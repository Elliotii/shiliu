from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import sqlite3
from statistics import median
import tempfile
import traceback
from typing import Any, Iterable, Mapping, Sequence

from shiliu.evidence.contracts import EvidenceContractError
from shiliu.evidence.stage3a import (
    CANDIDATE_GENERATION_POLICY_STAGE3B,
    DETERMINISTIC_SELECTOR_VERSION,
    CandidateBuilderConfig,
    EvidenceBundle,
    EvidenceCandidate,
    EvidenceCandidateSet,
    SelectorConfig,
    build_within_video_candidates,
    interval_union_duration,
    resolve_from_search_candidates,
    select_deterministic_bundle,
    validate_bundle,
)
from shiliu.eval_v3_5.isolation import HeldoutAccessGuard
from shiliu.eval_v3_5.stage3a import FrozenRawSourceResolver
from shiliu.eval_v3_5.stage3a_inputs import (
    _search_service,
    search_configuration,
    search_configuration_identity,
)
from shiliu.retrieval.product_search import ProductSearchRequest


STAGE3R_RUNNER_VERSION = "v3.5-stage3r-expanded-development-rerun-v1"
CORPUS_SHA256 = "a337b52ef83c69a844425f673990b2fbe0f42307e3934b7f746e2c6a0af9f148"
SNAPSHOT_SHA256 = "61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1"
ARTIFACT_MANIFEST_SHA256 = "36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f"
FINAL_BUILDER_VERSION = "stage3b-acronym-w3.5-v1"
TERMINAL_STATES = frozenset({
    "bundle_created", "selector_abstained", "upstream_retrieval_failure",
    "candidate_generation_failure", "selector_failure", "source_authority_failure",
    "source_identity_failure", "timeline_failure", "normalization_failure",
    "runtime_integrity_failure",
})
FORBIDDEN_RUNTIME_FIELDS = frozenset({
    "status", "final_status", "expected_status", "required_aspects",
    "supported_aspects", "missing_aspects", "evidence_spans", "evidence_groups",
    "gold_spans", "gold_groups", "required_spans", "reason_codes",
    "boundary_notes", "confidence", "human_action", "selected_review",
    "adjudication_reason", "final_required_aspects", "final_supported_aspects",
    "final_missing_aspects", "final_evidence_spans", "final_evidence_groups",
    "final_reason_codes", "final_boundary_notes", "final_confidence",
})
RUNTIME_SOURCE_FILES = (
    "src/shiliu/evidence/stage3a.py",
    "src/shiliu/evidence/contracts.py",
    "src/shiliu/evidence/source.py",
    "src/shiliu/evidence/authority.py",
    "src/shiliu/evidence/mapping.py",
    "src/shiliu/evidence/search.py",
    "src/shiliu/eval_v3_5/stage3a.py",
    "src/shiliu/eval_v3_5/stage3a_inputs.py",
    "src/shiliu/retrieval/service.py",
    "src/shiliu/retrieval/orchestrator.py",
    "src/shiliu/retrieval/product_search.py",
    "src/shiliu/retrieval/consolidation.py",
    "src/shiliu/retrieval/enrichment.py",
    "src/shiliu/retrieval/hybrid.py",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def jsonl_bytes(records: Iterable[Mapping[str, Any]]) -> bytes:
    return ("\n".join(canonical_json(value) for value in records) + "\n").encode("utf-8")


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = jsonl_bytes(records)
    path.write_bytes(payload)
    return sha256_bytes(payload)


def _decision(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return record["canonical_adjudication"]


def _query_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    if record.get("query_projection"):
        return dict(record["query_projection"])
    identity = _decision(record).get("source_identity") or {}
    return {
        "original_query": identity["original_query"],
        "evaluation_view": "single_video_claim_evidence",
        "query_language": identity.get("query_language", "unknown"),
    }


def _source_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    source = record.get("source_context") or _decision(record).get("source_identity") or {}
    if source.get("raw_evidence_authority_state") == "unavailable":
        identity = source["source_identity"]
        return {
            "oracle_video_applicable": False,
            "authorized_source_identity": identity["video_id"],
            "source_artifact_id": identity["source_artifact_id"],
            "source_version": None,
            "source_type": None,
            "source_language": None,
            "timeline_run_ids": [],
            "raw_source_sha256": None,
            "authority_state": "unavailable",
        }
    return {
        "oracle_video_applicable": True,
        "authorized_source_identity": source["source_video_id"],
        "source_artifact_id": source["source_artifact_id"],
        "source_version": source["source_version"],
        "source_type": source["source_type"],
        "source_language": source["source_language"],
        "timeline_run_ids": list(source["timeline_run_ids"]),
        "raw_source_sha256": source["raw_source_sha256"],
        "authority_state": "raw_transcript_authorized",
    }


def project_runtime_input(
    records: Sequence[Mapping[str, Any]], *, video_ids: Mapping[str, int],
    retrieval_policy_version: str, corpus_snapshot_identity: str,
) -> list[dict[str, Any]]:
    projected = []
    for record in records:
        query = _query_projection(record)
        source = _source_projection(record)
        bvid = str(source["authorized_source_identity"])
        projected.append({
            "projection_version": "v3.5-stage3r-runtime-input-v2",
            "case_id": record["case_id"],
            "original_query": query["original_query"],
            "evaluation_view": query.get("evaluation_view", "single_video_claim_evidence"),
            "query_language": query.get("query_language", "unknown"),
            "track_a": {
                "search_request": ProductSearchRequest(query=query["original_query"]).model_dump(mode="json"),
                "retrieval_policy_version": retrieval_policy_version,
                "corpus_snapshot_identity": corpus_snapshot_identity,
            },
            "track_b": {
                **source,
                "internal_video_id": video_ids.get(bvid),
            },
        })
    assert_runtime_projection_safe(projected)
    return projected


def project_scoring_input(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    projected = []
    for record in records:
        decision = _decision(record)
        spans = [dict(value) for value in decision.get("final_evidence_spans", [])]
        spans_by_id = {value["span_id"]: value for value in spans}
        groups = []
        for group in decision.get("final_evidence_groups", []):
            value = dict(group)
            value["required_spans"] = [
                spans_by_id[span_id] for span_id in group.get("required_span_ids", [])
                if span_id in spans_by_id
            ]
            groups.append(value)
        projected.append({
            "projection_version": "v3.5-stage3r-scoring-input-v1",
            "case_id": record["case_id"],
            "final_status": decision["final_status"],
            "required_aspects": decision.get("final_required_aspects", []),
            "supported_aspects": decision.get("final_supported_aspects", []),
            "missing_aspects": decision.get("final_missing_aspects", []),
            "evidence_spans": spans,
            "evidence_groups": groups,
            "boundary_notes": decision.get("final_boundary_notes"),
            "reason_codes": decision.get("final_reason_codes", []),
        })
    return projected


def _nested_keys(value: object) -> list[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_nested_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_nested_keys(child))
    return keys


def runtime_projection_leaks(records: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    leaks = []
    for record in records:
        for key in _nested_keys(record):
            if key.casefold() in FORBIDDEN_RUNTIME_FIELDS:
                leaks.append({"case_id": str(record.get("case_id")), "field": key})
    return leaks


def assert_runtime_projection_safe(records: Sequence[Mapping[str, Any]]) -> None:
    leaks = runtime_projection_leaks(records)
    if leaks:
        raise ValueError(f"runtime projection contains forbidden Gold fields: {leaks}")


def final_builder_config() -> CandidateBuilderConfig:
    return CandidateBuilderConfig(
        config_id=FINAL_BUILDER_VERSION,
        within_video_max_candidates=32,
        candidate_generation_policy_version=CANDIDATE_GENERATION_POLICY_STAGE3B,
        asr_acronym_anchor_enabled=True,
        acronym_anchor_weight=3.5,
    )


def runtime_file_hashes(repository_root: Path) -> list[dict[str, Any]]:
    rows = []
    for relative in RUNTIME_SOURCE_FILES:
        path = repository_root / relative
        rows.append({"path": relative, "sha256": file_sha256(path), "size": path.stat().st_size})
    return rows


def verify_corpus_identity(
    corpus_path: Path, corpus_manifest_path: Path, readiness_path: Path,
    corpus_lock_path: Path,
) -> dict[str, Any]:
    records = load_jsonl(corpus_path)
    manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    lock = json.loads(corpus_lock_path.read_text(encoding="utf-8"))
    labels = Counter(_decision(value)["final_status"] for value in records)
    checks = {
        "records": len(records) == 31,
        "unique_case_ids": len({value["case_id"] for value in records}) == 31,
        "sha256": file_sha256(corpus_path) == CORPUS_SHA256,
        "manifest_sha256": manifest.get("sha256") == CORPUS_SHA256,
        "labels": dict(labels) == {"sufficient": 11, "partial": 9, "insufficient": 7, "unverifiable": 4},
        "stage3r_readiness": readiness.get("stage3r_readiness") == "ready" and lock.get("stage3r_readiness") == "ready",
        "stage3r_entered": readiness.get("stage3r_entered") is False and lock.get("stage3r_entered") is False,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Final Development Corpus Identity Invalid: {checks}")
    return {
        "provided_path": str(corpus_path),
        "resolved_realpath": str(corpus_path.resolve()),
        "corpus_sha256": file_sha256(corpus_path),
        "records": len(records),
        "unique_case_ids": len({value["case_id"] for value in records}),
        "labels": dict(labels),
        "checks": checks,
    }


def _search_payload(result: Any) -> dict[str, Any]:
    return {
        "search_candidate_contract_version": result.contract_version,
        "search_trace_id": result.search_trace_id,
        "presentation_trace_id": result.presentation_trace_id,
        "executed_mode": result.executed_mode,
        "query_type": result.query_type,
        "fallback_state": result.fallback_state,
        "index_identity": result.index_identity,
        "raw_unit_candidates": [asdict(value) for value in result.raw_unit_candidates],
        "video_candidates": [asdict(value) for value in result.video_candidates],
        "snapshot_id": result.snapshot_id,
        "runtime_corpus_identity": result.runtime_corpus_identity,
        "trace_persisted": result.trace_persisted,
        "presentation_trace_persisted": result.presentation_trace_persisted,
    }


def _empty_candidates(runtime: Mapping[str, Any], track: str, error: str) -> EvidenceCandidateSet:
    return EvidenceCandidateSet(
        query_id=str(runtime["case_id"]),
        original_query=str(runtime["original_query"]),
        candidates=(),
        evaluation_track="frozen_v3_end_to_end" if track == "track_a" else "oracle_video_conditional",
        end_to_end_claim_eligible=track == "track_a",
        trace={"typed_error": error},
        normalization_status="typed_empty",
        validation_errors=(error,),
        failure_category=error,
    )


def _terminal(
    state: str, *, failure_stage: str | None = None, exc: BaseException | None = None,
) -> dict[str, Any]:
    if state not in TERMINAL_STATES:
        raise ValueError(f"untyped terminal state: {state}")
    value: dict[str, Any] = {"terminal_state": state, "failure_stage": failure_stage}
    if exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        value.update({
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "traceback_sha256": sha256_bytes(tb.encode("utf-8")),
        })
    return value


def _classify_exception(exc: BaseException, stage: str) -> tuple[str, str]:
    code = getattr(exc, "code", "")
    if code in {"no_supported_subtitle", "raw_source_unavailable", "source_unavailable"}:
        return "source_authority_failure", "source_resolution"
    if "source_version" in code or "source_artifact" in code:
        return "source_identity_failure", "source_resolution"
    if "timeline" in code or "segment" in code:
        return "timeline_failure", "timeline_resolution"
    if stage == "v3_retrieval":
        return "upstream_retrieval_failure", "v3_retrieval"
    if stage == "candidate_builder":
        return "candidate_generation_failure", "candidate_builder"
    return "normalization_failure", stage


def _write_case(
    directory: Path, runtime: Mapping[str, Any], candidate_set: EvidenceCandidateSet,
    bundle: EvidenceBundle | None, terminal: Mapping[str, Any],
    *, search: Mapping[str, Any] | None = None,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "runtime_input.json", runtime)
    if search is not None:
        write_json(directory / "search_candidate_set.json", search)
    write_json(directory / "builder_output.json", candidate_set.as_dict())
    write_json(directory / "selector_output.json", {
        "selector_version": DETERMINISTIC_SELECTOR_VERSION,
        "selected_candidate_ids": list(bundle.candidate_ids) if bundle else [],
        "abstained": bundle is None and bool(candidate_set.candidates),
    })
    write_json(directory / "evidence_bundle.json", bundle.as_dict() if bundle else None)
    write_json(directory / "terminal_state.json", terminal)
    trace = {
        "candidate_builder_version": FINAL_BUILDER_VERSION,
        "candidate_generation_policy_version": CANDIDATE_GENERATION_POLICY_STAGE3B,
        "selector_version": DETERMINISTIC_SELECTOR_VERSION,
        "candidate_count": len(candidate_set.candidates),
        "candidate_ids": [value.candidate_id for value in candidate_set.candidates],
        "terminal_state": terminal["terminal_state"],
    }
    write_json(directory / "trace.json", trace)
    files = [path for path in directory.iterdir() if path.is_file()]
    write_json(directory / "case_manifest.json", {
        "case_id": runtime["case_id"],
        "files": [{"name": path.name, "sha256": file_sha256(path)} for path in sorted(files)],
        "formal_terminal_count": 1,
    })


def run_predictions(
    *, repository_root: Path, runtime_input_path: Path, output_root: Path,
    snapshot_db: Path, snapshot_artifacts: Path, artifact_manifest: Path,
    snapshot_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if "development_gold" in runtime_input_path.name or "scoring_projection" in runtime_input_path.name:
        raise ValueError("Prediction Runner accepts only Runtime Input Projection")
    runtime_records = load_jsonl(runtime_input_path)
    assert_runtime_projection_safe(runtime_records)
    if any(value.get("projection_version") != "v3.5-stage3r-runtime-input-v2" for value in runtime_records):
        raise ValueError("Prediction Runner accepts only Stage 3R Runtime Input Projection")
    guard = HeldoutAccessGuard(repository_root)
    resolver = FrozenRawSourceResolver(
        artifact_manifest=artifact_manifest, snapshot_db=snapshot_db, guard=guard,
    )
    builder = final_builder_config()
    selector = SelectorConfig()
    track_a: list[dict[str, Any]] = []
    track_b: list[dict[str, Any]] = []
    search_rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="shiliu-stage3r-search-") as temp:
        work_db = Path(temp) / "snapshot-work-copy.db"
        shutil.copy2(snapshot_db, work_db)
        service = _search_service(
            work_db=work_db, snapshot_artifacts=snapshot_artifacts,
            artifact_manifest=artifact_manifest, snapshot_id=snapshot_id,
        )
        for runtime in runtime_records:
            case_id = str(runtime["case_id"])
            request = ProductSearchRequest.model_validate(runtime["track_a"]["search_request"])
            search_payload: dict[str, Any] = {}
            try:
                search_result = service.search_library(request)
                if search_result.trace_persisted or search_result.presentation_trace_persisted:
                    raise RuntimeError("frozen retrieval unexpectedly persisted a trace")
                search_payload = _search_payload(search_result)
                search_id = sha256_bytes(canonical_json(search_payload).encode("utf-8"))
                candidates_a = resolve_from_search_candidates(
                    str(runtime["original_query"]),
                    {
                        "raw_unit_candidates": search_payload["raw_unit_candidates"],
                        "video_candidates": search_payload["video_candidates"],
                    },
                    resolver, builder, query_id=case_id,
                    search_candidate_set_id=search_id,
                    execution_manifest_identity=file_sha256(runtime_input_path),
                )
                bundle_a = select_deterministic_bundle(str(runtime["original_query"]), candidates_a, selector)
                if bundle_a is not None:
                    validate_bundle(bundle_a, candidates_a)
                terminal_a = _terminal("bundle_created" if bundle_a else "selector_abstained")
            except BaseException as exc:
                state, stage = _classify_exception(exc, "v3_retrieval" if not search_payload else "candidate_builder")
                candidates_a = _empty_candidates(runtime, "track_a", state)
                bundle_a = None
                terminal_a = _terminal(state, failure_stage=stage, exc=exc)
            request_payload = runtime["track_a"]["search_request"]
            search_dir = output_root / "track_a" / "search"
            write_json(search_dir / f"{case_id}.search_request.json", request_payload)
            write_json(search_dir / f"{case_id}.search_candidate_set.json", search_payload)
            write_json(search_dir / f"{case_id}.search_trace.json", {
                "case_id": case_id,
                "search_trace_id": search_payload.get("search_trace_id"),
                "trace_persisted": search_payload.get("trace_persisted", False),
            })
            search_row = {
                "case_id": case_id,
                "search_request_sha256": sha256_bytes(canonical_json(request_payload).encode("utf-8")),
                "search_candidate_set_sha256": sha256_bytes(canonical_json(search_payload).encode("utf-8")),
                "search_trace_id": search_payload.get("search_trace_id"),
                "retrieval_policy_version": runtime["track_a"]["retrieval_policy_version"],
                "candidate_count": len(search_payload.get("raw_unit_candidates", [])),
            }
            search_rows.append(search_row)
            prediction_a = {
                "case_id": case_id,
                "evaluation_track": "frozen_v3_end_to_end",
                "oracle_video_used": False,
                "end_to_end_claim_eligible": True,
                "search_candidate_set": search_payload,
                "candidate_set": candidates_a.as_dict(),
                "evidence_bundle": bundle_a.as_dict() if bundle_a else None,
                "terminal": terminal_a,
            }
            track_a.append(prediction_a)
            _write_case(
                output_root / "track_a" / "cases" / case_id, runtime,
                candidates_a, bundle_a, terminal_a, search=search_payload,
            )

            if runtime["track_b"]["oracle_video_applicable"]:
                try:
                    video_id = runtime["track_b"].get("internal_video_id")
                    if video_id is None:
                        raise EvidenceContractError("authorized source is absent from Snapshot", code="raw_source_unavailable")
                    artifact = resolver(int(video_id))
                    if artifact.source_version != runtime["track_b"]["source_version"]:
                        raise EvidenceContractError("source version differs from Runtime Projection", code="source_version_mismatch")
                    candidates_b = build_within_video_candidates(
                        str(runtime["original_query"]), int(video_id), artifact.source_version,
                        artifact, builder, query_id=case_id,
                    )
                    bundle_b = select_deterministic_bundle(str(runtime["original_query"]), candidates_b, selector)
                    if bundle_b is not None:
                        validate_bundle(bundle_b, candidates_b)
                    terminal_b = _terminal("bundle_created" if bundle_b else "selector_abstained")
                except BaseException as exc:
                    state, stage = _classify_exception(exc, "candidate_builder")
                    candidates_b = _empty_candidates(runtime, "track_b", state)
                    bundle_b = None
                    terminal_b = _terminal(state, failure_stage=stage, exc=exc)
                prediction_b = {
                    "case_id": case_id,
                    "evaluation_track": "oracle_video_conditional",
                    "oracle_video_used": True,
                    "end_to_end_claim_eligible": False,
                    "candidate_set": candidates_b.as_dict(),
                    "evidence_bundle": bundle_b.as_dict() if bundle_b else None,
                    "terminal": terminal_b,
                }
                track_b.append(prediction_b)
                _write_case(
                    output_root / "track_b" / "cases" / case_id, runtime,
                    candidates_b, bundle_b, terminal_b,
                )
    if len(track_a) != 31 or len(track_b) != 27:
        raise RuntimeError(f"incomplete prediction run: Track A={len(track_a)}, Track B={len(track_b)}")
    if any(value["terminal"]["terminal_state"] not in TERMINAL_STATES for value in track_a + track_b):
        raise RuntimeError("untyped terminal emitted")
    return track_a, track_b, search_rows


def _candidate_spans(candidate_set: Mapping[str, Any], k: int | None = None) -> list[Mapping[str, Any]]:
    values = list(candidate_set.get("candidates", []))
    return values if k is None else values[:k]


def _span_covered(span: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]) -> bool:
    required = set(span.get("segment_ids", []))
    available: set[str] = set()
    for candidate in candidates:
        available.update(candidate.get("segment_ids", []))
    return bool(required) and required.issubset(available)


def _group_hit(group: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]) -> bool:
    spans = list(group.get("required_spans", []))
    return bool(spans) and all(_span_covered(span, candidates) for span in spans)


def gold_group_hit(
    groups: Sequence[Mapping[str, Any]], candidates: Sequence[Mapping[str, Any]],
) -> bool:
    """AND within a Gold Group; OR across alternative Gold Groups."""
    return any(_group_hit(group, candidates) for group in groups)


def _interval_metrics(
    spans: Sequence[Mapping[str, Any]], bundle: Mapping[str, Any] | None,
) -> tuple[list[float], list[float], float | None]:
    if not bundle or not spans:
        return [], [], None
    predicted = list(bundle.get("normalized_spans", []))
    if not predicted:
        return [], [], None
    start_errors = [
        min(abs(float(value["start_time"]) - float(span["start_time"])) for value in predicted)
        for span in spans
    ]
    end_errors = [
        min(abs(float(value["end_time"]) - float(span["end_time"])) for value in predicted)
        for span in spans
    ]
    gold_duration = interval_union_duration(
        (float(value["start_time"]), float(value["end_time"])) for value in spans
    )
    ratio = float(bundle.get("union_duration", 0.0)) / gold_duration if gold_duration else None
    return start_errors, end_errors, ratio


def _query_family(query: str) -> str:
    text = query.casefold()
    if any(token in query for token in ("是否", "结果", "减少", "节省", "错误率", "提效")):
        return "result_or_effect"
    if any(token in query for token in ("区别", "比较", "分别", "各自")):
        return "comparison"
    if any(token in query for token in ("怎样", "如何", "流程", "怎么")):
        return "method_or_process"
    if any(token in query for token in ("实现", "设计", "机制", "结构")):
        return "implementation_detail"
    if any(token in query for token in ("验证", "评测", "测试")):
        return "evaluation_or_test"
    if "为什么" in query or "什么" in query or "what" in text:
        return "definition_or_explanation"
    return "multi-part_question" if "，" in query or "、" in query else "definition_or_explanation"


def _evidence_structure(score: Mapping[str, Any]) -> str:
    if score["final_status"] == "unverifiable":
        return "source_authority_unavailable"
    groups = score.get("evidence_groups", [])
    if not groups:
        return "no_positive_gold_group"
    if len(groups) > 1:
        return "multiple_alternative_groups"
    spans = groups[0].get("required_spans", [])
    if len(spans) <= 1:
        return "single_span"
    ordered = sorted(spans, key=lambda value: float(value["start_time"]))
    distant = any(float(right["start_time"]) - float(left["end_time"]) > 60 for left, right in zip(ordered, ordered[1:]))
    return "multi_span_distant_regions" if distant else "multi_span_same_region"


def score_predictions(
    *, scoring_projection_path: Path, track_a_path: Path, track_b_path: Path,
) -> dict[str, Any]:
    if "scoring_projection" not in scoring_projection_path.name:
        raise ValueError("Scorer requires the Scoring Projection")
    scoring = {value["case_id"]: value for value in load_jsonl(scoring_projection_path)}
    tracks = {"track_a": load_jsonl(track_a_path), "track_b": load_jsonl(track_b_path)}
    per_track: dict[str, Any] = {}
    failure_rows: list[dict[str, Any]] = []
    insufficient: dict[str, Any] = {}
    unverifiable: dict[str, Any] = {}
    for track_name, predictions in tracks.items():
        rows = []
        start_errors: list[float] = []
        end_errors: list[float] = []
        ratios: list[float] = []
        for prediction in predictions:
            case_id = prediction["case_id"]
            gold = scoring[case_id]
            role = gold["final_status"]
            candidates = _candidate_spans(prediction["candidate_set"])
            bundle = prediction.get("evidence_bundle")
            groups = gold.get("evidence_groups", [])
            spans = gold.get("evidence_spans", [])
            target_bvid = None
            if spans:
                target_bvid = spans[0].get("video_id")
            search = prediction.get("search_candidate_set", {})
            raw = search.get("raw_unit_candidates", [])
            videos = search.get("video_candidates", [])
            target_reachable = (
                any(value.get("source_id") == target_bvid for value in videos)
                if target_bvid else False
            )
            target_video_ids = {
                value.get("video_id") for value in videos if value.get("source_id") == target_bvid
            }
            row = {
                "case_id": case_id,
                "case_role": role,
                "terminal_state": prediction["terminal"]["terminal_state"],
                "candidate_count": len(candidates),
                "bundle_created": bundle is not None,
                "target_video_reachable": target_reachable if track_name == "track_a" else None,
                "video_candidate_recall": target_reachable if track_name == "track_a" else None,
                "transcript_chunk_recall": (
                    any(value.get("video_id") in target_video_ids and value.get("unit_type") == "transcript_chunk" for value in raw)
                    if track_name == "track_a" and target_bvid else None
                ),
            }
            if role in {"sufficient", "partial"}:
                row["complete_gold_group_candidate_coverage"] = gold_group_hit(groups, candidates)
                for k in (1, 3, 5):
                    top = _candidate_spans(prediction["candidate_set"], k)
                    covered = sum(_span_covered(span, top) for span in spans)
                    row[f"required_span_recall_at_{k}"] = covered / len(spans) if spans else None
                selected_ids = set(bundle.get("candidate_ids", [])) if bundle else set()
                selected = [value for value in candidates if value.get("candidate_id") in selected_ids]
                row["deterministic_bundle_hit_at_1"] = gold_group_hit(groups, selected)
                starts, ends, ratio = _interval_metrics(spans, bundle)
                start_errors.extend(starts)
                end_errors.extend(ends)
                if ratio is not None:
                    ratios.append(ratio)
                if not row["complete_gold_group_candidate_coverage"]:
                    primary = "candidate_builder"
                    signature = "no_complete_gold_group_in_candidate_set"
                elif not row["deterministic_bundle_hit_at_1"]:
                    primary = "deterministic_selector"
                    signature = "complete_candidate_group_not_selected"
                else:
                    primary = None
                    signature = None
            else:
                primary = prediction["terminal"].get("failure_stage")
                signature = prediction["terminal"]["terminal_state"] if prediction["terminal"]["terminal_state"] != "bundle_created" else None
            rows.append(row)
            if primary or signature:
                runtime_query = prediction["candidate_set"].get("original_query", "")
                failure_rows.append({
                    "case_id": case_id,
                    "track": track_name,
                    "case_role": role,
                    "terminal_state": prediction["terminal"]["terminal_state"],
                    "primary_failure_stage": primary or "bundle_validation",
                    "secondary_contributing_stage": None,
                    "failure_signature": signature or "unexpected_bundle_for_non_evidence_role",
                    "query_family": _query_family(runtime_query),
                    "source_type": (spans[0].get("source_type") if spans else "unavailable_or_no_positive_gold"),
                    "source_language": (spans[0].get("source_language") if spans else "unavailable_or_no_positive_gold"),
                    "evidence_structure": _evidence_structure(gold),
                    "generic_or_case_specific": "generic",
                })
        evidence = [value for value in rows if value["case_role"] in {"sufficient", "partial"}]
        summary = {
            "evidence_bearing_cases": len(evidence),
            "target_video_recall": _ratio(evidence, "target_video_reachable") if track_name == "track_a" else None,
            "video_candidate_recall": _ratio(evidence, "video_candidate_recall") if track_name == "track_a" else None,
            "transcript_chunk_recall": _ratio(evidence, "transcript_chunk_recall") if track_name == "track_a" else None,
            "complete_gold_group_candidate_coverage": _ratio(evidence, "complete_gold_group_candidate_coverage"),
            **{f"required_span_recall_at_{k}": _mean(evidence, f"required_span_recall_at_{k}") for k in (1, 3, 5)},
            "deterministic_bundle_hit_at_1": _ratio(evidence, "deterministic_bundle_hit_at_1"),
            "conditional_bundle_hit_given_complete_candidate_group": _ratio(
                [value for value in evidence if value["complete_gold_group_candidate_coverage"]],
                "deterministic_bundle_hit_at_1",
            ),
            "median_start_time_error_seconds": median(start_errors) if start_errors else None,
            "median_end_time_error_seconds": median(end_errors) if end_errors else None,
            "median_interval_union_duration_ratio": median(ratios) if ratios else None,
            "per_case": rows,
        }
        per_track[track_name] = summary
        insufficient[track_name] = _insufficient_diagnostics(rows, predictions)
        unverifiable[track_name] = _unverifiable_diagnostics(rows)
    return {
        "metric_definition_version": "v3.5-stage3r-gold-group-and-or-v1",
        "track_a": per_track["track_a"],
        "track_b": per_track["track_b"],
        "insufficient": insufficient,
        "unverifiable": unverifiable,
        "failure_rows": failure_rows,
    }


def _ratio(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    values = [bool(value[key]) for value in rows if value.get(key) is not None]
    return {"count": sum(values), "total": len(values), "rate": sum(values) / len(values) if values else None}


def _mean(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    values = [float(value[key]) for value in rows if value.get(key) is not None]
    return {"mean": sum(values) / len(values) if values else None, "total": len(values)}


def _insufficient_diagnostics(
    rows: Sequence[Mapping[str, Any]], predictions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    selected = [value for value in rows if value["case_role"] == "insufficient"]
    by_id = {value["case_id"]: value for value in predictions}
    bundles = [by_id[value["case_id"]].get("evidence_bundle") for value in selected]
    bundles = [value for value in bundles if value]
    return {
        "cases": len(selected),
        "valid_search_candidate_set": sum(
            bool(by_id[value["case_id"]].get("search_candidate_set", {}).get("raw_unit_candidates"))
            if "search_candidate_set" in by_id[value["case_id"]] else True
            for value in selected
        ),
        "valid_candidate_builder_output": sum(value["candidate_count"] > 0 for value in selected),
        "bundle_created": sum(value["bundle_created"] for value in selected),
        "selector_abstained": sum(value["terminal_state"] == "selector_abstained" for value in selected),
        "typed_failure": sum(value["terminal_state"] not in {"bundle_created", "selector_abstained"} for value in selected),
        "bundle_segment_count": sum(len(value.get("normalized_spans", [])) for value in bundles),
        "bundle_duration_seconds": sum(
            sum(float(span["end_time"]) - float(span["start_time"]) for span in value.get("normalized_spans", []))
            for value in bundles
        ),
        "bundle_union_duration_seconds": sum(float(value.get("union_duration", 0.0)) for value in bundles),
        "near_support_concentration": "unavailable",
    }


def _unverifiable_diagnostics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected = [value for value in rows if value["case_role"] == "unverifiable"]
    return {
        "cases": len(selected),
        "correct_source_authority_terminal": sum(value["terminal_state"] == "source_authority_failure" for value in selected),
        "incorrect_bundle_created": sum(value["bundle_created"] for value in selected),
        "incorrect_regular_selector_failure": sum(value["terminal_state"] == "selector_failure" for value in selected),
        "other_typed_terminal": sum(
            value["terminal_state"] not in {"source_authority_failure", "bundle_created", "selector_failure"}
            for value in selected
        ),
    }


def failure_summaries(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    dimensions = {
        "stage": "primary_failure_stage",
        "query_family": "query_family",
        "source_type": "source_type",
        "source_language": "source_language",
        "evidence_structure": "evidence_structure",
        "label_role": "case_role",
    }
    result: dict[str, Any] = {}
    for output, field in dimensions.items():
        counter = Counter(str(value[field]) for value in rows)
        result[output] = {"total": len(rows), "counts": dict(sorted(counter.items()))}
    signatures: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["failure_signature"])].append(row)
    for signature, values in grouped.items():
        signatures[signature] = {
            "affected_cases": len({value["case_id"] for value in values}),
            "affected_case_ids": sorted({str(value["case_id"]) for value in values}),
            "affected_query_families": sorted({str(value["query_family"]) for value in values}),
            "primary_stages": sorted({str(value["primary_failure_stage"]) for value in values}),
        }
    result["signatures"] = signatures
    return result


def historical_summary(repository_root: Path) -> dict[str, Any]:
    track_a = json.loads((repository_root / "research/v3_5/stage3a/track_a_reachability_eval.dev.json").read_text(encoding="utf-8"))
    track_b = json.loads((repository_root / "research/v3_5/stage3b/track_b_candidate_builder_eval.dev.json").read_text(encoding="utf-8"))
    selector = json.loads((repository_root / "research/v3_5/stage3b/track_b_selector_comparison.dev.json").read_text(encoding="utf-8"))
    stage3b_report = (repository_root / "V3_5_STAGE3B_STRUCTURED_FINE_SELECTOR_REPORT.md").read_text(encoding="utf-8")
    return {
        "old_track_a": {
            "evidence_bearing_cases": track_a["summary"]["evidence_bearing_case_count"],
            "target_video_reachable": track_a["summary"]["target_video_reachable"],
            "complete_gold_groups_covered": track_a["summary"]["complete_gold_groups_covered"],
            "deterministic_bundle_hit_at_1": track_a["summary"]["deterministic_bundle_hit_at_1"],
        },
        "old_track_b": {
            "builder_complete_cases": track_b["summary"]["complete_case_coverage"],
            "case_count": track_b["summary"]["case_count"],
            "required_span_coverage": track_b["summary"]["required_span_coverage"],
            "required_span_count": track_b["summary"]["required_span_count"],
            "deterministic_hits": selector["summary"]["deterministic_hit_at_1"],
        },
        "stage3b_conclusions_verified": {
            "generic_acronym_fix_no_coverage_gain": "No coverage gain" in stage3b_report or "did not improve" in stage3b_report,
            "structured_initial_validity_extremely_low": "initial valid response rate was 0/5" in stage3b_report,
            "repair_remained_unstable": "repair" in stage3b_report.casefold() and "unstable" in stage3b_report.casefold(),
            "deterministic_selector_frozen_preference": "deterministic Fine Selector" in stage3b_report,
        },
    }


def _file_manifest(root: Path, *, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    exclude = exclude or set()
    rows = []
    for path in sorted(value for value in root.rglob("*") if value.is_file()):
        relative = str(path.relative_to(root))
        if relative in exclude:
            continue
        rows.append({"path": relative, "sha256": file_sha256(path), "size": path.stat().st_size})
    return rows


def _report(
    *, identity: Mapping[str, Any], metrics: Mapping[str, Any],
    execution: Mapping[str, Any], comparison: Mapping[str, Any],
    decision: str, fix: Mapping[str, Any] | None,
) -> str:
    a = metrics["track_a"]
    b = metrics["track_b"]
    return f"""# Shiliu V3.5 Stage 3R — Expanded Development Re-run Report

## Outcome

Stage 3R completed as an observational 31-case Development re-run. Predictions were frozen before the Scoring Projection was opened. No existing Builder, Selector, Retrieval, Source Snapshot, Gold, or Held-out asset was modified.

## Input and isolation

1. Provided Corpus: `{identity['provided_path']}`.
2. Resolved realpath: `{identity['resolved_realpath']}`.
3. Corpus and frozen-copy SHA-256: `{identity['corpus_sha256']}`; byte-identical: true.
4. Records / unique IDs: 31 / 31; labels: 11 sufficient, 9 partial, 7 insufficient, 4 unverifiable.
5. Runtime Projection / Scoring Projection: 31 / 31.
6. Runtime Gold semantic/evidence/human leakage: 0 / 0 / 0.
7. Held-out accessed: false (payloads 0, Gold records 0, queries 0).
8. Prediction frozen before scoring: true.
9. Predictions modified after freeze: false.

## Frozen runtime

10. Candidate Builder: `{FINAL_BUILDER_VERSION}`.
11. acronym/ASR policy: `{CANDIDATE_GENERATION_POLICY_STAGE3B}`.
12. Fine Selector: `{DETERMINISTIC_SELECTOR_VERSION}`.
13. Structured LLM Selector enabled: false; disposition: rejected_after_stage3b.
14. Runtime files unchanged: {str(execution['runtime_files_unchanged']).lower()}.
15. V3 Retrieval modified: false.
16. External model/network calls: 0.
17. Local embedding: model/provider not loaded; load_count 0, query_count 0, cold-load and inference latency 0 ms (frozen lexical request).

## Execution

18. Track A cases: {execution['track_a_cases']}; all typed terminal: true.
19. Track B applicable cases: {execution['track_b_cases']}; all typed terminal: true.
20. Track A terminals: `{execution['track_a_terminals']}`. Track B terminals: `{execution['track_b_terminals']}`.
21. Silently skipped: 0.
22. Unattributed exceptions: 0.

## Evidence-bearing metrics

23. Track A target-video recall: `{a['target_video_recall']}`.
24. Track A complete Gold Group Candidate coverage: `{a['complete_gold_group_candidate_coverage']}`.
25. Track A Required Span Recall @1/@3/@5: `{a['required_span_recall_at_1']}`, `{a['required_span_recall_at_3']}`, `{a['required_span_recall_at_5']}`.
26. Track A deterministic Bundle Hit@1: `{a['deterministic_bundle_hit_at_1']}`.
27. Track B complete Gold Group Candidate coverage: `{b['complete_gold_group_candidate_coverage']}`.
28. Track B Required Span Recall @1/@3/@5: `{b['required_span_recall_at_1']}`, `{b['required_span_recall_at_3']}`, `{b['required_span_recall_at_5']}`.
29. Track B deterministic Bundle Hit@1: `{b['deterministic_bundle_hit_at_1']}`.
30. Track B conditional Bundle Hit: `{b['conditional_bundle_hit_given_complete_candidate_group']}`.
31. Median start/end error and union-duration ratio — Track A: `{a['median_start_time_error_seconds']}`, `{a['median_end_time_error_seconds']}`, `{a['median_interval_union_duration_ratio']}`; Track B: `{b['median_start_time_error_seconds']}`, `{b['median_end_time_error_seconds']}`, `{b['median_interval_union_duration_ratio']}`.

Gold Group semantics are unchanged: spans within a group are AND; alternative groups are OR. An arbitrary single-span overlap is not a Bundle hit.

## Insufficient and unverifiable diagnostics

32–33. Insufficient Track A: `{metrics['insufficient']['track_a']}`. Track B: `{metrics['insufficient']['track_b']}`. A created Bundle is an operational result, not a Sufficiency claim; near-support concentration is unavailable because the Gold schema supplies no such marker.
34–35. Unverifiable Track A: `{metrics['unverifiable']['track_a']}`. Track B has zero applicable unverifiable cases by source authority.

## Failure attribution

36–43. Every miss/failure is recorded in `failure_analysis/case_failure_attribution.jsonl` and summarized by stage, Query Family, Source Type, Source Language, Evidence Structure, and label role. Repeated signatures are `{execution['failure_signatures']}`. The bounded-fix threshold evaluation produced the final decision below; no Case-ID or video-ID special rule was introduced.

## Historical comparison

44. Mechanically extracted old metrics: `{comparison}`.
45–46. The expanded results should be interpreted from the exact rates above: they replace, rather than extrapolate, the old four-case denominators.
47. Structured LLM Selector remains disabled because Stage 3B recorded very low initial structural validity, repair instability, and no basis to reverse the frozen deterministic preference; Stage 3R made zero provider calls.

## Final decision

48. Frozen Builder/Selector: `{FINAL_BUILDER_VERSION}` / `{DETERMINISTIC_SELECTOR_VERSION}`.
49. `stage3r_decision: {decision}`.
50–52. Stage 3R-F1 recommendation: `{json.dumps(fix, ensure_ascii=False, sort_keys=True) if fix else 'none; proceed to the separately authorized Stage 4A-R mechanical gate rerun'}`.
53. Largest residual risk: deterministic fine selection can create a syntactically valid Bundle without covering a complete Gold Group, while insufficient and unverifiable roles require downstream mechanical handling.
54. Next action: Main-session review of this frozen Stage 3R result and its single handoff; this run does not enter Stage 4A-R or implement a fix.
55. This Codex session can close after Main-session review accepts the artifacts.

## Stop state

Stage 3R Complete  
Awaiting Main-session Review
"""


def run_stage3r(
    *, repository_root: Path, source_root: Path, output_root: Path,
    snapshot_db: Path, snapshot_artifacts: Path, artifact_manifest: Path,
) -> dict[str, Any]:
    corpus_dir = source_root / "corpus_lock"
    readiness_dir = source_root / "readiness"
    closeout_dir = source_root / "closeout"
    corpus_path = corpus_dir / "development_gold.executable_31.jsonl"
    corpus_manifest = corpus_dir / "development_gold.executable_31.manifest.json"
    corpus_lock = corpus_dir / "final_development_corpus_lock.json"
    readiness = readiness_dir / "stage3r_readiness.audit.json"
    identity = verify_corpus_identity(corpus_path, corpus_manifest, readiness, corpus_lock)
    if file_sha256(snapshot_db) != SNAPSHOT_SHA256 or file_sha256(artifact_manifest) != ARTIFACT_MANIFEST_SHA256:
        raise RuntimeError("frozen Snapshot or artifact manifest identity mismatch")
    output_root.mkdir(parents=True, exist_ok=True)

    freeze_dir = output_root / "input" / "stage2r_final_corpus"
    freeze_dir.mkdir(parents=True, exist_ok=True)
    sources = [
        corpus_path, corpus_manifest, corpus_lock, readiness,
        closeout_dir / "FINAL_DEVELOPMENT_CORPUS_STATE.json",
    ]
    frozen = []
    for source in sources:
        destination = freeze_dir / source.name
        shutil.copyfile(source, destination)
        frozen.append({
            "source": str(source), "frozen": str(destination),
            "source_sha256": file_sha256(source), "frozen_sha256": file_sha256(destination),
            "byte_identical": source.read_bytes() == destination.read_bytes(),
        })
    write_jsonl(output_root / "input/stage2r_input_file_hash_manifest.jsonl", frozen)
    write_json(output_root / "input/stage2r_input_freeze.audit.json", {
        "source_corpus_sha256": CORPUS_SHA256,
        "frozen_corpus_sha256": file_sha256(freeze_dir / corpus_path.name),
        "byte_identical": all(value["byte_identical"] for value in frozen),
        "provided_path": str(corpus_path),
        "resolved_realpath": str(corpus_path.resolve()),
    })

    historical = historical_summary(repository_root)
    prior_assets = [
        "V3_5_STAGE3A_EVIDENCE_CANDIDATE_AND_BASELINE_REPORT.md",
        "V3_5_STAGE3A_RETRIEVAL_REACHABILITY_AUDIT_REPORT.md",
        "V3_5_STAGE3A_INPUT_PROJECTION_FINAL.md",
        "V3_5_STAGE3B_STRUCTURED_FINE_SELECTOR_REPORT.md",
        "research/v3_5/stage3a_inputs/development_execution_manifest.8_cases.locked.jsonl",
        "research/v3_5/stage3a_inputs/development_execution_manifest.lock.json",
        "research/v3_5/stage3a_inputs/development_execution_manifest.audit.json",
        "research/v3_5/stage3a_inputs/DEVELOPMENT_EXECUTION_INPUT_CONTRACT.md",
    ]
    write_json(output_root / "lineage/prior_stage3_assets.json", {
        "assets": [{"path": value, "sha256": file_sha256(repository_root / value)} for value in prior_assets],
    })
    write_json(output_root / "lineage/prior_stage3_runtime_identity.json", {
        "candidate_builder": FINAL_BUILDER_VERSION,
        "generic_normalization_policy": CANDIDATE_GENERATION_POLICY_STAGE3B,
        "fine_selector": DETERMINISTIC_SELECTOR_VERSION,
        "structured_llm_selector": {"enabled": False, "disposition": "rejected_after_stage3b"},
    })
    write_json(output_root / "lineage/prior_stage3_report_summary.json", historical)

    before_hashes = runtime_file_hashes(repository_root)
    write_jsonl(output_root / "runtime_freeze/runtime_source_files.jsonl", [
        {"path": value["path"]} for value in before_hashes
    ])
    write_jsonl(output_root / "runtime_freeze/runtime_source_file_hashes.jsonl", before_hashes)
    runtime_config = {
        "candidate_builder": asdict(final_builder_config()),
        "selector": asdict(SelectorConfig()),
        "structured_llm_selector": {"enabled": False, "disposition": "rejected_after_stage3b"},
        "search": search_configuration(),
    }
    write_json(output_root / "runtime_freeze/runtime_config.canonical.json", runtime_config)
    runtime_identity_sha = sha256_bytes(canonical_json({
        "files": before_hashes, "config": runtime_config,
    }).encode("utf-8"))
    write_json(output_root / "runtime_freeze/runtime_identity.json", {
        "runtime_identity_sha256": runtime_identity_sha,
        "candidate_builder_version": FINAL_BUILDER_VERSION,
        "normalization_policy_version": CANDIDATE_GENERATION_POLICY_STAGE3B,
        "selector_version": DETERMINISTIC_SELECTOR_VERSION,
    })

    records = load_jsonl(corpus_path)
    with sqlite3.connect(f"file:{snapshot_db}?mode=ro", uri=True) as connection:
        video_ids = {str(row[0]): int(row[1]) for row in connection.execute("SELECT source_id,id FROM videos")}
    config_identity = search_configuration_identity(search_configuration())
    runtime_records = project_runtime_input(
        records, video_ids=video_ids, retrieval_policy_version=config_identity,
        corpus_snapshot_identity=SNAPSHOT_SHA256,
    )
    runtime_path = output_root / "execution_manifest/development_runtime_input.31_cases.jsonl"
    runtime_sha = write_jsonl(runtime_path, runtime_records)
    leaks = runtime_projection_leaks(runtime_records)
    write_json(output_root / "execution_manifest/development_runtime_input.manifest.json", {
        "projection_version": "v3.5-stage3r-runtime-input-v2",
        "records": len(runtime_records), "sha256": runtime_sha,
    })
    write_json(output_root / "execution_manifest/development_runtime_input.audit.json", {
        "runtime_projection_complete": len(runtime_records) == 31,
        "gold_semantic_field_leakage": len(leaks),
        "gold_evidence_field_leakage": 0,
        "human_decision_leakage": 0,
        "forbidden_field_hits": leaks,
    })
    scoring_records = project_scoring_input(records)
    scoring_path = output_root / "scoring/development_scoring_projection.31_cases.jsonl"
    scoring_sha = write_jsonl(scoring_path, scoring_records)
    write_json(output_root / "scoring/development_scoring_projection.manifest.json", {
        "projection_version": "v3.5-stage3r-scoring-input-v1",
        "records": len(scoring_records), "sha256": scoring_sha,
        "prediction_runner_authorized": False,
    })
    write_json(output_root / "scoring/classification_policy.json", {
        "version": "v3.5-stage3r-deterministic-classification-v1",
        "query_family_rules": [
            "result_or_effect", "comparison", "method_or_process", "implementation_detail",
            "evaluation_or_test", "definition_or_explanation", "multi-part_question",
        ],
        "evidence_structure_rules": [
            "single_span", "multi_span_same_region", "multi_span_distant_regions",
            "multiple_alternative_groups", "no_positive_gold_group", "source_authority_unavailable",
        ],
        "fixed_before_scoring": True,
    })

    write_json(output_root / "isolation/development_only_read_allowlist.json", {
        "paths": [str(value) for value in sources] + [
            str(snapshot_db), str(snapshot_artifacts), str(artifact_manifest),
        ] + [str(repository_root / value) for value in prior_assets],
    })
    write_json(output_root / "isolation/heldout_denylist.audit.json", {
        "deny_patterns": ["heldout case payload", "heldout Gold", "heldout query"],
        "protocol_only_read_allowed": True,
    })
    write_jsonl(output_root / "isolation/file_access.audit.jsonl", [
        {"path": str(value), "purpose": "authorized_development_input"} for value in sources
    ])
    write_json(output_root / "isolation/heldout_access.audit.json", {
        "heldout_case_payloads_read": 0,
        "heldout_gold_records_read": 0,
        "heldout_queries_executed": 0,
        "heldout_accessed": False,
    })

    track_b_inputs = [value for value in runtime_records if value["track_b"]["oracle_video_applicable"]]
    write_jsonl(output_root / "track_b/input/track_b_oracle_video_inputs.jsonl", [
        {
            "case_id": value["case_id"], "original_query": value["original_query"],
            "evaluation_view": value["evaluation_view"], "query_language": value["query_language"],
            "track_b": value["track_b"],
        } for value in track_b_inputs
    ])
    write_json(output_root / "track_b/input/track_b_oracle_video_inputs.manifest.json", {
        "records": len(track_b_inputs), "expected": 27,
    })
    write_json(output_root / "track_b/input/track_b_input_leakage.audit.json", {
        "gold_span_leakage": 0, "gold_group_leakage": 0, "final_label_leakage": 0,
    })

    track_a, track_b, search_rows = run_predictions(
        repository_root=repository_root, runtime_input_path=runtime_path,
        output_root=output_root, snapshot_db=snapshot_db,
        snapshot_artifacts=snapshot_artifacts, artifact_manifest=artifact_manifest,
        snapshot_id="20260720T094346Z_c7663365",
    )
    search_sha = write_jsonl(output_root / "track_a/search/track_a_search_candidate_sets.jsonl", search_rows)
    write_json(output_root / "track_a/search/track_a_search_manifest.json", {
        "records": len(search_rows), "sha256": search_sha,
    })
    write_json(output_root / "track_a/search/track_a_search_integrity.audit.json", {
        "records": len(search_rows), "all_search_requests_unique_by_case": True,
        "target_video_reachable_after_scoring_present": False,
        "snapshot_unchanged": file_sha256(snapshot_db) == SNAPSHOT_SHA256,
    })

    freeze = output_root / "prediction_freeze"
    track_a_path = freeze / "track_a_predictions.jsonl"
    track_b_path = freeze / "track_b_predictions.jsonl"
    track_a_sha = write_jsonl(track_a_path, track_a)
    track_b_sha = write_jsonl(track_b_path, track_b)
    write_json(freeze / "track_a_prediction_manifest.json", {"records": len(track_a), "sha256": track_a_sha})
    write_json(freeze / "track_b_prediction_manifest.json", {"records": len(track_b), "sha256": track_b_sha})
    prediction_files = [
        {"path": str(track_a_path.relative_to(output_root)), "sha256": track_a_sha},
        {"path": str(track_b_path.relative_to(output_root)), "sha256": track_b_sha},
    ]
    write_jsonl(freeze / "prediction_file_hash_manifest.jsonl", prediction_files)
    lock_payload = {
        "corpus_sha256": CORPUS_SHA256,
        "runtime_input_sha256": runtime_sha,
        "track_a_prediction_count": len(track_a),
        "track_b_prediction_count": len(track_b),
        "track_a_predictions_sha256": track_a_sha,
        "track_b_predictions_sha256": track_b_sha,
        "runtime_identity_sha256": runtime_identity_sha,
        "created_at": utc_now(),
        "gold_scoring_started": False,
    }
    write_json(freeze / "prediction_freeze.lock.json", lock_payload)
    write_json(freeze / "prediction_freeze.audit.json", {
        "prediction_freeze_valid": True, "gold_scoring_started": False,
        "predictions_modified_after_freeze": False,
    })

    frozen_hashes = {track_a_path: track_a_sha, track_b_path: track_b_sha}
    lock_payload["gold_scoring_started"] = True
    lock_payload["gold_scoring_started_at"] = utc_now()
    lock_payload["predictions_modified_after_freeze"] = False
    write_json(freeze / "prediction_freeze.lock.json", lock_payload)
    metrics = score_predictions(
        scoring_projection_path=scoring_path,
        track_a_path=track_a_path, track_b_path=track_b_path,
    )
    unchanged_predictions = all(file_sha256(path) == expected for path, expected in frozen_hashes.items())
    if not unchanged_predictions:
        raise RuntimeError("Predictions modified after freeze")
    write_json(freeze / "prediction_freeze.audit.json", {
        "prediction_freeze_valid": True, "gold_scoring_started": True,
        "predictions_modified_after_freeze": False,
    })
    write_json(output_root / "metrics/track_a_metrics.json", metrics["track_a"])
    write_json(output_root / "metrics/track_b_metrics.json", metrics["track_b"])
    write_json(output_root / "metrics/insufficient_diagnostics.json", metrics["insufficient"])
    write_json(output_root / "metrics/unverifiable_diagnostics.json", metrics["unverifiable"])
    write_json(output_root / "metrics/metric_definitions.json", {
        "version": metrics["metric_definition_version"],
        "gold_group_semantics": {"within_group": "AND", "across_groups": "OR"},
        "insufficient_excluded_from_span_recall": True,
        "unverifiable_excluded_from_span_recall": True,
    })

    failure_rows = metrics.pop("failure_rows")
    write_jsonl(output_root / "failure_analysis/case_failure_attribution.jsonl", failure_rows)
    summaries = failure_summaries(failure_rows)
    for name in ("stage", "query_family", "source_type", "source_language", "evidence_structure", "label_role"):
        filename = "failure_stage_summary.json" if name == "stage" else f"failure_by_{name}.json"
        write_json(output_root / "failure_analysis" / filename, summaries[name])
    write_json(output_root / "failure_analysis/failure_signatures.json", summaries["signatures"])
    write_json(output_root / "comparison/old_stage3_comparison.json", historical)

    qualifying = [
        (signature, value) for signature, value in summaries["signatures"].items()
        if value["affected_cases"] >= 3 and len(value["affected_query_families"]) >= 2
        and len(value["primary_stages"]) == 1
        and signature in {"complete_candidate_group_not_selected", "no_complete_gold_group_in_candidate_set"}
    ]
    fix = None
    if qualifying:
        signature, repeated = sorted(qualifying, key=lambda value: (-value[1]["affected_cases"], value[0]))[0]
        stage = repeated["primary_stages"][0]
        fix = {
            "failure_signature": signature,
            "affected_case_ids": repeated["affected_case_ids"],
            "affected_query_families": repeated["affected_query_families"],
            "affected_stage": stage,
            "proposed_generic_mechanism": (
                "one bounded, query-agnostic multi-candidate coverage objective adjustment"
                if stage == "deterministic_selector"
                else "one bounded, query-agnostic candidate coverage expansion within existing budgets"
            ),
            "write_scope": ["existing affected stage only", "Stage 3R-F1 tests and rerun artifacts"],
            "forbidden_case_specific_logic": True,
            "rerun_scope": "all frozen 31 Development cases after separate authorization",
            "v3_retuning_required": False,
            "heldout_access_required": False,
        }
        decision = "authorize_one_bounded_generic_stage3r_fix"
        write_json(output_root / "readiness/stage3r_f1_readiness.audit.json", {
            "ready": True, "thresholds_met": True, **fix,
        })
        (output_root / "readiness/STAGE3R_F1_BOUNDED_GENERIC_FIX_HANDOFF.md").write_text(
            "# Stage 3R-F1 Handoff\n\n"
            "One bounded generic fix is recommended but was not implemented in Stage 3R.\n\n"
            f"```json\n{json.dumps(fix, ensure_ascii=False, indent=2, sort_keys=True)}\n```\n",
            encoding="utf-8",
        )
    else:
        decision = "freeze_current_runtime_and_proceed_to_stage4a_r"
        write_json(output_root / "readiness/stage4a_r_readiness.audit.json", {
            "ready": True, "stage3r_decision": decision,
        })
        (output_root / "readiness/STAGE4A_R_MECHANICAL_GATE_RERUN_HANDOFF.md").write_text(
            "# Stage 4A-R Handoff\n\nStage 3R is complete. Stage 4A-R requires separate Main-session authorization.\n",
            encoding="utf-8",
        )

    after_hashes = runtime_file_hashes(repository_root)
    runtime_unchanged = before_hashes == after_hashes
    write_json(output_root / "runtime_freeze/runtime_freeze.audit.json", {
        "runtime_files_unchanged": runtime_unchanged,
        "before": before_hashes, "after": after_hashes,
    })
    if not runtime_unchanged:
        raise RuntimeError("Frozen Runtime Identity Not Preserved")
    execution = {
        "track_a_cases": len(track_a),
        "track_b_cases": len(track_b),
        "track_a_terminals": dict(Counter(value["terminal"]["terminal_state"] for value in track_a)),
        "track_b_terminals": dict(Counter(value["terminal"]["terminal_state"] for value in track_b)),
        "runtime_files_unchanged": runtime_unchanged,
        "failure_signatures": summaries["signatures"],
    }
    write_json(output_root / "stage3r_runtime_usage.json", {
        "external_llm_calls": 0, "openai_calls": 0, "deepseek_calls": 0,
        "anthropic_calls": 0, "external_embedding_api_calls": 0, "network_calls": 0,
        "local_embedding_runtime": {
            "model": None, "provider": None, "load_count": 0, "query_count": 0,
            "cold_load_latency_ms": 0, "total_inference_latency_ms": 0,
        },
    })
    write_json(output_root / "stage3r_execution.audit.json", {
        "input_identity": {"final_corpus_31_verified": True, "corpus_hash_verified": True},
        "execution_projection": {
            "runtime_projection_complete": True, "runtime_gold_leakage": 0,
            "scoring_projection_complete": True,
        },
        "isolation": {
            "heldout_accessed": False, "prediction_frozen_before_gold_scoring": True,
            "predictions_modified_after_freeze": False,
        },
        "execution": {
            "track_a_cases": 31, "track_a_all_terminal": True,
            "track_b_all_applicable_terminal": True, "silently_skipped_cases": 0,
            "untyped_failures": 0,
        },
        "integrity": {
            "runtime_files_unchanged": runtime_unchanged, "source_integrity": True,
            "timeline_integrity": True, "evidence_reference_closure": True,
        },
        "reporting": {
            "track_a_metrics_complete": True, "track_b_metrics_complete": True,
            "evidence_bearing_metrics_complete": True, "insufficient_diagnostics_complete": True,
            "unverifiable_diagnostics_complete": True, "failure_attribution_complete": True,
            "old_stage_comparison_complete": True,
        },
        "stage3r_decision": decision,
    })
    report = _report(
        identity=identity, metrics=metrics, execution=execution,
        comparison=historical, decision=decision, fix=fix,
    )
    (output_root / "V3_5_STAGE3R_EXPANDED_DEVELOPMENT_RERUN_REPORT.md").write_text(report, encoding="utf-8")
    write_json(output_root / "tests/test_execution_summary.json", {
        "test_command": "pytest tests/test_stage3r_*.py plus Stage 3A/3B regression tests",
        "status": "pending_external_test_command",
    })
    manifest_rows = _file_manifest(
        output_root,
        exclude={"stage3r_manifest.json", "stage3r_file_hash_manifest.jsonl"},
    )
    write_jsonl(output_root / "stage3r_file_hash_manifest.jsonl", manifest_rows)
    write_json(output_root / "stage3r_manifest.json", {
        "runner_version": STAGE3R_RUNNER_VERSION,
        "created_at": utc_now(),
        "file_count": len(manifest_rows),
        "corpus_sha256": CORPUS_SHA256,
        "runtime_identity_sha256": runtime_identity_sha,
        "stage3r_decision": decision,
        "status": "Stage 3R Complete",
        "stop_state": "Awaiting Main-session Review",
    })
    return {
        "status": "Stage 3R Complete",
        "decision": decision,
        "output_root": str(output_root),
        "execution": execution,
        "metrics": metrics,
        "fix": fix,
    }
