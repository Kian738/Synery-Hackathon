"""L2: question text -> QuerySpec -> resolved inputs, compared field by field with the gold 'inputs'.

--parser rules   free, deterministic regex parser
--parser llm     Claude structured-output parser (costs credits; pick the model with --model)
On the test split (no gold) it reports coverage: how many questions each parser can resolve."""

import argparse
from functools import lru_cache

from eval.common import load_questions, source_of
from eval.ledger import Ledger
from floorwise.agent.parse_rules import parse_rules
from floorwise.agent.spec import resolve_spec_all
from floorwise.core.model import Building


@lru_cache(maxsize=64)
def building_at(directory: str) -> Building:
    return Building.load(directory)


def make_parser(name: str, model: str | None):
    if name == "rules":
        return lambda building, text: (parse_rules(text), {})
    from floorwise.agent.parse_llm import LLMParser

    parser = LLMParser(model=model) if model else LLMParser()
    return lambda building, text: parser.parse(building, text)


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.parser")
    cli.add_argument("--split", default="train,dev")
    cli.add_argument("--parser", default="rules", choices=["rules", "llm"])
    cli.add_argument("--model", default=None)
    cli.add_argument("--limit", type=int, default=None)
    cli.add_argument("-v", "--verbose", action="store_true")
    args = cli.parse_args()
    parse = make_parser(args.parser, args.model)
    ledger = Ledger("parser", {"splits": args.split, "parser": args.parser, "model": args.model}, name=args.parser)
    items = load_questions(args.split.split(","))
    if args.limit:
        items = items[:: max(1, len(items) // args.limit)][: args.limit]
    for directory, question in items:
        building = building_at(str(directory))
        spec, usage, inputs, error, readings = None, {}, None, None, []
        try:
            spec, usage = parse(building, question["question"])
            if spec is None:
                error = "no parse"
            else:
                readings = resolve_spec_all(building, spec)
                inputs = readings[0]
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
        ledger.add_usage(usage)
        gold = question.get("inputs")
        kind_ok = spec is not None and spec.kind == question["kind"]
        if gold is None:
            correct = inputs is not None and kind_ok
        else:
            correct = kind_ok and any(
                all(_same(reading.get(key), value) for key, value in gold.items()) for reading in readings
            )
        ledger.record(
            id=question["id"], kind=question["kind"], source=source_of(question["building_id"]), correct=correct,
            error=error, readings=len(readings), spec=spec.model_dump(exclude_none=True) if spec else None, inputs=inputs, gold=gold,
        )
        if not correct and args.verbose:
            print("BAD", question["id"], error, "\n   ", question["question"][:160], "\n    got", inputs, "\n   gold", gold)
    ledger.finish()


def _same(ours, gold) -> bool:
    if isinstance(gold, float) or isinstance(ours, float):
        return ours is not None and abs(float(ours) - float(gold)) < 1e-9
    return ours == gold


if __name__ == "__main__":
    main()
