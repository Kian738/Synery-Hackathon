"""Findings tell the stakeholder what is wrong and what would help, from real traces on two kinds of building."""
import pytest

from floorwise.core.model import Building
from floorwise.paths import DATA
from floorwise.reason import run_plan
from floorwise.reason.findings import AUDIENCES, assess
from floorwise.reason.templates import instantiate


def trace_for(name: str, room_name: str):
    building = Building.load(DATA / "dev" / name)
    fire = next(s["id"] for s in building.spaces.values() if s["name"] == room_name)
    return building, fire, run_plan(building, instantiate("evacuation", spec={"hazards": [{"spaces": [fire]}], "responders": {"auto": True}}))


@pytest.fixture(scope="module")
def campus():
    return trace_for("proc-campus-dev-000", "Canteen 0.28")


@pytest.fixture(scope="module")
def factory():
    return trace_for("proc-factory-dev-003", "Meeting room 0.24")


def test_a_verified_door_fix_is_suggested_with_its_numbers(campus):
    _, _, trace = campus
    fix = trace.answer.fixes[0]
    suggested = [f for f in assess(trace) if f.suggestion]
    assert suggested and f"{fix.T_before_s} s -> {fix.T_after_s} s" in suggested[0].suggestion
    assert fix.verified


def test_people_with_no_time_to_leave_are_reported_as_a_finding(campus):
    building, fire, _ = campus
    trace = run_plan(building, instantiate("evacuation", spec={"hazards": [{"spaces": [fire], "escape_s": 0}], "responders": {"auto": True}}))
    stranded = sum(trace.results[4].value.stranded.values())
    titles = " ".join(f.title for f in assess(trace))
    assert stranded > 0 and (f"{stranded} people" in titles)


def test_people_in_the_hazard_room_leave_within_the_default_window(campus):
    _, _, trace = campus
    assert not trace.results[4].value.stranded


def test_when_no_door_helps_the_report_says_so_and_names_the_step(factory):
    _, _, trace = factory
    findings = assess(trace)
    assert any(f.severity == "info" and "best" in f.evidence and "no door or widening" in f.detail for f in findings)
    assert not any(f.suggestion for f in findings)


def test_audiences_change_the_wording_not_the_numbers(campus):
    _, _, trace = campus
    texts = {a: assess(trace, a) for a in AUDIENCES}
    assert any("not a compliance check" in f.title for f in texts["regulator"])
    assert not any("not a compliance check" in f.title for f in texts["occupant"])
    fix_times = {a: [f.evidence for f in fs if f.suggestion] for a, fs in texts.items()}
    assert len({tuple(map(tuple, v)) for v in fix_times.values()}) == 1


def test_every_finding_points_at_a_step_of_the_trace(campus, factory):
    for _, _, trace in (campus, factory):
        ids = {r.id for r in trace.results} | ({trace.abstained.step} if trace.abstained else set())
        for finding in assess(trace):
            assert finding.evidence and set(finding.evidence) <= ids


def test_a_plan_that_stopped_early_reports_where():
    building = Building.load(DATA / "dev" / "proc-campus-dev-000")
    trace = run_plan(building, instantiate("evacuation", spec={"hazards": [{"spaces": ["no-such-space"]}]}))
    (finding,) = assess(trace)
    assert finding.severity == "blocker" and finding.evidence == (trace.abstained.step,)


def test_unknown_audience_is_refused(campus):
    with pytest.raises(ValueError):
        assess(campus[2], "journalist")


def test_no_route_findings_are_each_proven_by_a_re_solve():
    from dataclasses import replace

    from floorwise.core.graph import Constraints
    from floorwise.core.routing import plan_route

    campus = Building.load(DATA / "dev" / "proc-campus-dev-000")
    by_name = {s["name"]: s["id"] for s in campus.spaces.values()}
    start, end = by_name["Main lobby"], by_name["Print room 0.16"]
    trolley = Constraints(step_free=True, min_width_m=1.1)
    from floorwise.reason.findings import why_no_route

    findings = why_no_route(campus, start, end, trolley)
    assert findings[0].severity == "improve" and findings[0].suggestion and "0.9 m to 1.1 m" in findings[0].suggestion
    assert plan_route(campus, [start, end], replace(trolley, min_width_m=None)).length_m > 0  # the relaxed route is real


def test_a_closed_element_that_cuts_the_way_is_named_with_the_route_it_restores():
    from floorwise.core.graph import Constraints
    from floorwise.reason.findings import why_no_route

    factory = Building.load(DATA / "dev" / "proc-factory-dev-003")
    ids = {s["name"]: s["id"] for s in factory.spaces.values()}
    lift = next(c["id"] for c in factory.connectors.values() if c["kind"] == "lift")
    constraints = Constraints(step_free=True, closed=frozenset({lift}))
    upper = next(s["id"] for s in factory.spaces.values() if factory.level(s["floor_id"]) == 1 and s["type"] == "room")
    start = ids["Kitchen 0.28"]
    findings = why_no_route(factory, start, upper, constraints)
    assert any(f.suggestion and lift in f.suggestion for f in findings)
