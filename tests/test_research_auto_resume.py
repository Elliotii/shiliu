from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import time
from unittest.mock import patch

import pytest

from shiliu.db import Database
from shiliu.app import Application
from shiliu.research.product_contracts import CreateProductResearchRequest
from shiliu.research.recovery import ResearchRecoveryCoordinator
from shiliu.research.provider_wiring import ProviderRunBudgetPolicy
from shiliu.research.errors import ResearchUnsafeState
from shiliu.research.execution import ResearchExecutionLedger
from shiliu.research.schema import RESEARCH_ACTIVE_TIME_POLICY_VERSION
from shiliu.research.service import ResearchTaskService
from shiliu.retrieval.qwen import LocalModelNotReadyError


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 20, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


def _ledger(app_paths, *, budget_ms: int = 360_000):
    db = Database(app_paths.database)
    db.initialize()
    clock = MutableClock()
    kernel = ResearchTaskService(db, clock=clock)
    task_id = "rtask_active_time_test"
    metadata = {
        "time_policy_version": RESEARCH_ACTIVE_TIME_POLICY_VERSION,
        "active_budget_ms": budget_ms,
        "scheduling_intent": "queued",
        "scheduling_status": "queued",
        "run_command_id": "run:test",
        "resume_reason": "test",
    }
    kernel.create_task(
        command_id="create:test",
        task_id=task_id,
        objective="test active time",
        _execution_metadata=metadata,
    )
    claimed = kernel.claim_owner(
        task_id=task_id,
        command_id="claim:one",
        owner_id="owner-one",
        expected_state_version=0,
        lease_seconds=60,
    )
    return (
        clock,
        kernel,
        ResearchExecutionLedger(db, kernel),
        task_id,
        int(claimed["owner_epoch"]),
    )


def test_long_blocking_call_ticks_full_elapsed_not_five_second_cap(app_paths) -> None:
    _clock, kernel, ledger, task_id, epoch = _ledger(app_paths)
    state_version = kernel.get_task(task_id)["task"]["state_version"]
    segment_id, started = ledger.begin_segment(
        task_id=task_id, owner_id="owner-one", owner_epoch=epoch
    )
    assert started.reserved_tail_ms == 5_000

    at_five = ledger.tick(
        task_id=task_id,
        owner_id="owner-one",
        owner_epoch=epoch,
        segment_id=segment_id,
        elapsed_ms=5_000,
    )
    at_ninety = ledger.tick(
        task_id=task_id,
        owner_id="owner-one",
        owner_epoch=epoch,
        segment_id=segment_id,
        elapsed_ms=90_000,
    )
    settled = ledger.settle(
        task_id=task_id,
        owner_id="owner-one",
        owner_epoch=epoch,
        segment_id=segment_id,
        elapsed_ms=90_000,
    )

    assert at_five.consumed_active_ms == 5_000
    assert at_ninety.consumed_active_ms == 90_000
    assert settled.consumed_active_ms == 90_000
    assert settled.reserved_tail_ms == 0
    assert kernel.get_task(task_id)["task"]["state_version"] == state_version


def test_offline_time_is_free_and_crash_tail_settles_once(app_paths) -> None:
    clock, kernel, ledger, task_id, epoch = _ledger(app_paths)
    segment_id, _ = ledger.begin_segment(
        task_id=task_id, owner_id="owner-one", owner_epoch=epoch
    )
    ledger.tick(
        task_id=task_id,
        owner_id="owner-one",
        owner_epoch=epoch,
        segment_id=segment_id,
        elapsed_ms=40_000,
    )
    clock.advance(6 * 60 * 60)
    task = kernel.get_task(task_id)["task"]
    claimed = kernel.claim_owner(
        task_id=task_id,
        command_id="claim:two",
        owner_id="owner-two",
        expected_state_version=int(task["state_version"]),
        lease_seconds=60,
    )
    new_epoch = int(claimed["owner_epoch"])
    replacement, recovered = ledger.begin_segment(
        task_id=task_id, owner_id="owner-two", owner_epoch=new_epoch
    )
    same_segment, repeated = ledger.begin_segment(
        task_id=task_id, owner_id="owner-two", owner_epoch=new_epoch
    )

    assert recovered.consumed_active_ms == 45_000
    assert repeated.consumed_active_ms == 45_000
    assert replacement == same_segment


def test_sleep_is_not_charged_and_uncertain_interval_stops_auto_run(app_paths) -> None:
    _clock, _kernel, ledger, task_id, epoch = _ledger(app_paths)
    segment_id, _ = ledger.begin_segment(
        task_id=task_id, owner_id="owner-one", owner_epoch=epoch
    )
    slept = ledger.tick(
        task_id=task_id,
        owner_id="owner-one",
        owner_epoch=epoch,
        segment_id=segment_id,
        elapsed_ms=0,
        interval_classification="sleep",
    )
    uncertain = ledger.tick(
        task_id=task_id,
        owner_id="owner-one",
        owner_epoch=epoch,
        segment_id=segment_id,
        elapsed_ms=0,
        interval_classification="uncertain",
    )

    assert slept.consumed_active_ms == 0
    assert uncertain.timing_status == "uncertain"
    assert uncertain.scheduling_status == "manual_required"
    with pytest.raises(ResearchUnsafeState, match="uncertain"):
        ledger.enqueue(
            task_id,
            command_id="manual:unsafe",
            manual=True,
            reason="must_not_bypass",
        )


def test_legacy_task_does_not_receive_an_implicit_budget(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    kernel = ResearchTaskService(db)
    created = kernel.create_task(command_id="legacy:create", objective="legacy")
    ledger = ResearchExecutionLedger(db, kernel)

    assert ledger.snapshot(str(created["task_id"]), required=False) is None
    with pytest.raises(ResearchUnsafeState, match="legacy_time_unaccounted"):
        ledger.enqueue(
            str(created["task_id"]),
            command_id="legacy:run",
            manual=True,
            reason="legacy",
        )


def test_supervisor_persists_time_while_provider_thread_is_blocked(app_paths) -> None:
    core = Application(app_paths)
    created = core.research_provider_product.create_provider_task(
        CreateProductResearchRequest(
            command_id="supervised:create",
            objective="supervised blocking call",
            run_immediately=True,
        )
    )
    task_id = str(created["task_id"])

    class BlockingOrchestrator:
        _run_lock = object()

        def run_to_boundary(self, _task_id: str, **_kwargs):
            time.sleep(0.08)
            return {"boundary": "test"}

    core._research_provider_orchestrator = BlockingOrchestrator()
    core.provider_research_availability = lambda: {
        "available": True,
        "reason": "test",
    }
    coordinator = ResearchRecoveryCoordinator(core)
    coordinator.TICK_SECONDS = 0.01
    coordinator.LEASE_RENEW_SECONDS = 0.02
    coordinator.LEASE_SECONDS = 1

    assert coordinator.run_once() == task_id
    snapshot = coordinator.ledger.snapshot(task_id)
    raw = core.research.get_task(task_id)

    assert snapshot is not None
    assert snapshot.consumed_active_ms >= 50
    assert snapshot.consumed_active_ms < 500
    assert snapshot.reserved_tail_ms == 0
    assert not any(
        event["event_type"] == "owner_renewed" for event in raw["events"]
    )


def test_v1_budget_manifest_and_hash_remain_byte_contract_compatible() -> None:
    policy = ProviderRunBudgetPolicy(
        run_id="legacy-run",
        task_ids=("legacy-task",),
        started_at="2026-09-20T00:00:00+00:00",
    )

    assert "time_policy_version" not in policy.manifest()
    assert policy.evidence_policy_binding(case_id="legacy")["policy_hash"] == (
        policy.policy_hash
    )


def test_provider_create_replay_keeps_same_v2_metadata_contract(app_paths) -> None:
    core = Application(app_paths)
    request = CreateProductResearchRequest(
        command_id="v2-create-replay",
        objective="idempotent v2 create",
        run_immediately=False,
    )

    first = core.research_provider_product.create_provider_task(request)
    second = core.research_provider_product.create_provider_task(request)

    assert first == second
    snapshot = core.research_provider_product.execution.snapshot(
        str(first["task_id"])
    )
    assert snapshot is not None
    assert snapshot.time_policy_version == RESEARCH_ACTIVE_TIME_POLICY_VERSION


def test_research_provider_disables_inner_transport_retry_only(app_paths) -> None:
    core = Application(app_paths)
    core.config = replace(core.config, llm_model="test-model")
    with patch("shiliu.app.load_api_key", return_value="test-secret"):
        provider = core.research_provider("query_analysis")

    assert provider.structured_transport_retries == 0


def test_provider_research_stops_before_paid_call_when_dense_runtime_is_unready(
    app_paths,
) -> None:
    core = Application(app_paths)
    core.config = replace(
        core.config,
        llm_base_url="https://api.deepseek.com/v1",
        llm_model="deepseek-v4-pro",
    )

    class UnreadyDenseIndex:
        def search(self, *_args, **_kwargs):
            raise LocalModelNotReadyError("qwen runtime missing")

    core._dense_retrieval = UnreadyDenseIndex()
    with patch("shiliu.app.load_api_key", return_value="test-secret"):
        first = core.provider_research_availability()
        second = core.provider_research_availability()

    assert first == second
    assert first["available"] is False
    assert "Provider 调用前停止" in str(first["reason"])


def test_provider_research_readiness_probe_is_cached(app_paths) -> None:
    core = Application(app_paths)
    core.config = replace(
        core.config,
        llm_base_url="https://api.deepseek.com/v1",
        llm_model="deepseek-v4-pro",
    )

    class ReadyDenseIndex:
        def __init__(self) -> None:
            self.calls = 0

        def search(self, *_args, **_kwargs):
            self.calls += 1
            return []

    dense = ReadyDenseIndex()
    core._dense_retrieval = dense
    with patch("shiliu.app.load_api_key", return_value="test-secret"):
        first = core.provider_research_availability()
        second = core.provider_research_availability()

    assert first["available"] is True
    assert second == first
    assert dense.calls == 1


def test_retry_backoff_is_finite_persistent_and_manual_keeps_lifetime_count(
    app_paths,
) -> None:
    clock, _kernel, ledger, task_id, _epoch = _ledger(app_paths)

    first = ledger.record_failure(task_id, code="database_busy", safe_to_retry=True)
    clock.advance(5)
    second = ledger.record_failure(task_id, code="database_busy", safe_to_retry=True)
    clock.advance(30)
    stopped = ledger.record_failure(task_id, code="database_busy", safe_to_retry=True)
    manual = ledger.enqueue(
        task_id,
        command_id="manual:new-round",
        manual=True,
        reason="manual_continue_requested",
    )

    assert first.scheduling_status == "backoff"
    assert first.automatic_failure_count == 1
    assert second.scheduling_status == "backoff"
    assert second.automatic_failure_count == 2
    assert stopped.scheduling_status == "manual_required"
    assert stopped.next_retry_at is None
    assert stopped.lifetime_automatic_failure_count == 3
    assert manual.automatic_failure_count == 0
    assert manual.lifetime_automatic_failure_count == 3
    assert manual.manual_generation == 1
