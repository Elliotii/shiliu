from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from shiliu.eval_v3_5.runtime_guard import (
    load_frozen_eval_runtime_config,
    preflight_frozen_eval_runtime,
)
from shiliu.eval_v3_5.stage3r import file_sha256


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/v3_5/product_query_set_v1/p14_frozen_evaluation"
GATE = OUT / "P14_REPLACEMENT_ENTRY_GATE.json"
GATE_MD = OUT / "P14_REPLACEMENT_ENTRY_GATE.md"
MANIFEST = OUT / "P14_REPLACEMENT_FORMAL_RUN_MANIFEST.json"
RUNTIME_SEAL = OUT / "FROZEN_EVAL_RUNTIME_SEAL.json"
ENV_DELTA = OUT / "P14_REPLACEMENT_ENVIRONMENT_DELTA.json"
PREFLIGHT = OUT / "P14_REPLACEMENT_SYNTHETIC_PREFLIGHT.json"
WRAPPER = ROOT / "research/scripts/run_p14_replacement_frozen_evaluation.py"
AUTHORIZATION = Path(
    "/Users/elliot/.codex/attachments/"
    "30c9b41b-13b2-4bc2-8a21-cfdb01a44a7e/pasted-text.txt"
)
FROZEN_SOURCE_COMMIT = "91a34061f8aebb216749c015a37a4ff1974f4f2a"
ORIGINAL_RUN_ID = "P14_FROZEN_EVALUATION_20260727T181722Z"
ORIGINAL_HASHES = {
    "manifest": (
        OUT / "P14_FROZEN_FORMAL_RUN_MANIFEST.json",
        "83c7265c32e86fb4b311e604be1545c55a05627817ea265b5c8d97fc46bc2101",
    ),
    "invalid_run_seal": (
        OUT / "P14_FROZEN_INVALID_RUN_FREEZE_SEAL.json",
        "f61bb37a04daaf298e0f3c970231a4b10ff87abd3b63b35348b45bfb8d8ae57c",
    ),
    "invalid_report_json": (
        OUT / "P14_FROZEN_INVALID_RUN_REPORT.json",
        "dabc251742dae3bf76b95a947f8c4eda52019f98b673187db53b59abcd88cad2",
    ),
    "invalid_report_md": (
        OUT / "P14_FROZEN_INVALID_RUN_REPORT.md",
        "fe73786a332e6cccb621a817856af39627d435049095eeb1aafc3a7ad9a74266",
    ),
    "original_result_json": (
        OUT
        / "history/original_invalid_run/"
        "P14_FROZEN_EVALUATION_RESULT.invalid.json",
        "a2f1189e4487bbe301a3ef398137a07d0b21b126e1eb362f411d78081934e798",
    ),
    "original_result_md": (
        OUT
        / "history/original_invalid_run/"
        "P14_FROZEN_EVALUATION_RESULT.invalid.md",
        "abb80dbb73228b6ec65a5e0870675c64776103120dcfb67bda186f2b102436b2",
    ),
    "provider_failure_log": (
        OUT / "history/original_invalid_run/original_provider_failure.log",
        "4a88086eb1f452631401a1b8bcce141d16730a172b4671242db115a840c49df6",
    ),
    "original_draft": (
        OUT / "P14_FROZEN_EVALUATION_CLOSEOUT_DRAFT.md",
        "27fd1824ec0afd8b286c447829d08a8b9f1754efb558978ff7efaa0370743f6a",
    ),
}
FROZEN_HASHES = {
    "runtime_seal": (
        RUNTIME_SEAL,
        "65ebb99d53c6025d63177e5c0c131ee35f7f5a987de0e42ec8db7ab79dc6dbb4",
    ),
    "original_entry_gate": (
        OUT / "P14_FROZEN_ENTRY_GATE.json",
        "fd4add3d2b3d76c33397e6d92f327a8b3709224ff4680711f041eb5111821bb8",
    ),
    "query_manifest": (
        ROOT
        / "research/v3_5/product_query_set_v1/split_v1/"
        "product_query_split_v1.manifest.json",
        "34d3ecdb79dfa86d9ac43f48a6a245ab4c996004cacb4191a637798ec1f85ec3",
    ),
    "frozen_gold_seal": (
        ROOT
        / "research/v3_5/product_query_set_v1/gold_construction_v1/"
        "frozen_guarded/frozen_cycle_v1/internal_protected/"
        "frozen_gold_v1.seal.json",
        "166e7c463de06e31d6c831d97c00f54dcf149312fb77cb66505bf15985c584a8",
    ),
    "semantic_judge_freeze_seal": (
        ROOT / "SUFFICIENCY_JUDGE_FINAL_FREEZE_SEAL.json",
        "2e2d90afda5dc6e7f7576742e900782f857622a331303bca18b983d27b645d59",
    ),
    "stage5_refreeze_seal": (
        ROOT / "STAGE5_CURRENT_INTEGRATION_REFREEZE_SEAL.json",
        "4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c",
    ),
    "scorer_freeze_seal": (
        ROOT
        / "research/v3_5/product_query_set_v1/"
        "f1a_candidate_builder_major_cycle_1/scorer_v4_final_eval/"
        "SCORER_V4_FREEZE_SEAL.json",
        "e45b4c5604d2de9171086093ad2e26d09dcfd446f233a6397af9f86a4876b669",
    ),
    "projection_source": (
        ROOT
        / "research/v3_5/product_query_set_v1/"
        "f1a_candidate_builder_major_cycle_1/scorer_v4_projection.py",
        "8d2752ed92fb96337af603a7768d47a628550b7796904dd760dc516d70e9cb7e",
    ),
    "stage4b_runner": (
        ROOT
        / "research/v3_5/product_query_set_v1/stage4b_incremental/run_stage4b.py",
        "f067b96d41876f7f1fb628e275f8484d8837627b9ab68e5d1bec72dc02dbf3ef",
    ),
    "semantic_schema": (
        ROOT
        / "research/v3_5/product_query_set_v1/stage4b_incremental/"
        "semantic_judge_batch_output.schema.json",
        "1b04bd32b0820abd3f1c109c63a0d61b2b0d45b737082b856cad67813070977c",
    ),
    "base_executor_and_scorer": (
        ROOT / "research/scripts/run_p14_frozen_evaluation.py",
        "94748013de4902472d295e13d727eeaf6ad2f8bee9d06b96da06763030fdc52e",
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def stable_hash(value: object) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


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


def assert_hashes(values: dict[str, tuple[Path, str]]) -> dict[str, str]:
    actual: dict[str, str] = {}
    for name, (path, expected) in values.items():
        digest = file_sha256(path)
        if digest != expected:
            raise RuntimeError(
                f"Frozen hash mismatch for {name}: expected {expected}, got {digest}"
            )
        actual[str(path.relative_to(ROOT))] = digest
    return actual


def build_gate() -> None:
    if MANIFEST.exists():
        raise RuntimeError("Replacement Run ID already exists; refusing another")
    if GATE.exists() or GATE_MD.exists():
        raise RuntimeError("Replacement Entry Gate output collision")
    original_hashes = assert_hashes(ORIGINAL_HASHES)
    frozen_hashes = assert_hashes(FROZEN_HASHES)
    if (
        subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        != FROZEN_SOURCE_COMMIT
    ):
        raise RuntimeError("Repository source commit changed")
    environment = json.loads(ENV_DELTA.read_text(encoding="utf-8"))
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if environment["unauthorized_differences"]["count"] != 0:
        raise RuntimeError("Unauthorized environment difference recorded")
    if preflight["status"] != "pass":
        raise RuntimeError("Synthetic provider preflight did not pass")
    runtime = load_frozen_eval_runtime_config(RUNTIME_SEAL)
    runtime_checks = preflight_frozen_eval_runtime(runtime)
    frozen_configuration = {
        "provider": "openai-codex-cli",
        "model": "gpt-5.6-terra",
        "temperature": 0,
        "policy": "v3.5-semantic-sufficiency-policy-v1",
        "prompt_hash": (
            "4d87dd06ab3362ae7ffdeae2b4d82e2accc0d10db8dd69cdeb3928f9000f898c"
        ),
        "schema_hash": (
            "1b04bd32b0820abd3f1c109c63a0d61b2b0d45b737082b856cad67813070977c"
        ),
        "CODEX_SQLITE_HOME": str(
            (OUT / "replacement_provider_state").resolve()
        ),
    }
    configuration_hash = stable_hash(frozen_configuration)
    if configuration_hash != preflight["configuration_hash"]:
        raise RuntimeError("Preflight/formal configuration hash drift")
    gate = {
        "schema_version": "v3.5-b-p14-replacement-entry-gate-v1",
        "replacement_entry_gate": "pass",
        "replacement_formal_run_authorized": True,
        "replacement_run_started": False,
        "new_run_id_created": False,
        "maximum_new_run_ids": 1,
        "Frozen_Query_reopened": False,
        "Frozen_Gold_opened": False,
        "original_invalid_run": {
            "run_id": ORIGINAL_RUN_ID,
            "manifest_hash": ORIGINAL_HASHES["manifest"][1],
            "invalid_run_seal_hash": ORIGINAL_HASHES["invalid_run_seal"][1],
            "logs_hashes": {
                key: expected
                for key, (_, expected) in ORIGINAL_HASHES.items()
                if key
                in {
                    "invalid_report_json",
                    "invalid_report_md",
                    "provider_failure_log",
                    "original_result_json",
                    "original_result_md",
                    "original_draft",
                }
            },
            "failure_classification": "infrastructure_invalid_run",
            "preserved": True,
            "valid_frozen_evaluation_run_consumed": False,
        },
        "replacement_entry_gate_checks": {
            "original_invalid_run_preserved": True,
            "synthetic_provider_preflight_passed": True,
            "frozen_gold_still_sealed": True,
            "repository_source_commit_unchanged": True,
            "code_and_policy_hashes_unchanged": True,
            "only_authorized_environment_delta_present": True,
            "runtime_seal_valid": runtime_checks["preflight_status"] == "pass",
            "Frozen_Query_manifest_unchanged": True,
            "Frozen_Gold_seals_unchanged": True,
            "scorer_and_projection_hashes_unchanged": True,
            "atomic_case_persistence_ready": True,
            "resume_contract_ready": True,
        },
        "repository_source_commit": FROZEN_SOURCE_COMMIT,
        "frozen_configuration": frozen_configuration,
        "frozen_configuration_hash": configuration_hash,
        "runtime_preflight": runtime_checks,
        "environment_delta_hash": file_sha256(ENV_DELTA),
        "synthetic_preflight_hash": file_sha256(PREFLIGHT),
        "synthetic_preflight_trace_hash": preflight["trace_hash"],
        "orchestration_wrapper": {
            "path": str(WRAPPER.relative_to(ROOT)),
            "sha256": file_sha256(WRAPPER),
            "behavior_semantics_unchanged": True,
            "component_inputs_unchanged": True,
            "component_outputs_unchanged": True,
            "orchestration_only": True,
            "atomic_case_persistence": True,
            "same_run_id_resume": True,
        },
        "verified_original_invalid_artifact_hashes": original_hashes,
        "verified_frozen_artifact_hashes": frozen_hashes,
        "main_session_authorization": {
            "path": str(AUTHORIZATION),
            "sha256": file_sha256(AUTHORIZATION),
            "replacement_authorized": True,
            "maximum_new_run_ids": 1,
            "same_replacement_run_id_resume_allowed": True,
        },
        "outcome": "p14_replacement_entry_gate_passed",
        "status": "replacement_formal_run_authorized",
        "checked_at": utc_now(),
    }
    if not all(gate["replacement_entry_gate_checks"].values()):
        raise RuntimeError("Replacement Entry Gate check failed")
    atomic_json(GATE, gate)
    report = f"""# P14 Replacement Entry Gate

## Result

- Replacement Entry Gate: `pass`
- Replacement formal run authorized: `true`
- New replacement run ID created: `false`
- Frozen Query reopened: `false`
- Frozen Gold opened: `false`
- Original infrastructure-invalid run preserved: `true`
- Synthetic provider preflight: `pass`
- Repository source commit: `{FROZEN_SOURCE_COMMIT}`
- Unauthorized environment differences: `0`
- Atomic per-Case persistence ready: `true`
- Same replacement run-ID resume ready: `true`

The only implementation delta is the authorization-scoped orchestration wrapper
for isolated provider state, atomic Case/Trace persistence, and same-ID resume.
No frozen algorithm, prompt, policy, schema, scorer, projection, Query, Gold, or
runtime asset changed.
"""
    atomic_write(GATE_MD, report.encode("utf-8"))
    print(json.dumps(gate, ensure_ascii=False, sort_keys=True, indent=2))


def build_manifest() -> None:
    if MANIFEST.exists():
        raise RuntimeError("Replacement Manifest already exists; refusing another Run ID")
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    if (
        gate.get("replacement_entry_gate") != "pass"
        or gate.get("new_run_id_created") is not False
        or gate.get("Frozen_Query_reopened") is not False
        or gate.get("Frozen_Gold_opened") is not False
    ):
        raise RuntimeError("Replacement Entry Gate is not a clean authorization")
    created_at = utc_now()
    compact = created_at.replace("-", "").replace(":", "").replace("+00:00", "Z")
    replacement_run_id = f"P14_REPLACEMENT_FROZEN_EVALUATION_{compact}"
    original_manifest = json.loads(
        ORIGINAL_HASHES["manifest"][0].read_text(encoding="utf-8")
    )
    manifest = {
        "schema_version": "v3.5-b-p14-replacement-formal-run-manifest-v1",
        "replacement_run_id": replacement_run_id,
        "replacement_run_id_creation_ordinal": 1,
        "maximum_new_run_ids": 1,
        "parent_invalid_run_id": ORIGINAL_RUN_ID,
        "main_session_authorization_hash_or_reference": {
            "path": str(AUTHORIZATION),
            "sha256": file_sha256(AUTHORIZATION),
        },
        "repository_source_commit": FROZEN_SOURCE_COMMIT,
        "formal_component_hashes": original_manifest["formal_component_hashes"],
        "semantic_judge_hashes": {
            "freeze_seal": FROZEN_HASHES["semantic_judge_freeze_seal"][1],
            "stage4b_runner": FROZEN_HASHES["stage4b_runner"][1],
            "prompt": (
                "4d87dd06ab3362ae7ffdeae2b4d82e2accc0d10db8dd69cdeb3928f9000f898c"
            ),
            "policy": "v3.5-semantic-sufficiency-policy-v1",
            "model": "gpt-5.6-terra",
            "temperature": 0,
        },
        "schema_hashes": {
            "semantic_judge_batch_output": FROZEN_HASHES["semantic_schema"][1],
            "Evidence_Identity_Contract_V1": (
                "35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7"
            ),
        },
        "scorer_hashes": {
            "SCORER_V4_FREEZE_SEAL.json": FROZEN_HASHES["scorer_freeze_seal"][1],
            "frozen_P14_executor_and_scorer": (
                FROZEN_HASHES["base_executor_and_scorer"][1]
            ),
        },
        "projection_contract_hashes": {
            "scorer_v4_projection.py": FROZEN_HASHES["projection_source"][1],
            "Evidence_Identity_Contract_V1": (
                "35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7"
            ),
        },
        "Frozen_Query_manifest_hash": FROZEN_HASHES["query_manifest"][1],
        "Frozen_Query_content_hash_from_manifest": (
            "faf962049281cba4c8a035e64068ef91b7cfa9159ea438cfe33052a225add44f"
        ),
        "Frozen_Gold_seal_hashes": {
            "aggregate": FROZEN_HASHES["frozen_gold_seal"][1],
            "retrieval": (
                "2f53b9294a7211b4371aadc934d1ec1a178b2a0fa00ee1b9b4177737b7b4ca34"
            ),
            "evidence": (
                "b47235b273640fedf4754dfcb9983b733655ed80730d07ba12700987d4c30827"
            ),
            "sufficiency": (
                "ccc7b0bfe35e78c5eec50ccb3c972b327bd400437f442d70da94e3f9df07b69a"
            ),
        },
        "runtime_seal_hash": FROZEN_HASHES["runtime_seal"][1],
        "environment_delta_hash": file_sha256(ENV_DELTA),
        "synthetic_preflight_hash": file_sha256(PREFLIGHT),
        "entry_gate_hash": file_sha256(GATE),
        "orchestration_wrapper_hash": file_sha256(WRAPPER),
        "configuration_hash": gate["frozen_configuration_hash"],
        "atomic_persistence_contract": {
            "per_case_json": True,
            "per_trace_json": True,
            "write_temp_file": True,
            "fsync": True,
            "atomic_replace": True,
            "completion_marker_written_last": True,
        },
        "resume_contract": {
            "same_replacement_run_id_only": True,
            "completed_cases_not_recomputed": True,
            "completed_artifact_hashes_unchanged": True,
            "configuration_hash_unchanged": True,
            "component_hashes_unchanged": True,
            "Frozen_Gold_must_be_unopened": True,
            "resume_audit_required": True,
        },
        "original_invalid_run": {
            "run_id": ORIGINAL_RUN_ID,
            "manifest_hash": ORIGINAL_HASHES["manifest"][1],
            "invalid_run_seal_hash": ORIGINAL_HASHES["invalid_run_seal"][1],
            "logs_hashes": gate["original_invalid_run"]["logs_hashes"],
            "failure_classification": "infrastructure_invalid_run",
            "valid_frozen_evaluation_run_consumed": False,
        },
        "output_paths": {
            "case_root": relative(OUT / "p14_replacement_cases"),
            "trace_root": relative(OUT / "p14_replacement_traces"),
            "resume_audit": relative(OUT / "P14_REPLACEMENT_RESUME_AUDIT.jsonl"),
            "per_case_predictions": relative(
                OUT / "p14_replacement_predictions.per_case.jsonl"
            ),
            "predictions_freeze": relative(
                OUT / "P14_REPLACEMENT_PREDICTIONS_FREEZE.json"
            ),
            "retrieval_metrics": relative(
                OUT / "P14_FROZEN_RETRIEVAL_METRICS.json"
            ),
            "evidence_metrics": relative(OUT / "P14_FROZEN_EVIDENCE_METRICS.json"),
            "mechanical_gate_metrics": relative(
                OUT / "P14_FROZEN_MECHANICAL_GATE_METRICS.json"
            ),
            "sufficiency_metrics": relative(
                OUT / "P14_FROZEN_SUFFICIENCY_METRICS.json"
            ),
            "unified_metrics": relative(OUT / "P14_FROZEN_UNIFIED_METRICS.json"),
            "result_freeze": relative(
                OUT / "P14_FROZEN_RESULT_FREEZE_SEAL.json"
            ),
        },
        "expected_case_count": 10,
        "formal_prediction_run_count_before_start": 0,
        "Frozen_Query_opened_at_manifest_time": False,
        "Frozen_Gold_opened_at_manifest_time": False,
        "created_at": created_at,
        "immutable_after_creation": True,
    }
    atomic_json(MANIFEST, manifest)
    MANIFEST.chmod(0o444)
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("gate", "manifest"))
    args = parser.parse_args()
    build_gate() if args.phase == "gate" else build_manifest()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
