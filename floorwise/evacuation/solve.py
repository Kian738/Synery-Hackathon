"""Exact quickest evacuation: binary search on the horizon, schedule, exit totals, minimum cut."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from floorwise.core.model import OUTSIDE, Building
from floorwise.evacuation.adapter import build_graph
from floorwise.evacuation.ten import (
    KIND_AGG,
    KIND_ELEMENT,
    KIND_SOURCE,
    TO_SINK,
    Problem,
    Solution,
)
from floorwise.evacuation.types import (
    DEFAULT_PARAMS,
    Capacity,
    Evacuation,
    FlowParams,
    Hazard,
    Move,
    Occupants,
)


@dataclass
class Quickest:
    """Smallest horizon (steps) at which the maximum possible number of people is out, plus its flows."""

    steps: int
    solution: Solution | None  # at `steps`; None when nobody can or needs to leave
    infeasible: Solution | None  # at steps - 1: its minimum cut explains T
    free_flow: int
    evacuable: np.ndarray
    possible: int  # persons in spaces with a route at all

    @property
    def evacuated(self) -> int:
        return 0 if self.solution is None else self.solution.value


def quickest(problem: Problem, incumbent_steps: int | None = None) -> Quickest | None:
    """Binary search on the horizon. With incumbent_steps, return None unless a strictly smaller T exists
    and everybody the incumbent evacuated is still evacuated (one max-flow decides)."""
    free, evacuable = problem.free_flow_steps()
    possible = int(problem.occ[evacuable].sum())
    if possible == 0:
        return Quickest(0, None, None, 0, evacuable, 0)
    memo: dict[int, Solution] = {}

    def flow(steps: int) -> Solution:
        if steps not in memo:
            memo[steps] = problem.solve(steps)
        return memo[steps]

    top = problem.steps_max
    if incumbent_steps is not None and (incumbent_steps - 1 < free or flow(incumbent_steps - 1).value < possible):
        return None
    low, high, target = 0, top, possible
    if flow(free).value == possible:
        high = free
    else:
        low, step = free, 1
        while True:
            probe = min(low + step, top)
            if flow(probe).value == possible:
                high = probe
                break
            if probe == top:
                target, low = flow(top).value, 0  # some persons can never make it: aim for everyone who can
                break
            low, step = probe, step * 2
    while high - low > 1:
        middle = (low + high) // 2
        if flow(middle).value == target:
            high = middle
        else:
            low = middle
    return Quickest(high, flow(high), flow(high - 1) if high >= 1 else None, free, evacuable, possible)


def schedule_of(problem: Problem, solution: Solution) -> tuple[Move, ...]:
    """Who crosses which element when. Opposite flows over one element in one step cancel (swapping two
    people is the same as both staying put), so the schedule never has a pointless swap."""
    net, dt = solution.net, problem.params.dt_s
    spaces = problem.graph.spaces
    pending: dict[tuple[str, int, str, str], int] = {}
    for position in np.flatnonzero((net.kind == KIND_ELEMENT) & (solution.flow > 0)):
        arc, when = int(net.arc[position]), int(net.when[position])
        tail, head = int(problem.arc_tail[arc]), int(problem.arc_head[arc])
        key = (problem.arc_element[arc], when, spaces[tail], OUTSIDE if head == TO_SINK else spaces[head])
        pending[key] = pending.get(key, 0) + int(solution.flow[position])
    for key in sorted(pending):
        element, when, source, target = key
        opposite = (element, when, target, source)
        common = min(pending[key], pending.get(opposite, 0))
        if common:
            pending[key] -= common
            pending[opposite] -= common
    taus = {problem.arc_element[a]: int(problem.arc_tau[a]) for a in range(len(problem.arc_tail))}
    moves = [Move(when * dt, element, source, target, persons, (when + taus[element]) * dt)
             for (element, when, source, target), persons in sorted(pending.items(), key=lambda kv: (kv[0][1], kv[0]))
             if persons > 0]
    return tuple(moves)


def bottleneck_of(problem: Problem, infeasible: Solution | None) -> tuple[str, ...]:
    """Elements on the minimum cut (source side = residual reachability) of the last infeasible horizon."""
    if infeasible is None:
        return ()
    net = infeasible.net
    cut = infeasible.reach[net.tail] & ~infeasible.reach[net.head] & (net.cap > 0)
    found: set[str] = set()
    for position in np.flatnonzero(cut):
        kind, arc = int(net.kind[position]), int(net.arc[position])
        if kind == KIND_ELEMENT:
            found.add(problem.arc_element[arc])
        elif kind == KIND_AGG:
            found.update(problem.arc_element[a] for a in np.flatnonzero(problem.arc_agg == arc))
    return tuple(sorted(found))


def assumptions_of(params: FlowParams, occupants_label: str) -> tuple[str, ...]:
    return (
        (f"occupants: {occupants_label}"),
        (f"flow {params.specific_flow} persons/s per metre of effective width, {params.boundary_m} m boundary layer "
        "each side (sweep 1.0 to 1.6); capacity is integer persons per step by cumulative flooring"),
        (f"walking {params.speed_mps} m/s on straight lines anchor -> door -> anchor; every hop rounded up to whole "
        f"{params.dt_s} s steps (T is an upper bound on the continuous-time answer, by less than one step per hop)"),
        (f"stairs: {params.stairs_m_per_m_climbed} m per metre climbed at {params.stairs_speed_factor} x walking speed "
        "(ASSUMPTION, not verified); stairs and lift arcs are not width-limited unless a Capacity is given"),
        "persons start at the anchor of their space; spaces hold any number of people (no density model, no smoke)",
        "lifts are " + ("INCLUDED (assumption)" if params.include_lifts else "excluded from evacuation"),
    )


def evaluate(problem: Problem, occupants_label: str, *, with_ccrp: bool, with_nearest: bool) -> Evacuation:
    best = quickest(problem)
    assert best is not None
    dt = problem.params.dt_s
    spaces = problem.graph.spaces
    by_exit: dict[str, int] = {}
    stranded: dict[str, int] = {}
    moves: tuple[Move, ...] = ()
    if best.solution is not None:
        solution = best.solution
        moves = schedule_of(problem, solution)
        for position in np.flatnonzero((solution.net.kind == KIND_ELEMENT) & (solution.flow > 0)):
            arc = int(solution.net.arc[position])
            if problem.arc_head[arc] == TO_SINK:
                element = problem.arc_element[arc]
                by_exit[element] = by_exit.get(element, 0) + int(solution.flow[position])
    served = np.zeros(problem.n, dtype=np.int64)
    if best.solution is not None:
        net = best.solution.net
        sources = net.kind == KIND_SOURCE
        served[net.arc[sources]] = best.solution.flow[sources]
    for index in np.flatnonzero(problem.occ - served > 0):
        stranded[spaces[int(index)]] = int(problem.occ[index] - served[index])
    cut_off = {spaces[int(i)]: int(problem.occ[i]) for i in np.flatnonzero((problem.occ > 0) & ~best.evacuable)}
    time_limited: tuple[str, ...] = ()
    if best.steps >= 1 and best.solution is not None:
        late = problem.latest(best.steps - 1) < 0
        time_limited = tuple(spaces[int(i)] for i in np.flatnonzero(best.evacuable & late))
    ccrp = nearest = None
    if with_ccrp:
        from floorwise.evacuation.ccrp import ccrp as run_ccrp

        ccrp = run_ccrp(problem)
    if with_nearest:
        from floorwise.evacuation.nearest import nearest_exit

        nearest = nearest_exit(problem)
    return Evacuation(
        T_s=best.steps * dt, total=problem.total, evacuated=best.evacuated, stranded=stranded, cut_off=cut_off,
        free_flow_s=best.free_flow * dt, by_exit=dict(sorted(by_exit.items())), schedule=moves,
        bottleneck=bottleneck_of(problem, best.infeasible), time_limited=time_limited, ccrp=ccrp,
        nearest_exit=nearest, params=problem.params, occupants_label=occupants_label,
        assumptions=assumptions_of(problem.params, occupants_label), skipped_openings=problem.graph.skipped)


def evacuate(building: Building, occupants: Occupants, hazard: Hazard | Sequence[Hazard] | None = None,
             capacities: Sequence[Capacity] = (), params: FlowParams = DEFAULT_PARAMS, *, with_ccrp: bool = True,
             with_nearest: bool = True) -> Evacuation:
    """Exact quickest evacuation of `occupants` to the outside under `hazard` and `capacities`."""
    problem = Problem(build_graph(building, params), occupants.by_space, hazard, capacities, params)
    return evaluate(problem, occupants.label, with_ccrp=with_ccrp, with_nearest=with_nearest)
