"""Where to add or widen a door: min-cut pruning, greedy exact re-solve, independent verification."""

import json

import pytest
from evac_support import make_building, real_building

from floorwise.core import geometry
from floorwise.evacuation import (
    FlowParams,
    Hazard,
    Occupants,
    best_doors,
    evacuate,
    to_dict,
)
from floorwise.evacuation import doors as doors_module
from floorwise.evacuation.doors import edited_building

NEW, WIDEN = 0.9, 1.8


def two_room_building():
    """40 people in A behind one narrow door; B next door has a wide exit. D and E are an unrelated empty pair."""
    return make_building(
        {"A": (0, 0, 6, 6), "B": (6, 0, 12, 6), "C": (0, 6, 12, 10), "D": (20, 0, 26, 6), "E": (26, 0, 32, 6)},
        [("AC", "A", "C", 0.9, (3, 6)), ("BC", "B", "C", 1.2, (9, 6)), ("BX", "B", "outside", 1.5, (12, 3)),
         ("CX", "C", "outside", 0.9, (6, 10)), ("DX", "D", "outside", 1.0, (20, 3)), ("EX", "E", "outside", 1.0, (32, 3))],
    )


def occupants():
    return Occupants.explicit({"A": 40})


def best_single_fix_by_brute_force(building, occ):
    """Oracle: evaluate every candidate with a full independent evacuate on an edited copy of the building."""
    base = evacuate(building, occ, with_ccrp=False, with_nearest=False)
    results = {}
    spaces = sorted(building.spaces)
    for a in spaces:
        for b, _ in geometry.wall_neighbours(building, a):
            if a < b and not any(set(o["space_ids"]) == {a, b} for o in building.openings.values()):
                edited = edited_building(building, [("add", f"new:{a}|{b}", (a, b), geometry.wall_midpoint(building, a, b), NEW)])
                results[("add", a, b)] = evacuate(edited, occ, with_ccrp=False, with_nearest=False)
    for opening_id, opening in building.openings.items():
        if opening["width_m"] < WIDEN:
            edited = edited_building(building, [("widen", opening_id, tuple(opening["space_ids"]), None, WIDEN)])
            results[("widen", opening_id)] = evacuate(edited, occ, with_ccrp=False, with_nearest=False)
    return base, results


def test_greedy_first_fix_equals_the_brute_force_optimum_and_is_verified():
    building = two_room_building()
    plan = best_doors(building, occupants())
    base, results = best_single_fix_by_brute_force(building, occupants())
    oracle = min(r.T_s for r in results.values())
    assert plan.T_before_s == base.T_s
    assert oracle < base.T_s, "the fixture must have an improving door"
    first = plan.fixes[0]
    assert first.T_before_s == base.T_s and first.T_after_s == oracle
    assert first.verified is True
    assert plan.T_after_s == plan.fixes[-1].T_after_s <= first.T_after_s


def test_pruning_by_the_min_cut_skips_candidates_that_cannot_help_without_losing_the_optimum():
    plan = best_doors(two_room_building(), occupants())
    assert plan.candidates > plan.crossing_cut >= plan.evaluated >= 1
    # D-E and the entrance doors of empty rooms are in the candidate list but never cross the cut.
    assert all(fix.between[0] not in ("D", "E") for fix in plan.fixes)


def test_no_improving_door_returns_no_fixes():
    building = make_building({"A": (0, 0, 4, 4)}, [("D", "A", "outside", 3.0, (4, 2))])
    plan = best_doors(building, Occupants.explicit({"A": 2}))
    assert plan.fixes == () and plan.T_after_s == plan.T_before_s


def test_each_fix_is_checked_by_a_fresh_evacuate_on_an_edited_copy(monkeypatch):
    calls = []
    real = doors_module.evacuate

    def spy(building, *args, **kwargs):
        calls.append(building)
        return real(building, *args, **kwargs)

    monkeypatch.setattr(doors_module, "evacuate", spy)
    original = two_room_building()
    plan = best_doors(original, occupants(), max_fixes=2)
    assert len(calls) == len(plan.fixes) >= 1
    assert all(c is not original and c.openings is not original.openings for c in calls)
    assert len(original.openings) == 6  # the input building is never mutated


def test_a_fix_that_the_independent_solve_disagrees_with_is_not_marked_verified(monkeypatch):
    real = doors_module.evacuate

    def wrong(building, *args, **kwargs):
        result = real(building, *args, **kwargs)
        from dataclasses import replace

        return replace(result, T_s=result.T_s + 5)

    monkeypatch.setattr(doors_module, "evacuate", wrong)
    plan = best_doors(two_room_building(), occupants(), max_fixes=1)
    assert plan.fixes and plan.fixes[0].verified is False


def test_hazard_spaces_get_no_new_doors_and_output_is_deterministic():
    building = two_room_building()
    runs = [json.dumps(to_dict(best_doors(building, occupants(), Hazard(spaces=("C",)))), sort_keys=True)
            for _ in range(2)]
    assert runs[0] == runs[1]
    plan = best_doors(building, occupants(), Hazard(spaces=("C",)))
    assert all("C" not in fix.between for fix in plan.fixes)


def test_widening_reports_previous_width_and_new_door_reports_position():
    plan = best_doors(two_room_building(), occupants(), max_fixes=3)
    for fix in plan.fixes:
        if fix.kind == "widen":
            assert fix.previous_width_m is not None and fix.width_m == WIDEN > fix.previous_width_m
        else:
            assert fix.kind == "add" and fix.position is not None and fix.width_m == NEW


@pytest.mark.parametrize("name", ["proc-campus-dev-000", "osm-way27326387"])
def test_real_building_fixes_never_increase_time_and_are_verified(name):
    building = real_building(name)
    occ = Occupants.from_seats(building)
    plan = best_doors(building, occ, params=FlowParams(), max_fixes=2)
    before = evacuate(building, occ, with_ccrp=False, with_nearest=False)
    assert plan.T_before_s == before.T_s
    assert plan.T_after_s <= plan.T_before_s
    times = [plan.T_before_s] + [fix.T_after_s for fix in plan.fixes]
    assert times == sorted(times, reverse=True) and len(set(times)) == len(times)
    assert all(fix.verified for fix in plan.fixes)
