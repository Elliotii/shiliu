from __future__ import annotations

import asyncio
import copy
import json

import pytest

from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.store import AssistantConflict
from test_assistant_stage_c import _services, _add_material
from test_assistant_consolidation_nb import _run, _topics


def fixture(app_paths):
    db, artifacts, sources, store, wiki = _services(app_paths)
    space = store.create_space(name='W1 isolated', all_active=True)
    tools = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    return db, artifacts, sources, store, wiki, space, tools


def execute(tools, store, run, args, call='save', name='knowledge_save_discussion', replay=False):
    return asyncio.run(tools.execute(name=name, arguments=args, call_id=call,
        run_context=store.run_context(run['id']), replay=replay))


def test_schema_correction_and_different_calls_share_one_single_page_plan(app_paths):
    db, _, _, store, wiki, space, tools = fixture(app_paths)
    run, _ = _run(store, space['id'], '请保存刚才的讨论成果', key='single')
    args = {'topics': [_topics()[0]]}
    wrong = copy.deepcopy(args); wrong['topics'][0]['blocks'][0]['omitted'] = ['不是块字段']
    failed = execute(tools, store, run, wrong)
    assert failed['status'] == 'invalid_arguments'
    assert failed['items'][0]['issues'][0]['path'] == 'topics[0].blocks[0].omitted'
    assert wiki.list_discussion_plans(space_id=space['id']) == []
    first = execute(tools, store, run, args, 'corrected')
    assert first['status'] == 'ok', first
    second = execute(tools, store, run, args, 'another-call')
    assert first['items'][0]['id'] == second['items'][0]['id']
    assert 'repair_count' not in store.knowledge_save_request(run['id'])
    assert len(wiki.list_discussion_plans(space_id=space['id'])) == 1
    assert len(wiki.list_pages(space_id=space['id'])) == 1
    assert wiki.list_pages(space_id=space['id'])[0]['version'] == 1
    assert 'knowledge_save_outcome' not in [s['function']['name'] for s in tools.schemas()]
    assert execute(tools, store, run, {}, 'retired', name='knowledge_save_outcome')['error_code'] == 'retired_tool'


def test_partial_personal_repair_keeps_success_and_real_prior_quote(app_paths):
    _, _, _, store, wiki, space, tools = fixture(app_paths)
    old, context = _run(store, space['id'], '我实拍时觉得这个场景景深太浅', key='quote')
    quote_id = context['thread']['messages'][-1]['id']
    run, _ = _run(store, space['id'], '请把这些讨论保存为两页知识', thread_id=old['thread_id'], key='save-personal')
    topics = _topics(); topics[1]['blocks'] = [{'role': 'personal', 'heading': '实拍体验',
        'markdown': '我实拍时觉得这个场景景深太浅', 'user_quote': '我实拍时觉得这个场景景深太浅'}]
    partial = execute(tools, store, run, {'topics': topics})
    assert partial['status'] == 'partial', partial
    plan = partial['items'][0]
    first_page = wiki.list_pages(space_id=space['id'])[0]
    fixed = execute(tools, store, run, {'plan_id': plan['id'], 'expected_version': plan['version'],
        'replacements': [{'index': 1, 'topic': {**topics[1], 'blocks': [{**topics[1]['blocks'][0], 'user_message_id': quote_id}]}}]}, 'fix')
    assert fixed['status'] == 'ok', fixed
    assert fixed['items'][0]['id'] == plan['id'] and fixed['items'][0]['status'] == 'completed'
    assert len(wiki.list_pages(space_id=space['id'])) == 2
    assert wiki.get_page(first_page['id'], space_id=space['id'])['version'] == first_page['version']
    assert fixed['items'][0]['payload']['original_topics'][1]['blocks'][0].get('user_message_id') is None
    final = execute(tools, store, run, {'topics': topics}, 'refresh')
    assert final['items'][0]['status'] == 'completed'
    assert len(wiki.list_pages(space_id=space['id'])) == 2


def test_page_receipt_recovers_after_commit_before_plan_result(app_paths, monkeypatch):
    _, _, _, store, wiki, space, tools = fixture(app_paths)
    run, _ = _run(store, space['id'], '请保存这两个讨论主题', key='crash')
    original = wiki.save_discussion
    def crash_once(**kwargs):
        original(**kwargs)
        raise RuntimeError('connection lost after commit')
    monkeypatch.setattr(wiki, 'save_discussion', crash_once)
    unknown = execute(tools, store, run, {'topics': _topics()})
    assert unknown['status'] == 'outcome_unknown', unknown
    page = wiki.list_pages(space_id=space['id'])[0]
    monkeypatch.setattr(wiki, 'save_discussion', original)
    resumed = execute(tools, store, run, {'topics': _topics()}, 'after-restart')
    assert resumed['status'] == 'ok', resumed
    assert len(wiki.list_discussion_plans(space_id=space['id'])) == 1
    assert len(wiki.list_pages(space_id=space['id'])) == 2
    assert wiki.get_page(page['id'], space_id=space['id'])['version'] == 1


def test_schema_errors_share_t_budget_without_save_specific_limit(app_paths):
    _, _, _, store, wiki, space, tools = fixture(app_paths)
    run, _ = _run(store, space['id'], '请保存讨论', key='cap')
    for index in range(3):
        assert execute(tools, store, run, {'topics': []}, str(index))['status'] == 'invalid_arguments'
    saved = execute(tools, store, run, {'topics': [_topics()[0]]}, 'fourth')
    assert saved['status'] == 'ok'
    assert len(wiki.list_pages(space_id=space['id'])) == 1


def test_delivery_required_then_local_source_repair(app_paths):
    db, artifacts, sources, store, wiki, space, tools = fixture(app_paths)
    source_id = db.create_favorite_source(folder_id=481, folder_title='W1', history_policy='all')
    video_id = _add_material(db, artifacts, source_id, bvid='BV1W10000001', title='正文材料', text='有条件的正文')
    ref = f'video:{video_id}:{sources.snapshots.capture(video_id).revision}'
    run, _ = _run(store, space['id'], '请保存这条材料结论', key='delivery')
    args = {'topics': [{'title': '正文条件', 'purpose': '保留原文', 'blocks': [
        {'role': 'source', 'heading': '条件', 'markdown': '有条件的正文', 'source_refs': [ref], 'source_view': 'transcript'}]}]}
    store.begin_tool_call(run['id'], ordinal=1, call_id='read', name='collection_read', arguments={'view': 'transcript'})
    store.finish_tool_call(run['id'], call_id='read', result={'status': 'ok', 'source_refs': [ref]})
    partial = execute(tools, store, run, args)
    assert partial['status'] == 'partial'
    plan = partial['items'][0]
    assert 'source_not_delivered' in json.dumps(plan)
    with db.connect() as c:
        working = json.loads(c.execute('SELECT working_state_json FROM assistant_runs WHERE id=?', (run['id'],)).fetchone()[0])
        working['model_delivered_materials'] = [{'source_ref': ref, 'kind': 'collection_read', 'view': 'transcript', 'projection': '正文'}]
        c.execute('UPDATE assistant_runs SET working_state_json=? WHERE id=?', (json.dumps(working), run['id']))
    fixed = execute(tools, store, run, {'plan_id': plan['id'], 'expected_version': plan['version'],
        'replacements': [{'index': 0, 'topic': args['topics'][0]}]}, 'fix')
    assert fixed['status'] == 'ok', fixed


def test_request_id_freezes_official_answer_and_rejects_cross_thread(app_paths):
    _, _, _, store, _, space, _ = fixture(app_paths)
    thread = store.create_thread(space['id'])
    run = store.create_run(thread['id'], text='讨论', request_id='answer')
    claimed = store.claim_next_run()
    store.complete_run(run['id'], epoch=claimed['run_epoch'], answer='可保存的正式答案', usage={})
    answer = next(m for m in store.get_thread(thread['id'])['messages'] if m['role'] == 'assistant')
    saved = store.create_run(thread['id'], text='请保存讨论', request_id='ui-save', answer_message_id=answer['id'])
    assert saved['working_state']['knowledge_save']['answer_message_id'] == answer['id']
    repeated = store.create_run(thread['id'], text='不同文字也不得改变原对象', request_id='ui-save', answer_message_id='fake')
    assert repeated['id'] == saved['id']
    other = store.create_thread(space['id'])
    with pytest.raises(AssistantConflict, match='save_answer_not_available'):
        store.create_run(other['id'], text='请保存讨论', request_id='bad', answer_message_id=answer['id'])


def test_preview_repair_and_confirmation_share_candidate(app_paths):
    _, _, _, store, wiki, space, tools = fixture(app_paths)
    run, _ = _run(store, space['id'], '请先给一页提案，确认后再保存', key='preview')
    result = execute(tools, store, run, {'topics': [_topics()[0]]}, name='knowledge_propose')
    assert result['status'] == 'ok'
    plan = result['items'][0]
    assert plan['status'] == 'pending' and wiki.list_pages(space_id=space['id']) == []
    confirm, _ = _run(store, space['id'], '可以了，按这个存', thread_id=run['thread_id'], key='confirm')
    saved = execute(tools, store, confirm, {'plan_id': plan['id'], 'expected_version': 1, 'accept': True}, name='knowledge_confirm')
    assert saved['status'] == 'ok', json.dumps(saved, ensure_ascii=False)
    assert saved['items'][0]['id'] == plan['id'] and len(wiki.list_pages(space_id=space['id'])) == 1


def test_registered_legacy_pending_restores_original_receipt_only(app_paths):
    from test_assistant_k import graph_for, AnswerProvider
    _, _, _, store, wiki, space, tools = fixture(app_paths)
    run, context = _run(store, space['id'], '请保存这份讨论成果', key='legacy')
    claimed = store.claim_next_run()
    user_id = next(m['id'] for m in context['thread']['messages'] if m['role'] == 'user')
    args = {k: v for k, v in _topics()[0].items() if k in {'title', 'purpose', 'blocks'}}
    page = wiki.save_discussion(space_id=space['id'], source_message_id=user_id,
        operation_key=f"tool:{run['id']}:old", **args)
    call = {'id': 'old', 'type': 'function', 'function': {'name': 'knowledge_save_outcome', 'arguments': json.dumps(args)}}
    store.save_assistant_tool_message(run['id'], content='', provider_payload={'tool_calls': [call]})
    store.begin_tool_call(run['id'], ordinal=1, call_id='old', name='knowledge_save_outcome', arguments=args)
    engine = graph_for(store, tools, AnswerProvider())  # Freeze only calls persisted before W1.
    asyncio.run(engine.run(claimed))
    assert store.get_run(run['id'])['status'] == 'completed'
    assert len(wiki.list_pages(space_id=space['id'])) == 1
    assert wiki.get_page(page['id'], space_id=space['id'])['version'] == 1
    assert wiki.list_discussion_plans(space_id=space['id']) == []


def test_replacement_cannot_edit_completed_topic_but_can_correct_role(app_paths):
    _, _, _, store, wiki, space, tools = fixture(app_paths)
    run, _ = _run(store, space['id'], '请保存两个讨论主题', key='immutable')
    topics = _topics(); topics[1]['blocks'][0] = {'role': 'source', 'heading': '没有依据', 'markdown': '不得冒充已读'}
    plan = execute(tools, store, run, {'topics': topics})['items'][0]
    denied = execute(tools, store, run, {'plan_id': plan['id'], 'expected_version': 1,
        'replacements': [{'index': 0, 'topic': topics[0]}]}, 'edit-success')
    assert denied['error_code'] == 'knowledge_topic_already_completed'
    denied = execute(tools, store, run, {'plan_id': plan['id'], 'expected_version': 1,
        'replacements': [{'index': 1, 'topic': {**topics[1], 'blocks': [{**topics[1]['blocks'][0], 'role': 'analysis'}]}}]}, 'role-change')
    assert denied['status'] == 'ok'
    assert all(page['version'] == 1 for page in wiki.list_pages(space_id=space['id']))


@pytest.mark.parametrize('bad_kind', ['other_thread', 'assistant', 'suppressed'])
def test_personal_identity_and_current_authorization_are_separate(app_paths, bad_kind):
    _, _, _, store, wiki, space, tools = fixture(app_paths)
    text = '我实拍时发现景深太浅'
    old, context = _run(store, space['id'], text, key='prior')
    quote_id = context['thread']['messages'][-1]['id']
    thread_id = old['thread_id']
    if bad_kind == 'other_thread':
        thread_id = store.create_thread(space['id'])['id']
    if bad_kind == 'assistant':
        quote_id = store.save_assistant_tool_message(old['id'], content=text, provider_payload={})
    if bad_kind == 'suppressed':
        memories = MemoryService(store.db)
        memory = memories.save_explicit(text=text, subject_key='体验', kind='context', scope_kind='space',
            scope_id=space['id'], source_message_ids=[quote_id], operation_key='prior-memory')
        memories.forget(memory['id'], expected_version=memory['version'], operation_key='forget')
    run, _ = _run(store, space['id'], '请保存这条体验',
                  thread_id=thread_id, key='new')
    result = execute(tools, store, run, {'topics': [{'title': '体验', 'purpose': '实拍', 'blocks': [
        {'role': 'personal', 'heading': '个人', 'markdown': text, 'user_quote': text, 'user_message_id': quote_id}]}]})
    assert result['status'] in {'partial', 'invalid_arguments', 'unavailable'}
    assert wiki.list_pages(space_id=space['id']) == []


def test_json_format_repair_uses_t_dispatches_without_save_cap(app_paths):
    from shiliu.domain import PipelineError
    from shiliu.assistant.provider import ModelTurn, NativeToolCall
    from test_assistant_k import graph_for, AnswerProvider
    _, _, _, store, wiki, space, tools = fixture(app_paths)
    run, _ = _run(store, space['id'], '请保存讨论成果', key='json')
    claimed = store.claim_next_run()
    class Provider(AnswerProvider):
        def turn(self, **kwargs):
            self.requests.append(kwargs['messages'])
            n = len(self.requests)
            if n == 1:
                error = PipelineError('broken JSON', code='tool_arguments_invalid', retryable=False)
                error.tool_names = ['knowledge_save_discussion']; error.usage = {'total_tokens': 7}
                raise error
            if n < 4:
                return ModelTurn(text='', tool_calls=[NativeToolCall(call_id=f's{n}', name='knowledge_save_discussion',
                    arguments={'topics': [] if n == 2 else [_topics()[0]]})], usage={'total_tokens': 3})
            return ModelTurn(text='已保存一页。', usage={'total_tokens': 2})
    provider = Provider()
    asyncio.run(graph_for(store, tools, provider).run(claimed))
    current = store.get_run(run['id'])
    assert current['status'] == 'completed' and current['usage']['total_tokens'] == 15
    assert current['working_state']['execution_budget']['model_calls'] == 4
    assert not current['working_state'].get('knowledge_save')
    assert wiki.list_pages(space_id=space['id'])[0]['version'] == 1


def test_repair_receipt_survives_interruption_before_page_commit(app_paths, monkeypatch):
    _, _, _, store, wiki, space, tools = fixture(app_paths)
    old, context = _run(store, space['id'], '我实拍时发现景深太浅', key='old')
    quote_id = context['thread']['messages'][-1]['id']
    run, _ = _run(store, space['id'], '请保存讨论体验', thread_id=old['thread_id'], key='repair-crash')
    args = {'topics': [{'title': '体验', 'purpose': '实拍', 'blocks': [{'role': 'personal',
        'heading': '体验', 'markdown': '我实拍时发现景深太浅', 'user_quote': '我实拍时发现景深太浅'}]}]}
    plan = execute(tools, store, run, args)['items'][0]
    corrections = {'plan_id': plan['id'], 'expected_version': 1,
        'replacements': [{'index': 0, 'topic': {**args['topics'][0], 'blocks': [{**args['topics'][0]['blocks'][0], 'user_message_id': quote_id}]}}]}
    decide = wiki.decide_discussion_plan
    monkeypatch.setattr(wiki, 'decide_discussion_plan', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('after repair commit')))
    assert execute(tools, store, run, corrections, 'same-repair')['status'] == 'outcome_unknown'
    monkeypatch.setattr(wiki, 'decide_discussion_plan', decide)
    result = execute(tools, store, run, corrections, 'same-repair')
    assert result['status'] == 'ok', result
    assert result['items'][0]['version'] == 2
    assert 'repair_count' not in store.knowledge_save_request(run['id'])
    assert wiki.list_pages(space_id=space['id'])[0]['version'] == 1


def test_attached_metadata_and_time_are_delivery_not_transcript(app_paths):
    db, artifacts, sources, store, wiki, space, tools = fixture(app_paths)
    source_id = db.create_favorite_source(folder_id=482, folder_title='W1 metadata', history_policy='all')
    video_id = _add_material(db, artifacts, source_id, bvid='BV1W10000002', title='日期材料', text='正文')
    ref = f'video:{video_id}:{sources.snapshots.capture(video_id).revision}'
    run, _ = _run(store, space['id'], '请保存这些材料的标题信息', key='metadata')
    result = {'source_refs': [ref], 'items': [{'source_ref': f'video:{video_id}', 'video': {'title': '日期材料'},
        'time': {'published_at': None}}], 'coverage': {'requested_view': 'overview'}}
    from shiliu.assistant.delivery import read_evidence
    _, projection = read_evidence('collection_read', result, result_ref=f"run-result:{run['id']}:metadata")
    with db.connect() as c:
        working = json.loads(c.execute('SELECT working_state_json FROM assistant_runs WHERE id=?', (run['id'],)).fetchone()[0])
        working['model_delivered_materials'] = projection
        c.execute('UPDATE assistant_runs SET working_state_json=? WHERE id=?', (json.dumps(working), run['id']))
    args = {'topics': [{'title': '标题记录', 'purpose': '元数据', 'blocks': [{'role': 'source', 'heading': '标题',
        'markdown': '标题是日期材料，发布时间未知。', 'source_refs': [ref], 'source_view': 'metadata'}]}]}
    assert execute(tools, store, run, args)['status'] == 'ok'
    assert not any(item.get('view') == 'transcript' for item in projection)


def test_wiki_evidence_keeps_lineage_identity_and_task_subset(app_paths):
    db, artifacts, sources, store, wiki, space, tools = fixture(app_paths)
    source_id = db.create_favorite_source(folder_id=483, folder_title='W1 wiki', history_policy='all')
    video_id = _add_material(db, artifacts, source_id, bvid='BV1W10000003', title='来源甲', text='原材料条件')
    other_id = _add_material(db, artifacts, source_id, bvid='BV1W10000004', title='来源乙', text='其他材料')
    ref = f'video:{video_id}:{sources.snapshots.capture(video_id).revision}'
    old, context = _run(store, space['id'], '先研究这条材料', key='wiki-basis')
    with db.connect() as c:
        working = json.loads(c.execute('SELECT working_state_json FROM assistant_runs WHERE id=?',(old['id'],)).fetchone()[0])
        working['model_delivered_materials']=[{'source_ref':ref,'kind':'collection_read','view':'transcript','projection':'正文'}]
        c.execute('UPDATE assistant_runs SET working_state_json=? WHERE id=?',(json.dumps(working),old['id']))
    page = wiki.save_discussion(space_id=space['id'], source_message_id=context['thread']['messages'][-1]['id'],
        operation_key='fixture-wiki', title='原知识页', purpose='条件', blocks=[{'role': 'source', 'heading': '材料',
        'markdown': '原材料条件', 'source_refs': [ref]}])
    run, _ = _run(store, space['id'], '请保存这个知识页的条件讨论', thread_id=old['thread_id'], key='wiki-save')
    wiki_ref = f"wiki:{page['id']}:{page['version']}"
    with db.connect() as c:
        working = json.loads(c.execute('SELECT working_state_json FROM assistant_runs WHERE id=?', (run['id'],)).fetchone()[0])
        working['model_delivered_materials'] = [{'source_ref': wiki_ref, 'kind': 'knowledge_read', 'view': '知识页正文',
            'projection': '知识页正文', 'position': {'block_ids': [b['stable_id'] for b in page['blocks']]}, 'lineage_refs': [ref]}]
        working['task_subset'] = {'video_ids': [other_id], 'scope_version': space['scope_version']}
        c.execute('UPDATE assistant_runs SET working_state_json=? WHERE id=?', (json.dumps(working), run['id']))
    args = {'topics': [{'title': '讨论页', 'purpose': '保存知识页依据', 'blocks': [{'role': 'source', 'heading': '条件',
        'markdown': '原材料条件', 'source_refs': [ref], 'evidence_ref': wiki_ref}]}]}
    denied = execute(tools, store, run, args)
    assert denied['status'] == 'partial'
    assert 'wiki_source_out_of_scope' in json.dumps(denied)
    assert len(wiki.list_pages(space_id=space['id'])) == 1
    with db.connect() as c:
        working['task_subset'] = {'video_ids': [video_id], 'scope_version': space['scope_version']}
        c.execute('UPDATE assistant_runs SET working_state_json=? WHERE id=?', (json.dumps(working), run['id']))
    plan = denied['items'][0]
    saved = execute(tools, store, run, {'plan_id': plan['id'], 'expected_version': 1,
        'replacements': [{'index': 0, 'topic': args['topics'][0]}]}, 'scope-fixed')
    assert saved['status'] == 'ok', json.dumps(saved, ensure_ascii=False)
    new_page = wiki.get_page(saved['items'][0]['results']['0']['page_id'], space_id=space['id'])
    assert new_page['blocks'][0]['evidence_ref'] == wiki_ref
    assert not new_page['blocks'][0].get('source_view')  # Wiki lineage is not a transcript Read.
