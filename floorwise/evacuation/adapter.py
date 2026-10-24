"""The ONE module that reads a Building. Everything else works on the CapacityGraph it returns, so the
evacuation solver does not depend on the route cost model in floorwise.core.graph / routing.

Space = node at its anchor (representative point). Opening = arc between two spaces through its position.
Connector = arc between consecutive stops. Entrances (an opening touching 'outside') are the exits.
"""

import itertools
import math
from dataclasses import dataclass, replace

from shapely.geometry import Polygon

from floorwise.core.model import OUTSIDE, Building
from floorwise.evacuation.types import FlowParams


@dataclass(frozen=True)
class Element:
    """An undirected passage. For exits b == OUTSIDE and leg_b_m == 0."""

    id: str
    kind: str  # door | opening | entrance | stairs | lift
    a: str
    b: str
    width_m: float | None  # None: not width-limited (connectors); capped only by an explicit Capacity
    leg_a_m: float  # anchor of a to the crossing point (0 for connectors)
    leg_b_m: float
    length_m: float  # whole walking length a -> b
    speed_factor: float
    position: tuple[float, float] | None
    floor_id: str | None
    step_free: bool

    @property
    def is_exit(self) -> bool:
        return self.b == OUTSIDE

    @property
    def family(self) -> str:
        """Hazards and capacities name a connector, not each stop-to-stop piece of it."""
        return self.id.split("#")[0]


@dataclass(frozen=True)
class CapacityGraph:
    spaces: tuple[str, ...]  # sorted ids, never OUTSIDE
    anchors: dict[str, tuple[float, float]]
    elements: tuple[Element, ...]  # sorted by id
    skipped: tuple[str, ...]  # openings naming an unknown space

    def element(self, element_id: str) -> Element:
        for candidate in self.elements:
            if candidate.id == element_id:
                return candidate
        raise KeyError(element_id)

    def has_element(self, element_id: str) -> bool:
        return any(candidate.id == element_id for candidate in self.elements)

    def with_element(self, new: Element) -> "CapacityGraph":
        return replace(self, elements=tuple(sorted((*self.elements, new), key=lambda e: e.id)))

    def with_width(self, element_id: str, width_m: float) -> "CapacityGraph":
        return replace(self, elements=tuple(
            replace(e, width_m=width_m) if e.id == element_id else e for e in self.elements))

    @property
    def exits(self) -> tuple[Element, ...]:
        return tuple(e for e in self.elements if e.is_exit)


def door_element(opening: dict, anchors: dict[str, tuple[float, float]]) -> Element | None:
    """An opening dict (dataset shape) as an Element, or None if it names a space we do not have."""
    first, second = opening["space_ids"]
    if first == OUTSIDE:
        first, second = second, first
    position = (float(opening["position"][0]), float(opening["position"][1]))
    if first not in anchors or (second != OUTSIDE and second not in anchors) or first == second:
        return None
    leg_a = math.dist(anchors[first], position)
    leg_b = 0.0 if second == OUTSIDE else math.dist(anchors[second], position)
    kind = "entrance" if second == OUTSIDE else opening["kind"]
    return Element(opening["id"], kind, first, second, float(opening["width_m"]), leg_a, leg_b, leg_a + leg_b, 1.0,
                   position, opening.get("floor_id"), bool(opening.get("step_free", True)))


def build_graph(building: Building, params: FlowParams) -> CapacityGraph:
    anchors = {}
    for space_id in sorted(building.spaces):
        point = Polygon(building.spaces[space_id]["polygon"]).representative_point()
        anchors[space_id] = (point.x, point.y)
    elements: list[Element] = []
    skipped: list[str] = []
    for opening_id in sorted(building.openings):
        element = door_element(building.openings[opening_id], anchors)
        if element is None:
            skipped.append(opening_id)
        else:
            elements.append(element)
    for connector_id in sorted(building.connectors):
        connector = building.connectors[connector_id]
        is_lift = connector["kind"] == "lift"
        if is_lift and not params.include_lifts:
            continue
        stops = sorted(zip(connector["floor_ids"], connector["space_ids"], strict=True),
                       key=lambda stop: building.level(stop[0]))
        for index, ((low_floor, low), (high_floor, high)) in enumerate(itertools.pairwise(stops)):
            if low not in anchors or high not in anchors:
                continue
            rise = abs(building.elevation(high_floor) - building.elevation(low_floor))
            run = math.dist(anchors[low], anchors[high])
            if is_lift:
                length, factor = params.lift_m_per_ride + rise, 1.0
            else:
                length, factor = max(params.stairs_m_per_m_climbed * rise, run), params.stairs_speed_factor
            element_id = connector_id if len(stops) == 2 else f"{connector_id}#{index}"
            elements.append(Element(element_id, connector["kind"], low, high, None, 0.0, 0.0, length, factor, None,
                                    None, bool(connector.get("step_free", True))))
    return CapacityGraph(tuple(sorted(building.spaces)), anchors, tuple(sorted(elements, key=lambda e: e.id)),
                         tuple(skipped))
