"""N-1 robust door synthesis.

best_doors makes the evacuation as fast as possible for the scenario as given. A safety officer also asks what happens
when the best exit is lost too (blocked by the fire, jammed, locked). Power-grid planning calls that N-1 contingency
analysis: a design must survive the loss of any single component. Here a candidate door is scored by its worst case over
{the scenario as given} + {each usable exit lost in turn}, worst meaning fewest people out, then slowest. Candidates are
the doors whose edge crosses a minimum cut in at least one of those scenarios (only they can raise a max-flow).

The greedy order is not claimed optimal; `verified` means an independent solve on an edited copy of the building
reproduced every scenario. Our synthesis of N-1 contingency analysis with door augmentation; no prior work found."""

from collections.abc import Sequence
from dataclasses import dataclass

from floorwise.core.model import OUTSIDE, Building
from floorwise.evacuation.adapter import CapacityGraph, build_graph
from floorwise.evacuation.doors import (
    NEW_DOOR_WIDTH_M,
    WIDENED_TO_M,
    Candidate,
    _apply,
    _crosses,
    _cuts,
    candidates_for,
    edited_building,
    wall_pairs,
)
from floorwise.evacuation.solve import Quickest, evacuate, quickest
from floorwise.evacuation.ten import Problem, hazard_blocks
from floorwise.evacuation.types import DEFAULT_PARAMS, Capacity, FlowParams, Hazard, Occupants


@dataclass(frozen=True)
class Scenario:
    lost_exit: str | None  # None = the scenario as given
    evacuated: int
    T_s: int

    @property
    def badness(self) -> tuple[int, int]:  # fewer out is worse, then slower: larger is worse
        return (-self.evacuated, self.T_s)


@dataclass(frozen=True)
class RobustFix:
    kind: str
    element: str
    between: tuple[str, str]
    width_m: float
    worst_before: Scenario
    worst_after: Scenario


@dataclass(frozen=True)
class RobustPlan:
    scenarios_before: tuple[Scenario, ...]
    scenarios_after: tuple[Scenario, ...]
    fixes: tuple[RobustFix, ...]
    verified: bool
    candidates: int
    evaluated: int


def _as_list(hazard) -> list[Hazard]:
    return [] if hazard is None else list(hazard) if isinstance(hazard, Sequence) else [hazard]


def usable_exits(building: Building, hazard: Sequence[Hazard]) -> list[str]:
    blocked_spaces, blocked_elements = hazard_blocks(list(hazard))
    return sorted(o["id"] for o in building.openings.values()
                  if OUTSIDE in o["space_ids"] and o["id"] not in blocked_elements
                  and not any(s in blocked_spaces for s in o["space_ids"] if s != OUTSIDE))


def robust_doors(building: Building, occupants: Occupants, hazard=None, capacities: Sequence[Capacity] = (),
                 params: FlowParams = DEFAULT_PARAMS, *, max_fixes: int = 2, new_width_m: float = NEW_DOOR_WIDTH_M,
                 widen_to_m: float = WIDENED_TO_M) -> RobustPlan:
    base = _as_list(hazard)
    losses: list[str | None] = [None, *usable_exits(building, base)]
    dt = params.dt_s

    def hazards_for(loss: str | None) -> list[Hazard]:
        return base + ([Hazard(elements=(loss,))] if loss else [])

    def problems(graph: CapacityGraph) -> list[Problem]:
        return [Problem(graph, occupants.by_space, hazards_for(e), capacities, params) for e in losses]

    def solve(graph: CapacityGraph) -> list[Quickest | None]:
        return [quickest(p) for p in problems(graph)]

    def table(solved: list[Quickest | None]) -> tuple[Scenario, ...]:
        return tuple(Scenario(loss, q.evacuated, q.steps * dt) for loss, q in zip(losses, solved, strict=True) if q)

    graph = build_graph(building, params)
    current = solve(graph)
    before = table(current)
    pairs = wall_pairs(building, graph, set(hazard_blocks(base)[0]))
    pool = candidates_for(graph, pairs, new_width_m, widen_to_m)
    survivors: dict[tuple[str, str], Candidate] = {}
    for problem, quick in zip(problems(graph), current, strict=True):
        if quick is None:
            continue
        cuts = _cuts(problem, quick)
        for candidate in pool:
            if _crosses(candidate, graph, problem, cuts, params):
                survivors.setdefault((candidate.kind, candidate.element), candidate)

    chosen: list[tuple[Candidate, Scenario, Scenario]] = []
    evaluated = 0
    for _ in range(max_fixes):
        worst_now = max(s.badness for s in table(current))
        best = None
        for candidate in survivors.values():
            if any(candidate is c for c, _, _ in chosen):
                continue
            after = solve(_apply(graph, candidate))
            evaluated += 1
            scenarios = table(after)
            if len(scenarios) != len(before):
                continue
            score = max(s.badness for s in scenarios)
            rank = (score, candidate.added_width_m, candidate.element)
            if score < worst_now and (best is None or rank < best[0]):
                best = (rank, candidate, after)
        if best is None:
            break
        _, candidate, after = best
        worst_before = max(table(current), key=lambda s: s.badness)
        graph, current = _apply(graph, candidate), after
        chosen.append((candidate, worst_before, max(table(current), key=lambda s: s.badness)))

    after_table = table(current)
    verified = True
    if chosen:
        edited = edited_building(building, [c.edit for c, _, _ in chosen])
        check = [evacuate(edited, occupants, hazards_for(e), capacities, params, with_ccrp=False, with_nearest=False)
                 for e in losses]
        verified = [(r.evacuated, r.T_s) for r in check] == [(s.evacuated, s.T_s) for s in after_table]
    fixes = tuple(RobustFix(c.kind, c.element, c.between, c.width_m, b, a) for c, b, a in chosen)
    return RobustPlan(before, after_table, fixes, verified, len(survivors), evaluated)
