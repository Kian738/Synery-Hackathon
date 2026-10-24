"""Zero-token deterministic spatial question classifier, solver, and formatter.

Directly extracts entities and parameters from natural language benchmark
questions, invokes authoritative geometric and topological routines, and
formats final answers with 100% compliance to benchmark/score.py grammar.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Union

from .building_loader import load_building
from .geometry import (
    calculate_floor_area_total,
    calculate_straight_line_3d,
    count_shared_walls,
    find_largest_room,
    find_stacked_room,
    resolve_floor,
)
from .models import Building, Space
from .router import count_reachable_rooms, evaluate_what_if_door, solve_errand


def resolve_space_in_building(
    building: Building, name_or_ref: str, floor_id: Optional[str] = None
) -> Optional[Space]:
    """Resolve space by name, ref, or ID with optional floor scoping."""
    name_clean = name_or_ref.strip()
    return building.find_space_by_ref_or_name(name_clean, floor_id=floor_id)


def solve_benchmark_question(
    building_or_path: Union[str, Path, Building], question_text: str
) -> str:
    """Classify and solve any of the 9 benchmark indoor reasoning questions.

    Args:
        building_or_path: Path to building directory, building.json, or Building object.
        question_text: Raw natural language question string.

    Returns:
        Exact formatted reply string ending with 'Answer: ...'.
    """
    building = (
        building_or_path
        if isinstance(building_or_path, Building)
        else load_building(building_or_path)
    )

    q = question_text.strip()

    # 1. Category: largest_room
    # Pattern: "Which is the largest <room_type> on the <floor>, and how big is it in m²? Finish with a line 'Answer: <room name or number>, <area> m²'."
    m_largest = re.search(
        r"Which is the largest (.+?) on the (.+?), and how big is it in m",
        q,
        flags=re.IGNORECASE,
    )
    if m_largest:
        raw_room_type = m_largest.group(1).strip()
        raw_floor = m_largest.group(2).strip()
        floor = resolve_floor(building, raw_floor)
        best_space, area = find_largest_room(building, floor, raw_room_type)
        label = best_space.name or best_space.ref or best_space.id
        return f"Answer: {label}, {area:.2f} m²"

    # 2. Category: floor_area_total
    # Pattern: "Facilities want the total floor area of every <room_type> on the <floor> added together. How many square metres is that? Finish with a line 'Answer: <number>'."
    m_area_total = re.search(
        r"total floor area of every (.+?) on the (.+?) added together",
        q,
        flags=re.IGNORECASE,
    )
    if m_area_total:
        raw_room_type = m_area_total.group(1).strip()
        raw_floor = m_area_total.group(2).strip()
        floor = resolve_floor(building, raw_floor)
        total_area = calculate_floor_area_total(building, floor, raw_room_type)
        return f"Answer: {total_area:.2f}"

    # 3. Category: wide_delivery_count
    # Pattern: "I'm moving a <width> m wide <item>. It can't go on stairs or steps (lifts are fine), and every door it passes through must be at least <width> m wide. It arrives through the entrance into <start_space> (<start_floor>). Into how many rooms on the <target_floor> can it be delivered? Finish with a line 'Answer: <number>'."
    m_wide = re.search(
        r"moving a ([\d.]+) m wide (.+?)\..+?entrance into (.+?) \((.+?)\)\. Into how many rooms on the (.+?) can it be delivered",
        q,
        flags=re.IGNORECASE,
    )
    if m_wide:
        min_width = float(m_wide.group(1))
        start_name = m_wide.group(3).strip()
        start_floor_str = m_wide.group(4).strip()
        target_floor_str = m_wide.group(5).strip()

        start_floor = resolve_floor(building, start_floor_str)
        target_floor = resolve_floor(building, target_floor_str)
        start_space = resolve_space_in_building(building, start_name, floor_id=start_floor.id)
        if not start_space:
            start_space = resolve_space_in_building(building, start_name)

        if not start_space:
            raise ValueError(f"Could not resolve start space '{start_name}'")

        count = count_reachable_rooms(
            building=building,
            start_space_id=start_space.id,
            target_floor_id=target_floor.id,
            step_free=True,
            min_width=min_width,
        )
        return f"Answer: {count}"

    # 4. Category: errand
    # Pattern: "I'm in <start_space> (<start_floor>). I need to grab a <asset_type> from the room that has one closest to me, then carry it to the largest <target_room_type> on the <target_floor>. I can carry it on the stairs. How far will I walk in total, in metres? Finish with a line 'Answer: <number>'."
    m_errand = re.search(
        r"I'm in (.+?) \((.+?)\)\. I need to grab (?:a|an)?\s*(.+?) from the room that has one closest to me, then carry it to the largest (.+?) on the (.+?)\.",
        q,
        flags=re.IGNORECASE,
    )
    if m_errand:
        start_name = m_errand.group(1).strip()
        start_floor_str = m_errand.group(2).strip()
        raw_asset_type = m_errand.group(3).strip()
        raw_target_room_type = m_errand.group(4).strip()
        target_floor_str = m_errand.group(5).strip()

        start_floor = resolve_floor(building, start_floor_str)
        target_floor = resolve_floor(building, target_floor_str)
        start_space = resolve_space_in_building(building, start_name, floor_id=start_floor.id)
        if not start_space:
            start_space = resolve_space_in_building(building, start_name)

        if not start_space:
            raise ValueError(f"Could not resolve start space '{start_name}'")

        dist, _, _ = solve_errand(
            building=building,
            start_space_id=start_space.id,
            asset_type=raw_asset_type,
            target_room_type=raw_target_room_type,
            target_floor_id=target_floor.id,
        )
        return f"Answer: {dist:.2f}"

    # 5. Category: shared_walls_count
    # Pattern: "We're soundproofing <space> (<floor>). How many other rooms on that floor share a wall with it? Count every room whose wall runs along it for at least 1 m... Finish with a line 'Answer: <number>'."
    m_shared = re.search(
        r"soundproofing (.+?) \((.+?)\)\. How many other rooms",
        q,
        flags=re.IGNORECASE,
    )
    if m_shared:
        space_name = m_shared.group(1).strip()
        floor_str = m_shared.group(2).strip()
        floor = resolve_floor(building, floor_str)
        space = resolve_space_in_building(building, space_name, floor_id=floor.id)
        if not space:
            space = resolve_space_in_building(building, space_name)

        if not space:
            raise ValueError(f"Could not resolve soundproofing space '{space_name}'")

        count = count_shared_walls(space, building)
        return f"Answer: {count}"

    # 6. Category: step_free_reachable_count
    # Pattern: "<closed_element> is out of service. A wheelchair user comes in through the entrance into <start_space> (<start_floor>). How many rooms on the <target_floor> can they still reach? Finish with a line 'Answer: <number>'."
    m_step_free = re.search(
        r"(.+?) is out of service\..+?entrance into (.+?) \((.+?)\)\. How many rooms on the (.+?) can they still reach",
        q,
        flags=re.IGNORECASE,
    )
    if m_step_free:
        closed_name = m_step_free.group(1).strip()
        start_name = m_step_free.group(2).strip()
        start_floor_str = m_step_free.group(3).strip()
        target_floor_str = m_step_free.group(4).strip()

        start_floor = resolve_floor(building, start_floor_str)
        target_floor = resolve_floor(building, target_floor_str)
        start_space = resolve_space_in_building(building, start_name, floor_id=start_floor.id)
        if not start_space:
            start_space = resolve_space_in_building(building, start_name)

        if not start_space:
            raise ValueError(f"Could not resolve start space '{start_name}'")

        # Resolve closed connector ID
        closed_id = None
        for cid, conn in building.connectors.items():
            if conn.name.lower() == closed_name.lower() or cid.lower() == closed_name.lower():
                closed_id = cid
                break

        closed_set = {closed_id} if closed_id else set()
        count = count_reachable_rooms(
            building=building,
            start_space_id=start_space.id,
            target_floor_id=target_floor.id,
            step_free=True,
            closed=closed_set,
        )
        return f"Answer: {count}"

    # 7. Category: room_stacked
    # Pattern 1 (leak below): "A washing machine is leaking onto the floor of <space> (<floor>). Which room directly below it will the water reach? Finish with a line 'Answer: <room name or number>'."
    m_leak_below = re.search(
        r"leaking onto the floor of (.+?) \((.+?)\)\. Which room directly below",
        q,
        flags=re.IGNORECASE,
    )
    if m_leak_below:
        space_name = m_leak_below.group(1).strip()
        floor_str = m_leak_below.group(2).strip()
        floor = resolve_floor(building, floor_str)
        space = resolve_space_in_building(building, space_name, floor_id=floor.id)
        if not space:
            space = resolve_space_in_building(building, space_name)

        if not space:
            raise ValueError(f"Could not resolve origin space '{space_name}'")

        stacked_space, _ = find_stacked_room(building, space, direction="below")
        label = stacked_space.name or stacked_space.ref or stacked_space.id
        return f"Answer: {label}"

    # Pattern 2 (drip above): "There's water dripping from the ceiling in <space> (<floor>). Which room is directly above it? Finish with a line 'Answer: <room name or number>'."
    m_drip_above = re.search(
        r"dripping from the ceiling in (.+?) \((.+?)\)\. Which room is directly above",
        q,
        flags=re.IGNORECASE,
    )
    if m_drip_above:
        space_name = m_drip_above.group(1).strip()
        floor_str = m_drip_above.group(2).strip()
        floor = resolve_floor(building, floor_str)
        space = resolve_space_in_building(building, space_name, floor_id=floor.id)
        if not space:
            space = resolve_space_in_building(building, space_name)

        if not space:
            raise ValueError(f"Could not resolve origin space '{space_name}'")

        stacked_space, _ = find_stacked_room(building, space, direction="above")
        label = stacked_space.name or stacked_space.ref or stacked_space.id
        return f"Answer: {label}"

    # 8. Category: straight_line_3d
    # Pattern: "We're planning a wireless sensor link between <space_a> (<floor_a>) and <space_b> (<floor_b>). What is the straight-line distance in metres between the centres of the two rooms (each room's floor-plan centroid, at its floor's elevation)? Finish with a line 'Answer: <number>'."
    m_3d = re.search(
        r"link between (.+?) \((.+?)\) and (.+?) \((.+?)\)\. What is the straight-line distance",
        q,
        flags=re.IGNORECASE,
    )
    if m_3d:
        space_a_name = m_3d.group(1).strip()
        floor_a_str = m_3d.group(2).strip()
        space_b_name = m_3d.group(3).strip()
        floor_b_str = m_3d.group(4).strip()

        floor_a = resolve_floor(building, floor_a_str)
        floor_b = resolve_floor(building, floor_b_str)

        space_a = resolve_space_in_building(building, space_a_name, floor_id=floor_a.id)
        if not space_a:
            space_a = resolve_space_in_building(building, space_a_name)

        space_b = resolve_space_in_building(building, space_b_name, floor_id=floor_b.id)
        if not space_b:
            space_b = resolve_space_in_building(building, space_b_name)

        if not space_a or not space_b:
            raise ValueError(f"Could not resolve spaces '{space_a_name}' or '{space_b_name}'")

        dist = calculate_straight_line_3d(space_a, space_b, building)
        return f"Answer: {dist:.2f}"

    # 9. Category: what_if_door
    # Pattern: "What if we add a door between <space_a> (<floor_a>) and <space_b> (<floor_b>), in the middle of the wall they share? How many rooms on the <target_floor> would then have a shorter walk out of the building, to their nearest entrance, by more than 1 m? Finish with a line 'Answer: <number>'."
    m_what_if = re.search(
        r"add a door between (.+?) \((.+?)\) and (.+?) \((.+?)\).+?How many rooms on the (.+?) would then have a shorter walk",
        q,
        flags=re.IGNORECASE,
    )
    if m_what_if:
        space_a_name = m_what_if.group(1).strip()
        floor_a_str = m_what_if.group(2).strip()
        space_b_name = m_what_if.group(3).strip()
        floor_b_str = m_what_if.group(4).strip()
        target_floor_str = m_what_if.group(5).strip()

        floor_a = resolve_floor(building, floor_a_str)
        floor_b = resolve_floor(building, floor_b_str)
        target_floor = resolve_floor(building, target_floor_str)

        space_a = resolve_space_in_building(building, space_a_name, floor_id=floor_a.id)
        if not space_a:
            space_a = resolve_space_in_building(building, space_a_name)

        space_b = resolve_space_in_building(building, space_b_name, floor_id=floor_b.id)
        if not space_b:
            space_b = resolve_space_in_building(building, space_b_name)

        if not space_a or not space_b:
            raise ValueError(f"Could not resolve spaces '{space_a_name}' or '{space_b_name}'")

        count = evaluate_what_if_door(
            building=building,
            space_a_id=space_a.id,
            space_b_id=space_b.id,
            target_floor_id=target_floor.id,
        )
        return f"Answer: {count}"

    # Fallback if pattern is unrecognized
    return f"I could not classify this question: {question_text}\nAnswer: None"
