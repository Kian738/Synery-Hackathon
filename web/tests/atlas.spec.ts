import { test, expect } from "@playwright/test";

test("the Building Atlas shows thumbnails, filters, searches and opens a building by keyboard", async ({ page }) => {
  await page.goto("/?building=proc-factory-dev-003");
  await page.getByRole("button", { name: "Change building" }).click();
  const atlas = page.getByRole("dialog", { name: "Building atlas" });
  await expect(atlas).toBeVisible();
  const cards = atlas.getByRole("option");
  await expect(cards.first()).toContainText("open now"); // the current building is pinned first
  expect(await cards.count()).toBeGreaterThan(20);
  await expect.poll(async () => atlas.locator("img").first().evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await atlas.getByRole("button", { name: "Residential" }).click();
  const homes = await cards.count();
  expect(homes).toBeGreaterThan(0);
  expect(homes).toBeLessThan(await page.evaluate(() => 280));
  await atlas.getByRole("button", { name: "Residential" }).click();
  await atlas.getByLabel("Search buildings").fill("Hörsaalzentrum 024");
  await expect(cards.first()).toContainText("Hörsaalzentrum 024");
  await page.keyboard.press("Enter");
  await expect(atlas).toBeHidden();
  await expect(page).toHaveURL(/building=proc-campus-dev-000/);
});

test("the atlas closes with Escape and keeps the building", async ({ page }) => {
  await page.goto("/?building=proc-factory-dev-003");
  await page.getByRole("button", { name: "Change building" }).click();
  await expect(page.getByRole("dialog", { name: "Building atlas" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Building atlas" })).toBeHidden();
  await expect(page).toHaveURL(/proc-factory-dev-003/);
});
