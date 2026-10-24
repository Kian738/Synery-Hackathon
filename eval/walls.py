"""L8b: does the DRAWN route cross the walls we draw?

The judges' distances ignore wall geometry beyond the room outlines, but the 3D view shows walls (floorwise.core.scene)
and a route line that cuts through one looks broken. For random room pairs per building this suite plans the drawn route
(navigation mode, the same code the app uses) and intersects every drawn segment with the compiled walls of its floor.
A segment may touch a wall only where the compiled scene has a gap (a door or opening); a crossing anywhere else is a miss.

  uv run python -m eval.walls --split dev --pairs 6
  uv run python -m eval.walls --split train,dev,test --pairs 3      # every supplied building"""

import argparse
import random

from shapely import STRtree
from shapely.geometry import LineString

from eval.common import SPLITS, source_of
from eval.ledger import Ledger
from floorwise.core.graph import Constraints
from floorwise.core.model import Building
from floorwise.core.routing import NoRoute, plan_route
from floorwise.core.scene import compile_scene
from floorwise.paths import DATA

TOUCH_M = 0.05  # a wall may be grazed or touched at its end (door jambs); longer overlap is a crossing


def crossings(building: Building, route, trees: dict) -> list[dict]:
    found = []
    points = route.polyline
    for p, q in zip(points, points[1:]):
        if p["floor_id"] != q["floor_id"] or q.get("gap"):
            continue
        line = LineString([(p["x"], p["y"]), (q["x"], q["y"])])
        if line.length < 1e-6 or p["floor_id"] not in trees:
            continue
        tree, walls = trees[p["floor_id"]]
        for index in tree.query(line):
            wall = walls[int(index)]
            hit = line.intersection(wall)
            if hit.is_empty or hit.length > 0.0 and hit.length <= TOUCH_M:
                continue
            if line.crosses(wall) or hit.length > TOUCH_M:
                found.append({"floor": p["floor_id"], "at": [round(hit.centroid.x, 2), round(hit.centroid.y, 2)]})
    return found


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.walls")
    cli.add_argument("--split", default="dev")
    cli.add_argument("--pairs", type=int, default=6)
    cli.add_argument("--limit", type=int, default=None)
    cli.add_argument("--seed", type=int, default=21)
    args = cli.parse_args()
    ledger = Ledger("walls", {"splits": args.split, "pairs": args.pairs, "seed": args.seed})
    paths = sorted(p for s in args.split.split(",") if s in SPLITS for p in (DATA / s).glob("*/building.json"))[: args.limit]
    for path in paths:
        building = Building.load(path.parent)
        scene = compile_scene(building)
        trees = {}
        for fid in building.floors:
            walls = [LineString([w["a"], w["b"]]) for w in scene["walls"] if w["floor_id"] == fid]
            if walls:
                trees[fid] = (STRtree(walls), walls)
        rooms = [s for s, v in building.spaces.items() if v["type"] == "room"]
        if len(rooms) < 2:
            continue
        rng = random.Random(f"{args.seed}:{building.id}")
        for n in range(args.pairs):
            a, b = rng.sample(rooms, 2)
            try:
                route = plan_route(building, [a, b], Constraints(), humane=True)
            except NoRoute as error:
                ledger.record(id=f'{building.id}:{n}', kind='route unavailable', source=source_of(building.id), building=building.id,
                              correct=True, outcome='unavailable', reason=str(error), start=a, end=b)
                continue
            if not route.preview_available:
                ledger.record(id=f'{building.id}:{n}', kind='preview withheld', source=source_of(building.id), building=building.id,
                              correct=True, outcome='withheld', warnings=route.warnings, start=a, end=b)
                continue
            hits = crossings(building, route, trees)
            ledger.record(id=f"{building.id}:{n}", kind="route vs walls", source=source_of(building.id), building=building.id,
                          correct=not hits, crossings=len(hits), where=hits[:3], start=a, end=b)
    ledger.finish()


if __name__ == "__main__":
    main()
