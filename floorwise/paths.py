"""Where the student kit lives. Override with FLOORWISE_KIT=<path to industrial-agents-hackathon-2026>."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIT = Path(os.environ.get("FLOORWISE_KIT", ROOT / "docs" / "industrial-agents-hackathon-2026"))
DATA = KIT / "data"


def use_kit_modules() -> None:
    """Make the kit's official scorer (benchmark.score) importable without copying it."""
    if str(KIT) not in sys.path:
        sys.path.append(str(KIT))
