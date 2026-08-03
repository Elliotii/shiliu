from __future__ import annotations

from typing import Callable

from langgraph.graph import END, START, StateGraph

from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.deep.contracts import (
    AgentDecision,
    DeepSearchState,
    FinishAction,
    ReadTranscriptWindowAction,
    SearchNavigationAction,
    SearchTranscriptsAction,
    StopAction,
    ToolObservation,
)
from shiliu.ask.deep.decision import AgentDecisionService
from shiliu.ask.deep.navigation import NavigationService
from shiliu.ask.deep.reducer import DeepStateReducer, action_key
from shiliu.ask.deep.transcript import (
    TranscriptSearchService,
    TranscriptWindowReader,
)


class DeepSearchGraph:
    def __init__(
        self,
        *,
        decision_service: AgentDecisionService,
        navigation: NavigationService,
        transcripts: TranscriptSearchService,
        windows: TranscriptWindowReader,
        reducer: DeepStateReducer,
        budget: DeepSearchBudget,
        clock: Callable[[], float],
    ) -> None:
        self.decision_service = decision_service
        self.navigation = navigation
        self.transcripts = transcripts
        self.windows = windows
        self.reducer = reducer
        self.budget = budget
        self.clock = clock
        self.compiled = self._build().compile()

    def run(self, state: DeepSearchState) -> DeepSearchState:
        return self.compiled.invoke(state, config={"recursion_limit": 80})

    def _build(self) -> StateGraph:
        graph = StateGraph(DeepSearchState)
        graph.add_node("decide_action", self._decide)
        graph.add_node("guard_action", self._guard)
        graph.add_node("search_navigation", self._search_navigation)
        graph.add_node("search_transcripts", self._search_transcripts)
        graph.add_node("read_transcript_window", self._read_window)
        graph.add_node("reduce_observation", self._reduce)
        graph.add_node("finalize", self._finalize)
        graph.add_edge(START, "decide_action")
        graph.add_edge("decide_action", "guard_action")
        graph.add_conditional_edges(
            "guard_action",
            self._route_guard,
            {
                "search_navigation": "search_navigation",
                "search_transcripts": "search_transcripts",
                "read_transcript_window": "read_transcript_window",
                "finalize": "finalize",
            },
        )
        for node in (
            "search_navigation",
            "search_transcripts",
            "read_transcript_window",
        ):
            graph.add_edge(node, "reduce_observation")
        graph.add_conditional_edges(
            "reduce_observation",
            self._route_reducer,
            {
                "continue": "decide_action",
                "correct_empty_navigation": "guard_action",
                "finalize": "finalize",
            },
        )
        graph.add_edge("finalize", END)
        return graph

    def _decide(self, state: DeepSearchState) -> DeepSearchState:
        blocked = self.budget.before_decision(state, self.clock())
        if blocked:
            return self.reducer.reject(
                state, blocked, "decision budget or search deadline reached"
            )
        try:
            decision, metadata = self.decision_service.decide(state)
        except Exception as exc:
            return self.reducer.record_decision_error(state, exc)
        return self.reducer.record_decision(state, decision, metadata)

    def _guard(self, state: DeepSearchState) -> DeepSearchState:
        if state["termination_reason"] is not None:
            return state
        decision = _decision_from_state(state)
        action = decision.action
        if isinstance(action, FinishAction):
            reason = (
                "answer_ready" if state["evidence_spans"] else "evidence_unavailable"
            )
            return self.reducer.reject(state, reason, f"agent suggested {action.kind}")
        if isinstance(action, StopAction):
            reason = (
                "no_new_evidence"
                if state["evidence_spans"]
                else "evidence_unavailable"
            )
            return self.reducer.reject(state, reason, f"agent suggested {action.kind}")
        if isinstance(action, SearchNavigationAction) and any(
            value.get("event_type") == "empty_navigation_transcript_fallback"
            for value in state["events"]
        ):
            return self.reducer.reject(
                state,
                "repeated_search",
                "navigation already returned empty and used its bounded transcript fallback",
            )
        blocked = self.budget.before_tool(state, self.clock())
        if blocked:
            return self.reducer.reject(state, blocked, "tool budget or deadline reached")
        key = action_key(decision)
        if key is None:
            return self.reducer.reject(
                state, "provider_error", "agent returned an unsupported action"
            )
        if key in state["repeated_action_keys"]:
            return self.reducer.reject(
                state, "repeated_search", f"repeated action: {key}"
            )
        if (
            isinstance(action, SearchTranscriptsAction)
            and len(action.video_ids) > self.budget.focused_video_limit
        ):
            return self.reducer.reject(
                state, "budget_exhausted", "focused video limit exceeded"
            )
        if isinstance(action, ReadTranscriptWindowAction):
            known = {
                segment_id
                for span in state["evidence_spans"]
                for segment_id in span.segment_ids
            }
            if action.anchor_segment_id not in known:
                return self.reducer.reject(
                    state, "evidence_unavailable", "unknown window anchor"
                )
        return self.reducer.approve_tool(state, key)

    @staticmethod
    def _route_guard(state: DeepSearchState) -> str:
        if state["termination_reason"] is not None:
            return "finalize"
        action = _decision_from_state(state).action
        return action.kind

    def _search_navigation(self, state: DeepSearchState) -> DeepSearchState:
        action = _decision_from_state(state).action
        assert isinstance(action, SearchNavigationAction)
        started = self.clock()
        try:
            documents = self.navigation.search(
                action.query,
                filters=state["filters"],
                limit=self.budget.focused_video_limit,
            )
            observation = ToolObservation(
                kind="navigation",
                summary=f"navigation returned {len(documents)} videos",
                navigation_documents=documents,
                latency_ms=max(0, (self.clock() - started) * 1000),
            )
        except Exception as exc:
            observation = ToolObservation(
                kind="navigation",
                summary="navigation failed",
                error=f"{type(exc).__name__}: {exc}"[:500],
                latency_ms=max(0, (self.clock() - started) * 1000),
            )
        return {**state, "pending_observation": observation}

    def _search_transcripts(self, state: DeepSearchState) -> DeepSearchState:
        action = _decision_from_state(state).action
        assert isinstance(action, SearchTranscriptsAction)
        started = self.clock()
        try:
            result = self.transcripts.search(
                action.query,
                filters=state["filters"],
                video_ids=tuple(action.video_ids),
                query_index=state["tool_calls"] - 1,
            )
            observation = ToolObservation(
                kind="transcript_search",
                summary=(
                    f"transcript search returned {len(result.spans)} spans "
                    f"and {len(result.stale_reasons)} stale hits; "
                    f"{result.dropped_span_count} spans were deterministically bounded"
                ),
                evidence_spans=list(result.spans),
                stale_reasons=list(result.stale_reasons),
                dropped_evidence_count=result.dropped_span_count,
                latency_ms=max(0, (self.clock() - started) * 1000),
            )
        except Exception as exc:
            observation = ToolObservation(
                kind="transcript_search",
                summary="transcript search failed",
                error=f"{type(exc).__name__}: {exc}"[:500],
                latency_ms=max(0, (self.clock() - started) * 1000),
            )
        return {**state, "pending_observation": observation}

    def _read_window(self, state: DeepSearchState) -> DeepSearchState:
        action = _decision_from_state(state).action
        assert isinstance(action, ReadTranscriptWindowAction)
        started = self.clock()
        anchor_span = next(
            value
            for value in state["evidence_spans"]
            if action.anchor_segment_id in value.segment_ids
        )
        try:
            result = self.windows.read(
                video_id=anchor_span.video_id,
                anchor_segment_id=action.anchor_segment_id,
                before=action.before,
                after=action.after,
            )
            observation = ToolObservation(
                kind="transcript_window",
                summary=(
                    f"window read {len(result.span.segment_ids)} authoritative segments"
                ),
                evidence_spans=[result.span],
                latency_ms=max(0, (self.clock() - started) * 1000),
            )
        except Exception as exc:
            observation = ToolObservation(
                kind="transcript_window",
                summary="transcript window read failed",
                error=f"{type(exc).__name__}: {exc}"[:500],
                latency_ms=max(0, (self.clock() - started) * 1000),
            )
        return {**state, "pending_observation": observation}

    def _reduce(self, state: DeepSearchState) -> DeepSearchState:
        observation = state["pending_observation"]
        if observation is None:
            return self.reducer.reject(
                state, "provider_error", "tool produced no observation"
            )
        updated = self.reducer.record_observation(state, observation)
        if (
            observation.kind == "navigation"
            and not observation.navigation_documents
            and observation.error is None
        ):
            return self.reducer.correct_empty_navigation(updated)
        if updated["termination_reason"] is None:
            blocked = self.budget.before_decision(updated, self.clock())
            if blocked is not None:
                return self.reducer.reject(
                    updated,
                    blocked,
                    "decision budget or search deadline reached after observation",
                )
        return updated

    def _route_reducer(self, state: DeepSearchState) -> str:
        if state["termination_reason"] is not None:
            return "finalize"
        if (
            state["events"]
            and state["events"][-1].get("event_type")
            == "empty_navigation_transcript_fallback"
        ):
            return "correct_empty_navigation"
        return "continue"

    def _finalize(self, state: DeepSearchState) -> DeepSearchState:
        return self.reducer.record_finalize(state)


def _decision_from_state(state: DeepSearchState) -> AgentDecision:
    if state["last_action"] is None:
        raise RuntimeError("deep state has no last action")
    return AgentDecision.model_validate({"action": state["last_action"]})
