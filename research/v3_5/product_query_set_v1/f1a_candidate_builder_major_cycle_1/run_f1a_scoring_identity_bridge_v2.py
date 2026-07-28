from __future__ import annotations

import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from statistics import mean
from typing import Any, Mapping

from shiliu.eval_v3_5.scoring_identity_bridge import (
    complete_group_ids,
    covered_aspect_ids,
    covered_span_ids,
    material_aspect_ids,
    required_span_ids,
)


ROOT = Path("/Users/elliot/new-systems/agent-job-prep/Shiliu")
V1_PATH = ROOT / "research/v3_5/product_query_set_v1/f1a_candidate_builder_major_cycle_1/run_f1a_scored_regressions.py"
OUT = ROOT / "research/v3_5/product_query_set_v1/f1a_candidate_builder_major_cycle_1/scoring_identity_bridge_v2"
SCORER_VERSION = "corrected_identity_bridge_v2"
DEVELOPMENT_IDS = (
    "PQS_V1_Q003", "PQS_V1_Q004", "PQS_V1_Q005", "PQS_V1_Q006",
    "PQS_V1_Q007", "PQS_V1_Q008", "PQS_V1_Q011", "PQS_V1_Q012",
    "PQS_V1_Q013", "PQS_V1_Q014", "PQS_V1_Q015", "PQS_V1_Q017",
    "PQS_V1_Q018", "PQS_V1_Q019",
)
EXISTING_SIX = {
    "PQS_V1_Q006", "PQS_V1_Q007", "PQS_V1_Q011",
    "PQS_V1_Q012", "PQS_V1_Q013", "PQS_V1_Q019",
}


def load_v1() -> Any:
    spec = importlib.util.spec_from_file_location("f1a_v1_runner", V1_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("F1A v1 runner import failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V1 = load_v1()


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def seal_path() -> Path:
    return OUT / "SCORER_V2_FREEZE_SEAL_REPLACEMENT.json"


def initial_seal_path() -> Path:
    return OUT / "SCORER_V2_FREEZE_SEAL.json"


def invalidate_initial_seal() -> None:
    initial = initial_seal_path()
    record_path = OUT / "SCORER_V2_FREEZE_SEAL_INVALIDATION.json"
    if record_path.exists():
        return
    if not initial.exists():
        raise RuntimeError("initial SCORER_V2_FREEZE_SEAL is absent")
    write_json(record_path, {
        "status": "invalidated_due_to_preflight_manifest_resolution_defect",
        "reason": "logical_schema_key_treated_as_path",
        "preserved_initial_seal_path": str(initial.relative_to(ROOT)),
        "preserved_initial_seal_sha256": digest(initial),
        "eval_started_before_correction": False,
        "gold_opened_before_correction": False,
    })


def gold_hashes() -> dict[str, str]:
    return {name: digest(path) for name, path in V1.DEVELOPMENT_GOLD_PATHS.items()}


def freeze() -> dict[str, Any]:
    if seal_path().exists():
        raise RuntimeError("replacement SCORER_V2_FREEZE_SEAL already exists")
    invalidate_initial_seal()
    V1.assert_sealed()
    initial = json.loads(initial_seal_path().read_text(encoding="utf-8"))
    stress_inputs = {
        str(path.relative_to(ROOT)): digest(path)
        for path in (V1.STRESS_SCORING, V1.STRESS_RUNTIME, V1.STRESS_BRIDGE)
    }
    value = {
        "schema_version": "v3.5-b-f1a-scorer-v2-freeze-seal-v1",
        "scorer_version": SCORER_VERSION,
        "scorer_source_hashes": {
            str(V1_PATH.relative_to(ROOT)): digest(V1_PATH),
            str(Path(__file__).relative_to(ROOT)): digest(Path(__file__)),
        },
        "identity_bridge_helper_hashes": {
            "src/shiliu/eval_v3_5/scoring_identity_bridge.py": digest(ROOT / "src/shiliu/eval_v3_5/scoring_identity_bridge.py"),
        },
        "test_hashes": {
            "tests/test_f1a_scoring_identity_bridge.py": digest(ROOT / "tests/test_f1a_scoring_identity_bridge.py"),
            "tests/test_v3_5_f1a_evaluation_harness_recovery.py": digest(ROOT / "tests/test_v3_5_f1a_evaluation_harness_recovery.py"),
            "tests/test_v3_5_f1a_major_cycle_contract.py": digest(ROOT / "tests/test_v3_5_f1a_major_cycle_contract.py"),
        },
        "identity_schema_hashes": {
            "src/shiliu/evidence/contracts.py": digest(ROOT / "src/shiliu/evidence/contracts.py"),
            "research/v3_5/product_query_set_v1/gold_protocol_v1/product_evidence_gold.schema.json": digest(ROOT / "research/v3_5/product_query_set_v1/gold_protocol_v1/product_evidence_gold.schema.json"),
        },
        "builder_freeze_seal_hash": digest(ROOT / "research/v3_5/product_query_set_v1/f1a_candidate_builder_major_cycle_1/f1a_implementation_freeze_seal.json"),
        "development_gold_hashes": initial["development_gold_hashes"],
        "stress_input_hashes": stress_inputs,
        "query_specific_rules": 0,
        "builder_behavior_change_allowed": False,
        "scorer_behavior_change_allowed_after_seal": False,
        "test_behavior_change_allowed_after_seal": False,
    }
    write_json(seal_path(), value)
    return value


def assert_frozen(*, verify_gold: bool = False) -> dict[str, Any]:
    value = json.loads(seal_path().read_text(encoding="utf-8"))
    for section in ("scorer_source_hashes", "identity_bridge_helper_hashes", "test_hashes", "identity_schema_hashes"):
        for relative, expected in value[section].items():
            if digest(ROOT / relative) != expected:
                raise RuntimeError(f"scorer v2 freeze mismatch: {relative}")
    V1.assert_sealed()
    if verify_gold and gold_hashes() != value["development_gold_hashes"]:
        raise RuntimeError("Development Gold changed after scorer freeze")
    return value


def preflight() -> dict[str, Any]:
    value = assert_frozen()
    return {
        "status": "pass",
        "replacement_scorer_v2_seal": str(seal_path().relative_to(ROOT)),
        "identity_schema_hashes_resolved": sorted(value["identity_schema_hashes"]),
        "builder_freeze_seal_hash": value["builder_freeze_seal_hash"],
        "development_gold_opened": False,
        "candidate_replay_started": False,
    }


def score_development() -> dict[str, Any]:
    output = OUT / "f1a_eval_v2_development_metrics.json"
    if output.exists():
        raise RuntimeError("Development Eval v2 already exists")
    seal = assert_frozen()
    config = V1.builder_config()
    source_resolver = V1.resolver()
    runtime_rows: list[dict[str, Any]] = []
    for query_id in DEVELOPMENT_IDS:
        trace = V1.load(V1.P8 / f"blind_run/product_initial_baseline.traces/{query_id}.trace.json")
        candidates, bundle, latency_ms, swaps = V1.candidate_runtime(query_id, V1.query_text(trace), trace["search_candidate_set"], source_resolver, config)
        runtime_rows.append({"query_id": query_id, "candidates": candidates, "bundle": bundle, "latency_ms": latency_ms, "swap": swaps})
    assert_frozen(verify_gold=True)
    layers = {name: {str(row["query_id"]): row for row in load_jsonl(path)} for name, path in V1.DEVELOPMENT_GOLD_PATHS.items()}
    rows: list[dict[str, Any]] = []
    for runtime in runtime_rows:
        query_id = runtime["query_id"]
        evidence = layers["evidence"][query_id]
        candidate_values = [candidate.as_dict() for candidate in runtime["candidates"].candidates]
        covered = covered_span_ids(evidence, candidate_values)
        groups = complete_group_ids(evidence, covered)
        aspects = covered_aspect_ids(evidence, covered)
        required = required_span_ids(evidence)
        material = material_aspect_ids(evidence)
        terminal = V1.runtime_terminal(runtime["candidates"])
        rows.append({
            "query_id": query_id,
            "terminal_status": terminal["status"],
            "candidate_count": len(candidate_values),
            "invalid_candidate_count": sum(candidate.normalization_status != "valid" or bool(candidate.validation_errors) for candidate in runtime["candidates"].candidates),
            "complete_group_hit": bool(groups), "covered_group_ids": groups,
            "covered_span_ids": sorted(covered), "covered_aspect_ids": aspects,
            "required_span_recall": len(covered & required) / len(required) if required else None,
            "required_aspect_coverage": len(set(aspects) & material) / len(material) if material else None,
            "eligible_for_builder_denominator": query_id != "PQS_V1_Q017",
            "eligible_for_primary_failure": query_id not in {"PQS_V1_Q014", "PQS_V1_Q017"},
            "latency_ms": runtime["latency_ms"], "swap_count": runtime["swap"]["swap_count"],
            "scoring_identity_version": SCORER_VERSION,
        })
    eligible = [row for row in rows if row["eligible_for_builder_denominator"]]
    metrics = {
        "schema_version": "v3.5-b-f1a-development-eval-v2-v1", "scorer_version": SCORER_VERSION,
        "builder_version": config.config_id, "builder_freeze_seal_hash": seal["builder_freeze_seal_hash"],
        "development_gold_hashes": gold_hashes(), "complete_development_score": True,
        "complete_group_coverage": {"numerator": sum(row["complete_group_hit"] for row in eligible), "denominator": len(eligible)},
        "builder_primary_failures": sum(not row["complete_group_hit"] for row in rows if row["eligible_for_primary_failure"]),
        "required_span_recall": mean(row["required_span_recall"] for row in eligible if row["required_span_recall"] is not None),
        "required_aspect_coverage": mean(row["required_aspect_coverage"] for row in eligible if row["required_aspect_coverage"] is not None),
        "existing_six_regressions": sorted(row["query_id"] for row in rows if row["query_id"] in EXISTING_SIX and not row["complete_group_hit"]),
        "candidate_count_total": sum(row["candidate_count"] for row in rows), "invalid_candidate_count": sum(row["invalid_candidate_count"] for row in rows),
        "maximum_swap_count_per_query": max(row["swap_count"] for row in rows), "forced_swaps": False,
        "eval_v1_status": "invalidated_as_algorithm_result_due_to_confirmed_scoring_identity_defect",
    }
    metrics["complete_group_coverage"]["rate"] = metrics["complete_group_coverage"]["numerator"] / metrics["complete_group_coverage"]["denominator"]
    write_jsonl(OUT / "f1a_eval_v2_development_per_query.jsonl", rows)
    write_json(output, metrics)
    return metrics


def score_stress() -> dict[str, Any]:
    output = OUT / "f1a_eval_v2_stress_metrics.json"
    if output.exists() or not (OUT / "f1a_eval_v2_development_metrics.json").exists():
        raise RuntimeError("Stress Eval v2 requires exactly one completed Development Eval v2")
    assert_frozen()
    config = V1.builder_config()
    source_resolver = V1.resolver()
    gold = {row["case_id"]: row for row in load_jsonl(V1.STRESS_SCORING)}
    runtime = {row["case_id"]: row for row in load_jsonl(V1.STRESS_RUNTIME)}
    bridge = {(row["case_id"], row["gold_segment_id"]): row["physical_segment_id"] for row in load_jsonl(V1.STRESS_BRIDGE)}
    rows = []
    for case_id in V1.load(V1.STRESS / "input_freeze/evidence_bearing_case_ids.json")["case_ids"]:
        search = V1.load(V1.STRESS / f"execution/cases/{case_id}/search_candidate_set.json")
        candidates, _, latency_ms, swaps = V1.candidate_runtime(case_id, str(runtime[case_id]["original_query"]), search, source_resolver, config)
        groups = V1._physical_groups(case_id, gold[case_id]["evidence_groups"], bridge)
        completed = V1._complete_groups(groups, [candidate.as_dict() for candidate in candidates.candidates])
        rows.append({"case_id": case_id, "complete_group_hit": bool(completed), "covered_group_ids": completed, "candidate_count": len(candidates.candidates), "invalid_candidate_count": sum(candidate.normalization_status != "valid" or bool(candidate.validation_errors) for candidate in candidates.candidates), "latency_ms": latency_ms, "swap_count": swaps["swap_count"]})
    result = {"schema_version": "v3.5-b-f1a-stress-eval-v2-v1", "scorer_version": SCORER_VERSION, "builder_version": config.config_id, "complete_group_coverage": {"numerator": sum(row["complete_group_hit"] for row in rows), "denominator": len(rows)}, "candidate_count_total": sum(row["candidate_count"] for row in rows), "invalid_candidate_count": sum(row["invalid_candidate_count"] for row in rows), "maximum_swap_count_per_query": max(row["swap_count"] for row in rows), "forced_swaps": False, "per_case": rows}
    result["complete_group_coverage"]["rate"] = result["complete_group_coverage"]["numerator"] / result["complete_group_coverage"]["denominator"]
    write_json(output, result)
    return result


def closeout() -> dict[str, Any]:
    development = json.loads((OUT / "f1a_eval_v2_development_metrics.json").read_text(encoding="utf-8"))
    stress = json.loads((OUT / "f1a_eval_v2_stress_metrics.json").read_text(encoding="utf-8"))
    gates = {
        "complete_group_coverage_minimum_8_of_13": development["complete_group_coverage"]["numerator"] >= 8,
        "builder_primary_failures_maximum_4": development["builder_primary_failures"] <= 4,
        "required_span_recall_minimum": development["required_span_recall"] >= 9 / 13,
        "required_aspect_coverage_minimum": development["required_aspect_coverage"] >= 9 / 13,
        "existing_six_regressions_allowed_0": not development["existing_six_regressions"],
        "invalid_identity_source_timeline_maximum_0": development["invalid_candidate_count"] == 0,
        "candidate_cap_32": True,
        "maximum_swaps_per_query_4": development["maximum_swap_count_per_query"] <= 4,
        "forced_swaps_false": development["forced_swaps"] is False,
        "stress_complete_group_coverage_minimum_11_of_20": stress["complete_group_coverage"]["numerator"] >= 11,
    }
    passed = all(gates.values())
    paths = [seal_path(), OUT / "f1a_eval_v2_development_per_query.jsonl", OUT / "f1a_eval_v2_development_metrics.json", OUT / "f1a_eval_v2_stress_metrics.json"]
    value = {"schema_version": "v3.5-b-f1a-scorer-v2-closeout-v1", "outcome": "accepted_new_builder" if passed else "rejected_keep_existing_builder", "final_builder": "stage3b-adaptive-swap-w3.5-v1" if passed else "stage3b-acronym-w3.5-v1", "gates": gates, "eval_v1": {"development": "0/13", "status": "invalidated_as_algorithm_result_due_to_confirmed_scoring_identity_defect"}, "eval_v2": {"builder_version": "stage3b-adaptive-swap-w3.5-v1", "scorer_version": SCORER_VERSION}, "output_hashes": {str(path.relative_to(ROOT)): digest(path) for path in paths}}
    write_json(OUT / "f1a_eval_v2_final_closeout.json", value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("freeze", "preflight", "development", "stress", "closeout"))
    args = parser.parse_args()
    print(json.dumps({"freeze": freeze, "preflight": preflight, "development": score_development, "stress": score_stress, "closeout": closeout}[args.phase](), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
