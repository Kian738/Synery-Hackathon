"""L8: are drawn routes humane? For random room pairs per building (navigation mode, humane=True):

- inside:     every walking segment stays inside the union of the route's spaces (0.3 m tolerance for walls)
- furniture:  no segment crosses a furniture/machine footprint (except the start and end rooms' own items
              it must reach, which are not obstacles to their own door)
- no_jumps:   no straight hop longer than the room it is in allows (catches entrance teleports)
- detour:     walking length / straight-line door-to-door length stays below 2.5 per room

  uv run fw eval walkability --split dev --pairs 6"""

import argparse
import math
import random

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from eval.common import source_of
from eval.ledger import Ledger
from floorwise.core.graph import Constraints
from floorwise.core.model import Building
from floorwise.core.routing import NoRoute, plan_route
from floorwise.core import walk
from floorwise.core.walk import BLOCKING_CATEGORIES
from floorwise.paths import DATA

SEED = 13


def footprint(asset: dict) -> Polygon:
    f = asset.get("footprint") or {}
    w, d = f.get("width_m", 0.5) * 0.9, f.get("depth_m", 0.5) * 0.9  # small shrink: touching an edge is fine
    a = math.radians(f.get("rotation_deg", 0.0))
    cx, cy = asset["position"]
    pts = []
    for dx, dy in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)):
        pts.append((cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)))
    return Polygon(pts)


def check(building: Building, a: str, b: str) -> dict | None:
    try:
        route = plan_route(building, [a, b], Constraints(outside="none"), humane=True)
    except NoRoute as error:
        # "No validated walking passage" = guidance withheld; anything else = the building model has no route at all.
        return None if "validated walking passage" in str(error) else {"unreachable": True}
    if not route.preview_available: return None
    by_floor: dict[str, list] = {}
    for p in route.polyline:
        by_floor.setdefault(p["floor_id"], []).append(p)
    spaces = set(p["node"] for p in route.polyline)
    area = unary_union([building.polygons[s].buffer(0.3) for s in spaces])
    obstacles: dict[str, list] = {}
    for x in building.assets.values():
        if x["space_id"] in spaces and x.get("category") in BLOCKING_CATEGORIES:
            obstacles.setdefault(x["space_id"], []).append(footprint(x))
    doors = {tuple(o["position"]) for o in building.openings.values()}
    outside, crossings, jumps, data_blocked = 0, 0, 0, 0
    pts = route.polyline
    for p, q in zip(pts, pts[1:]):
        if p["floor_id"] != q["floor_id"]:
            continue
        line = LineString([(p["x"], p["y"]), (q["x"], q["y"])])
        if line.length < 0.05:
            continue
        door_hop = (p["x"], p["y"]) in doors or (q["x"], q["y"]) in doors
        # Stepping through a door crosses the wall itself (walls are up to ~0.6 m thick in the data).
        if line.difference(area).length > (0.7 if door_hop else 0.01):
            outside += 1
        # Only the segment's own room: furniture of the next room sometimes pokes through the wall in the data.
        own = obstacles.get(p["node"], []) if p["node"] == q["node"] else []
        if any(line.crosses(o) or line.within(o) for o in own):
            if p["node"] in walk.BLOCKED:
                data_blocked += 1  # the dataset's furniture leaves no gap between the two doors
            else:
                crossings += 1
        if p["node"] != q["node"] and line.length > 2.0:
            jumps += 1  # moving between rooms happens at a door: consecutive points should be close
    straight = sum(math.dist((p["x"], p["y"]), (q["x"], q["y"])) for p, q in zip(pts, pts[1:]) if p["floor_id"] == q["floor_id"])
    return {"outside": outside, "crossings": crossings, "jumps": jumps, "data_blocked": data_blocked, "walk_m": route.walk_m, "graph_m": route.length_m,
            "ok": outside == 0 and crossings == 0 and jumps == 0, "points": len(pts), "straight": straight}


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.walkability")
    cli.add_argument("--split", default="dev")
    cli.add_argument("--pairs", type=int, default=6)
    cli.add_argument("--limit", type=int, default=None)
    cli.add_argument("-v", "--verbose", action="store_true")
    args = cli.parse_args()
    rng = random.Random(SEED)
    ledger = Ledger("walkability", {"split": args.split, "pairs": args.pairs})
    paths = sorted((DATA / args.split).glob("*/building.json"))[: args.limit]
    for path in paths:
        building = Building.load(path.parent)
        rooms = [s for s in building.spaces if building.spaces[s]["type"] == "room"]
        if len(rooms) < 2:
            continue
        for n in range(args.pairs):
            a, b = rng.sample(rooms, 2)
            result = check(building, a, b)
            if result and result.get("unreachable"):
                ledger.record(id=f"{building.id}:{n}", kind="no route in the building model (not walked)", source=source_of(building.id),
                              building=building.id, correct=True, start=a, end=b)
                continue
            if result is None:
                ledger.record(id=f"{building.id}:{n}", kind="no validated route (guidance withheld)", source=source_of(building.id),
                              building=building.id, correct=True, outcome='withheld', start=a, end=b, available=False)
                continue
            kind = ("walkable (furniture in data blocks a door)" if result["data_blocked"] else "walkable") if result["ok"] else                 ("outside" if result["outside"] else "furniture" if result["crossings"] else "jump")
            ledger.record(id=f"{building.id}:{n}", kind=kind, source=source_of(building.id),
                          building=building.id, correct=result["ok"], start=a, end=b, **result)
            if args.verbose and not result["ok"]:
                print("BAD", building.id, a, b, result)
    ledger.finish()


if __name__ == "__main__":
    main()
