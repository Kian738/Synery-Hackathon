"""Scenario endpoints: run a verified multi-hop plan on a session's building and say what to ask next.

POST /api/sessions/{id}/scenario        run a template ("evacuation", "delivery", "maintenance_closure"); returns the
                                        step-by-step trace, findings for the audience, and for evacuation the schedule
POST /api/sessions/{id}/scenario/ask    the single most important missing input for a partial scenario, or null
Every number is the output of a checked step; the UI only words and draws it."""
import json
import queue
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from server.locks import session_write

from floorwise.evacuation import to_dict
from floorwise.reason import PlanError, ScenarioSpec
from floorwise.reason.report import robust_report, scenario_report
from floorwise.reason.elicit import next_question
from floorwise.reason.findings import AUDIENCES, assess
from floorwise.reason.templates import TemplateError, instantiate, template_names


class DirectScenarioBody(BaseModel):
    occupants: dict[str, int]
    door_rate_per_minute: float = Field(gt=0, le=10000)
    closed: list[str] = []
    responder_target: str | None = None
    responder_entrance: str | None = None


class ScenarioBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    template: str = "evacuation"
    params: dict = Field(default_factory=dict)
    audience: str = "safety_officer"


class AskBody(BaseModel):
    spec: dict = Field(default_factory=dict)


def scenario_router(get_session):
    router = APIRouter(prefix="/api/sessions")

    @router.post("/{session_id}/scenario")
    def run(session_id: str, body: dict):
        if "occupants" in body or "door_rate_per_minute" in body:
            try:
                direct = DirectScenarioBody(**body)
            except Exception as e:
                raise HTTPException(422, str(e)) from e
            entry = get_session(session_id)
            from floorwise.agent.scenarios import simulate
            with session_write(entry):
                before = len(entry["session"].events)
                result = simulate(entry["session"], **direct.model_dump())
                return {"result": result, "events": entry["session"].events[before:]}

        try:
            template_body = ScenarioBody(**body)
        except Exception as e:
            raise HTTPException(422, str(e)) from e

        if template_body.audience not in AUDIENCES:
            raise HTTPException(422, f"audience must be one of {list(AUDIENCES)}")
        entry = get_session(session_id)
        try:
            instantiate(template_body.template, **template_body.params)
        except TemplateError as error:
            raise HTTPException(422, {"error": str(error), "templates": list(template_names())}) from error
        with session_write(entry):
            try:
                report = scenario_report(entry["session"].building, template_body.template, template_body.params, template_body.audience)
            except PlanError as error:
                raise HTTPException(422, str(error)) from error
        return report

    @router.post("/{session_id}/scenario/stream")
    def stream(session_id: str, body: ScenarioBody):
        """Same run as /scenario, as lines of JSON: one {"step": ...} per checked step as it finishes, then {"report": ...}
        (or {"error": ...}). The panel shows the live step; the reasoning is visible while it happens."""
        if body.audience not in AUDIENCES:
            raise HTTPException(422, f"audience must be one of {list(AUDIENCES)}")
        entry = get_session(session_id)
        try:
            instantiate(body.template, **body.params)
        except TemplateError as error:
            raise HTTPException(422, {"error": str(error), "templates": list(template_names())}) from error
        lines: queue.Queue = queue.Queue()

        def work() -> None:
            try:
                with entry["lock"]:
                    report = scenario_report(entry["session"].building, body.template, body.params, body.audience,
                                             on_step=lambda step: lines.put({"step": step}))
                lines.put({"report": report})
            except Exception as error:  # noqa: BLE001  the stream must always end with a result or an error line
                lines.put({"error": str(error)})
            lines.put(None)

        threading.Thread(target=work, daemon=True).start()

        def generate():
            while (item := lines.get()) is not None:
                yield json.dumps(item, ensure_ascii=False, default=str) + chr(10)

        return StreamingResponse(generate(), media_type="application/x-ndjson")

    @router.post("/{session_id}/scenario/robust")
    def robust(session_id: str, body: ScenarioBody):
        entry = get_session(session_id)
        with session_write(entry):
            try:
                return robust_report(entry["session"].building, body.params.get("spec", {}))
            except (ValueError, TypeError, KeyError) as error:
                raise HTTPException(422, str(error)) from error

    @router.post("/{session_id}/scenario/ask")
    def ask(session_id: str, body: AskBody):
        entry = get_session(session_id)
        try:
            spec = ScenarioSpec.from_dict(body.spec)
        except (ValueError, TypeError) as error:
            raise HTTPException(422, str(error)) from error
        question = next_question(spec, entry["session"].building)
        return {"question": None if question is None else to_dict(question)}

    return router
