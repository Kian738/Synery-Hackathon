"""Single-element closure analysis rooted at the exits, independent of navigation mode."""
from dataclasses import asdict, dataclass

from floorwise.core.graph import DOOR_PREFIX, Constraints, RouteGraph
from floorwise.core.model import Building, OUTSIDE


@dataclass(frozen=True)
class WeakPoint:
    element_ids: tuple[str, ...]
    name: str
    kind: str
    rooms_lost: int
    of_rooms: int
    room_ids: tuple[str, ...]


SINK = OUTSIDE  # analysis-only node: every usable entrance door leads to it, so "reaches an exit" is "reaches the sink"


def chaos_test(building: Building, constraints: Constraints = Constraints()) -> dict:
    rooms = {s for s, r in building.spaces.items() if r['type'] == 'room'}
    route_graph = RouteGraph(building, constraints)
    graph = route_graph.graph
    for door in route_graph.entrance_doors():
        graph.add_edge(SINK, door, weight=0.0)
    baseline = route_graph.reachable(SINK) & rooms
    edges_by_element = {}
    for u, v, key, attributes in graph.edges(keys=True, data=True):
        if 'via' in attributes:  # a stair flight or lift ride
            edges_by_element.setdefault(attributes['via'], []).append((u, v, key, dict(attributes)))
        for node in (u, v):  # closing an opening removes its door node, with every edge that crosses it
            if node.startswith(DOOR_PREFIX):
                edges_by_element.setdefault(node[len(DOOR_PREFIX):], []).append((u, v, key, dict(attributes)))
    groups = {}
    elements = list(building.connectors.values()) + list(building.openings.values())
    for element in elements:
        if element['id'] in constraints.closed:
            continue
        removed = edges_by_element.get(element['id'], [])
        if not removed:
            continue
        try:
            for u, v, key, attributes in removed:
                if graph.has_edge(u, v, key):
                    graph.remove_edge(u, v, key)
            after = route_graph.reachable(SINK)
            lost = tuple(sorted(baseline - after))
        finally:
            for u, v, key, attributes in removed:
                if not graph.has_edge(u, v, key):
                    graph.add_edge(u, v, key=key, **attributes)
        if lost:
            groups.setdefault(lost, []).append(element)
    result = []
    for lost, members in groups.items():
        first = members[0]  # connector first when its access doors have the same effect
        result.append(WeakPoint(tuple(m['id'] for m in members), _display_name(building, first),
                                first['kind'], len(lost), len(baseline), lost))
    result.sort(key=lambda r: (-r.rooms_lost, r.name))
    return {'rooms_reachable': len(baseline), 'rooms_total': len(rooms), 'critical': [asdict(r) for r in result],
            'worst_case_reach': worst_case_reach(result, len(baseline))}


def _display_name(building: Building, element: dict) -> str:
    """A lift is named; a door is named by the two places it joins, never by its id."""
    if element.get('name'):
        return element['name']
    places = [building.label(s) for s in element.get('space_ids', ()) if s != OUTSIDE]
    return ' ↔ '.join(places) or element['id']


def worst_case_reach(weak_points: list[WeakPoint], reachable: int) -> float | None:
    """Share of reachable rooms that still reach an exit after the single worst interior closure.

    This is the N-1 contingency figure from power-grid planning (can the system survive losing any one part),
    applied to a building. Entrances are left out: closing the only entrance cuts off everything by definition."""
    if not reachable:
        return None
    worst = max((w.rooms_lost for w in weak_points if w.kind != 'entrance'), default=0)
    return round((reachable - worst) / reachable, 3)
