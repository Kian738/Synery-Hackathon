"""Does the top door fix survive the physics band and different occupancy? Prints one line per case.

  uv run python -m eval.sensitivity [building] [room]

A fix is stable when the same door is chosen at every specific flow in 1.0..1.6 and every occupancy scale.
Absolute seconds move with the assumptions; this checks that the ranking of fixes does not."""
import sys
from dataclasses import replace

from floorwise.core.model import Building
from floorwise.evacuation import Hazard, Occupants, best_doors, evacuate
from floorwise.evacuation.types import DEFAULT_PARAMS
from floorwise.paths import DATA

FLOWS = (1.0, 1.316, 1.6)
SCALES = (0.5, 1.0, 1.5)


def run(name: str, room: str) -> list[tuple[float, float, int, int, str | None]]:
    building = Building.load(DATA / "dev" / name)
    hazard = Hazard(spaces=(next(s["id"] for s in building.spaces.values() if s["name"] == room),))
    base = Occupants.from_seats(building)
    rows = []
    for flow in FLOWS:
        params = replace(DEFAULT_PARAMS, specific_flow=flow)
        for scale in SCALES:
            people = Occupants.explicit({k: max(1, round(v * scale)) for k, v in base.by_space.items()}) if scale != 1.0 else base
            result = evacuate(building, people, hazard, params=params, with_ccrp=False, with_nearest=False)
            plan = best_doors(building, people, hazard, params=params, max_fixes=1)
            top = plan.fixes[0].element if plan.fixes else None
            rows.append((flow, scale, result.evacuated, result.T_s, top))
    return rows


if __name__ == "__main__":
    name, room = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("proc-campus-dev-000", "Canteen 0.28")
    rows = run(name, room)
    for flow, scale, out, t, top in rows:
        print(f"flow {flow:5.3f}  occupancy x{scale:<3}  out {out:4d}  T {t:4d} s  top fix {top}")
    tops = {r[4] for r in rows}
    print(f"top fix stable across {len(rows)} cases: {len(tops) == 1}  ({', '.join(map(str, sorted(map(str, tops))))})")
