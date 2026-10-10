from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shiliu.artifacts import ArtifactStore
from shiliu.db import Database, utc_now


class SourceChangedDuringCapture(RuntimeError):
    pass


@dataclass(frozen=True)
class CapturedSource:
    revision: str
    snapshot_ref: str
    snapshot: dict[str, Any]


class SourceSnapshotStore:
    def __init__(self, db: Database, artifacts: ArtifactStore, root: Path) -> None:
        self.db = db
        self.artifacts = artifacts
        self.root = root.resolve()

    def capture(self, video_id: int, *, principal_id: str = "local_operator") -> CapturedSource:
        for _attempt in range(2):
            before = self._state(video_id)
            snapshot = self._build_snapshot(before)
            after = self._state(video_id)
            if self._capture_token(before) != self._capture_token(after):
                continue
            if snapshot["material_hashes"] != self._material_hashes(after["video"]):
                continue
            return self._commit(snapshot, principal_id=principal_id)
        raise SourceChangedDuringCapture(f"video {video_id} changed during source capture")

    def _state(self, video_id: int) -> dict[str, Any]:
        with self.db.connect() as connection:
            video = connection.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
            if video is None:
                raise KeyError(video_id)
            memberships = connection.execute(
                """
                SELECT m.source_id, m.favorite_time, m.first_observed_at, m.removed_at,
                       s.folder_id, s.folder_title, s.status
                FROM video_source_memberships m
                JOIN favorite_sources s ON s.id=m.source_id
                WHERE m.video_id=?
                ORDER BY m.source_id
                """,
                (video_id,),
            ).fetchall()
            notes = connection.execute(
                "SELECT id, content, updated_at FROM video_notes WHERE video_id=? ORDER BY id",
                (video_id,),
            ).fetchall()
        return {
            "video": dict(video),
            "memberships": [dict(row) for row in memberships],
            "notes": [dict(row) for row in notes],
        }

    @staticmethod
    def _capture_token(state: dict[str, Any]) -> tuple[Any, ...]:
        video = state["video"]
        return (
            video.get("updated_at"),
            video.get("active_revision"),
            video.get("raw_subtitle_path"),
            video.get("transcript_path"),
            video.get("summary_path"),
            tuple((m["source_id"], m["favorite_time"], m["removed_at"], m["status"]) for m in state["memberships"]),
            tuple((n["id"], n["updated_at"]) for n in state["notes"]),
        )

    def _build_snapshot(self, state: dict[str, Any]) -> dict[str, Any]:
        video = state["video"]
        material_text: dict[str, str] = {}
        for kind, column in (
            ("raw_subtitle", "raw_subtitle_path"),
            ("transcript", "transcript_path"),
            ("summary", "summary_path"),
        ):
            candidate = video.get(column)
            if not candidate:
                continue
            try:
                path = self.artifacts.managed_file(str(candidate))
                text = path.read_text(encoding="utf-8")
            except (OSError, ValueError, UnicodeError):
                continue
            material_text[kind] = text
        material_hashes = {
            kind: _sha256(text.encode("utf-8"))
            for kind, text in material_text.items()
        }
        notes = [
            {"id": row["id"], "content": row["content"], "updated_at": row["updated_at"]}
            for row in state["notes"]
        ]
        metadata = {
            key: video.get(key)
            for key in (
                "id", "platform", "source_id", "part", "title", "uploader", "uploader_id",
                "description", "description_links_json", "video_url", "cid", "part_title",
                "duration_seconds", "page_count", "published_at", "metadata_observed_at",
                "subtitle_source", "active_revision", "discovered_at",
            )
        }
        memberships = [
            {
                key: row.get(key)
                for key in (
                    "source_id", "folder_id", "folder_title", "favorite_time",
                    "first_observed_at", "removed_at", "status",
                )
            }
            for row in state["memberships"]
        ]
        stable_metadata = dict(metadata)
        stable_metadata.pop("metadata_observed_at", None)
        metadata_hash = _json_hash(stable_metadata)
        content_hash = _json_hash(
            {"material_hashes": material_hashes, "notes": notes, "active_revision": video.get("active_revision")}
        )
        membership_hash = _json_hash(memberships)
        coverage = _coverage(material_text)
        revision = _json_hash(
            {
                "metadata_hash": metadata_hash,
                "content_hash": content_hash,
                "membership_hash": membership_hash,
                "extractor_version": "assistant-source-v1",
            }
        )
        return {
            "schema": "assistant-source-snapshot-v1",
            "revision": revision,
            "metadata_hash": metadata_hash,
            "content_hash": content_hash,
            "membership_hash": membership_hash,
            "coverage": coverage,
            "metadata": metadata,
            "memberships": memberships,
            "materials": material_text,
            "material_hashes": material_hashes,
            "notes": notes,
        }

    def _material_hashes(self, video: dict[str, Any]) -> dict[str, str]:
        values: dict[str, str] = {}
        for kind, column in (
            ("raw_subtitle", "raw_subtitle_path"),
            ("transcript", "transcript_path"),
            ("summary", "summary_path"),
        ):
            candidate = video.get(column)
            if not candidate:
                continue
            try:
                path = self.artifacts.managed_file(str(candidate))
                values[kind] = _sha256(path.read_bytes())
            except (OSError, ValueError):
                continue
        return values

    def _commit(self, snapshot: dict[str, Any], *, principal_id: str) -> CapturedSource:
        payload = _canonical_json(snapshot)
        object_hash = _sha256(payload)
        relative = Path("objects") / "sha256" / object_hash[:2] / f"{object_hash}.json"
        path = self.root / relative
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".json.tmp")
            temporary.write_bytes(payload)
            temporary.replace(path)
        now = utc_now()
        video_id = int(snapshot["metadata"]["id"])
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO assistant_source_heads(
                    principal_id, video_id, metadata_hash, content_hash,
                    membership_hash, current_revision, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(principal_id, video_id) DO UPDATE SET
                    metadata_hash=excluded.metadata_hash,
                    content_hash=excluded.content_hash,
                    membership_hash=excluded.membership_hash,
                    current_revision=excluded.current_revision,
                    updated_at=excluded.updated_at
                """,
                (
                    principal_id, video_id, snapshot["metadata_hash"], snapshot["content_hash"],
                    snapshot["membership_hash"], snapshot["revision"], now,
                ),
            )
            head = connection.execute(
                "SELECT id FROM assistant_source_heads WHERE principal_id=? AND video_id=?",
                (principal_id, video_id),
            ).fetchone()
            connection.execute(
                """
                INSERT OR IGNORE INTO assistant_source_revisions(
                    revision, head_id, metadata_hash, content_hash, membership_hash,
                    snapshot_ref, coverage, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot["revision"], int(head["id"]), snapshot["metadata_hash"],
                    snapshot["content_hash"], snapshot["membership_hash"],
                    str(relative), snapshot["coverage"], now,
                ),
            )
        return CapturedSource(
            revision=str(snapshot["revision"]), snapshot_ref=str(relative), snapshot=snapshot
        )


def _coverage(materials: dict[str, str]) -> str:
    if materials.get("raw_subtitle"):
        return "full_available_transcript"
    if materials.get("transcript"):
        return "partial_transcript"
    if materials.get("summary"):
        return "summary_based"
    return "metadata_only"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _json_hash(value: Any) -> str:
    return _sha256(_canonical_json(value))


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
