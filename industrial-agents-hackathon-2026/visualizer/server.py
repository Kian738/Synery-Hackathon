"""Standard library ThreadingHTTPServer REST API backend for Talk to Your Building visualizer.

Provides endpoints for building geometry, multi-floor routing with 3D paths,
live closure dispatching, synthetic door creation, natural language voice command parsing,
and static dashboard file delivery with zero external dependencies.
"""

from __future__ import annotations

import json
import math
import mimetypes
import os
import re
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional, Union

from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points

from spatial_engine.building_loader import load_building
from spatial_engine.graph import DOOR_PREFIX, OUTSIDE_NODE, build_routing_graph
from spatial_engine.models import Building, Connector, Floor, Opening, Space
from spatial_engine.router import find_route, RouteResult, count_reachable_rooms


class VisualizerService:
    """Core state and spatial logic service backing the Visualizer REST API."""

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        initial_building_path: Optional[Path] = None,
    ) -> None:
        self.base_dir = (base_dir or Path.cwd()).resolve()
        self.static_dir = (Path(__file__).parent / "static").resolve()
        self.lock = threading.RLock()

        self.available_buildings: dict[str, Path] = {}
        self.current_building: Optional[Building] = None
        self.current_building_path: Optional[Path] = None
        self.closed_ids: set[str] = set()
        self.synthetic_openings: list[Opening] = []

        self._discover_buildings()

        # Load initial building
        if initial_building_path and Path(initial_building_path).exists():
            self.load_building_by_path(Path(initial_building_path))
        elif "proc-factory-dev-003" in self.available_buildings:
            self.load_building_by_id("proc-factory-dev-003")
        elif self.available_buildings:
            first_id = next(iter(self.available_buildings))
            self.load_building_by_id(first_id)

    def _discover_buildings(self) -> None:
        """Scan data/dev and data/test for building directories containing building.json."""
        candidate_dirs = [
            self.base_dir / "data" / "dev",
            self.base_dir / "data" / "test",
            self.base_dir / "data",
        ]
        for parent in candidate_dirs:
            if not parent.is_dir():
                continue
            for entry in parent.iterdir():
                if entry.is_dir() and (entry / "building.json").exists():
                    self.available_buildings[entry.name] = entry

    def list_buildings(self) -> list[dict[str, Any]]:
        """Return summary list of all discovered buildings."""
        with self.lock:
            results = []
            for b_id, b_path in sorted(self.available_buildings.items()):
                json_path = b_path / "building.json"
                floor_count = 0
                space_count = 0
                name = b_id
                split = "dev" if "dev" in b_path.parts else "test"
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    name = data.get("name", b_id)
                    floor_count = len(data.get("floors", []))
                    space_count = len(data.get("spaces", []))
                except Exception:
                    pass

                results.append(
                    {
                        "id": b_id,
                        "name": name,
                        "floors": floor_count,
                        "spaces": space_count,
                        "path": str(b_path),
                        "split": split,
                        "is_active": (
                            self.current_building is not None
                            and self.current_building.id == b_id
                        ),
                    }
                )
            return results

    def load_building_by_path(self, path: Path) -> Building:
        """Load a building from a directory path."""
        with self.lock:
            b = load_building(path)
            self.current_building = b
            self.current_building_path = path.resolve()
            self.available_buildings[b.id] = path.resolve()
            self.closed_ids.clear()
            self.synthetic_openings.clear()
            return b

    def load_building_by_id(self, building_id: str) -> Building:
        """Switch current building by ID."""
        with self.lock:
            if building_id in self.available_buildings:
                return self.load_building_by_path(self.available_buildings[building_id])
            # Check if building_id matches directory name
            for b_id, b_path in self.available_buildings.items():
                if b_id.lower() == building_id.lower():
                    return self.load_building_by_path(b_path)
            raise ValueError(f"Building '{building_id}' not found in available datasets")

    def get_building_data(self, building_id: Optional[str] = None) -> dict[str, Any]:
        """Serialize full building geometry, openings, connectors, assets, and closures."""
        with self.lock:
            if building_id and (
                self.current_building is None or self.current_building.id != building_id
            ):
                self.load_building_by_id(building_id)

            if not self.current_building:
                raise RuntimeError("No building is currently loaded")

            b = self.current_building

            # Floor list sorted by elevation
            floors_data = [
                {
                    "id": f.id,
                    "level": f.level,
                    "name": f.name,
                    "elevation_m": f.elevation_m,
                    "height_m": f.height_m,
                }
                for f in sorted(b.floors.values(), key=lambda fl: (fl.level, fl.elevation_m))
            ]

            # Spaces
            spaces_data = [
                {
                    "id": s.id,
                    "floor_id": s.floor_id,
                    "type": s.type,
                    "room_type": s.room_type,
                    "name": s.name,
                    "ref": s.ref,
                    "polygon": s.polygon_coords,
                    "area": round(s.area, 2),
                    "centroid": [round(s.centroid[0], 3), round(s.centroid[1], 3)],
                    "representative_point": [
                        round(s.representative_point[0], 3),
                        round(s.representative_point[1], 3),
                    ],
                    "synthetic": getattr(s, "synthetic", False),
                    "is_closed": s.id in self.closed_ids,
                }
                for s in b.spaces.values()
            ]

            # Openings
            openings_data = [
                {
                    "id": o.id,
                    "floor_id": o.floor_id,
                    "space_ids": o.space_ids,
                    "kind": o.kind,
                    "position": [round(o.position[0], 3), round(o.position[1], 3)],
                    "width_m": round(o.width_m, 2),
                    "step_free": o.step_free,
                    "synthetic": getattr(o, "synthetic", False),
                    "is_closed": o.id in self.closed_ids,
                }
                for o in b.openings.values()
            ]

            # Connectors
            connectors_data = [
                {
                    "id": c.id,
                    "kind": c.kind,
                    "name": c.name,
                    "floor_ids": c.floor_ids,
                    "space_ids": c.space_ids,
                    "step_free": c.step_free,
                    "synthetic": getattr(c, "synthetic", False),
                    "is_closed": c.id in self.closed_ids,
                }
                for c in b.connectors.values()
            ]

            # Assets
            assets_data = [
                {
                    "id": a.id,
                    "name": a.name,
                    "category": a.category,
                    "type": a.type,
                    "space_id": a.space_id,
                    "floor_id": a.floor_id,
                    "position": [round(a.position[0], 3), round(a.position[1], 3)],
                    "footprint": (
                        {
                            "width_m": a.footprint.width_m,
                            "depth_m": a.footprint.depth_m,
                            "rotation_deg": a.footprint.rotation_deg,
                        }
                        if a.footprint
                        else None
                    ),
                }
                for a in b.assets.values()
            ]

            return {
                "status": "ok",
                "building": {
                    "id": b.id,
                    "name": b.name,
                    "source": b.metadata.source,
                    "units": b.metadata.units,
                    "floors": floors_data,
                    "spaces": spaces_data,
                    "openings": openings_data,
                    "connectors": connectors_data,
                    "assets": assets_data,
                    "closed": sorted(list(self.closed_ids)),
                },
            }

    def calculate_route(
        self,
        start: str,
        destination: str,
        step_free: bool = False,
        min_width: Optional[float] = None,
        closed: Optional[list[str]] = None,
        via: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Calculate optimal route and return distance, node sequence, and 3D path coordinates."""
        with self.lock:
            if not self.current_building:
                raise RuntimeError("No building is currently loaded")

            b = self.current_building
            active_closed = set(self.closed_ids)
            if closed:
                active_closed.update(closed)

            try:
                res: RouteResult = find_route(
                    building=b,
                    start=start,
                    destination=destination,
                    step_free=step_free,
                    min_width=min_width,
                    closed=active_closed,
                    via=via,
                )
            except Exception as e:
                return {
                    "status": "no_path",
                    "error": str(e),
                    "distance": 0.0,
                    "length_m": 0.0,
                    "path": [],
                    "space_path": [],
                    "points_3d": [],
                    "steps": [f"No path found: {e}"],
                    "start": start,
                    "destination": destination,
                    "step_free": step_free,
                    "closed": sorted(list(active_closed)),
                }

            # Build 3D polyline coordinates: [[x, y, z], ...]
            # z is floor elevation + vertical offset for walking level
            points_3d: list[list[float]] = []

            for node in res.path:
                if node.startswith(DOOR_PREFIX):
                    op_id = node[len(DOOR_PREFIX) :]
                    opening = b.openings.get(op_id)
                    if opening:
                        fl = b.floors.get(opening.floor_id)
                        z = fl.elevation_m if fl else 0.0
                        points_3d.append(
                            [
                                round(opening.position[0], 3),
                                round(opening.position[1], 3),
                                round(z + 0.35, 3),
                            ]
                        )
                elif node == OUTSIDE_NODE:
                    # Keep previous coordinate if exists
                    if points_3d:
                        points_3d.append(list(points_3d[-1]))
                else:
                    # Space representative point
                    space = b.spaces.get(node)
                    if space:
                        fl = b.floors.get(space.floor_id)
                        z = fl.elevation_m if fl else 0.0
                        pos = space.representative_point
                        pt = [round(pos[0], 3), round(pos[1], 3), round(z + 0.35, 3)]

                        # Check if vertical transition occurred between consecutive space nodes
                        if points_3d and abs(points_3d[-1][2] - pt[2]) > 0.5:
                            # Add vertical shaft transition point
                            prev = points_3d[-1]
                            points_3d.append([prev[0], prev[1], pt[2]])

                        points_3d.append(pt)

            return {
                "status": "ok",
                "distance": res.distance,
                "length_m": res.length_m,
                "path": res.path,
                "space_path": res.space_path,
                "points_3d": points_3d,
                "steps": res.steps,
                "start": res.start_node,
                "destination": res.end_node,
                "step_free": step_free,
                "closed": sorted(list(active_closed)),
            }

    def toggle_closure(
        self,
        element: Optional[str] = None,
        is_closed: Optional[bool] = None,
        closed_list: Optional[list[str]] = None,
        reset: bool = False,
    ) -> dict[str, Any]:
        """Toggle or set closed status of connectors, spaces, or openings."""
        with self.lock:
            if not self.current_building:
                raise RuntimeError("No building is currently loaded")

            b = self.current_building

            if reset:
                self.closed_ids.clear()
            elif closed_list is not None:
                self.closed_ids = set(closed_list)
            elif element:
                # Find matching target ID by name or ref
                target_id = element
                # Check direct match
                if target_id not in b.connectors and target_id not in b.spaces and target_id not in b.openings:
                    # Search by connector name
                    for c in b.connectors.values():
                        if c.name.lower() == element.lower() or c.id.lower() == element.lower():
                            target_id = c.id
                            break
                    else:
                        # Search by space ref or name
                        sp = b.find_space_by_ref_or_name(element)
                        if sp:
                            target_id = sp.id

                if is_closed is None:
                    if target_id in self.closed_ids:
                        self.closed_ids.remove(target_id)
                    else:
                        self.closed_ids.add(target_id)
                else:
                    if is_closed:
                        self.closed_ids.add(target_id)
                    else:
                        self.closed_ids.discard(target_id)

            # Compute reachability summary
            closed_spaces = [s for s in self.closed_ids if s in b.spaces]
            closed_connectors = [c for c in self.closed_ids if c in b.connectors]
            closed_openings = [o for o in self.closed_ids if o in b.openings]

            return {
                "status": "ok",
                "closed": sorted(list(self.closed_ids)),
                "reachability": {
                    "total_spaces": len(b.spaces),
                    "active_spaces": len(b.spaces) - len(closed_spaces),
                    "closed_spaces_count": len(closed_spaces),
                    "closed_connectors_count": len(closed_connectors),
                    "closed_openings_count": len(closed_openings),
                },
            }

    def add_synthetic_door(
        self, space_a_id: str, space_b_id: str, step_free: bool = True
    ) -> dict[str, Any]:
        """Add a synthetic door between two adjacent rooms if distance <= 0.6 m."""
        with self.lock:
            if not self.current_building:
                raise RuntimeError("No building is currently loaded")

            b = self.current_building

            # Resolve space identifiers
            sp_a = b.find_space_by_ref_or_name(space_a_id) or b.get_space(space_a_id)
            sp_b = b.find_space_by_ref_or_name(space_b_id) or b.get_space(space_b_id)

            if not sp_a:
                raise ValueError(f"Space '{space_a_id}' not found in building")
            if not sp_b:
                raise ValueError(f"Space '{space_b_id}' not found in building")

            # Check geometric distance between polygon boundaries
            poly_a = sp_a.polygon
            poly_b = sp_b.polygon
            dist = poly_a.distance(poly_b)

            if dist > 0.60001:
                return {
                    "status": "error",
                    "error": (
                        f"Rooms '{sp_a.name or sp_a.id}' and '{sp_b.name or sp_b.id}' "
                        f"are separated by {dist:.3f} m (> 0.6 m threshold) and cannot be joined"
                    ),
                    "distance_m": round(dist, 3),
                }

            # Calculate door position at midpoint between nearest boundary points
            p_a, p_b = nearest_points(poly_a, poly_b)
            door_x = round((p_a.x + p_b.x) / 2.0, 3)
            door_y = round((p_a.y + p_b.y) / 2.0, 3)

            door_idx = len(b.openings) + 1
            door_id = f"door_synthetic_{door_idx}"

            new_opening = Opening(
                id=door_id,
                floor_id=sp_a.floor_id,
                space_ids=[sp_a.id, sp_b.id],
                kind="door",
                position=(door_x, door_y),
                width_m=1.0,
                step_free=step_free,
                synthetic=True,
            )

            # Update Building model indices in place
            b.openings[door_id] = new_opening
            if sp_a.id not in b.openings_by_space:
                b.openings_by_space[sp_a.id] = []
            b.openings_by_space[sp_a.id].append(new_opening)

            if sp_b.id not in b.openings_by_space:
                b.openings_by_space[sp_b.id] = []
            b.openings_by_space[sp_b.id].append(new_opening)

            if sp_a.floor_id not in b.openings_by_floor:
                b.openings_by_floor[sp_a.floor_id] = []
            b.openings_by_floor[sp_a.floor_id].append(new_opening)

            self.synthetic_openings.append(new_opening)

            return {
                "status": "ok",
                "door_id": door_id,
                "position": [door_x, door_y],
                "floor_id": sp_a.floor_id,
                "space_a": sp_a.id,
                "space_b": sp_b.id,
                "width_m": 1.0,
                "step_free": step_free,
                "distance_m": round(dist, 3),
            }

    def process_voice_command(self, transcript: str) -> dict[str, Any]:
        """Parse spoken or typed natural language commands into deterministic dispatch actions."""
        text = transcript.strip().lower()
        if not text:
            return {
                "intent": "empty",
                "response_text": "No speech detected. Please speak into the microphone or type a command.",
                "action": {"type": "none"},
            }

        with self.lock:
            b = self.current_building

        # 1. Navigation / Route commands: "take me to...", "navigate to...", "go to...", "route from A to B"
        nav_match = (
            re.search(r"(?:take me to|navigate to|go to|route to|how do i get to)\s+(.+)", text)
            or re.search(r"route from\s+(.+?)\s+to\s+(.+)", text)
        )
        if nav_match:
            groups = nav_match.groups()
            if len(groups) == 2:
                start_ref, dest_ref = groups[0].strip(), groups[1].strip()
            else:
                start_ref, dest_ref = None, groups[0].strip()

            dest_space = None
            if b:
                dest_space = b.find_space_by_ref_or_name(dest_ref)
                if not dest_space:
                    # Try matching asset
                    for a in b.assets.values():
                        if dest_ref in a.name.lower() or dest_ref in a.type.lower():
                            dest_space = b.spaces.get(a.space_id)
                            break
                if not dest_space:
                    # Match by room_type substring
                    for s in b.spaces.values():
                        if dest_ref in s.room_type.lower() or dest_ref in s.name.lower():
                            dest_space = s
                            break

            dest_id = dest_space.id if dest_space else dest_ref
            dest_name = (dest_space.name or dest_space.ref or dest_id) if dest_space else dest_ref

            return {
                "intent": "navigate",
                "response_text": f"Navigating to {dest_name}. Calculating optimal path.",
                "action": {
                    "type": "route",
                    "destination": dest_id,
                    "destination_name": dest_name,
                    "start": start_ref,
                },
            }

        # 2. Closures: "close lift...", "block stair...", "close room..."
        close_match = re.search(r"(?:close|block|shut|disable)\s+(.+)", text)
        if close_match:
            elem_query = close_match.group(1).strip()
            elem_id = elem_query
            elem_name = elem_query
            if b:
                # Check connectors
                for c in b.connectors.values():
                    if elem_query in c.name.lower() or elem_query in c.kind.lower() or elem_query in c.id.lower():
                        elem_id = c.id
                        elem_name = c.name or c.id
                        break
                else:
                    sp = b.find_space_by_ref_or_name(elem_query)
                    if sp:
                        elem_id = sp.id
                        elem_name = sp.name or sp.ref or sp.id

            self.toggle_closure(element=elem_id, is_closed=True)
            return {
                "intent": "close",
                "response_text": f"Closed {elem_name}. Recomputing active navigation paths.",
                "action": {"type": "close", "element": elem_id, "name": elem_name},
            }

        # 3. Openings / Reopen: "open lift...", "unblock..."
        open_match = re.search(r"(?:open|unblock|enable|reopen)\s+(.+)", text)
        if open_match:
            elem_query = open_match.group(1).strip()
            elem_id = elem_query
            elem_name = elem_query
            if b:
                for c in b.connectors.values():
                    if elem_query in c.name.lower() or elem_query in c.kind.lower():
                        elem_id = c.id
                        elem_name = c.name or c.id
                        break
                else:
                    sp = b.find_space_by_ref_or_name(elem_query)
                    if sp:
                        elem_id = sp.id
                        elem_name = sp.name or sp.ref or sp.id

            self.toggle_closure(element=elem_id, is_closed=False)
            return {
                "intent": "open",
                "response_text": f"Reopened {elem_name}.",
                "action": {"type": "open", "element": elem_id, "name": elem_name},
            }

        # 4. Find nearest asset / room: "find nearest fire extinguisher", "where is nearest..."
        find_match = re.search(
            r"(?:find|locate|where is)(?:\s+the)?(?:\s+nearest|\s+closest)?\s+(.+)", text
        )
        if find_match:
            target_query = find_match.group(1).strip()
            matched_asset = None
            if b:
                for a in b.assets.values():
                    if (
                        target_query in a.type.lower()
                        or target_query in a.name.lower()
                        or target_query in a.category.lower()
                    ):
                        matched_asset = a
                        break

            if matched_asset and b:
                sp = b.spaces.get(matched_asset.space_id)
                fl = b.floors.get(matched_asset.floor_id)
                fl_name = fl.name if fl else matched_asset.floor_id
                sp_name = sp.name or sp.ref if sp else matched_asset.space_id
                return {
                    "intent": "find_nearest",
                    "response_text": (
                        f"Nearest {matched_asset.name or matched_asset.type} is in "
                        f"{sp_name} on {fl_name}."
                    ),
                    "action": {
                        "type": "locate",
                        "asset_id": matched_asset.id,
                        "space_id": matched_asset.space_id,
                        "floor_id": matched_asset.floor_id,
                        "position": [
                            matched_asset.position[0],
                            matched_asset.position[1],
                            fl.elevation_m if fl else 0.0,
                        ],
                    },
                }

        # 5. Floor Switching: "show floor 1", "go to level 0", "ground floor"
        floor_match = re.search(
            r"(?:show|go to|view|display|switch to)?\s*(?:floor|level)\s*(-?\d+|ground|first|second|basement)",
            text,
        )
        if floor_match:
            raw_lvl = floor_match.group(1).strip()
            level_map = {"ground": 0, "first": 1, "second": 2, "basement": -1}
            target_lvl = level_map.get(raw_lvl)
            if target_lvl is None:
                try:
                    target_lvl = int(raw_lvl)
                except ValueError:
                    target_lvl = 0

            return {
                "intent": "switch_floor",
                "response_text": f"Switching camera to Floor level {target_lvl}.",
                "action": {"type": "set_floor", "level": target_lvl},
            }

        # 6. Exploded / View Mode: "explode", "exploded view", "3d view", "2d view"
        if "explode" in text or "expand floors" in text:
            return {
                "intent": "view_mode",
                "response_text": "Activating exploded multi-floor view.",
                "action": {"type": "set_exploded", "value": 2.5},
            }
        if "collapse" in text or "stack floors" in text or "reset view" in text:
            return {
                "intent": "view_mode",
                "response_text": "Resetting floor vertical spacing to stacked view.",
                "action": {"type": "set_exploded", "value": 1.0},
            }
        if "2d" in text or "top down" in text:
            return {
                "intent": "view_mode",
                "response_text": "Switching to 2D top-down view.",
                "action": {"type": "set_view", "mode": "2d"},
            }
        if "3d" in text or "perspective" in text:
            return {
                "intent": "view_mode",
                "response_text": "Switching to 3D perspective view.",
                "action": {"type": "set_view", "mode": "3d"},
            }

        # 7. Add door command: "add door between A and B"
        door_cmd_match = re.search(r"add door between\s+(.+?)\s+and\s+(.+)", text)
        if door_cmd_match:
            room_a, room_b = door_cmd_match.group(1).strip(), door_cmd_match.group(2).strip()
            return {
                "intent": "add_door",
                "response_text": f"Attempting to add synthetic door between {room_a} and {room_b}.",
                "action": {"type": "add_door", "space_a": room_a, "space_b": room_b},
            }

        # 8. Help / Default
        return {
            "intent": "help" if "help" in text else "unknown",
            "response_text": (
                "You can say: 'Take me to [Room]', 'Close East Lift', "
                "'Find nearest fire extinguisher', 'Show Floor 1', or 'Explode floors'."
            ),
            "action": {"type": "help"},
        }


class VisualizerRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler implementing the Visualizer REST API and static asset delivery."""

    service: VisualizerService

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard log spam unless requested."""
        if os.environ.get("VISUALIZER_VERBOSE") == "1":
            super().log_message(format, *args)

    def _send_json(self, status_code: int, data: Any) -> None:
        """Send JSON response with CORS headers."""
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        """Read and parse JSON request body."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw)
        except Exception as e:
            raise ValueError(f"Invalid JSON request body: {e}")

    def do_OPTIONS(self) -> None:
        """Handle preflight CORS requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """Route GET requests to API endpoints or static files."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. API: List buildings
        if path == "/api/buildings":
            try:
                buildings = self.service.list_buildings()
                self._send_json(200, {"status": "ok", "buildings": buildings})
            except Exception as e:
                self._send_json(500, {"status": "error", "error": str(e)})
            return

        # 2. API: Get building data
        if path == "/api/building":
            b_id = query.get("id", [None])[0]
            try:
                data = self.service.get_building_data(building_id=b_id)
                self._send_json(200, data)
            except Exception as e:
                self._send_json(404, {"status": "error", "error": str(e)})
            return

        # 3. Static files
        self._serve_static_file(path)

    def do_POST(self) -> None:
        """Route POST requests to spatial calculation endpoints."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            body = self._read_json_body()
        except ValueError as err:
            self._send_json(400, {"status": "error", "error": str(err)})
            return

        # 1. API: Calculate route
        if path == "/api/route":
            start = body.get("start")
            destination = body.get("destination") or body.get("end")
            if not start or not destination:
                self._send_json(
                    400,
                    {
                        "status": "error",
                        "error": "Both 'start' and 'destination' must be specified",
                    },
                )
                return

            step_free = bool(body.get("step_free", False))
            min_width = body.get("min_width")
            closed = body.get("closed")
            via = body.get("via")

            result = self.service.calculate_route(
                start=str(start),
                destination=str(destination),
                step_free=step_free,
                min_width=float(min_width) if min_width is not None else None,
                closed=list(closed) if closed else None,
                via=list(via) if via else None,
            )
            self._send_json(200, result)
            return

        # 2. API: Closures toggle
        if path in ("/api/closures", "/api/closure"):
            element = body.get("element") or body.get("id")
            is_closed = body.get("closed")
            closed_list = body.get("closed_list") or (
                body.get("closed") if isinstance(body.get("closed"), list) else None
            )
            reset = bool(body.get("reset", False))

            result = self.service.toggle_closure(
                element=str(element) if element else None,
                is_closed=bool(is_closed) if isinstance(is_closed, bool) else None,
                closed_list=closed_list,
                reset=reset,
            )
            self._send_json(200, result)
            return

        # 3. API: Add synthetic door
        if path in ("/api/door", "/api/add_door"):
            space_a = body.get("space_a") or body.get("first_space")
            space_b = body.get("space_b") or body.get("second_space")
            if not space_a or not space_b:
                self._send_json(
                    400,
                    {
                        "status": "error",
                        "error": "Both 'space_a' and 'space_b' are required",
                    },
                )
                return

            step_free = bool(body.get("step_free", True))
            try:
                result = self.service.add_synthetic_door(
                    space_a_id=str(space_a),
                    space_b_id=str(space_b),
                    step_free=step_free,
                )
                if result.get("status") == "error":
                    self._send_json(400, result)
                else:
                    self._send_json(200, result)
            except Exception as e:
                self._send_json(400, {"status": "error", "error": str(e)})
            return

        # 4. API: Voice command parsing
        if path in ("/api/voice_command", "/api/chat"):
            transcript = body.get("transcript") or body.get("message") or ""
            result = self.service.process_voice_command(transcript=str(transcript))
            self._send_json(200, result)
            return

        self._send_json(404, {"status": "error", "error": f"Endpoint '{path}' not found"})

    def _serve_static_file(self, req_path: str) -> None:
        """Serve files from static_dir with path containment and proper MIME type."""
        clean_path = req_path.lstrip("/")
        if not clean_path or clean_path == "/":
            clean_path = "index.html"

        target_file = (self.service.static_dir / clean_path).resolve()

        # Security check: ensure path is inside static_dir
        try:
            target_file.relative_to(self.service.static_dir)
        except ValueError:
            self._send_json(403, {"status": "error", "error": "Access denied"})
            return

        if not target_file.is_file():
            # If not found, fall back to index.html for SPA client-side routing
            index_file = self.service.static_dir / "index.html"
            if index_file.is_file():
                target_file = index_file
            else:
                self._send_json(404, {"status": "error", "error": f"File '{clean_path}' not found"})
                return

        mime_type, _ = mimetypes.guess_type(str(target_file))
        if not mime_type:
            mime_type = "application/octet-stream"
        if mime_type.startswith("text/") or mime_type in (
            "application/javascript",
            "application/json",
        ):
            mime_type += "; charset=utf-8"

        try:
            with open(target_file, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_json(500, {"status": "error", "error": f"Error reading file: {e}"})


class VisualizerServer(ThreadingHTTPServer):
    """Threaded HTTP Server configured with visualizer service."""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        service: VisualizerService,
    ) -> None:
        VisualizerRequestHandler.service = service
        super().__init__(server_address, VisualizerRequestHandler)
        self.service = service


def create_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    initial_building_dir: Optional[Union[str, Path]] = None,
    base_dir: Optional[Union[str, Path]] = None,
) -> VisualizerServer:
    """Create and return a configured VisualizerServer instance."""
    init_path = Path(initial_building_dir) if initial_building_dir else None
    base = Path(base_dir) if base_dir else None
    service = VisualizerService(base_dir=base, initial_building_path=init_path)
    return VisualizerServer((host, port), service)
