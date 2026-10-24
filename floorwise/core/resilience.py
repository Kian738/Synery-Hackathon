"""Single-element closure analysis rooted at the exits, independent of navigation mode."""
from dataclasses import asdict, dataclass, replace

from floorwise.core.graph import Constraints, RouteGraph
from floorwise.core.model import Building, OUTSIDE


@dataclass(frozen=True)
class WeakPoint:
    element_ids: tuple[str, ...]
    name: str
    kind: str
    rooms_lost: int
    of_rooms: int
    room_ids: tuple[str, ...]


def chaos_test(building: Building, constraints: Constraints = Constraints()) -> dict:
    constraints = replace(constraints, outside='free')
    rooms = {s for s, r in building.spaces.items() if r['type'] == 'room'}
    route_graph = RouteGraph(building, constraints)
    graph = route_graph.graph
    baseline = route_graph.reachable(OUTSIDE) & rooms
    edges_by_element = {}
    for u, v, key, attributes in graph.edges(keys=True, data=True):
        edges_by_element.setdefault(attributes['via'], []).append((u, v, key, dict(attributes)))
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
                graph.remove_edge(u, v, key)
            after = route_graph.reachable(OUTSIDE)
            lost = tuple(sorted(baseline - after))
        finally:
            for u, v, key, attributes in removed:
                graph.add_edge(u, v, key=key, **attributes)
        if lost:
            groups.setdefault(lost, []).append(element)
    result = []
    for lost, members in groups.items():
        first = members[0]  # connector first when its access doors have the same effect
        result.append(WeakPoint(tuple(m['id'] for m in members), first.get('name') or first['id'],
                                first['kind'], len(lost), len(baseline), lost))
    result.sort(key=lambda r: (-r.rooms_lost, r.name))
    return {'rooms_reachable': len(baseline), 'rooms_total': len(rooms), 'critical': [asdict(r) for r in result]}
