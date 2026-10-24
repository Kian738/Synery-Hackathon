import { expect, test } from "@playwright/test";

test("lab opens on the inspection sheet in plain words", async ({ page }) => {
  await page.goto("/lab");
  await expect(page.getByRole("heading", { name: /checks pass/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Benchmark answers" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run all free checks" })).toBeVisible();
});

test("a check links to its run and the drill-down shows an item", async ({ page }) => {
  await page.goto("/lab");
  await page.getByRole("link", { name: /Open run|See the/ }).first().click();
  await expect(page.getByText(/of \d+ items/)).toBeVisible();
  await page.locator("tbody tr").first().click();
  await expect(page.getByText(/Correct|Wrong|Unscored/).first()).toBeVisible();
});

test("history lists runs", async ({ page }) => {
  await page.goto("/lab/runs");
  await expect(page.locator("tbody tr").first()).toBeVisible();
});

test("dataset lists 280 buildings", async ({ page }) => {
  await page.goto("/lab/dataset");
  await expect(page.locator("tbody tr")).toHaveCount(280);
});
