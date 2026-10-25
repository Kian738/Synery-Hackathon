"""Properties that must hold on every building, whatever the numbers: they catch what example tests cannot.

monotone     adding a door never lengthens a route; closing a connector never shortens one
undo         an edit followed by undo gives back exactly the same lengths
step-free    a step-free route is never shorter than the unconstrained one
symmetry     the way there and the way back have the same length
triangle     going via a third room is never shorter than going direct"""
import itertools
import random

import pytest

from eval.common import building_paths
from floorwise.agent.session import Session
from floorwise.core.geometry import wall_neighbours
from floorwise.core.graph import Constraints
from floorwise.core.model import Building
from floorwise.core.routing import NoRoute, plan_route

NAMES = ["proc-factory-dev-003", "proc-campus-dev-000", "swiss-1785", "swiss-460", "resplan-15793", "osm-way61408163"]


def load(name: str) -> Building:
    return Building.load(next(p for p in building_paths(["train", "dev", "test"]) if p.parent.name == name).parent)


def length(building: Building, stops, constraints=Constraints()):
    try:
        return plan_route(building, list(stops), constraints).length_m
    except NoRoute:
        return None


def pairs(building: Building, seed: str, count: int):
    rooms = sorted(s for s, v in building.spaces.items() if v["type"] == "room")
    rng = random.Random(seed)
    return [tuple(rng.sample(rooms, 2)) for _ in range(count)] if len(rooms) > 3 else []


@pytest.mark.parametrize("name", NAMES)
def test_symmetry_triangle_and_step_free(name):
    b = load(name)
    for a, c in pairs(b, name, 10):
        ab, ba = length(b, [a, c]), length(b, [c, a])
        assert (ab is None) == (ba is None) and (ab is None or abs(ab - ba) <= 0.021), (a, c, ab, ba)  # legs are summed rounded, so 0.01 m may differ
        sf = length(b, [a, c], Constraints(step_free=True))
        if ab is not None and sf is not None:
            assert sf >= ab - 1e-6
        if ab is None:
            assert sf is None
    for a, m, c in [tuple(random.Random(name + str(i)).sample(sorted(b.spaces), 3)) for i in range(6)]:
        if any(b.spaces[x]["type"] != "room" for x in (a, m, c)):
            continue
        direct, via = length(b, [a, c]), length(b, [a, m, c])
        if direct is not None and via is not None:
            assert via >= direct - 1e-6


@pytest.mark.parametrize("name", NAMES[:4])
def test_a_new_door_never_lengthens_and_undo_restores(name):
    session = Session.for_building(load(name))
    b = session.building
    joined = {frozenset(o["space_ids"]) for o in b.openings.values()}
    candidates = [(s, o) for s, v in sorted(b.spaces.items()) if v["type"] == "room" for o, _ in wall_neighbours(b, s)
                  if b.spaces[o]["type"] == "room" and frozenset((s, o)) not in joined]
    if not candidates:
        pytest.skip("no doorless neighbours")
    probes = pairs(b, name + "d", 12)
    before = [length(b, p) for p in probes]
    for first, second in candidates[:3]:
        result = session.add_door(b.spaces[first]["name"] + " (" + b.floor_name(b.spaces[first]["floor_id"]) + ")", b.spaces[second]["name"] + " (" + b.floor_name(b.spaces[second]["floor_id"]) + ")")
        if "error" in result:
            continue
        after = [length(session.building, p) for p in probes]
        for old, new in zip(before, after):
            assert (old is None) or (new is not None and new <= old + 1e-6)
        session.undo()
        assert [length(session.building, p) for p in probes] == before


@pytest.mark.parametrize("name", NAMES[:4])
def test_closing_never_shortens_and_reopening_restores(name):
    b = load(name)
    probes = pairs(b, name + "c", 12)
    base = [length(b, p) for p in probes]
    for connector in itertools.islice(sorted(b.connectors), 4):
        closed = Constraints(closed=frozenset({connector}))
        for old, p in zip(base, probes):
            new = length(b, p, closed)
            if old is None:
                assert new is None
            elif new is not None:
                assert new >= old - 1e-6
        assert [length(b, p) for p in probes] == base
