from fastapi.testclient import TestClient

from server.app import app

client = TestClient(app)


def test_map_flow_without_api_key():
    listing = client.get("/api/buildings", params={"split": "dev"}).json()
    assert any(b["building_id"] == "proc-factory-dev-003" for b in listing)
    geometry = client.get("/api/buildings/proc-factory-dev-003").json()
    assert geometry["spaces"] and geometry["floors"]
    session_id = client.post("/api/sessions", json={"building_id": "proc-factory-dev-003"}).json()["session_id"]
    lobby = next(s for s in geometry["spaces"] if s["room_type"] == "lobby")["id"]
    lab = next(s for s in geometry["spaces"] if s["room_type"] == "quality_lab")["id"]
    routed = client.post(f"/api/sessions/{session_id}/route", json={"start": lobby, "destination": lab}).json()
    assert routed["result"]["length_m"] > 0
    assert routed["events"][0]["type"] == "route"
    closed = client.post(f"/api/sessions/{session_id}/close", json={"element": "Office lift"}).json()
    assert closed["result"]["closed"] is True
    missing = client.post(f"/api/sessions/{session_id}/route", json={"start": "Room 9.99", "destination": lab})
    assert missing.status_code == 422


def test_lab_endpoints():
    suites = client.get("/api/lab/suites").json()
    assert "e2e" in suites["suites"]
    runs = client.get("/api/lab/runs").json()
    assert isinstance(runs, list)
    if runs:
        detail = client.get(f"/api/lab/runs/{runs[0]['run']}").json()
        assert "rows" in detail
    assert client.post("/api/lab/jobs", json={"suite": "rm -rf", "args": []}).status_code == 422
    assert client.post("/api/lab/jobs", json={"suite": "routes", "args": ["--evil"]}).status_code == 422
    assert client.get("/api/lab/dataset").json()["splits"]["train"] == 200


def test_tts_endpoints():
    status = client.get("/api/tts/status").json()
    assert "enabled" in status
    assert "provider" in status
    # Without cloud API keys, /api/tts returns 501
    tts_resp = client.post("/api/tts", json={"text": "Hello world"})
    assert tts_resp.status_code in (200, 501)
    # Empty text validation
    empty_resp = client.post("/api/tts", json={"text": ""})
    assert empty_resp.status_code == 400


def test_speech_text_processing():
    from server.app import clean_speech_text, extract_speech_sentences

    raw = "Here is the route to **Room 204**:\n# Steps\n- Walk down the hall.\n- Turn right!"
    cleaned = clean_speech_text(raw)
    assert "**" not in cleaned
    assert "#" not in cleaned
    assert "-" not in cleaned
    assert "Room 204" in cleaned

    sentences, remainder = extract_speech_sentences("Hello world! How are you doing? I am fine", is_final=False)
    assert len(sentences) == 2
    assert sentences[0] == "Hello world!"
    assert sentences[1] == "How are you doing?"
    assert remainder == "I am fine"

    final_sentences, remainder = extract_speech_sentences(remainder, is_final=True)
    assert final_sentences == ["I am fine"]
    assert remainder == ""


def test_tts_streamer_mock():
    from server.app import TtsStreamer

    chunks = []
    def push_fn(kind, data):
        chunks.append((kind, data))

    # Mock synthesize method to avoid external HTTP calls during unit test
    streamer = TtsStreamer(push_fn, api_key="test_key", voice_id="test_voice")
    streamer._synthesize = lambda text: b"MPEG_AUDIO_FIXTURE"

    streamer.feed_delta("First sentence here. ")
    streamer.feed_delta("Second sentence ")
    streamer.feed_delta("arrives now! ")
    streamer.flush_and_close(timeout=2.0)

    audio_chunks = [c for c in chunks if c[0] == "audio_chunk"]
    assert len(audio_chunks) == 2
    assert audio_chunks[0][1]["text"] == "First sentence here."
    assert audio_chunks[0][1]["index"] == 0
    assert audio_chunks[0][1]["format"] == "audio/mpeg"
    assert audio_chunks[1][1]["text"] == "Second sentence arrives now!"
    assert audio_chunks[1][1]["index"] == 1


def test_tts_streamer_fallback_on_reply():
    from server.app import TtsStreamer

    chunks = []
    streamer = TtsStreamer(lambda kind, data: chunks.append((kind, data)), api_key="test_key", voice_id="test_voice")
    streamer._synthesize = lambda text: b"MPEG_AUDIO"

    reply = "Here is the route. Walk straight ahead."
    if streamer.chunk_index == 0 and reply:
        streamer.feed_delta(reply)
    streamer.flush_and_close(timeout=2.0)

    audio_chunks = [c for c in chunks if c[0] == "audio_chunk"]
    assert len(audio_chunks) == 2
    assert audio_chunks[0][1]["text"] == "Here is the route."
    assert audio_chunks[1][1]["text"] == "Walk straight ahead."


def test_openai_loop_emits_text_delta(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from floorwise.llm.loop import Conversation

    class MockStream:
        def __init__(self, chunks):
            self.chunks = chunks
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def __iter__(self):
            return iter(self.chunks)

    chunks = [
        SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=SimpleNamespace(content="Walk to room 101.", tool_calls=None))]),
        SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=SimpleNamespace(content=" ", tool_calls=None))]),
        SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=SimpleNamespace(content="Turn left.", tool_calls=None))]),
    ]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MockStream(chunks)

    monkeypatch.setattr("floorwise.llm.client", lambda provider: mock_client)

    events = []
    conv = Conversation("system", [], provider="groq")
    conv.messages = []
    reply = conv.ask("Where is room 101?", on_event=lambda kind, data: events.append((kind, data)))

    assert reply == "Walk to room 101. Turn left."
    text_deltas = [e[1]["text"] for e in events if e[0] == "text_delta"]
    assert text_deltas == ["Walk to room 101.", " ", "Turn left."]


