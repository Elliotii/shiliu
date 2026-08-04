from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.db import Database, SCHEMA_VERSION
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.research.errors import (
    ResearchConflict,
    ResearchUnsafeState,
    ResearchValidationError,
    SimulatedCrash,
)
from shiliu.research.inner_contracts import ContinueInnerResearchRequest
from shiliu.research.outer_contracts import (
    AdvanceOuterResearchRequest,
    RegisteredConstraintEvaluator,
)
from shiliu.research.outer_service import OuterResearchService
from shiliu.retrieval.coordinator import SYNC_STATE_VERSION
from shiliu.web import create_web_app


STAGE3_TABLES = {
    "research_constraint_specs",
    "research_audit_candidates",
    "research_constraint_audit_observations",
    "research_outer_audits",
    "research_compact_improvement_states",
    "research_continuation_decisions",
    "research_continuation_seeds",
    "research_outer_result_links",
}

OBJECTIVE_TEXT = "生成一份包含当前可重建引用的研究回答"
CONSTRAINT_TEXT = "至少包含一条当前可重建证据"


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime.now(timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def _fixture_core(app_paths):
    core = Application(app_paths)
    source_id = core.db.create_favorite_source(
        folder_id=1303, folder_title="Stage 3 Fixture"
    )
    item = FavoriteItem(
        bvid="BVSTAGE30001",
        title="Durable outer audit",
        uploader="Stage3",
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
                {
                    "from": index * 5,
                    "to": index * 5 + 4,
                    "content": text,
                }
            )
            for index, text in enumerate(
                (
                    OBJECTIVE_TEXT,
                    CONSTRAINT_TEXT,
                    "研究持久证据并判断月球构成",
                    "只有确定性 evaluator 可以通过 gate。",
                    "可恢复缺口创建带 lineage 的子 Attempt。",
                    "预算耗尽必须形成持久停止。",
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


def _policy(*, constraint_kind: str = "minimum_current_evidence", minimum: int = 1):
    return {
        "authority": "live_current_exact_replay",
        "outer_audit": {
            "objective": {"kind": "grounded_answer"},
            "constraints": [
                {"kind": constraint_kind, "minimum": minimum}
            ],
        },
    }


def _registered_evaluators(
    *, minimum: int = 1
) -> tuple[RegisteredConstraintEvaluator, ...]:
    return (
        RegisteredConstraintEvaluator(
            registration_id="stage3-test-grounded-objective",
            constraint_scope="objective",
            exact_text=OBJECTIVE_TEXT,
            evaluator_kind="grounded_answer",
            evaluator_policy_version="stage3-test-evaluator-v1",
        ),
        RegisteredConstraintEvaluator(
            registration_id="stage3-test-evidence-count",
            constraint_scope="success_constraint",
            exact_text=CONSTRAINT_TEXT,
            evaluator_kind="minimum_current_evidence",
            evaluator_policy_version="stage3-test-evaluator-v1",
            parameters={"minimum": minimum},
        ),
    )


def _start(
    core: Application,
    task_id: str,
    *,
    policy=None,
    owner="worker",
    registered=True,
    registry_minimum=1,
    objective=OBJECTIVE_TEXT,
    success_constraints=None,
):
    if registered:
        core._research_outer = OuterResearchService(
            db=core.db,
            kernel=core.research,
            registered_evaluators=_registered_evaluators(
                minimum=registry_minimum
            ),
        )
    core.research.create_task(
        command_id=f"create:{task_id}",
        task_id=task_id,
        objective=objective,
        success_constraints=(
            list(success_constraints)
            if success_constraints is not None
            else [CONSTRAINT_TEXT]
        ),
        evidence_policy=policy if policy is not None else _policy(),
    )
    claim = core.research.claim_owner(
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
        owner_epoch=int(claim["owner_epoch"]),
        expected_state_version=1,
    )
    return {
        "task_id": task_id,
        "attempt_id": str(started["attempt_id"]),
        "owner_id": owner,
        "owner_epoch": int(claim["owner_epoch"]),
        "state_version": 2,
        "checkpoint_id": None,
    }


def _finish_inner(core: Application, run: dict[str, object]) -> None:
    for index in range(5):
        outcome = core.research_inner.continue_run(
            str(run["task_id"]),
            ContinueInnerResearchRequest(
                command_id=f"inner:{run['task_id']}:{run['attempt_id']}:{index}",
                attempt_id=str(run["attempt_id"]),
                owner_id=str(run["owner_id"]),
                owner_epoch=int(run["owner_epoch"]),
                expected_state_version=int(run["state_version"]),
                expected_checkpoint_id=(
                    str(run["checkpoint_id"]) if run["checkpoint_id"] else None
                ),
            ),
        )
        run["state_version"] = int(outcome["state_version"])
        run["checkpoint_id"] = str(outcome["checkpoint_id"])
    assert outcome["phase"] == "complete"


def _outer_request(run: dict[str, object], command_id: str, **values):
    return AdvanceOuterResearchRequest(
        command_id=command_id,
        attempt_id=str(run["attempt_id"]),
        owner_id=str(run["owner_id"]),
        owner_epoch=int(run["owner_epoch"]),
        expected_state_version=int(run["state_version"]),
        expected_checkpoint_id=str(run["checkpoint_id"]),
        **values,
    )


def _counts(core: Application, task_id: str) -> dict[str, int]:
    with core.db.connect() as connection:
        return {
            table: int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE task_id=?",  # noqa: S608
                    (task_id,),
                ).fetchone()[0]
            )
            for table in STAGE3_TABLES
        }


def test_schema_9_migrates_old_result_enum_and_adds_stage3_tables(app_paths) -> None:
    app_paths.database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(app_paths.database)
    connection.executescript(
        """
        CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '8');
        CREATE TABLE research_results(
            result_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, goal_id TEXT NOT NULL,
            attempt_id TEXT, checkpoint_id TEXT, answer_status TEXT NOT NULL,
            termination_reason TEXT NOT NULL CHECK (
                termination_reason IN ('answer_ready', 'implementation_error')
            ),
            failure_class TEXT NOT NULL, reason_detail TEXT NOT NULL,
            is_task_terminal INTEGER NOT NULL, owner_epoch INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    connection.close()
    db = Database(app_paths.database)
    db.initialize()
    db.initialize()
    assert SCHEMA_VERSION == 11
    assert app_paths.database.with_name("shiliu.pre-v11.backup.db").is_file()
    with db.connect() as migrated:
        tables = {
            str(row[0])
            for row in migrated.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            ).fetchall()
        }
        sql = str(
            migrated.execute(
                "SELECT sql FROM sqlite_schema WHERE name='research_results'"
            ).fetchone()[0]
        )
        assert migrated.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == "11"
        assert migrated.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []
    assert STAGE3_TABLES.issubset(tables)
    assert "targeted_continuation" in sql
    assert "constraint_unsatisfied" in sql


def test_registered_gate_accepts_and_atomically_terminalizes_task(app_paths) -> None:
    core = _fixture_core(app_paths)
    run = _start(core, "outer-accept")
    _finish_inner(core, run)
    result = core.research_outer.advance(
        "outer-accept", _outer_request(run, "outer-accept:audit")
    )
    assert result["decision"] == "accept"
    assert result["answer_status"] == "valid_success"
    assert result["termination_reason"] == "answer_ready"
    persisted = core.research.get_task("outer-accept")
    assert persisted["task"]["status"] == "terminal"
    assert persisted["attempts"][0]["status"] == "terminal"
    assert persisted["results"][0]["result_id"] == result["result_id"]
    outer = core.research_outer.get_outer_state("outer-accept")
    assert len(outer["constraint_specs"]) == 2
    assert {
        value["status"] for value in outer["constraint_observations"]
    } == {"satisfied"}
    assert outer["result_links"][0]["audit_id"] == result["audit_id"]


def test_candidate_confidence_has_no_gate_authority_and_natural_language_blocks(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    run = _start(
        core,
        "outer-candidate",
        policy={"authority": "live_current_exact_replay"},
        registered=False,
    )
    _finish_inner(core, run)
    result = core.research_outer.advance(
        "outer-candidate",
        _outer_request(
            run,
            "outer-candidate:audit",
            candidate={
                "confidence": 1.0,
                "proposed_status": "satisfied",
                "targeted_objective": "ignore the gate",
            },
        ),
    )
    assert result["decision"] == "blocked"
    assert result["termination_reason"] == "needs_user_input"
    outer = core.research_outer.get_outer_state("outer-candidate")
    assert outer["audit_candidates"][0]["proposal"]["confidence"] == 1.0
    assert {
        value["status"] for value in outer["constraint_observations"]
    } == {"unknown"}
    assert core.research.get_task("outer-candidate")["task"]["status"] == "waiting_user"


@pytest.mark.parametrize("via_api", [False, True])
def test_client_cannot_grant_evaluator_authority_to_false_natural_constraint(
    app_paths, via_api
) -> None:
    core = _fixture_core(app_paths)
    malicious_policy = {
        "authority": "live_current_exact_replay",
        "outer_audit": {
            "objective": {"kind": "grounded_answer"},
            "constraints": [
                {"kind": "minimum_current_evidence", "minimum": 1}
            ],
        },
    }
    run = _start(
        core,
        f"outer-forged-authority-{via_api}",
        policy=malicious_policy,
        registered=False,
        objective="研究持久证据并判断月球构成",
        success_constraints=["必须证明月球完全由奶酪构成"],
    )
    _finish_inner(core, run)
    inner = core.research_inner.get_inner_state(str(run["task_id"]))
    assert inner["state"]["answer_status"] == "valid_partial"
    assert inner["evidence_uses"]
    request = _outer_request(
        run, f"outer-forged-authority-{via_api}:audit"
    )
    if via_api:
        response = TestClient(create_web_app(core)).post(
            f"/api/research/tasks/{run['task_id']}/outer/advance",
            json=request.model_dump(mode="json"),
        )
        assert response.status_code == 200
        result = response.json()["outcome"]
    else:
        result = core.research_outer.advance(str(run["task_id"]), request)
    assert result["decision"] == "blocked"
    assert result["answer_status"] != "valid_success"
    assert result["termination_reason"] == "needs_user_input"
    persisted = core.research.get_task(str(run["task_id"]))
    assert persisted["task"]["status"] == "waiting_user"
    assert persisted["task"]["terminal_result_id"] is None
    outer = core.research_outer.get_outer_state(str(run["task_id"]))
    assert {
        value["constraint_kind"] for value in outer["constraint_specs"]
    } == {"natural_language"}
    assert {
        value["evaluator_policy"]["authority"]
        for value in outer["constraint_specs"]
    } == {"unregistered_natural_language"}
    assert {
        value["status"] for value in outer["constraint_observations"]
    } == {"unknown"}


def test_recoverable_gap_atomically_creates_retry_child_seed_and_scoped_uses(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    run = _start(
        core,
        "outer-continue",
        policy=_policy(minimum=99),
        registry_minimum=99,
    )
    _finish_inner(core, run)
    parent_use_ids = {
        value["evidence_use_id"]
        for value in core.research.get_task("outer-continue")["evidence_uses"]
    }
    result = core.research_outer.advance(
        "outer-continue", _outer_request(run, "outer-continue:audit")
    )
    assert result["decision"] == "targeted_continue"
    assert result["termination_reason"] == "targeted_continuation"
    assert result["child_attempt_id"] != run["attempt_id"]
    persisted = core.research.get_task("outer-continue")
    assert persisted["task"]["status"] == "running"
    assert [value["status"] for value in persisted["attempts"]] == [
        "terminal",
        "running",
    ]
    child = persisted["attempts"][1]
    assert child["cause"] == "retry"
    assert child["parent_attempt_id"] == run["attempt_id"]
    assert child["source_checkpoint_id"] == result["checkpoint_id"]
    assert persisted["results"][0]["is_task_terminal"] is False
    assert persisted["results"][0]["termination_reason"] == "targeted_continuation"
    outer = core.research_outer.get_outer_state("outer-continue")
    seed = outer["continuation_seeds"][0]
    assert seed["child_attempt_id"] == child["attempt_id"]
    assert seed["targeted_objective"].startswith("Resolve constraint")
    child_uses = {
        value["evidence_use_id"]
        for value in persisted["evidence_uses"]
        if value["attempt_id"] == child["attempt_id"]
    }
    assert child_uses
    assert child_uses.isdisjoint(parent_use_ids)
    assert {
        value["evidence_id"]
        for value in persisted["evidence_uses"]
        if value["attempt_id"] == child["attempt_id"]
    } == {
        value["evidence_id"]
        for value in persisted["evidence_uses"]
        if value["attempt_id"] == run["attempt_id"]
    }
    child_inner = core.research_inner.get_inner_state("outer-continue")["state"]
    assert child_inner["attempt_id"] == child["attempt_id"]
    assert child_inner["open_questions"] == [seed["targeted_objective"]]


def test_replay_is_exactly_once_and_payload_mismatch_fails_closed(app_paths) -> None:
    core = _fixture_core(app_paths)
    run = _start(core, "outer-replay")
    _finish_inner(core, run)
    request = _outer_request(run, "outer-replay:audit")
    first = core.research_outer.advance("outer-replay", request)
    before = _counts(core, "outer-replay")
    replay = core.research_outer.advance("outer-replay", request)
    assert replay["deduplicated"] is True
    assert replay["audit_id"] == first["audit_id"]
    assert _counts(core, "outer-replay") == before
    mismatched_payload = request.model_dump(mode="json")
    mismatched_payload["candidate"] = {"gap": "changed"}
    with pytest.raises(ResearchConflict):
        core.research_outer.advance(
            "outer-replay",
            AdvanceOuterResearchRequest.model_validate(mismatched_payload),
        )
    assert _counts(core, "outer-replay") == before


@pytest.mark.parametrize(
    "fault_point",
    [
        "after_outer_currentness_observations_insert",
        "after_outer_audit_insert",
        "after_constraint_observations_insert",
        "after_improvement_state_insert",
        "after_outer_checkpoint_insert",
        "after_outer_parent_result_insert",
        "after_outer_child_attempt_insert",
        "after_outer_continuation_seed_insert",
        "after_outer_event_insert",
        "after_outer_receipt_insert",
    ],
)
def test_continuation_fault_points_roll_back_every_stage3_write(
    app_paths, fault_point
) -> None:
    core = _fixture_core(app_paths)
    task_id = f"fault-{fault_point}"
    run = _start(
        core,
        task_id,
        policy=_policy(minimum=99),
        registry_minimum=99,
    )
    _finish_inner(core, run)
    before = _counts(core, task_id)

    def inject(point: str) -> None:
        if point == fault_point:
            raise SimulatedCrash(point)

    service = OuterResearchService(
        db=core.db,
        kernel=core.research,
        fault_injector=inject,
        registered_evaluators=_registered_evaluators(minimum=99),
    )
    with pytest.raises(SimulatedCrash):
        service.advance(task_id, _outer_request(run, f"{task_id}:audit"))
    assert _counts(core, task_id) == before
    persisted = core.research.get_task(task_id)
    assert persisted["task"]["state_version"] == run["state_version"]
    assert persisted["attempts"][0]["status"] == "running"
    assert not any(
        value["command_id"] == f"{task_id}:audit"
        for value in persisted["command_receipts"]
    )


def test_stale_owner_and_unresolved_side_effect_have_no_outer_drift(app_paths) -> None:
    core = _fixture_core(app_paths)
    run = _start(
        core,
        "outer-fences",
        policy=_policy(minimum=99),
        registry_minimum=99,
    )
    _finish_inner(core, run)
    before = _counts(core, "outer-fences")
    with pytest.raises(ResearchConflict):
        core.research_outer.advance(
            "outer-fences",
            _outer_request(run, "outer-fences:stale").model_copy(
                update={"owner_epoch": int(run["owner_epoch"]) + 1}
            ),
        )
    assert _counts(core, "outer-fences") == before
    reserved = core.research.reserve_side_effect(
        task_id="outer-fences",
        attempt_id=str(run["attempt_id"]),
        command_id="outer-fences:reserve",
        owner_id=str(run["owner_id"]),
        owner_epoch=int(run["owner_epoch"]),
        expected_state_version=int(run["state_version"]),
        effect_kind="outer_candidate",
        idempotency_key="candidate-1",
        request_payload={"x": 1},
    )
    transitioned = core.research.transition_side_effect(
        task_id="outer-fences",
        side_effect_id=core.research.get_task("outer-fences")["side_effects"][0][
            "side_effect_id"
        ],
        command_id="outer-fences:in-flight",
        owner_id=str(run["owner_id"]),
        owner_epoch=int(run["owner_epoch"]),
        expected_state_version=int(reserved["state_version"]),
        target_status="in_flight",
    )
    run["state_version"] = int(transitioned["state_version"])
    with pytest.raises(ResearchUnsafeState):
        core.research_outer.advance(
            "outer-fences", _outer_request(run, "outer-fences:audit")
        )
    assert _counts(core, "outer-fences") == before


def test_concurrent_same_command_produces_one_audit_and_result(app_paths) -> None:
    core = _fixture_core(app_paths)
    run = _start(core, "outer-race")
    _finish_inner(core, run)
    request = _outer_request(run, "outer-race:audit")
    with ThreadPoolExecutor(max_workers=2) as executor:
        values = list(
            executor.map(
                lambda _: core.research_outer.advance("outer-race", request),
                range(2),
            )
        )
    assert {value["audit_id"] for value in values} == {values[0]["audit_id"]}
    assert sum(bool(value["deduplicated"]) for value in values) == 1
    outer = core.research_outer.get_outer_state("outer-race")
    assert len(outer["outer_audits"]) == 1
    assert len(outer["result_links"]) == 1


def test_api_exposes_outer_advance_status_and_rejects_provider(app_paths) -> None:
    core = _fixture_core(app_paths)
    run = _start(core, "outer-api")
    _finish_inner(core, run)
    client = TestClient(create_web_app(core))
    provider_payload = _outer_request(
        run, "outer-api:provider", execution_mode="provider"
    ).model_dump(mode="json")
    denied = client.post(
        "/api/research/tasks/outer-api/outer/advance", json=provider_payload
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "research_unsafe_state"
    response = client.post(
        "/api/research/tasks/outer-api/outer/advance",
        json=_outer_request(run, "outer-api:audit").model_dump(mode="json"),
    )
    assert response.status_code == 200
    assert response.json()["outcome"]["decision"] == "accept"
    status = client.get("/api/research/tasks/outer-api/outer")
    assert status.status_code == 200
    assert status.json()["outer"]["state"]["phase"] == "accepted"


def test_source_drift_appends_invalid_observation_without_rewriting_identity(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    run = _start(core, "outer-stale")
    _finish_inner(core, run)
    before = core.research.get_task("outer-stale")
    evidence_id = before["evidence_uses"][0]["evidence_id"]
    identity_before = None
    with core.db.connect() as connection:
        identity_before = dict(
            connection.execute(
                "SELECT * FROM research_evidence_identities WHERE evidence_id=?",
                (evidence_id,),
            ).fetchone()
        )
        video_id = int(identity_before["video_id"])
        connection.execute(
            "UPDATE videos SET raw_subtitle_path=?, updated_at=? WHERE id=?",
            (
                str(app_paths.content_dir / "missing-stage3-source.json"),
                "2099-01-01T00:00:00+00:00",
                video_id,
            ),
        )
    outcome = core.research_outer.advance(
        "outer-stale", _outer_request(run, "outer-stale:audit")
    )
    assert outcome["decision"] in {"stop_partial", "stop_insufficient"}
    assert outcome["termination_reason"] == "evidence_unavailable"
    with core.db.connect() as connection:
        identity_after = dict(
            connection.execute(
                "SELECT * FROM research_evidence_identities WHERE evidence_id=?",
                (evidence_id,),
            ).fetchone()
        )
        observations = connection.execute(
            """
            SELECT outcome FROM research_evidence_validations
            WHERE task_id='outer-stale' ORDER BY observed_at
            """
        ).fetchall()
    assert identity_after == identity_before
    assert observations[-1]["outcome"] in {"stale", "missing"}


def test_outer_budget_is_aggregate_and_repeated_target_stops_after_child(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    run = _start(
        core,
        "outer-repeat",
        policy=_policy(minimum=99),
        registry_minimum=99,
    )
    _finish_inner(core, run)
    first = core.research_outer.advance(
        "outer-repeat", _outer_request(run, "outer-repeat:audit-1")
    )
    child = {
        **run,
        "attempt_id": str(first["child_attempt_id"]),
        "state_version": int(first["state_version"]),
    }
    child_state = core.research_inner.get_inner_state("outer-repeat")["state"]
    child["checkpoint_id"] = child_state["last_complete_checkpoint_id"]
    _finish_inner(core, child)
    second = core.research_outer.advance(
        "outer-repeat", _outer_request(child, "outer-repeat:audit-2")
    )
    assert second["decision"] in {"stop_partial", "stop_insufficient"}
    assert second["termination_reason"] == "no_new_evidence"
    outer = core.research_outer.get_outer_state("outer-repeat")
    first_budget = outer["outer_audits"][0]["budget_after"]
    second_budget = outer["outer_audits"][1]["budget_after"]
    assert first_budget["outer_audits"] == 1
    assert second_budget["outer_audits"] == 2
    assert second_budget["total_inner_actions"] > first_budget["total_inner_actions"]
    assert len(outer["constraint_specs"]) == 2
    assert core.research.get_task("outer-repeat")["task"]["status"] == "terminal"


@pytest.mark.parametrize(
    ("dimension", "attribute", "limit"),
    [
        ("runtime", "MAX_RUNTIME_SECONDS", 0),
        ("total_evidence_uses", "MAX_TOTAL_EVIDENCE_USES", 1),
        ("outer_context_characters", "MAX_OUTER_CONTEXT_CHARACTERS", 1),
    ],
)
def test_outer_hard_budget_prevents_child_and_commits_honest_terminal_stop(
    app_paths, dimension, attribute, limit
) -> None:
    core = _fixture_core(app_paths)
    task_id = f"outer-budget-{dimension}"
    run = _start(
        core,
        task_id,
        policy=_policy(minimum=99),
        registry_minimum=99,
    )
    _finish_inner(core, run)
    service = OuterResearchService(
        db=core.db,
        kernel=core.research,
        registered_evaluators=_registered_evaluators(minimum=99),
    )
    setattr(service, attribute, limit)
    result = service.advance(
        task_id, _outer_request(run, f"{task_id}:audit")
    )
    assert result["decision"] in {"stop_partial", "stop_insufficient"}
    assert result["termination_reason"] == "budget_exhausted"
    persisted = core.research.get_task(task_id)
    assert persisted["task"]["status"] == "terminal"
    assert len(persisted["attempts"]) == 1
    outer = service.get_outer_state(task_id)
    assert outer["outer_audits"][0]["blocker"] == "budget_exhausted"
    assert outer["outer_audits"][0]["reason_codes"] == [
        f"outer_budget:{dimension}"
    ]


@pytest.mark.parametrize("via_api", [False, True])
def test_accept_path_context_overflow_durably_stops_before_gate(
    app_paths, via_api
) -> None:
    core = _fixture_core(app_paths)
    task_id = f"outer-accept-context-{via_api}"
    run = _start(core, task_id)
    _finish_inner(core, run)
    service = OuterResearchService(
        db=core.db,
        kernel=core.research,
        registered_evaluators=_registered_evaluators(),
    )
    service.MAX_OUTER_CONTEXT_CHARACTERS = 1
    core._research_outer = service
    request = _outer_request(run, f"{task_id}:audit")
    if via_api:
        response = TestClient(create_web_app(core)).post(
            f"/api/research/tasks/{task_id}/outer/advance",
            json=request.model_dump(mode="json"),
        )
        assert response.status_code == 200
        result = response.json()["outcome"]
    else:
        result = service.advance(task_id, request)
    assert result["decision"] in {"stop_partial", "stop_insufficient"}
    assert result["termination_reason"] == "budget_exhausted"
    assert result["answer_status"] != "valid_success"
    persisted = core.research.get_task(task_id)
    assert persisted["task"]["status"] == "terminal"
    outer = service.get_outer_state(task_id)
    audit = outer["outer_audits"][0]
    assert audit["blocker"] == "budget_exhausted"
    assert audit["reason_codes"] == [
        "outer_budget:outer_context_characters"
    ]
    assert audit["budget_after"]["outer_context_characters"] == 0
    assert outer["audit_candidates"] == []
    replay = service.advance(task_id, request)
    assert replay["deduplicated"] is True
    assert replay["audit_id"] == result["audit_id"]


def test_context_overflow_stop_preserves_takeover_fence(app_paths) -> None:
    core = _fixture_core(app_paths)
    task_id = "outer-context-takeover"
    run = _start(core, task_id)
    _finish_inner(core, run)
    stale_request = _outer_request(run, f"{task_id}:stale-audit")
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE research_tasks SET lease_until=? WHERE task_id=?",
            (
                (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                task_id,
            ),
        )
    takeover = core.research.claim_owner(
        task_id=task_id,
        command_id=f"{task_id}:takeover",
        owner_id="new-owner",
        expected_state_version=int(run["state_version"]),
        lease_seconds=300,
    )
    service = OuterResearchService(
        db=core.db,
        kernel=core.research,
        registered_evaluators=_registered_evaluators(),
    )
    service.MAX_OUTER_CONTEXT_CHARACTERS = 1
    before = _counts(core, task_id)
    with pytest.raises(ResearchConflict):
        service.advance(task_id, stale_request)
    assert _counts(core, task_id) == before
    current_request = stale_request.model_copy(
        update={
            "command_id": f"{task_id}:current-audit",
            "owner_id": "new-owner",
            "owner_epoch": int(takeover["owner_epoch"]),
            "expected_state_version": int(takeover["state_version"]),
        }
    )
    stopped = service.advance(task_id, current_request)
    assert stopped["termination_reason"] == "budget_exhausted"
    assert service.get_outer_state(task_id)["outer_audits"][0][
        "owner_epoch"
    ] == takeover["owner_epoch"]


def test_context_overflow_stop_fault_rolls_back_then_retries_once(app_paths) -> None:
    core = _fixture_core(app_paths)
    task_id = "outer-context-fault"
    run = _start(core, task_id)
    _finish_inner(core, run)
    request = _outer_request(run, f"{task_id}:audit")

    def inject(point: str) -> None:
        if point == "after_outer_receipt_insert":
            raise SimulatedCrash(point)

    crashing = OuterResearchService(
        db=core.db,
        kernel=core.research,
        registered_evaluators=_registered_evaluators(),
        fault_injector=inject,
    )
    crashing.MAX_OUTER_CONTEXT_CHARACTERS = 1
    before = _counts(core, task_id)
    receipts_before = len(
        core.research.get_task(task_id)["command_receipts"]
    )
    with pytest.raises(SimulatedCrash):
        crashing.advance(task_id, request)
    assert _counts(core, task_id) == before
    assert (
        len(core.research.get_task(task_id)["command_receipts"])
        == receipts_before
    )
    assert core.research.get_task(task_id)["task"]["status"] == "running"

    restarted = OuterResearchService(
        db=core.db,
        kernel=core.research,
        registered_evaluators=_registered_evaluators(),
    )
    restarted.MAX_OUTER_CONTEXT_CHARACTERS = 1
    stopped = restarted.advance(task_id, request)
    assert stopped["termination_reason"] == "budget_exhausted"
    replay = restarted.advance(task_id, request)
    assert replay["deduplicated"] is True
    assert replay["audit_id"] == stopped["audit_id"]


@pytest.mark.parametrize("via_api", [False, True])
def test_oversized_candidate_fails_closed_before_any_persistence(
    app_paths, via_api
) -> None:
    core = _fixture_core(app_paths)
    task_id = f"outer-candidate-size-{via_api}"
    run = _start(core, task_id)
    _finish_inner(core, run)
    candidate = {
        "evidence_refs": [f"{index:02d}" + "e" * 126 for index in range(24)],
        "reason_codes": [f"{index:02d}" + "r" * 98 for index in range(16)],
        "gap": "g" * 500,
        "targeted_objective": "t" * 500,
        "confidence": 0.5,
    }
    request = _outer_request(
        run,
        f"{task_id}:audit",
        candidate=candidate,
    )
    before = _counts(core, task_id)
    receipts_before = len(
        core.research.get_task(task_id)["command_receipts"]
    )
    if via_api:
        response = TestClient(create_web_app(core)).post(
            f"/api/research/tasks/{task_id}/outer/advance",
            json=request.model_dump(mode="json"),
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "research_validation_error"
    else:
        with pytest.raises(ResearchValidationError):
            core.research_outer.advance(task_id, request)
    assert _counts(core, task_id) == before
    assert (
        len(core.research.get_task(task_id)["command_receipts"])
        == receipts_before
    )
    assert core.research.get_task(task_id)["task"]["status"] == "running"


def test_takeover_fences_old_owner_and_new_owner_reuses_same_lineage(app_paths) -> None:
    core = _fixture_core(app_paths)
    run = _start(core, "outer-takeover", policy=_policy())
    _finish_inner(core, run)
    old_request = _outer_request(run, "outer-takeover:old-audit")
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE research_tasks SET lease_until=? WHERE task_id=?",
            (
                (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                "outer-takeover",
            ),
        )
    takeover = core.research.claim_owner(
        task_id="outer-takeover",
        command_id="outer-takeover:claim-new",
        owner_id="new-owner",
        expected_state_version=int(run["state_version"]),
        lease_seconds=300,
    )
    before = _counts(core, "outer-takeover")
    with pytest.raises(ResearchConflict):
        core.research_outer.advance("outer-takeover", old_request)
    assert _counts(core, "outer-takeover") == before
    new_request = old_request.model_copy(
        update={
            "command_id": "outer-takeover:new-audit",
            "owner_id": "new-owner",
            "owner_epoch": int(takeover["owner_epoch"]),
            "expected_state_version": int(takeover["state_version"]),
        }
    )
    accepted = core.research_outer.advance("outer-takeover", new_request)
    assert accepted["decision"] == "accept"
    outer = core.research_outer.get_outer_state("outer-takeover")
    assert outer["outer_audits"][0]["owner_epoch"] == takeover["owner_epoch"]


def test_optional_unknown_constraint_does_not_block_required_gate(app_paths) -> None:
    core = _fixture_core(app_paths)
    policy = {
        "authority": "live_current_exact_replay",
        "outer_audit": {
            "objective": {"kind": "grounded_answer"},
            "constraints": [
                {"kind": "natural_language", "required": False}
            ],
        },
    }
    run = _start(
        core,
        "outer-optional",
        policy=policy,
        registered=False,
    )
    core._research_outer = OuterResearchService(
        db=core.db,
        kernel=core.research,
        registered_evaluators=(
            _registered_evaluators()[0],
            RegisteredConstraintEvaluator(
                registration_id="stage3-test-optional-natural-language",
                constraint_scope="success_constraint",
                exact_text=CONSTRAINT_TEXT,
                evaluator_kind="natural_language",
                evaluator_policy_version="stage3-test-evaluator-v1",
                required=False,
            ),
        ),
    )
    _finish_inner(core, run)
    result = core.research_outer.advance(
        "outer-optional", _outer_request(run, "outer-optional:audit")
    )
    assert result["decision"] == "accept"
    observations = core.research_outer.get_outer_state("outer-optional")[
        "constraint_observations"
    ]
    assert [value["status"] for value in observations] == [
        "satisfied",
        "unknown",
    ]


def test_internal_evaluator_failure_rolls_back_then_commits_fenced_failure_once(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    run = _start(core, "outer-implementation-failure")
    _finish_inner(core, run)

    class FailingAuthority:
        def __init__(self) -> None:
            self.calls = 0

        def observe(self, _identity):
            self.calls += 1
            raise RuntimeError("sensitive outer validator details")

    authority = FailingAuthority()
    service = OuterResearchService(
        db=core.db,
        kernel=core.research,
        authority=authority,  # type: ignore[arg-type]
    )
    request = _outer_request(
        run, "outer-implementation-failure:audit"
    )
    first = service.advance("outer-implementation-failure", request)
    assert first["termination_reason"] == "implementation_error"
    assert first["failure_class"] == "implementation_failure"
    assert "sensitive" not in json.dumps(first)
    assert authority.calls == 1
    replay = service.advance("outer-implementation-failure", request)
    assert replay["deduplicated"] is True
    assert replay["audit_id"] == first["audit_id"]
    assert authority.calls == 1
    persisted = core.research.get_task("outer-implementation-failure")
    assert persisted["task"]["status"] == "blocked"
    assert persisted["attempts"][0]["status"] == "blocked"
    outer = service.get_outer_state("outer-implementation-failure")
    assert outer["outer_audits"][0]["outcome"] == "failed"
    assert outer["state"]["phase"] == "failed"


def test_simulated_crash_is_not_misclassified_as_implementation_failure(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    run = _start(core, "outer-simulated-crash")
    _finish_inner(core, run)

    class CrashingAuthority:
        def observe(self, _identity):
            raise SimulatedCrash("outer crash")

    service = OuterResearchService(
        db=core.db,
        kernel=core.research,
        authority=CrashingAuthority(),  # type: ignore[arg-type]
    )
    before = _counts(core, "outer-simulated-crash")
    with pytest.raises(SimulatedCrash):
        service.advance(
            "outer-simulated-crash",
            _outer_request(run, "outer-simulated-crash:audit"),
        )
    assert _counts(core, "outer-simulated-crash") == before
    assert core.research.get_task("outer-simulated-crash")["task"]["status"] == "running"


def test_takeover_between_internal_failure_and_failure_commit_fences_old_owner(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    run = _start(core, "outer-failure-race", owner="old-owner")
    _finish_inner(core, run)

    class FailingAuthority:
        def observe(self, _identity):
            raise RuntimeError("late failure")

    class RacingService(OuterResearchService):
        def _commit_implementation_failure(self, **kwargs):
            with core.db.connect() as connection:
                connection.execute(
                    "UPDATE research_tasks SET lease_until=? WHERE task_id=?",
                    (
                        (
                            datetime.now(timezone.utc) - timedelta(seconds=1)
                        ).isoformat(),
                        "outer-failure-race",
                    ),
                )
            core.research.claim_owner(
                task_id="outer-failure-race",
                command_id="outer-failure-race:takeover",
                owner_id="new-owner",
                expected_state_version=int(run["state_version"]),
                lease_seconds=300,
            )
            return super()._commit_implementation_failure(**kwargs)

    service = RacingService(
        db=core.db,
        kernel=core.research,
        authority=FailingAuthority(),  # type: ignore[arg-type]
    )
    before = _counts(core, "outer-failure-race")
    with pytest.raises(ResearchConflict):
        service.advance(
            "outer-failure-race",
            _outer_request(run, "outer-failure-race:audit"),
        )
    assert _counts(core, "outer-failure-race") == before
    persisted = core.research.get_task("outer-failure-race")
    assert persisted["task"]["owner_id"] == "new-owner"
    assert persisted["attempts"][0]["status"] == "running"
