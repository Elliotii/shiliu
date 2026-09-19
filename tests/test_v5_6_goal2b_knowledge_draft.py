from __future__ import annotations

from copy import deepcopy
import sqlite3

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.ask import AskService
from shiliu.domain import SubtitleSegment
from shiliu.knowledge_draft import (
    ConfirmDraftPromotionRequest,
    DraftCommandRequest,
    KnowledgeDraftError,
    SaveKnowledgeDraftRequest,
)
from shiliu.research.product_contracts import (
    CreateProductResearchRequest,
    RunProductResearchRequest,
)
from shiliu.web import create_web_app
from test_v4_fast_ask_api import _CompatibilityClaimVerifier, _Provider, _application
from test_v5_b_stage1_knowledge_workspace import (
    OBJECTIVE,
    _fixture_core,
    _terminal_task,
)


def _replace_fixture_source(core: Application) -> None:
    core.artifacts.save_raw_subtitle(
        "BV5101000001",
        [
            SubtitleSegment.model_validate(
                {
                    "from": 0,
                    "to": 4,
                    "content": "底层字幕已变化，旧 Research Evidence 不再 current。",
                }
            )
        ],
    )


def _research_draft(core: Application, task_id: str, suffix: str) -> dict[str, object]:
    return core.knowledge_drafts.save(
        SaveKnowledgeDraftRequest(
            source_kind="research_task",
            source_id=task_id,
            command_id=f"goal2b:research:save:{suffix}",
        )
    )


def test_fast_draft_materializes_real_research_and_confirms_long_term_knowledge(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    provider = _Provider()
    core._ask_service = AskService(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
        provider_factory=lambda _role: provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
        claim_verifier=_CompatibilityClaimVerifier(),
    )
    client = TestClient(create_web_app(core))
    answer = client.post(
        "/api/ask", json={"query": OBJECTIVE, "mode": "fast"}
    ).json()
    assert answer["status"] in {"complete", "partial"}

    saved_response = client.post(
        "/api/knowledge/drafts",
        json={
            "source_kind": "ask_run",
            "source_id": answer["run_id"],
            "command_id": "goal2b:draft:save",
        },
    )
    assert saved_response.status_code == 201, saved_response.text
    saved = saved_response.json()["draft"]
    assert saved["status"] == "saved"
    assert saved["authority"] == "draft_only_not_fact_or_citation"

    prepared_response = client.post(
        f"/api/knowledge/drafts/{saved['draft_id']}/prepare-promotion",
        json={"command_id": "goal2b:draft:prepare", "expected_version": 1},
    )
    assert prepared_response.status_code == 201, prepared_response.text
    prepared = prepared_response.json()["draft"]
    assert prepared["status"] == "promotion_ready"
    assert prepared["candidate_ids"]
    task_id = prepared["materialization_task_id"]
    raw = core.research.get_task(task_id)
    assert raw["attempts"] and raw["events"] and raw["checkpoints"]
    assert raw["evidence_uses"] and raw["provisional_artifacts"]
    workspace = core.research_knowledge.get_workspace(task_id)
    assert all(value["status"] == "pending_review" for value in workspace["candidates"])
    prepared_replay = client.post(
        f"/api/knowledge/drafts/{saved['draft_id']}/prepare-promotion",
        json={"command_id": "goal2b:draft:prepare", "expected_version": 1},
    ).json()["draft"]
    assert prepared_replay["draft_revision_id"] == prepared["draft_revision_id"]

    confirmed_response = client.post(
        f"/api/knowledge/drafts/{saved['draft_id']}/confirm-promotion",
        json={
            "command_id": "goal2b:draft:confirm",
            "expected_version": prepared["version"],
            "candidate_ids": prepared["candidate_ids"],
        },
    )
    assert confirmed_response.status_code == 201, confirmed_response.text
    confirmed = confirmed_response.json()["draft"]
    assert confirmed["status"] == "confirmed"
    assert confirmed["promotion_output"]["review_status"] == "published"
    published = core.research_knowledge.get_workspace(task_id)
    assert published["facts"] and published["artifacts"] and published["pages"]
    assert published["pages"][0]["review_status"] == "published"
    confirmed_replay = client.post(
        f"/api/knowledge/drafts/{saved['draft_id']}/confirm-promotion",
        json={
            "command_id": "goal2b:draft:confirm",
            "expected_version": prepared["version"],
            "candidate_ids": prepared["candidate_ids"],
        },
    ).json()["draft"]
    assert confirmed_replay["draft_revision_id"] == confirmed["draft_revision_id"]

    history = client.get(f"/api/knowledge/drafts/{saved['draft_id']}").json()
    assert [value["status"] for value in history["history"]] == [
        "saved",
        "materializing",
        "promotion_ready",
        "confirmed",
    ]


def test_draft_revisions_are_immutable_deduped_and_fail_closed(app_paths) -> None:
    core, _ = _application(app_paths, _Provider())
    client = TestClient(create_web_app(core))
    answer = client.post("/api/ask", json={"query": "MCP"}).json()
    payload = {
        "source_kind": "ask_run",
        "source_id": answer["run_id"],
        "command_id": "goal2b:dedupe",
    }
    first = client.post("/api/knowledge/drafts", json=payload).json()["draft"]
    replay = client.post("/api/knowledge/drafts", json=payload).json()["draft"]
    assert replay["draft_revision_id"] == first["draft_revision_id"]
    with core.db.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE knowledge_draft_revisions SET status='failed' WHERE draft_id=?",
                (first["draft_id"],),
            )

    insufficient_core, _ = _application(
        app_paths, _Provider(answer_modes=("partial",)), claim_verifier=None
    )
    insufficient_client = TestClient(create_web_app(insufficient_core))
    insufficient = insufficient_client.post("/api/ask", json={"query": "MCP"}).json()
    rejected = insufficient_client.post(
        "/api/knowledge/drafts",
        json={
            "source_kind": "ask_run",
            "source_id": insufficient["run_id"],
            "command_id": "goal2b:reject",
        },
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "draft_source_not_eligible"


def test_research_insufficient_without_evidence_cannot_be_saved(app_paths) -> None:
    core = Application(app_paths)
    created = core.research_product.create_task(
        CreateProductResearchRequest(
            command_id="goal2b:research:insufficient:create",
            objective="不存在于本地证据中的问题",
            success_constraints=[],
            run_immediately=False,
        )
    )
    task_id = str(created["task_id"])
    outcome = core.research_product.run_to_boundary(
        task_id,
        RunProductResearchRequest(command_id="goal2b:research:insufficient:run"),
    )
    assert outcome["task_status"] == "terminal"
    raw = core.research.get_task(task_id)
    assert raw["provisional_artifacts"][-1]["answer_status"] == "valid_insufficient"
    assert raw["evidence_uses"] == []

    with pytest.raises(KnowledgeDraftError) as raised:
        _research_draft(core, task_id, "insufficient")
    assert raised.value.code == "draft_source_not_eligible"
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM knowledge_draft_revisions"
        ).fetchone()[0] == 0


def test_valid_research_draft_binds_exact_server_lineage_and_replay_fails_closed(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    task_id = _terminal_task(core, "goal2b-draft-lineage")
    raw = core.research.get_task(task_id)
    result_id = str(raw["task"]["terminal_result_id"])
    artifact = raw["provisional_artifacts"][-1]
    saved = _research_draft(core, task_id, "lineage")

    assert saved["status"] == "saved"
    assert saved["authority"] == "draft_only_not_fact_or_citation"
    assert saved["source_answer_snapshot"]["result"]["result_id"] == result_id
    assert (
        saved["source_answer_snapshot"]["artifact"]["artifact_id"]
        == artifact["artifact_id"]
    )
    assert {
        value["evidence_use_id"] for value in saved["evidence_refs"]
    } == set(artifact["evidence_use_ids"])
    assert all(value["validation_observation_id"] for value in saved["evidence_refs"])

    replay = _research_draft(core, task_id, "lineage")
    assert replay["draft_revision_id"] == saved["draft_revision_id"]
    with pytest.raises(KnowledgeDraftError) as raised:
        core.knowledge_drafts.save(
            SaveKnowledgeDraftRequest(
                source_kind="research_task",
                source_id=task_id,
                expected_source_hash="sha256:" + "0" * 64,
                command_id="goal2b:research:save:lineage",
            )
        )
    assert raised.value.code == "draft_source_hash_mismatch"


@pytest.mark.parametrize(
    "invalid_kind",
    [
        "failed",
        "interrupted",
        "external_unknown",
        "side_effect_unknown",
        "empty",
        "unbound",
    ],
)
def test_failed_interrupted_unknown_empty_or_unbound_research_cannot_be_saved(
    app_paths, monkeypatch, invalid_kind: str
) -> None:
    core = _fixture_core(app_paths)
    task_id = _terminal_task(core, f"goal2b-draft-invalid-{invalid_kind}")
    raw = deepcopy(core.research.get_task(task_id))
    result = next(
        value
        for value in raw["results"]
        if value["result_id"] == raw["task"]["terminal_result_id"]
    )
    artifact = raw["provisional_artifacts"][-1]
    if invalid_kind == "failed":
        result["failure_class"] = "provider_failure"
    elif invalid_kind == "interrupted":
        raw["task"]["status"] = "blocked"
    elif invalid_kind == "external_unknown":
        result["termination_reason"] = "external_side_effect_unknown"
    elif invalid_kind == "side_effect_unknown":
        raw["side_effects"].append({"status": "unknown"})
    elif invalid_kind == "empty":
        artifact["answer_blocks"] = []
    else:
        artifact["evidence_use_ids"] = ["evidence_use_unbound"]
    monkeypatch.setattr(core.research_product.kernel, "get_task", lambda _task_id: raw)

    with pytest.raises(KnowledgeDraftError) as raised:
        _research_draft(core, task_id, invalid_kind)
    assert raised.value.code == "draft_source_not_eligible"
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM knowledge_draft_revisions"
        ).fetchone()[0] == 0


def test_research_source_drift_blocks_prepare_before_materialization(app_paths) -> None:
    core = _fixture_core(app_paths)
    task_id = _terminal_task(core, "goal2b-draft-prepare-drift")
    saved = _research_draft(core, task_id, "prepare-drift")
    with core.db.connect() as connection:
        task_count = connection.execute("SELECT COUNT(*) FROM research_tasks").fetchone()[0]
        candidate_count = connection.execute(
            "SELECT COUNT(*) FROM research_knowledge_candidates"
        ).fetchone()[0]
    _replace_fixture_source(core)

    with pytest.raises(KnowledgeDraftError) as raised:
        core.knowledge_drafts.prepare_promotion(
            str(saved["draft_id"]),
            DraftCommandRequest(
                command_id="goal2b:research:prepare:drift",
                expected_version=int(saved["version"]),
            ),
        )
    assert raised.value.code == "draft_source_evidence_changed"
    history = core.knowledge_drafts.get(str(saved["draft_id"]))["history"]
    assert [value["status"] for value in history] == ["saved", "needs_revalidation"]
    assert history[-1]["revalidation_state"] == "needs_revalidation"
    with core.db.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM research_tasks").fetchone()[0]
            == task_count
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM research_knowledge_candidates"
        ).fetchone()[0] == candidate_count


def test_research_source_drift_blocks_confirm_before_publication(app_paths) -> None:
    core = _fixture_core(app_paths)
    task_id = _terminal_task(core, "goal2b-draft-confirm-drift")
    saved = _research_draft(core, task_id, "confirm-drift")
    prepared = core.knowledge_drafts.prepare_promotion(
        str(saved["draft_id"]),
        DraftCommandRequest(
            command_id="goal2b:research:prepare:confirm-drift",
            expected_version=int(saved["version"]),
        ),
    )
    assert prepared["status"] == "promotion_ready"
    materialization_task_id = str(prepared["materialization_task_id"])
    workspace = core.research_knowledge.get_workspace(materialization_task_id)
    assert workspace["candidates"]
    assert workspace["facts"] == []
    assert workspace["artifacts"] == []
    assert workspace["pages"] == []
    _replace_fixture_source(core)

    with pytest.raises(KnowledgeDraftError) as raised:
        core.knowledge_drafts.confirm_promotion(
            str(saved["draft_id"]),
            ConfirmDraftPromotionRequest(
                command_id="goal2b:research:confirm:drift",
                expected_version=int(prepared["version"]),
                candidate_ids=list(prepared["candidate_ids"]),
            ),
            principal_id="local_operator",
        )
    assert raised.value.code == "draft_source_evidence_changed"
    history = core.knowledge_drafts.get(str(saved["draft_id"]))["history"]
    assert history[-1]["status"] == "needs_revalidation"
    final = core.research_knowledge.get_workspace(materialization_task_id)
    assert final["facts"] == []
    assert final["artifacts"] == []
    assert final["pages"] == []


def test_unchanged_valid_research_draft_promotes_only_after_confirmation(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    task_id = _terminal_task(core, "goal2b-draft-valid-promotion")
    saved = _research_draft(core, task_id, "valid-promotion")
    prepared_request = DraftCommandRequest(
        command_id="goal2b:research:prepare:valid",
        expected_version=int(saved["version"]),
    )
    prepared = core.knowledge_drafts.prepare_promotion(
        str(saved["draft_id"]), prepared_request
    )
    assert prepared["status"] == "promotion_ready"
    replay = core.knowledge_drafts.prepare_promotion(
        str(saved["draft_id"]), prepared_request
    )
    assert replay["draft_revision_id"] == prepared["draft_revision_id"]
    with pytest.raises(KnowledgeDraftError) as raised:
        core.knowledge_drafts.prepare_promotion(
            str(saved["draft_id"]),
            DraftCommandRequest(
                command_id=prepared_request.command_id,
                expected_version=int(saved["version"]) + 1,
            ),
        )
    assert raised.value.code == "draft_command_payload_mismatch"

    confirm_request = ConfirmDraftPromotionRequest(
        command_id="goal2b:research:confirm:valid",
        expected_version=int(prepared["version"]),
        candidate_ids=list(prepared["candidate_ids"]),
    )
    confirmed = core.knowledge_drafts.confirm_promotion(
        str(saved["draft_id"]),
        confirm_request,
        principal_id="local_operator",
    )
    assert confirmed["status"] == "confirmed"
    published = core.research_knowledge.get_workspace(
        str(prepared["materialization_task_id"])
    )
    assert published["facts"]
    assert published["artifacts"]
    assert published["pages"]
    confirmed_replay = core.knowledge_drafts.confirm_promotion(
        str(saved["draft_id"]),
        confirm_request,
        principal_id="local_operator",
    )
    assert confirmed_replay["draft_revision_id"] == confirmed["draft_revision_id"]
