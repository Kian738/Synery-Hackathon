"""Real dev buildings for the reason tests. Building ids live here, never in floorwise/."""

from collections import Counter
from dataclasses import fields

from floorwise.core.graph import Constraints
from floorwise.core.model import OUTSIDE, Building
from floorwise.paths import DATA

FACTORY_DIR = DATA / "dev" / "proc-factory-dev-003"
CAMPUS_DIR = DATA / "dev" / "proc-campus-dev-000"
HOUSE_DIR = DATA / "dev" / "resplan-14509"


def people(**kwargs) -> Constraints:
    """How the engine asks the core about walking people: indoors only, whatever the route model calls that."""
    if "outside" in {f.name for f in fields(Constraints)}:
        kwargs["outside"] = "none"
    return Constraints(**kwargs)


def ground_exit_space(building: Building) -> str:
    return min({s for o in building.openings.values() if OUTSIDE in o["space_ids"] for s in o["space_ids"] if s != OUTSIDE})


def connector(building: Building, kind: str) -> str:
    return next(c["id"] for c in building.connectors.values() if c["kind"] == kind)


def duplicated_name() -> tuple[Building, str, int]:
    """First dev building that has a space name used more than once on one floor."""
    for directory in sorted((DATA / "dev").iterdir()):
        building = Building.load(directory)
        for floor_id in building.floors:
            names = Counter(s["name"] for s in building.spaces_on(floor_id))
            for name, count in sorted(names.items()):
                if count > 1:
                    return building, name, sum(1 for s in building.spaces.values() if s["name"] == name)
    raise AssertionError("no dev building repeats a space name")


def plan(question: str, steps: list[tuple[str, str, dict]], answer: str) -> dict:
    return {"question": question, "steps": [{"id": i, "op": op, "args": args} for i, op, args in steps], "answer": answer}
