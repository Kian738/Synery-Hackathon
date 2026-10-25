import { CAMERA_RADIUS_M } from "./focus";
import type { XY } from "./types";

/** The Guide me camera path. It is NOT the drawn route: it follows the same journey but as a few long straight runs through the
 *  middle of corridors and doors, joined by rounded corners, so the picture never lurches left and right.
 *  Steps per floor run: resample, centre away from walls, pull the string straight (as far as clearance allows), round the corners. */

interface PathPoint { x: number; y: number; floor_id: string; node: string; gap?: boolean }
type Wall = { floor_id: string; a: XY; b: XY };
type Seg = { a: XY; b: XY };

const STEP_M = 0.25, CENTRE_M = 0.6, STRAIGHT_CLEARANCE_M = CAMERA_RADIUS_M + 0.03;

function distance(x: number, y: number, w: Seg): number {
  const dx = w.b[0] - w.a[0], dy = w.b[1] - w.a[1], len2 = dx * dx + dy * dy;
  if (len2 < 1e-9) return Math.hypot(x - w.a[0], y - w.a[1]);
  const t = Math.max(0, Math.min(1, ((x - w.a[0]) * dx + (y - w.a[1]) * dy) / len2));
  return Math.hypot(x - (w.a[0] + dx * t), y - (w.a[1] + dy * t));
}
const clearance = (x: number, y: number, walls: Seg[]) => walls.reduce((m, w) => Math.min(m, distance(x, y, w)), Infinity);

/** True when the straight segment keeps at least `min` metres from every wall. */
function straight(a: XY, b: XY, walls: Seg[], min: number): boolean {
  min = Math.min(min, clearance(a[0], a[1], walls) - 0.02, clearance(b[0], b[1], walls) - 0.02); // ends may sit near a wall (a door, a start point)
  const n = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 0.15));
  for (let i = 0; i <= n; i++) if (clearance(a[0] + ((b[0] - a[0]) * i) / n, a[1] + ((b[1] - a[1]) * i) / n, walls) < min) return false;
  return true;
}

function centre(pts: XY[], walls: Seg[]): XY[] {
  const out = pts.map(p => [...p] as XY);
  for (let it = 0; it < 6; it++) {
    for (let i = 1; i < out.length - 1; i++) {
      let best = CENTRE_M * 1.6, nx = 0, ny = 0;
      for (const w of walls) {
        const d = distance(out[i][0], out[i][1], w);
        if (d < best && d > 1e-6) {
          const dx = w.b[0] - w.a[0], dy = w.b[1] - w.a[1], len2 = dx * dx + dy * dy || 1;
          const t = Math.max(0, Math.min(1, ((out[i][0] - w.a[0]) * dx + (out[i][1] - w.a[1]) * dy) / len2));
          best = d; nx = (out[i][0] - (w.a[0] + dx * t)) / d; ny = (out[i][1] - (w.a[1] + dy * t)) / d;
        }
      }
      if (best < CENTRE_M * 1.6) {
        const x = out[i][0] + nx * Math.min(0.1, (CENTRE_M * 1.6 - best) * 0.3), y = out[i][1] + ny * Math.min(0.1, (CENTRE_M * 1.6 - best) * 0.3);
        if (Math.hypot(x - pts[i][0], y - pts[i][1]) <= 0.9) { out[i][0] = x; out[i][1] = y; }
      }
    }
  }
  return out;
}

/** Greedy string pulling: from each key point jump to the farthest later point that is reachable in a straight, clear line. */
export function pullStraight(pts: XY[], walls: Seg[], min = STRAIGHT_CLEARANCE_M): XY[] {
  const keys: XY[] = [pts[0]];
  let i = 0;
  while (i < pts.length - 1) {
    let j = pts.length - 1;
    while (j > i + 1 && !straight(pts[i], pts[j], walls, min)) j--;
    keys.push(pts[j]);
    i = j;
  }
  return keys;
}

/** Replace each interior corner by a quadratic arc, shrinking the radius until the arc is clear of the walls. */
export function roundCorners(keys: XY[], walls: Seg[], radius = 1.0): XY[] {
  if (keys.length < 3) return keys;
  const out: XY[] = [keys[0]];
  for (let k = 1; k < keys.length - 1; k++) {
    const p = keys[k - 1], c = keys[k], n = keys[k + 1];
    const l1 = Math.hypot(c[0] - p[0], c[1] - p[1]), l2 = Math.hypot(n[0] - c[0], n[1] - c[1]);
    let r = Math.min(radius, 0.45 * l1, 0.45 * l2), arc: XY[] | null = null;
    for (let tries = 0; tries < 4 && r > 0.05; tries++, r /= 2) {
      const a: XY = [c[0] + ((p[0] - c[0]) / l1) * r, c[1] + ((p[1] - c[1]) / l1) * r];
      const b: XY = [c[0] + ((n[0] - c[0]) / l2) * r, c[1] + ((n[1] - c[1]) / l2) * r];
      const sample: XY[] = Array.from({ length: 9 }, (_, i) => { const t = i / 8, u = 1 - t; return [u * u * a[0] + 2 * u * t * c[0] + t * t * b[0], u * u * a[1] + 2 * u * t * c[1] + t * t * b[1]] as XY; });
      if (sample.every(q => clearance(q[0], q[1], walls) >= CAMERA_RADIUS_M)) { arc = sample; break; }
    }
    out.push(...(arc ?? [c]));
  }
  out.push(keys[keys.length - 1]);
  return out;
}

function resample(pts: XY[]): XY[] {
  const out: XY[] = [pts[0]];
  for (let i = 1; i < pts.length; i++) {
    const a = out[out.length - 1], b = pts[i], d = Math.hypot(b[0] - a[0], b[1] - a[1]), n = Math.floor(d / STEP_M);
    for (let k = 1; k <= n; k++) out.push([a[0] + ((b[0] - a[0]) * k * STEP_M) / d, a[1] + ((b[1] - a[1]) * k * STEP_M) / d]);
    if (n * STEP_M < d - 1e-6) out.push(b);
  }
  return out;
}

export interface Door { ids: string[]; x: number; y: number; nx: number; ny: number }

const LEAD_M = 0.6;

/** Process one stretch inside a room: centre, pull straight, round, resample. Endpoints stay exactly where they are. */
function room(points: XY[], local: Seg[]): XY[] {
  if (points.length < 3) return points;
  const a = points[0], b = points[points.length - 1];
  const out = resample(roundCorners(pullStraight(centre(resample(points), local), local), local));
  out[0] = a; out[out.length - 1] = b;
  return out;
}

export function cameraPath<T extends PathPoint>(polyline: T[], walls: Wall[], doors: Door[] = []): T[] {
  const out: T[] = [];
  let run: T[] = [];
  const flush = () => {
    if (run.length < 3) { out.push(...run); run = []; return; }
    const xs = run.map(p => p.x), ys = run.map(p => p.y);
    const box = { x0: Math.min(...xs) - 3, x1: Math.max(...xs) + 3, y0: Math.min(...ys) - 3, y1: Math.max(...ys) + 3 };
    const local: Seg[] = walls.filter(w => w.floor_id === run[0].floor_id
      && Math.max(w.a[0], w.b[0]) >= box.x0 && Math.min(w.a[0], w.b[0]) <= box.x1 && Math.max(w.a[1], w.b[1]) >= box.y0 && Math.min(w.a[1], w.b[1]) <= box.y1);
    // doors the route crosses: where the space changes, the door joining those two spaces nearest to the crossing
    const crossings: { at: number; door: Door; dir: 1 | -1 }[] = [];
    for (let i = 1; i < run.length; i++) {
      if (run[i].node === run[i - 1].node) continue;
      let best: Door | null = null, bestD = 1.6;
      for (const d of doors) {
        if (!d.ids.includes(run[i].node) || !d.ids.includes(run[i - 1].node)) continue;
        const dist = Math.hypot(d.x - run[i].x, d.y - run[i].y);
        if (dist < bestD) { bestD = dist; best = d; }
      }
      if (best) {
        const next = run[Math.min(run.length - 1, i + 1)], prev = run[i - 1];
        crossings.push({ at: i, door: best, dir: (best.nx * (next.x - prev.x) + best.ny * (next.y - prev.y)) >= 0 ? 1 : -1 });
      }
    }
    const pts = run.map(p => [p.x, p.y] as XY);
    const result: XY[] = [];
    let from = 0;
    for (const c of crossings) {
      const n: XY = [c.door.nx * c.dir, c.door.ny * c.dir];
      const before: XY = [c.door.x - n[0] * LEAD_M, c.door.y - n[1] * LEAD_M], mid: XY = [c.door.x, c.door.y], after: XY = [c.door.x + n[0] * LEAD_M, c.door.y + n[1] * LEAD_M];
      // original points up to just before the lead-in, ending exactly at the lead-in point
      const room1 = [...pts.slice(from, c.at).filter(q => Math.hypot(q[0] - c.door.x, q[1] - c.door.y) > LEAD_M + 0.1), before];
      if (result.length) room1.unshift(result.pop()!);
      result.push(...room(room1, local), mid, after);
      from = c.at;
      while (from < pts.length && Math.hypot(pts[from][0] - c.door.x, pts[from][1] - c.door.y) < LEAD_M + 0.1) from++;
    }
    const tail = pts.slice(from);
    const last = pts[pts.length - 1];
    const lastRoom = [...(result.length ? [result.pop()!] : []), ...tail];
    if (!tail.length || Math.hypot(lastRoom.at(-1)![0] - last[0], lastRoom.at(-1)![1] - last[1]) > 1e-6) lastRoom.push(last);
    result.push(...room(lastRoom, local));
    const dense = resample(result);
    for (const q of dense) {
      let src = run[0], best = Infinity;
      for (const p of run) { const d = (p.x - q[0]) ** 2 + (p.y - q[1]) ** 2; if (d < best) { best = d; src = p; } }
      out.push({ ...src, x: q[0], y: q[1] });
    }
    out[out.length - dense.length] = { ...out[out.length - dense.length], x: run[0].x, y: run[0].y };
    out[out.length - 1] = { ...out[out.length - 1], x: last[0], y: last[1] };
    run = [];
  };
  for (const p of polyline) {
    if (run.length && (p.floor_id !== run[0].floor_id || p.gap)) flush();
    run.push(p);
  }
  flush();
  return out;
}
