"""Where should a new door go? Rank the doors a building could get, then prove the best ones by running the stress test again with each added.

1. Candidates: two rooms on one floor that share a wall of at least 1 m and have no door between them.
2. Shortcut value (cheap, exact on the distances to the exit): every person in room a saves max(0, d(a) - (d(c) + L)) metres when the door joins a to c,
   L = straight line between the two room centres, and the same the other way round; the sum over people is the candidate's score.
3. The best few candidates are re-run through the full stress test (same seed) with the door added. A door that makes the 95th percentile worse is
   returned with regress=true and the reason: more doors can move a queue to a worse place (Braess effect), and that is shown, not hidden.

The door is placed where the wall is clear of furniture and corners (core.geometry.wall_midpoint), 1.0 m wide."""

import math

import networkx as nx

from floorwise.core import geometry
from floorwise.core.graph import Constraints, RouteGraph, anchor
from floorwise.core.model import OUTSIDE, Building
from floorwise.core.walk import BLOCKING_CATEGORIES, _footprint_polygon
from floorwise.stress.sim import Spec, estimate_occupants, run

NEW_DOOR_WIDTH_M = 1.0
MIN_SHARED_WALL_M = 1.0
REGRESS_TOLERANCE = 0.02


def make_door(building: Building, first: str, second: str, serial: int) -> dict | None:
    furniture = [_footprint_polygon(x, 0) for x in building.assets.values() if x["space_id"] in (first, second) and x.get("category") in BLOCKING_CATEGORIES]
    position = geometry.wall_midpoint(building, first, second, avoid=furniture)
    if position is None:
        return None
    floor_id = building.spaces[first]["floor_id"]
    return {"id": f"{floor_id}-O-stress{serial}", "floor_id": floor_id, "space_ids": [first, second], "kind": "door",
            "position": [round(position[0], 3), round(position[1], 3)], "width_m": NEW_DOOR_WIDTH_M, "step_free": True, "synthetic": True}


def candidates(building: Building) -> list[tuple[str, str]]:
    joined = {frozenset(o["space_ids"]) for o in building.openings.values()}
    out = []
    for sid, space in sorted(building.spaces.items()):
        if space["type"] in ("outdoor", "lift", "stair") or len(space["polygon"]) < 3:
            continue
        for other, length in geometry.wall_neighbours(building, sid, MIN_SHARED_WALL_M):
            if other <= sid or frozenset((sid, other)) in joined or building.spaces[other]["type"] in ("outdoor", "lift", "stair"):
                continue
            out.append((sid, other))
    return out


def exit_candidates(building: Building) -> list[dict]:
    """New doors to the outside: a room on the ground floor with at least 1.5 m of its outline that no other room touches."""
    from shapely.geometry import Point
    from shapely.ops import unary_union

    levels = sorted(f["level"] for f in building.data["floors"])
    ground = 0 if 0 in levels else levels[0]
    floor_ids = {f["id"] for f in building.data["floors"] if f["level"] == ground}
    out = []
    by_floor = {fid: [(sid, building.polygons[sid]) for sid, s in building.spaces.items() if s["floor_id"] == fid and len(s["polygon"]) >= 3] for fid in floor_ids}
    for fid, items in by_floor.items():
        for sid, poly in items:
            if building.spaces[sid]["type"] in ("outdoor", "lift", "stair"):
                continue
            others = unary_union([p for other, p in items if other != sid]).buffer(0.4)
            free = poly.exterior.difference(others)
            parts = [g for g in getattr(free, "geoms", [free]) if g.length >= 1.5]
            if not parts:
                continue
            best = max(parts, key=lambda g: g.length)
            middle = best.interpolate(0.5, normalized=True)
            door = {"id": f"{fid}-O-stressX{len(out) + 1}", "floor_id": fid, "space_ids": [sid, OUTSIDE], "kind": "entrance",
                    "position": [round(middle.x, 3), round(middle.y, 3)], "width_m": NEW_DOOR_WIDTH_M, "step_free": True, "synthetic": True}
            out.append({"room": sid, "door": door, "wall_m": round(best.length, 1)})
    return out

def recommend(building: Building, spec: Spec | None = None, top: int = 5, verify: int = 8) -> dict:
    spec = spec or Spec()
    counts = spec.occupants if spec.occupants is not None else estimate_occupants(building)[0]
    graph = RouteGraph(building, Constraints(closed=spec.closed, outside="exits", no_lifts=True, step_free=spec.kind == "step_free_evacuation")).graph
    if OUTSIDE not in graph:
        return {"error": "This building has no entrance, so there is nothing to evacuate to.", "candidates": []}
    dist = nx.single_source_dijkstra_path_length(graph, OUTSIDE, weight="weight")
    scored = []
    for a, c in candidates(building):
        if a not in dist and c not in dist:
            continue
        straight = math.dist(anchor(building, a), anchor(building, c))
        da, dc = dist.get(a, math.inf), dist.get(c, math.inf)
        saved = counts.get(a, 0) * max(0.0, da - (dc + straight)) + counts.get(c, 0) * max(0.0, dc - (da + straight))
        if math.isinf(da) != math.isinf(dc):   # a door that connects a cut-off room to the way out is worth more than any shortcut
            saved += 1000.0 * (counts.get(a, 0) if math.isinf(da) else counts.get(c, 0)) + 1.0
        if saved > 0:
            scored.append((saved, a, c))
    scored.sort(reverse=True)
    exits = []
    for item in exit_candidates(building):
        room = item['room']
        if room not in dist and counts.get(room, 0) == 0:
            continue
        reach = math.dist(anchor(building, room), item['door']['position']) * 1.3
        saved = counts.get(room, 0) * max(0.0, dist.get(room, math.inf) - reach) if room in dist else 1000.0 * counts.get(room, 0) + 1.0
        # a new way out also relieves the queue at the busiest exit: weight rooms next to it up by the people routed through it
        exits.append((saved, item))
    exits.sort(key=lambda e: -e[0])
    before = run(building, spec)
    results = []
    for rank, (saved, a, c) in enumerate(scored[:verify]):
        door = make_door(building, a, c, rank + 1)
        if door is None:
            continue
        after = run(building, Spec(spec.kind, spec.occupants, spec.closed, spec.pre_movement_median_s, spec.seed, (door,)))
        bk, ak = before.kpis, after.kpis
        delta = round(ak["p95_s"] - bk["p95_s"], 1)
        regress = ak["p95_s"] > bk["p95_s"] * (1 + REGRESS_TOLERANCE) or ak["stranded"] > bk["stranded"]
        results.append({
            "first": a, "second": c, "first_name": building.label(a), "second_name": building.label(c), "floor_id": door["floor_id"], "door": door,
            "shortcut_people_m": round(saved, 1), "p95_before_s": bk["p95_s"], "p95_after_s": ak["p95_s"], "delta_p95_s": delta,
            "max_before_s": bk["max_s"], "max_after_s": ak["max_s"], "stranded_before": bk["stranded"], "stranded_after": ak["stranded"],
            "regress": regress,
            "reason": ("moves the queue elsewhere: the 95th percentile gets worse" if regress and ak["stranded"] <= bk["stranded"]
                       else f"cuts the 95th percentile by {-delta:g} s" if delta < 0 else "no change in the 95th percentile (it helps single rooms, not the slowest people)"),
        })
    for rank, (saved, item) in enumerate(exits[:verify]):
        door = item["door"]
        after = run(building, Spec(spec.kind, spec.occupants, spec.closed, spec.pre_movement_median_s, spec.seed, (door,)))
        bk, ak = before.kpis, after.kpis
        delta = round(ak["p95_s"] - bk["p95_s"], 1)
        regress = ak["p95_s"] > bk["p95_s"] * (1 + REGRESS_TOLERANCE) or ak["stranded"] > bk["stranded"]
        results.append({
            "first": item["room"], "second": OUTSIDE, "first_name": building.label(item["room"]), "second_name": "the outside", "floor_id": door["floor_id"], "door": door,
            "shortcut_people_m": round(saved, 1), "p95_before_s": bk["p95_s"], "p95_after_s": ak["p95_s"], "delta_p95_s": delta,
            "max_before_s": bk["max_s"], "max_after_s": ak["max_s"], "stranded_before": bk["stranded"], "stranded_after": ak["stranded"], "regress": regress, "new_exit": True,
            "reason": ("moves the queue elsewhere: the 95th percentile gets worse" if regress and ak["stranded"] <= bk["stranded"]
                       else f"a new way out: cuts the 95th percentile by {-delta:g} s" if delta < 0 else "a new way out, but the slowest people are held up elsewhere"),
        })
    results.sort(key=lambda r: (r["regress"], r["delta_p95_s"], -r["shortcut_people_m"]))
    return {"baseline": before.kpis, "candidates": results[:top], "assumptions": before.assumptions, "checked": len(results), "ranked": len(scored)}
