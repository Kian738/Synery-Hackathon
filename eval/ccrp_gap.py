"""How much faster is the exact plan than the classic CCRP heuristic across the dataset?

  uv run python -m eval.ccrp_gap [limit]

One hazard per building (the room with the most seats), the app's occupant estimate and escape window. Prints the
distribution and the buildings with the biggest gap, so a demo scenario can be chosen from data, not by luck."""
import random
import sys

from floorwise.core.model import Building
from floorwise.evacuation import Hazard, Occupants, best_doors, evacuate
from floorwise.paths import DATA
from floorwise.reason import occupants as seats
from floorwise.reason.evac_ops import DEFAULT_ESCAPE_S


def main(limit: int) -> None:
    gains = []
    paths = sorted(p for s in ("train", "dev") for p in (DATA / s).glob("*/building.json"))
    random.Random(7).shuffle(paths)
    rows = []
    for path in paths[:limit]:
        building = Building.load(path.parent)
        counts = seats.seat_counts(building)
        if not counts:
            continue
        room = max(counts, key=lambda s: (counts[s], s))
        people = Occupants.explicit(dict(seats.build(building, None).by_space))
        try:
            r = evacuate(building, people, Hazard(spaces=(room,), escape_s=DEFAULT_ESCAPE_S))
        except Exception:  # noqa: BLE001  a building the solver cannot take is skipped, not hidden: counted below
            continue
        hazard = Hazard(spaces=(room,), escape_s=DEFAULT_ESCAPE_S)
        plan = best_doors(building, people, hazard, max_fixes=1)
        if plan.fixes and plan.evacuated_after >= plan.evacuated_before:
            gains.append((1 - plan.T_after_s / plan.T_before_s, path.parent.name, plan.T_before_s, plan.T_after_s))
        if r.ccrp and r.evacuated == r.ccrp.evacuated == r.total and r.T_s > 0:
            rows.append((r.ccrp.T_s / r.T_s - 1, path.parent.name, building.label(room), r.T_s, r.ccrp.T_s, r.nearest_exit.T_s if r.nearest_exit else None))
    rows.sort(reverse=True)
    gaps = [g for g, *_ in rows]
    print(f"{len(rows)} scenarios where everyone gets out under both methods")
    print(f"CCRP slower than exact in {sum(g > 0 for g in gaps)}; median {sorted(gaps)[len(gaps) // 2]:.1%}, max {max(gaps):.1%}")
    for g, name, room, t, c, n in rows[:5]:
        print(f"  {g:6.1%}  {name}  fire in {room}: exact {t} s, CCRP {c} s, nearest-exit {n} s")

    gains.sort(reverse=True)
    print(f"a verified door fix exists in {len(gains)} of {len(paths[:limit])} sampled buildings; median gain {sorted(g for g, *_ in gains)[len(gains) // 2]:.0%}, best {gains[0][0]:.0%}" if gains else "no door fix found")
    for g, name, t0, t1 in gains[:4]:
        print(f"  {g:4.0%}  {name}: {t0} s -> {t1} s")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
