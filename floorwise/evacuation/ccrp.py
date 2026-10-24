"""CCRP, the Capacity Constrained Route Planner (Lu, George, Shekhar): repeatedly send flow along the
earliest-arrival route over the time-expanded capacities that earlier routes left, reserve it, repeat.
Heuristic: it never reroutes flow it has already placed, so it can only match or lose to the exact optimum."""

import heapq
import math

import numpy as np

from floorwise.evacuation.ten import TO_SINK, Problem
from floorwise.evacuation.types import Baseline


def _next_open(residual: np.ndarray) -> np.ndarray:
    """Per arc and step t: first step >= t with residual capacity (len(row) if none)."""
    steps = residual.shape[1]
    marks = np.where(residual > 0, np.arange(steps)[None, :], steps)
    return np.minimum.accumulate(marks[:, ::-1], axis=1)[:, ::-1]


def ccrp(problem: Problem) -> Baseline:
    n, top = problem.n, problem.steps_max
    residual = problem.arc_cap.copy()
    first_open = _next_open(residual)
    tails, heads, taus = problem.arc_tail.tolist(), problem.arc_head.tolist(), problem.arc_tau.tolist()
    aggs, alive = problem.arc_agg.tolist(), problem.alive_until.tolist()
    agg_left = list(problem.agg_total)
    remaining = problem.occ.tolist()
    by_exit: dict[str, int] = {}
    last_arrival = sent = 0
    sink = n
    while any(remaining):
        arrival: dict[int, int] = {}
        via: dict[int, tuple[int, int]] = {}  # node -> (arc, departure step)
        heap: list[tuple[int, int]] = []
        for origin in range(n):
            if remaining[origin] > 0 and alive[origin] > 0:
                arrival[origin] = 0
                heap.append((0, origin))
        heapq.heapify(heap)
        while heap:
            at, node = heapq.heappop(heap)
            if node == sink:
                break
            if arrival.get(node, math.inf) < at:
                continue
            last = min(alive[node], top)
            for arc in problem.out_arcs[node]:
                if at >= last:
                    break
                depart = int(first_open[arc, at])
                if depart >= last or (aggs[arc] >= 0 and agg_left[aggs[arc]] <= 0):
                    continue
                head, land = heads[arc], depart + taus[arc]
                if land > top or (head != TO_SINK and land >= alive[head]):
                    continue
                head = sink if head == TO_SINK else head
                if land < arrival.get(head, math.inf):
                    arrival[head] = land
                    via[head] = (arc, depart)
                    heapq.heappush(heap, (land, head))
        if sink not in arrival:
            break
        path, node = [], sink
        while node in via:
            arc, depart = via[node]
            path.append((arc, depart))
            node = tails[arc]
        amount = remaining[node]
        for arc, depart in path:
            amount = min(amount, int(residual[arc, depart]))
            if aggs[arc] >= 0:
                amount = min(amount, agg_left[aggs[arc]])
        for arc, depart in path:
            residual[arc, depart] -= amount
            if residual[arc, depart] == 0:
                first_open[arc] = _next_open(residual[arc : arc + 1])[0]
            if aggs[arc] >= 0:
                agg_left[aggs[arc]] -= amount
        remaining[node] -= amount
        sent += amount
        element = problem.arc_element[path[0][0]]
        by_exit[element] = by_exit.get(element, 0) + amount
        last_arrival = max(last_arrival, arrival[sink])
    return Baseline("ccrp", last_arrival * problem.params.dt_s, sent, dict(sorted(by_exit.items())))
