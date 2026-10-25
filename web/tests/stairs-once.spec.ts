import { expect, test } from "@playwright/test";

test("a multi-floor route lists the stairs once, not once per floor", async ({ page }) => {
  const building = "osm-way27917482";
  await page.goto(`/?building=${building}&at=${building}-F3-S069&to=00.05.058`);
  await expect(page.getByText(/Step 1 of/)).toBeVisible({ timeout: 25_000 });
  const stairSteps = page.getByText(/Take the (stairs|lift) (up|down)/);
  await expect(stairSteps.first()).toBeAttached();
  expect(await stairSteps.count()).toBeLessThanOrEqual(2);
});
