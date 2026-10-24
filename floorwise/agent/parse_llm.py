"""LLM as a semantic parser: question -> QuerySpec (structured output). The model only extracts what the
question says; entity linking and every number stay deterministic. Used when the rule parser does not
recognise the wording (new phrasings on the Sunday building). Provider: see floorwise.llm."""

from floorwise.agent.spec import QuerySpec
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
- route: how to get from start to destination; step_free if the person needs it; closed if a lift/stair is closed.
- tour: visit stops in order (stops, start first).
- other: anything else.

Use the vocabulary below to normalise words (e.g. "WCs" -> the matching room type), but keep names of \
specific rooms as written."""


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
        spec, usage = structured.parse("parser", SYSTEM, f"{vocabulary}\n\nQuestion: {question}", QuerySpec,
                                       provider=self.provider, model=self.model)
        return spec, dict(usage)
