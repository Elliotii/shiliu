from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

from shiliu.evidence.contracts import (
    EvidenceContractError,
    EvidenceWarning,
    ParsedSourceArtifact,
    RawEvidenceSegment,
    SourceArtifactReference,
    TIMELINE_EPSILON_SECONDS,
    TimelineRun,
)


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def authoritative_raw_json_path(candidate: str | Path) -> Path:
    return Path(candidate).expanduser().resolve().with_name("subtitle-raw.json")


def make_source_artifact_id(reference: SourceArtifactReference) -> str:
    lineage = str(reference.source_lineage or reference.source_type or "unknown").lower()
    if lineage not in {"human", "ai", "asr", "unknown"}:
        lineage = "unknown"
    payload = {
        "artifact_role": reference.artifact_role,
        "part": int(reference.part),
        "platform": reference.platform,
        "source_id": reference.source_id,
        "source_lineage": lineage,
    }
    return "source_artifact_" + sha256(canonical_json(payload)).hexdigest()


def make_source_artifact_id_v1(reference: SourceArtifactReference) -> str:
    """Reproduce the superseded Stage 1A provisional identity for audit only."""
    payload = {
        "part": int(reference.part),
        "platform": reference.platform,
        "source_id": reference.source_id,
        "source_language": reference.source_language,
        "source_type": reference.source_type,
    }
    return "source_artifact_" + sha256(canonical_json(payload)).hexdigest()


def source_version_for_bytes(raw_bytes: bytes) -> str:
    return sha256(raw_bytes).hexdigest()


def make_segment_id(
    source_artifact_id: str, source_version: str, original_ordinal: int
) -> str:
    payload = {
        "original_ordinal": int(original_ordinal),
        "source_artifact_id": source_artifact_id,
        "source_version": source_version,
    }
    return "segment_" + sha256(canonical_json(payload)).hexdigest()


def make_segment_digest(start_time: float, end_time: float, content: str) -> str:
    payload = {
        "content": content,
        "from": float(start_time),
        "to": float(end_time),
    }
    return sha256(canonical_json(payload)).hexdigest()


def make_timeline_run_id(source_version: str, run_ordinal: int) -> str:
    payload = {"run_ordinal": int(run_ordinal), "source_version": source_version}
    return "timeline_run_" + sha256(canonical_json(payload)).hexdigest()


def load_source_artifact(
    reference: SourceArtifactReference,
    *,
    expected_source_version: str | None = None,
    epsilon_seconds: float = TIMELINE_EPSILON_SECONDS,
) -> ParsedSourceArtifact:
    path = authoritative_raw_json_path(reference.artifact_path)
    if not path.is_file():
        raise EvidenceContractError(
            f"authoritative raw subtitle is missing: {path}",
            code="raw_subtitle_missing",
        )
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise EvidenceContractError(str(exc), code="source_unreadable") from exc
    version = source_version_for_bytes(raw_bytes)
    if expected_source_version is not None and version != expected_source_version:
        raise EvidenceContractError(
            "authoritative raw subtitle version does not match expected_source_version",
            code="source_version_mismatch",
        )
    try:
        payload = json.loads(raw_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceContractError(str(exc), code="source_unreadable") from exc

    artifact_id = make_source_artifact_id(reference)
    if not isinstance(payload, list):
        return ParsedSourceArtifact(
            reference=reference,
            source_artifact_id=artifact_id,
            source_version=version,
            validation_status="source_unreadable",
            warnings=(EvidenceWarning("source_unreadable", "top-level JSON must be an array"),),
            invalid_segment_ordinals=(),
            timeline_runs=(),
            segments=(),
        )

    warnings: list[EvidenceWarning] = []
    invalid: list[int] = []
    segments: list[RawEvidenceSegment] = []
    structural_invalid = False
    time_invalid = False
    for ordinal, item in enumerate(payload):
        if not isinstance(item, dict):
            structural_invalid = True
            invalid.append(ordinal)
            warnings.append(EvidenceWarning("source_unreadable", "segment must be an object", ordinal))
            continue
        if not {"from", "to", "content"}.issubset(item):
            structural_invalid = True
            invalid.append(ordinal)
            warnings.append(EvidenceWarning("source_unreadable", "segment fields are missing", ordinal))
            continue
        if not isinstance(item["content"], str):
            structural_invalid = True
            invalid.append(ordinal)
            warnings.append(EvidenceWarning("source_unreadable", "segment content must be a string", ordinal))
            continue
        try:
            start = float(item["from"])
            end = float(item["to"])
        except (TypeError, ValueError):
            time_invalid = True
            invalid.append(ordinal)
            warnings.append(EvidenceWarning("segment_time_invalid", "segment time is not numeric", ordinal))
            continue
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
            time_invalid = True
            invalid.append(ordinal)
            warnings.append(EvidenceWarning("segment_time_invalid", "segment time is invalid", ordinal))
            continue
        text = item["content"]
        segments.append(
            RawEvidenceSegment(
                segment_id=make_segment_id(artifact_id, version, ordinal),
                source_artifact_id=artifact_id,
                source_version=version,
                original_ordinal=ordinal,
                start_time=start,
                end_time=end,
                source_text=text,
                source_type=reference.source_type,
                source_language=reference.source_language,
                segment_digest=make_segment_digest(start, end, text),
                timeline_run_id="",
                run_local_ordinal=-1,
            )
        )

    if structural_invalid:
        status = "source_unreadable"
        runs: tuple[TimelineRun, ...] = ()
    elif time_invalid:
        status = "invalid_segment_time"
        runs = ()
    else:
        segments, runs = _assign_timeline_runs(
            segments, source_version=version, epsilon_seconds=epsilon_seconds
        )
        status = "valid_multiple_runs" if len(runs) > 1 else "valid_single_run"
        if len(runs) > 1:
            warnings.append(
                EvidenceWarning(
                    "source_timeline_non_monotonic",
                    f"source contains {len(runs)} monotonic timeline runs",
                )
            )
    return ParsedSourceArtifact(
        reference=reference,
        source_artifact_id=artifact_id,
        source_version=version,
        validation_status=status,  # type: ignore[arg-type]
        warnings=tuple(warnings),
        invalid_segment_ordinals=tuple(sorted(set(invalid))),
        timeline_runs=runs,
        segments=tuple(segments),
    )


def require_same_timeline_run(segments: tuple[RawEvidenceSegment, ...]) -> str:
    run_ids = {segment.timeline_run_id for segment in segments}
    if not segments or len(run_ids) != 1 or "" in run_ids:
        raise EvidenceContractError(
            "evidence span must contain segments from exactly one timeline run",
            code="invalid_cross_timeline_chunk",
        )
    return next(iter(run_ids))


def _assign_timeline_runs(
    segments: list[RawEvidenceSegment],
    *,
    source_version: str,
    epsilon_seconds: float,
) -> tuple[list[RawEvidenceSegment], tuple[TimelineRun, ...]]:
    if epsilon_seconds < 0:
        raise ValueError("epsilon_seconds must not be negative")
    if not segments:
        return segments, ()
    boundaries = [0]
    for index in range(1, len(segments)):
        if segments[index].start_time < segments[index - 1].start_time - epsilon_seconds:
            boundaries.append(index)
    boundaries.append(len(segments))
    assigned = list(segments)
    runs: list[TimelineRun] = []
    for run_ordinal, (start_index, stop_index) in enumerate(zip(boundaries, boundaries[1:])):
        run_id = make_timeline_run_id(source_version, run_ordinal)
        values = segments[start_index:stop_index]
        for local, segment in enumerate(values):
            assigned[start_index + local] = replace(
                segment, timeline_run_id=run_id, run_local_ordinal=local
            )
        runs.append(
            TimelineRun(
                timeline_run_id=run_id,
                run_ordinal=run_ordinal,
                first_original_ordinal=values[0].original_ordinal,
                last_original_ordinal=values[-1].original_ordinal,
                start_time=values[0].start_time,
                end_time=values[-1].end_time,
                segment_count=len(values),
            )
        )
    return assigned, tuple(runs)
