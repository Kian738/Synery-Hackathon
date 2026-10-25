import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";

/** axe-core on the screens a person meets. Serious and critical violations fail the test; the list is printed so each can be fixed or
 *  consciously waived below with the reason. The 3D canvas itself is excluded (it is a picture; every action in it has a named control). */
const WAIVED: Record<string, string> = {
  // "rule-id": "why this is acceptable"
};

async function violations(page: Page) {
  const result = await new AxeBuilder({ page }).exclude("canvas").withTags(["wcag2a", "wcag2aa"]).analyze();
  return result.violations.filter(v => ["serious", "critical"].includes(v.impact ?? "") && !(v.id in WAIVED))
    .map(v => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.slice(0, 3).map(n => n.target.join(" ")).join(" | ")}`);
}

test("Welcome screen has no serious accessibility violations", async ({ page }) => {
  await page.goto("/?building=swiss-1785");
  await expect(page.getByRole("button", { name: "Toilets" })).toBeVisible({ timeout: 25_000 });
  expect(await violations(page)).toEqual([]);
});

test("route card and step list have no serious accessibility violations", async ({ page }) => {
  await page.goto("/?building=swiss-1785&to=Toilets");
  await expect(page.getByText(/Step 1 of/)).toBeVisible({ timeout: 25_000 });
  expect(await violations(page)).toEqual([]);
});

test("Guide me card has no serious accessibility violations", async ({ page }) => {
  await page.goto("/?building=swiss-1785&to=Toilets");
  await expect(page.getByText(/Step 1 of/)).toBeVisible({ timeout: 25_000 });
  await page.getByRole("button", { name: /Guide me/ }).first().click();
  await expect(page.getByRole("region", { name: "Route preview player" })).toBeVisible({ timeout: 15_000 });
  expect(await violations(page)).toEqual([]);
});

test("atlas and layers popover have no serious accessibility violations", async ({ page }) => {
  await page.goto("/?building=swiss-1785");
  await page.getByRole("button", { name: "Layers" }).click();
  expect(await violations(page)).toEqual([]);
});
