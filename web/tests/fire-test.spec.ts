import { expect, test } from "@playwright/test";

test("one click on Fire test runs the evacuation scenario and the replay starts", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "desktop analysis view");
  test.setTimeout(120_000);
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByRole("button", { name: /Fire test/ }).click();
  await expect(page.getByText(/Everyone is out in \d+ s|of \d+ people get out/).first()).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(/\d+ of \d+ out/).first()).toBeVisible();
});
