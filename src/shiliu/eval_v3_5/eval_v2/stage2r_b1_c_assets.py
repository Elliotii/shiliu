from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .contracts import (
    ANNOTATION_AGREEMENT_VERSION,
    ANNOTATION_REVIEW_SCHEMA_VERSION,
    AnnotationAgreementV2,
    AnnotationReviewV2,
)
from .query_grounding import QUERY_GROUNDING_VALIDATOR_VERSION
from .query_projection import QUERY_PROJECTION_POLICY_VERSION, QueryProjectedAnnotationPacketV2
from .review_compiler import REVIEW_COMPILER_VERSION
from .reviewer_draft import REVIEWER_DRAFT_SCHEMA_VERSION
from .reviewer_registry import PRIMARY_REVIEWER, SECONDARY_REVIEWER


B1B_ROOT = Path("research/v3_5/eval_v2/stage2r_b1_b_canary")
B1C_ROOT = Path("research/v3_5/eval_v2/stage2r_b1_c")
BUNDLE_PATH = Path("V3_5_STAGE2R_B1_C_CANARY_HUMAN_ADJUDICATION_BUNDLE.md")
RUNS = (
    "B1B_V2C_B1A00001_0b975c6b5eb9",
    "B1B_V2C_B1A00002_fe057eee3b4a",
)


def generate_freeze_and_bundle() -> dict[str, object]:
    B1C_ROOT.mkdir(parents=True, exist_ok=True)
    protected = _protected_artifacts()
    before = {str(path): sha256_file(path) for path in protected}
    bundle = render_bundle()
    BUNDLE_PATH.write_text(bundle, encoding="utf-8")
    after = {str(path): sha256_file(path) for path in protected}
    if before != after:
        raise RuntimeError("original Canary review artifacts changed while building bundle")

    source_files = (
        Path("src/shiliu/eval_v3_5/eval_v2/query_projection.py"),
        Path("src/shiliu/eval_v3_5/eval_v2/reviewer_draft.py"),
        Path("src/shiliu/eval_v3_5/eval_v2/providers.py"),
        Path("src/shiliu/eval_v3_5/eval_v2/reviewer_registry.py"),
        Path("src/shiliu/eval_v3_5/eval_v2/query_grounding.py"),
        Path("src/shiliu/eval_v3_5/eval_v2/review_compiler.py"),
        Path("src/shiliu/eval_v3_5/eval_v2/agreement.py"),
        Path("src/shiliu/eval_v3_5/eval_v2/contracts.py"),
        Path("src/shiliu/eval_v3_5/eval_v2/canary.py"),
        Path("src/shiliu/eval_v3_5/eval_v2/stage2r_b_runtime.py"),
    )
    artifact_files = tuple(
        sorted(
            path
            for run in RUNS
            for path in (B1B_ROOT / run).rglob("*")
            if path.is_file()
        )
    ) + (BUNDLE_PATH,)
    manifest = {
        "query_projection_version": QUERY_PROJECTION_POLICY_VERSION,
        "reviewer_draft_schema_version": REVIEWER_DRAFT_SCHEMA_VERSION,
        "primary_prompt_version": PRIMARY_REVIEWER.prompt_version,
        "secondary_prompt_version": SECONDARY_REVIEWER.prompt_version,
        "query_grounding_validator_version": QUERY_GROUNDING_VALIDATOR_VERSION,
        "review_compiler_version": REVIEW_COMPILER_VERSION,
        "canonical_review_schema_version": ANNOTATION_REVIEW_SCHEMA_VERSION,
        "agreement_version": ANNOTATION_AGREEMENT_VERSION,
        "source_file_sha256": {
            path.as_posix(): sha256_file(path) for path in source_files
        },
        "artifact_sha256": {
            path.as_posix(): sha256_file(path) for path in artifact_files
        },
        "freeze_status": "frozen_for_remaining_pilot",
        "future_protocol_defect_policy": (
            "stop and create a new Eval Protocol Version; do not modify frozen components in place"
        ),
        "remaining_pilot_authorized": False,
        "remaining_pilot_reason": "awaiting human adjudication of both Canary Cases",
    }
    manifest_path = B1C_ROOT / "canary_freeze_manifest.json"
    _write_json(manifest_path, manifest)
    integrity = {
        "original_review_artifacts_unchanged": before == after,
        "protected_artifact_sha256_before": before,
        "protected_artifact_sha256_after": after,
        "bundle_path": BUNDLE_PATH.as_posix(),
        "bundle_sha256": sha256_file(BUNDLE_PATH),
        "freeze_manifest_path": manifest_path.as_posix(),
        "freeze_manifest_sha256": sha256_file(manifest_path),
        "human_decision_prefilled": False,
        "final_gold_created": False,
        "reviewed_case_ids": ["V2C_B1A00001", "V2C_B1A00002"],
        "third_case_selected": False,
    }
    _write_json(B1C_ROOT / "canary_freeze_and_bundle_integrity.audit.json", integrity)
    historical = historical_usage_completeness()
    _write_json(B1C_ROOT / "historical_usage_completeness.json", historical)
    _write_json(B1C_ROOT / "usage_batch_summary.json", usage_batch_summary(historical))
    return integrity


def render_bundle() -> str:
    lines = [
        "# Shiliu V3.5 Stage 2R-B1-C — Canary Human Adjudication Bundle",
        "",
        "This bundle combines the two frozen Canary reviews for human adjudication. It is not Final Gold and contains no automatic Human Decision.",
        "",
    ]
    for run_name in RUNS:
        root = B1B_ROOT / run_name
        # Read the accepted Human Packet as the requested source-of-record handoff,
        # then render structured fields from its frozen packet/review artifacts.
        human_packet = root / "human_review_packet.md"
        human_packet.read_text(encoding="utf-8")
        packet = QueryProjectedAnnotationPacketV2.model_validate(_read(root / "primary/reviewer_packet.json"))
        primary = AnnotationReviewV2.model_validate(_read(root / "primary/canonical_review.json"))
        secondary = AnnotationReviewV2.model_validate(_read(root / "secondary/canonical_review.json"))
        agreement = AnnotationAgreementV2.model_validate(_read(root / "agreement.json"))
        lines.extend(_render_case(packet, primary, secondary, agreement, root, human_packet))
    lines.extend(
        [
            "## Bundle Guardrails",
            "",
            "- No majority vote or automatic adjudication was applied.",
            "- No Final Gold was produced.",
            "- No third Case was selected or reviewed.",
            "- Remaining Pilot authorization remains false pending both Human Decisions.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_case(
    packet: QueryProjectedAnnotationPacketV2,
    primary: AnnotationReviewV2,
    secondary: AnnotationReviewV2,
    agreement: AnnotationAgreementV2,
    root: Path,
    human_packet: Path,
) -> list[str]:
    source = packet.source_metadata
    lines = [
        f"## Case — {packet.case_id}",
        "",
        "### Case Information",
        "",
        f"- `case_id`: `{packet.case_id}`",
        f"- `original_query`: {packet.original_query}",
        f"- `evaluation_view`: `{packet.evaluation_view}`",
        f"- `evidence_question`: {packet.evidence_question}",
        f"- Source / video: `{source.get('video_id')}`",
        f"- Source type: `{source.get('source_type')}`",
        f"- Source language: `{source.get('source_language')}`",
        f"- Transcript boundaries: `{packet.full_raw_transcript[0].segment_id}` → `{packet.full_raw_transcript[-1].segment_id}`",
        f"- Packet hash: `{packet.case_input_sha256}`",
        f"- Original Human Packet: `{human_packet.as_posix()}`",
        "",
    ]
    lines.extend(_render_review("Primary Review", primary, packet))
    lines.extend(_render_review("Secondary Review", secondary, packet))
    lines.extend(_render_agreement(agreement))
    lines.extend(_focus_questions(packet.case_id))
    lines.extend(_blank_human_decision())
    return lines


def _render_review(
    heading: str, review: AnnotationReviewV2, packet: QueryProjectedAnnotationPacketV2
) -> list[str]:
    body = review.review
    aspect_text = {aspect.aspect_id: aspect.description for aspect in body.required_aspects}
    by_segment = {segment.segment_id: segment for segment in packet.full_raw_transcript}
    lines = [
        f"### {heading}",
        "",
        f"- Status: `{body.status}`",
        f"- Required aspects: `{aspect_text}`",
        f"- Supported aspects: `{[(value, aspect_text.get(value)) for value in body.supported_aspects]}`",
        f"- Missing aspects: `{[(value, aspect_text.get(value)) for value in body.missing_aspects]}`",
        f"- Evidence groups: `{[group.model_dump(mode='json') for group in body.acceptable_evidence_groups]}`",
        f"- Reason codes: `{list(body.reason_codes)}`",
        f"- Confidence: `{body.confidence}`",
        f"- Boundary notes: {body.boundary_notes or '(none)'}",
        "- Required spans:",
        "",
    ]
    if not body.required_spans:
        lines.append("  - None.")
    for span in body.required_spans:
        selected = [by_segment[segment_id] for segment_id in span.segment_ids]
        raw_text = " ".join(segment.text for segment in selected)
        lines.extend(
            [
                f"  - `{span.span_id}` — `{span.start_time:.3f}s` → `{span.end_time:.3f}s`",
                f"    - Segment IDs: `{list(span.segment_ids)}`",
                f"    - Required Aspect IDs: `{list(span.required_aspect_ids)}`",
                f"    - Raw transcript text: {raw_text}",
            ]
        )
    lines.extend(
        [
            "- Optional context spans:",
            "",
            f"  - `{[span.model_dump(mode='json') for span in body.optional_context_spans]}`",
            "",
        ]
    )
    return lines


def _render_agreement(agreement: AnnotationAgreementV2) -> list[str]:
    return [
        "### Mechanical Agreement",
        "",
        f"- Label agreement: `{agreement.label_exact_agreement}`",
        f"- Aspect agreement: `{agreement.required_aspect_agreement.model_dump(mode='json')}`",
        f"- Supported aspect agreement: `{agreement.supported_aspect_agreement.model_dump(mode='json')}`",
        f"- Missing aspect agreement: `{agreement.missing_aspect_agreement.model_dump(mode='json')}`",
        f"- Evidence-group agreement: `{agreement.evidence_group_agreement.model_dump(mode='json')}`",
        f"- Span IoU: `{agreement.required_span_overlap.model_dump(mode='json')}`",
        f"- Time-region agreement: `{agreement.time_region_overlap.model_dump(mode='json')}`",
        f"- Source agreement: `{agreement.source_agreement}`",
        f"- Reason-code agreement: `{agreement.reason_code_agreement.model_dump(mode='json')}`",
        f"- Mandatory Human Review triggers: `{list(agreement.mandatory_triggers)}`",
        "",
    ]


def _focus_questions(case_id: str) -> list[str]:
    if case_id == "V2C_B1A00001":
        questions = (
            "是否批准 `insufficient`？",
            "Required Aspect 应采用哪种规范表达？",
            "Missing Aspect 如何表达？",
            "Reason Code 和 Boundary Note 如何处理？",
        )
    else:
        questions = (
            "是否批准 `sufficient`？",
            "应采用一个宽 Span，还是两个互补 Required Spans？",
            "CLI 架构说明是否属于必要证据？",
            "MCP 的授权、边界情况和效率说明是否必须同时存在？",
            "Required Aspect 的最终规范表达是什么？",
            "Reason Code 是否保留？",
        )
    return ["### Human Focus Questions", ""] + [
        f"{index}. {question}" for index, question in enumerate(questions, start=1)
    ] + [""]


def _blank_human_decision() -> list[str]:
    return [
        "### Blank Human Decision Template",
        "",
        "```yaml",
        "human_decision:",
        "  action:  # choose one: approve_primary | approve_secondary | merge_and_revise | reject_both",
        "  final_status:",
        "  final_required_aspects:",
        "  final_supported_aspects:",
        "  final_missing_aspects:",
        "  final_evidence_groups:",
        "  final_required_spans:",
        "  final_optional_context:",
        "  final_reason_codes:",
        "  final_boundary_notes:",
        "  adjudication_reason:",
        "```",
        "",
    ]


def historical_usage_completeness() -> dict[str, object]:
    paths: list[dict[str, object]] = []
    complete = True
    for run in RUNS:
        root = B1B_ROOT / run
        for role in ("primary", "secondary"):
            role_root = root / role
            manifest = _read(role_root / "provider_result_manifest.json")
            repair = (role_root / "reviewer_draft.repair.json").exists()
            per_attempt_exists = (role_root / "provider_attempt_usage.jsonl").exists()
            if not per_attempt_exists:
                complete = False
            paths.append(
                {
                    "case_id": manifest["case_id"],
                    "reviewer_role": role,
                    "historical_transport_attempt_count": manifest["transport_attempt_count"],
                    "repair_attempted": manifest["repair_attempted"],
                    "selected_body_input_tokens": manifest.get("input_tokens", "unavailable"),
                    "selected_body_output_tokens": manifest.get("output_tokens", "unavailable"),
                    "per_attempt_usage_record_available": per_attempt_exists,
                    "historical_usage_fabricated": False,
                }
            )
    return {
        "b1_b_historical_attempt_usage_complete": complete,
        "batch_total_classification": "complete" if complete else "lower_bound",
        "historical_usage_backfilled": False,
        "reason": (
            "B1-B did not persist every successful Draft body separately; missing historical tokens remain unavailable"
            if not complete
            else "all historical attempt records available"
        ),
        "paths": paths,
    }


def usage_batch_summary(historical: dict[str, object]) -> dict[str, object]:
    usage_path = B1C_ROOT / "provider_attempt_usage.jsonl"
    records = [
        json.loads(line)
        for line in usage_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    returned = [record for record in records if record["model_body_returned"]]
    complete = all(
        record[field] != "unavailable"
        for record in returned
        for field in ("input_tokens", "output_tokens", "cached_tokens")
    )
    return {
        "stage2r_b1_c_transport_attempt_count": len(records),
        "stage2r_b1_c_usage_complete": complete,
        "stage2r_b1_c_total_classification": "complete" if complete else "lower_bound",
        "stage2r_b1_c_input_tokens": sum(
            int(record["input_tokens"])
            for record in returned
            if isinstance(record["input_tokens"], int)
        ),
        "stage2r_b1_c_output_tokens": sum(
            int(record["output_tokens"])
            for record in returned
            if isinstance(record["output_tokens"], int)
        ),
        "stage2r_b1_c_cached_tokens": sum(
            int(record["cached_tokens"])
            for record in returned
            if isinstance(record["cached_tokens"], int)
        ),
        "b1_b_historical_total_classification": historical["batch_total_classification"],
        "b1_b_historical_usage_backfilled": False,
        "combined_b1_b_and_b1_c_total_classification": "lower_bound",
    }


def _protected_artifacts() -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for run in RUNS
            for path in (B1B_ROOT / run).rglob("*")
            if path.is_file()
            and path.name
            in {
                "reviewer_draft.initial.json",
                "reviewer_draft.repair.json",
                "canonical_review.json",
                "agreement.json",
                "human_review_packet.md",
            }
        )
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
