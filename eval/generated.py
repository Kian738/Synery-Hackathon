"""L3d: generated route questions for EVERY building (train, dev and test), checked against an independent router.

The warm-up set has gold answers for only 240 buildings and a few questions each. This suite writes new questions in
the dataset's own wording (route, step-free, closure, tour) for any building, runs each one through the whole
benchmark path (parser -> resolver -> solver -> reply), reads the reply back the way a grader would, and scores it
with eval.judge: the kit's own implementation (starter_agent.building_map, kit 1.1.0) provides the optimum and
measures our route. Nothing is hand-labelled and no test answer is used; the test buildings are included because the
question is generated and the oracle is code.

Questions only name spaces whose label ("Name (Floor)") is unique in the building, so every miss is a real bug, not
an ambiguous mention. Unique-label skips are counted.

  uv run python -m eval.generated --split dev --per-building 8
  uv run python -m eval.generated --split train,dev,test --per-building 6     # every supplied building"""

import argparse
import copy
import random

from eval import judge
from eval.common import SPLITS, source_of
from eval.ledger import Ledger
from floorwise.agent.answer import answer_with_trace, committed
from floorwise.core.model import Building
from floorwise.paths import DATA

KINDS = ("route", "route_step_free", "route_with_closure", "tour")


def eligible(building: Building) -> tuple[list[str], int]:
    """Spaces a person asks about, with a label no other space has."""
    labels: dict[str, list[str]] = {}
    for sid, space in building.spaces.items():
        labels.setdefault(building.label(sid), []).append(sid)
    ok = [ids[0] for ids in labels.values() if len(ids) == 1 and building.spaces[ids[0]]["type"] in ("room", "hall")]
    return sorted(ok), len(building.spaces) - len(ok)


def generate(building: Building, count: int, rng: random.Random) -> list[dict]:
    rooms, _ = eligible(building)
    names: dict[str, list[str]] = {}
    for cid, connector in building.connectors.items():
        names.setdefault(connector["name"], []).append(cid)
    unique_connectors = [ids[0] for ids in names.values() if len(ids) == 1]
    questions = []
    if len(rooms) < 3:
        return questions
    for index in range(count):
        kind = KINDS[index % len(KINDS)]
        a, b, c = rng.sample(rooms, 3)
        label = building.label
        if kind == "route":
            text, spec = f"How do I get from {label(a)} to {label(b)}?", {"stops": [a, b]}
        elif kind == "route_step_free":
            text, spec = f"Is there a step-free route from {label(a)} to {label(b)}?", {"stops": [a, b], "step_free": True}
        elif kind == "route_with_closure" and unique_connectors:
            closed = rng.choice(unique_connectors)
            text = f"{building.connectors[closed]['name']} is closed for maintenance. How do I get from {label(a)} to {label(b)}?"
            spec = {"stops": [a, b], "closed": {closed}}
        elif kind == "tour":
            text, spec = f"Starting at {label(a)}, visit {label(b)}, then {label(c)} in this order. What is the route?", {"stops": [a, b, c]}
        else:
            continue
        questions.append({"id": f"{building.id}:{kind}:{index}", "kind": kind, "question": text, **spec})
    return questions


def oracle(bm, question: dict) -> float | None:
    """Optimal length by the kit's implementation, or None when no route exists under the rules."""
    use = question.get("closed", set())
    bm.closed = set(use)
    stops = question["stops"]
    try:
        route = bm.route(stops[0], stops[-1], step_free=question.get("step_free", False), via=stops[1:-1])
    except Exception:  # noqa: BLE001 - the kit raises MapError when there is no route
        return None
    return route.length_m


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.generated")
    cli.add_argument("--split", default="dev")
    cli.add_argument("--per-building", type=int, default=8)
    cli.add_argument("--seed", type=int, default=7)
    cli.add_argument("--limit", type=int, default=None, help="only the first N buildings")
    args = cli.parse_args()
    ledger = Ledger("generated", {"splits": args.split, "per_building": args.per_building, "seed": args.seed})
    paths = sorted(p for split in args.split.split(",") if split in SPLITS for p in (DATA / split).glob("*/building.json"))[: args.limit]
    for path in paths:
        directory = path.parent
        building = Building.load(directory)
        questions = generate(building, args.per_building, random.Random(f"{args.seed}:{building.id}"))
        if not questions:
            continue
        bm = judge.kit_map(copy.deepcopy(building.data))
        for question in questions:
            best = oracle(bm, question)
            reply, trace = answer_with_trace(directory, question["question"])
            sequence = judge.parse_answer(committed(reply))
            verdict = None
            if sequence is not None:
                verdict = judge.measure(bm, sequence, step_free=question.get("step_free", False), closed=question.get("closed", set()))
                if verdict.valid and not judge.visits_in_order(sequence, question["stops"]):
                    verdict = judge.Verdict(False, None, "the route does not run between the requested places in order")
            points = judge.score(best, verdict, sequence is None)
            ledger.record(
                id=question["id"], kind=question["kind"], source=source_of(building.id), building=building.id,
                correct=points >= 1.0, points=round(points, 4), best_m=best, our_m=verdict.length_m if verdict else None,
                reason=(verdict.reason if verdict else "said no route" if sequence is None else ""),
                parser=trace.get("parser"), fallback=trace.get("fallback"), question=question["question"], answer_line=committed(reply)[:240],
            )
    ledger.finish()


if __name__ == "__main__":
    main()
