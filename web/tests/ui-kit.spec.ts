import { test, expect } from "@playwright/test";
import fs from "node:fs";

test("every control on the 3D stage shares one height, radius and gap, and has a name", async ({ page }) => {
  await page.goto("/?building=osm-way27917482&to=Toilet");
  await expect(page.getByRole("button", { name: "Fit building" })).toBeVisible({ timeout: 20_000 });
  const report = await page.evaluate(() => {
    const ctl = [...document.querySelectorAll<HTMLElement>(".k-ctl")].filter(e => e.offsetParent);
    const docks = [...document.querySelectorAll<HTMLElement>(".k-dock")].filter(e => e.offsetParent);
    const gaps: number[] = [];
    for (const d of docks) {
      const kids = [...d.children].filter(c => (c as HTMLElement).offsetParent) as HTMLElement[];
      kids.slice(1).forEach((k, i) => { const a = kids[i].getBoundingClientRect(), b = k.getBoundingClientRect(); gaps.push(d.classList.contains("col") ? b.top - a.bottom : b.left - a.right); });
    }
    const boxes = ctl.map(e => e.getBoundingClientRect());
    let overlaps = 0;
    boxes.forEach((a, i) => boxes.slice(i + 1).forEach(b => { if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) overlaps++; }));
    return {
      heights: [...new Set(ctl.map(e => Math.round(e.getBoundingClientRect().height)))],
      radii: [...new Set(ctl.map(e => getComputedStyle(e).borderTopLeftRadius))],
      gaps: [...new Set(gaps.map(g => Math.round(g)))],
      unnamed: ctl.filter(e => !(e.getAttribute("aria-label") || e.textContent?.trim())).length,
      overlaps, count: ctl.length,
    };
  });
  expect(report.count).toBeGreaterThan(6);
  expect(report.heights).toEqual([40]);
  expect(report.radii).toEqual(["12px"]);
  expect(report.gaps).toEqual([8]);
  expect(report.unnamed).toBe(0);
  expect(report.overlaps).toBe(0);
});

test("floor rail is a compact strip that opens on hover and keeps route floors named", async ({ page }) => {
  await page.goto("/?building=proc-campus-test-013");
  const rail = page.getByRole("navigation", { name: "Floors" });
  await expect(rail).toBeVisible({ timeout: 20_000 });
  const collapsed = (await rail.boundingBox())!.width;
  expect(collapsed).toBeLessThan(90);
  const rows = rail.getByRole("button");
  const gap = await rows.evaluateAll(els => { const r = els.map(e => e.getBoundingClientRect()); return Math.round(r[1].top - r[0].bottom); });
  expect(gap).toBe(4);
  await rail.hover();
  await expect.poll(async () => (await rail.boundingBox())!.width).toBeGreaterThan(collapsed + 40);
});

test("no leftover private button styles for controls the kit replaced", () => {
  const css = fs.readFileSync("src/styles.css", "utf8");
  for (const dead of [".view-scope", ".focus-pill", ".closed-chip", ".building-tools"]) expect(css.includes(dead), dead).toBe(false);
});
