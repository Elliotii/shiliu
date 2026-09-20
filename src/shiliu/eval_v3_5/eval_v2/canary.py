from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from shiliu.domain import PipelineError

from .agreement import compare_reviews
from .contracts import AnnotationPacketV2, AnnotationReviewV2, TranscriptSegment
from .hashing import stable_sha256
from .packets import verify_packet_hash
from .providers import (
    ReviewerPayload,
    audit_reviewer_payload,
    reviewer_draft_prompt,
)
from .reviewer_registry import PRIMARY_REVIEWER, SECONDARY_REVIEWER, ReviewerProviderConfig
from .query_projection import (
    QUERY_PROJECTION_POLICY_VERSION,
    QueryProjectedAnnotationPacketV2,
    validate_projection,
)
from .stage2r_b_runtime import (
    ProviderInvocationError,
    RawInvocation,
    bind_and_validate,
)


MAX_TRANSPORT_ATTEMPTS = 3


@dataclass(frozen=True)
class CanaryCaseSpec:
    case_id: str
    candidate_id: str
    query_id: str
    query: str
    evaluation_view: str
    evidence_question: str
    projection_policy_version: str
    projection_status: str
    query_language: str
    query_family: str
    leakage_group: str
    case_class: str
    selection_reason: str
    complexity_tags: tuple[str, ...]
    video_id: str
    source_language: str
    source_type: str
    raw_subtitle_json: Path
    full_transcript_reference: Path
    development_authorization_source: str


@dataclass(frozen=True)
class TransportAttempt:
    attempt: int
    phase: str
    payload_fingerprint: str
    success: bool
    latency_ms: int
    failure_class: str | None = None
    http_status: int | None = None
    retry_delay_ms: int = 0
    safe_provider_error_code: str | None = None
    request_id: str | None = None
    safe_response_headers: tuple[tuple[str, str], ...] = ()
    model_body_returned: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    provider_latency_ms: int | None = None


@dataclass
class TransportBudget:
    attempts: list[TransportAttempt] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return MAX_TRANSPORT_ATTEMPTS - len(self.attempts)


@dataclass(frozen=True)
class CanaryPathResult:
    status: str
    initial: RawInvocation | None
    repaired: RawInvocation | None
    canonical_review: AnnotationReviewV2 | None
    initial_errors: tuple[str, ...]
    final_errors: tuple[str, ...]
    transport_attempts: tuple[TransportAttempt, ...]
    repair_attempted: bool
    provider_error: str | None
    end_to_end_latency_ms: int
    query_grounding_status: str = "valid"
    query_grounding_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanaryCaseResult:
    spec: CanaryCaseSpec
    review_run_id: str
    packet: AnnotationPacketV2
    packet_sha256: str
    primary: CanaryPathResult
    secondary: CanaryPathResult
    agreement: object | None
    run_root: Path
    human_packet_path: Path


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def build_canary_packet(spec: CanaryCaseSpec) -> QueryProjectedAnnotationPacketV2:
    projection_status = validate_projection(
        original_query=spec.query,
        evaluation_view=spec.evaluation_view,
        evidence_question=spec.evidence_question,
    )
    if spec.projection_status != "annotatable" or projection_status != "annotatable":
        raise ValueError("projection_status=not_annotatable")
    if spec.projection_policy_version != QUERY_PROJECTION_POLICY_VERSION:
        raise ValueError("unsupported query projection policy")
    raw_bytes = spec.raw_subtitle_json.read_bytes()
    raw = json.loads(raw_bytes)
    if not isinstance(raw, list) or not raw:
        raise ValueError("raw subtitle must be a non-empty segment array")
    version_hash = hashlib.sha256(raw_bytes).hexdigest()
    source_artifact = f"raw_subtitle:{spec.video_id}:p1"
    source_version = f"sha256:{version_hash}"
    timeline_run = f"timeline_{version_hash[:16]}"
    segments = tuple(
        TranscriptSegment(
            segment_id=f"{spec.video_id}_seg_{index:06d}",
            start_time=float(item["from"]),
            end_time=float(item["to"]),
            text=str(item["content"]),
            source_language=spec.source_language,
            source_type=spec.source_type,
            timeline_run_id=timeline_run,
            source_artifact_id=source_artifact,
            source_version=source_version,
        )
        for index, item in enumerate(raw, start=1)
    )
    source_metadata = {
            "video_id": spec.video_id,
            "source_artifact_id": source_artifact,
            "source_version": source_version,
            "timeline_run_id": timeline_run,
            "source_type": spec.source_type,
            "source_language": spec.source_language,
            "full_transcript": True,
            "transcript_first_segment_id": segments[0].segment_id,
            "transcript_last_segment_id": segments[-1].segment_id,
            "development_pilot": True,
        }
    base = {
        "packet_version": "v3.5-annotation-packet-v2",
        "case_id": spec.case_id,
        "query": spec.query,
        "original_query": spec.query,
        "evaluation_view": spec.evaluation_view,
        "evidence_question": spec.evidence_question,
        "projection_policy_version": spec.projection_policy_version,
        "query_language": spec.query_language,
        "full_raw_transcript": [x.model_dump(mode="json") for x in segments],
        "source_metadata": source_metadata,
        "segment_schema": "v3.5-raw-segment-review-v2",
        "annotation_protocol_version": "v3.5-annotation-protocol-v2",
        "review_output_schema_version": "v3.5-annotation-review-v2",
    }
    packet = QueryProjectedAnnotationPacketV2.model_validate(
        {**base, "case_input_sha256": stable_sha256(base)}
    )
    if not verify_packet_hash(packet):
        raise ValueError("packet hash verification failed")
    return packet


def packet_duration(packet: AnnotationPacketV2) -> float:
    if not packet.full_raw_transcript:
        return 0.0
    return max(x.end_time for x in packet.full_raw_transcript) - min(
        x.start_time for x in packet.full_raw_transcript
    )


def payload_fingerprint(payload: ReviewerPayload, config: ReviewerProviderConfig) -> str:
    return hashlib.sha256(
        payload.packet_bytes
        + b"\0"
        + payload.prompt.encode("utf-8")
        + b"\0"
        + canonical_bytes(payload.draft_schema)
        + b"\0"
        + canonical_bytes(asdict(config))
    ).hexdigest()


def invoke_with_transport_budget(
    *,
    invoke: Callable[[], RawInvocation],
    phase: str,
    fingerprint: str,
    budget: TransportBudget,
    delays_ms: tuple[int, int] = (500, 1000),
) -> RawInvocation | None:
    while budget.remaining > 0:
        attempt_number = len(budget.attempts) + 1
        started = time.perf_counter()
        try:
            result = invoke()
        except PipelineError as exc:
            latency_ms = round((time.perf_counter() - started) * 1000)
            retry = bool(exc.retryable and budget.remaining > 1)
            delay_ms = delays_ms[min(attempt_number - 1, len(delays_ms) - 1)] if retry else 0
            budget.attempts.append(
                TransportAttempt(
                    attempt=attempt_number,
                    phase=phase,
                    payload_fingerprint=fingerprint,
                    success=False,
                    latency_ms=latency_ms,
                    failure_class=getattr(exc, "failure_class", exc.code),
                    http_status=getattr(exc, "http_status", None),
                    retry_delay_ms=delay_ms,
                    safe_provider_error_code=getattr(exc, "safe_provider_error_code", None),
                    request_id=getattr(exc, "request_id", None),
                    safe_response_headers=getattr(exc, "safe_response_headers", ()),
                )
            )
            if not retry:
                return None
            time.sleep(delay_ms / 1000)
            continue
        except Exception:
            latency_ms = round((time.perf_counter() - started) * 1000)
            budget.attempts.append(
                TransportAttempt(
                    attempt=attempt_number,
                    phase=phase,
                    payload_fingerprint=fingerprint,
                    success=False,
                    latency_ms=latency_ms,
                failure_class="unexpected_provider_failure",
                )
            )
            return None
        budget.attempts.append(
            TransportAttempt(
                attempt=attempt_number,
                phase=phase,
                payload_fingerprint=fingerprint,
                success=True,
                latency_ms=round((time.perf_counter() - started) * 1000),
                model_body_returned=True,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cached_tokens=result.cached_tokens,
                provider_latency_ms=result.latency_ms,
            )
        )
        return result
    return None


def execute_canary_path(
    *,
    packet: AnnotationPacketV2,
    payload: ReviewerPayload,
    config: ReviewerProviderConfig,
    role: str,
    initial_invoke: Callable[[], RawInvocation],
    repair_invoke: Callable[[RawInvocation, tuple[str, ...]], tuple[RawInvocation, ReviewerPayload]],
    output_dir: Path,
) -> CanaryPathResult:
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "reviewer_packet.json", packet.model_dump(mode="json"))
    audit = audit_reviewer_payload(payload, config)
    if not audit.passed:
        raise ValueError("payload forbidden-field scan failed")
    _write_json(output_dir / "packet_manifest.json", asdict(audit))

    started = time.perf_counter()
    budget = TransportBudget()
    initial = invoke_with_transport_budget(
        invoke=initial_invoke,
        phase="initial",
        fingerprint=payload_fingerprint(payload, config),
        budget=budget,
    )
    if initial is None:
        result = CanaryPathResult(
            status="provider_error",
            initial=None,
            repaired=None,
            canonical_review=None,
            initial_errors=(),
            final_errors=(),
            transport_attempts=tuple(budget.attempts),
            repair_attempted=False,
            provider_error="transport_exhausted_or_non_retryable",
            end_to_end_latency_ms=round((time.perf_counter() - started) * 1000),
            query_grounding_status="not_available",
        )
        _persist_path_result(output_dir, packet, config, role, result)
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
    repaired: RawInvocation | None = None
    repair_attempted = False
    if validation.status != "valid":
        repair_attempted = True
        if budget.remaining:
            repair_holder: dict[str, ReviewerPayload] = {}

            def repair_call() -> RawInvocation:
                invocation, repair_payload = repair_invoke(initial, validation.errors)
                repair_holder["payload"] = repair_payload
                return invocation

            # Build once without invoking when the caller exposes the payload is
            # deliberately avoided; the first call records the exact repair fingerprint
            # through the payload returned by the adapter closure after success.
            repaired = invoke_with_transport_budget(
                invoke=repair_call,
                phase="repair",
                fingerprint=hashlib.sha256(
                    payload_fingerprint(payload, config).encode("ascii")
                    + canonical_bytes(list(validation.errors))
                    + canonical_bytes(initial.body)
                ).hexdigest(),
                budget=budget,
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
    status = (
        "valid" if review is not None and not repair_attempted
        else "valid_after_repair" if review is not None
        else "invalid_after_repair" if repair_attempted
        else "invalid"
    )
    result = CanaryPathResult(
        status=status,
        initial=initial,
        repaired=repaired,
        canonical_review=review,
        initial_errors=initial_errors,
        final_errors=validation.errors,
        transport_attempts=tuple(budget.attempts),
        repair_attempted=repair_attempted,
        provider_error=None if review is not None else "draft_invalid_or_repair_transport_failed",
        end_to_end_latency_ms=round((time.perf_counter() - started) * 1000),
        query_grounding_status=validation.query_grounding_status,
        query_grounding_errors=validation.query_grounding_errors,
    )
    _persist_path_result(output_dir, packet, config, role, result)
    return result


def run_canary_case(
    *,
    spec: CanaryCaseSpec,
    output_root: Path,
    primary_invoke_factory: Callable[[ReviewerPayload], RawInvocation],
    primary_repair_factory: Callable[[ReviewerPayload, RawInvocation, tuple[str, ...]], tuple[RawInvocation, ReviewerPayload]],
    secondary_invoke_factory: Callable[[ReviewerPayload], RawInvocation],
    secondary_repair_factory: Callable[[ReviewerPayload, RawInvocation, tuple[str, ...]], tuple[RawInvocation, ReviewerPayload]],
    protocol_excerpt: str,
) -> CanaryCaseResult:
    packet = build_canary_packet(spec)
    review_run_id = f"B1B_{spec.case_id}_{packet.case_input_sha256[:12]}"
    run_root = output_root / review_run_id
    run_root.mkdir(parents=True, exist_ok=False)
    primary_payload = ReviewerPayload.from_packet(
        packet, reviewer_draft_prompt(role="Primary", protocol_excerpt=protocol_excerpt)
    )
    secondary_payload = ReviewerPayload(
        packet_bytes=primary_payload.packet_bytes,
        prompt=reviewer_draft_prompt(role="Secondary", protocol_excerpt=protocol_excerpt),
        draft_schema=primary_payload.draft_schema,
    )
    if primary_payload.packet_bytes != secondary_payload.packet_bytes:
        raise ValueError("cross-provider packet bytes differ")

    primary = execute_canary_path(
        packet=packet,
        payload=primary_payload,
        config=PRIMARY_REVIEWER,
        role="primary",
        initial_invoke=lambda: primary_invoke_factory(primary_payload),
        repair_invoke=lambda raw, errors: primary_repair_factory(
            primary_payload, raw, errors
        ),
        output_dir=run_root / "primary",
    )
    secondary = execute_canary_path(
        packet=packet,
        payload=secondary_payload,
        config=SECONDARY_REVIEWER,
        role="secondary",
        initial_invoke=lambda: secondary_invoke_factory(secondary_payload),
        repair_invoke=lambda raw, errors: secondary_repair_factory(
            secondary_payload, raw, errors
        ),
        output_dir=run_root / "secondary",
    )

    agreement = None
    if primary.canonical_review is not None and secondary.canonical_review is not None:
        agreement = compare_reviews(
            primary.canonical_review,
            secondary.canonical_review,
            cross_language=False,
            asr_error=spec.source_type == "raw_asr",
        )
        _write_json(run_root / "agreement.json", agreement.model_dump(mode="json"))

    identity = {
        "review_run_id": review_run_id,
        "case_id": spec.case_id,
        "packet_sha256": primary_payload.packet_sha256,
        "primary_status": primary.status,
        "secondary_status": secondary.status,
        "primary_attempts": len(primary.transport_attempts),
        "secondary_attempts": len(secondary.transport_attempts),
        "agreement_status": agreement.status if agreement is not None else "not_available",
        "human_review_required": True,
        "primary_query_grounding": primary.query_grounding_status,
        "secondary_query_grounding": secondary.query_grounding_status,
    }
    _write_json(run_root / "review_run.json", identity)
    human_packet_path = run_root / "human_review_packet.md"
    human_packet_path.write_text(
        render_human_review_packet(
            spec=spec,
            packet=packet,
            primary=primary,
            secondary=secondary,
            agreement=agreement,
            review_run_id=review_run_id,
        ),
        encoding="utf-8",
    )
    return CanaryCaseResult(
        spec=spec,
        review_run_id=review_run_id,
        packet=packet,
        packet_sha256=primary_payload.packet_sha256,
        primary=primary,
        secondary=secondary,
        agreement=agreement,
        run_root=run_root,
        human_packet_path=human_packet_path,
    )


def render_human_review_packet(
    *,
    spec: CanaryCaseSpec,
    packet: AnnotationPacketV2,
    primary: CanaryPathResult,
    secondary: CanaryPathResult,
    agreement: object | None,
    review_run_id: str,
) -> str:
    lines = [
        f"# Human Review Packet — {spec.case_id}",
        "",
        f"- Review Run: `{review_run_id}`",
        f"- Query: {spec.query}",
        f"- Evaluation view: `{spec.evaluation_view}`",
        f"- Evidence question: {spec.evidence_question}",
        f"- Projection policy: `{spec.projection_policy_version}`",
        f"- Query family: `{spec.query_family}`",
        f"- Leakage group: `{spec.leakage_group}`",
        f"- Source / Video: `{spec.video_id}`",
        f"- Transcript boundaries: `{packet.full_raw_transcript[0].segment_id}` → `{packet.full_raw_transcript[-1].segment_id}`",
        f"- Segment count: {len(packet.full_raw_transcript)}",
        f"- Duration: {packet_duration(packet):.3f}s",
        f"- Full transcript reference: `{spec.full_transcript_reference}`",
        "",
    ]
    lines.extend(_render_review("Primary", primary, packet))
    lines.extend(_render_review("Secondary", secondary, packet))
    lines.extend(["## Mechanical Agreement", ""])
    if agreement is None:
        lines.append("Agreement unavailable because fewer than two valid Canonical Reviews were produced.")
    else:
        value = agreement.model_dump(mode="json")
        lines.extend(
            [
                f"- Overall: `{value['status']}`",
                f"- Label agreement: `{value['label_exact_agreement']}`",
                f"- Required aspects: `{value['required_aspect_agreement']}`",
                f"- Supported aspects: `{value['supported_aspect_agreement']}`",
                f"- Missing aspects: `{value['missing_aspect_agreement']}`",
                f"- Evidence groups: `{value['evidence_group_agreement']}`",
                f"- Required span overlap: `{value['required_span_overlap']}`",
                f"- Time overlap: `{value['time_region_overlap']}`",
                f"- Source agreement: `{value['source_agreement']}`",
                f"- Reason code agreement: `{value['reason_code_agreement']}`",
                f"- Mandatory triggers: `{value['mandatory_triggers']}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Review Questions",
            "",
            "- [ ] 最终 Label 是否正确？",
            "- [ ] Required Aspects 是否完整？",
            "- [ ] Evidence Groups 是否可接受？",
            "- [ ] Required Spans 是否足够且不过宽？",
            "- [ ] 是否漏掉互补证据？",
            "- [ ] 是否需要修正？",
            "",
            "Human decision: **pending**. This packet is not final Gold.",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_review(
    label: str, result: CanaryPathResult, packet: AnnotationPacketV2
) -> list[str]:
    lines = [
        f"## {label}",
        "",
        f"- Path status: `{result.status}`",
        f"- Query grounding: `{result.query_grounding_status}`",
        f"- Query grounding findings: `{list(result.query_grounding_errors)}`",
    ]
    review = result.canonical_review
    if review is None:
        lines.extend([f"- Provider error: `{result.provider_error}`", ""])
        return lines
    body = review.review
    aspect_by_id = {x.aspect_id: x.description for x in body.required_aspects}
    lines.extend(
        [
            f"- Proposed status: `{body.status}`",
            f"- Required aspects: `{aspect_by_id}`",
            f"- Supported aspects: `{[(x, aspect_by_id.get(x)) for x in body.supported_aspects]}`",
            f"- Missing aspects: `{[(x, aspect_by_id.get(x)) for x in body.missing_aspects]}`",
            f"- Evidence groups: `{[x.model_dump(mode='json') for x in body.acceptable_evidence_groups]}`",
            f"- Optional context: `{[x.span_id for x in body.optional_context_spans]}`",
            f"- Reason codes: `{list(body.reason_codes)}`",
            f"- Confidence: `{body.confidence}`",
            f"- Notes: `{body.boundary_notes}`",
            "",
            "### Required Evidence",
            "",
        ]
    )
    by_id = {x.segment_id: x for x in packet.full_raw_transcript}
    for span in body.required_spans:
        selected = [by_id[x] for x in span.segment_ids]
        raw_text = " ".join(x.text for x in selected)
        lines.extend(
            [
                f"- `{span.span_id}` — `{span.start_time:.3f}s` → `{span.end_time:.3f}s`; segments `{list(span.segment_ids)}`; source `{span.video_id}` / `{span.source_artifact_id}` / `{span.source_version}` / `{span.timeline_run_id}`",
                f"  - Raw text: {raw_text}",
            ]
        )
    lines.append("")
    return lines


def scan_artifacts_for_secrets(
    root: Path, *, secrets: tuple[str, ...]
) -> dict[str, object]:
    scanned: list[str] = []
    violations: list[str] = []
    for path in sorted(x for x in root.rglob("*") if x.is_file()):
        text = path.read_text(encoding="utf-8")
        scanned.append(path.relative_to(root).as_posix())
        if any(secret and secret in text for secret in secrets):
            violations.append(path.relative_to(root).as_posix() + ":secret_value")
        if "Authorization" in text or "Bearer " in text:
            violations.append(path.relative_to(root).as_posix() + ":authorization")
    return {
        "scanned_files": scanned,
        "violations": violations,
        "passed": not violations,
    }


def _persist_path_result(
    output_dir: Path,
    packet: AnnotationPacketV2,
    config: ReviewerProviderConfig,
    role: str,
    result: CanaryPathResult,
) -> None:
    selected = result.repaired or result.initial
    validation = {
        "initial_errors": list(result.initial_errors),
        "final_errors": list(result.final_errors),
        "status": result.status,
        "repair_count": 1 if result.repair_attempted else 0,
        "query_grounding_status": result.query_grounding_status,
        "query_grounding_errors": list(result.query_grounding_errors),
    }
    _write_json(output_dir / "reviewer_validation.json", validation)
    canonical_hash = None
    if result.canonical_review is not None:
        canonical = result.canonical_review.model_dump(mode="json")
        _write_json(output_dir / "canonical_review.json", canonical)
        canonical_hash = hashlib.sha256(canonical_bytes(canonical)).hexdigest()
    successes = [x for x in result.transport_attempts if x.success]
    failures = [asdict(x) for x in result.transport_attempts if not x.success]
    manifest = {
        "review_run_id": output_dir.parent.name,
        "case_id": packet.case_id,
        "reviewer_role": role,
        "provider_id": config.provider_id,
        "requested_model": selected.model if selected else config.model,
        "response_model_echo": selected.response_model if selected else None,
        "packet_sha256": hashlib.sha256(
            canonical_bytes(packet.model_dump(mode="json"))
        ).hexdigest(),
        "prompt_version": config.prompt_version,
        "schema_version": config.draft_schema_version,
        "transport_attempt_count": len(result.transport_attempts),
        "transport_failures": failures,
        "selected_successful_attempt": successes[-1].attempt if successes else None,
        "initial_valid": result.initial is not None and not result.initial_errors,
        "repair_attempted": result.repair_attempted,
        "repair_valid": result.repaired is not None and result.canonical_review is not None,
        "canonical_compilation_success": result.canonical_review is not None,
        "canonical_sha256": canonical_hash,
        "input_tokens": selected.input_tokens if selected else None,
        "output_tokens": selected.output_tokens if selected else None,
        "cached_tokens": selected.cached_tokens if selected else None,
        "provider_latency_ms": selected.latency_ms if selected else None,
        "end_to_end_latency_ms": result.end_to_end_latency_ms,
        "finish_reason": selected.finish_reason if selected else None,
        "cost_usd_if_available": None,
    }
    _write_json(output_dir / "provider_result_manifest.json", manifest)
    selected_phase = (
        "repair"
        if result.canonical_review is not None and result.repaired is not None
        else "initial"
        if result.canonical_review is not None and result.initial is not None
        else None
    )
    usage_records = [
        {
            "provider": config.provider_id,
            "case_id": packet.case_id,
            "reviewer_role": role,
            "attempt_index": attempt.attempt,
            "attempt_type": (
                "draft_repair"
                if attempt.success and attempt.phase == "repair"
                else "initial_draft"
                if attempt.success and attempt.phase == "initial"
                else "transport"
            ),
            "selected_for_final": bool(
                attempt.success and selected_phase == attempt.phase
            ),
            "http_status": attempt.http_status if attempt.http_status is not None else "unavailable",
            "model_body_returned": attempt.model_body_returned,
            "input_tokens": _available(attempt.input_tokens),
            "output_tokens": _available(attempt.output_tokens),
            "cached_tokens": _available(attempt.cached_tokens),
            "provider_latency_ms": _available(attempt.provider_latency_ms),
            "end_to_end_latency_ms": attempt.latency_ms,
            "safe_error_category": attempt.failure_class or "none",
        }
        for attempt in result.transport_attempts
    ]
    (output_dir / "provider_attempt_usage.jsonl").write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in usage_records
        ),
        encoding="utf-8",
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _available(value: int | None) -> int | str:
    return value if value is not None else "unavailable"
