from __future__ import annotations

from typing import Any

from shiliu.ask.context import fuse_evidence
from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.deep.contracts import (
    AgentDecision,
    DeepSearchState,
    ReadTranscriptWindowAction,
    SearchNavigationAction,
    SearchTranscriptsAction,
    ToolObservation,
)
from shiliu.retrieval.planner import normalize_query


class DeepStateReducer:
    def __init__(self, budget: DeepSearchBudget) -> None:
        self.budget = budget

    def record_decision(
        self,
        state: DeepSearchState,
        decision: AgentDecision,
        metadata: dict[str, Any],
    ) -> DeepSearchState:
        updated = _copy(state)
        updated["decision_rounds"] += 1
        updated["last_action"] = decision.action.model_dump(mode="json")
        usage = metadata.get("usage")
        if isinstance(usage, dict):
            updated["usage"].append({"role": "agent_action", **usage})
        allowed_ids = {
            value.citation_id for value in updated["evidence_spans"]
        }
        open_questions = list(updated["open_questions"])
        for question in decision.open_questions:
            normalized = normalize_query(question)
            if normalized not in open_questions and len(open_questions) < 6:
                open_questions.append(normalized)
        resolved = list(updated["resolved_questions"])
        for suggestion in decision.resolved_questions:
            if set(suggestion.citation_ids).issubset(allowed_ids):
                resolved.append(suggestion.model_dump(mode="json"))
                open_questions = [
                    value for value in open_questions
                    if normalize_query(value) != normalize_query(suggestion.question)
                ]
        updated["open_questions"] = open_questions
        updated["resolved_questions"] = resolved[-6:]
        updated["events"].append(
            {
                "event_type": "decision",
                "decision_round": updated["decision_rounds"],
                "action": updated["last_action"],
                "latency_ms": metadata.get("latency_ms"),
                "usage": usage,
                "retry_count": metadata.get("retry_count", 0),
                "finish_reason": metadata.get("finish_reason"),
                "response_id": metadata.get("response_id"),
            }
        )
        return updated

    def record_decision_error(
        self, state: DeepSearchState, error: Exception
    ) -> DeepSearchState:
        updated = _copy(state)
        updated["decision_rounds"] += 1
        text = f"{type(error).__name__}: {error}"[:500]
        metadata = getattr(error, "completion_metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        error_code = str(getattr(error, "code", type(error).__name__))
        updated["errors"].append(text)
        updated["termination_reason"] = (
            "budget_exhausted"
            if error_code == "deadline_exhausted"
            else "provider_error"
        )
        updated["events"].append(
            {
                "event_type": "decision_error",
                "decision_round": updated["decision_rounds"],
                "provider_error_code": error_code,
                "finish_reason": metadata.get("finish_reason"),
                "usage": metadata.get("usage"),
                "latency_ms": metadata.get("latency_ms"),
                "response_id": metadata.get("response_id"),
                "retry_count": metadata.get("retry_count", 0),
                "bounded_observation_summary": text,
            }
        )
        return updated

    def approve_tool(
        self, state: DeepSearchState, action_key: str
    ) -> DeepSearchState:
        updated = _copy(state)
        updated["tool_calls"] += 1
        updated["previous_queries"].append(action_key)
        updated["repeated_action_keys"].append(action_key)
        updated["events"].append(
            {
                "event_type": "guard",
                "guard_decision": "allowed",
                "tool_call": updated["tool_calls"],
                "action_key": action_key,
            }
        )
        return updated

    def reject(
        self, state: DeepSearchState, reason: str, detail: str
    ) -> DeepSearchState:
        updated = _copy(state)
        updated["termination_reason"] = reason  # type: ignore[typeddict-item]
        updated["events"].append(
            {
                "event_type": "guard",
                "guard_decision": reason,
                "bounded_observation_summary": detail[:500],
            }
        )
        return updated

    def record_finalize(self, state: DeepSearchState) -> DeepSearchState:
        updated = _copy(state)
        updated["events"].append(
            {
                "event_type": "finalize",
                "termination_reason": updated["termination_reason"],
                "evidence_count": len(updated["evidence_spans"]),
            }
        )
        return updated

    def correct_empty_navigation(
        self, state: DeepSearchState
    ) -> DeepSearchState:
        """Route one empty navigation into a global authoritative search."""

        updated = _copy(state)
        action = SearchNavigationAction.model_validate(updated["last_action"])
        fallback = SearchTranscriptsAction(
            kind="search_transcripts",
            query=action.query,
            video_ids=[],
        )
        updated["last_action"] = fallback.model_dump(mode="json")
        updated["events"].append(
            {
                "event_type": "empty_navigation_transcript_fallback",
                "source_action_key": action_key(
                    AgentDecision(action=action)
                ),
                "forced_action": fallback.model_dump(mode="json"),
                "bounded_observation_summary": (
                    "empty navigation deterministically routed to one global "
                    "transcript search"
                ),
            }
        )
        return updated

    def record_observation(
        self, state: DeepSearchState, observation: ToolObservation
    ) -> DeepSearchState:
        updated = _copy(state)
        old_segment_ids = list(updated["visited_segment_ids"])
        old_segments = set(old_segment_ids)
        if observation.kind == "navigation":
            by_id = {
                value.video_id: value for value in updated["navigation_documents"]
            }
            for value in observation.navigation_documents:
                by_id[value.video_id] = value
            updated["navigation_documents"] = list(by_id.values())[-8:]
            updated["navigation_result_count"] += len(
                observation.navigation_documents
            )
            updated["visited_video_ids"] = list(
                dict.fromkeys(
                    [
                        *updated["visited_video_ids"],
                        *[
                            value.video_id
                            for value in observation.navigation_documents
                        ],
                    ]
                )
            )
        else:
            fused = fuse_evidence(
                [*updated["evidence_spans"], *observation.evidence_spans]
            )
            updated["evidence_spans"] = list(fused)
            ordered_new_segment_ids = list(
                dict.fromkeys(
                    segment_id
                    for span in observation.evidence_spans
                    for segment_id in span.segment_ids
                )
            )
            new_segment_ids = set(ordered_new_segment_ids)
            progressed = bool(new_segment_ids - old_segments)
            updated["visited_segment_ids"] = list(
                dict.fromkeys([*old_segment_ids, *ordered_new_segment_ids])
            )
            updated["visited_video_ids"] = list(
                dict.fromkeys(
                    [
                        *updated["visited_video_ids"],
                        *[value.video_id for value in observation.evidence_spans],
                    ]
                )
            )
            updated["consecutive_no_new_evidence"] = (
                0
                if progressed
                else updated["consecutive_no_new_evidence"] + 1
            )
        updated["stale_reasons"].extend(observation.stale_reasons)
        if observation.error:
            updated["errors"].append(observation.error[:500])
        updated["last_observation_summary"] = observation.summary[:1000]
        updated["pending_observation"] = None
        updated["events"].append(
            {
                "event_type": "observation",
                "tool_call": updated["tool_calls"],
                "observation_kind": observation.kind,
                "bounded_observation_summary": observation.summary[:500],
                "new_video_ids": [
                    value.video_id for value in observation.navigation_documents
                ],
                "new_segment_ids": [
                    value
                    for span in observation.evidence_spans
                    for value in span.segment_ids
                    if value not in old_segments
                ][:60],
                "evidence_count": len(updated["evidence_spans"]),
                "latency_ms": observation.latency_ms,
                "dropped_evidence_count": observation.dropped_evidence_count,
            }
        )
        if (
            observation.kind != "navigation"
            and updated["consecutive_no_new_evidence"]
            >= self.budget.consecutive_no_new_evidence_limit
        ):
            updated["termination_reason"] = (
                "evidence_unavailable"
                if not updated["evidence_spans"] and updated["stale_reasons"]
                else "no_new_evidence"
            )
        if (
            sum(len(value.quote_text) for value in updated["evidence_spans"])
            >= self.budget.final_evidence_context_chars
        ):
            updated["termination_reason"] = "budget_exhausted"
        return updated


def action_key(decision: AgentDecision) -> str | None:
    action = decision.action
    if isinstance(action, SearchNavigationAction):
        return "navigation:" + normalize_query(action.query).casefold()
    if isinstance(action, SearchTranscriptsAction):
        videos = ",".join(str(value) for value in sorted(set(action.video_ids)))
        return f"transcripts:{normalize_query(action.query).casefold()}:{videos}"
    if isinstance(action, ReadTranscriptWindowAction):
        return (
            f"window:{action.anchor_segment_id}:{action.before}:{action.after}"
        )
    return None


def _copy(state: DeepSearchState) -> DeepSearchState:
    copied = dict(state)
    for key in (
        "open_questions",
        "resolved_questions",
        "evidence_spans",
        "navigation_documents",
        "visited_video_ids",
        "visited_segment_ids",
        "previous_queries",
        "repeated_action_keys",
        "errors",
        "stale_reasons",
        "events",
        "usage",
    ):
        copied[key] = list(state[key])  # type: ignore[literal-required]
    return copied  # type: ignore[return-value]
