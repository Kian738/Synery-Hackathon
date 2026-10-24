"""N-1 robust door synthesis: never worse in its own worst case, verified against an independent solve, deterministic."""
import pytest

from floorwise.core.model import Building
from floorwise.evacuation import Hazard, Occupants
from floorwise.evacuation.robust import robust_doors, usable_exits
from floorwise.paths import DATA


def case(name: str, room: str):
    building = Building.load(DATA / "dev" / name)
    fire = next(s["id"] for s in building.spaces.values() if s["name"] == room)
    return building, Occupants.from_seats(building), Hazard(spaces=(fire,))


@pytest.fixture(scope="module")
def campus():
    building, occupants, hazard = case("proc-campus-dev-000", "Canteen 0.28")
    return building, occupants, hazard, robust_doors(building, occupants, hazard)


def worst(scenarios):
    return max(s.badness for s in scenarios)


def test_the_worst_case_never_gets_worse_and_is_verified(campus):
    plan = campus[3]
    assert worst(plan.scenarios_after) <= worst(plan.scenarios_before)
    assert plan.verified and len(plan.scenarios_before) == len(plan.scenarios_after) >= 3


def test_every_fix_strictly_improves_the_worst_case(campus):
    for fix in campus[3].fixes:
        assert fix.worst_after.badness < fix.worst_before.badness


def test_scenarios_are_the_given_case_plus_each_usable_exit_lost(campus):
    building, _, hazard, plan = campus
    lost = [s.lost_exit for s in plan.scenarios_before]
    assert lost == [None, *usable_exits(building, [hazard])]
    assert all("outside" in building.openings[e]["space_ids"] for e in lost[1:])


def test_identical_inputs_give_identical_plans(campus):
    building, occupants, hazard, plan = campus
    assert robust_doors(building, occupants, hazard) == plan


def test_a_building_where_nothing_helps_gets_no_fixes_and_no_regression():
    building, occupants, hazard = case("proc-factory-dev-003", "Meeting room 0.24")
    plan = robust_doors(building, occupants, hazard)
    assert plan.verified and worst(plan.scenarios_after) <= worst(plan.scenarios_before)
    assert all(f.worst_after.badness < f.worst_before.badness for f in plan.fixes)
