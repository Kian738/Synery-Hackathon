import { expect, test } from "@playwright/test";

// The two-minute demo path, end to end, with screenshots for review: test-results/demo-*.png
test.beforeEach(({}, info) => test.skip(info.project.name === "phone", "desktop analysis view"));

test("demo path: quick fire test, checked steps, apply the fix and see the new time", async ({ page }) => {
  test.setTimeout(180_000); // the N-1 check re-solves every exit-loss scenario, about 20 s
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByRole("button", { name: "Fire / evacuation scenario" }).click();
  await page.getByRole("button", { name: /Quick fire test/ }).click();
  const headline = page.locator(".scenario-headline");
  await expect(headline).toHaveText(/Everyone is out in \d+ s/, { timeout: 60000 });
  const before = Number((await headline.innerText()).match(/(\d+) s/)![1]);
  await page.screenshot({ path: "test-results/demo-1-result.png" });
  await page.getByText(/\d+ steps checked/).click();
  await page.screenshot({ path: "test-results/demo-2-steps.png" });
  await page.getByRole("button", { name: /Apply to model/ }).click();
  await expect(async () => {
    const after = Number((await headline.innerText()).match(/(\d+) s/)![1]);
    expect(after).toBeLessThan(before);
  }).toPass({ timeout: 60000 });
  await page.screenshot({ path: "test-results/demo-3-applied.png" });
  await page.getByRole("button", { name: "Check if an exit fails" }).click();
  await expect(page.getByText(/If one exit is lost, everyone is out in \d+ s/)).toBeVisible({ timeout: 90000 });
  await page.screenshot({ path: "test-results/demo-4-n-minus-one.png" });
});
