"""Offline Runtime and save-tool regressions for the real-trial follow-up."""
from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import replace

import pytest

from test_assistant_context_c2 import c2, running, execute as tool, batch, read
from test_assistant_context_c3 import c3, history, notes
from test_assistant_w1 import fixture, execute
from test_assistant_consolidation_nb import _run, _topics
from test_assistant_real_use_a import material
from shiliu.assistant.provider import ModelTurn
from shiliu.domain import PipelineError


def test_new_topics_edit_same_page_keeps_sources_notes_and_completed_plan(app_paths):
    db, artifacts, sources, store, wiki, space, tools = fixture(app_paths)
    run, context = _run(store, space['id'], '保存讨论；我的笔记是先核对条件')
    user_id = context['thread']['messages'][-1]['id']
    ref = material(db, artifacts, sources, store, run, 1, 'summary')
    topic = _topics()[0]
    topic['blocks'] += [
        {'role': 'source', 'heading': '来源条件', 'markdown': '有条件正文',
         'source_refs': [ref], 'source_view': 'summary'},
        {'role': 'personal', 'heading': '我的笔记', 'markdown': '先核对条件',
         'user_quote': '先核对条件', 'user_message_id': user_id},
    ]
    saved = execute(tools, store, run, {'topics': [topic]})
    assert saved['status'] == 'ok', saved
    original_plan = saved['items'][0]
    original_page = wiki.list_pages(space_id=space['id'])[0]
    with db.connect() as connection:
        original_row = dict(connection.execute('SELECT * FROM assistant_knowledge_plans WHERE id=?', (original_plan['id'],)).fetchone())
    edit, _ = _run(store, space['id'], '请把已保存页的判断更正为条件已核实，保留其他内容',
                   thread_id=run['thread_id'], key='edit')
    updated_topic = copy.deepcopy(topic)
    updated_topic['expected_version'] = original_page['version']
    updated_topic['blocks'][0]['markdown'] = '条件已核实。'
    updated = execute(tools, store, edit, {'topics': [updated_topic]}, 'edit')
    assert updated['status'] == 'ok', updated
    page = wiki.get_page(original_page['id'], space_id=space['id'])
    assert len(wiki.list_pages(space_id=space['id'])) == 1
    assert page['version'] == original_page['version'] + 1
    assert updated['items'][0]['id'] != original_plan['id']
    assert all(b['markdown'] != '条件不同，需要分别核对。' for b in page['blocks'])
    assert [b['markdown'] for b in page['blocks']] == ['条件已核实。', '有条件正文', '先核对条件']
    assert page['blocks'][1]['source_refs'] == original_page['blocks'][1]['source_refs']
    assert page['blocks'][2] == original_page['blocks'][2]
    assert execute(tools, store, edit, {'topics': [updated_topic]}, 'repeat')['items'][0]['id'] == updated['items'][0]['id']
    assert wiki.get_page(page['id'], space_id=space['id'])['version'] == page['version']
    with db.connect() as connection:
        assert dict(connection.execute('SELECT * FROM assistant_knowledge_plans WHERE id=?', (original_plan['id'],)).fetchone()) == original_row


def test_runtime_commits_real_identity_keeps_examples_and_save_binding(c3):
    fake = 'amsg_model_invented'
    examples = '\n> 【正式回答 message_id: quoted_example】\n\n```text\n【正式回答 message_id: code_example】\n```'
    body = '有效成果：条件已核实。' + examples
    raw = f'【正式回答 message_id: {fake}】\n{body}'
    c3.provider.main = lambda request: ModelTurn(raw, [], 'stop', {'total_tokens': 11})
    run = running(c3, text='请核对条件')
    asyncio.run(c3.graph.run(run))
    thread = c3.store.get_thread(c3.thread['id'])
    answer = next(m for m in thread['messages'] if m['role'] == 'assistant')
    assert answer['content'] == body and answer['id'] != fake
    assert c3.store.get_run(run['id'])['status'] == 'completed'
    from shiliu.assistant.api import get_thread as api_get_thread
    from types import SimpleNamespace
    runtime = SimpleNamespace(store=c3.store, sources=c3.sources, memories=c3.memories, wiki=c3.wiki)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(core=SimpleNamespace(
        config=SimpleNamespace(assistant_enabled=True), assistant_runtime=runtime))))
    visible = asyncio.run(api_get_thread(c3.thread['id'], request))['thread']
    assert next(m for m in visible['messages'] if m['id'] == answer['id'])['content'] == body
    save = running(c3, text='请保存刚才的成果', key='save')
    candidate = c3.composer.prepare(save['id'], provider=c3.provider)
    projected = next(m for m in candidate.request.body['messages'] if body in str(m.get('content')))
    assert projected['content'] == f"【正式回答 message_id: {answer['id']}】\n{body}"
    args = {'topics': [_topics()[0]], 'answer_message_ids': [fake]}
    rejected = tool(c3, save, 'knowledge_save_discussion', args, 'fake')
    assert rejected['error_code'] == 'save_message_not_available'
    assert not c3.tools.wiki.list_pages(space_id=c3.space['id'])
    args['answer_message_ids'] = [answer['id']]
    saved = tool(c3, save, 'knowledge_save_discussion', args, 'real')
    assert saved['status'] == 'ok', saved
    assert saved['items'][0]['payload']['save_request']['answer_message_ids'] == [answer['id']]
    assert len(c3.tools.wiki.list_pages(space_id=c3.space['id'])) == 1
    # A quotation or fenced example at the very start must also remain intact.
    from shiliu.assistant.runtime import AssistantExecutionGraph
    assert AssistantExecutionGraph._presentable_answer(examples.strip()) == examples.strip()


def test_plan_state_error_differs_from_real_version_conflict(app_paths):
    _, _, _, store, wiki, space, tools = fixture(app_paths)
    run, _ = _run(store, space['id'], '保存讨论')
    topic = _topics()[0]
    saved = execute(tools, store, run, {'topics': [topic]})
    completed = saved['items'][0]
    denied = execute(tools, store, run, {'plan_id': completed['id'], 'expected_version': completed['version'],
        'replacements': [{'index': 0, 'topic': topic}]}, 'completed')
    assert denied['status'] == 'invalid_arguments' and denied['error_code'] == 'knowledge_plan_not_repairable'
    assert 'topics' in denied['summary'] and 'topic.expected_version' in denied['summary']
    pending_run, _ = _run(store, space['id'], '先给我看另一份提案，确认后再保存',
                           thread_id=run['thread_id'], key='pending')
    pending = execute(tools, store, pending_run, {'topics': [_topics()[1]]}, 'propose', name='knowledge_propose')['items'][0]
    conflict = execute(tools, store, pending_run, {'plan_id': pending['id'], 'expected_version': pending['version'] + 1,
        'replacements': [{'index': 0, 'topic': _topics()[1]}]}, 'conflict')
    assert conflict['error_code'] == 'knowledge_plan_version_conflict'
    assert conflict['summary'] != denied['summary']
    assert wiki.get_page(saved['items'][0]['results']['0']['page_id'], space_id=space['id'])['version'] == 1


def test_summary_79k_independent_of_64k_main_and_endpoint_run_limits(c3):
    messages = [{'role': 'user', 'content': '摘' * 79000}]
    request = c3.provider.prepare_compaction(messages=messages, remaining_tokens=200000)
    assert 79000 < request.input_tokens < 80000
    assert request.body['max_tokens'] == 65536
    assert not c3.provider.budget_request(request, input_limit_tokens=64000).fits
    with pytest.raises(PipelineError, match='摘要输入超过'):
        c3.provider.prepare_compaction(messages=messages, remaining_tokens=200000, input_limit_tokens=64000)
    for caps, remaining in [(c3.provider.capabilities, request.input_tokens),
                            (replace(c3.provider.capabilities, shared_window_tokens=request.input_tokens), 200000)]:
        c3.provider.capabilities = caps
        with pytest.raises(PipelineError) as caught:
            c3.provider.prepare_compaction(messages=messages, remaining_tokens=remaining)
        assert caught.value.code == 'provider_capacity_invalid'
    assert not c3.provider.sent


def test_runtime_large_summary_returns_to_main_limit(c3):
    run, state, _ = history(c3, count=23)
    c3.composer.input_budget_tokens = 64000
    c3.graph.compaction_soft_target = 32000
    output = asyncio.run(c3.graph._model(state))
    assert output['route'] == 'final'
    assert [r.purpose for r in c3.provider.sent] == ['compact', 'turn']
    summary, main = c3.provider.sent
    assert summary.input_tokens > 79000
    assert summary.body['max_tokens'] == 65536
    assert c3.provider.budget_request(main, input_limit_tokens=64000).fits
    assert c3.composer.input_budget_tokens == 64000 and len(notes(c3)) == 1


def discarded(c3, run):
    return [e['payload'] for e in c3.store.events(run['id']) if e['event_type'] == 'context_compaction_discarded']


@pytest.mark.parametrize('hard', [False, True])
def test_summary_prepare_failure_preserves_cause_and_legal_dispatch_rule(c3, monkeypatch, hard):
    run, state, before = history(c3)
    if hard:
        c3.composer.input_budget_tokens = before.request.input_tokens - 1
    def rejected(**kwargs):
        raise PipelineError('会话摘要没有可用输入/输出额度', code='provider_capacity_invalid', retryable=False)
    monkeypatch.setattr(c3.provider, 'prepare_compaction', rejected)
    output = asyncio.run(c3.graph._model(state))
    failures = discarded(c3, run)
    assert failures == [{'stage': 'prepare', 'dispatched': False,
                         'code': 'provider_capacity_invalid', 'reason': '会话摘要没有可用输入/输出额度'}]
    assert not notes(c3)
    if hard:
        assert output['route'] == 'stopped' and not c3.provider.sent
        failed_run = c3.store.get_run(run['id'])
        assert failed_run['last_error_code'] == 'context_recovery_failed'
        assert 'provider_capacity_invalid' in failed_run['last_error_message']
        assert 'prepare' in failed_run['last_error_message'] and '容量恢复未完成' in failed_run['last_error_message']
    else:
        assert output['route'] == 'final'
        assert len(c3.provider.sent) == 1 and c3.provider.sent[0].purpose == 'turn'
        assert c3.provider.sent[0].body['messages'] == before.request.body['messages']
        asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
        assert len(discarded(c3, run)) == 1


def test_wiki_read_sources_can_save_with_wiki_evidence_without_original_reread(c3):
    research = running(c3, text='研究当前材料')
    result = read(c3, 'original')
    ref = result['source_refs'][0]
    batch(c3, research, [('original', 'collection_read',
                         {'source_ref': ref, 'view': 'summary'}, result)])
    asyncio.run(c3.graph.run(research))
    save = running(c3, text='保存研究结果', key='source-page')
    block = {'role': 'source', 'heading': '来源条件', 'markdown': '甲乙丙丁条件。',
             'source_refs': [ref], 'source_view': 'summary'}
    saved = tool(c3, save, 'knowledge_save_discussion', {'topics': [
        {'title': '原知识页', 'purpose': '保存来源条件', 'blocks': [block]}]}, 'save')
    page_id = saved['items'][0]['results']['0']['page_id']
    assert c3.store.complete_run(save['id'], epoch=save['run_epoch'], answer='已保存', usage={})
    # Another thread has only the actual Wiki read, no original-video delivery.
    c3.thread = c3.store.create_thread(c3.space['id'])
    reading = running(c3, text='读取知识页', key='wiki-read')
    args = {'page_id': page_id, 'page_version': 1, 'mode': 'page'}
    wiki_read = tool(c3, reading, 'knowledge_read', args, 'wiki')
    page = wiki_read['items'][0]
    assert page['blocks'][0]['source_refs'] == [ref]
    assert page['evidence_ref'] == f'wiki:{page_id}:1'
    batch(c3, reading, [('wiki', 'knowledge_read', args, wiki_read)])
    asyncio.run(c3.graph.run(reading))
    # Both an unchanged legacy hash receipt and the new complete reference remain
    # valid; compare without rewriting either historical result.
    legacy = copy.deepcopy(wiki_read)
    legacy['items'][0]['blocks'][0]['source_refs'] = [ref.split(':')[2]]
    for prior in (wiki_read, legacy):
        assert c3.tools.reusable_result_valid(
            {'run_id': reading['id'], 'call_id': 'wiki', 'name': 'knowledge_read', 'result': prior},
            run_context=c3.store.run_context(reading['id']))
    copy_run = running(c3, text='把刚读的知识页另存一份', key='wiki-copy')
    copied_block = {**block, 'source_refs': page['blocks'][0]['source_refs'],
                    'evidence_ref': page['evidence_ref']}
    copied_block.pop('source_view')  # Wiki evidence does not assert an original view.
    copied = tool(c3, copy_run, 'knowledge_save_discussion', {'topics': [
        {'title': '新讨论页', 'purpose': '保留知识页依据', 'blocks': [copied_block]}]}, 'copy')
    assert copied['status'] == 'ok', copied
    new_page = c3.wiki.get_page(copied['items'][0]['results']['0']['page_id'], space_id=c3.space['id'])
    assert new_page['blocks'][0]['evidence_ref'] == page['evidence_ref']
    assert new_page['blocks'][0]['assessment'] == 'source_reported'
    assert not new_page['blocks'][0].get('source_view')
    assert all(m['kind'] != 'collection_read' for r in c3.store.get_thread(c3.thread['id'])['runs']
               for m in r['working_state'].get('model_delivered_materials', []))
    c3.wiki.edit_block(page_id, block_id=page['blocks'][0]['stable_id'], markdown='人工修改',
                      expected_version=1, operation_key='changed')
    assert not c3.tools.reusable_result_valid(
        {'run_id': reading['id'], 'call_id': 'wiki', 'name': 'knowledge_read', 'result': wiki_read},
        run_context=c3.store.run_context(reading['id']))
