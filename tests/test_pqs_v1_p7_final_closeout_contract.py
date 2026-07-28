from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTION = ROOT / "research/v3_5/product_query_set_v1/gold_construction_v1"
DEV = CONSTRUCTION / "development_seal_v1"
FROZEN_ROOT = CONSTRUCTION / "frozen_guarded"
FROZEN = FROZEN_ROOT / "frozen_cycle_v1"
OUT = CONSTRUCTION / "p7_final_closeout"
sys.path.insert(0, str(ROOT / "scripts"))
from validate_p7_product_gold_closeout import (  # noqa: E402
    EXPECTED_DEV_HASHES,
    EXPECTED_FROZEN_HASHES,
    collect_source_state,
    nonempty_line_count,
    query_ids_only,
    validate_closeout,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def j(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def jl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def source_paths() -> tuple[dict[str, Path], dict[str, Path]]:
    development = {
        "retrieval": DEV / "sealed/product_retrieval_gold.development.v1.sealed.jsonl",
        "evidence": DEV / "sealed/product_evidence_gold.development.v1.sealed.jsonl",
        "sufficiency": DEV / "sealed/product_sufficiency_gold.development.v1.sealed.jsonl",
        "status": DEV / "sealed/reviewed_case_status.development.v1.sealed.jsonl",
    }
    frozen = {
        "retrieval": FROZEN / "sealed/product_retrieval_gold.frozen.v1.sealed.jsonl",
        "evidence": FROZEN / "sealed/product_evidence_gold.frozen.v1.sealed.jsonl",
        "sufficiency": FROZEN / "sealed/product_sufficiency_gold.frozen.v1.sealed.jsonl",
        "status": FROZEN / "sealed/reviewed_case_status.frozen.v1.sealed.jsonl",
    }
    return development, frozen


def test_p7_closeout_ledger_hash_matches() -> None:
    assert sha(OUT / "PQS_V1_P7_FINAL_CLOSEOUT_DECISION_LEDGER.json") == (
        "5fd179b5a89cfff5d9eda326dde5bd245a9c380a91de1909af1462d654288953"
    )


def test_development_gold_seal_identity_matches() -> None:
    assert sha(DEV / "development_gold_v1.seal.json") == EXPECTED_DEV_HASHES["seal"]
    assert sha(DEV / "development_gold_v1.manifest.json") == EXPECTED_DEV_HASHES["manifest"]
    assert sha(DEV / "development_gold_v1.audit.json") == EXPECTED_DEV_HASHES["audit"]


def test_frozen_gold_seal_identity_matches() -> None:
    assert sha(FROZEN / "internal_protected/frozen_gold_v1.seal.json") == (
        EXPECTED_FROZEN_HASHES["seal"]
    )
    assert sha(FROZEN / "internal_protected/product_gold_frozen_v1.manifest.json") == (
        EXPECTED_FROZEN_HASHES["manifest"]
    )
    assert sha(FROZEN / "internal_protected/frozen_gold_v1.audit.json") == (
        EXPECTED_FROZEN_HASHES["audit"]
    )
    assert sha(FROZEN_ROOT / "FROZEN_PACKET_ACCESS_GUARD.json") == (
        EXPECTED_FROZEN_HASHES["guard"]
    )


def test_exactly_24_locked_queries() -> None:
    locked = ROOT / "research/v3_5/product_query_set_v1/freeze/product_query_set_v1.locked.jsonl"
    assert len(query_ids_only(locked)) == 24


def test_exactly_14_development_queries() -> None:
    development, _ = source_paths()
    assert len(query_ids_only(development["retrieval"])) == 14


def test_exactly_10_frozen_queries() -> None:
    _, frozen = source_paths()
    assert len(query_ids_only(frozen["retrieval"])) == 10


def test_development_and_frozen_are_disjoint() -> None:
    development, frozen = source_paths()
    assert query_ids_only(development["retrieval"]).isdisjoint(
        query_ids_only(frozen["retrieval"])
    )


def test_union_equals_locked_product_query_set() -> None:
    development, frozen = source_paths()
    locked = ROOT / "research/v3_5/product_query_set_v1/freeze/product_query_set_v1.locked.jsonl"
    assert query_ids_only(development["retrieval"]) | query_ids_only(frozen["retrieval"]) == (
        query_ids_only(locked)
    )


def test_no_missing_duplicate_or_unexpected_query() -> None:
    state = collect_source_state()
    assert state["missing"] == state["duplicate"] == state["unexpected"] == 0


def test_three_layers_have_24_total_records_each() -> None:
    development, frozen = source_paths()
    for layer in ("retrieval", "evidence", "sufficiency"):
        assert nonempty_line_count(development[layer]) == 14
        assert nonempty_line_count(frozen[layer]) == 10
        assert nonempty_line_count(development[layer]) + nonempty_line_count(frozen[layer]) == 24


def test_case_status_has_24_total_records() -> None:
    development, frozen = source_paths()
    assert nonempty_line_count(development["status"]) == 14
    assert nonempty_line_count(frozen["status"]) == 10


def test_no_unresolved_case() -> None:
    assert j(DEV / "development_gold_v1.seal.json")["review_status"]["pending"] == 0
    assert (
        j(FROZEN / "internal_protected/frozen_gold_v1.seal.json")[
            "pending_user_adjudication"
        ]
        == 0
    )
    assert j(OUT / "p7_product_gold_v1.audit.json")["resolution"]["total_pending"] == 0


def test_both_gold_versions_formally_sealed() -> None:
    manifest = j(OUT / "p7_product_gold_v1.manifest.json")
    assert manifest["development_gold"]["formally_sealed_by_v3_5_b"]
    assert manifest["frozen_gold"]["formally_sealed_by_v3_5_b"]


def test_sealed_artifact_hashes_unchanged() -> None:
    development, frozen = source_paths()
    assert all(
        sha(development[layer]) == EXPECTED_DEV_HASHES[layer]
        for layer in development
    )
    assert all(
        sha(frozen[layer]) == EXPECTED_FROZEN_HASHES[layer]
        for layer in frozen
    )


def test_p7_manifest_references_without_copying_gold() -> None:
    manifest = j(OUT / "p7_product_gold_v1.manifest.json")
    assert manifest["development_gold"]["seal_path"]
    assert manifest["frozen_gold"]["seal_path"]
    assert not list(OUT.glob("*gold*.sealed.jsonl"))
    assert not list(OUT.glob("*gold*.reviewed.jsonl"))


def test_p7_report_contains_no_case_level_gold() -> None:
    report = (OUT / "P7_PRODUCT_GOLD_CLOSEOUT_REPORT.md").read_text(encoding="utf-8")
    forbidden = (
        "PQS_V1_Q",
        "quote_text",
        "span_registry",
        "required_aspects",
        "supported_aspects",
        "missing_aspects",
        "reason_codes",
        "bilibili:",
    )
    assert not any(token in report for token in forbidden)


def test_no_frozen_gold_leakage() -> None:
    audit = j(OUT / "p7_product_gold_v1.audit.json")
    assert not audit["scope"]["frozen_gold_leakage_detected"]


def test_no_semantic_content_opened() -> None:
    assert not j(OUT / "p7_product_gold_v1.audit.json")["scope"]["semantic_content_opened"]


def test_no_product_prediction_or_pipeline_access() -> None:
    scope = j(OUT / "p7_product_gold_v1.audit.json")["scope"]
    assert not scope["product_prediction_read"]
    assert scope["product_pipeline_calls"] == 0


def test_p8_not_started() -> None:
    decision = j(OUT / "p7_product_gold_v1.execution_decision.json")
    assert not decision["p8_authorized"]
    assert not j(OUT / "p7_product_gold_v1.audit.json")["scope"]["p8_started"]


def test_upstream_assets_unchanged() -> None:
    collect_source_state()
    assert sha(
        ROOT / "research/v3_5/product_query_set_v1/freeze/product_query_set_v1.locked.jsonl"
    ) == "35d33dcf4dd77f12cad4e0c118f2c2f2e371a3019320906a3d2134bb933dd59c"


def test_closeout_hash_manifest_matches() -> None:
    for row in jl(OUT / "p7_product_gold_v1.file_hash_manifest.jsonl"):
        assert sha(OUT / row["path"]) == row["sha256"]


def test_full_closeout_validator_passes() -> None:
    result = validate_closeout()
    assert result["status"] == "passed"
    assert result["total_query_count"] == 24
    assert result["scope_violation_count"] == 0
