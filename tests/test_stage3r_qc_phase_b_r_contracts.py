from __future__ import annotations

import json
from pathlib import Path

import pytest

from shiliu.eval_v3_5.stage3r_qc_phase_b_r import (
    APPROVED_QUERY_SHA256,
    PhaseBRBlocked,
    classify_query_contract,
    classify_retrieval_mode,
    effective_runtime_config,
    inspect_index,
    resolve_product_default_path,
    resolve_view_reuse,
    runtime_configs_equivalent,
    select_frozen_known_positive,
    union_q2,
)
from shiliu.eval_v3_5.stage3r_qc_phase_b import file_sha256


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/stage3r_qc/phase_b_r"
SNAPSHOT = Path(
    "/Users/elliot/Documents/Shiliu/eval/v3_stage6/"
    "20260720T094346Z_c7663365/shiliu_eval.db"
)


def load_json(relative: str):
    return json.loads((OUT / relative).read_text(encoding="utf-8"))


def load_jsonl(relative: str):
    return [
        json.loads(line)
        for line in (OUT / relative).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_stage3r_qc_phase_b_r_reuses_phase_b_approved_queries():
    approved = ROOT / "research/v3_5/stage3r_qc/phase_b/input_freeze/approved_query_decisions.jsonl"
    assert file_sha256(approved) == APPROVED_QUERY_SHA256
    assert load_json("input_validation/approved_query_validation.json") == {
        "byte_preserved_phase_b_freeze": True,
        "case_alignment_with_phase_a": True,
        "queries_modified": False,
        "records": 10,
        "sha256": APPROVED_QUERY_SHA256,
        "sha256_match": True,
    }


def test_stage3r_qc_phase_b_r_reuses_phase_b_lexical_results():
    rows = load_jsonl("scoring/case_results.mode_corrected.jsonl")
    assert {row["lexical"]["source"] for row in rows} == {"reused_phase_b"}


def test_stage3r_qc_phase_b_r_does_not_rerun_lexical():
    audit = load_json("stage3r_qc_phase_b_r_execution.audit.json")
    usage = load_json("stage3r_qc_phase_b_r_runtime_usage.json")
    assert audit["lexical_rerun"] is False
    assert usage["lexical"]["new_calls"] == 0


def test_stage3r_qc_phase_b_r_resolves_actual_product_default_path():
    resolution = resolve_product_default_path(ROOT)
    assert resolution["effective_search_request_mode"] == "lexical"
    assert resolution["checks"] and all(resolution["checks"].values())


def test_stage3r_qc_phase_b_r_does_not_assume_auto():
    resolution = load_json("product_path/product_default_resolution.json")
    assert resolution["frontend_default_mode"] == "lexical"
    assert resolution["router_invoked"] is False


def test_stage3r_qc_phase_b_r_compares_effective_runtime_configs():
    matrix = load_json("runtime_preflight/runtime_equivalence_matrix.json")
    assert matrix["lexical_equals_product_default"] is True
    assert matrix["lexical_equals_hybrid"] is False
    assert len(matrix["compared_fields"]) == 12


def test_stage3r_qc_phase_b_r_reuses_product_view_when_equal_to_lexical():
    lexical = effective_runtime_config("lexical")
    assert resolve_view_reuse(dict(lexical), lexical, effective_runtime_config("hybrid")) == "lexical"


def test_stage3r_qc_phase_b_r_reuses_product_view_when_equal_to_hybrid():
    hybrid = effective_runtime_config("hybrid")
    assert resolve_view_reuse(dict(hybrid), effective_runtime_config("lexical"), hybrid) == "hybrid"


def test_stage3r_qc_phase_b_r_does_not_reuse_non_equivalent_modes():
    product = {**effective_runtime_config("lexical"), "top_k": 20}
    assert resolve_view_reuse(
        product, effective_runtime_config("lexical"), effective_runtime_config("hybrid")
    ) is None
    assert not runtime_configs_equivalent(product, effective_runtime_config("lexical"))


def test_stage3r_qc_phase_b_r_validates_known_positive_smoke_query():
    selected = select_frozen_known_positive(ROOT)
    audit = load_json("runtime_preflight/known_positive_smoke.audit.json")
    assert selected["query_id"] == "Q01"
    assert all(
        audit[key]
        for key in (
            "lexical_known_positive_returns_results",
            "product_default_known_positive_returns_results",
            "hybrid_known_positive_returns_results",
        )
    )


def test_stage3r_qc_phase_b_r_blocks_on_broken_runtime_or_index(tmp_path):
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"not sqlite")
    with pytest.raises((PhaseBRBlocked, Exception)):
        inspect_index(broken)


def test_stage3r_qc_phase_b_r_does_not_rebuild_index():
    identity = inspect_index(SNAPSHOT)
    integrity = load_json("runtime_freeze/runtime_integrity.audit.json")
    assert identity["embedding_index_available"] is True
    assert integrity["index_rebuilt"] is False


def test_stage3r_qc_phase_b_r_only_exactly_deduplicates_queries():
    usage = load_json("stage3r_qc_phase_b_r_runtime_usage.json")["hybrid"]
    assert usage["logical_queries"] == 49
    assert usage["unique_queries"] == 49
    assert usage["exact_duplicate_reuse_count"] == 0
