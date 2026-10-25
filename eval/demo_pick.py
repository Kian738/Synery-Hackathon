"""Pick the building and fire room for the one-button demo, from measurements.

  uv run python -m eval.demo_pick [--limit N]

A demo scenario should be fast (the whole plan answers in a few seconds), complete (everyone gets out, a verified door fix
exists, the responders find a way in) and worth watching (the planned evacuation clearly beats everyone taking the nearest
exit, several floors, a crowd). Every building in the kit is scanned with its busiest rooms as the fire room; the ranking and
the numbers behind it are written to runs/demo_pick.json so the choice can be audited and re-run. Nothing here is specific to
a building: another dataset gives another pick."""

import argparse
import json
import time
from pathlib import Path

from floorwise.core.model import Building
from floorwise.evacuation import Hazard, Occupants, best_doors, evacuate
from floorwise.paths import DATA, ROOT
from floorwise.reason import occupants as seats
from floorwise.reason.evac_ops import DEFAULT_ESCAPE_S

MAX_SECONDS = 4.0  # per building: skip anything slower, a demo must not make the audience wait
MIN_PEOPLE, MAX_PEOPLE = 60, 900


def scan(path: Path, rooms_per_building: int) -> list[dict]:
    building = Building.load(path)
    counts = seats.seat_counts(building)
    if not counts or len(building.floors) < 2:
        return []
    people = Occupants.explicit(dict(seats.build(building, None).by_space))
    if not MIN_PEOPLE <= people.total <= MAX_PEOPLE:
        return []
    found = []
    for room in sorted(counts, key=lambda s: (-counts[s], s))[:rooms_per_building]:
        started = time.perf_counter()
        hazard = Hazard(spaces=(room,), escape_s=DEFAULT_ESCAPE_S)
        try:
            result = evacuate(building, people, hazard)
            if time.perf_counter() - started > MAX_SECONDS or not result.nearest_exit or not result.ccrp:
                continue
            plan = best_doors(building, people, hazard, max_fixes=1)
        except Exception:  # noqa: BLE001  a building the solver cannot take is skipped, not hidden: it is counted below
            continue
        seconds = time.perf_counter() - started
        if seconds > MAX_SECONDS or result.stranded or not plan.fixes or not plan.fixes[0].verified:
            continue
        fix = plan.fixes[0]
        vs_nearest = result.nearest_exit.T_s / result.T_s - 1
        gain = 1 - fix.T_after_s / fix.T_before_s
        score = min(vs_nearest, 1.0) + 2 * min(gain, 0.3) + min(result.total / 400, 1) * 0.5 + min(len(building.floors) / 4, 1) * 0.3 - seconds / 20
        found.append({"building_id": building.id, "room_id": room, "room": building.label(room), "people": result.total,
                      "floors": len(building.floors), "T_s": result.T_s, "ccrp_s": result.ccrp.T_s,
                      "nearest_exit_s": result.nearest_exit.T_s, "vs_nearest": round(vs_nearest, 3),
                      "fix_before_s": fix.T_before_s, "fix_after_s": fix.T_after_s, "fix_gain": round(gain, 3),
                      "seconds": round(seconds, 2), "score": round(score, 3)})
    return found


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.demo_pick")
    cli.add_argument("--limit", type=int)
    cli.add_argument("--rooms", type=int, default=2)
    args = cli.parse_args()
    paths = sorted(p.parent for split in ("train", "dev", "test") for p in (DATA / split).glob("*/building.json"))[: args.limit]
    ranked: list[dict] = []
    for index, path in enumerate(paths):
        ranked += scan(path, args.rooms)
        if index % 20 == 19:
            print(f"scanned {index + 1}/{len(paths)}, {len(ranked)} usable so far", flush=True)
    ranked.sort(key=lambda r: -r["score"])
    out = ROOT / "runs" / "demo_pick.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"scanned": len(paths), "usable": len(ranked), "top": ranked[:15]}, indent=1), encoding="utf-8")
    print(f"{len(ranked)} usable of {len(paths)} buildings; top 5:")
    for r in ranked[:5]:
        print(f"  {r['score']:.2f}  {r['building_id']}  fire in {r['room']}: {r['people']} people, plan {r['T_s']} s vs nearest-exit "
              f"{r['nearest_exit_s']} s (+{r['vs_nearest']:.0%}), CCRP {r['ccrp_s']} s, fix {r['fix_before_s']}->{r['fix_after_s']} s, {r['seconds']} s")


if __name__ == "__main__":
    main()
