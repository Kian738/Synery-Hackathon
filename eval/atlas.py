"""Dataset atlas: how fragile is every kit building when one lift or door closes?

For each building: share of rooms that still reach an exit for anyone, for a step-free user and for a 1.1 m
trolley, plus the single worst closure for step-free users (chaos_test, rooted at the exits). The summary
rows are the claims in docs/JUDGING.md. The JSON is read-only data for the app (a building-health view)."""

import argparse
import csv
import json
import time
from collections import defaultdict
from pathlib import Path

from floorwise.core.graph import Constraints
from floorwise.core.model import Building
from floorwise.core.resilience import chaos_test
from floorwise.paths import DATA

TROLLEY_WIDTH_M = 1.1
LIFT_SHARE = 0.25
DOOR_ROOMS = 5
INTERIOR_KINDS = ("door", "opening")  # an entrance or a stair is expected to strand what lies behind it
PROFILES = {
    "anyone": Constraints(),
    "step_free": Constraints(step_free=True),
    "trolley": Constraints(step_free=True, min_width_m=TROLLEY_WIDTH_M),
}


def analyse(building_id: str, split: str, source: str) -> dict:
    building = Building.load(DATA / split / building_id)
    reach = {}
    for name, profile in PROFILES.items():
        result = chaos_test(building, profile)
        reach[name] = result
    step_free = reach["step_free"]
    rooms = step_free["rooms_total"]
    top = next((w for w in step_free["critical"] if w["kind"] != "entrance"), None)  # the front door is not news
    base = step_free["rooms_reachable"]
    return {
        "building_id": building_id, "split": split, "source": source, "rooms": rooms,
        "reach": {name: round(r["rooms_reachable"] / rooms, 3) if rooms else None for name, r in reach.items()},
        "top_weak_point": ({"name": top["name"], "kind": top["kind"], "rooms_lost": top["rooms_lost"],
                            "share": round(top["rooms_lost"] / max(1, base), 3)} if top else None),
        "lift_strands_quarter": any(w["kind"] == "lift" and w["rooms_lost"] / max(1, base) >= LIFT_SHARE for w in step_free["critical"]),
        "door_strands_five": any(w["kind"] in INTERIOR_KINDS and w["rooms_lost"] >= DOOR_ROOMS for w in step_free["critical"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="eval.atlas")
    parser.add_argument("--split", default="train,dev,test")
    parser.add_argument("--out", default="runs/atlas.json")
    args = parser.parse_args()
    splits = set(args.split.split(","))
    with (DATA / "manifest.csv").open(encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["split"] in splits]

    started = time.perf_counter()
    buildings = [analyse(row["building_id"], row["split"], row["source"]) for row in rows]
    elapsed = time.perf_counter() - started

    by_source = defaultdict(list)
    for item in buildings:
        by_source[item["source"]].append(item)
        by_source["all"].append(item)
    print(f"{'source':<16}{'bldgs':>6}{'rooms':>8}{'anyone':>8}{'stepfree':>9}{'trolley':>8}{'lift>=25%':>10}{'door>=5':>8}")
    summary = {}
    for source, items in sorted(by_source.items(), key=lambda kv: (kv[0] == "all", kv[0])):
        rooms = sum(i["rooms"] for i in items)
        share = {p: sum(i["reach"][p] * i["rooms"] for i in items if i["reach"][p] is not None) / rooms for p in PROFILES}
        lifts = sum(i["lift_strands_quarter"] for i in items)
        doors = sum(i["door_strands_five"] for i in items)
        summary[source] = {"buildings": len(items), "rooms": rooms, "reach": {p: round(v, 3) for p, v in share.items()},
                           "lift_strands_quarter": lifts, "door_strands_five": doors}
        print(f"{source:<16}{len(items):>6}{rooms:>8}{share['anyone']:>8.0%}{share['step_free']:>9.0%}{share['trolley']:>8.0%}{lifts:>10}{doors:>8}")
    print(f"{len(buildings)} buildings in {elapsed:.1f} s")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "buildings": buildings}, indent=1), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
