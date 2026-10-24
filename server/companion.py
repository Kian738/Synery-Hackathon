"""Phone companion: short-lived, confirmed pairing and a validated relay between one laptop and one phone.

The laptop shows the building; the phone is a controller. The server holds no building data and never moves
anyone: it only relays heading deltas, step requests and instruction state between two authenticated peers.

Not mounted anywhere yet. The integrator adds one line to server/app.py:

    from server.companion import create_companion_router
    app.include_router(create_companion_router())

Protocol v1 (JSON text frames, details in docs/parallel/phone-handoff.md):

  REST    POST   /companion/sessions              laptop: create a session -> session id, laptop token, pairing code
          POST   /companion/sessions/{id}/code    laptop (Bearer token): new code, old one dies
          DELETE /companion/sessions/{id}         laptop (Bearer token): revoke everything now
          POST   /companion/pair                  phone: {"code": "123456"} -> request id, phone secret, verify number
          GET    /companion/info                  protocol version, LAN addresses, secure-context hint
  WS      /companion/ws                           first frame is hello; every later frame is {"v":1,"t":...,"seq":n,...}
          Sequence numbers are per role and strictly increasing; hello_ok (and approved, for a phone that was waiting)
          carry last_seq, and a client continues numbering after it.

Security stance: secrets travel in POST bodies and the first WebSocket frame, never in URLs, so access logs and
referrers cannot contain them. Tokens are random, stored hashed and compared in constant time. The pairing code
is single use, expires quickly and is rate limited; a phone is only ever attached after the laptop's user
confirms the verify number shown on both screens. Session ids alone grant nothing."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import importlib.util
import json
import logging
import math
import secrets
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

PROTOCOL_VERSION = 1
log = logging.getLogger("floorwise.companion")

ICONS = ("start", "straight", "left", "right", "back", "lift", "stairs", "outside", "arrive")
STATUSES = ("idle", "guiding", "arrived")
STEP_ACTIONS = ("next", "back", "repeat")
LAPTOP_TYPES = {"route_state", "approve", "deny", "new_code", "revoke", "ping"}
PHONE_TYPES = {"heading", "step", "recenter", "ping"}

# WebSocket close codes (4000-4999 are application defined).
CLOSE_POLICY = 1008
CLOSE_AUTH = 4401
CLOSE_ORIGIN = 4403
CLOSE_REPLACED = 4409
CLOSE_REVOKED = 4410
CLOSE_VERSION = 4426
CLOSE_TOO_FAST = 4429


@dataclass(frozen=True)
class Settings:
    code_ttl_s: float = 120.0           # a pairing code works once, for this long
    request_ttl_s: float = 120.0        # the laptop must confirm a phone within this long
    session_ttl_s: float = 2 * 3600.0   # hard lifetime of a session
    idle_ttl_s: float = 30 * 60.0       # no traffic from either side
    code_digits: int = 6
    max_code_failures: int = 8          # wrong or expired codes per failure window, per client key
    failure_window_s: float = 60.0
    lockout_s: float = 30.0
    max_sessions: int = 200
    max_creates_per_min: int = 10       # per client key
    max_message_bytes: int = 4096
    hello_timeout_s: float = 10.0
    heading_per_s: float = 30.0         # sustained heading messages per second (token bucket)
    heading_burst: int = 20
    too_fast_drops: int = 300           # dropped heading frames within drop_window_s before disconnecting
    drop_window_s: float = 10.0
    max_malformed: int = 12             # malformed frames within malformed_window_s before disconnecting
    malformed_window_s: float = 60.0
    max_delta_deg: float = 90.0
    max_text_chars: int = 240
    max_steps: int = 500
    max_pending: int = 3


class Denied(Exception):
    """Raised for REST callers; the message is deliberately generic."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


def _digest(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _same(secret: str, digest: bytes) -> bool:
    return hmac.compare_digest(_digest(secret), digest)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-finite number {name}")


class Bucket:
    """Token bucket: `rate` events per second sustained, `burst` at once."""

    def __init__(self, rate: float, burst: int, now: float) -> None:
        self.rate, self.burst, self.tokens, self.stamp = rate, float(burst), float(burst), now

    def take(self, now: float) -> bool:
        self.tokens = min(self.burst, self.tokens + (now - self.stamp) * self.rate)
        self.stamp = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class Window:
    """Counts events inside a sliding window."""

    def __init__(self, span: float) -> None:
        self.span = span
        self.stamps: list[float] = []

    def add(self, now: float) -> int:
        self.stamps = [t for t in self.stamps if now - t < self.span] + [now]
        return len(self.stamps)

    def count(self, now: float) -> int:
        return len([t for t in self.stamps if now - t < self.span])


@dataclass
class PhoneRequest:
    request_id: str
    secret_digest: bytes
    verify: int
    expires: float


@dataclass
class Session:
    id: str
    laptop_digest: bytes
    created: float
    last_seen: float
    code: str | None = None
    code_expires: float = 0.0
    requests: dict[str, PhoneRequest] = field(default_factory=dict)   # phones the laptop has not answered yet
    phone: PhoneRequest | None = None                                 # the confirmed phone
    last_seq: dict[str, int] = field(default_factory=lambda: {"laptop": 0, "phone": 0})
    state: dict | None = None                                         # last route_state, replayed to a phone that (re)connects
    state_seq: int = 0                                                # the laptop's sequence number of that snapshot
    revoked: bool = False
    conns: dict[str, "Conn"] = field(default_factory=dict)            # "laptop" / "phone" (the confirmed one) -> live socket
    waiting: dict[str, "Conn"] = field(default_factory=dict)          # request id -> phone socket not yet confirmed


class Conn:
    """One WebSocket as the hub sees it. `send(dict)` and `close(code, reason)` are supplied by the transport."""

    def __init__(self, send: Callable[[dict], None], close: Callable[[int, str], None], now: float = 0.0, client: str = "-") -> None:
        self.send, self._close, self.client = send, close, client
        self.role: str | None = None
        self.session: Session | None = None
        self.request: PhoneRequest | None = None   # a phone's own pairing request
        self.waiting = False                       # phone socket the laptop has not confirmed yet
        self.closed = False
        self.bucket: Bucket | None = None
        self.drops = Window(10.0)
        self.malformed = Window(60.0)
        self.last_error_at = -1e9
        self.opened = now

    def close(self, code: int, reason: str) -> None:
        if not self.closed:
            self.closed = True
            self._close(code, reason)


class Hub:
    def __init__(self, settings: Settings | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.s = settings or Settings()
        self.clock = clock
        self.sessions: dict[str, Session] = {}
        self.failures: dict[str, Window] = {}
        self.locked_until: dict[str, float] = {}
        self.creates: dict[str, Window] = {}

    # ---------- REST-level operations ----------

    def create_session(self, client: str = "-") -> dict:
        now = self.clock()
        self.gc()
        window = self.creates.setdefault(client, Window(60.0))
        if window.count(now) >= self.s.max_creates_per_min:
            raise Denied(429, "Too many sessions from this device. Wait a minute.")
        if len(self.sessions) >= self.s.max_sessions:
            raise Denied(503, "The companion service is busy.")
        window.add(now)
        sid, token = secrets.token_urlsafe(9), secrets.token_urlsafe(24)
        session = Session(id=sid, laptop_digest=_digest(token), created=now, last_seen=now)
        self.sessions[sid] = session
        code = self._issue_code(session)
        log.info("session %s created", sid[:4])
        return {"v": PROTOCOL_VERSION, "session": sid, "laptop_token": token, "code": code,
                "code_expires_in": self.s.code_ttl_s, "session_ttl": self.s.session_ttl_s}

    def _authorised(self, session_id: str, token: str) -> Session:
        self.gc()
        session = self.sessions.get(session_id)
        if session is None or session.revoked or not _same(token or "", session.laptop_digest):
            raise Denied(401, "Not authorised.")
        return session

    def new_code(self, session_id: str, token: str) -> dict:
        session = self._authorised(session_id, token)
        return {"code": self._issue_code(session), "code_expires_in": self.s.code_ttl_s}

    def _issue_code(self, session: Session) -> str:
        now = self.clock()
        active = {s.code for s in self.sessions.values() if s.code and s.code_expires > now}
        while True:
            code = "".join(str(secrets.randbelow(10)) for _ in range(self.s.code_digits))
            if code not in active:
                break
        session.code, session.code_expires = code, now + self.s.code_ttl_s
        return code

    def revoke(self, session_id: str, token: str) -> None:
        self._end(self._authorised(session_id, token), "revoked")

    def _end(self, session: Session, reason: str) -> None:
        session.revoked, session.code = True, None
        for conn in [*session.conns.values(), *session.waiting.values()]:
            conn.send({"v": PROTOCOL_VERSION, "t": "bye", "reason": reason})
            conn.close(CLOSE_REVOKED, reason)
        session.conns.clear()
        session.waiting.clear()
        self.sessions.pop(session.id, None)
        log.info("session %s ended: %s", session.id[:4], reason)

    def pair(self, code: str, client: str = "-") -> dict:
        """Phone side of pairing. Consumes the code and queues a request the laptop's user must confirm."""
        now = self.clock()
        self.gc()
        if self.locked_until.get(client, 0.0) > now:
            raise Denied(429, "Too many attempts. Wait a little and ask for a new code.")
        code = "".join(ch for ch in (code or "") if not ch.isspace())
        match = None
        for session in self.sessions.values():       # no early exit: timing does not reveal which code was close
            if session.code and session.code_expires > now and hmac.compare_digest(code.encode(), session.code.encode()):
                match = session
        if match is None or len(match.requests) >= self.s.max_pending:
            if self.failures.setdefault(client, Window(self.s.failure_window_s)).add(now) >= self.s.max_code_failures:
                self.locked_until[client] = now + self.s.lockout_s
                log.warning("pairing attempts locked for one client")
            raise Denied(400, "That code is not valid. Check it, or ask the laptop for a new one.")
        match.code = None                               # single use
        secret = secrets.token_urlsafe(24)
        request = PhoneRequest(secrets.token_urlsafe(8), _digest(secret), 10 + secrets.randbelow(90), now + self.s.request_ttl_s)
        match.requests[request.request_id] = request
        match.last_seen = now
        laptop = match.conns.get("laptop")
        if laptop:
            laptop.send(self._pair_request(request, now))
        return {"v": PROTOCOL_VERSION, "session": match.id, "request_id": request.request_id, "phone_secret": secret,
                "verify": request.verify, "expires_in": self.s.request_ttl_s}

    @staticmethod
    def _pair_request(request: PhoneRequest, now: float) -> dict:
        return {"v": PROTOCOL_VERSION, "t": "pair_request", "request_id": request.request_id, "verify": request.verify,
                "expires_in": max(0.0, round(request.expires - now, 1))}

    # ---------- WebSocket-level operations ----------

    def receive(self, conn: Conn, raw: str | bytes) -> None:
        if conn.closed:
            return
        now = self.clock()
        self.gc()
        size = len(raw) if isinstance(raw, (bytes, bytearray)) else len(raw.encode("utf-8"))
        if size > self.s.max_message_bytes:
            conn.send(self._error("too_large", "Message too large."))
            conn.close(CLOSE_POLICY, "too_large")
            return
        try:
            message = json.loads(raw, parse_constant=_reject_constant)
        except (ValueError, UnicodeDecodeError):
            return self._malformed(conn, now, "Not valid JSON.")
        if not isinstance(message, dict) or not isinstance(message.get("t"), str):
            return self._malformed(conn, now, "Messages are JSON objects with a type.")
        if message.get("v") != PROTOCOL_VERSION:
            conn.send(self._error("unsupported_version", f"Protocol version {PROTOCOL_VERSION} only."))
            conn.close(CLOSE_VERSION, "unsupported_version")
            return
        session = conn.session
        if session is None:
            return self._hello(conn, message, now)
        if session.revoked or not self._live(session, conn):
            conn.close(CLOSE_REVOKED, "revoked")
            return
        session.last_seen = now
        kind, role = message["t"], conn.role or ""
        if kind not in (LAPTOP_TYPES if role == "laptop" else PHONE_TYPES):
            return self._malformed(conn, now, "That message type is not allowed for this role.")
        if conn.waiting:
            self._error_to(conn, now, "not_approved", "Waiting for the laptop to confirm this phone.")
            return
        seq = message.get("seq")
        if not _is_int(seq) or seq < 1:
            return self._malformed(conn, now, "seq must be a positive integer.")
        if seq <= session.last_seq[role]:
            return self._error_to(conn, now, "stale_seq", "Old or repeated message ignored.")
        try:
            clean = getattr(self, f"_on_{kind}")(conn, session, message, now)
        except ValueError as problem:
            return self._malformed(conn, now, str(problem))
        if not session.revoked:
            session.last_seq[role] = seq
        if clean is not None:
            peer = session.conns.get("phone" if role == "laptop" else "laptop")
            if peer:
                peer.send({"v": PROTOCOL_VERSION, "seq": seq, **clean})

    def disconnect(self, conn: Conn) -> None:
        """Transport closed. Leaves the session intact so the laptop keeps working and either side can resume."""
        conn.closed = True
        session = conn.session
        if session is None or conn.role is None or not self._live(session, conn):
            return
        if conn.waiting:
            session.waiting.pop(conn.request.request_id, None)
            return
        del session.conns[conn.role]
        peer = session.conns.get("laptop" if conn.role == "phone" else "phone")
        if peer:
            peer.send({"v": PROTOCOL_VERSION, "t": "peer", "role": conn.role, "online": False})
        log.info("session %s: %s disconnected", session.id[:4], conn.role)

    def gc(self) -> None:
        now = self.clock()
        for session in list(self.sessions.values()):
            if now - session.created > self.s.session_ttl_s:
                self._end(session, "expired")
            elif now - session.last_seen > self.s.idle_ttl_s:
                self._end(session, "idle")
            else:
                for rid, request in list(session.requests.items()):
                    if request.expires < now:
                        del session.requests[rid]
                        waiting = session.waiting.pop(rid, None)
                        if waiting:
                            waiting.send({"v": PROTOCOL_VERSION, "t": "bye", "reason": "request_expired"})
                            waiting.close(CLOSE_POLICY, "request_expired")

    @staticmethod
    def _live(session: Session, conn: Conn) -> bool:
        if conn.waiting:
            return conn.request is not None and session.waiting.get(conn.request.request_id) is conn
        return session.conns.get(conn.role or "") is conn

    # ---------- handlers ----------

    def _hello(self, conn: Conn, message: dict, now: float) -> None:
        window = self.failures.setdefault(f"ws:{conn.client}", Window(self.s.failure_window_s))

        def fail() -> None:
            window.add(now)
            conn.send(self._error("auth_failed", "Not authorised."))
            conn.close(CLOSE_AUTH, "auth_failed")

        if message["t"] != "hello" or message.get("role") not in ("laptop", "phone") or window.count(now) > 50:
            return fail()
        session = self.sessions.get(message["session"]) if isinstance(message.get("session"), str) else None
        token = message.get("token")
        if session is None or session.revoked or not isinstance(token, str):
            return fail()
        role = message["role"]
        if role == "laptop":
            if not _same(token, session.laptop_digest):
                return fail()
        else:
            request = session.phone if session.phone and _same(token, session.phone.secret_digest) else next(
                (r for r in session.requests.values() if _same(token, r.secret_digest)), None)
            if request is None:
                return fail()
            conn.request = request
            conn.waiting = request is not session.phone
        conn.role, conn.session, conn.bucket = role, session, Bucket(self.s.heading_per_s, self.s.heading_burst, now)
        old = session.waiting.get(conn.request.request_id) if conn.waiting else session.conns.get(role)
        if old is not None:
            old.send({"v": PROTOCOL_VERSION, "t": "bye", "reason": "replaced"})
            old.close(CLOSE_REPLACED, "replaced")
        if conn.waiting:
            session.waiting[conn.request.request_id] = conn
        else:
            session.conns[role] = conn
        session.last_seen = now
        approved = not conn.waiting
        reply: dict = {"v": PROTOCOL_VERSION, "t": "hello_ok", "role": role, "session": session.id, "last_seq": session.last_seq[role],
                       "peer_online": ("phone" if role == "laptop" else "laptop") in session.conns, "approved": approved}
        if role == "laptop":
            reply["pending"] = [self._pair_request(r, now) for r in session.requests.values()]
            reply["phone_paired"] = session.phone is not None
        conn.send(reply)
        if role == "phone":
            if approved:
                self._replay(session, conn)
            else:
                conn.send({"v": PROTOCOL_VERSION, "t": "pending", "verify": conn.request.verify})
        peer = session.conns.get("laptop" if role == "phone" else "phone")
        if peer and approved:
            peer.send({"v": PROTOCOL_VERSION, "t": "peer", "role": role, "online": True})
        log.info("session %s: %s connected", session.id[:4], role)

    @staticmethod
    def _replay(session: Session, conn: Conn) -> None:
        if session.state is not None:
            conn.send({"v": PROTOCOL_VERSION, "replay": True, "seq": session.state_seq, **session.state})

    def _on_ping(self, conn: Conn, session: Session, message: dict, now: float) -> None:
        conn.send({"v": PROTOCOL_VERSION, "t": "pong"})

    def _on_approve(self, conn: Conn, session: Session, message: dict, now: float) -> None:
        request = self._request(session, message)
        previous = session.conns.get("phone")
        session.phone = request
        session.requests.pop(request.request_id, None)
        incoming = session.waiting.pop(request.request_id, None)
        if previous is not None and previous is not incoming:
            session.conns.pop("phone", None)
            previous.send({"v": PROTOCOL_VERSION, "t": "bye", "reason": "replaced"})
            previous.close(CLOSE_REPLACED, "replaced")
        if incoming is not None:
            incoming.waiting = False
            session.conns["phone"] = incoming
            incoming.send({"v": PROTOCOL_VERSION, "t": "approved", "last_seq": session.last_seq["phone"]})
            self._replay(session, incoming)
            conn.send({"v": PROTOCOL_VERSION, "t": "peer", "role": "phone", "online": True})

    def _on_deny(self, conn: Conn, session: Session, message: dict, now: float) -> None:
        request = self._request(session, message)
        session.requests.pop(request.request_id, None)
        waiting = session.waiting.pop(request.request_id, None)
        if waiting is not None:
            waiting.send({"v": PROTOCOL_VERSION, "t": "bye", "reason": "denied"})
            waiting.close(CLOSE_POLICY, "denied")

    def _request(self, session: Session, message: dict) -> PhoneRequest:
        rid = message.get("request_id")
        request = session.requests.get(rid) if isinstance(rid, str) else None
        if request is None or request.expires < self.clock():
            raise ValueError("Unknown or expired pairing request.")
        return request

    def _on_new_code(self, conn: Conn, session: Session, message: dict, now: float) -> None:
        conn.send({"v": PROTOCOL_VERSION, "t": "code", "code": self._issue_code(session), "code_expires_in": self.s.code_ttl_s})

    def _on_revoke(self, conn: Conn, session: Session, message: dict, now: float) -> None:
        self._end(session, "revoked")

    def _on_route_state(self, conn: Conn, session: Session, message: dict, now: float) -> dict:
        status, route_id = message.get("status"), message.get("route_id")
        if status not in STATUSES:
            raise ValueError("Unknown status.")
        if route_id is not None and not (isinstance(route_id, str) and len(route_id) <= 64):
            raise ValueError("route_id must be a short string.")
        clean: dict = {"t": "route_state", "status": status, "route_id": route_id}
        if status != "idle":
            count, index = message.get("step_count"), message.get("step_index")
            if not (_is_int(count) and 1 <= count <= self.s.max_steps):
                raise ValueError("step_count out of range.")
            if not (_is_int(index) and 0 <= index < count):
                raise ValueError("step_index out of range.")
            clean.update(step_count=count, step_index=index, instruction=self._instruction(message.get("instruction")))
            if message.get("next") is not None:
                clean["next"] = self._instruction(message["next"])
        if "heading_deg" in message:
            if not _finite(message["heading_deg"]):
                raise ValueError("heading_deg must be a number.")
            clean["heading_deg"] = round(float(message["heading_deg"]) % 360, 1)
        session.state, session.state_seq = clean, message["seq"]
        return clean

    def _instruction(self, value: Any) -> dict:
        if not isinstance(value, dict):
            raise ValueError("instruction must be an object.")
        text, short, icon = value.get("text"), value.get("short", ""), value.get("icon")
        if not (isinstance(text, str) and 0 < len(text) <= self.s.max_text_chars) or not isinstance(short, str) or len(short) > self.s.max_text_chars:
            raise ValueError("instruction text is missing or too long.")
        if icon not in ICONS:
            raise ValueError("Unknown icon.")
        out = {"text": text, "short": short, "icon": icon}
        if "metres" in value:
            if not _finite(value["metres"]) or not 0 <= value["metres"] <= 100000:
                raise ValueError("metres out of range.")
            out["metres"] = round(float(value["metres"]), 1)
        return out

    def _on_heading(self, conn: Conn, session: Session, message: dict, now: float) -> dict | None:
        dyaw, dpitch, mode = message.get("dyaw"), message.get("dpitch", 0), message.get("mode")
        limit = self.s.max_delta_deg
        if not (_finite(dyaw) and abs(dyaw) <= limit and _finite(dpitch) and abs(dpitch) <= limit) or mode not in ("touch", "gyro"):
            raise ValueError("heading needs dyaw/dpitch within the allowed range and a mode.")
        if not conn.bucket.take(now):
            if conn.drops.add(now) > self.s.too_fast_drops:
                conn.send(self._error("too_fast", "Sensor rate far above the limit; disconnecting."))
                conn.close(CLOSE_TOO_FAST, "too_fast")
            else:
                self._error_to(conn, now, "rate_limited", "Slow down: heading updates above 30 per second are dropped.")
            return None
        return {"t": "heading", "dyaw": round(float(dyaw), 3), "dpitch": round(float(dpitch), 3), "mode": mode}

    def _on_step(self, conn: Conn, session: Session, message: dict, now: float) -> dict:
        if message.get("action") not in STEP_ACTIONS:
            raise ValueError("Unknown step action.")
        return {"t": "step", "action": message["action"]}

    def _on_recenter(self, conn: Conn, session: Session, message: dict, now: float) -> dict:
        return {"t": "recenter"}

    # ---------- helpers ----------

    @staticmethod
    def _error(code: str, text: str) -> dict:
        return {"v": PROTOCOL_VERSION, "t": "error", "code": code, "message": text}

    def _error_to(self, conn: Conn, now: float, code: str, text: str) -> None:
        if now - conn.last_error_at >= 1.0:           # one error notice per second is enough
            conn.last_error_at = now
            conn.send(self._error(code, text))

    def _malformed(self, conn: Conn, now: float, text: str) -> None:
        self._error_to(conn, now, "bad_message", text)
        if conn.malformed.add(now) > self.s.max_malformed:
            conn.close(CLOSE_POLICY, "too_many_bad_messages")


# ---------- FastAPI glue ----------

class PairBody(BaseModel):
    code: str


def origin_ok(headers: Any) -> bool:
    """Browsers always send Origin on WebSocket handshakes. Accept only the page's own host (or no Origin at all,
    as native clients and test tools do), so another website cannot drive a socket from a visitor's browser."""
    origin = headers.get("origin")
    if not origin:
        return True
    return urlsplit(origin).netloc.lower() == (headers.get("host") or "").lower()


def _bearer(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    return token if scheme.lower() == "bearer" else ""


def _client(connection: Request | WebSocket) -> str:
    return connection.client.host if connection.client else "-"


def websocket_available() -> bool:
    """uvicorn serves WebSockets only when `websockets` (or `wsproto`) is installed; plain `uvicorn` accepts the
    route and then fails every handshake, which looks like a flaky phone. Report it instead."""
    return any(importlib.util.find_spec(name) is not None for name in ("websockets", "wsproto"))


def lan_addresses() -> list[str]:
    """Private IPv4 addresses of this machine: where a phone on the same network can reach the server."""
    found: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            private = address.startswith(("10.", "192.168.")) or (address.startswith("172.") and 16 <= int(address.split(".")[1]) <= 31)
            if private and address not in found:
                found.append(address)
    except OSError:
        pass
    return found


def create_companion_router(settings: Settings | None = None, hub: Hub | None = None, prefix: str = "/companion") -> APIRouter:
    """Router factory. `router.hub` exposes the Hub (tests, or the host app, may inspect or share it)."""
    hub = hub or Hub(settings)
    router = APIRouter(prefix=prefix, tags=["companion"])
    router.hub = hub  # type: ignore[attr-defined]

    def guard(call: Callable[[], Any]) -> Any:
        try:
            return call()
        except Denied as denied:
            raise HTTPException(status_code=denied.status, detail=denied.message) from None

    @router.get("/info")
    def info(request: Request) -> dict:
        return {"v": PROTOCOL_VERSION, "ws": f"{prefix}/ws", "websocket": websocket_available(), "secure_context": request.url.scheme == "https",
                "lan_addresses": lan_addresses(),
                "sensor_note": "Phone motion sensors need HTTPS or localhost; over plain LAN HTTP the touch controls still work."}

    @router.post("/sessions")
    def create(request: Request) -> dict:
        return guard(lambda: hub.create_session(_client(request)))

    @router.post("/sessions/{session_id}/code")
    def new_code(session_id: str, authorization: str | None = Header(None)) -> dict:
        return guard(lambda: hub.new_code(session_id, _bearer(authorization)))

    @router.delete("/sessions/{session_id}")
    def delete(session_id: str, authorization: str | None = Header(None)) -> dict:
        guard(lambda: hub.revoke(session_id, _bearer(authorization)))
        return {"ok": True}

    @router.post("/pair")
    def pair(body: PairBody, request: Request) -> dict:
        return guard(lambda: hub.pair(body.code, _client(request)))

    @router.websocket("/ws")
    async def socket_endpoint(websocket: WebSocket) -> None:
        if not origin_ok(websocket.headers):
            await websocket.close(code=CLOSE_ORIGIN)
            return
        await websocket.accept()
        loop = asyncio.get_running_loop()
        outbox: asyncio.Queue = asyncio.Queue(maxsize=256)

        def push(item: Any) -> None:
            try:
                outbox.put_nowait(item)
            except asyncio.QueueFull:          # a client that cannot keep up is dropped, never buffered without bound
                conn.closed = True
                loop.create_task(websocket.close(code=CLOSE_POLICY))

        conn = Conn(push, lambda code, reason: push(("close", code, reason)), hub.clock(), _client(websocket))

        async def writer() -> None:
            while True:
                item = await outbox.get()
                if item is None:
                    return
                if isinstance(item, tuple):
                    await websocket.close(code=item[1])
                    return
                await websocket.send_text(json.dumps(item, separators=(",", ":")))

        task = asyncio.create_task(writer())
        try:
            first = True
            while not conn.closed:
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(), hub.s.hello_timeout_s if first else None)
                except asyncio.TimeoutError:
                    conn.close(CLOSE_AUTH, "hello_timeout")
                    break
                first = False
                hub.receive(conn, raw)
        except WebSocketDisconnect:
            pass
        finally:
            hub.disconnect(conn)
            push(None)
            try:
                await asyncio.wait_for(task, 2)
            except Exception:  # noqa: BLE001 - the peer may already have closed the socket
                task.cancel()

    return router


def create_demo_app(static_dir: str | None = None, settings: Settings | None = None) -> FastAPI:
    """Standalone app for the two-browser demo and tests: the companion router plus optional static files."""
    app = FastAPI(title="floorwise companion demo")
    app.include_router(create_companion_router(settings))
    if static_dir:
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=static_dir, html=True), name="demo")
    return app


def main() -> None:
    import argparse

    import uvicorn

    cli = argparse.ArgumentParser(prog="python -m server.companion", description="Standalone companion demo server")
    cli.add_argument("--port", type=int, default=8100)
    cli.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to let a phone on the same network connect")
    cli.add_argument("--static", default=None, help="directory with the built demo pages")
    args = cli.parse_args()
    if not websocket_available():
        print("WARNING: no WebSocket library installed, so pairing cannot connect. Run with: uv run --with websockets python -m server.companion")
    if args.host != "127.0.0.1":
        print("Listening beyond localhost. Plain HTTP on a LAN is not a secure context: phone motion sensors stay off, touch works.")
        for address in lan_addresses():
            print(f"  phone URL: http://{address}:{args.port}/")
    uvicorn.run(create_demo_app(args.static), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
