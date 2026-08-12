from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.db import SCHEMA_VERSION
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.research.knowledge_assistance import POLICY_VERSION
from shiliu.research.knowledge_contracts import CreateWorkspaceRecordRequest
from shiliu.retrieval.coordinator import SYNC_STATE_VERSION
from shiliu.web import create_web_app
from test_v5_b_stage3_artifact_reuse import _core, _vertical
from test_v5_b_stage4_personal_workspace import _create, _decide, _event_refs


def _project(core: Application, task_id: str, **overrides) -> dict:
    request = {
        "principal_id": "local_operator",
        "assistance_enabled": True,
    }
    request.update(overrides)
    return core.research_knowledge.get_personal_workspace(task_id, **request)[
        "knowledge_assistance"
    ]


def _counts(core: Application) -> dict[str, int]:
    with core.db.connect() as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "research_workspace_records",
                "research_events",
                "research_command_receipts",
                "research_knowledge_fact_states",
                "taxonomy_corpus_snapshots",
            )
        }


def _source_id(core: Application) -> int:
    with core.db.connect() as connection:
        return int(connection.execute("SELECT id FROM favorite_sources ORDER BY id LIMIT 1").fetchone()[0])


def _add_current_item(core: Application, source_id: int) -> int:
    existing = FavoriteItem(
        bvid="BV5303000001",
        title="V5-B Artifact Reuse Fixture",
        uploader="V5B",
        favorite_time=1,
    )
    added = FavoriteItem(
        bvid="BV5404000002",
        title="New project candidate",
        uploader="V5C",
        favorite_time=2,
    )
    core.db.record_source_snapshot(source_id, [existing, added], processing_profile="formal")
    video = core.db.get_video_by_source(added.bvid)
    assert video is not None
    video_id = int(video["id"])
    _, raw_path = core.artifacts.save_raw_subtitle(
        added.bvid,
        [
            SubtitleSegment.model_validate(
                {"from": 0, "to": 5, "content": "MCP project adds an exact idempotent receipt."}
            )
        ],
    )
    core.db.update_video(
        video_id,
        title=added.title,
        uploader=added.uploader,
        description="",
        status="completed",
        raw_subtitle_path=str(raw_path),
        subtitle_source="human",
        subtitle_language="en",
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
    return video_id


def _snapshot_pair(core: Application) -> tuple[int, int]:
    source_id = _source_id(core)
    baseline = core.taxonomy_corpus.freeze([source_id])
    _add_current_item(core, source_id)
    current = core.taxonomy_corpus.freeze([source_id])
    return baseline.snapshot_id, current.snapshot_id


def test_stage4_cold_explicit_progress_watched_not_mastered_disabled_and_restart(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "v5c4-progress")
    assert SCHEMA_VERSION == 16
    before = _counts(core)
    cold = _project(core, task_id)
    assert cold["policy_version"] == POLICY_VERSION
    assert cold["status"] == "baseline"
    assert cold["lanes"]["progress"]["cards"] == []
    assert _counts(core) == before

    _create(
        core,
        task_id,
        command_id="v5c4:mastered",
        record_kind="progress_observation",
        semantic_key="mcp",
        payload={"topic": "MCP", "state": "mastered", "user_asserted": True},
    )
    _create(
        core,
        task_id,
        command_id="v5c4:watched",
        record_kind="progress_observation",
        semantic_key="leases",
        payload={"topic": "leases", "state": "reviewed", "observation_type": "watched"},
        source_refs=_event_refs(core, task_id, 1),
    )
    treatment = _project(core, task_id)
    cards = treatment["lanes"]["progress"]["cards"]
    assert [value["mastery"] for value in cards] == [True, False]
    assert cards[0]["state"] == "mastered"
    assert cards[1]["observation_type"] == "watched"
    durable = _counts(core)
    assert _project(core, task_id, assistance_enabled=False)["status"] == "disabled"
    assert _counts(core) == durable
    assert _project(Application(app_paths), task_id) == treatment


def test_stage4_persisted_staleness_is_bounded_and_read_only(app_paths) -> None:
    core = _core(app_paths)
    task_id, fact, _, _ = _vertical(core, "v5c4-stale")
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE research_knowledge_fact_states SET currentness_status='stale', "
            "state_version=state_version+1 WHERE fact_id=?",
            (fact["fact_id"],),
        )
    before = _counts(core)
    treatment = _project(core, task_id)
    cards = treatment["lanes"]["staleness"]["cards"]
    assert len(cards) == 1
    assert cards[0]["kind"] == "staleness"
    assert cards[0]["dismiss_control"]["source_refs"][0]["ref_type"] == "fact_revision"
    assert "persisted Fact lineage" in cards[0]["explanation"]
    assert _counts(core) == before
    with core.db.connect() as connection:
        state = connection.execute(
            "SELECT currentness_status FROM research_knowledge_fact_states WHERE fact_id=?",
            (fact["fact_id"],),
        ).fetchone()[0]
    assert state == "stale"


def test_stage4_same_scope_delta_radar_drift_and_exact_dismiss_lifecycle(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "v5c4-radar")
    baseline_id, current_id = _snapshot_pair(core)
    _create(
        core,
        task_id,
        command_id="v5c4:candidate-focus",
        record_kind="focus_state",
        semantic_key="unrelated",
        payload={"topic": "unrelated", "state": "active"},
        source_refs=_event_refs(core, task_id, 2),
    )
    candidate_baseline = _project(
        core, task_id,
        baseline_snapshot_id=baseline_id,
        current_snapshot_id=current_id,
    )
    assert candidate_baseline["lanes"]["radar"]["cards"] == []
    assert candidate_baseline["lanes"]["collection_delta"]["cards"]
    _create(
        core,
        task_id,
        command_id="v5c4:focus",
        record_kind="focus_state",
        semantic_key="mcp",
        payload={"topic": "MCP", "state": "active"},
    )
    treatment = _project(
        core,
        task_id,
        baseline_snapshot_id=baseline_id,
        current_snapshot_id=current_id,
    )
    delta = treatment["lanes"]["collection_delta"]["cards"]
    radar = treatment["lanes"]["radar"]["cards"]
    assert len(delta) == 1 and delta[0]["delta_kind"] == "added"
    assert len(radar) == 1
    assert "current transcript exact match" in radar[0]["explanation"]
    assert treatment["authority"]["citation_or_verifier"] is False

    control = radar[0]["dismiss_control"]
    core.research_knowledge.create_personal_workspace_record(
        task_id,
        CreateWorkspaceRecordRequest(
            command_id="v5c4:wrong-source-dismiss",
            **{**control, "source_refs": control["source_refs"][:1]},
            reason="wrong source boundary must not suppress",
        ),
        principal_id="local_operator",
    )
    wrong_source = _project(
        core, task_id,
        baseline_snapshot_id=baseline_id,
        current_snapshot_id=current_id,
    )
    assert len(wrong_source["lanes"]["radar"]["cards"]) == 1
    dismissed = core.research_knowledge.create_personal_workspace_record(
        task_id,
        CreateWorkspaceRecordRequest(
            command_id="v5c4:dismiss",
            **control,
            reason="explicit test click",
        ),
        principal_id="local_operator",
    )
    after = _project(core, task_id, baseline_snapshot_id=baseline_id, current_snapshot_id=current_id)
    assert after["lanes"]["radar"]["cards"] == []
    tombstoned = _decide(
        core,
        task_id,
        dismissed,
        command_id="v5c4:dismiss-tombstone",
        action="tombstone",
    )
    after_tombstone = _project(core, task_id, baseline_snapshot_id=baseline_id, current_snapshot_id=current_id)
    assert after_tombstone["lanes"]["radar"]["cards"] == []
    restored = _decide(
        core,
        task_id,
        tombstoned,
        command_id="v5c4:dismiss-restore",
        action="correct",
        replacement_payload={**control["payload"], "dismissed": False},
    )
    assert restored["version"] == 4
    restored_context = _project(core, task_id, baseline_snapshot_id=baseline_id, current_snapshot_id=current_id)
    assert len(restored_context["lanes"]["radar"]["cards"]) == 1
    assert _project(
        Application(app_paths), task_id,
        baseline_snapshot_id=baseline_id,
        current_snapshot_id=current_id,
    ) == restored_context

    source_id = _source_id(core)
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE videos SET description='preview drift' WHERE id=(SELECT video_id FROM video_source_memberships WHERE source_id=? ORDER BY source_position DESC LIMIT 1)",
            (source_id,),
        )
    drift = _project(core, task_id, baseline_snapshot_id=baseline_id, current_snapshot_id=current_id)
    assert drift["lanes"]["collection_delta"]["cards"] == []
    assert drift["lanes"]["collection_delta"]["reason_codes"] == ["current_preview_drift_fail_closed"]
    assert drift["lanes"]["radar"]["cards"] == []


def test_stage4_temporary_expiry_api_surface_and_no_automatic_post(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "v5c4-api")
    baseline_id, current_id = _snapshot_pair(core)
    _create(
        core,
        task_id,
        command_id="v5c4:api-focus",
        record_kind="focus_state",
        semantic_key="mcp",
        payload={"topic": "MCP", "state": "active"},
    )
    app = create_web_app(core)
    with TestClient(app) as client:
        response = client.get(
            f"/api/research/product/tasks/{task_id}/workspace",
            params={
                "assistance_enabled": "true",
                "baseline_snapshot_id": baseline_id,
                "current_snapshot_id": current_id,
            },
        )
        assert response.status_code == 200
        context = response.json()["workspace"]["knowledge_assistance"]
        assert len(context["lanes"]["radar"]["cards"]) == 1
        before = _counts(core)
        page = client.get(f"/research/{task_id}")
        assert page.status_code == 200
        assert "Knowledge Progress &amp; Assistance" in page.text
        script = client.get("/static/research.js").text
        assert "sessionDismissedAssistance.add" in script
        assert "assistance-dismiss" in script
        assert "data-assistance-refresh" in page.text

    # Page/API reads are zero-write. An already-expired explicit control restores the card.
    assert _counts(core) == before
    control = context["lanes"]["radar"]["cards"][0]["dismiss_control"]
    core.research_knowledge.create_personal_workspace_record(
        task_id,
        CreateWorkspaceRecordRequest(
            command_id="v5c4:expired-dismiss",
            **control,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            reason="explicit temporary dismiss fixture",
        ),
        principal_id="local_operator",
    )
    restored = _project(
        core, task_id,
        baseline_snapshot_id=baseline_id,
        current_snapshot_id=current_id,
    )
    assert len(restored["lanes"]["radar"]["cards"]) == 1
