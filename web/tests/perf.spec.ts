import { test, expect } from "@playwright/test";

/** Budgets for the biggest building (CIT, five floors, ~100k furniture parts). They protect laptops and phones: a change that
 *  brings back heavy far-away geometry fails here before anyone sees a stutter. Triangles are the cost driver, not draw calls. */
const read = (page: import("@playwright/test").Page) => page.evaluate(() => {
  const c = document.querySelector("canvas")!.dataset;
  return { calls: Number(c.perfCalls), triangles: Number(c.perfTriangles) };
});

test("the big building stays within its triangle and draw-call budget in every view", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/?building=osm-way27917482");
  await expect(page.locator("canvas")).toHaveAttribute("data-perf-calls", /\d+/, { timeout: 30_000 });
  await page.waitForTimeout(3000);
  const overview = await read(page);
  expect(overview.triangles).toBeLessThan(600_000);
  await page.getByRole("button", { name: "Layers" }).click();
  await page.getByRole("group", { name: "Visible floors" }).getByRole("button", { name: "Building" }).click();
  await page.waitForTimeout(4000);
  const whole = await read(page);
  expect(whole.triangles).toBeLessThan(1_200_000);
  expect(whole.calls).toBeLessThan(400);
  for (let i = 0; i < 8; i++) { await page.getByRole("button", { name: "Zoom in" }).click(); await page.waitForTimeout(120); }
  await page.waitForTimeout(2500);
  const close = await read(page);
  expect(close.triangles).toBeLessThan(8_000_000);
  expect(close.calls).toBeLessThan(400);
});

test("building geometry is served compressed", async ({ request }) => {
  const res = await request.get("/api/buildings/osm-way27917482", { headers: { "accept-encoding": "gzip" } });
  expect(res.ok()).toBe(true);
  expect(res.headers()["content-encoding"]).toBe("gzip");
});
