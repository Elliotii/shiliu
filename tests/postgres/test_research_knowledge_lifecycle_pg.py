"""PG knowledge correction, refresh, page history and revision-hash exports."""
import pytest
from shiliu.storage.errors import StorageError
from test_research_knowledge_pg import knowledge_core
from test_research_outer_pg import outer_core
from test_v5_b_stage2_knowledge_lifecycle import (
    _vertical,_propose_and_accept_correction,RunKnowledgeOperationRequest,
    ReviewTopicPageRequest,EditTopicPageRequest,RevertTopicPageRequest,
)


def test_original_correction_refresh_page_history_on_pg(knowledge_core):
    core = knowledge_core
    task_id, _, artifact, page = _vertical(core, "lifecycle")
    accepted = _propose_and_accept_correction(core, task_id, "lifecycle")
    assert accepted["result_revision_id"]
    assert accepted["operation_id"]
    before_run = core.research_knowledge.get_workspace(task_id)
    assert before_run["pages"][0]["version"] == 1
    assert before_run["operations"][0]["status"] == "pending"
    finished = core.research_knowledge.run_update_operation(
        task_id,
        accepted["operation_id"],
        RunKnowledgeOperationRequest(command_id="v5b2:operation:lifecycle"),
        principal_id="local_operator",
    )
    assert finished["status"] == "succeeded"
    assert finished["outputs"]["artifacts"][0]["revision"] == 2
    assert finished["outputs"]["pages"][0]["version"] == 2
    workspace = core.research_knowledge.get_workspace(task_id)
    assert [value["revision"] for value in workspace["facts"]] == [1, 2]
    assert workspace["pages"][0]["published_version"] == 1
    assert workspace["pages"][0]["review_status"] == "draft"
    core.research_knowledge.review_page(
        task_id,
        page["page_id"],
        ReviewTopicPageRequest(
            command_id="v5b2:publish:lifecycle:v2",
            decision="publish",
            expected_version=2,
        ),
        principal_id="local_operator",
    )
    edited = core.research_knowledge.edit_topic_page(
        task_id,
        page["page_id"],
        EditTopicPageRequest(
            command_id="v5b2:edit:lifecycle",
            expected_version=2,
            annotation="人工审查备注",
        ),
        principal_id="local_operator",
    )
    assert edited["version"] == 3 and edited["published_version"] == 2
    history = core.research_knowledge.get_topic_page_history(task_id, page["page_id"])
    assert [value["revision_kind"] for value in history["revisions"]] == [
        "initial",
        "refresh",
        "edit",
    ]
    diff = core.research_knowledge.get_topic_page_diff(task_id, page["page_id"], 2, 3)
    assert any("人工审查备注" in line for line in diff["lines"])
    reverted = core.research_knowledge.revert_topic_page(
        task_id,
        page["page_id"],
        RevertTopicPageRequest(
            command_id="v5b2:revert:lifecycle",
            expected_version=3,
            target_version=1,
        ),
        principal_id="local_operator",
    )
    assert reverted["version"] == 4 and reverted["revision_kind"] == "revert"
    assert core.research_knowledge.get_topic_page_history(
        task_id, page["page_id"]
    )["published_version"] == 2
    db=core.db
    for statement,params in [
        ("UPDATE research_fact_revisions SET claim_text='forged' WHERE workspace_id=%s AND fact_revision_id=%s",(db.workspace_id,accepted["result_revision_id"])),
        ("UPDATE research_topic_page_revisions SET title='forged' WHERE workspace_id=%s AND page_id=%s AND version=1",(db.workspace_id,page["page_id"])),
    ]:
        with pytest.raises(StorageError) as error:
            with db.connect() as conn:conn.execute(statement,params)
        assert error.value.sqlstate=="23514"
    with db.connect(read_only=True) as conn:
        assert conn.execute("SELECT count(*) AS n FROM research_knowledge_artifact_revisions WHERE workspace_id=%s AND artifact_id=%s",(db.workspace_id,artifact["artifact_id"])).fetchone()["n"]==2


def test_original_revision_hash_export_retry_on_pg(knowledge_core,app_paths,monkeypatch):
    import test_v5_b_stage2_knowledge_lifecycle as original
    monkeypatch.setattr(original,"_core",lambda paths:knowledge_core)
    original.test_revision_hash_export_failure_is_observable_and_same_command_retries(app_paths)


def test_fact_review_fault_rolls_back_revision_decision_operation_and_receipt(knowledge_core):
    from shiliu.research.knowledge_contracts import ProposeFactUpdateRequest,ReviewFactUpdateRequest
    from shiliu.research.errors import SimulatedCrash
    core=knowledge_core
    task_id,fact,_,_=_vertical(core,"atomic-review")
    proposed=core.research_knowledge.propose_fact_update(task_id,fact["fact_id"],ProposeFactUpdateRequest(command_id="propose-atomic",kind="user_correction",expected_fact_state_version=fact["fact_state_version"],proposed_claim=fact["citations"][0]["quote"],evidence_use_ids=[fact["citations"][0]["evidence_use_id"]]),principal_id=core.db.context.user_id)
    before=core.research_knowledge.get_workspace(task_id)
    before_task=core.research.get_task(task_id)
    def fault(point):
        if point=="after_stage2_fact_revision":raise SimulatedCrash(point)
    core.research_knowledge.fault_injector=fault
    with pytest.raises(SimulatedCrash):
        core.research_knowledge.review_fact_update(task_id,proposed["update_candidate_id"],ReviewFactUpdateRequest(command_id="review-atomic",decision="accept",expected_candidate_version=0,expected_fact_state_version=fact["fact_state_version"]),principal_id=core.db.context.user_id)
    core.research_knowledge.fault_injector=lambda point:None
    assert core.research_knowledge.get_workspace(task_id)==before
    assert core.research.get_task(task_id)==before_task


def test_operation_crash_recovers_only_expired_claim(knowledge_core):
    from shiliu.research.knowledge_contracts import RecoverKnowledgeOperationsRequest
    from shiliu.research.errors import SimulatedCrash,ResearchConflict
    core=knowledge_core
    db=core.db
    task_id,_,_,_=_vertical(core,"operation-crash")
    accepted=_propose_and_accept_correction(core,task_id,"operation-crash")
    operation_id=accepted["operation_id"]
    def crash(point):
        if point=="after_stage2_operation_claim":raise SimulatedCrash(point)
    core.research_knowledge.fault_injector=crash
    with pytest.raises(SimulatedCrash):core.research_knowledge.run_update_operation(task_id,operation_id,RunKnowledgeOperationRequest(command_id="operation-crash"),principal_id=db.context.user_id)
    core.research_knowledge.fault_injector=lambda point:None
    assert core.research_knowledge.get_workspace(task_id)["operations"][0]["status"]=="running"
    with pytest.raises(ResearchConflict):core.research_knowledge.run_update_operation(task_id,operation_id,RunKnowledgeOperationRequest(command_id="premature-takeover"),principal_id=db.context.user_id)
    with db.connect() as conn:
        core.research._task(conn,task_id)
        conn.execute("UPDATE research_knowledge_update_operations SET lease_until=clock_timestamp()-interval '1 second' WHERE workspace_id=%s AND task_id=%s AND operation_id=%s",(db.workspace_id,task_id,operation_id))
    recovered=core.research_knowledge.recover_update_operations(task_id,RecoverKnowledgeOperationsRequest(command_id="recover"),principal_id=db.context.user_id)
    workspace=core.research_knowledge.get_workspace(task_id)
    assert workspace["operations"][0]["status"]=="succeeded"
    assert workspace["operations"][0]["claim_generation"]==2
    assert len(workspace["artifacts"])==2 and workspace["pages"][0]["version"]==2
