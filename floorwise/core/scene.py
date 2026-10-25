"""Schematic wall compilation. Source coordinates and navigation geometry never change."""
import hashlib
import json
import math
from functools import lru_cache

from shapely.geometry import LineString, Point

from floorwise.core.model import Building


DOOR_HEIGHT_M = 2.1
HEADER_MAX_WIDTH_M = 2.5


def compile_scene(building: Building) -> dict:
    return _compile(json.dumps(building.data, sort_keys=True, separators=(',', ':')))


@lru_cache(maxsize=32)
def _compile(content: str) -> dict:
    data = json.loads(content)
    floors = {f['id']: f for f in data['floors']}
    openings = {}
    for opening in data['openings']:
        for space in opening['space_ids']:
            openings.setdefault(space, []).append(opening)
    walls, unmatched = [], set()
    matched = set()
    seen = set()
    headers, header_seen = [], set()
    for space in data['spaces']:
        polygon = space['polygon']
        if len(polygon) < 3:
            continue
        height = float(floors[space['floor_id']].get('height_m') or 3)
        edges = list(zip(polygon, polygon[1:] + polygon[:1]))
        opening_edges = {}
        for o in openings.get(space['id'], []):
            candidates = []
            for index, (a, b) in enumerate(edges):
                dx, dy = b[0]-a[0], b[1]-a[1]
                length2 = dx*dx + dy*dy
                if length2 <= 1e-10:
                    continue
                x, y = o['position']
                t = max(0, min(1, ((x-a[0])*dx+(y-a[1])*dy)/length2))
                candidates.append((math.hypot(x-a[0]-t*dx, y-a[1]-t*dy), index))
            if candidates:
                distance, index = min(candidates)
                if distance <= 0.8:
                    opening_edges[o['id']] = index
        for edge_index, (a, b) in enumerate(edges):
            dx, dy = b[0]-a[0], b[1]-a[1]
            length = math.hypot(dx, dy)
            if length < 1e-5:
                continue
            cuts = []
            for o in openings.get(space['id'], []):
                if opening_edges.get(o['id']) != edge_index:
                    continue
                x, y = o['position']
                t = ((x-a[0])*dx + (y-a[1])*dy) / length**2
                distance = abs((x-a[0])*dy-(y-a[1])*dx) / length
                if distance <= 0.8 and -0.05 <= t <= 1.05:
                    half = max(0.1, float(o.get('width_m') or 0.9)/2)
                    cuts.append((max(0, t*length-half), min(length, t*length+half)))
                    matched.add((o['id'], space['id']))
                    if o.get('width_m', 0.9) <= HEADER_MAX_WIDTH_M and o.get('kind') != 'opening' or o.get('width_m', 0.9) <= 1.6:
                        # The wall above a door or narrow opening stays: a lintel from the door height up to the ceiling.
                        low_h, high_h = max(0, t*length-half), min(length, t*length+half)
                        door_h = min(DOOR_HEIGHT_M, max(height - 0.3, 0.5))
                        start = [a[0]+dx*low_h/length, a[1]+dy*low_h/length]
                        end = [a[0]+dx*high_h/length, a[1]+dy*high_h/length]
                        key = (space['floor_id'], tuple(sorted((tuple(round(v, 2) for v in start), tuple(round(v, 2) for v in end)))))
                        if key not in header_seen and high_h-low_h > 0.05 and height > door_h + 0.05:
                            header_seen.add(key)
                            headers.append({'floor_id': space['floor_id'], 'a': [round(v, 3) for v in start], 'b': [round(v, 3) for v in end],
                                            'base_m': door_h, 'height_m': height})
            spans, cursor = [], 0.0
            for low, high in sorted(cuts):
                if low > cursor:
                    spans.append((cursor, low))
                cursor = max(cursor, high)
            if cursor < length:
                spans.append((cursor, length))
            for low, high in spans:
                if high-low < 0.02:
                    continue
                start = [a[0]+dx*low/length, a[1]+dy*low/length]
                end = [a[0]+dx*high/length, a[1]+dy*high/length]
                key = (space['floor_id'], tuple(sorted((tuple(round(v, 3) for v in start), tuple(round(v, 3) for v in end)))))
                if key in seen:
                    continue
                seen.add(key)
                walls.append({'floor_id': space['floor_id'], 'space_id': space['id'], 'a': start, 'b': end, 'height_m': height})
    # A doorway clears every wall inside its thin box, including walls of a third space that overlaps the door in the
    # supplied footprints (a lift shaft drawn over a corridor), so no route meets a wall stub inside a doorway.
    from shapely import STRtree as _Tree
    from shapely.ops import unary_union as _union
    cleared = []
    for fid in floors:
        floor_walls = [w for w in walls if w['floor_id'] == fid]
        zones, zone_spaces = [], []
        lines = [LineString([w['a'], w['b']]) for w in floor_walls]
        wall_tree = _Tree(lines) if lines else None
        for o in data['openings']:
            if o.get('floor_id') != fid or o.get('kind') not in ('door', 'entrance', 'opening') or wall_tree is None:
                continue
            half = max(0.1, float(o.get('width_m') or 0.9)/2)
            point = Point(o['position'])
            nearest = int(wall_tree.nearest(point))
            host, best = floor_walls[nearest], lines[nearest].distance(point)
            if best > 0.8:
                continue
            hx, hy = host['b'][0]-host['a'][0], host['b'][1]-host['a'][1]
            hn = math.hypot(hx, hy) or 1.0
            ux, uy = hx/hn, hy/hn
            px, py = o['position']
            zones.append(LineString([(px-ux*half, py-uy*half), (px+ux*half, py+uy*half)]).buffer(0.35, cap_style='flat'))
            zone_spaces.append(set(o['space_ids']))
        if not zones:
            cleared += floor_walls
            continue
        tree = _Tree(zones)
        for wall, line in zip(floor_walls, lines):
            # Only walls of spaces the opening does not join: the joined spaces were cut along their own wall above.
            hits = [i for i in tree.query(line, predicate='intersects') if wall['space_id'] not in zone_spaces[int(i)]]
            if not hits:
                cleared.append(wall)
                continue
            rest = line.difference(_union([zones[int(i)] for i in hits]))
            for part in getattr(rest, 'geoms', [rest]):
                if part.is_empty or part.length < 0.02:
                    continue
                coords = list(part.coords)
                cleared.append({**wall, 'a': [coords[0][0], coords[0][1]], 'b': [coords[-1][0], coords[-1][1]]})
    walls = cleared
    # Node and deduplicate partial collinear overlap for display only. Analytical walls are unchanged.
    from shapely.ops import unary_union
    unique=[]
    for fid in floors:
        source=[w for w in walls if w['floor_id']==fid]
        if not source:continue
        from shapely import STRtree
        source_lines=[LineString([w['a'],w['b']]) for w in source]
        tree=STRtree(source_lines)
        union=unary_union(source_lines)
        segments=list(union.geoms) if hasattr(union,'geoms') else [union]
        for segment in segments:
            coords=list(segment.coords)
            for a,b in zip(coords,coords[1:]):
                owners=tree.query(LineString([a,b]),predicate='covered_by')
                owner=source[int(owners[0])]['space_id'] if len(owners) else None
                unique.append({'floor_id':fid,'space_id':owner,'a':list(a),'b':list(b),'height_m':source[0]['height_m']})
    walls=unique
    walls=apply_rails(data, walls)
    # Actual upper-floor footprints form ceilings below. Missing coverage stays open.
    from shapely import constrained_delaunay_triangles, make_valid
    from shapely.geometry import Polygon
    slabs = []
    for fid in floors:
        footprint = unary_union([make_valid(Polygon(s['polygon'])) for s in data['spaces']
                                 if s['floor_id'] == fid and len(s['polygon']) >= 3])
        triangles = constrained_delaunay_triangles(footprint)
        vertices = [list(p) for triangle in triangles.geoms for p in list(triangle.exterior.coords)[:3]]
        slabs.append({'floor_id': fid, 'vertices': vertices, 'area_m2': footprint.area})
    # A roof closes every indoor footprint that has no floor above it (the top floor, and wings lower than their
    # neighbours). Where a floor above does cover it, that floor is the ceiling instead. Outdoor spaces get no roof, and
    # nothing is inferred over an atrium the data does not record as a space.
    roofs = []
    ordered = sorted(data['floors'], key=lambda f: f.get('level', f.get('elevation_m', 0)))
    indoor = {f['id']: unary_union([make_valid(Polygon(sp['polygon'])) for sp in data['spaces']
                                    if sp['floor_id'] == f['id'] and sp.get('type') != 'outdoor' and len(sp['polygon']) >= 3]) for f in ordered}
    for index, floor in enumerate(ordered):
        cover = indoor[floor['id']]
        if cover.is_empty:
            continue
        if index + 1 < len(ordered):
            above = indoor[ordered[index + 1]['id']]
            if not above.is_empty:
                cover = cover.difference(above.buffer(0.05))
        cover = cover.buffer(0)
        if cover.is_empty or cover.area < 0.5:
            continue
        triangles = constrained_delaunay_triangles(cover)
        vertices = [list(p) for triangle in triangles.geoms for p in list(triangle.exterior.coords)[:3]]
        roofs.append({'floor_id': floor['id'], 'vertices': vertices, 'area_m2': cover.area,
                      'elevation_m': float(floor.get('elevation_m') or 0.0) + float(floor.get('height_m') or 3.0)})
    unmatched = sorted(o['id'] for o in data['openings'] if any(s != 'outside' and (o['id'], s) not in matched for s in o['space_ids']))
    from floorwise.core.stair_scene import compile_stair_plates, compile_stair_shafts
    shafts=compile_stair_shafts(data)
    plates=compile_stair_plates(data,shafts)
    return {'stair_shafts':shafts,'plates':plates,'overlaps':compile_overlaps(data), 'revision': hashlib.sha256(('scene-v5:' + content).encode()).hexdigest()[:16], 'walls': walls, 'slabs': slabs,
            'headers': headers, 'roofs': roofs,
            'unmatched_openings': unmatched,
            'assumptions': ['Schematic reconstruction from supplied footprints; no window or stair-flight geometry is supplied.',
                            'Wall thickness and furniture heights are illustrative. Floor coordinates are preserved.',
                            'Stair meshes stay within shared recorded shaft footprints; unfit flights are withheld. Stair internals remain illustrative.',
                            'Slabs use recorded space footprints. Roofs close indoor footprints with no floor above; no atrium is inferred.',
                            'Lintels close the wall above doors and narrow openings at 2.1 m; their height is illustrative.']}


def compile_overlaps(data: dict, min_area: float = 0.05) -> list[dict]:
    """Display only: where two rooms of one floor overlap in the data, the part they share, so the 3D view can draw it as a blend of both
    floor colours instead of two floors fighting for the same pixels (`eval.overlaps` counts them). Analytical polygons are never touched."""
    from shapely import make_valid
    from shapely.geometry import Polygon
    from shapely.strtree import STRtree

    out: list[dict] = []
    by_floor: dict[str, list[tuple[str, Polygon]]] = {}
    for space in data['spaces']:
        if len(space['polygon']) >= 3:
            by_floor.setdefault(space['floor_id'], []).append((space['id'], make_valid(Polygon(space['polygon']))))
    for floor_id, items in by_floor.items():
        tree = STRtree([poly for _, poly in items])
        for i, (first, poly) in enumerate(items):
            for j in sorted(tree.query(poly)):
                if j <= i:
                    continue
                second, other = items[j]
                shared = poly.intersection(other)
                for part in getattr(shared, 'geoms', [shared]):
                    if part.geom_type == 'Polygon' and part.area >= min_area:
                        out.append({'floor_id': floor_id, 'a': first, 'b': second, 'polygon': [list(p) for p in part.exterior.coords][:-1], 'area_m2': round(part.area, 3)})
    return out

def apply_rails(data: dict, walls: list[dict], rail_height: float = 1.1, min_open: float = 0.6) -> list[dict]:
    """Open-air walkways (a bridge across an atrium, a stair standing in a void) get a fence, not a room's wall.

    A corridor or stair on an upper floor whose walls mostly face empty air (nothing of that floor within 0.3 m outside) is open to the sky or
    the atrium: its open edges become railings of ail_height and carry ail: True. Walls toward neighbouring rooms stay full height. Display
    only; the analytical model is untouched."""
    from shapely import make_valid
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union

    ordered = sorted(data['floors'], key=lambda f: f.get('level', f.get('elevation_m', 0)))
    if len(ordered) < 2:
        return walls
    lowest = ordered[0]['id']
    polygons = {s['id']: make_valid(Polygon(s['polygon'])) for s in data['spaces'] if len(s['polygon']) >= 3}
    cover = {f['id']: unary_union([polygons[s['id']] for s in data['spaces'] if s['floor_id'] == f['id'] and s['id'] in polygons]) for f in ordered}
    by_space = {s['id']: s for s in data['spaces']}
    open_edge: list[bool] = []
    total: dict[str, float] = {}
    exposed: dict[str, float] = {}
    for wall in walls:
        owner = by_space.get(wall.get('space_id') or '')
        is_open = False
        if owner and owner['type'] in ('corridor', 'stair') and owner['floor_id'] != lowest and owner['id'] in polygons:
            (ax, ay), (bx, by) = wall['a'], wall['b']
            length = math.hypot(bx - ax, by - ay)
            if length > 1e-6:
                nx, ny = -(by - ay) / length, (bx - ax) / length
                mx, my = (ax + bx) / 2, (ay + by) / 2
                sides = [Point(mx + nx * 0.3, my + ny * 0.3), Point(mx - nx * 0.3, my - ny * 0.3)]
                outside = [p for p in sides if not polygons[owner['id']].buffer(0.05).contains(p)]
                is_open = bool(outside) and not any(cover[owner['floor_id']].buffer(0.02).contains(p) for p in outside)
                total[owner['id']] = total.get(owner['id'], 0.0) + length
                if is_open:
                    exposed[owner['id']] = exposed.get(owner['id'], 0.0) + length
        open_edge.append(is_open)
    def elongated(sid: str) -> bool:
        edges = list(polygons[sid].minimum_rotated_rectangle.exterior.coords)
        sides = sorted(math.dist(edges[i], edges[i + 1]) for i in range(2))
        return sides[0] > 0 and sides[1] / sides[0] >= 3.0

    # A stair standing in the air, or a long narrow walkway open on both sides (a bridge, a gallery): not a hall on the facade.
    railed = {sid for sid, length in total.items() if length and exposed.get(sid, 0.0) / length >= min_open
              and (by_space[sid]['type'] == 'stair' or (elongated(sid) and exposed.get(sid, 0.0) / length >= 0.7))}
    out = []
    for wall, is_open in zip(walls, open_edge):
        if is_open and wall.get('space_id') in railed:
            out.append({**wall, 'height_m': min(wall['height_m'], rail_height), 'rail': True})
        else:
            out.append(wall)
    return out