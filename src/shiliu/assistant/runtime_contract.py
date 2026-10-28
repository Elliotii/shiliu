"""Shared Assistant errors and pure token accounting; no storage backend."""
from contextvars import ContextVar

_TOOL_EXECUTION = ContextVar("assistant_tool_execution", default=None)

class AssistantConflict(RuntimeError):
    pass

class ModelBudgetWait(RuntimeError):
    code = "background_budget_wait"

class ExecutionBudgetExceeded(AssistantConflict):
    code = "execution_budget_exhausted"

def known_tokens(usage: dict) -> int:
    return max(int(usage.get("total_tokens") or 0),
               int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
               + int(usage.get("completion_tokens") or usage.get("output_tokens") or 0))
