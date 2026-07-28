"""Aggregate-only mechanical validator for P7 Product Gold Final Closeout."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTION = ROOT / "research/v3_5/product_query_set_v1/gold_construction_v1"
DEV = CONSTRUCTION / "development_seal_v1"
FROZEN_ROOT = CONSTRUCTION / "frozen_guarded"
FROZEN = FROZEN_ROOT / "frozen_cycle_v1"
OUT = CONSTRUCTION / "p7_final_closeout"
LOCKED = ROOT / "research/v3_5/product_query_set_v1/freeze/product_query_set_v1.locked.jsonl"
P5 = ROOT / "research/v3_5/product_query_set_v1/split_v1/product_query_split_v1.locked.json"

EXPECTED_LEDGER_HASH = "5fd179b5a89cfff5d9eda326dde5bd245a9c380a91de1909af1462d654288953"
EXPECTED_LOCKED_HASH = "35d33dcf4dd77f12cad4e0c118f2c2f2e371a3019320906a3d2134bb933dd59c"
EXPECTED_DEV_HASHES = {
    "retrieval": "b34188c269bf3a2410f8602fdb7d72908a96c822ac3b8f675d4f4c2b72b45679",
    "evidence": "b259a1b225a48558f5d1a6c4cb4909ea413e86116a1564b3fa724632ae88efc1",
    "sufficiency": "11196158746bb2c12e457fcb36b87a1621e79dca0b2f628a4870ca5ec6c5de92",
    "status": "9ba38a1f8cf636ebb9e80219cd85a41003743cb11f370a24d3946534378c6352",
    "seal": "1010fb635680bacc72c9aac8cbd096494370cd0709ed1d746754a0eade90cb5a",
    "manifest": "5fbed371246b2589cdfca1456f96da64142ea627d8b29fe1872fd1606c1505dc",
    "audit": "24bf42c63b7c62efe2e8753b33a19e41b2662b8781320da76b2bf4ec10be8451",
}
EXPECTED_FROZEN_HASHES = {
    "retrieval": "2f53b9294a7211b4371aadc934d1ec1a178b2a0fa00ee1b9b4177737b7b4ca34",
    "evidence": "b47235b273640fedf4754dfcb9983b733655ed80730d07ba12700987d4c30827",
    "sufficiency": "ccc7b0bfe35e78c5eec50ccb3c972b327bd400437f442d70da94e3f9df07b69a",
    "status": "67db16cfe9b4736ad2e8cd81ce77cd9d4b5f952506303b21c8abdb4cddba9259",
    "seal": "166e7c463de06e31d6c831d97c00f54dcf149312fb77cb66505bf15985c584a8",
    "manifest": "3978a4339f791c0faf102be9b565148f07836317b96df7a6a10116226b7725e9",
    "audit": "b921cef2de6cfe05fbad9979007955b0fc3753f9e694957ae4c9e44772465ac2",
    "guard": "e6b8047dab9b83a6c0f8c26633b869d227dd175188c32f660cf50aa4e8921e88",
}
QUERY_ID_RE = re.compile(r'"query_id"\s*:\s*"([^"]+)"')
FORBIDDEN_REPORT_TOKENS = (
    "quote_text",
    "span_registry",
    "required_aspects",
    "supported_aspects",
    "missing_aspects",
    "reason_codes",
    "known_relevant_video_ids",
    "acceptable_video_ids",
    "hard_negative_video_ids",
    "bilibili:",
)


class CloseoutValidationError(ValueError):
    pass


def fail(category: str) -> None:
    raise CloseoutValidationError(category)


def sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        fail("artifact_identity_failure")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("aggregate_metadata_failure")
    if not isinstance(value, dict):
        fail("aggregate_metadata_failure")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        values = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError):
        fail("aggregate_metadata_failure")
    if not all(isinstance(value, dict) for value in values):
        fail("aggregate_metadata_failure")
    return values


def nonempty_line_count(path: Path) -> int:
    try:
        return sum(bool(line.strip()) for line in path.read_text(encoding="utf-8").splitlines())
    except OSError:
        fail("record_count_failure")


def query_ids_only(path: Path) -> set[str]:
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        fail("query_identity_failure")
    values: list[str] = []
    for line in lines:
        matches = QUERY_ID_RE.findall(line)
        if len(matches) != 1:
            fail("query_identity_failure")
        values.append(matches[0])
    if len(values) != len(set(values)):
        fail("query_identity_failure")
    return set(values)


def paths() -> dict[str, dict[str, Path]]:
    return {
        "development": {
            "retrieval": DEV / "sealed/product_retrieval_gold.development.v1.sealed.jsonl",
            "evidence": DEV / "sealed/product_evidence_gold.development.v1.sealed.jsonl",
            "sufficiency": DEV / "sealed/product_sufficiency_gold.development.v1.sealed.jsonl",
            "status": DEV / "sealed/reviewed_case_status.development.v1.sealed.jsonl",
            "seal": DEV / "development_gold_v1.seal.json",
            "manifest": DEV / "development_gold_v1.manifest.json",
            "audit": DEV / "development_gold_v1.audit.json",
        },
        "frozen": {
            "retrieval": FROZEN / "sealed/product_retrieval_gold.frozen.v1.sealed.jsonl",
            "evidence": FROZEN / "sealed/product_evidence_gold.frozen.v1.sealed.jsonl",
            "sufficiency": FROZEN / "sealed/product_sufficiency_gold.frozen.v1.sealed.jsonl",
            "status": FROZEN / "sealed/reviewed_case_status.frozen.v1.sealed.jsonl",
            "seal": FROZEN / "internal_protected/frozen_gold_v1.seal.json",
            "manifest": FROZEN / "internal_protected/product_gold_frozen_v1.manifest.json",
            "audit": FROZEN / "internal_protected/frozen_gold_v1.audit.json",
            "guard": FROZEN_ROOT / "FROZEN_PACKET_ACCESS_GUARD.json",
        },
    }


def validate_hash_manifest(root: Path, manifest_path: Path) -> None:
    for row in read_jsonl(manifest_path):
        relative = row.get("path")
        expected = row.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            fail("source_hash_manifest_failure")
        target = root / relative
        if not target.is_file() or sha(target) != expected:
            fail("source_hash_manifest_failure")


def collect_source_state() -> dict[str, Any]:
    source_paths = paths()
    if sha(LOCKED) != EXPECTED_LOCKED_HASH:
        fail("p4_locked_identity_failure")
    for key, expected in EXPECTED_DEV_HASHES.items():
        if sha(source_paths["development"][key]) != expected:
            fail("development_identity_failure")
    for key, expected in EXPECTED_FROZEN_HASHES.items():
        if sha(source_paths["frozen"][key]) != expected:
            fail("frozen_identity_failure")

    validate_hash_manifest(DEV, DEV / "development_gold_v1.file_hash_manifest.jsonl")
    validate_hash_manifest(
        FROZEN,
        FROZEN / "internal_protected/frozen_gold_v1.file_hash_manifest.jsonl",
    )

    locked_ids = query_ids_only(LOCKED)
    development_ids = query_ids_only(source_paths["development"]["retrieval"])
    frozen_ids = query_ids_only(source_paths["frozen"]["retrieval"])
    split = read_json(P5)
    if (
        set(split.get("development", {}).get("query_ids", [])) != development_ids
        or set(split.get("frozen_evaluation", {}).get("query_ids", [])) != frozen_ids
    ):
        fail("p5_split_identity_failure")
    if (
        len(locked_ids) != 24
        or len(development_ids) != 14
        or len(frozen_ids) != 10
        or development_ids & frozen_ids
        or development_ids | frozen_ids != locked_ids
    ):
        fail("query_coverage_failure")

    record_counts = {
        group: {
            layer: nonempty_line_count(source_paths[group][layer])
            for layer in ("retrieval", "evidence", "sufficiency", "status")
        }
        for group in ("development", "frozen")
    }
    if set(record_counts["development"].values()) != {14}:
        fail("development_record_count_failure")
    if set(record_counts["frozen"].values()) != {10}:
        fail("frozen_record_count_failure")

    dev_seal = read_json(source_paths["development"]["seal"])
    frozen_seal = read_json(source_paths["frozen"]["seal"])
    if dev_seal.get("review_status", {}).get("pending") != 0:
        fail("development_unresolved_failure")
    if frozen_seal.get("pending_user_adjudication") != 0:
        fail("frozen_unresolved_failure")
    if dev_seal.get("immutability", {}).get("in_place_edit_forbidden") is not True:
        fail("development_immutability_failure")
    if frozen_seal.get("byte_identical_copy") is not True:
        fail("frozen_immutability_failure")

    return {
        "locked_query_count": 24,
        "development_query_count": 14,
        "frozen_query_count": 10,
        "disjoint": True,
        "union_equals_locked": True,
        "duplicate": 0,
        "missing": 0,
        "unexpected": 0,
        "record_counts": record_counts,
        "total_each_layer": 24,
        "unresolved": 0,
        "source_hashes": {
            "development": EXPECTED_DEV_HASHES,
            "frozen": EXPECTED_FROZEN_HASHES,
        },
    }


def validate_closeout() -> dict[str, Any]:
    state = collect_source_state()
    ledger = OUT / "PQS_V1_P7_FINAL_CLOSEOUT_DECISION_LEDGER.json"
    if sha(ledger) != EXPECTED_LEDGER_HASH:
        fail("decision_ledger_identity_failure")
    manifest = read_json(OUT / "p7_product_gold_v1.manifest.json")
    audit = read_json(OUT / "p7_product_gold_v1.audit.json")
    decision = read_json(OUT / "p7_product_gold_v1.execution_decision.json")
    if (
        manifest.get("locked_query_count") != 24
        or manifest.get("coverage", {}).get("disjoint") is not True
        or manifest.get("coverage", {}).get("union_equals_locked_query_set") is not True
        or manifest.get("resolution", {}).get("unresolved_cases") != 0
    ):
        fail("aggregate_manifest_failure")
    if (
        audit.get("coverage", {}).get("locked_queries") != 24
        or audit.get("resolution", {}).get("total_pending") != 0
        or audit.get("scope", {}).get("semantic_content_opened") is not False
        or audit.get("scope", {}).get("sealed_files_modified") is not False
        or audit.get("scope", {}).get("product_pipeline_calls") != 0
        or audit.get("scope", {}).get("p8_started") is not False
    ):
        fail("aggregate_audit_failure")
    expected_decision = {
        "acceptance_status": "pending_v3_5_b_review",
        "development_gold_formally_sealed": True,
        "execution_status": "complete",
        "frozen_gold_formally_sealed": True,
        "p7_product_gold_package_version": "PQS_V1_PRODUCT_GOLD_V1",
        "p7_status": "closeout_execution_candidate_ready",
        "p8_authorized": False,
        "total_query_count": 24,
        "unresolved_case_count": 0,
    }
    if decision != expected_decision:
        fail("execution_decision_failure")
    for row in read_jsonl(OUT / "p7_product_gold_v1.file_hash_manifest.jsonl"):
        relative = row.get("path")
        expected = row.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            fail("closeout_hash_manifest_failure")
        target = OUT / relative
        if not target.is_file() or sha(target) != expected:
            fail("closeout_hash_manifest_failure")
    report = (OUT / "P7_PRODUCT_GOLD_CLOSEOUT_REPORT.md").read_text(encoding="utf-8")
    if any(token in report for token in FORBIDDEN_REPORT_TOKENS):
        fail("closeout_report_leakage_failure")
    return {
        "status": "passed",
        "total_query_count": state["locked_query_count"],
        "development_query_count": state["development_query_count"],
        "frozen_query_count": state["frozen_query_count"],
        "total_each_layer": state["total_each_layer"],
        "unresolved_case_count": state["unresolved"],
        "scope_violation_count": 0,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(validate_closeout(), sort_keys=True))
    except CloseoutValidationError as exc:
        print(json.dumps({"status": "blocked", "category": str(exc)}, sort_keys=True))
        raise SystemExit(1)
