import { test, expect } from "@playwright/test";
import { cameraPath } from "../src/lib/cameraPath";
import { openingFrame } from "../src/lib/openings";
import { inside } from "../src/components/Connectors3D";

const BUILDINGS = ["osm-way27917482", "proc-campus-test-013", "swiss-1785", "swiss-921", "proc-factory-dev-003", "proc-campus-dev-000"];

function rng(seed: number) { let s = seed; return () => (s = (s * 1664525 + 1013904223) % 4294967296) / 4294967296; }

test("camera paths over many routes stay inside their rooms and off the walls", async ({ page }) => {
  test.setTimeout(240_000);
  const stats: { points: number; outside: number; tooClose: number; routes: number; worst: number; crossings?: number } = { points: 0, outside: 0, tooClose: 0, routes: 0, worst: Infinity };
  for (const building of BUILDINGS) {
    const geometry = await (await page.request.get(`/api/buildings/${building}`)).json();
    const sid = (await (await page.request.post("/api/sessions", { data: { building_id: building } })).json()).session_id;
    const scene = await (await page.request.get(`/api/sessions/${sid}/scene`)).json();
    const walls = scene.scene.walls as { floor_id: string; a: number[]; b: number[] }[];
    const spaces = new Map<string, { polygon: number[][] }>(geometry.spaces.map((s: any) => [s.id, s]));
    const rooms = geometry.spaces.filter((s: any) => s.type === "room").map((s: any) => s.id);
    const doors = geometry.openings.filter((o: any) => ["door", "opening", "entrance"].includes(o.kind)).flatMap((o: any) => {
      const f = openingFrame(geometry, o);
      return f ? [{ ids: o.space_ids, x: o.position[0], y: o.position[1], nx: -Math.sin(f.angle), ny: Math.cos(f.angle) }] : [];
    });
    const rand = rng(building.length * 977);
    for (let n = 0; n < 8; n++) {
      const a = rooms[Math.floor(rand() * rooms.length)], b = rooms[Math.floor(rand() * rooms.length)];
      if (a === b) continue;
      const res = await page.request.post(`/api/sessions/${sid}/route`, { data: { start: a, destination: b } });
      if (!res.ok()) continue;
      const route = (await res.json()).events.find((e: any) => e.type === "route")?.route;
      if (!route?.polyline?.length) continue;
      stats.routes++;
      const path = cameraPath(route.polyline, walls, doors);
      const floorSpaces = (f: string) => geometry.spaces.filter((sp: any) => sp.floor_id === f);
      const cross = (a: number[], b: number[], c: number[], d: number[]) => {
        const o = (p: number[], q: number[], r: number[]) => (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
        return o(a, b, c) * o(a, b, d) < -1e-9 && o(c, d, a) * o(c, d, b) < -1e-9;
      };
      path.forEach((p, i) => {
        stats.points++;
        if (!floorSpaces(p.floor_id).some((sp: any) => inside(sp.polygon, p.x, p.y) || sp.polygon.some((q: number[]) => Math.hypot(q[0] - p.x, q[1] - p.y) < 0.05))) stats.outside++;
        const prev = path[i - 1];
        if (prev && prev.floor_id === p.floor_id) for (const w of walls) if (w.floor_id === p.floor_id && cross([prev.x, prev.y], [p.x, p.y], w.a, w.b)) { stats.crossings = (stats.crossings ?? 0) + 1; break; }
        let d = Infinity;
        for (const w of walls) {
          if (w.floor_id !== p.floor_id) continue;
          const dx = w.b[0] - w.a[0], dy = w.b[1] - w.a[1], l2 = dx * dx + dy * dy;
          if (l2 < 1e-9) continue;
          const t = Math.max(0, Math.min(1, ((p.x - w.a[0]) * dx + (p.y - w.a[1]) * dy) / l2));
          d = Math.min(d, Math.hypot(p.x - w.a[0] - dx * t, p.y - w.a[1] - dy * t));
        }
        if (d < 0.3) stats.tooClose++;
        stats.worst = Math.min(stats.worst, d);
      });
    }
  }
  console.log("CAMSTATS", JSON.stringify(stats));
  expect(stats.routes).toBeGreaterThan(20);
  expect(stats.tooClose / stats.points).toBeLessThan(0.002);
  expect(stats.outside / stats.points).toBeLessThan(0.005);
  expect(stats.crossings ?? 0).toBe(0);
});
