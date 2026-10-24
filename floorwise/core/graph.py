"""The route graph: the organisers' route model (kit v1.1.0, README section 3), plus a constraint layer.

Nodes are space anchors and "door:<opening id>" nodes. Inside a space the graph joins the anchor to each door and
each pair of doors with the walking length of floorwise.core.inroom (15 cm off the walls, round corners, doors
land 30 cm inside); an edge records the space it crosses. Stairs cost 2 m per metre climbed between consecutive
stops; a lift costs 15 m once per ride plus 1 m per metre climbed, with every pair of stops joined. There is no
route via the outside: an entrance is a door like any other, and a route never leaves the building.
A MultiGraph keeps a stair and a lift that join the same two spaces."""

import itertools
from dataclasses import dataclass

import networkx as nx

from floorwise.core import inroom
from floorwise.core.model import OUTSIDE, Building

DOOR_PREFIX = "door:"
STAIRS_M_PER_RISE = 2.0
LIFT_FIXED_M = 15.0
LIFT_M_PER_RISE = 1.0
LENGTH_DECIMALS = inroom.LENGTH_DECIMALS


@dataclass(frozen=True)
class Constraints:
    """Hard constraints drop edges; soft ones (avoid_types_penalty) scale walking cost."""

    step_free: bool = False
    min_width_m: float | None = None
    closed: frozenset[str] = frozenset()  # opening, connector or space ids
    avoid_spaces: frozenset[str] = frozenset()  # never enter (start/end are exempt)
    avoid_types: frozenset[str] = frozenset()  # room_type or space type, e.g. "production_zone"
    no_stairs: bool = False
    no_lifts: bool = False
    extra_openings: tuple[dict, ...] = ()  # what-if doors
    soft_avoid_types: frozenset[str] = frozenset()
    soft_penalty: float = 3.0

    def describe(self) -> list[str]:
        notes = []
        if self.step_free:
            notes.append("step-free")
        if self.min_width_m:
            notes.append(f"doors at least {self.min_width_m:g} m wide")
        if self.no_stairs and not self.step_free:
            notes.append("no stairs")
        if self.no_lifts:
            notes.append("no lifts")
        if self.closed:
            notes.append(f"closed: {', '.join(sorted(self.closed))}")
        if self.avoid_spaces:
            notes.append(f"avoiding {len(self.avoid_spaces)} space(s)")
        if self.avoid_types:
            notes.append(f"avoiding {', '.join(sorted(self.avoid_types))}")
        if self.soft_avoid_types:
            notes.append(f"preferring to avoid {', '.join(sorted(self.soft_avoid_types))}")
        return notes


def anchor(building: Building, space_id: str) -> tuple[float, float]:
    return inroom.anchor_point(inroom.outline(building.spaces[space_id]["polygon"]))


def is_door(node: str) -> bool:
    return node.startswith(DOOR_PREFIX)


class RouteGraph:
    def __init__(self, building: Building, constraints: Constraints = Constraints(),
                 keep: frozenset[str] = frozenset()) -> None:
        """keep: spaces exempt from avoid rules (the route's own start and stops)."""
        self.building = building
        self.constraints = constraints
        self.graph = self._build(keep)

    def _space_allowed(self, space_id: str, keep: frozenset[str]) -> bool:
        constraints = self.constraints
        if space_id in constraints.closed:
            return False
        if space_id in keep:
            return True
        space = self.building.spaces[space_id]
        if space_id in constraints.avoid_spaces:
            return False
        return not (space["room_type"] in constraints.avoid_types or space["type"] in constraints.avoid_types)

    def _opening_allowed(self, opening: dict) -> bool:
        constraints = self.constraints
        if opening["id"] in constraints.closed:
            return False
        if constraints.step_free and not opening.get("step_free", True):
            return False
        if constraints.min_width_m is not None and float(opening.get("width_m") or 0) < constraints.min_width_m - 1e-9:
            return False
        return True

    def _softened(self, space_id: str) -> float:
        constraints, space = self.constraints, self.building.spaces[space_id]
        soft = space["room_type"] in constraints.soft_avoid_types or space["type"] in constraints.soft_avoid_types
        return constraints.soft_penalty if constraints.soft_avoid_types and soft else 1.0

    def _build(self, keep: frozenset[str]) -> nx.MultiGraph:
        building, constraints = self.building, self.constraints
        graph = nx.MultiGraph()
        spaces = [space_id for space_id in building.spaces if self._space_allowed(space_id, keep)]
        graph.add_nodes_from(spaces)
        extra = constraints.extra_openings
        open_doors = {
            DOOR_PREFIX + opening["id"]
            for opening in itertools.chain(building.openings.values(), extra)
            if self._opening_allowed(opening)
        }
        for space_id in spaces:
            penalty = self._softened(space_id)
            for first, second, length in inroom.space_walks(building, space_id, inroom.doors_of(building, space_id, extra), DOOR_PREFIX):
                if (first == space_id or first in open_doors) and second in open_doors:
                    graph.add_edge(first, second, weight=round(length, LENGTH_DECIMALS) * penalty, space=space_id)
        for connector in building.connectors.values():
            if connector["id"] in constraints.closed:
                continue
            if constraints.step_free and not connector.get("step_free", True):
                continue
            is_lift = connector["kind"] == "lift"
            if (is_lift and constraints.no_lifts) or (not is_lift and constraints.no_stairs):
                continue
            stops = sorted(
                zip(connector["floor_ids"], connector["space_ids"], strict=True),
                key=lambda stop: building.level(stop[0]),
            )
            # A lift ride pays the fixed cost once however many floors it passes, so every pair of stops is joined.
            pairs = itertools.combinations(stops, 2) if is_lift else itertools.pairwise(stops)
            for (low_floor, low_space), (high_floor, high_space) in pairs:
                if low_space not in graph or high_space not in graph:
                    continue
                rise = abs(building.elevation(high_floor) - building.elevation(low_floor))
                cost = LIFT_FIXED_M + LIFT_M_PER_RISE * rise if is_lift else STAIRS_M_PER_RISE * rise
                graph.add_edge(low_space, high_space, weight=round(cost, LENGTH_DECIMALS), via=connector["id"])
        inroom.save(building)
        return graph

    # ---------- queries ----------

    def distances_from(self, source: str) -> dict[str, float]:
        if source not in self.graph:
            return {}
        return nx.single_source_dijkstra_path_length(self.graph, source, weight="weight")

    def shortest(self, source: str, target: str) -> tuple[float, list[str]] | None:
        try:
            return nx.single_source_dijkstra(self.graph, source, target, weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def reachable(self, source: str) -> set[str]:
        if source not in self.graph:
            return set()
        return set(nx.node_connected_component(self.graph, source))

    def entrance_doors(self) -> list[str]:
        """Door nodes of every usable entrance (an opening that touches the outside)."""
        extra = self.constraints.extra_openings
        openings = itertools.chain(self.building.openings.values(), extra)
        return [DOOR_PREFIX + o["id"] for o in openings if OUTSIDE in o["space_ids"] and DOOR_PREFIX + o["id"] in self.graph]

    def distances_to_entrances(self) -> dict[str, float]:
        """Walking distance from every node to its nearest entrance door."""
        doors = self.entrance_doors()
        if not doors:
            return {}
        return nx.multi_source_dijkstra_path_length(self.graph, doors, weight="weight")

    def edge_via(self, first: str, second: str) -> dict:
        """The element a step between two route nodes uses. Route nodes alternate space and door (see expand), so a
        step touching a door uses that opening; a step between two spaces uses its stair or lift."""
        door = first if is_door(first) else second if is_door(second) else None
        if door:
            return {"via": door[len(DOOR_PREFIX):], "weight": 0.0}
        return min(self.graph[first][second].values(), key=lambda edge: edge["weight"])

    def expand(self, nodes: list[str]) -> list[str]:
        """Graph path -> the alternating path space, door, space, door ... that directions and drawing walk along.
        A door-to-door step crosses a space that is not a node of its own; it is inserted between the two doors."""
        expanded = [nodes[0]]
        for first, second in itertools.pairwise(nodes):
            if is_door(first) and is_door(second):
                expanded.append(min(self.graph[first][second].values(), key=lambda edge: edge["weight"])["space"])
            expanded.append(second)
        return expanded

    def elements(self, nodes: list[str]) -> list[str]:
        """Openings and connectors a graph path uses, in order; a connector once per stair flight or ride."""
        used = []
        for index, node in enumerate(nodes):
            if is_door(node):
                used.append(node[len(DOOR_PREFIX):])
            elif index and not is_door(nodes[index - 1]):
                edge = min(self.graph[nodes[index - 1]][node].values(), key=lambda edge: edge["weight"])
                if "via" in edge:
                    used.append(edge["via"])
        return used
