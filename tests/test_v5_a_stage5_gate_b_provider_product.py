from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.ask.contracts import (
    AnswerBlock,
    AskResponse,
    GroundedAnswerDraft,
    TraceSummary,
)
from shiliu.ask.deep.contracts import AgentDecision
from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.research.contracts import AttemptCause
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
from shiliu.research.provider_wiring import (
    ProviderRunBudgetPolicy,
    ReceiptBoundProviderService,
)
from shiliu.retrieval.coordinator import SYNC_STATE_VERSION
from shiliu.web import create_web_app


ROOT = Path(__file__).resolve().parents[1]
RUNNER_SPEC = importlib.util.spec_from_file_location(
    "v5_a_gate_b_postfix_validate",
    ROOT / "scripts/v5_a_gate_b_postfix_validate.py",
)
assert RUNNER_SPEC and RUNNER_SPEC.loader
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(RUNNER)


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

    def __init__(
        self, *, fail_transport: bool = False, known_failures: int = 0
    ) -> None:
        self.base_url = "https://api.deepseek.com/v1"
        self.model = "deepseek-v4-pro"
        self.thinking_enabled = False
        self.reasoning_effort: str | None = None
        self.fail_transport = fail_transport
        self.known_failures = known_failures
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
        if self.known_failures:
            self.known_failures -= 1
            error = RuntimeError("known mock Provider failure")
            error.completion_metadata = {
                "usage": {"prompt_tokens": 20, "completion_tokens": 0},
                "response_id": f"mock-known-failure-{len(self.calls)}",
                "finish_reason": "invalid_output",
                "latency_ms": 1.0,
                "retry_count": 0,
                "content_received": True,
            }
            raise error
        if role == "agent_action":
            output: object = AgentDecision(
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


class _EmptyNavigationProductProvider(_ProductMockProvider):
    """Exercise the real Deep graph without encoding fixture-specific routing."""

    def generate_structured(self, **kwargs):
        role = str(kwargs["role"])
        self.calls.append(role)
        if role == "agent_action":
            action_number = self.calls.count("agent_action")
            output: object = AgentDecision.model_validate(
                {
                    "action": (
                        {"kind": "search_navigation", "query": "人工验收"}
                        if action_number == 1
                        else {"kind": "finish", "summary": "已有当前字幕证据"}
                    )
                }
            )
        elif role == "grounded_answer":
            serialized = "\n".join(
                str(value["content"]) for value in kwargs["messages"]
            )
            citation_ids = re.findall(r"citation_v1_[0-9a-f]{64}", serialized)
            assert citation_ids
            output = GroundedAnswerDraft(
                status="complete",
                answer_blocks=[
                    AnswerBlock(
                        text="Agent 开发流程在 test 完成后进入 checkpoint，主动停下来接受人工验收，以发现仍不满足条件的问题。",
                        citation_ids=[citation_ids[0]],
                    )
                ],
                limitations=[],
            )
        else:  # pragma: no cover
            raise AssertionError(role)
        return _Reply(
            output=output,
            usage={"prompt_tokens": 20, "completion_tokens": 5},
            response_id=f"mock-empty-navigation-{role}-{len(self.calls)}",
        )


class _BoundedMockDeepExecutor:
    def __init__(
        self,
        db,
        *,
        insufficient_objectives: set[str] | None = None,
        complete_objectives: set[str] | None = None,
    ) -> None:
        self.db = db
        self.authority = PersistentEvidenceAuthority(db)
        self.insufficient_objectives = insufficient_objectives or set()
        self.complete_objectives = complete_objectives or set()

    def execute(self, *, objective: str, provider_factory) -> DurableDeepResearchOutput:
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
            final_blocks: list[AnswerBlock] = []
            draft = GroundedAnswerDraft(
                status="insufficient",
                answer_blocks=[],
                limitations=["当前固定证据不足以回答该目标"],
            )
            citations = []
            termination = "evidence_unavailable"
        else:
            assert span is not None
            status = (
                "complete" if objective in self.complete_objectives else "partial"
            )
            final_blocks = [
                AnswerBlock(
                    text=span.quote_text,
                    citation_ids=[span.citation_id],
                )
            ]
            draft = GroundedAnswerDraft(
                status=status,
                answer_blocks=final_blocks,
                limitations=[f"Deep {status} limitation preserved"],
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
            answer_blocks=final_blocks,
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
            response=response,
            trace={
                "run_id": response.run_id,
                "query": objective,
                "events": [{"event_type": "bounded_mock_deep"}],
                "status": response.status,
            },
        )


class _ForbiddenRecoveryDeepExecutor:
    def __init__(self) -> None:
        self.incremental_calls = {
            "search": 0,
            "evidence_gap": 0,
            "replan": 0,
            "finalizer": 0,
            "trust": 0,
            "ask_response_construction": 0,
        }

    def execute(self, **_kwargs):
        self.incremental_calls["search"] += 1
        raise AssertionError("local recovery must not execute Deep business semantics")


class _GenerationFailedDeepExecutor:
    def execute(self, *, objective: str, provider_factory, **_kwargs):
        provider_factory("agent_action").generate_structured(
            role="agent_action",
            messages=[{"role": "user", "content": objective}],
            response_schema=AgentDecision,
            max_tokens=1200,
        )
        response = AskResponse(
            run_id="mock-deep-generation-failed",
            mode="deep",
            status="insufficient",
            execution_outcome="generation_failed",
            answer_blocks=[],
            citations=[],
            limitations=["Grounded answer Provider 调用失败。"],
            termination_reason="provider_error",
            trace_summary=TraceSummary(
                query_count=1,
                retrieval_count=1,
                valid_evidence_count=0,
                stale_evidence_count=0,
                context_span_count=0,
                context_truncated=False,
                repair_used=False,
                latency_ms=3,
                termination_reason="provider_error",
                decision_rounds=1,
                tool_calls=1,
                visited_video_count=0,
                visited_segment_count=0,
                navigation_result_count=0,
            ),
        )
        return DurableDeepResearchOutput(
            response=response,
            trace={"run_id": response.run_id, "query": objective, "events": []},
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
    created = product.create_provider_task(
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
    complete_objectives: set[str] | None = None,
    fault_injector=None,
):
    receipt = ReceiptBoundProviderService(
        db=core.db,
        kernel=core.research,
        role_token_caps={"grounded_answer": 8192},
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
            core.db,
            insufficient_objectives=insufficient_objectives,
            complete_objectives=complete_objectives,
        ),
        materializer=materializer,
        provider_product_authorized=True,
        fault_injector=fault_injector,
    ), receipt


def _fresh_orchestrator(
    app_paths, provider, deep_executor, *, runner_id="gate-b-product-worker"
):
    core = Application(app_paths)
    materializer = TranscriptEvidenceMaterializer(core.db)
    inner = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=core.research_inner.tools,
        materializer=materializer,
        provider_runs_authorized=True,
    )
    product = ResearchProductService(
        db=core.db,
        kernel=core.research,
        inner=inner,
        outer=core.research_outer,
        control=core.research_control,
        runner_id=runner_id,
    )
    receipt = ReceiptBoundProviderService(
        db=core.db,
        kernel=core.research,
        provider_dispatch_authorized=True,
    )
    orchestrator = ReceiptBoundResearchProductOrchestrator(
        db=core.db,
        kernel=core.research,
        inner=inner,
        product=product,
        receipt_service=receipt,
        provider_factory=lambda role: provider.for_role(role),
        deep_executor=deep_executor,
        materializer=materializer,
        provider_product_authorized=True,
    )
    return core, product, orchestrator, receipt


def _install_web_provider(
    core: Application,
    inner: InnerResearchService,
    product: ResearchProductService,
    orchestrator: ReceiptBoundResearchProductOrchestrator,
    receipt: ReceiptBoundProviderService,
) -> None:
    core._research_inner = inner
    core._research_product = product
    core._research_provider_inner = inner
    core._research_provider_product = product
    core._research_provider_receipts = receipt
    core._research_provider_orchestrator = orchestrator
    core.provider_research_availability = lambda: {
        "available": True,
        "reason": "test server authorization",
    }


def test_web_product_entry_runs_server_owned_receipt_bound_provider_journey(
    app_paths,
) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider()
    orchestrator, receipt = _orchestrator(
        core, inner, product, materializer, provider
    )
    _install_web_provider(core, inner, product, orchestrator, receipt)
    client = TestClient(create_web_app(core))

    forbidden = client.post(
        "/api/research/product/tasks",
        json={
            "command_id": "web-provider-forbidden-client-authority",
            "objective": GROUNDED_OBJECTIVE,
            "execution_mode": "provider",
        },
    )
    assert forbidden.status_code == 422

    created = client.post(
        "/api/research/product/tasks",
        json={
            "command_id": "web-provider-grounded",
            "objective": GROUNDED_OBJECTIVE,
            "success_constraints": [GROUNDED_CONSTRAINT],
            "run_immediately": True,
        },
    )
    assert created.status_code == 202
    task_id = str(created.json()["outcome"]["task_id"])
    detail = client.get(f"/api/research/product/tasks/{task_id}")
    assert detail.status_code == 200
    projected = detail.json()["product"]
    raw = core.research.get_task(task_id)

    assert projected["task"]["status"] == "terminal"
    assert "user_completion" in projected, ",".join(sorted(projected))
    assert projected["user_completion"]["product_execution"] == (
        "receipt_bound_provider"
    )
    assert projected["user_completion"]["objective_verified"] is False
    assert projected["citations"]
    assert "模型驱动研究结论" in projected["plain_summary"]["found"]
    assert raw["outer_audits"] == []
    assert raw["results"]
    policy = raw["goals"][0]["evidence_policy"]
    assert policy["provider_authority"] == "server_product_action"
    assert policy["provider_run_budget"]["policy_hash"]
    assert all(value["status"] == "succeeded" for value in raw["side_effects"])
    assert receipt.budget_snapshot(task_id).logical_calls == len(provider.calls)
    calls = list(provider.calls)
    replay = client.post(
        f"/api/research/product/tasks/{task_id}/run",
        json={"command_id": "client-command-cannot-rekey-provider-run"},
    )
    assert replay.status_code == 202
    assert replay.json()["run_command_id"] == (
        f"web:provider-research:{task_id}:run"
    )
    assert provider.calls == calls
    rejected_retry = client.post(
        f"/api/research/product/tasks/{task_id}/retry",
        json={"command_id": "web-provider-success-is-not-retryable"},
    )
    assert rejected_retry.status_code == 409


def test_interrupted_in_flight_provider_call_projects_blocked_before_replay(
    app_paths,
) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider()

    def crash(point: str) -> None:
        if point == "before_provider_factory":
            raise SimulatedCrash(point)

    receipt = ReceiptBoundProviderService(
        db=core.db,
        kernel=core.research,
        provider_dispatch_authorized=True,
        fault_injector=crash,
    )
    orchestrator = ReceiptBoundResearchProductOrchestrator(
        db=core.db,
        kernel=core.research,
        inner=inner,
        product=product,
        receipt_service=receipt,
        provider_factory=lambda role: provider.for_role(role),
        deep_executor=_BoundedMockDeepExecutor(core.db),
        materializer=materializer,
        provider_product_authorized=True,
    )
    task_id = _create(product, "web-interrupted-in-flight", GROUNDED_OBJECTIVE)

    with pytest.raises(SimulatedCrash, match="before_provider_factory"):
        orchestrator.run_to_boundary(
            task_id,
            command_id=f"web:provider-research:{task_id}:run",
        )
    raw = core.research.get_task(task_id)
    projected = product.get_task(task_id)

    assert raw["task"]["status"] == "running"
    assert raw["side_effects"][-1]["status"] == "in_flight"
    assert projected["user_completion"]["status"] == "blocked"
    assert projected["provider_status"] == "provider_call_outcome_unresolved"
    assert "不会自动重试" in projected["plain_summary"]["why_stopped"]
    assert "中断当前运行" in projected["plain_summary"]["next_action"]


def test_known_failed_product_retry_uses_same_task_and_new_attempt(app_paths) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider(known_failures=1)
    orchestrator, receipt = _orchestrator(
        core, inner, product, materializer, provider
    )
    _install_web_provider(core, inner, product, orchestrator, receipt)
    client = TestClient(create_web_app(core))

    created = client.post(
        "/api/research/product/tasks",
        json={
            "command_id": "web-provider-known-failure",
            "objective": GROUNDED_OBJECTIVE,
            "run_immediately": True,
        },
    )
    task_id = str(created.json()["outcome"]["task_id"])
    failed = core.research.get_task(task_id)
    old_attempt = dict(failed["attempts"][0])
    old_result = dict(failed["results"][0])
    assert failed["task"]["status"] == "ready"
    assert failed["task"]["terminal_result_id"] is None
    assert old_result["failure_class"] == "provider_failure"
    assert old_result["termination_reason"] == "provider_error"
    assert old_result["is_task_terminal"] == 0
    assert product.get_task(task_id)["control"]["allowed_operations"] == ["retry"]

    retried = client.post(
        f"/api/research/product/tasks/{task_id}/retry",
        json={"command_id": "web-provider-known-failure-retry"},
    )
    assert retried.status_code == 202
    assert retried.json()["outcome"]["task_id"] == task_id
    assert retried.json()["href"] == f"/research/{task_id}"
    settled = core.research.get_task(task_id)
    assert settled["task"]["parent_task_id"] is None
    assert len(settled["goals"]) == 1
    assert [value["ordinal"] for value in settled["attempts"]] == [1, 2]
    assert settled["attempts"][1]["cause"] == "retry"
    assert settled["attempts"][1]["parent_attempt_id"] == old_attempt["attempt_id"]
    assert settled["attempts"][0] == old_attempt
    assert settled["results"][0] == old_result
    assert settled["results"][1]["attempt_id"] == settled["attempts"][1]["attempt_id"]


def test_web_concurrent_provider_trigger_does_not_terminalize_active_run(
    app_paths,
) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider()
    orchestrator, receipt = _orchestrator(
        core, inner, product, materializer, provider
    )

    class _ClaimThenConflict:
        def run_to_boundary(self, task_id: str, **_: Any) -> None:
            task = core.research.get_task(task_id)["task"]
            core.research.claim_owner(
                task_id=task_id,
                command_id=f"test:claim:{task_id}",
                owner_id=product.runner_id,
                expected_state_version=int(task["state_version"]),
                lease_seconds=product.LEASE_SECONDS,
            )
            task = core.research.get_task(task_id)["task"]
            core.research.start_attempt(
                task_id=task_id,
                command_id=f"test:start:{task_id}",
                owner_id=product.runner_id,
                owner_epoch=int(task["owner_epoch"]),
                expected_state_version=int(task["state_version"]),
                cause=AttemptCause.INITIAL,
            )
            raise ResearchConflict("concurrent provider trigger")

    _install_web_provider(core, inner, product, orchestrator, receipt)
    core._research_provider_orchestrator = _ClaimThenConflict()
    client = TestClient(create_web_app(core))

    created = client.post(
        "/api/research/product/tasks",
        json={
            "command_id": "web-provider-concurrent-trigger",
            "objective": GROUNDED_OBJECTIVE,
            "run_immediately": True,
        },
    )
    assert created.status_code == 202
    task_id = str(created.json()["outcome"]["task_id"])
    raw = core.research.get_task(task_id)

    assert raw["task"]["status"] == "running"
    assert raw["task"]["owner_id"] == product.runner_id
    assert raw["attempts"][-1]["status"] == "running"
    assert raw["results"] == []


def test_web_provider_unknown_is_terminal_honest_and_not_replayed(app_paths) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider(fail_transport=True)
    orchestrator, receipt = _orchestrator(
        core, inner, product, materializer, provider
    )
    _install_web_provider(core, inner, product, orchestrator, receipt)
    client = TestClient(create_web_app(core))

    created = client.post(
        "/api/research/product/tasks",
        json={
            "command_id": "web-provider-unknown",
            "objective": GROUNDED_OBJECTIVE,
            "run_immediately": True,
        },
    )
    assert created.status_code == 202
    task_id = str(created.json()["outcome"]["task_id"])
    projected = client.get(
        f"/api/research/product/tasks/{task_id}"
    ).json()["product"]
    raw = core.research.get_task(task_id)

    assert projected["task"]["status"] == "blocked"
    assert projected["user_completion"]["status"] == "blocked"
    assert projected["user_completion"]["objective_verified"] is False
    assert projected["control"]["unresolved_side_effects"][0]["status"] == "unknown"
    assert [value["status"] for value in raw["side_effects"]] == ["unknown"]
    assert provider.calls == ["agent_action"]


@pytest.mark.parametrize(
    "objective,answer_status",
    [
        (GROUNDED_OBJECTIVE, "complete"),
        (GROUNDED_OBJECTIVE, "partial"),
        ("无法由当前字幕证明的目标", "insufficient"),
    ],
)
def test_provider_product_grounded_and_insufficient_close_durable_lineage(
    app_paths, objective: str, answer_status: str
) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider()
    orchestrator, receipt = _orchestrator(
        core,
        inner,
        product,
        materializer,
        provider,
        insufficient_objectives=(
            {objective} if answer_status == "insufficient" else set()
        ),
        complete_objectives={objective} if answer_status == "complete" else set(),
    )
    task_id = _create(product, answer_status, objective)
    inner.grounded_validator = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("Research must not revalidate Deep AskResponse")
    )
    product.outer.advance = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("Provider completion must not enter Outer")
    )

    result = orchestrator.run_to_boundary(
        task_id, command_id=f"gate-b-product:run:{objective}"
    )
    assert result["task_status"] == "terminal"
    raw = core.research.get_task(task_id)
    assert raw["task"]["status"] == "terminal"
    assert raw["checkpoints"]
    assert raw["outer_audits"] == []
    assert raw["traces"]
    artifact = raw["provisional_artifacts"][-1]
    assert artifact["provider_side_effect_id"]
    expected_result_status = {
        "complete": "valid_success",
        "partial": "valid_partial",
        "insufficient": "valid_insufficient",
    }[answer_status]
    assert artifact["answer_status"] == expected_result_status
    assert raw["traces"][-1]["ended_at"] is not None
    assert raw["results"][-1]["is_task_terminal"] == 1
    assert raw["results"][-1]["answer_status"] == expected_result_status
    assert raw["results"][-1]["attempt_id"] == raw["attempts"][-1]["attempt_id"]
    assert raw["results"][-1]["checkpoint_id"] == artifact["checkpoint_id"]
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_outer_result_links WHERE task_id=?",
            (task_id,),
        ).fetchone()[0] == 0

    restarted = Application(app_paths)
    projection = restarted.research_product.get_task(task_id)
    assert projection["state"]["answer_status"] == expected_result_status
    assert projection["answer_blocks"] == artifact["answer_blocks"]
    assert projection["limitations"] == artifact["limitations"]
    assert [value["citation_id"] for value in projection["citations"]] == artifact[
        "evidence_ids"
    ]
    assert projection["user_completion"]["objective_verified"] is False
    assert projection["provider_status"] == "boundary_recorded_not_call_verified"
    before_calls = list(provider.calls)
    before_budget = receipt.budget_snapshot(task_id)
    replay = orchestrator.run_to_boundary(
        task_id, command_id=f"gate-b-product:run:{objective}"
    )
    assert replay["deduplicated"] is True
    assert provider.calls == before_calls
    assert receipt.budget_snapshot(task_id) == before_budget


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
    assert raw["events"][-1]["event_type"] == "provider_call_unknown"
    assert raw["inner_actions"][-1]["error_code"] == "provider_dispatch_unknown"

    forbidden_deep = _ForbiddenRecoveryDeepExecutor()
    restarted_provider = _ProductMockProvider()
    restarted_core, restarted_product, restarted, _restarted_receipt = (
        _fresh_orchestrator(app_paths, restarted_provider, forbidden_deep)
    )
    replay = restarted.run_to_boundary(
        task_id, command_id="gate-b-product:unknown:different-command"
    )
    assert replay["task_status"] == "blocked"
    assert len(provider.calls) == 1
    assert restarted_provider.calls == []
    assert all(value == 0 for value in forbidden_deep.incremental_calls.values())
    with pytest.raises(ResearchConflict, match="known-failed"):
        restarted_product.retry_provider_attempt(
            task_id, command_id="gate-b-product:unknown:retry"
        )
    restarted_raw = restarted_core.research.get_task(task_id)
    assert restarted_raw["task"]["status"] == "blocked"
    assert restarted_raw["side_effects"][-1]["status"] == "unknown"
    assert len(restarted_raw["attempts"]) == 1


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
    assert result["task_status"] == "terminal"
    # The unchanged Deep finalizer correctly skips grounded generation when it
    # has no admissible evidence context; the preceding real roles remain receipted.
    assert provider.calls == ["agent_action"]
    raw = core.research.get_task(task_id)
    artifact = raw["provisional_artifacts"][-1]
    assert artifact["answer_status"] == "valid_insufficient"
    assert raw["attempts"][-1]["status"] == "terminal"
    assert raw["results"][-1]["answer_status"] == "valid_insufficient"
    assert raw["results"][-1]["checkpoint_id"] == artifact["checkpoint_id"]
    assert raw["outer_audits"] == []
    projection = product.get_task(task_id)
    assert projection["state"]["answer_status"] == "valid_insufficient"
    assert projection["answer_blocks"] == artifact["answer_blocks"] == []
    assert projection["citations"] == []
    assert projection["limitations"] == artifact["limitations"]


def test_generation_failed_ask_response_preserves_provider_failure_mapping(
    app_paths,
) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider()
    receipt = ReceiptBoundProviderService(
        db=core.db,
        kernel=core.research,
        provider_dispatch_authorized=True,
    )
    orchestrator = ReceiptBoundResearchProductOrchestrator(
        db=core.db,
        kernel=core.research,
        inner=inner,
        product=product,
        receipt_service=receipt,
        provider_factory=lambda role: provider.for_role(role),
        deep_executor=_GenerationFailedDeepExecutor(),
        materializer=materializer,
        provider_product_authorized=True,
    )
    task_id = _create(product, "generation-failed-mapping", GROUNDED_OBJECTIVE)

    result = orchestrator.run_to_boundary(
        task_id, command_id="gate-b-product:generation-failed-mapping"
    )
    raw = core.research.get_task(task_id)
    mapped = raw["results"][-1]
    projection = product.get_task(task_id)

    assert result["task_status"] == "ready"
    assert mapped["answer_status"] == "not_produced"
    assert mapped["termination_reason"] == "provider_error"
    assert mapped["failure_class"] == "provider_failure"
    assert mapped["is_task_terminal"] == 0
    assert projection["user_completion"]["status"] == "failed_execution"
    assert projection["control"]["allowed_operations"] == ["retry"]


def test_empty_navigation_real_product_path_commits_current_evidence_no_network(
    app_paths,
) -> None:
    core, _fixture_inner, _fixture_product, materializer = _fixture(app_paths)
    provider = _EmptyNavigationProductProvider()
    inner = InnerResearchService(
        db=core.db,
        kernel=core.research,
        tools=core.research_inner.tools,
        materializer=materializer,
        provider_runs_authorized=True,
    )
    product = ResearchProductService(
        db=core.db,
        kernel=core.research,
        inner=inner,
        outer=core.research_outer,
        control=core.research_control,
        runner_id="empty-navigation-product-worker",
    )
    receipt = ReceiptBoundProviderService(
        db=core.db,
        kernel=core.research,
        role_token_caps={"grounded_answer": 8192},
        provider_dispatch_authorized=True,
    )
    product_search = core.product_search
    original_search = product_search.search

    def empty_navigation_only(request, *, video_ids=()):
        response = original_search(request, video_ids=video_ids)
        if request.scope != "video":
            return response
        return replace(
            response,
            returned_group_count=0,
            results=(),
        )

    product_search.search = empty_navigation_only
    deep = ReceiptBoundDeepResearchExecutor(
        db=core.db,
        artifacts=core.artifacts,
        product_search=product_search,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
        budget=DeepSearchBudget(
            max_decision_rounds=3,
            max_tool_calls=3,
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
    task_id = product.create_provider_task(
        CreateProductResearchRequest(
            command_id="empty-navigation-product:create",
            objective="用任意措辞说明 checkpoint 的人工验收作用",
            success_constraints=[],
            constraint_profile="grounded_current_evidence",
            run_immediately=False,
        )
    )["task_id"]
    product.outer.advance = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("Provider completion must not enter Outer")
    )

    result = orchestrator.run_to_boundary(
        task_id,
        command_id="empty-navigation-product:run",
        max_logical_calls=5,
        max_http_attempts=10,
    )

    raw = core.research.get_task(task_id)
    assert raw["outer_audits"] == []
    assert result["task_status"] == "terminal"
    assert raw["evidence_uses"]
    assert raw["evidence_validations"]
    assert {
        value["outcome"] for value in raw["evidence_validations"]
    } == {"current"}
    artifact = raw["provisional_artifacts"][-1]
    assert artifact["answer_blocks"][0]["citation_ids"]
    assert raw["results"][-1]["answer_status"] == "valid_success"
    assert raw["results"][-1]["checkpoint_id"] == artifact["checkpoint_id"]
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_outer_result_links WHERE task_id=?",
            (task_id,),
        ).fetchone()[0] == 0
    projection = product.get_task(task_id)
    assert projection["state"]["answer_status"] == "valid_success"
    assert projection["answer_blocks"] == artifact["answer_blocks"]
    assert [value["citation_id"] for value in projection["citations"]] == artifact[
        "evidence_ids"
    ]
    assert projection["limitations"] == artifact["limitations"]
    assert projection["user_completion"]["objective_verified"] is False
    assert provider.calls == [
        "agent_action",
        "agent_action",
        "grounded_answer",
    ]


def test_case_l_cross_instance_receipt_bound_local_recovery(
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
    carrier = next(
        value for value in raw["command_receipts"]
        if value["command_type"] == "provider_deep_finalized"
    )
    attempt_id = raw["attempts"][-1]["attempt_id"]
    assert raw["attempts"][-1]["result_id"] is None
    assert raw["task"]["terminal_result_id"] is None
    assert not any(
        value["attempt_id"] == attempt_id for value in raw["results"]
    )
    assert not any(
        value["attempt_id"] == attempt_id
        and value["state_payload"].get("phase") == "complete"
        for value in raw["checkpoints"]
    )
    assert carrier["response"]["attempt_id"] == attempt_id
    durable_response = AskResponse.model_validate(carrier["response"]["response"])
    durable_citation = durable_response.citations[0]
    provider_receipt = next(
        value for value in raw["command_receipts"]
        if value["command_type"] == "provider_call_receipted"
        and value["response"]["receipt_binding"]["role"] == "grounded_answer"
    )
    provider_binding = provider_receipt["response"]["receipt_binding"]
    calls = list(provider.calls)
    budget = receipt.budget_snapshot(task_id)
    old_epoch = int(raw["task"]["owner_epoch"])
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE research_tasks SET lease_until=? WHERE task_id=?",
            ("2000-01-01T00:00:00+00:00", task_id),
        )

    forbidden_deep = _ForbiddenRecoveryDeepExecutor()
    recovery_provider = _ProductMockProvider()
    recovered_core, _recovered_product, recovered, recovered_receipt = (
        _fresh_orchestrator(
            app_paths,
            recovery_provider,
            forbidden_deep,
            runner_id="gate-b-product-worker-restarted",
        )
    )
    replay = recovered.run_to_boundary(
        task_id, command_id="gate-b-product:fault-replay"
    )
    assert replay["task_status"] == "terminal"
    assert provider.calls == calls
    assert recovery_provider.calls == []
    assert recovered_receipt.budget_snapshot(task_id) == budget
    assert all(value == 0 for value in forbidden_deep.incremental_calls.values())
    raw = recovered_core.research.get_task(task_id)
    assert int(raw["task"]["owner_epoch"]) > old_epoch
    assert len(raw["provisional_artifacts"]) == 1
    assert raw["outer_audits"] == []
    artifact = raw["provisional_artifacts"][0]
    result = raw["results"][0]
    assert result["attempt_id"] == attempt_id
    assert result["checkpoint_id"] == artifact["checkpoint_id"]
    assert all(value["attempt_id"] == attempt_id for value in raw["side_effects"])
    assert carrier["response"]["checkpoint_id"] in {
        value["checkpoint_id"] for value in raw["checkpoints"]
    }
    with recovered_core.db.connect() as connection:
        identity = connection.execute(
            "SELECT * FROM research_evidence_identities WHERE evidence_id=?",
            (durable_citation.citation_id,),
        ).fetchone()
    assert identity is not None
    assert str(identity["evidence_id"]) == durable_citation.citation_id
    assert str(identity["source_artifact_id"]) == durable_citation.source_artifact_id
    assert str(identity["source_version"]) == durable_citation.source_version
    assert json.loads(str(identity["segment_ids_json"])) == durable_citation.segment_ids
    assert float(identity["start_time"]) == durable_citation.start_time
    assert float(identity["end_time"]) == durable_citation.end_time

    provider_effect = next(
        value for value in raw["side_effects"]
        if value["side_effect_id"] == artifact["provider_side_effect_id"]
    )
    final_provider_receipt = next(
        value for value in raw["command_receipts"]
        if value["command_type"] == "provider_call_receipted"
        and value["outcome_reference"] == provider_effect["result_reference"]
    )
    final_provider_binding = final_provider_receipt["response"]["receipt_binding"]
    assert provider_effect["provider_operation_id"] == provider_binding[
        "provider_operation_id"
    ]
    assert provider_effect["receipt_hash"] == provider_binding["receipt_hash"]
    assert provider_effect["result_reference"] == provider_binding["result_reference"]
    assert final_provider_binding["usage"] == provider_binding["usage"]
    assert final_provider_binding["cost_usd"] == provider_binding["cost_usd"]

    reread = Application(app_paths).research_product.get_task(task_id)
    assert reread["task"]["status"] == "terminal"
    assert reread["result"]["result_id"] == result["result_id"]
    assert reread["answer_blocks"] == artifact["answer_blocks"]


def test_new_owner_completes_ingested_provider_window_without_new_call(
    app_paths,
) -> None:
    fired = False

    def crash_after_ingest(point: str) -> None:
        nonlocal fired
        if point == "after_provider_ingest_commit" and not fired:
            fired = True
            raise SimulatedCrash(point)

    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider()
    orchestrator, receipt = _orchestrator(
        core,
        inner,
        product,
        materializer,
        provider,
        fault_injector=crash_after_ingest,
    )
    task_id = _create(product, "ingested-completion-window", GROUNDED_OBJECTIVE)
    with pytest.raises(SimulatedCrash, match="after_provider_ingest_commit"):
        orchestrator.run_to_boundary(
            task_id, command_id="gate-b-product:ingested-completion-window"
        )
    before = core.research.get_task(task_id)
    attempt_id = str(before["attempts"][-1]["attempt_id"])
    assert before["attempts"][-1]["status"] != "terminal"
    assert any(
        checkpoint["attempt_id"] == attempt_id
        and checkpoint["state_payload"].get("phase") == "complete"
        for checkpoint in before["checkpoints"]
    )
    assert not any(result["attempt_id"] == attempt_id for result in before["results"])
    calls = list(provider.calls)
    budget = receipt.budget_snapshot(task_id)
    old_epoch = int(before["task"]["owner_epoch"])
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE research_tasks SET lease_until=? WHERE task_id=?",
            ("2000-01-01T00:00:00+00:00", task_id),
        )

    recovery_provider = _ProductMockProvider()
    recovered_core, _product, recovered, recovered_receipt = _fresh_orchestrator(
        app_paths,
        recovery_provider,
        _ForbiddenRecoveryDeepExecutor(),
        runner_id="gate-b-ingest-window-restarted",
    )
    outcome = recovered.run_to_boundary(
        task_id, command_id="gate-b-product:ingested-completion-window"
    )
    after = recovered_core.research.get_task(task_id)

    assert outcome["task_status"] == "terminal"
    assert int(after["task"]["owner_epoch"]) > old_epoch
    assert len(after["results"]) == 1
    assert after["results"][0]["attempt_id"] == attempt_id
    assert provider.calls == calls
    assert recovery_provider.calls == []
    assert recovered_receipt.budget_snapshot(task_id) == budget


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
            max_logical_calls=1,
        )
    assert provider.calls == ["agent_action"]
    with pytest.raises(ResearchUnsafeState, match="logical-call cap"):
        orchestrator.run_to_boundary(
            task_id,
            command_id="gate-b-product:logical-cap",
            max_logical_calls=1,
        )
    assert provider.calls == ["agent_action"]


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
    grounded_task = product.create_provider_task(
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
    assert grounded_raw["outer_audits"] == []

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
    hitl_task = product.create_provider_task(
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


def test_completion_runner_persists_run_budget_before_mock_transport(
    app_paths,
) -> None:
    core, inner, product, materializer = _fixture(app_paths)
    provider = _ProductMockProvider()
    orchestrator, receipt = _orchestrator(
        core, inner, product, materializer, provider
    )
    run_id = "GB-PC-no-network-budget-binding"
    case_ids = ("GB-PC-G-01", "GB-PC-H-01")
    task_ids = tuple(RUNNER._completion_task_id(run_id, value) for value in case_ids)
    envelope = RUNNER._run_envelope(completion=True)
    policy = ProviderRunBudgetPolicy(
        run_id=run_id,
        task_ids=task_ids,
        started_at=datetime.now(timezone.utc).isoformat(),
        max_logical_calls=envelope["max_logical_calls"],
        max_http_attempts=envelope["max_http_attempts"],
        max_input_tokens=envelope["max_input_tokens"],
        max_output_tokens=envelope["max_output_tokens"],
        max_wall_seconds=envelope["max_wall_seconds"],
        reserve_stop_usd=envelope["reserve_stop_usd"],
        absolute_max_cost_usd=envelope["absolute_max_cost_usd"],
    )
    cases = (
        {
            "case_id": "GB-PC-G-01",
            "objective": GROUNDED_OBJECTIVE,
            "success_constraints": [],
        },
        {
            "case_id": "GB-PC-H-01",
            "objective": AMBIGUOUS_OBJECTIVE,
            "success_constraints": ["继续前需要用户选择（mock）"],
        },
    )
    for case, task_id in zip(cases, task_ids, strict=True):
        created = RUNNER._create_completion_provider_task(
            kernel=core.research,
            run_id=run_id,
            case=case,
            run_policy=policy,
        )
        assert created["task_id"] == task_id

    result = orchestrator.run_to_boundary(
        task_ids[0],
        command_id="completion-test:bound-provider-budget",
        max_logical_calls=5,
        max_http_attempts=10,
        max_input_tokens=40_000,
        max_output_tokens=8_896,
        max_wall_time_seconds=660,
        run_budget=policy,
    )

    assert result["task_status"] == "terminal"
    assert provider.calls
    aggregate = receipt.run_budget_snapshot(policy)
    assert aggregate.committed_logical_calls == len(provider.calls)
    assert aggregate.task_ids == tuple(sorted(task_ids))
