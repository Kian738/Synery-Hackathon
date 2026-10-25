import copy
import json

from floorwise.agent.session import Session
from floorwise.agent.tools import make_tools
from floorwise.cli import structured
from floorwise.agent.answer import answer_with_trace
from floorwise.core.model import Building
from floorwise.core.scene import compile_scene
from floorwise.paths import DATA
from eval.differential import compare_building


def test_scene_compiler_cuts_only_the_nearest_wall_at_a_corner():
    data = {'building': {'id': 'fixture'}, 'floors': [{'id':'f','height_m':3.4}],
            'spaces': [{'id':'s','floor_id':'f','polygon':[[0,0],[4,0],[4,4],[0,4]]}],
            'openings': [{'id':'o','space_ids':['s','outside'],'position':[0.2,0],'width_m':0.9}],
            'vertical_connectors':[], 'assets':[]}
    original = copy.deepcopy(data)
    scene = compile_scene(Building(data))
    assert not scene['unmatched_openings']
    assert all(w['height_m'] == 3.4 for w in scene['walls'])
    # The adjacent vertical wall remains continuous even though it is close to the door.
    assert any(w['a'] == [0,4] and w['b'] == [0,0] for w in scene['walls'])
    assert data == original
    data['openings'][0]['width_m'] = 1.2
    assert compile_scene(Building(data))['revision'] != scene['revision']


def test_analytical_tools_match_core_and_do_not_apply_what_ifs():
    b = Building.load(DATA/'dev'/'proc-campus-dev-000')
    session = Session.for_building(b)
    tools = {t.name:t for t in make_tools(session)}
    result = json.loads(tools['count_items'].fn('desk', 'ground floor'))
    assert result['count'] == sum(a['type']=='desk' and b.level(a['floor_id'])==0 for a in b.assets.values())
    places = json.loads(tools['find_places'].fn(room_type='office', contains_item='coffee machine'))
    assert places['total'] == 0
    before = copy.deepcopy(session.building.data)
    tools['distance_3d'].fn('Main lobby', 'Print room 0.16')
    assert session.building.data == before


def test_benchmark_output_includes_exact_ordered_route_nodes():
    directory = DATA/'dev'/'proc-campus-dev-000'
    reply, trace = answer_with_trace(directory, 'How do I get from Main lobby (Ground floor) to Print room 0.16 (Ground floor)?')
    output = structured('fixture',reply,trace)
    assert output['route_nodes'][0] == trace['result']['stops'][0]
    assert output['route_nodes'][-1] == trace['result']['stops'][-1]
    assert any(n.startswith('door:') for n in output['route_nodes'])


def test_closure_router_matches_independent_official_implementation():
    b=Building.load(DATA/'dev'/'proc-campus-dev-000')
    rows=compare_building(b,pairs=2,closures=2)
    # The evaluator now includes two complete-graph comparisons in addition to
    # the twelve sampled closure routes. Keep both obligations explicit.
    assert len([row for row in rows if row.get('kind') == 'graph equality']) == 2
    assert len([row for row in rows if row.get('kind') != 'graph equality']) == 12
    assert all(row['correct'] for row in rows)
