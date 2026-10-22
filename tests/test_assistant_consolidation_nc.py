from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

import pytest

from shiliu.assistant.provider import OpenAICompatibleAssistantProvider, ModelTurn
from shiliu.assistant.runtime import AssistantExecutionGraph, AssistantRuntime
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.sources import SourceScope
from shiliu.assistant.store import AssistantRunStore
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.domain import PipelineError
from test_assistant_stage_c import _services, _add_material, DeterministicWikiProvider


def _running(store, space_id, text='请只看这几篇', thread_id=None, key='nc'):
    thread_id = thread_id or store.create_thread(space_id)['id']
    run = store.create_run(thread_id, text=text, request_id=key)
    return store.claim_next_run()


def test_provider_real_sse_fields_complete_tools_and_incomplete_stream(monkeypatch):
    chunks = [
        {'choices': [{'delta': {'reasoning_content': 'HIDDEN', 'content': '中文'}}]},
        {'choices': [{'delta': {'tool_calls': [{'index': 0, 'id': 'c1', 'function': {'name': 'read', 'arguments': '{"id":'}}]}}]},
        {'choices': [{'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': '1}'}}]}, 'finish_reason': 'tool_calls'}]},
        {'choices': [], 'usage': {'total_tokens': 19}, 'model': 'actual-provider-model'},
    ]
    @contextmanager
    def stream(*args, **kwargs):
        assert kwargs['json']['stream'] is True
        assert kwargs['json']['thinking'] == {'type': 'disabled'}
        class Response:
            def raise_for_status(self): pass
            def iter_lines(self):
                yield from ['data: ' + json.dumps(c) for c in chunks]
                yield 'data: [DONE]'
        yield Response()
    monkeypatch.setattr('shiliu.assistant.provider.httpx.stream', stream)
    p = OpenAICompatibleAssistantProvider(base_url='http://provider', api_key='test', model='configured')
    seen = []
    turn = p.stream_turn(messages=[], tools=[], max_tokens=10, on_text=seen.append)
    assert seen == ['中文'] and 'HIDDEN' not in str(turn)
    assert turn.tool_calls[0].arguments == {'id': 1} and turn.usage['total_tokens'] == 19
    chunks[2]['choices'][0]['delta']['tool_calls'][0]['function']['arguments'] = 'x}'
    with pytest.raises(PipelineError, match='工具参数'):
        p.stream_turn(messages=[], tools=[], max_tokens=10, on_text=seen.append)


def test_draft_epoch_stop_finish_restart_and_final_commit(app_paths):
    db, _, sources, store, wiki = _services(app_paths)
    space = store.create_space(name='NC', all_active=True)
    run = _running(store, space['id'])
    assert store.save_answer_draft(run['id'], epoch=1, text='草稿')
    reopened = AssistantRunStore(db)
    assert reopened.get_run(run['id'])['working_state']['answer_draft']['text'] == '草稿'
    store.request_finish(run['id'])
    assert not store.save_answer_draft(run['id'], epoch=1, text='迟到片段')
    assert store.save_answer_draft(run['id'], epoch=1, text='收尾', allow_finish=True)
    store.cancel_run(run['id'])
    assert not reopened.save_answer_draft(run['id'], epoch=1, text='迟到最终')
    assert not any(m['role'] == 'assistant' for m in store.get_thread(run['thread_id'])['messages'])
    next_run = _running(store, space['id'], text='继续', thread_id=run['thread_id'], key='next')
    assert store.save_answer_draft(next_run['id'], epoch=1, text='正式答案')
    assert store.try_complete_run(next_run['id'], epoch=1, answer='正式答案', usage={},
                                  expected_scope_version=1, expected_observed_memory_epoch=0,
                                  dependency_refs=[], expected_task_note_version=None) == 'completed'
    assert store.try_complete_run(next_run['id'], epoch=1, answer='重复', usage={},
                                  expected_scope_version=1, expected_observed_memory_epoch=0,
                                  dependency_refs=[], expected_task_note_version=None) == 'run_fenced'
    assert [m['content'] for m in store.get_thread(run['thread_id'])['messages'] if m['role']=='assistant'] == ['正式答案']


def test_restart_expired_lease_keeps_candidate_budget_and_does_not_steal(app_paths):
    db, _, _, store, _ = _services(app_paths)
    with db.connect() as c:
        job_id = store.enqueue_job(c, kind='source_extract', dedupe_key='lease-nc', payload={'message_ids': ['m1', 'm2'], 'batch_cursor': 2})
    job = store.claim_job(owner='other-instance')
    store.save_job_proposal(job_id, {'response': {'summary': 'candidate'}}, owner=job['lease_owner'], lease_epoch=job['lease_epoch'])
    store.reserve_model_request(lane='background', request_limit=60)
    reopened = AssistantRunStore(db)
    assert reopened.recover_expired_jobs() == 0
    assert reopened.claim_job(owner='new-instance') is None
    with db.connect() as c:
        c.execute("UPDATE assistant_jobs SET lease_until=? WHERE id=?", ((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(), job_id))
    assert reopened.recover_expired_jobs() == 1
    restored = reopened.claim_job(owner='new-instance')
    assert restored['proposal']['response']['summary'] == 'candidate'
    assert restored['payload'] == job['payload'] and restored['attempt'] == 2
    assert not store.finish_job(job_id, proposal={}, owner=job['lease_owner'], lease_epoch=job['lease_epoch'])
    with db.connect() as c:
        assert c.execute("SELECT requests_used FROM assistant_model_budget_days WHERE lane='background'").fetchone()[0] == 1
        c.execute("UPDATE assistant_jobs SET attempt=3,lease_until='2000-01-01T00:00:00+00:00' WHERE id=?", (job_id,))
    reopened.recover_expired_jobs()
    assert reopened.claim_job(owner='third') is None
    assert reopened.list_jobs()[0]['status'] == 'blocked'


def test_task_subset_propagates_search_read_wiki_and_followup(app_paths):
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=42, folder_title='学习资料', history_policy='all')
    first = _add_material(db, artifacts, source_id, bvid='BV1NC0000001', title='允许', text='允许内容')
    other = _add_material(db, artifacts, source_id, bvid='BV1NC0000002', title='排除', text='排除秘密内容')
    space = store.create_space(name='NC', all_active=True)
    run = _running(store, space['id'])
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    def execute(name, args):
        if name == "task_scope":
            args = {**args, "basis_quote": "请只看这几篇"}
        return asyncio.run(registry.execute(name=name, arguments=args, call_id=name, run_context=store.run_context(run['id'])))
    assert execute('task_scope', {'video_ids':[first]})['status'] == 'ok'
    context = store.run_context(run['id'])
    assert context['space']['video_ids'] == [first]
    assert store.get_space(space['id'])['video_ids'] == [] and store.get_space(space['id'])['scope_version']==1
    assert execute('collection_read', {'source_ref':f'video:{other}', 'view':'summary'})['status'] != 'ok'
    results = execute('search_knowledge', {'query':'内容', 'sources':['collection']})
    assert str(other) not in [str(item.get('video_id')) for item in results['items'][0]['candidates']]
    refs = [f'video:{v}:{sources.snapshots.capture(v).revision}' for v in (first,other)]
    projected = wiki._task_projection({'blocks':[{'markdown':'允许','source_refs':[refs[0]]},
                                                {'markdown':'混合泄漏','source_refs':refs},
                                                {'markdown':'未知泄漏'},
                                                {'markdown':'旧哈希混合泄漏','source_refs':[r.split(':')[2] for r in refs]},
                                                {'markdown':'旧哈希允许','source_refs':[refs[0].split(':')[2]]}],
                                     'materials':[{'video_id':first},{'video_id':other}], 'summary':'泄漏'},
                                     SourceScope(all_active=True, video_ids=frozenset([first])))
    assert [b['markdown'] for b in projected['blocks']] == ['允许','旧哈希允许']
    assert projected['materials']==[{'video_id':first}]
    complete = wiki._task_projection({'blocks':[{'markdown':'允许','source_refs':[refs[0]]}],
                                     'materials':[{'video_id':first}], 'summary':'这些可见块的导读'},
                                     SourceScope(all_active=True, video_ids=frozenset([first])))
    assert complete['summary']=='这些可见块的导读' and projected['summary']!='泄漏'
    store.cancel_run(run['id'])
    next_run = store.create_run(run['thread_id'], text='继续使用这些资料', request_id='followup')
    assert next_run['working_state']['task_subset']['video_ids'] == [first]
    assert store.run_context(next_run['id'])['space']['video_ids']==[first]

@pytest.mark.parametrize('action', ['stop', 'finish'])
def test_stream_control_fences_late_fragments_and_settles_usage(app_paths, action):
    import threading
    from test_assistant_consolidation_na_review import services, graph
    _, store, _, thread, memories, tools = services(app_paths)
    run = store.create_run(thread['id'], text='请读材料', request_id='stream-control')
    claimed = store.claim_next_run()
    entered, release = threading.Event(), threading.Event()
    class Provider:
        count = 0
        def stream_turn(self, *, messages, tools, max_tokens, on_text):
            self.count += 1
            if self.count == 1:
                on_text('早期草稿')
                entered.set()
                assert release.wait(5)
                on_text('迟到片段不得出现')
                return ModelTurn('迟到最终', usage={'total_tokens': 13})
            on_text('当前有效收尾')
            return ModelTurn('当前有效收尾', usage={'total_tokens': 7})
    engine = graph(store, memories, tools, Provider())
    async def exercise():
        task = asyncio.create_task(engine.run(claimed))
        while not entered.is_set():
            await asyncio.sleep(.01)
        assert store.get_run(run['id'])['working_state']['answer_draft']['text']=='早期草稿'
        if action == 'stop': store.cancel_run(run['id'])
        else: store.request_finish(run['id'])
        await asyncio.wait_for(task, 2)
        release.set()
        await asyncio.sleep(.2)
    asyncio.run(exercise())
    messages = store.get_thread(thread['id'])['messages']
    answers = [m['content'] for m in messages if m['role']=='assistant']
    assert answers == ([] if action=='stop' else ['当前有效收尾'])
    assert store.get_run(run['id'])['usage']['total_tokens']==(13 if action=='stop' else 20)
    assert '迟到片段' not in json.dumps(store.get_run(run['id'])['working_state'],ensure_ascii=False)



@pytest.mark.parametrize('trigger', ['finish', 'timeout'])
@pytest.mark.parametrize('old_tools', [True, False])
def test_replaced_stream_cannot_mutate_blocked_finalizer(app_paths, monkeypatch, trigger, old_tools):
    import threading
    from types import SimpleNamespace
    from shiliu.assistant.provider import NativeToolCall
    from test_assistant_consolidation_na_review import services, graph
    _, store, _, thread, memories, tools = services(app_paths)
    run = store.create_run(thread['id'], text='请读材料', request_id='stream-interleave')
    claimed = store.claim_next_run()
    clock = {'now': 1000.0}
    monkeypatch.setattr('shiliu.assistant.runtime.time', SimpleNamespace(monotonic=lambda: clock['now']))
    old_entered, old_release = threading.Event(), threading.Event()
    new_entered, new_release = threading.Event(), threading.Event()
    writes = []
    original_save = store.save_answer_draft
    def save(*args, **kwargs):
        result = original_save(*args, **kwargs)
        writes.append((kwargs['text'], result))
        return result
    monkeypatch.setattr(store, 'save_answer_draft', save)
    executed = []
    async def execute(**kwargs):
        executed.append(kwargs)
        raise AssertionError('obsolete tool executed')
    monkeypatch.setattr(tools, 'execute', execute)
    class Provider:
        calls = 0
        def stream_turn(self, *, messages, tools, max_tokens, on_text):
            self.calls += 1
            if self.calls == 1:
                on_text('旧探索草稿')
                old_entered.set()
                assert old_release.wait(5)
                on_text('旧迟到片段')
                return ModelTurn('旧最终答案', tool_calls=[NativeToolCall(
                    call_id='obsolete', name='memory_save', arguments={'text': '不得写入'})] if old_tools else [],
                    usage={'total_tokens': 13})
            assert not tools
            on_text('新收尾草稿')
            new_entered.set()
            assert new_release.wait(5)
            return ModelTurn('新收尾答案', usage={'total_tokens': 7})
    provider = Provider()
    engine = graph(store, memories, tools, provider)
    async def until(predicate):
        async def poll():
            while not predicate():
                await asyncio.sleep(.005)
        await asyncio.wait_for(poll(), 2)
    async def exercise():
        task = asyncio.create_task(engine.run(claimed))
        try:
            await until(old_entered.is_set)
            if trigger == 'finish':
                store.request_finish(run['id'])
                clock['now'] += 1
            else:
                clock['now'] += 241  # Advance only runtime's clock, not asyncio's.
            await until(new_entered.is_set)
            before = store.get_run(run['id'])['working_state']['answer_draft']
            assert before['text'] == '新收尾草稿'
            clock['now'] += 1  # Force the old token past the snapshot throttle.
            old_release.set()
            await until(lambda: store.get_run(run['id'])['working_state'].get('late_model_usage', {}).get('total_tokens') == 13)
            assert store.get_run(run['id'])['working_state']['answer_draft'] == before
            assert ('旧迟到片段', False) in writes
            assert ('' if old_tools else '旧最终答案', False) in writes
            assert not executed
            assert not any(m['role'] == 'assistant' for m in store.get_thread(thread['id'])['messages'])
            new_release.set()
            await asyncio.wait_for(task, 2)
        finally:
            old_release.set()
            new_release.set()
    asyncio.run(exercise())
    assert provider.calls == 2 and not executed
    assert [m['content'] for m in store.get_thread(thread['id'])['messages']
            if m['role'] == 'assistant'] == ['新收尾答案']
    assert store.get_run(run['id'])['usage']['total_tokens'] == 20


def test_draft_memory_forget_invalidates_before_next_fragment(app_paths):
    db, _, _, store, _ = _services(app_paths)
    space = store.create_space(name='NC', all_active=True)
    memories = MemoryService(db)
    memory = memories.save_explicit(text='本周优先学数据库',subject_key='database',kind='context',scope_kind='space',
                                   scope_id=space['id'],operation_key='nc-memory')
    run = _running(store, space['id'])
    ref = memories.dependency_ref(memory)
    store.save_context_observation(run['id'], epoch=1, metadata={'observed_memory_epoch': memories.current_epoch(),
                                                                'dependency_refs':[ref]})
    assert store.save_answer_draft(run['id'],epoch=1,text='当前背景',call_id='current',start_call=True)
    memories.forget(memory['id'],expected_version=1,operation_key='nc-forget')
    assert not store.save_answer_draft(run['id'],epoch=1,text='旧调用',call_id='obsolete')
    assert store.get_run(run['id'])['working_state']['answer_draft']['text']=='当前背景'
    assert not store.save_answer_draft(run['id'],epoch=1,text='旧背景迟到',call_id='current')
    draft = store.get_run(run['id'])['working_state']['answer_draft']
    assert draft['text']=='' and draft['status']=='invalidated'

@pytest.mark.parametrize('new_policy', ['apply', 'off', 'forget'])
def test_staged_memory_restart_keeps_fixed_batch_and_late_policy(app_paths, monkeypatch, new_policy):
    db, _, sources, store, _ = _services(app_paths)
    space=store.create_space(name='NC',all_active=True)
    run=_running(store,space['id'],text='我决定接下来两周优先补数据库基础')
    message=next(m for m in store.get_thread(run['thread_id'])['messages'] if m['role']=='user')
    with db.connect() as c:
        store._enqueue_memory_extraction(c,run={**run,'extraction_memory_epoch':0},user_messages=[message],
                                        admission={'enabled':True,'generation':0})
    store.cancel_run(run['id'])
    idle={'value':True}
    monkeypatch.setattr(store,'maintenance_idle',lambda **kw:idle['value'])
    class Provider:
        calls=0
        def extract_memories(self, *, prompt):
            self.calls+=1; idle['value']=False
            return [{'op':'add','kind':'context','text':'接下来两周优先补数据库基础','subject_key':'database',
                     'scope_kind':'space','scope_id':space['id'],'source_excerpt':message['content']}]
    provider=Provider()
    runtime=AssistantRuntime(store=store,sources=sources,memory_backend=None,context7=None,provider_factory=lambda:provider)
    job=store.claim_job(owner='first')
    asyncio.run(runtime._process_job(job))
    assert store.list_jobs()[0]['status']=='queued' and provider.calls==1
    reopened=AssistantRunStore(db)
    monkeypatch.setattr(reopened,'maintenance_idle',lambda **kw:True)
    next_run=reopened.create_run(run['thread_id'],text='接着解释资料',request_id='new-message')
    next_message=next(m for m in reopened.get_thread(run['thread_id'])['messages'] if m['run_id']==next_run['id'])
    with db.connect() as c:
        reopened._enqueue_memory_extraction(c,run={**next_run,'extraction_memory_epoch':0},user_messages=[next_message],
                                            admission={'enabled':True,'generation':0})
    memories=MemoryService(db)
    if new_policy=='off': memories.set_auto_enabled(False)
    elif new_policy=='forget':
        old=memories.save_explicit(text='接下来两周优先补数据库基础',subject_key='database',kind='context',scope_kind='space',
                                   scope_id=space['id'],operation_key='old',source_message_ids=[message['id']])
        memories.forget(old['id'],expected_version=1,operation_key='forgot')
    with db.connect() as c:
        c.execute("UPDATE assistant_jobs SET not_before='2099-01-01T00:00:00+00:00' WHERE kind IN ('memory_index','memory_purge')")
    recovered=reopened.claim_job(owner='second')
    assert recovered['payload']['message_ids']==[message['id']]
    assert next_message['id'] not in recovered['payload']['message_ids']
    new_runtime=AssistantRuntime(store=reopened,sources=sources,memory_backend=None,context7=None,provider_factory=lambda:provider)
    asyncio.run(new_runtime._process_job(recovered))
    assert provider.calls==1
    rows=memories.list(space_id=space['id'])
    assert len(rows)==(1 if new_policy=='apply' else 0)
    jobs=reopened.list_jobs()
    assert any(j['payload'].get('message_ids')==[next_message['id']] for j in jobs)
    assert next(j for j in jobs if j['id']==job['id'])['status']=='succeeded'


def test_source_card_restart_reuses_completed_batches(app_paths):
    from shiliu.assistant.wiki import MaintenanceYield
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id=db.create_favorite_source(folder_id=42,folder_title='NC',history_policy='all')
    vid=_add_material(db,artifacts,source_id,bvid='BV1NC0000003',title='长资料',text='资料内容。'*6000)
    captured=sources.snapshots.capture(vid)
    with db.connect() as c:
        job_id=store.enqueue_job(c,kind='source_extract',dedupe_key='card-nc',payload={'video_id':vid,'revision':captured.revision})
    job=store.claim_job(owner='first')
    allowed={'value':True}
    wiki.publish_allowed=lambda:allowed['value']
    class Provider(DeterministicWikiProvider):
        def generate_json(self, **kwargs):
            value=super().generate_json(**kwargs)
            allowed['value']=False
            return value
    first=Provider()
    with pytest.raises(MaintenanceYield):wiki.extract_source_card(job,provider=first)
    store.defer_job_for_activity(job)
    assert first.card_calls==1
    reopened=AssistantRunStore(db)
    restored=reopened.claim_job(owner='second')
    wiki.store=reopened; allowed['value']=True; second=DeterministicWikiProvider()
    wiki.extract_source_card(restored,provider=second)
    # 36k chars / 12k = three batches, first one already durable.
    assert second.card_calls==2
    assert wiki.get_source_card(captured.revision) is not None


def test_subset_bootstrap_handoff_and_topic_reject_excluded_source(app_paths):
    db, artifacts, sources, store, wiki = _services(app_paths)
    sid=db.create_favorite_source(folder_id=42,folder_title='NC',history_policy='all')
    first=_add_material(db,artifacts,sid,bvid='BV1NC0000004',title='选中',text='只用这份资料')
    other=_add_material(db,artifacts,sid,bvid='BV1NC0000005',title='排除',text='不能读这份资料')
    space=store.create_space(name='NC',all_active=True)
    with pytest.raises(ValueError,match='source_out_of_scope'):
        wiki.request_topic(space_id=space['id'],topic='范围测试',source_refs=[f'video:{other}'],request_key='excluded',task_subset=[first])
    batch=wiki.bootstrap_space(space['id'],limit=10,task_subset=[first])
    assert batch['video_ids']==[first] and batch['queued']==1
    job=store.claim_job(owner='reconcile')
    result=wiki.reconcile(job)
    assert store.finish_job(job['id'],proposal=result,owner=job['lease_owner'],lease_epoch=job['lease_epoch'])
    extract=store.claim_job(owner='extract')
    assert extract['payload']['task_subset']==[first]
    result=wiki.extract_source_card(extract,provider=DeterministicWikiProvider())
    assert store.finish_job(extract['id'],proposal=result,owner=extract['lease_owner'],lease_epoch=extract['lease_epoch'])
    integrations=[j for j in store.list_jobs() if j['kind']=='wiki_integrate']
    assert integrations and all(j['payload']['task_subset']==[first] for j in integrations)
    assert store.get_space(space['id'])['video_ids']==[]


def test_inner_maintenance_publish_rejects_expired_owner(app_paths):
    from shiliu.assistant.wiki import MaintenanceYield
    db, _, _, store, _ = _services(app_paths)
    with db.connect() as c:
        jid=store.enqueue_job(c,kind='source_extract',dedupe_key='inner-lease',payload={})
    job=store.claim_job(owner='old-owner')
    runtime=AssistantRuntime.__new__(AssistantRuntime)
    runtime.store=store; runtime._active_maintenance_job=job;runtime._maintenance_startup_at='2000-01-01T00:00:00+00:00'
    with db.connect() as c:
        c.execute("UPDATE assistant_jobs SET lease_until='2000-01-01T00:00:00+00:00' WHERE id=?",(jid,))
        with pytest.raises(MaintenanceYield,match='maintenance_lease_lost'):
            runtime._require_maintenance_idle(c)


def test_new_tool_history_references_receipt_and_old_body_still_reads(app_paths):
    db, _, _, store, _ = _services(app_paths)
    space=store.create_space(name='NC',all_active=True);run=_running(store,space['id'])
    result={'call_id':'c1','status':'ok','items':[{'text':'完整不可变正文'}]}
    store.begin_tool_call(run['id'],ordinal=1,call_id='c1',name='collection_read',arguments={'source_ref':'video:1'})
    store.finish_tool_call(run['id'],call_id='c1',result=result)
    store.save_tool_result_message(run['id'],content=json.dumps(result),provider_payload={'tool_call_id':'c1'})
    store.save_tool_result_message(run['id'],content=json.dumps({'status':'ok','items':['旧正文']}),provider_payload={'tool_call_id':'legacy'})
    with db.connect() as c:
        rows=c.execute("SELECT content FROM assistant_messages WHERE run_id=? AND role='tool' ORDER BY seq",(run['id'],)).fetchall()
    assert '_assistant_result_ref' in rows[0]['content'] and '完整不可变正文' not in rows[0]['content']
    messages=[m for m in store.get_thread(run['thread_id'])['messages'] if m['role']=='tool']
    assert json.loads(messages[0]['content'])==result and json.loads(messages[1]['content'])['items']==['旧正文']


def test_direct_page_sources_do_not_require_a_source_card(app_paths):
    db, artifacts, sources, store, wiki = _services(app_paths)
    sid=db.create_favorite_source(folder_id=42,folder_title='NC',history_policy='all')
    vid=_add_material(db,artifacts,sid,bvid='BV1NC0000006',title='无来源卡仍有出处',text='原材料')
    captured=sources.snapshots.capture(vid)
    space=store.create_space(name='NC',all_active=True);run=_running(store,space['id'],text='请保存这份讨论')
    msg=next(m['id'] for m in store.get_thread(run['thread_id'])['messages'] if m['role']=='user')
    from assistant_context_support import deliver_collection
    registry=AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    deliver_collection(store, registry, run, f'video:{vid}:{captured.revision}')
    page=wiki.save_discussion(space_id=space['id'],title='NC出处',purpose='保留来源',blocks=[
        {'role':'source','heading':'依据','markdown':'原材料中的条件','source_refs':[f'video:{vid}:{captured.revision}']}],
        operation_key='nc-no-card',source_message_id=msg)
    visible=wiki.get_page(page['id'],space_id=space['id'])
    block=visible['blocks'][0]
    assert block['sources'][0]['title']=='无来源卡仍有出处'
    assert block['sources'][0]['material_view']=='未生成来源卡' and not block.get('source_view')


def test_tool_queue_and_formal_save_keep_subset_boundary(app_paths):
    db, artifacts, sources, store, wiki = _services(app_paths)
    sid=db.create_favorite_source(folder_id=42,folder_title='NC',history_policy='all')
    first=_add_material(db,artifacts,sid,bvid='BV1NC0000007',title='选中',text='允许资料')
    other=_add_material(db,artifacts,sid,bvid='BV1NC0000008',title='排除',text='排除资料')
    refs={v:f'video:{v}:{sources.snapshots.capture(v).revision}' for v in (first,other)}
    space=store.create_space(name='NC',all_active=True)
    run=_running(store,space['id'],text='请只看这份，整理并保存主题')
    store.set_task_subset(run['id'],epoch=1,video_ids=[first])
    registry=AssistantToolRegistry(sources=sources,memories=MemoryService(db),store=store,wiki=wiki)
    def call(name,args,key):
        return asyncio.run(registry.execute(name=name,arguments=args,call_id=key,run_context=store.run_context(run['id'])))
    assert call('knowledge_organize',{'topic':'NC','source_refs':[refs[other]]},'excluded')['status']!='ok'
    accepted=call('knowledge_organize',{'topic':'NC','source_refs':[refs[first]]},'allowed')
    assert accepted['status']=='ok'
    job=next(j for j in store.list_jobs() if j['kind']=='source_reconcile')
    assert job['payload']['task_subset']==[first]
    denied=call('knowledge_save_outcome',{'title':'不能保存排除材料','purpose':'边界',
        'blocks':[{'role':'source','heading':'排除','markdown':'不能写入','source_refs':[refs[other]]}]},'denied')
    assert denied['status']!='ok' and wiki.list_pages(space_id=space['id'])==[]


def test_current_call_source_invalidates_visible_draft(app_paths):
    from types import SimpleNamespace
    from shiliu.assistant.api import _safe_draft
    db, artifacts, sources, store, wiki = _services(app_paths)
    source = db.create_favorite_source(folder_id=43, folder_title='R1', history_policy='all')
    video = _add_material(db, artifacts, source, bvid='BV1NCR100001', title='R1', text='原始资料')
    revision = sources.snapshots.capture(video).revision
    space = store.create_space(name='R1', all_active=True)
    run = _running(store, space['id'])
    store.save_context_observation(run['id'], epoch=1, metadata={
        'observed_memory_epoch': 0, 'dependency_refs': [f'video:{video}:{revision}']})
    runtime = SimpleNamespace(store=store, sources=sources, memories=MemoryService(db), wiki=wiki)
    assert store.save_answer_draft(run['id'], epoch=1, text='当前依据', call_id='current', start_call=True)
    assert _safe_draft(runtime, store.get_run(run['id']))['working_state']['answer_draft']['text']=='当前依据'
    with db.connect() as c:
        c.execute('UPDATE assistant_source_heads SET current_revision=? WHERE video_id=?', ('replaced', video))
    visible = _safe_draft(runtime, store.get_run(run['id']))['working_state']['answer_draft']
    assert visible['text']=='' and visible['status']=='invalidated'


def _c1_provider(**kwargs):
    return OpenAICompatibleAssistantProvider(
        base_url='https://api.deepseek.com/v1', api_key='synthetic',
        model='deepseek-v4-flash', **kwargs,
    )


def test_provider_prepared_body_matches_turn_stream_and_compact(monkeypatch):
    import httpx
    from shiliu.assistant.provider_request import estimate_tokens
    from shiliu.assistant.provider_request import prepare_request

    messages = [
        {'role': 'system', 'content': '合成规则'},
        {'role': 'user', 'content': '合成要求'},
        {'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': 'c1', 'type': 'function', 'function': {'name': 'read', 'arguments': '{"start":1}'}}]},
        {'role': 'tool', 'tool_call_id': 'c1', 'content': '合成正文'},
        {'role': 'system', 'content': '合成状态'},
    ]
    tools = [{'type': 'function', 'function': {'name': 'read', 'parameters': {'type': 'object'}}}]
    p = _c1_provider()
    captured = []
    prepared = []
    # A Fake Provider can use the same immutable request contract, without a second counter.
    original = p.prepare_request
    def record(**kwargs):
        request = original(**kwargs)
        prepared.append(request)
        return request
    monkeypatch.setattr(p, 'prepare_request', record)
    def post(url, **kwargs):
        captured.append(kwargs)
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'message': {'content': '最终正文', 'reasoning_content': '隐藏推理'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 61, 'completion_tokens': 9, 'total_tokens': 70},
        })
    @contextmanager
    def stream(method, url, **kwargs):
        captured.append(kwargs)
        class Response:
            def raise_for_status(self): pass
            def iter_lines(self):
                yield 'data: ' + json.dumps({'choices': [{'delta': {'content': '最终正文'}, 'finish_reason': 'stop'}], 'usage': {'total_tokens': 70}})
                yield 'data: [DONE]'
        yield Response()
    monkeypatch.setattr('shiliu.assistant.provider.httpx.post', post)
    monkeypatch.setattr('shiliu.assistant.provider.httpx.stream', stream)
    assert p.turn(messages=messages, tools=tools, max_tokens=4096).text == '最终正文'
    assert p.stream_turn(messages=messages, tools=tools, max_tokens=4096, on_text=lambda _: None).text == '最终正文'
    assert [c['json'] for c in captured] == [r.body for r in prepared]
    assert prepared[0].input_tokens == prepared[1].input_tokens
    for request in prepared:
        input_body = {k: v for k, v in request.body.items()
                      if k not in {'model', 'max_tokens', 'stream', 'stream_options'}}
        assert request.input_tokens == estimate_tokens(json.dumps(input_body, ensure_ascii=False))
    assert captured[0]['json'] == {
        'model': p.model, 'messages': messages, 'tools': tools, 'tool_choice': 'auto',
        'max_tokens': 4096, 'thinking': {'type': 'disabled'},
    }
    # Inspection and caller mutations cannot alter an already prepared request.
    frozen = prepared[0].body
    prepared[0].body['messages'][0]['content'] = 'mutated copy'
    messages[0]['content'] = 'new caller value'
    assert prepared[0].body == frozen

    expected = p.prepare_compaction(messages=messages, remaining_tokens=200000)
    result = p.compact_context(messages=messages, remaining_tokens=200000, remaining_seconds=12)
    assert captured[-1]['json'] == expected.body and captured[-1]['timeout'] == 12
    assert result.text == '最终正文' and result.finish_reason == 'stop'
    assert result.usage == {'prompt_tokens': 61, 'completion_tokens': 9, 'total_tokens': 70}
    assert '隐藏推理' not in str(result)
    assert expected.body['thinking'] == {'type': 'enabled'}
    assert expected.body['reasoning_effort'] == 'low' and expected.body['tools'] == []
    assert expected.body['tool_choice'] == 'none' and expected.body['max_tokens'] == 65536
    assert expected.input_tokens == prepare_request(
        base_url=p.base_url, model=p.model, messages=messages, tools=[],
        max_tokens=expected.body['max_tokens'], compact=True,
    ).input_tokens
    # Auxiliary methods retain their original disabled/JSON policies after low summary.
    def json_post(url, **kwargs):
        captured.append(kwargs)
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'message': {'content': '{"proposals":[]}'}, 'finish_reason': 'stop'}],
            'usage': {'total_tokens': 3},
        })
    monkeypatch.setattr('shiliu.assistant.provider.httpx.post', json_post)
    assert p.extract_memories(prompt='合成用户原话') == []
    assert p.generate_json_with_usage(system='合成规则', prompt='合成提案', max_tokens=2400)[1] == {'total_tokens': 3}
    p.turn(messages=messages, tools=[], max_tokens=4096)
    assert [c['json']['max_tokens'] for c in captured[-3:]] == [1600, 2400, 4096]
    for item in captured[-3:]:
        assert item['json']['thinking'] == {'type': 'disabled'}
        assert 'reasoning_effort' not in item['json']
    assert all(c['json']['model'] == p.model for c in captured)


def test_provider_capacity_and_summary_output_reserve(monkeypatch):
    from dataclasses import replace
    p = _c1_provider()
    request = p.prepare_request(messages=[{'role': 'user', 'content': '合成'}], tools=[], max_tokens=4096)
    assert p.budget_request(request).available_input_tokens == 256000  # C, not C-O
    caps = replace(p.capabilities, shared_window_tokens=10000, uncounted_input_tokens=7,
                   max_output_tokens=8000, low_default_output_tokens=7000)
    p = _c1_provider(capabilities=caps)
    budget = p.budget_request(request)
    assert budget.available_input_tokens == 10000 - 4096 - 7
    assert budget.fits
    messages = [{'role': 'user', 'content': '合成摘要输入'}]
    default = p.prepare_compaction(messages=messages, remaining_tokens=100000)
    limited = p.prepare_compaction(messages=messages, remaining_tokens=default.input_tokens + 900)
    assert default.body['max_tokens'] == 7000 and limited.body['max_tokens'] == 900
    window_limited = _c1_provider(capabilities=replace(caps, shared_window_tokens=5000))
    window_request = window_limited.prepare_compaction(messages=messages, remaining_tokens=100000)
    assert window_request.body['max_tokens'] == 5000 - window_request.input_tokens - 7
    assert window_limited.budget_request(window_request).fits  # Equality at shared window.
    assert not p.budget_request(request, input_limit_tokens=1).fits
    monkeypatch.setattr('shiliu.assistant.provider.httpx.post', lambda *a, **k: pytest.fail('must not dispatch'))
    for kwargs, code in [
        ({'remaining_tokens': default.input_tokens}, 'provider_capacity_invalid'),
        ({'remaining_tokens': 100000, 'input_limit_tokens': 1}, 'context_budget_exceeded'),
    ]:
        with pytest.raises(PipelineError) as caught:
            p.prepare_compaction(messages=messages, **kwargs)
        assert caught.value.code == code
    with pytest.raises(PipelineError) as caught:
        p.compact_context(messages=messages, remaining_tokens=100000, remaining_seconds=0)
    assert caught.value.code == 'provider_timeout'
    with pytest.raises(PipelineError):
        p.budget_request(p.prepare_request(messages=[], tools=[], max_tokens=8001))
    unknown = OpenAICompatibleAssistantProvider(base_url='https://proxy.example/v1', api_key='synthetic', model=p.model)
    with pytest.raises(PipelineError) as caught:
        unknown.budget_request(unknown.prepare_request(messages=[], tools=[], max_tokens=10))
    assert caught.value.code == 'provider_capabilities_unknown'
    with pytest.raises(PipelineError):
        OpenAICompatibleAssistantProvider(base_url='https://proxy.example/v1', api_key='synthetic', model=p.model, capabilities=caps)
    no_low = _c1_provider(capabilities=replace(caps, supports_low_thinking=False, low_default_output_tokens=None))
    assert no_low.budget_request(request).fits
    with pytest.raises(PipelineError) as caught:
        no_low.prepare_compaction(messages=messages, remaining_tokens=100000)
    assert caught.value.code == 'provider_low_unsupported'
    # Custom route may explicitly assert verified capabilities, but names alone never suffice.
    custom = replace(caps, base_url=unknown.base_url, source='synthetic test route contract')
    configured = OpenAICompatibleAssistantProvider(base_url=unknown.base_url, api_key='synthetic', model=p.model, capabilities=custom)
    assert configured.budget_request(configured.prepare_request(messages=[], tools=[], max_tokens=10)).fits


@pytest.mark.parametrize('finish,content,extra', [
    ('length', '{"valid_json":true}', {}),
    ('stop', '  ', {'reasoning_content': '只有推理'}),
    (None, '缺失状态', {}),
    ('content_filter', '部分正文', {}),
    ('aborted', '部分正文', {}),
    ('insufficient_system_resource', '部分正文', {}),
    ('stop', '正文', {'refusal': '拒绝'}),
    ('tool_calls', '', {'tool_calls': [{'id': 'c1', 'function': {'name': 'read', 'arguments': '{}'}}]}),
    ('stop', '正文', {'tool_calls': [{'id': 'c1', 'function': {'name': 'read', 'arguments': '{}'}}]}),
])
def test_compaction_rejects_incomplete_or_nontext_result_with_usage(monkeypatch, finish, content, extra):
    import httpx
    def post(url, **kwargs):
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'message': {'content': content, **extra}, 'finish_reason': finish}],
            'usage': {'total_tokens': 87},
        })
    monkeypatch.setattr('shiliu.assistant.provider.httpx.post', post)
    with pytest.raises(PipelineError) as caught:
        _c1_provider().compact_context(messages=[{'role': 'user', 'content': '合成输入'}],
                                      remaining_tokens=100000, remaining_seconds=20)
    assert caught.value.code == 'provider_compaction_incomplete'
    assert caught.value.usage == {'total_tokens': 87} and caught.value.finish_reason == finish


def test_provider_explicit_overflow_classification_for_post_and_stream(monkeypatch):
    import httpx
    p = _c1_provider()
    response_data = {'status': 400, 'body': {'error': {'code': 'context_length_exceeded'}}}
    def response(url):
        return httpx.Response(response_data['status'], request=httpx.Request('POST', url), json=response_data['body'])
    monkeypatch.setattr('shiliu.assistant.provider.httpx.post', lambda url, **kwargs: response(url))
    @contextmanager
    def stream(method, url, **kwargs):
        unread = httpx.Response(response_data['status'], request=httpx.Request(method, url),
                               stream=httpx.ByteStream(json.dumps(response_data['body']).encode()))
        try:
            yield unread
        finally:
            unread.close()
    monkeypatch.setattr('shiliu.assistant.provider.httpx.stream', stream)
    for status, body, expected in [
        (400, {'error': {'code': 'context_length_exceeded'}}, 'provider_context_window_exceeded'),
        (400, {'error': {'type': 'context_window_exceeded'}}, 'provider_context_window_exceeded'),
        (400, {'error': {'message': 'context window exceeded'}}, 'provider_http'),
        (400, {'error': {'code': 'invalid_request_error'}}, 'provider_http'),
        (400, {'error': {'code': {'malformed': True}}}, 'provider_http'),
        (400, ['malformed error envelope'], 'provider_http'),
        (401, {'error': {'code': 'context_length_exceeded'}}, 'provider_auth'),
        (429, {'error': {'code': 'rate_limit'}}, 'provider_http'),
        (500, {'error': {'code': 'context_length_exceeded'}}, 'provider_http'),
    ]:
        response_data.update(status=status, body=body)
        for streamed, dispatch in [
            (False, lambda: p.turn(messages=[], tools=[], max_tokens=10)),
            (True, lambda: p.stream_turn(messages=[], tools=[], max_tokens=10, on_text=lambda _: None)),
        ]:
            with pytest.raises(PipelineError) as caught:
                dispatch()
            legacy_stream_error = streamed and expected != 'provider_context_window_exceeded'
            assert caught.value.code == ('provider_stream_network' if legacy_stream_error else expected)
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout('synthetic')
    monkeypatch.setattr('shiliu.assistant.provider.httpx.post', timeout)
    with pytest.raises(PipelineError) as caught:
        p.turn(messages=[], tools=[], max_tokens=10)
    assert caught.value.code == 'provider_timeout'
