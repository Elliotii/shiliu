from __future__ import annotations

import asyncio
import json
import threading
from copy import deepcopy
from types import SimpleNamespace

import pytest

from shiliu.assistant.api import get_thread as api_get_thread
from shiliu.assistant.context import ContextBudgetExceeded, SYSTEM_RULES
from shiliu.assistant.delivery import validate_model_sequence
from shiliu.assistant.provider import OpenAICompatibleAssistantProvider, ModelTurn, NativeToolCall
from shiliu.assistant.runtime import AssistantExecutionGraph, FINAL_INSTRUCTION
from shiliu.assistant.store import AssistantConflict
from shiliu.assistant.compaction import plan_compaction, checkpoint_proposal
from shiliu.db import utc_now
from shiliu.domain import PipelineError
from test_assistant_context_c2 import c2, running, batch, read


class ScriptedProvider(OpenAICompatibleAssistantProvider):
    """Offline transport; production request preparation and capacity contracts."""
    def __init__(self):
        super().__init__(base_url='https://api.deepseek.com/v1', api_key='synthetic', model='deepseek-v4-flash')
        self.sent = []
        self.summary = '有效条件与已核实发现；保留来源版本和未完成项，回读原始结果。'
        self.main = lambda request: ModelTurn('已按有效材料完成回答。', [], 'stop', {'total_tokens': 11})

    def send_prepared(self, request, *, on_text=None, timeout_seconds=None):
        self.sent.append(request)
        validate_model_sequence(request.body['messages'])
        if request.purpose == 'compact':
            if callable(self.summary):
                return self.summary(request)
            return ModelTurn(self.summary, [], 'stop', {'prompt_tokens': request.input_tokens, 'completion_tokens': 12})
        turn = self.main(request)
        if on_text:
            on_text(turn.text)
        return turn


@pytest.fixture
def c3(c2):
    c2.provider = ScriptedProvider()
    c2.graph = AssistantExecutionGraph(store=c2.store, memories=c2.memories, tools=c2.tools,
                                      provider_factory=lambda: c2.provider)
    c2.composer = c2.graph.composer
    return c2


def state_for(c3, run):
    c3.store.initialize_execution_budget(run['id'], epoch=run['run_epoch'])
    return dict(run_id=run['id'], epoch=run['run_epoch'], step_count=0, tool_count=0,
        usage={}, route='model', turn=None, memory_restart_count=0, step_base=0, tool_base=0,
        context_metadata={}, replay_call_ids=[])


def history(c3, *, count=7, characters=4000):
    run = running(c3, text='请改写下面：保留真实用户原话与全部条件，不补事实。')
    for i in range(count):
        result = read(c3, f'r{i}', max_characters=characters)
        batch(c3, run, [(f'r{i}', 'collection_read', {'source_ref': f'video:{c3.video_id}', 'view': 'summary'}, result)])
    candidate = c3.composer.prepare(run['id'], provider=c3.provider)
    c3.composer.persist(candidate)
    c3.store.confirm_model_delivery(run['id'], epoch=run['run_epoch'], spans=[],
        message_ids=candidate.message_ids, context_revision=candidate.state['revision'])
    # Keep the newest complete group and protected low-seq user under the soft target.
    c3.graph.compaction_soft_target = candidate.request.input_tokens // 2
    c3.composer.input_budget_tokens = int(candidate.request.input_tokens / .9)
    return run, state_for(c3, run), candidate


def notes(c3):
    with c3.db.connect() as connection:
        return [dict(r) for r in connection.execute('SELECT * FROM assistant_task_notes')]


def test_runtime_normal_uses_exact_prepared_and_confirms_delivery(c3):
    run = running(c3, text='你好')
    asyncio.run(c3.graph.run(run))
    assert c3.store.get_run(run['id'])['status'] == 'completed'
    assert len(c3.provider.sent) == 1
    request = c3.provider.sent[0]
    assert request.body['messages'][0] == {'role': 'system', 'content': SYSTEM_RULES}
    context = c3.store.working_run_context(run['id'])
    assert context['thread']['context_state']['format_version'] == 1
    projection = json.loads(context['thread']['messages'][0]['provider_payload_json'])['model_projection']
    assert projection['delivery']['confirmed']
    observation = c3.store.get_run(run['id'])['working_state']['context_observation']
    assert observation['estimated_input_tokens'] == request.input_tokens
    assert not notes(c3)


def test_runtime_one_summary_atomic_checkpoint_restart_no_refill(c3):
    run, state, before = history(c3)
    output = asyncio.run(c3.graph._model(state))
    assert output['route'] == 'final'
    assert [r.purpose for r in c3.provider.sent] == ['compact', 'turn']
    compact, main = c3.provider.sent
    assert compact.body['thinking'] == {'type': 'enabled'}
    assert compact.body['reasoning_effort'] == 'low' and compact.body['max_tokens'] == 65536
    data = json.loads(compact.body['messages'][1]['content'])
    roles = {m['role'] for m in data['removed_complete_history']}
    assert roles == {'assistant', 'tool'}
    tool = next(m for m in data['removed_complete_history'] if m['role'] == 'tool')
    assert tool['id'] and tool['seq'] and '甲乙丙丁条件' in tool['representation']['content']
    assert '保留真实用户原话' in str(data['current_requirements_background'])
    assert len(notes(c3)) == 1 and notes(c3)[0]['note_version'] == 1
    context = c3.store.working_run_context(run['id'])
    assert context['thread']['context_state']['checkpoint']['version'] == 1
    assert main.input_tokens < before.request.input_tokens
    restarted = AssistantExecutionGraph(store=c3.store, memories=c3.memories, tools=c3.tools,
                                        provider_factory=lambda: c3.provider)
    candidate = restarted.composer.prepare(run['id'], provider=c3.provider)
    assert not candidate.rebuilt
    assert candidate.request.body['messages'] == main.body['messages']
    assert candidate.message_ids[0] == before.message_ids[0]
    assert set(candidate.message_ids) < set(before.message_ids)
    assert c3.store.get_run(run['id'])['working_state']['execution_budget']['model_calls'] == 2


@pytest.mark.parametrize('failure', ['error', 'empty', 'length', 'no_shrink', 'missing_finish'])
def test_preventative_failure_continues_legal_original_once(c3, failure):
    run, state, before = history(c3)
    def summary(request):
        if failure == 'error':
            raise PipelineError('offline failure', code='provider_network', retryable=True)
        return ModelTurn('' if failure == 'empty' else ('无法压缩' * 20000 if failure == 'no_shrink' else '正文'),
                         [], 'length' if failure == 'length' else None if failure == 'missing_finish' else 'stop',
                         {'total_tokens': 9})
    c3.provider.summary = summary
    output = asyncio.run(c3.graph._model(state))
    assert output['route'] == 'final' and not notes(c3)
    failure_event = next(e['payload'] for e in c3.store.events(run['id'])
                         if e['event_type'] == 'context_compaction_discarded')
    assert failure_event['dispatched']
    assert failure_event['stage'] == ('dispatch' if failure == 'error' else
                                      'candidate' if failure == 'no_shrink' else 'response')
    assert failure_event['code'] == ('provider_network' if failure == 'error' else
                                     'context_budget_exceeded' if failure == 'no_shrink' else 'ValueError')
    assert c3.provider.sent[-1].body['messages'] == before.request.body['messages']
    assert c3.store.get_run(run['id'])['last_error_code'] is None
    # A further ordinary preparation under the same pressure cannot summarize again.
    asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert len([r for r in c3.provider.sent if r.purpose == 'compact']) == 1


def test_success_still_above_line_and_small_append_do_not_resummarize(c3):
    run, state, before = history(c3)
    before = c3.composer.prepare(run['id'], provider=c3.provider)
    plan = plan_compaction(before, composer=c3.composer, provider=c3.provider,
                           soft_target=c3.graph.compaction_soft_target)
    # Construct a large but valid summary with only a slight actual reduction.
    left, right = 1, before.request.input_tokens
    while left < right:
        size = (left + right + 1) // 2
        proposal = checkpoint_proposal(before, plan, '摘' * size, composer=c3.composer, provider=c3.provider)
        if proposal.request.input_tokens <= before.request.input_tokens * .96:
            left = size
        else:
            right = size - 1
    c3.provider.summary = '摘' * left
    first = asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    # Tune against measured input rather than a guessed character/token equivalence.
    if not notes(c3):
        pytest.fail('fixture summary must be a valid shrinking replacement')
    c3.composer.input_budget_tokens = int(first.request.input_tokens / .9)
    second = asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert second.request.input_tokens >= .85 * second.budget.available_input_tokens
    batch(c3, run, [('small', 'collection_read', {}, read(c3, 'small', max_characters=20))])
    third = asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert len([r for r in c3.provider.sent if r.purpose == 'compact']) == 1
    assert notes(c3)[0]['note_version'] == 1
    assert third.state['pressure_event_attempted']


def test_no_eligible_prefix_records_attempt_and_no_model_summary(c3):
    run = running(c3, text='你好')
    state = state_for(c3, run)
    initial = c3.composer.prepare(run['id'], provider=c3.provider)
    c3.composer.input_budget_tokens = int(initial.request.input_tokens / .9)
    for _ in range(2):
        asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert not c3.provider.sent and not notes(c3)
    current = c3.store.working_run_context(run['id'])['thread']['context_state']
    assert current['pressure_event_attempted'] and current['last_attempt_history_frontier'] == 1


def test_explicit_provider_overflow_bypasses_dedup_and_retries_once_no_tools(c3):
    run, state, before = history(c3)
    # Fail the initial optional attempt; provider then explicitly rejects the main request.
    c3.provider.summary = lambda req: ModelTurn('', [], 'stop', {'total_tokens': 3})
    asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    c3.provider.summary = '已核实发现和条件，未完成项回读。'
    calls = []
    def main(request):
        calls.append(request)
        if len(calls) == 1:
            raise PipelineError('overflow', code='provider_context_window_exceeded', retryable=False)
        return ModelTurn('恢复后的有效回答', [], 'stop', {'total_tokens': 5})
    c3.provider.main = main
    output = asyncio.run(c3.graph._model(state))
    assert output['route'] == 'final'
    assert len(calls) == 2 and calls[1].input_tokens < calls[0].input_tokens
    assert len(notes(c3)) == 1
    assert c3.store.get_run(run['id'])['working_state']['context_recovery_attempts'] == 1
    assert c3.store.get_run(run['id'])['tool_count'] == 0


def test_local_hard_capacity_uses_same_executor(c3):
    run, state, before = history(c3)
    # Summary prompt includes identity metadata; leave its input legal while the main
    # request exceeds B by adding a large, production-counted tool schema.
    original = c3.tools.schemas
    c3.tools.schemas = lambda: [*original(), {'type': 'function', 'function': {'name': 'synthetic', 'description': '甲'*18000, 'parameters': {'type': 'object'}}}]
    # Changing schema invalidates prior identity, so build this baseline anew first.
    fresh = c3.composer.prepare(run['id'], provider=c3.provider, input_limit_tokens=256000)
    c3.composer.persist(fresh)
    c3.store.confirm_model_delivery(run['id'], epoch=run['run_epoch'], spans=[],message_ids=fresh.message_ids,context_revision=fresh.state['revision'])
    c3.composer.input_budget_tokens = fresh.request.input_tokens - 1000
    prepared = asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert prepared.budget.fits and notes(c3)
    assert [r.purpose for r in c3.provider.sent] == ['compact']


def test_final_no_summary_actual_output_suffix_and_fallback(c3):
    run, state, before = history(c3)
    result = asyncio.run(c3.graph._finish_with_available(state, reason='user_requested'))
    assert result['route'] == 'final' and len(c3.provider.sent) == 1
    request = c3.provider.sent[0]
    assert request.purpose == 'turn' and request.body['tools'] == []
    assert request.body['max_tokens'] == 8192
    assert request.body['messages'][0]['content'] == SYSTEM_RULES
    assert request.body['messages'][-1] == {'role': 'system', 'content': FINAL_INSTRUCTION}
    assert not notes(c3)


def test_final_illegal_input_falls_back_without_dispatch(c3):
    run = running(c3, text='你好')
    state = state_for(c3, run)
    c3.composer.input_budget_tokens = 10
    output = asyncio.run(c3.graph._finish_with_available(state, reason='budget'))
    assert output['route'] == 'final' and '不能可靠' in output['turn'].text
    assert not c3.provider.sent and not notes(c3)


def test_summary_dependency_conflict_rebuilds_original_without_advancing_note(c3):
    run, state, before = history(c3)
    def changed(request):
        with c3.db.connect() as connection:
            connection.execute("UPDATE assistant_source_heads SET current_revision='changed' WHERE video_id=?", (c3.video_id,))
        return ModelTurn('不能移植的摘要', [], 'stop', {'total_tokens': 7})
    c3.provider.summary = changed
    candidate = asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert not notes(c3) and not candidate.checkpoint
    assert '甲乙丙丁条件' not in str(candidate.request.body)
    assert '保留真实用户原话' in str(candidate.request.body)


def test_summary_cancellation_late_usage_once_and_no_answer_draft(c3):
    async def scenario():
        run, state, before = history(c3)
        entered, release = threading.Event(), threading.Event()
        def delayed(request):
            entered.set(); release.wait(5)
            return ModelTurn('晚到摘要不得发布', [], 'stop', {'total_tokens': 17})
        c3.provider.summary = delayed
        pending = asyncio.create_task(c3.graph._prepare_dispatch(state, provider=c3.provider))
        while not entered.is_set():
            await asyncio.sleep(.01)
        assert not c3.store.get_run(run['id'])['working_state'].get('answer_draft')
        c3.store.cancel_run(run['id'])
        with pytest.raises((AssistantConflict, ContextBudgetExceeded)):
            await pending
        assert not notes(c3)
        release.set()
        for _ in range(100):
            if c3.store.get_run(run['id'])['usage'].get('total_tokens') == 17:
                break
            await asyncio.sleep(.01)
        assert c3.store.get_run(run['id'])['usage']['total_tokens'] == 17
        assert not c3.store.get_run(run['id'])['working_state'].get('answer_draft')
    asyncio.run(scenario())


def test_atomic_installer_failure_rolls_back_note_boundary_and_new_projections(c3, monkeypatch):
    run, state, before = history(c3)
    pending_ids = batch(c3, run, [('pending', 'collection_read', {}, read(c3, 'pending', max_characters=100))])
    installer = c3.store.install_working_context
    injected = []
    def fail_after_note(connection, **kwargs):
        if kwargs['state'].get('checkpoint'):
            assert connection.execute('SELECT COUNT(*) FROM assistant_task_notes').fetchone()[0] == 1
            injected.append(True)
            raise AssistantConflict('synthetic_atomic_conflict')
        return installer(connection, **kwargs)
    monkeypatch.setattr(c3.store, 'install_working_context', fail_after_note)
    candidate = asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert injected == [True] and not notes(c3)
    failure_event = next(e['payload'] for e in c3.store.events(run['id'])
                         if e['event_type'] == 'context_compaction_discarded')
    assert failure_event['stage'] == 'commit' and failure_event['dispatched']
    assert failure_event['reason'] == 'synthetic_atomic_conflict'
    assert not candidate.state['checkpoint'] and set(before.message_ids) <= set(candidate.message_ids)
    assert set(pending_ids) <= set(candidate.message_ids)
    assert len([r for r in c3.provider.sent if r.purpose == 'compact']) == 1


def test_long_summary_and_bound_save_body_remain_whole_above_soft_target(c3):
    first = running(c3, text='你好')
    body = '应保存的正文、必要数字123与限定条件。' * 2200
    assert c3.store.complete_run(first['id'], epoch=first['run_epoch'], answer=body, usage={})
    answer = next(m for m in c3.store.get_thread(c3.thread['id'])['messages'] if m['content'] == body)
    run = running(c3, text='请保存这份正式结论，必须保留全部正文。', key='bound', answer_message_id=answer['id'])
    state = state_for(c3, run)
    for i in range(8):
        batch(c3, run, [(f'bound{i}', 'collection_read', {}, read(c3, f'bound{i}'))])
    initial = c3.composer.prepare(run['id'], provider=c3.provider)
    c3.composer.persist(initial)
    c3.store.confirm_model_delivery(run['id'], epoch=run['run_epoch'], spans=[],
        message_ids=initial.message_ids, context_revision=initial.state['revision'])
    c3.composer.input_budget_tokens = int(initial.request.input_tokens / .9)
    c3.provider.summary = '摘要发现、具体条件与未知。' * 900  # More than the retired 8K cap.
    output = asyncio.run(c3.graph._model(state))
    assert output['route'] == 'final' and len(notes(c3)) == 1
    assert len(json.loads(notes(c3)[0]['checkpoint_json'])['text']) > 8000
    request = c3.provider.sent[-1]
    assert request.input_tokens > 32000 and request.input_tokens < initial.request.input_tokens
    assert str(request.body).count(body) == 1
    active = c3.store.working_run_context(run['id'])['thread']['context_state']
    assert answer['id'] in active['protected_message_ids']
    assert len([r for r in c3.provider.sent if r.purpose == 'compact']) == 1


def test_tool_argument_repair_is_recounted_suffix_and_fixed_first_system(c3):
    run = running(c3, text='你好')
    calls = []
    def main(request):
        calls.append(request)
        if len(calls) == 1:
            raise PipelineError('invalid args', code='tool_arguments_invalid', retryable=False)
        return ModelTurn('修复后回答', [], 'stop', {'total_tokens': 5})
    c3.provider.main = main
    asyncio.run(c3.graph.run(run))
    assert c3.store.get_run(run['id'])['status'] == 'completed' and len(calls) == 2
    assert calls[0].body['messages'][0] == calls[1].body['messages'][0]
    assert calls[1].input_tokens > calls[0].input_tokens
    assert calls[1].body['messages'][-1]['role'] == 'system'
    observation = c3.store.get_run(run['id'])['working_state']['context_observation']
    assert observation['estimated_input_tokens'] == calls[1].input_tokens
    assert not notes(c3)


def test_new_pressure_event_requires_new_processed_removed_history(c3):
    run, state, before = history(c3)
    c3.provider.summary = lambda req: ModelTurn('', [], 'stop')
    first = asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    # A real ordinary low-pressure request resets the event, but not the history frontier.
    c3.composer.input_budget_tokens = first.request.input_tokens * 2
    low = asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert not low.state['pressure_event_attempted']
    c3.composer.input_budget_tokens = int(first.request.input_tokens / .9)
    asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert len(c3.provider.sent) == 1  # All selected raw history predates last attempt.
    # Process enough genuinely new complete groups to move the replaced prefix forward.
    for i in range(8):
        batch(c3, run, [(f'new{i}', 'collection_read', {}, read(c3, f'new{i}'))])
    large = c3.composer.prepare(run['id'], provider=c3.provider, input_limit_tokens=256000)
    c3.composer.persist(large)
    c3.store.confirm_model_delivery(run['id'], epoch=run['run_epoch'], spans=[],
        message_ids=large.message_ids, context_revision=large.state['revision'])
    c3.composer.input_budget_tokens = large.request.input_tokens * 2
    asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    c3.composer.input_budget_tokens = int(large.request.input_tokens / .9)
    c3.provider.summary = '新历史纳入后的完整发现与未知。'
    asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert len(c3.provider.sent) == 2 and len(notes(c3)) == 1


@pytest.mark.parametrize('context7_enabled', [False, True])
def test_api_checkpoint_usability_tracks_actual_source_validity(c3, context7_enabled):
    if context7_enabled:
        c3.tools.context7 = SimpleNamespace(tools={'context7_query_docs': {
            'description': '公开文档', 'inputSchema': {'type': 'object', 'properties': {}}}})
    run, state, before = history(c3)
    asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    runtime = SimpleNamespace(store=c3.store, sources=c3.sources, memories=c3.memories, wiki=c3.wiki, tools=c3.tools)
    candidate = c3.composer.prepare(run['id'], provider=c3.provider)
    assert candidate.checkpoint is not None and not candidate.rebuilt
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(core=SimpleNamespace(
        config=SimpleNamespace(assistant_enabled=True), assistant_runtime=runtime))))
    assert asyncio.run(api_get_thread(c3.thread['id'], request))['thread']['task_note']['usable']
    with c3.db.connect() as connection:
        connection.execute("UPDATE assistant_source_heads SET current_revision='changed' WHERE video_id=?", (c3.video_id,))
    public = asyncio.run(api_get_thread(c3.thread['id'], request))['thread']
    assert not public['task_note']['usable']
    assert not public['task_note']['searched_scope_and_material_refs']
    assert len(public['messages']) == len(before.context['thread']['messages'])


def test_legacy_note_is_unusable_and_small_thread_rebuild_keeps_history(c3):
    run = running(c3, text='你好')
    with c3.db.connect() as connection:
        connection.execute('INSERT INTO assistant_task_notes(id,thread_id,note_version,scope_version,covered_until_message_seq,'
            'goal,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
            ('legacy',c3.thread['id'],3,1,999,'过时的程序整理',utc_now(),utc_now()))
    assert not c3.store.get_thread(c3.thread['id'])['task_note']['usable']
    asyncio.run(c3.graph.run(run))
    assert c3.store.get_run(run['id'])['status'] == 'completed'
    assert '你好' in str(c3.provider.sent[-1].body)
    assert '过时的程序整理' not in str(c3.provider.sent[-1].body)
    assert notes(c3)[0]['note_version'] == 3
    assert len(c3.store.get_thread(c3.thread['id'])['messages']) == 2


def test_summary_contains_original_historical_user_roles_and_never_replays_tools(c3):
    run, state, before = history(c3)
    assert c3.store.complete_run(run['id'], epoch=run['run_epoch'], answer='第一段阶段结果', usage={})
    next_run = running(c3, text='请改写下面：保持上一段已核实条件，继续核对。', key='follow')
    next_state = state_for(c3, next_run)
    candidate = c3.composer.prepare(next_run['id'], provider=c3.provider)
    c3.composer.persist(candidate)
    c3.store.confirm_model_delivery(next_run['id'], epoch=next_run['run_epoch'], spans=[],
        message_ids=candidate.message_ids, context_revision=candidate.state['revision'])
    c3.composer.input_budget_tokens = int(candidate.request.input_tokens / .9)
    output = asyncio.run(c3.graph._model(next_state))
    assert output['route'] == 'final'
    compact = next(req for req in c3.provider.sent if req.purpose == 'compact')
    data = json.loads(compact.body['messages'][1]['content'])
    old_user = next(item for item in data['removed_complete_history'] if item['role'] == 'user')
    assert old_user['id'] == before.message_ids[0]
    assert old_user['representation']['content'] == before.projections[old_user['id']]['message']['content']
    assert c3.store.get_run(next_run['id'])['tool_count'] == 0


def test_unprocessable_protected_input_stops_without_summary_or_illegal_main(c3):
    run = running(c3, text='请改写下面：' + '必须保留原话'*1000)
    state = state_for(c3, run)
    c3.composer.input_budget_tokens = 20
    output = asyncio.run(c3.graph._model(state))
    assert output['route'] == 'stopped' and not c3.provider.sent and not notes(c3)
    assert c3.store.get_run(run['id'])['last_error_code'] == 'context_recovery_failed'
    assert len(c3.store.get_thread(c3.thread['id'])['messages']) == 1


def test_second_explicit_overflow_stops_after_one_main_retry(c3):
    run, state, before = history(c3)
    c3.composer.input_budget_tokens = before.request.input_tokens * 2
    def overflow(request):
        raise PipelineError('overflow', code='provider_context_window_exceeded', retryable=False)
    c3.provider.main = overflow
    output = asyncio.run(c3.graph._model(state))
    assert output['route'] == 'stopped'
    assert [req.purpose for req in c3.provider.sent] == ['turn', 'compact', 'turn']
    assert c3.provider.sent[-1].input_tokens < c3.provider.sent[0].input_tokens
    assert c3.store.get_run(run['id'])['last_error_code'] == 'context_recovery_failed'
    assert notes(c3)[0]['note_version'] == 1


@pytest.mark.parametrize('persistent', [False, True])
def test_bounded_fresh_prepare_on_unrelated_metadata_cas_conflict(c3, monkeypatch, persistent):
    run = running(c3, text='你好')
    state = state_for(c3, run)
    save, calls = c3.store.save_working_context, []
    def conflict(*args, **kwargs):
        calls.append(True)
        if persistent or len(calls) == 1:
            raise AssistantConflict('working_context_changed')
        return save(*args, **kwargs)
    monkeypatch.setattr(c3.store, 'save_working_context', conflict)
    output = asyncio.run(c3.graph._model(state))
    assert len(calls) == 2 and not notes(c3)
    assert output['route'] == ('stopped' if persistent else 'final')
    assert len(c3.provider.sent) == (0 if persistent else 1)


def test_memory_forgotten_during_summary_never_commits_or_restores_old_text(c3):
    memory = c3.memories.save_explicit(text='保留真实用户原话时必须区分特别偏好Z', subject_key='context_c3',
        kind='preference', scope_kind='space', scope_id=c3.space['id'],
        operation_key='c3-memory', source_message_ids=[])
    run, state, before = history(c3)
    assert '特别偏好Z' in str(before.request.body)
    def forget(request):
        c3.memories.forget(memory['id'], expected_version=memory['version'], operation_key='c3-forget',
                           source_message_ids=[])
        return ModelTurn('依赖已经失效的摘要', [], 'stop', {'total_tokens': 9})
    c3.provider.summary = forget
    candidate = asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert not notes(c3) and '特别偏好Z' not in str(candidate.request.body)
    assert '保留真实用户原话' in str(candidate.request.body)


def test_summary_background_memory_dependencies_are_inherited(c3):
    memory = c3.memories.save_explicit(text='保留真实用户原话时必须区分特别偏好B', subject_key='background',
        kind='preference', scope_kind='space', scope_id=c3.space['id'],
        operation_key='c3-background', source_message_ids=[])
    run, state, before = history(c3)
    candidate = asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert notes(c3) and candidate.checkpoint
    assert f"memory:{memory['id']}:{memory['version']}" in candidate.checkpoint['dependencies']
    compact = next(r for r in c3.provider.sent if r.purpose == 'compact')
    assert '特别偏好B' in str(compact.body)
    c3.memories.forget(memory['id'], expected_version=memory['version'], operation_key='forget-background')
    assert c3.graph.task_notes.checkpoint_for_context(c3.thread['id'], space_id=c3.space['id'],
        scope_version=1, identity=candidate.state['identity']) is None


def test_summary_finish_uses_final_suffix_and_late_usage_only(c3):
    async def scenario():
        run, state, before = history(c3)
        entered, release = threading.Event(), threading.Event()
        def delayed(request):
            entered.set(); release.wait(5)
            return ModelTurn('晚到摘要不得变成回答', [], 'stop', {'total_tokens': 17})
        c3.provider.summary = delayed
        pending = asyncio.create_task(c3.graph._model(state))
        while not entered.is_set():
            await asyncio.sleep(.01)
        c3.store.request_finish(run['id'])
        output = await asyncio.wait_for(pending, 2)
        assert output['route'] == 'final' and not notes(c3)
        assert [r.purpose for r in c3.provider.sent] == ['compact', 'turn']
        assert c3.provider.sent[-1].body['tools'] == []
        assert c3.provider.sent[-1].body['messages'][-1]['content'] == FINAL_INSTRUCTION
        release.set()
        for _ in range(100):
            if c3.store.get_run(run['id'])['usage'].get('total_tokens') == 28:
                break
            await asyncio.sleep(.01)
        assert c3.store.get_run(run['id'])['usage']['total_tokens'] == 28
        assert '晚到摘要' not in json.dumps(c3.store.get_run(run['id'])['working_state'], ensure_ascii=False)
    asyncio.run(scenario())


def test_runtime_recovery_completes_native_batch_without_reexecuting_receipts(c3, monkeypatch):
    run = running(c3, text='请改写以下内容：保留条件。')
    ids = batch(c3, run, [('one', 'collection_read', {}, read(c3, 'one')),
                         ('two', 'collection_read', {}, read(c3, 'two'))])
    with c3.db.connect() as connection:
        connection.execute('DELETE FROM assistant_messages WHERE id=?', (ids[1],))
    async def forbidden(**kwargs):
        pytest.fail('completed durable tool receipt was executed again')
    monkeypatch.setattr(c3.tools, 'execute', forbidden)
    asyncio.run(c3.graph.run(run))
    assert c3.store.get_run(run['id'])['status'] == 'completed'
    assert len(c3.provider.sent) == 1
    messages = c3.provider.sent[0].body['messages']
    assert [m['tool_call_id'] for m in messages if m['role'] == 'tool'] == ['one', 'two']
    assert c3.store.completed_tool_message_count(run['id']) == 2


def test_send_prepared_posts_exact_admitted_body_without_repreparation(monkeypatch):
    provider = OpenAICompatibleAssistantProvider(base_url='https://api.deepseek.com/v1', api_key='synthetic', model='deepseek-v4-flash')
    requests = [provider.prepare_request(messages=[{'role': 'user', 'content': '原话'}], tools=[], max_tokens=4096),
                provider.prepare_compaction(messages=[{'role': 'user', 'content': '待总结数据'}], remaining_tokens=100000)]
    captured = []
    def post(body, **kwargs):
        captured.append(deepcopy(body))
        return {'choices': [{'message': {'content': '完整正文', 'reasoning_content': '不入正文'}, 'finish_reason': 'stop'}]}
    monkeypatch.setattr(provider, '_post', post)
    monkeypatch.setattr(provider, 'prepare_request', lambda **kwargs: pytest.fail('prepared request rebuilt at send time'))
    for request in requests:
        assert provider.send_prepared(request, timeout_seconds=10).text == '完整正文'
    assert captured == [request.body for request in requests]


def test_finish_arriving_with_completed_summary_is_rechecked_in_atomic_commit(c3):
    run, state, before = history(c3)
    def simultaneous_finish(request):
        c3.store.request_finish(run['id'])
        return ModelTurn('完成但已被先回答取代的摘要', [], 'stop', {'total_tokens': 9})
    c3.provider.summary = simultaneous_finish
    output = asyncio.run(c3.graph._model(state))
    assert output['route'] == 'final' and not notes(c3)
    assert [r.purpose for r in c3.provider.sent] == ['compact', 'turn']
    assert c3.provider.sent[-1].body['tools'] == []
    assert c3.store.get_run(run['id'])['usage']['total_tokens'] == 20
