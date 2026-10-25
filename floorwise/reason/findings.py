"""What the stakeholder should do about a scenario: findings with evidence, a verified suggestion where one exists, and
wording for who is asking. Every number comes from a step of the trace; nothing here computes or guesses a figure.

Audiences: occupant, safety_officer, builder, regulator. A regulator sees reference values labelled "not a compliance
check"; the engine models flows, it does not certify a building."""

from dataclasses import dataclass
from typing import Literal

from floorwise.reason.types import Trace

AUDIENCES = ("occupant", "safety_officer", "builder", "regulator")
Severity = Literal["blocker", "risk", "improve", "info"]
Tier = Literal["computed", "estimate", "assumption"]
ORDER = {"blocker": 0, "risk": 1, "improve": 2, "info": 3}
DOOR_RATE_REFERENCE = "SFPE hydraulic model, 1.316 persons/s per metre of effective width (a band of 1.0 to 1.6 is plausible)"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    title: str
    detail: str
    evidence: tuple[str, ...]  # trace step ids the numbers come from
    tier: Tier
    suggestion: str | None = None  # present only when a re-solve confirmed it


def _result(trace: Trace, op: str):
    return next((r.value for r in trace.results if r.op == op and r.ok), None)


def assess(trace: Trace, audience: str = "safety_officer", building=None) -> list[Finding]:
    """Findings from an evacuation-style trace, most serious first. An abstained trace yields one blocker that names the
    step that stopped and why; a plan that never reached the solver has nothing else to report."""
    if audience not in AUDIENCES:
        raise ValueError(f"audience must be one of {AUDIENCES}, got {audience!r}")
    found: list[Finding] = []
    if trace.abstained and not _result(trace, "evacuate"):
        a = trace.abstained
        return [Finding("blocker", f"The analysis stopped at step '{a.step}'", a.reason, (a.step,), "computed")]
    evacuation = _result(trace, "evacuate")
    if evacuation is not None:
        found += _people(evacuation, audience)
        found += _doors(trace, evacuation, audience, building)
    plan = _result(trace, "responder_route")
    if plan is not None:
        found += _responders(plan, audience)
    if trace.abstained:  # the solver ran but a later step found nothing to propose
        found.append(Finding("info", f"No improvement found at step '{trace.abstained.step}'", trace.abstained.reason,
                             (trace.abstained.step,), "computed"))
    if evacuation is not None:
        found.append(Finding("info", "What this is built on", "; ".join(evacuation.assumptions), ("evac",), "assumption"))
        if audience == "regulator":
            found.append(Finding("info", "Reference value, not a compliance check", DOOR_RATE_REFERENCE, ("evac",), "assumption"))
    return sorted(found, key=lambda f: ORDER[f.severity])


def _people(evacuation, audience: str) -> list[Finding]:
    stranded = sum(evacuation.stranded.values())
    cut = sum(evacuation.cut_off.values())
    found = []
    if cut:
        where = ", ".join(sorted(evacuation.cut_off))
        found.append(Finding("blocker", f"{cut} people have no route out",
                             f"They start in {where}; every way out is blocked or unconnected. This is a modelled hazard, not a prediction.",
                             ("evac",), "computed"))
    elif stranded:
        found.append(Finding("risk", f"{stranded} people are not out within the model horizon",
                             "Capacity, not blockage, limits them: the doors they need are saturated.", ("evac",), "computed"))
    queue = evacuation.T_s - evacuation.free_flow_s
    if queue > 0 and not stranded:
        found.append(Finding("improve" if audience != "occupant" else "info",
                             f"Evacuation takes {evacuation.T_s} s, {queue} s of it queueing",
                             f"Without queueing it would take {evacuation.free_flow_s} s.", ("evac",), "computed"))
    return found


def _name(building, ident: str) -> str:
    """People read names, never ids: a door is the two places it joins, a space is its label."""
    if building is None:
        return ident
    if ident in building.openings:
        from floorwise.core.resilience import _display_name
        return _display_name(building, building.openings[ident])
    return building.label(ident) if ident in building.spaces else ident


def _capacity_math(building, evacuation, door: str) -> str:
    """The number behind the headline: rate = specific flow x (width - 2 x boundary layer), SFPE handbook form."""
    if building is None or door not in building.openings:
        return ""
    width = building.openings[door].get("width_m")
    params = evacuation.params
    if not width:
        return ""
    effective = max(0.0, width - 2 * params.boundary_m)
    return f" Tightest door: {width} m wide, {params.specific_flow} x ({width} - {2 * params.boundary_m:.2f}) = {params.specific_flow * effective:.2f} people per second."


def _doors(trace: Trace, evacuation, audience: str, building=None) -> list[Finding]:
    found = []
    if evacuation.bottleneck:
        found.append(Finding("risk", f"{len(evacuation.bottleneck)} doors limit the evacuation",
                             "The minimum cut: " + ", ".join(_name(building, d) for d in evacuation.bottleneck[:3]) + (" and more" if len(evacuation.bottleneck) > 3 else "")
                             + "." + _capacity_math(building, evacuation, evacuation.bottleneck[0]),
                             ("bn",), "computed"))
    plan = _result(trace, "best_door")
    for fix in getattr(plan, "fixes", ()):
        verb = "Add a door" if fix.kind == "add" else f"Widen {_name(building, fix.element)} from {fix.previous_width_m} m"
        where = " and ".join(_name(building, x) for x in fix.between)
        detail = f"{verb} between {where} to {fix.width_m} m: evacuation {fix.T_before_s} s -> {fix.T_after_s} s"
        if audience == "occupant":
            detail = f"A door between {where} would get everyone out about {fix.T_before_s - fix.T_after_s} s sooner."
        found.append(Finding("improve", f"Proposed: {fix.kind} {_name(building, fix.element)}", detail, ("best",), "computed",
                             suggestion=detail if fix.verified else None))
    return found


def _responders(plan, audience: str) -> list[Finding]:
    if plan.status == "no_route":
        return [Finding("blocker", "Responders cannot reach the target",
                        "No route from a usable entrance reaches it under the hazard.", ("resp",), "computed")]
    if plan.status == "deadline_unmet":
        return [Finding("risk", "Responders arrive after the deadline", f"Earliest arrival {plan.chosen.arrival_s:.0f} s.", ("resp",), "computed")]
    delay = plan.delay_s or 0
    note = f"Responders arrive at {plan.chosen.arrival_s:.0f} s and delay the evacuation by {delay} s (counterflow modelled as half the door width)."
    return [Finding("improve" if delay else "info", "Responder access", note, ("resp",), "computed")]


def why_no_route(building, start: str, end: str, constraints) -> list[Finding]:
    """No route exists under `constraints`: what would make one? Each relaxation is tried on its own and re-solved, so a
    suggestion is listed only if it really opens a route, with the length it would give."""
    from dataclasses import replace

    from floorwise.core.fixes import smallest_fix
    from floorwise.core.routing import NoRoute, plan_route

    def length(candidate) -> float | None:
        try:
            return plan_route(building, [start, end], candidate).length_m
        except NoRoute:
            return None

    if length(constraints) is not None:
        return [Finding("info", "A route exists under these constraints", f"{length(constraints)} m.", ("route",), "computed")]
    found = []
    relaxations = [
        ("min_width_m", f"doors narrower than {constraints.min_width_m} m are the obstacle", replace(constraints, min_width_m=None)),
        ("step_free", "the step-free requirement is the obstacle: a route with steps exists", replace(constraints, step_free=False)),
        ("no_stairs", "avoiding stairs is the obstacle", replace(constraints, no_stairs=False)),
        ("no_lifts", "avoiding lifts is the obstacle", replace(constraints, no_lifts=False)),
    ]
    for field, reason, relaxed in relaxations:
        if getattr(constraints, field) and (metres := length(relaxed)) is not None:
            fix = smallest_fix(building, start, end, constraints) if field == "min_width_m" else None
            suggestion = None
            if fix is not None and fix.verified:
                suggestion = "Widen " + "; ".join(f"{' and '.join(w.between)} from {w.from_m} m to {w.to_m} m" for w in fix.widen) + " (re-solved: the route opens)"
            found.append(Finding("improve", f"Without that constraint a route of {metres} m exists", reason.capitalize() + ".",
                                 ("route",), "computed", suggestion))
    for element in sorted(constraints.closed):
        if (metres := length(replace(constraints, closed=constraints.closed - {element}))) is not None:
            found.append(Finding("improve", f"Reopening {element} restores a route of {metres} m", "It is the only way between the two places.",
                                 ("route",), "computed", f"Reopen {element} (re-solved: the route opens)"))
    return found or [Finding("blocker", "No single change opens a route", "Even relaxing each constraint alone does not connect the two places.", ("route",), "computed")]
