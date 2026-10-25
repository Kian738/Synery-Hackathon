import type { Asset } from "./types";

/** The dataset rotates seating at random (eval.orientation --relational: 19-22 % at every offset, i.e. no signal), so a chair or sofa is drawn
 *  facing the nearest table or screen of its own room when there is one within reach. Everything else keeps the measured rotation. */
const SURFACES = new Set(["desk", "dining_table", "seminar_table", "meeting_table", "reading_table", "canteen_table", "workbench", "lab_bench", "outdoor_table", "reception_desk", "assembly_station", "packing_station"]);
const FOCUS = new Set(["tv_stand", "whiteboard", "projector_screen", "display_screen", "lectern", "coffee_table"]);
const TARGETS: Record<string, Set<string>> = {
  chair: SURFACES, office_chair: SURFACES, dining_chair: SURFACES, outdoor_chair: SURFACES, armchair: FOCUS,
  lecture_seating_row: new Set(["whiteboard", "projector_screen", "display_screen", "lectern"]),
};
export const FACING_REACH_M = 2.8;
export const FACING_OFFSET_DEG = 180;

/** Y rotation (degrees) of the model whose front is local -Z; plan (x, y) maps to scene (x, -y). */
export function facingDegrees(asset: Asset, room: Asset[]): number {
  const own = (asset.footprint?.rotation_deg ?? 0) + FACING_OFFSET_DEG;
  const kinds = TARGETS[asset.type];
  if (!kinds) return own;
  let best: Asset | null = null, bestD = FACING_REACH_M;
  for (const o of room) {
    if (o === asset || !kinds.has(o.type)) continue;
    const d = Math.hypot(o.position[0] - asset.position[0], o.position[1] - asset.position[1]);
    if (d < bestD) { best = o; bestD = d; }
  }
  if (!best || bestD < 0.05) return own;
  const dx = best.position[0] - asset.position[0], dy = best.position[1] - asset.position[1];
  return (Math.atan2(-dx, dy) * 180) / Math.PI;
}

/** Rotation per asset id for one list of assets, grouped by room. */
export function facingTable(assets: Asset[]): Map<string, number> {
  const rooms = new Map<string, Asset[]>();
  for (const a of assets) { const r = rooms.get(a.space_id); if (r) r.push(a); else rooms.set(a.space_id, [a]); }
  const out = new Map<string, number>();
  for (const room of rooms.values()) for (const a of room) out.set(a.id, facingDegrees(a, room));
  return out;
}
