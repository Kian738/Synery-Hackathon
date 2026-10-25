"""Responders: reserve-then-route.

For every usable entrance, enumerate the k shortest hazard-free routes to the target. A route reserves each
element it crosses for the window in which the team passes; reserved elements run at half effective width in
both directions (counterflow, conservative). Evacuees are re-solved exactly on the reduced capacities and the
candidate with the smallest evacuation time wins, subject to an optional arrival deadline.
The joint problem (responders and evacuees as two commodities over time) is NP-hard; this is exact over the
enumerated candidates only.
"""

import itertools
import time
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import networkx as nx

from floorwise.core.model import Building
from floorwise.evacuation.adapter import CapacityGraph, Element, build_graph
from floorwise.evacuation.solve import evaluate, quickest
from floorwise.evacuation.ten import Problem, element_rate, hazard_blocks
from floorwise.evacuation.types import (
    DEFAULT_PARAMS,
    Capacity,
    Evacuation,
    FlowParams,
    Hazard,
    Occupants,
)


@dataclass(frozen=True)
class Responders:
    target: str  # space id the team must reach
    entrances: tuple[str, ...] | None = None  # opening ids touching outside; None = every usable one
    team_size: int = 2  # persons; sets how long a team occupies each door it passes
    dispatch_s: float = 0.0  # time the team reaches the entrance
    deadline_s: float | None = None  # latest acceptable arrival at the target
    k_routes: int = 3  # shortest simple routes per entrance
    max_candidates: int = 12  # evacuation re-solves are capped to the earliest-arriving candidates
    budget_s: float | None = None  # compute time after which no further candidate is re-solved (at least one always is)


@dataclass(frozen=True)
class Reservation:
    element: str
    from_s: float
    to_s: float


@dataclass(frozen=True)
class RouteCandidate:
    entrance: str
    spaces: tuple[str, ...]  # from the entrance's inside space to the target
    elements: tuple[str, ...]  # entrance first, then every element crossed
    arrival_s: float  # at the target's boundary (its door), not inside it
    reservations: tuple[Reservation, ...]
    status: Literal["chosen", "evaluated", "not_better", "over_deadline", "not_evaluated"]
    evacuation_T_s: int | None  # None unless evaluated exactly; not_better means >= the chosen T
    evacuated: int | None


@dataclass(frozen=True)
class ResponderPlan:
    status: Literal["ok", "no_route", "deadline_unmet"]
    chosen: RouteCandidate | None
    candidates: tuple[RouteCandidate, ...]
    T_without_s: int
    T_with_s: int | None
    delay_s: int | None
    evacuation: Evacuation | None  # the evacuation with the chosen reservations in place
    baseline: Evacuation  # the evacuation without responders


def _route_graph(graph: CapacityGraph, params: FlowParams, banned_spaces: set[str], banned_elements: set[str],
                 target: str) -> nx.Graph:
    """Spaces and elements as nodes; edge weight = walking seconds on that side. Entering the target through a
    door costs nothing: the team has arrived at its boundary."""
    route = nx.Graph()
    for element in graph.elements:
        if element.is_exit or element.family in banned_elements:
            continue
        for space, leg in ((element.a, element.leg_a_m), (element.b, element.leg_b_m)):
            if space in banned_spaces:
                continue
            if element.width_m is None:  # connector: the whole ride is paid on entering the far side
                weight = element.length_m / (params.speed_mps * element.speed_factor) if space == element.b else 0.0
            else:
                weight = 0.0 if space == target else leg / params.speed_mps
            route.add_edge(("s", space), ("e", element.id), weight=weight)
    return route


def _walk(graph: CapacityGraph, params: FlowParams, entrance: Element, path: Sequence[tuple[str, str]],
          dispatch_s: float) -> tuple[float, list[tuple[str, float]]]:
    """(arrival_s, [(element, time the team reaches it)]) for entrance followed by path = [(space, element), ...]."""
    speed = params.speed_mps
    clock = dispatch_s
    crossings = [(entrance.id, clock)]
    clock += entrance.leg_a_m / speed
    arrival = clock
    for space, element_id in path:
        element = graph.element(element_id)
        if element.width_m is None:
            crossings.append((element_id, clock))
            clock += element.length_m / (speed * element.speed_factor)
            arrival = clock
            continue
        leg = element.leg_a_m if element.a == space else element.leg_b_m
        reach = clock + leg / speed
        crossings.append((element_id, reach))
        arrival = reach
        far = element.leg_b_m if element.a == space else element.leg_a_m
        clock = reach + far / speed
    return arrival, crossings


def enumerate_routes(graph: CapacityGraph, params: FlowParams, hazard: Hazard | Sequence[Hazard] | None,
                     responders: Responders) -> list[RouteCandidate]:
    space_block, element_block = hazard_blocks(hazard)
    if responders.target not in graph.spaces:
        raise ValueError(f"unknown target space {responders.target!r}")
    banned_spaces = set(space_block) - {responders.target}
    banned_elements = set(element_block)
    route = _route_graph(graph, params, banned_spaces, banned_elements, responders.target)
    wanted = None if responders.entrances is None else set(responders.entrances)
    if wanted is not None:
        unknown = sorted(wanted - {e.id for e in graph.exits})
        if unknown:
            raise ValueError(f"not entrances (openings touching outside): {unknown}")
    found: list[RouteCandidate] = []
    for entrance in graph.exits:
        if (wanted is not None and entrance.id not in wanted) or entrance.family in banned_elements:
            continue
        inside = entrance.a
        if inside in banned_spaces:
            continue
        if inside == responders.target:
            node_paths: list[list] = [[("s", inside)]]
        elif ("s", inside) in route and ("s", responders.target) in route:
            try:
                node_paths = list(itertools.islice(
                    nx.shortest_simple_paths(route, ("s", inside), ("s", responders.target), weight="weight"),
                    responders.k_routes))
            except nx.NetworkXNoPath:
                node_paths = []
        else:
            node_paths = []
        for nodes in node_paths:
            spaces = tuple(name for kind, name in nodes if kind == "s")
            elements = [name for kind, name in nodes if kind == "e"]
            steps = list(zip(spaces[:-1], elements, strict=True))
            arrival, crossings = _walk(graph, params, entrance, steps, responders.dispatch_s)
            reservations = []
            for element_id, reach in crossings:
                rate = element_rate(graph.element(element_id), params)
                hold = params.dt_s if math.isinf(rate) or rate <= 0 else max(
                    float(params.dt_s), responders.team_size / (0.5 * rate))
                reservations.append(Reservation(element_id, round(reach, 3), round(reach + hold, 3)))
            found.append(RouteCandidate(entrance.id, spaces, (entrance.id, *elements), round(arrival, 3),
                                        tuple(reservations), "not_evaluated", None, None))
    return sorted(found, key=lambda c: (c.arrival_s, c.entrance, c.elements))


def with_responders(building: Building, occupants: Occupants, hazard: Hazard | Sequence[Hazard] | None = None,
                    capacities: Sequence[Capacity] = (), params: FlowParams = DEFAULT_PARAMS, *,
                    responders: Responders) -> ResponderPlan:
    graph = build_graph(building, params)
    baseline_problem = Problem(graph, occupants.by_space, hazard, capacities, params)
    baseline = evaluate(baseline_problem, occupants.label, with_ccrp=False, with_nearest=False)
    candidates = enumerate_routes(graph, params, hazard, responders)
    if not candidates:
        return ResponderPlan("no_route", None, (), baseline.T_s, None, None, None, baseline)
    deadline = responders.deadline_s
    results: dict[int, RouteCandidate] = {}
    best: tuple[int, int, Problem] | None = None  # (-evacuated, steps, problem)
    best_index = -1
    evaluated = 0
    started = time.perf_counter()
    for index, candidate in enumerate(candidates):
        if deadline is not None and candidate.arrival_s > deadline:
            results[index] = _with(candidate, "over_deadline")
            continue
        if evaluated >= responders.max_candidates:
            continue
        if responders.budget_s is not None and evaluated and time.perf_counter() - started > responders.budget_s:
            continue
        evaluated += 1
        reservations: dict[str, list[tuple[float, float]]] = {}
        for item in candidate.reservations:
            reservations.setdefault(item.element, []).append((item.from_s, item.to_s))
        problem = Problem(graph, occupants.by_space, hazard, capacities, params, reservations)
        incumbent = None
        if best is not None and baseline.evacuated == baseline.total - sum(baseline.cut_off.values()):
            incumbent = best[1]
        found = quickest(problem, incumbent_steps=incumbent)
        if found is None:
            results[index] = _with(candidate, "not_better")
            continue
        score = (-found.evacuated, found.steps)
        results[index] = _with(candidate, "evaluated", found.steps * params.dt_s, found.evacuated)
        if best is None or score < best[:2]:
            best, best_index = (score[0], score[1], problem), index
    plan_candidates = tuple(results.get(i, candidates[i]) for i in range(len(candidates)))
    if best is None:
        return ResponderPlan("deadline_unmet", None, plan_candidates, baseline.T_s, None, None, None, baseline)
    chosen = _with(candidates[best_index], "chosen", results[best_index].evacuation_T_s, results[best_index].evacuated)
    plan_candidates = tuple(chosen if i == best_index else c for i, c in enumerate(plan_candidates))
    final = evaluate(best[2], occupants.label, with_ccrp=False, with_nearest=False)
    return ResponderPlan("ok", chosen, plan_candidates, baseline.T_s, final.T_s, final.T_s - baseline.T_s, final,
                         baseline)


def _with(candidate: RouteCandidate, status: str, evacuation_T_s: int | None = None,
          evacuated: int | None = None) -> RouteCandidate:
    return RouteCandidate(candidate.entrance, candidate.spaces, candidate.elements, candidate.arrival_s,
                          candidate.reservations, status, evacuation_T_s, evacuated)  # type: ignore[arg-type]
