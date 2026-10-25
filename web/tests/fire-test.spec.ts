import { expect, test } from "@playwright/test";

test("one click on Fire test runs the evacuation scenario and the replay starts", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "desktop analysis view");
  test.setTimeout(120_000);
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByLabel("Building tools", { exact: true }).click();
  await page.getByRole("button", { name: "Scenarios", exact: true }).click();
  await page.getByRole("button", { name: /Quick fire test/ }).click();
  await expect(page.getByText(/Everyone is out in \d+ s|of \d+ people get out/).first()).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(/\d+ of \d+ out/).first()).toBeVisible();
});

test("on a phone the scenario sheet sits fully inside the viewport and the replay controls are reachable", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "phone layout");
  test.setTimeout(120_000);
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByLabel("Building tools", { exact: true }).click();
  await page.getByRole("button", { name: "Scenarios", exact: true }).click();
  await page.getByRole("button", { name: /Quick fire test/ }).click();
  await expect(page.locator(".scenario-headline")).toBeVisible({ timeout: 90_000 });
  const box = (await page.locator(".k-sheet.scenario").boundingBox())!;
  const vp = page.viewportSize()!;
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(vp.height + 1);
  expect(box.height).toBeGreaterThan(300); // not squeezed into the short stage
  await expect(page.getByRole("slider", { name: "Replay time" })).toBeInViewport();
  await expect(page.getByRole("button", { name: /^(Play|Pause)$/ })).toBeInViewport();
});

test("the fire test shows no Run demo state", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "desktop analysis view");
  await page.goto("/?building=proc-campus-dev-000");
  await page.getByLabel("Building tools", { exact: true }).click();
  await page.getByRole("button", { name: "Scenarios", exact: true }).click();
  const sheet = page.locator(".k-sheet.scenario");
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText(/Prepared scenario|Run demo/)).toHaveCount(0);
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
  await page.getByLabel("Building tools", { exact: true }).click();
  await page.getByRole("button", { name: "Scenarios", exact: true }).click();
  await page.getByRole("button", { name: /Quick fire test/ }).click();
  await expect(page.getByText(/Everyone is out in \d+ s|of \d+ people get out/).first()).toBeVisible({ timeout: 90_000 });
  const seen: string[] = await page.evaluate(() => [...(window as any).__live]);
  expect(seen.some(t => /people placed|usable exits|people out in|doors limit/.test(t))).toBe(true);
});
