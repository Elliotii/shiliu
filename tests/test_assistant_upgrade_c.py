from __future__ import annotations

from test_assistant_context_c2 import c2
from test_assistant_context_c3 import c3, history, state_for, notes
from assistant_context_support import mixed_checkpoint

from datetime import datetime, timedelta, timezone
import json

from assistant_context_support import ContextHarness
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.memory_policy import anchored_validity, forbids_auto_save, plausible_personal_excerpt
from shiliu.assistant.store import AssistantRunStore
from shiliu.assistant.task_notes import TaskNoteService
from shiliu.db import Database


def test_excluded_topic_does_not_trigger_personal_recall(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="影像与面试", all_active=True)
    memories = MemoryService(db)
    memories.save_explicit(
        text="面试技术选型先比较 SQLite 与 Redis，尚未决定",
        subject_key="面试技术选型", kind="decision", scope_kind="space",
        scope_id=space["id"], operation_key="c-excluded-topic",
    )
    unrelated = store.create_thread(space["id"])
    run = store.create_run(unrelated["id"],
        text="找夏日湖泊胶片氛围，不要用之前的个人决定", request_id="c-unrelated")
    messages, _ = ContextHarness(memories).request_messages(store.run_context(run["id"]))
    assert "SQLite 与 Redis" not in str(messages)
    related = store.create_thread(space["id"])
    run = store.create_run(related["id"],
        text="我的面试技术选型现在决定采用 Redis 了吗？", request_id="c-related")
    messages, _ = ContextHarness(memories).request_messages(store.run_context(run["id"]))
    assert "SQLite 与 Redis" in str(messages)


def test_relative_time_is_anchored_and_old_note_expires_without_epoch_change(c3, monkeypatch):
    from test_assistant_context_c2 import running
    assert anchored_validity('下周有面试','2026-09-24T10:00:00+08:00') == {}
    validity = anchored_validity('这条记忆下周适用','2026-09-24T10:00:00+08:00')
    assert validity['expires_at']=='2026-10-04T16:00:00+00:00'
    assert anchored_validity('这条约束接下来三周有效','2026-09-24T10:00:00+08:00')['expires_at']=='2026-10-14T16:00:00+00:00'
    monkeypatch.setattr('shiliu.assistant.memory.utc_now',lambda:'2026-09-24T02:00:00+00:00')
    memory, candidate = mixed_checkpoint(c3,personal='下周面试优先准备后端项目说明',kind='context')
    with c3.db.connect() as connection:
        connection.execute('UPDATE assistant_memories SET expires_at=? WHERE id=?',(validity['expires_at'],memory['id']))
    assert c3.graph.task_notes.valid_for_context(c3.thread['id'],space_id=c3.space['id'],scope_version=1)
    epoch = c3.memories.current_epoch()
    monkeypatch.setattr('shiliu.assistant.memory.utc_now',lambda:'2026-10-04T16:00:00+00:00')
    assert c3.memories.current_epoch()==epoch
    assert not c3.memories.validate_dependency_refs([c3.memories.dependency_ref(memory)],space_id=c3.space['id'])['valid']
    assert c3.graph.task_notes.valid_for_context(c3.thread['id'],space_id=c3.space['id'],scope_version=1) is None
    run = running(c3,text='继续核对材料',key='expired')
    fresh = c3.composer.prepare(run['id'],provider=c3.provider)
    assert not fresh.checkpoint and '优先准备后端项目说明' not in str(fresh.request.body)


def test_auto_switch_and_provenance_guards(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="收藏", all_active=True)
    memories = MemoryService(db)
    assert memories.auto_enabled()
    memories.set_auto_enabled(False)
    assert not memories.auto_enabled()
    proposal = {"op": "add", "kind": "context", "text": "我准备面试", "subject_key": "interview",
                "scope_kind": "space", "scope_id": space["id"], "source_excerpt": "我准备面试"}
    assert memories.apply_extracted(proposal, source_message_ids=["m1"], expected_epoch=0,
                                    operation_key="auto-off") is None
    explicit = memories.save_explicit(text="我准备面试", subject_key="interview", kind="context",
                                      scope_kind="space", scope_id=space["id"], operation_key="explicit-on")
    assert explicit["status"] == "active"
    assert memories.recall("推荐一道好吃的甜点", space_id=space["id"]) == []
    assert memories.recall("我的面试准备先看什么", space_id=space["id"])
    assert forbids_auto_save("仅本次使用，不要保存我的情况")
    assert not forbids_auto_save("不要保存这段分析，但我下周有面试")
    assert forbids_auto_save("不要保存这段分析，也不要记住我的情况")
    assert not plausible_personal_excerpt("作者说该方案最好", "decision")
    assert not plausible_personal_excerpt("假设我决定用该方案", "decision")
    assert plausible_personal_excerpt("我还在比较两种后端方案", "context")
    assert not plausible_personal_excerpt("我还在比较两种后端方案", "decision")


def test_cancel_does_not_undo_confirmed_memory_or_reanimate_run(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="取消回答", all_active=True)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="请记住我正在准备面试，并找材料", request_id="cancel-c")
    memory = MemoryService(db).save_explicit(
        text="我正在准备面试", subject_key="interview", kind="context", scope_kind="space",
        scope_id=space["id"], operation_key="confirmed-before-cancel")
    store.cancel_run(run["id"])
    assert MemoryService(db).get(memory["id"])["status"] == "active"
    assert store.get_run(run["id"])["status"] == "cancelled"
    following = store.create_run(thread["id"], text="继续聊新问题", request_id="after-cancel-c")
    assert following["status"] == "queued"
