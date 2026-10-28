"""Real PG owner fencing with the original bounded active-time ledger."""
import pytest

from shiliu.research.service import ResearchTaskService
from shiliu.research.execution import ResearchExecutionLedger
from shiliu.research.schema import RESEARCH_ACTIVE_TIME_POLICY_VERSION
from shiliu.research import ResearchConflict
from test_v5_a_stage1_research_kernel import claim,start


def test_crash_tail_is_charged_once_and_sleep_never_counts(collection_db):
    service=ResearchTaskService(collection_db)
    service.create_task(command_id="active-create",task_id="active-task",objective="synthetic",_execution_metadata={
        "time_policy_version":RESEARCH_ACTIVE_TIME_POLICY_VERSION,"active_budget_ms":100000,
        "scheduling_intent":"queued","scheduling_status":"queued","run_command_id":"run","resume_reason":None})
    claim(service,"active-task");start(service,"active-task")
    ledger=ResearchExecutionLedger(collection_db,service,reservation_ms=5000)
    segment,initial=ledger.begin_segment(task_id="active-task",owner_id="worker-a",owner_epoch=1)
    assert initial.consumed_active_ms==0 and initial.reserved_tail_ms==5000
    running=ledger.tick(task_id="active-task",owner_id="worker-a",owner_epoch=1,segment_id=segment,elapsed_ms=3000)
    assert running.consumed_active_ms==3000
    sleeping=ledger.tick(task_id="active-task",owner_id="worker-a",owner_epoch=1,segment_id=segment,elapsed_ms=999999,interval_classification="sleep")
    assert sleeping.consumed_active_ms==3000
    with collection_db.connect() as conn:
        conn.execute("UPDATE shiliu.research_tasks SET lease_until=clock_timestamp()-interval '1 second' WHERE task_id='active-task'")
    claim(service,"active-task",command_id="takeover",owner_id="worker-b",expected=2)
    segment2,recovered=ledger.begin_segment(task_id="active-task",owner_id="worker-b",owner_epoch=2)
    assert recovered.consumed_active_ms==8000
    assert ledger.begin_segment(task_id="active-task",owner_id="worker-b",owner_epoch=2)[0]==segment2
    assert ledger.snapshot("active-task").consumed_active_ms==8000
    with pytest.raises(ResearchConflict):
        ledger.settle(task_id="active-task",owner_id="worker-a",owner_epoch=1,segment_id=segment,elapsed_ms=4000)
    final=ledger.settle(task_id="active-task",owner_id="worker-b",owner_epoch=2,segment_id=segment2,elapsed_ms=2000)
    assert final.consumed_active_ms==10000 and final.reserved_tail_ms==0 and final.segment_id is None
    assert ledger.snapshot("active-task").consumed_active_ms==10000
    assert ledger.renew_lease_only(task_id="active-task",owner_id="worker-b",owner_epoch=2,lease_seconds=60)
