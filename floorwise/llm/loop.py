"""One agent turn with tools, for Claude (Messages API) or an OpenAI-compatible provider (Groq, OpenRouter).

The conversation history is kept in the provider's own message format inside Conversation."""

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from floorwise import llm
from floorwise.llm import budget
from floorwise.llm.tools import Tool, call

MAX_TOKENS = 16000
MAX_STEPS = 16
FALLBACK_BETA = "server-side-fallback-2026-07-01"

OnEvent = Callable[[str, dict], None] | None


@dataclass
class Conversation:
    system: str
    tools: list[Tool]
    provider: str = field(default_factory=llm.provider_name)
    model: str | None = None
    effort: str = "low"
    messages: list = field(default_factory=list)
    usage: Counter = field(default_factory=Counter)

    def __post_init__(self) -> None:
        self.model = self.model or llm.model_for("chat", self.provider)
        self.client = llm.client(self.provider)
        self.by_name = {t.name: t for t in self.tools}

    def ask(self, text: str, on_event: OnEvent = None) -> str:
        self.messages.append({"role": "user", "content": text})
        if self.provider == "anthropic":
            return self._anthropic(on_event)
        return self._openai(on_event)

    # ---------- Claude ----------

    def _anthropic(self, on_event: OnEvent) -> str:
        system = [{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}]
        tools = [t.anthropic() for t in self.tools]
        for _ in range(MAX_STEPS):
            budget.check()
            response = self.client.beta.messages.create(
                model=self.model, max_tokens=MAX_TOKENS, system=system, tools=tools, messages=self.messages,
                output_config={"effort": self.effort}, betas=[FALLBACK_BETA], fallbacks="default",
            )
            usage = response.usage
            budget.add(usage.input_tokens, usage.output_tokens)
            self.usage.update({"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                               "cache_read_input_tokens": usage.cache_read_input_tokens or 0,
                               "cache_creation_input_tokens": usage.cache_creation_input_tokens or 0})
            self.messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "refusal":
                return "Sorry, I can't help with that request."
            uses = [b for b in response.content if b.type == "tool_use"]
            if not uses:
                return "\n".join(b.text for b in response.content if b.type == "text").strip()
            results = []
            for block in uses:
                if on_event:
                    on_event("tool", {"name": block.name, "input": block.input})
                content, is_error = call(self.by_name, block.name, block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error})
            self.messages.append({"role": "user", "content": results})
            if on_event:
                on_event("step", {})
        return "I ran out of steps for this request. Could you narrow it down?"

    # ---------- OpenAI-compatible (Groq, OpenRouter) ----------

    def _openai(self, on_event: OnEvent) -> str:
        tools = [t.openai() for t in self.tools]
        for _ in range(MAX_STEPS):
            budget.check()
            response = self.client.chat.completions.create(
                model=self.model, max_tokens=4096, tools=tools, tool_choice="auto",
                messages=[{"role": "system", "content": self.system}, *self.messages],
            )
            if response.usage:
                budget.add(response.usage.prompt_tokens, response.usage.completion_tokens)
                self.usage.update({"input_tokens": response.usage.prompt_tokens, "output_tokens": response.usage.completion_tokens})
            message = response.choices[0].message
            entry = {"role": "assistant", "content": message.content or ""}
            if message.tool_calls:
                entry["tool_calls"] = [
                    {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                    for c in message.tool_calls
                ]
            self.messages.append(entry)
            if not message.tool_calls:
                return (message.content or "").strip()
            for c in message.tool_calls:
                try:
                    arguments = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                if on_event:
                    on_event("tool", {"name": c.function.name, "input": arguments})
                content, is_error = call(self.by_name, c.function.name, arguments)
                self.messages.append({"role": "tool", "tool_call_id": c.id, "content": ("ERROR: " if is_error else "") + content})
            if on_event:
                on_event("step", {})
        return "I ran out of steps for this request. Could you narrow it down?"
