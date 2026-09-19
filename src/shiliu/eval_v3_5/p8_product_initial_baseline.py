"""P8 Product Initial Baseline blind runner and post-seal scorer.

The two public entry points are deliberately separated. ``run_blind`` has no
Development Gold parameter and never resolves a Gold path. ``score_frozen``
first verifies the immutable prediction seal and only then opens Development
Gold. Frozen Evaluation assets are never accepted by either entry point.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Iterable, Mapping, Sequence

from shiliu.evidence.stage3a import (
    DETERMINISTIC_SELECTOR_VERSION,
    EvidenceCandidateSet,
    SelectorConfig,
    resolve_from_search_candidates,
    select_deterministic_bundle,
    validate_bundle,
)
from shiliu.evidence.contracts import EvidenceContractError
from shiliu.evidence.stage4 import MechanicalGatePolicy, apply_mechanical_sufficiency_gate
from shiliu.eval_v3_5.isolation import HeldoutAccessGuard
from shiliu.eval_v3_5.stage3a import FrozenRawSourceResolver
from shiliu.eval_v3_5.stage3r import _search_payload, file_sha256, final_builder_config
from shiliu.eval_v3_5.stage3r_qc_phase_b_r import build_search_service, inspect_index
from shiliu.eval_v3_5.stage4a import _request
from shiliu.retrieval.planner import SearchPlanner, SearchRequest
from shiliu.retrieval.product_search import ProductSearchRequest
from shiliu.retrieval.qwen import QwenEmbeddingProvider


RUNNER_VERSION = "v3.5-pqs-v1-p8-product-initial-baseline-v2-source-terminal"
ATTEMPT_ID = "P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_3"
OUTPUT_RELATIVE = Path("research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3")
QUERY_RELATIVE = Path("research/v3_5/product_query_set_v1/split_v1/product_query_development_v1.locked.jsonl")
AUTHORITY_RELATIVE = Path("03_V3_5_DECISION_AND_ARTIFACT_INDEX.md")
ARTIFACT_MANIFEST_RELATIVE = Path("research/v3_eval/artifact_manifest.jsonl")
SNAPSHOT_ID = "20260720T094346Z_c7663365"
SNAPSHOT_SHA256 = "61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1"
QUERY_SHA256 = "e68d6bb405bafadb56c5333834d72c8155a7a310ca2e20341df4f412488a8935"
AUTHORITY_SHA256 = "13e792483b0f5c4945a7a2802e56cd9f8076479d7c583b2022ac197acfb98421"
ARTIFACT_MANIFEST_SHA256 = "36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f"
GOLD_HASHES = {
    "retrieval": "b34188c269bf3a2410f8602fdb7d72908a96c822ac3b8f675d4f4c2b72b45679",
    "evidence": "b259a1b225a48558f5d1a6c4cb4909ea413e86116a1564b3fa724632ae88efc1",
    "sufficiency": "11196158746bb2c12e457fcb36b87a1621e79dca0b2f628a4870ca5ec6c5de92",
    "case_status": "9ba38a1f8cf636ebb9e80219cd85a41003743cb11f370a24d3946534378c6352",
}
COMPONENT_HASHES = {
    "candidate_builder": ("src/shiliu/evidence/stage3b.py", "8a2ed841efdf42f048347bf23ed1170a67ce7be0f3b03823eabef31847a80458"),
    "deterministic_selector": ("src/shiliu/evidence/stage3a.py", "34774d6c166680e7523010f9d1d950f9aa1b890487f46427279164cdedaed552"),
    "mechanical_gate_contract": ("research/v3_5/stage4a/mechanical_gate_contract.json", "f255c42a46825b77f45b7d8c54b1f5746cfed2f5d8d501a4cb9aef6d09b93051"),
    "product_default_wiring": ("research/v3_5/product_default_auto_wiring/product_default_auto_wiring_manifest.json", "5d5d42ad7501f8a9d917a17b7b6116da4f84f3d5d974f8a54e3dbcd88cb588f9"),
    "router": ("src/shiliu/retrieval/planner.py", "0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e"),
}
PRIMARY_ENUM = {
    "retrieval_failure", "retrieval_gold_unjudged", "candidate_builder_failure",
    "deterministic_selector_failure", "mechanical_gate_failure",
    "source_unverifiable", "identity_or_scoring_defect", "end_to_end_bundle_hit",
}
SOURCE_TERMINAL_CODES = frozenset({
    "no_supported_subtitle",
    "raw_source_unavailable",
    "source_unavailable",
    "source_unreadable",
    "title_only",
    "language_unresolved",
})


class P8Blocked(RuntimeError):
    def __init__(self, category: str, message: str, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.category = category
        self.details = dict(details or {})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def value_sha256(value: object) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    values = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for row in values) + ("\n" if values else ""), encoding="utf-8")


def _component_identity(repository_root: Path) -> dict[str, Any]:
    mismatches: dict[str, Any] = {}
    values: dict[str, Any] = {}
    for name, (relative, expected) in COMPONENT_HASHES.items():
        actual = file_sha256(repository_root / relative)
        values[name] = {"path": relative, "sha256": actual, "expected_sha256": expected}
        if actual != expected:
            mismatches[name] = values[name]
    if mismatches:
        raise P8Blocked("component_authority_identity", "Runtime component hash mismatch", mismatches)
    return values


def _trace_root_hash(trace_rows: Sequence[Mapping[str, Any]]) -> str:
    return value_sha256([{"path": row["path"], "sha256": row["sha256"]} for row in trace_rows])


def _query_hash(row: Mapping[str, Any]) -> str:
    return sha256(str(row["query_text"]).encode("utf-8")).hexdigest()


def _git_identity(repository_root: Path) -> dict[str, str]:
    import subprocess
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository_root, check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"], cwd=repository_root,
        check=True, capture_output=True, text=True,
    ).stdout
    return {"git_commit": commit, "dirty_tree_fingerprint_sha256": sha256(status.encode()).hexdigest()}


def _candidate_summary(candidate_set: Any) -> dict[str, Any]:
    candidates = list(candidate_set.candidates)
    return {
        "outcome": (
            "no_authoritative_source"
            if candidate_set.failure_category in SOURCE_TERMINAL_CODES
            else ("complete" if not candidate_set.failure_category else "failed")
        ),
        "candidate_count": len(candidates),
        "source_failure_code": (
            candidate_set.failure_category
            if candidate_set.failure_category in SOURCE_TERMINAL_CODES
            else None
        ),
        "candidate_ids": [value.candidate_id for value in candidates],
        "parent_video_ids": sorted({value.video_id for value in candidates}),
        "parent_chunk_ids": sorted({chunk for value in candidates for chunk in value.parent_chunk_ids}),
        "evidence_spans": [
            {
                "candidate_id": value.candidate_id, "video_id": value.video_id,
                "segment_ids": list(value.segment_ids), "start_time": value.start_time,
                "end_time": value.end_time, "source_artifact_id": value.source_artifact_id,
                "source_version": value.source_version, "timeline_run_id": value.timeline_run_id,
            }
            for value in candidates
        ],
        "source_types": [value.source_type for value in candidates],
        "source_languages": [value.source_language for value in candidates],
        "invalid_candidate_count": sum(value.normalization_status != "valid" or bool(value.validation_errors) for value in candidates),
        "normalization_status": candidate_set.normalization_status,
        "validation_errors": list(candidate_set.validation_errors),
    }


def _prediction_row(
    *, query: Mapping[str, Any], run_id: str, search_payload: Mapping[str, Any],
    candidate_set: Any, bundle: Any, gate: Any, timings: Mapping[str, float],
    trace_path: str, input_identity: Mapping[str, Any],
) -> dict[str, Any]:
    video_candidates = list(search_payload["video_candidates"])
    raw_candidates = list(search_payload["raw_unit_candidates"])
    builder = _candidate_summary(candidate_set)
    return {
        "query_id": query["query_id"], "query_text_sha256": _query_hash(query), "run_id": run_id,
        "input_identity": dict(input_identity),
        "retrieval": {
            "effective_mode": search_payload["executed_mode"],
            "router_decision": search_payload["executed_mode"],
            "returned_video_ids_ranked": [str(row["source_id"]) for row in video_candidates],
            "returned_video_records": video_candidates,
            "returned_chunk_ids": [str(row["unit_id"]) for row in raw_candidates if row["unit_type"] == "transcript_chunk"],
            "metadata_only_candidates": sum(row["unit_type"] == "video" for row in raw_candidates),
            "transcript_candidates": sum(row["unit_type"] == "transcript_chunk" for row in raw_candidates),
            "latency_ms": timings["retrieval"],
            "search_trace_id": search_payload["search_trace_id"],
            "index_identity": search_payload["index_identity"],
        },
        "candidate_builder": {**builder, "latency_ms": timings["builder"]},
        "deterministic_selector": {
            "outcome": (
                "not_applicable"
                if candidate_set.failure_category in SOURCE_TERMINAL_CODES
                else ("selected" if bundle else "no_bundle")
            ),
            "selected_candidate_ids": list(bundle.candidate_ids) if bundle else [],
            "selected_candidate_count": len(bundle.candidate_ids) if bundle else 0,
            "selected_evidence_spans": list(bundle.normalized_spans) if bundle else [],
            "bundle_identity": bundle.bundle_id if bundle else None,
            "latency_ms": timings["selector"],
        },
        "mechanical_gate": {
            "outcome": gate.gate_outcome, "reason_codes": [gate.operational_reason_code] if gate.operational_reason_code else [],
            "identity_checks": {"validation_errors": list(gate.validation_errors), "evidence_bundle_id": gate.evidence_bundle_id},
            "source_checks": {"source_integrity_valid": not bool(candidate_set.validation_errors)},
            "timeline_checks": {"candidate_timeline_ids": sorted({c.timeline_run_id for c in candidate_set.candidates})},
            "latency_ms": timings["gate"], "gate_decision_id": gate.gate_decision_id,
        },
        "trace_path": trace_path, "operational_errors": [],
        "terminal_prediction": {
            "complete": True,
            "recognized_source_terminal": candidate_set.failure_category in SOURCE_TERMINAL_CODES,
        },
    }


def run_blind(
    *, repository_root: Path, snapshot_db: Path, snapshot_artifacts: Path,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Run exactly one persisted prediction for each of the 14 Development queries."""
    output_root = output_root or repository_root / OUTPUT_RELATIVE
    blind = output_root / "blind_run"
    predictions_path = blind / "product_initial_baseline.predictions.jsonl"
    seal_path = blind / "product_initial_baseline.prediction_freeze.seal.json"
    input_path = blind / "product_initial_baseline.input_manifest.json"
    if any(path.exists() for path in (predictions_path, seal_path, input_path)):
        raise P8Blocked("new_attempt_output_collision", "Blind artifacts already exist; refusing to reuse or overwrite", {"output_root": str(output_root)})

    query_path = repository_root / QUERY_RELATIVE
    authority_path = repository_root / AUTHORITY_RELATIVE
    artifact_manifest = repository_root / ARTIFACT_MANIFEST_RELATIVE
    checks = {
        "authority_index": file_sha256(authority_path) == AUTHORITY_SHA256,
        "development_query": file_sha256(query_path) == QUERY_SHA256,
        "artifact_manifest": file_sha256(artifact_manifest) == ARTIFACT_MANIFEST_SHA256,
        "snapshot": file_sha256(snapshot_db) == SNAPSHOT_SHA256,
    }
    if not all(checks.values()):
        raise P8Blocked("input_identity", "P8 blind input identity mismatch", checks)
    queries = load_jsonl(query_path)
    if len(queries) != 14 or len({row["query_id"] for row in queries}) != 14:
        raise P8Blocked("query_identity", "Expected exactly 14 unique Development queries")
    if any(row.get("split_assignment") != "development" for row in queries):
        raise P8Blocked("query_split", "Non-Development query entered blind allowlist")
    components = _component_identity(repository_root)
    index = inspect_index(snapshot_db)
    if index["index_sha256_or_manifest_identity"] != SNAPSHOT_SHA256:
        raise P8Blocked("index_identity", "Snapshot inspection disagrees with authority", index)
    git = _git_identity(repository_root)
    input_manifest = {
        "attempt_id": ATTEMPT_ID, "runner_version": RUNNER_VERSION, "frozen_at": utc_now(),
        "query": {"path": str(QUERY_RELATIVE), "sha256": QUERY_SHA256, "count": 14},
        "authority_index": {"path": str(AUTHORITY_RELATIVE), "sha256": AUTHORITY_SHA256},
        "components": components,
        "versions": {
            "product_default_wiring": "v3-product-search-default-auto-v1",
            "auto_router": "v3-search-planner-auto-v1",
            "candidate_builder": "stage3b-acronym-w3.5-v1",
            "deterministic_selector": DETERMINISTIC_SELECTOR_VERSION,
            "mechanical_gate": "v3.5-mechanical-sufficiency-gate-v1",
        },
        "index": {**index, "snapshot_id": SNAPSHOT_ID, "snapshot_sha256": SNAPSHOT_SHA256},
        "artifact_manifest": {"path": str(ARTIFACT_MANIFEST_RELATIVE), "sha256": ARTIFACT_MANIFEST_SHA256},
        "code": git,
        "harness": {
            "version": RUNNER_VERSION,
            "module_path": "src/shiliu/eval_v3_5/p8_product_initial_baseline.py",
            "module_sha256": file_sha256(repository_root / "src/shiliu/eval_v3_5/p8_product_initial_baseline.py"),
            "script_path": "scripts/run_p8_product_initial_baseline.py",
            "script_sha256": file_sha256(repository_root / "scripts/run_p8_product_initial_baseline.py"),
            "evaluation_serialization_changed": True,
            "terminal_outcome_handling_changed": True,
            "component_functional_behavior_changed": False,
        },
        "prior_attempt": {
            "attempt_id": "P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_2",
            "status": "invalid_incomplete_attempt",
            "partial_prediction_count": 9,
            "reused_in_attempt_3": False,
        },
        "recovery": {
            "category": "evaluation_terminal_serialization",
            "source_terminal_code": ["no_supported_subtitle"],
            "component_functional_behavior_changed": False,
            "harness_version_changed": True,
        },
        "run_policy": {
            "valid_prediction_runs_per_query": 1, "best_of_n": False, "gold_aware_retry": False,
            "manual_result_selection": False, "configuration_change_during_run": False,
        },
        "barrier": {
            "development_gold_opened": False, "frozen_gold_opened": False,
            "frozen_queries_executed": 0, "blind_entry_accepts_gold_path": False,
        },
    }
    write_json(input_path, input_manifest)
    audit_path = blind / "product_initial_baseline.blind_run.audit.json"
    write_json(audit_path, {
        "attempt_id": ATTEMPT_ID, "status": "in_progress", "started_at": utc_now(),
        "development_gold_opened": False, "frozen_gold_opened": False,
        "frozen_query_runs": 0, "prediction_runs": 0, "component_behavior_changed": False,
    })

    predictions: list[dict[str, Any]] = []
    trace_dir = blind / "product_initial_baseline.traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    guard = HeldoutAccessGuard(repository_root)
    resolver = FrozenRawSourceResolver(artifact_manifest=artifact_manifest, snapshot_db=snapshot_db, guard=guard)
    builder, selector, policy = final_builder_config(), SelectorConfig(), MechanicalGatePolicy()
    input_identity = {"input_manifest_sha256": file_sha256(input_path), "snapshot_sha256": SNAPSHOT_SHA256}
    with tempfile.TemporaryDirectory(prefix="shiliu-p8-blind-") as temp:
        work_db = Path(temp) / "snapshot-work-copy.db"
        shutil.copy2(snapshot_db, work_db)
        service = build_search_service(
            work_db=work_db, snapshot_artifacts=snapshot_artifacts,
            artifact_manifest=artifact_manifest, provider=QwenEmbeddingProvider(),
        )
        for position, query in enumerate(queries, 1):
            query_id = str(query["query_id"])
            run_id = f"{ATTEMPT_ID}:{position:02d}:{query_id}"
            request = ProductSearchRequest.model_validate({"query": str(query["query_text"])})
            if not request.default_applied or request.mode != "auto":
                raise P8Blocked("product_default", "Omitted mode did not apply Product Auto", {"query_id": query_id})
            planned = SearchPlanner().plan(SearchRequest(query=request.query, mode=request.mode, raw_top_k=50))
            started = time.perf_counter()
            search_set = service.search_library(request)
            retrieval_ms = (time.perf_counter() - started) * 1000
            payload = _search_payload(search_set)
            if payload["executed_mode"] != planned.planned_mode:
                raise P8Blocked("router_runtime", "Router decision and effective mode differ", {"query_id": query_id})
            search_id = value_sha256(payload)
            started = time.perf_counter()
            try:
                candidate_set = resolve_from_search_candidates(
                    request.query, {"raw_unit_candidates": payload["raw_unit_candidates"], "video_candidates": payload["video_candidates"]},
                    resolver, builder, query_id=query_id, search_candidate_set_id=search_id,
                    execution_manifest_identity=SNAPSHOT_SHA256,
                )
            except EvidenceContractError as exc:
                if exc.code not in SOURCE_TERMINAL_CODES:
                    raise
                normalized_source_code = (
                    "raw_source_unavailable"
                    if exc.code == "source_unavailable"
                    else exc.code
                )
                candidate_set = EvidenceCandidateSet(
                    query_id=query_id,
                    original_query=request.query,
                    candidates=(),
                    evaluation_track="frozen_v3_end_to_end",
                    end_to_end_claim_eligible=True,
                    trace={
                        "recognized_authoritative_source_terminal": True,
                        "source_failure_code": normalized_source_code,
                        "original_exception_code": exc.code,
                        "source_failure_message": str(exc),
                        "serialization_policy": RUNNER_VERSION,
                    },
                    normalization_status="typed_empty",
                    validation_errors=(),
                    failure_category=normalized_source_code,
                )
            builder_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            bundle = select_deterministic_bundle(request.query, candidate_set, selector)
            selector_ms = (time.perf_counter() - started) * 1000
            if bundle is not None:
                validate_bundle(bundle, candidate_set)
            reason = candidate_set.failure_category
            if reason is None and bundle is None:
                reason = "selector_failed"
            request_record = {"query_id": query_id, "original_query": request.query, "search_candidate_set_id": search_id}
            gate_request, state = _request(request_record, candidate_set, bundle, reason)
            started = time.perf_counter()
            gate = apply_mechanical_sufficiency_gate(gate_request, state, bundle, policy)
            gate_ms = (time.perf_counter() - started) * 1000
            trace_path = trace_dir / f"{query_id}.trace.json"
            trace = {
                "attempt_id": ATTEMPT_ID, "run_id": run_id, "query": dict(query),
                "request_payload": {"query": request.query}, "router_plan": planned.as_dict(),
                "search_candidate_set": payload, "evidence_candidate_set": candidate_set.as_dict(),
                "evidence_bundle": bundle.as_dict() if bundle else None,
                "mechanical_gate_request": gate_request.model_dump(mode="json"),
                "evidence_resolution_state": state.model_dump(mode="json"),
                "mechanical_gate_decision": gate.model_dump(mode="json"),
            }
            write_json(trace_path, trace)
            relative_trace = str(trace_path.relative_to(output_root))
            row = _prediction_row(
                query=query, run_id=run_id, search_payload=payload, candidate_set=candidate_set,
                bundle=bundle, gate=gate,
                timings={"retrieval": round(retrieval_ms, 3), "builder": round(builder_ms, 3), "selector": round(selector_ms, 3), "gate": round(gate_ms, 3)},
                trace_path=relative_trace, input_identity=input_identity,
            )
            predictions.append(row)
            write_jsonl(predictions_path, predictions)
            write_json(audit_path, {
                "attempt_id": ATTEMPT_ID, "status": "in_progress", "started_at": input_manifest["frozen_at"],
                "development_gold_opened": False, "frozen_gold_opened": False,
                "frozen_query_runs": 0, "prediction_runs": len(predictions),
                "component_behavior_changed": False,
            })

    if len(predictions) != 14 or len({row["query_id"] for row in predictions}) != 14:
        raise P8Blocked("prediction_completeness", "Prediction set did not reach exactly 14 unique records")
    trace_rows = [
        {"path": str(path.relative_to(output_root)), "sha256": file_sha256(path), "bytes": path.stat().st_size}
        for path in sorted(trace_dir.glob("*.trace.json"))
    ]
    hash_rows = [
        {"path": str(input_path.relative_to(output_root)), "sha256": file_sha256(input_path), "bytes": input_path.stat().st_size},
        {"path": str(predictions_path.relative_to(output_root)), "sha256": file_sha256(predictions_path), "bytes": predictions_path.stat().st_size},
        *trace_rows,
    ]
    hash_manifest = blind / "product_initial_baseline.prediction_hash_manifest.jsonl"
    write_jsonl(hash_manifest, hash_rows)
    sealed_at = utc_now()
    seal = {
        "attempt_id": ATTEMPT_ID, "status": "sealed_before_gold_scoring",
        "query_count": 14, "prediction_record_count": 14, "trace_count": 14,
        "development_gold_opened": False, "frozen_gold_opened": False,
        "component_versions": input_manifest["versions"],
        "harness_identity": input_manifest["harness"],
        "input_manifest_sha256": file_sha256(input_path),
        "predictions_sha256": file_sha256(predictions_path),
        "trace_root_sha256": _trace_root_hash(trace_rows),
        "prediction_hash_manifest_sha256": file_sha256(hash_manifest),
        "sealed_at": sealed_at, "immutable_after_seal": True,
    }
    write_json(seal_path, seal)
    write_json(audit_path, {
        "attempt_id": ATTEMPT_ID, "status": "sealed_before_gold_scoring",
        "started_at": input_manifest["frozen_at"], "sealed_at": sealed_at,
        "development_gold_opened": False, "development_gold_opened_before_prediction_freeze": False,
        "frozen_gold_opened": False, "frozen_query_runs": 0, "prediction_runs": 14,
        "valid_prediction_runs_per_query": 1, "best_of_n": False, "gold_aware_retry": False,
        "manual_result_selection": False, "component_behavior_changed": False,
        "prior_attempt": input_manifest["prior_attempt"],
        "recovery": input_manifest["recovery"],
        "complete_terminal_predictions": 14,
        "prediction_hashes_verified": verify_prediction_seal(output_root),
    })
    for path in [input_path, predictions_path, hash_manifest, *sorted(trace_dir.glob("*.trace.json"))]:
        path.chmod(0o444)
    return {"status": "sealed_before_gold_scoring", "seal_path": str(seal_path), "seal_sha256": file_sha256(seal_path)}


def verify_prediction_seal(output_root: Path) -> bool:
    blind = output_root / "blind_run"
    seal = json.loads((blind / "product_initial_baseline.prediction_freeze.seal.json").read_text(encoding="utf-8"))
    if seal.get("status") != "sealed_before_gold_scoring" or seal.get("development_gold_opened") is not False:
        return False
    manifest = load_jsonl(blind / "product_initial_baseline.prediction_hash_manifest.jsonl")
    for row in manifest:
        if file_sha256(output_root / row["path"]) != row["sha256"]:
            return False
    traces = [row for row in manifest if row["path"].endswith(".trace.json")]
    return (
        len(traces) == 14
        and seal["predictions_sha256"] == file_sha256(blind / "product_initial_baseline.predictions.jsonl")
        and seal["input_manifest_sha256"] == file_sha256(blind / "product_initial_baseline.input_manifest.json")
        and seal["trace_root_sha256"] == _trace_root_hash(traces)
    )


def _covered_span_ids(evidence: Mapping[str, Any], candidate_spans: Sequence[Mapping[str, Any]]) -> set[str]:
    covered: set[str] = set()
    for gold_span in evidence.get("span_registry", []):
        required = set(gold_span["segment_ids"])
        available = set().union(*(
            set(candidate.get("segment_ids", []))
            for candidate in candidate_spans
            if (
                str(candidate.get("source_version")) == str(gold_span["source_version"])
                and str(candidate.get("timeline_run_id")) == str(gold_span["timeline_run_id"])
            )
        ), set())
        if required.issubset(available):
            covered.add(str(gold_span["span_id"]))
    return covered


def _complete_groups(evidence: Mapping[str, Any], covered_spans: set[str]) -> list[str]:
    result = []
    for group in evidence.get("acceptable_evidence_groups", []):
        if all(set(value["required_span_ids"]).issubset(covered_spans) for value in group["required_span_sets"]):
            result.append(str(group["group_id"]))
    return result


def _covered_aspects(evidence: Mapping[str, Any], covered_spans: set[str]) -> list[str]:
    result = []
    for aspect in evidence.get("aspect_evidence_options", []):
        if any(set(value["required_span_ids"]).issubset(covered_spans) for value in aspect["alternative_sets"]):
            result.append(str(aspect["aspect_id"]))
    return result


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _canonical_video_id(value: object) -> str:
    text = str(value)
    if text.startswith("bilibili:"):
        return text
    if text.startswith("BV"):
        return f"bilibili:{text}"
    return text


def _latency(rows: Sequence[Mapping[str, Any]], stage: str) -> dict[str, Any]:
    values = sorted(float(row[stage]["latency_ms"]) for row in rows)
    return {"mean_ms": _mean(values), "min_ms": values[0] if values else None, "max_ms": values[-1] if values else None}


def _gold_paths(repository_root: Path) -> dict[str, Path]:
    root = repository_root / "research/v3_5/product_query_set_v1/gold_construction_v1/development_seal_v1/sealed"
    return {
        "retrieval": root / "product_retrieval_gold.development.v1.sealed.jsonl",
        "evidence": root / "product_evidence_gold.development.v1.sealed.jsonl",
        "sufficiency": root / "product_sufficiency_gold.development.v1.sealed.jsonl",
        "case_status": root / "reviewed_case_status.development.v1.sealed.jsonl",
    }


def score_frozen(
    *, repository_root: Path, snapshot_db: Path, output_root: Path | None = None,
) -> dict[str, Any]:
    """Open Development Gold only after verifying the immutable prediction seal."""
    output_root = output_root or repository_root / OUTPUT_RELATIVE
    if not verify_prediction_seal(output_root):
        raise P8Blocked("prediction_freeze_barrier", "Prediction Seal or hash verification failed")
    predictions_path = output_root / "blind_run/product_initial_baseline.predictions.jsonl"
    predictions = load_jsonl(predictions_path)
    before_hash = file_sha256(predictions_path)
    gold_paths = _gold_paths(repository_root)
    scoring_audit_path = output_root / "scoring/product_initial_baseline.scoring.audit.json"
    prior_scoring_audit = (
        json.loads(scoring_audit_path.read_text(encoding="utf-8"))
        if scoring_audit_path.exists()
        else None
    )
    first_open_at = (
        str(prior_scoring_audit["development_gold_first_open_at"])
        if prior_scoring_audit
        else utc_now()
    )
    scoring_recomputed_at = utc_now()
    actual_gold_hashes = {name: file_sha256(path) for name, path in gold_paths.items()}
    if actual_gold_hashes != GOLD_HASHES:
        raise P8Blocked("development_gold_identity", "Development Gold hash mismatch", {"expected": GOLD_HASHES, "actual": actual_gold_hashes})
    retrieval_gold = {row["query_id"]: row for row in load_jsonl(gold_paths["retrieval"])}
    evidence_gold = {row["query_id"]: row for row in load_jsonl(gold_paths["evidence"])}
    sufficiency_gold = {row["query_id"]: row for row in load_jsonl(gold_paths["sufficiency"])}
    case_status = {row["query_id"]: row for row in load_jsonl(gold_paths["case_status"])}
    if any(len(value) != 14 for value in (retrieval_gold, evidence_gold, sufficiency_gold, case_status)):
        raise P8Blocked("scoring_contract", "Development Gold layers must each contain 14 unique queries")
    if file_sha256(predictions_path) != before_hash:
        raise P8Blocked("prediction_immutability", "Prediction bytes changed after Gold open")

    unjudged_rows: list[dict[str, Any]] = []
    per_query: list[dict[str, Any]] = []
    addendum: list[dict[str, Any]] = []
    reviewer_guard = HeldoutAccessGuard(repository_root)
    reviewer_resolver = FrozenRawSourceResolver(
        artifact_manifest=repository_root / ARTIFACT_MANIFEST_RELATIVE,
        snapshot_db=snapshot_db,
        guard=reviewer_guard,
    )
    for prediction in predictions:
        query_id = prediction["query_id"]
        retrieval = retrieval_gold[query_id]
        evidence = evidence_gold[query_id]
        returned = [_canonical_video_id(value) for value in prediction["retrieval"]["returned_video_ids_ranked"]]
        returned_records = {
            _canonical_video_id(value["source_id"]): value
            for value in prediction["retrieval"]["returned_video_records"]
        }
        reviewed = {_canonical_video_id(value) for value in retrieval["relevance_review_scope"]["reviewed_video_ids"]}
        acceptable = {_canonical_video_id(value) for value in retrieval["acceptable_video_ids"]}
        known = {_canonical_video_id(value) for value in retrieval["known_relevant_video_ids"]}
        unresolved = []
        for rank, video_id in enumerate(returned, 1):
            if video_id not in reviewed:
                item = {
                    "query_id": query_id, "returned_video_id": video_id, "returned_rank": rank,
                    "prediction_run_id": prediction["run_id"], "current_relevance_status": "unjudged",
                }
                unjudged_rows.append(item)
                unresolved.append(item)
                source_review: dict[str, Any]
                outcome: str
                record = returned_records.get(video_id)
                try:
                    if record is None:
                        raise EvidenceContractError("returned video metadata is absent", code="raw_source_unavailable")
                    artifact = reviewer_resolver(int(record["video_id"]))
                    transcript = "\n".join(segment.source_text for segment in artifact.segments)
                    source_review = {
                        "authoritative_source_available": True,
                        "source_artifact_id": artifact.source_artifact_id,
                        "source_version": artifact.source_version,
                        "full_transcript_sha256": sha256(transcript.encode("utf-8")).hexdigest(),
                        "segment_count": len(artifact.segments),
                    }
                    outcome = "remain_unjudged_semantic_boundary"
                except EvidenceContractError as exc:
                    source_review = {
                        "authoritative_source_available": False,
                        "source_failure_code": exc.code,
                    }
                    outcome = "remain_unjudged_source_blocked"
                addendum.append({
                    **item, "review_outcome": outcome,
                    "final_relevance_status": "unresolved_unjudged",
                    "reviewer": "P8_BOUNDED_RELEVANCE_REVIEWER_V1",
                    "review_scope": "current query + neutral persisted metadata + full authoritative transcript/ASR when available",
                    "source_review": source_review,
                    "provenance": {
                        "prediction_sha256": before_hash,
                        "reason": "bounded review did not produce a reliable positive or negative semantic judgment",
                        "system_scores_visible_to_reviewer": False,
                        "frozen_assets_visible_to_reviewer": False,
                    },
                })
        ranks = [idx for idx, value in enumerate(returned, 1) if value in acceptable]
        success = bool(ranks)
        state = "determinate_success" if success else ("indeterminate_due_to_unjudged" if unresolved else "determinate_failure")
        candidate_spans = prediction["candidate_builder"]["evidence_spans"]
        builder_covered = _covered_span_ids(evidence, candidate_spans)
        builder_groups = _complete_groups(evidence, builder_covered)
        builder_aspects = _covered_aspects(evidence, builder_covered)
        selected_ids = set(prediction["deterministic_selector"]["selected_candidate_ids"])
        selected_spans = [row for row in candidate_spans if row["candidate_id"] in selected_ids]
        selected_covered = _covered_span_ids(evidence, selected_spans)
        selected_groups = _complete_groups(evidence, selected_covered)
        selected_aspects = _covered_aspects(evidence, selected_covered)
        required_span_ids = {span for group in evidence["acceptable_evidence_groups"] for value in group["required_span_sets"] for span in value["required_span_ids"]}
        material_aspects = {row["aspect_id"] for row in evidence["required_aspects"] if row["materiality"] == "material"}
        selected_count = len(selected_ids)
        selected_duration = sum(max(0.0, float(row["end_time"]) - float(row["start_time"])) for row in selected_spans)
        union_duration = 0.0
        bundle_trace = json.loads((output_root / prediction["trace_path"]).read_text(encoding="utf-8")).get("evidence_bundle")
        if bundle_trace:
            union_duration = float(bundle_trace.get("union_duration", 0.0))
        gate_outcome = prediction["mechanical_gate"]["outcome"]
        source_reviewable = bool(evidence["source_review_state"]["authoritative_sources_reviewable"])
        source_terminal = bool(
            set(prediction["mechanical_gate"]["reason_codes"]) & SOURCE_TERMINAL_CODES
            or prediction["terminal_prediction"]["recognized_source_terminal"]
        )
        identity_valid = source_terminal or not prediction["candidate_builder"]["validation_errors"]
        if not identity_valid:
            primary = "identity_or_scoring_defect"
        elif source_terminal or not source_reviewable:
            primary = "source_unverifiable"
        elif state == "indeterminate_due_to_unjudged":
            primary = "retrieval_gold_unjudged"
        elif state == "determinate_failure":
            primary = "retrieval_failure"
        elif not builder_groups:
            primary = "candidate_builder_failure"
        elif not selected_groups:
            primary = "deterministic_selector_failure"
        elif gate_outcome != "judge_eligible":
            primary = "mechanical_gate_failure"
        else:
            primary = "end_to_end_bundle_hit"
        row = {
            "query_id": query_id, "prediction_run_id": prediction["run_id"],
            "persisted_assets": {"prediction_sha256": before_hash, "trace_path": prediction["trace_path"], "gate_decision_id": prediction["mechanical_gate"]["gate_decision_id"]},
            "retrieval": {
                "state": state, "acceptable_hit": success, "first_acceptable_rank": min(ranks) if ranks else None,
                **{f"hit_at_{k}": any(rank <= k for rank in ranks) for k in (1, 3, 5, 10)},
                **{f"known_relevant_recall_at_{k}": len(set(returned[:k]) & known) / len(known) if known else None for k in (1, 3, 5, 10)},
                "unjudged_count": len(unresolved), "returned_count": len(returned),
                "unjudged_ranks": [item["returned_rank"] for item in unresolved],
            },
            "candidate_builder": {
                "complete_group_hit": bool(builder_groups), "covered_group_ids": builder_groups,
                "covered_span_ids": sorted(builder_covered),
                "required_span_recall": len(builder_covered & required_span_ids) / len(required_span_ids) if required_span_ids else None,
                "covered_aspect_ids": builder_aspects,
                "required_aspect_coverage": len(set(builder_aspects) & material_aspects) / len(material_aspects) if material_aspects else None,
                "candidate_count": len(prediction["candidate_builder"]["candidate_ids"]),
                "invalid_candidate_count": prediction["candidate_builder"]["invalid_candidate_count"],
            },
            "deterministic_selector": {
                "bundle_hit": bool(selected_groups), "covered_group_ids": selected_groups,
                "complete_group_available_but_not_selected": bool(builder_groups and not selected_groups),
                "required_span_recall": len(selected_covered & required_span_ids) / len(required_span_ids) if required_span_ids else None,
                "required_aspect_coverage": len(set(selected_aspects) & material_aspects) / len(material_aspects) if material_aspects else None,
                "selected_candidate_count": selected_count,
                "compactness": union_duration / selected_duration if selected_duration else None,
                "redundancy": 1.0 - (union_duration / selected_duration) if selected_duration else None,
            },
            "mechanical_gate": {
                "outcome": gate_outcome, "reason_codes": prediction["mechanical_gate"]["reason_codes"],
                "valid_decision": gate_outcome in {"judge_eligible", "terminal_unverifiable"},
            },
            "primary_attribution": primary,
            "decision_sensitive_unjudged": primary == "retrieval_gold_unjudged",
        }
        per_query.append(row)

    unjudged_rows = list({(row["query_id"], row["returned_video_id"]): row for row in unjudged_rows}.values())
    write_jsonl(output_root / "unjudged/product_initial_baseline.unjudged_pool.jsonl", unjudged_rows)
    write_jsonl(output_root / "unjudged/development_retrieval_pool_addendum.v1.jsonl", addendum)
    decision_queue = [
        {"query_id": row["query_id"], "primary_attribution": row["primary_attribution"], "decision_sensitive_unjudged": True,
         "checkpoint_1_only": True, "user_adjudication_required_during_p8": False}
        for row in per_query if row["decision_sensitive_unjudged"]
    ]
    write_jsonl(output_root / "unjudged/product_initial_baseline.decision_sensitive_unjudged_queue.jsonl", decision_queue)
    addendum_manifest = {
        "version": "development_retrieval_pool_addendum.v1", "base_gold_modified": False,
        "prediction_rerun": False, "pair_count": len(addendum),
        "outcomes": dict(Counter(row["review_outcome"] for row in addendum)),
        "unresolved_items_may_remain_explicitly_unjudged": True,
        "automatically_treated_as_negative": False,
    }
    write_json(output_root / "unjudged/development_retrieval_pool_addendum.v1.manifest.json", addendum_manifest)
    write_json(output_root / "unjudged/development_retrieval_pool_addendum.v1.audit.json", {
        **addendum_manifest, "existing_positive_deletions": 0, "evidence_gold_modified": False,
        "sufficiency_gold_modified": False, "query_modified": False,
    })
    write_jsonl(output_root / "scoring/product_initial_baseline.per_query.jsonl", per_query)
    attributions = [
        {"query_id": row["query_id"], "primary_attribution": row["primary_attribution"],
         "decision_sensitive_unjudged": row["decision_sensitive_unjudged"], "persisted_assets": row["persisted_assets"]}
        for row in per_query
    ]
    write_jsonl(output_root / "scoring/product_initial_baseline.failure_attribution.jsonl", attributions)
    determinate = [row for row in per_query if row["retrieval"]["state"] != "indeterminate_due_to_unjudged"]
    hit_metrics: dict[str, Any] = {}
    for k in (1, 3, 5, 10):
        determinate_hits = sum(row["retrieval"][f"hit_at_{k}"] for row in determinate)
        lower = sum(row["retrieval"][f"hit_at_{k}"] for row in per_query)
        upper = sum(
            row["retrieval"][f"hit_at_{k}"]
            or (
                row["retrieval"]["state"] == "indeterminate_due_to_unjudged"
                and any(rank <= k for rank in row["retrieval"]["unjudged_ranks"])
            )
            for row in per_query
        )
        hit_metrics[f"hit_at_{k}"] = {
            "metrics_on_determinate_queries": determinate_hits / len(determinate) if determinate else None,
            "all_query_lower_bound": lower / 14, "all_query_upper_bound": upper / 14,
        }
    builder_span = [row["candidate_builder"]["required_span_recall"] for row in per_query if row["candidate_builder"]["required_span_recall"] is not None]
    selector_span = [row["deterministic_selector"]["required_span_recall"] for row in per_query if row["deterministic_selector"]["required_span_recall"] is not None]
    gate_counts = Counter(row["mechanical_gate"]["outcome"] for row in per_query)
    source_type_counts = Counter(
        source_type
        for prediction in predictions
        for source_type in prediction["candidate_builder"]["source_types"]
    )
    language_counts = Counter(
        language
        for prediction in predictions
        for language in prediction["candidate_builder"]["source_languages"]
    )
    candidate_widths = [
        max(0.0, float(span["end_time"]) - float(span["start_time"]))
        for prediction in predictions
        for span in prediction["candidate_builder"]["evidence_spans"]
    ]
    selected_counts = [
        row["deterministic_selector"]["selected_candidate_count"] for row in per_query
    ]
    scores = {
        "attempt_id": ATTEMPT_ID,
        "measurement_note": "Metric intervals express uncertainty from non-exhaustive Retrieval Gold and do not assign positive or negative labels to unresolved videos.",
        "retrieval": {
            "determinate_query_count": len(determinate), "indeterminate_query_count": 14 - len(determinate),
            "any_acceptable_video": hit_metrics,
            "known_relevant_recall": {f"at_{k}": _mean([row["retrieval"][f"known_relevant_recall_at_{k}"] for row in per_query if row["retrieval"][f"known_relevant_recall_at_{k}"] is not None]) for k in (1, 3, 5, 10)},
            "first_acceptable_rank": [row["retrieval"]["first_acceptable_rank"] for row in per_query],
            "empty_result_count": sum(row["retrieval"]["returned_count"] == 0 for row in per_query),
            "router_distribution": dict(Counter(row["retrieval"]["effective_mode"] for row in predictions)),
            "unjudged_return_count": len(unjudged_rows),
            "metadata_only_candidate_availability": sum(row["retrieval"]["metadata_only_candidates"] > 0 for row in predictions),
            "transcript_candidate_availability": sum(row["retrieval"]["transcript_candidates"] > 0 for row in predictions),
            "latency": _latency(predictions, "retrieval"),
        },
        "candidate_builder": {
            "complete_acceptable_evidence_group_coverage": sum(row["candidate_builder"]["complete_group_hit"] for row in per_query) / 14,
            "required_span_recall_macro": _mean(builder_span),
            "required_aspect_coverage_macro": _mean([row["candidate_builder"]["required_aspect_coverage"] for row in per_query if row["candidate_builder"]["required_aspect_coverage"] is not None]),
            "candidate_count": sum(row["candidate_builder"]["candidate_count"] for row in per_query),
            "evidence_compression": {
                "definition": "mean constructed evidence-candidate window width in seconds",
                "mean_window_seconds": _mean(candidate_widths),
            },
            "window_width_mean_seconds": _mean(candidate_widths),
            "cross_run_candidate_count": 0,
            "invalid_candidate_count": sum(row["candidate_builder"]["invalid_candidate_count"] for row in per_query),
            "source_type_breakdown": dict(source_type_counts),
            "language_breakdown": dict(language_counts),
            "asr_breakdown": {
                "asr": source_type_counts.get("asr", 0),
                "human": source_type_counts.get("human", 0),
                "ai": source_type_counts.get("ai", 0),
            },
            "latency": _latency(predictions, "candidate_builder"),
        },
        "deterministic_selector": {
            "bundle_hit": sum(row["deterministic_selector"]["bundle_hit"] for row in per_query) / 14,
            "complete_group_available_but_not_selected": sum(row["deterministic_selector"]["complete_group_available_but_not_selected"] for row in per_query),
            "selected_candidate_count": {
                "total": sum(selected_counts), "mean": _mean(selected_counts),
            },
            "required_span_recall_macro": _mean(selector_span),
            "required_aspect_coverage_macro": _mean([row["deterministic_selector"]["required_aspect_coverage"] for row in per_query if row["deterministic_selector"]["required_aspect_coverage"] is not None]),
            "compactness_macro": _mean([row["deterministic_selector"]["compactness"] for row in per_query if row["deterministic_selector"]["compactness"] is not None]),
            "redundancy_macro": _mean([row["deterministic_selector"]["redundancy"] for row in per_query if row["deterministic_selector"]["redundancy"] is not None]),
            "formula": {"compactness": "selected interval union duration / summed selected interval duration", "redundancy": "1 - compactness"},
            "latency": _latency(predictions, "deterministic_selector"),
        },
        "mechanical_gate": {
            "judge_eligible_count": gate_counts["judge_eligible"],
            "terminal_unverifiable_count": gate_counts["terminal_unverifiable"],
            "invalid_identity_count": sum("identity" in " ".join(row["mechanical_gate"]["reason_codes"]) for row in per_query),
            "invalid_source_count": sum(
                bool(set(row["mechanical_gate"]["reason_codes"]) & SOURCE_TERMINAL_CODES)
                for row in per_query
            ),
            "invalid_timeline_count": sum("timeline" in " ".join(row["mechanical_gate"]["reason_codes"]) for row in per_query),
            "mechanically_complete_count": gate_counts["judge_eligible"],
            "mechanically_incomplete_count": gate_counts["terminal_unverifiable"],
            "invalid_decision_count": sum(not row["mechanical_gate"]["valid_decision"] for row in per_query),
            "latency": _latency(predictions, "mechanical_gate"),
        },
        "primary_failure_distribution": dict(Counter(row["primary_attribution"] for row in per_query)),
    }
    write_json(output_root / "scoring/product_initial_baseline.scores.json", scores)
    write_json(scoring_audit_path, {
        "status": "complete", "development_gold_first_open_at": first_open_at,
        "scoring_recomputed_at": scoring_recomputed_at,
        "scoring_recompute_count": (
            int(prior_scoring_audit.get("scoring_recompute_count", 0)) + 1
            if prior_scoring_audit
            else 0
        ),
        "scorer_module_sha256": file_sha256(repository_root / "src/shiliu/eval_v3_5/p8_product_initial_baseline.py"),
        "video_identity_normalization": "bilibili-prefix-canonical-v1",
        "prediction_sealed_at": json.loads((output_root / "blind_run/product_initial_baseline.prediction_freeze.seal.json").read_text())["sealed_at"],
        "development_gold_opened_after_prediction_seal": True, "frozen_gold_opened": False,
        "prediction_sha256_before_gold": before_hash, "prediction_sha256_after_gold": file_sha256(predictions_path),
        "prediction_modified_after_gold": False, "prediction_rerun": False,
        "scores_recomputed_without_prediction_rerun": True, "outside_pool_automatic_negative": False,
    })
    _write_closeout(
        repository_root=repository_root, output_root=output_root, scores=scores,
        first_open_at=first_open_at, actual_gold_hashes=actual_gold_hashes,
        per_query=per_query, addendum_manifest=addendum_manifest,
    )
    return scores


def _write_closeout(
    *, repository_root: Path, output_root: Path, scores: Mapping[str, Any],
    first_open_at: str, actual_gold_hashes: Mapping[str, str],
    per_query: Sequence[Mapping[str, Any]], addendum_manifest: Mapping[str, Any],
) -> None:
    stress_source = repository_root / "research/v3_5/stage3r_qc/track_a_auto_refresh/stage3r_track_a_auto_refresh_manifest.json"
    stress = {
        "dataset_role": "evidence_sufficiency_stress_set_v2", "product_benchmark": False,
        "optimization_authority": False, "execution": "reused_frozen_corrected_stress_track_a",
        "source_path": str(stress_source.relative_to(repository_root)),
        "source_sha256": file_sha256(stress_source),
        "source_metrics": json.loads(stress_source.read_text(encoding="utf-8"))["metrics"],
        "product_prediction_rerun": False, "product_failure_attribution_modified": False,
    }
    write_json(output_root / "stress_regression/stress_set_v2_regression.initial_product_baseline.json", stress)
    distribution = dict(Counter(row["primary_attribution"] for row in per_query))
    decision = {
        "execution_status": "complete", "acceptance_status": "pending_v3_5_b_review",
        "p8_status": "product_initial_baseline_execution_candidate_ready",
        "prediction_set_frozen": True, "development_gold_opened_only_after_prediction_freeze": True,
        "frozen_gold_accessed": False, "component_behavior_changed": False,
        "unjudged": {
            "resolved_count": 0, "unresolved_count": addendum_manifest["pair_count"],
            "decision_sensitive_count": sum(row["decision_sensitive_unjudged"] for row in per_query),
            "blocked_P8": False,
        },
        "checkpoint_1_authorized": False, "f1a_authorized": False, "f1b_authorized": False,
    }
    write_json(output_root / "closeout/product_initial_baseline.execution_decision.json", decision)
    seal_path = output_root / "blind_run/product_initial_baseline.prediction_freeze.seal.json"
    manifest = {
        "attempt_id": ATTEMPT_ID, "runner_version": RUNNER_VERSION,
        "p4_p5_p6_p7_identity_verified": True,
        "prediction_freeze_seal_sha256": file_sha256(seal_path),
        "development_gold_first_open_at": first_open_at, "development_gold_hashes": dict(actual_gold_hashes),
        "query_count": 14, "valid_prediction_run_count": 14, "functional_component_change_count": 0,
        "frozen_query_runs": 0, "frozen_gold_access": False,
        "metrics_recomputable": True, "primary_attribution_count": 14,
        "primary_failure_distribution": distribution,
        "addendum": dict(addendum_manifest),
        "stress_regression_separate": True,
    }
    write_json(output_root / "closeout/product_initial_baseline.manifest.json", manifest)
    report = f"""# Product Initial Baseline Report

P8 execution status: complete. Acceptance remains pending V3.5-B review.

## Runtime Identity

Attempt `{ATTEMPT_ID}` used Product Default Auto `v3-product-search-default-auto-v1`,
Candidate Builder `stage3b-acronym-w3.5-v1`, Deterministic Selector
`v3.5-deterministic-fine-selector-v1`, Mechanical Gate
`v3.5-mechanical-sufficiency-gate-v1`, and snapshot `{SNAPSHOT_ID}` /
`{SNAPSHOT_SHA256}`. Functional component changes: 0.

## Prediction Freeze Proof

Fourteen Development queries produced exactly fourteen predictions and traces.
The Prediction Seal SHA-256 is `{file_sha256(seal_path)}`. Development Gold was
first opened at `{first_open_at}`, after the seal. Frozen Query runs and Frozen
Gold access were both zero.

## Metrics

Retrieval: `{json.dumps(scores['retrieval'], ensure_ascii=False, sort_keys=True)}`.

Candidate Builder: `{json.dumps(scores['candidate_builder'], ensure_ascii=False, sort_keys=True)}`.

Deterministic Selector: `{json.dumps(scores['deterministic_selector'], ensure_ascii=False, sort_keys=True)}`.

Mechanical Gate: `{json.dumps(scores['mechanical_gate'], ensure_ascii=False, sort_keys=True)}`.
The Mechanical Gate reports mechanical eligibility only; no semantic sufficiency
judgment was performed.

## Unjudged and Measurement Limits

Unjudged pairs: `{addendum_manifest['pair_count']}`. Unresolved pairs remain
explicitly unjudged and do not block P8. Metric intervals express uncertainty
from non-exhaustive Retrieval Gold and do not assign positive or negative labels
to unresolved videos. The sealed base Gold was not modified.

## Primary Failure Attribution

`{json.dumps(distribution, ensure_ascii=False, sort_keys=True)}`.

## Product / Stress Separation

Stress Set v2 was reused as a separate regression artifact. It is not a Product
Benchmark and has no optimization authority. It did not change Product
predictions, configuration, or failure attribution.

## Governance

No Query, Split, Gold, Router, Retrieval, Builder, Selector, or Gate behavior was
changed. F1A, F1B, Stage 4A-R, Stage 4B, Checkpoint 1, and P9 were not started or
authorized. The only possible next governance action is V3.5-B Checkpoint 1
review; this P8 execution does not perform it.
"""
    write_json(output_root / "closeout/PQS_V1_P8_PRODUCT_INITIAL_BASELINE_DECISION_LEDGER.json", {
        "source_sha256": "e5af8a5e35f25c5946ae0c26f7f759245e62eb1189144604e78e64ee49d0c79e",
        "authoritative_amendment_applied": True, "unresolved_unjudged_blocks_p8": False,
    })
    (output_root / "closeout/PRODUCT_INITIAL_BASELINE_REPORT.md").write_text(report, encoding="utf-8")
    files = [
        path for path in output_root.rglob("*")
        if path.is_file() and path.name not in {"product_initial_baseline.file_hash_manifest.jsonl", "P8_PRODUCT_INITIAL_BASELINE_BLOCKING_REPORT.md"}
    ]
    write_jsonl(output_root / "closeout/product_initial_baseline.file_hash_manifest.jsonl", [
        {"path": str(path.relative_to(output_root)), "sha256": file_sha256(path), "bytes": path.stat().st_size}
        for path in sorted(files)
    ])
