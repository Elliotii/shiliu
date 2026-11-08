"""Save/Publish regressions for normal summaries and explicit retry."""
import asyncio
import json
import pytest
from psycopg.types.json import Jsonb
from test_wiki_tool_consolidation import begin, PersonalWriter
from test_assistant_runtime_p0 import runtime_parts
from test_wiki import wiki_parts, add_source
from test_assistant_p2_knowledge_write import Writer, formal_answer
from shiliu.assistant.knowledge_write import accept_save, execute_save
from shiliu.assistant.sources import SourceScope
from shiliu.assistant.tools import AssistantToolRegistry


def test_button_research_with_memory_context_preserves_analysis_and_title(runtime_parts,wiki_parts):
    db,store,runtime,_,space,_,_=runtime_parts
    thread,answer=formal_answer(runtime_parts,wiki_parts)
    with db.connect() as c:
        c.execute('UPDATE assistant_threads SET context_state_json=%s WHERE id=%s',
            (Jsonb({'entries':[{'kind':'block','block_type':'memory','content':'个人背景只供理解，不属于这次研究。','dependency_refs':[]}]}),thread))
    receipt=accept_save(store,thread_id=thread,answer_message_id=answer,request_id='button-memory',
        requirement='整理并保存这条研究回答',wiki=runtime.wiki)
    job=store.claim_job(owner='button-memory',kinds={'wiki_save'})
    assert job['id']==receipt['id']
    class ResearchWriter(Writer):
        def generate_json_with_usage(self,**kwargs):
            self.prompts.append(kwargs['messages'])
            return {'topics':[{'title':'事务研究','purpose':'保存研究结论','blocks':[
                {'role':'analysis','heading':'综合方法','markdown':'模型调用放在事务外，提交前核对来源版本。'},
                {'role':'analysis','heading':'证据缺口','markdown':'尚未测试长时间并发，不外推稳定性。'}]}]}, {'total_tokens':4}
    writer=ResearchWriter()
    result=execute_save(store,runtime.wiki,writer,job,max_tokens=8192)
    page=runtime.wiki.get_page(result['pages'][0]['page_id'])
    assert page['title']=='事务研究' and len(page['blocks'])==2
    assert page['blocks'][0]['markdown']=='模型调用放在事务外，提交前核对来源版本。'
    assert len(writer.prompts)==1


@pytest.mark.parametrize('scope_changes', [False, True])
def test_source_paraphrase_and_analysis_publish_and_read_in_new_thread(runtime_parts,wiki_parts,scope_changes):
    db,store,runtime,_,space,_,sources=runtime_parts
    vid,_,ref,_=add_source(wiki_parts,text='面汤金黄清澈，一滴油没有。')
    run=wiki_parts[5]
    with db.connect() as c:c.execute("UPDATE assistant_runs SET status='running' WHERE id=%s",(run,))
    result=sources.read(call_id='source',scope=SourceScope(all_active=True),source_ref=f'video:{vid}',view='transcript').model_dump(mode='json')
    store.begin_tool_call(run,ordinal=1,call_id='source',name='collection_read',arguments={},expected_epoch=1)
    store.finish_tool_call(run,call_id='source',result=result,expected_epoch=1)
    store.save_assistant_tool_message(run,content='',provider_payload={'tool_calls':[
        {'id':'source','type':'function','function':{'name':'collection_read','arguments':'{}'}}]},expected_epoch=1)
    store.save_message(run,role='tool',content=json.dumps(result),provider_payload={'name':'collection_read','tool_call_id':'source'},expected_epoch=1)
    registry=AssistantToolRegistry(store=store,sources=sources,memories=runtime.memories,wiki=runtime.wiki)
    search_ref=f'run-result:{run}:explore'
    search={'status':'empty','items':[], 'coverage':{'canonical_name':'search_knowledge','scope':registry.scope_identity(store.get_space(space))}}
    store.begin_tool_call(run,ordinal=2,call_id='explore',name='search_knowledge',arguments={},expected_epoch=1)
    store.finish_tool_call(run,call_id='explore',result=search,expected_epoch=1)
    store.save_assistant_tool_message(run,content='',provider_payload={'tool_calls':[
        {'id':'explore','type':'function','function':{'name':'search_knowledge','arguments':'{}'}}]},expected_epoch=1)
    store.save_message(run,role='tool',content=json.dumps(search),provider_payload={'name':'search_knowledge','tool_call_id':'explore'},expected_epoch=1)
    thread,answer=formal_answer(runtime_parts,wiki_parts)
    with db.connect() as c:
        c.execute("UPDATE assistant_messages SET provider_payload_json=jsonb_set(provider_payload_json,'{dependency_refs}',%s) WHERE id=%s",(Jsonb([search_ref]),answer))
    accept_save(store,thread_id=thread,answer_message_id=answer,request_id='summary',requirement='保存研究',wiki=runtime.wiki)
    job=store.claim_job(owner='summary',kinds={'wiki_save'})
    if scope_changes:
        add_source(wiki_parts,index=2,text='无关的新材料，不属于保存内容。')
        assert not registry.dependency_refs_valid([search_ref],space,thread,1,space_override=job['payload']['scope'])
    class SummaryWriter(Writer):
        def generate_json_with_usage(self,**kwargs):
            self.prompts.append(kwargs['messages'])
            return {'topics':[{'title':'面汤研究','purpose':'条件和缺口','blocks':[
                {'role':'source','heading':'来源概括','markdown':'面汤清澈，作者称没有油。','source_refs':[ref],'source_view':'transcript'},
                {'role':'analysis','heading':'解释与缺口','markdown':'可能较清爽，但辣度仍未知。','source_refs':[ref]}]}]}, {'total_tokens':4}
    writer=SummaryWriter();result=execute_save(store,runtime.wiki,writer,job,max_tokens=8192)
    store.finish_job(job['id'],proposal=result,owner=job['lease_owner'],lease_epoch=job['lease_epoch'])
    page=runtime.wiki.get_page(result['pages'][0]['page_id'])
    assert page['blocks'][0]['markdown']=='面汤清澈，作者称没有油。' and len(writer.prompts)==1
    assert [b['assessment'] for b in page['blocks']]==['source_reported','system_synthesis']
    new=store.create_thread(space);nr=store.create_run(new['id'],text='读取面汤研究',request_id='read-summary')
    registry=AssistantToolRegistry(store=store,sources=sources,memories=runtime.memories,wiki=runtime.wiki)
    read=asyncio.run(registry.execute(name='knowledge_read',arguments={'page_id':page['id'],'mode':'page'},call_id='read',
        run_context={'thread':store.get_thread(new['id']),'run':store.get_run(nr['id']),'space':store.task_space(new['id'])}))
    assert read['status']=='ok' and '辣度仍未知' in str(read['items'])


def test_manual_retry_revalidates_returned_draft_without_model_call(runtime_parts,wiki_parts):
    db,store,runtime,_,_,_,_=runtime_parts
    thread,answer=formal_answer(runtime_parts,wiki_parts)
    receipt=accept_save(store,thread_id=thread,answer_message_id=answer,request_id='old-gate',requirement='保存研究',wiki=runtime.wiki)
    job=store.claim_job(owner='old-gate',kinds={'wiki_save'})
    raw={'topics':[{'title':'保留草稿研究','purpose':'保存已返回结果','blocks':[
        {'role':'analysis','heading':'方法','markdown':'保留合理概括和证据缺口。','decision_basis':[{'kind':'source','claim':'旧格式内容'}]}]}]}
    staged={'raw_output':raw,'generation_attempts':2,'generation_pending':False,
        'terminal_error':'wiki_scope_has_no_authorized_blocks','generation_error':'wiki_scope_has_no_authorized_blocks',
        'generation_history':[{'output':raw,'error':'wiki_scope_has_no_authorized_blocks'}]}
    store.save_job_proposal(job['id'],staged,owner=job['lease_owner'],lease_epoch=job['lease_epoch'])
    store.fail_job(job,code='wiki_writer_invalid_draft',message='wiki_scope_has_no_authorized_blocks',blocked=True)
    store.retry_job(receipt['id']);retried=store.claim_job(owner='after-removal',kinds={'wiki_save'})
    class NoCalls(Writer):
        def generate_json_with_usage(self,**kwargs):raise AssertionError('Stored draft must be reused')
    outcome=execute_save(store,runtime.wiki,NoCalls(),retried,max_tokens=8192)
    assert outcome['outcome']=='success' and outcome['generation_attempts']==2 and outcome['generation_history']==staged['generation_history']
    again=execute_save(store,runtime.wiki,NoCalls(),retried,max_tokens=8192)
    assert again['pages']==outcome['pages']
    store.finish_job(retried['id'],proposal=outcome,owner=retried['lease_owner'],lease_epoch=retried['lease_epoch'])


def test_previous_user_quote_is_bounded_and_persists(runtime_parts):
    from shiliu.assistant.wiki_draft_checks import bind_history_quotes
    db,store,runtime,_,space,_,_=runtime_parts
    thread=store.create_thread(space)
    first=store.create_run(thread['id'],text='我的方法是先提出可证伪假设，再记录对照条件。暂不保存。',request_id='old-content')
    old=store.get_thread(thread['id'])['messages'][-1]
    # Use completed fixture state, not a model or a product business mutation.
    with db.connect() as c:c.execute("UPDATE assistant_runs SET status='completed' WHERE id=%s",(first['id'],))
    run=store.create_run(thread['id'],text='把我上一条提出的方法保存到Wiki。',request_id='reauthorize')
    current=store.get_thread(thread['id'])['messages'][-1]
    quote='先提出可证伪假设，再记录对照条件。'
    refs=[{'message_id':old['id'],'quote':quote}]
    accepted=accept_save(store,thread_id=thread['id'],answer_message_id=None,user_message_id=current['id'],request_id='ref',requirement=current['content'],user_facts=True,wiki=runtime.wiki,wiki_message_quotes=refs,wiki_authorized_quotes=[quote])
    assert accepted['id']==accept_save(store,thread_id=thread['id'],answer_message_id=None,user_message_id=current['id'],request_id='ref',requirement=current['content'],user_facts=True,wiki=runtime.wiki,wiki_message_quotes=refs,wiki_authorized_quotes=[quote])['id']
    job=store.claim_job(owner='historical-quote',kinds={'wiki_save'})
    assert job['payload']['wiki_reauthorized_messages']==refs
    class PriorWriter(PersonalWriter):
        def generate_json_with_usage(self,**kw):
            return {'topics':[{'title':'研究方法','purpose':'长期复用','blocks':[
                {'role':'personal','heading':'方法','markdown':'先提出能被反驳的假设，然后记录对照。','user_message_id':old['id'],'user_quote':quote}]}]}, {'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}
    outcome=execute_save(store,runtime.wiki,PriorWriter(old),job,max_tokens=8192)
    page=runtime.wiki.get_page(outcome['pages'][0]['page_id'])
    assert page['blocks'][0]['markdown']=='先提出能被反驳的假设，然后记录对照。' and page['blocks'][0]['user_message_id']==old['id']
    with db.connect(read_only=True) as c:
        with pytest.raises(ValueError,match='ambiguous'):
            bind_history_quotes(store,c,thread['id'],current['id'],'把某些旧内容保存到Wiki',refs)
