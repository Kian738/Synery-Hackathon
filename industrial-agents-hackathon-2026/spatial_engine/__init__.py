"""Spatial Engine: Core Indoor Spatial Reasoning and Geometry Layer."""

from .models import (
    Asset,
    AssetFootprint,
    Building,
    BuildingMetadata,
    Connector,
    Floor,
    Opening,
    Space,
)
from .building_loader import load_building, load_equipment_csv
from .geometry import (
    calculate_floor_area_total,
    calculate_room_area,
    calculate_straight_line_3d,
    count_shared_walls,
    find_largest_room,
    find_stacked_room,
    get_shared_boundary,
    get_shared_wall_spaces,
    is_point_in_space,
    is_valid_shared_wall_room,
    resolve_floor,
)

__all__ = [
    "Asset",
    "AssetFootprint",
    "Building",
    "BuildingMetadata",
    "Connector",
    "Floor",
    "Opening",
    "Space",
    "load_building",
    "load_equipment_csv",
    "calculate_floor_area_total",
    "calculate_room_area",
    "calculate_straight_line_3d",
    "count_shared_walls",
    "find_largest_room",
    "find_stacked_room",
    "get_shared_boundary",
    "get_shared_wall_spaces",
    "is_point_in_space",
    "is_valid_shared_wall_room",
    "resolve_floor",
]
