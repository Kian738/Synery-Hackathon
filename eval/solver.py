"""L1: gold inputs -> our solver -> official scorer. Any miss is a semantics bug in floorwise.core."""

import argparse
import traceback
from collections import Counter
from functools import lru_cache

from eval.common import load_questions, score_reply, source_of
from eval.ledger import Ledger
from floorwise.agent.solve import solve
from floorwise.core.model import Building


@lru_cache(maxsize=64)
def building_at(directory: str) -> Building:
    return Building.load(directory)


def run(splits: list[str], kinds: list[str] | None, verbose: bool) -> Counter:
    ledger = Ledger("solver", {"splits": splits, "kinds": kinds})
    tally: Counter = Counter()
    for directory, question in load_questions(splits):
        if kinds and question["kind"] not in kinds:
            continue
        building = building_at(str(directory))
        try:
            result, reply = solve(building, question["kind"], question["inputs"])
            error = None
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            result, reply, error = {}, "", f"{type(exc).__name__}: {exc}"
            if verbose:
                traceback.print_exc()
        correct = score_reply(question["answer"], reply)
        tally[(question["kind"], correct)] += 1
        tally[(source_of(question["building_id"]) + "|" + question["kind"], correct)] += 1
        ledger.record(
            id=question["id"], kind=question["kind"], source=source_of(question["building_id"]),
            correct=correct, error=error, reply=reply, expected=question["answer"], result=_compact(result),
        )
        if not correct and verbose:
            print(f"BAD {question['id']} {question['kind']} expected={question['answer']} got={_compact(result)} err={error}")
    ledger.finish()
    return tally


def _compact(result: dict) -> dict:
    return {k: v for k, v in result.items() if k not in ("space_ids", "improved", "neighbours")}


def main() -> None:
    parser = argparse.ArgumentParser(prog="eval.solver")
    parser.add_argument("--split", default="train,dev")
    parser.add_argument("--kinds", nargs="*")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    run(args.split.split(","), args.kinds, args.verbose)


if __name__ == "__main__":
    main()
