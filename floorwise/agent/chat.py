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

SYSTEM_PROMPT = """You are the indoor guide for one building: like a map app, but you can talk. People ask \
where things are, how to get somewhere, and tell you about changes.

Ground rules:
- Every fact (rooms, items, areas, routes, distances, counts) comes from your tools. Never estimate geometry \
yourself; the tools compute it exactly.
- Ask back only when the answer depends on it: if a name fits several places and their words don't settle \
it, ask one short question listing at most 3 options. If one match is clearly meant, go ahead.
- Before acting, say in one short line what you understood (from, to, constraints like step-free, avoid X). \
Then give directions as a short numbered list a person can follow while walking: room names, landmarks, \
turns, lifts or stairs, then the total distance. Keep it brief; they may be listening, not reading.
- Remember the person: if they mention a wheelchair, crutches, pram, trolley or a wide load, call \
remember_person once and apply it to every later route without asking again. Same for where they are.
- "Avoid X and Y" means the route must not pass through them (avoid); "if possible" or "quiet" means \
prefer_avoid. If a constrained route is impossible, say so and offer the closest alternative.
- Changes (closures, new doors, moved items): for doors, preview first, tell the person the effect, and \
apply only after they agree. After a closure, say who is affected (e.g. rooms that lose step-free access).
- If something does not exist (a room number that isn't there), say so and suggest the nearest matches.

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
                if kind == "tool":
                    on_event("tool", payload)
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
