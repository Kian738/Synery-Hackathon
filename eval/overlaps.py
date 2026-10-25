"""L12: where do two rooms of one floor overlap in the data? (the source of floor z-fighting stripes in the 3D view)

Rooms that overlap draw two floors in the same place. Overlaps below MIN_M2 are digitising noise; larger ones are listed so the scene can draw
them as a blend of both colours instead of flickering. Stairs, lifts and outdoor spaces are included (they often sit inside a corridor).

  uv run python -m eval.overlaps --split train,dev,test --top 15"""

import argparse

from shapely import make_valid
from shapely.geometry import Polygon
from shapely.strtree import STRtree

from eval.common import building_paths
from floorwise.core.model import Building

MIN_M2 = 0.05


def overlaps(building: Building) -> list[tuple[str, str, str, float]]:
    out = []
    by_floor: dict[str, list[tuple[str, Polygon]]] = {}
    for sid, s in building.spaces.items():
        if len(s["polygon"]) >= 3:
            by_floor.setdefault(s["floor_id"], []).append((sid, make_valid(Polygon(s["polygon"]))))
    for floor, items in by_floor.items():
        tree = STRtree([p for _, p in items])
        for i, (sid, poly) in enumerate(items):
            for j in tree.query(poly):
                if j <= i:
                    continue
                other_id, other = items[j]
                area = poly.intersection(other).area
                if area >= MIN_M2:
                    out.append((floor, sid, other_id, area))
    return out


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.overlaps")
    cli.add_argument("--split", default="train,dev,test")
    cli.add_argument("--top", type=int, default=15)
    args = cli.parse_args()
    rows, total_pairs, with_overlap = [], 0, 0
    paths = building_paths(args.split.split(","))
    for path in paths:
        b = Building.load(path.parent)
        found = overlaps(b)
        total_pairs += len(found)
        if found:
            with_overlap += 1
            rows.append((sum(a for *_, a in found), len(found), b.id))
    print(f"{len(paths)} buildings, {with_overlap} with overlapping rooms, {total_pairs} overlapping pairs (>= {MIN_M2} m2)")
    for area, n, bid in sorted(rows, reverse=True)[: args.top]:
        print(f"  {bid:32} {n:4} pairs  {area:8.1f} m2")


if __name__ == "__main__":
    main()
