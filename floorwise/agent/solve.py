"""Benchmark solver: a resolved query (kind + ids) goes in, a reply ending in 'Answer: ...' comes out.

Every number comes from floorwise.core; the reply also states what was understood and the evidence,
so a person (or a judge) can check it."""

from floorwise.agent.answer_format import number, space_label
from floorwise.core import ops
from floorwise.core.model import Building

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
    else:
        raise SolveError(f"unknown kind {kind}")
    return result, reply


def _check(result: dict) -> None:
    if "error" in result:
        raise SolveError(result["error"])


def _type(value: str) -> str:
    return value.replace("_", " ")
