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
    if entry is None:
        # Compression/antialiasing can move an otherwise known fill by a few
        # levels. Accept a close training-palette colour only when its type is
        # unambiguous among equally close colours.
        nearby=[]
        for key,candidate in PALETTE.items():
            if candidate['n']<10:continue
            rgb=tuple(int(key[i:i+2],16) for i in (1,3,5))
            if max(abs(a-b) for a,b in zip(colour,rgb))<=7:
                nearby.append((math.dist(colour,rgb),candidate))
        nearby.sort(key=lambda pair:pair[0])
        if nearby and len({e['type'] for d,e in nearby if d<=nearby[0][0]+2.})==1:
            entry=nearby[0][1]
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


def stack_transforms(scans: list[tuple[int, FloorScan]], labels: dict, metres_per_pixel: float,
                     base_level: int | None = None, issues: list[str] | None = None) -> dict[int, tuple[float, float, float]]:
    """One-to-one core registration. No source coordinates enter this calculation."""
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    issues = issues if issues is not None else []
    if base_level is None:base_level=scans[0][0]
    base_scan=dict(scans)[base_level]
    base_cores=cores(base_scan,labels,base_level)
    transforms={base_level:(metres_per_pixel,0.,0.)}
    for level,floor_scan in scans:
        if level==base_level:continue
        own=cores(floor_scan,labels,level);hypotheses=[]
        for kind,centre,area in own:
            for bk,bc,ba in base_cores:
                if bk!=kind or area<=0:continue
                ratio=math.sqrt(ba/area)
                dx,dy=bc[0]-centre[0]*ratio,bc[1]-centre[1]*ratio
                cost=np.full((len(own),len(base_cores)),1e6)
                for i,(k,c,a) in enumerate(own):
                    for j,(kk,cc,aa) in enumerate(base_cores):
                        if k==kk:
                            location=math.dist((c[0]*ratio+dx,c[1]*ratio+dy),cc)
                            size=abs(math.sqrt(a)*ratio-math.sqrt(aa))
                            cost[i,j]=location+size
                rows,cols=linear_sum_assignment(cost)
                tolerance=max(3.,math.sqrt(ba)*.20)
                pairs=[(i,j) for i,j in zip(rows,cols) if cost[i,j]<=tolerance]
                error=sum(cost[i,j] for i,j in pairs)/max(1,len(pairs))
                hypotheses.append((-len(pairs),error,ratio,dx,dy))
        if not hypotheses:
            issues.append(f'Floor {level}: no common labelled core; alignment is unverified.')
            transforms[level]=(metres_per_pixel,0.,0.);continue
        hypotheses.sort();best=hypotheses[0]
        alternatives=[h for h in hypotheses[1:] if h[0]==best[0] and h[1]<=best[1]+.5 and math.dist(h[3:5],best[3:5])>3.]
        if alternatives:
            issues.append(f'Floor {level}: several core alignments fit; confirm registration.')
        transforms[level]=(metres_per_pixel*best[2],best[3],best[4])
    return transforms


def build(images: dict[int, Path], width_m: float | None = None, metres_per_pixel: float | None = None,
          name: str = "New building", building_id: str = "built", vision: bool = False) -> tuple[dict, dict]:
    if not images:raise ValueError('Supply at least one floor-plan image')
    if metres_per_pixel is None and (width_m is None or not math.isfinite(width_m) or width_m<=0):
        raise ValueError('Supply one real plan width; absolute scale is not present in an image')
    if metres_per_pixel is not None and (not math.isfinite(metres_per_pixel) or metres_per_pixel<=0):
        raise ValueError('Metres per pixel must be finite and positive')
    scans = [(level, scan(path)) for level, path in sorted(images.items())]
    if any(not floor_scan.regions for _,floor_scan in scans):
        raise ValueError('No recoverable rooms on one or more floors; a reviewed plan or clearer image is needed')
    issues=[]
    labels = {(level, r.index): palette_label(r.colour) for level, s in scans for r in s.regions}
    if vision:
        from floorwise.build.label import label_with_vision

        for level, path in sorted(images.items()):
            floor_scan = dict(scans)[level]
            for index, label in label_with_vision(path, floor_scan).items():
                labels[(level, index)].update({k: v for k, v in label.items() if v})
    base_level=next(iter(images))
    base_scan=dict(scans)[base_level]
    if metres_per_pixel is None:
        xs = [x for r in base_scan.regions for x, _ in r.polygon_px]
        metres_per_pixel = (width_m / (max(xs) - min(xs))) if width_m else 0.1
    transforms = stack_transforms(scans, labels, metres_per_pixel, base_level, issues)
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
    # Uncertain registration must not invent traversable inter-floor links.
    if not any('alignment' in issue or 'registration' in issue for issue in issues):
        link_cores(building)
    unknown=sum(palette_label(r.colour)['room_type']=='generic_room' for _,floor_scan in scans for r in floor_scan.regions)
    if unknown and not vision:issues.append(f'{unknown} room labels/types could not be inferred; confirm their meaning.')
    report=validate(building)
    report.update({'status':'draft','review_required':bool(issues),'warnings':issues,
                   'provenance':{'geometry':'image segmentation','scale':'caller supplied dimension',
                                 'registration':'one-to-one labelled core matching',
                                 'semantics':'vision labels' if vision else 'training palette; unrecognized colours remain generic'},
                   'inferred_fields':['Opening widths default to 0.9 m; verify physical clearance.',
                                      'Opening accessibility defaults to step-free and is unverified; confirm it before accessible guidance.',
                                      'Floor elevations use the supplied/default floor height.']})
    return building, report


def link_cores(building: dict) -> None:
    """Assign every core at most once per floor; stairs never jump missing levels."""
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    levels={f['id']:f['level'] for f in building['floors']}
    chains=[]
    for level in sorted(set(levels.values())):
        own=[s for s in building['spaces'] if levels[s['floor_id']]==level and s['type'] in CORE_TYPES]
        existing=[c for c in chains if levels[c[-1]['floor_id']]<level and
                  (c[-1]['type']=='lift' or levels[c[-1]['floor_id']]==level-1)]
        costs=np.zeros((len(existing),len(own)))
        for i,chain in enumerate(existing):
            p=Polygon(chain[-1]['polygon'])
            for j,s in enumerate(own):
                if s['type']==chain[-1]['type']:
                    q=Polygon(s['polygon']);costs[i,j]=p.intersection(q).area/max(min(p.area,q.area),1e-9)
        assigned=set()
        if costs.size:
            rows,cols=linear_sum_assignment(-costs)
            for i,j in zip(rows,cols):
                if costs[i,j]>.3:
                    existing[i].append(own[j]);assigned.add(int(j))
        chains.extend([[s] for j,s in enumerate(own) if j not in assigned])
    for number,chain in enumerate(c for c in chains if len(c)>1):
        kind='lift' if chain[0]['type']=='lift' else 'stairs'
        building['vertical_connectors'].append({'id':f"{building['building']['id']}-V{number+1:02d}",
            'kind':kind,'name':f"{'Lift' if kind=='lift' else 'Staircase'} {number+1}",
            'floor_ids':[s['floor_id'] for s in chain],'space_ids':[s['id'] for s in chain],
            'step_free':kind=='lift','synthetic':True})


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
