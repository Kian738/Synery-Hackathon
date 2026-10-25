import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


class ScenarioBody(BaseModel):
    occupants: dict[str,int]
    door_rate_per_minute: float = Field(gt=0,le=10000)
    closed: list[str] = []
    responder_target: str | None = None
    responder_entrance: str | None = None


def router(get_session, call):
    api=APIRouter(prefix='/api/sessions')
    @api.post('/{session_id}/scenario')
    async def scenario(session_id:str,body:ScenarioBody):
        entry=get_session(session_id)
        def work():
            from floorwise.agent.scenarios import simulate
            with entry['lock']:
                before=len(entry['session'].events)
                result=simulate(entry['session'],**body.model_dump())
                return {'result':result,'events':entry['session'].events[before:]}
        try:return await asyncio.to_thread(work)
        except (ValueError,KeyError) as e:raise HTTPException(422,str(e)) from e
    return api
