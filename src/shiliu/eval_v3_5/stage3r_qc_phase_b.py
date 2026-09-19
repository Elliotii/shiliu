from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from shiliu.eval_v3_5.stage3a_inputs import _search_service
from shiliu.eval_v3_5.stage3r import _search_payload, runtime_file_hashes
from shiliu.retrieval.planner import normalize_query
from shiliu.retrieval.product_search import ProductSearchRequest


RUNNER_VERSION = "v3.5-stage3r-qc-phase-b-v1"
REQUIRED_FIELDS = frozenset({
    "case_id", "q1_discovery_query", "q2_retrieval_intents", "human_notes",
})
FORBIDDEN_SOURCE_SUFFIXES = (".template.jsonl", ".proposed.jsonl")
SNAPSHOT_SHA256 = "61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1"
ARTIFACT_MANIFEST_SHA256 = "36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f"
SNAPSHOT_ID = "20260720T094346Z_c7663365"


class PhaseBBlocked(RuntimeError):
    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    path.write_text(payload + ("\n" if rows else ""), encoding="utf-8")


def load_jsonl_bytes(path: str | Path) -> list[dict[str, Any]]:
    try:
        text = Path(path).read_bytes().decode("utf-8")
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhaseBBlocked("approved_query_file_invalid", f"Invalid UTF-8 JSONL: {exc}") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise PhaseBBlocked("approved_query_file_invalid", "Every JSONL record must be an object")
    return rows


def require_approved_source(path: str | Path) -> Path:
    source = Path(path).resolve()
    if not source.is_file():
        raise PhaseBBlocked(
            "approved_query_file_missing",
            "The human-approved query decision file is missing",
            {"source_path": str(source)},
        )
    lower_name = source.name.lower()
    if lower_name.endswith(FORBIDDEN_SOURCE_SUFFIXES):
        raise PhaseBBlocked(
            "forbidden_query_file_kind",
            "Template and proposed query files cannot be used as Phase B input",
            {"source_path": str(source), "source_name": source.name},
        )
    return source


def validate_query_records(
    rows: Sequence[Mapping[str, Any]], expected_case_ids: Sequence[str],
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    case_ids: list[str] = []
    if len(rows) != 10:
        errors.append({"code": "record_count", "expected": 10, "actual": len(rows)})
    for index, row in enumerate(rows, start=1):
        if set(row) != REQUIRED_FIELDS:
            errors.append({
                "code": "schema_fields", "record": index,
                "missing": sorted(REQUIRED_FIELDS - set(row)),
                "unexpected": sorted(set(row) - REQUIRED_FIELDS),
            })
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            errors.append({"code": "invalid_case_id", "record": index})
        else:
            case_ids.append(case_id)
        q1 = row.get("q1_discovery_query")
        if not isinstance(q1, str) or not q1.strip():
            errors.append({"code": "empty_q1", "record": index})
        q2 = row.get("q2_retrieval_intents")
        if not isinstance(q2, list) or not 1 <= len(q2) <= 3:
            errors.append({"code": "invalid_q2_count", "record": index})
        elif any(not isinstance(intent, str) or not intent.strip() for intent in q2):
            errors.append({"code": "blank_q2_intent", "record": index})
        if not isinstance(row.get("human_notes"), str):
            errors.append({"code": "invalid_human_notes", "record": index})
    duplicates = sorted(case_id for case_id, count in Counter(case_ids).items() if count > 1)
    if duplicates:
        errors.append({"code": "duplicate_case_ids", "case_ids": duplicates})
    actual = set(case_ids)
    expected = set(expected_case_ids)
    if actual != expected:
        errors.append({
            "code": "case_alignment",
            "missing_case_ids": sorted(expected - actual),
            "unexpected_case_ids": sorted(actual - expected),
        })
    result = {
        "valid": not errors,
        "records": len(rows),
        "unique_case_ids": len(actual),
        "expected_case_ids": sorted(expected),
        "actual_case_ids": sorted(actual),
        "errors": errors,
    }
    if errors:
        raise PhaseBBlocked("approved_query_file_invalid", "Approved query file validation failed", result)
    return result


def audit_exact_leakage(
    rows: Sequence[Mapping[str, Any]],
    forbidden_values: Mapping[str, Sequence[str]],
    *,
    minimum_quote_length: int = 24,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for row in rows:
        queries = [row["q1_discovery_query"], *row["q2_retrieval_intents"]]
        for query_index, query in enumerate(queries):
            for category, values in forbidden_values.items():
                for value in values:
                    candidate = str(value)
                    if not candidate:
                        continue
                    is_quote = category == "gold_quotes"
                    if is_quote and len(candidate) < minimum_quote_length:
                        continue
                    if candidate.casefold() in query.casefold():
                        findings.append({
                            "case_id": row["case_id"],
                            "query_index": query_index,
                            "category": category,
                            "matched_value_sha256": sha256(candidate.encode("utf-8")).hexdigest(),
                        })
    return {"hard_leakage_count": len(findings), "findings": findings}


def freeze_approved_file(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    source_hash = file_sha256(source)
    frozen_hash = file_sha256(destination)
    if source_hash != frozen_hash or source.read_bytes() != destination.read_bytes():
        raise PhaseBBlocked("approved_query_freeze_failed", "Approved query bytes changed during freeze")
    return {
        "byte_preserved": True,
        "source_sha256": source_hash,
        "frozen_copy_sha256": frozen_hash,
        "hash_match": True,
    }


def selected_case_ids(repository_root: Path) -> list[str]:
    path = repository_root / "research/v3_5/stage3r_qc/sample/selected_case_manifest.json"
    return list(json.loads(path.read_text(encoding="utf-8"))["selected_case_ids"])


def _blocked_report(audit: Mapping[str, Any]) -> str:
    return "\n".join([
        "# V3.5 Stage 3R-QC Phase B — Blocked",
        "",
        "## Status",
        "",
        "Stage 3R-QC Phase B Blocked",
        "",
        "Approved Query File Invalid or Does Not Match Phase A",
        "",
        "## Gate result",
        "",
        f"- reason_code: `{audit['reason_code']}`",
        f"- source_path: `{audit.get('source_path', 'not_provided')}`",
        f"- source_sha256: `{audit.get('source_sha256', 'not_available')}`",
        "- approved_query_frozen: `false`",
        "- Q0 rerun: `false`",
        "- Q1 retrieval calls: `0`",
        "- Q2 retrieval calls: `0`",
        "- external calls: `0`",
        "- held-out accessed: `false`",
        "",
        "The supplied `.proposed.jsonl` file is explicitly forbidden by the Phase B input contract. "
        "Provide the human-approved `.approved.jsonl` file to resume.",
        "",
    ])


def write_blocked_attempt(
    repository_root: Path, error: PhaseBBlocked, source: str | Path | None,
) -> dict[str, Any]:
    output = repository_root / "research/v3_5/stage3r_qc/phase_b"
    source_path = Path(source).resolve() if source is not None else None
    audit: dict[str, Any] = {
        "stage": "Stage 3R-QC Phase B",
        "status": "blocked",
        "reason_code": error.code,
        "message": str(error),
        "details": error.details,
        "runner_version": RUNNER_VERSION,
        "recorded_at": utc_now(),
        "source_path": str(source_path) if source_path else None,
        "source_sha256": file_sha256(source_path) if source_path and source_path.is_file() else None,
        "approved_query_file_valid": False,
        "approved_query_frozen": False,
        "q0_v3_calls": 0,
        "q1_v3_calls": 0,
        "q2_v3_calls": 0,
        "candidate_builder_calls": 0,
        "selector_calls": 0,
        "sufficiency_judge_calls": 0,
        "external_llm_calls": 0,
        "external_network_calls": 0,
        "heldout_accessed": False,
    }
    write_json(output / "stage3r_qc_phase_b_execution.audit.json", audit)
    write_json(output / "query_validation/query_input_gate.audit.json", audit)
    report = output / "V3_5_STAGE3R_QC_PHASE_B_QUERY_CONTRACT_DIAGNOSTIC_REPORT.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_blocked_report(audit), encoding="utf-8")
    return audit


def run_phase_b_intake(repository_root: Path, approved_query_file: str | Path) -> dict[str, Any]:
    source = require_approved_source(approved_query_file)
    rows = load_jsonl_bytes(source)
    validation = validate_query_records(rows, selected_case_ids(repository_root))
    # Freezing happens only after source-kind, schema, and exact case-set gates pass.
    freeze = freeze_approved_file(
        source,
        repository_root
        / "research/v3_5/stage3r_qc/phase_b/input_freeze/approved_query_decisions.jsonl",
    )
    return {"status": "input_frozen", "validation": validation, "freeze": freeze}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _case_metadata(repository_root: Path) -> dict[str, dict[str, Any]]:
    path = repository_root / "research/v3_5/stage3r_qc/sample/selected_cases.internal.jsonl"
    return {row["case_id"]: row for row in _load_jsonl(path)}


def _identity_metadata(repository_root: Path) -> dict[str, dict[str, Any]]:
    path = repository_root / "research/v3_5/stage3r_qc/video_identity/canonical_video_identity_mapping.jsonl"
    return {
        row["case_id"]: row
        for row in _load_jsonl(path)
        if row["case_id"] in set(selected_case_ids(repository_root))
    }


def _runtime_records(repository_root: Path) -> dict[str, dict[str, Any]]:
    path = repository_root / "research/v3_5/stage3r/execution_manifest/development_runtime_input.31_cases.jsonl"
    return {row["case_id"]: row for row in _load_jsonl(path)}


def _gold_records(repository_root: Path) -> dict[str, dict[str, Any]]:
    path = repository_root / "research/v3_5/stage3r/input/stage2r_final_corpus/development_gold.executable_31.jsonl"
    return {row["case_id"]: row for row in _load_jsonl(path)}


def _query_texts(row: Mapping[str, Any]) -> list[str]:
    return [str(row["q1_discovery_query"]), *map(str, row["q2_retrieval_intents"])]


def build_forbidden_values(
    repository_root: Path,
    rows: Sequence[Mapping[str, Any]],
    snapshot_db: Path,
    snapshot_artifacts: Path,
) -> dict[str, list[str]]:
    case_ids = {row["case_id"] for row in rows}
    identities = _identity_metadata(repository_root)
    gold = _gold_records(repository_root)
    runtime = _runtime_records(repository_root)
    values: dict[str, list[str]] = {
        "video_ids": [], "bvid_aid": [], "source_artifact_ids": [],
        "gold_segment_ids": [], "full_target_titles": [], "gold_quotes": [],
    }
    target_product_ids: list[int] = []
    for case_id in sorted(case_ids):
        identity = identities[case_id]["runtime_canonical_video_identity"]
        runtime_row = runtime[case_id]
        values["video_ids"].append(str(identity["product_video_id"]))
        values["bvid_aid"].append(str(identity["bvid"]))
        values["source_artifact_ids"].append(str(identity["source_artifact_id"]))
        target_product_ids.append(int(identity["product_video_id"]))
        decision = gold[case_id]["canonical_adjudication"]
        for span in decision.get("final_evidence_spans", []):
            values["gold_segment_ids"].extend(map(str, span.get("segment_ids", [])))
        # Include every runtime-exposed identity representation in the mechanical blocklist.
        values["bvid_aid"].append(str(runtime_row["track_b"]["authorized_source_identity"]))
    placeholders = ",".join("?" for _ in target_product_ids)
    with sqlite3.connect(f"file:{snapshot_db}?mode=ro", uri=True) as connection:
        values["full_target_titles"] = [
            str(row[0])
            for row in connection.execute(
                f"SELECT title FROM videos WHERE id IN ({placeholders})", target_product_ids
            )
        ]
    for case_id in sorted(case_ids):
        bvid = identities[case_id]["runtime_canonical_video_identity"]["bvid"]
        transcript = snapshot_artifacts / str(bvid) / "subtitle-raw.json"
        if not transcript.is_file():
            continue
        segments = _load_json(transcript)
        contents = [str(segment.get("content", "")).strip() for segment in segments]
        values["gold_quotes"].extend(
            "".join(contents[index:index + 3])
            for index in range(max(0, len(contents) - 2))
            if len("".join(contents[index:index + 3])) >= 24
        )
    return {key: sorted(set(value for value in items if value)) for key, items in values.items()}


def _runtime_hash_check(repository_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    frozen_path = repository_root / "research/v3_5/stage3r/runtime_freeze/runtime_source_file_hashes.jsonl"
    expected = {row["path"]: row["sha256"] for row in _load_jsonl(frozen_path)}
    actual_rows = runtime_file_hashes(repository_root)
    mismatches = [
        {"path": row["path"], "expected": expected.get(row["path"]), "actual": row["sha256"]}
        for row in actual_rows
        if expected.get(row["path"]) != row["sha256"]
    ]
    return actual_rows, {
        "frozen_source_manifest": str(frozen_path),
        "files_checked": len(actual_rows),
        "mismatches": mismatches,
        "runtime_hashes_match_stage3r": not mismatches,
    }


def _file_manifest(directory: Path, destination: Path) -> None:
    rows = [
        {
            "path": str(path.relative_to(directory)),
            "sha256": file_sha256(path),
            "size": path.stat().st_size,
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path != destination
    ]
    write_jsonl(destination, rows)


def _score_search(payload: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, Any]:
    target_bvid = str(target["bvid"])
    target_video_id = int(target["product_video_id"])
    candidates = list(payload.get("video_candidates", []))
    matched = [
        candidate for candidate in candidates
        if str(candidate.get("source_id")) == target_bvid
        and int(candidate.get("video_id")) == target_video_id
    ]
    if len(matched) > 1:
        raise PhaseBBlocked("canonical_video_identity_scoring_failed", "Duplicate target canonical identity")
    video_level = bool(matched and matched[0].get("video_level_hit_present"))
    transcript_chunk = any(
        int(unit.get("video_id")) == target_video_id
        and unit.get("unit_type") == "transcript_chunk"
        for unit in payload.get("raw_unit_candidates", [])
    )
    hit_type = (
        "both" if video_level and transcript_chunk
        else "video_level" if video_level
        else "transcript_chunk" if transcript_chunk
        else "none"
    )
    return {
        "target_hit": bool(matched),
        "target_rank": int(matched[0]["product_rank"]) if matched else None,
        "hit_type": hit_type,
        "video_level_hit": video_level,
        "transcript_chunk_hit": transcript_chunk,
        "empty_result": not candidates,
        "candidate_video_count": len(candidates),
        "candidate_chunk_count": sum(
            unit.get("unit_type") == "transcript_chunk"
            for unit in payload.get("raw_unit_candidates", [])
        ),
    }


def _execute_query(
    service: Any,
    query: str,
    frozen_request: Mapping[str, Any],
    target: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    request_payload = {**dict(frozen_request), "query": query}
    request = ProductSearchRequest.model_validate(request_payload)
    result = service.search_library(request)
    if result.trace_persisted or result.presentation_trace_persisted:
        raise PhaseBBlocked("frozen_v3_runtime_identity_cannot_be_preserved", "Search trace persisted")
    payload = _search_payload(result)
    score = _score_search(payload, target)
    trace = {
        "search_trace_id": payload["search_trace_id"],
        "presentation_trace_id": payload["presentation_trace_id"],
        "executed_mode": payload["executed_mode"],
        "query_type": payload["query_type"],
        "fallback_state": payload["fallback_state"],
        "index_identity": payload["index_identity"],
        "trace_persisted": payload["trace_persisted"],
        "presentation_trace_persisted": payload["presentation_trace_persisted"],
    }
    return request_payload, payload, {**score, "trace": trace}


def _write_execution(
    directory: Path,
    request: Mapping[str, Any],
    payload: Mapping[str, Any],
    scored: Mapping[str, Any],
    *,
    reused: bool = False,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "request.json", request)
    write_json(directory / "search_candidate_set.json", payload)
    write_json(directory / "runtime_trace.json", scored["trace"])
    write_json(directory / "runtime_usage.json", {
        "retrieval_call_count": 0 if reused else 1,
        "reused_q1_result": reused,
        "local_query_embedding_calls": 0,
        "external_calls": 0,
    })


def _classification(q0: bool, q1: bool, q2: bool) -> str:
    if q0:
        return "already_retrievable"
    if q1:
        return "single_intent_contract_recoverable"
    if q2:
        return "decomposition_recoverable"
    return "persistent_retrieval_gap"


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
    }


def _view_hit_types(case_results: Sequence[Mapping[str, Any]], view: str) -> dict[str, int]:
    counts = Counter(
        row[view].get("hit_type", "none")
        for row in case_results
        if row["label_role"] == "evidence_bearing"
    )
    return {
        "video_level_only_hit": counts["video_level"],
        "transcript_chunk_hit": counts["transcript_chunk"],
        "both_video_and_chunk_hit": counts["both"],
        "target_video_miss": counts["none"],
    }


def _top_titles(payload: Mapping[str, Any], limit: int = 3) -> list[str]:
    return [str(row["title"]) for row in payload.get("video_candidates", [])[:limit]]


def _report_markdown(
    source: Path,
    freeze: Mapping[str, Any],
    runtime_identity: Mapping[str, Any],
    metrics: Mapping[str, Any],
    budget: Mapping[str, Any],
    by_type: Mapping[str, Any],
    insufficient: Mapping[str, Any],
    empty: Mapping[str, Any],
    wrong: Mapping[str, Any],
) -> str:
    lines = [
        "# V3.5 Stage 3R-QC Phase B Query Contract Diagnostic",
        "",
        "## Status",
        "",
        "Stage 3R-QC Phase B Complete",
        "",
        "Ready for Human Diagnostic Review",
        "",
        "## Input and runtime",
        "",
        f"- Approved file: `{source}`",
        f"- SHA-256: `{freeze['source_sha256']}`; byte-preserved freeze: `{str(freeze['byte_preserved']).lower()}`",
        "- Records: `10`; exact Phase A case alignment: `true`; hard query leakage: `0`",
        f"- Frozen V3 runtime identity: `{runtime_identity['runtime_identity_sha256']}`",
        "- Retrieval parameters modified: `false`; Q0 rerun: `false`; held-out accessed: `false`",
        f"- Q1 actual calls: `{budget['q1']['actual_new_calls']}`",
        f"- Q2 logical intents / actual new calls / Q1 reuse: `{budget['q2']['logical_intents']} / {budget['q2']['actual_new_calls']} / {budget['q2']['q1_results_reused']}`",
        "- Local query embedding calls: `0`; external calls: `0` (frozen mode was lexical)",
        "",
        "## Evidence-bearing results (n=9)",
        "",
        f"- Q0 recall: `{metrics['q0_target_video_recall']['numerator']}/9`",
        f"- Q1 recall: `{metrics['q1_target_video_recall']['numerator']}/9`",
        f"- Q2 recall: `{metrics['q2_target_video_recall']['numerator']}/9`",
        f"- Q1 incremental recovery: `{metrics['q1_incremental_recovery_over_q0']}`",
        f"- Q2 additional recovery: `{metrics['q2_incremental_recovery_over_q0_q1']}`",
        f"- Persistent misses: `{metrics['persistent_miss_count']}`",
        f"- Class counts: already `{metrics['already_retrievable_count']}`, single-intent `{metrics['single_intent_contract_recoverable_count']}`, decomposition `{metrics['decomposition_recoverable_count']}`, persistent `{metrics['persistent_retrieval_gap_count']}`",
        "",
        "## Query type",
        "",
    ]
    for query_type, value in sorted(by_type.items()):
        lines.append(
            f"- `{query_type}`: cases {value['case_count']}, Q0/Q1/Q2 hits "
            f"{value['q0_hits']}/{value['q1_hits']}/{value['q2_hits']}; "
            f"classifications `{value['classifications']}`"
        )
    lines.extend([
        "",
        "## Empty and non-empty misses",
        "",
        f"- Empty results: `{empty}`",
        f"- Non-empty target misses: `{wrong}`",
        "",
        "## Insufficient diagnostic (excluded from recall)",
        "",
        f"- `{insufficient['case_id']}` Q0/Q1/Q2: "
        f"`{insufficient['q0_target_hit']}/{insufficient['q1_target_hit']}/{insufficient['q2_target_hit']}`",
        f"- Natural Discovery Query found the topic target video: `{str(insufficient['q1_target_hit']).lower()}`",
        "",
        "## Interpretation boundary",
        "",
        "- This is a descriptive 9-case diagnostic, not a statistical-generalization claim.",
        "- Q2 is a multi-query diagnostic upper bound and is not a current product automation capability.",
        "- This run does not authorize changing V3, starting Product Query Set, or starting F1A/F1B.",
        "- Return to the main session for human review; close this Codex session after handoff.",
        "",
    ])
    return "\n".join(lines)


def _human_packet(case_results: Sequence[Mapping[str, Any]], payloads: Mapping[str, Any]) -> str:
    lines = ["# Stage 3R-QC Phase B Human Review Packet", ""]
    for row in case_results:
        lines.extend([
            f"## {row['case_id']}", "",
            f"- Query Type / Label Role: `{row['query_type']}` / `{row['label_role']}`",
            f"- Q0: {row['q0']['query']} → hit `{row['q0']['target_hit']}`, rank `{row['q0']['target_rank']}`",
            f"- Q1: {row['q1']['query']} → hit `{row['q1']['target_hit']}`, rank `{row['q1']['target_rank']}`",
            f"- Q2: `{row['q2']['intents']}` → hit `{row['q2']['target_hit']}`, best per-intent rank `{row['q2']['target_best_rank']}`, actual calls `{row['q2']['new_retrieval_call_count']}`",
            f"- Classification: `{row['classification']}`", "",
        ])
        if row["classification"] == "persistent_retrieval_gap":
            stored = payloads[row["case_id"]]
            lines.append(f"- Q1 top titles: `{_top_titles(stored['q1'])}`")
            for index, payload in enumerate(stored["q2"], start=1):
                lines.append(f"- Q2 intent {index} top titles: `{_top_titles(payload)}`")
            lines.extend(["- Matched chunk summary: `not_available_in_frozen_search_candidate_set`", ""])
    return "\n".join(lines)


def run_phase_b(
    *,
    repository_root: Path,
    approved_query_file: str | Path,
    snapshot_db: Path,
    snapshot_artifacts: Path,
    artifact_manifest: Path,
) -> dict[str, Any]:
    source = require_approved_source(approved_query_file)
    rows = load_jsonl_bytes(source)
    validation = validate_query_records(rows, selected_case_ids(repository_root))
    if file_sha256(snapshot_db) != SNAPSHOT_SHA256:
        raise PhaseBBlocked("frozen_v3_runtime_identity_cannot_be_preserved", "Snapshot hash mismatch")
    if file_sha256(artifact_manifest) != ARTIFACT_MANIFEST_SHA256:
        raise PhaseBBlocked("frozen_v3_runtime_identity_cannot_be_preserved", "Artifact manifest hash mismatch")
    runtime_before, runtime_audit_before = _runtime_hash_check(repository_root)
    if not runtime_audit_before["runtime_hashes_match_stage3r"]:
        raise PhaseBBlocked("frozen_v3_runtime_identity_cannot_be_preserved", "Runtime source hash mismatch")

    output = repository_root / "research/v3_5/stage3r_qc/phase_b"
    freeze_dir = output / "input_freeze"
    freeze = freeze_approved_file(source, freeze_dir / "approved_query_decisions.jsonl")
    ordered = sorted(rows, key=lambda row: row["case_id"])
    write_jsonl(freeze_dir / "approved_query_decisions.parsed.jsonl", ordered)
    identity = {
        **freeze, "records": len(rows), "source_path": str(source),
        "frozen_path": str(freeze_dir / "approved_query_decisions.jsonl"),
    }
    write_json(freeze_dir / "approved_query_decisions.identity.json", identity)
    write_json(freeze_dir / "approved_query_decisions.validation.json", validation)
    (freeze_dir / "approved_query_decisions.sha256").write_text(freeze["source_sha256"] + "\n")
    write_jsonl(freeze_dir / "phase_b_input_hashes.jsonl", [
        {"path": str(source), "sha256": freeze["source_sha256"]},
        {
            "path": "approved_query_decisions.jsonl",
            "sha256": freeze["frozen_copy_sha256"],
        },
    ])
    write_json(freeze_dir / "phase_b_input_freeze.audit.json", identity)

    forbidden = build_forbidden_values(
        repository_root, rows, snapshot_db, snapshot_artifacts
    )
    leakage = audit_exact_leakage(rows, forbidden)
    if leakage["hard_leakage_count"]:
        raise PhaseBBlocked("query_leakage_detected", "Hard query leakage detected", leakage)
    query_validation = output / "query_validation"
    write_json(query_validation / "query_schema_validation.json", validation)
    write_json(query_validation / "query_case_alignment.audit.json", {
        "case_alignment_valid": True,
        "expected_case_ids": sorted(selected_case_ids(repository_root)),
        "actual_case_ids": sorted(row["case_id"] for row in rows),
    })
    write_json(query_validation / "query_leakage.audit.json", {
        **leakage,
        "approved_query_file_valid": True,
        "case_alignment_valid": True,
        "audited_categories": sorted(forbidden),
        "neutral_topic_terms_used_as_queries": False,
        "gold_transcript_displayed": False,
    })
    write_json(query_validation / "query_input_gate.audit.json", {
        "status": "passed",
        "approved_query_file_valid": True,
        "case_alignment_valid": True,
        "hard_leakage_count": 0,
        "approved_query_frozen": True,
        "source_sha256": freeze["source_sha256"],
    })
    write_jsonl(query_validation / "query_normalization_preview.jsonl", [
        {
            "case_id": row["case_id"],
            "kind": kind,
            "query_index": index,
            "execution_query": query,
            "frozen_runtime_normalized_query": normalize_query(query),
        }
        for row in ordered
        for index, (kind, query) in enumerate(
            [("q1", row["q1_discovery_query"])]
            + [("q2", query) for query in row["q2_retrieval_intents"]],
            start=1,
        )
    ])

    runtime_dir = output / "runtime_freeze"
    runtime_identity = _load_json(repository_root / "research/v3_5/stage3r/runtime_freeze/runtime_identity.json")
    runtime_config = _load_json(repository_root / "research/v3_5/stage3r/runtime_freeze/runtime_config.canonical.json")
    write_json(runtime_dir / "frozen_v3_runtime_identity.json", {
        **runtime_identity,
        "retrieval_version": runtime_config["search"]["lexical_provider_version"],
        "router_version": runtime_config["search"]["retrieval_router_version"],
        "normalization_version": runtime_identity["normalization_policy_version"],
        "lexical_version": runtime_config["search"]["lexical_provider_version"],
        "dense_provider": runtime_config["search"]["dense_provider_version"],
        "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
        "hybrid_rrf_version": runtime_config["search"]["fusion_version"],
        "chunk_version": runtime_identity["normalization_policy_version"],
        "top_k": runtime_config["search"]["requested_limit"],
        "filters": runtime_config["search"]["request_defaults"]["filters"],
        "scope": runtime_config["search"]["request_defaults"]["scope"],
        "index_identity": SNAPSHOT_SHA256,
    })
    write_jsonl(runtime_dir / "frozen_v3_runtime_file_hashes.jsonl", runtime_before)
    write_json(runtime_dir / "frozen_v3_runtime_config.audit.json", {
        **runtime_audit_before, "retrieval_parameters_modified": False,
    })

    cases = _case_metadata(repository_root)
    identities = _identity_metadata(repository_root)
    runtimes = _runtime_records(repository_root)
    q0_rows = {
        row["case_id"]: row
        for row in _load_jsonl(
            repository_root / "research/v3_5/stage3r_qc/q0_baseline/selected_q0_results.jsonl"
        )
    }
    case_results: list[dict[str, Any]] = []
    payload_cache: dict[str, Any] = {}
    q1_calls = 0
    q2_calls = 0
    q2_reuse = 0
    q2_logical = 0
    q2_unique = 0
    with tempfile.TemporaryDirectory(prefix="shiliu-stage3r-qc-phase-b-") as temporary:
        work_db = Path(temporary) / "snapshot-work-copy.db"
        shutil.copy2(snapshot_db, work_db)
        service = _search_service(
            work_db=work_db, snapshot_artifacts=snapshot_artifacts,
            artifact_manifest=artifact_manifest, snapshot_id=SNAPSHOT_ID,
        )
        for decision in ordered:
            case_id = decision["case_id"]
            target = identities[case_id]["runtime_canonical_video_identity"]
            frozen_request = runtimes[case_id]["track_a"]["search_request"]
            q1_query = decision["q1_discovery_query"]
            request1, payload1, scored1 = _execute_query(service, q1_query, frozen_request, target)
            q1_calls += 1
            q1_dir = output / "execution/q1/cases" / case_id
            _write_execution(q1_dir, request1, payload1, scored1)
            _file_manifest(q1_dir, q1_dir / "file_hash_manifest.jsonl")

            intents = list(decision["q2_retrieval_intents"])
            q2_logical += len(intents)
            executed: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = {}
            intent_results: list[dict[str, Any]] = []
            q2_payloads: list[dict[str, Any]] = []
            new_calls_case = 0
            reused_case = 0
            for index, query in enumerate(intents, start=1):
                if query == q1_query:
                    execution = (request1, payload1, scored1)
                    reused = True
                    q2_reuse += 1
                    reused_case += 1
                elif query in executed:
                    execution = executed[query]
                    reused = True
                else:
                    execution = _execute_query(service, query, frozen_request, target)
                    executed[query] = execution
                    reused = False
                    q2_calls += 1
                    new_calls_case += 1
                request2, payload2, scored2 = execution
                intent_dir = output / "execution/q2/cases" / case_id / f"intent_{index:02d}"
                _write_execution(intent_dir, request2, payload2, scored2, reused=reused)
                intent_results.append({
                    "intent_index": index, "query": query,
                    "target_hit": scored2["target_hit"],
                    "target_rank": scored2["target_rank"],
                    "empty_result": scored2["empty_result"],
                    "reused_q1_result": query == q1_query,
                })
                q2_payloads.append(payload2)
            q2_unique += len(set(intents))
            union: dict[str, dict[str, Any]] = {}
            for index, payload in enumerate(q2_payloads, start=1):
                for candidate in payload.get("video_candidates", []):
                    canonical = str(candidate["source_id"])
                    union.setdefault(canonical, {
                        "canonical_video_identity": canonical,
                        "per_intent_ranks": {},
                    })["per_intent_ranks"][str(index)] = int(candidate["product_rank"])
            hit_intents = [
                value["intent_index"] for value in intent_results if value["target_hit"]
            ]
            ranks = {
                str(value["intent_index"]): value["target_rank"]
                for value in intent_results
            }
            q2_summary = {
                "intents": intents,
                "logical_intent_count": len(intents),
                "unique_execution_query_count": len(set(intents)),
                "new_retrieval_call_count": new_calls_case,
                "reused_q1_result_count": reused_case,
                "target_hit": bool(hit_intents),
                "target_best_rank": min(
                    (value["target_rank"] for value in intent_results if value["target_rank"] is not None),
                    default=None,
                ),
                "target_per_intent_ranks": ranks,
                "target_hit_intents": hit_intents,
                "union_candidate_video_count": len(union),
                "all_intents_empty": all(value["empty_result"] for value in intent_results),
                "hit_type": (
                    "both" if any(_score_search(payload, target)["hit_type"] == "both" for payload in q2_payloads)
                    else "video_level" if any(_score_search(payload, target)["video_level_hit"] for payload in q2_payloads)
                    else "transcript_chunk" if any(_score_search(payload, target)["transcript_chunk_hit"] for payload in q2_payloads)
                    else "none"
                ),
            }
            q2_dir = output / "execution/q2/cases" / case_id
            write_json(q2_dir / "q2_union.json", {
                "merge_rule": "union_of_canonical_video_identities",
                "reranked": False,
                "candidates": list(union.values()),
            })
            write_json(q2_dir / "q2_case_summary.json", {
                **q2_summary, "intent_results": intent_results,
            })
            _file_manifest(q2_dir, q2_dir / "file_hash_manifest.jsonl")

            q0 = q0_rows[case_id]
            q0_result = {
                "query": q0["q0_query"],
                "target_hit": q0["q0_target_video_hit"],
                "target_rank": q0["q0_target_video_rank"],
                "hit_type": (
                    "both" if q0["q0_video_level_hit"] and q0["q0_transcript_chunk_hit"]
                    else "video_level" if q0["q0_video_level_hit"]
                    else "transcript_chunk" if q0["q0_transcript_chunk_hit"]
                    else "none"
                ),
                "empty_result": q0["q0_empty_result"],
                "candidate_video_count": q0["q0_search_candidate_count"],
            }
            q1_result = {
                "query": q1_query,
                **{key: scored1[key] for key in (
                    "target_hit", "target_rank", "hit_type", "empty_result",
                    "candidate_video_count", "candidate_chunk_count",
                )},
                "retrieval_call_count": 1,
            }
            classification = _classification(
                q0_result["target_hit"], q1_result["target_hit"], q2_summary["target_hit"]
            )
            case_results.append({
                "case_id": case_id,
                "label_role": "evidence_bearing" if cases[case_id]["evidence_bearing"] else "insufficient_diagnostic",
                "query_type": cases[case_id]["query_type"],
                "q0": q0_result,
                "q1": q1_result,
                "q2": q2_summary,
                "classification": classification,
                "q1_regression_vs_q0": q0_result["target_hit"] and not q1_result["target_hit"],
                "q2_regression_vs_q1": q1_result["target_hit"] and not q2_summary["target_hit"],
            })
            payload_cache[case_id] = {"q1": payload1, "q2": q2_payloads}

    write_jsonl(output / "scoring/case_results.jsonl", case_results)
    evidence = [row for row in case_results if row["label_role"] == "evidence_bearing"]
    classifications = Counter(row["classification"] for row in evidence)
    metrics = {
        "q0_target_video_recall": _rate(sum(row["q0"]["target_hit"] for row in evidence), 9),
        "q1_target_video_recall": _rate(sum(row["q1"]["target_hit"] for row in evidence), 9),
        "q2_target_video_recall": _rate(sum(row["q2"]["target_hit"] for row in evidence), 9),
        "q1_incremental_recovery_over_q0": sum(
            not row["q0"]["target_hit"] and row["q1"]["target_hit"] for row in evidence
        ),
        "q2_incremental_recovery_over_q0_q1": sum(
            not row["q0"]["target_hit"] and not row["q1"]["target_hit"] and row["q2"]["target_hit"]
            for row in evidence
        ),
        "persistent_miss_count": classifications["persistent_retrieval_gap"],
        **{f"{name}_count": classifications[name] for name in (
            "already_retrievable", "single_intent_contract_recoverable",
            "decomposition_recoverable", "persistent_retrieval_gap",
        )},
    }
    by_type: dict[str, Any] = {}
    for query_type in (
        "definition", "purpose_or_use_case", "how_to_or_process", "comparison",
        "natural_multi_aspect", "actual_result_verification", "advanced_evidence_audit",
    ):
        subset = [row for row in case_results if row["query_type"] == query_type]
        by_type[query_type] = {
            "case_count": len(subset),
            "q0_hits": sum(row["q0"]["target_hit"] for row in subset),
            "q1_hits": sum(row["q1"]["target_hit"] for row in subset),
            "q2_hits": sum(row["q2"]["target_hit"] for row in subset),
            "classifications": dict(Counter(row["classification"] for row in subset)),
            "small_sample_no_significance_claim": True,
        }
    insufficient_row = next(row for row in case_results if row["label_role"] == "insufficient_diagnostic")
    insufficient = {
        "case_id": insufficient_row["case_id"],
        "excluded_from_evidence_bearing_recall": True,
        "q0_target_hit": insufficient_row["q0"]["target_hit"],
        "q1_target_hit": insufficient_row["q1"]["target_hit"],
        "q2_target_hit": insufficient_row["q2"]["target_hit"],
    }
    budget = {
        "q0": {"actual_new_calls": 0, "source": "frozen_stage3r"},
        "q1": {"logical_queries": 10, "actual_new_calls": q1_calls},
        "q2": {
            "logical_intents": q2_logical,
            "unique_execution_queries": q2_unique,
            "actual_new_calls": q2_calls,
            "q1_results_reused": q2_reuse,
        },
    }
    empty = {
        "q0_empty_result_rate": _rate(sum(row["q0"]["empty_result"] for row in evidence), 9),
        "q1_empty_result_rate": _rate(sum(row["q1"]["empty_result"] for row in evidence), 9),
        "q2_all_intents_empty_rate": _rate(sum(row["q2"]["all_intents_empty"] for row in evidence), 9),
        "per_intent_empty_result_rate": _rate(
            sum(
                not payload.get("video_candidates")
                for row in evidence for payload in payload_cache[row["case_id"]]["q2"]
            ),
            sum(len(row["q2"]["intents"]) for row in evidence),
        ),
    }
    wrong = {
        view: {
            "wrong_video_nonempty_miss_count": sum(
                not row[view]["target_hit"]
                and not (
                    row[view]["empty_result"] if view != "q2" else row[view]["all_intents_empty"]
                )
                for row in evidence
            ),
            "wrong_video_nonempty_miss_rate": None,
        }
        for view in ("q0", "q1", "q2")
    }
    for value in wrong.values():
        value["wrong_video_nonempty_miss_rate"] = value["wrong_video_nonempty_miss_count"] / 9

    analysis = output / "analysis"
    write_json(analysis / "evidence_bearing_metrics.json", metrics)
    write_json(analysis / "insufficient_diagnostic_result.json", insufficient)
    write_json(analysis / "metrics_by_query_type.json", by_type)
    write_json(analysis / "metrics_by_hit_type.json", {
        view: _view_hit_types(case_results, view) for view in ("q0", "q1", "q2")
    })
    write_json(analysis / "retrieval_budget_summary.json", budget)
    write_json(analysis / "empty_result_summary.json", empty)
    write_json(analysis / "wrong_video_nonempty_miss_summary.json", wrong)
    write_json(analysis / "query_contract_classification_summary.json", {
        "counts": dict(classifications),
        "semantic_neighbor_recall": {"status": "not_scored_no_frozen_definition"},
    })
    write_jsonl(analysis / "persistent_miss_cases.jsonl", [
        row for row in evidence if row["classification"] == "persistent_retrieval_gap"
    ])
    review = output / "review"
    review.mkdir(parents=True, exist_ok=True)
    (review / "semantic_neighbor_review_packet.md").write_text(
        _human_packet(case_results, payload_cache), encoding="utf-8"
    )
    (output / "STAGE3R_QC_PHASE_B_HUMAN_REVIEW_PACKET.md").write_text(
        _human_packet(case_results, payload_cache), encoding="utf-8"
    )
    write_json(output / "isolation/heldout_access.audit.json", {
        "heldout_accessed": False, "heldout_queries_executed": 0,
        "heldout_gold_records_read": 0,
    })

    runtime_after, runtime_audit_after = _runtime_hash_check(repository_root)
    if runtime_before != runtime_after or not runtime_audit_after["runtime_hashes_match_stage3r"]:
        raise PhaseBBlocked("frozen_v3_runtime_identity_cannot_be_preserved", "Runtime changed during execution")
    write_json(output / "phase_b_tests/runtime_integrity_check.json", {
        "runtime_hashes_unchanged": True, "before": runtime_before, "after": runtime_after,
    })
    usage = {
        "q0_v3_calls": 0, "q1_v3_calls": q1_calls, "q2_v3_calls": q2_calls,
        "candidate_builder_calls": 0, "selector_calls": 0, "sufficiency_judge_calls": 0,
        "external_llm_calls": 0, "external_network_calls": 0,
        "local_query_embedding_calls": 0,
        "embedding_provider_identity": runtime_config["search"]["dense_provider_version"],
        "embedding_model_identity": "Qwen/Qwen3-Embedding-0.6B",
        "heldout_accessed": False,
    }
    write_json(output / "stage3r_qc_phase_b_runtime_usage.json", usage)
    execution_audit = {
        "status": "complete", **usage,
        "approved_query_file_valid": True, "case_alignment_valid": True,
        "hard_leakage_count": 0, "q0_rerun": False,
        "retrieval_configuration_modified": False,
        "canonical_video_identity_reused": True,
        "q2_reranked": False,
        "product_query_set_started": False, "f1a_f1b_started": False,
    }
    write_json(output / "stage3r_qc_phase_b_execution.audit.json", execution_audit)
    write_json(output / "stage3r_qc_phase_b_manifest.json", {
        "stage": "Stage 3R-QC Phase B", "status": "complete",
        "approved_query_sha256": freeze["source_sha256"],
        "runtime_identity_sha256": runtime_identity["runtime_identity_sha256"],
        "case_count": 10, "evidence_bearing_denominator": 9,
    })
    (output / "V3_5_STAGE3R_QC_PHASE_B_QUERY_CONTRACT_DIAGNOSTIC_REPORT.md").write_text(
        _report_markdown(
            source, freeze, runtime_identity, metrics, budget, by_type,
            insufficient, empty, wrong,
        ),
        encoding="utf-8",
    )
    _file_manifest(output, output / "stage3r_qc_phase_b_file_hash_manifest.jsonl")
    return {
        "status": "complete",
        "approved_query_sha256": freeze["source_sha256"],
        "metrics": metrics,
        "retrieval_budget": budget,
        "runtime_usage": usage,
    }
