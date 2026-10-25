"""Where the student kit lives. Override with FLOORWISE_KIT=<path to industrial-agents-hackathon-2026>."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_KIT_NAME = "industrial-agents-hackathon-2026"
_CANDIDATES = (ROOT / "docs" / _KIT_NAME, ROOT.parent / _KIT_NAME)
KIT = Path(os.environ.get("FLOORWISE_KIT") or next((c for c in _CANDIDATES if (c / "benchmark" / "score.py").is_file()), _CANDIDATES[0]))
DATA = KIT / "data"


def use_kit_modules() -> None:
    """Make the kit's official scorer (benchmark.score) importable without copying it."""
    if str(KIT) not in sys.path:
        sys.path.append(str(KIT))
