import { test, expect } from "@playwright/test";

test("opening a map shows the whole building; a route then focuses on the route; Find, Share and Save are gone", async ({ page }) => {
  await page.goto("/?building=swiss-1785");
  await page.getByRole("button", { name: "Layers" }).click();
  const group = page.getByRole("group", { name: "Visible floors" });
  await expect(group.getByRole("button", { name: "Whole building" })).toHaveAttribute("aria-pressed", "true", { timeout: 25_000 });
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Toilets" }).click();
  await expect(page.getByTestId("focus-toggle")).toContainText(/dimmed/, { timeout: 25_000 });
  await page.getByRole("button", { name: "Layers" }).click();
  await expect(group.getByRole("button", { name: /Route floors|This floor/ }).and(page.locator('[aria-pressed="true"]'))).toHaveCount(1);
  await expect(group.getByRole("button", { name: "Whole building" })).toHaveAttribute("aria-pressed", "false");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Building tools" }).click();
  await expect(page.getByRole("button", { name: /Find|share|save/i })).toHaveCount(0);
  await page.keyboard.press("Control+k");
  await expect(page.getByText("Find, remember, share")).toHaveCount(0);
});

test("a building opened from the atlas starts as the whole building even after a route elsewhere", async ({ page }) => {
  await page.goto("/?building=swiss-1785&to=Toilets");
  await expect(page.getByTestId("focus-toggle")).toContainText(/dimmed/, { timeout: 25_000 });
  await page.goto("/?building=proc-campus-test-013");
  await page.getByRole("button", { name: "Layers" }).click();
  await expect(page.getByRole("group", { name: "Visible floors" }).getByRole("button", { name: "Whole building" })).toHaveAttribute("aria-pressed", "true", { timeout: 25_000 });
});
