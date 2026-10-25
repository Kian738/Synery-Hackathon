import type { Asset } from "./types";

/** Orientation of items whose dataset rotation is unreliable. Everything else keeps the measured rotation + 180 (`eval.orientation`).
 *  - Wall-backed furniture (vending machines, shelves, cabinets, appliances, boards ...): the dataset leaves some at rotation 0 whatever the
 *    wall does (CIT's Magistrale vending machines face along the wall). When the measured back is not on the nearest wall of the room, the item
 *    turns square to that wall with its back against it. Items that already stand right are untouched.
 *  - Chairs tucked within CHAIR_REACH_M of a desk turn to that desk's own axis (never to a corner).
 *  Lecture rows are NOT touched: halls are round, fan-shaped or mixed, and the measured rotations are the best information. */
export const FACING_OFFSET_DEG = 180;
export const CHAIR_REACH_M = 0.7;
export const WALL_REACH_M = 0.9;
export const WALL_TOLERANCE_DEG = 35;
const WALL_BACKED = new Set(["vending_machine", "bookshelf", "shelf", "paper_shelf", "wardrobe", "fridge", "stove", "tv_stand", "nightstand", "filing_cabinet", "locker", "coffee_machine", "microwave", "dishwasher", "washing_machine", "whiteboard", "display_screen", "projector_screen", "coat_rack", "shoe_cabinet", "tool_cabinet", "chemical_cabinet", "fire_extinguisher", "electrical_panel", "printer", "multifunction_printer", "hand_dryer", "water_dispenser", "atm", "ups_unit", "defibrillator", "eyewash_station", "sofa"]);
// Not here, measured: kitchen counters 46 %, server racks 37 %, built-in wardrobes 48 % would change (islands, aisles, fitted runs): the dataset rotation stays.
const CHAIRS = new Set(["chair", "office_chair", "dining_chair", "outdoor_chair"]);
const SURFACES = new Set(["desk", "dining_table", "seminar_table", "meeting_table", "reading_table", "canteen_table", "workbench", "lab_bench", "outdoor_table", "reception_desk", "assembly_station", "packing_station"]);

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

type Ring = [number, number][];

/** Nearest wall of the room: distance, the unit normal pointing into the room, and the wall point. */
function nearestWall(ring: Ring, x: number, y: number) {
  let best = { d: Infinity, nx: 0, ny: 0, px: 0, py: 0 };
  const cx = ring.reduce((s, p) => s + p[0], 0) / ring.length, cy = ring.reduce((s, p) => s + p[1], 0) / ring.length;
  for (let i = 0; i < ring.length; i++) {
    const [ax, ay] = ring[i], [bx, by] = ring[(i + 1) % ring.length], ex = bx - ax, ey = by - ay, len2 = ex * ex + ey * ey;
    if (len2 < 1e-9) continue;
    const u = Math.max(0, Math.min(1, ((x - ax) * ex + (y - ay) * ey) / len2)), px = ax + u * ex, py = ay + u * ey, d = Math.hypot(x - px, y - py);
    if (d < best.d) {
      const len = Math.sqrt(len2); let nx = -ey / len, ny = ex / len;
      const toward = (x - px) * nx + (y - py) * ny || (cx - px) * nx + (cy - py) * ny; // item on the wall line: the side of the room centre
      if (toward < 0) { nx = -nx; ny = -ny; }
      best = { d, nx, ny, px, py };
    }
  }
  return best;
}

function wallYaw(asset: Asset, ring: Ring | undefined): number {
  const measured = own(asset);
  if (!ring || ring.length < 3) return measured;
  const w = nearestWall(ring, asset.position[0], asset.position[1]);
  if (w.d > WALL_REACH_M) return measured;
  const r = rad(measured), backX = Math.sin(r), backY = -Math.cos(r);             // plan direction of the measured back
  const toWallX = -w.nx, toWallY = -w.ny;                                          // from the item into the wall
  const angle = (Math.acos(Math.max(-1, Math.min(1, backX * toWallX + backY * toWallY))) * 180) / Math.PI;
  return angle <= WALL_TOLERANCE_DEG ? measured : yawFor(w.nx, w.ny);              // front into the room, back on the wall
}

/** Y rotation (degrees) of one asset's model: front is local -Z. `room` holds the assets of the same space, `ring` its polygon. */
export function facingDegrees(asset: Asset, room: Asset[], ring?: Ring): number {
  if (CHAIRS.has(asset.type)) return chairYaw(asset, room);
  if (WALL_BACKED.has(asset.type)) return wallYaw(asset, ring);
  return own(asset);
}

/** Rotation per asset id, grouped by room. `rings` maps a space id to its polygon. */
export function facingTable(assets: Asset[], rings?: Map<string, Ring>): Map<string, number> {
  const rooms = new Map<string, Asset[]>();
  for (const a of assets) { const r = rooms.get(a.space_id); if (r) r.push(a); else rooms.set(a.space_id, [a]); }
  const out = new Map<string, number>();
  for (const [space, room] of rooms) for (const a of room) out.set(a.id, facingDegrees(a, room, rings?.get(space)));
  return out;
}
