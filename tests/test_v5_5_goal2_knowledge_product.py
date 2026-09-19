from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shiliu.research.errors import ResearchUnsafeState
from shiliu.research.knowledge_contracts import (
    AssessArtifactRouteRequest,
    IntakeKnowledgeCandidatesRequest,
    ProceedArtifactRouteRequest,
    PublishKnowledgeSelection,
    PublishResearchKnowledgeRequest,
)
from shiliu.research.product_contracts import CreateProductResearchRequest
from shiliu.web import create_web_app
from test_v5_b_stage1_knowledge_workspace import (
    _fixture_core,
    _intake,
    _terminal_task,
)


def _publish(core, task_id: str, *, command_id: str = "v55:g2:publish") -> dict:
    workspace = core.research_knowledge.get_workspace(task_id)
    selections = [
        PublishKnowledgeSelection(
            candidate_id=value["candidate_id"],
            expected_state_version=value["state_version"],
        )
        for value in workspace["candidates"]
        if value["status"] == "pending_review"
    ]
    return core.research_knowledge.publish_selected_candidates(
        task_id,
        PublishResearchKnowledgeRequest(
            command_id=command_id,
            selections=selections,
        ),
        principal_id="local_operator",
    )


def test_goal2_explicit_publish_reuses_v5b_steps_and_is_retry_safe(app_paths) -> None:
    core = _fixture_core(app_paths)
    task_id = _terminal_task(core, "v55-goal2-publish")
    workspace = _intake(core, task_id, "v55-goal2-publish")
    assert workspace["candidates"]
    assert workspace["facts"] == []
    assert workspace["artifacts"] == []
    assert workspace["pages"] == []

    request_payload = {
        "command_id": "v55:g2:web-publish",
        "selections": [
            {
                "candidate_id": value["candidate_id"],
                "expected_state_version": value["state_version"],
            }
            for value in workspace["candidates"]
        ],
    }
    client = TestClient(create_web_app(core))
    response = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/publish",
        json=request_payload,
    )
    assert response.status_code == 201
    first = response.json()["outcome"]
    assert first["review_status"] == "published"

    replay = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/publish",
        json=request_payload,
    )
    assert replay.status_code == 201
    assert replay.json()["outcome"] == first

    published = core.research_knowledge.get_workspace(task_id)
    assert all(value["status"] == "accepted" for value in published["candidates"])
    assert published["facts"]
    assert len(published["artifacts"]) == 1
    assert len(published["pages"]) == 1
    assert published["pages"][0]["review_status"] == "published"
    assert published["pages"][0]["published_version"] == 1
    assert all(
        citation["current_outcome"] == "current"
        and citation["transcript_href"].startswith(("/videos/", "/media/"))
        for fact in published["facts"]
        for citation in fact["citations"]
    )

    html = client.get(f"/research/{task_id}").text
    script = client.get("/static/research.js").text
    assert "保存到知识" in html
    assert "只有你明确确认后" in html
    assert "检查已有知识" in html
    assert "知识维护与高级诊断" in html
    assert "确认发布" in script
    assert "/knowledge/publish" in script
    assert "下钻到原始字幕" in script
    assert "已有知识足够，可以直接使用" in script


def test_goal2_related_but_different_question_directly_reuses_published_knowledge(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    task_id = _terminal_task(core, "v55-goal2-reuse")
    _intake(core, task_id, "v55-goal2-reuse")
    published = _publish(core, task_id, command_id="v55:g2:reuse-publish")

    assessed = core.research_knowledge.assess_artifact_route(
        task_id,
        AssessArtifactRouteRequest(
            command_id="v55:g2:related-question",
            query="什么时候应该为 MCP 工具执行增加可恢复的幂等保护？",
            required_aspects=["幂等回执"],
        ),
    )
    assert assessed["recommended_route"] == "direct_reuse"
    assert assessed["selected_artifact_revision_id"] == published[
        "artifact_revision_id"
    ]
    assert assessed["gates"][0]["citation_status"] == "pass"
    assert assessed["gates"][0]["completeness_status"] == "complete"
    assert assessed["gates"][0]["facts"][0]["citations"][0][
        "transcript_href"
    ].startswith("/media/")

    reused = core.research_knowledge.proceed_artifact_route(
        task_id,
        assessed["route_id"],
        ProceedArtifactRouteRequest(
            command_id="v55:g2:confirm-reuse",
            route="direct_reuse",
            expected_version=1,
            reason="user confirmed existing knowledge reuse",
        ),
        principal_id="local_operator",
    )
    assert reused["status"] == "completed"
    assert reused["final_route"] == "direct_reuse"
    assert reused["outcome_artifact_revision_id"] == published[
        "artifact_revision_id"
    ]
    assert reused["continuation_task_id"] is None


def test_goal2_incomplete_research_cannot_enter_publish_flow(app_paths) -> None:
    core = _fixture_core(app_paths)
    created = core.research_product.create_task(
        CreateProductResearchRequest(
            command_id="v55:g2:incomplete-create",
            objective="尚未执行完成的研究不能发布为长期知识",
            success_constraints=[],
            run_immediately=False,
        )
    )
    task_id = str(created["task_id"])
    with pytest.raises(ResearchUnsafeState, match="KnowledgeDelta"):
        core.research_knowledge.intake_candidates(
            task_id,
            IntakeKnowledgeCandidatesRequest(command_id="v55:g2:incomplete-intake"),
        )
    workspace = core.research_knowledge.get_workspace(task_id)
    assert workspace["candidates"] == []
    assert workspace["facts"] == []
    assert workspace["artifacts"] == []
    assert workspace["pages"] == []
