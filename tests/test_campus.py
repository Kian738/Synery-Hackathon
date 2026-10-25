"""Routing between buildings: three legs, joint entrance choice, constraints carry across, honest outdoor estimate."""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from floorwise.core import campus
from floorwise.core.graph import DOOR_PREFIX, Constraints
from floorwise.core.model import Building
from floorwise.paths import DATA
from server.app import app

A, B = "osm-way22744230", "osm-way10053349"
ANCHORS = {A: campus.Anchor(48.151082, 11.567701), B: campus.Anchor(48.148858, 11.568008)}


@pytest.fixture(scope="module")
def buildings():
    return {i: Building.load(next(DATA.glob(f"*/{i}"))) for i in (A, B)}


def room(building, index):
    return [s["id"] for s in building.spaces.values() if s["type"] == "room"][index]


def plan(buildings, start=5, dest=9, constraints=Constraints(), **kw):
    a, b = buildings[A], buildings[B]
    return campus.plan_campus(a, ANCHORS[A], room(a, start) if start is not None else None,
                              b, ANCHORS[B], room(b, dest) if dest is not None else None, constraints, constraints, **kw)


def test_total_is_sum_of_the_three_legs(buildings):
    p = plan(buildings)
    assert p.total_m == pytest.approx(p.first.distance_m + p.outdoor.distance_m + p.second.distance_m, abs=0.2)
    assert p.outdoor.estimated and p.first.route["length_m"] == pytest.approx(p.first.distance_m, abs=0.06)


def test_joint_choice_beats_every_other_pair(buildings):
    a, b = buildings[A], buildings[B]
    p = plan(buildings, top_k=1)
    da = campus.door_costs(a, Constraints(), room(a, 5))
    db = campus.door_costs(b, Constraints(), room(b, 9))
    ea = {e.opening_id: e for e in campus.entrances(a, ANCHORS[A])}
    eb = {e.opening_id: e for e in campus.entrances(b, ANCHORS[B])}
    best = min(da[i] + db[j] + campus.estimate_outdoor(ea[i], eb[j]).distance_m for i in da for j in db)
    assert p.total_m == pytest.approx(best, abs=0.2)


def test_building_level_route_has_no_indoor_legs(buildings):
    p = plan(buildings, None, None)
    assert p.first is None and p.second is None and p.total_m == p.outdoor.distance_m


def test_closed_entrance_is_never_used(buildings):
    first = plan(buildings)
    closed = Constraints(closed=frozenset({first.exit_a.opening_id, first.entry_b.opening_id}))
    second = plan(buildings, constraints=closed)
    assert second.exit_a.opening_id != first.exit_a.opening_id and second.entry_b.opening_id != first.entry_b.opening_id
    assert second.total_m >= first.total_m - 1e-6


def test_step_free_never_uses_a_step_entrance(buildings):
    for building in buildings.values():
        steps = {o["id"] for o in building.openings.values() if "outside" in o["space_ids"] and not o.get("step_free", True)}
        usable = campus.door_costs(building, Constraints(step_free=True), None)
        assert not steps & set(usable)


def test_no_usable_entrance_is_an_error(buildings):
    every = frozenset(o["id"] for o in buildings[B].openings.values() if "outside" in o["space_ids"])
    with pytest.raises(campus.NoCampusRoute):
        plan(buildings, constraints=Constraints(closed=every))


def test_provider_answer_replaces_the_estimate_and_is_used(buildings):
    calls = []

    def provider(first, second):
        calls.append((first.opening_id, second.opening_id))
        return campus.Outdoor(1.0, 0.1, [[0, 0], [1, 1]], [], False, "test")

    p = plan(buildings, outdoor=provider, top_k=3)
    assert 1 <= len(calls) <= 3 and not p.outdoor.estimated and p.outdoor.distance_m == 1.0


def test_geo_transform_is_metric(buildings):
    a = buildings[A]
    cx, cy = campus.frame_centre(a)
    lat0, lon0 = campus.to_geo(a, ANCHORS[A], cx, cy)
    assert (lat0, lon0) == pytest.approx((ANCHORS[A].lat, ANCHORS[A].lon))
    lat1, lon1 = campus.to_geo(a, ANCHORS[A], cx + 100, cy + 50)
    assert campus.haversine_m(lat0, lon0, lat1, lon1) == pytest.approx(111.8, rel=0.01)
    assert lat1 > lat0 and lon1 > lon0  # x east, y north


def test_indoor_leg_ends_at_the_door(buildings):
    p = plan(buildings)
    last = p.first.route["polyline"][-1]
    assert last["node"] == DOOR_PREFIX + p.exit_a.opening_id
    assert p.second.route["polyline"][0]["node"] == DOOR_PREFIX + p.entry_b.opening_id


def test_a_blocked_exit_falls_back_to_the_next_pair(buildings, monkeypatch):
    from floorwise.core.routing import NoRoute, plan_route
    first = plan(buildings)
    blocked = first.exit_a.space_id

    def picky(building, stops, constraints=Constraints(), humane=False):
        if humane and stops[-1] == blocked and building.id == A:
            raise NoRoute("blocked by furniture")
        return plan_route(building, stops, constraints, humane=humane)

    monkeypatch.setattr(campus, "plan_route", picky)
    second = plan(buildings)
    assert second.exit_a.space_id != blocked and second.first.route["preview_available"] is not False


def test_if_no_pair_can_be_drawn_the_plain_route_is_used(buildings, monkeypatch):
    from floorwise.core.routing import NoRoute, plan_route

    def never_drawn(building, stops, constraints=Constraints(), humane=False):
        if humane:
            raise NoRoute("blocked by furniture")
        return plan_route(building, stops, constraints, humane=False)

    monkeypatch.setattr(campus, "plan_route", never_drawn)
    p = plan(buildings)
    assert p.first.route["preview_available"] is False and p.first.route["steps"]
    assert p.second.route["preview_available"] is False


def test_a_room_that_is_the_entrance_room_makes_a_trivial_leg(buildings):
    a, b = buildings[A], buildings[B]
    door = campus.entrances(a, ANCHORS[A])[0]
    p = campus.plan_campus(a, ANCHORS[A], door.space_id, b, ANCHORS[B], None, Constraints(), Constraints())
    assert p.first.trivial == (p.exit_a.space_id == door.space_id)
    same = campus.plan_campus(a, ANCHORS[A], p.exit_a.space_id, b, ANCHORS[B], None, Constraints(), Constraints())
    assert same.first.trivial and same.first.distance_m >= 0


def navigator_accepts(route: dict) -> bool:
    """The same contract as web/src/lib/validation.ts isRoute: a leg that fails it would show nothing in the Navigator."""
    num = lambda v: isinstance(v, (int, float))
    guide = route.get("guide") or {}
    return (len(route.get("stops", [])) >= 2 and num(route.get("length_m")) and isinstance(route.get("constraints"), list)
            and isinstance(route.get("floors"), list) and len(route.get("polyline", [])) > 0
            and all(num(p["x"]) and num(p["y"]) and isinstance(p["floor_id"], str) for p in route["polyline"])
            and len(guide.get("steps", [])) > 0 and all(isinstance(x["text"], str) and num(x["metres"]) for x in guide["steps"])
            and isinstance(guide.get("spoken"), str))


def test_both_indoor_legs_can_be_shown_by_the_navigator_as_they_are(buildings):
    p = plan(buildings)
    assert navigator_accepts(p.first.route) and navigator_accepts(p.second.route)


def test_the_guide_ends_at_the_exit_door_and_starts_at_the_entrance(buildings):
    p = plan(buildings)
    last = p.first.route["guide"]["steps"][-1]
    assert last["kind"] == "arrive" and last["point"] == [p.exit_a.x, p.exit_a.y] and "exit" in last["text"]
    assert "arrived" not in " ".join(x["text"] for x in p.first.route["guide"]["steps"]).lower().replace("you have reached the exit", "")
    first = p.second.route["guide"]["steps"][0]
    assert first["point"] == [p.entry_b.x, p.entry_b.y] and "come in through" in first["text"]


def test_modes_change_the_outdoor_time_and_the_pair_ranking_uses_time(buildings):
    foot, bike, car = (plan(buildings, mode=m) for m in ("foot", "bike", "car"))
    assert foot.outdoor.duration_min > bike.outdoor.duration_min > car.outdoor.duration_min
    assert (foot.outdoor.mode, bike.outdoor.mode, car.outdoor.mode) == ("foot", "bike", "car")


class TestApi:
    client = TestClient(app)

    @pytest.fixture(autouse=True)
    def offline(self, monkeypatch):
        """No test touches the network: routers fail unless a test installs a fake."""
        import httpx

        from server import campus as server_campus

        def down(*args, **kwargs):
            raise httpx.ConnectError("offline")

        monkeypatch.setattr(server_campus, "_ors", down)
        monkeypatch.setattr(server_campus, "_osrm", down)
        monkeypatch.setattr(server_campus, "_cache", {})
        monkeypatch.setattr(server_campus, "_ors_refused", None)
        monkeypatch.delenv("ORS_API_KEY", raising=False)
        self.server_campus = server_campus

    def body(self, buildings, **extra):
        return {"from_building": A, "to_building": B, "from_room": room(buildings[A], 5), "to_room": room(buildings[B], 9), **extra}

    def fake(self, name):
        return lambda *args, **kwargs: campus.Outdoor(300.0, 4.0, [[11.5, 48.1], [11.6, 48.2]], [{"instruction": "Go", "distance_m": 300}], False, name, "foot")

    def test_openrouteservice_is_used_when_it_answers(self, buildings, monkeypatch):
        monkeypatch.setenv("ORS_API_KEY", "k")
        monkeypatch.setattr(self.server_campus, "_ors", self.fake("OpenRouteService (foot-walking)"))
        outdoor = self.client.post("/api/campus/route", json=self.body(buildings)).json()["legs"][1]
        assert not outdoor["estimated"] and outdoor["provider"].startswith("OpenRouteService")

    def test_refused_key_falls_back_to_osm_routing_and_says_so(self, buildings, monkeypatch):
        import httpx

        def refused(*args, **kwargs):
            request = httpx.Request("POST", "https://example.invalid")
            raise httpx.HTTPStatusError("denied", request=request, response=httpx.Response(403, request=request))

        monkeypatch.setenv("ORS_API_KEY", "k")
        monkeypatch.setattr(self.server_campus, "_ors", refused)
        monkeypatch.setattr(self.server_campus, "_osrm", self.fake("OpenStreetMap routing (foot)"))
        body = self.client.post("/api/campus/route", json=self.body(buildings)).json()
        assert body["legs"][1]["provider"].startswith("OpenStreetMap") and not body["legs"][1]["estimated"]
        assert any("refused the API key" in w for w in body["warnings"])
        assert self.server_campus._ors_refused  # and it is not asked again in this process

    def test_mode_is_passed_through(self, buildings):
        for mode in ("bike", "car"):
            leg = self.client.post("/api/campus/route", json=self.body(buildings, mode=mode)).json()["legs"][1]
            assert leg["mode"] == mode and leg["estimated"]

    def test_step_free_flag_no_longer_exists_only_the_mode_counts(self, buildings):
        body = self.client.post("/api/campus/route", json=self.body(buildings, step_free=True)).json()
        assert body["mode"] == "foot"

    def test_outdoor_steps_carry_a_map_position(self, buildings, monkeypatch):
        steps = [{"instruction": "Go", "distance_m": 300, "at": [11.5, 48.1]}]
        monkeypatch.setattr(self.server_campus, "_osrm", lambda *a, **k: campus.Outdoor(300.0, 4.0, [[11.5, 48.1], [11.6, 48.2]], steps, False, "OpenStreetMap routing (foot)", "foot"))
        leg = self.client.post("/api/campus/route", json=self.body(buildings)).json()["legs"][1]
        assert leg["steps"][0]["at"] == [11.5, 48.1]

    def test_wheelchair_mode_forces_step_free_indoors(self, buildings):
        body = self.client.post("/api/campus/route", json=self.body(buildings, mode="wheelchair")).json()
        assert body["mode"] == "wheelchair" and body["legs"][0]["door"]["step_free"] and body["legs"][2]["door"]["step_free"]

    def test_unknown_mode_is_rejected(self, buildings):
        assert self.client.post("/api/campus/route", json=self.body(buildings, mode="teleport")).status_code == 422

    def test_route_between_rooms(self, buildings):
        r = self.client.post("/api/campus/route", json={
            "from_building": A, "to_building": B,
            "from_room": room(buildings[A], 5), "to_room": room(buildings[B], 9)})
        assert r.status_code == 200
        body = r.json()
        assert [leg["kind"] for leg in body["legs"]] == ["indoor", "outdoor", "indoor"]
        assert body["legs"][1]["estimated"] and any("estimate" in w for w in body["warnings"])
        assert body["total_m"] == pytest.approx(sum(leg["distance_m"] for leg in body["legs"]), abs=0.2)

    def test_ambiguous_room_asks_back(self):
        r = self.client.post("/api/campus/route", json={"from_building": A, "to_building": B, "from_room": "zzz-no-such-room"})
        assert r.status_code == 409 and r.json()["detail"]["which"] == "from" and r.json()["detail"]["candidates"]

    def test_building_without_location_is_refused(self):
        r = self.client.post("/api/campus/route", json={"from_building": A, "to_building": "proc-campus-dev-000"})
        assert r.status_code == 422

    def test_same_building_is_refused(self):
        assert self.client.post("/api/campus/route", json={"from_building": A, "to_building": A}).status_code == 422
