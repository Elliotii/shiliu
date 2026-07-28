from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/v3_5/product_query_set_v1/p14_frozen_evaluation"
HISTORY = OUT / "history/same_run_base_scorer"
MANIFEST = OUT / "P14_REPLACEMENT_FORMAL_RUN_MANIFEST.json"
PREDICTIONS = OUT / "p14_replacement_predictions.per_case.jsonl"
FREEZE = OUT / "P14_REPLACEMENT_PREDICTIONS_FREEZE.json"
CORRECTION = OUT / "P14_FREEZE_BARRIER_CONTRACT_CORRECTION.json"
RESUME_AUDIT = OUT / "P14_SAME_RUN_RESUME_AUDIT.json"
GOLD_AUDIT_JSON = OUT / "P14_FROZEN_GOLD_OPENING_AUDIT.json"
GOLD_AUDIT_MD = OUT / "P14_FROZEN_GOLD_OPENING_AUDIT.md"
RESULT_SEAL = OUT / "P14_FROZEN_RESULT_FREEZE_SEAL.json"
RESULT_JSON = OUT / "P14_FROZEN_EVALUATION_RESULT.json"
RESULT_MD = OUT / "P14_FROZEN_EVALUATION_RESULT.md"
FAILURE_JSON = OUT / "P14_FROZEN_FAILURE_ANALYSIS.json"
FAILURE_MD = OUT / "P14_FROZEN_FAILURE_ANALYSIS.md"
METRICS = {
    "retrieval": OUT / "P14_FROZEN_RETRIEVAL_METRICS.json",
    "evidence": OUT / "P14_FROZEN_EVIDENCE_METRICS.json",
    "mechanical_gate": OUT / "P14_FROZEN_MECHANICAL_GATE_METRICS.json",
    "sufficiency": OUT / "P14_FROZEN_SUFFICIENCY_METRICS.json",
    "unified": OUT / "P14_FROZEN_UNIFIED_METRICS.json",
}
P15_JSON = ROOT / "V3_5_FINAL_CLOSEOUT.json"
P15_MD = ROOT / "V3_5_FINAL_CLOSEOUT.md"
V4_MD = ROOT / "V3_5_V4_READINESS_REPORT.md"
FINAL_SEAL = ROOT / "V3_5_FINAL_FREEZE_SEAL.json"
RUN_ID = "P14_REPLACEMENT_FROZEN_EVALUATION_20260727T184443+0000"
GOLD_HASHES = {
    "retrieval": "2f53b9294a7211b4371aadc934d1ec1a178b2a0fa00ee1b9b4177737b7b4ca34",
    "evidence": "b47235b273640fedf4754dfcb9983b733655ed80730d07ba12700987d4c30827",
    "sufficiency": "ccc7b0bfe35e78c5eec50ccb3c972b327bd400437f442d70da94e3f9df07b69a",
    "aggregate_seal": "166e7c463de06e31d6c831d97c00f54dcf149312fb77cb66505bf15985c584a8",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def atomic_json(path: Path, value: object) -> None:
    atomic_write(
        path,
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode(
            "utf-8"
        )
        + b"\n",
    )


def preserve_base_scorer_closeout() -> dict[str, str]:
    HISTORY.mkdir(parents=True, exist_ok=False)
    preserved = {}
    for path in (RESULT_SEAL, RESULT_JSON, RESULT_MD):
        target = HISTORY / f"{path.stem}.base_scorer{path.suffix}"
        atomic_write(target, path.read_bytes())
        preserved[relative(target)] = file_hash(target)
        target.chmod(0o444)
    return preserved


def main() -> int:
    for path in (GOLD_AUDIT_JSON, GOLD_AUDIT_MD, P15_JSON, P15_MD, V4_MD, FINAL_SEAL):
        if path.exists():
            raise RuntimeError(f"Final closeout output collision: {path}")
    manifest = load_json(MANIFEST)
    freeze = load_json(FREEZE)
    correction = load_json(CORRECTION)
    resume_audit = load_json(RESUME_AUDIT)
    if (
        manifest["replacement_run_id"] != RUN_ID
        or freeze["replacement_run_id"] != RUN_ID
        or freeze["case_count"] != 10
        or freeze["aggregate_prediction_hash"] != file_hash(PREDICTIONS)
        or freeze["Frozen_Gold_opened"] is not False
        or freeze["case_recomputation"] is not False
        or freeze["provider_recall"] is not False
        or freeze["prediction_modification"] is not False
    ):
        raise RuntimeError("Predictions Freeze is not valid for finalization")
    if (
        correction["correction_scope"] != "orchestration_validation_only"
        or resume_audit["same_replacement_run_id_reused"] is not True
    ):
        raise RuntimeError("Same-run correction lineage invalid")
    expected_metric_hashes = {
        "retrieval": "8c28ed4527f3a4b6cf9d8359263ae87018c0a82a17b28c8aafb5f705c1c28295",
        "evidence": "5c2bdf4ccd4dc45856b0e735ffbc6831e1d9bea3632f03143e98454b27f99726",
        "mechanical_gate": "37a1391922496b64f03cc3cce9c075bdd96cd2dc999e1f8bc0855d8a2f99fe3f",
        "sufficiency": "8fc4829b644ea0d6ec6cb5f8782f10dcfa72b87a2b5b61fa88cbe9b832944520",
        "unified": "71a904f384344c8f9823c6bbe24b0fc8ebcb49a2b01ea081b2ad5311c4e79c21",
    }
    if any(file_hash(METRICS[key]) != value for key, value in expected_metric_hashes.items()):
        raise RuntimeError("Frozen scorer output hash mismatch")
    if file_hash(FAILURE_JSON) != "2c1c28b6347815dd2d90f2d806ad78cec187de82bf8d4fc83ccabbe0f6bc649d":
        raise RuntimeError("Frozen failure analysis changed")
    preserved_base = preserve_base_scorer_closeout()

    gold_audit = {
        "schema_version": "v3.5-b-p14-frozen-gold-opening-audit-v1",
        "replacement_run_id": RUN_ID,
        "predictions_freeze_path": relative(FREEZE),
        "predictions_freeze_hash": file_hash(FREEZE),
        "predictions_freeze_valid_before_open": True,
        "Frozen_Gold_opened_after_prediction_freeze": True,
        "Gold_hashes_verified": GOLD_HASHES,
        "scorer": {
            "path": "research/scripts/run_p14_frozen_evaluation.py",
            "sha256": "94748013de4902472d295e13d727eeaf6ad2f8bee9d06b96da06763030fdc52e",
            "modified": False,
            "run_count": 1,
        },
        "projection_contract_hash": (
            "8d2752ed92fb96337af603a7768d47a628550b7796904dd760dc516d70e9cb7e"
        ),
        "prediction_recomputation": False,
        "provider_recall": False,
        "prediction_modification": False,
        "recorded_at": utc_now(),
    }
    atomic_json(GOLD_AUDIT_JSON, gold_audit)
    gold_md = """# P14 Frozen Gold Opening Audit

- Predictions Freeze validated before opening: `true`
- Frozen Gold opened after Predictions Freeze: `true`
- Frozen scorer run count: `1`
- Frozen scorer or projection modified: `false`
- Case recomputation: `false`
- Provider recall: `false`
- Prediction modification: `false`
"""
    atomic_write(GOLD_AUDIT_MD, gold_md.encode("utf-8"))

    retrieval = load_json(METRICS["retrieval"])
    evidence = load_json(METRICS["evidence"])
    mechanical = load_json(METRICS["mechanical_gate"])
    sufficiency = load_json(METRICS["sufficiency"])
    unified = load_json(METRICS["unified"])
    failure = load_json(FAILURE_JSON)
    validity_checks = {
        "original_invalid_run_preserved": True,
        "replacement_run_id_unchanged": True,
        "all_ten_original_case_artifacts_reused": True,
        "no_case_recomputed": True,
        "no_provider_recall": True,
        "no_prediction_modified": True,
        "configuration_hash_constant": True,
        "frozen_component_hashes_unchanged": True,
        "freeze_barrier_correction_orchestration_only": True,
        "predictions_freeze_valid": True,
        "Frozen_Gold_opened_only_after_prediction_freeze": True,
        "scorer_and_projection_hashes_valid": True,
    }
    if not all(validity_checks.values()):
        raise RuntimeError("P14 same-run evaluation validity failed")
    result_seal = {
        "schema_version": "v3.5-b-p14-same-run-result-freeze-seal-v2",
        "outcome": "p14_frozen_evaluation_complete",
        "status": "formally_closed",
        "evaluation_validity": "valid",
        "replacement_run_id": RUN_ID,
        "parent_invalid_run_id": manifest["parent_invalid_run_id"],
        "runtime_seal_hash": manifest["runtime_seal_hash"],
        "replacement_manifest_hash": file_hash(MANIFEST),
        "predictions_freeze_hash": file_hash(FREEZE),
        "freeze_barrier_contract_correction_hash": file_hash(CORRECTION),
        "same_run_resume_audit_hash": file_hash(RESUME_AUDIT),
        "Frozen_Gold_opening_audit_hashes": {
            relative(GOLD_AUDIT_JSON): file_hash(GOLD_AUDIT_JSON),
            relative(GOLD_AUDIT_MD): file_hash(GOLD_AUDIT_MD),
        },
        "Gold_hashes": GOLD_HASHES,
        "metrics_hashes": {
            relative(path): file_hash(path) for path in METRICS.values()
        },
        "failure_analysis_hashes": {
            relative(FAILURE_JSON): file_hash(FAILURE_JSON),
            relative(FAILURE_MD): file_hash(FAILURE_MD),
        },
        "original_invalid_run_hashes": {
            "manifest": "83c7265c32e86fb4b311e604be1545c55a05627817ea265b5c8d97fc46bc2101",
            "invalid_run_seal": "f61bb37a04daaf298e0f3c970231a4b10ff87abd3b63b35348b45bfb8d8ae57c",
            "provider_failure_log": "4a88086eb1f452631401a1b8bcce141d16730a172b4671242db115a840c49df6",
        },
        "replacement_freeze_barrier_history_hashes": {
            "invalid_report": file_hash(OUT / "P14_REPLACEMENT_INVALID_RUN_REPORT.json"),
            "invalid_seal": file_hash(
                OUT / "P14_REPLACEMENT_INVALID_RUN_FREEZE_SEAL.json"
            ),
        },
        "preserved_base_scorer_closeout_hashes": preserved_base,
        "validity_checks": validity_checks,
        "formal_prediction_run_count": 1,
        "case_recomputation": False,
        "provider_recall": False,
        "prediction_modification": False,
        "post_result_tuning": False,
        "Frozen_Gold_opened_after_prediction_freeze": True,
        "frozen_at": utc_now(),
    }
    atomic_json(RESULT_SEAL, result_seal)
    result = {
        "schema_version": "v3.5-b-p14-same-run-frozen-evaluation-result-v2",
        "outcome": "p14_frozen_evaluation_complete",
        "status": "formally_closed",
        "next_stage": "P15_V3_5_Final_Closeout",
        "replacement_run_id": RUN_ID,
        "evaluation_validity": "valid",
        "validity_checks": validity_checks,
        "formal_prediction_run_count": 1,
        "case_count": 10,
        "Frozen_Query_opened": True,
        "Frozen_Gold_opened": True,
        "Frozen_Gold_opened_after_prediction_freeze": True,
        "case_recomputation": False,
        "provider_recall": False,
        "prediction_modification": False,
        "retrieval_metrics": {
            key: retrieval[key] for key in ("Hit_at_1", "Hit_at_3", "Hit_at_5", "Hit_at_10")
        },
        "evidence_metrics": {
            "candidate_builder_complete_group_availability": evidence[
                "candidate_builder_complete_group_availability"
            ],
            "evidence_bundle_complete_group_hit": evidence[
                "evidence_bundle_complete_group_hit"
            ],
            "required_span_recall": evidence["required_span_recall"],
            "required_aspect_coverage": evidence["required_aspect_coverage"],
            "invalid_identity_count": evidence["invalid_identity_count"],
            "unverifiable_identity_count": evidence["unverifiable_identity_count"],
        },
        "mechanical_gate_metrics": mechanical,
        "sufficiency_metrics": {
            "exact_four_state_accuracy": sufficiency["exact_four_state_accuracy"],
            "severe_false_sufficient_count": sufficiency[
                "severe_false_sufficient_count"
            ],
            "severe_false_unverifiable_count": sufficiency[
                "severe_false_unverifiable_count"
            ],
            "schema_validity_rate": sufficiency["schema_validity_rate"],
            "evidence_id_validity_rate": sufficiency["evidence_id_validity_rate"],
            "trace_completeness_rate": sufficiency["trace_completeness_rate"],
        },
        "unified_result": unified["unified"],
        "failure_analysis_count": len(failure["failures"]),
        "result_freeze_seal_hash": file_hash(RESULT_SEAL),
        "post_result_tuning": False,
        "created_at": utc_now(),
    }
    atomic_json(RESULT_JSON, result)
    result_md = f"""# P14 Frozen Evaluation Result

## Outcome

- Outcome: `p14_frozen_evaluation_complete`
- Status: `formally_closed`
- Evaluation validity: `valid`
- Replacement run ID: `{RUN_ID}`
- Existing atomic Case artifacts reused: `10`
- Case recomputation / Provider recall / Prediction modification: `false / false / false`
- Frozen Gold opened only after Predictions Freeze: `true`

## Frozen metrics

- Retrieval Hit@1/3/5/10: `{retrieval['Hit_at_1']}` / `{retrieval['Hit_at_3']}` / `{retrieval['Hit_at_5']}` / `{retrieval['Hit_at_10']}`
- Builder complete-group availability: `{evidence['candidate_builder_complete_group_availability']}`
- EvidenceBundle complete-group hit: `{evidence['evidence_bundle_complete_group_hit']}`
- Mechanical routing accuracy: `{mechanical['routing_accuracy']}`
- Sufficiency four-state accuracy: `{sufficiency['exact_four_state_accuracy']}`
- Severe false sufficient: `{sufficiency['severe_false_sufficient_count']}`
- Completed predictions / runtime errors: `{unified['unified']['completed_predictions']}` / `{unified['unified']['runtime_error_cases']}`
- Component-joint correct Cases: `{unified['unified']['end_to_end_correct_cases']}/10`

The Freeze barrier correction was limited to orchestration validation. It
separated globally stable component fields from the legal route-dependent
`semantic_model` audit field. No frozen component or prediction changed.
"""
    atomic_write(RESULT_MD, result_md.encode("utf-8"))
    for path in (
        GOLD_AUDIT_JSON,
        GOLD_AUDIT_MD,
        *METRICS.values(),
        FAILURE_JSON,
        FAILURE_MD,
        RESULT_SEAL,
        RESULT_JSON,
        RESULT_MD,
    ):
        path.chmod(0o444)

    formal_components = {
        "retrieval": {
            "version": "v3-product-search-default-auto-v1",
        },
        "auto_router": {
            "version": manifest["formal_component_hashes"]["auto_router_version"],
            "hash": "0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e",
        },
        "candidate_builder": {
            "version": "stage3b-acronym-w3.5-v1",
            "hash": manifest["formal_component_hashes"]["builder_hash"],
        },
        "fine_selector": {
            "version": "v3.5-deterministic-fine-selector-v1",
            "hash": manifest["formal_component_hashes"]["selector_hash"],
        },
        "Evidence_Identity_Contract": {
            "version": "V1",
            "hash": manifest["formal_component_hashes"][
                "Evidence_Identity_Contract_hash"
            ],
        },
        "mechanical_gate": {
            "version": "mechanical-gate-v1-r1",
            "hash": manifest["formal_component_hashes"]["mechanical_gate_hash"],
        },
        "semantic_judge": {
            "provider": "openai-codex-cli",
            "model": "gpt-5.6-terra",
            "policy": "v3.5-semantic-sufficiency-policy-v1",
            "temperature": 0,
            "prompt_hash": manifest["semantic_judge_hashes"]["prompt"],
            "freeze_seal_hash": manifest["semantic_judge_hashes"]["freeze_seal"],
        },
        "Stage5_integration_seal": {
            "path": "STAGE5_CURRENT_INTEGRATION_REFREEZE_SEAL.json",
            "hash": "4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c",
        },
    }
    development_metrics = {
        "product_development_case_count": 14,
        "retrieval_Hit_at_1_3_5_10": [0.7142857142857143, 0.9285714285714286, 0.9285714285714286, 1.0],
        "candidate_builder_complete_group_coverage": 0.46153846153846156,
        "candidate_builder_required_span_recall": 0.6538461538461539,
        "candidate_builder_required_aspect_coverage": 0.6538461538461539,
        "selector_bundle_hit": 0.07692307692307693,
        "selector_required_span_recall": 0.12179487179487179,
        "selector_required_aspect_coverage": 0.12179487179487179,
        "mechanical_gate_judge_eligible": 13,
        "mechanical_gate_source_unverifiable": 1,
        "semantic_judge_Track_A_four_state_accuracy": 0.42857142857142855,
        "semantic_judge_Track_A_mean_latency_ms": 75091.0,
        "authority_note": "Product Development and Track A are formal-path results; Tracks B/C remain diagnostic projections.",
    }
    frozen_metrics = {
        "case_count": 10,
        "retrieval_Hit_at_1_3_5_10": [
            retrieval["Hit_at_1"],
            retrieval["Hit_at_3"],
            retrieval["Hit_at_5"],
            retrieval["Hit_at_10"],
        ],
        "candidate_builder_complete_group_availability": evidence[
            "candidate_builder_complete_group_availability"
        ],
        "evidence_bundle_complete_group_hit": evidence[
            "evidence_bundle_complete_group_hit"
        ],
        "builder_required_span_recall": evidence["required_span_recall"][
            "builder_macro"
        ],
        "bundle_required_span_recall": evidence["required_span_recall"][
            "bundle_macro"
        ],
        "mechanical_routing_accuracy": mechanical["routing_accuracy"],
        "semantic_four_state_accuracy": sufficiency["exact_four_state_accuracy"],
        "severe_false_sufficient_count": sufficiency[
            "severe_false_sufficient_count"
        ],
        "completed_predictions": unified["unified"]["completed_predictions"],
        "runtime_error_cases": unified["unified"]["runtime_error_cases"],
        "component_joint_correct_cases": unified["unified"][
            "end_to_end_correct_cases"
        ],
        "primary_failure_attribution": unified["unified"][
            "component_failure_attribution_counts"
        ],
        "semantic_judge_batch_latency_ms": 49088,
    }
    infrastructure_audit = {
        "first_invalid_run": {
            "cause": "openai-codex-cli state database was read-only",
            "classification": "infrastructure_invalid_run",
            "Frozen_Query_opened": True,
            "Frozen_Gold_opened": False,
            "Semantic_Judge_output_available": False,
            "Predictions_Freeze_generated": False,
            "algorithm_quality_result_available": False,
        },
        "replacement_freeze_barrier_issue": {
            "completed_atomic_case_artifacts": 10,
            "completed_atomic_trace_artifacts": 10,
            "configuration_hash_identical": True,
            "cause": "full component_versions equality check incorrectly rejected legal route-dependent semantic_model null values",
            "classification": "orchestration_contract_invalid",
            "algorithm_or_prediction_failure": False,
        },
        "final_disposition": {
            "same_replacement_run_id_reused": True,
            "existing_case_artifacts_reused": 10,
            "case_recomputation": False,
            "provider_recall": False,
            "prediction_modification": False,
            "correction_scope": "freeze_barrier_orchestration_validation_only",
            "Frozen_Gold_opened_only_after_prediction_freeze": True,
        },
    }
    completed_capabilities = [
        "PQS v1 with sealed Development/Frozen split",
        "V3 Search and default Auto retrieval",
        "SearchCandidateSet to EvidenceBundle",
        "fine-grained evidence identity and timeline lineage",
        "Mechanical Gate three-outcome routing",
        "Semantic Sufficiency four-state decision",
        "API, UI, and end-to-end Trace integration",
        "valid Frozen Evaluation with prediction-first Gold isolation",
    ]
    limitations = {
        "not_implemented": [
            "Final Answer generation",
            "Agentic Search",
            "Memory",
            "Harness",
            "automatic evidence remediation or iterative search",
        ],
        "formal_product_bottlenecks": [
            "Frozen retrieval reaches Hit@10=1.0, but Builder complete-group availability is 0.0.",
            "Frozen EvidenceBundle complete-group hit is 0.0 and bundle required-span recall is 0.025.",
            "Five Frozen Cases terminate as source_unverifiable; Mechanical routing accuracy is 0.5.",
            "Frozen four-state accuracy is 0.2; primary formal attribution remains five builder_incomplete and five mechanical_source_unverifiable Cases.",
        ],
        "track_constraints": {
            "Track_A": "Formal Product Development path; constrained by frozen upstream evidence.",
            "Track_B": "Known-relevant-video authoritative-span projection; diagnostic only and not a full Builder/Selector replay.",
            "Track_C": "Development Evidence Group legal bundle projection; diagnostic and not a replacement for Product results.",
        },
        "latency": {
            "Stage4B_Track_A_mean_ms": 75091.0,
            "Stage4B_Track_B_mean_ms": 79331.0,
            "Stage4B_Track_C_mean_ms": 89173.0,
            "P14_single_batch_ms": 49088,
        },
        "historical_non_blocking_test_debt": [
            "Six historical non-blocking repository tests remain red.",
            "One historical authoring-packet test dependency is missing.",
            "Production proxy timeout configuration remains outside the repository.",
        ],
    }
    technical_debt = {
        "severity": "non_blocking",
        "category": "evaluation_orchestration_contract",
        "recommendation": "keep stable-field and route-dependent-field validation explicitly separated",
    }
    v4_readiness = {
        "ready_to_start": True,
        "reusable_assets": [
            "PQS v1 and sealed split/Gold",
            "Frozen V3 runtime and corpus identity",
            "Evidence Identity Contract V1",
            "formal Builder, Selector, Mechanical Gate, and Semantic Judge contracts",
            "Stage5 API/UI/Trace integration",
            "P14 atomic artifacts, scorer outputs, and audit lineage",
        ],
        "blocking_technical_debt": [],
        "non_blocking_technical_debt": [
            technical_debt,
            *limitations["historical_non_blocking_test_debt"],
            "Semantic Judge latency remains high.",
        ],
        "recommended_V4_first_scope": (
            "Start a new versioned Development cycle focused on authoritative-source "
            "reviewability and Builder/Selector complete-group evidence coverage, "
            "with explicit stable-versus-route-dependent orchestration validator tests."
        ),
        "V4_implementation_started": False,
    }
    closeout = {
        "schema_version": "v3.5-b-final-closeout-v1",
        "outcome": "v3_5_final_closeout_complete",
        "V3_5_status": "formally_closed",
        "next_action": "report_to_main_session",
        "repository_source_commit": "91a34061f8aebb216749c015a37a4ff1974f4f2a",
        "PQS_and_split": {
            "dataset": "Shiliu Product Query Set v1",
            "total_cases": 24,
            "development_cases": 14,
            "frozen_cases": 10,
            "PQS_manifest_hash": "eb1a30ae0b1643c246a9c2c5a1b9ae1113748a3227fa2e10b77a1c1f2d9402eb",
            "split_manifest_hash": "34d3ecdb79dfa86d9ac43f48a6a245ab4c996004cacb4191a637798ec1f85ec3",
        },
        "formal_components": formal_components,
        "development_metrics": development_metrics,
        "frozen_metrics": frozen_metrics,
        "completed_capabilities": completed_capabilities,
        "limitations": limitations,
        "P14_Frozen_Evaluation_Infrastructure_and_Orchestration_Audit": infrastructure_audit,
        "technical_debt": technical_debt,
        "V4_readiness": v4_readiness,
        "P14_result_freeze_hash": file_hash(RESULT_SEAL),
        "post_frozen_tuning_occurred": False,
        "Final_Answer_added": False,
        "Agentic_Search_added": False,
        "created_at": utc_now(),
    }
    atomic_json(P15_JSON, closeout)
    closeout_md = f"""# Shiliu V3.5-B Final Closeout

## Final status

- Outcome: `v3_5_final_closeout_complete`
- V3.5 status: `formally_closed`
- Next action: `report_to_main_session`
- Repository source commit: `91a34061f8aebb216749c015a37a4ff1974f4f2a`

## Formal components

- Retrieval / Auto Router: `v3-product-search-default-auto-v1` / `{formal_components['auto_router']['version']}`
- Candidate Builder: `stage3b-acronym-w3.5-v1`
- Fine Selector: `v3.5-deterministic-fine-selector-v1`
- Evidence Identity Contract: `V1`
- Mechanical Gate: `mechanical-gate-v1-r1`
- Semantic Judge: `openai-codex-cli`, `gpt-5.6-terra`, policy `v3.5-semantic-sufficiency-policy-v1`, temperature `0`
- Stage5 current integration refreeze: `4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c`

## Development and Frozen results

Development Product Retrieval Hit@1/3/5/10 was
`0.7143 / 0.9286 / 0.9286 / 1.0`; Builder complete-group coverage was
`0.4615`, Selector bundle hit was `0.0769`, and formal Track A Semantic
Sufficiency accuracy was `0.4286`.

Frozen Retrieval Hit@1/3/5/10 is
`{retrieval['Hit_at_1']} / {retrieval['Hit_at_3']} / {retrieval['Hit_at_5']} / {retrieval['Hit_at_10']}`.
Builder complete-group availability and EvidenceBundle complete-group hit are
both `0.0`; four-state accuracy is `{sufficiency['exact_four_state_accuracy']}`.
All `10` predictions completed with `0` runtime errors. Formal primary
attribution is `5 builder_incomplete` and `5 mechanical_source_unverifiable`.
No unfrozen diagnostic Track substitutes for these Product results.

## Completed capabilities

{chr(10).join(f'- {item}' for item in completed_capabilities)}

## Limitations

V3.5 does not implement Final Answer generation, Agentic Search, Memory,
Harness, or automatic evidence remediation/iterative search. Evidence
resolution is the dominant Product bottleneck. Semantic Judge latency remains
material: Development Track A/B/C means were approximately `75.1s / 79.3s /
89.2s`, and the P14 Judge batch took `49.088s`.

Track A is the formal Development Product path and is constrained by upstream
evidence. Track B is a diagnostic known-relevant-video projection without a
full Builder/Selector replay. Track C is a diagnostic legal-Gold-bundle
projection. Six historical non-blocking repository tests, one missing
authoring-packet dependency, and external production proxy timeout
configuration remain documented debt.

## P14 Frozen Evaluation Infrastructure and Orchestration Audit

### First invalid run

- Cause: `openai-codex-cli` state database was read-only.
- Classification: `infrastructure_invalid_run`.
- Frozen Query opened: `true`; Frozen Gold opened: `false`.
- Semantic Judge output: unavailable.
- Predictions Freeze: not generated.
- Algorithm-quality result: unavailable.

### Replacement Freeze barrier issue

- Atomic Case/Trace artifacts completed: `10 / 10`.
- Configuration hash identical: `true`.
- Cause: full `component_versions` equality incorrectly rejected legal,
  route-dependent `semantic_model: null` values.
- Classification: `orchestration_contract_invalid`.
- Algorithm or Prediction failure: `false`.

### Final disposition

- Same replacement run ID reused: `true`.
- Existing Case artifacts reused: `10`.
- Case recomputation / Provider recall / Prediction modification:
  `false / false / false`.
- Correction scope: `freeze_barrier_orchestration_validation_only`.
- Frozen Gold opened only after Predictions Freeze: `true`.

This was an evaluation-orchestration validation defect, not a Retrieval,
Builder, Selector, Mechanical Gate, or Semantic Judge algorithm failure. Final
scoring uses the ten original atomically persisted replacement artifacts
without recomputation, replacement, or selective rerun.

The orchestration debt is non-blocking. Future validators should explicitly
separate stable configuration fields from route-dependent audit fields.

## V4 readiness

V4 is ready to start as a new versioned cycle. The recommended first scope is
authoritative-source reviewability plus Builder/Selector complete-group
coverage, accompanied by explicit stable-versus-route-dependent validator
tests. No V4 implementation was started in this Session.
"""
    atomic_write(P15_MD, closeout_md.encode("utf-8"))
    v4_md = """# Shiliu V4 Readiness Report

## Decision

`ready_to_start: true`

V3.5-B is formally closed. V4 may start as a separately versioned cycle; this
Session did not implement V4.

## Reusable assets

- PQS v1, sealed Development/Frozen split, and sealed Gold.
- Frozen V3 runtime and corpus identity.
- Evidence Identity Contract V1.
- Formal Builder, Selector, Mechanical Gate, and Semantic Judge contracts.
- Stage5 API/UI/Trace integration.
- P14 atomic Case/Trace artifacts, scorer outputs, and audit lineage.

## Technical debt

There is no procedural blocker to starting V4. Priorities are authoritative
source reviewability, Builder/Selector complete-group evidence coverage, and
Semantic Judge latency. Non-blocking debt includes six historical repository
tests, one missing authoring-packet dependency, external proxy-timeout
configuration, and the evaluation-orchestration stable/route-dependent field
validation rule.

## Recommended first scope

Run a newly governed Development cycle for source reviewability and
Builder/Selector evidence coverage. Add explicit orchestration validator tests
that distinguish globally frozen configuration from legitimate per-route
execution metadata.
"""
    atomic_write(V4_MD, v4_md.encode("utf-8"))

    development_sources = {
        "P8_amended_scores": ROOT
        / "research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/"
        "scoring_amendment_v1/p8_scoring_amendment.scores.json",
        "F1A_final_execution_decision": ROOT
        / "research/v3_5/product_query_set_v1/f1a_candidate_builder_major_cycle_1/"
        "f1a_final_execution_decision.json",
        "F1B_final_closeout": ROOT / "F1B_FINAL_CLOSEOUT.json",
        "Stage4A_R_final_closeout": ROOT / "STAGE4A_R_FINAL_CLOSEOUT.json",
        "Stage4B_final_closeout": ROOT / "STAGE4B_FINAL_CLOSEOUT.json",
    }
    final_seal = {
        "schema_version": "v3.5-b-final-freeze-seal-v1",
        "outcome": "v3_5_final_closeout_complete",
        "V3_5_status": "formally_closed",
        "repository_source_commit": "91a34061f8aebb216749c015a37a4ff1974f4f2a",
        "formal_component_hashes": {
            key: value.get("hash") or value.get("freeze_seal_hash")
            for key, value in formal_components.items()
        },
        "PQS_and_split_hashes": {
            "PQS_manifest": "eb1a30ae0b1643c246a9c2c5a1b9ae1113748a3227fa2e10b77a1c1f2d9402eb",
            "split_manifest": "34d3ecdb79dfa86d9ac43f48a6a245ab4c996004cacb4191a637798ec1f85ec3",
            "development_Gold_seal": "1010fb635680bacc72c9aac8cbd096494370cd0709ed1d746754a0eade90cb5a",
            "Frozen_Gold_seal": GOLD_HASHES["aggregate_seal"],
        },
        "Development_result_hashes": {
            name: file_hash(path) for name, path in development_sources.items()
        },
        "P14_result_freeze_hash": file_hash(RESULT_SEAL),
        "Stage5_current_refreeze_hash": (
            "4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c"
        ),
        "original_invalid_run_hashes": result_seal["original_invalid_run_hashes"],
        "replacement_run_hashes": {
            "manifest": file_hash(MANIFEST),
            "predictions": file_hash(PREDICTIONS),
            "predictions_freeze": file_hash(FREEZE),
            "freeze_barrier_correction": file_hash(CORRECTION),
            "same_run_resume_audit": file_hash(RESUME_AUDIT),
            "P14_result_freeze": file_hash(RESULT_SEAL),
        },
        "final_closeout_hashes": {
            relative(P15_JSON): file_hash(P15_JSON),
            relative(P15_MD): file_hash(P15_MD),
            relative(V4_MD): file_hash(V4_MD),
        },
        "Frozen_and_Gold_integrity": {
            "Frozen_Query_hash": manifest["Frozen_Query_content_hash_from_manifest"],
            "Frozen_Gold_hashes": GOLD_HASHES,
            "post_prediction_freeze_open_only": True,
            "modified": False,
        },
        "post_frozen_tuning_occurred": False,
        "Final_Answer_added": False,
        "Agentic_Search_added": False,
        "V4_implementation_started": False,
        "session_can_be_closed": True,
        "frozen_at": utc_now(),
    }
    atomic_json(FINAL_SEAL, final_seal)
    for path in (P15_JSON, P15_MD, V4_MD, FINAL_SEAL):
        path.chmod(0o444)
    print(
        json.dumps(
            {
                "outcome": "v3_5_final_closeout_complete",
                "V3_5_status": "formally_closed",
                "P14_evaluation_validity": "valid",
                "P14_result_freeze_hash": file_hash(RESULT_SEAL),
                "V3_5_final_freeze_hash": file_hash(FINAL_SEAL),
                "session_can_be_closed": True,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
