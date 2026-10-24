import dataclasses
import re
from pathlib import Path

import pytest
from reason_support import FACTORY_DIR

from floorwise.core.model import Building
from floorwise.paths import DATA
from floorwise.reason.types import (
    Capacity,
    Hazard,
    OccupantSpec,
    Responders,
    ScenarioSpec,
    UserConstraints,
    World,
)


def test_scenario_spec_from_dict_equals_direct_construction():
    spec = ScenarioSpec.from_dict({
        "hazards": [{"spaces": ["a"], "elements": ["d1"], "start_s": 30}],
        "capacities": [{"element": "d1", "kind": "rate_persons_per_s", "value": 1.5},
                       {"element": "d2", "kind": "total_persons", "value": 40}],
        "occupants": {"source": "uniform", "uniform_count": 5, "overrides": {"b": 2}},
        "objective": "min_total_person_time",
        "responders": {"auto": True, "target": "a"},
        "user": {"step_free": True, "min_door_width_m": 0.9, "avoid_lifts": True},
    })
    assert spec == ScenarioSpec(
        hazards=(Hazard(spaces=("a",), elements=("d1",), start_s=30.0),),
        capacities=(Capacity("d1", "rate_persons_per_s", 1.5), Capacity("d2", "total_persons", 40.0)),
        occupants=OccupantSpec(source="uniform", uniform_count=5, overrides=(("b", 2),)),
        objective="min_total_person_time",
        responders=Responders(auto=True, target="a"),
        user=UserConstraints(step_free=True, min_door_width_m=0.9, avoid_lifts=True),
    )


@pytest.mark.parametrize("bad,needle", [
    ({"capacities": [{"element": "d", "kind": "persons_per_minute", "value": 1}]}, "kind"),
    ({"capacities": [{"element": "d", "kind": "total_persons", "value": -3}]}, "value"),
    ({"hazards": [{}]}, "hazard"),
    ({"hazards": [{"spaces": ["a"], "start_s": -1}]}, "start_s"),
    ({"occupants": {"source": "uniform"}}, "uniform_count"),
    ({"occupants": {"source": "crowd"}}, "source"),
    ({"responders": {}}, "responders"),
    ({"objective": "min_vibes"}, "objective"),
    ({"user": {"min_door_width_m": 0}}, "min_door_width_m"),
    ({"surprise": 1}, "surprise"),
])
def test_scenario_spec_rejects_illegal_states_naming_the_field(bad, needle):
    with pytest.raises(ValueError, match=needle):
        ScenarioSpec.from_dict(bad)


def test_types_are_frozen():
    spec = ScenarioSpec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.objective = "min_evacuation_time"  # type: ignore[misc]


def test_world_lineage_is_a_new_object_and_leaves_the_building_alone():
    building = Building.load(FACTORY_DIR)
    g0 = World.of(building)
    g1 = g0.derive(closed={"x"}, change="close x")
    g2 = g1.derive(closed={"y"}, change="close y")
    assert (g0.label, g1.label, g2.label) == ("G0", "G1", "G2")
    assert g0.closed == frozenset() and g1.closed == {"x"} and g2.closed == {"x", "y"}
    assert g2.history == ("close x", "close y")
    assert g1.building is building


def test_no_building_ids_or_names_in_the_package():
    files = [*Path("floorwise/reason").glob("*.py"), *Path("floorwise/reason").glob("*.json")]
    source = "\n".join(p.read_text(encoding="utf-8") for p in files)
    assert len(files) >= 8 and source
    assert not re.search(r"proc-(?:factory|campus)|osm-way|resplan-\d|swiss-\d", source)
    building_ids = {p.name for split in ("train", "dev", "test") for p in (DATA / split).iterdir() if p.is_dir()}
    assert len(building_ids) == 280
    assert not [b for b in building_ids if b in source]


def test_capacity_units_follow_the_kind():
    assert Capacity("d", "rate_persons_per_s", 1.3).unit == "persons/s"
    assert Capacity("d", "total_persons", 40).unit == "persons"


def test_a_bare_string_is_one_id_not_a_list_of_characters():
    spec = ScenarioSpec.from_dict({"hazards": [{"spaces": "room-1"}], "responders": {"entrances": "door-1"}})
    assert spec.hazards[0].spaces == ("room-1",) and spec.responders.entrances == ("door-1",)


@pytest.mark.parametrize("bad", [
    {"occupants": {"source": "user", "overrides": [["a", 1]]}},
    {"occupants": {"source": "user", "overrides": {"a": 2.7}}},
    {"capacities": [{"element": "d", "kind": "total_persons", "value": True}]},
])
def test_wrong_shapes_are_value_errors(bad):
    with pytest.raises(ValueError):
        ScenarioSpec.from_dict(bad)
