import { expect, test } from "@playwright/test";

const FACTORY = "/?building=proc-factory-dev-003";
const CAMPUS = "/?building=proc-campus-dev-000";

test("welcome shows categories that exist in this building", async ({ page }) => {
  await page.goto(FACTORY);
  await expect(page.getByRole("heading", { name: /know your building/i })).toBeVisible();
  await expect(page.getByRole("button", { name: "Coffee" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Toilets" }).first()).toBeVisible();
});

test("start defaults to the main entrance, so a category routes in one tap", async ({ page }) => {
  await page.goto(CAMPUS);
  await expect(page.getByText("Starting from")).toContainText("Main lobby");
  await page.getByRole("button", { name: "Toilets" }).first().click();
  await expect(page.getByRole("region", { name: "Route" })).toContainText(/Toilet/);
});

test("example requests only mention things this building has", async ({ page }) => {
  await page.goto(CAMPUS);
  const examples = page.locator("ul li button");
  await expect(examples.first()).toBeVisible();
  const text = (await examples.allTextContents()).join(" ");
  expect(text).not.toContain("3D printer");
  expect(text).not.toContain("office lift");
});

test("start picker lists entrances and searches rooms", async ({ page }) => {
  await page.goto(FACTORY);
  await page.getByRole("button", { name: /starting from/i }).click();
  await page.getByRole("textbox", { name: "Search for your room" }).fill("Kitchen 0.31");
  await page.getByRole("button", { name: /Kitchen 0.31/ }).click();
  await expect(page.getByText("Starting from")).toContainText("Kitchen 0.31");
});

test("indoor route never leaves the building (no entrance teleport)", async ({ page }) => {
  await page.goto(`${FACTORY}&at=proc-factory-dev-003-F0-S031&to=H-B3`);
  const route = page.getByRole("region", { name: "Route" });
  await expect(route).toContainText("Main aisle H-B3");
  await expect(route).not.toContainText(/go outside/i);
});

test("deep link draws a multi-floor route with followable steps", async ({ page }) => {
  await page.goto(`${FACTORY}&at=proc-factory-dev-003-F0-S021&to=Meeting%20room%201.10`);
  const route = page.getByRole("region", { name: "Route" });
  await expect(route).toContainText("Meeting room 1.10");
  await expect(route.getByRole("listitem")).not.toHaveCount(0);
  await expect(route).toContainText(/floor change/);
  await expect(route).toContainText(/m walk/);
});

test("follow-route mode advances through eye-level waypoints", async ({ page }) => {
  await page.goto(`${FACTORY}&at=proc-factory-dev-003-F0-S021&to=Meeting%20room%201.10`);
  await page.getByRole("button", { name: "Start step by step" }).click();
  await expect(page.getByText(/Route preview.*position is manually set/)).toBeVisible();
  await expect(page.getByText(/Waypoint 1 \/ /)).toBeVisible();
  const canvas=page.locator("canvas");
  await expect(canvas).toHaveAttribute("data-camera-position", /\[/);
  const before=await canvas.getAttribute("data-camera-position");
  await page.getByRole("button", {name:"Next waypoint"}).click();
  await expect(canvas).not.toHaveAttribute("data-camera-position", before!);
  await expect(page.getByText(/Waypoint 2 \/ /)).toBeVisible();
});

test("step-free toggle is announced as pressed", async ({ page }) => {
  await page.goto(FACTORY);
  const toggle = page.getByRole("button", { name: "Step-free" });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
});

test("3D view can be switched on", async ({ page }) => {
  await page.goto(FACTORY);
  await page.getByRole("button", { name: "3D" }).click();
  await expect(page.getByRole("button", { name: "3D" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "All floors" })).toBeVisible();
});

test("floor-plan fallback remains available", async ({ page }) => {
  await page.goto(FACTORY);
  await page.getByRole("button", {name:"Floor plan", exact:true}).click();
  await expect(page.getByRole("img",{name:"Floor plan",exact:true})).toBeVisible();
});

// Chromium can return a promise from scrolling. Effects must never return it as cleanup.
test("chat stays usable through multiple replies and promise-returning scrolling", async ({ page }) => {
  await page.addInitScript(() => { Element.prototype.scrollIntoView = (() => Promise.resolve()) as any; });
  await page.route("**/api/sessions/*/chat", async route => {
    await route.fulfill({contentType:"text/event-stream", body:'data: {"type":"reply","data":{"text":"The coffee machine is in the kitchen.","model":"test"}}\n\ndata: {"type":"done","data":null}\n\n'});
  });
  await page.goto(CAMPUS);
  for (const text of ["Where is coffee?", "And the printer?"]) {
    await page.getByRole("textbox",{name:"Message"}).fill(text);
    await page.getByRole("button",{name:"Send",exact:true}).click();
    await expect(page.getByRole("region",{name:"Conversation"})).toContainText(text);
    await expect(page.getByRole("button",{name:"Recover view"})).toHaveCount(0);
  }
  await expect(page.getByText("The coffee machine is in the kitchen.")).toHaveCount(2);
});

test("HTTP chat failures preserve the composer and building controls", async ({page}) => {
  await page.route("**/api/sessions/*/chat", route => route.fulfill({status:503,body:"temporarily unavailable"}));
  await page.goto(CAMPUS);
  await page.getByRole("textbox",{name:"Message"}).fill("Hello");
  await page.getByRole("button",{name:"Send",exact:true}).click();
  await expect(page.getByRole("region",{name:"Conversation"})).toContainText("503");
  await expect(page.getByRole("button",{name:"3D",exact:true})).toBeVisible();
  await expect(page.getByRole("textbox",{name:"Message"})).toBeEnabled();
});

test("weak point simulation highlights the real step-free consequence", async ({page}) => {
  await page.goto(FACTORY);
  await page.getByRole("button",{name:"Test weak points"}).click();
  await expect(page.getByRole("region",{name:"Weak points"})).toContainText("Office lift");
  await expect(page.getByRole("region",{name:"Weak points"})).toContainText("29 of 56");
});

test("3D scene has compiled geometry and a rendered canvas", async ({page}, testInfo) => {
  const errors: string[]=[]; page.on("pageerror",e=>errors.push(e.message));
  await page.goto(CAMPUS);
  await expect(page.getByTestId("building-scene")).toHaveAttribute("data-scene-revision", /[a-f0-9]{16}/);
  await expect(page.locator("canvas")).toBeVisible();
  expect(errors).toEqual([]);
  await page.screenshot({path:`../runs/demo/${testInfo.project.name}.png`});
});


test("an empty streamed route is rejected without crashing", async ({page}) => {
  await page.route("**/api/sessions/*/chat", route => route.fulfill({contentType:"text/event-stream",body:'data: {"type":"ui","data":{"type":"route","route":{"polyline":[]}}}\n\ndata: {"type":"done","data":null}\n\n'}));
  await page.goto(CAMPUS);
  await page.getByRole("textbox",{name:"Message"}).fill("Route please");
  await page.getByRole("button",{name:"Send",exact:true}).click();
  await expect(page.getByRole("status")).toContainText("incomplete");
  await expect(page.getByRole("button",{name:"Recover view"})).toHaveCount(0);
});

test("closure events show step-free impact without contradictory copy", async ({page}) => {
  await page.route("**/api/sessions/*/chat", async route => {
    const session=route.request().url().split("/").at(-2);
    const result=await page.request.post(`/api/sessions/${session}/close`,{data:{element:"Office lift",closed:true}});
    const body=await result.json();
    await route.fulfill({contentType:"text/event-stream",body:body.events.map((data:unknown)=>`data: ${JSON.stringify({type:"ui",data})}\n\n`).join("")+'data: {"type":"done","data":null}\n\n'});
  });
  await page.goto(FACTORY);
  await page.getByRole("textbox",{name:"Message"}).fill("Close the office lift");
  await page.getByRole("button",{name:"Send",exact:true}).click();
  await expect(page.getByRole("status")).toContainText("29 of 56 rooms lose their step-free way out");
  await expect(page.getByRole("status")).not.toContainText("No rooms lose");
});

test("a verified widening applies to the same door and restores a route", async ({page}) => {
  await page.route("**/api/sessions/*/chat", async route => {
    const session=route.request().url().split("/").at(-2);
    const result=await page.request.post(`/api/sessions/${session}/route`,{data:{start:"Main lobby",destination:"Print room 0.16",step_free:true,min_door_width_m:1.1}});
    const body=await result.json();
    await route.fulfill({contentType:"text/event-stream",body:body.events.map((data:unknown)=>`data: ${JSON.stringify({type:"ui",data})}\n\n`).join("")+'data: {"type":"done","data":null}\n\n'});
  });
  await page.goto(CAMPUS);
  await page.getByRole("textbox",{name:"Message"}).fill("Can a 1.1 metre trolley reach the print room?");
  await page.getByRole("button",{name:"Send",exact:true}).click();
  await expect(page.getByRole("button",{name:"Apply to model"})).toBeVisible();
  await page.getByRole("button",{name:"Apply to model"}).click();
  await expect(page.getByRole("region",{name:"Route"})).toContainText("Print room 0.16");
});

test("microphone denial is recoverable and does not submit speech", async ({page}) => {
  await page.addInitScript(()=>{
    (window as any).SpeechRecognition=class {
      onerror:any;onend:any; onresult:any;
      start(){setTimeout(()=>{this.onerror?.({error:"not-allowed"});this.onend?.();},0);}
      abort(){this.onend?.();}
    };
  });
  await page.goto(CAMPUS);
  await page.getByRole("button",{name:"Speak",exact:true}).click();
  await expect(page.getByRole("status")).toContainText("Microphone access was denied");
  await expect(page.getByRole("button",{name:"Speak",exact:true})).toBeVisible();
  await expect(page.getByRole("region",{name:"Conversation"})).toHaveCount(0);
});

test("reduced motion uses static waypoint guidance", async ({page}) => {
  await page.emulateMedia({reducedMotion:"reduce"});
  await page.goto(`${FACTORY}&at=proc-factory-dev-003-F0-S021&to=Meeting%20room%201.10`);
  await page.getByRole("button",{name:"Start step by step"}).click();
  await expect(page.getByRole("button",{name:"Next waypoint"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Play preview"})).toHaveCount(0);
});
