from __future__ import annotations

import json
from typing import Any, Callable

from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.deep.contracts import AgentDecision, DeepSearchState
from shiliu.ask.deep.policy import DEEP_POLICY_INSTRUCTIONS


class DecisionViewProjector:
    """Deterministically project private runtime state for one agent decision."""

    def __init__(self, budget: DeepSearchBudget) -> None:
        self.budget = budget

    def project(self, state: DeepSearchState, *, now: float) -> dict[str, object]:
        evidence = state["evidence_spans"][-12:]
        return {
            "question": state["query"],
            "priority_open_question": (
                state["open_questions"][0]
                if state["open_questions"]
                else state["query"]
            ),
            "open_questions": state["open_questions"][:6],
            "resolved_questions": state["resolved_questions"][-6:],
            "last_action": state["last_action"],
            "last_observation_summary": state["last_observation_summary"][:600],
            "navigation_documents": [
                {
                    "video_id": value.video_id,
                    "title": value.title,
                    "uploader": value.uploader,
                    "matched_excerpt": value.matched_excerpt[:240],
                    "authority": value.authority,
                }
                for value in state["navigation_documents"][-8:]
            ],
            "transcript_evidence": [
                {
                    "citation_id": span.citation_id,
                    "video_id": span.video_id,
                    "title": span.title,
                    "start_time": span.start_time,
                    "end_time": span.end_time,
                    "quote": span.quote_text[:360],
                }
                for span in evidence
            ],
            "window_anchors": [
                {
                    "citation_id": span.citation_id,
                    "video_id": span.video_id,
                    "anchor_segment_id": span.segment_ids[
                        len(span.segment_ids) // 2
                    ],
                }
                for span in evidence
                if span.segment_ids
            ],
            "visited_summary": {
                "video_count": len(state["visited_video_ids"]),
                "segment_count": len(state["visited_segment_ids"]),
                "recent_video_ids": state["visited_video_ids"][-8:],
            },
            "previous_scoped_query_keys": state["previous_queries"][-12:],
            "remaining": {
                "decision_rounds": max(
                    0,
                    self.budget.max_decision_rounds
                    - state["decision_rounds"],
                ),
                "tool_calls": max(
                    0, self.budget.max_tool_calls - state["tool_calls"]
                ),
                "search_seconds": max(
                    0, state["search_deadline"] - now
                ),
                "total_seconds": max(
                    0, state["total_deadline"] - now
                ),
                "context_characters": max(
                    0,
                    self.budget.final_evidence_context_chars
                    - sum(
                        len(value.quote_text)
                        for value in state["evidence_spans"]
                    ),
                ),
            },
        }


class AgentDecisionService:
    def __init__(
        self,
        provider_factory: Callable[[str], object],
        budget: DeepSearchBudget,
        *,
        clock: Callable[[], float],
    ) -> None:
        self.provider_factory = provider_factory
        self.budget = budget
        self.clock = clock
        self.projector = DecisionViewProjector(budget)

    def decide(self, state: DeepSearchState) -> tuple[AgentDecision, dict[str, Any]]:
        provider = self.provider_factory("agent_action")
        now = self.clock()
        remaining = min(
            max(0.001, state["search_deadline"] - now),
            max(0.001, state["total_deadline"] - now),
        )
        response = provider.generate_structured(  # type: ignore[attr-defined]
            role="agent_action",
            messages=_decision_messages(
                state,
                self.budget,
                now=now,
                projector=self.projector,
            ),
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


def _decision_messages(
    state: DeepSearchState,
    budget: DeepSearchBudget,
    *,
    now: float,
    projector: DecisionViewProjector | None = None,
) -> list[dict[str, str]]:
    payload = (projector or DecisionViewProjector(budget)).project(
        state, now=now
    )
    schema = json.dumps(
        AgentDecision.model_json_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return [
        {
            "role": "system",
            "content": (
                DEEP_POLICY_INSTRUCTIONS + f"\nRequired JSON Schema: {schema}"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        },
    ]
