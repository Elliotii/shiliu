"""Real isolated PostgreSQL, Stub Writer, no external API."""
import asyncio
import json
import pytest
from test_wiki import wiki_parts
from test_assistant_runtime_p0 import runtime_parts
from test_assistant_p2_knowledge_write import Writer, formal_answer
from test_wiki_tool_consolidation import request, PersonalWriter, begin, FACT
from shiliu.assistant.knowledge_write import accept_save, execute_save, WriterDraftError
from shiliu.assistant.runtime_contract import AssistantConflict


def proposal(store, job):
    with store.db.connect(read_only=True) as c:
        return c.execute('SELECT proposal_json FROM assistant_jobs WHERE id=%s',(job['id'],)).fetchone()['proposal_json']


def test_one_correction_then_terminal_and_no_bad_draft(runtime_parts):
    _, user, _, _ = request(runtime_parts)
    store, runtime = runtime_parts[1:3]
    job = store.claim_job(owner='candidate5', kinds={'wiki_save'})
    writer = PersonalWriter(user, bad_quote=True)
    with pytest.raises(WriterDraftError):
        execute_save(store,runtime.wiki,writer,job,max_tokens=8192)
    staged=proposal(store,job)
    assert len(writer.prompts)==2 and 'draft' not in staged
    assert staged['generation_attempts']==2 and len(staged['generation_history'])==2
    with pytest.raises(WriterDraftError):
        execute_save(store,runtime.wiki,writer,{**job,'proposal':staged},max_tokens=8192)
    assert len(writer.prompts)==2 and not runtime.wiki.list_pages(space_id=runtime_parts[4])


def test_transient_commit_failure_reuses_valid_draft(runtime_parts, monkeypatch):
    _, user, _, _=request(runtime_parts)
    store,runtime=runtime_parts[1:3]
    job=store.claim_job(owner='candidate5',kinds={'wiki_save'})
    writer=PersonalWriter(user)
    original=runtime.wiki.save_discussion_topics
    def unavailable(**kwargs):
        raise ConnectionError('deterministic connection interruption before commit')
    monkeypatch.setattr(runtime.wiki,'save_discussion_topics',unavailable)
    with pytest.raises(ConnectionError):
        execute_save(store,runtime.wiki,writer,job,max_tokens=8192)
    staged=proposal(store,job)
    assert 'draft' in staged and len(writer.prompts)==1
    monkeypatch.setattr(runtime.wiki,'save_discussion_topics',original)
    result=execute_save(store,runtime.wiki,writer,{**job,'proposal':staged},max_tokens=8192)
    # Lost acknowledgment after commit uses the existing original plan/receipts.
    again=execute_save(store,runtime.wiki,writer,{**job,'proposal':staged},max_tokens=8192)
    assert result['pages']==again['pages'] and len(writer.prompts)==1
    assert len(runtime.wiki.list_pages(space_id=runtime_parts[4]))==1


def test_unknown_generation_never_automatically_reissued(runtime_parts):
    _,user,_,_=request(runtime_parts)
    store,runtime=runtime_parts[1:3]
    job=store.claim_job(owner='candidate5',kinds={'wiki_save'})
    writer=PersonalWriter(user)
    attempts=[]
    def unknown(**kwargs):
        attempts.append(1)
        raise ConnectionError('response lost')
    writer.generate_json_with_usage=unknown
    with pytest.raises(WriterDraftError,match='unknown'):
        execute_save(store,runtime.wiki,writer,job,max_tokens=8192)
    with pytest.raises(WriterDraftError,match='unknown'):
        execute_save(store,runtime.wiki,writer,{**job,'proposal':proposal(store,job)},max_tokens=8192)
    assert len(attempts)==1


def test_empty_authorized_page_async_update_and_raw_preservation(runtime_parts):
    db,store,runtime,_,space,_,_=runtime_parts
    from shiliu.assistant.tools import AssistantToolRegistry
    tools=AssistantToolRegistry(store=store,sources=runtime.sources,memories=runtime.memories,wiki=runtime.wiki)
    thread,user,_,_=request(runtime_parts)
    job=store.claim_job(owner='candidate5',kinds={'wiki_save'})
    first=execute_save(store,runtime.wiki,PersonalWriter(user),job,max_tokens=8192)
    store.finish_job(job['id'],proposal=first,owner=job['lease_owner'],lease_epoch=job['lease_epoch'])
    page=runtime.wiki.get_page(first['pages'][0]['page_id'])
    memory=runtime.memories.save_explicit(text=FACT,subject_key='candidate5-plan',kind='context',
        scope_kind='space',scope_id=space,source_message_ids=[user['id']],operation_key='memory-initial')
    new='霁桥评审改为2026年11月14日15:00，原安排作废。'
    wiki_clause = '请更新知识页：' + new
    thread2,correct,context=begin(runtime_parts,'请更正Memory：'+new+'另'+wiki_clause)
    runtime.memories.forget(memory['id'],expected_version=1,operation_key='memory-forget')
    # Exercise empty-page recovery against a source protected by legacy data.
    with db.connect() as c:
        c.execute('UPDATE assistant_memory_suppressions SET wiki_source_message_ids_json=NULL')
    assert runtime.wiki.get_page(page['id'])['blocks']==[]
    with db.connect(read_only=True) as c:
        raw=c.execute('SELECT blocks_json FROM assistant_wiki_pages WHERE id=%s',(page['id'],)).fetchone()
    assert raw['blocks_json'] and raw['blocks_json'][0]['user_message_id']==user['id']
    read=asyncio.run(tools.execute(name='knowledge_read',arguments={'page_id':page['id'],'mode':'page','page_version':1},
        call_id='empty',run_context=context))
    assert read['status']=='empty' and read['coverage']['page_exists']
    assert read['coverage']['body_state']=='no_visible_body' and read['items'][0]['version']==1
    missing=asyncio.run(tools.execute(name='knowledge_read',arguments={'page_id':'awiki_missing','mode':'page'},call_id='missing',run_context=context))
    assert missing['status']=='unavailable' and missing['coverage']['body_state']=='unavailable_page'
    assert missing['coverage']['page_exists'] is None  # Do not expose foreign page existence.
    blocks=[{'role':'personal','heading':'新安排','markdown':new,'user_message_id':correct['id'],'user_quote':new}]
    accepted=asyncio.run(tools.execute(name='knowledge_update_page',arguments={'page_id':page['id'],'expected_version':1,
        'purpose':'纠正计划','wiki_authorized_quotes':[wiki_clause],
        'blocks':blocks},call_id='update',run_context=context))
    assert accepted['status']=='ok'
    edit_job=store.claim_job(owner='candidate5',kinds={'wiki_save'})
    writer=PersonalWriter(correct)
    def update(**kwargs):
        writer.prompts.append(kwargs['messages'])
        return {'topics':[{'title':page['title'],'page_id':page['id'],'expected_version':1,'purpose':'纠正计划','blocks':blocks}]}, {'total_tokens':4}
    writer.generate_json_with_usage=update
    result=execute_save(store,runtime.wiki,writer,edit_job,max_tokens=8192)
    current=runtime.wiki.get_page(page['id'])
    assert current['version']==2 and current['blocks'][0]['markdown']==new
    assert result['pages'][0]['page_id']==page['id']
    _,no_write,denied_context=begin(runtime_parts,'请只更正 Memory，不要写入或修改 Wiki：'+new)
    denied=asyncio.run(tools.execute(name='knowledge_update_page',arguments={'page_id':page['id'],'expected_version':2,
        'purpose':'不应修改','blocks':blocks},call_id='denied',run_context=denied_context))
    assert denied['error_code']=='knowledge_save_forbidden'
    assert runtime.wiki.get_page(page['id'])['version']==2




def test_source_error_is_corrected_once_before_staging(runtime_parts,wiki_parts):
    from test_wiki import add_source
    from shiliu.assistant.sources import SourceScope
    db,store,runtime,_,space,_,sources=runtime_parts
    vid,_,ref,_=add_source(wiki_parts)
    run=wiki_parts[5]
    with db.connect() as c:
        c.execute("UPDATE assistant_runs SET status='running' WHERE id=%s",(run,))
    result=sources.read(call_id='source',scope=SourceScope(all_active=True),source_ref=f'video:{vid}',view='transcript',max_characters=24000).model_dump(mode='json')
    store.begin_tool_call(run,ordinal=1,call_id='source',name='collection_read',arguments={},expected_epoch=1)
    store.finish_tool_call(run,call_id='source',result=result,expected_epoch=1)
    store.save_assistant_tool_message(run,content='',provider_payload={'tool_calls':[{'id':'source','type':'function','function':{'name':'collection_read','arguments':'{}'}}]},expected_epoch=1)
    store.save_message(run,role='tool',content=json.dumps(result),provider_payload={'name':'collection_read','tool_call_id':'source'},expected_epoch=1)
    thread,answer=formal_answer(runtime_parts,wiki_parts)
    accept_save(store,wiki=runtime.wiki,thread_id=thread,answer_message_id=answer,request_id='source',requirement='保存')
    job=store.claim_job(owner='candidate5',kinds={'wiki_save'})
    writer=Writer()
    def generate(**kwargs):
        writer.prompts.append(kwargs['messages'])
        reference=f'video:{vid}' if len(writer.prompts)==1 else ref
        quote = '事务提交前必须核验来源版本。'
        return {'topics':[{'title':'来源身份','purpose':'保留来源','blocks':[{
            'role':'source','heading':'原文依据','markdown':quote,
            'source_refs':[reference],'source_view':'transcript'
        }]}]}, {'total_tokens':4}
    writer.generate_json_with_usage=generate
    saved=execute_save(store,runtime.wiki,writer,job,max_tokens=8192)
    staged=proposal(store,job)
    assert len(writer.prompts)==2 and staged['generation_attempts']==2
    assert len(staged['generation_history'])==1
    assert staged['draft']['topics'][0]['blocks'][0]['source_refs']==[ref]
    assert staged['generation_history'][0]['error'].startswith('versioned_video_source_required:')
    assert 'versioned_video_source_required' in json.dumps(writer.prompts[1])
    assert ref in json.dumps(writer.prompts[1])
    assert saved['outcome']=='success'


def test_wiki_read_after_correction_does_not_trigger_runtime_continuation(runtime_parts):
    from test_assistant_p3_lifecycle import OLD,NEW,save,block,page_from,user
    from test_assistant_runtime_p0 import ScriptedProvider
    from shiliu.assistant.provider import ModelTurn,NativeToolCall
    from shiliu.assistant.runtime import AssistantExecutionGraph
    from shiliu.assistant.tools import AssistantToolRegistry
    db,store,runtime,_,space,message,_=runtime_parts
    wiki_fact = '项目评审需核对原始材料和版本。'
    with db.connect() as c:
        c.execute('UPDATE assistant_messages SET content=%s WHERE id=%s',(OLD + wiki_fact,message))
    memory=runtime.memories.save_explicit(text=OLD,subject_key='repeat-plan',kind='context',scope_kind='space',scope_id=space,source_message_ids=[message],operation_key='initial')
    first=page_from(runtime.wiki,save(runtime.wiki,space,message,[block(message,wiki_fact)]))
    current=user(store,space,'请更新记忆和知识页：'+NEW)
    class Provider(ScriptedProvider):
        def send_prepared(self,request,**kwargs):
            self.calls+=1
            if self.calls==1:
                args=dict(memory_id=memory['id'],expected_version=1,text=NEW);name='memory_correct'
            elif self.calls == 2:
                args=dict(page_id=first['id'],page_version=1,mode='page');name='knowledge_read'
            else:
                assert '尚未执行 Wiki 更新' not in json.dumps(request.body,ensure_ascii=False)
                assert wiki_fact in json.dumps(request.body,ensure_ascii=False)
                return ModelTurn(text=wiki_fact,finish_reason='stop')
            return ModelTurn(text='',finish_reason='tool_calls',tool_calls=[NativeToolCall(str(self.calls),name,args)])
    provider=Provider()
    registry=AssistantToolRegistry(store=store,sources=runtime.sources,memories=runtime.memories,wiki=runtime.wiki)
    graph=AssistantExecutionGraph(store=store,memories=runtime.memories,tools=registry,provider_factory=lambda:provider,recover_legacy=False)
    run=store.claim_next_run();asyncio.run(graph.run(run))
    assert store.get_run(run['id'])['status']=='completed'
    assert provider.calls==3 and runtime.wiki.get_page(first['id'])['version']==1
    with db.connect(read_only=True) as c:
        assert c.execute("SELECT count(*) AS n FROM assistant_jobs WHERE kind='wiki_save'").fetchone()['n']==0
