"""Level 4 EDIT: every edit the agent can make changes the building's answers, and undo restores them exactly."""

import json

import pytest

from floorwise.agent.session import Session
from floorwise.agent.tools import make_tools
from floorwise.core.geometry import wall_neighbours
from floorwise.core.graph import Constraints
from floorwise.core.model import Building
from floorwise.core.routing import plan_route
from floorwise.paths import DATA

FACTORY = DATA / "dev" / "proc-factory-dev-003"


@pytest.fixture()
def session() -> Session:
    return Session.for_building(Building.load(FACTORY))


def length(session: Session, a: str, b: str) -> float:
    return plan_route(session.building, [a, b], Constraints()).length_m


def doorless_pair(session: Session):
    """Two rooms that share a wall, have no door between them, and a detour between them."""
    b = session.building
    joined = {frozenset(o["space_ids"]) for o in b.openings.values()}
    for sid, space in b.spaces.items():
        if space["type"] != "room":
            continue
        for other, _ in wall_neighbours(b, sid):
            if b.spaces[other]["type"] == "room" and frozenset((sid, other)) not in joined:
                try:
                    if length(session, sid, other) > 6:
                        return sid, other
                except ValueError:
                    continue
    pytest.skip("no suitable doorless pair")


def test_add_door_shortens_the_route_and_undo_restores_it(session):
    a, c = doorless_pair(session)
    before = length(session, a, c)
    preview = session.door_preview(a, c)
    assert length(session, a, c) == before, "a preview must not change anything"
    assert preview["impact"] is not None
    session.add_door(a, c)
    after = length(session, a, c)
    assert after < before
    assert session.undo()["undone"] == "add_door"
    assert length(session, a, c) == before
    assert session.edits == []


def test_remove_door_walls_it_up_and_undo_brings_it_back(session):
    b = session.building
    door = next(o for o in b.openings.values() if o["kind"] == "door" and len(set(o["space_ids"])) == 2 and all(s in b.spaces for s in o["space_ids"]))
    first, second = door["space_ids"]
    before = length(session, first, second)
    result = session.remove_door(first, second)
    assert result["removed"] == door["id"]
    assert door["id"] not in b.openings and all(o["id"] != door["id"] for o in b.data["openings"])
    try:
        assert length(session, first, second) >= before
    except ValueError:
        pass  # walling it up may cut the pair off entirely, which is also a valid consequence
    session.undo()
    assert door["id"] in b.openings
    assert length(session, first, second) == before


def test_entrances_cannot_be_removed(session):
    entrance = next(o for o in session.building.openings.values() if o["kind"] == "entrance")
    assert "error" in session.remove_door(entrance["id"])


def test_move_add_remove_item_and_undo(session):
    b = session.building
    asset = next(iter(b.assets.values()))
    target = next(s["id"] for s in b.spaces.values() if s["type"] == "room" and s["id"] != asset["space_id"])
    origin = asset["space_id"]
    session.move_asset(asset["id"], target)
    assert b.assets[asset["id"]]["space_id"] == target
    session.undo()
    assert b.assets[asset["id"]]["space_id"] == origin

    added = session.add_asset("Test printer", "3d printer", target)
    assert added["id"] in b.assets and any(a["id"] == added["id"] for a in b.data["assets"])
    assert any(hit["id"] == added["id"] for hit in session.search("Test printer")["assets"])
    session.undo()
    assert added["id"] not in b.assets

    count = len(b.assets)
    session.remove_asset(asset["id"])
    assert len(b.assets) == count - 1
    session.undo()
    assert asset["id"] in b.assets and len(b.assets) == count


def test_widen_door_is_undoable(session):
    door = next(o for o in session.building.openings.values() if o["kind"] == "door")
    width = door["width_m"]
    session.widen_door(door["id"], width + 0.5)
    assert door["width_m"] == width + 0.5
    session.undo()
    assert door["width_m"] == width


def test_undo_with_nothing_to_undo_says_so(session):
    assert "error" in session.undo()


def test_edits_never_leak_into_another_session():
    original = Building.load(FACTORY)
    one, two = Session.for_building(original), Session.for_building(original)
    a, c = doorless_pair(one)
    one.add_door(a, c)
    assert len(one.building.openings) == len(two.building.openings) + 1
    assert len(original.openings) == len(two.building.openings)


def test_agent_tools_cover_every_edit_and_return_json(session):
    tools = {t.name: t for t in make_tools(session)}
    assert {"add_door", "remove_door", "move_item", "add_item", "remove_item", "undo_edit", "set_closed"} <= set(tools)
    room = next(s["id"] for s in session.building.spaces.values() if s["type"] == "room")
    out = json.loads(tools["add_item"].fn(name="Lathe", kind="cnc mill", room=room))
    assert out["added"] == "Lathe"
    assert json.loads(tools["undo_edit"].fn())["undone"] == "add_asset"


def test_benchmark_mode_exposes_no_edit_tools(session):
    assert "remove_door" not in {t.name for t in make_tools(session, allow_edits=False)}


def test_http_edit_flow_changes_the_route_and_undo_restores_it():
    from fastapi.testclient import TestClient

    from server.app import app

    client = TestClient(app)
    session_id = client.post("/api/sessions", json={"building_id": "proc-factory-dev-003"}).json()["session_id"]
    local = Session.for_building(Building.load(FACTORY))
    a, c = doorless_pair(local)

    def route_length():
        return client.post(f"/api/sessions/{session_id}/route", json={"start": a, "destination": c}).json()["result"]["length_m"]

    before = route_length()
    assert client.post(f"/api/sessions/{session_id}/door", json={"first": a, "second": c}).status_code == 200  # preview
    assert route_length() == before
    assert "added" in client.post(f"/api/sessions/{session_id}/door", json={"first": a, "second": c, "confirm": True}).json()["result"]
    assert route_length() < before
    assert client.post(f"/api/sessions/{session_id}/undo").json()["result"]["undone"] == "add_door"
    assert route_length() == before
