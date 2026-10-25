from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from floorwise.agent.chat import ChatAgent
from floorwise.agent.session import Session
from floorwise.core import analytics
from floorwise.core.model import Building
from floorwise.paths import DATA
from server.app import app
from floorwise.agent.local import execute_spec
from floorwise.agent.spec import QuerySpec


@pytest.fixture
def session():
    return Session.for_building(Building.load(DATA/'dev'/'proc-campus-dev-000'))


def test_complete_chair_count_rankings_and_pages(session):
    b=session.building
    result=session.count_items('chairs')
    expected=[a for a in b.assets.values() if 'chair' in a['type'].split('_') or a['type']=='armchair']
    assert result['count']==len(expected)>12
    assert sum(row['count'] for row in result['per_floor'])==len(expected)
    visual=session.visual_results[result['result_id']]
    assert {e['id'] for e in visual['entities']}=={a['id'] for a in expected}
    ranked=session.rank_by_items('chairs')
    assert ranked['rows'][0]['count']==max(sum(a['space_id']==s['id'] for a in expected) for s in analytics.rooms(b))
    all_rows=[];offset=0
    while True:
        page=session.result_page(ranked['result_id'],offset,7)
        all_rows+=page['rows']
        if page['next_offset'] is None:break
        offset=page['next_offset']
    assert len(all_rows)==ranked['total_rooms']
    assert sum(row['count'] for row in all_rows)==ranked['total_items']
    assert len({r['id'] for r in all_rows})==len(all_rows)


def test_compound_filters_use_and_and_validated_minima(session):
    b=session.building
    result=analytics.filter_rooms(b,[{'item_type':'chairs','minimum':8},{'item_type':'projector','minimum':1}])
    for row in result['rows']:
        assets=[a for a in b.assets.values() if a['space_id']==row['id']]
        assert sum(a['type'] in analytics.asset_kinds(b,'chairs') for a in assets)>=8
        assert any(a['type'] in analytics.asset_kinds(b,'projector') for a in assets)
    with pytest.raises(ValueError):analytics.filter_rooms(b,[{'item_type':'chair','minimum':-1}])
    with pytest.raises(ValueError):session.result_page('missing',-1)


def test_deterministic_helpers_remain_available_without_models(session):
    from floorwise.agent.local import dispatch
    with patch('floorwise.llm.client',side_effect=AssertionError('Helpers called a model')):
        for text in ['How many chairs are there?', 'Which room has the most chairs?',
                     'Show me all chairs on the ground floor', 'How big is Main lobby?']:
            assert dispatch(session,text)
            assert any(e['type']=='visual_result' for e in session.events)


def test_result_pages_are_session_scoped_and_bounded():
    client=TestClient(app)
    a=client.post('/api/sessions',json={'building_id':'proc-campus-dev-000'}).json()['session_id']
    c=client.post('/api/sessions',json={'building_id':'proc-campus-dev-000'}).json()['session_id']
    response=client.get(f'/api/sessions/{a}/search',params={'q':'chair'}).json()
    rid=response['result']['result_id']
    assert client.get(f'/api/sessions/{a}/results/{rid}').json()['total']>12
    assert client.get(f'/api/sessions/{c}/results/{rid}').status_code==404
    assert client.get(f'/api/sessions/{a}/results/{rid}?limit=101').status_code==422


def test_stats_preserve_total_and_source_geometry(session):
    b=session.building
    result=analytics.statistics(b)
    assert result['count']==len(analytics.rooms(b))
    assert result['total_area_m2']==round(sum(b.area(s['id']) for s in analytics.rooms(b)),2)
    assert round(sum(row['area_m2'] for row in result['rows']),1)==round(result['total_area_m2'],1)


def test_all_question_families_have_visual_contracts():
    import json
    from floorwise.agent.parse_rules import parse_rules
    seen=set()
    # Train/dev only. Test-set labels are never read or added.
    for directory in sorted((DATA/'dev').iterdir()):
        for name in ('questions.jsonl','questions_basic.jsonl'):
            path=directory/name
            if not path.exists():continue
            for line in path.read_text(encoding='utf-8').splitlines():
                row=json.loads(line);kind=row['kind']
                if kind in seen:continue
                spec=parse_rules(row['question'])
                if spec is None:continue
                current=Session.for_building(Building.load(directory))
                try:reply=execute_spec(current,spec)
                except (ValueError,KeyError):continue
                if not reply or not current.events:continue
                assert any(e['type'] in ('visual_result','route','fix_preview') for e in current.events),kind
                for event in current.events:
                    if event['type']=='visual_result':
                        result=event['result']
                        assert all(e['id'] in current.building.spaces or e['id'] in current.building.assets for e in result['entities'])
                        assert result['provenance'] and isinstance(result['measurements'],dict)
                seen.add(kind)
    assert seen=={'locate','count','route','route_step_free','route_with_closure','tour','largest_room',
                  'floor_area_total','errand','wide_delivery_count','step_free_reachable_count',
                  'room_stacked','shared_walls_count','straight_line_3d','what_if_door'}


def test_local_routes_preserve_remembered_needs_and_position(session):
    session.profile.step_free=True
    session.profile.location=session.space('Main lobby')
    declared=session.profile.location
    execute_spec(session,QuerySpec(kind='route',start='Main lobby',destination='Meeting room 1.10',step_free=False))
    assert session.profile.location==declared
    assert 'step-free' in session.last_route.constraints


def test_configured_pricing_and_per_turn_zero_usage(session,monkeypatch):
    from floorwise.llm.pricing import estimate
    assert estimate([{'model':'unknown','usage':{'input_tokens':10}}]) is None
    monkeypatch.setenv('FLOORWISE_MODEL_PRICES_JSON','{"fixture":{"input":2,"output":4,"cache_read":0.2,"cache_write":2.5}}')
    assert estimate([{'model':'fixture','usage':{'input_tokens':1000,'output_tokens':100,'cache_read_input_tokens':1000}}])==.0026


def test_chat_without_key_reports_error_and_completes_stream(monkeypatch):
    for name in ('ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','GROQ_API_KEY','OPENROUTER_API_KEY','FLOORWISE_ANTHROPIC_PROFILE','FLOORWISE_PROVIDER'):
        monkeypatch.delenv(name,raising=False)
    client=TestClient(app)
    sid=client.post('/api/sessions',json={'building_id':'proc-campus-dev-000'}).json()['session_id']
    response=client.post(f'/api/sessions/{sid}/chat',json={'text':'Which room has the most chairs?'})
    assert response.status_code==200
    assert '"type": "error"' in response.text
    assert '"type": "done"' in response.text
    assert '"dispatch": "deterministic"' not in response.text


def test_selected_room_and_single_result_support_follow_up_without_a_model(session):
    from floorwise.agent.local import dispatch
    sid=session.space('Main lobby')
    session.ui_selection=sid
    assert str(round(session.building.area(sid),2)) in dispatch(session,'How big is this room?')
    session.ui_selection=None
    assert str(round(session.building.area(sid),2)) in dispatch(session,'How big is it?')


def test_item_ranking_reports_all_top_ties(session):
    import copy
    data=copy.deepcopy(session.building.data)
    destinations=analytics.rooms(session.building)[:2]
    data['assets']=[{'id':f'item-{i}-{j}','type':'chair','space_id':s['id'],'floor_id':s['floor_id']}
                    for i,s in enumerate(destinations) for j in range(2)]
    ranked=analytics.rank_by_items(Building(data),'chairs')
    assert ranked['top_ties']==2 and ranked['total_items']==4
    assert [r['count'] for r in ranked['rows'][:2]]==[2,2]


def test_incomplete_parser_result_is_not_executed(session):
    assert execute_spec(session,QuerySpec(kind='step_free_reachable_count',closed='Lift 1')) is None
    assert not session.events and not session.closed


def test_parser_width_is_applied_instead_of_silently_dropped(session):
    reply=execute_spec(session,QuerySpec(kind='route',start='Main lobby',destination='Print room 0.16',min_width=1.1,step_free=True))
    assert reply and any(e['type']=='fix_preview' for e in session.events)


def test_benchmark_tool_counts_keep_exact_item_semantics(session):
    import json
    from floorwise.agent.tools import make_tools
    tools={t.name:t for t in make_tools(session,allow_edits=False,exact_items=True)}
    result=json.loads(tools['count_items'].fn('chair'))
    assert result['count']==sum(a['type']=='chair' for a in session.building.assets.values())
    assert result['scope']=='exact item type'
    assert session.count_items('chairs')['count']>=result['count']
