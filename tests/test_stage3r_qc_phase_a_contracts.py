from __future__ import annotations

import json
from pathlib import Path

import pytest

from shiliu.eval_v3_5.stage3r_qc_phase_a import (
    EXPECTED_STRESS_SET_SHA256,
    REQUIRED_QUERY_TYPES,
    PhaseABlocked,
    canonical_video_identity_from_gold,
    classify_video_mapping,
    file_sha256,
    load_jsonl,
    select_representative_cases,
    video_identity_matches,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/stage3r_qc"
CORPUS = ROOT / "research/v3_5/stage3r/input/stage2r_final_corpus/development_gold.executable_31.jsonl"


def _read(path: str) -> dict:
    return json.loads((OUT / path).read_text())


def test_stage3r_qc_phase_a_validates_stress_set_identity() -> None:
    assert file_sha256(CORPUS) == EXPECTED_STRESS_SET_SHA256
    assert _read("input_freeze/stress_set_identity.json")["records"] == 31


def test_stage3r_qc_phase_a_does_not_access_heldout() -> None:
    assert _read("stage3r_qc_phase_a_execution.audit.json")["heldout_accessed"] is False


def test_stage3r_qc_phase_a_video_identity_is_deterministic() -> None:
    row = load_jsonl(CORPUS)[0]
    assert canonical_video_identity_from_gold(row) == canonical_video_identity_from_gold(row)
    runtime_by_case = {
        runtime["case_id"]: runtime["canonical_video_identity"]
        for runtime in load_jsonl(OUT / "video_identity/runtime_video_identity_projection.jsonl")
    }
    assert video_identity_matches(
        canonical_video_identity_from_gold(row),
        runtime_by_case[row["case_id"]],
    )


def test_stage3r_qc_phase_a_rejects_ambiguous_video_identity() -> None:
    identity = {"source_platform": "bilibili", "source_version": "v", "source_artifact_id": "a", "bvid": "BV1"}
    assert classify_video_mapping(identity, identity, ["BV1", "BV1"]) == "identity_ambiguous"


def test_stage3r_qc_phase_a_distinguishes_identity_failure_from_retrieval_miss() -> None:
    identity = {"source_platform": "bilibili", "source_version": "v", "source_artifact_id": "a", "bvid": "BV1"}
    other = {**identity, "source_version": "other"}
    assert classify_video_mapping(identity, identity, []) == "runtime_result_not_present"
    assert classify_video_mapping(identity, other, []) == "cross_version"


def test_stage3r_qc_phase_a_rejects_missing_video_identity() -> None:
    row = load_jsonl(CORPUS)[0]
    row["canonical_adjudication"]["source_identity"]["source_video_id"] = ""
    with pytest.raises(PhaseABlocked):
        canonical_video_identity_from_gold(row)


def test_stage3r_qc_phase_a_selects_10_to_12_cases() -> None:
    manifest = _read("sample/selected_case_manifest.json")
    assert 10 <= manifest["total_cases"] <= 12


def test_stage3r_qc_phase_a_selects_8_to_10_evidence_bearing() -> None:
    assert 8 <= _read("sample/selected_case_manifest.json")["evidence_bearing_cases"] <= 10


def test_stage3r_qc_phase_a_selects_1_to_2_insufficient_diagnostics() -> None:
    assert 1 <= _read("sample/selected_case_manifest.json")["insufficient_diagnostic_cases"] <= 2


def test_stage3r_qc_phase_a_does_not_count_insufficient_as_evidence_bearing() -> None:
    rows = load_jsonl(OUT / "sample/selected_cases.internal.jsonl")
    assert all(not row["evidence_bearing"] for row in rows if row["label"] == "insufficient")


def test_stage3r_qc_phase_a_covers_required_query_types() -> None:
    actual = set(_read("sample/selected_case_manifest.json")["query_type_distribution"])
    assert REQUIRED_QUERY_TYPES <= actual


def test_stage3r_qc_phase_a_reuses_frozen_q0() -> None:
    assert all(row["reused_frozen_q0"] for row in load_jsonl(OUT / "q0_baseline/q0_asset_trace.jsonl"))


def test_stage3r_qc_phase_a_does_not_rerun_v3() -> None:
    audit = _read("stage3r_qc_phase_a_execution.audit.json")
    assert audit["v3_retrieval_calls"] == audit["embedding_calls"] == 0


def test_stage3r_qc_phase_a_authoring_packet_excludes_target_title() -> None:
    audit = _read("query_authoring/authoring_packet_leakage.audit.json")
    assert audit["leaked_target_video_fields"] == 0
    assert audit["target_video_titles_read_for_packet"] is False


def test_stage3r_qc_phase_a_authoring_packet_excludes_video_ids() -> None:
    assert _read("query_authoring/authoring_packet_leakage.audit.json")["leaked_video_id_values"] == []


def test_stage3r_qc_phase_a_authoring_packet_excludes_gold_spans() -> None:
    assert _read("query_authoring/authoring_packet_leakage.audit.json")["leaked_gold_fields"] == 0


def test_stage3r_qc_phase_a_authoring_packet_excludes_labels() -> None:
    fields = _read("query_authoring/authoring_packet_leakage.audit.json")["packet_fields"]
    assert "sufficiency_label" not in fields and "label" not in fields


def test_stage3r_qc_phase_a_authoring_packet_excludes_q0_results() -> None:
    assert _read("query_authoring/authoring_packet_leakage.audit.json")["leaked_runtime_results"] == 0


def test_stage3r_qc_phase_a_query_template_is_blank() -> None:
    for row in load_jsonl(OUT / "query_authoring/stage3r_qc_query_decisions.template.jsonl"):
        assert row["q1_discovery_query"] == "" and row["q2_retrieval_intents"] == [] and row["human_notes"] == ""


def test_stage3r_qc_phase_a_does_not_generate_q1() -> None:
    assert _read("stage3r_qc_phase_a_execution.audit.json")["q1_queries_generated_by_codex"] == 0


def test_stage3r_qc_phase_a_does_not_generate_q2() -> None:
    assert _read("stage3r_qc_phase_a_execution.audit.json")["q2_queries_generated_by_codex"] == 0
