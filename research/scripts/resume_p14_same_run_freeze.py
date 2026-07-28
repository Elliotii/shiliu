from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/v3_5/product_query_set_v1/p14_frozen_evaluation"
CASE_ROOT = OUT / "p14_replacement_cases"
TRACE_ROOT = OUT / "p14_replacement_traces"
MANIFEST = OUT / "P14_REPLACEMENT_FORMAL_RUN_MANIFEST.json"
ENTRY_GATE = OUT / "P14_REPLACEMENT_ENTRY_GATE.json"
PREFLIGHT = OUT / "P14_REPLACEMENT_SYNTHETIC_PREFLIGHT.json"
ENV_DELTA = OUT / "P14_REPLACEMENT_ENVIRONMENT_DELTA.json"
RESUME_LOG = OUT / "P14_REPLACEMENT_RESUME_AUDIT.jsonl"
PREDICTIONS = OUT / "p14_replacement_predictions.per_case.jsonl"
PREDICTION_FREEZE = OUT / "P14_REPLACEMENT_PREDICTIONS_FREEZE.json"
CORRECTION_JSON = OUT / "P14_FREEZE_BARRIER_CONTRACT_CORRECTION.json"
CORRECTION_MD = OUT / "P14_FREEZE_BARRIER_CONTRACT_CORRECTION.md"
AUDIT_JSON = OUT / "P14_SAME_RUN_RESUME_AUDIT.json"
AUDIT_MD = OUT / "P14_SAME_RUN_RESUME_AUDIT.md"
PRIOR_INVALID_REPORT = OUT / "P14_REPLACEMENT_INVALID_RUN_REPORT.json"
PRIOR_INVALID_SEAL = OUT / "P14_REPLACEMENT_INVALID_RUN_FREEZE_SEAL.json"
AUTHORIZATION = Path(
    "/Users/elliot/.codex/attachments/"
    "89921ef5-ae00-4a7f-86ca-9ec78e95df9f/pasted-text.txt"
)
RUN_ID = "P14_REPLACEMENT_FROZEN_EVALUATION_20260727T184443+0000"
SOURCE_COMMIT = "91a34061f8aebb216749c015a37a4ff1974f4f2a"
RUNTIME_SEAL_HASH = (
    "65ebb99d53c6025d63177e5c0c131ee35f7f5a987de0e42ec8db7ab79dc6dbb4"
)


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


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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


def artifact_payload_hash(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("artifact_hash", None)
    return stable_hash(payload)


def assert_no_output_collision() -> None:
    for path in (
        CORRECTION_JSON,
        CORRECTION_MD,
        AUDIT_JSON,
        AUDIT_MD,
        PREDICTION_FREEZE,
    ):
        if path.exists():
            raise RuntimeError(f"Same-run correction output collision: {path}")


def main() -> int:
    assert_no_output_collision()
    manifest = load_json(MANIFEST)
    gate = load_json(ENTRY_GATE)
    preflight = load_json(PREFLIGHT)
    environment = load_json(ENV_DELTA)
    prior_invalid = load_json(PRIOR_INVALID_REPORT)
    if manifest["replacement_run_id"] != RUN_ID:
        raise RuntimeError("Replacement Run ID changed")
    if manifest["replacement_run_id_creation_ordinal"] != 1:
        raise RuntimeError("Replacement Run ID is not the sole authorized ID")
    if gate["replacement_entry_gate"] != "pass" or preflight["status"] != "pass":
        raise RuntimeError("Replacement lineage is not valid")
    if environment["unauthorized_differences"]["count"] != 0:
        raise RuntimeError("Unauthorized environment delta exists")
    if prior_invalid["Frozen_Gold_opened"] is not False:
        raise RuntimeError("Frozen Gold was opened before same-run correction")
    if any(
        (OUT / name).exists()
        for name in (
            "P14_FROZEN_RETRIEVAL_METRICS.json",
            "P14_FROZEN_EVIDENCE_METRICS.json",
            "P14_FROZEN_MECHANICAL_GATE_METRICS.json",
            "P14_FROZEN_SUFFICIENCY_METRICS.json",
            "P14_FROZEN_UNIFIED_METRICS.json",
        )
    ):
        raise RuntimeError("Scoring artifact exists before Predictions Freeze")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if head != SOURCE_COMMIT or manifest["repository_source_commit"] != SOURCE_COMMIT:
        raise RuntimeError("Repository source commit changed")

    case_paths = sorted(CASE_ROOT.glob("*.json"))
    trace_paths = sorted(TRACE_ROOT.glob("*.json"))
    if len(case_paths) != 10 or len(trace_paths) != 10:
        raise RuntimeError("Expected exactly ten Case and Trace artifacts")
    cases = [load_json(path) for path in case_paths]
    case_ids = [str(case["case_id"]) for case in cases]
    if len(set(case_ids)) != 10:
        raise RuntimeError("Duplicate Case IDs")
    if any(
        case["replacement_run_id"] != RUN_ID
        or case["completion_status"] != "complete"
        or case["artifact_hash"] != artifact_payload_hash(case)
        for case in cases
    ):
        raise RuntimeError("Case artifact identity or hash invalid")
    trace_hashes_valid = all(
        file_hash(ROOT / case["trace_path"]) == case["trace_hash"]
        and load_json(ROOT / case["trace_path"]) == case["trace"]
        for case in cases
    )
    if not trace_hashes_valid:
        raise RuntimeError("Trace artifact hash or embedded trace mismatch")
    configuration_hashes = {case["configuration_hash"] for case in cases}
    if configuration_hashes != {manifest["configuration_hash"]}:
        raise RuntimeError("Configuration hash differs across existing Cases")

    expected_stable_components = {
        "retrieval": "v3-product-search-default-auto-v1",
        "auto_router": (
            "unversioned:SearchPlanner@sha256:"
            "0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e"
        ),
        "builder": "stage3b-acronym-w3.5-v1",
        "selector": "v3.5-deterministic-fine-selector-v1",
        "evidence_bundle": "v3.5-evidence-bundle-v1",
        "mechanical_gate": "mechanical-gate-v1-r1",
        "semantic_policy": "v3.5-semantic-sufficiency-policy-v1",
        "semantic_prompt": "v3.5-semantic-judge-prompt-v1",
    }
    stable_component_hashes = set()
    route_checks: dict[str, dict[str, Any]] = {}
    for case in cases:
        versions = dict(case["component_versions"])
        semantic_model = versions.pop("semantic_model")
        if versions != expected_stable_components:
            raise RuntimeError(f"Stable component version drift: {case['case_id']}")
        stable_component_hashes.add(stable_hash(versions))
        prediction = case["prediction"]
        gate_outcome = prediction["mechanical_gate_result"]["gate_outcome"]
        called = prediction["semantic_judge_called"]
        decision = prediction["sufficiency_decision_or_null"]
        if gate_outcome == "judge_eligible":
            valid = (
                called is True
                and semantic_model == "gpt-5.6-terra"
                and decision is not None
                and decision["semantic_judge_invoked"] is True
                and decision["judge_model"] == "gpt-5.6-terra"
            )
        elif gate_outcome == "source_unverifiable":
            valid = (
                called is False
                and semantic_model is None
                and decision is not None
                and decision["semantic_judge_invoked"] is False
                and decision["judge_model"] is None
            )
        elif gate_outcome == "invalid":
            valid = called is False and semantic_model is None and decision is None
        else:
            valid = False
        if not valid:
            raise RuntimeError(f"Route/Judge inconsistency: {case['case_id']}")
        route_checks[str(case["case_id"])] = {
            "gate_outcome": gate_outcome,
            "semantic_judge_called": called,
            "semantic_model": semantic_model,
            "sufficiency_decision_present": decision is not None,
            "routing_consistency_valid": valid,
        }
    if len(stable_component_hashes) != 1:
        raise RuntimeError("Stable component fields differ across Cases")

    required_global = {
        "replacement_run_id": manifest["replacement_run_id"] == RUN_ID,
        "repository_source_commit": head == SOURCE_COMMIT,
        "configuration_hash": len(configuration_hashes) == 1,
        "retrieval_version": all(
            case["component_versions"]["retrieval"]
            == expected_stable_components["retrieval"]
            for case in cases
        ),
        "auto_router_version": all(
            case["component_versions"]["auto_router"]
            == expected_stable_components["auto_router"]
            for case in cases
        ),
        "builder_version": (
            manifest["formal_component_hashes"]["builder_version"]
            == expected_stable_components["builder"]
        ),
        "selector_version": (
            manifest["formal_component_hashes"]["selector_version"]
            == expected_stable_components["selector"]
        ),
        "Evidence_Identity_Contract_version_and_hash": (
            manifest["formal_component_hashes"]["Evidence_Identity_Contract_hash"]
            == "35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7"
        ),
        "mechanical_gate_version": (
            manifest["formal_component_hashes"]["mechanical_gate_version"]
            == expected_stable_components["mechanical_gate"]
        ),
        "semantic_judge_provider": (
            manifest["formal_component_hashes"]["semantic_judge_provider"]
            == "openai-codex-cli"
        ),
        "semantic_judge_prompt_hash": (
            manifest["semantic_judge_hashes"]["prompt"]
            == "4d87dd06ab3362ae7ffdeae2b4d82e2accc0d10db8dd69cdeb3928f9000f898c"
        ),
        "semantic_judge_policy": (
            manifest["semantic_judge_hashes"]["policy"]
            == "v3.5-semantic-sufficiency-policy-v1"
        ),
        "semantic_judge_temperature": (
            manifest["semantic_judge_hashes"]["temperature"] == 0
        ),
        "input_schema_hash": (
            manifest["schema_hashes"]["Evidence_Identity_Contract_V1"]
            == "35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7"
        ),
        "output_schema_hash": (
            manifest["schema_hashes"]["semantic_judge_batch_output"]
            == "1b04bd32b0820abd3f1c109c63a0d61b2b0d45b737082b856cad67813070977c"
        ),
        "runtime_seal_hash": manifest["runtime_seal_hash"] == RUNTIME_SEAL_HASH,
    }
    if not all(required_global.values()):
        raise RuntimeError("A required globally stable field changed")

    prediction_rows = load_jsonl(PREDICTIONS)
    if len(prediction_rows) != 10:
        raise RuntimeError("Existing predictions JSONL is not exactly ten rows")
    artifacts_by_id = {case["case_id"]: case for case in cases}
    prediction_ids = [str(row["case_id"]) for row in prediction_rows]
    if (
        len(set(prediction_ids)) != 10
        or set(prediction_ids) != set(artifacts_by_id)
        or any(row != artifacts_by_id[str(row["case_id"])]["prediction"] for row in prediction_rows)
    ):
        raise RuntimeError("Existing predictions JSONL differs from Case artifacts")

    correction = {
        "schema_version": "v3.5-b-p14-freeze-barrier-contract-correction-v1",
        "replacement_run_id": RUN_ID,
        "correction_scope": "orchestration_validation_only",
        "prior_failure_class": "orchestration_contract_invalid",
        "prior_failure_stage": "predictions_freeze_barrier",
        "corrected_contract": {
            "must_be_identical_across_all_cases": list(required_global),
            "allowed_route_dependent_field": "semantic_model",
            "judge_called_required_value": "gpt-5.6-terra",
            "judge_not_called_required_value": None,
        },
        "stable_field_checks": required_global,
        "stable_component_versions_identical": True,
        "route_dependent_semantic_model_values_valid": True,
        "route_and_judge_call_consistent": True,
        "per_case_routing_checks": route_checks,
        "prediction_recomputation": False,
        "provider_recall": False,
        "artifact_modification": False,
        "new_run_id_created": False,
        "Frozen_Gold_opened_during_correction": False,
        "authorization": {
            "path": str(AUTHORIZATION),
            "sha256": file_hash(AUTHORIZATION),
        },
        "created_at": utc_now(),
    }
    atomic_json(CORRECTION_JSON, correction)
    correction_md = """# P14 Freeze Barrier Contract Correction

## Scope

`correction_scope: orchestration_validation_only`

The prior validator incorrectly required every complete `component_versions`
object to be identical. The corrected barrier compares all stable formal
configuration fields globally and validates `semantic_model` against the
Mechanical Gate route:

- Judge called: `semantic_model: gpt-5.6-terra`.
- Judge not called: `semantic_model: null`.

All ten existing Case and Trace artifacts validate. No Retrieval, Builder,
Selector, Mechanical Gate, Semantic Judge, Prediction, EvidenceBundle,
SufficiencyDecision, Case, or Trace was rerun or modified. Frozen Gold remained
closed during correction.
"""
    atomic_write(CORRECTION_MD, correction_md.encode("utf-8"))

    audit = {
        "schema_version": "v3.5-b-p14-same-run-resume-audit-v1",
        "replacement_run_id": RUN_ID,
        "same_replacement_run_id_reused": True,
        "new_run_id_created": False,
        "existing_case_artifacts_reused": 10,
        "existing_trace_artifacts_reused": 10,
        "case_recomputation": False,
        "provider_recall": False,
        "prediction_modification": False,
        "artifact_modification": False,
        "Frozen_Gold_opened": False,
        "prior_invalid_barrier_report_hash": file_hash(PRIOR_INVALID_REPORT),
        "prior_invalid_barrier_seal_hash": file_hash(PRIOR_INVALID_SEAL),
        "original_resume_log_hash": file_hash(RESUME_LOG),
        "authorization_hash": file_hash(AUTHORIZATION),
        "configuration_hash": manifest["configuration_hash"],
        "case_file_hashes_before_resume": {
            relative(path): file_hash(path) for path in case_paths
        },
        "trace_file_hashes_before_resume": {
            relative(path): file_hash(path) for path in trace_paths
        },
        "recorded_at": utc_now(),
    }
    atomic_json(AUDIT_JSON, audit)
    audit_md = f"""# P14 Same-Run Resume Audit

- Replacement run ID reused: `{RUN_ID}`
- New run ID created: `false`
- Existing Case artifacts reused: `10`
- Existing Trace artifacts reused: `10`
- Case recomputation: `false`
- Provider recall: `false`
- Prediction modification: `false`
- Artifact modification: `false`
- Frozen Gold opened: `false`

Resume authority: `{file_hash(AUTHORIZATION)}`.
"""
    atomic_write(AUDIT_MD, audit_md.encode("utf-8"))

    freeze_barrier = {
        "completed_cases": 10,
        "completed_traces": 10,
        "duplicate_cases": 0,
        "missing_cases": 0,
        "artifact_hashes_valid": True,
        "trace_hashes_valid": True,
        "configuration_hash_identical": True,
        "stable_component_versions_identical": True,
        "route_dependent_semantic_model_values_valid": True,
        "route_and_judge_call_consistent": True,
        "Frozen_Gold_opened": False,
    }
    if not all(
        value is True or value == 0
        for key, value in freeze_barrier.items()
        if key not in {"completed_cases", "completed_traces"}
    ):
        raise RuntimeError("Corrected Predictions Freeze barrier failed")
    freeze = {
        "schema_version": "v3.5-b-p14-replacement-predictions-freeze-v2",
        "replacement_run_id": RUN_ID,
        "parent_invalid_run_id": manifest["parent_invalid_run_id"],
        "case_count": 10,
        "per_case_artifact_hashes": {
            relative(path): file_hash(path) for path in case_paths
        },
        "per_case_trace_hashes": {
            relative(path): file_hash(path) for path in trace_paths
        },
        "trace_hashes": {
            relative(path): file_hash(path) for path in trace_paths
        },
        "aggregate_prediction_hash": file_hash(PREDICTIONS),
        "configuration_hash": manifest["configuration_hash"],
        "formal_component_hashes": manifest["formal_component_hashes"],
        "component_hashes": manifest["formal_component_hashes"],
        "runtime_seal_hash": manifest["runtime_seal_hash"],
        "runtime_asset_hashes": gate["runtime_preflight"]["verified_hashes"],
        "formal_run_manifest_hash": file_hash(MANIFEST),
        "freeze_barrier_contract_correction_hash": file_hash(CORRECTION_JSON),
        "same_run_resume_audit_hash": file_hash(AUDIT_JSON),
        "freeze_barrier": freeze_barrier,
        "formal_prediction_run_count": 1,
        "case_recomputation": False,
        "provider_recall": False,
        "prediction_modification": False,
        "Frozen_Query_opened": True,
        "Frozen_Gold_opened": False,
        "predictions_frozen_at": utc_now(),
        "immutable_after_freeze": True,
    }
    atomic_json(PREDICTION_FREEZE, freeze)
    for path in (
        CORRECTION_JSON,
        CORRECTION_MD,
        AUDIT_JSON,
        AUDIT_MD,
        PREDICTION_FREEZE,
    ):
        path.chmod(0o444)
    print(json.dumps(freeze, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
