from __future__ import annotations

import json
from pathlib import Path

from shiliu.eval_v3_5.product_query_set_phase_a_r import (
    MAX_CANDIDATE_POOL, SUPPLEMENTAL_SOURCES, build_revised_candidates,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/product_query_set_v1/phase_a_r"


def _audit() -> dict:
    return json.loads((OUT / "product_query_set_phase_a_r_execution.audit.json").read_text(encoding="utf-8"))


def _rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (OUT / name).read_text(encoding="utf-8").splitlines() if line]


def test_pqs_phase_a_r_keeps_phase_a_assets_unchanged() -> None:
    assert (ROOT / "research/v3_5/product_query_set_v1/phase_a/product_query_candidates.discovered.jsonl").is_file()


def test_pqs_phase_a_r_caps_by_declared_deterministic_order() -> None:
    rows = _rows("product_query_candidates.revised.jsonl")
    assert len(rows) == MAX_CANDIDATE_POOL
    assert [row["raw_query"] for row in rows[:8]] == [
        "找出我收藏过的 Harness 相关内容。", "哪些视频讨论了 Agent Memory 的上下文压缩？",
        "最近收藏但还没看的 LangGraph 视频有哪些？", "哪条视频在什么时间点提到了某个 GitHub 项目？",
        *(row["raw_query"] for row in SUPPLEMENTAL_SOURCES),
    ]


def test_pqs_phase_a_r_only_exactly_deduplicates() -> None:
    first = dict(SUPPLEMENTAL_SOURCES[0]); duplicate = dict(first); duplicate["raw_query"] = "  添加公开来源  "
    rows, duplicates, _ = build_revised_candidates([], [first, duplicate])
    assert len(rows) == 1 and duplicates == 1


def test_pqs_phase_a_r_does_not_semantically_delete() -> None:
    first = dict(SUPPLEMENTAL_SOURCES[0]); related = dict(first); related["raw_query"] = "新增公开收藏来源"; related["source_order"] = 99
    rows, duplicates, _ = build_revised_candidates([], [first, related])
    assert len(rows) == 2 and duplicates == 0


def test_pqs_phase_a_r_stays_query_only() -> None:
    audit = _audit()
    assert audit["retrieval_calls"] == audit["embedding_calls"] == 0
    assert audit["video_or_transcript_viewed"] is False and audit["answerability_checked"] is False
    assert audit["system_results_used"] is False and audit["codex_generated_queries"] == 0


def test_pqs_phase_a_r_keeps_human_decisions_blank() -> None:
    assert all(all(value == "" for key, value in row.items() if key != "candidate_query_id") for row in _rows("product_query_decisions.revised.template.jsonl"))
