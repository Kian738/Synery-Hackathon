"""Multi-floor topological navigation graph builder.

Constructs NetworkX MultiGraph instances connecting spaces, door checkpoints,
and vertical connectors with accurate spatial weights and access constraints.
"""

from __future__ import annotations

import math
from typing import Optional, Set
import networkx as nx

from .models import Building

DOOR_PREFIX = "door:"
OUTSIDE_NODE = "outside"


def build_routing_graph(
    building: Building,
    step_free: bool = False,
    min_door_width: Optional[float] = None,
    closed: Optional[Set[str]] = None,
) -> nx.MultiGraph:
    """Construct a NetworkX MultiGraph adhering to the competition indoor routing specification.

    Nodes:
      - Space anchors: space ID (coordinates at space.representative_point)
      - Door checkpoints: 'door:<opening_id>' (coordinates at opening.position)
      - Building exterior: 'outside'

    Edges:
      - Space-to-Door: Euclidean walk distance
      - Door-to-Outside: weight 0.0 (entrance)
      - Vertical Stairs: weight 12.0 * span (where span = |level2 - level1|)
      - Vertical Lift: weight 15.0 + 6.0 * span

    Constraints:
      - step_free: Excludes stairs and non-step-free doors
      - min_door_width: Excludes doors narrower than threshold
      - closed: Dynamic exclusion set containing space IDs, opening IDs, or connector IDs
    """
    closed_elements = closed or set()
    graph = nx.MultiGraph()

    # 1. Add Space Anchor Nodes
    anchors: dict[str, tuple[float, float]] = {}
    for sid, space in building.spaces.items():
        if sid not in closed_elements:
            anchors[sid] = space.representative_point
            graph.add_node(
                sid,
                pos=space.representative_point,
                type=space.type,
                room_type=space.room_type,
                floor_id=space.floor_id,
            )

    # 2. Add Openings (Doors / Entrances)
    for oid, opening in building.openings.items():
        door_node = DOOR_PREFIX + oid
        if oid in closed_elements or door_node in closed_elements:
            continue
        if step_free and not opening.step_free:
            continue
        if min_door_width is not None and opening.width_m < min_door_width - 1e-6:
            continue

        door_pos = opening.position
        graph.add_node(door_node, pos=door_pos, floor_id=opening.floor_id, kind=opening.kind)

        for sid in opening.space_ids:
            if sid in closed_elements:
                continue
            if sid == OUTSIDE_NODE:
                graph.add_edge(door_node, OUTSIDE_NODE, weight=0.0, kind="entrance")
            elif sid in anchors:
                anchor_pos = anchors[sid]
                dist = math.hypot(anchor_pos[0] - door_pos[0], anchor_pos[1] - door_pos[1])
                graph.add_edge(
                    door_node,
                    sid,
                    weight=dist,
                    opening_id=oid,
                    kind="doorway",
                    width_m=opening.width_m,
                    step_free=opening.step_free,
                )

    # 3. Add Vertical Connectors (Stairs & Lifts)
    for cid, connector in building.connectors.items():
        if cid in closed_elements:
            continue
        if step_free and not connector.step_free:
            continue

        space_ids = connector.space_ids
        floor_ids = connector.floor_ids
        if len(space_ids) < 2 or len(floor_ids) < 2:
            continue

        # Sort floor stops by integer floor level
        stops = sorted(
            zip(floor_ids, space_ids),
            key=lambda item: building.floors[item[0]].level if item[0] in building.floors else 0,
        )

        is_lift = connector.is_lift
        for (f1, s1), (f2, s2) in zip(stops[:-1], stops[1:]):
            if s1 in closed_elements or s2 in closed_elements:
                continue

            floor1 = building.floors.get(f1)
            floor2 = building.floors.get(f2)
            level1 = floor1.level if floor1 else 0
            level2 = floor2.level if floor2 else 0
            span = abs(level1 - level2)

            # Cost model: Lift has 15m wait penalty + 6m/floor; Stairs have 12m/floor
            cost = 15.0 + 6.0 * span if is_lift else 12.0 * span
            graph.add_edge(
                s1,
                s2,
                weight=cost,
                connector_id=cid,
                kind=connector.kind,
                span=span,
            )

    return graph
