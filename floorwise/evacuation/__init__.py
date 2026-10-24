"""Evacuation: exact flows over time on a capacity graph of the building.

    evacuate(building, occupants, hazard, capacities, params) -> Evacuation
    with_responders(building, occupants, hazard, capacities, params, responders=...) -> ResponderPlan
    best_doors(building, occupants, hazard, capacities, params) -> DoorPlan

All inputs are typed and carry units; every result is a frozen dataclass that `to_dict` turns into JSON.
"""

from floorwise.evacuation.doors import DoorFix, DoorPlan, best_doors
from floorwise.evacuation.responders import (
    Reservation,
    ResponderPlan,
    Responders,
    RouteCandidate,
    with_responders,
)
from floorwise.evacuation.solve import evacuate
from floorwise.evacuation.types import (
    Baseline,
    Capacity,
    Evacuation,
    FlowParams,
    Hazard,
    Move,
    Occupants,
    to_dict,
)

__all__ = [
    "Baseline", "Capacity", "DoorFix", "DoorPlan", "Evacuation", "FlowParams", "Hazard", "Move", "Occupants", "Reservation",
    "ResponderPlan", "Responders", "RouteCandidate", "best_doors", "evacuate", "to_dict", "with_responders",
]
