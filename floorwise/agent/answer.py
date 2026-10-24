"""Benchmark entry point: answer(building_directory, question_text) -> reply ending in 'Answer: ...'.

Pipeline: rule parser (free) -> Claude parser if the wording is new -> entity linking -> exact solver.
When a name is shared by several spaces, every reading is solved and the most common answer wins.
Anything outside the known question families goes to the tool-using chat agent."""

import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from floorwise.agent.parse_rules import parse_rules
from floorwise.agent.solve import SolveError, solve
from floorwise.agent.spec import QuerySpec, resolve_spec_all
from floorwise.core.model import Building
from floorwise.core.resolve import ResolveError

ANSWER_LINE = re.compile(r"^\W*answer\W*:\s*(.+)$", flags=re.IGNORECASE | re.MULTILINE)
USE_LLM = os.environ.get("FLOORWISE_OFFLINE") != "1"


@lru_cache(maxsize=16)
def load_building(directory: str) -> Building:
    return Building.load(directory)


@lru_cache(maxsize=1)
def llm_parser():
    from floorwise.agent.parse_llm import LLMParser

    return LLMParser()


def parse(building: Building, question: str) -> tuple[QuerySpec | None, str]:
    spec = parse_rules(question)
    if spec is not None:
        return spec, "rules"
    if not USE_LLM:
        return None, "none"
    spec, _usage = llm_parser().parse(building, question)
    return spec, "llm"


def committed(reply: str) -> str:
    matches = ANSWER_LINE.findall(reply)
    return matches[-1].strip() if matches else ""


def answer_with_trace(building_directory: Path | str, question: str) -> tuple[str, dict]:
    building = load_building(str(building_directory))
    trace: dict = {"building": building.id}
    try:
        spec, via = parse(building, question)
        trace["parser"] = via
        if spec is None or spec.kind == "other":
            return fallback(building, question, trace, "not one of the known question families")
        trace["spec"] = spec.model_dump(exclude_none=True)
        readings = resolve_spec_all(building, spec)
        trace["readings"] = readings
        replies = []
        for inputs in readings:
            try:
                replies.append(solve(building, spec.kind, inputs)[1])
            except SolveError as error:
                trace.setdefault("solve_errors", []).append(str(error))
        if not replies:
            return fallback(building, question, trace, "; ".join(trace.get("solve_errors", [])))
        votes = Counter(committed(reply) for reply in replies)
        winner = votes.most_common(1)[0][0]
        reply = next(r for r in replies if committed(r) == winner)
        if len(readings) > 1:
            trace["votes"] = dict(votes)
            reply = (
                f"Note: the name in the question fits {len(readings)} spaces; "
                f"{votes[winner]} of them give this answer.\n" + reply
            )
        return reply, trace
    except ResolveError as error:
        trace["resolve_error"] = str(error)
        return fallback(building, question, trace, str(error))


def fallback(building: Building, question: str, trace: dict, reason: str) -> tuple[str, dict]:
    trace["fallback"] = reason
    if USE_LLM:
        try:
            from floorwise.agent.chat import ask_once

            reply, usage = ask_once(building, question)
            trace["usage"] = usage
            return reply, trace
        except Exception as error:  # noqa: BLE001 - the benchmark run must never stop on one question
            trace["fallback_error"] = f"{type(error).__name__}: {error}"
    return f"I could not answer this reliably ({reason}).\nAnswer: unknown", trace


def answer(building_directory: Path, question_text: str) -> str:
    """Signature expected by the kit's benchmark.evaluate --agent."""
    return answer_with_trace(building_directory, question_text)[0]
