"""chaos_test must equal the slow definition: rebuild the whole route graph with one element closed."""
import csv
import time
from dataclasses import asdict, replace

import pytest

from floorwise.core.graph import Constraints, RouteGraph
from floorwise.core.model import OUTSIDE, Building
from floorwise.core.resilience import WeakPoint, chaos_test
from floorwise.paths import DATA

MAX_SPACES_FOR_REFERENCE = 120
LARGEST_BUILDING_BUDGET_S = 20


def reference_chaos(building: Building, constraints: Constraints) -> dict:
    constraints = replace(constraints, outside='free')
    rooms = {s for s, r in building.spaces.items() if r['type'] == 'room'}
    baseline = RouteGraph(building, constraints).reachable(OUTSIDE) & rooms
    groups = {}
    for element in list(building.connectors.values()) + list(building.openings.values()):
        if element['id'] in constraints.closed:
            continue
        after = RouteGraph(building, replace(constraints, closed=constraints.closed | {element['id']})).reachable(OUTSIDE)
        lost = tuple(sorted(baseline - after))
        if lost:
            groups.setdefault(lost, []).append(element)
    result = [WeakPoint(tuple(m['id'] for m in members), members[0].get('name') or members[0]['id'],
                        members[0]['kind'], len(lost), len(baseline), lost) for lost, members in groups.items()]
    result.sort(key=lambda r: (-r.rooms_lost, r.name))
    return {'rooms_reachable': len(baseline), 'rooms_total': len(rooms), 'critical': [asdict(r) for r in result]}


def without_names(result: dict) -> dict:
    items = [{k: v for k, v in item.items() if k != 'name'} for item in result['critical']]
    comparable = {k: v for k, v in result.items() if k != 'worst_case_reach'}  # covered by test_fix_and_worst_case
    return {**comparable, 'critical': sorted(items, key=lambda item: (-item['rooms_lost'], item['element_ids']))}


def small_buildings():
    """Buildings small enough for the slow reference, chosen from the manifest so only the sampled ones are loaded."""
    with (DATA / "manifest.csv").open(encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle) if r["split"] in ("train", "dev") and int(r["spaces"]) <= MAX_SPACES_FOR_REFERENCE]
    return [DATA / r["split"] / r["building_id"] for r in sorted(rows, key=lambda r: r["building_id"])]


def sample(step: int):
    return [Building.load(path) for path in small_buildings()[::step]]


@pytest.mark.parametrize('profile', [Constraints(), Constraints(step_free=True), Constraints(step_free=True, min_width_m=1.1)])
def test_fast_chaos_equals_rebuild_per_element(profile):
    checked = 0
    for building in sample(15):
        assert without_names(chaos_test(building, profile)) == without_names(reference_chaos(building, profile)), building.id
        checked += 1
    assert checked >= 8


def test_fast_chaos_respects_already_closed_elements():
    building = next(b for b in map(Building.load, small_buildings()) if b.connectors)
    closed = Constraints(closed=frozenset({next(iter(building.connectors))}))
    assert without_names(chaos_test(building, closed)) == without_names(reference_chaos(building, closed))


def test_largest_building_finishes_in_seconds():
    path = max((DATA / 'train').glob('*/building.json'), key=lambda p: p.stat().st_size)
    building = Building.load(path.parent)
    started = time.perf_counter()
    chaos_test(building, Constraints(step_free=True))
    assert time.perf_counter() - started < LARGEST_BUILDING_BUDGET_S


def test_weak_point_names_are_readable_never_raw_ids():
    checked = 0
    for building in sample(10):
        elements = {**building.connectors, **building.openings}
        for item in chaos_test(building, Constraints(step_free=True))['critical']:
            lead = elements[item['element_ids'][0]]
            assert item['name'] not in elements, (building.id, item['name'])
            if lead.get('name'):
                assert item['name'] == lead['name']
            checked += 1
    assert checked >= 20
