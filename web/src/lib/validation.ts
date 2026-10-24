import type { Route } from "./types";

/** Validate the render contract at the stream boundary, before state becomes visible. */
export function isRoute(value: unknown): value is Route {
  const r = value as Route | null;
  return !!r && Array.isArray(r.stops) && r.stops.length >= 2 && r.stops.every(s=>typeof s==="string")
    && Number.isFinite(r.length_m) && Array.isArray(r.constraints) && Array.isArray(r.floors)
    && Array.isArray(r.polyline) && r.polyline.length > 0
    && r.polyline.every(p=>!!p && Number.isFinite(p.x) && Number.isFinite(p.y) && typeof p.floor_id==="string")
    && !!r.guide && Array.isArray(r.guide.steps) && r.guide.steps.length > 0
    && r.guide.steps.every(s=>!!s && typeof s.text==="string" && Number.isFinite(s.metres))
    && typeof r.guide.spoken==="string";
}
