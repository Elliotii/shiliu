from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
import hashlib
import json
from typing import Any, Callable

from shiliu.artifacts import ArtifactStore
from shiliu.ask.contracts import AskRequest, AskResponse, TranscriptEvidenceSpan
from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.deep.service import DeepSearchService
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.query_analysis import QueryAnalyzer, QueryPlan
from shiliu.db import Database
from shiliu.research.errors import (
    ResearchConflict,
    ResearchUnsafeState,
    ResearchValidationError,
)
from shiliu.research.inner_contracts import ContinueInnerResearchRequest
from shiliu.research.inner_service import InnerResearchService
from shiliu.research.product_contracts import RunProductResearchRequest
from shiliu.research.product_service import ResearchProductService
from shiliu.research.provider_wiring import (
    ProviderCallContext,
    ReceiptBoundProviderFactory,
    ReceiptBoundProviderService,
)
from shiliu.research.schema import INNER_RESEARCH_STATE_SCHEMA_VERSION
from shiliu.research.service import ResearchTaskService
from shiliu.retrieval.product_search import ProductSearchService


ProviderFactory = Callable[[str], object]
PROVIDER_PRODUCT_ORCHESTRATION_VERSION = "v5-a-gate-b-product-orchestration-v1"


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _command(parent: str, operation: str, *parts: object) -> str:
    digest = _hash({"parent": parent, "operation": operation, "parts": parts})[:32]
    return f"gate-b-product:{operation}:{digest}"


@dataclass(frozen=True)
class DurableDeepResearchOutput:
    query_plan: QueryPlan
    response: AskResponse
    trace: dict[str, Any]


class ReceiptBoundDeepResearchExecutor:
    """Run the unchanged V4 Deep structured roles behind durable receipts."""

    def __init__(
        self,
        *,
        db: Database,
        artifacts: ArtifactStore,
        product_search: ProductSearchService,
        runtime_corpus_identity: str | None,
        budget: DeepSearchBudget,
    ) -> None:
        self.db = db
        self.artifacts = artifacts
        self.product_search = product_search
        self.runtime_corpus_identity = runtime_corpus_identity
        self.budget = budget

    def execute(
        self,
        *,
        objective: str,
        provider_factory: ReceiptBoundProviderFactory,
    ) -> DurableDeepResearchOutput:
        plan = QueryAnalyzer(provider_factory).analyze(objective)
        if plan.error:
            raise ResearchUnsafeState(f"query_analysis failed: {plan.error}")
        deep = DeepSearchService(
            db=self.db,
            artifacts=self.artifacts,
            product_search=self.product_search,
            provider_factory=provider_factory,
            runtime_corpus_identity=self.runtime_corpus_identity,
            budget=self.budget,
        )
        response, trace = deep.ask(AskRequest(query=objective, mode="deep"))
        return DurableDeepResearchOutput(
            query_plan=plan,
            response=response,
            trace=dict(trace),
        )


class ReceiptBoundResearchProductOrchestrator:
    """Bridge real structured calls into Stage 2–4 durable product semantics.

    The class is intentionally absent from the public Gate A API. Construction
    requires explicit Provider dispatch and Provider-ingest authority; the normal
    product runner remains deterministic and credential-free.
    """

    MAX_PREPARATION_STEPS = 8
    MAX_CONTINUATION_CYCLES = 2

    def __init__(
        self,
        *,
        db: Database,
        kernel: ResearchTaskService,
        inner: InnerResearchService,
        product: ResearchProductService,
        receipt_service: ReceiptBoundProviderService,
        provider_factory: ProviderFactory,
        deep_executor: ReceiptBoundDeepResearchExecutor,
        materializer: TranscriptEvidenceMaterializer | None = None,
        provider_product_authorized: bool = False,
    ) -> None:
        self.db = db
        self.kernel = kernel
        self.inner = inner
        self.product = product
        self.receipt_service = receipt_service
        self.provider_factory = provider_factory
        self.deep_executor = deep_executor
        self.materializer = materializer or TranscriptEvidenceMaterializer(db)
        self.provider_product_authorized = provider_product_authorized

    def run_to_boundary(
        self,
        task_id: str,
        *,
        command_id: str,
        max_continuation_cycles: int = 1,
        max_logical_calls: int = 17,
        max_http_attempts: int = 34,
    ) -> dict[str, Any]:
        if not self.provider_product_authorized:
            raise ResearchConflict("Provider product orchestration is not authorized")
        if not self.receipt_service.provider_dispatch_authorized:
            raise ResearchConflict("Provider dispatch is not authorized")
        if not self.inner.provider_runs_authorized:
            raise ResearchConflict("Provider inner ingest is not authorized")
        if not 1 <= max_continuation_cycles <= self.MAX_CONTINUATION_CYCLES:
            raise ResearchValidationError("max_continuation_cycles must be 1..2")
        if not 1 <= max_logical_calls <= 17 or not 1 <= max_http_attempts <= 34:
            raise ResearchValidationError(
                "Provider product call caps exceed the accepted Gate B envelope"
            )
        payload_hash = _hash(
            {
                "operation": "run_receipt_bound_research_product",
                "version": PROVIDER_PRODUCT_ORCHESTRATION_VERSION,
                "task_id": task_id,
                "command_id": command_id,
                "max_continuation_cycles": max_continuation_cycles,
                "max_logical_calls": max_logical_calls,
                "max_http_attempts": max_http_attempts,
            }
        )
        with self.kernel._transaction() as connection:
            self.kernel._task(connection, task_id)
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}

        provider_cycles = 0
        while provider_cycles < max_continuation_cycles:
            boundary = self._prepare_inner(task_id, command_id, provider_cycles)
            if boundary is not None:
                return self._finish(
                    task_id=task_id,
                    command_id=command_id,
                    payload_hash=payload_hash,
                    boundary=boundary,
                    provider_cycles=provider_cycles,
                )
            raw = self.kernel.get_task(task_id)
            task = raw["task"]
            attempt = self._active_attempt(raw)
            checkpoint = self._latest_attempt_checkpoint(raw, attempt["attempt_id"])
            goal = next(
                value
                for value in raw["goals"]
                if value["goal_id"] == attempt["goal_id"]
            )
            context = ProviderCallContext(
                task_id=task_id,
                attempt_id=str(attempt["attempt_id"]),
                owner_id=self.product.runner_id,
                owner_epoch=int(task["owner_epoch"]),
                expected_state_version=int(task["state_version"]),
                expected_checkpoint_id=str(checkpoint["checkpoint_id"]),
                expected_control_generation=int(task["control_generation"]),
                operation_key=_command(
                    command_id, "provider", attempt["attempt_id"], provider_cycles
                ),
                max_logical_calls=max_logical_calls,
                max_http_attempts=max_http_attempts,
            )
            bound = self.receipt_service.factory(
                context=context,
                provider_factory=self.provider_factory,
            )
            output = self.deep_executor.execute(
                objective=str(goal["objective"]),
                provider_factory=bound,
            )
            spans = self._reconstruct_spans(output)
            current_task = self.kernel.get_task(task_id)["task"]
            if (
                int(current_task["state_version"]) != context.expected_state_version
                or int(current_task["control_generation"])
                != context.expected_control_generation
            ):
                raise ResearchConflict(
                    "Task/control generation changed before Provider artifact ingest"
                )
            committed = self.inner.commit_provider_synthesis(
                task_id,
                ContinueInnerResearchRequest(
                    command_id=_command(
                        command_id,
                        "ingest",
                        attempt["attempt_id"],
                        provider_cycles,
                    ),
                    attempt_id=str(attempt["attempt_id"]),
                    owner_id=self.product.runner_id,
                    owner_epoch=int(current_task["owner_epoch"]),
                    expected_state_version=int(current_task["state_version"]),
                    expected_checkpoint_id=str(checkpoint["checkpoint_id"]),
                    execution_mode="provider",
                ),
                response=output.response,
                spans=spans,
                receipt_bindings=bound.receipt_bindings,
                trace=output.trace,
                provider_operation_prefix=context.operation_key,
            )
            provider_cycles += 1
            if committed.get("phase") == "stopped":
                return self._finish(
                    task_id=task_id,
                    command_id=command_id,
                    payload_hash=payload_hash,
                    boundary="durable_inner_stop",
                    provider_cycles=provider_cycles,
                )
            outer = self.product.run_to_boundary(
                task_id,
                RunProductResearchRequest(
                    command_id=_command(
                        command_id,
                        "outer-boundary",
                        attempt["attempt_id"],
                        provider_cycles,
                    ),
                    max_steps=1,
                ),
            )
            status = str(self.kernel.get_task(task_id)["task"]["status"])
            if status in {"terminal", "waiting_user", "blocked"}:
                return self._finish(
                    task_id=task_id,
                    command_id=command_id,
                    payload_hash=payload_hash,
                    boundary=str(outer["boundary"]),
                    provider_cycles=provider_cycles,
                    provider_artifact_id=str(
                        committed["provisional_artifact_id"]
                    ),
                )
        return self._finish(
            task_id=task_id,
            command_id=command_id,
            payload_hash=payload_hash,
            boundary="bounded_provider_continuation_yield",
            provider_cycles=provider_cycles,
        )

    def _prepare_inner(
        self, task_id: str, command_id: str, cycle: int
    ) -> str | None:
        for step in range(self.MAX_PREPARATION_STEPS):
            raw = self.kernel.get_task(task_id)
            status = str(raw["task"]["status"])
            if status in {"terminal", "waiting_user", "blocked"}:
                return "durable_boundary"
            attempt = self._active_attempt(raw, required=False)
            latest = next(
                (
                    value
                    for value in reversed(raw["checkpoints"])
                    if attempt is not None
                    and value["attempt_id"] == attempt["attempt_id"]
                ),
                None,
            )
            if (
                latest is not None
                and latest["state_schema_version"]
                == INNER_RESEARCH_STATE_SCHEMA_VERSION
                and latest["state_payload"].get("phase")
                == "provisional_synthesis"
            ):
                return None
            self.product.run_to_boundary(
                task_id,
                RunProductResearchRequest(
                    command_id=_command(
                        command_id,
                        "prepare",
                        cycle,
                        step,
                        raw["task"]["state_version"],
                    ),
                    max_steps=1,
                ),
            )
        raise ResearchUnsafeState(
            "durable inner loop did not reach Provider synthesis boundary"
        )

    def _reconstruct_spans(
        self, output: DurableDeepResearchOutput
    ) -> tuple[TranscriptEvidenceSpan, ...]:
        return tuple(
            self.materializer.reconstruct_citation(
                citation,
                execution_id=output.response.run_id,
                search_trace_id=str(output.trace.get("run_id") or output.response.run_id),
                query=str(output.trace.get("query") or ""),
            )
            for citation in output.response.citations
        )

    def _finish(
        self,
        *,
        task_id: str,
        command_id: str,
        payload_hash: str,
        boundary: str,
        provider_cycles: int,
        provider_artifact_id: str | None = None,
    ) -> dict[str, Any]:
        with self.kernel._transaction() as connection:
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}
            task = self.kernel._task(connection, task_id)
            latest = connection.execute(
                "SELECT checkpoint_id, attempt_id FROM research_checkpoints "
                "WHERE task_id=? ORDER BY created_at DESC, sequence DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            response = {
                "task_id": task_id,
                "boundary": boundary,
                "task_status": str(task["status"]),
                "state_version": int(task["state_version"]),
                "control_generation": int(task["control_generation"]),
                "provider_cycles": provider_cycles,
                "provider_artifact_id": provider_artifact_id,
            }
            now = self.kernel._now().astimezone(timezone.utc).isoformat(
                timespec="microseconds"
            )
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                attempt_id=str(latest["attempt_id"]) if latest else None,
                checkpoint_id=str(latest["checkpoint_id"]) if latest else None,
                event_type="provider_product_boundary",
                payload=response,
                command_id=command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            response["event_id"] = event_id
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type="provider_product_orchestration",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
        return {**response, "deduplicated": False}

    @staticmethod
    def _active_attempt(
        raw: dict[str, Any], *, required: bool = True
    ) -> dict[str, Any] | None:
        attempt = next(
            (
                value
                for value in reversed(raw["attempts"])
                if value["status"] != "terminal"
            ),
            None,
        )
        if attempt is None and required:
            raise ResearchUnsafeState("Task has no active Attempt")
        return attempt

    @staticmethod
    def _latest_attempt_checkpoint(
        raw: dict[str, Any], attempt_id: str
    ) -> dict[str, Any]:
        checkpoint = next(
            (
                value
                for value in reversed(raw["checkpoints"])
                if value["attempt_id"] == attempt_id
            ),
            None,
        )
        if checkpoint is None:
            raise ResearchUnsafeState("active Attempt has no durable checkpoint")
        return checkpoint
