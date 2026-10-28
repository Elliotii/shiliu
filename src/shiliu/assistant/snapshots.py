from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from shiliu.artifacts import ArtifactStore
from shiliu.db import Database, utc_now, collection_dto
from shiliu.storage.artifacts import ArtifactPrepareStale
from shiliu.storage.fences import lock_workspace


class SourceChangedDuringCapture(RuntimeError):
    pass


@dataclass(frozen=True)
class CapturedSource:
    revision: str
    snapshot_ref: str
    snapshot: dict[str, Any]


class SourceSnapshotStore:
    def __init__(
        self, db: Database, artifacts: ArtifactStore, root: Path | None = None
    ) -> None:
        self.db = db
        self.artifacts = artifacts
        self.root = artifacts.root

    def capture(
        self,
        video_id: int,
        *,
        principal_id: str | None = None,
        publish_guard: Callable[[Any], None] | None = None,
    ) -> CapturedSource:
        principal_id = principal_id or self.db.context.user_id
        if principal_id != self.db.context.user_id:
            raise PermissionError("source_snapshot_owner_mismatch")
        for attempt in range(3):
            before = self._state(video_id)
            snapshot = self._build_snapshot(before)
            payload = _canonical_json(snapshot)
            descriptor = self.artifacts.objects.prepare(
                payload, media_type="application/json"
            )
            try:
                with self.db.connect(guard=True) as conn:
                    if publish_guard is not None:
                        publish_guard(conn)
                    current = self._state(video_id, conn=conn)
                    if before["capture_epoch"] != current[
                        "capture_epoch"
                    ] or self._capture_token(before) != self._capture_token(current):
                        raise SourceChangedDuringCapture(
                            "source_changed_during_capture"
                        )
                    self.db._video(conn, video_id, lock=True)
                    ref = self.artifacts.objects.publish(
                        conn,
                        f"assistant-source:{principal_id}:{video_id}",
                        snapshot["revision"],
                        descriptor,
                        video_id=video_id,
                    )
                    self._commit(conn, snapshot, principal_id, ref)
                return CapturedSource(snapshot["revision"], ref, snapshot)
            except (ArtifactPrepareStale, SourceChangedDuringCapture):
                if attempt == 2:
                    raise
        raise AssertionError("unreachable")

    def _state(self, video_id, *, conn=None):
        def read(c):
            video = self.db.get_video(video_id, conn=c)
            if video is None:
                raise KeyError(video_id)
            memberships = c.execute(
                "SELECT m.source_id,m.favorite_time,m.first_observed_at,m.removed_at,s.folder_id,s.folder_title,s.status "
                "FROM shiliu.video_source_memberships m JOIN shiliu.favorite_sources s ON "
                "(m.workspace_id,m.source_id)=(s.workspace_id,s.id) WHERE m.workspace_id=%s AND m.video_id=%s ORDER BY m.source_id",
                (self.db.workspace_id, video_id),
            ).fetchall()
            notes = self.db.list_notes_for_videos([video_id], conn=c)[video_id]
            epoch = c.execute(
                "SELECT dependency_epoch FROM shiliu.workspace_guards WHERE workspace_id=%s",
                (self.db.workspace_id,),
            ).fetchone()["dependency_epoch"]
            return {
                "video": video,
                "memberships": [collection_dto(r) for r in memberships],
                "notes": notes,
                "capture_epoch": epoch,
            }

        if conn is not None:
            return read(conn)
        with self.db.pg.transaction(read_only=True, isolation="repeatable read") as c:
            return read(c)

    @staticmethod
    def _capture_token(state: dict[str, Any]) -> tuple[Any, ...]:
        video = state["video"]
        return (
            video.get("updated_at"),
            video.get("active_revision"),
            video.get("raw_subtitle_path"),
            video.get("transcript_path"),
            video.get("summary_path"),
            tuple(
                (m["source_id"], m["favorite_time"], m["removed_at"], m["status"])
                for m in state["memberships"]
            ),
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
                text = self.artifacts.read_text(str(candidate))
            except (OSError, ValueError, UnicodeError):
                raise SourceChangedDuringCapture("source_material_unavailable")
            material_text[kind] = text
        material_hashes = {
            kind: _sha256(text.encode("utf-8")) for kind, text in material_text.items()
        }
        notes = [
            {
                "id": row["id"],
                "content": row["content"],
                "updated_at": row["updated_at"],
            }
            for row in state["notes"]
        ]
        metadata = {
            key: video.get(key)
            for key in (
                "id",
                "platform",
                "source_id",
                "part",
                "title",
                "uploader",
                "uploader_id",
                "description",
                "description_links_json",
                "video_url",
                "cid",
                "part_title",
                "duration_seconds",
                "page_count",
                "published_at",
                "metadata_observed_at",
                "subtitle_source",
                "active_revision",
                "discovered_at",
            )
        }
        memberships = [
            {
                key: row.get(key)
                for key in (
                    "source_id",
                    "folder_id",
                    "folder_title",
                    "favorite_time",
                    "first_observed_at",
                    "removed_at",
                    "status",
                )
            }
            for row in state["memberships"]
        ]
        stable_metadata = dict(metadata)
        stable_metadata.pop("metadata_observed_at", None)
        metadata_hash = _json_hash(stable_metadata)
        content_hash = _json_hash(
            {
                "material_hashes": material_hashes,
                "notes": notes,
                "active_revision": video.get("active_revision"),
            }
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

    def _commit(self, conn, snapshot, principal_id, ref):
        video_id = int(snapshot["metadata"]["id"])
        head = conn.execute(
            "INSERT INTO shiliu.assistant_source_heads(workspace_id,principal_id,video_id,metadata_hash,content_hash,"
            "membership_hash,current_revision,updated_at) VALUES(%s,%s,%s,%s,%s,%s,NULL,clock_timestamp()) "
            "ON CONFLICT(principal_id,video_id) DO UPDATE SET metadata_hash=excluded.metadata_hash,content_hash=excluded.content_hash,"
            "membership_hash=excluded.membership_hash,updated_at=excluded.updated_at RETURNING id",
            (
                self.db.workspace_id,
                principal_id,
                video_id,
                snapshot["metadata_hash"],
                snapshot["content_hash"],
                snapshot["membership_hash"],
            ),
        ).fetchone()
        conn.execute(
            "INSERT INTO shiliu.assistant_source_revisions(workspace_id,video_id,revision,head_id,metadata_hash,content_hash,"
            "membership_hash,snapshot_ref,coverage,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp()) "
            "ON CONFLICT(revision) DO NOTHING",
            (
                self.db.workspace_id,
                video_id,
                snapshot["revision"],
                head["id"],
                snapshot["metadata_hash"],
                snapshot["content_hash"],
                snapshot["membership_hash"],
                ref,
                snapshot["coverage"],
            ),
        )

        conn.execute(
            "UPDATE shiliu.assistant_source_heads SET current_revision=%s WHERE workspace_id=%s AND id=%s",
            (snapshot["revision"], self.db.workspace_id, head["id"]),
        )

        conn.execute(
            "UPDATE shiliu.assistant_wiki_proposals SET status='stale',decided_at=clock_timestamp(),updated_at=clock_timestamp(),payload_json=jsonb_set(payload_json,'{decision_reason}','\"source_revision_changed\"') WHERE workspace_id=%s AND principal_id=%s AND kind='source_patch' AND status='pending' AND EXISTS (SELECT 1 FROM shiliu.assistant_source_revisions r WHERE r.workspace_id=assistant_wiki_proposals.workspace_id AND r.video_id=%s AND r.revision<>%s AND (r.revision=payload_json->>'revision' OR (payload_json->'source_revisions') ? r.revision))",
            (self.db.workspace_id, principal_id, video_id, snapshot["revision"]),
        )

    def load(self, video_id, revision):
        with self.db.connect(read_only=True) as c:
            row = c.execute(
                "SELECT r.snapshot_ref FROM shiliu.assistant_source_revisions r JOIN shiliu.assistant_source_heads h "
                "ON (h.workspace_id,h.id)=(r.workspace_id,r.head_id) WHERE r.workspace_id=%s AND r.video_id=%s AND r.revision=%s "
                "AND h.principal_id=%s",
                (self.db.workspace_id, video_id, revision, self.db.context.user_id),
            ).fetchone()
        if row is None:
            raise KeyError(revision)
        ref = row["snapshot_ref"]
        if ref.startswith("artifact:"):
            raw = self.artifacts.read_bytes(ref)
        else:
            # Explicit W04 historical manifest binding; never read a naked path.
            raw = self.artifacts.objects.read_bytes(
                logical_key="source_snapshot:" + revision, source_version=revision
            )
        return CapturedSource(revision, ref, json.loads(raw))


def _coverage(materials: dict[str, str]) -> str:
    if materials.get("raw_subtitle"):
        return "full_available_transcript"
    if materials.get("transcript"):
        return "partial_transcript"
    if materials.get("summary"):
        return "summary_based"
    return "metadata_only"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _json_hash(value: Any) -> str:
    return _sha256(_canonical_json(value))


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
