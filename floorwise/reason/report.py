"""One scenario run as a plain dict: the shape the REST API returns and the chat tool hands to Claude."""
from dataclasses import asdict
from types import SimpleNamespace

from floorwise.core.model import Building
from floorwise.evacuation import to_dict
from floorwise.evacuation.robust import robust_doors, usable_exits
from floorwise.reason import evac_ops
from floorwise.reason.execute import run_plan
from floorwise.reason.findings import assess
from floorwise.reason.templates import instantiate


def _summary(r) -> str:
    """One human sentence per step; the raw value stays in the solver, never in the screen."""
    v, g = r.value, getattr
    if not r.ok:
        return f"{r.op}: {r.reason}"
    lines = {
        "scenario": lambda: "Scenario read",
        "apply_hazards": lambda: f"Hazard applied: {len(v.closed)} place(s) closed",
        "occupants": lambda: f"{sum(v.by_space.values())} people placed ({v.source})",
        "exits": lambda: f"{len(v)} usable exits",
        "evacuate": lambda: f"{v.evacuated} of {v.total} people out in {v.T_s} s",
        "bottleneck": lambda: f"{len(v)} doors limit the flow",
        "responder_route": lambda: f"Responders reach the hazard (+{g(v, 'delay_s', 0)} s for evacuees)",
        "door_candidates": lambda: "Candidate doors screened against the minimum cut",
        "best_door": lambda: f"{len(v.fixes)} fix: {v.T_before_s} s -> {v.T_after_s} s",
    }
    return lines.get(r.op, lambda: f"{r.op} checked")()


def resolve_exit(building: Building, text: str) -> str:
    """An exit as an opening id, or the outside door(s) of a named space; ambiguous or missing is an error with candidates."""
    if text in building.openings and "outside" in building.openings[text]["space_ids"]:
        return text
    from floorwise.core import resolve
    space = resolve.resolve_space(building, text).id
    exits = sorted(o["id"] for o in building.openings.values() if "outside" in o["space_ids"] and space in o["space_ids"])
    if len(exits) != 1:
        raise ValueError(f"{text!r} has {len(exits)} exits to the outside; name the exit by its id: {exits[:6]}" if exits
                         else f"{text!r} has no exit to the outside")
    return exits[0]


def scenario_report(building: Building, template: str, params: dict, audience: str) -> dict:
    trace = run_plan(building, instantiate(template, **params))
    evacuation = next((r.value for r in trace.results if r.op == "evacuate" and r.ok), None)
    return {
        "template": template,
        "steps": [{"id": r.id, "op": r.op, "ok": r.ok, "summary": _summary(r),
                   "reason": r.reason, "ms": round(r.ms, 1)} for r in trace.results],
        "responder": _responder(building, trace),
        "abstained": None if trace.abstained is None else asdict(trace.abstained),
        "answer": to_dict(trace.answer),
        "evacuation": None if evacuation is None else to_dict(evacuation),
        "findings": [asdict(f) for f in assess(trace, audience, building)] if evacuation is not None or trace.abstained else [],
    }


def _responder(building: Building, trace) -> dict | None:
    """The chosen responder route as places to draw: the entrance, the spaces and doors crossed, when they arrive."""
    plan = next((r.value for r in trace.results if r.op == "responder_route" and r.ok), None)
    chosen = getattr(plan, "chosen", None)
    if chosen is None:
        return None
    return {"entrance": chosen.entrance, "spaces": list(chosen.spaces), "elements": list(chosen.elements),
            "arrival_s": round(chosen.arrival_s), "delay_s": plan.delay_s}


def robust_report(building: Building, spec: dict) -> dict:
    """N-1: the worst case over 'the scenario as given' and 'each usable exit lost', and the doors that improve it.
    Slow (it re-solves every scenario per candidate door), so it is asked for, never run by default."""
    from floorwise.reason.types import ScenarioSpec

    parsed = ScenarioSpec.from_dict(spec)
    world = SimpleNamespace(building=building, closed=frozenset())
    hazards = evac_ops._hazards(world, parsed)
    plan = robust_doors(building, evac_ops._people(world, parsed), hazards, evac_ops._capacities(parsed))

    def name(door: str) -> str:
        from floorwise.reason.findings import _name
        return _name(building, door)

    def rows(table):
        return [{"lost_exit": s.lost_exit and name(s.lost_exit), "evacuated": s.evacuated, "T_s": s.T_s} for s in table]

    return {"before": rows(plan.scenarios_before), "after": rows(plan.scenarios_after), "verified": plan.verified,
            "fixes": [{"element": f.element, "name": name(f.element), "width_m": f.width_m} for f in plan.fixes]}
