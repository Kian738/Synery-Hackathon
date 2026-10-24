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
