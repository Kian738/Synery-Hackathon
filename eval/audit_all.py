"""One audit over every supplied building: data quality, scene compile and connector health, ranked, written to docs/AUDIT_<date>.md.

Each finding has a severity (how bad when it happens) and a count (how many buildings or rooms). Re-run it after any change to scene, routing
or the models; the table shows what a user could meet, in the order worth fixing.

  uv run python -m eval.audit_all                  # all buildings, writes docs/AUDIT_<date>.md
  uv run python -m eval.audit_all --limit 20       # quick look"""

import argparse
import datetime
import time
from collections import Counter, defaultdict

from shapely import make_valid
from shapely.geometry import Point, Polygon

from eval.common import building_paths
from eval.connectivity import audit_building
from eval.overlaps import overlaps
from floorwise.core.model import Building
from floorwise.core.scene import compile_scene
from floorwise.paths import ROOT


def audit(building: Building) -> list[tuple[str, str, int, str]]:
    """(severity, key, count, example) per finding for one building."""
    out: list[tuple[str, str, int, str]] = []
    conn = audit_building(building)
    stranded = sum(conn["cut"].values())
    if conn.get("entrance_stranded"):
        out.append(("high", "default entrance cannot reach most of the building", 1, f"entrance part {conn.get('entrance_part')} of {conn['main']}"))
    if stranded:
        out.append(("medium", "rooms with no way to the main part (data fact)", stranded, str(conn["cut"])))
    found = overlaps(building)
    if found:
        out.append(("low", "rooms overlap (drawn as blend)", len(found), f"{found[0][1]} / {found[0][2]}"))
    polygons = {sid: make_valid(Polygon(s["polygon"])) for sid, s in building.spaces.items() if len(s["polygon"]) >= 3}
    outside = [a["id"] for a in building.assets.values() if a["space_id"] in polygons and not polygons[a["space_id"]].buffer(0.3).contains(Point(a["position"]))]
    if outside:
        out.append(("medium", "items positioned outside their room", len(outside), outside[0]))
    tiny = [sid for sid, p in polygons.items() if p.area < 0.3 and building.spaces[sid]["type"] != "outdoor"]
    if tiny:
        out.append(("low", "rooms smaller than 0.3 m2", len(tiny), tiny[0]))
    started = time.time()
    scene = compile_scene(building)
    seconds = time.time() - started
    if seconds > 5:
        out.append(("medium", "scene compile slower than 5 s", 1, f"{seconds:.1f} s"))
    if scene["unmatched_openings"]:
        out.append(("medium", "openings without a wall to sit in", len(scene["unmatched_openings"]), scene["unmatched_openings"][0]))
    withheld = [s for s in scene["stair_shafts"] if s.get("warning")]
    if withheld:
        out.append(("high", "stair flights withheld (no safe footprint)", len(withheld), f"{withheld[0]['connector_id']}"))
    if building.connectors and not scene["stair_shafts"]:
        out.append(("high", "connectors but no stair shafts compiled", len(building.connectors), ""))
    names = Counter(s["name"] for s in building.spaces.values() if s["type"] in ("room", "hall"))
    dup = sum(1 for n, c in names.items() if c > 1 and n)
    if dup:
        out.append(("low", "room names used more than once", dup, next(n for n, c in names.items() if c > 1)))
    return out


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.audit_all")
    cli.add_argument("--split", default="train,dev,test")
    cli.add_argument("--limit", type=int, default=None)
    cli.add_argument("--out", default=None)
    args = cli.parse_args()
    paths = building_paths(args.split.split(","))[: args.limit]
    table: dict[str, dict] = defaultdict(lambda: {"buildings": 0, "count": 0, "severity": "low", "example": "", "building": ""})
    rank = {"high": 0, "medium": 1, "low": 2}
    for path in paths:
        building = Building.load(path.parent)
        for severity, key, count, example in audit(building):
            row = table[key]
            row["buildings"] += 1
            row["count"] += count
            row["severity"] = min(row["severity"], severity, key=rank.get)
            if not row["example"]:
                row["example"], row["building"] = example, building.id
    rows = sorted(table.items(), key=lambda kv: (rank[kv[1]["severity"]], -kv[1]["buildings"]))
    date = datetime.date.today().isoformat()
    lines = [f"# Data and scene audit, {date}", "", f"{len(paths)} buildings. Severity x frequency; example is one building to open first.", "",
             "| Severity | Finding | Buildings | Total | Example |", "|---|---|---|---|---|"]
    lines += [f"| {v['severity']} | {k} | {v['buildings']} | {v['count']} | `{v['building']}` {v['example']} |" for k, v in rows]
    target = ROOT / (args.out or f"docs/AUDIT_{date}.md")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwritten to {target}")


if __name__ == "__main__":
    main()
