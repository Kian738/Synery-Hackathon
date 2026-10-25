"""Stress test of the multi-hop evacuation scenario across the dataset.

For each sampled building and hazard room, run the evacuation plan twice and check what must always hold: no crash,
identical results on rerun, the exact optimum never slower than the CCRP baseline, every proposed fix verified and
never worse (more people out, or as many and no slower), people conserved. Also records how much worse 'everyone to the nearest exit' is than the optimum."""

import argparse
import csv
import random

from eval.ledger import Ledger
from floorwise.core.model import Building
from floorwise.paths import DATA
from floorwise.reason import run_plan
from floorwise.reason.findings import assess
from floorwise.reason.templates import instantiate

SEATS = ("chair", "office_chair", "bench")


def hazard_rooms(building: Building, rng: random.Random, count: int) -> list[str]:
    seats: dict[str, int] = {}
    for asset in building.assets.values():
        if asset["type"] in SEATS:
            seats[asset["space_id"]] = seats.get(asset["space_id"], 0) + 1
    busiest = sorted(seats, key=lambda s: (-seats[s], s))[:1]
    others = sorted(s["id"] for s in building.spaces.values() if s["type"] == "room")
    return list(dict.fromkeys(busiest + rng.sample(others, min(count - len(busiest), len(others)))))[:count]


def check(building: Building, room: str) -> tuple[bool, str, dict]:
    plan = instantiate("evacuation", spec={"hazards": [{"spaces": [room]}], "responders": {"auto": True}})
    first, second = run_plan(building, plan), run_plan(building, plan)
    if [r.value for r in first.results] != [r.value for r in second.results]:
        return False, "not deterministic", {}
    evacuation = next((r.value for r in first.results if r.op == "evacuate" and r.ok), None)
    if evacuation is None:
        return True, f"abstained at {first.abstained.step}", {"abstained": first.abstained.step}
    stats = {"T": evacuation.T_s, "total": evacuation.total, "stranded": sum(evacuation.stranded.values())}
    if evacuation.evacuated + sum(evacuation.stranded.values()) != evacuation.total:
        return False, "people not conserved", stats
    if evacuation.ccrp and evacuation.T_s > evacuation.ccrp.T_s:
        return False, f"exact {evacuation.T_s} s slower than CCRP {evacuation.ccrp.T_s} s", stats
    if evacuation.nearest_exit:
        stats["nearest_over_exact"] = round(evacuation.nearest_exit.T_s / max(1, evacuation.T_s), 3)
    for fix in getattr(first.answer, "fixes", ()):
        better = fix.evacuated_after > fix.evacuated_before or (
            fix.evacuated_after == fix.evacuated_before and fix.T_after_s <= fix.T_before_s)  # most people out, then fastest
        if not fix.verified or not better:
            return False, f"fix {fix.element} not verified or not better", stats
    assess(first)  # the findings report must build from every trace
    return True, "", stats


def main() -> None:
    parser = argparse.ArgumentParser(prog="eval.scenarios")
    parser.add_argument("--split", default="train,dev")
    parser.add_argument("--limit", type=int, default=24, help="buildings, stratified by source; 0 = all")
    parser.add_argument("--hazards", type=int, default=2)
    args = parser.parse_args()
    with (DATA / "manifest.csv").open(encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle) if r["split"] in args.split.split(",")]
    rows.sort(key=lambda r: (r["source"], r["building_id"]))
    if args.limit:
        by_source: dict[str, list[dict]] = {}
        for row in rows:
            by_source.setdefault(row["source"], []).append(row)
        rows = [r for group in zip(*[g[:: max(1, len(g) // max(1, args.limit // len(by_source)))] for g in by_source.values()]) for r in group]
    ledger = Ledger("scenarios", vars(args))
    gaps = []
    for row in rows:
        building = Building.load(DATA / row["split"] / row["building_id"])
        for room in hazard_rooms(building, random.Random(row["building_id"]), args.hazards):
            try:
                ok, note, stats = check(building, room)
            except Exception as error:  # noqa: BLE001  a crash is a failed check, reported with its type
                ok, note, stats = False, f"{type(error).__name__}: {error}"[:160], {}
            if "nearest_over_exact" in stats:
                gaps.append(stats["nearest_over_exact"])
            ledger.record(id=f"{building.id}:{room}", kind="evacuation scenario", source=row["source"], correct=ok, note=note, **stats)
    summary = ledger.finish()
    if gaps:
        print(f"nearest-exit evacuation time over the exact optimum: median {sorted(gaps)[len(gaps) // 2]:.2f}x, "
              f"max {max(gaps):.2f}x, strictly worse in {sum(g > 1 for g in gaps)}/{len(gaps)} scenarios")
    if summary["correct"] != summary["total"]:
        raise SystemExit("scenario stress test found violations")


if __name__ == "__main__":
    main()
