// A guided trip between two buildings: inside A (Navigator), outside (map), inside B (Navigator).
// The route and the position in the trip live in sessionStorage so the three screens can hand over to each other.

export type Mode = "foot" | "wheelchair" | "bike" | "car";
export type Door = { opening_id: string; label: string; lat: number; lon: number; step_free: boolean; width_m: number | null };
export type IndoorLeg = {
  kind: "indoor"; role: "exit" | "entry"; building_id: string; building_name: string; distance_m: number;
  from: string; to: string; at: string; target: string; door: Door;
  trivial?: boolean; // the room already is the entrance room: nothing to walk inside
  route: Record<string, unknown> & { steps: string[]; preview_available?: boolean; warnings?: string[] };
};
export type OutdoorStep = { instruction: string; distance_m: number; at?: [number, number] };
export type OutdoorLeg = {
  kind: "outdoor"; distance_m: number; duration_min: number; polyline: [number, number][]; estimated: boolean; provider: string; mode: Mode;
  steps: OutdoorStep[];
  from: { label: string; lat: number; lon: number }; to: { label: string; lat: number; lon: number };
};
export type Leg = IndoorLeg | OutdoorLeg;
export type CampusResult = {
  from_building: { id: string; name: string }; to_building: { id: string; name: string }; legs: Leg[]; mode: Mode;
  total_m: number; duration_min: number; entrance_pairs_considered: number; warnings: string[];
  alternatives: { exit: string; entrance: string; total_m: number; outdoor_m: number; estimated: boolean }[];
};
export type Query = { from_building: string; to_building: string; from_room: string; to_room: string; mode: Mode };

const ROUTE_KEY = "fw-campus-route";
const JOURNEY_KEY = "fw-journey";

export function loadRoute(): { query: Query; result: CampusResult } | null {
  try {
    const saved = JSON.parse(sessionStorage.getItem(ROUTE_KEY) ?? "null");
    return saved?.result ? { query: { mode: "foot", ...saved.query }, result: saved.result } : null;
  } catch { return null; } // a stale or corrupt entry is just ignored
}
export const saveRoute = (query: Query, result: CampusResult) => sessionStorage.setItem(ROUTE_KEY, JSON.stringify({ query, result }));
export const clearRoute = () => { sessionStorage.removeItem(ROUTE_KEY); clearJourney(); };

export function journeyIndex(): number | null {
  const raw = sessionStorage.getItem(JOURNEY_KEY);
  const index = raw === null ? NaN : Number(raw);
  return Number.isInteger(index) && index >= 0 ? index : null;
}
export const setJourneyIndex = (index: number) => sessionStorage.setItem(JOURNEY_KEY, String(index));
export const clearJourney = () => sessionStorage.removeItem(JOURNEY_KEY);

/** Where the Navigator should open for an indoor leg: it walks from `at` to the exit (or from the entrance to the room). */
export function indoorLink(leg: IndoorLeg, mode: Mode): string {
  // No `to`: the Navigator shows this leg exactly as the trip planner computed it (to the exit door, or from the
  // entrance), instead of planning its own route to the room.
  const params = new URLSearchParams({ building: leg.building_id, from: "map", at: leg.at, trip: leg.role });
  if (mode === "wheelchair") params.set("step_free", "1");
  return `/?${params}`;
}

/** The indoor leg the person is on right now, if a journey is running in this building. */
export function currentIndoorLeg(buildingId: string) {
  // Only when this Navigator page was opened for a leg (not by diving into the building from the map).
  const role = new URLSearchParams(window.location.search).get("trip");
  const saved = loadRoute();
  if (!saved || (role !== "exit" && role !== "entry")) return null;
  const index = saved.result.legs.findIndex((l) => l.kind === "indoor" && l.role === role && l.building_id === buildingId);
  const leg = saved.result.legs[index];
  if (!leg || leg.kind !== "indoor") return null;
  // `active`: a trip is running and this is its current leg. Otherwise the leg is just being looked at.
  return { leg, index, active: journeyIndex() === index, total: saved.result.legs.length, result: saved.result, mode: saved.query.mode, key: `${role}:${leg.building_id}` };
}

/** What to say for an outdoor leg without turn-by-turn steps (a straight-line estimate). */
export function fallbackSteps(leg: OutdoorLeg, destination: string): OutdoorStep[] {
  const verb = { foot: "Walk", wheelchair: "Roll", bike: "Cycle", car: "Drive" }[leg.mode];
  return [
    { instruction: `${verb} towards ${destination} (about ${Math.round(leg.distance_m)} m; no street directions available)`, distance_m: Math.round(leg.distance_m), at: [leg.from.lon, leg.from.lat] },
    { instruction: `You have reached ${destination}`, distance_m: 0, at: [leg.to.lon, leg.to.lat] },
  ];
}

/** The next leg to walk after `index`: an entry leg whose room is already at the door is skipped (the trip ends there). */
export function nextLeg(result: CampusResult, index: number): number {
  let next = index + 1;
  while (next < result.legs.length) {
    const leg = result.legs[next];
    if (!(leg.kind === "indoor" && leg.trivial && leg.role === "entry")) break; // an exit leg is always shown: it is where the trip starts
    next += 1;
  }
  return next;
}

/** Where the person ends up when the trip is over: the destination building, at the entrance room when that is the destination. */
export function arrivalLink(result: CampusResult): string {
  const entry = result.legs.find((l): l is IndoorLeg => l.kind === "indoor" && l.role === "entry");
  return `/?building=${encodeURIComponent(result.to_building.id)}&from=map${entry?.trivial ? `&at=${encodeURIComponent(entry.at)}` : ""}`;
}

/** Leaving the teleport tunnel: the indoor leg in the destination building, or the arrival if there is nothing to walk. */
export function afterTunnel(result: CampusResult, outdoorIndex: number, mode: Mode): { to: string; finished: boolean } {
  const next = nextLeg(result, outdoorIndex);
  const leg = result.legs[next];
  if (leg?.kind === "indoor") { setJourneyIndex(next); return { to: indoorLink(leg, mode), finished: false }; }
  return { to: arrivalLink(result), finished: true };
}
