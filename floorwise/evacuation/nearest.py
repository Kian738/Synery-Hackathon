"""Nearest-exit baseline: every space sends everybody to the exit that is individually closest in walking
time, along that shortest route, ignoring what everybody else does. Doors still queue (same capacities)."""

import heapq
import math

from floorwise.evacuation.ten import TO_SINK, Problem
from floorwise.evacuation.types import Baseline


def next_hops(problem: Problem) -> dict[int, int]:
    """space -> arc to take, by reverse Dijkstra in continuous walking seconds (ties: lowest arc index).
    Spaces blocked from the start and arcs that never open are left out."""
    distance: dict[int, float] = {}
    hop: dict[int, int] = {}
    heap: list[tuple[float, int]] = []
    for arc in range(len(problem.arc_tail)):
        tail = int(problem.arc_tail[arc])
        if problem.arc_head[arc] == TO_SINK and problem.alive_until[tail] > 0:
            seconds = problem.arc_seconds[arc]
            if seconds < distance.get(tail, math.inf) - 1e-12:
                distance[tail], hop[tail] = seconds, arc
                heapq.heappush(heap, (seconds, tail))
    while heap:
        seconds, node = heapq.heappop(heap)
        if distance[node] < seconds:
            continue
        for arc in problem.in_arcs[node]:
            tail = int(problem.arc_tail[arc])
            candidate = seconds + problem.arc_seconds[arc]
            if problem.alive_until[tail] > 0 and candidate < distance.get(tail, math.inf) - 1e-12:
                distance[tail], hop[tail] = candidate, arc
                heapq.heappush(heap, (candidate, tail))
    return hop


def nearest_exit(problem: Problem) -> Baseline:
    hop = next_hops(problem)
    waiting = {int(s): int(problem.occ[s]) for s in range(problem.n) if problem.occ[s] > 0}
    landing: dict[int, list[tuple[int, int]]] = {}
    by_exit: dict[str, int] = {}
    exit_left = list(problem.agg_total)  # persons an exit with a total cap can still take
    evacuated = last_arrival = 0
    for step in range(problem.steps_max):
        for space, count in sorted(landing.pop(step, ())):
            waiting[space] = waiting.get(space, 0) + count
        for space in sorted(waiting):
            if step >= problem.alive_until[space]:
                waiting[space] = 0  # the space became impassable with people still in it
            elif space in hop and waiting[space] > 0:
                arc = hop[space]
                moved = min(waiting[space], int(problem.arc_cap[arc, step]))
                capped = int(problem.arc_agg[arc])
                if capped >= 0:
                    moved = min(moved, exit_left[capped])
                    exit_left[capped] -= moved
                if moved == 0:
                    continue
                waiting[space] -= moved
                land = step + int(problem.arc_tau[arc])
                if problem.arc_head[arc] == TO_SINK:
                    element = problem.arc_element[arc]
                    by_exit[element] = by_exit.get(element, 0) + moved
                    evacuated += moved
                    last_arrival = max(last_arrival, land)
                else:
                    landing.setdefault(land, []).append((int(problem.arc_head[arc]), moved))
        waiting = {s: c for s, c in waiting.items() if c > 0}
        if not waiting and not landing:
            break
    return Baseline("nearest_exit", last_arrival * problem.params.dt_s, evacuated, dict(sorted(by_exit.items())))
