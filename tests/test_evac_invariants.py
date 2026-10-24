"""Invariants of the exact solver across real buildings and several generic hazards.

Every check re-derives its reference independently (widths from the building data, replay from the schedule)
instead of reading the solver's own arrays."""

import hashlib
import json
import math
import os
import subprocess
import sys
from functools import cache

import pytest
from evac_support import DT, anchor, door_caps, hazard_cases, real_building, replay

from floorwise.evacuation import (
    Evacuation,
    FlowParams,
    Hazard,
    Occupants,
    best_doors,
    evacuate,
    to_dict,
)
from floorwise.evacuation.adapter import build_graph
from floorwise.evacuation.doors import edited_building
from floorwise.evacuation.solve import quickest
from floorwise.evacuation.ten import Problem

BUILDINGS = ["proc-factory-dev-003", "proc-campus-dev-000", "osm-way27326387", "proc-factory-dev-007"]
SPEED = FlowParams().speed_mps


@cache
def building_of(name):
    return real_building(name)


@cache
def occupants_of(name):
    return Occupants.from_seats(building_of(name))


@cache
def hazards_of(name):
    return hazard_cases(building_of(name), occupants_of(name).by_space)


@cache
def run(name: str, case: str) -> Evacuation:
    return evacuate(building_of(name), occupants_of(name), hazards_of(name)[case])


CASES = [(name, case) for name in BUILDINGS for case in ("none", "fire_room_at_30s", "widest_exit_closed",
                                                          "busy_corridor_at_60s")]


@pytest.fixture(params=CASES, ids=[f"{n}:{c}" for n, c in CASES])
def scenario(request):
    name, case = request.param
    if case not in hazards_of(name):
        pytest.skip("building has no corridor")
    return name, case, run(name, case)


def test_the_dev_buildings_have_enough_variety():
    assert len(BUILDINGS) >= 3 and all(occupants_of(n).total > 20 for n in BUILDINGS)
    assert len({run(n, "none").T_s for n in BUILDINGS}) >= 3


def test_people_are_conserved_and_replay_ends_outside(scenario):
    name, _, result = scenario
    occupants = occupants_of(name)
    assert result.total == occupants.total
    assert result.evacuated + sum(result.stranded.values()) == result.total
    assert sum(result.by_exit.values()) == result.evacuated
    outside, left, _ = replay(occupants.by_space, result.schedule)
    assert outside == result.evacuated
    assert sum(left.values()) == result.total - result.evacuated
    assert sum(result.stranded.values()) == result.total - result.evacuated
    assert set(result.cut_off) <= set(result.stranded)


def test_no_door_carries_more_than_its_width_allows_per_step(scenario):
    name, _, result = scenario
    building = building_of(name)
    steps = result.T_s // DT + 2
    per_arc: dict[tuple, int] = {}
    for move in result.schedule:
        per_arc[(move.element, move.depart_s, move.from_space, move.to_space)] = (
            per_arc.get((move.element, move.depart_s, move.from_space, move.to_space), 0) + move.persons)
        opening = building.openings.get(move.element)
        if opening is not None:
            assert move.persons <= door_caps(opening["width_m"], steps)[move.depart_s // DT]
        assert move.arrive_s > move.depart_s
    assert all(n > 0 for n in per_arc.values())
    # one element, one step: opposite directions never both used (they cancel)
    assert len({(e, t, frozenset((a, b))) for e, t, a, b in per_arc}) == len(per_arc)


def test_hazard_spaces_and_closed_doors_carry_nothing_after_their_block_time(scenario):
    name, case, result = scenario
    hazard = hazards_of(name)[case]
    building = building_of(name)
    if hazard is None:
        return
    for move in result.schedule:
        for space in hazard.spaces:
            assert not (move.from_space == space and move.depart_s >= hazard.from_s)
            assert not (move.to_space == space and move.arrive_s >= hazard.from_s)
        if move.element in hazard.elements:
            opening = building.openings[move.element]
            leg = math.dist(anchor(building, move.from_space), opening["position"]) / SPEED
            assert move.depart_s + leg < hazard.from_s


def test_cut_off_occupants_are_reported_not_dropped():
    name = "proc-factory-dev-003"
    occupants = occupants_of(name)
    crowded = max(occupants.by_space, key=lambda s: (occupants.by_space[s], s))
    result = evacuate(building_of(name), occupants, Hazard(spaces=(crowded,)), with_ccrp=False, with_nearest=False)
    assert result.cut_off == {crowded: occupants.by_space[crowded]}
    assert result.stranded[crowded] == occupants.by_space[crowded]
    assert result.evacuated == occupants.total - occupants.by_space[crowded]
    assert result.total == occupants.total


def test_exact_is_never_slower_than_ccrp_and_free_flow_bounds_both(scenario):
    _, _, result = scenario
    assert result.free_flow_s <= result.T_s or result.evacuated == 0
    if result.ccrp.evacuated == result.evacuated:
        assert result.T_s <= result.ccrp.T_s
    assert result.ccrp.evacuated <= result.evacuated
    if result.nearest_exit.evacuated == result.evacuated:
        assert result.T_s <= result.nearest_exit.T_s
    assert result.nearest_exit.evacuated <= result.evacuated


@pytest.mark.parametrize("name", BUILDINGS)
def test_closing_a_door_never_makes_the_evacuation_better(name):
    base = run(name, "none")
    used: dict[str, int] = {}
    for move in base.schedule:
        used[move.element] = used.get(move.element, 0) + move.persons
    busiest = sorted(used, key=lambda e: (-used[e], e))[:3]
    for element in busiest:
        closed = evacuate(building_of(name), occupants_of(name), Hazard(elements=(element,)),
                          with_ccrp=False, with_nearest=False)
        assert (closed.total - closed.evacuated, closed.T_s) >= (base.total - base.evacuated, base.T_s), element


@pytest.mark.parametrize("name", BUILDINGS)
def test_adding_a_verified_door_never_makes_the_evacuation_worse(name):
    building, occupants = building_of(name), occupants_of(name)
    plan = best_doors(building, occupants, max_fixes=2)
    base = run(name, "none")
    assert plan.T_before_s == base.T_s
    previous = base
    for index, fix in enumerate(plan.fixes):
        assert fix.verified
        edited = edited_building(building, [(f.kind, f.element, f.between, f.position, f.width_m)
                                            for f in plan.fixes[: index + 1]])
        again = evacuate(edited, occupants, with_ccrp=False, with_nearest=False)
        assert again.T_s == fix.T_after_s <= previous.T_s
        assert again.evacuated >= previous.evacuated
        previous = again


@pytest.mark.parametrize("name", BUILDINGS[:3])
def test_replayed_schedule_has_the_same_door_counts_as_the_solver_flows(name):
    """Replay counts per (element, step) come from the schedule; the reference is the raw max-flow solution."""
    building, occupants = building_of(name), occupants_of(name)
    params = FlowParams()
    problem = Problem(build_graph(building, params), occupants.by_space, None, (), params)
    best = quickest(problem)
    result = run(name, "none")
    assert best.steps * DT == result.T_s
    net = best.solution.net
    raw: dict[tuple, int] = {}
    for position in range(len(net.tail)):
        if net.kind[position] == 1 and best.solution.flow[position] > 0:
            arc, when = int(net.arc[position]), int(net.when[position])
            head = int(problem.arc_head[arc])
            key = (problem.arc_element[arc], when * DT, problem.graph.spaces[int(problem.arc_tail[arc])],
                   "outside" if head < 0 else problem.graph.spaces[head])
            raw[key] = raw.get(key, 0) + int(best.solution.flow[position])
    net_flow: dict[tuple, int] = {}
    for (element, when, source, target), persons in raw.items():  # swaps over one element in one step cancel
        sign, pair = (1, (source, target)) if source < target else (-1, (target, source))
        net_flow[(element, when, *pair)] = net_flow.get((element, when, *pair), 0) + sign * persons
    raw = {(e, w, a, b) if n > 0 else (e, w, b, a): abs(n) for (e, w, a, b), n in net_flow.items() if n != 0}
    _, _, counts = replay(occupants.by_space, result.schedule)
    assert counts == raw and len(raw) > 5


def test_output_is_byte_identical_across_runs_and_hash_seeds():
    name = "proc-factory-dev-003"
    local = json.dumps(to_dict(run(name, "fire_room_at_30s")), sort_keys=True)
    again = json.dumps(to_dict(evacuate(building_of(name), occupants_of(name),
                                        hazards_of(name)["fire_room_at_30s"])), sort_keys=True)
    assert local == again
    script = (
        "import json, sys; sys.path.insert(0, 'tests');"
        "from evac_support import real_building, hazard_cases;"
        "from floorwise.evacuation import Occupants, evacuate, to_dict;"
        f"b = real_building({name!r}); o = Occupants.from_seats(b);"
        "h = hazard_cases(b, o.by_space)['fire_room_at_30s'];"
        "print(json.dumps(to_dict(evacuate(b, o, h)), sort_keys=True))"
    )
    other = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True,
                           env={**os.environ, "PYTHONHASHSEED": "12345"}).stdout.strip()
    assert hashlib.sha256(other.encode()).hexdigest() == hashlib.sha256(local.encode()).hexdigest()
    assert len(local) > 5000


def test_dt_sweep_and_flow_band_move_the_answer_in_the_right_direction():
    name = "proc-campus-dev-000"
    building, occupants = building_of(name), occupants_of(name)
    times = {}
    for specific in (1.0, 1.316, 1.6):
        times[specific] = evacuate(building, occupants, params=FlowParams(specific_flow=specific),
                                   with_ccrp=False, with_nearest=False).T_s
    assert times[1.0] >= times[1.316] >= times[1.6] and times[1.0] > times[1.6]


def test_heuristics_lose_to_the_optimum_somewhere_and_never_win():
    """Measured, deterministic: nearest-exit and CCRP are strictly worse on at least one building each."""
    rows = {name: run(name, "none") for name in BUILDINGS}
    assert any(r.nearest_exit.T_s > r.T_s for r in rows.values())
    assert any(r.ccrp.T_s > r.T_s for r in rows.values())
    assert all(r.T_s <= r.ccrp.T_s and r.T_s <= r.nearest_exit.T_s for r in rows.values())


@pytest.mark.parametrize("name", ["proc-campus-dev-000", "osm-way27326387"])
def test_coarse_steps_round_up_so_they_never_report_less_than_fine_steps(name):
    """Measured on these buildings, not a theorem: every hop is rounded up to whole steps."""
    building, occupants = building_of(name), occupants_of(name)
    times = [evacuate(building, occupants, params=FlowParams(dt_s=dt), with_ccrp=False, with_nearest=False).T_s
             for dt in (1, 5, 10)]
    assert times[0] <= times[1] <= times[2] and times[0] < times[2]
