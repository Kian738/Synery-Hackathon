import copy

from shapely.geometry import Point, Polygon

from floorwise.core.model import Building
from floorwise.core.scene import compile_scene


def test_upper_footprints_preserve_atrium_and_do_not_invent_a_roof():
    def room(i, floor, x0, y0, x1, y1):
        return {'id': i, 'floor_id': floor, 'polygon': [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]}
    data = {'building': {'id':'atrium'},
            'floors':[{'id':'g','elevation_m':0,'height_m':4},{'id':'u','elevation_m':4,'height_m':3}],
            'spaces':[room('hall','g',0,0,10,10),room('n','u',0,0,10,2),room('s','u',0,8,10,10),
                      room('w','u',0,2,2,8),room('e','u',8,2,10,8),room('duplicate','u',0,0,10,2)],
            'assets':[],'openings':[],'vertical_connectors':[]}
    original=copy.deepcopy(data)
    slabs=compile_scene(Building(data))['slabs']
    assert {s['floor_id'] for s in slabs} == {'g','u'}
    upper=next(s for s in slabs if s['floor_id']=='u')
    triangles=[Polygon(upper['vertices'][i:i+3]) for i in range(0,len(upper['vertices']),3)]
    assert abs(sum(t.area for t in triangles)-64)<1e-8
    assert upper['area_m2']==64
    assert all(not t.covers(Point(5,5)) for t in triangles)
    assert all(t.intersection(Polygon([[2,2],[8,2],[8,8],[2,8]])).area<1e-8 for t in triangles)
    assert data==original


def test_empty_floor_has_no_inferred_surface():
    data={'building':{'id':'empty'},'floors':[{'id':'f','height_m':3}],
          'spaces':[],'assets':[],'openings':[],'vertical_connectors':[]}
    assert compile_scene(Building(data))['slabs']==[{'floor_id':'f','vertices':[],'area_m2':0.0}]
