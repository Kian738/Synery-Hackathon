"""ElevenLabs proxy: no key means 503 and a browser fallback; with a key the audio is cached and the character budget is enforced."""
import httpx
from fastapi.testclient import TestClient

from server import voice
from server.app import app

client = TestClient(app)


def _reset(monkeypatch, key="k"):
    voice._cache.clear(); voice._spent["chars"] = 0
    if key: monkeypatch.setenv("ELEVENLABS_API_KEY", key)
    else: monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)


def test_without_key_everything_falls_back(monkeypatch):
    _reset(monkeypatch, None)
    assert client.get("/api/voice/status").json()["provider"] == "browser"
    assert client.post("/api/voice/tts", json={"text": "hi"}).status_code == 503
    assert client.post("/api/voice/stt", content=b"x", headers={"content-type": "audio/webm"}).status_code == 503


def test_tts_is_cached_and_budgeted(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("ELEVENLABS_MAX_CHARS", "10")
    calls = []
    def fake(url, **kw):
        calls.append(kw["json"]["text"]); return httpx.Response(200, content=b"MP3", request=httpx.Request("POST", url))
    monkeypatch.setattr(voice.httpx, "post", fake)
    first = client.post("/api/voice/tts", json={"text": "Turn  left"})
    again = client.post("/api/voice/tts", json={"text": "Turn left"})
    assert first.content == b"MP3" and again.headers["x-voice-cache"] == "hit" and calls == ["Turn left"]
    assert client.post("/api/voice/tts", json={"text": "A much longer sentence"}).status_code == 429
    assert client.post("/api/voice/tts", json={"text": "x" * 601}).status_code == 422


def test_stt_returns_text(monkeypatch):
    _reset(monkeypatch)
    class Fake:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, **kw): return httpx.Response(200, json={"text": " where is the lift "}, request=httpx.Request("POST", url))
    monkeypatch.setattr(voice.httpx, "AsyncClient", lambda **k: Fake())
    assert client.post("/api/voice/stt", content=b"abc", headers={"content-type": "audio/webm"}).json() == {"text": "where is the lift"}
