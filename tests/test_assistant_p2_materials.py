from types import SimpleNamespace
from shiliu.assistant.knowledge_write import prepare_materials
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.sources import SourceScope


def test_materials_keep_actual_wiki_and_external_read_bodies():
    wiki={'items':[{'id':'page','version':1,'evidence_ref':'wiki:page:1','blocks':[{'markdown':'真实正文'}]}]}
    external={'result_ref':'run-result:run:call','items':[{'response':{'content':[{'type':'text','text':'真实文档'}]}}]}
    value=prepare_materials([{'role':'tool','content':wiki},{'role':'tool','content':external}])
    assert value['original_evidence']==[wiki,external]


def test_frozen_search_dependency_does_not_read_new_thread_scope():
    def changed(*args):
        raise AssertionError('old save must not use new task scope')
    store=SimpleNamespace(task_space=changed)
    sources=SimpleNamespace(visible_video_ids=lambda scope: sorted(scope.video_ids),source_refs_visible=lambda refs,scope:True)
    tools=AssistantToolRegistry(store=store,sources=sources,memories=None,wiki=None)
    frozen={'source_ids':[],'video_ids':[1],'all_active':False,'scope_version':1}
    result={'coverage':{'scope':tools.scope_identity(frozen)},'items':[]}
    tools._validate_historical_result({'run_id':'run','call_id':'call','name':'search_knowledge','result':result},
         scope=SourceScope(video_ids=frozenset([1])),space_id=1,thread_id='thread',scope_version=1,space_override=frozen)


def test_writer_high_keeps_native_prefix_but_has_no_executable_tools(monkeypatch):
    from shiliu.assistant.provider import OpenAICompatibleAssistantProvider
    from shiliu.domain import PipelineError
    import pytest
    provider=OpenAICompatibleAssistantProvider(base_url='https://synthetic.invalid/v1',api_key='synthetic',model='deepseek-v4-flash')
    prefix=[{'role':'system','content':'original system'}, {'role':'user','content':'research'},
            {'role':'assistant','content':'', 'tool_calls':[{'id':'read','type':'function','function':{'name':'collection_read','arguments':'{}'}}]},
            {'role':'tool','tool_call_id':'read','content':'original evidence'},
            {'role':'assistant','content':'research answer'}, {'role':'user','content':'Wiki JSON only'}]
    seen=[]
    def post(body):
        seen.append(body)
        return {'choices':[{'finish_reason':'stop','message':{'content':'{"topics":[],"omitted":[]}'}}],
                'usage':{'prompt_tokens':100,'completion_tokens':60,'completion_tokens_details':{'reasoning_tokens':40}}}
    monkeypatch.setattr(provider,'_post',post)
    _,usage=provider.generate_json_with_usage(messages=prefix,thinking='enabled',reasoning_effort='high',max_tokens=65536)
    assert seen[0]['messages']==prefix and 'tools' not in seen[0] and 'tool_choice' not in seen[0]
    assert seen[0]['thinking']=={'type':'enabled'} and seen[0]['reasoning_effort']=='high'
    assert usage['completion_tokens_details']['reasoning_tokens']==40
    monkeypatch.setattr(provider,'_post',lambda body:{'choices':[{'finish_reason':'tool_calls','message':{'content':'{}','tool_calls':[{}]}}],'usage':{'total_tokens':9}})
    with pytest.raises(PipelineError) as error:
        provider.generate_json_with_usage(messages=prefix,thinking='enabled',reasoning_effort='high')
    assert error.value.usage=={'total_tokens':9}
