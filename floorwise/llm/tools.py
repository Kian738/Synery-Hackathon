"""Tool specs written once as plain Python functions, exported to any provider's tool format.

The JSON schema comes from the function signature and the 'Args:' section of its docstring."""

import inspect
import json
import re
import typing
from dataclasses import dataclass
from typing import Callable

from pydantic import create_model


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    fn: Callable[..., str]

    def anthropic(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.schema}

    def openai(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.schema}}


class ToolFailure(Exception):
    """Raised by a tool for errors the model should see and recover from (unknown room, no route...)."""


def tool(fn: Callable[..., str]) -> Tool:
    doc = inspect.getdoc(fn) or ""
    summary, _, args_block = doc.partition("Args:")
    arg_docs = {}
    for match in re.finditer(r"^\s*(\w+):\s*(.+?)(?=^\s*\w+:|\Z)", args_block, flags=re.M | re.S):
        arg_docs[match.group(1)] = " ".join(match.group(2).split())
    hints = typing.get_type_hints(fn)
    fields = {}
    for name, parameter in inspect.signature(fn).parameters.items():
        default = ... if parameter.default is inspect.Parameter.empty else parameter.default
        from pydantic import Field

        fields[name] = (hints.get(name, str), Field(default, description=arg_docs.get(name)))
    model = create_model(f"{fn.__name__}_args", **fields)
    schema = model.model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    return Tool(fn.__name__, " ".join(summary.split()), schema, fn)


def call(tools: dict[str, Tool], name: str, raw_input) -> tuple[str, bool]:
    """Run a tool; returns (content, is_error)."""
    if name not in tools:
        return f"unknown tool {name}", True
    try:
        arguments = json.loads(raw_input) if isinstance(raw_input, str) else dict(raw_input or {})
        return tools[name].fn(**arguments), False
    except ToolFailure as error:
        return str(error), True
    except (TypeError, ValueError) as error:
        return f"bad arguments for {name}: {error}", True
