from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/v3_5/product_query_set_v1/p14_frozen_evaluation"
CASE_ROOT = OUT / "p14_replacement_cases"
TRACE_ROOT = OUT / "p14_replacement_traces"
MANIFEST = OUT / "P14_REPLACEMENT_FORMAL_RUN_MANIFEST.json"
GATE = OUT / "P14_REPLACEMENT_ENTRY_GATE.json"
PREFLIGHT = OUT / "P14_REPLACEMENT_SYNTHETIC_PREFLIGHT.json"
ENV_DELTA = OUT / "P14_REPLACEMENT_ENVIRONMENT_DELTA.json"
PREDICTIONS = OUT / "p14_replacement_predictions.per_case.jsonl"
PREDICTION_FREEZE = OUT / "P14_REPLACEMENT_PREDICTIONS_FREEZE.json"
RESUME_AUDIT = OUT / "P14_REPLACEMENT_RESUME_AUDIT.jsonl"
REPORT_JSON = OUT / "P14_REPLACEMENT_INVALID_RUN_REPORT.json"
REPORT_MD = OUT / "P14_REPLACEMENT_INVALID_RUN_REPORT.md"
INVALID_SEAL = OUT / "P14_REPLACEMENT_INVALID_RUN_FREEZE_SEAL.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def stable_hash(value: object) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def atomic_write(path: Path, data: bytes) -> None:
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


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_payload_hash(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("artifact_hash", None)
    return stable_hash(payload)


def main() -> int:
    if REPORT_JSON.exists() or REPORT_MD.exists() or INVALID_SEAL.exists():
        raise RuntimeError("Invalid Replacement Run freeze output collision")
    metric_paths = [
        OUT / "P14_FROZEN_RETRIEVAL_METRICS.json",
        OUT / "P14_FROZEN_EVIDENCE_METRICS.json",
        OUT / "P14_FROZEN_MECHANICAL_GATE_METRICS.json",
        OUT / "P14_FROZEN_SUFFICIENCY_METRICS.json",
        OUT / "P14_FROZEN_UNIFIED_METRICS.json",
    ]
    if PREDICTION_FREEZE.exists() or any(path.exists() for path in metric_paths):
        raise RuntimeError("Invalid-run facts conflict with Freeze or scoring outputs")
    manifest = load_json(MANIFEST)
    case_paths = sorted(CASE_ROOT.glob("*.json"))
    trace_paths = sorted(TRACE_ROOT.glob("*.json"))
    if len(case_paths) != 10 or len(trace_paths) != 10:
        raise RuntimeError("Expected ten preserved Case and Trace artifacts")
    cases = [load_json(path) for path in case_paths]
    artifact_hashes_valid = all(
        case.get("completion_status") == "complete"
        and case.get("artifact_hash") == artifact_payload_hash(case)
        and file_hash(ROOT / case["trace_path"]) == case["trace_hash"]
        for case in cases
    )
    if not artifact_hashes_valid:
        raise RuntimeError("Preserved Case/Trace artifact integrity failed")
    configuration_hashes = {case["configuration_hash"] for case in cases}
    if configuration_hashes != {manifest["configuration_hash"]}:
        raise RuntimeError("Case configuration hash drift is not the observed failure")
    component_hashes = {
        stable_hash(case["component_versions"]) for case in cases
    }
    normalized_component_hashes = set()
    semantic_model_values = set()
    for case in cases:
        versions = dict(case["component_versions"])
        semantic_model_values.add(versions.pop("semantic_model"))
        normalized_component_hashes.add(stable_hash(versions))
    if len(component_hashes) != 2 or len(normalized_component_hashes) != 1:
        raise RuntimeError("Observed component-version assertion has changed")
    original_expected = {
        "manifest": "83c7265c32e86fb4b311e604be1545c55a05627817ea265b5c8d97fc46bc2101",
        "invalid_run_seal": "f61bb37a04daaf298e0f3c970231a4b10ff87abd3b63b35348b45bfb8d8ae57c",
        "invalid_report_json": "dabc251742dae3bf76b95a947f8c4eda52019f98b673187db53b59abcd88cad2",
        "invalid_report_md": "fe73786a332e6cccb621a817856af39627d435049095eeb1aafc3a7ad9a74266",
        "provider_failure_log": "4a88086eb1f452631401a1b8bcce141d16730a172b4671242db115a840c49df6",
        "original_result_json": "a2f1189e4487bbe301a3ef398137a07d0b21b126e1eb362f411d78081934e798",
        "original_result_md": "abb80dbb73228b6ec65a5e0870675c64776103120dcfb67bda186f2b102436b2",
    }
    gate = load_json(GATE)
    for key, expected in original_expected.items():
        actual = (
            gate["original_invalid_run"]["manifest_hash"]
            if key == "manifest"
            else gate["original_invalid_run"]["invalid_run_seal_hash"]
            if key == "invalid_run_seal"
            else gate["original_invalid_run"]["logs_hashes"][key]
        )
        if actual != expected:
            raise RuntimeError(f"Original invalid-run lineage changed: {key}")
    case_file_hashes = {relative(path): file_hash(path) for path in case_paths}
    trace_file_hashes = {relative(path): file_hash(path) for path in trace_paths}
    report = {
        "schema_version": "v3.5-b-p14-replacement-invalid-run-report-v1",
        "outcome": "p14_replacement_run_blocked_or_invalid",
        "status": "blocked_pending_main_session",
        "replacement_run_id": manifest["replacement_run_id"],
        "parent_invalid_run_id": manifest["parent_invalid_run_id"],
        "replacement_run_started": True,
        "new_run_id_created": True,
        "new_run_id_creation_ordinal": 1,
        "maximum_new_run_ids": 1,
        "formal_prediction_run_count": 1,
        "replacement_predictions_completed_in_atomic_artifacts": 10,
        "predictions_freeze_generated": False,
        "Frozen_Query_reopened": True,
        "Frozen_Gold_opened": False,
        "scoring_performed": False,
        "P15_started": False,
        "failure_stage": "predictions_freeze_barrier",
        "failure_class": "orchestration_contract_invalid",
        "failure": {
            "error_type": "RuntimeError",
            "message": "Replacement Case configuration/component drift",
            "root_cause": (
                "The orchestration-only wrapper compared the complete "
                "per-Case component_versions objects. The frozen prediction "
                "summary records semantic_model as null when the mechanical "
                "gate does not invoke the Judge and as gpt-5.6-terra when it "
                "does; therefore two object hashes were observed even though "
                "the frozen formal configuration hash was constant."
            ),
            "semantic_model_values_observed": sorted(
                semantic_model_values, key=lambda value: str(value)
            ),
            "full_component_version_hash_count": len(component_hashes),
            "component_version_hash_count_excluding_conditional_semantic_model": (
                len(normalized_component_hashes)
            ),
        },
        "mechanical_audit": {
            "completed_case_count": len(case_paths),
            "trace_count": len(trace_paths),
            "all_completion_status_complete": True,
            "all_artifact_hashes_valid": artifact_hashes_valid,
            "all_trace_hashes_valid": artifact_hashes_valid,
            "configuration_hash_constant": True,
            "formal_component_manifest_unchanged": True,
            "completed_cases_recomputed": False,
            "predictions_jsonl_exists_but_is_not_frozen": PREDICTIONS.exists(),
            "predictions_freeze_exists": False,
            "frozen_metrics_exist": False,
        },
        "evaluation_validity": {
            "main_session_authorization_valid": True,
            "original_invalid_run_preserved": True,
            "replacement_run_id_unique": True,
            "synthetic_preflight_passed": True,
            "entry_gate_passed": True,
            "only_authorized_environment_delta_present": True,
            "repository_source_commit_unchanged": True,
            "component_and_policy_hashes_unchanged": True,
            "case_count_is_ten": True,
            "predictions_freeze_valid": False,
            "completed_cases_not_recomputed": True,
            "configuration_hash_constant": True,
            "Frozen_Gold_opened_only_after_freeze": True,
            "scorer_and_projection_valid": "not_reached",
            "overall": "invalid",
        },
        "governance_disposition": {
            "replacement_rerun_performed": False,
            "same_id_resume_after_deterministic_freeze_barrier_failure_performed": False,
            "completed_case_modified": False,
            "wrapper_modified_after_manifest": False,
            "Gold_opened_for_diagnosis": False,
            "rerun_authorized": False,
            "required_action": "stop_and_escalate_to_main_session",
        },
        "lineage_hashes": {
            "authorization": gate["main_session_authorization"]["sha256"],
            "environment_delta": file_hash(ENV_DELTA),
            "synthetic_preflight": file_hash(PREFLIGHT),
            "replacement_entry_gate": file_hash(GATE),
            "replacement_manifest": file_hash(MANIFEST),
            "resume_audit": file_hash(RESUME_AUDIT),
            "unfrozen_predictions_jsonl": file_hash(PREDICTIONS),
        },
        "case_file_hashes": case_file_hashes,
        "trace_file_hashes": trace_file_hashes,
        "original_invalid_run_hashes": original_expected,
        "created_at": utc_now(),
    }
    atomic_json(REPORT_JSON, report)
    markdown = f"""# P14 Replacement Invalid Run Report

## Outcome

- Outcome: `p14_replacement_run_blocked_or_invalid`
- Status: `blocked_pending_main_session`
- Replacement run ID: `{manifest['replacement_run_id']}`
- Failure class: `orchestration_contract_invalid`
- Failure stage: `predictions_freeze_barrier`
- Replacement formal prediction run count: `1`
- Completed atomic Case/Trace artifacts: `10` / `10`
- Predictions Freeze generated: `false`
- Frozen Gold opened: `false`
- Scoring performed: `false`
- P15 started: `false`
- Rerun authorized: `false`

## Mechanical cause

The frozen pipeline completed and atomically persisted all ten Case and Trace
artifacts. Before Predictions Freeze, the orchestration-only wrapper rejected
the set because it compared each complete `component_versions` object. The
frozen prediction summary intentionally records `semantic_model: null` when
the Mechanical Gate does not call the Judge and `semantic_model:
gpt-5.6-terra` when it does. The formal configuration hash remained identical
for all ten Cases, and every Case/Trace hash validates.

This failure is not an algorithm-quality result. No Case was recomputed or
modified; no wrapper repair or same-ID resume was attempted after the
deterministic Freeze-barrier failure. Frozen Gold remained closed, no scorer
ran, and P15 did not start.

## Required disposition

Stop and escalate to the main Session. A rerun is not authorized by this
Session.
"""
    atomic_write(REPORT_MD, markdown.encode("utf-8"))
    seal = {
        "schema_version": "v3.5-b-p14-replacement-invalid-run-freeze-seal-v1",
        "outcome": report["outcome"],
        "status": report["status"],
        "replacement_run_id": manifest["replacement_run_id"],
        "parent_invalid_run_id": manifest["parent_invalid_run_id"],
        "replacement_manifest_hash": file_hash(MANIFEST),
        "invalid_run_report_hashes": {
            relative(REPORT_JSON): file_hash(REPORT_JSON),
            relative(REPORT_MD): file_hash(REPORT_MD),
        },
        "case_file_hashes": case_file_hashes,
        "trace_file_hashes": trace_file_hashes,
        "unfrozen_predictions_jsonl_hash": file_hash(PREDICTIONS),
        "resume_audit_hash": file_hash(RESUME_AUDIT),
        "predictions_freeze_exists": False,
        "Frozen_Gold_opened": False,
        "scoring_performed": False,
        "P15_started": False,
        "rerun_authorized": False,
        "frozen_at": utc_now(),
    }
    atomic_json(INVALID_SEAL, seal)
    preserved_paths = [
        *case_paths,
        *trace_paths,
        PREDICTIONS,
        RESUME_AUDIT,
        OUT / "p14_replacement_work/semantic_judge_batch.validated.json",
        REPORT_JSON,
        REPORT_MD,
        INVALID_SEAL,
    ]
    for path in preserved_paths:
        if path.exists():
            path.chmod(0o444)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
