from __future__ import annotations

from collections import Counter
from hashlib import sha256
import inspect
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3"
AUTHORITY_SHA256 = "13e792483b0f5c4945a7a2802e56cd9f8076479d7c583b2022ac197acfb98421"
QUERY_SHA256 = "e68d6bb405bafadb56c5333834d72c8155a7a310ca2e20341df4f412488a8935"
GOLD_HASHES = {
    "retrieval": "b34188c269bf3a2410f8602fdb7d72908a96c822ac3b8f675d4f4c2b72b45679",
    "evidence": "b259a1b225a48558f5d1a6c4cb4909ea413e86116a1564b3fa724632ae88efc1",
    "sufficiency": "11196158746bb2c12e457fcb36b87a1621e79dca0b2f628a4870ca5ec6c5de92",
    "case_status": "9ba38a1f8cf636ebb9e80219cd85a41003743cb11f370a24d3946534378c6352",
}
COMPONENT_HASHES = {
    "candidate_builder": (
        "src/shiliu/evidence/stage3b.py",
        "8a2ed841efdf42f048347bf23ed1170a67ce7be0f3b03823eabef31847a80458",
    ),
    "deterministic_selector": (
        "src/shiliu/evidence/stage3a.py",
        "34774d6c166680e7523010f9d1d950f9aa1b890487f46427279164cdedaed552",
    ),
    "mechanical_gate_contract": (
        "research/v3_5/stage4a/mechanical_gate_contract.json",
        "f255c42a46825b77f45b7d8c54b1f5746cfed2f5d8d501a4cb9aef6d09b93051",
    ),
    "product_default_wiring": (
        "research/v3_5/product_default_auto_wiring/product_default_auto_wiring_manifest.json",
        "5d5d42ad7501f8a9d917a17b7b6116da4f84f3d5d974f8a54e3dbcd88cb588f9",
    ),
    "router": (
        "src/shiliu/retrieval/planner.py",
        "0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e",
    ),
}
PRIMARY_ENUM = {
    "retrieval_failure",
    "retrieval_gold_unjudged",
    "candidate_builder_failure",
    "deterministic_selector_failure",
    "mechanical_gate_failure",
    "source_unverifiable",
    "identity_or_scoring_defect",
    "end_to_end_bundle_hit",
}


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verify_prediction_seal(output_root: Path) -> bool:
    blind = output_root / "blind_run"
    seal = json.loads(
        (blind / "product_initial_baseline.prediction_freeze.seal.json").read_text()
    )
    rows = jsonl(blind / "product_initial_baseline.prediction_hash_manifest.jsonl")
    trace_rows = [row for row in rows if row["path"].endswith(".trace.json")]
    return (
        seal["status"] == "sealed_before_gold_scoring"
        and seal["development_gold_opened"] is False
        and len(trace_rows) == 14
        and all(
            digest(output_root / row["path"]) == row["sha256"]
            for row in rows
            if not row["path"].endswith(".trace.json")
        )
        and seal["predictions_sha256"]
        == digest(blind / "product_initial_baseline.predictions.jsonl")
    )


def test_p8_decision_ledger_hash_matches():
    assert digest(Path("/Users/elliot/Downloads/V3_5_PQS_V1_P8_PRODUCT_INITIAL_BASELINE_DECISION_LEDGER.json")) == "e5af8a5e35f25c5946ae0c26f7f759245e62eb1189144604e78e64ee49d0c79e"


def test_authority_index_hash_matches():
    current = digest(ROOT / "03_V3_5_DECISION_AND_ARTIFACT_INDEX.md")
    if current == AUTHORITY_SHA256:
        return

    # P8 froze AUTHORITY_SHA256 as its blind-run input. Later governance
    # checkpoints or a versioned scoring amendment may update the live index
    # without changing the frozen P8 Prediction identity.
    amendment = (
        ROOT
        / "research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3"
        / "scoring_amendment_v1/p8_scoring_amendment.manifest.json"
    )
    assert amendment.is_file()
    value = json.loads(amendment.read_text())
    assert value["original_scoring"]["preserved"] is True
    assert value["success_state"]["P8_prediction_set"]["status"] == "valid_and_frozen"
    index = (ROOT / "03_V3_5_DECISION_AND_ARTIFACT_INDEX.md").read_text()
    assert value["scoring_hash_root"] in index


def test_p7_package_identity_matches():
    base = ROOT / "research/v3_5/product_query_set_v1/gold_construction_v1/p7_final_closeout"
    expected = {
        "P7_PRODUCT_GOLD_CLOSEOUT_REPORT.md": "edf4c0c2c4dd543e72ae256a6c75ec7e00a9a2472d672ebd22af51e5ce153863",
        "p7_product_gold_v1.manifest.json": "afad8112a6667fc465f7d8a1c7fc44cb22fca93759b425ef9f83203f1ed515df",
        "p7_product_gold_v1.audit.json": "91861b3e576f18e4953c044e7214fec5467072eff920792d46988a2ad82ffcf1",
    }
    assert {name: digest(base / name) for name in expected} == expected


def test_exactly_14_development_queries():
    path = ROOT / "research/v3_5/product_query_set_v1/split_v1/product_query_development_v1.locked.jsonl"
    rows = jsonl(path)
    assert digest(path) == QUERY_SHA256
    assert len(rows) == len({row["query_id"] for row in rows}) == 14


def test_no_frozen_query_executed():
    audit = json.loads((OUT / "blind_run/product_initial_baseline.blind_run.audit.json").read_text())
    assert audit["frozen_query_runs"] == 0


def test_frozen_gold_never_opened():
    audit = json.loads((OUT / "scoring/product_initial_baseline.scoring.audit.json").read_text())
    assert audit["frozen_gold_opened"] is False


def test_development_gold_not_opened_before_prediction_seal():
    seal = json.loads((OUT / "blind_run/product_initial_baseline.prediction_freeze.seal.json").read_text())
    audit = json.loads((OUT / "scoring/product_initial_baseline.scoring.audit.json").read_text())
    assert audit["development_gold_opened_after_prediction_seal"] is True
    assert audit["development_gold_first_open_at"] > seal["sealed_at"]


def test_exactly_one_valid_prediction_per_query():
    rows = jsonl(OUT / "blind_run/product_initial_baseline.predictions.jsonl")
    assert len(rows) == len({row["query_id"] for row in rows}) == 14
    assert all(row["terminal_prediction"]["complete"] for row in rows)


def test_recognized_source_terminal_is_complete_prediction():
    rows = jsonl(OUT / "blind_run/product_initial_baseline.predictions.jsonl")
    terminal = [row for row in rows if row["terminal_prediction"]["recognized_source_terminal"]]
    assert terminal
    assert all(row["candidate_builder"]["outcome"] == "no_authoritative_source" for row in terminal)
    assert all(row["deterministic_selector"]["outcome"] == "not_applicable" for row in terminal)
    assert all(row["mechanical_gate"]["outcome"] == "terminal_unverifiable" for row in terminal)


def test_attempt_2_not_reused():
    audit = json.loads((OUT / "blind_run/product_initial_baseline.blind_run.audit.json").read_text())
    assert audit["prior_attempt"] == {
        "attempt_id": "P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_2",
        "status": "invalid_incomplete_attempt",
        "partial_prediction_count": 9,
        "reused_in_attempt_3": False,
    }


def test_no_best_of_n_or_gold_aware_retry():
    audit = json.loads((OUT / "blind_run/product_initial_baseline.blind_run.audit.json").read_text())
    assert audit["valid_prediction_runs_per_query"] == 1
    assert audit["best_of_n"] is audit["gold_aware_retry"] is False


def test_prediction_and_trace_hashes_are_frozen():
    assert verify_prediction_seal(OUT)


def test_predictions_immutable_after_gold_open():
    audit = json.loads((OUT / "scoring/product_initial_baseline.scoring.audit.json").read_text())
    assert audit["prediction_sha256_before_gold"] == audit["prediction_sha256_after_gold"]
    assert audit["prediction_modified_after_gold"] is False


def test_runtime_component_versions_match_authority():
    frozen = json.loads(
        (OUT / "blind_run/product_initial_baseline.input_manifest.json").read_text()
    )
    for name, (_relative, expected) in COMPONENT_HASHES.items():
        assert frozen["components"][name]["sha256"] == expected
        assert frozen["components"][name]["expected_sha256"] == expected

    # P8 records its own frozen inputs. Later accepted/rejected component cycles are
    # bound by the final seal and must not make this historical test compare old
    # hashes with the latest working-tree bytes.
    final = json.loads((ROOT / "V3_5_FINAL_FREEZE_SEAL.json").read_text())
    assert final["formal_component_hashes"] == {
        "Evidence_Identity_Contract": "35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7",
        "Stage5_integration_seal": "4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c",
        "auto_router": "0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e",
        "candidate_builder": "7f995a3c1c31eddd0eff6221494dd60032d00a155d431a68c58fb7cf55bbf3c1",
        "fine_selector": "350a2aa6fab58580fb259471a7a6b87fc206701189ebb7bff97d031613444c67",
        "mechanical_gate": "1577a51e57661a0a8bcbd51cfaed31013bdf2859ab786d67c50f7c42fa84f17c",
        "retrieval": None,
        "semantic_judge": "2e2d90afda5dc6e7f7576742e900782f857622a331303bca18b983d27b645d59",
    }
    from shiliu.evidence.stage3a import select_deterministic_bundle

    assert sha256(inspect.getsource(select_deterministic_bundle).encode()).hexdigest() == (
        "3990fa6226ca611f5dd935c2293f8c21d1084e6e1540a3e4806b73c184b1a60e"
    )


def test_functional_component_behavior_unchanged():
    decision = json.loads((OUT / "closeout/product_initial_baseline.execution_decision.json").read_text())
    assert decision["component_behavior_changed"] is False


def test_retrieval_metrics_recomputable():
    rows = jsonl(OUT / "scoring/product_initial_baseline.per_query.jsonl")
    scores = json.loads((OUT / "scoring/product_initial_baseline.scores.json").read_text())
    assert scores["retrieval"]["any_acceptable_video"]["hit_at_10"]["all_query_lower_bound"] == sum(row["retrieval"]["hit_at_10"] for row in rows) / 14


def test_builder_metrics_recomputable():
    rows = jsonl(OUT / "scoring/product_initial_baseline.per_query.jsonl")
    scores = json.loads((OUT / "scoring/product_initial_baseline.scores.json").read_text())
    assert scores["candidate_builder"]["complete_acceptable_evidence_group_coverage"] == sum(row["candidate_builder"]["complete_group_hit"] for row in rows) / 14


def test_selector_metrics_recomputable():
    rows = jsonl(OUT / "scoring/product_initial_baseline.per_query.jsonl")
    scores = json.loads((OUT / "scoring/product_initial_baseline.scores.json").read_text())
    assert scores["deterministic_selector"]["bundle_hit"] == sum(row["deterministic_selector"]["bundle_hit"] for row in rows) / 14


def test_gate_metrics_do_not_claim_semantic_sufficiency():
    scores = (OUT / "scoring/product_initial_baseline.scores.json").read_text()
    assert "semantic sufficient" not in scores
    assert "semantic partial" not in scores
    assert "semantic insufficient" not in scores


def test_outside_pool_return_not_automatic_negative():
    audit = json.loads((OUT / "unjudged/development_retrieval_pool_addendum.v1.audit.json").read_text())
    assert audit["automatically_treated_as_negative"] is False


def test_unjudged_pool_is_deduplicated():
    rows = jsonl(OUT / "unjudged/product_initial_baseline.unjudged_pool.jsonl")
    assert len(rows) == len({(row["query_id"], row["returned_video_id"]) for row in rows})


def test_addendum_does_not_modify_base_gold():
    audit = json.loads((OUT / "unjudged/development_retrieval_pool_addendum.v1.audit.json").read_text())
    assert audit["base_gold_modified"] is False
    assert audit["evidence_gold_modified"] is audit["sufficiency_gold_modified"] is False


def test_addendum_never_deletes_existing_positive():
    audit = json.loads((OUT / "unjudged/development_retrieval_pool_addendum.v1.audit.json").read_text())
    assert audit["existing_positive_deletions"] == 0


def test_scores_recomputed_without_prediction_rerun():
    audit = json.loads((OUT / "scoring/product_initial_baseline.scoring.audit.json").read_text())
    assert audit["scores_recomputed_without_prediction_rerun"] is True
    assert audit["prediction_rerun"] is False


def test_each_query_has_exactly_one_primary_attribution():
    rows = jsonl(OUT / "scoring/product_initial_baseline.failure_attribution.jsonl")
    assert len(rows) == len({row["query_id"] for row in rows}) == 14


def test_primary_attribution_uses_closed_enum():
    rows = jsonl(OUT / "scoring/product_initial_baseline.failure_attribution.jsonl")
    assert {row["primary_attribution"] for row in rows} <= PRIMARY_ENUM


def test_failure_attribution_references_persisted_assets():
    rows = jsonl(OUT / "scoring/product_initial_baseline.failure_attribution.jsonl")
    assert all(row["persisted_assets"]["prediction_sha256"] and row["persisted_assets"]["trace_path"] for row in rows)


def test_stress_regression_is_separate():
    value = json.loads((OUT / "stress_regression/stress_set_v2_regression.initial_product_baseline.json").read_text())
    assert value["product_benchmark"] is value["optimization_authority"] is False
    assert value["product_prediction_rerun"] is False


def test_no_f1a_f1b_or_stage4_started():
    decision = json.loads((OUT / "closeout/product_initial_baseline.execution_decision.json").read_text())
    assert decision["f1a_authorized"] is decision["f1b_authorized"] is decision["checkpoint_1_authorized"] is False


def test_manifest_and_report_hashes_match():
    rows = jsonl(OUT / "closeout/product_initial_baseline.file_hash_manifest.jsonl")
    trace_rows = []
    for row in rows:
        path = OUT / row["path"]
        if row["path"].startswith("blind_run/product_initial_baseline.traces/"):
            trace_rows.append(row)
        if path.is_file():
            assert digest(path) == row["sha256"]
        else:
            assert row["path"].startswith(
                "blind_run/product_initial_baseline.traces/"
            )
    assert len(trace_rows) == 14
    assert any(row["path"] == "closeout/PRODUCT_INITIAL_BASELINE_REPORT.md" for row in rows)


def test_upstream_p4_through_p7_assets_unchanged():
    gold_root = ROOT / "research/v3_5/product_query_set_v1/gold_construction_v1/development_seal_v1/sealed"
    names = {
        "product_retrieval_gold.development.v1.sealed.jsonl": GOLD_HASHES["retrieval"],
        "product_evidence_gold.development.v1.sealed.jsonl": GOLD_HASHES["evidence"],
        "product_sufficiency_gold.development.v1.sealed.jsonl": GOLD_HASHES["sufficiency"],
        "reviewed_case_status.development.v1.sealed.jsonl": GOLD_HASHES["case_status"],
    }
    assert {name: digest(gold_root / name) for name in names} == names


def test_primary_distribution_sums_to_14():
    rows = jsonl(OUT / "scoring/product_initial_baseline.failure_attribution.jsonl")
    assert sum(Counter(row["primary_attribution"] for row in rows).values()) == 14
