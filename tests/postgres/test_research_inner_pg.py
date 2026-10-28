"""Explicit PG Collection -> inner Research evidence/checkpoint composition."""
from types import SimpleNamespace
import pytest

from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.deep.navigation import NavigationService
from shiliu.ask.deep.transcript import TranscriptSearchService,TranscriptWindowReader
from shiliu.research.service import ResearchTaskService
from shiliu.research.inner_service import InnerResearchService
from shiliu.research.inner_tools import LocalInnerToolAdapter, DeterministicInnerToolAdapter
from test_collection_retrieval import add_video,product_composition


def start_pg(core,task_id,*,owner="worker",objective="MCP"):
    core.research.create_task(command_id=f"create:{task_id}",task_id=task_id,objective=objective,
        success_constraints=["引用当前字幕"],evidence_policy={"authority":"live_current_exact_replay"})
    claimed=core.research.claim_owner(task_id=task_id,command_id=f"claim:{task_id}",owner_id=owner,expected_state_version=0,lease_seconds=60)
    started=core.research.start_attempt(task_id=task_id,command_id=f"start:{task_id}",owner_id=owner,
        owner_epoch=claimed["owner_epoch"],expected_state_version=1)
    return dict(task_id=task_id,attempt_id=started["attempt_id"],owner_id=owner,owner_epoch=claimed["owner_epoch"],state_version=2,checkpoint_id=None)


@pytest.mark.parametrize("contract",[
    "test_durable_inner_loop_runs_one_action_per_checkpoint_and_stays_nonterminal",
    "test_inner_command_replay_is_idempotent_and_payload_mismatch_fails_closed",
    "test_unresolved_side_effect_blocks_inner_checkpoint_without_state_drift",
    "test_budget_stop_is_persisted_and_survives_restart",
    "test_local_action_failure_persists_orthogonal_failure_dimensions",
    "test_long_objective_is_preserved_while_tool_queries_are_bounded",
    "test_short_objective_remains_the_normalized_tool_query",
    "test_terminal_task_cannot_start_inner_run_and_has_no_state_drift",
    "test_concurrent_cross_task_materialization_converges_on_one_identity",
    "test_concurrent_same_command_commits_one_action_checkpoint_and_receipt",
])
def test_original_inner_contract_on_real_pg_collection(retrieval,app_paths,tmp_path,monkeypatch,contract):
    import test_v5_a_stage2_inner_loop as original
    db,artifacts,lexical,dense=retrieval
    _,vid=add_video(retrieval,text="MCP 使用客户端与服务端连接模型和外部能力。工具调用需要明确的请求与响应协议。研究任务通过持久 checkpoint 恢复。")
    db.update_video(vid,title="MCP Durable Research")
    dense.rebuild()
    _,product,evidence=product_composition(retrieval)
    materializer=TranscriptEvidenceMaterializer(db,artifacts=artifacts)
    tools=LocalInnerToolAdapter(navigation=NavigationService(db=db,artifacts=artifacts,product_search=product),
        transcripts=TranscriptSearchService(evidence_search=evidence,materializer=materializer),
        windows=TranscriptWindowReader(db,materializer))
    kernel=ResearchTaskService(db)
    inner=InnerResearchService(db=db,kernel=kernel,tools=tools,materializer=materializer)
    if contract.startswith("test_concurrent_"):
        # The original concurrency fixture asks an unfocused adapter for a seed
        # span. Build that seed through an explicitly focused PG search.
        seed=tools.search("MCP",video_ids=(vid,),query_index=0)
        assert seed.spans
        inner.tools=DeterministicInnerToolAdapter(search_spans=seed.spans)
    core=SimpleNamespace(db=db,artifacts=artifacts,research=kernel,research_inner=inner)
    monkeypatch.setattr(original,"_fixture_core",lambda paths:(core,tmp_path/"synthetic-unused-raw.json"))
    # The original 300s SQLite fixture lease is replaced with the formal 60s PG
    # lease; the original five-phase, artifact, budget and restart assertions run.
    monkeypatch.setattr(original,"_start",start_pg)
    monkeypatch.setattr(original,"TranscriptEvidenceMaterializer",lambda db:materializer)
    def counts(db,task_id):
        state=kernel.get_task(task_id)
        return {"research_"+key:len(state[key]) for key in ("inner_actions","evidence_uses","evidence_validations","provisional_artifacts")}
    monkeypatch.setattr(original,"_counts",counts)
    getattr(original,contract)(app_paths)
