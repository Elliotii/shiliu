from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = (
    ROOT / "research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3"
)
AMENDMENT = BASELINE / "scoring_amendment_v1"
EXPECTED_SEAL_SHA256 = (
    "069fcf9e3ec70cf28d23674a2752033e608bf46937c990176dd6fb52f9e04617"
)
EXPECTED_PREDICTIONS_SHA256 = (
    "b34f173ac99208f4adb72966880ab7e9cf97d3e27157084792502f103e709038"
)
EXPECTED_LEDGER_SHA256 = (
    "2c8c8502da58e835cf23d7d6c6df41f2e5bde7484cee7a9ab9fe3def23bfc5e9"
)


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text().splitlines() if line.strip()
    ]


def per_query() -> list[dict]:
    return load_jsonl(AMENDMENT / "p8_scoring_amendment.per_query.jsonl")


def scores() -> dict:
    return load_json(AMENDMENT / "p8_scoring_amendment.scores.json")


def test_prediction_seal_unchanged() -> None:
    assert (
        digest(BASELINE / "blind_run/product_initial_baseline.prediction_freeze.seal.json")
        == EXPECTED_SEAL_SHA256
    )
    assert (
        digest(BASELINE / "blind_run/product_initial_baseline.predictions.jsonl")
        == EXPECTED_PREDICTIONS_SHA256
    )
    audit = load_json(AMENDMENT / "p8_scoring_amendment.audit.json")
    assert audit["identity"]["trace_count"] == 14
    assert audit["identity"]["traces_unchanged"] is True


def test_amendment_ledger_hash_matches() -> None:
    assert (
        digest(
            AMENDMENT
            / "V3_5_P8_SCORING_CHECKPOINT_1_AMENDMENT_DECISION_LEDGER.json"
        )
        == EXPECTED_LEDGER_SHA256
    )


def test_zero_acceptable_group_not_builder_failure_eligible() -> None:
    rows = [
        row
        for row in per_query()
        if row["gold_eligibility"]["acceptable_evidence_group_count"] == 0
    ]
    assert len(rows) == 1
    assert rows[0]["gold_eligibility"]["eligible_for_candidate_builder_failure"] is False
    assert rows[0]["primary_attribution"] == "gold_defined_evidence_absent"


def test_zero_acceptable_group_excluded_from_complete_group_denominator() -> None:
    metric = scores()["candidate_builder"][
        "complete_acceptable_evidence_group_coverage"
    ]
    assert metric["numerator"] == 6
    assert metric["denominator"] == metric["eligible_query_count"] == 13
    assert metric["excluded_query_count"] == 1
    assert len(metric["excluded_query_ids"]) == 1


def test_q017_has_non_builder_generic_attribution() -> None:
    row = next(row for row in per_query() if row["query_id"] == "PQS_V1_Q017")
    assert row["primary_attribution"] == "gold_defined_evidence_absent"
    assert row["gold_eligibility"]["required_material_evidence_constructible"] is False


def test_no_query_id_specific_scoring_rule() -> None:
    source = (ROOT / "src/shiliu/eval_v3_5/p8_scoring_amendment.py").read_text()
    scoring_contract = source[: source.index("def generate(")]
    assert "PQS_V1_Q017" not in scoring_contract
    assert "Q017" not in scoring_contract
    assert "video_id ==" not in scoring_contract


def test_all_primary_attributions_meet_eligibility() -> None:
    for row in per_query():
        primary = row["primary_attribution"]
        eligibility = row["gold_eligibility"]
        if primary == "candidate_builder_failure":
            assert eligibility["eligible_for_candidate_builder_failure"] is True
            assert eligibility["acceptable_evidence_group_count"] > 0
            assert eligibility["required_material_evidence_constructible"] is True
            assert row["candidate_builder"]["complete_group_hit"] is False
        elif primary == "deterministic_selector_failure":
            assert row["candidate_builder"]["complete_group_hit"] is True
            assert row["deterministic_selector"]["bundle_hit"] is False
        elif primary == "end_to_end_bundle_hit":
            assert row["deterministic_selector"]["bundle_hit"] is True
        elif primary == "source_unverifiable":
            assert row["mechanical_gate"]["outcome"] == "terminal_unverifiable"
        elif primary == "gold_defined_evidence_absent":
            assert eligibility["acceptable_evidence_group_count"] == 0
            assert eligibility["required_material_evidence_constructible"] is False
        else:
            raise AssertionError(f"unexpected amended primary attribution: {primary}")


def test_exactly_one_primary_attribution_per_query() -> None:
    rows = load_jsonl(
        AMENDMENT / "p8_scoring_amendment.failure_attribution.jsonl"
    )
    assert len(rows) == len({row["query_id"] for row in rows}) == 14
    assert all(row["primary_attribution"] for row in rows)


def test_retrieval_metrics_unchanged_unless_mechanically_affected() -> None:
    original = load_json(BASELINE / "scoring/product_initial_baseline.scores.json")
    assert scores()["retrieval"] == original["retrieval"]


def test_builder_metric_denominators_are_explicit() -> None:
    builder = scores()["candidate_builder"]
    for name in (
        "complete_acceptable_evidence_group_coverage",
        "required_span_recall_macro",
        "required_aspect_coverage_macro",
        "primary_failure_count",
    ):
        metric = builder[name]
        assert {
            "numerator",
            "denominator",
            "eligible_query_count",
            "excluded_query_count",
            "excluded_query_ids",
            "exclusion_reason",
        } <= set(metric)
    assert builder["complete_acceptable_evidence_group_coverage"]["denominator"] == 13
    assert builder["required_span_recall_macro"]["denominator"] == 13
    assert builder["required_aspect_coverage_macro"]["denominator"] == 13
    assert builder["primary_failure_count"]["denominator"] == 12


def test_original_scoring_preserved_and_superseded() -> None:
    manifest = load_json(AMENDMENT / "p8_scoring_amendment.manifest.json")
    assert manifest["original_scoring"]["preserved"] is True
    assert (
        manifest["original_scoring"]["status"]
        == "superseded_by_scoring_amendment"
    )
    assert (
        digest(BASELINE / "scoring/product_initial_baseline.scores.json")
        == "30cce533265015cfcc5fd35992e43583d9f2a968928d2e012a9f49ee6c07466d"
    )


def test_no_prediction_component_or_gold_change() -> None:
    audit = load_json(AMENDMENT / "p8_scoring_amendment.audit.json")
    assert audit["identity"]["predictions_unchanged"] is True
    assert audit["identity"]["development_gold_unchanged"] is True
    assert all(
        audit["execution"][key] is False
        for key in (
            "retrieval_rerun",
            "builder_rerun",
            "selector_rerun",
            "gate_rerun",
            "prediction_rerun",
            "trace_rerun",
        )
    )


def test_no_frozen_access_and_no_downstream_start() -> None:
    audit = load_json(AMENDMENT / "p8_scoring_amendment.audit.json")
    decision = load_json(
        AMENDMENT / "p8_scoring_amendment.execution_decision.json"
    )
    assert audit["identity"]["frozen_gold_opened"] is False
    assert decision["P9"]["restarted"] is False
    assert decision["F1A_authorized"] is False
    assert decision["F1B_authorized"] is False
    assert decision["Stage4_started"] is False


def test_manifest_hashes_match() -> None:
    rows = load_jsonl(
        AMENDMENT / "p8_scoring_amendment.file_hash_manifest.jsonl"
    )
    assert len(rows) == 8
    for row in rows:
        assert digest(ROOT / row["path"]) == row["sha256"]

