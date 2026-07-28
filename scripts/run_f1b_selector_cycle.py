from __future__ import annotations

import argparse
from dataclasses import fields
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from statistics import mean
import sys
import time
from typing import Any, Mapping

from shiliu.evidence.stage3a import (
    EvidenceCandidate,
    EvidenceCandidateSet,
    interval_union_duration,
    select_greedy_marginal_bundle,
    validate_bundle,
)
from shiliu.eval_v3_5.scoring_identity_bridge import (
    complete_group_ids,
    covered_aspect_ids,
    material_aspect_ids,
    required_span_ids,
)


ROOT = Path(__file__).resolve().parents[1]
P8 = ROOT / "research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3"
STRESS = ROOT / "research/v3_5/stage3r_qc/track_a_auto_refresh"
CYCLE = ROOT / "research/v3_5/product_query_set_v1/f1b_selector_major_cycle_1"
F1A = ROOT / "research/v3_5/product_query_set_v1/f1a_candidate_builder_major_cycle_1"
GATE = ROOT / "F1B_GATE_FREEZE.json"
SEAL = ROOT / "SELECTOR_V2_FREEZE_SEAL.json"
PREFLIGHT = CYCLE / "f1b_post_freeze_preflight.json"
PRODUCT_ROWS = ROOT / "f1b_product_after.per_case.jsonl"
PRODUCT_METRICS = ROOT / "f1b_product_after.metrics.json"
STRESS_METRICS = ROOT / "f1b_stress_after.metrics.json"
PRODUCT_IDS = (
    "PQS_V1_Q003", "PQS_V1_Q004", "PQS_V1_Q005", "PQS_V1_Q006",
    "PQS_V1_Q007", "PQS_V1_Q008", "PQS_V1_Q011", "PQS_V1_Q012",
    "PQS_V1_Q013", "PQS_V1_Q014", "PQS_V1_Q015", "PQS_V1_Q017",
    "PQS_V1_Q018", "PQS_V1_Q019",
)
BUILDER_COMPLETE = {
    "PQS_V1_Q006", "PQS_V1_Q007", "PQS_V1_Q011",
    "PQS_V1_Q012", "PQS_V1_Q013", "PQS_V1_Q019",
}
PREVIOUS_MISSES = BUILDER_COMPLETE - {"PQS_V1_Q006"}


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"module import failed: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(F1A))
SCORER = load_module(F1A / "run_f1a_scorer_v4.py", "f1b_scorer_v4")
PROJECTION = load_module(F1A / "scorer_v4_projection.py", "f1b_projection_v4")
V1 = SCORER.V1


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True)
            for row in rows
        ) + "\n",
        encoding="utf-8",
    )


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def stable_root(paths: list[Path]) -> str:
    rows = [
        {"path": relative(path), "sha256": digest(path)}
        for path in sorted(paths)
    ]
    payload = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()
    return sha256(payload).hexdigest()


def candidate_set_from_dict(value: Mapping[str, Any]) -> EvidenceCandidateSet:
    allowed = {field.name for field in fields(EvidenceCandidate)}
    candidates = tuple(
        EvidenceCandidate(**{
            key: (
                tuple(item) if key in {
                    "segment_ids", "original_ordinals", "parent_chunk_ids",
                    "search_candidate_ids", "candidate_methods",
                    "related_candidate_ids", "validation_errors",
                } else item
            )
            for key, item in candidate.items() if key in allowed
        })
        for candidate in value.get("candidates", [])
    )
    return EvidenceCandidateSet(
        query_id=str(value["query_id"]),
        original_query=str(value["original_query"]),
        candidates=candidates,
        evaluation_track=str(value["evaluation_track"]),
        end_to_end_claim_eligible=bool(value["end_to_end_claim_eligible"]),
        trace=dict(value.get("trace", {})),
        normalization_status=str(value.get("normalization_status", "valid")),
        validation_errors=tuple(value.get("validation_errors", [])),
        failure_category=value.get("failure_category"),
    )


def selected_candidate_dicts(
    candidate_set: EvidenceCandidateSet, candidate_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    by_id = {
        candidate.candidate_id: candidate
        for candidate in candidate_set.candidates
    }
    return [by_id[candidate_id].as_dict() for candidate_id in candidate_ids]


def compactness(bundle: Any) -> float | None:
    if bundle is None:
        return None
    selected_duration = sum(
        float(span["end_time"]) - float(span["start_time"])
        for span in bundle.normalized_spans
    )
    return bundle.union_duration / selected_duration if selected_duration else None


def frozen_paths() -> dict[str, list[Path]]:
    product_traces = sorted(
        (P8 / "blind_run/product_initial_baseline.traces").glob("*.json"),
    )
    stress_cases = sorted(
        (STRESS / "execution/cases").glob("*/candidate_set.json"),
    )
    stress_builder_inputs = sorted(
        (STRESS / "execution/cases").glob("*/candidate_builder_input.json"),
    )
    return {
        "development_gold": sorted(V1.DEVELOPMENT_GOLD.glob("*.jsonl")),
        "product_inputs": [
            P8 / "blind_run/product_initial_baseline.predictions.jsonl",
            P8 / "blind_run/product_initial_baseline.input_manifest.json",
            *product_traces,
        ],
        "stress_inputs": [
            STRESS / "input_freeze/evidence_bearing_case_ids.json",
            *stress_cases,
            *stress_builder_inputs,
            V1.STRESS_SCORING,
            V1.STRESS_RUNTIME,
            V1.STRESS_BRIDGE,
        ],
        "identity": [
            F1A / "EVIDENCE_IDENTITY_CONTRACT_V1.json",
            F1A / "EVIDENCE_IDENTITY_CONTRACT_V1_FREEZE_SEAL.json",
            ROOT / "src/shiliu/evidence/contracts.py",
            ROOT / "src/shiliu/eval_v3_5/scoring_identity_bridge.py",
        ],
        "projection": [
            F1A / "scorer_v4_projection.py",
            F1A / "scorer_v4_final_eval/SCORER_V4_FREEZE_SEAL.json",
        ],
    }


def assert_frozen() -> dict[str, Any]:
    gate = load_json(GATE)
    seal = load_json(SEAL)
    paths = frozen_paths()
    expected_roots = {
        "development_gold": gate["frozen_asset_hashes"]["Development_Gold_hashes"]["root_sha256"],
        "product_inputs": gate["frozen_asset_hashes"]["Product_input_hashes"]["root_sha256"],
        "stress_inputs": gate["frozen_asset_hashes"]["Stress_input_hashes"]["root_sha256"],
        "identity": gate["frozen_asset_hashes"]["Evidence_Identity_Contract_V1_hashes"]["root_sha256"],
        "projection": gate["frozen_asset_hashes"]["projection_contract_hashes"]["root_sha256"],
    }
    actual_roots = {name: stable_root(value) for name, value in paths.items()}
    if actual_roots != expected_roots:
        raise RuntimeError({
            "frozen_asset_root_mismatch": {
                name: {"expected": expected_roots[name], "actual": actual_roots[name]}
                for name in expected_roots
                if expected_roots[name] != actual_roots[name]
            }
        })
    for section in (
        "selector_source_hashes", "selector_config_hashes", "test_hashes",
        "projection_contract_hashes",
    ):
        for path, expected in seal[section].items():
            if digest(ROOT / path) != expected:
                raise RuntimeError(f"selector seal mismatch: {path}")
    if digest(GATE) != seal["F1B_GATE_FREEZE_hash"]:
        raise RuntimeError("F1B Gate Freeze changed after selector seal")
    return seal


def preflight() -> dict[str, Any]:
    if PREFLIGHT.exists():
        raise RuntimeError("F1B post-freeze preflight already exists")
    seal = assert_frozen()
    result = {
        "schema_version": "v3.5-b-f1b-post-freeze-preflight-v1",
        "status": "pass",
        "Gate_Freeze_hash_valid": True,
        "Selector_v2_Seal_valid": True,
        "formal_builder_unchanged": True,
        "identity_contract_unchanged": True,
        "Gold_and_inputs_unchanged": True,
        "bundle_budget_unchanged": True,
        "bundle_budget": 6,
        "selector_version": "v3.5-deterministic-fine-selector-v2",
        "candidate_replay_started": False,
        "Development_Gold_opened_for_after_scoring": False,
        "formal_Product_After_run_count": 0,
        "formal_Stress_After_run_count": 0,
        "Frozen_Evaluation_accessed": False,
        "selector_v2_seal_sha256": digest(SEAL),
        "seal_schema_version": seal["schema_version"],
    }
    write_json(PREFLIGHT, result)
    return result


def product() -> dict[str, Any]:
    if PRODUCT_METRICS.exists() or PRODUCT_ROWS.exists():
        raise RuntimeError("formal Product After already exists")
    if load_json(PREFLIGHT).get("status") != "pass":
        raise RuntimeError("post-freeze preflight must pass")
    assert_frozen()
    mapping = SCORER.canonicalizer()
    layers = {
        name: {
            str(row["query_id"]): row for row in load_jsonl(path)
        }
        for name, path in V1.DEVELOPMENT_GOLD_PATHS.items()
    }
    rows: list[dict[str, Any]] = []
    for query_id in PRODUCT_IDS:
        trace = load_json(
            P8 / f"blind_run/product_initial_baseline.traces/{query_id}.trace.json",
        )
        candidate_set = candidate_set_from_dict(trace["evidence_candidate_set"])
        started = time.perf_counter()
        bundle = select_greedy_marginal_bundle(
            candidate_set.original_query, candidate_set,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        if bundle is not None:
            validate_bundle(bundle, candidate_set)
            selected = selected_candidate_dicts(
                candidate_set, bundle.candidate_ids,
            )
        else:
            selected = []
        evidence = layers["evidence"][query_id]
        selected_covered, selected_projections = PROJECTION.project_evidence(
            evidence, selected, mapping,
        )
        candidate_values = [
            candidate.as_dict() for candidate in candidate_set.candidates
        ]
        builder_covered, _ = PROJECTION.project_evidence(
            evidence, candidate_values, mapping,
        )
        selected_groups = complete_group_ids(evidence, selected_covered)
        selected_aspects = set(covered_aspect_ids(evidence, selected_covered))
        builder_aspects = set(covered_aspect_ids(evidence, builder_covered))
        required = required_span_ids(evidence)
        material = material_aspect_ids(evidence)
        invalid_runtime = sum(
            candidate.normalization_status != "valid"
            or bool(candidate.validation_errors)
            for candidate in candidate_set.candidates
        )
        invalid_selected = PROJECTION.unverifiable_candidate_count(
            selected, mapping,
        )
        rows.append({
            "query_id": query_id,
            "selector_version": "v3.5-deterministic-fine-selector-v2",
            "selected_bundle_id": bundle.bundle_id if bundle else None,
            "selected_candidate_ids": list(bundle.candidate_ids) if bundle else [],
            "selected_candidate_count": len(bundle.candidate_ids) if bundle else 0,
            "selected_video_id": bundle.video_id if bundle else None,
            "bundle_hit": bool(selected_groups),
            "covered_group_ids": selected_groups,
            "selected_covered_span_ids": sorted(selected_covered),
            "builder_available_span_ids": sorted(builder_covered),
            "selected_covered_aspect_ids": sorted(selected_aspects),
            "builder_available_aspect_ids": sorted(builder_aspects),
            "required_span_count": len(required),
            "material_aspect_count": len(material),
            "required_span_recall": (
                len(selected_covered & required) / len(required)
                if required else None
            ),
            "required_aspect_coverage": (
                len(selected_aspects & material) / len(material)
                if material else None
            ),
            "compactness": compactness(bundle),
            "selector_latency_ms": latency_ms,
            "invalid_identity_or_timeline": invalid_runtime + invalid_selected,
            "projection_unverifiable_comparison_count": sum(
                value.unverifiable_count
                for value in selected_projections.values()
            ),
        })
    six = [row for row in rows if row["query_id"] in BUILDER_COMPLETE]
    compact = [row["compactness"] for row in rows if row["compactness"] is not None]
    span_numerator = sum(len(row["selected_covered_span_ids"]) for row in six)
    span_denominator = sum(len(row["builder_available_span_ids"]) for row in six)
    aspect_numerator = sum(len(row["selected_covered_aspect_ids"]) for row in six)
    aspect_denominator = sum(len(row["builder_available_aspect_ids"]) for row in six)
    result = {
        "schema_version": "v3.5-b-f1b-product-after-v1",
        "formal_Product_After_run_count": 1,
        "query_count": len(rows),
        "builder_version": "stage3b-acronym-w3.5-v1",
        "selector_version": "v3.5-deterministic-fine-selector-v2",
        "bundle_budget": 6,
        "selector_hits_on_builder_complete_cases": {
            "numerator": sum(row["bundle_hit"] for row in six),
            "denominator": len(six),
        },
        "recovered_previous_misses": {
            "numerator": sum(
                row["bundle_hit"]
                for row in rows if row["query_id"] in PREVIOUS_MISSES
            ),
            "denominator": len(PREVIOUS_MISSES),
        },
        "Q006_regressions": sum(
            not row["bundle_hit"]
            for row in rows if row["query_id"] == "PQS_V1_Q006"
        ),
        "selector_to_builder_span_capture_ratio": (
            span_numerator / span_denominator if span_denominator else None
        ),
        "selector_to_builder_span_capture": {
            "numerator": span_numerator, "denominator": span_denominator,
        },
        "selector_to_builder_aspect_capture_ratio": (
            aspect_numerator / aspect_denominator if aspect_denominator else None
        ),
        "selector_to_builder_aspect_capture": {
            "numerator": aspect_numerator, "denominator": aspect_denominator,
        },
        "compactness_percent": mean(compact) * 100.0,
        "mean_selector_latency_ms": mean(
            row["selector_latency_ms"] for row in rows
        ),
        "maximum_selected_candidate_count": max(
            row["selected_candidate_count"] for row in rows
        ),
        "invalid_identity_or_timeline": sum(
            row["invalid_identity_or_timeline"] for row in rows
        ),
        "Frozen_Evaluation_accessed": False,
    }
    write_jsonl(PRODUCT_ROWS, rows)
    write_json(PRODUCT_METRICS, result)
    return result


def stress() -> dict[str, Any]:
    if STRESS_METRICS.exists():
        raise RuntimeError("formal Stress After already exists")
    if load_json(PRODUCT_METRICS).get("formal_Product_After_run_count") != 1:
        raise RuntimeError("Stress After requires exactly one Product After")
    assert_frozen()
    mapping = SCORER.canonicalizer()
    gold = {
        row["case_id"]: row for row in load_jsonl(V1.STRESS_SCORING)
    }
    bridge = {
        (row["case_id"], row["gold_segment_id"]): row["physical_segment_id"]
        for row in load_jsonl(V1.STRESS_BRIDGE)
    }
    rows: list[dict[str, Any]] = []
    case_ids = load_json(
        STRESS / "input_freeze/evidence_bearing_case_ids.json",
    )["case_ids"]
    for case_id in case_ids:
        root = STRESS / f"execution/cases/{case_id}"
        candidate_set = candidate_set_from_dict(load_json(root / "candidate_set.json"))
        query = str(load_json(root / "candidate_builder_input.json")["query"])
        started = time.perf_counter()
        bundle = select_greedy_marginal_bundle(query, candidate_set)
        latency_ms = (time.perf_counter() - started) * 1000.0
        if bundle is not None:
            validate_bundle(bundle, candidate_set)
            selected = selected_candidate_dicts(candidate_set, bundle.candidate_ids)
        else:
            selected = []
        groups = V1._physical_groups(
            case_id, gold[case_id]["evidence_groups"], bridge,
        )
        covered_span_ids: set[str] = set()
        covered_aspects: set[str] = set()
        required_span_ids_all: set[str] = set()
        required_aspects_all = {
            str(value["aspect_id"]) for value in gold[case_id].get(
                "required_aspects", [],
            )
        }
        completed_groups: list[str] = []
        unverifiable_comparisons = 0
        for group in groups:
            group_covered = True
            for span in group.get("required_spans", []):
                span_id = str(span["span_id"])
                required_span_ids_all.add(span_id)
                projection = PROJECTION.project_gold_span(span, selected, mapping)
                unverifiable_comparisons += projection.unverifiable_count
                if projection.covered:
                    covered_span_ids.add(span_id)
                    covered_aspects |= {
                        str(value)
                        for value in span.get("required_aspect_ids", [])
                    }
                else:
                    group_covered = False
            if group_covered and group.get("required_spans"):
                completed_groups.append(str(group["group_id"]))
        invalid_runtime = sum(
            candidate.normalization_status != "valid"
            or bool(candidate.validation_errors)
            for candidate in candidate_set.candidates
        )
        invalid_selected = PROJECTION.unverifiable_candidate_count(
            selected, mapping,
        )
        rows.append({
            "case_id": case_id,
            "bundle_hit": bool(completed_groups),
            "covered_group_ids": completed_groups,
            "selected_candidate_count": len(bundle.candidate_ids) if bundle else 0,
            "covered_span_count": len(covered_span_ids),
            "required_span_count": len(required_span_ids_all),
            "covered_aspect_count": len(covered_aspects & required_aspects_all),
            "required_aspect_count": len(required_aspects_all),
            "compactness": compactness(bundle),
            "selector_latency_ms": latency_ms,
            "invalid_identity_or_timeline": invalid_runtime + invalid_selected,
            "projection_unverifiable_comparison_count": unverifiable_comparisons,
        })
    compact = [row["compactness"] for row in rows if row["compactness"] is not None]
    span_denominator = sum(row["required_span_count"] for row in rows)
    aspect_denominator = sum(row["required_aspect_count"] for row in rows)
    result = {
        "schema_version": "v3.5-b-f1b-stress-after-v1",
        "formal_Stress_After_run_count": 1,
        "case_count": len(rows),
        "bundle_hits": {
            "numerator": sum(row["bundle_hit"] for row in rows),
            "denominator": len(rows),
        },
        "required_span_recall": (
            sum(row["covered_span_count"] for row in rows) / span_denominator
            if span_denominator else None
        ),
        "required_aspect_coverage": (
            sum(row["covered_aspect_count"] for row in rows) / aspect_denominator
            if aspect_denominator else None
        ),
        "compactness_percent": mean(compact) * 100.0,
        "mean_selector_latency_ms": mean(
            row["selector_latency_ms"] for row in rows
        ),
        "maximum_selected_candidate_count": max(
            row["selected_candidate_count"] for row in rows
        ),
        "invalid_identity_or_timeline": sum(
            row["invalid_identity_or_timeline"] for row in rows
        ),
        "per_case": rows,
        "Frozen_Evaluation_accessed": False,
    }
    write_json(STRESS_METRICS, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("preflight", "product", "stress"))
    args = parser.parse_args()
    action = {
        "preflight": preflight,
        "product": product,
        "stress": stress,
    }[args.phase]
    print(json.dumps(action(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
