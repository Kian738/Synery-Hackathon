import pytest
from floorwise.core.model import Building
from floorwise.core.connectors import inventory
from floorwise.agent.session import Session
from floorwise.paths import DATA


def test_inventory_counts_connectors_once_and_distinguishes_containment_access_and_touching():
    floors=[{'id':f'f{i}','name':f'Floor {i}','level':i} for i in range(2)]
    def space(id,f,poly):return {'id':id,'name':id,'floor_id':f,'type':'stair','room_type':'stairwell','polygon':poly,'ref':id}
    spaces=[space('hall','f0',[[0,0],[10,0],[10,10],[0,10]])]
    shapes=[[[1,1],[3,1],[3,3],[1,3]],[[10,1],[12,1],[12,3],[10,3]],[[0,10],[2,10],[2,12],[0,12]]]
    connectors=[]
    for i,poly in enumerate(shapes):
        spaces.extend([space(f's{i}-{f}',f'f{f}',poly) for f in range(2)])
        connectors.append({'id':f'c{i}','name':f'Stairs {i}','kind':'stairs','floor_ids':['f0','f1'],'space_ids':[f's{i}-0',f's{i}-1']})
    b=Building({'building':{'id':'fixture'},'floors':floors,'spaces':spaces,'assets':[],'vertical_connectors':connectors,'openings':[{'id':'d','floor_id':'f0','space_ids':['hall','s1-0']}]})
    result=inventory(b,room='hall')
    assert result['count']==2
    assert {r['stops'][0]['relation'] for r in result['rows']}=={'inside_room_footprint','direct_opening'}
    assert inventory(b)['count']==3
    assert [f['count'] for f in inventory(b)['per_floor']]==[3,3]
    assert inventory(b)['individual_step_count'] is None


def test_reported_main_hall_has_two_connections_not_the_building_total():
    b=Building.load(DATA/'dev'/'osm-way27917482');session=Session.for_building(b)
    hall=next(s for s in b.spaces.values() if s['name']=='MI Magistrale')
    assert inventory(b,room=hall['id'])['count']==2
    assert inventory(b)['count']==25
    assert inventory(b,'elevators')['count']==7
    info=session.room_info(hall['id'])
    assert info['door_count']>12 and info['door_examples_only']
    assert info['connector_access']['count']==2
    counted=session.count_items('staircases',room=hall['id'])
    assert counted['count']==2 and counted['domain']=='connectors'
    assert len(session.visual_results[counted['result_id']]['rows'])==2
    with pytest.raises(ValueError):session.count_items('staircases',room=hall['id'],exact=True)
