/** How the camera shows one floor change. Only the clean case (a real stair flight with a footprint, both stops above each other and
 *  short legs from the route's points to the flight ends) is walked; everything else (lifts, no footprint, legs through the treads or over
 *  the stair hole, stops metres apart) gets the StairInterlude overlay. When unsure: interlude. See docs/TASKLIST.md, stairs audit. */
export type RideMode = "walk" | "interlude";
export interface RideStep {
  kind: "stairs" | "lift" | string;
  from: { x: number; y: number };
  to: { x: number; y: number };
  /** the stair's own flight line on the plan (bottom to top), or null when no flight footprint fits */
  flight: { x: number; y: number }[] | null;
}
const LEG_MAX = 0.6, STOP_GAP_MAX = 1.5;

export function rideMode(step: RideStep): RideMode {
  if (step.kind !== "stairs") return "interlude";
  const f = step.flight;
  if (!f || f.length < 2) return "interlude";
  const ok = (v: number) => Number.isFinite(v);
  if (![step.from.x, step.from.y, step.to.x, step.to.y].every(ok) || !f.every(p => ok(p.x) && ok(p.y))) return "interlude";
  if (Math.hypot(step.to.x - step.from.x, step.to.y - step.from.y) > STOP_GAP_MAX) return "interlude";
  const d = (a: { x: number; y: number }, b: { x: number; y: number }) => Math.hypot(a.x - b.x, a.y - b.y);
  const start = f[0], end = f[f.length - 1];
  // either direction: the legs before and after the flight must be short, or they cut through treads / float over the hole
  const up = Math.max(d(step.from, start), d(step.to, end)), down = Math.max(d(step.from, end), d(step.to, start));
  return Math.min(up, down) <= LEG_MAX ? "walk" : "interlude";
}
