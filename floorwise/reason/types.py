"""Data shapes of the reasoning engine. Everything is a frozen dataclass: a plan is data, a trace is data,
and a scenario is a typed, unit-bearing request that names no building and no number of its own.

Lineage: a World is one node G0 -> G1 -> ... of a scenario. Graph-changing operators return a new World and
never touch the Building."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from types import MappingProxyType
from typing import Any, Literal

from floorwise.core.model import Building

Ref = str  # "#<step id>" in an argument means: the output of that step. "#world" is G0.
WORLD_REF = "world"

# ---------- plan and trace ----------


@dataclass(frozen=True)
class Step:
    id: str
    op: str
    args: Mapping[str, Any] = field(default_factory=dict)  # each value: a literal or a Ref


@dataclass(frozen=True)
class Plan:
    question: str
    steps: tuple[Step, ...]
    answer: Ref


@dataclass(frozen=True)
class Abstention:
    """The engine's bottom value: which step stopped the plan, why, and what it could have meant."""

    step: str
    op: str
    reason: str
    candidates: tuple[Mapping[str, Any], ...] = ()

    def __str__(self) -> str:
        return f"abstained at step '{self.step}' ({self.op or 'plan'}): {self.reason}"


class Abstain(Exception):
    """An operator has no defensible answer. The executor stops the plan and reports the step and this reason."""

    def __init__(self, reason: str, candidates: tuple = ()) -> None:
        super().__init__(reason)
        self.reason = reason
        self.candidates = tuple(candidates)


@dataclass(frozen=True)
class StepResult:
    id: str
    op: str
    ok: bool
    value: Any
    checks: tuple[str, ...]  # postconditions that held
    reason: str | None
    summary: str  # one line
    ms: float = field(compare=False)  # wall time; excluded from equality so identical runs give identical traces


@dataclass(frozen=True)
class Trace:
    plan: Plan
    results: tuple[StepResult, ...]
    answer: Any | None
    abstained: Abstention | None


# ---------- worlds ----------


@dataclass(frozen=True)
class World:
    """A building under changes: which elements are closed and which doors were added, as a numbered lineage."""

    building_id: str
    building: Building = field(compare=False, repr=False)
    closed: frozenset[str] = frozenset()
    extra_openings: tuple[Mapping[str, Any], ...] = ()
    history: tuple[str, ...] = ()  # one entry per change; G0 has none

    @classmethod
    def of(cls, building: Building) -> "World":
        return cls(building.id, building)

    @property
    def label(self) -> str:
        return f"G{len(self.history)}"

    def derive(self, *, closed=(), extra_openings=(), change: str) -> "World":
        return World(self.building_id, self.building, self.closed | frozenset(closed),
                     self.extra_openings + tuple(extra_openings), self.history + (change,))

    def summary(self) -> str:
        return f"{self.label}: {self.history[-1]}" if self.history else "G0: the building as given"


# ---------- values that operators produce ----------


@dataclass(frozen=True)
class RouteFacts:
    length_m: float
    space_path: tuple[str, ...]
    element_path: tuple[str, ...]

    def summary(self) -> str:
        return f"{self.length_m:g} m through {len(self.space_path)} spaces"


@dataclass(frozen=True)
class Comparison:
    left: float
    right: float
    relation: Literal["less", "equal", "greater"]  # of left against right

    def summary(self) -> str:
        return f"{self.left:g} vs {self.right:g} ({self.relation})"


@dataclass(frozen=True)
class Occupants:
    by_space: Mapping[str, int]
    source: Literal["seats", "user", "uniform"]

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_space", MappingProxyType(dict(sorted(self.by_space.items()))))

    @property
    def total(self) -> int:
        return sum(self.by_space.values())

    def summary(self) -> str:
        return f"{self.total} people in {len(self.by_space)} spaces (source: {self.source})"


# ---------- the scenario ----------

CapacityKind = Literal["rate_persons_per_s", "total_persons"]
OccupantSource = Literal["seats", "user", "uniform"]
Objective = Literal["min_evacuation_time", "min_total_person_time"]
CAPACITY_KINDS = ("rate_persons_per_s", "total_persons")
OCCUPANT_SOURCES = ("seats", "user", "uniform")
OBJECTIVES = ("min_evacuation_time", "min_total_person_time")


def _positive(name: str, value: float | None) -> None:
    if value is not None and not (math.isfinite(value) and value > 0):
        raise ValueError(f"{name} must be a positive finite number, got {value!r}")


@dataclass(frozen=True)
class Hazard:
    """Spaces and/or elements (doors, stairs, lifts) that become unusable, optionally only from start_s seconds."""

    spaces: tuple[str, ...] = ()
    elements: tuple[str, ...] = ()
    start_s: float | None = None

    def __post_init__(self) -> None:
        if not self.spaces and not self.elements:
            raise ValueError("hazard needs spaces or elements")
        if self.start_s is not None and not (math.isfinite(self.start_s) and self.start_s >= 0):
            raise ValueError(f"hazard start_s must be a finite number of seconds >= 0, got {self.start_s!r}")


@dataclass(frozen=True)
class Capacity:
    """What an element can pass: a rate in persons per second, or a total number of persons."""

    element: str
    kind: CapacityKind
    value: float

    def __post_init__(self) -> None:
        if self.kind not in CAPACITY_KINDS:
            raise ValueError(f"capacity kind must be one of {CAPACITY_KINDS}, got {self.kind!r}")
        _positive("capacity value", self.value)

    @property
    def unit(self) -> str:
        return "persons/s" if self.kind == "rate_persons_per_s" else "persons"


@dataclass(frozen=True)
class OccupantSpec:
    """Where the people are: estimated from seats, given by the user, or the same count in every room.
    overrides replace the count of single spaces whatever the source."""

    source: OccupantSource
    uniform_count: int | None = None
    overrides: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        if self.source not in OCCUPANT_SOURCES:
            raise ValueError(f"occupants source must be one of {OCCUPANT_SOURCES}, got {self.source!r}")
        if self.source == "uniform" and (self.uniform_count is None or self.uniform_count < 0):
            raise ValueError("occupants source 'uniform' needs a uniform_count >= 0")
        if any(count < 0 for _, count in self.overrides):
            raise ValueError("occupants overrides must be >= 0 persons")


@dataclass(frozen=True)
class Responders:
    """Where emergency responders enter: named entrances, or let the engine choose (auto). target defaults to the hazard."""

    entrances: tuple[str, ...] = ()
    auto: bool = False
    target: str | None = None

    def __post_init__(self) -> None:
        if bool(self.entrances) == self.auto:
            raise ValueError("responders: give entrances or auto=true, not both and not neither")


@dataclass(frozen=True)
class UserConstraints:
    step_free: bool = False
    min_door_width_m: float | None = None
    avoid_lifts: bool = False
    avoid_stairs: bool = False

    def __post_init__(self) -> None:
        _positive("min_door_width_m", self.min_door_width_m)


@dataclass(frozen=True)
class ScenarioSpec:
    hazards: tuple[Hazard, ...] = ()
    capacities: tuple[Capacity, ...] = ()
    occupants: OccupantSpec | None = None
    objective: Objective | None = None
    responders: Responders | None = None
    user: UserConstraints = UserConstraints()

    def __post_init__(self) -> None:
        if self.objective is not None and self.objective not in OBJECTIVES:
            raise ValueError(f"objective must be one of {OBJECTIVES}, got {self.objective!r}")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ScenarioSpec":
        """Strict parse of the JSON form: unknown keys are errors, not silently dropped."""
        _no_unknown("scenario", raw, ScenarioSpec)
        occupants = raw.get("occupants")
        responders = raw.get("responders")
        return cls(
            hazards=tuple(_build(Hazard, h, spaces=_tuple, elements=_tuple, start_s=_float) for h in raw.get("hazards", ())),
            capacities=tuple(_build(Capacity, c, value=_float) for c in raw.get("capacities", ())),
            occupants=None if occupants is None else _build(
                OccupantSpec, occupants, overrides=_overrides),
            objective=raw.get("objective"),
            responders=None if responders is None else _build(Responders, responders, entrances=_tuple),
            user=_build(UserConstraints, raw.get("user", {}), min_door_width_m=_float),
        )


def _tuple(value) -> tuple:
    return (value,) if isinstance(value, str) else tuple(value)


def _float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"expected a number, got {value!r}")  # noqa: TRY004
    return float(value)


def _overrides(value) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, Mapping):
        raise ValueError("occupants overrides must be an object of space id -> persons")  # noqa: TRY004
    for count in value.values():
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError(f"occupants override counts must be whole persons, got {count!r}")  # noqa: TRY004
    return tuple(sorted(value.items()))


def _no_unknown(label: str, raw: Mapping[str, Any], cls: type) -> None:
    unknown = sorted(set(raw) - {f.name for f in fields(cls)})
    if unknown:
        raise ValueError(f"{label}: unknown field(s) {', '.join(unknown)}")


def _build(cls: type, raw: Mapping[str, Any], **converters):
    _no_unknown(cls.__name__.lower(), raw, cls)
    return cls(**{key: converters[key](value) if key in converters else value for key, value in raw.items()})
