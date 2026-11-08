"""P2 real PG authorization, commits, replay and foreground/background overlap."""
import asyncio
import threading
import time

import pytest

from test_wiki import wiki_parts, add_source  # noqa: F401
from test_assistant_runtime_p0 import runtime_parts, ScriptedProvider, row  # noqa: F401
from shiliu.assistant.knowledge_write import accept_save, execute_save, list_saves
from shiliu.assistant.runtime_contract import AssistantConflict


def formal_answer(parts, wiki_parts):
    db, store, runtime, _, space, msg, _ = parts
    run = wiki_parts[5]
    with db.connect() as c:
        c.execute("UPDATE assistant_runs SET status='running' WHERE id=%s", (run,))
    assert store.try_complete_run(run, epoch=1, answer='研究结论：模型调用放在事务外，提交前校验版本。',
        usage={}, expected_scope_version=store.get_space(space)['scope_version'],
        expected_observed_memory_epoch=store.current_memory_epoch(), dependency_refs=[], expected_task_note_version=None) == 'completed'
    thread_id = store.get_run(run)['thread_id']
    answer = store.get_thread(thread_id)['messages'][-1]
    return thread_id, answer['id']


class Writer(ScriptedProvider):
    def __init__(self, *, hold=False):
        super().__init__()
        self.entered, self.release = threading.Event(), threading.Event()
        if not hold:
            self.release.set()
        self.prompts = []

    def generate_json_with_usage(self, *, max_tokens, messages=None, **kwargs):
        assert kwargs['thinking'] == 'enabled' and kwargs['reasoning_effort'] == 'high'
        self.prompts.append(__import__('json').dumps(messages, ensure_ascii=False))
        self.entered.set()
        assert self.release.wait(15)
        return {'topics': [{'title': '事务研究', 'purpose': '长期复用', 'blocks': [
            {'role': 'analysis', 'heading': '提交边界', 'markdown': '模型调用放在事务外，提交前校验版本。'}]}],
            'omitted': []}, {'prompt_tokens': 4, 'completion_tokens': 3, 'total_tokens': 7}


def test_button_job_real_commit_dedupe_and_receipt_recovery(runtime_parts, wiki_parts):
    db, store, runtime, _, space, _, _ = runtime_parts
    thread, answer = formal_answer(runtime_parts, wiki_parts)
    before = store.get_thread(thread)
    accepted = accept_save(store, wiki=runtime.wiki, thread_id=thread, answer_message_id=answer, request_id='one', requirement='保存研究')
    assert accepted['id'] == accept_save(store, wiki=runtime.wiki, thread_id=thread, answer_message_id=answer, request_id='one', requirement='保存研究')['id']
    after = store.get_thread(thread)
    assert len(before['messages']) == len(after['messages']) and len(before['runs']) == len(after['runs'])
    job = store.claim_job(owner='P2', kinds={'wiki_save'})
    from shiliu.assistant.context import SYSTEM_RULES
    frozen = job['payload']['history']
    assert frozen['messages'][0] == {'role': 'system', 'content': SYSTEM_RULES}
    from shiliu.assistant.context import ContextMessages
    assert frozen['messages'][-1] == ContextMessages._provider_message(before['messages'][-1])
    assert answer in frozen['message_ids']
    provider = Writer()
    result = execute_save(store, runtime.wiki, provider, job, max_tokens=8192)
    assert result['outcome'] == 'success'
    # Crash after page commit and before Job completion: replay same plan/receipt.
    with db.connect(read_only=True) as c:
        staged = c.execute('SELECT proposal_json FROM assistant_jobs WHERE id=%s', (job['id'],)).fetchone()['proposal_json']
    again = execute_save(store, runtime.wiki, provider, {**job, 'proposal': staged}, max_tokens=8192)
    assert len(provider.prompts) == 1 and result['pages'] == again['pages']
    store.finish_job(job['id'], proposal=again, owner=job['lease_owner'], lease_epoch=job['lease_epoch'])
    saved = runtime.wiki.get_page(result['pages'][0]['page_id'], space_id=space)
    assert saved['version'] == 1 and saved['blocks'][0]['markdown'].startswith('模型调用')
    assert list_saves(store, thread)[0]['status'] == 'completed'
    assert len(runtime.wiki.list_pages(space_id=space)) == 1


def test_same_thread_foreground_completes_while_writer_waits(runtime_parts, wiki_parts):
    db, store, runtime, _, space, _, _ = runtime_parts
    thread, answer = formal_answer(runtime_parts, wiki_parts)
    provider = Writer(hold=True)
    runtime.provider_factory = lambda: provider
    accept_save(store, wiki=runtime.wiki, thread_id=thread, answer_message_id=answer, request_id='parallel', requirement='保存事务研究')
    runtime.start()
    try:
        assert provider.entered.wait(10), 'active saves must not wait 180 seconds'
        run = store.create_run(thread, text='换个话题，解释技术视频的 Agent Loop', request_id='new-topic')
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and store.get_run(run['id'])['status'] not in {'completed', 'failed'}:
            time.sleep(.05)
        assert store.get_run(run['id'])['status'] == 'completed'
        assert list_saves(store, thread)[0]['status'] == 'processing'
        assert '换个话题' not in provider.prompts[0]
        provider.release.set()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and list_saves(store, thread)[0]['status'] == 'processing':
            time.sleep(.05)
        assert list_saves(store, thread)[0]['status'] == 'completed'
    finally:
        provider.release.set()
        runtime.stop()


def test_invalid_answer_and_source_identity_rejected(runtime_parts, wiki_parts):
    _, store, runtime, _, _, msg, _ = runtime_parts
    thread, answer = formal_answer(runtime_parts, wiki_parts)
    with pytest.raises(AssistantConflict):
        accept_save(store, wiki=runtime.wiki, thread_id=thread, answer_message_id=msg, request_id='bad', requirement='save')
    accept_save(store, wiki=runtime.wiki, thread_id=thread, answer_message_id=answer, request_id='good', requirement='保存')
    job = store.claim_job(owner='P2', kinds={'wiki_save'})
    with runtime.wiki.job_save(job):
        assert not runtime.wiki._job_source_delivered('video:123:invented', 'transcript')
    with pytest.raises(Exception, match='wiki_save_job|required|fenced'):
        with runtime.wiki.job_save({**job, 'lease_epoch': job['lease_epoch']+1}):
            pass


def test_job_source_and_personal_use_real_evidence_and_user(runtime_parts, wiki_parts):
    import json
    from shiliu.assistant.sources import SourceScope
    db, store, runtime, _, space, msg, sources = runtime_parts
    vid, _, ref, _ = add_source(wiki_parts)
    run = wiki_parts[5]
    with db.connect() as c:
        c.execute("UPDATE assistant_runs SET status='running' WHERE id=%s", (run,))
    result = sources.read(call_id='P2-source', scope=SourceScope(all_active=True),
                          source_ref=f'video:{vid}', view='transcript', max_characters=24000).model_dump(mode='json')
    store.begin_tool_call(run, ordinal=1, call_id='P2-source', name='collection_read', arguments={}, expected_epoch=1)
    store.finish_tool_call(run, call_id='P2-source', result=result, expected_epoch=1)
    store.save_assistant_tool_message(run, content='', provider_payload={'tool_calls': [
        {'id': 'P2-source', 'type': 'function', 'function': {'name': 'collection_read', 'arguments': '{}'}}]}, expected_epoch=1)
    store.save_message(run, role='tool', content=json.dumps(result), provider_payload={'name': 'collection_read', 'tool_call_id': 'P2-source'}, expected_epoch=1)
    thread, answer = formal_answer(runtime_parts, wiki_parts)
    request = store.create_run(thread, text='请保存刚才研究和我的偏好到Wiki：我喜欢白天学习数据库。', request_id='source-permission')
    authority = store.get_thread(thread)['messages'][-1]
    accept_save(store, wiki=runtime.wiki, thread_id=thread, answer_message_id=answer,
        request_id='source', requirement=authority['content'], user_message_id=authority['id'],
        wiki_message_quotes=[{'message_id':msg,'quote':'我喜欢白天学习数据库'}])
    job = store.claim_job(owner='P2', kinds={'wiki_save'})
    provider = Writer()
    def generate(**kwargs):
        return {'topics': [{'title': '来源与笔记', 'purpose': '保存依据', 'blocks': [
            {'role': 'source', 'heading': '来源要求', 'markdown': '事务提交前必须核验来源版本。', 'source_refs': [ref], 'source_view': 'transcript', 'decision_basis':[{'kind':'source','claim':'事务提交前必须核验来源版本。','quote':'事务提交前必须核验来源版本。','source_ref':ref}]},
            {'role': 'personal', 'heading': '我的偏好', 'markdown': '我喜欢白天学习数据库', 'user_quote': '我喜欢白天学习数据库', 'user_message_id': msg}]}]}, {'total_tokens': 10}
    provider.generate_json_with_usage = generate
    result = execute_save(store, runtime.wiki, provider, job, max_tokens=8192)
    page = runtime.wiki.get_page(result['pages'][0]['page_id'], space_id=space)
    assert {b['assessment'] for b in page['blocks']} == {'source_reported', 'user_explicit'}
    assert page['blocks'][1]['user_message_id'] == msg


def test_stale_answer_dependencies_rejected_even_for_analysis(runtime_parts, wiki_parts):
    from psycopg.types.json import Jsonb
    db, store, runtime, _, _, _, sources = runtime_parts
    vid, _, ref, _ = add_source(wiki_parts)
    thread, answer = formal_answer(runtime_parts, wiki_parts)
    with db.connect() as c:
        c.execute("UPDATE assistant_messages SET provider_payload_json=provider_payload_json || %s WHERE id=%s",
                  (Jsonb({'dependency_refs': [ref]}), answer))
    accept_save(store, wiki=runtime.wiki, thread_id=thread, answer_message_id=answer, request_id='stale', requirement='保存')
    db.update_video(vid, title='改版的来源')
    sources.snapshots.capture(vid)
    job = store.claim_job(owner='P2', kinds={'wiki_save'})
    provider = Writer()
    with pytest.raises(AssistantConflict, match='dependencies_changed'):
        execute_save(store, runtime.wiki, provider, job, max_tokens=8192)
    assert provider.prompts == []


def test_generation_unknown_is_preserved_without_automatic_regeneration(runtime_parts, wiki_parts):
    from psycopg.types.json import Jsonb
    from shiliu.assistant.knowledge_write import prepare_materials
    db, store, runtime, _, space, _, _ = runtime_parts
    thread, answer = formal_answer(runtime_parts, wiki_parts)
    accept_save(store, wiki=runtime.wiki, thread_id=thread, answer_message_id=answer, request_id='network', requirement='保存')
    # A queued pre-upgrade Job has frozen bucket materials, without history.
    legacy = prepare_materials(store.get_thread(thread)['messages'])
    with db.connect() as c:
        c.execute("UPDATE assistant_jobs SET payload_json=(payload_json-'history') || %s WHERE kind='wiki_save'",
                  (Jsonb({'materials': legacy}),))
    job = store.claim_job(owner='P2', kinds={'wiki_save'})
    provider = Writer()
    actual = provider.generate_json_with_usage
    def timeout(**kwargs):
        raise TimeoutError('synthetic lost generation response')
    provider.generate_json_with_usage = timeout
    from shiliu.assistant.knowledge_write import WriterDraftError
    with pytest.raises(WriterDraftError, match='unknown'):
        execute_save(store, runtime.wiki, provider, job, max_tokens=8192)
    assert runtime.wiki.list_pages(space_id=space) == []
    provider.generate_json_with_usage = actual
    # Even a caller holding the original pre-generation Job must consult PG.
    with pytest.raises(WriterDraftError, match='unknown'):
        execute_save(store, runtime.wiki, provider, job, max_tokens=8192)
    assert runtime.wiki.list_pages(space_id=space) == []
    assert provider.prompts == []
    with store.db.connect(read_only=True) as c:
        receipts = c.execute('SELECT status FROM model_dispatch_receipts WHERE job_id=%s', (job['id'],)).fetchall()
    assert len(receipts) == 1 and receipts[0]['status'] == 'unknown'


def test_failed_commit_reuses_draft_and_plan(runtime_parts, wiki_parts, monkeypatch):
    db, store, runtime, _, _, _, _ = runtime_parts
    thread, answer = formal_answer(runtime_parts, wiki_parts)
    accept_save(store, wiki=runtime.wiki, thread_id=thread, answer_message_id=answer, request_id='commit-failure', requirement='保存')
    job = store.claim_job(owner='P2', kinds={'wiki_save'})
    provider = Writer()
    original = runtime.wiki.save_discussion
    def rejected(**kwargs):
        raise ValueError('synthetic commit rejection')
    monkeypatch.setattr(runtime.wiki, 'save_discussion', rejected)
    with pytest.raises(ValueError, match='wiki_save_failed'):
        execute_save(store, runtime.wiki, provider, job, max_tokens=8192)
    monkeypatch.setattr(runtime.wiki, 'save_discussion', original)
    with db.connect(read_only=True) as c:
        staged = c.execute('SELECT proposal_json FROM assistant_jobs WHERE id=%s', (job['id'],)).fetchone()['proposal_json']
    result = execute_save(store, runtime.wiki, provider, {**job, 'proposal': staged}, max_tokens=8192)
    assert len(provider.prompts) == 1 and len(result['pages']) == 1


def test_partial_retry_preserves_completed_page(runtime_parts, wiki_parts, monkeypatch):
    db, store, runtime, _, space, _, _ = runtime_parts
    thread, answer = formal_answer(runtime_parts, wiki_parts)
    accept_save(store, wiki=runtime.wiki, thread_id=thread, answer_message_id=answer, request_id='partial', requirement='保存')
    job = store.claim_job(owner='P2', kinds={'wiki_save'})
    provider = Writer()
    generate = provider.generate_json_with_usage
    def two(**kwargs):
        draft, usage = generate(**kwargs)
        draft['topics'].append({**draft['topics'][0], 'title': '第二个主题'})
        return draft, usage
    provider.generate_json_with_usage = two
    original = runtime.wiki.save_discussion
    def partial(**kwargs):
        if kwargs['title'] == '第二个主题':
            raise ValueError('synthetic second-page failure')
        return original(**kwargs)
    monkeypatch.setattr(runtime.wiki, 'save_discussion', partial)
    result = execute_save(store, runtime.wiki, provider, job, max_tokens=8192)
    assert result['outcome'] == 'partial' and len(result['pages']) == 1
    store.finish_job(job['id'], proposal=result, owner=job['lease_owner'], lease_epoch=job['lease_epoch'])
    store.retry_job(job['id'])
    assert list_saves(store, thread)[0]['status'] == 'queued'
    monkeypatch.setattr(runtime.wiki, 'save_discussion', original)
    again = store.claim_job(owner='P2-retry', kinds={'wiki_save'})
    recovered = execute_save(store, runtime.wiki, provider, again, max_tokens=8192)
    assert recovered['outcome'] == 'success' and len(recovered['pages']) == 2
    assert len(provider.prompts) == 1
    assert all(p['version'] == 1 for p in runtime.wiki.list_pages(space_id=space))


def test_trial_opt_in_only_allows_explicit_wiki_routes():
    from shiliu.w16_trial import trial_request_allowed
    paths = ['/api/assistant/threads/one/knowledge-writes', '/api/assistant/threads/one/knowledge-writes/job/retry']
    for path in paths:
        assert not trial_request_allowed('POST', path, manual_models=True)
        assert trial_request_allowed('POST', path, manual_models=True, wiki_saves=True)
    assert not trial_request_allowed('POST', '/api/assistant/jobs/old/retry', manual_models=True, wiki_saves=True)
    assert not trial_request_allowed('POST', '/api/sync', manual_models=True, wiki_saves=True)


def test_checkpoint_save_supplements_original_snapshot_without_read_or_new_topic(runtime_parts, wiki_parts, monkeypatch):
    db, store, runtime, _, space, _, sources = runtime_parts
    vid, _, ref, _ = add_source(wiki_parts)
    thread_id, answer = formal_answer(runtime_parts, wiki_parts)
    thread = store.get_thread(thread_id, include_internal=True)
    upper = thread['messages'][-1]['seq']
    from shiliu.assistant.tools import AssistantToolRegistry
    from shiliu.assistant.task_notes import TaskNoteService
    from shiliu.assistant.working_context import WorkingContextComposer
    registry = AssistantToolRegistry(store=store, sources=sources, memories=runtime.memories, wiki=runtime.wiki)
    notes = TaskNoteService(db, runtime.memories, dependency_ref_validator=registry.dependency_refs_valid)
    composer = WorkingContextComposer(store=store, tools=registry, task_notes=notes)
    # The synthetic checkpoint stands in for the existing compaction service;
    # original content is loaded through the real immutable source snapshot.
    note = {'id': 'checkpoint-save-test', 'dependencies': [ref]}
    monkeypatch.setattr(notes, 'checkpoint_for_context', lambda *a, **k: note)
    monkeypatch.setattr(notes, 'render', lambda n: '压缩后的研究与用户偏好')
    monkeypatch.setattr(notes, 'material_index', lambda n: [{'source_ref': ref, 'view': 'transcript'}])
    def forbidden(*a, **k):
        raise AssertionError('freezing must not capture or read a new source')
    monkeypatch.setattr(sources, 'read', forbidden)
    store.create_run(thread_id, text='新话题不能进入旧保存', request_id='later')
    thread = store.get_thread(thread_id, include_internal=True)
    thread['context_state'] = {'revision': 2, 'checkpoint': {'id': note['id']},
                               'entries': [], 'materialized_through_seq': upper}
    frozen = composer.freeze_for_save({'thread': thread, 'space': store.task_space(thread_id),
        'run': thread['runs'][-1]}, through_seq=upper, answer_id=answer)
    assert frozen['checkpoint_id'] == note['id']
    assert '新话题不能进入旧保存' not in __import__('json').dumps(frozen, ensure_ascii=False)
    evidence = frozen['original_evidence'][0]
    assert evidence['source_refs'] == [ref] and evidence['items'][0]['content']
    assert evidence['items'][0]['provenance']['immutable'] is True
    db.update_video(vid, title='来源版本已变化')
    sources.snapshots.capture(vid)
    stale = composer.freeze_for_save({'thread': thread, 'space': store.task_space(thread_id),
        'run': thread['runs'][-1]}, through_seq=upper, answer_id=answer)
    assert stale['checkpoint_id'] is None and not stale['original_evidence']


def test_natural_save_keeps_prepared_results_after_authorization_not_pending_call(runtime_parts, wiki_parts):
    from psycopg.types.json import Jsonb
    db, store, runtime, _, _, _, _ = runtime_parts
    thread, answer = formal_answer(runtime_parts, wiki_parts)
    run = store.create_run(thread, text='保存刚才研究', request_id='natural-boundary')
    claimed = store.claim_next_run()
    assert claimed['id'] == run['id']
    authorization = store.get_thread(thread)['messages'][-1]
    store.save_message(run['id'], role='assistant', content='保存前已经投影的研究补充', expected_epoch=1)
    prepared = store.get_thread(thread)
    frontier = prepared['messages'][-1]['seq']
    state = {'revision': 1, 'materialized_through_seq': frontier,
             'entries': [{'kind': 'message', 'message_id': m['id']} for m in prepared['messages']]}
    with db.connect() as c:
        c.execute('UPDATE assistant_threads SET context_state_json=%s WHERE id=%s', (Jsonb(state), thread))
    store.save_assistant_tool_message(run['id'], content='', provider_payload={'tool_calls': [
        {'id':'pending-save','type':'function','function':{'name':'knowledge_save_request','arguments':'{}'}}]}, expected_epoch=1)
    accept_save(store, wiki=runtime.wiki, thread_id=thread, answer_message_id=answer, request_id='natural',
                requirement='', user_message_id=authorization['id'])
    job = store.claim_job(owner='P2', kinds={'wiki_save'})
    frozen = job['payload']['history']
    assert frozen['through_seq'] == frontier > authorization['seq']
    text = __import__('json').dumps(frozen, ensure_ascii=False)
    assert '保存前已经投影的研究补充' in text and 'pending-save' not in text
