from __future__ import annotations

from test_assistant_context_c2 import c2
from test_assistant_context_c3 import c3, history, state_for, notes
from assistant_context_support import mixed_checkpoint

import json

import pytest

from assistant_context_support import ContextHarness
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.store import AssistantRunStore
from shiliu.assistant.task_notes import TaskNoteService
from shiliu.db import Database


@pytest.mark.parametrize("change,question,expected", [
    ("correct", "继续看这个问题", True),
    ("forget", "继续看这个问题", False),
    ("expire", "继续看这个问题", False),
    ("correct", "继续推荐美食", False),
    ("correct", "继续看这个问题，但不要用之前的个人决定", False),
])
def test_recent_task_dependency_rechecks_current_memory(app_paths, monkeypatch, change, question, expected):
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="隔离面试资料", all_active=True)
    memories = MemoryService(db)
    old = memories.save_explicit(
        text="我的旧判断：面试演示选 Redis。", subject_key="面试演示架构",
        kind="decision", scope_kind="space", scope_id=space["id"], operation_key="qa:old",
    )
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="核对面试演示架构的材料", request_id="qa:first")
    ref = memories.dependency_ref(old)
    store.save_assistant_tool_message(run["id"], content="", provider_payload={"tool_calls": [{
        "id": "read", "type": "function", "function": {"name": "knowledge_read", "arguments": "{}"},
    }]})
    store.save_tool_result_message(run["id"], content=json.dumps({
        "status": "ok", "dependency_refs": [ref], "items": [{"content": "独立材料：先列适用条件。"}],
    }, ensure_ascii=False), provider_payload={"tool_call_id": "read", "name": "knowledge_read"})
    store.cancel_run(run["id"])
    new = memories.correct(old["id"], text="我的新判断：面试演示先比较 SQLite 和 Redis。",
                           expected_version=old["version"], operation_key="qa:new")
    if change == "forget":
        memories.forget(old["id"], expected_version=new["version"], operation_key="qa:forget")
    elif change == "expire":
        monkeypatch.setattr("shiliu.assistant.memory.utc_now", lambda: "2100-01-01T00:00:00+00:00")
        with db.connect() as connection:
            connection.execute("UPDATE assistant_memories SET expires_at=? WHERE id=?",
                               ("2099-01-01T00:00:00+00:00", old["id"]))
    continuation = store.create_run(thread["id"], text=question, request_id="qa:next")
    messages, _, metadata = ContextHarness(memories).request_input(store.run_context(continuation["id"]))
    projection = json.dumps(messages, ensure_ascii=False)
    assert ("我的新判断：面试演示先比较 SQLite 和 Redis" in projection) is expected
    assert "我的旧判断：面试演示选 Redis" not in projection
    if expected:
        assert memories.dependency_ref(new) in metadata["dependency_refs"]
    else:
        assert memories.dependency_ref(new) not in metadata['dependency_refs']



def test_linked_candidate_still_obeys_space_and_version_fence(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    first = store.create_space(name="甲", all_active=True)
    second = store.create_space(name="乙", all_active=True)
    memories = MemoryService(db)
    old = memories.save_explicit(text="隔离决定甲", subject_key="专属主题", kind="decision",
                                 scope_kind="space", scope_id=first["id"], operation_key="qa:scope")
    assert memories.recall_with_status("继续", space_id=second["id"], linked_ids=[old["id"]])["items"] == []
    selected = memories.recall_with_status("继续", space_id=first["id"], linked_ids=[old["id"]])["items"]
    assert selected[0]["version"] == old["version"]
    new = memories.correct(old["id"], text="隔离决定乙", expected_version=old["version"], operation_key="qa:fence")
    assert not memories.validate_dependency_refs([memories.dependency_ref(old)], space_id=first["id"])["valid"]
    selected = memories.recall_with_status("继续", space_id=first["id"], linked_ids=[old["id"]])["items"]
    assert selected[0]["version"] == new["version"]
    assert selected[0]["dependency_ref"] == memories.dependency_ref(new)


def test_excluded_personal_background_does_not_reenter_from_task_note_goal(c3):
    from test_assistant_context_c2 import running
    memory, previous = mixed_checkpoint(c3)
    run = running(c3, text='继续核对，但不要用之前的个人决定', key='exclude')
    candidate = c3.composer.prepare(run['id'], provider=c3.provider)
    text = json.dumps(candidate.request.body['messages'], ensure_ascii=False)
    assert '面试演示架构采用 Redis' not in text
    assert '甲乙丙丁条件' in text and '独立材料说明适用条件' in text
    assert not candidate.checkpoint
    assert c3.memories.dependency_ref(memory) not in candidate.metadata['dependency_refs']
    assert c3.graph.task_notes.get(c3.thread['id'])['note_version'] == previous.checkpoint['note_version']


@pytest.mark.parametrize("source", ["lexical", "pinned", "semantic"])
def test_current_turn_decision_exclusion_is_final_admission(app_paths, source):
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="隔离材料", all_active=True)

    class SemanticBackend:
        def search(self, query, *, top_k, scope_key):
            return ([{"metadata": {"record_id": decision["id"],
                                    "record_version": decision["version"]}, "score": 0.98}]
                    if scope_key == f"space:{space['id']}" else [])

    memories = MemoryService(db)
    decision_text = ("我选择 PostgreSQL" if source == "semantic"
                     else "我的面试演示架构采用 Redis")
    decision = memories.save_explicit(
        text=decision_text,
        subject_key="数据库路线" if source == "semantic" else "面试演示架构",
        kind="decision", scope_kind="space", scope_id=space["id"],
        pinned=source == "pinned", operation_key=f"qa:r1:{source}:decision",
    )
    preference = memories.save_explicit(
        text="回答请用简短中文", subject_key="表达方式", kind="preference",
        scope_kind="space", scope_id=space["id"], pinned=True,
        operation_key=f"qa:r1:{source}:preference",
    )
    if source == "semantic":
        memories = MemoryService(db, backend=SemanticBackend())
        semantic = memories.recall_with_status("核对面试演示架构", space_id=space["id"])["items"]
        assert any(item["id"] == decision["id"] and "semantic" in item["recall_reasons"]
                   for item in semantic)
    elif source == "pinned":
        pinned = memories.recall_with_status("无关话题", space_id=space["id"])["items"]
        assert any(item["id"] == decision["id"] and "explicit_or_pending" in item["recall_reasons"]
                   for item in pinned)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"],
        text="继续核对面试演示架构，但不要用之前的个人决定；请简短回答。",
        request_id=f"qa:r1:{source}:run")
    messages, _, metadata = ContextHarness(memories).request_input(store.run_context(run["id"]))
    system = json.dumps(messages, ensure_ascii=False)
    assert decision_text not in system
    assert memories.dependency_ref(decision) not in metadata["dependency_refs"]
    assert "回答请用简短中文" in system
    assert memories.dependency_ref(preference) in metadata["dependency_refs"]
    assert memories.get(decision["id"])["status"] == "active"
    store.cancel_run(run["id"])
    next_run = store.create_run(thread["id"], text="继续核对面试演示架构，参考我的决定",
                                request_id=f"qa:r1:{source}:next")
    next_messages, _, next_metadata = ContextHarness(memories).request_input(
        store.run_context(next_run["id"])
    )
    assert decision_text in json.dumps(next_messages, ensure_ascii=False)
    assert memories.dependency_ref(decision) in next_metadata["dependency_refs"]


def test_narrow_old_scheme_rejection_keeps_corrected_decision(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="隔离材料", all_active=True)
    memories = MemoryService(db)
    old = memories.save_explicit(text="旧方案直接采用 Redis", subject_key="面试演示架构",
                                 kind="decision", scope_kind="space", scope_id=space["id"],
                                 operation_key="qa:r1:old")
    new = memories.correct(old["id"], text="新方案先比较 SQLite 与 Redis",
                           expected_version=old["version"], operation_key="qa:r1:new")
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="继续核对面试演示架构，不要照搬旧方案",
                           request_id="qa:r1:narrow")
    messages, _, metadata = ContextHarness(memories).request_input(store.run_context(run["id"]))
    assert "新方案先比较 SQLite 与 Redis" in json.dumps(messages, ensure_ascii=False)
    assert memories.dependency_ref(new) in metadata["dependency_refs"]


def test_broad_personal_background_exclusion_filters_other_memory_kinds(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="隔离材料", all_active=True)
    memories = MemoryService(db)
    background = memories.save_explicit(text="我的面试演示下周开始", subject_key="面试演示",
                                        kind="context", scope_kind="space", scope_id=space["id"],
                                        pinned=True, operation_key="qa:r1:background")
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="继续核对面试演示，但不要用之前的个人背景",
                           request_id="qa:r1:broad")
    messages, _, metadata = ContextHarness(memories).request_input(store.run_context(run["id"]))
    assert "我的面试演示下周开始" not in json.dumps(messages, ensure_ascii=False)
    assert memories.dependency_ref(background) not in metadata["dependency_refs"]
    assert memories.get(background["id"])["status"] == "active"


def test_exclusion_filters_actual_task_note_render_without_hiding_material(c3):
    from test_assistant_context_c2 import running
    memory, previous = mixed_checkpoint(c3)
    run = running(c3, text='继续核对，但不要用之前的个人决定', key='exclude')
    candidate = c3.composer.prepare(run['id'], provider=c3.provider)
    text = json.dumps(candidate.request.body['messages'], ensure_ascii=False)
    assert '面试演示架构采用 Redis' not in text
    assert '甲乙丙丁条件' in text and '独立材料说明适用条件' in text
    assert not candidate.checkpoint
    assert c3.memories.dependency_ref(memory) not in candidate.metadata['dependency_refs']
    assert c3.graph.task_notes.get(c3.thread['id'])['note_version'] == previous.checkpoint['note_version']


def test_exclusion_keeps_only_note_carried_independent_task_state(c3):
    from test_assistant_context_c2 import running
    _, previous = mixed_checkpoint(c3)
    run = running(c3, text='继续，但不要参考个人决定', key='independent')
    candidate = c3.composer.prepare(run['id'], provider=c3.provider)
    text = json.dumps(candidate.request.body['messages'], ensure_ascii=False)
    assert not candidate.checkpoint
    assert all(term in text for term in ['完整阅读两份材料后比较条件','本轮只分析，不保存','继续读第二份材料'])
    assert '面试演示架构采用 Redis' not in text
    assert any(m['role'] == 'user' for m in candidate.request.body['messages'])
    assert c3.graph.task_notes.get(c3.thread['id'])['note_version'] == previous.checkpoint['note_version']


def test_mixed_note_projects_only_excluded_personal_content(c3):
    from test_assistant_context_c2 import running
    memory, previous = mixed_checkpoint(c3)
    run = running(c3, text='继续核对，但不要用之前的个人决定', key='exclude')
    candidate = c3.composer.prepare(run['id'], provider=c3.provider)
    text = json.dumps(candidate.request.body['messages'], ensure_ascii=False)
    assert '面试演示架构采用 Redis' not in text
    assert '甲乙丙丁条件' in text and '独立材料说明适用条件' in text
    assert not candidate.checkpoint
    assert c3.memories.dependency_ref(memory) not in candidate.metadata['dependency_refs']
    assert c3.graph.task_notes.get(c3.thread['id'])['note_version'] == previous.checkpoint['note_version']
