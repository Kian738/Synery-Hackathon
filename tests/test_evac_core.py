"""Exact core on hand-checkable buildings: capacity maths, time-expanded max-flow, min-cut, hazard, units."""

import json

import pytest
from evac_support import DT, door_caps, hop_steps, make_building

from floorwise.evacuation import (
    Capacity,
    FlowParams,
    Hazard,
    Occupants,
    evacuate,
    to_dict,
)

ROOM = {"A": (0, 0, 4, 4)}


def single_room(width: float = 1.0, people: int = 10):
    building = make_building(ROOM, [("D", "A", "outside", width, (4, 2))])
    return building, Occupants.explicit({"A": people})


def test_single_room_matches_hand_computation():
    building, occupants = single_room(width=1.0, people=10)
    result = evacuate(building, occupants, with_ccrp=False, with_nearest=False)
    tau = hop_steps(building, "A", "outside", (4, 2))
    caps = door_caps(1.0, 6)
    assert caps[:4] == [4, 5, 4, 5]  # 0.9212 persons/s * 5 s, cumulative floor
    departures, left = [], 10
    for cap in caps:
        moved = min(cap, left)
        departures.append(moved)
        left -= moved
        if not left:
            break
    assert [(m.depart_s, m.persons) for m in result.schedule] == [(DT * k, n) for k, n in enumerate(departures)]
    assert result.T_s == DT * (len(departures) - 1 + tau)
    assert (result.evacuated, result.total, result.stranded) == (10, 10, {})
    assert result.by_exit == {"D": 10}
    assert result.bottleneck == ("D",)  # the door queue, not walking time, sets T
    assert result.time_limited == ()


def test_wider_door_is_never_slower_and_flow_band_is_a_parameter():
    times = []
    for width in (0.9, 1.2, 2.0):
        building, occupants = single_room(width=width, people=40)
        times.append(evacuate(building, occupants, with_ccrp=False, with_nearest=False).T_s)
    assert times == sorted(times, reverse=True) and times[0] > times[-1]
    building, occupants = single_room(width=1.2, people=40)
    low = evacuate(building, occupants, params=FlowParams(specific_flow=1.0), with_ccrp=False, with_nearest=False)
    high = evacuate(building, occupants, params=FlowParams(specific_flow=1.6), with_ccrp=False, with_nearest=False)
    assert low.T_s > high.T_s


def test_free_flow_limited_case_reports_walking_not_a_door():
    building, occupants = single_room(width=3.0, people=2)
    result = evacuate(building, occupants, with_ccrp=False, with_nearest=False)
    assert result.T_s == DT * hop_steps(building, "A", "outside", (4, 2))
    assert result.bottleneck == ()
    assert result.time_limited == ("A",)
    assert 0 < result.free_flow_s <= result.T_s


def test_explicit_rate_and_total_capacity_override_width():
    building, occupants = single_room(width=3.0, people=20)
    wide = evacuate(building, occupants, with_ccrp=False, with_nearest=False)
    slow = evacuate(building, occupants, capacities=[Capacity("D", "rate_persons_per_s", 0.5)],
                    with_ccrp=False, with_nearest=False)
    assert slow.T_s > wide.T_s
    total = evacuate(building, occupants, capacities=[Capacity("D", "total_persons", 8)],
                     with_ccrp=False, with_nearest=False)
    assert total.evacuated == 8 and sum(total.stranded.values()) == 12


def test_total_cap_on_interior_door_is_refused_not_approximated():
    building = make_building({"A": (0, 0, 4, 4), "B": (4, 0, 8, 4)},
                             [("AB", "A", "B", 1.0, (4, 2)), ("X", "B", "outside", 1.0, (8, 2))])
    with pytest.raises(ValueError, match="total_persons"):
        evacuate(building, Occupants.explicit({"A": 3}), capacities=[Capacity("AB", "total_persons", 2)])


def test_two_exits_split_the_load_and_min_cut_names_the_binding_exit():
    building = make_building(
        {"A": (0, 0, 4, 4), "C": (4, 0, 14, 4)},
        [("AC", "A", "C", 3.0, (4, 2)), ("N", "C", "outside", 1.0, (9, 4)), ("S", "C", "outside", 1.0, (9, 0))],
    )
    one = evacuate(building, Occupants.explicit({"A": 30}), hazard=Hazard(elements=("S",)),
                   with_ccrp=False, with_nearest=False)
    two = evacuate(building, Occupants.explicit({"A": 30}), with_ccrp=False, with_nearest=False)
    assert two.T_s < one.T_s
    assert set(two.by_exit) == {"N", "S"} and sum(two.by_exit.values()) == 30
    assert one.by_exit == {"N": 30}
    assert one.bottleneck == ("N",)


def test_hazard_space_after_block_time_carries_no_flow_and_traps_late_occupants():
    building = make_building({"A": (0, 0, 4, 4), "B": (4, 0, 8, 4)},
                             [("AB", "A", "B", 1.0, (4, 2)), ("X", "B", "outside", 1.0, (8, 2))])
    result = evacuate(building, Occupants.explicit({"A": 30, "B": 0}), hazard=Hazard(spaces=("B",), from_s=20),
                      with_ccrp=False, with_nearest=False)
    assert result.evacuated < 30 and sum(result.stranded.values()) == 30 - result.evacuated
    assert all(m.depart_s < 20 for m in result.schedule if m.from_space == "B")
    assert all(m.arrive_s <= 20 for m in result.schedule if m.to_space == "B")
    assert result.cut_off == {}  # they could have left in isolation; time ran out


def test_occupants_in_a_hazard_space_from_the_start_are_cut_off_and_reported():
    building = make_building({"A": (0, 0, 4, 4), "B": (4, 0, 8, 4)},
                             [("AB", "A", "B", 1.0, (4, 2)), ("X", "B", "outside", 1.0, (8, 2))])
    result = evacuate(building, Occupants.explicit({"A": 5, "B": 7}), hazard=Hazard(spaces=("B",)),
                      with_ccrp=False, with_nearest=False)
    assert result.evacuated == 0
    assert result.cut_off == {"A": 5, "B": 7} and result.stranded == {"A": 5, "B": 7}
    assert result.T_s == 0 and result.total == 12


def test_empty_occupants_give_zero_time():
    building, _ = single_room()
    result = evacuate(building, Occupants.explicit({}), with_ccrp=False, with_nearest=False)
    assert (result.T_s, result.total, result.evacuated, result.schedule) == (0, 0, 0, ())


def test_default_occupants_are_seat_assets_labelled_estimate():
    building = make_building(ROOM, [("D", "A", "outside", 1.0, (4, 2))], seats={"A": 7})
    occupants = Occupants.from_seats(building)
    assert occupants.by_space == {"A": 7} and occupants.source == "seats" and "estimate" in occupants.label


def test_identical_inputs_give_byte_identical_json():
    building = make_building(
        {"A": (0, 0, 4, 4), "C": (4, 0, 14, 4)},
        [("AC", "A", "C", 3.0, (4, 2)), ("N", "C", "outside", 1.0, (9, 4)), ("S", "C", "outside", 1.0, (9, 0))],
    )
    runs = [json.dumps(to_dict(evacuate(building, Occupants.explicit({"A": 30, "C": 11}))), sort_keys=True)
            for _ in range(3)]
    assert runs[0] == runs[1] == runs[2] and len(runs[0]) > 200


def test_params_are_validated_and_frozen():
    with pytest.raises(ValueError):
        FlowParams(dt_s=0)
    with pytest.raises(AttributeError):
        FlowParams().dt_s = 3  # type: ignore[misc]
