"""Schematic wall compilation. Source coordinates and navigation geometry never change."""
import hashlib
import json
import math
from functools import lru_cache

from floorwise.core.model import Building


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
    # Node and deduplicate partial collinear overlap for display only. Analytical walls are unchanged.
    from shapely.geometry import LineString
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
    unmatched = sorted(o['id'] for o in data['openings'] if any(s != 'outside' and (o['id'], s) not in matched for s in o['space_ids']))
    return {'revision': hashlib.sha256(content.encode()).hexdigest()[:16], 'walls': walls,
            'unmatched_openings': unmatched,
            'assumptions': ['Schematic reconstruction from supplied footprints; no window or stair-flight geometry is supplied.',
                            'Wall thickness and furniture heights are illustrative. Floor coordinates are preserved.']}
