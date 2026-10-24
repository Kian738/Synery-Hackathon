import pytest
from reason_support import CAMPUS_DIR, FACTORY_DIR, HOUSE_DIR, people

from floorwise.core.graph import RouteGraph
from floorwise.core.model import Building
from floorwise.core.routing import plan_route
from floorwise.reason import run_plan
from floorwise.reason.operators import REGISTRY
from floorwise.reason.plan import check_plan
from floorwise.reason.templates import TemplateError, instantiate, template_names


def space_id(building: Building, name: str) -> str:
    (found,) = [s["id"] for s in building.spaces.values() if s["name"] == name]
    return found


def test_the_three_missions_are_data_and_all_type_check_without_a_building():
    assert template_names() == ("delivery", "evacuation", "maintenance_closure")
    plans = [
        instantiate("evacuation", spec={"hazards": [{"spaces": ["x"]}]}),
        instantiate("delivery", item="coffee machine", start="Hall", destination="Lab"),
        instantiate("maintenance_closure", element="Lift", start="Hall"),
    ]
    for plan in plans:
        assert check_plan(plan, REGISTRY) is plan
        assert plan.steps and plan.answer.startswith("#")


def test_template_parameters_are_validated_by_name():
    with pytest.raises(TemplateError, match="destination"):
        instantiate("delivery", item="coffee machine", start="Hall")
    with pytest.raises(TemplateError, match="colour"):
        instantiate("delivery", item="a", start="b", destination="c", colour="red")
    with pytest.raises(TemplateError, match="nothing"):
        instantiate("nothing")


def test_evacuation_template_runs_every_step_with_the_exact_solver():
    campus = Building.load(CAMPUS_DIR)
    seats = {}
    for asset in campus.assets.values():
        if asset["type"] in ("chair", "office_chair"):
            seats[asset["space_id"]] = seats.get(asset["space_id"], 0) + 1
    fire = max(sorted(seats), key=seats.get)
    spec = {"hazards": [{"spaces": [fire]}], "responders": {"auto": True}}
    trace = run_plan(campus, instantiate("evacuation", spec=spec))
    assert trace.abstained is None
    assert [r.id for r in trace.results] == ["spec", "g1", "occ", "exits", "evac", "bn", "resp", "cand", "best"]
    assert trace.results[1].value.closed == {fire}
    assert trace.answer.T_after_s < trace.answer.T_before_s and all(f.verified for f in trace.answer.fixes)


def test_evacuation_template_abstains_naming_the_step_when_no_door_helps():
    factory = Building.load(FACTORY_DIR)
    fire = space_id(factory, "Meeting room 0.24")
    trace = run_plan(factory, instantiate("evacuation", spec={"hazards": [{"spaces": [fire]}], "responders": {"auto": True}}))
    assert trace.abstained.step == "best" and "no door or widening" in trace.abstained.reason


def test_delivery_equals_direct_core_calls_on_two_kinds_of_building():
    factory, campus = Building.load(FACTORY_DIR), Building.load(CAMPUS_DIR)
    for building, item, start_name, destination_name, floor_width in [
        (factory, "coffee machine", "Hall access 0.19", "Quality lab 0.21", None),
        (campus, "coffee machine", "Corridor 0.01", None, 0.9),
    ]:
        start = space_id(building, start_name)
        destination = space_id(building, destination_name) if destination_name else next(
            s["id"] for s in building.spaces.values() if s["type"] == "room" and building.level(s["floor_id"]) == 2)
        params = {"item": item, "start": start, "destination": destination, "min_width_m": floor_width}
        trace = run_plan(building, instantiate("delivery", **params))
        constraints = people(step_free=False, min_width_m=floor_width)
        holders = {a["space_id"] for a in building.assets.values() if a["type"] == "coffee_machine"}
        distances = RouteGraph(building, constraints, keep=frozenset({start})).distances_from(start)
        pickup = min((distances[h], h) for h in holders if h in distances)[1]
        expected = round(plan_route(building, [start, pickup], constraints).length_m
                         + plan_route(building, [pickup, destination], constraints).length_m, 2)
        assert trace.abstained is None
        assert trace.answer == expected > 0


def test_delivery_abstains_at_the_step_that_fails_when_no_holder_is_reachable_with_wide_doors():
    factory = Building.load(FACTORY_DIR)
    params = {"item": "coffee machine", "start": space_id(factory, "Hall access 0.19"), "destination": space_id(factory, "Quality lab 0.21")}
    assert run_plan(factory, instantiate("delivery", min_width_m=0.9, **params)).abstained is None
    wide = run_plan(factory, instantiate("delivery", min_width_m=1.0, **params))
    assert wide.answer is None and wide.abstained.step == "pick"
    assert [r.id for r in wide.results if r.ok] == ["item", "s", "d", "hold"]


def test_delivery_replans_in_the_closed_world_when_an_element_is_blocked():
    factory = Building.load(FACTORY_DIR)
    upstairs = next(s["id"] for s in factory.spaces.values() if s["type"] == "room" and factory.level(s["floor_id"]) == 1
                    and not any(a["space_id"] == s["id"] for a in factory.assets.values() if a["type"] == "coffee_machine"))
    params = {"item": "coffee machine", "start": space_id(factory, "Hall access 0.19"), "destination": upstairs}
    free = run_plan(factory, instantiate("delivery", **params))
    assert free.abstained is None and free.answer > 0
    stairs_blocked = run_plan(factory, instantiate("delivery", blocked="Office staircase", **params))
    step_free_without_lift = run_plan(factory, instantiate("delivery", blocked="Office lift", step_free=True, **params))
    assert stairs_blocked.abstained is None and stairs_blocked.answer >= free.answer
    assert [r.op for r in stairs_blocked.results][:2] == ["resolve_element", "close"]
    assert step_free_without_lift.answer is None and step_free_without_lift.abstained.step == "leg2"


def test_maintenance_closure_tells_who_loses_access_on_two_kinds_of_building():
    factory, house, campus = (Building.load(p) for p in (FACTORY_DIR, HOUSE_DIR, CAMPUS_DIR))
    lift = run_plan(factory, instantiate("maintenance_closure", element="Office lift", start="Hall access 0.19", step_free=True))
    assert lift.abstained is None and lift.answer == 29 and len(lift.results[-2].value) == 29
    redundant = run_plan(campus, instantiate("maintenance_closure", element="Lift 1", start="Corridor 0.01", step_free=True))
    assert redundant.abstained is None and redundant.answer == 0
    living, bathroom = space_id(house, "Living room 0.01"), space_id(house, "Bathroom 0.04")
    door = next(o["id"] for o in house.openings.values() if set(o["space_ids"]) == {living, bathroom})
    lost = run_plan(house, instantiate("maintenance_closure", element=door, start="Living room 0.01"))
    assert lost.answer == 1 and lost.results[-2].value == (bathroom,)


def test_maintenance_closure_with_a_route_pair_reports_the_detour_or_abstains():
    campus = Building.load(CAMPUS_DIR)
    start = space_id(campus, "Corridor 0.01")
    target = next(s["id"] for s in campus.spaces.values() if s["type"] == "room" and campus.level(s["floor_id"]) == 2)
    trace = run_plan(campus, instantiate("maintenance_closure", element="Lift 1", start=start, from_space=start, to_space=target, step_free=True))
    assert trace.abstained is None
    assert trace.answer.right >= trace.answer.left > 0


def test_instantiated_plans_do_not_alias_the_callers_dict():
    spec = {"hazards": [{"spaces": ["x"]}]}
    plan = instantiate("evacuation", spec=spec)
    spec["hazards"][0]["spaces"].append("y")
    assert plan.steps[0].args["spec"] == {"hazards": [{"spaces": ["x"]}]}
