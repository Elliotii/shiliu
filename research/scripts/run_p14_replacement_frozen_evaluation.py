from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from typing import Any, Mapping

from shiliu.evidence.contracts import EvidenceContractError
from shiliu.evidence.stage3a import (
    EvidenceBundle,
    EvidenceCandidate,
    EvidenceCandidateSet,
    SelectorConfig,
    resolve_from_search_candidates,
    select_deterministic_bundle,
    validate_bundle,
)
from shiliu.evidence.stage4 import (
    EvidenceResolutionState,
    MechanicalGateDecision,
    MechanicalGatePolicy,
    SufficiencyRequest,
    apply_mechanical_sufficiency_gate,
    terminal_sufficiency_decision,
)
from shiliu.eval_v3_5.isolation import HeldoutAccessGuard
from shiliu.eval_v3_5.p8_product_initial_baseline import _search_payload, value_sha256
from shiliu.eval_v3_5.runtime_guard import (
    load_frozen_eval_runtime_config,
    preflight_frozen_eval_runtime,
)
from shiliu.eval_v3_5.stage3a import FrozenRawSourceResolver
from shiliu.eval_v3_5.stage3r import file_sha256, final_builder_config
from shiliu.eval_v3_5.stage3r_qc_phase_b_r import build_search_service
from shiliu.eval_v3_5.stage4a import _request
from shiliu.eval_v3_5.stage4b import (
    SEMANTIC_POLICY_VERSION,
    batch_prompt,
    hash_value,
    parse_batch_output,
    project_runtime_request,
    to_decision,
    validate_output,
)
from shiliu.retrieval.planner import SearchPlanner, SearchRequest
from shiliu.retrieval.product_search import ProductSearchRequest
from shiliu.retrieval.qwen import QwenEmbeddingProvider


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/v3_5/product_query_set_v1/p14_frozen_evaluation"
QUERY = ROOT / (
    "research/v3_5/product_query_set_v1/split_v1/frozen_locked/"
    "product_query_frozen_evaluation_v1.locked.jsonl"
)
RUNTIME_SEAL = OUT / "FROZEN_EVAL_RUNTIME_SEAL.json"
ENTRY_GATE = OUT / "P14_REPLACEMENT_ENTRY_GATE.json"
MANIFEST = OUT / "P14_REPLACEMENT_FORMAL_RUN_MANIFEST.json"
CASE_ROOT = OUT / "p14_replacement_cases"
TRACE_ROOT = OUT / "p14_replacement_traces"
WORK_ROOT = OUT / "p14_replacement_work"
RAW_RESPONSE = WORK_ROOT / "semantic_judge_batch.validated.json"
RESUME_AUDIT = OUT / "P14_REPLACEMENT_RESUME_AUDIT.jsonl"
PREDICTIONS = OUT / "p14_replacement_predictions.per_case.jsonl"
PREDICTION_FREEZE = OUT / "P14_REPLACEMENT_PREDICTIONS_FREEZE.json"
STATE = OUT / "replacement_provider_state"
QUERY_HASH = "faf962049281cba4c8a035e64068ef91b7cfa9159ea438cfe33052a225add44f"
MODEL = "gpt-5.6-terra"
SOURCE_TERMINAL_CODES = frozenset(
    {
        "no_supported_subtitle",
        "raw_source_unavailable",
        "source_unavailable",
        "source_unreadable",
        "title_only",
        "language_unresolved",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


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


def atomic_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    data = b"".join(canonical_bytes(row) + b"\n" for row in rows)
    atomic_write(path, data)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def load_base_runner() -> Any:
    path = ROOT / "research/scripts/run_p14_frozen_evaluation.py"
    spec = importlib.util.spec_from_file_location("p14_frozen_base_for_replacement", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Frozen P14 base runner import failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def append_resume_audit(event: Mapping[str, Any]) -> None:
    rows = load_jsonl(RESUME_AUDIT) if RESUME_AUDIT.exists() else []
    rows.append(dict(event))
    atomic_jsonl(RESUME_AUDIT, rows)


def artifact_payload_hash(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("artifact_hash", None)
    return stable_hash(payload)


def verify_complete_artifact(path: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = load_json(path)
    if value.get("completion_status") != "complete":
        raise RuntimeError(f"Incomplete Case artifact at completed path: {path}")
    if value.get("replacement_run_id") != manifest["replacement_run_id"]:
        raise RuntimeError(f"Replacement Run ID mismatch: {path}")
    if value.get("configuration_hash") != manifest["configuration_hash"]:
        raise RuntimeError(f"Configuration hash mismatch: {path}")
    if value.get("artifact_hash") != artifact_payload_hash(value):
        raise RuntimeError(f"Case artifact hash mismatch: {path}")
    trace_path = ROOT / value["trace_path"]
    if file_sha256(trace_path) != value["trace_hash"]:
        raise RuntimeError(f"Trace hash mismatch: {trace_path}")
    return value


def evidence_candidate_set_from_dict(value: Mapping[str, Any]) -> EvidenceCandidateSet:
    candidates = []
    for raw in value["candidates"]:
        item = dict(raw)
        item.pop("evidence_candidate_contract_version", None)
        for key in (
            "segment_ids",
            "original_ordinals",
            "parent_chunk_ids",
            "search_candidate_ids",
            "candidate_methods",
            "related_candidate_ids",
            "validation_errors",
        ):
            item[key] = tuple(item[key])
        candidates.append(EvidenceCandidate(**item))
    return EvidenceCandidateSet(
        query_id=str(value["query_id"]),
        original_query=str(value["original_query"]),
        candidates=tuple(candidates),
        evaluation_track=str(value["evaluation_track"]),
        end_to_end_claim_eligible=bool(value["end_to_end_claim_eligible"]),
        trace=dict(value["trace"]),
        normalization_status=str(value["normalization_status"]),
        validation_errors=tuple(value["validation_errors"]),
        failure_category=value.get("failure_category"),
    )


def evidence_bundle_from_dict(value: Mapping[str, Any] | None) -> EvidenceBundle | None:
    if value is None:
        return None
    item = dict(value)
    item.pop("evidence_bundle_contract_version", None)
    for key in (
        "source_artifact_ids",
        "source_versions",
        "timeline_run_ids",
        "candidate_ids",
        "normalized_spans",
        "source_texts",
        "validation_errors",
    ):
        item[key] = tuple(item[key])
    return EvidenceBundle(**item)


def verify_authorization() -> tuple[dict[str, Any], dict[str, Any]]:
    if os.environ.get("CODEX_SQLITE_HOME") != str(STATE.resolve()):
        raise RuntimeError("CODEX_SQLITE_HOME is not the authorized state directory")
    gate = load_json(ENTRY_GATE)
    if (
        gate.get("replacement_entry_gate") != "pass"
        or gate.get("replacement_formal_run_authorized") is not True
        or gate.get("new_run_id_created") is not False
        or gate.get("Frozen_Gold_opened") is not False
    ):
        raise RuntimeError("Replacement Entry Gate does not authorize execution")
    manifest = load_json(MANIFEST)
    if (
        manifest.get("maximum_new_run_ids") != 1
        or manifest.get("replacement_run_id_creation_ordinal") != 1
        or manifest.get("configuration_hash")
        != gate["frozen_configuration_hash"]
    ):
        raise RuntimeError("Replacement Manifest policy mismatch")
    runtime = load_frozen_eval_runtime_config(RUNTIME_SEAL)
    preflight = preflight_frozen_eval_runtime(runtime)
    if file_sha256(runtime.database.path) != runtime.database.sha256:
        raise RuntimeError("Frozen runtime database changed after manifest")
    return manifest, preflight


def prepare_case(
    *,
    base: Any,
    query: Mapping[str, Any],
    position: int,
    manifest: Mapping[str, Any],
    service: Any,
    resolver: FrozenRawSourceResolver,
    runtime: Any,
) -> dict[str, Any]:
    case_id = str(query["query_id"])
    run_id = f"{manifest['replacement_run_id']}:{position:02d}:{case_id}"
    typed_errors: list[dict[str, Any]] = []
    request = ProductSearchRequest.model_validate({"query": str(query["query_text"])})
    if not request.default_applied or request.mode != "auto":
        raise RuntimeError(f"Product Auto default not applied: {case_id}")
    plan = SearchPlanner().plan(
        SearchRequest(query=request.query, mode=request.mode, raw_top_k=50)
    )
    started = time.perf_counter()
    search_set = service.search_library(request)
    retrieval_ms = round((time.perf_counter() - started) * 1000, 3)
    search_payload = _search_payload(search_set)
    if search_payload["executed_mode"] != plan.planned_mode:
        raise RuntimeError(f"Router/runtime mismatch: {case_id}")
    search_id = value_sha256(search_payload)
    started = time.perf_counter()
    try:
        candidate_set = resolve_from_search_candidates(
            request.query,
            {
                "raw_unit_candidates": search_payload["raw_unit_candidates"],
                "video_candidates": search_payload["video_candidates"],
            },
            resolver,
            final_builder_config(),
            query_id=case_id,
            search_candidate_set_id=search_id,
            execution_manifest_identity=runtime.corpus_identity,
        )
    except EvidenceContractError as exc:
        if exc.code not in SOURCE_TERMINAL_CODES:
            raise
        normalized = (
            "raw_source_unavailable" if exc.code == "source_unavailable" else exc.code
        )
        candidate_set = EvidenceCandidateSet(
            query_id=case_id,
            original_query=request.query,
            candidates=(),
            evaluation_track="frozen_v3_end_to_end",
            end_to_end_claim_eligible=True,
            trace={
                "recognized_authoritative_source_terminal": True,
                "source_failure_code": normalized,
                "source_failure_message": str(exc),
            },
            normalization_status="typed_empty",
            validation_errors=(),
            failure_category=normalized,
        )
        typed_errors.append(
            {"stage": "builder", "code": normalized, "message": str(exc)}
        )
    builder_ms = round((time.perf_counter() - started) * 1000, 3)
    started = time.perf_counter()
    bundle = select_deterministic_bundle(
        request.query, candidate_set, SelectorConfig()
    )
    selector_ms = round((time.perf_counter() - started) * 1000, 3)
    if bundle is not None:
        validate_bundle(bundle, candidate_set)
    reason = candidate_set.failure_category
    if reason is None and bundle is None:
        reason = "selector_failed"
    gate_request, resolution = _request(
        {
            "query_id": case_id,
            "original_query": request.query,
            "search_candidate_set_id": search_id,
        },
        candidate_set,
        bundle,
        reason,
    )
    started = time.perf_counter()
    gate = apply_mechanical_sufficiency_gate(
        gate_request, resolution, bundle, MechanicalGatePolicy()
    )
    gate_ms = round((time.perf_counter() - started) * 1000, 3)
    runtime_request = None
    if gate.gate_outcome == "judge_eligible":
        runtime_request = project_runtime_request(
            gate_request,
            gate,
            bundle,
            query_language=str(query.get("query_language") or "zh"),
        )
    return {
        "completion_status": "incomplete",
        "replacement_run_id": manifest["replacement_run_id"],
        "configuration_hash": manifest["configuration_hash"],
        "query": dict(query),
        "run_id": run_id,
        "router_plan": plan.as_dict(),
        "search_candidate_set": search_payload,
        "evidence_candidate_set": candidate_set.as_dict(),
        "evidence_bundle": bundle.as_dict() if bundle else None,
        "sufficiency_request": gate_request.model_dump(mode="json"),
        "runtime_sufficiency_request": (
            runtime_request.model_dump(mode="json") if runtime_request else None
        ),
        "evidence_resolution_state": resolution.model_dump(mode="json"),
        "mechanical_gate_result": gate.model_dump(mode="json"),
        "typed_errors": typed_errors,
        "stage_latencies": {
            "retrieval_ms": retrieval_ms,
            "builder_ms": builder_ms,
            "selector_ms": selector_ms,
            "mechanical_gate_ms": gate_ms,
        },
    }


def obtain_judge_outputs(
    *, base: Any, work: list[dict[str, Any]]
) -> tuple[dict[str, Any], int, int, str | None]:
    eligible = [
        row for row in work if row["runtime_sufficiency_request"] is not None
    ]
    if not eligible:
        return {}, 0, 0, None
    requests = tuple(
        SufficiencyRequest.model_validate(row["runtime_sufficiency_request"])
        for row in eligible
    )
    if RAW_RESPONSE.exists():
        raw_state = load_json(RAW_RESPONSE)
        if (
            raw_state["replacement_run_id"] != work[0]["replacement_run_id"]
            or raw_state["configuration_hash"] != work[0]["configuration_hash"]
        ):
            raise RuntimeError("Persisted Judge batch cannot safely resume")
        raw = str(raw_state["raw"])
        latency_ms = int(raw_state["latency_ms"])
        retry_count = int(raw_state["retry_count"])
        persisted_query_ids = list(raw_state["eligible_query_ids"])
    else:
        runner = base.load_stage4b_runner()
        schema = (
            ROOT
            / "research/v3_5/product_query_set_v1/stage4b_incremental/"
            "semantic_judge_batch_output.schema.json"
        )
        raw, latency_ms, retry_count = runner._codex_call(
            batch_prompt(requests), schema
        )

        def parse_validate(value: str) -> tuple[Any, ...]:
            outputs = parse_batch_output(value, len(eligible))
            by_id = {output.query_id: output for output in outputs}
            for row, request in zip(eligible, requests):
                validate_output(
                    by_id[request.query_id],
                    request,
                    evidence_bundle_from_dict(row["evidence_bundle"]),
                )
            return outputs

        try:
            outputs = parse_validate(raw)
        except Exception as exc:
            repair_prompt = (
                batch_prompt(requests)
                + "\n\nMECHANICAL REPAIR: The prior output failed validation: "
                + str(exc)
                + ". Preserve your semantic status decisions, but for "
                "evidence_ids_used copy only exact full strings from that same "
                "item's evidence_bundle.candidate_ids. Never use span_id, "
                "segment_id, shortened IDs, or IDs from another item."
            )
            raw, repair_latency, _ = runner._codex_call(repair_prompt, schema)
            outputs = parse_validate(raw)
            latency_ms += repair_latency
            retry_count += 1
        atomic_json(
            RAW_RESPONSE,
            {
                "replacement_run_id": work[0]["replacement_run_id"],
                "configuration_hash": work[0]["configuration_hash"],
                "raw": raw,
                "raw_hash": sha256(raw.encode("utf-8")).hexdigest(),
                "eligible_query_ids": [
                    request.query_id for request in requests
                ],
                "latency_ms": latency_ms,
                "retry_count": retry_count,
                "validated_before_persistence": True,
                "persisted_at": utc_now(),
            },
        )
        persisted_query_ids = [request.query_id for request in requests]
    outputs = parse_batch_output(raw, len(persisted_query_ids))
    by_id = {output.query_id: output for output in outputs}
    for row, request in zip(eligible, requests):
        validate_output(
            by_id[request.query_id],
            request,
            evidence_bundle_from_dict(row["evidence_bundle"]),
        )
    return (
        {output.query_id: output for output in outputs},
        latency_ms,
        retry_count,
        sha256(raw.encode("utf-8")).hexdigest(),
    )


def finalize_case(
    *,
    base: Any,
    work: Mapping[str, Any],
    manifest: Mapping[str, Any],
    judge_outputs: Mapping[str, Any],
    judge_latency_ms: int,
    retry_count: int,
    raw_hash: str | None,
) -> dict[str, Any]:
    query = work["query"]
    case_id = str(query["query_id"])
    candidate_set = evidence_candidate_set_from_dict(work["evidence_candidate_set"])
    bundle = evidence_bundle_from_dict(work["evidence_bundle"])
    gate = MechanicalGateDecision.model_validate(work["mechanical_gate_result"])
    gate_request = SufficiencyRequest.model_validate(work["sufficiency_request"])
    runtime_request = (
        SufficiencyRequest.model_validate(work["runtime_sufficiency_request"])
        if work["runtime_sufficiency_request"]
        else None
    )
    resolution = EvidenceResolutionState.model_validate(
        work["evidence_resolution_state"]
    )
    called = gate.gate_outcome == "judge_eligible"
    if called:
        output = judge_outputs[case_id]
        decision = to_decision(output, runtime_request, bundle, judge_model=MODEL)
    elif gate.gate_outcome == "source_unverifiable":
        decision = terminal_sufficiency_decision(gate)
    else:
        decision = None
    trace_path = TRACE_ROOT / f"{gate.trace_id}.json"
    trace = {
        "replacement_formal_run_manifest_hash": file_sha256(MANIFEST),
        "runtime_seal_hash": file_sha256(RUNTIME_SEAL),
        "replacement_run_id": manifest["replacement_run_id"],
        "run_id": work["run_id"],
        "query": query,
        "router_plan": work["router_plan"],
        "search_candidate_set": work["search_candidate_set"],
        "evidence_candidate_set": work["evidence_candidate_set"],
        "evidence_bundle": work["evidence_bundle"],
        "sufficiency_request": work["sufficiency_request"],
        "runtime_sufficiency_request": work["runtime_sufficiency_request"],
        "evidence_resolution_state": resolution.model_dump(mode="json"),
        "mechanical_gate_result": gate.model_dump(mode="json"),
        "semantic_judge": {
            "called": called,
            "model": MODEL if called else None,
            "policy": SEMANTIC_POLICY_VERSION,
            "raw_response_hash": raw_hash if called else None,
            "retry_count": retry_count if called else 0,
        },
        "sufficiency_decision": (
            decision.model_dump(mode="json") if decision else None
        ),
        "typed_errors": work["typed_errors"],
    }
    atomic_json(trace_path, trace)
    prediction = base.prediction_summary(
        query=query,
        run_id=work["run_id"],
        search_payload=work["search_candidate_set"],
        candidate_set=candidate_set,
        bundle=bundle,
        gate=gate,
        decision=decision,
        request_hash=hash_value(
            runtime_request.model_dump(mode="json")
            if runtime_request
            else gate_request.model_dump(mode="json")
        ),
        timings=work["stage_latencies"],
        trace_path=trace_path,
        semantic_judge_called=called,
        judge_latency_ms=judge_latency_ms if called else 0,
        retries=retry_count if called else 0,
        typed_errors=work["typed_errors"],
    )
    prediction["replacement_run_id"] = manifest["replacement_run_id"]
    artifact = {
        "replacement_run_id": manifest["replacement_run_id"],
        "case_id": case_id,
        "query_hash": base.stable_hash(query),
        "prediction": prediction,
        "search_candidate_set_summary": prediction["search_candidate_set_summary"],
        "evidence_candidate_set_summary": prediction[
            "evidence_candidate_set_summary"
        ],
        "evidence_bundle": prediction["evidence_bundle"],
        "mechanical_gate_result": prediction["mechanical_gate_result"],
        "sufficiency_decision_or_null": prediction[
            "sufficiency_decision_or_null"
        ],
        "trace": trace,
        "trace_path": relative(trace_path),
        "trace_hash": file_sha256(trace_path),
        "component_versions": prediction["component_versions"],
        "configuration_hash": manifest["configuration_hash"],
        "completion_status": "complete",
        "completed_at": utc_now(),
    }
    artifact["artifact_hash"] = artifact_payload_hash(artifact)
    case_path = CASE_ROOT / f"{case_id}.json"
    atomic_json(case_path, artifact)
    return artifact


def predict() -> dict[str, Any]:
    manifest, runtime_preflight = verify_authorization()
    base = load_base_runner()
    if PREDICTIONS.exists() or PREDICTION_FREEZE.exists():
        raise RuntimeError("Replacement Predictions already frozen")
    if file_sha256(QUERY) != QUERY_HASH:
        raise RuntimeError("Frozen Query hash mismatch")
    queries = load_jsonl(QUERY)
    if len(queries) != 10 or len({str(row["query_id"]) for row in queries}) != 10:
        raise RuntimeError("Frozen Query set must contain 10 unique cases")
    if any(row.get("split_assignment") != "frozen_evaluation" for row in queries):
        raise RuntimeError("Non-Frozen query entered replacement run")
    CASE_ROOT.mkdir(parents=True, exist_ok=True)
    TRACE_ROOT.mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    existing_cases = {
        path.stem: verify_complete_artifact(path, manifest)
        for path in sorted(CASE_ROOT.glob("*.json"))
    }
    prior_state_exists = bool(
        existing_cases
        or list(WORK_ROOT.glob("*.incomplete.json"))
        or RAW_RESPONSE.exists()
        or RESUME_AUDIT.exists()
    )
    before_hashes = {
        case_id: file_sha256(CASE_ROOT / f"{case_id}.json")
        for case_id in existing_cases
    }
    append_resume_audit(
        {
            "replacement_run_id": manifest["replacement_run_id"],
            "event": "same_run_id_resume" if prior_state_exists else "initial_execution",
            "completed_cases_skipped": sorted(existing_cases),
            "completed_artifact_hashes_before": before_hashes,
            "configuration_hash": manifest["configuration_hash"],
            "component_hashes": manifest["formal_component_hashes"],
            "Frozen_Gold_opened": False,
            "intermediate_predictions_used_for_changes": False,
            "recorded_at": utc_now(),
        }
    )
    runtime = load_frozen_eval_runtime_config(RUNTIME_SEAL)
    resolver = FrozenRawSourceResolver(
        artifact_manifest=base.ARTIFACT_MANIFEST,
        snapshot_db=base.SNAPSHOT,
        guard=HeldoutAccessGuard(ROOT),
    )
    missing_queries = [
        (position, query)
        for position, query in enumerate(queries, 1)
        if str(query["query_id"]) not in existing_cases
    ]
    if missing_queries:
        with tempfile.TemporaryDirectory(prefix="shiliu-p14-replacement-") as temp:
            work_db = Path(temp) / "sealed-snapshot-work-copy.db"
            shutil.copy2(runtime.database.path, work_db)
            service = build_search_service(
                work_db=work_db,
                snapshot_artifacts=base.ARTIFACTS,
                artifact_manifest=base.ARTIFACT_MANIFEST,
                provider=QwenEmbeddingProvider(),
            )
            for position, query in missing_queries:
                case_id = str(query["query_id"])
                work_path = WORK_ROOT / f"{case_id}.incomplete.json"
                if work_path.exists():
                    work = load_json(work_path)
                    if (
                        work["replacement_run_id"] != manifest["replacement_run_id"]
                        or work["configuration_hash"] != manifest["configuration_hash"]
                    ):
                        raise RuntimeError(f"Incomplete Case cannot safely resume: {case_id}")
                else:
                    work = prepare_case(
                        base=base,
                        query=query,
                        position=position,
                        manifest=manifest,
                        service=service,
                        resolver=resolver,
                        runtime=runtime,
                    )
                    atomic_json(work_path, work)
    all_work = [
        load_json(WORK_ROOT / f"{query['query_id']}.incomplete.json")
        for query in queries
        if str(query["query_id"]) not in existing_cases
    ]
    judge_outputs, judge_latency, retry_count, raw_hash = obtain_judge_outputs(
        base=base, work=all_work
    )
    for work in all_work:
        case_id = str(work["query"]["query_id"])
        artifact = finalize_case(
            base=base,
            work=work,
            manifest=manifest,
            judge_outputs=judge_outputs,
            judge_latency_ms=judge_latency,
            retry_count=retry_count,
            raw_hash=raw_hash,
        )
        existing_cases[case_id] = artifact
    completed = {
        path.stem: verify_complete_artifact(path, manifest)
        for path in sorted(CASE_ROOT.glob("*.json"))
    }
    expected_ids = {str(query["query_id"]) for query in queries}
    if set(completed) != expected_ids or len(completed) != 10:
        raise RuntimeError("Replacement completed Case set is not exactly Frozen 10")
    after_hashes = {
        case_id: file_sha256(CASE_ROOT / f"{case_id}.json")
        for case_id in completed
    }
    if any(after_hashes[case_id] != value for case_id, value in before_hashes.items()):
        raise RuntimeError("A completed Case changed during resume")
    predictions = [completed[str(query["query_id"])]["prediction"] for query in queries]
    atomic_jsonl(PREDICTIONS, predictions)
    configuration_hashes = {
        artifact["configuration_hash"] for artifact in completed.values()
    }
    component_versions = {
        stable_hash(artifact["component_versions"]) for artifact in completed.values()
    }
    if len(configuration_hashes) != 1 or len(component_versions) != 1:
        raise RuntimeError("Replacement Case configuration/component drift")
    trace_hashes = {
        completed[case_id]["trace_path"]: completed[case_id]["trace_hash"]
        for case_id in sorted(completed)
    }
    freeze = {
        "schema_version": "v3.5-b-p14-replacement-predictions-freeze-v1",
        "replacement_run_id": manifest["replacement_run_id"],
        "parent_invalid_run_id": manifest["parent_invalid_run_id"],
        "case_count": 10,
        "completed_cases": 10,
        "duplicate_case_predictions": 0,
        "missing_case_predictions": 0,
        "all_artifact_hashes_valid": True,
        "all_configuration_hashes_identical": True,
        "all_component_versions_identical": True,
        "per_case_artifact_hashes": {
            relative(CASE_ROOT / f"{case_id}.json"): file_sha256(
                CASE_ROOT / f"{case_id}.json"
            )
            for case_id in sorted(completed)
        },
        "aggregate_prediction_hash": file_sha256(PREDICTIONS),
        "trace_hashes": trace_hashes,
        "configuration_hash": manifest["configuration_hash"],
        "formal_component_hashes": manifest["formal_component_hashes"],
        "runtime_seal_hash": file_sha256(RUNTIME_SEAL),
        "runtime_asset_hashes": runtime_preflight["verified_hashes"],
        "formal_prediction_run_count": 1,
        "original_invalid_run_counts_toward_valid_quota": False,
        "Frozen_Query_opened": True,
        "Frozen_Gold_opened": False,
        "completed_cases_not_recomputed": all(
            after_hashes[case_id] == value
            for case_id, value in before_hashes.items()
        ),
        "predictions_frozen_at": utc_now(),
        "immutable_after_freeze": True,
    }
    atomic_json(PREDICTION_FREEZE, freeze)
    for path in [
        PREDICTIONS,
        *sorted(CASE_ROOT.glob("*.json")),
        *sorted(TRACE_ROOT.glob("*.json")),
    ]:
        path.chmod(0o444)
    append_resume_audit(
        {
            "replacement_run_id": manifest["replacement_run_id"],
            "event": "predictions_frozen",
            "completed_cases": 10,
            "completed_artifact_hashes_after": after_hashes,
            "completed_cases_not_recomputed": all(
                after_hashes[case_id] == value
                for case_id, value in before_hashes.items()
            ),
            "Frozen_Gold_opened": False,
            "recorded_at": utc_now(),
        }
    )
    return {
        "status": "replacement_predictions_frozen",
        "replacement_run_id": manifest["replacement_run_id"],
        "case_count": 10,
        "prediction_freeze_sha256": file_sha256(PREDICTION_FREEZE),
    }


def score() -> dict[str, Any]:
    manifest, _ = verify_authorization()
    freeze = load_json(PREDICTION_FREEZE)
    if (
        freeze.get("replacement_run_id") != manifest["replacement_run_id"]
        or freeze.get("case_count") != 10
        or freeze.get("formal_prediction_run_count") != 1
        or freeze.get("Frozen_Gold_opened") is not False
        or freeze.get("aggregate_prediction_hash") != file_sha256(PREDICTIONS)
    ):
        raise RuntimeError("Replacement Predictions Freeze barrier failed")
    base = load_base_runner()
    base.PREDICTIONS = PREDICTIONS
    base.PREDICTION_FREEZE = PREDICTION_FREEZE
    base.FORMAL_MANIFEST = MANIFEST
    base.ENTRY_GATE = ENTRY_GATE
    result = base.score()
    return {
        **result,
        "replacement_run_id": manifest["replacement_run_id"],
        "Frozen_Gold_opened_after_prediction_freeze": True,
        "frozen_scorer_reused_without_changes": True,
        "base_scorer_runner_hash": file_sha256(
            ROOT / "research/scripts/run_p14_frozen_evaluation.py"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("predict", "score"))
    args = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    result = predict() if args.phase == "predict" else score()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
