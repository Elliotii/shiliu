"""Local trial consumes only allowed projections and preserves old execution."""

import time

from fastapi.testclient import TestClient
import pytest

from shiliu.app import Application
from shiliu.config import AppConfig
from shiliu.w16_trial import (
    paused_provider,
    provider_availability,
    trial_request_allowed,
)
from shiliu.web import create_web_app
from test_application_pg import application_target  # noqa: F401
from test_collection_retrieval import FixedProvider


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/setup/complete"),
        ("GET", "/api/setup/folders"),
        ("POST", "/api/sync"),
        ("POST", "/api/sources/1/sync"),
        ("POST", "/api/videos/1/asr"),
        ("POST", "/api/videos/1/retry"),
        ("POST", "/api/research/product/tasks/old/run"),
        ("POST", "/api/assistant/threads/old/runs"),
        ("POST", "/api/assistant/jobs/old/retry"),
        ("POST", "/api/assistant/wiki/organize"),
    ],
)
def test_trial_external_operations_are_rejected_before_route_dispatch(method, path):
    assert not trial_request_allowed(method, path)


def test_manual_models_only_open_foreground_routes():
    for path in [
        "/api/ask",
        "/api/ask/stream",
        "/api/ask/runs",
        "/api/assistant/threads/new/runs",
        "/api/assistant/runs/new/resume",
    ]:
        assert trial_request_allowed("POST", path, manual_models=True)
        assert not trial_request_allowed("POST", path)
    for path in [
        "/api/sync",
        "/api/setup/test-provider",
        "/api/videos/1/asr",
        "/api/research/product/tasks/old/run",
        "/api/assistant/jobs/old/retry",
    ]:
        assert not trial_request_allowed("POST", path, manual_models=True)


def test_manual_foreground_consumes_only_new_runs(
    application_target, app_paths, monkeypatch
):
    from datetime import datetime, timezone
    from shiliu.assistant.pg_store import PgAssistantRunStore
    from shiliu.assistant.provider import OpenAICompatibleAssistantProvider, ModelTurn
    from shiliu.assistant.dependencies import Context7MCPClient

    def forbidden(*args, **kwargs):
        raise AssertionError("unapproved recovery or external dependency")

    for name in [
        "recover_interrupted_runs",
        "recover_expired_jobs",
        "freeze_legacy_recovery_calls",
    ]:
        monkeypatch.setattr(PgAssistantRunStore, name, forbidden)
    monkeypatch.setattr(Context7MCPClient, "connect", forbidden)

    class Provider(OpenAICompatibleAssistantProvider):
        calls = 0

        def send_prepared(self, request, **kwargs):
            self.calls += 1
            return ModelTurn(
                text="合成前台问答完成。",
                finish_reason="stop",
                usage={"input_tokens": 3, "output_tokens": 2},
            )

    provider = Provider(
        base_url="https://api.deepseek.com/v1",
        api_key="synthetic",
        model="deepseek-v4-flash",
    )
    core = Application(
        app_paths,
        postgres_config=application_target[0],
        config=AppConfig(
            content_dir=str(app_paths.content_dir), assistant_enabled=True
        ),
        embedding_provider=FixedProvider(),
        adapter=object(),
        provider_factory=paused_provider,
        assistant_provider_factory=lambda: provider,
        extraction_provider_factory=forbidden,
        provider_availability=provider_availability,
    )
    store = core.assistant_runtime.store
    space = store.create_space(name="manual-foreground-boundary")
    old_thread = store.create_thread(space["id"])
    old = store.create_run(old_thread["id"], text="old queued", request_id="old")
    boundary = datetime.now(timezone.utc).isoformat()
    try:
        assert store.claim_next_run(created_after=boundary) is None
        with TestClient(
            create_web_app(
                core,
                background_tasks=False,
                local_projections_only=True,
                manual_model_since=boundary,
            )
        ) as client:
            thread = client.post(
                "/api/assistant/threads", json={"space_id": space["id"]}
            ).json()["thread"]
            response = client.post(
                f"/api/assistant/threads/{thread['id']}/runs",
                json={"input": "请回答合成测试", "request_id": "new-manual"},
            )
            assert response.status_code == 202
            current = response.json()["run"]
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                current = store.get_run(current["id"])
                if current["status"] == "completed":
                    break
                time.sleep(0.05)
            assert current["status"] == "completed" and provider.calls == 1
            assert store.get_run(old["id"])["status"] == "queued"
            assert (
                client.post(f"/api/assistant/runs/{old['id']}/resume").status_code
                == 403
            )
            assert client.post("/api/sync").status_code == 403
            assert core._research_recovery is None
            assert core.assistant_runtime.maintenance_paused
            assert core.assistant_runtime.capabilities()["context7"] == "disabled"
            assert all(
                j["status"] == "queued"
                for j in store.list_jobs()
                if j["kind"] == "memory_extract"
            )
    finally:
        core.close()


def test_trial_keeps_history_and_only_claims_local_jobs(
    application_target, app_paths, monkeypatch
):
    from shiliu.ask.persistence import AskRunStore
    from shiliu.assistant.pg_store import PgAssistantRunStore
    from shiliu.assistant.dependencies import Context7MCPClient

    def forbidden(*args, **kwargs):
        raise AssertionError("trial crossed external/recovery boundary")

    import shiliu.app as app_module

    monkeypatch.setattr(app_module, "load_api_key", forbidden)
    monkeypatch.setattr(Context7MCPClient, "connect", forbidden)
    monkeypatch.setattr(PgAssistantRunStore, "recover_interrupted_runs", forbidden)
    monkeypatch.setattr(PgAssistantRunStore, "recover_expired_jobs", forbidden)
    monkeypatch.setattr(PgAssistantRunStore, "claim_next_run", forbidden)
    claims = []
    original = PgAssistantRunStore.claim_job

    def claim(self, **kwargs):
        claims.append(kwargs)
        assert kwargs["kinds"] == {"memory_index", "memory_purge"}
        assert not kwargs["allow_model_jobs"] and not kwargs["allow_maintenance"]
        return original(self, **kwargs)

    monkeypatch.setattr(PgAssistantRunStore, "claim_job", claim)
    core = Application(
        app_paths,
        postgres_config=application_target[0],
        config=AppConfig(
            content_dir=str(app_paths.content_dir), assistant_enabled=True
        ),
        embedding_provider=FixedProvider(),
        adapter=object(),
        provider_factory=paused_provider,
        assistant_provider_factory=paused_provider,
        provider_availability=provider_availability,
    )
    store = AskRunStore(core.db)
    store.start(
        run_id="history-still-running", query="synthetic", mode="deep", filters={}
    )
    memory = core.assistant_runtime.memories.save_explicit(
        text="合成试用边界记忆",
        subject_key="trial-boundary",
        kind="preference",
        scope_kind="user",
        scope_id=None,
        operation_key="trial-boundary-save",
    )
    with core.db.connect() as c:
        model_job = core.assistant_runtime.store.enqueue_job(
            c,
            kind="memory_extract",
            dedupe_key="trial-model-must-stay-queued",
            payload={},
        )
    try:
        with TestClient(
            create_web_app(core, background_tasks=False, local_projections_only=True)
        ) as client:
            for method, path in [
                ("get", "/api/setup/folders"),
                ("post", "/api/sync"),
                ("post", "/api/research/product/tasks/old/run"),
            ]:
                response = getattr(client, method)(path)
                assert response.status_code == 403
                assert response.json()["code"] == "trial_operation_paused"
            assert client.get("/api/health").status_code == 200
            assert core._research_recovery is None
            assert core._projection_thread.is_alive()
            assert core.assistant_runtime.capabilities()["context7"] == "disabled"
            assert client.get("/api/ask/runs/history-still-running").status_code == 200
            assert (
                store.get_run("history-still-running")["lifecycle_status"] == "running"
            )
            deadline = time.monotonic() + 3
            while not claims and time.monotonic() < deadline:
                time.sleep(0.05)
            assert claims
            while time.monotonic() < deadline:
                with core.db.connect(read_only=True) as c:
                    projected = c.execute(
                        "SELECT count(*) AS n FROM memory_embeddings WHERE memory_id=%s",
                        (memory["id"],),
                    ).fetchone()["n"]
                if projected:
                    break
                time.sleep(0.05)
            assert projected == 1
            with core.db.connect(read_only=True) as c:
                job = c.execute(
                    "SELECT status,lease_owner FROM assistant_jobs WHERE id=%s",
                    (model_job,),
                ).fetchone()
            assert job["status"] == "queued" and job["lease_owner"] is None
    finally:
        core.close()
