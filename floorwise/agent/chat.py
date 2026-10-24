"""Conversational building guide: Claude talks, the Session (deterministic core) supplies every fact.

Run:  uv run --env-file .env python -m floorwise.agent.chat <building directory>"""

import argparse
import json
import os
from pathlib import Path

import anthropic

from floorwise.agent.session import Session
from floorwise.agent.tools import make_tools
from floorwise.core.model import Building

MODEL = os.environ.get("FLOORWISE_CHAT_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("FLOORWISE_CHAT_EFFORT", "low")
MAX_TOKENS = 16000
MAX_TOOL_ITERATIONS = 16
FALLBACK_BETA = "server-side-fallback-2026-07-01"

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
    def __init__(self, session: Session, client: anthropic.Anthropic | None = None, model: str = MODEL,
                 effort: str = EFFORT, benchmark: bool = False) -> None:
        self.session = session
        self.client = client or anthropic.Anthropic()
        self.model, self.effort = model, effort
        self.tools = make_tools(session, allow_edits=not benchmark)
        text = SYSTEM_PROMPT.format(overview=json.dumps(session.overview(), ensure_ascii=False))
        if benchmark:
            text += BENCHMARK_SUFFIX
        self.system = [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
        self.messages: list[dict] = []
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}

    def ask(self, user_text: str, on_event=None) -> str:
        """One user turn. on_event(kind, payload) streams tool calls and UI events to the app."""
        self.messages.append({"role": "user", "content": user_text})
        runner = self.client.beta.messages.tool_runner(
            model=self.model,
            max_tokens=MAX_TOKENS,
            max_iterations=MAX_TOOL_ITERATIONS,
            system=self.system,
            tools=self.tools,
            messages=list(self.messages),
            output_config={"effort": self.effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        final = None
        seen_events = len(self.session.events)
        for message in runner:
            final = message
            self._track(message)
            self.messages.append({"role": "assistant", "content": message.content})
            if on_event:
                for block in message.content:
                    if block.type == "tool_use":
                        on_event("tool", {"name": block.name, "input": block.input})
            tool_response = runner.generate_tool_call_response()
            if tool_response is not None:
                self.messages.append(tool_response)
            if on_event:
                for event in self.session.events[seen_events:]:
                    on_event("ui", event)
                seen_events = len(self.session.events)
        if final is None:
            return "(no response)"
        if final.stop_reason == "refusal":
            return "Sorry, I can't help with that request."
        return "\n".join(block.text for block in final.content if block.type == "text").strip()

    def _track(self, message) -> None:
        usage = message.usage
        self.usage["input_tokens"] += usage.input_tokens
        self.usage["output_tokens"] += usage.output_tokens
        self.usage["cache_read_input_tokens"] += usage.cache_read_input_tokens or 0
        self.usage["cache_creation_input_tokens"] += usage.cache_creation_input_tokens or 0


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
