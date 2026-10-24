"""Spatial Engine: Deterministic Indoor Spatial Reasoning and Navigation Engine."""

from .models import (
    Asset,
    AssetFootprint,
    Building,
    BuildingMetadata,
    Connector,
    Floor,
    Opening,
    Space,
    VerticalConnector,
)
from .building_loader import load_building, load_equipment_csv
from .geometry import (
    calculate_floor_area_total,
    calculate_room_area,
    calculate_straight_line_3d,
    count_shared_walls,
    find_largest_room,
    find_stacked_room,
    resolve_floor,
)
from .graph import DOOR_PREFIX, OUTSIDE_NODE, build_routing_graph
from .router import (
    RouteResult,
    count_reachable_rooms,
    evaluate_what_if_door,
    find_route,
    solve_errand,
)
from .landmarks import (
    calculate_segment_landmarks,
    clarify_query,
    compute_path_waypoints,
    generate_landmark_instructions,
    resolve_clarification,
)
from .solver import solve_benchmark_question

__all__ = [
    "Asset",
    "AssetFootprint",
    "Building",
    "BuildingMetadata",
    "Connector",
    "Floor",
    "Opening",
    "Space",
    "VerticalConnector",
    "load_building",
    "load_equipment_csv",
    "calculate_floor_area_total",
    "calculate_room_area",
    "calculate_straight_line_3d",
    "count_shared_walls",
    "find_largest_room",
    "find_stacked_room",
    "resolve_floor",
    "DOOR_PREFIX",
    "OUTSIDE_NODE",
    "build_routing_graph",
    "RouteResult",
    "count_reachable_rooms",
    "evaluate_what_if_door",
    "find_route",
    "solve_errand",
    "solve_benchmark_question",
    "calculate_segment_landmarks",
    "clarify_query",
    "compute_path_waypoints",
    "generate_landmark_instructions",
    "resolve_clarification",
]

