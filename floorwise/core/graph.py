"""The route graph: exactly the dataset's route model, plus a constraint layer.

Nodes are space ids, "door:<opening id>" nodes and one "outside" node. Space anchors are shapely's
representative_point(); each space links to each of its openings by straight-line distance; stairs cost
12 m per floor, lifts 15 m wait + 6 m per floor; entrances meet at "outside" at zero cost. A MultiGraph
keeps parallel stair/lift edges."""

import itertools
import math
from dataclasses import dataclass, field

import networkx as nx
from shapely.geometry import Polygon

from floorwise.core.model import OUTSIDE, Building

DOOR_PREFIX = "door:"
STAIRS_COST_PER_FLOOR_M = 12.0
LIFT_WAIT_COST_M = 15.0
LIFT_COST_PER_FLOOR_M = 6.0


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
    # "free": the dataset's model, all entrances meet at one outside node at zero cost (benchmark).
    # "none": people do not teleport between entrances; routes stay indoors (navigation).
    outside: str = "free"

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
    point = Polygon(building.spaces[space_id]["polygon"]).representative_point()
    return (point.x, point.y)


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

    def _build(self, keep: frozenset[str]) -> nx.MultiGraph:
        building, constraints = self.building, self.constraints
        graph = nx.MultiGraph()
        anchors = {
            space_id: anchor(building, space_id)
            for space_id in building.spaces
            if self._space_allowed(space_id, keep)
        }
        graph.add_nodes_from(anchors)
        for opening in itertools.chain(building.openings.values(), constraints.extra_openings):
            if not self._opening_allowed(opening):
                continue
            door = DOOR_PREFIX + opening["id"]
            for space_id in opening["space_ids"]:
                if space_id == OUTSIDE:
                    if constraints.outside == "free":
                        graph.add_edge(OUTSIDE, door, weight=0.0, via=opening["id"])
                elif space_id in anchors:
                    distance = math.dist(anchors[space_id], opening["position"])
                    if constraints.soft_avoid_types:
                        space = building.spaces[space_id]
                        if space["room_type"] in constraints.soft_avoid_types or space["type"] in constraints.soft_avoid_types:
                            distance *= constraints.soft_penalty
                    graph.add_edge(space_id, door, weight=distance, via=opening["id"])
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
            for (low_floor, low_space), (high_floor, high_space) in itertools.pairwise(stops):
                if low_space not in anchors or high_space not in anchors:
                    continue
                span = abs(building.level(high_floor) - building.level(low_floor))
                cost = LIFT_WAIT_COST_M + LIFT_COST_PER_FLOOR_M * span if is_lift else STAIRS_COST_PER_FLOOR_M * span
                graph.add_edge(low_space, high_space, weight=cost, via=connector["id"])
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

    def edge_via(self, first: str, second: str) -> dict:
        return min(self.graph[first][second].values(), key=lambda edge: edge["weight"])
