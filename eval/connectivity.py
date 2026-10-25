"""L11: which rooms can nobody walk to, and why? (the data behind "no route although the places look connected")

For every building the default route graph (no constraints) is split into connected parts. The part that holds the main entrance is the building;
every other room is listed with a reason, so a user report can be matched to a known cause instead of a guess:

  no_openings        no door, stair or lift touches the room (data fact: the kit has no edge either)
  outside_only       its only opening leads outside (a separate entrance, no route inside by the rules)
  island             a group of rooms joined to each other but not to the main part (no link in the data)
  wall_neighbour     like island, but a wall of the room lies within 0.5 m of a room of the main part: a door may have been left out of the data
  entrance_stranded  (building level) the default start, the main entrance, is not in the largest part: "Starting from <entrance>" cannot reach most rooms
  connector_stop     a stair or lift stop lies in a different part than the other stops of the same connector (floors that never join)

The reasons are data findings, not router bugs: the router equals the kit's on every building (`eval.differential`).

  uv run python -m eval.connectivity --split train,dev,test
  uv run python -m eval.connectivity --building swiss-460 --list"""

import argparse
from collections import Counter, defaultdict

import networkx as nx
from shapely.geometry import Polygon
from shapely.strtree import STRtree

from eval.common import building_paths
from floorwise.agent.session import main_entrance
from floorwise.core.graph import Constraints, RouteGraph
from floorwise.core.model import Building

NEAR_M = 0.5


def audit_building(building: Building) -> dict:
    graph = RouteGraph(building, Constraints()).graph
    spaces = {sid: s for sid, s in building.spaces.items() if s.get("type") != "outdoor" and len(s["polygon"]) >= 3}
    entrance = main_entrance(building)
    parts = [set(c) & set(spaces) for c in nx.connected_components(graph)]
    parts = [p for p in parts if p]
    if not parts:
        return {"spaces": len(spaces), "main": 0, "cut": {}, "findings": [], "entrance_stranded": False}
    main = max(parts, key=len)
    entrance_part = next((p for p in parts if entrance in p), main)
    openings_of: dict[str, list[dict]] = defaultdict(list)
    for o in building.openings.values():
        for sid in o["space_ids"]:
            openings_of[sid].append(o)
    connectors_of = defaultdict(list)
    for c in building.connectors.values():
        for sid in c["space_ids"]:
            connectors_of[sid].append(c)
    polygons = {sid: Polygon(s["polygon"]).buffer(0) for sid, s in spaces.items()}
    main_ids = [sid for sid in main]
    tree = STRtree([polygons[s] for s in main_ids])
    findings = []
    for part in parts:
        if part is main:
            continue
        for sid in sorted(part):
            floor = spaces[sid]["floor_id"]
            if not openings_of[sid] and not connectors_of[sid]:
                reason = "no_openings"
            elif all("outside" in o["space_ids"] for o in openings_of[sid]) and not connectors_of[sid]:
                reason = "outside_only"
            else:
                reason = "island"
                near = [main_ids[i] for i in tree.query(polygons[sid].buffer(NEAR_M)) if spaces[main_ids[i]]["floor_id"] == floor]
                if near:
                    reason = "wall_neighbour"
                if any(len({sid2 in main for sid2 in c["space_ids"]}) > 1 for c in connectors_of[sid]):
                    reason = "connector_stop"
            findings.append({"space": sid, "name": spaces[sid]["name"], "floor": floor, "reason": reason, "part_size": len(part)})
    return {"spaces": len(spaces), "main": len(main), "cut": dict(Counter(f["reason"] for f in findings)), "findings": findings,
            "entrance_stranded": entrance_part is not main, "entrance_part": len(entrance_part)}


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.connectivity")
    cli.add_argument("--split", default="train,dev,test")
    cli.add_argument("--building", default=None)
    cli.add_argument("--list", action="store_true")
    args = cli.parse_args()
    paths = building_paths(args.split.split(","))
    if args.building:
        paths = [p for p in paths if p.parent.name == args.building]
    totals: Counter = Counter()
    worst = []
    buildings_with = 0
    stranded = []
    spaces_total = 0
    for path in paths:
        building = Building.load(path.parent)
        result = audit_building(building)
        spaces_total += result["spaces"]
        cut = sum(result["cut"].values())
        totals.update(result["cut"])
        if result["entrance_stranded"]:
            stranded.append((building.id, result["entrance_part"], result["main"]))
        if cut:
            buildings_with += 1
            worst.append((cut, result["spaces"], building.id, result["cut"]))
        if args.list:
            for f in result["findings"]:
                print(f"{building.id:30} {f['reason']:15} {f['floor']:28} {f['name']}")
    print(f"{len(paths)} buildings, {spaces_total} rooms, {buildings_with} buildings with rooms cut off from the main entrance part")
    print("reasons: " + ", ".join(f"{k}={v}" for k, v in totals.most_common()) if totals else "reasons: none")
    print(f"entrance stranded (default start cannot reach the largest part): {len(stranded)} buildings")
    for bid, size, big in stranded[:20]:
        print(f"  {bid:32} entrance part {size} rooms, largest part {big}")
    for cut, n, bid, why in sorted(worst, reverse=True)[:15]:
        print(f"  {bid:32} {cut:4}/{n:<4} {why}")


if __name__ == "__main__":
    main()
