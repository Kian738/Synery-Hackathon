"""Routes: shortest path under constraints, multi-stop tours, plus the followable guide
(floorwise.core.instructions) and a polyline for drawing."""

import itertools
import math
from dataclasses import asdict, dataclass, field

from floorwise.core.graph import DOOR_PREFIX, Constraints, RouteGraph
from floorwise.core import walk
from floorwise.core.instructions import guide, point_of
from floorwise.core.model import Building



@dataclass
class Leg:
    from_space_id: str
    to_space_id: str
    length_m: float
    nodes: list[str]
    space_path: list[str]
    element_path: list[str]


@dataclass
class Route:
    stops: list[str]
    length_m: float
    legs: list[Leg]
    steps: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    floors: list[str] = field(default_factory=list)
    polyline: list[dict] = field(default_factory=list)  # [{floor_id, x, y}] for drawing
    guide: dict = field(default_factory=dict)  # structured steps + spoken overview
    preview_available: bool = True
    warnings: list[str] = field(default_factory=list)
    walk_m: float | None = None  # humane walking length along the drawn path (navigation only)

    def to_dict(self) -> dict:
        return asdict(self)


class NoRoute(ValueError):
    pass


def plan_route(building: Building, stops: list[str], constraints: Constraints = Constraints(), humane: bool = False) -> Route:
    """humane=True: also compute real walking lines through each room (floorwise.core.walk) and use them for
    drawing, distances and turns. The graph length (length_m) is unchanged either way."""
    graph = RouteGraph(building, constraints, keep=frozenset(stops))
    legs, path = [], []
    for start, end in itertools.pairwise(stops):
        found = graph.shortest(start, end)
        if found is None:
            raise NoRoute(
                f"No route from {building.label(start)} to {building.label(end)}"
                + (f" ({'; '.join(constraints.describe())})" if constraints.describe() else "")
            )
        length, nodes = found
        spaces = [n for n in graph.expand(nodes) if not n.startswith(DOOR_PREFIX)]
        legs.append(Leg(start, end, round(length, 2), nodes, [n for i, n in enumerate(spaces) if not i or n != spaces[i - 1]],
                        graph.elements(nodes)))
        path += nodes if not path else nodes[1:]
    all_nodes = graph.expand(path)
    # The expected answers sum the rounded legs (the kit's own router rounds the exact sum, 0.01 m apart at most).
    route = Route(stops=stops, length_m=round(sum(leg.length_m for leg in legs), 2), legs=legs, constraints=constraints.describe())
    try:
        segments = walking_segments(building, graph, all_nodes) if humane else None
    except walk.WalkBlocked as error:
        if error.space_id in stops:
            raise NoRoute(f"No validated walking passage at {building.label(error.space_id)}; furniture or geometry blocks this route.") from error
        # Exclude the blocked space and re-plan; every retry strictly reduces available spaces.
        from dataclasses import replace
        return plan_route(building, stops, replace(constraints, closed=constraints.closed | {error.space_id}), humane=True)
    route.guide = guide(building, graph, all_nodes, segments)
    route.steps = [step["text"] for step in route.guide["steps"]]
    if segments:
        route.polyline = []
        previous = None
        for i in sorted(segments):
            # A new piece starts after a floor change: never join those with a line.
            gap = previous is not None and i - previous != 2  # 2 = through one door; 1 = lift/stairs
            for k, (x, y) in enumerate(segments[i]):
                route.polyline.append({"floor_id": building.spaces[all_nodes[i]]["floor_id"], "x": round(x, 3), "y": round(y, 3),
                                       "node": all_nodes[i], **({"gap": True} if gap and k == 0 else {})})
            previous = i
        route.walk_m = round(sum(walk.length(seg) for seg in segments.values()), 1)
    else:
        route.polyline = polyline(building, graph, all_nodes)
    route.floors = list(dict.fromkeys(p["floor_id"] for p in route.polyline))
    if humane:
        from floorwise.core.scene import compile_scene
        unsupported = set(compile_scene(building)['unmatched_openings'])
        used = {e for leg in route.legs for e in leg.element_path}
        if unsupported & used:
            route.preview_available = False
            route.warnings.append("Some route openings cannot be aligned with the supplied room boundaries. Use the floor plan; eye-level playback is unavailable.")
    return route


def polyline(building: Building, graph: RouteGraph, nodes: list[str]) -> list[dict]:
    points = []
    for node in nodes:
        point = point_of(building, graph, node)
        if point:
            points.append({"floor_id": point[0], "x": round(point[1], 3), "y": round(point[2], 3), "node": node})
    return points


def walking_segments(building: Building, graph: RouteGraph, nodes: list[str]) -> dict[int, list[tuple[float, float]]]:
    """For every space node in the route: the walking line through that space, from where the person enters
    (a door, or the room itself at the start / after a lift) to where they leave."""
    segments = {}
    for index, node in enumerate(nodes):
        if node.startswith(DOOR_PREFIX) or node not in building.spaces:
            continue
        floor = building.spaces[node]["floor_id"]
        here = point_of(building, graph, node)

        def door_point(neighbour: int):
            if 0 <= neighbour < len(nodes) and nodes[neighbour].startswith(DOOR_PREFIX):
                p = point_of(building, graph, nodes[neighbour])
                if p and p[0] == floor:
                    return (p[1], p[2])
            return None

        entry_door, exit_door = door_point(index - 1), door_point(index + 1)
        entry = entry_door or (here[1], here[2])
        exit_ = exit_door or (here[1], here[2])
        segments[index] = [entry] if entry == exit_ else walk.walk_in_space(
            building, node, entry, exit_, a_door=entry_door is not None, b_door=exit_door is not None)
    return segments
