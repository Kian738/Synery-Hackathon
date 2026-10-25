export type XY = [number, number];

export interface Floor {
  id: string;
  level: number;
  name: string;
  elevation_m: number;
  height_m: number;
}

export interface Space {
  id: string;
  floor_id: string;
  type: string;
  room_type: string;
  name: string;
  ref: string | null;
  polygon: XY[];
  anchor?: XY;
}

export interface Opening {
  id: string;
  floor_id: string;
  space_ids: string[];
  kind: string;
  position: XY;
  width_m: number;
  step_free: boolean;
}

export interface Connector {
  id: string;
  kind: "stairs" | "lift";
  name: string;
  floor_ids: string[];
  space_ids: string[];
  step_free: boolean;
}

export interface Asset {
  id: string;
  name: string;
  type: string;
  category: string;
  space_id: string;
  floor_id: string;
  position: XY;
  footprint?: { width_m: number; depth_m: number; rotation_deg: number };
}

export interface Geometry {
  building: { id: string; name: string; source: string; source_ref?:{osm?:string}; attribution?:string; license?:string };
  scene?: { plates?: Record<string, { exterior: XY[]; holes: XY[][] }[]>; stair_shafts?: {connector_id:string;from_floor:string;to_floor:string;footprint:XY[]|null;basis:string;warning:string|null}[]; revision: string; headers?: { floor_id: string; a: XY; b: XY; base_m: number; height_m: number }[]; roofs?: { floor_id: string; vertices: XY[]; area_m2: number; elevation_m: number }[]; slabs?: {floor_id:string;vertices:XY[];area_m2:number}[]; walls: { floor_id: string; space_id: string|null; a: XY; b: XY; height_m: number }[]; unmatched_openings: string[]; assumptions: string[] };
  floors: Floor[];
  spaces: Space[];
  openings: Opening[];
  connectors: Connector[];
  assets: Asset[];
}

export interface GuideStep {
  kind: "start" | "walk" | "floor" | "outside" | "arrive";
  icon: "start" | "straight" | "left" | "right" | "back" | "lift" | "stairs" | "outside" | "arrive";
  text: string;
  short: string;
  metres: number;
  floor_id: string | null;
  point: XY | null;
  landmark: string | null;
  space_id: string | null;
}

export interface RoutePoint {
  floor_id: string;
  x: number;
  y: number;
  node: string;
  gap?: boolean;
}

export interface Route {
  preview_available?: boolean;
  warnings?: string[];
  stops: string[];
  length_m: number;
  steps: string[];
  constraints: string[];
  floors: string[];
  polyline: RoutePoint[];
  guide: { steps: GuideStep[]; spoken: string };
  walk_m?: number | null;
}

export interface Impact {
  of_rooms?: number;
  cut_off_ids?: string[];
  reconnected_ids?: string[];
  step_free?: Impact;
  your_needs?: Impact;
  rooms_cut_off_from_exits: string[];
  cut_off_count: number;
  rooms_reconnected: string[];
  longer_way_out_count: number;
  shorter_way_out_count: number;
  most_affected: { room: string; change_m: number }[];
}

export interface Profile {
  location_source?: "default" | "declared" | "link" | null;
  step_free: boolean;
  min_door_width_m: number | null;
  location: string | null;
}

export interface FixProposal { reachable_before: boolean; reason: string; verified: boolean; widen: { opening_id: string; from_m: number; to_m: number; between: string[] }[]; rooms_reachable_before?: number | null; rooms_reachable_after?: number | null; of_rooms?: number | null }
export interface WeakPoint { name: string; element_ids: string[]; room_ids: string[]; rooms_lost: number; of_rooms: number; kind: string }

export type UiEvent =
  | { type: "visual_result"; result: VisualResult; total_rows: number }
  | { type: "fix_preview"; opening: Opening; fix: FixProposal; start: string; destination: string }
  | { type: "weak_points"; items: WeakPoint[]; profile: string }
  | { type: "route"; route: Route }
  | { type: "highlight"; ids: string[] }
  | { type: "closure"; id: string; closed: boolean; impact: Impact }
  | { type: "preview_door"; door: Opening; impact: Impact }
  | { type: "edit"; op: string; [key: string]: unknown }
  | { type: "profile"; profile: Profile }
  | { type: "scenario_result"; report: ScenarioReport; hazard: string }
  | { type: "scenario_replay"; action: "play" | "pause" | "restart" | "seek"; seconds?: number }
  | { type: "choice"; question: string; options: string[] };

export interface BuildingRow {
  building_id: string;
  split: string;
  source: string;
  name: string;
  floors: string;
  rooms?: string | number | null;
}

export interface VisualResult {
  id:string;
  kind:"comparison"|"matches"|"count"|"ranking"|"area"|"shared_walls"|"stacking"|"distance"|"reachability"|"intervention";
  title:string;
  entities:{id:string;floor_id:string;kind:string}[];
  floor_ids:string[];
  measurements:Record<string,unknown>;
  lines:{a:[number,number,number];b:[number,number,number]}[];
  warnings:string[];
  provenance:string;
}

export type Audience = "safety_officer" | "occupant" | "builder" | "regulator";
export interface ScenarioStep { id: string; op: string; ok: boolean; summary: string; reason: string | null; ms: number }
export interface ScenarioFinding { severity: "blocker" | "risk" | "improve" | "info"; title: string; detail: string; evidence: string[]; tier: string; suggestion: string | null }
export interface ScenarioFix { element: string; width_m: number; previous_width_m: number; between: string[]; T_before_s: number; T_after_s: number }
export interface ScenarioMove { depart_s: number; element: string; from_space: string; to_space: string; persons: number; arrive_s: number }
export interface ScenarioResponder { entrance: string; spaces: string[]; elements: string[]; arrival_s: number; delay_s: number }
/** What the plan and 3D view draw for a scenario: hazard, slow doors, responder route, and replay crowd level per room (1 some, 2 many). */
export interface ScenarioMark { hazard: string; doors: string[]; responder?: ScenarioResponder | null; crowd?: Record<string, 1 | 2> }
export interface ScenarioReport {
  steps: ScenarioStep[];
  abstained: { step?: string; reason?: string } | string | null;
  answer: { fixes?: ScenarioFix[] } | null;
  evacuation?: { T_s: number; total: number; evacuated: number; stranded: Record<string, number>; by_exit: Record<string, number>; bottleneck: string[]; nearest_exit?: { T_s: number; evacuated: number } | null; schedule?: ScenarioMove[] } | null;
  responder?: ScenarioResponder | null;
  findings: ScenarioFinding[];
}

export interface RobustReport { before: { lost_exit: string | null; evacuated: number; T_s: number }[]; after: { lost_exit: string | null; evacuated: number; T_s: number }[]; verified: boolean; fixes: { element: string; name: string; width_m: number }[] }
