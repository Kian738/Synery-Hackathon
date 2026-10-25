"""Session-scoped insight endpoints; helpers are injected to avoid importing app twice."""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Literal


class WidenBody(BaseModel):
    opening_id: str
    width_m: float = Field(gt=0, le=20)


class ProfileBody(BaseModel):
    step_free: bool | None = None
    min_door_width_m: float | None = Field(default=None, gt=0, le=20)
    location: str | None = None
    location_source: Literal['default','declared','link'] | None = None


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
            changed = (body.step_free is not None and body.step_free != session.profile.step_free) or (
                'min_door_width_m' in body.model_fields_set and body.min_door_width_m != session.profile.min_door_width_m)
            location_changed=body.location is not None and session.place(body.location)!=session.profile.location
            if body.location is not None:
                session.profile.location = session.place(body.location)
                session.profile.location_source = body.location_source or 'declared'
            if body.step_free is not None:
                session.profile.step_free = body.step_free
            if 'min_door_width_m' in body.model_fields_set:
                session.profile.min_door_width_m = body.min_door_width_m
            update = None
            request = getattr(session, 'last_route_request', None)
            if (changed or location_changed) and request:
                start, destination, via, kwargs = request
                if location_changed:start=session.profile.location
                kwargs = dict(kwargs)
                if body.step_free is not None:kwargs['step_free']=session.profile.step_free
                if 'min_door_width_m' in body.model_fields_set:kwargs['min_door_width_m']=session.profile.min_door_width_m
                update = session.route(start, destination, via, **kwargs)
            events, session.events[:] = list(session.events), []
            return {'profile': session.profile.__dict__, 'events': events, 'route_update': update}

    return router
