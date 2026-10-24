"""A replica of the judges' route scoring, as described by Synera on the hackathon channel:

  - the answer is the ordered list of spaces the route passes through;
  - every step must go through a real door, opening, stair or lift, and the rules (step-free, closed places) must hold;
  - the route is then measured with the official distance rule; the answer's own distance numbers do not matter;
  - score = best possible length / your length; within 1% of the best is full marks; an invalid route scores 0;
  - if no route exists under the rules, the correct answer is to say so.

The measuring uses the kit's own starter_agent.building_map (kit 1.1.0), not our router, so a bug in our graph cannot
hide itself. `measure` restricts that graph to the listed spaces, in order (a layered shortest path)."""

import heapq
import re
from dataclasses import dataclass

from floorwise.paths import use_kit_modules

FULL_MARKS_WITHIN = 0.01
NO_ROUTE = re.compile(r"\bno\s+route\b|\bunreachable\b|\bnot reachable\b|\bno way\b", re.I)
SEPARATOR = re.compile(r"\s*(?:->|→|>|,|;|\n)\s*")


@dataclass
class Verdict:
    valid: bool
    length_m: float | None
    reason: str = ""


def kit_map(building_data: dict):
    use_kit_modules()
    from starter_agent.building_map import BuildingMap

    return BuildingMap(building_data)


def parse_answer(answer_line: str) -> list[str] | None:
    """The ordered space ids in an answer line, or None for 'no route'."""
    if NO_ROUTE.search(answer_line) and "->" not in answer_line:
        return None
    return [part.strip() for part in SEPARATOR.split(answer_line.strip().strip("[]")) if part.strip()]


def measure(bm, sequence: list[str], step_free: bool = False, closed: set[str] | None = None) -> Verdict:
    """Length of the cheapest walk that visits `sequence` in order, or invalid if some step has no door/stair/lift."""
    if not sequence:
        return Verdict(False, None, "empty route")
    unknown = [s for s in sequence if s not in bm.spaces]
    if unknown:
        return Verdict(False, None, f"unknown space {unknown[0]}")
    if any(a == b for a, b in zip(sequence, sequence[1:])):
        return Verdict(False, None, "the same space twice in a row")
    bm.closed = set(closed or ())
    if any(s in bm.closed for s in sequence):
        return Verdict(False, None, "route uses a closed space")
    graph = bm.graph(step_free)
    last = len(sequence) - 1
    start, goal = (0, sequence[0]), (last, sequence[-1])
    dist = {start: 0.0}
    heap = [(0.0, 0, sequence[0])]
    seen: set = set()
    while heap:
        d, i, node = heapq.heappop(heap)
        if (i, node) in seen:
            continue
        seen.add((i, node))
        if (i, node) == goal:
            return Verdict(True, round(d, 2))
        for neighbour, edges in graph[node].items():
            for edge in edges.values():
                space = edge.get("space") or (node if node in bm.spaces else neighbour if neighbour in bm.spaces else None)
                if space == sequence[i]:  # a walk inside the current space
                    _relax(heap, dist, d + edge["weight"], i, neighbour)
                elif "via" in edge and i < last and neighbour == sequence[i + 1] and node == sequence[i]:
                    _relax(heap, dist, d + edge["weight"], i + 1, neighbour)  # stairs or a lift to the next space
        if i < last and node.startswith("door:"):  # a door shared with the next space
            if sequence[i + 1] in graph[node] or any(edge.get("space") == sequence[i + 1] for edges in graph[node].values() for edge in edges.values()):
                _relax(heap, dist, d, i + 1, node)
    return Verdict(False, None, "a step does not go through an open door, opening, stair or lift")


def visits_in_order(sequence: list[str], stops: list[str]) -> bool:
    """Starts at the first stop, ends at the last, and passes the others in order."""
    if not stops or sequence[0] != stops[0] or sequence[-1] != stops[-1]:
        return False
    cursor = 0
    for space in sequence:
        if cursor < len(stops) and space == stops[cursor]:
            cursor += 1
    return cursor == len(stops)


def _relax(heap: list, dist: dict, cost: float, layer: int, node: str) -> None:
    if cost < dist.get((layer, node), float("inf")) - 1e-12:
        dist[(layer, node)] = cost
        heapq.heappush(heap, (cost, layer, node))


def score(best_m: float | None, verdict: Verdict | None, said_no_route: bool) -> float:
    """The judges' score for one route question. best_m None means no route exists under the rules."""
    if best_m is None:
        return 1.0 if said_no_route else 0.0
    if said_no_route or verdict is None or not verdict.valid or not verdict.length_m:
        return 0.0
    ratio = best_m / verdict.length_m
    return 1.0 if verdict.length_m <= best_m * (1 + FULL_MARKS_WITHIN) + 1e-9 else min(1.0, ratio)
