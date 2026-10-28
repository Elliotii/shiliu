"""Research kernel migration: reuse original commands against real PG."""
import pytest

from shiliu.research.service import ResearchTaskService
from shiliu.research import ResearchConflict,AnswerStatus,TerminationReason,FailureClass
from test_v5_a_stage1_research_kernel import create_task,claim,start,bootstrap


def test_research_create_replay_and_mismatch_audit_survive_rollback(collection_db):
    service=ResearchTaskService(collection_db)
    created=create_task(service)
    assert create_task(service)==created
    with pytest.raises(ResearchConflict):
        service.create_task(command_id="create-1",task_id="task-1",objective="different payload")
    state=service.get_task("task-1")
    assert len(state["goals"])==1 and len(state["command_receipts"])==1
    assert state["events"][-1]["event_type"]=="command_payload_mismatch_rejected"


def test_research_checkpoint_result_and_restart_lineage(collection_db):
    service=ResearchTaskService(collection_db)
    attempt=bootstrap(service)
    first=service.commit_checkpoint(task_id="task-1",attempt_id=attempt["attempt_id"],command_id="checkpoint-1",
        owner_id="worker-a",owner_epoch=1,expected_state_version=2,expected_checkpoint_id=None,state_payload={"verified":["synthetic"]})
    second=service.resume_attempt(task_id="task-1",attempt_id=attempt["attempt_id"],command_id="resume-1",
        owner_id="worker-a",owner_epoch=1,expected_state_version=3,expected_checkpoint_id=first["checkpoint_id"])
    restarted=ResearchTaskService(collection_db)
    assert restarted.checkpoint_lineage(second["checkpoint_id"])==[second["checkpoint_id"],first["checkpoint_id"]]
    state=restarted.get_task("task-1")
    assert state["checkpoints"][-1]["state_payload"]=={"verified":["synthetic"]}
    result=restarted.complete_attempt(task_id="task-1",attempt_id=attempt["attempt_id"],command_id="complete-1",
        owner_id="worker-a",owner_epoch=1,expected_state_version=4,checkpoint_id=second["checkpoint_id"],
        answer_status=AnswerStatus.VALID_SUCCESS,termination_reason=TerminationReason.ANSWER_READY,
        failure_class=FailureClass.NONE,reason_detail="synthetic complete",task_terminal=True)
    assert restarted.get_task("task-1")["task"]["terminal_result_id"]==result["result_id"]


def test_research_create_fault_rolls_back_root_goal_event_and_receipt(collection_db):
    def fault(point):
        if point=="after_task_insert":raise RuntimeError("synthetic crash")
    service=ResearchTaskService(collection_db,fault_injector=fault)
    with pytest.raises(RuntimeError,match="synthetic crash"):create_task(service)
    with collection_db.connect(read_only=True) as conn:
        for table in ("research_tasks","research_goals","research_events","research_command_receipts"):
            assert conn.execute(f"SELECT count(*) AS n FROM shiliu.{table}").fetchone()["n"]==0


def test_research_second_owner_default_identity_and_legacy_replay(collection_db):
    import hashlib
    from datetime import datetime,timezone
    from shiliu.db import Database
    from shiliu.storage.scope import ResourceContext
    from shiliu.research.errors import ResearchNotFound
    first=ResearchTaskService(collection_db)
    legacy_id="rtask_"+hashlib.sha256(b"shared-command").hexdigest()[:32]
    legacy=first.create_task(command_id="shared-command",task_id=legacy_id,objective="synthetic")
    assert first.create_task(command_id="shared-command",objective="synthetic")==legacy
    with collection_db.connect() as conn:
        now=datetime.now(timezone.utc)
        conn.execute("INSERT INTO shiliu.users(id,display_name,created_at) VALUES('research-owner','Synthetic',%s)",(now,))
        conn.execute("INSERT INTO shiliu.workspaces(id,kind,owner_user_id,created_at) VALUES('personal:research-owner','personal','research-owner',%s)",(now,))
        conn.execute("INSERT INTO shiliu.workspace_guards(workspace_id) VALUES('personal:research-owner')")
    other=ResearchTaskService(Database(collection_db.pg,ResourceContext("personal:research-owner","research-owner")))
    own=other.create_task(command_id="shared-command",objective="synthetic")
    assert own["task_id"]!=legacy_id
    assert other.create_task(command_id="shared-command",objective="synthetic")==own
    claim(other,own["task_id"])
    started=start(other,own["task_id"])
    assert other.get_task(own["task_id"])["attempts"][0]["attempt_id"]==started["attempt_id"]
    with pytest.raises(ResearchNotFound):other.get_task(legacy_id)


def test_research_takeover_rebinds_reserved_but_never_replays_unknown(collection_db):
    from shiliu.research import ResearchUnsafeState
    service=ResearchTaskService(collection_db)
    attempt=bootstrap(service)
    def reserve(key,version):
        return service.reserve_side_effect(task_id="task-1",attempt_id=attempt["attempt_id"],command_id="reserve-"+key,
            owner_id="worker-a",owner_epoch=1,expected_state_version=version,effect_kind="synthetic_export",idempotency_key=key,request_payload={"key":key})
    reserved=reserve("reserved",2)
    flying=reserve("flying",3)
    service.transition_side_effect(task_id="task-1",side_effect_id=flying["side_effect_id"],command_id="dispatch",
        owner_id="worker-a",owner_epoch=1,expected_state_version=4,target_status="in_flight")
    with collection_db.connect() as conn:
        conn.execute("UPDATE shiliu.research_tasks SET lease_until=clock_timestamp()-interval '1 second' WHERE task_id='task-1'")
    claimed=claim(service,owner_id="worker-b",command_id="takeover",expected=5)
    assert claimed["owner_epoch"]==2
    recovered=service.recover_in_flight(task_id="task-1",command_id="recover",owner_id="worker-b",owner_epoch=2,expected_state_version=6)
    assert recovered["unknown_side_effect_ids"]==[flying["side_effect_id"]]
    state=service.get_task("task-1")
    effects={e["side_effect_id"]:e for e in state["side_effects"]}
    assert effects[reserved["side_effect_id"]]["owner_epoch"]==2
    assert effects[flying["side_effect_id"]]["owner_epoch"]==1 and effects[flying["side_effect_id"]]["status"]=="unknown"
    with pytest.raises(ResearchConflict):
        service.commit_checkpoint(task_id="task-1",attempt_id=attempt["attempt_id"],command_id="stale-checkpoint",owner_id="worker-a",
            owner_epoch=1,expected_state_version=7,expected_checkpoint_id=None,state_payload={})
    with pytest.raises(ResearchUnsafeState,match="unresolved"):
        service.commit_checkpoint(task_id="task-1",attempt_id=attempt["attempt_id"],command_id="unsafe-checkpoint",owner_id="worker-b",
            owner_epoch=2,expected_state_version=7,expected_checkpoint_id=None,state_payload={})


def test_ancestor_branch_schema_still_rejects_unrelated_task_source(collection_db):
    import test_v5_a_stage1_research_kernel as original
    from shiliu.research.adapter import DeterministicEffectAdapter
    from seed_rows import insert
    from psycopg.errors import ForeignKeyViolation
    service=ResearchTaskService(collection_db)
    original.test_branch_and_replay_use_read_only_checkpoint_from_current_or_ancestor_task(
        (collection_db,original.MutableClock(),DeterministicEffectAdapter(),service))
    with collection_db.connect() as conn:
        child=dict(conn.execute("SELECT * FROM shiliu.research_attempts WHERE cause='branch' LIMIT 1").fetchone())
        source=conn.execute("SELECT * FROM shiliu.research_checkpoints WHERE task_id='unrelated' LIMIT 1").fetchone()
        child.pop("insertion_seq",None)
        invalid=dict(child,attempt_id="unrelated-source-branch",ordinal=child["ordinal"]+1,status="terminal",
                     parent_attempt_id=source["attempt_id"],source_checkpoint_id=source["checkpoint_id"])
        with pytest.raises(ForeignKeyViolation,match="research_attempt_source_lineage"):
            with conn.transaction():insert(conn,"research_attempts",invalid)


# Reviewed original kernel contracts that do not depend on SQLite DDL or a fake lease clock.
ORIGINAL_KERNEL_CONTRACTS = [
    'test_create_task_is_atomic_and_entities_have_distinct_ids',
    'test_all_stage1_entity_id_namespaces_remain_distinct',
    'test_command_dedupe_returns_same_response_and_payload_mismatch_fails_closed',
    'test_active_owner_cannot_be_taken_over_and_renew_is_fenced',
    'test_concurrent_owner_claim_has_one_winner',
    'test_checkpoint_resume_and_strict_lineage_survive_restart',
    'test_start_resume_and_retry_command_replays_are_semantically_idempotent',
    'test_public_start_attempt_rejects_cause_and_lineage_bypasses_without_drift',
    'test_stale_checkpoint_and_checkpoint_fault_fail_closed',
    'test_result_commit_requires_latest_checkpoint_guard',
    'test_attempt_result_can_be_terminal_while_task_remains_retryable',
    'test_result_dimensions_preserve_partial_provider_failure_without_provider_run',
    'test_result_dimensions_preserve_implementation_failure_without_answer',
    'test_result_fault_rolls_back_result_attempt_and_task_terminal_state',
    'test_terminal_task_cannot_revive_and_retry_creates_immutable_child_lineage',
    'test_goal_revision_is_immutable_and_starts_new_attempt',
    'test_branch_and_replay_use_read_only_checkpoint_from_current_or_ancestor_task',
    'test_cancel_is_idempotent_and_cancel_result_wins_only_once',
    'test_cancel_and_result_race_has_one_terminal_winner',
    'test_deterministic_side_effect_is_task_scoped_and_replay_safe',
    'test_same_side_effect_business_key_is_valid_across_tasks',
    'test_concurrent_same_task_side_effect_reservation_creates_one_record',
    'test_reserved_side_effect_survives_restart_and_can_continue_once',
    'test_in_flight_cannot_be_marked_unknown_before_old_owner_is_fenced',
    'test_checkpoint_rejected_while_side_effect_is_unresolved',
 ]

@pytest.mark.parametrize("contract",ORIGINAL_KERNEL_CONTRACTS)
def test_original_kernel_contract_on_pg(collection_db,contract):
    import test_v5_a_stage1_research_kernel as original
    from shiliu.research.adapter import DeterministicEffectAdapter
    clock=original.MutableClock()
    adapter=DeterministicEffectAdapter()
    service=ResearchTaskService(collection_db,clock=clock,effect_adapter=adapter)
    getattr(original,contract)((collection_db,clock,adapter,service))
