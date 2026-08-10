from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from shiliu.ask.contracts import AskRequest
from shiliu.ask.deep.contracts import (
    AgentDecision,
    DeepSearchState,
    ReadTranscriptWindowAction,
    SearchNavigationAction,
    SearchTranscriptsAction,
    StopAction,
)
from shiliu.ask.deep.decision import AgentDecisionService, _decision_messages
from shiliu.ask.deep.graph import DeepSearchGraph
from shiliu.ask.deep.reducer import action_key
from shiliu.ask.deep.service import DeepSearchService
from shiliu.ask.query_analysis import QueryAnalyzer
from shiliu.research.errors import ResearchUnsafeState
from shiliu.research.provider_product import (
    DurableDeepResearchOutput,
    ReceiptBoundDeepResearchExecutor,
)
from shiliu.retrieval.planner import normalize_query


CANDIDATE_ID = "V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001"
CANDIDATE_VERSION = "1.0.0"
CANDIDATE_ARTIFACT_SHA256 = (
    "6bcda6e5c5428c304807f067570c9acb7977cbd991c355edaeb9346d3d13cdbe"
)
TREATMENT_VERSION = "v5-d-stage2-evidence-delta-followup-treatment-v1"
CANDIDATE_CONTEXT_VERSION = "v5-d-stage2-evidence-delta-context-v1"
CANDIDATE_INSTRUCTION = (
    "Stage-2 experiment treatment: after an evidence-seeking action adds zero "
    "current transcript evidence while an objective requirement remains open, "
    "choose at most one evidence-bearing recovery tied to that open requirement. "
    "The recovery must change the transcript source target or query scope, must "
    "not repeat an exact prior action key, and must stay inside the current "
    "corpus, provider, permissions, and budget. Navigation remains routing-only. "
    "After that one recovery, continue only if current transcript evidence grows; "
    "otherwise honestly stop. Do not use Gold, evaluator, split, reserve, or "
    "promotion information."
)
CANDIDATE_INSTRUCTION_SHA256 = hashlib.sha256(
    CANDIDATE_INSTRUCTION.encode("utf-8")
).hexdigest()


class CandidateIdentityError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_candidate_artifact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CandidateIdentityError("candidate artifact is missing")
    if sha256_file(path) != CANDIDATE_ARTIFACT_SHA256:
        raise CandidateIdentityError("candidate artifact hash mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "candidate_id": CANDIDATE_ID,
        "version": CANDIDATE_VERSION,
        "lifecycle_status": "proposed_non_active",
        "runtime_registration": None,
        "active": False,
        "shadow": False,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise CandidateIdentityError(f"candidate identity mismatch: {key}")
    return payload


def _hashed_action_key(decision: AgentDecision) -> str | None:
    key = action_key(decision)
    return hashlib.sha256(key.encode("utf-8")).hexdigest() if key else None


def _last_observation(state: DeepSearchState) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in reversed(state["events"])
            if event.get("event_type") == "observation"
        ),
        None,
    )


def _scope_terms(value: str) -> set[str]:
    normalized = normalize_query(value).casefold()
    return set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized))


def _query_scope_is_materially_new(previous: str, proposed: str) -> bool:
    left = normalize_query(previous).casefold()
    right = normalize_query(proposed).casefold()
    if not left or not right or left == right:
        return False
    return bool(_scope_terms(right) - _scope_terms(left))


class EvidenceDeltaFollowupDecisionService(AgentDecisionService):
    """Experiment-only decision adapter for the single frozen V5-D Candidate."""

    def __init__(
        self,
        provider_factory: Callable[[str], object],
        budget: object,
        *,
        clock: Callable[[], float],
        candidate_path: Path,
        source_index_runtime_health_valid: bool,
    ) -> None:
        super().__init__(provider_factory, budget, clock=clock)  # type: ignore[arg-type]
        validate_candidate_artifact(candidate_path)
        self.source_index_runtime_health_valid = source_index_runtime_health_valid
        self.recovery_used = False
        self.recovery_action_key: str | None = None
        self.audit: list[dict[str, Any]] = []

    def _applicable(self, state: DeepSearchState) -> bool:
        observation = _last_observation(state)
        return bool(
            self.source_index_runtime_health_valid
            and observation is not None
            and observation.get("observation_kind")
            in {"transcript_search", "transcript_window"}
            and not observation.get("new_segment_ids")
            and int(state["consecutive_no_new_evidence"]) >= 1
            and state["open_questions"]
            and not state["errors"]
            and not state["stale_reasons"]
            and state["termination_reason"] is None
            and state["tool_calls"] < self.budget.max_tool_calls
            and state["decision_rounds"] < self.budget.max_decision_rounds
        )

    def decide(self, state: DeepSearchState) -> tuple[AgentDecision, dict[str, Any]]:
        if not self._applicable(state):
            decision, metadata = super().decide(state)
            self.audit.append(
                {
                    "candidate_id": CANDIDATE_ID,
                    "applicable": False,
                    "baseline_fallback": True,
                    "selected_action_key_sha256": _hashed_action_key(decision),
                }
            )
            return decision, metadata

        if self.recovery_used:
            decision = AgentDecision(
                action=StopAction(
                    kind="stop",
                    summary=(
                        "one bounded Candidate recovery completed without current "
                        "transcript Evidence gain"
                    ),
                )
            )
            self.audit.append(
                {
                    "candidate_id": CANDIDATE_ID,
                    "applicable": True,
                    "recovery_ordinal": 1,
                    "honest_stop_after_zero_delta": True,
                    "provider_call_performed": False,
                }
            )
            return decision, {
                "finish_reason": "candidate_honest_stop",
                "usage": None,
                "latency_ms": 0,
                "response_id": None,
                "retry_count": 0,
            }

        provider = self.provider_factory("agent_action")
        now = self.clock()
        remaining = min(
            max(0.001, state["search_deadline"] - now),
            max(0.001, state["total_deadline"] - now),
        )
        messages = _decision_messages(
            state,
            self.budget,
            now=now,
            projector=self.projector,
        )
        messages[0] = {
            **messages[0],
            "content": messages[0]["content"] + "\n" + CANDIDATE_INSTRUCTION,
        }
        response = provider.generate_structured(  # type: ignore[attr-defined]
            role="agent_action",
            messages=messages,
            response_schema=AgentDecision,
            max_tokens=1200,
            timeout_seconds=remaining,
        )
        output = getattr(response, "output", response)
        proposed = (
            output
            if isinstance(output, AgentDecision)
            else AgentDecision.model_validate(output)
        )
        recovery = self._eligible_recovery(state, proposed)
        if recovery is None:
            selected = AgentDecision(
                action=StopAction(
                    kind="stop",
                    summary="no eligible materially new evidence-bearing target",
                ),
                open_questions=proposed.open_questions,
                resolved_questions=proposed.resolved_questions,
            )
            mode = "honest_stop_no_eligible_target"
        else:
            selected = AgentDecision(
                action=recovery,
                open_questions=proposed.open_questions,
                resolved_questions=proposed.resolved_questions,
            )
            self.recovery_used = True
            self.recovery_action_key = action_key(selected)
            mode = "bounded_recovery"
        self.audit.append(
            {
                "candidate_id": CANDIDATE_ID,
                "candidate_version": CANDIDATE_VERSION,
                "treatment_version": TREATMENT_VERSION,
                "candidate_context_version": CANDIDATE_CONTEXT_VERSION,
                "candidate_instruction_sha256": CANDIDATE_INSTRUCTION_SHA256,
                "applicable": True,
                "last_action_zero_current_evidence_delta": True,
                "unresolved_objective_work": True,
                "recovery_ordinal": 1 if recovery is not None else 0,
                "selection_mode": mode,
                "provider_call_performed": True,
                "proposed_action_key_sha256": _hashed_action_key(proposed),
                "selected_action_key_sha256": _hashed_action_key(selected),
                "materially_new_target": recovery is not None,
            }
        )
        return selected, {
            "finish_reason": getattr(response, "finish_reason", None),
            "usage": getattr(response, "usage", None),
            "latency_ms": getattr(response, "latency_ms", None),
            "response_id": getattr(response, "response_id", None),
            "retry_count": int(getattr(response, "retry_count", 0)),
        }

    def _eligible_recovery(
        self, state: DeepSearchState, proposed: AgentDecision
    ) -> SearchTranscriptsAction | ReadTranscriptWindowAction | None:
        previous_keys = set(state["repeated_action_keys"])
        last = state["last_action"] or {}
        last_query = str(last.get("query") or "")
        last_video_ids = {int(value) for value in last.get("video_ids") or []}

        if isinstance(proposed.action, ReadTranscriptWindowAction):
            key = action_key(proposed)
            if key is not None and key not in previous_keys:
                return proposed.action
        if isinstance(proposed.action, SearchTranscriptsAction):
            key = action_key(proposed)
            source_changed = set(proposed.action.video_ids) != last_video_ids
            query_changed = _query_scope_is_materially_new(
                last_query, proposed.action.query
            )
            if key is not None and key not in previous_keys and (
                source_changed or query_changed
            ):
                return proposed.action

        evidence_video_ids = {span.video_id for span in state["evidence_spans"]}
        remaining_documents = [
            document
            for document in state["navigation_documents"]
            if document.video_id not in last_video_ids
            and document.video_id not in evidence_video_ids
        ]
        proposed_query = (
            proposed.action.query
            if isinstance(
                proposed.action, (SearchNavigationAction, SearchTranscriptsAction)
            )
            else ""
        )
        if remaining_documents:
            query = proposed_query or last_query or state["open_questions"][0]
            candidate = SearchTranscriptsAction(
                kind="search_transcripts",
                query=query,
                video_ids=[remaining_documents[0].video_id],
            )
            key = action_key(AgentDecision(action=candidate))
            if key is not None and key not in previous_keys:
                return candidate

        expanded = state["open_questions"][0] or state["query"]
        if _query_scope_is_materially_new(last_query, expanded):
            candidate = SearchTranscriptsAction(
                kind="search_transcripts", query=expanded, video_ids=[]
            )
            key = action_key(AgentDecision(action=candidate))
            if key is not None and key not in previous_keys:
                return candidate
        return None


class ExperimentalReceiptBoundDeepResearchExecutor(
    ReceiptBoundDeepResearchExecutor
):
    """Explicit Stage-2-only executor; product construction never imports it."""

    def __init__(
        self,
        *,
        candidate_path: Path,
        source_index_runtime_health_valid: bool,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        validate_candidate_artifact(candidate_path)
        self.candidate_path = candidate_path
        self.source_index_runtime_health_valid = (
            source_index_runtime_health_valid
        )
        self.last_trace: dict[str, Any] | None = None

    def execute(
        self,
        *,
        objective: str,
        provider_factory: Callable[[str], object],
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
        treatment = EvidenceDeltaFollowupDecisionService(
            provider_factory,
            self.budget,
            clock=deep.clock,
            candidate_path=self.candidate_path,
            source_index_runtime_health_valid=(
                self.source_index_runtime_health_valid
            ),
        )
        deep.graph = DeepSearchGraph(
            decision_service=treatment,
            navigation=deep.graph.navigation,
            transcripts=deep.graph.transcripts,
            windows=deep.graph.windows,
            reducer=deep.graph.reducer,
            budget=self.budget,
            clock=deep.clock,
        )
        response, trace = deep.ask(AskRequest(query=objective, mode="deep"))
        trace["stage2_candidate_treatment"] = {
            "candidate_id": CANDIDATE_ID,
            "candidate_version": CANDIDATE_VERSION,
            "treatment_version": TREATMENT_VERSION,
            "candidate_context_version": CANDIDATE_CONTEXT_VERSION,
            "candidate_instruction_sha256": CANDIDATE_INSTRUCTION_SHA256,
            "runtime_registration": None,
            "active": False,
            "shadow": False,
            "audit": treatment.audit,
        }
        self.last_trace = dict(trace)
        return DurableDeepResearchOutput(
            query_plan=plan,
            response=response,
            trace=dict(trace),
        )
