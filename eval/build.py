"""L7: rebuild floors from their plan images and compare with the true building.json.

Scale and offset are taken from the true outline's bounding box (simulating "the building is N m wide",
the one number a person gives the builder). Metrics per floor:
- room recall: true spaces matched by a rebuilt space with IoU >= 0.5
- mean IoU of matched spaces, false spaces (rebuilt spaces with no match)
- door recall: true doors with a rebuilt door within 1 m joining the same matched spaces
- connected: every rebuilt space reachable from the entrances"""

import argparse
import random
from pathlib import Path

import networkx as nx
from shapely.geometry import Point, Polygon
from shapely.validation import make_valid

from eval.common import source_of
from eval.ledger import Ledger
from floorwise.build.from_image import scan
from floorwise.core.model import Building
from floorwise.paths import DATA

IOU_MATCH = 0.5
DOOR_RADIUS_M = 1.0


def poly(points) -> Polygon:
    p = Polygon(points)
    return p if p.is_valid else make_valid(p)


def evaluate_floor(building: Building, floor: dict, image: Path) -> dict:
    floor_scan = scan(image)
    truth = {s["id"]: poly(s["polygon"]) for s in building.spaces_on(floor["id"])}
    if not truth or not floor_scan.regions:
        return {"room_recall": 0.0, "error": "nothing found"}
    xs = [x for p in truth.values() for x in p.exterior.coords.xy[0]] if all(p.geom_type == "Polygon" for p in truth.values()) else \
        [c[0] for s in building.spaces_on(floor["id"]) for c in s["polygon"]]
    ys = [c[1] for s in building.spaces_on(floor["id"]) for c in s["polygon"]]
    xs = [c[0] for s in building.spaces_on(floor["id"]) for c in s["polygon"]]
    px = [x for r in floor_scan.regions for x, _ in r.polygon_px]
    py = [y for r in floor_scan.regions for _, y in r.polygon_px]
    scale_x = (max(xs) - min(xs)) / max(1e-9, (max(px) - min(px)))
    scale_y = (max(ys) - min(ys)) / max(1e-9, (max(py) - min(py)))
    scale = (scale_x + scale_y) / 2

    def to_m(x, y):
        return (min(xs) + (x - min(px)) * scale, max(ys) - (y - min(py)) * scale)

    rebuilt = {r.index: poly([to_m(x, y) for x, y in r.polygon_px]) for r in floor_scan.regions}
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    true_ids, rebuilt_ids = list(truth), list(rebuilt)
    overlaps=np.array([[truth[t].intersection(rebuilt[r]).area / max(1e-9,truth[t].union(rebuilt[r]).area)
                        for r in rebuilt_ids] for t in true_ids])
    match, ious = {}, []
    if overlaps.size:
        left,right=linear_sum_assignment(-overlaps)
        for i,j in zip(left,right):
            if overlaps[i,j]>=IOU_MATCH:
                match[true_ids[i]]=rebuilt_ids[j];ious.append(float(overlaps[i,j]))
    matched_regions = set(match.values())
    true_doors = [o for o in building.openings.values() if o["floor_id"] == floor["id"] and "outside" not in o["space_ids"]]
    found = 0
    for opening in true_doors:
        a, b = opening["space_ids"]
        if a not in match or b not in match:
            continue
        target = Point(opening["position"])
        for marker in floor_scan.markers:
            if marker.kind == "door" and set(marker.regions) == {match[a], match[b]} and \
                    Point(to_m(*marker.centre_px)).distance(target) <= DOOR_RADIUS_M:
                found += 1
                break
    graph = nx.Graph()
    graph.add_nodes_from(rebuilt)
    for marker in floor_scan.markers:
        if marker.kind == "door":
            graph.add_edge(*marker.regions)
        else:
            graph.add_edge("outside", marker.regions[0])
    reach = nx.node_connected_component(graph,'outside') if 'outside' in graph else set()
    return {
        "room_recall": round(len(match) / len(truth), 3),
        'room_precision': round(len(match) / max(1,len(rebuilt)),3),
        'calibration': 'assisted: supplied true outline bounds, not autonomous scale recovery',
        "mean_iou": round(sum(ious) / len(ious), 3) if ious else 0.0,
        "false_spaces": len(rebuilt) - len(matched_regions),
        "door_recall": round(found / len(true_doors), 3) if true_doors else None,
        "connected_share": round(len([n for n in reach if n != "outside"]) / len(rebuilt), 3),  # largest component
        "spaces_true": len(truth), "spaces_rebuilt": len(rebuilt),
    }


def main() -> None:
    cli = argparse.ArgumentParser(prog="eval.build")
    cli.add_argument("--split", default="dev")
    cli.add_argument("--limit", type=int, default=40)
    cli.add_argument("--recall-gate", type=float, default=0.9)
    args = cli.parse_args()
    ledger = Ledger("build", {"split": args.split})
    directories = sorted((DATA / args.split).glob("*/building.json"))
    random.Random(3).shuffle(directories)
    for path in directories[: args.limit]:
        building = Building.load(path.parent)
        for floor in building.floors.values():
            image = path.parent / f"floor_{floor['level']}_plain.png"
            if not image.exists():
                continue
            metrics = evaluate_floor(building, floor, image)
            doors = metrics.get('door_recall')
            ok = metrics.get("room_recall", 0) >= args.recall_gate and (doors is None or doors >= args.recall_gate) and metrics.get('connected_share',0)>=args.recall_gate
            ledger.record(id=floor["id"], kind="floor", source=source_of(building.id), correct=ok, **metrics)
    rows = ledger.rows
    summary = ledger.finish()
    for key in ("room_recall", "mean_iou", "door_recall", "connected_share"):
        values = [r[key] for r in rows if r.get(key) is not None]
        print(f"  mean {key:16s} {sum(values) / max(1, len(values)):.3f}")
    if not summary['total'] or summary['correct'] != summary['total']:
        raise SystemExit('Image reconstruction did not meet the configured per-floor checks; see the raw metrics.')


if __name__ == "__main__":
    main()
