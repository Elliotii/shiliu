from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from shiliu.ask.adaptive import (
    decision_from_trace,
    envelope_for_completed_run,
    evidence_reference,
    revalidate_inherited_evidence,
)
from shiliu.ask.contracts import AskRequest
from shiliu.evidence.continuation import (
    MAX_REFRESH_ROUNDS,
    ContinuationBudgetState,
    ContinuationContractError,
    ContinuationFailureState,
    ContinuationStopReason,
    ContinuationTarget,
    ReceiptState,
    RefreshObservation,
    SearchExecutionReference,
    SideEffectState,
    create_continuation_envelope,
    parse_continuation_envelope,
    run_targeted_refresh,
    serialize_continuation_envelope,
)
from shiliu.evidence.decision import (
    AspectCoverage,
    AuthorizationStatus,
    ConflictObservation,
    ConflictStatus,
    ContributionKind,
    CorpusNewMaterialCheck,
    CorpusNewMaterialStatus,
    CoverageStatus,
    EvidenceAuthorityReference,
    EvidenceContribution,
    EvidenceDecisionAction,
    EvidenceDecisionInput,
    EvidenceRequirement,
    LibraryFreshness,
    LibraryFreshnessStatus,
    ReferenceScopeStatus,
    RequirementOrigin,
    ScopeAssessment,
    ScopeMatchStatus,
    SourceVersionStatus,
    create_evidence_decision,
    decision_from_persistence_projection,
    scope_hash,
    sha256_identity,
)
from shiliu.research.errors import ResearchValidationError
from shiliu.research.product_contracts import CreateProductResearchRequest
from shiliu.retrieval.product_search import ProductSearchFilterRequest


NOW = datetime(2026, 8, 18, 8, 0, tzinfo=timezone.utc)


def _reference(name: str, *, status: SourceVersionStatus = SourceVersionStatus.CURRENT):
    return EvidenceAuthorityReference(
        reference_id=name,
        source_artifact_id=f"artifact-{name}",
        source_version=f"version-{name}",
        timeline_run_id=f"timeline-{name}",
        segment_ids=(f"segment-{name}",),
        source_version_status=status,
        scope_status=ReferenceScopeStatus.IN_SCOPE,
        authorization_status=AuthorizationStatus.AUTHORIZED,
    )


def _decision(
    *,
    open_second: bool = True,
    conflict: bool = False,
    scope: ScopeMatchStatus = ScopeMatchStatus.EXACT,
):
    old = _reference("old")
    requirements = (
        EvidenceRequirement(
            aspect_id="old-aspect",
            description="旧方面",
            origin=RequirementOrigin.EXPLICIT_USER,
        ),
        EvidenceRequirement(
            aspect_id="new-aspect",
            description="新方面",
            origin=RequirementOrigin.EXPLICIT_USER,
        ),
    )
    conflicts = (
        ConflictObservation(
            conflict_id="conflict-1",
            status=ConflictStatus.POTENTIAL,
            left_reference_ids=("old",),
            right_reference_ids=("new",),
            observed_at=NOW,
            explanation="new and old evidence disagree",
        ),
    ) if conflict else ()
    return create_evidence_decision(
        EvidenceDecisionInput(
            normalized_question="原问题",
            requirements=requirements,
            scope=ScopeAssessment(
                status=scope,
                requested_scope_hash=scope_hash({"scope": "requested"}),
                candidate_scope_hash=(
                    scope_hash({"scope": "candidate"})
                    if scope != ScopeMatchStatus.UNKNOWN
                    else None
                ),
                explanation="fixture scope",
            ),
            coverage=(
                AspectCoverage(
                    aspect_id="old-aspect",
                    status=CoverageStatus.COVERED,
                    authority_references=(old,),
                    explanation="old Evidence covers this aspect",
                ),
                AspectCoverage(
                    aspect_id="new-aspect",
                    status=CoverageStatus.OPEN if open_second else CoverageStatus.COVERED,
                    authority_references=() if open_second else (old,),
                    explanation="open gap" if open_second else "complete",
                ),
            ),
            library_freshness=LibraryFreshness(
                status=LibraryFreshnessStatus.FRESH,
                corpus_new_material_check=CorpusNewMaterialCheck(
                    status=CorpusNewMaterialStatus.NO_RELEVANT_NEW_MATERIAL,
                    recorded_check_time=NOW,
                    bounded_query_hash=sha256_identity({"fixture": True}),
                ),
            ),
            conflicts=conflicts,
            contributions=(
                EvidenceContribution(
                    kind=ContributionKind.REUSED,
                    reference_id="old",
                    aspect_ids=("old-aspect",),
                ),
            ),
        ),
        recorded_at=NOW,
    )


def _envelope(decision, **updates):
    return create_continuation_envelope(
        parent_run_id="ask-parent",
        parent_decision=decision,
        target=updates.pop("target", ContinuationTarget.DEEP),
        original_question="原问题",
        normalized_scope={"folder_ids": [1]},
        **updates,
    )


def test_envelope_is_typed_versioned_integrity_bound_and_provider_false() -> None:
    decision = _decision()
    envelope = _envelope(decision)
    restored = parse_continuation_envelope(serialize_continuation_envelope(envelope))

    assert restored == envelope
    assert restored.schema_version == "v5.6-continuation-envelope-v1"
    assert restored.budget.max_refresh_rounds == MAX_REFRESH_ROUNDS == 3
    assert restored.provider_authority_granted is False
    assert restored.provider_authority_inherited is False

    payload = json.loads(serialize_continuation_envelope(envelope))
    payload["original_question"] = "篡改问题"
    with pytest.raises(ContinuationContractError) as caught:
        parse_continuation_envelope(payload)
    assert caught.value.code == "continuation_integrity_failed"


def test_targeted_refresh_queries_only_open_aspects_and_merges_old_new() -> None:
    decision = _decision()
    envelope = _envelope(decision)
    calls: list[tuple[str, str, int]] = []

    def refresh(aspect_id: str, query: str, round_number: int):
        calls.append((aspect_id, query, round_number))
        return RefreshObservation(
            aspect_id=aspect_id,
            authority_references=(_reference("new"),),
            search_executions=(
                SearchExecutionReference(
                    execution_id="search-new",
                    search_trace_id="trace-new",
                    query=query,
                    relation_kind="targeted_refresh",
                ),
            ),
        )

    result = run_targeted_refresh(decision, envelope, refresh, now=lambda: NOW)

    assert calls == [("new-aspect", "新方面", 1)]
    assert result.stop_reason == ContinuationStopReason.COVERAGE_COMPLETE
    assert result.final_decision.open_aspects == ()
    assert result.final_decision.action == EvidenceDecisionAction.DIRECT_REUSE
    assert {(value.kind.value, value.reference_id) for value in result.contributions} >= {
        ("reused", "old"),
        ("new", "new"),
    }
    assert result.rounds[0].new_reference_ids == ("new",)


def test_complete_current_coverage_direct_reuses_without_refresh() -> None:
    decision = _decision(open_second=False)
    assert decision.action == EvidenceDecisionAction.DIRECT_REUSE
    called = False

    def refresh(*_args):
        nonlocal called
        called = True
        raise AssertionError("complete direct reuse must not search")

    result = run_targeted_refresh(decision, _envelope(decision), refresh, now=lambda: NOW)
    assert called is False
    assert result.stop_reason == ContinuationStopReason.COVERAGE_COMPLETE


def test_no_new_evidence_conflict_deadline_cap_and_unknown_side_effect_stop() -> None:
    decision = _decision()
    no_new = run_targeted_refresh(
        decision,
        _envelope(decision),
        lambda aspect, _query, _round: RefreshObservation(
            aspect_id=aspect, aspect_complete=False
        ),
        now=lambda: NOW,
    )
    assert no_new.stop_reason == ContinuationStopReason.NO_NEW_ELIGIBLE_EVIDENCE
    assert no_new.failure_state == ContinuationFailureState.EVIDENCE_INSUFFICIENT

    conflict = run_targeted_refresh(
        decision,
        _envelope(decision),
        lambda aspect, _query, _round: RefreshObservation(
            aspect_id=aspect,
            authority_references=(_reference("new"),),
            conflicts=(
                ConflictObservation(
                    conflict_id="c",
                    status=ConflictStatus.CONFIRMED,
                    left_reference_ids=("old",),
                    right_reference_ids=("new",),
                    observed_at=NOW,
                    explanation="blocked",
                ),
            ),
        ),
        now=lambda: NOW,
    )
    assert conflict.stop_reason == ContinuationStopReason.CONFLICT_UNRESOLVED
    assert conflict.final_decision.action == EvidenceDecisionAction.DEEP_RESEARCH

    deadline = run_targeted_refresh(
        decision,
        _envelope(
            decision,
            budget=ContinuationBudgetState(deadline_at=NOW),
        ),
        lambda *_args: pytest.fail("deadline must stop before search"),
        now=lambda: NOW,
    )
    assert deadline.stop_reason == ContinuationStopReason.DEADLINE_EXHAUSTED

    capped = run_targeted_refresh(
        decision,
        _envelope(
            decision,
            budget=ContinuationBudgetState(refresh_rounds_completed=3),
        ),
        lambda *_args: pytest.fail("cap must stop before search"),
        now=lambda: NOW,
    )
    assert capped.stop_reason == ContinuationStopReason.MAX_REFRESH_ROUNDS

    unknown = run_targeted_refresh(
        decision,
        _envelope(
            decision,
            failure_state=ContinuationFailureState.UNKNOWN_SIDE_EFFECT,
            side_effect_state=SideEffectState.UNKNOWN,
        ),
        lambda *_args: pytest.fail("unknown side effect must never replay"),
        now=lambda: NOW,
    )
    assert unknown.stop_reason == ContinuationStopReason.UNKNOWN_SIDE_EFFECT
    assert unknown.failure_state == ContinuationFailureState.UNKNOWN_SIDE_EFFECT


def test_repeat_action_and_tool_budget_stop_without_hidden_recursion() -> None:
    decision = _decision()
    calls = 0

    def partial(aspect: str, _query: str, _round: int):
        nonlocal calls
        calls += 1
        return RefreshObservation(
            aspect_id=aspect,
            aspect_complete=False,
            authority_references=(_reference("partial"),),
        )

    repeated = run_targeted_refresh(
        decision, _envelope(decision), partial, now=lambda: NOW
    )
    assert calls == 1
    assert repeated.stop_reason == ContinuationStopReason.REPEATED_ACTION
    assert len(repeated.rounds) == 1

    exhausted = run_targeted_refresh(
        decision,
        _envelope(
            decision,
            budget=ContinuationBudgetState(remaining_tool_calls=0),
        ),
        lambda *_args: pytest.fail("zero tool budget must not execute"),
        now=lambda: NOW,
    )
    assert exhausted.stop_reason == ContinuationStopReason.TOOL_BUDGET_EXHAUSTED


@pytest.mark.parametrize(
    ("receipt,failure,side_effect,expected"),
    [
        (ReceiptState.IN_FLIGHT, ContinuationFailureState.NONE, SideEffectState.NONE, ContinuationStopReason.RECEIPT_PREVENTS_REPLAY),
        (ReceiptState.NOT_APPLICABLE, ContinuationFailureState.INTERRUPTED, SideEffectState.NONE, ContinuationStopReason.INTERRUPTED),
        (ReceiptState.NOT_APPLICABLE, ContinuationFailureState.UNKNOWN_SIDE_EFFECT, SideEffectState.UNKNOWN, ContinuationStopReason.UNKNOWN_SIDE_EFFECT),
    ],
)
def test_reload_preserves_receipt_interruption_and_unknown_without_replay(
    receipt, failure, side_effect, expected
) -> None:
    decision = _decision()
    envelope = _envelope(
        decision,
        receipt_state=receipt,
        failure_state=failure,
        side_effect_state=side_effect,
    )
    reloaded = parse_continuation_envelope(serialize_continuation_envelope(envelope))
    result = run_targeted_refresh(
        decision,
        reloaded,
        lambda *_args: pytest.fail("unsafe persisted state must not replay"),
        now=lambda: NOW,
    )
    assert result.stop_reason == expected
    assert result.failure_state == failure


def test_source_version_change_fails_inherited_evidence_closed(app_paths) -> None:
    from test_v4_fast_ask_api import _Provider, _application
    from shiliu.evidence.source import authoritative_raw_json_path

    provider = _Provider()
    core, raw_path = _application(app_paths, provider)
    response = core.ask_service.ask(AskRequest(query="MCP", mode="fast"))
    trace = core.ask_service.get_trace(response.run_id)
    assert trace is not None
    decision = decision_from_trace(trace)
    assert decision is not None
    envelope = parse_continuation_envelope(trace["continuation_envelope"])

    authority_path = authoritative_raw_json_path(raw_path)
    authority_path.write_text(
        authority_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    revalidated = revalidate_inherited_evidence(
        run_store=core.ask_service.run_store,
        materializer=core.ask_service.materializer,
        decision=decision,
        envelope=envelope,
    )
    assert revalidated.spans == ()
    assert revalidated.dropped_reference_ids
    assert revalidated.failure_state == ContinuationFailureState.EVIDENCE_UNAVAILABLE
    assert revalidated.decision.action == EvidenceDecisionAction.DEEP_RESEARCH


def test_fast_and_deep_consume_same_decision_with_parent_lineage(app_paths) -> None:
    from test_v4_fast_ask_api import _Provider, _application

    provider = _Provider()
    core, _ = _application(app_paths, provider)
    fast = core.ask_service.ask(AskRequest(query="MCP", mode="fast"))
    fast_trace = core.ask_service.get_trace(fast.run_id)
    assert fast_trace is not None
    decision = decision_from_trace(fast_trace)
    assert decision is not None
    envelope = parse_continuation_envelope(fast_trace["continuation_envelope"])

    deep, deep_trace = core.ask_service.deep_service.ask(
        AskRequest(query="MCP", mode="deep"),
        evidence_decision=decision,
        continuation_envelope=envelope,
    )
    durable = core.ask_service.run_store.get_run(deep.run_id)
    assert durable is not None
    assert durable["parent_run_id"] == fast.run_id
    assert deep_trace["adaptive_directive"] == "finalize"
    assert any(
        value.get("event_type") == "canonical_evidence_decision_consumed"
        for value in deep_trace["events"]
    )
    assert deep_trace["provider_usage"]["agent_actions"] == []
    assert deep_trace["final_evidence"]
    assert envelope.original_question == "MCP"


def test_fast_to_research_persists_same_decision_without_provider_inheritance(app_paths) -> None:
    from test_v4_fast_ask_api import _Provider, _application

    provider = _Provider()
    core, _ = _application(app_paths, provider)
    fast = core.ask_service.ask(AskRequest(query="MCP", mode="fast"))
    trace = core.ask_service.get_trace(fast.run_id)
    assert trace is not None
    decision = decision_from_trace(trace)
    assert decision is not None
    envelope = envelope_for_completed_run(
        run_id=fast.run_id,
        decision=decision,
        target=ContinuationTarget.RESEARCH,
        question="MCP",
        filters=trace["filters"],
        citations=trace["citations"],
        search_executions=trace["search_executions"],
    )
    created = core.research_product.create_task(
        CreateProductResearchRequest(
            command_id="goal2a:fast-to-research",
            objective="MCP",
            run_immediately=False,
        ),
        evidence_decision=decision,
        continuation_envelope=envelope,
    )
    raw = core.research.get_task(str(created["task_id"]))
    goal = raw["goals"][0]
    policy = goal["evidence_policy"]
    restored = decision_from_persistence_projection(policy["evidence_decision"])
    assert restored.decision_id == decision.decision_id
    assert policy["continuation_envelope"]["parent_run_id"] == fast.run_id
    assert policy["provider_authority_inherited"] is False
    assert policy["product_execution"] == "deterministic_no_provider"

    with pytest.raises(ResearchValidationError):
        core.research_product.create_task(
            CreateProductResearchRequest(
                command_id="goal2a:changed-question",
                objective="另一个问题",
                run_immediately=False,
            ),
            evidence_decision=decision,
            continuation_envelope=envelope,
        )


def test_bounded_knowledge_route_persists_canonical_owner(app_paths) -> None:
    from test_v5_b_stage3_artifact_reuse import GAP, _assess, _core, _vertical
    from shiliu.research.knowledge_contracts import ProceedArtifactRouteRequest

    core = _core(app_paths)
    task_id, _fact, artifact, _page = _vertical(core, "goal2a-canonical")
    response = _assess(
        core,
        task_id,
        suffix="goal2a-canonical",
        query=artifact["topic"],
        aspects=[artifact["body"]["facts"][0]["claim"]],
    )
    decision = decision_from_persistence_projection(response["evidence_decision"])
    assert response["canonical_action"] == decision.action.value
    assert response["recommended_route"] == "direct_reuse"
    assert decision.action == EvidenceDecisionAction.DIRECT_REUSE
    assert decision.provider_authority_granted is False
    stored = core.research_knowledge.get_artifact_route(task_id, response["route_id"])
    persisted = stored["latest"]["retrieval"]["evidence_decision"]
    assert decision_from_persistence_projection(persisted).decision_id == decision.decision_id

    incremental = _assess(
        core,
        task_id,
        suffix="goal2a-incremental",
        query=f"{artifact['topic']} {GAP}",
        aspects=[artifact["body"]["facts"][0]["claim"], GAP],
    )
    incremental_decision = decision_from_persistence_projection(
        incremental["evidence_decision"]
    )
    assert incremental_decision.action == EvidenceDecisionAction.TARGETED_REFRESH
    proceeded = core.research_knowledge.proceed_artifact_route(
        task_id,
        incremental["route_id"],
        ProceedArtifactRouteRequest(
            command_id="goal2a:knowledge:continue",
            expected_version=1,
            route="incremental_refresh",
        ),
        principal_id="local_operator",
    )
    child = core.research.get_task(proceeded["continuation_task_id"])
    policy = child["goals"][0]["evidence_policy"]
    assert policy["continuation_envelope"]["target"] == "knowledge_reuse"
    assert policy["continuation_envelope"]["open_aspects"] == ["aspect_2"]
    assert policy["provider_authority_inherited"] is False


def test_failure_categories_remain_distinct_in_ask_persistence(app_paths) -> None:
    from shiliu.app import Application
    from shiliu.ask.persistence import AskRunStore

    core = Application(app_paths)
    store = AskRunStore(core.db)
    cases = {
        "unknown_side_effect": "unknown_side_effect",
        "transport_connection": "transport",
        "interrupted": "interrupted",
        "provider_error": "provider",
        "generation_failed": "generation",
    }
    for index, (code, expected_class) in enumerate(cases.items()):
        run_id = f"failure-{index}"
        store.start(run_id=run_id, query="q", mode="fast", filters={})
        error = RuntimeError(code)
        error.code = code  # type: ignore[attr-defined]
        store.fail(run_id, error)
        record = store.get_run(run_id)
        assert record is not None
        assert record["error"]["failure_class"] == expected_class
    assert len(set(cases.values())) == len(cases)


def test_goal2a_does_not_add_goal2b_surface() -> None:
    from pathlib import Path

    root = Path(__file__).parents[1] / "src" / "shiliu"
    changed_modules = [
        root / "evidence" / "continuation.py",
        root / "ask" / "adaptive.py",
    ]
    text = "\n".join(value.read_text(encoding="utf-8") for value in changed_modules)
    assert "StreamingResponse" not in text
    assert "KnowledgeDraft" not in text
    assert "evaluate_bounded_claim_support" not in text


def _service_envelope(decision, trace, *, target=ContinuationTarget.FAST):
    prior = parse_continuation_envelope(trace["continuation_envelope"])
    return create_continuation_envelope(
        parent_run_id=trace["run_id"],
        parent_decision=decision,
        target=target,
        original_question=trace["query"],
        normalized_scope=trace["filters"],
        inherited_evidence=prior.inherited_evidence,
        search_executions=prior.search_executions,
    )


def _deep_decision(decision):
    observed_at = datetime.now(timezone.utc)
    reference_ids = tuple(
        reference.reference_id
        for coverage in decision.coverage
        for reference in coverage.authority_references
    )
    return create_evidence_decision(
        EvidenceDecisionInput(
            normalized_question=decision.normalized_question,
            requirements=decision.requirements,
            scope=decision.scope,
            coverage=decision.coverage,
            library_freshness=decision.library_freshness,
            conflicts=(
                ConflictObservation(
                    conflict_id="repair-conflict",
                    status=ConflictStatus.CONFIRMED,
                    left_reference_ids=reference_ids,
                    right_reference_ids=reference_ids,
                    observed_at=observed_at,
                    explanation="repair fixture requires the Deep boundary",
                ),
            ),
            contributions=decision.contributions,
        ),
        recorded_at=observed_at,
    )


def _targeted_decision(decision):
    recorded_at = datetime.now(timezone.utc)
    requirement = EvidenceRequirement(
        aspect_id="repair-open-aspect",
        description="需要定向补证的方面",
        origin=RequirementOrigin.EXPLICIT_USER,
    )
    return create_evidence_decision(
        EvidenceDecisionInput(
            normalized_question=decision.normalized_question,
            requirements=(*decision.requirements, requirement),
            scope=decision.scope,
            coverage=(
                *decision.coverage,
                AspectCoverage(
                    aspect_id=requirement.aspect_id,
                    status=CoverageStatus.OPEN,
                    authority_references=(),
                    explanation="repair fixture open aspect",
                ),
            ),
            library_freshness=decision.library_freshness,
            contributions=decision.contributions,
        ),
        recorded_at=recorded_at,
    )


def _clarify_decision(decision):
    recorded_at = datetime.now(timezone.utc)
    return create_evidence_decision(
        EvidenceDecisionInput(
            normalized_question=decision.normalized_question,
            requirements=decision.requirements,
            scope=ScopeAssessment(
                status=ScopeMatchStatus.UNKNOWN,
                requested_scope_hash=decision.scope.requested_scope_hash,
                candidate_scope_hash=None,
                explanation="repair fixture unknown scope",
            ),
            coverage=decision.coverage,
            library_freshness=decision.library_freshness,
            contributions=decision.contributions,
        ),
        recorded_at=recorded_at,
    )


def test_service_gate_rejects_question_scope_and_hash_stale_envelope_before_calls(
    app_paths,
) -> None:
    from test_v4_fast_ask_api import _Provider, _application

    provider = _Provider()
    core, _ = _application(app_paths, provider)
    parent = core.ask_service.ask(AskRequest(query="MCP", mode="fast"))
    trace = core.ask_service.get_trace(parent.run_id)
    assert trace is not None
    decision = decision_from_trace(trace)
    assert decision is not None
    envelope = _service_envelope(decision, trace)
    before = (provider.query_calls, provider.agent_calls, provider.answer_calls)

    with pytest.raises(ContinuationContractError) as question_error:
        core.ask_service.ask(
            AskRequest(query="完全不同的问题", mode="fast"),
            evidence_decision=decision,
            continuation_envelope=envelope,
        )
    assert question_error.value.code == "continuation_question_mismatch"

    with pytest.raises(ContinuationContractError) as scope_error:
        core.ask_service.ask(
            AskRequest(
                query="MCP",
                mode="fast",
                filters=ProductSearchFilterRequest(folder_id=123),
            ),
            evidence_decision=decision,
            continuation_envelope=envelope,
        )
    assert scope_error.value.code == "continuation_scope_mismatch"

    tampered = envelope.model_copy(update={"normalized_scope": {"folder_id": 123}})
    with pytest.raises(ContinuationContractError) as integrity_error:
        core.ask_service.ask(
            AskRequest(query="MCP", mode="fast"),
            evidence_decision=decision,
            continuation_envelope=tampered,
        )
    assert integrity_error.value.code == "continuation_integrity_failed"
    assert (provider.query_calls, provider.agent_calls, provider.answer_calls) == before


def test_deep_and_research_reject_hash_stale_envelope_before_side_effects(
    app_paths,
) -> None:
    from test_v4_fast_ask_api import _Provider, _application

    provider = _Provider()
    core, _ = _application(app_paths, provider)
    parent = core.ask_service.ask(AskRequest(query="MCP", mode="fast"))
    trace = core.ask_service.get_trace(parent.run_id)
    assert trace is not None
    decision = decision_from_trace(trace)
    assert decision is not None
    before = (provider.query_calls, provider.agent_calls, provider.answer_calls)

    deep_envelope = _service_envelope(
        decision, trace, target=ContinuationTarget.DEEP
    )
    stale_deep = deep_envelope.model_copy(
        update={"normalized_scope": {"folder_id": 123}}
    )
    with pytest.raises(ContinuationContractError) as deep_error:
        core.ask_service.deep_service.ask(
            AskRequest(query="MCP", mode="deep"),
            evidence_decision=decision,
            continuation_envelope=stale_deep,
        )
    assert deep_error.value.code == "continuation_integrity_failed"

    research_envelope = _service_envelope(
        decision, trace, target=ContinuationTarget.RESEARCH
    )
    stale_research = research_envelope.model_copy(
        update={"normalized_scope": {"folder_id": 123}}
    )
    with pytest.raises(ResearchValidationError):
        core.research_product.create_task(
            CreateProductResearchRequest(
                command_id="goal2a-repair:research-tamper",
                objective="MCP",
                run_immediately=False,
            ),
            evidence_decision=decision,
            continuation_envelope=stale_research,
        )
    assert (provider.query_calls, provider.agent_calls, provider.answer_calls) == before


def test_fast_deep_action_enters_deep_boundary_with_durable_lineage(app_paths) -> None:
    from test_v4_fast_ask_api import _Provider, _application

    provider = _Provider()
    core, _ = _application(app_paths, provider)
    parent = core.ask_service.ask(AskRequest(query="MCP", mode="fast"))
    trace = core.ask_service.get_trace(parent.run_id)
    assert trace is not None
    parent_decision = decision_from_trace(trace)
    assert parent_decision is not None
    decision = _deep_decision(parent_decision)
    assert decision.action == EvidenceDecisionAction.DEEP_RESEARCH
    envelope = _service_envelope(
        decision, trace, target=ContinuationTarget.DEEP
    )
    answer_before = provider.answer_calls

    response = core.ask_service.ask(
        AskRequest(query="MCP", mode="fast"),
        evidence_decision=decision,
        continuation_envelope=envelope,
    )

    assert response.mode == "deep"
    assert provider.agent_calls > 0
    assert provider.answer_calls == answer_before + 1
    durable = core.ask_service.run_store.get_run(response.run_id)
    assert durable is not None
    assert durable["parent_run_id"] == parent.run_id
    child = decision_from_trace(core.ask_service.get_trace(response.run_id))
    assert child is not None
    assert child.parent_decision_id is not None


def test_deep_zero_evidence_repeated_search_completes_insufficient_with_lineage(
    app_paths,
) -> None:
    from types import SimpleNamespace

    from shiliu.ask.deep.contracts import AgentDecision
    from shiliu.evidence.source import authoritative_raw_json_path
    from test_v4_fast_ask_api import _Provider, _application

    provider = _Provider()
    core, raw_path = _application(app_paths, provider)
    parent = core.ask_service.ask(AskRequest(query="MCP", mode="fast"))
    parent_trace = core.ask_service.get_trace(parent.run_id)
    assert parent_trace is not None
    parent_decision = decision_from_trace(parent_trace)
    assert parent_decision is not None
    decision = _deep_decision(parent_decision)
    envelope = _service_envelope(
        decision, parent_trace, target=ContinuationTarget.DEEP
    )

    authority_path = authoritative_raw_json_path(raw_path)
    authority_path.write_text(
        authority_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    original_generate = provider.generate_structured

    def repeat_zero_yield_search(
        *, role, messages, response_schema, max_tokens, timeout_seconds=None
    ):
        if role != "agent_action":
            return original_generate(
                role=role,
                messages=messages,
                response_schema=response_schema,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
            )
        provider.agent_calls += 1
        return SimpleNamespace(
            output=AgentDecision.model_validate(
                {
                    "action": {
                        "kind": "search_transcripts",
                        "query": "rc5-deterministic-zero-yield-token",
                        "video_ids": [],
                    }
                }
            ),
            usage={"prompt_tokens": 20, "completion_tokens": 10},
        )

    provider.generate_structured = repeat_zero_yield_search
    answer_calls_before = provider.answer_calls

    response, trace = core.ask_service.deep_service.ask(
        AskRequest(query="MCP", mode="deep"),
        evidence_decision=decision,
        continuation_envelope=envelope,
    )

    assert response.status == "insufficient"
    assert response.execution_outcome == "evidence_unavailable"
    assert response.answer_blocks == []
    assert response.citations == []
    assert response.termination_reason == "repeated_search"
    assert response.limitations == ["没有找到可绑定当前字幕版本的有效证据"]
    assert provider.answer_calls == answer_calls_before
    assert trace["evidence_count"] == 0
    assert trace["adaptive_directive"] == "deep_research"
    assert trace["finalization"].get("answer_calls", 0) == 0
    assert any(
        event.get("event_type") == "observation"
        and event.get("observation_kind") == "transcript_search"
        for event in trace["events"]
    )
    assert any(
        event.get("event_type") == "finalize"
        and event.get("termination_reason") == "repeated_search"
        for event in trace["events"]
    )

    durable = core.ask_service.run_store.get_run(response.run_id)
    assert durable is not None
    assert durable["lifecycle_status"] == "completed"
    assert durable["parent_run_id"] == parent.run_id
    assert durable["answer_status"] == "insufficient"
    assert durable["termination_reason"] == "repeated_search"
    assert durable["error"] == {}
    event_types = [
        event["event_type"]
        for event in core.ask_service.run_store.get_events(response.run_id)
    ]
    assert "canonical_evidence_decision_consumed" in event_types
    assert "decision" in event_types
    assert "observation" in event_types
    assert event_types[-1] == "run_completed"


def test_deep_nonempty_nonfinal_continuation_still_fails_closed(
    app_paths, monkeypatch
) -> None:
    from types import SimpleNamespace

    from shiliu.ask.deep.contracts import AgentDecision
    import shiliu.ask.deep.service as deep_service_module
    from test_v4_fast_ask_api import _Provider, _application

    provider = _Provider()
    core, _ = _application(app_paths, provider)
    parent = core.ask_service.ask(AskRequest(query="MCP", mode="fast"))
    parent_trace = core.ask_service.get_trace(parent.run_id)
    assert parent_trace is not None
    parent_decision = decision_from_trace(parent_trace)
    assert parent_decision is not None
    decision = _deep_decision(parent_decision)
    envelope = _service_envelope(
        decision, parent_trace, target=ContinuationTarget.DEEP
    )
    original_generate = provider.generate_structured

    def repeat_search(
        *, role, messages, response_schema, max_tokens, timeout_seconds=None
    ):
        if role != "agent_action":
            return original_generate(
                role=role,
                messages=messages,
                response_schema=response_schema,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
            )
        provider.agent_calls += 1
        return SimpleNamespace(
            output=AgentDecision.model_validate(
                {
                    "action": {
                        "kind": "search_transcripts",
                        "query": "MCP",
                        "video_ids": [],
                    }
                }
            ),
            usage={"prompt_tokens": 20, "completion_tokens": 10},
        )

    provider.generate_structured = repeat_search
    monkeypatch.setattr(
        deep_service_module,
        "create_current_evidence_decision",
        lambda **_kwargs: decision,
    )
    answer_calls_before = provider.answer_calls

    with pytest.raises(ContinuationContractError) as action_error:
        core.ask_service.deep_service.ask(
            AskRequest(query="MCP", mode="deep"),
            evidence_decision=decision,
            continuation_envelope=envelope,
        )

    assert action_error.value.code == "continuation_action_boundary"
    assert provider.agent_calls >= 2
    assert provider.answer_calls == answer_calls_before


def test_parent_binding_and_provider_authority_tamper_fail_before_calls(
    app_paths,
) -> None:
    from test_v4_fast_ask_api import _Provider, _application

    provider = _Provider()
    core, _ = _application(app_paths, provider)
    parent = core.ask_service.ask(AskRequest(query="MCP", mode="fast"))
    trace = core.ask_service.get_trace(parent.run_id)
    assert trace is not None
    decision = decision_from_trace(trace)
    assert decision is not None
    envelope = _service_envelope(decision, trace)
    before = (provider.query_calls, provider.agent_calls, provider.answer_calls)

    other_decision = _deep_decision(decision)
    with pytest.raises(ContinuationContractError) as binding_error:
        core.ask_service.ask(
            AskRequest(query="MCP", mode="fast"),
            evidence_decision=other_decision,
            continuation_envelope=envelope,
        )
    assert binding_error.value.code == "parent_decision_mismatch"

    authority_decision = decision.model_copy(
        update={"provider_authority_granted": True}
    )
    with pytest.raises(ContinuationContractError) as authority_error:
        core.ask_service.ask(
            AskRequest(query="MCP", mode="fast"),
            evidence_decision=authority_decision,
            continuation_envelope=envelope,
        )
    assert authority_error.value.code == "continuation_provider_authority_forbidden"

    authority_envelope = envelope.model_copy(
        update={"provider_authority_inherited": True}
    )
    with pytest.raises(ContinuationContractError) as envelope_error:
        core.ask_service.ask(
            AskRequest(query="MCP", mode="fast"),
            evidence_decision=decision,
            continuation_envelope=authority_envelope,
        )
    assert envelope_error.value.code == "invalid_continuation_envelope"
    assert (provider.query_calls, provider.agent_calls, provider.answer_calls) == before


def test_research_target_fails_closed_in_fast_and_remains_valid_in_research(
    app_paths,
) -> None:
    from test_v4_fast_ask_api import _Provider, _application

    provider = _Provider()
    core, _ = _application(app_paths, provider)
    parent = core.ask_service.ask(AskRequest(query="MCP", mode="fast"))
    trace = core.ask_service.get_trace(parent.run_id)
    assert trace is not None
    decision = decision_from_trace(trace)
    assert decision is not None
    envelope = _service_envelope(
        decision, trace, target=ContinuationTarget.RESEARCH
    )
    before = (provider.query_calls, provider.agent_calls, provider.answer_calls)

    with pytest.raises(ContinuationContractError) as target_error:
        core.ask_service.ask(
            AskRequest(query="MCP", mode="fast"),
            evidence_decision=decision,
            continuation_envelope=envelope,
        )
    assert target_error.value.code == "continuation_target_mismatch"

    created = core.research_product.create_task(
        CreateProductResearchRequest(
            command_id="goal2a-repair:research-valid",
            objective="MCP",
            run_immediately=False,
        ),
        evidence_decision=decision,
        continuation_envelope=envelope,
    )
    raw = core.research.get_task(str(created["task_id"]))
    policy = raw["goals"][0]["evidence_policy"]
    assert policy["continuation_envelope"]["envelope_id"] == envelope.envelope_id
    assert policy["provider_authority_inherited"] is False
    assert (provider.query_calls, provider.agent_calls, provider.answer_calls) == before


def test_non_finalize_and_unsafe_states_never_call_fast_answer(app_paths) -> None:
    from test_v4_fast_ask_api import _Provider, _application

    provider = _Provider()
    core, _ = _application(app_paths, provider)
    parent = core.ask_service.ask(AskRequest(query="MCP", mode="fast"))
    trace = core.ask_service.get_trace(parent.run_id)
    assert trace is not None
    decision = decision_from_trace(trace)
    assert decision is not None
    before = (provider.query_calls, provider.agent_calls, provider.answer_calls)

    clarify = _clarify_decision(decision)
    assert clarify.action == EvidenceDecisionAction.CLARIFY
    with pytest.raises(ContinuationContractError) as clarify_error:
        core.ask_service.ask(
            AskRequest(query="MCP", mode="fast"),
            evidence_decision=clarify,
            continuation_envelope=_service_envelope(clarify, trace),
        )
    assert clarify_error.value.code == "continuation_action_boundary"

    abstain = decision.model_copy(update={"action": EvidenceDecisionAction.ABSTAIN})
    with pytest.raises(ContinuationContractError) as abstain_error:
        core.ask_service.ask(
            AskRequest(query="MCP", mode="fast"),
            evidence_decision=abstain,
            continuation_envelope=envelope_for_completed_run(
                run_id=parent.run_id,
                decision=abstain,
                target=ContinuationTarget.FAST,
                question="MCP",
                filters=trace["filters"],
                citations=trace["citations"],
                search_executions=trace["search_executions"],
            ),
        )
    assert abstain_error.value.code == "continuation_decision_integrity_failed"

    unsafe = create_continuation_envelope(
        parent_run_id=parent.run_id,
        parent_decision=decision,
        target=ContinuationTarget.FAST,
        original_question="MCP",
        normalized_scope=trace["filters"],
        inherited_evidence=parse_continuation_envelope(
            trace["continuation_envelope"]
        ).inherited_evidence,
        receipt_state=ReceiptState.UNKNOWN,
    )
    with pytest.raises(ContinuationContractError) as unsafe_error:
        core.ask_service.ask(
            AskRequest(query="MCP", mode="fast"),
            evidence_decision=decision,
            continuation_envelope=unsafe,
        )
    assert unsafe_error.value.code == "continuation_replay_unsafe"
    assert (provider.query_calls, provider.agent_calls, provider.answer_calls) == before


def test_fast_targeted_refresh_child_deep_does_not_call_fast_finalizer(
    app_paths, monkeypatch
) -> None:
    from types import SimpleNamespace
    from test_v4_fast_ask_api import _Provider, _application
    import shiliu.ask.service as ask_service_module

    provider = _Provider()
    core, _ = _application(app_paths, provider)
    parent = core.ask_service.ask(AskRequest(query="MCP", mode="fast"))
    trace = core.ask_service.get_trace(parent.run_id)
    assert trace is not None
    parent_decision = decision_from_trace(trace)
    assert parent_decision is not None
    targeted = _targeted_decision(parent_decision)
    assert targeted.action == EvidenceDecisionAction.TARGETED_REFRESH
    envelope = _service_envelope(targeted, trace)
    observed: dict[str, object] = {}

    def fake_refresh(**kwargs):
        observed.update(kwargs)
        child = _deep_decision(kwargs["decision"])
        return SimpleNamespace(
            execution=SimpleNamespace(
                final_decision=child,
                search_executions=(),
                rounds=(),
                stop_reason=ContinuationStopReason.CONFLICT_UNRESOLVED,
            ),
            spans=kwargs["inherited_spans"],
        )

    monkeypatch.setattr(ask_service_module, "execute_targeted_refresh", fake_refresh)
    before = (provider.query_calls, provider.agent_calls, provider.answer_calls)
    with pytest.raises(ContinuationContractError) as action_error:
        core.ask_service.ask(
            AskRequest(query="MCP", mode="fast"),
            evidence_decision=targeted,
            continuation_envelope=envelope,
        )
    assert action_error.value.code == "continuation_action_boundary"
    assert observed["decision"].parent_decision_id == targeted.decision_id
    assert (provider.query_calls, provider.agent_calls, provider.answer_calls) == before
