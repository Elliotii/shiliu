from __future__ import annotations

from dataclasses import dataclass

from shiliu.ask.deep.contracts import DeepSearchState


@dataclass(frozen=True)
class DeepSearchBudget:
    max_decision_rounds: int = 6
    max_tool_calls: int = 12
    focused_video_limit: int = 8
    consecutive_no_new_evidence_limit: int = 2
    window_default_each_side: int = 2
    window_max_each_side: int = 4
    final_evidence_context_chars: int = 12_000
    total_runtime_seconds: float = 360
    search_phase_cutoff_seconds: float = 150
    final_answer_reserve_seconds: float = 210

    def __post_init__(self) -> None:
        if self.max_decision_rounds <= 0 or self.max_tool_calls <= 0:
            raise ValueError("round and tool budgets must be positive")
        if not 1 <= self.focused_video_limit <= 8:
            raise ValueError("focused video limit must be between 1 and 8")
        if self.consecutive_no_new_evidence_limit <= 0:
            raise ValueError("no-new-evidence limit must be positive")
        if not (
            0
            <= self.window_default_each_side
            <= self.window_max_each_side
            <= 4
        ):
            raise ValueError("window budgets must satisfy 0 <= default <= max <= 4")
        if self.final_evidence_context_chars <= 0:
            raise ValueError("evidence context budget must be positive")
        if (
            self.total_runtime_seconds <= 0
            or self.search_phase_cutoff_seconds <= 0
            or self.final_answer_reserve_seconds <= 0
        ):
            raise ValueError("runtime deadlines must be positive")
        if abs(
            self.search_phase_cutoff_seconds
            + self.final_answer_reserve_seconds
            - self.total_runtime_seconds
        ) > 1e-9:
            raise ValueError("search cutoff and answer reserve must equal total runtime")

    def before_decision(self, state: DeepSearchState, now: float) -> str | None:
        if now >= state["total_deadline"] or now >= state["search_deadline"]:
            return "budget_exhausted"
        if state["decision_rounds"] >= self.max_decision_rounds:
            return "budget_exhausted"
        return None

    def before_tool(self, state: DeepSearchState, now: float) -> str | None:
        if now >= state["total_deadline"] or now >= state["search_deadline"]:
            return "budget_exhausted"
        if state["tool_calls"] >= self.max_tool_calls:
            return "budget_exhausted"
        return None

    def remaining_total(self, state: DeepSearchState, now: float) -> float:
        return max(0.0, state["total_deadline"] - now)
