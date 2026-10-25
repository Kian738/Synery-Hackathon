"""Where to add or widen a door.

Candidates: new doors between same-floor spaces that share >= 1 m of wall (floorwise.core.geometry), and widening
of existing openings. A change can only raise the max-flow of the last infeasible horizon if it touches that
network's minimum cut (max-flow min-cut theorem), so candidates are pruned by the cut. Survivors are re-solved
exactly, the largest drop in evacuation time is applied, and the loop repeats (greedy: adding doors to a flow
network is NP-hard, so the sequence is not claimed optimal). Every fix is finally re-checked by a fresh solve on
an edited copy of the building that shares no state with the search.
"""

import copy
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from floorwise.core import geometry
from floorwise.core.model import Building
from floorwise.evacuation.adapter import CapacityGraph, build_graph, door_element
from floorwise.evacuation.solve import Quickest, bottleneck_of, evacuate, quickest
from floorwise.evacuation.ten import Problem, hazard_blocks, hop_steps
from floorwise.evacuation.types import (
    DEFAULT_PARAMS,
    Capacity,
    FlowParams,
    Hazard,
    Occupants,
)

NEW_DOOR_WIDTH_M = 0.9  # a single-leaf door, the width the Session door preview uses
WIDENED_TO_M = 1.8  # a double-leaf door; ASSUMPTION, both are parameters
Edit = tuple[str, str, tuple[str, str], tuple[float, float] | None, float]  # kind, element, between, position, width


@dataclass(frozen=True)
class DoorFix:
    kind: Literal["add", "widen"]
    element: str  # the opening id (existing for widen, "new:<a>|<b>" for add)
    between: tuple[str, str]
    position: tuple[float, float] | None
    width_m: float
    previous_width_m: float | None
    T_before_s: int  # evacuation time before this fix (after the earlier ones)
    T_after_s: int
    evacuated_before: int
    evacuated_after: int
    verified: bool  # an independent solve on an edited copy of the building gave the same T and evacuated count


@dataclass(frozen=True)
class DoorPlan:
    T_before_s: int
    T_after_s: int
    evacuated_before: int
    evacuated_after: int
    fixes: tuple[DoorFix, ...]
    candidates: int  # candidates generated, summed over greedy rounds
    crossing_cut: int  # of those, the ones the minimum cut did not rule out
    evaluated: int  # exact re-solves actually run
    new_width_m: float
    widen_to_m: float
    complete: bool = True  # False when the time budget stopped the search before every candidate was checked


@dataclass(frozen=True)
class Candidate:
    kind: Literal["add", "widen"]
    element: str
    between: tuple[str, str]
    position: tuple[float, float] | None
    width_m: float
    previous_width_m: float | None

    @property
    def edit(self) -> Edit:
        return (self.kind, self.element, self.between, self.position, self.width_m)

    @property
    def added_width_m(self) -> float:
        return self.width_m - (self.previous_width_m or 0.0)


def edited_building(building: Building, edits: Sequence[Edit]) -> Building:
    """A deep copy with the doors added or widened; the input is untouched."""
    data = copy.deepcopy(building.data)
    for kind, element, between, position, width in edits:
        if kind == "add":
            floor_id = building.spaces[between[0]]["floor_id"]
            data["openings"].append({
                "id": element, "floor_id": floor_id, "space_ids": list(between), "kind": "door",
                "position": list(position), "width_m": width, "step_free": True, "synthetic": True})
        else:
            for opening in data["openings"]:
                if opening["id"] == element:
                    opening["width_m"] = width
    return Building(data, building.directory)


def _apply(graph: CapacityGraph, candidate: Candidate) -> CapacityGraph:
    if candidate.kind == "widen":
        return graph.with_width(candidate.element, candidate.width_m)
    first, second = candidate.between
    opening = {"id": candidate.element, "floor_id": None, "space_ids": [first, second], "kind": "door",
               "position": list(candidate.position), "width_m": candidate.width_m, "step_free": True}
    element = door_element(opening, graph.anchors)
    assert element is not None
    return graph.with_element(element)


def wall_pairs(building: Building, graph: CapacityGraph, excluded: set[str]) -> list[tuple[str, str, tuple[float, float]]]:
    """Same-floor pairs sharing >= 1 m of wall, with the wall midpoint; no stair, lift or excluded spaces."""
    eligible = [s for s in graph.spaces if s not in excluded and building.spaces[s]["type"] not in ("stair", "lift")]
    allowed = set(eligible)
    pairs = []
    for first in eligible:
        for second, _ in geometry.wall_neighbours(building, first):
            if first < second and second in allowed:
                midpoint = geometry.wall_midpoint(building, first, second)
                if midpoint is not None:
                    pairs.append((first, second, (round(midpoint[0], 3), round(midpoint[1], 3))))
    return sorted(pairs)


def candidates_for(graph: CapacityGraph, pairs: list[tuple[str, str, tuple[float, float]]], new_width_m: float,
                   widen_to_m: float) -> list[Candidate]:
    connected = {frozenset((e.a, e.b)) for e in graph.elements}
    found = [Candidate("add", f"new:{a}|{b}", (a, b), position, new_width_m, None)
             for a, b, position in pairs if frozenset((a, b)) not in connected]
    found += [Candidate("widen", e.id, (e.a, e.b), e.position, widen_to_m, e.width_m)
              for e in graph.elements if e.width_m is not None and e.width_m < widen_to_m]
    return found


def _crosses(candidate: Candidate, graph: CapacityGraph, problem: Problem, cuts: list[tuple[set[str], np.ndarray]],
             params: FlowParams) -> bool:
    """Could this change touch the minimum cut of any of the networks in `cuts`?"""
    for cut_ids, mask in cuts:
        if candidate.kind == "widen":
            if candidate.element in cut_ids:
                return True
            continue
        element = _apply(graph, candidate).element(candidate.element)
        tau, horizon = hop_steps(element, params), mask.shape[0] - 1
        for tail, head in ((element.a, element.b), (element.b, element.a)):
            i, j = problem.index[tail], problem.index[head]
            when = np.arange(max(horizon - tau + 1, 0))
            if when.size and (mask[when, i] & ~mask[when + tau, j] & (when + tau < problem.alive_until[j])).any():
                return True
    return False


def _cuts(problem: Problem, current: Quickest) -> list[tuple[set[str], np.ndarray]]:
    solutions = [current.infeasible] if current.infeasible is not None else []
    if current.evacuated < problem.total:  # someone is out of reach: a door may rescue them, not just speed T up
        solutions.append(problem.solve(problem.steps_max))
    cuts = []
    for solution in solutions:
        steps, n = solution.net.steps, problem.n
        mask = solution.reach[: n * (steps + 1)].reshape(steps + 1, n)
        cuts.append((set(bottleneck_of(problem, solution)), mask))
    return cuts


def best_doors(building: Building, occupants: Occupants, hazard: Hazard | Sequence[Hazard] | None = None,
               capacities: Sequence[Capacity] = (), params: FlowParams = DEFAULT_PARAMS, *, max_fixes: int = 3,
               new_width_m: float = NEW_DOOR_WIDTH_M, budget_s: float | None = None, widen_to_m: float = WIDENED_TO_M) -> DoorPlan:
    started = time.perf_counter()
    graph = build_graph(building, params)
    dt = params.dt_s
    blocked_spaces, _ = hazard_blocks(hazard)

    def problem_of(g: CapacityGraph) -> Problem:
        return Problem(g, occupants.by_space, hazard, capacities, params)

    first_problem = problem_of(graph)
    current = quickest(first_problem)
    assert current is not None
    start = current
    pairs = wall_pairs(building, graph, set(blocked_spaces))
    chosen: list[tuple[Candidate, Quickest, Quickest]] = []  # (candidate, quickest before, quickest after)
    total = crossing = evaluated = 0
    incomplete = False
    for _ in range(max_fixes):
        problem = first_problem if not chosen else problem_of(graph)
        pool = candidates_for(graph, pairs, new_width_m, widen_to_m)
        cuts = _cuts(problem, current)
        survivors = [c for c in pool if _crosses(c, graph, problem, cuts, params)]
        total, crossing = total + len(pool), crossing + len(survivors)
        best: tuple[tuple[int, int], float, str, Candidate, Quickest] | None = None
        # The score is (people out, then time). Only candidates that let the most people leave can win, and a cheap count
        # finds them before any max-flow runs. Among those, the best time so far bounds every later search to one max-flow
        # (steps + 1, so an equal time still reaches the tie-break on added width and nothing else changes).
        prepared = []
        for candidate in survivors:
            candidate_problem = problem_of(_apply(graph, candidate))
            prepared.append((int(candidate_problem.occ[candidate_problem.evacuable()].sum()), candidate, candidate_problem))
        most = max([current.evacuated] + [reachable for reachable, _, _ in prepared])
        prepared.sort(key=lambda item: -item[1].added_width_m)  # widest first: the likeliest wins are found before a time budget runs out
        for reachable, candidate, candidate_problem in prepared:
            if reachable < most:
                continue
            if budget_s is not None and evaluated and time.perf_counter() - started > budget_s:
                incomplete = True
                break
            if best is not None:
                bound = best[4].steps + 1
            else:
                bound = current.steps if reachable == current.evacuated else None
            after = quickest(candidate_problem, bound)
            evaluated += 1
            if after is None:
                continue
            score = (-after.evacuated, after.steps)
            if score >= (-current.evacuated, current.steps):
                continue
            key = (score, candidate.added_width_m, candidate.element)
            if best is None or key < best[:3]:
                best = (*key, candidate, after)
        if best is None:
            break
        chosen.append((best[3], current, best[4]))
        graph, current = _apply(graph, best[3]), best[4]
    fixes = []
    for index, (candidate, before, after) in enumerate(chosen):
        edited = edited_building(building, [c.edit for c, _, _ in chosen[: index + 1]])
        check = evacuate(edited, occupants, hazard, capacities, params, with_ccrp=False, with_nearest=False)
        fixes.append(DoorFix(candidate.kind, candidate.element, candidate.between, candidate.position,
                             candidate.width_m, candidate.previous_width_m, before.steps * dt, after.steps * dt,
                             before.evacuated, after.evacuated,
                             check.T_s == after.steps * dt and check.evacuated == after.evacuated))
    return DoorPlan(start.steps * dt, current.steps * dt, start.evacuated, current.evacuated, tuple(fixes), total,
                    crossing, evaluated, new_width_m, widen_to_m, not incomplete)
