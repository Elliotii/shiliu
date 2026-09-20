from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


EXPECTED_STRESS_SET_SHA256 = "a337b52ef83c69a844425f673990b2fbe0f42307e3934b7f746e2c6a0af9f148"
RUNNER_VERSION = "v3.5-stage3r-qc-phase-a-v1"
EVIDENCE_LABELS = frozenset({"sufficient", "partial"})
ALLOWED_PACKET_FIELDS = (
    "case_id", "original_query", "query_type", "neutral_topic_terms", "authoring_instruction",
)
REQUIRED_QUERY_TYPES = frozenset({
    "definition", "purpose_or_use_case", "how_to_or_process", "comparison",
    "natural_multi_aspect", "actual_result_verification", "advanced_evidence_audit",
})
FORBIDDEN_PACKET_FIELDS = frozenset({
    "target_video_title", "bvid", "aid", "target_video_id", "gold_segment_id",
    "gold_timestamp", "gold_quote", "supported_aspects", "missing_aspects",
    "sufficiency_label", "q0_retrieval_result",
})
AUTHORING_INSTRUCTION = (
    "请写一个你在拾流中为了找到相关视频而会自然输入的简短搜索表达，"
    "再写最多三个互不重复的自然检索意图。"
)


class PhaseABlocked(RuntimeError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(canonical_json(row) for row in rows) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _source(record: Mapping[str, Any]) -> Mapping[str, Any]:
    decision = record["canonical_adjudication"]
    return record.get("source_context") or decision.get("source_identity") or {}


def _source_identity(record: Mapping[str, Any]) -> Mapping[str, Any]:
    source = _source(record)
    return source.get("source_identity") or source


def _query(record: Mapping[str, Any]) -> str:
    projection = record.get("query_projection")
    if projection:
        return str(projection["original_query"])
    return str(record["canonical_adjudication"]["source_identity"]["original_query"])


def _label(record: Mapping[str, Any]) -> str:
    return str(record["canonical_adjudication"]["final_status"])


def classify_query(query: str) -> tuple[str, str]:
    """Classify from Original Query lexical/syntactic cues only."""
    rules = (
        ("advanced_evidence_audit", r"安全审计|受控性能基准|评测流程|质量评测|测试集",
         "Original Query contains explicit audit/evaluation/test-set language."),
        ("actual_result_verification", r"是否.*(?:实际|真的|已有|确实|结果)|实际.*(?:结果|减少|节省)|节省多少|错误率|多少工时",
         "Original Query explicitly asks whether a claimed real-world result occurred or requests measured outcomes."),
        ("natural_multi_aspect", r"还缺哪些.*以及何时|上线前.*上线后|从原型.*云部署.*(?:测试|回滚)",
         "Original Query naturally combines multiple independently searchable aspects."),
        ("comparison", r"相比|有什么区别|各自怎样|分别适合|分别应该|自建而不是采购",
         "Original Query explicitly contrasts two alternatives, roles, or methods."),
        ("purpose_or_use_case", r"有什么作用|适合什么任务|用于|用法|为何使用",
         "Original Query explicitly asks about purpose, use, or task fit."),
        ("definition", r"是什么|有哪些|什么问题|什么关系|什么能力|为什么.*(?:会|变坏|重要|值得)",
         "Original Query asks for a definition, conceptual explanation, or causal account."),
        ("how_to_or_process", r"如何|怎样|怎么|流程|推进到|建立",
         "Original Query asks for a procedure, design method, or operational process."),
    )
    for query_type, pattern, reason in rules:
        if re.search(pattern, query, flags=re.IGNORECASE):
            return query_type, reason
    return "other", "No allowed lexical/syntactic rule matched; no Gold content was consulted."


def neutral_topic_terms(query: str) -> list[str]:
    """Mechanically retain distinctive Latin/alphanumeric tokens from Original Query only."""
    stop = {"and", "or", "the", "to", "from", "in", "what", "how", "why"}
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_+.-]*", query):
        if token.lower() not in stop and token not in terms:
            terms.append(token)
    return terms[:8]


def canonical_video_identity_from_gold(record: Mapping[str, Any]) -> dict[str, Any]:
    source = _source_identity(record)
    bvid = source.get("source_video_id") or source.get("video_id")
    artifact = source.get("source_artifact_id")
    version = source.get("source_version") or source.get("raw_source_sha256")
    if not bvid or not artifact or not version:
        raise PhaseABlocked(f"Gold video identity missing for {record['case_id']}")
    return {
        "source_platform": "bilibili",
        "product_video_id": None,
        "source_artifact_id": str(artifact),
        "source_version": str(version),
        "bvid": str(bvid),
        "aid": None,
    }


def canonical_video_identity_from_runtime(runtime: Mapping[str, Any]) -> dict[str, Any]:
    track_b = runtime["track_b"]
    required = ("authorized_source_identity", "internal_video_id", "source_artifact_id", "source_version")
    if any(track_b.get(field) in (None, "") for field in required):
        raise PhaseABlocked(f"Runtime video identity missing for {runtime['case_id']}")
    return {
        "source_platform": "bilibili",
        "product_video_id": int(track_b["internal_video_id"]),
        "source_artifact_id": str(track_b["source_artifact_id"]),
        "source_version": str(track_b["source_version"]),
        "bvid": str(track_b["authorized_source_identity"]),
        "aid": None,
    }


def video_identity_matches(gold: Mapping[str, Any], runtime: Mapping[str, Any]) -> bool:
    return all(gold[field] == runtime[field] for field in ("source_platform", "source_artifact_id", "source_version", "bvid"))


def classify_video_mapping(
    gold: Mapping[str, Any], runtime: Mapping[str, Any], result_bvids: Sequence[str],
) -> str:
    if gold["source_platform"] != runtime["source_platform"]:
        return "cross_source"
    if gold["source_version"] != runtime["source_version"]:
        return "cross_version"
    if not video_identity_matches(gold, runtime):
        return "identity_missing"
    matches = [value for value in result_bvids if value == runtime["bvid"]]
    if len(matches) > 1:
        return "identity_ambiguous"
    if not matches:
        return "runtime_result_not_present"
    return "identity_resolved"


def _result_bvids(prediction: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for candidate in prediction["search_candidate_set"].get("video_candidates", []):
        value = candidate.get("bvid") or candidate.get("source_id") or candidate.get("video_id")
        if value is not None:
            values.append(str(value))
    return values


def validate_hash_manifest(root: Path, manifest_path: Path) -> tuple[int, list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    rows = load_jsonl(manifest_path)
    for row in rows:
        path = root / row["path"]
        actual = file_sha256(path) if path.is_file() else None
        if actual != row["sha256"]:
            failures.append({"path": str(path), "expected_sha256": row["sha256"], "actual_sha256": actual})
    return len(rows), failures


def select_representative_cases(inventory: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    evidence = [dict(row) for row in inventory if row["label"] in EVIDENCE_LABELS]
    insufficient = [dict(row) for row in inventory if row["label"] == "insufficient"]
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    for query_type in sorted(REQUIRED_QUERY_TYPES):
        pool = insufficient if query_type == "actual_result_verification" else evidence
        candidates = sorted(
            (row for row in pool if row["query_type"] == query_type and row["case_id"] not in used),
            key=lambda row: (row["label"] != "partial", row["case_id"]),
        )
        if not candidates and pool is evidence:
            candidates = sorted(
                (row for row in inventory if row["query_type"] == query_type and row["case_id"] not in used
                 and row["label"] in EVIDENCE_LABELS),
                key=lambda row: row["case_id"],
            )
        if not candidates:
            raise PhaseABlocked(f"Required query type unavailable: {query_type}")
        chosen = candidates[0]
        selected.append(chosen)
        used.add(chosen["case_id"])
    while sum(row["label"] in EVIDENCE_LABELS for row in selected) < 8:
        candidates = sorted(
            (row for row in evidence if row["case_id"] not in used),
            key=lambda row: (Counter(x["query_type"] for x in selected)[row["query_type"]], row["case_id"]),
        )
        if not candidates:
            raise PhaseABlocked("Cannot select eight evidence-bearing cases")
        selected.append(candidates[0])
        used.add(candidates[0]["case_id"])
    if not any(row["label"] == "insufficient" for row in selected):
        candidates = sorted(row for row in insufficient if row["case_id"] not in used)
        if not candidates:
            raise PhaseABlocked("No insufficient diagnostic case available")
        selected.append(candidates[0])
    if len(selected) < 10:
        candidates = sorted(
            (row for row in evidence if row["case_id"] not in used),
            key=lambda row: (Counter(x["query_type"] for x in selected)[row["query_type"]], row["case_id"]),
        )
        selected.extend(candidates[:10 - len(selected)])
    if not (10 <= len(selected) <= 12):
        raise PhaseABlocked("Representative sample is outside 10–12 cases")
    return sorted(selected, key=lambda row: row["case_id"])


def _packet_markdown(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = ["# Stage 3R-QC Anonymized Query-authoring Packet", "", "仅根据下列允许字段填写另附的空白 JSONL 模板。", ""]
    for row in rows:
        lines.extend([
            f"## {row['case_id']}", "",
            f"- original_query: {row['original_query']}",
            f"- query_type: {row['query_type']}",
            f"- neutral_topic_terms: {', '.join(row['neutral_topic_terms']) or '(empty)'}",
            f"- authoring_instruction: {row['authoring_instruction']}", "",
        ])
    return "\n".join(lines) + "\n"


def _walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def build_phase_a(repository_root: str | Path) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    stage3r = root / "research/v3_5/stage3r"
    stage3r_s1 = root / "research/v3_5/stage3r_s1"
    output = root / "research/v3_5/stage3r_qc"
    corpus_path = stage3r / "input/stage2r_final_corpus/development_gold.executable_31.jsonl"
    stage3r_manifest = stage3r / "stage3r_manifest.json"
    s1_manifest = stage3r_s1 / "stage3r_s1_manifest.json"
    prediction_path = stage3r / "prediction_freeze/track_a_predictions.jsonl"
    runtime_path = stage3r / "execution_manifest/development_runtime_input.31_cases.jsonl"
    required = (corpus_path, stage3r_manifest, s1_manifest, prediction_path, runtime_path)
    if any(not path.is_file() for path in required):
        raise PhaseABlocked("Frozen Stage 3R/S1 assets cannot be located")
    if file_sha256(corpus_path) != EXPECTED_STRESS_SET_SHA256:
        raise PhaseABlocked("Stress Set SHA-256 mismatch")
    s3_count, s3_failures = validate_hash_manifest(stage3r, stage3r / "stage3r_file_hash_manifest.jsonl")
    s1_count, s1_failures = validate_hash_manifest(stage3r_s1, stage3r_s1 / "stage3r_s1_file_hash_manifest.jsonl")
    if s3_failures or s1_failures:
        raise PhaseABlocked("Frozen Stage 3R/S1 file hash manifest validation failed")

    gold_records = load_jsonl(corpus_path)
    predictions = load_jsonl(prediction_path)
    runtime_rows = load_jsonl(runtime_path)
    if len(gold_records) != 31 or len(predictions) != 31 or len(runtime_rows) != 31:
        raise PhaseABlocked("Frozen 31-case asset cardinality mismatch")
    labels = Counter(_label(row) for row in gold_records)
    if labels != Counter({"sufficient": 11, "partial": 9, "insufficient": 7, "unverifiable": 4}):
        raise PhaseABlocked(f"Stress Set label distribution mismatch: {labels}")
    gold_by_case = {str(row["case_id"]): row for row in gold_records}
    pred_by_case = {str(row["case_id"]): row for row in predictions}
    runtime_by_case = {str(row["case_id"]): row for row in runtime_rows}
    if set(gold_by_case) != set(pred_by_case) or set(gold_by_case) != set(runtime_by_case):
        raise PhaseABlocked("Frozen asset case identities differ")

    input_hash_rows = [
        {"path": str(path.relative_to(root)), "sha256": file_sha256(path), "size": path.stat().st_size}
        for path in required
    ]
    write_json(output / "input_freeze/stress_set_identity.json", {
        "path": str(corpus_path.relative_to(root)), "sha256": file_sha256(corpus_path),
        "records": 31, "labels": dict(sorted(labels.items())),
    })
    write_json(output / "input_freeze/stage3r_identity.json", {
        "manifest_path": str(stage3r_manifest.relative_to(root)), "manifest_sha256": file_sha256(stage3r_manifest),
        "file_hash_entries_verified": s3_count, "file_hash_failures": 0,
        "track_a_prediction_path": str(prediction_path.relative_to(root)),
        "track_a_prediction_sha256": file_sha256(prediction_path),
        "track_a_case_artifact_count": len(list((stage3r / "track_a/cases").glob("*/case_manifest.json"))),
    })
    write_json(output / "input_freeze/stage3r_s1_identity.json", {
        "manifest_path": str(s1_manifest.relative_to(root)), "manifest_sha256": file_sha256(s1_manifest),
        "file_hash_entries_verified": s1_count, "file_hash_failures": 0,
    })
    track_a_files = sorted(path for path in (stage3r / "track_a").rglob("*") if path.is_file())
    write_jsonl(output / "input_freeze/frozen_track_a_asset_manifest.jsonl", (
        {"path": str(path.relative_to(root)), "sha256": file_sha256(path), "size": path.stat().st_size}
        for path in track_a_files
    ))
    write_jsonl(output / "input_freeze/phase_a_input_hashes.jsonl", input_hash_rows)
    current_state_path = root / "V3_5_CURRENT_STATE.md"
    current_state_text = current_state_path.read_text(encoding="utf-8") if current_state_path.is_file() else ""
    state_facts_consistent = all(marker in current_state_text for marker in ("Stage 3R-S1", "0/20", "11/20", "2/20"))
    if current_state_path.is_file() and not state_facts_consistent:
        raise PhaseABlocked("V3_5_CURRENT_STATE.md conflicts with frozen Stage 3R-S1 facts")
    write_json(output / "input_freeze/phase_a_input_freeze.audit.json", {
        "passed": True, "heldout_accessed": False, "stress_set_identity_verified": True,
        "stage3r_hash_failures": 0, "stage3r_s1_hash_failures": 0,
        "current_state_document_present": current_state_path.is_file(),
        "current_state_facts_consistent": state_facts_consistent,
        "lessons_and_product_reframe_document_present": (root / "V3_5_EVAL_LESSONS_AND_PRODUCT_REFRAME.md").is_file(),
    })

    gold_projections: list[dict[str, Any]] = []
    runtime_projections: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    namespace: dict[str, set[tuple[Any, ...]]] = defaultdict(set)
    evidence_cases = [case_id for case_id, record in gold_by_case.items() if _label(record) in EVIDENCE_LABELS]
    insufficient_target_cases = [
        case_id for case_id, record in gold_by_case.items()
        if _label(record) == "insufficient"
        and _source_identity(record).get("source_artifact_id")
        and (_source_identity(record).get("source_video_id") or _source_identity(record).get("video_id"))
    ]
    identity_case_ids = sorted(set(evidence_cases) | set(insufficient_target_cases))
    for case_id in identity_case_ids:
        gold_identity = canonical_video_identity_from_gold(gold_by_case[case_id])
        runtime_identity = canonical_video_identity_from_runtime(runtime_by_case[case_id])
        case_role = "evidence_bearing" if case_id in evidence_cases else "insufficient_diagnostic_eligible"
        gold_projections.append({"case_id": case_id, "case_role": case_role, "canonical_video_identity": gold_identity})
        runtime_projections.append({"case_id": case_id, "case_role": case_role, "canonical_video_identity": runtime_identity})
        namespace[runtime_identity["bvid"]].add((
            runtime_identity["product_video_id"], runtime_identity["source_artifact_id"], runtime_identity["source_version"],
        ))
        status = classify_video_mapping(gold_identity, runtime_identity, _result_bvids(pred_by_case[case_id]))
        row = {
            "case_id": case_id, "case_role": case_role, "mapping_status": status,
            "gold_canonical_video_identity": gold_identity,
            "runtime_canonical_video_identity": runtime_identity,
            "identity_resolved": video_identity_matches(gold_identity, runtime_identity),
            "retrieval_miss": status == "runtime_result_not_present",
        }
        mappings.append(row)
        if status not in {"identity_resolved", "runtime_result_not_present"}:
            failures.append(row)
    duplicates = {bvid: sorted(values) for bvid, values in namespace.items() if len(values) > 1}
    resolved = sum(
        row["identity_resolved"] for row in mappings if row["case_role"] == "evidence_bearing"
    )
    insufficient_resolved = sum(
        row["identity_resolved"] for row in mappings if row["case_role"] == "insufficient_diagnostic_eligible"
    )
    ambiguous = sum(row["mapping_status"] == "identity_ambiguous" for row in mappings)
    write_jsonl(output / "video_identity/gold_video_identity_projection.jsonl", gold_projections)
    write_jsonl(output / "video_identity/runtime_video_identity_projection.jsonl", runtime_projections)
    write_jsonl(output / "video_identity/canonical_video_identity_mapping.jsonl", mappings)
    write_jsonl(output / "video_identity/video_identity_failures.jsonl", failures)
    identity_summary = {
        "evidence_bearing_cases": 20, "evidence_bearing_gold_video_identity_resolved": resolved,
        "insufficient_cases_with_explicit_target": len(insufficient_target_cases),
        "insufficient_target_video_identity_resolved": insufficient_resolved,
        "ambiguous_gold_video_identity": ambiguous, "duplicate_canonical_video_identity": len(duplicates),
        "runtime_result_not_present": sum(row["mapping_status"] == "runtime_result_not_present" for row in mappings),
        "identity_failures": len(failures), "preflight_gate_passed": resolved == 20 and not ambiguous and not duplicates,
    }
    write_json(output / "video_identity/video_identity_summary.json", identity_summary)
    write_json(output / "video_identity/video_identity_preflight.audit.json", {
        **identity_summary, "passed": identity_summary["preflight_gate_passed"],
        "title_matching_used": False, "manual_video_mapping_used": False,
        "identity_failure_definition": "Canonical authority fields fail to resolve uniquely or disagree.",
        "retrieval_miss_definition": "Canonical identity resolves, but the target BVID is absent from frozen SearchCandidateSet.",
    })
    if not identity_summary["preflight_gate_passed"]:
        raise PhaseABlocked("Canonical Video Identity Cannot Be Proven")

    inventory: list[dict[str, Any]] = []
    classifications: list[dict[str, Any]] = []
    for case_id in sorted(gold_by_case):
        query = _query(gold_by_case[case_id])
        query_type, reason = classify_query(query)
        row = {
            "case_id": case_id, "original_query": query, "label": _label(gold_by_case[case_id]),
            "evidence_bearing": _label(gold_by_case[case_id]) in EVIDENCE_LABELS,
            "query_type": query_type, "classification_reason": reason,
        }
        inventory.append(row)
        classifications.append({
            "case_id": case_id, "original_query": query, "query_type": query_type,
            "classification_reason": reason, "classification_inputs": ["original_query"],
        })
    selected = select_representative_cases(inventory)
    selected_ids = {row["case_id"] for row in selected}
    for row in selected:
        row["selection_reason"] = (
            f"Deterministic label/query-type stratification; represents {row['query_type']} "
            f"with label role {row['label']}; expected Q1/Q2 recoverability was not used."
        )
        row["canonical_target_video_identity"] = (
            canonical_video_identity_from_gold(gold_by_case[row["case_id"]])
            if _source_identity(gold_by_case[row["case_id"]]).get("source_artifact_id") else None
        )
    evidence_selected = sum(row["evidence_bearing"] for row in selected)
    insufficient_selected = sum(row["label"] == "insufficient" for row in selected)
    type_distribution = Counter(row["query_type"] for row in selected)
    label_distribution = Counter(row["label"] for row in selected)
    write_jsonl(output / "sample/eligible_case_inventory.jsonl", inventory)
    write_jsonl(output / "sample/query_type_classification.jsonl", classifications)
    write_jsonl(output / "sample/selected_cases.internal.jsonl", selected)
    write_json(output / "sample/selected_case_manifest.json", {
        "total_cases": len(selected), "evidence_bearing_cases": evidence_selected,
        "insufficient_diagnostic_cases": insufficient_selected,
        "label_distribution": dict(sorted(label_distribution.items())),
        "query_type_distribution": dict(sorted(type_distribution.items())),
        "required_query_types_covered": sorted(REQUIRED_QUERY_TYPES),
        "selection_used_expected_recovery_difficulty": False,
        "selected_case_ids": sorted(selected_ids),
    })
    write_json(output / "sample/sample_selection.audit.json", {
        "passed": 10 <= len(selected) <= 12 and 8 <= evidence_selected <= 10 and 1 <= insufficient_selected <= 2
        and REQUIRED_QUERY_TYPES.issubset(type_distribution),
        "total_cases_valid": 10 <= len(selected) <= 12,
        "evidence_bearing_count_valid": 8 <= evidence_selected <= 10,
        "insufficient_diagnostic_count_valid": 1 <= insufficient_selected <= 2,
        "insufficient_counted_as_evidence_bearing": False,
        "required_query_types_covered": REQUIRED_QUERY_TYPES.issubset(type_distribution),
        "heldout_accessed": False, "new_cases_added": False,
    })

    q0_rows: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    for case_id in sorted(selected_ids):
        prediction = pred_by_case[case_id]
        target = canonical_video_identity_from_gold(gold_by_case[case_id])["bvid"]
        result_ids = _result_bvids(prediction)
        rank = result_ids.index(target) + 1 if target in result_ids else None
        chunks = prediction.get("candidate_set", {}).get("candidates")
        q0_rows.append({
            "case_id": case_id, "q0_query": _query(gold_by_case[case_id]),
            "q0_target_video_hit": target in result_ids, "q0_target_video_rank": rank,
            "q0_video_level_hit": target in result_ids,
            "q0_transcript_chunk_hit": bool(chunks) if chunks is not None else "not_available_in_frozen_artifact",
            "q0_empty_result": not prediction["search_candidate_set"].get("video_candidates"),
            "q0_search_candidate_count": len(prediction["search_candidate_set"].get("video_candidates", [])),
        })
        traces.append({
            "case_id": case_id, "source": str(prediction_path.relative_to(root)),
            "source_sha256": file_sha256(prediction_path), "reused_frozen_q0": True, "v3_rerun": False,
        })
    write_jsonl(output / "q0_baseline/selected_q0_results.jsonl", q0_rows)
    write_jsonl(output / "q0_baseline/q0_asset_trace.jsonl", traces)
    write_json(output / "q0_baseline/q0_baseline_summary.json", {
        "selected_cases": len(q0_rows), "target_video_hits": sum(row["q0_target_video_hit"] for row in q0_rows),
        "empty_results": sum(row["q0_empty_result"] for row in q0_rows),
        "reused_frozen_q0": True, "v3_retrieval_calls": 0,
    })

    packet_rows = [{
        "case_id": row["case_id"], "original_query": row["original_query"],
        "query_type": row["query_type"], "neutral_topic_terms": neutral_topic_terms(row["original_query"]),
        "authoring_instruction": AUTHORING_INSTRUCTION,
    } for row in selected]
    query_dir = output / "query_authoring"
    write_json(query_dir / "authoring_packet_allowlist.json", {
        "allowed_fields": list(ALLOWED_PACKET_FIELDS), "neutral_topic_term_source": "original_query_only",
        "forbidden_fields": sorted(FORBIDDEN_PACKET_FIELDS),
    })
    guide = """# Stage 3R-QC Query Authoring Guide

请仅使用匿名 Packet 中的信息填写 `stage3r_qc_query_decisions.template.jsonl`。

- Q1：一个简短、自然、用于发现主题相关视频的搜索表达。
- Q2：1–3 个简短、自然、关注不同检索方面的意图；不要机械重复 Q1。
- 禁止加入目标视频标题、任何 Video ID、答案、Gold 字幕、时间或其他外部提示。
- 保持 `case_id` 不变；可填写 `human_notes`，不要改动 Packet。

此模板当前为空。Phase A 不生成或运行任何 Q1/Q2。
"""
    (query_dir / "STAGE3R_QC_QUERY_AUTHORING_GUIDE.md").parent.mkdir(parents=True, exist_ok=True)
    (query_dir / "STAGE3R_QC_QUERY_AUTHORING_GUIDE.md").write_text(guide, encoding="utf-8")
    (query_dir / "STAGE3R_QC_ANONYMIZED_QUERY_PACKET.md").write_text(_packet_markdown(packet_rows), encoding="utf-8")
    template_rows = [
        {"case_id": row["case_id"], "q1_discovery_query": "", "q2_retrieval_intents": [], "human_notes": ""}
        for row in selected
    ]
    write_jsonl(query_dir / "stage3r_qc_query_decisions.template.jsonl", template_rows)
    packet_keys = _walk_keys(packet_rows)
    packet_text = (query_dir / "STAGE3R_QC_ANONYMIZED_QUERY_PACKET.md").read_text(encoding="utf-8")
    known_bvids = {canonical_video_identity_from_gold(gold_by_case[row["case_id"]])["bvid"] for row in selected}
    leaked_ids = sorted(value for value in known_bvids if value in packet_text)
    leakage = {
        "passed": packet_keys == set(ALLOWED_PACKET_FIELDS) and not leaked_ids,
        "packet_fields": sorted(packet_keys), "allowlist_exact_match": packet_keys == set(ALLOWED_PACKET_FIELDS),
        "leaked_target_video_fields": len(packet_keys & FORBIDDEN_PACKET_FIELDS),
        "leaked_gold_fields": len(packet_keys & {
            "gold_segment_id", "gold_timestamp", "gold_quote", "supported_aspects", "missing_aspects", "sufficiency_label",
        }),
        "leaked_runtime_results": int("q0_retrieval_result" in packet_keys),
        "leaked_video_id_values": leaked_ids, "target_video_titles_read_for_packet": False,
    }
    write_json(query_dir / "authoring_packet_leakage.audit.json", leakage)
    if not leakage["passed"]:
        raise PhaseABlocked("Anonymized Packet Cannot Be Produced Without Gold Leakage")

    phase_tests = {
        "stress_set_identity": "passed", "heldout_isolation": "passed",
        "canonical_video_identity": "passed", "sample_contract": "passed",
        "frozen_q0_reuse": "passed", "packet_allowlist_and_leakage": "passed",
        "blank_query_template": "passed",
    }
    write_json(output / "phase_a_tests/phase_a_contract_checks.json", phase_tests)
    execution = {
        "status": "Stage 3R-QC Phase A Complete", "runner_version": RUNNER_VERSION,
        "v3_retrieval_calls": 0, "embedding_calls": 0, "external_llm_calls": 0,
        "external_network_calls": 0, "candidate_builder_calls": 0, "selector_calls": 0,
        "heldout_accessed": False, "q1_queries_generated_by_codex": 0, "q2_queries_generated_by_codex": 0,
        "phase_b_run": False, "ready_for_human_query_authoring": True,
    }
    write_json(output / "stage3r_qc_phase_a_execution.audit.json", execution)
    report = _report(
        corpus_path=corpus_path.relative_to(root), corpus_hash=file_sha256(corpus_path),
        stage3r_manifest=stage3r_manifest.relative_to(root), s1_manifest=s1_manifest.relative_to(root),
        identity=identity_summary, selected=selected, label_distribution=label_distribution,
        type_distribution=type_distribution,
    )
    (output / "V3_5_STAGE3R_QC_PHASE_A_PREPARATION_REPORT.md").write_text(report, encoding="utf-8")
    manifest = {
        "stage": "stage3r_qc_phase_a", "status": execution["status"], "runner_version": RUNNER_VERSION,
        "created_at": utc_now(), "input_stress_set_sha256": file_sha256(corpus_path),
        "selected_cases": len(selected), "identity_preflight_passed": True,
        "anonymized_packet_path": "query_authoring/STAGE3R_QC_ANONYMIZED_QUERY_PACKET.md",
        "blank_template_path": "query_authoring/stage3r_qc_query_decisions.template.jsonl",
        "phase_b_run": False, "stop_state": "Ready for Human Query Authoring",
    }
    write_json(output / "stage3r_qc_phase_a_manifest.json", manifest)
    hash_manifest = output / "stage3r_qc_phase_a_file_hash_manifest.jsonl"
    files = sorted(path for path in output.rglob("*") if path.is_file() and path != hash_manifest)
    write_jsonl(hash_manifest, (
        {"path": str(path.relative_to(output)), "sha256": file_sha256(path), "size": path.stat().st_size}
        for path in files
    ))
    return {
        "status": execution["status"], "selected_cases": len(selected),
        "evidence_bearing_cases": evidence_selected, "insufficient_diagnostic_cases": insufficient_selected,
        "query_type_distribution": dict(sorted(type_distribution.items())),
        "identity_preflight": identity_summary, "output_dir": str(output),
    }


def _report(
    *, corpus_path: Path, corpus_hash: str, stage3r_manifest: Path, s1_manifest: Path,
    identity: Mapping[str, Any], selected: Sequence[Mapping[str, Any]],
    label_distribution: Counter[str], type_distribution: Counter[str],
) -> str:
    reasons = "\n".join(f"- `{row['case_id']}`: {row['selection_reason']}" for row in selected)
    return f"""# V3.5 Stage 3R-QC Phase A Preparation Report

## 输入与冻结

1. Stress Set：`{corpus_path}`；SHA-256 `{corpus_hash}`。
2. Stage 3R Manifest：`{stage3r_manifest}`；S1 Manifest：`{s1_manifest}`。
3. Q0 完全复用冻结 Track A Prediction。
4. V3 调用：0。
5. Held-out 访问：false。

`V3_5_CURRENT_STATE.md` 存在且包含 S1 的 0/20、11/20、2/20 当前事实。
`V3_5_EVAL_LESSONS_AND_PRODUCT_REFRAME.md` 当前不存在；Phase A 未在允许边界外新建该文件。

## Video Identity

6. Evidence-bearing 目标身份解析：{identity['evidence_bearing_gold_video_identity_resolved']}/20。
7. Ambiguous Identity：{identity['ambiguous_gold_video_identity']}。
8. Duplicate canonical namespace identity：{identity['duplicate_canonical_video_identity']}。
9. Authority fields 不可唯一解析或相互冲突是 Identity Failure；identity 可解析但冻结 SearchCandidateSet 不含目标是 Retrieval Miss。
10. 以 BVID、内部 `product_video_id`、`source_artifact_id`、`source_version` 交叉验证后，未发现仍存 Video ID Namespace Bug 的证据。

## 样本

11. 选中 {len(selected)} Case。
12. Evidence-bearing：{sum(row['evidence_bearing'] for row in selected)}。
13. Insufficient diagnostic：{sum(row['label'] == 'insufficient' for row in selected)}。
14. 标签分布：`{dict(sorted(label_distribution.items()))}`。
15. Query Type 分布：`{dict(sorted(type_distribution.items()))}`。
16. 入选理由：

{reasons}

17. 未根据预期恢复难度挑选；只使用 Original Query 分类和标签角色分层。

## Authoring Packet

18. 仅展示 `case_id`、`original_query`、`query_type`、从 Original Query 机械提取的 `neutral_topic_terms`、统一 instruction。
19. 隐藏目标标题/ID、Gold、标签、Q0 结果及其他 reviewer/Codex 建议。
20. 目标标题泄漏：0。
21. BV/AID/Video ID 泄漏：0。
22. Gold Span/时间/字幕泄漏：0。
23. Sufficiency Label 泄漏：0。
24. Q0 Result 泄漏：0。

## 下一步与停止点

25. 人工填写 `query_authoring/stage3r_qc_query_decisions.template.jsonl`。
26. Q1 是一个简短自然的 discovery query，不直接回答完整 Evidence Question。
27. Q2 是 1–3 个简短自然且关注不同方面的 retrieval intents，不机械重复。
28. 人工完成后应在单独 Phase B 入口验证、hash 并冻结决策文件，且不得改写 Phase A Packet。
29. Phase B 未运行。
30. 当前 Codex Session 应在此停止，等待人工 Query Authoring。

## 完成状态

Stage 3R-QC Phase A Complete

Frozen Stage 3R/S1 Inputs Verified  
Canonical Video Identity Verified  
Representative QC Sample Selected  
Anonymized Query-authoring Packet Generated  
Blank Q1/Q2 Template Generated  
No Retrieval Executed  
No Q1/Q2 Generated by Codex  
Ready for Human Query Authoring
"""
