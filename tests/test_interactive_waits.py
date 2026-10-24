from types import SimpleNamespace
from collections import Counter
from unittest.mock import patch

import pytest

from floorwise.llm import budget
from floorwise.agent.chat import ChatAgent
from floorwise.agent.session import Session
from floorwise.core.model import Building
from floorwise.paths import DATA


def test_interactive_timeouts_do_not_change_benchmark_defaults(monkeypatch):
    monkeypatch.setenv('FLOORWISE_LLM_TIMEOUT_S','90')
    class Agent:
        benchmark=False
        @budget.interactive_turn
        def request(self):
            assert 0<budget.timeout_s()<=25
            assert budget.retries()==0
    Agent().request()
    assert budget.timeout_s()==90
    assert budget.retries()==1


def test_total_deadline_is_checked_before_another_model_call(monkeypatch):
    clock=[10.]
    monkeypatch.setattr(budget.time,'monotonic',lambda:clock[0])
    monkeypatch.setenv('FLOORWISE_CHAT_DEADLINE_S','30')
    class Agent:
        benchmark=False
        @budget.interactive_turn
        def request(self):
            clock[0]=39
            assert budget.timeout_s()==1
            clock[0]=41
            with pytest.raises(TimeoutError):budget.check()
    Agent().request()


def test_unknown_conversation_still_reaches_the_model_instead_of_a_canned_greeting(monkeypatch):
    building=Building.load(DATA/'dev'/'proc-campus-dev-000')
    agent=ChatAgent(Session.for_building(building))
    monkeypatch.setattr('floorwise.agent.chat.llm.info',lambda:SimpleNamespace(available=False))
    class Conversation:
        provider='fixture';model='model';usage=Counter()
        def ask(self,text,on_event=None):
            assert text.startswith('hello')
            return 'Real model response fixture'
    agent.conversation=Conversation()
    monkeypatch.setattr(agent,'_prepare_conversation',lambda text:None)
    assert agent.ask('hello')=='Real model response fixture'


def test_common_count_commands_do_not_need_a_model():
    building=Building.load(DATA/'dev'/'proc-campus-dev-000')
    agent=ChatAgent(Session.for_building(building))
    with patch('floorwise.llm.client',side_effect=AssertionError('Unexpected model call')):
        answer=agent.ask('Count all chairs in the building')
    assert 'chair' in answer
    assert agent.turn_usage['dispatch']=='deterministic'


def test_claude_transport_requires_fields_without_changing_parser_defaults():
    from floorwise.agent.parse_llm import WireQuery
    from floorwise.llm.structured import required_transport_schema
    schema=required_transport_schema(WireQuery)
    wire=schema.model_json_schema()
    assert set(wire['required'])==set(wire['properties'])
    assert WireQuery(kind='other').floor==''
    original=WireQuery(kind='route',start='A',destination='B',stairs_allowed=False)
    assert WireQuery.model_validate(schema.model_validate(original.model_dump()).model_dump())==original


@pytest.mark.parametrize('provider',['anthropic','groq'])
def test_failed_model_turn_does_not_poison_next_request(monkeypatch,provider):
    from floorwise.llm.loop import Conversation
    monkeypatch.setattr('floorwise.llm.client',lambda provider:object())
    conversation=Conversation('system',[],provider=provider)
    conversation.messages=[{'role':'user','content':'prior'},{'role':'assistant','content':'answer'}]
    def fail(self,event):
        self.messages.append({'role':'assistant','content':'incomplete tool call'})
        raise TimeoutError('fixture timeout')
    method='_anthropic' if provider=='anthropic' else '_openai'
    monkeypatch.setattr(Conversation,method,fail)
    with pytest.raises(TimeoutError):conversation.ask('hello')
    assert len(conversation.messages)==2
    monkeypatch.setattr(Conversation,method,lambda self,event:'recovered')
    assert conversation.ask('retry')=='recovered'
    assert conversation.messages[-1]['content']=='retry'


def test_chat_failure_ends_stream_and_session_can_retry(monkeypatch):
    import json
    from fastapi.testclient import TestClient
    from server.app import app
    client=TestClient(app)
    sid=client.post('/api/sessions',json={'building_id':'proc-campus-dev-000'}).json()['session_id']
    def fail(self,text,on_event=None):
        if on_event:on_event('progress',{'stage':'model','message':'Waiting for Claude'})
        raise TimeoutError('fixture timeout')
    monkeypatch.setattr(ChatAgent,'ask',fail)
    def events():
        response=client.post(f'/api/sessions/{sid}/chat',json={'text':'hello'})
        return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    first=events()
    assert first[0]['type']=='progress'
    assert first[-1]['type']=='done'
    assert 'timed out' in next(e['data']['message'] for e in first if e['type']=='error')
    monkeypatch.setattr(ChatAgent,'ask',lambda self,text,on_event=None:'recovered from real agent fixture')
    second=events()
    assert any(e['type']=='reply' for e in second)
    assert second[-1]['type']=='done'
