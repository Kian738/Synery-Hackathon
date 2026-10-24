"""Spend guard: every LLM call in this process counts against a token budget, and requests time out.

  FLOORWISE_MAX_TOKENS     total input+output tokens allowed per process (default 400 000; 0 = no limit)
  FLOORWISE_LLM_TIMEOUT_S  seconds per request before it is abandoned (default 90)

When the budget is spent, BudgetExceeded is raised before the next call, so a runaway eval or a looping
agent stops instead of eating credits."""

import os
import threading
import time
from contextvars import ContextVar
from functools import wraps

_lock = threading.Lock()
_used = 0
_interactive = ContextVar('floorwise_interactive_deadline', default=None)


def interactive_turn(function):
    """Bound interactive network waits without changing benchmark/eval timeouts."""
    @wraps(function)
    def run(agent, *args, **kwargs):
        if agent.benchmark:
            return function(agent, *args, **kwargs)
        token = _interactive.set((time.monotonic()+float(os.environ.get('FLOORWISE_CHAT_DEADLINE_S','60')),
                                  float(os.environ.get('FLOORWISE_CHAT_CALL_TIMEOUT_S','25'))))
        try:
            return function(agent, *args, **kwargs)
        finally:
            _interactive.reset(token)
    return run


def retries() -> int:
    return 0 if _interactive.get() else 1


class BudgetExceeded(RuntimeError):
    pass


def limit() -> int:
    return int(os.environ.get("FLOORWISE_MAX_TOKENS", "400000"))


def timeout_s() -> float:
    maximum = float(os.environ.get("FLOORWISE_LLM_TIMEOUT_S", "90"))
    scope = _interactive.get()
    return max(.05,min(maximum,scope[1],scope[0]-time.monotonic())) if scope else maximum


def check() -> None:
    scope = _interactive.get()
    if scope and time.monotonic() >= scope[0]:
        raise TimeoutError('This request took too long. Try one question at a time; computed map results remain available.')
    if limit() and _used >= limit():
        raise BudgetExceeded(f"LLM token budget spent ({_used:,} of {limit():,}). Raise FLOORWISE_MAX_TOKENS to continue.")


def add(input_tokens: int, output_tokens: int) -> None:
    global _used
    with _lock:
        _used += int(input_tokens or 0) + int(output_tokens or 0)


def used() -> int:
    return _used
