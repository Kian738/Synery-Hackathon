"""Shared helpers for every eval suite: loading questions per split and the official scorer."""

import json
import csv
from pathlib import Path

from floorwise.paths import DATA, use_kit_modules

use_kit_modules()
from benchmark.score import score_reply  # noqa: E402  (official kit scorer, unchanged)

SPLITS = ("train", "dev", "test")


def building_paths(splits: list[str], data: Path = DATA) -> list[Path]:
    """The supplied manifest defines the official cohort, not unrelated folders."""
    manifest = data / "manifest.csv"
    if not manifest.exists():
        return sorted(p for split in splits for p in (data / split).glob("*/building.json"))
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r["split"] in splits]
    paths = sorted(data / r["split"] / r["building_id"] / "building.json" for r in rows)
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise ValueError(f"Required building files missing: {missing[:5]}")
    return paths


def load_questions(splits: list[str], filename: str = "questions.jsonl") -> list[tuple[Path, dict]]:
    items = []
    for building in building_paths(splits):
        path = building.parent / filename
        if not path.exists():
            raise ValueError(f"Required question file missing: {path}")
        with path.open(encoding="utf-8") as handle:
            items += [(path.parent, json.loads(line)) for line in handle if line.strip()]
    return items


def source_of(building_id: str) -> str:
    if building_id.startswith("proc-"):
        return "-".join(building_id.split("-")[:2])
    return building_id.split("-")[0]


__all__ = ["load_questions", "score_reply", "source_of", "SPLITS"]
