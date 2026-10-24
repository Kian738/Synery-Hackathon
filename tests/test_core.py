"""Fast core checks (no API). The full regression gates are the eval suites (eval.routes, eval.solver)."""

import math

import pytest

from floorwise.agent.parse_rules import parse_rules
from floorwise.agent.session import Session
from floorwise.agent.tools import make_tools
from floorwise.core import resolve as R
from floorwise.core.graph import Constraints
from floorwise.core.model import Building
from floorwise.core.routing import plan_route
from floorwise.paths import DATA

FACTORY = DATA / "dev" / "proc-factory-dev-003"
CAMPUS = DATA / "dev" / "proc-campus-dev-000"


@pytest.fixture(scope="module")
def factory() -> Building:
    return Building.load(FACTORY)


@pytest.fixture(scope="module")
def campus() -> Building:
    return Building.load(CAMPUS)


@pytest.mark.parametrize("text,level", [
    ("ground floor", 0), ("the floor 2", 2), ("Floor 3", 3), ("basement 1", -1), ("2nd floor", 2),
    ("second floor", 2), ("level -2", -2), ("EG", 0),
])
def test_floor_words(text, level):
    assert R.floor_level_from_text(text) == level


def test_route_properties(campus):
    rooms = [s["id"] for s in campus.spaces.values() if s["type"] == "room"]
    a, b, c = rooms[0], rooms[len(rooms) // 2], rooms[-1]
    normal = plan_route(campus, [a, c]).length_m
    step_free = plan_route(campus, [a, c], Constraints(step_free=True)).length_m
    assert step_free >= normal - 1e-6
    tour = plan_route(campus, [a, b, c]).length_m
    assert tour >= normal - 0.02  # triangle inequality (legs are rounded)
    ax, ay = campus.polygons[a].representative_point().coords[0]
    cx, cy = campus.polygons[c].representative_point().coords[0]
    if campus.spaces[a]["floor_id"] == campus.spaces[c]["floor_id"]:
        assert normal >= math.dist((ax, ay), (cx, cy)) - 1e-6


def test_avoid_types_changes_or_keeps_route(factory):
    session = Session.for_building(factory)
    lobby = next(s["id"] for s in factory.spaces.values() if s["room_type"] == "lobby")
    target = next(s["id"] for s in factory.spaces.values() if s["room_type"] == "quality_lab")
    free = session.route(lobby, target)
    avoided = session.route(lobby, target, avoid=["production zone"])
    assert "error" in avoided or avoided["length_m"] >= free["length_m"]


def test_session_operations(factory):
    session = Session.for_building(factory)
    assert session.overview()["floors"]
    assert session.search("office", "floor 1")["total"] > 0
    room = next(s for s in factory.spaces.values() if s["room_type"] == "office")
    info = session.room_info(room["id"])
    assert info["area_m2"] > 0
    lift = next(c for c in factory.connectors.values() if c["kind"] == "lift")
    closed = session.set_closed(lift["name"], True)
    assert closed["id"] == lift["id"]
    lobby = next(s["id"] for s in factory.spaces.values() if s["room_type"] == "lobby")
    upper = next(f["id"] for f in factory.floors.values() if f["level"] == 1)
    assert session.reachable(lobby, factory.floors[upper]["name"], step_free=True)["reachable_rooms"] == 0
    assert session.nearest(lobby, "toilet")["nearest"]
    assert session.rank_rooms("ground floor", "office")["count"] > 0
    # An office pair that shares a wall gets a door preview and then the edit.
    offices = [s["id"] for s in factory.spaces_on(room["floor_id"]) if s["room_type"] == "office"]
    from floorwise.core.geometry import wall_neighbours

    pair = next((o, n) for o in offices for n, _ in wall_neighbours(factory, o) if n in offices)
    preview = session.door_preview(*pair)
    assert "door" in preview
    assert "added" in session.add_door(*pair)
    assert session.events


def test_tools_build(factory):
    tools = make_tools(Session.for_building(factory))
    names = {t.name for t in tools}
    assert {"find_route", "add_door", "set_closed", "search"} <= names


def test_rule_parser_rejects_unknown_wording():
    assert parse_rules("How do I get to the canteen?") is None
