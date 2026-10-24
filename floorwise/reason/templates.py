"""Deterministic offline plan templates. The missions live in templates.json as data: the engine has no code that is
specific to a building, a question or a scenario. `instantiate` fills a template's parameters and returns a Plan.

Template language: "$name" in an argument is replaced by the parameter (an optional parameter that is absent drops
the argument); {"$if": p, "then": x, "else": y} picks by whether p was given; a step with "when": p (or "unless": p)
exists only if p was given (or not); "together" lists parameter groups that must be given all or none."""

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

from floorwise.reason.plan import parse_plan
from floorwise.reason.types import Plan

_DROP = object()
TEMPLATE_FILE = Path(__file__).with_name("templates.json")


class TemplateError(ValueError):
    pass


@cache
def _load() -> dict[str, dict]:
    return json.loads(TEMPLATE_FILE.read_text(encoding="utf-8"))


def template_names() -> tuple[str, ...]:
    return tuple(sorted(_load()))


def instantiate(name: str, **params: Any) -> Plan:
    templates = _load()
    if name not in templates:
        raise TemplateError(f"no template named '{name}'; available: {', '.join(template_names())}")
    template = templates[name]
    allowed = set(template["required"]) | set(template["optional"])
    given = {key: copy.deepcopy(value) for key, value in params.items() if value is not None}
    if unknown := sorted(set(given) - allowed):
        raise TemplateError(f"template '{name}' has no parameter(s) {', '.join(unknown)}; takes {', '.join(sorted(allowed))}")
    if absent := [key for key in template["required"] if key not in given]:
        raise TemplateError(f"template '{name}' needs parameter(s) {', '.join(absent)}")
    for group in template.get("together", ()):
        if 0 < sum(key in given for key in group) < len(group):
            raise TemplateError(f"template '{name}': give {' and '.join(group)} together or not at all")

    steps = []
    for step in template["steps"]:
        if ("when" in step and step["when"] not in given) or ("unless" in step and step["unless"] in given):
            continue
        args = {key: _fill(value, given) for key, value in step["args"].items()}
        steps.append({"id": step["id"], "op": step["op"], "args": {k: v for k, v in args.items() if v is not _DROP}})
    question = f"{name.replace('_', ' ')}: " + ", ".join(f"{k}={v}" for k, v in sorted(given.items()) if isinstance(v, (str, int, float, bool)))
    return parse_plan({"question": question, "steps": steps, "answer": _fill(template["answer"], given)})


def _fill(value: Any, given: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        return given.get(value[1:], _DROP)
    if isinstance(value, dict) and "$if" in value:
        return _fill(value["then"] if value["$if"] in given else value["else"], given)
    return value
