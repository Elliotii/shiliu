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
from shiliu.research.errors import (
    ResearchConflict,
    ResearchValidationError,
    SimulatedCrash,
)
from shiliu.research.provider_wiring import (
    PROVIDER_ACTION_SCHEMA_VERSION,
    ProviderBudgetExceeded,
    ProviderCallFailed,
    ProviderCallContext,
    ProviderDispatchUnknown,
    ProviderPricePolicy,
    ProviderRunBudgetPolicy,
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
    name = "openai-compatible"

    def __init__(
        self,
        *,
        fail: Exception | None = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-v4-pro",
        thinking_enabled: bool = False,
        reasoning_effort: str | None = None,
        lock_role_identity: bool = False,
    ) -> None:
        self.fail = fail
        self.base_url = base_url
        self.model = model
        self.thinking_enabled = thinking_enabled
        self.reasoning_effort = reasoning_effort
        self.lock_role_identity = lock_role_identity
        self.calls: list[dict[str, object]] = []

    def for_role(self, role: str):
        if not self.lock_role_identity:
            self.thinking_enabled = role == "grounded_answer"
            self.reasoning_effort = "high" if self.thinking_enabled else None
        return self

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


class _MissingResponseIdProvider(_NoNetworkProvider):
    def generate_structured(self, **kwargs):
        reply = super().generate_structured(**kwargs)
        reply.response_id = ""
        return reply


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


def _started_provider_run(app_paths, *, policy_overrides=None):
    db = Database(app_paths.database)
    db.initialize()
    clock = _MutableClock()
    kernel = ResearchTaskService(db, clock=clock)
    task_ids = tuple(f"rtask_gate_b_run_{index}" for index in range(3))
    policy = ProviderRunBudgetPolicy(
        run_id="GB-RUN-WIDE-NO-NETWORK",
        task_ids=task_ids,
        started_at=clock().isoformat(timespec="microseconds"),
        **(policy_overrides or {}),
    )
    contexts = []
    for index, task_id in enumerate(task_ids):
        kernel.create_task(
            command_id=f"run-create:{index}",
            task_id=task_id,
            objective=f"run-wide objective {index}",
            success_constraints=["bounded"],
            evidence_policy={
                "authority": "eval_snapshot_exact_replay",
                "provider_run_budget": policy.evidence_policy_binding(
                    case_id=f"CASE-{index}"
                ),
            },
        )
        claim = kernel.claim_owner(
            task_id=task_id,
            command_id=f"run-claim:{index}",
            owner_id="run-worker",
            expected_state_version=0,
            lease_seconds=3600,
        )
        attempt = kernel.start_attempt(
            task_id=task_id,
            command_id=f"run-start:{index}",
            owner_id="run-worker",
            owner_epoch=int(claim["owner_epoch"]),
            expected_state_version=1,
        )
        contexts.append(
            ProviderCallContext(
                task_id=task_id,
                attempt_id=str(attempt["attempt_id"]),
                owner_id="run-worker",
                owner_epoch=int(claim["owner_epoch"]),
                expected_state_version=2,
                expected_checkpoint_id=None,
                expected_control_generation=0,
                operation_key=f"run-wide:{index}",
                max_logical_calls=7,
                max_http_attempts=14,
                max_input_tokens=60_000,
                max_output_tokens=14_192,
                run_budget=policy,
            )
        )
    return db, kernel, clock, policy, contexts


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
                context=context, provider_factory=lambda role: provider.for_role(role)
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
        context=context, provider_factory=lambda role: provider.for_role(role)
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
    for effect in effects:
        descriptor = json.loads(str(effect["request_json"]))
        assert descriptor["provider_identity"]["base_url"] == (
            "https://api.deepseek.com/v1"
        )
        assert descriptor["provider_identity"]["model"] == "deepseek-v4-pro"
    assert sum(row["event_type"] == "provider_call_receipted" for row in events) == 3
    for row in events:
        if row["event_type"] != "provider_call_receipted":
            continue
        binding = json.loads(str(row["payload_json"]))
        assert binding["provider"] == "deepseek_openai_compatible"
        assert binding["model"] == "deepseek-v4-pro"
        assert binding["provider_identity"] == {
            "provider_protocol": "openai-compatible",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-v4-pro",
            "role": binding["role"],
            "thinking_enabled": binding["role"] == "grounded_answer",
            "reasoning_effort": (
                "high" if binding["role"] == "grounded_answer" else None
            ),
        }
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
        provider_factory=lambda role: replay_provider.for_role(role),
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
        wiring.factory(
            context=context, provider_factory=lambda role: provider.for_role(role)
        )
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
        provider_factory=lambda role: blocked_provider.for_role(role),
    )
    with pytest.raises(ProviderBudgetExceeded):
        _direct_query(blocked_factory)
    with pytest.raises(ProviderBudgetExceeded):
        _direct_query(
            restarted.factory(
                context=blocked_context,
                provider_factory=lambda role: blocked_provider.for_role(role),
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
                context=context, provider_factory=lambda role: provider.for_role(role)
            ),
            "x" * 300_000,
        )
    assert provider.calls == []
    task = kernel.get_task(context.task_id)
    assert task["side_effects"] == []
    assert task["inner_actions"] == []


@pytest.mark.parametrize(
    "policy_overrides,error",
    [
        ({"max_logical_calls": 2}, "run-wide logical-call"),
        ({"max_http_attempts": 3}, "run-wide HTTP-attempt"),
        ({"max_output_tokens": 1230}, "run-wide output-token"),
    ],
)
def test_run_wide_meter_blocks_cross_task_reservation_and_survives_restart(
    app_paths, policy_overrides, error: str
) -> None:
    db, kernel, _clock, policy, contexts = _started_provider_run(
        app_paths, policy_overrides=policy_overrides
    )
    provider = _NoNetworkProvider()
    wiring = ReceiptBoundProviderService(
        db=db, kernel=kernel, provider_dispatch_authorized=True
    )
    for context in contexts[:2]:
        _direct_query(
            wiring.factory(
                context=context,
                provider_factory=lambda role: provider.for_role(role),
            )
        )
    before = wiring.run_budget_snapshot(policy)
    assert before.committed_logical_calls == 2
    assert before.active_logical_reservations == 0

    restarted = ReceiptBoundProviderService(
        db=db, kernel=kernel, provider_dispatch_authorized=True
    )
    assert restarted.run_budget_snapshot(policy) == before
    blocked = _NoNetworkProvider()
    with pytest.raises(ProviderBudgetExceeded, match=error):
        _direct_query(
            restarted.factory(
                context=contexts[2],
                provider_factory=lambda role: blocked.for_role(role),
            )
        )
    with pytest.raises(ProviderBudgetExceeded, match=error):
        _direct_query(
            restarted.factory(
                context=contexts[2],
                provider_factory=lambda role: blocked.for_role(role),
            )
        )
    assert blocked.calls == []
    assert restarted.run_budget_snapshot(policy) == before
    task = kernel.get_task(contexts[2].task_id)
    rejected = [
        receipt
        for receipt in task["command_receipts"]
        if receipt["command_type"] == "provider_call_budget_rejected"
    ]
    assert len(rejected) == 1

    replay_provider = _NoNetworkProvider()
    replay_context = replace(
        contexts[0],
        expected_state_version=int(
            kernel.get_task(contexts[0].task_id)["task"]["state_version"]
        ),
    )
    replay = _direct_query(
        restarted.factory(
            context=replay_context,
            provider_factory=lambda role: replay_provider.for_role(role),
        )
    )
    assert replay.deduplicated is True
    assert replay_provider.calls == []
    assert restarted.run_budget_snapshot(policy) == before


def test_run_wide_binding_mismatch_fails_before_transport(app_paths) -> None:
    db, kernel, _clock, policy, contexts = _started_provider_run(app_paths)
    tampered = replace(policy, max_logical_calls=16)
    context = replace(contexts[0], run_budget=tampered)
    provider = _NoNetworkProvider()
    wiring = ReceiptBoundProviderService(
        db=db, kernel=kernel, provider_dispatch_authorized=True
    )
    with pytest.raises(ResearchValidationError, match="does not match"):
        _direct_query(
            wiring.factory(
                context=context,
                provider_factory=lambda role: provider.for_role(role),
            )
        )
    assert provider.calls == []
    assert wiring.run_budget_snapshot(policy).accounted_logical_calls == 0


def test_run_wide_cost_cap_is_rebuilt_across_three_tasks(
    app_paths,
) -> None:
    db, kernel, clock, policy, contexts = _started_provider_run(
        app_paths,
        policy_overrides={
            "reserve_stop_usd": Decimal("0.0060"),
            "absolute_max_cost_usd": Decimal("0.00605"),
            "max_wall_seconds": 10,
        },
    )
    provider = _NoNetworkProvider()
    wiring = ReceiptBoundProviderService(
        db=db, kernel=kernel, provider_dispatch_authorized=True
    )
    for context in contexts:
        _direct_query(
            wiring.factory(
                context=context,
                provider_factory=lambda role: provider.for_role(role),
            )
        )
    snapshot = wiring.run_budget_snapshot(policy)
    assert snapshot.committed_logical_calls == 3
    assert Decimal(snapshot.committed_cost_usd) > 0

    next_context = replace(
        contexts[0],
        expected_state_version=int(
            kernel.get_task(contexts[0].task_id)["task"]["state_version"]
        ),
        operation_key="run-wide:cost-block",
    )
    blocked = _NoNetworkProvider()
    with pytest.raises(ProviderBudgetExceeded, match="run-wide worst-case cost"):
        _direct_query(
            wiring.factory(
                context=next_context,
                provider_factory=lambda role: blocked.for_role(role),
            )
        )
    assert blocked.calls == []


def test_run_wide_wall_cap_does_not_reset_on_restart(app_paths) -> None:
    db, kernel, clock, policy, contexts = _started_provider_run(
        app_paths,
        policy_overrides={"max_wall_seconds": 10},
    )
    clock.advance(10)
    restarted = ReceiptBoundProviderService(
        db=db, kernel=kernel, provider_dispatch_authorized=True
    )
    blocked = _NoNetworkProvider()
    with pytest.raises(ProviderBudgetExceeded, match="wall-time"):
        _direct_query(
            restarted.factory(
                context=contexts[0],
                provider_factory=lambda role: blocked.for_role(role),
            )
        )
    assert blocked.calls == []
    assert restarted.run_budget_snapshot(policy).accounted_logical_calls == 0


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
            context=context, provider_factory=lambda role: provider.for_role(role)
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
        context=context, provider_factory=lambda role: failing.for_role(role)
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
                provider_factory=lambda role: replay_provider.for_role(role),
            )
        )
    with pytest.raises(ProviderDispatchUnknown):
        _direct_query(
            wiring.factory(
                context=replace(
                    replay_context, operation_key="different-provider-operation"
                ),
                provider_factory=lambda role: replay_provider.for_role(role),
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
            wiring.factory(
                context=context,
                provider_factory=lambda role: provider.for_role(role),
            )
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
                provider_factory=lambda role: replay_provider.for_role(role),
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
            wiring.factory(
                context=context,
                provider_factory=lambda role: provider.for_role(role),
            )
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
        context=context, provider_factory=lambda role: provider.for_role(role)
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
                provider_factory=lambda role: provider.for_role(role),
            ),
            "different payload",
        )
    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    "overrides, mismatch_field",
    [
        ({"model": "deepseek-unapproved"}, "model"),
        ({"base_url": "https://unapproved.example/v1"}, "base_url"),
        (
            {
                "thinking_enabled": True,
                "reasoning_effort": "high",
            },
            "thinking_enabled",
        ),
    ],
)
def test_actual_provider_identity_mismatch_is_rejected_before_transport(
    app_paths, overrides: dict[str, object], mismatch_field: str
) -> None:
    db, kernel, _clock, context = _started(
        app_paths, task_id=f"rtask_identity_{mismatch_field}"
    )
    provider = _NoNetworkProvider(lock_role_identity=True, **overrides)
    wiring = ReceiptBoundProviderService(
        db=db, kernel=kernel, provider_dispatch_authorized=True
    )
    with pytest.raises(ProviderCallFailed, match="runtime identity"):
        _direct_query(
            wiring.factory(
                context=context,
                provider_factory=lambda _role: provider,
            )
        )
    assert provider.calls == []
    task = kernel.get_task(context.task_id)
    assert task["side_effects"][0]["status"] == "failed"
    assert task["side_effects"][0]["receipt_hash"] is None
    assert task["inner_actions"][0]["status"] == "rejected"
    assert task["inner_actions"][0]["error_code"] == "provider_identity_mismatch"
    rejected = [
        event for event in task["events"]
        if event["event_type"] == "provider_identity_rejected"
    ]
    assert len(rejected) == 1
    payload = rejected[0]["payload"]
    assert mismatch_field in payload["identity_mismatches"]
    assert payload["transport_calls"] == 0

    replay_provider = _NoNetworkProvider()
    replay_context = replace(
        context,
        expected_state_version=int(task["task"]["state_version"]),
    )
    with pytest.raises(ProviderCallFailed, match="identity mismatch"):
        _direct_query(
            wiring.factory(
                context=replay_context,
                provider_factory=lambda role: replay_provider.for_role(role),
            )
        )
    assert replay_provider.calls == []


def test_missing_provider_operation_id_is_unknown_and_never_replayed(
    app_paths,
) -> None:
    db, kernel, _clock, context = _started(
        app_paths, task_id="rtask_missing_operation_id"
    )
    provider = _MissingResponseIdProvider()
    wiring = ReceiptBoundProviderService(
        db=db, kernel=kernel, provider_dispatch_authorized=True
    )
    with pytest.raises(ProviderDispatchUnknown, match="identity is missing"):
        _direct_query(
            wiring.factory(
                context=context,
                provider_factory=lambda role: provider.for_role(role),
            )
        )
    assert len(provider.calls) == 1
    task = kernel.get_task(context.task_id)
    assert task["task"]["status"] == "blocked"
    assert task["side_effects"][0]["status"] == "unknown"
    assert task["side_effects"][0]["provider_operation_id"] is None
    assert task["side_effects"][0]["receipt_hash"] is None
    assert task["inner_actions"][0]["status"] == "unknown"
    assert not any(
        receipt["command_type"] == "provider_call_receipted"
        for receipt in task["command_receipts"]
    )

    replay_provider = _NoNetworkProvider()
    replay_context = replace(
        context,
        expected_state_version=int(task["task"]["state_version"]),
    )
    with pytest.raises(ProviderDispatchUnknown):
        _direct_query(
            wiring.factory(
                context=replay_context,
                provider_factory=lambda role: replay_provider.for_role(role),
            )
        )
    assert replay_provider.calls == []
