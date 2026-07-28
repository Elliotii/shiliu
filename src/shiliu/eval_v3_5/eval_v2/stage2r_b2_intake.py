from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .packets import verify_packet_hash
from .query_projection import QueryProjectedAnnotationPacketV2


FREEZE_MANIFEST = Path("research/v3_5/eval_v2/stage2r_b1_c/canary_freeze_manifest.json")
BUNDLE = Path("V3_5_STAGE2R_B1_C_CANARY_HUMAN_ADJUDICATION_BUNDLE.md")
DECISIONS = Path(
    "research/v3_5/eval_v2/stage2r_b2_inputs/canary_human_decisions.user.jsonl"
)
OUTPUT_ROOT = Path("research/v3_5/eval_v2/stage2r_b2")
EXPECTED_FREEZE_SHA256 = "d64d72ebd283fb86d798b9c026a230569d924cdcf2c77471b5a5e0b2c72df394"
EXPECTED_BUNDLE_SHA256 = "00137397059ab02e0155c4b1af94e239e7f591c830319c3a0ebe6975495de356"
EXPECTED_CASES = ("V2C_B1A00001", "V2C_B1A00002")
PRIMARY_ROOTS = {
    "V2C_B1A00001": Path(
        "research/v3_5/eval_v2/stage2r_b1_b_canary/"
        "B1B_V2C_B1A00001_0b975c6b5eb9"
    ),
    "V2C_B1A00002": Path(
        "research/v3_5/eval_v2/stage2r_b1_b_canary/"
        "B1B_V2C_B1A00002_fe057eee3b4a"
    ),
}


class HumanDecisionValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedDecision:
    value: dict[str, object]
    primary_review_sha256: str
    packet_sha256: str


def validate_preconditions() -> dict[str, object]:
    if _sha256(FREEZE_MANIFEST) != EXPECTED_FREEZE_SHA256:
        raise HumanDecisionValidationError("freeze_manifest_hash_mismatch")
    if _sha256(BUNDLE) != EXPECTED_BUNDLE_SHA256:
        raise HumanDecisionValidationError("bundle_hash_mismatch")
    manifest = _read(FREEZE_MANIFEST)
    for path, expected in manifest["source_file_sha256"].items():
        if _sha256(Path(path)) != expected:
            raise HumanDecisionValidationError(f"frozen_source_hash_mismatch:{path}")
    for path, expected in manifest["artifact_sha256"].items():
        if _sha256(Path(path)) != expected:
            raise HumanDecisionValidationError(f"frozen_artifact_hash_mismatch:{path}")
    return manifest


def validate_human_decisions() -> tuple[ValidatedDecision, ...]:
    validate_preconditions()
    if not DECISIONS.is_file() or DECISIONS.stat().st_size == 0:
        raise HumanDecisionValidationError("human_decision_file_missing_or_empty")
    rows = [json.loads(line) for line in DECISIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    case_ids = [row.get("case_id") for row in rows]
    if len(rows) != 2 or tuple(sorted(case_ids)) != EXPECTED_CASES:
        raise HumanDecisionValidationError("human_decision_case_inventory_invalid")
    return tuple(_validate_one(row) for row in rows)


def _validate_one(row: dict[str, object]) -> ValidatedDecision:
    required = {
        "case_id", "human_action", "final_status", "final_required_aspects",
        "final_supported_aspects", "final_missing_aspects", "final_evidence_groups",
        "final_required_spans", "final_optional_context", "final_reason_codes",
        "final_boundary_notes", "adjudication_reason",
    }
    missing = sorted(required - set(row))
    if missing:
        raise HumanDecisionValidationError("missing_fields:" + ",".join(missing))
    case_id = str(row["case_id"])
    if case_id not in PRIMARY_ROOTS:
        raise HumanDecisionValidationError(f"unexpected_case_id:{case_id}")
    if row["human_action"] != "approve_primary":
        raise HumanDecisionValidationError(f"unsupported_action_for_expansion:{case_id}")
    if not isinstance(row["adjudication_reason"], str) or not row["adjudication_reason"].strip():
        raise HumanDecisionValidationError(f"empty_adjudication_reason:{case_id}")

    root = PRIMARY_ROOTS[case_id]
    review_path = root / "primary/canonical_review.json"
    review = _read(review_path)
    body = review["review"]
    packet_path = root / "primary/reviewer_packet.json"
    packet = QueryProjectedAnnotationPacketV2.model_validate(_read(packet_path))
    if not verify_packet_hash(packet):
        raise HumanDecisionValidationError(f"packet_hash_invalid:{case_id}")

    group_span_ids = [
        span_id
        for group in body["acceptable_evidence_groups"]
        for span_id in group["required_span_ids"]
    ]
    selected_spans = [
        span for span in body["required_spans"] if span["span_id"] in set(group_span_ids)
    ]
    expected = {
        "final_status": body["status"],
        "final_required_aspects": body["required_aspects"],
        "final_supported_aspects": body["supported_aspects"],
        "final_missing_aspects": body["missing_aspects"],
        "final_evidence_groups": body["acceptable_evidence_groups"],
        "final_required_spans": selected_spans,
        "final_optional_context": body.get("optional_context_spans", []),
        "final_reason_codes": body.get("reason_codes", []),
        "final_boundary_notes": [body["boundary_notes"]] if body.get("boundary_notes") else [],
    }
    for field, value in expected.items():
        if row[field] != value:
            raise HumanDecisionValidationError(f"primary_mapping_mismatch:{case_id}:{field}")

    status = row["final_status"]
    if status not in {"sufficient", "partial", "insufficient", "unverifiable"}:
        raise HumanDecisionValidationError(f"invalid_four_state:{case_id}")
    aspects = {item["aspect_id"] for item in row["final_required_aspects"]}
    supported = set(row["final_supported_aspects"])
    missing_aspects = set(row["final_missing_aspects"])
    if supported & missing_aspects or supported | missing_aspects != aspects:
        raise HumanDecisionValidationError(f"aspect_partition_invalid:{case_id}")
    span_by_id = {span["span_id"]: span for span in row["final_required_spans"]}
    referenced = {
        span_id for group in row["final_evidence_groups"] for span_id in group["required_span_ids"]
    }
    if referenced != set(span_by_id):
        raise HumanDecisionValidationError(f"group_span_closure_invalid:{case_id}")
    for group in row["final_evidence_groups"]:
        if not set(group["required_aspect_ids"]) <= aspects:
            raise HumanDecisionValidationError(f"group_aspect_reference_invalid:{case_id}")
    _validate_spans(case_id, tuple(span_by_id.values()), packet)
    return ValidatedDecision(
        value=row,
        primary_review_sha256=_sha256(review_path),
        packet_sha256=_sha256(packet_path),
    )


def _validate_spans(
    case_id: str, spans: tuple[dict[str, object], ...], packet: QueryProjectedAnnotationPacketV2
) -> None:
    by_id = {segment.segment_id: segment for segment in packet.full_raw_transcript}
    for span in spans:
        try:
            selected = [by_id[segment_id] for segment_id in span["segment_ids"]]
        except KeyError as exc:
            raise HumanDecisionValidationError(f"unknown_segment_id:{case_id}:{exc.args[0]}") from None
        if not selected:
            raise HumanDecisionValidationError(f"empty_span:{case_id}")
        if min(item.start_time for item in selected) != span["start_time"]:
            raise HumanDecisionValidationError(f"span_start_reconstruction_failed:{case_id}")
        if max(item.end_time for item in selected) != span["end_time"]:
            raise HumanDecisionValidationError(f"span_end_reconstruction_failed:{case_id}")
        identity = {
            (
                item.source_artifact_id, item.source_version, item.timeline_run_id,
                item.source_language, item.source_type,
            )
            for item in selected
        }
        expected = {
            (
                span["source_artifact_id"], span["source_version"], span["timeline_run_id"],
                span["source_language"], span["source_type"],
            )
        }
        if identity != expected:
            raise HumanDecisionValidationError(f"span_source_identity_invalid:{case_id}")


def persist_validated_decisions(validated: tuple[ValidatedDecision, ...]) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=False)
    records = [
        {
            **item.value,
            "adjudication_status": "pilot_adjudicated",
            "human_authored": True,
            "automatic_decision_used": False,
            "primary_review_sha256": item.primary_review_sha256,
            "packet_sha256": item.packet_sha256,
        }
        for item in validated
    ]
    (OUTPUT_ROOT / "adjudicated_canary_cases.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    audit = {
        "source_bundle_sha256": _sha256(BUNDLE),
        "user_decision_file_sha256": _sha256(DECISIONS),
        "case_count": len(records),
        "validated_case_ids": [record["case_id"] for record in records],
        "human_authored": True,
        "automatic_decision_used": False,
        "canonical_reconstruction_passed": True,
        "human_action_unchanged": True,
        "adjudication_reason_unchanged": True,
        "model_calls": 0,
    }
    (OUTPUT_ROOT / "canary_adjudication.audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
