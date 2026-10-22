from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shiliu.assistant.api import router
from shiliu.assistant.context import ContextMessages
from shiliu.assistant.memory_time import event_signature, time_context, validity, has_personal_candidate
from shiliu.assistant.runtime import AssistantRuntime, AssistantExecutionGraph
from test_assistant_w1 import fixture, execute
from test_assistant_consolidation_nb import _run
from test_assistant_stage_b import FakeMemoryBackend
from test_assistant_k import graph_for
from shiliu.assistant.provider import ModelTurn


AT = '2026-10-17T13:45:38+00:00'


def save_fact(parts, text, *, key='fact', kind='context', **fields):
    db, _, _, store, _, space, tools = parts
    original, ctx = _run(store, space['id'], text, key=key)
    message = ctx['thread']['messages'][-1]
    with db.connect() as c:
        c.execute('UPDATE assistant_messages SET created_at=? WHERE id=?', (AT, message['id']))
    run, _ = _run(store, space['id'], '请记住这个', thread_id=original['thread_id'], key=key+'-save')
    args = dict(text=text, subject_key=key, kind=kind, source_message_ids=[message['id']], **fields)
    result = execute(tools, store, run, args, name='memory_save')
    return result, run, args


@pytest.mark.parametrize('text,precision,value', [
    ('我喜欢单机游戏', None, None),
    ('过段时间学习日语', 'vague', None),
    ('2077之前玩到一半，打算下个月继续玩', 'month', '2026-11'),
    ('下周开始准备面试', 'week', '2026-W43'),
    ('明年年初考虑换电脑', 'year_part', '2027年初'),
    ('接下来两周重点学习数据库', 'range', '2026-10-17'),
])
def test_fact_time_is_not_memory_expiry(app_paths, monkeypatch, text, precision, value):
    parts = fixture(app_paths)
    result, run, args = save_fact(parts, text)
    assert result['status'] == 'ok', result
    m = result['items'][0]
    assert m['valid_from'] is None and m['expires_at'] is None
    events = m['time_context']['events']
    assert (events[0]['precision'], events[0]['value']) == (precision, value) if precision else not events
    assert m['time_context']['stated_at'] == AT
    tools = parts[-1]
    repeated = execute(tools, parts[3], run, args, call='retry', name='memory_save')
    assert repeated['items'][0]['id'] == m['id']
    monkeypatch.setattr('shiliu.assistant.memory.utc_now', lambda: '2026-12-15T00:00:00+00:00')
    recalled = tools.memories.recall(text, space_id=parts[-2]['id'])
    assert recalled and recalled[0]['time_context'] == m['time_context']
    line = ContextMessages._memory_line(recalled[0])
    assert AT in line
    if value:
        assert value in line
    if value == '2026-11':
        assert tools.memories.recall('11月', space_id=parts[-2]['id'])[0]['id'] == m['id']


def test_actual_validity_and_forged_event_expiry(app_paths, monkeypatch):
    parts = fixture(app_paths)
    saved, _, _ = save_fact(parts, '这个决定只在月底之前有效')
    assert saved['status'] == 'ok', saved
    m = saved['items'][0]
    assert m['expires_at'] == '2026-10-31T16:00:00+00:00'
    assert not m['time_context']['events']
    monkeypatch.setattr('shiliu.assistant.memory.utc_now', lambda: '2026-11-01T00:00:00+00:00')
    assert not parts[-1].memories.recall('这个决定', space_id=parts[-2]['id'])
    bad, _, _ = save_fact(parts, '我2026-11-01继续玩2077', key='forged', expires_at='2026-11-02T00:00:00+08:00')
    assert bad['error_code'] == 'memory_validity_without_user_basis'
    assert '删除无依据' in bad['summary']
    start, _, _ = save_fact(parts, '这条记忆从11月起适用', key='start', valid_from='2026-11-01T00:00:00+08:00')
    assert start['status'] == 'ok', start
    assert start['items'][0]['valid_from'] == '2026-10-31T16:00:00+00:00'


def test_correction_read_api_and_forget_do_not_leak_temporal_data(app_paths):
    parts = fixture(app_paths)
    db, _, _, store, _, space, tools = parts
    result, run, _ = save_fact(parts, '下个月继续玩2077')
    old = result['items'][0]
    change, _ = _run(store, space['id'], '把2077的计划改到12月', thread_id=run['thread_id'], key='change')
    updated = execute(tools, store, change, dict(memory_id=old['id'], expected_version=1,
        text='计划12月继续玩2077', update_time_context=True), name='memory_correct')
    assert updated['status'] == 'ok', updated
    current = updated['items'][0]
    assert current['version'] == 2 and current['time_context']['events'][0]['value'].endswith('-12')
    app = FastAPI()
    app.state.core = SimpleNamespace(config=SimpleNamespace(assistant_enabled=True),
        assistant_runtime=SimpleNamespace(memories=tools.memories, store=store))
    app.include_router(router)
    client = TestClient(app)
    listing = client.get(f"/api/assistant/memories?space_id={space['id']}").json()['memories'][0]
    assert listing['time_context'] == current['time_context']
    polished = client.patch(f"/api/assistant/memories/{old['id']}", json=dict(text='计划12月继续玩2077，先完成主线',
        expected_version=2, operation_key='polish', update_time_context=False)).json()['memory']
    assert polished['time_context'] == current['time_context']
    assert tools.memories.recall('2077', space_id=space['id'])[0]['version'] == 3
    tools.memories.forget(old['id'], expected_version=3, operation_key='forget')
    assert tools.memories.get(old['id'])['time_context'] == {}
    assert tools.memories.list(space_id=space['id']) == []
    assert not tools.memories.recall('2077', space_id=space['id'])
    with db.connect() as c:
        assert c.execute('SELECT time_context_json FROM assistant_memories WHERE id=?',(old['id'],)).fetchone()[0] == '{}'


def test_same_subject_independent_facts_and_semantic_time_dedup(app_paths):
    parts = fixture(app_paths)
    first, run, _ = save_fact(parts, '我喜欢单机游戏', key='games')
    tools, store = parts[-1], parts[3]
    second, _ = _run(store, parts[-2]['id'], '请记住我也喜欢合作游戏', key='second')
    r = execute(tools, store, second, dict(text='我也喜欢合作游戏', subject_key='games', kind='preference'), name='memory_save')
    assert r['status'] == 'ok'
    assert r['items'][0]['id'] != first['items'][0]['id']
    a = time_context('下个月玩游戏', AT)
    b = time_context('下月玩游戏', '2026-10-20T00:00:00+00:00')
    assert event_signature(a) == event_signature(dict(reversed(list(b.items()))))


@pytest.mark.parametrize('fact,kind,allowed', [
    ('假设我决定买电脑，只是举例', 'decision', False),
    ('视频作者建议我买电脑', 'decision', False),
    ('我正在考虑买电脑，还没有决定', 'context', True),
    ('决定下个月继续玩2077', 'decision', True),
    ('正在考虑买电脑，还没有决定', 'context', True),
])
def test_fact_meaning_is_not_a_negation_blacklist(app_paths, fact, kind, allowed):
    r, _, _ = save_fact(fixture(app_paths), fact, kind=kind)
    assert (r['status'] == 'ok') is allowed


def test_automatic_extraction_without_pronouns_and_policy_fences(app_paths):
    parts = fixture(app_paths)
    db, _, sources, store, _, space, _ = parts
    class Provider:
        calls = 0
        def extract_memories(self, *, prompt):
            self.calls += 1
            return [dict(op='add', kind='context', text='下个月继续玩2077', subject_key='games',
                         source_excerpt='下个月继续玩2077', scope_kind='space')]
    provider = Provider()
    runtime = AssistantRuntime(store=store, sources=sources, memory_backend=FakeMemoryBackend(),
        context7=SimpleNamespace(), provider_factory=lambda: provider)
    runtime._maintenance_idle = lambda: True
    runtime._require_maintenance_idle = lambda connection: None
    run, _ = _run(store, space['id'], '下个月继续玩2077', key='automatic')
    claimed = store.claim_next_run()
    assert store.complete_run(run['id'], epoch=claimed['run_epoch'], answer='收到', usage={})
    job = store.claim_job(owner='time-test')
    result = asyncio.run(runtime._extract_memories(job))
    assert len(result['applied_memory_ids']) == 1, result
    m = runtime.memories.list(space_id=space['id'])[0]
    assert m['expires_at'] is None and m['time_context']['events'][0]['precision'] == 'month'
    runtime.memories.set_auto_enabled(False)
    assert asyncio.run(runtime._extract_memories(job))['reason'] == 'automatic_memory_policy_changed'
    assert provider.calls == 1
    for text in ['你好', '这次回答短一点', '请用中文', '什么是向量数据库']:
        assert not has_personal_candidate([{'content': text}])


def test_migration_preserves_old_expiry_and_is_idempotent(app_paths):
    parts = fixture(app_paths)
    db, _, _, _, _, space, tools = parts
    old = tools.memories.save_explicit(text='旧事实', subject_key='old', kind='context', scope_kind='space',
        scope_id=space['id'], operation_key='old', expires_at='2025-01-01T00:00:00+00:00')
    with db.connect() as c:
        c.execute('ALTER TABLE assistant_memories DROP COLUMN time_context_json')
    db.initialize()
    db.initialize()
    reread = tools.memories.get(old['id'])
    assert reread['expires_at'] == old['expires_at'] and reread['time_context'] == {}


def test_no_write_receipt_cannot_promise_persistent_memory(app_paths):
    parts = fixture(app_paths)
    store, space, tools = parts[3], parts[-2], parts[-1]
    run, _ = _run(store, space['id'], '2077玩到一半', key='no-write')
    run = store.claim_next_run()
    class Provider:
        def turn(self, **kwargs):
            return ModelTurn(text='已记下：2077玩到一半。之后我会记得。\n\n可以继续聊游戏。')
    asyncio.run(graph_for(store, tools, Provider()).run(run))
    formal = [m['content'] for m in store.get_thread(run['thread_id'])['messages'] if m['role'] == 'assistant' and m['content']][-1]
    assert '尚未确认保存' in formal and '已记下' not in formal
    example = '例如用户说“已记下”，不代表成功。'
    assert AssistantExecutionGraph._memory_claim(example, False) == example


def test_cross_year_and_actual_stage_boundaries():
    assert time_context('下个月玩', '2026-12-31T15:00:00+00:00')['events'][0]['value'] == '2027-01'
    assert time_context('接下来两周学习', AT)['events'][0]['end_value'] == '2026-10-31'
    assert validity('这个约束只在月底之前有效', '2028-02-10T00:00:00+00:00')['expires_at'] == '2028-02-29T16:00:00+00:00'


def test_time_words_do_not_change_their_owner_or_precision():
    for statement in ['我下个月参加有效沟通课程', '护照下个月到期', '我决定下个月更换到期护照']:
        assert validity(statement, AT) == {}
        assert time_context(statement, AT)['events'][0]['value'] == '2026-11'
    assert time_context('2027年11月继续玩2077', AT)['events'][0]['value'] == '2027-11'
    assert time_context('下下周开始准备面试', AT)['events'][0]['value'] == '2026-W44'
    for text in ['好的，我已记下：你喜欢单机游戏。', '以后我会记住你喜欢单机游戏。']:
        assert '尚未确认保存' in AssistantExecutionGraph._memory_claim(text, False)


def test_polish_preserves_relative_validity_and_null_really_clears(app_paths):
    parts = fixture(app_paths)
    memories = parts[-1].memories
    saved = memories.save_explicit(text='这个决定只在月底之前有效', subject_key='choice', kind='context',
        scope_kind='space', scope_id=parts[-2]['id'], operation_key='original-validity',
        stated_text='这个决定只在月底之前有效', stated_at=AT)
    polished = memories.correct(saved['id'], text='这个决定只在月底之前有效，补充说明', expected_version=1,
        operation_key='polish-validity', stated_text='这个决定只在月底之前有效，补充说明',
        stated_at='2026-11-10T00:00:00+00:00', update_time_context=False)
    assert polished['expires_at'] == saved['expires_at']
    cleared = memories.correct(saved['id'], text=polished['text'], expected_version=2,
        operation_key='clear-validity', expires_at=None, stated_text=polished['text'],
        stated_at='2026-11-10T00:00:00+00:00')
    assert cleared['expires_at'] is None


def test_invented_date_and_partial_multi_event_change_are_not_silent(app_paths):
    parts = fixture(app_paths)
    run, _ = _run(parts[3], parts[-2]['id'], '请记住我正在准备面试', key='invented')
    bad = execute(parts[-1], parts[3], run, dict(text='我未来30天准备面试', subject_key='study', kind='context'), name='memory_save')
    assert bad['error_code'] == 'memory_event_without_user_basis'
    m = parts[-1].memories.save_explicit(text='下个月玩游戏，明年年初换电脑', subject_key='two', kind='context',
        scope_kind='space', scope_id=parts[-2]['id'], operation_key='two',
        stated_text='下个月玩游戏，明年年初换电脑', stated_at=AT)
    with pytest.raises(ValueError, match='memory_time_source_ambiguous'):
        parts[-1].memories.correct(m['id'], text='游戏改到3月，电脑不变', expected_version=1,
            operation_key='partial', stated_text='游戏改到3月，电脑不变', stated_at=AT)
    assert len(parts[-1].memories.get(m['id'])['time_context']['events']) == 2


def test_cross_month_tool_polish_uses_old_relative_clock(app_paths, monkeypatch):
    parts = fixture(app_paths)
    result, original, _ = save_fact(parts, '下个月继续玩2077')
    m = result['items'][0]
    monkeypatch.setattr('shiliu.assistant.store.utc_now', lambda: '2026-11-20T00:00:00+00:00')
    run, _ = _run(parts[3], parts[-2]['id'], '只补充不购买DLC，计划时间不变',
                  key='polish-later', thread_id=original['thread_id'])
    updated = execute(parts[-1], parts[3], run, dict(memory_id=m['id'], expected_version=1,
        text='下个月继续玩2077，不购买DLC', update_time_context=False), name='memory_correct')
    assert updated['status'] == 'ok', updated
    assert updated['items'][0]['time_context'] == m['time_context']


def test_partial_update_retains_other_event_with_its_original_clock(app_paths):
    parts = fixture(app_paths)
    memories = parts[-1].memories
    m = memories.save_explicit(text='下个月玩游戏，明年年初换电脑', subject_key='two', kind='context',
        scope_kind='space', scope_id=parts[-2]['id'], operation_key='two-events',
        stated_text='下个月玩游戏，明年年初换电脑', stated_at=AT)
    updated = memories.correct(m['id'], text='游戏改到3月，明年年初换电脑', expected_version=1,
        operation_key='one-event-update', stated_text='游戏改到3月', stated_at='2027-01-20T00:00:00+00:00')
    events = updated['time_context']['events']
    assert [event['value'] for event in events] == ['2027-03', '2027年初']
    assert events[1]['stated_at'] == AT
