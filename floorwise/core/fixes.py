"""Find and verify small door-width interventions without changing the building."""
from dataclasses import dataclass, replace
import math

import networkx as nx

from floorwise.core.graph import Constraints, RouteGraph
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


def smallest_fix(building: Building, start: str, target: str, constraints: Constraints) -> FixProposal:
    if RouteGraph(building, constraints, keep=frozenset({start, target})).shortest(start, target):
        return FixProposal(True, "A route already satisfies these constraints.")
    width = constraints.min_width_m
    if width is None or not math.isfinite(width) or width <= 0:
        return FixProposal(False, "No door-width repair can restore this connection.")
    graph = RouteGraph(building, replace(constraints, min_width_m=None), keep=frozenset({start, target})).graph
    # A door contributes two half costs. Entrances are never proposed for widening.
    for u, v, key, edge in list(graph.edges(keys=True, data=True)):
        opening = building.openings.get(edge['via'])
        narrow = opening is not None and float(opening.get('width_m') or 0) < width - 1e-9
        if narrow and 'outside' in opening['space_ids']:
            graph.remove_edge(u, v, key)
        else:
            edge['repair_cost'] = (0.5 if narrow else 0) + edge['weight'] * 1e-9
    try:
        path = nx.shortest_path(graph, start, target, weight='repair_cost')
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return FixProposal(False, "No connection exists even after relaxing door widths.")
    ids = []
    for u, v in zip(path, path[1:]):
        edge = min(graph[u][v].values(), key=lambda e: e['repair_cost'])
        o = building.openings.get(edge['via'])
        if o and float(o.get('width_m') or 0) < width - 1e-9 and o['id'] not in ids:
            ids.append(o['id'])
    if not ids or len(ids) > MAX_FIX_OPENINGS:
        return FixProposal(False, f"No repair within {MAX_FIX_OPENINGS} door widenings was found.")
    copies = tuple({**building.openings[o], 'width_m': width} for o in ids)
    check = RouteGraph(building, replace(constraints, extra_openings=constraints.extra_openings + copies),
                       keep=frozenset({start, target})).shortest(start, target)
    if check is None:
        return FixProposal(False, "The proposed repair did not verify.")
    widen = tuple(Widening(o, tuple(building.label(s) for s in building.openings[o]['space_ids']),
                           float(building.openings[o]['width_m']), width) for o in ids)
    return FixProposal(False, "These door widenings restore connectivity under the requested constraints. Physical work is required.", widen, True)
