from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from shiliu.assistant.context import ContextComposer
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.provider import ModelTurn, NativeToolCall
from shiliu.assistant.runtime import AssistantExecutionGraph
from shiliu.assistant.store import (
    AssistantConflict,
    AssistantRunStore,
    ModelBudgetWait,
)
from shiliu.assistant.task_notes import TaskNoteService
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.wiki import WikiService
from shiliu.db import Database, SCHEMA_VERSION, utc_now


def _services(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="S2-C", all_active=True, goal="比较收藏材料并形成可继续结论")
    memories = MemoryService(db)
    notes = TaskNoteService(db, memories)
    return db, store, space, memories, notes


def test_task_note_compacts_material_coverage_and_forget_removes_old_constraint(app_paths) -> None:
    _db, store, space, memories, notes = _services(app_paths)
    thread = store.create_thread(space["id"], title="连续探索")
    first = store.create_run(
        thread["id"],
        text="本项目必须优先比较可恢复性，" + "并保留原材料证据。" * 80,
        request_id="note-first",
    )
    claimed = store.claim_next_run()
    assert claimed and claimed["id"] == first["id"]
    first_context = store.run_context(first["id"])
    source_message = next(
        item for item in first_context["thread"]["messages"]
        if item["run_id"] == first["id"] and item["role"] == "user"
    )
    memory = memories.save_explicit(
        text="本项目优先比较可恢复性",
        subject_key="comparison_priority",
        kind="constraint",
        scope_kind="space",
        scope_id=space["id"],
        operation_key="note-memory-v1",
        source_message_ids=[source_message["id"]],
        source_excerpt="本项目必须优先比较可恢复性",
    )
    call_id = "read-real-material"
    store.save_assistant_tool_message(
        first["id"], content="", provider_payload={"tool_calls": [{
            "id": call_id, "type": "function",
            "function": {"name": "collection_read", "arguments": "{}"},
        }]},
    )
    store.save_tool_result_message(
        first["id"],
        content=json.dumps({
            "status": "ok", "summary": "已读取完整字幕并记录适用条件",
            "source_refs": ["video:7:rev"],
            "dependency_refs": [f"memory:{memory['id']}:1"],
            "coverage": {"material": "full_available_transcript"},
            "items": [{"view": "transcript", "coverage": "full_available_transcript"}],
        }, ensure_ascii=False),
        provider_payload={"tool_call_id": call_id, "name": "collection_read"},
    )
    outcome = store.try_complete_run(
        first["id"], epoch=claimed["run_epoch"], answer="旧答案采用可恢复性约束",
        usage={"total_tokens": 500}, expected_scope_version=space["scope_version"],
        expected_observed_memory_epoch=memories.current_epoch(),
        dependency_refs=[f"memory:{memory['id']}:1"], expected_task_note_version=None,
    )
    assert outcome == "completed"
    current = store.create_run(
        thread["id"], text="补充要求：继续查证第二份材料。", request_id="note-current"
    )
    composer = ContextComposer(
        memories, task_notes=notes,
    )
    messages, _cost, metadata = composer.compose_with_metadata(
        store.run_context(current["id"]),
        tool_schemas=[{"type": "function", "function": {"name": "collection_read"}}],
        force_compact=True,
    )
    note = notes.get(thread["id"])
    assert note is not None and metadata["compressed"] is True
    assert "优先比较可恢复性" in note["goal"]
    assert any("优先比较可恢复性" in item["quote"] for item in note["explicit_constraints"])
    assert note["searched_scope_and_material_refs"][0]["view"] == "transcript"
    assert "full_available_transcript" in json.dumps(
        note["searched_scope_and_material_refs"], ensure_ascii=False
    )
    assert metadata["tool_schema_tokens"] > 0
    assert "当前任务笔记" in json.dumps(messages, ensure_ascii=False)

    memories.forget(
        memory["id"], expected_version=1, operation_key="forget-note-constraint"
    )
    refreshed, _cost, refreshed_meta = composer.compose_with_metadata(
        store.run_context(current["id"]), tool_schemas=[]
    )
    encoded = json.dumps(refreshed, ensure_ascii=False)
    assert "本项目必须优先比较可恢复性" not in encoded
    assert "旧答案采用可恢复性约束" not in encoded
    assert refreshed_meta["task_note_version"] is None


def test_task_note_commit_rejects_memory_change_after_compression(app_paths) -> None:
    _db, store, space, memories, notes = _services(app_paths)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="必须保留准确引用", request_id="note-race")
    context = store.run_context(run["id"])
    message = next(item for item in context["thread"]["messages"] if item["role"] == "user")
    memory = memories.save_explicit(
        text="必须保留准确引用", subject_key="citation", kind="constraint",
        scope_kind="space", scope_id=space["id"], operation_key="citation-v1",
        source_message_ids=[message["id"]], source_excerpt=message["content"],
    )
    context = store.run_context(run["id"])
    context["run"]["observed_memory_epoch"] = memories.current_epoch()
    candidate = notes.build_candidate(
        context, messages=context["thread"]["messages"], recalled_memories=[{
            "dependency_ref": f"memory:{memory['id']}:1"
        }], covered_until_message_seq=message["seq"],
    )
    memories.correct(
        memory["id"], text="引用只保留原材料可核对部分", expected_version=1,
        operation_key="citation-v2",
    )
    with pytest.raises(AssistantConflict, match="task_note_memory_changed"):
        notes.commit(thread["id"], candidate)


def test_task_note_can_compact_completed_tool_groups_inside_current_run(app_paths) -> None:
    _db, store, _space, memories, notes = _services(app_paths)
    thread = store.create_thread(_space["id"])
    run = store.create_run(
        thread["id"], text="继续当前任务并读取多份原材料", request_id="same-run-note"
    )
    assert store.claim_next_run()
    for index in range(3):
        call_id = f"same-run-read-{index}"
        store.save_assistant_tool_message(
            run["id"], content="", provider_payload={"tool_calls": [{
                "id": call_id, "type": "function",
                "function": {"name": "collection_read", "arguments": "{}"},
            }]},
        )
        store.save_tool_result_message(
            run["id"],
            content=json.dumps({
                "status": "ok", "summary": f"已读材料 {index} " + "证据" * 120,
                "source_refs": [f"video:{index + 1}:{'a' * 64}"],
                "items": [{"view": "transcript", "coverage": "partial_transcript"}],
            }, ensure_ascii=False),
            provider_payload={"tool_call_id": call_id, "name": "collection_read"},
        )
    composer = ContextComposer(
        memories, task_notes=notes, input_budget_tokens=5000,
        compression_threshold=0.05, recent_groups=1,
    )
    messages, _cost, metadata = composer.compose_with_metadata(store.run_context(run["id"]))
    note = notes.get(thread["id"])
    assert note is not None
    assert run["id"] in note["source_run_ids"]
    assert len(note["searched_scope_and_material_refs"]) == 2
    assert metadata["compressed"] is True
    assert metadata["retained_history_tokens"] < metadata["uncompressed_history_tokens"]
    assert sum(message["role"] == "tool" for message in messages) == 1


def test_identical_read_only_tool_call_reuses_durable_result_in_same_run(app_paths) -> None:
    db, store, space, memories, _notes = _services(app_paths)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="读取材料", request_id="tool-reuse")
    with db.connect() as connection:
        connection.execute(
            """
            INSERT INTO videos(
                id,platform,source_id,part,title,video_url,status,discovered_at,updated_at
            ) VALUES(7,'test','stable-read',1,'稳定材料','https://example.test/7',
                     'completed',?,?)
            """,
            (utc_now(), utc_now()),
        )
        connection.execute(
            """
            INSERT INTO assistant_source_heads(
                principal_id,video_id,metadata_hash,content_hash,membership_hash,
                current_revision,updated_at
            ) VALUES('local_operator',7,'m','c','s','rev-1',?)
            """,
            (utc_now(),),
        )
    registry = AssistantToolRegistry(
        sources=SimpleNamespace(source_refs_visible=lambda _refs, _scope: True),
        memories=memories, store=store, wiki=None, context7=None,
    )
    assert store.begin_tool_call(
        run["id"], ordinal=1, call_id="read-1", name="collection_read",
        arguments={"source_ref": "video:7", "view": "transcript"},
    ) is None
    store.finish_tool_call(
        run["id"], call_id="read-1",
        result={
            "status": "ok", "summary": "持久结果", "items": [{"content": "正文"}],
            "source_refs": ["video:7:rev-1"],
        },
    )
    reused = store.begin_tool_call(
        run["id"], ordinal=2, call_id="read-2", name="collection_read",
        arguments={"view": "transcript", "source_ref": "video:7"},
        reuse_validator=lambda candidate: registry.reusable_result_valid(
            candidate, run_context=store.run_context(run["id"])
        ),
    )
    assert reused is not None
    assert json.loads(reused["result_json"])["summary"] == "持久结果"
    with db.connect() as connection:
        calls = connection.execute(
            "SELECT call_id,status,result_json FROM assistant_tool_calls "
            "WHERE run_id=? ORDER BY ordinal", (run["id"],),
        ).fetchall()
        event = connection.execute(
            "SELECT event_type,payload_json FROM assistant_run_events "
            "WHERE run_id=? AND event_type='tool_reused'", (run["id"],),
        ).fetchone()
    assert [row["call_id"] for row in calls] == ["read-1", "read-2"]
    assert all(row["status"] == "completed" for row in calls)
    assert event is not None and json.loads(event["payload_json"])["reused_call_id"] == "read-1"


def test_invalid_or_failed_results_do_not_bypass_historical_dependency_checks(app_paths) -> None:
    _db, store, space, memories, notes = _services(app_paths)
    sources = SimpleNamespace(source_refs_visible=lambda _refs, _scope: True)
    registry = AssistantToolRegistry(
        sources=sources, memories=memories, store=store, wiki=None, context7=None
    )
    guarded_notes = TaskNoteService(
        store.db, memories, dependency_ref_validator=registry.dependency_refs_valid
    )
    thread = store.create_thread(space["id"])
    memory = memories.save_explicit(
        text="旧的 UI 直接保存约束", subject_key="ui_only", kind="constraint",
        scope_kind="space", scope_id=space["id"], operation_key="ui-only-v1",
        source_message_ids=[],
    )

    first = store.create_run(thread["id"], text="查找 UI 约束", request_id="dep-first")
    claimed_first = store.claim_next_run()
    assert claimed_first and claimed_first["id"] == first["id"]
    first_call = "memory-result"
    store.save_assistant_tool_message(
        first["id"], content="", provider_payload={"tool_calls": [{
            "id": first_call, "type": "function",
            "function": {"name": "memory_search", "arguments": "{}"},
        }]},
    )
    first_result = asyncio.run(registry.execute(
        name="memory_search", arguments={"query": "UI 约束"}, call_id=first_call,
        run_context=store.run_context(first["id"]),
    ))
    first_ref = f"run-result:{first['id']}:{first_call}"
    first_result["result_ref"] = first_ref
    assert store.begin_tool_call(
        first["id"], ordinal=1, call_id=first_call, name="memory_search",
        arguments={"query": "UI 约束"},
    ) is None
    store.finish_tool_call(first["id"], call_id=first_call, result=first_result)
    store.save_tool_result_message(
        first["id"], content=json.dumps(first_result, ensure_ascii=False),
        provider_payload={"tool_call_id": first_call, "name": "memory_search"},
    )
    assert store.try_complete_run(
        first["id"], epoch=claimed_first["run_epoch"], answer="旧的 UI 直接保存约束",
        usage={}, expected_scope_version=space["scope_version"],
        expected_observed_memory_epoch=memories.current_epoch(),
        dependency_refs=[f"memory:{memory['id']}:1", first_ref],
        expected_task_note_version=None,
        dependency_validator=registry.dependency_refs_valid,
    ) == "completed"

    second = store.create_run(thread["id"], text="回读上次工具结果", request_id="dep-second")
    claimed_second = store.claim_next_run()
    assert claimed_second and claimed_second["id"] == second["id"]
    read_call = "read-old-result"
    read_result = asyncio.run(registry.execute(
        name="run_read_result", arguments={"result_ref": first_ref}, call_id=read_call,
        run_context=store.run_context(second["id"]),
    ))
    read_ref = f"run-result:{second['id']}:{read_call}"
    read_result["result_ref"] = read_ref
    assert "旧的 UI 直接保存约束" in json.dumps(read_result, ensure_ascii=False)
    assert store.begin_tool_call(
        second["id"], ordinal=1, call_id=read_call, name="run_read_result",
        arguments={"result_ref": first_ref},
        reuse_validator=lambda _candidate: True,
    ) is None
    store.finish_tool_call(second["id"], call_id=read_call, result=read_result)
    store.save_assistant_tool_message(
        second["id"], content="", provider_payload={"tool_calls": [{
            "id": read_call, "type": "function",
            "function": {"name": "run_read_result", "arguments": "{}"},
        }]},
    )
    store.save_tool_result_message(
        second["id"], content=json.dumps(read_result, ensure_ascii=False),
        provider_payload={"tool_call_id": read_call, "name": "run_read_result"},
    )
    assert store.try_complete_run(
        second["id"], epoch=claimed_second["run_epoch"], answer="回读：旧的 UI 直接保存约束",
        usage={}, expected_scope_version=space["scope_version"],
        expected_observed_memory_epoch=memories.current_epoch(), dependency_refs=[first_ref],
        expected_task_note_version=None,
        dependency_validator=registry.dependency_refs_valid,
    ) == "completed"

    second_context = store.run_context(second["id"])
    guarded_notes.commit(
        thread["id"],
        guarded_notes.build_candidate(
            second_context,
            messages=second_context["thread"]["messages"],
            recalled_memories=[],
            covered_until_message_seq=max(
                int(item["seq"]) for item in second_context["thread"]["messages"]
            ),
        ),
    )

    current = store.create_run(thread["id"], text="继续，但只用仍有效信息", request_id="dep-current")
    claimed_current = store.claim_next_run()
    assert claimed_current and claimed_current["id"] == current["id"]
    composer = ContextComposer(
        memories, task_notes=guarded_notes, input_budget_tokens=12000,
        dependency_ref_validator=registry.dependency_refs_valid,
    )
    before, _cost, metadata = composer.compose_with_metadata(store.run_context(current["id"]))
    assert "旧的 UI 直接保存约束" in json.dumps(before, ensure_ascii=False)
    assert first_ref in metadata["dependency_refs"]

    memories.correct(
        memory["id"], text="新的 UI 约束", expected_version=1,
        operation_key="ui-only-v2",
    )
    after, _cost, _after_metadata = composer.compose_with_metadata(store.run_context(current["id"]))
    assert "旧的 UI 直接保存约束" not in json.dumps(after, ensure_ascii=False)
    assert guarded_notes.valid_for_context(
        thread["id"], space_id=space["id"], scope_version=space["scope_version"]
    ) is None
    # Even with the observation epoch refreshed, the dependency captured only
    # through tool/history content prevents publishing the stale draft.
    assert store.try_complete_run(
        current["id"], epoch=claimed_current["run_epoch"], answer="旧答案",
        usage={}, expected_scope_version=space["scope_version"],
        expected_observed_memory_epoch=memories.current_epoch(),
        dependency_refs=metadata["dependency_refs"], expected_task_note_version=None,
        dependency_validator=registry.dependency_refs_valid,
    ) in {"memory_dependency_changed", "dependency_changed"}

    assert store.begin_tool_call(
        current["id"], ordinal=1, call_id="read-after-correct", name="run_read_result",
        arguments={"result_ref": first_ref},
        reuse_validator=lambda _candidate: True,
    ) is None
    stale_read = asyncio.run(registry.execute(
        name="run_read_result", arguments={"result_ref": first_ref},
        call_id="read-after-correct", run_context=store.run_context(current["id"]),
    ))
    assert stale_read["status"] == "unavailable"
    assert "旧的 UI 直接保存约束" not in json.dumps(stale_read, ensure_ascii=False)

    store.cancel_run(current["id"])
    failed_run = store.create_run(thread["id"], text="重试失败读取", request_id="failed-retry")
    assert store.begin_tool_call(
        failed_run["id"], ordinal=1, call_id="failed-1", name="collection_read",
        arguments={"source_ref": "video:7", "view": "transcript"},
    ) is None
    store.finish_tool_call(
        failed_run["id"], call_id="failed-1",
        result={"status": "unavailable", "summary": "临时失败", "retryable": True},
    )
    assert store.begin_tool_call(
        failed_run["id"], ordinal=2, call_id="failed-2", name="collection_read",
        arguments={"view": "transcript", "source_ref": "video:7"},
        reuse_validator=lambda _candidate: True,
    ) is None


def test_task_note_keeps_all_effective_constraints_and_completed_progress(app_paths) -> None:
    _db, store, space, memories, notes = _services(app_paths)
    thread = store.create_thread(space["id"])
    requirements = ["必须使用蓝色表格，只比较材料甲和乙"] + [
        f"必须保留独立条件 {index}" for index in range(2, 15)
    ]
    for index, requirement in enumerate(requirements, start=1):
        run = store.create_run(
            thread["id"], text=requirement, request_id=f"constraint-{index}"
        )
        claimed = store.claim_next_run()
        assert claimed and claimed["id"] == run["id"]
        assert store.try_complete_run(
            run["id"], epoch=claimed["run_epoch"], answer=f"已完成条件 {index}",
            usage={}, expected_scope_version=space["scope_version"],
            expected_observed_memory_epoch=memories.current_epoch(), dependency_refs=[],
            expected_task_note_version=None,
        ) == "completed"

    continuation = store.create_run(
        thread["id"], text="继续刚才已经完成的任务，只概括当前状态。",
        request_id="short-continuation",
    )
    context = store.run_context(continuation["id"])
    covered_until = max(
        int(item["seq"]) for item in context["thread"]["messages"]
        if item["run_id"] != continuation["id"]
    )
    candidate = notes.build_candidate(
        context, messages=context["thread"]["messages"], recalled_memories=[],
        covered_until_message_seq=covered_until,
    )
    note = notes.commit(thread["id"], candidate)
    rendered = notes.render(note)
    assert len(note["explicit_constraints"]) == len(requirements) + 1
    assert all(
        clause in rendered
        for requirement in requirements
        for clause in requirement.split("，")
    )
    assert "必须使用蓝色表格" in note["goal"]
    assert "只比较材料甲和乙" in note["goal"]
    assert note["open_questions"] == []
    assert note["next_actions"] == []
    assert any(
        item["kind"] == "task_progress" and "14 条用户要求" in item["text"]
        for item in note["findings"]
    )

    composer = ContextComposer(
        memories, task_notes=notes, input_budget_tokens=24000,
        compression_threshold=0.01, recent_groups=1,
    )
    messages, _cost, _metadata = composer.compose_with_metadata(context)
    encoded = json.dumps(messages, ensure_ascii=False)
    assert "必须使用蓝色表格" in encoded
    assert "只比较材料甲和乙" in encoded
    assert requirements[-1] in encoded
    assert "继续从原始材料或可回读结果查证尚未解决的问题" not in encoded

    store.cancel_run(continuation["id"])
    withdrawn = store.create_run(
        thread["id"], text="取消之前关于使用蓝色表格的要求。",
        request_id="withdraw-constraint",
    )
    claimed = store.claim_next_run()
    assert claimed and claimed["id"] == withdrawn["id"]
    assert store.try_complete_run(
        withdrawn["id"], epoch=claimed["run_epoch"], answer="已撤回该要求",
        usage={}, expected_scope_version=space["scope_version"],
        expected_observed_memory_epoch=memories.current_epoch(), dependency_refs=[],
        expected_task_note_version=None,
    ) == "completed"
    later = store.create_run(thread["id"], text="继续", request_id="after-withdraw")
    later_context = store.run_context(later["id"])
    later_candidate = notes.build_candidate(
        later_context, messages=later_context["thread"]["messages"],
        recalled_memories=[],
        covered_until_message_seq=max(
            int(item["seq"]) for item in later_context["thread"]["messages"]
            if item["run_id"] != later["id"]
        ),
    )
    assert all(
        "使用蓝色表格" not in item["quote"]
        for item in later_candidate["explicit_constraints"]
    )
    assert any(
        item["quote"] == "只比较材料甲和乙"
        for item in later_candidate["explicit_constraints"]
    )
    assert "使用蓝色表格" not in later_candidate["goal"]
    assert "只比较材料甲和乙" in later_candidate["goal"]
    later_note = notes.commit(thread["id"], later_candidate)
    assert "使用蓝色表格" not in notes.render(later_note)
    projected, _cost, projected_metadata = composer.compose_with_metadata(later_context)
    provider_input = json.dumps(projected, ensure_ascii=False)
    assert "必须使用蓝色表格" not in provider_input
    assert "只比较材料甲和乙" in provider_input
    claimed = store.claim_next_run()
    assert claimed and claimed["id"] == later["id"]
    assert store.try_complete_run(
        later["id"], epoch=claimed["run_epoch"],
        answer="继续按材料甲和乙的范围处理。", usage={},
        expected_scope_version=space["scope_version"],
        expected_observed_memory_epoch=projected_metadata["observed_memory_epoch"],
        dependency_refs=projected_metadata["dependency_refs"],
        expected_task_note_version=projected_metadata["task_note_version"],
    ) == "completed"
    final = [
        item for item in store.get_thread(thread["id"])["messages"]
        if item["run_id"] == later["id"] and item["role"] == "assistant"
    ]
    assert len(final) == 1
    assert "蓝色表格" not in final[0]["content"]


def test_current_forget_receipt_is_visible_and_final_confirmation_commits(app_paths) -> None:
    _db, store, space, memories, _notes = _services(app_paths)
    thread = store.create_thread(space["id"])
    memory = memories.save_explicit(
        text="旧正文：技术比较优先速度", subject_key="old_priority",
        kind="preference", scope_kind="space", scope_id=space["id"],
        operation_key="prepare-for-forget", source_message_ids=[],
    )
    run = store.create_run(
        thread["id"], text="请忘记刚才保存的技术比较偏好。",
        request_id="confirm-forget",
    )
    claimed = store.claim_next_run()
    assert claimed and claimed["id"] == run["id"]
    registry = AssistantToolRegistry(
        sources=SimpleNamespace(source_refs_visible=lambda _refs, _scope: True),
        memories=memories, store=store, wiki=None, context7=None,
    )

    class ConfirmingProvider:
        calls = 0
        second_input: list[dict[str, object]] | None = None

        def turn(self, *, messages, tools, max_tokens):
            self.calls += 1
            if self.calls == 1:
                return ModelTurn(text="", tool_calls=[
                    NativeToolCall(
                        call_id="search-before-forget", name="memory_search",
                        arguments={"query": "技术比较"},
                    ),
                    NativeToolCall(
                        call_id="forget-current", name="memory_forget",
                        arguments={"memory_id": memory["id"], "expected_version": 1},
                    ),
                ], usage={"total_tokens": 10})
            self.second_input = messages
            tool_calls = [
                call for item in messages if item["role"] == "assistant"
                for call in item.get("tool_calls", [])
            ]
            results = [json.loads(item["content"]) for item in messages if item["role"] == "tool"]
            assert len(tool_calls) == len(results) == 1
            assert tool_calls[0]["id"] == "forget-current"
            assert results[0]["status"] == "ok"
            assert results[0]["items"] == [{"status": "forgotten"}]
            assert results[0]["operation_receipt_verified"] is True
            assert "旧正文：技术比较优先速度" not in json.dumps(messages, ensure_ascii=False)
            assert not memories.recall("技术比较", space_id=space["id"])
            return ModelTurn(text="已忘记刚才保存的偏好。", usage={"total_tokens": 10})

    provider = ConfirmingProvider()
    graph = AssistantExecutionGraph(
        store=store, memories=memories, tools=registry,
        provider_factory=lambda: provider, max_steps=3,
    )
    asyncio.run(graph.run(claimed))
    assert provider.calls == 2 and provider.second_input is not None
    assert store.get_run(run["id"])["status"] == "completed"
    assert memories.get(memory["id"])["status"] == "forgotten"
    final = [
        item for item in store.get_thread(thread["id"])["messages"]
        if item["run_id"] == run["id"] and item["role"] == "assistant"
        and item["content"]
    ]
    assert len(final) == 1
    assert final[0]["content"] == "已忘记刚才保存的偏好。"
    assert f"run-result:{run['id']}:forget-current" in json.loads(
        final[0]["provider_payload_json"]
    )["dependency_refs"]


def test_observed_epoch_refresh_does_not_change_extraction_baseline(app_paths) -> None:
    db, store, space, memories, _notes = _services(app_paths)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="请记住旧消息", request_id="epoch-split")
    claimed = store.claim_next_run()
    assert claimed
    extraction_epoch = claimed["extraction_memory_epoch"]
    memories.save_explicit(
        text="无关的新约束", subject_key="unrelated", kind="constraint",
        scope_kind="space", scope_id=space["id"], operation_key="epoch-unrelated",
    )
    observed = memories.current_epoch()
    assert store.save_context_observation(
        run["id"], epoch=claimed["run_epoch"], metadata={
            "observed_memory_epoch": observed, "scope_version": space["scope_version"],
            "memory_dependency_refs": [], "task_note_version": None,
            "estimated_input_tokens": 100, "tool_schema_tokens": 10, "compressed": False,
        },
    )
    outcome = store.try_complete_run(
        run["id"], epoch=claimed["run_epoch"], answer="完成", usage={},
        expected_scope_version=space["scope_version"],
        expected_observed_memory_epoch=observed, dependency_refs=[],
        expected_task_note_version=None,
    )
    assert outcome == "completed"
    with db.connect() as connection:
        payload = json.loads(connection.execute(
            "SELECT payload_json FROM assistant_jobs WHERE kind='memory_extract' AND dedupe_key=?",
            (f"memory_extract:{run['id']}:v1",),
        ).fetchone()["payload_json"])
        epochs = connection.execute(
            "SELECT extraction_memory_epoch, observed_memory_epoch FROM assistant_runs WHERE id=?",
            (run["id"],),
        ).fetchone()
    assert payload["memory_epoch"] == extraction_epoch
    assert epochs["extraction_memory_epoch"] == extraction_epoch
    assert epochs["observed_memory_epoch"] == observed > extraction_epoch


def test_unrelated_space_memory_change_does_not_restart_final_commit(app_paths) -> None:
    _db, store, space, memories, _notes = _services(app_paths)
    other = store.create_space(name="另一个范围", video_ids=[99])
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="完成当前范围回答", request_id="scoped-epoch")
    claimed = store.claim_next_run()
    assert claimed and claimed["id"] == run["id"]
    observed = memories.current_epoch()
    memories.save_explicit(
        text="只属于另一个范围", subject_key="other_space", kind="constraint",
        scope_kind="space", scope_id=other["id"], operation_key="other-space-change",
    )
    assert memories.current_epoch() > observed
    outcome = store.try_complete_run(
        run["id"], epoch=claimed["run_epoch"], answer="当前范围回答完成", usage={},
        expected_scope_version=space["scope_version"],
        expected_observed_memory_epoch=observed, dependency_refs=[],
        expected_task_note_version=None,
    )
    assert outcome == "completed"
    assert store.get_run(run["id"])["observed_memory_epoch"] == memories.current_epoch()


def test_correction_and_forget_track_every_explicit_mutation_message(app_paths) -> None:
    _db, store, space, memories, _notes = _services(app_paths)
    thread = store.create_thread(space["id"])
    first = store.create_run(thread["id"], text="请记住旧约束", request_id="source-v1")
    first_message = next(
        item for item in store.get_thread(thread["id"])["messages"]
        if item["run_id"] == first["id"] and item["role"] == "user"
    )
    memory = memories.save_explicit(
        text="旧约束", subject_key="source_chain", kind="constraint",
        scope_kind="space", scope_id=space["id"], operation_key="source-chain-v1",
        source_message_ids=[first_message["id"]], source_excerpt=first_message["content"],
    )
    store.save_tool_result_message(
        first["id"], content=json.dumps({"items": [{"id": memory["id"]}]}, ensure_ascii=False),
        provider_payload={"tool_call_id": "save", "name": "memory_save"},
    )
    store.cancel_run(first["id"])
    second = store.create_run(thread["id"], text="把旧约束改成新约束", request_id="source-v2")
    second_message = next(
        item for item in store.get_thread(thread["id"])["messages"]
        if item["run_id"] == second["id"] and item["role"] == "user"
    )
    source_ids = AssistantToolRegistry._memory_mutation_source_message_ids(
        store.run_context(second["id"]), memory["id"], second_message["id"]
    )
    assert set(source_ids) == {first_message["id"], second_message["id"]}
    corrected = memories.correct(
        memory["id"], text="新约束", expected_version=1,
        operation_key="source-chain-v2", source_message_ids=source_ids,
        source_excerpt=second_message["content"],
    )
    forgotten = memories.forget(
        memory["id"], expected_version=corrected["version"],
        operation_key="source-chain-forget", source_message_ids=["forget-message"],
    )
    assert forgotten["status"] == "forgotten"
    assert {first_message["id"], second_message["id"], "forget-message"}.issubset(
        memories.suppressed_source_message_ids(space_id=space["id"])
    )


def test_continuous_context_change_pauses_instead_of_publishing_stale_answer(app_paths) -> None:
    _db, store, space, memories, _notes = _services(app_paths)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="给出当前结论", request_id="stale-final")
    claimed = store.claim_next_run()
    assert claimed

    class MovingProvider:
        calls = 0

        def turn(self, *, messages, tools, max_tokens):
            self.calls += 1
            memories.save_explicit(
                text=f"生成期间变化 {self.calls}", subject_key=f"moving_{self.calls}",
                kind="constraint", scope_kind="space", scope_id=space["id"],
                operation_key=f"moving-{self.calls}",
            )
            return ModelTurn(text=f"已知陈旧答案 {self.calls}", usage={"total_tokens": 10})

    provider = MovingProvider()
    graph = AssistantExecutionGraph(
        store=store, memories=memories,
        tools=SimpleNamespace(schemas=lambda: [], execute=None),
        provider_factory=lambda: provider, max_steps=4,
    )
    asyncio.run(graph.run(claimed))
    final = store.get_run(run["id"])
    thread_state = store.get_thread(thread["id"])
    assert final["status"] == "interrupted"
    assert final["last_error_code"] == "context_changed_retry_exhausted"
    assert all("已知陈旧答案" not in item["content"] for item in thread_state["messages"])


def test_background_daily_budget_wait_and_automatic_scope_are_bounded(app_paths) -> None:
    db, store, _space, _memories, _notes = _services(app_paths)
    budget = store.reserve_model_request(lane="background", request_limit=1)
    assert budget["requests_used"] == 1
    store.record_model_usage(
        lane="background", usage=None,
        outcome="response_usage_unavailable", latency_ms=12.5,
    )
    with pytest.raises(ModelBudgetWait):
        store.reserve_model_request(lane="background", request_limit=1)

    automatic = store.create_space(
        name="较大明确维护范围", video_ids=list(range(1, 22)), maintenance_mode="automatic"
    )
    assert len(automatic["video_ids"]) == 21
    sources = SimpleNamespace(visible_video_ids=lambda scope, order: [])
    wiki = WikiService(db=db, store=store, sources=sources)
    with pytest.raises(ValueError, match="invalid_maintenance_budget"):
        wiki.bootstrap_space(automatic["id"], limit=11, model_budget=30)

    with db.connect() as connection:
        job_id = store.enqueue_job(
            connection, kind="memory_extract", dedupe_key="budget-wait-job",
            payload={"thread_id": "unused", "message_ids": [], "memory_epoch": 0},
        )
    job = store.claim_job(owner="budget-test", allow_model_jobs=True)
    assert job and job["id"] == job_id
    store.defer_job_for_budget(job, message="每日额度已用完")
    waiting = next(item for item in store.list_jobs() if item["id"] == job_id)
    assert waiting["status"] == "budget_wait"
    assert waiting["attempt"] == 0
    assert waiting["last_error_code"] == "background_budget_wait"

    batch = wiki.bootstrap_space(automatic["id"], limit=1, model_budget=1)
    with db.connect() as connection:
        connection.execute(
            "UPDATE assistant_maintenance_batches SET calls_used=1 WHERE id=?",
            (batch["batch_id"],),
        )
        batch_job_id = store.enqueue_job(
            connection, kind="source_extract", dedupe_key="batch-budget-wait-job",
            payload={
                "video_id": 1, "revision": "0" * 64,
                "maintenance_batch_id": batch["batch_id"],
            },
        )
    batch_job = store.claim_job(owner="batch-budget-test", allow_model_jobs=True)
    assert batch_job and batch_job["id"] == batch_job_id
    store.defer_job_for_batch_budget(batch_job, message="本批额度已用完")
    paused = next(item for item in store.list_jobs() if item["id"] == batch_job_id)
    assert paused["status"] == "budget_wait"
    assert paused["last_error_code"] == "maintenance_budget_wait"
    continued = store.retry_job(batch_job_id)
    assert continued["status"] == "queued"
    assert continued["payload"]["maintenance_batch_id"] != batch["batch_id"]
    with db.connect() as connection:
        old_batch = connection.execute(
            "SELECT calls_used FROM assistant_maintenance_batches WHERE id=?",
            (batch["batch_id"],),
        ).fetchone()
        new_batch = connection.execute(
            "SELECT calls_used,model_limit FROM assistant_maintenance_batches WHERE id=?",
            (continued["payload"]["maintenance_batch_id"],),
        ).fetchone()
        usage = json.loads(connection.execute(
            "SELECT usage_json FROM assistant_model_budget_days "
            "WHERE lane='background'",
        ).fetchone()["usage_json"])
    assert old_batch["calls_used"] == 1
    assert new_batch["calls_used"] == 0 and new_batch["model_limit"] == 1
    assert usage["unknown_usage_responses"] == 1


def test_wait_age_promotion_is_recorded_without_extra_workers(app_paths) -> None:
    db, store, _space, _memories, _notes = _services(app_paths)
    with db.connect() as connection:
        job_id = store.enqueue_job(
            connection, kind="memory_extract", dedupe_key="aged-model-job",
            payload={"thread_id": "unused", "message_ids": [], "memory_epoch": 0},
        )
        connection.execute(
            "UPDATE assistant_jobs SET created_at=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(timespec="seconds"), job_id),
        )
    assert store.model_job_wait_exceeded(30)
    claimed = store.claim_job(
        owner="scheduler-test", allow_model_jobs=True, scheduler_reason="wait_age_promotion"
    )
    assert claimed and claimed["id"] == job_id
    with db.connect() as connection:
        event = connection.execute(
            "SELECT reason,queue_wait_seconds FROM assistant_scheduler_events WHERE job_id=?",
            (job_id,),
        ).fetchone()
    assert event["reason"] == "wait_age_promotion"
    assert event["queue_wait_seconds"] >= 30
    assert SCHEMA_VERSION == 25
