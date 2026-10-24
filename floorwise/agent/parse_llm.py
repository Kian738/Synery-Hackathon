"""Claude as a semantic parser: question -> QuerySpec (structured output). Claude only extracts what the
question says; entity linking and every number stay deterministic. Used when the rule parser does not
recognise the wording (new phrasings on the Sunday building)."""

import os

import anthropic

from floorwise.agent.spec import QuerySpec
from floorwise.core import resolve as R
from floorwise.core.model import Building

DEFAULT_MODEL = os.environ.get("FLOORWISE_PARSER_MODEL", "claude-haiku-5-5")

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
- other: anything else.

Use the vocabulary below to normalise words (e.g. "WCs" -> the matching room type), but keep names of \
specific rooms as written."""


class LLMParser:
    def __init__(self, model: str = DEFAULT_MODEL, client: anthropic.Anthropic | None = None) -> None:
        self.model = model
        self.client = client or anthropic.Anthropic()

    def parse(self, building: Building, question: str) -> tuple[QuerySpec | None, dict]:
        vocabulary = (
            f"Floors: {', '.join(f['name'] for f in sorted(building.floors.values(), key=lambda f: f['level']))}\n"
            f"Room types: {', '.join(sorted(R.room_types(building)))}\n"
            f"Item types: {', '.join(sorted(R.asset_types(building)))}\n"
            f"Stairs and lifts: {', '.join(c['name'] for c in building.connectors.values())}"
        )
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=4000,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"{vocabulary}\n\nQuestion: {question}"}],
            output_format=QuerySpec,
            output_config={"effort": "low"},
        )
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_read_input_tokens": response.usage.cache_read_input_tokens or 0,
            "cache_creation_input_tokens": response.usage.cache_creation_input_tokens or 0,
        }
        if response.stop_reason == "refusal":
            return None, usage
        return response.parsed_output, usage
