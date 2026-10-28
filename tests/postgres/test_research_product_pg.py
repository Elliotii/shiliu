"""The product runner uses the real PG inner/outer/control composition."""
from shiliu.research.control_service import ResearchControlService
from shiliu.research.product_service import ResearchProductService
from shiliu.research.product_contracts import CreateProductResearchRequest,RunProductResearchRequest
from test_research_outer_pg import outer_core


def test_product_run_to_terminal_candidate_delta_and_history(outer_core):
    core=outer_core
    product=ResearchProductService(db=core.db,kernel=core.research,inner=core.research_inner,outer=core.research_outer,control=ResearchControlService(core.db,kernel=core.research))
    created=product.create_task(CreateProductResearchRequest(command_id="product-create",objective="生成一份包含当前可重建引用的研究回答",run_immediately=False))
    task_id=created["task_id"]
    result=product.run_to_boundary(task_id,RunProductResearchRequest(command_id="product-run"))
    assert result["task_status"]=="terminal"
    persisted=core.research.get_task(task_id)
    assert persisted["task"]["terminal_result_id"]
    snapshots=[e for e in persisted["events"] if e["event_type"]=="candidate_deltas_materialized"]
    assert len(snapshots)==1
    assert {d["delta_kind"] for d in snapshots[0]["payload"]["deltas"]}=={"KnowledgeDelta","CorpusDelta","UserModelDelta","SystemExperienceDelta"}
    assert snapshots[0]["payload"]["evidence_use_ids"]
    detail=product.get_task(task_id)
    assert detail["task"]["task_id"]==task_id
    assert product.list_tasks()[0]["task_id"]==task_id
    replay=product.run_to_boundary(task_id,RunProductResearchRequest(command_id="product-run"))
    assert replay["deduplicated"]
