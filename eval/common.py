"""Shared helpers for every eval suite: loading questions per split and the official scorer."""

import json
from pathlib import Path

from floorwise.paths import DATA, use_kit_modules

use_kit_modules()
from benchmark.score import score_reply  # noqa: E402  (official kit scorer, unchanged)

SPLITS = ("train", "dev", "test")


def load_questions(splits: list[str], filename: str = "questions.jsonl") -> list[tuple[Path, dict]]:
    items = []
    for split in splits:
        for path in sorted((DATA / split).glob(f"*/{filename}")):
            with path.open(encoding="utf-8") as handle:
                items += [(path.parent, json.loads(line)) for line in handle if line.strip()]
    return items


def source_of(building_id: str) -> str:
    if building_id.startswith("proc-"):
        return "-".join(building_id.split("-")[:2])
    return building_id.split("-")[0]


__all__ = ["load_questions", "score_reply", "source_of", "SPLITS"]
