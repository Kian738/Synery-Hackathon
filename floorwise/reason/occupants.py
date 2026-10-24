"""Who is in the building. The dataset has no occupancy field, so the default is an estimate from seats.

ASSUMPTIONS (labelled, adjustable, never presented as measurements):
- one person per seat for the chair-like asset types below;
- a seating row seats floor(width / SEAT_PITCH_M) people, with a seat pitch of 0.5 m;
- outdoor spaces hold nobody to evacuate."""

import math
from collections import Counter

from floorwise.core.model import Building
from floorwise.reason.types import Occupants, OccupantSpec

SEAT_TYPES = frozenset({"chair", "office_chair", "dining_chair", "armchair", "bench"})
SEAT_ROW_TYPE = "lecture_seating_row"
SEAT_PITCH_M = 0.5


def seat_counts(building: Building) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for asset in building.assets.values():
        space = building.spaces.get(asset["space_id"])
        if space is None or space["type"] == "outdoor":
            continue
        if asset["type"] in SEAT_TYPES:
            counts[space["id"]] += 1
        elif asset["type"] == SEAT_ROW_TYPE:
            counts[space["id"]] += math.floor(asset["footprint"]["width_m"] / SEAT_PITCH_M + 1e-9)
    return {space_id: count for space_id, count in counts.items() if count}


def has_seat_data(building: Building) -> bool:
    return bool(seat_counts(building))


def build(building: Building, spec: OccupantSpec | None) -> Occupants:
    """Raises ValueError when the spec cannot be turned into counts (the operator turns that into an abstention)."""
    spec = spec or OccupantSpec(source="seats")
    unknown = [space_id for space_id, _ in spec.overrides if space_id not in building.spaces]
    if unknown:
        raise ValueError(f"occupant override names unknown space(s): {', '.join(unknown)}")
    if spec.source == "seats":
        counts = seat_counts(building)
        if not counts and not spec.overrides:
            raise ValueError("this building has no seat data to estimate occupants from; give counts per space or a uniform count")
    elif spec.source == "uniform":
        counts = {s["id"]: spec.uniform_count for s in building.spaces.values() if s["type"] == "room"}
    else:
        counts = {}
        if not spec.overrides:
            raise ValueError("occupants source 'user' needs counts per space")
    counts.update(dict(spec.overrides))
    return Occupants({space_id: count for space_id, count in counts.items() if count}, spec.source)
