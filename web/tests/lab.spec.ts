import { expect, test } from "@playwright/test";

test("lab overview lists suites with scores", async ({ page }) => {
  await page.goto("/lab");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "e2e" }).first()).toBeVisible();
});

test("a run opens with drill-down", async ({ page }) => {
  await page.goto("/lab/runs");
  await page.getByRole("link").filter({ hasText: /ago/ }).first().click();
  await expect(page.getByText(/of \d+ items/)).toBeVisible();
  await page.locator("tbody tr").first().click();
  await expect(page.getByText(/Correct|Wrong|Unscored/).first()).toBeVisible();
});

test("dataset lists 280 buildings", async ({ page }) => {
  await page.goto("/lab/dataset");
  await expect(page.locator("tbody tr")).toHaveCount(280);
});
