"""Scenario endpoints: run a verified multi-hop plan on a session's building and say what to ask next.

POST /api/sessions/{id}/scenario        run a template ("evacuation", "delivery", "maintenance_closure"); returns the
                                        step-by-step trace, findings for the audience, and for evacuation the schedule
POST /api/sessions/{id}/scenario/ask    the single most important missing input for a partial scenario, or null
Every number is the output of a checked step; the UI only words and draws it."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from floorwise.evacuation import to_dict
from floorwise.reason import PlanError, ScenarioSpec
from floorwise.reason.report import scenario_report
from floorwise.reason.elicit import next_question
from floorwise.reason.findings import AUDIENCES, assess
from floorwise.reason.templates import TemplateError, instantiate, template_names


class ScenarioBody(BaseModel):
    template: str = "evacuation"
    params: dict = Field(default_factory=dict)
    audience: str = "safety_officer"


class AskBody(BaseModel):
    spec: dict = Field(default_factory=dict)


def scenario_router(get_session):
    router = APIRouter(prefix="/api/sessions")

    @router.post("/{session_id}/scenario")
    def run(session_id: str, body: ScenarioBody):
        if body.audience not in AUDIENCES:
            raise HTTPException(422, f"audience must be one of {list(AUDIENCES)}")
        entry = get_session(session_id)
        try:
            instantiate(body.template, **body.params)
        except TemplateError as error:
            raise HTTPException(422, {"error": str(error), "templates": list(template_names())}) from error
        with entry["lock"]:
            try:
                report = scenario_report(entry["session"].building, body.template, body.params, body.audience)
            except PlanError as error:
                raise HTTPException(422, str(error)) from error
        return report

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
