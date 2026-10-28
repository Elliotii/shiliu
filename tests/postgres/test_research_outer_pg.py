"""Retained deterministic outer gate/continuation assertions against real PG."""
import pytest
from types import SimpleNamespace
from psycopg import sql
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.deep.navigation import NavigationService
from shiliu.ask.deep.transcript import TranscriptSearchService,TranscriptWindowReader
from shiliu.research.service import ResearchTaskService
from shiliu.research.inner_service import InnerResearchService
from shiliu.research.inner_tools import LocalInnerToolAdapter
from shiliu.research.outer_service import OuterResearchService
from test_collection_retrieval import add_video,product_composition

class Core(SimpleNamespace):
    @property
    def research_outer(self):return self._research_outer

@pytest.fixture
def outer_core(retrieval,app_paths,monkeypatch):
    import test_v5_a_stage3_outer_audit as original
    db,artifacts,lexical,dense=retrieval
    _,vid=add_video(retrieval,text=original.OBJECTIVE_TEXT+"。"+original.CONSTRAINT_TEXT+"。研究持久证据并判断月球构成。可恢复缺口创建带 lineage 的子 Attempt。")
    db.update_video(vid,title=original.OBJECTIVE_TEXT)
    dense.rebuild()
    _,product,evidence=product_composition(retrieval)
    materializer=TranscriptEvidenceMaterializer(db,artifacts)
    tools=LocalInnerToolAdapter(navigation=NavigationService(db=db,artifacts=artifacts,product_search=product),
        transcripts=TranscriptSearchService(evidence_search=evidence,materializer=materializer),windows=TranscriptWindowReader(db,materializer))
    kernel=ResearchTaskService(db)
    inner=InnerResearchService(db=db,kernel=kernel,tools=tools,materializer=materializer)
    core=Core(paths=app_paths,db=db,artifacts=artifacts,research=kernel,research_inner=inner)
    def outer(**kwargs):
        kwargs.setdefault("authority",inner.authority)
        return OuterResearchService(**kwargs)
    core._research_outer=outer(db=db,kernel=kernel)
    def start(core,task_id,*,policy=None,owner="worker",registered=True,registry_minimum=1,objective=original.OBJECTIVE_TEXT,success_constraints=None):
        if registered:core._research_outer=outer(db=db,kernel=kernel,registered_evaluators=original._registered_evaluators(minimum=registry_minimum))
        kernel.create_task(command_id=f"create:{task_id}",task_id=task_id,objective=objective,success_constraints=list(success_constraints) if success_constraints is not None else [original.CONSTRAINT_TEXT],evidence_policy=policy if policy is not None else original._policy())
        claimed=kernel.claim_owner(task_id=task_id,command_id=f"claim:{task_id}",owner_id=owner,expected_state_version=0,lease_seconds=60)
        started=kernel.start_attempt(task_id=task_id,command_id=f"start:{task_id}",owner_id=owner,owner_epoch=claimed["owner_epoch"],expected_state_version=1)
        return dict(task_id=task_id,attempt_id=started["attempt_id"],owner_id=owner,owner_epoch=claimed["owner_epoch"],state_version=2,checkpoint_id=None)
    def counts(core,task_id):
        with db.connect(read_only=True) as conn:
            return {table:conn.execute(sql.SQL('SELECT count(*) AS n FROM {} WHERE workspace_id=%s AND task_id=%s').format(sql.Identifier(table)),(db.workspace_id,task_id)).fetchone()["n"] for table in original.STAGE3_TABLES}
    monkeypatch.setattr(original,"_fixture_core",lambda paths:core)
    monkeypatch.setattr(original,"_start",start)
    monkeypatch.setattr(original,"_counts",counts)
    monkeypatch.setattr(original,"OuterResearchService",outer)
    return core

@pytest.mark.parametrize("contract",[
    "test_registered_gate_accepts_and_atomically_terminalizes_task",
    "test_candidate_confidence_has_no_gate_authority_and_natural_language_blocks",
    "test_recoverable_gap_atomically_creates_retry_child_seed_and_scoped_uses",
    "test_replay_is_exactly_once_and_payload_mismatch_fails_closed",
    "test_concurrent_same_command_produces_one_audit_and_result",
    "test_outer_budget_is_aggregate_and_repeated_target_stops_after_child",
    "test_internal_evaluator_failure_rolls_back_then_commits_fenced_failure_once",
    "test_simulated_crash_is_not_misclassified_as_implementation_failure",
])
def test_original_outer_contract_on_pg(outer_core,app_paths,contract):
    import test_v5_a_stage3_outer_audit as original
    getattr(original,contract)(app_paths)

@pytest.mark.parametrize("via_api",[False,True])
def test_original_forged_evaluator_authority_on_pg(outer_core,app_paths,via_api):
    import test_v5_a_stage3_outer_audit as original
    original.test_client_cannot_grant_evaluator_authority_to_false_natural_constraint(app_paths,via_api)

@pytest.mark.parametrize("fault_point",[
    "after_outer_currentness_observations_insert","after_outer_audit_insert",
    "after_constraint_observations_insert","after_improvement_state_insert",
    "after_outer_checkpoint_insert","after_outer_parent_result_insert",
    "after_outer_child_attempt_insert","after_outer_continuation_seed_insert",
    "after_outer_event_insert","after_outer_receipt_insert",
])
def test_original_continuation_atomic_faults_on_pg(outer_core,app_paths,fault_point):
    import test_v5_a_stage3_outer_audit as original
    original.test_continuation_fault_points_roll_back_every_stage3_write(app_paths,fault_point)
