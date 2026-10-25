"""L9: building EDITS (challenge level 4/5: "Add a door between rooms 2.03 and 2.04") checked against the kit.

For every building, per trial this suite edits a live session the way the agent does and compares the effect with the kit's own
implementation (starter_agent.building_map, kit 1.1.0) run on the same edited data, so a stale cache or a wrong graph cannot
hide itself:

  add_door     route length after the edit equals the kit's length on the building with that door, is never longer than before,
               and `undo` restores the original length exactly.
  remove_door  same for walling a door up (the kit says "no route" when it disconnects the pair; so must we).
  move_item    the item is found in its new room afterwards and back in the old one after undo.
  add_item     a new item is searchable in its room and gone after undo.

  uv run python -m eval.edits --split dev --per-building 4
  uv run python -m eval.edits --split train,dev,test --per-building 2     # every supplied building"""

import argparse
import copy
import random

from eval import judge
from eval.common import building_paths, source_of
from eval.ledger import Ledger
from floorwise.agent.session import Session
from floorwise.core.geometry import wall_neighbours
from floorwise.core.graph import Constraints
from floorwise.core.model import Building
from floorwise.core.routing import NoRoute, plan_route

TOLERANCE_M = 0.011


def ours(session: Session, a: str, b: str) -> float | None:
    try:
        return plan_route(session.building, [a, b], Constraints()).length_m
    except NoRoute:
        return None


def kits(data: dict, a: str, b: str) -> float | None:
    import networkx

    bm = judge.kit_map(copy.deepcopy(data))
    try:
        return bm.route(a, b).length_m
    except Exception as error:  # noqa: BLE001
        if isinstance(getattr(error, "__cause__", None), (networkx.NetworkXNoPath, networkx.NodeNotFound)):
            return None
        raise


def same(x: float | None, y: float | None) -> bool:
    return (x is None and y is None) or (x is not None and y is not None and abs(x - y) <= TOLERANCE_M)


def room_pairs(building: Building, rng: random.Random, count: int) -> list[tuple[str, str]]:
    joined = {frozenset(o["space_ids"]) for o in building.openings.values()}
    pairs = []
    rooms = [s for s, v in building.spaces.items() if v["type"] == "room"]
    rng.shuffle(rooms)
    for sid in rooms:
        for other, _ in wall_neighbours(building, sid):
            if building.spaces[other]["type"] == "room" and frozenset((sid, other)) not in joined:
                pairs.append((sid, other))
                break
        if len(pairs) >= count:
            break
    return pairs


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.edits")
    cli.add_argument("--split", default="dev")
    cli.add_argument("--per-building", type=int, default=4)
    cli.add_argument("--seed", type=int, default=13)
    cli.add_argument("--limit", type=int, default=None)
    args = cli.parse_args()
    ledger = Ledger("edits", {"splits": args.split, "per_building": args.per_building, "seed": args.seed})
    for path in building_paths(args.split.split(","))[: args.limit]:
        original = Building.load(path.parent)
        rng = random.Random(f"{args.seed}:{original.id}")
        base = {"source": source_of(original.id), "building": original.id}
        for index, (a, c) in enumerate(room_pairs(original, rng, args.per_building)):
            session = Session.for_building(original)
            before = ours(session, a, c)
            problem = ""
            try:
                result = session.add_door(a, c)
                if "added" not in result:
                    raise ValueError(result)
                after = ours(session, a, c)
                expected = kits(session.building.data, a, c)
                if not same(after, expected):
                    problem = f"after add_door we say {after}, the kit says {expected}"
                elif before is not None and (after is None or after > before + TOLERANCE_M):
                    problem = f"a new door made the route longer ({before} -> {after})"
                else:
                    session.undo()
                    if not same(ours(session, a, c), before) or not same(ours(session, a, c), kits(session.building.data, a, c)):
                        problem = "undo did not restore the original length"
            except Exception as error:  # noqa: BLE001
                problem = f"{type(error).__name__}: {error}"
            ledger.record(id=f"{original.id}:add_door:{index}", kind="add_door", correct=not problem, problem=problem, a=a, b=c, **base)

        doors = [o for o in original.openings.values() if o["kind"] == "door" and len(set(o["space_ids"])) == 2 and all(s in original.spaces for s in o["space_ids"])]
        rng.shuffle(doors)
        for index, door in enumerate(doors[: args.per_building]):
            session = Session.for_building(original)
            a, c = door["space_ids"]
            before = ours(session, a, c)
            problem = ""
            try:
                session.remove_door(door["id"])
                after, expected = ours(session, a, c), kits(session.building.data, a, c)
                if not same(after, expected):
                    problem = f"after remove_door we say {after}, the kit says {expected}"
                else:
                    session.undo()
                    if not same(ours(session, a, c), before):
                        problem = "undo did not restore the original length"
            except Exception as error:  # noqa: BLE001
                problem = f"{type(error).__name__}: {error}"
            ledger.record(id=f"{original.id}:remove_door:{index}", kind="remove_door", correct=not problem, problem=problem, a=a, b=c, **base)

        rooms = [s for s, v in original.spaces.items() if v["type"] == "room"]
        assets = list(original.assets.values())
        if len(rooms) >= 2 and assets:
            for index in range(min(args.per_building, 2)):
                session = Session.for_building(original)
                asset = rng.choice(assets)
                target = rng.choice([r for r in rooms if r != asset["space_id"]])
                problem = ""
                try:
                    session.move_asset(asset["id"], target)
                    if session.building.assets[asset["id"]]["space_id"] != target:
                        problem = "the moved item is not in its new room"
                    session.undo()
                    if session.building.assets[asset["id"]]["space_id"] != asset["space_id"]:
                        problem = problem or "undo did not return the item"
                    added = session.add_asset("Eval printer", "3d printer", target)
                    if not any(hit["id"] == added["id"] for hit in session.search("Eval printer")["assets"]):
                        problem = problem or "the new item cannot be found"
                    session.undo()
                    if added["id"] in session.building.assets:
                        problem = problem or "undo kept the new item"
                except Exception as error:  # noqa: BLE001
                    problem = f"{type(error).__name__}: {error}"
                ledger.record(id=f"{original.id}:items:{index}", kind="move_add_item", correct=not problem, problem=problem, **base)
    summary = ledger.finish()
    if not summary["total"] or summary["correct"] != summary["total"] or summary.get("source_changed"):
        raise SystemExit("Edit check failed")


if __name__ == "__main__":
    main()
