import type { Geometry, Route, XY } from "./types";

/** Focus + context (docs/UI_RESEARCH.md §1): the rooms a person needs to read a route, and nothing else. */
const CONTEXT_M = 5;

/** The route's own rooms, the stops, anything highlighted, and rooms whose door lies within CONTEXT_M of the walked line.
 *  Null means "draw everything" (no route, or focus switched off). */
export function relevantSpaces(
  geometry: Pick<Geometry, "openings" | "connectors">,
  route: Route | null | undefined,
  extra: Iterable<string> = [],
): Set<string> | null {
  if (!route) return null;
  const keep = new Set<string>([...route.polyline.map(p => p.node), ...route.stops, ...extra]);
  const line = route.polyline.filter((_, i) => i % 2 === 0 || i === route.polyline.length - 1);
  for (const o of geometry.openings) {
    if (line.some(p => p.floor_id === o.floor_id && Math.hypot(p.x - o.position[0], p.y - o.position[1]) < CONTEXT_M)) o.space_ids.forEach(id => keep.add(id));
  }
  for (const c of geometry.connectors) if (c.space_ids.some(id => keep.has(id))) c.space_ids.forEach(id => keep.add(id));
  return keep;
}

/** Stair and lift spaces above their lowest stop: the shaft is open there, so no floor plate is drawn. */
export function shaftVoids(geometry: Pick<Geometry, "floors" | "spaces" | "connectors">): Set<string> {
  const out = new Set<string>();
  const level = new Map(geometry.floors.map(f => [f.id, f.level]));
  const floorOf = new Map(geometry.spaces.map(s => [s.id, s.floor_id]));
  const core = new Set(geometry.spaces.filter(s => /stair|lift/.test((s as { type?: string }).type ?? "stair")).map(s => s.id));
  for (const c of geometry.connectors) {
    const at = (id: string) => level.get(floorOf.get(id) ?? "") ?? 0;
    const lowest = Math.min(...c.space_ids.map(at));
    for (const id of c.space_ids) if (core.has(id) && at(id) > lowest) out.add(id);
  }
  return out;
}

export const CAMERA_RADIUS_M = 0.45;

/** Slide a first-person camera position off any wall closer than CAMERA_RADIUS_M, along the wall normal. */
export function clearOfWalls(x: number, y: number, walls: { a: XY; b: XY }[], radius = CAMERA_RADIUS_M): [number, number] {
  for (let pass = 0; pass < 2; pass++) {
    for (const w of walls) {
      const dx = w.b[0] - w.a[0], dy = w.b[1] - w.a[1], len2 = dx * dx + dy * dy;
      if (len2 < 1e-9) continue;
      const t = Math.max(0, Math.min(1, ((x - w.a[0]) * dx + (y - w.a[1]) * dy) / len2));
      const cx = w.a[0] + dx * t, cy = w.a[1] + dy * t, d = Math.hypot(x - cx, y - cy);
      if (d < radius && d > 1e-6) { x += (x - cx) / d * (radius - d); y += (y - cy) / d * (radius - d); }
    }
  }
  return [x, y];
}

/** Smoothstep along a connector ride: the camera eases in and out while it climbs. */
export const ease = (t: number) => t * t * (3 - 2 * t);

interface PathPoint { x: number; y: number; floor_id: string; node: string; gap?: boolean }

/** A separate path for the Guide me camera: the same journey as the drawn route, but resampled every 0.4 m, nudged to the middle of
 *  corridors and doorways, smoothed, and never closer than CAMERA_RADIUS_M to a wall. The drawn route stays the shortest one. */
export function cameraPolyline<T extends PathPoint>(polyline: T[], walls: { floor_id: string; a: XY; b: XY }[]): T[] {
  const byFloor = new Map<string, { a: XY; b: XY }[]>();
  for (const w of walls) byFloor.set(w.floor_id, [...(byFloor.get(w.floor_id) ?? []), w]);
  const out: T[] = [];
  let run: T[] = [];
  const flush = () => {
    if (run.length < 3) { out.push(...run); run = []; return; }
    const local = byFloor.get(run[0].floor_id) ?? [];
    // resample
    let pts: { x: number; y: number; src: T }[] = [];
    for (let i = 0; i < run.length - 1; i++) {
      const a = run[i], b = run[i + 1], n = Math.max(1, Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / 0.4));
      for (let k = 0; k < n; k++) pts.push({ x: a.x + ((b.x - a.x) * k) / n, y: a.y + ((b.y - a.y) * k) / n, src: k * 2 < n ? a : b });
    }
    pts.push({ x: run[run.length - 1].x, y: run[run.length - 1].y, src: run[run.length - 1] });
    const origin = pts.map(p => ({ x: p.x, y: p.y }));
    for (let it = 0; it < 8; it++) {
      for (let i = 1; i < pts.length - 1; i++) {
        let best = 1.3, nx = 0, ny = 0;
        for (const w of local) {
          const dx = w.b[0] - w.a[0], dy = w.b[1] - w.a[1], len2 = dx * dx + dy * dy;
          if (len2 < 1e-9) continue;
          const t = Math.max(0, Math.min(1, ((pts[i].x - w.a[0]) * dx + (pts[i].y - w.a[1]) * dy) / len2));
          const cx = w.a[0] + dx * t, cy = w.a[1] + dy * t, d = Math.hypot(pts[i].x - cx, pts[i].y - cy);
          if (d < best && d > 1e-6) { best = d; nx = (pts[i].x - cx) / d; ny = (pts[i].y - cy) / d; }
        }
        if (best < 1.3) {
          const push = Math.min(0.12, (1.3 - best) * 0.25);
          const x = pts[i].x + nx * push, y = pts[i].y + ny * push;
          if (Math.hypot(x - origin[i].x, y - origin[i].y) <= 0.9) { pts[i].x = x; pts[i].y = y; }
        }
      }
      // smooth: average with neighbours
      pts = pts.map((p, i) => (i === 0 || i === pts.length - 1) ? p : { ...p, x: (pts[i - 1].x + 2 * p.x + pts[i + 1].x) / 4, y: (pts[i - 1].y + 2 * p.y + pts[i + 1].y) / 4 });
    }
    for (const p of pts) { const [x, y] = clearOfWalls(p.x, p.y, local); out.push({ ...p.src, x, y } as T); }
    run = [];
  };
  for (const p of polyline) {
    if (run.length && (p.floor_id !== run[0].floor_id || p.gap)) flush();
    run.push(p);
  }
  flush();
  return out;
}
