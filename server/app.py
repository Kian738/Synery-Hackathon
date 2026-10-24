"""HTTP API for the app. Map interactions (route, close, add door) call the Session directly, so the map
works without an API key; /chat runs the Claude agent and streams its tool calls and UI events (SSE).

  uv run --env-file .env uvicorn server.app:app --reload --port 8000"""

import asyncio
import csv
import json
import os
import threading
import uuid
from functools import lru_cache
from pathlib import Path

import re
import tempfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from floorwise.agent.session import Session
from floorwise.core.model import Building
from floorwise.core.resolve import ResolveError
from floorwise.paths import DATA, ROOT

app = FastAPI(title="floorwise")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SESSIONS: dict[str, dict] = {}

from server.lab import router as lab_router  # noqa: E402
from server.companion import create_companion_router  # noqa: E402

app.include_router(lab_router)
app.include_router(create_companion_router())


@lru_cache(maxsize=1)
def manifest() -> list[dict]:
    with (DATA / "manifest.csv").open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def building_dir(building_id: str) -> Path:
    for row in manifest():
        if row["building_id"] == building_id:
            return DATA / row["path"]
    custom = ROOT / "buildings" / building_id
    if (custom / "building.json").exists():
        return custom
    raise HTTPException(404, f"unknown building {building_id}")


@lru_cache(maxsize=32)
def load(building_id: str) -> Building:
    return Building.load(building_dir(building_id))


def session_or_404(session_id: str) -> dict:
    if session_id not in SESSIONS:
        raise HTTPException(404, "unknown session")
    return SESSIONS[session_id]


def geometry_payload(b: Building) -> dict:
    anchors={sid: list(poly.representative_point().coords)[0] for sid,poly in b.polygons.items()}
    return {
        "building": b.info,
        "floors": sorted(b.data["floors"], key=lambda f: f["level"]),
        "spaces": [
            {**{k: s.get(k) for k in ("id", "floor_id", "type", "room_type", "name", "ref", "polygon", "synthetic")}, "anchor": anchors[s["id"]]} for s in b.spaces.values()
        ],
        "openings": [
            {k: o.get(k) for k in ("id", "floor_id", "space_ids", "kind", "position", "width_m", "step_free", "synthetic")}
            for o in b.openings.values()
        ],
        "connectors": list(b.connectors.values()),
        "assets": [
            {k: a.get(k) for k in ("id", "name", "type", "category", "space_id", "floor_id", "position", "footprint", "source")}
            for a in b.assets.values()
        ],
    }


# ---------- buildings ----------

@app.get("/api/buildings")
def buildings(split: str | None = None) -> list[dict]:
    rows = [r for r in manifest() if split is None or r["split"] == split]
    custom = [
        {"building_id": p.name, "split": "custom", "source": "built", "name": p.name, "floors": "?"}
        for p in sorted((ROOT / "buildings").glob("*")) if (p / "building.json").exists()
    ] if (ROOT / "buildings").exists() else []
    keys = ("building_id", "split", "source", "name", "floors", "rooms", "assets", "has_lift")
    return [{k: r.get(k) for k in keys} for r in rows] + custom


@app.get("/api/buildings/{building_id}")
def building(building_id: str) -> dict:
    return geometry_payload(load(building_id))


# ---------- sessions ----------

class NewSession(BaseModel):
    building_id: str


@app.post("/api/sessions")
def new_session(body: NewSession) -> dict:
    session_id = uuid.uuid4().hex[:12]
    SESSIONS[session_id] = {"session": Session.for_building(load(body.building_id)), "agent": None, "lock": threading.RLock()}
    return {"session_id": session_id, "building_id": body.building_id}


@app.get("/api/sessions/{session_id}")
def session_state(session_id: str) -> dict:
    s: Session = session_or_404(session_id)["session"]
    return {"closed": sorted(s.closed), "edits": s.edits, "profile": s.profile.__dict__,
            "last_route": s.last_route.to_dict() if s.last_route else None}


@app.get("/api/sessions/{session_id}/geometry")
def session_geometry(session_id: str) -> dict:
    """Geometry including this session's edits (new doors, moved items)."""
    return geometry_payload(session_or_404(session_id)["session"].building)


@app.get("/api/sessions/{session_id}/scene")
def session_scene(session_id: str) -> dict:
    from floorwise.core.scene import compile_scene
    b = session_or_404(session_id)["session"].building
    return {**geometry_payload(b), "scene": compile_scene(b)}


class RouteBody(BaseModel):
    start: str
    destination: str
    via: list[str] | None = None
    step_free: bool | None = None
    min_door_width_m: float | None = None
    avoid: list[str] | None = None
    prefer_avoid: list[str] | None = None
    avoid_stairs: bool = False


def call(session: Session, method: str, *args, **kwargs) -> dict:
    try:
        result = getattr(session, method)(*args, **kwargs)
    except ResolveError as error:
        raise HTTPException(422, {"error": str(error), "candidates": error.candidates[:8]}) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    events, session.events[:] = list(session.events), []
    return {"result": result, "events": events}


@app.post("/api/sessions/{session_id}/route")
def route(session_id: str, body: RouteBody) -> dict:
    entry = session_or_404(session_id)
    with entry["lock"]:
        return call(entry["session"], "route", body.start, body.destination, body.via, step_free=body.step_free,
                    min_door_width_m=body.min_door_width_m, avoid=body.avoid, prefer_avoid=body.prefer_avoid,
                    avoid_stairs=body.avoid_stairs)


class CloseBody(BaseModel):
    element: str
    closed: bool = True


@app.post("/api/sessions/{session_id}/close")
def close(session_id: str, body: CloseBody) -> dict:
    entry = session_or_404(session_id)
    with entry["lock"]:
        return call(entry["session"], "set_closed", body.element, body.closed)


class DoorBody(BaseModel):
    first: str
    second: str
    confirm: bool = False


@app.post("/api/sessions/{session_id}/door")
def door(session_id: str, body: DoorBody) -> dict:
    s = session_or_404(session_id)["session"]
    return call(s, "add_door" if body.confirm else "door_preview", body.first, body.second)


@app.get("/api/sessions/{session_id}/search")
def search(session_id: str, q: str, floor: str | None = None) -> dict:
    return call(session_or_404(session_id)["session"], "search", q, floor)


from server.insight import insight_router
app.include_router(insight_router(session_or_404, call))
from server.scenario import scenario_router  # noqa: E402
app.include_router(scenario_router(session_or_404))

@app.get("/api/sessions/{session_id}/results/{result_id}")
def visual_result_page(session_id: str, result_id: str, offset: int = 0, limit: int = 25) -> dict:
    entry=session_or_404(session_id)
    with entry['lock']:
        try:
            return entry['session'].result_page(result_id, offset, limit)
        except KeyError as error:
            raise HTTPException(404, 'Result expired or belongs to another session') from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error


# ---------- chat (Claude) ----------

class ChatBody(BaseModel):
    text: str
    selected_space: str | None = None


@app.post("/api/sessions/{session_id}/chat")
async def chat(session_id: str, body: ChatBody) -> StreamingResponse:
    entry = session_or_404(session_id)
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def push(kind: str, payload) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, {"type": kind, "data": payload})

    def work() -> None:
        with entry["lock"]:
            try:
                from floorwise import llm

                if entry["agent"] is None:
                    from floorwise.agent.chat import ChatAgent

                    entry["agent"] = ChatAgent(entry["session"])
                agent = entry["agent"]
                entry["session"].events.clear()
                if body.selected_space is not None and body.selected_space not in entry["session"].building.spaces:
                    raise ValueError("Selected room does not belong to this building")
                entry["session"].ui_selection=body.selected_space
                reply = agent.ask(body.text, on_event=push)
                push("reply", {"text": reply, "usage": agent.turn_usage, "model": agent.model})
            except Exception as error:  # noqa: BLE001 - surface every failure to the UI
                push("error", {"message": f"{type(error).__name__}: {error}"})
            finally:
                push("done", None)

    threading.Thread(target=work, daemon=True).start()

    async def stream():
        while True:
            item = await queue.get()
            yield f"data: {json.dumps(item, ensure_ascii=False, default=str)}\n\n"
            if item["type"] == "done":
                break

    return StreamingResponse(stream(), media_type="text/event-stream")


# ---------- Level 4: build a building from plan images ----------

@app.post("/api/build")
async def build_from_plans(
    files: list[UploadFile] = File(...),
    levels: str = Form(..., description="comma-separated floor level per file, e.g. 0,1,2"),
    width_m: float = Form(..., description="width of the ground floor in metres"),
    name: str = Form("New building"),
    vision: bool = Form(False),
) -> dict:
    from floorwise.build.builder import build

    import math
    if not math.isfinite(width_m) or width_m <= 0 or width_m > 2000:
        raise HTTPException(422, "Supply a positive plan width of at most 2000 metres.")
    try:
        level_list = [int(v) for v in levels.split(",")]
    except ValueError as error:
        raise HTTPException(422, "Floor levels must be comma-separated integers.") from error
    if not files or len(files) > 20 or len(set(level_list)) != len(level_list):
        raise HTTPException(422, "Supply 1-20 images, with one distinct level per image.")
    if len(level_list) != len(files):
        raise HTTPException(422, "one level per file")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "building"
    building_id = f"built-{slug}-{uuid.uuid4().hex[:4]}"
    with tempfile.TemporaryDirectory() as folder:
        images = {}
        for level, upload in zip(level_list, files):
            path = Path(folder) / f"floor_{level}.png"
            content = await upload.read(15 * 1024 * 1024 + 1)
            if len(content) > 15 * 1024 * 1024:
                raise HTTPException(422, "Each plan image must be at most 15 MB.")
            path.write_bytes(content)
            images[level] = path
        building, report = await asyncio.to_thread(
            build, images, width_m=width_m, name=name, building_id=building_id, vision=vision)
    target = ROOT / "buildings" / building_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "building.json").write_text(json.dumps(building, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"building_id": building_id, "report": report}


# ---------- static web app (after `npm run build` in web/) ----------

WEB_DIST = ROOT / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/")
    @app.get("/phone")
    @app.get("/lab")
    @app.get("/lab/{rest:path}")
    def index(rest: str = "") -> FileResponse:
        return FileResponse(WEB_DIST / "index.html")
