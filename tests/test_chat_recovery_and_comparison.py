import copy
from types import SimpleNamespace as NS

import pytest

from floorwise.llm.loop import Conversation,THINKING_BINDING_BETA
from floorwise.core.analytics import item_leaders
from floorwise.core.model import Building
from floorwise.agent.session import Session
from floorwise.paths import DATA


def test_signature_recovery_keeps_words_and_tool_evidence_and_retries_once(monkeypatch):
    calls=[]
    class Rejected(Exception):
        status_code=400
        body={'error':{'message':'Invalid signature in thinking block. tools differs'}}
    def create(**arguments):
        calls.append(copy.deepcopy(arguments))
        if len(calls)==1:raise Rejected()
        return NS(content=[NS(type='text',text='Recovered')],stop_reason='end_turn',usage=NS(input_tokens=1,output_tokens=1,cache_read_input_tokens=0,cache_creation_input_tokens=0))
    monkeypatch.setattr('floorwise.llm.client',lambda _:NS(beta=NS(messages=NS(create=create))))
    c=Conversation('system',[],provider='anthropic')
    c.messages=[{'role':'user','content':'original'}, {'role':'assistant','content':[{'type':'thinking','thinking':'private','signature':'bad'},{'type':'text','text':'Five printers'}]}]
    assert c.ask('Which room has the most?')=='Recovered'
    assert len(calls)==2 and c.thinking_recoveries==1
    assert calls[0]['tools']==calls[1]['tools']
    assert THINKING_BINDING_BETA in calls[1]['betas']
    assert calls[1]['messages'][1]['content']==[{'type':'text','text':'Five printers'}]
    assert calls[1]['messages'][-1]['content']=='Which room has the most?'


def test_unrelated_provider_errors_are_not_retried(monkeypatch):
    attempts=[]
    class BadSchema(Exception):status_code=400;body={'message':'Schema is too complex'}
    def create(**args):attempts.append(1);raise BadSchema()
    monkeypatch.setattr('floorwise.llm.client',lambda _:NS(beta=NS(messages=NS(create=create))))
    c=Conversation('system',[],provider='anthropic')
    with pytest.raises(BadSchema):c.ask('Hello')
    assert len(attempts)==1 and c.messages==[]


def test_wire_sdk_sends_binding_header_and_option(monkeypatch):
    import httpx2 as httpx
    import json
    from floorwise import llm
    monkeypatch.setenv("ANTHROPIC_API_KEY","test")
    monkeypatch.delenv("FLOORWISE_OFFLINE",raising=False)
    wire=[]
    def handle(request):
        wire.append((request.headers,json.loads(request.content)))
        return httpx.Response(400,json={'type':'error','error':{'type':'invalid_request_error','message':'test only'}})
    sdk=llm.client('anthropic').with_options(max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(Exception) as rejected:
        sdk.beta.messages.create(model='claude-opus-5-5',max_tokens=10,messages=[{'role':'user','content':'test'}],
                                 thinking={'type':'adaptive','block_binding':{'prefix_mismatch_behavior':'drop_block'}},betas=[THINKING_BINDING_BETA])
    assert rejected.value.status_code==400
    assert THINKING_BINDING_BETA in wire[0][0]['anthropic-beta']
    assert wire[0][1]['thinking']['block_binding']['prefix_mismatch_behavior']=='drop_block'


def test_complete_all_type_comparison_and_floor_totals():
    b=Building.load(DATA/'dev'/'proc-campus-dev-000')
    result=item_leaders(b,compare_floor='Ground floor')
    assert result['type_count']==len({a['type'] for a in b.assets.values()})
    printers=next(r for r in result['rows'] if r['item_type']=='3d_printer')
    assert [s['total'] for s in printers['scopes']]==[8,5]
    assert [s['maximum'] for s in printers['scopes']]==[5,5]
    for row in result['rows']:
        for scope in row['scopes']:
            assert len(scope['leader_ids'])==len(scope['leaders'])
    session=Session.for_building(b)
    summary=session.rank_by_items('all')
    assert summary['type_count']==result['type_count']
    assert session.result_page(summary['result_id'])['total']==result['type_count']


def test_exterior_uses_only_closed_supplied_outline_and_recorded_height():
    from server.exterior import describe
    data={'elements':[{'type':'node','id':i,'lat':48+y,'lon':11+x} for i,(x,y) in enumerate([(0,0),(1,0),(1,1),(0,1)])]+
          [{'type':'way','id':5,'nodes':[0,1,2,3,0],'tags':{}}]}
    result=describe(data,'5')
    assert result['center']==[11.5,48.5] and result['recorded_height_m'] is None
    data['elements'][-1]['tags']['height']='12 m'
    assert describe(data,'5')['recorded_height_m']==12
    data['elements'][-1]['nodes'].pop()
    with pytest.raises(ValueError,match='closed'):describe(data,'5')


def test_real_sdk_stream_emits_text_before_final_message_and_sends_beta(monkeypatch):
    import json
    import httpx2 as httpx
    from floorwise import llm
    monkeypatch.setenv('ANTHROPIC_API_KEY','test');monkeypatch.delenv('FLOORWISE_OFFLINE',raising=False)
    seen=[];requests=[]
    def frame(kind,**data):return ('event: '+kind+'\ndata: '+json.dumps({'type':kind,**data})+'\n\n').encode()
    class Wire(httpx.SyncByteStream):
        def __iter__(self):
            yield frame('message_start',message={'id':'msg_test','type':'message','role':'assistant','content':[], 'model':'claude-opus-5-5','stop_reason':None,'stop_sequence':None,'usage':{'input_tokens':1,'output_tokens':0}})
            yield frame('content_block_start',index=0,content_block={'type':'text','text':''})
            yield frame('content_block_delta',index=0,delta={'type':'text_delta','text':'Hello'})
            assert any(kind=='assistant_delta' and data['text']=='Hello' for kind,data in seen)
            yield frame('content_block_stop',index=0)
            yield frame('message_delta',delta={'stop_reason':'end_turn','stop_sequence':None},usage={'output_tokens':1})
            yield frame('message_stop')
    def handle(request):
        requests.append(request)
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Wire())
    sdk=llm.client('anthropic').with_options(max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(llm,'client',lambda _:sdk)
    conversation=Conversation('Guide',[],provider='anthropic')
    assert conversation.ask('hello',lambda kind,data:seen.append((kind,data)))=='Hello'
    assert THINKING_BINDING_BETA in requests[0].headers['anthropic-beta']


def test_chat_rejects_empty_and_unbounded_input_and_comparison_is_a_real_api():
    from fastapi.testclient import TestClient
    from server.app import app
    c=TestClient(app);sid=c.post('/api/sessions',json={'building_id':'proc-campus-dev-000'}).json()['session_id']
    for text in ('','   ','a'*12001):assert c.post(f'/api/sessions/{sid}/chat',json={'text':text}).status_code==422
    response=c.post(f'/api/sessions/{sid}/analysis',json={'kind':'comparison','floor':'Ground floor'})
    assert response.status_code==200
    result=response.json()['result'];assert result['scope_count']==2
    card=next(e['result'] for e in response.json()['events'] if e['type']=='visual_result')
    assert card['kind']=='comparison' and 'entity_values' not in card['measurements']


def test_missing_geographic_reference_never_guesses_a_city():
    from server.exterior import exterior
    building=NS(id='swiss-fixture',info={'source':'swiss_dwellings'})
    with pytest.raises(ValueError,match='geographic source reference'):exterior(building)


def test_api_stream_has_proxy_headers_and_keeps_text_events():
    from fastapi.testclient import TestClient
    from server.app import app,SESSIONS
    client=TestClient(app);sid=client.post('/api/sessions',json={'building_id':'proc-campus-dev-000'}).json()['session_id']
    class Agent:
        turn_usage={};model='fixture';conversation=NS(last_message_id='wire')
        def ask(self,text,on_event):
            on_event('assistant_start',{'message_id':'wire','model':'fixture'})
            on_event('assistant_delta',{'message_id':'wire','text':'Hello'})
            return 'Hello'
    SESSIONS[sid]['agent']=Agent()
    response=client.post(f'/api/sessions/{sid}/chat',json={'text':'hello'})
    assert response.headers['x-accel-buffering']=='no' and 'no-transform' in response.headers['cache-control']
    assert response.text.index('assistant_delta')<response.text.index('"reply"')<response.text.index('"done"')


def test_busy_session_rejects_pointer_action_instead_of_waiting_forever():
    from fastapi.testclient import TestClient
    from server.app import app,SESSIONS
    client=TestClient(app);sid=client.post('/api/sessions',json={'building_id':'proc-campus-dev-000'}).json()['session_id']
    class BusyLock:
        def acquire(self,timeout):assert timeout==5;return False
        def release(self):pytest.fail('An unacquired lock must not be released')
    SESSIONS[sid]['lock']=BusyLock()
    response=client.post(f'/api/sessions/{sid}/analysis',json={'kind':'comparison'})
    assert response.status_code==409 and 'still running' in response.json()['detail']
