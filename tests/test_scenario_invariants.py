"""Properties every evacuation answer must satisfy, whatever the building or hazard room (no gold answers needed)."""
import random

import pytest

from floorwise.core.model import Building
from floorwise.paths import DATA
from floorwise.reason.report import scenario_report

BUILDINGS = [("dev", "proc-campus-dev-000"), ("dev", "proc-factory-dev-003"), ("dev", "swiss-1785") if (DATA / "dev" / "swiss-1785").exists() else ("train", "swiss-1785")]


def report(building, rooms, audience="safety_officer", **spec_extra):
    spec = {"hazards": [{"spaces": rooms}], "responders": {"auto": True}, **spec_extra}
    return scenario_report(building, "evacuation", {"spec": spec}, audience)


@pytest.mark.parametrize("split,name", BUILDINGS)
def test_evacuation_invariants(split, name):
    building = Building.load(DATA / split / name)
    rooms = [s for s, v in building.spaces.items() if v["type"] == "room"]
    rng = random.Random(name)
    checked = 0
    for room in rng.sample(rooms, min(4, len(rooms))):
        out = report(building, [room])
        evac = out["evacuation"]
        if not evac:
            assert out["abstained"], "no evacuation numbers means the report must say why"
            continue
        checked += 1
        assert 0 <= evac["evacuated"] <= evac["total"]
        assert evac["T_s"] >= 0
        assert sum(evac["by_exit"].values()) <= evac["total"]
        assert sum(evac["stranded"].values()) + evac["evacuated"] <= evac["total"] + 1e-6
        again = report(building, [room])["evacuation"]
        assert again["T_s"] == evac["T_s"] and again["by_exit"] == evac["by_exit"], "same inputs, same answer"
    assert checked >= 1


def test_an_exit_limit_never_speeds_people_up():
    building = Building.load(DATA / "dev" / "proc-campus-dev-000")
    room = next(s for s, v in building.spaces.items() if v["name"] == "Canteen 0.28")
    free = report(building, [room])["evacuation"]
    busiest = max(free["by_exit"], key=free["by_exit"].get)
    limited = report(building, [room], capacities=[{"element": busiest, "kind": "total_persons", "value": 5}])["evacuation"]
    assert limited["T_s"] >= free["T_s"]
    assert limited["by_exit"].get(busiest, 0) <= 5
