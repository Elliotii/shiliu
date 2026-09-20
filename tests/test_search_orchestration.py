from __future__ import annotations

from dataclasses import replace

import pytest

from shiliu.artifacts import ArtifactStore
from shiliu.db import Database
from shiliu.retrieval.dense import DenseIndexNotReadyError, DenseIndexRebuildRequiredError
from shiliu.retrieval.hybrid import HybridExecution
from shiliu.retrieval.models import DenseSearchResult, HybridSearchResult, SearchResult
from shiliu.retrieval.orchestrator import SearchExecutionError, SearchOrchestrator
from shiliu.retrieval.planner import SearchFilterRequest, SearchRequest
from shiliu.retrieval.qwen import LocalModelNotReadyError
from shiliu.retrieval.service import RetrievalService


def lexical_result(unit_id="unit:1", unit_type="video", score=2.0):
    return SearchResult(
        unit_id=unit_id, unit_type=unit_type, video_id=1, platform="bilibili",
        source_id="BV1", part=1, title="Title", uploader="Creator", chunk_id=None,
        source_type="ai", start_time=None if unit_type == "video" else 1.0,
        end_time=None if unit_type == "video" else 2.0,
        matched_excerpt="x" * 400, lexical_score=score, retrieval_method="lexical",
        index_version="lex-v1", reading_state="unread", is_marked=False,
        is_ignored=False, archived=False, folders=(),
    )


def dense_result(unit_id="unit:2", score=0.8):
    return DenseSearchResult(
        unit_id=unit_id, unit_type="transcript_chunk", video_id=2,
        platform="bilibili", source_id="BV2", part=1, title="Dense", uploader="UP",
        chunk_id="chunk", source_type="human", start_time=3.0, end_time=4.0,
        matched_excerpt="dense", dense_score=score, retrieval_method="dense",
        index_version="lex-v1", dense_index_version="dense-v1", model_id="qwen",
        projection_version="projection-v1", reading_state="read", is_marked=True,
        is_ignored=False, archived=False, folders=(),
    )


def hybrid_result(unit_id="unit:3", score=0.03):
    return HybridSearchResult(
        unit_id=unit_id, unit_type="video", video_id=3, platform="bilibili",
        source_id="BV3", part=1, title="Hybrid", uploader="UP", chunk_id=None,
        source_type="ai", start_time=None, end_time=None, matched_excerpt="hybrid",
        lexical_score=1.2, dense_score=0.7, lexical_rank=2, dense_rank=1,
        rrf_score=score, retrieval_method="hybrid", lexical_retrieval_method="lexical",
        fusion_version="rrf-v1", index_version="rrf-v1",
        lexical_index_version="lex-v1", dense_index_version="dense-v1",
        model_id="qwen", projection_version="projection-v1", reading_state="unread",
        is_marked=False, is_ignored=False, archived=False, folders=(),
    )


class FakeRetriever:
    def __init__(self, results=(), error=None):
        self.results = list(results)
        self.error = error
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if self.error:
            raise self.error
        return list(self.results)


class FakeHybrid(FakeRetriever):
    def search_with_trace(self, query, **kwargs):
        values = self.search(query, **kwargs)
        return HybridExecution(values, 7, 8, 1.1, 2.2, 0.3)


def orchestrator(app_paths, *, lexical=None, dense=None, hybrid=None):
    db = Database(app_paths.database)
    db.initialize()
    RetrievalService(db=db, artifacts=ArtifactStore(app_paths.videos_dir)).initialize_schema()
    with db.connect() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS retrieval_dense_index_meta(
            index_name TEXT PRIMARY KEY,dense_index_version TEXT,model_id TEXT,
            embedding_dimension INTEGER,embedding_dtype TEXT,normalized INTEGER,
            projection_version TEXT,total_unit_count INTEGER,video_unit_count INTEGER,
            chunk_unit_count INTEGER,built_at TEXT,updated_at TEXT,
            build_duration_seconds REAL,model_revision TEXT,provider_version TEXT,
            embedding_mode TEXT,query_instruction_version TEXT,input_policy_version TEXT)"""
        )
    lexical = lexical or FakeRetriever([lexical_result()])
    dense = dense or FakeRetriever([dense_result()])
    hybrid = hybrid or FakeHybrid([hybrid_result()])
    value = SearchOrchestrator(
        db=db, lexical=lexical, dense_factory=lambda: dense,
        hybrid_factory=lambda: hybrid,
    )
    return value, lexical, dense, hybrid


@pytest.mark.parametrize(
    ("mode", "expected", "unit_id"),
    [("lexical", "lexical", "unit:1"), ("dense", "dense", "unit:2"),
     ("hybrid", "hybrid", "unit:3")],
)
def test_explicit_modes_preserve_retriever_order_and_component_scores(
    app_paths, mode, expected, unit_id
) -> None:
    value, _, _, _ = orchestrator(app_paths)
    response = value.search(SearchRequest(query="MCP", mode=mode))
    assert response.executed_mode == expected and response.raw_hits[0].unit_id == unit_id
    assert response.raw_hits[0].rank == 1 and response.trace_persisted
    assert len(response.raw_hits[0].excerpt) <= 300
    if mode == "hybrid":
        assert response.raw_hits[0].lexical_rank == 2
        assert response.raw_hits[0].dense_rank == 1
        assert response.candidate_counts == {"lexical": 7, "dense": 8}


def test_auto_exact_never_constructs_dense_or_hybrid(app_paths) -> None:
    calls = []
    value, lexical, _, _ = orchestrator(app_paths)
    value._dense_factory = lambda: calls.append("dense")
    value._hybrid_factory = lambda: calls.append("hybrid")
    response = value.search(SearchRequest(query="MCP", mode="auto"))
    assert response.plan.query_type == "exact_entity"
    assert response.executed_mode == "lexical" and calls == []
    assert lexical.calls


@pytest.mark.parametrize(
    ("query", "query_type"),
    [("MCP 协议", "mixed_entity"), ("工具失败后如何继续", "semantic_question"),
     ("上下文压缩", "keyword_phrase")],
)
def test_auto_non_exact_routes_hybrid(app_paths, query, query_type) -> None:
    value, _, _, hybrid = orchestrator(app_paths)
    response = value.search(SearchRequest(query=query, mode="auto"))
    assert response.plan.query_type == query_type
    assert response.plan.planned_mode == response.executed_mode == "hybrid"
    assert hybrid.calls


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (DenseIndexNotReadyError("not ready"), "dense_not_ready"),
        (DenseIndexRebuildRequiredError("rebuild"), "dense_rebuild_required"),
        (LocalModelNotReadyError("local model"), "local_model_not_ready"),
    ],
)
def test_auto_approved_dense_failures_fallback_to_lexical(app_paths, error, reason) -> None:
    value, lexical, _, _ = orchestrator(app_paths, hybrid=FakeHybrid(error=error))
    response = value.search(SearchRequest(query="上下文压缩", mode="auto"))
    assert response.executed_mode == "lexical" and response.fallback
    assert response.fallback_reason == reason and lexical.calls
    trace = value.get_trace(response.trace_id)
    assert trace["fallback"] is True and trace["fallback_reason"] == reason


@pytest.mark.parametrize("mode", ["dense", "hybrid"])
def test_explicit_dense_failure_never_falls_back(app_paths, mode) -> None:
    failing = FakeRetriever(error=DenseIndexNotReadyError("not ready"))
    value, lexical, _, _ = orchestrator(
        app_paths, dense=failing, hybrid=FakeHybrid(error=DenseIndexNotReadyError("not ready"))
    )
    with pytest.raises(SearchExecutionError) as captured:
        value.search(SearchRequest(query="MCP", mode=mode))
    assert captured.value.code == "dense_not_ready"
    assert not lexical.calls and captured.value.trace_persisted


def test_unknown_hybrid_failure_does_not_fallback(app_paths) -> None:
    value, lexical, _, _ = orchestrator(
        app_paths, hybrid=FakeHybrid(error=RuntimeError("unknown"))
    )
    with pytest.raises(SearchExecutionError) as captured:
        value.search(SearchRequest(query="上下文压缩", mode="auto"))
    assert captured.value.code == "retrieval_internal_error" and not lexical.calls


def test_scope_and_filters_are_forwarded_before_top_k(app_paths) -> None:
    value, lexical, _, _ = orchestrator(app_paths)
    request = SearchRequest(
        query="MCP", scope="transcript_chunk", raw_top_k=50,
        filters=SearchFilterRequest(folder_id=2, reading_state="read", ignored=True),
    )
    value.search(request)
    _, kwargs = lexical.calls[0]
    assert kwargs["level"] == "transcript_chunk" and kwargs["top_k"] == 50
    assert kwargs["filters"].folder_id == 2 and kwargs["include_ignored"] is True


def test_trace_is_bounded_contains_no_excerpt_and_lookup_is_structured(app_paths) -> None:
    value, _, _, _ = orchestrator(app_paths)
    response = value.search(SearchRequest(query="MCP"))
    trace = value.get_trace(response.trace_id)
    assert trace["status"] == "success" and trace["raw_hit_count"] == 1
    assert "excerpt" not in trace["raw_hits"][0]
    assert trace["planning_ms"] >= 0 and trace["total_ms"] >= 0
    assert value.get_trace("missing") is None
    value.initialize_schema()


def test_trace_persistence_failure_does_not_fail_successful_search(app_paths, monkeypatch) -> None:
    value, _, _, _ = orchestrator(app_paths)
    monkeypatch.setattr(value, "_persist_trace", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("trace down")))
    response = value.search(SearchRequest(query="MCP"))
    assert not response.trace_persisted
    assert response.trace_error["code"] == "trace_persistence_failed"


def test_error_trace_message_is_bounded(app_paths) -> None:
    value, _, _, _ = orchestrator(
        app_paths, dense=FakeRetriever(error=RuntimeError("x" * 900))
    )
    with pytest.raises(SearchExecutionError):
        value.search(SearchRequest(query="MCP", mode="dense"))
    with value.db.connect() as connection:
        message = connection.execute(
            "SELECT error_message FROM retrieval_search_traces ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
    assert len(message) <= 500
