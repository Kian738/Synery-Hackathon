"""Humane walking paths. The route graph decides WHICH rooms and doors; this module decides HOW a person
walks through each room: around furniture and machines, away from walls, with straight lines where
nothing is in the way. Without it a route is drawn anchor -> door -> anchor and cuts through tables.

Per space: rasterise the polygon (0.2 m cells), mark furniture footprints as blocked, compute clearance
(distance to the nearest wall or obstacle), run A* with a penalty for low clearance, then smooth the cell
path by line of sight. Results are cached per (space, from, to)."""

import heapq
import math
from functools import lru_cache

import cv2
import numpy as np
from matplotlib.path import Path as MplPath
from shapely.geometry import LineString, MultiPolygon, Polygon

from floorwise.core.model import Building

CELL_M = 0.2
DESIRED_CLEARANCE_M = 0.9
CLEARANCE_WEIGHT = 2.5
OBSTACLE_MARGIN_M = 0.2
WALKABLE_CLEARANCE_M = 0.2
BLOCKING_CATEGORIES = {"furniture", "machine", "equipment", "fixture"}
DOOR_CLEAR_M = 0.3


class WalkBlocked(ValueError):
    def __init__(self, space_id: str):
        self.space_id = space_id
        super().__init__(f"No validated walking passage through {space_id}")


class Grid:
    def __init__(self, building: Building, space_id: str) -> None:
        polygon = building.polygons[space_id]
        if isinstance(polygon, MultiPolygon) or polygon.geom_type != "Polygon":
            polygon = max(getattr(polygon, "geoms", [polygon]), key=lambda p: p.area)
            if polygon.geom_type != "Polygon":
                polygon = Polygon(building.spaces[space_id]["polygon"]).convex_hull
        minx, miny, maxx, maxy = polygon.bounds
        self.ox, self.oy = minx - CELL_M, miny - CELL_M
        self.w = int(math.ceil((maxx - minx) / CELL_M)) + 3
        self.h = int(math.ceil((maxy - miny) / CELL_M)) + 3
        # A cell is inside the room only if its centre is (rasterising alone leaks half a cell past walls,
        # which matters in thin corridors).
        cols, rows = np.meshgrid(np.arange(self.w), np.arange(self.h))
        centres = np.column_stack([self.ox + cols.ravel() * CELL_M, self.oy + rows.ravel() * CELL_M])
        room_mask = MplPath(np.asarray(polygon.exterior.coords)).contains_points(centres).reshape(self.h, self.w).astype(np.uint8)
        if room_mask.sum() < 2:  # rooms thinner than a cell: fall back to the rasterised outline
            room_mask = np.zeros((self.h, self.w), np.uint8)
            cv2.fillPoly(room_mask, [self._px(polygon.exterior.coords)], 1)
        mask = room_mask.copy()
        for asset in building.assets.values():
            if asset["space_id"] != space_id or asset.get("category") not in BLOCKING_CATEGORIES:
                continue
            footprint = asset.get("footprint") or {}
            width = footprint.get("width_m", 0.5) + 2 * OBSTACLE_MARGIN_M
            depth = footprint.get("depth_m", 0.5) + 2 * OBSTACLE_MARGIN_M
            angle = math.radians(footprint.get("rotation_deg", 0.0))
            cx, cy = asset["position"]
            corners = []
            for dx, dy in ((-width / 2, -depth / 2), (width / 2, -depth / 2), (width / 2, depth / 2), (-width / 2, depth / 2)):
                corners.append((cx + dx * math.cos(angle) - dy * math.sin(angle), cy + dx * math.sin(angle) + dy * math.cos(angle)))
            cv2.fillPoly(mask, [self._px(corners)], 0)
        # Doorways stay walkable even when furniture stands close to them.
        door_mask = np.zeros_like(mask)
        for opening in building.openings.values():
            if space_id in opening["space_ids"]:
                x, y = opening["position"]
                cv2.circle(door_mask, (int(round((x - self.ox) / CELL_M)), int(round((y - self.oy) / CELL_M))),
                           max(1, int(round(DOOR_CLEAR_M / CELL_M))), 1, -1)
        mask = np.maximum(mask, door_mask & room_mask)
        self.inside = room_mask
        self.open = mask.astype(bool)  # inside the room and not under furniture (no clearance rule)
        self.clearance = cv2.distanceTransform(mask, cv2.DIST_L2, 5) * CELL_M
        self.free = self.clearance >= WALKABLE_CLEARANCE_M
        # Near doors the clearance rule is waived (but furniture still blocks), so the walk reaches the door
        # itself instead of a free cell metres away followed by a straight hop through a sofa.
        near = cv2.dilate(door_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * int(1.0 / CELL_M) + 1,) * 2))
        self.free |= near.astype(bool) & self.open
        if not self.free.any():  # tiny rooms: anything inside counts
            self.free = mask.astype(bool) | self.inside.astype(bool)
        # Walkable = not under furniture. Clearance is a cost preference (in astar), not a hard rule, so rooms
        # that furniture nearly splits stay connected instead of producing blind straight hops.
        self.free = self.free | self.open
        # A* forbids diagonal corner cutting. Its connected regions therefore match
        # four-neighbour connectivity, not diagonal-only contacts between obstacles.
        _, self.components = cv2.connectedComponents(self.free.astype(np.uint8), connectivity=4)

    def _px(self, coords) -> np.ndarray:
        return np.array([[int(round((x - self.ox) / CELL_M)), int(round((y - self.oy) / CELL_M))] for x, y in coords], np.int32)

    def cell(self, x: float, y: float) -> tuple[int, int]:
        return (min(self.h - 1, max(0, int(round((y - self.oy) / CELL_M)))), min(self.w - 1, max(0, int(round((x - self.ox) / CELL_M)))))

    def point(self, cell: tuple[int, int]) -> tuple[float, float]:
        return (self.ox + cell[1] * CELL_M, self.oy + cell[0] * CELL_M)

    def nearest_free(self, cell: tuple[int, int], component: int | None = None) -> tuple[int, int] | None:
        """Nearest walkable cell; with component, only cells reachable from that region (no boxed-in pockets)."""
        if self.free[cell] and (component is None or self.components[cell] == component):
            return cell
        allowed = self.free if component is None else (self.components == component)
        ys, xs = np.nonzero(allowed)
        if not len(ys):
            return None
        index = int(np.argmin((ys - cell[0]) ** 2 + (xs - cell[1]) ** 2))
        return (int(ys[index]), int(xs[index]))

    def visible(self, a: tuple[int, int], b: tuple[int, int]) -> bool:
        steps = max(abs(a[0] - b[0]), abs(a[1] - b[1])) * 4 + 1
        for t in np.linspace(0, 1, steps):
            r = int(round(a[0] + (b[0] - a[0]) * t))
            c = int(round(a[1] + (b[1] - a[1]) * t))
            if not self.free[r, c] or self.clearance[r, c] < WALKABLE_CLEARANCE_M + 0.15:
                return False
        return True

    def astar(self, start: tuple[int, int], goal: tuple[int, int], passable: np.ndarray | None = None,
              extra_cost: np.ndarray | None = None) -> list[tuple[int, int]] | None:
        passable = self.free if passable is None else passable
        moves = [(-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1), (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]
        penalty = 1 + CLEARANCE_WEIGHT * np.clip((DESIRED_CLEARANCE_M - self.clearance) / DESIRED_CLEARANCE_M, 0, 1)
        if extra_cost is not None:
            penalty = penalty + extra_cost
        best = {start: 0.0}
        parent = {}
        queue = [(0.0, start)]
        while queue:
            _, here = heapq.heappop(queue)
            if here == goal:
                path = [here]
                while here in parent:
                    here = parent[here]
                    path.append(here)
                return path[::-1]
            for dr, dc, length in moves:
                r, c = here[0] + dr, here[1] + dc
                if not (0 <= r < self.h and 0 <= c < self.w) or not passable[r, c]:
                    continue
                if dr and dc and (not passable[here[0], c] or not passable[r, here[1]]):
                    continue
                cost = best[here] + length * penalty[r, c]
                if cost < best.get((r, c), float("inf")):
                    best[(r, c)] = cost
                    parent[(r, c)] = here
                    heapq.heappush(queue, (cost + math.hypot(goal[0] - r, goal[1] - c), (r, c)))
        return None

    def clear_xy(self, p: tuple[float, float], q: tuple[float, float], doors: tuple = (), relaxed: bool = False) -> bool:
        """Line of sight in metres, sampled every 10 cm: every sample walkable and away from obstacles.
        The first and last 0.45 m may be in a doorway's tight cells."""
        length = math.dist(p, q)
        steps = max(2, int(length / 0.1) + 1)
        for k in range(steps + 1):
            t = k / steps
            x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
            r, c = self.cell(x, y)
            near_end = any(math.dist((x, y), d) < 0.45 for d in doors)
            walkable = self.open[r, c] if relaxed else self.free[r, c]
            if not walkable and not (near_end and self.inside[r, c]):
                return False
            if not near_end and self.clearance[r, c] < (0.12 if relaxed else WALKABLE_CLEARANCE_M + 0.1):
                return False
        return True

    def smooth_points(self, points: list[tuple[float, float]], relaxed: bool = False) -> list[tuple[float, float]]:
        if len(points) <= 2:
            return points
        out, i = [points[0]], 0
        doors = (points[0], points[-1])
        while i < len(points) - 1:
            j = len(points) - 1
            while j > i + 1 and not self.clear_xy(points[i], points[j], doors, relaxed):
                j -= 1
            out.append(points[j])
            i = j
        return out

    def smooth(self, cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if len(cells) <= 2:
            return cells
        out = [cells[0]]
        i = 0
        while i < len(cells) - 1:
            j = len(cells) - 1
            while j > i + 1 and not self.visible(cells[i], cells[j]):
                j -= 1
            out.append(cells[j])
            i = j
        return out


_grids: dict[tuple[int, str], Grid] = {}
# Spaces where the furniture in the data leaves no free path between two doors (reported by evals).
BLOCKED: set[str] = set()


def grid(building: Building, space_id: str) -> Grid:
    key = (id(building), space_id)
    if key not in _grids:
        if len(_grids) > 4000:
            _grids.clear()
        _grids[key] = Grid(building, space_id)
    return _grids[key]


def walk_in_space(building: Building, space_id: str, a: tuple[float, float], b: tuple[float, float],
                  a_door: bool = True, b_door: bool = True) -> list[tuple[float, float]]:
    """Walking line from a to b inside one space. a/b are door positions (kept exactly) or room points
    (start/end of a route, after a lift), which are moved to the nearest free spot."""
    points = list(_walk(id(building), building, space_id, (round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3)), a_door, b_door))
    if len(points) < 2:
        return points
    from floorwise.core.walk_domain import repair_nested_crossings
    try:
        points = repair_nested_crossings(building, space_id, points, a_door, b_door)
    except ValueError:
        raise WalkBlocked(space_id)
    line = LineString(points)
    if not building.polygons[space_id].buffer(0.35).covers(line):
        raise WalkBlocked(space_id)
    for asset in building.assets.values():
        if asset['space_id'] != space_id or asset.get('category') not in BLOCKING_CATEGORIES:
            continue
        f = asset.get('footprint') or {}
        w, d = f.get('width_m', 0.5), f.get('depth_m', 0.5)
        angle = math.radians(f.get('rotation_deg', 0))
        x, y = asset['position']
        obstacle = Polygon([(x + dx*math.cos(angle)-dy*math.sin(angle), y + dx*math.sin(angle)+dy*math.cos(angle))
                            for dx,dy in [(-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2)]])
        if line.intersection(obstacle.buffer(-0.01)).length > 0.02:
            raise WalkBlocked(space_id)
    return points


def corridor_spine(building: Building, space_id: str, a: tuple[float,float], b: tuple[float,float]):
    """Straight central run through an empty convex corridor, with perpendicular door approaches.

    This is display/walking geometry only. It cannot bypass a door, obstacle or concave corner.
    Raster noise must not make an empty, straight hallway look like a slalom.
    """
    if building.spaces[space_id]['type'] != 'corridor':
        return None
    polygon=building.polygons[space_id]
    if polygon.geom_type!='Polygon' or polygon.interiors or polygon.convex_hull.area-polygon.area>1e-5:
        return None
    if any(asset['space_id']==space_id and asset.get('category') in BLOCKING_CATEGORIES for asset in building.assets.values()):
        return None
    rect=list(polygon.minimum_rotated_rectangle.exterior.coords)[:4]
    edges=[(math.dist(rect[i],rect[(i+1)%4]),rect[i],rect[(i+1)%4]) for i in range(4)]
    long,first,last=max(edges);width=min(e[0] for e in edges)
    if width<.5 or long<3*width:
        return None
    axis=((last[0]-first[0])/long,(last[1]-first[1])/long)
    if abs((b[0]-a[0])*axis[0]+(b[1]-a[1])*axis[1])<2*width:
        return None
    centre=(sum(p[0] for p in rect)/4,sum(p[1] for p in rect)/4)
    limit=long/2-min(width/2,.35)
    def project(p):
        distance=max(-limit,min(limit,(p[0]-centre[0])*axis[0]+(p[1]-centre[1])*axis[1]))
        return (centre[0]+distance*axis[0],centre[1]+distance*axis[1])
    points=_dedupe([a,project(a),project(b),b])
    return points if polygon.buffer(.02).covers(LineString(points)) else None


@lru_cache(maxsize=20000)
def _walk(_key: int, building: Building, space_id: str, a: tuple[float, float], b: tuple[float, float],
          a_door: bool = True, b_door: bool = True) -> tuple:
    central=corridor_spine(building,space_id,a,b)
    if central is not None:
        return tuple(central)
    try:
        g = grid(building, space_id)
    except Exception:  # noqa: BLE001 - degenerate polygons: fall back to a straight line
        raise WalkBlocked(space_id)
    start = g.nearest_free(g.cell(*a))
    goal = g.nearest_free(g.cell(*b))
    if start is None or goal is None:
        raise WalkBlocked(space_id)
    if g.components[start] != g.components[goal]:
        if a_door and b_door:
            # The data's furniture walls these two doors off. Squeeze through with the least furniture overlap.
            BLOCKED.add(space_id)
            inside = g.inside.astype(bool)
            cells = g.astar(start, goal, inside, extra_cost=np.where(g.open, 0.0, 25.0))
            if cells:
                raw = [a] + [g.point(c) for c in cells] + [b]
                return tuple(_dedupe(raw[:1] + raw[1:-1:2] + raw[-1:]))
            raise WalkBlocked(space_id)
        # A route end (not a door) in a boxed-in pocket: use the nearest spot reachable from the door.
        if a_door:
            goal = g.nearest_free(g.cell(*b), g.components[start])
        else:
            start = g.nearest_free(g.cell(*a), g.components[goal])
    cells = g.astar(start, goal)
    strict = True
    if not cells:
        # Narrow or oddly shaped room: walk anywhere inside it rather than drawing a line through walls.
        cells = g.astar(start, goal, g.open | g.free)
        strict = False
        if not cells:
            raise WalkBlocked(space_id)
    raw = ([a] if a_door else []) + [g.point(c) for c in cells] + ([b] if b_door else [])
    points = g.smooth_points(raw, relaxed=not strict)
    return tuple(_dedupe(points))


def _dedupe(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = [points[0]]
    for p in points[1:]:
        if math.dist(p, out[-1]) > 0.05:
            out.append(p)
    return out


def length(points: list[tuple[float, float]]) -> float:
    return sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def invalidate(building: Building) -> None:
    """Drop occupancy caches after a session changes doors or furniture."""
    for key in list(_grids):
        if key[0] == id(building):
            del _grids[key]
    _walk.cache_clear()
