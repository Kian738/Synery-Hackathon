"""HTTP face of the evacuation stress test (floorwise.stress): run it on a session's building (edits and closures included) and ask where a new door should go."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from floorwise.stress.doors import recommend
from floorwise.stress.sim import Spec, run


class StressBody(BaseModel):
    kind: str = Field("evacuation", pattern="^(evacuation|step_free_evacuation)$")
    closed: list[str] = []
    occupants: dict[str, int] | None = None
    pre_movement_median_s: float = Field(30.0, ge=0.0, le=600.0)
    seed: int = 7
    top: int = Field(5, ge=1, le=10)


def create_stress_router(session_or_404) -> APIRouter:
    router = APIRouter(prefix="/api/sessions/{session_id}/stress")

    def spec_of(entry, body: StressBody) -> Spec:
        session = entry["session"]
        building = session.building
        unknown = [c for c in body.closed if c not in building.openings and c not in building.connectors and c not in building.spaces]
        if unknown:
            raise HTTPException(422, f"Unknown element(s) to close: {', '.join(unknown[:3])}")
        occupants = body.occupants
        if occupants is not None:
            bad = [s for s in occupants if s not in building.spaces]
            if bad:
                raise HTTPException(422, f"Unknown room(s): {', '.join(bad[:3])}")
            occupants = {s: max(0, min(int(n), 5000)) for s, n in occupants.items()}
        closed = frozenset(set(body.closed) | set(session.closed))
        return Spec(kind=body.kind, occupants=occupants, closed=closed, pre_movement_median_s=body.pre_movement_median_s, seed=body.seed)

    @router.post("")
    def stress(session_id: str, body: StressBody) -> dict:
        entry = session_or_404(session_id)
        result = run(entry["session"].building, spec_of(entry, body))
        frames = {sid: head for sid, head in result.frames.get("rooms", {}).items() if max(head) > 0}
        return {"kpis": result.kpis, "doors": result.doors[:40], "rooms": result.rooms, "frames": {"step_s": result.frames.get("step_s", 1.0), "rooms": frames},
                "flags": result.flags, "assumptions": result.assumptions}

    @router.post("/doors")
    def stress_doors(session_id: str, body: StressBody) -> dict:
        entry = session_or_404(session_id)
        return recommend(entry["session"].building, spec_of(entry, body), top=body.top)

    return router
