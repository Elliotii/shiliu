from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CYCLE = ROOT / "research/v3_5/product_query_set_v1/gold_construction_v1/development_cycle"
sys.path.insert(0, str(ROOT / "scripts"))
from validate_development_gold_cycle import validate_cycle  # noqa: E402
from validate_product_gold_protocol_v1 import validate_three_layer  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def j(path: Path) -> dict:
    return json.loads(path.read_text())


def jl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_cycle_ledger_hash_matches() -> None:
    assert sha(CYCLE / "PQS_V1_DEVELOPMENT_GOLD_CYCLE_DECISION_LEDGER.json") == (
        "99cb02349b5a67a9a33ccaaba75bc84d12a6c81be2a37db54fab3cba6c77e1ea"
    )


def test_14_development_queries_complete_and_no_frozen_query() -> None:
    status = jl(CYCLE / "reviewed_gold_candidate/reviewed_case_status.jsonl")
    ids = {row["query_id"] for row in status}
    frozen = {
        row["query_id"]
        for row in jl(
            ROOT / "research/v3_5/product_query_set_v1/split_v1/frozen_locked/product_query_frozen_evaluation_v1.locked.jsonl"
        )
    }
    assert len(ids) == 14
    assert ids.isdisjoint(frozen)


def test_four_valid_isolated_units_and_cross_review_mapping() -> None:
    audit = j(CYCLE / "development_gold_cycle.audit.json")
    assert set(audit["valid_units"]) == {
        "annotator_A", "annotator_B", "reviewer_A", "reviewer_B_replacement"
    }
    assert audit["assignment"]["cross_reviewer_mapping_correct"]
    assert not audit["boundary"]["same_unit_annotated_and_reviewed_same_case"]


def test_invalid_reviewer_attempt_excluded_before_draft() -> None:
    invalid = j(CYCLE / "development_gold_cycle.audit.json")["invalidated_attempts"][0]
    assert invalid["independent_drafts_written"] == 0
    assert not invalid["comparison_performed"]
    assert not invalid["counted_as_valid_unit"]


def test_independent_drafts_sealed_before_initial_open() -> None:
    audit = j(CYCLE / "development_gold_cycle.audit.json")
    assert audit["independence"]["reviewer_A_draft_before_open"]
    assert audit["independence"]["reviewer_B_draft_before_open"]
    validate_cycle()


def test_all_three_layers_have_14_records_and_pass_p6() -> None:
    base = CYCLE / "reviewed_gold_candidate"
    layers = {
        name: {
            row["query_id"]: row
            for row in jl(base / f"product_{name}_gold.development.reviewed.jsonl")
        }
        for name in ("retrieval", "evidence", "sufficiency")
    }
    assert all(len(value) == 14 for value in layers.values())
    for query_id in layers["retrieval"]:
        validate_three_layer(
            layers["retrieval"][query_id],
            layers["evidence"][query_id],
            layers["sufficiency"][query_id],
        )


def test_evidence_spans_replay_and_navigation_not_evidence() -> None:
    result = validate_cycle()
    assert result["replayed_span_count"] == 41
    evidence = jl(
        CYCLE / "reviewed_gold_candidate/product_evidence_gold.development.reviewed.jsonl"
    )
    assert all(
        span["source_type"] in {"official_subtitle", "asr_transcript"}
        for record in evidence
        for span in record["span_registry"]
    )


def test_unreviewed_videos_are_not_hard_negatives() -> None:
    rows = jl(
        CYCLE / "reviewed_gold_candidate/product_retrieval_gold.development.reviewed.jsonl"
    )
    assert all(
        set(row["hard_negative_video_ids"])
        <= set(row["relevance_review_scope"]["reviewed_video_ids"])
        for row in rows
    )
    assert all(row["unjudged_outside_pool_is_negative"] is False for row in rows)


def test_no_downstream_failure_codes_in_gold() -> None:
    prefixes = ("RET_", "BLD_", "SEL_", "GATE_", "JDG_", "SRC_")
    base = CYCLE / "reviewed_gold_candidate"
    for layer in ("retrieval", "evidence", "sufficiency"):
        for row in jl(base / f"product_{layer}_gold.development.reviewed.jsonl"):
            assert not any(code.startswith(prefixes) for code in row["reason_codes"])


def test_review_outcomes_and_one_reconciliation_only() -> None:
    audit = j(CYCLE / "development_gold_cycle.audit.json")
    assert audit["review_counts"] == {
        "agree": 13, "revise_gold": 1, "escalate": 0, "blocked_by_source": 0
    }
    assert audit["reconciliation"]["cases"] == 1
    assert audit["reconciliation"]["rounds_max_per_case"] == 1
    assert not audit["reconciliation"]["second_round_started"]


def test_no_pending_user_adjudication_bundle_needed() -> None:
    decision = j(CYCLE / "development_gold_cycle.execution_decision.json")
    assert decision["pending_user_adjudication"] == 0
    assert not (CYCLE / "adjudication/development_gold_user_adjudication_bundle.md").exists()


def test_upstream_assets_unchanged() -> None:
    expected = {
        "research/v3_5/product_query_set_v1/freeze/product_query_set_v1.locked.jsonl": "35d33dcf4dd77f12cad4e0c118f2c2f2e371a3019320906a3d2134bb933dd59c",
        "research/v3_5/product_query_set_v1/split_v1/product_query_development_v1.locked.jsonl": "e68d6bb405bafadb56c5333834d72c8155a7a310ca2e20341df4f412488a8935",
        "research/v3_5/product_query_set_v1/gold_protocol_v1/PRODUCT_QUERY_GOLD_PROTOCOL_V1.md": "1da2fd575a091ac5adff7e823080b8d90564fbf912abdb3cc5ee409599886e06",
        "research/v3_5/product_query_set_v1/gold_construction_v1/shared/neutral_library_navigation_index.jsonl": "5cbd90113068167137f0fae6a4f10e08af7eaf8d2c0f3c10d03704a2acd9f32f",
        "research/v3_5/product_query_set_v1/gold_construction_v1/shared/authoritative_transcript_identity_catalog.jsonl": "6dea9ffb022387d9e8535beca03c989316941027ef46370519a4905174ca9aa4",
    }
    assert all(sha(ROOT / path) == digest for path, digest in expected.items())


def test_no_product_pipeline_prediction_existing_gold_frozen_or_p8() -> None:
    boundary = j(CYCLE / "development_gold_cycle.audit.json")["boundary"]
    assert boundary == {
        "same_unit_annotated_and_reviewed_same_case": False,
        "orchestrator_made_semantic_decisions": False,
        "frozen_packet_opened": False,
        "product_prediction_read": False,
        "existing_gold_read": False,
        "product_pipeline_calls": 0,
        "p8_started": False,
    }


def test_execution_state_is_reviewed_candidate_not_sealed() -> None:
    assert j(CYCLE / "development_gold_cycle.execution_decision.json") == {
        "execution_status": "complete",
        "cycle_status": "reviewed_development_gold_candidate_ready",
        "reviewed_case_count": 14,
        "pending_user_adjudication": 0,
        "acceptance_status": "pending_v3_5_b_review",
        "development_gold_formally_sealed": False,
        "frozen_cycle_authorized": False,
        "p8_authorized": False,
    }


def test_cycle_file_hash_manifest_is_current() -> None:
    for row in jl(CYCLE / "development_gold_cycle.file_hash_manifest.jsonl"):
        path = ROOT / row["path"]
        assert path.stat().st_size == row["size_bytes"]
        assert sha(path) == row["sha256"]
