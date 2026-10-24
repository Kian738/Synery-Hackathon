"""Reserve-then-route responders on a hand-made corridor building, and on real buildings."""

import math

import pytest
from evac_support import DT, anchor, make_building, real_building

from floorwise.evacuation import (
    FlowParams,
    Hazard,
    Occupants,
    Responders,
    evacuate,
    with_responders,
)

SPEED = 1.34


def corridor_building():
    """Corridor C (x 0..20). W (wide) and E (narrow) are entrances; the fire room R is off C near E."""
    return make_building(
        {"C": (0, 0, 20, 4), "R": (14, 4, 18, 8)},
        [("W", "C", "outside", 3.0, (0, 2)), ("E", "C", "outside", 1.0, (20, 2)), ("RC", "C", "R", 0.9, (16, 4))],
    )


def test_arrival_time_is_walking_time_to_the_target_door():
    building = corridor_building()
    plan = with_responders(building, Occupants.explicit({"C": 30}), Hazard(spaces=("R",)),
                           responders=Responders(target="R", entrances=("E",), k_routes=1))
    assert plan.status == "ok" and plan.chosen.entrance == "E"
    expected = (math.dist(anchor(building, "C"), (20, 2)) + math.dist(anchor(building, "C"), (16, 4))) / SPEED
    assert plan.chosen.arrival_s == pytest.approx(expected, abs=1e-3)  # results are rounded to 3 dp
    assert plan.chosen.elements == ("E", "RC")


def test_responders_never_make_the_evacuation_faster_and_the_numbers_are_reported_both_ways():
    building = corridor_building()
    occupants = Occupants.explicit({"C": 60})
    plan = with_responders(building, occupants, Hazard(spaces=("R",)), responders=Responders(target="R"))
    without = evacuate(building, occupants, Hazard(spaces=("R",)), with_ccrp=False, with_nearest=False)
    assert plan.T_without_s == without.T_s
    assert plan.T_with_s >= plan.T_without_s
    assert plan.delay_s == plan.T_with_s - plan.T_without_s
    assert plan.evacuation.T_s == plan.T_with_s and plan.evacuation.evacuated == 60


def test_chosen_candidate_minimises_evacuation_time_and_a_deadline_changes_the_choice():
    building = corridor_building()
    occupants = Occupants.explicit({"C": 80})
    hazard = Hazard(spaces=("R",))
    free = with_responders(building, occupants, hazard, responders=Responders(target="R", k_routes=2))
    evaluated = [c for c in free.candidates if c.evacuation_T_s is not None]
    assert free.chosen.evacuation_T_s == min(c.evacuation_T_s for c in evaluated)
    assert len({c.entrance for c in free.candidates}) == 2
    arrivals = sorted({c.arrival_s for c in free.candidates})
    deadline = (arrivals[0] + arrivals[-1]) / 2
    tight = with_responders(building, occupants, hazard, responders=Responders(target="R", deadline_s=deadline))
    assert tight.chosen.arrival_s <= deadline
    assert all(c.status == "over_deadline" for c in tight.candidates if c.arrival_s > deadline)


def test_deadline_nobody_can_meet_is_reported_not_ignored():
    building = corridor_building()
    plan = with_responders(building, Occupants.explicit({"C": 10}), Hazard(spaces=("R",)),
                           responders=Responders(target="R", deadline_s=1.0))
    assert plan.status == "deadline_unmet" and plan.chosen is None and plan.T_with_s is None
    assert plan.T_without_s > 0 and plan.candidates


def test_responder_routes_avoid_hazard_and_unusable_entrances():
    building = corridor_building()
    plan = with_responders(building, Occupants.explicit({"C": 10}), Hazard(spaces=("R",), elements=("W",)),
                           responders=Responders(target="R"))
    assert {c.entrance for c in plan.candidates} == {"E"}
    blocked = with_responders(building, Occupants.explicit({"C": 10}), Hazard(spaces=("R",), elements=("W", "E")),
                              responders=Responders(target="R"))
    assert blocked.status == "no_route" and blocked.chosen is None


def test_reservation_halves_effective_width_during_the_window_only():
    building = corridor_building()
    plan = with_responders(building, Occupants.explicit({"C": 200}), Hazard(spaces=("R",)),
                           responders=Responders(target="R", entrances=("W",), team_size=2, k_routes=1))
    windows = {r.element: (r.from_s, r.to_s) for r in plan.chosen.reservations}
    assert set(windows) == {"W", "RC"}
    start, end = windows["W"]
    assert start == 0.0 and 0 < end - start <= 2 * DT
    assert plan.T_with_s >= plan.T_without_s


def test_identical_inputs_identical_plan():
    import json

    from floorwise.evacuation import to_dict

    building = corridor_building()
    runs = [json.dumps(to_dict(with_responders(building, Occupants.explicit({"C": 40}), Hazard(spaces=("R",)),
                                               responders=Responders(target="R"))), sort_keys=True)
            for _ in range(2)]
    assert runs[0] == runs[1]


def test_real_building_responders_reach_a_fire_room_without_crossing_it():
    building = real_building("proc-factory-dev-003")
    occupants = Occupants.from_seats(building)
    fire = max(occupants.by_space, key=lambda s: (occupants.by_space[s], s))
    plan = with_responders(building, occupants, Hazard(spaces=(fire,)), params=FlowParams(),
                           responders=Responders(target=fire, k_routes=2, max_candidates=4))
    assert plan.status == "ok"
    assert fire not in plan.chosen.spaces[:-1] and plan.T_with_s >= plan.T_without_s


def test_a_large_team_in_a_single_entrance_visibly_slows_the_evacuation():
    building = make_building(
        {"C": (0, 0, 20, 4), "R": (14, 4, 18, 8)},
        [("E", "C", "outside", 1.0, (20, 2)), ("RC", "C", "R", 0.9, (16, 4))],
    )
    occupants = Occupants.explicit({"C": 60})
    small = with_responders(building, occupants, Hazard(spaces=("R",)), responders=Responders(target="R", team_size=1))
    large = with_responders(building, occupants, Hazard(spaces=("R",)), responders=Responders(target="R", team_size=12))
    assert large.T_with_s > large.T_without_s == small.T_without_s
    assert large.delay_s > small.delay_s >= 0
