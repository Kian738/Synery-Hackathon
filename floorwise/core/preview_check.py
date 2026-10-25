"""Display safety gate; never changes official graph weights or benchmark answers."""
from functools import lru_cache
from shapely import STRtree
from shapely.geometry import LineString, Point


MIN_WALL_M = 0.3
DOOR_SLACK_M = 0.6


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
    doors: dict[str, list[Point]] = {}
    for o in building.openings.values():
        if o.get('kind') in ('door', 'entrance', 'opening'):
            doors.setdefault(o['floor_id'], []).append(Point(o['position']))
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
                if wall.length < MIN_WALL_M:  # a 20 cm stub left by a digitised notch is not a barrier anyone walks around
                    continue
                if segment.crosses(wall) or segment.intersection(wall).length > .05:
                    # A walking line that grazes a wall end beside a door is going through the door: the wall pieces are cut to the door
                    # width, and a door sitting at a room corner leaves the next wall starting a hand's breadth from where people pass.
                    crossing = segment.intersection(wall)
                    if any(crossing.distance(door) < DOOR_SLACK_M for door in doors.get(p['floor_id'], [])):
                        continue
                    found.add('rendered wall')
        if p.get('node') == q.get('node') and any(segment.crosses(o) or segment.within(o) for o in obstacles.get(p.get('node'), [])):
            found.add('recorded furniture')
    return sorted(found)
