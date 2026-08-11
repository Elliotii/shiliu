from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.ask.contracts import AskRequest
from shiliu.db import SCHEMA_VERSION
from shiliu.research.errors import (
    ResearchConflict,
    ResearchValidationError,
    SimulatedCrash,
)
from shiliu.research.knowledge_contracts import (
    AssessArtifactRouteRequest,
    CreateWorkspaceRecordRequest,
    DecideWorkspaceRecordRequest,
    WorkspaceSourceRef,
)
from shiliu.retrieval.product_search import ProductSearchRequest
from shiliu.web import create_web_app
from test_v5_b_stage3_artifact_reuse import OBJECTIVE, _core, _vertical


def _event_refs(core: Application, task_id: str, limit: int = 3) -> list[WorkspaceSourceRef]:
    with core.db.connect() as connection:
        rows = connection.execute(
            "SELECT event_id FROM research_events WHERE task_id=? "
            "ORDER BY sequence LIMIT ?",
            (task_id, limit),
        ).fetchall()
    assert len(rows) == limit
    return [
        WorkspaceSourceRef(
            ref_type="research_event", ref_id=str(row[0]), task_id=task_id
        )
        for row in rows
    ]


def _experience_refs(core: Application, task_id: str) -> list[WorkspaceSourceRef]:
    with core.db.connect() as connection:
        trace = connection.execute(
            "SELECT trace_id FROM research_traces WHERE task_id=? ORDER BY started_at LIMIT 1",
            (task_id,),
        ).fetchone()
        result = connection.execute(
            "SELECT result_id FROM research_results WHERE task_id=? ORDER BY rowid LIMIT 1",
            (task_id,),
        ).fetchone()
    assert trace is not None and result is not None
    return [
        WorkspaceSourceRef(
            ref_type="research_trace", ref_id=str(trace[0]), task_id=task_id
        ),
        WorkspaceSourceRef(
            ref_type="research_result", ref_id=str(result[0]), task_id=task_id
        ),
    ]


def _create(
    core: Application,
    task_id: str,
    *,
    command_id: str,
    record_kind: str,
    semantic_key: str,
    payload: dict,
    source_refs: list[WorkspaceSourceRef] | None = None,
    expires_at: datetime | None = None,
    reopen_reason: str | None = None,
) -> dict:
    return core.research_knowledge.create_personal_workspace_record(
        task_id,
        CreateWorkspaceRecordRequest(
            command_id=command_id,
            record_kind=record_kind,
            semantic_key=semantic_key,
            payload=payload,
            source_refs=source_refs or [],
            confidence=0.8 if source_refs else None,
            expires_at=expires_at,
            reason="Stage 4 directed fixture",
            reopen_reason=reopen_reason,
        ),
        principal_id="local_operator",
    )


def _decide(
    core: Application,
    task_id: str,
    record: dict,
    *,
    command_id: str,
    action: str,
    replacement_payload: dict | None = None,
) -> dict:
    return core.research_knowledge.decide_personal_workspace_record(
        task_id,
        record["record_id"],
        DecideWorkspaceRecordRequest(
            command_id=command_id,
            action=action,
            expected_version=record["version"],
            replacement_payload=replacement_payload,
            reason="Stage 4 directed decision",
        ),
        principal_id="local_operator",
    )


def _stable_search(value: dict) -> dict:
    return {
        "plan": value["plan"],
        "executed_mode": value["executed_mode"],
        "fallback": value["fallback"],
        "fallback_reason": value["fallback_reason"],
        "raw_hit_count": value["raw_hit_count"],
        "returned_group_count": value["returned_group_count"],
        "results": value["results"],
        "warnings": value["warnings"],
        "error": value["error"],
    }


def _stable_ask(value: dict) -> dict:
    return {
        key: value[key]
        for key in (
            "mode",
            "status",
            "answer_blocks",
            "citations",
            "limitations",
            "termination_reason",
        )
    }


def _stable_route(value: dict) -> dict:
    return {
        "artifact_candidates": value["artifact_candidates"],
        "open_corpus": value["open_corpus"],
        "gates": value["gates"],
        "recommended_route": value["recommended_route"],
        "expected_authority_hash": value["expected_authority_hash"],
    }


def _stable_research(value: dict) -> dict:
    return {
        key: item
        for key, item in value.items()
        if key not in {"artifact_routes", "closeout", "updated_at"}
    }


def test_stage4_schema_explicit_memory_api_ui_restart_and_idempotency(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "workspace-explicit")
    assert SCHEMA_VERSION == 15
    with core.db.connect() as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'research_workspace_%' ORDER BY name"
        ).fetchall()
        assert [str(row[0]) for row in tables] == ["research_workspace_records"]

    created = _create(
        core,
        task_id,
        command_id="v5b4:memory:create",
        record_kind="explicit_memory",
        semantic_key="response language",
        payload={"key": "response_language", "value": "Chinese"},
    )
    assert created["authority_class"] == "user_authored"
    assert created["user_state_authority"] is True
    replay = _create(
        core,
        task_id,
        command_id="v5b4:memory:create",
        record_kind="explicit_memory",
        semantic_key="response language",
        payload={"key": "response_language", "value": "Chinese"},
    )
    assert replay["deduplicated"] is True
    with pytest.raises(ResearchConflict, match="payload"):
        _create(
            core,
            task_id,
            command_id="v5b4:memory:create",
            record_kind="explicit_memory",
            semantic_key="response language",
            payload={"key": "response_language", "value": "English"},
        )
    corrected = _decide(
        core,
        task_id,
        created,
        command_id="v5b4:memory:correct",
        action="correct",
        replacement_payload={"key": "response_language", "value": "中文"},
    )
    tombstoned = _decide(
        core,
        task_id,
        corrected,
        command_id="v5b4:memory:tombstone",
        action="tombstone",
    )
    assert tombstoned["effective_status"] == "tombstoned"
    restarted = Application(core.paths)
    record = restarted.research_knowledge.get_personal_workspace(task_id)["records"][0]
    assert record["version"] == 3
    assert [item["decision_action"] for item in record["history"]] == [
        "create",
        "correct",
        "tombstone",
    ]
    with restarted.db.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE research_workspace_records SET status='current' "
                "WHERE record_revision_id=?",
                (record["record_revision_id"],),
            )

    client = TestClient(create_web_app(restarted))
    api_created = client.post(
        f"/api/research/product/tasks/{task_id}/workspace/records",
        json={
            "command_id": "v5b4:api:create",
            "record_kind": "explicit_memory",
            "semantic_key": "answer density",
            "payload": {"key": "answer_density", "value": "compact"},
            "source_refs": [],
            "reason": "public journey",
        },
    )
    assert api_created.status_code == 201
    api_record = api_created.json()["outcome"]
    api_decision = client.post(
        f"/api/research/product/tasks/{task_id}/workspace/records/"
        f"{api_record['record_id']}/decisions",
        json={
            "command_id": "v5b4:api:expire",
            "action": "expire",
            "expected_version": 1,
            "reason": "public journey",
        },
    )
    assert api_decision.status_code == 200
    api_workspace = client.get(
        f"/api/research/product/tasks/{task_id}/workspace?record_kind=explicit_memory"
    )
    assert api_workspace.status_code == 200
    assert len(api_workspace.json()["workspace"]["records"]) == 2
    html = client.get(f"/research/{task_id}").text
    js = client.get("/static/research.js").text
    assert "Personal and Corpus Workspace" in html
    assert "data-workspace-record-form" in html
    assert "decideWorkspaceRecord" in js
    assert "不会影响 Search、Ask、Research、ArtifactRoute" in html


def test_inferred_candidate_review_expiry_and_no_resurrection(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "workspace-inferred")
    refs = _event_refs(core, task_id)
    with pytest.raises(ResearchValidationError, match="at least two"):
        _create(
            core,
            task_id,
            command_id="v5b4:inferred:weak",
            record_kind="inferred_candidate",
            semantic_key="stable preference",
            payload={"statement": "prefers diagrams"},
            source_refs=refs[:1],
        )
    created = _create(
        core,
        task_id,
        command_id="v5b4:inferred:create",
        record_kind="inferred_candidate",
        semantic_key="stable preference",
        payload={"statement": "prefers diagrams"},
        source_refs=refs[:2],
    )
    assert created["candidate_only"] is True
    assert created["user_state_authority"] is False
    rejected = _decide(
        core,
        task_id,
        created,
        command_id="v5b4:inferred:reject",
        action="reject",
    )
    replay = _create(
        core,
        task_id,
        command_id="v5b4:inferred:old-boundary",
        record_kind="inferred_candidate",
        semantic_key="stable preference",
        payload={"statement": "prefers diagrams"},
        source_refs=refs[:2],
    )
    assert replay["record_revision_id"] == rejected["record_revision_id"]
    assert replay["suppressed_no_resurrection"] is True
    with pytest.raises(ResearchValidationError, match="reopen_reason"):
        _create(
            core,
            task_id,
            command_id="v5b4:inferred:new-boundary-blocked",
            record_kind="inferred_candidate",
            semantic_key="stable preference",
            payload={"statement": "prefers diagrams"},
            source_refs=[refs[0], refs[2]],
        )
    reopened = _create(
        core,
        task_id,
        command_id="v5b4:inferred:new-boundary",
        record_kind="inferred_candidate",
        semantic_key="stable preference",
        payload={"statement": "prefers diagrams"},
        source_refs=[refs[0], refs[2]],
        reopen_reason="new independent event boundary",
    )
    confirmed = _decide(
        core,
        task_id,
        reopened,
        command_id="v5b4:inferred:confirm",
        action="confirm",
    )
    assert confirmed["authority_class"] == "user_confirmed"
    assert confirmed["user_state_authority"] is True
    expired = _create(
        core,
        task_id,
        command_id="v5b4:inferred:expired",
        record_kind="inferred_candidate",
        semantic_key="temporary preference",
        payload={"statement": "temporarily exploring SQLite"},
        source_refs=refs[:2],
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    assert expired["status"] == "candidate"
    assert expired["effective_status"] == "expired"
    with pytest.raises(ResearchValidationError, match="effective status"):
        _decide(
            core,
            task_id,
            expired,
            command_id="v5b4:inferred:expired-reject",
            action="reject",
        )


def test_focus_and_progress_preserve_semantic_authority(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "workspace-progress")
    refs = _event_refs(core, task_id)
    with pytest.raises(ResearchValidationError, match="at least two"):
        _create(
            core,
            task_id,
            command_id="v5b4:focus:one-action",
            record_kind="focus_state",
            semantic_key="current focus",
            payload={"topic": "MCP", "state": "focused"},
            source_refs=refs[:1],
        )
    explicit_focus = _create(
        core,
        task_id,
        command_id="v5b4:focus:explicit",
        record_kind="focus_state",
        semantic_key="current focus",
        payload={"topic": "MCP", "state": "focused"},
    )
    assert explicit_focus["authority_class"] == "user_authored"
    with pytest.raises(ResearchValidationError, match="explicit user assertion"):
        _create(
            core,
            task_id,
            command_id="v5b4:progress:watched-is-not-learned",
            record_kind="progress_observation",
            semantic_key="MCP learning",
            payload={"topic": "MCP", "state": "learned"},
            source_refs=refs[:2],
        )
    observed = _create(
        core,
        task_id,
        command_id="v5b4:progress:researched",
        record_kind="progress_observation",
        semantic_key="MCP research progress",
        payload={"topic": "MCP", "state": "researched"},
        source_refs=refs[:2],
    )
    asserted = _create(
        core,
        task_id,
        command_id="v5b4:progress:self-asserted",
        record_kind="progress_observation",
        semantic_key="MCP self assessment",
        payload={"topic": "MCP", "state": "learned", "user_asserted": True},
    )
    assert observed["authority_class"] == "evidence_backed_observation"
    assert observed["user_state_authority"] is False
    assert asserted["authority_class"] == "user_authored"
    assert asserted["user_state_authority"] is True


def test_corpus_snapshot_soft_prior_and_product_noninterference(app_paths) -> None:
    core = _core(app_paths)
    task_id, fact, _, _ = _vertical(core, "workspace-noninterference")
    source_ids = [
        int(value["id"])
        for value in core.taxonomy_corpus.repository.selectable_sources()
    ]
    snapshot = core.taxonomy_corpus.freeze(source_ids)

    search_before = _stable_search(
        core.product_search.search(ProductSearchRequest(query=OBJECTIVE)).as_dict()
    )
    ask_before = _stable_ask(
        core.ask_service.ask(AskRequest(query="ZZZZZ-NO-SUCH-EVIDENCE")).model_dump(
            mode="json"
        )
    )
    research_before = _stable_research(
        core.research_knowledge.get_workspace(task_id)
    )
    route_before = _stable_route(
        core.research_knowledge.assess_artifact_route(
            task_id,
            AssessArtifactRouteRequest(
                command_id="v5b4:route:before",
                query=fact["claim"],
                required_aspects=[fact["claim"]],
            ),
        )
    )
    corpus = _create(
        core,
        task_id,
        command_id="v5b4:corpus:create",
        record_kind="corpus_observation",
        semantic_key="MCP corpus topic",
        payload={"observation_type": "topic", "value": "MCP"},
        source_refs=[
            WorkspaceSourceRef(
                ref_type="taxonomy_snapshot", ref_id=str(snapshot.snapshot_id)
            )
        ],
    )
    assert corpus["soft_prior_only"] is True
    assert corpus["product_behavior_effect"] is False
    with core.db.connect() as connection:
        video_id = int(
            connection.execute("SELECT id FROM videos ORDER BY id LIMIT 1").fetchone()[0]
        )
    core.db.update_video(video_id, description="changed only to form snapshot v2")
    changed_snapshot = core.taxonomy_corpus.freeze(source_ids)
    assert changed_snapshot.snapshot_id != snapshot.snapshot_id
    corpus_v2 = _create(
        core,
        task_id,
        command_id="v5b4:corpus:new-snapshot",
        record_kind="corpus_observation",
        semantic_key="MCP corpus topic",
        payload={"observation_type": "topic", "value": "MCP"},
        source_refs=[
            WorkspaceSourceRef(
                ref_type="taxonomy_snapshot", ref_id=str(changed_snapshot.snapshot_id)
            )
        ],
    )
    assert corpus_v2["version"] == 2

    search_after = _stable_search(
        core.product_search.search(ProductSearchRequest(query=OBJECTIVE)).as_dict()
    )
    ask_after = _stable_ask(
        core.ask_service.ask(AskRequest(query="ZZZZZ-NO-SUCH-EVIDENCE")).model_dump(
            mode="json"
        )
    )
    research_after = _stable_research(
        core.research_knowledge.get_workspace(task_id)
    )
    route_after = _stable_route(
        core.research_knowledge.assess_artifact_route(
            task_id,
            AssessArtifactRouteRequest(
                command_id="v5b4:route:after",
                query=fact["claim"],
                required_aspects=[fact["claim"]],
            ),
        )
    )
    assert search_after == search_before
    assert ask_after == ask_before
    assert research_after == research_before
    assert route_after == route_before
    assert route_after["open_corpus"]["independent_lane"] is True
    assert route_after["open_corpus"]["hard_filter"] is False


def test_system_experience_lineage_never_mutates_skill_or_runtime(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "workspace-experience")
    other_task_id, _, _, _ = _vertical(core, "workspace-experience-other")
    refs = _experience_refs(core, task_id)
    with core.db.connect() as connection:
        before_schema = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND (lower(name) LIKE '%skill%' OR lower(name) LIKE '%policy%') "
                "ORDER BY name"
            ).fetchall()
        ]
    crossed = [refs[0].model_copy(update={"task_id": other_task_id}), refs[1]]
    with pytest.raises(ResearchValidationError, match="crossed"):
        _create(
            core,
            task_id,
            command_id="v5b4:experience:cross-task",
            record_kind="system_experience",
            semantic_key="retry recovery",
            payload={
                "observed_pattern": "retry recovered",
                "outcome": "success",
                "environment_fingerprint": "test/no-provider",
            },
            source_refs=crossed,
        )
    observed = _create(
        core,
        task_id,
        command_id="v5b4:experience:observed",
        record_kind="system_experience",
        semantic_key="retry recovery",
        payload={
            "observed_pattern": "retry recovered",
            "outcome": "success",
            "environment_fingerprint": "test/no-provider",
        },
        source_refs=refs,
    )
    with pytest.raises(ResearchValidationError, match="effective status"):
        _decide(
            core,
            task_id,
            observed,
            command_id="v5b4:experience:premature-source",
            action="candidate_source",
        )
    diagnosed = _decide(
        core,
        task_id,
        observed,
        command_id="v5b4:experience:diagnose",
        action="diagnose",
        replacement_payload={"cause": "durable receipt preserved identity"},
    )
    candidate = _decide(
        core,
        task_id,
        diagnosed,
        command_id="v5b4:experience:candidate-source",
        action="candidate_source",
    )
    invalidated = _decide(
        core,
        task_id,
        candidate,
        command_id="v5b4:experience:invalidate",
        action="invalidate",
    )
    assert invalidated["effective_status"] == "invalidated"
    assert invalidated["candidate_only"] is True
    assert invalidated["product_behavior_effect"] is False
    with core.db.connect() as connection:
        after_schema = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND (lower(name) LIKE '%skill%' OR lower(name) LIKE '%policy%') "
                "ORDER BY name"
            ).fetchall()
        ]
    assert after_schema == before_schema


def test_workspace_cross_task_fault_rollback_and_filtered_projection(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "workspace-fault")
    other_task_id, _, _, _ = _vertical(core, "workspace-fault-other")
    other_ref = _event_refs(core, other_task_id, limit=1)[0]
    crossed_ref = other_ref.model_copy(update={"task_id": task_id})
    with pytest.raises(ResearchValidationError, match="crossed"):
        _create(
            core,
            task_id,
            command_id="v5b4:fault:cross-task",
            record_kind="progress_observation",
            semantic_key="cross task",
            payload={"topic": "MCP", "state": "researched"},
            source_refs=[crossed_ref],
        )

    core.research_knowledge.fault_injector = lambda point: (
        (_ for _ in ()).throw(SimulatedCrash(point))
        if point == "after_stage4_workspace_record"
        else None
    )
    with pytest.raises(SimulatedCrash, match="after_stage4_workspace_record"):
        _create(
            core,
            task_id,
            command_id="v5b4:fault:create",
            record_kind="explicit_memory",
            semantic_key="rollback memory",
            payload={"key": "rollback", "value": "must disappear"},
        )
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_workspace_records WHERE command_id=?",
            ("v5b4:fault:create",),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM research_command_receipts WHERE command_id=?",
            ("v5b4:fault:create",),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM research_events WHERE command_id=?",
            ("v5b4:fault:create",),
        ).fetchone()[0] == 0

    core.research_knowledge.fault_injector = lambda _point: None
    created = _create(
        core,
        task_id,
        command_id="v5b4:fault:create",
        record_kind="explicit_memory",
        semantic_key="rollback memory",
        payload={"key": "rollback", "value": "persist after retry"},
    )
    core.research_knowledge.fault_injector = lambda point: (
        (_ for _ in ()).throw(SimulatedCrash(point))
        if point == "after_stage4_workspace_decision"
        else None
    )
    with pytest.raises(SimulatedCrash, match="after_stage4_workspace_decision"):
        _decide(
            core,
            task_id,
            created,
            command_id="v5b4:fault:decision",
            action="expire",
        )
    restarted = Application(core.paths)
    projected = restarted.research_knowledge.get_personal_workspace(
        task_id, record_kind="explicit_memory", status="current"
    )
    selected = next(
        value for value in projected["records"] if value["record_id"] == created["record_id"]
    )
    assert selected["version"] == 1
    with restarted.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_command_receipts WHERE command_id=?",
            ("v5b4:fault:decision",),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM research_events WHERE command_id=?",
            ("v5b4:fault:decision",),
        ).fetchone()[0] == 0
