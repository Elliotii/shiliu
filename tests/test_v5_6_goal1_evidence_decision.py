from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from shiliu.ask.persistence import AskRunStore, initialize_ask_schema
from shiliu.db import Database
from shiliu.evidence.claim_support import (
    MAX_MATERIAL_CLAIMS,
    BoundedClaimSupportInput,
    ClaimSupportOutcome,
    ClaimSupportReasonCode,
    MaterialClaim,
    SemanticSupportObservation,
    SemanticSupportVerdict,
    evaluate_bounded_claim_support,
)
from shiliu.evidence.decision import (
    AuthorizationStatus,
    ConflictObservation,
    ConflictStatus,
    ContributionKind,
    CorpusNewMaterialCheck,
    CorpusNewMaterialStatus,
    CoverageStatus,
    DecisionReasonCode,
    EvidenceAuthorityReference,
    EvidenceContribution,
    EvidenceDecisionAction,
    EvidenceDecisionContractError,
    EvidenceDecisionInput,
    EvidenceRequirement,
    FactRevisionAuthorityReference,
    LibraryFreshness,
    LibraryFreshnessStatus,
    ReferenceScopeStatus,
    RequirementOrigin,
    ScopeAssessment,
    ScopeMatchStatus,
    SemanticAdvice,
    SemanticAdviceKind,
    SourceVersionStatus,
    AspectCoverage,
    create_evidence_decision,
    decision_from_persistence_projection,
    decision_to_persistence_projection,
    parse_evidence_decision,
    resolve_requirements,
    scope_hash,
    serialize_evidence_decision,
    sha256_identity,
)


NOW = datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc)
PREVIOUS = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)


def _requirement(
    aspect_id: str = "pricing",
    *,
    origin: RequirementOrigin = RequirementOrigin.EXPLICIT_USER,
) -> EvidenceRequirement:
    return EvidenceRequirement(
        aspect_id=aspect_id,
        description=f"Cover {aspect_id}",
        origin=origin,
        precedence=3,
    )


def _evidence_reference(
    reference_id: str = "evidence-1",
    *,
    source_version_status: SourceVersionStatus = SourceVersionStatus.CURRENT,
    scope_status: ReferenceScopeStatus = ReferenceScopeStatus.IN_SCOPE,
    authorization_status: AuthorizationStatus = AuthorizationStatus.AUTHORIZED,
) -> EvidenceAuthorityReference:
    return EvidenceAuthorityReference(
        reference_id=reference_id,
        source_artifact_id="source-artifact-1",
        source_version="source-version-1",
        timeline_run_id="timeline-1",
        segment_ids=("segment-1",),
        source_version_status=source_version_status,
        scope_status=scope_status,
        authorization_status=authorization_status,
    )


def _freshness(
    status: CorpusNewMaterialStatus = CorpusNewMaterialStatus.NO_RELEVANT_NEW_MATERIAL,
) -> LibraryFreshness:
    mapped = {
        CorpusNewMaterialStatus.NO_RELEVANT_NEW_MATERIAL: LibraryFreshnessStatus.FRESH,
        CorpusNewMaterialStatus.RELEVANT_NEW_MATERIAL: LibraryFreshnessStatus.NEW_MATERIAL,
        CorpusNewMaterialStatus.NOT_CHECKED: LibraryFreshnessStatus.UNKNOWN,
        CorpusNewMaterialStatus.CHECK_FAILED: LibraryFreshnessStatus.CHECK_FAILED,
    }[status]
    return LibraryFreshness(
        status=mapped,
        corpus_new_material_check=CorpusNewMaterialCheck(
            status=status,
            recorded_check_time=NOW,
            previous_check_time=PREVIOUS,
            bounded_query_hash=scope_hash({"query": "pricing", "limit": 8}),
            candidate_reference_ids=("artifact-revision-1",),
            relevant_material_reference_ids=("evidence-new",)
            if status == CorpusNewMaterialStatus.RELEVANT_NEW_MATERIAL
            else (),
        ),
    )


def _input(
    *,
    requirement: EvidenceRequirement | None = None,
    scope_status: ScopeMatchStatus = ScopeMatchStatus.EXACT,
    coverage_status: CoverageStatus = CoverageStatus.COVERED,
    reference: EvidenceAuthorityReference | FactRevisionAuthorityReference | None = None,
    freshness: LibraryFreshness | None = None,
    conflicts: tuple[ConflictObservation, ...] = (),
    contributions: tuple[EvidenceContribution, ...] | None = None,
    semantic_advice: tuple[SemanticAdvice, ...] = (),
    parent_decision_id: str | None = None,
) -> EvidenceDecisionInput:
    requirement = requirement or _requirement()
    reference = reference or _evidence_reference()
    if contributions is None:
        contributions = (
            EvidenceContribution(
                kind=ContributionKind.REUSED,
                reference_id=reference.reference_id,
                aspect_ids=(requirement.aspect_id,),
            ),
        )
    return EvidenceDecisionInput(
        normalized_question="What is the current pricing?",
        parent_decision_id=parent_decision_id,
        requirements=(requirement,),
        scope=ScopeAssessment(
            status=scope_status,
            requested_scope_hash=scope_hash({"time": "current", "view": "all"}),
            candidate_scope_hash=scope_hash({"time": "current", "view": "all"}),
            explanation=f"scope is {scope_status.value}",
            compared_reference_ids=(reference.reference_id,),
        ),
        coverage=(
            AspectCoverage(
                aspect_id=requirement.aspect_id,
                status=coverage_status,
                authority_references=(reference,)
                if coverage_status != CoverageStatus.UNKNOWN
                else (),
                explanation=f"coverage is {coverage_status.value}",
            ),
        ),
        library_freshness=freshness or _freshness(),
        conflicts=conflicts,
        contributions=contributions,
        semantic_advice=semantic_advice,
    )


def test_explicit_requirements_win_and_inference_is_bounded_and_traceable() -> None:
    resolved = resolve_requirements(
        (
            _requirement("pricing", origin=RequirementOrigin.BOUNDED_INFERENCE),
            _requirement("pricing", origin=RequirementOrigin.EXPLICIT_USER),
            _requirement("limits", origin=RequirementOrigin.BOUNDED_INFERENCE),
        )
    )
    assert [item.aspect_id for item in resolved] == ["pricing", "limits"]
    assert resolved[0].origin == RequirementOrigin.EXPLICIT_USER
    assert resolved[0].precedence == 0
    assert resolved[1].origin == RequirementOrigin.BOUNDED_INFERENCE
    assert resolved[1].precedence == 2

    too_many = tuple(
        _requirement(f"inferred-{index}", origin=RequirementOrigin.BOUNDED_INFERENCE)
        for index in range(9)
    )
    with pytest.raises(EvidenceDecisionContractError) as captured:
        resolve_requirements(too_many)
    assert captured.value.code == "inferred_requirements_unbounded"

    unknown = _requirement("unknown", origin=RequirementOrigin.UNKNOWN)
    decision = create_evidence_decision(
        _input(requirement=unknown, coverage_status=CoverageStatus.UNKNOWN),
        recorded_at=NOW,
    )
    assert decision.action == EvidenceDecisionAction.CLARIFY
    assert DecisionReasonCode.REQUIREMENT_UNKNOWN in decision.reason_codes


@pytest.mark.parametrize(
    ("status", "expected_action", "expected_reason"),
    (
        (
            ScopeMatchStatus.EXACT,
            EvidenceDecisionAction.DIRECT_REUSE,
            DecisionReasonCode.SCOPE_EXACT,
        ),
        (
            ScopeMatchStatus.COMPATIBLE,
            EvidenceDecisionAction.TARGETED_REFRESH,
            DecisionReasonCode.SCOPE_COMPATIBLE,
        ),
        (
            ScopeMatchStatus.MISMATCH,
            EvidenceDecisionAction.DEEP_RESEARCH,
            DecisionReasonCode.SCOPE_MISMATCH,
        ),
        (
            ScopeMatchStatus.UNKNOWN,
            EvidenceDecisionAction.CLARIFY,
            DecisionReasonCode.SCOPE_UNKNOWN,
        ),
    ),
)
def test_scope_states_are_explainable_and_fail_closed(
    status: ScopeMatchStatus,
    expected_action: EvidenceDecisionAction,
    expected_reason: DecisionReasonCode,
) -> None:
    decision = create_evidence_decision(_input(scope_status=status), recorded_at=NOW)
    assert decision.action == expected_action
    assert expected_reason in decision.reason_codes
    assert decision.scope.explanation == f"scope is {status.value}"


def test_coverage_references_existing_evidence_or_fact_revision_without_copying_facts() -> None:
    evidence = _evidence_reference()
    evidence_decision = create_evidence_decision(_input(reference=evidence), recorded_at=NOW)
    assert evidence_decision.coverage[0].authority_references[0].kind == "evidence"
    assert not hasattr(evidence_decision.coverage[0].authority_references[0], "quote_text")

    fact = FactRevisionAuthorityReference(
        reference_id="fact-revision-7",
        evidence_reference_ids=("evidence-use-9",),
        source_version_status=SourceVersionStatus.CURRENT,
        scope_status=ReferenceScopeStatus.IN_SCOPE,
        authorization_status=AuthorizationStatus.AUTHORIZED,
    )
    fact_decision = create_evidence_decision(_input(reference=fact), recorded_at=NOW)
    assert fact_decision.coverage[0].authority_references[0].kind == "fact_revision"
    assert fact_decision.action == EvidenceDecisionAction.DIRECT_REUSE


def test_incomplete_coverage_cannot_direct_reuse() -> None:
    decision = create_evidence_decision(
        _input(coverage_status=CoverageStatus.PARTIAL), recorded_at=NOW
    )
    assert decision.action == EvidenceDecisionAction.TARGETED_REFRESH
    assert decision.open_aspects == ("pricing",)
    assert DecisionReasonCode.COVERAGE_INCOMPLETE in decision.reason_codes


def test_freshness_is_a_recorded_local_corpus_check_not_file_existence_or_internet_claim() -> None:
    decision = create_evidence_decision(_input(), recorded_at=NOW)
    check = decision.library_freshness.corpus_new_material_check
    assert check.corpus_scope == "local_shiliu_corpus"
    assert check.recorded_check_time == NOW
    assert check.internet_freshness_claimed is False
    assert decision.action == EvidenceDecisionAction.DIRECT_REUSE

    with pytest.raises(ValidationError):
        CorpusNewMaterialCheck.model_validate(
            {
                **check.model_dump(mode="json"),
                "file_exists": True,
            }
        )

    new_material = create_evidence_decision(
        _input(freshness=_freshness(CorpusNewMaterialStatus.RELEVANT_NEW_MATERIAL)),
        recorded_at=NOW,
    )
    assert new_material.action == EvidenceDecisionAction.TARGETED_REFRESH
    assert DecisionReasonCode.LOCAL_CORPUS_NEW_MATERIAL in new_material.reason_codes


@pytest.mark.parametrize("seconds_before_decision", (1, 0))
def test_corpus_check_time_may_precede_or_equal_decision_time(
    seconds_before_decision: int,
) -> None:
    freshness = _freshness()
    check = freshness.corpus_new_material_check.model_copy(
        update={"recorded_check_time": NOW - timedelta(seconds=seconds_before_decision)}
    )
    bounded_freshness = LibraryFreshness(
        status=freshness.status,
        corpus_new_material_check=check,
    )
    decision = create_evidence_decision(
        _input(freshness=bounded_freshness), recorded_at=NOW
    )
    assert decision.library_freshness.corpus_new_material_check.recorded_check_time <= NOW


def test_future_corpus_check_fails_closed_with_stable_contract_error() -> None:
    freshness = _freshness()
    check = freshness.corpus_new_material_check.model_copy(
        update={"recorded_check_time": NOW + timedelta(microseconds=1)}
    )
    future_freshness = LibraryFreshness(
        status=freshness.status,
        corpus_new_material_check=check,
    )
    with pytest.raises(EvidenceDecisionContractError) as captured:
        create_evidence_decision(_input(freshness=future_freshness), recorded_at=NOW)
    assert captured.value.code == "corpus_check_after_decision"


@pytest.mark.parametrize(
    ("source_status", "reason"),
    (
        (SourceVersionStatus.STALE, DecisionReasonCode.SOURCE_VERSION_STALE),
        (SourceVersionStatus.INVALID, DecisionReasonCode.SOURCE_VERSION_INVALID),
        (SourceVersionStatus.UNAVAILABLE, DecisionReasonCode.SOURCE_VERSION_UNAVAILABLE),
    ),
)
def test_stale_invalid_or_unavailable_source_versions_fail_closed(
    source_status: SourceVersionStatus, reason: DecisionReasonCode
) -> None:
    decision = create_evidence_decision(
        _input(reference=_evidence_reference(source_version_status=source_status)),
        recorded_at=NOW,
    )
    assert decision.action == EvidenceDecisionAction.DEEP_RESEARCH
    assert reason in decision.reason_codes


def test_traceable_conflict_blocks_unsafe_reuse() -> None:
    conflict = ConflictObservation(
        conflict_id="conflict-1",
        status=ConflictStatus.POTENTIAL,
        left_reference_ids=("evidence-old",),
        right_reference_ids=("evidence-new",),
        observed_at=NOW,
        explanation="Two traceable Evidence references disagree.",
    )
    decision = create_evidence_decision(
        _input(conflicts=(conflict,)), recorded_at=NOW
    )
    assert decision.action == EvidenceDecisionAction.DEEP_RESEARCH
    assert DecisionReasonCode.BLOCKING_CONFLICT in decision.reason_codes
    assert decision.conflicts[0].left_reference_ids == ("evidence-old",)


@pytest.mark.parametrize("status", tuple(ConflictStatus))
@pytest.mark.parametrize("seconds_before_decision", (1, 0))
def test_conflict_observation_time_may_precede_or_equal_decision_time(
    status: ConflictStatus,
    seconds_before_decision: int,
) -> None:
    conflict = ConflictObservation(
        conflict_id=f"conflict-{status.value}-{seconds_before_decision}",
        status=status,
        left_reference_ids=("evidence-old",),
        right_reference_ids=("evidence-new",),
        observed_at=NOW - timedelta(seconds=seconds_before_decision),
        explanation="Bounded decision-time causality test.",
    )
    decision = create_evidence_decision(_input(conflicts=(conflict,)), recorded_at=NOW)
    assert decision.conflicts[0].observed_at <= decision.recorded_at


@pytest.mark.parametrize("status", tuple(ConflictStatus))
def test_future_conflict_observation_fails_closed_for_every_status(
    status: ConflictStatus,
) -> None:
    conflict = ConflictObservation(
        conflict_id=f"future-conflict-{status.value}",
        status=status,
        left_reference_ids=("evidence-old",),
        right_reference_ids=("evidence-new",),
        observed_at=NOW + timedelta(microseconds=1),
        explanation="Future observations cannot cause an earlier decision.",
    )
    with pytest.raises(EvidenceDecisionContractError) as captured:
        create_evidence_decision(_input(conflicts=(conflict,)), recorded_at=NOW)
    assert captured.value.code == "conflict_observation_after_decision"


def test_action_reason_and_serialization_never_grant_authority() -> None:
    decision = create_evidence_decision(_input(), recorded_at=NOW)
    assert decision.reason_codes
    assert decision.provider_authority_granted is False
    assert decision.fact_authority_granted is False
    assert decision.citation_authority_granted is False
    assert decision.raw_evidence_authority_granted is False
    serialized = serialize_evidence_decision(decision)
    assert '"provider_authority_granted":false' in serialized
    assert set(item.value for item in EvidenceDecisionAction) == {
        "answer_fresh",
        "direct_reuse",
        "targeted_refresh",
        "deep_research",
        "clarify",
        "partial_answer",
        "abstain",
    }
    assert set(item.value for item in ContributionKind) == {
        "old",
        "reused",
        "new",
        "dropped",
    }


def test_semantic_advice_changes_input_identity_but_not_authority_or_action() -> None:
    baseline = create_evidence_decision(_input(), recorded_at=NOW)
    advised = create_evidence_decision(
        _input(
            semantic_advice=(
                SemanticAdvice(
                    advice_id="advice-1",
                    kind=SemanticAdviceKind.TIME_SENSITIVITY,
                    proposed_value="Consider another bounded local check.",
                    supporting_reference_ids=("evidence-1",),
                ),
            )
        ),
        recorded_at=NOW,
    )
    assert advised.authority_hash == baseline.authority_hash
    assert advised.input_hash != baseline.input_hash
    assert advised.decision_id != baseline.decision_id
    assert advised.action == baseline.action
    assert DecisionReasonCode.SEMANTIC_ADVICE_NON_AUTHORITATIVE in advised.reason_codes


def test_identity_hash_parent_and_canonical_serializer_are_stable() -> None:
    first = create_evidence_decision(_input(), recorded_at=NOW)
    repeated = create_evidence_decision(_input(), recorded_at=NOW)
    assert repeated == first
    assert serialize_evidence_decision(repeated) == serialize_evidence_decision(first)
    assert parse_evidence_decision(serialize_evidence_decision(first)) == first

    child = create_evidence_decision(
        _input(parent_decision_id=first.decision_id), recorded_at=NOW
    )
    assert child.parent_decision_id == first.decision_id
    assert child.decision_id != first.decision_id
    assert re.fullmatch(r"evd_[0-9a-f]{32}", child.decision_id)


def test_existing_ask_trace_json_round_trip_requires_no_schema_migration(
    tmp_path: Path,
) -> None:
    decision = create_evidence_decision(_input(), recorded_at=NOW)
    projection = decision_to_persistence_projection(decision)
    db = Database(tmp_path / "goal1.sqlite3")
    with db.connect() as connection:
        initialize_ask_schema(connection)
    store = AskRunStore(db)
    store.start(run_id="run-goal1", query="pricing", mode="fast", filters={})
    store.complete(
        run_id="run-goal1",
        trace={"evidence_decision": projection},
        answer_status="insufficient",
        termination_reason="no_new_evidence",
        query_analysis={},
        rewrites=(),
        search_executions=(),
        final_evidence=(),
        citations=(),
        answer_blocks=(),
        limitations=("contract round-trip only",),
        usage_summary={},
    )
    restored = store.get_run("run-goal1")
    assert restored is not None
    parsed = decision_from_persistence_projection(
        restored["trace"]["evidence_decision"]
    )
    assert parsed == decision
    with db.connect() as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(ask_runs)").fetchall()
        }
    assert "trace_json" in columns
    assert "evidence_decision_json" not in columns


def test_compatibility_unknown_version_extra_field_and_tamper_fail_closed() -> None:
    decision = create_evidence_decision(_input(), recorded_at=NOW)
    payload = json.loads(serialize_evidence_decision(decision))

    payload["schema_version"] = "v5.6-evidence-decision-v999"
    with pytest.raises(EvidenceDecisionContractError) as unknown:
        parse_evidence_decision(json.dumps(payload))
    assert unknown.value.code == "unknown_schema_version"

    payload = json.loads(serialize_evidence_decision(decision))
    payload["future_unreviewed_field"] = True
    with pytest.raises(EvidenceDecisionContractError) as forward:
        parse_evidence_decision(json.dumps(payload))
    assert forward.value.code == "invalid_contract"

    payload = json.loads(serialize_evidence_decision(decision))
    payload["action"] = EvidenceDecisionAction.ABSTAIN.value
    with pytest.raises(EvidenceDecisionContractError) as tampered:
        parse_evidence_decision(json.dumps(payload))
    assert tampered.value.code == "decision_integrity_failed"


def test_no_duplicate_mode_specific_evidence_decision_contract_exists() -> None:
    source_root = Path(__file__).parents[1] / "src" / "shiliu"
    owners = []
    for path in source_root.rglob("*.py"):
        if re.search(r"^class EvidenceDecision\b", path.read_text(), re.MULTILINE):
            owners.append(path.relative_to(source_root).as_posix())
    assert owners == ["evidence/decision.py"]


def _claim(
    claim_id: str,
    reference_id: str = "evidence-1",
) -> MaterialClaim:
    return MaterialClaim(
        claim_id=claim_id,
        answer_block_id=f"block-{claim_id}",
        claim_text_hash=sha256_identity({"claim": claim_id}),
        authority_reference_ids=(reference_id,),
    )


def _observation(
    claim_id: str,
    verdict: SemanticSupportVerdict,
    reference_id: str = "evidence-1",
) -> SemanticSupportObservation:
    return SemanticSupportObservation(
        observation_id=f"observation-{claim_id}",
        claim_id=claim_id,
        verdict=verdict,
        authority_reference_ids=(reference_id,),
        verifier_reference="precomputed-semantic-observation",
    )


def test_bounded_material_claim_support_expresses_all_required_outcomes() -> None:
    value = BoundedClaimSupportInput(
        material_claims=(_claim("allow"), _claim("downgrade"), _claim("remove")),
        authority_references=(_evidence_reference(),),
        semantic_observations=(
            _observation("allow", SemanticSupportVerdict.SUPPORTED),
            _observation("downgrade", SemanticSupportVerdict.PARTIAL),
            _observation("remove", SemanticSupportVerdict.UNSUPPORTED),
        ),
    )
    decision = evaluate_bounded_claim_support(value)
    outcomes = {item.claim_id: item.outcome for item in decision.dispositions}
    assert outcomes == {
        "allow": ClaimSupportOutcome.ALLOW,
        "downgrade": ClaimSupportOutcome.DOWNGRADE,
        "remove": ClaimSupportOutcome.REMOVE,
    }
    assert decision.overall_outcome == ClaimSupportOutcome.PARTIAL
    assert decision.execution.deterministic_evaluation_passes == 1
    assert decision.execution.verifier_calls == 0
    assert decision.execution.repair_attempts == 0
    assert decision.execution.unbounded_loop_possible is False
    assert decision.verifier_type is None
    assert decision.semantic_pass_count_policy is None
    assert decision.bounded_repair_policy is None
    assert decision.deterministic_only_claim_classes == ()

    insufficient = evaluate_bounded_claim_support(
        BoundedClaimSupportInput(
            material_claims=(_claim("remove"),),
            authority_references=(_evidence_reference(),),
            semantic_observations=(
                _observation("remove", SemanticSupportVerdict.UNSUPPORTED),
            ),
        )
    )
    assert insufficient.overall_outcome == ClaimSupportOutcome.INSUFFICIENT


@pytest.mark.parametrize(
    "bad_reference",
    (
        _evidence_reference(source_version_status=SourceVersionStatus.STALE),
        _evidence_reference(source_version_status=SourceVersionStatus.INVALID),
        _evidence_reference(source_version_status=SourceVersionStatus.UNAVAILABLE),
        _evidence_reference(source_version_status=SourceVersionStatus.UNKNOWN),
        _evidence_reference(scope_status=ReferenceScopeStatus.OUT_OF_SCOPE),
        _evidence_reference(scope_status=ReferenceScopeStatus.UNKNOWN),
        _evidence_reference(authorization_status=AuthorizationStatus.UNAUTHORIZED),
        _evidence_reference(authorization_status=AuthorizationStatus.UNKNOWN),
    ),
)
def test_semantic_support_cannot_legalize_deterministic_authority_failure(
    bad_reference: EvidenceAuthorityReference,
) -> None:
    decision = evaluate_bounded_claim_support(
        BoundedClaimSupportInput(
            material_claims=(_claim("claim"),),
            authority_references=(bad_reference,),
            semantic_observations=(
                _observation("claim", SemanticSupportVerdict.SUPPORTED),
            ),
        )
    )
    disposition = decision.dispositions[0]
    assert disposition.outcome == ClaimSupportOutcome.REMOVE
    assert decision.overall_outcome == ClaimSupportOutcome.INSUFFICIENT
    assert (
        ClaimSupportReasonCode.SEMANTIC_RESULT_CANNOT_OVERRIDE_AUTHORITY
        in disposition.reason_codes
    )


def test_supported_semantic_observation_requires_a_nonempty_evidence_binding() -> None:
    with pytest.raises(ValidationError):
        SemanticSupportObservation(
            observation_id="observation-empty-binding",
            claim_id="claim",
            verdict=SemanticSupportVerdict.SUPPORTED,
            authority_reference_ids=(),
            verifier_reference="precomputed-semantic-observation",
        )


@pytest.mark.parametrize("binding", ("unknown-evidence", "evidence-outside-claim"))
def test_semantic_binding_must_be_known_and_owned_by_the_claim(binding: str) -> None:
    references = (_evidence_reference(),)
    if binding == "evidence-outside-claim":
        references = (*references, _evidence_reference(binding))
    with pytest.raises(ValidationError):
        BoundedClaimSupportInput(
            material_claims=(_claim("claim"),),
            authority_references=references,
            semantic_observations=(
                _observation("claim", SemanticSupportVerdict.SUPPORTED, binding),
            ),
        )


def test_accepted_references_are_exactly_supported_eligible_bindings() -> None:
    claim = MaterialClaim(
        claim_id="claim",
        answer_block_id="block-claim",
        claim_text_hash=sha256_identity({"claim": "claim"}),
        authority_reference_ids=("evidence-1", "evidence-2"),
    )
    decision = evaluate_bounded_claim_support(
        BoundedClaimSupportInput(
            material_claims=(claim,),
            authority_references=(
                _evidence_reference("evidence-1"),
                _evidence_reference("evidence-2"),
            ),
            semantic_observations=(
                _observation(
                    "claim", SemanticSupportVerdict.SUPPORTED, "evidence-1"
                ),
            ),
        )
    )
    disposition = decision.dispositions[0]
    assert disposition.outcome == ClaimSupportOutcome.ALLOW
    assert disposition.accepted_reference_ids == ("evidence-1",)


def test_claim_support_input_is_bounded_and_material_only() -> None:
    claims = tuple(_claim(f"claim-{index}") for index in range(MAX_MATERIAL_CLAIMS + 1))
    with pytest.raises(ValidationError):
        BoundedClaimSupportInput(
            material_claims=claims,
            authority_references=(_evidence_reference(),),
        )
    with pytest.raises(ValidationError):
        MaterialClaim.model_validate(
            {
                **_claim("nonmaterial").model_dump(mode="json"),
                "materiality": "nonmaterial",
            }
        )

    with pytest.raises(ValidationError):
        AspectCoverage(
            aspect_id="pricing",
            status=CoverageStatus.COVERED,
            authority_references=(),
            explanation="unsupported declaration",
        )
