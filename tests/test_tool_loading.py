from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from floorwise import llm
from floorwise.llm.loop import Conversation
from floorwise.llm.tools import tool


@pytest.mark.parametrize('provider',['anthropic','groq'])
def test_new_tool_schema_is_available_on_next_loop_step(provider,monkeypatch):
    @tool
    def exact_count() -> str:
        """A deterministic fixture tool."""
        return '{"count":17}'

    conversation=None

    @tool
    def load_tools(names: list[str]) -> str:
        """Load the requested fixture tool."""
        conversation.tools.append(exact_count)
        conversation.by_name['exact_count']=exact_count
        return 'enabled'

    usage=NS(input_tokens=1,output_tokens=1,cache_read_input_tokens=0,cache_creation_input_tokens=0)
    if provider=='anthropic':
        responses=[NS(usage=usage,stop_reason='tool_use',content=[NS(type='tool_use',id='a',name='load_tools',input={'names':['exact_count']})]),
                   NS(usage=usage,stop_reason='tool_use',content=[NS(type='tool_use',id='b',name='exact_count',input={})]),
                   NS(usage=usage,stop_reason='end_turn',content=[NS(type='text',text='17')])]
        create=Mock(side_effect=responses)
        client=NS(beta=NS(messages=NS(create=create)))
    else:
        usage=NS(prompt_tokens=1,completion_tokens=1)
        responses=[NS(usage=usage,choices=[NS(message=NS(content='',tool_calls=[NS(id='a',function=NS(name='load_tools',arguments='{"names":["exact_count"]}'))]))]),
                   NS(usage=usage,choices=[NS(message=NS(content='',tool_calls=[NS(id='b',function=NS(name='exact_count',arguments='{}'))]))]),
                   NS(usage=usage,choices=[NS(message=NS(content='17',tool_calls=[]))])]
        create=Mock(side_effect=responses)
        client=NS(chat=NS(completions=NS(create=create)))
    monkeypatch.setattr(llm,'client',lambda _:client)
    conversation=Conversation('fixture',[load_tools],provider=provider,model='fixture')
    assert conversation.ask('count')=='17'
    schemas=[call.kwargs['tools'] for call in create.call_args_list]
    names=lambda specs:[s['name'] if provider=='anthropic' else s['function']['name'] for s in specs]
    assert names(schemas[0])==['load_tools']
    assert 'exact_count' in names(schemas[1])
