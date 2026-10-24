"""CCRP (heuristic) and nearest-exit assignment against the exact optimum."""

from evac_support import make_building

from floorwise.evacuation import Hazard, Occupants, evacuate

HALL = {"A": (0, 0, 4, 4), "C": (4, 0, 14, 4)}


def hall_with_two_exits(people: int):
    """Everyone starts in C. N is nearer than S, both 1.0 m wide: nearest-exit sends everybody through N."""
    building = make_building(HALL, [("AC", "A", "C", 3.0, (4, 2)), ("N", "C", "outside", 1.0, (7, 4)),
                                    ("S", "C", "outside", 1.0, (13, 0))])
    return building, Occupants.explicit({"C": people})


def test_ccrp_and_nearest_agree_with_exact_when_there_is_one_route():
    building = make_building({"A": (0, 0, 4, 4)}, [("D", "A", "outside", 1.0, (4, 2))])
    result = evacuate(building, Occupants.explicit({"A": 12}))
    assert result.ccrp.T_s == result.nearest_exit.T_s == result.T_s
    assert result.ccrp.evacuated == result.nearest_exit.evacuated == 12


def test_nearest_exit_is_strictly_worse_than_the_optimum_when_it_overloads_one_door():
    building, occupants = hall_with_two_exits(60)
    result = evacuate(building, occupants)
    assert result.nearest_exit.by_exit == {"N": 60}
    assert set(result.by_exit) == {"N", "S"}
    assert result.nearest_exit.T_s > result.T_s


def test_ccrp_is_never_better_than_exact_and_uses_both_exits():
    building, occupants = hall_with_two_exits(60)
    result = evacuate(building, occupants)
    assert result.T_s <= result.ccrp.T_s
    assert result.ccrp.evacuated == 60 and set(result.ccrp.by_exit) == {"N", "S"}


def test_baselines_report_who_they_could_not_get_out():
    building, occupants = hall_with_two_exits(10)
    result = evacuate(building, occupants, hazard=Hazard(elements=("N", "S")))
    assert result.evacuated == 0 and result.ccrp.evacuated == 0 and result.nearest_exit.evacuated == 0
    assert result.cut_off == {"C": 10}


def test_total_cap_on_an_exit_diverts_the_rest_in_all_three_methods():
    from floorwise.evacuation import Capacity

    building, occupants = hall_with_two_exits(30)
    result = evacuate(building, occupants, capacities=[Capacity("N", "total_persons", 10)])
    assert result.by_exit["N"] <= 10 and result.evacuated == 30
    assert result.ccrp.by_exit.get("N", 0) <= 10 and result.ccrp.evacuated == 30
