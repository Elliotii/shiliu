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
    read_reference_bytes,
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
    if (
        declared_source != reference.source_id
        or declared_path != actual_path
        or not expected
    ):
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
    artifacts=None,
) -> SourceVersionBinding:
    actual = source_version_for_bytes(
        read_reference_bytes(reference, artifacts=artifacts)
    )
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
    artifacts=None,
) -> SourceVersionBinding:
    with db.connect() as connection:
        row = connection.execute(
            "SELECT s.desired_state,s.lexical_state,s.dense_state FROM shiliu.retrieval_sync_state s "
            "JOIN shiliu.retrieval_projection_tasks t ON t.workspace_id=s.workspace_id AND t.domain='collection' AND t.resource_key=s.video_id::text "
            "JOIN shiliu.videos v ON (v.workspace_id,v.id)=(s.workspace_id,s.video_id) "
            "WHERE s.workspace_id=%s AND s.video_id=%s AND (t.payload->>'ready_generation')::bigint=t.requested_generation "
            "AND v.raw_subtitle_path=%s AND v.removed_at IS NULL AND NOT v.is_ignored "
            "AND EXISTS(SELECT 1 FROM shiliu.video_source_memberships m JOIN shiliu.favorite_sources f ON (f.workspace_id,f.id)=(m.workspace_id,m.source_id) WHERE m.workspace_id=v.workspace_id AND m.video_id=v.id AND m.removed_at IS NULL AND f.status='active')",
            (db.workspace_id, video_id, reference.artifact_path),
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
    actual = source_version_for_bytes(
        read_reference_bytes(reference, artifacts=artifacts)
    )
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
        if (
            record.get("artifact_type") == "raw_subtitle"
            and record.get("video_id") == video_id
        ):
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
