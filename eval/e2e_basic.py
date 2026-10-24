"""L3b: warm-up families (locate, count, route, step-free, closure, tour) end to end from the question text.

Scored like the kit's starter evaluator: locate = gold asset among those found, count exact,
routes within 1% of the optimal length (or correctly reported unreachable)."""

import argparse

from eval.common import load_questions, source_of
from eval.ledger import Ledger
from floorwise.agent.answer import answer_with_trace

ROUTE_TOLERANCE = 0.01


def correct(question: dict, trace: dict) -> bool:
    gold, result = question["answer"], trace.get("result") or {}
    kind = question["kind"]
    if kind == "locate":
        return gold["asset_id"] in result.get("asset_ids", [])
    if kind == "count":
        return result.get("count") == gold["count"]
    if gold.get("reachable") is False:
        return result.get("reachable") is False
    if not result.get("reachable"):
        return False
    return abs(result["length_m"] - gold["optimal_length_m"]) <= max(ROUTE_TOLERANCE * gold["optimal_length_m"], ROUTE_TOLERANCE)


def _slim(result: dict | None) -> dict | None:
    if not result:
        return result
    return {k: v for k, v in result.items() if k not in ("matches", "legs")}


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.e2e_basic")
    cli.add_argument("--split", default="dev")
    cli.add_argument("-v", "--verbose", action="store_true")
    args = cli.parse_args()
    ledger = Ledger("e2e_basic", {"splits": args.split})
    for directory, question in load_questions(args.split.split(","), "questions_basic.jsonl"):
        reply, trace = answer_with_trace(directory, question["question"])
        ok = correct(question, trace)
        ledger.record(id=question["id"], kind=question["kind"], source=source_of(question["building_id"]), building=question["building_id"], correct=ok,
                      parser=trace.get("parser"), fallback=trace.get("fallback"), readings=len(trace.get("readings", [])),
                      question=question["question"], expected=question["answer"], result=_slim(trace.get("result")))
        if not ok and args.verbose:
            print("BAD", question["id"], question["kind"], trace.get("fallback") or trace.get("resolve_error"), "|", question["question"][:120])
    ledger.finish()


if __name__ == "__main__":
    main()
