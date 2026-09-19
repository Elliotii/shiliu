from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from shiliu.ask.adaptive import (
    create_current_evidence_decision,
    envelope_for_completed_run,
    revalidate_inherited_evidence,
)
from shiliu.ask.contracts import AnswerBlock, EvidenceSegment, TranscriptEvidenceSpan
from shiliu.ask.persistence import AskRunStore, initialize_ask_schema
from shiliu.ask.trust import apply_answer_trust
from shiliu.db import Database
from shiliu.evidence.continuation import (
    ContinuationContractError,
    ContinuationFailureState,
    ContinuationTarget,
    InheritedEvidenceReference,
    parse_continuation_envelope,
    serialize_continuation_envelope,
    validate_continuation_consumption,
)
from shiliu.evidence.decision import (
    AuthorizationStatus,
    CANONICAL_SEGMENT_ID_LIMIT,
    ContributionKind,
    EVIDENCE_SEGMENT_CARDINALITY_EXCEEDED_REASON,
    EvidenceAuthorityReference,
    ReferenceScopeStatus,
    SourceVersionStatus,
    decision_from_persistence_projection,
    decision_to_persistence_projection,
    parse_evidence_decision,
    serialize_evidence_decision,
)
from shiliu.retrieval.product_search import ProductSearchFilterRequest


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def _segment_ids(count: int) -> tuple[str, ...]:
    return tuple(f"segment-{index:03d}" for index in range(count))


def _span(name: str, count: int) -> TranscriptEvidenceSpan:
    ids = _segment_ids(count)
    segment = EvidenceSegment(
        segment_id=ids[0],
        original_ordinal=0,
        run_local_ordinal=0,
        start_time=0,
        end_time=2,
        source_text=f"{name} exact evidence",
    )
    return TranscriptEvidenceSpan(
        citation_id=f"citation-{name}",
        video_id=1,
        bvid="BV1",
        title="title",
        source_type="human",
        source_language="en",
        source_artifact_id=f"artifact-{name}",
        source_version=f"version-{name}",
        source_version_authority="raw_subtitle",
        timeline_run_id=f"timeline-{name}",
        segment_ids=ids,
        segment_ordinals=tuple(range(count)),
        start_time=0,
        end_time=2,
        quote_text=segment.source_text,
        jump_url="https://example.test?t=0",
        parent_chunk_ids=(f"chunk-{name}",),
        retrieval_provenance=(),
        segments=(segment,),
    )


def _authority(name: str, count: int) -> EvidenceAuthorityReference:
    return EvidenceAuthorityReference(
        reference_id=f"citation-{name}",
        source_artifact_id=f"artifact-{name}",
        source_version=f"version-{name}",
        timeline_run_id=f"timeline-{name}",
        segment_ids=_segment_ids(count),
        source_version_status=SourceVersionStatus.CURRENT,
        scope_status=ReferenceScopeStatus.IN_SCOPE,
        authorization_status=AuthorizationStatus.AUTHORIZED,
    )


def _inherited(name: str, count: int) -> InheritedEvidenceReference:
    return InheritedEvidenceReference(
        reference_id=f"citation-{name}",
        citation_identity_version="v4-citation-identity-v1",
        source_artifact_id=f"artifact-{name}",
        source_version=f"version-{name}",
        timeline_run_id=f"timeline-{name}",
        segment_ids=_segment_ids(count),
        citation_lineage_hash="sha256:" + "1" * 64,
    )


@pytest.mark.parametrize("count", [128, 129, 163, 167, 256])
def test_canonical_models_preserve_every_accepted_segment_id_in_order(count: int) -> None:
    assert CANONICAL_SEGMENT_ID_LIMIT == 256
    expected = _segment_ids(count)

    authority = _authority(str(count), count)
    inherited = _inherited(str(count), count)

    assert authority.segment_ids == expected
    assert inherited.segment_ids == expected
    assert authority.model_dump(mode="json")["segment_ids"] == list(expected)
    assert inherited.model_dump(mode="json")["segment_ids"] == list(expected)


def test_257_is_rejected_by_strict_models_but_product_adapters_degrade_safely() -> None:
    oversized = _span("oversized", 257)
    with pytest.raises(ValidationError):
        _authority("oversized", 257)
    with pytest.raises(ValidationError):
        _inherited("oversized", 257)

    decision = create_current_evidence_decision(
        question="question",
        filters=ProductSearchFilterRequest(),
        spans=(oversized,),
        recorded_at=NOW,
    )
    assert decision.covered_aspects == ()
    assert decision.open_aspects == ("question",)
    assert [(value.kind, value.reference_id) for value in decision.contributions] == [
        (ContributionKind.DROPPED, oversized.citation_id)
    ]

    envelope = envelope_for_completed_run(
        run_id="run-oversized",
        decision=decision,
        target=ContinuationTarget.DEEP,
        question="question",
        filters={},
        citations=(oversized.as_citation().model_dump(mode="json"),),
        search_executions=(),
    )
    assert envelope.inherited_evidence == ()
    assert envelope.failure_state == ContinuationFailureState.EVIDENCE_UNAVAILABLE
    assert any(
        value.kind == ContributionKind.DROPPED
        and value.reference_id == oversized.citation_id
        for value in envelope.contributions
    )


def test_mixed_eligible_and_oversized_blocks_keep_only_complete_canonical_support() -> None:
    eligible = _span("eligible", 256)
    oversized = _span("oversized", 257)
    result = apply_answer_trust(
        run_id="run-mixed",
        answer_blocks=(
            AnswerBlock(text=eligible.quote_text, citation_ids=[eligible.citation_id]),
            AnswerBlock(text=oversized.quote_text, citation_ids=[oversized.citation_id]),
        ),
        citations=(eligible.as_citation(), oversized.as_citation()),
        spans=(eligible, oversized),
        status="complete",
        limitations=(),
        termination_reason="answer_ready",
        validate_current=lambda _span: None,
    )

    assert result.status == "partial"
    assert result.execution_outcome == "answer_generated"
    assert result.answer_blocks == (
        AnswerBlock(text=eligible.quote_text, citation_ids=[eligible.citation_id]),
    )
    assert tuple(value.citation_id for value in result.citations) == (
        eligible.citation_id,
    )
    assert EVIDENCE_SEGMENT_CARDINALITY_EXCEEDED_REASON in result.summary.reason_codes
    assert result.summary.verifier_logical_calls == 0
    assert result.summary.verifier_http_attempts == 0
    assert any("256" in value for value in result.limitations)


def test_all_oversized_blocks_return_truthful_evidence_unavailable() -> None:
    oversized = _span("oversized", 257)
    result = apply_answer_trust(
        run_id="run-all-oversized",
        answer_blocks=(
            AnswerBlock(text=oversized.quote_text, citation_ids=[oversized.citation_id]),
        ),
        citations=(oversized.as_citation(),),
        spans=(oversized,),
        status="complete",
        limitations=(),
        termination_reason="answer_ready",
        validate_current=lambda _span: None,
    )

    assert result.status == "insufficient"
    assert result.execution_outcome == "evidence_unavailable"
    assert result.termination_reason == "evidence_unavailable"
    assert result.answer_blocks == result.citations == ()
    assert result.summary.verifier_logical_calls == 0
    assert result.summary.verifier_http_attempts == 0
    assert EVIDENCE_SEGMENT_CARDINALITY_EXCEEDED_REASON in result.summary.reason_codes


def test_256_decision_canonical_hash_and_existing_trace_persistence_round_trip(
    tmp_path: Path,
) -> None:
    span = _span("max", 256)
    decision = create_current_evidence_decision(
        question="question",
        filters=ProductSearchFilterRequest(),
        spans=(span,),
        recorded_at=NOW,
    )
    serialized = serialize_evidence_decision(decision)
    repeated = create_current_evidence_decision(
        question="question",
        filters=ProductSearchFilterRequest(),
        spans=(span,),
        recorded_at=NOW,
    )
    assert repeated == decision
    assert serialize_evidence_decision(repeated) == serialized
    assert parse_evidence_decision(serialized) == decision
    assert decision.coverage[0].authority_references[0].segment_ids == span.segment_ids

    projection = decision_to_persistence_projection(decision)
    db = Database(tmp_path / "rc4.sqlite3")
    with db.connect() as connection:
        initialize_ask_schema(connection)
    store = AskRunStore(db)
    store.start(run_id="run-rc4", query="question", mode="fast", filters={})
    store.complete(
        run_id="run-rc4",
        trace={"evidence_decision": projection},
        answer_status="insufficient",
        termination_reason="no_new_evidence",
        query_analysis={},
        rewrites=(),
        search_executions=(),
        final_evidence=(),
        citations=(),
        answer_blocks=(),
        limitations=("round trip",),
        usage_summary={},
    )
    restored = store.get_run("run-rc4")
    assert restored is not None
    assert decision_from_persistence_projection(
        restored["trace"]["evidence_decision"]
    ) == decision


def test_256_continuation_round_trip_revalidation_and_lineage_tamper_fail_closed() -> None:
    span = _span("max", 256)
    filters = ProductSearchFilterRequest()
    scope = filters.model_dump(mode="json", exclude_none=True)
    decision = create_current_evidence_decision(
        question="question",
        filters=filters,
        spans=(span,),
        recorded_at=NOW,
    )
    envelope = envelope_for_completed_run(
        run_id="run-max",
        decision=decision,
        target=ContinuationTarget.DEEP,
        question="question",
        filters=scope,
        citations=(span.as_citation().model_dump(mode="json"),),
        search_executions=(),
    )
    restored = parse_continuation_envelope(serialize_continuation_envelope(envelope))
    assert restored == envelope
    assert restored.inherited_evidence[0].segment_ids == span.segment_ids
    assert validate_continuation_consumption(
        decision,
        restored,
        current_question="question",
        current_scope=scope,
        target=ContinuationTarget.DEEP,
    ) == restored

    class _RunStore:
        @staticmethod
        def get_run(_run_id: str):
            return {
                "lifecycle_status": "completed",
                "citations": [span.as_citation().model_dump(mode="json")],
                "search_executions": [],
                "query": "question",
            }

    class _Materializer:
        @staticmethod
        def reconstruct_citation(citation, **_kwargs):
            assert tuple(citation.segment_ids) == span.segment_ids
            return span

    revalidated = revalidate_inherited_evidence(
        run_store=_RunStore(),  # type: ignore[arg-type]
        materializer=_Materializer(),  # type: ignore[arg-type]
        decision=decision,
        envelope=restored,
    )
    assert revalidated.spans == (span,)
    assert revalidated.dropped_reference_ids == ()
    assert revalidated.failure_state == ContinuationFailureState.NONE
    assert revalidated.decision.coverage[0].authority_references[0].segment_ids == (
        span.segment_ids
    )

    tampered = json.loads(serialize_continuation_envelope(envelope))
    tampered["inherited_evidence"][0]["segment_ids"][0] = "segment-tampered"
    with pytest.raises(ContinuationContractError) as caught:
        parse_continuation_envelope(tampered)
    assert caught.value.code == "continuation_integrity_failed"


def test_currentness_failure_still_hides_accepted_cardinality_support() -> None:
    span = _span("stale", 167)

    def stale(_span: TranscriptEvidenceSpan) -> None:
        raise ValueError("source version changed")

    result = apply_answer_trust(
        run_id="run-stale",
        answer_blocks=(
            AnswerBlock(text=span.quote_text, citation_ids=[span.citation_id]),
        ),
        citations=(span.as_citation(),),
        spans=(span,),
        status="complete",
        limitations=(),
        termination_reason="answer_ready",
        validate_current=stale,
    )
    assert result.status == "insufficient"
    assert result.answer_blocks == result.citations == ()
    assert result.summary.verifier_logical_calls == 0
    assert "evidence_source_unavailable" in result.summary.reason_codes
