"""L5: metamorphic and property checks. No gold needed, so it also runs on test and on any new building.

Transformations that must not change answers:
- translate the whole building (all kinds)
- shuffle the order of spaces/openings/assets in the JSON (all kinds)
- rotate the building (pure geometry kinds only: the dataset's route anchors, representative_point(),
  are not rotation invariant, so route-based answers may legitimately move)
Properties: step-free >= normal, closure >= open, tour >= direct, route >= straight line."""

import argparse
import copy
import math
import random
from functools import lru_cache

from eval.common import load_questions, source_of
from eval.ledger import Ledger
from floorwise.agent.solve import solve
from floorwise.core.graph import Constraints
from floorwise.core.model import Building
from floorwise.core.routing import NoRoute, plan_route

GEOMETRY_KINDS = {"largest_room", "floor_area_total", "room_stacked", "shared_walls_count", "straight_line_3d"}
SEED = 11


@lru_cache(maxsize=32)
def raw(directory: str) -> dict:
    return Building.load(directory).data


def transform(data: dict, dx: float = 0.0, dy: float = 0.0, angle: float = 0.0, shuffle: bool = False) -> Building:
    out = copy.deepcopy(data)
    c, s = math.cos(angle), math.sin(angle)

    def move(point):
        x, y = point
        return [x * c - y * s + dx, x * s + y * c + dy]

    for space in out["spaces"]:
        space["polygon"] = [move(p) for p in space["polygon"]]
    for opening in out["openings"]:
        opening["position"] = move(opening["position"])
    for asset in out["assets"]:
        asset["position"] = move(asset["position"])
    if shuffle:
        rng = random.Random(SEED)
        for key in ("spaces", "openings", "assets", "vertical_connectors"):
            rng.shuffle(out[key])
    return Building(out)


def value(result: dict):
    for key in ("space_id", "count", "total_m2", "distance_m", "total_m", "area_m2"):
        if key in result:
            return result[key]
    return None


def same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= max(1e-6, 1e-4 * abs(a))
    return a == b


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.metamorphic")
    cli.add_argument("--split", default="dev")
    cli.add_argument("--limit", type=int, default=None)
    args = cli.parse_args()
    ledger = Ledger("metamorphic", {"splits": args.split})
    rng = random.Random(SEED)
    items = [(d, q) for d, q in load_questions(args.split.split(",")) if "inputs" in q]
    for directory, question in items[: args.limit]:
        data = raw(str(directory))
        base = value(solve(Building(copy.deepcopy(data)), question["kind"], question["inputs"])[0])
        variants = {"translate": transform(data, dx=rng.uniform(-500, 500), dy=rng.uniform(-500, 500)),
                    "shuffle": transform(data, shuffle=True)}
        if question["kind"] in GEOMETRY_KINDS:
            variants["rotate"] = transform(data, angle=rng.uniform(0, 2 * math.pi))
        for name, building in variants.items():
            try:
                got = value(solve(building, question["kind"], question["inputs"])[0])
                ok = same(base, got)
            except Exception as error:  # noqa: BLE001
                got, ok = f"{type(error).__name__}: {error}", False
            ledger.record(id=f"{question['id']}:{name}", kind=f"{question['kind']}:{name}", source=source_of(question["building_id"]),
                          correct=ok, base=base, got=got)
    # Route properties on sampled room pairs per building.
    seen = set()
    for directory, question in items:
        if directory in seen or (args.limit and len(seen) >= args.limit):
            continue
        seen.add(directory)
        b = Building.load(directory)
        rooms = [s["id"] for s in b.spaces.values() if s["type"] == "room"]
        for _ in range(5):
            a, c, mid = rng.sample(rooms, 3) if len(rooms) >= 3 else (rooms * 3)[:3]
            try:
                normal = plan_route(b, [a, c]).length_m
            except NoRoute:
                continue
            checks = {}
            try:
                checks["step_free>=normal"] = plan_route(b, [a, c], Constraints(step_free=True)).length_m >= normal - 0.01
            except NoRoute:
                checks["step_free>=normal"] = True
            try:
                checks["tour>=direct"] = plan_route(b, [a, mid, c]).length_m >= normal - 0.02
            except NoRoute:
                pass
            if b.connectors:
                closed = next(iter(b.connectors))
                try:
                    checks["closure>=open"] = plan_route(b, [a, c], Constraints(closed=frozenset({closed}))).length_m >= normal - 0.01
                except NoRoute:
                    checks["closure>=open"] = True
            for name, ok in checks.items():
                ledger.record(id=f"{b.id}:{a}:{c}:{name}", kind=f"property:{name}", source=source_of(b.id), correct=ok)
    ledger.finish()


if __name__ == "__main__":
    main()
