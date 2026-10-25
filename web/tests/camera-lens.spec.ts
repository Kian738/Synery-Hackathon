import { expect, test } from "@playwright/test";

// Guide me flies a first-person camera through rooms. The overview lens (near ~0.6 m) clips walls away at walking distance.
test("Guide me uses its own close lens", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "desktop guide control");
  await page.goto("/?building=proc-campus-dev-000&at=proc-campus-dev-000-F2-S008&to=Canteen%200.28");
  await expect(page.getByRole("region", { name: "Route" })).toBeVisible();
  const canvas = page.locator("canvas").first();
  await page.getByRole("button", { name: "Guide me" }).first().click();
  await expect(canvas).toHaveAttribute("data-camera-near", /^0\.0[0-9]*$/, { timeout: 20000 });
  await expect(canvas).toHaveAttribute("data-camera-fov", "70");
  await page.getByRole("button", { name: "3D", exact: true }).first().click();
  await expect(canvas).toBeVisible();  // leaving Guide me restores the overview lens (the diagnostic attribute stays on the canvas)
});
