import {test,expect} from "@playwright/test";
import {roomMentions} from "../src/lib/roomMentions";
import type {Space} from "../src/lib/types";
import fs from "node:fs/promises";
import path from "node:path";
import {getAssetVisual} from "../src/scene-assets/catalog";
import {partHalfExtents} from "../src/scene-assets/contact-sheet";

test("small robot cells keep rotated arms inside the supplied footprint",()=>{
  for(const [w,d] of [[.5,.5],[1,.5],[2,1]])for(const lod of ["overview","interior"] as const){
    const visual=getAssetVisual({type:"robot_cell",footprint:{width_m:w,depth_m:d,rotation_deg:0}},lod);
    for(const p of visual.parts){const h=partHalfExtents(p,w,d);expect(Math.abs(p.position[0])*w+h[0]).toBeLessThanOrEqual(w/2+.002);expect(Math.abs(p.position[2])*d+h[2]).toBeLessThanOrEqual(d/2+.002);}
  }
});

test("room links use unique exact references without linking measurements or ambiguous names",()=>{
  const spaces=[{id:"a",name:"Lab 2.17",ref:"2.17"},{id:"b",name:"Office",ref:"00.05.058"},{id:"c",name:"Office",ref:"3.14"}] as Space[];
  const text="Lab 2.17 is 2.17 m away from Office. Room 00.05.058 is beside room 3.14.";
  expect(roomMentions(text,spaces).map(m=>({text:text.slice(m.start,m.end),id:m.id}))).toEqual([{text:"Lab 2.17",id:"a"},{text:"00.05.058",id:"b"},{text:"3.14",id:"c"}]);
  expect(roomMentions("office",[{id:"a",name:"Office"},{id:"b",name:"OFFICE"}] as Space[])).toEqual([]);
  const marked="İ test Lab (A)+1.";
  const [mention]=roomMentions(marked,[{id:"x",name:"Lab (A)+1"}] as Space[]);
  expect(marked.slice(mention.start,mention.end)).toBe("Lab (A)+1");
});

test("chat room mention opens the real room inspector",async({page})=>{
  await page.route("**/api/sessions/*/chat",r=>r.fulfill({contentType:"text/event-stream",body:'data: {"type":"reply","data":{"text":"Look in Lab 2.17.","usage":{}}}\n\ndata: {"type":"done","data":null}\n\n'}));
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByRole("textbox",{name:"Message"}).fill("Where is it?");await page.getByRole("button",{name:"Send",exact:true}).click();
  await page.getByRole("region",{name:"Conversation"}).getByRole("button",{name:"Lab 2.17",exact:true}).click();
  await expect(page.getByRole("dialog",{name:"Lab 2.17",exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"Go here",exact:true})).toBeVisible();
});

test("scene consumes pinch-wheel zoom and the page itself never zooms",async({page})=>{
  await page.goto("/?building=proc-campus-dev-000");
  const stage=page.getByTestId("building-scene");await expect(page.locator("canvas")).toHaveAttribute("data-scene-painted","true");
  const cancelled=await stage.evaluate(el=>!el.dispatchEvent(new WheelEvent("wheel",{bubbles:true,cancelable:true,ctrlKey:true,deltaY:-15})));
  expect(cancelled).toBe(true);
  expect(await page.locator("body").evaluate(el=>!el.dispatchEvent(new WheelEvent("wheel",{bubbles:true,cancelable:true,ctrlKey:true,deltaY:-15})))).toBe(true);
});

test("phone drag works before any route and can open its own building view",async({page,browser,baseURL},info)=>{
  test.skip(info.project.name!=="desktop","Uses an independent phone context");
  await page.goto("/?building=proc-campus-dev-000");
  const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  await expect(page.locator("canvas")).toHaveAttribute("data-scene-painted","true");
  await page.getByLabel("Building tools",{exact:true}).click();
  await page.getByRole("button",{name:"Phone companion",exact:true}).click();await page.getByRole("button",{name:"Pair a phone",exact:true}).click();
  const code=page.locator(".cmp-code");await expect(code).toHaveText(/^\d{6}$/);
  const context=await browser.newContext({baseURL,viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  try{
    const phone=await context.newPage();await phone.goto(`/phone#code=${(await code.textContent())!.trim()}`);
    await phone.getByRole("button",{name:"Pair",exact:true}).click();await expect(page.getByRole("button",{name:"Allow",exact:true})).toBeVisible();await page.getByRole("button",{name:"Allow",exact:true}).click();
    await expect(phone.getByRole("heading",{name:"Explore the building"})).toBeVisible();
    await expect(phone.getByRole("link",{name:"Open 3D on this phone"})).toHaveAttribute("href",/building=proc-campus-dev-000&explore=1/);
    await expect(phone.getByRole("button",{name:"Turn on motion look"})).toBeHidden();
    await page.getByRole("button",{name:"Close phone setup"}).click();await page.waitForTimeout(700);
    const before=await page.locator("canvas").getAttribute("data-camera-position");
    const pad=phone.getByRole("group",{name:"Look pad: drag to turn the laptop view"});
    const b=(await pad.boundingBox())!;await phone.mouse.move(b.x+b.width*.4,b.y+b.height*.5);await phone.mouse.down();await phone.mouse.move(b.x+b.width*.7,b.y+b.height*.5,{steps:8});await phone.mouse.up();
    await expect.poll(()=>page.locator("canvas").getAttribute("data-camera-position")).not.toBe(before);
    await expect(page.getByRole("region",{name:"Route preview player"})).toHaveCount(0);
    const out=path.resolve("../runs/third-pass");await fs.mkdir(out,{recursive:true});await phone.screenshot({path:path.join(out,"phone-overview.png")});
    const popupPromise=context.waitForEvent("page");await phone.getByRole("link",{name:"Open 3D on this phone"}).click();const popup=await popupPromise;
    await expect(popup.locator("canvas")).toHaveAttribute("data-scene-painted","true");await expect(popup.locator(".navigator-shell")).toHaveClass(/stage-expanded/);
    await popup.screenshot({path:path.join(out,"phone-building.png")});
    expect(errors).toEqual([]);
  }finally{await context.close();}
});

test("CIT ground hallway keeps upper floor context without a blanket ceiling",async({page},info)=>{
  test.setTimeout(45_000);
  await page.goto("/?building=osm-way27917482&at=osm-way27917482-F0-S026&to=00.05.058");
  await expect(page.getByRole("region",{name:"Route"})).toContainText("00.05.058",{timeout:25_000});
  await page.getByRole("button",{name:"Guide me step by step"}).click();
  const scene=page.getByTestId("building-scene");
  await expect(scene).toHaveAttribute("data-ceiling-source","upper-floor-footprints");
  await expect(scene).toHaveAttribute("data-context-floors",/F1.*F2.*F3/);
  await expect(scene).toHaveAttribute("data-visible-floors",/F0.*F1.*F2.*F3/);
  await expect(page.locator("canvas")).toHaveAttribute("data-camera-position",/\[/);
  const box=(await page.getByRole("region",{name:"Route preview player"}).boundingBox())!;
  expect(box.height).toBeLessThan(160);
  const out=path.resolve("../runs/third-pass");await fs.mkdir(out,{recursive:true});await page.screenshot({path:path.join(out,`${info.project.name}-cit-atrium.png`)});
});
