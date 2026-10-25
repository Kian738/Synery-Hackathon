import json,shutil,subprocess,copy
import pytest
from shapely.geometry import Polygon,MultiPoint
from floorwise.core.model import Building
from floorwise.core.stair_scene import compile_stair_shafts,fitted_rectangle
from floorwise.core.scene import compile_scene
from floorwise.paths import DATA,ROOT


def test_concave_footprint_is_not_replaced_by_a_room_crossing_bounding_box():
    shape=Polygon([(0,0),(8,0),(8,3),(3,3),(3,8),(0,8)])
    fitted=fitted_rectangle(shape,[shape])
    assert fitted and shape.covers(Polygon(fitted))
    assert not shape.covers(shape.minimum_rotated_rectangle)
    assert fitted_rectangle(Polygon([(20,20),(21,20),(21,21),(20,21)]).intersection(shape),[shape]) is None


@pytest.mark.parametrize('building_id',['osm-way27326387','osm-way27917482'])
def test_every_stair_mesh_part_stays_inside_both_supplied_floor_shafts(building_id):
    node=shutil.which('node')
    if not node:pytest.skip('Node runtime unavailable')
    building=Building.load(DATA/'dev'/building_id);before=copy.deepcopy(building.data)
    shafts=compile_stair_shafts(building.data)
    assert building.data==before
    assert all(s['footprint'] for s in shafts)
    if building_id=='osm-way27326387':
        assert len(shafts)==2 and shafts[0]['footprint']==shafts[1]['footprint']
        assert all(s['basis']=='common_all_stops' for s in shafts)
    proc=subprocess.run([node,'--experimental-strip-types','web/tests/stair-shaft-contracts.mjs'],cwd=ROOT,input=json.dumps({'data':building.data,'shafts':shafts}),capture_output=True,text=True,timeout=45)
    assert proc.returncode==0,proc.stderr
    meshes=json.loads(proc.stdout)
    assert len(meshes)==len(shafts)
    for mesh in meshes:
        for points in mesh['footprints']:
            footprint=MultiPoint(points).convex_hull
            for sid in (mesh['lower'],mesh['upper']):
                owner=building.spaces[sid];polygon=Polygon(owner['polygon'])
                assert polygon.buffer(1e-7).covers(footprint),(building_id,sid,footprint.wkt)
                if building_id=='osm-way27326387':
                    for other in building.spaces.values():
                        if other['floor_id']==owner['floor_id'] and other['id']!=sid:
                            assert footprint.intersection(Polygon(other['polygon'])).area<1e-6,(sid,other['id'])
    assert compile_scene(building)['stair_shafts']==shafts


def test_disjoint_floor_frames_withhold_a_flight_instead_of_spanning_other_rooms():
    data={'floors':[{'id':'a','level':0},{'id':'b','level':1}],
          'spaces':[{'id':'s0','polygon':[[0,0],[4,0],[4,4],[0,4]]},{'id':'s1','polygon':[[10,10],[14,10],[14,14],[10,14]]}],
          'vertical_connectors':[{'id':'c','kind':'stairs','floor_ids':['a','b'],'space_ids':['s0','s1']}]}
    result=compile_stair_shafts(data)
    assert len(result)==1 and result[0]['footprint'] is None and result[0]['warning']
