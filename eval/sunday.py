"""L3c: the Sunday route scoring, replicated end to end.

For every warm-up route, step-free, closure and tour question (train and dev) the question text goes through the
whole benchmark path, the reply's `Answer:` line is read back the way a grader would read it (ordered space ids, or
"no route"), and eval.judge validates and measures that route with the kit's own implementation. Score is the
judges' score: best length / our length, 1.0 within 1%, 0 for an invalid route; "no route" is correct only when the
dataset says there is none.

  uv run python -m eval.sunday --split train,dev
A question passes when its score is 1.0. Known ambiguous names (eval/known_issues.json) are reported separately."""

import argparse
import copy

from eval import judge
from eval.common import load_questions, source_of
from eval.ledger import Ledger
from floorwise.agent.answer import answer_with_trace, committed
from floorwise.core.model import Building

ROUTE_KINDS = {"route", "route_step_free", "route_with_closure", "tour"}


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.sunday")
    cli.add_argument("--split", default="train,dev")
    cli.add_argument("--kinds", nargs="*")
    args = cli.parse_args()
    ledger = Ledger("sunday", {"splits": args.split})
    maps: dict[str, object] = {}
    for directory, question in load_questions(args.split.split(","), "questions_basic.jsonl"):
        if question["kind"] not in ROUTE_KINDS or (args.kinds and question["kind"] not in args.kinds):
            continue
        answer = question["answer"]
        reply, trace = answer_with_trace(directory, question["question"])
        sequence = judge.parse_answer(committed(reply))
        said_no_route = sequence is None
        verdict = None
        if sequence is not None:
            key = str(directory)
            if key not in maps:
                maps[key] = judge.kit_map(copy.deepcopy(Building.load(directory).data))
            closed = {answer["closed_element_id"]} if answer.get("closed_element_id") else set()
            verdict = judge.measure(maps[key], sequence, step_free=question["kind"] == "route_step_free", closed=closed)
            stops = answer.get("stops") or [answer.get("from_space_id"), answer.get("to_space_id")]
            if verdict.valid and not judge.visits_in_order(sequence, [s for s in stops if s]):
                verdict = judge.Verdict(False, None, "the route does not run between the requested places in order")
        best = None if answer.get("reachable") is False else answer["optimal_length_m"]
        points = judge.score(best, verdict, said_no_route)
        ledger.record(
            id=question["id"], kind=question["kind"], source=source_of(question["building_id"]), building=question["building_id"],
            correct=points >= 1.0, points=round(points, 4), best_m=best, our_m=verdict.length_m if verdict else None,
            valid=verdict.valid if verdict else None, reason=(verdict.reason if verdict else "said no route" if said_no_route else ""),
            readings=len(trace.get("readings", [])), question=question["question"], answer_line=committed(reply)[:300],
        )
    ledger.finish()


if __name__ == "__main__":
    main()
