"""Typed, unit-bearing inputs and JSON-serialisable results. Units are in the field names (_s, _m, _mps).

Nothing here knows a building, a room name or a scenario number: every default below is a labelled parameter.
"""

import dataclasses
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from floorwise.core.model import Building

# Assets that stand for one seated person. A row or a bench counts once: a labelled underestimate.
SEAT_TYPES = frozenset({
    "chair", "office_chair", "dining_chair", "armchair", "outdoor_chair", "sofa", "bench", "lecture_seating_row",
})
NON_OCCUPIED_SPACE_TYPES = frozenset({"stair", "lift"})


@dataclass(frozen=True)
class FlowParams:
    """Everything the physics rests on. The first three form the sweepable capacity band (1.0 to 1.6)."""

    specific_flow: float = 1.316  # persons per second per metre of effective width (SFPE, Pathfinder V&V)
    boundary_m: float = 0.15  # unusable boundary layer on each side of a door
    speed_mps: float = 1.34  # free walking speed (Weidmann)
    stairs_speed_factor: float = 0.7  # ASSUMPTION, not verified: stairs are slower than level walking
    stairs_m_per_m_climbed: float = 2.0  # path length per metre climbed (dataset route model v1.1.0 convention)
    dt_s: int = 5  # time step; every hop is rounded UP to whole steps
    max_horizon_s: int = 1800  # persons not out by then are reported as stranded
    include_lifts: bool = False  # lifts are not evacuation routes (ASR A2.3)
    lift_m_per_ride: float = 15.0  # only used when include_lifts: dataset convention, labelled assumption

    def __post_init__(self) -> None:
        if self.dt_s < 1 or self.max_horizon_s < self.dt_s:
            raise ValueError("dt_s must be >= 1 and max_horizon_s >= dt_s")
        if min(self.specific_flow, self.speed_mps, self.stairs_speed_factor, self.stairs_m_per_m_climbed) <= 0:
            raise ValueError("flow, speed and stairs factors must be positive")
        if self.boundary_m < 0:
            raise ValueError("boundary_m must be >= 0")


DEFAULT_PARAMS = FlowParams()


@dataclass(frozen=True)
class Occupants:
    """Persons per space at time 0, standing at the space's anchor point."""

    by_space: dict[str, int]
    source: Literal["seats", "user", "uniform"]
    label: str

    @staticmethod
    def explicit(by_space: Mapping[str, int], label: str = "user override") -> "Occupants":
        if any(count < 0 or int(count) != count for count in by_space.values()):
            raise ValueError("occupant counts must be non-negative integers")
        return Occupants({s: int(n) for s, n in sorted(by_space.items()) if n > 0}, "user", label)

    @staticmethod
    def from_seats(building: Building) -> "Occupants":
        """Default proxy: one person per seat-type asset in each space. No occupancy data exists in the dataset."""
        counts: dict[str, int] = {}
        for asset in building.assets.values():
            space = building.spaces.get(asset["space_id"])
            if asset["type"] in SEAT_TYPES and space and space["type"] not in NON_OCCUPIED_SPACE_TYPES:
                counts[asset["space_id"]] = counts.get(asset["space_id"], 0) + 1
        return Occupants(dict(sorted(counts.items())), "seats", "estimate: one person per seat-type asset")

    @staticmethod
    def uniform(building: Building, per_space: int, space_types: Iterable[str] = ("room",)) -> "Occupants":
        wanted = set(space_types)
        by_space = {s: per_space for s, sp in sorted(building.spaces.items()) if sp["type"] in wanted and per_space > 0}
        return Occupants(by_space, "uniform", f"assumption: {per_space} persons in every {'/'.join(sorted(wanted))}")

    @property
    def total(self) -> int:
        return sum(self.by_space.values())


@dataclass(frozen=True)
class Hazard:
    """Spaces and elements (opening or connector ids) that are impassable from from_s seconds on.
    escape_s: people already inside a hazard space may keep leaving for this many seconds after from_s (0 = none).
    It is an assumption, never a measurement; the space stays usable for everyone during that window."""

    spaces: tuple[str, ...] = ()
    elements: tuple[str, ...] = ()
    from_s: float = 0.0
    escape_s: float = 0.0


@dataclass(frozen=True)
class Capacity:
    """Explicit cap for one opening or connector. rate_persons_per_s replaces the width-derived rate;
    total_persons is the most persons that may ever pass (exact on exits only, refused elsewhere)."""

    element: str
    kind: Literal["rate_persons_per_s", "total_persons"]
    value: float

    def __post_init__(self) -> None:
        if self.kind not in ("rate_persons_per_s", "total_persons") or self.value < 0:
            raise ValueError("Capacity needs kind rate_persons_per_s or total_persons and a value >= 0")


@dataclass(frozen=True)
class Move:
    """persons leave from_space at depart_s through element and are in to_space ('outside' = exit) at arrive_s."""

    depart_s: int
    element: str
    from_space: str
    to_space: str
    persons: int
    arrive_s: int


@dataclass(frozen=True)
class Baseline:
    name: str
    T_s: int
    evacuated: int
    by_exit: dict[str, int]


@dataclass(frozen=True)
class Evacuation:
    T_s: int  # whole steps until the last evacuee is outside (0 if nobody could or needed to leave)
    total: int
    evacuated: int
    stranded: dict[str, int]  # persons not outside by max_horizon_s, per origin space
    cut_off: dict[str, int]  # subset of stranded whose space has no route at all (hazard or disconnected)
    free_flow_s: int  # same rounding as T_s but with no queueing: T_s - free_flow_s is the queueing delay
    by_exit: dict[str, int]
    schedule: tuple[Move, ...]
    bottleneck: tuple[str, ...]  # elements on the minimum cut of the last infeasible horizon (T_s - dt_s)
    time_limited: tuple[str, ...]  # occupied spaces whose walking time alone reaches T_s
    ccrp: Baseline | None
    nearest_exit: Baseline | None
    params: FlowParams
    occupants_label: str
    assumptions: tuple[str, ...]
    skipped_openings: tuple[str, ...] = field(default=())  # openings naming a space the building does not have


def to_dict(value: Any) -> Any:
    """Recursive JSON-ready view: dataclasses to dicts, mappings sorted by key, tuples to lists."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_dict(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {str(k): to_dict(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value) if isinstance(value, (set, frozenset)) else value
        return [to_dict(v) for v in items]
    return value
