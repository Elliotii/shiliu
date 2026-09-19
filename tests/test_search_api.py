from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.retrieval.dense import DenseIndexNotReadyError, DenseIndexRebuildRequiredError
from shiliu.retrieval.qwen import LocalModelNotReadyError
from shiliu.web import create_web_app
from tests.test_search_orchestration import FakeHybrid, FakeRetriever, orchestrator


def client(app_paths, *, lexical=None, dense=None, hybrid=None):
    core = Application(app_paths)
    search, lexical, dense, hybrid = orchestrator(
        app_paths, lexical=lexical, dense=dense, hybrid=hybrid
    )
    core._search_orchestrator = search
    return TestClient(create_web_app(core)), search, lexical, dense, hybrid


def test_raw_search_success_and_trace_lookup(app_paths) -> None:
    web, _, _, _, _ = client(app_paths)
    response = web.post("/api/search/raw", json={"query": "MCP"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] and body["executed_mode"] == "lexical"
    assert body["trace_persisted"] and body["raw_hits"][0]["rank"] == 1
    trace = web.get(f"/api/search/traces/{body['trace_id']}")
    assert trace.status_code == 200 and trace.json()["trace"]["status"] == "success"


def test_api_exact_auto_explicit_override_scope_and_filter(app_paths) -> None:
    web, _, lexical, _, _ = client(app_paths)
    exact = web.post("/api/search/raw", json={"query": "MCP", "mode": "auto"})
    assert exact.status_code == 200
    assert exact.json()["plan"]["query_type"] == "exact_entity"
    assert exact.json()["executed_mode"] == "lexical"
    explicit = web.post("/api/search/raw", json={"query": "MCP", "mode": "dense"})
    assert explicit.status_code == 200 and explicit.json()["executed_mode"] == "dense"
    scoped = web.post(
        "/api/search/raw",
        json={
            "query": "MCP", "scope": "transcript_chunk", "raw_top_k": 50,
            "filters": {"folder_id": 7, "reading_state": "read", "ignored": True},
        },
    )
    assert scoped.status_code == 200
    _, kwargs = lexical.calls[-1]
    assert kwargs["level"] == "transcript_chunk" and kwargs["top_k"] == 50
    assert kwargs["filters"].folder_id == 7 and kwargs["include_ignored"]


def test_api_semantic_auto_fallback_is_http_200(app_paths) -> None:
    web, _, _, _, _ = client(
        app_paths, hybrid=FakeHybrid(error=DenseIndexNotReadyError("not ready"))
    )
    response = web.post(
        "/api/search/raw", json={"query": "工具调用失败后如何继续", "mode": "auto"}
    )
    body = response.json()
    assert response.status_code == 200 and body["fallback"]
    assert body["executed_mode"] == "lexical"
    assert body["fallback_reason"] == "dense_not_ready"


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (DenseIndexRebuildRequiredError("rebuild"), 409, "dense_rebuild_required"),
        (DenseIndexNotReadyError("not ready"), 503, "dense_not_ready"),
        (LocalModelNotReadyError("local model"), 503, "local_model_not_ready"),
    ],
)
def test_api_explicit_dense_structured_errors(app_paths, error, status, code) -> None:
    web, _, _, _, _ = client(app_paths, dense=FakeRetriever(error=error))
    response = web.post(
        "/api/search/raw", json={"query": "MCP", "mode": "dense"}
    )
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["trace_persisted"] is True


def test_api_validation_errors_and_unknown_trace(app_paths) -> None:
    web, _, _, _, _ = client(app_paths)
    semantic = web.post("/api/search/raw", json={"query": "   "})
    assert semantic.status_code == 400
    assert semantic.json()["error"]["code"] == "invalid_search_request"
    schema = web.post(
        "/api/search/raw", json={"query": "MCP", "filters": {"creator": "UP"}}
    )
    assert schema.status_code == 422
    assert web.get("/api/search/traces/not-found").status_code == 404
