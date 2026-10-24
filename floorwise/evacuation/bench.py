"""Measure the solver on real buildings: `uv run python -m floorwise.evacuation.bench [building-id ...]`.

Prints one row per building: size of the capacity graph and of the time-expanded network at the answer, wall
seconds for the exact solve (graph + search), CCRP and nearest-exit, and the three evacuation times.
Seat-count occupants (an estimate), no hazard, default FlowParams. Seconds are wall clock on the machine running it.
"""

import sys
import time

from floorwise.core.model import Building
from floorwise.evacuation.adapter import build_graph
from floorwise.evacuation.ccrp import ccrp
from floorwise.evacuation.nearest import nearest_exit
from floorwise.evacuation.solve import quickest
from floorwise.evacuation.ten import Problem
from floorwise.evacuation.types import DEFAULT_PARAMS, Occupants
from floorwise.paths import DATA

DEFAULT_BUILDINGS = ("proc-factory-dev-003", "proc-campus-dev-000", "swiss-1689", "osm-way27917482")


def find(name: str) -> Building:
    for split in ("dev", "train"):
        if (DATA / split / name).exists():
            return Building.load(DATA / split / name)
    raise SystemExit(f"unknown building {name}")


def measure(name: str) -> dict[str, object]:
    building = find(name)
    occupants = Occupants.from_seats(building)
    start = time.perf_counter()
    problem = Problem(build_graph(building, DEFAULT_PARAMS), occupants.by_space, None, (), DEFAULT_PARAMS)
    best = quickest(problem)
    exact_s = time.perf_counter() - start
    net = problem.net(max(best.steps, 1))
    start = time.perf_counter()
    heuristic = ccrp(problem)
    ccrp_s = time.perf_counter() - start
    start = time.perf_counter()
    nearest = nearest_exit(problem)
    nearest_s = time.perf_counter() - start
    return {
        "building": name, "spaces": len(building.spaces), "people": occupants.total,
        "nodes": net.node_count, "arcs": len(net.tail), "T_exact_s": best.steps * DEFAULT_PARAMS.dt_s,
        "T_ccrp_s": heuristic.T_s, "T_nearest_s": nearest.T_s, "exact_sec": round(exact_s, 2),
        "ccrp_sec": round(ccrp_s, 2), "nearest_sec": round(nearest_s, 2),
    }


def main() -> None:
    rows = [measure(name) for name in (sys.argv[1:] or DEFAULT_BUILDINGS)]
    header = list(rows[0])
    print(" | ".join(header))
    for row in rows:
        print(" | ".join(str(row[key]) for key in header))


if __name__ == "__main__":
    main()
