"""LLM as a semantic parser: question -> QuerySpec (structured output). The model only extracts what the
question says; entity linking and every number stay deterministic. Used when the rule parser does not
recognise the wording (new phrasings on the Sunday building). Provider: see floorwise.llm."""

from typing import Literal

from pydantic import BaseModel

from floorwise.agent.spec import Kind, QuerySpec
from floorwise.core import resolve as R
from floorwise.core.model import Building
from floorwise.llm import structured

SYSTEM = """You turn a question about a building into a QuerySpec. Copy room names, floors and items \
exactly as the question writes them (keep the "(Floor 2)" part with a room). Do not compute anything.

Question families (kind):
- largest_room: largest room of a type on a floor (and its area).
- floor_area_total: total area of all rooms of a type on a floor.
- errand: start in a room, fetch the nearest item of a type, carry it to the largest room of a type on a \
floor; total walking distance. stairs_allowed=false only if the person cannot use stairs.
- wide_delivery_count: something of a given width (min_width, metres) enters at a room, no stairs/steps, \
lifts fine; how many rooms on a floor it can reach.
- step_free_reachable_count: a lift or staircase (closed) is out of service; a wheelchair user enters at a \
room (start); how many rooms on a floor they can reach.
- room_stacked: which room is directly above or below a room (direction). Water dripping from a ceiling \
means above; leaking onto a floor means below.
- shared_walls_count: how many rooms share a wall with a room (start).
- straight_line_3d: straight-line distance between the centres of two rooms (first, second).
- what_if_door: add a door between two rooms (first, second); how many rooms on another floor (floor) get \
a shorter walk out of the building.
- locate: where is an item (item).
- count: how many items of a type on a floor (item, floor).
- route: how to get from start to destination; step_free if the person needs it; closed if a lift/stair/room/door is closed or blocked (closed_more for further closed places). Rules that may be stated: without stairs (stairs_allowed=false: lifts, ramps and doors only), a forklift (forklift=true: aisles and openings of 3 m or wider), production bays are destinations that may be entered but not crossed as a shortcut (bays_destinations=true), places to avoid (avoid).
- tour: visit stops in order (stops, start first); the same route rules apply.
- other: anything else.

Use the vocabulary below to normalise words (e.g. "WCs" -> the matching room type), but keep names of \
specific rooms as written."""


class WireQuery(BaseModel):
    """Flat on purpose: no optional/union fields (strict structured output rejects deep unions as too complex).
    Empty string / 0 / [] means "not mentioned"."""

    kind: Kind
    floor: str = ""
    room_type: str = ""
    asset_type: str = ""
    item: str = ""
    start: str = ""
    destination: str = ""
    first: str = ""
    second: str = ""
    closed: str = ""
    min_width: float = 0.0
    direction: Literal["above", "below", ""] = ""
    stops: list[str] = []
    step_free: bool = False
    stairs_allowed: bool = True
    forklift: bool = False
    bays_destinations: bool = False
    avoid: list[str] = []
    closed_more: list[str] = []

    def to_spec(self) -> QuerySpec:
        data = {k: v for k, v in self.model_dump().items() if v not in ("", [], 0.0)}
        data["step_free"] = self.step_free or None
        data["stairs_allowed"] = None if self.stairs_allowed else False
        data["forklift"] = self.forklift or None
        data["bays_destinations"] = self.bays_destinations or None
        return QuerySpec(**data)


class LLMParser:
    def __init__(self, model: str | None = None, provider: str | None = None) -> None:
        self.model, self.provider = model, provider

    def parse(self, building: Building, question: str) -> tuple[QuerySpec | None, dict]:
        vocabulary = (
            f"Floors: {', '.join(f['name'] for f in sorted(building.floors.values(), key=lambda f: f['level']))}\n"
            f"Room types: {', '.join(sorted(R.room_types(building)))}\n"
            f"Item types: {', '.join(sorted(R.asset_types(building)))}\n"
            f"Stairs and lifts: {', '.join(c['name'] for c in building.connectors.values())}"
        )
        wire, usage = structured.parse("parser", SYSTEM, f"{vocabulary}\n\nQuestion: {question}", WireQuery,
                                       provider=self.provider, model=self.model)
        return (wire.to_spec() if wire else None), dict(usage)
