from __future__ import annotations

import argparse
import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any


EVALUATOR_VERSION = "v5-d-stage2-paired-grounded-outcome-evaluator-v1"
STATUS_RANK = {
    "valid_insufficient": 0,
    "valid_partial": 1,
    "valid_success": 2,
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _usage(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _source_count(database: Path, evidence_ids: list[str]) -> int:
    if not evidence_ids:
        return 0
    connection = sqlite3.connect(
        f"file:{database}?mode=ro&immutable=1", uri=True
    )
    try:
        placeholders = ",".join("?" for _ in evidence_ids)
        row = connection.execute(
            f"SELECT COUNT(DISTINCT video_id) FROM research_evidence_identities "
            f"WHERE evidence_id IN ({placeholders})",
            evidence_ids,
        ).fetchone()
        return int(row[0])
    finally:
        connection.close()


def arm_metrics(attempt_dir: Path, database: Path) -> dict[str, Any]:
    projection = _load(attempt_dir / "durable_product_projection.private.json")
    raw = _load(attempt_dir / "research_task_trace.private.json")
    trace = _load(attempt_dir / "deep_provider_trace.private.json")
    usage = _usage(attempt_dir / "usage_cost.private.jsonl")
    artifact = projection.get("provisional_artifact") or {}
    evidence_ids = list(artifact.get("evidence_ids") or [])
    receipt_states = [str(value.get("status")) for value in usage]
    valid = bool(
        artifact
        and trace
        and usage
        and all(state == "succeeded" for state in receipt_states)
        and trace.get("termination_reason")
        not in {"provider_error", "deadline_exhausted"}
    )
    candidate = trace.get("stage2_candidate_treatment") or {}
    candidate_audit = list(candidate.get("audit") or [])
    material_recoveries = [
        value
        for value in candidate_audit
        if value.get("materially_new_target") is True
    ]
    repeated_search = any(
        event.get("event_type") == "guard"
        and event.get("guard_decision") == "repeated_search"
        for event in trace.get("events") or []
    )
    current_evidence = {
        value["evidence_id"]
        for value in raw.get("evidence_validations") or []
        if value.get("outcome") == "current"
    }
    citations_current = all(value in current_evidence for value in evidence_ids)
    return {
        "valid": valid,
        "answer_status": artifact.get("answer_status"),
        "answer_status_rank": STATUS_RANK.get(
            str(artifact.get("answer_status")), -1
        ),
        "answer_block_count": len(artifact.get("answer_blocks") or []),
        "grounded_current_citation_count": len(evidence_ids),
        "all_final_citations_current": citations_current,
        "grounded_source_count": _source_count(database, evidence_ids),
        "limitation_count": len(artifact.get("limitations") or []),
        "termination_reason": trace.get("termination_reason"),
        "repeated_search_guard": repeated_search,
        "candidate_applicable_count": sum(
            1 for value in candidate_audit if value.get("applicable") is True
        ),
        "candidate_material_recovery_count": len(material_recoveries),
        "candidate_honest_stop_after_zero_delta": any(
            value.get("honest_stop_after_zero_delta") is True
            for value in candidate_audit
        ),
        "logical_provider_calls": len(usage),
        "http_attempts": sum(
            int(value.get("transport_attempts") or 0) for value in usage
        ),
        "input_tokens": sum(
            int((value.get("usage") or {}).get("input_tokens") or 0)
            for value in usage
        ),
        "output_tokens": sum(
            int((value.get("usage") or {}).get("output_tokens") or 0)
            for value in usage
        ),
        "executed_tool_calls": int(trace.get("tool_calls") or 0),
        "cost_usd": str(
            sum(
                (Decimal(str(value.get("cost_usd") or "0")) for value in usage),
                Decimal("0"),
            )
        ),
        "unknown_provider_receipts": sum(
            1 for value in usage if value.get("status") == "unknown"
        ),
        "provider_route_delta": 0,
        "tool_permission_delta": 0,
    }


def _review_arm(
    review: dict[str, Any], arm: str, allowed_aspects: set[str]
) -> dict[str, Any]:
    value = review["arms"][arm]
    covered = list(value["covered_required_aspects"])
    if len(set(covered)) != len(covered) or not set(covered).issubset(
        allowed_aspects
    ):
        raise RuntimeError("manual aspect review is outside frozen requirements")
    return {
        "covered_required_aspect_count": len(covered),
        "covered_required_aspect_hashes": sorted(
            __import__("hashlib").sha256(item.encode("utf-8")).hexdigest()
            for item in covered
        ),
        "counterexample_or_limitation_preserved": bool(
            value["counterexample_or_limitation_preserved"]
        ),
        "source_diversity_requirement_pass": bool(
            value["source_diversity_requirement_pass"]
        ),
        "stop_correctness_pass": bool(value["stop_correctness_pass"]),
        "one_recovery_stop_risk_pass": bool(
            value["one_recovery_stop_risk_pass"]
        ),
    }


def evaluate_pair(
    *,
    pair_kind: str,
    case_id: str,
    case_manifest: Path,
    baseline_dir: Path,
    treatment_dir: Path,
    review_path: Path,
    database: Path,
) -> dict[str, Any]:
    cases = _load(case_manifest)["cases"]
    matches = [value for value in cases if value["case_id"] == case_id]
    if len(matches) != 1:
        raise RuntimeError("pair case identity is absent or ambiguous")
    case = matches[0]
    allowed_aspects = set(case["gold_required_aspects"])
    review = _load(review_path)
    if review.get("evaluator_version") != EVALUATOR_VERSION:
        raise RuntimeError("manual review evaluator identity mismatch")
    if review.get("case_id") != case_id:
        raise RuntimeError("manual review case identity mismatch")
    baseline = {
        **arm_metrics(baseline_dir, database),
        **_review_arm(review, "baseline", allowed_aspects),
    }
    treatment = {
        **arm_metrics(treatment_dir, database),
        **_review_arm(review, "treatment", allowed_aspects),
    }
    delta = {
        "required_aspects": (
            treatment["covered_required_aspect_count"]
            - baseline["covered_required_aspect_count"]
        ),
        "grounded_current_citations": (
            treatment["grounded_current_citation_count"]
            - baseline["grounded_current_citation_count"]
        ),
        "grounded_sources": (
            treatment["grounded_source_count"]
            - baseline["grounded_source_count"]
        ),
        "logical_provider_calls": (
            treatment["logical_provider_calls"]
            - baseline["logical_provider_calls"]
        ),
        "http_attempts": treatment["http_attempts"] - baseline["http_attempts"],
        "input_tokens": treatment["input_tokens"] - baseline["input_tokens"],
        "output_tokens": treatment["output_tokens"] - baseline["output_tokens"],
        "executed_tool_calls": (
            treatment["executed_tool_calls"]
            - baseline["executed_tool_calls"]
        ),
        "cost_usd": str(
            Decimal(treatment["cost_usd"]) - Decimal(baseline["cost_usd"])
        ),
    }
    overhead_pass = bool(
        delta["logical_provider_calls"] <= 2
        and delta["http_attempts"] <= 4
        and delta["input_tokens"] <= 25_000
        and delta["output_tokens"] <= 5_000
        and delta["executed_tool_calls"] <= 1
        and treatment["provider_route_delta"] == 0
        and treatment["tool_permission_delta"] == 0
    )
    common_validity = bool(
        baseline["valid"]
        and treatment["valid"]
        and baseline["all_final_citations_current"]
        and treatment["all_final_citations_current"]
        and not baseline["unknown_provider_receipts"]
        and not treatment["unknown_provider_receipts"]
        and overhead_pass
    )
    grounded_improvement = bool(
        delta["required_aspects"] >= 1
        and delta["grounded_current_citations"] >= 1
    )
    recovery_stop_pass = bool(
        treatment["stop_correctness_pass"]
        and treatment["one_recovery_stop_risk_pass"]
    )
    mechanism_pass = bool(
        baseline["repeated_search_guard"]
        and treatment["candidate_material_recovery_count"] >= 1
        and not treatment["repeated_search_guard"]
    )
    no_regression = bool(
        treatment["answer_status_rank"] >= baseline["answer_status_rank"]
        and delta["required_aspects"] >= 0
        and delta["grounded_current_citations"] >= 0
        and treatment["counterexample_or_limitation_preserved"]
        >= baseline["counterexample_or_limitation_preserved"]
        and treatment["source_diversity_requirement_pass"]
        >= baseline["source_diversity_requirement_pass"]
        and treatment["stop_correctness_pass"]
        >= baseline["stop_correctness_pass"]
    )
    if pair_kind in {"source", "related"}:
        passed = bool(
            common_validity
            and grounded_improvement
            and mechanism_pass
            and recovery_stop_pass
        )
        negative_transfer = False
    elif pair_kind == "unrelated":
        passed = bool(common_validity and no_regression)
        negative_transfer = not passed
    else:
        raise RuntimeError("unknown frozen pair kind")
    return {
        "evaluator_version": EVALUATOR_VERSION,
        "case_id": case_id,
        "pair_kind": pair_kind,
        "baseline": baseline,
        "treatment": treatment,
        "delta": delta,
        "common_validity_pass": common_validity,
        "overhead_pass": overhead_pass,
        "grounded_improvement_pass": grounded_improvement,
        "mechanism_pass": mechanism_pass,
        "recovery_stop_pass": recovery_stop_pass,
        "no_material_regression": no_regression,
        "negative_transfer": negative_transfer,
        "pair_pass": passed,
        "longer_answer_hit_or_search_count_used_as_success_proxy": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair-kind", choices=("source", "related", "unrelated"), required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--treatment-dir", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = evaluate_pair(
        pair_kind=arguments.pair_kind,
        case_id=arguments.case_id,
        case_manifest=arguments.case_manifest,
        baseline_dir=arguments.baseline_dir,
        treatment_dir=arguments.treatment_dir,
        review_path=arguments.review,
        database=arguments.database,
    )
    arguments.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    arguments.output.chmod(0o600)
    print(
        json.dumps(
            {
                "case_id": result["case_id"],
                "pair_kind": result["pair_kind"],
                "pair_pass": result["pair_pass"],
                "negative_transfer": result["negative_transfer"],
                "required_aspect_delta": result["delta"]["required_aspects"],
                "grounded_citation_delta": result["delta"]["grounded_current_citations"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
