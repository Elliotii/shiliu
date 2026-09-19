from __future__ import annotations

from dataclasses import fields
from hashlib import sha256
import inspect
from pathlib import Path

from shiliu.evidence.stage3a import (
    ADAPTIVE_BOUNDED_COVERAGE_SWAP_VERSION,
    F1A_CANDIDATE_BUILDER_VERSION,
    CandidateBuilderConfig,
    adaptive_bounded_coverage_swap,
)


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_single_active_design_and_builder_version() -> None:
    assert ADAPTIVE_BOUNDED_COVERAGE_SWAP_VERSION == "adaptive_bounded_coverage_swap_v1"
    assert F1A_CANDIDATE_BUILDER_VERSION == "stage3b-adaptive-swap-w3.5-v1"


def test_candidate_and_window_budgets_are_unchanged() -> None:
    config = CandidateBuilderConfig(within_video_max_candidates=32)
    assert config.within_video_max_candidates == 32
    assert config.max_segments_per_candidate == 6
    assert config.hard_max_duration_seconds == 60
    assert config.hard_max_characters == 500
    assert config.within_video_max_total_union_duration_seconds == 600
    assert config.within_video_max_total_characters == 6000
    assert config.adaptive_coverage_swap_max_swaps == 4


def test_end_to_end_builder_trace_declares_query_level_four_swap_limit() -> None:
    source = (ROOT / "src/shiliu/evidence/stage3a.py").read_text()
    assert '"adaptive_bounded_coverage_swap_query_limit": 4' in source
    assert "remaining_query_swap_budget" in source


def test_adaptive_swap_has_no_runtime_gold_case_or_video_parameter() -> None:
    parameters = set(inspect.signature(adaptive_bounded_coverage_swap).parameters)
    assert parameters == {"original_selected", "outside_pool", "config"}
    source = inspect.getsource(adaptive_bounded_coverage_swap).casefold()
    assert "gold_" not in source
    assert '.get("gold' not in source
    assert "query_id" not in source
    assert "video_id" not in source


def test_adaptive_swap_has_no_model_or_retrieval_call_surface() -> None:
    source = inspect.getsource(adaptive_bounded_coverage_swap)
    forbidden = (
        "complete_raw", "embedding", "search_library", "retrieve",
        "QwenEmbeddingProvider", "StructuredProvider",
    )
    assert all(value not in source for value in forbidden)


def test_structured_selector_source_is_unchanged() -> None:
    assert digest(ROOT / "src/shiliu/evidence/stage3b.py") == (
        "8a2ed841efdf42f048347bf23ed1170a67ce7be0f3b03823eabef31847a80458"
    )


def test_config_schema_adds_only_bounded_swap_controls() -> None:
    names = {value.name for value in fields(CandidateBuilderConfig)}
    assert {
        "adaptive_coverage_swap_enabled",
        "adaptive_coverage_swap_max_swaps",
        "candidate_allocation_policy_version",
    }.issubset(names)
