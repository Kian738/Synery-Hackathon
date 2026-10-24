"""Multi-floor pathfinding, errand routing, and counterfactual simulation.

Provides deterministic Dijkstra shortest paths, multi-stop errand routing
(start -> nearest asset -> largest target room), constrained reachability
analysis under step-free and door width clearance criteria, and what-if
counterfactual door addition impact evaluations.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Union

import networkx as nx
from shapely.geometry import Polygon
from shapely.ops import nearest_points

from .geometry import find_largest_room
from .graph import (
    DOOR_PREFIX,
    OUTSIDE_NODE,
    build_routing_graph,
)
from .models import Building

ADJACENT_DOOR_MAX_DISTANCE_M: float = 0.6
DEFAULT_THRESHOLD: float = 1.0
DEFAULT_EPSILON: float = 1e-6


@dataclass
class RouteResult:
    """Result of a shortest path query between two nodes."""

    distance: float
    path: list[str]
    length_m: float = 0.0
    space_path: list[str] = field(default_factory=list)
    start_node: str = ""
    end_node: str = ""
    steps: list[str] = field(default_factory=list)
    step_free: bool = False
    closed: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.length_m == 0.0 and self.distance != 0.0:
            self.length_m = round(self.distance, 2)
        elif self.distance == 0.0 and self.length_m != 0.0:
            self.distance = self.length_m
        if not self.space_path and self.path:
            self.space_path = [n for n in self.path if not str(n).startswith(DOOR_PREFIX)]
        if not self.start_node and self.path:
            self.start_node = self.path[0]
        if not self.end_node and self.path:
            self.end_node = self.path[-1]

    @property
    def node_sequence(self) -> list[str]:
        """Sequence of nodes traversed along the route."""
        return self.path

    def __iter__(self):
        """Allows unpacking as (distance, path)."""
        yield self.distance
        yield self.path


@dataclass
class ErrandResult:
    """Result of a multi-stop errand query (start -> asset -> target room)."""

    total_distance: float
    via_space_id: str
    target_space_id: str
    path: list[str] = field(default_factory=list)
    leg1_distance: float = 0.0
    leg2_distance: float = 0.0
    leg1_path: list[str] = field(default_factory=list)
    leg2_path: list[str] = field(default_factory=list)
    start_space_id: str = ""
    asset_type: str = ""
    target_room_type: str = ""
    target_floor_id: str = ""

    @property
    def via(self) -> str:
        """Space where target asset was retrieved."""
        return self.via_space_id

    @property
    def target(self) -> str:
        """Final destination space (largest room of target type)."""
        return self.target_space_id

    @property
    def distance(self) -> float:
        """Total route distance in metres."""
        return self.total_distance

    @property
    def length_m(self) -> float:
        """Total route length in metres."""
        return self.total_distance

    def __iter__(self):
        """Allows unpacking as (total_distance, via_space_id, target_space_id)."""
        yield self.total_distance
        yield self.via_space_id
        yield self.target_space_id


def shortest_path(
    graph: nx.MultiGraph,
    start_node: str,
    end_node: str,
) -> RouteResult:
    """Find optimal shortest path between two nodes in a MultiGraph.

    Args:
        graph: Navigation MultiGraph.
        start_node: Starting node identifier.
        end_node: Destination node identifier.

    Returns:
        RouteResult containing shortest path distance and traversed node list.

    Raises:
        nx.NodeNotFound: If start_node or end_node is not in the graph.
        nx.NetworkXNoPath: If no connected path exists between nodes.
    """
    if start_node not in graph:
        raise nx.NodeNotFound(f"Start node '{start_node}' not found in routing graph")
    if end_node not in graph:
        raise nx.NodeNotFound(f"End node '{end_node}' not found in routing graph")

    length = nx.shortest_path_length(graph, start_node, end_node, weight="weight")
    path = nx.shortest_path(graph, start_node, end_node, weight="weight")

    return RouteResult(
        distance=float(length),
        path=path,
        start_node=start_node,
        end_node=end_node,
    )


def count_reachable_rooms(
    building: Union[Building, dict[str, Any]],
    start_id: str,
    target_floor_id: str,
    step_free: bool = False,
    min_width: Optional[float] = None,
    closed: Optional[Union[set[str], list[str], Iterable[str]]] = None,
) -> int:
    """Count spaces with type == 'room' on target_floor_id reachable from start_id.

    Applies step-free accessibility constraints, door clearance thresholds, and dynamic
    closures of rooms, doors, or vertical connectors.

    Args:
        building: Building model or building JSON dict.
        start_id: Starting space identifier.
        target_floor_id: Floor identifier on which to count reachable rooms.
        step_free: Whether route must be accessible without stairs or stepped doors.
        min_width: Minimum opening width clearance required.
        closed: Set of space, opening, or connector IDs currently closed.

    Returns:
        Integer count of reachable rooms on the target floor.
    """
    closed_set = set(closed) if closed else set()
    graph = build_routing_graph(
        building,
        step_free=step_free,
        min_door_width=min_width,
        closed=closed_set,
    )

    if start_id not in graph:
        return 0

    reachable_nodes = set(nx.descendants(graph, start_id)) | {start_id}

    count = 0
    if isinstance(building, Building):
        for space in building.spaces.values():
            if (
                space.id in reachable_nodes
                and space.floor_id == target_floor_id
                and space.type == "room"
            ):
                count += 1
    else:
        for s in building.get("spaces", []):
            if (
                s.get("id") in reachable_nodes
                and s.get("floor_id") == target_floor_id
                and s.get("type") == "room"
            ):
                count += 1

    return count


def solve_errand(
    building: Union[Building, dict[str, Any]],
    start_id: str,
    asset_type: str,
    target_room_type: str,
    target_floor_id: str,
) -> ErrandResult:
    """Solve a 2-leg errand route: start -> nearest asset space -> largest target room.

    Leg 1: Shortest path from start_id to closest space containing an asset of asset_type.
    Leg 2: Shortest path from that space to the largest room (by polygon area) of
           target_room_type on target_floor_id.

    Args:
        building: Building model or building JSON dict.
        start_id: Starting room ID.
        asset_type: Category/type of asset to retrieve (e.g. 'fire_extinguisher', 'stove').
        target_room_type: Room type of destination (e.g. 'kitchen', 'meeting_room').
        target_floor_id: Floor ID on which destination room is located.

    Returns:
        ErrandResult containing total distance, via asset space ID, target room ID, and paths.

    Raises:
        ValueError: If no asset of asset_type exists in the building or no matching target rooms.
        nx.NetworkXNoPath: If start node is disconnected or asset/target room is unreachable.
    """
    graph = build_routing_graph(building, step_free=False)
    if start_id not in graph:
        raise nx.NetworkXNoPath(f"Start node {start_id} not in graph")

    # 1. Identify candidate spaces containing the target asset type
    asset_spaces: list[str] = []
    if isinstance(building, Building):
        assets = building.assets_by_type.get(asset_type, [])
        if not assets:
            assets = [a for a in building.assets.values() if a.type == asset_type]
        asset_spaces = [a.space_id for a in assets if a.space_id in graph]
    else:
        for a in building.get("assets", []):
            if a.get("type") == asset_type:
                sid = str(a.get("space_id", ""))
                if sid in graph:
                    asset_spaces.append(sid)

    if not asset_spaces:
        raise ValueError(f"No asset of type '{asset_type}' found in graph")

    # 2. Leg 1 Dijkstra: Find closest space containing asset
    lengths, paths = nx.single_source_dijkstra(graph, start_id, weight="weight")
    reachable_asset_spaces = [s for s in asset_spaces if s in lengths]
    if not reachable_asset_spaces:
        raise nx.NetworkXNoPath(f"No asset of type '{asset_type}' reachable from {start_id}")

    # Tie-break deterministically by distance then space ID
    best_asset_space = min(reachable_asset_spaces, key=lambda s: (lengths[s], s))
    dist1 = float(lengths[best_asset_space])
    leg1_path = list(paths[best_asset_space])

    # 3. Destination Room: Find largest room of target_room_type on target_floor_id
    if isinstance(building, Building):
        target_space, _ = find_largest_room(building, target_floor_id, target_room_type)
        target_id = target_space.id
    else:
        candidates = [
            s
            for s in building.get("spaces", [])
            if s.get("floor_id") == target_floor_id and s.get("room_type") == target_room_type
        ]
        if not candidates:
            raise ValueError(
                f"No spaces with room_type='{target_room_type}' on floor '{target_floor_id}'"
            )
        target_space = max(candidates, key=lambda s: Polygon(s["polygon"]).area)
        target_id = str(target_space["id"])

    if target_id not in graph:
        raise nx.NetworkXNoPath(f"Target room {target_id} not in graph")

    # 4. Leg 2 Dijkstra: from best_asset_space to target_id
    dist2, leg2_path = nx.single_source_dijkstra(
        graph, best_asset_space, target_id, weight="weight"
    )
    dist2 = float(dist2)
    leg2_path = list(leg2_path)

    combined_path = leg1_path + leg2_path[1:]
    total_dist = round(dist1 + dist2, 4)

    return ErrandResult(
        total_distance=total_dist,
        via_space_id=best_asset_space,
        target_space_id=target_id,
        path=combined_path,
        leg1_distance=round(dist1, 4),
        leg2_distance=round(dist2, 4),
        leg1_path=leg1_path,
        leg2_path=leg2_path,
        start_space_id=start_id,
        asset_type=asset_type,
        target_room_type=target_room_type,
        target_floor_id=target_floor_id,
    )


def evaluate_what_if_door(
    building: Union[Building, dict[str, Any]],
    space_a_id: str,
    space_b_id: str,
    target_floor_id: str,
    threshold: float = DEFAULT_THRESHOLD,
) -> int:
    """Simulate adding a door between space A and B and evaluate its exit impact.

    Counts how many rooms on target_floor_id would have their shortest walking distance
    to an outside entrance improved by more than `threshold` metres (improvement > threshold + 1e-6).

    Args:
        building: Building model or building JSON dict.
        space_a_id: First space identifier.
        space_b_id: Second space identifier.
        target_floor_id: Floor identifier on which to evaluate room improvements.
        threshold: Required distance improvement threshold in metres (default: 1.0 m).

    Returns:
        Number of rooms on target_floor_id experiencing exit distance reduction > threshold.

    Raises:
        ValueError: If space IDs are invalid or rooms are separated by > 0.6 m.
    """
    if isinstance(building, Building):
        space_a = building.get_space(space_a_id)
        space_b = building.get_space(space_b_id)
        if not space_a or not space_b:
            raise ValueError(f"Invalid space IDs for what_if_door: {space_a_id}, {space_b_id}")
        poly_a, poly_b = space_a.polygon, space_b.polygon
        anchor_a, anchor_b = space_a.representative_point, space_b.representative_point
        target_rooms = [
            s.id
            for s in building.spaces.values()
            if s.floor_id == target_floor_id and s.type == "room"
        ]
    else:
        spaces_dict = {str(s["id"]): s for s in building.get("spaces", [])}
        if space_a_id not in spaces_dict or space_b_id not in spaces_dict:
            raise ValueError(f"Invalid space IDs for what_if_door: {space_a_id}, {space_b_id}")
        poly_a = Polygon(spaces_dict[space_a_id]["polygon"])
        poly_b = Polygon(spaces_dict[space_b_id]["polygon"])
        rep_a = poly_a.representative_point()
        rep_b = poly_b.representative_point()
        anchor_a = (float(rep_a.x), float(rep_a.y))
        anchor_b = (float(rep_b.x), float(rep_b.y))
        target_rooms = [
            str(s["id"])
            for s in building.get("spaces", [])
            if s.get("floor_id") == target_floor_id and s.get("type") == "room"
        ]

    # Verify geometric adjacency: rooms separated by > 0.6m cannot be joined by a door
    if poly_a.distance(poly_b) > ADJACENT_DOOR_MAX_DISTANCE_M:
        raise ValueError("Rooms separated by > 0.6m cannot be joined by a standard door")

    # 1. Baseline distances to outside entrance
    base_graph = build_routing_graph(building, step_free=False)
    d_before: dict[str, float] = {}
    if OUTSIDE_NODE in base_graph:
        lengths_from_outside = nx.single_source_dijkstra_path_length(
            base_graph, OUTSIDE_NODE, weight="weight"
        )
        for r_id in target_rooms:
            d_before[r_id] = lengths_from_outside.get(r_id, float("inf"))
    else:
        for r_id in target_rooms:
            d_before[r_id] = float("inf")

    # 2. Synthesize virtual door at midpoint of nearest boundary points
    p_a, p_b = nearest_points(poly_a, poly_b)
    door_x = (p_a.x + p_b.x) / 2.0
    door_y = (p_a.y + p_b.y) / 2.0

    dist_a = math.hypot(anchor_a[0] - door_x, anchor_a[1] - door_y)
    dist_b = math.hypot(anchor_b[0] - door_x, anchor_b[1] - door_y)

    updated_graph = base_graph.copy()
    new_door_node = "door:virtual_synthetic"
    updated_graph.add_edge(
        new_door_node,
        space_a_id,
        weight=dist_a,
        opening_id="virtual_synthetic",
        via="virtual_synthetic",
        kind="door",
    )
    updated_graph.add_edge(
        new_door_node,
        space_b_id,
        weight=dist_b,
        opening_id="virtual_synthetic",
        via="virtual_synthetic",
        kind="door",
    )

    # 3. Recompute shortest distances to outside
    if OUTSIDE_NODE in updated_graph:
        d_after_map = nx.single_source_dijkstra_path_length(
            updated_graph, OUTSIDE_NODE, weight="weight"
        )
    else:
        d_after_map = {}

    count = 0
    for r_id, before_len in d_before.items():
        if before_len == float("inf"):
            continue
        after_len = d_after_map.get(r_id, float("inf"))
        if (before_len - after_len) > threshold + DEFAULT_EPSILON:
            count += 1

    return count


def resolve_space(building: Union[Building, dict[str, Any]], reference: str) -> str:
    """Resolve a space id, asset id, or exact room/asset name into a space id."""
    if isinstance(building, Building):
        if reference in building.spaces:
            return reference
        if reference in building.assets:
            return building.assets[reference].space_id
        matched = building.find_space_by_ref_or_name(reference)
        if matched:
            return matched.id
        return reference

    # Dictionary fallback
    spaces = {s["id"]: s for s in building.get("spaces", [])}
    if reference in spaces:
        return reference
    assets = {a["id"]: a for a in building.get("assets", [])}
    if reference in assets:
        return str(assets[reference].get("space_id", ""))

    lowered = reference.strip().lower()
    for s in spaces.values():
        if (s.get("ref") or "").lower() == lowered or s.get("name", "").lower() == lowered:
            return str(s["id"])

    return reference


def directions(
    graph: nx.MultiGraph,
    nodes: list[str],
    building: Optional[Union[Building, dict[str, Any]]] = None,
) -> list[str]:
    """Turn a node path into step-by-step navigation instructions."""
    if not nodes:
        return ["No path."]
    if len(nodes) == 1:
        return [f"Start and finish in {nodes[0]}."]

    steps = [f"Start in {nodes[0]}."]
    walked = 0.0

    for previous, current in itertools.pairwise(nodes):
        if not graph.has_edge(previous, current):
            continue
        edge_candidates = graph[previous][current].values()
        edge = min(edge_candidates, key=lambda c: c.get("weight", 0.0))
        walked += edge.get("weight", 0.0)
        via = edge.get("via", "")
        kind = edge.get("kind", "")

        if kind in ("stairs", "lift"):
            steps.append(f"Take {kind} ({via}) to next level (about {walked:.1f} m).")
            walked = 0.0
        elif current == OUTSIDE_NODE:
            steps.append(f"Walk about {walked:.1f} m and exit the building.")
            walked = 0.0
        elif not current.startswith(DOOR_PREFIX):
            steps.append(f"Walk about {walked:.1f} m through door into {current}.")
            walked = 0.0

    steps.append(f"You have arrived at {nodes[-1]}.")
    return steps


def find_route(
    building: Union[Building, dict[str, Any]],
    start: str,
    destination: str,
    step_free: bool = False,
    min_width: Optional[float] = None,
    closed: Optional[Union[set[str], list[str], Iterable[str]]] = None,
    via: Optional[list[str]] = None,
) -> RouteResult:
    """High-level multi-stop or single-leg route solver.

    Args:
        building: Building model or raw JSON dict.
        start: Starting space or asset reference.
        destination: Destination space or asset reference.
        step_free: Whether route must be step-free.
        min_width: Minimum door clearance required.
        closed: Set of closed IDs.
        via: Optional intermediate stop references.

    Returns:
        RouteResult with combined length, node path, space path, and instructions.
    """
    start_id = resolve_space(building, start)
    dest_id = resolve_space(building, destination)
    via_ids = [resolve_space(building, v) for v in (via or [])]
    stops = [start_id] + via_ids + [dest_id]

    closed_set = set(closed) if closed else set()
    graph = build_routing_graph(
        building,
        step_free=step_free,
        min_door_width=min_width,
        closed=closed_set,
    )

    total_length = 0.0
    full_nodes: list[str] = []

    for leg_start, leg_end in itertools.pairwise(stops):
        leg_length, leg_path = nx.single_source_dijkstra(
            graph, leg_start, leg_end, weight="weight"
        )
        total_length += float(leg_length)
        if not full_nodes:
            full_nodes.extend(leg_path)
        else:
            full_nodes.extend(leg_path[1:])

    step_instructions = directions(graph, full_nodes, building)

    return RouteResult(
        distance=round(total_length, 2),
        path=full_nodes,
        length_m=round(total_length, 2),
        space_path=[n for n in full_nodes if not n.startswith(DOOR_PREFIX)],
        start_node=start_id,
        end_node=dest_id,
        steps=step_instructions,
        step_free=step_free,
        closed=sorted(closed_set),
    )
