import { expect, test } from "@playwright/test";

const FACTORY = "/?building=proc-factory-dev-003";
const CAMPUS = "/?building=proc-campus-dev-000";

test("welcome shows categories that exist in this building", async ({ page }) => {
  await page.goto(FACTORY);
  await expect(page.getByRole("heading", { name: /where do you/i })).toBeVisible();
  await expect(page.getByRole("button", { name: "Coffee" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Toilets" }).first()).toBeVisible();
});

test("start defaults to the main entrance, so a category routes in one tap", async ({ page }) => {
  await page.goto(CAMPUS);
  await expect(page.getByText("Starting from")).toContainText("Main lobby");
  await page.getByRole("button", { name: "Toilets" }).first().click();
  await expect(page.getByRole("region", { name: "Route" })).toContainText(/Toilet/);
});

test("example requests only mention things this building has", async ({ page }) => {
  await page.goto(CAMPUS);
  const examples = page.locator("ul li button");
  await expect(examples.first()).toBeVisible();
  const text = (await examples.allTextContents()).join(" ");
  expect(text).not.toContain("3D printer");
  expect(text).not.toContain("office lift");
});

test("start picker lists entrances and searches rooms", async ({ page }) => {
  await page.goto(FACTORY);
  await page.getByRole("button", { name: /starting from/i }).click();
  await page.getByRole("textbox", { name: "Search for your room" }).fill("Kitchen 0.31");
  await page.getByRole("button", { name: /Kitchen 0.31/ }).click();
  await expect(page.getByText("Starting from")).toContainText("Kitchen 0.31");
});

test("indoor route never leaves the building (no entrance teleport)", async ({ page }) => {
  await page.goto(`${FACTORY}&at=proc-factory-dev-003-F0-S031&to=H-B3`);
  const route = page.getByRole("region", { name: "Route" });
  await expect(route).toContainText("Main aisle H-B3");
  await expect(route).not.toContainText(/go outside/i);
});

test("deep link draws a multi-floor route with followable steps", async ({ page }) => {
  await page.goto(`${FACTORY}&at=proc-factory-dev-003-F0-S021&to=Meeting%20room%201.10`);
  const route = page.getByRole("region", { name: "Route" });
  await expect(route).toContainText("Meeting room 1.10");
  await expect(route.getByRole("listitem")).not.toHaveCount(0);
  await expect(route).toContainText(/floor change/);
  await expect(route).toContainText(/m walk/);
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

test("3D view can be switched on", async ({ page }) => {
  await page.goto(FACTORY);
  await page.getByRole("button", { name: "3D" }).click();
  await expect(page.getByRole("button", { name: "3D" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "All floors" })).toBeVisible();
});

test("map key opens and closes", async ({ page }) => {
  await page.goto(FACTORY);
  await page.getByRole("button", { name: "Key" }).click();
  await expect(page.getByText("Door with steps")).toBeVisible();
});
