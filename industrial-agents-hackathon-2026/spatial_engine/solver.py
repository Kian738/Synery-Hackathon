"""Deterministic benchmark solver for indoor spatial reasoning questions.

Implements zero-token-cost, high-precision deterministic solving for all 9 benchmark
question categories across industrial complexes, residential, and university buildings:
  1. largest_room
  2. floor_area_total
  3. straight_line_3d
  4. room_stacked
  5. shared_walls_count
  6. wide_delivery_count
  7. step_free_reachable_count
  8. errand
  9. what_if_door

All answers strictly conform to the format required by benchmark/score.py:
  - Formatter regex: `^\\W*answer\\W*:\\s*(.+)$`
  - For numeric answers: strictly exactly one number (`len(numbers) == 1`)
  - For largest_room: `Answer: {room_name_or_ref}, {area} m²`
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional, Union

from .building_loader import load_building
from .geometry import (
    calculate_floor_area_total,
    calculate_straight_line_3d,
    count_shared_walls,
    find_largest_room,
    find_stacked_room,
)
from .models import Building, Floor, Space
from .router import (
    count_reachable_rooms,
    evaluate_what_if_door,
    solve_errand as router_solve_errand,
)

# Global building cache to accelerate multi-question evaluation runs
_BUILDING_CACHE: dict[str, Building] = {}

# Regex patterns for question classification and entity extraction
RE_TOTAL_FLOOR_AREA = re.compile(
    r"every\s+(.+?)\s+on\s+(?:the\s+)?(.+?)\s+added\s+together", re.IGNORECASE
)
RE_LARGEST_ROOM = re.compile(
    r"largest\s+(.+?)\s+on\s+(?:the\s+)?(.+?),\s+and\s+how\s+big", re.IGNORECASE
)
RE_SHARED_WALLS = re.compile(
    r"soundproofing\s+(.+?)\s*\(((?:Ground floor|Floor\s*-?\d+|Basement\s*\d+))\)\.",
    re.IGNORECASE,
)
RE_STRAIGHT_LINE_3D = re.compile(
    r"between\s+(.+?)\s*\(((?:Ground floor|Floor\s*-?\d+|Basement\s*\d+))\)\s+and\s+(.+?)\s*\(((?:Ground floor|Floor\s*-?\d+|Basement\s*\d+))\)\.",
    re.IGNORECASE,
)
RE_ROOM_STACKED_BELOW = re.compile(
    r"floor\s+of\s+(.+?)\s*\(((?:Ground floor|Floor\s*-?\d+|Basement\s*\d+))\)\.\s+Which\s+room\s+directly\s+below",
    re.IGNORECASE,
)
RE_ROOM_STACKED_ABOVE = re.compile(
    r"ceiling\s+in\s+(.+?)\s*\(((?:Ground floor|Floor\s*-?\d+|Basement\s*\d+))\)\.\s+Which\s+room\s+is\s+directly\s+above",
    re.IGNORECASE,
)
RE_WHAT_IF_DOOR = re.compile(
    r"between\s+(.+?)\s*\((.+?)\)\s+and\s+(.+?)\s*\((.+?)\),\s+in\s+the\s+middle\s+of\s+the\s+wall\s+they\s+share\?\s+How\s+many\s+rooms\s+on\s+(?:the\s+)?(.+?)\s+would\s+then\s+have",
    re.IGNORECASE,
)
RE_STEP_FREE_LIFT = re.compile(
    r"(.+?)\s+is\s+out\s+of\s+service", re.IGNORECASE
)
RE_STEP_FREE_START = re.compile(
    r"entrance\s+into\s+(.+?)\s*\(((?:Ground floor|Floor\s*-?\d+|Basement\s*\d+))\)\.",
    re.IGNORECASE,
)
RE_STEP_FREE_TARGET = re.compile(
    r"rooms\s+on\s+(?:the\s+)?(.+?)\s+can\s+they\s+still\s+reach", re.IGNORECASE
)
RE_WIDE_DELIVERY_WIDTH = re.compile(
    r"moving\s+a\s+([\d\.]+)\s+m\s+wide", re.IGNORECASE
)
RE_WIDE_DELIVERY_START = re.compile(
    r"entrance\s+into\s+(.+?)\s*\(((?:Ground floor|Floor\s*-?\d+|Basement\s*\d+))\)\.",
    re.IGNORECASE,
)
RE_WIDE_DELIVERY_TARGET = re.compile(
    r"rooms\s+on\s+(?:the\s+)?(.+?)\s+can\s+it\s+be\s+delivered", re.IGNORECASE
)
RE_ERRAND_START = re.compile(
    r"I'm\s+in\s+(.+?)\s*\(((?:Ground floor|Floor\s*-?\d+|Basement\s*\d+))\)\.",
    re.IGNORECASE,
)
RE_ERRAND_ASSET = re.compile(
    r"grab\s+(?:a|an)\s+(.+?)\s+from\s+the\s+room", re.IGNORECASE
)
RE_ERRAND_DEST = re.compile(
    r"to\s+the\s+largest\s+(.+?)\s+on\s+(?:the\s+)?(.+?)\.\s+I\s+can\s+carry",
    re.IGNORECASE,
)


def get_cached_building(building_dir: Union[Path, str]) -> Building:
    """Load and cache building model from directory path."""
    resolved_path = str(Path(building_dir).resolve())
    if resolved_path not in _BUILDING_CACHE:
        _BUILDING_CACHE[resolved_path] = load_building(resolved_path)
    return _BUILDING_CACHE[resolved_path]


def clear_building_cache() -> None:
    """Clear memory cache of loaded buildings."""
    _BUILDING_CACHE.clear()


def parse_floor_level(fname: str) -> int:
    """Parse a floor name or level string into an integer level.

    Examples:
        'Ground floor' -> 0
        'Floor 1' -> 1
        'Floor 4' -> 4
        'Basement 1' -> -1
        'Basement 2' -> -2
        '-1' -> -1
        '2' -> 2
    """
    cleaned = fname.strip().lower()
    if "ground" in cleaned:
        return 0
    if "basement" in cleaned:
        m = re.search(r"basement\s*(\d+)", cleaned)
        return -int(m.group(1)) if m else -1
    m = re.search(r"floor\s*(-?\d+)", cleaned)
    if m:
        return int(m.group(1))
    m = re.search(r"^(-?\d+)$", cleaned)
    if m:
        return int(m.group(1))
    return 0


def resolve_space_by_text(
    building: Building, rname: str, fname: str
) -> Optional[Space]:
    """Resolve a room name and floor name from natural language text to a Space model.

    Args:
        building: Loaded Building instance.
        rname: Raw room name or reference string (e.g. 'Toilet 0.36', 'Generic room -1.14').
        fname: Floor name string (e.g. 'Ground floor', 'Floor 1', 'Basement 1').

    Returns:
        Matched Space object or None if not found.
    """
    lvl = parse_floor_level(fname)
    fl = building.floors_by_level.get(lvl)
    if not fl:
        return None

    candidates = building.spaces_by_floor.get(fl.id, [])
    rn = rname.strip().lower()

    # Remove conversational prefixes
    for prefix in ("the entrance into ", "entrance into ", "into ", "in ", "the "):
        if rn.startswith(prefix):
            rn = rn[len(prefix) :].strip()

    # 1. Exact name match
    for s in candidates:
        if s.name and s.name.lower() == rn:
            return s

    # 2. Exact ref match
    for s in candidates:
        if s.ref and s.ref.lower() == rn:
            return s

    # 3. Reference token matching (word boundary)
    words = set(re.findall(r"[A-Za-z0-9_\.\-]+", rn))
    ref_matches = [s for s in candidates if s.ref and s.ref.lower() in words]
    if len(ref_matches) == 1:
        return ref_matches[0]

    # 4. Name substring match
    name_matches = [
        s
        for s in candidates
        if s.name and (s.name.lower() in rn or rn in s.name.lower())
    ]
    if len(name_matches) == 1:
        return name_matches[0]

    if ref_matches:
        return ref_matches[0]
    if name_matches:
        return name_matches[0]

    # Fallback search across all building spaces if floor assignment differed
    all_ref_matches = [s for s in building.spaces.values() if s.ref and s.ref.lower() in words]
    if len(all_ref_matches) == 1:
        return all_ref_matches[0]

    return None


def classify_question(text: str) -> str:
    """Classify benchmark question text into one of the 9 benchmark categories.

    Args:
        text: Question text string.

    Returns:
        One of: 'largest_room', 'floor_area_total', 'straight_line_3d',
                'room_stacked', 'shared_walls_count', 'wide_delivery_count',
                'step_free_reachable_count', 'errand', 'what_if_door'.

    Raises:
        ValueError: If question text does not match any recognized category.
    """
    text_lower = text.lower()
    if "total floor area" in text_lower:
        return "floor_area_total"
    if "grab a" in text_lower or "carry it to" in text_lower:
        return "errand"
    if "share a wall with it" in text_lower or "soundproofing" in text_lower:
        return "shared_walls_count"
    if "straight-line distance" in text_lower or "wireless sensor link" in text_lower:
        return "straight_line_3d"
    if "directly below" in text_lower or "directly above" in text_lower:
        return "room_stacked"
    if "what if we add a door" in text_lower:
        return "what_if_door"
    if "out of service" in text_lower or "wheelchair user" in text_lower:
        return "step_free_reachable_count"
    if "can it be delivered" in text_lower or "delivered" in text_lower:
        return "wide_delivery_count"
    if "largest" in text_lower and (
        "how big" in text_lower or "m²" in text_lower or "<area>" in text_lower
    ):
        return "largest_room"

    raise ValueError(f"Unrecognized benchmark question format: {text[:100]}")


def _format_space_label(space: Space) -> str:
    """Format space label ensuring ref disambiguation for space scoring."""
    lbl = space.name if space.name else space.ref
    if space.ref and space.ref not in lbl:
        lbl = f"{lbl} {space.ref}"
    return lbl


def solve_largest_room(building: Building, question_text: str) -> str:
    """Solve largest_room query."""
    m = RE_LARGEST_ROOM.search(question_text)
    if not m:
        raise ValueError(f"Unable to parse largest_room query: {question_text}")
    rtype = m.group(1).strip().replace(" ", "_")
    lvl = parse_floor_level(m.group(2))
    fl = building.floors_by_level[lvl]
    space, area = find_largest_room(building, fl.id, rtype)
    lbl = _format_space_label(space)
    return f"Answer: {lbl}, {area:.1f} m²"


def solve_floor_area_total(building: Building, question_text: str) -> str:
    """Solve floor_area_total query."""
    m = RE_TOTAL_FLOOR_AREA.search(question_text)
    if not m:
        raise ValueError(f"Unable to parse floor_area_total query: {question_text}")
    rtype = m.group(1).strip().replace(" ", "_")
    lvl = parse_floor_level(m.group(2))
    fl = building.floors_by_level[lvl]
    total = calculate_floor_area_total(building, fl.id, rtype)
    return f"Answer: {total:.1f}"


def solve_errand(building: Building, question_text: str) -> str:
    """Solve errand 2-leg routing query."""
    m_start = RE_ERRAND_START.search(question_text)
    if not m_start:
        raise ValueError(f"Unable to parse start room in errand: {question_text}")
    start_space = resolve_space_by_text(building, m_start.group(1), m_start.group(2))
    if not start_space:
        raise ValueError(f"Could not resolve start space: {m_start.group(1)} on {m_start.group(2)}")

    m_asset = RE_ERRAND_ASSET.search(question_text)
    if not m_asset:
        raise ValueError(f"Unable to parse asset type in errand: {question_text}")
    asset_type = m_asset.group(1).strip().replace(" ", "_")

    m_dest = RE_ERRAND_DEST.search(question_text)
    if not m_dest:
        raise ValueError(f"Unable to parse destination in errand: {question_text}")
    target_rtype = m_dest.group(1).strip().replace(" ", "_")
    dest_lvl = parse_floor_level(m_dest.group(2))
    dest_floor = building.floors_by_level[dest_lvl]

    res = router_solve_errand(building, start_space.id, asset_type, target_rtype, dest_floor.id)
    return f"Answer: {res.total_distance:.2f}"


def solve_shared_walls_count(building: Building, question_text: str) -> str:
    """Solve shared_walls_count adjacency query."""
    m = RE_SHARED_WALLS.search(question_text)
    if not m:
        raise ValueError(f"Unable to parse space in shared_walls_count: {question_text}")
    space = resolve_space_by_text(building, m.group(1), m.group(2))
    if not space:
        raise ValueError(f"Could not resolve space: {m.group(1)} on {m.group(2)}")

    cnt = count_shared_walls(space, building)
    return f"Answer: {cnt}"


def solve_straight_line_3d(building: Building, question_text: str) -> str:
    """Solve straight_line_3d centroid distance query."""
    m = RE_STRAIGHT_LINE_3D.search(question_text)
    if not m:
        raise ValueError(f"Unable to parse spaces in straight_line_3d: {question_text}")
    s1 = resolve_space_by_text(building, m.group(1), m.group(2))
    s2 = resolve_space_by_text(building, m.group(3), m.group(4))
    if not s1 or not s2:
        raise ValueError(
            f"Could not resolve spaces for 3D distance: '{m.group(1)}' or '{m.group(3)}'"
        )

    dist = calculate_straight_line_3d(s1, s2, building)
    return f"Answer: {dist:.2f}"


def solve_room_stacked(building: Building, question_text: str) -> str:
    """Solve room_stacked vertical overlap query."""
    if "directly below" in question_text.lower():
        m = RE_ROOM_STACKED_BELOW.search(question_text)
        direction = "below"
    else:
        m = RE_ROOM_STACKED_ABOVE.search(question_text)
        direction = "above"

    if not m:
        raise ValueError(f"Unable to parse space in room_stacked: {question_text}")
    space = resolve_space_by_text(building, m.group(1), m.group(2))
    if not space:
        raise ValueError(f"Could not resolve space: {m.group(1)} on {m.group(2)}")

    stacked, _ = find_stacked_room(space, direction, building)
    lbl = _format_space_label(stacked)
    return f"Answer: {lbl}"


def solve_what_if_door(building: Building, question_text: str) -> str:
    """Solve what_if_door counterfactual simulation query."""
    m = RE_WHAT_IF_DOOR.search(question_text)
    if not m:
        raise ValueError(f"Unable to parse what_if_door query: {question_text}")
    s1 = resolve_space_by_text(building, m.group(1), m.group(2))
    s2 = resolve_space_by_text(building, m.group(3), m.group(4))
    if not s1 or not s2:
        raise ValueError(
            f"Could not resolve spaces for what_if_door: '{m.group(1)}' or '{m.group(3)}'"
        )

    target_lvl = parse_floor_level(m.group(5))
    target_floor = building.floors_by_level[target_lvl]
    cnt = evaluate_what_if_door(building, s1.id, s2.id, target_floor.id)
    return f"Answer: {cnt}"


def solve_step_free_reachable_count(building: Building, question_text: str) -> str:
    """Solve step_free_reachable_count query."""
    m_lift = RE_STEP_FREE_LIFT.search(question_text)
    if not m_lift:
        raise ValueError(f"Unable to parse closed lift: {question_text}")
    lift_name = m_lift.group(1).strip()
    matched = [c for c in building.connectors.values() if c.name.lower() == lift_name.lower()]
    if not matched:
        raise ValueError(f"Connector '{lift_name}' not found in building {building.id}")
    closed_id = matched[0].id

    m_room = RE_STEP_FREE_START.search(question_text)
    if not m_room:
        raise ValueError(f"Unable to parse start space: {question_text}")
    space = resolve_space_by_text(building, m_room.group(1), m_room.group(2))
    if not space:
        raise ValueError(f"Could not resolve space: {m_room.group(1)} on {m_room.group(2)}")

    m_target = RE_STEP_FREE_TARGET.search(question_text)
    if not m_target:
        raise ValueError(f"Unable to parse target floor: {question_text}")
    target_lvl = parse_floor_level(m_target.group(1))
    target_floor = building.floors_by_level[target_lvl]

    cnt = count_reachable_rooms(
        building, space.id, target_floor.id, step_free=True, min_width=None, closed={closed_id}
    )
    return f"Answer: {cnt}"


def solve_wide_delivery_count(building: Building, question_text: str) -> str:
    """Solve wide_delivery_count clearance query."""
    m_width = RE_WIDE_DELIVERY_WIDTH.search(question_text)
    if not m_width:
        raise ValueError(f"Unable to parse door width clearance: {question_text}")
    width = float(m_width.group(1))

    m_room = RE_WIDE_DELIVERY_START.search(question_text)
    if not m_room:
        raise ValueError(f"Unable to parse entrance start space: {question_text}")
    space = resolve_space_by_text(building, m_room.group(1), m_room.group(2))
    if not space:
        raise ValueError(f"Could not resolve space: {m_room.group(1)} on {m_room.group(2)}")

    m_target = RE_WIDE_DELIVERY_TARGET.search(question_text)
    if not m_target:
        raise ValueError(f"Unable to parse target floor: {question_text}")
    target_lvl = parse_floor_level(m_target.group(1))
    target_floor = building.floors_by_level[target_lvl]

    cnt = count_reachable_rooms(
        building, space.id, target_floor.id, step_free=True, min_width=width
    )
    return f"Answer: {cnt}"


def answer(building_dir: Union[Path, str], question_text: str) -> str:
    """Deterministic solver entrypoint conforming to benchmark evaluation interface.

    Args:
        building_dir: Directory containing building.json and related assets.
        question_text: Raw natural language benchmark question text.

    Returns:
        Formatted string ending with the committed 'Answer: ...' line.
    """
    building = get_cached_building(building_dir)
    kind = classify_question(question_text)

    if kind == "largest_room":
        return solve_largest_room(building, question_text)
    elif kind == "floor_area_total":
        return solve_floor_area_total(building, question_text)
    elif kind == "errand":
        return solve_errand(building, question_text)
    elif kind == "shared_walls_count":
        return solve_shared_walls_count(building, question_text)
    elif kind == "straight_line_3d":
        return solve_straight_line_3d(building, question_text)
    elif kind == "room_stacked":
        return solve_room_stacked(building, question_text)
    elif kind == "what_if_door":
        return solve_what_if_door(building, question_text)
    elif kind == "step_free_reachable_count":
        return solve_step_free_reachable_count(building, question_text)
    elif kind == "wide_delivery_count":
        return solve_wide_delivery_count(building, question_text)

    raise ValueError(f"Unhandled question kind: {kind}")


def solve_question(building_dir: Union[Path, str], question_text: str) -> str:
    """Alias to answer() conforming to PROJECT.md interface contract."""
    return answer(building_dir, question_text)


def evaluate_dataset(
    dataset_dir: Union[Path, str], kinds: Optional[list[str]] = None
) -> dict[str, float]:
    """Run deterministic evaluation over a dataset split and compute accuracy metrics.

    Args:
        dataset_dir: Directory containing building subdirectories (e.g. data/dev).
        kinds: Optional list of question kinds to filter by.

    Returns:
        Dictionary mapping category names (and 'all') to accuracy percentages (0.0 to 1.0).
    """
    from benchmark.score import score_reply

    dataset_path = Path(dataset_dir)
    results: dict[str, list[int]] = {}  # kind -> [correct, total]

    question_files = sorted(dataset_path.glob("*/questions.jsonl"))
    for qfile in question_files:
        bdir = qfile.parent
        with qfile.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                q = json.loads(line)
                kind = q.get("kind", "")
                if kinds and kind not in kinds:
                    continue

                reply = answer(bdir, q["question"])
                is_correct = score_reply(q["answer"], reply)

                results.setdefault(kind, [0, 0])
                results[kind][1] += 1
                if is_correct:
                    results[kind][0] += 1

    accuracies: dict[str, float] = {}
    total_correct = 0
    total_questions = 0

    for kind, (c, t) in sorted(results.items()):
        accuracies[kind] = c / t if t > 0 else 0.0
        total_correct += c
        total_questions += t

    accuracies["all"] = total_correct / total_questions if total_questions > 0 else 0.0
    return accuracies
