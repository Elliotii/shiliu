from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.db import SCHEMA_VERSION
from shiliu.research.knowledge_contracts import WorkspaceSourceRef
from shiliu.research.routing_recommendation import (
    ROUTE_RECOMMENDATION_POLICY_VERSION,
    ROUTING_PREFERENCE_KEY,
)
from shiliu.web import create_web_app
from test_v5_b_stage3_artifact_reuse import _assess, _core, _vertical
from test_v5_b_stage4_personal_workspace import _create, _decide, _event_refs


def _schema_identity(core: Application) -> list[tuple[str, str, str]]:
    with core.db.connect() as connection:
        return [
            (str(row[0]), str(row[1]), str(row[2] or ""))
            for row in connection.execute(
                "SELECT type, name, sql FROM sqlite_master "
                "WHERE type IN ('table','index','trigger') ORDER BY type, name"
            ).fetchall()
        ]


def _counts(core: Application) -> dict[str, int]:
    tables = (
        "research_tasks",
        "research_events",
        "research_command_receipts",
        "research_artifact_routes",
        "research_workspace_records",
        "asr_jobs",
    )
    with core.db.connect() as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }


def _route_preference(
    core: Application, task_id: str, path: str, *, suffix: str
) -> dict:
    return _create(
        core,
        task_id,
        command_id=f"v5c3:preference:{suffix}",
        record_kind="explicit_memory",
        semantic_key=ROUTING_PREFERENCE_KEY,
        payload={"key": ROUTING_PREFERENCE_KEY, "value": path},
    )


def _project(core: Application, task_id: str, **overrides) -> dict:
    request = {
        "principal_id": "local_operator",
        "routing_enabled": True,
        "allow_provider_answer": False,
        "allow_high_cost_or_durable": False,
        "allow_manual_asr": False,
    }
    request.update(overrides)
    return core.research_knowledge.get_personal_workspace(task_id, **request)[
        "route_recommendation"
    ]


def test_stage3_baseline_confirmed_disabled_override_restart_and_rollback(
    app_paths,
) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "v5c3-paired")
    assert SCHEMA_VERSION == 17
    schema_before = _schema_identity(core)

    baseline_counts = _counts(core)
    baseline = _project(core, task_id)
    assert baseline["policy_version"] == ROUTE_RECOMMENDATION_POLICY_VERSION
    assert baseline["status"] == "baseline"
    assert baseline["recommendation"] is None
    assert baseline["reason_codes"] == ["no_confirmed_route_preference"]

    _create(
        core,
        task_id,
        command_id="v5c3:unrelated",
        record_kind="explicit_memory",
        semantic_key="answer density",
        payload={"key": "answer density", "value": "compact"},
    )
    assert _project(core, task_id)["status"] == "baseline"

    preference = _route_preference(core, task_id, "deep", suffix="paired")
    durable_counts = _counts(core)
    treatment_workspace = core.research_knowledge.get_personal_workspace(
        task_id,
        principal_id="local_operator",
        routing_enabled=True,
        allow_provider_answer=True,
        allow_high_cost_or_durable=True,
    )
    treatment = treatment_workspace["route_recommendation"]
    assert treatment["status"] == "recommended"
    assert treatment["recommendation"]["path"] == "deep"
    assert treatment["preference"]["record_revision_id"] == preference[
        "record_revision_id"
    ]
    assert treatment["recommendation"]["cta"]["href"].startswith(
        "/ask?q="
    )
    assert treatment["authority"]["execution_authority"] is False
    assert treatment["authority"]["permission_authority"] is False
    assert set(treatment["side_effects"].values()) == {0}
    selected = next(
        value
        for value in treatment_workspace["records"]
        if value["record_id"] == preference["record_id"]
    )
    assert selected["route_recommendation_effect"] is True

    disabled = _project(
        core,
        task_id,
        routing_enabled=False,
        allow_provider_answer=True,
        allow_high_cost_or_durable=True,
    )
    assert disabled["status"] == "disabled"
    assert disabled["recommendation"] is None
    overridden = _project(
        core,
        task_id,
        current_explicit_path="fast",
        allow_provider_answer=True,
        allow_high_cost_or_durable=True,
    )
    assert overridden["status"] == "overridden"
    assert overridden["settings"]["current_explicit_path"] == "fast"
    assert overridden["explicit_choice_preserved"] is True
    assert overridden["recommendation"] is None

    restarted = Application(app_paths)
    restarted_context = _project(
        restarted,
        task_id,
        allow_provider_answer=True,
        allow_high_cost_or_durable=True,
    )
    assert restarted_context == treatment
    assert _counts(core) == durable_counts

    corrected = _decide(
        core,
        task_id,
        preference,
        command_id="v5c3:correct-fast",
        action="correct",
        replacement_payload={"key": ROUTING_PREFERENCE_KEY, "value": "fast"},
    )
    corrected_context = _project(core, task_id, allow_provider_answer=True)
    assert corrected_context["recommendation"]["path"] == "fast"
    tombstoned = _decide(
        core,
        task_id,
        corrected,
        command_id="v5c3:tombstone",
        action="tombstone",
    )
    assert tombstoned["effective_status"] == "tombstoned"
    rolled_back = _project(
        core,
        task_id,
        allow_provider_answer=True,
        allow_high_cost_or_durable=True,
    )
    assert rolled_back["status"] == "baseline"
    assert rolled_back["recommendation"] is None
    assert "terminal_route_preference_not_applied" in rolled_back["reason_codes"]
    assert _schema_identity(core) == schema_before
    assert baseline_counts["asr_jobs"] == _counts(core)["asr_jobs"]


def test_stage3_candidate_focus_corpus_principal_and_content_drift_fail_closed(
    app_paths,
) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "v5c3-authority")
    _create(
        core,
        task_id,
        command_id="v5c3:candidate",
        record_kind="inferred_candidate",
        semantic_key=ROUTING_PREFERENCE_KEY,
        payload={"statement": "deep"},
        source_refs=_event_refs(core, task_id, limit=2),
    )
    _create(
        core,
        task_id,
        command_id="v5c3:focus",
        record_kind="focus_state",
        semantic_key="current focus",
        payload={"topic": "MCP", "state": "active"},
    )
    with core.db.connect() as connection:
        source_id = int(
            connection.execute("SELECT id FROM favorite_sources ORDER BY id LIMIT 1").fetchone()[0]
        )
    snapshot = core.taxonomy_corpus.freeze([source_id])
    _create(
        core,
        task_id,
        command_id="v5c3:corpus",
        record_kind="corpus_observation",
        semantic_key="MCP corpus topic",
        payload={"observation_type": "topic", "value": "MCP"},
        source_refs=[
            WorkspaceSourceRef(
                ref_type="taxonomy_snapshot", ref_id=str(snapshot.snapshot_id)
            )
        ],
    )
    candidate = _project(
        core,
        task_id,
        allow_provider_answer=True,
        allow_high_cost_or_durable=True,
    )
    assert candidate["status"] == "baseline"
    assert "candidate_route_preference_not_confirmed" in candidate["reason_codes"]
    assert candidate["recommendation"] is None

    preference = _route_preference(core, task_id, "research", suffix="authority")
    research_denied = _project(core, task_id)
    assert research_denied["status"] == "blocked"
    assert research_denied["reason_codes"] == ["research_cost_denied"]
    research_allowed = _project(
        core, task_id, allow_high_cost_or_durable=True
    )
    assert research_allowed["status"] == "recommended"
    assert research_allowed["recommendation"]["path"] == "research"
    wrong_principal = _project(
        core,
        task_id,
        principal_id="different_operator",
        allow_high_cost_or_durable=True,
    )
    assert wrong_principal["status"] == "fail_closed"
    assert wrong_principal["reason_codes"] == ["unauthorized_route_preference"]

    with core.db.connect() as connection:
        row = connection.execute(
            "SELECT * FROM research_workspace_records WHERE record_revision_id=?",
            (preference["record_revision_id"],),
        ).fetchone()
        assert row is not None
        columns = [value[1] for value in connection.execute("PRAGMA table_info(research_workspace_records)")]
        values = dict(row)
        values["record_revision_id"] = "workspacerevision_conflicting_route"
        values["record_id"] = "workspacerecord_conflicting_route"
        values["command_id"] = "v5c3:synthetic-conflict"
        values["payload_json"] = json.dumps(
            {"key": ROUTING_PREFERENCE_KEY, "value": "fast"},
            sort_keys=True,
            separators=(",", ":"),
        )
        identity = {
            "record_kind": values["record_kind"],
            "authority_class": values["authority_class"],
            "status": values["status"],
            "semantic_key": values["semantic_key"],
            "payload": json.loads(values["payload_json"]),
            "source_refs": json.loads(values["source_refs_json"]),
            "confidence": values["confidence"],
            "expires_at": values["expires_at"],
            "policy_version": values["policy_version"],
        }
        values["content_hash"] = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        placeholders = ",".join("?" for _ in columns)
        connection.execute(
            f"INSERT INTO research_workspace_records({','.join(columns)}) VALUES({placeholders})",
            tuple(values[column] for column in columns),
        )
    conflict = _project(core, task_id, allow_high_cost_or_durable=True)
    assert conflict["status"] == "fail_closed"
    assert conflict["reason_codes"] == ["confirmed_route_preference_conflict"]


def test_stage3_artifact_gate_permission_cost_and_manual_asr_noninterference(
    app_paths,
) -> None:
    core = _core(app_paths)
    task_id, fact, _, _ = _vertical(core, "v5c3-gates")
    preference = _route_preference(core, task_id, "fast", suffix="gates")
    assessed = _assess(
        core,
        task_id,
        suffix="v5c3-direct",
        query=fact["claim"],
        aspects=[fact["claim"]],
    )
    assert assessed["recommended_route"] == "direct_reuse"
    counts_before = _counts(core)
    direct = _project(core, task_id)
    assert direct["status"] == "recommended"
    assert direct["recommendation"] == {
        "path": "artifact_route",
        "artifact_route": "direct_reuse",
        "cta": {"kind": "focus_artifact_route"},
    }
    assert direct["preference"]["record_revision_id"] == preference[
        "record_revision_id"
    ]
    assert direct["capabilities"]["artifact_route"]["open_corpus"] == {
        "independent_lane": True,
        "hard_filter": False,
        "summary_hash": assessed["open_corpus"]["summary_hash"],
    }
    assert _counts(core) == counts_before

    with core.db.connect() as connection:
        connection.execute(
            "UPDATE research_knowledge_fact_states SET currentness_status='stale', "
            "state_version=state_version+1 WHERE fact_id=?",
            (fact["fact_id"],),
        )
    stale = _project(core, task_id)
    assert stale["status"] == "fail_closed"
    assert stale["reason_codes"] == ["artifact_route_authority_drift"]
    assert stale["recommendation"] is None
    stale_explicit = _project(
        core, task_id, current_explicit_path="artifact_route"
    )
    assert stale_explicit["status"] == "overridden"
    assert stale_explicit["explicit_choice_preserved"] is True
    assert "selected_artifact_context_unsafe" in stale_explicit["reason_codes"]

    fresh_task, _, _, _ = _vertical(core, "v5c3-asr")
    preference = _decide(
        core,
        fresh_task,
        preference,
        command_id="v5c3:preference:asr",
        action="correct",
        replacement_payload={"key": ROUTING_PREFERENCE_KEY, "value": "deep"},
    )
    denied = _project(core, fresh_task, allow_provider_answer=False)
    assert denied["status"] == "blocked"
    assert denied["reason_codes"] == ["deep_permission_denied"]
    cost_denied = _project(
        core,
        fresh_task,
        allow_provider_answer=True,
        allow_high_cost_or_durable=False,
    )
    assert cost_denied["status"] == "blocked"
    assert cost_denied["reason_codes"] == ["deep_cost_denied"]

    with core.db.connect() as connection:
        video_id = int(connection.execute("SELECT id FROM videos ORDER BY id DESC LIMIT 1").fetchone()[0])
    transcript_available = _project(
        core,
        fresh_task,
        allow_provider_answer=True,
        allow_high_cost_or_durable=True,
        allow_manual_asr=True,
        asr_video_id=video_id,
    )
    assert transcript_available["status"] == "blocked"
    assert transcript_available["reason_codes"] == ["manual_asr_inapplicable"]
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE videos SET raw_subtitle_path=NULL WHERE id=?", (video_id,)
        )
    asr_counts = _counts(core)
    asr_denied = _project(
        core,
        fresh_task,
        allow_provider_answer=True,
        allow_high_cost_or_durable=True,
        asr_video_id=video_id,
    )
    assert asr_denied["status"] == "blocked"
    assert asr_denied["reason_codes"] == ["manual_asr_permission_denied"]
    manual = _project(
        core,
        fresh_task,
        allow_provider_answer=True,
        allow_high_cost_or_durable=True,
        allow_manual_asr=True,
        asr_video_id=video_id,
    )
    assert manual["status"] == "recommended"
    assert manual["recommendation"]["path"] == "manual_asr"
    assert manual["recommendation"]["then_path"] == "deep"
    assert manual["capabilities"]["manual_asr"]["credential_checked"] is False
    uncertain = _project(
        core,
        fresh_task,
        allow_manual_asr=True,
        asr_video_id=999999,
    )
    assert uncertain["status"] == "fail_closed"
    assert uncertain["reason_codes"] == ["manual_asr_context_unsafe"]
    assert _counts(core) == asr_counts


def test_stage3_workspace_api_panel_and_inert_cta(app_paths, monkeypatch) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "v5c3-api")
    _route_preference(core, task_id, "fast", suffix="api")
    counts_before = _counts(core)
    def forbidden_execution(*_args, **_kwargs):
        raise AssertionError("read-only routing projection attempted execution")

    monkeypatch.setattr(core, "provider", forbidden_execution)
    monkeypatch.setattr(core, "asr_service", forbidden_execution)
    monkeypatch.setattr(core.ask_service, "ask", forbidden_execution)
    monkeypatch.setattr(core.research_product, "create_task", forbidden_execution)
    monkeypatch.setattr(core.research_product, "run_to_boundary", forbidden_execution)
    monkeypatch.setattr(
        core.research_knowledge, "proceed_artifact_route", forbidden_execution
    )
    client = TestClient(create_web_app(core))

    response = client.get(
        f"/api/research/product/tasks/{task_id}/workspace",
        params={"allow_provider_answer": "true"},
    )
    assert response.status_code == 200
    context = response.json()["workspace"]["route_recommendation"]
    assert context["status"] == "recommended"
    assert context["recommendation"]["path"] == "fast"
    assert context["capabilities"]["translation"] == {
        "status": "not_implemented",
        "reason": "not_a_distinct_route",
    }

    explicit = client.get(
        f"/api/research/product/tasks/{task_id}/workspace",
        params={
            "allow_provider_answer": "true",
            "current_explicit_path": "deep",
        },
    ).json()["workspace"]["route_recommendation"]
    assert explicit["status"] == "overridden"
    assert explicit["settings"]["current_explicit_path"] == "deep"

    page = client.get(f"/research/{task_id}")
    assert page.status_code == 200
    assert 'data-route-recommendation-panel' in page.text
    assert 'data-routing-explicit-path' in page.text
    assert 'data-routing-provider-permission' in page.text
    assert 'Translation route' not in page.text
    script = client.get("/static/research.js").text
    assert "renderRouteRecommendation" in script
    assert "execution authority false" in script
    assert "focus.addEventListener('click'" in script
    assert "focus.click(" not in script
    assert "/api/videos/${" not in script
    assert _counts(core) == counts_before
