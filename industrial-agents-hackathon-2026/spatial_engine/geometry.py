"""Core spatial geometry calculations and reasoning algorithms.

Provides polygon area, floor aggregations, 3D Euclidean distances between
centroids, vertical stacking overlap maximization, and wall boundary buffering.
"""

from __future__ import annotations

import math
from typing import Optional, Union

from shapely.geometry import LineString, Point
from shapely.ops import unary_union

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
    if floor_spec in building.floors:
        return building.floors[floor_spec]

    # String integer level
    try:
        level_int = int(floor_spec)
        if level_int in building.floors_by_level:
            return building.floors_by_level[level_int]
    except ValueError:
        pass

    # Match by name case-insensitively
    spec_lower = floor_spec.strip().lower()
    for f in building.floors.values():
        if f.name.lower() == spec_lower:
            return f

    raise ValueError(f"Unable to resolve floor '{floor_spec}' in building {building.id}")


def calculate_room_area(space: Space) -> float:
    """Calculate the 2D surface area of a space polygon in square metres.

    Args:
        space: Space model instance.

    Returns:
        Polygon surface area in square metres (float).
    """
    return float(space.polygon.area)


def calculate_floor_area_total(
    building: Building, floor_id: Union[str, int, Floor], room_type: str
) -> float:
    """Calculate the aggregate floor area of all spaces matching room_type on a floor.

    Args:
        building: Building instance.
        floor_id: Floor ID, level, or Floor object.
        room_type: Category to filter by (e.g. 'kitchen', 'office').

    Returns:
        Sum of surface areas in square metres.
    """
    floor = resolve_floor(building, floor_id)
    candidates = building.spaces_by_floor_and_room_type.get((floor.id, room_type), [])

    if not candidates:
        # Fallback in case indexed by different key or missing
        candidates = [
            s
            for s in building.spaces_by_floor.get(floor.id, [])
            if s.room_type == room_type
        ]

    return sum(calculate_room_area(s) for s in candidates)


def find_largest_room(
    building: Building, floor_id: Union[str, int, Floor], room_type: str
) -> tuple[Space, float]:
    """Identify the room with the largest polygon surface area on a target floor.

    Args:
        building: Building instance.
        floor_id: Floor ID, level, or Floor object.
        room_type: Category to filter by (e.g. 'kitchen', 'meeting_room').

    Returns:
        Tuple of (largest_space, area_in_m2).

    Raises:
        ValueError: If no spaces matching room_type exist on the specified floor.
    """
    floor = resolve_floor(building, floor_id)
    candidates = building.spaces_by_floor_and_room_type.get((floor.id, room_type), [])

    if not candidates:
        candidates = [
            s
            for s in building.spaces_by_floor.get(floor.id, [])
            if s.room_type == room_type
        ]

    if not candidates:
        raise ValueError(
            f"No spaces with room_type='{room_type}' found on floor '{floor.id}' ({floor.name})"
        )

    largest_space = max(candidates, key=calculate_room_area)
    return largest_space, calculate_room_area(largest_space)


def calculate_straight_line_3d(
    space_a: Space, space_b: Space, building: Building
) -> float:
    """Compute the 3D Euclidean distance between the 2D centroids of two rooms.

    Uses each room polygon's 2D centroid (x, y) together with the elevation_m (z)
    of its corresponding floor level.

    Args:
        space_a: First Space instance.
        space_b: Second Space instance.
        building: Building containing both spaces and their floors.

    Returns:
        3D straight-line distance in metres (float).
    """
    floor_a = building.floors.get(space_a.floor_id)
    floor_b = building.floors.get(space_b.floor_id)

    if floor_a is None:
        raise ValueError(f"Floor '{space_a.floor_id}' not found for space '{space_a.id}'")
    if floor_b is None:
        raise ValueError(f"Floor '{space_b.floor_id}' not found for space '{space_b.id}'")

    c_a = space_a.centroid
    c_b = space_b.centroid

    dx = c_a[0] - c_b[0]
    dy = c_a[1] - c_b[1]
    dz = floor_a.elevation_m - floor_b.elevation_m

    return float(math.sqrt(dx * dx + dy * dy + dz * dz))


def find_stacked_room(
    space: Space, target_direction: str, building: Building
) -> tuple[Space, float]:
    """Find the space on an adjacent floor level maximizing 2D polygon overlap area.

    Args:
        space: Base Space instance.
        target_direction: Direction to look: 'above' / 'up' (+1 level)
                          or 'below' / 'down' (-1 level).
        building: Building instance.

    Returns:
        Tuple of (stacked_space, overlap_area_in_m2).

    Raises:
        ValueError: If direction is invalid, adjacent floor does not exist,
                    or no candidates exist.
    """
    current_floor = building.floors.get(space.floor_id)
    if current_floor is None:
        raise ValueError(f"Floor '{space.floor_id}' not found for space '{space.id}'")

    direction_normalized = target_direction.strip().lower()
    if direction_normalized in ("above", "up", "top", "+1"):
        target_level = current_floor.level + 1
    elif direction_normalized in ("below", "down", "bottom", "-1"):
        target_level = current_floor.level - 1
    else:
        raise ValueError(
            f"Invalid target direction '{target_direction}'. Expected 'above' or 'below'."
        )

    target_floor = building.floors_by_level.get(target_level)
    if target_floor is None:
        raise ValueError(
            f"No adjacent floor at level {target_level} (direction '{target_direction}' from level {current_floor.level})"
        )

    candidates = building.spaces_by_floor.get(target_floor.id, [])
    if not candidates:
        raise ValueError(f"No spaces found on target floor '{target_floor.id}'")

    poly_base = space.polygon
    best_space: Optional[Space] = None
    max_overlap = 0.0

    for cand in candidates:
        try:
            inter = poly_base.intersection(cand.polygon)
            overlap = float(inter.area)
        except Exception:
            overlap = 0.0

        if overlap > max_overlap and overlap > 1e-6:
            max_overlap = overlap
            best_space = cand

    if best_space is None:
        raise ValueError(
            f"Unable to find overlapping space on floor {target_floor.id}"
        )

    return best_space, max_overlap


def is_valid_shared_wall_room(space: Space) -> bool:
    """Predicate determining if a space qualifies as a room for shared wall calculations.

    Excludes corridors, stairwells, lifts, balconies, and outdoor spaces.
    """
    stype = space.type.strip().lower()
    rtype = space.room_type.strip().lower()

    if stype in EXCLUDED_TYPES:
        return False
    if rtype in EXCLUDED_ROOM_TYPES:
        return False
    return True


def _get_ring_segments(
    ring,
) -> list[tuple[tuple[float, float], tuple[float, float], float, float, float, LineString]]:
    """Extract individual linear segments from a LinearRing with precomputed lengths and vectors."""
    if ring is None or ring.is_empty:
        return []
    coords = list(ring.coords)
    segs = []
    for i in range(len(coords) - 1):
        p1, p2 = coords[i], coords[i + 1]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length > 1e-6:
            segs.append((p1, p2, dx, dy, length, LineString([p1, p2])))
    return segs


def _directional_shared_length(
    space_a: Space, space_b: Space, buffer_dist: float = 0.35
) -> float:
    """Measure contact length of space_b edges running parallel along space_a edges within buffer_dist."""
    target_segs = _get_ring_segments(space_a.polygon.exterior)
    cand_segs = _get_ring_segments(space_b.polygon.exterior)
    if not target_segs or not cand_segs:
        return 0.0

    total_length = 0.0
    for cp1, cp2, cdx, cdy, clen, c_line in cand_segs:
        parallel_t_bufs = []
        for tp1, tp2, tdx, tdy, tlen, t_line in target_segs:
            # Check parallel / collinear orientation: |cos theta| >= 0.8
            cos_theta = abs(tdx * cdx + tdy * cdy) / (tlen * clen)
            if cos_theta >= 0.8:
                parallel_t_bufs.append(t_line.buffer(buffer_dist, cap_style="flat"))
        if parallel_t_bufs:
            u = unary_union(parallel_t_bufs)
            inter = u.intersection(c_line)
            if not inter.is_empty:
                total_length += float(inter.length)
    return total_length


def get_shared_boundary(
    space_a: Space, space_b: Space, buffer_dist: float = 0.35
) -> float:
    """Calculate the shared wall contact length between two spaces.

    Measures mutual wall contact along parallel boundary segments without
    perpendicular end-cap dilation inflation.
    """
    try:
        l1 = _directional_shared_length(space_a, space_b, buffer_dist)
        l2 = _directional_shared_length(space_b, space_a, buffer_dist)
        return max(l1, l2)
    except Exception:
        return 0.0


def get_shared_wall_spaces(
    target_space: Space,
    building: Building,
    min_length: float = 1.0,
    buffer_dist: float = 0.35,
) -> list[tuple[Space, float]]:
    """Find all distinct qualifying rooms sharing a wall with target_space >= min_length.

    Args:
        target_space: Reference Space.
        building: Building instance.
        min_length: Minimum contact length in metres (default 1.0 m).
        buffer_dist: Wall thickness buffer in metres (default 0.35 m).

    Returns:
        List of (qualifying_space, contact_length_m) sorted by contact length descending.
    """
    floor_spaces = building.spaces_by_floor.get(target_space.floor_id, [])
    results: list[tuple[Space, float]] = []

    for candidate in floor_spaces:
        if candidate.id == target_space.id:
            continue
        if not is_valid_shared_wall_room(candidate):
            continue

        try:
            inter_len = get_shared_boundary(target_space, candidate, buffer_dist)
        except Exception:
            inter_len = 0.0

        if inter_len >= min_length - 1e-6:
            results.append((candidate, inter_len))

    results.sort(key=lambda item: item[1], reverse=True)
    return results


def count_shared_walls(
    target_space: Space,
    building: Building,
    min_length: float = 1.0,
    buffer_dist: float = 0.35,
) -> int:
    """Count distinct rooms sharing a wall of at least min_length with target_space.

    Corridors, stairwells, lifts, balconies, and outdoor spaces are excluded.

    Args:
        target_space: Target Space.
        building: Building instance.
        min_length: Minimum contact length threshold (default 1.0 m).
        buffer_dist: Wall thickness dilation buffer (default 0.35 m).

    Returns:
        Integer count of matching rooms.
    """
    return len(
        get_shared_wall_spaces(
            target_space=target_space,
            building=building,
            min_length=min_length,
            buffer_dist=buffer_dist,
        )
    )


def is_point_in_space(space: Space, point: tuple[float, float]) -> bool:
    """Check if 2D coordinate point (x, y) is inside or on the boundary of space."""
    pt = Point(point[0], point[1])
    return bool(space.polygon.contains(pt) or space.polygon.touches(pt))
