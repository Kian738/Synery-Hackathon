from server.locks import session_write
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict, StrictInt
from server.scenario import ScenarioBody as TemplateBody, scenario_router


class ScenarioBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    occupants: dict[str,StrictInt]
    door_rate_per_minute: float = Field(gt=0,le=10000)
    closed: list[str] = []
    responder_target: str | None = None
    responder_entrance: str | None = None


def router(get_session, call):
    api=APIRouter()
    legacy=scenario_router(get_session)
    run_template=next(route.endpoint for route in legacy.routes if route.path.endswith('/scenario'))
    legacy.routes[:]=[route for route in legacy.routes if not route.path.endswith('/scenario')]
    api.include_router(legacy)
    @api.post('/api/sessions/{session_id}/scenario')
    async def scenario(session_id:str,body:ScenarioBody|TemplateBody):
        if isinstance(body,TemplateBody):return await asyncio.to_thread(run_template,session_id,body)
        entry=get_session(session_id)
        def work():
            from floorwise.agent.scenarios import simulate
            with session_write(entry):
                before=len(entry['session'].events)
                result=simulate(entry['session'],**body.model_dump())
                return {'result':result,'events':entry['session'].events[before:]}
        try:return await asyncio.to_thread(work)
        except (ValueError,KeyError) as e:raise HTTPException(422,str(e)) from e
    return api
