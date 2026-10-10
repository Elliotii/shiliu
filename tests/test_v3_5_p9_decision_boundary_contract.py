from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_AMENDMENT = (
    ROOT / "research/v3_5/checkpoints/checkpoint_1/amendment_v1"
)
P9 = (
    ROOT
    / "research/v3_5/product_query_set_v1/f1a_candidate_builder_decision"
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def test_p9_is_ready_but_not_restarted() -> None:
    decision = load_json(
        CHECKPOINT_AMENDMENT
        / "checkpoint_1_amendment.execution_decision.json"
    )
    assert decision["P9"] == {
        "restart_readiness": True,
        "restarted": False,
        "status": "blocked_pending_v3_5_b_acceptance",
    }


def test_no_downstream_authorization_or_stage_start() -> None:
    decision = load_json(
        CHECKPOINT_AMENDMENT
        / "checkpoint_1_amendment.execution_decision.json"
    )
    assert decision["F1A_authorized"] is False
    assert decision["F1B_authorized"] is False
    assert decision["Stage4_started"] is False


def test_prior_p9_block_is_preserved_without_a_decision_candidate() -> None:
    blocked_response = (
        P9 / "P9_F1A_CANDIDATE_BUILDER_DECISION_BLOCKED_RESPONSE.md"
    ).read_text()
    assert "P9 F1A Candidate Builder Decision Blocked" in blocked_response
    assert "PQS_V1_Q017" in blocked_response
    assert "Decision Candidate" in blocked_response
    assert not any(P9.glob("*EXECUTION_CANDIDATE*"))
