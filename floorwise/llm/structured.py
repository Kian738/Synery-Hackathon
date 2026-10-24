"""Structured output (text -> validated pydantic object) on any provider."""

import json
from collections import Counter
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from floorwise import llm
from floorwise.llm import budget

T = TypeVar("T", bound=BaseModel)


def parse(role: str, system: str, user_content, schema: type[T], provider: str | None = None,
          model: str | None = None) -> tuple[T | None, Counter]:
    provider = provider or llm.provider_name()
    model = model or llm.model_for(role, provider)
    client = llm.client(provider)
    usage: Counter = Counter()
    budget.check()
    if provider == "anthropic":
        response = client.messages.parse(
            model=model, max_tokens=8000, output_format=schema, output_config={"effort": "low"},
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_content}],
        )
        budget.add(response.usage.input_tokens+(response.usage.cache_read_input_tokens or 0)+(response.usage.cache_creation_input_tokens or 0), response.usage.output_tokens)
        usage.update({"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
                      "cache_read_input_tokens": response.usage.cache_read_input_tokens or 0, "cache_creation_input_tokens": response.usage.cache_creation_input_tokens or 0})
        return (None if response.stop_reason == "refusal" else response.parsed_output), usage

    json_schema = schema.model_json_schema()
    instruction = f"{system}\n\nReply with one JSON object only, matching this JSON schema:\n{json.dumps(json_schema)}"
    messages = [{"role": "system", "content": instruction}, {"role": "user", "content": user_content}]
    for attempt in range(2):
        budget.check()
        response = client.chat.completions.create(
            model=model, max_tokens=4000, messages=messages, response_format={"type": "json_object"},
        )
        if response.usage:
            budget.add(response.usage.prompt_tokens, response.usage.completion_tokens)
            usage.update({"input_tokens": response.usage.prompt_tokens, "output_tokens": response.usage.completion_tokens})
        text = response.choices[0].message.content or ""
        try:
            return schema.model_validate_json(text), usage
        except ValidationError as error:
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": f"That JSON does not match the schema: {error}. Reply with corrected JSON only."}]
    return None, usage
