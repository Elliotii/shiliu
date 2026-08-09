from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json

from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.ask.contracts import AskRequest
from shiliu.domain import FavoriteItem
from shiliu.research.knowledge_contracts import (
    AssessArtifactRouteRequest,
    WorkspaceSourceRef,
)
from shiliu.research.personalization import LIMITATIONS_POSITION_KEY
from shiliu.research.product_contracts import CreateProductResearchRequest
from shiliu.retrieval.corpus_search import CORPUS_SEARCH_POLICY_VERSION
from shiliu.retrieval.product_search import ProductSearchRequest
from shiliu.web import create_web_app
from test_product_search_api import chunk
from test_search_orchestration import FakeRetriever, orchestrator
from test_v5_b_stage3_artifact_reuse import OBJECTIVE, _core, _vertical
from test_v5_b_stage4_personal_workspace import (
    _create,
    _decide,
    _stable_ask,
    _stable_research,
    _stable_route,
    _stable_search,
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _schema_identity(core: Application) -> list[tuple[str, str, str]]:
    with core.db.connect() as connection:
        return [
            (str(row[0]), str(row[1]), str(row[2] or ""))
            for row in connection.execute(
                "SELECT type, name, sql FROM sqlite_master "
                "WHERE type IN ('table','index','trigger') ORDER BY type, name"
            ).fetchall()
        ]


def _stage2_fixture(app_paths, suffix: str):
    core = Application(app_paths)
    source_id = core.db.create_favorite_source(
        folder_id=6200, folder_title="Stage 2 Corpus Fixture"
    )
    values = [
        ("Open systems counterexample", "Open UP"),
        ("General retrieval baseline", "General UP"),
        ("Independent evidence lane", "Evidence UP"),
        ("MCP server tools guide", "MCP Studio"),
        ("MCP protocol practice", "MCP Studio"),
        ("Other candidate", "Other UP"),
    ]
    items = [
        FavoriteItem(
            bvid=f"BV6200{index:06d}",
            title=title,
            uploader=uploader,
            favorite_time=100 - index,
        )
        for index, (title, uploader) in enumerate(values, 1)
    ]
    core.db.record_source_snapshot(source_id, items, processing_profile="formal")
    video_ids = []
    results = []
    for rank, item in enumerate(items, 1):
        video = core.db.get_video_by_source(item.bvid)
        assert video is not None
        video_id = int(video["id"])
        video_ids.append(video_id)
        core.db.update_video(video_id, description=f"{item.title} current description")
        results.append(
            replace(
                chunk(
                    f"stage2:{rank}",
                    video_id,
                    rank * 10,
                    rank * 10 + 5,
                    score=10.0 - rank,
                ),
                title=item.title,
                uploader=item.uploader,
                source_id=item.bvid,
            )
        )
    snapshot = core.taxonomy_corpus.freeze([source_id])
    raw_search, lexical, _, _ = orchestrator(
        app_paths, lexical=FakeRetriever(results)
    )
    core._search_orchestrator = raw_search
    core._product_search = None
    _ = core.product_search
    task = core.research_product.create_task(
        CreateProductResearchRequest(
            command_id=f"v5c2:create:{suffix}",
            objective=f"MCP corpus-aware search {suffix}",
            success_constraints=[],
            run_immediately=False,
        )
    )
    return core, str(task["task_id"]), snapshot, video_ids, lexical


def _corpus_prior(core: Application, task_id: str, snapshot, *, suffix: str, **payload):
    return _create(
        core,
        task_id,
        command_id=f"v5c2:corpus:{suffix}",
        record_kind="corpus_observation",
        semantic_key=payload.pop("semantic_key", "MCP corpus topic"),
        payload={"observation_type": "topic", "value": "MCP", **payload},
        source_refs=[
            WorkspaceSourceRef(
                ref_type="taxonomy_snapshot", ref_id=str(snapshot.snapshot_id)
            )
        ],
    )


def _request(task_id: str | None = None, *, enabled: bool = True, query: str = "MCP"):
    return ProductSearchRequest(
        query=query,
        mode="lexical",
        result_limit=4,
        max_windows_per_video=1,
        corpus_task_id=task_id,
        corpus_aware=enabled,
    )


def _stable_raw(value) -> dict:
    return {
        "plan": value.plan.as_dict(),
        "executed_mode": value.executed_mode,
        "fallback": value.fallback,
        "fallback_reason": value.fallback_reason,
        "index_identity": value.index_identity,
        "raw_hits": [item.as_dict() for item in value.raw_hits],
        "candidate_counts": value.candidate_counts,
    }


def test_stage2_empty_treatment_disabled_unrelated_and_counterexample_matrix(
    app_paths,
) -> None:
    core, task_id, snapshot, video_ids, lexical = _stage2_fixture(
        app_paths, "paired"
    )
    schema_before = _schema_identity(core)
    baseline_raw, baseline = core.product_search.search_with_raw(
        _request(), principal_id="local_operator"
    )
    _create(
        core,
        task_id,
        command_id="v5c2:wrong-kind",
        record_kind="explicit_memory",
        semantic_key="MCP corpus topic",
        payload={"key": "MCP corpus topic", "value": "MCP"},
    )
    no_prior_raw, no_prior = core.product_search.search_with_raw(
        _request(task_id), principal_id="local_operator"
    )
    assert _stable_raw(no_prior_raw) == _stable_raw(baseline_raw)
    assert [value.video_id for value in no_prior.results] == video_ids[:4]
    assert no_prior.corpus_context["status"] == "baseline"
    assert no_prior.corpus_context["reason_codes"] == ["no_current_corpus_prior"]

    _corpus_prior(core, task_id, snapshot, suffix="paired")
    with core.db.connect() as connection:
        workspace_count = connection.execute(
            "SELECT COUNT(*) FROM research_workspace_records"
        ).fetchone()[0]
    treatment_raw, treatment = core.product_search.search_with_raw(
        _request(task_id), principal_id="local_operator"
    )
    assert _stable_raw(treatment_raw) == _stable_raw(baseline_raw)
    assert lexical.calls[-1][0] == lexical.calls[0][0] == "MCP"
    assert [value.video_id for value in treatment.results] == [
        video_ids[0],
        video_ids[3],
        video_ids[1],
        video_ids[4],
    ]
    assert treatment.corpus_context["policy_version"] == CORPUS_SEARCH_POLICY_VERSION
    assert treatment.corpus_context["status"] == "applied"
    assert treatment.corpus_context["applied"] is True
    assert treatment.corpus_context["open_lane"] == {
        "independent": True,
        "baseline_candidate_pool_unchanged": True,
        "reserved_slots_min": 2,
    }
    assert [value["lane"] for value in treatment.result_contributions] == [
        "open_counterexample",
        "corpus_soft_prior",
        "open_baseline",
        "corpus_soft_prior",
    ]
    assert treatment.corpus_context["counterexample"] == {
        "required_when_available": True,
        "video_id": video_ids[0],
        "preserved": True,
    }
    assert all(
        value[key] is False
        for value in treatment.result_contributions
        for key in (
            "citation_authority",
            "verifier_authority",
            "fact_authority",
            "hard_filter",
            "route_authority",
        )
    )
    first_context_hash = treatment.corpus_context["context_hash"]
    first_result_hash = treatment.corpus_context["result_hash"]
    core._product_search = None
    restarted = core.product_search.search(
        _request(task_id), principal_id="local_operator"
    )
    assert [value.video_id for value in restarted.results] == [
        video_ids[0],
        video_ids[3],
        video_ids[1],
        video_ids[4],
    ]
    assert restarted.corpus_context["context_hash"] == first_context_hash
    assert restarted.corpus_context["result_hash"] == first_result_hash
    assert len({value.video_id for value in restarted.results}) == 4

    filtered_baseline_raw, _ = core.product_search.search_with_raw(
        ProductSearchRequest(
            query="MCP",
            mode="lexical",
            result_limit=4,
            max_windows_per_video=1,
            filters={"uploader_contains": "MCP Studio"},
        ),
        principal_id="local_operator",
    )
    filtered_treatment_raw, _ = core.product_search.search_with_raw(
        ProductSearchRequest(
            query="MCP",
            mode="lexical",
            result_limit=4,
            max_windows_per_video=1,
            corpus_task_id=task_id,
            filters={"uploader_contains": "MCP Studio"},
        ),
        principal_id="local_operator",
    )
    assert _stable_raw(filtered_treatment_raw) == _stable_raw(filtered_baseline_raw)
    assert lexical.calls[-2][1]["filters"].uploader_contains == "MCP Studio"
    assert lexical.calls[-1][1]["filters"].uploader_contains == "MCP Studio"

    disabled_raw, disabled = core.product_search.search_with_raw(
        _request(task_id, enabled=False), principal_id="local_operator"
    )
    unrelated_raw, unrelated = core.product_search.search_with_raw(
        _request(task_id, query="unrelated baseline query"),
        principal_id="local_operator",
    )
    assert _stable_raw(disabled_raw) == _stable_raw(baseline_raw)
    assert [value.video_id for value in disabled.results] == video_ids[:4]
    assert disabled.corpus_context["status"] == "disabled"
    assert [value.video_id for value in unrelated.results] == video_ids[:4]
    assert unrelated.corpus_context["reason_codes"] == ["unrelated_corpus_prior"]
    assert unrelated_raw.plan.requested_mode == "lexical"
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_workspace_records"
        ).fetchone()[0] == workspace_count
    assert _schema_identity(core) == schema_before


def test_stage2_terminal_correction_malformed_conflict_and_snapshot_drift_fail_closed(
    app_paths,
) -> None:
    core, task_id, snapshot, video_ids, _ = _stage2_fixture(app_paths, "failclosed")
    record = _corpus_prior(core, task_id, snapshot, suffix="valid")
    invalidated = _decide(
        core,
        task_id,
        record,
        command_id="v5c2:invalidate",
        action="invalidate",
    )
    terminal = core.product_search.search(
        _request(task_id), principal_id="local_operator"
    )
    assert [value.video_id for value in terminal.results] == video_ids[:4]
    assert terminal.corpus_context["reason_codes"] == [
        "terminal_corpus_prior_not_applied"
    ]
    corrected = _decide(
        core,
        task_id,
        invalidated,
        command_id="v5c2:correct",
        action="correct",
        replacement_payload={"observation_type": "topic", "value": "MCP"},
    )
    assert corrected["version"] == 3
    assert core.product_search.search(
        _request(task_id), principal_id="local_operator"
    ).corpus_context["applied"] is True
    assert core.product_search.search(
        _request(task_id), principal_id="other_operator"
    ).corpus_context["status"] == "fail_closed"
    tombstoned = _decide(
        core,
        task_id,
        corrected,
        command_id="v5c2:tombstone",
        action="tombstone",
    )
    terminal_again = core.product_search.search(
        _request(task_id), principal_id="local_operator"
    )
    assert [value.video_id for value in terminal_again.results] == video_ids[:4]
    restored = _decide(
        core,
        task_id,
        tombstoned,
        command_id="v5c2:restore-as-new",
        action="correct",
        replacement_payload={"observation_type": "topic", "value": "MCP"},
    )
    assert restored["version"] == 5
    assert core.product_search.search(
        _request(task_id), principal_id="local_operator"
    ).corpus_context["applied"] is True

    malformed_task = core.research_product.create_task(
        CreateProductResearchRequest(
            command_id="v5c2:create:malformed",
            objective="MCP malformed corpus prior",
            success_constraints=[],
            run_immediately=False,
        )
    )["task_id"]
    _corpus_prior(
        core,
        str(malformed_task),
        snapshot,
        suffix="malformed",
        semantic_key="MCP malformed corpus topic",
        unexpected="not part of the exact payload",
    )
    malformed = core.product_search.search(
        _request(str(malformed_task)), principal_id="local_operator"
    )
    assert malformed.corpus_context["status"] == "fail_closed"
    assert malformed.corpus_context["reason_codes"] == [
        "malformed_or_drifted_corpus_prior"
    ]

    with core.db.connect() as connection:
        latest = dict(
            connection.execute(
                "SELECT * FROM research_workspace_records WHERE record_id=? "
                "ORDER BY version DESC LIMIT 1",
                (record["record_id"],),
            ).fetchone()
        )
        payload = {"observation_type": "topic", "value": "MCP alternate"}
        source_refs = json.loads(latest["source_refs_json"])
        content_hash = _hash(
            {
                "record_kind": "corpus_observation",
                "authority_class": "corpus_soft_prior",
                "status": "current",
                "semantic_key": latest["semantic_key"],
                "payload": payload,
                "source_refs": source_refs,
                "confidence": latest["confidence"],
                "expires_at": latest["expires_at"],
                "policy_version": latest["policy_version"],
            }
        )
        connection.execute(
            """
            INSERT INTO research_workspace_records(
                record_revision_id, record_id, version, parent_revision_id,
                command_task_id, record_kind, authority_class, status,
                semantic_key, payload_json, source_refs_json, source_boundary_hash,
                confidence, expires_at, decision_action, reason, principal_id,
                policy_version, content_hash, command_id, command_payload_hash,
                created_at
            ) VALUES(?, ?, 1, NULL, ?, 'corpus_observation', 'corpus_soft_prior',
                     'current', ?, ?, ?, ?, ?, ?, 'create', 'conflict fixture',
                     'local_operator', ?, ?, ?, ?, ?)
            """,
            (
                "v5c2-conflict-revision",
                "v5c2-conflict-record",
                task_id,
                latest["semantic_key"],
                _canonical_json(payload),
                latest["source_refs_json"],
                latest["source_boundary_hash"],
                latest["confidence"],
                latest["expires_at"],
                latest["policy_version"],
                content_hash,
                "v5c2:conflict:insert",
                "c" * 64,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    conflict = core.product_search.search(
        _request(task_id), principal_id="local_operator"
    )
    assert conflict.corpus_context["status"] == "fail_closed"
    assert conflict.corpus_context["reason_codes"] == ["conflicting_corpus_prior"]

    drift_state = app_paths.state_dir / "drift"
    drift_content = app_paths.content_dir / "drift"
    drift_paths = replace(
        app_paths,
        state_dir=drift_state,
        content_dir=drift_content,
        database=drift_state / "shiliu.db",
        config=drift_state / "config.toml",
        logs_dir=drift_state / "logs",
        videos_dir=drift_content / "videos",
        sync_lock=drift_state / "sync.lock",
    )
    drift_core, drift_task, drift_snapshot, drift_ids, _ = _stage2_fixture(
        drift_paths, "drift"
    )
    _corpus_prior(drift_core, drift_task, drift_snapshot, suffix="drift")
    with drift_core.db.connect() as connection:
        connection.execute(
            "UPDATE taxonomy_corpus_snapshots SET snapshot_hash=? WHERE id=?",
            ("f" * 64, drift_snapshot.snapshot_id),
        )
    drifted = drift_core.product_search.search(
        _request(drift_task), principal_id="local_operator"
    )
    assert [value.video_id for value in drifted.results] == drift_ids[:4]
    assert drifted.corpus_context["status"] == "fail_closed"
    assert drifted.corpus_context["reason_codes"] == [
        "malformed_or_drifted_corpus_prior"
    ]
    with drift_core.db.connect() as connection:
        connection.execute(
            "UPDATE taxonomy_corpus_snapshots SET snapshot_hash=? WHERE id=?",
            (drift_snapshot.snapshot_hash, drift_snapshot.snapshot_id),
        )
    assert drift_core.product_search.search(
        _request(drift_task), principal_id="local_operator"
    ).corpus_context["applied"] is True
    with drift_core.db.connect() as connection:
        connection.execute(
            "UPDATE taxonomy_corpus_snapshots SET frozen_at=? WHERE id=?",
            ("drifted-after-workspace-bind", drift_snapshot.snapshot_id),
        )
    boundary_drift = drift_core.product_search.search(
        _request(drift_task), principal_id="local_operator"
    )
    assert [value.video_id for value in boundary_drift.results] == drift_ids[:4]
    assert boundary_drift.corpus_context["status"] == "fail_closed"


def test_stage2_api_ui_legacy_shape_and_explanation(app_paths) -> None:
    core, task_id, snapshot, video_ids, _ = _stage2_fixture(app_paths, "api")
    _corpus_prior(core, task_id, snapshot, suffix="api")
    client = TestClient(create_web_app(core))
    response = client.post(
        "/api/search",
        json={
            "query": "MCP",
            "mode": "lexical",
            "result_limit": 4,
            "max_windows_per_video": 1,
            "corpus_task_id": task_id,
            "corpus_aware": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["corpus_context"]["applied"] is True
    assert [value["video_id"] for value in body["results"]] == [
        video_ids[0],
        video_ids[3],
        video_ids[1],
        video_ids[4],
    ]
    disabled = client.post(
        "/api/search",
        json={
            "query": "MCP",
            "mode": "lexical",
            "result_limit": 4,
            "max_windows_per_video": 1,
            "corpus_task_id": task_id,
            "corpus_aware": False,
        },
    ).json()
    assert disabled["corpus_context"]["status"] == "disabled"
    assert [value["video_id"] for value in disabled["results"]] == video_ids[:4]

    legacy = ProductSearchRequest(query="MemoryOS", mode="lexical")
    serialized = legacy.model_dump(mode="json")
    assert "corpus_task_id" not in serialized and "corpus_aware" not in serialized
    html = client.get("/search").text
    script = client.get("/static/search.js").text
    assert "data-corpus-search-context" in html
    assert 'name="corpus_task_id"' in html
    assert 'name="corpus_aware"' in html
    assert "result_contributions" in script
    assert "Corpus soft prior" in script


def test_stage2_search_ask_research_route_and_stage1_noninterference(app_paths) -> None:
    core = _core(app_paths)
    task_id, fact, _, _ = _vertical(core, "v5c-stage2-noninterference")
    preference = _create(
        core,
        task_id,
        command_id="v5c2:stage1-preference",
        record_kind="explicit_memory",
        semantic_key=LIMITATIONS_POSITION_KEY,
        payload={"key": LIMITATIONS_POSITION_KEY, "value": "before_answer"},
    )
    assert preference["product_behavior_effect"] is False
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
    research_before = _stable_research(core.research_knowledge.get_workspace(task_id))
    personalization_before = core.research_knowledge.get_personal_workspace(task_id)[
        "personalization_context"
    ]
    route_before = _stable_route(
        core.research_knowledge.assess_artifact_route(
            task_id,
            AssessArtifactRouteRequest(
                command_id="v5c2:route:before",
                query=fact["claim"],
                required_aspects=[fact["claim"]],
            ),
        )
    )
    _corpus_prior(core, task_id, snapshot, suffix="noninterference")
    search_after = _stable_search(
        core.product_search.search(ProductSearchRequest(query=OBJECTIVE)).as_dict()
    )
    ask_after = _stable_ask(
        core.ask_service.ask(AskRequest(query="ZZZZZ-NO-SUCH-EVIDENCE")).model_dump(
            mode="json"
        )
    )
    research_after = _stable_research(core.research_knowledge.get_workspace(task_id))
    personalization_after = core.research_knowledge.get_personal_workspace(task_id)[
        "personalization_context"
    ]
    route_after = _stable_route(
        core.research_knowledge.assess_artifact_route(
            task_id,
            AssessArtifactRouteRequest(
                command_id="v5c2:route:after",
                query=fact["claim"],
                required_aspects=[fact["claim"]],
            ),
        )
    )
    assert search_after == search_before
    assert ask_after == ask_before
    assert research_after == research_before
    assert route_after == route_before
    assert personalization_after == personalization_before
    assert route_after["open_corpus"]["independent_lane"] is True
    assert route_after["open_corpus"]["hard_filter"] is False
