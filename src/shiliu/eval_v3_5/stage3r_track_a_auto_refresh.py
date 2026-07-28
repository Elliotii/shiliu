"""Frozen omitted-mode Product Search replay for the Stage 3R stress Track A."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from shiliu.evidence.stage3a import (
    CandidateBuilderConfig,
    SelectorConfig,
    resolve_from_search_candidates,
    select_deterministic_bundle,
    validate_bundle,
)
from shiliu.eval_v3_5.isolation import HeldoutAccessGuard
from shiliu.eval_v3_5.stage3a import FrozenRawSourceResolver
from shiliu.eval_v3_5.stage3r import (
    FINAL_BUILDER_VERSION,
    _search_payload,
    file_sha256,
    final_builder_config,
    runtime_file_hashes,
)
from shiliu.eval_v3_5.stage3r_qc_phase_b_r import build_search_service, inspect_index
from shiliu.retrieval.planner import SearchPlanner, SearchRequest
from shiliu.retrieval.product_search import (
    EXISTING_AUTO_ROUTER_VERSION,
    PRODUCT_DEFAULT_WIRING_VERSION,
    PRODUCT_SEARCH_DEFAULT_MODE,
    ProductSearchRequest,
)
from shiliu.retrieval.qwen import QWEN_MODEL_ID, QWEN_MODEL_PATH, QWEN_PROVIDER_VERSION, QwenEmbeddingProvider, verify_qwen_snapshot
from shiliu.retrieval.hybrid import FUSION_VERSION
from shiliu.retrieval.service import INDEX_VERSION
from shiliu.evidence.stage3a import DETERMINISTIC_SELECTOR_VERSION


RUNNER_VERSION = "v3.5-stage3r-track-a-auto-refresh-v1"
OUTPUT_RELATIVE = Path("research/v3_5/stage3r_qc/track_a_auto_refresh")
SNAPSHOT_ID = "20260720T094346Z_c7663365"
SNAPSHOT_SHA256 = "61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1"
ARTIFACT_MANIFEST_SHA256 = "36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f"
SCORING_RELATIVE = Path("research/v3_5/stage3r/scoring/development_scoring_projection.31_cases.jsonl")
RUNTIME_RELATIVE = Path("research/v3_5/stage3r/execution_manifest/development_runtime_input.31_cases.jsonl")
SEGMENT_BRIDGE_RELATIVE = Path("research/v3_5/stage3r_s1/identity_mapping/gold_segment_identity_projection.jsonl")
CANONICAL_IDENTITY_RELATIVE = Path("research/v3_5/stage3r_qc/video_identity/canonical_video_identity_mapping.jsonl")


class TrackAAutoRefreshBlocked(RuntimeError):
    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + ("\n" if rows else ""), encoding="utf-8")


def _sha(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_omitted_mode_request(query: str) -> tuple[dict[str, Any], ProductSearchRequest]:
    """The serialized request deliberately has no ``mode`` key."""
    payload = {"query": query}
    request = ProductSearchRequest.model_validate(payload)
    if "mode" in request.model_fields_set or request.mode != "auto" or not request.default_applied:
        raise TrackAAutoRefreshBlocked("product_default_not_auto", "Omitted mode did not resolve to Product Auto", payload)
    return payload, request


def classify_failure(*, target_hit: bool, complete_group: bool, bundle_hit: bool, blocked: bool = False) -> str:
    if blocked:
        return "blocked_identity_or_runtime_failure"
    if bundle_hit:
        return "end_to_end_bundle_hit"
    if not target_hit:
        return "retrieval_failure"
    if not complete_group:
        return "candidate_builder_failure"
    return "deterministic_selector_failure"


def _complete_groups(groups: Sequence[Mapping[str, Any]], candidates: Sequence[Mapping[str, Any]]) -> list[str]:
    available = set().union(*(set(value.get("segment_ids", [])) for value in candidates)) if candidates else set()
    completed = []
    for group in groups:
        if all(set(span.get("segment_ids", [])).issubset(available) for span in group.get("required_spans", [])):
            completed.append(str(group["group_id"]))
    return completed


def _physical_groups(case_id: str, groups: Sequence[Mapping[str, Any]], bridge: Mapping[tuple[str, str], str]) -> list[dict[str, Any]]:
    """Use the S1 bridge only during scoring; it is never passed to runtime code."""
    converted: list[dict[str, Any]] = []
    for group in groups:
        value = {**group, "required_spans": []}
        for span in group.get("required_spans", []):
            converted_span = dict(span)
            converted_span["segment_ids"] = [bridge[(case_id, str(segment))] for segment in span.get("segment_ids", [])]
            value["required_spans"].append(converted_span)
        converted.append(value)
    return converted


def _runtime_identity(repository_root: Path, snapshot_db: Path) -> dict[str, Any]:
    planner_hash = file_sha256(repository_root / "src/shiliu/retrieval/planner.py")
    actual_router_version = f"unversioned:SearchPlanner@sha256:{planner_hash}"
    frozen = json.loads((repository_root / "research/v3_5/auto_smoke/runtime_preflight/auto_runtime_identity.json").read_text(encoding="utf-8"))
    if actual_router_version != frozen["auto_router_version"]:
        raise TrackAAutoRefreshBlocked("auto_router_identity_mismatch", "Auto Router source differs from the frozen Auto Smoke", {"expected": frozen["auto_router_version"], "actual": actual_router_version})
    index = inspect_index(snapshot_db)
    if index["index_sha256_or_manifest_identity"] != SNAPSHOT_SHA256 or not index["embedding_index_available"]:
        raise TrackAAutoRefreshBlocked("index_identity_mismatch", "Frozen index or hybrid embedding index is unavailable", index)
    return {
        "auto_router_version": actual_router_version,
        "declared_auto_router_version": EXISTING_AUTO_ROUTER_VERSION,
        "lexical_version": INDEX_VERSION,
        "dense_provider": QWEN_PROVIDER_VERSION,
        "embedding_model": QWEN_MODEL_ID,
        "hybrid_rrf_version": FUSION_VERSION,
        "index_identity": SNAPSHOT_SHA256,
        "snapshot_identity": SNAPSHOT_ID,
        "chunk_version": "v3.5-search-candidate-v1",
        "top_k": 10,
        "raw_top_k": 50,
        "scope": "all",
        "filters": {},
        "candidate_builder_version": FINAL_BUILDER_VERSION,
        "candidate_builder_normalization_version": "v3.5-stage3b-asr-acronym-anchor-v1",
        "deterministic_selector_version": DETERMINISTIC_SELECTOR_VERSION,
        "selector_policy_version": "v3.5-deterministic-fine-selector-v1",
        "index": index,
    }


def _preflight(repository_root: Path, snapshot_db: Path, snapshot_artifacts: Path, artifact_manifest: Path) -> dict[str, Any]:
    wiring = json.loads((repository_root / "research/v3_5/product_default_auto_wiring/product_default_auto_wiring_manifest.json").read_text(encoding="utf-8"))
    checks = {
        "frontend_initial_mode_auto": wiring.get("frontend", {}).get("initial_default_mode") == "auto",
        "backend_omitted_mode_auto": wiring.get("backend", {}).get("omitted_mode_default") == "auto" and PRODUCT_SEARCH_DEFAULT_MODE == "auto",
        "wiring_version": wiring.get("wiring_version") == PRODUCT_DEFAULT_WIRING_VERSION,
        "snapshot_hash": file_sha256(snapshot_db) == SNAPSHOT_SHA256,
        "artifact_manifest_hash": file_sha256(artifact_manifest) == ARTIFACT_MANIFEST_SHA256,
    }
    if not all(checks.values()):
        raise TrackAAutoRefreshBlocked("wiring_or_snapshot_preflight_failed", "Product default or frozen input identity failed preflight", checks)
    verify_qwen_snapshot(QWEN_MODEL_PATH)
    runtime = _runtime_identity(repository_root, snapshot_db)
    payload, request = build_omitted_mode_request("MCP")
    plan = SearchPlanner().plan(SearchRequest(query=request.query, mode=request.mode, raw_top_k=50))
    known_positive = {"request": payload, "default_applied": request.default_applied, "router_invoked": True, "router_decision": plan.planned_mode, "effective_mode": plan.planned_mode}
    return {"checks": checks, "runtime_identity": runtime, "known_positive_contract": known_positive}


def _case_hash_manifest(case_dir: Path) -> None:
    rows = [{"path": path.name, "sha256": file_sha256(path), "bytes": path.stat().st_size} for path in sorted(case_dir.iterdir()) if path.is_file() and path.name != "file_hash_manifest.jsonl"]
    write_jsonl(case_dir / "file_hash_manifest.jsonl", rows)


def _render_report(summary: Mapping[str, Any]) -> str:
    metric = summary["metrics"]
    attribution = metric["failure_attribution"]
    runtime = summary["runtime_identity"]
    usage = summary["runtime_usage"]
    return f"""# V3.5 Stage 3R Track A Auto Product Refresh

Status: **Stage 3R-QC-R Complete**. The run used the 20 frozen Evidence-bearing cases, each original query, and a ProductSearchRequest with the `mode` field omitted. Backend default: `auto`; wiring: `{PRODUCT_DEFAULT_WIRING_VERSION}`.

## Input and Runtime

- Evidence-bearing cases: 20/20. Original Query used for every request: yes. `mode` omitted: yes. Backend Auto Default applied: yes.
- Router: `{runtime['auto_router_version']}`. Index/snapshot: `{runtime['index_identity']}` / `{runtime['snapshot_identity']}`. Lexical: `{runtime['lexical_version']}`. Dense provider/model/RRF: `{runtime['dense_provider']}` / `{runtime['embedding_model']}` / `{runtime['hybrid_rrf_version']}`.
- Builder/normalization: `{runtime['candidate_builder_version']}` / `{runtime['candidate_builder_normalization_version']}`. Selector/policy: `{runtime['deterministic_selector_version']}` / `{runtime['selector_policy_version']}`.
- No configuration or algorithm was modified; the router, retrieval, builder, selector, and index remained frozen.

| Metric | Historical Explicit Lexical Track A | Corrected Product-default Auto Track A |
| --- | ---: | ---: |
| Target Video Recall | 0/20 | {metric['target_video_recall']['numerator']}/20 |
| Complete Gold Group Candidate Coverage | 0/20 | {metric['complete_gold_group_candidate_coverage']['numerator']}/20 |
| Bundle Hit | 0/20 | {metric['bundle_hit']['numerator']}/20 |

Router distribution: `{metric['router_distribution']}`. Target-rank distribution: `{metric['target_video_rank']}`.

Empty results: `{metric['empty_result_count']}`. Router misses: `{metric['router_miss_count']}`.

Builder conditional coverage given target-video retrieval: `{metric['conditional_builder_coverage_given_target_video_retrieved']['numerator']}/{metric['conditional_builder_coverage_given_target_video_retrieved']['denominator']}`. Selector conditional bundle hit given a complete candidate group: `{metric['conditional_bundle_hit_given_complete_candidate_group']['numerator']}/{metric['conditional_bundle_hit_given_complete_candidate_group']['denominator']}`.

Failure attribution: retrieval `{attribution['retrieval_failure']}`, builder `{attribution['candidate_builder_failure']}`, selector `{attribution['deterministic_selector_failure']}`, end-to-end hits `{attribution['end_to_end_bundle_hit']}`, blocked `{attribution['blocked_identity_or_runtime_failure']}`. Total: {sum(attribution.values())}/20. Builder failures are target-video hits without a complete Gold Group; selector failures are complete-group candidate sets whose selected bundle missed every complete Gold Group.

The frozen Oracle-video Track B remains a conditional diagnostic only: 11/20 complete candidate coverage and 2/20 bundle hits. It is not an end-to-end Product result. The historical 0/20 lexical result is consistent with the prior Product-default lexical wiring; this refresh attributes all 20 historical target-video misses to that historical default path, not to the frozen Auto run.

Product Query Set/F1A/F1B: not started. Held-out: not accessed. Structured LLM selector, sufficiency judge, final-answer, external LLM, and external network calls: all 0 (`{usage}`). This evaluation is complete and intentionally stops for human review; it does not authorize closing the Codex session.

The historical lexical assets were read-only and retained. This refresh is a new frozen baseline and stops for human review.
"""


def _render_review(rows: Sequence[Mapping[str, Any]], metrics: Mapping[str, Any]) -> str:
    lines = ["# Stage 3R Track A Auto Refresh Human Review Packet", "", "## Summary", "", f"Target Video Recall: {metrics['target_video_recall']['numerator']}/20", f"Complete Gold Group Coverage: {metrics['complete_gold_group_candidate_coverage']['numerator']}/20", f"Bundle Hit: {metrics['bundle_hit']['numerator']}/20", f"Router distribution: `{metrics['router_distribution']}`", "", "## Failure Cases", ""]
    for row in rows:
        if row["classification"] == "end_to_end_bundle_hit":
            continue
        lines.extend([f"### {row['case_id']}", "", row["original_query"], "", f"Router: `{row['routing']['router_decision']}`; effective mode: `{row['routing']['effective_mode']}`", f"Target video: `{row['retrieval']['target_video_hit']}` / rank `{row['retrieval']['target_video_rank']}`", f"Complete Gold Group Available: `{row['builder']['complete_gold_group_covered']}`; Bundle Hit: `{row['selector']['bundle_hit']}`", f"Primary Failure Attribution: `{row['classification']}`"])
        if row["classification"] == "candidate_builder_failure":
            lines.extend([f"Builder candidate count: `{row['builder']['candidate_count']}`; Gold segments reachable: `{row['builder']['gold_segments_present_count']}/{row['builder']['gold_segments_total_count']}`; missing complete group: `{row['builder']['candidate_builder_failure_reason']}`"])
        if row["classification"] == "deterministic_selector_failure":
            lines.extend([f"Available complete Gold Groups: `{row['builder']['covered_gold_group_ids']}`; selected evidence: `{row['selector']['selected_evidence_ids']}`; selector miss: `{row['selector']['selector_failure_reason']}`"])
        lines.append("")
    return "\n".join(lines) + "\n"


def run_stage3r_track_a_auto_refresh(*, repository_root: Path, snapshot_db: Path, snapshot_artifacts: Path, artifact_manifest: Path, output_root: Path | None = None) -> dict[str, Any]:
    output_root = output_root or repository_root / OUTPUT_RELATIVE
    if (output_root / "stage3r_track_a_auto_refresh_manifest.json").exists():
        raise TrackAAutoRefreshBlocked("output_already_exists", "Refresh output already exists; refusing to overwrite frozen evidence", {"output_root": str(output_root)})
    preflight = _preflight(repository_root, snapshot_db, snapshot_artifacts, artifact_manifest)
    scoring = {row["case_id"]: row for row in load_jsonl(repository_root / SCORING_RELATIVE)}
    runtime = {row["case_id"]: row for row in load_jsonl(repository_root / RUNTIME_RELATIVE)}
    cases = [row for row in scoring.values() if row["final_status"] in {"sufficient", "partial"}]
    cases.sort(key=lambda row: row["case_id"])
    if len(cases) != 20 or any(case["case_id"] not in runtime for case in cases):
        raise TrackAAutoRefreshBlocked("evidence_bearing_input_invalid", "Expected exactly 20 Evidence-bearing cases", {"cases": len(cases)})
    bridge = {(row["case_id"], row["gold_segment_id"]): row["physical_segment_id"] for row in load_jsonl(repository_root / SEGMENT_BRIDGE_RELATIVE)}
    if any((case["case_id"], segment) not in bridge for case in cases for group in case["evidence_groups"] for span in group["required_spans"] for segment in span["segment_ids"]):
        raise TrackAAutoRefreshBlocked("gold_identity_unresolved", "S1 segment bridge cannot resolve all frozen Gold segments")
    identities = {row["case_id"]: row for row in load_jsonl(repository_root / CANONICAL_IDENTITY_RELATIVE)}
    if any(not identities.get(case["case_id"], {}).get("identity_resolved") for case in cases):
        raise TrackAAutoRefreshBlocked("canonical_video_identity_unresolved", "Canonical Video Identity is incomplete")
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "input_freeze/evidence_bearing_case_ids.json", {"case_ids": [case["case_id"] for case in cases], "count": 20, "scoring_projection": str(SCORING_RELATIVE), "runtime_projection": str(RUNTIME_RELATIVE)})
    write_json(output_root / "runtime_preflight/preflight.json", preflight)
    write_jsonl(output_root / "runtime_preflight/runtime_file_hashes.jsonl", runtime_file_hashes(repository_root))
    guard = HeldoutAccessGuard(repository_root)
    builder = final_builder_config()
    selector = SelectorConfig()
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="shiliu-stage3r-auto-refresh-") as temp:
        work_db = Path(temp) / "snapshot-work-copy.db"
        shutil.copy2(snapshot_db, work_db)
        service = build_search_service(
            work_db=work_db,
            snapshot_artifacts=snapshot_artifacts,
            artifact_manifest=artifact_manifest,
            provider=QwenEmbeddingProvider(),
        )
        resolver = FrozenRawSourceResolver(artifact_manifest=artifact_manifest, snapshot_db=snapshot_db, guard=guard)
        for gold in cases:
            case_id = gold["case_id"]
            query = str(runtime[case_id]["original_query"])
            request_payload, request = build_omitted_mode_request(query)
            plan = SearchPlanner().plan(SearchRequest(query=query, mode=request.mode, raw_top_k=50))
            if plan.planned_mode not in {"lexical", "hybrid", "dense"}:
                raise TrackAAutoRefreshBlocked("router_runtime_failure", "Router returned unsupported effective mode", {"case_id": case_id, "plan": plan.as_dict()})
            result = service.search_library(request)
            search_payload = _search_payload(result)
            router_consistent = plan.planned_mode == result.executed_mode
            if not router_consistent:
                raise TrackAAutoRefreshBlocked("router_effective_mode_mismatch", "Router decision differs from effective mode", {"case_id": case_id, "router": plan.planned_mode, "effective": result.executed_mode})
            target_bvid = str(gold["evidence_spans"][0]["video_id"])
            video_candidates = search_payload["video_candidates"]
            target_ranks = [int(value["product_rank"]) for value in video_candidates if value.get("source_id") == target_bvid]
            raw_target = [value for value in search_payload["raw_unit_candidates"] if int(value.get("video_id", -1)) == int(identities[case_id]["runtime_canonical_video_identity"]["product_video_id"])]
            target_hit = bool(target_ranks or raw_target)
            target_rank = min(target_ranks) if target_ranks else None
            target_video_level = any(value.get("source_id") == target_bvid and value.get("video_level_hit_present") for value in video_candidates)
            target_chunk = any(value.get("unit_type") == "transcript_chunk" for value in raw_target)
            target_type = "both" if target_video_level and target_chunk else ("video_level" if target_video_level else ("transcript_chunk" if target_chunk else "none"))
            builder_input = {"query": query, "search_candidate_set": {"raw_unit_candidates": search_payload["raw_unit_candidates"], "video_candidates": video_candidates}}
            candidate_set = resolve_from_search_candidates(query, builder_input["search_candidate_set"], resolver, builder, query_id=case_id, search_candidate_set_id=_sha(search_payload), execution_manifest_identity=SNAPSHOT_SHA256)
            bundle = select_deterministic_bundle(query, candidate_set, selector)
            if bundle is not None:
                validate_bundle(bundle, candidate_set)
            physical_groups = _physical_groups(case_id, gold["evidence_groups"], bridge)
            candidates = [candidate.as_dict() for candidate in candidate_set.candidates]
            selected = [candidate.as_dict() for candidate in candidate_set.candidates if bundle and candidate.candidate_id in bundle.candidate_ids]
            complete = _complete_groups(physical_groups, candidates)
            selected_complete = _complete_groups(physical_groups, selected)
            classification = classify_failure(target_hit=target_hit, complete_group=bool(complete), bundle_hit=bool(selected_complete))
            case = {
                "case_id": case_id, "original_query": query,
                "request": {"mode_field_present": False, "requested_mode": None, "default_applied": True, "configured_default_mode": "auto", "product_default_wiring_version": PRODUCT_DEFAULT_WIRING_VERSION},
                "routing": {"router_invoked": True, "router_version": preflight["runtime_identity"]["auto_router_version"], "router_decision": plan.planned_mode, "router_reason_codes": [plan.routing_reason], "effective_mode": result.executed_mode, "embedding_invoked": result.executed_mode in {"hybrid", "dense"}, "router_mode_consistent": True},
                "retrieval": {"target_video_hit": target_hit, "target_video_rank": target_rank, "target_video_hit_type": target_type, "result_count": len(search_payload["raw_unit_candidates"]), "candidate_video_count": len(video_candidates), "candidate_chunk_count": sum(value.get("unit_type") == "transcript_chunk" for value in search_payload["raw_unit_candidates"]), "empty_result": not search_payload["raw_unit_candidates"]},
                "builder": {"target_video_retrieved": target_hit, "builder_called": True, "candidate_count": len(candidates), "gold_segments_present_count": len(set().union(*(set(candidate.get("segment_ids", [])) for candidate in candidates)) & set(bridge[(case_id, segment)] for group in gold["evidence_groups"] for span in group["required_spans"] for segment in span["segment_ids"])), "gold_segments_total_count": sum(len(span["segment_ids"]) for group in gold["evidence_groups"] for span in group["required_spans"]), "complete_gold_group_covered": bool(complete), "covered_gold_group_ids": complete, "partially_covered_gold_group_ids": [], "candidate_builder_failure_reason": None if (not target_hit or complete) else "target_video_retrieved_without_complete_gold_group"},
                "selector": {"complete_gold_group_available_in_candidate_set": bool(complete), "selector_called": True, "selected_evidence_ids": list(bundle.candidate_ids) if bundle else [], "selected_segment_identities": sorted(set().union(*(set(candidate.get("segment_ids", [])) for candidate in selected))) if selected else [], "bundle_hit": bool(selected_complete), "hit_gold_group_ids": selected_complete, "selector_failure_reason": None if (not complete or selected_complete) else "complete_gold_group_available_but_not_selected"},
                "classification": classification,
            }
            if not target_hit:
                case["builder"]["candidate_builder_failure_reason"] = "builder_not_reachable_due_to_retrieval_miss"
            if not complete:
                case["selector"]["selector_failure_reason"] = "selector_not_reachable_due_to_builder_miss"
            case_dir = output_root / "execution/cases" / case_id
            write_json(case_dir / "product_request.json", request_payload)
            write_json(case_dir / "routing_trace.json", case["routing"])
            write_json(case_dir / "search_candidate_set.json", search_payload)
            write_json(case_dir / "candidate_builder_input.json", builder_input)
            write_json(case_dir / "candidate_set.json", candidate_set.as_dict())
            write_json(case_dir / "selector_input.json", {"query": query, "candidate_set": candidate_set.as_dict()})
            write_json(case_dir / "evidence_bundle.json", bundle.as_dict() if bundle else None)
            write_json(case_dir / "scoring.json", case)
            _case_hash_manifest(case_dir)
            rows.append(case)
    attribution = Counter(row["classification"] for row in rows)
    router = Counter(row["routing"]["effective_mode"] for row in rows)
    ranks = Counter("miss" if row["retrieval"]["target_video_rank"] is None else ("rank_1" if row["retrieval"]["target_video_rank"] == 1 else "rank_1_to_3" if row["retrieval"]["target_video_rank"] <= 3 else "rank_1_to_5" if row["retrieval"]["target_video_rank"] <= 5 else "rank_1_to_10") for row in rows)
    hit = sum(row["retrieval"]["target_video_hit"] for row in rows)
    coverage = sum(row["builder"]["complete_gold_group_covered"] for row in rows)
    bundle_hits = sum(row["selector"]["bundle_hit"] for row in rows)
    metric = {"evidence_bearing_cases": 20, "target_video_recall": {"numerator": hit, "denominator": 20, "rate": hit / 20}, "target_video_rank": {key: ranks.get(key, 0) for key in ("rank_1", "rank_1_to_3", "rank_1_to_5", "rank_1_to_10", "miss")}, "router_distribution": {key: router.get(key, 0) for key in ("lexical", "hybrid", "dense", "other")}, "router_miss_count": 0, "router_miss_case_ids": [], "empty_result_count": sum(row["retrieval"]["empty_result"] for row in rows), "complete_gold_group_candidate_coverage": {"numerator": coverage, "denominator": 20, "rate": coverage / 20}, "conditional_builder_coverage_given_target_video_retrieved": {"numerator": coverage, "denominator": hit, "rate": coverage / hit if hit else None}, "bundle_hit": {"numerator": bundle_hits, "denominator": 20, "rate": bundle_hits / 20}, "conditional_bundle_hit_given_complete_candidate_group": {"numerator": bundle_hits, "denominator": coverage, "rate": bundle_hits / coverage if coverage else None}, "failure_attribution": {key: attribution.get(key, 0) for key in ("end_to_end_bundle_hit", "retrieval_failure", "candidate_builder_failure", "deterministic_selector_failure", "blocked_identity_or_runtime_failure")}}
    usage = {"product_search_calls": 20, "router_calls": 20, "lexical_effective_calls": router.get("lexical", 0), "hybrid_effective_calls": router.get("hybrid", 0), "dense_effective_calls": router.get("dense", 0), "candidate_builder_calls": 20, "deterministic_selector_calls": 20, "structured_llm_selector_calls": 0, "sufficiency_judge_calls": 0, "final_answer_calls": 0, "external_llm_calls": 0, "external_network_calls": 0, "heldout_accessed": False}
    summary = {"runner_version": RUNNER_VERSION, "status": "complete", "metrics": metric, "runtime_usage": usage, "runtime_identity": preflight["runtime_identity"], "historical_explicit_lexical_track_a": {"target_video_recall": "0/20", "complete_gold_group_candidate_coverage": "0/20", "bundle_hit": "0/20"}, "historical_oracle_video_track_b": {"complete_gold_group_candidate_coverage": "11/20", "bundle_hit": "2/20", "conditional_bundle_hit": "2/11"}}
    write_jsonl(output_root / "scoring/case_results.jsonl", rows)
    write_json(output_root / "analysis/metrics.json", metric)
    write_json(output_root / "comparison/historical_comparison.json", summary["historical_explicit_lexical_track_a"] | {"corrected_product_default_auto_track_a": metric, "oracle_track_b_diagnostic_only": summary["historical_oracle_video_track_b"]})
    write_json(output_root / "isolation/heldout_access.audit.json", guard.audit_record(source_files_scanned=[str(SCORING_RELATIVE), str(RUNTIME_RELATIVE), str(SEGMENT_BRIDGE_RELATIVE)], test_files_scanned=[], violations=[]))
    write_json(output_root / "stage3r_track_a_auto_refresh_runtime_usage.json", usage)
    write_json(output_root / "stage3r_track_a_auto_refresh_execution.audit.json", {"status": "complete", "historical_assets_modified": False, "router_modified": False, "retrieval_algorithms_modified": False, "index_rebuilt": False, "product_query_set_started": False, "f1a_started": False, "f1b_started": False, "heldout_accessed": False, "failure_counts_sum_to_twenty": sum(metric["failure_attribution"].values()) == 20})
    write_json(output_root / "stage3r_track_a_auto_refresh_manifest.json", summary | {"input_freeze": {"case_count": 20, "uses_original_queries": True, "mode_omitted": True}, "runtime_identity": preflight["runtime_identity"]})
    (output_root / "V3_5_STAGE3R_TRACK_A_AUTO_PRODUCT_REFRESH_REPORT.md").write_text(_render_report(summary), encoding="utf-8")
    (output_root / "STAGE3R_TRACK_A_AUTO_PRODUCT_REFRESH_HUMAN_REVIEW_PACKET.md").write_text(_render_review(rows, metric), encoding="utf-8")
    files = [path for path in output_root.rglob("*") if path.is_file() and path.name != "stage3r_track_a_auto_refresh_file_hash_manifest.jsonl"]
    write_jsonl(output_root / "stage3r_track_a_auto_refresh_file_hash_manifest.jsonl", [{"path": str(path.relative_to(output_root)), "sha256": file_sha256(path), "bytes": path.stat().st_size} for path in sorted(files)])
    return summary
