"""Benchmark Agent Entrypoint.

Provides the standardized `solve_question` interface compatible with
`benchmark/evaluate.py` and official evaluation runners.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Union

from spatial_engine.building_loader import load_building
from spatial_engine.models import Building
from spatial_engine.solver import solve_benchmark_question

# In-memory LRU/dict cache for parsed Building instances to avoid redundant I/O
_BUILDING_CACHE: Dict[str, Building] = {}


def get_or_load_building(building_dir: Union[str, Path]) -> Building:
    """Retrieve cached Building instance or load and cache it."""
    canonical_path = str(Path(building_dir).resolve())
    if canonical_path not in _BUILDING_CACHE:
        _BUILDING_CACHE[canonical_path] = load_building(building_dir)
    return _BUILDING_CACHE[canonical_path]


def solve_question(building_dir: Path, question: str) -> str:
    """Entry point callable for benchmark evaluation.

    Args:
        building_dir: Path to directory containing building.json.
        question: Question text.

    Returns:
        Exact formatted reply string ending with 'Answer: ...'.
    """
    building = get_or_load_building(building_dir)
    return solve_benchmark_question(building, question)
