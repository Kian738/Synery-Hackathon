"""Geometric vector cross-product landmark guidance and ambiguity resolution.

Provides human-friendly landmark-referenced turn-by-turn navigation instructions
using vector cross-products (v x u) to determine relative orientation (left/right)
of machinery, equipment, and rooms along path segments, as well as conversational
ambiguity clarification for voice interaction.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Optional

from shapely.geometry import LineString, Point

from .graph import DOOR_PREFIX, OUTSIDE_NODE
from .models import Asset, Building, Space


@dataclass
class LandmarkObservation:
    """An asset or architectural feature observed along a path segment."""

    asset: Asset
    side: str  # 'left', 'right', or 'ahead'
    distance_to_path_m: float
    cross_product: float
    salience_score: float


def compute_path_waypoints(
    building: Building, path_nodes: list[str]
) -> list[list[float]]:
    """Convert a sequence of topological graph node IDs into 3D waypoints [x, y, z].

    z corresponds to the floor's elevation_m.
    """
    waypoints: list[list[float]] = []
    for node in path_nodes:
        if node == OUTSIDE_NODE:
            # Anchor outside node slightly offset from last doorway or [0, 0, 0]
            if waypoints:
                last_wp = waypoints[-1]
                waypoints.append([last_wp[0] + 2.0, last_wp[1] + 2.0, last_wp[2]])
            else:
                waypoints.append([0.0, 0.0, 0.0])
        elif node.startswith(DOOR_PREFIX):
            oid = node[len(DOOR_PREFIX) :]
            opening = building.openings.get(oid)
            if opening:
                floor = building.floors.get(opening.floor_id)
                elev = floor.elevation_m if floor else 0.0
                waypoints.append([round(opening.position[0], 3), round(opening.position[1], 3), elev])
        else:
            space = building.spaces.get(node)
            if space:
                floor = building.floors.get(space.floor_id)
                elev = floor.elevation_m if floor else 0.0
                pos = space.representative_point
                waypoints.append([round(pos[0], 3), round(pos[1], 3), elev])

    return waypoints


def calculate_segment_landmarks(
    building: Building,
    p1: list[float],
    p2: list[float],
    floor_id: Optional[str] = None,
    buffer_distance_m: float = 5.0,
) -> list[LandmarkObservation]:
    """Find and rank physical assets adjacent to a 2D line segment using vector cross-product.

    Vector math:
      v = (p2.x - p1.x, p2.y - p1.y)  [motion vector]
      u = (asset.x - p1.x, asset.y - p1.y) [vector to asset]
      cross = v.x * u.y - v.y * u.x
      If cross > 0: asset is on the LEFT of the moving user.
      If cross < 0: asset is on the RIGHT of the moving user.
    """
    vx = p2[0] - p1[0]
    vy = p2[1] - p1[1]
    seg_len = math.hypot(vx, vy)
    if seg_len < 0.1:
        return []

    line = LineString([(p1[0], p1[1]), (p2[0], p2[1])])

    # Candidate assets on this floor
    if floor_id:
        candidate_assets = [a for a in building.assets.values() if a.floor_id == floor_id]
    else:
        # Match floor by elevation if available
        elev = p1[2] if len(p1) > 2 else 0.0
        matching_floors = [f.id for f in building.floors.values() if abs(f.elevation_m - elev) < 0.5]
        if matching_floors:
            candidate_assets = [a for a in building.assets.values() if a.floor_id in matching_floors]
        else:
            candidate_assets = list(building.assets.values())

    observations: list[LandmarkObservation] = []

    for asset in candidate_assets:
        pt = Point(asset.position[0], asset.position[1])
        dist = float(line.distance(pt))
        if dist > buffer_distance_m:
            continue

        # Project point onto segment to ensure it is along the path (not behind or beyond)
        proj_dist = line.project(pt)
        if proj_dist < -1.0 or proj_dist > seg_len + 1.0:
            continue

        ux = asset.position[0] - p1[0]
        uy = asset.position[1] - p1[1]
        cross = vx * uy - vy * ux

        if cross > 0.15:
            side = "left"
        elif cross < -0.15:
            side = "right"
        else:
            side = "ahead"

        # Salience scoring: industrial machinery > equipment > fixtures > furniture
        cat = (asset.category or "").lower()
        if "machine" in cat or "cnc" in cat or "mill" in cat or "lathe" in cat or "press" in cat:
            base_salience = 12.0
        elif "equipment" in cat or "robot" in cat or "conveyor" in cat or "cabinet" in cat:
            base_salience = 8.0
        elif "storage" in cat or "rack" in cat or "shelf" in cat:
            base_salience = 5.0
        else:
            base_salience = 3.0

        # Closer landmarks get higher priority
        score = base_salience / (1.0 + dist)

        observations.append(
            LandmarkObservation(
                asset=asset,
                side=side,
                distance_to_path_m=dist,
                cross_product=cross,
                salience_score=score,
            )
        )

    observations.sort(key=lambda obs: obs.salience_score, reverse=True)
    return observations


def generate_landmark_instructions(
    building: Building,
    path_nodes: list[str],
    waypoints: Optional[list[list[float]]] = None,
) -> list[str]:
    """Generate human-friendly, landmark-referenced navigation instructions.

    Combines:
    - Starting location name
    - Passage through specific doorway checkpoints and room transitions
    - Vector cross-product asset observations ("turn right after CNC mill H-A1-A")
    - Elevator and stair vertical transitions
    - Final arrival confirmation
    """
    if not path_nodes:
        return ["No navigation path available."]

    if waypoints is None or len(waypoints) != len(path_nodes):
        waypoints = compute_path_waypoints(building, path_nodes)

    instructions: list[str] = []

    # 1. Starting anchor instruction
    first_node = path_nodes[0]
    first_space = building.spaces.get(first_node)
    start_floor_name = ""
    if first_space:
        floor = building.floors.get(first_space.floor_id)
        if floor:
            start_floor_name = f" on {floor.name}"
        instructions.append(f"Start in {first_space.name}{start_floor_name}.")
    else:
        instructions.append("Begin navigation from your current position.")

    # 2. Iterate through path steps
    i = 0
    while i < len(path_nodes) - 1:
        curr_node = path_nodes[i]
        next_node = path_nodes[i + 1]
        p1 = waypoints[i]
        p2 = waypoints[i + 1]

        # Case A: Connector transition (Floor change)
        curr_space = building.spaces.get(curr_node)
        next_space = building.spaces.get(next_node)
        if curr_space and next_space and curr_space.floor_id != next_space.floor_id:
            curr_floor = building.floors.get(curr_space.floor_id)
            next_floor = building.floors.get(next_space.floor_id)
            target_floor_name = next_floor.name if next_floor else next_space.floor_id

            # Find which vertical connector links these spaces
            connector_name = "stairs or elevator"
            for conn in building.connectors.values():
                if curr_space.id in conn.space_ids and next_space.id in conn.space_ids:
                    kind_desc = "elevator" if conn.is_lift else "staircase"
                    connector_name = f"{conn.name or kind_desc}"
                    break

            instructions.append(f"Take {connector_name} to {target_floor_name}.")
            i += 1
            continue

        # Case B: Doorway crossing (Space -> Door -> Space)
        if next_node.startswith(DOOR_PREFIX):
            oid = next_node[len(DOOR_PREFIX) :]
            opening = building.openings.get(oid)
            dest_space = None
            if i + 2 < len(path_nodes) and not path_nodes[i + 2].startswith(DOOR_PREFIX):
                dest_space = building.spaces.get(path_nodes[i + 2])

            door_desc = ""
            if opening:
                door_desc = f"door {opening.id}"
                if opening.is_entrance:
                    door_desc = "the building entrance"

            # Check for landmarks along the walk to the door
            floor_id = curr_space.floor_id if curr_space else None
            landmarks = calculate_segment_landmarks(building, p1, p2, floor_id=floor_id)

            walk_dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            step_text = ""
            if landmarks:
                top_lm = landmarks[0]
                side_str = f"on your {top_lm.side}" if top_lm.side in ("left", "right") else "ahead"
                if walk_dist > 8.0:
                    step_text = (
                        f"Walk {walk_dist:.0f} m toward {door_desc}, passing {top_lm.asset.name} {side_str}."
                    )
                else:
                    step_text = f"Proceed past {top_lm.asset.name} ({side_str}) and pass through {door_desc}."
            else:
                if walk_dist > 2.0:
                    step_text = f"Walk {walk_dist:.0f} m toward and pass through {door_desc}."
                else:
                    step_text = f"Pass through {door_desc}."

            if dest_space:
                step_text = step_text.rstrip(".") + f" into {dest_space.name}."
                i += 2  # Skip past the door node and destination space
            else:
                step_text = step_text.rstrip(".") + "."
                i += 1

            instructions.append(step_text)
            continue

        # Case C: Corridor or hall walk within space or between spaces
        floor_id = curr_space.floor_id if curr_space else None
        landmarks = calculate_segment_landmarks(building, p1, p2, floor_id=floor_id)
        seg_dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])

        if seg_dist > 1.5:
            if landmarks:
                top_lm = landmarks[0]
                side_str = f"on your {top_lm.side}" if top_lm.side in ("left", "right") else "directly ahead"
                instructions.append(
                    f"Continue {seg_dist:.0f} m past {top_lm.asset.name} {side_str}."
                )
            else:
                instructions.append(f"Continue {seg_dist:.0f} m straight ahead.")

        i += 1

    # 3. Final arrival instruction
    last_node = path_nodes[-1]
    if last_node == OUTSIDE_NODE:
        instructions.append("You have exited the building to the outside.")
    else:
        last_space = building.spaces.get(last_node)
        if last_space:
            instructions.append(f"You have arrived at your destination: {last_space.name}.")
        else:
            instructions.append("You have reached your destination.")

    return instructions


# ---------------------------------------------------------------------------
# Ambiguity Clarification State Machine
# ---------------------------------------------------------------------------


def clarify_query(raw_query: str, building: Building) -> dict[str, Any]:
    """Inspect a user navigation query and resolve entities or return clarification options.

    Handles:
    - Specific room/machine targets: "CNC mill 0.21", "Server room 1.05"
    - Ambiguous multi-match queries: "milling machine", "restroom", "office"
    - Vehicle constraint extraction: "with forklift", "step-free"
    """
    clean_text = raw_query.lower().strip()

    # Detect constraints
    step_free = bool(
        re.search(r"\b(wheelchair|step[\s-]free|no stairs|trolley|cart|pram)\b", clean_text)
    )
    is_forklift = bool(re.search(r"\b(forklift|pallet|reach truck)\b", clean_text))
    min_width = 1.5 if is_forklift else (1.2 if "pallet" in clean_text else 0.0)

    # Strip navigation trigger phrases
    stripped = re.sub(
        r"^(?:take me to|navigate to|how do i get to|where is|go to|route to|find|locate)\s+",
        "",
        clean_text,
    )
    # Strip trailing constraint phrases
    stripped = re.sub(
        r"\s+(?:with\s+(?:a\s+)?(?:forklift|pallet|cart)|step[\s-]free|no stairs).*",
        "",
        stripped,
    ).strip()

    if not stripped:
        return {
            "ambiguous": False,
            "target": None,
            "prompt": "Please specify a room, machine, or landmark destination.",
            "step_free": step_free,
            "min_width": min_width,
            "candidates": [],
        }

    # 1. Search in Assets
    matched_assets: list[Asset] = []
    norm_term = stripped.replace(" ", "_")

    for asset in building.assets.values():
        name_lower = asset.name.lower()
        type_lower = asset.type.lower()
        cat_lower = asset.category.lower()
        aid_lower = asset.id.lower()

        if (
            stripped == name_lower
            or stripped == aid_lower
            or norm_term == type_lower
            or stripped in name_lower
            or norm_term in type_lower
            or (stripped in cat_lower and len(stripped) > 3)
        ):
            matched_assets.append(asset)

    # 2. Search in Spaces
    matched_spaces: list[Space] = []
    for space in building.spaces.values():
        name_lower = space.name.lower()
        ref_lower = (space.ref or "").lower()
        type_lower = space.room_type.lower()
        sid_lower = space.id.lower()

        if (
            stripped == sid_lower
            or (ref_lower and stripped == ref_lower)
            or stripped == name_lower
            or norm_term == type_lower
            or stripped in name_lower
            or (ref_lower and stripped in ref_lower)
            or (norm_term in type_lower and len(stripped) > 3)
        ):
            matched_spaces.append(space)

    total_matches = len(matched_assets) + len(matched_spaces)

    # Case 1: Exact unique match
    if total_matches == 1:
        if matched_assets:
            target_asset = matched_assets[0]
            space = building.spaces.get(target_asset.space_id)
            space_name = space.name if space else target_asset.space_id
            return {
                "ambiguous": False,
                "target_type": "asset",
                "target_id": target_asset.id,
                "target_space_id": target_asset.space_id,
                "target_name": target_asset.name,
                "prompt": f"Setting route to {target_asset.name} in {space_name}.",
                "step_free": step_free,
                "min_width": min_width,
                "candidates": [],
            }
        else:
            target_space = matched_spaces[0]
            return {
                "ambiguous": False,
                "target_type": "space",
                "target_id": target_space.id,
                "target_space_id": target_space.id,
                "target_name": target_space.name,
                "prompt": f"Setting route to {target_space.name}.",
                "step_free": step_free,
                "min_width": min_width,
                "candidates": [],
            }

    # Case 2: Ambiguous multiple matches
    if total_matches > 1:
        candidates: list[dict[str, Any]] = []
        labels: list[str] = []

        for asset in matched_assets[:5]:
            space = building.spaces.get(asset.space_id)
            loc_str = space.name if space else asset.space_id
            desc = f"{asset.name} ({loc_str})"
            candidates.append(
                {
                    "type": "asset",
                    "id": asset.id,
                    "space_id": asset.space_id,
                    "name": asset.name,
                    "description": desc,
                }
            )
            labels.append(desc)

        for space in matched_spaces[: 5 - len(candidates)]:
            floor = building.floors.get(space.floor_id)
            floor_name = floor.name if floor else space.floor_id
            desc = f"{space.name} ({floor_name})"
            candidates.append(
                {
                    "type": "space",
                    "id": space.id,
                    "space_id": space.id,
                    "name": space.name,
                    "description": desc,
                }
            )
            labels.append(desc)

        options_text = "; ".join(f"'{lbl}'" for lbl in labels)
        clarification_prompt = (
            f"I found {total_matches} potential destinations for '{stripped}': "
            f"{options_text}. Which one would you like to navigate to?"
        )

        return {
            "ambiguous": True,
            "count": total_matches,
            "target": None,
            "prompt": clarification_prompt,
            "candidates": candidates,
            "step_free": step_free,
            "min_width": min_width,
        }

    # Case 3: No matches found
    return {
        "ambiguous": False,
        "target": None,
        "prompt": f"Sorry, I couldn't locate any room or machine matching '{stripped}'.",
        "step_free": step_free,
        "min_width": min_width,
        "candidates": [],
    }


def resolve_clarification(
    user_choice: str, candidates: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """Resolve user selection from a previous ambiguity clarification prompt.

    Supports ordinals ("first", "second", "1", "2") or name matching.
    """
    choice = user_choice.lower().strip()
    ordinal_map = {
        "1": 0,
        "first": 0,
        "1st": 0,
        "one": 0,
        "2": 1,
        "second": 1,
        "2nd": 1,
        "two": 1,
        "3": 2,
        "third": 2,
        "3rd": 2,
        "three": 2,
        "4": 3,
        "fourth": 3,
        "4th": 3,
        "four": 3,
        "5": 4,
        "fifth": 4,
        "5th": 4,
        "five": 4,
    }

    # Ordinal match
    for key, idx in ordinal_map.items():
        if choice == key or choice.startswith(f"the {key}") or choice.startswith(f"option {key}"):
            if 0 <= idx < len(candidates):
                return candidates[idx]

    # Name or ID match
    for cand in candidates:
        cand_name = cand.get("name", "").lower()
        cand_id = cand.get("id", "").lower()
        if choice in cand_name or cand_name in choice or choice == cand_id:
            return cand

    return None
