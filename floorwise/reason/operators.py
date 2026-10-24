"""The operator algebra: a registry of typed operators a plan can call.

Each operator is (name, input types, output type, fn, postconditions). Types are plain tags, so a plan can be
type-checked as a DAG before anything runs. A graph-changing operator returns a new World (G0 -> G1 -> ...) and
never touches the Building. Evacuation operators are placeholders until floorwise/evacuation registers them with
`REGISTRY.register(operator, replace=True)`.

Types: World Space Spaces Element Floor RoomType ItemType Number Text Bool Mapping List Route Comparison
Occupants ScenarioSpec, and the evacuation types Evacuation Bottleneck Responder DoorCandidates DoorFix.
A param type may list alternatives: "Space|Spaces"."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from floorwise.reason import adapters, occupants
from floorwise.reason.types import Abstain, Comparison, Occupants, ScenarioSpec, World

Check = Callable[[Any, Mapping[str, Any]], bool]  # (value, resolved args) -> held?
NOT_PLUGGED_IN = "provided by floorwise/evacuation"


class _Bottom:
    def __repr__(self) -> str:
        return "BOTTOM"


BOTTOM = _Bottom()  # an operator may return this instead of raising Abstain


@dataclass(frozen=True)
class Param:
    name: str
    type: str
    required: bool = True


@dataclass(frozen=True)
class Operator:
    name: str
    params: tuple[Param, ...]
    returns: str
    fn: Callable[..., Any]
    post: tuple[tuple[str, Check], ...] = ()
    unit: str = ""  # appended to a number in the one-line summary
    doc: str = ""


class Registry:
    def __init__(self, operators: Iterable[Operator] = ()) -> None:
        self._operators: dict[str, Operator] = {}
        for operator in operators:
            self.register(operator)

    def register(self, operator: Operator, *, replace: bool = False) -> None:
        if operator.name in self._operators and not replace:
            raise ValueError(f"operator '{operator.name}' is already registered; pass replace=True to plug in a real one")
        self._operators[operator.name] = operator

    def get(self, name: str) -> Operator:
        return self._operators[name]

    def __contains__(self, name: str) -> bool:
        return name in self._operators

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._operators))

    def copy(self) -> "Registry":
        return Registry(self._operators.values())


# ---------- the type system ----------

SUPERTYPES = {"Space": {"Element"}}  # a Space can be closed, like a door or a lift
LITERALS = {  # which JSON literals may stand for a value of this type (ids are validated against the building)
    "Text": {"Text"}, "Number": {"Number"}, "Bool": {"Bool"}, "Mapping": {"Mapping"}, "List": {"List"},
    "Space": {"Text"}, "Element": {"Text"}, "Floor": {"Text"}, "RoomType": {"Text"}, "ItemType": {"Text"}, "Spaces": {"List"},
}


def literal_tag(value: Any) -> str:
    if isinstance(value, bool):
        return "Bool"
    if isinstance(value, (int, float)):
        return "Number"
    return {str: "Text", dict: "Mapping", list: "List", tuple: "List"}.get(type(value), type(value).__name__)


def alternatives(type_: str) -> tuple[str, ...]:
    return tuple(type_.split("|"))


def accepts_type(expected: str, actual: str) -> bool:
    return any(actual == alt or alt in SUPERTYPES.get(actual, ()) for alt in alternatives(expected))


def accepts_literal(expected: str, value: Any) -> bool:
    return any(literal_tag(value) in LITERALS.get(alt, ()) for alt in alternatives(expected))


# ---------- helpers ----------


def _ids(value: str | tuple[str, ...]) -> tuple[str, ...]:
    return (value,) if isinstance(value, str) else tuple(value)


def _flags(step_free, min_width_m, no_stairs, no_lifts) -> dict:
    if min_width_m is not None and not min_width_m > 0:
        raise Abstain(f"min_width_m must be a positive number of metres, got {min_width_m!r}")
    return {"step_free": bool(step_free), "min_width_m": min_width_m, "no_stairs": bool(no_stairs), "no_lifts": bool(no_lifts)}


_WALK = (Param("step_free", "Bool", False), Param("min_width_m", "Number", False),
         Param("no_stairs", "Bool", False), Param("no_lifts", "Bool", False))


def _in(collection) -> Check:
    return lambda value, args: all(v in collection(args) for v in _ids(value))


# ---------- names to ids ----------


def _resolve(world, text, floor=None):
    return adapters.resolve_space(world.building, text, floor)


def _resolve_element(world, text):
    return adapters.resolve_element(world.building, text)


# ---------- graph-changing: each returns a new World ----------


def _describe(building, element: str) -> str:
    if element in building.connectors:
        return building.connectors[element]["name"]
    return building.label(element) if element in building.spaces else element


def _close(world: World, element: str) -> World:
    return world.derive(closed={element}, change=f"closed {_describe(world.building, element)}")


def _reopen(world: World, element: str) -> World:
    if element not in world.closed:
        raise Abstain(f"{element} is not closed in {world.label}")
    return World(world.building_id, world.building, world.closed - {element}, world.extra_openings,
                 world.history + (f"reopened {_describe(world.building, element)}",))


def _scenario(spec: Mapping) -> ScenarioSpec:
    try:
        return ScenarioSpec.from_dict(spec)
    except (ValueError, TypeError) as error:
        raise Abstain(f"invalid scenario: {error}") from error


def _apply_hazards(world: World, spec: ScenarioSpec) -> World:
    """Close what is unusable from the start. A hazard with a later start_s stays in the spec for the solver."""
    if not spec.hazards:
        raise Abstain("the scenario names no hazard")
    active = [h for h in spec.hazards if not h.start_s]
    spaces = tuple(s for h in spec.hazards for s in h.spaces)
    elements = tuple(e for h in spec.hazards for e in h.elements)
    adapters.hazard_targets_exist(world.building, spaces, elements)
    targets = {t for h in active for t in (*h.spaces, *h.elements)}
    return world.derive(closed=targets, change=f"hazard at {', '.join(sorted(targets)) or 'a later time only'}")


def _occupants(world: World, spec: ScenarioSpec | None = None) -> Occupants:
    try:
        return occupants.build(world.building, spec.occupants if spec else None)
    except ValueError as error:
        raise Abstain(str(error)) from error


def _lineage_grew(value: World, args: Mapping) -> bool:
    return value.history[:-1] == args["world"].history and value.building is args["world"].building


def _hazards_closed(value: World, args: Mapping) -> bool:
    return all(t in value.closed for h in args["spec"].hazards if not h.start_s for t in (*h.spaces, *h.elements))


def _not_plugged_in(**_: Any):
    raise NotImplementedError(NOT_PLUGGED_IN)


def _placeholder(name: str, params: tuple[Param, ...], returns: str) -> Operator:
    return Operator(name, params, returns, _not_plugged_in, doc=NOT_PLUGGED_IN)


def build_registry() -> Registry:
    world, spec = Param("world", "World"), Param("spec", "ScenarioSpec")
    floor = Param("floor", "Floor", False)
    registry = Registry([
        Operator("resolve", (world, Param("text", "Text"), floor), "Space", _resolve,
                 (("resolved id is a space of the building", _in(lambda a: a["world"].building.spaces)),),
                 doc="Name or room number to a space id. Ambiguity abstains with the candidates."),
        Operator("resolve_floor", (world, Param("text", "Text")), "Floor",
                 lambda world, text: adapters.resolve_floor(world.building, text),
                 (("resolved id is a floor of the building", _in(lambda a: a["world"].building.floors)),)),
        Operator("resolve_type", (world, Param("text", "Text")), "RoomType",
                 lambda world, text: adapters.resolve_room_type(world.building, text)),
        Operator("resolve_item", (world, Param("text", "Text")), "ItemType",
                 lambda world, text: adapters.resolve_item_type(world.building, text)),
        Operator("resolve_element", (world, Param("text", "Text")), "Element", _resolve_element,
                 (("resolved id is an element of the building", lambda v, a: adapters.is_element(a["world"].building, v)),),
                 doc="A lift, stair, door or space by name or id."),
        Operator("close", (world, Param("element", "Element")), "World", _close,
                 (("lineage grew by exactly one world", _lineage_grew),
                  ("the element is closed in the new world", lambda v, a: a["element"] in v.closed)),
                 doc="Graph-changing: returns G(n+1) with the element closed."),
        Operator("reopen", (world, Param("element", "Element")), "World", _reopen,
                 (("lineage grew by exactly one world", _lineage_grew),
                  ("the element is open in the new world", lambda v, a: a["element"] not in v.closed))),
        Operator("scenario", (Param("spec", "Mapping"),), "ScenarioSpec", _scenario,
                 doc="Parse a typed scenario (hazards, capacities, occupants, objective, responders, user constraints)."),
        Operator("apply_hazards", (world, spec), "World", _apply_hazards,
                 (("lineage grew by exactly one world", _lineage_grew),
                  ("every hazard in effect from the start is closed", _hazards_closed)),
                 doc="Graph-changing: hazards in effect from the start become closed elements."),
        Operator("reach", (world, Param("start", "Space"), floor, *_WALK), "Spaces",
                 lambda world, start, floor=None, step_free=False, min_width_m=None, no_stairs=False, no_lifts=False:
                 adapters.reach(world, start, floor, **_flags(step_free, min_width_m, no_stairs, no_lifts)),
                 (("every result is a space of the building", _in(lambda a: a["world"].building.spaces)),),
                 doc="Rooms reachable on foot from start, optionally on one floor."),
        Operator("route", (world, Param("start", "Space"), Param("end", "Space"), *_WALK), "Route",
                 lambda world, start, end, step_free=False, min_width_m=None, no_stairs=False, no_lifts=False:
                 adapters.route(world, start, end, **_flags(step_free, min_width_m, no_stairs, no_lifts)),
                 (("path runs from start to end", lambda v, a: v.space_path[0] == a["start"] and v.space_path[-1] == a["end"]),
                  ("no closed element on the path", lambda v, a: not (set(v.element_path) | set(v.space_path)) & a["world"].closed)),
                 doc="Shortest route under the world's closures and the walking constraints. No route abstains."),
        Operator("nearest", (world, Param("start", "Space"), Param("candidates", "Spaces"), *_WALK), "Space",
                 lambda world, start, candidates, step_free=False, min_width_m=None, no_stairs=False, no_lifts=False:
                 adapters.nearest(world, start, tuple(candidates), **_flags(step_free, min_width_m, no_stairs, no_lifts)),
                 (("result is one of the candidates", lambda v, a: v in a["candidates"]),),
                 doc="The candidate with the shortest walking distance from start (ties by id)."),
        Operator("exits", (world,), "Spaces", adapters.exits,
                 (("every exit is a space of the building", _in(lambda a: a["world"].building.spaces)),),
                 doc="Spaces with an entrance still usable in this world."),
        Operator("find", (world, Param("item", "ItemType"), floor), "Spaces",
                 lambda world, item, floor=None: adapters.spaces_with_item(world.building, item, floor)),
        Operator("spaces_of_type", (world, Param("room_type", "RoomType"), floor), "Spaces",
                 lambda world, room_type, floor=None: adapters.spaces_of_type(world.building, room_type, floor)),
        Operator("occupants", (world, Param("spec", "ScenarioSpec", False)), "Occupants", _occupants,
                 (("counts are non-negative", lambda v, a: all(c >= 0 for c in v.by_space.values())),
                  ("every counted space is a space of the building", lambda v, a: set(v.by_space) <= set(a["world"].building.spaces))),
                 doc="People per space: estimated from seats unless the scenario says otherwise."),
        Operator("count", (Param("items", "Spaces"),), "Number", lambda items: len(items)),
        Operator("area", (world, Param("spaces", "Space|Spaces")), "Number",
                 lambda world, spaces: adapters.area_m2(world.building, tuple(sorted(set(_ids(spaces))))),
                 (("area is positive", lambda v, a: v > 0),), unit="m2"),
        Operator("difference", (Param("left", "Spaces"), Param("right", "Spaces")), "Spaces",
                 lambda left, right: tuple(sorted(set(left) - set(right))),
                 (("result is inside left and disjoint from right", lambda v, a: set(v) <= set(a["left"]) and not set(v) & set(a["right"])),)),
        Operator("length", (Param("route", "Route"),), "Number", lambda route: route.length_m, unit="m"),
        Operator("add", (Param("left", "Number"), Param("right", "Number")), "Number", lambda left, right: round(left + right, 2)),
        Operator("compare", (Param("left", "Number"), Param("right", "Number")), "Comparison",
                 lambda left, right: Comparison(left, right, "less" if left < right else "greater" if left > right else "equal")),
        _placeholder("evacuate", (world, Param("occupants", "Occupants"), spec), "Evacuation"),
        _placeholder("bottleneck", (world, Param("evacuation", "Evacuation")), "Bottleneck"),
        _placeholder("responder_route", (world, spec, Param("evacuation", "Evacuation")), "Responder"),
        _placeholder("door_candidates", (world, Param("evacuation", "Evacuation"), Param("bottleneck", "Bottleneck")), "DoorCandidates"),
        _placeholder("best_door", (world, Param("candidates", "DoorCandidates"), spec, Param("evacuation", "Evacuation")), "DoorFix"),
    ])
    return registry


REGISTRY = build_registry()
