from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from .packets import verify_packet_hash
from .query_projection import QueryProjectedAnnotationPacketV2


B2_ROOT = Path("research/v3_5/eval_v2/stage2r_b2")
DECISIONS = Path(
    "research/v3_5/eval_v2/stage2r_b2_inputs/"
    "remaining_pilot_human_decisions.user.jsonl"
)
OUTPUT = B2_ROOT / "adjudicated_remaining_pilot_cases.jsonl"
AUDIT = B2_ROOT / "remaining_pilot_adjudication.audit.json"
REPORT = Path("V3_5_STAGE2R_B2_HUMAN_ADJUDICATION_INTAKE_REPORT.md")
EXPECTED_CASES = ("V2C_B2P00001", "V2C_B2P00002")
ROLES = ("primary", "secondary")
FOUR_STATE = {"sufficient", "partial", "insufficient", "unverifiable"}
ALLOWED_ACTIONS = {
    "approve_primary", "approve_secondary", "merge_and_revise", "reject_both"
}
ALLOWED_PATCH_KEYS = {
    "final_status",
    "replace_required_aspect_text",
    "remove_required_spans",
    "add_reason_codes",
    "remove_reason_codes",
    "replace_boundary_notes",
}


class RemainingPilotDecisionError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _protected_paths() -> tuple[Path, ...]:
    return tuple(
        B2_ROOT / case_id / relative
        for case_id in EXPECTED_CASES
        for relative in (
            "primary/canonical_review.json",
            "secondary/canonical_review.json",
            "agreement.json",
            "human_review_packet.md",
        )
    )


def _protected_hashes() -> dict[str, str]:
    return {str(path): _sha256(path) for path in _protected_paths()}


def _load_decisions() -> list[dict[str, Any]]:
    if not DECISIONS.is_file() or not DECISIONS.stat().st_size:
        raise RemainingPilotDecisionError("human_decision_file_missing_or_empty")
    rows = [
        json.loads(line)
        for line in DECISIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != 2 or tuple(row.get("case_id") for row in rows) != EXPECTED_CASES:
        raise RemainingPilotDecisionError("human_decision_case_inventory_invalid")
    return rows


def _canonical_body(case_id: str, role: str) -> dict[str, Any]:
    if role not in ROLES:
        raise RemainingPilotDecisionError(f"invalid_base_review:{case_id}:{role}")
    return _read_json(B2_ROOT / case_id / role / "canonical_review.json")["review"]


def _canonical_to_final(body: dict[str, Any]) -> dict[str, Any]:
    referenced = {
        span_id
        for group in body["acceptable_evidence_groups"]
        for span_id in group["required_span_ids"]
    }
    return {
        "final_status": body["status"],
        "final_required_aspects": copy.deepcopy(body["required_aspects"]),
        "final_supported_aspects": copy.deepcopy(body["supported_aspects"]),
        "final_missing_aspects": copy.deepcopy(body["missing_aspects"]),
        "final_evidence_groups": copy.deepcopy(body["acceptable_evidence_groups"]),
        "final_required_spans": [
            copy.deepcopy(span)
            for span in body["required_spans"]
            if span["span_id"] in referenced
        ],
        "final_optional_context": copy.deepcopy(body.get("optional_context_spans", [])),
        "final_reason_codes": copy.deepcopy(body.get("reason_codes", [])),
        "final_boundary_notes": (
            [body["boundary_notes"]] if body.get("boundary_notes") else []
        ),
    }


def _apply_patch(case_id: str, final: dict[str, Any], changes: dict[str, Any]) -> None:
    unknown = set(changes) - ALLOWED_PATCH_KEYS
    if unknown:
        raise RemainingPilotDecisionError(
            f"unsupported_patch_keys:{case_id}:{','.join(sorted(unknown))}"
        )
    if "final_status" in changes:
        final["final_status"] = changes["final_status"]
    if "replace_required_aspect_text" in changes:
        replacement = changes["replace_required_aspect_text"]
        if not isinstance(replacement, dict) or set(replacement) != {"aspect_id", "description"}:
            raise RemainingPilotDecisionError(f"invalid_aspect_replacement:{case_id}")
        matches = [
            aspect for aspect in final["final_required_aspects"]
            if aspect["aspect_id"] == replacement["aspect_id"]
        ]
        if len(matches) != 1 or not isinstance(replacement["description"], str):
            raise RemainingPilotDecisionError(f"aspect_replacement_target_invalid:{case_id}")
        matches[0]["description"] = replacement["description"]
    if "remove_required_spans" in changes:
        removed = changes["remove_required_spans"]
        if not isinstance(removed, list) or not all(isinstance(item, str) for item in removed):
            raise RemainingPilotDecisionError(f"invalid_remove_required_spans:{case_id}")
        known = {span["span_id"] for span in final["final_required_spans"]}
        if not set(removed) <= known:
            raise RemainingPilotDecisionError(f"unknown_removed_span:{case_id}")
        final["final_required_spans"] = [
            span for span in final["final_required_spans"] if span["span_id"] not in set(removed)
        ]
        final["final_evidence_groups"] = [
            group for group in final["final_evidence_groups"]
            if not set(group["required_span_ids"]) & set(removed)
        ]
    for key, mode in (("remove_reason_codes", "remove"), ("add_reason_codes", "add")):
        if key not in changes:
            continue
        values = changes[key]
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise RemainingPilotDecisionError(f"invalid_{key}:{case_id}")
        if mode == "remove":
            if not set(values) <= set(final["final_reason_codes"]):
                raise RemainingPilotDecisionError(f"unknown_removed_reason_code:{case_id}")
            final["final_reason_codes"] = [
                code for code in final["final_reason_codes"] if code not in set(values)
            ]
        else:
            for value in values:
                if value not in final["final_reason_codes"]:
                    final["final_reason_codes"].append(value)
    if "replace_boundary_notes" in changes:
        note = changes["replace_boundary_notes"]
        if not isinstance(note, str):
            raise RemainingPilotDecisionError(f"invalid_boundary_notes:{case_id}")
        final["final_boundary_notes"] = [note] if note else []


def _validate_final(case_id: str, final: dict[str, Any], packet: QueryProjectedAnnotationPacketV2) -> None:
    if final["final_status"] not in FOUR_STATE:
        raise RemainingPilotDecisionError(f"invalid_four_state:{case_id}")
    aspects = {item["aspect_id"] for item in final["final_required_aspects"]}
    supported = set(final["final_supported_aspects"])
    missing = set(final["final_missing_aspects"])
    if supported & missing or supported | missing != aspects:
        raise RemainingPilotDecisionError(f"aspect_partition_invalid:{case_id}")
    span_by_id = {span["span_id"]: span for span in final["final_required_spans"]}
    referenced = {
        span_id
        for group in final["final_evidence_groups"]
        for span_id in group["required_span_ids"]
    }
    if referenced != set(span_by_id):
        raise RemainingPilotDecisionError(f"group_span_closure_invalid:{case_id}")
    if any(
        not set(group["required_aspect_ids"]) <= aspects
        for group in final["final_evidence_groups"]
    ):
        raise RemainingPilotDecisionError(f"group_aspect_reference_invalid:{case_id}")
    segments = {segment.segment_id: segment for segment in packet.full_raw_transcript}
    for span in span_by_id.values():
        try:
            selected = [segments[segment_id] for segment_id in span["segment_ids"]]
        except KeyError as exc:
            raise RemainingPilotDecisionError(
                f"unknown_segment_id:{case_id}:{exc.args[0]}"
            ) from None
        if not selected:
            raise RemainingPilotDecisionError(f"empty_span:{case_id}")
        if min(item.start_time for item in selected) != span["start_time"]:
            raise RemainingPilotDecisionError(f"span_start_reconstruction_failed:{case_id}")
        if max(item.end_time for item in selected) != span["end_time"]:
            raise RemainingPilotDecisionError(f"span_end_reconstruction_failed:{case_id}")
        identities = {
            (
                item.source_artifact_id,
                item.source_version,
                item.timeline_run_id,
                item.source_language,
                item.source_type,
            )
            for item in selected
        }
        expected = {
            (
                span["source_artifact_id"],
                span["source_version"],
                span["timeline_run_id"],
                span["source_language"],
                span["source_type"],
            )
        }
        if identities != expected:
            raise RemainingPilotDecisionError(f"span_source_identity_invalid:{case_id}")


def expand_decisions() -> list[dict[str, Any]]:
    expanded = []
    for row in _load_decisions():
        case_id = row["case_id"]
        action = row.get("human_action")
        if action not in ALLOWED_ACTIONS:
            raise RemainingPilotDecisionError(f"invalid_human_action:{case_id}")
        reason = row.get("adjudication_reason")
        if not isinstance(reason, str) or not reason.strip():
            raise RemainingPilotDecisionError(f"empty_adjudication_reason:{case_id}")
        if action == "reject_both":
            raise RemainingPilotDecisionError(f"reject_both_cannot_form_adjudication:{case_id}")
        if action in {"approve_primary", "approve_secondary"}:
            allowed = {"case_id", "human_action", "adjudication_reason"}
            if set(row) != allowed:
                raise RemainingPilotDecisionError(f"unexpected_approval_fields:{case_id}")
            base_review = action.removeprefix("approve_")
            changes: dict[str, Any] = {}
        else:
            allowed = {
                "case_id", "human_action", "base_review", "changes", "adjudication_reason"
            }
            if set(row) != allowed:
                raise RemainingPilotDecisionError(f"unexpected_merge_fields:{case_id}")
            base_review = row.get("base_review")
            changes = row.get("changes")
            if base_review not in ROLES or not isinstance(changes, dict):
                raise RemainingPilotDecisionError(f"invalid_merge_contract:{case_id}")
        review_path = B2_ROOT / case_id / base_review / "canonical_review.json"
        packet_path = B2_ROOT / case_id / base_review / "reviewer_packet.json"
        packet = QueryProjectedAnnotationPacketV2.model_validate(_read_json(packet_path))
        if not verify_packet_hash(packet):
            raise RemainingPilotDecisionError(f"packet_hash_invalid:{case_id}")
        final = _canonical_to_final(_canonical_body(case_id, base_review))
        if changes:
            _apply_patch(case_id, final, changes)
        _validate_final(case_id, final, packet)
        expanded.append(
            {
                "case_id": case_id,
                "human_action": action,
                **({"base_review": base_review, "changes": changes} if action == "merge_and_revise" else {}),
                **final,
                "adjudication_reason": reason,
                "adjudication_status": "pilot_adjudicated",
                "human_authored": True,
                "automatic_decision_used": False,
                "base_review_sha256": _sha256(review_path),
                "packet_sha256": _sha256(packet_path),
            }
        )
    return expanded


def main() -> None:
    before = _protected_hashes()
    expanded = expand_decisions()
    OUTPUT.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in expanded
        ),
        encoding="utf-8",
    )
    after = _protected_hashes()
    if before != after:
        raise RemainingPilotDecisionError("protected_source_hash_changed")
    audit = {
        "case_count": len(expanded),
        "validated_case_ids": [record["case_id"] for record in expanded],
        "user_decision_file_sha256": _sha256(DECISIONS),
        "source_assets_unchanged": True,
        "protected_sha256_before": before,
        "protected_sha256_after": after,
        "human_authored": True,
        "automatic_decision_used": False,
        "canonical_reconstruction_passed": True,
        "human_action_unchanged": True,
        "adjudication_reason_unchanged": True,
        "model_calls": 0,
        "reviewer_calls": 0,
        "agreement_rerun": False,
        "final_gold_created": False,
        "stage2r_c_entered": False,
        "output_sha256": _sha256(OUTPUT),
    }
    AUDIT.write_text(
        json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    REPORT.write_text(
        "# V3.5 Stage 2R-B2 Remaining Pilot Human Adjudication Intake Report\n\n"
        "## Outcome\n\n"
        "The two user-provided decisions were validated and deterministically expanded "
        "from the selected frozen Canonical Reviews. No semantic decision was made by code.\n\n"
        "- `V2C_B2P00001`: `approve_primary`; final status `insufficient`.\n"
        "- `V2C_B2P00002`: `merge_and_revise` from Secondary; final status "
        "`insufficient`; only the user-specified finite patch was applied.\n"
        "- Source Review, Agreement, and Human Packet hashes were unchanged.\n"
        "- Canonical reconstruction and reference validation passed.\n"
        "- Model calls: `0`; Reviewer calls: `0`; Agreement reruns: `0`.\n"
        "- Final Gold created: **No**.\n"
        "- Stage 2R-C entered: **No**.\n\n"
        "## Artifacts\n\n"
        f"- User decisions: `{DECISIONS}` (`{_sha256(DECISIONS)}`)\n"
        f"- Expanded adjudications: `{OUTPUT}` (`{_sha256(OUTPUT)}`)\n"
        f"- Audit: `{AUDIT}` (`{_sha256(AUDIT)}`)\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
