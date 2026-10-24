import math

from shapely.geometry import LineString

from floorwise.core.model import Building
from floorwise.core.graph import Constraints
from floorwise.core.routing import plan_route
from floorwise.core.walk import corridor_spine
from floorwise.paths import DATA


def test_cit_route_does_not_trap_start_in_diagonal_only_grid_region():
    building=Building.load(DATA/'dev'/'osm-way27917482')
    route=plan_route(building,['osm-way27917482-F3-S069','osm-way27917482-F0-S332'],Constraints(),humane=True)
    assert route.preview_available and route.walk_m is not None
    assert route.floors[0].endswith('F3') and route.floors[-1].endswith('F0')
    assert all(p['node']!='outside' for p in route.polyline)


def test_rotated_empty_corridor_has_one_straight_central_run():
    angle=math.radians(11)
    def rotate(p):return [p[0]*math.cos(angle)-p[1]*math.sin(angle),p[0]*math.sin(angle)+p[1]*math.cos(angle)]
    data={'building':{'id':'fixture'},'floors':[{'id':'f','level':0,'elevation_m':0}],
          'spaces':[{'id':'corridor','floor_id':'f','type':'corridor','polygon':[rotate(p) for p in [(0,0),(2,0),(2,30),(0,30)]]}],
          'assets':[],'openings':[],'vertical_connectors':[]}
    building=Building(data)
    points=corridor_spine(building,'corridor',rotate((1.95,3)),rotate((1.95,27)))
    assert len(points)==4
    central=(points[2][0]-points[1][0],points[2][1]-points[1][1])
    axis=(-math.sin(angle),math.cos(angle))
    assert abs(central[0]*axis[1]-central[1]*axis[0])<1e-8
    assert building.polygons['corridor'].buffer(.02).covers(LineString(points))
    data['assets']=[{'id':'obstacle','space_id':'corridor','category':'furniture'}]
    assert corridor_spine(Building(data),'corridor',rotate((1.95,3)),rotate((1.95,27))) is None
