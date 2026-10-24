"""Run a checked plan step by step. A step that cannot be answered stops the plan: the Trace says which step and why
(abstention), and no later step runs. Plans are type-checked first, so a type error never costs a computation."""

import time
from collections.abc import Callable, Mapping
from typing import Any

from floorwise.reason import adapters
from floorwise.reason.operators import BOTTOM, REGISTRY, Operator, Registry
from floorwise.reason.plan import PlanError, check_plan, is_ref, parse_plan
from floorwise.reason.types import (
    WORLD_REF,
    Abstain,
    Abstention,
    Plan,
    StepResult,
    Trace,
    World,
)

OnStep = Callable[[StepResult], None]
SUMMARY_WIDTH = 100


def run_plan(source, plan: "Plan | Mapping[str, Any] | str", on_step: OnStep | None = None,
             registry: Registry = REGISTRY) -> Trace:
    """source: a Building or a building directory. on_step receives each StepResult as soon as it exists; an exception
    it raises is the caller's and propagates."""
    building = adapters.load_building(source)
    try:
        parsed = check_plan(parse_plan(plan), registry, building)
    except PlanError as error:
        question = plan.question if isinstance(plan, Plan) else str(plan.get("question", "")) if isinstance(plan, Mapping) else ""
        return Trace(Plan(question, (), ""), (), None, Abstention(error.step, "", f"plan rejected before execution: {error.message}"))

    values: dict[str, Any] = {WORLD_REF: World.of(building)}
    results: list[StepResult] = []
    for step in parsed.steps:
        operator = registry.get(step.op)
        args = {name: values[v[1:]] if is_ref(v) else _literal(v) for name, v in step.args.items()}
        started = time.perf_counter()
        value, reason, candidates, checks, line = _invoke(operator, args)
        result = StepResult(step.id, step.op, reason is None, None if reason else value, tuple(checks), reason,
                            reason or line, (time.perf_counter() - started) * 1000)
        results.append(result)
        if on_step:
            on_step(result)
        if reason is not None:
            return Trace(parsed, tuple(results), None, Abstention(step.id, step.op, reason, candidates))
        values[step.id] = value
    return Trace(parsed, tuple(results), values[parsed.answer[1:]], None)


def _literal(value: Any) -> Any:
    return tuple(value) if isinstance(value, list) else value


def _invoke(operator: Operator, args: Mapping[str, Any]) -> tuple[Any, str | None, tuple, list[str], str]:
    """(value, abstain reason, candidates, postconditions that held, one-line summary)."""
    try:
        value = operator.fn(**args)
    except Abstain as stop:
        return None, stop.reason, stop.candidates, [], ""
    except NotImplementedError as error:
        return None, f"operator '{operator.name}' is not available: {error}", (), [], ""
    except Exception as error:  # noqa: BLE001 - an operator bug must surface as a named abstention, never as a wrong answer
        return None, f"operator '{operator.name}' failed: {type(error).__name__}: {error}", (), [], ""
    if value is BOTTOM or value is None:
        return None, f"operator '{operator.name}' has no value for these inputs", (), [], ""
    held = []
    for label, check in operator.post:
        try:
            ok = bool(check(value, args))
        except Exception:  # noqa: BLE001 - a check that cannot run has not held
            ok = False
        if not ok:
            return None, f"postcondition failed: {label}", (), held, ""
        held.append(label)
    try:
        line = summarize(value, operator.unit)
    except Exception as error:  # noqa: BLE001 - a value that cannot be described cannot be shown
        return None, f"operator '{operator.name}' returned a value that cannot be summarised: {error}", (), held, ""
    return value, None, (), held, line


def summarize(value: Any, unit: str = "") -> str:
    """One line, from the value itself."""
    if hasattr(value, "summary"):
        text = value.summary()
    elif isinstance(value, bool):
        text = "yes" if value else "no"
    elif isinstance(value, (int, float)):
        text = f"{value:g} {unit}".strip()
    elif isinstance(value, tuple) and all(isinstance(v, str) for v in value):
        shown = ", ".join(value[:3]) + (", ..." if len(value) > 3 else "")
        text = f"{len(value)} item(s): {shown}" if value else "none"
    else:
        text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= SUMMARY_WIDTH else text[: SUMMARY_WIDTH - 3] + "..."
