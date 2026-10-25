"""Evacuation stress test on the navigation graph: every person walks the shortest way out and queues at the doors.

The same RouteGraph that answers "how do I get to the lift" supplies every length, every closure and every step-free rule, so the stress test and
the navigation can never disagree (tests/test_stress_sim.py asserts that a person's free-flow walk equals plan_route to the centimetre).

Model (idealised, parameterised, not a validated fire simulator; assumptions are returned with every result):
- each person has a pre-movement delay (log-normal, median 30 s) and a walking speed (normal, 1.34 m/s, sd 0.26, clipped 0.8 to 1.9);
- a door or stair is a server with the SFPE flow rule: 1.316 persons per second per metre of effective width, effective width = width - 0.30 m;
- people are served first come first served; the wait is the queue in front of that door;
- the room a person waits or walks in is the room whose door or stair they are heading for, so rooms and doors get a peak head count.
Defaults for who is where come from seats in the data, else from occupant-load factors by room type (labelled assumptions)."""

import heapq
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import networkx as nx
import numpy as np

from floorwise.core.graph import DOOR_PREFIX, Constraints, RouteGraph, anchor
from floorwise.core.model import OUTSIDE, Building
from floorwise.reason.occupants import seat_counts

FLOW_PER_M_S = 1.316            # SFPE: persons per second per metre of effective door width
BOUNDARY_M = 0.15               # each side of a door is unusable (shy distance)
STAIR_WIDTH_M = 1.2             # stairs carry no width in the data
MEAN_SPEED = 1.34
SPEED_SD = 0.26
PRE_MOVEMENT_MEDIAN_S = 30.0
PRE_MOVEMENT_SIGMA = 0.5
FRAME_COUNT = 90
# Fruin level of service for walkways, persons per m2 (upper bound of each band). Remembered values, labelled as such in the UI.
LOS_BANDS = (("A", 0.31), ("B", 0.43), ("C", 0.72), ("D", 1.08), ("E", 2.17))
# m2 per person by room type: IBC/ASR-style occupant-load factors (approximate, used only where the data has no seats).
LOAD_FACTOR_M2 = {"office": 9.3, "generic_room": 9.3, "lecture_hall": 1.0, "classroom": 1.9, "canteen": 1.4, "meeting_room": 1.4, "library": 4.6,
                  "lobby": 3.0, "kitchen": 18.6, "storage": 27.9, "print_room": 18.6, "toilet": 0.0, "bedroom": 18.6, "living_room": 18.6}
DEFAULT_LOAD_FACTOR_M2 = 9.3


def los(density: float) -> str:
    for letter, bound in LOS_BANDS:
        if density <= bound:
            return letter
    return "F"


@dataclass
class Spec:
    kind: str = "evacuation"                      # evacuation | step_free_evacuation
    occupants: dict[str, int] | None = None       # per space; None = estimate
    closed: frozenset[str] = frozenset()          # openings, connectors or spaces that are out of use
    pre_movement_median_s: float = PRE_MOVEMENT_MEDIAN_S
    seed: int = 7
    extra_openings: tuple[dict, ...] = ()         # doors that exist only in a what-if (door recommendations)


def estimate_occupants(building: Building) -> tuple[dict[str, int], str]:
    """(people per space, how it was estimated). Seats where the data has them, else floor area over an occupant-load factor."""
    seats = seat_counts(building)
    counts: dict[str, int] = {}
    for sid, space in building.spaces.items():
        if space["type"] in ("outdoor", "lift", "stair") or len(space["polygon"]) < 3:
            continue
        if sid in seats:
            counts[sid] = seats[sid]
            continue
        if space["type"] == "corridor":
            continue
        factor = LOAD_FACTOR_M2.get(space["room_type"], DEFAULT_LOAD_FACTOR_M2)
        if factor:
            n = int(building.polygons[sid].area / factor)
            if n:
                counts[sid] = n
    basis = "seats in the data where present, otherwise floor area divided by an occupant-load factor (approximate, from standards, not measured)"
    return counts, basis


def door_capacity(width_m: float) -> float:
    """Persons per second through an opening of this width (SFPE flow rule with a 15 cm boundary each side)."""
    return FLOW_PER_M_S * max(width_m - 2 * BOUNDARY_M, 0.3)


@dataclass
class Result:
    kpis: dict
    doors: list[dict]
    rooms: list[dict]
    frames: dict
    assumptions: list[str]
    flags: list[dict] = field(default_factory=list)
    people: list[tuple] = field(default_factory=list)


def _label(building: Building, node: str) -> str:
    return building.label(node) if node in building.spaces else node


def run(building: Building, spec: Spec | None = None, keep_people: bool = False) -> Result:
    spec = spec or Spec()
    rng = random.Random(spec.seed)
    counts, basis = (dict(spec.occupants), "given per room") if spec.occupants is not None else estimate_occupants(building)
    constraints = Constraints(closed=spec.closed, outside="exits", no_lifts=True, step_free=spec.kind == "step_free_evacuation", extra_openings=spec.extra_openings)
    graph = RouteGraph(building, constraints)
    g = graph.graph
    openings = {**building.openings, **{o["id"]: o for o in spec.extra_openings}}
    if OUTSIDE not in g:
        return Result({"people": sum(counts.values()), "evacuated": 0, "stranded": sum(counts.values()), "no_exit": True}, [], [], {}, [basis])
    dist, paths = nx.single_source_dijkstra(g, OUTSIDE, weight="weight")
    people = []   # (id, start space, speed, ready_time, node path to the exit)
    stranded = Counter()
    pid = 0
    for sid in sorted(counts):
        for _ in range(counts[sid]):
            pid += 1
            if sid not in paths:
                stranded[sid] += 1
                continue
            speed = min(1.9, max(0.8, rng.gauss(MEAN_SPEED, SPEED_SD)))
            ready = rng.lognormvariate(math.log(spec.pre_movement_median_s), PRE_MOVEMENT_SIGMA)
            people.append((pid, sid, speed, ready, paths[sid][::-1]))
    # servers: doors (door nodes) and stairs (connector ids)
    free_at: dict[str, float] = defaultdict(float)
    capacity: dict[str, float] = {}
    arrivals: dict[str, list[tuple[float, float]]] = defaultdict(list)   # server -> (arrive, start service)
    room_spans: dict[str, list[tuple[float, float]]] = defaultdict(list)
    heap: list[tuple[float, int, int, int]] = []
    state = {}
    for index, (pid_, sid, speed, ready, path) in enumerate(people):
        state[index] = {"depart": ready, "i": 0}
        heapq.heappush(heap, (ready, index, 0, 0))
    exits_at = [math.nan] * len(people)
    first_exit_node: dict[int, str] = {}
    while heap:
        t, index, i, _ = heapq.heappop(heap)
        pid_, sid, speed, ready, path = people[index]
        node = path[i]
        if node == OUTSIDE:
            exits_at[index] = t
            continue
        server = None
        if node.startswith(DOOR_PREFIX):
            server = node
            width = float(openings[node[len(DOOR_PREFIX):]].get("width_m") or 0.9)
            capacity[node] = door_capacity(width)
        start = t
        if server:
            start = max(t, free_at[server])
            free_at[server] = start + 1.0 / capacity[server]
            arrivals[server].append((t, start))
        nxt = path[i + 1]
        edge = graph.cheapest(node, nxt)
        # connectors (stairs) are servers too, taken at the start of the crossing
        via = edge.get("via")
        depart = start
        if via and via in building.connectors and node in building.spaces:
            width = STAIR_WIDTH_M
            capacity[via] = door_capacity(width)
            depart = max(start, free_at[via])
            free_at[via] = depart + 1.0 / capacity[via]
            arrivals[via].append((start, depart))
        space = edge.get("space") or (node if node in building.spaces else None)
        walk = float(edge["weight"]) / speed
        if space:
            room_spans[space].append((state[index].get("entered", 0.0), depart))
        state[index]["entered"] = depart
        heapq.heappush(heap, (depart + walk, index, i + 1, 0))
    evacuated = [t for t in exits_at if not math.isnan(t)]
    horizon = max(evacuated, default=0.0)
    times = np.asarray(sorted(evacuated)) if evacuated else np.asarray([0.0])
    kpis = {
        "people": sum(counts.values()), "evacuated": len(evacuated), "stranded": sum(stranded.values()),
        "first_out_s": round(float(times[0]), 1), "p50_s": round(float(np.percentile(times, 50)), 1),
        "p95_s": round(float(np.percentile(times, 95)), 1), "max_s": round(float(times[-1]), 1),
        "stranded_rooms": [{"id": sid, "name": _label(building, sid), "people": n} for sid, n in stranded.most_common(8)],
    }
    # doors and stairs: load, longest wait, how many were waiting at once
    doors = []
    for server, rows in arrivals.items():
        waits = [s - a for a, s in rows]
        events = sorted([(a, 1) for a, s in rows if s > a] + [(s, -1) for a, s in rows if s > a])
        peak = level = 0
        for _, delta in events:
            level += delta
            peak = max(peak, level)
        oid = server[len(DOOR_PREFIX):] if server.startswith(DOOR_PREFIX) else server
        if oid in openings:
            opening = openings[oid]
            between = [_label(building, s) for s in opening["space_ids"] if s != OUTSIDE] + (["outside"] if OUTSIDE in opening["space_ids"] else [])
            position, floor_id, width = opening["position"], opening["floor_id"], float(opening.get("width_m") or 0.9)
        else:
            connector = building.connectors[oid]
            between = [connector["name"]]
            first_space = building.spaces[connector["space_ids"][0]]
            position, floor_id, width = list(anchor(building, connector["space_ids"][0])), first_space["floor_id"], STAIR_WIDTH_M
        doors.append({"id": oid, "kind": "stair" if oid in building.connectors else openings[oid]["kind"], "between": between, "floor_id": floor_id, "position": list(position),
                      "width_m": round(width, 2), "flow_pps": round(capacity.get(server, 0.0), 2), "load": len(rows), "peak_queue": peak,
                      "max_wait_s": round(max(waits), 1), "total_wait_s": round(sum(waits), 1), "last_through_s": round(max(s for _, s in rows), 1)})
    doors.sort(key=lambda d: -d["total_wait_s"])
    # rooms over time: head count in FRAME_COUNT frames, peak density and Fruin level
    step = max(horizon / FRAME_COUNT, 1.0)
    grid = np.arange(0.0, horizon + step, step)
    frames: dict[str, list[int]] = {}
    rooms = []
    for sid, spans in room_spans.items():
        starts = np.asarray([a for a, _ in spans])
        ends = np.asarray([b for _, b in spans])
        head = [int(((starts <= t) & (ends > t)).sum()) for t in grid]
        if not any(head):
            continue
        frames[sid] = head
        area = max(building.polygons[sid].area * 0.7, 1.0)  # 30 % of a room is furniture and walls
        peak = max(head)
        rooms.append({"id": sid, "name": _label(building, sid), "floor_id": building.spaces[sid]["floor_id"], "peak_people": peak,
                      "peak_at_s": round(float(grid[int(np.argmax(head))]), 1), "peak_density": round(peak / area, 2), "los": los(peak / area)})
    rooms.sort(key=lambda r: -r["peak_density"])
    flags = []
    far = [(sid, d) for sid, d in dist.items() if sid in counts and d > 35.0 * 1.5]
    if far:
        flags.append({"kind": "long_escape_route", "text": f"{len(far)} rooms are more than 52 m of route from an exit (ASR A2.3: 35 m escape length at 1.5 x walking length; indicative)",
                      "rooms": [{"id": sid, "name": _label(building, sid), "route_m": round(d, 1)} for sid, d in sorted(far, key=lambda x: -x[1])[:8]]})
    assumptions = [
        f"People: {basis}.", f"Pre-movement: log-normal, median {spec.pre_movement_median_s:g} s; walking speed 1.34 m/s (sd 0.26).",
        f"Door flow: {FLOW_PER_M_S} persons per second per metre of width minus {2 * BOUNDARY_M:g} m of boundary; stairs {STAIR_WIDTH_M} m wide (not in the data); lifts not used.",
        "Everyone takes the shortest route to the nearest entrance; no route choice by queue length, no smoke, no merging at stair landings.",
        "Density = head count over 70 % of the room area; levels of service from Fruin's walkway bands (values from memory of the literature).",
    ]
    result = Result(kpis, doors, sorted(rooms, key=lambda r: r["name"]), {"step_s": round(float(step), 2), "rooms": frames}, assumptions, flags)
    if keep_people:
        result.people = [(p[0], p[1], p[2], p[3], exits_at[i]) for i, p in enumerate(people)]
    return result
