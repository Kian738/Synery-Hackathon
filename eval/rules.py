"""L3e: every route rule as a property, on every building, with no gold answers needed.

The rules come from the kit README (section 3) and from Synera's description of how routes are scored. Each check
below names the rule it enforces:

  walking        paths stay 15 cm off the walls (inside the shrunken outline) and match the edge length
  vertical       stairs 2 m per metre climbed; a lift 15 m once per ride + 1 m per metre; lifts join every pair of stops
  furniture      furniture is not an obstacle: removing every asset changes no edge
  closed         a closed stair, lift, opening or room is never used
  step_free      without stairs: no stair edge, no opening with steps; never shorter than the unrestricted route
  forklift       only openings and aisles of 3 m or wider, no stairs or lifts
  bays           production bays can be a destination but are never crossed
  outside        no way round the outside: entrances are door nodes of one interior space only
  valid          each route is valid under the kit's own measurement and equals its length

  uv run python -m eval.rules --split dev --pairs 4"""

import argparse
import copy
import itertools
import random

from shapely.geometry import LineString

from eval import judge
from eval.common import SPLITS, source_of
from eval.ledger import Ledger
from floorwise.core import spacewalk
from floorwise.core.graph import (DOOR_PREFIX, FORKLIFT_MIN_WIDTH_M, LIFT_FIXED_M, LIFT_M_PER_RISE, STAIRS_M_PER_RISE,
                                  Constraints, RouteGraph, _is_forklift_aisle, is_bay)
from floorwise.core.model import OUTSIDE, Building
from floorwise.paths import DATA

TOL = 1e-6


def check_walking(building: Building, rng: random.Random, samples: int) -> list[tuple[str, bool, str]]:
    rows = []
    spaces = rng.sample(sorted(building.spaces), min(samples, len(building.spaces)))
    for sid in spaces:
        space = building.spaces[sid]
        touching = [o for o in building.openings.values() if sid in o["space_ids"]]
        edges = {(a, b): w for a, b, w in spacewalk.base_edges(building)[sid]}
        polygon = spacewalk.outline(space["polygon"])
        walkable = polygon.buffer(-spacewalk.WALL_CLEARANCE_M)
        if walkable.is_empty or walkable.geom_type != "Polygon":
            walkable = polygon
        allowed = walkable.buffer(spacewalk.COVER_TOLERANCE_M)
        for (a, b), weight in itertools.islice(edges.items(), 6):
            line = spacewalk.path_inside(space, touching, a, b)
            length = sum(((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5 for p, q in zip(line, line[1:]))
            # The drawn walk, minus the door-to-landing steps at its ends, is a path inside the shrunken outline.
            inner = line[1:-1] if len(line) > 2 else line
            inside = len(inner) < 2 or allowed.covers(LineString(inner))
            straight = ((line[0][0] - line[-1][0]) ** 2 + (line[0][1] - line[-1][1]) ** 2) ** 0.5
            fallback = abs(weight - straight * spacewalk.BLOCKED_DETOUR_FACTOR) < 1e-6 and abs(length - weight) > 1e-6
            rows.append(("walking", inside and (abs(length - weight) < 1e-6 or fallback), f"{sid} {a}->{b} edge {weight:.3f} drawn {length:.3f}"))
    return rows


def check_vertical(building: Building) -> list[tuple[str, bool, str]]:
    rows = []
    graph = RouteGraph(building).graph
    elevations = {fid: float(f.get("elevation_m") or 0.0) for fid, f in building.floors.items()}
    space_floor = {sid: s["floor_id"] for sid, s in building.spaces.items()}
    for u, v, data in graph.edges(data=True):
        via = data.get("via")
        if via not in building.connectors:
            continue
        connector = building.connectors[via]
        rise = abs(elevations[space_floor[u]] - elevations[space_floor[v]])
        want = LIFT_FIXED_M + LIFT_M_PER_RISE * rise if connector["kind"] == "lift" else STAIRS_M_PER_RISE * rise
        rows.append(("vertical", abs(data["weight"] - round(want, 3)) < TOL, f"{via} {u}->{v} {data['weight']} want {want:.3f}"))
    for connector in building.connectors.values():
        if connector["kind"] == "lift" and len(connector["space_ids"]) > 2:
            n = len(connector["space_ids"])
            joined = sum(1 for a, b in itertools.combinations(connector["space_ids"], 2)
                         if graph.has_node(a) and graph.has_node(b) and any(d.get("via") == connector["id"] for d in (graph.get_edge_data(a, b) or {}).values()))
            rows.append(("vertical", joined == n * (n - 1) // 2, f"lift {connector['id']} joins {joined} of {n * (n - 1) // 2} stop pairs"))
    return rows


def check_furniture(building: Building) -> list[tuple[str, bool, str]]:
    bare = Building(copy.deepcopy({**building.data, "assets": []}))
    mine = sorted((tuple(sorted((u, v))), round(d["weight"], 3)) for u, v, d in RouteGraph(building).graph.edges(data=True))
    bare_edges = sorted((tuple(sorted((u, v))), round(d["weight"], 3)) for u, v, d in RouteGraph(bare).graph.edges(data=True))
    return [("furniture", mine == bare_edges, f"{len(building.assets)} assets do not change {len(mine)} edges")]


def check_outside(building: Building) -> list[tuple[str, bool, str]]:
    graph = RouteGraph(building).graph
    entrances = [o for o in building.openings.values() if OUTSIDE in o["space_ids"]]
    ok = OUTSIDE not in graph and all(len(graph[DOOR_PREFIX + o["id"]]) >= 1 for o in entrances if DOOR_PREFIX + o["id"] in graph)
    # every entrance door node touches only walks of its one interior space
    for o in entrances:
        node = DOOR_PREFIX + o["id"]
        if node in graph:
            ok = ok and {d.get("space") for _, _, d in graph.edges(node, data=True)} <= {s for s in o["space_ids"] if s != OUTSIDE}
    return [("outside", ok, f"{len(entrances)} entrances, no outside node")]


def route_checks(building: Building, rng: random.Random, pairs: int, bm) -> list[tuple[str, bool, str]]:
    rows = []
    rooms = sorted(building.spaces)
    if len(rooms) < 2:
        return rows
    connectors = sorted(building.connectors)
    for _ in range(pairs):
        a, b = rng.sample(rooms, 2)
        base = RouteGraph(building, Constraints(), keep=frozenset({a, b})).shortest(a, b)
        # valid: our route is a valid walk by the kit's measure and has the length we claim
        if base:
            sequence = RouteGraph(building, keep=frozenset({a, b})).expand(base[1])
            spaces = [n for n in sequence if not n.startswith(DOOR_PREFIX)]
            verdict = judge.measure(bm, spaces)
            rows.append(("valid", verdict.valid and abs(verdict.length_m - round(base[0], 2)) <= 0.011, f"{a}->{b} ours {base[0]:.2f} kit {verdict.length_m} {verdict.reason}"))
        for name, constraints in (("step_free", Constraints(step_free=True)),
                                  ("closed", Constraints(closed=frozenset({rng.choice(connectors)})) if connectors else None),
                                  ("forklift", Constraints(forklift=True)),
                                  ("bays", Constraints(bays_are_destinations=True))):
            if constraints is None:
                continue
            graph = RouteGraph(building, constraints, keep=frozenset({a, b}))
            found = graph.shortest(a, b)
            if found is None:
                rows.append((name, True, f"{a}->{b} no route under {name} (allowed)"))
                continue
            nodes = graph.expand(found[1])
            elements = graph.elements(found[1])
            spaces = [n for n in nodes if not n.startswith(DOOR_PREFIX)]
            middle = spaces[1:-1]
            ok = base is None or found[0] >= base[0] - 1e-9  # a rule never makes a route shorter
            if name == "step_free":
                ok = ok and all(building.connectors[e]["kind"] != "stairs" and building.connectors[e].get("step_free", True) if e in building.connectors
                                else building.openings[e].get("step_free", True) for e in elements)
            if name == "closed":
                ok = ok and not (constraints.closed & set(elements)) and not (constraints.closed & set(spaces))
            if name == "forklift":
                ok = ok and not any(e in building.connectors for e in elements) \
                    and all(float(building.openings[e].get("width_m") or 0) >= FORKLIFT_MIN_WIDTH_M - 1e-9 for e in elements if e in building.openings) \
                    and all(_is_forklift_aisle(building, building.spaces[s]) for s in middle)
            if name == "bays":
                ok = ok and not any(is_bay(building.spaces[s]) for s in middle)
            rows.append((name, ok, f"{a}->{b} {found[0]:.2f} m, elements {len(elements)}"))
    return rows


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.rules")
    cli.add_argument("--split", default="dev")
    cli.add_argument("--pairs", type=int, default=4)
    cli.add_argument("--samples", type=int, default=4)
    cli.add_argument("--limit", type=int, default=None)
    cli.add_argument("--seed", type=int, default=3)
    args = cli.parse_args()
    ledger = Ledger("rules", {"splits": args.split, "pairs": args.pairs, "seed": args.seed})
    paths = sorted(p for s in args.split.split(",") if s in SPLITS for p in (DATA / s).glob("*/building.json"))[: args.limit]
    for path in paths:
        building = Building.load(path.parent)
        rng = random.Random(f"{args.seed}:{building.id}")
        bm = judge.kit_map(copy.deepcopy(building.data))
        rows = check_walking(building, rng, args.samples) + check_vertical(building) + check_furniture(building) + check_outside(building) \
            + route_checks(building, rng, args.pairs, bm)
        for index, (kind, ok, note) in enumerate(rows):
            ledger.record(id=f"{building.id}:{kind}:{index}", kind=kind, source=source_of(building.id), building=building.id, correct=ok, note=note)
    ledger.finish()


if __name__ == "__main__":
    main()
