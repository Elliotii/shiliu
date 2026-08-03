from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from shiliu.app import Application
from shiliu.ask.contracts import (
    AnswerBlock,
    AskResponse,
    GroundedAnswerDraft,
    QueryAnalysis,
    TraceSummary,
)
from shiliu.ask.deep.contracts import AgentDecision
from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.query_analysis import QueryAnalyzer
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.research.control_contracts import HumanDecisionRequest
from shiliu.research.errors import ResearchConflict, ResearchUnsafeState, SimulatedCrash
from shiliu.research.inner_evidence import PersistentEvidenceAuthority
from shiliu.research.inner_service import InnerResearchService
from shiliu.research.outer_contracts import RegisteredConstraintEvaluator
from shiliu.research.outer_service import OuterResearchService
from shiliu.research.product_contracts import CreateProductResearchRequest
from shiliu.research.product_service import ResearchProductService
from shiliu.research.provider_product import (
    DurableDeepResearchOutput,
    ReceiptBoundDeepResearchExecutor,
    ReceiptBoundResearchProductOrchestrator,
)
from shiliu.research.provider_wiring import ReceiptBoundProviderService
from shiliu.retrieval.coordinator import SYNC_STATE_VERSION


ROOT = Path(__file__).resolve().parents[1]
RUNNER_SPEC = importlib.util.spec_from_file_location(
    "v5_a_gate_b_postfix_validate",
    ROOT / "scripts/v5_a_gate_b_postfix_validate.py",
)
assert RUNNER_SPEC and RUNNER_SPEC.loader
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(RUNNER)
_load_case_projection = RUNNER._load_case_projection


GROUNDED_OBJECTIVE = "MCP"
GROUNDED_CONSTRAINT = "至少有一条当前字幕证据"
AMBIGUOUS_OBJECTIVE = "可靠性和迭代速度哪个优先？若目标不清楚请先询问用户"


@dataclass
class _Reply:
    output: object
    usage: dict[str, int]
    response_id: str
    finish_reason: str = "stop"
    latency_ms: float = 1.0
    retry_count: int = 0


class _ProductMockProvider:
    name = "openai-compatible"

    def __init__(self, *, fail_transport: bool = False) -> None:
        self.base_url = "https://api.deepseek.com/v1"
        self.model = "deepseek-v4-pro"
        self.thinking_enabled = False
        self.reasoning_effort: str | None = None
        self.fail_transport = fail_transport
        self.calls: list[str] = []
        self.next_grounded_draft: GroundedAnswerDraft | None = None

    def for_role(self, role: str):
        self.thinking_enabled = role == "grounded_answer"
        self.reasoning_effort = "high" if self.thinking_enabled else None
        return self

    def generate_structured(self, **kwargs):
        role = str(kwargs["role"])
        self.calls.append(role)
        if self.fail_transport:
            raise RuntimeError("ambiguous no-network transport outcome")
        if role == "query_analysis":
            output: object = QueryAnalysis(
                normalized_intent="durable research",
                search_queries=["MCP checkpoint"],
                entities=["MCP"],
                language="zh",
            )
        elif role == "agent_action":
            output = AgentDecision(
                action={"kind": "finish", "summary": "bounded mock research"},
                open_questions=[],
                resolved_questions=[],
            )
        elif role == "grounded_answer":
            output = self.next_grounded_draft or GroundedAnswerDraft(
                status="insufficient",
                answer_blocks=[],
                limitations=["placeholder"],
            )
            self.next_grounded_draft = None
        else:  # pragma: no cover
            raise AssertionError(role)
        return _Reply(
            output=output,
            usage={"prompt_tokens": 20, "completion_tokens": 5},
            response_id=f"mock-product-{role}-{len(self.calls)}",
        )


class _BoundedMockDeepExecutor:
    def __init__(self, db, *, insufficient_objectives: set[str] | None = None) -> None:
        self.db = db
        self.authority = PersistentEvidenceAuthority(db)
        self.insufficient_objectives = insufficient_objectives or set()

    def execute(self, *, objective: str, provider_factory) -> DurableDeepResearchOutput:
        plan = QueryAnalyzer(provider_factory).analyze(objective)
        if plan.error:
            raise ResearchUnsafeState(plan.error)
        provider_factory("agent_action").generate_structured(
            role="agent_action",
            messages=[{"role": "user", "content": objective}],
            response_schema=AgentDecision,
            max_tokens=1200,
        )
        task_id = provider_factory.context.task_id
        attempt_id = provider_factory.context.attempt_id
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT eu.*, ei.* FROM research_evidence_uses eu
                JOIN research_evidence_identities ei
                  ON ei.evidence_id=eu.evidence_id
                WHERE eu.task_id=? AND eu.attempt_id=?
                ORDER BY eu.created_at, eu.evidence_use_id LIMIT 1
                """,
                (task_id, attempt_id),
            ).fetchone()
        insufficient = objective in self.insufficient_objectives or row is None
        span = None if row is None else self.authority.observe(row).span
        if insufficient:
            draft = GroundedAnswerDraft(
                status="insufficient",
                answer_blocks=[],
                limitations=["当前固定证据不足以回答该目标"],
            )
            citations = []
            termination = "evidence_unavailable"
        else:
            assert span is not None
            draft = GroundedAnswerDraft(
                status="partial",
                answer_blocks=[
                    AnswerBlock(
                        text=span.quote_text,
                        citation_ids=[span.citation_id],
                    )
                ],
                limitations=["仍需 Outer Goal Audit 判断目标是否满足"],
            )
            citations = [span.as_citation()]
            termination = "answer_ready"
        transport = provider_factory("grounded_answer")
        receipt_transport = getattr(transport, "provider", transport)
        provider = receipt_transport.factory.provider_factory("grounded_answer")
        if isinstance(provider, _ProductMockProvider):
            provider.next_grounded_draft = draft
        grounded = transport.generate_structured(
            role="grounded_answer",
            messages=[{"role": "user", "content": objective}],
            response_schema=GroundedAnswerDraft,
            max_tokens=4096,
        )
        # The mock transport proves receipt mechanics; this executor supplies the
        # typed grounded result that the unchanged Deep path would validate.
        assert isinstance(grounded.output, GroundedAnswerDraft)
        response = AskResponse(
            run_id=f"mock-deep-{task_id}-{attempt_id}",
            mode="deep",
            status=draft.status,
            answer_blocks=draft.answer_blocks,
            citations=citations,
            limitations=draft.limitations,
            termination_reason=termination,
            trace_summary=TraceSummary(
                query_count=1,
                retrieval_count=1,
                valid_evidence_count=len(citations),
                stale_evidence_count=0,
                context_span_count=len(citations),
                context_truncated=False,
                repair_used=False,
                latency_ms=3,
                termination_reason=termination,
                decision_rounds=1,
                tool_calls=1,
                visited_video_count=1 if citations else 0,
                visited_segment_count=1 if citations else 0,
                navigation_result_count=1,
            ),
        )
        return DurableDeepResearchOutput(
            query_plan=plan,
            response=response,
            trace={
                "run_id": response.run_id,
                "query": objective,
                "events": [{"event_type": "bounded_mock_deep"}],
                "status": response.status,
            },
        )


def _fixture(app_paths, *, inner_fault_injector=None):
    core = Application(app_paths)
    source_db_id = core.db.create_favorite_source(
        folder_id=1506, folder_title="Gate B Product Fixture"
    )
    item = FavoriteItem(
        bvid="BV1506000001",
        title="MCP Durable Product Orchestration",
        uploader="GateB",
        favorite_time=1,
    )
    core.db.record_source_snapshot(source_db_id, [item], processing_profile="formal")
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
                    "长期研究需要持久 checkpoint 才能在重启后继续。",
                    "SideEffect receipt 防止外部调用被自动重复。",
                    "Outer audit 判断证据是否真正满足目标。",
                    "Agent 开发流程在 test 完成后进入 checkpoint，主动停下来接受人工验收，以发现仍不满足条件的问题。",
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
            """,
            (video_id, SYNC_STATE_VERSION, now, now, now),
        )
    base_inner = core.research_inner
    materializer = TranscriptEvidenceMaterializer(core.db)
    inner = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=base_inner.tools,
        materializer=materializer,
        provider_runs_authorized=True,
        fault_injector=inner_fault_injector,
    )
    outer = OuterResearchService(
        db=core.db,
        kernel=core.research,
        registered_evaluators=(
            RegisteredConstraintEvaluator(
                registration_id="gate-b-grounded-objective",
                constraint_scope="objective",
                exact_text=GROUNDED_OBJECTIVE,
                evaluator_kind="grounded_answer",
                evaluator_policy_version="gate-b-product-test-v1",
            ),
            RegisteredConstraintEvaluator(
                registration_id="gate-b-current-evidence",
                constraint_scope="success_constraint",
                exact_text=GROUNDED_CONSTRAINT,
                evaluator_kind="minimum_current_evidence",
                evaluator_policy_version="gate-b-product-test-v1",
                parameters={"minimum": 1},
            ),
        ),
    )
    product = ResearchProductService(
        db=core.db,
        kernel=core.research,
        inner=inner,
        outer=outer,
        control=core.research_control,
        runner_id="gate-b-product-worker",
    )
    return core, inner, product, materializer


def _create(product: ResearchProductService, suffix: str, objective: str) -> str:
    created = product.create_task(
        CreateProductResearchRequest(
            command_id=f"gate-b-product:create:{suffix}",
            objective=objective,
            success_constraints=[GROUNDED_CONSTRAINT],
            run_immediately=False,
        )
    )
    return str(created["task_id"])


def _orchestrator(
    core,
    inner,
    product,
    materializer,
    provider,
    *,
    insufficient_objectives: set[str] | None = None,
):
    receipt = ReceiptBoundProviderService(
        db=core.db,
        kernel=core.research,
        provider_dispatch_authorized=True,
    )
    return ReceiptBoundResearchProductOrchestrator(
        db=core.db,
        kernel=core.research,
        inner=inner,
        product=product,
        receipt_service=receipt,
        provider_factory=lambda role: provider.for_role(role),
        deep_executor=_BoundedMockDeepExecutor(
            core.db, insufficient_objectives=insufficient_objectives
        ),
        materializer=materializer,
        provider_product_authorized=True,
    ), receipt


@pytest.mark.parametrize(
    "objective,insufficient",
    [(GROUNDED_OBJECTIVE, False), ("无法由当前字幕证明的目标", True)],
)
def test_provider_product_grounded_and_insufficient_close_durable_lineage(
    app_paths, objective: str, insufficient: bool
) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider()
    orchestrator, receipt = _orchestrator(
        core,
        inner,
        product,
        materializer,
        provider,
        insufficient_objectives={objective} if insufficient else set(),
    )
    task_id = _create(product, "insufficient" if insufficient else "grounded", objective)

    result = orchestrator.run_to_boundary(
        task_id, command_id=f"gate-b-product:run:{objective}"
    )
    assert result["task_status"] in {"terminal", "waiting_user"}
    raw = core.research.get_task(task_id)
    assert raw["task"]["status"] != "running"
    assert raw["checkpoints"]
    assert raw["outer_audits"]
    assert raw["traces"]
    artifact = raw["provisional_artifacts"][-1]
    assert artifact["provider_side_effect_id"]
    assert artifact["answer_status"] == (
        "valid_insufficient" if insufficient else "valid_partial"
    )
    if insufficient:
        assert result["task_status"] == "waiting_user"
        assert raw["results"] == []
    else:
        assert raw["traces"][-1]["ended_at"] is not None
        assert raw["results"][-1]["is_task_terminal"] == 1
        assert raw["results"][-1]["answer_status"] == "valid_success"
    before_calls = list(provider.calls)
    before_budget = receipt.budget_snapshot(task_id)
    replay = orchestrator.run_to_boundary(
        task_id, command_id=f"gate-b-product:run:{objective}"
    )
    assert replay["deduplicated"] is True
    assert provider.calls == before_calls
    assert receipt.budget_snapshot(task_id) == before_budget


def test_postfix_projection_reads_current_input_from_control_status_no_network(
    app_paths,
) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider()
    objective = "当前固定语料无法证明的投影恢复目标"
    orchestrator, _receipt = _orchestrator(
        core,
        inner,
        product,
        materializer,
        provider,
        insufficient_objectives={objective},
    )
    task_id = _create(product, "projection-control-input", objective)

    result = orchestrator.run_to_boundary(
        task_id, command_id="gate-b-product:projection-control-input"
    )
    projection, raw = _load_case_projection(
        app=core, task_id=task_id, result=result, hitl=None
    )

    assert raw["task"]["status"] == "waiting_user"
    assert "input_requests" not in raw
    control = core.research_control.get_status(task_id)
    assert len(control["open_input_requests"]) == 1
    assert projection["open_input_requests"] == control["open_input_requests"]
    assert projection["open_input_requests"][0]["current_status"] == "open"
    assert projection["outer_audit"]["outcome"] == "blocked"


def test_provider_product_waiting_user_fixed_answer_continues_exact_once(
    app_paths,
) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider()
    orchestrator, _receipt = _orchestrator(
        core, inner, product, materializer, provider
    )
    task_id = _create(product, "hitl", AMBIGUOUS_OBJECTIVE)
    first = orchestrator.run_to_boundary(
        task_id, command_id="gate-b-product:hitl:first"
    )
    assert first["task_status"] == "waiting_user"
    status = core.research_control.get_status(task_id)
    assert len(status["open_input_requests"]) == 1
    current = status["open_input_requests"][0]
    task = status["task"]
    decision_request = HumanDecisionRequest(
        command_id="gate-b-product:hitl:fixed-answer",
        input_request_id=current["input_request_id"],
        expected_state_version=int(task["state_version"]),
        expected_control_generation=int(task["control_generation"]),
        decision_kind="clarify_goal",
        response={
            "objective": GROUNDED_OBJECTIVE,
            "success_constraints": [GROUNDED_CONSTRAINT],
            "evidence_policy": {"authority": "server_registry_only"},
        },
    )
    decided = core.research_control.decide_input(
        task_id, decision_request, principal_id="local_operator"
    )
    replay = core.research_control.decide_input(
        task_id, decision_request, principal_id="local_operator"
    )
    assert replay["deduplicated"] is True
    assert replay["decision_id"] == decided["decision_id"]
    stale = decision_request.model_copy(
        update={
            "command_id": "gate-b-product:hitl:stale-history",
            "expected_state_version": decided["state_version"],
            "expected_control_generation": decided["control_generation"],
        }
    )
    with pytest.raises(ResearchConflict, match="already disposed"):
        core.research_control.decide_input(
            task_id, stale, principal_id="local_operator"
        )
    final = orchestrator.run_to_boundary(
        task_id, command_id="gate-b-product:hitl:after-current-decision"
    )
    assert final["task_status"] == "terminal"
    raw = core.research.get_task(task_id)
    assert len(raw["goals"]) == 2
    assert len(raw["attempts"]) == 2
    assert raw["attempts"][1]["parent_attempt_id"] == raw["attempts"][0]["attempt_id"]
    control = core.research_control.get_status(task_id)
    assert len(control["human_decisions"]) == 1
    assert control["open_input_requests"] == []
    assert raw["task"]["status"] == "terminal"


def test_postfix_prepare_hitl_continues_to_durable_projection_and_report_no_network(
    app_paths, tmp_path: Path
) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider()
    orchestrator, _receipt = _orchestrator(
        core, inner, product, materializer, provider
    )
    task_id = _create(product, "runner-hitl-recovery", AMBIGUOUS_OBJECTIVE)
    case = {
        "case_id": "GB-H-01",
        "objective": AMBIGUOUS_OBJECTIVE,
        "success_constraints": [GROUNDED_CONSTRAINT],
        "fixed_user_answer": "可靠性优先；未知副作用不得自动重放。",
    }

    hitl = RUNNER._prepare_hitl(
        app=core, product=product, task_id=task_id, case=case
    )
    assert hitl["decision_replay_deduplicated"] is True
    assert hitl["input_source_checkpoint_id"]
    assert hitl["child_parent_attempt_id"] == hitl["input_attempt_id"]
    assert (
        hitl["child_source_checkpoint_id"]
        == hitl["input_source_checkpoint_id"]
    )
    control_after_decision = core.research_control.get_status(task_id)
    assert len(control_after_decision["human_decisions"]) == 1
    assert control_after_decision["open_input_requests"] == []

    result = orchestrator.run_to_boundary(
        task_id, command_id="gate-b-product:runner-hitl-recovery:provider-once"
    )
    projection, raw = RUNNER._load_case_projection(
        app=core, task_id=task_id, result=result, hitl=hitl
    )
    assert provider.calls
    assert projection["task_status"] in {"terminal", "blocked"}
    assert projection["provisional_artifact"] is not None
    assert projection["outer_audit"] is not None
    assert projection["checkpoint_count"] >= 2
    assert projection["trace_count"] >= 2
    assert projection["provider_receipts"]
    assert all(
        row["status"] == "succeeded" for row in projection["provider_receipts"]
    )
    final_control = core.research_control.get_status(task_id)
    assert len(final_control["input_requests"]) == 1
    assert final_control["open_input_requests"] == []
    assert any(
        event["event_type"] == "duplicate_input_request_suppressed"
        for event in raw["events"]
    )

    report_root = tmp_path / "runner-hitl-report"
    RUNNER._write_case_evidence(
        root=report_root, case=case, projection=projection, raw=raw
    )
    stored = json.loads(
        (report_root / "cases/GB-H-01/durable_product_projection.json").read_text()
    )
    assert stored["hitl"]["child_attempt_id"] == hitl["child_attempt_id"]
    assert stored["open_input_requests"] == projection["open_input_requests"]
    assert (report_root / "cases/GB-H-01/research_task_trace.json").is_file()
    assert (report_root / "cases/GB-H-01/usage_cost.jsonl").read_text().strip()


def test_provider_product_unknown_dispatch_blocks_and_never_replays_transport(
    app_paths,
) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider(fail_transport=True)
    orchestrator, _receipt = _orchestrator(
        core, inner, product, materializer, provider
    )
    task_id = _create(product, "unknown", GROUNDED_OBJECTIVE)
    with pytest.raises(ResearchUnsafeState):
        orchestrator.run_to_boundary(
            task_id, command_id="gate-b-product:unknown"
        )
    assert len(provider.calls) == 1
    raw = core.research.get_task(task_id)
    assert raw["task"]["status"] == "blocked"
    assert raw["side_effects"][-1]["status"] == "unknown"
    replay = orchestrator.run_to_boundary(
        task_id, command_id="gate-b-product:unknown"
    )
    assert replay["task_status"] == "blocked"
    assert len(provider.calls) == 1


def test_unchanged_deep_executor_reaches_durable_waiting_boundary_no_network(
    app_paths,
) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider()
    receipt = ReceiptBoundProviderService(
        db=core.db,
        kernel=core.research,
        provider_dispatch_authorized=True,
    )
    deep = ReceiptBoundDeepResearchExecutor(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
        budget=DeepSearchBudget(
            max_decision_rounds=1,
            max_tool_calls=1,
            total_runtime_seconds=10,
            search_phase_cutoff_seconds=5,
            final_answer_reserve_seconds=5,
        ),
    )
    orchestrator = ReceiptBoundResearchProductOrchestrator(
        db=core.db,
        kernel=core.research,
        inner=inner,
        product=product,
        receipt_service=receipt,
        provider_factory=lambda role: provider.for_role(role),
        deep_executor=deep,
        materializer=materializer,
        provider_product_authorized=True,
    )
    task_id = _create(product, "unchanged-deep", "解释一个当前语义仍不明确的目标")
    result = orchestrator.run_to_boundary(
        task_id, command_id="gate-b-product:unchanged-deep"
    )
    assert result["task_status"] == "waiting_user"
    # The unchanged Deep finalizer correctly skips grounded generation when it
    # has no admissible evidence context; the preceding real roles remain receipted.
    assert provider.calls == ["query_analysis", "agent_action"]
    raw = core.research.get_task(task_id)
    assert raw["provisional_artifacts"][-1]["answer_status"] == "valid_insufficient"
    assert raw["outer_audits"][-1]["outcome"] == "blocked"


def test_provider_product_ingest_fault_rolls_back_then_replays_without_transport(
    app_paths,
) -> None:
    fired = False

    def crash_once(point: str) -> None:
        nonlocal fired
        if point == "after_provisional_artifact_insert" and not fired:
            fired = True
            raise SimulatedCrash(point)

    core, inner, product, materializer = _fixture(
        app_paths, inner_fault_injector=crash_once
    )
    provider = _ProductMockProvider()
    orchestrator, receipt = _orchestrator(
        core, inner, product, materializer, provider
    )
    task_id = _create(product, "fault-replay", GROUNDED_OBJECTIVE)
    with pytest.raises(SimulatedCrash):
        orchestrator.run_to_boundary(
            task_id, command_id="gate-b-product:fault-replay"
        )
    raw = core.research.get_task(task_id)
    assert raw["provisional_artifacts"] == []
    calls = list(provider.calls)
    budget = receipt.budget_snapshot(task_id)

    replay = orchestrator.run_to_boundary(
        task_id, command_id="gate-b-product:fault-replay"
    )
    assert replay["task_status"] == "terminal"
    assert provider.calls == calls
    assert receipt.budget_snapshot(task_id) == budget
    raw = core.research.get_task(task_id)
    assert len(raw["provisional_artifacts"]) == 1
    assert len(raw["outer_audits"]) == 1


def test_provider_product_logical_cap_blocks_before_next_transport(app_paths) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider()
    orchestrator, _receipt = _orchestrator(
        core, inner, product, materializer, provider
    )
    task_id = _create(product, "logical-cap", GROUNDED_OBJECTIVE)
    with pytest.raises(ResearchUnsafeState, match="logical-call cap"):
        orchestrator.run_to_boundary(
            task_id,
            command_id="gate-b-product:logical-cap",
            max_logical_calls=2,
        )
    assert provider.calls == ["query_analysis", "agent_action"]
    with pytest.raises(ResearchUnsafeState, match="logical-call cap"):
        orchestrator.run_to_boundary(
            task_id,
            command_id="gate-b-product:logical-cap",
            max_logical_calls=2,
        )
    assert provider.calls == ["query_analysis", "agent_action"]


def test_completion_cases_use_product_profile_and_exact_one_hitl_no_network(
    app_paths,
) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider()
    orchestrator, _receipt = _orchestrator(
        core, inner, product, materializer, provider
    )
    cases = json.loads(
        (ROOT / "V5_A_STAGE_5_GATE_B_COMPLETION_CASES.json").read_text(
            encoding="utf-8"
        )
    )["cases"]
    by_id = {case["case_id"]: case for case in cases}

    grounded = by_id["GB-PC-G-01"]
    grounded_fixture = {**grounded, "objective": GROUNDED_OBJECTIVE}
    grounded_task = product.create_task(
        CreateProductResearchRequest(
            command_id="completion-test:g:create",
            objective=grounded_fixture["objective"],
            success_constraints=grounded_fixture["success_constraints"],
            constraint_profile=grounded_fixture["constraint_profile"],
            run_immediately=False,
        )
    )["task_id"]
    grounded_result = orchestrator.run_to_boundary(
        grounded_task, command_id="completion-test:g:provider-once"
    )
    grounded_raw = core.research.get_task(grounded_task)
    assert grounded_result["task_status"] == "terminal"
    assert grounded_raw["evidence_uses"]
    assert grounded_raw["outer_audits"][-1]["outcome"] == "accept"

    hitl_case = by_id["GB-PC-H-01"]
    hitl_fixture = {
        **hitl_case,
        "objective": AMBIGUOUS_OBJECTIVE,
        "success_constraints": ["继续前需要用户明确选择优先级（mock）"],
        "fixed_human_response": {
            "objective": GROUNDED_OBJECTIVE,
            "success_constraints": [],
        },
    }
    hitl_task = product.create_task(
        CreateProductResearchRequest(
            command_id="completion-test:h:create",
            objective=hitl_fixture["objective"],
            success_constraints=hitl_fixture["success_constraints"],
            constraint_profile=hitl_fixture["constraint_profile"],
            run_immediately=False,
        )
    )["task_id"]
    hitl = RUNNER._prepare_hitl(
        app=core, product=product, task_id=hitl_task, case=hitl_fixture
    )
    hitl_result = orchestrator.run_to_boundary(
        hitl_task, command_id="completion-test:h:provider-once"
    )
    projection, _raw = RUNNER._load_case_projection(
        app=core, task_id=hitl_task, result=hitl_result, hitl=hitl
    )
    control = core.research_control.get_status(hitl_task)
    assert projection["task_status"] != "running"
    assert projection["evidence_use_count"] >= 1
    assert projection["input_request_count"] == 1
    assert projection["human_decision_count"] == 1
    assert control["open_input_requests"] == []
