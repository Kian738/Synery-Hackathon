import { expect, test } from "@playwright/test";

test("the fire scenario states one headline, collapses 9 steps and lists them on request", async ({ page }) => {
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByRole("button", { name: "Fire / evacuation scenario" }).click();
  await page.getByRole("textbox", { name: "Search rooms" }).fill("Canteen 0.28");
  await page.getByRole("button", { name: "Canteen 0.28", exact: true }).click();
  await page.getByRole("button", { name: "Run scenario" }).click();
  await expect(page.getByText(/Everyone is out in \d+ s/)).toBeVisible({ timeout: 60000 });
  const steps = page.getByText("9 steps checked");
  await expect(steps).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: /hazard/i }).first()).toBeHidden();
  await steps.click();
  await expect(page.getByRole("listitem").filter({ hasText: /hazard/i }).first()).toBeVisible();
});
