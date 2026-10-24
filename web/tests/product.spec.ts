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

test('scenario requires explicit assumptions and presents a computed comparison',async({page})=>{
  await page.goto('/?building=proc-campus-dev-000');
  await page.getByLabel('Building tools',{exact:true}).click();
  await page.getByRole('button',{name:'Scenarios',exact:true}).click();
  const panel=page.getByRole('region',{name:'Scenario inputs'});
  await expect(panel.getByRole('button',{name:'Compare scenario'})).toBeDisabled();
  await panel.getByLabel('People in this room').fill('20');await panel.getByLabel('People per minute').fill('20');
  await panel.getByRole('button',{name:'Compare scenario'}).click();
  const answer=page.getByRole('region',{name:'Visual answer'});
  await expect(answer.getByRole('heading')).toContainText('of 20 evacuated',{timeout:20000});
  await answer.getByText('Inputs, method and assumptions',{exact:true}).click();
  await expect(answer.getByText(/Explicit user occupancy only/)).toBeVisible();
});
