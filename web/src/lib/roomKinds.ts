import type { Space } from "./types";

/** One colour per kind of room, so a bathroom looks like a bathroom everywhere: 3D floors, the plan, the legend, chips.
 *  Colour is never the only cue (names, icons and the legend always accompany it). Hues are spread around the wheel and
 *  kept apart from the route amber (#ffd45c), the closure red and the "you are here" green. */
export type RoomKind =
  | "toilet" | "kitchen" | "lab" | "office" | "meeting" | "lobby" | "circulation" | "core"
  | "production" | "warehouse" | "technical" | "storage" | "living" | "sleep" | "other";

interface KindStyle { label: string; scene: string; plan: string; ink: string; icon: string }

export const ROOM_KIND: Record<RoomKind, KindStyle> = {
  toilet:      { label: "Toilets & bathrooms",      scene: "#2f9fb3", plan: "#c8eaf0", ink: "#0d4a58", icon: "wc" },
  kitchen:     { label: "Kitchens & canteens",      scene: "#d98a43", plan: "#fbe3c8", ink: "#6b3c0b", icon: "kitchen" },
  lab:         { label: "Labs & workshops",         scene: "#45a874", plan: "#cdeedd", ink: "#14502e", icon: "lab" },
  office:      { label: "Offices",                  scene: "#7e93a8", plan: "#e3e9ee", ink: "#2a3a4a", icon: "office" },
  meeting:     { label: "Meeting, seminar & lecture", scene: "#8c78c4", plan: "#e4dcf6", ink: "#3b2c70", icon: "meeting" },
  lobby:       { label: "Lobbies & entrances",      scene: "#c2a15a", plan: "#f2e8cc", ink: "#5c4710", icon: "exit" },
  circulation: { label: "Corridors & aisles",       scene: "#dde4e3", plan: "#f4f5f4", ink: "#2a3237", icon: "route" },
  core:        { label: "Stairs & lifts",           scene: "#8ea6b6", plan: "#c9cfcc", ink: "#243a4d", icon: "lift" },
  production:  { label: "Production bays",          scene: "#cf6f58", plan: "#f7d9d1", ink: "#6a2415", icon: "machine" },
  warehouse:   { label: "Warehouse & logistics",    scene: "#9d8d5c", plan: "#ece5cf", ink: "#4e4219", icon: "box" },
  technical:   { label: "Server & technical",       scene: "#4f86d0", plan: "#d3e2f6", ink: "#173a6b", icon: "server" },
  storage:     { label: "Storage & lockers",        scene: "#8d9d7b", plan: "#e1e8d8", ink: "#3a4a28", icon: "box" },
  living:      { label: "Living & dining",          scene: "#b78f78", plan: "#f1e0d6", ink: "#5a3a28", icon: "sofa" },
  sleep:       { label: "Bedrooms",                 scene: "#a77fa0", plan: "#efdcec", ink: "#5a2f55", icon: "bed" },
  other:       { label: "Other rooms",              scene: "#7a8a93", plan: "#e6eaec", ink: "#2a3a42", icon: "room" },
};

export function kindOf(space: Space): RoomKind {
  const t = `${space.type} ${space.room_type}`;
  if (/stair|lift/.test(t)) return "core";
  if (/toilet|bathroom|wc|shower/.test(t)) return "toilet";
  if (/kitchen|canteen|dining|shop/.test(t)) return /dining/.test(t) ? "living" : "kitchen";
  if (/bedroom/.test(t)) return "sleep";
  if (/living|balcony/.test(t)) return /balcony/.test(t) ? "circulation" : "living";
  if (/corridor|aisle/.test(t)) return "circulation";
  if (/lobby|hall_access|reception|entrance/.test(t)) return "lobby";
  if (/production|assembly|additive/.test(t)) return "production";
  if (/warehouse|logistics/.test(t)) return "warehouse";
  if (/server|technical/.test(t)) return "technical";
  if (/lab|quality|makerspace|workshop/.test(t)) return "lab";
  if (/meeting|seminar|lecture|library|classroom/.test(t)) return "meeting";
  if (/storage|locker|print_room|archive/.test(t)) return "storage";
  if (/office/.test(t)) return "office";
  return /hall/.test(t) ? "circulation" : "other";
}

export const kindScene = (space: Space) => ROOM_KIND[kindOf(space)].scene;
export const kindPlan = (space: Space) => ROOM_KIND[kindOf(space)].plan;

/** The kinds present in a set of spaces, most common first: a legend only lists what the person can see. */
export function kindsPresent(spaces: Space[]): { kind: RoomKind; count: number }[] {
  const counts = new Map<RoomKind, number>();
  for (const s of spaces) counts.set(kindOf(s), (counts.get(kindOf(s)) ?? 0) + 1);
  return [...counts].map(([kind, count]) => ({ kind, count })).sort((a, b) => b.count - a.count);
}
