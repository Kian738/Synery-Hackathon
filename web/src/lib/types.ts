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
  building: { id: string; name: string; source: string };
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
}

export interface Route {
  stops: string[];
  length_m: number;
  steps: string[];
  constraints: string[];
  floors: string[];
  polyline: RoutePoint[];
  guide: { steps: GuideStep[]; spoken: string };
}

export interface Impact {
  rooms_cut_off_from_exits: string[];
  cut_off_count: number;
  rooms_reconnected: string[];
  longer_way_out_count: number;
  shorter_way_out_count: number;
  most_affected: { room: string; change_m: number }[];
}

export interface Profile {
  step_free: boolean;
  min_door_width_m: number | null;
  location: string | null;
}

export type UiEvent =
  | { type: "route"; route: Route }
  | { type: "highlight"; ids: string[] }
  | { type: "closure"; id: string; closed: boolean; impact: Impact }
  | { type: "preview_door"; door: Opening; impact: Impact }
  | { type: "edit"; op: string; [key: string]: unknown }
  | { type: "profile"; profile: Profile };

export interface BuildingRow {
  building_id: string;
  split: string;
  source: string;
  name: string;
  floors: string;
}
