"""The route graph: the judges' route model (kit 1.1.0, README section 3), plus a constraint layer.

Nodes are space ids (the centre point, shapely's representative_point of the outline) and "door:<opening id>"
nodes at each opening's position. Inside a space, its centre and each of its openings are joined by the walk that
stays 15 cm off the walls and goes round corners (floorwise.core.spacewalk); an opening lands 30 cm inside each
space. Stairs cost 2 m per metre climbed between the spaces' centre points; a lift costs 15 m once per ride plus
1 m per metre climbed and joins every pair of its stops. There is no way round the outside: an entrance is a door
node attached to its one interior space. A MultiGraph keeps parallel stair/lift/door edges.

`outside="exits"` adds a virtual OUTSIDE node joined at zero cost to every open entrance door. It is only for
exit-distance and exit-reachability analyses (distances_from(OUTSIDE) is the walk to the nearest entrance); routes
between rooms never use it, because the default is `outside="none"`."""

import itertools
from dataclasses import dataclass

import networkx as nx
from shapely.geometry import Polygon

from floorwise.core import spacewalk
from floorwise.core.model import OUTSIDE, Building

DOOR_PREFIX = spacewalk.DOOR_PREFIX
STAIRS_M_PER_RISE = 2.0
LIFT_FIXED_M = 15.0
LIFT_M_PER_RISE = 1.0
LENGTH_DECIMALS = 3
FORKLIFT_MIN_WIDTH_M = 3.0
BAY_SUFFIX = "_zone"  # production_zone, assembly_zone, additive_zone, warehouse_zone, logistics_zone


@dataclass(frozen=True)
class Constraints:
    """Hard constraints drop edges; soft ones (soft_avoid_types) scale walking cost."""

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
    forklift: bool = False  # forklift aisles and openings 3 m or wider only; no stairs or lifts
    bays_are_destinations: bool = False  # production bays may be entered to deliver, never crossed as a shortcut
    # "none": routes stay inside the building (the default, the judges' model).
    # "exits": a virtual OUTSIDE node touches every open entrance, for exit-distance analyses only ("free" is the old name).
    outside: str = "none"

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
        if self.forklift:
            notes.append(f"forklift: aisles and openings at least {FORKLIFT_MIN_WIDTH_M:g} m wide, no stairs or lifts")
        if self.bays_are_destinations:
            notes.append("production bays are destinations only")
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
    return spacewalk.anchor_of(spacewalk.outline(building.spaces[space_id]["polygon"]))


def is_bay(space: dict) -> bool:
    return space["type"] == "hall" and space["room_type"].endswith(BAY_SUFFIX)


def _is_forklift_aisle(building: Building, space: dict) -> bool:
    """A space a forklift may drive through: not a bay, and wide enough for the 3 m a forklift needs."""
    cache = building.__dict__.setdefault("_aisle", {})
    if space["id"] not in cache:
        polygon = spacewalk.outline(space["polygon"])
        cache[space["id"]] = (space["type"] in ("corridor", "hall", "outdoor") and not is_bay(space)
                              and not polygon.buffer(-FORKLIFT_MIN_WIDTH_M / 2).is_empty)
    return cache[space["id"]]


class RouteGraph:
    def __init__(self, building: Building, constraints: Constraints = Constraints(),
                 keep: frozenset[str] = frozenset()) -> None:
        """keep: spaces exempt from avoid rules (the route's own start and stops)."""
        self.building = building
        self.constraints = constraints
        self.terminal = self._terminal_spaces()
        self.graph = self._build(keep)

    def _terminal_spaces(self) -> frozenset[str]:
        """Spaces a route may end in (or start from) but never cross: production bays when they are destinations
        only, and for a forklift every space that is not a wide aisle."""
        c, b = self.constraints, self.building
        if not (c.bays_are_destinations or c.forklift):
            return frozenset()
        return frozenset(
            sid for sid, space in b.spaces.items()
            if (c.bays_are_destinations and is_bay(space)) or (c.forklift and not _is_forklift_aisle(b, space))
        )

    def _space_allowed(self, space_id: str, keep: frozenset[str]) -> bool:
        c = self.constraints
        if space_id in c.closed:
            return False
        if space_id in keep:
            return True
        space = self.building.spaces[space_id]
        if space_id in c.avoid_spaces:
            return False
        if space["room_type"] in c.avoid_types or space["type"] in c.avoid_types:
            return False
        return True

    def _opening_allowed(self, opening: dict) -> bool:
        c = self.constraints
        if opening["id"] in c.closed:
            return False
        if c.step_free and not opening.get("step_free", True):
            return False
        width = float(opening.get("width_m") or 0)
        if c.min_width_m is not None and width < c.min_width_m - 1e-9:
            return False
        if c.forklift and width < FORKLIFT_MIN_WIDTH_M - 1e-9:
            return False
        return True

    def _build(self, keep: frozenset[str]) -> nx.MultiGraph:
        b, c = self.building, self.constraints
        graph = nx.MultiGraph()
        open_spaces = [sid for sid in b.spaces if self._space_allowed(sid, keep)]
        graph.add_nodes_from(open_spaces)
        openings = list(itertools.chain(b.openings.values(), c.extra_openings))
        open_doors = {DOOR_PREFIX + o["id"] for o in openings if self._opening_allowed(o)}
        soft = c.soft_avoid_types
        for sid in open_spaces:
            space = b.spaces[sid]
            factor = c.soft_penalty if soft and (space["room_type"] in soft or space["type"] in soft) else 1.0
            edges = spacewalk.edges_with(b, sid, c.extra_openings) if c.extra_openings else spacewalk.base_edges(b)[sid]
            for first, second, length in edges:
                if (first == sid or first in open_doors) and second in open_doors:
                    graph.add_edge(first, second, weight=round(length, LENGTH_DECIMALS) * factor, space=sid,
                                   via=second[len(DOOR_PREFIX):] if first == sid else None)
        if c.outside in ("exits", "free"):
            for o in openings:
                if OUTSIDE in o["space_ids"] and DOOR_PREFIX + o["id"] in graph:
                    graph.add_edge(OUTSIDE, DOOR_PREFIX + o["id"], weight=0.0, via=o["id"])
        elevations = {fid: float(f.get("elevation_m") or 0.0) for fid, f in b.floors.items()}
        for connector in b.connectors.values():
            if connector["id"] in c.closed or (c.step_free and not connector.get("step_free", True)):
                continue
            is_lift = connector["kind"] == "lift"
            if (is_lift and (c.no_lifts or c.forklift)) or (not is_lift and (c.no_stairs or c.forklift)):
                continue
            stops = sorted(zip(connector["floor_ids"], connector["space_ids"], strict=True), key=lambda s: b.level(s[0]))
            pairs = itertools.combinations(stops, 2) if is_lift else itertools.pairwise(stops)
            for (low_floor, low_space), (high_floor, high_space) in pairs:
                if low_space not in graph or high_space not in graph:
                    continue
                rise = abs(elevations[high_floor] - elevations[low_floor])
                cost = LIFT_FIXED_M + LIFT_M_PER_RISE * rise if is_lift else STAIRS_M_PER_RISE * rise
                graph.add_edge(low_space, high_space, weight=round(cost, LENGTH_DECIMALS), via=connector["id"])
        return graph

    # ---------- queries ----------

    def _search(self, source: str, target: str | None = None) -> tuple[dict[str, float], dict[str, str]]:
        """Dijkstra from source that never crosses a terminal space: walks inside one are only allowed when the route
        starts there, or as the final step in from a door to its centre."""
        import heapq

        graph, terminal = self.graph, self.terminal
        start_space = source if source in self.building.spaces else None
        dist, prev, done = {source: 0.0}, {}, set()
        heap = [(0.0, source)]
        while heap:
            d, u = heapq.heappop(heap)
            if u in done:
                continue
            done.add(u)
            if u == target:
                break
            if u in terminal and u != start_space:
                continue  # arrived at a terminal space's centre: the route ends here
            for v, edges in graph[u].items():
                for data in edges.values():
                    space = data.get("space")
                    if space in terminal and space != start_space and v != space:
                        continue  # a walk inside a terminal space that is not the final step in
                    nd = d + data["weight"]
                    if nd < dist.get(v, float("inf")) - 1e-12:
                        dist[v], prev[v] = nd, u
                        heapq.heappush(heap, (nd, v))
        return dist, prev

    def distances_from(self, source: str) -> dict[str, float]:
        if source not in self.graph:
            return {}
        if not self.terminal:
            return nx.single_source_dijkstra_path_length(self.graph, source, weight="weight")
        return self._search(source)[0]

    def shortest(self, source: str, target: str) -> tuple[float, list[str]] | None:
        """(length, nodes). Nodes are the raw graph path; use expand() for the list of spaces and doors."""
        if source not in self.graph or target not in self.graph:
            return None
        if not self.terminal:
            try:
                return nx.single_source_dijkstra(self.graph, source, target, weight="weight")
            except nx.NetworkXNoPath:
                return None
        dist, prev = self._search(source, target)
        if target not in dist:
            return None
        nodes = [target]
        while nodes[-1] != source:
            nodes.append(prev[nodes[-1]])
        return dist[target], nodes[::-1]

    def reachable(self, source: str) -> set[str]:
        if source not in self.graph:
            return set()
        if not self.terminal:
            return set(nx.node_connected_component(self.graph, source))
        return set(self._search(source)[0])

    def expand(self, nodes: list[str]) -> list[str]:
        """Insert the space a door-to-door stretch crosses, so the list alternates space, door, space.
        Spaces in the result are exactly the spaces the route passes through."""
        out: list[str] = []
        for index, node in enumerate(nodes):
            if index and node.startswith(DOOR_PREFIX) and nodes[index - 1].startswith(DOOR_PREFIX):
                out.append(self.cheapest(nodes[index - 1], node)["space"])
            out.append(node)
        return out

    def cheapest(self, first: str, second: str) -> dict:
        return min(self.graph[first][second].values(), key=lambda edge: edge["weight"])

    def edge_via(self, first: str, second: str) -> dict:
        """The element (opening id, stair or lift id) joining two adjacent nodes of an expanded path."""
        door_first, door_second = first.startswith(DOOR_PREFIX), second.startswith(DOOR_PREFIX)
        if door_first != door_second:  # space <-> door, possibly with the door's other half implied by expand()
            return {"via": (first if door_first else second)[len(DOOR_PREFIX):], "weight": 0.0}
        if first in self.graph and second in self.graph[first]:
            return self.cheapest(first, second)
        return {"via": None, "weight": 0.0}

    def collapse(self, nodes: list[str]) -> list[str]:
        """Inverse of expand(): drop a space that sits between two doors (the direct door-to-door walk is never
        longer than going via the room's centre, so a shortest path only visits a centre at its ends)."""
        out: list[str] = []
        for index, node in enumerate(nodes):
            if (out and index + 1 < len(nodes) and node in self.building.spaces
                    and out[-1].startswith(DOOR_PREFIX) and nodes[index + 1].startswith(DOOR_PREFIX)):
                continue
            out.append(node)
        return out

    def path_length(self, nodes: list[str]) -> float:
        """Length of a (raw or expanded) node path under the current constraints."""
        raw = self.collapse(nodes)
        return sum(self.cheapest(a, b)["weight"] for a, b in zip(raw, raw[1:], strict=False))

    def elements(self, nodes: list[str]) -> list[str]:
        """Every opening, stair and lift the raw path uses, once each, in order."""
        used: list[str] = []
        for index, node in enumerate(nodes):
            if node.startswith(DOOR_PREFIX):
                used.append(node[len(DOOR_PREFIX):])
            elif index and not nodes[index - 1].startswith(DOOR_PREFIX) and node != OUTSIDE and nodes[index - 1] != OUTSIDE:
                edge = self.cheapest(nodes[index - 1], node)
                if edge.get("via") and edge["via"] in self.building.connectors:
                    used.append(edge["via"])
        return used
