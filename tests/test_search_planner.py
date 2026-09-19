from __future__ import annotations

import pytest
from pydantic import ValidationError

from shiliu.retrieval.planner import (
    SearchFilterRequest, SearchPlanner, SearchRequest, SearchValidationError,
    classify_query, normalize_query,
)


@pytest.mark.parametrize(
    "query",
    ["MCP", "C++", "C#", "GPT-5", "Qwen3-Embedding-0.6B", "OpenAI Agents SDK"],
)
def test_exact_ascii_entity_boundaries(query) -> None:
    assert classify_query(query) == "exact_entity"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("LangGraph 工作流", "mixed_entity"),
        ("MCP 协议", "mixed_entity"),
        ("怎样让模型在工具调用失败后继续", "semantic_question"),
        ("how to recover after tool failure?", "semantic_question"),
        ("上下文压缩", "keyword_phrase"),
        ("向量数据库", "keyword_phrase"),
    ],
)
def test_deterministic_query_types(query, expected) -> None:
    assert classify_query(query) == expected
    assert classify_query(query) == expected


def test_nfkc_whitespace_and_raw_query_preserved() -> None:
    request = SearchRequest(query="  ＭＣＰ\t协议  ", mode="auto")
    plan = SearchPlanner().plan(request)
    assert plan.raw_query == "  ＭＣＰ\t协议  "
    assert plan.normalized_query == "MCP 协议"
    assert plan.query_type == "mixed_entity"
    assert plan.planned_mode == "hybrid"


@pytest.mark.parametrize("query", ["", "  \t\n  "])
def test_empty_query_rejected_in_planner(query) -> None:
    with pytest.raises(SearchValidationError, match="empty"):
        SearchPlanner().plan(SearchRequest(query=query))


def test_query_length_limit() -> None:
    assert len(normalize_query("x" * 500)) == 500
    with pytest.raises(SearchValidationError, match="500"):
        normalize_query("x" * 501)


def test_auto_routing_and_explicit_override() -> None:
    planner = SearchPlanner()
    exact = planner.plan(SearchRequest(query="MCP", mode="auto"))
    semantic = planner.plan(SearchRequest(query="工具调用失败后如何继续", mode="auto"))
    explicit = planner.plan(SearchRequest(query="MCP", mode="dense"))
    assert (exact.planned_mode, exact.routing_reason, exact.fallback_allowed) == (
        "lexical", "short_ascii_entity", False,
    )
    assert semantic.planned_mode == "hybrid" and semantic.fallback_allowed
    assert explicit.planned_mode == "dense" and explicit.routing_reason == "explicit_mode"


def test_scope_top_k_unknown_filter_and_range_validation() -> None:
    assert SearchRequest(query="MCP", scope="video", raw_top_k=100).scope == "video"
    for payload in (
        {"query": "MCP", "scope": "segment"},
        {"query": "MCP", "raw_top_k": 0},
        {"query": "MCP", "raw_top_k": 101},
        {"query": "MCP", "filters": {"creator": "unknown-field"}},
        {"query": "MCP", "filters": {"reading_state": "later"}},
    ):
        with pytest.raises(ValidationError):
            SearchRequest.model_validate(payload)
    with pytest.raises(ValidationError, match="must not exceed"):
        SearchFilterRequest(favorite_time_from=2, favorite_time_to=1)


def test_filter_mapping_preserves_existing_product_semantics() -> None:
    filters = SearchFilterRequest(
        source_db_id=1, folder_id=2, favorite_time_from=3,
        favorite_time_to=4, reading_state="read", marked=True,
        uploader="  Creator  ", archived=False, ignored=True,
    )
    mapped = filters.retrieval_filters()
    assert mapped.source_db_id == 1 and mapped.folder_id == 2
    assert mapped.is_marked is True and mapped.uploader == "Creator"
    assert filters.ignored is True and filters.active_dict()["ignored"] is True
