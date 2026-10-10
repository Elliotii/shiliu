from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.artifacts import ArtifactStore
from shiliu.assistant.context import ContextComposer
from shiliu.assistant.dependencies import Mem0SemanticIndex
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.provider import ModelTurn, NativeToolCall
from shiliu.assistant.runtime import AssistantExecutionGraph, AssistantRuntime
from shiliu.assistant.snapshots import SourceSnapshotStore
from shiliu.assistant.sources import CollectionSourceService, SourceScope
from shiliu.assistant.store import AssistantRunStore
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.config import AppConfig, load_config, save_config
from shiliu.db import Database
from shiliu.domain import FavoriteItem
from shiliu.web import create_web_app


def test_assistant_flash_model_is_independent_and_round_trips(app_paths, monkeypatch) -> None:
    config = AppConfig(
        content_dir=str(app_paths.content_dir),
        interactive_model="existing-interactive",
        ingestion_model="existing-ingestion",
    )
    save_config(config, app_paths)
    loaded = load_config(app_paths)
    assert loaded.model_for("assistant") == "deepseek-v4-flash"
    assert loaded.model_for("grounded_answer") == "existing-interactive"
    assert loaded.model_for("formal_summary") == "existing-ingestion"
    # Construct no Application: model routing must not initialize a real database.
    import shiliu.app as app_module
    monkeypatch.setattr(app_module, "load_api_key", lambda _ref: "test-only")
    provider = Application.assistant_provider(SimpleNamespace(config=loaded))
    calls = []
    def capture(body):
        calls.append(body)
        return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
    monkeypatch.setattr(provider, "_post", capture)
    provider.turn(messages=[{"role": "user", "content": "test"}], tools=[])
    assert calls[0]["model"] == "deepseek-v4-flash"
    assert calls[0]["thinking"] == {"type": "disabled"}


class FakeMemoryBackend:
    def __init__(self) -> None:
        self.values: dict[str, dict] = {}
        self.deleted: list[str] = []

    def add(self, text, *, record_id, operation_id, record_version=1, scope_key="user"):
        backend_id = f"backend-{record_id}-{record_version}"
        self.values[backend_id] = {
            "id": backend_id,
            "memory": text,
            "score": 0.9,
            "metadata": {
                "record_id": record_id,
                "record_version": record_version,
                "scope_key": scope_key,
                "operation_id": operation_id,
            },
        }
        return {"results": [{"id": backend_id}]}

    def search(self, query, *, top_k=5, scope_key="user"):
        return [
            value for value in self.values.values()
            if value["metadata"]["scope_key"] == scope_key
        ][:top_k]

    def get_all(self, *, scope_key):
        return [
            value for value in self.values.values()
            if value["metadata"]["scope_key"] == scope_key
        ]

    def delete(self, backend_id):
        self.deleted.append(backend_id)
        self.values.pop(backend_id, None)


def test_mem0_stop_closes_qdrant_and_memory_before_releasing_owner(tmp_path) -> None:
    calls: list[str] = []

    class Client:
        def close(self) -> None:
            calls.append("qdrant")

    class Memory:
        vector_store = SimpleNamespace(client=Client())

        def close(self) -> None:
            calls.append("memory")

    backend = Mem0SemanticIndex(tmp_path / "mem0")
    backend._memory = Memory()
    backend._lock.release = lambda: calls.append("lock")  # type: ignore[method-assign]

    backend.stop()

    assert calls == ["qdrant", "memory", "lock"]
    assert backend._memory is None


class ScriptedProvider:
    def __init__(self) -> None:
        self.turns = 0
        self.observed_messages = []

    def turn(self, *, messages, tools, max_tokens):
        self.turns += 1
        self.observed_messages.append(messages)
        if self.turns == 1:
            return ModelTurn(
                text="",
                tool_calls=[
                    NativeToolCall(
                        call_id="call-search-1",
                        name="collection_search",
                        arguments={"sort": "collected_desc", "limit": 5},
                    )
                ],
                finish_reason="tool_calls",
                usage={"prompt_tokens": 20},
            )
        return ModelTurn(
            text="我找到了当前 Space 中的收藏，并据此给出回答。",
            finish_reason="stop",
            usage={"completion_tokens": 12},
        )

    def extract_memories(self, *, prompt):
        return []


class ExtractProvider:
    def __init__(self) -> None:
        self.calls = 0

    def extract_memories(self, *, prompt):
        self.calls += 1
        return [
            {
                "op": "add", "kind": "constraint",
                "text": "项目不使用图数据库", "subject_key": "graph_database",
                "scope_kind": "user", "source_excerpt": "请记住项目不使用图数据库",
            },
            {
                "op": "add", "kind": "preference",
                "text": "用户偏好微服务", "subject_key": "architecture_preference",
                "scope_kind": "user", "source_excerpt": "视频说微服务最好",
            },
        ]

    def turn(self, **kwargs):
        raise AssertionError("not used")


class SlowProvider:
    def turn(self, **kwargs):
        time.sleep(0.08)
        return ModelTurn(text="不应提交的迟到回答", finish_reason="stop")

    def extract_memories(self, *, prompt):
        return []


def _source_service(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    artifacts = ArtifactStore(app_paths.videos_dir)
    return db, CollectionSourceService(
        db=db,
        artifacts=artifacts,
        snapshots=SourceSnapshotStore(db, artifacts, app_paths.assistant_content_dir),
    )


def _add_video(db: Database, *, folder_id: int = 501):
    source_id = db.create_favorite_source(
        folder_id=folder_id, folder_title="阶段 B", history_policy="all"
    )
    db.record_source_snapshot(
        source_id,
        [FavoriteItem(
            bvid="BV1B23456789", title="Memory Agent 工程", uploader="公开作者",
            favorite_time=1_700_000_000,
        )],
        processing_profile="fast",
        authoritative=True,
        remote_total=1,
    )
    video = db.get_video_by_source("BV1B23456789")
    assert video is not None
    return source_id, int(video["id"])


def test_collection_read_cursor_is_version_bound_and_continues(app_paths) -> None:
    db, sources = _source_service(app_paths)
    source_id, video_id = _add_video(db)
    db.update_video(video_id, description="甲乙丙丁戊己庚辛壬癸")
    scope = SourceScope(source_db_ids=frozenset({source_id}))

    first = sources.read(
        call_id="read-page-1", scope=scope, source_ref=f"video:{video_id}",
        view="description", max_characters=4,
    )
    assert first.items[0]["content"] == "甲乙丙丁"
    assert first.truncated is True and first.next_cursor

    db.update_video(video_id, description="新版内容不会进入旧 cursor")
    second = sources.read(
        call_id="read-page-2", scope=scope, source_ref=first.source_refs[0],
        view="description", cursor=first.next_cursor, max_characters=4,
    )
    third = sources.read(
        call_id="read-page-3", scope=scope, source_ref=first.source_refs[0],
        view="description", cursor=second.next_cursor, max_characters=4,
    )

    assert second.items[0]["content"] == "戊己庚辛"
    assert third.items[0]["content"] == "壬癸"
    assert third.next_cursor is None and third.truncated is False


def test_query_time_sort_is_explicitly_bounded_and_reorders_candidates(app_paths) -> None:
    db, sources = _source_service(app_paths)
    source_id = db.create_favorite_source(
        folder_id=502, folder_title="真实排序", history_policy="all"
    )
    db.record_source_snapshot(
        source_id,
        [
            FavoriteItem(bvid="BV1B2345678A", title="较早 Agent", uploader="A", favorite_time=100),
            FavoriteItem(bvid="BV1B2345678B", title="较新 Agent", uploader="B", favorite_time=300),
        ],
        processing_profile="fast",
        authoritative=True,
        remote_total=2,
    )
    older = db.get_video_by_source("BV1B2345678A")
    newer = db.get_video_by_source("BV1B2345678B")
    assert older and newer

    class Search:
        def search_with_raw(self, *_args, **_kwargs):
            return None, SimpleNamespace(results=[
                SimpleNamespace(video_id=older["id"], match_excerpt="旧命中"),
                SimpleNamespace(video_id=newer["id"], match_excerpt="新命中"),
            ])

    sources.product_search = Search()  # type: ignore[assignment]
    result = sources.search(
        call_id="sorted-query", scope=SourceScope(frozenset({source_id})),
        query="Agent", sort="collected_desc", limit=2,
    )

    assert [item["video_id"] for item in result.items] == [newer["id"], older["id"]]
    assert [item["matched_excerpt"] for item in result.items] == ["新命中", "旧命中"]
    assert "不是对范围内全部关键词命中的穷尽排序" in result.summary


def test_space_video_selection_intersects_real_collection_scope(app_paths) -> None:
    db, sources = _source_service(app_paths)
    source_id = db.create_favorite_source(
        folder_id=503, folder_title="试用范围", history_policy="all"
    )
    db.record_source_snapshot(
        source_id,
        [
            FavoriteItem(bvid="BV1B2345678C", title="选中", uploader="A", favorite_time=200),
            FavoriteItem(bvid="BV1B2345678D", title="未选中", uploader="B", favorite_time=300),
        ],
        processing_profile="fast",
        authoritative=True,
        remote_total=2,
    )
    selected = db.get_video_by_source("BV1B2345678C")
    excluded = db.get_video_by_source("BV1B2345678D")
    assert selected and excluded
    store = AssistantRunStore(db)
    space = store.create_space(
        name="真实收藏试用", source_ids=[source_id], video_ids=[selected["id"]]
    )
    assert space["video_ids"] == [selected["id"]]
    scope = SourceScope(
        source_db_ids=frozenset(space["source_ids"]),
        video_ids=frozenset(space["video_ids"]),
    )

    assert sources.visible_video_ids(scope) == [selected["id"]]
    assert sources.source_refs_visible([f"video:{selected['id']}"], scope)
    assert not sources.source_refs_visible([f"video:{excluded['id']}"], scope)


def test_metadata_mode_finds_title_without_content_index_and_returns_beijing_time(app_paths) -> None:
    db, sources = _source_service(app_paths)
    source_id = db.create_favorite_source(
        folder_id=504, folder_title="标题回退", history_policy="all"
    )
    db.record_source_snapshot(
        source_id,
        [FavoriteItem(
            bvid="BV1B2345678E", title="Agent 面试项目方向", uploader="公开作者",
            favorite_time=1_700_000_000,
        )],
        processing_profile="fast", authoritative=True, remote_total=1,
    )

    result = sources.search(
        call_id="title-fallback", scope=SourceScope(frozenset({source_id})),
        query="Agent 面试 项目", mode="metadata", limit=3,
    )

    assert result.status == "ok"
    assert result.items[0]["title"] == "Agent 面试项目方向"
    assert result.items[0]["memberships"][0]["favorite_time"].endswith("+08:00")
    assert result.coverage["exhaustive"] is True


def test_collection_search_uses_one_unified_scope_beyond_deep_bound(app_paths) -> None:
    db, sources = _source_service(app_paths)
    source_id = db.create_favorite_source(
        folder_id=505, folder_title="九项试用范围", history_policy="all"
    )
    items = [
        FavoriteItem(
            bvid=f"BV1B23456{i:02d}", title=f"Agent 材料 {i}", uploader="作者",
            favorite_time=100 + i,
        )
        for i in range(9)
    ]
    db.record_source_snapshot(
        source_id, items, processing_profile="fast", authoritative=True, remote_total=9,
    )
    calls: list[tuple[int, ...]] = []

    class Search:
        def search_with_raw(self, _request, *, scope_video_ids, principal_id):
            assert principal_id == "local_operator"
            calls.append(scope_video_ids)
            return None, SimpleNamespace(results=[
                SimpleNamespace(
                    video_id=scope_video_ids[0], match_excerpt="命中",
                    best_score=float(scope_video_ids[0]), best_rank=1,
                )
            ])

    sources.product_search = Search()  # type: ignore[assignment]
    result = sources.search(
        call_id="nine-video-search",
        scope=SourceScope(
            source_db_ids=frozenset({source_id}),
            video_ids=frozenset(
                int(db.get_video_by_source(item.bvid)["id"]) for item in items
            ),
        ),
        query="Agent",
        limit=5,
    )

    assert [len(batch) for batch in calls] == [9]
    assert result.status == "ok"
    assert len(result.items) == 1


def test_memory_formal_state_projection_correction_forget_and_late_proposal(app_paths) -> None:
    db, _sources = _source_service(app_paths)
    store = AssistantRunStore(db)
    space = store.create_space(name="项目", all_active=True)
    backend = FakeMemoryBackend()
    memories = MemoryService(db, backend=backend)

    created = memories.save_explicit(
        text="本项目不引入图数据库",
        subject_key="storage_choice",
        kind="constraint",
        scope_kind="space",
        scope_id=space["id"],
        operation_key="memory-op-1",
        source_message_ids=["user-message-1"],
        source_excerpt="请记住本项目不引入图数据库",
    )
    replay = memories.save_explicit(
        text="会被 operation receipt 忽略",
        subject_key="different",
        kind="context",
        scope_kind="space",
        scope_id=space["id"],
        operation_key="memory-op-1",
    )
    assert replay["id"] == created["id"]

    projected = memories.project(memory_id=created["id"], version=1)
    corrected = memories.correct(
        created["id"],
        text="本阶段使用 SQLite，不引入图数据库",
        expected_version=1,
        operation_key="memory-correct-1",
    )
    memories.project(
        memory_id=created["id"], version=2, old_backend_id=projected["backend_id"]
    )
    recalled = memories.recall("存储怎么选", space_id=space["id"])
    assert [item["text"] for item in recalled] == [corrected["text"]]
    assert projected["backend_id"] in backend.deleted

    forgotten = memories.forget(
        created["id"], expected_version=2, operation_key="memory-forget-1"
    )
    backend.values["late-old-vector"] = {
        "id": "late-old-vector", "memory": "旧正文", "score": 1.0,
        "metadata": {
            "record_id": created["id"], "record_version": 1,
            "scope_key": f"space:{space['id']}", "operation_id": "old",
        },
    }
    assert forgotten["status"] == "forgotten"
    assert memories.recall("图数据库", space_id=space["id"]) == []
    late = memories.apply_extracted(
        {
            "op": "add", "kind": "constraint", "text": "本项目不引入图数据库",
            "subject_key": "storage_choice", "scope_kind": "space",
            "scope_id": space["id"], "source_excerpt": "请记住",
        },
        source_message_ids=["user-message-1"],
        expected_epoch=0,
        operation_key="late-proposal",
    )
    assert late is None
    same_fact_from_later_message = memories.apply_extracted(
        {
            "op": "add", "kind": "constraint", "text": "本阶段使用 SQLite，不引入图数据库",
            "subject_key": "storage_choice", "scope_kind": "space",
            "scope_id": space["id"], "source_excerpt": "项目仍然这样做",
        },
        source_message_ids=["later-message"],
        expected_epoch=0,
        operation_key="late-proposal-other-message",
    )
    assert same_fact_from_later_message is None


def test_native_tool_graph_persists_pairs_answer_and_request_replay(app_paths) -> None:
    db, sources = _source_service(app_paths)
    source_id, _video_id = _add_video(db)
    store = AssistantRunStore(db)
    space = store.create_space(name="对话", source_ids=[source_id])
    thread = store.create_thread(space["id"])
    created = store.create_run(thread["id"], text="列出我的项目收藏", request_id="request-1")
    claimed = store.claim_next_run()
    assert claimed and claimed["id"] == created["id"]
    provider = ScriptedProvider()
    memories = MemoryService(db)
    registry = AssistantToolRegistry(sources=sources, memories=memories, store=store)
    graph = AssistantExecutionGraph(
        store=store, memories=memories, tools=registry,
        provider_factory=lambda: provider,
    )

    asyncio.run(graph.run(claimed))

    completed = store.get_run(created["id"])
    restored = AssistantRunStore(db).get_thread(thread["id"])
    replay = store.create_run(
        thread["id"], text="不会重复创建", request_id="request-1"
    )
    roles = [item["role"] for item in restored["messages"]]
    assert completed["status"] == "completed"
    assert replay["id"] == created["id"]
    assert roles == ["user", "assistant", "tool", "assistant"]
    assert provider.turns == 2
    assert any("tool_call_id" in message for message in provider.observed_messages[-1])
    jobs = store.list_jobs()
    assert [job["kind"] for job in jobs] == ["memory_extract"]


def test_narrow_collection_lookup_does_not_schedule_memory_extraction(app_paths) -> None:
    db, sources = _source_service(app_paths)
    source_id, _video_id = _add_video(db)
    store = AssistantRunStore(db)
    space = store.create_space(name="简单找回", source_ids=[source_id])
    thread = store.create_thread(space["id"])
    run = store.create_run(
        thread["id"], text="我收藏里有没有《Memory Agent 工程》？只需找回这条标题和收藏时间。",
        request_id="narrow-lookup",
    )
    claimed = store.claim_next_run()
    assert claimed and claimed["id"] == run["id"]
    memories = MemoryService(db)
    provider = ScriptedProvider()
    graph = AssistantExecutionGraph(
        store=store, memories=memories,
        tools=AssistantToolRegistry(sources=sources, memories=memories, store=store),
        provider_factory=lambda: provider,
    )
    asyncio.run(graph.run(claimed))
    assert store.get_run(run["id"])["status"] == "completed"
    assert [message["role"] for message in store.get_thread(thread["id"])["messages"]] == [
        "user", "assistant", "tool", "assistant",
    ]
    assert store.list_jobs() == []


def test_user_answer_omits_english_process_preamble() -> None:
    raw = "I have what I need. Here's the comparison.\n\n## 两份材料\n条件不同。"
    assert AssistantExecutionGraph._presentable_answer(raw) == "## 两份材料\n条件不同。"
    assert AssistantExecutionGraph._presentable_answer("## Agent Memory\n中文说明。") == "## Agent Memory\n中文说明。"


def test_cancel_restart_resume_and_expired_job_lease_are_durable(app_paths) -> None:
    db, _sources = _source_service(app_paths)
    first = AssistantRunStore(db)
    space = first.create_space(name="恢复", all_active=True)
    thread = first.create_thread(space["id"])
    cancelled = first.create_run(thread["id"], text="停止我", request_id="cancel-1")
    claimed = first.claim_next_run()
    assert claimed and claimed["id"] == cancelled["id"]
    first.cancel_run(cancelled["id"])
    assert first.complete_run(
        cancelled["id"], epoch=claimed["run_epoch"], answer="迟到答案", usage={}
    ) is False

    second_thread = first.create_thread(space["id"])
    interrupted = first.create_run(second_thread["id"], text="重启我", request_id="restart-1")
    assert first.claim_next_run()["id"] == interrupted["id"]
    restarted = AssistantRunStore(db)
    assert restarted.recover_interrupted_runs() == 1
    resumed = restarted.resume_run(interrupted["id"])
    assert resumed["status"] == "queued" and resumed["run_epoch"] == 2

    with db.connect() as connection:
        job_id = first.enqueue_job(
            connection, kind="memory_index", dedupe_key="lease-test",
            payload={"memory_id": "missing", "version": 1},
        )
    leased = first.claim_job(owner="dead-worker", lease_seconds=120)
    assert leased and leased["id"] == job_id
    with db.connect() as connection:
        connection.execute(
            "UPDATE assistant_jobs SET lease_until='2000-01-01T00:00:00+00:00' WHERE id=?",
            (job_id,),
        )
    reclaimed = restarted.claim_job(owner="new-worker")
    assert reclaimed and reclaimed["id"] == job_id and reclaimed["attempt"] == 2
    assert restarted.heartbeat_job(
        job_id, owner="new-worker", lease_epoch=reclaimed["lease_epoch"]
    )
    assert not restarted.finish_job(
        job_id, owner="dead-worker", lease_epoch=leased["lease_epoch"]
    )
    assert restarted.finish_job(
        job_id, owner="new-worker", lease_epoch=reclaimed["lease_epoch"]
    )


def test_cancel_during_model_call_fences_late_provider_result(app_paths) -> None:
    db, sources = _source_service(app_paths)
    store = AssistantRunStore(db)
    space = store.create_space(name="取消", all_active=True)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="开始慢请求", request_id="slow-1")
    claimed = store.claim_next_run()
    assert claimed
    memories = MemoryService(db)
    graph = AssistantExecutionGraph(
        store=store,
        memories=memories,
        tools=AssistantToolRegistry(sources=sources, memories=memories, store=store),
        provider_factory=SlowProvider,
    )

    async def scenario():
        task = asyncio.create_task(graph.run(claimed))
        await asyncio.sleep(0.02)
        store.cancel_run(run["id"])
        await task

    asyncio.run(scenario())
    restored = store.get_thread(thread["id"])
    assert store.get_run(run["id"])["status"] == "cancelled"
    assert [(item["role"], item["content"]) for item in restored["messages"]] == [
        ("user", "开始慢请求")
    ]


def test_scope_change_cancels_active_run_and_fences_old_scope(app_paths) -> None:
    db, _sources = _source_service(app_paths)
    source_id, _video_id = _add_video(db)
    store = AssistantRunStore(db)
    space = store.create_space(name="范围", source_ids=[source_id])
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="读取旧范围", request_id="scope-1")
    claimed = store.claim_next_run()
    assert claimed

    updated = store.update_space(
        space["id"], expected_scope_version=1, source_ids=[], all_active=False
    )

    fenced = store.get_run(run["id"])
    assert updated["scope_version"] == 2
    assert fenced["status"] == "cancelled" and fenced["run_epoch"] == 2
    assert fenced["last_error_code"] == "scope_changed"
    assert store.complete_run(run["id"], epoch=1, answer="旧范围迟到结果", usage={}) is False


def test_context_budget_keeps_current_request_and_tool_pairs(app_paths) -> None:
    db, _sources = _source_service(app_paths)
    memories = MemoryService(db)
    composer = ContextComposer(memories, input_budget_tokens=1800)
    messages = [
        {"role": "user", "content": "旧问题" * 80, "provider_payload_json": "{}"},
        {
            "role": "assistant", "content": "", "provider_payload_json": json.dumps({
                "tool_calls": [{"id": "old-call", "type": "function", "function": {
                    "name": "collection_search", "arguments": "{}"
                }}]
            }),
        },
        {
            "role": "tool", "content": "旧结果" * 80,
            "provider_payload_json": json.dumps({
                "tool_call_id": "old-call", "name": "collection_search"
            }),
        },
        {"role": "user", "content": "这是当前必须保留的要求", "provider_payload_json": "{}"},
    ]
    output, estimated = composer.compose({
        "space": {"id": 1, "name": "预算", "goal": "", "scope_version": 1},
        "thread": {"messages": messages},
    })

    assert output[-1]["content"] == "这是当前必须保留的要求"
    tool_results = [item for item in output if item["role"] == "tool"]
    tool_call_ids = {
        call["id"] for item in output if item["role"] == "assistant"
        for call in item.get("tool_calls", [])
    }
    assert all(item["tool_call_id"] in tool_call_ids for item in tool_results)
    assert estimated <= 1800


def test_automatic_extraction_keeps_temporary_and_video_opinions_out(app_paths) -> None:
    db, sources = _source_service(app_paths)
    store = AssistantRunStore(db)
    space = store.create_space(name="提炼", all_active=True)
    provider = ExtractProvider()
    runtime = AssistantRuntime(
        store=store,
        sources=sources,
        memory_backend=FakeMemoryBackend(),  # type: ignore[arg-type]
        context7=SimpleNamespace(),  # type: ignore[arg-type]
        provider_factory=lambda: provider,
    )
    thread = store.create_thread(space["id"])
    run = store.create_run(
        thread["id"],
        text="请记住项目不使用图数据库。视频说微服务最好。",
        request_id="extract-1",
    )
    claimed = store.claim_next_run()
    assert claimed
    assert store.complete_run(run["id"], epoch=1, answer="收到", usage={})
    job = store.claim_job(owner="extract-test")
    assert job and job["kind"] == "memory_extract"
    result = asyncio.run(runtime._extract_memories(job))
    store.finish_job(job["id"], proposal=result)
    memories = runtime.memories.list(space_id=space["id"])

    assert len(result["applied_memory_ids"]) == 1
    assert [item["subject_key"] for item in memories] == ["graph_database"]
    assert memories[0]["scope_kind"] == "space"
    with db.connect() as connection:
        assert connection.execute(
            "SELECT proposal_json FROM assistant_jobs WHERE id=?", (job["id"],)
        ).fetchone()[0]
    index_job = store.claim_job(owner="index-placeholder")
    assert index_job and index_job["kind"] == "memory_index"
    store.finish_job(index_job["id"])

    temporary_thread = store.create_thread(space["id"])
    temporary_run = store.create_run(
        temporary_thread["id"], text="这次回答短一点", request_id="extract-temp"
    )
    temporary_claim = store.claim_next_run()
    assert temporary_claim
    assert store.complete_run(temporary_run["id"], epoch=1, answer="好", usage={})
    temporary_job = store.claim_job(owner="extract-test-2")
    assert temporary_job
    temporary = asyncio.run(runtime._extract_memories(temporary_job))
    assert temporary["proposals"] == []
    assert provider.calls == 1


def test_assistant_page_and_management_api_are_operable_without_worker_mocking(app_paths) -> None:
    save_config(
        AppConfig(
            content_dir=str(app_paths.content_dir),
            bili_cli_root=str(app_paths.state_dir / "unused"),
            assistant_enabled=True,
        ),
        app_paths,
    )
    application = Application(app_paths)
    store = application.assistant_foundation.store
    memories = MemoryService(application.db)
    application._assistant_runtime = SimpleNamespace(
        store=store,
        memories=memories,
        capabilities=lambda: {"runtime": "test-ready"},
        start=lambda: None,
        stop=lambda: None,
    )
    client = TestClient(create_web_app(application))

    page = client.get("/assistant")
    created_space = client.post(
        "/api/assistant/spaces",
        json={"name": "界面项目", "goal": "完成阶段 B", "source_ids": [], "all_active": True},
    )
    space_id = created_space.json()["space"]["id"]
    created_thread = client.post(
        "/api/assistant/threads", json={"space_id": space_id, "title": ""}
    )
    thread_id = created_thread.json()["thread"]["id"]
    run = client.post(
        f"/api/assistant/threads/{thread_id}/runs",
        json={"input": "从收藏开始", "request_id": "ui-request-1"},
    )
    memory = client.post(
        "/api/assistant/memories",
        json={
            "text": "回答优先给出可执行步骤", "subject_key": "answer_style",
            "kind": "preference", "scope_kind": "space", "scope_id": space_id,
            "operation_key": "ui-memory-1", "pinned": False,
        },
    )
    blocked_job = store.claim_job(owner="api-retry-test")
    assert blocked_job
    store.fail_job(
        blocked_job, code="memory_backend_unavailable", message="先初始化本地索引",
        blocked=True,
    )
    retried = client.post(f"/api/assistant/jobs/{blocked_job['id']}/retry")

    assert page.status_code == 200 and "想从收藏里找什么？" in page.text
    assert "subject_key" not in page.text and "operation_key" not in page.text
    assert run.status_code == 202 and run.json()["run"]["status"] == "queued"
    assert memory.status_code == 201
    assert retried.status_code == 202 and retried.json()["job"]["status"] == "queued"
    assert client.get(f"/api/assistant/threads/{thread_id}").json()["thread"]["messages"][0]["content"] == "从收藏开始"


def test_recall_multiple_records_and_corrected_pending_projection(app_paths) -> None:
    db, _sources = _source_service(app_paths)
    backend = FakeMemoryBackend()
    memories = MemoryService(db, backend=backend)
    store = AssistantRunStore(db)
    space = store.create_space(name="召回", all_active=True)
    first = memories.save_explicit(
        text="必须使用 SQLite", subject_key="database", kind="constraint",
        scope_kind="space", scope_id=space["id"], operation_key="multi-1",
    )
    second = memories.save_explicit(
        text="部署必须可离线", subject_key="deployment", kind="constraint",
        scope_kind="space", scope_id=space["id"], operation_key="multi-2",
    )
    memories.project(memory_id=first["id"], version=1)
    memories.project(memory_id=second["id"], version=1)
    assert {item["id"] for item in memories.recall("项目约束", space_id=space["id"])} == {
        first["id"], second["id"],
    }

    corrected = memories.correct(
        first["id"], text="必须使用 SQLite 3.46", expected_version=1,
        operation_key="multi-correct",
    )
    recalled = memories.recall("数据库", space_id=space["id"])
    assert next(item for item in recalled if item["id"] == first["id"])["text"] == corrected["text"]


def test_model_memory_writes_reject_another_space(app_paths) -> None:
    db, sources = _source_service(app_paths)
    store = AssistantRunStore(db)
    space_a = store.create_space(name="A", all_active=True)
    space_b = store.create_space(name="B", all_active=True)
    thread = store.create_thread(space_a["id"])
    run = store.create_run(thread["id"], text="改记忆", request_id="cross-space")
    memories = MemoryService(db)
    foreign = memories.save_explicit(
        text="B 的私有约束", subject_key="private", kind="constraint",
        scope_kind="space", scope_id=space_b["id"], operation_key="foreign-memory",
    )
    registry = AssistantToolRegistry(sources=sources, memories=memories, store=store)

    async def execute(name, arguments):
        return await registry.execute(
            name=name, arguments=arguments, call_id=f"call-{name}",
            run_context=store.run_context(run["id"]),
        )

    corrected = asyncio.run(execute("memory_correct", {
        "memory_id": foreign["id"], "text": "越权修改", "expected_version": 1,
    }))
    forgotten = asyncio.run(execute("memory_forget", {
        "memory_id": foreign["id"], "expected_version": 1,
    }))
    assert corrected["status"] == "unavailable"
    assert forgotten["status"] == "unavailable"
    assert memories.get(foreign["id"])["text"] == "B 的私有约束"
    assert memories.get(foreign["id"])["status"] == "active"


def test_scope_change_excludes_completed_old_tool_body(app_paths) -> None:
    db, _sources = _source_service(app_paths)
    source_id, _video_id = _add_video(db)
    store = AssistantRunStore(db)
    space = store.create_space(name="范围隔离", source_ids=[source_id])
    thread = store.create_thread(space["id"])
    old = store.create_run(thread["id"], text="旧范围", request_id="old-scope")
    claimed = store.claim_next_run()
    assert claimed
    store.save_assistant_tool_message(old["id"], content="", provider_payload={
        "tool_calls": [{"id": "old-call", "type": "function", "function": {
            "name": "collection_read", "arguments": "{}",
        }}],
    })
    store.save_tool_result_message(
        old["id"], content="OLD_SCOPE_SECRET_SENTINEL",
        provider_payload={"tool_call_id": "old-call", "name": "collection_read"},
    )
    assert store.complete_run(old["id"], epoch=1, answer="旧回答", usage={})
    store.update_space(space["id"], expected_scope_version=1, source_ids=[], all_active=False)
    current = store.create_run(thread["id"], text="新范围", request_id="new-scope")
    encoded = json.dumps(store.run_context(current["id"]), ensure_ascii=False)
    assert "OLD_SCOPE_SECRET_SENTINEL" not in encoded
    assert "新范围" in encoded


def test_duplicate_extraction_preserves_explicit_edit_protection(app_paths) -> None:
    db, _sources = _source_service(app_paths)
    store = AssistantRunStore(db)
    space = store.create_space(name="保护", all_active=True)
    memories = MemoryService(db)
    explicit = memories.save_explicit(
        text="输出先给结论", subject_key="answer_style", kind="preference",
        scope_kind="space", scope_id=space["id"], operation_key="explicit-first",
        pinned=True,
    )
    duplicate = memories.apply_extracted(
        {"op": "add", "kind": "preference", "text": "输出先给结论",
         "subject_key": "answer_style", "scope_kind": "space", "scope_id": space["id"],
         "source_excerpt": "请记住输出先给结论"},
        source_message_ids=["message-1"], expected_epoch=0, operation_key="extract-duplicate",
    )
    restored = memories.get(explicit["id"])
    assert duplicate and duplicate["id"] == explicit["id"]
    assert restored["origin"] == "explicit"
    assert restored["user_edited"] is True
    assert restored["pinned"] is True


def test_tool_interruption_recovers_before_model_and_budget_resume_completes(app_paths) -> None:
    db, sources = _source_service(app_paths)
    _source_id, _video_id = _add_video(db)
    store = AssistantRunStore(db)
    space = store.create_space(name="恢复执行", all_active=True)
    memories = MemoryService(db)
    registry = AssistantToolRegistry(sources=sources, memories=memories, store=store)

    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="恢复搜索", request_id="recover-tool")
    claimed = store.claim_next_run()
    assert claimed
    store.save_assistant_tool_message(run["id"], content="", provider_payload={
        "tool_calls": [{"id": "pending-search", "type": "function", "function": {
            "name": "collection_search", "arguments": json.dumps({"limit": 3}),
        }}],
    })
    assert store.recover_interrupted_runs() == 1
    store.resume_run(run["id"])
    resumed = store.claim_next_run()
    assert resumed

    class FinalProvider:
        def __init__(self): self.calls = 0
        def turn(self, **kwargs):
            self.calls += 1
            assert any(message["role"] == "tool" for message in kwargs["messages"])
            return ModelTurn(text="恢复完成", finish_reason="stop")

    provider = FinalProvider()
    graph = AssistantExecutionGraph(
        store=store, memories=memories, tools=registry, provider_factory=lambda: provider,
    )
    asyncio.run(graph.run(resumed))
    recovered_thread = store.get_thread(thread["id"])
    assert store.get_run(run["id"])["status"] == "completed"
    assert [message["role"] for message in recovered_thread["messages"]].count("tool") == 1
    assert provider.calls == 1

    budget_thread = store.create_thread(space["id"])
    budget_run = store.create_run(
        budget_thread["id"], text="预算后继续", request_id="budget-resume",
    )
    budget_claim = store.claim_next_run()
    assert budget_claim
    exhausted = AssistantExecutionGraph(
        store=store, memories=memories, tools=registry,
        provider_factory=lambda: FinalProvider(), max_steps=0,
    )
    asyncio.run(exhausted.run(budget_claim))
    assert store.get_run(budget_run["id"])["status"] == "budget_exhausted"
    store.resume_run(budget_run["id"])
    next_segment = store.claim_next_run()
    assert next_segment

    class PlainProvider:
        def turn(self, **kwargs):
            return ModelTurn(text="继续成功", finish_reason="stop")

    continued = AssistantExecutionGraph(
        store=store, memories=memories, tools=registry,
        provider_factory=PlainProvider, max_steps=1,
    )
    asyncio.run(continued.run(next_segment))
    assert store.get_run(budget_run["id"])["status"] == "completed"


def test_slow_background_extraction_does_not_block_foreground_or_heartbeat(app_paths) -> None:
    db, sources = _source_service(app_paths)
    store = AssistantRunStore(db)
    space = store.create_space(name="并发", all_active=True)

    class FastProvider:
        def turn(self, **kwargs):
            return ModelTurn(text="前台已响应", finish_reason="stop")
        def extract_memories(self, *, prompt):
            return []

    class SlowExtractProvider(FastProvider):
        def extract_memories(self, *, prompt):
            time.sleep(0.12)
            return []

    class ObservedRuntime(AssistantRuntime):
        heartbeat_ticks = 0
        async def _heartbeat_job(self, job):
            while True:
                await asyncio.sleep(0.01)
                self.heartbeat_ticks += 1

    runtime = ObservedRuntime(
        store=store, sources=sources, memory_backend=FakeMemoryBackend(),  # type: ignore[arg-type]
        context7=SimpleNamespace(), provider_factory=FastProvider,  # type: ignore[arg-type]
        extraction_provider_factory=SlowExtractProvider,
    )
    completed_thread = store.create_thread(space["id"])
    completed = store.create_run(
        completed_thread["id"], text="请记住并发测试", request_id="background-source",
    )
    assert store.claim_next_run()
    assert store.complete_run(completed["id"], epoch=1, answer="收到", usage={})
    background_job = store.claim_job(owner="slow-background")
    assert background_job and background_job["kind"] == "memory_extract"

    foreground_thread = store.create_thread(space["id"])
    foreground = store.create_run(
        foreground_thread["id"], text="现在回答", request_id="foreground-run",
    )
    graph = AssistantExecutionGraph(
        store=store, memories=runtime.memories,
        tools=AssistantToolRegistry(sources=sources, memories=runtime.memories, store=store),
        provider_factory=FastProvider,
    )

    async def scenario():
        background = asyncio.create_task(runtime._process_job(background_job))
        foreground_loop = asyncio.create_task(runtime._foreground_loop(graph))
        for _ in range(30):
            if store.get_run(foreground["id"])["status"] == "completed":
                break
            await asyncio.sleep(0.01)
        runtime._stop.set()
        await background
        await foreground_loop

    asyncio.run(scenario())
    assert store.get_run(foreground["id"])["status"] == "completed"
    assert runtime.heartbeat_ticks > 0
