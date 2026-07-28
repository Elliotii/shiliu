from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "research/v3_5/checkpoints/checkpoint_1"
P8 = ROOT / "research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3"
EXPECTED_LEDGER_SHA256 = (
    "b24882b24707b454796a681896024adc55ab3c5563ec0999a2c6880a26f5f3e2"
)
EXPECTED_SEAL_SHA256 = (
    "069fcf9e3ec70cf28d23674a2752033e608bf46937c990176dd6fb52f9e04617"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _audit() -> dict:
    return _json(CHECKPOINT / "checkpoint_1.audit.json")


def _decision() -> dict:
    return _json(CHECKPOINT / "checkpoint_1.execution_decision.json")


def test_checkpoint_1_ledger_hash_matches() -> None:
    assert (
        _sha256(CHECKPOINT / "V3_5_CHECKPOINT_1_DECISION_LEDGER.json")
        == EXPECTED_LEDGER_SHA256
    )


def test_p7_and_p8_acceptance_identity_matches() -> None:
    decision = _decision()
    assert decision["P7"] == "complete_and_accepted"
    assert decision["P8"] == "complete_and_accepted"
    assert decision["P8_formal_attempt"] == "P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_3"


def test_attempt_3_is_only_formal_p8_baseline() -> None:
    identity = _audit()["input_identity"]
    assert identity["attempt_3_is_only_formal_p8_baseline"] is True
    assert identity["attempt_1_and_2_historical_invalid_only"] is True


def test_prediction_seal_identity_matches() -> None:
    seal = P8 / "blind_run/product_initial_baseline.prediction_freeze.seal.json"
    assert _sha256(seal) == EXPECTED_SEAL_SHA256
    data = _json(seal)
    assert data["attempt_id"] == "P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_3"
    assert data["prediction_record_count"] == 14
    assert data["trace_count"] == 14


def test_current_state_records_p7_p8_complete() -> None:
    state = (ROOT / "V3_5_CURRENT_STATE.md").read_text()
    assert state.index("P8 Scoring / Checkpoint 1 Amendment") < state.index(
        "H0-R Corrected Handoff State"
    )
    assert "P8_prediction_set:" in state
    assert "status: valid_and_frozen" in state
    assert "formal_attempt: P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_3" in state


def test_decision_ledger_records_baseline_findings() -> None:
    index = (ROOT / "03_V3_5_DECISION_AND_ARTIFACT_INDEX.md").read_text()
    assert "Hit@10 `14/14`" in index
    assert "Builder Primary Failure `6`" in index
    assert "Selector Primary Failure `5`" in index
    assert "Invalid Decision `0`" in index


def test_artifact_index_contains_p7_p8_assets() -> None:
    index = (ROOT / "03_V3_5_DECISION_AND_ARTIFACT_INDEX.md").read_text()
    required = [
        "P7 aggregate package manifest",
        "Development Gold seal",
        "Frozen Gold seal",
        "Attempt 3 Input Manifest",
        "Attempt 3 Predictions",
        "Attempt 3 Trace Root",
        "Attempt 3 Prediction Seal",
        "Attempt 3 Scores",
        "Attempt 3 Per-query",
        "Attempt 3 Failure Attribution",
        "Attempt 3 Unjudged Pool",
        "Development Retrieval Pool Addendum",
        "Attempt 3 Stress Regression",
        "Attempt 3 Report",
        "Attempt 3 Manifest",
        "Attempt 3 Execution Decision",
        "Attempt 3 Hash Manifest",
        "Checkpoint 1 Report",
    ]
    for name in required:
        assert name in index


def test_remaining_plan_holds_p9_for_amendment_review() -> None:
    plan = (ROOT / "02_PRODUCT_QUERY_SET_AND_REMAINING_V3_5_PLAN.md").read_text()
    marker = "The active remaining\nroute begins"
    active_route = plan[plan.index(marker) :]
    assert active_route.index("P9  F1A Candidate Builder Decision") < active_route.index(
        "P10 F1B Deterministic Selector Decision"
    )
    assert "status: blocked_pending_v3_5_b_acceptance" in plan
    assert "restarted: false" in plan


def test_retrieval_not_reopened() -> None:
    assert _decision()["retrieval_reopen_by_default"] is False
    assert _audit()["governance"]["retrieval_reopen_signal"] is False


def test_f1a_signal_recorded_but_not_authorized() -> None:
    decision = _decision()
    assert decision["F1A_entry_signal"] is True
    assert decision["F1A_authorized"] is False


def test_f1b_signal_recorded_but_not_authorized() -> None:
    decision = _decision()
    assert decision["F1B_candidate_signal"] is True
    assert decision["F1B_authorized"] is False


def test_no_prediction_or_scoring_rerun() -> None:
    scope = _audit()["scope"]
    assert scope["predictions_rerun"] is False
    assert scope["traces_rerun"] is False
    assert scope["scoring_rerun"] is False
    assert scope["stress_regression_rerun"] is False


def test_no_component_behavior_change() -> None:
    assert _audit()["scope"]["functional_components_changed"] is False


def test_no_query_split_gold_change() -> None:
    assert _audit()["scope"]["query_split_gold_changed"] is False


def test_no_frozen_gold_access() -> None:
    assert _audit()["scope"]["frozen_gold_opened"] is False


def test_no_f1a_f1b_or_stage4_started() -> None:
    scope = _audit()["scope"]
    assert scope["F1A_started"] is False
    assert scope["F1B_started"] is False
    assert scope["Stage4_started"] is False
    assert scope["P9_started"] is False


def test_checkpoint_outputs_hash_consistent() -> None:
    rows = [
        json.loads(line)
        for line in (CHECKPOINT / "checkpoint_1.file_hash_manifest.jsonl")
        .read_text()
        .splitlines()
        if line
    ]
    immutable_checkpoint_paths = {
        "research/v3_5/checkpoints/checkpoint_1/CHECKPOINT_1_REPORT.md",
        "research/v3_5/checkpoints/checkpoint_1/checkpoint_1.manifest.json",
        "research/v3_5/checkpoints/checkpoint_1/checkpoint_1.audit.json",
        "research/v3_5/checkpoints/checkpoint_1/checkpoint_1.execution_decision.json",
        "research/v3_5/checkpoints/checkpoint_1/V3_5_CHECKPOINT_1_DECISION_LEDGER.json",
    }
    assert immutable_checkpoint_paths <= {row["path"] for row in rows}
    for row in rows:
        if row["path"] not in immutable_checkpoint_paths:
            continue
        path = ROOT / row["path"]
        assert path.is_file()
        assert _sha256(path) == row["sha256"]
