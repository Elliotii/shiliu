from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.v5_d_r1_evaluator import EVALUATOR_VERSION, evaluate_pair


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _arm(
    root: Path,
    *,
    status: str,
    citations: list[str],
    repeated: bool,
    treatment: bool,
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
            {"event_type": "guard", "guard_decision": "repeated_search"}
        )
    candidate = {}
    if treatment:
        candidate = {
            "runtime_registration": None,
            "active": False,
            "shadow": False,
            "audit": [
                {
                    "applicable": True,
                    "materially_new_target": True,
                    "objective_coverage_bundle": True,
                },
                {
                    "applicable": True,
                    "post_recovery_completion_gate": True,
                    "coverage_satisfied": True,
                    "second_recovery_performed": False,
                },
            ],
        }
    _write(
        root / "deep_provider_trace.private.json",
        {
            "termination_reason": (
                "answer_ready" if not repeated else "repeated_search"
            ),
            "events": events,
            "tool_calls": tools,
            "r1_candidate_treatment": candidate,
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
                    "recovery_quality_pass": True,
                    "stop_correctness_pass": False,
                    "final_answer_no_material_regression": True,
                },
                "treatment": {
                    "covered_required_aspects": ["a", "b"],
                    "counterexample_or_limitation_preserved": True,
                    "source_diversity_requirement_pass": True,
                    "recovery_quality_pass": True,
                    "stop_correctness_pass": True,
                    "final_answer_no_material_regression": True,
                },
            },
        },
    )
    _database(database)
    return manifest, review, database


def test_source_pair_requires_grounded_coverage_handoff_and_stop(
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
        treatment=False,
        calls=5,
        tools=3,
    )
    _arm(
        treatment,
        status="valid_partial",
        citations=["c1", "c2"],
        repeated=False,
        treatment=True,
        calls=7,
        tools=4,
    )
    result = evaluate_pair(
        case_id="C1",
        case_manifest=manifest,
        baseline_dir=baseline,
        treatment_dir=treatment,
        review_path=review,
        database=database,
    )
    assert result["pair_pass"] is True
    assert result["delta"]["required_aspects"] == 1
    assert result["delta"]["grounded_current_citations"] == 2
    assert result["material_post_recovery_mechanism_change_pass"] is True
    assert result["recovery_stop_pass"] is True


def test_more_citations_without_required_aspect_delta_fails(tmp_path: Path) -> None:
    manifest, review, database = _inputs(tmp_path)
    value = json.loads(review.read_text(encoding="utf-8"))
    value["arms"]["treatment"]["covered_required_aspects"] = ["a"]
    _write(review, value)
    baseline = tmp_path / "baseline"
    treatment = tmp_path / "treatment"
    _arm(
        baseline,
        status="valid_insufficient",
        citations=[],
        repeated=True,
        treatment=False,
        calls=5,
        tools=3,
    )
    _arm(
        treatment,
        status="valid_partial",
        citations=["c1", "c2"],
        repeated=False,
        treatment=True,
        calls=7,
        tools=4,
    )
    result = evaluate_pair(
        case_id="C1",
        case_manifest=manifest,
        baseline_dir=baseline,
        treatment_dir=treatment,
        review_path=review,
        database=database,
    )
    assert result["pair_pass"] is False
    assert result["grounded_improvement_pass"] is False
    assert result["longer_answer_hit_or_search_count_used_as_success_proxy"] is False


def test_repeated_search_removed_without_stop_correctness_fails(
    tmp_path: Path,
) -> None:
    manifest, review, database = _inputs(tmp_path)
    value = json.loads(review.read_text(encoding="utf-8"))
    value["arms"]["treatment"]["stop_correctness_pass"] = False
    _write(review, value)
    baseline = tmp_path / "baseline"
    treatment = tmp_path / "treatment"
    _arm(
        baseline,
        status="valid_insufficient",
        citations=[],
        repeated=True,
        treatment=False,
        calls=5,
        tools=3,
    )
    _arm(
        treatment,
        status="valid_partial",
        citations=["c1", "c2"],
        repeated=False,
        treatment=True,
        calls=7,
        tools=4,
    )
    result = evaluate_pair(
        case_id="C1",
        case_manifest=manifest,
        baseline_dir=baseline,
        treatment_dir=treatment,
        review_path=review,
        database=database,
    )
    assert result["pair_pass"] is False
    assert result["recovery_stop_pass"] is False
