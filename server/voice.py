"""ElevenLabs voice proxy: text to speech and speech to text behind the server, so the key never reaches the browser.

  GET  /api/voice/status   {"tts": bool, "stt": bool, "provider": "elevenlabs" | "browser"}
  POST /api/voice/tts      {"text": "..."} -> audio/mpeg (cached per phrase, capped per process)
  POST /api/voice/stt      raw audio body (webm/ogg/mp4/wav) -> {"text": "..."}

Without ELEVENLABS_API_KEY every endpoint answers 503 and the client falls back to the browser's own speech. The character budget
(ELEVENLABS_MAX_CHARS, default 60000 per server process) stops a loop or a script from spending the credits."""

import hashlib
import os
from collections import OrderedDict

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/voice")

API = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"  # "Rachel": clear, neutral; override with ELEVENLABS_VOICE_ID
MAX_TEXT = 600
MAX_AUDIO_BYTES = 5_000_000
CACHE_LIMIT = 64
_cache: "OrderedDict[str, bytes]" = OrderedDict()
_spent = {"chars": 0}


def _key() -> str | None:
    return os.environ.get("ELEVENLABS_API_KEY") or None


def _budget() -> int:
    try:
        return int(os.environ.get("ELEVENLABS_MAX_CHARS", "60000"))
    except ValueError:
        return 60000


class Speak(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)


@router.get("/status")
def status() -> dict:
    ready = _key() is not None
    return {"tts": ready, "stt": ready, "provider": "elevenlabs" if ready else "browser", "chars_left": max(0, _budget() - _spent["chars"]) if ready else 0}


@router.post("/tts")
def tts(body: Speak) -> Response:
    key = _key()
    if not key:
        raise HTTPException(503, "Voice output is not configured; the browser voice is used instead.")
    text = " ".join(body.text.split())
    voice = os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE)
    digest = hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()
    if digest in _cache:
        _cache.move_to_end(digest)
        return Response(_cache[digest], media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600", "X-Voice-Cache": "hit"})
    if _spent["chars"] + len(text) > _budget():
        raise HTTPException(429, "The voice budget for this session of the server is used up; the browser voice is used instead.")
    try:
        reply = httpx.post(f"{API}/text-to-speech/{voice}", params={"output_format": "mp3_44100_64"}, timeout=20.0,
                           headers={"xi-api-key": key, "accept": "audio/mpeg"},
                           json={"text": text, "model_id": os.environ.get("ELEVENLABS_MODEL", "eleven_flash_v2_5"),
                                 "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}})
    except httpx.HTTPError as error:
        raise HTTPException(502, f"Voice service unreachable: {type(error).__name__}") from error
    if reply.status_code != 200:
        raise HTTPException(502, f"Voice service answered {reply.status_code}")
    _spent["chars"] += len(text)
    _cache[digest] = reply.content
    while len(_cache) > CACHE_LIMIT:
        _cache.popitem(last=False)
    return Response(reply.content, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600", "X-Voice-Cache": "miss"})


@router.post("/stt")
async def stt(request: Request) -> dict:
    key = _key()
    if not key:
        raise HTTPException(503, "Voice input is not configured; the browser microphone recognition is used instead.")
    audio = await request.body()
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(413 if audio else 400, "Send between 1 byte and 5 MB of audio.")
    kind = (request.headers.get("content-type") or "audio/webm").split(";")[0]
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            reply = await client.post(f"{API}/speech-to-text", headers={"xi-api-key": key}, data={"model_id": os.environ.get("ELEVENLABS_STT_MODEL", "scribe_v1")},
                                      files={"file": ("speech", audio, kind)})
    except httpx.HTTPError as error:
        raise HTTPException(502, f"Voice service unreachable: {type(error).__name__}") from error
    if reply.status_code != 200:
        raise HTTPException(502, f"Voice service answered {reply.status_code}")
    return {"text": str(reply.json().get("text", "")).strip()}
