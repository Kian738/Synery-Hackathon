"""The drawn building envelope: lintels over doors, roofs only where nothing is above, doorways clear third-party walls."""
from shapely.geometry import Point, Polygon

from floorwise.core.model import Building
from floorwise.core.scene import compile_scene


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def make(spaces, openings=(), floors=None):
    floors = floors or [{'id': 'g', 'level': 0, 'elevation_m': 0, 'height_m': 3.0}, {'id': 'u', 'level': 1, 'elevation_m': 3.0, 'height_m': 3.0}]
    return Building({'building': {'id': 't'}, 'floors': floors, 'spaces': spaces, 'openings': list(openings), 'vertical_connectors': [], 'assets': []})


def space(i, floor, poly, kind='room'):
    return {'id': i, 'floor_id': floor, 'type': kind, 'room_type': 'office', 'polygon': poly}


def test_the_wall_above_a_door_stays_but_wide_openings_stay_open():
    spaces = [space('a', 'g', rect(0, 0, 10, 10)), space('b', 'g', rect(10, 0, 20, 10))]
    door = {'id': 'd', 'floor_id': 'g', 'space_ids': ['a', 'b'], 'kind': 'door', 'position': [10, 5], 'width_m': 0.9, 'step_free': True}
    hall = {'id': 'h', 'floor_id': 'g', 'space_ids': ['a', 'b'], 'kind': 'opening', 'position': [10, 2], 'width_m': 6.0, 'step_free': True}
    scene = compile_scene(make(spaces, [door]))
    assert [(h['base_m'], h['height_m']) for h in scene['headers']] == [(2.1, 3.0)]
    header = scene['headers'][0]
    assert abs(abs(header['a'][1] - header['b'][1]) - 0.9) < 0.02  # as wide as the door, on the shared wall
    wide = compile_scene(make(spaces, [hall]))
    assert wide['headers'] == []  # a six metre opening between halls is open to the ceiling


def test_roofs_cover_only_indoor_footprints_with_nothing_above():
    spaces = [space('hall', 'g', rect(0, 0, 10, 10)), space('n', 'u', rect(0, 0, 10, 2)), space('s', 'u', rect(0, 8, 10, 10)),
              space('terrace', 'g', rect(10, 0, 14, 10), kind='outdoor')]
    roofs = {r['floor_id']: r for r in compile_scene(make(spaces))['roofs']}
    ground, upper = roofs['g'], roofs['u']
    assert upper['elevation_m'] == 6.0 and abs(upper['area_m2'] - 40) < 1e-6          # the top floor is roofed
    assert ground['elevation_m'] == 3.0 and abs(ground['area_m2'] - 60) < 1.5         # 100 m2 minus the 40 m2 the upper floor covers (plus a 5 cm overlap margin)
    triangles = [Polygon(ground['vertices'][i:i + 3]) for i in range(0, len(ground['vertices']), 3)]
    assert all(not t.covers(Point(5, 1)) for t in triangles)                          # under the upper floor: no roof
    assert any(t.covers(Point(5, 5)) for t in triangles)                              # the open middle is roofed (nothing above)
    assert all(not t.covers(Point(12, 5)) for t in triangles)                         # the outdoor terrace gets none


def test_a_doorway_clears_a_third_spaces_wall_but_not_its_own_walls():
    spaces = [space('a', 'g', rect(0, 0, 10, 10)), space('b', 'g', rect(10, 0, 20, 10)), space('shaft', 'g', rect(9.4, 4, 10.6, 6), kind='lift')]
    door = {'id': 'd', 'floor_id': 'g', 'space_ids': ['a', 'b'], 'kind': 'door', 'position': [10, 5], 'width_m': 0.9, 'step_free': True}
    walls = compile_scene(make(spaces, [door]))['walls']
    from shapely.geometry import LineString
    doorway = LineString([(9.9, 5), (10.1, 5)])
    assert not any(LineString([w['a'], w['b']]).intersects(doorway) for w in walls)
