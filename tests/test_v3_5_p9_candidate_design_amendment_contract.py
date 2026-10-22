from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
P9 = (
    ROOT
    / "research/v3_5/product_query_set_v1/"
    "f1a_candidate_builder_decision_restart"
)
OUTPUT = P9 / "design_amendment_v1"
DESIGN = OUTPUT / "f1a_candidate_design.amended_v1.json"


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def amended_design() -> dict:
    return load_json(DESIGN)


def test_p9_execute_decision_unchanged() -> None:
    design = amended_design()
    assert design["p9_decision"] == "execute"
    assert design["failure_mechanism"] == {
        "primary": "bounded_candidate_pruning_coverage_gap",
        "secondary": "dedup_below_threshold_leaves_complement_gap",
    }


def test_original_design_preserved_and_superseded() -> None:
    original = P9 / "f1a_candidate_design.json"
    superseded = amended_design()["superseded_design"]
    assert original.is_file()
    assert digest(original) == (
        "8e591d14163178bb5ab6ad4c446324c7baaa9184773709403c20dbe409f7bad7"
    )
    assert superseded["status"] == "superseded_before_implementation"
    assert superseded["implemented"] is False
    assert superseded["evaluated"] is False


def test_amended_design_is_unique_active_design() -> None:
    design = amended_design()
    assert design["active_design"]["name"] == "adaptive_bounded_coverage_swap_v1"
    assert design["active_design"]["status"] == "implementation_candidate"
    assert design["superseded_design"]["status"] != "implementation_candidate"
    assert load_json(OUTPUT / "p9_candidate_design_amendment.audit.json")[
        "supersession"
    ]["active_design_is_unique"] is True


def test_preserves_original_top_32_as_initial_set() -> None:
    active = amended_design()["active_design"]
    assert active["initial_selected_set"] == {
        "candidate_cap": 32,
        "preserve_original_top_32": True,
        "source": "current_builder_original_ranked_output",
    }
    assert active["candidate_pool"]["selected_set"] == "original_top_32"


def test_swap_count_is_zero_to_four() -> None:
    swap = amended_design()["active_design"]["swap_rule"]
    assert swap["minimum_swaps_per_query"] == 0
    assert swap["maximum_swaps_per_query"] == 4


def test_swaps_are_not_forced() -> None:
    swap = amended_design()["active_design"]["swap_rule"]
    assert swap["forced_swaps"] is False
    assert swap["no_improvement_result"]["swap_count"] == 0
    assert swap["no_improvement_result"]["final_set_equals_original_top_32"] is True


def test_outside_candidate_requires_existing_query_support() -> None:
    active = amended_design()["active_design"]
    assert active["candidate_pool"]["outside_pool"] == (
        "candidates_ranked_after_top_32_from_same_builder_candidate_pool"
    )
    eligibility = active["outside_candidate_eligibility"]
    assert eligibility["query_supported_anchor_region"] == [
        "existing_query_anchor",
        "existing_acronym_or_entity_anchor",
        "existing_retrieval_chunk_lineage",
    ]
    assert eligibility["minimum_relevance_or_anchor_support"] == (
        "reuse_current_builder_admission_signal_or_threshold"
    )


def test_no_gold_runtime_signal() -> None:
    forbidden = amended_design()["active_design"]["runtime_forbidden_signals"]
    assert {
        "development_gold_required_aspect",
        "development_gold_required_span",
        "development_gold_segment",
        "query_id_rule",
        "video_id_rule",
    }.issubset(forbidden)


def test_redundancy_victim_not_fixed_to_ranks_29_to_32() -> None:
    active = amended_design()["active_design"]
    assert active["victim_rule"]["fixed_rank_29_to_32_replacement"] is False
    assert active["victim_priority"][:2] == [
        "higher_redundancy_with_selected_set",
        "lower_exclusive_interval_or_segment_coverage",
    ]


def test_strict_set_improvement_required() -> None:
    swap = amended_design()["active_design"]["swap_rule"]
    assert swap["strict_set_improvement_required"] is True
    assert swap["requirements"]["set_level_coverage_improves"] is True
    assert swap["requirements"]["query_support_guard_preserved"] is True


def test_candidate_and_window_budgets_unchanged() -> None:
    budgets = amended_design()["active_design"]["immutable_budgets"]
    assert budgets == {
        "candidate_cap": 32,
        "per_window_character_limit": 500,
        "per_window_seconds_limit": 60,
        "per_window_segment_limit": 6,
        "selector_candidate_count_budget": "unchanged",
        "total_character_limit": 6000,
        "total_seconds_limit": 600,
    }


def test_addressable_failures_and_q018_non_goal_unchanged() -> None:
    design = amended_design()
    assert design["addressable_failures"] == {
        "count": 5,
        "ids": [
            "PQS_V1_Q003",
            "PQS_V1_Q004",
            "PQS_V1_Q005",
            "PQS_V1_Q008",
            "PQS_V1_Q015",
        ],
    }
    assert design["non_goal"] == ["PQS_V1_Q018"]


def test_acceptance_thresholds_unchanged() -> None:
    metrics = amended_design()["acceptance_metrics"]
    assert metrics["builder_complete_group_coverage"] == {
        "before": "6/13",
        "minimum_after": "8/13",
    }
    assert metrics["builder_primary_failures"] == {
        "before": 6,
        "maximum_after": 4,
    }
    assert metrics["required_span_recall"]["minimum_after"] == 0.6923
    assert metrics["required_aspect_coverage"]["minimum_after"] == 0.6923
    assert metrics["existing_builder_hit_regression_allowed"] == 0


def test_no_code_prediction_scoring_or_gold_change() -> None:
    audit = load_json(OUTPUT / "p9_candidate_design_amendment.audit.json")
    scope = audit["scope"]
    assert scope["code_changed"] is False
    assert scope["predictions_rerun"] is False
    assert scope["scoring_rerun"] is False
    assert scope["query_split_gold_changed"] is False
    selector_v2_seal = load_json(ROOT / "SELECTOR_V2_FREEZE_SEAL.json")
    assert digest(ROOT / "src/shiliu/evidence/stage3a.py") == (
        selector_v2_seal["selector_source_hashes"]["src/shiliu/evidence/stage3a.py"]
    )
    assert digest(ROOT / "src/shiliu/evidence/stage3b.py") == (
        "8a2ed841efdf42f048347bf23ed1170a67ce7be0f3b03823eabef31847a80458"
    )


def test_no_frozen_access() -> None:
    audit = load_json(OUTPUT / "p9_candidate_design_amendment.audit.json")
    assert audit["scope"]["frozen_gold_opened"] is False


def test_no_f1a_implementation_f1b_or_stage4_start() -> None:
    audit = load_json(OUTPUT / "p9_candidate_design_amendment.audit.json")
    decision = load_json(
        OUTPUT / "p9_candidate_design_amendment.execution_decision.json"
    )
    assert audit["scope"]["f1a_implementation_started"] is False
    assert audit["scope"]["f1b_started"] is False
    assert audit["scope"]["stage4_started"] is False
    assert decision["f1a_implementation_authorized"] is False
    assert decision["f1a_major_cycles_remaining"] == 1
    assert decision["f1b_authorized"] is False
    assert decision["stage4_started"] is False
    assert not (ROOT / "F1A_IMPLEMENTATION_TASK.md").exists()
    assert not (OUTPUT / "F1A_IMPLEMENTATION_TASK.md").exists()


def test_manifest_hashes_match() -> None:
    rows = load_jsonl(OUTPUT / "p9_candidate_design_amendment.file_hash_manifest.jsonl")
    assert len(rows) == 7
    for row in rows:
        path = OUTPUT / row["path"]
        assert path.is_file()
        assert path.name != "p9_candidate_design_amendment.file_hash_manifest.jsonl"
        assert path.stat().st_size == row["bytes"]
        assert digest(path) == row["sha256"]


def test_authority_files_point_to_amended_design() -> None:
    for name in (
        "V3_5_CURRENT_STATE.md",
        "02_PRODUCT_QUERY_SET_AND_REMAINING_V3_5_PLAN.md",
        "03_V3_5_DECISION_AND_ARTIFACT_INDEX.md",
    ):
        text = (ROOT / name).read_text()
        assert "adaptive_bounded_coverage_swap_v1" in text
        assert "F1A_IMPLEMENTATION_CONTRACT" in text
