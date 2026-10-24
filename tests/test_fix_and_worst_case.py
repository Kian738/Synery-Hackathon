"""Before/after counters on a verified fix, and the worst single closure of a building."""
from dataclasses import replace

import pytest

from floorwise.core.fixes import smallest_fix
from floorwise.core.graph import Constraints, RouteGraph
from floorwise.core.model import Building
from floorwise.core.resilience import chaos_test
from floorwise.paths import DATA

TROLLEY = Constraints(step_free=True, min_width_m=1.1, outside="none")


@pytest.fixture(scope="module")
def campus() -> Building:
    return Building.load(DATA / "dev" / "proc-campus-dev-000")


def space_id(building: Building, name: str) -> str:
    return next(s["id"] for s in building.spaces.values() if s["name"] == name)


def rooms_from(building: Building, start: str, constraints: Constraints) -> int:
    reached = RouteGraph(building, constraints, keep=frozenset({start})).reachable(start)
    return sum(building.spaces[s]["type"] == "room" for s in reached if s in building.spaces)


def test_fix_reports_real_before_and_after_counts(campus):
    start, target = space_id(campus, "Main lobby"), space_id(campus, "Print room 0.16")
    fix = smallest_fix(campus, start, target, TROLLEY)
    assert fix.verified
    assert fix.rooms_reachable_before == rooms_from(campus, start, TROLLEY)
    assert fix.rooms_reachable_before < fix.rooms_reachable_after <= fix.of_rooms
    copies = tuple({**campus.openings[w.opening_id], "width_m": w.to_m} for w in fix.widen)
    assert fix.rooms_reachable_after == rooms_from(campus, start, replace(TROLLEY, extra_openings=copies))


def test_unverified_fix_carries_no_counters(campus):
    fix = smallest_fix(campus, space_id(campus, "Main lobby"), space_id(campus, "Print room 0.16"),
                       Constraints(step_free=True, outside="none"))
    assert fix.reachable_before and fix.rooms_reachable_after is None


def test_worst_case_reach_of_the_factory_is_the_office_lift():
    factory = Building.load(DATA / "dev" / "proc-factory-dev-003")
    result = chaos_test(factory, Constraints(step_free=True))
    assert result["worst_case_reach"] == round((56 - 29) / 56, 3)
    assert result["worst_case_reach"] < chaos_test(factory, Constraints())["worst_case_reach"]


def test_entrances_do_not_set_the_worst_case():
    for path in sorted((DATA / "dev").glob("*/building.json")):
        building = Building.load(path.parent)
        if len(building.spaces) > 150:
            continue
        result = chaos_test(building, Constraints(step_free=True))
        interior = [i["rooms_lost"] for i in result["critical"] if i["kind"] != "entrance"]
        entrances = [i["rooms_lost"] for i in result["critical"] if i["kind"] == "entrance"]
        if interior and entrances and max(entrances) > max(interior):
            expected = round((result["rooms_reachable"] - max(interior)) / result["rooms_reachable"], 3)
            assert result["worst_case_reach"] == expected
            return
    pytest.fail("no dev building has an entrance that out-strands every interior element")
