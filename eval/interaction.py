"""L6: scripted conversations with tricky users, graded like the Interaction jury (25 points):
does the agent ask only what it needs, show what it understood, and give directions a person can follow?

Each scenario has user turns plus deterministic checks on the tool calls (e.g. the second route of a
wheelchair user must be step-free without asking again; a door is only added after the person agrees).
A Claude judge then scores the transcript against the rubric.

  uv run --env-file .env python -m eval.interaction [--only wheelchair] [--judge-model claude-opus-5-5]"""

import argparse
import json
from dataclasses import dataclass, field

from pydantic import BaseModel

from eval.ledger import Ledger
from floorwise.agent.chat import ChatAgent
from floorwise.agent.session import Session
from floorwise.core.model import Building
from floorwise.llm import model_for, structured
from floorwise.paths import DATA

FACTORY = DATA / "dev" / "proc-factory-dev-003"
CAMPUS = DATA / "dev" / "proc-campus-dev-000"


@dataclass
class Scenario:
    name: str
    building: object
    persona: str
    turns: list[str]
    checks: list = field(default_factory=list)  # callables(calls, replies) -> (ok, note)


def calls_named(calls, name):
    return [c for c in calls if c["name"] == name]


def check_second_route_step_free(calls, replies):
    routes = calls_named(calls, "find_route")
    remembered = any(c["input"].get("step_free") for c in calls_named(calls, "remember_person"))
    if len(routes) < 2:
        return False, f"expected 2 routes, got {len(routes)}"
    last = routes[-1]["input"]
    ok = last.get("step_free") is True or (last.get("step_free") is None and remembered)
    return ok, "second route step-free" if ok else f"second route input {last}"


def check_no_question_on_second_turn(calls, replies):
    return "?" not in replies[-1].strip()[-3:], "did not end with a question"


def check_door_previewed_then_applied(calls, replies):
    doors = calls_named(calls, "add_door")
    confirms = [d["input"].get("confirm") for d in doors]
    if not doors:
        return False, "no add_door call"
    first_confirm = confirms.index(True) if True in confirms else None
    ok = confirms[0] is not True and first_confirm is not None and doors[first_confirm]["turn"] >= 2
    return ok, f"confirm flags per call {confirms}"


def check_closed(calls, replies):
    return bool(calls_named(calls, "set_closed")), "set_closed called"


def check_asks_back(calls, replies):
    return "?" in replies[0], "asked which one"


def check_no_fabrication(calls, replies):
    text = replies[0].lower()
    ok = any(w in text for w in ("no room", "doesn't exist", "does not exist", "couldn't find", "could not find", "not find", "no such", "isn't a", "is no"))
    return ok, "said the room does not exist"


def check_avoid(calls, replies):
    routes = calls_named(calls, "find_route")
    return any(r["input"].get("avoid") for r in routes), "used avoid"


SCENARIOS = [
    Scenario("first_day", FACTORY, "New employee, first day, knows no room names.",
             ["Hi, it's my first day here. Where can I get a coffee?",
              "I'm at the quality lab right now. How do I get there?"],
             [check_no_question_on_second_turn]),
    Scenario("wheelchair", CAMPUS, "Wheelchair user; expects step-free routes every time without repeating it.",
             ["I use a wheelchair. How do I get from the Main lobby to Lab 1.24?",
              "Thanks. Afterwards I need to go from Lab 1.24 to Lab 0.11."],
             [check_second_route_step_free]),
    Scenario("technician", FACTORY, "Service technician, hands full, wants short spoken directions with landmarks.",
             ["Hands full. Fastest way from Warehouse zone H-C1 to the coordinate measuring machine. Keep it short."], []),
    Scenario("facility_manager", FACTORY, "Facility manager making changes to the building.",
             ["The office lift is closed for maintenance. What changes?",
              "Also, add a door between Meeting room 0.20 and Quality lab 0.21.",
              "Yes, go ahead."],
             [check_closed, check_door_previewed_then_applied]),
    Scenario("vague", FACTORY, "Vague user.", ["Where's the printer?"], [check_asks_back]),
    Scenario("wrong_room", FACTORY, "User with a wrong room number.", ["How do I get from Kitchen 0.28 to room 9.99?"],
             [check_no_fabrication]),
    Scenario("avoid", FACTORY, "Forklift-shy visitor.",
             ["Get me from Warehouse zone H-C1 to Server room 0.45, but avoid the production zones and the assembly zone."],
             [check_avoid]),
    Scenario("change_mind", FACTORY, "User who changes their mind halfway.",
             ["Route me from Locker room 0.39 to Meeting room 0.20.", "Actually no, I'd rather go to Kitchen 0.31 instead."],
             []),
]

RUBRIC = """Score the building guide's side of this conversation, 1 (poor) to 5 (excellent), on:
- asks_only_what_needed: asks back only when the answer depends on it; never asks for things already said.
- shows_understanding: states briefly what it understood (from, to, constraints) before or with the answer.
- followable_directions: directions a person can follow while walking (rooms, landmarks, turns, floors, distance); short.
- remembers_context: keeps constraints and location from earlier turns.
- handles_changes_safely: previews edits before applying, explains effects of closures (score 5 if not applicable).
- correctness: claims agree with the tool results shown; nothing invented.
List concrete issues."""


class Grade(BaseModel):
    asks_only_what_needed: int
    shows_understanding: int
    followable_directions: int
    remembers_context: int
    handles_changes_safely: int
    correctness: int
    issues: list[str]


def run_scenario(scenario: Scenario) -> dict:
    session = Session.for_building(Building.load(scenario.building))
    agent = ChatAgent(session)
    calls, replies, transcript = [], [], []
    for turn_index, text in enumerate(scenario.turns, 1):
        transcript.append(f"USER: {text}")

        def on_event(kind, payload, turn=turn_index):
            if kind == "tool":
                calls.append({"turn": turn, **payload})
                transcript.append(f"  [tool {payload['name']} {json.dumps(payload['input'], ensure_ascii=False)}]")

        reply = agent.ask(text, on_event=on_event)
        replies.append(reply)
        transcript.append(f"GUIDE: {reply}")
    return {"calls": calls, "replies": replies, "transcript": "\n".join(transcript), "usage": agent.usage, "model": agent.model}


def judge(scenario: Scenario, transcript: str, model: str | None) -> Grade | None:
    grade, _ = structured.parse("judge", "You grade conversations between a building guide and a person.",
                                f"Persona: {scenario.persona}\n\n{RUBRIC}\n\nTranscript:\n{transcript}", Grade, model=model)
    return grade


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.interaction")
    cli.add_argument("--only", nargs="*")
    cli.add_argument("--judge-model", default=None, help="default: the provider's judge model")
    args = cli.parse_args()
    ledger = Ledger("interaction", {"judge": args.judge_model or model_for("judge")})
    for scenario in SCENARIOS:
        if args.only and scenario.name not in args.only:
            continue
        run = run_scenario(scenario)
        ledger.add_usage(run["usage"])
        check_results = [(fn.__name__, *fn(run["calls"], run["replies"])) for fn in scenario.checks]
        grade = judge(scenario, run["transcript"], args.judge_model)
        scores = grade.model_dump(exclude={"issues"}) if grade else {}
        mean = sum(scores.values()) / len(scores) if scores else 0
        ok = all(c[1] for c in check_results) and mean >= 4.0
        ledger.record(id=scenario.name, kind=scenario.name, source="interaction", correct=ok, mean=round(mean, 2),
                      scores=scores, checks=check_results, issues=grade.issues if grade else [], transcript=run["transcript"])
        print(f"\n=== {scenario.name}: mean {mean:.2f} checks {[(c[0], c[1]) for c in check_results]}")
        print(run["transcript"])
        if grade and grade.issues:
            print("issues:", *grade.issues, sep="\n  - ")
    ledger.finish()


if __name__ == "__main__":
    main()
