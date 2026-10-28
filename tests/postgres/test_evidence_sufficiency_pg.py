"""Current /api/evidence-sufficiency: retain Stage5's original gate contracts.

Only the old filesystem/implicit-Application fixture is replaced. Original
assertions run against a real PG Application and immutable raw Artifact bytes.
"""
import pytest
import test_stage5_integration as original
from shiliu.app import Application
from shiliu.config import AppConfig
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.stage5 import Stage5PipelineService
from test_application_pg import application_target  # noqa: F401 -- pytest fixture
from test_collection_retrieval import FixedProvider


@pytest.fixture
def current_stage5(application_target,app_paths,monkeypatch,request):  # noqa: F811 -- pytest fixture injection
    runtime,_=application_target
    core=Application(app_paths,config=AppConfig(content_dir=str(app_paths.content_dir),assistant_enabled=False),
        postgres_config=runtime,embedding_provider=FixedProvider(),adapter=object(),
        provider_availability=lambda:{'available':False,'reason':'synthetic offline'})
    request.addfinalizer(core.close)
    sid=core.db.create_favorite_source(folder_id=1,folder_title='合成MCP来源')
    core.db.record_source_snapshot(sid,[FavoriteItem(bvid='BV0000000001',title='合成MCP',favorite_time=100)],processing_profile='formal')
    batch=core.artifacts.batch(1)
    _,ref=batch.save_raw_subtitle('BV0000000001',[
        SubtitleSegment.model_validate({'from':i*5.,'to':i*5.+4.,'content':text})
        for i,text in enumerate(['MCP 是一种连接模型与工具的协议。','它通过标准接口暴露资源和工具。','客户端发现能力后发起结构化调用。','服务端执行工具并返回结构化结果。'])])
    batch.commit(lambda c:core.db.update_video(1,raw_subtitle_path=ref,subtitle_language='zh',subtitle_source='ai',conn=c))
    def service(paths,*,status='sufficient',empty=False):
        judge=original.FakeJudge(status)
        value=Stage5PipelineService(db=core.db,artifacts=core.artifacts,
            evidence_search=original.StaticSearch(original._search_set(empty=empty)),
            trace_dir=paths.logs_dir/'stage5-pg',judge=judge)
        return value,judge
    monkeypatch.setattr(original,'_service',service)
    monkeypatch.setattr(original,'Application',lambda paths:core)
    try:yield core
    finally:core.close()


@pytest.mark.parametrize('status',['sufficient','partial','insufficient','unverifiable'])
def test_current_semantic_gate_four_states(current_stage5,app_paths,status):
    original.test_judge_eligible_pipeline_preserves_four_states_and_trace(app_paths,status)


def test_current_source_unverifiable_bypasses_judge(current_stage5,app_paths):
    original.test_source_unverifiable_bypasses_judge_and_preserves_terminal_status(app_paths)


def test_current_invalid_gate_bypasses_judge(current_stage5,app_paths):
    original.test_invalid_synthetic_gate_bypasses_judge(app_paths)


def test_current_evidence_sufficiency_api_and_trace(current_stage5,app_paths):
    original.test_api_contract_and_trace_route(app_paths)


@pytest.mark.parametrize('filters',[{'uploader':'Exact Creator'},{'uploader_contains':'creator'}])
def test_current_evidence_api_filter_dto(current_stage5,app_paths,filters):
    original.test_stage5_route_supports_exact_and_contains_uploader_fields(app_paths,filters)


def test_current_evidence_ui_contract(current_stage5,app_paths):
    original.test_stage5_ui_surface_and_safe_dom(app_paths)
