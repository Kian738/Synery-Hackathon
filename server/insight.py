"""Session-scoped insight endpoints; helpers are injected to avoid importing app twice."""
from fastapi import APIRouter
from pydantic import BaseModel, Field


class WidenBody(BaseModel):
    opening_id: str
    width_m: float = Field(gt=0, le=20)


class ProfileBody(BaseModel):
    step_free: bool | None = None
    min_door_width_m: float | None = Field(default=None, gt=0, le=20)
    location: str | None = None


def insight_router(get_session, call):
    router = APIRouter(prefix='/api/sessions')

    @router.post('/{session_id}/widen')
    def widen(session_id: str, body: WidenBody):
        entry = get_session(session_id)
        with entry['lock']:
            return call(entry['session'], 'widen_door', body.opening_id, body.width_m)

    @router.get('/{session_id}/weak-points')
    def weak_points(session_id: str, step_free: bool = True):
        entry = get_session(session_id)
        with entry['lock']:
            return call(entry['session'], 'weak_points', step_free)

    @router.post('/{session_id}/profile')
    def profile(session_id: str, body: ProfileBody):
        entry = get_session(session_id)
        with entry['lock']:
            session = entry['session']
            if body.location is not None:
                session.profile.location = session.place(body.location)
            if body.step_free is not None:
                session.profile.step_free = body.step_free
            if 'min_door_width_m' in body.model_fields_set:
                session.profile.min_door_width_m = body.min_door_width_m
            return {'profile': session.profile.__dict__}

    return router
