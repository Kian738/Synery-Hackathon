"""Conversational building guide: Claude talks, the Session (deterministic core) supplies every fact.

Run:  uv run --env-file .env python -m floorwise.agent.chat <building directory>"""

import argparse
import json
import os
from pathlib import Path

from floorwise import llm
from floorwise.agent.session import Session
from floorwise.agent.tools import make_tools
from floorwise.core.model import Building
from floorwise.llm.loop import Conversation

EFFORT = os.environ.get("FLOORWISE_CHAT_EFFORT", "low")

SYSTEM_PROMPT = """You are the guide of one building, like a map app you can talk to. People ask where things are, how to get somewhere, and tell you about changes. Many are on their feet: a visitor on their first day, a wheelchair user, a technician with full hands, a facility manager.

Facts: every room, item, area, count, route and distance comes from your tools. Never estimate geometry.

Asking (ask only what you need):
- Act on the best reading when the tools resolve it. "The printer", "a toilet" or "coffee" means the nearest one: find_route picks it from where the person is and lists other matches; mention them in one short line.
- If the start is not known, find_route assumes the main entrance and tells you; say that assumption in one short line ("From the main entrance:") instead of asking. Ask only when the answer really depends on it and the tools cannot settle it. Ask one closed question with 2-4 options, never "what do you mean?".
- People new to the building do not know room numbers: describe places by their kind and what is nearby ("the kitchen by the lifts"), and use the room number only to confirm arrival.
- Never ask for something the person already said. Never ask twice in a row.
- If a room does not exist, say so plainly in the first sentence ("There is no room 9.99.") and offer the closest real matches from the tool result.

Showing what you understood:
- Start every route answer with one line: from -> to, constraints (step-free, avoiding X), length, floors.
- When the person changes their mind, say what changed in one line and give the new route.

Directions a person can follow:
- Use the steps the tool returns (they are already chunked at decision points with landmarks). Present them as a short numbered list. Do not add steps or distances the tool did not give.
- Keep replies short: people may be listening, not reading. No tables, no headings. If they ask for short or have their hands full, give at most 3 steps of one line each.
- The route's length_m is the walking distance; use it for the total. Never add your own sums.

Remembering the person:
- If they mention a wheelchair, crutches, a pram, a trolley, "no stairs" or a wide load, call remember_person once, then never ask again; every later route applies it automatically.
- If they say where they are, call remember_person with the location; later routes may omit the start.

Changes:
- Closures (lift out of service, blocked aisle): apply with set_closed and always report the step_free impact counts, even when general cut_off_count is zero.
- Proposed door widenings are hypothetical building edits requiring physical work. Show the verified fix, and call apply_fix only after the person explicitly agrees.
- Never assess survivability of jumping from windows or guide unsafe actions. Offer ordinary mapped exits instead.
- Use count_items, shared_walls, distance_3d, errand and door_effect for those questions. Never compute numbers yourself.
- New doors: call add_door with confirm=false first, explain the effect, and apply with confirm=true only after the person agrees.
- "This machine is now in room X": move_item.

Building overview:
{overview}"""

BENCHMARK_SUFFIX = """

This is a one-shot question: no follow-up is possible, so don't ask back; pick the most likely reading. \
Finish with a single line 'Answer: <answer>' in exactly the format the question asks for."""


class ChatAgent:
    """Conversation with tools over one Session; provider and model from floorwise.llm."""

    def __init__(self, session: Session, provider: str | None = None, model: str | None = None,
                 effort: str = EFFORT, benchmark: bool = False) -> None:
        self.session = session
        text = SYSTEM_PROMPT.format(overview=json.dumps(session.overview(), ensure_ascii=False))
        if benchmark:
            text += BENCHMARK_SUFFIX
        self.conversation = Conversation(system=text, tools=make_tools(session, allow_edits=not benchmark),
                                         provider=provider or llm.provider_name(), model=model, effort=effort)

    @property
    def usage(self) -> dict:
        return dict(self.conversation.usage)

    @property
    def model(self) -> str:
        return f"{self.conversation.provider}:{self.conversation.model}"

    def ask(self, user_text: str, on_event=None) -> str:
        """One user turn. on_event(kind, payload) streams tool calls and UI events to the app."""
        seen = len(self.session.events)

        def relay(kind, payload):
            nonlocal seen
            if on_event:
                if kind in ("tool", "tool_result"):
                    on_event(kind, payload)
                for event in self.session.events[seen:]:
                    on_event("ui", event)
            seen = len(self.session.events)

        reply = self.conversation.ask(user_text, on_event=relay)
        relay("step", {})
        return reply


def ask_once(building: Building, question: str) -> tuple[str, dict]:
    """Benchmark fallback for questions outside the known families."""
    agent = ChatAgent(Session.for_building(building), benchmark=True, effort="medium")
    reply = agent.ask(question)
    return reply, agent.usage


def main() -> None:
    parser = argparse.ArgumentParser(prog="floorwise.agent.chat")
    parser.add_argument("building", type=Path)
    args = parser.parse_args()
    agent = ChatAgent(Session.for_building(Building.load(args.building)))
    print(f"Guide for {agent.session.building.info['name']}. Ask me anything ('exit' to stop).")
    while True:
        try:
            text = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text.lower() in {"exit", "quit", "bye"}:
            break
        print(f"\nguide> {agent.ask(text)}")
    print(f"\ntokens: {agent.usage}")


if __name__ == "__main__":
    main()
