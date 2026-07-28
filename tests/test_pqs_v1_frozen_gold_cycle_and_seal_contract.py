from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTION = (
    ROOT / "research/v3_5/product_query_set_v1/gold_construction_v1"
)
FROZEN = CONSTRUCTION / "frozen_guarded"
CYCLE = FROZEN / "frozen_cycle_v1"
INITIAL = CYCLE / "annotation/initial"
INDEPENDENT = CYCLE / "review/independent_draft"
COMPARISON = CYCLE / "review/comparison"
CANDIDATE = CYCLE / "reviewed_gold_candidate"
SEALED = CYCLE / "sealed"
INTERNAL = CYCLE / "internal_protected"
COMPLETION = CYCLE / "completion_only"
P5 = ROOT / "research/v3_5/product_query_set_v1/split_v1"
P6 = ROOT / "research/v3_5/product_query_set_v1/gold_protocol_v1"
EXPECTED_LEDGER_SHA = "9d37f019ed0ef302c56070e939a024c96546195ebde1236fdb5b30c5d5d78ee8"
EXPECTED_P7A_GUARD_SHA = "aad5e437cb49ccae62b9a72ccd706da827a6235089c045ef2688fe4bbe8c7f10"
EXPECTED_INDEPENDENT_SEAL_SHA = (
    "97eff00429cfaa62ca414793d45503149ddeda887c1301ede176081dca77073d"
)
ALLOWED_OUTCOMES = {"agree", "revise_gold", "escalate", "blocked_by_source"}
COMPLETION_FIELDS = {
    "input_identity_verified",
    "frozen_query_count",
    "guarded_batch_count",
    "annotator_unit_count",
    "reviewer_unit_count",
    "reviewer_independent_draft_seal_valid",
    "reviewed_case_count",
    "aggregate_outcomes",
    "pending_user_adjudication",
    "three_layer_validation",
    "evidence_spans_replayed",
    "replay_failures",
    "sealed_artifact_hashes",
    "byte_identical_copy",
    "semantic_fields_changed_by_orchestrator",
    "frozen_gold_leakage_detected",
    "development_gold_read_by_semantic_units",
    "product_prediction_read",
    "product_pipeline_calls",
    "p8_started",
    "acceptance_status",
    "current_codex_session_can_close",
}
FORBIDDEN_COMPLETION_TOKENS = (
    "PQS_V1_Q",
    "bilibili:",
    "quote_text",
    "required_aspects",
    "supported_aspects",
    "missing_aspects",
    "reason_codes",
    "span_registry",
    "acceptable_video_ids",
)
sys.path.insert(0, str(ROOT / "scripts"))
from validate_frozen_gold_cycle_v1 import (  # noqa: E402
    FrozenCycleValidationError,
    replay_evidence,
    validate_frozen_cycle,
    validate_reviewer_seal,
    validate_three_layer_records,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def require_final() -> None:
    if not (INTERNAL / "frozen_gold_v1.seal.json").is_file():
        pytest.skip("Frozen Gold materializer has not been executed")


def comparison_cases() -> list[dict]:
    return [read_json(path) for path in sorted(COMPARISON.glob("opaque_case_*.json"))]


def candidate_layers() -> tuple[list[dict], list[dict], list[dict]]:
    return (
        read_jsonl(CANDIDATE / "product_retrieval_gold.frozen.v1.reviewed.jsonl"),
        read_jsonl(CANDIDATE / "product_evidence_gold.frozen.v1.reviewed.jsonl"),
        read_jsonl(CANDIDATE / "product_sufficiency_gold.frozen.v1.reviewed.jsonl"),
    )


def test_frozen_cycle_ledger_hash_matches() -> None:
    assert sha(CYCLE / "PQS_V1_FROZEN_GOLD_CYCLE_DECISION_LEDGER.json") == (
        EXPECTED_LEDGER_SHA
    )


def test_guard_identity_matches_p7a() -> None:
    guard = read_json(FROZEN / "FROZEN_PACKET_ACCESS_GUARD.json")
    transitions = list(guard.get("status_transition_history", []))
    if isinstance(guard.get("status_transition"), dict):
        transitions.append(guard["status_transition"])
    assert any(
        transition.get("previous_guard_sha256") == EXPECTED_P7A_GUARD_SHA
        for transition in transitions
    )


def test_exactly_10_frozen_queries_in_5_packets() -> None:
    manifest = read_json(FROZEN / "batch_manifest.json")
    ids = [
        query_id
        for query_ids in manifest["batch_assignments"].values()
        for query_id in query_ids
    ]
    assert manifest["batch_count"] == 5
    assert manifest["query_count"] == 10
    assert len(ids) == len(set(ids)) == 10


def test_query_ids_match_p5_frozen_split() -> None:
    packet_manifest = read_json(FROZEN / "batch_manifest.json")
    packet_ids = {
        query_id
        for query_ids in packet_manifest["batch_assignments"].values()
        for query_id in query_ids
    }
    split = read_json(P5 / "product_query_split_v1.locked.json")
    assert packet_ids == set(split["frozen_evaluation"]["query_ids"])


def test_no_development_query_in_frozen_packets() -> None:
    packet_manifest = read_json(FROZEN / "batch_manifest.json")
    frozen_ids = {
        query_id
        for query_ids in packet_manifest["batch_assignments"].values()
        for query_id in query_ids
    }
    split = read_json(P5 / "product_query_split_v1.locked.json")
    development_ids = {
        row["query_id"]
        for row in split["assignments"]
        if row["split_assignment"] == "development"
    }
    assert frozen_ids.isdisjoint(development_ids)


def test_annotator_and_reviewer_are_distinct_units() -> None:
    initial = read_json(INITIAL / "initial_annotation.seal.json")
    reviewer = read_json(INDEPENDENT / "independent_draft.seal.json")
    assert initial["unit_id"] != reviewer["reviewer_unit_id"]


def test_reviewer_draft_sealed_before_annotation_open() -> None:
    seal = read_json(INDEPENDENT / "independent_draft.seal.json")
    assert seal["initial_annotation_opened"] is False
    assert seal["independent_draft_complete"] is True
    assert seal["seal_status"] == "sealed"


def test_reviewer_draft_immutable_after_seal() -> None:
    seal = read_json(INDEPENDENT / "independent_draft.seal.json")
    assert seal["independent_draft_mutable_after_seal"] is False
    assert sha(INDEPENDENT / "independent_draft.seal.json") == (
        EXPECTED_INDEPENDENT_SEAL_SHA
    )
    assert all(
        sha(INDEPENDENT / name) == expected
        for name, expected in seal["artifact_hashes"].items()
    )


def test_invalid_contaminated_reviewer_cannot_participate() -> None:
    seal = read_json(INDEPENDENT / "independent_draft.seal.json")
    contaminated = copy.deepcopy(seal)
    contaminated["initial_annotation_opened"] = True
    with pytest.raises(FrozenCycleValidationError):
        validate_reviewer_seal(contaminated)


def test_review_outcomes_use_closed_enum() -> None:
    cases = comparison_cases()
    assert len(cases) == 10
    assert all(case["outcome"] in ALLOWED_OUTCOMES for case in cases)


def test_revise_gold_has_complete_three_layer_replacement() -> None:
    for case in comparison_cases():
        if case["outcome"] != "revise_gold":
            continue
        assert case["replacement_records_present"] is True
        replacement = case["replacement_records"]
        assert set(replacement) == {
            "retrieval_gold",
            "evidence_gold",
            "sufficiency_gold",
        }


def test_reconciliation_rounds_at_most_one() -> None:
    if (CANDIDATE / "reviewed_case_status.frozen.v1.jsonl").is_file():
        statuses = read_jsonl(CANDIDATE / "reviewed_case_status.frozen.v1.jsonl")
        assert all(row["reconciliation_rounds"] <= 1 for row in statuses)
    else:
        audit = read_json(COMPARISON / "comparison.audit.json")
        assert audit["scope_flags"]["reconciliation_started"] is False


def test_orchestrator_never_makes_semantic_choice() -> None:
    source = (ROOT / "scripts/materialize_frozen_gold_cycle_v1.py").read_text()
    assert '"semantic_fields_changed_by_orchestrator": False' in source
    assert '"semantic_choice_made_by_orchestrator": False' in source
    if (INTERNAL / "frozen_gold_v1.audit.json").is_file():
        audit = read_json(INTERNAL / "frozen_gold_v1.audit.json")
        assert audit["scope"]["semantic_fields_changed_by_orchestrator"] is False


def test_all_resolved_cases_have_final_three_layer_records() -> None:
    require_final()
    retrieval, evidence, sufficiency = candidate_layers()
    statuses = read_jsonl(CANDIDATE / "reviewed_case_status.frozen.v1.jsonl")
    assert len(retrieval) == len(evidence) == len(sufficiency) == len(statuses) == 10
    assert all(row["resolution_status"] == "resolved" for row in statuses)


def test_p6_three_layer_schema_validation_passes() -> None:
    require_final()
    validate_three_layer_records(ROOT, *candidate_layers())


def test_cross_object_validation_passes() -> None:
    require_final()
    validate_three_layer_records(ROOT, *candidate_layers())


def test_all_evidence_spans_replay() -> None:
    require_final()
    _, evidence, _ = candidate_layers()
    expected = sum(len(row["span_registry"]) for row in evidence)
    assert replay_evidence(ROOT, evidence) == expected


def test_navigation_only_sources_not_used_as_evidence() -> None:
    require_final()
    _, evidence, _ = candidate_layers()
    assert all(
        span["source_type"] in {"official_subtitle", "asr_transcript"}
        for row in evidence
        for span in row["span_registry"]
    )
    assert all(
        row["source_review_state"]["navigation_sources_used_as_gold_evidence"] is False
        for row in evidence
    )


def test_no_downstream_failure_codes_in_gold() -> None:
    require_final()
    prefixes = ("RET_", "BLD_", "SEL_", "GATE_", "JDG_", "SRC_")
    for layer in candidate_layers():
        assert all(
            not any(code.startswith(prefixes) for code in row["reason_codes"])
            for row in layer
        )


def test_sealed_files_byte_identical_to_reviewed_candidate() -> None:
    require_final()
    pairs = {
        "product_retrieval_gold.frozen.v1.reviewed.jsonl":
            "product_retrieval_gold.frozen.v1.sealed.jsonl",
        "product_evidence_gold.frozen.v1.reviewed.jsonl":
            "product_evidence_gold.frozen.v1.sealed.jsonl",
        "product_sufficiency_gold.frozen.v1.reviewed.jsonl":
            "product_sufficiency_gold.frozen.v1.sealed.jsonl",
        "reviewed_case_status.frozen.v1.jsonl":
            "reviewed_case_status.frozen.v1.sealed.jsonl",
    }
    assert all(
        (CANDIDATE / reviewed).read_bytes() == (SEALED / sealed).read_bytes()
        for reviewed, sealed in pairs.items()
    )


def test_hash_manifest_matches_all_sealed_files() -> None:
    require_final()
    rows = read_jsonl(INTERNAL / "frozen_gold_v1.file_hash_manifest.jsonl")
    hashes = {row["path"]: row["sha256"] for row in rows}
    for path in SEALED.iterdir():
        relative = path.relative_to(CYCLE).as_posix()
        assert hashes[relative] == sha(path)


def test_completion_response_contains_only_allowed_fields() -> None:
    require_final()
    completion = read_json(COMPLETION / "FROZEN_GOLD_V1_COMPLETION_STATUS.json")
    response = read_json(COMPLETION / "FROZEN_GOLD_V1_COMPLETION_RESPONSE.md")
    assert set(completion) == COMPLETION_FIELDS
    assert response == completion


def test_completion_response_contains_no_query_level_gold() -> None:
    require_final()
    text = (COMPLETION / "FROZEN_GOLD_V1_COMPLETION_RESPONSE.md").read_text()
    assert not any(token in text for token in FORBIDDEN_COMPLETION_TOKENS)


def test_no_frozen_gold_in_normal_logs() -> None:
    require_final()
    for path in COMPLETION.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not any(token in text for token in FORBIDDEN_COMPLETION_TOKENS)


def test_no_development_gold_read_by_semantic_units() -> None:
    initial = read_json(INITIAL / "initial_annotation.audit.json")
    reviewer = read_json(INDEPENDENT / "independent_draft.audit.json")
    comparison = read_json(COMPARISON / "comparison.audit.json")
    assert initial["access_scope"]["development_gold_opened"] is False
    assert reviewer["scope"]["development_gold_opened"] is False
    assert comparison["scope_flags"]["development_gold_opened"] is False
    if (INTERNAL / "frozen_gold_v1.audit.json").is_file():
        assert (
            read_json(INTERNAL / "frozen_gold_v1.audit.json")["scope"][
                "development_gold_read_by_semantic_units"
            ]
            is False
        )


def test_no_prediction_or_product_pipeline_access() -> None:
    initial = read_json(INITIAL / "initial_annotation.audit.json")
    reviewer = read_json(INDEPENDENT / "independent_draft.audit.json")
    comparison = read_json(COMPARISON / "comparison.audit.json")
    assert initial["access_scope"]["product_prediction_opened"] is False
    assert initial["access_scope"]["product_pipeline_calls"] == 0
    assert reviewer["scope"]["product_prediction_opened"] is False
    assert reviewer["scope"]["product_pipeline_calls"] == 0
    assert comparison["scope_flags"]["product_prediction_opened"] is False
    assert comparison["scope_flags"]["product_pipeline_calls"] == 0


def test_p8_not_started() -> None:
    source = (ROOT / "scripts/materialize_frozen_gold_cycle_v1.py").read_text()
    assert '"p8_started": False' in source
    assert '"p8_authorized": False' in source
    if (INTERNAL / "frozen_gold_v1.audit.json").is_file():
        assert read_json(INTERNAL / "frozen_gold_v1.audit.json")["scope"]["p8_started"] is False


def test_upstream_p3_through_development_seal_assets_unchanged() -> None:
    # The materializer is path-limited to Frozen lifecycle outputs and contains
    # no read or write reference to protected Development Gold directories.
    source = (ROOT / "scripts/materialize_frozen_gold_cycle_v1.py").read_text()
    assert "development_cycle" not in source
    assert "development_seal" not in source
    assert "gold_construction_v1/development" not in source
    expected = {
        P5 / "product_query_split_v1.locked.json":
            "3191bbe3bad682966a0f4c865510c86ac3cbdec933da298cc1bb0cafa2f0d09b",
        P6 / "PRODUCT_QUERY_GOLD_PROTOCOL_V1.md":
            "1da2fd575a091ac5adff7e823080b8d90564fbf912abdb3cc5ee409599886e06",
    }
    assert all(sha(path) == expected_hash for path, expected_hash in expected.items())


def test_full_frozen_cycle_validator_passes() -> None:
    require_final()
    result = validate_frozen_cycle(ROOT)
    assert result["status"] == "passed"
    assert result["case_count"] == 10
    assert result["scope_violation_count"] == 0
