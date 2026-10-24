"""Compare closure routing against the kit's independent BuildingMap implementation."""
import argparse
import copy
import random

import networkx as nx

from eval.ledger import Ledger
from floorwise.core.graph import Constraints, RouteGraph
from floorwise.core.model import Building
from floorwise.paths import DATA, use_kit_modules


def compare_building(building: Building, pairs: int = 3, closures: int = 4) -> list[dict]:
    use_kit_modules()
    from starter_agent.building_map import BuildingMap
    original = copy.deepcopy(building.data)
    reference = BuildingMap(copy.deepcopy(building.data))
    rng = random.Random(17)
    rooms = sorted(building.spaces)
    if len(rooms) < 2:
        return []
    targets = [rng.sample(rooms, 2) for _ in range(pairs)]
    connectors = sorted(building.connectors)
    opening_ids = sorted(building.openings)
    sample = connectors[:closures]
    sample += rng.sample(opening_ids, min(max(0, closures-len(sample)), len(opening_ids)))
    rows = []
    for step_free in [False, True]:
        for closed in [None, *sample]:
            reference.closed = {closed} if closed else set()
            official = reference.graph(step_free)
            ours = RouteGraph(building, Constraints(step_free=step_free, closed=frozenset(reference.closed)))
            for a, b in targets:
                expected = nx.single_source_dijkstra_path_length(official, a).get(b) if a in official else None
                actual = ours.shortest(a, b)
                ok = (expected is None and actual is None) or (expected is not None and actual is not None and abs(expected-actual[0]) < 1e-7)
                if actual and closed:
                    ok = ok and all(ours.edge_via(u,v)['via'] != closed for u,v in zip(actual[1],actual[1][1:]))
                rows.append({'correct': ok, 'start': a, 'end': b, 'closed': closed, 'step_free': step_free,
                             'expected_m': expected, 'actual_m': actual[0] if actual else None})
    assert building.data == original, 'Differential evaluation mutated its input'
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', default='train,dev')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--pairs', type=int, default=3)
    parser.add_argument('--closures', type=int, default=4)
    args = parser.parse_args()
    ledger = Ledger('differential', vars(args))
    paths = sorted(p for split in args.split.split(',') for p in (DATA/split).glob('*/building.json'))[:args.limit]
    for path in paths:
        b = Building.load(path)
        for i, row in enumerate(compare_building(b, args.pairs, args.closures)):
            ledger.record(id=f'{b.id}:{i}', kind='closure differential', building=b.id, source=b.info['source'], **row)
    summary = ledger.finish()
    if summary['correct'] != summary['total'] or not summary['total']:
        raise SystemExit('Differential routing mismatch')


if __name__ == '__main__':
    main()
