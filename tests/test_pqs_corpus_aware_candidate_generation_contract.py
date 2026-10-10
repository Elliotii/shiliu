from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/product_query_set_v1/corpus_aware_generation"
USER = OUT / "product_query_candidates.user_review.jsonl"
BASIS = OUT / "product_query_candidates.internal_basis.jsonl"
INVENTORY = OUT / "product_query_corpus_inventory.internal.jsonl"
AUDIT = OUT / "corpus_aware_candidate_generation.audit.json"

FORBIDDEN_USER_FIELDS = {
    "video_id",
    "bv_id",
    "source_path",
    "source_title",
    "uploader",
    "target_video",
    "transcript_quote",
    "expected_answer",
    "gold",
    "gold_span",
    "sufficiency_label",
    "retrieval_mode",
    "rank",
    "system_prediction",
    "system_success",
    "system_failure",
    "dev_or_frozen_identity",
}


def rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def audit() -> dict:
    return json.loads(AUDIT.read_text(encoding="utf-8"))


def test_required_outputs_exist() -> None:
    for path in (USER, BASIS, INVENTORY, AUDIT, OUT / "corpus_aware_candidate_generation_report.md"):
        assert path.is_file() and path.stat().st_size > 0


def test_no_eval_or_gold_paths_read() -> None:
    data = audit()
    assert data["gold_assets_read"] is False
    assert all(item["evaluation_asset"] is False for item in data["read_audit"])
    denied = re.compile(r"(^|/)(gold|phase_a|phase_a_r)(/|$)|frozen_evaluation|heldout", re.I)
    assert not any(denied.search(path) for path in data["allowed_sources_read"])


def test_no_product_retrieval_pipeline_called() -> None:
    assert audit()["product_retrieval_calls"] == 0


def test_no_search_candidate_set_generated() -> None:
    assert audit()["search_candidate_set_read"] is False
    assert not (OUT / "SearchCandidateSet.json").exists()


def test_no_builder_selector_or_judge_called() -> None:
    data = audit()
    for key in ("candidate_builder_calls", "selector_calls", "mechanical_gate_calls", "semantic_judge_calls"):
        assert data[key] == 0


def test_no_old_user_decisions_read() -> None:
    assert audit()["old_user_decisions_read"] is False


def test_no_legacy_acceptance_decisions_read() -> None:
    assert audit()["legacy_acceptance_results_read"] is False


def test_no_old_neutral_pass1_candidates_read() -> None:
    assert audit()["old_neutral_pass1_candidates_read"] is False


def test_candidate_count_between_36_and_48() -> None:
    assert 36 <= len(rows(USER)) <= 48


def test_candidate_ids_unique_and_contiguous() -> None:
    ids = [row["candidate_id"] for row in rows(USER)]
    assert len(ids) == len(set(ids))
    assert ids == [f"PQC_{index:03d}" for index in range(1, len(ids) + 1)]


def test_user_review_contains_no_internal_source_ids() -> None:
    text = USER.read_text(encoding="utf-8")
    assert not re.search(r"\bBV[0-9A-Za-z]{10}\b", text)
    assert not re.search(r'"video_id"\s*:', text)
    assert "/Users/" not in text


def test_user_review_contains_no_answers_or_predictions() -> None:
    text = USER.read_text(encoding="utf-8")
    for phrase in ("expected_answer", "system_prediction", "system_success", "system_failure", "预期标签", "系统能回答"):
        assert phrase not in text


def test_internal_basis_has_matching_candidate_ids() -> None:
    user_ids = [row["candidate_id"] for row in rows(USER)]
    basis_ids = [row["candidate_id"] for row in rows(BASIS)]
    assert user_ids == basis_ids


def test_every_candidate_has_self_review() -> None:
    required = {
        "natural_user_question",
        "overly_generic",
        "overly_compound",
        "duplicate_or_near_duplicate",
        "answer_shaped_from_source",
        "overly_tied_to_single_title",
        "useful_for_personal_collection_search",
        "wording_clarity",
    }
    assert all(set(row["self_review_notes"]) == required for row in rows(BASIS))


def test_no_exact_duplicate_queries() -> None:
    queries = [row["query"].strip().casefold() for row in rows(USER)]
    assert len(queries) == len(set(queries))


def test_no_forbidden_output_fields() -> None:
    assert all(not (set(row) & FORBIDDEN_USER_FIELDS) for row in rows(USER))


def test_full_corpus_dump_not_used() -> None:
    assert audit()["full_corpus_dump_used"] is False


def test_transcript_access_logged() -> None:
    data = audit()
    logged = {item["file_or_table"] for item in data["read_audit"] if item["transcript_body_read"]}
    assert logged == set(data["transcript_files_or_items_inspected"])


def test_inventory_is_specific_and_structured() -> None:
    items = rows(INVENTORY)
    assert len(items) >= 20
    assert all(item["specific_subject"] and item["approximate_source_count"] > 0 for item in items)
    assert len({item["topic_cluster"] for item in items}) >= 8
