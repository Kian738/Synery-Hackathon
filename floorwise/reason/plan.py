"""Parse a plan from JSON and type-check the whole DAG before anything runs.

A plan is {"question", "steps": [{"id", "op", "args"}], "answer": "#<id>"}. An argument is a literal or a "#<id>"
reference to an earlier step's output; "#world" is the building as given (G0). Every error names the step."""

import json
from collections.abc import Mapping
from typing import Any

from floorwise.core.model import Building
from floorwise.reason import adapters
from floorwise.reason.operators import (
    REGISTRY,
    Registry,
    accepts_literal,
    accepts_type,
    alternatives,
    literal_tag,
)
from floorwise.reason.types import WORLD_REF, Plan, Step


class PlanError(ValueError):
    def __init__(self, step: str, message: str) -> None:
        super().__init__(f"step '{step}': {message}")
        self.step = step
        self.message = message


def is_ref(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("#")


def parse_plan(raw: "Plan | Mapping[str, Any] | str") -> Plan:
    if isinstance(raw, Plan):
        return raw
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as error:
            raise PlanError("plan", f"not valid JSON ({error})") from error
    if not isinstance(raw, Mapping):
        raise PlanError("plan", "a plan is a JSON object with question, steps and answer")
    steps = raw.get("steps")
    if not isinstance(steps, list) or not steps:
        raise PlanError("plan", "steps must be a non-empty list")
    if not isinstance(raw.get("answer"), str):
        raise PlanError("plan", "answer must be a reference like \"#s3\"")
    parsed = []
    for index, step in enumerate(steps):
        label = step.get("id", f"#{index}") if isinstance(step, Mapping) else f"#{index}"
        if not isinstance(step, Mapping) or not isinstance(step.get("id"), str) or not isinstance(step.get("op"), str):
            raise PlanError(str(label), "a step needs a string id and a string op")
        if not isinstance(step.get("args", {}), Mapping):
            raise PlanError(step["id"], "args must be an object")
        parsed.append(Step(step["id"], step["op"], dict(step.get("args", {}))))
    return Plan(str(raw.get("question", "")), tuple(parsed), raw["answer"])


def check_plan(plan: Plan, registry: Registry = REGISTRY, building: Building | None = None) -> Plan:
    """Raise PlanError naming the first offending step; return the plan unchanged when it is sound.

    With a building, literal ids are also checked against it, so a typo fails before the first step runs."""
    index = {step.id: i for i, step in enumerate(plan.steps)}
    _check_ids(plan, index)
    deps = {step.id: [a[1:] for a in step.args.values() if is_ref(a)] for step in plan.steps}
    _check_refs(plan, index, deps)
    outputs = {WORLD_REF: "World"}
    for step in plan.steps:
        _check_step(step, registry, outputs, building)
        outputs[step.id] = registry.get(step.op).returns
    if not is_ref(plan.answer) or plan.answer[1:] not in outputs:
        raise PlanError("answer", f"answer {plan.answer!r} does not reference a step")
    return plan


def _check_ids(plan: Plan, index: dict[str, int]) -> None:
    seen = set()
    for step in plan.steps:
        if step.id == WORLD_REF:
            raise PlanError(step.id, f"'{WORLD_REF}' is reserved for the building as given")
        if step.id in seen:
            raise PlanError(step.id, "duplicate step id")
        seen.add(step.id)


def _check_refs(plan: Plan, index: dict[str, int], deps: dict[str, list[str]]) -> None:
    for step in plan.steps:
        for ref in deps[step.id]:
            if ref != WORLD_REF and ref not in index:
                raise PlanError(step.id, f"refers to unknown step '#{ref}'")
    cycle = _find_cycle(plan, deps)
    if cycle:
        raise PlanError(cycle[0], f"cycle among steps {', '.join(cycle)}")
    for step in plan.steps:
        for ref in deps[step.id]:
            if ref != WORLD_REF and index[ref] > index[step.id]:
                raise PlanError(step.id, f"refers to later step '#{ref}'; a step may only use earlier steps")


def _find_cycle(plan: Plan, deps: dict[str, list[str]]) -> list[str] | None:
    """Steps on a cycle, in plan order. Linear time and no recursion: a step on a cycle is neither downstream of a
    cycle (Kahn peeling from the sources) nor upstream of one (peeling from the sinks)."""
    needs = {step.id: {d for d in deps[step.id] if d in deps} for step in plan.steps}
    users: dict[str, set[str]] = {node: set() for node in needs}
    for node, wanted in needs.items():
        for dep in wanted:
            users[dep].add(node)
    off_cycle = _peel(needs, users) | _peel(users, needs)
    remaining = [step.id for step in plan.steps if step.id not in off_cycle]
    return remaining or None


def _peel(follows: dict[str, set[str]], followed_by: dict[str, set[str]]) -> set[str]:
    """Nodes that can be ordered after everything they follow (Kahn's algorithm)."""
    open_count = {node: len(parents) for node, parents in follows.items()}
    ready = [node for node, count in open_count.items() if count == 0]
    done: set[str] = set()
    while ready:
        node = ready.pop()
        done.add(node)
        for child in followed_by[node]:
            open_count[child] -= 1
            if open_count[child] == 0:
                ready.append(child)
    return done


def _check_step(step: Step, registry: Registry, outputs: dict[str, str], building: Building | None) -> None:
    if step.op not in registry:
        raise PlanError(step.id, f"unknown operator '{step.op}'")
    operator = registry.get(step.op)
    known = {p.name: p for p in operator.params}
    for name in step.args:
        if name not in known:
            raise PlanError(step.id, f"'{step.op}' has no argument '{name}' (takes: {', '.join(known) or 'none'})")
    for param in operator.params:
        if param.required and param.name not in step.args:
            raise PlanError(step.id, f"'{step.op}' is missing required argument '{param.name}' ({param.type})")
    for name, value in step.args.items():
        expected = known[name].type
        if is_ref(value):
            actual = outputs[value[1:]]
            if not accepts_type(expected, actual):
                raise PlanError(step.id, f"argument '{name}' of '{step.op}' expects {expected}, but {value} gives {actual}")
        elif not accepts_literal(expected, value):
            raise PlanError(step.id, f"argument '{name}' of '{step.op}' expects {expected}, got literal {value!r} ({literal_tag(value)})")
        elif building is not None:
            _check_literal_ids(step, name, expected, value, building)


ID_POOLS = {
    "Space": lambda building, item: item in building.spaces,
    "Spaces": lambda building, item: item in building.spaces,
    "Floor": lambda building, item: item in building.floors,
    "Element": adapters.is_element,
}


def _check_literal_ids(step: Step, name: str, expected: str, value: Any, building: Building) -> None:
    pools = [ID_POOLS[alt] for alt in alternatives(expected) if alt in ID_POOLS]
    if not pools or "Text" in alternatives(expected):
        return
    for item in [value] if isinstance(value, str) else value:
        if not isinstance(item, str):
            raise PlanError(step.id, f"argument '{name}' of '{step.op}': ids are strings, got {item!r}")
        if not any(pool(building, item) for pool in pools):
            raise PlanError(step.id, f"argument '{name}' of '{step.op}': {item!r} is not an id in {building.id}")
