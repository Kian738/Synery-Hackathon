"""Walking inside one space, as the organisers grade it (kit v1.1.0, README section 3).

A person keeps 15 cm off the walls, walks round corners and never through walls; a door lands 30 cm inside
the space. Between any two points of a space the length is a shortest path over a visibility graph made of
those points and the corners of the walkable area. Lengths are cached per (building, space, its doors), so a
what-if door only recomputes the two spaces it touches."""

import hashlib
import itertools
import json
import math
import os
import pickle

import numpy as np
import shapely
from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points

from floorwise.core.model import Building
from floorwise.paths import ROOT

WALL_CLEARANCE_M = 0.15
DOOR_LANDING_M = 0.30
NARROW_LANDING_M = 0.05  # used when a space is too narrow for a 30 cm landing
COVER_TOLERANCE_M = 0.02
BLOCKED_DETOUR_FACTOR = 1.5  # no clear walk between two points: straight line times this
LENGTH_DECIMALS = 3

Point2 = tuple[float, float]
# (first member, second member, walking length incl. door offsets) per pair; members are the space id or "door:<id>"
Walk = tuple[str, str, float]

_CACHE: dict[tuple, list[Walk]] = {}
_LOADED: set[str] = set()  # buildings whose saved walks were read
_DIRTY: set[str] = set()  # buildings with walks computed since they were last saved
CACHE_DIR = ROOT / ".cache" / "walks"


def outline(points: list[Point2]) -> Polygon:
    polygon = Polygon(points)
    return polygon if polygon.is_valid else polygon.buffer(0)


def anchor_point(polygon: Polygon) -> Point2:
    point = polygon.representative_point()
    return (point.x, point.y)


def door_landing(polygon: Polygon, position: Point2) -> Point2:
    """Where a door at `position` lands inside the space."""
    inner = polygon.buffer(-DOOR_LANDING_M)
    if inner.is_empty:
        inner = polygon.buffer(-NARROW_LANDING_M)
    if inner.is_empty:
        return anchor_point(polygon)
    if inner.contains(Point(position)):
        return (position[0], position[1])
    landing = nearest_points(inner, Point(position))[0]
    return (landing.x, landing.y)


def _visibility(allowed: Polygon, nodes: list[Point2]) -> np.ndarray:
    """Straight lengths between nodes that see each other inside `allowed`; infinity where a wall is in the way."""
    coordinates = np.asarray(nodes, dtype=float)
    straight = np.hypot(*(coordinates[:, None, :] - coordinates[None, :, :]).transpose(2, 0, 1))
    first, second = np.triu_indices(len(nodes), k=1)
    shapely.prepare(allowed)
    clear = shapely.covers(allowed, shapely.linestrings(np.stack([coordinates[first], coordinates[second]], axis=1)))
    usable = clear | (straight[first, second] == 0)
    matrix = np.full(straight.shape, np.inf)
    np.fill_diagonal(matrix, 0.0)
    matrix[first[usable], second[usable]] = straight[first[usable], second[usable]]
    matrix[second[usable], first[usable]] = straight[first[usable], second[usable]]
    return matrix


def _all_pairs(matrix: np.ndarray) -> np.ndarray:
    for middle in range(len(matrix)):
        matrix = np.minimum(matrix, matrix[:, middle, None] + matrix[None, middle, :])
    return matrix


def walking_lengths(polygon: Polygon, points: list[Point2]) -> dict[tuple[int, int], float]:
    walkable = polygon.buffer(-WALL_CLEARANCE_M)
    if walkable.is_empty or walkable.geom_type != "Polygon":
        walkable = polygon
    allowed = walkable.buffer(COVER_TOLERANCE_M)
    direct = _visibility(allowed, list(points))
    if np.isfinite(direct).all():
        walks = direct  # every point sees every other: straight lines are shortest, corners cannot help
    else:
        corners = [corner for ring in [walkable.exterior, *walkable.interiors] for corner in list(ring.coords)[:-1]]
        walks = _all_pairs(_visibility(allowed, list(points) + corners))
    lengths = {}
    for source in range(len(points)):
        for target in range(len(points)):
            walk = float(walks[source, target])
            lengths[(source, target)] = walk if math.isfinite(walk) else math.dist(points[source], points[target]) * BLOCKED_DETOUR_FACTOR
    return lengths


def _openings_by_space(building: Building) -> dict[str, list[dict]]:
    """Openings grouped by the spaces they touch, built once per building (rebuilt if openings were added)."""
    cached = getattr(building, "_openings_by_space", None)
    if cached is None or cached[0] != len(building.openings):
        grouped: dict[str, list[dict]] = {}
        for opening in building.openings.values():
            for space_id in opening["space_ids"]:
                grouped.setdefault(space_id, []).append(opening)
        cached = building._openings_by_space = (len(building.openings), grouped)
    return cached[1]


def doors_of(building: Building, space_id: str, extra_openings: tuple[dict, ...] = ()) -> list[dict]:
    """Every opening that touches the space, including what-if doors; a what-if door replaces one with its id."""
    if not extra_openings:
        return _openings_by_space(building).get(space_id, [])
    extra = {opening["id"]: opening for opening in extra_openings}
    openings = [extra.get(o["id"], o) for o in _openings_by_space(building).get(space_id, [])]
    return openings + [o for o in extra.values() if space_id in o["space_ids"] and o["id"] not in building.openings]


def _cache_file(building: Building):
    """Saved walks are keyed by the content of the space outlines, so edited geometry never reads stale lengths."""
    fingerprint = getattr(building, "_walk_fingerprint", None)
    if fingerprint is None:
        outlines = json.dumps([(sid, space["polygon"]) for sid, space in sorted(building.spaces.items())])
        fingerprint = building._walk_fingerprint = hashlib.md5(outlines.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{building.id}-{fingerprint}.pkl"


def _load(building: Building) -> None:
    if building.id in _LOADED or os.environ.get("FLOORWISE_NO_WALK_CACHE"):
        return
    _LOADED.add(building.id)
    try:
        saved = pickle.loads(_cache_file(building).read_bytes())
    except (OSError, pickle.UnpicklingError, EOFError):
        return
    _CACHE.update({(building.id, *key): walks for key, walks in saved.items()})


def save(building: Building) -> None:
    """Write this building's computed walks to disk (called after a graph build; cheap when nothing is new)."""
    if building.id not in _DIRTY or os.environ.get("FLOORWISE_NO_WALK_CACHE"):
        return
    _DIRTY.discard(building.id)
    mine = {key[1:]: walks for key, walks in _CACHE.items() if key[0] == building.id}
    path = _cache_file(building)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_bytes(pickle.dumps(mine))
    temporary.replace(path)


def space_walks(building: Building, space_id: str, doors: list[dict], door_prefix: str) -> list[Walk]:
    """Walking lengths between the space's anchor and each door, and between each pair of doors."""
    _load(building)
    key = (building.id, space_id, tuple((d["id"], d["position"][0], d["position"][1]) for d in doors))
    if key not in _CACHE:
        polygon = outline(building.spaces[space_id]["polygon"])
        members = [(space_id, anchor_point(polygon), 0.0)]
        for opening in doors:
            position = (opening["position"][0], opening["position"][1])
            landing = door_landing(polygon, position)
            members.append((door_prefix + opening["id"], landing, math.dist(landing, position)))
        lengths = walking_lengths(polygon, [landing for _, landing, _ in members])
        _CACHE[key] = [
            (members[a][0], members[b][0], lengths[(a, b)] + members[a][2] + members[b][2])
            for a, b in itertools.combinations(range(len(members)), 2)
        ]
        _DIRTY.add(building.id)
    return _CACHE[key]
