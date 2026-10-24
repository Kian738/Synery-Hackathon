from dataclasses import replace

from reason_support import FACTORY_DIR, HOUSE_DIR

from floorwise.core.model import Building
from floorwise.reason.elicit import missing, next_question
from floorwise.reason.types import Hazard, OccupantSpec, Responders, ScenarioSpec

HAZARD = (Hazard(spaces=("any-space",)),)


def test_empty_spec_ranks_the_hazard_first_and_everything_else_below_it():
    gaps = missing(ScenarioSpec())
    assert [g.field for g in gaps] == ["hazards", "occupants", "objective", "capacities"]
    assert [g.importance for g in gaps] == sorted((g.importance for g in gaps), reverse=True)
    assert gaps[0].essential and not any(g.essential for g in gaps[1:])


def test_next_question_is_one_question_with_two_to_four_options():
    question = next_question(ScenarioSpec())
    assert question.field == "hazards"
    assert 2 <= len(question.options) <= 4
    assert len({o.value for o in question.options}) == len(question.options)
    assert question.text.endswith("?")


def test_every_default_option_is_labelled_as_an_assumption():
    building = Building.load(FACTORY_DIR)
    gaps = missing(ScenarioSpec(hazards=HAZARD), building)
    assert gaps
    for gap in gaps:
        defaults = [o for o in gap.options if o.assumption]
        assert len(defaults) == 1 and "assumption" in defaults[0].label
        assert not any("assumption" in o.label for o in gap.options if not o.assumption)


def test_nothing_essential_missing_returns_none_and_lists_defaults_as_assumptions():
    building = Building.load(FACTORY_DIR)
    spec = ScenarioSpec(hazards=HAZARD)
    assert next_question(spec, building) is None
    remaining = missing(spec, building)
    assert [g.field for g in remaining] == ["occupants", "objective", "capacities"]
    assert all(not g.essential and any(o.assumption for o in g.options) for g in remaining)


def test_never_asks_about_something_already_given():
    full = ScenarioSpec(
        hazards=HAZARD,
        occupants=OccupantSpec(source="uniform", uniform_count=3),
        objective="min_evacuation_time",
        responders=Responders(auto=True, target="any-space"),
    )
    asked = {g.field for g in missing(full)}
    assert "hazards" not in asked and "occupants" not in asked and "objective" not in asked
    assert next_question(full) is None
    assert next_question(replace(full, hazards=())).field == "hazards"


def test_a_building_without_seat_data_makes_the_occupant_source_essential():
    house_without_seats = Building.load(HOUSE_DIR)
    data = house_without_seats.data
    stripped = Building({**data, "assets": [a for a in data["assets"] if "chair" not in a["type"] and a["type"] != "bench"]})
    spec = ScenarioSpec(hazards=HAZARD)
    question = next_question(spec, stripped)
    assert question.field == "occupants"
    assert question.options[0].value in {"user", "uniform"}
    assert next_question(spec, house_without_seats) is None  # the house has seats, so the estimate exists
    assert next_question(replace(spec, occupants=OccupantSpec(source="uniform", uniform_count=2)), stripped) is None


def test_a_seats_source_without_seat_data_or_a_user_source_without_counts_is_still_a_question():
    house = Building.load(HOUSE_DIR)
    data = house.data
    stripped = Building({**data, "assets": [a for a in data["assets"] if "chair" not in a["type"]]})
    for source in ("seats", "user"):
        spec = ScenarioSpec(hazards=HAZARD, occupants=OccupantSpec(source=source))
        asked = next_question(spec, stripped)
        assert asked is not None and asked.field == "occupants"
    assert next_question(ScenarioSpec(hazards=HAZARD, occupants=OccupantSpec(source="seats")), house) is None
