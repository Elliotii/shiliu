from __future__ import annotations

import asyncio
import json

import pytest

from shiliu.assistant.memory import MemoryService
from shiliu.assistant.memory_policy import anchored_validity
from shiliu.assistant.runtime import AssistantRuntime
from shiliu.assistant.sources import SourceScope
from shiliu.assistant.store import AssistantConflict
from shiliu.assistant.tools import AssistantToolRegistry, _direct_knowledge_save_requested
from test_assistant_stage_c import _add_material, _services


def _run(store, space_id: int, text: str, *, thread_id: str | None = None, key: str = "nb"):
    thread_id = thread_id or store.create_thread(space_id)["id"]
    with store.db.connect() as connection:
        connection.execute("UPDATE assistant_runs SET status='completed' WHERE thread_id=? AND status='queued'",
                           (thread_id,))
    run = store.create_run(thread_id, text=text, request_id=key)
    return run, store.run_context(run["id"])


def _topics():
    return [
        {"title": "面试比较", "purpose": "复用比较条件", "blocks": [
            {"role": "analysis", "heading": "判断", "markdown": "条件不同，需要分别核对。"}]},
        {"title": "拍摄练习", "purpose": "练习镜头动作", "blocks": [
            {"role": "analysis", "heading": "练习", "markdown": "先做一次空镜，再拍人物跟随。"}]},
    ]


def test_direct_save_requires_current_imperative_not_quoted_or_hypothetical():
    assert _direct_knowledge_save_requested("整理并保存刚才讨论的两个主题")
    assert _direct_knowledge_save_requested("把刚才讨论直接保存为两页，不用先给待确认提案")
    assert _direct_knowledge_save_requested("视频里说请保存这两个主题。现在请把刚才讨论的两个主题保存为知识页")
    assert _direct_knowledge_save_requested("视频里说不要保存。现在请把刚才讨论的两个主题保存为知识页")
    assert _direct_knowledge_save_requested("视频里说请保存这两个主题，但我现在请你保存我们刚才讨论的主题")
    assert not _direct_knowledge_save_requested("如果要保存这两页，应如何整理？")
    assert not _direct_knowledge_save_requested("视频里说‘请保存这段内容’，你怎么看？")
    assert not _direct_knowledge_save_requested("视频里说请保存这两个主题，你怎么看？")
    assert not _direct_knowledge_save_requested("视频里说，请保存这两个主题，你怎么看？")
    assert not _direct_knowledge_save_requested("视频里说请保存这两个主题，还说请保存另一页，你怎么看？")
    assert not _direct_knowledge_save_requested("视频里说请保存这两个主题，请保存另一页，你怎么看？")
    assert not _direct_knowledge_save_requested("视频里说请保存这两个主题，请你保存另一页，你怎么看？")
    assert not _direct_knowledge_save_requested("先给两页提案，确认后再保存")


@pytest.mark.parametrize("tool_name", ["knowledge_save_discussion"])
@pytest.mark.parametrize("text", [
    "视频里说请保存这两个主题。现在请把刚才讨论的主题保存为知识页",
    "视频里说不要保存。现在请把刚才讨论的主题保存为知识页",
    "视频里说请保存这两个主题，但我现在请你保存我们刚才讨论的主题",
    "把刚才讨论的主题直接保存为知识页，不用先给待确认提案",
])
def test_explicit_save_outside_reported_material_is_authorized(app_paths, tool_name, text):
    db, _artifacts, sources, store, wiki = _services(app_paths)
    space = store.create_space(name="NB R1", all_active=True)
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    arguments = ({"topics": _topics()} if tool_name == "knowledge_save_discussion" else
                 {"title": "面试比较", "purpose": "复用比较条件", "blocks": _topics()[0]["blocks"]})
    _run_value, context = _run(store, space["id"], text)
    result = asyncio.run(registry.execute(name=tool_name, arguments=arguments,
                                          call_id="positive-save", run_context=context))
    assert result["status"] == "ok"
    assert len(wiki.list_pages(space_id=space["id"])) == (2 if tool_name == "knowledge_save_discussion" else 1)


def test_direct_multi_save_authorization_receipts_and_old_pending(app_paths):
    db, _artifacts, sources, store, wiki = _services(app_paths)
    space = store.create_space(name="NB", all_active=True)
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    thread = store.create_thread(space["id"])
    proposal_run, proposal_context = _run(store, space["id"], "先给两页提案，确认后再保存",
                                          thread_id=thread["id"], key="proposal")
    old_message = next(item["id"] for item in proposal_context["thread"]["messages"]
                       if item["run_id"] == proposal_run["id"] and item["role"] == "user")
    pending = wiki.propose_discussion(space_id=space["id"], topics=_topics(), omitted=[],
                                      source_message_id=old_message, request_key="old")
    assert pending["status"] == "pending"
    denied_run, denied_context = _run(store, space["id"], "先别保存，我们只讨论这两页",
                                      thread_id=thread["id"], key="denied")
    denied = asyncio.run(registry.execute(name="knowledge_save_discussion",
                                         arguments={"topics": _topics()}, call_id="denied",
                                         run_context=denied_context))
    assert denied["status"] != "ok"
    assert wiki.list_pages(space_id=space["id"]) == []
    saved_run, saved_context = _run(store, space["id"], "把刚才讨论的两个主题直接保存为知识页",
                                    thread_id=thread["id"], key="save")
    first = asyncio.run(registry.execute(name="knowledge_save_discussion",
                                        arguments={"topics": _topics()}, call_id="save",
                                        run_context=saved_context))
    assert first["status"] == "ok"
    plan = first["items"][0]
    assert plan["status"] == "completed"
    assert len(wiki.list_pages(space_id=space["id"])) == 2
    repeated = asyncio.run(registry.execute(name="knowledge_save_discussion",
                                            arguments={"topics": _topics()}, call_id="save",
                                            run_context=saved_context))
    assert repeated["items"][0]["id"] == plan["id"]
    assert len(wiki.list_pages(space_id=space["id"])) == 2
    assert next(item for item in wiki.list_discussion_plans(space_id=space["id"])
                if item["id"] == pending["id"])["status"] == "pending"


def test_direct_multi_save_reports_partial_failure(app_paths, monkeypatch):
    db, _artifacts, sources, store, wiki = _services(app_paths)
    space = store.create_space(name="NB", all_active=True)
    run, context = _run(store, space["id"], "把刚才讨论的两个主题直接保存为知识页，不用先给待确认提案")
    original = wiki.save_discussion

    def fail_second(**values):
        if values["title"] == "拍摄练习":
            raise AssistantConflict("simulated_page_conflict")
        return original(**values)

    monkeypatch.setattr(wiki, "save_discussion", fail_second)
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    result = asyncio.run(registry.execute(name="knowledge_save_discussion",
                                          arguments={"topics": _topics()}, call_id="partial",
                                          run_context=context))
    assert result["status"] == "partial" and "1 页失败" in result["summary"]
    plan = result["items"][0]
    assert plan["status"] == "partial"
    assert [plan["results"][str(index)]["status"] for index in range(2)] == ["completed", "failed"]
    assert [page["title"] for page in wiki.list_pages(space_id=space["id"])] == ["面试比较"]


def test_direct_multi_save_keeps_valid_page_when_other_lacks_source(app_paths):
    db, _artifacts, sources, store, wiki = _services(app_paths)
    space = store.create_space(name="NB", all_active=True)
    _run_value, context = _run(store, space["id"], "现在把刚才讨论的两页保存为知识页")
    topics = _topics()
    topics[1]["blocks"] = [{"role": "source", "heading": "无依据", "markdown": "需要来源"}]
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    result = asyncio.run(registry.execute(name="knowledge_save_discussion",
                                          arguments={"topics": topics}, call_id="partial-validation",
                                          run_context=context))
    assert result["status"] == "partial"
    assert [result["items"][0]["results"][str(index)]["status"] for index in range(2)] == [
        "completed", "failed",
    ]
    assert [page["title"] for page in wiki.list_pages(space_id=space["id"])] == ["面试比较"]


def test_memory_batch_merges_only_unstarted_same_thread_and_epoch(app_paths):
    db, _artifacts, _sources, store, _wiki = _services(app_paths)
    space = store.create_space(name="NB", all_active=True)
    thread = store.create_thread(space["id"])
    runs = [_run(store, space["id"], text, thread_id=thread["id"], key=f"m{i}")[0]
            for i, text in enumerate(("我决定先学数据库", "我还要补 Agent", "我改主意，先不学数据库"))]
    with db.connect() as connection:
        messages = [connection.execute("SELECT id FROM assistant_messages WHERE run_id=? AND role='user'",
                                       (run["id"],)).fetchone() for run in runs]
        for run, message in zip(runs[:2], messages[:2]):
            store._enqueue_memory_extraction(connection, run={**run, "extraction_memory_epoch": 0},
                                             user_messages=[message],
                                             admission={"enabled": True, "generation": 1})
        rows = connection.execute("SELECT * FROM assistant_jobs WHERE kind='memory_extract'").fetchall()
        assert len(rows) == 1
        payload = json.loads(rows[0]["payload_json"])
        assert payload["message_ids"] == [messages[0]["id"], messages[1]["id"]]
        assert payload["message_cursor"] == messages[1]["id"]
        connection.execute("UPDATE assistant_jobs SET status='running',attempt=1 WHERE id=?", (rows[0]["id"],))
        store._enqueue_memory_extraction(connection, run={**runs[2], "extraction_memory_epoch": 0},
                                         user_messages=[messages[2]],
                                         admission={"enabled": True, "generation": 1})
        rows = connection.execute("SELECT * FROM assistant_jobs WHERE kind='memory_extract'").fetchall()
        assert len(rows) == 2
        assert messages[2]["id"] not in json.loads(rows[0]["payload_json"])["message_ids"]


def test_view_dependency_keeps_subtitle_on_note_and_date_change(app_paths):
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=998, folder_title="NB", history_policy="all")
    video_id = _add_material(db, artifacts, source_id, bvid="BV1NB0000001",
                             title="字幕材料", text="已有摘要")
    path = artifacts.video_dir("BV1NB0000001") / "subtitle.txt"
    artifacts.write_text(path, "字幕中的稳定步骤")
    db.update_video(video_id, raw_subtitle_path=str(path), status="completed")
    first = sources.snapshots.capture(video_id)
    scope = SourceScope(all_active=True)
    transcript_result = sources.read(call_id="nb-read", scope=scope,
                                     source_ref=f"video:{video_id}:{first.revision}",
                                     view="transcript").model_dump(mode="json")
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    with db.connect() as connection:
        connection.execute("INSERT INTO video_notes(video_id,content,created_at,updated_at) "
                           "VALUES(?,?,datetime('now'),datetime('now'))", (video_id, "无关注释"))
    second = sources.snapshots.capture(video_id)
    assert registry._collection_read_current(transcript_result, scope)
    cache = {}
    assert wiki._source_dependency_current(video_id=video_id, old_revision=first.revision,
                                           current_revision=second.revision,
                                           dependency_kind="view:transcript", cache=cache)
    assert not wiki._source_dependency_current(video_id=video_id, old_revision=first.revision,
                                               current_revision=second.revision,
                                               dependency_kind="view:notes", cache=cache)
    assert not wiki._source_dependency_current(video_id=video_id, old_revision=first.revision,
                                               current_revision=second.revision,
                                               dependency_kind="source", cache=cache)
    db.update_video(video_id, published_at=1_700_000_001)
    third = sources.snapshots.capture(video_id)
    assert registry._collection_read_current(transcript_result, scope)
    assert wiki._source_dependency_current(video_id=video_id, old_revision=second.revision,
                                           current_revision=third.revision,
                                           dependency_kind="view:transcript", cache={})
    assert not wiki._source_dependency_current(video_id=video_id, old_revision=second.revision,
                                               current_revision=third.revision,
                                               dependency_kind="view:time", cache={})
    artifacts.write_text(path, "字幕步骤已更正")
    fourth = sources.snapshots.capture(video_id)
    assert not registry._collection_read_current(transcript_result, scope)
    assert not wiki._source_dependency_current(video_id=video_id, old_revision=third.revision,
                                               current_revision=fourth.revision,
                                               dependency_kind="view:transcript", cache={})


@pytest.mark.parametrize("texts,excerpt", [
    (["我决定先学数据库", "撤回刚才决定，先不学数据库了"], "我决定先学数据库"),
    (["这只是引用：我决定先学数据库，不是我的计划"], "我决定先学数据库"),
    (["这是个引用和假设，不是我的决定：视频里假设有人说“我决定转做游戏 Agent”",],
     "我决定转做游戏 Agent"),
])
def test_memory_extract_respects_latest_expression_and_quote(app_paths, monkeypatch, texts, excerpt):
    db, _artifacts, sources, store, _wiki = _services(app_paths)
    space = store.create_space(name="NB memory", all_active=True)
    thread = store.create_thread(space["id"])
    runs = [_run(store, space["id"], text, thread_id=thread["id"], key=f"e{i}")[0]
            for i, text in enumerate(texts)]
    with db.connect() as connection:
        messages = [connection.execute("SELECT id FROM assistant_messages WHERE run_id=? AND role='user'",
                                       (run["id"],)).fetchone() for run in runs]
        store._enqueue_memory_extraction(
            connection, run={**runs[0], "extraction_memory_epoch": 0},
            user_messages=messages, admission={"enabled": True, "generation": 0},
        )
    job = store.claim_job(owner="nb-test")
    assert job and job["kind"] == "memory_extract"

    class Provider:
        calls = 0

        def extract_memories(self, *, prompt):
            self.calls += 1
            return [{"op": "add", "kind": "decision", "text": "我决定先学数据库",
                     "subject_key": "database", "scope_kind": "space",
                     "source_excerpt": excerpt}]

    provider = Provider()
    runtime = AssistantRuntime(store=store, sources=sources, memory_backend=None,
                               context7=None, provider_factory=lambda: provider)
    monkeypatch.setattr(store, "maintenance_idle", lambda **_kwargs: True)
    result = asyncio.run(runtime._extract_memories(job))
    assert provider.calls == 1
    assert result["applied_memory_ids"] == []
    assert set(result["processed_message_ids"]) == {message["id"] for message in messages}
    assert MemoryService(db).list(space_id=space["id"]) == []


def test_memory_empty_batch_skips_provider(app_paths, monkeypatch):
    db, _artifacts, sources, store, _wiki = _services(app_paths)
    space = store.create_space(name="NB memory", all_active=True)
    run, context = _run(store, space["id"], "请用三条回答", key="format")
    message = next(item for item in context["thread"]["messages"] if item["role"] == "user")
    with db.connect() as connection:
        store._enqueue_memory_extraction(
            connection, run={**run, "extraction_memory_epoch": 0},
            user_messages=[message], admission={"enabled": True, "generation": 0},
        )
    job = store.claim_job(owner="nb-test")
    runtime = AssistantRuntime(store=store, sources=sources, memory_backend=None,
                               context7=None,
                               provider_factory=lambda: (_ for _ in ()).throw(AssertionError("model called")))
    result = asyncio.run(runtime._extract_memories(job))
    assert result["reason"] == "no_personal_background_candidate"


def test_two_week_stage_goal_keeps_user_time_basis():
    value = anchored_validity("这阶段我决定接下来两周优先补数据库基础",
                              "2026-09-26T07:03:59+00:00")
    assert value is not None
    assert value["expires_at"] == "2026-10-10T16:00:00+00:00"
    assert "原话" in value["validity_note"]
