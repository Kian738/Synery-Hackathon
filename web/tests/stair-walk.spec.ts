import { expect, test } from "@playwright/test";

// Some supplied connectors join stair spaces that are metres apart on the plan. The first-person camera must not glide
// across the rooms between them: it climbs in place in each shaft and cuts once, and never crosses a wall.
const ROUTES = [
  { building: "swiss-1689", from: "swiss-1689-F2-S038", to: "swiss-1689-F1-S014" },
  { building: "swiss-1785", from: "swiss-1785-F1-S003", to: "swiss-1785-F2-S015" },
];

function crosses(a: number[], b: number[], c: number[], d: number[]) {
  const o = (p: number[], q: number[], r: number[]) => (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
  return o(a, b, c) * o(a, b, d) < 0 && o(c, d, a) * o(c, d, b) < 0;
}

for (const route of ROUTES) {
  test(`Guide me climbs ${route.building} stairs without crossing walls or gliding between far-apart stops`, async ({ page }, info) => {
    test.skip(info.project.name === "phone", "desktop guide control");
    test.setTimeout(150_000);
    let walls: { floor_id: string; a: number[]; b: number[] }[] = [];
    page.on("response", async r => {
      if (!r.url().includes("/api/") || !(r.headers()["content-type"] ?? "").includes("json")) return;
      try { const j = await r.json(); if (j?.scene?.walls?.length) walls = j.scene.walls; } catch { /* not a geometry payload */ }
    });
    await page.goto(`/?building=${route.building}&at=${route.from}&to=${route.to}`);
    await page.getByRole("button", { name: "Guide me step by step" }).click();
    const slider = page.getByRole("slider", { name: "Preview progress" });
    await expect(slider).toBeAttached({ timeout: 30_000 });
    const canvas = page.locator("canvas").first();
    const samples: { x: number; y: number; h: number; floor: string }[] = [];
    const N = 160;
    for (let i = 0; i <= N; i++) {
      await slider.evaluate((el: HTMLInputElement, f: number) => {
        const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
        set.call(el, String(f * Number(el.max)));
        el.dispatchEvent(new Event("input", { bubbles: true }));
      }, i / N);
      await page.waitForTimeout(60);
      const pos = JSON.parse((await canvas.getAttribute("data-camera-position")) ?? "null");
      const floor = (await canvas.getAttribute("data-camera-floor")) ?? "";
      if (pos) samples.push({ x: pos[0], y: -pos[2], h: pos[1], floor });
    }
    expect(walls.length).toBeGreaterThan(0);
    expect(samples.length).toBeGreaterThan(N / 2);
    let cuts = 0, crossings = 0;
    for (let i = 1; i < samples.length; i++) {
      const p = samples[i - 1], q = samples[i];
      const step = Math.hypot(q.x - p.x, q.y - p.y);
      if (step > 3) { cuts++; continue; }  // the one deliberate cut between two far-apart stair stops
      for (const w of walls) if (w.floor_id === q.floor && w.floor_id === p.floor && crosses([p.x, p.y], [q.x, q.y], w.a, w.b)) { crossings++; break; }
    }
    expect(crossings).toBe(0);
    expect(cuts).toBeLessThanOrEqual(2);
  });
}
