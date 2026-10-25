import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

async function scopeTo(page: import("@playwright/test").Page, name: string) {
  const group = page.getByRole("group", { name: "Visible floors" });
  if (!(await group.isVisible())) await page.getByRole("button", { name: "Layers" }).click();
  await group.getByRole("button", { name, exact: true }).click();
}


const campus="/?building=proc-campus-dev-000";
async function capture(page:any,name:string,project:string){
  const folder=path.resolve(process.cwd(),"../runs/ux-overhaul");await mkdir(folder,{recursive:true});
  if(await page.locator("canvas").count())await expect(page.locator("canvas")).toHaveAttribute("data-scene-painted","true");
  await page.screenshot({path:path.join(folder,`${project}-${name}.png`)});
}
test("computed analytics cards are complete and paged (model wording fixture)",async({page},info)=>{
  const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  // Offline UI fixture: real computed ranking, deliberately mocked model wording.
  await page.route('**/api/sessions/*/chat',async route=>{
    const sid=route.request().url().split('/').at(-2)!;
    const computed=await page.request.post(`/api/sessions/${sid}/analysis`,{data:{kind:'ranking',item:'chairs'}});
    const body=await computed.json();
    const events=body.events.map((data:any)=>({type:'ui',data}));
    events.push({type:'reply',data:{text:'Computed ranking fixture.',model:'fixture',usage:{input_tokens:0,output_tokens:0}}},{type:'done',data:null});
    await route.fulfill({contentType:'text/event-stream',body:events.map((e:any)=>`data: ${JSON.stringify(e)}\n\n`).join('')});
  });
  await page.goto(campus);
  await page.getByRole("textbox",{name:"Message"}).fill("Which room has the most chairs?");
  await page.getByRole("button",{name:"Send",exact:true}).click();
  const answer=page.getByRole("region",{name:"Visual answer"});
  await expect(answer.getByRole("heading")).toHaveText("Rooms ranked by chairs");
  await expect(page.getByText("Computed ranking fixture.",{exact:true})).toBeVisible();
  await expect(answer.getByRole("navigation",{name:"Result pages"})).toBeVisible();
  await expect(answer.locator(".result-list button").first()).toBeVisible();
  const first=await answer.locator(".result-list button").first().textContent();
  await answer.getByRole("button",{name:"Next",exact:true}).click();
  await expect(answer.getByRole("navigation",{name:"Result pages"})).toContainText("26");
  await answer.getByRole("button",{name:"Previous",exact:true}).click();
  await expect(answer.locator(".result-list button").first()).toHaveText(first!);
  await answer.locator(".result-list button").first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await capture(page,"ranking",info.project.name);
  await page.getByRole("button",{name:"I'm here",exact:true}).click();
  await expect(page.getByRole("status").filter({hasText:"Location set:"})).toBeVisible();
  await expect(page.getByRole("combobox",{name:"Facing direction"})).toHaveCount(0);
  expect(errors).toEqual([]);
});
test("floor scope and linked plan stay usable through preview",async({page},info)=>{
  await page.goto(`${campus}&at=proc-campus-dev-000-F2-S008&to=Canteen%200.28`);
  const scene=page.getByTestId("building-scene");await expect(scene).toBeVisible();
  await expect(page.getByRole("region",{name:"Route"})).toBeVisible();  // the deep-link route must be loaded before the scope is changed
  const readAloud=page.getByRole("button",{name:"Read aloud"});  // spoken steps start a camera tour that would override the floor scope under test
  if(await readAloud.getAttribute("aria-pressed")==="true")await readAloud.click();
  await expect(page.locator(".building-tools")).toBeAttached();
  if(await page.locator(".building-tools > summary").isVisible() && !(await page.locator(".building-tools").getAttribute("open")!==null))await page.getByLabel("Building tools",{exact:true}).click();
  await scopeTo(page,"Route floors");
  await expect(scene).toHaveAttribute("data-visible-floors",/F0.*F1.*F2/);
  await capture(page,"route-floors",info.project.name);
  await expect(page.locator(".building-tools")).toBeAttached();
  if(await page.locator(".building-tools > summary").isVisible() && !(await page.locator(".building-tools").getAttribute("open")!==null))await page.getByLabel("Building tools",{exact:true}).click();
  await scopeTo(page,"This floor");
  await expect(scene).toHaveAttribute("data-visible-floors",/^[^,]+$/);
  await page.getByRole("button",{name:"Guide me step by step"}).click();
  await page.getByRole("button",{name:"Play preview",exact:true}).click();
  await expect(page.getByRole("button",{name:"Pause preview"})).toBeVisible();
  await expect(page.locator("canvas")).toHaveAttribute("data-camera-floor",/F2/);
  await expect.poll(async()=>Number(await page.getByRole("slider",{name:"Preview progress"}).inputValue())).toBeGreaterThan(.3);
  await capture(page,"preview",info.project.name);
  await page.getByRole("button",{name:"Pause preview"}).click();
  await page.getByRole("button",{name:"Show map",exact:true}).click();
  await expect(page.getByRole("button",{name:"Close map"})).toBeVisible();
  await capture(page,"expanded-plan",info.project.name);
});
