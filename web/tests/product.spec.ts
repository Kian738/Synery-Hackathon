import {test,expect} from '@playwright/test';

test('readiness reports historical evidence and all four judge criteria',async({page})=>{
  await page.goto('/lab');
  await expect(page.getByRole('heading',{name:'Release readiness'})).toBeVisible();
  await expect(page.getByRole('heading',{name:/Does it work/})).toBeVisible({timeout:15000});
  for(const name of ['Interaction','Creativity','Pitch and demo'])await expect(page.getByRole('heading',{name:new RegExp(name)})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Find every feature'})).toBeVisible();
  await expect(page.getByText('Readiness evidence, not a predicted jury score. Raw misses remain misses.')).toBeVisible();
});

test('real computed equipment groups can be closed and reopened from chat',async({page})=>{
  await page.route('**/api/sessions/*/chat',async route=>{
    const sid=route.request().url().split('/').at(-2)!;
    const response=await page.request.post(`/api/sessions/${sid}/analysis`,{data:{kind:'count',item:'3d printer'}});
    const body=await response.json();
    const events:any[]=body.events.map((data:any)=>({type:'ui',data}));
    events.push({type:'assistant_start',data:{message_id:'answer',model:'fixture'}},{type:'assistant_delta',data:{message_id:'answer',text:'Eight printers in four rooms.'}},{type:'assistant_end',data:{message_id:'answer'}},{type:'reply',data:{message_id:'answer',text:'Eight printers in four rooms.',usage:{}}},{type:'done',data:null});
    await route.fulfill({contentType:'text/event-stream',body:events.map(e=>`data: ${JSON.stringify(e)}\n\n`).join('')});
  });
  await page.goto('/?building=proc-campus-dev-000');
  await page.getByRole('textbox',{name:'Message'}).fill('How many 3d printers and where?');
  await page.getByRole('button',{name:'Send',exact:true}).click();
  const result=page.getByRole('region',{name:'Visual answer'});
  await expect(result.getByRole('button',{name:/Makerspace 0.08.*5/})).toBeVisible();
  await expect(result.getByText('8 items',{exact:true})).toBeVisible();
  await expect(page.getByText('Eight printers in four rooms.',{exact:true})).toHaveCount(1);
  await result.getByRole('button',{name:/Items in Makerspace/}).click();
  await expect(result.locator('.result-list li')).toHaveCount(5);
  await result.getByRole('button',{name:'Back to rooms'}).click();
  await expect(result.locator('.result-list li')).toHaveCount(4);
  await page.getByRole('button',{name:'Close visual answer'}).click();
  await expect(result).toHaveCount(0);
  await page.getByRole('button',{name:'View results',exact:true}).click();
  await expect(result.locator('.result-list li')).toHaveCount(4);
});

test('streamed text is visible before final reply and stop recovers the composer',async({page})=>{
  // Controlled transport fixture verifies incremental UI, never claimed as live Claude evidence.
  await page.route('**/api/sessions/*/chat',async route=>{
    await route.fulfill({contentType:'text/event-stream',body:'data: {"type":"assistant_start","data":{"message_id":"partial","model":"fixture"}}\n\ndata: {"type":"assistant_delta","data":{"message_id":"partial","text":"Checking the recorded rooms."}}\n\ndata: {"type":"error","data":{"message":"Connection interrupted. Please retry."}}\n\ndata: {"type":"done","data":null}\n\n'});
  });
  await page.goto('/?building=proc-campus-dev-000');
  await page.getByRole('textbox',{name:'Message'}).fill('hello');await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect(page.getByText('Checking the recorded rooms.',{exact:true})).toBeVisible();
  await expect(page.getByText('Answer interrupted. Computed results remain available.',{exact:true})).toBeVisible();
  await expect(page.getByRole('textbox',{name:'Message'})).toBeEnabled();
});

test('all four speeds are visible and preserve paused progress',async({page})=>{
  await page.goto('/?building=proc-campus-dev-000&at=proc-campus-dev-000-F2-S017&to=Lab%204.26&step_free=1');
  await page.getByRole('button',{name:'Guide me step by step'}).click();
  await page.getByRole('button',{name:'Play preview',exact:true}).click();
  await page.getByRole('button',{name:'Pause preview',exact:true}).click();
  const progress=page.getByRole('slider',{name:'Preview progress'});await progress.fill('2');
  for(const speed of ['0.5','1','2','4']){
    const button=page.getByRole('button',{name:`Playback speed ${speed}×`,exact:true});await expect(button).toBeVisible();await button.click();
    await expect(button).toHaveAttribute('aria-pressed','true');await expect(progress).toHaveValue('2');
  }
});

test('scenario states its assumptions and presents a computed comparison',async({page})=>{
  test.setTimeout(300_000);
  await page.goto('/?building=proc-campus-dev-000');
  await page.getByLabel('Building tools',{exact:true}).click();
  await page.getByRole('button',{name:'Scenarios',exact:true}).click();
  const panel=page.getByRole('region',{name:'Fire / evacuation scenario'});
  await expect(panel.getByRole('group',{name:'Who is this for'}).getByRole('button')).toHaveCount(4);
  await page.getByRole('button',{name:/Quick fire test/}).click();
  const headline=page.locator('.scenario-headline');
  await expect(headline).toHaveText(/Everyone is out in \d+ s|of \d+ people get out/,{timeout:60000});
  await expect(panel.getByText(/estimated from seats/)).toBeVisible();
  await expect(page.getByText(/Everyone to the nearest exit/)).toBeVisible();
  await page.getByRole('button',{name:'Show more'}).click();
  await expect(page.getByText('What this is built on')).toBeVisible();
  const before=await headline.innerText();
  await panel.getByText('Change room, audience or numbers',{exact:true}).click();
  await panel.getByText('Your numbers',{exact:true}).click();
  await panel.getByLabel('People in the fire room').fill('20');
  await panel.getByLabel('Passage rate (people per minute)').fill('20');
  await panel.getByRole('button',{name:'Run scenario'}).click();
  await expect(panel.getByText(/Your numbers: \d+ of 20 people get out of the fire room; every door passes 20 people per minute/)).toBeVisible({timeout:200000});
  await expect(headline).not.toHaveText(before);
  await page.screenshot({path:'test-results/scenario-your-numbers.png'});
});
