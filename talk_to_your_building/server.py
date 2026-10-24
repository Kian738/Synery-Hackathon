"""Standalone zero-dependency HTTP server and REST API for Talk to Your Building.

Serves the interactive 3D digital twin visualizer and provides REST endpoints for:
  - GET  /api/buildings
  - GET  /api/building/state
  - POST /api/route
  - POST /api/incident
  - POST /api/voice/intent

Can be launched via:
  python -m talk_to_your_building.server --port 8000
"""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import re
import sys
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

from shapely.ops import nearest_points

from talk_to_your_building.spatial_engine.building_loader import load_building
from talk_to_your_building.spatial_engine.graph import DOOR_PREFIX, OUTSIDE_NODE
from talk_to_your_building.spatial_engine.landmarks import (
    clarify_query,
    compute_path_waypoints,
    generate_landmark_instructions,
    resolve_clarification,
)
from talk_to_your_building.spatial_engine.models import Building, Opening, Space
from talk_to_your_building.spatial_engine.router import RouteResult, find_route

# Base directories
PACKAGE_DIR = Path(__file__).resolve().parent
VISUALIZER_DIR = PACKAGE_DIR / "visualizer"
WORKSPACE_DIR = PACKAGE_DIR.parent


def find_data_directories() -> list[Path]:
    """Find available data/dev and data/test directories across common workspace locations."""
    candidates = [
        WORKSPACE_DIR / "data",
        WORKSPACE_DIR / "industrial-agents-hackathon-2026" / "data",
        Path.cwd() / "data",
        Path.cwd() / "industrial-agents-hackathon-2026" / "data",
    ]
    existing = []
    seen = set()
    for c in candidates:
        if c.is_dir() and str(c.resolve()) not in seen:
            existing.append(c.resolve())
            seen.add(str(c.resolve()))
    return existing


def list_available_buildings() -> list[dict[str, Any]]:
    """Scan available buildings from data/dev/ and data/test/."""
    buildings: list[dict[str, Any]] = []
    seen_ids = set()

    for data_dir in find_data_directories():
        for split in ("dev", "test"):
            split_dir = data_dir / split
            if not split_dir.is_dir():
                continue
            for b_dir in sorted(split_dir.iterdir()):
                if b_dir.is_dir() and (b_dir / "building.json").is_file():
                    b_id = b_dir.name
                    if b_id in seen_ids:
                        continue
                    seen_ids.add(b_id)

                    # Quick inspect metadata
                    name = b_id
                    try:
                        with open(b_dir / "building.json", "r", encoding="utf-8") as f:
                            data = json.load(f)
                            meta = data.get("building", {})
                            name = meta.get("name") or b_id
                    except Exception:
                        pass

                    buildings.append(
                        {
                            "id": b_id,
                            "name": name,
                            "split": split,
                            "path": str(b_dir),
                        }
                    )

    buildings.sort(key=lambda x: (0 if x["split"] == "dev" else 1, x["id"]))
    return buildings


class BuildingSessionManager:
    """Manages loaded buildings, active dynamic closures, and counterfactual synthetic doors."""

    def __init__(self, default_building_id: Optional[str] = None):
        self.building_cache: dict[str, Building] = {}
        self.closed_elements: dict[str, set[str]] = {}  # building_id -> set of closed IDs
        self.incidents: dict[str, list[dict[str, Any]]] = {}  # building_id -> list of incidents
        self.synthetic_doors: dict[str, list[Opening]] = {}  # building_id -> list of Opening
        self.current_building_id: str = ""

        # Initial loading
        available = list_available_buildings()
        target_id = default_building_id or (available[0]["id"] if available else None)
        if target_id:
            self.load_or_switch_building(target_id)

    def load_or_switch_building(self, building_id_or_path: str) -> Optional[Building]:
        """Load building into cache or switch to it."""
        # 1. Match by exact building ID in cache
        if building_id_or_path in self.building_cache:
            self.current_building_id = building_id_or_path
            return self.building_cache[building_id_or_path]

        # 2. Check if it's a filesystem path
        p = Path(building_id_or_path)
        if (p.is_dir() and (p / "building.json").exists()) or (p.is_file() and p.name == "building.json"):
            b = load_building(p)
            self.building_cache[b.id] = b
            self.current_building_id = b.id
            if b.id not in self.closed_elements:
                self.closed_elements[b.id] = set()
                self.incidents[b.id] = []
                self.synthetic_doors[b.id] = []
            return b

        # 3. Search in data directories
        for data_dir in find_data_directories():
            for split in ("dev", "test"):
                candidate = data_dir / split / building_id_or_path
                if candidate.is_dir() and (candidate / "building.json").is_file():
                    b = load_building(candidate)
                    self.building_cache[b.id] = b
                    self.current_building_id = b.id
                    if b.id not in self.closed_elements:
                        self.closed_elements[b.id] = set()
                        self.incidents[b.id] = []
                        self.synthetic_doors[b.id] = []
                    return b

        # 4. Fallback search across available buildings
        for b_info in list_available_buildings():
            if b_info["id"] == building_id_or_path or building_id_or_path in b_info["path"]:
                b = load_building(b_info["path"])
                self.building_cache[b.id] = b
                self.current_building_id = b.id
                if b.id not in self.closed_elements:
                    self.closed_elements[b.id] = set()
                    self.incidents[b.id] = []
                    self.synthetic_doors[b.id] = []
                return b

        return None

    def get_current_building(self) -> Optional[Building]:
        if not self.current_building_id:
            available = list_available_buildings()
            if available:
                self.load_or_switch_building(available[0]["id"])
        return self.building_cache.get(self.current_building_id)

    def get_closed_set(self, building_id: Optional[str] = None) -> set[str]:
        bid = building_id or self.current_building_id
        return self.closed_elements.setdefault(bid, set())

    def get_incidents(self, building_id: Optional[str] = None) -> list[dict[str, Any]]:
        bid = building_id or self.current_building_id
        return self.incidents.setdefault(bid, [])

    def add_synthetic_door(
        self, space_a_id: str, space_b_id: str, width_m: float = 1.0, building_id: Optional[str] = None
    ) -> Optional[Opening]:
        """Dynamically insert an opening connecting two adjacent spaces."""
        bid = building_id or self.current_building_id
        building = self.building_cache.get(bid)
        if not building:
            return None

        space_a = building.spaces.get(space_a_id)
        space_b = building.spaces.get(space_b_id)
        if not space_a or not space_b:
            return None

        # Verify same floor
        if space_a.floor_id != space_b.floor_id:
            return None

        # Validate adjacency (separated by <= 0.8m)
        dist = space_a.polygon.distance(space_b.polygon)
        if dist > 0.8:
            return None

        # Calculate midpoint of nearest boundary points
        p_a, p_b = nearest_points(space_a.polygon, space_b.polygon)
        door_x = round((p_a.x + p_b.x) / 2.0, 3)
        door_y = round((p_a.y + p_b.y) / 2.0, 3)

        door_id = f"{space_a.floor_id}-O-SYN-{len(self.synthetic_doors.setdefault(bid, [])) + 1}"
        opening = Opening(
            id=door_id,
            floor_id=space_a.floor_id,
            space_ids=[space_a_id, space_b_id],
            kind="door",
            position=(door_x, door_y),
            width_m=float(width_m),
            step_free=True,
            synthetic=True,
        )

        # Register in building model
        building.openings[door_id] = opening
        building.openings_by_space.setdefault(space_a_id, []).append(opening)
        building.openings_by_space.setdefault(space_b_id, []).append(opening)
        building.openings_by_floor.setdefault(space_a.floor_id, []).append(opening)
        self.synthetic_doors[bid].append(opening)

        return opening


# Global session manager
SESSION = BuildingSessionManager()


class BuildingAPIRequestHandler(SimpleHTTPRequestHandler):
    """HTTP Request Handler delivering the REST API and static visualizer Single Page App."""

    def __init__(self, *args, **kwargs):
        # Serve static files from visualizer directory
        super().__init__(*args, directory=str(VISUALIZER_DIR), **kwargs)

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json_response(self, data: Any, status: int = 200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # REST API endpoints
        if path == "/api/buildings":
            self.handle_get_buildings()
            return
        elif path == "/api/building/state":
            b_id = query.get("building", [None])[0]
            self.handle_get_building_state(b_id)
            return

        # Serve visualizer index for root or direct assets
        if path in ("", "/"):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            self._send_json_response({"error": "Invalid JSON payload"}, status=400)
            return

        if path == "/api/route":
            self.handle_post_route(payload)
        elif path == "/api/incident":
            self.handle_post_incident(payload)
        elif path == "/api/voice/intent":
            self.handle_post_voice_intent(payload)
        else:
            self._send_json_response({"error": f"Unknown endpoint '{path}'"}, status=404)

    # -----------------------------------------------------------------------
    # Endpoint Handlers
    # -----------------------------------------------------------------------

    def handle_get_buildings(self):
        """GET /api/buildings: Returns list of available buildings."""
        buildings = list_available_buildings()
        self._send_json_response(
            {
                "buildings": buildings,
                "current_building_id": SESSION.current_building_id,
                "count": len(buildings),
            }
        )

    def handle_get_building_state(self, requested_id: Optional[str] = None):
        """GET /api/building/state: Returns full building geometry and operational state."""
        if requested_id:
            SESSION.load_or_switch_building(requested_id)

        building = SESSION.get_current_building()
        if not building:
            self._send_json_response({"error": "No building loaded"}, status=404)
            return

        closed_set = SESSION.get_closed_set(building.id)
        incidents = SESSION.get_incidents(building.id)

        # 1. Floors with bounding boxes
        floors_out = []
        for fid, fl in building.floors.items():
            # Calculate bbox across all spaces on this floor
            spaces_on_floor = building.spaces_by_floor.get(fid, [])
            min_x, min_y, max_x, max_y = 0.0, 0.0, 0.0, 0.0
            if spaces_on_floor:
                min_x = min(s.polygon.bounds[0] for s in spaces_on_floor)
                min_y = min(s.polygon.bounds[1] for s in spaces_on_floor)
                max_x = max(s.polygon.bounds[2] for s in spaces_on_floor)
                max_y = max(s.polygon.bounds[3] for s in spaces_on_floor)

            floors_out.append(
                {
                    "id": fl.id,
                    "level": fl.level,
                    "name": fl.name,
                    "elevation_m": fl.elevation_m,
                    "height_m": fl.height_m,
                    "bbox": [round(min_x, 3), round(min_y, 3), round(max_x, 3), round(max_y, 3)],
                }
            )

        # 2. Spaces with polygons and representative points
        spaces_out = []
        for sid, sp in building.spaces.items():
            spaces_out.append(
                {
                    "id": sp.id,
                    "floor_id": sp.floor_id,
                    "type": sp.type,
                    "room_type": sp.room_type,
                    "name": sp.name,
                    "ref": sp.ref,
                    "polygon": [[round(pt[0], 3), round(pt[1], 3)] for pt in sp.polygon_coords],
                    "area": round(sp.area, 3),
                    "representative_point": [round(sp.representative_point[0], 3), round(sp.representative_point[1], 3)],
                    "centroid": [round(sp.centroid[0], 3), round(sp.centroid[1], 3)],
                    "isOpen": sid not in closed_set,
                    "synthetic": sp.synthetic,
                }
            )

        # 3. Openings with step_free, clear width, and status
        openings_out = []
        for oid, op in building.openings.items():
            openings_out.append(
                {
                    "id": op.id,
                    "floor_id": op.floor_id,
                    "space_ids": op.space_ids,
                    "kind": op.kind,
                    "position": [round(op.position[0], 3), round(op.position[1], 3)],
                    "width_m": round(op.width_m, 3),
                    "step_free": op.step_free,
                    "isOpen": op.id not in closed_set and (DOOR_PREFIX + op.id) not in closed_set,
                    "synthetic": op.synthetic,
                }
            )

        # 4. Vertical Connectors with operational status
        connectors_out = []
        for cid, conn in building.connectors.items():
            connectors_out.append(
                {
                    "id": conn.id,
                    "kind": conn.kind,
                    "name": conn.name,
                    "floor_ids": conn.floor_ids,
                    "space_ids": conn.space_ids,
                    "step_free": conn.step_free,
                    "isOperational": conn.id not in closed_set,
                    "synthetic": conn.synthetic,
                }
            )

        # 5. Assets with footprints
        assets_out = []
        for aid, ast in building.assets.items():
            fp = None
            if ast.footprint:
                fp = {
                    "width_m": ast.footprint.width_m,
                    "depth_m": ast.footprint.depth_m,
                    "rotation_deg": ast.footprint.rotation_deg,
                }
            assets_out.append(
                {
                    "id": ast.id,
                    "name": ast.name,
                    "category": ast.category,
                    "type": ast.type,
                    "space_id": ast.space_id,
                    "floor_id": ast.floor_id,
                    "position": [round(ast.position[0], 3), round(ast.position[1], 3)],
                    "footprint": fp,
                }
            )

        self._send_json_response(
            {
                "building": {
                    "id": building.id,
                    "name": building.name,
                    "units": building.metadata.units,
                },
                "floors": floors_out,
                "spaces": spaces_out,
                "openings": openings_out,
                "vertical_connectors": connectors_out,
                "assets": assets_out,
                "closed_elements": list(closed_set),
                "active_incidents": incidents,
            }
        )

    def handle_post_route(self, payload: dict[str, Any]):
        """POST /api/route: Calculates optimal constrained route and returns 3D waypoints + landmark guidance."""
        building_id = payload.get("building")
        if building_id and building_id != SESSION.current_building_id:
            SESSION.load_or_switch_building(building_id)

        building = SESSION.get_current_building()
        if not building:
            self._send_json_response({"error": "No building loaded"}, status=404)
            return

        start_req = payload.get("start")
        dest_req = payload.get("destination") or payload.get("target")
        step_free = bool(payload.get("step_free", False))
        min_width = float(payload.get("min_width", 0.0))
        stops_req = payload.get("stops", [])

        if not start_req or not dest_req:
            self._send_json_response(
                {"error": "Both 'start' and 'destination' must be provided"}, status=400
            )
            return

        # Helper to resolve an entity to space ID
        def resolve_to_space_id(entity: str) -> Optional[str]:
            if not entity:
                return None
            ent_clean = str(entity).strip()

            # 1. Direct space ID
            if ent_clean in building.spaces:
                return ent_clean

            # 2. Asset ID
            if ent_clean in building.assets:
                return building.assets[ent_clean].space_id

            # 3. Space by ref or name
            space = building.find_space_by_ref_or_name(ent_clean)
            if space:
                return space.id

            # 4. Asset by name or type
            for asset in building.assets.values():
                if asset.name.lower() == ent_clean.lower() or asset.type.lower() == ent_clean.lower():
                    return asset.space_id

            return None

        start_sid = resolve_to_space_id(start_req)
        dest_sid = resolve_to_space_id(dest_req)

        if not start_sid:
            self._send_json_response(
                {"error": f"Start entity '{start_req}' could not be resolved to a building space"},
                status=400,
            )
            return
        if not dest_sid:
            self._send_json_response(
                {"error": f"Destination entity '{dest_req}' could not be resolved to a building space"},
                status=400,
            )
            return

        # Resolve intermediate stops
        resolved_stops = []
        for st in stops_req:
            sid = resolve_to_space_id(st)
            if sid:
                resolved_stops.append(sid)

        closed_set = SESSION.get_closed_set(building.id)

        # Chain route calculation across stops: start -> stop_1 -> ... -> destination
        all_stops = [start_sid] + resolved_stops + [dest_sid]
        total_distance = 0.0
        combined_path_nodes: list[str] = []
        combined_path_spaces: list[str] = []
        combined_path_openings: list[str] = []

        for i in range(len(all_stops) - 1):
            s_from = all_stops[i]
            s_to = all_stops[i + 1]
            leg_result = find_route(
                building,
                s_from,
                s_to,
                step_free=step_free,
                min_width=min_width,
                closed=closed_set,
            )

            if not leg_result.success:
                self._send_json_response(
                    {
                        "success": False,
                        "error_message": f"Path blocked between {s_from} and {s_to}: {leg_result.error_message}",
                        "distance_m": 0.0,
                        "waypoints": [],
                        "path_spaces": [],
                        "landmark_instructions": [
                            f"Unable to route from {s_from} to {s_to} due to operational closures or constraints."
                        ],
                    }
                )
                return

            total_distance += leg_result.distance_m

            # Merge paths without duplicate joining nodes
            if not combined_path_nodes:
                combined_path_nodes.extend(leg_result.path_nodes)
                combined_path_spaces.extend(leg_result.path_spaces)
                combined_path_openings.extend(leg_result.path_openings)
            else:
                combined_path_nodes.extend(leg_result.path_nodes[1:])
                combined_path_spaces.extend(leg_result.path_spaces[1:])
                combined_path_openings.extend(leg_result.path_openings)

        # 3D waypoints
        waypoints = compute_path_waypoints(building, combined_path_nodes)

        # Landmark directions
        instructions = generate_landmark_instructions(building, combined_path_nodes, waypoints)

        self._send_json_response(
            {
                "success": True,
                "distance_m": round(total_distance, 3),
                "path_nodes": combined_path_nodes,
                "path_spaces": combined_path_spaces,
                "path_openings": combined_path_openings,
                "waypoints": waypoints,
                "landmark_instructions": instructions,
                "vehicle_clearance_ok": True,
                "constraints": {
                    "step_free": step_free,
                    "min_width": min_width,
                },
            }
        )

    def handle_post_incident(self, payload: dict[str, Any]):
        """POST /api/incident: Toggles connectors, closures, adds synthetic doors, and checks rerouting."""
        building = SESSION.get_current_building()
        if not building:
            self._send_json_response({"error": "No building loaded"}, status=404)
            return

        action = payload.get("action", "toggle")
        target_id = payload.get("target_id", "")
        reason = payload.get("reason", "Operator report")
        severity = payload.get("severity", "warning")
        incident_type = payload.get("incident_type", "closure")
        params = payload.get("params", {})
        active_route_nodes = payload.get("active_route_nodes", [])

        closed_set = SESSION.get_closed_set(building.id)
        incidents = SESSION.get_incidents(building.id)

        # 1. Dynamic Counterfactual Door Addition
        if action == "add_door":
            space_a = params.get("space_a") or target_id
            space_b = params.get("space_b")
            width = float(params.get("width_m", 1.0))
            if not space_a or not space_b:
                self._send_json_response(
                    {"error": "add_door requires 'space_a' and 'space_b'"}, status=400
                )
                return

            new_door = SESSION.add_synthetic_door(space_a, space_b, width_m=width)
            if not new_door:
                self._send_json_response(
                    {
                        "success": False,
                        "error": f"Spaces {space_a} and {space_b} are not adjacent on the same floor",
                    },
                    status=400,
                )
                return

            incidents.append(
                {
                    "id": f"INC-DOOR-{len(incidents) + 1}",
                    "type": "add_door",
                    "target_id": new_door.id,
                    "spaces": [space_a, space_b],
                    "reason": reason or "Synthetic emergency door added",
                    "severity": "info",
                    "active": True,
                }
            )

            self._send_json_response(
                {
                    "success": True,
                    "action": "add_door",
                    "new_door": {
                        "id": new_door.id,
                        "floor_id": new_door.floor_id,
                        "space_ids": new_door.space_ids,
                        "position": [new_door.position[0], new_door.position[1]],
                        "width_m": new_door.width_m,
                    },
                    "active_incidents": incidents,
                    "closed_elements": list(closed_set),
                }
            )
            return

        # 2. Toggle or set closed status
        if not target_id:
            self._send_json_response({"error": "Missing 'target_id'"}, status=400)
            return

        is_now_closed = False
        if action == "close" or action == "report":
            closed_set.add(target_id)
            is_now_closed = True
        elif action == "open":
            closed_set.discard(target_id)
            is_now_closed = False
        elif action == "toggle":
            if target_id in closed_set:
                closed_set.remove(target_id)
                is_now_closed = False
            else:
                closed_set.add(target_id)
                is_now_closed = True

        # Update or record incident
        existing_inc = next((inc for inc in incidents if inc["target_id"] == target_id), None)
        if is_now_closed:
            if existing_inc:
                existing_inc["active"] = True
                existing_inc["reason"] = reason
            else:
                incidents.append(
                    {
                        "id": f"INC-{len(incidents) + 1}",
                        "type": incident_type,
                        "target_id": target_id,
                        "reason": reason,
                        "severity": severity,
                        "active": True,
                    }
                )
        else:
            if existing_inc:
                existing_inc["active"] = False

        # Check if active navigation route is affected
        reroute_needed = False
        if active_route_nodes:
            for node in active_route_nodes:
                if node == target_id or (node.startswith(DOOR_PREFIX) and node[len(DOOR_PREFIX) :] == target_id):
                    reroute_needed = True
                    break

        self._send_json_response(
            {
                "success": True,
                "action": action,
                "target_id": target_id,
                "is_closed": is_now_closed,
                "closed_elements": list(closed_set),
                "active_incidents": [inc for inc in incidents if inc.get("active", True)],
                "reroute_needed": reroute_needed,
            }
        )

    def handle_post_voice_intent(self, payload: dict[str, Any]):
        """POST /api/voice/intent: NLP parsing, ambiguity clarification, incident speech handling."""
        transcript = payload.get("transcript", "").strip()
        current_space = payload.get("current_space")
        building = SESSION.get_current_building()
        if not building:
            self._send_json_response({"error": "No building loaded"}, status=404)
            return

        # 1. Check for incident speech commands
        # Example: "Elevator V01 is down", "Close staircase V02", "Corridor F0-S016 is blocked"
        t_lower = transcript.lower()
        incident_match = re.search(
            r"(?:the\s+)?(.+?)\s+(?:is\s+)?(down|broken|blocked|closed|stuck|hazardous|out of service)",
            t_lower,
        )
        if incident_match:
            raw_target = incident_match.group(1).strip()
            # Try to match connector or space
            matched_id = None
            for cid, conn in building.connectors.items():
                if raw_target in conn.name.lower() or raw_target in cid.lower():
                    matched_id = cid
                    break
            if not matched_id:
                for sid, sp in building.spaces.items():
                    if raw_target in sp.name.lower() or raw_target in sid.lower() or raw_target == (sp.ref or "").lower():
                        matched_id = sid
                        break

            if matched_id:
                closed_set = SESSION.get_closed_set(building.id)
                closed_set.add(matched_id)
                incidents = SESSION.get_incidents(building.id)
                incidents.append(
                    {
                        "id": f"INC-VOICE-{len(incidents) + 1}",
                        "type": "voice_reported_closure",
                        "target_id": matched_id,
                        "reason": f"Voice report: '{transcript}'",
                        "severity": "critical",
                        "active": True,
                    }
                )
                self._send_json_response(
                    {
                        "intent": "REPORT_INCIDENT",
                        "prompt": f"Alert registered: {raw_target} is reported closed. The topological map has been updated.",
                        "target_id": matched_id,
                        "action": "close",
                        "closed_elements": list(closed_set),
                    }
                )
                return

        # 2. Check for synthetic door creation speech
        # Example: "Open door between room 1 and room 2", "Add door between H-A1 and H-A2"
        door_match = re.search(
            r"(?:add|open|create)\s+(?:a\s+)?door\s+between\s+(.+?)\s+and\s+(.+)", t_lower
        )
        if door_match:
            cand_a = door_match.group(1).strip()
            cand_b = door_match.group(2).strip()
            sp_a = building.find_space_by_ref_or_name(cand_a)
            sp_b = building.find_space_by_ref_or_name(cand_b)
            if sp_a and sp_b:
                new_door = SESSION.add_synthetic_door(sp_a.id, sp_b.id)
                if new_door:
                    self._send_json_response(
                        {
                            "intent": "ADD_DOOR",
                            "prompt": f"Synthetic door successfully added between {sp_a.name} and {sp_b.name}.",
                            "door_id": new_door.id,
                        }
                    )
                    return
                else:
                    self._send_json_response(
                        {
                            "intent": "ADD_DOOR",
                            "prompt": f"Could not create door: {sp_a.name} and {sp_b.name} are not adjacent on the same floor level.",
                        }
                    )
                    return

        # 3. Standard Navigation Query & Ambiguity Clarification
        clarify_res = clarify_query(transcript, building)

        if clarify_res["ambiguous"]:
            self._send_json_response(
                {
                    "intent": "CLARIFY",
                    "prompt": clarify_res["prompt"],
                    "ambiguous": True,
                    "count": clarify_res["count"],
                    "candidates": clarify_res["candidates"],
                }
            )
            return

        if clarify_res.get("target_id") or clarify_res.get("target_space_id"):
            dest_space_id = clarify_res.get("target_space_id")
            # Determine start space
            start_space_id = current_space or list(building.spaces.keys())[0]

            closed_set = SESSION.get_closed_set(building.id)
            route = find_route(
                building,
                start_space_id,
                dest_space_id,
                step_free=clarify_res.get("step_free", False),
                min_width=clarify_res.get("min_width", 0.0),
                closed=closed_set,
            )

            waypoints = compute_path_waypoints(building, route.path_nodes) if route.success else []
            instructions = (
                generate_landmark_instructions(building, route.path_nodes, waypoints)
                if route.success
                else [route.error_message or "Path blocked."]
            )

            self._send_json_response(
                {
                    "intent": "NAVIGATE",
                    "prompt": clarify_res["prompt"],
                    "ambiguous": False,
                    "target_name": clarify_res.get("target_name"),
                    "route": {
                        "success": route.success,
                        "distance_m": round(route.distance_m, 2),
                        "path_nodes": route.path_nodes,
                        "waypoints": waypoints,
                        "landmark_instructions": instructions,
                    },
                }
            )
            return

        # Default fallback
        self._send_json_response(
            {
                "intent": "UNKNOWN",
                "prompt": clarify_res.get(
                    "prompt", "I didn't understand the request. Please ask for a destination or incident report."
                ),
            }
        )


def run_server(host: str = "0.0.0.0", port: int = 8000, default_building: Optional[str] = None):
    """Start the ThreadingHTTPServer."""
    if default_building:
        SESSION.load_or_switch_building(default_building)

    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, BuildingAPIRequestHandler)
    print(f"=================================================================")
    print(f"Talk to Your Building — Industrial Digital Twin & Visualizer")
    print(f"Server active at: http://localhost:{port}/")
    print(f"Serving 3D visualizer from: {VISUALIZER_DIR}")
    print(f"Active building: {SESSION.current_building_id}")
    print(f"=================================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer shutting down gracefully.")
        httpd.server_close()


def main():
    parser = argparse.ArgumentParser(
        description="Run the Talk to Your Building visualizer & REST API server"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host interface (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument(
        "--building",
        default="proc-factory-dev-003",
        help="Building ID or directory to load by default",
    )
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, default_building=args.building)


if __name__ == "__main__":
    main()
