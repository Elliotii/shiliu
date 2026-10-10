from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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
from scripts.v5_d_r1_treatment import (
    CANDIDATE_ARTIFACT_SHA256,
    CANDIDATE_ID,
    CANDIDATE_INSTRUCTION,
    CandidateIdentityError,
    CoverageBundleFollowupDecisionService,
    objective_focus_query,
    objective_named_titles,
    objective_required_source_count,
    sha256_file,
    validate_candidate_artifact,
)


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "V5_D_CANDIDATE_EVIDENCE_DELTA_FOLLOWUP_V1_1.json"


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
        uploader=f"uploader-{video_id}",
        description="",
        summary_sections=[],
        user_notes=[],
        cleaned_transcript=[],
        metadata={},
        matched_excerpt=title,
        matched_sources=["title"],
        source_labels={"title": label},
    )


def _span(video_id: int, suffix: str) -> SimpleNamespace:
    return SimpleNamespace(
        video_id=video_id,
        citation_id=f"citation-{suffix}",
    )


def _state(
    *,
    query: str,
    last_action: SearchNavigationAction | SearchTranscriptsAction,
    navigation_documents: list[NavigationDocument],
    observation_kind: str,
    new_segments: list[str],
    evidence_spans: list[Any] | None = None,
    repeated_keys: list[str] | None = None,
) -> dict[str, Any]:
    last_key = action_key(AgentDecision(action=last_action))
    assert last_key is not None
    return {
        "run_id": "test",
        "query": query,
        "filters": {},
        "open_questions": [query],
        "resolved_questions": [],
        "evidence_spans": evidence_spans or [],
        "navigation_documents": navigation_documents,
        "visited_video_ids": [],
        "visited_segment_ids": [],
        "previous_queries": [last_key],
        "repeated_action_keys": repeated_keys or [last_key],
        "decision_rounds": 2,
        "tool_calls": 2,
        "consecutive_no_new_evidence": 1 if not new_segments else 0,
        "navigation_result_count": len(navigation_documents),
        "started_at": 0.0,
        "search_deadline": 100.0,
        "total_deadline": 200.0,
        "last_action": last_action.model_dump(mode="json"),
        "last_observation_summary": "bounded",
        "pending_observation": None,
        "errors": [],
        "stale_reasons": [],
        "events": [
            {
                "event_type": "observation",
                "observation_kind": observation_kind,
                "new_segment_ids": new_segments,
            }
        ],
        "usage": [],
        "termination_reason": None,
    }


def _service(provider: _Provider, *, health_valid: bool = True):
    return CoverageBundleFollowupDecisionService(
        lambda role: provider,
        DeepSearchBudget(),
        clock=lambda: 10.0,
        candidate_path=CANDIDATE,
        source_index_runtime_health_valid=health_valid,
    )


def test_candidate_identity_is_exact_non_active_and_one_recovery() -> None:
    payload = validate_candidate_artifact(CANDIDATE)
    assert sha256_file(CANDIDATE) == CANDIDATE_ARTIFACT_SHA256
    assert payload["candidate_id"] == CANDIDATE_ID
    assert payload["runtime_registration"] is None
    assert payload["active"] is False
    assert payload["shadow"] is False
    assert payload["recovery_logic"]["maximum_candidate_recovery_actions"] == 1
    assert payload["recovery_logic"]["second_recovery_authorized"] is False


def test_candidate_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    changed = tmp_path / "candidate.json"
    changed.write_text(CANDIDATE.read_text(encoding="utf-8") + "\n")
    with pytest.raises(CandidateIdentityError, match="hash mismatch"):
        validate_candidate_artifact(changed)


def test_objective_coverage_is_derived_without_gold() -> None:
    comparison = "比较《来源甲》和《来源乙》对“Claude Code”的讨论"
    open_collection = "研究“ReAct”，至少综合三条不同视频来源"
    assert objective_named_titles(comparison) == ("来源甲", "来源乙")
    assert objective_required_source_count(comparison) == 2
    assert objective_required_source_count(open_collection) == 3
    assert objective_focus_query(comparison) == "Claude Code"
    assert objective_focus_query(open_collection) == "ReAct"


def test_zero_delta_selects_one_named_multi_source_coverage_bundle() -> None:
    query = "比较《来源甲》和《来源乙》对“Claude Code”的讨论"
    last = SearchTranscriptsAction(
        kind="search_transcripts", query="Claude Code", video_ids=[101]
    )
    proposed = AgentDecision(
        action=SearchTranscriptsAction(
            kind="search_transcripts", query="Claude Code", video_ids=[202]
        )
    )
    provider = _Provider([proposed])
    service = _service(provider)
    state = _state(
        query=query,
        last_action=last,
        navigation_documents=[
            _document(101, "来源甲"),
            _document(202, "来源乙"),
        ],
        observation_kind="transcript_search",
        new_segments=[],
    )
    selected, _ = service.decide(state)  # type: ignore[arg-type]
    assert isinstance(selected.action, SearchTranscriptsAction)
    assert selected.action.query == "Claude Code"
    assert selected.action.video_ids == [101, 202]
    assert service.recovery_used is True
    assert service.audit[-1]["objective_coverage_bundle"] is True
    assert service.audit[-1]["second_recovery_authorized"] is False
    assert CANDIDATE_INSTRUCTION in provider.calls[0]["messages"][0]["content"]


def test_post_recovery_gate_stops_for_synthesis_without_provider_or_second_recovery() -> None:
    query = "比较《来源甲》和《来源乙》对“Claude Code”的讨论"
    last = SearchTranscriptsAction(
        kind="search_transcripts", query="Claude Code", video_ids=[101]
    )
    provider = _Provider(
        [
            AgentDecision(
                action=SearchTranscriptsAction(
                    kind="search_transcripts",
                    query="Claude Code",
                    video_ids=[202],
                )
            )
        ]
    )
    service = _service(provider)
    before = _state(
        query=query,
        last_action=last,
        navigation_documents=[
            _document(101, "来源甲"),
            _document(202, "来源乙"),
        ],
        observation_kind="transcript_search",
        new_segments=[],
    )
    recovery, _ = service.decide(before)  # type: ignore[arg-type]
    assert isinstance(recovery.action, SearchTranscriptsAction)
    after = _state(
        query=query,
        last_action=recovery.action,
        navigation_documents=before["navigation_documents"],
        observation_kind="transcript_search",
        new_segments=["s1", "s2"],
        evidence_spans=[_span(101, "a"), _span(202, "b")],
        repeated_keys=[
            *before["repeated_action_keys"],
            action_key(recovery),
        ],
    )
    stopped, metadata = service.decide(after)  # type: ignore[arg-type]
    assert isinstance(stopped.action, StopAction)
    assert metadata["finish_reason"] == "candidate_post_recovery_completion_gate"
    assert len(provider.calls) == 1
    assert service.audit[-1]["coverage_satisfied"] is True
    assert service.audit[-1]["second_recovery_performed"] is False


def test_exact_repeated_navigation_with_open_coverage_becomes_global_bundle() -> None:
    query = "研究“ReAct”，至少综合三条不同视频来源"
    repeated = SearchNavigationAction(
        kind="search_navigation", query="ReAct reasoning acting"
    )
    key = action_key(AgentDecision(action=repeated))
    assert key is not None
    provider = _Provider([AgentDecision(action=repeated)])
    service = _service(provider)
    state = _state(
        query=query,
        last_action=repeated,
        navigation_documents=[
            _document(1, "ReAct source one"),
            _document(2, "ReAct source two"),
            _document(3, "ReAct source three"),
        ],
        observation_kind="navigation",
        new_segments=[],
        repeated_keys=[key],
    )
    selected, _ = service.decide(state)  # type: ignore[arg-type]
    assert isinstance(selected.action, SearchTranscriptsAction)
    assert selected.action.query == "ReAct"
    assert selected.action.video_ids == []
    assert service.audit[-1]["trigger"] == (
        "proposed_exact_prior_action_with_coverage_gap"
    )


def test_non_applicable_state_uses_unchanged_baseline_context() -> None:
    query = "概括单一来源"
    proposed = AgentDecision(
        action=SearchNavigationAction(kind="search_navigation", query="单一来源")
    )
    provider = _Provider([proposed])
    service = _service(provider)
    state = _state(
        query=query,
        last_action=SearchNavigationAction(
            kind="search_navigation", query="initial"
        ),
        navigation_documents=[],
        observation_kind="navigation",
        new_segments=[],
    )
    selected, _ = service.decide(state)  # type: ignore[arg-type]
    assert selected == proposed
    assert CANDIDATE_INSTRUCTION not in provider.calls[0]["messages"][0]["content"]
    assert service.audit[-1]["baseline_fallback"] is True


def test_default_product_source_does_not_import_r1_treatment() -> None:
    matches = []
    for path in (ROOT / "src").rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        if "v5_d_r1_treatment" in content or "CoverageBundleFollowupDecisionService" in content:
            matches.append(path)
    assert matches == []


def test_candidate_json_contains_no_v1_2_or_active_registration() -> None:
    payload = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    assert payload["version"] == "1.1.0"
    assert payload["rollback_or_rejection_behavior"]["v1_2_automatic_revision"] is False
    assert payload["v1_0_to_v1_1_delta"]["not_added"] == [
        "second_recovery",
        "larger_recovery_count",
        "single_source_continue_search_heuristic",
        "termination_reason_or_repeat_count_trigger",
    ]
