from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

from shiliu.evidence import (
    SourceArtifactReference,
    bind_snapshot_manifest_version,
    load_source_artifact,
)
from shiliu.eval_v3_5.models import (
    MASTER_CASE_SCHEMA_VERSION,
    REVIEW_DECISION_SCHEMA_VERSION,
    REVIEW_PACKET_VERSION,
    MasterCaseCandidate,
    NavigationAid,
    ReviewDecisionTemplate,
)
from shiliu.eval_v3_5.sampling import PRIMARY_SELECTIONS, RESERVE_SELECTIONS, rationale


DEFAULT_SNAPSHOT_DB = Path("local-data/eval/shiliu_eval.db")
DEFAULT_ARTIFACT_MANIFEST = Path("research/v3_eval/artifact_manifest.jsonl")
DEFAULT_QUERIES = Path("research/v3_eval/eval_queries.locked.jsonl")
DEFAULT_GOLD = Path("research/v3_eval/eval_gold.locked.jsonl")
DEFAULT_POOL = Path("research/v3_eval/eval_pool_candidates.jsonl")
DEFAULT_OUTPUT = Path("research/v3_5")
SNAPSHOT_ID = "20260720T094346Z_c7663365"
NAVIGATION_LABEL = "Navigation Aid Only — Not Annotation Boundary"


@dataclass(frozen=True)
class PacketBuildSummary:
    primary_count: int
    reserve_count: int
    packet_count: int
    query_video_count: int
    query_corpus_count: int
    total_transcript_segments: int
    largest_packet: str
    largest_packet_bytes: int
    source_distribution: dict[str, int]
    language_distribution: dict[str, int]
    query_type_distribution: dict[str, int]
    sampling_distribution: dict[str, int]


def build_review_assets(
    *,
    output_root: str | Path = DEFAULT_OUTPUT,
    snapshot_db: str | Path = DEFAULT_SNAPSHOT_DB,
    artifact_manifest: str | Path = DEFAULT_ARTIFACT_MANIFEST,
    queries_path: str | Path = DEFAULT_QUERIES,
    gold_path: str | Path = DEFAULT_GOLD,
    pool_path: str | Path = DEFAULT_POOL,
) -> PacketBuildSummary:
    root = Path(output_root)
    packets_dir = root / "review_packets"
    packets_dir.mkdir(parents=True, exist_ok=True)
    queries = _records_by("query_id", queries_path)
    gold = _records_by("query_id", gold_path)
    pool = _pool_records(pool_path)
    connection = sqlite3.connect(
        f"file:{Path(snapshot_db).resolve()}?mode=ro&immutable=1", uri=True
    )
    connection.row_factory = sqlite3.Row
    try:
        primary = tuple(
            _build_case(item, queries, gold, pool, connection, artifact_manifest)
            for item in PRIMARY_SELECTIONS
        )
        reserves = tuple(
            _build_case(item, queries, gold, pool, connection, artifact_manifest)
            for item in RESERVE_SELECTIONS
        )
        all_cases = primary + reserves
        packet_manifest = []
        total_segments = 0
        for case in all_cases:
            packet_text, segment_count = _render_packet(case, connection)
            packet_path = packets_dir / f"{case.case_id}.md"
            packet_path.write_text(packet_text, encoding="utf-8")
            total_segments += segment_count
            packet_manifest.append(
                {
                    "case_id": case.case_id,
                    "packet_version": REVIEW_PACKET_VERSION,
                    "packet_path": str(packet_path),
                    "sha256": sha256(packet_text.encode("utf-8")).hexdigest(),
                    "case_scope": case.case_scope,
                    "source_version": case.source_version,
                    "segment_count": segment_count,
                    "full_transcript_complete": case.source_state == "readable_raw",
                }
            )
    finally:
        connection.close()

    _write_jsonl(root / "master_case_candidates.jsonl", primary)
    _write_jsonl(root / "master_case_reserves.jsonl", reserves)
    decisions = [ReviewDecisionTemplate(case_id=case.case_id) for case in all_cases]
    _write_jsonl(root / "review_decisions.template.jsonl", decisions)
    (root / "review_packet_manifest.json").write_text(
        json.dumps(
            {
                "snapshot_id": SNAPSHOT_ID,
                "packet_version": REVIEW_PACKET_VERSION,
                "candidate_manifest_is_gold": False,
                "packets": packet_manifest,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    leakage = _leakage_report(all_cases)
    (root / "preliminary_leakage_report.json").write_text(
        json.dumps(leakage, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(_readme(), encoding="utf-8")
    return validate_review_assets(
        output_root=root,
        snapshot_db=snapshot_db,
        artifact_manifest=artifact_manifest,
    )


def validate_review_assets(
    *,
    output_root: str | Path = DEFAULT_OUTPUT,
    snapshot_db: str | Path = DEFAULT_SNAPSHOT_DB,
    artifact_manifest: str | Path = DEFAULT_ARTIFACT_MANIFEST,
) -> PacketBuildSummary:
    root = Path(output_root)
    primary = _load_cases(root / "master_case_candidates.jsonl")
    reserves = _load_cases(root / "master_case_reserves.jsonl")
    if not 18 <= len(primary) <= 24:
        raise ValueError("primary case count must be 18–24")
    if not 4 <= len(reserves) <= 8:
        raise ValueError("reserve case count must be 4–8")
    all_cases = primary + reserves
    manifest = json.loads((root / "review_packet_manifest.json").read_text())
    entries = {item["case_id"]: item for item in manifest["packets"]}
    if set(entries) != {case.case_id for case in all_cases}:
        raise ValueError("every candidate must have exactly one packet")

    decisions = [
        ReviewDecisionTemplate.model_validate_json(line)
        for line in (root / "review_decisions.template.jsonl").read_text().splitlines()
    ]
    original_case_ids = {case.case_id for case in primary} | {
        f"RESERVE_{index:03d}" for index in range(1, 7)
    }
    if {item.case_id for item in decisions} != original_case_ids:
        raise ValueError("original decision template must retain the 20 primary and 6 Stage 2A reserves")

    connection = sqlite3.connect(
        f"file:{Path(snapshot_db).resolve()}?mode=ro&immutable=1", uri=True
    )
    connection.row_factory = sqlite3.Row
    total_segments = 0
    largest = ("", 0)
    try:
        for case in all_cases:
            packet_path = root / "review_packets" / f"{case.case_id}.md"
            text = packet_path.read_text(encoding="utf-8")
            size = packet_path.stat().st_size
            largest = max(largest, (case.case_id, size), key=lambda value: value[1])
            entry = entries[case.case_id]
            if sha256(text.encode("utf-8")).hexdigest() != entry["sha256"]:
                raise ValueError(f"packet hash mismatch: {case.case_id}")
            if NAVIGATION_LABEL not in text or "Decision Status:\nunreviewed" not in text:
                raise ValueError(f"packet navigation/decision marker missing: {case.case_id}")
            if "Sufficiency Label:\nunreviewed" not in text:
                raise ValueError(f"packet has no blank Sufficiency field: {case.case_id}")
            if case.source_state == "readable_raw":
                row = connection.execute(
                    "SELECT * FROM videos WHERE id=?", (case.target_video_id,)
                ).fetchone()
                reference = _reference(row)
                binding = bind_snapshot_manifest_version(
                    reference,
                    video_id=int(case.target_video_id),
                    manifest_path=artifact_manifest,
                )
                artifact = load_source_artifact(
                    reference, expected_source_version=binding.source_version
                )
                if artifact.source_version != case.source_version:
                    raise ValueError(f"source version mismatch: {case.case_id}")
                if f"<!-- SEGMENT_COUNT={len(artifact.segments)} -->" not in text:
                    raise ValueError(f"transcript count marker mismatch: {case.case_id}")
                if any(segment.segment_id not in text for segment in artifact.segments):
                    raise ValueError(f"segment omitted from packet: {case.case_id}")
                expected_runs = {segment.timeline_run_id for segment in artifact.segments}
                if any(f"Timeline Run `{run_id}`" not in text for run_id in expected_runs):
                    raise ValueError(f"timeline run omitted: {case.case_id}")
                total_segments += len(artifact.segments)
            elif "## Full Raw Transcript" in text:
                raise ValueError(f"unavailable/corpus packet must not fake transcript: {case.case_id}")
    finally:
        connection.close()

    return PacketBuildSummary(
        primary_count=len(primary), reserve_count=len(reserves),
        packet_count=len(all_cases),
        query_video_count=sum(case.case_scope == "query_video" for case in all_cases),
        query_corpus_count=sum(case.case_scope == "query_corpus" for case in all_cases),
        total_transcript_segments=total_segments,
        largest_packet=largest[0], largest_packet_bytes=largest[1],
        source_distribution=dict(Counter(case.source_type or case.source_state for case in primary)),
        language_distribution=dict(Counter(case.source_language or "none" for case in primary)),
        query_type_distribution=dict(Counter(case.query_type for case in primary)),
        sampling_distribution=dict(Counter(case.sampling_stratum for case in primary)),
    )


def _build_case(selection, queries, gold, pool, connection, artifact_manifest) -> MasterCaseCandidate:
    case_id, query_id, video_id, stratum, origin = selection
    query = queries[query_id]
    query_text = str(query["query"])
    metrics = (
        "Sufficiency", "ReasonCodes", "NegativeControl"
    ) if video_id is None else (
        "GoldGroupCoverage@K", "EvidenceSetHit@1", "SegmentF1",
        "StartTimeError", "DurationRatio", "Sufficiency", "ReasonCodes",
    )
    if video_id is None:
        aids = (
            NavigationAid(
                aid_type="v3_negative_control",
                details={
                    "query_id": query_id,
                    "judged_not_relevant_count": len(gold[query_id]["judged_not_relevant_ids"]),
                    "top_pool_video_ids": [item["video_id"] for item in pool.get(query_id, [])[:10]],
                },
            ),
        )
        return MasterCaseCandidate(
            case_id=case_id, case_scope="query_corpus", query=query_text,
            query_language=_query_language(query_text),
            query_type=query["expected_query_type"], source_state="query_corpus",
            sampling_stratum=stratum, case_origin=origin,
            candidate_rationale=rationale(stratum), navigation_aids=aids,
            preliminary_leakage_keys={
                "query_family_key": _query_family(query_id),
                "video_key": "no_target",
                "evidence_seed_key": f"negative_control:{query_id}",
                "source_artifact_key": "no_target",
            },
            applicable_metrics=metrics,
        )

    row = connection.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    if row is None:
        raise ValueError(f"selected video does not exist: {video_id}")
    intervals = [
        item for item in gold[query_id]["intervals"] if int(item["video_id"]) == video_id
    ]
    aids = [
        NavigationAid(
            aid_type="existing_approved_interval",
            details={
                "start": item["start"], "end": item["end"],
                "raw_segment_start_index": item["raw_segment_start_index"],
                "raw_segment_end_index": item["raw_segment_end_index"],
                "human_note": item.get("human_note", ""),
            },
        )
        for item in intervals
    ]
    pooled = next((item for item in pool.get(query_id, []) if int(item["video_id"]) == video_id), None)
    if pooled:
        aids.append(
            NavigationAid(
                aid_type="v3_search_diagnostic",
                details={
                    "best_rank": pooled.get("best_rank"),
                    "appeared_in_modes": pooled.get("appeared_in_modes", []),
                    "window_ranges": [
                        [item.get("start"), item.get("end")]
                        for item in pooled.get("top_evidence", [])
                    ],
                },
            )
        )
    if not aids:
        aids.append(NavigationAid(aid_type="case_origin", details={"origin": origin}))

    raw_path = str(row["raw_subtitle_path"] or "")
    if raw_path:
        reference = _reference(row)
        binding = bind_snapshot_manifest_version(
            reference, video_id=video_id, manifest_path=artifact_manifest
        )
        artifact = load_source_artifact(reference, expected_source_version=binding.source_version)
        source_state = "readable_raw"
        artifact_id = artifact.source_artifact_id
        version = artifact.source_version
        source_type = str(row["subtitle_source"] or "unknown")
        source_language = str(row["subtitle_language"] or "unknown")
        timeline = artifact.validation_status
    else:
        source_state = "title_only" if "title_only" in origin else "subtitle_missing"
        artifact_id = version = source_type = source_language = timeline = None

    seed_key = (
        f"{row['source_id']}:{intervals[0]['raw_segment_start_index']}-{intervals[0]['raw_segment_end_index']}"
        if intervals else f"no_interval:{query_id}:{video_id}"
    )
    return MasterCaseCandidate(
        case_id=case_id, case_scope="query_video", query=query_text,
        query_language=_query_language(query_text), query_type=query["expected_query_type"],
        target_video_id=video_id, target_bvid=str(row["source_id"]),
        source_state=source_state, source_artifact_id=artifact_id,
        source_version=version, source_type=source_type,
        source_language=source_language, timeline_status=timeline,
        sampling_stratum=stratum, case_origin=origin,
        candidate_rationale=rationale(stratum), navigation_aids=tuple(aids),
        split_constraint="development_only" if stratum == "multi_timeline_robustness" else "unassigned",
        preliminary_leakage_keys={
            "query_family_key": _query_family(query_id),
            "video_key": f"video:{video_id}",
            "evidence_seed_key": seed_key,
            "source_artifact_key": artifact_id or f"unavailable:{row['source_id']}",
        },
        applicable_metrics=metrics,
    )


def _render_packet(case: MasterCaseCandidate, connection) -> tuple[str, int]:
    title = f"# {case.case_id} — V3.5 Master Case Human Review Packet"
    lines = [
        title, "", f"Packet Version: `{REVIEW_PACKET_VERSION}`", "",
        "## Review Instructions", "",
        "请基于完整 Raw Transcript 做判断。", "",
        "V3 Chunk、Existing Interval、Search Hit、Keyword Location 仅用于导航，不限制可标注范围。",
        "", "不要因为标题、AI Summary 或 Search Rank 判断正文是否支持 Query。", "",
        f"**{NAVIGATION_LABEL}**", "",
        "## Case Metadata", "",
        f"- Case ID: `{case.case_id}`", f"- Scope: `{case.case_scope}`",
        f"- Query: {case.query}", f"- Query language/type: `{case.query_language}` / `{case.query_type}`",
        f"- Target video: `{case.target_video_id or 'none'}` / `{case.target_bvid or 'none'}`",
        f"- Source state/type/language: `{case.source_state}` / `{case.source_type or 'none'}` / `{case.source_language or 'none'}`",
        f"- Source artifact ID: `{case.source_artifact_id or 'none'}`",
        f"- Source version: `{case.source_version or 'none'}`",
        f"- Timeline status: `{case.timeline_status or 'none'}`",
        f"- Sampling stratum: `{case.sampling_stratum}` (sampling hypothesis only; not Gold)",
        f"- Case origin: `{case.case_origin}`", "",
        "## Navigation Aids", "", f"**{NAVIGATION_LABEL}**", "",
        "```json", json.dumps([item.model_dump(mode="json") for item in case.navigation_aids], ensure_ascii=False, indent=2), "```", "",
    ]
    segment_count = 0
    if case.case_scope == "query_corpus":
        lines.extend([
            "## Corpus-level Human Review Question", "",
            "当前冻结资料库是否存在可批准 Target Video？请确认 no approved target，或指出一个应转换为 query_video 的真实 Target。",
            "", "本 Packet 不伪造 Target Video、Transcript 或 no-answer Label。", "",
        ])
    elif case.source_state != "readable_raw":
        row = connection.execute("SELECT title,status FROM videos WHERE id=?", (case.target_video_id,)).fetchone()
        lines.extend([
            "## Source Availability", "",
            f"- Title: {row['title']}", f"- Snapshot status: `{row['status']}`",
            "- No authoritative Raw Transcript is available; no transcript has been fabricated.", "",
        ])
    else:
        row = connection.execute("SELECT * FROM videos WHERE id=?", (case.target_video_id,)).fetchone()
        artifact = load_source_artifact(_reference(row), expected_source_version=case.source_version)
        segment_count = len(artifact.segments)
        ids_digest = sha256("\n".join(item.segment_id for item in artifact.segments).encode()).hexdigest()
        lines.extend([
            "## Full Raw Transcript", "",
            "The following JSONL contains every Raw Segment in original Artifact order. No window or navigation aid limits annotation.", "",
            f"<!-- SOURCE_VERSION={artifact.source_version} -->",
            f"<!-- SEGMENT_COUNT={segment_count} -->",
            f"<!-- SEGMENT_ID_LIST_SHA256={ids_digest} -->", "",
        ])
        for run in artifact.timeline_runs:
            lines.extend([
                f"### Timeline Run `{run.timeline_run_id}`", "",
                f"Run ordinal `{run.run_ordinal}`; original ordinals `{run.first_original_ordinal}–{run.last_original_ordinal}`; segments `{run.segment_count}`.",
                "", "```jsonl",
            ])
            for segment in artifact.segments:
                if segment.timeline_run_id != run.timeline_run_id:
                    continue
                lines.append(json.dumps({
                    "original_ordinal": segment.original_ordinal,
                    "segment_id": segment.segment_id,
                    "start_time": segment.start_time,
                    "end_time": segment.end_time,
                    "source_text": segment.source_text,
                    "timeline_run_id": segment.timeline_run_id,
                    "evidence_eligible": segment.evidence_eligible,
                }, ensure_ascii=False, separators=(",", ":")))
            lines.extend(["```", ""])

    lines.extend([
        "## Human Decision Form", "",
        "Decision Status:", "unreviewed", "",
        "Required Aspects:", "- ", "",
        "Gold Evidence Groups:", "- ", "",
        "Sufficiency Label:", "unreviewed", "",
        "Supported Aspects:", "- ", "",
        "Missing Aspects:", "- ", "",
        "Conflict Notes:", "", "",
        "Primary Reason Codes:", "- ", "",
        "Support Notes:", "", "",
        "Review Confidence:", "high / medium / low", "",
        "Needs Second Review:", "yes / no", "",
        "Reviewer Flags:", "- ", "",
    ])
    return "\n".join(lines), segment_count


def _leakage_report(cases):
    groups = []
    for key in ("query_family_key", "video_key", "evidence_seed_key", "source_artifact_key"):
        values = defaultdict(list)
        for case in cases:
            values[case.preliminary_leakage_keys[key]].append(case.case_id)
        for value, case_ids in sorted(values.items()):
            if len(case_ids) > 1 and value not in {"no_target"}:
                groups.append({"key_type": key, "key": value, "case_ids": case_ids})
    return {
        "status": "preliminary_only_no_split_assigned",
        "groups": groups,
        "required_relationship_check": {
            "cases": ["CASE_001", "RESERVE_001"],
            "relationship": "Q01–V78 and Q15–V78 share the exact approved interval seed",
            "future_leakage_group_candidate": True,
        },
    }


def _records_by(key: str, path: str | Path):
    return {record[key]: record for record in _jsonl(path)}


def _pool_records(path: str | Path):
    result = defaultdict(list)
    for record in _jsonl(path):
        result[record["query_id"]].append(record)
    for values in result.values():
        values.sort(key=lambda item: (item.get("best_rank") or 9999, item["video_id"]))
    return result


def _jsonl(path: str | Path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, values) -> None:
    path.write_text(
        "".join(json.dumps(value.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n" for value in values),
        encoding="utf-8",
    )


def _load_cases(path: Path):
    return tuple(MasterCaseCandidate.model_validate_json(line) for line in path.read_text().splitlines())


def _reference(row) -> SourceArtifactReference:
    return SourceArtifactReference(
        platform=str(row["platform"]), source_id=str(row["source_id"]),
        part=int(row["part"]), source_type=str(row["subtitle_source"] or "unknown"),
        source_language=str(row["subtitle_language"] or "unknown"),
        artifact_path=str(row["raw_subtitle_path"] or ""),
    )


def _query_language(value: str) -> str:
    has_ascii = bool(re.search(r"[A-Za-z]", value))
    has_cjk = bool(re.search(r"[\u3400-\u9fff]", value))
    if has_ascii and has_cjk:
        return "mixed"
    return "en" if has_ascii else "zh"


def _query_family(query_id: str) -> str:
    families = {
        "Q01": "mcp_cli_advantages", "Q15": "mcp_cli_advantages",
        "Q04": "lora_anime_finetune", "Q17": "lora_anime_finetune",
        "Q02": "rag", "Q08": "rag_industrial",
        "Q03": "memoryos", "Q07": "claude_memory", "Q11": "memory_safety",
        "Q14": "quantum_negative_control", "Q18": "kubernetes_negative_control",
    }
    return families.get(query_id, query_id.lower())


def _readme() -> str:
    return f"""# V3.5 Stage 2A Human Review Assets

These files are candidate review materials, not Gold and not a Development/Held-out split.

- `master_case_candidates.jsonl`: 20 primary sampling candidates.
- `master_case_reserves.jsonl`: 6 reserve candidates.
- `review_packets/`: one human packet per candidate, with full Raw Transcript whenever authority exists.
- `review_decisions.template.jsonl`: blank, unreviewed decision records.
- `review_packet_manifest.json`: packet hashes and transcript counts.
- `preliminary_leakage_report.json`: preliminary duplicate/leakage keys only.

Every navigation section is labeled **{NAVIGATION_LABEL}**. Human reviewers must inspect the full transcript and must not treat V3 intervals, hits, windows, ranks, titles, or summaries as annotation boundaries.
"""


if __name__ == "__main__":
    print(build_review_assets())
