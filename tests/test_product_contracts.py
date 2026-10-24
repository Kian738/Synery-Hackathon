"""Regression evidence across model transport, result storage, Lab and source contracts."""
import json
import threading
from collections import Counter
from contextlib import contextmanager
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from floorwise.agent.chat import ChatAgent
from floorwise.agent.session import Session
from floorwise.core.model import Building
from floorwise.paths import DATA
from server.app import app, SESSIONS


@pytest.fixture
def session():return Session.for_building(Building.load(DATA/'dev'/'proc-campus-dev-000'))


def test_count_groups_are_complete_paged_and_immutable(session):
    result=session.count_items('3d printer')
    rid=result['result_id']
    rooms=session.result_page(rid,view='rooms')
    assert sum(r['count'] for r in rooms['rows'])==8
    assert sorted(r['count'] for r in rooms['rows'])==[1,1,1,5]
    room=next(r for r in rooms['rows'] if r['count']==5)
    assert session.result_page(rid,view='items',room=room['id'])['total']==5
    chairs=session.count_items('chair')
    page=session.result_page(chairs['result_id'],limit=2,view='rooms')
    assert len(page['rows'])==2 and page['total']>12 and page['next_offset']==2
    assert session.result_page(rid,view='rooms')==rooms
    with pytest.raises(ValueError):session.result_page(rid,view='bogus')


def test_result_read_does_not_wait_for_chat_lock():
    client=TestClient(app);sid=client.post('/api/sessions',json={'building_id':'proc-campus-dev-000'}).json()['session_id']
    entry=SESSIONS[sid];rid=entry['session'].count_items('3d printer')['result_id']
    acquired=threading.Event();release=threading.Event()
    def hold():
        with entry['lock']:acquired.set();release.wait(5)
    worker=threading.Thread(target=hold);worker.start();acquired.wait(2)
    try:
        response=client.get(f'/api/sessions/{sid}/results/{rid}?view=rooms')
        assert response.status_code==200 and response.json()['total']==4
        assert worker.is_alive()
    finally:release.set();worker.join()


def test_normal_chat_streams_tools_then_answer_without_regex(monkeypatch,session):
    calls=[]
    class Stream:
        def __init__(self,arguments):self.arguments=arguments;calls.append(arguments)
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def __iter__(self):
            yield NS(type='content_block_delta',delta=NS(type='text_delta',text='Checking.' if len(calls)==1 else 'Eight printers in four rooms.'))
        def get_final_message(self):
            content=[NS(type='tool_use',id='count-1',name='count_items',input={'item_type':'3d printer'})] if len(calls)==1 else [NS(type='text',text='Eight printers in four rooms.')]
            return NS(content=content,stop_reason='tool_use' if len(calls)==1 else 'end_turn',usage=NS(input_tokens=10,output_tokens=10,cache_read_input_tokens=0,cache_creation_input_tokens=0))
    client=NS(beta=NS(messages=NS(stream=lambda **kwargs:Stream(kwargs))))
    monkeypatch.setattr('floorwise.llm.client',lambda provider:client)
    monkeypatch.setattr('floorwise.agent.local.dispatch',lambda *args:pytest.fail('Regex dispatch reached'))
    agent=ChatAgent(session,provider='anthropic');events=[]
    reply=agent.ask('How many 3d printers and where?',lambda kind,data:events.append((kind,data)))
    assert reply=='Eight printers in four rooms.'
    assert len(calls)==2 and 'output_format' not in calls[0]
    assert all(not tool.get('strict') for tool in calls[0]['tools'])
    assert sum(kind=='tool' for kind,_ in events)==1
    assert sum(kind=='assistant_start' for kind,_ in events)==2
    assert any(kind=='assistant_delta' for kind,_ in events)
    assert any(kind=='ui' and data['type']=='visual_result' for kind,data in events)
    assert agent.turn_usage['input_tokens']==20


def test_bad_tool_inputs_cannot_execute():
    from floorwise.llm.tools import tool,call
    seen=[]
    @tool
    def record(quantity:int)->str:seen.append(quantity);return 'ok'
    for arguments in ({'quantity':'not a number'},{'quantity':1,'surprise':True},'{broken'):
        result,error=call({'record':record},'record',arguments)
        assert error and not seen
    assert call({'record':record},'record',{'quantity':3})==('ok',False)
    assert seen==[3]


def test_tool_schemas_stay_identical_after_specialized_tool_discovery(monkeypatch,session):
    monkeypatch.setattr('floorwise.llm.client',lambda provider:object())
    agent=ChatAgent(session,provider='anthropic')
    agent._prepare_conversation('hello')
    before=[t.anthropic() for t in agent.conversation.tools]
    from floorwise.llm.tools import call
    result,error=call(agent.conversation.by_name,'load_tools',{'names':['stacked_room','add_door']})
    assert not error and 'run_tool' in result
    agent._prepare_conversation('closed lift and room above')
    assert [t.anthropic() for t in agent.conversation.tools]==before


def test_openai_compatible_stream_accumulates_tool_json_before_execution(monkeypatch,session):
    calls=[]
    class Stream:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def __iter__(self):
            if len(calls)==1:
                yield NS(usage=None,choices=[NS(delta=NS(content=None,tool_calls=[NS(index=0,id='count',function=NS(name='count_items',arguments='{"item_type":'))]))])
                assert not session.visual_results
                yield NS(usage=None,choices=[NS(delta=NS(content=None,tool_calls=[NS(index=0,id=None,function=NS(name=None,arguments='"3d printer"}'))]))])
            else:yield NS(usage=None,choices=[NS(delta=NS(content='Eight printers.',tool_calls=[]))])
            yield NS(usage=NS(prompt_tokens=10,completion_tokens=5),choices=[])
    def create(**kwargs):calls.append(kwargs);return Stream()
    monkeypatch.setattr('floorwise.llm.client',lambda provider:NS(chat=NS(completions=NS(create=create))))
    agent=ChatAgent(session,provider='groq');events=[]
    assert agent.ask('How many 3d printers and where?',lambda k,d:events.append((k,d)))=='Eight printers.'
    assert session.result_page(next(iter(session.visual_results)),view='rooms')['total']==4
    assert agent.turn_usage['input_tokens']==20 and any(k=='assistant_delta' for k,_ in events)


def test_scenario_requires_explicit_inputs_and_does_not_mutate_building(session):
    from floorwise.agent.scenarios import simulate
    from copy import deepcopy
    before=deepcopy(session.building.data)
    with pytest.raises(ValueError):simulate(session,{},20)
    with pytest.raises(ValueError):simulate(session,{'Main lobby':20},0)
    result=simulate(session,{'Main lobby':20},20)
    assert result['evacuated']+result['stranded']==20
    assert result['baseline_s']>=0 and result['assumptions']
    assert session.building.data==before and not session.edits


def test_readiness_does_not_relabel_old_or_known_misses_as_current_pass(monkeypatch):
    from server import readiness
    current={'version':1,'source':'new','dataset':'kit','frontend':'web','provider':'fixture','models':{},'effort':'low'}
    monkeypatch.setattr(readiness,'fingerprint',lambda:current)
    historical={'suite':'e2e','correct':99,'total':100,'accuracy':.99,'known_failures':1,'fingerprint':{**current,'source':'old'}}
    report=readiness.readiness([historical])
    benchmark=next(r for r in report['requirements'] if r['id']=='benchmark')
    assert benchmark['status']=='historical' and benchmark['latest']['correct']==99
    assert sum(g['points'] for g in report['groups'])==100
    historical['fingerprint']=current;historical['accuracy']=.8
    assert next(r for r in readiness.readiness([historical])['requirements'] if r['id']=='benchmark')['status']=='fail'


def test_pack_has_24_cases_three_repeats_three_demos():
    from eval.conversations import cases
    catalog=cases();assert len(catalog)==30 and len({c['id'] for c in catalog})==30
    assert Counter(c['family'] for c in catalog)=={'equipment':4,'context':4,'routing':4,'spatial':4,'interventions':4,'limits':4,'regression repeat':3,'demo':3}
    assert all(c['turns'] and c['expected'] for c in catalog)


def test_submission_contract_uses_every_public_id_once():
    import csv
    from floorwise.paths import ROOT
    expected={json.loads(line)['id'] for p in (DATA/'test').glob('*/questions.jsonl') for line in p.read_text(encoding='utf8').splitlines() if line.strip()}
    path=ROOT/'submissions/team_floorwise_test.csv'
    with path.open(encoding='utf8',newline='') as stream:
        reader=csv.DictReader(stream);assert reader.fieldnames==['question_id','answer'];rows=list(reader)
    assert len(rows)==len(expected)==145 and {r['question_id'] for r in rows}==expected
    assert all('Answer:' in r['answer'] for r in rows) and path.stat().st_size<5_000_000


def test_exact_equipment_type_and_assumed_origin_remain_distinct():
    from floorwise.agent.session import Session
    from floorwise.core.model import Building
    s=Session.for_building(Building.load(DATA/'dev'/'proc-campus-dev-000'))
    normal={a['space_id'] for a in s.building.assets.values() if a['type']=='printer'}
    selected=s.place('printer',near=s.default_start)
    assert normal and selected in normal
    s.profile.location=s.default_start;s.profile.location_source='default'
    result=s.route('', 'Makerspace 0.08')
    assert 'assumed_start' in result and 'equipment position' in result['destination_basis']
    s.profile.location_source='declared'
    assert 'assumed_start' not in s.route('', 'Makerspace 0.08')


def test_readiness_distinguishes_safe_previews_from_navigation_coverage(monkeypatch):
    from server import readiness
    current={'version':1,'source':'source','dataset':'kit','frontend':'web','provider':'fixture','models':{},'effort':'low'}
    monkeypatch.setattr(readiness,'fingerprint',lambda:current)
    sample={'suite':'walls','correct':10,'total':10,'accuracy':1.,'fingerprint':current,
            'navigation':{'sampled':10,'safe':8,'emitted':8,'unavailable':1,'withheld':1}}
    assert next(r for r in readiness.readiness([sample])['requirements'] if r['id']=='walls')['status']=='limited'
    unrelated={'suite':'browser','accuracy':1.,'fingerprint':current,'coverage':{'passed':['unrelated browser case'],'failed':[]}}
    assert all(f['status']!='verified and visible' for f in readiness.features([unrelated]))
