from __future__ import annotations

import pytest
import asyncio
import threading
from datetime import datetime, timedelta, timezone

from shiliu.assistant.memory import MemoryService
from shiliu.assistant.runtime import AssistantExecutionGraph
from shiliu.assistant.provider import ModelTurn
from shiliu.assistant.tools import AssistantToolRegistry

from shiliu.assistant.store import AssistantConflict
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
        name="knowledge_save_outcome", arguments={"title": "不应存在", "purpose": "测试",
                                                  "blocks": [_block("不入页")]}, call_id="d-deny",
        run_context=store.run_context(run["id"]),
    ))
    assert denied["error_code"] == "knowledge_save_forbidden"
    legacy_denied = asyncio.run(registry.execute(
        name="knowledge_organize", arguments={"topic": "不应存在", "source_refs": ["video:1:x"]},
        call_id="d-deny-legacy", run_context=store.run_context(run["id"]),
    ))
    assert legacy_denied["error_code"] == "knowledge_save_forbidden"
    assert wiki.list_pages(space_id=space["id"]) == []

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


def test_model_cannot_invent_personal_note(app_paths) -> None:
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
                     "user_quote": "保存这份分析"}],
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
    stored = asyncio.run(registry.execute(
        name="knowledge_save_outcome", arguments={
            "title": "面试材料", "purpose": "准备说明",
            "blocks": [{"role": "source", "heading": "独立来源", "markdown": "材料的条件差异保持独立",
                        "source_refs": [f"video:{video_id}:{revision}"]},
                       {**_block("根据近期面试安排先练习条件比较"),
                        "memory_id": memory["id"], "memory_version": memory["version"]}],
        }, call_id="d-analysis-memory", run_context=store.run_context(run["id"]),
    ))
    assert stored["status"] == "ok"
    page = wiki.get_page(stored["items"][0]["page_id"], space_id=space["id"])
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


def test_negative_personal_and_confirmation_tool_guards(app_paths) -> None:
    db, _artifacts, sources, store, wiki = _services(app_paths)
    space = store.create_space(name="D", all_active=True)
    seed_id = _message_id(store, space["id"], "保存这个单主题")
    page = wiki.save_discussion(space_id=space["id"], title="已有页", purpose="用来验证",
                                blocks=[_block("独立内容")], source_message_id=seed_id,
                                operation_key="guard-seed")
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)

    def call(text, name, arguments, call_id):
        thread = store.create_thread(space["id"])
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
    for prompt in ("不要确认这个提案", "拒绝这个提案"):
        wrong = call(prompt, "knowledge_confirm", {"plan_id": plan["id"], "expected_version": 1,
                                                  "accept": True}, f"wrong-{prompt}")
        assert wrong["status"] != "ok"
    assert len(wiki.list_pages(space_id=space["id"])) == 1
    accepted = call("确认这个提案", "knowledge_confirm", {"plan_id": plan["id"],
                                                   "expected_version": 1, "accept": True}, "right-confirm")
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
                                    provider_factory=lambda: provider)
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
    if expect_hint:
        assert "及时调用 knowledge_propose" in prompt
        assert "先使用现有读取工具" in prompt
    else:
        assert "当前多主题任务本段约剩" not in prompt
