from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from shiliu.db import SCHEMA_VERSION
from shiliu.research.errors import ResearchValidationError
from shiliu.research.knowledge_contracts import (
    CreateWorkspaceRecordRequest,
    DecideWorkspaceRecordRequest,
    SubmitKnowledgeFeedbackRequest,
    WorkspaceSourceRef,
)
from shiliu.research.personalization import (
    LIMITATIONS_POSITION_KEY,
    PERSONALIZATION_CONTEXT_POLICY_VERSION,
    PersonalizationContextProjection,
)
from shiliu.web import create_web_app
from test_v5_b_stage3_artifact_reuse import _core, _vertical
from test_v5_b_stage4_personal_workspace import _create, _decide


def _product_authority(value: dict) -> dict:
    return {
        "state": value["state"],
        "answer_blocks": value["answer_blocks"],
        "citations": value["citations"],
        "limitations": value["limitations"],
        "provider_status": value["provider_status"],
    }


def _schema_identity(core) -> list[tuple[str, str, str]]:
    with core.db.connect() as connection:
        return [
            (str(row[0]), str(row[1]), str(row[2] or ""))
            for row in connection.execute(
                "SELECT type, name, sql FROM sqlite_master "
                "WHERE type IN ('table','index','trigger') ORDER BY type, name"
            ).fetchall()
        ]


def _feedback(
    core,
    task_id: str,
    page: dict,
    *,
    command_id: str,
    proposed_value: str | None,
    principal_id: str = "local_operator",
) -> dict:
    preference = (
        {
            "semantic_key": LIMITATIONS_POSITION_KEY,
            "proposed_value": proposed_value,
        }
        if proposed_value is not None
        else None
    )
    return core.research_knowledge.submit_feedback(
        task_id,
        SubmitKnowledgeFeedbackRequest(
            command_id=command_id,
            target_kind="topic_page_revision",
            target_id=page["page_revision_id"],
            decision="helpful",
            reason_code="answer_quality",
            note="bounded Stage 1 preference feedback",
            expected_hash=page["content_hash"],
            candidate_preference=preference,
        ),
        principal_id=principal_id,
    )


def _source_refs(task_id: str, *events: dict) -> list[WorkspaceSourceRef]:
    return [
        WorkspaceSourceRef(
            ref_type="research_event", ref_id=value["event_id"], task_id=task_id
        )
        for value in events
    ]


def test_stage1_projection_conflict_and_malformed_inputs_fail_closed() -> None:
    base = {
        "semantic_key": LIMITATIONS_POSITION_KEY,
        "effective_status": "current",
        "record_kind": "explicit_memory",
        "authority_class": "user_authored",
        "record_id": "explicit",
        "record_revision_id": "explicit-v1",
        "version": 1,
        "content_hash": "a" * 64,
        "created_at": "2026-08-09T00:00:00+00:00",
        "payload": {
            "key": LIMITATIONS_POSITION_KEY,
            "value": "before_answer",
        },
    }
    conflicting = {
        **base,
        "record_kind": "inferred_candidate",
        "authority_class": "user_confirmed",
        "effective_status": "confirmed",
        "record_id": "candidate",
        "record_revision_id": "candidate-v2",
        "version": 2,
        "content_hash": "b" * 64,
        "created_at": "2026-08-09T00:01:00+00:00",
        "payload": {"statement": "after_answer"},
    }
    projection = PersonalizationContextProjection()
    context = projection.project([base, conflicting])
    assert context["applied"] is False
    assert context["preference"] is None
    assert "confirmed_preference_conflict_fail_closed" in context["reason_codes"]

    malformed = {
        **base,
        "record_revision_id": "explicit-bad",
        "payload": {
            "key": LIMITATIONS_POSITION_KEY,
            "value": "sometimes_before",
        },
    }
    first = projection.project([malformed])
    second = projection.project([malformed])
    assert first == second
    assert first["applied"] is False
    assert "malformed_or_unauthorized_preference" in first["reason_codes"]


def test_stage1_paired_profile_disable_restore_tombstone_and_noninterference(
    app_paths,
) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "v5c-stage1-paired")
    assert SCHEMA_VERSION == 15
    schema_before = _schema_identity(core)
    product_before = _product_authority(core.research_product.get_task(task_id))

    baseline = core.research_knowledge.get_personal_workspace(task_id)
    context = baseline["personalization_context"]
    assert context["policy_version"] == PERSONALIZATION_CONTEXT_POLICY_VERSION
    assert context["applied"] is False
    assert context["preference"] is None
    assert context["reason_codes"] == ["no_confirmed_preference"]

    _create(
        core,
        task_id,
        command_id="v5c1:unrelated",
        record_kind="explicit_memory",
        semantic_key="answer density",
        payload={"key": "answer density", "value": "compact"},
    )
    unrelated = core.research_knowledge.get_personal_workspace(task_id)
    assert unrelated["personalization_context"]["applied"] is False

    _create(
        core,
        task_id,
        command_id="v5c1:focus",
        record_kind="focus_state",
        semantic_key="MCP Project",
        payload={"topic": "MCP Project", "state": "active"},
    )
    created = _create(
        core,
        task_id,
        command_id="v5c1:preference",
        record_kind="explicit_memory",
        semantic_key=LIMITATIONS_POSITION_KEY,
        payload={"key": LIMITATIONS_POSITION_KEY, "value": "before_answer"},
    )
    treatment = core.research_knowledge.get_personal_workspace(task_id)
    treatment_context = treatment["personalization_context"]
    assert treatment_context["applied"] is True
    assert treatment_context["preference"]["value"] == "before_answer"
    assert treatment_context["preference"]["record_revision_id"] == created[
        "record_revision_id"
    ]
    assert treatment_context["current_focus"]["topic"] == "MCP Project"
    selected = next(
        value for value in treatment["records"] if value["record_id"] == created["record_id"]
    )
    assert selected["product_behavior_effect"] is True

    disabled = core.research_knowledge.get_personal_workspace(
        task_id, personalization_enabled=False
    )
    assert disabled["personalization_context"]["applied"] is False
    assert disabled["personalization_context"]["preference"]["value"] == "before_answer"
    assert "personalization_disabled" in disabled["personalization_context"][
        "reason_codes"
    ]
    assert not any(value["product_behavior_effect"] for value in disabled["records"])

    corrected = _decide(
        core,
        task_id,
        created,
        command_id="v5c1:correct-after",
        action="correct",
        replacement_payload={
            "key": LIMITATIONS_POSITION_KEY,
            "value": "after_answer",
        },
    )
    assert core.research_knowledge.get_personal_workspace(task_id)[
        "personalization_context"
    ]["preference"]["value"] == "after_answer"
    restored = core.research_knowledge.decide_personal_workspace_record(
        task_id,
        corrected["record_id"],
        DecideWorkspaceRecordRequest(
            command_id="v5c1:restore-before",
            action="correct",
            expected_version=corrected["version"],
            replacement_payload={
                "key": LIMITATIONS_POSITION_KEY,
                "value": "before_answer",
            },
            reason="restore_previous_value:v1",
        ),
        principal_id="local_operator",
    )
    restored_workspace = core.research_knowledge.get_personal_workspace(task_id)
    restored_record = next(
        value
        for value in restored_workspace["records"]
        if value["record_id"] == restored["record_id"]
    )
    assert restored["version"] == 3
    assert [value["payload"]["value"] for value in restored_record["history"]] == [
        "before_answer",
        "after_answer",
        "before_answer",
    ]
    assert restored_workspace["personalization_context"]["preference"][
        "record_revision_id"
    ] == restored["record_revision_id"]

    tombstoned = _decide(
        core,
        task_id,
        restored,
        command_id="v5c1:tombstone",
        action="tombstone",
    )
    assert tombstoned["effective_status"] == "tombstoned"
    rolled_back = core.research_knowledge.get_personal_workspace(task_id)
    assert rolled_back["personalization_context"]["applied"] is False
    assert rolled_back["personalization_context"]["preference"] is None
    assert "terminal_record_not_applied" in rolled_back["personalization_context"][
        "reason_codes"
    ]

    assert _product_authority(core.research_product.get_task(task_id)) == product_before
    assert _schema_identity(core) == schema_before


def test_stage1_structured_feedback_candidate_confirmation_and_principal_fence(
    app_paths,
) -> None:
    core = _core(app_paths)
    task_id, _, _, page = _vertical(core, "v5c-stage1-feedback")
    first = _feedback(
        core,
        task_id,
        page,
        command_id="v5c1:feedback:first",
        proposed_value="before_answer",
    )
    second = _feedback(
        core,
        task_id,
        page,
        command_id="v5c1:feedback:second",
        proposed_value="before_answer",
    )
    assert first["candidate_preference"]["proposed_value"] == "before_answer"
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_workspace_records"
        ).fetchone()[0] == 0
        event_payload = json.loads(
            connection.execute(
                "SELECT payload_json FROM research_events WHERE event_id=?",
                (first["event_id"],),
            ).fetchone()[0]
        )
    assert event_payload["authority"] == "advisory_feedback_only"
    assert event_payload["automatic_action"] is False
    assert event_payload["principal_id"] == "local_operator"

    with pytest.raises(ResearchValidationError, match="exact candidate key and value"):
        _create(
            core,
            task_id,
            command_id="v5c1:candidate:mismatch",
            record_kind="inferred_candidate",
            semantic_key=LIMITATIONS_POSITION_KEY,
            payload={"statement": "after_answer"},
            source_refs=_source_refs(task_id, first, second),
        )

    candidate = _create(
        core,
        task_id,
        command_id="v5c1:candidate:create",
        record_kind="inferred_candidate",
        semantic_key=LIMITATIONS_POSITION_KEY,
        payload={"statement": "before_answer"},
        source_refs=_source_refs(task_id, first, second),
    )
    candidate_context = core.research_knowledge.get_personal_workspace(task_id)[
        "personalization_context"
    ]
    assert candidate_context["applied"] is False
    assert "candidate_not_confirmed" in candidate_context["reason_codes"]

    confirmed = _decide(
        core,
        task_id,
        candidate,
        command_id="v5c1:candidate:confirm",
        action="confirm",
    )
    confirmed_context = core.research_knowledge.get_personal_workspace(task_id)[
        "personalization_context"
    ]
    assert confirmed_context["applied"] is True
    assert confirmed_context["preference"]["record_revision_id"] == confirmed[
        "record_revision_id"
    ]
    corrected_candidate = _decide(
        core,
        task_id,
        confirmed,
        command_id="v5c1:candidate:correct",
        action="correct",
        replacement_payload={"statement": "after_answer"},
    )
    corrected_context = core.research_knowledge.get_personal_workspace(task_id)[
        "personalization_context"
    ]
    assert corrected_context["preference"]["value"] == "after_answer"
    rejected = _decide(
        core,
        task_id,
        corrected_candidate,
        command_id="v5c1:candidate:reject",
        action="reject",
    )
    assert rejected["effective_status"] == "rejected"
    assert core.research_knowledge.get_personal_workspace(task_id)[
        "personalization_context"
    ]["applied"] is False

    other_first = _feedback(
        core,
        task_id,
        page,
        command_id="v5c1:feedback:other:first",
        proposed_value="after_answer",
        principal_id="other_operator",
    )
    other_second = _feedback(
        core,
        task_id,
        page,
        command_id="v5c1:feedback:other:second",
        proposed_value="after_answer",
        principal_id="other_operator",
    )
    with pytest.raises(ResearchValidationError, match="principal_id"):
        core.research_knowledge.create_personal_workspace_record(
            task_id,
            CreateWorkspaceRecordRequest(
                command_id="v5c1:candidate:principal-fence",
                record_kind="inferred_candidate",
                semantic_key=LIMITATIONS_POSITION_KEY,
                payload={"statement": "after_answer"},
                source_refs=_source_refs(task_id, other_first, other_second),
                reason="must fail current principal fence",
            ),
            principal_id="local_operator",
        )
    other_candidate = core.research_knowledge.create_personal_workspace_record(
        task_id,
        CreateWorkspaceRecordRequest(
            command_id="v5c1:candidate:other-principal",
            record_kind="inferred_candidate",
            semantic_key=LIMITATIONS_POSITION_KEY,
            payload={"statement": "after_answer"},
            source_refs=_source_refs(task_id, other_first, other_second),
            reason="new exact feedback boundary",
            reopen_reason="explicitly reopen from a different principal boundary",
        ),
        principal_id="other_operator",
    )
    with pytest.raises(ResearchValidationError, match="principal_id"):
        core.research_knowledge.decide_personal_workspace_record(
            task_id,
            other_candidate["record_id"],
            DecideWorkspaceRecordRequest(
                command_id="v5c1:candidate:confirm-wrong-principal",
                action="confirm",
                expected_version=other_candidate["version"],
                reason="must fail confirmation principal fence",
            ),
            principal_id="local_operator",
        )
    other_confirmed = core.research_knowledge.decide_personal_workspace_record(
        task_id,
        other_candidate["record_id"],
        DecideWorkspaceRecordRequest(
            command_id="v5c1:candidate:confirm-other-principal",
            action="confirm",
            expected_version=other_candidate["version"],
            reason="matching principal confirms",
        ),
        principal_id="other_operator",
    )
    assert other_confirmed["authority_class"] == "user_confirmed"


def test_stage1_existing_api_surface_strict_payload_and_ui_explanation(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, _, page = _vertical(core, "v5c-stage1-api-ui")
    client = TestClient(create_web_app(core))
    created = client.post(
        f"/api/research/product/tasks/{task_id}/workspace/records",
        json={
            "command_id": "v5c1:api:preference",
            "record_kind": "explicit_memory",
            "semantic_key": LIMITATIONS_POSITION_KEY,
            "payload": {
                "key": LIMITATIONS_POSITION_KEY,
                "value": "before_answer",
            },
            "source_refs": [],
            "reason": "explicit Stage 1 preference",
        },
    )
    assert created.status_code == 201
    enabled = client.get(f"/api/research/product/tasks/{task_id}/workspace")
    assert enabled.status_code == 200
    assert enabled.json()["workspace"]["personalization_context"]["applied"] is True
    disabled = client.get(
        f"/api/research/product/tasks/{task_id}/workspace",
        params={"personalization_enabled": "false"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["workspace"]["personalization_context"]["applied"] is False

    legacy = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/feedback",
        json={
            "command_id": "v5c1:api:legacy-feedback",
            "target_kind": "topic_page_revision",
            "target_id": page["page_revision_id"],
            "decision": "helpful",
            "reason_code": "answer_quality",
            "note": "legacy shape remains accepted",
            "expected_hash": page["content_hash"],
        },
    )
    assert legacy.status_code == 201
    assert "candidate_preference" not in legacy.json()["outcome"]
    invalid = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/feedback",
        json={
            "command_id": "v5c1:api:invalid-feedback",
            "target_kind": "topic_page_revision",
            "target_id": page["page_revision_id"],
            "decision": "helpful",
            "reason_code": "answer_quality",
            "note": "invalid preference",
            "expected_hash": page["content_hash"],
            "candidate_preference": {
                "semantic_key": LIMITATIONS_POSITION_KEY,
                "proposed_value": "sometimes_before",
            },
        },
    )
    assert invalid.status_code == 422

    html = client.get(f"/research/{task_id}").text
    script = client.get("/static/research.js").text
    helper = client.get("/static/research-personalization.js").text
    assert "data-personalization-enabled" in html
    assert "data-personalization-explanation" in html
    assert "research-personalization.js" in html
    assert "candidate_preference" in script
    assert "restore_previous_value" in script
    assert "applyAnswerPresentation" in helper
