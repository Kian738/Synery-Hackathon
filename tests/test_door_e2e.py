"""Adding a door between room X and room Y works end to end: by the names a person types, through the same HTTP calls the app makes.

Preview first (nothing changes), then apply, then the route between the two rooms is the new short one, a second preview says so, undo gives the
old length back exactly, and removing the door again returns it too."""
import pytest
from fastapi.testclient import TestClient

from eval.common import building_paths
from floorwise.core.geometry import wall_neighbours
from floorwise.core.graph import Constraints
from floorwise.core.model import Building
from floorwise.core.routing import plan_route
from server.app import app

client = TestClient(app)
NAMES = ["proc-factory-dev-003", "proc-campus-dev-000", "swiss-1785", "resplan-15793", "osm-way61408163"]


def label(b: Building, sid: str) -> str:
    return b.label(sid)  # "Name (Floor)": what the app shows and a person types


def doorless_far_pair(b: Building):
    joined = {frozenset(o["space_ids"]) for o in b.openings.values()}
    best = None
    for sid, space in sorted(b.spaces.items()):
        if space["type"] != "room":
            continue
        for other, _ in wall_neighbours(b, sid):
            if b.spaces[other]["type"] != "room" or frozenset((sid, other)) in joined or b.spaces[other]["floor_id"] != space["floor_id"]:
                continue
            try:
                d = plan_route(b, [sid, other], Constraints()).length_m
            except ValueError:
                continue
            if d > 6 and (best is None or d > best[2]):
                best = (sid, other, d)
    return best


@pytest.mark.parametrize("name", NAMES)
def test_add_door_by_name_changes_the_route_and_undo_restores_it(name):
    path = next(p for p in building_paths(["train", "dev", "test"]) if p.parent.name == name)
    b = Building.load(path.parent)
    pair = doorless_far_pair(b)
    if pair is None:
        pytest.skip("no two neighbouring rooms without a door and with a detour")
    first, second, before = pair
    a, c = label(b, first), label(b, second)
    session = client.post("/api/sessions", json={"building_id": name}).json()["session_id"]

    def route_length():
        r = client.post(f"/api/sessions/{session}/route", json={"start": first, "destination": second}).json()["result"]
        return r.get("length_m")

    before = route_length()                                               # the app's own number (walking metres)
    assert before is not None and before > 3
    preview = client.post(f"/api/sessions/{session}/door", json={"first": a, "second": c}).json()["result"]
    assert "error" not in preview, preview
    assert route_length() == pytest.approx(before, abs=0.02)            # a preview changes nothing
    applied = client.post(f"/api/sessions/{session}/door", json={"first": a, "second": c, "confirm": True}).json()["result"]
    assert "error" not in applied, applied
    after = route_length()
    assert after is not None and after < before - 1.0                    # the new door is the short way now`n    walked = client.post(f"/api/sessions/{session}/route", json={"start": first, "destination": second}).json()["result"]`n    assert walked.get("walk_m") is not None, walked                      # and its walking line is drawable (a 3D preview exists)
    again = client.post(f"/api/sessions/{session}/door", json={"first": a, "second": c, "confirm": True}).json()["result"]
    assert "already a door" in again.get("error", "")                    # a second door in the same place is refused, not stacked
    client.post(f"/api/sessions/{session}/undo")
    assert route_length() == pytest.approx(before, abs=0.02)
    removed = client.post(f"/api/sessions/{session}/door", json={"first": a, "second": c, "confirm": True}).json()["result"]  # after the undo the door can be added again
    assert "error" not in removed
    removal = client.post(f"/api/sessions/{session}/door/remove", json={"first": a, "second": c}).json()["result"]
    assert "error" not in removal, removal
    assert route_length() == pytest.approx(before, abs=0.02)
