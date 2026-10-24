import type { Route, VisualResult } from "./types";

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

export function isVisualResult(value:unknown):value is VisualResult {
  const r=value as VisualResult|null;
  const xyz=(p:unknown)=>Array.isArray(p)&&p.length===3&&p.every(Number.isFinite);
  const proposed=r?.measurements?.proposed_opening as Record<string,unknown>|undefined;
  const primary=r?.measurements?.primary_ids;
  const validProposal=proposed===undefined||(!!proposed&&typeof proposed.floor_id==="string"&&Array.isArray(proposed.space_ids)&&proposed.space_ids.every(id=>typeof id==="string")&&Array.isArray(proposed.position)&&proposed.position.length===2&&proposed.position.every(Number.isFinite)&&typeof proposed.width_m==="number"&&Number.isFinite(proposed.width_m)&&proposed.width_m>0);
  return validProposal&&(primary===undefined||(Array.isArray(primary)&&primary.every(id=>typeof id==="string")))&&!!r&&typeof r.id==="string"&&typeof r.title==="string"&&typeof r.provenance==="string"
    &&["matches","count","ranking","area","shared_walls","stacking","distance","reachability","intervention"].includes(r.kind)
    &&Array.isArray(r.entities)&&r.entities.every(e=>!!e&&typeof e.id==="string"&&typeof e.floor_id==="string"&&typeof e.kind==="string")
    &&Array.isArray(r.floor_ids)&&r.floor_ids.every(f=>typeof f==="string")
    &&!!r.measurements&&typeof r.measurements==="object"&&!Array.isArray(r.measurements)
    &&Array.isArray(r.warnings)&&r.warnings.every(w=>typeof w==="string")
    &&Array.isArray(r.lines)&&r.lines.every(l=>!!l&&xyz(l.a)&&xyz(l.b));
}
