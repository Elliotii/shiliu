from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.research.control_contracts import ControlCommandRequest, HumanDecisionRequest
from shiliu.research.errors import ResearchConflict, SimulatedCrash
from shiliu.research.outer_contracts import RegisteredConstraintEvaluator
from shiliu.research.outer_service import OuterResearchService
from shiliu.research.product_contracts import (
    CreateProductResearchRequest,
    RunProductResearchRequest,
)
from shiliu.research.product_service import (
    CANDIDATE_DELTA_SCHEMA_VERSION,
    DELTA_KINDS,
    ResearchProductService,
)
from shiliu.retrieval.coordinator import SYNC_STATE_VERSION
from shiliu.web import create_web_app


OBJECTIVE = "MCP"
CONSTRAINT = "至少有一条当前字幕证据"


def _fixture_core(app_paths: object, *, registered: bool = False) -> Application:
    core = Application(app_paths)
    source_db_id = core.db.create_favorite_source(
        folder_id=1505, folder_title="Stage 5 Fixture"
    )
    item = FavoriteItem(
        bvid="BV1505000001",
        title="MCP Durable Product Research",
        uploader="Stage5",
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
                {"from": index * 5, "to": index * 5 + 4, "content": text}
            )
            for index, text in enumerate(
                (
                    "MCP 通过明确协议连接模型与外部工具。",
                    "工具执行需要持久请求身份与幂等回执。",
                    "失去 lease 的旧 worker 不得提交结果。",
                    "checkpoint 让长期任务可以安全恢复。",
                    "答案必须引用当前版本的权威字幕。",
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
    if registered:
        core._research_outer = OuterResearchService(
            db=core.db,
            kernel=core.research,
            registered_evaluators=(
                RegisteredConstraintEvaluator(
                    registration_id="stage5-grounded-objective",
                    constraint_scope="objective",
                    exact_text=OBJECTIVE,
                    evaluator_kind="grounded_answer",
                    evaluator_policy_version="stage5-test-evaluator-v1",
                ),
                RegisteredConstraintEvaluator(
                    registration_id="stage5-current-evidence",
                    constraint_scope="success_constraint",
                    exact_text=CONSTRAINT,
                    evaluator_kind="minimum_current_evidence",
                    evaluator_policy_version="stage5-test-evaluator-v1",
                    parameters={"minimum": 1},
                ),
            ),
        )
    return core


def _create(service: ResearchProductService, suffix: str) -> str:
    outcome = service.create_task(
        CreateProductResearchRequest(
            command_id=f"stage5:create:{suffix}",
            objective=OBJECTIVE,
            success_constraints=[CONSTRAINT],
            run_immediately=False,
        )
    )
    return str(outcome["task_id"])


def _delta_counts(core: Application, task_id: str) -> tuple[int, int]:
    with core.db.connect() as connection:
        events = int(
            connection.execute(
                "SELECT COUNT(*) FROM research_events "
                "WHERE task_id=? AND event_type='candidate_deltas_materialized'",
                (task_id,),
            ).fetchone()[0]
        )
        receipts = int(
            connection.execute(
                "SELECT COUNT(*) FROM research_command_receipts "
                "WHERE task_id=? AND command_type='materialize_candidate_deltas'",
                (task_id,),
            ).fetchone()[0]
        )
    return events, receipts


def test_research_page_and_public_product_api_reach_honest_waiting_boundary(
    app_paths,
) -> None:
    core = _fixture_core(app_paths)
    client = TestClient(create_web_app(core))

    page = client.get("/research")
    script = client.get("/static/research.js?v=1")
    assert page.status_code == 200
    assert 'data-research-page' in page.text
    assert 'href="/research"' in page.text
    assert "候选 Delta" in page.text
    assert "Provider · NOT EXERCISED" in page.text
    assert script.status_code == 200
    assert "/api/research/product/tasks" in script.text
    assert "['ready', 'running'].includes(product.task.status)" in script.text
    assert "owner_epoch" not in script.text

    created = client.post(
        "/api/research/product/tasks",
        json={
            "command_id": "public-product-create",
            "objective": OBJECTIVE,
            "success_constraints": [CONSTRAINT],
            "run_immediately": True,
        },
    )
    assert created.status_code == 202
    task_id = created.json()["outcome"]["task_id"]
    assert created.json()["href"] == f"/research/{task_id}"

    detail = client.get(f"/api/research/product/tasks/{task_id}")
    assert detail.status_code == 200
    product = detail.json()["product"]
    assert product["task"]["status"] == "waiting_user"
    assert product["provider_status"] == "not_exercised"
    assert product["control"]["open_input_requests"]
    assert "owner_epoch" not in json.dumps(product, ensure_ascii=False)
    assert product["candidate_deltas"]["authority"] == "candidate_only_not_promoted"
    assert {value["delta_kind"] for value in product["candidate_deltas"]["deltas"]} == set(
        DELTA_KINDS
    )
    assert product["trace"]["counts"]["actions"] == 5
    assert product["trace"]["counts"]["audits"] == 1
    assert client.get(f"/research/{task_id}").status_code == 200
    listed = client.get("/api/research/product/tasks").json()["tasks"]
    assert listed[0]["task_id"] == task_id


def test_registered_deterministic_journey_is_terminal_grounded_and_exact_once(
    app_paths,
) -> None:
    core = _fixture_core(app_paths, registered=True)
    task_id = _create(core.research_product, "terminal")
    request = RunProductResearchRequest(command_id="stage5:run:terminal")

    first = core.research_product.run_to_boundary(task_id, request)
    before = core.research.get_task(task_id)
    replay = core.research_product.run_to_boundary(task_id, request)
    after = core.research.get_task(task_id)
    product = core.research_product.get_task(task_id)

    assert first["boundary"] == "durable_boundary"
    assert first["task_status"] == "terminal"
    assert replay["deduplicated"] is True
    assert len(after["events"]) == len(before["events"])
    assert len(after["command_receipts"]) == len(before["command_receipts"])
    assert product["state"]["answer_status"] == "valid_success"
    assert product["state"]["termination_reason"] == "answer_ready"
    assert product["state"]["failure_class"] == "none"
    assert product["answer_blocks"]
    assert product["citations"]
    assert all(value["currentness"] == "current" for value in product["citations"])
    assert product["candidate_deltas"]["candidate_delta_schema_version"] == (
        CANDIDATE_DELTA_SCHEMA_VERSION
    )
    by_kind = {
        value["delta_kind"]: value
        for value in product["candidate_deltas"]["deltas"]
    }
    assert by_kind["KnowledgeDelta"]["items"]
    assert by_kind["CorpusDelta"]["empty_reason"]
    assert by_kind["UserModelDelta"]["empty_reason"]
    assert by_kind["SystemExperienceDelta"]["empty_reason"]
    assert all(
        value["promotion_status"] == "candidate_only_not_promoted"
        for value in by_kind.values()
    )
    assert _delta_counts(core, task_id) == (1, 1)
    assert any(
        value["command_type"] == "renew_owner"
        for value in after["command_receipts"]
    )


def test_shared_evidence_identity_keeps_task_scoped_uses_and_deltas_isolated(
    app_paths,
) -> None:
    core = _fixture_core(app_paths, registered=True)
    task_a = _create(core.research_product, "isolation-a")
    task_b = _create(core.research_product, "isolation-b")

    core.research_product.run_to_boundary(
        task_a, RunProductResearchRequest(command_id="stage5:run:isolation-a")
    )
    core.research_product.run_to_boundary(
        task_b, RunProductResearchRequest(command_id="stage5:run:isolation-b")
    )
    product_a = core.research_product.get_task(task_a)
    product_b = core.research_product.get_task(task_b)

    evidence_ids_a = {value["citation_id"] for value in product_a["citations"]}
    evidence_ids_b = {value["citation_id"] for value in product_b["citations"]}
    evidence_use_ids_a = {
        value["evidence_use_id"] for value in product_a["citations"]
    }
    evidence_use_ids_b = {
        value["evidence_use_id"] for value in product_b["citations"]
    }
    assert evidence_ids_a == evidence_ids_b
    assert evidence_ids_a
    assert evidence_use_ids_a.isdisjoint(evidence_use_ids_b)
    assert product_a["candidate_deltas"]["task_id"] == task_a
    assert product_b["candidate_deltas"]["task_id"] == task_b
    assert set(product_a["candidate_deltas"]["evidence_use_ids"]) == evidence_use_ids_a
    assert set(product_b["candidate_deltas"]["evidence_use_ids"]) == evidence_use_ids_b
    assert product_a["candidate_deltas"]["delta_snapshot_id"] != (
        product_b["candidate_deltas"]["delta_snapshot_id"]
    )


def test_candidate_delta_fault_rolls_back_then_restart_materializes_once(
    app_paths,
) -> None:
    core = _fixture_core(app_paths, registered=True)

    def fault(point: str) -> None:
        if point == "after_candidate_delta_event":
            raise SimulatedCrash(point)

    crashing = ResearchProductService(
        db=core.db,
        kernel=core.research,
        inner=core.research_inner,
        outer=core.research_outer,
        control=core.research_control,
        runner_id="stage5-crashing-runner",
        fault_injector=fault,
    )
    task_id = _create(crashing, "delta-fault")
    with pytest.raises(SimulatedCrash):
        crashing.run_to_boundary(
            task_id, RunProductResearchRequest(command_id="stage5:run:delta-fault")
        )
    assert core.research.get_task(task_id)["task"]["status"] == "terminal"
    assert _delta_counts(core, task_id) == (0, 0)

    restarted = ResearchProductService(
        db=core.db,
        kernel=core.research,
        inner=core.research_inner,
        outer=core.research_outer,
        control=core.research_control,
        runner_id="stage5-restarted-runner",
    )
    first = restarted.ensure_candidate_deltas(task_id)
    replay = restarted.ensure_candidate_deltas(task_id)
    assert first is not None and first["deduplicated"] is False
    assert replay is not None and replay["deduplicated"] is True
    assert _delta_counts(core, task_id) == (1, 1)


def test_restart_takeover_waits_for_lease_then_continues_same_attempt(app_paths) -> None:
    core = _fixture_core(app_paths, registered=True)
    first_runner = ResearchProductService(
        db=core.db,
        kernel=core.research,
        inner=core.research_inner,
        outer=core.research_outer,
        control=core.research_control,
        runner_id="stage5-runner-a",
    )
    task_id = _create(first_runner, "takeover")
    yielded = first_runner.run_to_boundary(
        task_id,
        RunProductResearchRequest(command_id="stage5:run:yield", max_steps=1),
    )
    assert yielded["boundary"] == "bounded_yield"
    before = core.research.get_task(task_id)
    assert before["task"]["status"] == "running"
    assert len(before["attempts"]) == 1

    restarted = ResearchProductService(
        db=core.db,
        kernel=core.research,
        inner=core.research_inner,
        outer=core.research_outer,
        control=core.research_control,
        runner_id="stage5-runner-b",
    )
    with pytest.raises(ResearchConflict, match="active owner"):
        restarted.run_to_boundary(
            task_id, RunProductResearchRequest(command_id="stage5:run:too-early")
        )
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE research_tasks SET lease_until=? WHERE task_id=?",
            ("2000-01-01T00:00:00+00:00", task_id),
        )
    completed = restarted.run_to_boundary(
        task_id, RunProductResearchRequest(command_id="stage5:run:takeover")
    )
    state = core.research.get_task(task_id)
    assert completed["task_status"] == "terminal"
    assert len(state["attempts"]) == 1
    assert state["attempts"][0]["attempt_id"] == before["attempts"][0]["attempt_id"]
    assert int(state["task"]["owner_epoch"]) > int(before["task"]["owner_epoch"])
    assert _delta_counts(core, task_id) == (1, 1)


def test_same_runner_command_race_has_single_boundary_receipt(app_paths) -> None:
    core = _fixture_core(app_paths, registered=True)
    service = core.research_product
    task_id = _create(service, "race")
    request = RunProductResearchRequest(command_id="stage5:run:race")

    def invoke(_: int):
        try:
            return ("ok", service.run_to_boundary(task_id, request))
        except ResearchConflict as exc:
            return ("conflict", str(exc))

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(invoke, range(2)))
    assert any(kind == "ok" for kind, _ in outcomes)
    replay = service.run_to_boundary(task_id, request)
    assert replay["deduplicated"] is True
    with core.db.connect() as connection:
        boundaries = int(
            connection.execute(
                "SELECT COUNT(*) FROM research_command_receipts "
                "WHERE task_id=? AND command_type='product_run_to_boundary'",
                (task_id,),
            ).fetchone()[0]
        )
    assert boundaries == 1
    assert _delta_counts(core, task_id) == (1, 1)


def test_current_input_control_and_trace_redaction_use_public_api(app_paths) -> None:
    core = _fixture_core(app_paths)
    client = TestClient(create_web_app(core))
    task_id = _create(core.research_product, "control")
    core.research_product.run_to_boundary(
        task_id, RunProductResearchRequest(command_id="stage5:run:control")
    )
    product = core.research_product.get_task(task_id)
    current_input = product["control"]["open_input_requests"][0]
    context = product["control"]["action_context"]
    decision = client.post(
        f"/api/research/tasks/{task_id}/inputs/decisions",
        json=HumanDecisionRequest(
            command_id="stage5:input:control",
            input_request_id=current_input["input_request_id"],
            expected_state_version=context["expected_state_version"],
            expected_control_generation=context["expected_control_generation"],
            decision_kind="clarify_goal",
            response={
                "objective": OBJECTIVE,
                "success_constraints": [CONSTRAINT],
                "evidence_policy": {"authority": "live_current_exact_replay"},
            },
        ).model_dump(mode="json"),
    )
    assert decision.status_code == 200
    running = core.research_product.get_task(task_id)
    assert running["task"]["status"] == "running"
    assert running["control"]["open_input_requests"] == []
    assert "run" in running["control"]["allowed_operations"]
    assert running["candidate_deltas"]["is_current_boundary"] is False

    core.research_product.run_to_boundary(
        task_id,
        RunProductResearchRequest(command_id="stage5:run:one-step", max_steps=1),
    )
    current = core.research_product.get_task(task_id)
    assert current["citations"] == []
    context = current["control"]["action_context"]
    interrupt = client.post(
        f"/api/research/tasks/{task_id}/control",
        json=ControlCommandRequest(
            command_id="stage5:interrupt",
            kind="interrupt",
            expected_state_version=context["expected_state_version"],
            expected_checkpoint_id=context["expected_checkpoint_id"],
            expected_control_generation=context["expected_control_generation"],
            reason="product interrupt",
        ).model_dump(mode="json"),
    )
    assert interrupt.status_code == 200
    blocked = core.research_product.get_task(task_id)
    assert blocked["task"]["status"] == "blocked"
    assert "resume" in blocked["control"]["allowed_operations"]
    context = blocked["control"]["action_context"]
    resume = client.post(
        f"/api/research/tasks/{task_id}/control",
        json=ControlCommandRequest(
            command_id="stage5:resume",
            kind="resume",
            expected_state_version=context["expected_state_version"],
            expected_checkpoint_id=context["expected_checkpoint_id"],
            expected_control_generation=context["expected_control_generation"],
            reason="product resume",
        ).model_dump(mode="json"),
    )
    assert resume.status_code == 200

    with core.research._transaction() as connection:
        task = core.research._task(connection, task_id)
        core.research._event(
            connection,
            task_id=task_id,
            goal_id=str(task["active_goal_id"]),
            event_type="test_sensitive_payload",
            payload={"secret": "do-not-project", "api_key": "also-hidden"},
            command_id="test-sensitive",
            owner_epoch=int(task["owner_epoch"]),
            now=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        )
    projected = client.get(f"/api/research/product/tasks/{task_id}").json()["product"]
    serialized = json.dumps(projected, ensure_ascii=False)
    assert "do-not-project" not in serialized
    assert "also-hidden" not in serialized
    assert projected["task"]["status"] == "running"
