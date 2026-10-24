"""The scenario API: every step comes back with its result, findings follow the audience, one question at a time."""
import pytest
from fastapi.testclient import TestClient

from floorwise.core.model import Building
from floorwise.paths import DATA
from server.app import app

BUILDING = "proc-campus-dev-000"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def session(client):
    return client.post("/api/sessions", json={"building_id": BUILDING}).json()["session_id"]


@pytest.fixture(scope="module")
def fire_room():
    building = Building.load(DATA / "dev" / BUILDING)
    return next(s["id"] for s in building.spaces.values() if s["name"] == "Canteen 0.28")


def run(client, session, fire_room, audience="safety_officer"):
    spec = {"hazards": [{"spaces": [fire_room]}], "responders": {"auto": True}}
    return client.post(f"/api/sessions/{session}/scenario", json={"template": "evacuation", "params": {"spec": spec}, "audience": audience})


def test_the_evacuation_scenario_returns_every_checked_step(client, session, fire_room):
    body = run(client, session, fire_room).json()
    assert [s["id"] for s in body["steps"]] == ["spec", "g1", "occ", "exits", "evac", "bn", "resp", "cand", "best"]
    assert all(s["ok"] for s in body["steps"]) and body["abstained"] is None
    assert body["evacuation"]["T_s"] > 0 and body["evacuation"]["schedule"]
    assert any(f["suggestion"] for f in body["findings"])


def test_the_same_request_gives_the_same_answer(client, session, fire_room):
    first, second = run(client, session, fire_room).json(), run(client, session, fire_room).json()
    strip = lambda b: {k: v for k, v in b.items() if k != "steps"}  # step timings differ, results must not
    assert strip(first) == strip(second)


def test_the_audience_changes_the_wording_not_the_numbers(client, session, fire_room):
    regulator = run(client, session, fire_room, "regulator").json()
    occupant = run(client, session, fire_room, "occupant").json()
    assert regulator["evacuation"] == occupant["evacuation"]
    assert any("not a compliance check" in f["title"] for f in regulator["findings"])
    assert not any("not a compliance check" in f["title"] for f in occupant["findings"])


def test_an_unknown_hazard_stops_at_a_named_step(client, session):
    body = client.post(f"/api/sessions/{session}/scenario",
                       json={"template": "evacuation", "params": {"spec": {"hazards": [{"spaces": ["nope"]}]}}}).json()
    assert body["abstained"]["step"] == "g1" and body["findings"][0]["severity"] == "blocker"


def test_bad_requests_are_refused_with_a_reason(client, session):
    assert client.post(f"/api/sessions/{session}/scenario", json={"template": "nope"}).status_code == 422
    assert client.post(f"/api/sessions/{session}/scenario", json={"audience": "journalist"}).status_code == 422


def test_it_asks_one_question_for_what_is_missing_and_none_when_complete(client, session, fire_room):
    asked = client.post(f"/api/sessions/{session}/scenario/ask", json={"spec": {}}).json()["question"]
    assert asked and asked["field"] and 2 <= len(asked["options"]) <= 4
    complete = {"hazards": [{"spaces": [fire_room]}], "occupants": {"source": "seats"}, "objective": "min_evacuation_time",
                "responders": {"auto": True}}
    assert client.post(f"/api/sessions/{session}/scenario/ask", json={"spec": complete}).json()["question"] is None


def test_claude_can_plan_a_scenario_by_room_name_and_gets_no_replay_table():
    from floorwise.agent.session import Session
    from floorwise.agent.tools import make_tools
    import json
    session = Session.for_building(Building.load(DATA / "dev" / BUILDING))
    tool = next(t for t in make_tools(session, allow_edits=False) if t.name == "plan_scenario")
    reply = json.loads(tool.fn(hazard_rooms=["Canteen 0.28"]))
    assert reply["abstained"] is None and reply["evacuation"]["T_s"] > 0 and "schedule" not in reply["evacuation"]
    assert any(f["suggestion"] for f in reply["findings"])


def test_people_in_the_hazard_room_get_a_stated_window_to_leave_and_zero_means_none(client, session, fire_room):
    def run_with(escape):
        hazard = {"spaces": [fire_room], **({} if escape is None else {"escape_s": escape})}
        spec = {"hazards": [hazard], "responders": {"auto": True}}
        return client.post(f"/api/sessions/{session}/scenario", json={"template": "evacuation", "params": {"spec": spec}}).json()["evacuation"]

    default, none = run_with(None), run_with(0)
    assert none["stranded"] and not default["stranded"]
    assert default["evacuated"] == default["total"] == none["total"]
    assert none["evacuated"] + sum(none["stranded"].values()) == none["total"]


def test_findings_name_doors_by_place_and_show_the_capacity_arithmetic(client, session, fire_room):
    findings = run(client, session, fire_room).json()["findings"]
    risk = next(f for f in findings if f["severity"] == "risk")
    assert BUILDING not in risk["detail"] and "people per second" in risk["detail"]
    assert all(BUILDING not in f["title"] for f in findings)


def test_n_minus_one_check_is_asked_for_and_never_makes_the_worst_case_worse(client, session, fire_room):
    spec = {"hazards": [{"spaces": [fire_room]}]}
    body = client.post(f"/api/sessions/{session}/scenario/robust", json={"params": {"spec": spec}}).json()
    worst = lambda rows: max((-r["evacuated"], r["T_s"]) for r in rows)
    assert body["verified"] and len(body["before"]) >= 3 and worst(body["after"]) <= worst(body["before"])
    assert all(BUILDING not in (r["lost_exit"] or "") for r in body["before"])
