from __future__ import annotations

import json
from pathlib import Path

from shiliu.eval_v3_5.stage3r_qc_phase_b_r import (
    classify_query_contract,
    classify_retrieval_mode,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/stage3r_qc/phase_b_r"


def load_json(relative: str):
    return json.loads((OUT / relative).read_text(encoding="utf-8"))


def rows():
    return [
        json.loads(line)
        for line in (OUT / "scoring/case_results.mode_corrected.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]


def test_stage3r_qc_phase_b_r_runs_q0_q1_q2_under_product_default():
    values = rows()
    assert len(values) == 10
    assert all(set(row["product_default"]) >= {"q0", "q1", "q2"} for row in values)
    assert all(row["product_default"]["reused_from_view"] == "lexical" for row in values)


def test_stage3r_qc_phase_b_r_runs_q0_q1_q2_under_explicit_hybrid():
    values = rows()
    assert all(set(row["hybrid"]) >= {"q0", "q1", "q2"} for row in values)
    assert all(row["hybrid"]["q0"]["effective_mode"] == "hybrid" for row in values)
    assert load_json("stage3r_qc_phase_b_r_runtime_usage.json")["hybrid"]["new_calls"] == 49


def test_stage3r_qc_phase_b_r_does_not_modify_queries():
    decisions = {
        row["case_id"]: row
        for row in (
            json.loads(line)
            for line in (
                ROOT
                / "research/v3_5/stage3r_qc/phase_b/input_freeze/"
                "approved_query_decisions.jsonl"
            )
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
    }
    for row in rows():
        expected = decisions[row["case_id"]]
        assert row["hybrid"]["q1"]["query"] == expected["q1_discovery_query"]
        assert row["hybrid"]["q2"]["intents"] == expected["q2_retrieval_intents"]


def test_stage3r_qc_phase_b_r_records_auto_router_decisions():
    distribution = load_json("analysis/router_distribution.json")
    assert distribution["product_default"]["q0_router_distribution"] == {
        "not_invoked_explicit_lexical": 10
    }
    assert all(row["hybrid"]["q0"]["router_invoked"] is False for row in rows())


def test_stage3r_qc_phase_b_r_uses_canonical_video_identity():
    assert all(row["identity_failure"] is False for row in rows())
    assert load_json("tests/contract_summary.json")["canonical_identity_used"] is True


def test_stage3r_qc_phase_b_r_q2_only_unions_video_identities():
    summaries = list((OUT / "execution/hybrid/q2/cases").glob("*/q2_union.json"))
    assert len(summaries) == 10
    for path in summaries:
        value = json.loads(path.read_text(encoding="utf-8"))
        assert value["merge_rule"] == "union_of_canonical_video_identities"
        assert all("canonical_video_identity" in item for item in value["union"])


def test_stage3r_qc_phase_b_r_does_not_rerank_q2_union():
    for path in (OUT / "execution/hybrid/q2/cases").glob("*/q2_union.json"):
        assert json.loads(path.read_text(encoding="utf-8"))["cross_intent_rerank"] is False


def test_stage3r_qc_phase_b_r_excludes_insufficient_from_main_recall():
    metrics = load_json("analysis/retrieval_matrix.json")
    assert all(
        metrics[view][kind]["denominator"] == 9
        for view in ("lexical", "product_default", "hybrid")
        for kind in ("q0_recall", "q1_recall", "q2_recall")
    )


def test_stage3r_qc_phase_b_r_reports_insufficient_separately():
    value = load_json("analysis/insufficient_diagnostic.json")
    assert value["case_id"] == "C2C_ee3fac675fc7d408"
    assert value["label_role"] == "insufficient_diagnostic"


def test_stage3r_qc_phase_b_r_classifies_query_contract_per_mode():
    assert classify_query_contract(False, True, False) == "single_intent_contract_recoverable"
    assert classify_query_contract(False, False, True) == "decomposition_recoverable"
    assert {row["hybrid"]["query_contract_classification"] for row in rows()} == {
        "already_retrievable"
    }


def test_stage3r_qc_phase_b_r_classifies_retrieval_mode_across_modes():
    assert classify_retrieval_mode(False, False, True) == "explicit_hybrid_required"
    evidence = [row for row in rows() if row["label_role"] == "evidence_bearing"]
    assert {row["retrieval_mode_classification"] for row in evidence} == {
        "explicit_hybrid_required"
    }


def test_stage3r_qc_phase_b_r_only_calls_persistent_after_hybrid_miss():
    assert classify_retrieval_mode(False, False, False) == "persistent_across_modes"
    effect = load_json("analysis/retrieval_mode_effect.json")
    assert effect["persistent_across_modes_count"] == 0
    assert effect["product_to_hybrid_recovery_count"] == 9
