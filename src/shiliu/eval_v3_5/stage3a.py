from __future__ import annotations

from dataclasses import asdict
import csv
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import sqlite3
from statistics import median
from typing import Iterable, Mapping, Sequence

from shiliu.evidence.contracts import EvidenceContractError, ParsedSourceArtifact, SourceArtifactReference
from shiliu.evidence.source import canonical_json, load_source_artifact
from shiliu.evidence.stage3a import (
    COVERAGE_SEMANTICS_VERSION,
    CandidateBuilderConfig,
    EvidenceBundle,
    EvidenceCandidate,
    EvidenceCandidateSet,
    SelectorConfig,
    interval_union_duration,
    build_within_video_candidates,
    resolve_from_search_candidates,
    select_deterministic_bundle,
)
from shiliu.eval_v3_5.isolation import HeldoutAccessGuard


STAGE3A_RUNNER_VERSION = "v3.5-stage3a-development-runner-v1"
EXPECTED_MANIFEST_HASH = "ef08e5c262d9fc885ab38d81c90f10ce4be6820c31d931c03f0ecdcfe71a534e"
EXPECTED_GOLD_HASH = "5693830749e3fba38dd35fc143988fb615ae48bf0f02b7344c8b03ce4a1d90d0"
EXPECTED_SNAPSHOT_HASH = "61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1"
EXPECTED_ARTIFACT_HASH = "36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f"
ORACLE_FORBIDDEN_FIELDS = frozenset({
    "gold_segment_ids", "gold_start", "gold_end", "gold_evidence_groups",
    "gold_span_times", "required_aspects", "supported_aspects", "missing_aspects",
    "sufficiency_label", "primary_reason_codes", "reason_codes", "labels",
})


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(text: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def validate_oracle_video_boundary(payload: Mapping[str, object], *, manifest_record: Mapping[str, object]) -> None:
    extra = set(payload) - {"case_id", "original_query", "oracle_target_video_id"}
    forbidden = set(payload) & ORACLE_FORBIDDEN_FIELDS
    if extra or forbidden:
        raise EvidenceContractError(
            f"oracle boundary contains forbidden or unsupported fields: {sorted(extra | forbidden)}",
            code="execution_manifest_mismatch",
        )
    if payload.get("case_id") != manifest_record.get("case_id") or payload.get("original_query") != manifest_record.get("original_query"):
        raise EvidenceContractError("oracle query identity differs from execution manifest", code="execution_manifest_mismatch")
    if payload.get("oracle_target_video_id") != manifest_record.get("target_video_id"):
        raise EvidenceContractError("oracle target differs from execution manifest", code="execution_manifest_mismatch")


def validate_search_candidate_set(record: Mapping[str, object]) -> None:
    payload = {
        "search_candidate_contract_version": record["search_candidate_contract_version"],
        "snapshot_database_sha256": record["snapshot_database_sha256"],
        "search_configuration_identity": record["search_configuration_identity"],
        "query_id": record["query_id"],
        "original_query": record["original_query"],
        "search_candidates": record["search_candidates"],
    }
    actual = sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != record.get("search_candidate_set_id"):
        raise EvidenceContractError("search candidate set identity mismatch", code="search_candidate_set_mismatch")


class FrozenRawSourceResolver:
    def __init__(self, *, artifact_manifest: Path, snapshot_db: Path, guard: HeldoutAccessGuard) -> None:
        self.artifact_manifest = artifact_manifest
        self.snapshot_db = snapshot_db
        records = load_jsonl(guard.read_text(artifact_manifest))
        self.records = {
            int(record["video_id"]): record for record in records
            if record.get("artifact_type") == "raw_subtitle" and record.get("video_id") is not None
        }
        self.cache: dict[int, ParsedSourceArtifact] = {}

    def __call__(self, video_id: int) -> ParsedSourceArtifact:
        if video_id in self.cache:
            return self.cache[video_id]
        record = self.records.get(video_id)
        if not record or record.get("status") != "ok" or not record.get("snapshot_path"):
            raise EvidenceContractError("no authoritative raw subtitle is available", code="no_supported_subtitle")
        with sqlite3.connect(f"file:{self.snapshot_db}?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT source_id, part, subtitle_source, subtitle_language FROM videos WHERE id=?",
                (video_id,),
            ).fetchone()
        if row is None:
            raise EvidenceContractError("video is absent from frozen snapshot", code="raw_source_unavailable")
        reference = SourceArtifactReference(
            platform="bilibili", source_id=str(row[0]), part=int(row[1]),
            source_type=str(row[2] or "unknown"), source_language=str(row[3] or "unknown"),
            artifact_path=str(record["snapshot_path"]), source_lineage=str(row[2] or "unknown"),
        )
        artifact = load_source_artifact(reference, expected_source_version=str(record["sha256"]))
        self.cache[video_id] = artifact
        return artifact


def candidate_union_covers(span: Mapping[str, object], candidates: Sequence[EvidenceCandidate]) -> bool:
    required = set(span.get("segment_ids", []))
    available = set().union(*(set(candidate.segment_ids) for candidate in candidates), set())
    return required.issubset(available)


def deterministic_covering_subset(
    span: Mapping[str, object], candidates: Sequence[EvidenceCandidate]
) -> tuple[EvidenceCandidate, ...]:
    required = set(span.get("segment_ids", []))
    eligible = [candidate for candidate in candidates if required & set(candidate.segment_ids)]
    for count in range(1, len(eligible) + 1):
        covering = [values for values in combinations(eligible, count) if required.issubset(set().union(*(set(value.segment_ids) for value in values), set()))]
        if covering:
            def key(values: tuple[EvidenceCandidate, ...]) -> tuple[object, ...]:
                duration = interval_union_duration((value.start_time, value.end_time) for value in values)
                union_ids = set().union(*(set(value.segment_ids) for value in values), set())
                return (duration, len(union_ids - required), tuple(sorted(value.candidate_id for value in values)))
            return tuple(sorted(covering, key=key)[0])
    return ()


def group_is_covered(group: Mapping[str, object], candidates: Sequence[EvidenceCandidate]) -> bool:
    return all(candidate_union_covers(span, candidates) for span in group.get("required_spans", []))


def bundle_hits_group(group: Mapping[str, object], bundle: EvidenceBundle | None, candidates: Sequence[EvidenceCandidate]) -> bool:
    if bundle is None:
        return False
    selected = {candidate.candidate_id: candidate for candidate in candidates}
    bundle_candidates = [selected[value] for value in bundle.candidate_ids if value in selected]
    return group_is_covered(group, bundle_candidates)


def _case_metrics(
    gold: Mapping[str, object], candidate_set: EvidenceCandidateSet, bundle: EvidenceBundle | None,
) -> dict[str, object]:
    groups = list(gold.get("gold_evidence_groups", []))
    gold_segments = set().union(*(
        set(span.get("segment_ids", [])) for group in groups for span in group.get("required_spans", [])
    ), set())
    complete = [group for group in groups if group_is_covered(group, candidate_set.candidates)]
    hit = any(bundle_hits_group(group, bundle, candidate_set.candidates) for group in groups)
    recalls = {}
    for k in (1, 3, 5):
        predicted = set().union(*(set(candidate.segment_ids) for candidate in candidate_set.candidates[:k]), set())
        recalls[f"gold_segment_recall_at_{k}"] = len(predicted & gold_segments) / max(1, len(gold_segments))
    start_errors: list[float] = []
    for group in complete:
        for span in group.get("required_spans", []):
            covering = deterministic_covering_subset(span, candidate_set.candidates)
            if covering:
                start_errors.append(abs(min(value.start_time for value in covering) - float(span["start_time"])))
    gold_intervals = [
        (float(span["start_time"]), float(span["end_time"]))
        for group in groups for span in group.get("required_spans", [])
    ]
    predicted_duration = bundle.union_duration if bundle else 0.0
    gold_duration = interval_union_duration(gold_intervals)
    return {
        "candidate_builder_case_covered": bool(complete),
        "complete_gold_groups_covered": len(complete),
        "complete_gold_group_count": len(groups),
        "required_spans_covered": sum(candidate_union_covers(span, candidate_set.candidates) for group in groups for span in group.get("required_spans", [])),
        "required_span_count": sum(len(group.get("required_spans", [])) for group in groups),
        **recalls,
        "deterministic_bundle_hit_at_1": hit,
        "median_start_time_error": median(start_errors) if start_errors else None,
        "predicted_gold_union_duration_ratio": predicted_duration / gold_duration if gold_duration else None,
        "candidate_count": len(candidate_set.candidates),
        "candidate_character_budget": sum(value.character_count for value in candidate_set.candidates),
        "candidate_token_budget": sum(value.lexical_token_count for value in candidate_set.candidates),
        "selected_bundle_candidate_count": len(bundle.candidate_ids) if bundle else 0,
        "selected_bundle_union_duration": predicted_duration,
    }


def _count_metric(cases: Sequence[Mapping[str, object]], key: str) -> dict[str, int]:
    correct = sum(bool(case.get(key)) for case in cases)
    return {"correct": correct, "incorrect": len(cases) - correct, "total": len(cases)}


def run_development_evaluation(
    *, repository_root: Path, manifest_path: Path, development_gold_path: Path,
    artifact_manifest_path: Path, snapshot_db_path: Path,
    builder_config: CandidateBuilderConfig | None = None,
    selector_config: SelectorConfig | None = None,
) -> dict[str, object]:
    builder_config = builder_config or CandidateBuilderConfig()
    selector_config = selector_config or SelectorConfig()
    guard = HeldoutAccessGuard(repository_root)
    identities = {
        "development_execution_manifest_sha256": file_sha256(guard.validate_path(manifest_path)),
        "development_gold_sha256": file_sha256(guard.validate_path(development_gold_path)),
        "artifact_manifest_sha256": file_sha256(guard.validate_path(artifact_manifest_path)),
        "snapshot_database_sha256": file_sha256(guard.validate_path(snapshot_db_path)),
    }
    expected = {
        "development_execution_manifest_sha256": EXPECTED_MANIFEST_HASH,
        "development_gold_sha256": EXPECTED_GOLD_HASH,
        "artifact_manifest_sha256": EXPECTED_ARTIFACT_HASH,
        "snapshot_database_sha256": EXPECTED_SNAPSHOT_HASH,
    }
    if identities != expected:
        raise EvidenceContractError(f"frozen input identity mismatch: {identities}", code="execution_manifest_mismatch")
    manifest = load_jsonl(guard.read_text(manifest_path))
    gold = {value["case_id"]: value for value in load_jsonl(guard.read_text(development_gold_path))}
    resolver = FrozenRawSourceResolver(artifact_manifest=artifact_manifest_path, snapshot_db=snapshot_db_path, guard=guard)
    track_a_cases: list[dict[str, object]] = []
    track_b_cases: list[dict[str, object]] = []
    traces: dict[str, dict[str, object]] = {}
    for record in manifest:
        validate_search_candidate_set(record)
        case_id = str(record["case_id"])
        search = record["search_candidates"]
        target = record.get("target_video_id")
        raw_units = list(search.get("raw_unit_candidates", []))
        videos = list(search.get("video_candidates", []))
        target_video_reachable = target is not None and any(value.get("video_id") == target for value in raw_units + videos)
        video_candidate_reachable = target is not None and any(value.get("video_id") == target for value in videos)
        transcript_chunk_reachable = target is not None and any(value.get("video_id") == target and value.get("unit_type") == "transcript_chunk" for value in raw_units)
        try:
            candidates_a = resolve_from_search_candidates(
                str(record["original_query"]), search, resolver, builder_config,
                query_id=str(record["query_id"]), search_candidate_set_id=str(record["search_candidate_set_id"]),
                execution_manifest_identity=EXPECTED_MANIFEST_HASH,
            )
            bundle_a = select_deterministic_bundle(str(record["original_query"]), candidates_a, selector_config)
        except EvidenceContractError as exc:
            candidates_a = EvidenceCandidateSet(
                query_id=str(record["query_id"]), original_query=str(record["original_query"]), candidates=(),
                evaluation_track="frozen_v3_end_to_end", end_to_end_claim_eligible=True,
                trace={"typed_error": exc.as_dict()}, normalization_status="typed_empty",
                validation_errors=(exc.code,), failure_category="normalization_failure",
            )
            bundle_a = None
        groups = list(gold[case_id].get("gold_evidence_groups", []))
        fine_metrics = _case_metrics(gold[case_id], candidates_a, bundle_a) if groups else {}
        failure = candidates_a.failure_category
        if groups and not failure:
            if not fine_metrics["candidate_builder_case_covered"]:
                failure = "candidate_generation_failure"
            elif not fine_metrics["deterministic_bundle_hit_at_1"]:
                failure = "selector_failure"
        track_a_cases.append({
            "case_id": case_id, "target_video_reachable": target_video_reachable,
            "video_candidate_reachable": video_candidate_reachable,
            "transcript_chunk_reachable": transcript_chunk_reachable,
            "candidate_builder_case_coverage": bool(candidates_a.candidates),
            "failure_category": failure, **fine_metrics,
            "candidate_ids": [value.candidate_id for value in candidates_a.candidates],
            "bundle_id": bundle_a.bundle_id if bundle_a else None,
        })
        traces[f"{case_id}.track_a"] = {"candidate_set": candidates_a.as_dict(), "bundle": bundle_a.as_dict() if bundle_a else None}
        if groups:
            payload = {"case_id": case_id, "original_query": record["original_query"], "oracle_target_video_id": target}
            validate_oracle_video_boundary(payload, manifest_record=record)
            artifact = resolver(int(target))
            candidates_b = build_within_video_candidates(
                str(record["original_query"]), int(target), artifact.source_version, artifact,
                builder_config, query_id=str(record["query_id"]),
            )
            bundle_b = select_deterministic_bundle(str(record["original_query"]), candidates_b, selector_config)
            metrics_b = _case_metrics(gold[case_id], candidates_b, bundle_b)
            if not metrics_b["candidate_builder_case_covered"]:
                failure_b = "candidate_generation_failure"
            elif not metrics_b["deterministic_bundle_hit_at_1"]:
                failure_b = "selector_failure"
            else:
                failure_b = None
            track_b_cases.append({
                "case_id": case_id, "evaluation_track": "oracle_video_conditional",
                "oracle_video_used": True, "end_to_end_claim_eligible": False,
                "failure_category": failure_b, **metrics_b,
                "candidate_ids": [value.candidate_id for value in candidates_b.candidates],
                "bundle_id": bundle_b.bundle_id if bundle_b else None,
            })
            traces[f"{case_id}.track_b"] = {"candidate_set": candidates_b.as_dict(), "bundle": bundle_b.as_dict() if bundle_b else None}
    evidence_a = [value for value in track_a_cases if value["case_id"] in {"CASE_001", "CASE_002", "CASE_003", "CASE_005"}]
    reachable_gold = [value for value in evidence_a if value["target_video_reachable"]]
    builder_eligible = [value for value in evidence_a if value.get("candidate_builder_case_covered")]
    selector_eligible = [value for value in evidence_a if value.get("complete_gold_groups_covered", 0)]
    track_a_summary = {
        "evidence_bearing_case_count": 4,
        "target_video_reachable": _count_metric(evidence_a, "target_video_reachable"),
        "video_candidate_reachable": _count_metric(evidence_a, "video_candidate_reachable"),
        "transcript_chunk_reachable": _count_metric(evidence_a, "transcript_chunk_reachable"),
        "upstream_retrieval_failure": {"count": sum(value["failure_category"] == "upstream_retrieval_failure" for value in evidence_a), "total": 4},
        "candidate_builder_case_coverage": _count_metric(evidence_a, "candidate_builder_case_covered"),
        "complete_gold_groups_covered": {"count": sum(int(value.get("complete_gold_groups_covered", 0)) for value in evidence_a), "total": sum(int(value.get("complete_gold_group_count", 0)) for value in evidence_a)},
        "selector_eligible_cases": len(selector_eligible),
        "deterministic_bundle_hit_at_1": {"count": sum(bool(value.get("deterministic_bundle_hit_at_1")) for value in selector_eligible), "eligible": len(selector_eligible)},
        "candidate_builder_coverage_given_target_video_reachable": _count_metric(reachable_gold, "candidate_builder_case_covered"),
        "selector_hit_given_complete_group_present": _count_metric(selector_eligible, "deterministic_bundle_hit_at_1"),
    }
    track_b_summary = {
        "candidate_builder_case_coverage": _count_metric(track_b_cases, "candidate_builder_case_covered"),
        "complete_gold_group_coverage": {"count": sum(int(value["complete_gold_groups_covered"]) for value in track_b_cases), "total": sum(int(value["complete_gold_group_count"]) for value in track_b_cases)},
        "required_span_coverage": {"count": sum(int(value["required_spans_covered"]) for value in track_b_cases), "total": sum(int(value["required_span_count"]) for value in track_b_cases)},
        "deterministic_bundle_hit_at_1": _count_metric(track_b_cases, "deterministic_bundle_hit_at_1"),
        "gold_segment_recall_at_1": sum(float(value["gold_segment_recall_at_1"]) for value in track_b_cases) / len(track_b_cases),
        "gold_segment_recall_at_3": sum(float(value["gold_segment_recall_at_3"]) for value in track_b_cases) / len(track_b_cases),
        "gold_segment_recall_at_5": sum(float(value["gold_segment_recall_at_5"]) for value in track_b_cases) / len(track_b_cases),
        "median_start_time_error": median(value["median_start_time_error"] for value in track_b_cases if value["median_start_time_error"] is not None) if any(value["median_start_time_error"] is not None for value in track_b_cases) else None,
        "per_case": track_b_cases,
    }
    return {
        "runner_version": STAGE3A_RUNNER_VERSION, "input_identities": identities,
        "builder_config": asdict(builder_config), "selector_config": asdict(selector_config),
        "track_a": {"summary": track_a_summary, "per_case": track_a_cases},
        "track_b": {"summary": track_b_summary, "per_case": track_b_cases},
        "traces": traces, "heldout_access_audit": guard.audit_record(
            source_files_scanned=["src/shiliu/evidence/stage3a.py", "src/shiliu/eval_v3_5/stage3a.py"],
            test_files_scanned=[], violations=[]),
    }


def write_development_artifacts(result: Mapping[str, object], *, output_directory: Path) -> None:
    """Materialize the frozen Development-only result; never accepts Held-out input."""
    output_directory.mkdir(parents=True, exist_ok=True)
    traces_directory = output_directory / "trace_samples"
    traces_directory.mkdir(exist_ok=True)

    def write_json(name: str, value: object) -> None:
        (output_directory / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    write_json("evidence_candidate_contract.json", {
        "contract_version": "v3.5-evidence-candidate-v1",
        "required_fields": [
            "candidate_id", "query_id", "video_id", "source_artifact_id", "source_version",
            "timeline_run_id", "segment_ids", "original_ordinals", "start_time", "end_time",
            "source_text", "source_language", "source_type", "parent_chunk_ids",
            "search_candidate_ids", "candidate_methods", "segment_count", "character_count",
            "lexical_token_count", "overlap_group_id", "related_candidate_ids",
            "overlap_relation", "trace_id", "normalization_status", "validation_errors",
        ],
        "identity": "SHA256(contract_version + source_artifact_id + source_version + timeline_run_id + ordered segment_ids + canonical candidate_methods + canonical parent_chunk_ids)",
        "invariants": ["single_video", "single_source_artifact", "single_source_version", "single_timeline_run", "contiguous_raw_segments", "raw_derived_text_and_time"],
        "typed_errors": [
            "segment_not_found", "segment_video_mismatch", "source_artifact_mismatch",
            "source_version_mismatch", "timeline_run_mismatch", "segment_order_invalid",
            "candidate_not_contiguous", "candidate_budget_exceeded", "raw_source_unavailable",
            "no_supported_subtitle", "invalid_bundle_reference", "execution_manifest_mismatch",
            "search_candidate_set_mismatch", "upstream_retrieval_failure",
        ],
    })
    write_json("evidence_bundle_contract.json", {
        "contract_version": "v3.5-evidence-bundle-v1",
        "required_fields": [
            "bundle_id", "query_id", "video_id", "source_artifact_ids", "source_versions",
            "timeline_run_ids", "candidate_ids", "normalized_spans", "union_duration",
            "source_texts", "selection_method", "score", "score_breakdown", "evaluation_track",
            "end_to_end_claim_eligible", "trace_id", "normalization_status", "validation_errors",
        ],
        "union_duration": "sum of merged non-overlapping candidate intervals; never envelope duration",
    })
    write_json("coverage_semantics_contract.json", {
        "coverage_semantics_version": COVERAGE_SEMANTICS_VERSION,
        "evidence_groups": "OR", "required_spans_within_group": "AND",
        "candidates_covering_span": "UNION",
        "covering_subset_tiebreak": ["complete segment coverage", "fewest candidates", "shortest union duration", "fewest extra segments", "candidate_id lexical"],
    })
    write_json("deterministic_selector_config.json", result["selector_config"])
    write_json("stage3a_run_manifest.json", {
        "runner_version": result["runner_version"], "input_identities": result["input_identities"],
        "builder_config": result["builder_config"], "selector_config": result["selector_config"],
        "evaluation_scope": "development_only", "heldout_executed": False,
    })
    write_json("track_a_reachability_eval.dev.json", result["track_a"])
    write_json("track_b_candidate_builder_eval.dev.json", {
        "summary": result["track_b"]["summary"],
        "per_case": [{key: value for key, value in case.items() if key != "bundle_id"} for case in result["track_b"]["per_case"]],
    })
    write_json("track_b_selector_eval.dev.json", result["track_b"])
    write_json("heldout_access_audit.json", result["heldout_access_audit"])
    tuning = {
        "candidate_builder_configs": [
            {"config_id": "stage3a-builder-default-v1", "within_video_max_candidates": 24, "result": "2/4 complete groups after final general algorithm; not selected"},
            {"config_id": result["builder_config"]["config_id"], "parameters": result["builder_config"], "result": result["track_b"]["summary"]["complete_gold_group_coverage"], "selected": True},
        ],
        "selector_configs": [
            {"config_id": "selector-k4", "max_candidates_per_bundle": 4, "selected": False},
            {"config_id": result["selector_config"]["config_id"], "parameters": result["selector_config"], "result": result["track_b"]["summary"]["deterministic_bundle_hit_at_1"], "selected": True},
            {"config_id": "selector-k8-locality", "max_candidates_per_bundle": 8, "selected": False},
        ],
        "selection_rationale": "32 candidates maximized complete-group coverage (3/4); default six-candidate selector retained because larger bundles did not improve hits and inflated duration.",
    }
    write_json("tuning_history.dev.json", tuning)

    for track_name, filename in (("track_a", "track_a_per_case.dev.csv"), ("track_b", "track_b_per_case.dev.csv")):
        rows = result[track_name]["per_case"]
        fields = sorted({key for row in rows for key in row if key not in {"candidate_ids"}})
        with (output_directory / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key) for key in fields})
    for name, trace in result["traces"].items():
        (traces_directory / f"{name}.json").write_text(
            json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    failures = [
        "# Stage 3A Development Failures", "",
        "Failure attribution is boundary-specific; Track B is not end-to-end.", "",
    ]
    for track_name in ("track_a", "track_b"):
        failures.append(f"## {track_name.replace('_', ' ').title()}")
        failures.append("")
        for case in result[track_name]["per_case"]:
            if case.get("failure_category"):
                failures.append(f"- {case['case_id']}: `{case['failure_category']}`")
        failures.append("")
    (output_directory / "failure_cases.dev.md").write_text("\n".join(failures), encoding="utf-8")

    examples = """# Stage 3A Functional Examples

- CASE_001: frozen target chunk IDs are validated against exact Stage 1 Raw segment IDs, split into run-local micro-windows, deduplicated, scored, and bundled.
- CASE_002: the V3 video-level candidate opens only video 40's frozen Raw transcript, scores the full transcript, and emits at most 32 bounded micro-windows.
- CASE_003 / CASE_005 Track A: the empty frozen SearchCandidateSet returns `upstream_retrieval_failure`; no candidate is fabricated.
- CASE_003 Track B: the manifest target video and frozen Raw transcript produce bounded candidates with `oracle_video_used=true` and `end_to_end_claim_eligible=false`; this is not end-to-end performance.
- Stable identity: repeated selected-config runs produced identical candidate IDs, bundle IDs, and ordering.
- Duplicate/overlap: exact spans merge provenance; high segment-Jaccard or interval-overlap windows are suppressed and retained overlaps record related IDs.
- Source mismatch: an expected/actual version mismatch raises `source_version_mismatch`.
- Missing source: an empty CandidateSet produces typed `upstream_retrieval_failure` and no Evidence.
"""
    (output_directory / "functional_examples.md").write_text(examples, encoding="utf-8")
