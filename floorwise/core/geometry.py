"""Plan geometry: areas, centroids in 3D, shared walls and vertical stacking, all from polygons."""

import math

from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import linemerge

from floorwise.core.model import Building

WALL_TOLERANCE_M = 0.35  # walls have thickness: outlines within this distance share a wall
MIN_SHARED_WALL_M = 1.0


def area(building: Building, space_id: str) -> float:
    return Polygon(building.spaces[space_id]["polygon"]).area


def centroid_3d(building: Building, space_id: str) -> tuple[float, float, float]:
    space = building.spaces[space_id]
    centre = Polygon(space["polygon"]).centroid
    return (centre.x, centre.y, building.elevation(space["floor_id"]))


def distance_3d(building: Building, first: str, second: str) -> float:
    return math.dist(centroid_3d(building, first), centroid_3d(building, second))


def shared_boundary(building: Building, first: str, second: str) -> LineString | MultiLineString | None:
    """The part of first's outline that runs within WALL_TOLERANCE_M of second's outline."""
    first_polygon, second_polygon = building.polygons[first], building.polygons[second]
    if first_polygon.distance(second_polygon) > WALL_TOLERANCE_M:
        return None
    shared = first_polygon.exterior.intersection(second_polygon.exterior.buffer(WALL_TOLERANCE_M))
    if shared.is_empty or shared.length == 0:
        return None
    return shared


def shared_wall_length(building: Building, first: str, second: str) -> float:
    shared = shared_boundary(building, first, second)
    return 0.0 if shared is None else shared.length


def wall_neighbours(building: Building, space_id: str, min_length: float = MIN_SHARED_WALL_M) -> list[tuple[str, float]]:
    """Spaces on the same floor whose wall runs along this one for at least min_length metres."""
    floor_id = building.spaces[space_id]["floor_id"]
    polygon = building.polygons[space_id]
    result = []
    for other in building.spaces_on(floor_id):
        other_id = other["id"]
        if other_id == space_id or polygon.distance(building.polygons[other_id]) > WALL_TOLERANCE_M:
            continue
        length = max(shared_wall_length(building, space_id, other_id), shared_wall_length(building, other_id, space_id))
        if length >= min_length:
            result.append((other_id, length))
    return result


def wall_midpoint(building: Building, first: str, second: str, avoid=()) -> tuple[float, float] | None:
    """Middle of the wall two spaces share: midpoint of the shared outline, snapped between both outlines.

    With `avoid` (furniture footprints) the door goes where the wall is clear: the candidate nearest the middle that keeps 0.6 m from every
    obstacle, else the one with the most room. A door on top of a shower cannot be walked through."""
    shared = shared_boundary(building, first, second)
    if shared is None:
        return None
    if isinstance(shared, MultiLineString) or shared.geom_type == "GeometryCollection":
        lines = [geometry for geometry in getattr(shared, "geoms", [shared]) if geometry.length > 0]
        merged = linemerge(lines) if lines else shared
        if merged.geom_type == "MultiLineString":
            merged = max(merged.geoms, key=lambda line: line.length)
        shared = merged
    other_exterior = building.polygons[second].exterior

    def snapped(fraction: float):
        middle = shared.interpolate(fraction, normalized=True)
        nearest = other_exterior.interpolate(other_exterior.project(middle))
        return ((middle.x + nearest.x) / 2, (middle.y + nearest.y) / 2)

    if not avoid or shared.length < 1.0:
        return snapped(0.5)
    from shapely.geometry import Point
    corners = [Point(c) for sid in (first, second) for c in list(building.polygons[sid].exterior.coords)]
    scored = []
    for rank, fraction in enumerate((0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8, 0.1, 0.9)):
        point = snapped(fraction)
        clearance = min(min(Point(point).distance(o) for o in avoid), min(Point(point).distance(c) for c in corners) * 1.2)  # never in a room corner either
        scored.append((clearance >= 0.6, -rank if clearance >= 0.6 else clearance, point))
    return max(scored, key=lambda s: (s[0], s[1]))[2]


def stacked(building: Building, space_id: str, direction: str) -> list[tuple[str, float]]:
    """Spaces on the next floor up/down, ranked by how much of this room's outline they cover."""
    space = building.spaces[space_id]
    levels = sorted(building.floors_by_level)
    index = levels.index(building.level(space["floor_id"]))
    neighbour_index = index + (1 if direction == "above" else -1)
    if not 0 <= neighbour_index < len(levels):
        return []
    floor_id = building.floors_by_level[levels[neighbour_index]]["id"]
    polygon = building.polygons[space_id]
    overlaps = []
    for other in building.spaces_on(floor_id):
        overlap = polygon.intersection(building.polygons[other["id"]]).area
        if overlap > 0:
            overlaps.append((other["id"], overlap))
    return sorted(overlaps, key=lambda item: -item[1])


def point_in_space(building: Building, floor_id: str, x: float, y: float) -> str | None:
    point = Point(x, y)
    for space in building.spaces_on(floor_id):
        if building.polygons[space["id"]].covers(point):
            return space["id"]
    return None
