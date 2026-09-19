"""V5.6 bounded AnswerBlock trust integration.

The canonical claim-support evaluator remains in ``evidence.claim_support``.
This module only derives its bounded input from the current answer snapshot,
applies the frozen exact-excerpt class, and adapts an optional server-owned
semantic observation interface.  Live dispatch is disabled by default.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Callable, Mapping, Protocol, Sequence

from shiliu.ask.contracts import (
    AnswerBlock,
    AnswerExecutionOutcome,
    AnswerStatus,
    AnswerTrustDisposition,
    AnswerTrustSummary,
    Citation,
    TerminationReason,
    TranscriptEvidenceSpan,
)
from shiliu.evidence.claim_support import (
    BoundedClaimSupportInput,
    ClaimSupportOutcome,
    MaterialClaim,
    SemanticSupportObservation,
    SemanticSupportVerdict,
    evaluate_bounded_claim_support,
)
from shiliu.evidence.decision import (
    AuthorizationStatus,
    CANONICAL_SEGMENT_ID_LIMIT,
    EVIDENCE_SEGMENT_CARDINALITY_EXCEEDED_REASON,
    EvidenceAuthorityReference,
    ReferenceScopeStatus,
    SourceVersionStatus,
    sha256_identity,
)


ANSWER_TRUST_SCHEMA_VERSION = "v5.6-answer-trust-v1"
EXACT_EXCERPT_CLASS = "exact_current_evidence_excerpt_v1"
MAX_VERIFIER_LOGICAL_CALLS = 1
MAX_VERIFIER_HTTP_ATTEMPTS = 2
MAX_VERIFIER_INPUT_TOKENS = 24_000
MAX_VERIFIER_OUTPUT_TOKENS = 2_048
MAX_VERIFIER_WALL_SECONDS = 12


class ClaimVerifierFailure(RuntimeError):
    code = "claim_verifier_failed"


class ClaimVerifierUnknown(RuntimeError):
    code = "claim_verifier_unknown"


@dataclass(frozen=True)
class ClaimVerifierItem:
    claim_id: str
    answer_block_id: str
    text: str
    authority_reference_ids: tuple[str, ...]
    evidence_quotes: tuple[str, ...]


@dataclass(frozen=True)
class ClaimVerifierVerdict:
    verdict: SemanticSupportVerdict
    authority_reference_ids: tuple[str, ...]


@dataclass(frozen=True)
class ClaimVerifierBatch:
    verdicts: Mapping[str, ClaimVerifierVerdict]
    verifier_reference: str
    http_attempts: int = 1


class ClaimVerifier(Protocol):
    enabled: bool

    def verify(self, claims: Sequence[ClaimVerifierItem]) -> ClaimVerifierBatch:
        """Return one committed batch observation for the supplied claims."""


class DisabledClaimVerifier:
    """Default runtime boundary: no model, credential, or price authority."""

    enabled = False

    def verify(self, claims: Sequence[ClaimVerifierItem]) -> ClaimVerifierBatch:
        raise ClaimVerifierFailure("claim verifier live dispatch is disabled")


@dataclass(frozen=True)
class TrustedAnswer:
    status: AnswerStatus
    execution_outcome: AnswerExecutionOutcome
    termination_reason: TerminationReason
    answer_blocks: tuple[AnswerBlock, ...]
    citations: tuple[Citation, ...]
    limitations: tuple[str, ...]
    summary: AnswerTrustSummary


@dataclass(frozen=True)
class SoftReviewResult:
    status: AnswerStatus
    limitations: tuple[str, ...]
    answer_version: int
    previous_answer_snapshot_hash: str
    answer_snapshot_hash: str
    changed: bool
    reasons: tuple[str, ...]
    open_aspects: tuple[str, ...]
    blocking_conflict_count: int
    contribution_count: int


EventSink = Callable[[str, Mapping[str, object]], None]


def apply_answer_trust(
    *,
    run_id: str,
    answer_blocks: Sequence[AnswerBlock],
    citations: Sequence[Citation],
    spans: Sequence[TranscriptEvidenceSpan],
    status: AnswerStatus,
    limitations: Sequence[str],
    termination_reason: TerminationReason,
    validate_current: Callable[[TranscriptEvidenceSpan], None],
    verifier: ClaimVerifier | None = None,
    event_sink: EventSink | None = None,
) -> TrustedAnswer:
    """Run exactly one bounded trust pass and atomically prune the answer."""

    verifier = verifier or DisabledClaimVerifier()
    snapshot = {
        "blocks": [value.model_dump(mode="json") for value in answer_blocks],
        "citations": [value.model_dump(mode="json") for value in citations],
        "status": status,
        "limitations": list(limitations),
    }
    answer_snapshot_hash = sha256_identity(snapshot)
    _emit(
        event_sink,
        "minimum_trust_started",
        {
            "answer_snapshot_hash": answer_snapshot_hash,
            "claim_count": len(answer_blocks),
            "claim_unit": "answer_block",
        },
    )
    span_by_id = {value.citation_id: value for value in spans}
    citation_by_id = {value.citation_id: value for value in citations}
    material_claims: list[MaterialClaim] = []
    authorities: list[EvidenceAuthorityReference] = []
    authority_seen: set[str] = set()
    observations: list[SemanticSupportObservation] = []
    support_classes: dict[str, str] = {}
    semantic_candidates: list[ClaimVerifierItem] = []
    authority_status: dict[str, SourceVersionStatus] = {}
    oversized_reference_ids = {
        value.citation_id
        for value in spans
        if len(value.segment_ids) > CANONICAL_SEGMENT_ID_LIMIT
    }

    for citation_id, span in span_by_id.items():
        current_status = SourceVersionStatus.CURRENT
        try:
            validate_current(span)
        except Exception:
            current_status = SourceVersionStatus.UNAVAILABLE
        authority_status[citation_id] = current_status

    for index, block in enumerate(answer_blocks):
        block_id = f"answer_block_{index + 1}"
        claim_id = f"claim_{sha256_identity([run_id, answer_snapshot_hash, index, block.text])[7:39]}"
        refs = tuple(dict.fromkeys(block.citation_ids))
        material_claims.append(
            MaterialClaim(
                claim_id=claim_id,
                answer_block_id=block_id,
                claim_text_hash=sha256_identity(block.text),
                authority_reference_ids=refs,
            )
        )
        for reference_id in refs:
            span = span_by_id.get(reference_id)
            if (
                span is None
                or reference_id in authority_seen
                or reference_id in oversized_reference_ids
            ):
                continue
            authority_seen.add(reference_id)
            authorities.append(
                EvidenceAuthorityReference(
                    reference_id=reference_id,
                    source_artifact_id=span.source_artifact_id,
                    source_version=span.source_version,
                    timeline_run_id=span.timeline_run_id,
                    segment_ids=span.segment_ids,
                    source_version_status=authority_status[reference_id],
                    scope_status=ReferenceScopeStatus.IN_SCOPE,
                    authorization_status=AuthorizationStatus.AUTHORIZED,
                )
            )
        exact = (
            len(refs) == 1
            and refs[0] in span_by_id
            and refs[0] not in oversized_reference_ids
            and authority_status.get(refs[0]) == SourceVersionStatus.CURRENT
            and _normalized(block.text) in _normalized(span_by_id[refs[0]].quote_text)
        )
        if exact:
            support_classes[claim_id] = EXACT_EXCERPT_CLASS
            observations.append(
                SemanticSupportObservation(
                    observation_id=f"exact_{claim_id}",
                    claim_id=claim_id,
                    verdict=SemanticSupportVerdict.SUPPORTED,
                    authority_reference_ids=refs,
                    verifier_reference=EXACT_EXCERPT_CLASS,
                )
            )
        else:
            support_classes[claim_id] = "unobserved"
            complete_support_eligible = not any(
                value in oversized_reference_ids for value in refs
            )
            eligible_refs = tuple(
                value
                for value in refs
                if value in span_by_id
                and authority_status.get(value) == SourceVersionStatus.CURRENT
                and value not in oversized_reference_ids
            )
            if complete_support_eligible and eligible_refs:
                semantic_candidates.append(
                    ClaimVerifierItem(
                        claim_id=claim_id,
                        answer_block_id=block_id,
                        text=block.text,
                        authority_reference_ids=eligible_refs,
                        evidence_quotes=tuple(
                            span_by_id[value].quote_text for value in eligible_refs
                        ),
                    )
                )

    verifier_state = "not_needed"
    verifier_calls = 0
    verifier_attempts = 0
    semantic_passes = 0
    verifier_reason: str | None = None
    if semantic_candidates and not bool(getattr(verifier, "enabled", False)):
        verifier_state = "disabled"
        verifier_reason = "claim_verifier_disabled"
    elif semantic_candidates:
        verifier_calls = 1
        request_hash = sha256_identity(
            [
                {
                    "claim_id": value.claim_id,
                    "text": value.text,
                    "authority_reference_ids": list(value.authority_reference_ids),
                    "evidence_quotes": list(value.evidence_quotes),
                }
                for value in semantic_candidates
            ]
        )
        _emit(
            event_sink,
            "claim_verifier_call_reserved",
            {
                "request_hash": request_hash,
                "role": "claim_support_verifier",
                "live_dispatch_default": "disabled",
                "max_logical_calls": MAX_VERIFIER_LOGICAL_CALLS,
                "max_http_attempts": MAX_VERIFIER_HTTP_ATTEMPTS,
                "max_input_tokens": MAX_VERIFIER_INPUT_TOKENS,
                "max_output_tokens": MAX_VERIFIER_OUTPUT_TOKENS,
                "max_wall_seconds": MAX_VERIFIER_WALL_SECONDS,
            },
        )
        try:
            batch = verifier.verify(tuple(semantic_candidates))
            verifier_attempts = int(batch.http_attempts)
            if verifier_attempts < 1 or verifier_attempts > MAX_VERIFIER_HTTP_ATTEMPTS:
                raise ClaimVerifierFailure("verifier exceeded HTTP attempt boundary")
            for item in semantic_candidates:
                verdict = batch.verdicts.get(item.claim_id)
                if verdict is None:
                    continue
                bound = tuple(
                    value
                    for value in verdict.authority_reference_ids
                    if value in item.authority_reference_ids
                )
                if not bound:
                    continue
                observations.append(
                    SemanticSupportObservation(
                        observation_id=f"semantic_{item.claim_id}",
                        claim_id=item.claim_id,
                        verdict=verdict.verdict,
                        authority_reference_ids=bound,
                        verifier_reference=batch.verifier_reference,
                    )
                )
                support_classes[item.claim_id] = "semantic_observation"
            semantic_passes = 1
            verifier_state = "committed"
            _emit(
                event_sink,
                "claim_verifier_call_committed",
                {
                    "request_hash": request_hash,
                    "verifier_reference": batch.verifier_reference,
                    "http_attempts": verifier_attempts,
                    "observation_count": len(batch.verdicts),
                },
            )
        except ClaimVerifierUnknown as exc:
            verifier_state = "unknown"
            verifier_reason = str(getattr(exc, "code", "claim_verifier_unknown"))
            _emit(event_sink, "claim_verifier_call_unknown", {"request_hash": request_hash})
        except Exception as exc:
            verifier_state = "failed"
            verifier_reason = str(getattr(exc, "code", "claim_verifier_failed"))
            _emit(
                event_sink,
                "claim_verifier_call_failed",
                {"request_hash": request_hash, "error_code": verifier_reason},
            )

    if not material_claims or not authorities:
        # Answer validation normally prevents this.  Keep the gate fail-closed.
        return _trust_insufficient(
            answer_snapshot_hash=answer_snapshot_hash,
            limitations=limitations,
            verifier_state=verifier_state,
            reason=(
                EVIDENCE_SEGMENT_CARDINALITY_EXCEEDED_REASON
                if oversized_reference_ids
                else "claim_authority_missing"
            ),
            evidence_unavailable=bool(oversized_reference_ids),
            event_sink=event_sink,
        )

    canonical_input = BoundedClaimSupportInput(
        material_claims=tuple(material_claims),
        authority_references=tuple(authorities),
        semantic_observations=tuple(observations),
    )
    decision = evaluate_bounded_claim_support(canonical_input)
    blocks_by_claim = dict(zip((value.claim_id for value in material_claims), answer_blocks, strict=True))
    block_ids = {value.claim_id: value.answer_block_id for value in material_claims}
    allowed_claim_ids = {
        value.claim_id
        for value in decision.dispositions
        if value.outcome == ClaimSupportOutcome.ALLOW
    }
    surviving = tuple(
        blocks_by_claim[value.claim_id]
        for value in material_claims
        if value.claim_id in allowed_claim_ids
    )
    used_ids = {
        reference_id for value in surviving for reference_id in value.citation_ids
    }
    surviving_citations = tuple(
        citation_by_id[value]
        for value in citation_by_id
        if value in used_ids
    )
    hidden_count = len(answer_blocks) - len(surviving)
    reason_codes = list(
        dict.fromkeys(
            str(reason.value)
            for disposition in decision.dispositions
            for reason in disposition.reason_codes
        )
    )
    if verifier_reason:
        reason_codes.append(verifier_reason)
    if oversized_reference_ids:
        reason_codes.append(EVIDENCE_SEGMENT_CARDINALITY_EXCEEDED_REASON)
    dispositions = [
        AnswerTrustDisposition(
            claim_id=value.claim_id,
            answer_block_id=block_ids[value.claim_id],
            outcome=value.outcome.value,
            accepted_reference_ids=list(value.accepted_reference_ids),
            rejected_reference_ids=list(value.rejected_reference_ids),
            reason_codes=[item.value for item in value.reason_codes],
            support_class=support_classes[value.claim_id],
        )
        for value in decision.dispositions
    ]
    if not surviving:
        return _trust_insufficient(
            answer_snapshot_hash=answer_snapshot_hash,
            limitations=limitations,
            verifier_state=verifier_state,
            reason_codes=reason_codes,
            dispositions=dispositions,
            input_hash=decision.input_hash,
            semantic_passes=semantic_passes,
            verifier_calls=verifier_calls,
            verifier_attempts=verifier_attempts,
            evidence_unavailable=bool(oversized_reference_ids),
            event_sink=event_sink,
        )

    for block in surviving:
        for reference_id in block.citation_ids:
            validate_current(span_by_id[reference_id])
    final_limitations = list(limitations)
    if oversized_reference_ids:
        final_limitations.append(
            "证据引用超过 canonical segment-ID 上限 "
            f"{CANONICAL_SEGMENT_ID_LIMIT}，相关回答块已隐藏"
        )
    if hidden_count:
        final_limitations.append(f"回答可信门隐藏了 {hidden_count} 个缺少独立支持的回答块")
    if verifier_state == "disabled" and semantic_candidates:
        final_limitations.append("语义核验默认关闭；仅保留当前原始证据的精确摘录")
    final_status: AnswerStatus = status
    overall = "allow"
    if hidden_count or status == "partial":
        final_status = "partial"
        overall = "partial"
    summary = AnswerTrustSummary(
        overall_outcome=overall,
        semantic_passes=semantic_passes,
        verifier_logical_calls=verifier_calls,
        verifier_http_attempts=verifier_attempts,
        verifier_state=verifier_state,
        input_hash=decision.input_hash,
        answer_snapshot_hash=answer_snapshot_hash,
        dispositions=dispositions,
        reason_codes=list(dict.fromkeys(reason_codes)),
    )
    _emit(
        event_sink,
        "minimum_trust_passed",
        {
            "answer_snapshot_hash": answer_snapshot_hash,
            "status": final_status,
            "surviving_block_count": len(surviving),
            "citation_ids": [value.citation_id for value in surviving_citations],
            "trust_summary": summary.model_dump(mode="json"),
        },
    )
    return TrustedAnswer(
        status=final_status,
        execution_outcome="answer_generated",
        termination_reason=termination_reason,
        answer_blocks=surviving,
        citations=surviving_citations,
        limitations=tuple(dict.fromkeys(final_limitations)),
        summary=summary,
    )


def provider_free_soft_review(
    *,
    answer_blocks: Sequence[AnswerBlock],
    citations: Sequence[Citation],
    limitations: Sequence[str],
    status: AnswerStatus,
    decision_projection: Mapping[str, object],
    validate_citation: Callable[[str], None],
) -> SoftReviewResult:
    """Review only current accepted state; never search, call, or rewrite facts."""

    previous_hash = sha256_identity(
        {
            "answer_blocks": [value.model_dump(mode="json") for value in answer_blocks],
            "citations": [value.model_dump(mode="json") for value in citations],
            "limitations": list(limitations),
            "status": status,
            "answer_version": 1,
        }
    )
    open_aspects = tuple(
        str(value) for value in (decision_projection.get("open_aspects") or ())
    )
    conflicts = tuple(decision_projection.get("conflicts") or ())
    blocking_conflicts = tuple(
        value
        for value in conflicts
        if isinstance(value, Mapping)
        and str(value.get("status") or "") in {"potential", "confirmed"}
    )
    contributions = tuple(decision_projection.get("contributions") or ())
    reasons: list[str] = []
    for citation in citations:
        try:
            validate_citation(citation.citation_id)
        except Exception:
            reasons.append("soft_review_source_changed")
    if open_aspects:
        reasons.append("soft_review_open_aspects_remain")
    if blocking_conflicts:
        reasons.append("soft_review_blocking_conflict")
    dropped = [
        value
        for value in contributions
        if isinstance(value, Mapping) and str(value.get("kind") or "") == "dropped"
    ]
    if dropped:
        reasons.append("soft_review_dropped_contribution")
    reviewed_limitations = list(limitations)
    if open_aspects:
        reviewed_limitations.append(
            f"展示后复核：仍有 {len(open_aspects)} 个证据方面未覆盖"
        )
    if blocking_conflicts:
        reviewed_limitations.append(
            f"展示后复核：检测到 {len(blocking_conflicts)} 个待处理冲突"
        )
    if "soft_review_source_changed" in reasons:
        reviewed_limitations.append("展示后复核：引用来源版本发生变化，请重新检索")
    if dropped:
        reviewed_limitations.append(
            f"展示后复核：{len(dropped)} 个继承证据贡献已被丢弃"
        )
    reviewed_limitations = list(dict.fromkeys(reviewed_limitations))
    changed = reviewed_limitations != list(limitations)
    reviewed_status: AnswerStatus = "partial" if changed and status == "complete" else status
    version = 2 if changed else 1
    reviewed_hash = sha256_identity(
        {
            "answer_blocks": [value.model_dump(mode="json") for value in answer_blocks],
            "citations": [value.model_dump(mode="json") for value in citations],
            "limitations": reviewed_limitations,
            "status": reviewed_status,
            "answer_version": version,
        }
    )
    return SoftReviewResult(
        status=reviewed_status,
        limitations=tuple(reviewed_limitations),
        answer_version=version,
        previous_answer_snapshot_hash=previous_hash,
        answer_snapshot_hash=reviewed_hash,
        changed=changed,
        reasons=tuple(dict.fromkeys(reasons)),
        open_aspects=open_aspects,
        blocking_conflict_count=len(blocking_conflicts),
        contribution_count=len(contributions),
    )


def _trust_insufficient(
    *,
    answer_snapshot_hash: str,
    limitations: Sequence[str],
    verifier_state: str,
    reason: str | None = None,
    reason_codes: Sequence[str] = (),
    dispositions: Sequence[AnswerTrustDisposition] = (),
    input_hash: str | None = None,
    semantic_passes: int = 0,
    verifier_calls: int = 0,
    verifier_attempts: int = 0,
    evidence_unavailable: bool = False,
    event_sink: EventSink | None,
) -> TrustedAnswer:
    reasons = list(dict.fromkeys([*reason_codes, *([reason] if reason else [])]))
    summary = AnswerTrustSummary(
        overall_outcome="insufficient",
        semantic_passes=semantic_passes,
        verifier_logical_calls=verifier_calls,
        verifier_http_attempts=verifier_attempts,
        verifier_state=verifier_state,  # type: ignore[arg-type]
        input_hash=input_hash or sha256_identity([answer_snapshot_hash, reasons]),
        answer_snapshot_hash=answer_snapshot_hash,
        dispositions=list(dispositions),
        reason_codes=reasons,
    )
    outcome: AnswerExecutionOutcome = "claim_support_insufficient"
    termination: TerminationReason = "claim_support_insufficient"
    if verifier_state == "unknown":
        outcome = "claim_verifier_unknown"
        termination = "claim_verifier_unknown"
    elif verifier_state == "failed":
        outcome = "claim_verifier_failed"
        termination = "claim_verifier_failed"
    elif evidence_unavailable:
        outcome = "evidence_unavailable"
        termination = "evidence_unavailable"
    _emit(
        event_sink,
        "minimum_trust_failed",
        {
            "answer_snapshot_hash": answer_snapshot_hash,
            "failure_class": outcome,
            "trust_summary": summary.model_dump(mode="json"),
        },
    )
    return TrustedAnswer(
        status="insufficient",
        execution_outcome=outcome,
        termination_reason=termination,
        answer_blocks=(),
        citations=(),
        limitations=tuple(
            dict.fromkeys(
                [
                    *limitations,
                    *(
                        [
                            "证据引用超过 canonical segment-ID 上限 "
                            f"{CANONICAL_SEGMENT_ID_LIMIT}，无法作为回答权威"
                        ]
                        if evidence_unavailable
                        else []
                    ),
                    "回答中的实质性陈述未通过展示前可信门，已全部隐藏",
                ]
            )
        ),
        summary=summary,
    )


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def _emit(sink: EventSink | None, event_type: str, payload: Mapping[str, object]) -> None:
    if sink is not None:
        sink(event_type, payload)
