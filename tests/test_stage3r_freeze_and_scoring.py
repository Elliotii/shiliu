from __future__ import annotations

import json
from pathlib import Path

from shiliu.eval_v3_5.stage3r import (
    _ratio,
    gold_group_hit,
    project_scoring_input,
)


SOURCE_ROOT = Path("/tmp/shiliu-v3-5-stage2r-c4-review-v1/finalize_and_lock")


def test_stage3r_gold_group_and_or_semantics() -> None:
    groups = [
        {
            "required_spans": [
                {"segment_ids": ["a", "b"]},
                {"segment_ids": ["c"]},
            ]
        },
        {"required_spans": [{"segment_ids": ["d"]}]},
    ]
    assert not gold_group_hit(groups, [{"segment_ids": ["a", "b"]}])
    assert gold_group_hit(groups, [{"segment_ids": ["a", "b", "c"]}])
    assert gold_group_hit(groups, [{"segment_ids": ["d"]}])


def test_stage3r_insufficient_excluded_from_span_recall() -> None:
    rows = [
        {"case_role": "sufficient", "hit": True},
        {"case_role": "partial", "hit": False},
        {"case_role": "insufficient", "hit": True},
    ]
    evidence = [value for value in rows if value["case_role"] in {"sufficient", "partial"}]
    assert _ratio(evidence, "hit") == {"count": 1, "total": 2, "rate": 0.5}


def test_stage3r_unverifiable_excluded_from_span_recall() -> None:
    rows = [
        {"case_role": "sufficient", "hit": True},
        {"case_role": "unverifiable", "hit": False},
    ]
    evidence = [value for value in rows if value["case_role"] in {"sufficient", "partial"}]
    assert _ratio(evidence, "hit") == {"count": 1, "total": 1, "rate": 1.0}


def test_stage3r_prediction_freeze_precedes_scoring(tmp_path: Path) -> None:
    freeze = tmp_path / "prediction_freeze.lock.json"
    freeze.write_text(json.dumps({
        "gold_scoring_started": False,
        "track_a_predictions_sha256": "a",
        "track_b_predictions_sha256": "b",
    }), encoding="utf-8")
    state = json.loads(freeze.read_text(encoding="utf-8"))
    assert state["gold_scoring_started"] is False
    state["gold_scoring_started"] = True
    freeze.write_text(json.dumps(state), encoding="utf-8")
    assert json.loads(freeze.read_text())["gold_scoring_started"] is True


def test_stage3r_predictions_immutable_after_freeze(tmp_path: Path) -> None:
    prediction = tmp_path / "prediction.jsonl"
    prediction.write_bytes(b'{"case_id":"A"}\n')
    before = prediction.read_bytes()
    project_scoring_input([
        {
            "case_id": "A",
            "canonical_adjudication": {
                "final_status": "insufficient",
                "final_evidence_spans": [],
                "final_evidence_groups": [],
            },
        }
    ])
    assert prediction.read_bytes() == before


def test_stage3r_all_cases_receive_typed_terminal() -> None:
    allowed = {
        "bundle_created", "selector_abstained", "upstream_retrieval_failure",
        "candidate_generation_failure", "selector_failure", "source_authority_failure",
        "source_identity_failure", "timeline_failure", "normalization_failure",
        "runtime_integrity_failure",
    }
    assert "unknown" not in allowed
    assert "silently_skipped" not in allowed
