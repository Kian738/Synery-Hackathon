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

Changes:
- Exit-impact distances use route-model metres including lift/stair penalties. Never call those physical walking metres.
- Closures (lift out of service, blocked aisle): apply with set_closed and always report the step_free impact counts, even when general cut_off_count is zero.
- Proposed door widenings are hypothetical building edits requiring physical work. Show the verified fix, and call apply_fix only after the person explicitly agrees.
- Never assess survivability of jumping from windows or guide unsafe actions. Offer ordinary mapped exits instead.
- Use find_places to combine room type, floor relation and contained equipment. A room must satisfy every descriptor; if no room matches, say so and offer real alternatives.
- Use count_items (floor optional), rank_rooms_by_items, filter_rooms and aggregate_stats for complete counts, rankings and compound requests. Search pages never limit computed totals. result_page reads more rows. Use shared_walls, distance_3d, errand and door_effect for geometry questions. Never compute numbers yourself.
- There is no booking, capacity, access-hours or window geometry data. Lecture seating rows are not seat counts. Use capabilities when unsure.
- Tool results have result_id references: complete visual answers are already shown to the person. Do not enumerate hundreds of entities in text.
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
                """Enable specialized tools before using them. Available names: find_places, count_items, rank_rooms_by_items, filter_rooms, aggregate_stats, result_page, capabilities, shared_walls, stacked_room, distance_3d, errand, door_effect, weak_points, nearest, reachable_rooms, rank_rooms, set_closed, add_door, move_item, apply_fix. Only tools permitted in this session can be loaded."""
                unknown=[n for n in names if n not in self._tool_catalog]
                if unknown:raise ValueError(f'Tools unavailable in this session: {unknown}')
                for name in names:
                    if name not in self.conversation.by_name:
                        self.conversation.tools.append(self._tool_catalog[name])
                        self.conversation.by_name[name]=self._tool_catalog[name]
                return json.dumps({'enabled':names})

            base={'building_overview','search','room_info','find_route','remember_person'}
            tools=list(self._tool_catalog.values()) if self.benchmark else [t for n,t in self._tool_catalog.items() if n in base]+[load_tools]
            self.conversation=Conversation(system=self._system,tools=tools,provider=self._provider,model=self._model,effort=self._effort)
        groups=[
            (r'closed|blocked|maintenance|reopen',{'set_closed','weak_points'}),
            (r'count|most|many|rank',{'count_items','rank_rooms_by_items','aggregate_stats','result_page'}),
            (r'with|contains|equipment|upstairs|downstairs',{'find_places','filter_rooms'}),
            (r'door|widen|trolley|pallet',{'add_door','door_effect','apply_fix','reachable_rooms'}),
            (r'move|moved',{'move_item'}),
            (r'above|below|wall|straight.line|3d distance',{'stacked_room','shared_walls','distance_3d'}),
            (r'nearest|closest|fetch|errand',{'nearest','errand'}),
            (r'largest|area|biggest',{'rank_rooms','aggregate_stats'}),
            (r'tools|capabilit|available|booking|seats',{'capabilities'}),
        ]
        for pattern,names in groups:
            if re.search(pattern,text,re.I):
                for name in sorted(names):
                    if name in self._tool_catalog and name not in self.conversation.by_name:
                        self.conversation.tools.append(self._tool_catalog[name]);self.conversation.by_name[name]=self._tool_catalog[name]

    @interactive_turn
    def ask(self, user_text: str, on_event=None) -> str:
        """One user turn. on_event(kind, payload) streams tool calls and UI events to the app."""
        seen = len(self.session.events)

        def relay(kind, payload):
            nonlocal seen
            if on_event:
                if kind in ("tool", "tool_result", "progress", "text_delta", "clear_deltas"):
                    on_event(kind, payload)
                for event in self.session.events[seen:]:
                    on_event("ui", event)
            seen = len(self.session.events)

        started=time.perf_counter()
        before=Counter(self.usage)
        self.last_model='deterministic'
        models=[]
        reply=None
        if not self.benchmark:
            from floorwise.agent.local import dispatch, execute_spec
            from floorwise.core.resolve import ResolveError
            try:
                relay('progress',{'stage':'compute','message':'Checking building data'})
                reply=dispatch(self.session,user_text)
                complex_request=re.search(r'\b(?:closed|blocked|maintenance|reopen|avoid|without|except|prefer|widen|move|moved|apply|approve|via|then|fetch|carry|upstairs|downstairs|containing)\b|\bwith\b|next to|add (?:a )?door|pick up',user_text,re.I)
                if reply is None and not complex_request and llm.info().available:
                    relay('progress',{'stage':'parse','message':'Understanding your request'})
                    from floorwise.agent.parse_llm import LLMParser
                    spec,usage=LLMParser(provider=self._provider).parse(self.session.building,user_text)
                    self._usage.update(usage)
                    self.last_model=f'{self._provider}:{llm.model_for("parser",self._provider)}'
                    models.append({'model':self.last_model,'usage':dict(usage)})
                    if spec and spec.kind!='other':
                        reply=execute_spec(self.session,spec)
            except ResolveError as error:
                choices=error.candidates[:4]
                reply=str(error) + (' Choose: '+ '; '.join(c.get('label',c.get('id','')) for c in choices) if choices else '')
            except (ValueError, KeyError):
                # Unknown syntax or unsupported parse: the full agent can recover using tools.
                reply=None
        if reply is not None:
            self.local_history=(self.local_history+[{'user':user_text,'reply':reply}])[-6:]
            relay('step',{})
            if on_event:
                for part in re.split(r'(\n+|(?<=[.!?])\s+)', reply):
                    if part:
                        on_event("text_delta", {"text": part})
            self._finish_usage(started,before,'deterministic' if self.last_model=='deterministic' else 'parser',models)
            return reply
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
