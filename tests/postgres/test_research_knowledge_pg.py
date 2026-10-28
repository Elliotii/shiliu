"""PG Research product -> review -> fact -> artifact -> published Topic Page."""
import pytest
from shiliu.research.product_service import ResearchProductService
from shiliu.research.control_service import ResearchControlService
from shiliu.research.knowledge_service import ResearchKnowledgeService
from shiliu.storage.errors import StorageError
from psycopg.types.json import Jsonb
from test_research_outer_pg import outer_core
from test_collection_retrieval import add_video
from test_v5_b_stage1_knowledge_workspace import (
    _terminal_task,_intake,ReviewKnowledgeCandidateRequest,BuildKnowledgeArtifactRequest,
    BuildTopicPageRequest,ReviewTopicPageRequest,IntakeKnowledgeCandidatesRequest,
    ResearchConflict,ResearchValidationError,KNOWLEDGE_WORKSPACE_SCHEMA_VERSION,
)

@pytest.fixture
def knowledge_core(outer_core,retrieval,tmp_path,monkeypatch):
    import test_v5_b_stage1_knowledge_workspace as original
    core=outer_core
    db,artifacts,lexical,dense=retrieval
    # Keep this original single-source vertical contract to one eligible video;
    # the shared outer fixture's source remains as ignored synthetic history.
    db.update_video(db.get_video_by_source("BV0000000001")["id"],is_ignored=True)
    _,vid=add_video(retrieval,index=2,text=original.OBJECTIVE+"。MCP 通过明确协议连接模型与外部工具。工具执行需要持久请求身份与幂等回执。失去 lease 的旧 worker 不得提交结果。")
    db.update_video(vid,title=original.OBJECTIVE)
    dense.rebuild()
    core.retrieval=lexical
    core.research_control=ResearchControlService(db,kernel=core.research)
    core.research_product=ResearchProductService(db=db,kernel=core.research,inner=core.research_inner,outer=core.research_outer,control=core.research_control)
    core.research_knowledge=ResearchKnowledgeService(db,kernel=core.research,product=core.research_product,retrieval=lexical,export_root=core.paths.content_dir/"knowledge-exports")
    monkeypatch.setattr(original,"_fixture_core",lambda paths:core)
    return core


def test_original_full_vertical_path_on_pg(knowledge_core):
    core = knowledge_core
    task_id = _terminal_task(core, "vertical")
    workspace = _intake(core, task_id, "vertical")
    second_intake = core.research_knowledge.intake_candidates(
        task_id,
        IntakeKnowledgeCandidatesRequest(command_id="v5b:intake:vertical:second"),
    )
    assert second_intake["candidate_ids"] == [
        workspace["candidates"][0]["candidate_id"]
    ]
    assert len(core.research_knowledge.get_workspace(task_id)["candidates"]) == 1
    candidate = workspace["candidates"][0]
    request = ReviewKnowledgeCandidateRequest(
        command_id="v5b:accept:vertical",
        decision="accept",
        expected_state_version=candidate["state_version"],
    )
    accepted = core.research_knowledge.review_candidate(
        task_id,
        candidate["candidate_id"],
        request,
        principal_id="local_operator",
    )
    assert accepted["status"] == "accepted"
    assert accepted["fact_revision_id"]
    assert all(
        value["outcome"] == "current" for value in accepted["validation_outcomes"]
    )
    replay = core.research_knowledge.review_candidate(
        task_id,
        candidate["candidate_id"],
        request,
        principal_id="local_operator",
    )
    assert replay["deduplicated"] is True
    with pytest.raises(ResearchConflict):
        core.research_knowledge.review_candidate(
            task_id,
            candidate["candidate_id"],
            ReviewKnowledgeCandidateRequest(
                command_id=request.command_id,
                decision="reject",
                expected_state_version=candidate["state_version"],
            ),
            principal_id="local_operator",
        )

    workspace = core.research_knowledge.get_workspace(task_id)
    fact = workspace["facts"][0]
    citation = fact["citations"][0]
    assert fact["revision"] == 1
    assert citation["accepted_outcome"] == "current"
    assert citation["current_outcome"] == "current"
    assert citation["jump_url"]
    assert citation["transcript_href"].startswith("/media/")
    other_task_id = _terminal_task(core, "cross-task")
    with pytest.raises(ResearchValidationError, match="accepted, current-grounded"):
        core.research_knowledge.build_artifact(
            other_task_id,
            BuildKnowledgeArtifactRequest(
                command_id="v5b:artifact:cross-task",
                fact_revision_ids=[fact["fact_revision_id"]],
            ),
        )
    with pytest.raises(ResearchValidationError, match="accepted, current-grounded"):
        core.research_knowledge.build_artifact(
            task_id,
            BuildKnowledgeArtifactRequest(
                command_id="v5b:artifact:forged",
                fact_revision_ids=["factrev_forged"],
            ),
        )
    artifact_request = BuildKnowledgeArtifactRequest(
        command_id="v5b:artifact:vertical",
        fact_revision_ids=[fact["fact_revision_id"]],
    )
    artifact = core.research_knowledge.build_artifact(task_id, artifact_request)
    assert artifact["revision"] == 1
    assert core.research_knowledge.build_artifact(
        task_id, artifact_request
    )["deduplicated"] is True
    with pytest.raises(ResearchConflict):
        core.research_knowledge.build_artifact(
            task_id,
            BuildKnowledgeArtifactRequest(
                command_id=artifact_request.command_id,
                fact_revision_ids=["factrev_forged"],
            ),
        )
    page = core.research_knowledge.build_topic_page(
        task_id,
        BuildTopicPageRequest(
            command_id="v5b:page:vertical",
            artifact_revision_id=artifact["artifact_revision_id"],
        ),
    )
    assert page["version"] == 1
    publish_request = ReviewTopicPageRequest(
        command_id="v5b:publish:vertical",
        decision="publish",
        expected_version=1,
    )
    published = core.research_knowledge.review_page(
        task_id,
        page["page_id"],
        publish_request,
        principal_id="local_operator",
    )
    assert published["review_status"] == "published"
    assert core.research_knowledge.review_page(
        task_id,
        page["page_id"],
        publish_request,
        principal_id="local_operator",
    )["deduplicated"] is True
    with pytest.raises(ResearchConflict):
        core.research_knowledge.review_page(
            task_id,
            page["page_id"],
            ReviewTopicPageRequest(
                command_id="v5b:return:late",
                decision="return",
                expected_version=1,
            ),
            principal_id="local_operator",
        )

    final = core.research_knowledge.get_workspace(task_id)
    assert final["workspace_schema_version"] == KNOWLEDGE_WORKSPACE_SCHEMA_VERSION
    assert final["authority"]["provider"] == "not_exercised"
    assert final["counts"] == {
        "candidates": 1,
        "facts": 1,
        "artifacts": 1,
        "pages": 1,
    }
    assert final["pages"][0]["review_status"] == "published"
    assert all(value["status"] == "succeeded" for value in final["build_runs"])
    assert final["artifacts"][0]["source"]["result_ids"]
    assert final["artifacts"][0]["source"]["boundary_hashes"]
    assert final["artifacts"][0]["source"]["corpus_snapshot"]["evidence"]
    # Original immutable-boundary assertions use the PG classified error and
    # explicit scoped SQL; each rejected statement has its own transaction.
    db=core.db
    for table,column,identity in [
        ("research_fact_revisions","fact_revision_id",fact["fact_revision_id"]),
        ("research_knowledge_candidates","candidate_id",candidate["candidate_id"]),
        ("research_events","event_id",candidate["source"]["event_id"]),
    ]:
        from psycopg import sql
        field="payload_json" if table=="research_events" else "claim_text"
        with pytest.raises(StorageError) as error:
            with db.connect() as conn:
                conn.execute(sql.SQL("UPDATE {} SET {}=%s WHERE workspace_id=%s AND {}=%s").format(sql.Identifier(table),sql.Identifier(field),sql.Identifier(column)),(Jsonb({}) if field=="payload_json" else "forged",db.workspace_id,identity))
        assert error.value.sqlstate=="23514"
    with db.connect(read_only=True) as conn:
        assert conn.execute("SELECT count(*) AS n FROM research_topic_page_review_decisions WHERE workspace_id=%s AND task_id=%s",(db.workspace_id,task_id)).fetchone()["n"]==1


@pytest.mark.parametrize("outcome",["missing","invalid","error"])
def test_original_noncurrent_authority_blocks_fact_on_pg(knowledge_core,app_paths,outcome):
    import test_v5_b_stage1_knowledge_workspace as original
    original.test_each_noncurrent_authority_outcome_blocks_fact(app_paths,outcome)


def test_original_public_knowledge_api_on_pg(knowledge_core,app_paths):
    import test_v5_b_stage1_knowledge_workspace as original
    original.test_public_api_runs_the_complete_stage1_vertical_path(app_paths)
