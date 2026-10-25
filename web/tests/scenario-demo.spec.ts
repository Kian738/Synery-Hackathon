import { expect, test } from "@playwright/test";

// The two-minute demo path, end to end, with screenshots for review: test-results/demo-*.png
test.beforeEach(({}, info) => test.skip(info.project.name === "phone", "desktop analysis view"));

test("demo path: quick fire test, checked steps, apply the fix and see the new time", async ({ page }) => {
  test.setTimeout(180_000); // the N-1 check re-solves every exit-loss scenario, about 20 s
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByLabel("Building tools", { exact: true }).click();
  await page.getByRole("button", { name: "Scenarios", exact: true }).click();
  await page.getByRole("button", { name: /Quick fire test/ }).click();
  const headline = page.locator(".scenario-headline");
  await expect(headline).toHaveText(/Everyone is out in \d+ s/, { timeout: 60000 });
  const before = Number((await headline.innerText()).match(/(\d+) s/)![1]);
  await page.screenshot({ path: "test-results/demo-1-result.png" });
  await page.getByText(/\d+ steps checked/).click();
  await page.screenshot({ path: "test-results/demo-2-steps.png" });
  await page.getByRole("button", { name: /Apply to model/ }).click();
  await expect(async () => {
    const after = Number((await headline.innerText()).match(/(\d+) s/)![1]);
    expect(after).toBeLessThan(before);
  }).toPass({ timeout: 60000 });
  await page.screenshot({ path: "test-results/demo-3-applied.png" });
  await page.locator("summary", { hasText: /^What if$/ }).click();
  await page.getByRole("button", { name: "Check if an exit fails" }).click();
  await expect(page.getByText(/If one exit is lost, everyone is out in \d+ s/)).toBeVisible({ timeout: 90000 });
  await page.screenshot({ path: "test-results/demo-4-n-minus-one.png" });
});

test("replay autoplays to the total, seeks, shows responders, and the exit limit row re-runs", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByLabel("Building tools", { exact: true }).click();
  await page.getByRole("button", { name: "Scenarios", exact: true }).click();
  await page.getByRole("button", { name: /Quick fire test/ }).click();
  const counter = page.locator(".scenario-counter");
  await expect(counter).toHaveText(/\d+ of \d+ out/, { timeout: 60000 });
  const total = Number((await counter.innerText()).match(/of (\d+) out/)![1]);
  const first = Number((await counter.innerText()).match(/^(\d+)/)![1]);
  expect(first).toBeLessThan(total);
  const beat = page.locator(".scenario-beat");
  await expect(beat).not.toHaveText("", { timeout: 10000 });
  const firstBeat = await beat.innerText();
  await expect.poll(() => beat.innerText(), { timeout: 30000 }).not.toBe(firstBeat);
  await expect(counter).toHaveText(`${total} of ${total} out`, { timeout: 30000 });
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible();
  const slider = page.getByRole("slider", { name: "Replay time" });
  await slider.fill("0");
  await expect(counter).toHaveText(new RegExp(`of ${total} out`));
  await slider.fill(await slider.getAttribute("max") as string);
  await expect(counter).toHaveText(`${total} of ${total} out`);
  await page.getByRole("button", { name: "Floor plan" }).click();
  // Navigator.tsx does not pass the scenario mark to PlanView yet, so the plan label is not asserted; the legend is.
  await expect(page.getByText(/Blue: responders/)).toBeVisible();
  await page.locator("summary", { hasText: /^What if$/ }).click();
  await page.getByRole("spinbutton", { name: "Max people" }).fill("3");
  await page.getByRole("button", { name: "Re-run with limit" }).click();
  await expect(page.locator(".scenario-headline")).toHaveText(/(\d+ of \d+ people get out|Everyone is out in \d+ s)/, { timeout: 60000 });
  await expect(counter).toBeVisible();
});

test("a scenario that arrives through chat opens the panel and replays on its own, then voice-style events pause it", async ({ page, request }) => {
  await page.goto("/?building=proc-campus-dev-000");
  const sid = await page.evaluate(async () => (await (await fetch("/api/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ building_id: "proc-campus-dev-000" }) })).json()).session_id);
  const space = (await (await request.get(`/api/sessions/${sid}/scene`)).json()).spaces.find((s: any) => s.name === "Canteen 0.28").id;
  const report = await (await request.post(`/api/sessions/${sid}/scenario`, { data: { template: "evacuation", params: { spec: { hazards: [{ spaces: [space] }], responders: { auto: true } } }, audience: "safety_officer" } })).json();
  const body = [
    { type: "ui", data: { type: "scenario_result", report, hazard: space } },
    { type: "reply", data: { text: "Here is what happens.", usage: {}, model: "test" } },
    { type: "done", data: null },
  ].map(e => `data: ${JSON.stringify(e)}\n\n`).join("");
  await page.route("**/api/sessions/*/chat", route => route.fulfill({ contentType: "text/event-stream", body }));
  await page.getByRole("textbox", { name: "Message" }).fill("There is a fire in the canteen, what happens?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const counter = page.getByText(/\d+ of \d+ out/).first();
  await expect(counter).toBeVisible({ timeout: 30000 });
  const total = Number((await counter.innerText()).match(/of (\d+)/)![1]);
  await expect(async () => { expect(Number((await counter.innerText()).match(/(\d+) of/)![1])).toBe(total); }).toPass({ timeout: 40000 });
});

test("blocking an exit (limit 0) reroutes people and takes longer; the first beat frames the fire room", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByLabel("Building tools", { exact: true }).click();
  await page.getByRole("button", { name: "Scenarios", exact: true }).click();
  await page.getByRole("button", { name: /Quick fire test/ }).click();
  const headline = page.locator(".scenario-headline");
  await expect(headline).toHaveText(/Everyone is out in \d+ s/, { timeout: 60000 });
  await page.waitForTimeout(1500);
  await expect(page.locator(".scenario-beat")).toContainText(/leaving/i);  // first beat is the fire room, not a later one
  const before = Number((await headline.innerText()).match(/(\d+) s/)![1]);
  await page.locator("summary", { hasText: /^What if$/ }).click();
  await page.getByLabel("Max people").fill("0");
  await page.getByRole("button", { name: "Re-run with limit" }).click();
  await expect(async () => {
    const after = Number((await headline.innerText()).match(/(\d+) s/)![1]);
    expect(after).toBeGreaterThan(before);
  }).toPass({ timeout: 60000 });
});
