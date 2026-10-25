"""HTTP API for the app. Map interactions (route, close, add door) call the Session directly, so the map
works without an API key; /chat runs the Claude agent and streams its tool calls and UI events (SSE).

  uv run --env-file .env uvicorn server.app:app --reload --port 8000"""

import asyncio
import base64
import csv
import json
import os
import queue as std_queue
import threading
import uuid
from functools import lru_cache
from pathlib import Path

import httpx
import re
import tempfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from floorwise.agent.session import Session
from floorwise.core.model import Building
from floorwise.core.resolve import ResolveError
from floorwise.paths import DATA, ROOT


def _load_env_if_present() -> None:
    # If ANTHROPIC_API_KEY is a CLI user token (sk-ant-usr-...) rather than an API key (sk-ant-api03-...),
    # unset it so the Anthropic SDK's valid auto-discovered profile/credentials are used instead.
    if os.environ.get("ANTHROPIC_API_KEY", "").startswith("sk-ant-usr-"):
        del os.environ["ANTHROPIC_API_KEY"]

    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k == "ANTHROPIC_API_KEY" and v.startswith("sk-ant-usr-"):
                continue
            if k and k not in os.environ:
                os.environ[k] = v

    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        cred_path = Path.home() / ".config" / "anthropic" / "credentials" / "default.json"
        if cred_path.is_file():
            try:
                import json
                cred = json.loads(cred_path.read_text(encoding="utf-8"))
                tok = cred.get("access_token")
                if tok:
                    os.environ["ANTHROPIC_AUTH_TOKEN"] = tok
            except Exception:
                pass


_load_env_if_present()

app = FastAPI(title="floorwise")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SESSIONS: dict[str, dict] = {}


@app.on_event('startup')
def record_build():
    from eval.evidence import fingerprint
    app.state.boot_fingerprint = fingerprint()


@app.get('/api/version')
def version():
    from eval.evidence import fingerprint
    current = fingerprint()
    boot = getattr(app.state, 'boot_fingerprint', current)
    return {'boot': boot, 'current': current, 'restart_required': boot != current}


@app.get('/api/sessions/{session_id}/state')
def state(session_id: str):
    session = session_or_404(session_id)['session']
    return {'profile': dict(session.profile.__dict__), 'closed': list(session.closed), 'edits': list(session.edits),
            'route': session.last_route.to_dict() if session.last_route else None,
            'results': [{k:v for k,v in r.items() if k not in ('rows','item_rows','room_rows')}
                        for r in list(session.visual_results.values())]}


@app.post('/api/lab/evaluate-conversation')
def evaluate_conversation(body: dict):
    if os.environ.get('FLOORWISE_EVAL_API') != '1': raise HTTPException(404, 'Evaluation endpoint disabled')
    from eval.conversations import cases, assertions, grade
    from floorwise.llm import budget
    case = next((c for c in cases() if c['id'] == body.get('case_id')), None)
    if not case: raise HTTPException(422, 'Unknown evaluation case')
    events = body.get('events', [])
    snapshot = state(body['session_id'])
    checks = assertions(case, snapshot, events)
    try:
        review, usage = grade(case, events)
    except budget.BudgetExceeded:
        return {'checks': checks, 'correct': False, 'incomplete': True, 'budget_used': budget.used(),
                'reason': 'Batch token budget exhausted', 'state': snapshot}
    scores = [v for k,v in (review or {}).items() if k != 'issues' and v is not None]
    review_passed = bool(scores) and min(scores) >= 4 and sum(scores)/len(scores) >= 4.5
    return {'checks': checks, 'review': review, 'review_usage': usage, 'budget_used': budget.used(),
            'correct': all(c['passed'] for c in checks) and review_passed,
            'review_source': 'model, not human', 'state': snapshot}

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
def visual_result_page(session_id: str, result_id: str, offset: int = 0, limit: int = 25, view: str = 'default', room: str | None = None) -> dict:
    entry=session_or_404(session_id)
    try:
        return entry['session'].result_page(result_id, offset, limit, view, room)
    except KeyError as error:
        raise HTTPException(404, 'Result expired or belongs to another session') from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


# ---------- chat (Claude) & streaming TTS ----------

ABBREVIATIONS = {"dr", "mr", "ms", "mrs", "eg", "ie", "vs", "rm", "no", "st"}


def clean_speech_text(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^Answer:\s*", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"^[-*•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_speech_sentences(buffer: str, is_final: bool = False) -> tuple[list[str], str]:
    sentences = []
    pattern = re.compile(r"([.!?]+(?:\s+|\Z)|\n+)")
    pos = 0
    while True:
        m = pattern.search(buffer, pos)
        if not m:
            if len(buffer) > 120:
                clause_match = re.search(r"[,;:\n]\s+", buffer[60:120])
                if clause_match:
                    split_idx = 60 + clause_match.end()
                    cand = buffer[:split_idx].strip()
                    sentences.append(cand)
                    buffer = buffer[split_idx:].lstrip()
                    pos = 0
                    continue
            break
        candidate = buffer[:m.end()].strip()
        text_before_match = buffer[:m.start()]
        if re.match(r"^\s*\d+\.\s*$", candidate):
            pos = m.end()
            continue
        words = re.findall(r"[A-Za-z]+", text_before_match)
        if words and words[-1].lower() in ABBREVIATIONS:
            pos = m.end()
            continue
        sentences.append(candidate)
        buffer = buffer[m.end():].lstrip()
        pos = 0

    if is_final and buffer.strip():
        sentences.append(buffer.strip())
        buffer = ""
    return sentences, buffer


class TtsStreamer:
    """Buffers text deltas from Claude, splits into spoken sentences, and streams

    low-latency ElevenLabs audio chunks as base64-encoded audio over SSE.
    """

    def __init__(self, push_fn, api_key: str, voice_id: str, model_id: str = "eleven_turbo_v2_5") -> None:
        self.push = push_fn
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.buffer = ""
        self.chunk_index = 0
        self.queue: std_queue.Queue = std_queue.Queue()
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def feed_delta(self, text: str) -> None:
        self.buffer += text
        sents, self.buffer = extract_speech_sentences(self.buffer, is_final=False)
        for s in sents:
            cleaned = clean_speech_text(s)
            if cleaned and re.search(r"[A-Za-z0-9]", cleaned):
                self.queue.put((self.chunk_index, cleaned))
                self.chunk_index += 1

    def clear(self) -> None:
        self.buffer = ""
        with self.queue.mutex:
            self.queue.queue.clear()

    def flush_and_close(self, timeout: float = 6.0) -> None:
        sents, self.buffer = extract_speech_sentences(self.buffer, is_final=True)
        for s in sents:
            cleaned = clean_speech_text(s)
            if cleaned and re.search(r"[A-Za-z0-9]", cleaned):
                self.queue.put((self.chunk_index, cleaned))
                self.chunk_index += 1
        self.queue.put(None)
        self.worker.join(timeout=timeout)

    def _synthesize(self, text: str) -> bytes | None:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream?optimize_streaming_latency=4"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 200 and resp.content:
                    return resp.content
                if resp.status_code != 200 and self.model_id != "eleven_multilingual_v2":
                    payload["model_id"] = "eleven_multilingual_v2"
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200 and resp.content:
                        return resp.content
        except Exception:
            pass
        return None

    def _run(self) -> None:
        while True:
            item = self.queue.get()
            if item is None:
                self.queue.task_done()
                break
            idx, text = item
            audio_bytes = self._synthesize(text)
            if audio_bytes:
                b64 = base64.b64encode(audio_bytes).decode("ascii")
                self.push("audio_chunk", {
                    "index": idx,
                    "text": text,
                    "audio": b64,
                    "format": "audio/mpeg",
                })
            self.queue.task_done()


class ChatBody(BaseModel):
    text: str
    selected_space: str | None = None
    request_id: str | None = None


class AnalysisBody(BaseModel):
    kind: str
    item: str = ''
    floor: str | None = None
    room: str | None = None


@app.post('/api/sessions/{session_id}/analysis')
def analysis(session_id: str, body: AnalysisBody):
    """Structured map actions; natural-language chat always goes through Claude."""
    operations={'count':'count_items','ranking':'rank_by_items','area':'room_info'}
    if body.kind not in operations: raise HTTPException(422,'Unknown analysis kind')
    entry=session_or_404(session_id)
    with entry['lock']:
        if body.kind=='area':return call(entry['session'],'room_info',body.room or body.item)
        return call(entry['session'],operations[body.kind],body.item,body.floor)


@app.post('/api/sessions/{session_id}/chat/cancel')
def cancel_chat(session_id: str, body: dict):
    entry = session_or_404(session_id)
    event = entry.get('requests', {}).get(body.get('request_id'))
    if event: event.set()
    return {'stopped': event is not None}


@app.post("/api/sessions/{session_id}/chat")
async def chat(session_id: str, body: ChatBody) -> StreamingResponse:
    entry = session_or_404(session_id)
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    request_id = body.request_id or uuid.uuid4().hex
    cancelled = threading.Event()
    entry.setdefault('requests', {})[request_id] = cancelled

    def push(kind: str, payload) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": kind, "data": payload, 'request_id': request_id})
        except Exception:
            pass

    def work() -> None:
        if not entry['lock'].acquire(timeout=5):
            entry.get('requests', {}).pop(request_id, None)
            push('error',{'message':'Another request is still using this session. Please retry shortly.'})
            push('done',None)
            return
        try:
            try:
                from floorwise import llm

                if entry["agent"] is None:
                    from floorwise.agent.chat import ChatAgent

                    entry["agent"] = ChatAgent(entry["session"])
                agent = entry["agent"]
                agent.cancelled = cancelled.is_set
                entry["session"].events.clear()
                if body.selected_space is not None and body.selected_space not in entry["session"].building.spaces:
                    raise ValueError("Selected room does not belong to this building")
                entry["session"].ui_selection = body.selected_space
 
                eleven_key = os.getenv("ELEVENLABS_API_KEY")
                voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
                model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")
                streamer = (
                    TtsStreamer(push, eleven_key, voice_id, model_id)
                    if eleven_key
                    else None
                )
 
                def on_chat_event(kind: str, payload) -> None:
                    if streamer:
                        if kind in ("text_delta", "assistant_delta") and isinstance(payload, dict) and "text" in payload:
                            streamer.feed_delta(payload["text"])
                        elif kind in ("clear_deltas", "assistant_start"):
                            streamer.clear()
                    push(kind, payload)
 
                reply = agent.ask(body.text, on_event=on_chat_event)
                if streamer:
                    if streamer.chunk_index == 0 and reply:
                        streamer.feed_delta(reply)
                    streamer.flush_and_close()
 
                push("reply", {
                    "text": reply,
                    "usage": agent.turn_usage,
                    "model": agent.model,
                    "message_id": getattr(getattr(agent, "conversation", None), "last_message_id", None),
                })
            except Exception as error:  # noqa: BLE001 - surface every failure to the UI
                message = ('Request stopped. Computed results remain available.' if isinstance(error, InterruptedError) else
                           'The language service timed out. Please retry. Computed map results remain available.' if 'timeout' in type(error).__name__.lower() else
                           'The language service could not complete this request. Please retry; computed results remain available.')
                diagnostic=str(getattr(error,'body',{}).get('error',{}).get('message','')) if isinstance(getattr(error,'body',None),dict) else ''
                for key,value in os.environ.items():
                    if any(word in key for word in ('KEY','TOKEN','SECRET')) and len(value)>8:diagnostic=diagnostic.replace(value,'[redacted]')
                push("error", {"message": message, 'code': type(error).__name__, 'request_id': request_id, 'diagnostic':diagnostic[:800]})
            finally:
                push("done", None)
        finally:
            entry.get('requests', {}).pop(request_id, None)
            entry['lock'].release()

    push('progress',{'stage':'queued','message':'Starting your request'})
    threading.Thread(target=work, daemon=True).start()

    async def stream():
        try:
            while True:
                item = await queue.get()
                yield f"data: {json.dumps(item, ensure_ascii=False, default=str)}\n\n"
                if item["type"] == "done": break
        finally:
            cancelled.set()

    return StreamingResponse(stream(), media_type="text/event-stream")


# ---------- text to speech (ElevenLabs / OpenAI / Browser fallback) ----------

class TtsBody(BaseModel):
    text: str
    voice_id: str | None = None


@app.get("/api/tts/status")
async def tts_status() -> dict:
    if os.getenv("ELEVENLABS_API_KEY"):
        return {"enabled": True, "provider": "elevenlabs"}
    if os.getenv("OPENAI_API_KEY"):
        return {"enabled": True, "provider": "openai"}
    return {"enabled": False, "provider": "browser"}


@app.post("/api/tts")
async def text_to_speech(body: TtsBody) -> Response:
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Text is required")

    eleven_key = os.getenv("ELEVENLABS_API_KEY")
    if eleven_key:
        voice_id = body.voice_id or os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": eleven_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"),
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }
        import httpx
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    raise HTTPException(resp.status_code, f"ElevenLabs error: {resp.text}")
                return Response(content=resp.content, media_type="audio/mpeg")
        except httpx.RequestError as exc:
            raise HTTPException(502, f"Failed to contact ElevenLabs: {exc}") from exc

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=openai_key)
            response = await client.audio.speech.create(
                model=os.getenv("OPENAI_TTS_MODEL", "tts-1"),
                voice=os.getenv("OPENAI_TTS_VOICE", "alloy"),
                input=text,
            )
            return Response(content=response.content, media_type="audio/mpeg")
        except Exception as exc:
            raise HTTPException(502, f"OpenAI TTS error: {exc}") from exc

    raise HTTPException(501, "No cloud TTS configured (ELEVENLABS_API_KEY or OPENAI_API_KEY missing)")


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
