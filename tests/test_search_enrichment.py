from __future__ import annotations

import json

import pytest

from shiliu.artifacts import ArtifactStore
from shiliu.db import Database
from shiliu.domain import (
    ActionItem,
    EntityItem,
    ImportantChapter,
    SubtitleSegment,
    SummaryResult,
)
from shiliu.retrieval.consolidation import SearchResultConsolidator
from shiliu.retrieval.enrichment import EvidenceEnricher, contains_technical_entity
from tests.test_search_consolidation import hit


def setup_video(app_paths, *, segments=(), chapters=(), duration=300):
    db = Database(app_paths.database)
    db.initialize()
    store = ArtifactStore(app_paths.videos_dir)
    video_id = db.create_video("BV1234567890", "Canonical Title", "Canonical UP", duration_seconds=duration)
    if segments:
        _, raw_text = store.save_raw_subtitle("BV1234567890", list(segments))
        with db.connect() as connection:
            connection.execute(
                "UPDATE videos SET raw_subtitle_path=?,subtitle_source='ai' WHERE id=?",
                (str(raw_text), video_id),
            )
    if chapters:
        _, summary_md = store.save_summary(
            "BV1234567890",
            SummaryResult(
                conclusion="Conclusion", key_points=["a", "b", "c"],
                detailed_notes=["note"], important_chapters=list(chapters),
                entities=[EntityItem(name="x")], action_items=[ActionItem(action="x")],
            ),
        )
        with db.connect() as connection:
            connection.execute("UPDATE videos SET summary_path=? WHERE id=?", (str(summary_md), video_id))
    return db, store, video_id


def enrich(app_paths, query, query_type, segments, *, start=0, end=50, chapters=(), duration=300):
    db, store, video_id = setup_video(
        app_paths, segments=segments, chapters=chapters, duration=duration
    )
    consolidated = SearchResultConsolidator().consolidate(
        (hit("chunk", video_id=video_id, start=start, end=end),)
    )
    result = EvidenceEnricher(db=db, artifacts=store).enrich(
        consolidated.groups, normalized_query=query, query_type=query_type
    )
    return consolidated.groups[0], result


@pytest.mark.parametrize("query", ["OpenAI", "MCP", "C++", "C#", "GPT-5", "Qwen3-Embedding-0.6B"])
def test_exact_phrase_anchor_uses_raw_segment_start(app_paths, query) -> None:
    group, _ = enrich(
        app_paths, query, "exact_entity",
        [SubtitleSegment.model_validate({"from": 12, "to": 14, "content": f"介绍 {query} 工具"})],
    )
    window = group.windows[0]
    assert window.jump_time == 12 and window.anchor_segment_start == 12
    assert window.jump_source == "exact_query_phrase" and window.anchor_confidence == "high"


@pytest.mark.parametrize(
    ("entity", "segment"),
    [
        ("RAG", "storage"), ("RAG", "drag"), ("RAG", "storage engine"),
        ("RAG", "paragraph"),
        ("AI", "train"), ("AI", "detail"), ("AI", "maintain"), ("AI", "email"),
        ("MCP", "XMCPY"), ("MCP", "preMCP2"),
        ("GPT-5", "GPT-50"), ("GPT-5", "XGPT-5"), ("GPT-5", "GPT-5X"),
        ("OpenAI", "MyOpenAIClient"), ("OpenAI", "OpenAI2"),
        ("Qwen3-Embedding-0.6B", "XQwen3-Embedding-0.6B"),
        ("Qwen3-Embedding-0.6B", "Qwen3-Embedding-0.6B2"),
        ("C#", "ABC#DEF"),
    ],
)
def test_technical_entity_negative_boundaries(entity, segment) -> None:
    assert not contains_technical_entity(segment, entity)


@pytest.mark.parametrize(
    ("entity", "segment"),
    [
        ("RAG", "RAG"), ("RAG", "RAG，"), ("RAG", "(RAG)"),
        ("RAG", "RAG-based"), ("RAG", "RAG 检索"),
        ("AI", "AI"), ("AI", "AI Agent"), ("AI", "生成式 AI"),
        ("AI", "（AI）"), ("AI", "AI-driven"),
        ("MCP", "MCP"), ("MCP", "MCP Server"), ("MCP", "（MCP）"),
        ("MCP", "MCP-based"),
        ("GPT-5", "GPT-5"), ("GPT-5", "GPT-5 API"), ("GPT-5", "（GPT-5）"),
        ("GPT-5", "GPT-5-based"),
        ("C++", "C++"), ("C++", "C++ 项目"), ("C++", "（C++）"),
        ("C++", "C++20"),
        ("C#", "C#"), ("C#", "C# 开发"), ("C#", "（C#）"),
        ("Qwen3-Embedding-0.6B", "Qwen3-Embedding-0.6B"),
        ("Qwen3-Embedding-0.6B", "Qwen3-Embedding-0.6B 模型"),
        ("Qwen3-Embedding-0.6B", "（Qwen3-Embedding-0.6B）"),
        (".NET", ".NET"), (".NET", ".NET Core"), (".NET", "ASP.NET"),
    ],
)
def test_technical_entity_positive_boundaries(entity, segment) -> None:
    assert contains_technical_entity(segment, entity)


@pytest.mark.parametrize(
    ("query", "contents"),
    [
        ("RAG", ["storage", "drag", "storage engine", "paragraph"]),
        ("AI", ["train", "detail", "maintain", "email"]),
        ("MCP", ["XMCPY", "preMCP2"]),
        ("GPT-5", ["GPT-50", "XGPT-5", "GPT-5X"]),
        ("OpenAI", ["MyOpenAIClient", "OpenAI2"]),
    ],
)
def test_exact_entity_substrings_never_create_high_confidence_anchor(
    app_paths, query, contents
) -> None:
    segments = [
        SubtitleSegment.model_validate({"from": index + 1, "to": index + 2, "content": value})
        for index, value in enumerate(contents)
    ]
    group, _ = enrich(app_paths, query, "exact_entity", segments, start=0, end=20)
    window = group.windows[0]
    assert window.jump_source == "chunk_start_fallback"
    assert window.anchor_confidence == "fallback"


def test_exact_entity_skips_substring_and_selects_real_boundary(app_paths) -> None:
    group, _ = enrich(
        app_paths, "RAG", "exact_entity",
        [
            SubtitleSegment.model_validate({"from": 3, "to": 4, "content": "storage engine"}),
            SubtitleSegment.model_validate({"from": 9, "to": 10, "content": "这里介绍 RAG 检索"}),
        ],
    )
    window = group.windows[0]
    assert window.jump_time == 9
    assert window.jump_source == "exact_query_phrase" and window.anchor_confidence == "high"


def test_mixed_entity_priority_two_rejects_embedded_ascii_term(app_paths) -> None:
    group, _ = enrich(
        app_paths, "MCP 工作方式", "mixed_entity",
        [
            SubtitleSegment.model_validate({"from": 2, "to": 3, "content": "XMCPY protocol"}),
            SubtitleSegment.model_validate({"from": 8, "to": 9, "content": "MCP 的运行机制"}),
        ],
    )
    window = group.windows[0]
    assert window.jump_time == 8
    assert window.jump_source == "exact_entity_term" and window.anchor_confidence == "high"


def test_mixed_full_phrase_skips_embedded_entity_and_selects_real_phrase(app_paths) -> None:
    group, _ = enrich(
        app_paths, "MCP 协议", "mixed_entity",
        [
            SubtitleSegment.model_validate({"from": 2, "to": 3, "content": "XMCPY protocol"}),
            SubtitleSegment.model_validate({"from": 12, "to": 13, "content": "MCP 协议的工作方式"}),
        ],
    )
    assert group.windows[0].jump_time == 12
    assert group.windows[0].jump_source == "exact_query_phrase"


def test_mixed_full_phrase_cannot_hide_embedded_ascii_entity(app_paths) -> None:
    group, _ = enrich(
        app_paths, "MCP 协议", "mixed_entity",
        [SubtitleSegment.model_validate({"from": 2, "to": 3, "content": "XMCP 协议"})],
    )
    window = group.windows[0]
    assert window.jump_source != "exact_query_phrase"
    assert window.anchor_confidence != "high"


def test_chinese_phrase_matching_semantics_are_unchanged(app_paths) -> None:
    group, _ = enrich(
        app_paths, "上下文压缩", "keyword_phrase",
        [SubtitleSegment.model_validate({"from": 7, "to": 8, "content": "这里讨论上下文压缩方法"})],
    )
    window = group.windows[0]
    assert window.jump_time == 7 and window.jump_source == "exact_query_phrase"
    assert window.anchor_confidence == "high"


def test_nfkc_and_case_insensitive_phrase_match(app_paths) -> None:
    group, _ = enrich(
        app_paths, "ＯｐｅｎＡＩ", "exact_entity",
        [SubtitleSegment.model_validate({"from": 8, "to": 9, "content": "openai API"})],
    )
    assert group.windows[0].jump_time == 8


def test_mixed_query_prefers_ascii_entity_when_full_phrase_absent(app_paths) -> None:
    group, _ = enrich(
        app_paths, "OpenAI 接口调用", "mixed_entity",
        [SubtitleSegment.model_validate({"from": 20, "to": 21, "content": "这里介绍 OpenAI 的能力"})],
    )
    window = group.windows[0]
    assert window.jump_source == "exact_entity_term"
    assert "OpenAI" in window.matched_terms


def test_keyword_coverage_and_tie_break(app_paths) -> None:
    group, _ = enrich(
        app_paths, "检索 模型 证据", "keyword_phrase",
        [
            SubtitleSegment.model_validate({"from": 5, "to": 6, "content": "检索与证据"}),
            SubtitleSegment.model_validate({"from": 9, "to": 10, "content": "模型、检索与证据，模型"}),
        ],
    )
    window = group.windows[0]
    assert window.jump_time == 9 and window.jump_source == "keyword_overlap"
    assert len(window.matched_terms) == 3


def test_anchor_only_searches_current_window(app_paths) -> None:
    group, _ = enrich(
        app_paths, "OpenAI", "exact_entity",
        [
            SubtitleSegment.model_validate({"from": 10, "to": 11, "content": "窗口内无目标"}),
            SubtitleSegment.model_validate({"from": 100, "to": 101, "content": "OpenAI"}),
        ],
        start=0, end=20,
    )
    assert group.windows[0].jump_source == "chunk_start_fallback"
    assert group.windows[0].jump_time == 0


def test_semantic_question_always_uses_chunk_start(app_paths) -> None:
    group, _ = enrich(
        app_paths, "怎样让模型失败后继续", "semantic_question",
        [SubtitleSegment.model_validate({"from": 11, "to": 12, "content": "怎样让模型失败后继续"})],
        start=10, end=20,
    )
    window = group.windows[0]
    assert window.jump_time == 10 and window.jump_source == "chunk_start_fallback"
    assert window.anchor_segment_start is None


def test_missing_and_malformed_subtitle_fall_back(app_paths) -> None:
    db, store, video_id = setup_video(app_paths)
    directory = store.video_dir("BV1234567890")
    raw_text = directory / "subtitle-raw.txt"
    raw_text.write_text("", encoding="utf-8")
    (directory / "subtitle-raw.json").write_text("{bad", encoding="utf-8")
    with db.connect() as connection:
        connection.execute("UPDATE videos SET raw_subtitle_path=? WHERE id=?", (str(raw_text), video_id))
    groups = SearchResultConsolidator().consolidate((hit("chunk", video_id=video_id),)).groups
    result = EvidenceEnricher(db=db, artifacts=store).enrich(
        groups, normalized_query="OpenAI", query_type="exact_entity"
    )
    assert groups[0].windows[0].jump_source == "chunk_start_fallback"
    assert result.warnings[0]["code"] == "subtitle_unavailable"


def test_chapters_sort_deduplicate_derive_bounds_and_do_not_change_jump(app_paths) -> None:
    chapters = [
        ImportantChapter(title="Late", start_seconds=100, summary="late"),
        ImportantChapter(title="Early", start_seconds=0, summary="early"),
        ImportantChapter(title="Duplicate", start_seconds=100, summary="duplicate"),
    ]
    group, result = enrich(
        app_paths, "OpenAI", "exact_entity",
        [SubtitleSegment.model_validate({"from": 120, "to": 121, "content": "OpenAI"})],
        start=110, end=130, chapters=chapters, duration=200,
    )
    window = group.windows[0]
    assert window.jump_time == 120
    assert window.chapter["title"] == "Late"
    assert window.chapter["start_time"] == 100
    assert window.chapter["derived_end_time"] == 200
    assert window.chapter["boundary_type"] == "derived_from_video_duration"
    assert result.chapter_enriched_count == 1


def test_last_chapter_open_ended_without_duration(app_paths) -> None:
    group, _ = enrich(
        app_paths, "OpenAI", "exact_entity",
        [SubtitleSegment.model_validate({"from": 20, "to": 21, "content": "OpenAI"})],
        chapters=[ImportantChapter(title="Only", start_seconds=0, summary="x")], duration=0,
    )
    assert group.windows[0].chapter["derived_end_time"] is None
    assert group.windows[0].chapter["boundary_type"] == "open_ended"


def test_malformed_summary_is_partial_warning_and_chapter_null(app_paths) -> None:
    db, store, video_id = setup_video(
        app_paths,
        segments=[SubtitleSegment.model_validate({"from": 1, "to": 2, "content": "OpenAI"})],
    )
    directory = store.video_dir("BV1234567890")
    summary_md = directory / "summary.md"
    summary_md.write_text("x", encoding="utf-8")
    (directory / "summary.json").write_text("[]", encoding="utf-8")
    with db.connect() as connection:
        connection.execute("UPDATE videos SET summary_path=? WHERE id=?", (str(summary_md), video_id))
    groups = SearchResultConsolidator().consolidate((hit("chunk", video_id=video_id),)).groups
    result = EvidenceEnricher(db=db, artifacts=store).enrich(
        groups, normalized_query="OpenAI", query_type="exact_entity"
    )
    assert groups[0].windows[0].chapter is None
    assert any(item["code"] == "summary_malformed" for item in result.warnings)


def test_excerpt_is_bounded(app_paths) -> None:
    group, _ = enrich(
        app_paths, "OpenAI", "exact_entity",
        [SubtitleSegment.model_validate({"from": 1, "to": 2, "content": "OpenAI " + "x" * 500})],
    )
    assert len(group.windows[0].excerpt) <= 300
