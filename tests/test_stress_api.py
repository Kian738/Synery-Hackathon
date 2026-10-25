"""The stress test over HTTP: runs on the session's building (edits and closures included) and ranks new doors, never as a hidden regression."""
from fastapi.testclient import TestClient

from server.app import app

client = TestClient(app)


def session(name="proc-factory-dev-003") -> str:
    return client.post("/api/sessions", json={"building_id": name}).json()["session_id"]


def test_stress_returns_kpis_doors_rooms_frames_and_the_assumptions():
    sid = session()
    r = client.post(f"/api/sessions/{sid}/stress", json={}).json()
    k = r["kpis"]
    assert k["evacuated"] == k["people"] > 0 and k["p50_s"] <= k["p95_s"] <= k["max_s"]
    assert r["doors"] and r["doors"][0]["total_wait_s"] >= r["doors"][-1]["total_wait_s"]
    assert r["rooms"] and {"los", "peak_density", "peak_people"} <= set(r["rooms"][0])
    assert r["frames"]["step_s"] > 0 and r["frames"]["rooms"]
    assert any("Pre-movement" in a for a in r["assumptions"])


def test_closing_an_exit_through_the_session_slows_or_strands():
    sid = session()
    base = client.post(f"/api/sessions/{sid}/stress", json={"seed": 3}).json()
    exit_id = next(d["id"] for d in base["doors"] if "outside" in d["between"])
    client.post(f"/api/sessions/{sid}/close", json={"element": exit_id, "closed": True})
    after = client.post(f"/api/sessions/{sid}/stress", json={"seed": 3}).json()
    assert after["kpis"]["stranded"] >= base["kpis"]["stranded"]
    assert after["kpis"]["max_s"] >= base["kpis"]["max_s"] or after["kpis"]["stranded"] > base["kpis"]["stranded"]


def test_door_recommendations_are_proved_by_a_second_run_and_flag_regressions():
    sid = session("osm-way61408163")
    r = client.post(f"/api/sessions/{sid}/stress/doors", json={"top": 3}).json()
    assert r["candidates"], r
    for c in r["candidates"]:
        assert c["p95_before_s"] == r["baseline"]["p95_s"]
        assert c["regress"] == (c["p95_after_s"] > c["p95_before_s"] * 1.02 or c["stranded_after"] > c["stranded_before"])
        assert c["door"]["position"] and c["door"]["width_m"] == 1.0
    assert [c["regress"] for c in r["candidates"]] == sorted(c["regress"] for c in r["candidates"])  # regressions last


def test_bad_input_is_refused_not_guessed():
    sid = session()
    assert client.post(f"/api/sessions/{sid}/stress", json={"closed": ["nope"]}).status_code == 422
    assert client.post(f"/api/sessions/{sid}/stress", json={"occupants": {"nope": 3}}).status_code == 422
    assert client.post(f"/api/sessions/{sid}/stress", json={"kind": "fire-ball"}).status_code == 422
