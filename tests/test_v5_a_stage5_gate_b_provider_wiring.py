from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from shiliu.ask.answer import GroundedAnswerService
from shiliu.ask.context import ContextBuildResult
from shiliu.ask.contracts import GroundedAnswerDraft, QueryAnalysis
from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.deep.contracts import AgentDecision
from shiliu.ask.deep.decision import AgentDecisionService
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.query_analysis import QueryAnalyzer
from shiliu.db import Database
from shiliu.research.control_contracts import ControlCommandRequest
from shiliu.research.control_service import ResearchControlService
from shiliu.research.errors import ResearchConflict, SimulatedCrash
from shiliu.research.provider_wiring import (
    PROVIDER_ACTION_SCHEMA_VERSION,
    ProviderBudgetExceeded,
    ProviderCallContext,
    ProviderDispatchUnknown,
    ProviderPricePolicy,
    ReceiptBoundProviderService,
)
from shiliu.research.service import ResearchTaskService
from shiliu.retrieval.product_search import ProductSearchFilterRequest


@dataclass
class _Reply:
    output: object
    usage: dict[str, int]
    response_id: str
    finish_reason: str = "stop"
    latency_ms: float = 3.5
    retry_count: int = 0


class _NoNetworkProvider:
    def __init__(self, *, fail: Exception | None = None) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    def generate_structured(self, **kwargs):
        self.calls.append(dict(kwargs))
        if self.fail is not None:
            raise self.fail
        role = str(kwargs["role"])
        if role == "query_analysis":
            output = QueryAnalysis(
                normalized_intent="MCP durable research",
                search_queries=["MCP checkpoint"],
                entities=["MCP"],
                language="zh",
            )
            usage = {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "prompt_cache_hit_tokens": 10,
            }
        elif role == "agent_action":
            output = AgentDecision(
                action={"kind": "finish", "summary": "enough evidence"},
                open_questions=[],
                resolved_questions=[],
            )
            usage = {"prompt_tokens": 150, "completion_tokens": 30}
        elif role == "grounded_answer":
            output = GroundedAnswerDraft(
                status="insufficient",
                answer_blocks=[],
                limitations=["当前固定字幕证据不足"],
            )
            usage = {"prompt_tokens": 200, "completion_tokens": 40}
        else:  # pragma: no cover - guarded by the product service
            raise AssertionError(role)
        return _Reply(
            output=output,
            usage=usage,
            response_id=f"mock-{role}-{len(self.calls)}",
        )


class _KnownInvalidThenValidProvider(_NoNetworkProvider):
    def generate_structured(self, **kwargs):
        if not self.calls:
            self.calls.append(dict(kwargs))
            error = ValueError("known invalid JSON output")
            error.completion_metadata = {  # type: ignore[attr-defined]
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 120, "completion_tokens": 25},
                "response_id": "mock-invalid-grounded",
                "latency_ms": 2.0,
                "retry_count": 0,
                "content_received": True,
            }
            raise error
        return super().generate_structured(**kwargs)


class _MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 3, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def _started(app_paths, *, task_id: str = "rtask_gate_b"):
    db = Database(app_paths.database)
    db.initialize()
    clock = _MutableClock()
    kernel = ResearchTaskService(db, clock=clock)
    kernel.create_task(
        command_id=f"create:{task_id}",
        task_id=task_id,
        objective="MCP durable research",
        success_constraints=["use current evidence"],
        evidence_policy={},
    )
    claim = kernel.claim_owner(
        task_id=task_id,
        command_id=f"claim:{task_id}",
        owner_id="worker-a",
        expected_state_version=0,
        lease_seconds=600,
    )
    attempt = kernel.start_attempt(
        task_id=task_id,
        command_id=f"start:{task_id}",
        owner_id="worker-a",
        owner_epoch=int(claim["owner_epoch"]),
        expected_state_version=1,
    )
    context = ProviderCallContext(
        task_id=task_id,
        attempt_id=str(attempt["attempt_id"]),
        owner_id="worker-a",
        owner_epoch=int(claim["owner_epoch"]),
        expected_state_version=2,
        expected_checkpoint_id=None,
        expected_control_generation=0,
        operation_key="gate-b-mechanical",
    )
    return db, kernel, clock, context


def _deep_state() -> dict[str, object]:
    return {
        "run_id": "gate-b",
        "query": "MCP durable research",
        "filters": ProductSearchFilterRequest(),
        "open_questions": ["MCP durable research"],
        "resolved_questions": [],
        "evidence_spans": [],
        "navigation_documents": [],
        "visited_video_ids": [],
        "visited_segment_ids": [],
        "previous_queries": [],
        "repeated_action_keys": [],
        "decision_rounds": 0,
        "tool_calls": 0,
        "consecutive_no_new_evidence": 0,
        "navigation_result_count": 0,
        "started_at": 0.0,
        "search_deadline": 100.0,
        "total_deadline": 200.0,
        "last_action": None,
        "last_observation_summary": "",
        "pending_observation": None,
        "errors": [],
        "stale_reasons": [],
        "events": [],
        "usage": [],
        "termination_reason": None,
    }


def _direct_query(factory, content: str = "MCP"):
    return factory("query_analysis").generate_structured(
        role="query_analysis",
        messages=[{"role": "user", "content": content}],
        response_schema=QueryAnalysis,
        max_tokens=1200,
    )


def test_default_wiring_authority_is_disabled_without_any_factory_access(
    app_paths,
) -> None:
    db, kernel, _clock, context = _started(
        app_paths, task_id="rtask_disabled"
    )
    provider = _NoNetworkProvider()
    disabled = ReceiptBoundProviderService(db=db, kernel=kernel)
    with pytest.raises(ResearchConflict, match="explicit run authorization"):
        _direct_query(
            disabled.factory(
                context=context, provider_factory=lambda _role: provider
            )
        )
    assert provider.calls == []
    task = kernel.get_task(context.task_id)
    assert task["side_effects"] == []
    assert task["inner_actions"] == []


def test_frozen_structured_roles_are_receipted_and_exact_replay_is_free(
    app_paths,
) -> None:
    db, kernel, _clock, context = _started(app_paths)
    provider = _NoNetworkProvider()
    wiring = ReceiptBoundProviderService(
        db=db, kernel=kernel, provider_dispatch_authorized=True
    )
    bound_factory = wiring.factory(
        context=context, provider_factory=lambda _role: provider
    )

    plan = QueryAnalyzer(bound_factory).analyze("MCP durable research")
    assert plan.analysis.entities == ["MCP"]
    decision, metadata = AgentDecisionService(
        bound_factory,
        DeepSearchBudget(),
        clock=lambda: 1.0,
    ).decide(_deep_state())  # type: ignore[arg-type]
    assert decision.action.kind == "finish"
    assert metadata["response_id"].startswith("mock-agent_action")
    answer = GroundedAnswerService(
        bound_factory,
        TranscriptEvidenceMaterializer(db),
    ).answer(
        query="MCP durable research",
        context=ContextBuildResult(
            spans=(),
            model_context="{}",
            citation_allowlist=(),
            truncated=False,
            dropped_span_count=0,
        ),
    )
    assert answer.draft is not None and answer.draft.status == "insufficient"
    assert [str(call["role"]) for call in provider.calls] == [
        "query_analysis",
        "agent_action",
        "grounded_answer",
    ]

    snapshot = wiring.budget_snapshot(context.task_id)
    assert snapshot.logical_calls == 3
    assert snapshot.transport_calls == 3
    assert snapshot.input_tokens == 450
    assert snapshot.cached_input_tokens == 10
    assert snapshot.output_tokens == 90
    assert Decimal(snapshot.committed_cost_usd) > 0
    assert snapshot.active_reserved_cost_usd == "0.000000000"
    with db.connect() as connection:
        effects = connection.execute(
            "SELECT * FROM research_side_effects WHERE task_id=? ORDER BY created_at",
            (context.task_id,),
        ).fetchall()
        actions = connection.execute(
            "SELECT * FROM research_inner_actions WHERE task_id=? AND action_schema_version=?",
            (context.task_id, PROVIDER_ACTION_SCHEMA_VERSION),
        ).fetchall()
        events = connection.execute(
            "SELECT event_type, payload_json FROM research_events WHERE task_id=?",
            (context.task_id,),
        ).fetchall()
    assert len(effects) == len(actions) == 3
    assert all(str(effect["status"]) == "succeeded" for effect in effects)
    assert all(effect["receipt_hash"] and effect["result_reference"] for effect in effects)
    assert sum(row["event_type"] == "provider_call_receipted" for row in events) == 3
    for row in events:
        if row["event_type"] != "provider_call_receipted":
            continue
        binding = json.loads(str(row["payload_json"]))
        assert binding["provider"] == "deepseek_openai_compatible"
        assert binding["model"] == "deepseek-v4-pro"
        assert binding["structured_request_hash"]
        assert binding["usage"]
        assert binding["cost_usd"]
        assert binding["result_reference"]
        assert binding["receipt_hash"]

    restarted_context = replace(
        context,
        expected_state_version=int(
            kernel.get_task(context.task_id)["task"]["state_version"]
        ),
    )
    replay_provider = _NoNetworkProvider()
    replay_factory = ReceiptBoundProviderService(
        db=db, kernel=kernel, provider_dispatch_authorized=True
    ).factory(
        context=restarted_context,
        provider_factory=lambda _role: replay_provider,
    )
    replay = QueryAnalyzer(replay_factory).analyze("MCP durable research")
    assert replay.analysis.entities == ["MCP"]
    assert replay_provider.calls == []
    assert restarted_context.expected_state_version == int(
        kernel.get_task(context.task_id)["task"]["state_version"]
    )


def test_restart_preserves_budget_and_reservation_rejects_before_factory(
    app_paths,
) -> None:
    db, kernel, _clock, context = _started(app_paths, task_id="rtask_budget")
    provider = _NoNetworkProvider()
    wiring = ReceiptBoundProviderService(
        db=db, kernel=kernel, provider_dispatch_authorized=True
    )
    response = _direct_query(
        wiring.factory(context=context, provider_factory=lambda _role: provider)
    )
    assert response.receipt_binding["cost_usd"]
    before = wiring.budget_snapshot(context.task_id)

    restarted_policy = replace(
        ProviderPricePolicy(),
        absolute_max_cost_usd=Decimal(before.committed_cost_usd),
    )
    restarted = ReceiptBoundProviderService(
        db=db,
        kernel=kernel,
        price_policy=restarted_policy,
        provider_dispatch_authorized=True,
    )
    assert restarted.budget_snapshot(context.task_id) == before
    blocked_provider = _NoNetworkProvider()
    blocked_context = replace(
        context,
        expected_state_version=int(
            kernel.get_task(context.task_id)["task"]["state_version"]
        ),
        operation_key="gate-b-budget-block",
    )
    blocked_factory = restarted.factory(
        context=blocked_context,
        provider_factory=lambda _role: blocked_provider,
    )
    with pytest.raises(ProviderBudgetExceeded):
        _direct_query(blocked_factory)
    with pytest.raises(ProviderBudgetExceeded):
        _direct_query(
            restarted.factory(
                context=blocked_context,
                provider_factory=lambda _role: blocked_provider,
            )
        )
    assert blocked_provider.calls == []
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_events WHERE task_id=? "
            "AND event_type='provider_cost_reservation_rejected'",
            (context.task_id,),
        ).fetchone()[0] == 1


def test_default_absolute_fifty_cent_cap_blocks_before_factory(app_paths) -> None:
    db, kernel, _clock, context = _started(
        app_paths, task_id="rtask_absolute_cap"
    )
    provider = _NoNetworkProvider()
    wiring = ReceiptBoundProviderService(
        db=db, kernel=kernel, provider_dispatch_authorized=True
    )
    assert wiring.price_policy.absolute_max_cost_usd == Decimal("0.50")
    with pytest.raises(ProviderBudgetExceeded, match="0.50"):
        _direct_query(
            wiring.factory(
                context=context, provider_factory=lambda _role: provider
            ),
            "x" * 300_000,
        )
    assert provider.calls == []
    task = kernel.get_task(context.task_id)
    assert task["side_effects"] == []
    assert task["inner_actions"] == []


def test_known_invalid_output_is_receipted_once_then_uses_bounded_repair(
    app_paths,
) -> None:
    db, kernel, _clock, context = _started(
        app_paths, task_id="rtask_known_invalid"
    )
    provider = _KnownInvalidThenValidProvider()
    wiring = ReceiptBoundProviderService(
        db=db, kernel=kernel, provider_dispatch_authorized=True
    )
    answer = GroundedAnswerService(
        wiring.factory(
            context=context, provider_factory=lambda _role: provider
        ),
        TranscriptEvidenceMaterializer(db),
    ).answer(
        query="MCP durable research",
        context=ContextBuildResult(
            spans=(),
            model_context="{}",
            citation_allowlist=(),
            truncated=False,
            dropped_span_count=0,
        ),
    )
    assert answer.repair_used is True
    assert answer.draft is not None and answer.draft.status == "insufficient"
    assert len(provider.calls) == 2
    task = kernel.get_task(context.task_id)
    assert [effect["status"] for effect in task["side_effects"]] == [
        "failed",
        "succeeded",
    ]
    assert wiring.budget_snapshot(context.task_id).logical_calls == 2


def test_unknown_dispatch_is_durable_and_never_auto_replays(app_paths) -> None:
    db, kernel, _clock, context = _started(app_paths, task_id="rtask_unknown")
    failing = _NoNetworkProvider(fail=RuntimeError("mock transport ambiguity"))
    wiring = ReceiptBoundProviderService(
        db=db, kernel=kernel, provider_dispatch_authorized=True
    )
    factory = wiring.factory(
        context=context, provider_factory=lambda _role: failing
    )
    with pytest.raises(ProviderDispatchUnknown):
        _direct_query(factory)
    task = kernel.get_task(context.task_id)
    assert task["task"]["status"] == "blocked"
    assert task["side_effects"][0]["status"] == "unknown"
    assert task["inner_actions"][0]["status"] == "unknown"
    assert wiring.budget_snapshot(context.task_id).active_reserved_cost_usd != "0.000000000"

    replay_provider = _NoNetworkProvider()
    replay_context = replace(
        context,
        expected_state_version=int(task["task"]["state_version"]),
    )
    with pytest.raises(ProviderDispatchUnknown):
        _direct_query(
            wiring.factory(
                context=replay_context,
                provider_factory=lambda _role: replay_provider,
            )
        )
    with pytest.raises(ProviderDispatchUnknown):
        _direct_query(
            wiring.factory(
                context=replace(
                    replay_context, operation_key="different-provider-operation"
                ),
                provider_factory=lambda _role: replay_provider,
            )
        )
    assert replay_provider.calls == []


@pytest.mark.parametrize(
    "fault_point", ["after_provider_dispatch", "after_provider_receipt"]
)
def test_crash_rolls_back_receipt_and_blocks_replay(
    app_paths, fault_point: str
) -> None:
    db, kernel, _clock, context = _started(app_paths, task_id="rtask_crash")
    provider = _NoNetworkProvider()

    def crash(point: str) -> None:
        if point == fault_point:
            raise SimulatedCrash(fault_point)

    wiring = ReceiptBoundProviderService(
        db=db,
        kernel=kernel,
        fault_injector=crash,
        provider_dispatch_authorized=True,
    )
    with pytest.raises(SimulatedCrash):
        _direct_query(
            wiring.factory(context=context, provider_factory=lambda _role: provider)
        )
    assert len(provider.calls) == 1
    task = kernel.get_task(context.task_id)
    assert task["side_effects"][0]["status"] == "in_flight"
    assert task["inner_actions"] == []
    assert not any(
        receipt["command_type"] == "provider_call_receipted"
        for receipt in task["command_receipts"]
    )
    replay_provider = _NoNetworkProvider()
    with pytest.raises(ProviderDispatchUnknown):
        _direct_query(
            ReceiptBoundProviderService(
                db=db, kernel=kernel, provider_dispatch_authorized=True
            ).factory(
                context=replace(
                    context,
                    expected_state_version=int(task["task"]["state_version"]),
                ),
                provider_factory=lambda _role: replay_provider,
            )
        )
    assert replay_provider.calls == []


def test_public_interrupt_fences_post_dispatch_commit(app_paths) -> None:
    db, kernel, _clock, context = _started(app_paths, task_id="rtask_control")
    control = ResearchControlService(db, kernel=kernel)
    provider = _NoNetworkProvider()

    def interrupt(point: str) -> None:
        if point != "after_provider_dispatch":
            return
        task = kernel.get_task(context.task_id)["task"]
        control.apply_control(
            context.task_id,
            ControlCommandRequest(
                command_id="interrupt:provider-race",
                kind="interrupt",
                expected_state_version=int(task["state_version"]),
                expected_checkpoint_id=None,
                expected_control_generation=int(task["control_generation"]),
                reason="mechanical owner/control fence race",
            ),
            principal_id="local_operator",
        )

    wiring = ReceiptBoundProviderService(
        db=db,
        kernel=kernel,
        fault_injector=interrupt,
        provider_dispatch_authorized=True,
    )
    with pytest.raises(ResearchConflict):
        _direct_query(
            wiring.factory(context=context, provider_factory=lambda _role: provider)
        )
    task = kernel.get_task(context.task_id)
    assert len(provider.calls) == 1
    assert task["task"]["owner_id"] is None
    assert task["task"]["control_generation"] == 1
    assert task["side_effects"][0]["status"] == "unknown"
    assert not any(
        receipt["command_type"] == "provider_call_receipted"
        for receipt in task["command_receipts"]
    )


def test_same_operation_payload_mismatch_fails_before_second_call(app_paths) -> None:
    db, kernel, _clock, context = _started(app_paths, task_id="rtask_mismatch")
    provider = _NoNetworkProvider()
    wiring = ReceiptBoundProviderService(
        db=db, kernel=kernel, provider_dispatch_authorized=True
    )
    first_factory = wiring.factory(
        context=context, provider_factory=lambda _role: provider
    )
    _direct_query(first_factory, "MCP")
    assert len(provider.calls) == 1

    mismatch_context = replace(
        context,
        expected_state_version=int(
            kernel.get_task(context.task_id)["task"]["state_version"]
        ),
    )
    with pytest.raises(ResearchConflict):
        _direct_query(
            wiring.factory(
                context=mismatch_context,
                provider_factory=lambda _role: provider,
            ),
            "different payload",
        )
    assert len(provider.calls) == 1
