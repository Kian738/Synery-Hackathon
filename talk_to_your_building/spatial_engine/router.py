"""Constrained pathfinding and spatial routing engine.

Provides constrained Dijkstra routing, step-free reachability counting,
industrial clearance filtering, 2-leg errand optimization, and counterfactual
doorway insertion simulations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Set
import networkx as nx
from shapely.ops import nearest_points

from .geometry import find_largest_room, resolve_floor
from .graph import DOOR_PREFIX, OUTSIDE_NODE, build_routing_graph
from .models import Building


@dataclass
class RouteResult:
    """Detailed pathfinding route solution."""

    distance_m: float
    path_nodes: list[str]
    path_spaces: list[str]
    path_openings: list[str]
    success: bool = True
    error_message: Optional[str] = None


def count_reachable_rooms(
    building: Building,
    start_space_id: str,
    target_floor_id: str,
    step_free: bool = False,
    min_width: Optional[float] = None,
    closed: Optional[Set[str]] = None,
) -> int:
    """Count reachable spaces with type == 'room' on target floor under constraints."""
    graph = build_routing_graph(
        building,
        step_free=step_free,
        min_door_width=min_width,
        closed=closed,
    )

    if start_space_id not in graph:
        return 0

    # Compute reachable connected component
    reachable_nodes = set(nx.descendants(graph, start_space_id)) | {start_space_id}

    target_floor = resolve_floor(building, target_floor_id)
    target_spaces = building.spaces_by_floor.get(target_floor.id, [])

    count = 0
    for space in target_spaces:
        if space.id in reachable_nodes and space.type == "room":
            count += 1

    return count


def solve_errand(
    building: Building,
    start_space_id: str,
    asset_type: str,
    target_room_type: str,
    target_floor_id: str,
) -> tuple[float, str, str]:
    """Calculate 2-leg errand route: start -> nearest asset space -> largest target room.

    Returns:
        tuple of (total_distance_m, nearest_asset_space_id, target_room_id).
    """
    graph = build_routing_graph(building, step_free=False)
    if start_space_id not in graph:
        raise nx.NetworkXNoPath(f"Start space '{start_space_id}' not in navigation graph")

    norm_asset_type = asset_type.strip().lower().replace(" ", "_")
    norm_room_type = target_room_type.strip().lower().replace(" ", "_")

    # 1. Identify candidate spaces holding the target asset
    candidate_asset_spaces = {
        asset.space_id
        for asset in building.assets_by_type.get(norm_asset_type, [])
        if asset.space_id in graph
    }

    # Fallback: scan all assets if not found in index
    if not candidate_asset_spaces:
        candidate_asset_spaces = {
            asset.space_id
            for asset in building.assets.values()
            if asset.type == norm_asset_type and asset.space_id in graph
        }

    if not candidate_asset_spaces:
        raise ValueError(f"No asset of type '{norm_asset_type}' found in navigable spaces")

    # 2. Find nearest asset space via single-source Dijkstra
    lengths = nx.single_source_dijkstra_path_length(graph, start_space_id, weight="weight")
    reachable_asset_spaces = [sid for sid in candidate_asset_spaces if sid in lengths]

    if not reachable_asset_spaces:
        raise nx.NetworkXNoPath(f"No asset of type '{norm_asset_type}' reachable from '{start_space_id}'")

    best_asset_space_id = min(reachable_asset_spaces, key=lambda sid: lengths[sid])
    dist1 = lengths[best_asset_space_id]

    # 3. Locate largest room of target_room_type on target floor
    target_floor = resolve_floor(building, target_floor_id)
    target_room, _ = find_largest_room(building, target_floor, norm_room_type)
    target_id = target_room.id

    if target_id not in graph:
        raise nx.NetworkXNoPath(f"Target room '{target_id}' not in navigation graph")

    # 4. Compute Leg 2 shortest path distance
    dist2 = nx.shortest_path_length(graph, best_asset_space_id, target_id, weight="weight")

    return float(dist1 + dist2), best_asset_space_id, target_id


def evaluate_what_if_door(
    building: Building,
    space_a_id: str,
    space_b_id: str,
    target_floor_id: str,
    threshold: float = 1.0,
) -> int:
    """Simulate adding a door and count rooms on target floor whose exit distance improves > threshold."""
    space_a = building.spaces.get(space_a_id)
    space_b = building.spaces.get(space_b_id)

    if not space_a or not space_b:
        raise ValueError("Invalid space IDs for what_if_door simulation")

    poly_a = space_a.polygon
    poly_b = space_b.polygon

    # Validate physical adjacency: rooms separated by > 0.6m cannot share a door
    if poly_a.distance(poly_b) > 0.6:
        raise ValueError("Rooms separated by > 0.6m cannot be joined by a standard door")

    # Baseline exit distances to outside
    base_graph = build_routing_graph(building, step_free=False)
    target_floor = resolve_floor(building, target_floor_id)
    target_rooms = [
        s for s in building.spaces_by_floor.get(target_floor.id, [])
        if s.type == "room"
    ]

    d_before: dict[str, float] = {}
    for room in target_rooms:
        rid = room.id
        if OUTSIDE_NODE in base_graph and rid in base_graph and nx.has_path(base_graph, rid, OUTSIDE_NODE):
            d_before[rid] = nx.shortest_path_length(base_graph, rid, OUTSIDE_NODE, weight="weight")
        else:
            d_before[rid] = float("inf")

    # Compute midpoint of nearest boundary points for synthetic door
    p_a, p_b = nearest_points(poly_a, poly_b)
    door_midpoint = ((p_a.x + p_b.x) / 2.0, (p_a.y + p_b.y) / 2.0)

    # Insert virtual door node into cloned graph
    updated_graph = base_graph.copy()
    virtual_door_node = "door:virtual_synthetic"

    anchor_a = space_a.representative_point
    anchor_b = space_b.representative_point
    dist_a = math.hypot(anchor_a[0] - door_midpoint[0], anchor_a[1] - door_midpoint[1])
    dist_b = math.hypot(anchor_b[0] - door_midpoint[0], anchor_b[1] - door_midpoint[1])

    updated_graph.add_edge(virtual_door_node, space_a_id, weight=dist_a)
    updated_graph.add_edge(virtual_door_node, space_b_id, weight=dist_b)

    # Count rooms where walk to outside improves by more than threshold
    count = 0
    for rid, before_len in d_before.items():
        if before_len == float("inf"):
            continue
        if OUTSIDE_NODE in updated_graph and rid in updated_graph and nx.has_path(updated_graph, rid, OUTSIDE_NODE):
            after_len = nx.shortest_path_length(updated_graph, rid, OUTSIDE_NODE, weight="weight")
            if (before_len - after_len) > threshold + 1e-6:
                count += 1

    return count


def find_route(
    building: Building,
    start_space_id: str,
    end_space_id: str,
    step_free: bool = False,
    min_width: float = 0.0,
    closed: Optional[Set[str]] = None,
) -> RouteResult:
    """Compute optimal path between two spaces."""
    graph = build_routing_graph(
        building,
        step_free=step_free,
        min_door_width=min_width if min_width > 0 else None,
        closed=closed,
    )

    if start_space_id not in graph:
        return RouteResult(
            distance_m=0.0,
            path_nodes=[],
            path_spaces=[],
            path_openings=[],
            success=False,
            error_message=f"Start space '{start_space_id}' not in graph",
        )

    if end_space_id not in graph:
        return RouteResult(
            distance_m=0.0,
            path_nodes=[],
            path_spaces=[],
            path_openings=[],
            success=False,
            error_message=f"End space '{end_space_id}' not in graph",
        )

    if not nx.has_path(graph, start_space_id, end_space_id):
        return RouteResult(
            distance_m=0.0,
            path_nodes=[],
            path_spaces=[],
            path_openings=[],
            success=False,
            error_message=f"No path between '{start_space_id}' and '{end_space_id}'",
        )

    distance = nx.shortest_path_length(graph, start_space_id, end_space_id, weight="weight")
    path_nodes = nx.shortest_path(graph, start_space_id, end_space_id, weight="weight")

    path_spaces: list[str] = []
    path_openings: list[str] = []
    for node in path_nodes:
        if node.startswith(DOOR_PREFIX):
            path_openings.append(node[len(DOOR_PREFIX):])
        elif node != OUTSIDE_NODE:
            path_spaces.append(node)

    return RouteResult(
        distance_m=float(distance),
        path_nodes=path_nodes,
        path_spaces=path_spaces,
        path_openings=path_openings,
        success=True,
    )
