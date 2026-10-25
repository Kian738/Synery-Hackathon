"""L13: the gold question bank: every supplied question with known gold, said five other ways (how people really type and speak).

The supplied warm-up questions come with exact answers (route lengths, counts, assets). This suite keeps those answers and rewrites only the
words AROUND the place names, never the names: terse, polite, voice-transcript (no capitals or punctuation), filler words, a German lead-in,
function-word typos. A variant fails when the answer differs from the gold the original question has. The per-style score shows which kind of
phrasing hurts, and `--holdout` evaluates only the buildings whose id hashes into the 20 % holdout, so tuning on the rest never leaks.

  uv run python -m eval.gold --split train,dev --per-building 6
  uv run python -m eval.gold --split train,dev --holdout        # frozen holdout only"""

import argparse
import hashlib
import os
import random
import re

os.environ.setdefault("FLOORWISE_OFFLINE", "1")  # the deterministic parser alone: no model call may rescue a phrasing

from eval.common import load_questions, source_of
from eval.e2e_basic import _slim, correct
from eval.ledger import Ledger
from floorwise.agent.answer import answer_with_trace

TYPOS = {"from": "form", "the": "teh", "route": "rotue", "how": "hwo", "step-free": "step free", "closed": "clsoed", "maintenance": "maintainance"}


def _outside_names(text: str, edit) -> str:
    """Apply `edit` to the words around place names only: a place name is a run containing a digit or a capitalised word after 'from', 'to',
    'visit', 'then', 'at' up to a parenthesis or sentence end, so the simplest safe rule is to edit only lower-case function words."""
    return re.sub(r"\b[a-z][a-z-]*\b", lambda m: edit(m.group(0)), text)


STYLES = {
    "voice": lambda q: re.sub(r"[?.,!:;()]", "", q).lower(),
    "polite": lambda q: f"Hi, could you help me? {q} Thank you!",
    "filler": lambda q: f"um so {q[0].lower() + q[1:]}",
    "german_lead": lambda q: f"Kurze Frage: {q}",
    "typos": lambda q: _outside_names(q, lambda w: TYPOS.get(w, w)),
}


def holdout(building_id: str) -> bool:
    return int(hashlib.sha1(building_id.encode()).hexdigest(), 16) % 5 == 0


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.gold")
    cli.add_argument("--split", default="train,dev")
    cli.add_argument("--per-building", type=int, default=6)
    cli.add_argument("--seed", type=int, default=11)
    cli.add_argument("--holdout", action="store_true", help="only the frozen 20 percent of buildings")
    cli.add_argument("--min", type=float, default=0.93, help="lowest accepted share per style")
    args = cli.parse_args()
    ledger = Ledger("gold", {"splits": args.split, "per_building": args.per_building, "seed": args.seed, "holdout": args.holdout})
    by_building: dict[str, list] = {}
    for directory, question in load_questions(args.split.split(","), "questions_basic.jsonl"):
        by_building.setdefault(question["building_id"], []).append((directory, question))
    for building_id, items in sorted(by_building.items()):
        if args.holdout != holdout(building_id) and args.holdout:
            continue
        if not args.holdout and holdout(building_id):
            continue
        for directory, question in random.Random(f"{args.seed}:{building_id}").sample(items, min(args.per_building, len(items))):
            for style, rewrite in STYLES.items():
                text = rewrite(question["question"])
                reply, trace = answer_with_trace(directory, text)
                ledger.record(id=f"{question['id']}:{style}", kind=style, source=source_of(building_id), building=building_id, correct=correct(question, trace),
                              base_kind=question["kind"], question=text, expected=_slim(question["answer"]) if False else None, result=_slim(trace.get("result")))
    summary = ledger.finish()
    low = {k: v for k, v in summary.get("by_kind", {}).items() if sum(v.values()) and v.get("correct", 0) / sum(v.values()) < args.min}
    if not summary["total"] or low or summary.get("source_changed"):
        raise SystemExit(f"Gold bank: a phrasing style fell below {args.min:.0%}: {low}")


if __name__ == "__main__":
    main()
