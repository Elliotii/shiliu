"""Mechanical validator for the DEVELOPMENT_GOLD_V1 execution candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from validate_development_gold_cycle import validate_replay
from validate_product_gold_protocol_v1 import validate_three_layer


ROOT = Path(__file__).resolve().parents[1]
CYCLE = ROOT / "research/v3_5/product_query_set_v1/gold_construction_v1/development_cycle"
SOURCE = CYCLE / "reviewed_gold_candidate"
OUT = ROOT / "research/v3_5/product_query_set_v1/gold_construction_v1/development_seal_v1"
SEALED = OUT / "sealed"
P5_DEVELOPMENT = (
    ROOT
    / "research/v3_5/product_query_set_v1/split_v1/"
    "product_query_development_v1.locked.jsonl"
)
EXPECTED_LEDGER_HASH = "6caeeb1898e9aef7ed401fba4d5b0285b4c84834b6e5a2416527b74aa9352651"
EXPECTED_REPORT_HASH = "5965d7d728b5f3d98b1b357e0bd79d3ae9394ab9bb94636ce569a5ad8a0e1a62"
SOURCE_TO_SEALED = {
    "product_retrieval_gold.development.reviewed.jsonl":
        "product_retrieval_gold.development.v1.sealed.jsonl",
    "product_evidence_gold.development.reviewed.jsonl":
        "product_evidence_gold.development.v1.sealed.jsonl",
    "product_sufficiency_gold.development.reviewed.jsonl":
        "product_sufficiency_gold.development.v1.sealed.jsonl",
    "reviewed_case_status.jsonl":
        "reviewed_case_status.development.v1.sealed.jsonl",
}
EXPECTED_SOURCE_HASHES = {
    "product_retrieval_gold.development.reviewed.jsonl":
        "b34188c269bf3a2410f8602fdb7d72908a96c822ac3b8f675d4f4c2b72b45679",
    "product_evidence_gold.development.reviewed.jsonl":
        "b259a1b225a48558f5d1a6c4cb4909ea413e86116a1564b3fa724632ae88efc1",
    "product_sufficiency_gold.development.reviewed.jsonl":
        "11196158746bb2c12e457fcb36b87a1621e79dca0b2f628a4870ca5ec6c5de92",
    "reviewed_case_status.jsonl":
        "9ba38a1f8cf636ebb9e80219cd85a41003743cb11f370a24d3946534378c6352",
}
DOWNSTREAM_PREFIXES = ("RET_", "BLD_", "SEL_", "GATE_", "JDG_", "SRC_")


class SealValidationError(ValueError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def validate_input_identity() -> None:
    ledger = OUT / "PQS_V1_DEVELOPMENT_GOLD_SEAL_DECISION_LEDGER.json"
    if sha(ledger) != EXPECTED_LEDGER_HASH:
        raise SealValidationError("Development Gold Seal Decision Ledger hash mismatch")
    if sha(CYCLE / "DEVELOPMENT_GOLD_CYCLE_REPORT.md") != EXPECTED_REPORT_HASH:
        raise SealValidationError("Development Gold Cycle report hash mismatch")
    for name, expected in EXPECTED_SOURCE_HASHES.items():
        if sha(SOURCE / name) != expected:
            raise SealValidationError(f"Source Candidate hash mismatch: {name}")


def validate_query_and_review_identity() -> set[str]:
    retrieval = read_jsonl(SOURCE / "product_retrieval_gold.development.reviewed.jsonl")
    evidence = read_jsonl(SOURCE / "product_evidence_gold.development.reviewed.jsonl")
    sufficiency = read_jsonl(SOURCE / "product_sufficiency_gold.development.reviewed.jsonl")
    statuses = read_jsonl(SOURCE / "reviewed_case_status.jsonl")
    collections = (retrieval, evidence, sufficiency, statuses)
    if any(len(rows) != 14 for rows in collections):
        raise SealValidationError("Development record count is not exactly 14")
    query_sets = [{row["query_id"] for row in rows} for rows in collections]
    if any(len(query_set) != 14 for query_set in query_sets):
        raise SealValidationError("Query IDs are not unique")
    if any(query_set != query_sets[0] for query_set in query_sets[1:]):
        raise SealValidationError("Query ID sets differ across layers/status")
    p5_ids = {row["query_id"] for row in read_jsonl(P5_DEVELOPMENT)}
    if query_sets[0] != p5_ids:
        raise SealValidationError("Query ID set differs from P5 Development Split")

    direct = [row for row in statuses if row["resolution"] == "agree"]
    reconciled = [row for row in statuses if row["resolution"] == "agree_reconciled"]
    if len(direct) != 13 or len(reconciled) != 1:
        raise SealValidationError("Review resolution is not 13 agreement + 1 reconciled")
    if (
        reconciled[0]["query_id"] != "PQS_V1_Q017"
        or reconciled[0]["reconciliation_rounds_used"] != 1
    ):
        raise SealValidationError("Q017 is not the sole one-round reconciled case")
    if any(row["user_adjudication_required"] for row in statuses):
        raise SealValidationError("Pending user adjudication exists")
    return query_sets[0]


def validate_gold_and_replay(query_ids: set[str]) -> int:
    files = (
        SEALED / "product_retrieval_gold.development.v1.sealed.jsonl",
        SEALED / "product_evidence_gold.development.v1.sealed.jsonl",
        SEALED / "product_sufficiency_gold.development.v1.sealed.jsonl",
    )
    layers = [{row["query_id"]: row for row in read_jsonl(path)} for path in files]
    if any(set(layer) != query_ids for layer in layers):
        raise SealValidationError("Sealed three-layer Query identity mismatch")
    replayed = 0
    for query_id in sorted(query_ids):
        retrieval, evidence, sufficiency = (layer[query_id] for layer in layers)
        validate_three_layer(retrieval, evidence, sufficiency)
        replayed += validate_replay(evidence)
        codes = (
            retrieval["reason_codes"]
            + evidence["reason_codes"]
            + sufficiency["reason_codes"]
        )
        if any(code.startswith(DOWNSTREAM_PREFIXES) for code in codes):
            raise SealValidationError("Downstream failure code appears in sealed Gold")
        if any(
            span["source_type"] not in {"official_subtitle", "asr_transcript"}
            for span in evidence["span_registry"]
        ):
            raise SealValidationError("Navigation/non-authoritative source used as Evidence")
    if replayed != 41:
        raise SealValidationError(f"Evidence replay count is {replayed}, expected 41")
    return replayed


def validate_immutability() -> None:
    for source_name, sealed_name in SOURCE_TO_SEALED.items():
        source = SOURCE / source_name
        sealed = SEALED / sealed_name
        if source.read_bytes() != sealed.read_bytes():
            raise SealValidationError(f"Sealed file is not byte-identical: {sealed_name}")
        if sha(source) != sha(sealed):
            raise SealValidationError(f"Source/sealed hash mismatch: {sealed_name}")


def validate_governance() -> None:
    seal = read_json(OUT / "development_gold_v1.seal.json")
    if (
        seal["status"] != "sealed_execution_candidate"
        or seal["query_count"] != 14
        or seal["evidence_span_count"] != 41
        or seal["review_status"]
        != {"reviewed_agreement": 13, "reviewed_reconciled": 1, "pending": 0}
    ):
        raise SealValidationError("Seal object state mismatch")
    if seal["mechanical_validation"] != {
        "schemas": "passed",
        "cross_object": "passed",
        "evidence_replay": "passed",
    }:
        raise SealValidationError("Seal mechanical validation state mismatch")

    manifest = read_json(OUT / "development_gold_v1.manifest.json")
    for relative, expected in manifest["artifact_hashes"].items():
        path = OUT / relative
        if not path.is_file() or sha(path) != expected:
            raise SealValidationError(f"Manifest artifact hash mismatch: {relative}")
    for relative, expected in manifest["source_candidate_hashes"].items():
        path = ROOT / relative
        if not path.is_file() or sha(path) != expected:
            raise SealValidationError(f"Manifest source hash mismatch: {relative}")

    for row in read_jsonl(OUT / "development_gold_v1.file_hash_manifest.jsonl"):
        path = OUT / row["path"]
        if not path.is_file() or sha(path) != row["sha256"]:
            raise SealValidationError(f"File hash manifest mismatch: {row['path']}")

    audit = read_json(OUT / "development_gold_v1.audit.json")
    if audit["immutability"] != {
        "sealed_files_byte_identical": True,
        "semantic_fields_changed": 0,
        "source_candidate_files_changed": False,
    }:
        raise SealValidationError("Audit immutability state mismatch")
    scope = audit["scope"]
    if (
        scope["frozen_packet_or_gold_opened"]
        or scope["product_prediction_read"]
        or scope["existing_external_gold_read"]
        or scope["product_pipeline_calls"]
        or scope["annotator_reviewer_or_reconciliation_restarted"]
        or scope["frozen_cycle_started"]
        or scope["p8_started"]
    ):
        raise SealValidationError("Seal scope boundary violation")

    decision = read_json(OUT / "development_gold_v1.execution_decision.json")
    if decision != {
        "acceptance_status": "pending_v3_5_b_review",
        "development_gold_formally_sealed_by_codex": False,
        "development_gold_seal_version": "DEVELOPMENT_GOLD_V1",
        "development_gold_sealed_execution_candidate_ready": True,
        "execution_status": "complete",
        "frozen_gold_cycle_authorized": False,
        "p8_authorized": False,
    }:
        raise SealValidationError("Execution Decision mismatch")


def validate_seal() -> dict[str, int]:
    validate_input_identity()
    query_ids = validate_query_and_review_identity()
    replayed = validate_gold_and_replay(query_ids)
    validate_immutability()
    validate_governance()
    return {"query_count": len(query_ids), "evidence_spans_replayed": replayed}


if __name__ == "__main__":
    result = validate_seal()
    print(f"Development Gold V1 Seal validation passed: {result}")
