// Real browser, real SSE, real tools. No mocked chat responses.
const {chromium,expect}=require('@playwright/test');
const fs=require('fs');const path=require('path');
const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
(async()=>{
  const browser=await chromium.launch({channel:'chrome',headless:true});
  let exhausted=false;
  try{for(const [index,scenario] of input.cases.entries()){
    if(exhausted){console.log('FW_CASE '+JSON.stringify({id:scenario.id,correct:false,outcome:'incomplete',reason:'batch token budget exhausted'}));continue;}
    const context=await browser.newContext({viewport:index%2?{width:390,height:844}:{width:1440,height:900},isMobile:index%2===1,hasTouch:index%2===1});
    const page=await context.newPage();const started=Date.now();let result={id:scenario.id,kind:scenario.family,building:scenario.building,correct:false,outcome:'failed'};
    try{
      await page.addInitScript(()=>{
        window.__fwEvents=[];window.__fwSession='';const original=window.fetch;
        window.fetch=async(...args)=>{
          const response=await original(...args);const url=String(args[0]);
          if(url==='/api/sessions'&&args[1]?.method==='POST')response.clone().json().then(j=>{window.__fwSession=j.session_id;});
          if(/\/api\/sessions\/[^/]+\/chat$/.test(url)&&response.body){
            const reader=response.clone().body.getReader(),decoder=new TextDecoder();
            (async()=>{let buffer='';for(;;){const {done,value}=await reader.read();buffer+=decoder.decode(value,{stream:!done});let cut;while((cut=buffer.indexOf('\n\n'))>=0){const chunk=buffer.slice(0,cut);buffer=buffer.slice(cut+2);const data=chunk.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trimStart()).join('\n');if(data){try{window.__fwEvents.push({...JSON.parse(data),observed_at:Date.now()});}catch{}}}if(done)break;}})().catch(()=>{});
          }
          return response;
        };
      });
      await page.goto(input.url+'/?building='+scenario.building);
      for(const question of scenario.turns){
        const before=await page.evaluate(()=>window.__fwEvents.filter(e=>e.type==='done').length);
        await page.getByRole('textbox',{name:'Message'}).fill(question);
        await page.getByRole('button',{name:'Send',exact:true}).click();
        await page.waitForFunction(n=>window.__fwEvents.filter(e=>e.type==='done').length>n,before,{timeout:75000});
        await expect(page.getByRole('button',{name:'Stop',exact:true})).toHaveCount(0);
        await page.getByRole('region',{name:'Conversation',exact:true}).evaluate(el=>{el.scrollTop=el.scrollHeight;});
      }
      const events=await page.evaluate(()=>window.__fwEvents),session=await page.evaluate(()=>window.__fwSession);
      const screenshot=path.join(input.artifacts,scenario.id+'.png');await page.screenshot({path:screenshot,fullPage:false});
      const response=await page.request.post(input.url+'/api/lab/evaluate-conversation',{data:{case_id:scenario.id,session_id:session,events},timeout:70000});
      if(!response.ok())throw Error('Evaluation failed with HTTP '+response.status());
      const evaluated=await response.json();exhausted=!!evaluated.incomplete||evaluated.budget_used>=input.tokenBudget;
      const usage={...evaluated.review_usage};for(const event of events)if(event.type==='reply'){for(const [k,v] of Object.entries(event.data.usage??{}))if(k.endsWith('_tokens')&&typeof v==='number')usage[k]=(usage[k]??0)+v;}
      const first=events.find(e=>e.type==='assistant_delta'),last=events.filter(e=>e.type==='reply').at(-1);
      result={...result,...evaluated,events,usage,screenshot,correct:evaluated.correct,outcome:evaluated.incomplete?'incomplete':evaluated.correct?'passed':'failed',first_delta_ms:first?first.observed_at-started:null,finished_ms:Date.now()-started,streamed_before_final:!!first&&!!last&&first.observed_at<last.observed_at};
      fs.writeFileSync(path.join(input.artifacts,scenario.id+'.json'),JSON.stringify(result,null,2));
    }catch(error){result.reason=error.message;result.events=await page.evaluate(()=>window.__fwEvents).catch(()=>[]);}
    finally{await context.close();}
    console.log('FW_CASE '+JSON.stringify(result));
  }}finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exit(1);});
