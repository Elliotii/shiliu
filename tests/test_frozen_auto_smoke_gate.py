from __future__ import annotations

from shiliu.eval_v3_5 import frozen_auto_smoke as smoke


def _case(case_id: str, hit: bool = True, router_miss: bool = False):
    return {
        "case_id": case_id,
        "label_role": "evidence_bearing",
        "q0": {"target_video_hit": hit, "router_miss": router_miss},
        "q1": {"target_video_hit": True},
        "q2": {"target_video_hit": True},
    }


def _record(**overrides):
    value = {
        "runtime_error": False,
        "router_mode_consistent": True,
        "auto_router_invoked": True,
        "fallback": False,
    }
    value.update(overrides)
    return value


def test_frozen_auto_smoke_pass_gate_requires_q0_nine_of_nine() -> None:
    rows = [_case(f"C{index}") for index in range(9)]
    result = smoke.apply_release_gate(
        rows=rows,
        all_records=[_record()],
        exact_records=[{"auto_vs_lexical_regression": False}],
        runtime_stable=True,
        snapshot_stable=True,
    )
    assert result["release_gate"] == "passed"
    rows[-1]["q0"]["target_video_hit"] = False
    assert smoke.apply_release_gate(
        rows=rows,
        all_records=[_record()],
        exact_records=[],
        runtime_stable=True,
        snapshot_stable=True,
    )["release_gate"] == "failed"


def test_frozen_auto_smoke_router_gap_recommends_hybrid_without_modification() -> None:
    rows = [_case(f"C{index}") for index in range(8)]
    rows.append(_case("miss", hit=False, router_miss=True))
    result = smoke.apply_release_gate(
        rows=rows,
        all_records=[_record()],
        exact_records=[],
        runtime_stable=True,
        snapshot_stable=True,
    )
    assert result["failure_class"] == "frozen_auto_router_gap"
    assert result["authorized_fallback_recommendation"] == "hybrid"
    assert result["router_change_authorized"] is False


def test_frozen_auto_smoke_runtime_failure_blocks_quality_conclusion() -> None:
    result = smoke.apply_release_gate(
        rows=[_case(f"C{index}") for index in range(9)],
        all_records=[_record(runtime_error=True)],
        exact_records=[],
        runtime_stable=True,
        snapshot_stable=True,
    )
    assert result["release_gate"] == "blocked"
    assert result["quality_conclusion_allowed"] is False
