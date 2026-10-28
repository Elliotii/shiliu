"""Original operational-control assertions on scoped PG kernel transactions."""
from types import SimpleNamespace
import pytest
from shiliu.research.service import ResearchTaskService
from shiliu.research.control_service import ResearchControlService


def bootstrap_pg(core,task_id="control-task"):
    kernel=core.research
    kernel.create_task(command_id=f"{task_id}:create",task_id=task_id,objective="研究可恢复控制",
        success_constraints=["保持历史不可变"],evidence_policy={"authority":"live_current_exact_replay"})
    claim=kernel.claim_owner(task_id=task_id,command_id=f"{task_id}:claim",owner_id="worker-a",expected_state_version=0,lease_seconds=60)
    attempt=kernel.start_attempt(task_id=task_id,command_id=f"{task_id}:start",owner_id="worker-a",owner_epoch=claim["owner_epoch"],expected_state_version=claim["state_version"])
    checkpoint=kernel.commit_checkpoint(task_id=task_id,attempt_id=attempt["attempt_id"],command_id=f"{task_id}:checkpoint",owner_id="worker-a",owner_epoch=claim["owner_epoch"],expected_state_version=attempt["state_version"],expected_checkpoint_id=None,state_payload={"phase":"durable","budget":{"actions":1}})
    return dict(task_id=task_id,owner_id="worker-a",owner_epoch=claim["owner_epoch"],attempt_id=attempt["attempt_id"],checkpoint_id=checkpoint["checkpoint_id"],state_version=checkpoint["state_version"])


@pytest.mark.parametrize("contract",[
    "test_interrupt_fences_stale_worker_and_resume_keeps_attempt_and_budget",
    "test_control_replay_payload_mismatch_and_fault_rollback",
    "test_cancel_pending_unknown_requires_immutable_resolution_and_never_replays",
    "test_replay_and_branch_create_isolated_children_without_tool_or_effect_replay",
    "test_audit_metadata_cannot_upgrade_restricted_server_principal",
    "test_cancel_reserved_effect_prevents_execution_and_terminalizes",
    "test_bounds_fail_closed_before_any_persistent_mutation",
    "test_derivation_fault_rolls_back_child_and_source_remains_immutable",
    "test_derived_child_can_be_claimed_and_resumed_without_source_mutation",
    "test_current_interrupt_resume_is_exact_once_and_consumed",
    "test_interrupt_unknown_resolution_preserves_current_resume_lineage",
])
def test_original_control_contract_on_pg(collection_db,app_paths,monkeypatch,contract):
    import test_v5_a_stage4_operational_control as original
    kernel=ResearchTaskService(collection_db)
    claim_owner=kernel.claim_owner
    def claim_fixture(**kwargs):
        # Historical test helpers requested 300s. PG authorization remains on
        # the server clock with the approved maximum 60s lease.
        if kwargs.get("lease_seconds")==300:kwargs["lease_seconds"]=60
        return claim_owner(**kwargs)
    monkeypatch.setattr(kernel,"claim_owner",claim_fixture)
    core=SimpleNamespace(paths=app_paths,db=collection_db,research=kernel,research_control=ResearchControlService(collection_db,kernel=kernel))
    monkeypatch.setattr(original,"Application",lambda paths:core)
    monkeypatch.setattr(original,"_bootstrap",bootstrap_pg)
    getattr(original,contract)(app_paths)


def test_human_clarification_native_json_time_and_atomic_replay(collection_db):
    from shiliu.research.control_contracts import CreateInputRequest,HumanDecisionRequest
    from shiliu.research.errors import ResearchConflict,SimulatedCrash
    db=collection_db
    kernel=ResearchTaskService(db)
    control=ResearchControlService(db,kernel=kernel)
    core=SimpleNamespace(research=kernel)
    run=bootstrap_pg(core,"clarify-pg")
    with kernel._transaction() as conn:
        kernel._task(conn,run["task_id"])
        conn.execute("UPDATE research_tasks SET status='waiting_user' WHERE workspace_id=%s AND owner_user_id=%s AND task_id=%s",(db.workspace_id,db.context.user_id,run["task_id"]))
        conn.execute("UPDATE research_attempts SET status='waiting_user' WHERE workspace_id=%s AND task_id=%s AND attempt_id=%s",(db.workspace_id,run["task_id"],run["attempt_id"]))
    opened=control.create_input(run["task_id"],CreateInputRequest(command_id="open",attempt_id=run["attempt_id"],owner_id=run["owner_id"],owner_epoch=run["owner_epoch"],expected_state_version=run["state_version"],expected_checkpoint_id=run["checkpoint_id"],kind="clarification",prompt="澄清目标"),principal_id=db.context.user_id)
    request=HumanDecisionRequest(command_id="decide",input_request_id=opened["input_request_id"],expected_state_version=opened["state_version"],expected_control_generation=0,decision_kind="clarify_goal",response={"objective":"研究持久血缘","success_constraints":["保留来源"],"evidence_policy":{"authority":"live_current_exact_replay"}})
    before=kernel.get_task(run["task_id"])
    def fault(point):
        if point=="after_human_decision_apply":raise SimulatedCrash(point)
    control.fault_injector=fault
    with pytest.raises(SimulatedCrash):control.decide_input(run["task_id"],request,principal_id=db.context.user_id)
    assert kernel.get_task(run["task_id"])==before
    control.fault_injector=lambda point:None
    outcome=control.decide_input(run["task_id"],request,principal_id=db.context.user_id)
    replay=ResearchControlService(db,kernel=kernel).decide_input(run["task_id"],request,principal_id=db.context.user_id)
    assert replay["deduplicated"] and replay["decision_id"]==outcome["decision_id"]
    state=kernel.get_task(run["task_id"])
    assert [g["revision"] for g in state["goals"]]==[1,2]
    assert state["attempts"][1]["parent_attempt_id"]==run["attempt_id"]
    assert state["attempts"][1]["cause"]=="goal_revision"
    assert state["results"][0]["termination_reason"]=="goal_revised"
    with pytest.raises(ResearchConflict):control.decide_input(run["task_id"],request.model_copy(update={"response":{"objective":"tampered"}}),principal_id=db.context.user_id)
    status=control.get_status(run["task_id"])
    assert status["open_input_requests"]==[]
    assert isinstance(status["human_decisions"][0]["response"],dict)
    assert isinstance(status["human_decisions"][0]["created_at"],str)
