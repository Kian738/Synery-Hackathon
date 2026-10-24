"""Time-expanded network: node (space, step), waiting arcs, one arc per element direction and departure step.

Capacity per step is an integer built by cumulative flooring of rate * dt, so the long-run rate is exact.
An arc leaves (u, t) and lands at (v, t + tau), tau = whole steps rounded UP. Exits land in the sink.
Max-flow is scipy.sparse.csgraph.maximum_flow (Dinic). Everything is built in sorted order, so identical inputs
give identical arrays and identical flows.
"""

import heapq
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import breadth_first_order, maximum_flow

from floorwise.evacuation.adapter import CapacityGraph, Element
from floorwise.evacuation.types import Capacity, FlowParams, Hazard

EPS = 1e-9
TO_SINK = -1  # head value of an arc that leaves the building
KIND_WAIT, KIND_ELEMENT, KIND_SOURCE, KIND_AGG = 0, 1, 2, 3


def hazard_blocks(hazard: Hazard | Sequence[Hazard] | None) -> tuple[dict[str, float], dict[str, float]]:
    """(space id -> earliest block time, element id -> earliest block time) over one or several hazards."""
    hazards = [] if hazard is None else [hazard] if isinstance(hazard, Hazard) else list(hazard)
    spaces: dict[str, float] = {}
    elements: dict[str, float] = {}
    for item in hazards:
        for space in item.spaces:
            spaces[space] = min(spaces.get(space, math.inf), item.from_s + item.escape_s)
        for element in item.elements:
            elements[element] = min(elements.get(element, math.inf), item.from_s)
    return spaces, elements


@lru_cache(maxsize=16384)
def step_caps(rate: float, block: float, leg_s: float, windows: tuple[tuple[float, float], ...], steps: int, dt: int,
              big: int) -> np.ndarray:
    """Integer persons that may depart per step: cumulative floor of rate * dt, zero once blocked, rate halved
    inside reservation windows (counterflow). Cached: door search re-solves differ by one element only."""
    starts = np.arange(steps) * dt
    open_now = starts + leg_s < block
    if math.isinf(rate):
        result = np.where(open_now, big, 0).astype(np.int64)
    else:
        profile = np.where(open_now, rate, 0.0)
        for begin, end in windows:
            profile[(starts < end) & (starts + dt > begin)] *= 0.5  # counterflow: half the effective width
        cumulative = np.floor(np.cumsum(profile * dt) + EPS).astype(np.int64)
        result = np.minimum(np.diff(cumulative, prepend=0), big)
    result.flags.writeable = False
    return result


def hop_steps(element: Element, params: FlowParams) -> int:
    """Whole steps one crossing takes, rounded up, at least one."""
    return max(1, math.ceil(element.length_m / (params.speed_mps * element.speed_factor) / params.dt_s - EPS))


def element_rate(element: Element, params: FlowParams) -> float:
    """Persons per second through the element from its width alone (inf if it has no width)."""
    if element.width_m is None:
        return math.inf
    return params.specific_flow * max(element.width_m - 2 * params.boundary_m, 0.0)


@dataclass
class Net:
    """One expanded network at a fixed horizon. Arrays are parallel; kind/arc/when say what each arc is."""

    steps: int
    node_count: int
    source: int
    sink: int
    tail: np.ndarray
    head: np.ndarray
    cap: np.ndarray
    kind: np.ndarray
    arc: np.ndarray  # Problem arc index (element arcs), space index (source arcs), aggregator index
    when: np.ndarray  # departure step


@dataclass
class Solution:
    value: int
    net: Net
    flow: np.ndarray  # per arc of the net
    reach: np.ndarray  # bool per node: source side of the minimum cut (residual reachability from the source)


class Problem:
    """A fully specified instance: capacities, hazard and reservations are baked into per-step arrays."""

    def __init__(self, graph: CapacityGraph, occupants: Mapping[str, int], hazard: Hazard | Sequence[Hazard] | None,
                 capacities: Sequence[Capacity], params: FlowParams,
                 reservations: Mapping[str, Sequence[tuple[float, float]]] | None = None) -> None:
        self.graph, self.params = graph, params
        self.n = len(graph.spaces)
        self.index = {space: i for i, space in enumerate(graph.spaces)}
        self.steps_max = max(1, params.max_horizon_s // params.dt_s)
        space_block, element_block = hazard_blocks(hazard)
        families = {e.family for e in graph.elements} | {e.id for e in graph.elements}
        for label, names, known in (("hazard space", space_block, self.index), ("hazard element", element_block, families),
                                    ("occupant space", occupants, self.index),
                                    ("capacity element", {c.element: c for c in capacities}, families)):
            unknown = sorted(set(names) - set(known))
            if unknown:
                raise ValueError(f"unknown {label}: {unknown[:3]}")
        self.occ = np.zeros(self.n, dtype=np.int64)
        for space, count in occupants.items():
            self.occ[self.index[space]] = count
        self.total = int(self.occ.sum())
        self.big = int(min(self.total + 1, 2**30))
        never = self.steps_max + 2
        self.alive_until = np.array(
            [never if space not in space_block else max(0, math.ceil(space_block[space] / params.dt_s - EPS))
             for space in graph.spaces], dtype=np.int64)
        self._build_arcs(element_block, {c.element: c for c in capacities}, reservations or {})

    # ---------- arcs ----------

    def _build_arcs(self, element_block: Mapping[str, float], caps: Mapping[str, Capacity],
                    reservations: Mapping[str, Sequence[tuple[float, float]]]) -> None:
        params = self.params
        rows: list[tuple[int, int, int]] = []
        self.arc_element: list[str] = []
        self.arc_seconds: list[float] = []  # continuous walking time of the whole hop, before rounding
        arrays: list[np.ndarray] = []
        agg_of: list[int] = []
        self.agg_total: list[int] = []
        for element in self.graph.elements:
            override = caps.get(element.id) or caps.get(element.family)
            total = None
            if override is not None and override.kind == "total_persons":
                if not element.is_exit:
                    raise ValueError(
                        f"total_persons cap on interior element {element.id!r} is not a network-flow constraint; "
                        "use rate_persons_per_s, or put the total cap on an exit")
                total = int(override.value)
            if override is not None and override.kind == "rate_persons_per_s":
                rate = override.value
            else:
                rate = element_rate(element, params)
            block = min(element_block.get(element.family, math.inf), element_block.get(element.id, math.inf))
            windows = reservations.get(element.id, ())
            tau = hop_steps(element, params)
            sides = [(element.a, element.b, element.leg_a_m)]
            if not element.is_exit:
                sides.append((element.b, element.a, element.leg_b_m))
            for tail, head, leg in sides:
                step_cap = step_caps(float(rate), block, leg / params.speed_mps, tuple(windows), self.steps_max,
                                     params.dt_s, self.big)
                if not step_cap.any() or total == 0:
                    continue
                rows.append((self.index[tail], TO_SINK if element.is_exit else self.index[head], tau))
                self.arc_element.append(element.id)
                self.arc_seconds.append(element.length_m / (params.speed_mps * element.speed_factor))
                arrays.append(step_cap)
                if total is None:
                    agg_of.append(-1)
                else:
                    agg_of.append(len(self.agg_total))
                    self.agg_total.append(total)
        self.arc_tail = np.array([r[0] for r in rows], dtype=np.int64)
        self.arc_head = np.array([r[1] for r in rows], dtype=np.int64)
        self.arc_tau = np.array([r[2] for r in rows], dtype=np.int64)
        self.arc_cap = np.array(arrays, dtype=np.int64).reshape(len(rows), self.steps_max)
        self.arc_agg = np.array(agg_of, dtype=np.int64)
        self.last_open = np.maximum.accumulate(
            np.where(self.arc_cap > 0, np.arange(self.steps_max)[None, :], -1), axis=1)  # last step <= t with cap > 0
        self.out_arcs: list[list[int]] = [[] for _ in range(self.n)]
        self.in_arcs: list[list[int]] = [[] for _ in range(self.n)]
        for arc in range(len(rows)):
            self.out_arcs[int(self.arc_tail[arc])].append(arc)
            if self.arc_head[arc] != TO_SINK:
                self.in_arcs[int(self.arc_head[arc])].append(arc)

    # ---------- reachability with deadline (no queueing) ----------

    def latest(self, deadline: int) -> np.ndarray:
        """Per space: the latest step a person can still be there and reach the sink by `deadline`
        (-1: cannot). Closings only ever remove options, so being earlier is never worse: latest[s] >= 0 means
        a person starting at s at step 0 can make it."""
        tails, taus = self.arc_tail.tolist(), self.arc_tau.tolist()
        alive = self.alive_until.tolist()
        best = [-1] * self.n
        heap: list[tuple[int, int]] = []
        top = self.steps_max - 1

        def relax(arc: int, arrive_by: int) -> None:
            tail = tails[arc]
            limit = min(alive[tail] - 1, arrive_by - taus[arc], top)
            depart = int(self.last_open[arc, limit]) if limit >= 0 else -1
            if depart > best[tail]:
                best[tail] = depart
                heapq.heappush(heap, (-depart, tail))

        for arc in np.flatnonzero(self.arc_head == TO_SINK).tolist():
            relax(arc, deadline)
        while heap:
            negative, space = heapq.heappop(heap)
            if -negative < best[space]:
                continue
            for arc in self.in_arcs[space]:
                relax(arc, best[space])
        return np.array(best, dtype=np.int64)

    def evacuable(self) -> np.ndarray:
        """Occupied spaces from which one person can reach the outside at all."""
        return (self.occ > 0) & (self.latest(self.steps_max) >= 0)

    def free_flow_steps(self, evacuable: np.ndarray, upper: int | None = None) -> int:
        """Smallest deadline (steps) at which every evacuable space can make it alone, no queueing. `upper` must
        be a deadline at which they can."""
        if not evacuable.any():
            return 0
        low, high = 0, upper or self.steps_max
        while high - low > 1:
            middle = (low + high) // 2
            if (self.latest(middle)[evacuable] >= 0).all():
                high = middle
            else:
                low = middle
        return high

    # ---------- the expanded network ----------

    def net(self, steps: int) -> Net:
        n = self.n
        if steps > self.steps_max:
            raise ValueError("horizon beyond max_horizon_s")
        alive = np.arange(steps + 1)[:, None] < self.alive_until[None, :]
        node_count = n * (steps + 1) + 2
        source, sink = n * (steps + 1), n * (steps + 1) + 1
        first_agg = node_count
        node_count += len(self.agg_total)
        parts: list[tuple[np.ndarray, np.ndarray, np.ndarray, int, np.ndarray, np.ndarray]] = []
        t_wait, s_wait = np.nonzero(alive[:-1] & alive[1:])
        parts.append((t_wait * n + s_wait, (t_wait + 1) * n + s_wait, np.full(t_wait.size, self.big), KIND_WAIT,
                      s_wait, t_wait))
        if len(self.arc_tail):
            when = np.arange(steps)[None, :]  # departure steps; tau >= 1 so the last useful one is steps - 1
            land = when + self.arc_tau[:, None]
            to_space = self.arc_head >= 0
            ok = (self.arc_cap[:, :steps] > 0) & (land <= steps) & alive[when, self.arc_tail[:, None]]
            ok &= ~to_space[:, None] | alive[np.minimum(land, steps), np.where(to_space, self.arc_head, 0)[:, None]]
            arc_index, depart = np.nonzero(ok)  # arc-major, then time: a fixed order
            head = self.arc_head[arc_index]
            sink_target = np.where(self.arc_agg[arc_index] < 0, sink, first_agg + self.arc_agg[arc_index])
            target = np.where(head >= 0, (depart + self.arc_tau[arc_index]) * n + head, sink_target)
            parts.append((depart * n + self.arc_tail[arc_index], target, self.arc_cap[arc_index, depart],
                          KIND_ELEMENT, arc_index, depart))
        origin = np.flatnonzero((self.occ > 0) & alive[0])
        parts.append((np.full(origin.size, source), origin, self.occ[origin], KIND_SOURCE, origin,
                      np.zeros(origin.size, dtype=np.int64)))
        for index, total in enumerate(self.agg_total):
            parts.append((np.array([first_agg + index]), np.array([sink]), np.array([total]), KIND_AGG,
                          np.array([index]), np.array([0])))
        cat = [np.concatenate([np.asarray(p[i], dtype=np.int64) for p in parts]) for i in (0, 1, 2, 4, 5)]
        kind = np.concatenate([np.full(len(p[0]), p[3], dtype=np.int64) for p in parts])
        return Net(steps, node_count, source, sink, cat[0], cat[1], np.minimum(cat[2], 2**30), kind, cat[3], cat[4])

    def solve(self, steps: int) -> Solution:
        net = self.net(steps)
        size = net.node_count
        keys = net.tail * size + net.head
        unique, inverse = np.unique(keys, return_inverse=True)
        merged = np.minimum(np.bincount(inverse, weights=net.cap), 2**30).astype(np.int32)
        rows, cols = unique // size, unique % size
        matrix = csr_matrix((merged, (rows, cols)), shape=(size, size))
        result = maximum_flow(matrix, net.source, net.sink)
        flow_unique = np.asarray(result.flow[rows, cols]).ravel().astype(np.int64)
        flow = self._split_duplicates(net, inverse, flow_unique)
        residual_forward = merged - flow_unique > 0
        residual_back = flow_unique > 0
        residual = csr_matrix((np.ones(int(residual_forward.sum() + residual_back.sum()), dtype=np.int8),
                               (np.concatenate([rows[residual_forward], cols[residual_back]]),
                                np.concatenate([cols[residual_forward], rows[residual_back]]))), shape=(size, size))
        reach = np.zeros(size, dtype=bool)
        reach[breadth_first_order(residual, net.source, directed=True, return_predecessors=False)] = True
        return Solution(int(result.flow_value), net, flow, reach)

    @staticmethod
    def _split_duplicates(net: Net, inverse: np.ndarray, flow_unique: np.ndarray) -> np.ndarray:
        """Parallel arcs share one matrix entry; hand its flow out in arc order, each up to its capacity."""
        flow = flow_unique[inverse].copy()
        counts = np.bincount(inverse)
        parallel = np.flatnonzero(counts > 1)
        if parallel.size:
            order = np.argsort(inverse, kind="stable")  # members of a group in arc order
            starts = np.concatenate([[0], np.cumsum(counts)])
            for group in parallel:
                remaining = int(flow_unique[group])
                for member in order[starts[group]: starts[group + 1]]:
                    take = min(remaining, int(net.cap[member]))
                    flow[member] = take
                    remaining -= take
        return flow
