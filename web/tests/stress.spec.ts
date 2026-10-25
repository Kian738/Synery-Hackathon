import { test, expect } from "@playwright/test";

test("the evacuation test runs, shows times, queues and a time scrubber, and proves a new door with a second run", async ({ page }) => {
  await page.goto("/?building=proc-factory-dev-003");
  await page.getByRole("button", { name: "Building tools" }).click();
  await page.getByRole("button", { name: "Evacuation test" }).click();
  const panel = page.getByRole("region", { name: "Evacuation stress test" });
  await expect(panel.getByText("95 % out")).toBeVisible({ timeout: 30_000 });
  await expect(panel.getByText(/\d+ of \d+ people reach an exit/)).toBeVisible();
  await expect(panel.getByText("Where people queue")).toBeVisible();
  // the scrubber moves the heat map: the time label follows
  const slider = panel.getByRole("slider", { name: "Time into the evacuation" });
  await slider.evaluate((el: HTMLInputElement) => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!; set.call(el, "90"); el.dispatchEvent(new Event("input", { bubbles: true })); });
  await expect(panel.locator("output")).toHaveText("1:30");
  // a slower reaction cannot finish earlier
  const before = await panel.locator(".k-stress-kpis dd").nth(2).innerText();
  await panel.getByRole("button", { name: "Slow reaction" }).click();
  await expect(panel.getByRole("button", { name: "Slow reaction" })).toHaveAttribute("aria-pressed", "true");
  await expect.poll(async () => panel.locator(".k-stress-kpis dd").nth(2).innerText(), { timeout: 30_000 }).not.toBe(before);
  await panel.getByRole("button", { name: "Where should a new door go?" }).click();
  await expect(panel.locator(".k-stress-ideas li, .k-hint").first()).toBeVisible({ timeout: 60_000 });
  await panel.getByRole("button", { name: "Close stress test" }).click();
  await expect(panel).toHaveCount(0);
});

test("the evacuation test never offers to add a door that makes things worse", async ({ page }) => {
  await page.goto("/?building=osm-way61408163");
  await page.getByRole("button", { name: "Building tools" }).click();
  await page.getByRole("button", { name: "Evacuation test" }).click();
  const panel = page.getByRole("region", { name: "Evacuation stress test" });
  await panel.getByRole("button", { name: "Where should a new door go?" }).click({ timeout: 60_000 });
  const items = panel.locator(".k-stress-ideas li");
  await expect(items.first()).toBeVisible({ timeout: 90_000 });
  for (const li of await items.all()) {
    if ((await li.getAttribute("data-regress")) === "true") await expect(li.getByRole("button", { name: "Add this door" })).toHaveCount(0);
  }
});
