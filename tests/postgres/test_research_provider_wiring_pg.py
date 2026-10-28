"""No-network providers exercise real PG intent, receipt and budget gates."""
import pytest
from datetime import datetime,timezone
from shiliu.research.service import ResearchTaskService
from shiliu.research.provider_wiring import ProviderCallContext,ProviderRunBudgetPolicy

@pytest.fixture
def provider_pg(collection_db,tmp_path,monkeypatch):
    import test_v5_a_stage5_gate_b_provider_wiring as original
    from shiliu.ask.evidence import TranscriptEvidenceMaterializer
    from shiliu.artifacts import ArtifactStore
    db=collection_db
    artifacts=ArtifactStore(tmp_path/"formal-provider",db)
    monkeypatch.setattr(original,"TranscriptEvidenceMaterializer",lambda db:TranscriptEvidenceMaterializer(db,artifacts))
    def started(paths,*,task_id="rtask_gate_b"):
        clock=original._MutableClock();clock.value=datetime.now(timezone.utc)
        kernel=ResearchTaskService(db,clock=clock)
        kernel.create_task(command_id=f"create:{task_id}",task_id=task_id,objective="MCP durable research",success_constraints=["use current evidence"],evidence_policy={})
        claimed=kernel.claim_owner(task_id=task_id,command_id=f"claim:{task_id}",owner_id="worker-a",expected_state_version=0,lease_seconds=60)
        attempt=kernel.start_attempt(task_id=task_id,command_id=f"start:{task_id}",owner_id="worker-a",owner_epoch=claimed["owner_epoch"],expected_state_version=1)
        context=ProviderCallContext(task_id=task_id,attempt_id=attempt["attempt_id"],owner_id="worker-a",owner_epoch=claimed["owner_epoch"],expected_state_version=2,expected_checkpoint_id=None,expected_control_generation=0,operation_key="gate-b-mechanical")
        return db,kernel,clock,context
    monkeypatch.setattr(original,"_started",started)
    def started_run(paths,*,policy_overrides=None):
        clock=original._MutableClock();clock.value=datetime.now(timezone.utc)
        kernel=ResearchTaskService(db,clock=clock)
        task_ids=tuple(f"rtask_gate_b_run_{index}" for index in range(3))
        policy=ProviderRunBudgetPolicy(run_id="GB-RUN-WIDE-NO-NETWORK",task_ids=task_ids,started_at=clock().isoformat(timespec="microseconds"),**(policy_overrides or {}))
        contexts=[]
        for index,task_id in enumerate(task_ids):
            kernel.create_task(command_id=f"run-create:{index}",task_id=task_id,objective=f"run-wide objective {index}",success_constraints=["bounded"],evidence_policy={"authority":"eval_snapshot_exact_replay","provider_run_budget":policy.evidence_policy_binding(case_id=f"CASE-{index}")})
            claim=kernel.claim_owner(task_id=task_id,command_id=f"run-claim:{index}",owner_id="run-worker",expected_state_version=0,lease_seconds=60)
            attempt=kernel.start_attempt(task_id=task_id,command_id=f"run-start:{index}",owner_id="run-worker",owner_epoch=claim["owner_epoch"],expected_state_version=1)
            contexts.append(ProviderCallContext(task_id=task_id,attempt_id=attempt["attempt_id"],owner_id="run-worker",owner_epoch=claim["owner_epoch"],expected_state_version=2,expected_checkpoint_id=None,expected_control_generation=0,operation_key=f"run-wide:{index}",max_logical_calls=7,max_http_attempts=14,max_input_tokens=60_000,max_output_tokens=14_192,run_budget=policy))
        return db,kernel,clock,policy,contexts
    monkeypatch.setattr(original,"_started_provider_run",started_run)
    return original

@pytest.mark.parametrize("contract",[
    "test_default_wiring_authority_is_disabled_without_any_factory_access",
    "test_default_absolute_fifty_cent_cap_blocks_before_factory",
    "test_run_wide_binding_mismatch_fails_before_transport",
    "test_run_wide_cost_cap_is_rebuilt_across_three_tasks",
    "test_run_wide_wall_cap_does_not_reset_on_restart",
    "test_known_invalid_output_is_receipted_once_then_uses_bounded_repair",
    "test_current_product_cap_allows_8192_without_changing_historical_default",
    "test_long_finish_summary_persists_raw_content_and_receipts_normalized_output",
    "test_invalid_agent_json_persists_raw_content_without_retry",
    "test_unknown_dispatch_is_durable_and_never_auto_replays",
    "test_public_interrupt_fences_post_dispatch_commit",
    "test_same_operation_payload_mismatch_fails_before_second_call",
    "test_missing_provider_operation_id_is_unknown_and_never_replayed",
])
def test_original_provider_contract_on_pg(provider_pg,app_paths,contract):
    getattr(provider_pg,contract)(app_paths)

@pytest.mark.parametrize("policy_overrides,error",[
    ({"max_logical_calls":2},"run-wide logical-call"),
    ({"max_http_attempts":3},"run-wide HTTP-attempt"),
    ({"max_output_tokens":1230},"run-wide output-token"),
])
def test_original_run_wide_reservation_on_pg(provider_pg,app_paths,policy_overrides,error):
    provider_pg.test_run_wide_meter_blocks_cross_task_reservation_and_survives_restart(app_paths,policy_overrides,error)

@pytest.mark.parametrize("fault_point",["after_provider_dispatch","after_provider_receipt"])
def test_original_receipt_crash_on_pg(provider_pg,app_paths,fault_point):
    provider_pg.test_crash_rolls_back_receipt_and_blocks_replay(app_paths,fault_point)


def test_original_three_structured_roles_and_free_replay_on_pg(provider_pg,app_paths):
    from dataclasses import replace
    from decimal import Decimal
    from test_v5_a_stage5_gate_b_provider_wiring import (
        _NoNetworkProvider,_deep_state,QueryAnalyzer,AgentDecisionService,
        DeepSearchBudget,GroundedAnswerService,ContextBuildResult,
        ReceiptBoundProviderService,PROVIDER_ACTION_SCHEMA_VERSION,
    )
    _started=provider_pg._started
    TranscriptEvidenceMaterializer=provider_pg.TranscriptEvidenceMaterializer
    db, kernel, _clock, context = _started(app_paths)
    provider = _NoNetworkProvider()
    wiring = ReceiptBoundProviderService(
        db=db,
        kernel=kernel,
        role_token_caps={"grounded_answer": 8192},
        provider_dispatch_authorized=True,
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
    durable=kernel.get_task(context.task_id)
    effects=durable["side_effects"]
    actions=[action for action in durable["inner_actions"] if action["action_schema_version"]==PROVIDER_ACTION_SCHEMA_VERSION]
    events=durable["events"]
    assert len(effects) == len(actions) == 3
    assert all(str(effect["status"]) == "succeeded" for effect in effects)
    assert all(effect["receipt_hash"] and effect["result_reference"] for effect in effects)
    for effect in effects:
        descriptor = effect["request"]
        assert descriptor["provider_identity"]["base_url"] == (
            "https://api.deepseek.com/v1"
        )
        assert descriptor["provider_identity"]["model"] == "deepseek-v4-pro"
    assert sum(row["event_type"] == "provider_call_receipted" for row in events) == 3
    for row in events:
        if row["event_type"] != "provider_call_receipted":
            continue
        binding = row["payload"]
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


def test_flash_receipt_reserves_and_replays_without_a_second_transport(provider_pg, app_paths):
    from dataclasses import replace
    from decimal import Decimal
    from shiliu.research.provider_wiring import ProviderPricePolicy, ReceiptBoundProviderService
    from test_v5_a_stage5_gate_b_provider_wiring import _NoNetworkProvider, _direct_query

    db, kernel, _, context = provider_pg._started(app_paths)
    policy = ProviderPricePolicy.deployed(base_url="https://api.deepseek.com/v1",
                                          model="deepseek-v4-flash")
    provider = _NoNetworkProvider()
    provider.model = "deepseek-v4-flash"
    service = ReceiptBoundProviderService(db=db, kernel=kernel, price_policy=policy,
                                          provider_dispatch_authorized=True)
    factory = service.factory(context=context, provider_factory=lambda role: provider.for_role(role))
    _direct_query(factory)
    effects = kernel.get_task(context.task_id)["side_effects"]
    assert len(effects) == 1 and effects[0]["status"] == "succeeded"
    assert effects[0]["request"]["price_table"]["pricing_basis"] == "published_peak_upper_bound_20261025"
    snapshot = service.budget_snapshot(context.task_id)
    assert Decimal(snapshot.committed_cost_usd) == policy.actual_cost(
        input_tokens=100, cached_input_tokens=10, output_tokens=20, transport_attempts=1)
    context = replace(context, expected_state_version=kernel.get_task(context.task_id)["task"]["state_version"])
    replay = service.factory(context=context, provider_factory=lambda role: provider.for_role(role))
    _direct_query(replay)
    assert len(provider.calls) == 1



def test_concurrent_run_wide_limit_counts_in_flight_reservation(provider_pg,app_paths):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from shiliu.research.provider_wiring import ReceiptBoundProviderService,ProviderBudgetExceeded
    db,kernel,clock,policy,contexts=provider_pg._started_provider_run(app_paths,policy_overrides={"max_logical_calls":1})
    wiring=ReceiptBoundProviderService(db=db,kernel=kernel,provider_dispatch_authorized=True)
    dispatched=threading.Event();release=threading.Event()
    first=provider_pg._NoNetworkProvider();second=provider_pg._NoNetworkProvider()
    def first_factory(role):
        dispatched.set()
        assert release.wait(5),"test did not release the transaction-free provider boundary"
        return first.for_role(role)
    with ThreadPoolExecutor(max_workers=2) as workers:
        future=workers.submit(provider_pg._direct_query,wiring.factory(context=contexts[0],provider_factory=first_factory))
        assert dispatched.wait(3)
        try:
            # The first task has released the DB transaction and is in_flight;
            # another task must count that durable reservation before dispatch.
            with pytest.raises(ProviderBudgetExceeded):provider_pg._direct_query(wiring.factory(context=contexts[1],provider_factory=lambda role:second.for_role(role)))
            assert second.calls==[]
            snapshot=wiring.run_budget_snapshot(policy)
            assert snapshot.active_logical_reservations==1
        finally:release.set()
        result=future.result(timeout=5)
    assert result.receipt_binding["receipt_hash"] and len(first.calls)==1
    snapshot=wiring.run_budget_snapshot(policy)
    assert snapshot.committed_logical_calls==1 and snapshot.active_logical_reservations==0
