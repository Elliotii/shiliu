"""Mechanical validation for the Development Gold Cycle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from validate_product_gold_protocol_v1 import validate_three_layer


ROOT = Path(__file__).resolve().parents[1]
CYCLE = ROOT / "research/v3_5/product_query_set_v1/gold_construction_v1/development_cycle"
CATALOG = ROOT / "research/v3_5/product_query_set_v1/gold_construction_v1/shared/authoritative_transcript_identity_catalog.jsonl"
EXPECTED_QUERIES = {
    "PQS_V1_Q003", "PQS_V1_Q004", "PQS_V1_Q005", "PQS_V1_Q006",
    "PQS_V1_Q007", "PQS_V1_Q008", "PQS_V1_Q011", "PQS_V1_Q012",
    "PQS_V1_Q013", "PQS_V1_Q014", "PQS_V1_Q015", "PQS_V1_Q017",
    "PQS_V1_Q018", "PQS_V1_Q019",
}
DOWNSTREAM_PREFIXES = ("RET_", "BLD_", "SEL_", "GATE_", "JDG_", "SRC_")


class CycleValidationError(ValueError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _catalog() -> dict[tuple[str, str], dict[str, Any]]:
    return {(row["video_id"], row["source_version"]): row for row in read_jsonl(CATALOG)}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _segment_id(artifact_id: str, version: str, ordinal: int) -> str:
    payload = {
        "original_ordinal": ordinal,
        "source_artifact_id": artifact_id,
        "source_version": version,
    }
    return "segment_" + hashlib.sha256(_canonical(payload)).hexdigest()


def validate_replay(evidence: dict[str, Any]) -> int:
    catalog = _catalog()
    count = 0
    for span in evidence["span_registry"]:
        source = catalog.get((span["video_id"], span["source_version"]))
        if source is None or span["source_type"] not in {"official_subtitle", "asr_transcript"}:
            raise CycleValidationError("Evidence source is not authoritative/catalog-bound")
        payload = json.loads(Path(source["source_path"]).read_bytes())
        ids = {
            _segment_id(source["source_artifact_id"], source["source_version"], ordinal): (ordinal, item)
            for ordinal, item in enumerate(payload)
        }
        try:
            selected = [ids[segment_id] for segment_id in span["segment_ids"]]
        except KeyError as exc:
            raise CycleValidationError("Evidence segment identity is not replayable") from exc
        ordinals = [item[0] for item in selected]
        if ordinals != sorted(ordinals):
            raise CycleValidationError("Evidence segment order is invalid")
        first, last = selected[0][1], selected[-1][1]
        if float(span["start_time"]) != float(first["from"]) or float(span["end_time"]) != float(last["to"]):
            raise CycleValidationError("Evidence time boundary does not replay exactly")
        normalized_quote = "".join(str(span["quote_text"]).split())
        normalized_source = "".join("".join(str(item[1]["content"]).split()) for item in selected)
        if normalized_quote != normalized_source:
            raise CycleValidationError("Evidence quote does not replay exact selected source text")
        if span["timeline_run_id"] not in source["timeline_run_ids"]:
            raise CycleValidationError("Evidence timeline identity mismatch")
        count += 1
    return count


def validate_independence() -> None:
    a = read_json(CYCLE / "independent_reviews/reviewer_A/independent_draft_seal.json")
    b = read_json(CYCLE / "independent_reviews/reviewer_B/independent_draft_seal.json")
    if a["initial_annotation_opened"] or b["initial_annotation_opened"]:
        raise CycleValidationError("Independent Draft was not sealed before Initial open")
    phase2_a = read_json(CYCLE / "independent_reviews/reviewer_A/reviewer_A.manifest.phase2.json")
    phase2_b = read_json(CYCLE / "independent_reviews/reviewer_B/reviewer_B.manifest.phase2.json")
    if phase2_a["phase1_seal_sha256"] != sha(CYCLE / "independent_reviews/reviewer_A/independent_draft_seal.json"):
        raise CycleValidationError("reviewer_A Phase 1 seal changed")
    if phase2_b["phase1_seal_sha256"] != sha(CYCLE / "independent_reviews/reviewer_B/independent_draft_seal.json"):
        raise CycleValidationError("reviewer_B Phase 1 seal changed")
    opened_a = phase2_a["initial_annotation_opened_at_utc"]
    sealed_a = a["sealed_at_utc"]
    opened_b = phase2_b["initial_annotation_opened_at_utc"]
    sealed_b = b["sealed_at"]
    if opened_a <= sealed_a or opened_b <= sealed_b:
        raise CycleValidationError("Initial Annotation opened before Independent Seal")


def validate_reviewed_candidate() -> dict[str, int]:
    base = CYCLE / "reviewed_gold_candidate"
    retrieval = read_jsonl(base / "product_retrieval_gold.development.reviewed.jsonl")
    evidence = read_jsonl(base / "product_evidence_gold.development.reviewed.jsonl")
    sufficiency = read_jsonl(base / "product_sufficiency_gold.development.reviewed.jsonl")
    statuses = read_jsonl(base / "reviewed_case_status.jsonl")
    layers = [{row["query_id"]: row for row in values} for values in (retrieval, evidence, sufficiency)]
    if any(set(layer) != EXPECTED_QUERIES for layer in layers):
        raise CycleValidationError("Reviewed Candidate does not contain exactly 14 Development Queries")
    if {row["query_id"] for row in statuses} != EXPECTED_QUERIES:
        raise CycleValidationError("Reviewed Case Status does not cover 14 Queries")
    replayed = 0
    for query_id in sorted(EXPECTED_QUERIES):
        validate_three_layer(layers[0][query_id], layers[1][query_id], layers[2][query_id])
        replayed += validate_replay(layers[1][query_id])
        if set(layers[0][query_id]["hard_negative_video_ids"]) - set(
            layers[0][query_id]["relevance_review_scope"]["reviewed_video_ids"]
        ):
            raise CycleValidationError("Unreviewed video used as hard negative")
        codes = (
            layers[0][query_id]["reason_codes"]
            + layers[1][query_id]["reason_codes"]
            + layers[2][query_id]["reason_codes"]
        )
        if any(code.startswith(DOWNSTREAM_PREFIXES) for code in codes):
            raise CycleValidationError("Downstream failure code appears in Gold")
    return {"query_count": 14, "replayed_span_count": replayed}


def validate_cycle() -> dict[str, int]:
    validate_independence()
    result = validate_reviewed_candidate()
    log = read_jsonl(CYCLE / "reconciliation/reconciliation_log.jsonl")
    if len(log) != 1 or log[0]["reconciliation_round"] != 1 or log[0]["second_round_started"]:
        raise CycleValidationError("Reconciliation count exceeds contract")
    decision = read_json(CYCLE / "development_gold_cycle.execution_decision.json")
    if decision["pending_user_adjudication"] != 0:
        raise CycleValidationError("Unresolved items were not routed consistently")
    audit = read_json(CYCLE / "development_gold_cycle.audit.json")
    boundary = audit["boundary"]
    if (
        boundary["same_unit_annotated_and_reviewed_same_case"]
        or boundary["orchestrator_made_semantic_decisions"]
        or boundary["frozen_packet_opened"]
        or boundary["product_prediction_read"]
        or boundary["existing_gold_read"]
        or boundary["product_pipeline_calls"]
        or boundary["p8_started"]
    ):
        raise CycleValidationError("Development Cycle boundary violation")
    return result


if __name__ == "__main__":
    result = validate_cycle()
    print(f"Development Gold Cycle validation passed: {result}")
