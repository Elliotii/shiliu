from __future__ import annotations

import hashlib
from dataclasses import replace
from unittest.mock import patch

from shiliu.app import Application
from shiliu.ask.answer import _answer_messages, _repair_messages
from shiliu.ask.context import ContextBuildResult
from shiliu.ask.validation import ValidationIssue


P2_SYSTEM_SHA256 = "bf1f883f4f6ec8617a5f19566e35556b820b86ae5cec4e58e8c26d0edbc95758"
P2_REPAIR_SYSTEM_SHA256 = "a4c021d415c8ffb4d3b8c8842f56fb3e039ac30bcf89dbc5f03da57f5c1e33fd"


def _empty_context() -> ContextBuildResult:
    return ContextBuildResult(
        spans=(),
        model_context=(
            '{"user_query":"q","normalized_intent":"q",'
            '"citation_allowlist":[],"transcript_evidence":[]}'
        ),
        citation_allowlist=(),
        truncated=False,
        dropped_span_count=0,
    )


def test_production_answer_messages_are_exact_frozen_stage1e_p2() -> None:
    answer_system = _answer_messages(query="q", context=_empty_context())[0]["content"]
    repair_system = _repair_messages(
        query="q",
        context=_empty_context(),
        issues=(ValidationIssue("x", "$", "x"),),
    )[0]["content"]

    assert hashlib.sha256(answer_system.encode()).hexdigest() == P2_SYSTEM_SHA256
    assert hashlib.sha256(repair_system.encode()).hexdigest() == P2_REPAIR_SYSTEM_SHA256
    assert "Behavior example" not in answer_system
    assert "memory distillation" not in answer_system


def test_application_splits_only_fast_and_deep_final_answer_providers(
    app_paths,
) -> None:
    application = Application(app_paths)
    application.config = replace(
        application.config,
        llm_model="deepseek-v4-pro",
        interactive_model="deepseek-v4-pro",
    )
    with patch("shiliu.app.load_api_key", return_value="redacted"):
        fast = application.fast_answer_provider("grounded_answer")
        fast_recovery = application.fast_answer_provider("grounded_answer_recovery")
        deep = application.deep_answer_provider("grounded_answer")
        deep_recovery = application.deep_answer_provider("grounded_answer_recovery")
        query_analysis = application.provider("query_analysis")
        agent_action = application.provider("agent_action")
        research = application.research_provider("grounded_answer")

    assert (fast.model, fast.thinking_enabled, fast.reasoning_effort) == (
        "deepseek-v4-flash",
        False,
        None,
    )
    assert (fast_recovery.model, fast_recovery.thinking_enabled, fast_recovery.reasoning_effort) == (
        "deepseek-v4-flash",
        False,
        None,
    )
    assert deep.model == application.config.model_for("grounded_answer")
    assert (deep.thinking_enabled, deep.reasoning_effort) == (False, None)
    assert deep_recovery.model == deep.model
    assert (deep_recovery.thinking_enabled, deep_recovery.reasoning_effort) == (
        False,
        None,
    )
    assert query_analysis.model == agent_action.model == deep.model
    assert query_analysis.thinking_enabled is agent_action.thinking_enabled is False
    assert research.model == deep.model
    assert (research.thinking_enabled, research.reasoning_effort) == (False, None)


def test_ask_service_uses_distinct_answer_services_but_shared_contracts(
    app_paths,
) -> None:
    application = Application(app_paths)
    service = application.ask_service

    assert service.deep_service is not None
    assert service.answer_service is service.finalizer.answer_service
    assert service.answer_service is not service.deep_service.answer_service
    assert service.finalizer is service.deep_service.finalizer
    assert type(service.context_builder) is type(service.deep_service.context_builder)
    assert service.finalizer.claim_verifier is service.deep_service.finalizer.claim_verifier
