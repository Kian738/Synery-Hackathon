import { test,expect } from "@playwright/test";
import { PickIntent } from "../src/lib/interaction";
import { placeMapLabels } from "../src/lib/mapLabels";
import fs from "node:fs/promises";
import path from "node:path";

test("a drag returning to its origin is never a selection",()=>{
  const gesture=new PickIntent();gesture.begin(0,0);gesture.move(20,0);gesture.move(0,0);expect(gesture.moved).toBe(true);
  gesture.begin(0,0);gesture.move(2,2);expect(gesture.moved).toBe(false);
});
test("dense labels retain the selected label without overlaps",()=>{
  const labels=Array.from({length:80},(_,i)=>({id:String(i),x:i%4*8,y:Math.floor(i/4)*8,width:55,height:17,priority:i===17?1000:0}));
  const ids=placeMapLabels(labels,12);expect(ids.has("17")).toBe(true);expect(ids.size).toBeLessThan(12);
});
test("CIT reported route opens an uncluttered player with one-click play",async({page},info)=>{
  const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  await page.goto("/?building=osm-way27917482&at=osm-way27917482-F3-S069&to=00.05.058");
  await expect(page.getByRole("region",{name:"Route"})).toContainText("00.05.058",{timeout:20_000});
  await page.getByRole("button",{name:"Guide me step by step"}).click();
  await expect(page.locator(".navigation-panel")).toBeHidden();
  await expect(page.locator(".floor-selector")).toBeHidden();
  await expect(page.getByRole("region",{name:"Linked floor plan"})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Ceiling",exact:true})).toHaveCount(0);
  await page.getByRole("button",{name:"Play preview",exact:true}).click();
  await expect.poll(async()=>Number(await page.getByRole("slider",{name:"Preview progress"}).inputValue())).toBeGreaterThan(.2);
  await page.getByRole("button",{name:"Pause preview"}).click();
  const directory=path.resolve("../runs/ux2");await fs.mkdir(directory,{recursive:true});
  await page.screenshot({path:path.join(directory,`${info.project.name}-cit-guide.png`)});
  await page.getByRole("button",{name:"Show map",exact:true}).click();
  await expect(page.getByRole("region",{name:"Linked floor plan"})).toBeVisible();
  await page.screenshot({path:path.join(directory,`${info.project.name}-cit-map.png`)});
  expect(errors).toEqual([]);
});
test("dragging the 3D model does not open the inspector",async({page})=>{
  await page.goto("/?building=proc-campus-dev-000");
  const canvas=page.locator("canvas");await expect(canvas).toHaveAttribute("data-scene-painted","true");
  const box=(await canvas.boundingBox())!;const x=box.x+box.width*.55,y=box.y+box.height*.55;
  await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+65,y+30,{steps:8});await page.mouse.move(x,y,{steps:8});await page.mouse.up();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
test("ten identical tools form one inspectable evidence group",async({page})=>{
  await page.route("**/api/sessions/*/chat",route=>{
    const events=[];
    for(let i=0;i<10;i++){events.push({type:"tool",data:{name:"count_items",input:{item_type:"chair",floor:`floor ${i}`}}});events.push({type:"tool_result",data:{name:"count_items",content:JSON.stringify({count:i}),is_error:false}});}
    events.push({type:"reply",data:{text:"All counts were computed.",model:"fixture",usage:{}}});events.push({type:"done",data:null});
    return route.fulfill({contentType:"text/event-stream",body:events.map(e=>`data: ${JSON.stringify(e)}\n\n`).join("")});
  });
  await page.goto("/?building=proc-campus-dev-000");await page.getByRole("textbox",{name:"Message"}).fill("Count chairs by floor");await page.getByRole("button",{name:"Send",exact:true}).click();
  const trace=page.locator(".tool-trace");await expect(trace).toHaveCount(1);await expect(trace.locator(":scope > summary")).toContainText("10 calls");
  await trace.locator(":scope > summary").click();await expect(trace.locator(":scope > details")).toHaveCount(1);
  await expect(trace.locator(":scope > details > summary")).toContainText("×10");
  await expect(page.getByText("All counts were computed.")).toBeVisible();
});
