import copy
from dataclasses import replace

import pytest
from reason_support import (
    CAMPUS_DIR,
    FACTORY_DIR,
    HOUSE_DIR,
    duplicated_name,
    ground_exit_space,
    people,
    plan,
)

from floorwise.core import geometry, ops
from floorwise.core.graph import RouteGraph
from floorwise.core.model import Building
from floorwise.core.routing import plan_route
from floorwise.reason import run_plan
from floorwise.reason.operators import BOTTOM, REGISTRY, Operator, Param
from floorwise.reason.types import World

W = "#world"


def by_name(building: Building, name: str) -> str:
    (space_id,) = [s["id"] for s in building.spaces.values() if s["name"] == name]
    return space_id


@pytest.fixture(scope="module")
def factory() -> Building:
    return Building.load(FACTORY_DIR)


@pytest.fixture(scope="module")
def campus() -> Building:
    return Building.load(CAMPUS_DIR)


@pytest.fixture(scope="module")
def house() -> Building:
    return Building.load(HOUSE_DIR)


def lift_contrast_steps(start_name: str, floor_name: str, element_text: str):
    """Rooms reachable step-free from a start, then the same after closing one connector."""
    return [
        ("start", "resolve", {"world": W, "text": start_name}),
        ("floor", "resolve_floor", {"world": W, "text": floor_name}),
        ("before", "reach", {"world": W, "start": "#start", "floor": "#floor", "step_free": True}),
        ("el", "resolve_element", {"world": W, "text": element_text}),
        ("g1", "close", {"world": W, "element": "#el"}),
        ("after", "reach", {"world": "#g1", "start": "#start", "floor": "#floor", "step_free": True}),
        ("n_before", "count", {"items": "#before"}),
        ("n_after", "count", {"items": "#after"}),
        ("cmp", "compare", {"left": "#n_before", "right": "#n_after"}),
    ]


def test_contrast_pair_closing_the_lift_flips_the_answer_but_closing_the_stairs_does_not(factory):
    lift = run_plan(factory, plan("lift closed", lift_contrast_steps("Hall access 0.19", "Floor 1", "Office lift"), "#cmp"))
    stairs = run_plan(factory, plan("stairs closed", lift_contrast_steps("Hall access 0.19", "Floor 1", "Office staircase"), "#cmp"))
    assert lift.abstained is None and stairs.abstained is None
    assert (lift.answer.left, lift.answer.right, lift.answer.relation) == (29, 0, "greater")
    assert (stairs.answer.left, stairs.answer.right, stairs.answer.relation) == (29, 29, "equal")


def test_reach_equals_direct_core_call_on_two_kinds_of_building(factory, campus):
    for building, start_name, floor_name in [(factory, "Hall access 0.19", "Floor 1"), (campus, "Corridor 0.01", "Floor 3")]:
        trace = run_plan(building, plan("reach", [
            ("s", "resolve", {"world": W, "text": start_name}),
            ("f", "resolve_floor", {"world": W, "text": floor_name}),
            ("r", "reach", {"world": W, "start": "#s", "floor": "#f", "step_free": True}),
        ], "#r"))
        start = by_name(building, start_name) if building is factory else ground_exit_space(building)
        floor = next(f["id"] for f in building.floors.values() if f["name"] == floor_name)
        direct = ops.reachable_rooms_on_floor(building, start, floor, people(step_free=True))
        assert trace.abstained is None
        assert trace.answer == tuple(sorted(direct["space_ids"]))
        assert len(trace.answer) == direct["count"] > 0


def test_route_equals_direct_core_call(factory, campus, house):
    def room_on_level(building, level):
        return next(s["id"] for s in building.spaces.values() if s["type"] == "room" and building.level(s["floor_id"]) == level)

    cases = [
        (factory, by_name(factory, "Hall access 0.19"), by_name(factory, "Quality lab 0.21"), {}),
        (campus, ground_exit_space(campus), room_on_level(campus, 3), {"step_free": True}),
        (house, by_name(house, "Living room 0.01"), by_name(house, "Bathroom 0.04"), {"min_width_m": 0.9}),
    ]
    for building, start, end, flags in cases:
        trace = run_plan(building, plan("route", [("r", "route", {"world": W, "start": start, "end": end, **flags})], "#r"))
        direct = plan_route(building, [start, end], people(**flags))
        assert trace.abstained is None
        assert trace.answer.length_m == direct.length_m > 0
        assert trace.answer.space_path == tuple(direct.legs[0].space_path)
        assert trace.answer.element_path == tuple(direct.legs[0].element_path)
        assert trace.results[0].checks == ("path runs from start to end", "no closed element on the path")


def test_contrast_pair_on_route_closing_the_only_step_free_link_turns_a_length_into_an_abstention(factory):
    upstairs = next(s["id"] for s in factory.spaces.values() if s["type"] == "room" and factory.level(s["floor_id"]) == 1)

    def steps(world_ref):
        return [
            ("el", "resolve_element", {"world": W, "text": "Office lift"}),
            ("g1", "close", {"world": W, "element": "#el"}),
            ("r", "route", {"world": world_ref, "start": by_name(factory, "Hall access 0.19"), "end": upstairs, "step_free": True}),
        ]

    open_trace = run_plan(factory, plan("open", steps(W), "#r"))
    closed_trace = run_plan(factory, plan("closed", steps("#g1"), "#r"))
    assert open_trace.abstained is None and open_trace.answer.length_m > 0
    assert closed_trace.answer is None
    assert closed_trace.abstained.step == "r" and "no route" in closed_trace.abstained.reason.lower()


def test_closing_returns_a_new_world_and_never_mutates_the_building(factory):
    before = copy.deepcopy(factory.data)
    trace = run_plan(factory, plan("close", [("el", "resolve_element", {"world": W, "text": "Office lift"}),
                                             ("g1", "close", {"world": W, "element": "#el"})], "#g1"))
    world = trace.answer
    assert isinstance(world, World) and world.label == "G1" and len(world.closed) == 1
    assert world.building is factory and factory.data == before


def test_exits_area_count_and_occupant_literals(factory, campus, house):
    def answer(building, op, **args):
        trace = run_plan(building, plan("q", [("a", op, {"world": W, **args})], "#a"))
        assert trace.abstained is None, trace.abstained
        return trace.answer

    assert len(answer(factory, "exits")) == 4 and len(answer(campus, "exits")) == 2
    assert answer(house, "exits") == ("resplan-14509-F0-S001",)
    assert answer(factory, "area", spaces=by_name(factory, "Quality lab 0.21")) == 25.6
    seats = [answer(b, "occupants") for b in (factory, campus, house)]
    assert [(o.source, o.total, len(o.by_space)) for o in seats] == [("seats", 146, 42), ("seats", 358, 64), ("seats", 4, 1)]


def test_nearest_equals_direct_distances(factory):
    start = by_name(factory, "Hall access 0.19")
    trace = run_plan(factory, plan("nearest coffee", [
        ("item", "resolve_item", {"world": W, "text": "coffee machine"}),
        ("where", "find", {"world": W, "item": "#item"}),
        ("near", "nearest", {"world": W, "start": start, "candidates": "#where"}),
    ], "#near"))
    holders = sorted({a["space_id"] for a in factory.assets.values() if a["type"] == "coffee_machine"})
    distances = RouteGraph(factory, people(), keep=frozenset({start})).distances_from(start)
    expected = min((distances[h], h) for h in holders if h in distances)[1]
    assert trace.answer == expected and trace.results[1].value == tuple(holders)


def test_ambiguous_name_abstains_with_candidates_and_nothing_after_it_runs():
    building, name, count = duplicated_name()
    calls = []
    registry = REGISTRY.copy()
    registry.register(Operator("spy", (Param("spaces", "Space|Spaces"),), "Number", lambda spaces: calls.append(spaces) or 1.0))
    trace = run_plan(building, plan("ambiguous", [("who", "resolve", {"world": W, "text": name}),
                                                  ("after", "spy", {"spaces": "#who"})], "#after"), registry=registry)
    assert trace.answer is None and calls == []
    assert trace.abstained.step == "who" and trace.abstained.op == "resolve"
    assert len(trace.abstained.candidates) == count >= 2
    assert [r.id for r in trace.results] == ["who"] and trace.results[0].ok is False


def test_type_error_stops_before_any_step_runs(factory):
    calls = []
    registry = REGISTRY.copy()
    registry.register(Operator("spy", (), "Number", lambda: calls.append(1) or 1.0))
    bad = plan("bad", [("ok", "spy", {}), ("bad", "route", {"world": W, "start": "#ok", "end": "#ok"})], "#bad")
    trace = run_plan(factory, bad, registry=registry)
    assert calls == [] and trace.results == ()
    assert trace.abstained.step == "bad" and "Number" in trace.abstained.reason


def test_failed_postcondition_abstains_naming_step_and_check(factory):
    registry = REGISTRY.copy()
    registry.register(Operator("liar", (), "Number", lambda: -5.0, post=(("is non-negative", lambda value, args: value >= 0),)))
    trace = run_plan(factory, plan("liar", [("x", "liar", {}), ("y", "add", {"left": "#x", "right": 1})], "#y"), registry=registry)
    assert trace.abstained.step == "x" and "is non-negative" in trace.abstained.reason
    assert trace.results[0].ok is False and len(trace.results) == 1


def test_bottom_value_abstains(factory):
    registry = REGISTRY.copy()
    registry.register(Operator("void", (), "Number", lambda: BOTTOM))
    trace = run_plan(factory, plan("void", [("v", "void", {})], "#v"), registry=registry)
    assert trace.abstained.step == "v" and trace.answer is None


def test_evacuation_operators_run_the_exact_solver_and_can_be_swapped(factory):
    fire = by_name(factory, "Quality lab 0.21")
    steps = [("spec", "scenario", {"spec": {"hazards": [{"spaces": [fire]}]}}),
             ("g1", "apply_hazards", {"world": W, "spec": "#spec"}),
             ("occ", "occupants", {"world": "#g1", "spec": "#spec"}),
             ("evac", "evacuate", {"world": "#g1", "occupants": "#occ", "spec": "#spec"})]
    trace = run_plan(factory, plan("fire", steps, "#evac"))
    assert [r.id for r in trace.results] == ["spec", "g1", "occ", "evac"] and trace.abstained is None
    assert trace.results[1].value.closed == {fire}
    assert trace.answer.total == trace.results[2].value.total and trace.answer.T_s > 0
    again = run_plan(factory, plan("fire", steps, "#evac"))
    assert again.answer == trace.answer  # deterministic

    swapped = REGISTRY.copy()
    swapped.register(replace(swapped.get("evacuate"), fn=lambda world, occupants, spec: {"T_s": 10}), replace=True)
    assert run_plan(factory, plan("fire", steps, "#evac"), registry=swapped).answer == {"T_s": 10}


def test_unknown_hazard_space_abstains_at_apply_hazards(factory):
    steps = [("spec", "scenario", {"spec": {"hazards": [{"spaces": ["not-a-space"]}]}}),
             ("g1", "apply_hazards", {"world": W, "spec": "#spec"})]
    trace = run_plan(factory, plan("fire", steps, "#g1"))
    assert trace.abstained.step == "g1" and "not-a-space" in trace.abstained.reason


def test_on_step_streams_every_result_in_order_with_summary_and_timing(factory):
    seen = []
    trace = run_plan(factory, plan("stream", [
        ("a", "resolve", {"world": W, "text": "Quality lab 0.21"}),
        ("b", "area", {"world": W, "spaces": "#a"}),
    ], "#b"), on_step=seen.append)
    assert [r.id for r in seen] == ["a", "b"] == [r.id for r in trace.results]
    assert all(r.ms >= 0 and r.summary and "\n" not in r.summary for r in seen)
    assert seen[1].summary == "25.6 m2" and seen[1].checks == ("area is positive",)


def test_same_plan_twice_gives_identical_traces(campus):
    steps = lift_contrast_steps("Corridor 0.01", "Floor 2", "Lift 1")
    first = run_plan(campus, plan("twice", steps, "#cmp"))
    second = run_plan(CAMPUS_DIR, plan("twice", steps, "#cmp"))
    assert first.abstained is None and first == second
    assert first.answer.relation == "equal"  # a redundant lift: closing one loses nothing


def test_run_plan_accepts_a_directory_and_a_json_string(house):
    text = '{"question":"q","steps":[{"id":"e","op":"exits","args":{"world":"#world"}}],"answer":"#e"}'
    assert run_plan(HOUSE_DIR, text).answer == run_plan(house, text).answer == ("resplan-14509-F0-S001",)


def test_area_equals_core_geometry(factory):
    space = by_name(factory, "Quality lab 0.21")
    trace = run_plan(factory, plan("area", [("a", "area", {"world": W, "spaces": space})], "#a"))
    assert trace.answer == round(geometry.area(factory, space), 2)


def test_exits_shrink_when_an_entrance_or_its_space_is_closed(factory):
    entrances = sorted(o["id"] for o in factory.openings.values() if "outside" in o["space_ids"])
    space_of = {o: next(s for s in factory.openings[o]["space_ids"] if s != "outside") for o in entrances}

    def exits_after_closing(element):
        trace = run_plan(factory, plan("exits", [("g1", "close", {"world": W, "element": element}),
                                                 ("e", "exits", {"world": "#g1"})], "#e"))
        assert trace.abstained is None
        return trace.answer

    everything = run_plan(factory, plan("exits", [("e", "exits", {"world": W})], "#e")).answer
    assert len(everything) == 4
    assert exits_after_closing(entrances[0]) == tuple(s for s in everything if s != space_of[entrances[0]])
    assert exits_after_closing(space_of[entrances[1]]) == tuple(s for s in everything if s != space_of[entrances[1]])


def test_a_hazard_that_starts_later_does_not_close_anything_at_time_zero(factory):
    lab = by_name(factory, "Quality lab 0.21")
    later = {"hazards": [{"spaces": [lab], "start_s": 60}]}
    now = {"hazards": [{"spaces": [lab], "start_s": 0}]}
    closed = lambda spec: run_plan(factory, plan("fire", [
        ("spec", "scenario", {"spec": spec}), ("g1", "apply_hazards", {"world": W, "spec": "#spec"})], "#g1")).answer.closed
    assert closed(later) == frozenset() and closed(now) == {lab}


def test_type_resolution_and_listing_equal_the_data(factory):
    trace = run_plan(factory, plan("offices", [
        ("t", "resolve_type", {"world": W, "text": "offices"}),
        ("all", "spaces_of_type", {"world": W, "room_type": "#t"}),
        ("n", "count", {"items": "#all"}),
    ], "#n"))
    assert trace.results[0].value == "office" and trace.answer == 29
    assert trace.results[1].value == tuple(sorted(s["id"] for s in factory.spaces.values() if s["room_type"] == "office"))


def test_reopen_returns_a_third_world_with_the_element_open_again(factory):
    trace = run_plan(factory, plan("reopen", [
        ("el", "resolve_element", {"world": W, "text": "Office lift"}),
        ("g1", "close", {"world": W, "element": "#el"}),
        ("g2", "reopen", {"world": "#g1", "element": "#el"}),
    ], "#g2"))
    assert (trace.results[1].value.label, trace.answer.label) == ("G1", "G2") and trace.answer.closed == frozenset()
    never_closed = run_plan(factory, plan("reopen", [("el", "resolve_element", {"world": W, "text": "Office lift"}),
                                                     ("g1", "reopen", {"world": W, "element": "#el"})], "#g1"))
    assert never_closed.abstained.step == "g1" and "not closed" in never_closed.abstained.reason


def test_ambiguous_connector_name_offers_the_connectors_as_candidates(campus):
    trace = run_plan(campus, plan("lift", [("el", "resolve_element", {"world": W, "text": "lift"})], "#el"))
    assert trace.abstained.step == "el"
    candidates = {c["id"] for c in trace.abstained.candidates}
    assert candidates <= set(campus.connectors) and {c["id"] for c in campus.connectors.values() if c["kind"] == "lift"} <= candidates


def test_a_none_value_is_a_bottom_not_an_answer(factory):
    registry = REGISTRY.copy()
    registry.register(Operator("nothing", (), "Number", lambda: None))
    trace = run_plan(factory, plan("none", [("n", "nothing", {})], "#n"), registry=registry)
    assert trace.abstained.step == "n"


def test_a_summary_that_raises_abstains_instead_of_crashing(factory):
    class Broken:
        def summary(self):
            raise RuntimeError("boom")

    registry = REGISTRY.copy()
    registry.register(Operator("broken", (), "Number", Broken))
    trace = run_plan(factory, plan("broken", [("b", "broken", {})], "#b"), registry=registry)
    assert trace.abstained.step == "b" and "boom" in trace.abstained.reason


def test_non_positive_width_abstains(factory):
    start = by_name(factory, "Hall access 0.19")
    trace = run_plan(factory, plan("w", [("r", "reach", {"world": W, "start": start, "min_width_m": -5})], "#r"))
    assert trace.abstained.step == "r" and "min_width_m" in trace.abstained.reason


def test_apply_hazards_postcondition_and_reopen_postcondition_are_real(factory):
    lab = by_name(factory, "Quality lab 0.21")
    registry = REGISTRY.copy()
    good = registry.get("apply_hazards")
    registry.register(replace(good, fn=lambda world, spec: world.derive(change="did nothing")), replace=True)
    trace = run_plan(factory, plan("fire", [("spec", "scenario", {"spec": {"hazards": [{"spaces": [lab]}]}}),
                                            ("g1", "apply_hazards", {"world": W, "spec": "#spec"})], "#g1"), registry=registry)
    assert trace.abstained.step == "g1" and "hazard" in trace.abstained.reason


def test_area_counts_a_repeated_id_once(factory):
    lab = by_name(factory, "Quality lab 0.21")
    trace = run_plan(factory, plan("a", [("a", "area", {"world": W, "spaces": [lab, lab]})], "#a"))
    assert trace.answer == 25.6
