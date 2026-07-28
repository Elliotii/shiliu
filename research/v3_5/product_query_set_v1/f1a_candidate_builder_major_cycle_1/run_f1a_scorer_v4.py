from __future__ import annotations

import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from statistics import mean
from typing import Any, Mapping

from scorer_v4_projection import project_evidence, project_gold_span, unverifiable_candidate_count
from shiliu.eval_v3_5.scoring_identity_bridge import (
    VideoIdentityCanonicalizer,
    complete_group_ids,
    covered_aspect_ids,
    material_aspect_ids,
    required_span_ids,
)


ROOT = Path("/Users/elliot/new-systems/agent-job-prep/Shiliu")
CYCLE = ROOT / "research/v3_5/product_query_set_v1/f1a_candidate_builder_major_cycle_1"
P8 = ROOT / "research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3"
OUT = CYCLE / "scorer_v4_final_eval"
V1_PATH = CYCLE / "run_f1a_scored_regressions.py"
CONTRACT = CYCLE / "EVIDENCE_IDENTITY_CONTRACT_V1.json"
CONTRACT_SEAL = CYCLE / "EVIDENCE_IDENTITY_CONTRACT_V1_FREEZE_SEAL.json"
CONTRACT_RESULTS = CYCLE / "EVIDENCE_IDENTITY_CONTRACT_V1_TEST_RESULTS.json"
CONTRACT_TEST = CYCLE / "test_evidence_identity_contract_v1.py"
BRIDGE = ROOT / "src/shiliu/eval_v3_5/scoring_identity_bridge.py"
PROJECTION = CYCLE / "scorer_v4_projection.py"
PROJECTION_TEST = CYCLE / "test_scorer_v4_projection.py"
RUNNER = Path(__file__)
BUILDER_SEAL = CYCLE / "f1a_implementation_freeze_seal.json"
ACCEPTANCE_GATES = CYCLE / "f1a_final_acceptance_gate.json"
PREDICTION_SEAL = P8 / "blind_run/product_initial_baseline.prediction_freeze.seal.json"
PREDICTION_MANIFEST = P8 / "blind_run/product_initial_baseline.prediction_hash_manifest.jsonl"
EXPECTED_CONTRACT_HASH = "35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7"
EXPECTED_CONTRACT_RESULTS_HASH = "eb5e5fe0eb5b42f85b89ec984b7bceb0a9a7e9d494ba32f70d068af15449b091"
EXPECTED_BRIDGE_HASH = "e317a8056b39a409fe5e63b3a45950bc7c1c2f98e77bce6550fcb6e7a5d278c3"
EXPECTED_BUILDER_SEAL_HASH = "12f98f1635b2afee62a8be3c6b94a6d9a0090242ffdec1afdb97632adf913f4b"
EXPECTED_ACCEPTANCE_GATE_HASH = "ad94871fd6970a8a9e1f985788701776430bf6ca349a3754ad8c6f697e7d8a39"
EXPECTED_MAPPING_HASH = "61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1"
EXPECTED_STRESS_HASHES = {
    "research/v3_5/stage3r/scoring/development_scoring_projection.31_cases.jsonl": "0da94d77a0d5affccab08553231d3517c1d5e67204e0e887816fe67eaf302a09",
    "research/v3_5/stage3r/execution_manifest/development_runtime_input.31_cases.jsonl": "0be574af5ffd20fe147aa350fbf176904dfa98d27d5c0b3ea37b30f13c741fdc",
    "research/v3_5/stage3r_s1/identity_mapping/gold_segment_identity_projection.jsonl": "18d2a8b7cf5ae87659780d45f2e222a9ca9491f83402d20c79f5464959159dab",
}
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
SCORER_VERSION = "scorer_v4_evidence_identity_contract_v1"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"module import failed: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V1 = load_module(V1_PATH, "f1a_v1_runner_for_scorer_v4")


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return sha256(payload).hexdigest()


def canonicalizer() -> VideoIdentityCanonicalizer:
    mapping = VideoIdentityCanonicalizer.from_sqlite(V1.SNAPSHOT_DB)
    if mapping.source_sha256 != EXPECTED_MAPPING_HASH or len(mapping) != 144:
        raise RuntimeError("authoritative video mapping integrity mismatch")
    return mapping


def gold_hashes() -> dict[str, str]:
    return {name: digest(path) for name, path in V1.DEVELOPMENT_GOLD_PATHS.items()}


def development_input_hashes() -> dict[str, str]:
    seal = load_json(PREDICTION_SEAL)
    manifest = load_jsonl(PREDICTION_MANIFEST)
    current = {relative(P8 / row["path"]): digest(P8 / row["path"]) for row in manifest}
    mismatches = {
        row["path"]: {"expected": row["sha256"], "actual": digest(P8 / row["path"])}
        for row in manifest if digest(P8 / row["path"]) != row["sha256"]
    }
    trace_rows = [
        {"path": row["path"], "sha256": row["sha256"]}
        for row in manifest if row["path"].endswith(".trace.json")
    ]
    if mismatches or len(trace_rows) != 14 or stable_hash(trace_rows) != seal["trace_root_sha256"]:
        raise RuntimeError(f"development input freeze mismatch: {mismatches}")
    if digest(P8 / "blind_run/product_initial_baseline.input_manifest.json") != seal["input_manifest_sha256"]:
        raise RuntimeError("development input manifest mismatch")
    current[relative(PREDICTION_SEAL)] = digest(PREDICTION_SEAL)
    current[relative(PREDICTION_MANIFEST)] = digest(PREDICTION_MANIFEST)
    return current


def stress_input_paths() -> list[Path]:
    case_ids = V1.STRESS / "input_freeze/evidence_bearing_case_ids.json"
    paths = [V1.STRESS_SCORING, V1.STRESS_RUNTIME, V1.STRESS_BRIDGE, case_ids]
    paths.extend(
        V1.STRESS / f"execution/cases/{case_id}/search_candidate_set.json"
        for case_id in load_json(case_ids)["case_ids"]
    )
    return paths


def stress_input_hashes() -> dict[str, str]:
    hashes = {relative(path): digest(path) for path in stress_input_paths()}
    for path, expected in EXPECTED_STRESS_HASHES.items():
        if hashes[path] != expected:
            raise RuntimeError(f"stress input freeze mismatch: {path}")
    return hashes


def verify_authorities() -> dict[str, Any]:
    contract_seal = load_json(CONTRACT_SEAL)
    checks = {
        "contract_json_hash_matches_freeze_seal": digest(CONTRACT) == contract_seal["contract_hash"] == EXPECTED_CONTRACT_HASH,
        "contract_test_results_hash_matches_freeze_seal": digest(CONTRACT_RESULTS) == contract_seal["test_hashes"][relative(CONTRACT_RESULTS)] == EXPECTED_CONTRACT_RESULTS_HASH,
        "canonicalizer_and_matcher_source_hashes_match_freeze_seal": digest(BRIDGE) == contract_seal["matcher_source_hashes"][relative(BRIDGE)] == EXPECTED_BRIDGE_HASH,
        "builder_freeze_seal_valid": digest(BUILDER_SEAL) == contract_seal["builder_freeze_seal_hash"] == EXPECTED_BUILDER_SEAL_HASH,
        "acceptance_gates_unchanged": digest(ACCEPTANCE_GATES) == EXPECTED_ACCEPTANCE_GATE_HASH,
    }
    builder_seal = V1.assert_sealed()
    checks["builder_source_and_config_unchanged"] = bool(builder_seal)
    frozen_gold = {
        "retrieval": "b34188c269bf3a2410f8602fdb7d72908a96c822ac3b8f675d4f4c2b72b45679",
        "evidence": "b259a1b225a48558f5d1a6c4cb4909ea413e86116a1564b3fa724632ae88efc1",
        "sufficiency": "11196158746bb2c12e457fcb36b87a1621e79dca0b2f628a4870ca5ec6c5de92",
        "case_status": "9ba38a1f8cf636ebb9e80219cd85a41003743cb11f370a24d3946534378c6352",
    }
    checks["development_gold_hashes_unchanged"] = gold_hashes() == frozen_gold
    development_hashes = development_input_hashes()
    stress_hashes = stress_input_hashes()
    checks["development_inputs_unchanged"] = bool(development_hashes)
    checks["stress_inputs_unchanged"] = bool(stress_hashes)
    if not all(checks.values()):
        raise RuntimeError(f"blocked_frozen_asset_integrity_mismatch: {checks}")
    return {
        "checks": checks,
        "builder_seal": builder_seal,
        "development_gold_hashes": frozen_gold,
        "development_input_hashes": development_hashes,
        "stress_input_hashes": stress_hashes,
    }


def seal_path() -> Path:
    return OUT / "SCORER_V4_FREEZE_SEAL.json"


def freeze() -> dict[str, Any]:
    if seal_path().exists():
        raise RuntimeError("SCORER_V4_FREEZE_SEAL already exists")
    authority = verify_authorities()
    mapping = canonicalizer()
    manifest = {
        "schema_version": "v3.5-b-f1a-scorer-v4-manifest-v1",
        "scorer_version": SCORER_VERSION,
        "builder": "stage3b-adaptive-swap-w3.5-v1",
        "identity_contract": "EVIDENCE_IDENTITY_CONTRACT_V1",
        "projection": {"match": "coverage", "non_match": "no_coverage", "unverifiable": "no_coverage_and_separate_report"},
        "formal_run_limits": {"development": 1, "stress": 1},
        "query_specific_rules": 0,
        "score_targeting_rules": 0,
    }
    manifest_path = OUT / "scorer_v4_manifest.json"
    write_json(manifest_path, manifest)
    value = {
        "schema_version": "v3.5-b-f1a-scorer-v4-freeze-seal-v1",
        "scorer_version": SCORER_VERSION,
        "evidence_identity_contract_hash": digest(CONTRACT),
        "evidence_identity_contract_freeze_seal_hash": digest(CONTRACT_SEAL),
        "canonicalizer_and_matcher_source_hashes": {relative(BRIDGE): digest(BRIDGE)},
        "scorer_v4_runner_source_hashes": {relative(RUNNER): digest(RUNNER), relative(V1_PATH): digest(V1_PATH)},
        "projection_logic_source_hashes": {relative(PROJECTION): digest(PROJECTION)},
        "test_hashes": {relative(CONTRACT_TEST): digest(CONTRACT_TEST), relative(PROJECTION_TEST): digest(PROJECTION_TEST)},
        "builder_freeze_seal_hash": digest(BUILDER_SEAL),
        "builder_source_hashes": authority["builder_seal"]["source_hashes"],
        "builder_config_hashes": authority["builder_seal"]["config_hashes"],
        "development_gold_hashes": authority["development_gold_hashes"],
        "development_input_hashes": authority["development_input_hashes"],
        "stress_input_hashes": authority["stress_input_hashes"],
        "acceptance_gate_hashes": {relative(ACCEPTANCE_GATES): digest(ACCEPTANCE_GATES)},
        "manifest_hashes": {relative(manifest_path): digest(manifest_path)},
        "authoritative_mapping_source_hashes": {mapping.source: mapping.source_sha256},
        "freeze_constraints": {"contract_change": False, "matcher_change": False, "scorer_projection_change": False, "builder_change": False, "test_semantics_change": False},
    }
    write_json(seal_path(), value)
    return value


def assert_frozen() -> dict[str, Any]:
    seal = load_json(seal_path())
    sections = (
        "canonicalizer_and_matcher_source_hashes", "scorer_v4_runner_source_hashes",
        "projection_logic_source_hashes", "test_hashes", "builder_source_hashes",
        "builder_config_hashes", "development_input_hashes", "stress_input_hashes",
        "acceptance_gate_hashes", "manifest_hashes",
    )
    for section in sections:
        for path, expected in seal[section].items():
            if digest(ROOT / path) != expected:
                raise RuntimeError(f"scorer v4 frozen asset mismatch: {path}")
    if digest(CONTRACT) != seal["evidence_identity_contract_hash"]:
        raise RuntimeError("contract changed after scorer v4 freeze")
    if digest(CONTRACT_SEAL) != seal["evidence_identity_contract_freeze_seal_hash"]:
        raise RuntimeError("contract seal changed after scorer v4 freeze")
    if digest(BUILDER_SEAL) != seal["builder_freeze_seal_hash"]:
        raise RuntimeError("builder seal changed after scorer v4 freeze")
    if gold_hashes() != seal["development_gold_hashes"]:
        raise RuntimeError("Development Gold changed after scorer v4 freeze")
    mapping = canonicalizer()
    if seal["authoritative_mapping_source_hashes"] != {mapping.source: mapping.source_sha256}:
        raise RuntimeError("canonical mapping changed after scorer v4 freeze")
    return seal


def preflight() -> dict[str, Any]:
    seal = assert_frozen()
    authority = verify_authorities()
    result = {
        "schema_version": "v3.5-b-f1a-scorer-v4-preflight-v1",
        "status": "pass",
        **authority["checks"],
        "scorer_v4_hash_valid": True,
        "candidate_replay_started": False,
        "development_gold_opened_for_scoring": False,
        "score_seen": False,
        "formal_development_run_count": 0,
        "formal_stress_run_count": 0,
        "scorer_v4_freeze_seal_hash": digest(seal_path()),
        "scorer_v4_freeze_seal": relative(seal_path()),
        "builder_freeze_seal_hash": seal["builder_freeze_seal_hash"],
    }
    write_json(OUT / "scorer_v4_preflight.json", result)
    return result


def score_development() -> dict[str, Any]:
    output = OUT / "f1a_eval_v4_development_metrics.json"
    if output.exists():
        raise RuntimeError("Development Eval v4 already exists")
    preflight_value = load_json(OUT / "scorer_v4_preflight.json")
    if preflight_value.get("status") != "pass":
        raise RuntimeError("post-freeze preflight has not passed")
    seal = assert_frozen()
    mapping = canonicalizer()
    config = V1.builder_config()
    source_resolver = V1.resolver()
    runtime_rows = []
    for query_id in DEVELOPMENT_IDS:
        trace = V1.load(V1.P8 / f"blind_run/product_initial_baseline.traces/{query_id}.trace.json")
        candidates, bundle, latency_ms, swaps = V1.candidate_runtime(
            query_id, V1.query_text(trace), trace["search_candidate_set"], source_resolver, config,
        )
        runtime_rows.append({"query_id": query_id, "candidates": candidates, "bundle": bundle, "latency_ms": latency_ms, "swap": swaps})
    assert_frozen()
    layers = {name: {str(row["query_id"]): row for row in load_jsonl(path)} for name, path in V1.DEVELOPMENT_GOLD_PATHS.items()}
    rows = []
    for runtime in runtime_rows:
        query_id = runtime["query_id"]
        evidence = layers["evidence"][query_id]
        candidates = [candidate.as_dict() for candidate in runtime["candidates"].candidates]
        covered, projections = project_evidence(evidence, candidates, mapping)
        groups = complete_group_ids(evidence, covered)
        aspects = covered_aspect_ids(evidence, covered)
        required = required_span_ids(evidence)
        material = material_aspect_ids(evidence)
        unverifiable = unverifiable_candidate_count(candidates, mapping)
        contract_invalid = sum(candidate.normalization_status != "valid" or bool(candidate.validation_errors) for candidate in runtime["candidates"].candidates)
        rows.append({
            "query_id": query_id,
            "terminal_status": V1.runtime_terminal(runtime["candidates"])["status"],
            "candidate_count": len(candidates),
            "invalid_candidate_count": contract_invalid + unverifiable,
            "unverifiable_scoring_identity_count": unverifiable,
            "complete_group_hit": bool(groups),
            "covered_group_ids": groups,
            "covered_span_ids": sorted(covered),
            "covered_aspect_ids": aspects,
            "required_span_recall": len(covered & required) / len(required) if required else None,
            "required_aspect_coverage": len(set(aspects) & material) / len(material) if material else None,
            "eligible_for_builder_denominator": query_id != "PQS_V1_Q017",
            "eligible_for_primary_failure": query_id not in {"PQS_V1_Q014", "PQS_V1_Q017"},
            "latency_ms": runtime["latency_ms"],
            "swap_count": runtime["swap"]["swap_count"],
            "projection_status_counts": {
                status: sum(getattr(value, f"{status}_count") for value in projections.values())
                for status in ("match", "non_match", "unverifiable")
            },
            "aggregate_preserved_span_coverage_count": sum(value.aggregate_preserved_span_coverage for value in projections.values()),
        })
    eligible = [row for row in rows if row["eligible_for_builder_denominator"]]
    metrics = {
        "schema_version": "v3.5-b-f1a-development-eval-v4-v1",
        "scorer_version": SCORER_VERSION,
        "builder_version": config.config_id,
        "scorer_v4_freeze_seal_hash": digest(seal_path()),
        "builder_freeze_seal_hash": seal["builder_freeze_seal_hash"],
        "development_gold_hashes": gold_hashes(),
        "complete_development_score": True,
        "complete_group_coverage": {"numerator": sum(row["complete_group_hit"] for row in eligible), "denominator": len(eligible)},
        "builder_primary_failures": sum(not row["complete_group_hit"] for row in rows if row["eligible_for_primary_failure"]),
        "required_span_recall": mean(row["required_span_recall"] for row in eligible if row["required_span_recall"] is not None),
        "required_aspect_coverage": mean(row["required_aspect_coverage"] for row in eligible if row["required_aspect_coverage"] is not None),
        "existing_six_regressions": sorted(row["query_id"] for row in rows if row["query_id"] in EXISTING_SIX and not row["complete_group_hit"]),
        "maximum_candidate_count_per_query": max(row["candidate_count"] for row in rows),
        "candidate_count_total": sum(row["candidate_count"] for row in rows),
        "invalid_candidate_count": sum(row["invalid_candidate_count"] for row in rows),
        "unverifiable_scoring_identity_count": sum(row["unverifiable_scoring_identity_count"] for row in rows),
        "canonical_match_count": sum(row["projection_status_counts"]["match"] for row in rows),
        "canonical_non_match_count": sum(row["projection_status_counts"]["non_match"] for row in rows),
        "canonical_unverifiable_comparison_count": sum(row["projection_status_counts"]["unverifiable"] for row in rows),
        "maximum_swap_count_per_query": max(row["swap_count"] for row in rows),
        "forced_swaps": False,
        "formal_development_run_count": 1,
    }
    metrics["complete_group_coverage"]["rate"] = metrics["complete_group_coverage"]["numerator"] / metrics["complete_group_coverage"]["denominator"]
    write_jsonl(OUT / "f1a_eval_v4_development_per_query.jsonl", rows)
    write_json(output, metrics)
    return metrics


def score_stress() -> dict[str, Any]:
    output = OUT / "f1a_eval_v4_stress_metrics.json"
    if output.exists():
        raise RuntimeError("Stress Eval v4 already exists")
    development = load_json(OUT / "f1a_eval_v4_development_metrics.json")
    if development.get("formal_development_run_count") != 1:
        raise RuntimeError("Stress Eval v4 requires exactly one Development Eval v4")
    assert_frozen()
    mapping = canonicalizer()
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
        candidate_values = [candidate.as_dict() for candidate in candidates.candidates]
        completed = []
        match_count = non_match_count = unverifiable_comparisons = 0
        for group in groups:
            projections = [project_gold_span(span, candidate_values, mapping) for span in group.get("required_spans", [])]
            if projections and all(value.covered for value in projections):
                completed.append(str(group["group_id"]))
            match_count += sum(value.match_count for value in projections)
            non_match_count += sum(value.non_match_count for value in projections)
            unverifiable_comparisons += sum(value.unverifiable_count for value in projections)
        unverifiable = unverifiable_candidate_count(candidate_values, mapping)
        contract_invalid = sum(candidate.normalization_status != "valid" or bool(candidate.validation_errors) for candidate in candidates.candidates)
        rows.append({
            "case_id": case_id, "complete_group_hit": bool(completed), "covered_group_ids": completed,
            "candidate_count": len(candidate_values), "invalid_candidate_count": contract_invalid + unverifiable,
            "unverifiable_scoring_identity_count": unverifiable, "canonical_match_count": match_count,
            "canonical_non_match_count": non_match_count, "canonical_unverifiable_comparison_count": unverifiable_comparisons,
            "latency_ms": latency_ms, "swap_count": swaps["swap_count"],
        })
    result = {
        "schema_version": "v3.5-b-f1a-stress-eval-v4-v1", "scorer_version": SCORER_VERSION,
        "builder_version": config.config_id,
        "complete_group_coverage": {"numerator": sum(row["complete_group_hit"] for row in rows), "denominator": len(rows)},
        "maximum_candidate_count_per_query": max(row["candidate_count"] for row in rows),
        "candidate_count_total": sum(row["candidate_count"] for row in rows),
        "invalid_candidate_count": sum(row["invalid_candidate_count"] for row in rows),
        "unverifiable_scoring_identity_count": sum(row["unverifiable_scoring_identity_count"] for row in rows),
        "canonical_match_count": sum(row["canonical_match_count"] for row in rows),
        "canonical_non_match_count": sum(row["canonical_non_match_count"] for row in rows),
        "canonical_unverifiable_comparison_count": sum(row["canonical_unverifiable_comparison_count"] for row in rows),
        "maximum_swap_count_per_query": max(row["swap_count"] for row in rows), "forced_swaps": False,
        "formal_stress_run_count": 1, "per_case": rows,
    }
    result["complete_group_coverage"]["rate"] = result["complete_group_coverage"]["numerator"] / result["complete_group_coverage"]["denominator"]
    write_json(output, result)
    return result


def closeout() -> dict[str, Any]:
    output = OUT / "f1a_eval_v4_final_closeout.json"
    if output.exists():
        raise RuntimeError("Eval v4 closeout already exists")
    assert_frozen()
    development = load_json(OUT / "f1a_eval_v4_development_metrics.json")
    stress = load_json(OUT / "f1a_eval_v4_stress_metrics.json")
    systemic_zero = (
        development["complete_group_coverage"]["numerator"] == 0
        and stress["complete_group_coverage"]["numerator"] == 0
        and development["canonical_match_count"] == 0
        and stress["canonical_match_count"] == 0
    )
    validity = {
        "contract_hash_valid": True, "matcher_hash_valid": True, "scorer_v4_hash_valid": True,
        "builder_hash_valid": True, "gold_hash_valid": True, "input_hashes_valid": True,
        "formal_run_counts_exactly_one_each": development["formal_development_run_count"] == 1 and stress["formal_stress_run_count"] == 1,
        "systemic_all_zero_due_to_identity_or_projection_defect": systemic_zero,
        "new_known_scoring_infrastructure_defect": False,
    }
    valid = all(value for key, value in validity.items() if key not in {"systemic_all_zero_due_to_identity_or_projection_defect", "new_known_scoring_infrastructure_defect"}) and not systemic_zero
    gates = {
        "complete_group_coverage_minimum_8_of_13": development["complete_group_coverage"]["numerator"] >= 8,
        "builder_primary_failures_maximum_4": development["builder_primary_failures"] <= 4,
        "required_span_recall_minimum_69_23_percent": development["required_span_recall"] >= 9 / 13,
        "required_aspect_coverage_minimum_69_23_percent": development["required_aspect_coverage"] >= 9 / 13,
        "existing_six_builder_hits_regressions_allowed_0": not development["existing_six_regressions"],
        "invalid_identity_source_timeline_maximum_0": development["invalid_candidate_count"] == 0,
        "candidate_cap_32": development["maximum_candidate_count_per_query"] <= 32 and stress["maximum_candidate_count_per_query"] <= 32,
        "maximum_swaps_per_query_4": development["maximum_swap_count_per_query"] <= 4 and stress["maximum_swap_count_per_query"] <= 4,
        "forced_swaps_false": development["forced_swaps"] is False and stress["forced_swaps"] is False,
        "stress_complete_group_coverage_minimum_11_of_20": stress["complete_group_coverage"]["numerator"] >= 11,
    }
    if valid and all(gates.values()):
        outcome, final_builder, algorithm_result, closure = "accepted_new_builder", "stage3b-adaptive-swap-w3.5-v1", "valid_pass", "formally_closed_pass"
    elif valid:
        outcome, final_builder, algorithm_result, closure = "rejected_keep_existing_builder", "stage3b-acronym-w3.5-v1", "valid_failure", "formally_closed_fail"
    else:
        outcome, final_builder, algorithm_result, closure = "no_promotion_due_to_unresolved_evaluation_infrastructure", "stage3b-acronym-w3.5-v1", "unresolved", "closed_without_valid_algorithm_verdict"
    paths = [
        OUT / "scorer_v4_manifest.json", seal_path(), OUT / "scorer_v4_preflight.json",
        OUT / "f1a_eval_v4_development_per_query.jsonl", OUT / "f1a_eval_v4_development_metrics.json",
        OUT / "f1a_eval_v4_stress_metrics.json",
    ]
    value = {
        "schema_version": "v3.5-b-f1a-scorer-v4-final-closeout-v1",
        "history": {
            "eval_v1": "invalid_due_to_identity_bridge_defect",
            "eval_v2": "invalid_due_to_BVID_numeric_identity_defect",
            "eval_v3": "invalid_due_to_source_type_identity_defect",
        },
        "eval_v4_validity": valid, "validity_checks": validity, "original_acceptance_gates": gates,
        "outcome": outcome, "final_builder": final_builder, "new_builder_algorithm_result": algorithm_result,
        "F1A_status": closure, "formal_run_counts": {"development": 1, "stress": 1},
        "change_status": {"builder": False, "contract": False, "matcher": False, "scorer_projection_after_freeze": False, "gold": False, "stress_inputs": False, "acceptance_gates": False},
        "F1B_status": "not_started", "Stage4_status": "not_started", "P10_status": "not_started",
        "session_can_be_closed": True,
        "output_hashes": {relative(path): digest(path) for path in paths},
    }
    write_json(output, value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("freeze", "preflight", "development", "stress", "closeout"))
    args = parser.parse_args()
    action = {"freeze": freeze, "preflight": preflight, "development": score_development, "stress": score_stress, "closeout": closeout}[args.phase]
    print(json.dumps(action(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
