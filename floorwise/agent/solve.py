"""Benchmark solver: a resolved query (kind + ids) goes in, a reply ending in 'Answer: ...' comes out.

Every number comes from floorwise.core; the reply also states what was understood and the evidence,
so a person (or a judge) can check it."""

from floorwise.agent.answer_format import number, space_label
from floorwise.core import ops
from floorwise.core.graph import Constraints
from floorwise.core.model import Building
from floorwise.core.resolve import normalise
from floorwise.core.routing import NoRoute, plan_route

KINDS = (
    "largest_room",
    "floor_area_total",
    "errand",
    "wide_delivery_count",
    "step_free_reachable_count",
    "room_stacked",
    "shared_walls_count",
    "straight_line_3d",
    "what_if_door",
    "locate",
    "count",
    "route",
    "tour",
)


class SolveError(ValueError):
    pass


def solve(building: Building, kind: str, inputs: dict) -> tuple[dict, str]:
    """Returns (result, reply)."""
    b = building
    if kind == "largest_room":
        result = ops.largest_room(b, inputs["floor_id"], inputs["room_type"])
        _check(result)
        label = space_label(b, result["space_id"])
        others = ", ".join(f"{space_label(b, r['space_id'])} {number(r['area_m2'], 1)} m²" for r in result["runners_up"])
        reply = (
            f"I compared every {_type(inputs['room_type'])} on {b.floor_name(inputs['floor_id'])} by polygon area. "
            f"The largest is {label} at {number(result['area_m2'])} m²"
            + (f" (next: {others})." if others else ".")
            + f"\nAnswer: {label}, {number(result['area_m2'])} m²"
        )
    elif kind == "floor_area_total":
        result = ops.floor_area_total(b, inputs["floor_id"], inputs["room_type"])
        reply = (
            f"I added up the polygon areas of all {result['count']} {_type(inputs['room_type'])} spaces on "
            f"{b.floor_name(inputs['floor_id'])}.\nAnswer: {number(result['total_m2'])}"
        )
    elif kind == "errand":
        result = ops.errand(b, inputs["start"], inputs["asset_type"], inputs["floor_id"], inputs["room_type"])
        _check(result)
        reply = (
            f"From {b.label(inputs['start'])} the nearest {_type(inputs['asset_type'])} is in "
            f"{b.label(result['pickup_space_id'])} ({number(result['first_leg_m'], 1)} m). From there to the largest "
            f"{_type(inputs['room_type'])} on {b.floor_name(inputs['floor_id'])}, {b.label(result['target_space_id'])}, "
            f"is {number(result['second_leg_m'], 1)} m.\nAnswer: {number(result['total_m'])}"
        )
    elif kind == "wide_delivery_count":
        result = ops.wide_delivery_count(b, inputs["start"], inputs["floor_id"], float(inputs["min_width"]))
        reply = (
            f"Using only step-free connections and doors at least {number(float(inputs['min_width']))} m wide from "
            f"{b.label(inputs['start'])}, {result['count']} rooms on {b.floor_name(inputs['floor_id'])} are reachable."
            f"\nAnswer: {result['count']}"
        )
    elif kind == "step_free_reachable_count":
        result = ops.step_free_reachable_count(b, inputs["start"], inputs["floor_id"], inputs["closed"])
        closed = b.connectors.get(inputs["closed"], {}).get("name", inputs["closed"])
        reply = (
            f"With {closed} out of service and only step-free connections from {b.label(inputs['start'])}, "
            f"{result['count']} rooms on {b.floor_name(inputs['floor_id'])} are reachable.\nAnswer: {result['count']}"
        )
    elif kind == "room_stacked":
        result = ops.room_stacked(b, inputs["start"], inputs["direction"])
        _check(result)
        label = space_label(b, result["space_id"])
        reply = (
            f"The space on the floor {inputs['direction']} that covers most of {b.label(inputs['start'])} is "
            f"{b.label(result['space_id'])} ({number(result['overlap_m2'], 1)} m² overlap).\nAnswer: {label}"
        )
    elif kind == "shared_walls_count":
        result = ops.shared_walls_count(b, inputs["start"])
        names = ", ".join(b.spaces[n["space_id"]]["name"] for n in result["neighbours"])
        reply = (
            f"Rooms sharing at least 1 m of wall with {b.label(inputs['start'])}: {names or 'none'}."
            f"\nAnswer: {result['count']}"
        )
    elif kind == "straight_line_3d":
        result = ops.straight_line_3d(b, inputs["first"], inputs["second"])
        reply = (
            f"Between the floor-plan centroids of {b.label(inputs['first'])} and {b.label(inputs['second'])} at their "
            f"floor elevations the straight-line distance is {number(result['distance_m'])} m."
            f"\nAnswer: {number(result['distance_m'])}"
        )
    elif kind == "what_if_door":
        result = ops.what_if_door(b, inputs["first"], inputs["second"], inputs["floor_id"])
        _check(result)
        reply = (
            f"With a new door between {b.label(inputs['first'])} and {b.label(inputs['second'])}, "
            f"{result['count']} rooms on {b.floor_name(inputs['floor_id'])} get a walk out of the building that is "
            f"more than 1 m shorter.\nAnswer: {result['count']}"
        )
    elif kind == "locate":
        result = locate(b, inputs)
        _check(result)
        where = "; ".join(f"{m['name']} in {m['room']}" for m in result["matches"][:6])
        more = f" (and {len(result['matches']) - 6} more)" if len(result["matches"]) > 6 else ""
        first = result["matches"][0]
        reply = f"I found {len(result['matches'])}: {where}{more}.\nAnswer: {first['room']}"
    elif kind == "count":
        result = ops_count(b, inputs)
        reply = (
            f"There are {result['count']} {_type(inputs['asset_type'])} items on {b.floor_name(inputs['floor_id'])}."
            f"\nAnswer: {result['count']}"
        )
    elif kind in ("route", "tour"):
        stops = inputs["stops"] if kind == "tour" else [inputs["start"], inputs["destination"]]
        constraints = Constraints(
            step_free=inputs.get("step_free", False),
            closed=frozenset({inputs["closed"]}) if inputs.get("closed") else frozenset(),
        )
        try:
            route = plan_route(b, stops, constraints)
        except NoRoute as error:
            result = {"reachable": False, "stops": stops}
            reply = f"{error}. There is no such route.\nAnswer: no route"
            return result, reply
        result = {
            "reachable": True, "stops": stops, "length_m": route.length_m,
            "space_path": [n for leg in route.legs for n in (leg.space_path if leg is route.legs[0] else leg.space_path[1:])],
            "legs": [{"from": leg.from_space_id, "to": leg.to_space_id, "length_m": leg.length_m,
                      "space_path": leg.space_path, "element_path": leg.element_path} for leg in route.legs],
        }
        understood = " → ".join(b.label(s) for s in stops)
        notes = f" ({', '.join(route.constraints)})" if route.constraints else ""
        steps = "\n".join(f"{i}. {step}" for i, step in enumerate(route.steps, 1))
        reply = f"Route {understood}{notes}: {number(route.length_m)} m.\n{steps}\nAnswer: {number(route.length_m)}"
    else:
        raise SolveError(f"unknown kind {kind}")
    return result, reply


def locate(b: Building, inputs: dict) -> dict:
    if inputs.get("asset_type"):
        assets = [a for a in b.assets.values() if a["type"] == inputs["asset_type"]]
    else:
        key = normalise(inputs["item"])
        assets = [a for a in b.assets.values() if key in normalise(a["name"])]
    if not assets:
        return {"error": f"nothing called {inputs['item']} in this building"}
    assets.sort(key=lambda a: (b.level(a["floor_id"]), a["name"]))
    return {
        "asset_ids": [a["id"] for a in assets],
        "matches": [{"asset_id": a["id"], "name": a["name"], "space_id": a["space_id"], "room": b.label(a["space_id"]),
                     "position": a["position"]} for a in assets],
    }


def ops_count(b: Building, inputs: dict) -> dict:
    assets = [a for a in b.assets.values() if a["type"] == inputs["asset_type"] and a["floor_id"] == inputs["floor_id"]]
    return {"count": len(assets), "asset_ids": [a["id"] for a in assets]}


def _check(result: dict) -> None:
    if "error" in result:
        raise SolveError(result["error"])


def _type(value: str) -> str:
    return value.replace("_", " ")
