from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.db import SCHEMA_VERSION
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.research.errors import (
    ResearchConflict,
    ResearchValidationError,
    SimulatedCrash,
)
from shiliu.research.knowledge_contracts import (
    AssessArtifactRouteRequest,
    BuildKnowledgeArtifactRequest,
    BuildTopicPageRequest,
    IntakeKnowledgeCandidatesRequest,
    ProceedArtifactRouteRequest,
    ReviewKnowledgeCandidateRequest,
    ReviewTopicPageRequest,
)
from shiliu.research.product_contracts import (
    CreateProductResearchRequest,
    RunProductResearchRequest,
)
from shiliu.retrieval.coordinator import SYNC_STATE_VERSION
from shiliu.web import create_web_app


OBJECTIVE = "请解释 MCP 工具执行为何需要幂等回执"
GAP = "幂等回执需要记录设备级重试代次"


def _core(app_paths) -> Application:
    core = Application(app_paths)
    source_id = core.db.create_favorite_source(
        folder_id=5303, folder_title="V5-B Stage 3 Fixture"
    )
    item = FavoriteItem(
        bvid="BV5303000001",
        title="V5-B Artifact Reuse Fixture",
        uploader="V5B",
        favorite_time=1,
    )
    core.db.record_source_snapshot(source_id, [item], processing_profile="formal")
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


def _vertical(core: Application, suffix: str) -> tuple[str, dict, dict, dict]:
    created = core.research_product.create_task(
        CreateProductResearchRequest(
            command_id=f"v5b3:create:{suffix}",
            objective=OBJECTIVE,
            success_constraints=[],
            run_immediately=False,
        )
    )
    task_id = str(created["task_id"])
    outcome = core.research_product.run_to_boundary(
        task_id, RunProductResearchRequest(command_id=f"v5b3:run:{suffix}")
    )
    assert outcome["task_status"] == "terminal"
    core.research_knowledge.intake_candidates(
        task_id,
        IntakeKnowledgeCandidatesRequest(command_id=f"v5b3:intake:{suffix}"),
    )
    candidate = core.research_knowledge.get_workspace(task_id)["candidates"][0]
    core.research_knowledge.review_candidate(
        task_id,
        candidate["candidate_id"],
        ReviewKnowledgeCandidateRequest(
            command_id=f"v5b3:accept:{suffix}",
            decision="accept",
            expected_state_version=candidate["state_version"],
        ),
        principal_id="local_operator",
    )
    fact = core.research_knowledge.get_workspace(task_id)["facts"][0]
    artifact = core.research_knowledge.build_artifact(
        task_id,
        BuildKnowledgeArtifactRequest(
            command_id=f"v5b3:artifact:{suffix}",
            fact_revision_ids=[fact["fact_revision_id"]],
        ),
    )
    page = core.research_knowledge.build_topic_page(
        task_id,
        BuildTopicPageRequest(
            command_id=f"v5b3:page:{suffix}",
            artifact_revision_id=artifact["artifact_revision_id"],
        ),
    )
    core.research_knowledge.review_page(
        task_id,
        page["page_id"],
        ReviewTopicPageRequest(
            command_id=f"v5b3:publish:{suffix}",
            decision="publish",
            expected_version=1,
        ),
        principal_id="local_operator",
    )
    workspace = core.research_knowledge.get_workspace(task_id)
    fact = next(value for value in workspace["facts"] if value["is_current_revision"])
    artifact = workspace["artifacts"][0]
    page = workspace["pages"][0]
    return task_id, fact, artifact, page


def _add_gap_source(core: Application, suffix: str) -> None:
    source_id = core.db.create_favorite_source(
        folder_id=5390 + len(suffix), folder_title=f"V5-B Gap {suffix}"
    )
    item = FavoriteItem(
        bvid=f"BV53{len(suffix):02d}999999",
        title=f"Stage 3 bounded gap {suffix}",
        uploader="V5B-gap",
        favorite_time=2,
    )
    core.db.record_source_snapshot(source_id, [item], processing_profile="formal")
    video = core.db.get_video_by_source(item.bvid)
    assert video is not None
    video_id = int(video["id"])
    _, raw_path = core.artifacts.save_raw_subtitle(
        item.bvid,
        [SubtitleSegment.model_validate({"from": 0, "to": 5, "content": GAP})],
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


def _assess(
    core: Application,
    task_id: str,
    *,
    suffix: str,
    query: str,
    aspects: list[str],
) -> dict:
    return core.research_knowledge.assess_artifact_route(
        task_id,
        AssessArtifactRouteRequest(
            command_id=f"v5b3:route:{suffix}",
            query=query,
            required_aspects=aspects,
        ),
    )


def _accept_child_fact(core: Application, child_task_id: str, suffix: str) -> dict:
    outcome = core.research_product.run_to_boundary(
        child_task_id,
        RunProductResearchRequest(command_id=f"v5b3:child-run:{suffix}"),
    )
    assert outcome["task_status"] == "terminal"
    core.research_knowledge.intake_candidates(
        child_task_id,
        IntakeKnowledgeCandidatesRequest(command_id=f"v5b3:child-intake:{suffix}"),
    )
    candidate = core.research_knowledge.get_workspace(child_task_id)["candidates"][0]
    core.research_knowledge.review_candidate(
        child_task_id,
        candidate["candidate_id"],
        ReviewKnowledgeCandidateRequest(
            command_id=f"v5b3:child-accept:{suffix}",
            decision="accept",
            expected_state_version=candidate["state_version"],
        ),
        principal_id="local_operator",
    )
    return next(
        value
        for value in core.research_knowledge.get_workspace(child_task_id)["facts"]
        if value["is_current_revision"]
    )


def test_stage3_schema_direct_route_open_lane_api_ui_and_citation(app_paths) -> None:
    core = _core(app_paths)
    task_id, fact, artifact, page = _vertical(core, "direct")
    assert SCHEMA_VERSION == 16
    with core.db.connect() as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='research_artifact_routes'"
        ).fetchall()
        assert [str(row[0]) for row in tables] == ["research_artifact_routes"]

    assessed = _assess(
        core,
        task_id,
        suffix="direct",
        query=fact["claim"],
        aspects=[fact["claim"]],
    )
    assert assessed["recommended_route"] == "direct_reuse"
    assert assessed["gates"][0]["score_reason"]["authority"] == "ranking_only"
    assert assessed["gates"][0]["scope_status"] == "exact"
    assert assessed["gates"][0]["completeness_status"] == "complete"
    assert assessed["gates"][0]["citation_status"] == "pass"
    assert assessed["gates"][0]["facts"][0]["citations"][0]["outcome"] == "current"
    assert assessed["open_corpus"]["independent_lane"] is True
    assert assessed["open_corpus"]["hard_filter"] is False
    assert assessed["open_corpus"]["results"]

    proceeded = core.research_knowledge.proceed_artifact_route(
        task_id,
        assessed["route_id"],
        ProceedArtifactRouteRequest(
            command_id="v5b3:proceed:direct",
            action="confirm",
            expected_version=1,
            route="direct_reuse",
        ),
        principal_id="local_operator",
    )
    assert proceeded["status"] == "completed"
    assert proceeded["outcome_artifact_revision_id"] == artifact["artifact_revision_id"]
    assert proceeded["continuation_task_id"] is None
    replay = core.research_knowledge.proceed_artifact_route(
        task_id,
        assessed["route_id"],
        ProceedArtifactRouteRequest(
            command_id="v5b3:proceed:direct",
            action="confirm",
            expected_version=1,
            route="direct_reuse",
        ),
        principal_id="local_operator",
    )
    assert replay["deduplicated"] is True
    workspace = core.research_knowledge.get_workspace(task_id)
    assert len(workspace["artifacts"]) == 1
    assert workspace["pages"][0]["page_revision_id"] == page["page_revision_id"]
    with core.db.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE research_artifact_routes SET status='superseded' WHERE route_id=?",
                (assessed["route_id"],),
            )

    client = TestClient(create_web_app(core))
    api_assess = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/routes/assess",
        json={
            "command_id": "v5b3:api:assess",
            "query": fact["claim"],
            "required_aspects": [fact["claim"]],
            "temporal_scope": {},
            "viewpoint_scope": {},
            "max_artifact_candidates": 5,
            "max_open_results": 5,
        },
    )
    assert api_assess.status_code == 201
    api_route = api_assess.json()["outcome"]
    assert api_route["recommended_route"] == "direct_reuse"
    api_proceed = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/routes/{api_route['route_id']}/proceed",
        json={
            "command_id": "v5b3:api:proceed",
            "action": "confirm",
            "expected_version": 1,
            "route": "direct_reuse",
            "reason": "public journey",
        },
    )
    assert api_proceed.status_code == 200
    assert api_proceed.json()["outcome"]["final_route"] == "direct_reuse"
    api = client.get(
        f"/api/research/product/tasks/{task_id}/knowledge/routes/{assessed['route_id']}"
    )
    assert api.status_code == 200
    assert api.json()["route"]["latest"]["final_route"] == "direct_reuse"
    html = client.get(f"/research/{task_id}").text
    js = client.get("/static/research.js").text
    assert "Artifact reuse route" in html
    assert "data-artifact-route-form" in html
    assert "/knowledge/routes/assess" in js
    assert "independent open corpus" in js


def test_direct_fails_closed_for_ambiguous_stale_and_late_authority(app_paths) -> None:
    core = _core(app_paths)
    task_id, fact, _, _ = _vertical(core, "fence")
    ambiguous = _assess(
        core, task_id, suffix="ambiguous", query=fact["claim"], aspects=[]
    )
    assert ambiguous["recommended_route"] == "research_seed"
    with pytest.raises(ResearchValidationError, match="unsafe route override"):
        core.research_knowledge.proceed_artifact_route(
            task_id,
            ambiguous["route_id"],
            ProceedArtifactRouteRequest(
                command_id="v5b3:unsafe-direct",
                expected_version=1,
                route="direct_reuse",
            ),
            principal_id="local_operator",
        )

    direct = _assess(
        core,
        task_id,
        suffix="late",
        query=fact["claim"],
        aspects=[fact["claim"]],
    )
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE research_knowledge_fact_states SET currentness_status='stale', "
            "state_version=state_version+1 WHERE fact_id=?",
            (fact["fact_id"],),
        )
    with pytest.raises(ResearchConflict, match="authority snapshot changed"):
        core.research_knowledge.proceed_artifact_route(
            task_id,
            direct["route_id"],
            ProceedArtifactRouteRequest(
                command_id="v5b3:late-direct",
                expected_version=1,
                route="direct_reuse",
            ),
            principal_id="local_operator",
        )
    stale = _assess(
        core,
        task_id,
        suffix="stale",
        query=fact["claim"],
        aspects=[fact["claim"]],
    )
    assert stale["recommended_route"] == "research_seed"
    safer = core.research_knowledge.proceed_artifact_route(
        task_id,
        stale["route_id"],
        ProceedArtifactRouteRequest(
            command_id="v5b3:safer-seed",
            expected_version=1,
            route="research_seed",
        ),
        principal_id="local_operator",
    )
    assert safer["final_route"] == "research_seed"
    assert safer["continuation_task_id"]
    with pytest.raises(ResearchConflict, match="payload hash"):
        core.research_knowledge.assess_artifact_route(
            task_id,
            AssessArtifactRouteRequest(
                command_id="v5b3:route:stale",
                query="different payload",
                required_aspects=["different payload"],
            ),
        )


def test_incremental_refresh_reuses_core_and_commits_contribution_lineage(app_paths) -> None:
    core = _core(app_paths)
    task_id, fact, artifact, page = _vertical(core, "incremental")
    _add_gap_source(core, "incremental")
    assessed = _assess(
        core,
        task_id,
        suffix="incremental",
        query=f"{fact['claim']}；{GAP}",
        aspects=[fact["claim"], GAP],
    )
    assert assessed["recommended_route"] == "incremental_refresh"
    gate = assessed["gates"][0]
    assert gate["reused_fact_revision_ids"] == [fact["fact_revision_id"]]
    assert gate["missing_aspects"] == [GAP]
    confirmed = core.research_knowledge.proceed_artifact_route(
        task_id,
        assessed["route_id"],
        ProceedArtifactRouteRequest(
            command_id="v5b3:proceed:incremental",
            expected_version=1,
            route="incremental_refresh",
        ),
        principal_id="local_operator",
    )
    child_task_id = confirmed["continuation_task_id"]
    assert child_task_id
    restarted = Application(core.paths)
    assert restarted.research_knowledge.get_artifact_route(
        task_id, assessed["route_id"]
    )["latest"]["continuation_task_id"] == child_task_id
    with restarted.db.connect() as connection:
        goal = connection.execute(
            "SELECT * FROM research_goals WHERE task_id=?", (child_task_id,)
        ).fetchone()
        policy = json.loads(str(goal["evidence_policy_json"]))
        assert policy["target_aspects"] == [GAP]
        assert policy["artifact_context_authority"] == "candidate_only_not_verifier"
        assert policy["open_retrieval_required"] is True
    new_fact = _accept_child_fact(restarted, child_task_id, "incremental")
    assert GAP in new_fact["claim"]
    finalized = restarted.research_knowledge.proceed_artifact_route(
        task_id,
        assessed["route_id"],
        ProceedArtifactRouteRequest(
            command_id="v5b3:finalize:incremental",
            action="finalize",
            expected_version=2,
            new_fact_aspect_map={GAP: new_fact["fact_revision_id"]},
        ),
        principal_id="local_operator",
    )
    assert finalized["status"] == "completed"
    assert finalized["outcome_artifact_revision_id"] != artifact["artifact_revision_id"]
    assert finalized["contribution"]["reused"][0]["fact_revision_id"] == fact["fact_revision_id"]
    assert finalized["contribution"]["newly_researched"][0]["aspect"] == GAP
    assert finalized["contribution"]["newly_researched"][0]["citations"][0]["outcome"] == "current"
    workspace = restarted.research_knowledge.get_workspace(task_id)
    assert len(workspace["artifacts"]) == 2
    assert workspace["pages"][0]["page_revision_id"] == page["page_revision_id"]
    assert workspace["pages"][0]["published_version"] == 1


def test_incremental_late_fence_cross_task_and_fault_leave_no_orphans(app_paths) -> None:
    core = _core(app_paths)
    task_id, fact, _, _ = _vertical(core, "rollback")
    _add_gap_source(core, "rollback")
    assessed = _assess(
        core,
        task_id,
        suffix="rollback",
        query=f"{fact['claim']}；{GAP}",
        aspects=[fact["claim"], GAP],
    )
    core.research_knowledge.fault_injector = lambda point: (
        (_ for _ in ()).throw(SimulatedCrash(point))
        if point == "after_stage3_continuation_task"
        else None
    )
    with pytest.raises(SimulatedCrash, match="after_stage3_continuation_task"):
        core.research_knowledge.proceed_artifact_route(
            task_id,
            assessed["route_id"],
            ProceedArtifactRouteRequest(
                command_id="v5b3:rollback-child",
                expected_version=1,
                route="incremental_refresh",
            ),
            principal_id="local_operator",
        )
    core.research_knowledge.fault_injector = lambda _point: None
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_tasks WHERE parent_task_id=?", (task_id,)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM research_artifact_routes WHERE route_id=?",
            (assessed["route_id"],),
        ).fetchone()[0] == 1

    confirmed = core.research_knowledge.proceed_artifact_route(
        task_id,
        assessed["route_id"],
        ProceedArtifactRouteRequest(
            command_id="v5b3:rollback-child",
            expected_version=1,
            route="incremental_refresh",
        ),
        principal_id="local_operator",
    )
    child = confirmed["continuation_task_id"]
    new_fact = _accept_child_fact(core, child, "rollback")
    other_task, other_fact, _, _ = _vertical(core, "unrelated")
    assert other_task != child
    with pytest.raises(ResearchValidationError, match="belong to child Task"):
        core.research_knowledge.proceed_artifact_route(
            task_id,
            assessed["route_id"],
            ProceedArtifactRouteRequest(
                command_id="v5b3:cross-task-fact",
                action="finalize",
                expected_version=2,
                new_fact_aspect_map={GAP: other_fact["fact_revision_id"]},
            ),
            principal_id="local_operator",
        )
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE research_knowledge_fact_states SET currentness_status='stale', "
            "state_version=state_version+1 WHERE fact_id=?",
            (fact["fact_id"],),
        )
    with pytest.raises(ResearchConflict, match="authority snapshot changed"):
        core.research_knowledge.proceed_artifact_route(
            task_id,
            assessed["route_id"],
            ProceedArtifactRouteRequest(
                command_id="v5b3:late-incremental",
                action="finalize",
                expected_version=2,
                new_fact_aspect_map={GAP: new_fact["fact_revision_id"]},
            ),
            principal_id="local_operator",
        )
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_artifact_routes WHERE route_id=?",
            (assessed["route_id"],),
        ).fetchone()[0] == 2


def test_no_hit_and_scope_mismatch_seed_without_fact_or_page_mutation(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, artifact, page = _vertical(core, "seed")
    no_hit = _assess(
        core,
        task_id,
        suffix="no-hit",
        query="完全不存在的量子园艺主题",
        aspects=["量子园艺"],
    )
    assert no_hit["recommended_route"] == "research_seed"
    assert no_hit["artifact_candidates"] == []
    proceeded = core.research_knowledge.proceed_artifact_route(
        task_id,
        no_hit["route_id"],
        ProceedArtifactRouteRequest(
            command_id="v5b3:seed:no-hit",
            expected_version=1,
            route="research_seed",
        ),
        principal_id="local_operator",
    )
    assert proceeded["status"] == "running"
    with core.db.connect() as connection:
        child = connection.execute(
            "SELECT * FROM research_tasks WHERE task_id=?",
            (proceeded["continuation_task_id"],),
        ).fetchone()
        assert str(child["parent_task_id"]) == task_id
        goal = connection.execute(
            "SELECT * FROM research_goals WHERE task_id=?",
            (proceeded["continuation_task_id"],),
        ).fetchone()
        policy = json.loads(str(goal["evidence_policy_json"]))
        assert policy["artifact_context_authority"] == "candidate_only_not_verifier"
        assert policy["open_retrieval_required"] is True
        assert connection.execute(
            "SELECT COUNT(*) FROM research_knowledge_artifact_revisions"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT current_version FROM research_topic_pages WHERE page_id=?",
            (page["page_id"],),
        ).fetchone()[0] == 1
    assert artifact["artifact_revision_id"] not in proceeded["contribution"]["reused"]
    substantial = _assess(
        core,
        task_id,
        suffix="substantial",
        query=f"{artifact['topic']} 新方面甲 新方面乙 新方面丙",
        aspects=[
            artifact["body"]["facts"][0]["claim"],
            "新方面甲",
            "新方面乙",
            "新方面丙",
        ],
    )
    assert substantial["artifact_candidates"]
    assert substantial["gates"][0]["completeness_status"] == "substantial_gap"
    assert substantial["recommended_route"] == "research_seed"


def test_assessment_fault_rolls_back_route_event_and_receipt(app_paths) -> None:
    core = _core(app_paths)
    task_id, fact, _, _ = _vertical(core, "assessment-fault")
    core.research_knowledge.fault_injector = lambda point: (
        (_ for _ in ()).throw(SimulatedCrash(point))
        if point == "after_stage3_route_assessment"
        else None
    )
    request = AssessArtifactRouteRequest(
        command_id="v5b3:assessment:fault",
        query=fact["claim"],
        required_aspects=[fact["claim"]],
    )
    with pytest.raises(SimulatedCrash, match="after_stage3_route_assessment"):
        core.research_knowledge.assess_artifact_route(task_id, request)
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_artifact_routes WHERE task_id=?",
            (task_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM research_command_receipts "
            "WHERE task_id=? AND command_id=?",
            (task_id, request.command_id),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM research_events "
            "WHERE task_id=? AND event_type='artifact_route_assessed'",
            (task_id,),
        ).fetchone()[0] == 0
