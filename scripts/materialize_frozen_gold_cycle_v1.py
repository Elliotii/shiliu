"""One-shot, aggregate-only Frozen Gold Cycle v1 materializer.

This script performs no semantic choice. It accepts only the mechanically
resolved all-agree route, copies each sealed Initial Annotation record into the
reviewed candidate, validates all three layers and evidence identity, creates
byte-identical sealed copies, writes protected lifecycle metadata, updates the
Frozen packet Guard, and stops before P7 closeout or P8.

No case-level value is printed or included in exceptions returned by the CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DEFAULT = Path(__file__).resolve().parents[1]
EXPECTED_LEDGER_SHA256 = "9d37f019ed0ef302c56070e939a024c96546195ebde1236fdb5b30c5d5d78ee8"
EXPECTED_INDEPENDENT_SEAL_SHA256 = (
    "97eff00429cfaa62ca414793d45503149ddeda887c1301ede176081dca77073d"
)
EXPECTED_CASE_COUNT = 10
EXPECTED_BATCH_COUNT = 5
ALLOWED_OUTCOMES = {"agree", "revise_gold", "escalate", "blocked_by_source"}
REVIEWED_NAMES = {
    "retrieval": "product_retrieval_gold.frozen.v1.reviewed.jsonl",
    "evidence": "product_evidence_gold.frozen.v1.reviewed.jsonl",
    "sufficiency": "product_sufficiency_gold.frozen.v1.reviewed.jsonl",
    "status": "reviewed_case_status.frozen.v1.jsonl",
}
SEALED_NAMES = {
    "retrieval": "product_retrieval_gold.frozen.v1.sealed.jsonl",
    "evidence": "product_evidence_gold.frozen.v1.sealed.jsonl",
    "sufficiency": "product_sufficiency_gold.frozen.v1.sealed.jsonl",
    "status": "reviewed_case_status.frozen.v1.sealed.jsonl",
}


class FrozenMaterializationError(RuntimeError):
    """Aggregate-safe materialization failure."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


def fail(category: str) -> None:
    raise FrozenMaterializationError(category)


def sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        fail("artifact_identity_failure")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("artifact_structure_failure")
    if not isinstance(value, dict):
        fail("artifact_structure_failure")
    return value


def read_jsonl_with_raw(path: Path) -> list[tuple[dict[str, Any], bytes]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        values = [(json.loads(line), line.encode("utf-8")) for line in lines if line.strip()]
    except (OSError, json.JSONDecodeError):
        fail("artifact_structure_failure")
    if not all(isinstance(value, dict) for value, _ in values):
        fail("artifact_structure_failure")
    return values


def canonical_line(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(f"{canonical_line(value)}\n" for value in values),
        encoding="utf-8",
    )


def utc_timestamp(explicit: str | None) -> str:
    if explicit:
        try:
            parsed = datetime.fromisoformat(explicit.replace("Z", "+00:00"))
        except ValueError:
            fail("timestamp_failure")
        if parsed.tzinfo is None:
            fail("timestamp_failure")
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def cycle_paths(root: Path) -> dict[str, Path]:
    construction = (
        root / "research/v3_5/product_query_set_v1/gold_construction_v1"
    )
    frozen = construction / "frozen_guarded"
    cycle = frozen / "frozen_cycle_v1"
    return {
        "construction": construction,
        "frozen": frozen,
        "cycle": cycle,
        "initial": cycle / "annotation/initial",
        "independent": cycle / "review/independent_draft",
        "comparison": cycle / "review/comparison",
        "candidate": cycle / "reviewed_gold_candidate",
        "sealed": cycle / "sealed",
        "internal": cycle / "internal_protected",
        "completion": cycle / "completion_only",
        "guard": frozen / "FROZEN_PACKET_ACCESS_GUARD.json",
    }


def import_validator(root: Path):
    scripts = str(root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        import validate_frozen_gold_cycle_v1 as validator  # type: ignore
    except ImportError:
        fail("validator_unavailable")
    return validator


def preflight(paths: dict[str, Path], validator: Any) -> dict[str, Any]:
    ledger = paths["cycle"] / "PQS_V1_FROZEN_GOLD_CYCLE_DECISION_LEDGER.json"
    if sha256(ledger) != EXPECTED_LEDGER_SHA256:
        fail("ledger_identity_failure")
    independent_seal_path = paths["independent"] / "independent_draft.seal.json"
    if sha256(independent_seal_path) != EXPECTED_INDEPENDENT_SEAL_SHA256:
        fail("reviewer_seal_identity_failure")
    independent_seal = read_json(independent_seal_path)
    try:
        validator.validate_reviewer_seal(independent_seal)
    except Exception:
        fail("reviewer_isolation_failure")
    comparison_manifest = read_json(paths["comparison"] / "comparison.manifest.json")
    comparison_audit = read_json(paths["comparison"] / "comparison.audit.json")
    outcome_counts = comparison_manifest.get("outcome_counts", {})
    if (
        comparison_manifest.get("case_count") != EXPECTED_CASE_COUNT
        or comparison_manifest.get("comparison_complete") is not True
        or outcome_counts.get("agree") != EXPECTED_CASE_COUNT
        or any(
            outcome_counts.get(name, 0)
            for name in ALLOWED_OUTCOMES
            if name != "agree"
        )
        or comparison_manifest.get("replacement_artifact_count") != 0
    ):
        fail("unresolved_comparison_failure")
    independent_identity = comparison_audit.get("independent_draft_identity", {})
    if (
        independent_identity.get("unchanged") is not True
        or independent_identity.get("seal_sha256_before")
        != EXPECTED_INDEPENDENT_SEAL_SHA256
        or independent_identity.get("seal_sha256_after")
        != EXPECTED_INDEPENDENT_SEAL_SHA256
    ):
        fail("reviewer_seal_identity_failure")
    initial_seal_path = paths["initial"] / "initial_annotation.seal.json"
    initial_seal = read_json(initial_seal_path)
    if (
        initial_seal.get("status") != "sealed_initial_annotation"
        or initial_seal.get("case_count") != EXPECTED_CASE_COUNT
        or initial_seal.get("batch_count") != EXPECTED_BATCH_COUNT
        or initial_seal.get("gold_layers_complete") is not True
        or initial_seal.get("mutable_after_seal") is not False
    ):
        fail("initial_annotation_seal_failure")
    for relative, expected in initial_seal.get(
        "opaque_batch_artifact_hashes", {}
    ).items():
        if sha256(paths["initial"] / relative) != expected:
            fail("initial_annotation_identity_failure")
    guard = read_json(paths["guard"])
    if guard.get("status") == "sealed_execution_candidate":
        return {"already_materialized": True}
    if guard.get("status") != "annotation_in_progress":
        fail("guard_state_failure")
    for output_key in ("candidate", "sealed", "internal", "completion"):
        output = paths[output_key]
        if output.exists() and any(output.iterdir()):
            fail("protected_output_residue")
    return {
        "already_materialized": False,
        "independent_seal": independent_seal,
        "comparison_manifest": comparison_manifest,
        "comparison_audit": comparison_audit,
        "initial_seal": initial_seal,
        "initial_seal_sha256": sha256(initial_seal_path),
        "entry_guard": guard,
        "entry_guard_sha256": sha256(paths["guard"]),
    }


def load_all_agree_records(
    paths: dict[str, Path],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    comparison_files = sorted(paths["comparison"].glob("opaque_case_*.json"))
    if len(comparison_files) != EXPECTED_CASE_COUNT:
        fail("comparison_artifact_count_failure")
    selected: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    seen_ordinals: set[int] = set()
    seen_identity_hashes: set[str] = set()
    initial_cache: dict[str, list[tuple[dict[str, Any], bytes]]] = {}
    draft_cache: dict[str, list[tuple[dict[str, Any], bytes]]] = {}
    for case_path in comparison_files:
        case = read_json(case_path)
        outcome = case.get("outcome")
        if outcome not in ALLOWED_OUTCOMES:
            fail("comparison_outcome_enum_failure")
        if outcome != "agree":
            fail("unresolved_comparison_failure")
        if (
            case.get("replacement_records_present") is not False
            or case.get("replacement_records") is not None
            or case.get("comparison_complete") is not True
        ):
            fail("all_agree_route_failure")
        opaque_ordinal = case.get("opaque_case_ordinal")
        if (
            not isinstance(opaque_ordinal, int)
            or opaque_ordinal in seen_ordinals
            or opaque_ordinal < 1
            or opaque_ordinal > EXPECTED_CASE_COUNT
        ):
            fail("comparison_identity_failure")
        seen_ordinals.add(opaque_ordinal)
        initial_locator = case.get("initial_annotation_locator", {})
        draft_locator = case.get("independent_draft_locator", {})
        initial_artifact = initial_locator.get("artifact")
        draft_artifact = draft_locator.get("artifact")
        initial_ordinal = initial_locator.get("record_ordinal")
        draft_ordinal = draft_locator.get("record_ordinal")
        if not (
            isinstance(initial_artifact, str)
            and isinstance(draft_artifact, str)
            and isinstance(initial_ordinal, int)
            and isinstance(draft_ordinal, int)
        ):
            fail("comparison_identity_failure")
        if initial_artifact not in initial_cache:
            initial_cache[initial_artifact] = read_jsonl_with_raw(
                paths["initial"] / initial_artifact
            )
        if draft_artifact not in draft_cache:
            draft_cache[draft_artifact] = read_jsonl_with_raw(
                paths["independent"] / draft_artifact
            )
        try:
            initial, initial_raw = initial_cache[initial_artifact][initial_ordinal]
            draft, draft_raw = draft_cache[draft_artifact][draft_ordinal]
        except (IndexError, KeyError):
            fail("comparison_identity_failure")
        if (
            sha256_bytes(initial_raw) != initial_locator.get("record_sha256")
            or sha256_bytes(draft_raw) != draft_locator.get("record_sha256")
        ):
            fail("comparison_identity_failure")
        query_id = initial.get("retrieval_gold", {}).get("query_id")
        if (
            not isinstance(query_id, str)
            or query_id != draft.get("retrieval_gold", {}).get("query_id")
            or initial.get("evidence_gold", {}).get("query_id") != query_id
            or initial.get("sufficiency_gold", {}).get("query_id") != query_id
        ):
            fail("comparison_identity_failure")
        identity_hash = sha256_bytes(query_id.encode("utf-8"))
        if identity_hash != case.get("opaque_case_identity_sha256"):
            fail("comparison_identity_failure")
        if identity_hash in seen_identity_hashes:
            fail("comparison_identity_failure")
        seen_identity_hashes.add(identity_hash)
        selected.append(
            {
                "opaque_case_ordinal": opaque_ordinal,
                "query_id": query_id,
                "retrieval_gold": initial["retrieval_gold"],
                "evidence_gold": initial["evidence_gold"],
                "sufficiency_gold": initial["sufficiency_gold"],
            }
        )
        statuses.append(
            {
                "query_id": query_id,
                "resolution_status": "resolved",
                "review_outcome": "agree",
                "final_record_source": "sealed_initial_annotation",
                "reconciliation_rounds": 0,
                "user_adjudication_required": False,
                "semantic_choice_made_by_orchestrator": False,
                "opaque_case_identity_sha256": identity_hash,
            }
        )
    selected.sort(key=lambda item: item["opaque_case_ordinal"])
    status_by_id = {item["query_id"]: item for item in statuses}
    statuses = [status_by_id[item["query_id"]] for item in selected]
    return selected, statuses


def create_data_outputs(
    paths: dict[str, Path],
    selected: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    for key in ("candidate", "sealed", "internal", "completion"):
        paths[key].mkdir(parents=True, exist_ok=True)
    layers = {
        "retrieval": [item["retrieval_gold"] for item in selected],
        "evidence": [item["evidence_gold"] for item in selected],
        "sufficiency": [item["sufficiency_gold"] for item in selected],
        "status": statuses,
    }
    hashes: dict[str, dict[str, str]] = {"candidate": {}, "sealed": {}}
    for layer, values in layers.items():
        candidate_path = paths["candidate"] / REVIEWED_NAMES[layer]
        sealed_path = paths["sealed"] / SEALED_NAMES[layer]
        write_jsonl(candidate_path, values)
        shutil.copyfile(candidate_path, sealed_path)
        if candidate_path.read_bytes() != sealed_path.read_bytes():
            fail("byte_identity_failure")
        hashes["candidate"][REVIEWED_NAMES[layer]] = sha256(candidate_path)
        hashes["sealed"][SEALED_NAMES[layer]] = sha256(sealed_path)
    return hashes


def write_protected_metadata(
    paths: dict[str, Path],
    preflight_state: dict[str, Any],
    data_hashes: dict[str, dict[str, str]],
    evidence_span_count: int,
    timestamp: str,
) -> dict[str, str]:
    internal = paths["internal"]
    comparison_manifest_path = paths["comparison"] / "comparison.manifest.json"
    comparison_audit_path = paths["comparison"] / "comparison.audit.json"
    independent_seal_path = paths["independent"] / "independent_draft.seal.json"
    manifest_path = internal / "product_gold_frozen_v1.manifest.json"
    audit_path = internal / "frozen_gold_v1.audit.json"
    decision_path = internal / "frozen_gold_v1.execution_decision.json"
    seal_path = internal / "frozen_gold_v1.seal.json"
    report_path = internal / "FROZEN_GOLD_V1_INTERNAL_REPORT.md"
    hash_manifest_path = internal / "frozen_gold_v1.file_hash_manifest.jsonl"
    manifest = {
        "manifest_version": "PRODUCT_GOLD_FROZEN_V1_MANIFEST_V1",
        "protocol_version": "PRODUCT_QUERY_GOLD_PROTOCOL_V1",
        "case_count": EXPECTED_CASE_COUNT,
        "guarded_batch_count": EXPECTED_BATCH_COUNT,
        "three_layer_record_counts": {
            "retrieval_gold": EXPECTED_CASE_COUNT,
            "evidence_gold": EXPECTED_CASE_COUNT,
            "sufficiency_gold": EXPECTED_CASE_COUNT,
        },
        "review_status_record_count": EXPECTED_CASE_COUNT,
        "resolution_route_counts": {
            "direct_agree": EXPECTED_CASE_COUNT,
            "reconciled": 0,
            "user_adjudicated": 0,
        },
        "reviewed_candidate_hashes": data_hashes["candidate"],
        "sealed_artifact_hashes": data_hashes["sealed"],
        "upstream_identity_hashes": {
            "frozen_cycle_decision_ledger": EXPECTED_LEDGER_SHA256,
            "initial_annotation_seal": preflight_state["initial_seal_sha256"],
            "independent_draft_seal": EXPECTED_INDEPENDENT_SEAL_SHA256,
            "comparison_manifest": sha256(comparison_manifest_path),
            "comparison_audit": sha256(comparison_audit_path),
        },
        "sealed_files_byte_identical_to_reviewed_candidate": True,
        "semantic_fields_changed_by_orchestrator": False,
    }
    write_json(manifest_path, manifest)
    audit = {
        "audit_version": "FROZEN_GOLD_V1_AUDIT_V1",
        "case_count": EXPECTED_CASE_COUNT,
        "reviewed_case_count": EXPECTED_CASE_COUNT,
        "aggregate_outcomes": {
            "direct_agree": EXPECTED_CASE_COUNT,
            "reconciled": 0,
            "escalated": 0,
            "blocked_by_source": 0,
        },
        "pending_user_adjudication": 0,
        "validation": {
            "p5_identity": "passed",
            "p6_schema": "passed",
            "p6_cross_object": "passed",
            "evidence_replay": "passed",
            "evidence_spans_replayed": evidence_span_count,
            "replay_failures": 0,
            "navigation_only_sources_used_as_evidence": 0,
            "downstream_failure_codes_in_gold": 0,
            "byte_identical_copy": True,
        },
        "scope": {
            "semantic_fields_changed_by_orchestrator": False,
            "development_gold_read_by_semantic_units": False,
            "product_prediction_read": False,
            "existing_gold_read": False,
            "product_pipeline_calls": 0,
            "frozen_gold_leakage_detected": False,
            "p7_final_closeout_started": False,
            "p8_started": False,
        },
        "independent_draft_seal_sha256_before": EXPECTED_INDEPENDENT_SEAL_SHA256,
        "independent_draft_seal_sha256_after": sha256(independent_seal_path),
        "manifest_sha256": sha256(manifest_path),
    }
    if audit["independent_draft_seal_sha256_after"] != EXPECTED_INDEPENDENT_SEAL_SHA256:
        fail("reviewer_seal_identity_failure")
    write_json(audit_path, audit)
    decision = {
        "decision_version": "FROZEN_GOLD_V1_EXECUTION_DECISION_V1",
        "execution_status": "complete",
        "cycle_status": "frozen_gold_sealed_execution_candidate_ready",
        "frozen_gold_sealed_execution_candidate_ready": True,
        "frozen_gold_formally_accepted_by_codex": False,
        "pending_user_adjudication": 0,
        "semantic_choice_made_by_orchestrator": False,
        "p7_final_closeout_authorized": False,
        "p8_authorized": False,
        "acceptance_status": "pending_v3_5_b_review",
        "decided_at_utc": timestamp,
        "manifest_sha256": sha256(manifest_path),
        "audit_sha256": sha256(audit_path),
    }
    write_json(decision_path, decision)
    seal = {
        "seal_version": "FROZEN_GOLD_V1_SEAL_V1",
        "status": "sealed_execution_candidate",
        "acceptance_status": "pending_v3_5_b_review",
        "sealed_at_utc": timestamp,
        "case_count": EXPECTED_CASE_COUNT,
        "guarded_batch_count": EXPECTED_BATCH_COUNT,
        "three_layer_counts": {
            "retrieval_gold": EXPECTED_CASE_COUNT,
            "evidence_gold": EXPECTED_CASE_COUNT,
            "sufficiency_gold": EXPECTED_CASE_COUNT,
        },
        "reviewed_case_count": EXPECTED_CASE_COUNT,
        "pending_user_adjudication": 0,
        "all_cases_resolved": True,
        "p6_schema_validation": "passed",
        "p6_cross_object_validation": "passed",
        "evidence_replay_status": "passed",
        "evidence_spans_replayed": evidence_span_count,
        "replay_failures": 0,
        "byte_identical_copy": True,
        "semantic_fields_changed_by_orchestrator": False,
        "frozen_gold_formally_accepted_by_codex": False,
        "p8_started": False,
        "sealed_artifact_hashes": data_hashes["sealed"],
        "manifest_sha256": sha256(manifest_path),
        "audit_sha256": sha256(audit_path),
        "execution_decision_sha256": sha256(decision_path),
    }
    write_json(seal_path, seal)
    report = "\n".join(
        [
            "Frozen Gold V1 Internal Aggregate Report",
            "",
            f"- Cases: {EXPECTED_CASE_COUNT}",
            f"- Guarded batches: {EXPECTED_BATCH_COUNT}",
            f"- Three-layer records: {EXPECTED_CASE_COUNT * 3}",
            f"- Direct agreements: {EXPECTED_CASE_COUNT}",
            "- Reconciled: 0",
            "- Pending user adjudication: 0",
            f"- Evidence spans replayed: {evidence_span_count}",
            "- Replay failures: 0",
            "- P6 schema and cross-object validation: passed",
            "- Byte-identical sealed copy: true",
            "- Semantic choices by orchestrator: false",
            "- Product pipeline calls: 0",
            "- P8 started: false",
            "- Acceptance: pending V3.5-B review",
            "",
        ]
    )
    report_path.write_text(report, encoding="utf-8")
    manifest_entries: list[dict[str, str]] = []
    for base_key in ("candidate", "sealed"):
        for file_path in sorted(paths[base_key].iterdir()):
            if file_path.is_file():
                manifest_entries.append(
                    {
                        "path": file_path.relative_to(paths["cycle"]).as_posix(),
                        "sha256": sha256(file_path),
                    }
                )
    for file_path in (
        manifest_path,
        audit_path,
        decision_path,
        seal_path,
        report_path,
    ):
        manifest_entries.append(
            {
                "path": file_path.relative_to(paths["cycle"]).as_posix(),
                "sha256": sha256(file_path),
            }
        )
    write_jsonl(hash_manifest_path, manifest_entries)
    return {
        "manifest_sha256": sha256(manifest_path),
        "audit_sha256": sha256(audit_path),
        "decision_sha256": sha256(decision_path),
        "seal_sha256": sha256(seal_path),
        "hash_manifest_sha256": sha256(hash_manifest_path),
        "report_sha256": sha256(report_path),
    }


def write_completion_only(
    paths: dict[str, Path],
    data_hashes: dict[str, dict[str, str]],
    evidence_span_count: int,
) -> None:
    completion = {
        "input_identity_verified": True,
        "frozen_query_count": EXPECTED_CASE_COUNT,
        "guarded_batch_count": EXPECTED_BATCH_COUNT,
        "annotator_unit_count": 1,
        "reviewer_unit_count": 1,
        "reviewer_independent_draft_seal_valid": True,
        "reviewed_case_count": EXPECTED_CASE_COUNT,
        "aggregate_outcomes": {
            "direct_agree": EXPECTED_CASE_COUNT,
            "reconciled": 0,
            "escalated": 0,
            "blocked_by_source": 0,
        },
        "pending_user_adjudication": 0,
        "three_layer_validation": "passed",
        "evidence_spans_replayed": evidence_span_count,
        "replay_failures": 0,
        "sealed_artifact_hashes": data_hashes["sealed"],
        "byte_identical_copy": True,
        "semantic_fields_changed_by_orchestrator": False,
        "frozen_gold_leakage_detected": False,
        "development_gold_read_by_semantic_units": False,
        "product_prediction_read": False,
        "product_pipeline_calls": 0,
        "p8_started": False,
        "acceptance_status": "pending_v3_5_b_review",
        "current_codex_session_can_close": True,
    }
    status_path = paths["completion"] / "FROZEN_GOLD_V1_COMPLETION_STATUS.json"
    response_path = paths["completion"] / "FROZEN_GOLD_V1_COMPLETION_RESPONSE.md"
    write_json(status_path, completion)
    # JSON is valid Markdown text and avoids adding any non-contract heading or prose.
    write_json(response_path, completion)


def update_guard(
    paths: dict[str, Path],
    preflight_state: dict[str, Any],
    timestamp: str,
) -> None:
    guard = dict(preflight_state["entry_guard"])
    previous_transition = guard.get("status_transition")
    history = list(guard.get("status_transition_history", []))
    if isinstance(previous_transition, dict):
        history.append(previous_transition)
    guard["status"] = "sealed_execution_candidate"
    guard["status_transition_history"] = history
    guard["status_transition"] = {
        "previous_status": "annotation_in_progress",
        "previous_guard_sha256": preflight_state["entry_guard_sha256"],
        "reason": "All Frozen cases resolved by independent all-agree review; mechanical validation and seal completed",
        "transitioned_at_utc": timestamp,
    }
    write_json(paths["guard"], guard)
    new_guard_sha256 = sha256(paths["guard"])
    transition = {
        "transition_version": "FROZEN_GOLD_V1_GUARD_TRANSITION_V1",
        "previous_status": "annotation_in_progress",
        "new_status": "sealed_execution_candidate",
        "entry_guard_sha256": preflight_state["entry_guard_sha256"],
        "previous_guard_sha256": preflight_state["entry_guard_sha256"],
        "new_guard_sha256": new_guard_sha256,
        "reason": guard["status_transition"]["reason"],
        "transitioned_at_utc": timestamp,
        "preserved_transition_history": history,
    }
    write_json(
        paths["cycle"] / "guard_transition.sealed_execution_candidate.json",
        transition,
    )


def materialize(root: Path, timestamp: str | None = None) -> dict[str, Any]:
    paths = cycle_paths(root)
    validator = import_validator(root)
    state = preflight(paths, validator)
    if state.get("already_materialized"):
        try:
            return validator.validate_frozen_cycle(root)
        except Exception:
            fail("existing_materialization_validation_failure")
    selected, statuses = load_all_agree_records(paths)
    retrieval = [item["retrieval_gold"] for item in selected]
    evidence = [item["evidence_gold"] for item in selected]
    sufficiency = [item["sufficiency_gold"] for item in selected]
    try:
        validator.validate_p5_identity(root, [row["query_id"] for row in retrieval])
        validator.validate_three_layer_records(root, retrieval, evidence, sufficiency)
        replayed = validator.replay_evidence(root, evidence)
    except Exception:
        fail("pre_materialization_validation_failure")
    timestamp_value = utc_timestamp(timestamp)
    data_hashes = create_data_outputs(paths, selected, statuses)
    write_protected_metadata(paths, state, data_hashes, replayed, timestamp_value)
    write_completion_only(paths, data_hashes, replayed)
    update_guard(paths, state, timestamp_value)
    try:
        result = validator.validate_frozen_cycle(root)
    except Exception:
        fail("post_materialization_validation_failure")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument(
        "--timestamp",
        help="Optional explicit ISO-8601 UTC timestamp for reproducible metadata",
    )
    args = parser.parse_args()
    try:
        result = materialize(args.root.resolve(), args.timestamp)
    except FrozenMaterializationError as exc:
        print(json.dumps({"status": "blocked", "category": exc.category}, sort_keys=True))
        return 1
    except Exception:
        print(json.dumps({"status": "blocked", "category": "aggregate_execution_failure"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
