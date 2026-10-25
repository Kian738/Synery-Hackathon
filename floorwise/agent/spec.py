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
    forklift: bool | None = Field(None, description="route/tour/errand: a forklift drives it (aisles and openings of 3 m or wider only)")
    bays_destinations: bool | None = Field(None, description="production bays may be entered to deliver but never crossed as a shortcut")
    avoid: list[str] | None = Field(None, description="rooms or room types the route must not pass through")
    closed_more: list[str] | None = Field(None, description="further closed or blocked lifts, stairs, rooms or doors")


def _rules(b: Building, spec: QuerySpec, inputs: dict) -> None:
    """Route rules beyond step-free and one closed lift (the judges' rule list): without stairs, forklift,
    production bays as destinations, several closed or blocked places, places to avoid. Only present when asked."""
    if spec.stairs_allowed is False:
        inputs["step_free"] = True  # "without stairs: lifts, ramps and doors only"
    if spec.forklift:
        inputs["forklift"] = True
    if spec.bays_destinations:
        inputs["bays_are_destinations"] = True
    if spec.closed_more:
        inputs["closed_ids"] = [R.resolve_element(b, item) for item in spec.closed_more]
    if spec.avoid:
        targets = [R.resolve_avoid(b, item) for item in spec.avoid]
        inputs["avoid_spaces"] = [v for k, v in targets if k == "space"]
        inputs["avoid_types"] = [v for k, v in targets if k == "type"]


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
        _rules(b, spec, inputs)
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
            inputs["closed"] = R.resolve_element(b, spec.closed)
        _rules(b, spec, inputs)
    if spec.kind == "tour":
        stops = _need(spec.stops, "stops")
        inputs["stops"] = [R.resolve_space(b, stop).id for stop in stops]
        inputs["step_free"] = bool(spec.step_free)
        if spec.closed:
            inputs["closed"] = R.resolve_element(b, spec.closed)
        _rules(b, spec, inputs)
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


MAX_ALTERNATIVES = 64
ENUMERATE_LIMIT = 4096
SLOTS = ("start", "first", "second", "destination")


def _even_picks(total: int, count: int) -> list[int]:
    """count indices spread evenly over range(total), always including the first and last: a fixed,
    order-independent sample instead of the first few readings (which would pin the first slot)."""
    if total <= count:
        return list(range(total))
    return sorted({round(i * (total - 1) / (count - 1)) for i in range(count)})


def _decode(index: int, radices: list[int]) -> list[int]:
    digits = []
    for radix in reversed(radices):
        index, digit = divmod(index, radix)
        digits.append(digit)
    return digits[::-1]


def _candidate_ids(building: Building, mention: str, strict: bool = True) -> list[str] | None:
    """None: the mention resolves to one space. Otherwise the spaces that tie on name (and floor).
    A mention that matches nothing exactly re-raises its own error when strict, so the caller sees why."""
    try:
        R.resolve_space(building, mention)
        return None
    except R.ResolveError as error:
        ids = [c["id"] for c in error.candidates if "score" not in c]
        if not ids and strict:
            raise
        return ids


def resolve_spec_all(building: Building, spec: QuerySpec) -> list[dict]:
    """Like resolve_spec, but when a space name is shared by several spaces (OSM has duplicate names),
    return one inputs dict per reading instead of failing. The benchmark path solves each and votes.

    Repeated mentions may denote the same space; zero-length readings remain valid.
    More than MAX_ALTERNATIVES readings are sampled evenly across all combinations, not cut off after the first."""
    try:
        return [resolve_spec(building, spec)]
    except R.ResolveError as error:
        slots: dict[str, list[str]] = {}
        for slot in SLOTS:
            mention = getattr(spec, slot)
            if mention is None:
                continue
            ids = _candidate_ids(building, mention)
            if ids is not None:
                slots[slot] = ids
        stop_options: list[list[str]] = []
        for stop in spec.stops or []:
            ids = _candidate_ids(building, stop)
            stop_options.append([R.resolve_space(building, stop).id] if ids is None else ids)
        if not slots and not any(len(o) > 1 for o in stop_options):
            raise error
    names = list(slots)
    options = [slots[name] for name in names] + stop_options
    radices = [len(o) for o in options]
    total = 1
    for radix in radices:
        total *= radix

    def reading(index: int) -> dict:
        choice = _decode(index, radices)
        update: dict = {name: options[i][choice[i]] for i, name in enumerate(names)}
        if spec.stops:
            update["stops"] = [options[len(names) + i][choice[len(names) + i]] for i in range(len(spec.stops))]
        return resolve_spec(building, spec.model_copy(update=update))

    indices = range(total) if total <= ENUMERATE_LIMIT else _even_picks(total, ENUMERATE_LIMIT)
    readings = [reading(i) for i in indices]
    return [readings[i] for i in _even_picks(len(readings), MAX_ALTERNATIVES)]


def describe_ambiguity(building: Building, spec: QuerySpec) -> list[dict]:
    """What a question leaves open: for every mention that fits several spaces, the tied candidates and
    which of their recorded properties could tell them apart. Display and diagnosis only; never used to choose."""
    found = []
    mentions = [(slot, getattr(spec, slot)) for slot in SLOTS if getattr(spec, slot)]
    mentions += [(f"stops[{i}]", stop) for i, stop in enumerate(spec.stops or [])]
    for slot, mention in mentions:
        ids = _candidate_ids(building, mention, strict=False)
        if not ids or len(ids) < 2:
            continue
        spaces = [building.spaces[i] for i in ids]
        differing = [key for key in ("ref", "room_type", "floor_id") if len({str(s.get(key)) for s in spaces}) > 1]
        found.append({
            "slot": slot,
            "mention": mention,
            "candidates": [{"id": s["id"], "label": building.label(s["id"]), "ref": s.get("ref")} for s in spaces],
            "differs_in": differing,
        })
    return found


def _need(value, what: str):
    if value is None or value == "":
        raise R.ResolveError(f"The question does not say which {what}.")
    return value
