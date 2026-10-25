"""L10: which way do wall-backed items face? (data audit behind the 3D orientation of toilets, sinks, sofas, counters ...)

The renderer draws every model with its front on local -Z, rotated by `footprint.rotation_deg` counter-clockwise in plan, so the front
points along (-sin a, cos a) and the back along (sin a, -cos a). For furniture that stands against a wall, the back should point at the
nearest wall. This audit measures, per asset type over every supplied building, how often the back / front / left / right points at the
nearest wall (within 35 degrees), and recommends the offset that makes the back face the wall. It reads data only; no answer is used.

  uv run python -m eval.orientation --split train,dev,test --limit 40
  uv run python -m eval.orientation --types toilet,sink,sofa,bed"""

import argparse
import math
from collections import defaultdict

from shapely.geometry import LineString, Point

from eval.common import building_paths
from floorwise.core.model import Building

WALL_BACKED = ("toilet", "sink", "kitchen_counter", "sofa", "bed", "single_bed", "wardrobe", "fridge", "stove", "tv_stand", "bookshelf",
               "shelf", "nightstand", "desk", "bathtub", "dishwasher", "washing_machine")
OFFSETS = {"back": 0, "right": 90, "front": 180, "left": 270}  # degrees added to the rotation so that this side becomes the back


def audit(buildings, types):
    hits: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total: dict[str, int] = defaultdict(int)
    for building in buildings:
        polygons = {sid: LineString(list(s["polygon"]) + [s["polygon"][0]]) for sid, s in building.spaces.items() if len(s["polygon"]) >= 3}
        for asset in building.assets.values():
            if asset["type"] not in types or asset["space_id"] not in polygons:
                continue
            rotation = (asset.get("footprint") or {}).get("rotation_deg", 0.0)
            point = Point(asset["position"])
            wall = polygons[asset["space_id"]]
            nearest = wall.interpolate(wall.project(point))
            to_wall = math.atan2(nearest.y - point.y, nearest.x - point.x)
            total[asset["type"]] += 1
            for name, extra in OFFSETS.items():
                a = math.radians(rotation + extra)
                back = math.atan2(-math.cos(a), math.sin(a))  # direction of the back for this reading
                delta = abs((back - to_wall + math.pi) % (2 * math.pi) - math.pi)
                if delta < math.radians(35):
                    hits[asset["type"]][name] += 1
    return hits, total


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.orientation")
    cli.add_argument("--split", default="train,dev,test")
    cli.add_argument("--limit", type=int, default=None)
    cli.add_argument("--types", default=",".join(WALL_BACKED))
    args = cli.parse_args()
    types = set(args.types.split(","))
    paths = building_paths(args.split.split(","))[: args.limit]
    hits, total = audit((Building.load(p.parent) for p in paths), types)
    print(f"{'type':18} {'n':>6}  back  right  front  left   -> offset that puts the back on the wall")
    for t in sorted(total):
        share = {k: hits[t][k] / total[t] for k in OFFSETS}
        best = max(share, key=share.get)
        print(f"{t:18} {total[t]:6}  " + "  ".join(f"{share[k]:4.0%}" for k in OFFSETS) + f"   -> {OFFSETS[best]:3} deg ({best})")


if __name__ == "__main__":
    main()
