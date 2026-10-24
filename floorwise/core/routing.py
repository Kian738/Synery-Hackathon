"""Routes people can follow: shortest path under constraints, multi-stop tours, and turn-by-turn steps
with landmarks ("turn left at the CNC mill")."""

import itertools
import math
from dataclasses import asdict, dataclass, field

from floorwise.core.graph import DOOR_PREFIX, Constraints, RouteGraph
from floorwise.core.model import OUTSIDE, Building

LANDMARK_RADIUS_M = 4.0
LANDMARK_CATEGORIES = ("machine", "equipment")


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
    route.steps = directions(building, graph, all_nodes)
    route.polyline = polyline(building, graph, all_nodes)
    route.floors = list(dict.fromkeys(p["floor_id"] for p in route.polyline))
    return route


def _point(building: Building, graph: RouteGraph, node: str) -> tuple[str, float, float] | None:
    if node == OUTSIDE:
        return None
    if node.startswith(DOOR_PREFIX):
        opening_id = node[len(DOOR_PREFIX):]
        opening = building.openings.get(opening_id) or next(
            (o for o in graph.constraints.extra_openings if o["id"] == opening_id), None)
        return (opening["floor_id"], opening["position"][0], opening["position"][1])
    from floorwise.core.graph import anchor

    x, y = anchor(building, node)
    return (building.spaces[node]["floor_id"], x, y)


def polyline(building: Building, graph: RouteGraph, nodes: list[str]) -> list[dict]:
    points = []
    for node in nodes:
        point = _point(building, graph, node)
        if point:
            points.append({"floor_id": point[0], "x": round(point[1], 3), "y": round(point[2], 3), "node": node})
    return points


def _turn(previous: tuple[float, float], here: tuple[float, float], following: tuple[float, float]) -> str:
    heading_in = math.atan2(here[1] - previous[1], here[0] - previous[0])
    heading_out = math.atan2(following[1] - here[1], following[0] - here[0])
    delta = math.degrees((heading_out - heading_in + math.pi) % (2 * math.pi) - math.pi)
    if abs(delta) < 30:
        return "go straight"
    if abs(delta) > 150:
        return "turn around"
    return "turn left" if delta > 0 else "turn right"


def landmark_near(building: Building, floor_id: str, x: float, y: float) -> str | None:
    best, best_distance = None, LANDMARK_RADIUS_M
    for asset in building.assets.values():
        if asset["floor_id"] != floor_id or asset.get("category") not in LANDMARK_CATEGORIES:
            continue
        distance = math.dist(asset["position"], (x, y))
        if distance < best_distance:
            best, best_distance = asset["type"].replace("_", " "), distance
    return best


def directions(building: Building, graph: RouteGraph, nodes: list[str]) -> list[str]:
    """One line per room change or floor change, with turn hints and nearby landmarks."""
    if not nodes:
        return []
    steps = [f"Start in {building.label(nodes[0])}."]
    walked = 0.0
    points = {node: _point(building, graph, node) for node in nodes}
    for index in range(1, len(nodes)):
        previous, current = nodes[index - 1], nodes[index]
        edge = graph.edge_via(previous, current)
        walked += edge["weight"]
        element = edge["via"]
        if element in building.connectors:
            connector = building.connectors[element]
            verb = "Take" if connector["kind"] == "lift" else "Use"
            steps.append(f"{verb} the {connector['name']} to {building.floor_name(building.spaces[current]['floor_id'])}.")
            walked = 0.0
        elif current == OUTSIDE:
            steps.append(f"Walk about {walked:.0f} m and leave the building through the entrance.")
            walked = 0.0
        elif not current.startswith(DOOR_PREFIX):
            opening = building.openings.get(element) or {"kind": "door"}
            space = building.spaces[current]
            door_point = points.get(previous)
            landmark = landmark_near(building, *door_point) if door_point else None
            target = f"the {opening['kind']}" if opening["kind"] in ("door", "entrance") else "the opening"
            target += f" by the {landmark}" if landmark else ""
            turn = ""
            is_last = index == len(nodes) - 1
            if not is_last and space["type"] not in ("lift", "stair") and door_point:
                # Heading into the door vs heading towards the next door: anchors are not where people walk.
                before = points.get(nodes[index - 2]) if index >= 2 else None
                after = points.get(nodes[index + 1]) if index + 1 < len(nodes) else None
                if before and after and before[0] == door_point[0] == after[0]:
                    turn = _turn(before[1:], door_point[1:], after[1:])
            if space["type"] in ("lift", "stair"):
                steps.append(f"Walk about {walked:.0f} m to {target} of {space['name']}.")
            else:
                then = f", then {turn}" if turn and turn != "go straight" else (", then go straight on" if turn else "")
                steps.append(f"Walk about {walked:.0f} m to {target} into {space['name']}{then}.")
            walked = 0.0
    steps.append(f"You have arrived at {building.label(nodes[-1])}.")
    return steps
