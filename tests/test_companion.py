"""Phone companion protocol: pairing, authorisation, validation, rate limits, revocation, reconnect.

The Hub is driven directly with fake sockets and a fake clock; a short end-to-end section goes through
FastAPI's WebSocket test client."""

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server import companion as C


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Peer:
    """A fake WebSocket: records what the hub sends, numbers its own messages."""

    def __init__(self, hub: C.Hub, role: str | None = None) -> None:
        self.hub, self.role, self.seq = hub, role, 0
        self.inbox: list[dict] = []
        self.closed: list[tuple[int, str]] = []
        self.conn = C.Conn(self.inbox.append, lambda code, reason: self.closed.append((code, reason)), hub.clock(), client=f"c-{id(self)}")

    def raw(self, text: str | bytes) -> None:
        self.hub.receive(self.conn, text)

    def hello(self, session: str, token: str, role: str | None = None, **extra) -> None:
        self.raw(json.dumps({"v": 1, "t": "hello", "role": role or self.role, "session": session, "token": token, **extra}))

    def send(self, kind: str, **fields) -> None:
        self.seq += 1
        self.raw(json.dumps({"v": 1, "t": kind, "seq": self.seq, **fields}))

    def types(self) -> list[str]:
        return [m["t"] for m in self.inbox if "t" in m]

    def last(self, kind: str) -> dict:
        return next(m for m in reversed(self.inbox) if m.get("t") == kind)

    def errors(self) -> list[str]:
        return [m["code"] for m in self.inbox if m.get("t") == "error"]


STEP = {"text": "Walk 20 metres along the corridor to the stairs.", "short": "Corridor", "icon": "straight", "metres": 20}


@pytest.mark.parametrize('building_id', ['', '../secret', 'bad/id', '<script>', 'x'*101, 42, None])
def test_building_reference_rejects_non_identifiers(building_id):
    hub, _, made, laptop = start()
    phone = pair_phone(hub, made, laptop)
    laptop.send('route_state', status='idle', building_id=building_id)
    assert laptop.errors()
    assert 'route_state' not in phone.types()


def test_building_reference_is_relayed_without_needing_a_route():
    hub, _, made, laptop = start()
    phone = pair_phone(hub, made, laptop)
    laptop.send('route_state', status='idle', building_id='sample-building_1')
    assert phone.last('route_state')['building_id'] == 'sample-building_1'


def start(clock: Clock | None = None, settings: C.Settings | None = None):
    clock = clock or Clock()
    hub = C.Hub(settings, clock)
    made = hub.create_session("laptop-ip")
    laptop = Peer(hub, "laptop")
    laptop.hello(made["session"], made["laptop_token"])
    return hub, clock, made, laptop


def pair_phone(hub: C.Hub, made: dict, laptop: Peer, approve: bool = True, client: str = "phone-ip") -> Peer:
    paired = hub.pair(hub.new_code(made["session"], made["laptop_token"])["code"], client)
    phone = Peer(hub, "phone")
    phone.hello(made["session"], paired["phone_secret"])
    if approve:
        laptop.send("approve", request_id=paired["request_id"])
    phone.paired = paired  # type: ignore[attr-defined]
    return phone


def test_full_pairing_flow_requires_the_laptop_to_confirm():
    hub, _, made, laptop = start()
    assert laptop.last("hello_ok")["approved"] and laptop.last("hello_ok")["pending"] == []
    paired = hub.pair(made["code"], "phone-ip")
    request = laptop.last("pair_request")
    assert request["request_id"] == paired["request_id"] and request["verify"] == paired["verify"] and 10 <= paired["verify"] <= 99
    phone = Peer(hub, "phone")
    phone.hello(made["session"], paired["phone_secret"])
    assert phone.last("hello_ok")["approved"] is False and phone.last("pending")["verify"] == paired["verify"]
    phone.send("heading", dyaw=5, mode="touch")                  # not confirmed yet: nothing reaches the laptop
    phone.send("step", action="next")
    assert "not_approved" in phone.errors() and "heading" not in laptop.types() and "step" not in laptop.types()
    laptop.send("route_state", status="guiding", route_id="r1", step_index=0, step_count=3, instruction=STEP)
    assert "route_state" not in phone.types()                    # and nothing is revealed to it either
    laptop.send("approve", request_id=paired["request_id"])
    assert "approved" in phone.types() and phone.last("route_state")["replay"] is True
    assert phone.last("route_state")["seq"] == 1                  # replayed snapshots carry the laptop's own sequence number
    assert laptop.last("peer") == {"v": 1, "t": "peer", "role": "phone", "online": True}
    phone.seq = 0
    phone.send("heading", dyaw=12.5, dpitch=-3, mode="touch")
    phone.send("step", action="next")
    phone.send("recenter")
    relayed = [m for m in laptop.inbox if m.get("t") in ("heading", "step", "recenter")]
    assert [m["t"] for m in relayed] == ["heading", "step", "recenter"]
    assert relayed[0]["dyaw"] == 12.5 and relayed[0]["dpitch"] == -3 and relayed[1]["action"] == "next"
    laptop.send("route_state", status="guiding", route_id="r1", step_index=1, step_count=3, instruction=STEP, next=STEP, heading_deg=-90)
    state = phone.last("route_state")
    assert state["step_index"] == 1 and state["heading_deg"] == 270 and state["instruction"]["metres"] == 20


def test_codes_are_single_use_short_lived_and_rate_limited():
    clock = Clock()
    hub, _, made, laptop = start(clock)
    hub.pair(made["code"], "a")
    with pytest.raises(C.Denied) as used:
        hub.pair(made["code"], "a")                               # single use
    assert used.value.status == 400
    code = hub.new_code(made["session"], made["laptop_token"])["code"]
    clock.advance(121)
    with pytest.raises(C.Denied):
        hub.pair(code, "a")                                       # expired
    fresh = hub.new_code(made["session"], made["laptop_token"])["code"]
    assert fresh != code
    # repeated wrong guesses lock one client out, even for the right code, but not another client
    for guess in range(C.Settings().max_code_failures):
        with pytest.raises(C.Denied):
            hub.pair(f"{guess:06d}" if f"{guess:06d}" != fresh else "999999", "guesser")
    with pytest.raises(C.Denied) as locked:
        hub.pair(fresh, "guesser")
    assert locked.value.status == 429
    assert hub.pair(fresh, "someone-else")["session"] == made["session"]
    clock.advance(31)
    hub.new_code(made["session"], made["laptop_token"])           # lockout is temporary
    assert hub.pair(hub.sessions[made["session"]].code, "guesser")["request_id"]


def test_a_session_id_or_another_sessions_secret_controls_nothing():
    hub, _, made, laptop = start()
    other = hub.create_session("x")
    phone = pair_phone(hub, made, laptop)
    intruder = Peer(hub, "laptop")
    intruder.hello(made["session"], "guess")
    assert intruder.errors() == ["auth_failed"] and intruder.closed[0][0] == C.CLOSE_AUTH
    intruder = Peer(hub, "laptop")
    intruder.hello(made["session"], other["laptop_token"])         # a valid token of a different session
    assert intruder.closed
    intruder = Peer(hub, "phone")
    intruder.hello(other["session"], phone.paired["phone_secret"])  # a valid phone secret for the wrong session
    assert intruder.closed
    intruder = Peer(hub, "laptop")
    intruder.hello(made["session"], phone.paired["phone_secret"])   # a phone secret cannot act as the laptop
    assert intruder.closed
    for peer in (Peer(hub), Peer(hub)):
        peer.raw(json.dumps({"v": 1, "t": "heading", "seq": 1, "dyaw": 1, "mode": "touch"}))   # no hello first
        assert peer.closed
    assert "heading" not in laptop.types()
    with pytest.raises(C.Denied):
        hub.revoke(made["session"], "wrong")
    with pytest.raises(C.Denied):
        hub.new_code(made["session"], phone.paired["phone_secret"])


def test_roles_are_enforced():
    hub, _, made, laptop = start()
    phone = pair_phone(hub, made, laptop)
    phone.send("route_state", status="idle")
    phone.send("approve", request_id="x")
    phone.send("revoke")
    laptop.send("heading", dyaw=1, mode="touch")
    laptop.send("step", action="next")
    assert phone.errors() == ["bad_message"] and "route_state" not in laptop.types()
    assert hub.sessions[made["session"]].phone is not None       # nothing above changed the session


@pytest.mark.parametrize("payload", [
    "not json", "[]", '{"t": 5}', '{"v": 1}', '{"v": 1, "t": "heading", "seq": NaN, "dyaw": 1, "mode": "touch"}',
    '{"v": 1, "t": "heading", "seq": 1, "dyaw": NaN, "mode": "touch"}', '{"v": 1, "t": "heading", "seq": 1, "dyaw": Infinity, "mode": "touch"}',
    '{"v": 1, "t": "heading", "seq": 1, "dyaw": "5", "mode": "touch"}', '{"v": 1, "t": "heading", "seq": 1, "dyaw": true, "mode": "touch"}',
    '{"v": 1, "t": "heading", "seq": 1, "dyaw": 500, "mode": "touch"}', '{"v": 1, "t": "heading", "seq": 1, "dyaw": 1, "mode": "psychic"}',
    '{"v": 1, "t": "heading", "seq": 0, "dyaw": 1, "mode": "touch"}', '{"v": 1, "t": "heading", "seq": true, "dyaw": 1, "mode": "touch"}',
    '{"v": 1, "t": "heading", "seq": 1.5, "dyaw": 1, "mode": "touch"}', '{"v": 1, "t": "heading", "dyaw": 1, "mode": "touch"}',
    '{"v": 1, "t": "step", "seq": 1, "action": "teleport"}', '{"v": 1, "t": "nonsense", "seq": 1}',
])
def test_malformed_messages_are_rejected_and_never_relayed(payload):
    hub, _, made, laptop = start()
    phone = pair_phone(hub, made, laptop)
    before = len(laptop.inbox)
    phone.raw(payload)
    assert phone.errors() == ["bad_message"]
    assert len(laptop.inbox) == before and not phone.closed
    phone.send("step", action="next")                              # the connection still works afterwards
    assert laptop.last("step")["action"] == "next"


def test_route_state_validation_rejects_bad_state():
    hub, _, made, laptop = start()
    phone = pair_phone(hub, made, laptop)
    bad = [
        {"status": "flying"}, {"status": "guiding", "step_index": 0, "step_count": 0, "instruction": STEP},
        {"status": "guiding", "step_index": 3, "step_count": 3, "instruction": STEP},
        {"status": "guiding", "step_index": 0, "step_count": 3, "instruction": {**STEP, "icon": "rocket"}},
        {"status": "guiding", "step_index": 0, "step_count": 3, "instruction": {**STEP, "text": "x" * 500}},
        {"status": "guiding", "step_index": 0, "step_count": 3, "instruction": {**STEP, "metres": -4}},
        {"status": "guiding", "step_index": 0, "step_count": 3},
        {"status": "idle", "route_id": "r" * 100},
    ]
    for fields in bad:
        laptop.send("route_state", **fields)
    assert laptop.errors().count("bad_message") >= 1                    # notices are throttled to one per second
    assert hub.sessions[made["session"]].state is None and "route_state" not in phone.types()
    assert hub.sessions[made["session"]].last_seq["laptop"] == 1       # only the approval counted; rejected messages did not


def test_stale_and_repeated_sequence_numbers_are_ignored():
    clock = Clock()
    hub, _, made, laptop = start(clock)
    phone = pair_phone(hub, made, laptop)
    phone.send("heading", dyaw=1, mode="touch")                    # seq 1
    phone.send("heading", dyaw=2, mode="touch")                    # seq 2
    phone.seq = 1
    phone.send("heading", dyaw=99, mode="touch")                   # stale: seq 2 again
    assert phone.errors() == ["stale_seq"]
    clock.advance(2)
    phone.seq = 0
    phone.send("step", action="back")                              # seq 1: replayed old number
    assert phone.errors() == ["stale_seq", "stale_seq"]
    assert [m["dyaw"] for m in laptop.inbox if m.get("t") == "heading"] == [1, 2] and "step" not in laptop.types()
    phone.seq = 2
    phone.send("step", action="back")                              # seq 3 is fresh
    assert laptop.last("step")["action"] == "back"


def test_oversized_and_wrong_version_frames_close_the_socket():
    hub, _, made, laptop = start()
    phone = pair_phone(hub, made, laptop)
    phone.raw("x" * 5000)
    assert phone.closed[0][1] == "too_large"
    other = Peer(hub, "phone")
    other.raw(json.dumps({"v": 2, "t": "hello"}))
    assert other.closed[0][0] == C.CLOSE_VERSION and other.errors() == ["unsupported_version"]


def test_a_flood_of_malformed_frames_disconnects():
    clock = Clock()
    hub, _, made, laptop = start(clock)
    phone = pair_phone(hub, made, laptop)
    for _ in range(C.Settings().max_malformed + 2):
        phone.raw("garbage")
    assert phone.closed and phone.closed[0][0] == C.CLOSE_POLICY
    assert not laptop.closed and hub.sessions[made["session"]].conns.get("laptop") is laptop.conn


def test_heading_rate_is_limited_then_the_flood_is_cut_off():
    clock = Clock()
    hub, _, made, laptop = start(clock)
    phone = pair_phone(hub, made, laptop)
    for _ in range(60):                                            # 60 frames in one instant: the burst passes, the rest drops
        phone.send("heading", dyaw=1, mode="gyro")
    delivered = len([m for m in laptop.inbox if m.get("t") == "heading"])
    assert delivered == C.Settings().heading_burst
    assert phone.errors() == ["rate_limited"]                      # one notice, not one per dropped frame
    clock.advance(1)
    phone.send("heading", dyaw=1, mode="gyro")
    assert len([m for m in laptop.inbox if m.get("t") == "heading"]) == delivered + 1
    for _ in range(C.Settings().too_fast_drops + 100):
        phone.send("heading", dyaw=1, mode="gyro")
    assert phone.closed and phone.closed[-1][0] == C.CLOSE_TOO_FAST
    assert not laptop.closed                                      # the desktop session is unaffected


def test_revoke_ends_everything_and_old_tokens_stop_working():
    hub, _, made, laptop = start()
    phone = pair_phone(hub, made, laptop)
    laptop.send("revoke")
    assert phone.closed[0][0] == C.CLOSE_REVOKED and laptop.closed[0][0] == C.CLOSE_REVOKED
    assert phone.last("bye")["reason"] == "revoked" and made["session"] not in hub.sessions
    again = Peer(hub, "phone")
    again.hello(made["session"], phone.paired["phone_secret"])
    assert again.errors() == ["auth_failed"]
    with pytest.raises(C.Denied):
        hub.pair(made["code"], "x")


def test_sessions_expire_by_age_and_by_silence():
    clock = Clock()
    hub, _, made, laptop = start(clock)
    phone = pair_phone(hub, made, laptop)
    clock.advance(C.Settings().idle_ttl_s - 5)
    phone.send("recenter")                                          # activity keeps it alive
    clock.advance(C.Settings().idle_ttl_s - 5)
    phone.send("recenter")
    assert made["session"] in hub.sessions
    clock.advance(C.Settings().idle_ttl_s + 5)
    hub.gc()
    assert made["session"] not in hub.sessions and phone.last("bye")["reason"] == "idle"
    hub2, clock2, made2, laptop2 = start()
    for _ in range(5):
        clock2.advance(C.Settings().idle_ttl_s - 60)
        laptop2.send("ping")
    hub2.gc()
    assert made2["session"] not in hub2.sessions and laptop2.last("bye")["reason"] == "expired"


def test_phone_disconnect_leaves_the_laptop_usable_and_reconnect_resumes():
    hub, _, made, laptop = start()
    laptop.send("route_state", status="guiding", route_id="r", step_index=2, step_count=4, instruction=STEP)
    phone = pair_phone(hub, made, laptop)
    phone.send("heading", dyaw=3, mode="touch")
    phone.send("step", action="next")
    hub.disconnect(phone.conn)
    assert laptop.last("peer")["online"] is False and not laptop.closed
    laptop.send("route_state", status="guiding", route_id="r", step_index=3, step_count=4, instruction=STEP)   # still works
    laptop.send("ping")
    assert laptop.last("pong")
    back = Peer(hub, "phone")
    back.hello(made["session"], phone.paired["phone_secret"])
    resumed = back.last("hello_ok")
    assert resumed["approved"] and resumed["last_seq"] == 2 and resumed["peer_online"]
    assert back.last("route_state")["step_index"] == 3 and back.last("route_state")["replay"]
    back.seq = resumed["last_seq"]                                  # a reloaded page continues after the last accepted number
    back.send("step", action="repeat")
    assert laptop.last("step")["action"] == "repeat" and laptop.last("peer")["online"] is True
    fresh = Peer(hub, "phone")                                      # a page that did NOT resume numbering is ignored, not trusted
    fresh.hello(made["session"], phone.paired["phone_secret"])
    fresh.send("step", action="next")
    assert fresh.errors() == ["stale_seq"] and back.last("bye")["reason"] == "replaced"


def test_laptop_reconnect_gets_pending_requests_and_replaces_the_old_socket():
    hub, _, made, laptop = start()
    paired = hub.pair(made["code"], "p")
    hub.disconnect(laptop.conn)
    again = Peer(hub, "laptop")
    again.hello(made["session"], made["laptop_token"])
    assert [r["request_id"] for r in again.last("hello_ok")["pending"]] == [paired["request_id"]]
    third = Peer(hub, "laptop")
    third.hello(made["session"], made["laptop_token"])
    assert again.last("bye")["reason"] == "replaced" and again.closed[0][0] == C.CLOSE_REPLACED


def test_a_second_phone_must_be_confirmed_and_replaces_the_first_only_then():
    hub, _, made, laptop = start()
    first = pair_phone(hub, made, laptop)
    first.send("recenter")
    code = hub.new_code(made["session"], made["laptop_token"])["code"]
    second_paired = hub.pair(code, "p2")
    second = Peer(hub, "phone")
    second.hello(made["session"], second_paired["phone_secret"])
    assert not first.closed                                         # connecting alone does not kick the working phone
    first.send("step", action="next")
    second.send("step", action="back")
    assert [m["action"] for m in laptop.inbox if m.get("t") == "step"] == ["next"]
    laptop.send("approve", request_id=second_paired["request_id"])
    assert first.closed[0][0] == C.CLOSE_REPLACED and first.last("bye")["reason"] == "replaced"
    second.seq = second.last("approved")["last_seq"]                  # numbering is per role: a new phone continues after the last accepted number
    second.send("step", action="back")
    assert laptop.last("step")["action"] == "back"
    stale = Peer(hub, "phone")
    stale.hello(made["session"], first.paired["phone_secret"])        # the replaced phone's secret is dead
    assert stale.errors() == ["auth_failed"]


def test_deny_and_unanswered_requests():
    clock = Clock()
    hub, _, made, laptop = start(clock)
    paired = hub.pair(made["code"], "p")
    phone = Peer(hub, "phone")
    phone.hello(made["session"], paired["phone_secret"])
    laptop.send("deny", request_id=paired["request_id"])
    assert phone.last("bye")["reason"] == "denied" and phone.closed
    code = hub.new_code(made["session"], made["laptop_token"])["code"]
    waiting_paired = hub.pair(code, "p")
    waiting = Peer(hub, "phone")
    waiting.hello(made["session"], waiting_paired["phone_secret"])
    clock.advance(C.Settings().request_ttl_s + 1)
    hub.gc()
    assert waiting.last("bye")["reason"] == "request_expired"
    late = Peer(hub, "phone")
    late.hello(made["session"], waiting_paired["phone_secret"])
    assert late.errors() == ["auth_failed"]
    laptop.send("approve", request_id=waiting_paired["request_id"])
    assert "bad_message" in laptop.errors()


def test_secrets_never_reach_the_logs(caplog):
    caplog.set_level(logging.DEBUG)
    hub, _, made, laptop = start()
    code = made["code"]
    phone = pair_phone(hub, made, laptop)
    phone.send("heading", dyaw=1, mode="touch")
    with pytest.raises(C.Denied):
        hub.pair("000000", "x")
    laptop.send("revoke")
    text = caplog.text
    for secret in (made["laptop_token"], phone.paired["phone_secret"], code, made["session"]):
        assert secret not in text
    assert "session" in text                                           # but the lifecycle is logged (by a short prefix only)


def test_session_creation_is_capped():
    hub = C.Hub(C.Settings(max_creates_per_min=3, max_sessions=4), Clock())
    for _ in range(3):
        hub.create_session("same")
    with pytest.raises(C.Denied) as many:
        hub.create_session("same")
    assert many.value.status == 429
    hub.create_session("other")
    with pytest.raises(C.Denied) as busy:
        hub.create_session("third")
    assert busy.value.status == 503


# ---------- through FastAPI ----------

@pytest.fixture()
def client():
    app = FastAPI()
    router = C.create_companion_router()
    app.include_router(router)
    return TestClient(app), router.hub


def frame(kind: str, seq: int | None = None, **fields) -> dict:
    return {"v": 1, "t": kind, **({"seq": seq} if seq is not None else {}), **fields}


def test_end_to_end_over_websockets(client):
    http, hub = client
    made = http.post("/companion/sessions").json()
    assert set(made) >= {"session", "laptop_token", "code"} and len(made["code"]) == 6
    with http.websocket_connect("/companion/ws") as laptop:
        laptop.send_json(frame("hello", role="laptop", session=made["session"], token=made["laptop_token"]))
        assert laptop.receive_json()["t"] == "hello_ok"
        paired = http.post("/companion/pair", json={"code": made["code"]}).json()
        request = laptop.receive_json()
        assert request["t"] == "pair_request" and request["verify"] == paired["verify"]
        with http.websocket_connect("/companion/ws") as phone:
            phone.send_json(frame("hello", role="phone", session=made["session"], token=paired["phone_secret"]))
            assert phone.receive_json()["t"] == "hello_ok" and phone.receive_json() == {"v": 1, "t": "pending", "verify": paired["verify"]}
            laptop.send_json(frame("approve", 1, request_id=paired["request_id"]))
            assert phone.receive_json()["t"] == "approved" and laptop.receive_json()["t"] == "peer"
            laptop.send_json(frame("route_state", 2, status="guiding", route_id="r", step_index=0, step_count=2, instruction=STEP))
            assert phone.receive_json()["instruction"]["short"] == "Corridor"
            phone.send_json(frame("heading", 1, dyaw=7.5, mode="touch"))
            assert laptop.receive_json()["dyaw"] == 7.5
            phone.send_json(frame("step", 2, action="next"))
            assert laptop.receive_json()["action"] == "next"
        laptop.send_json(frame("ping", 3))                              # phone socket closed: laptop keeps working
        messages = [laptop.receive_json(), laptop.receive_json()]
        assert {m["t"] for m in messages} == {"peer", "pong"}
    assert http.delete(f"/companion/sessions/{made['session']}", headers={"Authorization": f"Bearer {made['laptop_token']}"}).json() == {"ok": True}
    assert http.post("/companion/pair", json={"code": made["code"]}).status_code == 400


def test_rest_authorisation_and_websocket_origin(client):
    http, hub = client
    made = http.post("/companion/sessions").json()
    url = f"/companion/sessions/{made['session']}"
    assert http.post(f"{url}/code").status_code == 401
    assert http.post(f"{url}/code", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert http.delete(url, headers={"Authorization": "Bearer nope"}).status_code == 401
    fresh = http.post(f"{url}/code", headers={"Authorization": f"Bearer {made['laptop_token']}"}).json()
    assert fresh["code"] != made["code"] and http.post("/companion/pair", json={"code": made["code"]}).status_code == 400
    assert http.post("/companion/pair", json={}).status_code == 422
    with pytest.raises(WebSocketDisconnect) as refused:
        with http.websocket_connect("/companion/ws", headers={"origin": "http://evil.example"}):
            pass
    assert refused.value.code == C.CLOSE_ORIGIN
    with http.websocket_connect("/companion/ws", headers={"origin": "http://testserver"}) as ok:
        ok.send_json(frame("hello", role="laptop", session=made["session"], token="wrong"))
        assert ok.receive_json()["code"] == "auth_failed"
    info = http.get("/companion/info").json()
    assert info["v"] == 1 and info["secure_context"] is False and "HTTPS or localhost" in info["sensor_note"]
    assert info["websocket"] is C.websocket_available() and isinstance(info["lan_addresses"], list)


def test_origin_helper():
    assert C.origin_ok({"host": "192.168.1.5:8000", "origin": "http://192.168.1.5:8000"})
    assert C.origin_ok({"host": "x"})                                   # no Origin: not a browser
    assert not C.origin_ok({"host": "192.168.1.5:8000", "origin": "https://evil.example"})
