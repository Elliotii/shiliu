from __future__ import annotations

from test_assistant_context_c2 import c2
from test_assistant_context_c3 import c3, history, state_for, notes
from assistant_context_support import mixed_checkpoint

from assistant_offline_provider import offline_provider

import pytest
import asyncio
import json
import copy
from pathlib import Path
import threading
from datetime import datetime, timedelta, timezone

from shiliu.assistant.memory import MemoryService
from shiliu.assistant.runtime import AssistantExecutionGraph
from shiliu.assistant.provider import ModelTurn
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.task_notes import TaskNoteService

from shiliu.assistant.store import AssistantConflict
from shiliu.domain import PipelineError
from test_assistant_stage_c import _add_material, _services


def _message_id(store, space_id: int, text: str) -> str:
    thread = store.create_thread(space_id)
    run = store.create_run(thread["id"], text=text, request_id="d-save")
    return next(item["id"] for item in store.run_context(run["id"])["thread"]["messages"]
                if item["role"] == "user")


def _block(text: str) -> dict:
    return {"role": "analysis", "heading": "判断", "markdown": text, "source_refs": []}


def test_direct_save_update_and_revert(app_paths) -> None:
    _db, _artifacts, _sources, store, wiki = _services(app_paths)
    space = store.create_space(name="D", all_active=True)
    message_id = _message_id(store, space["id"], "保存这次分析；我的笔记是：先核对条件")
    first = wiki.save_discussion(space_id=space["id"], title="记忆比较", purpose="比较采用条件",
                                 blocks=[_block("条件未知时保留未知")], source_message_id=message_id,
                                 operation_key="d-one")
    assert first["blocks"][0]["assessment"] == "system_synthesis"
    assert wiki.save_discussion(space_id=space["id"], title="记忆比较", purpose="比较采用条件",
                                blocks=[_block("条件未知时保留未知")], source_message_id=message_id,
                                operation_key="d-one")["version"] == 1
    second = wiki.save_discussion(space_id=space["id"], title="记忆比较", purpose="比较采用条件",
                                  blocks=[{"role": "personal", "heading": "我的笔记", "markdown": "先核对条件",
                                           "user_quote": "先核对条件"}],
                                  expected_version=1, source_message_id=message_id, operation_key="d-two")
    assert second["version"] == 2 and len(second["blocks"]) == 2
    with pytest.raises(AssistantConflict, match="wiki_manual_conflict"):
        wiki.revise_derived_blocks(
            second["id"], space_id=space["id"], expected_version=2,
            summary="不应写入", edits=[{"block_id": second["blocks"][1]["stable_id"],
                                    "heading": "覆盖", "markdown": "覆盖人工笔记"}],
            operation_key="d-unsafe-repair",
        )
    with pytest.raises(AssistantConflict, match="wiki_version_conflict"):
        wiki.save_discussion(space_id=space["id"], title="记忆比较", purpose="比较采用条件",
                             blocks=[_block("旧版本")], expected_version=1,
                             source_message_id=message_id, operation_key="d-stale")
    reverted = wiki.revert(first["id"], target_version=1, expected_version=2, operation_key="d-revert")
    assert reverted["version"] == 3 and len(reverted["blocks"]) == 1


def test_multi_topic_partial_and_repeated_confirmation(app_paths) -> None:
    _db, _artifacts, _sources, store, wiki = _services(app_paths)
    space = store.create_space(name="D", all_active=True)
    message_id = _message_id(store, space["id"], "把讨论分成两个主题，确认后保存")
    topics = [
        {"title": "面试准备", "purpose": "准备面试", "blocks": [_block("按岗位核对问题")]},
        {"title": "拍摄参考", "purpose": "保留影像参考", "blocks": [_block("只作为作品参考")]},
    ]
    plan = wiki.propose_discussion(space_id=space["id"], topics=topics, omitted=["闲聊"],
                                   source_message_id=message_id, request_key="d-plan")
    assert plan["status"] == "pending"
    assert wiki.propose_discussion(space_id=space["id"], topics=topics, omitted=["闲聊"],
                                   source_message_id=message_id, request_key="d-plan")["id"] == plan["id"]
    revised = wiki.revise_discussion_plan(plan["id"], space_id=space["id"], expected_version=1,
                                          topics=[{**topics[0], "purpose": "准备可复用面试答案"}, topics[1]],
                                          omitted=["闲聊"], operation_key="d-revise")
    assert revised["version"] == 2 and revised["payload"]["topics"][0]["purpose"] == "准备可复用面试答案"
    with pytest.raises(AssistantConflict, match="knowledge_plan_version_conflict"):
        wiki.decide_discussion_plan(plan["id"], space_id=space["id"], expected_version=1,
                                    accept=True, operation_key="d-stale-confirm")
    result = wiki.decide_discussion_plan(plan["id"], space_id=space["id"], expected_version=2,
                                         accept=True, operation_key="d-confirm")
    assert result["status"] == "completed" and len(wiki.list_pages(space_id=space["id"])) == 2
    repeated = wiki.decide_discussion_plan(plan["id"], space_id=space["id"], expected_version=2,
                                           accept=True, operation_key="d-confirm-again")
    assert repeated["status"] == "completed" and len(wiki.list_pages(space_id=space["id"])) == 2

    another = wiki.propose_discussion(space_id=space["id"], topics=[
        {"title": "独立分析", "purpose": "保存判断", "blocks": [_block("可复用结论")]},
        {"title": "拍摄参考", "purpose": "检查版本冲突", "blocks": [_block("追加参考")]},
    ], omitted=[], source_message_id=message_id, request_key="d-partial")
    existing = next(page for page in wiki.list_pages(space_id=space["id"]) if page["title"] == "拍摄参考")
    wiki.edit_block(existing["id"], block_id=existing["blocks"][0]["stable_id"],
                    markdown="人工改过的参考", expected_version=existing["version"],
                    operation_key="d-manual")
    partial = wiki.decide_discussion_plan(another["id"], space_id=space["id"], expected_version=1,
                                          accept=True, operation_key="d-partial-confirm")
    assert partial["status"] == "partial"
    assert partial["results"]["0"]["status"] == "completed"
    assert partial["results"]["1"]["status"] == "failed"
    assert len(wiki.list_pages(space_id=space["id"])) == 3


def test_no_save_guard_and_independent_temporary_note(app_paths, monkeypatch) -> None:
    db, _artifacts, sources, store, wiki = _services(app_paths)
    space = store.create_space(name="D", all_active=True)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="不要保存这段分析，只回答", request_id="d-forbid")
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    denied = asyncio.run(registry.execute(
        name="knowledge_save_discussion", arguments={"topics": [{"title": "不应存在", "purpose": "测试",
                                                  "blocks": [_block("不入页")]}]}, call_id="d-deny",
        run_context=store.run_context(run["id"]),
    ))
    assert denied["error_code"] == "knowledge_save_forbidden"
    legacy_denied = asyncio.run(registry.execute(
        name="knowledge_organize", arguments={"topic": "不应存在", "source_refs": ["video:1:x"]},
        call_id="d-deny-legacy", run_context=store.run_context(run["id"]),
    ))
    assert legacy_denied["error_code"] == "knowledge_save_forbidden"
    assert wiki.list_pages(space_id=space["id"]) == []

    from shiliu.assistant.tools import _forbids_knowledge_save
    assert not _forbids_knowledge_save("分成两个主题，先给提案，不要保存个人记忆")
    assert not _forbids_knowledge_save("禁止保存个人 Memory，允许知识主题提案")
    assert not _forbids_knowledge_save("允许知识提案。个人 Memory 仍不要保存。")
    assert _forbids_knowledge_save("不要保存个人记忆，也不要保存这段分析")
    assert _forbids_knowledge_save("不要保存知识和个人记忆")
    assert _forbids_knowledge_save("不要保存个人记忆，也不要保存知识")

    joint = store.create_run(store.create_thread(space["id"])["id"],
                             text="不要保存知识和个人记忆，先只回答", request_id="d-joint-forbid")
    denied_outcome = asyncio.run(registry.execute(
        name="knowledge_save_discussion",
        arguments={"topics": [{"title": "不能出现的知识页", "purpose": "验证联合禁止",
                   "blocks": [_block("不得写入")]}]}, call_id="d-joint-outcome",
        run_context=store.run_context(joint["id"]),
    ))
    assert denied_outcome["error_code"] == "knowledge_save_forbidden"
    assert wiki.list_pages(space_id=space["id"]) == []
    assert wiki.list_discussion_plans(space_id=space["id"]) == []

    other = store.create_thread(space["id"])
    later = store.create_run(other["id"], text="保存这条个人安排：未来1天先准备面试", request_id="d-note")
    message_id = next(item["id"] for item in store.run_context(later["id"])["thread"]["messages"]
                      if item["role"] == "user")
    saved = wiki.save_discussion(
        space_id=space["id"], title="阶段安排", purpose="暂时安排",
        blocks=[{"role": "personal", "heading": "我的安排", "markdown": "未来1天先准备面试",
                 "user_quote": "未来1天先准备面试"}],
        source_message_id=message_id, operation_key="d-note-save",
    )
    assert len(saved["blocks"]) == 1
    assert saved["blocks"][0]["expires_at"]
    with db.connect() as connection:
        assert connection.execute("SELECT count(*) FROM assistant_memories").fetchone()[0] == 0
    monkeypatch.setattr("shiliu.assistant.wiki.utc_now", lambda: "2026-12-01T00:00:00+00:00")
    assert wiki.get_page(saved["id"], space_id=space["id"])["blocks"] == []


def test_personal_note_requires_traceable_user_quote(app_paths) -> None:
    _db, _artifacts, _sources, store, wiki = _services(app_paths)
    space = store.create_space(name="D", all_active=True)
    message_id = _message_id(store, space["id"], "请保存这份分析")
    with pytest.raises(ValueError, match="personal_quote_required"):
        wiki.save_discussion(
            space_id=space["id"], title="判断", purpose="模型分析",
            blocks=[{"role": "personal", "heading": "我的决定", "markdown": "我已决定采用甲"}],
            source_message_id=message_id, operation_key="d-fake-personal",
        )
    with pytest.raises(ValueError, match="personal_quote_required"):
        wiki.save_discussion(
            space_id=space["id"], title="判断", purpose="模型分析",
            blocks=[{"role": "personal", "heading": "我的决定", "markdown": "我已决定采用甲",
                     "user_quote": "我已经决定采用甲"}],
            source_message_id=message_id, operation_key="d-unrelated-quote",
        )


def test_analysis_memory_dependency_and_unanchored_personal_time(app_paths, monkeypatch) -> None:
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=994, folder_title="D material", history_policy="all")
    video_id = _add_material(db, artifacts, source_id, bvid="BV1D23456789",
                             title="独立材料", text="材料的条件差异保持独立")
    space = store.create_space(name="D", source_ids=[source_id])
    revision = sources.snapshots.capture(video_id).revision
    memories = MemoryService(db)
    memory = memories.save_explicit(text="我下周准备面试", subject_key="interview", kind="context",
                                    scope_kind="space", scope_id=space["id"], operation_key="d-background")
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="保存分析：根据我的面试安排，先练习条件比较",
                           request_id="d-analysis-memory")
    registry = AssistantToolRegistry(sources=sources, memories=memories, store=store, wiki=wiki)
    with db.connect() as connection:
        working = json.loads(connection.execute("SELECT working_state_json FROM assistant_runs WHERE id=?", (run["id"],)).fetchone()[0])
        working["model_delivered_materials"] = [{"source_ref": f"video:{video_id}:{revision}", "kind": "collection_read", "view": "summary", "projection": "正文"}]
        connection.execute("UPDATE assistant_runs SET working_state_json=? WHERE id=?", (json.dumps(working), run["id"]))
    stored = asyncio.run(registry.execute(
        name="knowledge_save_discussion", arguments={"topics": [{
            "title": "面试材料", "purpose": "准备说明",
            "blocks": [{"role": "source", "heading": "独立来源", "markdown": "材料的条件差异保持独立",
                        "source_refs": [f"video:{video_id}:{revision}"]},
                       {**_block("根据近期面试安排先练习条件比较"),
                        "memory_id": memory["id"], "memory_version": memory["version"]}],
        }]}, call_id="d-analysis-memory", run_context=store.run_context(run["id"]),
    ))
    assert stored["status"] == "ok"
    page = wiki.get_page(stored["items"][0]["results"]["0"]["page_id"], space_id=space["id"])
    assert [block["assessment"] for block in page["blocks"]] == ["source_reported", "system_synthesis"]
    assert wiki.personal_dependency_refs(page["id"], space_id=space["id"]) == [
        f"memory:{memory['id']}:{memory['version']}"]
    memories.correct(memory["id"], text="我暂不准备面试", expected_version=memory["version"],
                     operation_key="d-background-correct")
    visible = wiki.get_page(page["id"], space_id=space["id"])
    assert len(visible["blocks"]) == 1 and visible["blocks"][0]["markdown"] == "材料的条件差异保持独立"

    uncertain_id = _message_id(store, space["id"], "保存我的安排：下个月再考虑面试")
    uncertain = wiki.save_discussion(
        space_id=space["id"], title="下月安排", purpose="保留原话",
        blocks=[{"role": "personal", "heading": "我的安排", "markdown": "下个月再考虑面试",
                 "user_quote": "下个月再考虑面试"}],
        source_message_id=uncertain_id, operation_key="d-uncertain-time",
    )
    assert uncertain["blocks"][0]["historical_statement"] is True
    assert "需核对" in uncertain["blocks"][0]["validity_note"]

    delayed_id = _message_id(store, space["id"], "保存我的安排：未来1天先准备面试")
    with db.connect() as connection:
        connection.execute("UPDATE assistant_messages SET created_at=? WHERE id=?",
                           ((datetime.now(timezone.utc) - timedelta(days=10)).isoformat(), delayed_id))
    delayed = wiki.save_discussion(
        space_id=space["id"], title="旧安排", purpose="保存原话",
        blocks=[{"role": "personal", "heading": "我的安排", "markdown": "未来1天先准备面试",
                 "user_quote": "未来1天先准备面试"}],
        source_message_id=delayed_id, operation_key="d-delayed-note",
    )
    assert delayed["blocks"] == []
    assert wiki.get_page(delayed["id"], space_id=space["id"], include_hidden=True)["blocks"][0]["expires_at"]


@pytest.mark.parametrize("change", ["revise", "reject"])
def test_plan_claim_race_cannot_commit_old_version(app_paths, monkeypatch, change) -> None:
    _db, _artifacts, _sources, store, wiki = _services(app_paths)
    space = store.create_space(name="D", all_active=True)
    message_id = _message_id(store, space["id"], "分成两个主题后保存")
    topics = [{"title": "甲", "purpose": "甲用途", "blocks": [_block("甲材料")]},
              {"title": "乙", "purpose": "乙用途", "blocks": [_block("乙材料")]}]
    plan = wiki.propose_discussion(space_id=space["id"], topics=topics, omitted=[],
                                   source_message_id=message_id, request_key=f"race-{change}")
    reached, release = threading.Event(), threading.Event()
    original_get_space = store.get_space

    def intercepted(space_id):
        if threading.current_thread().name == "old-confirm":
            reached.set()
            assert release.wait(5)
        return original_get_space(space_id)

    monkeypatch.setattr(store, "get_space", intercepted)
    errors = []

    def old_confirm():
        try:
            wiki.decide_discussion_plan(plan["id"], space_id=space["id"], expected_version=1,
                                        accept=True, operation_key="race-old")
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=old_confirm, name="old-confirm")
    worker.start()
    assert reached.wait(5)
    if change == "revise":
        wiki.revise_discussion_plan(plan["id"], space_id=space["id"], expected_version=1,
                                    topics=[{**topics[0], "purpose": "新版用途"}, topics[1]], omitted=[],
                                    operation_key="race-revise")
    else:
        wiki.decide_discussion_plan(plan["id"], space_id=space["id"], expected_version=1,
                                    accept=False, operation_key="race-reject")
    release.set(); worker.join(5)
    assert len(errors) == 1 and isinstance(errors[0], AssistantConflict)
    assert wiki.list_pages(space_id=space["id"]) == []


def test_page_write_requires_claimed_plan_in_same_transaction(app_paths) -> None:
    _db, _artifacts, _sources, store, wiki = _services(app_paths)
    space = store.create_space(name="D", all_active=True)
    message_id = _message_id(store, space["id"], "分成两个主题")
    plan = wiki.propose_discussion(space_id=space["id"], topics=[
        {"title": "甲", "purpose": "甲用途", "blocks": [_block("甲")]},
        {"title": "乙", "purpose": "乙用途", "blocks": [_block("乙")]},
    ], omitted=[], source_message_id=message_id, request_key="unclaimed-plan")
    with pytest.raises(AssistantConflict, match="knowledge_plan_authorization_changed"):
        wiki.save_discussion(space_id=space["id"], title="甲", purpose="甲用途", blocks=[_block("甲")],
                             source_message_id=message_id, operation_key="unclaimed-write",
                             authorized_plan_id=plan["id"], authorized_plan_version=1)
    assert wiki.list_pages(space_id=space["id"]) == []


def test_personal_save_forbidden_and_confirmation_thread_guard(app_paths) -> None:
    db, _artifacts, sources, store, wiki = _services(app_paths)
    space = store.create_space(name="D", all_active=True)
    seed_id = _message_id(store, space["id"], "保存这个单主题")
    page = wiki.save_discussion(space_id=space["id"], title="已有页", purpose="用来验证",
                                blocks=[_block("独立内容")], source_message_id=seed_id,
                                operation_key="guard-seed")
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)

    def call(text, name, arguments, call_id, thread_id=None):
        thread = {"id": thread_id} if thread_id else store.create_thread(space["id"])
        run = store.create_run(thread["id"], text=text, request_id=call_id)
        return asyncio.run(registry.execute(name=name, arguments=arguments, call_id=call_id,
                                            run_context=store.run_context(run["id"])))

    denied = call("不要保存我的笔记：先核对条件", "knowledge_save_personal",
                  {"page_id": page["id"], "text": "先核对条件", "expected_page_version": 1}, "personal-deny")
    assert denied["error_code"] == "knowledge_save_forbidden"
    plan_id = _message_id(store, space["id"], "分成两个主题")
    plan = wiki.propose_discussion(space_id=space["id"], topics=[
        {"title": "甲", "purpose": "甲用途", "blocks": [_block("甲")]},
        {"title": "乙", "purpose": "乙用途", "blocks": [_block("乙")]},
    ], omitted=[], source_message_id=plan_id, request_key="guard-plan")
    wrong = call("确认这个提案", "knowledge_confirm", {"plan_id": plan["id"], "expected_version": 1,
                                                      "accept": True}, "foreign-confirm")
    assert wrong["error_code"] == "knowledge_plan_request_mismatch"
    assert len(wiki.list_pages(space_id=space["id"])) == 1
    with db.connect() as connection:
        plan_thread_id = connection.execute('SELECT thread_id FROM assistant_messages WHERE id=?', (plan_id,)).fetchone()[0]
        connection.execute("UPDATE assistant_runs SET status='completed' WHERE thread_id=? AND status='queued'", (plan_thread_id,))
    accepted = call("确认这个提案", "knowledge_confirm", {"plan_id": plan["id"],
                        "expected_version": 1, "accept": True}, "right-confirm", thread_id=plan_thread_id)
    assert accepted["status"] == "ok"
    assert len(wiki.list_pages(space_id=space["id"])) == 3


@pytest.mark.parametrize("prompt_text,tool_count,tool_base,expect_hint", [
    ("先完整读完这两份正文，再分成两个主题给提案", 8, 0, True),
    ("继续回读两个主题的疑点，再给提案", 9, 8, False),
    ("把已读材料分成两个主题，先整理提案再保存", 8, 0, True),
])
def test_mixed_run_keeps_read_tools_at_provider(
    app_paths, prompt_text: str, tool_count: int, tool_base: int, expect_hint: bool,
) -> None:
    db, _artifacts, sources, store, wiki = _services(app_paths)
    space = store.create_space(name="D", all_active=True)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text=prompt_text, request_id="d-mixed")
    claimed = store.claim_next_run()
    assert claimed and claimed["id"] == run["id"]
    for ordinal in range(1, tool_count + 1):
        call_id = f"search-{ordinal}"
        store.begin_tool_call(run["id"], ordinal=ordinal, call_id=call_id,
                              name="collection_read", arguments={"source_ref": "video:1"})
        store.finish_tool_call(run["id"], call_id=call_id, result={
            "call_id": call_id, "status": "ok",
            "summary": "候选，正文尚有未读部分" if "完整读完" in prompt_text else "已读材料候选",
            "source_refs": ["video:1:revision-a", "video:2:revision-b"], "items": [],
            "next_cursor": "more" if "完整读完" in prompt_text else None,
        })
    class Provider:
        def __init__(self) -> None:
            self.tools = []
            self.messages = []

        def turn(self, *, messages, tools, max_tokens):
            self.messages = messages
            self.tools = tools
            return ModelTurn(text="待继续处理", usage={"prompt_tokens": 10, "completion_tokens": 5})

    provider = Provider()
    graph = AssistantExecutionGraph(store=store, memories=MemoryService(db),
                                    tools=AssistantToolRegistry(sources=sources, memories=MemoryService(db),
                                                                store=store, wiki=wiki),
                                    provider_factory=lambda: offline_provider(provider))
    state = {
        "run_id": run["id"], "epoch": claimed["run_epoch"], "step_count": 0,
        "tool_count": tool_count, "tool_base": tool_base, "step_base": 0,
        "usage": {}, "route": "model", "turn": None, "memory_restart_count": 0,
        "context_metadata": {},
    }
    result = asyncio.run(graph._model(state))
    assert result["route"] == "final"
    offered = {item["function"]["name"] for item in provider.tools}
    assert {"collection_read", "run_read_result", "knowledge_propose"} <= offered
    prompt = str(provider.messages[0]["content"])
    assert "当前多主题任务本段约剩" not in prompt
    assert "及时调用 knowledge_propose" not in prompt


def test_malformed_tool_arguments_get_one_bounded_retry(app_paths) -> None:
    db, _artifacts, sources, store, wiki = _services(app_paths)
    space = store.create_space(name="D", all_active=True)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="分成两个主题给提案", request_id="d-json-retry")
    claimed = store.claim_next_run()

    class Provider:
        calls = 0

        def turn(self, *, messages, tools, max_tokens):
            self.calls += 1
            if self.calls == 1:
                raise PipelineError("bad json", code="tool_arguments_invalid", retryable=False)
            assert "工具调用必须是完整 JSON 对象" in messages[-1]["content"]
            return ModelTurn(text="请查看提案", usage={"prompt_tokens": 10, "completion_tokens": 5})

    provider = Provider()
    graph = AssistantExecutionGraph(store=store, memories=MemoryService(db),
                                    tools=AssistantToolRegistry(sources=sources, memories=MemoryService(db),
                                                                store=store, wiki=wiki),
                                    provider_factory=lambda: offline_provider(provider))
    state = {"run_id": run["id"], "epoch": claimed["run_epoch"], "step_count": 0,
             "tool_count": 0, "tool_base": 0, "step_base": 0, "usage": {},
             "route": "model", "turn": None, "memory_restart_count": 0,
             "context_metadata": {}}
    result = asyncio.run(graph._model(state))
    assert result["route"] == "final"
    assert provider.calls == 2


def test_two_pages_proposal_phrase_is_explicit_request(app_paths) -> None:
    db, _artifacts, sources, store, wiki = _services(app_paths)
    space = store.create_space(name="D", all_active=True)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="请把上面两页作为待确认提案，先别写页面，不要保存个人记忆",
                           request_id="d-two-pages")
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    result = asyncio.run(registry.execute(
        name="knowledge_propose", arguments={"topics": [
            {"title": "面试题卡", "purpose": "面试复习", "blocks": [_block("条件和依据")]},
            {"title": "旅行练习卡", "purpose": "动作练习", "blocks": [_block("动作和边界")]},
        ], "omitted": []}, call_id="d-two-pages",
        run_context=store.run_context(run["id"]),
    ))
    assert result["status"] == "ok"
    assert wiki.list_pages(space_id=space["id"]) == []


def test_knowledge_page_read_is_bounded_and_versioned(app_paths) -> None:
    db, _artifacts, sources, store, wiki = _services(app_paths)
    space = store.create_space(name="D page read", all_active=True)
    message_id = _message_id(store, space["id"], "保存面试比较")
    page = wiki.save_discussion(
        space_id=space["id"], title="面试比较", purpose="一次读小页",
        blocks=[{"role": "analysis", "heading": f"条件 {i}",
                 "markdown": f"条件 {i} 的依据"} for i in range(4)],
        source_message_id=message_id, operation_key="d-read-page",
    )
    run = store.create_run(store.create_thread(space["id"])["id"],
                           text="比较这页的四项条件", request_id="d-page-read")
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)

    def read(args: dict, call_id: str) -> dict:
        return asyncio.run(registry.execute(
            name="knowledge_read", arguments={"page_id": page["id"], **args},
            call_id=call_id, run_context=store.run_context(run["id"]),
        ))

    small = read({"mode": "page"}, "d-small")
    assert small["status"] == "ok" and small["next_cursor"] is None
    assert small["coverage"]["complete"] is True
    assert small["coverage"]["returned_blocks"] == 4
    assert len(small["coverage"]["returned_block_ids"]) == 4
    assert small["items"][0]["version"] == page["version"]
    assert all(block["assessment"] == "system_synthesis" for block in small["items"][0]["blocks"])

    large = wiki.save_discussion(
        space_id=space["id"], title="大页", purpose="有界续读",
        blocks=[{"role": "analysis", "heading": f"长块 {i}",
                 "markdown": f"内容 {i} " + "甲" * 2500} for i in range(5)],
        source_message_id=message_id, operation_key="d-read-large",
    )
    first = asyncio.run(registry.execute(
        name="knowledge_read", arguments={"page_id": large["id"], "mode": "page"},
        call_id="d-large-first", run_context=store.run_context(run["id"]),
    ))
    assert first["status"] == "ok" and first["truncated"] and first["next_cursor"]
    second = asyncio.run(registry.execute(
        name="knowledge_read", arguments={"page_id": large["id"], "mode": "page",
                                          "cursor": first["next_cursor"]},
        call_id="d-large-second", run_context=store.run_context(run["id"]),
    ))
    assert second["status"] == "ok"
    assert set(first["coverage"]["returned_block_ids"]).isdisjoint(second["coverage"]["returned_block_ids"])
    wiki.edit_block(large["id"], block_id=large["blocks"][0]["stable_id"],
                    markdown="版本已更新", expected_version=large["version"], operation_key="d-page-edit")
    stale = asyncio.run(registry.execute(
        name="knowledge_read", arguments={"page_id": large["id"], "mode": "page",
                                          "cursor": first["next_cursor"]},
        call_id="d-large-stale", run_context=store.run_context(run["id"]),
    ))
    assert stale["error_code"] == "knowledge_cursor_version_changed"


def test_task_note_retains_short_read_and_invalidates_edited_page(c3):
    from test_assistant_context_c2 import execute, batch
    run, state, _ = history(c3)
    user = next(m for m in c3.store.get_thread(c3.thread['id'])['messages'] if m['role']=='user')
    page = c3.wiki.save_discussion(space_id=c3.space['id'],title='页内具体判断',purpose='核对',
        source_message_id=user['id'],operation_key='short-read',blocks=[{'role':'analysis','heading':'具体判断','markdown':'空镜、跟随、细节动作'}])
    result = execute(c3,run,'knowledge_read',{'page_id':page['id'],'page_version':page['version'],'mode':'page'},call_id='wiki')
    batch(c3,run,[('wiki','knowledge_read',{'page_id':page['id']},result)])
    prepared = c3.composer.prepare(run['id'],provider=c3.provider)
    c3.composer.persist(prepared)
    c3.store.confirm_model_delivery(run['id'],epoch=run['run_epoch'],spans=[],message_ids=prepared.message_ids,context_revision=prepared.state['revision'])
    c3.provider.summary = '页内具体判断：空镜、跟随、细节动作。'
    candidate = asyncio.run(c3.graph._prepare_dispatch(state,provider=c3.provider,explicit_overflow=True))
    assert '空镜、跟随、细节动作' in c3.graph.task_notes.render(candidate.checkpoint)
    assert any(m['source_ref'].startswith('wiki:') for m in candidate.checkpoint['checkpoint']['material_index'])
    c3.wiki.edit_block(page['id'],block_id=page['blocks'][0]['stable_id'],markdown='新版判断',expected_version=page['version'],operation_key='edit-note-page')
    assert c3.graph.task_notes.checkpoint_for_context(c3.thread['id'],space_id=c3.space['id'],scope_version=1,identity=candidate.state['identity']) is None


def test_real_ue_proposal_requires_sources_before_confirmation(app_paths) -> None:
    fixture = json.loads((Path(__file__).resolve().parent / "fixtures" /
                          "ue_r34_proposal_v1.json").read_text())
    original = fixture["proposal_arguments"]["topics"]
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=995, folder_title="U-E isolated", history_policy="all")
    video_ids = [
        _add_material(db, artifacts, source_id, bvid="BV1UE0000001",
                      title="Agent 长期记忆怎么做才安全？先别急着总结", text="整合不默认"),
        _add_material(db, artifacts, source_id, bvid="BV1UE0000002",
                      title="出游拍出电影感，一台运动相机就够了", text="空镜与人物跟随"),
    ]
    refs = [f"video:{video_id}:{sources.snapshots.capture(video_id).revision}"
            for video_id in video_ids]
    space = store.create_space(name="U-E isolated", source_ids=[source_id])
    message_id = _message_id(store, space["id"], fixture["question"])

    with pytest.raises(ValueError, match=r"topic\[1\]\.block\[1\].*source_block_requires_source"):
        wiki.propose_discussion(space_id=space["id"], topics=copy.deepcopy(original),
                                omitted=[], source_message_id=message_id,
                                request_key="ue-fixed-invalid")
    assert wiki.list_discussion_plans(space_id=space["id"]) == []

    # Copy the already persisted v1 shape into this disposable database so
    # the old pending state gets the same pre-confirmation protection.
    plan_id = "akplan_ue_fixed_v1"
    payload = {"topics": [{**topic, "source_refs": [], "page_id": None,
                           "expected_version": None} for topic in copy.deepcopy(original)],
               "omitted": []}
    now = datetime.now(timezone.utc).isoformat()
    with db.connect() as connection:
        connection.execute(
            """INSERT INTO assistant_knowledge_plans
            (id,principal_id,space_id,version,scope_version,source_message_id,
             payload_json,results_json,status,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,'{}','pending',?,?)""",
            (plan_id, "local_operator", space["id"], 1, space["scope_version"],
             message_id, json.dumps(payload, ensure_ascii=False), now, now),
        )
    shown = next(plan for plan in wiki.list_discussion_plans(space_id=space["id"])
                 if plan["id"] == plan_id)
    assert shown["confirmable"] is False
    assert len([issue for issue in shown["validation_issues"]
                if "source_block_requires_source" in issue]) == 6
    with pytest.raises(AssistantConflict, match="knowledge_plan_not_confirmable"):
        wiki.decide_discussion_plan(plan_id, space_id=space["id"], expected_version=1,
                                    accept=True, operation_key="ue-invalid-confirm")
    assert wiki.list_pages(space_id=space["id"]) == []
    with pytest.raises(ValueError, match=r"topic\[1\]\.block\[1\].*source_block_requires_source"):
        wiki.revise_discussion_plan(plan_id, space_id=space["id"], expected_version=1,
                                    topics=copy.deepcopy(original), omitted=[],
                                    operation_key="ue-invalid-revise")

    repaired = copy.deepcopy(original)
    for index, topic in enumerate(repaired):
        for block in topic["blocks"]:
            if block["role"] == "source":
                block["source_refs"] = [refs[index]]
            else:
                assert block.get("source_refs") in (None, [])
    revised = wiki.revise_discussion_plan(
        plan_id, space_id=space["id"], expected_version=1, topics=repaired,
        omitted=[], operation_key="ue-fixed-revise",
    )
    assert revised["version"] == 2 and revised["confirmable"] is True
    completed = wiki.decide_discussion_plan(
        plan_id, space_id=space["id"], expected_version=2, accept=True,
        operation_key="ue-fixed-confirm",
    )
    assert completed["status"] == "completed"
    pages = wiki.list_pages(space_id=space["id"])
    assert len(pages) == 2
    for index, topic in enumerate(repaired):
        page = next(page for page in pages if page["title"] == topic["title"])
        assert sum(block["assessment"] == "source_reported" for block in page["blocks"]) == sum(
            block["role"] == "source" for block in topic["blocks"])
        assert all(block["source_refs"] == [] for block in page["blocks"]
                   if block["assessment"] == "system_synthesis")
