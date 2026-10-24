"""Routes: shortest path under constraints, multi-stop tours, plus the followable guide
(floorwise.core.instructions) and a polyline for drawing."""

import itertools
import math
from dataclasses import asdict, dataclass, field

from floorwise.core.graph import DOOR_PREFIX, Constraints, RouteGraph
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

    def to_dict(self) -> dict:
        return asdict(self)


class NoRoute(ValueError):
    pass


def plan_route(building: Building, stops: list[str], constraints: Constraints = Constraints()) -> Route:
    graph = RouteGraph(building, constraints, keep=frozenset(stops))
    legs, total, all_nodes = [], 0.0, []
    for start, end in itertools.pairwise(stops):
        found = graph.shortest(start, end)
        if found is None:
            raise NoRoute(
                f"No route from {building.label(start)} to {building.label(end)}"
                + (f" ({'; '.join(constraints.describe())})" if constraints.describe() else "")
            )
        length, nodes = found
        elements = []
        for first, second in itertools.pairwise(nodes):
            elements.append(graph.edge_via(first, second)["via"])
        legs.append(Leg(start, end, round(length, 2), nodes,
                        [n for n in nodes if not n.startswith(DOOR_PREFIX)], elements))
        total += length
        all_nodes += nodes if not all_nodes else nodes[1:]
    # The dataset sums rounded legs; doing the same keeps tours equal to the centimetre.
    route = Route(stops=stops, length_m=round(sum(leg.length_m for leg in legs), 2), legs=legs,
                  constraints=constraints.describe())
    route.guide = guide(building, graph, all_nodes)
    route.steps = [step["text"] for step in route.guide["steps"]]
    route.polyline = polyline(building, graph, all_nodes)
    route.floors = list(dict.fromkeys(p["floor_id"] for p in route.polyline))
    return route


def polyline(building: Building, graph: RouteGraph, nodes: list[str]) -> list[dict]:
    points = []
    for node in nodes:
        point = point_of(building, graph, node)
        if point:
            points.append({"floor_id": point[0], "x": round(point[1], 3), "y": round(point[2], 3), "node": node})
    return points
