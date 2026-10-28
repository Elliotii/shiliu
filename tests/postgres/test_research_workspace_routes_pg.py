"""Real PG accepted knowledge reuse and private workspace records."""
import pytest
from shiliu.research.knowledge_contracts import AssessArtifactRouteRequest,ProceedArtifactRouteRequest
from shiliu.research.errors import SimulatedCrash
from test_research_knowledge_pg import knowledge_core
from test_research_outer_pg import outer_core
from test_v5_b_stage3_artifact_reuse import _vertical,_assess


def test_direct_route_reuses_current_artifact_and_no_hit_seeds_child(knowledge_core):
    core=knowledge_core
    task_id,fact,artifact,page=_vertical(core,"routes-pg")
    assessed=_assess(core,task_id,suffix="direct",query=fact["claim"],aspects=[fact["claim"]])
    assert assessed["recommended_route"]=="direct_reuse"
    gate=assessed["gates"][0]
    assert gate["score_reason"]["authority"]=="ranking_only"
    assert gate["scope_status"]=="exact" and gate["completeness_status"]=="complete"
    assert gate["citation_status"]=="pass" and gate["facts"][0]["citations"][0]["outcome"]=="current"
    assert assessed["open_corpus"]["independent_lane"] and not assessed["open_corpus"]["hard_filter"]
    assert assessed["open_corpus"]["results"]
    request=ProceedArtifactRouteRequest(command_id="direct-confirm",action="confirm",expected_version=1,route="direct_reuse")
    outcome=core.research_knowledge.proceed_artifact_route(task_id,assessed["route_id"],request,principal_id=core.db.context.user_id)
    assert outcome["status"]=="completed" and outcome["outcome_artifact_revision_id"]==artifact["artifact_revision_id"]
    assert outcome["continuation_task_id"] is None
    assert core.research_knowledge.proceed_artifact_route(task_id,assessed["route_id"],request,principal_id=core.db.context.user_id)["deduplicated"]
    nohit=_assess(core,task_id,suffix="nohit",query="完全不存在的量子园艺主题",aspects=["量子园艺"])
    assert nohit["recommended_route"]=="research_seed" and nohit["artifact_candidates"]==[]
    seeded=core.research_knowledge.proceed_artifact_route(task_id,nohit["route_id"],ProceedArtifactRouteRequest(command_id="seed-confirm",expected_version=1,route="research_seed"),principal_id=core.db.context.user_id)
    child=core.research.get_task(seeded["continuation_task_id"])
    assert child["task"]["parent_task_id"]==task_id
    policy=child["goals"][0]["evidence_policy"]
    assert policy["artifact_context_authority"]=="candidate_only_not_verifier" and policy["open_retrieval_required"]
    final=core.research_knowledge.get_workspace(task_id)
    assert len(final["artifacts"])==1 and final["pages"][0]["version"]==1


def test_route_assessment_fault_rolls_back_event_receipt_and_route(knowledge_core):
    core=knowledge_core
    task_id,fact,_,_=_vertical(core,"route-rollback-pg")
    before=core.research.get_task(task_id)
    def fault(point):
        if point=="after_stage3_route_assessment":raise SimulatedCrash(point)
    core.research_knowledge.fault_injector=fault
    with pytest.raises(SimulatedCrash):core.research_knowledge.assess_artifact_route(task_id,AssessArtifactRouteRequest(command_id="route-rollback",query=fact["claim"],required_aspects=[fact["claim"]]))
    assert core.research.get_task(task_id)==before
    assert core.research_knowledge.reuse.list(task_id)==[]


@pytest.mark.parametrize("contract",[
    "test_inferred_candidate_review_expiry_and_no_resurrection",
    "test_focus_and_progress_preserve_semantic_authority",
])
def test_original_personal_workspace_contract_on_pg(knowledge_core,app_paths,monkeypatch,contract):
    import test_v5_b_stage4_personal_workspace as original
    core=knowledge_core
    def event_refs(core,task_id,limit=3):
        from shiliu.research.knowledge_contracts import WorkspaceSourceRef
        events=core.research.get_task(task_id)["events"][:limit]
        assert len(events)==limit
        return [WorkspaceSourceRef(ref_type="research_event",ref_id=e["event_id"],task_id=task_id) for e in events]
    monkeypatch.setattr(original,"_core",lambda paths:core)
    monkeypatch.setattr(original,"_event_refs",event_refs)
    getattr(original,contract)(app_paths)


def test_workspace_second_owner_own_records_and_cross_workspace_rejection(collection_db):
    from datetime import datetime,timezone
    from shiliu.db import Database
    from shiliu.storage.scope import ResourceContext
    from shiliu.research.service import ResearchTaskService
    from shiliu.research.personal_workspace import ResearchPersonalWorkspaceService
    from shiliu.research.knowledge_contracts import CreateWorkspaceRecordRequest,WorkspaceSourceRef
    from shiliu.research.errors import ResearchNotFound,ResearchValidationError,ResearchForbidden
    db=collection_db
    first_kernel=ResearchTaskService(db)
    first_task=first_kernel.create_task(command_id="owner-one-task",objective="synthetic")
    first=ResearchPersonalWorkspaceService(db,kernel=first_kernel)
    request=CreateWorkspaceRecordRequest(command_id="memory-create",record_kind="explicit_memory",semantic_key="response language",payload={"key":"response_language","value":"Chinese"})
    one=first.create(first_task["task_id"],request,principal_id=db.context.user_id)
    with db.connect() as conn:
        now=datetime.now(timezone.utc)
        conn.execute("INSERT INTO users(id,display_name,created_at) VALUES('workspace-owner','Synthetic',%s)",(now,))
        conn.execute("INSERT INTO workspaces(id,kind,owner_user_id,created_at) VALUES('personal:workspace-owner','personal','workspace-owner',%s)",(now,))
        conn.execute("INSERT INTO workspace_guards(workspace_id) VALUES('personal:workspace-owner')")
    other_db=Database(db.pg,ResourceContext("personal:workspace-owner","workspace-owner"))
    other_kernel=ResearchTaskService(other_db)
    own_task=other_kernel.create_task(command_id="owner-two-task",objective="synthetic")
    other=ResearchPersonalWorkspaceService(other_db,kernel=other_kernel)
    two=other.create(own_task["task_id"],request,principal_id=other_db.context.user_id)
    assert one["record_id"]!=two["record_id"]
    assert [r["record_id"] for r in other.get_workspace(own_task["task_id"],principal_id=other_db.context.user_id)["records"]]==[two["record_id"]]
    with pytest.raises(ResearchNotFound):other.get_workspace(first_task["task_id"])
    with pytest.raises(ResearchForbidden):other.create(own_task["task_id"],request.model_copy(update={"command_id":"forged-principal"}),principal_id=db.context.user_id)
    event=first_kernel.get_task(first_task["task_id"])["events"][0]
    crossed=CreateWorkspaceRecordRequest(command_id="crossed-source",record_kind="focus_state",semantic_key="current focus",payload={"topic":"MCP","state":"focused"},source_refs=[WorkspaceSourceRef(ref_type="research_event",ref_id=event["event_id"],task_id=first_task["task_id"])])
    with pytest.raises(ResearchValidationError):other.create(own_task["task_id"],crossed,principal_id=other_db.context.user_id)


def test_assistance_progress_and_staleness_read_real_pg_boundaries(knowledge_core):
    from shiliu.research.knowledge_contracts import CreateWorkspaceRecordRequest,WorkspaceSourceRef
    core=knowledge_core
    task_id,fact,_,_=_vertical(core,"assistance-pg")
    service=core.research_knowledge
    context=core.db.context
    cold=service.get_personal_workspace(task_id,principal_id=context.user_id,assistance_enabled=True)["knowledge_assistance"]
    assert cold["status"]=="baseline" and not cold["lanes"]["progress"]["cards"]
    events=core.research.get_task(task_id)["events"]
    for kind,payload,refs in [
        ("mastered",{"topic":"MCP","state":"mastered","user_asserted":True},[]),
        ("watched",{"topic":"leases","state":"reviewed","observation_type":"watched"},[WorkspaceSourceRef(ref_type="research_event",ref_id=events[0]["event_id"],task_id=task_id)]),
    ]:
        service.create_personal_workspace_record(task_id,CreateWorkspaceRecordRequest(command_id="progress-"+kind,record_kind="progress_observation",semantic_key=kind,payload=payload,source_refs=refs),principal_id=context.user_id)
    before=core.research.get_task(task_id)
    projected=service.get_personal_workspace(task_id,principal_id=context.user_id,assistance_enabled=True)["knowledge_assistance"]
    cards=projected["lanes"]["progress"]["cards"]
    assert [c["mastery"] for c in cards]==[True,False]
    assert cards[1]["observation_type"]=="watched"
    assert core.research.get_task(task_id)==before
    with core.db.connect() as conn:
        core.research._task(conn,task_id)
        conn.execute("UPDATE research_knowledge_fact_states SET currentness_status='stale',state_version=state_version+1 WHERE workspace_id=%s AND task_id=%s AND fact_id=%s",(context.workspace_id,task_id,fact["fact_id"]))
    stale=service.get_personal_workspace(task_id,principal_id=context.user_id,assistance_enabled=True)["knowledge_assistance"]["lanes"]["staleness"]["cards"]
    assert len(stale)==1 and stale[0]["dismiss_control"]["source_refs"][0]["ref_type"]=="fact_revision"
    from shiliu.research.knowledge_service import ResearchKnowledgeService
    restarted=ResearchKnowledgeService(core.db,kernel=core.research,product=core.research_product,retrieval=core.retrieval,export_root=service.lifecycle.export_root)
    assert restarted.get_personal_workspace(task_id,principal_id=context.user_id,assistance_enabled=True)==service.get_personal_workspace(task_id,principal_id=context.user_id,assistance_enabled=True)
