"""Multi-floor routing graph construction with dynamic constraint filtering.

Builds NetworkX MultiGraphs representing indoor connectivity across space representative
points, doors/openings, and multi-floor vertical connectors (stairs and lifts).
Supports dynamic constraint filters for door width clearances, step-free accessibility,
and dynamic closures.
"""

from __future__ import annotations

import itertools
import math
from typing import Any, Iterable, Optional, Union

import networkx as nx
from shapely.geometry import Polygon

from .models import Building, Connector, Floor, Opening, Space

OUTSIDE_NODE: str = "outside"
OUTSIDE: str = "outside"
DOOR_PREFIX: str = "door:"
STAIRS_COST_PER_FLOOR_M: float = 12.0
LIFT_WAIT_COST_M: float = 15.0
LIFT_COST_PER_FLOOR_M: float = 6.0
DEFAULT_TOLERANCE: float = 1e-6


def _extract_entities(
    building: Union[Building, dict[str, Any]]
) -> tuple[
    dict[str, Union[Floor, dict[str, Any]]],
    dict[str, Union[Space, dict[str, Any]]],
    dict[str, Union[Opening, dict[str, Any]]],
    dict[str, Union[Connector, dict[str, Any]]],
]:
    """Normalize Building dataclass or raw JSON dict into uniform accessors."""
    if isinstance(building, Building):
        return (
            building.floors,
            building.spaces,
            building.openings,
            building.connectors,
        )

    # Dictionary fallback
    floors = {str(f["id"]): f for f in building.get("floors", [])}
    spaces = {str(s["id"]): s for s in building.get("spaces", [])}
    openings = {str(o["id"]): o for o in building.get("openings", [])}
    connectors = {str(c["id"]): c for c in building.get("vertical_connectors", [])}
    return floors, spaces, openings, connectors


def build_routing_graph(
    building: Union[Building, dict[str, Any]],
    step_free: bool = False,
    min_door_width: Optional[float] = None,
    closed: Optional[Union[set[str], list[str], Iterable[str]]] = None,
) -> nx.MultiGraph:
    """Construct a MultiGraph representing navigable connectivity throughout a building.

    Nodes:
      - Space representative points: space.id
      - Door nodes: 'door:{opening_id}'
      - Exterior connection: 'outside'

    Edges:
      - Door <-> Space: Euclidean distance between representative point and door position.
      - Door <-> Outside: 0.0 weight for exterior doors.
      - Stop Space <-> Stop Space: Vertical connectors across consecutive floor stops.
        * Stairs: 12.0 * span (excluded if step_free=True).
        * Lifts: 15.0 + 6.0 * span.

    Filters:
      - Closed spaces, openings, and connectors are excluded.
      - Openings narrower than `min_door_width - 1e-6` are excluded.
      - If `step_free=True`, all stairs and non-step-free openings are excluded.

    Args:
        building: Building instance or building JSON dict.
        step_free: If True, exclude stairs and non-accessible doors.
        min_door_width: Minimum opening clearance in metres.
        closed: Set of space, opening, or connector IDs currently closed/blocked.

    Returns:
        Navigable nx.MultiGraph with Euclidean and vertical transition weights.
    """
    closed_set = set(closed) if closed else set()
    graph = nx.MultiGraph()

    floors, spaces, openings, connectors = _extract_entities(building)

    # 1. Register Space Anchors
    anchors: dict[str, tuple[float, float]] = {}
    for s_id, space in spaces.items():
        if s_id in closed_set:
            continue

        if isinstance(space, Space):
            pos = space.representative_point
            floor_id = space.floor_id
            stype = space.type
            room_type = space.room_type
            name = space.name
        else:
            poly_coords = space.get("polygon", [])
            poly = Polygon(poly_coords)
            rep = poly.representative_point()
            pos = (float(rep.x), float(rep.y))
            floor_id = str(space.get("floor_id", ""))
            stype = str(space.get("type", "room"))
            room_type = str(space.get("room_type", stype))
            name = str(space.get("name", s_id))

        anchors[s_id] = pos
        graph.add_node(
            s_id,
            pos=pos,
            floor_id=floor_id,
            type=stype,
            room_type=room_type,
            name=name,
        )

    # 2. Register Openings & Entrances
    for o_id, opening in openings.items():
        if o_id in closed_set:
            continue

        if isinstance(opening, Opening):
            is_step_free = opening.step_free
            width = opening.width_m
            pos = opening.position
            space_ids = opening.space_ids
            kind = opening.kind
            floor_id = opening.floor_id
        else:
            is_step_free = bool(opening.get("step_free", True))
            width = float(opening.get("width_m", 0.9))
            raw_pos = opening.get("position", [0.0, 0.0])
            pos = (float(raw_pos[0]), float(raw_pos[1]))
            space_ids = [str(sid) for sid in opening.get("space_ids", [])]
            kind = str(opening.get("kind", "door"))
            floor_id = str(opening.get("floor_id", ""))

        # Step-free filter: prune non-accessible openings
        if step_free and not is_step_free:
            continue

        # Door clearance filter: prune narrow openings
        if min_door_width is not None and width < (min_door_width - DEFAULT_TOLERANCE):
            continue

        door_node = f"{DOOR_PREFIX}{o_id}"
        graph.add_node(
            door_node,
            pos=pos,
            kind="door",
            opening_id=o_id,
            floor_id=floor_id,
        )

        for s_id in space_ids:
            if s_id in closed_set:
                continue

            if s_id == OUTSIDE_NODE:
                graph.add_node(OUTSIDE_NODE, kind="outside")
                graph.add_edge(
                    door_node,
                    OUTSIDE_NODE,
                    weight=0.0,
                    opening_id=o_id,
                    via=o_id,
                    kind="entrance",
                )
            elif s_id in anchors:
                anchor_pos = anchors[s_id]
                dist = math.hypot(anchor_pos[0] - pos[0], anchor_pos[1] - pos[1])
                graph.add_edge(
                    door_node,
                    s_id,
                    weight=dist,
                    opening_id=o_id,
                    via=o_id,
                    kind=kind,
                )

    # 3. Register Vertical Connectors (Stairs & Lifts)
    for c_id, connector in connectors.items():
        if c_id in closed_set:
            continue

        if isinstance(connector, Connector):
            conn_kind = connector.kind.lower()
            is_conn_step_free = connector.step_free
            c_floor_ids = connector.floor_ids
            c_space_ids = connector.space_ids
        else:
            conn_kind = str(connector.get("kind", "stairs")).lower()
            is_conn_step_free = bool(connector.get("step_free", False))
            c_floor_ids = [str(fid) for fid in connector.get("floor_ids", [])]
            c_space_ids = [str(sid) for sid in connector.get("space_ids", [])]

        is_lift = conn_kind in ("lift", "elevator")
        is_stairs = conn_kind in ("stairs", "stair")

        # Step-free constraint: EXCLUDE ALL STAIRS and non-accessible lifts
        if step_free and (is_stairs or not is_conn_step_free):
            continue

        if len(c_floor_ids) < 2 or len(c_space_ids) < 2:
            continue

        # Sort stops by floor level
        stops: list[tuple[int, str, str]] = []
        for f_id, s_id in zip(c_floor_ids, c_space_ids):
            floor_item = floors.get(f_id)
            if floor_item is not None:
                level = (
                    floor_item.level
                    if isinstance(floor_item, Floor)
                    else int(floor_item.get("level", 0))
                )
            else:
                level = 0
            stops.append((level, f_id, s_id))

        stops.sort(key=lambda item: item[0])
        normalized_kind = "lift" if is_lift else "stairs"

        for (_, f1, s1), (_, f2, s2) in itertools.pairwise(stops):
            if s1 in closed_set or s2 in closed_set:
                continue
            if s1 not in anchors or s2 not in anchors:
                continue

            floor1 = floors.get(f1)
            floor2 = floors.get(f2)
            level1 = floor1.level if isinstance(floor1, Floor) else int(floor1.get("level", 0)) if floor1 else 0
            level2 = floor2.level if isinstance(floor2, Floor) else int(floor2.get("level", 0)) if floor2 else 0
            span = abs(level1 - level2)

            if is_lift:
                cost = LIFT_WAIT_COST_M + LIFT_COST_PER_FLOOR_M * span
            else:
                cost = STAIRS_COST_PER_FLOOR_M * span

            graph.add_edge(
                s1,
                s2,
                weight=cost,
                connector_id=c_id,
                via=c_id,
                kind=normalized_kind,
                span=span,
            )

    return graph
