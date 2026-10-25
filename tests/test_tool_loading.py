import json
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from floorwise import llm
from floorwise.llm.loop import Conversation
from floorwise.llm.tools import tool


@pytest.mark.parametrize('provider',['anthropic','groq'])
def test_specialized_tool_executes_through_a_stable_validated_bridge(provider,monkeypatch):
    @tool
    def exact_count() -> str:
        """A deterministic fixture tool."""
        return '{"count":17}'

    conversation=None

    @tool
    def load_tools(names: list[str]) -> str:
        """Load the requested fixture tool."""
        return json.dumps({'tools':[exact_count.anthropic()]})

    @tool
    def run_tool(name:str,arguments:dict) -> str:
        from floorwise.llm.tools import call
        content,error=call({'exact_count':exact_count},name,arguments)
        assert not error
        return content

    usage=NS(input_tokens=1,output_tokens=1,cache_read_input_tokens=0,cache_creation_input_tokens=0)
    if provider=='anthropic':
        responses=[NS(usage=usage,stop_reason='tool_use',content=[NS(type='tool_use',id='a',name='load_tools',input={'names':['exact_count']})]),
                   NS(usage=usage,stop_reason='tool_use',content=[NS(type='tool_use',id='b',name='run_tool',input={'name':'exact_count','arguments':{}})]),
                   NS(usage=usage,stop_reason='end_turn',content=[NS(type='text',text='17')])]
        create=Mock(side_effect=responses)
        client=NS(beta=NS(messages=NS(create=create)))
    else:
        usage=NS(prompt_tokens=1,completion_tokens=1)
        responses=[NS(usage=usage,choices=[NS(message=NS(content='',tool_calls=[NS(id='a',function=NS(name='load_tools',arguments='{"names":["exact_count"]}'))]))]),
                   NS(usage=usage,choices=[NS(message=NS(content='',tool_calls=[NS(id='b',function=NS(name='run_tool',arguments='{"name":"exact_count","arguments":{}}'))]))]),
                   NS(usage=usage,choices=[NS(message=NS(content='17',tool_calls=[]))])]
        create=Mock(side_effect=responses)
        client=NS(chat=NS(completions=NS(create=create)))
    monkeypatch.setattr(llm,'client',lambda _:client)
    conversation=Conversation('fixture',[load_tools,run_tool],provider=provider,model='fixture')
    assert conversation.ask('count')=='17'
    schemas=[call.kwargs['tools'] for call in create.call_args_list]
    names=lambda specs:[s['name'] if provider=='anthropic' else s['function']['name'] for s in specs]
    assert all(names(schema)==['load_tools','run_tool'] for schema in schemas)
    assert all(schema==schemas[0] for schema in schemas)
