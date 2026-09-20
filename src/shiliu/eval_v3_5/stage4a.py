from __future__ import annotations

from collections import Counter
import csv
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from shiliu.evidence.stage3a import (
    DETERMINISTIC_SELECTOR_VERSION, EvidenceBundle, EvidenceCandidateSet, SelectorConfig,
    build_within_video_candidates, resolve_from_search_candidates, select_deterministic_bundle,
    validate_bundle,
)
from shiliu.evidence.stage4 import (
    FINAL_CANDIDATE_BUILDER_VERSION, MECHANICAL_GATE_CONTRACT_VERSION,
    MECHANICAL_GATE_POLICY_VERSION, REASON_ACTION, SUFFICIENCY_DECISION_CONTRACT_VERSION,
    SUFFICIENCY_REQUEST_CONTRACT_VERSION, EvidenceResolutionState, MechanicalGateDecision,
    MechanicalGatePolicy, SufficiencyDecision, SufficiencyRequest,
    apply_mechanical_sufficiency_gate, canonical_bytes, stable_id, terminal_sufficiency_decision,
)
from shiliu.eval_v3_5.isolation import HeldoutAccessGuard
from shiliu.eval_v3_5.stage3a import (
    EXPECTED_ARTIFACT_HASH, EXPECTED_GOLD_HASH, EXPECTED_MANIFEST_HASH, EXPECTED_SNAPSHOT_HASH,
    FrozenRawSourceResolver, bundle_hits_group, file_sha256, load_jsonl, validate_search_candidate_set,
)
from shiliu.eval_v3_5.stage3b import final_builder_config


STAGE4A_RUNNER_VERSION = "v3.5-stage4a-development-runner-v1"
EVIDENCE_CASE_IDS = ("CASE_001", "CASE_002", "CASE_003", "CASE_005")
# This is the frozen Stage 3B final generic-builder result, not a new semantic rule.
TRACK_B_FROZEN_OPERATIONAL_FAILURES = {"CASE_003": "candidate_generation_failure"}


def _set_id(candidate_set: EvidenceCandidateSet) -> str:
    return stable_id("candidate_set_", candidate_set.as_dict())


def _request(record: Mapping[str, Any], candidate_set: EvidenceCandidateSet,
             bundle: EvidenceBundle | None, reason: str | None) -> tuple[SufficiencyRequest, EvidenceResolutionState]:
    candidate_set_id = _set_id(candidate_set)
    status = "resolved" if reason is None and bundle is not None else "failed"
    source_states = tuple(sorted({candidate.normalization_status for candidate in candidate_set.candidates}))
    languages = tuple(sorted({candidate.source_language for candidate in candidate_set.candidates}))
    trace_id = stable_id("stage4a_trace_", {
        "query_id": record["query_id"], "evaluation_track": candidate_set.evaluation_track,
        "search_candidate_set_id": record["search_candidate_set_id"],
        "evidence_candidate_set_id": candidate_set_id, "evidence_bundle_id": bundle.bundle_id if bundle else None,
    })
    base = {
        "query_id": str(record["query_id"]), "original_query": str(record["original_query"]),
        "evaluation_track": candidate_set.evaluation_track,
        "end_to_end_claim_eligible": candidate_set.end_to_end_claim_eligible,
        "search_candidate_set_id": str(record["search_candidate_set_id"]),
        "evidence_candidate_set_id": candidate_set_id, "evidence_bundle_id": bundle.bundle_id if bundle else None,
        "evidence_resolution_status": status, "failure_attribution": reason,
        "candidate_builder_version": FINAL_CANDIDATE_BUILDER_VERSION,
        "selector_version": DETERMINISTIC_SELECTOR_VERSION, "source_states": source_states,
        "source_languages": languages, "trace_id": trace_id,
    }
    request = SufficiencyRequest(
        request_id=stable_id("request_", {"contract": SUFFICIENCY_REQUEST_CONTRACT_VERSION, **base}), **base,
    )
    state = EvidenceResolutionState(
        status=status, operational_reason_code=reason,
        search_candidate_set_id=str(record["search_candidate_set_id"]), evidence_candidate_set_id=candidate_set_id,
        evidence_bundle_id=bundle.bundle_id if bundle else None,
        available_evidence_candidate_ids=tuple(candidate.candidate_id for candidate in candidate_set.candidates),
        evidence_ids_raw_derived=bool(candidate_set.candidates),
        source_integrity_valid=candidate_set.normalization_status == "valid" and not candidate_set.validation_errors,
        validation_errors=candidate_set.validation_errors,
    )
    return request, state


def _freeze_predictions(*, manifest: Sequence[Mapping[str, Any]], resolver: FrozenRawSourceResolver
                        ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    builder, selector, policy = final_builder_config(), SelectorConfig(), MechanicalGatePolicy()
    tracks: dict[str, list[dict[str, Any]]] = {"track_a": [], "track_b": []}
    runtime: dict[str, dict[str, Any]] = {}
    for record in manifest:
        validate_search_candidate_set(record)
        case_id = str(record["case_id"])
        candidate_a = resolve_from_search_candidates(
            str(record["original_query"]), record["search_candidates"], resolver, builder,
            query_id=str(record["query_id"]), search_candidate_set_id=str(record["search_candidate_set_id"]),
            execution_manifest_identity=EXPECTED_MANIFEST_HASH,
        )
        bundle_a = select_deterministic_bundle(str(record["original_query"]), candidate_a, selector)
        reason_a = candidate_a.failure_category
        if reason_a is None and bundle_a is None:
            reason_a = "selector_failed"
        _freeze_one(case_id, "track_a", record, candidate_a, bundle_a, reason_a, policy, tracks, runtime)

        if case_id in EVIDENCE_CASE_IDS:
            target = int(record["target_video_id"])
            artifact = resolver(target)
            candidate_b = build_within_video_candidates(
                str(record["original_query"]), target, artifact.source_version, artifact, builder,
                query_id=str(record["query_id"]),
            )
            bundle_b = select_deterministic_bundle(str(record["original_query"]), candidate_b, selector)
            reason_b = TRACK_B_FROZEN_OPERATIONAL_FAILURES.get(case_id)
            if reason_b is not None:
                bundle_b = None
            elif bundle_b is None:
                reason_b = "selector_failed"
            _freeze_one(case_id, "track_b", record, candidate_b, bundle_b, reason_b, policy, tracks, runtime)
    return tracks, runtime


def _freeze_one(case_id: str, track: str, record: Mapping[str, Any], candidate_set: EvidenceCandidateSet,
                bundle: EvidenceBundle | None, reason: str | None, policy: MechanicalGatePolicy,
                tracks: dict[str, list[dict[str, Any]]], runtime: dict[str, dict[str, Any]]) -> None:
    if bundle is not None:
        validate_bundle(bundle, candidate_set)
    request, state = _request(record, candidate_set, bundle, reason)
    gate = apply_mechanical_sufficiency_gate(request, state, bundle, policy)
    terminal = terminal_sufficiency_decision(gate) if gate.gate_outcome == "source_unverifiable" else None
    row = {
        "case_id": case_id, "request": request, "state": state, "candidate_set": candidate_set,
        "bundle": bundle, "gate": gate, "terminal_decision": terminal,
    }
    runtime[f"{case_id}.{track}"] = row
    tracks[track].append(row)


def _gold_status(gold: Mapping[str, Any]) -> str:
    for key in ("status", "sufficiency_status", "sufficiency_label", "gold_status"):
        if gold.get(key) in {"sufficient", "partial", "insufficient", "unverifiable"}:
            return str(gold[key])
    raise RuntimeError("Development Gold status field is unsupported")


def _classification(gold_rows: Sequence[Mapping[str, Any]], predictions: Mapping[str, str]) -> dict[str, Any]:
    labels = ("sufficient", "partial", "insufficient", "unverifiable")
    pairs = [(_gold_status(row), predictions[str(row["case_id"])]) for row in gold_rows]
    matrix = {actual: {predicted: sum(a == actual and p == predicted for a, p in pairs) for predicted in labels} for actual in labels}
    per_class = {}
    for label in labels:
        tp = sum(a == label and p == label for a, p in pairs)
        predicted = sum(p == label for _, p in pairs)
        support = sum(a == label for a, _ in pairs)
        per_class[label] = {
            "precision": tp / predicted if predicted else None,
            "recall": tp / support if support else None, "support": support,
        }
    correct = sum(a == p for a, p in pairs)
    risk = [(a, p) for a, p in pairs if a in {"insufficient", "unverifiable"}]
    false_sufficient = sum(p == "sufficient" for _, p in risk)
    return {
        "overall_accuracy": correct / len(pairs), "absolute_correct_count": correct,
        "absolute_incorrect_count": len(pairs) - correct, "per_class": per_class,
        "confusion_matrix": matrix, "false_sufficient_count": false_sufficient,
        "false_sufficient_rate_on_insufficient_plus_unverifiable": false_sufficient / len(risk) if risk else None,
        "insufficient_to_sufficient": sum(a == "insufficient" and p == "sufficient" for a, p in pairs),
        "unverifiable_to_sufficient": sum(a == "unverifiable" and p == "sufficient" for a, p in pairs),
        "partial_zero_support_warning": "Partial class has zero Development support; any four-class Macro-F1 is descriptive only.",
    }


def _gate_summary(rows: Sequence[Mapping[str, Any]], gold: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    gates = [row["gate"] for row in rows]
    comparison = {
        status: {"judge_eligible": 0, "source_unverifiable": 0, "invalid": 0}
        for status in ("sufficient", "partial", "insufficient", "unverifiable")
    }
    for row in rows:
        comparison[_gold_status(gold[row["case_id"]])][row["gate"].gate_outcome] += 1
    return {
        "development_case_count": len(rows),
        "judge_eligible_count": sum(g.gate_outcome == "judge_eligible" for g in gates),
        "source_unverifiable_count": sum(g.gate_outcome == "source_unverifiable" for g in gates),
        "invalid_count": sum(g.gate_outcome == "invalid" for g in gates),
        **{f"{action}_count": sum(g.action_family == action for g in gates) for action in REASON_ACTION.values()},
        "unknown_operational_state_count": sum(g.operational_reason_code == "unknown_operational_state" for g in gates),
        "invalid_gate_decision_count": 0, "gold_comparison": comparison,
    }


def run_stage4a_development(*, repository_root: Path, manifest_path: Path, development_gold_path: Path,
                            artifact_manifest_path: Path, snapshot_db_path: Path) -> dict[str, Any]:
    guard = HeldoutAccessGuard(repository_root)
    identities = {
        "development_execution_manifest_sha256": file_sha256(guard.validate_path(manifest_path)),
        "artifact_manifest_sha256": file_sha256(guard.validate_path(artifact_manifest_path)),
        "snapshot_database_sha256": file_sha256(guard.validate_path(snapshot_db_path)),
    }
    expected = {
        "development_execution_manifest_sha256": EXPECTED_MANIFEST_HASH,
        "artifact_manifest_sha256": EXPECTED_ARTIFACT_HASH, "snapshot_database_sha256": EXPECTED_SNAPSHOT_HASH,
    }
    if identities != expected:
        raise RuntimeError(f"frozen pre-prediction identity mismatch: {identities}")
    manifest = load_jsonl(guard.read_text(manifest_path))
    resolver = FrozenRawSourceResolver(artifact_manifest=artifact_manifest_path, snapshot_db=snapshot_db_path, guard=guard)

    # All runtime Requests, Bundles, Gate decisions, IDs, and bytes freeze above this line.
    tracks, runtime = _freeze_predictions(manifest=manifest, resolver=resolver)
    prediction_hash = sha256(canonical_bytes({
        key: row["gate"].model_dump(mode="json") for key, row in sorted(runtime.items())
    })).hexdigest()

    identities["development_gold_sha256"] = file_sha256(guard.validate_path(development_gold_path))
    if identities["development_gold_sha256"] != EXPECTED_GOLD_HASH:
        raise RuntimeError("Development Gold identity mismatch")
    gold_rows = load_jsonl(guard.read_text(development_gold_path))
    gold = {str(row["case_id"]): row for row in gold_rows}

    adequacy_rows = []
    for key, row in sorted(runtime.items()):
        gate, bundle, candidate_set = row["gate"], row["bundle"], row["candidate_set"]
        item_gold = gold[row["case_id"]]
        status = _gold_status(item_gold)
        adequate: bool | None = None
        attribution = None
        if gate.gate_outcome == "judge_eligible":
            if status in {"sufficient", "partial"}:
                adequate = any(bundle_hits_group(group, bundle, candidate_set.candidates) for group in item_gold.get("gold_evidence_groups", []))
                if not adequate:
                    attribution = "upstream_evidence_resolution_failure"
            elif status == "insufficient":
                adequate = row["state"].source_integrity_valid
        adequacy_rows.append({
            "case_id": row["case_id"], "evaluation_track": gate.evaluation_track,
            "gate_outcome": gate.gate_outcome, "gold_status": status,
            "judge_input_adequate": adequate, "failure_attribution": attribution,
        })

    s0_predictions = {str(row["case_id"]): "sufficient" for row in gold_rows}
    track_a_by_case = {row["case_id"]: row for row in tracks["track_a"]}
    s1_predictions = {case_id: ("sufficient" if row["gate"].gate_outcome == "judge_eligible" else "unverifiable") for case_id, row in track_a_by_case.items()}
    s0 = {"baseline": "S0_always_sufficient", **_classification(gold_rows, s0_predictions),
          "per_case": [{"case_id": row["case_id"], "gold_status": _gold_status(row), "prediction": "sufficient"} for row in gold_rows]}
    s1 = {"baseline": "S1_mechanical_gate_only", "not_product_policy": True, **_classification(gold_rows, s1_predictions),
          "per_case": [{"case_id": row["case_id"], "gold_status": _gold_status(row), "prediction": s1_predictions[str(row["case_id"])]} for row in gold_rows]}
    eligible = [row for row in adequacy_rows if row["gate_outcome"] == "judge_eligible"]
    adequacy = {
        "gold_opened_after_prediction": True, "prediction_freeze_sha256": prediction_hash,
        "judge_eligible_case_count": len(eligible),
        "judge_input_adequate_count": sum(row["judge_input_adequate"] is True for row in eligible),
        "judge_input_inadequate_count": sum(row["judge_input_adequate"] is False for row in eligible),
        "per_case": adequacy_rows,
    }
    adequacy["by_track"] = {
        track_name: {
            "judge_eligible_case_count": len(values),
            "judge_input_adequate_count": sum(row["judge_input_adequate"] is True for row in values),
            "judge_input_inadequate_count": sum(row["judge_input_adequate"] is False for row in values),
            "failure_attribution_counts": dict(sorted(Counter(
                row["failure_attribution"] or "none" for row in values
            ).items())),
        }
        for track_name, values in {
            "frozen_v3_end_to_end": [row for row in eligible if row["evaluation_track"] == "frozen_v3_end_to_end"],
            "oracle_video_conditional": [row for row in eligible if row["evaluation_track"] == "oracle_video_conditional"],
        }.items()
    }
    serialized_tracks = {}
    traces = {}
    for track, rows in tracks.items():
        serialized_rows = []
        for row in rows:
            gate, terminal = row["gate"], row["terminal_decision"]
            serialized_rows.append({"case_id": row["case_id"], "gate": gate.model_dump(mode="json"),
                                    "terminal_sufficiency_decision": terminal.model_dump(mode="json") if terminal else None})
            traces[f"{row['case_id']}.{track}"] = {
                "evaluation_track": gate.evaluation_track, "query_identity": gate.query_id,
                "search_candidate_set_identity": gate.search_candidate_set_id,
                "evidence_candidate_set_identity": gate.evidence_candidate_set_id,
                "evidence_bundle_identity": gate.evidence_bundle_id,
                "candidate_builder_version": gate.candidate_builder_version, "selector_version": gate.selector_version,
                "evidence_resolution_status": row["request"].evidence_resolution_status,
                "failure_attribution": row["request"].failure_attribution,
                "mechanical_gate_policy_version": gate.mechanical_gate_policy_version,
                "gate_outcome": gate.gate_outcome, "operational_reason": gate.operational_reason_code,
                "action_family": gate.action_family, "semantic_judge_required": gate.semantic_judge_required,
                "terminal_sufficiency_decision_id": terminal.decision_id if terminal else None,
                "gold_opened_after_prediction": True,
                "judge_input_adequate": next(value["judge_input_adequate"] for value in adequacy_rows if value["case_id"] == row["case_id"] and value["evaluation_track"] == gate.evaluation_track),
            }
        serialized_tracks[track] = {"summary": _gate_summary(rows, gold), "per_case": serialized_rows}
    audit = guard.audit_record(
        source_files_scanned=["src/shiliu/evidence/stage4.py", "src/shiliu/eval_v3_5/stage4a.py", "src/shiliu/eval_v3_5/isolation.py"],
        test_files_scanned=["tests/test_v3_5_stage4a_gate.py", "tests/test_v3_5_stage4a_eval.py"], violations=[],
    )
    return {"runner_version": STAGE4A_RUNNER_VERSION, "input_identities": identities,
            "prediction_freeze_sha256": prediction_hash, **serialized_tracks,
            "judge_input_adequacy": adequacy, "s0": s0, "s1": s1, "traces": traces,
            "heldout_access_audit": audit}


def write_stage4a_artifacts(result: Mapping[str, Any], *, output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "trace_samples").mkdir(exist_ok=True)
    def dump(name: str, value: object) -> None:
        (output_directory / name).write_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n")
    dump("sufficiency_request_contract.json", SufficiencyRequest.model_json_schema())
    dump("mechanical_gate_contract.json", MechanicalGateDecision.model_json_schema())
    dump("sufficiency_decision_contract.json", SufficiencyDecision.model_json_schema())
    dump("mechanical_gate_policy.json", MechanicalGatePolicy().model_dump(mode="json"))
    dump("operational_reason_policy.json", {"policy_version": MECHANICAL_GATE_POLICY_VERSION, "reason_to_action_family": REASON_ACTION,
                                             "selector_aliases": {"selector_failure": "selector_failed", "no_selected_bundle": "selector_failed", "selector_abstain": "selector_failed", "invalid_bundle_reference": "selector_failed"}})
    dump("action_family_policy.json", {"policy_version": MECHANICAL_GATE_POLICY_VERSION, "action_families": sorted(set(REASON_ACTION.values()) | {"none"})})
    dump("track_a_mechanical_gate_eval.dev.json", result["track_a"])
    dump("track_b_mechanical_gate_eval.dev.json", result["track_b"])
    dump("judge_input_adequacy.dev.json", result["judge_input_adequacy"])
    dump("s0_always_sufficient_eval.dev.json", result["s0"])
    dump("s1_mechanical_gate_eval.dev.json", result["s1"])
    dump("heldout_access_audit.json", result["heldout_access_audit"])
    for name, value in result["traces"].items():
        dump(f"trace_samples/{name}.json", value)
    rows = []
    for track in ("track_a", "track_b"):
        for row in result[track]["per_case"]:
            gate = row["gate"]
            rows.append({"case_id": row["case_id"], "evaluation_track": gate["evaluation_track"],
                         "gate_outcome": gate["gate_outcome"], "operational_reason_code": gate["operational_reason_code"],
                         "action_family": gate["action_family"], "semantic_judge_required": gate["semantic_judge_required"]})
    with (output_directory / "mechanical_gate_per_case.dev.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    dump("stage4a_run_manifest.json", {
        "runner_version": result["runner_version"], "evaluation_scope": "development_only",
        "provider_calls": 0, "heldout_executed": False, "semantic_judge_started": False,
        "input_identities": result["input_identities"], "prediction_freeze_sha256": result["prediction_freeze_sha256"],
        "contracts": {"request": SUFFICIENCY_REQUEST_CONTRACT_VERSION, "gate": MECHANICAL_GATE_CONTRACT_VERSION,
                      "decision": SUFFICIENCY_DECISION_CONTRACT_VERSION, "policy": MECHANICAL_GATE_POLICY_VERSION},
        "candidate_builder_version": FINAL_CANDIDATE_BUILDER_VERSION,
        "selector_version": DETERMINISTIC_SELECTOR_VERSION,
    })
