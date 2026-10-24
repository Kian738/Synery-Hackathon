"""The only module of floorwise.reason that calls floorwise.core.

Operators call these small functions with plain ids and a World; if a core signature changes (the route model is
being rewritten), only this file changes. Core errors become Abstain here, so operators stay free of core types."""

from dataclasses import fields
from pathlib import Path

from floorwise.core import geometry, ops
from floorwise.core import resolve as R
from floorwise.core.graph import Constraints, RouteGraph
from floorwise.core.model import OUTSIDE, Building
from floorwise.core.routing import NoRoute, plan_route
from floorwise.reason.types import Abstain, RouteFacts, World


def load_building(source: "Building | str | Path") -> Building:
    return source if isinstance(source, Building) else Building.load(source)


# ---------- names to ids ----------


def _resolving(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except R.ResolveError as error:
        raise Abstain(str(error), tuple(error.candidates)) from error


def resolve_space(building: Building, text: str, floor_id: str | None = None) -> str:
    return _resolving(R.resolve_space, building, text, floor_id).id


def resolve_floor(building: Building, text: str) -> str:
    return _resolving(R.resolve_floor, building, text)


def resolve_room_type(building: Building, text: str) -> str:
    return _resolving(R.resolve_room_type, building, text)


def resolve_item_type(building: Building, text: str) -> str:
    return _resolving(R.resolve_asset_type, building, text)


def resolve_element(building: Building, text: str) -> str:
    """A connector, an opening or a space: an id as given, a lift or stair by name, else a space by name."""
    if text in building.connectors or text in building.openings or text in building.spaces:
        return text
    try:
        return R.resolve_connector(building, text)
    except R.ResolveError as connector_error:
        try:
            return resolve_space(building, text)
        except Abstain as space_error:
            # report whichever reading matched the words better
            def best(candidates):
                return max((c.get("score", 0) for c in candidates), default=0)

            raise (Abstain(str(connector_error), tuple(connector_error.candidates))
                   if best(connector_error.candidates) >= best(space_error.candidates) else space_error) from space_error


def is_element(building: Building, element_id: str) -> bool:
    return element_id in building.spaces or element_id in building.openings or element_id in building.connectors


# ---------- the world as core constraints ----------

_HAS_OUTSIDE_MODE = "outside" in {f.name for f in fields(Constraints)}


def constraints(world: World, *, step_free: bool = False, min_width_m: float | None = None,
                no_stairs: bool = False, no_lifts: bool = False) -> Constraints:
    """People walk indoors: no free hop between entrances (when the route model still has that switch)."""
    extra = {"outside": "none"} if _HAS_OUTSIDE_MODE else {}
    return Constraints(step_free=step_free, min_width_m=min_width_m, closed=world.closed, no_stairs=no_stairs,
                       no_lifts=no_lifts, extra_openings=tuple(world.extra_openings), **extra)


def route(world: World, start: str, end: str, **flags) -> RouteFacts:
    try:
        found = plan_route(world.building, [start, end], constraints(world, **flags))
    except NoRoute as error:
        raise Abstain(str(error)) from error
    leg = found.legs[0]
    return RouteFacts(found.length_m, tuple(leg.space_path), tuple(leg.element_path))


def reach(world: World, start: str, floor_id: str | None = None, **flags) -> tuple[str, ...]:
    """Rooms (type room, as everywhere in the benchmark) reachable on foot from start, optionally on one floor."""
    building = world.building
    graph = RouteGraph(building, constraints(world, **flags), keep=frozenset({start}))
    return tuple(sorted(
        space_id for space_id in graph.reachable(start)
        if space_id in building.spaces and ops.is_proper_room(building, space_id)
        and (floor_id is None or building.spaces[space_id]["floor_id"] == floor_id)
    ))


def nearest(world: World, start: str, candidates: tuple[str, ...], **flags) -> str:
    graph = RouteGraph(world.building, constraints(world, **flags), keep=frozenset({start}))
    distances = graph.distances_from(start)
    reachable = sorted((distances[c], c) for c in candidates if c in distances)
    if not reachable:
        raise Abstain(f"none of the {len(candidates)} candidate(s) can be reached from {world.building.label(start)}")
    return reachable[0][1]


# ---------- facts about the building ----------


def exits(world: World) -> tuple[str, ...]:
    """Spaces with an entrance that is still usable in this world."""
    building = world.building
    found = set()
    for opening in [*building.openings.values(), *world.extra_openings]:
        if OUTSIDE in opening["space_ids"] and opening["id"] not in world.closed:
            found.update(s for s in opening["space_ids"] if s != OUTSIDE and s not in world.closed)
    return tuple(sorted(found))


def area_m2(building: Building, space_ids: tuple[str, ...]) -> float:
    return round(sum(geometry.area(building, space_id) for space_id in space_ids), 2)


def spaces_of_type(building: Building, room_type: str, floor_id: str | None = None) -> tuple[str, ...]:
    floors = [floor_id] if floor_id else list(building.floors)
    return tuple(sorted(space_id for floor in floors for space_id in ops.rooms_of_type(building, floor, room_type)))


def spaces_with_item(building: Building, item_type: str, floor_id: str | None = None) -> tuple[str, ...]:
    return tuple(sorted({a["space_id"] for a in building.assets.values()
                         if a["type"] == item_type and (floor_id is None or a["floor_id"] == floor_id)}))


def hazard_targets_exist(building: Building, spaces: tuple[str, ...], elements: tuple[str, ...]) -> None:
    unknown = [s for s in spaces if s not in building.spaces] + [e for e in elements if not is_element(building, e)]
    if unknown:
        raise Abstain(f"the scenario names unknown id(s): {', '.join(unknown)}")

