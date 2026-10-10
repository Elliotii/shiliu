from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .agreement import compare_reviews
from .canary import CanaryPathResult, canonical_bytes, render_human_review_packet, scan_artifacts_for_secrets
from .contracts import AnnotationReviewV2
from .run_stage2r_b1_b import OUTPUT_ROOT, _specs, _write_json
from .stage2r_b_runtime import RawInvocation, bind_and_validate


def main() -> None:
    case_roots = {path.name.split("_")[2]: path for path in OUTPUT_ROOT.glob("B1B_*")}
    # The directory name split is not stable enough for lookup; bind by review_run metadata.
    by_case: dict[str, Path] = {}
    for root in OUTPUT_ROOT.glob("B1B_*"):
        identity = _read(root / "review_run.json")
        by_case[str(identity["case_id"])] = root

    target = by_case["V2C_B1A00002"]
    secondary_dir = target / "secondary"
    manifest = _read(secondary_dir / "provider_result_manifest.json")
    repaired_body = _read(secondary_dir / "reviewer_draft.repair.json")
    packet = _packet(target / "secondary/reviewer_packet.json")
    invocation = RawInvocation(
        body=repaired_body,
        model=str(manifest["requested_model"]),
        latency_ms=int(manifest["provider_latency_ms"]),
        input_tokens=_int_or_none(manifest.get("input_tokens")),
        output_tokens=_int_or_none(manifest.get("output_tokens")),
        cached_tokens=_int_or_none(manifest.get("cached_tokens")),
        finish_reason=str(manifest.get("finish_reason") or "") or None,
        response_model=str(manifest.get("response_model_echo") or "") or None,
        response_model_echo_available=manifest.get("response_model_echo") is not None,
        raw_call_count=1,
    )
    validation = bind_and_validate(
        packet=packet,
        invocation=invocation,
        provider="deepseek",
        role="secondary",
        prompt_version="v3.5-secondary-reviewer-draft-repair-prompt-v2-query-grounded",
        repair_count=1,
    )
    if validation.status != "valid" or validation.review is None:
        raise SystemExit(f"corrected validator did not accept persisted repair: {validation.errors}")
    canonical = validation.review.model_dump(mode="json")
    _write_json(secondary_dir / "canonical_review.json", canonical)
    canonical_sha = hashlib.sha256(canonical_bytes(canonical)).hexdigest()
    manifest.update(
        {
            "canonical_compilation_success": True,
            "canonical_sha256": canonical_sha,
            "repair_valid": True,
            "validator_rule_corrected_post_transport": True,
        }
    )
    _write_json(secondary_dir / "provider_result_manifest.json", manifest)
    _write_json(
        secondary_dir / "reviewer_validation.json",
        {
            "initial_errors": [],
            "final_errors": [],
            "status": "valid_after_repair",
            "repair_count": 1,
            "query_grounding_status": validation.query_grounding_status,
            "query_grounding_errors": list(validation.query_grounding_errors),
            "post_transport_validator_correction": "spacing-insensitive aspect/anchor binding",
        },
    )

    primary = AnnotationReviewV2.model_validate(_read(target / "primary/canonical_review.json"))
    agreement = compare_reviews(primary, validation.review, cross_language=False, asr_error=False)
    _write_json(target / "agreement.json", agreement.model_dump(mode="json"))
    identity = _read(target / "review_run.json")
    identity.update(
        {
            "secondary_status": "valid_after_repair",
            "secondary_query_grounding": validation.query_grounding_status,
            "agreement_status": agreement.status,
        }
    )
    _write_json(target / "review_run.json", identity)

    specs = {spec.case_id: spec for spec in _specs()}
    for case_id, root in by_case.items():
        packet_for_case = _packet(root / "primary/reviewer_packet.json")
        primary_review = AnnotationReviewV2.model_validate(_read(root / "primary/canonical_review.json"))
        secondary_review = AnnotationReviewV2.model_validate(_read(root / "secondary/canonical_review.json"))
        agreement_value = compare_reviews(
            primary_review, secondary_review, cross_language=False, asr_error=False
        )
        primary_validation = _read(root / "primary/reviewer_validation.json")
        secondary_validation = _read(root / "secondary/reviewer_validation.json")
        primary_result = _path_result(primary_review, primary_validation)
        secondary_result = _path_result(secondary_review, secondary_validation)
        (root / "human_review_packet.md").write_text(
            render_human_review_packet(
                spec=specs[case_id],
                packet=packet_for_case,
                primary=primary_result,
                secondary=secondary_result,
                agreement=agreement_value,
                review_run_id=root.name,
            ),
            encoding="utf-8",
        )

    summaries = _read(OUTPUT_ROOT / "canary_summary.json")
    for item in summaries:
        if item["case_id"] == "V2C_B1A00002":
            item.update(
                {
                    "secondary_status": "valid_after_repair",
                    "secondary_query_grounding": validation.query_grounding_status,
                    "agreement_status": agreement.status,
                }
            )
    _write_json(OUTPUT_ROOT / "canary_summary.json", summaries)
    _write_json(
        OUTPUT_ROOT / "validator_correction.audit.json",
        {
            "provider_resampled": False,
            "additional_transport_attempts": 0,
            "persisted_draft_recompiled": "secondary/reviewer_draft.repair.json",
            "original_false_positive": "aspect_not_bound_to_anchor:0",
            "cause": "anchor phrase contained spaces while semantically identical aspect did not",
            "corrected_rule": "exact evidence-question substring remains mandatory for anchors; aspect binding tolerates spacing when all significant query terms are present",
            "result": "valid_after_repair",
        },
    )
    _write_json(
        OUTPUT_ROOT / "secret_scan.audit.json",
        scan_artifacts_for_secrets(OUTPUT_ROOT, secrets=()),
    )


def _path_result(review: AnnotationReviewV2, validation: dict[str, object]) -> CanaryPathResult:
    return CanaryPathResult(
        status=str(validation["status"]),
        initial=None,
        repaired=None,
        canonical_review=review,
        initial_errors=tuple(validation.get("initial_errors", [])),
        final_errors=tuple(validation.get("final_errors", [])),
        transport_attempts=(),
        repair_attempted=int(validation.get("repair_count", 0)) == 1,
        provider_error=None,
        end_to_end_latency_ms=0,
        query_grounding_status=str(validation.get("query_grounding_status", "valid")),
        query_grounding_errors=tuple(validation.get("query_grounding_errors", [])),
    )


def _packet(path: Path):
    from .query_projection import QueryProjectedAnnotationPacketV2

    return QueryProjectedAnnotationPacketV2.model_validate(_read(path))


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _int_or_none(value: object) -> int | None:
    return int(value) if isinstance(value, int) else None


if __name__ == "__main__":
    main()
