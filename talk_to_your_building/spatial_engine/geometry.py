"""Core spatial geometry calculations and reasoning algorithms.

Provides polygon area, floor aggregations, 3D Euclidean distances between
centroids, vertical stacking overlap maximization, and wall boundary buffering.
"""

from __future__ import annotations

import math
import re
from typing import Optional, Union

from .models import Building, Floor, Space

# Space and room types explicitly excluded from soundproofing/shared-wall queries
EXCLUDED_TYPES = {"corridor", "stair", "stairwell", "lift", "outdoor"}
EXCLUDED_ROOM_TYPES = {"corridor", "stairwell", "lift", "balcony"}


def resolve_floor(building: Building, floor_spec: Union[str, int, Floor]) -> Floor:
    """Resolve a floor identifier, level integer, or name to a Floor object."""
    if isinstance(floor_spec, Floor):
        return floor_spec

    if isinstance(floor_spec, int):
        floor = building.floors_by_level.get(floor_spec)
        if floor:
            return floor
        raise ValueError(f"No floor with level {floor_spec} in building {building.id}")

    # String lookup: exact ID
    clean_spec = str(floor_spec).strip()
    if clean_spec in building.floors:
        return building.floors[clean_spec]

    # String integer level
    try:
        level_int = int(clean_spec)
        if level_int in building.floors_by_level:
            return building.floors_by_level[level_int]
    except ValueError:
        pass

    # Match by name case-insensitively
    spec_lower = clean_spec.lower()
    for f in building.floors.values():
        if f.name.lower() == spec_lower:
            return f

    # Regex matching common phrasings: "floor 3" -> 3, "ground floor" -> 0, "basement 1" -> -1
    m_floor = re.search(r"floor\s+(-?\d+)", spec_lower)
    if m_floor:
        lvl = int(m_floor.group(1))
        if lvl in building.floors_by_level:
            return building.floors_by_level[lvl]

    if "ground" in spec_lower and 0 in building.floors_by_level:
        return building.floors_by_level[0]

    m_base = re.search(r"basement\s+(\d+)", spec_lower)
    if m_base:
        lvl = -int(m_base.group(1))
        if lvl in building.floors_by_level:
            return building.floors_by_level[lvl]

    raise ValueError(f"Unable to resolve floor '{floor_spec}' in building {building.id}")


def calculate_room_area(space: Space) -> float:
    """Calculate the 2D surface area of a space polygon in square metres."""
    return float(space.polygon.area)


def calculate_floor_area_total(
    building: Building, floor_id: Union[str, int, Floor], room_type: str
) -> float:
    """Calculate the aggregate floor area of all spaces matching room_type on a floor."""
    floor = resolve_floor(building, floor_id)
    norm_room_type = room_type.strip().lower().replace(" ", "_")

    candidates = building.spaces_by_floor_and_room_type.get((floor.id, norm_room_type), [])
    if not candidates:
        candidates = [
            s
            for s in building.spaces_by_floor.get(floor.id, [])
            if s.room_type == norm_room_type
        ]

    return sum(s.area for s in candidates)


def find_largest_room(
    building: Building, floor_id: Union[str, int, Floor], room_type: str
) -> tuple[Space, float]:
    """Identify the room with the largest polygon surface area on a target floor."""
    floor = resolve_floor(building, floor_id)
    norm_room_type = room_type.strip().lower().replace(" ", "_")

    candidates = building.spaces_by_floor_and_room_type.get((floor.id, norm_room_type), [])
    if not candidates:
        candidates = [
            s
            for s in building.spaces_by_floor.get(floor.id, [])
            if s.room_type == norm_room_type
        ]

    if not candidates:
        raise ValueError(
            f"No spaces found matching room_type '{norm_room_type}' on floor {floor.id} ({floor.name})"
        )

    best_space = max(candidates, key=lambda s: s.area)
    return best_space, float(best_space.area)


def calculate_straight_line_3d(
    space_a: Space, space_b: Space, building: Building
) -> float:
    """Calculate 3D Euclidean distance between polygon centroids across elevations.

    Distance formula:
        d = sqrt((c_a.x - c_b.x)^2 + (c_a.y - c_b.y)^2 + (z_a - z_b)^2)
    """
    floor_a = building.floors.get(space_a.floor_id)
    floor_b = building.floors.get(space_b.floor_id)

    if not floor_a or not floor_b:
        raise ValueError("Invalid floor reference for straight_line_3d calculation")

    c_a = space_a.centroid
    c_b = space_b.centroid
    z_a = floor_a.elevation_m
    z_b = floor_b.elevation_m

    dx = c_a[0] - c_b[0]
    dy = c_a[1] - c_b[1]
    dz = z_a - z_b

    return math.sqrt(dx * dx + dy * dy + dz * dz)


def find_stacked_room(
    building: Building, start_space: Space, direction: str
) -> tuple[Space, float]:
    """Find space on adjacent floor level with maximum 2D polygon intersection area."""
    floor = building.floors.get(start_space.floor_id)
    if not floor:
        raise ValueError(f"Space {start_space.id} has invalid floor_id {start_space.floor_id}")

    current_level = floor.level
    dir_norm = direction.strip().lower()
    if dir_norm == "above":
        target_level = current_level + 1
    elif dir_norm == "below":
        target_level = current_level - 1
    else:
        raise ValueError(f"Invalid stacking direction '{direction}', must be 'above' or 'below'")

    target_floor = building.floors_by_level.get(target_level)
    if not target_floor:
        raise ValueError(f"Target level {target_level} does not exist in building {building.id}")

    candidates = building.spaces_by_floor.get(target_floor.id, [])
    if not candidates:
        raise ValueError(f"No spaces found on target floor {target_floor.id}")

    best_space: Optional[Space] = None
    best_overlap = -1.0

    poly_start = start_space.polygon
    for cand in candidates:
        inter_area = poly_start.intersection(cand.polygon).area
        if inter_area > best_overlap:
            best_overlap = inter_area
            best_space = cand

    if not best_space:
        raise ValueError(f"No overlapping space found on floor level {target_level}")

    return best_space, float(best_overlap)


def count_shared_walls(
    target_space: Space,
    building: Building,
    min_length: float = 1.0,
    buffer_dist: float = 0.35,
) -> int:
    """Count rooms on the same floor sharing >= min_length boundary with 0.35m buffer.

    Accounts for structural wall thickness gaps between interior room polygons.
    Excludes non-room spaces (corridors, stairwells, lifts, outdoor, balconies).
    """
    buf_target = target_space.exterior_ring.buffer(buffer_dist)
    target_floor_id = target_space.floor_id
    target_id = target_space.id

    count = 0
    candidates = building.spaces_by_floor.get(target_floor_id, [])

    for s in candidates:
        if s.id == target_id:
            continue
        # Exclude non-room spaces
        if s.type in EXCLUDED_TYPES:
            continue
        if s.room_type in EXCLUDED_ROOM_TYPES:
            continue

        overlap_len = buf_target.intersection(s.exterior_ring).length
        if overlap_len >= min_length - 1e-6:
            count += 1

    return count
