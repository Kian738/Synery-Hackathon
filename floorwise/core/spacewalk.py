"""Walking inside a space: the official route model (kit README section 3, kit version 1.1.0).

Between every pair of a space's nodes (its centre point and each of its openings) the walk is the shortest path
inside the space that stays 15 cm off the walls and goes round corners, never through them. It is computed on
polygon.buffer(-0.15) with a visibility graph over the two end points and the corners of that shrunken outline
(a segment is clear if buffer(0.02) of the shrunken outline covers it). An opening "lands" 30 cm inside each space
and the step from the opening to its landing is added. Furniture is never an obstacle. Edge lengths are rounded to
3 decimals by the caller.

This is an independent implementation of the written rules. eval.differential compares it with the kit's own
starter_agent/building_map.py, and eval.routes compares it with every expected answer to the centimetre."""

import itertools
import math
import pickle
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points

WALL_CLEARANCE_M = 0.15
DOOR_LANDING_M = 0.30
NARROW_LANDING_M = 0.05
COVER_TOLERANCE_M = 0.02
BLOCKED_DETOUR_FACTOR = 1.5  # when no clear walk exists between two points of a space
CACHE_VERSION = 1
DOOR_PREFIX = "door:"

Point2 = tuple[float, float]


def outline(points) -> Polygon:
    polygon = Polygon(points)
    return polygon if polygon.is_valid else polygon.buffer(0)


def anchor_of(polygon: Polygon) -> Point2:
    point = polygon.representative_point()
    return (point.x, point.y)


def door_landing(polygon: Polygon, position: Point2) -> Point2:
    """Where a door at `position` lands inside the space: 30 cm in from the walls."""
    inner = polygon.buffer(-DOOR_LANDING_M)
    if inner.is_empty:
        inner = polygon.buffer(-NARROW_LANDING_M)
    if inner.is_empty:
        return anchor_of(polygon)
    if inner.contains(Point(position)):
        return (position[0], position[1])
    landing = nearest_points(inner, Point(position))[0]
    return (landing.x, landing.y)


def _visibility(allowed: Polygon, nodes: list[Point2]) -> np.ndarray:
    coordinates = np.asarray(nodes, dtype=float)
    diff = coordinates[:, None, :] - coordinates[None, :, :]
    straight = np.hypot(diff[..., 0], diff[..., 1])
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


def walking_lengths(polygon: Polygon, points: list[Point2]) -> np.ndarray:
    """k x k matrix of shortest walks between `points` inside the polygon (15 cm off the walls, round corners)."""
    walkable = polygon.buffer(-WALL_CLEARANCE_M)
    if walkable.is_empty or walkable.geom_type != "Polygon":
        walkable = polygon
    allowed = walkable.buffer(COVER_TOLERANCE_M)
    corners = [c for ring in [walkable.exterior, *walkable.interiors] for c in list(ring.coords)[:-1]]
    walks = _all_pairs(_visibility(allowed, list(points) + corners))[: len(points), : len(points)]
    out = np.empty_like(walks)
    for i, j in itertools.product(range(len(points)), repeat=2):
        w = float(walks[i, j])
        out[i, j] = w if math.isfinite(w) else math.dist(points[i], points[j]) * BLOCKED_DETOUR_FACTOR
    return out


def space_edges(space: dict, openings: list[dict]) -> list[tuple[str, str, float]]:
    """Edges inside one space: (centre or door node, door node, metres). `openings` are the ones touching it."""
    polygon = outline(space["polygon"])
    members: list[tuple[str, Point2, float]] = [(space["id"], anchor_of(polygon), 0.0)]
    for opening in openings:
        position = (opening["position"][0], opening["position"][1])
        landing = door_landing(polygon, position)
        members.append((DOOR_PREFIX + opening["id"], landing, math.dist(landing, position)))
    lengths = walking_lengths(polygon, [landing for _, landing, _ in members])
    return [
        (members[a][0], members[b][0], float(lengths[a, b]) + members[a][2] + members[b][2])
        for a, b in itertools.combinations(range(len(members)), 2)
    ]


def path_inside(space: dict, openings: list[dict], first: str, second: str) -> list[Point2]:
    """The drawn polyline of one edge: where the walk actually goes (landing points and wall corners)."""
    polygon = outline(space["polygon"])
    members: dict[str, tuple[Point2, Point2]] = {space["id"]: (anchor_of(polygon),) * 2}  # type: ignore[dict-item]
    for opening in openings:
        position = (opening["position"][0], opening["position"][1])
        members[DOOR_PREFIX + opening["id"]] = (position, door_landing(polygon, position))
    walkable = polygon.buffer(-WALL_CLEARANCE_M)
    if walkable.is_empty or walkable.geom_type != "Polygon":
        walkable = polygon
    allowed = walkable.buffer(COVER_TOLERANCE_M)
    a_pos, a_land = members[first]
    b_pos, b_land = members[second]
    corners = [c for ring in [walkable.exterior, *walkable.interiors] for c in list(ring.coords)[:-1]]
    nodes = [a_land, b_land] + corners
    matrix = _visibility(allowed, nodes)
    n = len(nodes)
    dist = np.full(n, np.inf); dist[0] = 0.0
    prev = [-1] * n
    done = [False] * n
    for _ in range(n):
        u = min((i for i in range(n) if not done[i]), key=lambda i: dist[i], default=None)
        if u is None or not math.isfinite(dist[u]):
            break
        done[u] = True
        for v in range(n):
            if not done[v] and dist[u] + matrix[u, v] < dist[v]:
                dist[v] = dist[u] + matrix[u, v]
                prev[v] = u
    if not math.isfinite(dist[1]):
        chain = [a_land, b_land]
    else:
        chain, cursor = [], 1
        while cursor != -1:
            chain.append(nodes[cursor]); cursor = prev[cursor]
        chain.reverse()
    points = [a_pos] if a_pos != a_land else []
    points += chain
    if b_pos != b_land:
        points.append(b_pos)
    deduped = [points[0]]
    for p in points[1:]:
        if math.dist(p, deduped[-1]) > 1e-9:
            deduped.append(p)
    return deduped


def polyline_between(polygon: Polygon, p: Point2, q: Point2) -> list[Point2]:
    """The official walk between two points of a space, as a drawable polyline (furniture ignored)."""
    walkable = polygon.buffer(-WALL_CLEARANCE_M)
    if walkable.is_empty or walkable.geom_type != "Polygon":
        walkable = polygon
    allowed = walkable.buffer(COVER_TOLERANCE_M)
    corners = [c for ring in [walkable.exterior, *walkable.interiors] for c in list(ring.coords)[:-1]]
    nodes = [p, q] + corners
    matrix = _visibility(allowed, nodes)
    n = len(nodes)
    dist = np.full(n, np.inf)
    dist[0] = 0.0
    prev = np.full(n, -1)
    done = np.zeros(n, bool)
    for _ in range(n):
        masked = np.where(done, np.inf, dist)
        u = int(np.argmin(masked))
        if not np.isfinite(masked[u]) or u == 1:
            break
        done[u] = True
        cand = dist[u] + matrix[u]
        better = (cand < dist) & ~done
        dist[better] = cand[better]
        prev[better] = u
    if not np.isfinite(dist[1]):
        return [p, q]
    chain, k = [], 1
    while k != -1:
        chain.append(nodes[k])
        k = int(prev[k])
    return chain[::-1]


# ---------- per-building cache (memory, plus an on-disk copy of the unchanged building) ----------

def _disk_path(building) -> Path | None:
    directory = getattr(building, "directory", None)
    if directory is None:
        return None
    file = Path(directory) / "building.json"
    try:
        stat = file.stat()
    except OSError:
        return None
    root = Path(__file__).resolve().parents[2] / "runs" / ".walk-cache"
    return root / f"{building.id}-{stat.st_size}-{stat.st_mtime_ns}-v{CACHE_VERSION}.pkl"


def base_edges(building) -> dict[str, list[tuple[str, str, float]]]:
    """Walking edges of every space for the building as supplied (no what-if doors). Cached."""
    cached = getattr(building, "_base_walks", None)
    if cached is not None:
        return cached
    path = _disk_path(building)
    if path is not None and path.exists():
        try:
            building._base_walks = pickle.loads(path.read_bytes())
            return building._base_walks
        except Exception:  # noqa: BLE001 - a corrupt cache is just recomputed
            pass
    touching: dict[str, list[dict]] = {sid: [] for sid in building.spaces}
    for opening in building.openings.values():
        for sid in dict.fromkeys(opening["space_ids"]):
            if sid in touching:
                touching[sid].append(opening)
    edges = {sid: space_edges(space, touching[sid]) for sid, space in building.spaces.items()}
    building._base_walks = edges
    if path is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(pickle.dumps(edges))
        except OSError:
            pass
    return edges


def edges_with(building, space_id: str, extra: tuple[dict, ...]) -> list[tuple[str, str, float]]:
    """Edges of one space when extra openings (what-if doors) also touch it. Cached per distinct extra set."""
    mine = tuple(o for o in extra if space_id in o["space_ids"])
    if not mine:
        return base_edges(building)[space_id]
    cache = building.__dict__.setdefault("_extra_walks", {})
    key = (space_id, tuple((o["id"], o["position"][0], o["position"][1]) for o in mine))
    if key not in cache:
        base = [o for o in building.openings.values() if space_id in o["space_ids"]]
        cache[key] = space_edges(building.spaces[space_id], base + list(mine))
    return cache[key]
