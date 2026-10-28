"""Application is the sole pool owner; explicit configuration, no daily paths."""

import os
from pathlib import Path
from dataclasses import replace
import pytest
from shiliu.config import PostgresConfig, AppConfig
from shiliu.app import Application
from schema_support import formal_target
from test_collection_retrieval import FixedProvider


@pytest.fixture
def application_target(tmp_path):
    control = PostgresConfig(
        os.environ["SHILIU_DATABASE_URL"],
        Path(os.environ["SHILIU_ARTIFACT_ROOT"]),
        "test",
    )
    with formal_target(control) as (runtime, admin):
        (tmp_path / "formal-artifacts").mkdir(mode=0o700)
        yield replace(runtime, artifact_root=tmp_path / "formal-artifacts"), admin


def test_application_config_missing_fails_before_daily_path_or_credentials(monkeypatch):
    import shiliu.app as app_module
    from shiliu.config import AppPaths

    def forbidden(*args, **kwargs):
        raise AssertionError("daily paths or credentials consulted")

    for key in ["SHILIU_DATABASE_URL", "SHILIU_ARTIFACT_ROOT", "SHILIU_ENV"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(AppPaths, "defaults", forbidden)
    monkeypatch.setattr(app_module, "load_config", forbidden)
    monkeypatch.setattr(app_module, "load_api_key", forbidden)
    with pytest.raises(ValueError, match="Explicit PostgreSQL"):
        Application()


def test_application_real_pg_pool_start_recovery_single_serve_and_idempotent_close(
    application_target, app_paths, monkeypatch
):
    import shiliu.app as app_module
    import sqlite3
    from shiliu.ask.persistence import AskRunStore
    from shiliu.sync import SyncAlreadyRunning

    def forbidden(*args, **kwargs):
        raise AssertionError("legacy database or credential access")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(app_module, "load_config", forbidden)
    monkeypatch.setattr(app_module, "load_api_key", forbidden)
    runtime, _ = application_target
    config = AppConfig(content_dir=str(app_paths.content_dir), assistant_enabled=False)
    core = Application(
        app_paths,
        config=config,
        postgres_config=runtime,
        embedding_provider=FixedProvider(),
        adapter=object(),
        provider_availability=lambda: {
            "available": False,
            "reason": "no model configured",
        },
    )
    try:
        store = AskRunStore(core.db)
        store.start(
            run_id="lost-before-start", query="synthetic", mode="deep", filters={}
        )
        core.start(background_tasks=False)
        assert store.get_run("lost-before-start")["termination_reason"] == "interrupted"
        assert core.db.pg is core.pg
        assert core.research.db is core.db and core.artifacts.db is core.db
        other = Application(
            app_paths,
            config=config,
            postgres_config=runtime,
            embedding_provider=FixedProvider(),
            adapter=object(),
        )
        with pytest.raises(SyncAlreadyRunning):
            other.start(background_tasks=False)
        assert other.pg._pool.closed
        assert core.db.list_sources() == []
    finally:
        core.close()
    core.close()
    assert core.pg._pool.closed
    assert not app_paths.database.exists()


def test_application_compose_failure_closes_opened_pool(
    application_target, app_paths, monkeypatch
):
    from shiliu.storage.postgres import PgDatabase

    closed = []
    original = PgDatabase.close

    def close(self):
        original(self)
        closed.append(self)

    monkeypatch.setattr(PgDatabase, "close", close)

    def fail(*args):
        raise RuntimeError("synthetic compose failure")

    monkeypatch.setattr(Application, "_compose", fail)
    with pytest.raises(RuntimeError, match="synthetic compose"):
        Application(
            app_paths,
            config=AppConfig(content_dir=str(app_paths.content_dir)),
            postgres_config=application_target[0],
        )
    assert len(closed) == 1 and closed[0]._pool.closed


def create_core(runtime, app_paths, **overrides):
    config = overrides.pop(
        "config",
        AppConfig(content_dir=str(app_paths.content_dir), assistant_enabled=False),
    )
    return Application(
        app_paths,
        config=config,
        postgres_config=runtime,
        embedding_provider=FixedProvider(),
        adapter=object(),
        **overrides,
    )


def test_real_application_web_collection_ask_research_knowledge_export_and_draft(
    application_target, app_paths, monkeypatch
):
    import json
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from shiliu.web import create_web_app
    from test_collection_retrieval import add_video
    from test_v4_fast_ask_api import _Provider
    from test_deep_v2 import Provider as ReduceProvider
    from shiliu.ask.deep.v2 import QueryReduction, V2Decision
    from test_v5_b_stage3_artifact_reuse import _vertical, _assess
    from shiliu.research.knowledge_contracts import (
        ExportTopicPageRequest,
        ProceedArtifactRouteRequest,
    )
    from shiliu.knowledge_draft import SaveKnowledgeDraftRequest

    answer = _Provider()
    reducer = ReduceProvider([])

    class Provider:
        model = "synthetic"

        def generate_structured(self, **kwargs):
            if kwargs["response_schema"] is QueryReduction:
                return reducer.generate_structured(**kwargs)
            if kwargs["response_schema"] is V2Decision:
                payload = json.loads(kwargs["messages"][-1]["content"])
                decision = (
                    {
                        "type": "continue",
                        "actions": [
                            {
                                "action_id": "search",
                                "kind": "search_transcripts",
                                "arguments": {"query": "MCP"},
                                "purpose": "read synthetic evidence",
                            }
                        ],
                    }
                    if not payload["query_results"]
                    else {
                        "type": "finish",
                        "outcome": "sufficient",
                        "answer_evidence_refs": [
                            r
                            for q in payload["query_results"]
                            for r in q.get("retained_evidence_refs", [])
                        ],
                        "finish_reason": "evidence read",
                    }
                )
                return SimpleNamespace(
                    output=V2Decision.model_validate(decision),
                    usage={"input_tokens": 3},
                    latency_ms=1,
                )
            return answer.generate_structured(**kwargs)

    provider = Provider()
    core = create_core(
        application_target[0], app_paths, provider_factory=lambda role: provider
    )
    resources = (core.db, core.artifacts, core.retrieval, core.dense_retrieval)
    _, vid = add_video(
        resources,
        text="请解释 MCP 工具执行为何需要幂等回执。MCP 通过明确协议连接模型与外部工具。工具执行需要持久请求身份与幂等回执。失去 lease 的旧 worker 不得提交结果。",
    )
    core.db.update_video(vid, title="请解释 MCP 工具执行为何需要幂等回执")
    core.dense_retrieval.rebuild()
    with TestClient(create_web_app(core, background_tasks=False)) as client:
        health = client.get("/api/health")
        assert health.status_code == 200, health.text
        assert (
            health.json()["storage"] == "postgresql"
            and health.json()["collection_videos"] == 1
        )
        response = client.post(
            "/api/ask/stream", json={"query": "解释 MCP", "mode": "fast"}
        )
        assert response.status_code == 200, response.text
        fast_id = response.headers["x-shiliu-run-id"]
        assert core.ask_service.run_store.get_run(fast_id)["citations"]
        response = client.post(
            "/api/ask/runs", json={"query": "解释 MCP", "mode": "deep"}
        )
        assert response.status_code == 202, response.text
        deep = core.ask_service.run_store.get_run(response.json()["run_id"])
        assert deep["lifecycle_status"] == "completed" and deep["citations"], deep
        task, fact, artifact, page = _vertical(core, "real-app")
        exported = core.research_knowledge.export_topic_page(
            task,
            ExportTopicPageRequest(
                command_id="app-export",
                page_revision_id=page["page_revision_id"],
                export_format="markdown",
            ),
            principal_id=core.context.user_id,
        )
        assert exported["status"] == "succeeded"
        assert (
            core.paths.content_dir / "knowledge-exports" / exported["relative_path"]
        ).is_file()
        assessed = _assess(
            core, task, suffix="app", query=fact["claim"], aspects=[fact["claim"]]
        )
        outcome = core.research_knowledge.proceed_artifact_route(
            task,
            assessed["route_id"],
            ProceedArtifactRouteRequest(
                command_id="app-route",
                action="confirm",
                expected_version=1,
                route="direct_reuse",
            ),
            principal_id=core.context.user_id,
        )
        assert (
            outcome["outcome_artifact_revision_id"] == artifact["artifact_revision_id"]
        )
        draft = core.knowledge_drafts.save(
            SaveKnowledgeDraftRequest(
                command_id="app-draft", source_kind="ask_run", source_id=fast_id
            )
        )
        assert (
            core.knowledge_drafts.get(draft["draft_id"])["draft"]["draft_id"]
            == draft["draft_id"]
        )
        assert (
            core.research_knowledge.db is core.db
            and core.knowledge_drafts.db is core.db
        )
    assert core.pg._pool.closed


def test_real_cli_owns_pool_on_success_and_failure(
    application_target, app_paths, monkeypatch, capsys
):
    import shiliu.cli as cli

    created = []

    def factory():
        core = create_core(application_target[0], app_paths)
        created.append(core)
        return core

    monkeypatch.setattr(cli, "Application", factory)
    assert cli.main(["retrieval", "stats"]) == 0
    assert created[-1].pg._pool.closed
    assert "metadata_count" in capsys.readouterr().out
    original = factory

    def failing_factory():
        core = original()

        def fail():
            raise RuntimeError("synthetic command failure")

        core.retrieval.statistics = fail
        return core

    monkeypatch.setattr(cli, "Application", failing_factory)
    with pytest.raises(RuntimeError, match="command failure"):
        cli.main(["retrieval", "stats"])
    assert created[-1].pg._pool.closed


def test_health_unavailable_is_503_not_ready_or_empty(
    application_target, app_paths, monkeypatch
):
    from fastapi.testclient import TestClient
    from shiliu.web import create_web_app
    from shiliu.storage.errors import StorageError

    core = create_core(application_target[0], app_paths)
    with TestClient(create_web_app(core, background_tasks=False)) as client:
        assert client.get("/api/health").json()["ok"]

        def fail():
            raise StorageError("pool_timeout")

        monkeypatch.setattr(core, "health", fail)
        response = client.get("/api/health")
        assert (
            response.status_code == 503
            and response.json()["code"] == "storage_unavailable"
        )


def test_started_application_assistant_tools_memory_wiki_and_clean_exit(
    application_target, app_paths
):
    import json, time
    from fastapi.testclient import TestClient
    from shiliu.web import create_web_app
    from shiliu.assistant.provider import (
        OpenAICompatibleAssistantProvider,
        ModelTurn,
        NativeToolCall,
    )
    from shiliu.assistant.provider_request import EndpointCapabilities

    class Context:
        tools = {}

        async def connect(self):
            pass

        async def close(self):
            self.closed = True

    context = Context()

    class Provider(OpenAICompatibleAssistantProvider):
        calls = 0

        def send_prepared(self, request, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return ModelTurn(
                    text="",
                    tool_calls=[
                        NativeToolCall(
                            "memory",
                            "memory_save",
                            {
                                "text": "用户喜欢简短的中文回答",
                                "subject_key": "answer-style",
                                "kind": "preference",
                                "scope_kind": "user",
                            },
                        )
                    ],
                    finish_reason="tool_calls",
                    usage={"input_tokens": 3},
                )
            if self.calls == 2:
                return ModelTurn(
                    text="",
                    tool_calls=[
                        NativeToolCall(
                            "wiki",
                            "knowledge_save_discussion",
                            {
                                "topics": [
                                    {
                                        "title": "事务边界",
                                        "purpose": "保存讨论结论",
                                        "blocks": [
                                            {
                                                "role": "analysis",
                                                "heading": "事务边界",
                                                "markdown": "模型编码应在事务之外，发布前重新校验版本。",
                                            }
                                        ],
                                    }
                                ]
                            },
                        )
                    ],
                    finish_reason="tool_calls",
                    usage={"input_tokens": 4},
                )
            return ModelTurn(
                text="已保存偏好和讨论结论。",
                tool_calls=[],
                finish_reason="stop",
                usage={"input_tokens": 5},
            )

    provider = Provider(
        base_url="https://synthetic.invalid/v1",
        api_key="synthetic",
        model="synthetic",
        capabilities=EndpointCapabilities(
            "https://synthetic.invalid/v1",
            "synthetic",
            1048576,
            65536,
            4096,
            True,
            "offline fixture",
        ),
    )
    core = create_core(
        application_target[0],
        app_paths,
        config=AppConfig(
            content_dir=str(app_paths.content_dir), assistant_enabled=True
        ),
        assistant_provider_factory=lambda: provider,
        context7=context,
    )
    wiki_errors = []
    original_save = core.assistant_runtime.wiki.save_discussion_topics

    def save(**kwargs):
        try:
            return original_save(**kwargs)
        except Exception as error:
            wiki_errors.append((type(error).__name__, str(error)))
            raise

    core.assistant_runtime.wiki.save_discussion_topics = save
    with TestClient(create_web_app(core, background_tasks=False)) as client:
        response = client.post("/api/assistant/spaces", json={"name": "app-graph"})
        assert response.status_code == 201, response.text
        space = response.json()["space"]
        thread = client.post(
            "/api/assistant/threads", json={"space_id": space["id"]}
        ).json()["thread"]
        response = client.post(
            f"/api/assistant/threads/{thread['id']}/runs",
            json={
                "input": "请记住我喜欢简短的中文回答。请保存讨论结论：模型编码应在事务之外，发布前重新校验版本。",
                "request_id": "app-tools",
            },
        )
        assert response.status_code == 202, response.text
        run = response.json()["run"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            current = core.assistant_runtime.store.get_run(run["id"])
            if current["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.05)
        assert current["status"] == "completed", current.get("last_error_message")
        assert provider.calls == 3
        for call in ["memory", "wiki"]:
            outcome = core.assistant_runtime.store.resolve_run_result(
                f"run-result:{run['id']}:{call}",
                current_thread_id=thread["id"],
                current_scope_version=1,
            )
            assert outcome["result"]["status"] == "ok", (wiki_errors, outcome)
        assert core.assistant_runtime.wiki.list_pages(space_id=space["id"])
        response = client.get(f"/api/assistant/runs/{run['id']}/stream")
        assert response.status_code == 200
        snapshot = json.loads(response.text.removeprefix("data: ").strip())
        assert (
            snapshot["run"]["status"] == "completed"
            and snapshot["run"]["id"] == run["id"]
        )
        assert "\nid:" not in response.text
        assert core.assistant_runtime.store.db is core.db
    assert (
        core.pg._pool.closed
        and core.assistant_runtime._thread is None
        and context.closed
    )


def test_close_drains_registered_inflight_worker_before_pool(
    application_target, app_paths
):
    import threading, time

    core = create_core(application_target[0], app_paths)
    core.start(background_tasks=False)
    entered = threading.Event()
    release = threading.Event()
    closed = threading.Event()

    def work():
        entered.set()
        release.wait(3)
        assert not core.pg._pool.closed
        assert core.db.list_sources() == []

    worker = threading.Thread(target=work, name="synthetic-drain")
    core.start_worker(worker)
    assert entered.wait(1)

    def close():
        core.close()
        closed.set()

    closer = threading.Thread(target=close)
    closer.start()
    try:
        deadline = time.monotonic() + 1
        while not core._closing and time.monotonic() < deadline:
            time.sleep(0.01)
        assert core._closing and not core.pg._pool.closed
        with pytest.raises(RuntimeError, match="stopping"):
            core.start_worker(threading.Thread())
    finally:
        release.set()
        worker.join(3)
        closer.join(3)
    assert closed.is_set() and core.pg._pool.closed


def test_direct_deep_shutdown_tracks_owned_execution_and_preserves_interrupt(
    application_target, app_paths
):
    import threading, time
    from concurrent.futures import ThreadPoolExecutor
    from test_v4_fast_ask_api import _Provider
    from shiliu.ask.contracts import AskRequest

    entered = threading.Event()
    release = threading.Event()
    closed = threading.Event()

    class Blocking(_Provider):
        def generate_structured(self, **kwargs):
            entered.set()
            assert release.wait(5)
            return super().generate_structured(**kwargs)

    core = create_core(
        application_target[0], app_paths, provider_factory=lambda role: Blocking()
    )
    ask = core.ask_service
    with ThreadPoolExecutor(max_workers=2) as executor:
        result = executor.submit(
            ask.ask, AskRequest(query="synthetic deep shutdown", mode="deep")
        )
        assert entered.wait(2)
        with ask._owned_condition:
            run_id = next(iter(ask._executing_runs))

        def close():
            core.close()
            closed.set()

        closing = executor.submit(close)
        try:
            deadline = time.monotonic() + 2
            while (
                ask.run_store.get_run(run_id)["lifecycle_status"] == "running"
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            assert ask.run_store.get_run(run_id)["termination_reason"] == "interrupted"
            assert not core.pg._pool.closed
            with pytest.raises(RuntimeError, match="stopping"):
                ask.start_run(AskRequest(query="later", mode="fast"))
        finally:
            release.set()
        try:
            result.result(timeout=5)
        except Exception:
            pass  # late graph failure cannot overwrite the interrupted durable Run
        closing.result(timeout=5)
    assert closed.is_set() and core.pg._pool.closed


def test_second_owner_application_composes_own_assistant_without_local_operator_fallback(
    application_target, app_paths
):
    from shiliu.storage.scope import ResourceContext

    core = create_core(application_target[0], app_paths)
    with core.db.connect(guard=True) as c:
        c.execute(
            "INSERT INTO users(id,display_name,created_at) VALUES('app-second','synthetic',clock_timestamp())"
        )
        c.execute(
            "INSERT INTO workspaces(id,kind,owner_user_id,created_at) VALUES('personal:app-second','personal','app-second',clock_timestamp())"
        )
        c.execute(
            "INSERT INTO workspace_guards(workspace_id) VALUES('personal:app-second')"
        )
    core.close()

    class Offline:
        async def connect(self):
            raise RuntimeError("offline fixture")

    second = Application(
        app_paths,
        config=AppConfig(
            content_dir=str(app_paths.content_dir), assistant_enabled=True
        ),
        postgres_config=application_target[0],
        context=ResourceContext("personal:app-second", "app-second"),
        embedding_provider=FixedProvider(),
        adapter=object(),
        context7=Offline(),
        assistant_provider_factory=lambda: None,
    )
    try:
        second.start(background_tasks=False)
        assert second.assistant_runtime.memories.principal_id == "app-second"
        assert second.assistant_runtime.wiki.principal_id == "app-second"
        space = second.assistant_runtime.store.create_space(name="private-second")
        assert space["principal_id"] == "app-second"
    finally:
        second.close()
    assert second.pg._pool.closed


def test_application_research_stop_drains_provider_and_supervisor_before_pool(
    application_target, app_paths
):
    import threading, time
    from concurrent.futures import ThreadPoolExecutor
    from shiliu.research.product_contracts import CreateProductResearchRequest

    entered = threading.Event()
    release = threading.Event()
    core = create_core(
        application_target[0],
        app_paths,
        provider_availability=lambda: {
            "available": True,
            "reason": "local blocking fake",
        },
    )

    class Orchestrator:
        _run_lock = object()

        def run_to_boundary(self, task_id, **kwargs):
            entered.set()
            assert release.wait(5)
            with core.db.connect(read_only=True) as c:
                assert c.execute("SELECT 1 AS n").fetchone()["n"] == 1
            return {"boundary": "synthetic"}

    core._research_provider_orchestrator = Orchestrator()
    core.research_provider_product.create_provider_task(
        CreateProductResearchRequest(
            command_id="app-recovery-drain",
            objective="synthetic drain",
            run_immediately=True,
        )
    )
    core.start(background_tasks=True)
    try:
        assert entered.wait(3)
        with ThreadPoolExecutor(max_workers=1) as executor:
            closing = executor.submit(core.close)
            try:
                deadline = time.monotonic() + 2
                while not core._closing and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert core._closing and not core.pg._pool.closed
                assert core.research_recovery._thread.is_alive()
            finally:
                release.set()
            closing.result(timeout=5)
        assert core.pg._pool.closed and not core.research_recovery._thread.is_alive()
        assert core.research_recovery.run_once() is None
    finally:
        release.set()
        core.close()
