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
from floorwise.agent.spec import QuerySpec, describe_ambiguity, resolve_spec_all
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


def _single_number(text: str) -> float | None:
    numbers = re.findall(r"-?\d+(?:\.\d+)?", text)
    return float(numbers[0]) if len(numbers) == 1 else None


def pick_reading(answers: list[str], tolerance: float = 0.01) -> str:
    """Choose among the answers of several readings of an ambiguous question.

    Numbers: the value that agrees (within tolerance) with the most readings; ties go to the one closest
    to the median, which minimises the worst-case error. Text: plain majority, first on ties."""
    values = [_single_number(a) for a in answers]
    if any(v is None for v in values):
        return Counter(answers).most_common(1)[0][0]
    ordered = sorted(values)
    median = ordered[len(ordered) // 2] if len(ordered) % 2 else (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2

    def support(v: float) -> int:
        return sum(1 for w in values if abs(w - v) <= max(abs(v) * tolerance, 1e-9))

    best = max(range(len(answers)), key=lambda i: (support(values[i]), -abs(values[i] - median)))
    return answers[best]


def answer_with_trace(building_directory: Path | str, question: str, hints: dict | None = None) -> tuple[str, dict]:
    """hints: constraints given beside the question text (e.g. {"step_free": true, "closed": ["Lift 1"]})."""
    building = load_building(str(building_directory))
    trace: dict = {"building": building.id}
    try:
        spec, via = parse(building, question)
        trace["parser"] = via
        if spec is not None and hints:
            update = {}
            if hints.get("step_free"):
                update["step_free"] = True
            if hints.get("closed") and not spec.closed:
                closed = hints["closed"]
                update["closed"] = closed[0] if isinstance(closed, list) else closed
            spec = spec.model_copy(update=update)
        if spec is None or spec.kind == "other":
            return fallback(building, question, trace, "not one of the known question families")
        trace["spec"] = spec.model_dump(exclude_none=True)
        readings = resolve_spec_all(building, spec)
        trace["readings"] = readings
        solved = []
        for inputs in readings:
            try:
                solved.append(solve(building, spec.kind, inputs))
            except SolveError as error:
                trace.setdefault("solve_errors", []).append(str(error))
        if not solved:
            return fallback(building, question, trace, "; ".join(trace.get("solve_errors", [])))
        def vote_key(item: tuple[dict, str]) -> str:
            # Routes are compared by length (the judges score best length / our length), not by their space ids.
            result_, reply_ = item
            return f"{result_['length_m']:.2f} m" if result_.get("reachable") and "length_m" in result_ else committed(reply_)

        votes = Counter(vote_key(item) for item in solved)
        winner = pick_reading(list(votes.elements()))
        result, reply = next(item for item in solved if vote_key(item) == winner)
        trace["kind"] = spec.kind
        trace["result"] = result
        if len(readings) > 1:
            trace["votes"] = dict(votes)
            trace["ambiguity"] = describe_ambiguity(building, spec)
            reply = (
                f"Note: the question does not say which space it means; its wording fits {len(readings)} readings, "
                f"{votes[winner]} of which give this answer. Treat it as a best guess.\n" + reply
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
