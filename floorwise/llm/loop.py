"""One agent turn with tools, for Claude (Messages API) or an OpenAI-compatible provider (Groq, OpenRouter).

The conversation history is kept in the provider's own message format inside Conversation."""

import json
import uuid
from types import SimpleNamespace
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from floorwise import llm
from floorwise.llm import budget
from floorwise.llm.tools import Tool, call

MAX_TOKENS = 16000
MAX_STEPS = 16
FALLBACK_BETA = "server-side-fallback-2026-07-01"
THINKING_BINDING_BETA = "thinking-binding-controls-2026-08-01"

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
            arguments = dict(model=self.model, max_tokens=MAX_TOKENS, system=system, tools=tools, messages=self.messages,
                             output_config={"effort": self.effort}, betas=[FALLBACK_BETA, THINKING_BINDING_BETA],
                             # Loading specialized tools changes the prefix that old thinking
                             # signatures bind to. Let the API discard only invalid blocks;
                             # preserve assistant messages and tool results verbatim.
                             thinking={"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}},
                             fallbacks="default", timeout=budget.timeout_s())
            if on_event:
                message_id = uuid.uuid4().hex
                self.last_message_id = message_id
                on_event('assistant_start', {'message_id': message_id, 'model': self.model})
                with self.client.beta.messages.stream(**arguments) as stream:
                    for event in stream:
                        on_event('checkpoint', {})
                        if event.type == 'content_block_delta' and event.delta.type == 'text_delta':
                            on_event('assistant_delta', {'message_id': message_id, 'text': event.delta.text})
                    response = stream.get_final_message()
                on_event('assistant_end', {'message_id': message_id, 'stop_reason': response.stop_reason})
            else:
                response = self.client.beta.messages.create(**arguments)
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
            arguments = dict(model=self.model, max_tokens=4096, tools=tools, tool_choice="auto",
                             messages=[{"role": "system", "content": self.system}, *self.messages], timeout=budget.timeout_s())
            if on_event:
                message_id = uuid.uuid4().hex
                self.last_message_id = message_id
                on_event('assistant_start', {'message_id': message_id, 'model': self.model})
                fragments = {}; text = ''; usage = None
                with self.client.chat.completions.create(**arguments, stream=True, stream_options={'include_usage': True}) as stream:
                    for chunk in stream:
                        on_event('checkpoint', {})
                        if chunk.usage: usage = chunk.usage
                        if not chunk.choices: continue
                        delta = chunk.choices[0].delta
                        if delta.content:
                            text += delta.content
                            on_event('assistant_delta', {'message_id': message_id, 'text': delta.content})
                        for fragment in delta.tool_calls or []:
                            item = fragments.setdefault(fragment.index, {'id': '', 'name': '', 'arguments': ''})
                            if fragment.id: item['id'] = fragment.id
                            if fragment.function:
                                item['name'] += fragment.function.name or ''
                                item['arguments'] += fragment.function.arguments or ''
                calls = [SimpleNamespace(id=f['id'], function=SimpleNamespace(name=f['name'], arguments=f['arguments'])) for _, f in sorted(fragments.items())]
                response = SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=calls))])
                on_event('assistant_end', {'message_id': message_id})
            else:
                response = self.client.chat.completions.create(**arguments)
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
                if on_event:
                    on_event("tool_result", {"name": c.function.name, "content": content, "is_error": is_error})
                self.messages.append({"role": "tool", "tool_call_id": c.id, "content": ("ERROR: " if is_error else "") + content})
            if on_event:
                on_event("step", {})
        return "I ran out of steps for this request. Could you narrow it down?"
