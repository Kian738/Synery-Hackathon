import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const campus="/?building=proc-campus-dev-000";
async function capture(page:any,name:string,project:string){
  const folder=path.resolve(process.cwd(),"../runs/ux-overhaul");await mkdir(folder,{recursive:true});
  if(await page.locator("canvas").count())await expect(page.locator("canvas")).toHaveAttribute("data-scene-painted","true");
  await page.screenshot({path:path.join(folder,`${project}-${name}.png`)});
}
test("complete real chat analytics are visual, paged and free of model calls",async({page},info)=>{
  const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  await page.goto(campus);
  await page.getByRole("textbox",{name:"Message"}).fill("Which room has the most chairs?");
  await page.getByRole("button",{name:"Send",exact:true}).click();
  const answer=page.getByRole("region",{name:"Visual answer"});
  await expect(answer.getByRole("heading")).toHaveText("Rooms ranked by chairs");
  await expect(page.getByText(/Computed locally/)).toBeVisible();
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
  await page.getByRole("combobox",{name:"Facing direction"}).selectOption("90");
  expect(errors).toEqual([]);
});
test("floor scope and linked plan stay usable through preview",async({page},info)=>{
  await page.goto(`${campus}&at=proc-campus-dev-000-F2-S008&to=Canteen%200.28`);
  const scene=page.getByTestId("building-scene");await expect(scene).toBeVisible();
  await page.getByRole("combobox",{name:"Visible floors"}).selectOption("route");
  await expect(scene).toHaveAttribute("data-visible-floors",/F0.*F1.*F2/);
  await capture(page,"route-floors",info.project.name);
  await page.getByRole("combobox",{name:"Visible floors"}).selectOption("current");
  await expect(scene).toHaveAttribute("data-visible-floors",/^[^,]+$/);
  await page.getByRole("button",{name:"Guide me step by step"}).click();
  await page.getByRole("button",{name:"Preview route",exact:true}).click();
  await page.getByRole("button",{name:"Play preview",exact:true}).click();
  await expect(page.getByRole("button",{name:"Pause preview"})).toBeVisible();
  await expect(page.locator("canvas")).toHaveAttribute("data-camera-floor",/F2/);
  await expect.poll(async()=>Number(await page.getByRole("slider",{name:"Preview progress"}).inputValue())).toBeGreaterThan(.3);
  await capture(page,"preview",info.project.name);
  await page.getByRole("button",{name:"Pause preview"}).click();
  await page.getByRole("button",{name:"Expand plan",exact:true}).click();
  await expect(page.getByRole("button",{name:"Shrink plan"})).toBeVisible();
  await capture(page,"expanded-plan",info.project.name);
});
