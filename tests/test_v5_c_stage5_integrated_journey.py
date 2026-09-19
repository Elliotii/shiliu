from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shiliu.db import SCHEMA_VERSION
from shiliu.research.integrated_journey import INTEGRATED_JOURNEY_POLICY_VERSION
from shiliu.research.knowledge_contracts import (
    SubmitKnowledgeFeedbackRequest,
    WorkspaceSourceRef,
)
from shiliu.research.errors import ResearchValidationError
from shiliu.research.personalization import (
    DETAIL_LEVEL_KEY,
    LIMITATIONS_POSITION_KEY,
    PERSONALIZATION_CONTEXT_POLICY_VERSION,
    PersonalizationContextProjection,
)
from shiliu.web import create_web_app
from test_v5_b_stage3_artifact_reuse import _core, _vertical
from test_v5_b_stage4_personal_workspace import _create, _decide
from test_v5_c_stage1_personalized_answer_presentation import _product_authority


def _database_counts(core) -> dict[str, int]:
    with core.db.connect() as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "research_workspace_records",
                "research_events",
                "research_command_receipts",
                "research_tasks",
                "asr_jobs",
            )
        }


def _record(
    *,
    semantic_key: str,
    value: str,
    record_id: str,
    principal_id: str = "local_operator",
) -> dict:
    return {
        "semantic_key": semantic_key,
        "effective_status": "current",
        "record_kind": "explicit_memory",
        "authority_class": "user_authored",
        "record_id": record_id,
        "record_revision_id": f"{record_id}-v1",
        "version": 1,
        "content_hash": record_id[0] * 64,
        "created_at": f"2026-08-10T00:00:0{len(record_id)}+00:00",
        "principal_id": principal_id,
        "payload": {"key": semantic_key, "value": value},
    }


def test_stage5_answer_keys_are_independent_and_current_principal_scoped() -> None:
    projection = PersonalizationContextProjection()
    limitations = _record(
        semantic_key=LIMITATIONS_POSITION_KEY,
        value="before_answer",
        record_id="a",
    )
    limitations_conflict = {
        **_record(
            semantic_key=LIMITATIONS_POSITION_KEY,
            value="after_answer",
            record_id="b",
        ),
        "record_kind": "inferred_candidate",
        "authority_class": "user_confirmed",
        "effective_status": "confirmed",
        "payload": {"statement": "after_answer"},
    }
    compact = _record(
        semantic_key=DETAIL_LEVEL_KEY,
        value="compact",
        record_id="c",
    )
    other_principal = _record(
        semantic_key=DETAIL_LEVEL_KEY,
        value="standard",
        record_id="d",
        principal_id="other_operator",
    )

    first = projection.project(
        [limitations, limitations_conflict, compact, other_principal],
        principal_id="local_operator",
    )
    second = projection.project(
        [limitations, limitations_conflict, compact, other_principal],
        principal_id="local_operator",
    )
    assert first == second
    assert first["policy_version"] == PERSONALIZATION_CONTEXT_POLICY_VERSION
    assert first["applied"] is False
    assert first["preference"] is None
    assert "confirmed_preference_conflict_fail_closed" in first["reason_codes"]
    assert first["detail_applied"] is True
    assert first["detail_level"] == "compact"
    assert first["detail_preference"]["record_id"] == "c"

    wrong_principal = projection.project(
        [compact], principal_id="other_operator"
    )
    assert wrong_principal["detail_applied"] is False
    assert wrong_principal["detail_level"] == "standard"


def test_stage5_paired_journey_compact_off_rollback_restart_and_noninterference(
    app_paths,
) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "v5c-stage5-journey")
    assert SCHEMA_VERSION == 17
    product_full_before = core.research_product.get_task(task_id)
    product_before = _product_authority(product_full_before)
    counts_before = _database_counts(core)

    baseline = core.research_knowledge.get_personal_workspace(
        task_id,
        principal_id="local_operator",
        routing_enabled=True,
        assistance_enabled=True,
        journey_enabled=True,
    )
    assert baseline["personalization_context"]["detail_level"] == "standard"
    journey = baseline["integrated_journey"]
    assert journey["policy_version"] == INTEGRATED_JOURNEY_POLICY_VERSION
    assert journey["steps"]["answer"]["status"] == "baseline"
    assert journey["steps"]["search"]["status"] == "explicit_query_required"
    assert journey["steps"]["search"]["href"].endswith(
        f"corpus_task_id={task_id}&corpus_aware=true"
    )
    assert set(journey["side_effects"].values()) == {0}
    assert _database_counts(core) == counts_before

    _create(
        core,
        task_id,
        command_id="v5c5:unrelated",
        record_kind="explicit_memory",
        semantic_key="answer.presentation.color",
        payload={"key": "answer.presentation.color", "value": "green"},
    )
    unrelated = core.research_knowledge.get_personal_workspace(
        task_id,
        principal_id="local_operator",
        journey_enabled=True,
    )
    assert unrelated["personalization_context"]["detail_level"] == "standard"

    compact = _create(
        core,
        task_id,
        command_id="v5c5:compact",
        record_kind="explicit_memory",
        semantic_key=DETAIL_LEVEL_KEY,
        payload={"key": DETAIL_LEVEL_KEY, "value": "compact"},
    )
    treatment = core.research_knowledge.get_personal_workspace(
        task_id,
        principal_id="local_operator",
        routing_enabled=True,
        assistance_enabled=True,
        journey_enabled=True,
    )
    context = treatment["personalization_context"]
    assert context["detail_applied"] is True
    assert context["detail_level"] == "compact"
    assert context["detail_preference"]["record_revision_id"] == compact[
        "record_revision_id"
    ]
    assert treatment["integrated_journey"]["steps"]["answer"]["status"] == "treatment"
    applied = next(
        record for record in treatment["records"] if record["record_id"] == compact["record_id"]
    )
    assert applied["product_behavior_effect"] is True

    durable_counts = _database_counts(core)
    disabled = core.research_knowledge.get_personal_workspace(
        task_id,
        principal_id="local_operator",
        personalization_enabled=False,
        routing_enabled=False,
        current_explicit_path="fast",
        allow_provider_answer=True,
        allow_high_cost_or_durable=True,
        assistance_enabled=False,
        journey_enabled=False,
    )
    assert disabled["personalization_context"]["detail_level"] == "standard"
    assert disabled["integrated_journey"]["steps"]["answer"]["status"] == "disabled"
    assert disabled["integrated_journey"]["steps"]["routing"]["status"] == "disabled"
    assert disabled["integrated_journey"]["steps"]["assistance"]["status"] == "disabled"
    assert "corpus_aware=false" in disabled["integrated_journey"]["steps"]["search"]["href"]
    assert disabled["route_recommendation"]["settings"]["current_explicit_path"] == "fast"
    assert _database_counts(core) == durable_counts

    rolled_back = _decide(
        core,
        task_id,
        compact,
        command_id="v5c5:compact-to-standard",
        action="correct",
        replacement_payload={"key": DETAIL_LEVEL_KEY, "value": "standard"},
    )
    rollback_context = core.research_knowledge.get_personal_workspace(
        task_id,
        principal_id="local_operator",
        journey_enabled=True,
    )["personalization_context"]
    assert rolled_back["version"] == 2
    assert rollback_context["detail_level"] == "standard"
    assert rollback_context["detail_preference"]["record_revision_id"] == rolled_back[
        "record_revision_id"
    ]

    restarted = _core(app_paths).research_knowledge.get_personal_workspace(
        task_id,
        principal_id="local_operator",
        journey_enabled=True,
    )
    assert restarted["personalization_context"]["context_hash"] == rollback_context[
        "context_hash"
    ]
    product_after = core.research_product.get_task(task_id)
    assert {
        key: value for key, value in product_after.items() if key != "trace"
    } == {
        key: value for key, value in product_full_before.items() if key != "trace"
    }
    assert _product_authority(product_after) == product_before


def test_stage5_existing_api_and_ui_are_additive_and_inert(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, _, _ = _vertical(core, "v5c-stage5-api-ui")
    client = TestClient(create_web_app(core))
    created = client.post(
        f"/api/research/product/tasks/{task_id}/workspace/records",
        json={
            "command_id": "v5c5:api:compact",
            "record_kind": "explicit_memory",
            "semantic_key": DETAIL_LEVEL_KEY,
            "payload": {"key": DETAIL_LEVEL_KEY, "value": "compact"},
            "source_refs": [],
            "reason": "explicit Stage 5 detail preference",
        },
    )
    assert created.status_code == 201
    response = client.get(
        f"/api/research/product/tasks/{task_id}/workspace",
        params={"journey_enabled": "true"},
    )
    assert response.status_code == 200
    workspace = response.json()["workspace"]
    assert workspace["personalization_context"]["detail_level"] == "compact"
    assert workspace["integrated_journey"]["authority"]["search_completed"] is False
    assert workspace["integrated_journey"]["authority"]["execution"] is False

    invalid_pair = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/feedback",
        json={
            "command_id": "v5c5:api:invalid-pair",
            "target_kind": "topic_page_revision",
            "target_id": "irrelevant-because-contract-rejects-first",
            "decision": "helpful",
            "reason_code": "answer_quality",
            "note": "invalid exact pair",
            "expected_hash": "0" * 64,
            "candidate_preference": {
                "semantic_key": DETAIL_LEVEL_KEY,
                "proposed_value": "before_answer",
            },
        },
    )
    assert invalid_pair.status_code == 422

    html = client.get(f"/research/{task_id}").text
    helper = client.get("/static/research-personalization.js").text
    script = client.get("/static/research.js").text
    assert "data-integrated-journey" in html
    assert "data-answer-compact-details" in html
    assert "data-answer-compact-blocks" in html
    assert "data-journey-enabled" in html
    assert "applyAnswerDetail" in helper
    assert "journey_enabled" in script
    assert "context.steps" in script


def test_stage5_detail_feedback_stays_candidate_until_matching_principal_confirms(
    app_paths,
) -> None:
    core = _core(app_paths)
    task_id, _, _, page = _vertical(core, "v5c-stage5-detail-feedback")

    def feedback(command_id: str, principal_id: str) -> dict:
        return core.research_knowledge.submit_feedback(
            task_id,
            SubmitKnowledgeFeedbackRequest(
                command_id=command_id,
                target_kind="topic_page_revision",
                target_id=page["page_revision_id"],
                decision="helpful",
                reason_code="answer_quality",
                note="exact Stage 5 detail hint",
                expected_hash=page["content_hash"],
                candidate_preference={
                    "semantic_key": DETAIL_LEVEL_KEY,
                    "proposed_value": "compact",
                },
            ),
            principal_id=principal_id,
        )

    first = feedback("v5c5:feedback:first", "local_operator")
    second = feedback("v5c5:feedback:second", "local_operator")
    refs = [
        WorkspaceSourceRef(
            ref_type="research_event",
            ref_id=value["event_id"],
            task_id=task_id,
        )
        for value in (first, second)
    ]
    candidate = _create(
        core,
        task_id,
        command_id="v5c5:detail:candidate",
        record_kind="inferred_candidate",
        semantic_key=DETAIL_LEVEL_KEY,
        payload={"statement": "compact"},
        source_refs=refs,
    )
    context = core.research_knowledge.get_personal_workspace(
        task_id, principal_id="local_operator"
    )["personalization_context"]
    assert context["detail_applied"] is False
    assert "candidate_not_confirmed" in context["detail_reason_codes"]

    confirmed = _decide(
        core,
        task_id,
        candidate,
        command_id="v5c5:detail:confirm",
        action="confirm",
    )
    confirmed_context = core.research_knowledge.get_personal_workspace(
        task_id, principal_id="local_operator"
    )["personalization_context"]
    assert confirmed_context["detail_applied"] is True
    assert confirmed_context["detail_preference"]["record_revision_id"] == confirmed[
        "record_revision_id"
    ]

    other_first = feedback("v5c5:feedback:other:first", "other_operator")
    other_second = feedback("v5c5:feedback:other:second", "other_operator")
    other_refs = [
        WorkspaceSourceRef(
            ref_type="research_event",
            ref_id=value["event_id"],
            task_id=task_id,
        )
        for value in (other_first, other_second)
    ]
    with pytest.raises(ResearchValidationError, match="principal_id"):
        _create(
            core,
            task_id,
            command_id="v5c5:detail:wrong-principal",
            record_kind="inferred_candidate",
            semantic_key=DETAIL_LEVEL_KEY,
            payload={"statement": "compact"},
            source_refs=other_refs,
            reopen_reason="new other-principal evidence boundary",
        )
