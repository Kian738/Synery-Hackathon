"""QuerySpec: what a question asks, in the user's own words (mentions), before entity linking.

Both parsers (rules and Claude) produce a QuerySpec; resolve_spec() turns it into the id-level inputs the
solver takes, so parsing mistakes and linking mistakes are measured separately."""

from typing import Literal

from pydantic import BaseModel, Field

from floorwise.core import resolve as R
from floorwise.core.model import Building

Kind = Literal[
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
    "other",
]


class QuerySpec(BaseModel):
    kind: Kind
    floor: str | None = Field(None, description="Target floor as written, e.g. 'floor 2', 'ground floor', 'basement 1'")
    room_type: str | None = Field(None, description="Room type as written, e.g. 'meeting room', 'generic room'")
    asset_type: str | None = Field(None, description="Item to fetch as written, e.g. 'coat rack'")
    start: str | None = Field(None, description="Start / subject space with its floor, e.g. 'Office 0.29 (Ground floor)'")
    first: str | None = Field(None, description="First space of a pair, with floor")
    second: str | None = Field(None, description="Second space of a pair, with floor")
    closed: str | None = Field(None, description="Closed lift or staircase as written, e.g. 'Lift 1'")
    min_width: float | None = Field(None, description="Required door width in metres")
    direction: Literal["above", "below"] | None = None
    stairs_allowed: bool | None = Field(None, description="False if the person cannot use stairs")
    destination: str | None = Field(None, description="Route destination with floor, e.g. 'Lab 2.03 (Floor 2)'")
    stops: list[str] | None = Field(None, description="Tour: every stop in order, the start first")
    step_free: bool | None = Field(None, description="True if the route must be step-free (wheelchair, no stairs)")
    item: str | None = Field(None, description="locate/count: the item asked about, e.g. 'coffee machine'")


def resolve_spec(building: Building, spec: QuerySpec) -> dict:
    """Mentions -> solver inputs (same keys as the dataset's gold 'inputs'). Raises ResolveError."""
    b, inputs = building, {}
    if spec.kind in ("largest_room", "floor_area_total", "errand", "wide_delivery_count", "step_free_reachable_count",
                     "what_if_door", "count"):
        inputs["floor_id"] = R.resolve_floor(b, _need(spec.floor, "floor"))
    if spec.kind in ("largest_room", "floor_area_total", "errand"):
        inputs["room_type"] = R.resolve_room_type(b, _need(spec.room_type, "room type"))
    if spec.kind in ("errand", "wide_delivery_count", "step_free_reachable_count", "room_stacked", "shared_walls_count"):
        inputs["start"] = R.resolve_space(b, _need(spec.start, "start room")).id
    if spec.kind == "errand":
        inputs["asset_type"] = R.resolve_asset_type(b, _need(spec.asset_type or spec.item, "item"))
    if spec.kind == "wide_delivery_count":
        inputs["min_width"] = float(_need(spec.min_width, "width"))
    if spec.kind in ("locate", "count"):
        inputs["item"] = _need(spec.item or spec.asset_type, "item")
        try:
            inputs["asset_type"] = R.resolve_asset_type(b, inputs["item"])
        except R.ResolveError:
            if spec.kind == "count":
                raise
    if spec.kind == "route":
        inputs["start"] = R.resolve_space(b, _need(spec.start, "start")).id
        inputs["destination"] = R.resolve_space(b, _need(spec.destination, "destination")).id
        inputs["step_free"] = bool(spec.step_free)
        if spec.closed:
            inputs["closed"] = R.resolve_connector(b, spec.closed)
    if spec.kind == "tour":
        stops = _need(spec.stops, "stops")
        inputs["stops"] = [R.resolve_space(b, stop).id for stop in stops]
        inputs["step_free"] = bool(spec.step_free)
    if spec.kind == "step_free_reachable_count":
        inputs["closed"] = R.resolve_connector(b, _need(spec.closed, "closed lift or staircase"))
    if spec.kind == "room_stacked":
        inputs["direction"] = _need(spec.direction, "above or below")
    if spec.kind in ("straight_line_3d", "what_if_door"):
        inputs["first"] = R.resolve_space(b, _need(spec.first, "first room")).id
        inputs["second"] = R.resolve_space(b, _need(spec.second, "second room")).id
    if spec.kind == "what_if_door":
        inputs["door_floor_id"] = b.spaces[inputs["first"]]["floor_id"]
    return inputs


MAX_ALTERNATIVES = 12


def resolve_spec_all(building: Building, spec: QuerySpec) -> list[dict]:
    """Like resolve_spec, but when a space name is shared by several spaces (OSM has duplicate names),
    return one inputs dict per reading instead of failing. The benchmark path solves each and votes."""
    try:
        return [resolve_spec(building, spec)]
    except R.ResolveError as error:
        slots = {}
        for slot in ("start", "first", "second", "destination"):
            mention = getattr(spec, slot)
            if mention is None:
                continue
            try:
                R.resolve_space(building, mention)
            except R.ResolveError as slot_error:
                ids = [c["id"] for c in slot_error.candidates if "score" not in c]
                if not ids:
                    raise
                slots[slot] = ids
        stop_options = []
        for stop in spec.stops or []:
            try:
                stop_options.append([R.resolve_space(building, stop).id])
            except R.ResolveError as stop_error:
                ids = [c["id"] for c in stop_error.candidates if "score" not in c]
                if not ids:
                    raise
                stop_options.append(ids)
        if not slots and not any(len(o) > 1 for o in stop_options):
            raise error
    readings = [spec]
    for slot, ids in slots.items():
        readings = [r.model_copy(update={slot: space_id}) for r in readings for space_id in ids]
    if spec.stops:
        for index, ids in enumerate(stop_options):
            readings = [
                r.model_copy(update={"stops": [*r.stops[:index], space_id, *r.stops[index + 1:]]})
                for r in readings for space_id in ids
            ]
    return [resolve_spec(building, reading) for reading in readings[:MAX_ALTERNATIVES]]


def _need(value, what: str):
    if value is None or value == "":
        raise R.ResolveError(f"The question does not say which {what}.")
    return value
