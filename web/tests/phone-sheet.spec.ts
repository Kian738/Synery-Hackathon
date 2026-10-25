import { test, expect } from "@playwright/test";

/** Phone portrait: the sign column is a bottom sheet with three snap heights; the map stays above it.
 *  In Guide me the playbar and the loading pill keep the middle of the picture clear. */
test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

const ROUTE = "/?building=proc-factory-dev-003&at=proc-factory-dev-003-F0-S021&to=Meeting%20room%201.10";

test("bottom sheet snaps peek / half / full, map visible above, no sideways scroll", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto(ROUTE);
  await expect(page.getByRole("button", { name: "Guide me step by step" })).toBeVisible({ timeout: 30_000 });
  const panel = page.locator(".navigation-panel");
  const handle = page.locator(".k-sheet-handle");
  const box = async () => (await panel.boundingBox())!;
  await expect(handle).toBeVisible();
  const hb = (await handle.boundingBox())!;
  expect(hb.height).toBeGreaterThanOrEqual(40);
  // half
  let b = await box();
  expect(Math.abs(b.height - 422)).toBeLessThan(12);
  expect(b.y + b.height).toBeGreaterThan(840);
  const map = (await page.locator(".model-panel").boundingBox())!;
  expect(map.y).toBeLessThan(5);
  expect(map.height).toBeGreaterThan(400);
  await page.screenshot({ path: "test-results/phone-sheet-half.png" });
  // full
  await handle.press("ArrowUp");
  await page.waitForTimeout(400);
  b = await box();
  expect(b.height).toBeGreaterThan(740);
  await page.screenshot({ path: "test-results/phone-sheet-full.png" });
  // peek (two steps down)
  await handle.press("ArrowDown");
  await handle.press("ArrowDown");
  await page.waitForTimeout(400);
  b = await box();
  expect(Math.abs(b.height - 96)).toBeLessThan(8);
  await expect(page.locator(".navigation-panel form, .navigation-panel textarea").first()).toBeVisible();
  await page.screenshot({ path: "test-results/phone-sheet-peek.png" });
  // tap on the handle grows it again
  await handle.tap();
  await page.waitForTimeout(400);
  expect(Math.abs((await box()).height - 422)).toBeLessThan(12);
  const sideways = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(sideways).toBeLessThanOrEqual(0);
});

test("Guide me at 390: playbar and loading pill stay out of the middle band", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto(ROUTE);
  await page.getByRole("button", { name: "Guide me step by step" }).click({ timeout: 30_000 });
  const player = page.locator(".guide-player");
  await expect(player).toBeVisible();
  await page.waitForTimeout(600);
  await page.screenshot({ path: "test-results/phone-sheet-guide.png" });
  const p = (await player.boundingBox())!;
  expect(p.y).toBeGreaterThan(844 * 0.6);
  expect(p.x).toBeGreaterThanOrEqual(0);
  expect(p.x + p.width).toBeLessThanOrEqual(390);
  const pill = page.locator(".k-activity-pill");
  if (await pill.isVisible()) {
    const q = (await pill.boundingBox())!;
    expect(q.y + q.height).toBeLessThan(844 * 0.35);
    expect(q.y + q.height <= p.y).toBe(true);
  }
});
