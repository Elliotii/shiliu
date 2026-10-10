from __future__ import annotations

import json
from pathlib import Path

from shiliu.eval_v3_5.product_query_set_phase_a import (
    HUMAN_QUERY_SOURCES, MAX_CANDIDATE_POOL, build_candidates, family_gaps,
    normalize_for_exact_duplicate,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/product_query_set_v1/phase_a"


def _audit() -> dict:
    return json.loads((OUT / "product_query_set_phase_a_execution.audit.json").read_text(encoding="utf-8"))


def _rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (OUT / name).read_text(encoding="utf-8").splitlines() if line]


def test_pqs_phase_a_does_not_run_retrieval() -> None:
    assert _audit()["retrieval_calls"] == _audit()["product_search_calls"] == 0


def test_pqs_phase_a_does_not_call_embedding() -> None:
    assert _audit()["embedding_calls"] == 0


def test_pqs_phase_a_does_not_call_builder() -> None:
    assert _audit()["candidate_builder_calls"] == 0


def test_pqs_phase_a_does_not_call_selector() -> None:
    assert _audit()["selector_calls"] == 0


def test_pqs_phase_a_does_not_call_sufficiency_judge() -> None:
    assert _audit()["sufficiency_judge_calls"] == 0


def test_pqs_phase_a_does_not_access_heldout() -> None:
    assert _audit()["heldout_accessed"] is False


def test_pqs_phase_a_requires_traceable_query_source() -> None:
    broken = dict(HUMAN_QUERY_SOURCES[0]); broken["source_file"] = ""
    try:
        build_candidates([broken])
    except ValueError:
        pass
    else:
        raise AssertionError("untraceable source accepted")


def test_pqs_phase_a_preserves_raw_query() -> None:
    assert _rows("product_query_candidates.discovered.jsonl")[0]["raw_query"] == HUMAN_QUERY_SOURCES[0]["raw_query"]


def test_pqs_phase_a_only_exactly_deduplicates() -> None:
    first = dict(HUMAN_QUERY_SOURCES[0]); duplicate = dict(first); duplicate["raw_query"] = "  " + first["raw_query"] + "  "
    rows, removed = build_candidates([first, duplicate])
    assert len(rows) == 1 and removed == 1


def test_pqs_phase_a_does_not_semantically_delete_queries() -> None:
    a = dict(HUMAN_QUERY_SOURCES[0]); b = dict(a); b["raw_query"] = "如何找到我收藏的 Harness 内容？"
    rows, removed = build_candidates([a, b])
    assert len(rows) == 2 and removed == 0


def test_pqs_phase_a_does_not_generate_queries_from_video_titles() -> None:
    assert _audit()["video_titles_used_to_generate_queries"] is False


def test_pqs_phase_a_does_not_generate_queries_from_gold() -> None:
    assert _audit()["gold_used_to_generate_queries"] is False


def test_pqs_phase_a_does_not_use_system_results_for_selection() -> None:
    assert _audit()["system_results_used_to_select_queries"] is False


def test_pqs_phase_a_marks_answerability_unchecked() -> None:
    assert all(row["answerability_checked"] is False for row in _rows("product_query_candidates.discovered.jsonl"))


def test_pqs_phase_a_marks_retrieval_not_executed() -> None:
    assert all(row["retrieval_executed"] is False for row in _rows("product_query_candidates.discovered.jsonl"))


def test_pqs_phase_a_keeps_human_decisions_blank() -> None:
    assert all(all(value == "" for key, value in row.items() if key != "candidate_query_id") for row in _rows("product_query_decisions.template.jsonl"))


def test_pqs_phase_a_caps_candidate_pool() -> None:
    assert len(_rows("product_query_candidates.discovered.jsonl")) <= MAX_CANDIDATE_POOL


def test_pqs_phase_a_reports_query_family_gaps() -> None:
    assert any(value["shortfall"] for value in family_gaps(_rows("product_query_candidates.discovered.jsonl")).values())


def test_pqs_phase_a_generates_human_authoring_slots_when_under_minimum() -> None:
    from shiliu.eval_v3_5.product_query_set_phase_a import build_phase_a

    temporary_root = ROOT / ".pytest-pqs-phase-a-under-minimum"
    try:
        build_phase_a(temporary_root, HUMAN_QUERY_SOURCES[:1])
        packet = temporary_root / "research/v3_5/product_query_set_v1/phase_a/PQS_V1_HUMAN_AUTHORING_GAPS.md"
        assert "Slot 01" in packet.read_text(encoding="utf-8")
    finally:
        # This is a narrow temporary test fixture created by this test.
        import shutil
        shutil.rmtree(temporary_root, ignore_errors=True)


def test_pqs_phase_a_preserves_stress_set_as_separate_eval_role() -> None:
    assert "Product Query Set ≠ Evidence Sufficiency Stress Set" in (OUT / "PQS_V1_PROTOCOL.md").read_text(encoding="utf-8")


def test_pqs_phase_a_does_not_start_f1a() -> None:
    assert _audit()["f1a_started"] is False


def test_pqs_phase_a_does_not_start_f1b() -> None:
    assert _audit()["f1b_started"] is False


def test_pqs_phase_a_unicode_whitespace_normalization_is_mechanical() -> None:
    assert normalize_for_exact_duplicate(" a\n b ") == "a b"
