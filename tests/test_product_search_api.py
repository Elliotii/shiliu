from __future__ import annotations

from dataclasses import replace
import json

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.cli import build_parser
from shiliu.domain import SubtitleSegment
from shiliu.retrieval.dense import DenseIndexNotReadyError
from shiliu.retrieval.product_search import ProductSearchRequest
from shiliu.web import create_web_app
from tests.test_search_orchestration import (
    FakeHybrid,
    FakeRetriever,
    dense_result,
    hybrid_result,
    lexical_result,
    orchestrator,
)


def make_client(app_paths, *, lexical_results=(), dense=None, hybrid=None):
    core = Application(app_paths)
    for index in range(1, 5):
        core.db.create_video(f"BV{index:010d}", f"Canonical {index}", f"UP {index}", duration_seconds=300)
    lexical = FakeRetriever(lexical_results or [lexical_result()])
    search, lexical, dense_value, hybrid_value = orchestrator(
        app_paths, lexical=lexical, dense=dense, hybrid=hybrid
    )
    core._search_orchestrator = search
    return TestClient(create_web_app(core)), core, lexical, dense_value, hybrid_value


def chunk(unit_id, video_id, start, end, score=2.0):
    return replace(
        lexical_result(unit_id=unit_id, unit_type="transcript_chunk", score=score),
        video_id=video_id, source_id=f"BV{video_id:010d}",
        start_time=start, end_time=end, chunk_id=unit_id,
    )


def test_product_api_groups_same_video_and_combined_trace(app_paths) -> None:
    web, _, _, _, _ = make_client(
        app_paths,
        lexical_results=[chunk("c1", 1, 0, 10), chunk("c2", 1, 10, 20), chunk("c3", 2, 0, 5)],
    )
    response = web.post("/api/search", json={"query": "OpenAI", "result_limit": 10})
    body = response.json()
    assert response.status_code == 200 and body["ok"]
    assert body["raw_hit_count"] == 3 and body["unique_video_count"] == 2
    assert body["duplicate_occupancy_count"] == 1
    assert body["returned_group_count"] == 2
    assert body["results"][0]["matched_unit_count"] == 2
    assert len(body["results"][0]["windows"]) == 1
    trace = web.get(f"/api/search/traces/{body['trace_id']}").json()
    assert trace["raw_trace"]["status"] == "success"
    assert trace["presentation"]["status"] == "success"
    assert trace["presentation"]["trace_id"] == body["trace_id"]


def test_omitted_product_mode_defaults_to_auto_and_persists_provenance(app_paths) -> None:
    web, _, lexical, dense, hybrid = make_client(app_paths)
    body = web.post("/api/search", json={"query": "MCP"}).json()
    plan = body["plan"]
    assert body["ok"] and body["executed_mode"] == "lexical"
    assert plan["requested_mode"] is None
    assert plan["resolved_requested_mode"] == "auto"
    assert plan["default_applied"] is True
    assert plan["configured_default_mode"] == "auto"
    assert plan["router_invoked"] is True
    assert plan["router_decision"] == plan["effective_mode"] == "lexical"
    assert plan["embedding_invoked"] is False
    assert lexical.calls and not dense.calls and not hybrid.calls
    presentation = web.get(f"/api/search/traces/{body['trace_id']}").json()["presentation"]
    assert presentation["product_default_wiring_version"] == "v3-product-search-default-auto-v1"
    assert presentation["requested_mode"] is None and presentation["default_applied"] is True
    assert presentation["router_invoked"] is True
    assert presentation["router_decision"] == presentation["effective_mode"] == "lexical"


@pytest.mark.parametrize("mode", ["lexical", "dense", "hybrid"])
def test_explicit_product_modes_bypass_auto_router(app_paths, mode) -> None:
    web, _, _, _, _ = make_client(app_paths)
    body = web.post("/api/search", json={"query": "MCP", "mode": mode}).json()
    plan = body["plan"]
    assert body["ok"] and body["executed_mode"] == mode
    assert plan["requested_mode"] == mode and plan["default_applied"] is False
    assert plan["router_invoked"] is False and plan["effective_mode"] == mode
    assert plan["router_decision"] is None and plan["router_reason_codes"] == []


def test_explicit_auto_invokes_router_and_records_hybrid_execution(app_paths) -> None:
    web, _, _, _, hybrid = make_client(app_paths)
    body = web.post(
        "/api/search",
        json={"query": "工具调用失败后如何继续", "mode": "auto"},
    ).json()
    plan = body["plan"]
    assert body["ok"] and hybrid.calls
    assert plan["requested_mode"] == "auto" and plan["default_applied"] is False
    assert plan["router_invoked"] is True
    assert plan["router_decision"] == plan["effective_mode"] == "hybrid"
    assert plan["embedding_invoked"] is True


def test_raw_only_trace_keeps_compatibility_and_presentation_null(app_paths) -> None:
    web, _, _, _, _ = make_client(app_paths)
    body = web.post("/api/search/raw", json={"query": "MCP"}).json()
    trace = web.get(f"/api/search/traces/{body['trace_id']}").json()
    assert trace["trace"]["status"] == "success"
    assert trace["raw_trace"] == trace["trace"]
    assert trace["presentation"] is None


def test_internal_overfetch_result_and_window_limits(app_paths) -> None:
    results = [chunk(f"c{i}", i + 1, 100 * i, 100 * i + 5) for i in range(4)]
    web, _, lexical, _, _ = make_client(app_paths, lexical_results=results)
    body = web.post(
        "/api/search",
        json={"query": "MCP", "result_limit": 2, "max_windows_per_video": 1},
    ).json()
    assert body["raw_top_k"] == 50 and body["returned_group_count"] == 2
    assert lexical.calls[0][1]["top_k"] == 50


def test_max_windows_additional_count(app_paths) -> None:
    web, _, _, _, _ = make_client(
        app_paths,
        lexical_results=[chunk("a", 1, 0, 5), chunk("b", 1, 100, 105), chunk("c", 1, 200, 205)],
    )
    body = web.post(
        "/api/search",
        json={"query": "MCP", "max_windows_per_video": 2},
    ).json()
    group = body["results"][0]
    assert group["total_window_count"] == 3
    assert len(group["windows"]) == 2 and group["additional_window_count"] == 1


def test_scope_video_has_no_windows_and_filters_reach_raw_retrieval(app_paths) -> None:
    web, _, lexical, _, _ = make_client(app_paths, lexical_results=[lexical_result()])
    body = web.post(
        "/api/search",
        json={
            "query": "MCP", "scope": "video",
            "filters": {"folder_id": 7, "reading_state": "read", "ignored": True},
        },
    ).json()
    assert body["results"][0]["windows"] == []
    kwargs = lexical.calls[0][1]
    assert kwargs["level"] == "video" and kwargs["filters"].folder_id == 7
    assert kwargs["include_ignored"] is True
    assert body["plan"]["default_applied"] is True
    assert body["plan"]["router_invoked"] is True


def test_api_preserves_exact_uploader_and_adds_contains_filter(app_paths) -> None:
    web, _, lexical, _, _ = make_client(
        app_paths, lexical_results=[lexical_result()]
    )
    exact = web.post(
        "/api/search",
        json={"query": "MCP", "filters": {"uploader": "Alice Studio"}},
    )
    contains = web.post(
        "/api/search",
        json={"query": "MCP", "filters": {"uploader_contains": "alice"}},
    )

    assert exact.status_code == 200 and contains.status_code == 200
    assert lexical.calls[-2][1]["filters"].uploader == "Alice Studio"
    assert lexical.calls[-2][1]["filters"].uploader_contains is None
    assert lexical.calls[-1][1]["filters"].uploader is None
    assert lexical.calls[-1][1]["filters"].uploader_contains == "alice"


def test_unused_uploader_contains_preserves_frozen_request_shape() -> None:
    legacy = {
        "query": "MemoryOS",
        "mode": "lexical",
        "scope": "all",
        "result_limit": 10,
        "max_windows_per_video": 2,
        "filters": {
            "source_db_id": None,
            "folder_id": None,
            "favorite_time_from": None,
            "favorite_time_to": None,
            "reading_state": None,
            "marked": None,
            "uploader": None,
            "archived": None,
            "ignored": False,
        },
    }
    assert ProductSearchRequest.model_validate(legacy).model_dump(mode="json") == legacy

    current = ProductSearchRequest.model_validate(
        {**legacy, "filters": {**legacy["filters"], "uploader_contains": " alice "}}
    ).model_dump(mode="json")
    assert current["filters"]["uploader_contains"] == "alice"


def test_semantic_product_search_uses_chunk_fallback(app_paths) -> None:
    value = replace(
        hybrid_result(), video_id=1, source_id="BV0000000001",
        unit_type="transcript_chunk", chunk_id="h", start_time=42, end_time=50,
    )
    web, _, _, _, _ = make_client(app_paths, hybrid=FakeHybrid([value]))
    body = web.post(
        "/api/search",
        json={"query": "怎样让模型在工具调用失败后换一种办法继续完成任务", "mode": "auto"},
    ).json()
    window = body["results"][0]["windows"][0]
    assert body["plan"]["query_type"] == "semantic_question"
    assert window["jump_time"] == 42 and window["jump_source"] == "chunk_start_fallback"


def test_raw_search_error_propagates_structured_status(app_paths) -> None:
    web, _, _, _, _ = make_client(
        app_paths, dense=FakeRetriever(error=DenseIndexNotReadyError("not ready"))
    )
    response = web.post("/api/search", json={"query": "MCP", "mode": "dense"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dense_not_ready"


def test_partial_presentation_trace_failure_does_not_fail_search(app_paths, monkeypatch) -> None:
    web, core, _, _, _ = make_client(app_paths)
    service = core.product_search
    monkeypatch.setattr(
        service, "_persist_presentation",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("trace down")),
    )
    response = web.post("/api/search", json={"query": "MCP"})
    body = response.json()
    assert response.status_code == 200 and body["ok"]
    assert body["presentation_trace_persisted"] is False
    assert body["presentation_trace_error"]["code"] == "presentation_trace_persistence_failed"


def test_presentation_trace_summary_contains_no_body_text(app_paths) -> None:
    web, core, _, _, _ = make_client(app_paths, lexical_results=[chunk("c", 1, 0, 5)])
    body = web.post("/api/search", json={"query": "MCP"}).json()
    trace = core.product_search.get_presentation(body["trace_id"])
    serialized = json.dumps(trace["group_summary"], ensure_ascii=False)
    assert "excerpt" not in serialized and "summary" not in serialized
    core.product_search.initialize_schema()


def test_product_request_validation_and_cli_grouped_flags(app_paths) -> None:
    web, _, _, _, _ = make_client(app_paths)
    assert web.post("/api/search", json={"query": "MCP", "result_limit": 21}).status_code == 422
    args = build_parser().parse_args(
        ["retrieval", "search", "MCP", "--grouped", "--result-limit", "4", "--max-windows", "3"]
    )
    assert args.grouped and args.result_limit == 4 and args.max_windows == 3


def test_direct_product_request_defaults_to_auto() -> None:
    request = ProductSearchRequest(query="MCP")
    assert request.mode == "auto" and request.default_applied and request.result_limit == 10
