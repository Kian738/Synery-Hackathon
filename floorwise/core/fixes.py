"""Find and verify small door-width interventions without changing the building."""
from dataclasses import dataclass, replace
import math

import networkx as nx

from floorwise.core.graph import DOOR_PREFIX, Constraints, RouteGraph
from floorwise.core.model import Building

MAX_FIX_OPENINGS = 3


@dataclass(frozen=True)
class Widening:
    opening_id: str
    between: tuple[str, ...]
    from_m: float
    to_m: float


@dataclass(frozen=True)
class FixProposal:
    reachable_before: bool
    reason: str
    widen: tuple[Widening, ...] = ()
    verified: bool = False
    # Rooms reachable from the start on foot (no teleporting between entrances), before and after the fix.
    rooms_reachable_before: int | None = None
    rooms_reachable_after: int | None = None
    of_rooms: int | None = None


def _rooms_reachable_from(building: Building, start: str, target: str, constraints: Constraints) -> int:
    reached = RouteGraph(building, constraints, keep=frozenset({start, target})).reachable(start)
    return sum(building.spaces[s]["type"] == "room" for s in reached if s in building.spaces)


def smallest_fix(building: Building, start: str, target: str, constraints: Constraints) -> FixProposal:
    if RouteGraph(building, constraints, keep=frozenset({start, target})).shortest(start, target):
        return FixProposal(True, "A route already satisfies these constraints.")
    width = constraints.min_width_m
    if width is None or not math.isfinite(width) or width <= 0:
        return FixProposal(False, "No door-width repair can restore this connection.")
    graph = RouteGraph(building, replace(constraints, min_width_m=None), keep=frozenset({start, target})).graph
    narrow = {DOOR_PREFIX + o['id']: o for o in building.openings.values() if float(o.get('width_m') or 0) < width - 1e-9}
    # A door on a path has two edges at it, so half a cost each makes every narrow door cost one.
    # Entrances are never proposed for widening.
    graph.remove_nodes_from([node for node, o in narrow.items() if 'outside' in o['space_ids'] and node in graph])
    for u, v, key, edge in graph.edges(keys=True, data=True):
        edge['repair_cost'] = 0.5 * ((u in narrow) + (v in narrow)) + edge['weight'] * 1e-9
    try:
        path = nx.shortest_path(graph, start, target, weight='repair_cost')
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return FixProposal(False, "No connection exists even after relaxing door widths.")
    ids = list(dict.fromkeys(narrow[node]['id'] for node in path if node in narrow))
    if not ids or len(ids) > MAX_FIX_OPENINGS:
        return FixProposal(False, f"No repair within {MAX_FIX_OPENINGS} door widenings was found.")
    copies = tuple({**building.openings[o], 'width_m': width} for o in ids)
    check = RouteGraph(building, replace(constraints, extra_openings=constraints.extra_openings + copies),
                       keep=frozenset({start, target})).shortest(start, target)
    if check is None:
        return FixProposal(False, "The proposed repair did not verify.")
    widen = tuple(Widening(o, tuple(building.label(s) for s in building.openings[o]['space_ids']),
                           float(building.openings[o]['width_m']), width) for o in ids)
    widened = replace(constraints, extra_openings=constraints.extra_openings + copies)
    return FixProposal(
        False, "These door widenings restore connectivity under the requested constraints. Physical work is required.",
        widen, True,
        rooms_reachable_before=_rooms_reachable_from(building, start, target, constraints),
        rooms_reachable_after=_rooms_reachable_from(building, start, target, widened),
        of_rooms=sum(space["type"] == "room" for space in building.spaces.values()),
    )
