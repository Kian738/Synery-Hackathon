"""Test Helpers, Authoritative Reference Oracle, and Test Fixtures.

Provides authoritative mathematical references for expected output derivation,
dataset loaders, benchmark scoring helpers, and REST API test harnesses.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx
from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points

# Base Directories
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEV_DATA_DIR = PROJECT_ROOT / "data" / "dev"
TEST_DATA_DIR = PROJECT_ROOT / "data" / "test"
TRAIN_DATA_DIR = PROJECT_ROOT / "data" / "train"

# Representative Sample Buildings
BUILDING_FACTORY_003 = DEV_DATA_DIR / "proc-factory-dev-003"
BUILDING_FACTORY_012 = DEV_DATA_DIR / "proc-factory-dev-012"
BUILDING_CAMPUS_000 = DEV_DATA_DIR / "proc-campus-dev-000"
BUILDING_RESPLAN_3832 = DEV_DATA_DIR / "resplan-3832"
BUILDING_OSM_22744230 = DEV_DATA_DIR / "osm-way22744230"
BUILDING_OSM_27917482 = DEV_DATA_DIR / "osm-way27917482"

DOOR_PREFIX = "door:"
OUTSIDE_NODE = "outside"


def load_building_json(building_dir_or_file: Path | str) -> dict[str, Any]:
    """Loads building.json from a building directory or direct file path."""
    p = Path(building_dir_or_file)
    file_path = p / "building.json" if p.is_dir() else p
    if not file_path.exists():
        raise FileNotFoundError(f"Building file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


class ReferenceOracle:
    """Authoritative mathematical reference oracle for spatial reasoning and routing."""

    @staticmethod
    def room_area(space: dict[str, Any]) -> float:
        """Computes polygon area in square metres."""
        poly = Polygon(space["polygon"])
        return float(poly.area)

    @staticmethod
    def floor_area_total(building_data: dict[str, Any], floor_id: str, room_type: str) -> float:
        """Computes aggregate polygon surface area for all rooms of room_type on floor_id."""
        total = 0.0
        for s in building_data.get("spaces", []):
            if s.get("floor_id") == floor_id and s.get("room_type") == room_type:
                total += Polygon(s["polygon"]).area
        return float(total)

    @staticmethod
    def largest_room(building_data: dict[str, Any], floor_id: str, room_type: str) -> tuple[dict[str, Any], float]:
        """Finds room of room_type on floor_id with maximum polygon area."""
        candidates = [
            s for s in building_data.get("spaces", [])
            if s.get("floor_id") == floor_id and s.get("room_type") == room_type
        ]
        if not candidates:
            raise ValueError(f"No spaces matching floor_id={floor_id} and room_type={room_type}")
        best_space = max(candidates, key=lambda s: Polygon(s["polygon"]).area)
        return best_space, float(Polygon(best_space["polygon"]).area)

    @staticmethod
    def straight_line_3d(space_a: dict[str, Any], space_b: dict[str, Any], building_data: dict[str, Any]) -> float:
        """Computes 3D Euclidean distance between polygon centroids across elevations."""
        floors = {f["id"]: f for f in building_data.get("floors", [])}
        poly_a = Polygon(space_a["polygon"])
        poly_b = Polygon(space_b["polygon"])
        c_a = poly_a.centroid
        c_b = poly_b.centroid
        z_a = float(floors[space_a["floor_id"]]["elevation_m"])
        z_b = float(floors[space_b["floor_id"]]["elevation_m"])
        return math.sqrt((c_a.x - c_b.x) ** 2 + (c_a.y - c_b.y) ** 2 + (z_a - z_b) ** 2)

    @staticmethod
    def stacked_room(start_space: dict[str, Any], direction: str, building_data: dict[str, Any]) -> tuple[dict[str, Any], float]:
        """Finds space on adjacent floor level with maximum 2D polygon intersection area."""
        floors_by_id = {f["id"]: f for f in building_data.get("floors", [])}
        floors_by_level = {f["level"]: f for f in building_data.get("floors", [])}

        current_floor = floors_by_id[start_space["floor_id"]]
        current_level = int(current_floor["level"])

        target_level = current_level + 1 if direction == "above" else current_level - 1
        if target_level not in floors_by_level:
            raise ValueError(f"Target level {target_level} does not exist in building")

        target_floor_id = floors_by_level[target_level]["id"]
        poly_start = Polygon(start_space["polygon"])

        candidates = [
            s for s in building_data.get("spaces", [])
            if s.get("floor_id") == target_floor_id
        ]
        if not candidates:
            raise ValueError(f"No spaces found on target floor {target_floor_id}")

        best_space = None
        best_overlap = -1.0
        for s in candidates:
            poly_c = Polygon(s["polygon"])
            inter_area = poly_start.intersection(poly_c).area
            if inter_area > best_overlap:
                best_overlap = inter_area
                best_space = s

        return best_space, float(best_overlap)

    @staticmethod
    def shared_walls_count(target_space: dict[str, Any], building_data: dict[str, Any], min_length: float = 1.0, buffer_dist: float = 0.35) -> int:
        """Counts rooms sharing >= min_length boundary with 0.35m buffer."""
        poly_target = Polygon(target_space["polygon"])
        buf_target = poly_target.exterior.buffer(buffer_dist)
        target_floor = target_space["floor_id"]
        target_id = target_space["id"]

        count = 0
        for s in building_data.get("spaces", []):
            if s.get("floor_id") != target_floor or s.get("id") == target_id:
                continue
            # Exclude non-room spaces (corridors, stairs, lifts, outdoor, balconies)
            if s.get("type") in ("corridor", "stair", "stairwell", "lift", "outdoor"):
                continue
            if s.get("room_type") in ("corridor", "stairwell", "lift", "balcony"):
                continue

            poly_cand = Polygon(s["polygon"])
            overlap_len = buf_target.intersection(poly_cand.exterior).length
            if overlap_len >= min_length - 1e-6:
                count += 1
        return count

    @staticmethod
    def build_routing_graph(
        building_data: dict[str, Any],
        step_free: bool = False,
        min_door_width: float | None = None,
        closed: set[str] | None = None,
    ) -> nx.MultiGraph:
        """Constructs NetworkX MultiGraph adhering to the exact competition routing model."""
        closed = closed or set()
        graph = nx.MultiGraph()

        floors = {f["id"]: f for f in building_data.get("floors", [])}
        spaces = {s["id"]: s for s in building_data.get("spaces", [])}
        openings = {o["id"]: o for o in building_data.get("openings", [])}
        connectors = {c["id"]: c for c in building_data.get("vertical_connectors", [])}

        # 1. Anchors
        anchors: dict[str, tuple[float, float]] = {}
        for s_id, s in spaces.items():
            if s_id not in closed:
                pt = Polygon(s["polygon"]).representative_point()
                anchors[s_id] = (pt.x, pt.y)
        graph.add_nodes_from(anchors)

        # 2. Openings
        for o_id, opening in openings.items():
            if o_id in closed:
                continue
            if step_free and not opening.get("step_free", True):
                continue
            if min_door_width is not None and opening.get("width_m", 0.0) < min_door_width - 1e-6:
                continue

            door_node = DOOR_PREFIX + o_id
            pos = opening["position"]
            door_pt = (pos[0], pos[1])

            for s_id in opening["space_ids"]:
                if s_id in closed:
                    continue
                if s_id == OUTSIDE_NODE:
                    graph.add_edge(door_node, OUTSIDE_NODE, weight=0.0, kind="entrance")
                elif s_id in anchors:
                    dist = math.hypot(anchors[s_id][0] - door_pt[0], anchors[s_id][1] - door_pt[1])
                    graph.add_edge(door_node, s_id, weight=dist, opening_id=o_id)

        # 3. Vertical Connectors
        for c_id, connector in connectors.items():
            if c_id in closed:
                continue
            if step_free and not connector.get("step_free", False):
                continue

            space_ids = connector.get("space_ids", [])
            floor_ids = connector.get("floor_ids", [])
            if len(space_ids) < 2 or len(floor_ids) < 2:
                continue

            # Sort stops by floor level
            stops = sorted(
                zip(floor_ids, space_ids),
                key=lambda item: int(floors[item[0]]["level"]) if item[0] in floors else 0
            )

            is_lift = connector.get("kind") == "lift"
            for (f1, s1), (f2, s2) in zip(stops[:-1], stops[1:]):
                if s1 in closed or s2 in closed:
                    continue
                level1 = int(floors[f1]["level"])
                level2 = int(floors[f2]["level"])
                span = abs(level1 - level2)

                cost = 15.0 + 6.0 * span if is_lift else 12.0 * span
                graph.add_edge(s1, s2, weight=cost, connector_id=c_id, kind=connector.get("kind", "stairs"))

        return graph

    @staticmethod
    def shortest_path(graph: nx.MultiGraph, start_node: str, end_node: str) -> tuple[float, list[str]]:
        """Computes shortest path length and node sequence."""
        length = nx.shortest_path_length(graph, start_node, end_node, weight="weight")
        path = nx.shortest_path(graph, start_node, end_node, weight="weight")
        return float(length), path

    @staticmethod
    def count_reachable_rooms(
        building_data: dict[str, Any],
        start_id: str,
        target_floor_id: str,
        step_free: bool = False,
        min_width: float | None = None,
        closed: set[str] | None = None,
    ) -> int:
        """Counts reachable spaces with type == 'room' on target_floor_id."""
        graph = ReferenceOracle.build_routing_graph(
            building_data, step_free=step_free, min_door_width=min_width, closed=closed
        )
        if start_id not in graph:
            return 0

        reachable_nodes = set(nx.descendants(graph, start_id)) | {start_id}
        count = 0
        for s in building_data.get("spaces", []):
            if s.get("id") in reachable_nodes and s.get("floor_id") == target_floor_id and s.get("type") == "room":
                count += 1
        return count

    @staticmethod
    def solve_errand(
        building_data: dict[str, Any],
        start_id: str,
        asset_type: str,
        target_room_type: str,
        target_floor_id: str,
    ) -> tuple[float, str, str]:
        """Calculates 2-leg errand route: start -> nearest asset space -> largest target room."""
        graph = ReferenceOracle.build_routing_graph(building_data, step_free=False)
        if start_id not in graph:
            raise nx.NetworkXNoPath(f"Start node {start_id} not in graph")

        # 1. Candidate spaces with asset
        asset_spaces = [
            a["space_id"] for a in building_data.get("assets", [])
            if a.get("type") == asset_type and a.get("space_id") in graph
        ]
        if not asset_spaces:
            raise ValueError(f"No asset of type '{asset_type}' found in graph")

        # 2. Nearest asset space
        lengths = nx.single_source_dijkstra_path_length(graph, start_id, weight="weight")
        reachable_asset_spaces = [s for s in asset_spaces if s in lengths]
        if not reachable_asset_spaces:
            raise nx.NetworkXNoPath(f"No asset of type '{asset_type}' reachable from {start_id}")

        best_asset_space = min(reachable_asset_spaces, key=lambda s: lengths[s])
        dist1 = lengths[best_asset_space]

        # 3. Largest target room
        target_room, _ = ReferenceOracle.largest_room(building_data, target_floor_id, target_room_type)
        target_id = target_room["id"]
        if target_id not in graph:
            raise nx.NetworkXNoPath(f"Target room {target_id} not in graph")

        # 4. Leg 2 distance
        dist2 = nx.shortest_path_length(graph, best_asset_space, target_id, weight="weight")
        return float(dist1 + dist2), best_asset_space, target_id

    @staticmethod
    def evaluate_what_if_door(
        building_data: dict[str, Any],
        space_a_id: str,
        space_b_id: str,
        target_floor_id: str,
        threshold: float = 1.0,
    ) -> int:
        """Simulates adding a door and counts rooms on target floor whose exit distance improves > threshold."""
        spaces = {s["id"]: s for s in building_data.get("spaces", [])}
        if space_a_id not in spaces or space_b_id not in spaces:
            raise ValueError("Invalid space IDs for what_if_door")

        poly_a = Polygon(spaces[space_a_id]["polygon"])
        poly_b = Polygon(spaces[space_b_id]["polygon"])
        if poly_a.distance(poly_b) > 0.6:
            raise ValueError("Rooms separated by > 0.6m cannot be joined by a standard door")

        # Base distances to outside
        base_graph = ReferenceOracle.build_routing_graph(building_data, step_free=False)
        d_before: dict[str, float] = {}
        for s in building_data.get("spaces", []):
            if s.get("floor_id") == target_floor_id and s.get("type") == "room":
                s_id = s["id"]
                if OUTSIDE_NODE in base_graph and s_id in base_graph and nx.has_path(base_graph, s_id, OUTSIDE_NODE):
                    d_before[s_id] = nx.shortest_path_length(base_graph, s_id, OUTSIDE_NODE, weight="weight")
                else:
                    d_before[s_id] = float("inf")

        # Virtual door midpoint
        p_a, p_b = nearest_points(poly_a, poly_b)
        door_pt = Point((p_a.x + p_b.x) / 2.0, (p_a.y + p_b.y) / 2.0)

        # Graph with added door
        updated_graph = base_graph.copy()
        new_door_node = "door:virtual_synthetic"
        anchor_a = poly_a.representative_point()
        anchor_b = poly_b.representative_point()
        dist_a = math.hypot(anchor_a.x - door_pt.x, anchor_a.y - door_pt.y)
        dist_b = math.hypot(anchor_b.x - door_pt.x, anchor_b.y - door_pt.y)

        updated_graph.add_edge(new_door_node, space_a_id, weight=dist_a)
        updated_graph.add_edge(new_door_node, space_b_id, weight=dist_b)

        count = 0
        for s_id, before_len in d_before.items():
            if before_len == float("inf"):
                continue
            if OUTSIDE_NODE in updated_graph and s_id in updated_graph and nx.has_path(updated_graph, s_id, OUTSIDE_NODE):
                after_len = nx.shortest_path_length(updated_graph, s_id, OUTSIDE_NODE, weight="weight")
                if (before_len - after_len) > threshold + 1e-6:
                    count += 1
        return count


class MockVisualizerDispatcher:
    """Mock implementation of the Visualizer REST API backend for opaque-box API verification."""

    def __init__(self, building_data: dict[str, Any]):
        self.building_data = building_data
        self.closed: set[str] = set()
        self.added_doors: list[dict[str, Any]] = []

    def get_building(self) -> dict[str, Any]:
        """GET /api/building"""
        return {
            "building": self.building_data.get("building", {}),
            "floors": self.building_data.get("floors", []),
            "spaces": self.building_data.get("spaces", []),
            "openings": self.building_data.get("openings", []) + self.added_doors,
            "vertical_connectors": self.building_data.get("vertical_connectors", []),
            "assets": self.building_data.get("assets", []),
            "closed": list(self.closed),
        }

    def post_route(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST /api/route"""
        start = body.get("start")
        end = body.get("end")
        step_free = body.get("step_free", False)
        min_width = body.get("min_width")
        extra_closed = set(body.get("closed", []))
        all_closed = self.closed | extra_closed

        graph = ReferenceOracle.build_routing_graph(
            self.building_data, step_free=step_free, min_door_width=min_width, closed=all_closed
        )

        # Incorporate dynamically added doors
        spaces = {s["id"]: s for s in self.building_data.get("spaces", [])}
        for d in self.added_doors:
            if d["id"] in all_closed:
                continue
            s1, s2 = d["space_ids"]
            if s1 not in all_closed and s2 not in all_closed:
                pos = d["position"]
                pt_a = Polygon(spaces[s1]["polygon"]).representative_point()
                pt_b = Polygon(spaces[s2]["polygon"]).representative_point()
                graph.add_edge("door:" + d["id"], s1, weight=math.hypot(pt_a.x - pos[0], pt_a.y - pos[1]))
                graph.add_edge("door:" + d["id"], s2, weight=math.hypot(pt_b.x - pos[0], pt_b.y - pos[1]))

        if start not in graph or end not in graph or not nx.has_path(graph, start, end):
            raise nx.NetworkXNoPath(f"No route between {start} and {end}")

        length, path = ReferenceOracle.shortest_path(graph, start, end)

        # Generate 3D waypoints
        floors = {f["id"]: f for f in self.building_data.get("floors", [])}
        waypoints_3d = []
        for node in path:
            if node in spaces:
                pt = Polygon(spaces[node]["polygon"]).representative_point()
                elev = floors[spaces[node]["floor_id"]]["elevation_m"]
                waypoints_3d.append([pt.x, pt.y, elev])
            elif node.startswith(DOOR_PREFIX):
                d_id = node[len(DOOR_PREFIX):]
                matching = [o for o in (self.building_data.get("openings", []) + self.added_doors) if o["id"] == d_id]
                if matching:
                    pos = matching[0]["position"]
                    elev = floors[matching[0]["floor_id"]]["elevation_m"]
                    waypoints_3d.append([pos[0], pos[1], elev])

        return {
            "status": "ok",
            "distance": round(length, 2),
            "path": path,
            "waypoints_3d": waypoints_3d,
        }

    def post_closures(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST /api/closures"""
        closed_list = body.get("closed", [])
        self.closed = set(closed_list)
        return {"status": "ok", "closed": list(self.closed)}

    def post_door(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST /api/door"""
        space_a = body.get("space_a")
        space_b = body.get("space_b")
        if space_a == space_b:
            raise ValueError("Cannot create door between space and itself")
        spaces = {s["id"]: s for s in self.building_data.get("spaces", [])}
        if space_a not in spaces or space_b not in spaces:
            raise ValueError("Invalid spaces for door creation")

        poly_a = Polygon(spaces[space_a]["polygon"])
        poly_b = Polygon(spaces[space_b]["polygon"])
        if poly_a.distance(poly_b) > 0.6:
            raise ValueError("Rooms separated by > 0.6m cannot receive a door")

        p_a, p_b = nearest_points(poly_a, poly_b)
        mid_x = round((p_a.x + p_b.x) / 2.0, 3)
        mid_y = round((p_a.y + p_b.y) / 2.0, 3)
        door_id = f"door_dyn_{len(self.added_doors) + 1}"

        door_record = {
            "id": door_id,
            "floor_id": spaces[space_a]["floor_id"],
            "space_ids": [space_a, space_b],
            "kind": "door",
            "position": [mid_x, mid_y],
            "width_m": 0.9,
            "step_free": True,
            "synthetic": True,
        }
        self.added_doors.append(door_record)
        return {"status": "ok", "door_id": door_id, "position": [mid_x, mid_y]}

    def post_voice_command(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST /api/voice_command"""
        transcript = body.get("transcript", "").strip().lower()
        if not transcript:
            return {
                "intent": "unknown",
                "response_text": "I didn't catch that. Please state your navigation command.",
                "action": {},
            }

        # Intent: Errand
        m_errand = re.search(r"(?:find|fetch|grab|locate|take me to the nearest)\s+(?:a\s+|an\s+)?([a-z_]+)", transcript)
        if m_errand:
            asset = m_errand.group(1).strip()
            return {
                "intent": "errand",
                "response_text": f"Locating nearest {asset}.",
                "action": {"asset_type": asset},
            }

        # Intent: Navigate
        m_nav = re.search(r"(?:navigate|go|take me|route)\s+to\s+(.+)", transcript)
        if m_nav:
            target = m_nav.group(1).strip()
            return {
                "intent": "navigate",
                "response_text": f"Navigating to {target}.",
                "action": {"target": target},
            }

        # Intent: Close
        m_close = re.search(r"close\s+(.+)", transcript)
        if m_close:
            elem = m_close.group(1).strip()
            return {
                "intent": "close",
                "response_text": f"Marked {elem} as closed.",
                "action": {"element": elem},
            }

        # Intent: View floor
        m_floor = re.search(r"(?:show|view|switch to)\s+floor\s+(-?\d+)", transcript)
        if m_floor:
            lvl = int(m_floor.group(1))
            return {
                "intent": "view_floor",
                "response_text": f"Switching view to Floor {lvl}.",
                "action": {"level": lvl},
            }

        # Fallback
        return {
            "intent": "general_query",
            "response_text": f"Processed query: {transcript}",
            "action": {"transcript": transcript},
        }


def format_benchmark_answer(kind: str, value: Any, runner_ups: list[str] | None = None) -> str:
    """Formats compliant answer line matching benchmark/score.py regex."""
    if kind == "largest_room":
        # Space name/ref and area in m²
        name, area = value
        return f"The largest room is {name}.\nAnswer: {name}, {round(area, 1)} m²"
    elif kind == "room_stacked":
        return f"The vertically stacked space is {value}.\nAnswer: {value}"
    elif kind in ("floor_area_total", "straight_line_3d", "errand"):
        # Exactly one number
        return f"Computed spatial metric is {value}.\nAnswer: {value}"
    elif kind in ("wide_delivery_count", "shared_walls_count", "step_free_reachable_count", "what_if_door"):
        # Exact integer count
        return f"Reachable/shared count is {value}.\nAnswer: {int(value)}"
    else:
        return f"Answer: {value}"
