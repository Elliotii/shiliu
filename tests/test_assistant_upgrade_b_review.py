from __future__ import annotations

from test_assistant_context_c2 import c2
from test_assistant_context_c3 import c3, history, state_for, notes
from assistant_context_support import mixed_checkpoint

import asyncio
import json
import threading

import pytest

from shiliu.assistant.memory import MemoryService
from shiliu.assistant.runtime import AssistantExecutionGraph
from shiliu.assistant.sources import SourceScope
from shiliu.assistant.store import AssistantConflict, AssistantRunStore
from shiliu.assistant.task_notes import TaskNoteService
from shiliu.assistant.tools import AssistantToolRegistry

from test_assistant_stage_b import _add_video, _source_service


def _record_read(store, sources, run_id, source_id, video_id, call_id, cursor=None):
    response = sources.read(
        call_id=call_id, scope=SourceScope(frozenset({source_id})),
        source_ref=f"video:{video_id}", view="description", cursor=cursor,
        max_characters=3000,
    ).model_dump(mode="json")
    store.save_assistant_tool_message(run_id, content="", provider_payload={"tool_calls": [{
        "id": call_id, "type": "function", "function": {
            "name": "collection_read", "arguments": "{}",
        },
    }]})
    store.begin_tool_call(run_id, ordinal=int(call_id[-1]) if call_id[-1].isdigit() else 1,
                          call_id=call_id, name="collection_read",
                          arguments={"source_ref": f"video:{video_id}", "view": "description"})
    response["result_ref"] = f"run-result:{run_id}:{call_id}"
    store.finish_tool_call(run_id, call_id=call_id, result=response)
    store.save_tool_result_message(
        run_id, content=json.dumps(response, ensure_ascii=False),
        provider_payload={"tool_call_id": call_id, "name": "collection_read"},
    )
    return response


def test_r1_inherit_only_current_summary_with_source_and_run_dependencies(c3):
    run, state, _ = history(c3)
    c3.provider.summary = '当前有效事实及精确来源；旧版不再作为事实。'
    candidate = asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert c3.graph.task_notes.checkpoint_for_context(c3.thread['id'], space_id=c3.space['id'],
        scope_version=1, identity=candidate.state['identity'])
    assert any(ref.startswith('run-result:') for ref in candidate.checkpoint['dependencies'])
    with c3.db.connect() as connection:
        connection.execute("UPDATE assistant_source_heads SET current_revision='new' WHERE video_id=?", (c3.video_id,))
    fresh = c3.composer.prepare(run['id'], provider=c3.provider)
    assert not fresh.checkpoint and '当前有效事实及精确来源' not in str(fresh.request.body)
    assert '甲乙丙丁条件' not in str(fresh.request.body)


def test_r2_cancel_during_compaction_prevents_late_note_and_next_call(c3):
    from shiliu.assistant.provider import ModelTurn
    run, state, _ = history(c3)
    entered, release = threading.Event(), threading.Event()
    def summary(request):
        entered.set(); release.wait(5)
        return ModelTurn('迟到摘要', [], 'stop', {'total_tokens':7})
    c3.provider.summary = summary
    async def scenario():
        task = asyncio.create_task(c3.graph._prepare_dispatch(state, provider=c3.provider))
        while not entered.is_set(): await asyncio.sleep(.01)
        c3.store.cancel_run(run['id'])
        with pytest.raises(AssistantConflict): await task
        release.set()
        await asyncio.sleep(.1)
    asyncio.run(scenario())
    assert not notes(c3) and len(c3.provider.sent) == 1
    assert c3.store.get_run(run['id'])['usage']['total_tokens'] == 7
    assert c3.store.create_run(c3.thread['id'], text='新问题', request_id='next')['status'] == 'queued'


def test_r3_tail_condition_is_structured_and_visible_in_compact_context(c3):
    run, state, _ = history(c3)
    tail = '尾部关键条件：只在候选证据相互独立且用户确认后执行；资料确实未给出成本。'
    summary = '不同讲者有分歧。' + '普通事实。' * 2000 + tail
    c3.provider.summary = summary
    candidate = asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert candidate.checkpoint['checkpoint']['text'] == summary
    assert tail in c3.graph.task_notes.render(candidate.checkpoint)
    assert '不同讲者有分歧' in str(candidate.request.body)
