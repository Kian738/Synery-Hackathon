"""One scenario run as a plain dict: the shape the REST API returns and the chat tool hands to Claude."""
from dataclasses import asdict

from floorwise.core.model import Building
from floorwise.evacuation import to_dict
from floorwise.reason.execute import run_plan
from floorwise.reason.findings import assess
from floorwise.reason.templates import instantiate


def scenario_report(building: Building, template: str, params: dict, audience: str) -> dict:
    trace = run_plan(building, instantiate(template, **params))
    evacuation = next((r.value for r in trace.results if r.op == "evacuate" and r.ok), None)
    return {
        "template": template,
        "steps": [{"id": r.id, "op": r.op, "ok": r.ok, "summary": getattr(r, "summary", "") or "",
                   "reason": r.reason, "ms": round(r.ms, 1)} for r in trace.results],
        "abstained": None if trace.abstained is None else asdict(trace.abstained),
        "answer": to_dict(trace.answer),
        "evacuation": None if evacuation is None else to_dict(evacuation),
        "findings": [asdict(f) for f in assess(trace, audience, building)] if evacuation is not None or trace.abstained else [],
    }
