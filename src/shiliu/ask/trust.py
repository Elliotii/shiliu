"""V5.6 bounded AnswerBlock trust integration.

The canonical claim-support evaluator remains in ``evidence.claim_support``.
This module only derives its bounded input from the current answer snapshot,
applies the frozen exact-excerpt class, and adapts an optional server-owned
semantic observation interface.  Live dispatch is disabled by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Sequence

from shiliu.ask.contracts import (
    AnswerBlock,
    AnswerDraftBlock,
    AnswerExecutionOutcome,
    AnswerStatus,
    AnswerTrustDisposition,
    AnswerTrustSummary,
    Citation,
    TerminationReason,
    TranscriptEvidenceSpan,
)
from shiliu.evidence.claim_support import SemanticSupportVerdict
from shiliu.evidence.decision import (
    SourceVersionStatus,
    sha256_identity,
)


ANSWER_TRUST_SCHEMA_VERSION = "v5.6-answer-trust-v1"
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
    execution_outcome: AnswerExecutionOutcome
    termination_reason: TerminationReason | None
    answer_blocks: tuple[AnswerBlock, ...]
    citations: tuple[Citation, ...]
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
    answer_blocks: Sequence[AnswerDraftBlock | AnswerBlock],
    citations: Sequence[Citation],
    spans: Sequence[TranscriptEvidenceSpan],
    status: AnswerStatus,
    limitations: Sequence[str],
    termination_reason: TerminationReason,
    validate_current: Callable[[TranscriptEvidenceSpan], None],
    verifier: ClaimVerifier | None = None,
    event_sink: EventSink | None = None,
) -> TrustedAnswer:
    """Apply one deterministic Citation Integrity pass before publication."""

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
    authority_status: dict[str, SourceVersionStatus] = {}

    for citation_id, span in span_by_id.items():
        current_status = SourceVersionStatus.CURRENT
        try:
            validate_current(span)
        except Exception:
            current_status = SourceVersionStatus.UNAVAILABLE
        authority_status[citation_id] = current_status

    surviving: list[AnswerBlock] = []
    dispositions: list[AnswerTrustDisposition] = []
    reason_codes: list[str] = []
    for index, block in enumerate(answer_blocks):
        block_id = f"answer_block_{index + 1}"
        claim_id = f"claim_{sha256_identity([run_id, answer_snapshot_hash, index, block.text])[7:39]}"
        refs = tuple(dict.fromkeys(block.citation_ids))
        rejected: list[str] = []
        block_reasons: list[str] = []
        if not refs:
            block_reasons.append("citation_missing")
        for reference_id in refs:
            span = span_by_id.get(reference_id)
            if not reference_id or span is None:
                block_reasons.append("citation_not_allowed")
                rejected.append(reference_id)
            elif reference_id not in citation_by_id:
                block_reasons.append("citation_unmapped")
                rejected.append(reference_id)
            elif authority_status.get(reference_id) != SourceVersionStatus.CURRENT:
                block_reasons.append("citation_not_current")
                rejected.append(reference_id)
        block_reasons = list(dict.fromkeys(block_reasons))
        reason_codes.extend(block_reasons)
        if block_reasons:
            dispositions.append(
                AnswerTrustDisposition(
                    claim_id=claim_id,
                    answer_block_id=block_id,
                    outcome="remove",
                    accepted_reference_ids=[],
                    rejected_reference_ids=list(dict.fromkeys(rejected)),
                    reason_codes=block_reasons,
                    support_class="unobserved",
                )
            )
            continue
        strict_block = AnswerBlock(text=block.text, citation_ids=list(refs))
        surviving.append(strict_block)
        dispositions.append(
            AnswerTrustDisposition(
                claim_id=claim_id,
                answer_block_id=block_id,
                outcome="allow",
                accepted_reference_ids=list(refs),
                rejected_reference_ids=[],
                reason_codes=[],
                support_class="unobserved",
            )
        )

    reason_codes = list(dict.fromkeys(reason_codes))
    input_hash = sha256_identity(
        {
            "answer_snapshot_hash": answer_snapshot_hash,
            "allowlist": list(span_by_id),
            "dispositions": [value.model_dump(mode="json") for value in dispositions],
        }
    )
    if not surviving:
        return _trust_insufficient(
            answer_snapshot_hash=answer_snapshot_hash,
            limitations=limitations,
            verifier_state="not_needed",
            reason_codes=reason_codes or ("claim_authority_missing",),
            dispositions=dispositions,
            input_hash=input_hash,
            event_sink=event_sink,
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
    final_limitations = list(limitations)
    if hidden_count:
        final_limitations.append(
            f"回答可信门隐藏了 {hidden_count} 个引用完整性未通过的回答块"
        )
    final_status: AnswerStatus = status
    overall = "allow"
    if hidden_count or status == "partial":
        final_status = "partial"
        overall = "partial"
    summary = AnswerTrustSummary(
        overall_outcome=overall,
        semantic_passes=0,
        verifier_logical_calls=0,
        verifier_http_attempts=0,
        verifier_state="not_needed",
        input_hash=input_hash,
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
        answer_blocks=tuple(surviving),
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
        and str(value.get("status") or "") == "confirmed"
    )
    contributions = tuple(decision_projection.get("contributions") or ())
    reasons: list[str] = []
    invalid_citation_ids: set[str] = set()
    for citation in citations:
        try:
            validate_citation(citation.citation_id)
        except Exception:
            reasons.append("soft_review_source_changed")
            invalid_citation_ids.add(citation.citation_id)
    if open_aspects:
        reasons.append("soft_review_open_aspects_remain")
    if blocking_conflicts:
        reasons.append("soft_review_blocking_conflict")
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
    reviewed_limitations = list(dict.fromkeys(reviewed_limitations))
    reviewed_blocks = tuple(
        block
        for block in answer_blocks
        if not any(value in invalid_citation_ids for value in block.citation_ids)
    )
    used_citation_ids = {
        citation_id
        for block in reviewed_blocks
        for citation_id in block.citation_ids
    }
    reviewed_citations = tuple(
        citation for citation in citations if citation.citation_id in used_citation_ids
    )
    removed_blocks = len(answer_blocks) - len(reviewed_blocks)
    changed = (
        reviewed_limitations != list(limitations)
        or removed_blocks > 0
    )
    if not reviewed_blocks:
        reviewed_status: AnswerStatus = "insufficient"
        execution_outcome: AnswerExecutionOutcome = "evidence_unavailable"
        termination_reason: TerminationReason | None = "evidence_unavailable"
    else:
        reviewed_status = (
            "partial" if removed_blocks or (changed and status == "complete") else status
        )
        execution_outcome = "answer_generated"
        termination_reason = None
    version = 2 if changed else 1
    reviewed_hash = sha256_identity(
        {
            "answer_blocks": [value.model_dump(mode="json") for value in reviewed_blocks],
            "citations": [value.model_dump(mode="json") for value in reviewed_citations],
            "limitations": reviewed_limitations,
            "status": reviewed_status,
            "answer_version": version,
        }
    )
    return SoftReviewResult(
        status=reviewed_status,
        execution_outcome=execution_outcome,
        termination_reason=termination_reason,
        answer_blocks=reviewed_blocks,
        citations=reviewed_citations,
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
                    "回答中的实质性陈述未通过展示前可信门，已全部隐藏",
                ]
            )
        ),
        summary=summary,
    )


def _emit(sink: EventSink | None, event_type: str, payload: Mapping[str, object]) -> None:
    if sink is not None:
        sink(event_type, payload)
