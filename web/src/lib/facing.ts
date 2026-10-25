import type { Asset } from "./types";

/** Orientation of items whose dataset rotation is noise. Everything else keeps the measured rotation + 180 (`eval.orientation`).
 *  - Chairs turn to the nearest desk or table, but only to one of that desk's own four axes (a chair never points at a desk corner),
 *    and only when a desk edge is within CHAIR_REACH_M.
 *  - Lecture rows in one room are made parallel (the dataset mixes two orthogonal rotations in one hall) and turn their front (the desk side,
 *    where the people look) toward the lectern or board of the room when there is one. */
export const FACING_OFFSET_DEG = 180;
export const CHAIR_REACH_M = 1.0;
const CHAIRS = new Set(["chair", "office_chair", "dining_chair", "outdoor_chair"]);
const SURFACES = new Set(["desk", "dining_table", "seminar_table", "meeting_table", "reading_table", "canteen_table", "workbench", "lab_bench", "outdoor_table", "reception_desk", "assembly_station", "packing_station"]);
const FOCUS = new Set(["lectern", "whiteboard", "projector_screen", "display_screen"]);

const rad = (d: number) => (d * Math.PI) / 180;
const norm = (d: number) => ((d % 360) + 360) % 360;
/** Scene Y rotation (degrees) that turns the model front (local -Z) toward plan direction (dx, dy); plan y is scene -z. */
export const yawFor = (dx: number, dy: number) => (Math.atan2(-dx, dy) * 180) / Math.PI;
const own = (a: Asset) => (a.footprint?.rotation_deg ?? 0) + FACING_OFFSET_DEG;
const axesOf = (a: Asset) => { const r = rad(a.footprint?.rotation_deg ?? 0); return { ux: [Math.cos(r), Math.sin(r)], uy: [-Math.sin(r), Math.cos(r)] }; };
const dims = (a: Asset) => [a.footprint?.width_m ?? 0.5, a.footprint?.depth_m ?? 0.5];

/** Plan point of the desk rectangle closest to (x, y). */
function closestOnDesk(desk: Asset, x: number, y: number): [number, number] {
  const { ux, uy } = axesOf(desk), [w, d] = dims(desk);
  const dx = x - desk.position[0], dy = y - desk.position[1];
  const s = Math.max(-w / 2, Math.min(w / 2, dx * ux[0] + dy * ux[1])), t = Math.max(-d / 2, Math.min(d / 2, dx * uy[0] + dy * uy[1]));
  return [desk.position[0] + s * ux[0] + t * uy[0], desk.position[1] + s * ux[1] + t * uy[1]];
}

function chairYaw(chair: Asset, room: Asset[]): number {
  let best: Asset | null = null, bestD = CHAIR_REACH_M, bestPoint: [number, number] = [0, 0];
  for (const o of room) {
    if (!SURFACES.has(o.type)) continue;
    const p = closestOnDesk(o, chair.position[0], chair.position[1]), d = Math.hypot(p[0] - chair.position[0], p[1] - chair.position[1]);
    if (d < bestD) { best = o; bestD = d; bestPoint = p; }
  }
  if (!best) return own(chair);
  // chair sitting inside the desk footprint (d = 0): keep the measured rotation
  if (bestD < 0.03) return own(chair);
  const vx = bestPoint[0] - chair.position[0], vy = bestPoint[1] - chair.position[1];
  const { ux, uy } = axesOf(best);
  const candidates: number[][] = [ux, uy, [-ux[0], -ux[1]], [-uy[0], -uy[1]]];
  const snap = candidates.reduce((m, c) => (c[0] * vx + c[1] * vy > m[0] * vx + m[1] * vy ? c : m));
  return yawFor(snap[0], snap[1]);
}

function rowYaws(rows: Asset[], room: Asset[]): Map<string, number> {
  const out = new Map<string, number>();
  if (rows.length < 3) return out;
  // majority long-axis direction (the row's local x), in 15 degree bins modulo 180
  const bins = new Map<number, number>();
  for (const r of rows) { const b = Math.round(norm(r.footprint?.rotation_deg ?? 0) % 180 / 15) % 12; bins.set(b, (bins.get(b) ?? 0) + 1); }
  const bin = [...bins.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0])[0][0];
  const major = norm(rows.find(r => Math.round(norm(r.footprint?.rotation_deg ?? 0) % 180 / 15) % 12 === bin)!.footprint?.rotation_deg ?? 0) % 180;
  const focus = room.filter(o => FOCUS.has(o.type));
  const fx = focus.length ? focus.reduce((s, o) => s + o.position[0], 0) / focus.length : null;
  const fy = focus.length ? focus.reduce((s, o) => s + o.position[1], 0) / focus.length : null;
  // one common side for the whole hall, from the middle of the rows toward the board
  const cx = rows.reduce((q, r) => q + r.position[0], 0) / rows.length, cy = rows.reduce((q, r) => q + r.position[1], 0) / rows.length;
  let axis = major;
  if (fx !== null && fy !== null) { // people face the board: the rows' long axis is the common axis (or its quarter turn) that is most nearly square to the board
    const vx = fx - cx, vy = fy - cy, along = (deg: number) => Math.abs(-Math.sin(rad(deg)) * vx + Math.cos(rad(deg)) * vy);
    if (along(major + 90) > along(major)) axis = major + 90;
  }
  const px = -Math.sin(rad(axis)), py = Math.cos(rad(axis)); // plan direction of the row's local +y (perpendicular to its long axis)
  let sign = 1;
  if (fx !== null && fy !== null) sign = (fx - cx) * px + (fy - cy) * py >= 0 ? 1 : -1;
  else sign = rows.reduce((q, r) => q + (-Math.sin(rad(own(r))) * px + Math.cos(rad(own(r))) * py), 0) >= 0 ? 1 : -1;
  for (const r of rows) out.set(r.id, yawFor(px * sign, py * sign));
  return out;
}

/** Y rotation (degrees) of one asset's model: front is local -Z. `room` holds the assets of the same space. */
export function facingDegrees(asset: Asset, room: Asset[]): number {
  if (CHAIRS.has(asset.type)) return chairYaw(asset, room);
  if (asset.type === "lecture_seating_row") return rowYaws(room.filter(o => o.type === "lecture_seating_row"), room).get(asset.id) ?? own(asset);
  return own(asset);
}

/** Rotation per asset id for one list of assets, grouped by room. Rows are resolved once per room. */
export function facingTable(assets: Asset[]): Map<string, number> {
  const rooms = new Map<string, Asset[]>();
  for (const a of assets) { const r = rooms.get(a.space_id); if (r) r.push(a); else rooms.set(a.space_id, [a]); }
  const out = new Map<string, number>();
  for (const room of rooms.values()) {
    const rows = rowYaws(room.filter(o => o.type === "lecture_seating_row"), room);
    for (const a of room) out.set(a.id, CHAIRS.has(a.type) ? chairYaw(a, room) : (rows.get(a.id) ?? own(a)));
  }
  return out;
}
