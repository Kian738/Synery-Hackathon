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
            if (types and asset["type"] not in types) or asset["space_id"] not in polygons:
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


SURFACES = ("desk", "dining_table", "seminar_table", "meeting_table", "reading_table", "canteen_table", "workbench", "lab_bench", "coffee_table",
            "outdoor_table", "reception_desk", "assembly_station", "packing_station")
FOCUS = ("tv_stand", "whiteboard", "projector_screen", "display_screen", "lectern", "coffee_table", "fireplace")
RELATIONAL = {  # type -> kinds of neighbour in the same space that its front should point at
    "chair": SURFACES, "office_chair": SURFACES, "dining_chair": SURFACES, "outdoor_chair": SURFACES, "armchair": FOCUS, "sofa": FOCUS,
    "lecture_seating_row": ("whiteboard", "projector_screen", "display_screen", "lectern"), "bench": SURFACES, "microscope": ("lab_bench",),
}


def relational(buildings):
    """How often the rendered front (the model's -Z, after the offset) points at the nearest table / screen of the same space, per offset."""
    hits: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total: dict[str, int] = defaultdict(int)
    for building in buildings:
        by_space: dict[str, list] = defaultdict(list)
        for asset in building.assets.values():
            by_space[asset["space_id"]].append(asset)
        for items in by_space.values():
            for asset in items:
                targets = RELATIONAL.get(asset["type"])
                if not targets:
                    continue
                near = [(math.dist(asset["position"], o["position"]), o) for o in items if o["type"] in targets and o is not asset]
                if not near:
                    continue
                distance, other = min(near, key=lambda t: t[0])
                if distance > 3.0:
                    continue
                to_target = math.atan2(other["position"][1] - asset["position"][1], other["position"][0] - asset["position"][0])
                rotation = (asset.get("footprint") or {}).get("rotation_deg", 0.0)
                total[asset["type"]] += 1
                for name, extra in OFFSETS.items():
                    a = math.radians(rotation + extra)
                    front = math.atan2(math.cos(a), -math.sin(a))
                    if abs((front - to_target + math.pi) % (2 * math.pi) - math.pi) < math.radians(35):
                        hits[asset["type"]][name] += 1
    return hits, total


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.orientation")
    cli.add_argument("--split", default="train,dev,test")
    cli.add_argument("--limit", type=int, default=None)
    cli.add_argument("--types", default=",".join(WALL_BACKED))
    cli.add_argument("--relational", action="store_true", help="chairs/sofas/seating: face the nearest table or screen")
    args = cli.parse_args()
    types = set(args.types.split(",")) if args.types != "all" else set()
    paths = building_paths(args.split.split(","))[: args.limit]
    if args.relational:
        hits, total = relational(Building.load(p.parent) for p in paths)
        print(f"{'type':18} {'n':>6}  extra=0 90 180 270  (share whose front points at the nearest table/screen)")
        for t in sorted(total):
            print(f"{t:18} {total[t]:6}  " + "  ".join(f"{hits[t][k] / total[t]:4.0%}" for k in OFFSETS))
        return
    hits, total = audit((Building.load(p.parent) for p in paths), types)
    print(f"{'type':18} {'n':>6}  back  right  front  left   -> offset that puts the back on the wall")
    for t in sorted(total):
        share = {k: hits[t][k] / total[t] for k in OFFSETS}
        best = max(share, key=share.get)
        print(f"{t:18} {total[t]:6}  " + "  ".join(f"{share[k]:4.0%}" for k in OFFSETS) + f"   -> {OFFSETS[best]:3} deg ({best})")


if __name__ == "__main__":
    main()
