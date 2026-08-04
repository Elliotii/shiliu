from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.db import SCHEMA_VERSION
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.research.errors import ResearchConflict, ResearchValidationError, SimulatedCrash
from shiliu.research.knowledge_contracts import (
    BuildKnowledgeArtifactRequest,
    BuildTopicPageRequest,
    EditTopicPageRequest,
    ExportTopicPageRequest,
    IntakeKnowledgeCandidatesRequest,
    ProposeFactUpdateRequest,
    RecoverKnowledgeOperationsRequest,
    ResolveKnowledgeOperationRequest,
    RevalidateKnowledgeRequest,
    ReviewFactUpdateRequest,
    ReviewKnowledgeCandidateRequest,
    ReviewTopicPageRequest,
    RevertTopicPageRequest,
    RunKnowledgeOperationRequest,
)
from shiliu.research.product_contracts import (
    CreateProductResearchRequest,
    RunProductResearchRequest,
)
from shiliu.research.schema import prepare_research_schema_v12
from shiliu.retrieval.coordinator import SYNC_STATE_VERSION
from shiliu.web import create_web_app


OBJECTIVE = "请解释 MCP 工具执行为何需要幂等回执"


def _core(app_paths) -> Application:
    core = Application(app_paths)
    source_id = core.db.create_favorite_source(
        folder_id=5202, folder_title="V5-B Stage 2 Fixture"
    )
    item = FavoriteItem(
        bvid="BV5202000001",
        title="V5-B Lifecycle Fixture",
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
            command_id=f"v5b2:create:{suffix}",
            objective=OBJECTIVE,
            success_constraints=[],
            run_immediately=False,
        )
    )
    task_id = str(created["task_id"])
    outcome = core.research_product.run_to_boundary(
        task_id, RunProductResearchRequest(command_id=f"v5b2:run:{suffix}")
    )
    assert outcome["task_status"] == "terminal"
    core.research_knowledge.intake_candidates(
        task_id,
        IntakeKnowledgeCandidatesRequest(command_id=f"v5b2:intake:{suffix}"),
    )
    workspace = core.research_knowledge.get_workspace(task_id)
    candidate = workspace["candidates"][0]
    core.research_knowledge.review_candidate(
        task_id,
        candidate["candidate_id"],
        ReviewKnowledgeCandidateRequest(
            command_id=f"v5b2:accept:{suffix}",
            decision="accept",
            expected_state_version=candidate["state_version"],
        ),
        principal_id="local_operator",
    )
    fact = core.research_knowledge.get_workspace(task_id)["facts"][0]
    artifact = core.research_knowledge.build_artifact(
        task_id,
        BuildKnowledgeArtifactRequest(
            command_id=f"v5b2:artifact:{suffix}",
            fact_revision_ids=[fact["fact_revision_id"]],
        ),
    )
    page = core.research_knowledge.build_topic_page(
        task_id,
        BuildTopicPageRequest(
            command_id=f"v5b2:page:{suffix}",
            artifact_revision_id=artifact["artifact_revision_id"],
        ),
    )
    core.research_knowledge.review_page(
        task_id,
        page["page_id"],
        ReviewTopicPageRequest(
            command_id=f"v5b2:publish:{suffix}",
            decision="publish",
            expected_version=1,
        ),
        principal_id="local_operator",
    )
    return task_id, fact, artifact, page


def _propose_and_accept_correction(
    core: Application, task_id: str, suffix: str
) -> dict:
    workspace = core.research_knowledge.get_workspace(task_id)
    fact = next(value for value in workspace["facts"] if value["is_current_revision"])
    state = workspace["fact_states"][0]
    proposed = core.research_knowledge.propose_fact_update(
        task_id,
        fact["fact_id"],
        ProposeFactUpdateRequest(
            command_id=f"v5b2:propose:{suffix}",
            kind="user_correction",
            expected_fact_state_version=state["state_version"],
            proposed_claim=fact["citations"][0]["quote"],
            evidence_use_ids=[fact["citations"][0]["evidence_use_id"]],
            viewpoint_scope={"perspective": suffix},
        ),
        principal_id="local_operator",
    )
    assert proposed["validator_status"] == "eligible"
    workspace = core.research_knowledge.get_workspace(task_id)
    candidate = next(
        value
        for value in workspace["update_candidates"]
        if value["update_candidate_id"] == proposed["update_candidate_id"]
    )
    state = workspace["fact_states"][0]
    return core.research_knowledge.review_fact_update(
        task_id,
        candidate["update_candidate_id"],
        ReviewFactUpdateRequest(
            command_id=f"v5b2:review:{suffix}",
            decision="accept",
            expected_candidate_version=candidate["state_version"],
            expected_fact_state_version=state["state_version"],
        ),
        principal_id="local_operator",
    )


def _insert_second_fact(
    core: Application, task_id: str, source_fact: dict, *, temporal_scope: str = "{}"
) -> tuple[str, str]:
    fact_id = "fact_stage2_conflict_fixture"
    revision_id = "factrev_stage2_conflict_fixture"
    candidate_id = "kcandidate_stage2_conflict_fixture"
    now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    with core.db.connect() as connection:
        origin = connection.execute(
            "SELECT * FROM research_knowledge_candidates WHERE candidate_id=?",
            (source_fact["origin_candidate_id"],),
        ).fetchone()
        assert origin is not None
        connection.execute(
            """
            INSERT INTO research_knowledge_candidates(
                candidate_id, workspace_schema_version, task_id, goal_id,
                attempt_id, checkpoint_id, result_id, provisional_artifact_id,
                source_event_id, source_delta_snapshot_id, candidate_kind,
                source_boundary_hash, source_delta_hash, source_item_hash,
                source_item_index, parent_candidate_id, claim_text,
                citation_ids_json, evidence_use_ids_json, source_payload_json,
                status, state_version, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'KnowledgeDelta', ?, ?, ?, ?, ?,
                     ?, ?, ?, ?, 'accepted', 1, ?, ?)
            """,
            (
                candidate_id,
                str(origin["workspace_schema_version"]),
                task_id,
                str(origin["goal_id"]),
                str(origin["attempt_id"]),
                str(origin["checkpoint_id"]) if origin["checkpoint_id"] else None,
                str(origin["result_id"]) if origin["result_id"] else None,
                str(origin["provisional_artifact_id"]),
                str(origin["source_event_id"]),
                str(origin["source_delta_snapshot_id"]),
                str(origin["source_boundary_hash"]),
                str(origin["source_delta_hash"]),
                "stage2-conflict-item-hash",
                int(origin["source_item_index"]) + 100,
                str(origin["candidate_id"]),
                "另一条可追踪且当前 grounded 的知识观点",
                str(origin["citation_ids_json"]),
                str(origin["evidence_use_ids_json"]),
                str(origin["source_payload_json"]),
                now,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO research_grounded_facts("
            "fact_id, workspace_schema_version, task_id, origin_candidate_id, created_at"
            ") VALUES(?, ?, ?, ?, ?)",
            (fact_id, str(origin["workspace_schema_version"]), task_id, candidate_id, now),
        )
        connection.execute(
            """
            INSERT INTO research_fact_revisions(
                fact_revision_id, fact_id, task_id, revision,
                parent_revision_id, supersedes_revision_id, origin_candidate_id,
                claim_text, temporal_scope_json, viewpoint_scope_json,
                verification_status, content_hash, created_at
            ) VALUES(?, ?, ?, 1, NULL, NULL, ?, ?, ?, '{}',
                     'accepted_current', 'stage2-conflict-content', ?)
            """,
            (
                revision_id,
                fact_id,
                task_id,
                candidate_id,
                "另一条可追踪且当前 grounded 的知识观点",
                temporal_scope,
                now,
            ),
        )
        source_link = connection.execute(
            "SELECT * FROM research_fact_evidence_links WHERE fact_revision_id=?",
            (source_fact["fact_revision_id"],),
        ).fetchone()
        assert source_link is not None
        connection.execute(
            """
            INSERT INTO research_fact_evidence_links(
                link_id, task_id, fact_revision_id, evidence_id,
                evidence_use_id, validation_observation_id, ordinal, created_at
            ) VALUES('factevidence_stage2_conflict_fixture', ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                task_id,
                revision_id,
                str(source_link["evidence_id"]),
                str(source_link["evidence_use_id"]),
                str(source_link["validation_observation_id"]),
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO research_knowledge_fact_states(
                fact_id, task_id, current_revision_id, lifecycle_status,
                currentness_status, superseded_by_revision_id,
                latest_observation_set_id, state_version, updated_at
            ) VALUES(?, ?, ?, 'current', 'current', NULL, NULL, 0, ?)
            """,
            (fact_id, task_id, revision_id, now),
        )
    return fact_id, revision_id


def test_stage2_schema_source_is_reentrant_and_v11_page_rows_migrate(app_paths) -> None:
    core = _core(app_paths)
    assert SCHEMA_VERSION == 13
    core.db.initialize()
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == "13"
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            ).fetchall()
        }
        assert {
            "research_knowledge_fact_states",
            "research_knowledge_revalidation_observations",
            "research_knowledge_update_candidates",
            "research_knowledge_lifecycle_decisions",
            "research_knowledge_update_operations",
            "research_topic_page_revision_decisions",
            "research_knowledge_exports",
        } <= tables

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        CREATE TABLE research_tasks(task_id TEXT PRIMARY KEY);
        CREATE TABLE research_knowledge_artifact_revisions(artifact_revision_id TEXT PRIMARY KEY);
        CREATE TABLE research_topic_pages(
          page_id TEXT PRIMARY KEY, workspace_schema_version TEXT NOT NULL,
          task_id TEXT NOT NULL REFERENCES research_tasks(task_id),
          slug TEXT NOT NULL UNIQUE, current_version INTEGER NOT NULL CHECK(current_version = 1),
          review_status TEXT NOT NULL CHECK(review_status IN ('draft','published','returned')),
          state_version INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE research_topic_page_revisions(
          page_revision_id TEXT PRIMARY KEY, page_id TEXT NOT NULL REFERENCES research_topic_pages(page_id),
          task_id TEXT NOT NULL REFERENCES research_tasks(task_id), version INTEGER NOT NULL CHECK(version = 1),
          parent_revision_id TEXT REFERENCES research_topic_page_revisions(page_revision_id),
          supersedes_revision_id TEXT REFERENCES research_topic_page_revisions(page_revision_id),
          artifact_revision_id TEXT NOT NULL REFERENCES research_knowledge_artifact_revisions(artifact_revision_id),
          title TEXT NOT NULL, body_json TEXT NOT NULL, build_policy_version TEXT NOT NULL,
          input_hash TEXT NOT NULL, content_hash TEXT NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(page_id,version), UNIQUE(task_id,input_hash));
        CREATE TABLE research_topic_page_review_decisions(
          decision_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES research_tasks(task_id),
          page_id TEXT NOT NULL REFERENCES research_topic_pages(page_id),
          page_revision_id TEXT NOT NULL REFERENCES research_topic_page_revisions(page_revision_id),
          decision_kind TEXT NOT NULL CHECK(decision_kind IN ('publish','return')), reason TEXT NOT NULL,
          expected_version INTEGER NOT NULL CHECK(expected_version = 1), command_id TEXT NOT NULL,
          principal_id TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(task_id,command_id), UNIQUE(page_id));
        INSERT INTO research_tasks VALUES('task');
        INSERT INTO research_knowledge_artifact_revisions VALUES('artifact-rev');
        INSERT INTO research_topic_pages VALUES('page','v1','task','slug',1,'published',1,'now','now');
        INSERT INTO research_topic_page_revisions VALUES(
          'page-rev','page','task',1,NULL,NULL,'artifact-rev','Title','{}','policy','input','content','now');
        INSERT INTO research_topic_page_review_decisions VALUES(
          'decision','task','page','page-rev','publish','',1,'command','operator','now');
        """
    )
    prepare_research_schema_v12(connection)
    assert connection.execute(
        "SELECT published_version FROM research_topic_pages"
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT revision_kind FROM research_topic_page_revisions"
    ).fetchone()[0] == "initial"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_revalidation_is_append_only_visible_and_never_mutates_published_page(
    app_paths,
) -> None:
    core = _core(app_paths)
    task_id, fact, _, page = _vertical(core, "stale")
    before = core.research_knowledge.get_workspace(task_id)["pages"][0]
    assert before["version"] == 1 and before["published_version"] == 1
    current = core.research_knowledge.revalidate_knowledge(
        task_id,
        RevalidateKnowledgeRequest(
            command_id="v5b2:revalidate:current",
            fact_revision_ids=[fact["fact_revision_id"]],
        ),
    )
    assert current["facts"][0]["currentness"] == "current"
    core.artifacts.save_raw_subtitle(
        "BV5202000001",
        [SubtitleSegment.model_validate({"from": 0, "to": 4, "content": "changed"})],
    )
    outcome = core.research_knowledge.revalidate_knowledge(
        task_id,
        RevalidateKnowledgeRequest(
            command_id="v5b2:revalidate:stale",
            fact_revision_ids=[fact["fact_revision_id"]],
            trigger="source_change",
        ),
    )
    assert outcome["facts"][0]["currentness"] == "stale"
    replay = core.research_knowledge.revalidate_knowledge(
        task_id,
        RevalidateKnowledgeRequest(
            command_id="v5b2:revalidate:stale",
            fact_revision_ids=[fact["fact_revision_id"]],
            trigger="source_change",
        ),
    )
    assert replay["deduplicated"] is True
    workspace = core.research_knowledge.get_workspace(task_id)
    assert workspace["fact_states"][0]["currentness_status"] == "stale"
    assert workspace["pages"][0]["version"] == 1
    assert workspace["pages"][0]["published_version"] == 1
    assert workspace["pages"][0]["currentness_status"] == "stale"
    assert workspace["update_candidates"][0]["status"] == "needs_revalidation"
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_knowledge_revalidation_observations"
        ).fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE research_knowledge_revalidation_observations "
                "SET reason_code='forged'"
            )
        assert connection.execute(
            "SELECT current_version FROM research_topic_pages WHERE page_id=?",
            (page["page_id"],),
        ).fetchone()[0] == 1
    core.artifacts.save_raw_subtitle(
        "BV5202000001",
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
    restored = core.research_knowledge.revalidate_knowledge(
        task_id,
        RevalidateKnowledgeRequest(
            command_id="v5b2:revalidate:restored",
            fact_revision_ids=[fact["fact_revision_id"]],
        ),
    )
    assert restored["facts"][0]["currentness"] == "current"
    assert core.research_knowledge.get_workspace(task_id)["fact_states"][0][
        "currentness_status"
    ] == "current"
    assert core.research_knowledge.get_workspace(task_id)["update_candidates"][0][
        "status"
    ] == "superseded"


def test_correction_refresh_page_history_diff_revert_and_publish_are_immutable(
    app_paths,
) -> None:
    core = _core(app_paths)
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
    with core.db.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE research_fact_revisions SET claim_text='forged' "
                "WHERE fact_revision_id=?",
                (accepted["result_revision_id"],),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE research_topic_page_revisions SET title='forged' "
                "WHERE page_id=? AND version=1",
                (page["page_id"],),
            )
        assert connection.execute(
            "SELECT COUNT(*) FROM research_knowledge_artifact_revisions "
            "WHERE artifact_id=?",
            (artifact["artifact_id"],),
        ).fetchone()[0] == 2


def test_update_edit_needs_revalidation_and_stale_guards_leave_no_orphans(
    app_paths,
) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "guards")
    workspace = core.research_knowledge.get_workspace(task_id)
    fact = next(value for value in workspace["facts"] if value["is_current_revision"])
    unsupported = core.research_knowledge.propose_fact_update(
        task_id,
        fact["fact_id"],
        ProposeFactUpdateRequest(
            command_id="v5b2:unsupported:guards",
            kind="user_correction",
            expected_fact_state_version=fact["fact_state_version"],
            proposed_claim="这是一条当前字幕从未表达的新外部事实",
            evidence_use_ids=[fact["citations"][0]["evidence_use_id"]],
        ),
        principal_id="local_operator",
    )
    assert unsupported["status"] == "needs_revalidation"
    candidate = core.research_knowledge.get_workspace(task_id)["update_candidates"][0]
    with pytest.raises(ResearchConflict):
        core.research_knowledge.review_fact_update(
            task_id,
            candidate["update_candidate_id"],
            ReviewFactUpdateRequest(
                command_id="v5b2:unsafe-accept:guards",
                decision="accept",
                expected_candidate_version=0,
                expected_fact_state_version=fact["fact_state_version"],
            ),
            principal_id="local_operator",
        )
    edited = core.research_knowledge.review_fact_update(
        task_id,
        candidate["update_candidate_id"],
        ReviewFactUpdateRequest(
            command_id="v5b2:edit-update:guards",
            decision="edit",
            expected_candidate_version=0,
            expected_fact_state_version=fact["fact_state_version"],
            edited_claim="仍需服务器重新验证的用户修改",
        ),
        principal_id="local_operator",
    )
    child = next(
        value
        for value in core.research_knowledge.get_workspace(task_id)[
            "update_candidates"
        ]
        if value["update_candidate_id"] == edited["edited_candidate_id"]
    )
    assert child["status"] == "needs_revalidation"
    assert child["parent_candidate_id"] == candidate["update_candidate_id"]
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_fact_revisions WHERE task_id=?",
            (task_id,),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM research_knowledge_update_operations WHERE task_id=?",
            (task_id,),
        ).fetchone()[0] == 0


def test_retire_supersede_and_conflict_preserve_history_and_scope_semantics(
    app_paths,
) -> None:
    core = _core(app_paths)
    supersede_task, _, _, _ = _vertical(core, "supersede")
    workspace = core.research_knowledge.get_workspace(supersede_task)
    fact = next(value for value in workspace["facts"] if value["is_current_revision"])
    proposed = core.research_knowledge.propose_fact_update(
        supersede_task,
        fact["fact_id"],
        ProposeFactUpdateRequest(
            command_id="v5b2:propose:supersede",
            kind="supersede",
            expected_fact_state_version=fact["fact_state_version"],
            proposed_claim=fact["citations"][0]["quote"],
            evidence_use_ids=[fact["citations"][0]["evidence_use_id"]],
            temporal_scope={"period": "current"},
        ),
        principal_id="local_operator",
    )
    reviewed = core.research_knowledge.review_fact_update(
        supersede_task,
        proposed["update_candidate_id"],
        ReviewFactUpdateRequest(
            command_id="v5b2:review:supersede",
            decision="accept",
            expected_candidate_version=0,
            expected_fact_state_version=fact["fact_state_version"],
        ),
        principal_id="local_operator",
    )
    with core.db.connect() as connection:
        row = connection.execute(
            "SELECT parent_revision_id, supersedes_revision_id "
            "FROM research_fact_revisions WHERE fact_revision_id=?",
            (reviewed["result_revision_id"],),
        ).fetchone()
        assert tuple(row) == (fact["fact_revision_id"], fact["fact_revision_id"])

    retire_task, _, _, retire_page = _vertical(core, "retire")
    workspace = core.research_knowledge.get_workspace(retire_task)
    retire_fact = next(
        value for value in workspace["facts"] if value["is_current_revision"]
    )
    retire_candidate = core.research_knowledge.propose_fact_update(
        retire_task,
        retire_fact["fact_id"],
        ProposeFactUpdateRequest(
            command_id="v5b2:propose:retire",
            kind="retire",
            expected_fact_state_version=retire_fact["fact_state_version"],
        ),
        principal_id="local_operator",
    )
    retired = core.research_knowledge.review_fact_update(
        retire_task,
        retire_candidate["update_candidate_id"],
        ReviewFactUpdateRequest(
            command_id="v5b2:review:retire",
            decision="accept",
            expected_candidate_version=0,
            expected_fact_state_version=retire_fact["fact_state_version"],
        ),
        principal_id="local_operator",
    )
    finished = core.research_knowledge.run_update_operation(
        retire_task,
        retired["operation_id"],
        RunKnowledgeOperationRequest(command_id="v5b2:operation:retire"),
        principal_id="local_operator",
    )
    assert finished["status"] == "succeeded"
    retired_workspace = core.research_knowledge.get_workspace(retire_task)
    assert retired_workspace["fact_states"][0]["lifecycle_status"] == "retired"
    assert retired_workspace["pages"][0]["body"]["facts"] == []
    assert retired_workspace["pages"][0]["published_version"] == 1
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_fact_revisions WHERE task_id=?",
            (retire_task,),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM research_topic_page_fact_links pfl "
            "JOIN research_topic_page_revisions pr "
            "ON pr.page_revision_id=pfl.page_revision_id "
            "WHERE pr.page_id=? AND pr.version=2",
            (retire_page["page_id"],),
        ).fetchone()[0] == 0

    conflict_task, conflict_fact, _, _ = _vertical(core, "conflict")
    _, related_revision_id = _insert_second_fact(
        core, conflict_task, conflict_fact, temporal_scope='{"year":2024}'
    )
    workspace = core.research_knowledge.get_workspace(conflict_task)
    source = next(
        value
        for value in workspace["facts"]
        if value["fact_id"] == conflict_fact["fact_id"]
    )
    disjoint = core.research_knowledge.propose_fact_update(
        conflict_task,
        source["fact_id"],
        ProposeFactUpdateRequest(
            command_id="v5b2:conflict:disjoint",
            kind="potential_conflict",
            expected_fact_state_version=source["fact_state_version"],
            related_fact_revision_id=related_revision_id,
            temporal_scope={"year": 2025},
        ),
        principal_id="local_operator",
    )
    assert disjoint["status"] == "needs_revalidation"
    state = next(
        value
        for value in core.research_knowledge.get_workspace(conflict_task)["fact_states"]
        if value["fact_id"] == source["fact_id"]
    )
    core.research_knowledge.review_fact_update(
        conflict_task,
        disjoint["update_candidate_id"],
        ReviewFactUpdateRequest(
            command_id="v5b2:conflict:disjoint:reject",
            decision="reject",
            expected_candidate_version=0,
            expected_fact_state_version=state["state_version"],
        ),
        principal_id="local_operator",
    )
    state = next(
        value
        for value in core.research_knowledge.get_workspace(conflict_task)["fact_states"]
        if value["fact_id"] == source["fact_id"]
    )
    overlap = core.research_knowledge.propose_fact_update(
        conflict_task,
        source["fact_id"],
        ProposeFactUpdateRequest(
            command_id="v5b2:conflict:overlap",
            kind="potential_conflict",
            expected_fact_state_version=state["state_version"],
            related_fact_revision_id=related_revision_id,
        ),
        principal_id="local_operator",
    )
    assert overlap["status"] == "pending_review"
    state = next(
        value
        for value in core.research_knowledge.get_workspace(conflict_task)["fact_states"]
        if value["fact_id"] == source["fact_id"]
    )
    confirmed = core.research_knowledge.review_fact_update(
        conflict_task,
        overlap["update_candidate_id"],
        ReviewFactUpdateRequest(
            command_id="v5b2:conflict:confirm",
            decision="accept",
            expected_candidate_version=0,
            expected_fact_state_version=state["state_version"],
            reason="same scope, user confirms knowledge-organization conflict",
        ),
        principal_id="local_operator",
    )
    assert confirmed["result_kind"] == "confirm_conflict"
    states = core.research_knowledge.get_workspace(conflict_task)["fact_states"]
    assert {value["currentness_status"] for value in states} == {"conflicted"}


def test_lifecycle_fault_rolls_back_revision_decision_operation_and_receipt(
    app_paths,
) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "rollback")
    workspace = core.research_knowledge.get_workspace(task_id)
    fact = next(value for value in workspace["facts"] if value["is_current_revision"])
    proposed = core.research_knowledge.propose_fact_update(
        task_id,
        fact["fact_id"],
        ProposeFactUpdateRequest(
            command_id="v5b2:rollback:propose",
            kind="user_correction",
            expected_fact_state_version=fact["fact_state_version"],
            proposed_claim=fact["citations"][0]["quote"],
            evidence_use_ids=[fact["citations"][0]["evidence_use_id"]],
        ),
        principal_id="local_operator",
    )

    def crash(point: str) -> None:
        if point == "after_stage2_fact_revision":
            raise SimulatedCrash(point)

    core.research_knowledge.fault_injector = crash
    with pytest.raises(SimulatedCrash):
        core.research_knowledge.review_fact_update(
            task_id,
            proposed["update_candidate_id"],
            ReviewFactUpdateRequest(
                command_id="v5b2:rollback:review",
                decision="accept",
                expected_candidate_version=0,
                expected_fact_state_version=fact["fact_state_version"],
            ),
            principal_id="local_operator",
        )
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_fact_revisions WHERE task_id=?",
            (task_id,),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT status FROM research_knowledge_update_candidates "
            "WHERE update_candidate_id=?",
            (proposed["update_candidate_id"],),
        ).fetchone()[0] == "pending_review"
        assert connection.execute(
            "SELECT COUNT(*) FROM research_knowledge_lifecycle_decisions "
            "WHERE task_id=?",
            (task_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM research_knowledge_update_operations "
            "WHERE task_id=?",
            (task_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM research_command_receipts "
            "WHERE task_id=? AND command_id='v5b2:rollback:review'",
            (task_id,),
        ).fetchone()[0] == 0


def test_operation_crash_recovery_late_fence_retry_and_dead_letter(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, _, page = _vertical(core, "fence")
    accepted = _propose_and_accept_correction(core, task_id, "fence")

    def crash_after_claim(point: str) -> None:
        if point == "after_stage2_operation_claim":
            raise SimulatedCrash(point)

    core.research_knowledge.fault_injector = crash_after_claim
    with pytest.raises(SimulatedCrash):
        core.research_knowledge.run_update_operation(
            task_id,
            accepted["operation_id"],
            RunKnowledgeOperationRequest(command_id="v5b2:claim-crash:fence"),
            principal_id="local_operator",
        )
    with core.db.connect() as connection:
        row = connection.execute(
            "SELECT status, claim_generation FROM research_knowledge_update_operations "
            "WHERE operation_id=?",
            (accepted["operation_id"],),
        ).fetchone()
        assert tuple(row) == ("running", 1)
        connection.execute(
            "UPDATE research_knowledge_update_operations SET lease_until='2000-01-01T00:00:00+00:00' "
            "WHERE operation_id=?",
            (accepted["operation_id"],),
        )
    restarted = Application(core.paths)
    restarted.research_knowledge.edit_topic_page(
        task_id,
        page["page_id"],
        EditTopicPageRequest(
            command_id="v5b2:concurrent-edit:fence",
            expected_version=1,
            annotation="moves Page fence",
        ),
        principal_id="local_operator",
    )
    recovered = restarted.research_knowledge.recover_update_operations(
        task_id,
        RecoverKnowledgeOperationsRequest(command_id="v5b2:recover:fence"),
        principal_id="local_operator",
    )
    assert recovered["count"] == 1
    assert recovered["recovered"][0]["status"] == "superseded"
    with restarted.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_knowledge_artifact_revisions "
            "WHERE task_id=? AND revision>1",
            (task_id,),
        ).fetchone()[0] == 0

    retry_core = _core(app_paths.__class__(
        app_paths.state_dir.parent / "retry-state",
        app_paths.content_dir.parent / "retry-content",
        app_paths.state_dir.parent / "retry-state" / "shiliu.db",
        app_paths.state_dir.parent / "retry-state" / "config.toml",
        app_paths.state_dir.parent / "retry-state" / "logs",
        app_paths.content_dir.parent / "retry-content" / "videos",
        app_paths.state_dir.parent / "retry-state" / "sync.lock",
    ))
    retry_task, _, _, _ = _vertical(retry_core, "retry")
    retry_accepted = _propose_and_accept_correction(retry_core, retry_task, "retry")

    def transient(point: str) -> None:
        if point == "during_stage2_operation_build":
            raise OSError("temporary storage unavailable")

    retry_core.research_knowledge.fault_injector = transient
    first = retry_core.research_knowledge.run_update_operation(
        retry_task,
        retry_accepted["operation_id"],
        RunKnowledgeOperationRequest(command_id="v5b2:retry:first"),
        principal_id="local_operator",
    )
    assert first["status"] == "retry_wait"
    retry_core.research_knowledge.fault_injector = lambda _point: None
    second = retry_core.research_knowledge.run_update_operation(
        retry_task,
        retry_accepted["operation_id"],
        RunKnowledgeOperationRequest(command_id="v5b2:retry:second"),
        principal_id="local_operator",
    )
    assert second["status"] == "succeeded"

    dead_task, _, _, _ = _vertical(retry_core, "dead")
    dead_accepted = _propose_and_accept_correction(retry_core, dead_task, "dead")
    retry_core.research_knowledge.fault_injector = transient
    statuses = []
    for attempt in range(1, 4):
        outcome = retry_core.research_knowledge.run_update_operation(
            dead_task,
            dead_accepted["operation_id"],
            RunKnowledgeOperationRequest(
                command_id=f"v5b2:dead-letter:{attempt}"
            ),
            principal_id="local_operator",
        )
        statuses.append(outcome["status"])
    assert statuses == ["retry_wait", "retry_wait", "dead_letter"]
    assert outcome["error_class"] == "infrastructure_invalid"

    needs_task, _, _, _ = _vertical(retry_core, "needs-user")
    needs_accepted = _propose_and_accept_correction(
        retry_core, needs_task, "needs-user"
    )

    def implementation_failure(point: str) -> None:
        if point == "during_stage2_operation_build":
            raise RuntimeError("fixture requires user correction")

    retry_core.research_knowledge.fault_injector = implementation_failure
    needs_user = retry_core.research_knowledge.run_update_operation(
        needs_task,
        needs_accepted["operation_id"],
        RunKnowledgeOperationRequest(command_id="v5b2:needs-user:first"),
        principal_id="local_operator",
    )
    assert needs_user["status"] == "needs_user"
    resolved = retry_core.research_knowledge.resolve_update_operation(
        needs_task,
        needs_accepted["operation_id"],
        ResolveKnowledgeOperationRequest(
            command_id="v5b2:needs-user:resolve",
            action="retry",
            expected_claim_generation=needs_user["claim_generation"],
            reason="operator corrected the bounded blocker",
        ),
        principal_id="local_operator",
    )
    assert resolved["status"] == "pending"
    retry_core.research_knowledge.fault_injector = lambda _point: None
    assert retry_core.research_knowledge.run_update_operation(
        needs_task,
        needs_accepted["operation_id"],
        RunKnowledgeOperationRequest(command_id="v5b2:needs-user:second"),
        principal_id="local_operator",
    )["status"] == "succeeded"


def test_revision_hash_export_failure_is_observable_and_same_command_retries(
    app_paths,
) -> None:
    core = _core(app_paths)
    task_id, _, _, page = _vertical(core, "export")
    attempts = {"count": 0}

    def fail_once(point: str) -> None:
        if point == "during_stage2_export" and attempts["count"] == 0:
            attempts["count"] += 1
            raise OSError("simulated export failure")

    core.research_knowledge.fault_injector = fail_once
    request = ExportTopicPageRequest(
        command_id="v5b2:export:retry",
        page_revision_id=page["page_revision_id"],
        export_format="markdown",
    )
    failed = core.research_knowledge.export_topic_page(
        task_id, request, principal_id="local_operator"
    )
    assert failed["status"] == "retry_wait"
    assert failed["error_class"] == "infrastructure_invalid"
    canonical_before = core.research_knowledge.get_workspace(task_id)["pages"][0]
    core.research_knowledge.fault_injector = lambda _point: None
    exported = core.research_knowledge.export_topic_page(
        task_id, request, principal_id="local_operator"
    )
    assert exported["status"] == "succeeded"
    assert exported["attempt_count"] == 2
    output = core.paths.content_dir / "knowledge-exports" / exported["relative_path"]
    assert output.is_file()
    text = output.read_text(encoding="utf-8")
    assert page["page_revision_id"] in text
    assert exported["content_hash"] in text
    canonical_after = core.research_knowledge.get_workspace(task_id)["pages"][0]
    assert canonical_after["content_hash"] == canonical_before["content_hash"]
    assert canonical_after["version"] == canonical_before["version"]


def test_public_api_and_minimal_ui_expose_complete_stage2_journey(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, _, page = _vertical(core, "api")
    client = TestClient(create_web_app(core))
    html = client.get("/research")
    script = client.get("/static/research.js")
    assert html.status_code == 200
    assert "V5-B · STAGE 2" in html.text
    assert "data-knowledge-revalidate" in html.text
    assert "data-knowledge-operations" in html.text
    assert "revision-ID/content-hash" in script.text
    assert "History / diff" in script.text
    assert "Resolve → retry" in script.text
    detail = client.get(f"/api/research/product/tasks/{task_id}/knowledge")
    fact = next(
        value
        for value in detail.json()["workspace"]["facts"]
        if value["is_current_revision"]
    )
    proposed = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/facts/{fact['fact_id']}/updates",
        json={
            "command_id": "v5b2:api:propose",
            "kind": "user_correction",
            "expected_fact_state_version": fact["fact_state_version"],
            "proposed_claim": fact["citations"][0]["quote"],
            "evidence_use_ids": [fact["citations"][0]["evidence_use_id"]],
            "viewpoint_scope": {"perspective": "api"},
        },
    )
    assert proposed.status_code == 201
    candidate_id = proposed.json()["outcome"]["update_candidate_id"]
    reviewed = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/updates/{candidate_id}/review",
        json={
            "command_id": "v5b2:api:review",
            "decision": "accept",
            "expected_candidate_version": 0,
            "expected_fact_state_version": fact["fact_state_version"],
        },
    )
    assert reviewed.status_code == 200
    operation_id = reviewed.json()["outcome"]["operation_id"]
    ran = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/operations/{operation_id}/run",
        json={"command_id": "v5b2:api:operation", "claimant_id": "api_test"},
    )
    assert ran.status_code == 200 and ran.json()["outcome"]["status"] == "succeeded"
    edited = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/pages/{page['page_id']}/edit",
        json={
            "command_id": "v5b2:api:edit",
            "expected_version": 2,
            "annotation": "API review annotation",
        },
    )
    assert edited.status_code == 201 and edited.json()["outcome"]["version"] == 3
    history = client.get(
        f"/api/research/product/tasks/{task_id}/knowledge/pages/{page['page_id']}/history"
    )
    diff = client.get(
        f"/api/research/product/tasks/{task_id}/knowledge/pages/{page['page_id']}/diff",
        params={"from_version": 2, "to_version": 3},
    )
    assert history.status_code == 200 and len(history.json()["history"]["revisions"]) == 3
    assert diff.status_code == 200 and diff.json()["diff"]["lines"]
    exported = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/exports",
        json={
            "command_id": "v5b2:api:export",
            "page_revision_id": edited.json()["outcome"]["page_revision_id"],
            "export_format": "json",
        },
    )
    assert exported.status_code == 200
    assert exported.json()["outcome"]["status"] == "succeeded"
