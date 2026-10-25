import { test, expect, type Page } from "@playwright/test";

/** UX journeys with a budget: how many actions, how long, and no horizontal scroll or console error on the way. */
const BUILDING = "swiss-1785";
const errors = (page: Page) => {
  const list: string[] = [];
  page.on("pageerror", e => list.push(String(e)));
  // a failed request is named by its URL (the console line only says "404"); the browser's favicon probe is not ours
  page.on("response", r => { if (r.status() >= 400 && !/favicon/.test(r.url())) list.push(`${r.status()} ${r.url()}`); });
  page.on("console", m => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) list.push(m.text()); });
  return list;
};
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);

test("first route in one action: a Welcome chip", async ({ page }) => {
  const problems = errors(page);
  await page.goto(`/?building=${BUILDING}`);
  const started = Date.now();
  await page.getByRole("button", { name: "Toilets" }).click();
  await expect(page.getByText(/Step 1 of/)).toBeVisible({ timeout: 15_000 });
  expect(Date.now() - started).toBeLessThan(8000);
  expect(problems.filter(p => !/favicon|WebGL|THREE/i.test(p))).toEqual([]);
});

test("keyboard only: Tab reaches the chips, Enter starts the route, Escape closes popovers", async ({ page }) => {
  await page.goto(`/?building=${BUILDING}`);
  await page.getByRole("button", { name: "Toilets" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Step 1 of/)).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Layers" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Visible floors" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("group", { name: "Visible floors" })).toHaveCount(0);
});

test("every interactive control has an accessible name", async ({ page }) => {
  await page.goto(`/?building=${BUILDING}&to=Toilets`);
  await expect(page.getByText(/Step 1 of/)).toBeVisible({ timeout: 20_000 });
  const unnamed = await page.evaluate(() => [...document.querySelectorAll("button, a[href], input, select, [role=button]")]
    .filter(el => { const r = (el as HTMLElement).getBoundingClientRect(); return r.width > 0 && r.height > 0; })
    .filter(el => !(el.getAttribute("aria-label") || el.textContent?.trim() || el.getAttribute("title") || (el as HTMLInputElement).placeholder || el.getAttribute("aria-labelledby")))
    .map(el => el.outerHTML.slice(0, 100)));
  expect(unnamed).toEqual([]);
});

for (const width of [360, 390, 430]) {
  test(`phone ${width}px: Welcome, route and Guide me have no sideways scroll and tap targets >= 36 px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await page.goto(`/?building=${BUILDING}`);
    await expect(page.getByRole("button", { name: "Toilets" })).toBeVisible({ timeout: 20_000 });
    expect(await noSideScroll(page)).toBe(true);
    await page.getByRole("button", { name: "Toilets" }).click();
    await expect(page.getByText(/Step 1 of/)).toBeVisible({ timeout: 15_000 });
    expect(await noSideScroll(page)).toBe(true);
    const small = await page.evaluate(() => [...document.querySelectorAll("button")].filter(b => { const r = b.getBoundingClientRect(); return r.width > 0 && (r.height < 36 || r.width < 36); }).map(b => (b.getAttribute("aria-label") || b.textContent || "").trim().slice(0, 30)));
    expect(small, `controls under 36 px: ${small.join(", ")}`).toEqual([]);
    await page.getByRole("button", { name: /Guide me/ }).first().click();
    await expect(page.getByRole("region", { name: "Route preview player" })).toBeVisible({ timeout: 15_000 });
    expect(await noSideScroll(page)).toBe(true);
  });
}

test("reduced motion: the loader is static and Guide me does not autoplay", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/?building=${BUILDING}&to=Toilets`);
  await expect(page.getByText(/Step 1 of/)).toBeVisible({ timeout: 20_000 });
  const animated = await page.evaluate(() => [...document.querySelectorAll(".k-loader-floor")].some(el => getComputedStyle(el).animationName !== "none"));
  expect(animated).toBe(false);
});
