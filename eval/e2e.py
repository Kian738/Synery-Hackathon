"""L3: the full benchmark path, question text -> answer() -> official scorer, per kind and source.

Same scoring as the kit's benchmark.evaluate; adds the parse trace (rules / llm / fallback) to each row."""

import argparse
import time

from eval.common import load_questions, score_reply, source_of
from eval.ledger import Ledger
from floorwise.agent.answer import answer_with_trace


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.e2e")
    cli.add_argument("--split", default="dev")
    cli.add_argument("--kinds", nargs="*")
    cli.add_argument("--name", default=None)
    cli.add_argument("-v", "--verbose", action="store_true")
    args = cli.parse_args()
    ledger = Ledger("e2e", {"splits": args.split, "kinds": args.kinds}, name=args.name)
    for directory, question in load_questions(args.split.split(",")):
        if args.kinds and question["kind"] not in args.kinds:
            continue
        started = time.time()
        reply, trace = answer_with_trace(directory, question["question"])
        ledger.add_usage(trace.get("usage", {}))
        correct = score_reply(question["answer"], reply) if "answer" in question else None
        ledger.record(
            id=question["id"], kind=question["kind"], source=source_of(question["building_id"]), correct=correct,
            seconds=round(time.time() - started, 3), parser=trace.get("parser"), fallback=trace.get("fallback"),
            readings=len(trace.get("readings", [])), reply=reply,
        )
        if correct is False and args.verbose:
            print("BAD", question["id"], question["kind"], trace.get("fallback"), "|", reply.splitlines()[-1])
    ledger.finish()


if __name__ == "__main__":
    main()
