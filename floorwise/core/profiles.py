"""Named traveller profiles the organisers' rules describe, as constraints for the route engine.

Forklift: forklift aisles and openings only, openings 3 m or wider; pedestrian walkways do not count. A production
bay is a destination: a forklift can drive into one to deliver but never through one as a shortcut (the route's own
start and stops are exempt from avoid rules, so a bay at either end stays reachable)."""

from dataclasses import replace

from floorwise.core.graph import Constraints

FORKLIFT_MIN_OPENING_M = 3.0
PRODUCTION_BAY_ROOM_TYPE = "production_zone"


def forklift(base: Constraints = Constraints()) -> Constraints:
    return replace(
        base,
        min_width_m=max(base.min_width_m or 0.0, FORKLIFT_MIN_OPENING_M),
        avoid_types=base.avoid_types | {PRODUCTION_BAY_ROOM_TYPE},
    )
