from __future__ import annotations

import json
from pathlib import Path

from shiliu.db import Database
from shiliu.evidence.contracts import (
    EvidenceContractError,
    SOURCE_IDENTITY_VERSION,
    SourceArtifactReference,
    SourceVersionBinding,
)
from shiliu.evidence.source import (
    authoritative_raw_json_path,
    make_source_artifact_id,
    source_version_for_bytes,
)


def bind_snapshot_manifest_version(
    reference: SourceArtifactReference,
    *,
    video_id: int,
    manifest_path: str | Path,
) -> SourceVersionBinding:
    record = _snapshot_manifest_record(manifest_path, video_id=video_id)
    declared_path = authoritative_raw_json_path(str(record.get("snapshot_path") or ""))
    actual_path = authoritative_raw_json_path(reference.artifact_path)
    declared_source = str(record.get("bvid") or "")
    expected = str(record.get("sha256") or "")
    if declared_source != reference.source_id or declared_path != actual_path or not expected:
        raise EvidenceContractError(
            "Snapshot manifest logical source or path does not match the requested artifact",
            code="source_version_mismatch",
        )
    actual = _read_version(actual_path)
    if actual != expected:
        raise EvidenceContractError(
            "Snapshot artifact bytes do not match the manifest SHA-256",
            code="source_version_mismatch",
        )
    return _binding(reference, expected, actual, "snapshot_manifest")


def bind_pinned_version(
    reference: SourceArtifactReference,
    *,
    expected_source_version: str,
) -> SourceVersionBinding:
    actual = _read_version(authoritative_raw_json_path(reference.artifact_path))
    if actual != expected_source_version:
        raise EvidenceContractError(
            "Pinned source version does not match current authoritative bytes",
            code="source_version_mismatch",
        )
    return _binding(reference, expected_source_version, actual, "pinned_request")


def bind_live_current_version(
    reference: SourceArtifactReference,
    *,
    db: Database,
    video_id: int,
    require_dense_current: bool = False,
) -> SourceVersionBinding:
    with db.connect() as connection:
        row = connection.execute(
            "SELECT desired_state, lexical_state, dense_state "
            "FROM retrieval_sync_state WHERE video_id=?",
            (video_id,),
        ).fetchone()
    if (
        row is None
        or str(row["desired_state"]) != "indexed"
        or str(row["lexical_state"]) != "current"
        or (require_dense_current and str(row["dense_state"]) != "current")
    ):
        raise EvidenceContractError(
            "retrieval sync/index state is not compatible with live exact replay",
            code="index_not_ready",
        )
    actual = _read_version(authoritative_raw_json_path(reference.artifact_path))
    return _binding(reference, actual, actual, "live_current_exact_replay")


def _snapshot_manifest_record(
    manifest_path: str | Path, *, video_id: int
) -> dict[str, object]:
    try:
        lines = Path(manifest_path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EvidenceContractError(str(exc), code="source_unavailable") from exc
    matches = []
    for line in lines:
        record = json.loads(line)
        if record.get("artifact_type") == "raw_subtitle" and record.get("video_id") == video_id:
            matches.append(record)
    if len(matches) != 1 or matches[0].get("status") != "ok":
        raise EvidenceContractError(
            f"Snapshot manifest has no unique usable raw subtitle for video {video_id}",
            code="source_unavailable",
        )
    return matches[0]


def _read_version(path: Path) -> str:
    try:
        return source_version_for_bytes(path.read_bytes())
    except OSError as exc:
        raise EvidenceContractError(str(exc), code="source_unavailable") from exc


def _binding(
    reference: SourceArtifactReference,
    expected: str,
    actual: str,
    authority: str,
) -> SourceVersionBinding:
    return SourceVersionBinding(
        source_artifact_id=make_source_artifact_id(reference),
        source_identity_version=SOURCE_IDENTITY_VERSION,
        source_version=actual,
        source_version_authority=authority,  # type: ignore[arg-type]
        source_version_verified=expected == actual,
        source_version_expected=expected,
        source_version_actual=actual,
    )
