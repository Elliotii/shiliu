from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from shiliu.assistant.context import ContextComposer
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.memory_policy import anchored_validity, forbids_auto_save, plausible_personal_excerpt
from shiliu.assistant.store import AssistantRunStore
from shiliu.assistant.task_notes import TaskNoteService
from shiliu.db import Database


def test_relative_time_is_anchored_and_old_note_expires_without_epoch_change(app_paths, monkeypatch):
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="面试材料", all_active=True)
    memories = MemoryService(db)
    notes = TaskNoteService(db, memories)
    said_at = "2026-09-24T10:00:00+08:00"
    validity = anchored_validity("下周有面试", said_at)
    assert validity and validity["expires_at"] == "2026-10-04T16:00:00+00:00"
    duration = anchored_validity("今天确定接下来三周补数据库基础", said_at)
    assert duration and duration["expires_at"] == "2026-10-15T16:00:00+00:00"
    monkeypatch.setattr("shiliu.assistant.memory.utc_now", lambda: "2026-09-24T02:00:00+00:00")
    memory = memories.save_explicit(
        text="下周有面试，优先准备后端项目说明", subject_key="interview_week",
        kind="context", scope_kind="space", scope_id=space["id"],
        operation_key="time-c", **validity,
    )
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="先看哪份准备材料？", request_id="time-c-run")
    ref = memories.dependency_ref(memory)
    assert memories.validate_dependency_refs([ref], space_id=space["id"])["valid"]
    assert ref in [m["dependency_ref"] for m in memories.recall("面试准备后端", space_id=space["id"])]
    candidate = notes.build_candidate(store.run_context(run["id"]),
                                      messages=store.run_context(run["id"])["thread"]["messages"],
                                      recalled_memories=[], covered_until_message_seq=1)
    candidate["dependencies"].append(ref)
    # A B-style material summary can contain a personal judgement. Its own
    # dependency must expire even when the material locator remains valid.
    store.save_assistant_tool_message(run["id"], content="", provider_payload={"tool_calls": [{
        "id": "read-c", "type": "function", "function": {"name": "collection_read", "arguments": "{}"},
    }]})
    tool_id = store.save_tool_result_message(run["id"], content=json.dumps({
        "status": "ok", "source_refs": ["video:1:rev"],
        "result_ref": f"run-result:{run['id']}:read-c", "dependency_refs": [ref],
        "items": [{"content": "独立的数据库材料"}],
    }), provider_payload={"tool_call_id": "read-c", "name": "collection_read"})
    tool_seq = next(m["seq"] for m in store.get_thread(thread["id"])["messages"] if m["id"] == tool_id)
    candidate["findings"].append({"kind": "semantic_summary", "text": "因下周面试应先看该材料",
                                  "message_seq": tool_seq, "source_ref": "video:1:rev",
                                  "dependencies": [ref, "video:1:rev"]})
    candidate["covered_until_message_seq"] = tool_seq
    note = notes.commit(thread["id"], candidate)
    assert notes.valid_for_context(thread["id"], space_id=space["id"], scope_version=space["scope_version"])
    epoch = memories.current_epoch()
    monkeypatch.setattr("shiliu.assistant.memory.utc_now", lambda: "2026-10-04T16:00:00+00:00")
    assert memories.current_epoch() == epoch
    assert memories.recall("面试准备后端", space_id=space["id"]) == []
    assert not memories.validate_dependency_refs([ref], space_id=space["id"])["valid"]
    assert notes.valid_for_context(thread["id"], space_id=space["id"], scope_version=space["scope_version"]) is None
    rebuilt = notes.build_candidate(store.run_context(run["id"]),
                                    messages=store.run_context(run["id"])["thread"]["messages"],
                                    recalled_memories=[], covered_until_message_seq=tool_seq)
    assert not any(f.get("text") == "因下周面试应先看该材料" for f in rebuilt["findings"])
    with db.connect() as connection:
        assert not AssistantRunStore._memory_refs_valid(connection, [ref],
                                                         space_id=space["id"], now="2026-10-04T16:00:00+00:00")
    messages, _, _ = ContextComposer(memories, task_notes=notes).compose_with_metadata(store.run_context(run["id"]))
    assert "优先准备后端项目说明" not in str(messages)
    assert note["note_version"] == 1


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
