"""Shared helpers for the evacuation tests: tiny hand-made buildings and the real dev buildings."""

import math
from pathlib import Path

from shapely.geometry import Polygon

from floorwise.core.model import Building
from floorwise.paths import DATA

DT = 5


def rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def make_building(
    spaces: dict[str, tuple[float, float, float, float]],
    openings: list[tuple[str, str, str, float, tuple[float, float]]],
    seats: dict[str, int] | None = None,
) -> Building:
    """One floor. openings = (id, space_a, space_b ('outside' allowed), width_m, (x, y))."""
    data = {
        "building": {"id": "tiny"},
        "floors": [{"id": "F0", "level": 0, "name": "Ground", "elevation_m": 0.0, "height_m": 3.0}],
        "spaces": [
            {"id": sid, "floor_id": "F0", "type": "room", "room_type": "office", "name": sid, "ref": sid,
             "polygon": rect(*box), "synthetic": False}
            for sid, box in spaces.items()
        ],
        "openings": [
            {"id": oid, "floor_id": "F0", "space_ids": [a, b], "kind": "entrance" if "outside" in (a, b) else "door",
             "position": list(pos), "width_m": width, "step_free": True, "synthetic": False}
            for oid, a, b, width, pos in openings
        ],
        "vertical_connectors": [],
        "assets": [
            {"id": f"A{sid}{i}", "name": "chair", "category": "furniture", "type": "chair", "space_id": sid,
             "floor_id": "F0", "position": [0, 0], "footprint": {}, "source": "generated"}
            for sid, count in (seats or {}).items() for i in range(count)
        ],
    }
    return Building(data)


def anchor(building: Building, space_id: str) -> tuple[float, float]:
    point = Polygon(building.spaces[space_id]["polygon"]).representative_point()
    return (point.x, point.y)


def hop_steps(building: Building, space_a: str, space_b: str, position: tuple[float, float], speed: float = 1.34) -> int:
    """Independent re-derivation of one door crossing time in whole steps (outside has no anchor)."""
    legs = sum(math.dist(anchor(building, s), position) for s in (space_a, space_b) if s != "outside")
    return max(1, math.ceil(legs / speed / DT - 1e-9))


def door_caps(width_m: float, steps: int, specific_flow: float = 1.316, boundary_m: float = 0.15) -> list[int]:
    """Independent re-derivation of integer persons per step: cumulative floor of rate * time."""
    rate = specific_flow * max(width_m - 2 * boundary_m, 0.0)
    cumulative = [math.floor(rate * DT * (k + 1) + 1e-9) for k in range(steps)]
    return [cumulative[0]] + [cumulative[k] - cumulative[k - 1] for k in range(1, steps)]


def real_building(name: str) -> Building:
    for split in ("dev", "train"):
        path: Path = DATA / split / name
        if path.exists():
            return Building.load(path)
    raise FileNotFoundError(name)


def replay(occupants: dict[str, int], moves, dt: int = DT):
    """Play a schedule forward in time. Returns (persons outside, occupancy at the end, {(element, depart_s, from, to): n}).
    Fails loudly if anybody leaves a space they are not in."""
    occupancy = dict(occupants)
    outside = 0
    counts: dict[tuple, int] = {}
    timeline = sorted({m.depart_s for m in moves} | {m.arrive_s for m in moves})
    for now in timeline:
        for m in moves:
            if m.arrive_s == now:
                if m.to_space == "outside":
                    outside += m.persons
                else:
                    occupancy[m.to_space] = occupancy.get(m.to_space, 0) + m.persons
        for m in moves:
            if m.depart_s == now:
                have = occupancy.get(m.from_space, 0)
                assert have >= m.persons, f"{m.persons} leave {m.from_space} at {now}s but only {have} are there"
                occupancy[m.from_space] = have - m.persons
                key = (m.element, m.depart_s, m.from_space, m.to_space)
                counts[key] = counts.get(key, 0) + m.persons
    return outside, {s: n for s, n in occupancy.items() if n}, counts


def hazard_cases(building: Building, occupants: dict[str, int]) -> dict[str, "object"]:
    """Generic hazards derived from the data, no names: the most crowded room, the widest exit, a busy corridor."""
    from floorwise.evacuation import Hazard

    crowded = max(occupants, key=lambda s: (occupants[s], s))
    exits = sorted((o for o in building.openings.values() if "outside" in o["space_ids"]),
                   key=lambda o: (-o["width_m"], o["id"]))
    hubs = sorted((s for s in building.spaces if building.spaces[s]["type"] == "corridor"),
                  key=lambda s: (-sum(s in o["space_ids"] for o in building.openings.values()), s))
    cases = {"none": None, "fire_room_at_30s": Hazard(spaces=(crowded,), from_s=30.0),
             "widest_exit_closed": Hazard(elements=(exits[0]["id"],))}
    if hubs:
        cases["busy_corridor_at_60s"] = Hazard(spaces=(hubs[0],), from_s=60.0)
    return cases
