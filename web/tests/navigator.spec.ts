import { expect, test } from "@playwright/test";

const FACTORY = "/?building=proc-factory-dev-003";

test("welcome shows categories that exist in this building", async ({ page }) => {
  await page.goto(FACTORY);
  await expect(page.getByRole("heading", { name: /where do you/i })).toBeVisible();
  await expect(page.getByRole("button", { name: "Coffee" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Toilets" }).first()).toBeVisible();
});

test("category without a start point asks where you are instead of guessing", async ({ page }) => {
  await page.goto(FACTORY);
  await page.getByRole("button", { name: "Coffee" }).first().click();
  await expect(page.getByRole("status")).toContainText(/where are you/i);
});

test("deep link draws a route with followable steps", async ({ page }) => {
  await page.goto(`${FACTORY}&at=proc-factory-dev-003-F0-S021&to=Meeting%20room%201.10`);
  const route = page.getByRole("region", { name: "Route" });
  await expect(route).toContainText("Meeting room 1.10");
  await expect(route.getByRole("listitem")).not.toHaveCount(0);
  await expect(route).toContainText(/floor change/);
});

test("nearest-match routing from a set location (no LLM)", async ({ page }) => {
  await page.goto(`${FACTORY}&at=proc-factory-dev-003-F0-S021`);
  await page.getByRole("button", { name: "Toilets" }).first().click();
  await expect(page.getByRole("region", { name: "Route" })).toContainText(/Toilet/);
});

test("step-by-step mode moves through steps", async ({ page }) => {
  await page.goto(`${FACTORY}&at=proc-factory-dev-003-F0-S021&to=Meeting%20room%201.10`);
  await page.getByRole("button", { name: "Start step by step" }).click();
  const dialog = page.getByRole("dialog", { name: "Step by step" });
  await expect(dialog).toContainText("Step 1");
  await dialog.getByRole("button", { name: "Next" }).click();
  await expect(dialog).toContainText("Step 2");
});

test("step-free toggle is announced as pressed", async ({ page }) => {
  await page.goto(FACTORY);
  const toggle = page.getByRole("button", { name: "Step-free" });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
});
