"""Spend guard: every LLM call in this process counts against a token budget, and requests time out.

  FLOORWISE_MAX_TOKENS     total input+output tokens allowed per process (default 400 000; 0 = no limit)
  FLOORWISE_LLM_TIMEOUT_S  seconds per request before it is abandoned (default 90)

When the budget is spent, BudgetExceeded is raised before the next call, so a runaway eval or a looping
agent stops instead of eating credits."""

import os
import threading

_lock = threading.Lock()
_used = 0


class BudgetExceeded(RuntimeError):
    pass


def limit() -> int:
    return int(os.environ.get("FLOORWISE_MAX_TOKENS", "400000"))


def timeout_s() -> float:
    return float(os.environ.get("FLOORWISE_LLM_TIMEOUT_S", "90"))


def check() -> None:
    if limit() and _used >= limit():
        raise BudgetExceeded(f"LLM token budget spent ({_used:,} of {limit():,}). Raise FLOORWISE_MAX_TOKENS to continue.")


def add(input_tokens: int, output_tokens: int) -> None:
    global _used
    with _lock:
        _used += int(input_tokens or 0) + int(output_tokens or 0)


def used() -> int:
    return _used
