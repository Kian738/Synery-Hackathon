import type { Geometry, Space, XY } from "./types";

export function bounds(points: XY[]) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [x, y] of points) {
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  if (!isFinite(minX)) return { minX: 0, minY: 0, maxX: 10, maxY: 10 };
  return { minX, minY, maxX, maxY };
}

export function area(polygon: XY[]): number {
  let a = 0;
  for (let i = 0; i < polygon.length; i++) {
    const [x0, y0] = polygon[i];
    const [x1, y1] = polygon[(i + 1) % polygon.length];
    a += x0 * y1 - x1 * y0;
  }
  return Math.abs(a / 2);
}

export function centroid(polygon: XY[]): XY {
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < polygon.length; i++) {
    const [x0, y0] = polygon[i];
    const [x1, y1] = polygon[(i + 1) % polygon.length];
    const f = x0 * y1 - x1 * y0;
    a += f;
    cx += (x0 + x1) * f;
    cy += (y0 + y1) * f;
  }
  if (Math.abs(a) < 1e-9) return polygon[0];
  return [cx / (3 * a), cy / (3 * a)];
}

/** Five zones at most (signage guidance), always shown with a text label too. */
export type Zone = "circulation" | "hall" | "office" | "lab" | "service" | "core";

export function zoneOf(space: Space): Zone {
  const t = `${space.type} ${space.room_type}`;
  if (/stair|lift/.test(t)) return "core";
  if (/corridor|lobby|hall_access|balcony/.test(t)) return "circulation";
  if (/hall|production|assembly|additive|warehouse|logistics/.test(t)) return "hall";
  if (/lab|quality|makerspace|server|technical/.test(t)) return "lab";
  if (/toilet|bathroom|kitchen|canteen|locker|shop/.test(t)) return "service";
  return "office";
}

export const ZONE_LABEL: Record<Zone, string> = {
  circulation: "Circulation",
  hall: "Halls",
  office: "Rooms & offices",
  lab: "Labs & technical",
  service: "Kitchens & toilets",
  core: "Stairs & lifts",
};

/** Category shortcuts for people who know no room names; only those present in this building. */
export interface Category {
  key: string;
  label: string;
  query: string;
  icon: string;
}

const CATEGORY_RULES: { key: string; label: string; icon: string; test: (g: Geometry) => string | null }[] = [
  { key: "toilet", label: "Toilets", icon: "wc", test: (g) => (g.spaces.some((s) => /toilet|bathroom/.test(s.room_type)) ? "toilet" : null) },
  { key: "coffee", label: "Coffee", icon: "coffee", test: (g) => (g.assets.some((a) => a.type === "coffee_machine") ? "coffee machine" : null) },
  { key: "kitchen", label: "Kitchen", icon: "kitchen", test: (g) => (g.spaces.some((s) => s.room_type === "kitchen") ? "kitchen" : null) },
  { key: "canteen", label: "Canteen", icon: "kitchen", test: (g) => (g.spaces.some((s) => s.room_type === "canteen") ? "canteen" : null) },
  { key: "meeting", label: "Meeting room", icon: "meeting", test: (g) => (g.spaces.some((s) => s.room_type === "meeting_room") ? "meeting room" : null) },
  { key: "lift", label: "Lift", icon: "lift", test: (g) => (g.connectors.some((c) => c.kind === "lift") ? "lift" : null) },
  { key: "exit", label: "Exit", icon: "exit", test: (g) => (g.openings.some((o) => o.kind === "entrance") ? "exit" : null) },
  { key: "first_aid", label: "First aid", icon: "aid", test: (g) => (g.assets.some((a) => /first_aid|defibrillator/.test(a.type)) ? "first aid" : null) },
  { key: "printer", label: "Printer", icon: "printer", test: (g) => (g.assets.some((a) => /printer/.test(a.type)) ? "printer" : null) },
  { key: "lab", label: "Lab", icon: "lab", test: (g) => (g.spaces.some((s) => s.room_type === "lab") ? "lab" : null) },
];

export function categories(g: Geometry): Category[] {
  const out: Category[] = [];
  for (const rule of CATEGORY_RULES) {
    const query = rule.test(g);
    if (query) out.push({ key: rule.key, label: rule.label, query, icon: rule.icon });
  }
  return out.slice(0, 7);
}

export const label = (g: Geometry, id: string | null | undefined) => {
  if (!id) return "";
  const s = g.spaces.find((x) => x.id === id);
  return s ? s.name : id;
};
