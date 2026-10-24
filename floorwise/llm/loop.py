"""One agent turn with tools, for Claude (Messages API) or an OpenAI-compatible provider (Groq, OpenRouter).

The conversation history is kept in the provider's own message format inside Conversation."""

import json
import re
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
        checkpoint = len(self.messages)
        self.messages.append({"role": "user", "content": text})
        try:
            if self.provider == "anthropic":
                return self._anthropic(on_event)
            return self._openai(on_event)
        except Exception:
            # A failed tool turn must not leave unmatched tool calls or user turns
            # that invalidate the next request. Computed session state survives.
            del self.messages[checkpoint:]
            raise

    # ---------- Claude ----------

    def _anthropic(self, on_event: OnEvent) -> str:
        system = [{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}]
        for _ in range(MAX_STEPS):
            budget.check()
            if on_event:on_event('progress',{'stage':'model','message':'Waiting for Claude'})
            tools = [t.anthropic() for t in self.tools]
            streamed_chunks = []
            if hasattr(self.client.beta.messages, "stream"):
                with self.client.beta.messages.stream(
                    model=self.model, max_tokens=MAX_TOKENS, system=system, tools=tools, messages=self.messages,
                    output_config={"effort": self.effort}, betas=[FALLBACK_BETA], fallbacks="default", timeout=budget.timeout_s(),
                ) as stream:
                    for text in stream.text_stream:
                        streamed_chunks.append(text)
                        if on_event:
                            on_event("text_delta", {"text": text})
                    response = stream.get_final_message()
            else:
                response = self.client.beta.messages.create(
                    model=self.model, max_tokens=MAX_TOKENS, system=system, tools=tools, messages=self.messages,
                    output_config={"effort": self.effort}, betas=[FALLBACK_BETA], fallbacks="default", timeout=budget.timeout_s(),
                )
                for b in response.content:
                    if getattr(b, "type", None) == "text" and getattr(b, "text", None):
                        streamed_chunks.append(b.text)
                        if on_event:
                            on_event("text_delta", {"text": b.text})
            usage = response.usage
            budget.add(usage.input_tokens+(usage.cache_read_input_tokens or 0)+(usage.cache_creation_input_tokens or 0), usage.output_tokens)
            self.usage.update({"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                               "cache_read_input_tokens": usage.cache_read_input_tokens or 0,
                               "cache_creation_input_tokens": usage.cache_creation_input_tokens or 0})
            self.messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "refusal":
                return "Sorry, I can't help with that request."
            uses = [b for b in response.content if b.type == "tool_use"]
            if not uses:
                return "\n".join(b.text for b in response.content if b.type == "text").strip()
            if on_event and streamed_chunks:
                on_event("clear_deltas", {})
            results = []
            for block in uses:
                if on_event:
                    on_event("tool", {"name": block.name, "input": block.input})
                content, is_error = call(self.by_name, block.name, block.input)
                if on_event:
                    on_event("tool_result", {"name": block.name, "content": content, "is_error": is_error})
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error})
            self.messages.append({"role": "user", "content": results})
            if on_event:
                on_event("step", {})
        return "I ran out of steps for this request. Could you narrow it down?"

    # ---------- OpenAI-compatible (Groq, OpenRouter) ----------

    def _openai(self, on_event: OnEvent) -> str:
        for _ in range(MAX_STEPS):
            budget.check()
            if on_event:on_event('progress',{'stage':'model','message':'Waiting for the language model'})
            tools = [t.openai() for t in self.tools]
            response = self.client.chat.completions.create(
                model=self.model, max_tokens=4096, tools=tools, tool_choice="auto",
                messages=[{"role": "system", "content": self.system}, *self.messages], timeout=budget.timeout_s(),
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
                text = (message.content or "").strip()
                if on_event and text:
                    for part in re.split(r'(\n+|(?<=[.!?])\s+)', text):
                        if part:
                            on_event("text_delta", {"text": part})
                return text
            for c in message.tool_calls:
                try:
                    arguments = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                if on_event:
                    on_event("tool", {"name": c.function.name, "input": arguments})
                content, is_error = call(self.by_name, c.function.name, arguments)
                if on_event:
                    on_event("tool_result", {"name": c.function.name, "content": content, "is_error": is_error})
                self.messages.append({"role": "tool", "tool_call_id": c.id, "content": ("ERROR: " if is_error else "") + content})
            if on_event:
                on_event("step", {})
        return "I ran out of steps for this request. Could you narrow it down?"
