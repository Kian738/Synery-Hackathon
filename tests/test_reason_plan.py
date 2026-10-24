import json

import pytest
from reason_support import FACTORY_DIR, plan

from floorwise.core.model import Building
from floorwise.reason.operators import REGISTRY
from floorwise.reason.plan import PlanError, check_plan, parse_plan


def check(steps, answer):
    return check_plan(parse_plan(plan("q", steps, answer)), REGISTRY)


def test_valid_plan_parses_from_dict_and_json_text_identically():
    steps = [("a", "resolve", {"world": "#world", "text": "Lab"}), ("b", "area", {"world": "#world", "spaces": "#a"})]
    as_dict = plan("How big is the lab?", steps, "#b")
    from_dict, from_text = parse_plan(as_dict), parse_plan(json.dumps(as_dict))
    assert from_dict == from_text
    assert [s.id for s in from_dict.steps] == ["a", "b"] and from_dict.answer == "#b"
    assert check_plan(from_dict, REGISTRY) is from_dict


@pytest.mark.parametrize("raw", ["not json", "[]", {"question": "q"}, {"question": "q", "steps": [{"id": "a"}], "answer": "#a"},
                                 {"question": "q", "steps": [], "answer": "#a"}])
def test_malformed_plans_are_rejected_at_parse(raw):
    with pytest.raises(PlanError):
        parse_plan(raw)


def test_unknown_operator_names_the_step():
    with pytest.raises(PlanError) as error:
        check([("s1", "resolve", {"world": "#world", "text": "x"}), ("s2", "teleport", {})], "#s2")
    assert error.value.step == "s2" and "teleport" in str(error.value)


def test_missing_required_argument_names_step_and_argument():
    with pytest.raises(PlanError) as error:
        check([("s1", "resolve", {"world": "#world"})], "#s1")
    assert error.value.step == "s1" and "text" in str(error.value)


def test_unexpected_argument_is_an_error():
    with pytest.raises(PlanError) as error:
        check([("s1", "resolve", {"world": "#world", "text": "x", "colour": "red"})], "#s1")
    assert error.value.step == "s1" and "colour" in str(error.value)


def test_wrong_type_between_steps_names_the_consumer():
    steps = [("a", "resolve", {"world": "#world", "text": "Lab"}), ("n", "area", {"world": "#world", "spaces": "#a"}),
             ("r", "route", {"world": "#world", "start": "#n", "end": "#a"})]
    with pytest.raises(PlanError) as error:
        check(steps, "#r")
    assert error.value.step == "r"
    assert "Number" in str(error.value) and "Space" in str(error.value)


def test_wrong_literal_type_is_an_error():
    with pytest.raises(PlanError) as error:
        check([("a", "resolve", {"world": "#world", "text": 7})], "#a")
    assert error.value.step == "a" and "Text" in str(error.value)


def test_a_space_is_accepted_where_an_element_is_expected():
    steps = [("a", "resolve", {"world": "#world", "text": "Lab"}), ("w", "close", {"world": "#world", "element": "#a"})]
    assert check(steps, "#w").answer == "#w"


def test_reference_to_a_later_step_names_the_earlier_step():
    steps = [("a", "area", {"world": "#world", "spaces": "#b"}), ("b", "resolve", {"world": "#world", "text": "Lab"})]
    with pytest.raises(PlanError) as error:
        check(steps, "#a")
    assert error.value.step == "a" and "later" in str(error.value)


def test_cycle_is_an_error_naming_a_step_on_it():
    steps = [("a", "compare", {"left": "#b", "right": 1}), ("b", "compare", {"left": "#a", "right": 1})]
    with pytest.raises(PlanError) as error:
        check(steps, "#a")
    assert error.value.step in {"a", "b"} and "cycle" in str(error.value)


def test_self_reference_is_a_cycle():
    with pytest.raises(PlanError) as error:
        check([("a", "add", {"left": "#a", "right": 1})], "#a")
    assert error.value.step == "a" and "cycle" in str(error.value)


@pytest.mark.parametrize("steps,answer,step", [
    ([("a", "resolve", {"world": "#world", "text": "x"}), ("a", "resolve", {"world": "#world", "text": "y"})], "#a", "a"),
    ([("a", "area", {"world": "#world", "spaces": "#nope"})], "#a", "a"),
    ([("world", "resolve", {"world": "#world", "text": "x"})], "#world", "world"),
])
def test_duplicate_unknown_and_reserved_ids(steps, answer, step):
    with pytest.raises(PlanError) as error:
        check(steps, answer)
    assert error.value.step == step


def test_answer_must_reference_a_step():
    with pytest.raises(PlanError) as error:
        check([("a", "resolve", {"world": "#world", "text": "x"})], "#zzz")
    assert error.value.step == "answer"


def test_literal_ids_are_checked_against_the_building_before_execution():
    building = Building.load(FACTORY_DIR)
    parsed = parse_plan(plan("q", [("a", "area", {"world": "#world", "spaces": "no-such-space"})], "#a"))
    assert check_plan(parsed, REGISTRY) is parsed
    with pytest.raises(PlanError) as error:
        check_plan(parsed, REGISTRY, building=building)
    assert error.value.step == "a" and "no-such-space" in str(error.value)


def test_unhashable_literal_ids_are_a_plan_error_not_a_crash():
    building = Building.load(FACTORY_DIR)
    bad = parse_plan(plan("q", [("n", "nearest", {"world": "#world", "start": next(iter(building.spaces)), "candidates": [["y"]]})], "#n"))
    with pytest.raises(PlanError) as error:
        check_plan(bad, REGISTRY, building=building)
    assert error.value.step == "n"


def test_a_long_chain_of_later_references_is_reported_without_recursion():
    steps = [(f"s{i}", "add", {"left": f"#s{i + 1}", "right": 1}) for i in range(1500)]
    steps.append(("s1500", "add", {"left": 1, "right": 1}))
    with pytest.raises(PlanError) as error:
        check(steps, "#s0")
    assert error.value.step == "s0" and "later" in str(error.value)


def test_cycle_names_a_step_on_the_cycle_not_one_downstream_of_it():
    steps = [("a", "add", {"left": "#b", "right": 1}), ("b", "add", {"left": "#a", "right": 1}),
             ("c", "add", {"left": "#a", "right": 1})]
    with pytest.raises(PlanError) as error:
        check(steps, "#c")
    assert error.value.step in {"a", "b"}
