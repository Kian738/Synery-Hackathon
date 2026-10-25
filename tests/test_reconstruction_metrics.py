import copy
import pytest
from eval.reconstruction import measure,quality


def fixture():
    return {'building':{'id':'metric'},'floors':[{'id':'g','level':0},{'id':'u','level':1}],
        'spaces':[{'id':'a','floor_id':'g','type':'room','name':'A','room_type':'office','polygon':[[0,0],[4,0],[4,4],[0,4]]},
                  {'id':'b','floor_id':'u','type':'room','name':'B','room_type':'office','polygon':[[0,0],[4,0],[4,4],[0,4]]}],
        'openings':[{'id':'exit','floor_id':'g','space_ids':['a','outside'],'position':[0,2],'step_free':True}],
        'vertical_connectors':[{'id':'lift','kind':'lift','floor_ids':['g','u'],'space_ids':['a','b'],'step_free':True}],'assets':[]}


def test_upper_floor_without_entrance_is_not_an_isolated_floor_failure():
    source=fixture();predicted=copy.deepcopy(source)
    m=measure(source,predicted)
    assert quality(m,complete=True)
    assert m['exit_reachability_agreement']==1
    assert m['door_precision']==1


def test_missing_lift_fails_building_reachability():
    source=fixture();predicted=copy.deepcopy(source);predicted['vertical_connectors']=[]
    m=measure(source,predicted)
    assert not quality(m,complete=True)
    assert m['exit_reachability_agreement']==.5
    assert m['false_disconnected_pairs']==1


def test_false_bridge_cannot_improve_a_disconnected_model_into_a_pass():
    source=fixture();source['vertical_connectors']=[]
    predicted=fixture()
    m=measure(source,predicted)
    assert m['false_connected_pairs']==1
    assert m['false_exit_access']==1
    assert not quality(m,complete=True)


def test_opening_matches_are_one_to_one_and_invented_doors_reduce_precision():
    source=fixture();source['openings'].append({**source['openings'][0],'id':'another'})
    predicted=fixture()
    m=measure(source,predicted)
    assert m['doors_matched']==1 and m['door_recall']==.5
    m=measure(predicted,source)
    assert m['door_precision']==.5 and len(m['invented_doors'])==1


def test_duplicate_regions_reduce_precision_without_stealing_valid_match():
    source=fixture();predicted=copy.deepcopy(source)
    # Keep the two floors spatially separate for the unambiguous match fixture.
    source['spaces'][1]['polygon']=[[10,0],[14,0],[14,4],[10,4]]
    predicted['spaces'][1]['polygon']=source['spaces'][1]['polygon']
    predicted['spaces'].append({**predicted['spaces'][0],'id':'duplicate'})
    m=measure(source,predicted)
    assert m['room_recall']==1 and m['room_precision']==pytest.approx(2/3)
    assert not quality(m)


def test_identical_stacked_outlines_match_only_the_same_floor():
    source=fixture();predicted=copy.deepcopy(source)
    predicted['spaces'].reverse()
    m=measure(source,predicted)
    assert m['matched_spaces']=={'a':'a','b':'b'}
