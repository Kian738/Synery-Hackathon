"""Conversational building guide: Claude talks, the Session (deterministic core) supplies every fact.

Run:  uv run --env-file .env python -m floorwise.agent.chat <building directory>"""

import argparse
import json
import os
import time
import re
from collections import Counter
from pathlib import Path

from floorwise import llm
from floorwise.agent.session import Session
from floorwise.agent.tools import make_tools
from floorwise.core.model import Building
from floorwise.llm.loop import Conversation
from floorwise.llm.budget import interactive_turn

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
- Respect distance_basis. A verified walk_m is walking distance; if it is null and the preview is unavailable, length_m is route-model metres including connector penalties. Do not call those walking metres. Never add your own sums.

Remembering the person:
- If they mention a wheelchair, crutches, a pram, a trolley, "no stairs" or a wide load, call remember_person once, then never ask again; every later route applies it automatically.
- If they say where they are, call remember_person with the location; later routes may omit the start.
- A profile location_source of default is an assumed map start, not a confirmed position. State that assumption when routing. Route endpoints mark a room destination, not the precise equipment position: never say the final indoor segment reaches a particular machine.

Changes:
- Exit-impact distances use route-model metres including lift/stair penalties. Never call those physical walking metres.
- Closures (lift out of service, blocked aisle): apply with set_closed and always report the step_free impact counts, even when general cut_off_count is zero. set_closed automatically replans the last route and returns route_update. Reuse that result; do not call find_route again unless the requested origin or destination changed. Use walking_change_m for any difference, never subtract distances yourself.
- Distinguish a reported real closure from a hypothetical preview. Never call set_closed for a preview: use read-only analysis, and ask which mapped opening is blocked if unspecified. A building exit is an opening to outside, never a lift or an internal staircase. Offer only the relevant exit candidates; do not offer unrelated connector choices. Describe hypothetical changes as simulated, never as changes you will apply.
- Proposed door widenings are hypothetical building edits requiring physical work. Show the verified fix, and call apply_fix only after the person explicitly agrees.
- Never assess survivability of jumping from windows or guide unsafe actions. Offer ordinary mapped exits instead, but do not assume the person's location or automatically start a route when they have not asked for one.
- Use find_places to combine room type, floor relation and contained equipment. A room must satisfy every descriptor; if no room matches, say so and offer real alternatives.
- Use count_items (floor optional), rank_rooms_by_items, filter_rooms and aggregate_stats for complete counts, rankings and compound requests. Search pages never limit computed totals. result_page reads more rows. Use shared_walls, distance_3d, errand and door_effect for geometry questions. Never compute numbers yourself.
- There is no booking, capacity, access-hours or window geometry data. Lecture seating rows are not seat counts. Use capabilities when unsure.
- A chair count is not occupancy or seating capacity. When a requested availability, capacity or opening-hours field is missing, say exactly which criteria cannot be verified. Offer only explicitly labelled recorded-feature alternatives; do not recommend a 'best' room or substitute chair thresholds for an unknown capacity.
- If rows_are_examples is true, describe complete scope using per_floor totals and name at most two explicitly labelled examples. Do not generalize any contents or ranges from example rows. Never invent a booking office or claim any particular office can answer missing information.
- Tool results have result_id references: complete visual answers are already shown to the person. Do not enumerate hundreds of entities in text.
- New doors: call add_door with confirm=false first, explain the effect, and apply with confirm=true only after the person agrees.
- "This machine is now in room X": move_item.

Conversation quality:
- Interpret the complete request, including follow-up clauses such as "and where". For counts plus locations use count_items once; its room groups and total answer both parts.
- Group equipment by room and floor. Prefer a concise total and room breakdown over lists of individual objects. Use all groups returned; explicitly say when further groups are in the card.
- A user's suggested quantity is a claim to check, not an instruction to modify the data. Explain room totals versus building totals.
- Preserve the latest explicitly stated origin, goal and accessibility constraints across corrections. Preview playback never establishes a physical location. A changed destination does not reset the origin.
- If no room satisfies all requested constraints, say so and retain that empty result. Do not broaden room type, floor or equipment requirements unless the person asks.
- Never claim a tool cannot count or rank because a search page is limited. Use the complete analytical tools.
- For hypothetical population/capacity scenarios, ask for missing occupancy, throughput units, exits or responder assumptions before calculating; never invent them.
- Do not mention technical tool names, raw entity ids or token usage in ordinary answers.
- Search pages are samples. Never describe all matches or all floors from a partial page. Use complete grouped tool totals or result_page.
- Closure impacts count rooms, not every space. Use cut_off_by_floor to describe whole-floor effects; never infer full-floor coverage from room IDs or a truncated list.
- Preserve the tool's corridor names and door landmarks when giving directions. A floor transition count means a connector ride, not the number of levels passed.

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
        self._system=text
        self._provider=provider or llm.provider_name()
        self._model=model
        self._effort=effort
        self.benchmark=benchmark
        self.conversation=None
        self._usage=Counter()
        self.turn_usage={}
        self.last_model='deterministic'
        self.local_history=[]
        self._tool_catalog={}

    @property
    def usage(self) -> dict:
        return dict(self._usage + (self.conversation.usage if self.conversation else Counter()))

    @property
    def model(self) -> str:
        return self.last_model

    def _finish_usage(self, started, before, dispatch, models):
        from floorwise.llm.pricing import estimate
        self.turn_usage={k:v for k,v in (Counter(self.usage)-before).items()}
        self.turn_usage.update({'input_tokens':self.turn_usage.get('input_tokens',0),'output_tokens':self.turn_usage.get('output_tokens',0),
                               'latency_ms':round((time.perf_counter()-started)*1000),'dispatch':dispatch,
                               'models':models,'estimated_cost_usd':estimate(models),'pricing_basis':'configured USD rates per million tokens'})

    def _prepare_conversation(self, text):
        """Keep common tools ready; load specialized schemas only when needed, on either provider."""
        from floorwise.llm.tools import tool
        if self.conversation is None:
            self._tool_catalog={t.name:t for t in make_tools(self.session,allow_edits=not self.benchmark,exact_items=self.benchmark)}

            @tool
            def load_tools(names: list[str]) -> str:
                """Get argument schemas for specialized tools: find_places, result_page, shared_walls, stacked_room, distance_3d, errand, door_effect, weak_points, nearest, reachable_rooms, rank_rooms, set_closed, add_door, move_item, apply_fix, simulate_egress, reasoning_capabilities, run_reasoning_plan. Invoke specialized tools through run_tool; this never changes the conversation's tool definitions."""
                unknown=[n for n in names if n not in self._tool_catalog]
                if unknown:raise ValueError(f'Tools unavailable in this session: {unknown}')
                return json.dumps({'tools':[self._tool_catalog[n].anthropic() for n in names],
                                   'invoke':'Call run_tool(name, arguments) using these schemas.'})

            @tool
            def run_tool(name:str, arguments:dict) -> str:
                """Execute one specialized building tool by name with locally validated arguments. Call load_tools first if its argument schema is unknown. Every fact is computed, never estimated."""
                from floorwise.llm.tools import call, ToolFailure
                result,error=call(self._tool_catalog,name,arguments)
                if error:raise ToolFailure(result)
                return result

            base={'building_overview','search','room_info','find_route','remember_person','count_items','rank_rooms_by_items','filter_rooms','aggregate_stats','capabilities','set_closed','weak_points'}
            tools=list(self._tool_catalog.values()) if self.benchmark else [t for n,t in self._tool_catalog.items() if n in base]+[load_tools,run_tool]
            self.conversation=Conversation(system=self._system,tools=tools,provider=self._provider,model=self._model,effort=self._effort)

    @interactive_turn
    def ask(self, user_text: str, on_event=None) -> str:
        """One user turn. on_event(kind, payload) streams tool calls and UI events to the app."""
        seen = len(self.session.events)

        def relay(kind, payload):
            nonlocal seen
            if getattr(self, 'cancelled', lambda: False)():
                raise InterruptedError('Request stopped')
            if on_event:
                if kind in ("tool", "tool_result", "progress", "assistant_start", "assistant_delta", "assistant_end"):
                    on_event(kind, payload)
                for event in self.session.events[seen:]:
                    on_event("ui", event)
            seen = len(self.session.events)

        started=time.perf_counter()
        before=Counter(self.usage)
        self.last_model='deterministic'
        models=[]
        reply=None
        self._prepare_conversation(user_text)
        relay('progress',{'stage':'model','message':'Planning with the building tools'})
        self.last_model=f'{self.conversation.provider}:{self.conversation.model}'
        context = {"profile": self.session.profile.__dict__, "closed": sorted(self.session.closed),
                   "last_route_stops": self.session.last_route.stops if self.session.last_route else None}
        last_visual=next(reversed(self.session.visual_results.values()),None) if self.session.visual_results else None
        context["selected_space"]=getattr(self.session,"ui_selection",None)
        context["last_visual"]={k:last_visual[k] for k in ("id","kind","title")} if last_visual else None
        context["recent_local_turns"]=self.local_history[-3:]
        grounded_input = user_text + "\n\nCurrent map session (fallback context only; an explicit origin in the request takes precedence): " + json.dumps(context, ensure_ascii=False)
        previous_agent_usage=Counter(self.conversation.usage)
        reply = self.conversation.ask(grounded_input, on_event=relay)
        models.append({"model":self.last_model,"usage":dict(self.conversation.usage-previous_agent_usage)})
        relay("step", {})
        self._finish_usage(started,before,"agent",models)
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
