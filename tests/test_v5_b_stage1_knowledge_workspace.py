from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.db import SCHEMA_VERSION
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.research.errors import (
    ResearchConflict,
    ResearchUnsafeState,
    ResearchValidationError,
    SimulatedCrash,
)
from shiliu.research.knowledge_contracts import (
    BuildKnowledgeArtifactRequest,
    BuildTopicPageRequest,
    IntakeKnowledgeCandidatesRequest,
    ReviewKnowledgeCandidateRequest,
    ReviewTopicPageRequest,
)
from shiliu.research.knowledge_service import ResearchKnowledgeService
from shiliu.research.inner_evidence import CurrentnessResult
from shiliu.research.product_contracts import (
    CreateProductResearchRequest,
    RunProductResearchRequest,
)
from shiliu.research.schema import KNOWLEDGE_WORKSPACE_SCHEMA_VERSION
from shiliu.retrieval.coordinator import SYNC_STATE_VERSION
from shiliu.web import create_web_app


OBJECTIVE = "请解释 MCP 工具执行为何需要幂等回执"


def _fixture_core(app_paths: object) -> Application:
    core = Application(app_paths)
    source_db_id = core.db.create_favorite_source(
        folder_id=5101, folder_title="V5-B Stage 1 Fixture"
    )
    item = FavoriteItem(
        bvid="BV5101000001",
        title="V5-B Grounded Knowledge Fixture",
        uploader="V5B",
        favorite_time=1,
    )
    core.db.record_source_snapshot(
        source_db_id, [item], processing_profile="formal"
    )
    video = core.db.get_video_by_source(item.bvid)
    assert video is not None
    video_id = int(video["id"])
    _, raw_path = core.artifacts.save_raw_subtitle(
        item.bvid,
        [
            SubtitleSegment.model_validate(
                {"from": index * 5, "to": index * 5 + 4, "content": text}
            )
            for index, text in enumerate(
                (
                    "MCP 通过明确协议连接模型与外部工具。",
                    "工具执行需要持久请求身份与幂等回执。",
                    "失去 lease 的旧 worker 不得提交结果。",
                    "checkpoint 让长期任务可以安全恢复。",
                    "答案必须引用当前版本的权威字幕。",
                    OBJECTIVE,
                )
            )
        ],
    )
    core.db.update_video(
        video_id,
        title=item.title,
        uploader=item.uploader,
        status="completed",
        raw_subtitle_path=str(raw_path),
        subtitle_source="human",
        subtitle_language="zh",
    )
    core.retrieval.rebuild()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with core.db.connect() as connection:
        connection.execute(
            """
            INSERT INTO retrieval_sync_state(
                video_id, sync_state_version, desired_state, lexical_state,
                dense_state, last_trigger, last_attempt_at, last_success_at,
                last_error_stage, last_error_message, updated_at
            ) VALUES(?, ?, 'indexed', 'current', 'not_ready', 'test',
                     ?, ?, NULL, NULL, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                sync_state_version=excluded.sync_state_version,
                desired_state=excluded.desired_state,
                lexical_state=excluded.lexical_state,
                dense_state=excluded.dense_state,
                updated_at=excluded.updated_at
            """,
            (video_id, SYNC_STATE_VERSION, now, now, now),
        )
    return core


def _terminal_task(core: Application, suffix: str) -> str:
    created = core.research_product.create_task(
        CreateProductResearchRequest(
            command_id=f"v5b:create:{suffix}",
            objective=OBJECTIVE,
            success_constraints=[],
            run_immediately=False,
        )
    )
    task_id = str(created["task_id"])
    outcome = core.research_product.run_to_boundary(
        task_id,
        RunProductResearchRequest(command_id=f"v5b:run:{suffix}"),
    )
    assert outcome["task_status"] == "terminal"
    return task_id


def _intake(core: Application, task_id: str, suffix: str) -> dict[str, object]:
    outcome = core.research_knowledge.intake_candidates(
        task_id,
        IntakeKnowledgeCandidatesRequest(command_id=f"v5b:intake:{suffix}"),
    )
    assert outcome["candidate_count"] >= 1
    return core.research_knowledge.get_workspace(task_id)


def _accept_first(
    service: ResearchKnowledgeService, task_id: str, workspace: dict[str, object], suffix: str
) -> dict[str, object]:
    candidate = workspace["candidates"][0]  # type: ignore[index]
    return service.review_candidate(
        task_id,
        candidate["candidate_id"],  # type: ignore[index]
        ReviewKnowledgeCandidateRequest(
            command_id=f"v5b:accept:{suffix}",
            decision="accept",
            expected_state_version=candidate["state_version"],  # type: ignore[index]
        ),
        principal_id="local_operator",
    )


def test_stage1_schema_is_temp_db_only_reentrant_and_exposes_minimal_ui(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    assert SCHEMA_VERSION == 16
    assert core.db.path == app_paths.database
    core.db.initialize()
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == "16"
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            ).fetchall()
        }
        assert {
            "research_knowledge_candidates",
            "research_grounded_facts",
            "research_fact_revisions",
            "research_knowledge_artifact_revisions",
            "research_topic_page_revisions",
            "research_knowledge_build_runs",
        } <= tables
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    client = TestClient(create_web_app(core))
    page = client.get("/research")
    script = client.get("/static/research.js?v=1")
    assert page.status_code == 200
    assert "知识生命周期与 Topic Page 刷新" in page.text
    assert "data-knowledge-intake" in page.text
    assert "publish-or-return" in page.text
    assert script.status_code == 200
    assert "knowledgeAction('/intake'" in script.text
    assert "Accept → Fact" in script.text
    assert "Edit as new Candidate" in script.text
    assert "transcript_href" in script.text


def test_full_vertical_path_is_current_grounded_idempotent_and_immutable(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
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
    with core.db.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="fact revision is immutable"):
            connection.execute(
                "UPDATE research_fact_revisions SET claim_text='forged' "
                "WHERE fact_revision_id=?",
                (fact["fact_revision_id"],),
            )
    with core.db.connect() as connection:
        with pytest.raises(
            sqlite3.IntegrityError, match="candidate lineage is immutable"
        ):
            connection.execute(
                "UPDATE research_knowledge_candidates SET claim_text='forged' "
                "WHERE candidate_id=?",
                (candidate["candidate_id"],),
            )
    with core.db.connect() as connection:
        source_event_id = candidate["source"]["event_id"]
        with pytest.raises(sqlite3.IntegrityError, match="delta event is immutable"):
            connection.execute(
                "UPDATE research_events SET payload_json='{}' WHERE event_id=?",
                (source_event_id,),
            )
        assert connection.execute(
            "SELECT COUNT(*) FROM research_topic_page_review_decisions "
            "WHERE task_id=?",
            (task_id,),
        ).fetchone()[0] == 1


def test_edit_is_new_needs_revalidation_reject_creates_no_fact_and_stale_fails_closed(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    task_id = _terminal_task(core, "edit")
    workspace = _intake(core, task_id, "edit")
    candidate = workspace["candidates"][0]
    edited = core.research_knowledge.review_candidate(
        task_id,
        candidate["candidate_id"],
        ReviewKnowledgeCandidateRequest(
            command_id="v5b:edit",
            decision="edit",
            edited_claim=f"{candidate['claim']}（用户修订）",
            expected_state_version=0,
        ),
        principal_id="local_operator",
    )
    assert edited["status"] == "superseded"
    assert edited["edited_candidate_status"] == "needs_revalidation"
    workspace = core.research_knowledge.get_workspace(task_id)
    child = next(
        value
        for value in workspace["candidates"]
        if value["candidate_id"] == edited["edited_candidate_id"]
    )
    assert child["parent_candidate_id"] == candidate["candidate_id"]
    with pytest.raises(ResearchUnsafeState, match="validator"):
        core.research_knowledge.review_candidate(
            task_id,
            child["candidate_id"],
            ReviewKnowledgeCandidateRequest(
                command_id="v5b:edited:accept",
                decision="accept",
                expected_state_version=0,
            ),
            principal_id="local_operator",
        )
    rejected = core.research_knowledge.review_candidate(
        task_id,
        child["candidate_id"],
        ReviewKnowledgeCandidateRequest(
            command_id="v5b:edited:reject",
            decision="reject",
            expected_state_version=0,
        ),
        principal_id="local_operator",
    )
    assert rejected["status"] == "rejected"
    assert core.research_knowledge.get_workspace(task_id)["facts"] == []

    stale_task = _terminal_task(core, "stale")
    stale_workspace = _intake(core, stale_task, "stale")
    video = core.db.get_video_by_source("BV5101000001")
    assert video is not None
    core.artifacts.save_raw_subtitle(
        "BV5101000001",
        [
            SubtitleSegment.model_validate(
                {"from": 0, "to": 4, "content": "来源已在 temp fixture 中变化。"}
            )
        ],
    )
    stale = _accept_first(
        core.research_knowledge, stale_task, stale_workspace, "stale"
    )
    assert stale["status"] == "needs_revalidation"
    assert stale["fact_revision_id"] is None
    assert any(value["outcome"] != "current" for value in stale["validation_outcomes"])
    assert core.research_knowledge.get_workspace(stale_task)["facts"] == []


@pytest.mark.parametrize("outcome", ["missing", "invalid", "error"])
def test_each_noncurrent_authority_outcome_blocks_fact(app_paths, outcome: str) -> None:
    core = _fixture_core(app_paths)
    task_id = _terminal_task(core, f"noncurrent-{outcome}")
    workspace = _intake(core, task_id, f"noncurrent-{outcome}")

    class NoncurrentAuthority:
        def observe(self, identity):
            return CurrentnessResult(
                outcome=outcome,
                reason_code=f"forced_{outcome}",
                expected_source_version=str(identity["source_version"]),
                observed_source_version=None,
                span=None,
            )

    core.research_knowledge.authority = NoncurrentAuthority()  # type: ignore[assignment]
    result = _accept_first(
        core.research_knowledge,
        task_id,
        workspace,
        f"noncurrent-{outcome}",
    )
    assert result["status"] == "needs_revalidation"
    assert result["fact_revision_id"] is None
    assert result["validation_outcomes"][0]["outcome"] == outcome
    assert core.research_knowledge.get_workspace(task_id)["facts"] == []


def test_build_reservation_survives_crash_output_rolls_back_and_api_completes(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    task_id = _terminal_task(core, "crash")
    workspace = _intake(core, task_id, "crash")
    candidate = workspace["candidates"][0]
    points = {
        "after_initial_fact_revision",
        "after_artifact_build_reserved",
        "after_initial_topic_page_revision",
        "after_topic_page_review_decision",
    }

    def crash_once(point: str) -> None:
        if point in points:
            points.remove(point)
            raise SimulatedCrash(point)

    service = ResearchKnowledgeService(
        core.db,
        kernel=core.research,
        product=core.research_product,
        retrieval=core.retrieval,
        fault_injector=crash_once,
    )
    accept_request = ReviewKnowledgeCandidateRequest(
        command_id="v5b:accept:crash",
        decision="accept",
        expected_state_version=0,
    )
    with pytest.raises(SimulatedCrash, match="after_initial_fact_revision"):
        service.review_candidate(
            task_id,
            candidate["candidate_id"],
            accept_request,
            principal_id="local_operator",
        )
    rolled_back = service.get_workspace(task_id)
    assert rolled_back["facts"] == []
    assert rolled_back["candidates"][0]["status"] == "pending_review"
    accepted = service.review_candidate(
        task_id,
        candidate["candidate_id"],
        accept_request,
        principal_id="local_operator",
    )
    assert accepted["status"] == "accepted"
    fact = service.get_workspace(task_id)["facts"][0]
    artifact_request = BuildKnowledgeArtifactRequest(
        command_id="v5b:artifact:crash",
        fact_revision_ids=[fact["fact_revision_id"]],
    )
    with pytest.raises(SimulatedCrash, match="after_artifact_build_reserved"):
        service.build_artifact(task_id, artifact_request)
    with core.db.connect() as connection:
        run = connection.execute(
            "SELECT status, attempt_count FROM research_knowledge_build_runs "
            "WHERE task_id=? AND build_kind='artifact'",
            (task_id,),
        ).fetchone()
        assert dict(run) == {"status": "running", "attempt_count": 1}
        assert connection.execute(
            "SELECT COUNT(*) FROM research_knowledge_artifact_revisions WHERE task_id=?",
            (task_id,),
        ).fetchone()[0] == 0
    artifact = service.build_artifact(task_id, artifact_request)
    with core.db.connect() as connection:
        run = connection.execute(
            "SELECT status, attempt_count FROM research_knowledge_build_runs "
            "WHERE task_id=? AND build_kind='artifact'",
            (task_id,),
        ).fetchone()
        assert dict(run) == {"status": "succeeded", "attempt_count": 2}

    page_request = BuildTopicPageRequest(
        command_id="v5b:page:crash",
        artifact_revision_id=artifact["artifact_revision_id"],
    )
    with pytest.raises(SimulatedCrash, match="after_initial_topic_page_revision"):
        service.build_topic_page(task_id, page_request)
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_topic_page_revisions WHERE task_id=?",
            (task_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT status FROM research_knowledge_build_runs "
            "WHERE task_id=? AND build_kind='topic_page'",
            (task_id,),
        ).fetchone()[0] == "running"
    page = service.build_topic_page(task_id, page_request)
    assert page["version"] == 1

    review_request = ReviewTopicPageRequest(
        command_id="v5b:api:return",
        decision="return",
        expected_version=1,
        reason="needs another research task",
    )
    with pytest.raises(SimulatedCrash, match="after_topic_page_review_decision"):
        service.review_page(
            task_id,
            page["page_id"],
            review_request,
            principal_id="local_operator",
        )
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT review_status FROM research_topic_pages WHERE page_id=?",
            (page["page_id"],),
        ).fetchone()[0] == "draft"
        assert connection.execute(
            "SELECT COUNT(*) FROM research_topic_page_review_decisions "
            "WHERE page_id=?",
            (page["page_id"],),
        ).fetchone()[0] == 0

    client = TestClient(create_web_app(core))
    detail = client.get(f"/api/research/product/tasks/{task_id}/knowledge")
    assert detail.status_code == 200
    assert detail.json()["workspace"]["counts"]["pages"] == 1
    reviewed = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/pages/{page['page_id']}/review",
        json=review_request.model_dump(mode="json"),
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["outcome"]["review_status"] == "returned"
    with core.db.connect() as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_public_api_runs_the_complete_stage1_vertical_path(app_paths) -> None:
    core = _fixture_core(app_paths)
    task_id = _terminal_task(core, "public-api")
    client = TestClient(create_web_app(core))

    intake = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/intake",
        json={"command_id": "v5b:api:intake"},
    )
    assert intake.status_code == 200
    candidate_id = intake.json()["outcome"]["candidate_ids"][0]
    detail = client.get(f"/api/research/product/tasks/{task_id}/knowledge")
    candidate = detail.json()["workspace"]["candidates"][0]
    assert candidate["candidate_id"] == candidate_id
    assert candidate["evidence"][0]["current_outcome"] == "current"

    accepted = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/candidates/{candidate_id}/review",
        json={
            "command_id": "v5b:api:accept",
            "decision": "accept",
            "expected_state_version": 0,
        },
    )
    assert accepted.status_code == 200
    fact_revision_id = accepted.json()["outcome"]["fact_revision_id"]
    artifact = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/artifacts",
        json={
            "command_id": "v5b:api:artifact",
            "fact_revision_ids": [fact_revision_id],
        },
    )
    assert artifact.status_code == 201
    artifact_revision_id = artifact.json()["outcome"]["artifact_revision_id"]
    page = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/pages",
        json={
            "command_id": "v5b:api:page",
            "artifact_revision_id": artifact_revision_id,
        },
    )
    assert page.status_code == 201
    page_id = page.json()["outcome"]["page_id"]
    published = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/pages/{page_id}/review",
        json={
            "command_id": "v5b:api:publish",
            "decision": "publish",
            "expected_version": 1,
        },
    )
    assert published.status_code == 200
    assert published.json()["outcome"]["review_status"] == "published"
    final = client.get(
        f"/api/research/product/tasks/{task_id}/knowledge"
    ).json()["workspace"]
    assert final["counts"] == {
        "candidates": 1,
        "facts": 1,
        "artifacts": 1,
        "pages": 1,
    }
    assert final["facts"][0]["citations"][0]["transcript_href"]
