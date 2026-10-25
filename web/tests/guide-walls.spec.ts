import { test, expect } from "@playwright/test";
import { cameraPath, type Door } from "../src/lib/cameraPath";
import { openingFrame } from "../src/lib/openings";

/** Guide me never walks through walls: for several buildings and routes, build the camera path exactly as RouteCamera does
 *  (cameraPath over the route polyline, scene walls, door frames) and walk it every 5 cm on each floor. Count samples closer than
 *  0.15 m to a wall and steps that cross a wall. Scene walls are already split at door gaps, so a doorway is not a wall. */
const BUILDINGS = ["swiss-1785", "osm-way27917482", "osm-way360544293", "osm-way58216509", "osm-way61408163",
  "proc-factory-dev-003", "proc-campus-dev-000", "resplan-14509"];
const ROUTES = 6, NEAR_M = 0.15;

type W = { floor_id: string; a: number[]; b: number[] };
const dist = (w: W, x: number, y: number) => {
  const dx = w.b[0] - w.a[0], dy = w.b[1] - w.a[1], l2 = dx * dx + dy * dy;
  const t = l2 < 1e-9 ? 0 : Math.max(0, Math.min(1, ((x - w.a[0]) * dx + (y - w.a[1]) * dy) / l2));
  return Math.hypot(x - w.a[0] - t * dx, y - w.a[1] - t * dy);
};
const cross = (p: number[], q: number[], w: W) => {
  const o = (a: number[], b: number[], c: number[]) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  const d1 = o(w.a, w.b, p), d2 = o(w.a, w.b, q), d3 = o(p, q, w.a), d4 = o(p, q, w.b);
  return d1 * d2 < -1e-9 && d3 * d4 < -1e-9;
};

export async function measure(request: any, building: string) {
  const session = (await (await request.post("/api/sessions", { data: { building_id: building } })).json()).session_id;
  const g = await (await request.get(`/api/sessions/${session}/scene`)).json();
  const walls: W[] = g.scene.walls;
  const doors: Door[] = g.openings.filter((o: any) => ["door", "opening", "entrance"].includes(o.kind)).flatMap((o: any) => {
    const f = openingFrame(g, o); return f ? [{ ids: o.space_ids, x: o.position[0], y: o.position[1], nx: -Math.sin(f.angle), ny: Math.cos(f.angle) }] : [];
  });
  const rooms = g.spaces.filter((s: any) => !/stair|lift|elevator|shaft/i.test(`${s.type} ${s.room_type ?? ""}`));
  let samples = 0, near = 0, crossings = 0, routes = 0;
  const worst: string[] = [];
  for (let k = 0; k < ROUTES * 3 && routes < ROUTES; k++) {
    const a = rooms[(k * 7) % rooms.length], b = rooms[(k * 13 + Math.floor(rooms.length / 2)) % rooms.length];
    if (!a || !b || a.id === b.id) continue;
    const r = await (await request.post(`/api/sessions/${session}/route`, { data: { start: a.id, destination: b.id, step_free: false } })).json();
    const poly = r.events?.find((e: any) => e.type === "route")?.route?.polyline;
    if (!poly?.length) continue;
    routes++;
    const path = cameraPath(poly, walls, doors);
    for (let i = 1; i < path.length; i++) {
      const p = path[i - 1], q = path[i];
      if (q.gap || p.floor_id !== q.floor_id) continue;
      const own = walls.filter(w => w.floor_id === q.floor_id);
      if (own.some(w => cross([p.x, p.y], [q.x, q.y], w))) { crossings++; if (worst.length < 6) worst.push(`${building} ${a.id}->${b.id} crosses at ${q.x.toFixed(2)},${q.y.toFixed(2)}`); }
      const n = Math.max(1, Math.ceil(Math.hypot(q.x - p.x, q.y - p.y) / 0.05));
      for (let s = 0; s < n; s++) {
        const x = p.x + ((q.x - p.x) * s) / n, y = p.y + ((q.y - p.y) * s) / n;
        samples++;
        if (own.some(w => dist(w, x, y) < NEAR_M)) near++;
      }
    }
  }
  return { building, routes, samples, near, crossings, worst };
}

test("Guide me camera path keeps off and never crosses walls", async ({ request }) => {
  test.setTimeout(600_000);
  const rows = [];
  for (const b of BUILDINGS) rows.push(await measure(request, b));
  console.log(JSON.stringify(rows, null, 1));
  const total = rows.reduce((t, r) => ({ near: t.near + r.near, crossings: t.crossings + r.crossings, samples: t.samples + r.samples }), { near: 0, crossings: 0, samples: 0 });
  console.log("TOTAL", JSON.stringify(total));
  expect(rows.filter(r => r.routes > 0).length).toBeGreaterThanOrEqual(6);
  expect(total.crossings).toBeLessThanOrEqual(Number(process.env.GUIDE_WALL_CROSSINGS ?? 0));
  expect(total.near / total.samples).toBeLessThan(0.02);
});
