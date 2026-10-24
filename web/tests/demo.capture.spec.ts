import { expect, test } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";

// Explicit capture command only; regular UI regression runs do not wait for recordings.
test.use({video:process.env.FLOORWISE_CAPTURE_DEMO === "1" ? {mode:"on",size:{width:1440,height:900}} : "off"});
test("capture a deterministic fallback of the real route and widening workflow", async ({page},testInfo)=>{
  test.skip(process.env.FLOORWISE_CAPTURE_DEMO !== "1" || testInfo.project.name !== "desktop", "Use the documented capture command");
  test.setTimeout(120_000);
  const out=path.resolve("../runs/demo");await fs.mkdir(out,{recursive:true});
  await page.route("**/api/sessions/*/chat", async route=>{
    const sid=route.request().url().split("/").at(-2)!;
    const text=route.request().postDataJSON().text as string;
    if(text.includes("chairs")){
      const response=await page.request.post(`/api/sessions/${sid}/chat`,{data:{text}});
      await route.fulfill({contentType:"text/event-stream",body:await response.text()});return;
    }
    const response=text.includes("closed")
      ?await page.request.post(`/api/sessions/${sid}/close`,{data:{element:"Lift 2",closed:true}})
      :await page.request.post(`/api/sessions/${sid}/route`,{data:{start:"Main lobby",destination:"Print room 0.16",step_free:true,min_door_width_m:1.1}});
    const result=await response.json();
    const events=result.events.map((data:unknown)=>`data: ${JSON.stringify({type:"ui",data})}\n\n`).join("");
    await route.fulfill({contentType:"text/event-stream",body:events+'data: {"type":"done","data":null}\n\n'});
  });
  await page.goto("/?building=proc-campus-dev-000&at=proc-campus-dev-000-F2-S017&to=Lab%204.26&step_free=1");
  await expect(page.getByRole("region",{name:"Route"})).toContainText("Lab 4.26");
  await expect(page.locator("canvas")).toBeVisible();
  await page.getByRole("combobox",{name:"Visible floors"}).selectOption("building");
  await page.waitForTimeout(2000);
  await page.screenshot({path:path.join(out,"building-route.png")});
  await page.waitForTimeout(4000);
  await page.getByRole("button",{name:"Guide me",exact:true}).click();
  await expect(page.locator("canvas")).toHaveAttribute("data-camera-position", /\[/);
  await page.screenshot({path:path.join(out,"first-person.png")});
  await page.getByRole("button",{name:"Play preview",exact:true}).click();
  await page.waitForTimeout(6000);
  await page.getByRole("button",{name:"Pause preview",exact:true}).click();
  await page.getByRole("button",{name:"Next instruction",exact:true}).click();
  await page.waitForTimeout(3000);
  await page.getByRole("button",{name:"3D",exact:true}).click();
  await page.getByRole("textbox",{name:"Message"}).fill("Lift 2 is closed for maintenance. What changes?");
  await page.getByRole("button",{name:"Send",exact:true}).click();
  await expect(page.getByRole("status")).toBeVisible();
  await page.waitForTimeout(4000);
  await page.screenshot({path:path.join(out,"closure-reroute.png")});
  await page.getByRole("button",{name:"Stress test",exact:true}).click();
  await expect(page.getByRole("region",{name:"Building stress test"})).toBeVisible();
  await page.waitForTimeout(4000);
  await page.getByRole("textbox",{name:"Message"}).fill("Can a 1.1 m trolley reach Print room 0.16 from Main lobby?");
  await page.getByRole("button",{name:"Send",exact:true}).click();
  await expect(page.getByRole("button",{name:"Apply to model"})).toBeVisible();
  await page.waitForTimeout(4000);
  await page.getByRole("button",{name:"Apply to model"}).click();
  await expect(page.getByRole("region",{name:"Route"})).toContainText("Print room 0.16");
  await page.waitForTimeout(4000);
  await page.screenshot({path:path.join(out,"verified-fix.png")});
  await page.getByRole("textbox",{name:"Message"}).fill("Which room has the most chairs?");
  await page.getByRole("button",{name:"Send",exact:true}).click();
  await expect(page.getByRole("region",{name:"Visual answer"})).toContainText("Rooms ranked by chairs");
  await page.waitForTimeout(2500);
  await page.screenshot({path:path.join(out,"visual-answer.png")});
  const video=page.video();await page.close();if(video)await video.saveAs(path.join(out,"fallback.webm"));
  await fs.writeFile(path.join(out,"README.txt"),"Recorded deterministic fallback: real backend tools and geometry, scripted chat transport, no live Claude or microphone audio. Live Claude was evaluated separately with fw eval rehearse.\n");
});
