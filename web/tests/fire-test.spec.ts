import { expect, test } from "@playwright/test";

test("one click on Fire test runs the evacuation scenario and the replay starts", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "desktop analysis view");
  test.setTimeout(120_000);
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByRole("button", { name: /Fire test/ }).click();
  await expect(page.getByText(/Everyone is out in \d+ s|of \d+ people get out/).first()).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(/\d+ of \d+ out/).first()).toBeVisible();
});

test("the live line shows real reasoning steps while the scenario runs, then the headline replaces it", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "desktop analysis view");
  test.setTimeout(120_000);
  await page.goto("/?building=proc-campus-dev-000");
  await page.addInitScript(() => {
    (window as any).__live = new Set<string>();
    new MutationObserver(() => document.querySelectorAll('[aria-live="polite"] .k-hint').forEach(n => (window as any).__live.add(n.textContent ?? ""))).observe(document, { subtree: true, childList: true, characterData: true });
  });
  await page.reload();
  await page.getByRole("button", { name: /Fire test/ }).click();
  await expect(page.getByText(/Everyone is out in \d+ s|of \d+ people get out/).first()).toBeVisible({ timeout: 90_000 });
  const seen: string[] = await page.evaluate(() => [...(window as any).__live]);
  expect(seen.some(t => /people placed|usable exits|people out in|doors limit/.test(t))).toBe(true);
});
