"""Spatial operators: one function per question family. Inputs are resolved ids; outputs are plain
dicts with the answer plus the evidence the agent needs to explain it."""

from dataclasses import replace

from floorwise.core import geometry
from floorwise.core.graph import Constraints, RouteGraph
from floorwise.core.model import OUTSIDE, Building

# Spaces a person counts as "rooms" in reachability and adjacency questions.
NON_ROOM_TYPES = {"corridor", "stair", "lift", "outdoor"}
NON_ROOM_ROOM_TYPES = {"corridor", "stairwell", "lift"}


def is_room(building: Building, space_id: str) -> bool:
    space = building.spaces[space_id]
    return space["type"] not in NON_ROOM_TYPES and space["room_type"] not in NON_ROOM_ROOM_TYPES


def is_proper_room(building: Building, space_id: str) -> bool:
    """Reachability counts ("into how many rooms") use spaces of type room only: no halls, corridors, cores."""
    return building.spaces[space_id]["type"] == "room"


def rooms_of_type(building: Building, floor_id: str, room_type: str) -> list[str]:
    return [space["id"] for space in building.spaces_on(floor_id) if space["room_type"] == room_type]


def largest_room(building: Building, floor_id: str, room_type: str) -> dict:
    ranked = sorted(
        ((geometry.area(building, space_id), space_id) for space_id in rooms_of_type(building, floor_id, room_type)),
        reverse=True,
    )
    if not ranked:
        return {"error": f"no {room_type} on {building.floor_name(floor_id)}"}
    best_area, best = ranked[0]
    return {
        "space_id": best,
        "area_m2": round(best_area, 2),
        "runners_up": [{"space_id": space_id, "area_m2": round(value, 2)} for value, space_id in ranked[1:4]],
    }


def floor_area_total(building: Building, floor_id: str, room_type: str) -> dict:
    members = rooms_of_type(building, floor_id, room_type)
    total = sum(geometry.area(building, space_id) for space_id in members)
    return {"total_m2": round(total, 2), "count": len(members), "space_ids": members}


def reachable_rooms_on_floor(building: Building, start: str, floor_id: str, constraints: Constraints) -> dict:
    graph = RouteGraph(building, constraints, keep=frozenset({start}))
    reached = graph.reachable(start)
    rooms = [
        space["id"]
        for space in building.spaces_on(floor_id)
        if space["id"] in reached and is_proper_room(building, space["id"])
    ]
    return {"count": len(rooms), "space_ids": rooms, "constraints": constraints.describe()}


def wide_delivery_count(building: Building, start: str, floor_id: str, min_width: float) -> dict:
    return reachable_rooms_on_floor(building, start, floor_id, Constraints(step_free=True, min_width_m=min_width))


def step_free_reachable_count(building: Building, start: str, floor_id: str, closed: str) -> dict:
    return reachable_rooms_on_floor(building, start, floor_id, Constraints(step_free=True, closed=frozenset({closed})))


def errand(building: Building, start: str, asset_type: str, floor_id: str, room_type: str,
           constraints: Constraints = Constraints()) -> dict:
    graph = RouteGraph(building, constraints)
    from_start = graph.distances_from(start)
    holders = {asset["space_id"] for asset in building.assets.values() if asset["type"] == asset_type}
    candidates = sorted((from_start[space_id], space_id) for space_id in holders if space_id in from_start)
    if not candidates:
        return {"error": f"no reachable room has a {asset_type}"}
    first_leg, pickup = candidates[0]
    target = largest_room(building, floor_id, room_type)
    if "error" in target:
        return target
    second = graph.shortest(pickup, target["space_id"])
    if second is None:
        return {"error": "the target room cannot be reached from the pickup room"}
    return {
        "total_m": round(first_leg + second[0], 2),
        "pickup_space_id": pickup,
        "first_leg_m": round(first_leg, 2),
        "target_space_id": target["space_id"],
        "second_leg_m": round(second[0], 2),
    }


def room_stacked(building: Building, start: str, direction: str) -> dict:
    ranked = geometry.stacked(building, start, direction)
    if not ranked:
        return {"error": f"no floor {direction} this room"}
    return {
        "space_id": ranked[0][0],
        "overlap_m2": round(ranked[0][1], 2),
        "runners_up": [{"space_id": space_id, "overlap_m2": round(value, 2)} for space_id, value in ranked[1:4]],
    }


def shared_walls_count(building: Building, start: str) -> dict:
    neighbours = [
        (space_id, length) for space_id, length in geometry.wall_neighbours(building, start) if is_room(building, space_id)
    ]
    return {"count": len(neighbours), "neighbours": [{"space_id": s, "wall_m": round(l, 2)} for s, l in neighbours]}


def straight_line_3d(building: Building, first: str, second: str) -> dict:
    return {"distance_m": round(geometry.distance_3d(building, first, second), 2)}


def distances_to_exit(building: Building, constraints: Constraints = Constraints()) -> dict[str, float]:
    graph = RouteGraph(building, replace(constraints, outside="free"))
    return graph.distances_from(OUTSIDE)


def what_if_door(building: Building, first: str, second: str, floor_id: str, threshold_m: float = 1.0, constraints: Constraints = Constraints()) -> dict:
    position = geometry.wall_midpoint(building, first, second)
    if position is None:
        return {"error": "these two spaces do not share a wall"}
    door = {
        "id": f"whatif-{first}-{second}",
        "floor_id": building.spaces[first]["floor_id"],
        "space_ids": [first, second],
        "kind": "door",
        "position": [position[0], position[1]],
        "width_m": 0.9,
        "step_free": True,
        "synthetic": True,
    }
    before = distances_to_exit(building, constraints)
    after = distances_to_exit(building, replace(constraints, extra_openings=constraints.extra_openings + (door,)))
    improved = []
    for space in building.spaces_on(floor_id):
        space_id = space["id"]
        if not is_room(building, space_id) or space_id not in after:
            continue
        old = before.get(space_id, float("inf"))
        if old - after[space_id] > threshold_m:
            improved.append({"space_id": space_id, "before_m": round(old, 2), "after_m": round(after[space_id], 2)})
    return {"count": len(improved), "door_position": [round(position[0], 3), round(position[1], 3)], "improved": improved}
