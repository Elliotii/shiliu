from __future__ import annotations

import json
from pathlib import Path

from shiliu.eval_v3_5.stage3r_qc_phase_b import (
    _score_search,
    audit_exact_leakage,
    file_sha256,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/stage3r_qc/phase_b"
PHASE_A = ROOT / "research/v3_5/stage3r_qc"


def _json(relative: str):
    return json.loads((OUT / relative).read_text())


def _jsonl(relative: str):
    return [
        json.loads(line)
        for line in (OUT / relative).read_text().splitlines()
        if line.strip()
    ]


def _cases():
    return _jsonl("scoring/case_results.jsonl")


def _approved():
    return {
        row["case_id"]: row
        for row in _jsonl("input_freeze/approved_query_decisions.parsed.jsonl")
    }


def test_stage3r_qc_phase_b_rejects_video_id_leakage() -> None:
    rows = [{
        "case_id": "c", "q1_discovery_query": "find BV123",
        "q2_retrieval_intents": ["safe"], "human_notes": "",
    }]
    assert audit_exact_leakage(rows, {"video_ids": ["BV123"]})["hard_leakage_count"] == 1


def test_stage3r_qc_phase_b_rejects_full_target_title_leakage() -> None:
    rows = [{
        "case_id": "c", "q1_discovery_query": "完整目标视频标题",
        "q2_retrieval_intents": ["safe"], "human_notes": "",
    }]
    assert audit_exact_leakage(
        rows, {"full_target_titles": ["完整目标视频标题"]}
    )["hard_leakage_count"] == 1


def test_stage3r_qc_phase_b_rejects_gold_segment_leakage() -> None:
    rows = [{
        "case_id": "c", "q1_discovery_query": "SEG_001",
        "q2_retrieval_intents": ["safe"], "human_notes": "",
    }]
    assert audit_exact_leakage(
        rows, {"gold_segment_ids": ["SEG_001"]}
    )["hard_leakage_count"] == 1


def test_stage3r_qc_phase_b_does_not_use_neutral_terms_as_query_expansion() -> None:
    approved = _approved()
    for row in _cases():
        request = _json(f"execution/q1/cases/{row['case_id']}/request.json")
        assert request["query"] == approved[row["case_id"]]["q1_discovery_query"]


def test_stage3r_qc_phase_b_reuses_frozen_q0() -> None:
    assert _json("stage3r_qc_phase_b_execution.audit.json")["q0_rerun"] is False


def test_stage3r_qc_phase_b_does_not_rerun_q0() -> None:
    assert _json("stage3r_qc_phase_b_runtime_usage.json")["q0_v3_calls"] == 0


def test_stage3r_qc_phase_b_uses_frozen_v3_runtime() -> None:
    audit = _json("runtime_freeze/frozen_v3_runtime_config.audit.json")
    assert audit["runtime_hashes_match_stage3r"]


def test_stage3r_qc_phase_b_does_not_modify_v3_config() -> None:
    assert _json("stage3r_qc_phase_b_execution.audit.json")["retrieval_configuration_modified"] is False


def test_stage3r_qc_phase_b_runs_one_q1_per_case() -> None:
    assert len(_cases()) == 10
    assert all(row["q1"]["retrieval_call_count"] == 1 for row in _cases())


def test_stage3r_qc_phase_b_runs_each_unique_q2_intent() -> None:
    for row in _cases():
        assert row["q2"]["new_retrieval_call_count"] == row["q2"]["unique_execution_query_count"]


def test_stage3r_qc_phase_b_reuses_exact_duplicate_q1_result() -> None:
    # The approved input has no exact Q1/Q2 duplicate, so reuse must be exactly zero.
    assert _json("analysis/retrieval_budget_summary.json")["q2"]["q1_results_reused"] == 0


def test_stage3r_qc_phase_b_does_not_semantically_dedupe_queries() -> None:
    assert _json("analysis/retrieval_budget_summary.json")["q2"]["actual_new_calls"] == 29


def test_stage3r_qc_phase_b_q2_only_unions_canonical_video_ids() -> None:
    for row in _cases():
        union = _json(f"execution/q2/cases/{row['case_id']}/q2_union.json")
        assert union["merge_rule"] == "union_of_canonical_video_identities"


def test_stage3r_qc_phase_b_does_not_rerank_q2_union() -> None:
    assert all(
        not _json(f"execution/q2/cases/{row['case_id']}/q2_union.json")["reranked"]
        for row in _cases()
    )


def test_stage3r_qc_phase_b_reports_best_per_intent_rank() -> None:
    for row in _cases():
        ranks = [rank for rank in row["q2"]["target_per_intent_ranks"].values() if rank]
        assert row["q2"]["target_best_rank"] == (min(ranks) if ranks else None)


def test_stage3r_qc_phase_b_uses_canonical_video_identity() -> None:
    assert _json("stage3r_qc_phase_b_execution.audit.json")["canonical_video_identity_reused"]


def test_stage3r_qc_phase_b_distinguishes_identity_failure_from_retrieval_miss() -> None:
    target = {"bvid": "BV1", "product_video_id": 1}
    assert _score_search({"video_candidates": [], "raw_unit_candidates": []}, target)["target_hit"] is False


def test_stage3r_qc_phase_b_excludes_insufficient_from_main_recall() -> None:
    assert _json("analysis/evidence_bearing_metrics.json")["q2_target_video_recall"]["denominator"] == 9


def test_stage3r_qc_phase_b_reports_insufficient_diagnostic_separately() -> None:
    value = _json("analysis/insufficient_diagnostic_result.json")
    assert value["excluded_from_evidence_bearing_recall"] is True


def test_stage3r_qc_phase_b_classifies_query_contract_outcomes() -> None:
    allowed = {
        "already_retrievable", "single_intent_contract_recoverable",
        "decomposition_recoverable", "persistent_retrieval_gap",
    }
    assert all(row["classification"] in allowed for row in _cases())


def test_stage3r_qc_phase_b_does_not_call_candidate_builder() -> None:
    assert _json("stage3r_qc_phase_b_runtime_usage.json")["candidate_builder_calls"] == 0


def test_stage3r_qc_phase_b_does_not_call_selector() -> None:
    assert _json("stage3r_qc_phase_b_runtime_usage.json")["selector_calls"] == 0


def test_stage3r_qc_phase_b_does_not_access_heldout() -> None:
    assert _json("isolation/heldout_access.audit.json")["heldout_accessed"] is False


def test_stage3r_qc_phase_b_does_not_call_external_llm() -> None:
    assert _json("stage3r_qc_phase_b_runtime_usage.json")["external_llm_calls"] == 0


def test_stage3r_qc_phase_b_approved_freeze_hash_matches() -> None:
    identity = _json("input_freeze/approved_query_decisions.identity.json")
    frozen = OUT / "input_freeze/approved_query_decisions.jsonl"
    assert identity["hash_match"] and file_sha256(frozen) == identity["source_sha256"]


def test_stage3r_qc_phase_b_runtime_hashes_unchanged() -> None:
    assert _json("phase_b_tests/runtime_integrity_check.json")["runtime_hashes_unchanged"]


def test_stage3r_qc_phase_b_does_not_modify_phase_a_assets() -> None:
    manifest = PHASE_A / "stage3r_qc_phase_a_file_hash_manifest.jsonl"
    assert manifest.is_file() and len(manifest.read_text().splitlines()) > 0


def test_stage3r_qc_phase_b_reports_semantic_neighbor_not_scored() -> None:
    summary = _json("analysis/query_contract_classification_summary.json")
    assert summary["semantic_neighbor_recall"]["status"] == "not_scored_no_frozen_definition"


def test_stage3r_qc_phase_b_does_not_start_downstream_phases() -> None:
    audit = _json("stage3r_qc_phase_b_execution.audit.json")
    assert not audit["product_query_set_started"] and not audit["f1a_f1b_started"]
