from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.v5_d_stage2_evaluator import EVALUATOR_VERSION, evaluate_pair


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _arm(
    root: Path,
    *,
    status: str,
    citations: list[str],
    repeated: bool,
    recovery: bool,
    calls: int,
    tools: int,
) -> None:
    _write(
        root / "durable_product_projection.private.json",
        {
            "provisional_artifact": {
                "answer_status": status,
                "answer_blocks": [{"text": "bounded"}],
                "evidence_ids": citations,
                "limitations": ["limit"],
            }
        },
    )
    _write(
        root / "research_task_trace.private.json",
        {
            "evidence_validations": [
                {"evidence_id": value, "outcome": "current"}
                for value in citations
            ]
        },
    )
    events = []
    if repeated:
        events.append(
            {
                "event_type": "guard",
                "guard_decision": "repeated_search",
            }
        )
    audit = (
        [
            {
                "applicable": True,
                "materially_new_target": True,
            }
        ]
        if recovery
        else []
    )
    _write(
        root / "deep_provider_trace.private.json",
        {
            "termination_reason": "answer_ready" if not repeated else "repeated_search",
            "events": events,
            "tool_calls": tools,
            "stage2_candidate_treatment": {"audit": audit},
        },
    )
    rows = [
        {
            "status": "succeeded",
            "transport_attempts": 1,
            "cost_usd": "0.001",
            "usage": {"input_tokens": 100, "output_tokens": 20},
        }
        for _ in range(calls)
    ]
    (root / "usage_cost.private.jsonl").write_text(
        "".join(json.dumps(value) + "\n" for value in rows),
        encoding="utf-8",
    )


def _database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE research_evidence_identities "
            "(evidence_id TEXT PRIMARY KEY, video_id INTEGER NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO research_evidence_identities VALUES (?, ?)",
            [("c1", 1), ("c2", 2), ("c3", 3)],
        )
        connection.commit()
    finally:
        connection.close()


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest = tmp_path / "cases.json"
    review = tmp_path / "review.json"
    database = tmp_path / "eval.db"
    _write(
        manifest,
        {
            "cases": [
                {
                    "case_id": "C1",
                    "gold_required_aspects": ["a", "b", "c"],
                }
            ]
        },
    )
    _write(
        review,
        {
            "evaluator_version": EVALUATOR_VERSION,
            "case_id": "C1",
            "arms": {
                "baseline": {
                    "covered_required_aspects": ["a"],
                    "counterexample_or_limitation_preserved": True,
                    "source_diversity_requirement_pass": False,
                    "stop_correctness_pass": True,
                    "one_recovery_stop_risk_pass": True,
                },
                "treatment": {
                    "covered_required_aspects": ["a", "b"],
                    "counterexample_or_limitation_preserved": True,
                    "source_diversity_requirement_pass": True,
                    "stop_correctness_pass": True,
                    "one_recovery_stop_risk_pass": True,
                },
            },
        },
    )
    _database(database)
    return manifest, review, database


def test_source_pair_requires_grounded_delta_and_candidate_mechanism(
    tmp_path: Path,
) -> None:
    manifest, review, database = _inputs(tmp_path)
    baseline = tmp_path / "baseline"
    treatment = tmp_path / "treatment"
    _arm(
        baseline,
        status="valid_insufficient",
        citations=[],
        repeated=True,
        recovery=False,
        calls=5,
        tools=3,
    )
    _arm(
        treatment,
        status="valid_partial",
        citations=["c1"],
        repeated=False,
        recovery=True,
        calls=6,
        tools=4,
    )
    result = evaluate_pair(
        pair_kind="source",
        case_id="C1",
        case_manifest=manifest,
        baseline_dir=baseline,
        treatment_dir=treatment,
        review_path=review,
        database=database,
    )
    assert result["pair_pass"] is True
    assert result["delta"]["required_aspects"] == 1
    assert result["delta"]["grounded_current_citations"] == 1
    assert result["mechanism_pass"] is True


def test_unrelated_material_regression_is_negative_transfer(tmp_path: Path) -> None:
    manifest, review, database = _inputs(tmp_path)
    value = json.loads(review.read_text(encoding="utf-8"))
    value["arms"]["baseline"]["covered_required_aspects"] = ["a", "b"]
    value["arms"]["treatment"]["covered_required_aspects"] = ["a"]
    _write(review, value)
    baseline = tmp_path / "baseline"
    treatment = tmp_path / "treatment"
    _arm(
        baseline,
        status="valid_partial",
        citations=["c1", "c2"],
        repeated=False,
        recovery=False,
        calls=5,
        tools=3,
    )
    _arm(
        treatment,
        status="valid_insufficient",
        citations=["c1"],
        repeated=False,
        recovery=False,
        calls=5,
        tools=3,
    )
    result = evaluate_pair(
        pair_kind="unrelated",
        case_id="C1",
        case_manifest=manifest,
        baseline_dir=baseline,
        treatment_dir=treatment,
        review_path=review,
        database=database,
    )
    assert result["pair_pass"] is False
    assert result["negative_transfer"] is True
    assert result["longer_answer_hit_or_search_count_used_as_success_proxy"] is False
