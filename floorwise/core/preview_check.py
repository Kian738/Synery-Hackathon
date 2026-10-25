"""Display safety gate; never changes official graph weights or benchmark answers."""
from functools import lru_cache
from shapely import STRtree
from shapely.geometry import LineString


@lru_cache(maxsize=16)
def wall_index(building):
    from floorwise.core.scene import compile_scene
    floors = {}
    for wall in compile_scene(building)['walls']:
        floors.setdefault(wall['floor_id'], []).append(LineString([wall['a'], wall['b']]))
    return {fid: (STRtree(walls), walls) for fid, walls in floors.items()}


def issues(building, points):
    from floorwise.core.walk import BLOCKING_CATEGORIES, _footprint_polygon
    walls = wall_index(building)
    obstacles = {}
    for a in building.assets.values():
        if a.get('category') in BLOCKING_CATEGORIES:
            obstacles.setdefault(a['space_id'], []).append(_footprint_polygon(a, 0))
    found = set()
    for p, q in zip(points, points[1:]):
        if q.get('gap') or p['floor_id'] != q['floor_id']: continue
        segment = LineString([(p['x'], p['y']), (q['x'], q['y'])])
        if segment.length < .01: continue
        if p['floor_id'] in walls:
            tree, lines = walls[p['floor_id']]
            for index in tree.query(segment):
                wall = lines[int(index)]
                if segment.crosses(wall) or segment.intersection(wall).length > .05:
                    found.add('rendered wall')
        if p.get('node') == q.get('node') and any(segment.crosses(o) or segment.within(o) for o in obstacles.get(p.get('node'), [])):
            found.add('recorded furniture')
    return sorted(found)
