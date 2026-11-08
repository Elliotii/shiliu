"""P3 user corrections on the real PG Wiki/Memory version and receipt paths."""
import pytest
from test_wiki import wiki_parts  # noqa: F401
from test_assistant_runtime_p0 import runtime_parts  # noqa: F401
from shiliu.assistant.runtime_contract import AssistantConflict

OLD = '霁桥项目评审原定2026年11月12日10:00（北京时间）。'
NEW = '霁桥项目评审改为2026年11月14日15:00（北京时间），原安排作废。'


def user(store, space, text):
    thread = store.create_thread(space)
    run = store.create_run(thread['id'], text=text, request_id='p3')
    return store.get_thread(thread['id'])['messages'][-1]['id']


def block(message, text, **kw):
    return dict(role='personal', heading='项目安排', markdown=text,
                user_message_id=message, user_quote=text, **kw)


def save(wiki, space, message, blocks, *, version=None, key='save', **kw):
    return wiki.save_discussion_topics(space_id=space, source_message_id=message,
        request_key=key, omitted=[], topics=[dict(title='霁桥项目评审安排', purpose='项目计划',
            blocks=blocks, expected_version=version, **kw)])


def page_from(wiki, plan):
    results=list(plan['results'].values())
    assert all(r['status']=='completed' for r in results), results
    return wiki.get_page(results[0]['page_id'])


def test_memory_correction_preserves_independent_wiki_and_old_source_protection(runtime_parts):
    db, store, runtime, _, space, message, _ = runtime_parts
    wiki_fact = '项目评审需逐项核对证据来源与版本。'
    with db.connect() as c:
        c.execute('UPDATE assistant_messages SET content=%s WHERE id=%s',(OLD + wiki_fact,message))
    memory = runtime.memories.save_explicit(text=OLD,subject_key='jiqiao',kind='context',
        scope_kind='space',scope_id=space,source_message_ids=[message],operation_key='memory-v1')
    page = page_from(runtime.wiki,save(runtime.wiki,space,message,[block(message,wiki_fact)]))
    correction = user(store,space,NEW)
    current = runtime.memories.correct(memory['id'],text=NEW,expected_version=1,
        source_message_ids=[correction],operation_key='memory-v2')
    assert current['version'] == 2 and current['text'] == NEW
    assert message in runtime.memories.suppressed_source_message_ids(space_id=space)
    assert message not in runtime.memories.suppressed_source_message_ids(space_id=space,wiki_evidence=True)
    with db.connect(read_only=True) as c:
        thread_id = c.execute('SELECT thread_id FROM assistant_messages WHERE id=%s',(message,)).fetchone()['thread_id']
        assert not c.execute("SELECT 1 FROM assistant_jobs WHERE kind='wiki_save'").fetchone()
    assert store.knowledge_message(message,thread_id=thread_id,wiki_evidence=True)['content'] == OLD + wiki_fact
    with pytest.raises(AssistantConflict,match='save_message_suppressed'):
        store.knowledge_message(message,thread_id=thread_id)
    visible = runtime.wiki.get_page(page['id'])
    assert visible['version'] == 1 and [b['markdown'] for b in visible['blocks']] == [wiki_fact]
    from shiliu.assistant.wiki_retrieval import WikiHybridIndex
    search = WikiHybridIndex(None, wiki=runtime.wiki).search(wiki_fact, space_id=space)
    assert any(p['page_id'] == page['id'] for p in search['candidates'])
    # Legacy rows have no explicit Wiki list and continue to protect their sources.
    with db.connect() as c:
        c.execute('UPDATE assistant_memory_suppressions SET wiki_source_message_ids_json=NULL')
    assert runtime.wiki.get_page(page['id'])['blocks'] == []

    # A new ordinary correction of the same text must preserve the earlier
    # source fence without adding the new message to the Wiki privacy fence.
    repeated = user(store,space,OLD)
    other = runtime.memories.save_explicit(text=OLD,subject_key='jiqiao',kind='context',
        scope_kind='space',scope_id=space,source_message_ids=[repeated],operation_key='memory-recreated')
    runtime.memories.correct(other['id'],text='评审延期，时间待定。',expected_version=other['version'],
        source_message_ids=[correction],operation_key='memory-recorrected')
    protected = runtime.memories.suppressed_source_message_ids(space_id=space,wiki_evidence=True)
    assert message in protected and repeated not in protected


def test_targeted_personal_replace_preserves_other_manual_content_and_cas(runtime_parts):
    db, store, runtime, _, space, message, _ = runtime_parts
    wiki=runtime.wiki
    with db.connect() as c:
        c.execute('UPDATE assistant_messages SET content=%s WHERE id=%s',(OLD,message))
    first=page_from(wiki,save(wiki,space,message,[block(message,OLD),
        {'role':'analysis','heading':'其他笔记','markdown':'不要改动这份笔记'}]))
    protected=wiki.edit_block(first['id'],block_id=first['blocks'][1]['stable_id'],
        markdown='用户人工笔记保持原样',expected_version=1,operation_key='manual')
    current=user(store,space,'请更正项目安排：'+NEW)
    run=store.claim_next_run()
    assert run['thread_id']==store.get_run(run['id'])['thread_id']
    target=protected['blocks'][0]['stable_id']
    store.confirm_model_delivery(run['id'],epoch=1,spans=[],materials=[{
        'kind':'knowledge_read','source_ref':f"wiki:{first['id']}:2",'position':{'block_ids':[b['stable_id'] for b in protected['blocks']]}}])
    changed=page_from(wiki,save(wiki,space,current,[block(current,NEW,replace_block_id=target)],
        page_id=first['id'],version=2,key='replace'))
    assert changed['id']==first['id'] and changed['version']==3
    assert [b['markdown'] for b in changed['blocks']]==[NEW,'用户人工笔记保持原样']
    assert changed['blocks'][0]['stable_id']==target
    assert changed['blocks'][0]['user_message_id']==current
    assert changed['blocks'][1]['manual_lock'] is True
    stale=save(wiki,space,current,[block(current,NEW,replace_block_id=target)],page_id=first['id'],version=2,key='stale')
    assert all(r['status']=='failed' for r in stale['results'].values())
    assert wiki.get_page(first['id'])['version']==3
    with pytest.raises(AssistantConflict,match='page_missing'):
        save(wiki,space,current,[block(current,NEW)],page_id='awiki_wrong',version=3,key='wrong')
    assert len(wiki.list_pages(space_id=space))==1


def test_locked_block_cannot_be_replaced_without_actual_read(runtime_parts):
    db, store, runtime, _, space, message, _ = runtime_parts
    with db.connect() as c:
        c.execute('UPDATE assistant_messages SET content=%s WHERE id=%s',(OLD,message))
    first=page_from(runtime.wiki,save(runtime.wiki,space,message,[block(message,OLD)]))
    current=user(store,space,'请更正：'+NEW)
    failed=save(runtime.wiki,space,current,[block(current,NEW,replace_block_id=first['blocks'][0]['stable_id'])],
        page_id=first['id'],version=1,key='not-read')
    assert all('wiki_block_not_read' in r.get('reason','') for r in failed['results'].values())
    assert runtime.wiki.get_page(first['id'])['version']==1


@pytest.mark.parametrize('complete',[True,False])
def test_compound_correction_uses_independent_tools(runtime_parts,complete):
    import time,json
    from test_assistant_runtime_p0 import ScriptedProvider
    from shiliu.assistant.provider import ModelTurn,NativeToolCall
    db, store, runtime, _, space, message, _=runtime_parts
    with db.connect() as c:
        c.execute('UPDATE assistant_messages SET content=%s WHERE id=%s',(OLD,message))
    memory=runtime.memories.save_explicit(text=OLD,subject_key='jiqiao',kind='context',scope_kind='space',
        scope_id=space,source_message_ids=[message],operation_key='initial-memory')
    first=page_from(runtime.wiki,save(runtime.wiki,space,message,[block(message,OLD)]))
    wiki_clause = '请更新知识页：' + NEW
    current=user(store,space,'请更新记忆：'+NEW+'另'+wiki_clause)
    with db.connect(read_only=True) as c:
        rid=c.execute('SELECT run_id FROM assistant_messages WHERE id=%s',(current,)).fetchone()['run_id']
    class Provider(ScriptedProvider):
        def send_prepared(self,request,**kwargs):
            self.calls+=1
            if self.calls==1:
                return ModelTurn(text='',finish_reason='tool_calls',tool_calls=[NativeToolCall('correct','memory_correct',
                    dict(memory_id=memory['id'],expected_version=1,text=NEW))])
            if self.calls==2:
                assert 'wiki_update_targets' not in json.dumps(request.body,ensure_ascii=False)
                if complete:
                    return ModelTurn(text='',finish_reason='tool_calls',tool_calls=[NativeToolCall('update','knowledge_update_page',
                        dict(page_id=first['id'],purpose='新安排',expected_version=1,
                             wiki_authorized_quotes=[wiki_clause],blocks=[block(current,NEW)]))])
            return ModelTurn(text='已核对实际结果。',finish_reason='stop')
    import asyncio
    from shiliu.assistant.runtime import AssistantExecutionGraph
    from shiliu.assistant.tools import AssistantToolRegistry
    provider=Provider()
    registry=AssistantToolRegistry(store=store,sources=runtime.sources,memories=runtime.memories,wiki=runtime.wiki)
    graph=AssistantExecutionGraph(store=store,memories=runtime.memories,tools=registry,
        provider_factory=lambda:provider,recover_legacy=False)
    run=store.claim_next_run()
    asyncio.run(graph.run(run))
    assert store.get_run(rid)['status']=='completed',store.get_run(rid)
    assert provider.calls==(3 if complete else 2)
    assert runtime.memories.get(memory['id'])['version']==2
    assert runtime.wiki.get_page(first['id'])['version']==1  # accepted does not mean updated
    if complete:
        from test_assistant_p2_knowledge_write import Writer
        from shiliu.assistant.knowledge_write import execute_save
        class CorrectionWriter(Writer):
            def generate_json_with_usage(self, **kwargs):
                return {'topics':[dict(page_id=first['id'],title=first['title'],purpose='新安排',expected_version=1,
                    blocks=[block(current,NEW)])],'omitted':[]}, {'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}
        job=store.claim_job(owner='P3-compound',kinds={'wiki_save'})
        assert job is not None
        result=execute_save(store,runtime.wiki,CorrectionWriter(),job,max_tokens=8192)
        assert result['pages'][0]['page_id']==first['id']
        assert runtime.wiki.get_page(first['id'])['version']==2

        class ReuseProvider(ScriptedProvider):
            def send_prepared(self, request, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return ModelTurn(text='', finish_reason='tool_calls', tool_calls=[
                        NativeToolCall('read-updated', 'knowledge_read',
                            dict(page_id=first['id'], page_version=2, mode='page'))])
                body = json.dumps(request.body, ensure_ascii=False)
                assert NEW in body and 'read-updated' in body
                return ModelTurn(text=NEW, finish_reason='stop')

        reused = ReuseProvider()
        reuse_graph = AssistantExecutionGraph(store=store,memories=runtime.memories,tools=registry,
            provider_factory=lambda:reused,recover_legacy=False)
        user(store,space,'请只读取更新后的知识页，再说明其中的新安排。')
        reuse_run = store.claim_next_run()
        assert reuse_run['thread_id'] != run['thread_id']
        asyncio.run(reuse_graph.run(reuse_run))
        assert store.get_run(reuse_run['id'])['status'] == 'completed' and reused.calls == 2
        assert store.get_thread(reuse_run['thread_id'])['messages'][-1]['content'] == NEW



@pytest.mark.parametrize('field',['page_id','expected_version','replace_block_id'])
def test_p2_job_cannot_use_update_fields(runtime_parts,wiki_parts,field):
    from test_assistant_p2_knowledge_write import Writer,formal_answer
    from shiliu.assistant.knowledge_write import accept_save,execute_save
    _,store,runtime,_,space,_,_=runtime_parts
    thread,answer=formal_answer(runtime_parts,wiki_parts)
    accept_save(store,wiki=runtime.wiki,thread_id=thread,answer_message_id=answer,request_id='guard',requirement='保存')
    job=store.claim_job(owner='P3',kinds={'wiki_save'})
    provider=Writer();generate=provider.generate_json_with_usage
    def invalid(**kwargs):
        value,usage=generate(**kwargs)
        if field=='replace_block_id':value['topics'][0]['blocks'][0][field]='wblock_any'
        else:value['topics'][0][field]=1 if field=='expected_version' else 'awiki_any'
        return value,usage
    provider.generate_json_with_usage=invalid
    with pytest.raises(ValueError,match='create_job_cannot_update'):
        execute_save(store,runtime.wiki,provider,job,max_tokens=8192)
    assert runtime.wiki.list_pages(space_id=space)==[]


def test_explicit_edit_keeps_existing_manual_lock_and_receipt(runtime_parts):
    _,store,runtime,_,space,message,_=runtime_parts
    wiki=runtime.wiki
    first=page_from(wiki,save(wiki,space,message,[{'role':'analysis','heading':'结论','markdown':'原技术结论'}]))
    target=first['blocks'][0]['stable_id']
    locked=wiki.edit_block(first['id'],block_id=target,markdown='人工结论',expected_version=1,operation_key='lock')
    current=user(store,space,'请将结论修改为：提交前核验版本；其余内容不动。')
    run=store.claim_next_run()
    store.confirm_model_delivery(run['id'],epoch=1,spans=[],materials=[{
        'kind':'knowledge_read','source_ref':f"wiki:{first['id']}:2",'position':{'block_ids':[target]}}])
    args=[{'role':'analysis','heading':'结论','markdown':'提交前核验版本','replace_block_id':target}]
    plan=save(wiki,space,current,args,page_id=first['id'],version=2,key='edit')
    edited=page_from(wiki,plan)
    assert edited['blocks'][0]['manual_lock'] is True and edited['version']==3
    replay=page_from(wiki,save(wiki,space,current,args,page_id=first['id'],version=2,key='edit'))
    assert replay['version']==3 and len(replay['blocks'])==1
