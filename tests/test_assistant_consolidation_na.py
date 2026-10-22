from __future__ import annotations

from test_assistant_context_c2 import c2
from test_assistant_context_c3 import c3, history, state_for, notes
from assistant_context_support import mixed_checkpoint

import json
import asyncio
from datetime import datetime, timedelta, timezone

from assistant_context_support import ContextHarness
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.store import AssistantRunStore
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.runtime import AssistantExecutionGraph
from shiliu.assistant.provider import ModelTurn
from shiliu.db import Database


def _setup(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="N-A", all_active=True)
    thread = store.create_thread(space["id"])
    return db, store, thread


def test_large_input_is_not_forced_into_old_window(app_paths):
    db, store, thread = _setup(app_paths)
    run = store.create_run(thread["id"], text="核对材料：" + "中文证据" * 20000,
                           request_id="na-large")
    messages, estimated, metadata = ContextHarness(MemoryService(db)).request_input(
        store.run_context(run["id"]), tool_schemas=[])
    assert estimated > 24000
    assert estimated < 256000
    assert messages[-1]["role"] == "user"
    assert metadata["task_note_version"] is None


def test_stop_keeps_user_words_and_completed_read_pair(c3):
    from test_assistant_context_c2 import running, batch, read
    first = running(c3, text='逐篇核对这几份')
    batch(c3,first,[('read-a','collection_read',{},read(c3,'read-a'))])
    c3.store.cancel_run(first['id'])
    following = running(c3,text='刚才那几份继续',key='follow')
    candidate = c3.composer.prepare(following['id'],provider=c3.provider)
    assert '逐篇核对这几份' in str(candidate.request.body) and '甲乙丙丁条件' in str(candidate.request.body)
    assert any(m.get('tool_calls') for m in candidate.request.body['messages'])


def test_idle_gate_uses_user_activity_and_frontend_completion(app_paths):
    db, store, thread = _setup(app_paths)
    old = (datetime.now(timezone.utc) - timedelta(seconds=220)).isoformat(timespec="seconds")
    assert store.maintenance_idle(startup_at=old)
    run = store.create_run(thread["id"], text="现在找材料", request_id="na-idle")
    assert not store.maintenance_idle(startup_at=old)
    store.cancel_run(run["id"])
    assert not store.maintenance_idle(startup_at=old)
    with db.connect() as connection:
        connection.execute("UPDATE assistant_messages SET created_at=? WHERE run_id=?", (old, run["id"]))
        connection.execute("UPDATE assistant_runs SET completed_at=? WHERE id=?", (old, run["id"]))
        connection.execute("UPDATE assistant_runtime_state SET value=? WHERE key='last_user_activity_at'", (old,))
    assert store.maintenance_idle(startup_at=old)


def test_task_focus_is_bound_to_real_user_message(app_paths):
    db, store, thread = _setup(app_paths)
    run = store.create_run(thread["id"], text="请改为核对三份材料", request_id="na-focus")
    claimed = store.claim_next_run()
    focus = store.save_task_focus(run["id"], epoch=claimed["run_epoch"], focus={
        "goal": "核对三份材料", "selected_source_refs": [],
        "requirements": ["只看三份"], "working_notes": "已找到两份"})
    assert focus["user_quote"] == "请改为核对三份材料"
    assert focus["source_message_id"]
    messages, _, _ = ContextHarness(MemoryService(db)).request_input(
        store.run_context(run["id"]), tool_schemas=[])
    assert "核对三份材料" in str(messages)


def test_cancelled_user_quote_is_searchable_without_matching_current_question(app_paths):
    db, store, thread = _setup(app_paths)
    first = store.create_run(thread["id"], text="你现在把每一篇原文都看一遍，看看有没有漏掉的名字来",
                             request_id="na-quote")
    store.cancel_run(first["id"])
    current = store.create_run(thread["id"], text="我说过每一篇原文吗？", request_id="na-quote-query")
    registry = AssistantToolRegistry(sources=None, memories=MemoryService(db), store=store)
    result = asyncio.run(registry.execute(
        name="conversation_history", arguments={"query": "每一篇原文都看一遍 漏掉的名字"},
        call_id="history", run_context=store.run_context(current["id"])))
    found = result["items"][0]["messages"]
    assert len(found) == 1
    assert found[0]["exact_user_text"].startswith("你现在把每一篇原文")
    assert found[0]["run_status"] == "cancelled"


def test_maintenance_claim_gate_keeps_auto_jobs_queued(app_paths):
    db, store, _thread = _setup(app_paths)
    with db.connect() as connection:
        store.enqueue_job(connection, kind="memory_extract", dedupe_key="na:auto", payload={})
    assert store.claim_job(owner="na", allow_model_jobs=False, allow_maintenance=False) is None
    job = store.claim_job(owner="na", allow_model_jobs=True, allow_maintenance=True)
    assert job and job["kind"] == "memory_extract"


def test_presentable_answer_removes_internal_source_handle():
    answer = AssistantExecutionGraph._presentable_answer("可参考《甲》（video:12），名称尚待核对。")
    assert "video:12" not in answer
    assert "名称尚待核对" in answer


def test_finish_requested_uses_one_tool_free_answer(app_paths):
    db, store, thread = _setup(app_paths)
    run = store.create_run(thread["id"], text="先找材料", request_id="na-finish")
    store.request_finish(run["id"])
    claimed = store.claim_next_run()
    assert claimed and claimed["working_state"]["finish_requested"]

    class Provider:
        calls = 0

        def turn(self, *, messages, tools, max_tokens):
            self.calls += 1
            assert tools == []
            assert max_tokens == 8192
            return ModelTurn(text="目前没有完成读取，暂不能给出材料结论。",
                             usage={"prompt_tokens": 12, "completion_tokens": 10})

    provider = Provider()
    from test_assistant_consolidation_na_review import graph as control_graph
    graph = control_graph(store, MemoryService(db), AssistantToolRegistry(sources=None, memories=MemoryService(db),store=store),provider)
    graph.dependency_ref_validator = None
    asyncio.run(graph.run(store.get_run(run["id"])))
    finished = store.get_run(run["id"])
    assert finished["status"] == "completed"
    assert "没有完成读取" in store.get_thread(thread["id"])["messages"][-1]["content"]
    assert provider.calls == 1
