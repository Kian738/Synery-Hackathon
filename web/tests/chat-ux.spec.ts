import { test, expect } from "@playwright/test";

const REPLY = "Lab 0.27 has the most chairs.\n\n- Lab 0.27: 14\n- Canteen 0.28: 12";

async function fakeChat(page: import("@playwright/test").Page, count = { n: 0 }) {
  await page.route("**/api/sessions/*/chat", async route => {
    count.n++;
    const events = [{ type: "reply", data: { text: REPLY, model: "fixture", usage: { input_tokens: 0, output_tokens: 0 } } }, { type: "done", data: null }];
    await route.fulfill({ contentType: "text/event-stream", body: events.map(e => `data: ${JSON.stringify(e)}\n\n`).join("") });
  });
}

test("the composer stays put while an answer arrives, and the answer says how it was understood", async ({ page }) => {
  await fakeChat(page);
  await page.goto("/?building=proc-campus-dev-000");
  const box = page.getByRole("textbox", { name: "Message" });
  await expect(box).toBeVisible({ timeout: 20_000 });
  const before = (await box.boundingBox())!.y;
  await box.fill("Where are the most chairs?");
  await box.press("Enter"); // keyboard-only send
  await expect(page.getByText("Lab 0.27 has the most chairs.")).toBeVisible();
  expect(Math.abs((await box.boundingBox())!.y - before)).toBeLessThan(2);
  const understood = page.getByLabel("How this was understood");
  await expect(understood).toContainText("Understood as");
  await expect(understood).toContainText("From ");
});

test("the user's message is a bubble, follow-up chips offer a next step and asking one sends it", async ({ page }) => {
  const count = { n: 0 };
  await fakeChat(page, count);
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByRole("textbox", { name: "Message" }).fill("Where are the most chairs?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const mine = page.locator(".conversation-scroll p", { hasText: "Where are the most chairs?" });
  await expect(mine).toBeVisible();
  expect(await mine.evaluate(el => getComputedStyle(el).borderRadius)).toContain("16px");
  const next = page.getByLabel("Ask next").getByRole("button").first();
  await expect(next).toBeVisible();
  await next.click();
  await expect.poll(() => count.n).toBe(2);
});

test("chat answer cards use the kit radii", async ({ page }) => {
  await fakeChat(page);
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByRole("textbox", { name: "Message" }).fill("Where are the most chairs?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("Lab 0.27 has the most chairs.")).toBeVisible();
  const radii = await page.evaluate(() => [...document.querySelectorAll(".k-next .k-ctl, .k-understood b, .k-composer .k-ctl")].map(e => getComputedStyle(e).borderRadius));
  expect(radii.length).toBeGreaterThan(3);
  expect(new Set(radii).size).toBeLessThanOrEqual(2); // 12px controls and 999px pills only
});
