from shapely.geometry import LineString, Polygon

from floorwise.core.model import Building
from floorwise.core.walk_domain import repair_nested_crossings


def test_hallway_path_does_not_cross_an_enclosed_stairwell():
    outer=[[0,0],[12,0],[12,8],[0,8]];inner=[[5,2],[7,2],[7,6],[5,6]]
    b=Building({'building':{'id':'nested'},'floors':[{'id':'g','level':0,'height_m':3}],
                'spaces':[{'id':'hall','type':'corridor','floor_id':'g','polygon':outer},
                          {'id':'stairs','type':'stair','floor_id':'g','polygon':inner}],
                'assets':[],'openings':[],'vertical_connectors':[]})
    path=repair_nested_crossings(b,'hall',[(1,4),(11,4)],False,False)
    assert path[0]==(1,4) and path[-1]==(11,4)
    assert not LineString(path).intersects(Polygon(inner))
    assert Polygon(outer).covers(LineString(path))
    assert len(path)==4


def test_a_clear_path_is_unchanged():
    b=Building({'building':{'id':'clear'},'floors':[{'id':'g','level':0,'height_m':3}],
                'spaces':[{'id':'hall','type':'corridor','floor_id':'g','polygon':[[0,0],[12,0],[12,8],[0,8]]}],
                'assets':[],'openings':[],'vertical_connectors':[]})
    path=[(1,1),(11,1)]
    assert repair_nested_crossings(b,'hall',path,False,False)==path
