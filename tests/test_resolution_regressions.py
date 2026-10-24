"""Entity-resolution behaviour when a name fits several spaces (OSM buildings repeat names).

Synthetic buildings pin the rules down; one train fixture checks the whole benchmark path. Nothing here
learns or encodes a gold label: when the question text cannot tell spaces apart, the tests expect every reading."""

import pytest

from floorwise.agent.answer import answer_with_trace, pick_reading
from floorwise.agent.spec import MAX_ALTERNATIVES, QuerySpec, describe_ambiguity, resolve_spec_all
from floorwise.core import resolve as R
from floorwise.core.model import Building
from floorwise.paths import DATA


def space(index: int, floor: str, name: str, ref: str | None, room_type: str = "office") -> dict:
    return {"id": f"S{index:03d}", "floor_id": floor, "name": name, "ref": ref, "type": "room", "room_type": room_type,
            "polygon": [[index, 0], [index + 1, 0], [index + 1, 1], [index, 1]]}


def make_building(spaces: list[dict]) -> Building:
    floors = [{"id": "F0", "name": "Ground floor", "level": 0}, {"id": "F1", "name": "Floor 1", "level": 1}]
    return Building({"building": {"id": "synthetic", "name": "Synthetic", "source": "test"}, "floors": floors, "spaces": spaces,
                     "openings": [], "vertical_connectors": [], "assets": []})


@pytest.fixture()
def offices() -> Building:
    spaces = [space(i, "F0", "Büro", f"0.{i:02d}") for i in range(1, 4)]            # 3 offices share a name on the ground floor
    spaces += [space(10 + i, "F1", "Büro", f"1.{i:02d}") for i in range(1, 10)]      # 9 on floor 1
    spaces += [space(30, "F0", "Toilet 0.04", "0.04", "toilet")]
    return make_building(spaces)


def route(start: str, destination: str) -> QuerySpec:
    return QuerySpec(kind="route", start=start, destination=destination)


def test_unique_mentions_give_one_reading(offices):
    readings = resolve_spec_all(offices, route("Toilet 0.04 (Ground floor)", "Büro 0.02 (Ground floor)"))
    assert readings == [{"start": "S030", "destination": "S002", "step_free": False}]


def test_a_room_number_in_the_text_settles_a_repeated_name(offices):
    assert R.resolve_space(offices, "Büro 1.05 (Floor 1)").id == "S015"
    with pytest.raises(R.ResolveError) as error:
        R.resolve_space(offices, "Büro (Floor 1)")
    assert len(error.value.candidates) == 9


def test_every_candidate_is_a_reading_when_the_text_cannot_tell_them_apart(offices):
    readings = resolve_spec_all(offices, route("Büro (Floor 1)", "Toilet 0.04 (Ground floor)"))
    assert sorted(r["start"] for r in readings) == sorted(f"S{10 + i:03d}" for i in range(1, 10))
    assert {r["destination"] for r in readings} == {"S030"}


def test_repeated_ambiguous_mentions_preserve_same_room_readings(offices):
    readings = resolve_spec_all(offices, route("Büro (Ground floor)", "Büro (Ground floor)"))
    assert len(readings) == 9                                  # 3 x 3, including valid zero-length readings
    assert {(r["start"],r["destination"]) for r in readings if r["start"]==r["destination"]} == {(f"S{i:03d}",f"S{i:03d}") for i in range(1,4)}
    tour = QuerySpec(kind="tour", stops=["Büro (Ground floor)", "Büro (Ground floor)", "Büro (Floor 1)"])
    readings = resolve_spec_all(offices, tour)
    assert len(readings) == MAX_ALTERNATIVES
    assert any(r["stops"][0]==r["stops"][1] for r in readings)
    assert {r["stops"][0] for r in readings} == {"S001", "S002", "S003"}


def test_a_single_candidate_named_twice_is_left_alone(offices):
    readings = resolve_spec_all(offices, route("Toilet 0.04 (Ground floor)", "Toilet 0.04 (Ground floor)"))
    assert [(r["start"], r["destination"]) for r in readings] == [("S030", "S030")]


def test_straight_line_repeated_mentions_include_zero_distance(offices):
    readings = resolve_spec_all(offices, QuerySpec(kind="straight_line_3d", first="Büro (Ground floor)", second="Büro (Ground floor)"))
    assert len(readings) == 9 and any(r["first"] == r["second"] for r in readings)


def test_many_ambiguous_stops_are_sampled_across_the_space_not_cut_off_after_the_first(offices):
    tour = QuerySpec(kind="tour", stops=["Büro (Floor 1)"] * 3)  # 9**3 possible readings, including repeats
    readings = resolve_spec_all(offices, tour)
    assert len(readings) == MAX_ALTERNATIVES
    assert len({r["stops"][0] for r in readings}) == 9           # the first stop is not pinned to the first candidate
    assert len({r["stops"][2] for r in readings}) == 9
    assert readings == resolve_spec_all(offices, tour)           # deterministic
    assert len({tuple(r["stops"]) for r in readings}) == MAX_ALTERNATIVES


def test_huge_candidate_products_stay_bounded(offices):
    tour = QuerySpec(kind="tour", stops=["Büro (Floor 1)"] * 9)  # 9**9 combinations: never materialised
    assert len(resolve_spec_all(offices, tour)) == MAX_ALTERNATIVES


def test_a_mention_that_matches_nothing_keeps_its_own_error(offices):
    with pytest.raises(R.ResolveError, match="Quantum lab"):
        resolve_spec_all(offices, route("Büro (Floor 1)", "Quantum lab (Floor 1)"))


def test_ambiguity_report_says_what_could_tell_candidates_apart():
    building = make_building([space(1, "F0", "Lab", "A1"), space(2, "F0", "Lab", "A2"), space(3, "F0", "Hall", "H1"), space(4, "F0", "Hall", "H1")])
    report = describe_ambiguity(building, route("Lab (Ground floor)", "Hall (Ground floor)"))
    by_slot = {entry["slot"]: entry for entry in report}
    assert by_slot["start"]["differs_in"] == ["ref"]
    assert [c["ref"] for c in by_slot["start"]["candidates"]] == ["A1", "A2"]
    # Identical name and identical room number: nothing recorded separates them, so nothing in a question could.
    assert by_slot["destination"]["differs_in"] == []
    assert len(resolve_spec_all(building, route("Lab (Ground floor)", "Hall (Ground floor)"))) == 4
    assert describe_ambiguity(building, QuerySpec(kind="route", start="Lab A1", destination="Lab A2")) == []


def test_pick_reading_still_prefers_the_value_most_readings_agree_on():
    assert pick_reading(["10.0 m", "10.05 m", "20 m"]) in ("10.0 m", "10.05 m")  # the two that agree beat the outlier
    assert pick_reading(["Lab", "Hall", "Lab"]) == "Lab"
    assert pick_reading(["5", "50", "500"]) == "50"


TRAIN_FIXTURE = DATA / "train" / "osm-way37850565"


@pytest.mark.skipif(not TRAIN_FIXTURE.exists(), reason="supplied train data not present")
def test_benchmark_path_reports_the_ambiguity_instead_of_pretending():
    text = "Starting at Büro (Ground floor), visit Büro (Ground floor), then Büro (Floor 1) in this order. What is the route?"
    reply, trace = answer_with_trace(TRAIN_FIXTURE, text)
    assert len(trace["readings"]) == MAX_ALTERNATIVES
    assert any(r["stops"][0]==r["stops"][1] for r in trace["readings"])
    assert [entry["slot"] for entry in trace["ambiguity"]] == ["stops[0]", "stops[1]", "stops[2]"]
    assert all(entry["differs_in"] == ["ref"] for entry in trace["ambiguity"])
    assert reply.startswith("Note: the question does not say which space it means")
    assert "best guess" in reply.splitlines()[0]
    assert reply.rstrip().splitlines()[-1].lower().startswith("answer:")
    # A room number in the wording leaves nothing to guess.
    reply, trace = answer_with_trace(TRAIN_FIXTURE, "Is there a step-free route from Büro 0.12 (Ground floor) to Toilet 0.04 (Ground floor)?")
    assert len(trace["readings"]) == 1 and "ambiguity" not in trace and not reply.startswith("Note:")
