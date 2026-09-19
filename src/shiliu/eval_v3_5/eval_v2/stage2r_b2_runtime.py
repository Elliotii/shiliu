from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from shiliu.domain import PipelineError

from .agreement import compare_reviews
from .canary import CanaryCaseSpec, build_canary_packet, canonical_bytes, packet_duration
from .contracts import AnnotationReviewV2
from .providers import (
    ReviewerPayload,
    audit_reviewer_payload,
    reviewer_draft_prompt,
)
from .reviewer_registry import PRIMARY_REVIEWER, SECONDARY_REVIEWER, ReviewerProviderConfig
from .stage2r_b_runtime import (
    ProviderInvocationError,
    RawInvocation,
    bind_and_validate,
    canonical_json,
)


@dataclass
class B2Attempt:
    provider: str
    case_id: str
    reviewer_role: str
    attempt_index: int
    attempt_type: str
    selected_for_final: bool
    http_status: int | str
    model_body_returned: bool
    input_tokens: int | str
    output_tokens: int | str
    cached_tokens: int | str
    provider_latency_ms: int | str
    end_to_end_latency_ms: int
    safe_error_category: str
    payload_fingerprint: str


@dataclass
class B2PathResult:
    status: str
    initial: RawInvocation | None
    repaired: RawInvocation | None
    canonical_review: AnnotationReviewV2 | None
    initial_errors: tuple[str, ...]
    final_errors: tuple[str, ...]
    grounding_status: str
    grounding_errors: tuple[str, ...]
    repair_count: int
    attempts: list[B2Attempt]


def run_b2_case(
    *,
    spec: CanaryCaseSpec,
    output_root: Path,
    primary_invoke: Callable[[ReviewerPayload], RawInvocation],
    secondary_invoke: Callable[[object, str], RawInvocation],
    protocol_excerpt: str,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    packet = build_canary_packet(spec)
    case_root = output_root / spec.case_id
    case_root.mkdir(parents=True, exist_ok=False)
    primary_payload = ReviewerPayload.from_packet(
        packet, reviewer_draft_prompt(role="Primary", protocol_excerpt=protocol_excerpt)
    )
    secondary_payload = ReviewerPayload(
        packet_bytes=primary_payload.packet_bytes,
        prompt=reviewer_draft_prompt(role="Secondary", protocol_excerpt=protocol_excerpt),
        draft_schema=primary_payload.draft_schema,
    )
    if primary_payload.packet_bytes != secondary_payload.packet_bytes:
        raise RuntimeError("primary_secondary_packet_mismatch")

    primary = _run_path(
        packet=packet,
        payload=primary_payload,
        config=PRIMARY_REVIEWER,
        role="primary",
        max_attempts=5,
        retry_delays=(1, 2, 4, 8),
        invoke=lambda payload: primary_invoke(payload),
        sleep=sleep,
        output_dir=case_root / "primary",
    )
    secondary = _run_path(
        packet=packet,
        payload=secondary_payload,
        config=SECONDARY_REVIEWER,
        role="secondary",
        max_attempts=3,
        retry_delays=(1, 2),
        invoke=lambda payload: secondary_invoke(packet, payload.prompt),
        sleep=sleep,
        output_dir=case_root / "secondary",
    )

    agreement = None
    if primary.canonical_review is not None and secondary.canonical_review is not None:
        agreement = compare_reviews(
            primary.canonical_review,
            secondary.canonical_review,
            cross_language=False,
            asr_error=spec.source_type == "raw_asr",
        )
        _write_json(case_root / "agreement.json", agreement.model_dump(mode="json"))
        agreement_status = agreement.status
    else:
        agreement_status = derive_unavailable_agreement_status(
            primary.canonical_review, secondary.canonical_review
        )

    packet_hash = hashlib.sha256(primary_payload.packet_bytes).hexdigest()
    identity = {
        "case_id": spec.case_id,
        "candidate_id": spec.candidate_id,
        "packet_sha256": packet_hash,
        "packet_bytes_equal": True,
        "projection_status": spec.projection_status,
        "primary_status": primary.status,
        "secondary_status": secondary.status,
        "agreement_status": agreement_status,
        "human_review_required": True,
    }
    _write_json(case_root / "review_run.json", identity)
    (case_root / "human_review_packet.md").write_text(
        _render_human_packet(spec, packet, primary, secondary, agreement, agreement_status),
        encoding="utf-8",
    )
    return {
        **identity,
        "primary": primary,
        "secondary": secondary,
        "agreement": agreement,
        "case_root": case_root,
        "human_review_packet": case_root / "human_review_packet.md",
    }


def _run_path(
    *,
    packet,
    payload: ReviewerPayload,
    config: ReviewerProviderConfig,
    role: str,
    max_attempts: int,
    retry_delays: tuple[int, ...],
    invoke: Callable[[ReviewerPayload], RawInvocation],
    sleep: Callable[[float], None],
    output_dir: Path,
) -> B2PathResult:
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "reviewer_packet.json", packet.model_dump(mode="json"))
    audit = audit_reviewer_payload(payload, config)
    if not audit.passed:
        raise RuntimeError("forbidden_reviewer_payload")
    _write_json(output_dir / "packet_manifest.json", asdict(audit))
    attempts: list[B2Attempt] = []
    initial = _invoke_phase(
        payload=payload,
        invoke=invoke,
        config=config,
        packet_case_id=packet.case_id,
        role=role,
        phase="initial",
        max_total_attempts=max_attempts,
        retry_delays=retry_delays,
        attempts=attempts,
        sleep=sleep,
    )
    if initial is None:
        result = B2PathResult(
            status=f"{role}_transport_failed",
            initial=None,
            repaired=None,
            canonical_review=None,
            initial_errors=(),
            final_errors=(),
            grounding_status="not_available",
            grounding_errors=(),
            repair_count=0,
            attempts=attempts,
        )
        _persist_path(output_dir, result)
        return result

    _write_json(output_dir / "reviewer_draft.initial.json", initial.body)
    validation = bind_and_validate(
        packet=packet,
        invocation=initial,
        provider=config.provider_id,
        role=role,
        prompt_version=config.prompt_version,
        repair_count=0,
    )
    initial_errors = validation.errors
    repaired = None
    repair_count = 0
    if validation.status != "valid" and len(attempts) < max_attempts:
        repair_count = 1
        repair_payload = _repair_payload(role, payload, initial, validation.errors)
        repaired = _invoke_phase(
            payload=repair_payload,
            invoke=invoke,
            config=config,
            packet_case_id=packet.case_id,
            role=role,
            phase="repair",
            max_total_attempts=max_attempts,
            retry_delays=retry_delays,
            attempts=attempts,
            sleep=sleep,
        )
        if repaired is not None:
            _write_json(output_dir / "reviewer_draft.repair.json", repaired.body)
            validation = bind_and_validate(
                packet=packet,
                invocation=repaired,
                provider=config.provider_id,
                role=role,
                prompt_version=config.repair_prompt_version,
                repair_count=1,
            )

    review = validation.review if validation.status == "valid" else None
    selected_phase = "repair" if review is not None and repaired is not None else "initial" if review is not None else None
    for attempt in attempts:
        if attempt.model_body_returned and (
            (selected_phase == "repair" and attempt.attempt_type == "draft_repair")
            or (selected_phase == "initial" and attempt.attempt_type == "initial_draft")
        ):
            attempt.selected_for_final = True
    status = (
        "valid_after_repair" if review is not None and repaired is not None
        else "valid" if review is not None
        else "invalid_after_repair" if repair_count else "invalid"
    )
    result = B2PathResult(
        status=status,
        initial=initial,
        repaired=repaired,
        canonical_review=review,
        initial_errors=initial_errors,
        final_errors=validation.errors,
        grounding_status=validation.query_grounding_status,
        grounding_errors=validation.query_grounding_errors,
        repair_count=repair_count,
        attempts=attempts,
    )
    _persist_path(output_dir, result)
    return result


def _invoke_phase(
    *, payload: ReviewerPayload, invoke: Callable[[ReviewerPayload], RawInvocation],
    config: ReviewerProviderConfig, packet_case_id: str, role: str, phase: str,
    max_total_attempts: int, retry_delays: tuple[int, ...], attempts: list[B2Attempt],
    sleep: Callable[[float], None],
) -> RawInvocation | None:
    fingerprint = hashlib.sha256(
        payload.packet_bytes + b"\0" + payload.prompt.encode("utf-8")
        + b"\0" + canonical_bytes(payload.draft_schema)
        + b"\0" + canonical_bytes(asdict(config))
    ).hexdigest()
    phase_failure_count = 0
    while len(attempts) < max_total_attempts:
        index = len(attempts) + 1
        started = time.perf_counter()
        try:
            result = invoke(payload)
        except PipelineError as exc:
            elapsed = round((time.perf_counter() - started) * 1000)
            attempts.append(
                B2Attempt(
                    provider=config.provider_id, case_id=packet_case_id,
                    reviewer_role=role, attempt_index=index, attempt_type="transport",
                    selected_for_final=False,
                    http_status=getattr(exc, "http_status", None) or "unavailable",
                    model_body_returned=False, input_tokens="unavailable",
                    output_tokens="unavailable", cached_tokens="unavailable",
                    provider_latency_ms="unavailable", end_to_end_latency_ms=elapsed,
                    safe_error_category=getattr(exc, "failure_class", exc.code),
                    payload_fingerprint=fingerprint,
                )
            )
            if not exc.retryable or len(attempts) >= max_total_attempts:
                return None
            delay_index = min(phase_failure_count, len(retry_delays) - 1)
            phase_failure_count += 1
            sleep(retry_delays[delay_index])
            continue
        except Exception:
            elapsed = round((time.perf_counter() - started) * 1000)
            attempts.append(
                B2Attempt(
                    provider=config.provider_id, case_id=packet_case_id,
                    reviewer_role=role, attempt_index=index, attempt_type="transport",
                    selected_for_final=False, http_status="unavailable",
                    model_body_returned=False, input_tokens="unavailable",
                    output_tokens="unavailable", cached_tokens="unavailable",
                    provider_latency_ms="unavailable", end_to_end_latency_ms=elapsed,
                    safe_error_category="unexpected_provider_failure",
                    payload_fingerprint=fingerprint,
                )
            )
            return None
        elapsed = round((time.perf_counter() - started) * 1000)
        attempts.append(
            B2Attempt(
                provider=config.provider_id, case_id=packet_case_id,
                reviewer_role=role, attempt_index=index,
                attempt_type="draft_repair" if phase == "repair" else "initial_draft",
                selected_for_final=False, http_status="unavailable",
                model_body_returned=True,
                input_tokens=_available(result.input_tokens),
                output_tokens=_available(result.output_tokens),
                cached_tokens=_available(result.cached_tokens),
                provider_latency_ms=result.latency_ms,
                end_to_end_latency_ms=elapsed, safe_error_category="none",
                payload_fingerprint=fingerprint,
            )
        )
        return result
    return None


def _repair_payload(
    role: str, payload: ReviewerPayload, raw: RawInvocation, errors: tuple[str, ...]
) -> ReviewerPayload:
    prompt = "\n\n".join(
        [
            f"Repair only the supplied {role} ReviewerDraft. Return one JSON object matching the frozen Draft Schema. Preserve evidence_question and exact query anchors. Use only the original Packet, this Draft, the Schema, and Validation Errors. Never use another review or create A/S/G IDs.",
            "VALIDATION ERRORS:\n" + canonical_json(list(errors)),
            "ORIGINAL REVIEWER DRAFT:\n" + canonical_json(raw.body),
        ]
    )
    return ReviewerPayload(payload.packet_bytes, prompt, payload.draft_schema)


def _persist_path(output_dir: Path, result: B2PathResult) -> None:
    _write_json(
        output_dir / "reviewer_validation.json",
        {
            "status": result.status,
            "initial_errors": list(result.initial_errors),
            "final_errors": list(result.final_errors),
            "query_grounding_status": result.grounding_status,
            "query_grounding_errors": list(result.grounding_errors),
            "repair_count": result.repair_count,
        },
    )
    if result.canonical_review is not None:
        _write_json(
            output_dir / "canonical_review.json",
            result.canonical_review.model_dump(mode="json"),
        )
    (output_dir / "provider_attempt_usage.jsonl").write_text(
        "".join(json.dumps(asdict(attempt), ensure_ascii=False, sort_keys=True) + "\n" for attempt in result.attempts),
        encoding="utf-8",
    )


def _render_human_packet(spec, packet, primary, secondary, agreement, agreement_status) -> str:
    lines = [
        f"# Human Review Packet — {spec.case_id}", "",
        f"- Original Query: {spec.query}",
        f"- Evaluation View: `{spec.evaluation_view}`",
        f"- Evidence Question: {spec.evidence_question}",
        f"- Projection Status: `{spec.projection_status}`",
        f"- Source / Video: `{spec.video_id}`",
        f"- Source Type / Language: `{spec.source_type}` / `{spec.source_language}`",
        f"- Transcript boundaries: `{packet.full_raw_transcript[0].segment_id}` → `{packet.full_raw_transcript[-1].segment_id}`",
        f"- Segment count / duration: `{len(packet.full_raw_transcript)}` / `{packet_duration(packet):.3f}s`",
        f"- Full Transcript Reference: `{spec.full_transcript_reference}`", "",
    ]
    lines.extend(_render_path("Primary", primary, packet))
    lines.extend(_render_path("Secondary", secondary, packet))
    lines.extend(["## Mechanical Agreement", "", f"- Status: `{agreement_status}`"])
    if agreement is not None:
        lines.append(f"- Metrics: `{agreement.model_dump(mode='json')}`")
    lines.extend(
        [
            "", "## Blank Human Decision", "", "```yaml", "human_decision:",
            "  action:", "  final_status:", "  final_required_aspects:",
            "  final_supported_aspects:", "  final_missing_aspects:",
            "  final_evidence_groups:", "  final_required_spans:",
            "  final_optional_context:", "  final_reason_codes:",
            "  final_boundary_notes:", "  adjudication_reason:", "```", "",
            "Human decision is pending. This packet is not Final Gold.", "",
        ]
    )
    return "\n".join(lines)


def _render_path(label: str, result: B2PathResult, packet) -> list[str]:
    lines = [f"## {label}", "", f"- Status: `{result.status}`", f"- Query grounding: `{result.grounding_status}`", f"- Repair count: `{result.repair_count}`", f"- Attempts: `{[asdict(x) for x in result.attempts]}`"]
    if result.canonical_review is None:
        return lines + ["- Canonical Review: unavailable", ""]
    body = result.canonical_review.review
    by_id = {segment.segment_id: segment for segment in packet.full_raw_transcript}
    lines.extend(
        [
            f"- Proposed status: `{body.status}`",
            f"- Required aspects: `{[x.model_dump(mode='json') for x in body.required_aspects]}`",
            f"- Supported / Missing: `{list(body.supported_aspects)}` / `{list(body.missing_aspects)}`",
            f"- Evidence groups: `{[x.model_dump(mode='json') for x in body.acceptable_evidence_groups]}`",
            f"- Reason codes: `{list(body.reason_codes)}`",
            f"- Confidence: `{body.confidence}`",
            f"- Boundary notes: {body.boundary_notes or '(none)'}",
            "- Selected Raw Transcript Regions:",
        ]
    )
    if not body.required_spans:
        lines.append("  - None.")
    for span in body.required_spans:
        raw = " ".join(by_id[x].text for x in span.segment_ids)
        lines.extend([f"  - `{span.span_id}` `{span.start_time:.3f}s` → `{span.end_time:.3f}s`, segments `{list(span.segment_ids)}`", f"    - Raw text: {raw}"])
    return lines + [""]


def _available(value: int | None) -> int | str:
    return value if value is not None else "unavailable"


def derive_unavailable_agreement_status(
    primary: AnnotationReviewV2 | None, secondary: AnnotationReviewV2 | None
) -> str:
    return (
        "unavailable_single_review"
        if primary is not None or secondary is not None
        else "unavailable_no_valid_review"
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
