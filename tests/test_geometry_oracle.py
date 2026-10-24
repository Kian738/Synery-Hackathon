import pytest
from eval.geometry_oracle import moments
from floorwise.core.model import Building
from floorwise.core import geometry,ops


def test_concave_centroid_wall_and_stacking_hand_case():
    shape=[[0,0],[4,0],[4,1],[1,1],[1,4],[0,4]]
    floors=[{'id':'g','level':0,'elevation_m':0,'height_m':3},{'id':'u','level':1,'elevation_m':3,'height_m':3}]
    def room(sid,floor,poly,kind='room'):return {'id':sid,'name':sid,'floor_id':floor,'type':kind,'room_type':'office','polygon':poly}
    b=Building({'building':{'id':'independent'},'floors':floors,'spaces':[room('a','g',shape),room('b','g',[[4,0],[6,0],[6,1],[4,1]]),room('up','u',shape)],'openings':[],'assets':[],'vertical_connectors':[]})
    area,centroid=moments(shape)
    assert area==7 and centroid==pytest.approx((19/14,19/14))
    assert geometry.area(b,'a')==7
    assert geometry.centroid_3d(b,'a')==pytest.approx((19/14,19/14,0))
    assert geometry.distance_3d(b,'a','up')==3
    assert {sid for sid,_ in geometry.wall_neighbours(b,'a')}=={'b'}
    from shapely.geometry import Point
    assert not b.polygons['a'].covers(Point(*centroid))  # centroid must never become a walking anchor
    assert b.polygons['a'].covers(b.polygons['a'].representative_point())
