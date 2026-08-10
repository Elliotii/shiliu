from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
import json

import pytest

from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.deep.contracts import (
    AgentDecision,
    NavigationDocument,
    NavigationSourceLabel,
    SearchNavigationAction,
    SearchTranscriptsAction,
    StopAction,
)
from shiliu.ask.deep.reducer import action_key
from scripts.v5_d_stage2_treatment import (
    CANDIDATE_ARTIFACT_SHA256,
    CANDIDATE_ID,
    CANDIDATE_INSTRUCTION,
    CandidateIdentityError,
    EvidenceDeltaFollowupDecisionService,
    sha256_file,
    validate_candidate_artifact,
)
from scripts.v5_d_stage2_paired_runner import SOURCE_CASE_IDS, task_ids_for_cases


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "V5_D_CANDIDATE_EVIDENCE_DELTA_FOLLOWUP_V1.json"


class _Provider:
    def __init__(self, decisions: list[AgentDecision]) -> None:
        self.decisions = list(decisions)
        self.calls: list[dict[str, Any]] = []

    def generate_structured(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output=self.decisions.pop(0),
            finish_reason="stop",
            usage={"input_tokens": 10, "output_tokens": 5},
            latency_ms=1,
            response_id="mechanical-test",
            retry_count=0,
        )


def _document(video_id: int, title: str) -> NavigationDocument:
    label = NavigationSourceLabel(source="title", priority="high")
    return NavigationDocument(
        video_id=video_id,
        bvid=f"BV{video_id}",
        title=title,
        uploader="uploader",
        description="",
        summary_sections=[],
        user_notes=[],
        cleaned_transcript=[],
        metadata={},
        matched_excerpt=title,
        matched_sources=["title"],
        source_labels={"title": label},
    )


def _state(
    *,
    query: str = "请综合 ReAct 的主要观点、分歧、可操作结论和重要限制",
    last_query: str = "ReAct",
    last_video_ids: list[int] | None = None,
    navigation_documents: list[NavigationDocument] | None = None,
    zero_delta: bool = True,
) -> dict[str, Any]:
    last_action = SearchTranscriptsAction(
        kind="search_transcripts",
        query=last_query,
        video_ids=last_video_ids or [],
    )
    key = action_key(AgentDecision(action=last_action))
    assert key is not None
    return {
        "run_id": "test",
        "query": query,
        "filters": {},
        "open_questions": [query],
        "resolved_questions": [],
        "evidence_spans": [],
        "navigation_documents": navigation_documents or [],
        "visited_video_ids": [],
        "visited_segment_ids": [],
        "previous_queries": [key],
        "repeated_action_keys": [key],
        "decision_rounds": 2,
        "tool_calls": 2,
        "consecutive_no_new_evidence": 1 if zero_delta else 0,
        "navigation_result_count": len(navigation_documents or []),
        "started_at": 0.0,
        "search_deadline": 100.0,
        "total_deadline": 200.0,
        "last_action": last_action.model_dump(mode="json"),
        "last_observation_summary": "transcript search returned 0 spans",
        "pending_observation": None,
        "errors": [],
        "stale_reasons": [],
        "events": [
            {
                "event_type": "observation",
                "observation_kind": "transcript_search",
                "new_segment_ids": [] if zero_delta else ["segment-1"],
            }
        ],
        "usage": [],
        "termination_reason": None,
    }


def _service(provider: _Provider, *, health_valid: bool = True):
    return EvidenceDeltaFollowupDecisionService(
        lambda role: provider,
        DeepSearchBudget(),
        clock=lambda: 10.0,
        candidate_path=CANDIDATE,
        source_index_runtime_health_valid=health_valid,
    )


def test_candidate_identity_is_exact_and_non_active() -> None:
    payload = validate_candidate_artifact(CANDIDATE)
    assert sha256_file(CANDIDATE) == CANDIDATE_ARTIFACT_SHA256
    assert payload["candidate_id"] == CANDIDATE_ID
    assert payload["runtime_registration"] is None
    assert payload["active"] is False
    assert payload["shadow"] is False


def test_candidate_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    changed = tmp_path / "candidate.json"
    changed.write_text(CANDIDATE.read_text(encoding="utf-8") + "\n")
    with pytest.raises(CandidateIdentityError, match="hash mismatch"):
        validate_candidate_artifact(changed)


def test_non_applicable_state_uses_unchanged_baseline_messages() -> None:
    proposed = AgentDecision(
        action=SearchNavigationAction(kind="search_navigation", query="ReAct")
    )
    provider = _Provider([proposed])
    service = _service(provider)
    state = _state(zero_delta=False)
    selected, _ = service.decide(state)  # type: ignore[arg-type]
    assert selected == proposed
    assert len(provider.calls) == 1
    assert CANDIDATE_INSTRUCTION not in provider.calls[0]["messages"][0]["content"]
    assert service.audit[-1]["baseline_fallback"] is True


def test_zero_delta_repeated_navigation_becomes_material_global_recovery() -> None:
    proposed = AgentDecision(
        action=SearchNavigationAction(kind="search_navigation", query="ReAct")
    )
    provider = _Provider([proposed])
    service = _service(provider)
    state = _state()
    selected, _ = service.decide(state)  # type: ignore[arg-type]
    assert isinstance(selected.action, SearchTranscriptsAction)
    assert selected.action.query == state["open_questions"][0]
    assert selected.action.video_ids == []
    assert action_key(selected) not in state["repeated_action_keys"]
    assert CANDIDATE_INSTRUCTION in provider.calls[0]["messages"][0]["content"]
    assert service.audit[-1]["materially_new_target"] is True


def test_zero_delta_recovery_targets_one_untried_navigation_source() -> None:
    proposed = AgentDecision(
        action=SearchNavigationAction(kind="search_navigation", query="Claude Code")
    )
    provider = _Provider([proposed])
    service = _service(provider)
    state = _state(
        query="比较两个来源对 Claude Code 的结论、共同点和差异",
        last_query="Claude Code",
        last_video_ids=[100],
        navigation_documents=[
            _document(100, "source A"),
            _document(119, "source B"),
        ],
    )
    selected, _ = service.decide(state)  # type: ignore[arg-type]
    assert isinstance(selected.action, SearchTranscriptsAction)
    assert selected.action.video_ids == [119]
    assert selected.action.query == "Claude Code"
    assert action_key(selected) not in state["repeated_action_keys"]


def test_one_recovery_then_honest_stop_without_second_provider_call() -> None:
    proposed = AgentDecision(
        action=SearchNavigationAction(kind="search_navigation", query="ReAct")
    )
    provider = _Provider([proposed])
    service = _service(provider)
    state = _state()
    selected, _ = service.decide(state)  # type: ignore[arg-type]
    assert isinstance(selected.action, SearchTranscriptsAction)
    second = dict(state)
    second["last_action"] = selected.action.model_dump(mode="json")
    second["repeated_action_keys"] = [
        *state["repeated_action_keys"],
        action_key(selected),
    ]
    second["tool_calls"] = state["tool_calls"] + 1
    second["consecutive_no_new_evidence"] = 2
    stopped, metadata = service.decide(second)  # type: ignore[arg-type]
    assert isinstance(stopped.action, StopAction)
    assert metadata["finish_reason"] == "candidate_honest_stop"
    assert len(provider.calls) == 1


def test_invalid_runtime_health_falls_back_without_candidate_context() -> None:
    proposed = AgentDecision(
        action=SearchNavigationAction(kind="search_navigation", query="ReAct")
    )
    provider = _Provider([proposed])
    service = _service(provider, health_valid=False)
    selected, _ = service.decide(_state())  # type: ignore[arg-type]
    assert selected == proposed
    assert CANDIDATE_INSTRUCTION not in provider.calls[0]["messages"][0]["content"]


def test_default_product_source_does_not_import_experiment_treatment() -> None:
    matches = []
    for path in (ROOT / "src").rglob("*.py"):
        if "v5_d_stage2_treatment" in path.read_text(encoding="utf-8"):
            matches.append(path)
    assert matches == []


def test_freeze_manifest_binds_candidate_treatment_and_non_product_boundary() -> None:
    freeze = json.loads(
        (ROOT / "V5_D_STAGE_2_EXPERIMENT_FREEZE.json").read_text(
            encoding="utf-8"
        )
    )
    assert freeze["experiment_id"] == "V5D-S2-PAIRED-EVAL-001"
    assert freeze["candidate_freeze"]["artifact_sha256"] == (
        CANDIDATE_ARTIFACT_SHA256
    )
    assert freeze["candidate_freeze"]["runtime_registration"] is None
    assert freeze["candidate_freeze"]["active"] is False
    assert freeze["candidate_freeze"]["shadow"] is False
    assert freeze["non_product_boundary"]["default_product_import_or_discovery"] is False
    assert freeze["non_product_boundary"]["baseline_fallback"] == (
        "existing_No-Skill_unchanged"
    )
    for relative, expected in freeze["experiment_freeze"][
        "source_and_tests"
    ].items():
        assert sha256_file(ROOT / relative) == expected


def test_phase_budget_membership_is_complete_before_any_phase_provider_call() -> None:
    source_task_ids = task_ids_for_cases(SOURCE_CASE_IDS)
    assert len(source_task_ids) == 8
    assert len(set(source_task_ids)) == 8
    freeze = json.loads(
        (ROOT / "V5_D_STAGE_2_EXPERIMENT_FREEZE.json").read_text(
            encoding="utf-8"
        )
    )
    allocation = freeze["experiment_freeze"][
        "durable_phase_budget_allocation"
    ]
    assert allocation["source"]["logical_provider_calls"] == 104
    assert allocation["heldout"]["logical_provider_calls"] == 156
    assert (
        allocation["source"]["paid_cost_hard_stop_usd"]
        + allocation["heldout"]["paid_cost_hard_stop_usd"]
        == 0.50
    )
