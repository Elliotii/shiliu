from __future__ import annotations

import json
from typing import Any, Callable

from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.deep.contracts import AgentDecision, DeepSearchState


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

    def decide(self, state: DeepSearchState) -> tuple[AgentDecision, dict[str, Any]]:
        provider = self.provider_factory("agent_action")
        now = self.clock()
        remaining = min(
            max(0.001, state["search_deadline"] - now),
            max(0.001, state["total_deadline"] - now),
        )
        response = provider.generate_structured(  # type: ignore[attr-defined]
            role="agent_action",
            messages=_decision_messages(state, self.budget, now=now),
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
    state: DeepSearchState, budget: DeepSearchBudget, *, now: float
) -> list[dict[str, str]]:
    evidence = [
        {
            "citation_id": span.citation_id,
            "video_id": span.video_id,
            "start_time": span.start_time,
            "end_time": span.end_time,
            "segment_ids": list(span.segment_ids),
            "quote": span.quote_text[:500],
        }
        for span in state["evidence_spans"][-12:]
    ]
    navigation = [
        {
            "video_id": value.video_id,
            "title": value.title,
            "uploader": value.uploader,
            "description": value.description[:400],
            "summary_sections": value.summary_sections[:4],
            "matched_excerpt": value.matched_excerpt[:400],
            "authority": value.authority,
        }
        for value in state["navigation_documents"][-8:]
    ]
    payload = {
        "question": state["query"],
        "open_questions": state["open_questions"],
        "resolved_questions": state["resolved_questions"],
        "last_action": state["last_action"],
        "last_observation_summary": state["last_observation_summary"][:1000],
        "navigation_documents": navigation,
        "transcript_evidence": evidence,
        "visited_video_ids": state["visited_video_ids"][-24:],
        "visited_segment_ids": state["visited_segment_ids"][-60:],
        "previous_scoped_query_keys": state["previous_queries"][-24:],
        "remaining": {
            "decision_rounds": max(
                0, budget.max_decision_rounds - state["decision_rounds"]
            ),
            "tool_calls": max(0, budget.max_tool_calls - state["tool_calls"]),
            "search_seconds": max(0, state["search_deadline"] - now),
            "total_seconds": max(0, state["total_deadline"] - now),
            "context_characters": max(
                0,
                budget.final_evidence_context_chars
                - sum(len(value.quote_text) for value in state["evidence_spans"]),
            ),
        },
    }
    schema = json.dumps(
        AgentDecision.model_json_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return [
        {
            "role": "system",
            "content": (
                "Choose exactly one bounded search action. Return JSON matching the "
                "schema. Navigation is navigation_only and is never factual evidence. "
                "Only transcript_evidence citation IDs may resolve questions. Start "
                "from the user query and, when there are no observations yet, normally "
                "begin with search_navigation. React to observations, use focused "
                "transcript search for promising videos, read an authoritative window "
                "when a hit needs adjacent context, avoid repeated scoped queries and "
                "windows, and finish when the available transcript evidence can "
                "support a useful answer. Do not answer the question in this action."
                f"\nRequired JSON Schema: {schema}"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        },
    ]
