from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from shiliu.assistant.api import get_thread as api_get_thread
from shiliu.assistant.context import ContextBudgetExceeded
from shiliu.assistant.delivery import project_tool_result, validate_model_sequence
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.provider import OpenAICompatibleAssistantProvider
from shiliu.assistant.sources import SourceScope
from shiliu.assistant.store import AssistantConflict, AssistantRunStore
from shiliu.assistant.task_notes import TaskNoteService
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.working_context import WorkingContextComposer
from shiliu.db import Database, SCHEMA_VERSION, utc_now
from test_assistant_stage_c import _add_material, _services


@pytest.fixture
def c2(app_paths, monkeypatch):
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=42, folder_title='合成资料', history_policy='all')
    video_id = _add_material(db, artifacts, source_id, bvid='BV1C20000001', title='合成材料', text='甲乙丙丁条件。' * 1000)
    memories = MemoryService(db)
    tools = AssistantToolRegistry(store=store, sources=sources, memories=memories, wiki=wiki)
    space = store.create_space(name='C2合成', all_active=True)
    thread = store.create_thread(space['id'])
    notes = TaskNoteService(db, memories,
        source_ref_validator=lambda refs, sid: sources.source_refs_visible(refs, SourceScope(all_active=True)),
        dependency_ref_validator=tools.dependency_refs_valid)
    provider = OpenAICompatibleAssistantProvider(base_url='https://api.deepseek.com/v1', api_key='synthetic', model='deepseek-v4-flash')
    def forbidden(*args, **kwargs):
        pytest.fail('C2 components must never call a model')
    monkeypatch.setattr(provider, '_post', forbidden)
    monkeypatch.setattr(provider, 'turn', forbidden)
    monkeypatch.setattr(provider, 'stream_turn', forbidden)
    monkeypatch.setattr(provider, 'compact_context', forbidden)
    composer = WorkingContextComposer(store=store, tools=tools, task_notes=notes)
    return SimpleNamespace(db=db, artifacts=artifacts, sources=sources, store=store, wiki=wiki,
                           video_id=video_id, memories=memories, tools=tools, space=space,
                           thread=thread, notes=notes, provider=provider, composer=composer)


def running(c2, text='请比较这个材料，保持全部条件', key='first', *, answer_message_id=None):
    run = c2.store.create_run(c2.thread['id'], text=text, request_id=key, answer_message_id=answer_message_id)
    claimed = c2.store.claim_next_run()
    assert claimed and claimed['id'] == run['id']
    return claimed


def batch(c2, run, calls):
    """Persist native calls, immutable full receipts, then referenced history rows."""
    native = [{'id': cid, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}
              for cid, name, args, _ in calls]
    c2.store.save_assistant_tool_message(run['id'], content='', provider_payload={'tool_calls': native})
    ids = []
    with c2.db.connect() as connection:
        base = connection.execute('SELECT COUNT(*) FROM assistant_tool_calls WHERE run_id=?', (run['id'],)).fetchone()[0]
    for offset, (cid, name, args, result) in enumerate(calls):
        c2.store.begin_tool_call(run['id'], ordinal=base + offset, call_id=cid, name=name, arguments=args)
        c2.store.finish_tool_call(run['id'], call_id=cid, result=result)
        ids.append(c2.store.save_tool_result_message(run['id'], content=json.dumps(result, ensure_ascii=False),
                      provider_payload={'tool_call_id': cid, 'name': name}))
    return ids


def read(c2, call_id='read', *, cursor=None, max_characters=4000):
    return c2.sources.read(call_id=call_id, scope=SourceScope(all_active=True),
        source_ref=f'video:{c2.video_id}', view='summary', cursor=cursor,
        max_characters=max_characters).model_dump(mode='json')


def execute(c2, run, name, args, call_id='tool'):
    return asyncio.run(c2.tools.execute(name=name, arguments=args, call_id=call_id,
                                       run_context=c2.store.run_context(run['id'])))


def seed_checkpoint(c2, candidate, *, retained_ids, text='合成检查点正文', source_ids=None):
    """Synthetic persistence fixture only; no product checkpoint writer in C2."""
    note_id = 'anote_c2_fixture'
    checkpoint = {'format_version': 1, 'text': text, 'identity': candidate.state['identity'],
        'base_revision': candidate.state['revision'], 'replaced_prefix_until_seq': candidate.state['materialized_through_seq'],
        'protected_message_ids': retained_ids, 'source_message_ids': source_ids or [],
        'material_index': candidate.materials}
    with c2.db.connect() as connection:
        connection.execute('INSERT INTO assistant_task_notes(id,thread_id,note_version,scope_version,memory_generation,'
            'covered_until_message_seq,checkpoint_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
            (note_id, c2.thread['id'], 1, c2.space['scope_version'], c2.memories.current_epoch(),
             candidate.state['materialized_through_seq'], json.dumps(checkpoint, ensure_ascii=False), utc_now(), utc_now()))
        state = deepcopy(candidate.state)
        state['entries'] = [e for e in state['entries'] if e['kind'] != 'message' or e['message_id'] in retained_ids]
        state['checkpoint'] = {'id': note_id, 'version': 1}
        connection.execute('UPDATE assistant_threads SET context_state_json=? WHERE id=?',
                           (json.dumps(state, ensure_ascii=False), c2.thread['id']))
    return checkpoint


def test_v26_additive_migration_keeps_history_and_is_idempotent(c2):
    run = running(c2)
    batch(c2, run, [('r', 'collection_read', {'source_ref': f'video:{c2.video_id}', 'view': 'summary'}, read(c2))])
    with c2.db.connect() as connection:
        connection.execute('ALTER TABLE assistant_threads DROP COLUMN context_state_json')
        connection.execute('ALTER TABLE assistant_task_notes DROP COLUMN checkpoint_json')
        connection.execute("UPDATE schema_meta SET value='25' WHERE key='schema_version'")
        before = [tuple(r) for r in connection.execute('SELECT * FROM assistant_messages ORDER BY seq')]
        receipts = [tuple(r) for r in connection.execute('SELECT * FROM assistant_tool_calls ORDER BY ordinal')]
    c2.db.initialize()
    backup = c2.db.path.with_name(c2.db.path.stem + '.pre-v26.backup.db')
    assert backup.is_file()
    c2.db.initialize()
    with c2.db.connect() as connection:
        assert before == [tuple(r) for r in connection.execute('SELECT * FROM assistant_messages ORDER BY seq')]
        assert receipts == [tuple(r) for r in connection.execute('SELECT * FROM assistant_tool_calls ORDER BY ordinal')]
        assert connection.execute('SELECT context_state_json FROM assistant_threads').fetchone()[0] == '{}'
        assert 'checkpoint_json' in {r['name'] for r in connection.execute('PRAGMA table_info(assistant_task_notes)')}
        assert connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0] == '26'
    assert SCHEMA_VERSION == 26


def test_prepare_freeze_append_and_restart_with_exact_native_pairs(c2):
    run = running(c2)
    first = read(c2, 'a')
    second = read(c2, 'b', cursor=first['next_cursor'])
    ids = batch(c2, run, [('a', 'collection_read', {'source_ref': f'video:{c2.video_id}', 'view': 'summary'}, first),
                          ('b', 'collection_read', {'source_ref': f'video:{c2.video_id}', 'view': 'summary', 'cursor': first['next_cursor']}, second)])
    candidate = c2.composer.prepare(run['id'], provider=c2.provider)
    assert c2.store.get_thread(c2.thread['id'], include_internal=True)['context_state'] == {}
    assert not c2.store.get_run(run['id'])['working_state'].get('model_delivered_read_spans')
    assert candidate.request.input_tokens == candidate.budget.input_tokens and candidate.budget.fits
    validate_model_sequence(candidate.request.body['messages'])
    user = next(m for m in c2.store.get_thread(c2.thread['id'])['messages'] if m['role'] == 'user')
    user_projection = candidate.projections[user['id']]['message']
    assert user['content'] in user_projection['content'] and user['created_at'] in user_projection['content']
    assert candidate.metadata['visible_user_message_ids'] == [user['id']]
    c2.composer.persist(candidate)
    assert not any(p['delivery']['confirmed'] for p in candidate.projections.values())
    prefix = deepcopy(candidate.request.body['messages'])
    with pytest.raises(AssistantConflict, match='delivery_changed'):
        c2.store.confirm_model_delivery(run['id'], epoch=run['run_epoch'], spans=[],
            message_ids=candidate.message_ids, context_revision=999)
    assert c2.store.context_read_coverage(c2.thread['id'], source_ref=first['source_refs'][0], view='summary')['ranges'] == []
    c2.store.confirm_model_delivery(run['id'], epoch=run['run_epoch'], spans=[],
        message_ids=[ids[1]], context_revision=candidate.state['revision'])
    assert c2.store.context_read_coverage(c2.thread['id'], source_ref=first['source_refs'][0], view='summary')['missing_ranges'] == [[0, 4000]]
    c2.store.confirm_model_delivery(run['id'], epoch=run['run_epoch'], spans=[{'bogus': True}],
        message_ids=candidate.message_ids, context_revision=candidate.state['revision'])
    actual = c2.store.get_run(run['id'])['working_state']['model_delivered_read_spans']
    assert sorted(actual, key=lambda s: s['start']) == sorted(candidate.read_spans, key=lambda s: s['start'])
    coverage = c2.store.context_read_coverage(c2.thread['id'], source_ref=first['source_refs'][0], view='summary')
    assert coverage['ranges'] == [[0, first['coverage']['read_position']['total']]] and coverage['missing_ranges'] == []
    # Durable projection evidence, not just the bounded Run display, owns confirmation.
    with c2.db.connect() as connection:
        working = json.loads(connection.execute('SELECT working_state_json FROM assistant_runs WHERE id=?', (run['id'],)).fetchone()[0])
        working['model_delivered_materials'] = []
        connection.execute('UPDATE assistant_runs SET working_state_json=? WHERE id=?', (json.dumps(working), run['id']))
        assert c2.wiki._read_view_observed(connection, thread_id=c2.thread['id'], source_ref=first['source_refs'][0], view='summary')
    # Another real read returns the original body even if IO could be reused.
    reread = read(c2, 'again')
    batch(c2, run, [('again', 'collection_read', {'source_ref': f'video:{c2.video_id}', 'view': 'summary'}, reread)])
    appended = c2.composer.prepare(run['id'], provider=c2.provider)
    assert appended.request.body['messages'][:len(prefix)] == prefix
    assert first['items'][0]['content'] in appended.projections[appended.message_ids[-1]]['message']['content']
    c2.composer.persist(appended)
    c2.store.cancel_run(run['id'])
    next_run = running(c2, '继续核对这个材料', key='next')
    reopened = AssistantRunStore(Database(c2.db.path))
    composer = WorkingContextComposer(store=reopened, tools=c2.tools, task_notes=c2.notes)
    restored = composer.prepare(next_run['id'], provider=c2.provider)
    assert restored.request.body['messages'][:len(appended.request.body['messages'])] == appended.request.body['messages']
    assert all(restored.projections[mid]['message'] == appended.projections[mid]['message'] for mid in appended.message_ids)
    assert restored.projections[ids[0]]['delivery']['confirmed']
    assert c2.notes.get(c2.thread['id']) is None


def test_unfrozen_batch_allocation_counts_whole_body_and_preserves_raw(c2):
    # Full descriptions remain in raw results; only first-delivery metadata is bounded.
    c2.db.update_video(c2.video_id, description='长简介' * 12000)
    run = running(c2)
    overview = c2.sources.read(call_id='overview', scope=SourceScope(all_active=True),
                              source_ref=f'video:{c2.video_id}').model_dump(mode='json')
    projected_overview = project_tool_result('collection_read', overview, result_ref='run-result:r:o', sources=c2.sources)
    video = projected_overview['items'][0]['video']
    assert len(video['description_excerpt']) == 1200 and video['description_excerpt_truncated']
    assert video['description_read_args']['view'] == 'description'
    assert len(overview['items'][0]['video']['description']) == 36000
    results = [read(c2, f'b{i}', max_characters=6000) for i in range(2)]
    ids = batch(c2, run, [(f'b{i}', 'collection_read', {'source_ref': f'video:{c2.video_id}', 'view': 'summary'}, value)
                          for i, value in enumerate(results)])
    normal = c2.composer.prepare(run['id'], provider=c2.provider)
    assert '长简介' not in normal.projections[ids[0]]['message']['content']
    constrained = c2.composer.prepare(run['id'], provider=c2.provider,
        input_limit_tokens=normal.request.input_tokens - 7000)
    assert not constrained.budget.fits
    with pytest.raises(ContextBudgetExceeded):
        c2.composer.persist(constrained)
    fitted = c2.composer.fit_unfrozen_tools(constrained, provider=c2.provider)
    assert fitted.budget.fits and fitted.request.input_tokens <= fitted.budget.available_input_tokens
    positions = []
    for mid in ids:
        projection = json.loads(fitted.projections[mid]['message']['content'])
        positions.append(projection['coverage']['read_position'])
        assert projection['status'] == 'ok' and projection['truncated']
        continued = c2.sources.read(call_id='next', scope=SourceScope(all_active=True),
            source_ref=projection['source_refs'][0], view='summary', cursor=projection['next_cursor'], max_characters=2000)
        assert continued.coverage['read_position']['start'] == projection['coverage']['read_position']['end']
    assert abs(positions[0]['end'] - positions[1]['end']) < 40
    validate_model_sequence(fitted.request.body['messages'])
    c2.composer.persist(fitted)
    for index in range(2):
        raw = c2.store.resolve_run_result(f"run-result:{run['id']}:b{index}", current_thread_id=c2.thread['id'], current_scope_version=1)
        assert raw['result'] == results[index]
        assert raw['arguments'] == {'source_ref': f'video:{c2.video_id}', 'view': 'summary'}
    frozen = c2.composer.prepare(run['id'], provider=c2.provider, input_limit_tokens=100)
    with pytest.raises(ContextBudgetExceeded, match='没有可分页'):
        c2.composer.fit_unfrozen_tools(frozen, provider=c2.provider)


def test_checkpoint_low_seq_anchor_save_body_and_api_isolation(c2):
    run = running(c2)
    ids = batch(c2, run, [('old', 'collection_read', {'source_ref': f'video:{c2.video_id}', 'view': 'summary'}, read(c2, 'old'))])
    initial = c2.composer.prepare(run['id'], provider=c2.provider)
    c2.composer.persist(initial)
    c2.store.confirm_model_delivery(run['id'], epoch=run['run_epoch'], spans=[],
        message_ids=initial.message_ids, context_revision=initial.state['revision'])
    user_id = initial.message_ids[0]
    checkpoint = seed_checkpoint(c2, initial, retained_ids=[user_id], text='合成检查点专用标记' + '接续发现' * 2500)
    restored = c2.composer.prepare(run['id'], provider=c2.provider)
    assert restored.checkpoint and restored.request.body['messages'][1]['role'] == 'system'
    assert c2.notes.material_index(restored.checkpoint) == initial.materials
    assert all(m['projection'] == '摘要接续' for m in restored.metadata['material_projection'])
    assert checkpoint['text'] in restored.request.body['messages'][1]['content']  # No 8K business cap.
    assert restored.projections[user_id]['message'] == initial.projections[user_id]['message']
    assert ids[0] not in restored.message_ids and '甲乙丙丁条件' not in str(restored.request.body)
    c2.composer.persist(restored)
    final = c2.composer.prepare(run['id'], provider=c2.provider, tool_schemas=[], output_tokens=8192)
    assert not final.rebuilt and final.request.body['messages'] == restored.request.body['messages']
    assert final.request.body['tools'] == []
    assert c2.store.complete_run(run['id'], epoch=run['run_epoch'], answer='应保存的正式结论与限定条件：甲条件成立，乙未知。', usage={})
    answer = next(m for m in c2.store.get_thread(c2.thread['id'])['messages'] if m['role'] == 'assistant' and m['content'])
    save_run = running(c2, '请保存这份正式结论', key='save', answer_message_id=answer['id'])
    # Synthetic checkpoint has covered the answer, so the save binding must fetch its real text.
    with c2.db.connect() as connection:
        state = json.loads(connection.execute('SELECT context_state_json FROM assistant_threads WHERE id=?', (c2.thread['id'],)).fetchone()[0])
        state['materialized_through_seq'] = answer['seq']
        connection.execute('UPDATE assistant_threads SET context_state_json=? WHERE id=?', (json.dumps(state), c2.thread['id']))
    candidate = c2.composer.prepare(save_run['id'], provider=c2.provider)
    with c2.db.connect() as connection:
        user_id = next(m['id'] for m in candidate.context['thread']['messages'] if m['run_id'] == save_run['id'] and m['role'] == 'user')
        assert c2.wiki._source_delivered(connection, message_id=user_id, ref=initial.read_spans[0]['source_ref'], view='summary')
    assert answer['content'] in str(candidate.request.body) and answer['id'] in str(candidate.request.body)
    assert str(candidate.request.body).count(answer['content']) == 1
    c2.composer.persist(candidate)
    runtime = SimpleNamespace(store=c2.store, sources=c2.sources, memories=c2.memories, wiki=c2.wiki)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(core=SimpleNamespace(
        config=SimpleNamespace(assistant_enabled=True), assistant_runtime=runtime))))
    public = asyncio.run(api_get_thread(c2.thread['id'], request))
    encoded = json.dumps(public, ensure_ascii=False)
    assert 'model_projection' not in encoded and 'context_state' not in encoded and 'checkpoint_json' not in encoded
    assert '合成检查点专用标记' not in encoded
    # Invalid Note cannot leave an active covered-until filter hiding raw history.
    with c2.db.connect() as connection:
        connection.execute("UPDATE assistant_task_notes SET status='stale' WHERE thread_id=?", (c2.thread['id'],))
    rebuilt = c2.composer.prepare(save_run['id'], provider=c2.provider)
    assert rebuilt.rebuilt and rebuilt.checkpoint is None and ids[0] in rebuilt.message_ids
    assert '甲乙丙丁条件' in str(rebuilt.request.body)


def test_history_total_budget_is_lossless_and_keeps_filters(c2):
    run = running(c2, text='甲' * 17)
    assert c2.store.complete_run(run['id'], epoch=run['run_epoch'], answer='乙' * 19, usage={})
    next_run = running(c2, text='丙' * 13, key='history')
    args = {'role': 'all', 'after_seq': 0, 'limit': 2, 'max_characters': 7, 'total_max_characters': 9}
    parts = {}
    for _ in range(20):
        result = execute(c2, next_run, 'conversation_history', args)
        assert list(result['items'][0]) == ['messages']
        assert sum(len(m.get('text', m.get('exact_user_text', ''))) for m in result['items'][0]['messages']) <= 9
        for message in result['items'][0]['messages']:
            parts.setdefault(message['message_id'], '')
            parts[message['message_id']] += message.get('text', message.get('exact_user_text', ''))
        args = result['coverage']['next_read_args']
        if args is None:
            break
        assert args['role'] == 'all' and args['after_seq'] == 0 and args['limit'] == 2
    original = c2.store.get_thread(c2.thread['id'])['messages']
    assert parts == {m['id']: m['content'] for m in original}
    invalid = execute(c2, next_run, 'conversation_history', {'total_max_characters': 24001})
    assert invalid['status'] == 'invalid_arguments'


def test_nested_result_read_and_actual_source_offsets(c2):
    run = running(c2)
    context7 = {'status': 'ok', 'call_id': 'doc', 'items': [{'response': {'content': [
        {'type': 'text', 'text': '公开技术正文' * 10000}]}}], 'coverage': {}}
    material = read(c2, 'source', max_characters=4000)
    batch(c2, run, [('doc', 'context7_query-docs', {'query': 'public API'}, context7),
                    ('source', 'collection_read', {'source_ref': f'video:{c2.video_id}', 'view': 'summary'}, material)])
    result = execute(c2, run, 'run_read_result', {'result_ref': f"run-result:{run['id']}:doc", 'field': 'response.content.0.text', 'start': 7, 'max_characters': 1000})
    assert result['items'][0]['value'] == context7['items'][0]['response']['content'][0]['text'][7:1007]
    assert result['coverage']['next_read_args']['start'] == 1007
    assert result['coverage']['materials'][0]['view'] == '公开文档'
    projected = project_tool_result('context7_query-docs', context7, result_ref=f"run-result:{run['id']}:doc", sources=c2.sources)
    assert len(projected['items'][0]['response']['content'][0]['text']) == 40000
    assert projected['truncated'] and len(context7['items'][0]['response']['content'][0]['text']) == 60000
    source = execute(c2, run, 'run_read_result', {'result_ref': f"run-result:{run['id']}:source", 'field': 'content', 'start': 300, 'max_characters': 1000})
    span = source['coverage']['read_spans'][0]
    assert (span['start'], span['end'], span['view']) == (300, 1300, 'summary')
    assert all(m['view'] == 'summary' for m in source['coverage']['materials'])
    unrelated = execute(c2, run, 'run_read_result', {'result_ref': f"run-result:{run['id']}:source", 'field': 'video.title'})
    assert not unrelated['coverage']['read_spans']


def test_fences_and_invalid_sources_do_not_freeze_candidate(c2):
    run = running(c2)
    batch(c2, run, [('a', 'collection_read', {'source_ref': f'video:{c2.video_id}', 'view': 'summary'}, read(c2, 'a'))])
    candidate = c2.composer.prepare(run['id'], provider=c2.provider)
    c2.store.save_task_focus(run['id'], epoch=run['run_epoch'], focus={
        'goal': '准备后发生的新目标', 'selected_source_refs': [], 'requirements': [],
        'working_notes': '', 'next_actions': []})
    with pytest.raises(AssistantConflict, match='working_context_changed'):
        c2.composer.persist(candidate)
    candidate = c2.composer.prepare(run['id'], provider=c2.provider)
    with c2.db.connect() as connection:
        row = connection.execute('SELECT result_json FROM assistant_tool_calls WHERE run_id=? AND call_id=?', (run['id'], 'a')).fetchone()
        changed = json.loads(row[0]); changed['summary'] = '准备后改变的完整回执'
        connection.execute('UPDATE assistant_tool_calls SET result_json=? WHERE run_id=? AND call_id=?', (json.dumps(changed, ensure_ascii=False), run['id'], 'a'))
    with pytest.raises(AssistantConflict, match='working_projection_invalid'):
        c2.composer.persist(candidate)
    candidate = c2.composer.prepare(run['id'], provider=c2.provider)
    c2.db.update_video(c2.video_id, status='removed')
    with pytest.raises(AssistantConflict, match='working_context_changed'):
        c2.composer.persist(candidate)
    assert c2.store.get_thread(c2.thread['id'], include_internal=True)['context_state'] == {}
    c2.store.cancel_run(run['id'])
    with pytest.raises(AssistantConflict, match='run_fenced'):
        c2.composer.persist(candidate)


def test_full_focus_suffix_and_memory_invalidation_are_not_json_slices(c2):
    run = running(c2, '继续核对合成背景条件')
    memory = c2.memories.save_explicit(text='合成背景条件是离线工作', subject_key='synthetic', kind='context',
        scope_kind='space', scope_id=c2.space['id'], operation_key='c2-memory', pinned=True)
    first = c2.composer.prepare(run['id'], provider=c2.provider)
    assert '合成背景条件是离线工作' in str(first.request.body)
    c2.composer.persist(first)
    unrelated_space = c2.store.create_space(name='独立空间', all_active=True)
    c2.memories.save_explicit(text='独立空间的背景', subject_key='other', kind='context',
        scope_kind='space', scope_id=unrelated_space['id'], operation_key='other-memory')
    unchanged = c2.composer.prepare(run['id'], provider=c2.provider)
    assert unchanged.request.body['messages'] == first.request.body['messages'] and not unchanged.rebuilt
    c2.store.save_task_focus(run['id'], epoch=run['run_epoch'], focus={
        'goal': '完整工作状态', 'requirements': ['完整条件' * 1000], 'working_notes': '详细发现' * 1000,
        'selected_source_refs': [], 'next_actions': ['待核实乙条件']})
    changed = c2.composer.prepare(run['id'], provider=c2.provider)
    focus = next(e for e in changed.state['entries'] if e.get('block_type') == 'task_focus')
    data = json.loads(focus['content'].split('\n', 1)[1])['data']
    assert len(data['working_notes']) == 4000 and data['next_actions'] == ['待核实乙条件']
    assert changed.request.body['messages'][:len(first.request.body['messages'])] == first.request.body['messages']
    c2.composer.persist(changed)
    pending = c2.composer.prepare(run['id'], provider=c2.provider)
    with c2.db.connect() as connection:
        connection.execute("UPDATE assistant_memories SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (memory['id'],))
    with pytest.raises(AssistantConflict, match='working_context_changed'):
        c2.composer.persist(pending)
    with c2.db.connect() as connection:
        connection.execute('UPDATE assistant_memories SET expires_at=NULL WHERE id=?', (memory['id'],))
    c2.memories.forget(memory['id'], expected_version=memory['version'], operation_key='c2-forget')
    valid = c2.composer.prepare(run['id'], provider=c2.provider)
    assert valid.rebuilt and '合成背景条件是离线工作' not in str(valid.request.body)


def test_invalid_multi_call_group_is_not_accepted_by_equal_count(c2):
    run = running(c2)
    results = [read(c2, 'one'), read(c2, 'two')]
    batch(c2, run, [('one', 'collection_read', {}, results[0]), ('two', 'collection_read', {}, results[1])])
    with c2.db.connect() as connection:
        row = connection.execute("SELECT id,provider_payload_json FROM assistant_messages WHERE role='tool' ORDER BY seq DESC LIMIT 1").fetchone()
        payload = json.loads(row['provider_payload_json']); payload['tool_call_id'] = 'one'
        connection.execute('UPDATE assistant_messages SET provider_payload_json=? WHERE id=?', (json.dumps(payload), row['id']))
    with pytest.raises(AssistantConflict, match='incomplete_tool_group'):
        c2.composer.prepare(run['id'], provider=c2.provider)
    assert c2.notes.get(c2.thread['id']) is None


def test_typed_receipts_keep_failure_repair_positions_without_success_drafts(c2):
    raw = {'status': 'partial', 'error_code': 'save_incomplete', 'items': [{
        'id': 'plan', 'version': 3, 'payload': {'topics': [
            {'title': '成功页', 'blocks': [{'markdown': '成功正文' * 6000}]},
            {'title': '待修复页', 'blocks': [{'markdown': '必须保留的失败草稿'}]}]},
        'results': {'0': {'status': 'completed', 'page_id': 'p', 'version': 1},
                    '1': {'status': 'failed', 'issues': [{'path': 'topics[1].blocks[0]', 'code': 'source_not_delivered'}]}}}]}
    projected = project_tool_result('knowledge_save_discussion', raw, result_ref='run-result:r:c', sources=c2.sources)
    assert projected['status'] == raw['status'] and projected['error_code'] == raw['error_code']
    assert '成功正文' not in json.dumps(projected, ensure_ascii=False)
    assert projected['items'][0]['unfinished_topics'] == [{'index': 1, 'topic': raw['items'][0]['payload']['topics'][1]}]
    assert projected['items'][0]['results'] == raw['items'][0]['results']
    assert len(raw['items'][0]['payload']['topics'][0]['blocks'][0]['markdown']) == 24000


def test_invalidated_mixed_memory_group_keeps_verified_operation_data(c2):
    run = running(c2, '请忘记保存的合成偏好')
    memory = c2.memories.save_explicit(text='必须撤销的合成个人偏好', subject_key='old-c2', kind='preference',
        scope_kind='space', scope_id=c2.space['id'], operation_key='seed-forget')
    searched = execute(c2, run, 'memory_search', {'query': '合成个人偏好'}, call_id='search')
    forgotten = execute(c2, run, 'memory_forget', {'memory_id': memory['id'], 'expected_version': 1}, call_id='forget')
    assert forgotten['status'] == 'ok'
    batch(c2, run, [('search', 'memory_search', {'query': '合成个人偏好'}, searched),
                    ('forget', 'memory_forget', {'memory_id': memory['id'], 'expected_version': 1}, forgotten)])
    candidate = c2.composer.prepare(run['id'], provider=c2.provider)
    assert '必须撤销的合成个人偏好' not in str(candidate.request.body)
    block = next(e for e in candidate.state['entries'] if e.get('block_type') == 'operation_receipts')
    receipt = json.loads(block['content'].split('\n', 1)[1])['data'][0]
    assert receipt['result']['status'] == 'ok' and receipt['call']['id'] == 'forget'
    assert not any(m['role'] == 'tool' for m in candidate.request.body['messages'])
    c2.composer.persist(candidate)
    assert c2.notes.get(c2.thread['id']) is None


def test_whole_wiki_blocks_and_search_cards_have_typed_continuations(c2):
    page = {'status': 'ok', 'items': [{'id': 'awiki_synthetic', 'version': 4, 'title': '合成知识页',
        'blocks': [{'stable_id': 'b1', 'markdown': '第一完整块'}, {'stable_id': 'b2', 'markdown': '第二完整块'}]}],
        'coverage': {'mode': 'page', 'start_block': 2}, 'truncated': False}
    projected = project_tool_result('knowledge_read', page, result_ref='run-result:r:p',
                                    sources=c2.sources, body_characters=0)
    assert projected['items'][0]['blocks'] == [] and projected['status'] == 'ok'
    assert projected['coverage']['next_read_args'] == {'page_id': 'awiki_synthetic', 'page_version': 4, 'mode': 'page', 'cursor': '4:3'}
    page['coverage']['mode'] = 'block'
    block = project_tool_result('knowledge_read', page, result_ref='run-result:r:p',
                                sources=c2.sources, body_characters=0)
    assert block['coverage']['next_read_args']['block_ids'] == ['b1', 'b2']
    assert block['next_cursor'] is None
    search = {'status': 'ok', 'items': [{'source': 'collection', 'candidates': [{
        'source_ref': 'video:1', 'title': '候选', 'matched_excerpt': '命中摘要', 'description': '不应展开的长简介',
        'content': '不应展开的正文'}]}, {'source': 'wiki', 'candidates': [{'page_id': 'p', 'hits': [{'block_id': 'b1'}]}]}]}
    cards = project_tool_result('search_knowledge', search, result_ref='run-result:r:s', sources=c2.sources)
    assert cards['items'][0]['candidates'] == [{'source_ref': 'video:1', 'title': '候选', 'matched_excerpt': '命中摘要'}]
    assert cards['items'][1] == search['items'][1] and 'description' in search['items'][0]['candidates'][0]


def test_cancelled_incomplete_unit_does_not_fabricate_or_block_next_run(c2):
    run = running(c2, '取消前的真实要求')
    native = [{'id': cid, 'type': 'function', 'function': {'name': 'collection_read', 'arguments': '{}'}}
              for cid in ('done', 'missing')]
    c2.store.save_assistant_tool_message(run['id'], content='', provider_payload={'tool_calls': native})
    result = read(c2, 'done')
    c2.store.begin_tool_call(run['id'], ordinal=0, call_id='done', name='collection_read', arguments={})
    c2.store.finish_tool_call(run['id'], call_id='done', result=result)
    c2.store.save_tool_result_message(run['id'], content=json.dumps(result, ensure_ascii=False),
                                     provider_payload={'tool_call_id': 'done', 'name': 'collection_read'})
    with pytest.raises(AssistantConflict, match='incomplete_tool_group'):
        c2.composer.prepare(run['id'], provider=c2.provider)
    c2.store.cancel_run(run['id'])
    current = running(c2, '继续当前可确认结果', key='after-cancel')
    candidate = c2.composer.prepare(current['id'], provider=c2.provider)
    assert '取消前的真实要求' in str(candidate.request.body)
    assert not any(m.get('tool_calls') or m['role'] == 'tool' for m in candidate.request.body['messages'])
    raw = c2.store.resolve_run_result(f"run-result:{run['id']}:done", current_thread_id=c2.thread['id'], current_scope_version=1)
    assert raw['result'] == result
    c2.composer.persist(candidate)
