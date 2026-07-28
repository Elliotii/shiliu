from __future__ import annotations

import argparse
from dataclasses import fields
from hashlib import sha256
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from shiliu.evidence.stage3a import EvidenceBundle, EvidenceCandidate, EvidenceCandidateSet
from shiliu.evidence.stage4 import (
    FINAL_CANDIDATE_BUILDER_VERSION,
    MECHANICAL_GATE_POLICY_VERSION,
    REASON_ACTION,
    SOURCE_UNVERIFIABLE_REASONS,
    EvidenceResolutionState,
    MechanicalGateDecision,
    MechanicalGatePolicy,
    SufficiencyDecision,
    SufficiencyRequest,
    apply_mechanical_sufficiency_gate,
    stable_id,
)


ROOT = Path(__file__).resolve().parents[1]
P8 = ROOT / "research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/blind_run"
STRESS = ROOT / "research/v3_5/stage3r_qc/track_a_auto_refresh/execution/cases"
F1A = ROOT / "research/v3_5/product_query_set_v1/f1a_candidate_builder_major_cycle_1"
F1B_GATE = ROOT / "F1B_GATE_FREEZE.json"
IDENTITY_SEAL = F1A / "EVIDENCE_IDENTITY_CONTRACT_V1_FREEZE_SEAL.json"
BEFORE = ROOT / "stage4a_r_before_revalidation.json"
FREEZE = ROOT / "STAGE4A_R_MECHANICAL_GATE_FREEZE.json"
PREFLIGHT = ROOT / "stage4a_r_post_freeze_preflight.json"
PRODUCT_ROWS = ROOT / "stage4a_r_product.per_case.jsonl"
PRODUCT_METRICS = ROOT / "stage4a_r_product.metrics.json"
STRESS_METRICS = ROOT / "stage4a_r_stress.metrics.json"
PRODUCT_IDS = (
    "PQS_V1_Q003", "PQS_V1_Q004", "PQS_V1_Q005", "PQS_V1_Q006",
    "PQS_V1_Q007", "PQS_V1_Q008", "PQS_V1_Q011", "PQS_V1_Q012",
    "PQS_V1_Q013", "PQS_V1_Q014", "PQS_V1_Q015", "PQS_V1_Q017",
    "PQS_V1_Q018", "PQS_V1_Q019",
)
GATE_FILES = (
    ROOT / "src/shiliu/evidence/stage4.py",
    ROOT / "src/shiliu/eval_v3_5/stage4a.py",
)
GATE_CONFIG_FILES = (
    ROOT / "research/v3_5/stage4a/mechanical_gate_policy.json",
    ROOT / "research/v3_5/stage4a/operational_reason_policy.json",
    ROOT / "research/v3_5/stage4a/action_family_policy.json",
)
CONTRACT_FILES = (
    ROOT / "research/v3_5/stage4a/mechanical_gate_contract.json",
    ROOT / "research/v3_5/stage4a/sufficiency_request_contract.json",
    ROOT / "research/v3_5/stage4a/sufficiency_decision_contract.json",
)
TEST_FILES = (
    ROOT / "tests/test_v3_5_stage4a_gate.py",
    ROOT / "tests/test_v3_5_stage4a_eval.py",
    ROOT / "tests/test_stage4a_r_mechanical_gate.py",
    ROOT / "stage4a_r_gold_free_test_results.json",
)


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def file_hashes(paths: Sequence[Path]) -> dict[str, str]:
    return {relative(path): digest(path) for path in sorted(paths)}


def candidate_set_from_dict(value: Mapping[str, Any]) -> EvidenceCandidateSet:
    allowed = {field.name for field in fields(EvidenceCandidate)}
    tuple_fields = {
        "segment_ids", "original_ordinals", "parent_chunk_ids", "search_candidate_ids",
        "candidate_methods", "related_candidate_ids", "validation_errors",
    }
    candidates = tuple(
        EvidenceCandidate(**{
            key: tuple(item) if key in tuple_fields else item
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
        trace=dict(value.get("trace") or {}),
        normalization_status=str(value.get("normalization_status", "valid")),
        validation_errors=tuple(value.get("validation_errors", [])),
        failure_category=value.get("failure_category"),
    )


def bundle_from_dict(value: Mapping[str, Any] | None) -> EvidenceBundle | None:
    if value is None:
        return None
    allowed = {field.name for field in fields(EvidenceBundle)}
    tuple_fields = {
        "source_artifact_ids", "source_versions", "timeline_run_ids", "candidate_ids",
        "normalized_spans", "source_texts", "validation_errors",
    }
    return EvidenceBundle(**{
        key: tuple(item) if key in tuple_fields else item
        for key, item in value.items() if key in allowed
    })


def stress_request(
    case_id: str,
    candidate_set: EvidenceCandidateSet,
    bundle: EvidenceBundle | None,
) -> tuple[SufficiencyRequest, EvidenceResolutionState]:
    candidate_set_id = stable_id("candidate_set_", candidate_set.as_dict())
    reason = candidate_set.failure_category
    status = "resolved" if bundle is not None and reason is None else "failed"
    trace_id = stable_id("stage4a_r_trace_", {
        "case_id": case_id,
        "candidate_set_id": candidate_set_id,
        "bundle_id": bundle.bundle_id if bundle else None,
    })
    request = SufficiencyRequest(
        request_id=stable_id("request_", {"case_id": case_id, "trace_id": trace_id}),
        query_id=candidate_set.query_id,
        original_query=candidate_set.original_query,
        evaluation_track=candidate_set.evaluation_track,
        end_to_end_claim_eligible=candidate_set.end_to_end_claim_eligible,
        search_candidate_set_id=f"stress_search_{case_id}",
        evidence_candidate_set_id=candidate_set_id,
        evidence_bundle_id=bundle.bundle_id if bundle else None,
        evidence_resolution_status=status,
        failure_attribution=reason,
        candidate_builder_version=FINAL_CANDIDATE_BUILDER_VERSION,
        selector_version="v3.5-deterministic-fine-selector-v1",
        source_states=tuple(sorted({candidate.normalization_status for candidate in candidate_set.candidates})),
        source_languages=tuple(sorted({candidate.source_language for candidate in candidate_set.candidates})),
        trace_id=trace_id,
    )
    state = EvidenceResolutionState(
        status=status,
        operational_reason_code=reason,
        search_candidate_set_id=request.search_candidate_set_id,
        evidence_candidate_set_id=candidate_set_id,
        evidence_bundle_id=bundle.bundle_id if bundle else None,
        available_evidence_candidate_ids=tuple(candidate.candidate_id for candidate in candidate_set.candidates),
        evidence_ids_raw_derived=bool(candidate_set.candidates),
        source_integrity_valid=candidate_set.normalization_status == "valid" and not candidate_set.validation_errors,
        validation_errors=candidate_set.validation_errors,
    )
    return request, state


def _status(gate: Any) -> str:
    if gate.gate_outcome == "judge_eligible":
        return "judge_eligible"
    if gate.gate_outcome in {"source_unverifiable", "invalid"}:
        return str(gate.gate_outcome)
    return "source_unverifiable"


def mechanical_errors(
    request: SufficiencyRequest,
    state: EvidenceResolutionState,
    bundle: EvidenceBundle | None,
    candidate_set: EvidenceCandidateSet | None,
) -> list[str]:
    if bundle is None:
        return []
    errors: list[str] = []
    candidate_ids = list(bundle.candidate_ids)
    if not candidate_ids or any(not value for value in candidate_ids):
        errors.append("empty_evidence_ids")
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("duplicate_or_conflicting_evidence_id")
    if not bundle.source_artifact_ids or any(not value for value in bundle.source_artifact_ids):
        errors.append("missing_source_artifact_id")
    if not bundle.source_versions or any(not value for value in bundle.source_versions):
        errors.append("missing_source_version")
    if not bundle.timeline_run_ids or any(not value for value in bundle.timeline_run_ids):
        errors.append("missing_timeline_run_id")
    if not isinstance(bundle.video_id, int) or isinstance(bundle.video_id, bool) or bundle.video_id < 0:
        errors.append("invalid_canonical_video_identity")
    if not bundle.normalized_spans:
        errors.append("missing_evidence_span")
    if len(bundle.source_texts) != len(candidate_ids) or any(not str(value).strip() for value in bundle.source_texts):
        errors.append("missing_authoritative_source_text")
    if not request.source_languages or any(not value for value in request.source_languages):
        errors.append("missing_source_language")
    if not bundle.trace_id:
        errors.append("missing_bundle_trace_id")
    span_candidates: list[str] = []
    for span in bundle.normalized_spans:
        candidate_id = str(span.get("candidate_id", ""))
        span_candidates.append(candidate_id)
        if not candidate_id or candidate_id not in candidate_ids:
            errors.append("unresolved_candidate_to_segment_lineage")
        timeline = str(span.get("timeline_run_id", ""))
        if not timeline or timeline not in bundle.timeline_run_ids:
            errors.append("missing_or_conflicting_timeline_run_id")
        segment_ids = span.get("segment_ids")
        if not isinstance(segment_ids, (list, tuple)) or not segment_ids or any(not str(value) for value in segment_ids):
            errors.append("empty_or_unresolvable_segment_ids")
        start, end = span.get("start_time"), span.get("end_time")
        if (
            not isinstance(start, (int, float)) or isinstance(start, bool)
            or not isinstance(end, (int, float)) or isinstance(end, bool)
            or not math.isfinite(float(start)) or not math.isfinite(float(end))
            or float(start) < 0 or float(end) < float(start)
        ):
            errors.append("invalid_temporal_interval")
    if sorted(span_candidates) != sorted(candidate_ids):
        errors.append("candidate_span_lineage_mismatch")
    if candidate_set is not None:
        by_id = {candidate.candidate_id: candidate for candidate in candidate_set.candidates}
        if any(value not in by_id for value in candidate_ids):
            errors.append("unresolved_candidate_to_segment_lineage")
        for candidate_id in candidate_ids:
            candidate = by_id.get(candidate_id)
            if candidate is None:
                continue
            if (
                candidate.video_id != bundle.video_id
                or candidate.source_artifact_id not in bundle.source_artifact_ids
                or candidate.source_version not in bundle.source_versions
                or candidate.timeline_run_id not in bundle.timeline_run_ids
                or not candidate.segment_ids
                or not candidate.source_text.strip()
                or not candidate.source_language
            ):
                errors.append("candidate_bundle_identity_conflict")
    if request.evidence_bundle_id != bundle.bundle_id or state.evidence_bundle_id != bundle.bundle_id:
        errors.append("evidence_bundle_id_mismatch")
    return sorted(set(errors))


def product_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for query_id in PRODUCT_IDS:
        trace = load_json(P8 / f"product_initial_baseline.traces/{query_id}.trace.json")
        candidate_set = candidate_set_from_dict(trace["evidence_candidate_set"])
        bundle = bundle_from_dict(trace["evidence_bundle"])
        request = SufficiencyRequest(**trace["mechanical_gate_request"])
        state = EvidenceResolutionState(**trace["evidence_resolution_state"])
        try:
            gate = apply_mechanical_sufficiency_gate(request, state, bundle, MechanicalGatePolicy())
            status = _status(gate)
            exception = None
            reason_codes = [gate.operational_reason_code] if gate.operational_reason_code else []
        except Exception as exc:  # Gate contract requires containment; runner records any breach.
            status = "invalid"
            exception = f"{type(exc).__name__}: {exc}"
            reason_codes = ["unhandled_contract_exception"]
            gate = None
        errors = mechanical_errors(request, state, bundle, candidate_set)
        rows.append({
            "case_id": query_id,
            "builder_version": request.candidate_builder_version,
            "selector_version": request.selector_version,
            "candidate_count": len(candidate_set.candidates),
            "selected_candidate_count": len(bundle.candidate_ids) if bundle else 0,
            "evidence_span_count": len(bundle.normalized_spans) if bundle else 0,
            "identity_contract_pass": not errors,
            "invalid_identity_count": int(bool(errors)),
            "unverifiable_identity_count": 0,
            "source_availability": "unavailable" if status == "source_unverifiable" else "available",
            "bundle_contract_pass": bundle is not None and not errors,
            "mechanical_gate_status": status,
            "reason_codes": reason_codes,
            "trace_id": request.trace_id,
            "mechanical_validation_errors": errors,
            "unhandled_exception": exception,
        })
    return rows


def stress_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_root in sorted(STRESS.iterdir()):
        if not case_root.is_dir():
            continue
        candidate_set = candidate_set_from_dict(load_json(case_root / "candidate_set.json"))
        bundle = bundle_from_dict(load_json(case_root / "evidence_bundle.json"))
        request, state = stress_request(case_root.name, candidate_set, bundle)
        try:
            gate = apply_mechanical_sufficiency_gate(request, state, bundle, MechanicalGatePolicy())
            status = _status(gate)
            exception = None
            reason_codes = [gate.operational_reason_code] if gate.operational_reason_code else []
        except Exception as exc:
            status = "invalid"
            exception = f"{type(exc).__name__}: {exc}"
            reason_codes = ["unhandled_contract_exception"]
        errors = mechanical_errors(request, state, bundle, candidate_set)
        rows.append({
            "case_id": case_root.name,
            "mechanical_gate_status": status,
            "reason_codes": reason_codes,
            "bundle_contract_pass": bundle is not None and not errors,
            "invalid_identity_count": int(bool(errors)),
            "unverifiable_identity_count": 0,
            "mechanical_validation_errors": errors,
            "trace_id": request.trace_id,
            "unhandled_exception": exception,
        })
    return rows


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "total_cases": len(rows),
        "judge_eligible": sum(row["mechanical_gate_status"] == "judge_eligible" for row in rows),
        "source_unverifiable": sum(row["mechanical_gate_status"] == "source_unverifiable" for row in rows),
        "invalid": sum(row["mechanical_gate_status"] == "invalid" for row in rows),
        "unhandled_exception_count": sum(row["unhandled_exception"] is not None for row in rows),
        "invalid_identity_count": sum(int(row["invalid_identity_count"]) for row in rows),
        "unverifiable_identity_count": sum(int(row["unverifiable_identity_count"]) for row in rows),
        "bundle_contract_failure_count": sum(
            row["mechanical_gate_status"] == "judge_eligible" and not row["bundle_contract_pass"]
            for row in rows
        ),
        "exactly_one_terminal_status_per_case": all(
            row["mechanical_gate_status"] in {"judge_eligible", "source_unverifiable", "invalid"}
            for row in rows
        ),
    }


def integrity() -> dict[str, Any]:
    module_path = ROOT / "scripts/run_f1b_selector_cycle.py"
    spec = importlib.util.spec_from_file_location("stage4a_r_f1b_assets", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load frozen-asset verifier: {module_path}")
    f1b = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = f1b
    spec.loader.exec_module(f1b)

    selector_seal = f1b.assert_frozen()
    gate = load_json(F1B_GATE)
    identity_seal = load_json(IDENTITY_SEAL)
    return {
        "formal_builder_version_correct": selector_seal["formal_builder_hashes"]["version"] == FINAL_CANDIDATE_BUILDER_VERSION,
        "formal_builder_hashes_valid": not selector_seal["formal_builder_hashes"]["builder_behavior_changed"],
        "formal_selector_version_correct": gate["frozen_before"]["selector"]["version"] == "v3.5-deterministic-fine-selector-v1",
        "formal_selector_hashes_valid": True,
        "Evidence_Identity_Contract_V1_hash_valid": identity_seal["contract_hash"] == "35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7",
        "canonical_matcher_hash_valid": all(
            digest(ROOT / path) == expected
            for path, expected in identity_seal["matcher_source_hashes"].items()
        ),
        "Development_inputs_unchanged": selector_seal["Product_input_hashes"]["root_sha256"] == gate["frozen_asset_hashes"]["Product_input_hashes"]["root_sha256"],
        "Development_Gold_hashes_unchanged": selector_seal["Development_Gold_hashes"]["root_sha256"] == gate["frozen_asset_hashes"]["Development_Gold_hashes"]["root_sha256"],
        "Stress_inputs_unchanged": selector_seal["Stress_input_hashes"]["root_sha256"] == gate["frozen_asset_hashes"]["Stress_input_hashes"]["root_sha256"],
        "Mechanical_Gate_current_source_hashes": file_hashes(GATE_FILES),
        "Frozen_Evaluation_accessed": False,
        "formal_builder_hashes": gate["frozen_asset_hashes"]["formal_builder_hashes"],
        "formal_selector_hashes": gate["frozen_asset_hashes"]["selector_before_hashes"],
        "Evidence_Identity_Contract_V1_hashes": gate["frozen_asset_hashes"]["Evidence_Identity_Contract_V1_hashes"],
        "Development_input_hashes": gate["frozen_asset_hashes"]["Product_input_hashes"],
        "Development_Gold_hashes": gate["frozen_asset_hashes"]["Development_Gold_hashes"],
        "Stress_input_hashes": gate["frozen_asset_hashes"]["Stress_input_hashes"],
    }


def materialize_gate_contracts() -> None:
    write_json(
        ROOT / "research/v3_5/stage4a/mechanical_gate_contract.json",
        MechanicalGateDecision.model_json_schema(),
    )
    write_json(
        ROOT / "research/v3_5/stage4a/sufficiency_request_contract.json",
        SufficiencyRequest.model_json_schema(),
    )
    write_json(
        ROOT / "research/v3_5/stage4a/sufficiency_decision_contract.json",
        SufficiencyDecision.model_json_schema(),
    )
    write_json(
        ROOT / "research/v3_5/stage4a/mechanical_gate_policy.json",
        MechanicalGatePolicy().model_dump(mode="json"),
    )
    write_json(
        ROOT / "research/v3_5/stage4a/operational_reason_policy.json",
        {
            "policy_version": MECHANICAL_GATE_POLICY_VERSION,
            "reason_to_action_family": REASON_ACTION,
            "reason_to_terminal_projection": {
                reason: (
                    "source_unverifiable"
                    if reason in SOURCE_UNVERIFIABLE_REASONS
                    else "invalid"
                )
                for reason in sorted(REASON_ACTION)
            },
            "selector_aliases": {
                "selector_failure": "selector_failed",
                "no_selected_bundle": "selector_failed",
                "selector_abstain": "selector_failed",
                "invalid_bundle_reference": "selector_failed",
            },
        },
    )
    write_json(
        ROOT / "research/v3_5/stage4a/action_family_policy.json",
        {
            "policy_version": MECHANICAL_GATE_POLICY_VERSION,
            "action_families": sorted(set(REASON_ACTION.values()) | {"none"}),
        },
    )


def freeze_gate() -> None:
    if FREEZE.exists():
        raise RuntimeError("Stage 4A-R Gate Freeze already exists")
    if not BEFORE.exists():
        raise RuntimeError("Before revalidation must complete before Gate Freeze")
    materialize_gate_contracts()
    assets = integrity()
    seal = {
        "schema_version": "v3.5-b-stage4a-r-mechanical-gate-freeze-v1",
        "formal_gate_version": "mechanical-gate-v1-r1",
        "substantive_generic_revisions_used": 1,
        "substantive_generic_revisions_maximum": 1,
        "gate_source_hashes": file_hashes(GATE_FILES),
        "gate_config_hashes": file_hashes(GATE_CONFIG_FILES),
        "contract_schema_hashes": file_hashes(CONTRACT_FILES),
        "Evidence_Identity_Contract_V1_hashes": assets["Evidence_Identity_Contract_V1_hashes"],
        "formal_builder_hashes": assets["formal_builder_hashes"],
        "formal_selector_hashes": assets["formal_selector_hashes"],
        "canonical_matcher_hashes": load_json(IDENTITY_SEAL)["matcher_source_hashes"],
        "test_hashes": file_hashes(TEST_FILES),
        "execution_source_hashes": {
            relative(Path(__file__).resolve()): digest(Path(__file__).resolve()),
        },
        "Development_input_hashes": assets["Development_input_hashes"],
        "Development_Gold_hashes": assets["Development_Gold_hashes"],
        "Stress_input_hashes": assets["Stress_input_hashes"],
        "before_revalidation_sha256": digest(BEFORE),
        "terminal_projection_contract": {
            "statuses": ["judge_eligible", "source_unverifiable", "invalid"],
            "exactly_one_terminal_status_per_case": True,
            "source_unverifiable_is_terminal": True,
            "invalid_is_terminal": True,
            "judge_eligible_requires_semantic_judge": True,
            "semantic_sufficiency_evaluated": False,
        },
        "reason_code_contract": {
            reason: (
                "source_unverifiable"
                if reason in SOURCE_UNVERIFIABLE_REASONS
                else "invalid"
            )
            for reason in sorted(REASON_ACTION)
        },
        "Frozen_Evaluation_accessed": False,
        "formal_Product_revalidation_run_count": 0,
        "formal_Stress_revalidation_run_count": 0,
    }
    write_json(FREEZE, seal)


def verify_freeze() -> dict[str, Any]:
    seal = load_json(FREEZE)
    groups = {
        "gate_source_hashes": GATE_FILES,
        "gate_config_hashes": GATE_CONFIG_FILES,
        "contract_schema_hashes": CONTRACT_FILES,
        "test_hashes": TEST_FILES,
    }
    mismatches: dict[str, Any] = {}
    for name, paths in groups.items():
        actual = file_hashes(paths)
        if actual != seal[name]:
            mismatches[name] = {"expected": seal[name], "actual": actual}
    runner_path = Path(__file__).resolve()
    expected_runner = seal["execution_source_hashes"][relative(runner_path)]
    if digest(runner_path) != expected_runner:
        mismatches["execution_source_hashes"] = {
            "expected": expected_runner, "actual": digest(runner_path),
        }
    assets = integrity()
    for key in (
        "formal_builder_version_correct", "formal_builder_hashes_valid",
        "formal_selector_version_correct", "formal_selector_hashes_valid",
        "Evidence_Identity_Contract_V1_hash_valid", "canonical_matcher_hash_valid",
        "Development_inputs_unchanged", "Development_Gold_hashes_unchanged",
        "Stress_inputs_unchanged",
    ):
        if assets[key] is not True:
            mismatches[key] = assets[key]
    if mismatches:
        raise RuntimeError({"post_freeze_mismatch": mismatches})
    return seal


def post_freeze_preflight() -> None:
    if PREFLIGHT.exists():
        raise RuntimeError("Stage 4A-R post-freeze preflight already exists")
    seal = verify_freeze()
    write_json(PREFLIGHT, {
        "schema_version": "v3.5-b-stage4a-r-post-freeze-preflight-v1",
        "status": "pass",
        "formal_gate_version": seal["formal_gate_version"],
        "Gate_Freeze_hash_valid": True,
        "Gate_source_hashes_valid": True,
        "Gate_config_hashes_valid": True,
        "contract_schema_hashes_valid": True,
        "test_hashes_valid": True,
        "formal_builder_hashes_valid": True,
        "formal_selector_hashes_valid": True,
        "Evidence_Identity_Contract_V1_hash_valid": True,
        "canonical_matcher_hash_valid": True,
        "Development_inputs_and_Gold_unchanged": True,
        "Stress_inputs_unchanged": True,
        "formal_Product_revalidation_run_count": 0,
        "formal_Stress_revalidation_run_count": 0,
        "semantic_judge_started": False,
        "Frozen_Evaluation_accessed": False,
        "gate_freeze_sha256": digest(FREEZE),
    })


def run_after() -> None:
    if PRODUCT_ROWS.exists() or PRODUCT_METRICS.exists() or STRESS_METRICS.exists():
        raise RuntimeError("formal Stage 4A-R revalidation output already exists")
    if not PREFLIGHT.exists() or load_json(PREFLIGHT).get("status") != "pass":
        raise RuntimeError("passing post-freeze preflight required")
    verify_freeze()
    product = product_rows()
    product_summary = summarize(product)
    product_summary.update({
        "schema_version": "v3.5-b-stage4a-r-product-metrics-v1",
        "formal_Product_revalidation_run_count": 1,
        "historical_expected_distribution": {
            "judge_eligible": 13, "source_unverifiable": 1, "invalid": 0,
        },
        "historical_distribution_reproduced": (
            product_summary["judge_eligible"] == 13
            and product_summary["source_unverifiable"] == 1
            and product_summary["invalid"] == 0
        ),
        "judge_eligible_bundle_contract_pass_rate": (
            sum(
                row["bundle_contract_pass"]
                for row in product if row["mechanical_gate_status"] == "judge_eligible"
            )
            / max(1, product_summary["judge_eligible"])
        ),
        "source_unverifiable_cases_have_valid_reason_codes": all(
            row["reason_codes"]
            for row in product if row["mechanical_gate_status"] == "source_unverifiable"
        ),
        "Frozen_Evaluation_accessed": False,
    })
    write_jsonl(PRODUCT_ROWS, product)
    write_json(PRODUCT_METRICS, product_summary)

    stress = stress_rows()
    stress_summary = summarize(stress)
    stress_summary.update({
        "schema_version": "v3.5-b-stage4a-r-stress-metrics-v1",
        "formal_Stress_revalidation_run_count": 1,
        "judge_eligible_bundle_contract_pass_rate": (
            sum(
                row["bundle_contract_pass"]
                for row in stress if row["mechanical_gate_status"] == "judge_eligible"
            )
            / max(1, stress_summary["judge_eligible"])
        ),
        "source_unverifiable_cases_have_valid_reason_codes": all(
            row["reason_codes"]
            for row in stress if row["mechanical_gate_status"] == "source_unverifiable"
        ),
        "per_case": stress,
        "Frozen_Evaluation_accessed": False,
    })
    write_json(STRESS_METRICS, stress_summary)


def run_before() -> None:
    if BEFORE.exists():
        raise RuntimeError("Before revalidation already exists")
    assets = integrity()
    if not all(value is True for key, value in assets.items() if key.endswith(("correct", "valid", "unchanged"))):
        raise RuntimeError("formal frozen asset mismatch")
    product = product_rows()
    stress = stress_rows()
    write_json(BEFORE, {
        "schema_version": "v3.5-b-stage4a-r-before-v1",
        "asset_integrity": assets,
        "formal_gate_version": "mechanical-gate-v1",
        "product": summarize(product),
        "stress": summarize(stress),
        "product_per_case": product,
        "stress_per_case": stress,
        "formal_Product_revalidation_started": False,
        "formal_Stress_revalidation_started": False,
        "Frozen_Evaluation_accessed": False,
    })


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("command", choices=("integrity", "before", "freeze", "preflight", "after"))
    return value


def main() -> None:
    command = parser().parse_args().command
    if command == "integrity":
        print(json.dumps(integrity(), ensure_ascii=False, sort_keys=True, indent=2))
    elif command == "before":
        run_before()
    elif command == "freeze":
        freeze_gate()
    elif command == "preflight":
        post_freeze_preflight()
    elif command == "after":
        run_after()


if __name__ == "__main__":
    main()
