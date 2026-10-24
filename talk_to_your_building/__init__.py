"""Talk to Your Building: Autonomous Indoor Spatial Reasoning Agent & Navigation System.

Industrial Agents Hackathon 2026 — Track 01.
"""

from .agent import solve_question
from .spatial_engine.building_loader import load_building, load_equipment_csv
from .spatial_engine.geometry import (
    calculate_floor_area_total,
    calculate_room_area,
    calculate_straight_line_3d,
    count_shared_walls,
    find_largest_room,
    find_stacked_room,
    resolve_floor,
)
from .spatial_engine.graph import build_routing_graph
from .spatial_engine.models import (
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
from .spatial_engine.router import (
    RouteResult,
    count_reachable_rooms,
    evaluate_what_if_door,
    find_route,
    solve_errand,
)
from .spatial_engine.solver import solve_benchmark_question

__version__ = "1.0.0"

__all__ = [
    "solve_question",
    "load_building",
    "load_equipment_csv",
    "Building",
    "BuildingMetadata",
    "Floor",
    "Space",
    "Opening",
    "VerticalConnector",
    "Connector",
    "Asset",
    "AssetFootprint",
    "calculate_room_area",
    "calculate_floor_area_total",
    "find_largest_room",
    "calculate_straight_line_3d",
    "find_stacked_room",
    "count_shared_walls",
    "resolve_floor",
    "build_routing_graph",
    "count_reachable_rooms",
    "solve_errand",
    "evaluate_what_if_door",
    "find_route",
    "RouteResult",
    "solve_benchmark_question",
]
