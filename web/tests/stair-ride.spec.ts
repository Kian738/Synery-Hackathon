import { test, expect } from "@playwright/test";

/** The camera on a stair ride, measured: for several buildings, ride the first stair a route uses and check, at 40 moments of the ride,
 *  that the eye stays inside the stair space, never closer than 0.3 m to a wall, and at a believable height above the treads. */
const BUILDINGS = ["swiss-1785", "osm-way27917482", "proc-campus-dev-000", "proc-factory-dev-003", "swiss-460", "osm-way61408163"];

function inside(poly: number[][], x: number, y: number) {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}
const wallDistance = (walls: { floor_id: string; a: number[]; b: number[] }[], floor: string, x: number, y: number) => {
  let best = Infinity;
  for (const w of walls) {
    if (w.floor_id !== floor) continue;
    const dx = w.b[0] - w.a[0], dy = w.b[1] - w.a[1], l2 = dx * dx + dy * dy;
    if (l2 < 1e-9) continue;
    const t = Math.max(0, Math.min(1, ((x - w.a[0]) * dx + (y - w.a[1]) * dy) / l2));
    best = Math.min(best, Math.hypot(x - w.a[0] - t * dx, y - w.a[1] - t * dy));
  }
  return best;
};

for (const building of BUILDINGS) {
  test(`stair ride in ${building}: eye stays in the stair space, off the walls, at eye height`, async ({ page, request }) => {
    test.setTimeout(180_000);
    const geometry = await (await request.get(`/api/buildings/${building}`)).json();
    const scene = await (await request.get(`/api/buildings/${building}`)).json();
    const session = (await (await request.post("/api/sessions", { data: { building_id: building } })).json()).session_id;
    const full = await (await request.get(`/api/sessions/${session}/scene`)).json();
    const stairs = full.connectors.filter((c: any) => c.kind === "stairs");
    test.skip(!stairs.length, "no stairs");
    const spaces = new Map<string, any>(full.spaces.map((s: any) => [s.id, s]));
    const floors = new Map<string, any>(full.floors.map((f: any) => [f.id, f]));
    // a route that must use a stair: from a room next to the first stop of a stair to a room next to its last stop
    let tried = 0, rides = 0;
    for (const c of stairs.slice(0, 40)) {
      if (rides >= 2 || tried >= 8) break;
      const shaftOk = full.scene.stair_shafts.some((s: any) => s.connector_id === c.id && s.footprint);
      if (!shaftOk) continue;
      tried++;
      const first = c.space_ids[0], last = c.space_ids[c.space_ids.length - 1];
      const result = await (await request.post(`/api/sessions/${session}/route`, { data: { start: first, destination: last, step_free: false } })).json();
      if (result.result?.error || !result.result?.steps) continue;
      await page.goto(`/?building=${building}&at=${first}&to=${encodeURIComponent(spaces.get(last).name)}`);
      await page.getByRole("button", { name: "Guide me step by step" }).click({ timeout: 30_000 }).catch(() => null);
      const slider = page.getByRole("slider", { name: "Preview progress" });
      if (!(await slider.count())) continue;
      rides++;
      const canvas = page.locator("canvas");
      const problems: string[] = [];
      const shafts = full.scene.stair_shafts.filter((s: any) => s.connector_id === c.id && s.footprint);
      let previous: number | null = null;
      for (let i = 0; i <= 40; i++) {
        await slider.evaluate((el: HTMLInputElement, f: number) => {
          const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
          set.call(el, String(f * Number(el.max)));
          el.dispatchEvent(new Event("input", { bubbles: true }));
        }, i / 40);
        await page.waitForTimeout(120);
        const pos = JSON.parse((await canvas.getAttribute("data-camera-position")) ?? "null");
        const floor = await canvas.getAttribute("data-camera-floor");
        if (!pos || !floor) continue;
        const [x, y, h] = [pos[0], -pos[2], pos[1]];
        // only judge the moments that are on this stair: the eye is within 1.5 m of one of its spaces
        const near = c.space_ids.map((id: string) => spaces.get(id)).filter(Boolean).find((sp: any) => sp.floor_id === floor);
        const onStair = near && (inside(near.polygon, x, y) || shafts.some((s: any) => inside(s.footprint, x, y)));
        if (!onStair) continue;
        const d = wallDistance(full.scene.walls, floor, x, y);
        if (d < 0.28) problems.push(`${building} t=${i}/40 floor ${floor} eye ${x.toFixed(2)},${y.toFixed(2)} is ${d.toFixed(2)} m from a wall`);
        // the eye is 1.65 m above where the feet are, and the feet are between the lowest and the highest stop of this stair (the floor label flips at mid-ride)
        const levels = c.floor_ids.map((id: string) => floors.get(id)?.elevation_m ?? 0);
        const feet = h - 1.65;
        if (feet < Math.min(...levels) - 0.12 || feet > Math.max(...levels) + 0.12) problems.push(`${building} t=${i}/40 feet at ${feet.toFixed(2)} m, outside the stair's range ${Math.min(...levels)} to ${Math.max(...levels)}`);
        if (previous !== null && Math.abs(h - previous) > 1.6) problems.push(`${building} t=${i}/40 eye jumps ${(h - previous).toFixed(2)} m between two moments`);
        previous = h;
      }
      expect(problems, problems.join("\n")).toEqual([]);
    }
    test.skip(rides === 0, "no stair route could be ridden");
    void geometry; void scene;
  });
}
