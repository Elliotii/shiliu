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


CANDIDATE_ID = "V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001"
CANDIDATE_VERSION = "1.1.0"
CANDIDATE_ARTIFACT_SHA256 = (
    "c40c4df488c15801eb521530f16833158028cef076ba348ce811f3a8794d4efc"
)
TREATMENT_VERSION = "v5-d-r1-coverage-bundle-handoff-treatment-v1"
CANDIDATE_CONTEXT_VERSION = "v5-d-r1-coverage-bundle-context-v1"
CANDIDATE_INSTRUCTION = (
    "R1 experiment-only policy context: preserve the explicit user objective's "
    "source and evidence coverage obligations. A Candidate recovery remains one "
    "action, but that action may be a bounded multi-source or objective-scoped "
    "transcript coverage bundle. After it completes, retain Candidate control "
    "for a coverage completion or honest deficit stop; do not add a second "
    "recovery and do not return to an exact prior follow-up. Never use Gold, "
    "evaluator, split, reserve, promotion, or navigation text as Evidence."
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
    recovery = payload.get("recovery_logic") or {}
    if recovery.get("maximum_candidate_recovery_actions") != 1:
        raise CandidateIdentityError("candidate recovery bound mismatch")
    if recovery.get("second_recovery_authorized") is not False:
        raise CandidateIdentityError("candidate second recovery must be false")
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


_CHINESE_NUMERALS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def objective_named_titles(objective: str) -> tuple[str, ...]:
    values = [value.strip() for value in re.findall(r"《([^》]{1,160})》", objective)]
    return tuple(dict.fromkeys(value for value in values if value))


def objective_required_source_count(objective: str) -> int:
    named_count = len(objective_named_titles(objective))
    numeric_count = 0
    patterns = (
        r"至少(?:综合)?\s*([一二两三四五六七八九十\d]+)\s*条(?:不同)?(?:视频)?来源",
        r"([一二两三四五六七八九十\d]+)\s*个(?:不同)?(?:视频)?来源",
    )
    for pattern in patterns:
        match = re.search(pattern, objective)
        if not match:
            continue
        token = match.group(1)
        numeric_count = int(token) if token.isdigit() else _CHINESE_NUMERALS.get(token, 0)
        break
    return max(1, named_count, numeric_count)


def objective_focus_query(objective: str) -> str:
    for pattern in (r"“([^”]{1,120})”", r'"([^"\n]{1,120})"'):
        match = re.search(pattern, objective)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return objective


def _title_key(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", value.casefold()))


def _current_evidence_source_ids(state: DeepSearchState) -> set[int]:
    return {int(span.video_id) for span in state["evidence_spans"]}


class CoverageBundleFollowupDecisionService(AgentDecisionService):
    """R1 experiment-only adapter for the proposed/non-active Candidate."""

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
        self.required_source_count: int | None = None
        self.pre_recovery_source_count = 0
        self.recovery_open_questions: list[str] = []
        self.recovery_resolved_questions: list[str] = []
        self.audit: list[dict[str, Any]] = []

    def _health_and_budget_valid(self, state: DeepSearchState) -> bool:
        return bool(
            self.source_index_runtime_health_valid
            and not state["errors"]
            and not state["stale_reasons"]
            and state["termination_reason"] is None
            and state["tool_calls"] < self.budget.max_tool_calls
            and state["decision_rounds"] < self.budget.max_decision_rounds
        )

    def _coverage_gap(self, state: DeepSearchState) -> bool:
        return bool(
            state["open_questions"]
            and len(_current_evidence_source_ids(state))
            < objective_required_source_count(state["query"])
        )

    def _zero_evidence_trigger(self, state: DeepSearchState) -> bool:
        observation = _last_observation(state)
        return bool(
            self._health_and_budget_valid(state)
            and self._coverage_gap(state)
            and observation is not None
            and observation.get("observation_kind")
            in {"transcript_search", "transcript_window"}
            and not observation.get("new_segment_ids")
            and int(state["consecutive_no_new_evidence"]) >= 1
        )

    def _propose_with_candidate_context(
        self, state: DeepSearchState
    ) -> tuple[AgentDecision, dict[str, Any]]:
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
        decision = (
            output
            if isinstance(output, AgentDecision)
            else AgentDecision.model_validate(output)
        )
        return decision, {
            "finish_reason": getattr(response, "finish_reason", None),
            "usage": getattr(response, "usage", None),
            "latency_ms": getattr(response, "latency_ms", None),
            "response_id": getattr(response, "response_id", None),
            "retry_count": int(getattr(response, "retry_count", 0)),
        }

    def _proposed_exact_repeat(
        self, state: DeepSearchState, proposed: AgentDecision
    ) -> bool:
        if not isinstance(
            proposed.action, (SearchNavigationAction, SearchTranscriptsAction)
        ):
            return False
        key = action_key(proposed)
        return bool(key and key in set(state["repeated_action_keys"]))

    def _matching_named_source_ids(self, state: DeepSearchState) -> list[int]:
        title_keys = [_title_key(value) for value in objective_named_titles(state["query"])]
        matched: list[int] = []
        for target in title_keys:
            if not target:
                continue
            for document in state["navigation_documents"]:
                candidate = _title_key(document.title)
                if target in candidate or candidate in target:
                    value = int(document.video_id)
                    if value not in matched:
                        matched.append(value)
                    break
        return matched

    def _coverage_bundle(
        self, state: DeepSearchState
    ) -> SearchTranscriptsAction | None:
        required = objective_required_source_count(state["query"])
        named = objective_named_titles(state["query"])
        matched_ids = self._matching_named_source_ids(state)
        video_ids = matched_ids if named and len(matched_ids) >= required else []
        candidate = SearchTranscriptsAction(
            kind="search_transcripts",
            query=objective_focus_query(state["query"]),
            video_ids=video_ids,
        )
        key = action_key(AgentDecision(action=candidate))
        if key is None or key in set(state["repeated_action_keys"]):
            return None
        return candidate

    def _post_recovery_stop(
        self, state: DeepSearchState
    ) -> tuple[AgentDecision, dict[str, Any]]:
        observation = _last_observation(state)
        delta = len((observation or {}).get("new_segment_ids") or [])
        current_sources = len(_current_evidence_source_ids(state))
        required = self.required_source_count or objective_required_source_count(
            state["query"]
        )
        satisfied = bool(delta > 0 and current_sources >= required)
        if satisfied:
            mode = "coverage_satisfied_stop_for_synthesis"
            summary = (
                "the one Candidate coverage bundle satisfied the explicit "
                "grounded source obligation; synthesize with current Evidence"
            )
        elif delta > 0:
            mode = "honest_partial_stop_coverage_deficit"
            summary = (
                "the one Candidate coverage bundle added current Evidence but "
                "the explicit grounded source obligation remains incomplete"
            )
        else:
            mode = "honest_insufficient_stop_no_evidence"
            summary = (
                "the one Candidate coverage bundle added no current transcript "
                "Evidence"
            )
        self.audit.append(
            {
                "candidate_id": CANDIDATE_ID,
                "candidate_version": CANDIDATE_VERSION,
                "applicable": True,
                "phase": "post_recovery_handoff",
                "post_recovery_completion_gate": True,
                "provider_call_performed": False,
                "second_recovery_performed": False,
                "post_recovery_evidence_delta": delta,
                "pre_recovery_grounded_source_count": self.pre_recovery_source_count,
                "post_recovery_grounded_source_count": current_sources,
                "explicit_required_source_count": required,
                "coverage_satisfied": satisfied,
                "selection_mode": mode,
            }
        )
        return AgentDecision(
            action=StopAction(kind="stop", summary=summary),
            open_questions=self.recovery_open_questions,
            resolved_questions=self.recovery_resolved_questions,
        ), {
            "finish_reason": "candidate_post_recovery_completion_gate",
            "usage": None,
            "latency_ms": 0,
            "response_id": None,
            "retry_count": 0,
        }

    def decide(self, state: DeepSearchState) -> tuple[AgentDecision, dict[str, Any]]:
        if self.recovery_used:
            return self._post_recovery_stop(state)

        zero_trigger = self._zero_evidence_trigger(state)
        if zero_trigger:
            proposed, metadata = self._propose_with_candidate_context(state)
        else:
            proposed, metadata = super().decide(state)

        repeat_trigger = bool(
            self._health_and_budget_valid(state)
            and self._coverage_gap(state)
            and state["navigation_documents"]
            and self._proposed_exact_repeat(state, proposed)
        )
        if not (zero_trigger or repeat_trigger):
            self.audit.append(
                {
                    "candidate_id": CANDIDATE_ID,
                    "applicable": False,
                    "baseline_fallback": True,
                    "selected_action_key_sha256": _hashed_action_key(proposed),
                }
            )
            return proposed, metadata

        recovery = self._coverage_bundle(state)
        required = objective_required_source_count(state["query"])
        current_sources = len(_current_evidence_source_ids(state))
        if recovery is None:
            selected = AgentDecision(
                action=StopAction(
                    kind="stop",
                    summary="no eligible objective-derived coverage bundle remains",
                ),
                open_questions=proposed.open_questions,
                resolved_questions=proposed.resolved_questions,
            )
            mode = "honest_stop_no_eligible_coverage_bundle"
        else:
            selected = AgentDecision(
                action=recovery,
                open_questions=proposed.open_questions,
                resolved_questions=proposed.resolved_questions,
            )
            self.recovery_used = True
            self.recovery_action_key = action_key(selected)
            self.required_source_count = required
            self.pre_recovery_source_count = current_sources
            self.recovery_open_questions = list(proposed.open_questions)
            self.recovery_resolved_questions = list(proposed.resolved_questions)
            mode = "objective_coverage_bundle_recovery"
        self.audit.append(
            {
                "candidate_id": CANDIDATE_ID,
                "candidate_version": CANDIDATE_VERSION,
                "treatment_version": TREATMENT_VERSION,
                "candidate_context_version": CANDIDATE_CONTEXT_VERSION,
                "candidate_instruction_sha256": CANDIDATE_INSTRUCTION_SHA256,
                "applicable": True,
                "phase": "pre_recovery_follow_up",
                "trigger": (
                    "zero_current_evidence_delta"
                    if zero_trigger
                    else "proposed_exact_prior_action_with_coverage_gap"
                ),
                "explicit_required_source_count": required,
                "pre_recovery_grounded_source_count": current_sources,
                "named_objective_source_count": len(
                    objective_named_titles(state["query"])
                ),
                "coverage_bundle_video_count": (
                    len(recovery.video_ids) if recovery is not None else 0
                ),
                "coverage_bundle_global_scope": bool(
                    recovery is not None and not recovery.video_ids
                ),
                "recovery_ordinal": 1 if recovery is not None else 0,
                "second_recovery_authorized": False,
                "selection_mode": mode,
                "provider_call_performed": True,
                "proposed_action_key_sha256": _hashed_action_key(proposed),
                "selected_action_key_sha256": _hashed_action_key(selected),
                "materially_new_target": recovery is not None,
                "objective_coverage_bundle": recovery is not None,
            }
        )
        return selected, metadata


class R1ExperimentalReceiptBoundDeepResearchExecutor(
    ReceiptBoundDeepResearchExecutor
):
    """Explicit R1-only executor; default product construction never imports it."""

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
        self.source_index_runtime_health_valid = source_index_runtime_health_valid
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
        treatment = CoverageBundleFollowupDecisionService(
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
        trace["r1_candidate_treatment"] = {
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
