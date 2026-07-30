from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from shiliu.ask.context import TranscriptContextBuilder
from shiliu.app import Application
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.db import Database, SCHEMA_VERSION
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.research.errors import (
    ResearchConflict,
    ResearchUnsafeState,
    SimulatedCrash,
)
from shiliu.research import AnswerStatus, FailureClass, TaskStatus, TerminationReason
from shiliu.research.inner_contracts import (
    ContinueInnerResearchRequest,
    RevalidateInnerEvidenceRequest,
)
from shiliu.research.inner_service import InnerResearchService
from shiliu.research.inner_evidence import evidence_identity_payload
from shiliu.research.inner_tools import DeterministicInnerToolAdapter
from shiliu.retrieval.coordinator import SYNC_STATE_VERSION
from shiliu.web import create_web_app


STAGE2_TABLES = {
    "research_inner_actions",
    "research_evidence_identities",
    "research_evidence_uses",
    "research_evidence_provenance",
    "research_evidence_validations",
    "research_provisional_artifacts",
}


class MutableClock:
    def __init__(self, value: datetime | None = None) -> None:
        self.value = value or datetime.now(timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def _fixture_core(app_paths):
    core = Application(app_paths)
    source_db_id = core.db.create_favorite_source(
        folder_id=1202, folder_title="Stage 2 Fixture"
    )
    item = FavoriteItem(
        bvid="BV1234567890",
        title="MCP Durable Research",
        uploader="Stage2",
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
                {
                    "from": index * 5,
                    "to": index * 5 + 4,
                    "content": text,
                }
            )
            for index, text in enumerate(
                (
                    "MCP 使用客户端与服务端连接模型和外部能力。",
                    "工具调用需要明确的请求与响应协议。",
                    "研究任务通过持久 checkpoint 恢复。",
                    "权威字幕窗口提供相邻上下文。",
                    "最终回答必须绑定稳定引用。",
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
    return core, raw_path.with_name("subtitle-raw.json")


def _start(core: Application, task_id: str, *, owner: str = "worker"):
    core.research.create_task(
        command_id=f"create:{task_id}",
        task_id=task_id,
        objective="MCP",
        success_constraints=["引用当前字幕"],
        evidence_policy={"authority": "live_current_exact_replay"},
    )
    claimed = core.research.claim_owner(
        task_id=task_id,
        command_id=f"claim:{task_id}",
        owner_id=owner,
        expected_state_version=0,
        lease_seconds=300,
    )
    started = core.research.start_attempt(
        task_id=task_id,
        command_id=f"start:{task_id}",
        owner_id=owner,
        owner_epoch=int(claimed["owner_epoch"]),
        expected_state_version=1,
    )
    return {
        "task_id": task_id,
        "attempt_id": str(started["attempt_id"]),
        "owner_id": owner,
        "owner_epoch": int(claimed["owner_epoch"]),
        "state_version": 2,
        "checkpoint_id": None,
    }


def _continue(service: InnerResearchService, run: dict[str, object], index: int):
    request = ContinueInnerResearchRequest(
        command_id=(
            f"inner:{run['task_id']}:{run['attempt_id']}:{index}"
        ),
        attempt_id=str(run["attempt_id"]),
        owner_id=str(run["owner_id"]),
        owner_epoch=int(run["owner_epoch"]),
        expected_state_version=int(run["state_version"]),
        expected_checkpoint_id=(
            str(run["checkpoint_id"]) if run["checkpoint_id"] else None
        ),
    )
    result = service.continue_run(str(run["task_id"]), request)
    run["state_version"] = result["state_version"]
    run["checkpoint_id"] = result["checkpoint_id"]
    return result, request


def _counts(db: Database, task_id: str) -> dict[str, int]:
    with db.connect() as connection:
        return {
            table: int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE task_id=?",  # noqa: S608
                    (task_id,),
                ).fetchone()[0]
            )
            for table in (
                "research_inner_actions",
                "research_evidence_uses",
                "research_evidence_validations",
                "research_provisional_artifacts",
            )
        }


def _research_lengths(core: Application, task_id: str) -> dict[str, int]:
    state = core.research.get_task(task_id)
    return {
        key: len(state[key])
        for key in (
            "inner_actions",
            "checkpoints",
            "events",
            "command_receipts",
            "provisional_artifacts",
        )
    }


def test_schema_8_adds_stage2_tables_only_in_temporary_database(app_paths) -> None:
    app_paths.database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(app_paths.database)
    connection.executescript(
        """
        CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '7');
        """
    )
    connection.commit()
    connection.close()

    db = Database(app_paths.database)
    db.initialize()
    db.initialize()

    assert SCHEMA_VERSION == 8
    assert app_paths.database.with_name("shiliu.pre-v8.backup.db").is_file()
    with db.connect() as migrated:
        version = migrated.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
        tables = {
            str(row[0])
            for row in migrated.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            ).fetchall()
        }
        integrity = migrated.execute("PRAGMA integrity_check").fetchone()[0]
        violations = migrated.execute("PRAGMA foreign_key_check").fetchall()
    assert version == "8"
    assert STAGE2_TABLES.issubset(tables)
    assert integrity == "ok"
    assert violations == []


def test_durable_inner_loop_runs_one_action_per_checkpoint_and_stays_nonterminal(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "inner-e2e")

    phases = []
    for index in range(5):
        outcome, _ = _continue(core.research_inner, run, index)
        phases.append(outcome["phase"])

    assert phases == [
        "navigation",
        "transcript_search",
        "transcript_window",
        "provisional_synthesis",
        "complete",
    ]
    persisted = core.research_inner.get_inner_state("inner-e2e")
    assert persisted["state"]["phase"] == "complete"
    assert len(persisted["inner_actions"]) == 5
    assert len(persisted["evidence_uses"]) >= 1
    assert persisted["provisional_artifacts"][0]["answer_status"] == "valid_partial"
    assert persisted["provisional_artifacts"][0]["answer_blocks"]
    assert persisted["state"]["answer_status"] == "valid_partial"
    assert persisted["state"]["termination_reason"] == "answer_ready"
    assert persisted["state"]["failure_class"] == "none"
    assert (
        0
        < persisted["state"]["budget"]["synthesis_context_characters"]
        <= core.research_inner.MAX_CONTEXT_CHARACTERS
    )
    task = core.research.get_task("inner-e2e")
    assert task["task"]["status"] == "running"
    assert task["task"]["terminal_result_id"] is None
    assert task["attempts"][0]["status"] == "running"
    assert persisted["state"]["consecutive_no_progress"] == 1
    assert persisted["state"]["cumulative_progress"]["new_evidence_groups"] >= 1

    restarted = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=core.research_inner.tools,
        materializer=TranscriptEvidenceMaterializer(core.db),
    )
    assert restarted.get_inner_state("inner-e2e")["state"] == persisted["state"]


def test_api_synthesis_context_is_exactly_charged_once_across_replay_restart_and_takeover(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "synthesis-context-accounting")
    for index in range(4):
        _continue(core.research_inner, run, index)

    class _RecordingContextBuilder(TranscriptContextBuilder):
        def __init__(self) -> None:
            super().__init__(total_character_budget=12_000)
            self.calls = 0
            self.last_context = None

        def build(self, **kwargs):
            self.calls += 1
            self.last_context = super().build(**kwargs)
            return self.last_context

    builder = _RecordingContextBuilder()
    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=core.research_inner.tools,
        materializer=TranscriptEvidenceMaterializer(core.db),
        context_builder=builder,
    )
    core._research_inner = service
    client = TestClient(create_web_app(core))
    payload = {
        "command_id": "synthesis-context-accounting:commit",
        "attempt_id": run["attempt_id"],
        "owner_id": run["owner_id"],
        "owner_epoch": run["owner_epoch"],
        "expected_state_version": run["state_version"],
        "expected_checkpoint_id": run["checkpoint_id"],
    }
    response = client.post(
        "/api/research/tasks/synthesis-context-accounting/inner/continue",
        json=payload,
    )
    assert response.status_code == 200
    assert response.json()["outcome"]["phase"] == "complete"
    assert builder.calls == 1
    assert builder.last_context is not None
    expected_characters = len(builder.last_context.model_context)
    assert 0 < expected_characters <= service.MAX_CONTEXT_CHARACTERS
    assert (
        response.json()["inner"]["state"]["budget"][
            "synthesis_context_characters"
        ]
        == expected_characters
    )
    event = core.research.get_task("synthesis-context-accounting")["events"][-1]
    assert event["payload"]["synthesis_context_characters"] == expected_characters

    before_replay = _research_lengths(core, "synthesis-context-accounting")
    replay = client.post(
        "/api/research/tasks/synthesis-context-accounting/inner/continue",
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json()["outcome"]["deduplicated"] is True
    assert builder.calls == 1
    assert (
        replay.json()["inner"]["state"]["budget"][
            "synthesis_context_characters"
        ]
        == expected_characters
    )
    assert _research_lengths(core, "synthesis-context-accounting") == before_replay

    restarted = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=core.research_inner.tools,
        materializer=TranscriptEvidenceMaterializer(core.db),
    )
    assert (
        restarted.get_inner_state("synthesis-context-accounting")["state"][
            "budget"
        ]["synthesis_context_characters"]
        == expected_characters
    )

    with core.db.connect() as connection:
        connection.execute(
            """
            UPDATE research_tasks SET lease_until=?
            WHERE task_id='synthesis-context-accounting'
            """,
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),),
        )
    takeover = core.research.claim_owner(
        task_id="synthesis-context-accounting",
        command_id="synthesis-context-accounting:takeover",
        owner_id="new-owner",
        expected_state_version=int(response.json()["outcome"]["state_version"]),
        lease_seconds=300,
    )
    assert int(takeover["owner_epoch"]) == int(run["owner_epoch"]) + 1
    assert (
        restarted.get_inner_state("synthesis-context-accounting")["state"][
            "budget"
        ]["synthesis_context_characters"]
        == expected_characters
    )


def test_synthesis_context_over_server_limit_rolls_back_and_fails_durably(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "synthesis-context-limit")
    for index in range(4):
        _continue(core.research_inner, run, index)
    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=core.research_inner.tools,
        materializer=TranscriptEvidenceMaterializer(core.db),
    )
    service.MAX_CONTEXT_CHARACTERS = 1

    result, _ = _continue(service, run, 4)
    assert result["phase"] == "stopped"
    assert result["stop_reason"] == "implementation_error"
    persisted = service.get_inner_state("synthesis-context-limit")
    assert persisted["state"]["budget"]["synthesis_context_characters"] == 0
    assert persisted["state"]["termination_reason"] == "implementation_error"
    assert persisted["state"]["failure_class"] == "implementation_failure"
    assert persisted["provisional_artifacts"] == []
    assert persisted["inner_actions"][-1]["status"] == "failed"


def test_inner_command_replay_is_idempotent_and_payload_mismatch_fails_closed(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "inner-replay")
    first, request = _continue(core.research_inner, run, 0)
    before = _counts(core.db, "inner-replay")

    replay = core.research_inner.continue_run("inner-replay", request)
    assert replay["checkpoint_id"] == first["checkpoint_id"]
    assert replay["deduplicated"] is True
    assert _counts(core.db, "inner-replay") == before

    mismatch = request.model_copy(update={"expected_checkpoint_id": "forged"})
    with pytest.raises(ResearchConflict):
        core.research_inner.continue_run("inner-replay", mismatch)
    assert _counts(core.db, "inner-replay") == before


def test_conflicting_global_evidence_identity_payload_fails_closed_via_service(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    span = core.research_inner.tools.search(
        "MCP", video_ids=(), query_index=0
    ).spans[0]
    identity = evidence_identity_payload(span)
    with core.db.connect() as connection:
        connection.execute(
            """
            INSERT INTO research_evidence_identities(
                evidence_id, citation_identity_version, video_id,
                source_artifact_id, source_version, timeline_run_id,
                segment_ids_json, segment_ordinals_json,
                start_time, end_time, quote_hash, quote_preview,
                identity_payload_hash, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'forged', ?)
            """,
            (
                span.citation_id,
                span.citation_identity_version,
                span.video_id,
                span.source_artifact_id,
                span.source_version,
                span.timeline_run_id,
                json.dumps(list(span.segment_ids)),
                json.dumps(list(span.segment_ordinals)),
                span.start_time,
                span.end_time,
                identity["quote_hash"],
                span.quote_text,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    run = _start(core, "identity-conflict")
    _continue(core.research_inner, run, 0)
    _continue(core.research_inner, run, 1)
    before = _counts(core.db, "identity-conflict")
    with pytest.raises(ResearchUnsafeState, match="canonical identity payload"):
        _continue(core.research_inner, run, 2)
    assert _counts(core.db, "identity-conflict") == before


def test_global_identity_dedupes_but_task_attempt_use_and_provenance_are_isolated(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    span = core.research_inner.tools.search(
        "MCP", video_ids=(), query_index=0
    ).spans[0]
    window_span = span.model_copy(
        update={
            "retrieval_provenance": (
                {
                    "action": "read_transcript_window",
                    "query": "MCP window",
                    "rank": 1,
                },
            )
        }
    )
    deterministic = DeterministicInnerToolAdapter(
        search_spans=(span,), window_span=window_span
    )
    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=deterministic,
        materializer=TranscriptEvidenceMaterializer(core.db),
    )
    first = _start(core, "identity-a")
    second = _start(core, "identity-b")
    for run in (first, second):
        for index in range(4):
            _continue(service, run, index)

    with core.db.connect() as connection:
        identity_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM research_evidence_identities"
            ).fetchone()[0]
        )
        uses = connection.execute(
            """
            SELECT task_id, attempt_id, evidence_use_id
            FROM research_evidence_uses ORDER BY task_id
            """
        ).fetchall()
        provenance_counts = {
            str(row["task_id"]): int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM research_evidence_provenance ep
                    JOIN research_evidence_uses eu
                      ON eu.evidence_use_id=ep.evidence_use_id
                    WHERE eu.task_id=?
                    """,
                    (str(row["task_id"]),),
                ).fetchone()[0]
            )
            for row in uses
        }
    assert identity_count == 1
    assert len(uses) == 2
    assert uses[0]["evidence_use_id"] != uses[1]["evidence_use_id"]
    assert provenance_counts == {"identity-a": 2, "identity-b": 2}
    a = service.get_inner_state("identity-a")
    b = service.get_inner_state("identity-b")
    assert {
        value["evidence_use_id"] for value in a["evidence_uses"]
    }.isdisjoint(
        value["evidence_use_id"] for value in b["evidence_uses"]
    )


def test_stale_source_appends_observation_without_rewriting_identity_or_artifact(
    app_paths,
) -> None:
    core, raw_path = _fixture_core(app_paths)
    run = _start(core, "inner-stale")
    for index in range(3):
        _continue(core.research_inner, run, index)
    with core.db.connect() as connection:
        identity_before = dict(
            connection.execute(
                "SELECT * FROM research_evidence_identities"
            ).fetchone()
        )

    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    payload[0]["content"] = "字幕版本已改变"
    raw_path.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    _continue(core.research_inner, run, 3)
    synthesis, _ = _continue(core.research_inner, run, 4)
    assert synthesis["phase"] == "complete"

    with core.db.connect() as connection:
        identity_after = dict(
            connection.execute(
                "SELECT * FROM research_evidence_identities"
            ).fetchone()
        )
        outcomes = [
            str(row["outcome"])
            for row in connection.execute(
                """
                SELECT outcome FROM research_evidence_validations
                WHERE task_id='inner-stale' ORDER BY observed_at, observation_id
                """
            ).fetchall()
        ]
        artifact = connection.execute(
            """
            SELECT * FROM research_provisional_artifacts
            WHERE task_id='inner-stale'
            """
        ).fetchone()
    assert identity_after == identity_before
    assert "stale" in outcomes
    assert artifact is not None
    assert artifact["answer_status"] == "valid_insufficient"
    assert json.loads(artifact["evidence_use_ids_json"]) == []
    state = core.research_inner.get_inner_state("inner-stale")["state"]
    assert state["answer_status"] == "valid_insufficient"
    assert state["termination_reason"] == "evidence_unavailable"
    assert state["failure_class"] == "none"


def test_post_commit_source_drift_keeps_artifact_immutable_and_view_not_current(
    app_paths,
) -> None:
    core, raw_path = _fixture_core(app_paths)
    run = _start(core, "artifact-drift")
    for index in range(5):
        _continue(core.research_inner, run, index)
    before = core.research_inner.get_inner_state("artifact-drift")
    artifact_before = dict(before["provisional_artifacts"][0])
    assert artifact_before["derived_current"] is True

    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    payload[-1]["content"] = "提交后字幕发生变化"
    raw_path.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    after = core.research_inner.get_inner_state("artifact-drift")
    artifact_after = dict(after["provisional_artifacts"][0])
    assert artifact_after["artifact_hash"] == artifact_before["artifact_hash"]
    assert artifact_after["answer_blocks"] == artifact_before["answer_blocks"]
    assert artifact_after["derived_current"] is False
    assert {
        value["outcome"] for value in after["derived_currentness"].values()
    } == {"stale"}

    revalidated = core.research_inner.revalidate_evidence(
        "artifact-drift",
        RevalidateInnerEvidenceRequest(
            command_id="artifact-drift:revalidate",
            attempt_id=str(run["attempt_id"]),
            owner_id=str(run["owner_id"]),
            owner_epoch=int(run["owner_epoch"]),
            expected_state_version=int(run["state_version"]),
            expected_checkpoint_id=str(run["checkpoint_id"]),
        ),
    )
    assert set(revalidated["outcomes"].values()) == {"stale"}
    run["state_version"] = revalidated["state_version"]
    run["checkpoint_id"] = revalidated["checkpoint_id"]
    observed = core.research_inner.get_inner_state("artifact-drift")
    assert observed["provisional_artifacts"][0]["artifact_hash"] == artifact_before[
        "artifact_hash"
    ]
    assert observed["evidence_validations"][-1]["outcome"] == "stale"


def test_evidence_identity_use_provenance_validation_and_artifact_are_immutable(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "immutable")
    for index in range(5):
        _continue(core.research_inner, run, index)

    mutations = (
        "UPDATE research_evidence_identities SET quote_preview='changed'",
        "UPDATE research_evidence_uses SET use_purpose='changed'",
        "UPDATE research_evidence_provenance SET retrieval_method='changed'",
        "UPDATE research_evidence_validations SET outcome='stale'",
        "UPDATE research_provisional_artifacts SET limitations_json='[]'",
    )
    for statement in mutations:
        with pytest.raises(sqlite3.IntegrityError):
            with core.db.connect() as connection:
                connection.execute(statement)


def test_inner_fault_rolls_back_action_identity_use_checkpoint_event_and_receipt(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    span = core.research_inner.tools.search(
        "MCP", video_ids=(), query_index=0
    ).spans[0]
    run = _start(core, "inner-fault")
    adapter = DeterministicInnerToolAdapter(search_spans=(span,))
    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=adapter,
        materializer=TranscriptEvidenceMaterializer(core.db),
    )
    _continue(service, run, 0)
    _continue(service, run, 1)
    before = core.research.get_task("inner-fault")
    before_counts = _counts(core.db, "inner-fault")

    def crash(point: str) -> None:
        if point == "after_evidence_use_insert":
            raise SimulatedCrash(point)

    service.fault_injector = crash
    request = ContinueInnerResearchRequest(
        command_id="inner:inner-fault:2",
        attempt_id=str(run["attempt_id"]),
        owner_id=str(run["owner_id"]),
        owner_epoch=int(run["owner_epoch"]),
        expected_state_version=int(run["state_version"]),
        expected_checkpoint_id=str(run["checkpoint_id"]),
    )
    with pytest.raises(SimulatedCrash):
        service.continue_run("inner-fault", request)

    after = core.research.get_task("inner-fault")
    assert after["task"]["state_version"] == before["task"]["state_version"]
    assert len(after["events"]) == len(before["events"])
    assert len(after["command_receipts"]) == len(before["command_receipts"])
    assert _counts(core.db, "inner-fault") == before_counts
    with core.db.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM research_evidence_identities"
            ).fetchone()[0]
            == 0
        )


def test_artifact_fault_rolls_back_action_checkpoint_observations_and_artifact(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "artifact-fault")
    for index in range(4):
        _continue(core.research_inner, run, index)
    before = core.research.get_task("artifact-fault")
    before_counts = _counts(core.db, "artifact-fault")

    def crash(point: str) -> None:
        if point == "after_provisional_artifact_insert":
            raise SimulatedCrash(point)

    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=core.research_inner.tools,
        materializer=TranscriptEvidenceMaterializer(core.db),
        fault_injector=crash,
    )
    request = ContinueInnerResearchRequest(
        command_id="artifact-fault:synthesis",
        attempt_id=str(run["attempt_id"]),
        owner_id=str(run["owner_id"]),
        owner_epoch=int(run["owner_epoch"]),
        expected_state_version=int(run["state_version"]),
        expected_checkpoint_id=str(run["checkpoint_id"]),
    )
    with pytest.raises(SimulatedCrash):
        service.continue_run("artifact-fault", request)
    after = core.research.get_task("artifact-fault")
    assert after["task"]["state_version"] == before["task"]["state_version"]
    assert len(after["events"]) == len(before["events"])
    assert len(after["command_receipts"]) == len(before["command_receipts"])
    assert _counts(core.db, "artifact-fault") == before_counts
    assert (
        service.get_inner_state("artifact-fault")["state"]["budget"][
            "synthesis_context_characters"
        ]
        == 0
    )

    service.fault_injector = lambda _point: None
    recovered = service.continue_run("artifact-fault", request)
    assert recovered["phase"] == "complete"
    assert _counts(core.db, "artifact-fault")["research_provisional_artifacts"] == 1
    assert (
        service.get_inner_state("artifact-fault")["state"]["budget"][
            "synthesis_context_characters"
        ]
        > 0
    )


def test_takeover_fences_old_inner_worker_before_tool_or_mutation(app_paths) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "inner-fence", owner="old")
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE research_tasks SET lease_until=? WHERE task_id=?",
            (
                (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                "inner-fence",
            ),
        )
    current_version = int(
        core.research.get_task("inner-fence")["task"]["state_version"]
    )
    takeover = core.research.claim_owner(
        task_id="inner-fence",
        command_id="takeover",
        owner_id="new",
        expected_state_version=current_version,
        lease_seconds=300,
    )
    before = _counts(core.db, "inner-fence")
    with pytest.raises(ResearchConflict):
        core.research_inner.continue_run(
            "inner-fence",
            ContinueInnerResearchRequest(
                command_id="stale-inner",
                attempt_id=str(run["attempt_id"]),
                owner_id="old",
                owner_epoch=int(run["owner_epoch"]),
                expected_state_version=int(takeover["state_version"]),
            ),
        )
    assert _counts(core.db, "inner-fence") == before


def test_late_tool_response_is_rejected_when_takeover_happens_during_action(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "late-owner", owner="old")

    class _TakeoverDuringNavigation(DeterministicInnerToolAdapter):
        def navigate(self, query: str):
            with core.db.connect() as connection:
                connection.execute(
                    "UPDATE research_tasks SET lease_until=? WHERE task_id=?",
                    (
                        (
                            datetime.now(timezone.utc) - timedelta(seconds=1)
                        ).isoformat(),
                        "late-owner",
                    ),
                )
            core.research.claim_owner(
                task_id="late-owner",
                command_id="late-takeover",
                owner_id="new",
                expected_state_version=int(run["state_version"]),
                lease_seconds=300,
            )
            return super().navigate(query)

    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=_TakeoverDuringNavigation(),
        materializer=TranscriptEvidenceMaterializer(core.db),
    )
    _continue(service, run, 0)
    before = _counts(core.db, "late-owner")
    with pytest.raises(ResearchConflict):
        _continue(service, run, 1)
    assert _counts(core.db, "late-owner") == before
    assert core.research.get_task("late-owner")["task"]["owner_id"] == "new"


def test_unresolved_side_effect_blocks_inner_checkpoint_without_state_drift(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "inner-side-effect")
    _continue(core.research_inner, run, 0)
    reserved = core.research.reserve_side_effect(
        task_id="inner-side-effect",
        attempt_id=str(run["attempt_id"]),
        command_id="reserve-provider",
        owner_id=str(run["owner_id"]),
        owner_epoch=int(run["owner_epoch"]),
        expected_state_version=int(run["state_version"]),
        effect_kind="stage2_provider",
        idempotency_key="provider-call",
        request_payload={"role": "stage2_inner"},
    )
    started = core.research.transition_side_effect(
        task_id="inner-side-effect",
        side_effect_id=str(reserved["side_effect_id"]),
        command_id="start-provider",
        owner_id=str(run["owner_id"]),
        owner_epoch=int(run["owner_epoch"]),
        expected_state_version=int(reserved["state_version"]),
        target_status="in_flight",
        operation_id="fake-operation",
    )
    run["state_version"] = int(started["state_version"])
    before = _counts(core.db, "inner-side-effect")
    with pytest.raises(ResearchUnsafeState):
        _continue(core.research_inner, run, 1)
    assert _counts(core.db, "inner-side-effect") == before


def test_budget_stop_is_persisted_and_survives_restart(app_paths) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "inner-budget")
    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=DeterministicInnerToolAdapter(),
        materializer=TranscriptEvidenceMaterializer(core.db),
    )
    service.MAX_RESEARCH_ACTIONS = 1
    outcome, _ = _continue(service, run, 0)
    assert outcome["phase"] == "stopped"
    assert outcome["stop_reason"] == "budget_exhausted"
    restarted = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=DeterministicInnerToolAdapter(),
        materializer=TranscriptEvidenceMaterializer(core.db),
    )
    persisted = restarted.get_inner_state("inner-budget")["state"]
    assert persisted["phase"] == "stopped"
    assert persisted["budget"]["research_actions"] == 1
    assert persisted["answer_status"] == "not_produced"
    assert persisted["termination_reason"] == "budget_exhausted"
    assert persisted["failure_class"] == "none"


@pytest.mark.parametrize(
    ("dimension", "actions_before_stop"),
    (
        ("runtime_seconds", 1),
        ("decision_rounds", 4),
        ("window_reads", 3),
        ("materialized_evidence_uses", 3),
    ),
)
def test_pre_action_hard_budget_exhaustion_commits_one_durable_stop(
    app_paths,
    dimension: str,
    actions_before_stop: int,
) -> None:
    core, _ = _fixture_core(app_paths)
    span = core.research_inner.tools.search(
        "MCP", video_ids=(), query_index=0
    ).spans[0]
    adapter = DeterministicInnerToolAdapter(search_spans=(span,))
    clock = MutableClock()
    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=adapter,
        materializer=TranscriptEvidenceMaterializer(core.db),
        clock=clock,
    )
    if dimension == "decision_rounds":
        service.MAX_DECISION_ROUNDS = 1
    elif dimension == "window_reads":
        service.MAX_WINDOW_READS = 0
    elif dimension == "materialized_evidence_uses":
        service.MAX_EVIDENCE_USES = 1
    run = _start(core, f"budget-{dimension}")
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE research_tasks SET lease_until=? WHERE task_id=?",
            (
                (clock() + timedelta(seconds=900)).isoformat(),
                run["task_id"],
            ),
        )
    for index in range(actions_before_stop):
        _continue(service, run, index)
    if dimension == "runtime_seconds":
        clock.advance(361)
    if dimension == "materialized_evidence_uses":
        old_owner = str(run["owner_id"])
        old_epoch = int(run["owner_epoch"])
        with core.db.connect() as connection:
            connection.execute(
                "UPDATE research_tasks SET lease_until=? WHERE task_id=?",
                (
                    (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                    run["task_id"],
                ),
            )
        takeover = core.research.claim_owner(
            task_id=str(run["task_id"]),
            command_id="evidence-budget:takeover",
            owner_id="new-owner",
            expected_state_version=int(run["state_version"]),
            lease_seconds=300,
        )
        run["owner_id"] = "new-owner"
        run["owner_epoch"] = int(takeover["owner_epoch"])
        run["state_version"] = int(takeover["state_version"])
        stale_calls_before = len(adapter.calls)
        with pytest.raises(ResearchConflict):
            service.continue_run(
                str(run["task_id"]),
                ContinueInnerResearchRequest(
                    command_id="evidence-budget:stale-owner",
                    attempt_id=str(run["attempt_id"]),
                    owner_id=old_owner,
                    owner_epoch=old_epoch,
                    expected_state_version=int(run["state_version"]),
                    expected_checkpoint_id=str(run["checkpoint_id"]),
                ),
            )
        assert len(adapter.calls) == stale_calls_before
    before = _research_lengths(core, str(run["task_id"]))
    tool_calls_before = len(adapter.calls)
    request = ContinueInnerResearchRequest(
        command_id=f"budget-stop:{dimension}",
        attempt_id=str(run["attempt_id"]),
        owner_id=str(run["owner_id"]),
        owner_epoch=int(run["owner_epoch"]),
        expected_state_version=int(run["state_version"]),
        expected_checkpoint_id=str(run["checkpoint_id"]),
    )
    stopped = service.continue_run(str(run["task_id"]), request)
    assert stopped["phase"] == "stopped"
    assert stopped["action_id"] is None
    assert stopped["action_kind"] is None
    assert stopped["budget_dimension"] == dimension
    assert stopped["stop_reason"] == "budget_exhausted"
    assert len(adapter.calls) == tool_calls_before

    after = _research_lengths(core, str(run["task_id"]))
    assert after["inner_actions"] == before["inner_actions"]
    assert after["checkpoints"] == before["checkpoints"] + 1
    assert after["events"] == before["events"] + 1
    assert after["command_receipts"] == before["command_receipts"] + 1
    state = service.get_inner_state(str(run["task_id"]))["state"]
    assert state["phase"] == "stopped"
    assert state["answer_status"] == "not_produced"
    assert state["termination_reason"] == "budget_exhausted"
    assert state["failure_class"] == "none"
    event = core.research.get_task(str(run["task_id"]))["events"][-1]
    assert event["event_type"] == "inner_budget_exhausted"
    assert event["payload"]["budget_dimension"] == dimension

    replay = service.continue_run(str(run["task_id"]), request)
    assert replay["checkpoint_id"] == stopped["checkpoint_id"]
    assert replay["deduplicated"] is True
    assert _research_lengths(core, str(run["task_id"])) == after
    with pytest.raises(ResearchConflict):
        service.continue_run(
            str(run["task_id"]),
            request.model_copy(update={"expected_checkpoint_id": "forged"}),
        )
    mismatch_after = _research_lengths(core, str(run["task_id"]))
    assert mismatch_after["events"] == after["events"] + 1
    assert {
        key: value for key, value in mismatch_after.items() if key != "events"
    } == {key: value for key, value in after.items() if key != "events"}

    restarted = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=adapter,
        materializer=TranscriptEvidenceMaterializer(core.db),
        clock=clock,
    )
    assert restarted.get_inner_state(str(run["task_id"]))["state"] == state

    if dimension == "runtime_seconds":
        with core.db.connect() as connection:
            connection.execute(
                "UPDATE research_tasks SET lease_until=? WHERE task_id=?",
                (
                    (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                    run["task_id"],
                ),
            )
        takeover = core.research.claim_owner(
            task_id=str(run["task_id"]),
            command_id="budget-stop:takeover",
            owner_id="new-owner",
            expected_state_version=int(stopped["state_version"]),
            lease_seconds=300,
        )
        post_takeover = InnerResearchService(
            db=core.db,
            kernel=core.research,
            tools=adapter,
            materializer=TranscriptEvidenceMaterializer(core.db),
        )
        takeover_before = _research_lengths(core, str(run["task_id"]))
        with pytest.raises(ResearchUnsafeState, match="phase=stopped"):
            post_takeover.continue_run(
                str(run["task_id"]),
                ContinueInnerResearchRequest(
                    command_id="budget-stop:after-takeover",
                    attempt_id=str(run["attempt_id"]),
                    owner_id="new-owner",
                    owner_epoch=int(takeover["owner_epoch"]),
                    expected_state_version=int(takeover["state_version"]),
                    expected_checkpoint_id=str(stopped["checkpoint_id"]),
                ),
            )
        assert _research_lengths(core, str(run["task_id"])) == takeover_before


def test_api_runtime_budget_exhaustion_returns_durable_stop_and_replays_once(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    clock = MutableClock()
    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=DeterministicInnerToolAdapter(),
        materializer=TranscriptEvidenceMaterializer(core.db),
        clock=clock,
    )
    core._research_inner = service
    run = _start(core, "budget-api")
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE research_tasks SET lease_until=? WHERE task_id='budget-api'",
            ((clock() + timedelta(seconds=900)).isoformat(),),
        )
    first, _ = _continue(service, run, 0)
    clock.advance(361)
    client = TestClient(create_web_app(core))
    payload = {
        "command_id": "budget-api:stop",
        "attempt_id": run["attempt_id"],
        "owner_id": run["owner_id"],
        "owner_epoch": run["owner_epoch"],
        "expected_state_version": first["state_version"],
        "expected_checkpoint_id": first["checkpoint_id"],
    }
    response = client.post(
        "/api/research/tasks/budget-api/inner/continue", json=payload
    )
    assert response.status_code == 200
    assert response.json()["outcome"]["action_id"] is None
    assert response.json()["outcome"]["budget_dimension"] == "runtime_seconds"
    before_replay = _research_lengths(core, "budget-api")
    replay = client.post(
        "/api/research/tasks/budget-api/inner/continue", json=payload
    )
    assert replay.status_code == 200
    assert replay.json()["outcome"]["deduplicated"] is True
    assert _research_lengths(core, "budget-api") == before_replay
    mismatch = client.post(
        "/api/research/tasks/budget-api/inner/continue",
        json={**payload, "expected_checkpoint_id": "forged"},
    )
    assert mismatch.status_code == 409
    mismatch_after = _research_lengths(core, "budget-api")
    assert mismatch_after["events"] == before_replay["events"] + 1
    assert {
        key: value for key, value in mismatch_after.items() if key != "events"
    } == {
        key: value for key, value in before_replay.items() if key != "events"
    }


def test_api_evidence_budget_exhaustion_stops_before_window_and_replays_once(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    span = core.research_inner.tools.search(
        "MCP", video_ids=(), query_index=0
    ).spans[0]
    adapter = DeterministicInnerToolAdapter(search_spans=(span,))
    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=adapter,
        materializer=TranscriptEvidenceMaterializer(core.db),
    )
    service.MAX_EVIDENCE_USES = 1
    core._research_inner = service
    run = _start(core, "evidence-budget-api")
    for index in range(3):
        _continue(service, run, index)
    assert [value["kind"] for value in adapter.calls] == [
        "navigation",
        "transcript_search",
    ]

    client = TestClient(create_web_app(core))
    payload = {
        "command_id": "evidence-budget-api:stop",
        "attempt_id": run["attempt_id"],
        "owner_id": run["owner_id"],
        "owner_epoch": run["owner_epoch"],
        "expected_state_version": run["state_version"],
        "expected_checkpoint_id": run["checkpoint_id"],
    }
    before = _research_lengths(core, "evidence-budget-api")
    response = client.post(
        "/api/research/tasks/evidence-budget-api/inner/continue",
        json=payload,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"]["action_id"] is None
    assert body["outcome"]["budget_dimension"] == "materialized_evidence_uses"
    assert body["inner"]["state"]["phase"] == "stopped"
    assert body["inner"]["state"]["answer_status"] == "not_produced"
    assert body["inner"]["state"]["termination_reason"] == "budget_exhausted"
    assert body["inner"]["state"]["failure_class"] == "none"
    assert [value["kind"] for value in adapter.calls] == [
        "navigation",
        "transcript_search",
    ]
    after = _research_lengths(core, "evidence-budget-api")
    assert after["inner_actions"] == before["inner_actions"]
    assert after["checkpoints"] == before["checkpoints"] + 1
    assert after["events"] == before["events"] + 1
    assert after["command_receipts"] == before["command_receipts"] + 1

    replay = client.post(
        "/api/research/tasks/evidence-budget-api/inner/continue",
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json()["outcome"]["deduplicated"] is True
    assert _research_lengths(core, "evidence-budget-api") == after
    assert not any(
        value["kind"] == "transcript_window" for value in adapter.calls
    )
    mismatch = client.post(
        "/api/research/tasks/evidence-budget-api/inner/continue",
        json={**payload, "expected_checkpoint_id": "forged"},
    )
    assert mismatch.status_code == 409
    assert not any(
        value["kind"] == "transcript_window" for value in adapter.calls
    )


def test_local_action_failure_persists_orthogonal_failure_dimensions(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)

    class _FailingNavigation(DeterministicInnerToolAdapter):
        def navigate(self, query: str):
            raise RuntimeError(f"deterministic navigation failure: {query}")

    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=_FailingNavigation(),
        materializer=TranscriptEvidenceMaterializer(core.db),
    )
    run = _start(core, "inner-failure")
    _continue(service, run, 0)
    outcome, _ = _continue(service, run, 1)
    assert outcome["phase"] == "stopped"
    state = service.get_inner_state("inner-failure")
    assert state["state"]["answer_status"] == "not_produced"
    assert state["state"]["termination_reason"] == "implementation_error"
    assert state["state"]["failure_class"] == "implementation_failure"
    assert state["state"]["budget"]["synthesis_context_characters"] == 0
    assert state["inner_actions"][-1]["status"] == "failed"
    event = core.research.get_task("inner-failure")["events"][-1]
    assert event["payload"]["failure_class"] == (
        "implementation_failure"
    )


def test_synthesis_context_failure_rolls_back_then_commits_durable_failure_once(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "synthesis-context-failure")
    for index in range(4):
        _continue(core.research_inner, run, index)

    class _FailingContextBuilder:
        def __init__(self) -> None:
            self.calls = 0

        def build(self, **_kwargs):
            self.calls += 1
            raise RuntimeError("sensitive context builder failure")

    builder = _FailingContextBuilder()
    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=core.research_inner.tools,
        materializer=TranscriptEvidenceMaterializer(core.db),
        context_builder=builder,
    )
    before = _research_lengths(core, "synthesis-context-failure")
    result, request = _continue(service, run, 4)
    assert result["phase"] == "stopped"
    assert result["stop_reason"] == "implementation_error"
    assert result["provisional_artifact_id"] is None
    assert builder.calls == 1

    after = _research_lengths(core, "synthesis-context-failure")
    assert after["inner_actions"] == before["inner_actions"] + 1
    assert after["checkpoints"] == before["checkpoints"] + 1
    assert after["events"] == before["events"] + 1
    assert after["command_receipts"] == before["command_receipts"] + 1
    assert after["provisional_artifacts"] == before["provisional_artifacts"]
    state = service.get_inner_state("synthesis-context-failure")
    assert state["state"]["answer_status"] == "not_produced"
    assert state["state"]["termination_reason"] == "implementation_error"
    assert state["state"]["failure_class"] == "implementation_failure"
    assert state["state"]["budget"]["synthesis_context_characters"] == 0
    assert state["inner_actions"][-1]["status"] == "failed"
    assert state["inner_actions"][-1]["error_code"] == (
        "synthesis_implementation_error"
    )

    restarted = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=core.research_inner.tools,
        materializer=TranscriptEvidenceMaterializer(core.db),
        context_builder=builder,
    )
    replay = restarted.continue_run("synthesis-context-failure", request)
    assert replay["checkpoint_id"] == result["checkpoint_id"]
    assert replay["deduplicated"] is True
    assert builder.calls == 1
    assert _research_lengths(core, "synthesis-context-failure") == after
    with pytest.raises(ResearchConflict):
        restarted.continue_run(
            "synthesis-context-failure",
            request.model_copy(update={"expected_checkpoint_id": "forged"}),
        )
    assert builder.calls == 1
    mismatch_after = _research_lengths(core, "synthesis-context-failure")
    assert mismatch_after["events"] == after["events"] + 1
    assert {
        key: value for key, value in mismatch_after.items() if key != "events"
    } == {key: value for key, value in after.items() if key != "events"}


def test_api_validator_failure_returns_controlled_durable_failure_result(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "synthesis-validator-api")
    for index in range(4):
        _continue(core.research_inner, run, index)
    validator_calls = {"count": 0}

    def failing_validator(*_args, **_kwargs):
        validator_calls["count"] += 1
        raise ValueError("sensitive validator failure")

    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=core.research_inner.tools,
        materializer=TranscriptEvidenceMaterializer(core.db),
        grounded_validator=failing_validator,
    )
    core._research_inner = service
    client = TestClient(create_web_app(core))
    payload = {
        "command_id": "synthesis-validator-api:continue",
        "attempt_id": run["attempt_id"],
        "owner_id": run["owner_id"],
        "owner_epoch": run["owner_epoch"],
        "expected_state_version": run["state_version"],
        "expected_checkpoint_id": run["checkpoint_id"],
    }
    response = client.post(
        "/api/research/tasks/synthesis-validator-api/inner/continue",
        json=payload,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"]["phase"] == "stopped"
    assert body["outcome"]["stop_reason"] == "implementation_error"
    assert body["inner"]["state"]["failure_class"] == "implementation_failure"
    assert "sensitive validator failure" not in response.text
    assert validator_calls["count"] == 1
    replay = client.post(
        "/api/research/tasks/synthesis-validator-api/inner/continue",
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json()["outcome"]["deduplicated"] is True
    assert validator_calls["count"] == 1


def test_synthesis_failure_stale_owner_race_cannot_commit_failure_state(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "synthesis-stale-owner", owner="old-owner")
    for index in range(4):
        _continue(core.research_inner, run, index)

    class _FailingContextBuilder:
        def __init__(self) -> None:
            self.calls = 0

        def build(self, **_kwargs):
            self.calls += 1
            raise RuntimeError("late synthesis failure")

    builder = _FailingContextBuilder()

    def takeover_before_failure_commit(point: str) -> None:
        if point != "before_inner_failure_commit":
            return
        with core.db.connect() as connection:
            connection.execute(
                "UPDATE research_tasks SET lease_until=? WHERE task_id=?",
                (
                    (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                    "synthesis-stale-owner",
                ),
            )
        core.research.claim_owner(
            task_id="synthesis-stale-owner",
            command_id="synthesis-stale-owner:takeover",
            owner_id="new-owner",
            expected_state_version=int(run["state_version"]),
            lease_seconds=300,
        )

    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=core.research_inner.tools,
        materializer=TranscriptEvidenceMaterializer(core.db),
        context_builder=builder,
        fault_injector=takeover_before_failure_commit,
    )
    before = _counts(core.db, "synthesis-stale-owner")
    request = ContinueInnerResearchRequest(
        command_id="synthesis-stale-owner:continue",
        attempt_id=str(run["attempt_id"]),
        owner_id="old-owner",
        owner_epoch=int(run["owner_epoch"]),
        expected_state_version=int(run["state_version"]),
        expected_checkpoint_id=str(run["checkpoint_id"]),
    )
    with pytest.raises(ResearchConflict):
        service.continue_run("synthesis-stale-owner", request)
    assert builder.calls == 1
    assert _counts(core.db, "synthesis-stale-owner") == before
    state = core.research.get_task("synthesis-stale-owner")
    assert len(state["inner_actions"]) == 4
    assert not any(
        value["command_id"] == request.command_id
        for value in state["command_receipts"]
    )
    with pytest.raises(ResearchConflict):
        service.continue_run("synthesis-stale-owner", request)
    assert builder.calls == 1


def test_synthesis_simulated_crash_is_not_misclassified_as_failure(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "synthesis-simulated-crash")
    for index in range(4):
        _continue(core.research_inner, run, index)

    class _CrashingContextBuilder:
        def build(self, **_kwargs):
            raise SimulatedCrash("context crash")

    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=core.research_inner.tools,
        materializer=TranscriptEvidenceMaterializer(core.db),
        context_builder=_CrashingContextBuilder(),
    )
    before = _research_lengths(core, "synthesis-simulated-crash")
    with pytest.raises(SimulatedCrash):
        _continue(service, run, 4)
    assert _research_lengths(core, "synthesis-simulated-crash") == before
    state = service.get_inner_state("synthesis-simulated-crash")["state"]
    assert state["phase"] == "provisional_synthesis"
    assert state["termination_reason"] is None
    assert state["failure_class"] == "none"


def test_same_task_retry_attempt_gets_new_use_without_rewriting_identity(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    span = core.research_inner.tools.search(
        "MCP", video_ids=(), query_index=0
    ).spans[0]
    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=DeterministicInnerToolAdapter(search_spans=(span,)),
        materializer=TranscriptEvidenceMaterializer(core.db),
    )
    run = _start(core, "attempt-isolation")
    for index in range(3):
        _continue(service, run, index)
    completed = core.research.complete_attempt(
        task_id="attempt-isolation",
        attempt_id=str(run["attempt_id"]),
        command_id="complete-first-attempt",
        owner_id=str(run["owner_id"]),
        owner_epoch=int(run["owner_epoch"]),
        expected_state_version=int(run["state_version"]),
        answer_status=AnswerStatus.VALID_PARTIAL,
        termination_reason=TerminationReason.NO_NEW_EVIDENCE,
        failure_class=FailureClass.NONE,
        reason_detail="retry fixture",
        task_terminal=False,
        next_task_status=TaskStatus.READY,
        checkpoint_id=str(run["checkpoint_id"]),
    )
    retried = core.research.retry_attempt(
        task_id="attempt-isolation",
        parent_attempt_id=str(run["attempt_id"]),
        command_id="retry-attempt",
        owner_id=str(run["owner_id"]),
        owner_epoch=int(run["owner_epoch"]),
        expected_state_version=int(completed["state_version"]),
    )
    second = {
        **run,
        "attempt_id": str(retried["attempt_id"]),
        "state_version": int(retried["state_version"]),
        "checkpoint_id": None,
    }
    for index in range(3):
        _continue(service, second, index)

    with core.db.connect() as connection:
        identities = int(
            connection.execute(
                "SELECT COUNT(*) FROM research_evidence_identities"
            ).fetchone()[0]
        )
        uses = connection.execute(
            """
            SELECT attempt_id, evidence_id FROM research_evidence_uses
            WHERE task_id='attempt-isolation' ORDER BY created_at
            """
        ).fetchall()
    assert identities == 1
    assert len(uses) == 2
    assert uses[0]["attempt_id"] != uses[1]["attempt_id"]
    assert uses[0]["evidence_id"] == uses[1]["evidence_id"]


def test_api_exposes_durable_inner_continue_and_rejects_provider_mode(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "inner-api")
    client = TestClient(create_web_app(core))
    payload = {
        "command_id": "inner-api-plan",
        "attempt_id": run["attempt_id"],
        "owner_id": run["owner_id"],
        "owner_epoch": run["owner_epoch"],
        "expected_state_version": run["state_version"],
        "expected_checkpoint_id": None,
    }
    response = client.post(
        "/api/research/tasks/inner-api/inner/continue", json=payload
    )
    assert response.status_code == 200
    assert response.json()["outcome"]["phase"] == "navigation"
    status = client.get("/api/research/tasks/inner-api/inner")
    assert status.status_code == 200
    assert status.json()["inner"]["state"]["phase"] == "navigation"

    provider = client.post(
        "/api/research/tasks/inner-api/inner/continue",
        json={
            **payload,
            "command_id": "inner-api-provider",
            "expected_state_version": response.json()["outcome"]["state_version"],
            "expected_checkpoint_id": response.json()["outcome"]["checkpoint_id"],
            "execution_mode": "provider",
        },
    )
    assert provider.status_code == 409
    assert provider.json()["error"]["code"] == "research_unsafe_state"
    assert len(core.research.get_task("inner-api")["inner_actions"]) == 1


def test_terminal_task_cannot_start_inner_run_and_has_no_state_drift(app_paths) -> None:
    core, _ = _fixture_core(app_paths)
    run = _start(core, "inner-terminal")
    completed = core.research.complete_attempt(
        task_id="inner-terminal",
        attempt_id=str(run["attempt_id"]),
        command_id="inner-terminal:complete",
        owner_id=str(run["owner_id"]),
        owner_epoch=int(run["owner_epoch"]),
        expected_state_version=int(run["state_version"]),
        answer_status=AnswerStatus.VALID_INSUFFICIENT,
        termination_reason=TerminationReason.EVIDENCE_UNAVAILABLE,
        failure_class=FailureClass.NONE,
        reason_detail="terminal guard fixture",
        task_terminal=True,
        checkpoint_id=None,
    )
    before = _counts(core.db, "inner-terminal")
    with pytest.raises(ResearchUnsafeState):
        core.research_inner.continue_run(
            "inner-terminal",
            ContinueInnerResearchRequest(
                command_id="inner-terminal:continue",
                attempt_id=str(run["attempt_id"]),
                owner_id=str(run["owner_id"]),
                owner_epoch=int(run["owner_epoch"]),
                expected_state_version=int(completed["state_version"]),
                expected_checkpoint_id=None,
            ),
        )
    assert _counts(core.db, "inner-terminal") == before


def test_concurrent_cross_task_materialization_converges_on_one_identity(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    span = core.research_inner.tools.search(
        "MCP", video_ids=(), query_index=0
    ).spans[0]
    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=DeterministicInnerToolAdapter(search_spans=(span,)),
        materializer=TranscriptEvidenceMaterializer(core.db),
    )
    runs = [_start(core, value) for value in ("concurrent-a", "concurrent-b")]
    for run in runs:
        _continue(service, run, 0)
        _continue(service, run, 1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_continue, service, run, 2)
            for run in runs
        ]
        for future in futures:
            future.result()

    with core.db.connect() as connection:
        identities = connection.execute(
            "SELECT evidence_id, identity_payload_hash FROM research_evidence_identities"
        ).fetchall()
        uses = connection.execute(
            "SELECT task_id, evidence_id FROM research_evidence_uses"
        ).fetchall()
    assert len(identities) == 1
    assert len(uses) == 2
    assert {row["task_id"] for row in uses} == {
        "concurrent-a",
        "concurrent-b",
    }


def test_concurrent_same_command_commits_one_action_checkpoint_and_receipt(
    app_paths,
) -> None:
    core, _ = _fixture_core(app_paths)
    span = core.research_inner.tools.search(
        "MCP", video_ids=(), query_index=0
    ).spans[0]
    adapter = DeterministicInnerToolAdapter(search_spans=(span,))
    service = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=adapter,
        materializer=TranscriptEvidenceMaterializer(core.db),
    )
    run = _start(core, "same-command")
    _continue(service, run, 0)
    _continue(service, run, 1)
    request = ContinueInnerResearchRequest(
        command_id="same-command:search",
        attempt_id=str(run["attempt_id"]),
        owner_id=str(run["owner_id"]),
        owner_epoch=int(run["owner_epoch"]),
        expected_state_version=int(run["state_version"]),
        expected_checkpoint_id=str(run["checkpoint_id"]),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _index: service.continue_run("same-command", request),
                range(2),
            )
        )
    assert results[0]["checkpoint_id"] == results[1]["checkpoint_id"]
    assert sorted(value["deduplicated"] for value in results) == [False, True]
    state = core.research.get_task("same-command")
    assert len(state["inner_actions"]) == 3
    inner_receipts = [
        value
        for value in state["command_receipts"]
        if value["command_id"] == "same-command:search"
    ]
    assert len(inner_receipts) == 1


def test_live_db_sentinel_is_not_touched_by_stage2_temp_migration(app_paths) -> None:
    sentinel = app_paths.state_dir / "live-db-sentinel"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_bytes(b"unchanged")
    before = (
        sentinel.stat().st_mtime_ns,
        hashlib.sha256(sentinel.read_bytes()).hexdigest(),
    )
    Database(app_paths.database).initialize()
    after = (
        sentinel.stat().st_mtime_ns,
        hashlib.sha256(sentinel.read_bytes()).hexdigest(),
    )
    assert after == before
