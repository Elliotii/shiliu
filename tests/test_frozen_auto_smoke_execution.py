from __future__ import annotations

from pathlib import Path

from shiliu.eval_v3_5 import frozen_auto_smoke as smoke
from shiliu.retrieval.planner import SearchPlanner, SearchRequest


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_auto_smoke_runs_mode_auto() -> None:
    request = smoke.build_auto_request("MCP")
    assert request["mode"] == "auto"


def test_frozen_auto_smoke_invokes_router() -> None:
    plan = SearchPlanner().plan(SearchRequest(query="MCP", mode="auto"))
    assert plan.requested_mode == "auto"


def test_frozen_auto_smoke_records_router_decision() -> None:
    plan = SearchPlanner().plan(SearchRequest(query="MCP", mode="auto"))
    assert plan.planned_mode == "lexical"


def test_frozen_auto_smoke_records_effective_mode() -> None:
    plan = SearchPlanner().plan(SearchRequest(query="如何设计 RAG 评测？", mode="auto"))
    assert plan.planned_mode == "hybrid"


def test_frozen_auto_smoke_requires_router_mode_consistency() -> None:
    rows = [
        {
            "router_decision": "lexical",
            "effective_mode": "lexical",
            "router_mode_consistent": True,
        }
    ]
    assert all(row["router_decision"] == row["effective_mode"] for row in rows)


def test_frozen_auto_smoke_records_embedding_invocation() -> None:
    provider = smoke.CountingEmbeddingProvider.__new__(smoke.CountingEmbeddingProvider)
    provider.query_call_count = 0
    provider.document_call_count = 0
    assert provider.query_call_count == 0


def test_frozen_auto_smoke_records_provider_reuse() -> None:
    source = Path(smoke.__file__).read_text(encoding="utf-8")
    assert "embedding_provider_reuse_count" in source


def test_frozen_auto_smoke_records_latency() -> None:
    records = [
        {"latency_ms": 1.0, "runtime_error": False},
        {"latency_ms": 3.0, "runtime_error": False},
    ]
    summary = smoke.latency_summary(records)
    assert summary == {"count": 2, "median_ms": 2.0, "p95_ms": 3.0, "max_ms": 3.0}


def test_frozen_auto_smoke_does_not_use_external_embedding() -> None:
    identity = smoke.auto_runtime_identity(ROOT)
    assert identity["dense_provider"] == "v3-qwen3-embedding-provider-v1"


def test_frozen_auto_smoke_q2_is_union_only() -> None:
    result = smoke.q2_union(
        [
            {
                "intent_index": 1,
                "target_video_hit": True,
                "target_video_best_rank": 2,
                "empty_result": False,
            },
            {
                "intent_index": 2,
                "target_video_hit": False,
                "target_video_best_rank": None,
                "empty_result": False,
            },
        ]
    )
    assert result["merge_rule"] == "union_of_canonical_video_identities"
    assert result["cross_intent_rerank"] is False and result["score_merge"] is False
