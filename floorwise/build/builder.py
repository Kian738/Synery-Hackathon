"""Build a whole building from plan images, one per floor.

  uv run python -m floorwise.build.builder out_dir --floor 0=plan0.png --floor 1=plan1.png --width 55.5 [--vision]

1. scan each image (from_image.scan): rooms, doors, entrances
2. types from the learned fill palette; names/room types from Claude vision when --vision
3. metres: the ground floor's width in metres (one number from the person) sets the scale
4. floors are stacked by their stair/lift cores: a core keeps its size and place on every floor, so cores
   give each floor's scale and offset; overlapping cores on consecutive floors become stairs and lifts
5. validate: connectivity, unreachable rooms, rooms without doors"""

import argparse
import json
import math
from pathlib import Path

import networkx as nx
from shapely.geometry import Polygon

from floorwise.build.from_image import FloorScan, scan, to_building

PALETTE = json.loads(Path(__file__).with_name("palette.json").read_text(encoding="utf-8"))
CORE_TYPES = ("stair", "lift")
DEFAULT_ROOM_TYPE = {"room": "generic_room", "corridor": "corridor", "hall": "hall", "stair": "stairwell", "lift": "lift"}


def palette_label(colour: tuple[int, int, int]) -> dict:
    entry = PALETTE.get("#%02x%02x%02x" % colour)
    if entry is None or entry["n"] < 10:
        return {"type": "room", "room_type": "generic_room"}
    space_type = entry["type"]
    room_type = entry["room_type"] if entry["share"] >= 0.9 else DEFAULT_ROOM_TYPE.get(space_type, "generic_room")
    return {"type": space_type, "room_type": room_type}


def cores(floor_scan: FloorScan, labels: dict, level: int) -> list[tuple[str, tuple[float, float], float]]:
    out = []
    for region in floor_scan.regions:
        kind = labels[(level, region.index)]["type"]
        if kind in CORE_TYPES:
            out.append((kind, region.centre_px, region.area_px))
    return out


def stack_transforms(scans: list[tuple[int, FloorScan]], labels: dict, metres_per_pixel: float) -> dict[int, tuple[float, float, float]]:
    """Per level: (metres_per_pixel, dx_px, dy_px) mapping that floor's pixels into the base floor's pixels."""
    base_level, base_scan = min(scans, key=lambda item: abs(item[0]))
    base_cores = cores(base_scan, labels, base_level)
    transforms = {base_level: (metres_per_pixel, 0.0, 0.0)}
    for level, floor_scan in scans:
        if level == base_level:
            continue
        own = cores(floor_scan, labels, level)
        scale_ratio, dx, dy = 1.0, 0.0, 0.0
        pairs = []
        for kind, centre, area in own:
            same = [c for c in base_cores if c[0] == kind]
            if same:
                pairs.append(((kind, centre, area), same))
        if pairs:
            # Scale from core sizes, then offset from the best one-to-one core matching.
            ratios = [math.sqrt(min(s[2] for s in same) / area) for (_, _, area), same in pairs if area > 0]
            ratios = sorted(ratios)
            scale_ratio = ratios[len(ratios) // 2] if ratios else 1.0
            best = None
            for (_, centre, _), same in pairs:
                for candidate in same:
                    ox = candidate[1][0] - centre[0] * scale_ratio
                    oy = candidate[1][1] - centre[1] * scale_ratio
                    error = 0.0
                    for (k2, c2, _), same2 in pairs:
                        error += min(math.dist((c2[0] * scale_ratio + ox, c2[1] * scale_ratio + oy), s[1]) for s in same2)
                    if best is None or error < best[0]:
                        best = (error, ox, oy)
            _, dx, dy = best
        transforms[level] = (metres_per_pixel * scale_ratio, dx, dy)
    return transforms


def build(images: dict[int, Path], width_m: float | None = None, metres_per_pixel: float | None = None,
          name: str = "New building", building_id: str = "built", vision: bool = False) -> tuple[dict, dict]:
    scans = [(level, scan(path)) for level, path in sorted(images.items())]
    labels = {(level, r.index): palette_label(r.colour) for level, s in scans for r in s.regions}
    if vision:
        from floorwise.build.label import label_with_vision

        for level, path in sorted(images.items()):
            floor_scan = dict(scans)[level]
            for index, label in label_with_vision(path, floor_scan).items():
                labels[(level, index)].update({k: v for k, v in label.items() if v})
    base_level, base_scan = min(scans, key=lambda item: abs(item[0]))
    if metres_per_pixel is None:
        xs = [x for r in base_scan.regions for x, _ in r.polygon_px]
        metres_per_pixel = (width_m / (max(xs) - min(xs))) if width_m else 0.1
    transforms = stack_transforms(scans, labels, metres_per_pixel)
    # Bring every floor into the base floor's pixel frame, then one scale to metres.
    for level, floor_scan in scans:
        floor_mpp, dx, dy = transforms[level]
        ratio = floor_mpp / metres_per_pixel
        if level == base_level:
            continue
        for region in floor_scan.regions:
            region.polygon_px = [(x * ratio + dx, y * ratio + dy) for x, y in region.polygon_px]
            region.centre_px = (region.centre_px[0] * ratio + dx, region.centre_px[1] * ratio + dy)
        for marker in floor_scan.markers:
            marker.centre_px = (marker.centre_px[0] * ratio + dx, marker.centre_px[1] * ratio + dy)
        floor_scan.height = base_scan.height
    building = to_building(scans, metres_per_pixel, building_id=building_id, name=name, labels=labels)
    link_cores(building)
    return building, validate(building)


def link_cores(building: dict) -> None:
    by_floor = {}
    levels = {f["id"]: f["level"] for f in building["floors"]}
    for space in building["spaces"]:
        if space["type"] in CORE_TYPES:
            by_floor.setdefault(levels[space["floor_id"]], []).append(space)
    chains: list[list[dict]] = []
    for level in sorted(by_floor):
        for space in by_floor[level]:
            polygon = Polygon(space["polygon"])
            for chain in chains:
                last = chain[-1]
                if levels[last["floor_id"]] == level - 1 and last["type"] == space["type"]:
                    other = Polygon(last["polygon"])
                    if polygon.intersection(other).area > 0.3 * min(polygon.area, other.area):
                        chain.append(space)
                        break
            else:
                chains.append([space])
    for number, chain in enumerate(c for c in chains if len(c) > 1):
        kind = "lift" if chain[0]["type"] == "lift" else "stairs"
        building["vertical_connectors"].append({
            "id": f"{building['building']['id']}-V{number + 1:02d}", "kind": kind,
            "name": f"{'Lift' if kind == 'lift' else 'Staircase'} {number + 1}",
            "floor_ids": [s["floor_id"] for s in chain], "space_ids": [s["id"] for s in chain],
            "step_free": kind == "lift", "synthetic": True,
        })


def validate(building: dict) -> dict:
    graph = nx.Graph()
    graph.add_nodes_from(s["id"] for s in building["spaces"])
    for opening in building["openings"]:
        graph.add_edge(*opening["space_ids"])
    for connector in building["vertical_connectors"]:
        for a, b in zip(connector["space_ids"], connector["space_ids"][1:]):
            graph.add_edge(a, b)
    reachable = nx.node_connected_component(graph, "outside") if "outside" in graph else set()
    rooms = [s for s in building["spaces"] if s["type"] == "room"]
    return {
        "floors": len(building["floors"]), "spaces": len(building["spaces"]), "rooms": len(rooms),
        "doors": sum(1 for o in building["openings"] if o["kind"] == "door"),
        "entrances": sum(1 for o in building["openings"] if o["kind"] == "entrance"),
        "stairs_and_lifts": len(building["vertical_connectors"]),
        "unreachable_from_entrances": [s["name"] for s in building["spaces"] if s["id"] not in reachable][:20],
        "rooms_without_door": [s["name"] for s in rooms if graph.degree(s["id"]) == 0][:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="floorwise.build.builder")
    parser.add_argument("out", type=Path)
    parser.add_argument("--floor", action="append", required=True, help="LEVEL=path/to/plan.png")
    parser.add_argument("--width", type=float, default=None, help="ground floor width in metres")
    parser.add_argument("--name", default="New building")
    parser.add_argument("--vision", action="store_true", help="label rooms with Claude vision")
    args = parser.parse_args()
    images = {int(item.split("=", 1)[0]): Path(item.split("=", 1)[1]) for item in args.floor}
    building, report = build(images, width_m=args.width, name=args.name, building_id=args.out.name, vision=args.vision)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "building.json").write_text(json.dumps(building, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
