"""Frozen-authority development source inventory builder.

This module has no dependency on case construction or review workflows.
"""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any

from shiliu.evidence.contracts import SourceArtifactReference
from shiliu.evidence.source import canonical_json, load_source_artifact, make_source_artifact_id
from shiliu.eval_v3_5.eval_v2.protected_source_projection import ProtectedSourceProjection


INVENTORY_VERSION = "v3.5-development-source-inventory-safe-v2"
INVENTORY_FIELDS = frozenset({
    "safe_source_id", "platform", "video_id", "source_artifact_id", "source_version",
    "source_type", "source_language", "source_availability", "source_failure_code",
    "timeline_run_ids", "segment_count", "raw_duration_seconds", "export_relative_path",
    "source_record_digest", "used_in_existing_pilot", "existing_pilot_case_count",
    "development_case_construction_allowed", "inventory_version",
})


class SafeInventoryError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(path: Path) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("artifact_type") == "raw_subtitle":
                video_id = int(record["video_id"])
                if video_id in records:
                    raise SafeInventoryError("duplicate raw artifact authority")
                records[video_id] = record
    except (OSError, UnicodeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise SafeInventoryError("artifact authority invalid") from exc
    return records


def _source_type(value: Any) -> str:
    normalized = str(value or "unknown").lower()
    return normalized if normalized in {"human", "ai", "asr", "unknown"} else "unknown"


def _safe_id(snapshot_hash: str, artifact_id: str, version: str) -> str:
    payload = {
        "inventory_version": INVENTORY_VERSION,
        "snapshot_db_sha256": snapshot_hash,
        "source_artifact_id": artifact_id,
        "source_version": version,
    }
    return "SAFESRC_" + sha256(canonical_json(payload)).hexdigest()[:20]


def _unavailable_version(artifact_id: str, failure: str, declared: str) -> str:
    if len(declared) == 64 and all(character in "0123456789abcdef" for character in declared):
        return declared
    return sha256(canonical_json({"source_artifact_id": artifact_id, "availability": failure})).hexdigest()


def build_safe_development_source_inventory_v2(
    *,
    snapshot_db_path: str | Path,
    snapshot_db_sha256: str,
    artifact_root: str | Path,
    artifact_manifest_path: str | Path,
    artifact_manifest_sha256: str,
    protection: ProtectedSourceProjection,
    existing_pilot_video_counts: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    db_path = Path(snapshot_db_path).resolve()
    root = Path(artifact_root).resolve()
    manifest_path = Path(artifact_manifest_path).resolve()
    if _sha(db_path) != snapshot_db_sha256 or _sha(manifest_path) != artifact_manifest_sha256:
        raise SafeInventoryError("frozen authority identity mismatch")
    artifacts = _manifest(manifest_path)
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT id, platform, source_id, part, subtitle_source, subtitle_language, "
            "raw_subtitle_path, duration_seconds FROM videos ORDER BY id"
        ).fetchall()
    finally:
        connection.close()

    inventory: list[dict[str, Any]] = []
    excluded = 0
    unknown = 0
    all_availability: Counter[str] = Counter()
    for row in rows:
        logical_video = str(row["source_id"] or "").strip()
        if not logical_video:
            unknown += 1
            continue
        reference = SourceArtifactReference(
            platform=str(row["platform"]), source_id=logical_video, part=int(row["part"]),
            source_type=_source_type(row["subtitle_source"]),
            source_language=str(row["subtitle_language"] or "unknown"),
            artifact_path=str(row["raw_subtitle_path"] or (root / logical_video / "subtitle-raw.json")),
            source_lineage=_source_type(row["subtitle_source"]),
        )
        artifact_id = make_source_artifact_id(reference)
        protected_aliases = {logical_video, str(row["id"])}
        if artifact_id in protection.source_identities or protected_aliases & protection.video_identities:
            excluded += 1
            continue
        authority = artifacts.get(int(row["id"]), {})
        declared = str(authority.get("sha256") or "").lower()
        raw_path_value = str(row["raw_subtitle_path"] or "")
        raw_path = Path(raw_path_value).resolve() if raw_path_value else root / logical_video / "subtitle-raw.json"
        availability = "available"
        failure: str | None = None
        parsed = None
        if not raw_path_value or authority.get("status") != "ok":
            availability, failure = "missing", "raw_subtitle_not_declared"
        elif root not in raw_path.parents or raw_path.name != "subtitle-raw.json":
            availability, failure = "unsupported", "artifact_path_outside_frozen_root"
        elif not raw_path.is_file():
            availability, failure = "missing", "raw_subtitle_missing"
        else:
            try:
                actual = _sha(raw_path)
            except OSError:
                availability, failure = "unreadable", "source_unreadable"
            else:
                if not declared or actual != declared:
                    availability, failure = "version_mismatch", "source_version_mismatch"
                else:
                    try:
                        parsed = load_source_artifact(reference, expected_source_version=declared)
                    except Exception:
                        availability, failure = "unreadable", "source_unreadable"
                    else:
                        if parsed.validation_status not in {"valid_single_run", "valid_multiple_runs"}:
                            availability, failure = "invalid_timeline", parsed.validation_status
        version = declared if availability == "available" else _unavailable_version(artifact_id, failure or availability, declared)
        safe_id = _safe_id(snapshot_db_sha256, artifact_id, version)
        timeline_ids = [run.timeline_run_id for run in parsed.timeline_runs] if parsed else []
        segment_count = len(parsed.segments) if parsed else 0
        duration = max((segment.end_time for segment in parsed.segments), default=0.0) if parsed else 0.0
        pilot_count = int((existing_pilot_video_counts or {}).get(logical_video, 0))
        record: dict[str, Any] = {
            "safe_source_id": safe_id,
            "platform": str(row["platform"]),
            "video_id": logical_video,
            "source_artifact_id": artifact_id,
            "source_version": version,
            "source_type": reference.source_type,
            "source_language": reference.source_language,
            "source_availability": availability,
            "source_failure_code": failure,
            "timeline_run_ids": timeline_ids,
            "segment_count": segment_count,
            "raw_duration_seconds": duration,
            "export_relative_path": f"sources/{safe_id}/subtitle-raw.json" if availability == "available" else None,
            "used_in_existing_pilot": pilot_count > 0,
            "existing_pilot_case_count": pilot_count,
            "development_case_construction_allowed": True,
            "inventory_version": INVENTORY_VERSION,
        }
        record["source_record_digest"] = sha256(canonical_json(record)).hexdigest()
        if set(record) != INVENTORY_FIELDS:
            raise SafeInventoryError("inventory field whitelist violation")
        inventory.append(record)
        all_availability[availability] += 1
    inventory.sort(key=lambda item: item["safe_source_id"])
    manifest = {
        "inventory_version": INVENTORY_VERSION,
        "snapshot_db_path": str(db_path),
        "snapshot_db_sha256": snapshot_db_sha256,
        "artifact_root": str(root),
        "artifact_manifest_path": str(manifest_path),
        "artifact_manifest_sha256": artifact_manifest_sha256,
        "source_count": len(inventory),
        "inventory_sha256": sha256(b"".join(canonical_json(item) + b"\n" for item in inventory)).hexdigest(),
    }
    audit = {
        **protection.aggregate(excluded_source_count=excluded, unknown_count=unknown),
        "enumerated_source_count": len(rows),
        "safe_source_count": len(inventory),
        "availability_distribution": dict(sorted(all_availability.items())),
        "protected_source_overlap": 0,
        "unknown_protection_state_included": 0,
        "candidate_case_count": 0,
        "model_call_count": 0,
    }
    return inventory, manifest, audit


def write_inventory_jsonl(records: list[dict[str, Any]], path: str | Path) -> None:
    Path(path).write_bytes(b"".join(canonical_json(record) + b"\n" for record in records))


def write_canonical_json(value: object, path: str | Path) -> None:
    Path(path).write_bytes(canonical_json(value) + b"\n")

