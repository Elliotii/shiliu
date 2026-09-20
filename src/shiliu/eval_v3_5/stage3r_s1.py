from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from shiliu.evidence.contracts import (
    TIMELINE_EPSILON_SECONDS,
    EvidenceContractError,
    ParsedSourceArtifact,
    SourceArtifactReference,
)
from shiliu.evidence.source import load_source_artifact, make_source_artifact_id
from shiliu.evidence.stage3a import interval_union_duration


BRIDGE_VERSION = "v3.5-stage3r-segment-identity-bridge-v1"
RUNNER_VERSION = "v3.5-stage3r-s1-frozen-prediction-rescore-v1"
CORPUS_SHA256 = "a337b52ef83c69a844425f673990b2fbe0f42307e3934b7f746e2c6a0af9f148"
TRACK_A_SHA256 = "6696f3a83449bdbb5df21f7b841bace705633b718a367dc549990238e9b3b4d4"
TRACK_B_SHA256 = "2f188746ccd432e4fc634592e36cd2f0e04e4c27a2bfb8ce9210483d9b9f83fe"
LEGACY_GOLD_SEGMENT_ID = re.compile(r"^(?P<bvid>BV[0-9A-Za-z]+)_seg_(?P<ordinal>[0-9]{6})$")
ALLOWED_MAPPING_STATUSES = frozenset({
    "exact_identity_match", "gold_segment_not_present_in_runtime_universe",
    "runtime_segment_identity_missing", "source_artifact_mismatch",
    "source_version_mismatch", "timeline_run_mismatch", "ordinal_mismatch",
    "time_mismatch", "text_digest_mismatch", "ambiguous_mapping",
    "duplicate_canonical_key",
})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        "\n".join(canonical_json(record) for record in records) + "\n"
    ).encode("utf-8")
    path.write_bytes(payload)
    return sha256(payload).hexdigest()


@dataclass(frozen=True, order=True)
class CanonicalSegmentKey:
    source_artifact_id: str
    source_version: str
    timeline_run_id: str
    segment_ordinal: int

    def __post_init__(self) -> None:
        for field in ("source_artifact_id", "source_version", "timeline_run_id"):
            if not getattr(self, field):
                raise ValueError(f"Canonical Segment Key requires {field}")
        if not isinstance(self.segment_ordinal, int) or self.segment_ordinal < 0:
            raise ValueError("Canonical Segment Key requires a non-negative segment_ordinal")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sha256(self) -> str:
        return sha256(canonical_json(self.as_dict()).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SegmentIdentity:
    canonical_key: CanonicalSegmentKey
    physical_segment_id: str
    start_time: float
    end_time: float
    text_digest: str
    source_text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical_key": self.canonical_key.as_dict(),
            "canonical_segment_key_sha256": self.canonical_key.sha256,
            "physical_segment_id": self.physical_segment_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "text_digest": self.text_digest,
        }


def text_digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def identity_from_raw_segment(segment: Any) -> SegmentIdentity:
    return SegmentIdentity(
        canonical_key=CanonicalSegmentKey(
            source_artifact_id=segment.source_artifact_id,
            source_version=segment.source_version,
            timeline_run_id=segment.timeline_run_id,
            segment_ordinal=int(segment.original_ordinal),
        ),
        physical_segment_id=segment.segment_id,
        start_time=float(segment.start_time),
        end_time=float(segment.end_time),
        text_digest=text_digest(segment.source_text),
        source_text=segment.source_text,
    )


def project_gold_segment_identity(
    *, case_id: str, gold_segment_id: str, source_artifact_id: str,
    source_version: str, timeline_run_id: str, source_bvid: str,
    raw_artifact: ParsedSourceArtifact,
) -> dict[str, Any]:
    match = LEGACY_GOLD_SEGMENT_ID.fullmatch(gold_segment_id)
    if match is None or match.group("bvid") != source_bvid:
        raise EvidenceContractError(
            f"legacy Gold Segment ID is not exactly valid for source: {gold_segment_id}",
            code="segment_identity_invalid",
        )
    one_based = int(match.group("ordinal"))
    if one_based < 1:
        raise EvidenceContractError("legacy Gold ordinal must be one-based", code="segment_identity_invalid")
    ordinal = one_based - 1
    if raw_artifact.source_artifact_id != source_artifact_id:
        raise EvidenceContractError("Gold/Raw source artifact mismatch", code="source_artifact_mismatch")
    if raw_artifact.source_version != source_version:
        raise EvidenceContractError("Gold/Raw source version mismatch", code="source_version_mismatch")
    matches = [
        segment for segment in raw_artifact.segments
        if segment.original_ordinal == ordinal
        and segment.timeline_run_id == timeline_run_id
    ]
    if len(matches) != 1:
        raise EvidenceContractError(
            f"Gold Segment identity resolved {len(matches)} Raw segments",
            code="segment_identity_invalid",
        )
    identity = identity_from_raw_segment(matches[0])
    return {
        "bridge_version": BRIDGE_VERSION,
        "case_id": case_id,
        "gold_segment_id": gold_segment_id,
        "legacy_id_format_version": "v3.5-development-gold-bvid-seg-six-digit-one-based-v1",
        "legacy_ordinal_one_based": one_based,
        "parsed_ordinal_confirmed_against_raw_source": True,
        **identity.as_dict(),
    }


def project_runtime_segment_identity(
    *, candidate: Mapping[str, Any], runtime_segment_id: str,
    segment_ordinal: int, raw_identities: Mapping[str, SegmentIdentity],
) -> dict[str, Any]:
    identity = raw_identities.get(runtime_segment_id)
    if identity is None:
        raise EvidenceContractError("Runtime physical Segment ID is absent from Raw Source", code="segment_not_found")
    expected = CanonicalSegmentKey(
        source_artifact_id=str(candidate["source_artifact_id"]),
        source_version=str(candidate["source_version"]),
        timeline_run_id=str(candidate["timeline_run_id"]),
        segment_ordinal=int(segment_ordinal),
    )
    if identity.canonical_key != expected:
        raise EvidenceContractError("Runtime Candidate structured identity mismatch", code="segment_identity_invalid")
    return {
        "bridge_version": BRIDGE_VERSION,
        "runtime_segment_id": runtime_segment_id,
        "candidate_id": candidate["candidate_id"],
        **identity.as_dict(),
    }


def validate_exact_mapping(
    gold: Mapping[str, Any], runtime: Mapping[str, Any],
    *, epsilon_seconds: float = TIMELINE_EPSILON_SECONDS,
) -> str:
    g = gold["canonical_key"]
    r = runtime["canonical_key"]
    for field, status in (
        ("source_artifact_id", "source_artifact_mismatch"),
        ("source_version", "source_version_mismatch"),
        ("timeline_run_id", "timeline_run_mismatch"),
        ("segment_ordinal", "ordinal_mismatch"),
    ):
        if g[field] != r[field]:
            return status
    if abs(float(gold["start_time"]) - float(runtime["start_time"])) > epsilon_seconds:
        return "time_mismatch"
    if abs(float(gold["end_time"]) - float(runtime["end_time"])) > epsilon_seconds:
        return "time_mismatch"
    if gold["text_digest"] != runtime["text_digest"]:
        return "text_digest_mismatch"
    return "exact_identity_match"


def assert_unique_identity_universe(identities: Sequence[SegmentIdentity]) -> None:
    by_key: dict[CanonicalSegmentKey, set[str]] = defaultdict(set)
    for identity in identities:
        by_key[identity.canonical_key].add(identity.physical_segment_id)
    duplicates = {key: ids for key, ids in by_key.items() if len(ids) > 1}
    if duplicates:
        raise EvidenceContractError(
            f"duplicate Canonical Segment Keys: {duplicates}",
            code="duplicate_canonical_key",
        )


def _source_context(record: Mapping[str, Any]) -> Mapping[str, Any]:
    decision = record["canonical_adjudication"]
    return record.get("source_context") or decision.get("source_identity") or {}


def _query(record: Mapping[str, Any]) -> str:
    if record.get("query_projection"):
        return str(record["query_projection"]["original_query"])
    return str(record["canonical_adjudication"]["source_identity"]["original_query"])


def _load_raw_artifacts(
    gold_records: Sequence[Mapping[str, Any]], artifact_manifest: Path,
) -> tuple[dict[str, ParsedSourceArtifact], dict[str, Mapping[str, Any]]]:
    manifest = {
        str(row["bvid"]): row for row in load_jsonl(artifact_manifest)
        if row.get("artifact_type") == "raw_subtitle"
    }
    artifacts: dict[str, ParsedSourceArtifact] = {}
    sources: dict[str, Mapping[str, Any]] = {}
    for record in gold_records:
        source = _source_context(record)
        if source.get("raw_evidence_authority_state") == "unavailable":
            continue
        bvid = str(source["source_video_id"])
        if bvid in artifacts:
            continue
        row = manifest.get(bvid)
        if row is None or row.get("status") != "ok":
            raise EvidenceContractError(f"Raw manifest is unavailable for {bvid}", code="raw_source_unavailable")
        references = [
            SourceArtifactReference(
                platform="bilibili", source_id=bvid, part=1,
                source_type=lineage, source_language=str(source["source_language"]),
                artifact_path=str(row["snapshot_path"]), source_lineage=lineage,
            )
            for lineage in ("human", "ai", "asr")
        ]
        matching = [
            reference for reference in references
            if make_source_artifact_id(reference) == source["source_artifact_id"]
        ]
        if len(matching) != 1:
            raise EvidenceContractError(
                f"Source lineage cannot be resolved uniquely for {bvid}",
                code="source_artifact_mismatch",
            )
        reference = matching[0]
        artifact = load_source_artifact(reference, expected_source_version=str(source["source_version"]))
        if artifact.source_artifact_id != source["source_artifact_id"]:
            raise EvidenceContractError(f"Artifact identity mismatch for {bvid}", code="source_artifact_mismatch")
        artifacts[bvid] = artifact
        sources[bvid] = source
    return artifacts, sources


def build_identity_bridge(
    *, gold_records: Sequence[Mapping[str, Any]], predictions: Sequence[Mapping[str, Any]],
    artifact_manifest: Path,
) -> dict[str, Any]:
    artifacts, sources = _load_raw_artifacts(gold_records, artifact_manifest)
    raw_identities = {
        identity.physical_segment_id: identity
        for artifact in artifacts.values()
        for identity in map(identity_from_raw_segment, artifact.segments)
    }
    assert_unique_identity_universe(list(raw_identities.values()))
    runtime_rows_by_physical: dict[str, dict[str, Any]] = {}
    runtime_memberships: list[dict[str, Any]] = []
    for prediction in predictions:
        for candidate in prediction["candidate_set"].get("candidates", []):
            ids = list(candidate["segment_ids"])
            ordinals = list(candidate["original_ordinals"])
            if len(ids) != len(ordinals):
                raise EvidenceContractError("Candidate Segment IDs/ordinals length mismatch", code="segment_identity_invalid")
            for physical_id, ordinal in zip(ids, ordinals):
                row = project_runtime_segment_identity(
                    candidate=candidate, runtime_segment_id=str(physical_id),
                    segment_ordinal=int(ordinal), raw_identities=raw_identities,
                )
                runtime_memberships.append({
                    "case_id": prediction["case_id"],
                    "evaluation_track": prediction["evaluation_track"],
                    **row,
                })
                prior = runtime_rows_by_physical.setdefault(str(physical_id), row)
                if prior["canonical_key"] != row["canonical_key"]:
                    raise EvidenceContractError("physical Segment maps to multiple keys", code="duplicate_canonical_key")
    gold_rows: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen_gold: set[tuple[str, str]] = set()
    for record in gold_records:
        decision = record["canonical_adjudication"]
        source = _source_context(record)
        if not decision.get("final_evidence_spans"):
            continue
        bvid = str(source["source_video_id"])
        artifact = artifacts[bvid]
        for span in decision.get("final_evidence_spans", []):
            for gold_id in span.get("segment_ids", []):
                dedupe = (str(record["case_id"]), str(gold_id))
                if dedupe in seen_gold:
                    continue
                seen_gold.add(dedupe)
                try:
                    gold_row = project_gold_segment_identity(
                        case_id=str(record["case_id"]), gold_segment_id=str(gold_id),
                        source_artifact_id=str(span["source_artifact_id"]),
                        source_version=str(span["source_version"]),
                        timeline_run_id=str(span["timeline_run_id"]),
                        source_bvid=bvid, raw_artifact=artifact,
                    )
                    gold_rows.append(gold_row)
                    runtime_identity = raw_identities.get(gold_row["physical_segment_id"])
                    if runtime_identity is None:
                        status = "gold_segment_not_present_in_runtime_universe"
                        runtime_row = None
                    else:
                        runtime_row = runtime_identity.as_dict()
                        status = validate_exact_mapping(gold_row, runtime_row)
                    mapping = {
                        "case_id": record["case_id"],
                        "gold_segment_id": gold_id,
                        "runtime_segment_id": runtime_identity.physical_segment_id if runtime_identity else None,
                        "canonical_key": gold_row["canonical_key"],
                        "gold_start_time": gold_row["start_time"],
                        "runtime_start_time": runtime_row["start_time"] if runtime_row else None,
                        "gold_end_time": gold_row["end_time"],
                        "runtime_end_time": runtime_row["end_time"] if runtime_row else None,
                        "gold_text_digest": gold_row["text_digest"],
                        "runtime_text_digest": runtime_row["text_digest"] if runtime_row else None,
                        "mapping_status": status,
                        "mapping_reason": "structured_identity_and_strong_fields_match" if status == "exact_identity_match" else status,
                    }
                    mapping_rows.append(mapping)
                    if status != "exact_identity_match":
                        failures.append(mapping)
                except Exception as exc:
                    failure = {
                        "case_id": record["case_id"], "gold_segment_id": gold_id,
                        "mapping_status": getattr(exc, "code", "runtime_segment_identity_missing"),
                        "mapping_reason": str(exc),
                    }
                    failures.append(failure)
    if failures:
        raise EvidenceContractError(
            f"Gold identity bridge has {len(failures)} failures",
            code="segment_identity_invalid",
        )
    return {
        "gold_projection": gold_rows,
        "runtime_projection": list(runtime_rows_by_physical.values()),
        "runtime_memberships": runtime_memberships,
        "mapping": mapping_rows,
        "failures": failures,
        "ambiguities": [],
        "raw_identities": raw_identities,
        "artifacts": artifacts,
    }


def key_tuple(value: Mapping[str, Any]) -> tuple[str, str, str, int]:
    return (
        str(value["source_artifact_id"]), str(value["source_version"]),
        str(value["timeline_run_id"]), int(value["segment_ordinal"]),
    )


def _candidate_keys(candidate: Mapping[str, Any]) -> set[tuple[str, str, str, int]]:
    return {
        (
            str(candidate["source_artifact_id"]), str(candidate["source_version"]),
            str(candidate["timeline_run_id"]), int(ordinal),
        )
        for ordinal in candidate["original_ordinals"]
    }


def _span_keys(
    case_id: str, span: Mapping[str, Any],
    gold_by_case_id: Mapping[tuple[str, str], Mapping[str, Any]],
) -> set[tuple[str, str, str, int]]:
    return {
        key_tuple(gold_by_case_id[(case_id, str(segment_id))]["canonical_key"])
        for segment_id in span.get("segment_ids", [])
    }


def span_covered(
    *, case_id: str, span: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]],
    gold_by_case_id: Mapping[tuple[str, str], Mapping[str, Any]],
) -> bool:
    required = _span_keys(case_id, span, gold_by_case_id)
    available: set[tuple[str, str, str, int]] = set()
    for candidate in candidates:
        available.update(_candidate_keys(candidate))
    return bool(required) and required.issubset(available)


def gold_group_hit(
    *, case_id: str, groups: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    gold_by_case_id: Mapping[tuple[str, str], Mapping[str, Any]],
) -> bool:
    return any(
        bool(group.get("required_spans"))
        and all(
            span_covered(
                case_id=case_id, span=span, candidates=candidates,
                gold_by_case_id=gold_by_case_id,
            )
            for span in group["required_spans"]
        )
        for group in groups
    )


def _scoring_records(gold_records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for record in gold_records:
        decision = record["canonical_adjudication"]
        spans = [dict(value) for value in decision.get("final_evidence_spans", [])]
        spans_by_id = {str(value["span_id"]): value for value in spans}
        groups = []
        for group in decision.get("final_evidence_groups", []):
            group = dict(group)
            group["required_spans"] = [
                spans_by_id[str(span_id)] for span_id in group.get("required_span_ids", [])
            ]
            groups.append(group)
        result[str(record["case_id"])] = {
            "case_id": record["case_id"], "original_query": _query(record),
            "final_status": decision["final_status"], "evidence_spans": spans,
            "evidence_groups": groups, "source_context": _source_context(record),
        }
    return result


def _count_rate(
    rows: Sequence[Mapping[str, Any]], key: str, *, excluded_cases: Sequence[str],
) -> dict[str, Any]:
    values = [bool(row[key]) for row in rows if row.get(key) is not None]
    numerator = sum(values)
    return {
        "numerator": numerator, "denominator": len(values),
        "rate": numerator / len(values) if values else None,
        "excluded_cases": list(excluded_cases),
    }


def _mean_rate(
    rows: Sequence[Mapping[str, Any]], key: str, *, excluded_cases: Sequence[str],
) -> dict[str, Any]:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return {
        "numerator": sum(values), "denominator": len(values),
        "rate": sum(values) / len(values) if values else None,
        "excluded_cases": list(excluded_cases),
    }


def _interval_metrics(
    spans: Sequence[Mapping[str, Any]], bundle: Mapping[str, Any] | None,
) -> tuple[list[float], list[float], float | None]:
    if not bundle or not spans:
        return [], [], None
    predicted = list(bundle.get("normalized_spans", []))
    if not predicted:
        return [], [], None
    starts = [
        min(abs(float(value["start_time"]) - float(span["start_time"])) for value in predicted)
        for span in spans
    ]
    ends = [
        min(abs(float(value["end_time"]) - float(span["end_time"])) for value in predicted)
        for span in spans
    ]
    gold_duration = interval_union_duration(
        (float(value["start_time"]), float(value["end_time"])) for value in spans
    )
    ratio = float(bundle["union_duration"]) / gold_duration if gold_duration else None
    return starts, ends, ratio


def _source_bvid(score: Mapping[str, Any]) -> str:
    source = score["source_context"]
    if source.get("raw_evidence_authority_state") == "unavailable":
        return str(source["source_identity"]["video_id"])
    return str(source["source_video_id"])


def _query_family(query: str) -> str:
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
    if "为什么" in query or "什么" in query:
        return "definition_or_explanation"
    return "multi-part_question"


def _evidence_structure(score: Mapping[str, Any]) -> str:
    if score["final_status"] == "unverifiable":
        return "source_authority_unavailable"
    groups = score["evidence_groups"]
    if not groups:
        return "no_positive_gold_group"
    if len(groups) > 1:
        return "multiple_alternative_groups"
    spans = groups[0]["required_spans"]
    if len(spans) <= 1:
        return "single_span"
    ordered = sorted(spans, key=lambda value: float(value["start_time"]))
    return (
        "multi_span_distant_regions"
        if any(float(right["start_time"]) - float(left["end_time"]) > 60 for left, right in zip(ordered, ordered[1:]))
        else "multi_span_same_region"
    )


def rescore_frozen_stage3r_predictions(
    *, frozen_predictions: Sequence[Mapping[str, Any]],
    scoring: Mapping[str, Mapping[str, Any]],
    gold_projection: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    gold_by_case_id = {
        (str(value["case_id"]), str(value["gold_segment_id"])): value
        for value in gold_projection
    }
    track = (
        "track_a" if frozen_predictions
        and frozen_predictions[0]["evaluation_track"] == "frozen_v3_end_to_end"
        else "track_b"
    )
    rows = []
    starts: list[float] = []
    ends: list[float] = []
    ratios: list[float] = []
    for prediction in frozen_predictions:
        case_id = str(prediction["case_id"])
        gold = scoring[case_id]
        role = str(gold["final_status"])
        candidates = list(prediction["candidate_set"].get("candidates", []))
        bundle = prediction.get("evidence_bundle")
        row: dict[str, Any] = {
            "case_id": case_id, "case_role": role,
            "terminal_state": prediction["terminal"]["terminal_state"],
            "candidate_count": len(candidates), "bundle_created": bundle is not None,
        }
        if track == "track_a":
            search = prediction.get("search_candidate_set", {})
            bvid = _source_bvid(gold)
            target_ids = {
                value.get("video_id") for value in search.get("video_candidates", [])
                if value.get("source_id") == bvid
            }
            reachable = bool(target_ids)
            row.update({
                "target_video_recall": reachable,
                "video_candidate_recall": reachable,
                "transcript_chunk_recall": any(
                    value.get("video_id") in target_ids
                    and value.get("unit_type") == "transcript_chunk"
                    for value in search.get("raw_unit_candidates", [])
                ),
            })
        if role in {"sufficient", "partial"}:
            groups = gold["evidence_groups"]
            spans = gold["evidence_spans"]
            row["complete_gold_group_candidate_coverage"] = gold_group_hit(
                case_id=case_id, groups=groups, candidates=candidates,
                gold_by_case_id=gold_by_case_id,
            )
            for k in (1, 3, 5):
                covered = sum(
                    span_covered(
                        case_id=case_id, span=span, candidates=candidates[:k],
                        gold_by_case_id=gold_by_case_id,
                    )
                    for span in spans
                )
                row[f"required_span_recall_at_{k}"] = covered / len(spans) if spans else None
            selected_ids = set(bundle.get("candidate_ids", [])) if bundle else set()
            selected = [
                candidate for candidate in candidates
                if candidate["candidate_id"] in selected_ids
            ]
            row["deterministic_bundle_hit_at_1"] = gold_group_hit(
                case_id=case_id, groups=groups, candidates=selected,
                gold_by_case_id=gold_by_case_id,
            )
            start_values, end_values, ratio = _interval_metrics(spans, bundle)
            starts.extend(start_values)
            ends.extend(end_values)
            if ratio is not None:
                ratios.append(ratio)
        rows.append(row)
    evidence = [row for row in rows if row["case_role"] in {"sufficient", "partial"}]
    excluded = [row["case_id"] for row in rows if row["case_role"] not in {"sufficient", "partial"}]
    metrics = {
        "evidence_bearing_cases": len(evidence),
        "target_video_recall": _count_rate(evidence, "target_video_recall", excluded_cases=excluded) if track == "track_a" else None,
        "video_candidate_recall": _count_rate(evidence, "video_candidate_recall", excluded_cases=excluded) if track == "track_a" else None,
        "transcript_chunk_recall": _count_rate(evidence, "transcript_chunk_recall", excluded_cases=excluded) if track == "track_a" else None,
        "complete_gold_group_candidate_coverage": _count_rate(
            evidence, "complete_gold_group_candidate_coverage", excluded_cases=excluded,
        ),
        **{
            f"required_span_recall_at_{k}": _mean_rate(
                evidence, f"required_span_recall_at_{k}", excluded_cases=excluded,
            )
            for k in (1, 3, 5)
        },
        "deterministic_bundle_hit_at_1": _count_rate(
            evidence, "deterministic_bundle_hit_at_1", excluded_cases=excluded,
        ),
        "conditional_bundle_hit_given_complete_candidate_group": _count_rate(
            [row for row in evidence if row["complete_gold_group_candidate_coverage"]],
            "deterministic_bundle_hit_at_1",
            excluded_cases=excluded + [
                row["case_id"] for row in evidence
                if not row["complete_gold_group_candidate_coverage"]
            ],
        ),
        "median_start_time_error_seconds": {
            "numerator": None, "denominator": len(starts),
            "rate": median(starts) if starts else None, "excluded_cases": excluded,
        },
        "median_end_time_error_seconds": {
            "numerator": None, "denominator": len(ends),
            "rate": median(ends) if ends else None, "excluded_cases": excluded,
        },
        "median_interval_union_duration_ratio": {
            "numerator": None, "denominator": len(ratios),
            "rate": median(ratios) if ratios else None, "excluded_cases": excluded,
        },
    }
    return {"track": track, "case_scores": rows, "metrics": metrics}


def operational_diagnostics(
    *, track_a_scores: Sequence[Mapping[str, Any]],
    track_b_scores: Sequence[Mapping[str, Any]],
    track_a_predictions: Sequence[Mapping[str, Any]],
    track_b_predictions: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    def insufficient(track: str, scores: Sequence[Mapping[str, Any]], predictions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        selected = [row for row in scores if row["case_role"] == "insufficient"]
        by_id = {str(value["case_id"]): value for value in predictions}
        bundles = [
            by_id[str(row["case_id"])]["evidence_bundle"]
            for row in selected if by_id[str(row["case_id"])].get("evidence_bundle")
        ]
        return {
            "cases": len(selected),
            "valid_search_candidate_set": sum(
                bool(by_id[str(row["case_id"])].get("search_candidate_set", {}).get("raw_unit_candidates"))
                if track == "track_a" else True for row in selected
            ),
            "valid_candidate_builder_output": sum(row["candidate_count"] > 0 for row in selected),
            "bundle_created": sum(row["bundle_created"] for row in selected),
            "selector_abstained": sum(row["terminal_state"] == "selector_abstained" for row in selected),
            "typed_failure": sum(row["terminal_state"] not in {"bundle_created", "selector_abstained"} for row in selected),
            "bundle_segment_count": sum(len(bundle["normalized_spans"]) for bundle in bundles),
            "bundle_union_duration_seconds": sum(float(bundle["union_duration"]) for bundle in bundles),
            "near_support_concentration": "unavailable",
        }
    insufficient_result = {
        "track_a": insufficient("track_a", track_a_scores, track_a_predictions),
        "track_b": insufficient("track_b", track_b_scores, track_b_predictions),
    }
    unverifiable_rows = [row for row in track_a_scores if row["case_role"] == "unverifiable"]
    unverifiable_result = {
        "track_a": {
            "cases": len(unverifiable_rows),
            "correct_source_authority_terminal": sum(row["terminal_state"] == "source_authority_failure" for row in unverifiable_rows),
            "incorrect_bundle_created": sum(row["bundle_created"] for row in unverifiable_rows),
            "incorrect_regular_selector_failure": sum(row["terminal_state"] in {"selector_failure", "selector_abstained"} for row in unverifiable_rows),
            "other_typed_terminal": sum(row["terminal_state"] not in {"source_authority_failure", "bundle_created", "selector_failure", "selector_abstained"} for row in unverifiable_rows),
        },
        "track_b": {"cases": 0, "correct_source_authority_terminal": 0, "incorrect_bundle_created": 0, "incorrect_regular_selector_failure": 0, "other_typed_terminal": 0},
    }
    return insufficient_result, unverifiable_result


def failure_attribution(
    *, track_a_scores: Sequence[Mapping[str, Any]],
    track_b_scores: Sequence[Mapping[str, Any]],
    scoring: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for track, scores in (("track_a", track_a_scores), ("track_b", track_b_scores)):
        for score in scores:
            case_id = str(score["case_id"])
            gold = scoring[case_id]
            role = score["case_role"]
            stage = signature = None
            if role in {"sufficient", "partial"}:
                if track == "track_a" and not score["target_video_recall"]:
                    stage, signature = "v3_retrieval", "target_video_not_retrieved"
                elif not score["complete_gold_group_candidate_coverage"]:
                    stage, signature = "candidate_builder", "no_complete_gold_group_in_candidate_set"
                elif not score["deterministic_bundle_hit_at_1"]:
                    stage, signature = "deterministic_selector", "complete_candidate_group_not_selected"
            elif role == "unverifiable" and score["terminal_state"] != "source_authority_failure":
                stage, signature = "source_authority", "unverifiable_not_typed_as_source_authority_failure"
            elif score["terminal_state"] not in {"bundle_created", "selector_abstained"}:
                stage = "source_resolution"
                signature = score["terminal_state"]
            if stage is None:
                continue
            spans = gold["evidence_spans"]
            source = gold["source_context"]
            rows.append({
                "case_id": case_id, "track": track, "case_role": role,
                "terminal_state": score["terminal_state"],
                "primary_failure_stage": stage, "secondary_contributing_stage": None,
                "failure_signature": signature,
                "query_family": _query_family(gold["original_query"]),
                "source_type": spans[0]["source_type"] if spans else source.get("source_type", "unavailable"),
                "source_language": spans[0]["source_language"] if spans else source.get("source_language", "unavailable"),
                "evidence_structure": _evidence_structure(gold),
                "generic_or_case_specific": "generic",
            })
    return rows


def failure_summaries(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fields = {
        "stage": "primary_failure_stage", "query_family": "query_family",
        "source_type": "source_type", "source_language": "source_language",
        "evidence_structure": "evidence_structure", "label_role": "case_role",
    }
    output = {
        name: {"total": len(rows), "counts": dict(sorted(Counter(str(row[field]) for row in rows).items()))}
        for name, field in fields.items()
    }
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["failure_signature"])].append(row)
    output["signatures"] = {
        signature: {
            "affected_cases": len({row["case_id"] for row in values}),
            "affected_case_ids": sorted({str(row["case_id"]) for row in values}),
            "affected_query_families": sorted({str(row["query_family"]) for row in values}),
            "primary_stages": sorted({str(row["primary_failure_stage"]) for row in values}),
        }
        for signature, values in grouped.items()
    }
    return output


def _tree_hashes(root: Path) -> list[dict[str, Any]]:
    return [
        {"path": str(path.relative_to(root)), "sha256": file_sha256(path), "size": path.stat().st_size}
        for path in sorted(value for value in root.rglob("*") if value.is_file())
    ]


def _file_manifest(root: Path, exclude: set[str]) -> list[dict[str, Any]]:
    return [
        {"path": str(path.relative_to(root)), "sha256": file_sha256(path), "size": path.stat().st_size}
        for path in sorted(value for value in root.rglob("*") if value.is_file())
        if str(path.relative_to(root)) not in exclude
    ]


def _report(
    *, mapping: Mapping[str, Any], track_a: Mapping[str, Any],
    track_b: Mapping[str, Any], insufficient: Mapping[str, Any],
    unverifiable: Mapping[str, Any], summaries: Mapping[str, Any],
    decision: str, fix: Mapping[str, Any] | None,
    prediction_identity: Mapping[str, Any],
) -> str:
    a = track_a["metrics"]
    b = track_b["metrics"]
    if decision == "authorize_one_bounded_generic_stage3r_fix":
        stage3r_acceptance = (
            "false; the scoring repair is accepted, but Stage 3R-F1 is required "
            "before Stage 4A-R"
        )
        stop_state = """Stage 3R-S1 Complete
Segment Identity Scoring Repair Accepted
Frozen Predictions Rescored
One Bounded Generic Runtime Fix Recommended
Stage 3R-F1 Required Before Stage 4A-R
No Runtime Fix Applied"""
    else:
        stage3r_acceptance = "true"
        stop_state = """Stage 3R-S1 Complete
Gold and Runtime Segment Identities Reconciled
Frozen Track A and Track B Predictions Rescored
Corrected Metrics and Failure Attribution Accepted
Original Invalid Stage 3R Metrics Superseded
Stage 3R Accepted
Stage 4A-R Ready
No Prediction Runtime Re-executed"""
    return f"""# Shiliu V3.5 Stage 3R-S1 — Identity Repair and Frozen-Prediction Rescore

## Outcome

Stage 3R-S1 repaired only the Evaluation Scoring identity bridge. It did not call Retrieval, Candidate Builder, any Selector, model, embedding, or network service. The original frozen Prediction bytes were reused unchanged.

## Bug and repair

1. The invalid Stage 3R scorer compared human-readable Gold IDs (`BV..._seg_000NNN`) directly with physical Runtime IDs (`segment_<sha256>`).
2. They represent the same Raw Segment because both deterministically resolve to Source Artifact, Source Version, Timeline Run, and zero-based Raw ordinal.
3. The invalidated metrics were Candidate Group coverage, Span Recall@1/3/5, Bundle Hit, Conditional Hit, derived Failure Attribution, F1 recommendation, and readiness decision.
4. Bridge version: `{BRIDGE_VERSION}`.
5. Canonical Key: `source_artifact_id + source_version + timeline_run_id + segment_ordinal`.
6. Strong checks: exact Stage 1 time epsilon and exact UTF-8 text digest.
7. Fuzzy text or nearest-time matching: false.
8. Case/video-specific mapping: false.

## Mapping completeness

9. Unique case-scoped Gold Segment references: {mapping['gold_segment_references']}.
10. Gold identities resolved: {mapping['gold_segment_references']} / {mapping['gold_segment_references']}.
11. Exact Raw Runtime-universe mappings: {mapping['exact_identity_matches']}.
12. Gold Segment references actually present in a frozen CandidateSet: {mapping['gold_segment_references_present_in_frozen_candidates']}; Runtime Candidate membership occurrences audited: {mapping['runtime_membership_occurrences']}.
13. Missing identity / ambiguity / duplicate key: 0 / 0 / 0.
14. Cross-source / version / timeline: 0 / 0 / 0.
15. Start, end, and text digest matches: {mapping['exact_identity_matches']} / {mapping['exact_identity_matches']} / {mapping['exact_identity_matches']}.

## Prediction preservation

16. Track A: 31, SHA-256 `{prediction_identity['track_a_sha256']}`.
17. Track B: 27, SHA-256 `{prediction_identity['track_b_sha256']}`.
18. Retrieval / Builder / Selector reruns: 0 / 0 / 0.
19. Prediction hashes unchanged: true; per-case Stage 3R prediction files unchanged: true.

## Corrected metrics

20. Track A Target Video Recall: `{a['target_video_recall']}`.
21. Track A Complete Gold Group Candidate Coverage: `{a['complete_gold_group_candidate_coverage']}`.
22. Track A Span Recall@1/@3/@5: `{a['required_span_recall_at_1']}`, `{a['required_span_recall_at_3']}`, `{a['required_span_recall_at_5']}`.
23. Track A Bundle Hit: `{a['deterministic_bundle_hit_at_1']}`.
24. Track B Complete Gold Group Candidate Coverage: `{b['complete_gold_group_candidate_coverage']}`.
25. Track B Span Recall@1/@3/@5: `{b['required_span_recall_at_1']}`, `{b['required_span_recall_at_3']}`, `{b['required_span_recall_at_5']}`.
26. Track B Bundle Hit / Conditional Hit: `{b['deterministic_bundle_hit_at_1']}` / `{b['conditional_bundle_hit_given_complete_candidate_group']}`.
27. Track A median start/end/union ratio: `{a['median_start_time_error_seconds']}`, `{a['median_end_time_error_seconds']}`, `{a['median_interval_union_duration_ratio']}`.
28. Track B median start/end/union ratio: `{b['median_start_time_error_seconds']}`, `{b['median_end_time_error_seconds']}`, `{b['median_interval_union_duration_ratio']}`.

Every metric object includes numerator, denominator, rate, and excluded Cases. Gold Groups remain OR; Required Spans within a Group remain AND.

## Diagnostics and attribution

29. Insufficient operational diagnostics: `{insufficient}`.
30. Unverifiable diagnostics: `{unverifiable}`.
31. Unverifiable Cases incorrectly creating a Bundle: `{unverifiable['track_a']['incorrect_bundle_created']}`.
32. Rescored failure stages: `{summaries['stage']}`.
33. Failures by Query Family: `{summaries['query_family']}`.
34. Failures by Evidence Structure: `{summaries['evidence_structure']}`.
35. Repeated signatures: `{summaries['signatures']}`.

## Historical relationship

36. Preserved: original predictions, SearchCandidateSets, Builder/Selector outputs, Bundles, terminals, Runtime hashes, and Prediction Freeze.
37. Superseded: original scoring metrics, Failure Attribution, readiness decision, and F1 recommendation.
38. The old “Builder全面失败” and “Selector全面失败” conclusions were artifacts of the namespace bug and are not retained; corrected per-track outcomes above are authoritative.

## Final decision

39. Stage 3R-S1 status: complete.
40. `stage3r_final_decision: {decision}`.
41. Stage 3R-F1: `{json.dumps(fix, ensure_ascii=False, sort_keys=True) if fix else 'not recommended'}`.
42. Stage 3R accepted: {stage3r_acceptance}.
43. Next action: Main-session review, followed only by the handoff authorized by this decision.
44. This Codex session may close after Main-session review.

## Stop state

{stop_state.replace(chr(10), '  ' + chr(10))}
"""


def run_stage3r_s1(
    *, repository_root: Path, stage3r_root: Path, output_root: Path,
    artifact_manifest: Path,
) -> dict[str, Any]:
    corpus = stage3r_root / "input/stage2r_final_corpus/development_gold.executable_31.jsonl"
    track_a_path = stage3r_root / "prediction_freeze/track_a_predictions.jsonl"
    track_b_path = stage3r_root / "prediction_freeze/track_b_predictions.jsonl"
    lock_path = stage3r_root / "prediction_freeze/prediction_freeze.lock.json"
    stage3r_manifest_path = stage3r_root / "stage3r_manifest.json"
    stage3r_audit_path = stage3r_root / "stage3r_execution.audit.json"
    if file_sha256(corpus) != CORPUS_SHA256:
        raise RuntimeError("Final Development Corpus identity mismatch")
    gold_records = load_jsonl(corpus)
    labels = Counter(record["canonical_adjudication"]["final_status"] for record in gold_records)
    if len(gold_records) != 31 or dict(labels) != {
        "sufficient": 11, "partial": 9, "insufficient": 7, "unverifiable": 4,
    }:
        raise RuntimeError("Final Development Corpus shape mismatch")
    before_a = file_sha256(track_a_path)
    before_b = file_sha256(track_b_path)
    if before_a != TRACK_A_SHA256 or before_b != TRACK_B_SHA256:
        raise RuntimeError("Frozen Prediction Identity Not Preserved")
    track_a_predictions = load_jsonl(track_a_path)
    track_b_predictions = load_jsonl(track_b_path)
    if len(track_a_predictions) != 31 or len(track_b_predictions) != 27:
        raise RuntimeError("Frozen Prediction count mismatch")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    audit = json.loads(stage3r_audit_path.read_text(encoding="utf-8"))
    if (
        lock.get("predictions_modified_after_freeze") is not False
        or audit["isolation"]["heldout_accessed"] is not False
        or audit["execution_projection"]["runtime_gold_leakage"] != 0
    ):
        raise RuntimeError("Original Stage 3R freeze/isolation invalid")
    per_case_before = _tree_hashes(stage3r_root / "track_a/cases") + _tree_hashes(stage3r_root / "track_b/cases")

    output_root.mkdir(parents=True, exist_ok=True)
    original = output_root / "original_stage3r"
    original_report = stage3r_root / "V3_5_STAGE3R_EXPANDED_DEVELOPMENT_RERUN_REPORT.md"
    write_json(original / "original_stage3r_identity.json", {
        "original_stage3r_manifest_path": str(stage3r_manifest_path),
        "original_stage3r_manifest_sha256": file_sha256(stage3r_manifest_path),
        "original_stage3r_report_path": str(original_report),
        "original_stage3r_report_sha256": file_sha256(original_report),
        "track_a_predictions_path": str(track_a_path),
        "track_a_predictions_sha256": before_a,
        "track_b_predictions_path": str(track_b_path),
        "track_b_predictions_sha256": before_b,
        "prediction_freeze_lock_path": str(lock_path),
        "prediction_freeze_lock_sha256": file_sha256(lock_path),
        "original_metrics_status": "invalidated_due_to_segment_identity_namespace_mismatch",
        "original_failure_attribution_status": "invalidated_due_to_segment_identity_namespace_mismatch",
    })
    write_jsonl(original / "original_prediction_hashes.jsonl", [
        {"path": str(track_a_path), "sha256": before_a, "records": 31},
        {"path": str(track_b_path), "sha256": before_b, "records": 27},
    ])
    runtime_hashes_path = stage3r_root / "runtime_freeze/runtime_source_file_hashes.jsonl"
    (original / "original_runtime_hashes.jsonl").write_bytes(runtime_hashes_path.read_bytes())
    invalid_metrics = {
        "track_a": json.loads((stage3r_root / "metrics/track_a_metrics.json").read_text(encoding="utf-8")),
        "track_b": json.loads((stage3r_root / "metrics/track_b_metrics.json").read_text(encoding="utf-8")),
        "status": "invalidated_due_to_segment_identity_namespace_mismatch",
    }
    write_json(original / "original_invalid_metrics.json", invalid_metrics)
    invalid_failures = load_jsonl(stage3r_root / "failure_analysis/case_failure_attribution.jsonl")
    write_json(original / "original_invalid_failure_attribution.json", {
        "status": "invalidated_due_to_segment_identity_namespace_mismatch",
        "records": invalid_failures,
    })

    contract = {
        "contract_version": BRIDGE_VERSION,
        "canonical_segment_key": {
            "required_fields": [
                "source_artifact_id", "source_version", "timeline_run_id",
                "segment_ordinal",
            ],
            "segment_ordinal_basis": "zero_based_raw_original_ordinal",
            "serialization": {
                "sort_keys": True, "ensure_ascii": False,
                "separators": [",", ":"], "allow_nan": False,
            },
        },
        "strong_validation_fields": ["start_time", "end_time", "text_digest"],
        "time_epsilon_seconds": TIMELINE_EPSILON_SECONDS,
        "allowed_statuses": sorted(ALLOWED_MAPPING_STATUSES),
        "fuzzy_matching": False, "nearest_time_matching": False,
        "case_specific_mapping": False, "video_specific_mapping": False,
    }
    write_json(output_root / "contracts/segment_identity_bridge_contract.json", contract)
    (output_root / "contracts/segment_identity_bridge_policy.md").write_text(
        "# Segment Identity Bridge Policy\n\n"
        f"Version: `{BRIDGE_VERSION}`.\n\n"
        "The structured key is Source Artifact + Source Version + Timeline Run + "
        "zero-based Raw original ordinal. Legacy Gold IDs are parsed only after exact "
        "format validation and are confirmed against the separately authorized Raw "
        "Source. Start/end use the Stage 1 epsilon; text digest is exact. Fuzzy text, "
        "nearest-time, Case-specific, and video-specific mappings are prohibited.\n",
        encoding="utf-8",
    )

    bridge = build_identity_bridge(
        gold_records=gold_records,
        predictions=track_a_predictions + track_b_predictions,
        artifact_manifest=artifact_manifest,
    )
    write_jsonl(output_root / "identity_mapping/gold_segment_identity_projection.jsonl", bridge["gold_projection"])
    write_jsonl(output_root / "identity_mapping/runtime_segment_identity_projection.jsonl", bridge["runtime_projection"])
    write_jsonl(output_root / "identity_mapping/gold_to_runtime_segment_mapping.jsonl", bridge["mapping"])
    write_jsonl(output_root / "identity_mapping/mapping_failures.jsonl", bridge["failures"])
    write_jsonl(output_root / "identity_mapping/mapping_ambiguities.jsonl", bridge["ambiguities"])
    mapping_summary = {
        "bridge_version": BRIDGE_VERSION,
        "gold_segment_references": len(bridge["gold_projection"]),
        "gold_segments_identity_resolved": len(bridge["gold_projection"]),
        "exact_identity_matches": sum(row["mapping_status"] == "exact_identity_match" for row in bridge["mapping"]),
        "runtime_universe_physical_segments": len(bridge["runtime_projection"]),
        "runtime_membership_occurrences": len(bridge["runtime_memberships"]),
        "gold_segment_references_present_in_frozen_candidates": sum(
            any(
                membership["case_id"] == gold["case_id"]
                and membership["canonical_key"] == gold["canonical_key"]
                for membership in bridge["runtime_memberships"]
            )
            for gold in bridge["gold_projection"]
        ),
        "missing_gold_identity": 0, "ambiguous_mappings": 0,
        "duplicate_canonical_keys": 0, "cross_source_mappings": 0,
        "cross_version_mappings": 0, "cross_timeline_mappings": 0,
    }
    write_json(output_root / "identity_mapping/mapping_summary.json", mapping_summary)
    write_json(output_root / "identity_mapping/mapping_integrity.audit.json", {
        **mapping_summary,
        "gold_segments_identity_resolved_rate": 1.0,
        "each_gold_segment_maps_to_exactly_one_runtime_segment": True,
        "each_runtime_segment_key_maps_to_at_most_one_physical_segment": True,
        "start_time_match": True, "end_time_match": True,
        "text_digest_match": True, "mapping_valid": True,
    })

    scoring = _scoring_records(gold_records)
    track_a = rescore_frozen_stage3r_predictions(
        frozen_predictions=track_a_predictions, scoring=scoring,
        gold_projection=bridge["gold_projection"],
    )
    track_b = rescore_frozen_stage3r_predictions(
        frozen_predictions=track_b_predictions, scoring=scoring,
        gold_projection=bridge["gold_projection"],
    )
    write_jsonl(output_root / "rescore/track_a_case_scores.jsonl", track_a["case_scores"])
    write_jsonl(output_root / "rescore/track_b_case_scores.jsonl", track_b["case_scores"])
    write_json(output_root / "rescore/track_a_metrics.json", track_a["metrics"])
    write_json(output_root / "rescore/track_b_metrics.json", track_b["metrics"])
    insufficient, unverifiable = operational_diagnostics(
        track_a_scores=track_a["case_scores"], track_b_scores=track_b["case_scores"],
        track_a_predictions=track_a_predictions, track_b_predictions=track_b_predictions,
    )
    write_json(output_root / "rescore/insufficient_diagnostics.json", insufficient)
    write_json(output_root / "rescore/unverifiable_diagnostics.json", unverifiable)
    write_json(output_root / "rescore/rescore_summary.json", {
        "bridge_version": BRIDGE_VERSION, "track_a": track_a["metrics"],
        "track_b": track_b["metrics"], "corrected_metrics_accepted": True,
        "old_invalid_metrics_reused": False,
    })

    failure_rows = failure_attribution(
        track_a_scores=track_a["case_scores"], track_b_scores=track_b["case_scores"],
        scoring=scoring,
    )
    write_jsonl(output_root / "failure_analysis/case_failure_attribution.rescored.jsonl", failure_rows)
    summaries = failure_summaries(failure_rows)
    for name in ("stage", "query_family", "source_type", "source_language", "evidence_structure", "label_role"):
        filename = "failure_stage_summary.rescored.json" if name == "stage" else f"failure_by_{name}.rescored.json"
        write_json(output_root / "failure_analysis" / filename, summaries[name])
    write_json(output_root / "failure_analysis/failure_signatures.rescored.json", summaries["signatures"])

    write_json(output_root / "comparison/invalid_stage3r_metrics.json", invalid_metrics)
    rescored = {"track_a": track_a["metrics"], "track_b": track_b["metrics"]}
    write_json(output_root / "comparison/rescored_stage3r_metrics.json", rescored)
    write_json(output_root / "comparison/metric_delta.json", {
        "old_values_usable_as_baseline": False,
        "comparison": "old values invalidated; no arithmetic delta is meaningful",
    })
    write_json(output_root / "comparison/failure_attribution_delta.json", {
        "old_failure_attribution_usable": False,
        "old_records": len(invalid_failures), "rescored_records": len(failure_rows),
    })
    write_json(output_root / "comparison/stage3r_result_supersession.json", {
        "superseded_assets": [
            "original Stage 3R scoring metrics",
            "original Stage 3R failure attribution",
            "original Stage 3R readiness decision",
            "original Stage 3R-F1 recommendation",
        ],
        "preserved_assets": [
            "original Track A predictions", "original Track B predictions",
            "original SearchCandidateSets", "original Candidate Builder outputs",
            "original Selector outputs", "original EvidenceBundles",
            "original Runtime terminal states", "original Prediction Freeze",
        ],
        "supersession_reason": "segment_identity_namespace_mismatch_repaired",
    })

    qualifying = []
    for signature, value in summaries["signatures"].items():
        if (
            value["affected_cases"] >= 3
            and len(value["affected_query_families"]) >= 2
            and len(value["primary_stages"]) == 1
            and value["primary_stages"][0] in {"candidate_builder", "deterministic_selector"}
        ):
            qualifying.append((signature, value))
    fix = None
    if qualifying:
        signature, value = sorted(qualifying, key=lambda item: (-item[1]["affected_cases"], item[0]))[0]
        stage = value["primary_stages"][0]
        fix = {
            "failure_signature": signature,
            "affected_case_ids": value["affected_case_ids"],
            "affected_query_families": value["affected_query_families"],
            "affected_stage": stage,
            "proposed_generic_mechanism": (
                "one bounded generic Candidate Builder coverage repair within frozen budgets"
                if stage == "candidate_builder"
                else "one bounded generic multi-span coverage objective repair"
            ),
            "allowed_files": [
                "the separately authorized existing affected Runtime stage",
                "Stage 3R-F1 tests and rerun artifacts",
            ],
            "forbidden_case_specific_logic": True,
            "required_rerun_scope": "all frozen 31 Development Cases",
        }
        decision = "authorize_one_bounded_generic_stage3r_fix"
        write_json(output_root / "readiness/stage3r_f1_readiness.audit.json", {
            "stage3r_s1_status": "complete", "stage3r_final_decision": decision,
            **fix,
        })
        (output_root / "readiness/STAGE3R_F1_BOUNDED_GENERIC_FIX_HANDOFF.md").write_text(
            "# Stage 3R-F1 Bounded Generic Fix Handoff\n\n"
            "S1 accepted the corrected scoring and recommends exactly one bounded "
            "generic Runtime fix. No Runtime fix was applied in S1.\n\n"
            f"```json\n{json.dumps(fix, ensure_ascii=False, indent=2, sort_keys=True)}\n```\n",
            encoding="utf-8",
        )
    else:
        decision = "freeze_current_runtime_and_proceed_to_stage4a_r"
        write_json(output_root / "readiness/stage3r_acceptance.audit.json", {
            "stage3r_s1_status": "complete", "stage3r_final_decision": decision,
            "identity_mapping_complete": True, "predictions_unchanged": True,
            "rescoring_valid": True, "failure_attribution_complete": True,
            "stage3r_accepted": True,
        })
        (output_root / "readiness/STAGE4A_R_MECHANICAL_GATE_RERUN_HANDOFF.md").write_text(
            "# Stage 4A-R Mechanical Gate Rerun Handoff\n\n"
            "Stage 3R is accepted after S1 identity repair and frozen-prediction "
            "rescore. Stage 4A-R requires separate Main-session authorization.\n",
            encoding="utf-8",
        )

    after_a = file_sha256(track_a_path)
    after_b = file_sha256(track_b_path)
    per_case_after = _tree_hashes(stage3r_root / "track_a/cases") + _tree_hashes(stage3r_root / "track_b/cases")
    prediction_unchanged = before_a == after_a and before_b == after_b
    per_case_unchanged = per_case_before == per_case_after
    if not prediction_unchanged or not per_case_unchanged:
        raise RuntimeError("Frozen Prediction Identity Not Preserved")
    prediction_identity = {
        "track_a_sha256": after_a, "track_b_sha256": after_b,
        "track_a_predictions_unchanged": True,
        "track_b_predictions_unchanged": True,
        "per_case_prediction_files_unchanged": True,
    }
    write_json(original / "original_stage3r_freeze.audit.json", prediction_identity)
    write_json(output_root / "runtime_guards/forbidden_runtime_calls.audit.json", {
        "retrieval_calls": 0, "candidate_builder_calls": 0,
        "selector_calls": 0, "prediction_runner_calls": 0,
        "guard_method": "S1 imports and invokes no prohibited runner function",
    })
    write_json(output_root / "runtime_guards/prediction_rerun.audit.json", {
        **prediction_identity, "prediction_runtime_reexecuted": False,
    })
    write_json(output_root / "isolation/heldout_access.audit.json", {
        "heldout_accessed": False, "heldout_case_payloads_read": 0,
        "heldout_gold_records_read": 0, "heldout_queries_executed": 0,
    })
    write_json(output_root / "stage3r_s1_runtime_usage.json", {
        "retrieval_calls": 0, "candidate_builder_calls": 0, "selector_calls": 0,
        "external_llm_calls": 0, "openai_calls": 0, "deepseek_calls": 0,
        "anthropic_calls": 0, "external_embedding_calls": 0, "network_calls": 0,
    })
    execution_audit = {
        "stage3r_s1_status": "complete", "stage3r_final_decision": decision,
        "corpus": {"records": 31, "sha256": CORPUS_SHA256, "labels": dict(labels)},
        "prediction_preservation": prediction_identity,
        "mapping": {**mapping_summary, "mapping_valid": True},
        "rescoring": {
            "canonical_identity_used": True, "gold_group_or_span_and": True,
            "track_a_complete": True, "track_b_complete": True,
            "old_invalid_metrics_reused": False,
        },
        "runtime_guards": {
            "retrieval_calls": 0, "candidate_builder_calls": 0,
            "selector_calls": 0, "prediction_runner_calls": 0,
        },
        "isolation": {"heldout_accessed": False, "external_calls": 0},
        "runtime_files_modified": False,
        "final_readiness_decision_unique": True,
    }
    write_json(output_root / "stage3r_s1_execution.audit.json", execution_audit)
    report = _report(
        mapping=mapping_summary, track_a=track_a, track_b=track_b,
        insufficient=insufficient, unverifiable=unverifiable,
        summaries=summaries, decision=decision, fix=fix,
        prediction_identity=prediction_identity,
    )
    (output_root / "V3_5_STAGE3R_S1_IDENTITY_REPAIR_AND_RESCORE_REPORT.md").write_text(
        report, encoding="utf-8",
    )
    write_json(output_root / "tests/test_execution_summary.json", {
        "status": "pending", "command": "pytest Stage 3R-S1 and related regression tests",
    })
    rows = _file_manifest(
        output_root,
        exclude={"stage3r_s1_manifest.json", "stage3r_s1_file_hash_manifest.jsonl"},
    )
    write_jsonl(output_root / "stage3r_s1_file_hash_manifest.jsonl", rows)
    write_json(output_root / "stage3r_s1_manifest.json", {
        "runner_version": RUNNER_VERSION, "bridge_version": BRIDGE_VERSION,
        "created_at": utc_now(), "file_count": len(rows),
        "stage3r_s1_status": "complete", "stage3r_final_decision": decision,
        "stop_state": "Awaiting Main-session Review",
    })
    return {
        "stage3r_s1_status": "complete", "stage3r_final_decision": decision,
        "mapping_summary": mapping_summary, "track_a_metrics": track_a["metrics"],
        "track_b_metrics": track_b["metrics"], "fix": fix,
    }
