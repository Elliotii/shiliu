"""Collection Artifact preparation batches and manifest readers.

All formal writes use a batch and the caller's business transaction. The scratch
folder is only for ephemeral audio/provider input; it is never evidence identity.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
import httpx

from shiliu.storage.artifacts import (
    ArtifactStore as Objects,
    ArtifactPrepareStale,
    artifact_version_id,
    ArtifactError,
)
from shiliu.storage.fences import lock_workspace
from shiliu.domain import SubtitleSegment, SummaryResult, TranscriptResult


def json_bytes(value):
    # Preserve the established serialization for new source identities. Imported
    # raw bytes never pass through this serializer.
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


class VideoArtifactBatch:
    def __init__(self, store, video_id):
        self.store = store
        self.video_id = video_id
        self.entries = {}

    def _save(self, name, raw, version=None, media_type="application/json"):
        logical = f"video:{self.video_id}:{name}"
        version = version or sha256(raw).hexdigest()
        descriptor = self.store.objects.prepare(raw, media_type=media_type)
        ref = "artifact:" + artifact_version_id(
            self.store.db.workspace_id, logical, version
        )
        self.entries[(logical, version)] = (raw, descriptor, ref)
        return ref

    def save_metadata(self, bundle):
        return self._save(
            "metadata.json", json_bytes(bundle.model_dump(mode="json", by_alias=True))
        )

    def save_raw_subtitle_bytes(self, raw):
        # JSON must be readable for text rendering, but authoritative bytes stay exact.
        segments = [SubtitleSegment.model_validate(item) for item in json.loads(raw)]
        from shiliu.artifacts import format_timestamp

        version = sha256(raw).hexdigest()
        lines = [
            f"[{format_timestamp(s.start)} --> {format_timestamp(s.end)}] {s.content}"
            for s in segments
        ]
        text = ("\n".join(lines) + ("\n" if lines else "")).encode()
        return (
            self._save("subtitle-raw.json", raw, version),
            self._save("subtitle-raw.txt", text, version, "text/plain"),
        )

    def save_raw_subtitle(self, bvid, segments):
        return self.save_raw_subtitle_bytes(
            json_bytes([s.model_dump(mode="json", by_alias=True) for s in segments])
        )

    def save_asr_raw(self, bvid, payload):
        return self._save("asr-raw.json", json_bytes(payload))

    def save_transcript(self, bvid, transcript, *, revision=None):
        from shiliu.artifacts import render_transcript_markdown

        suffix = f".{revision}" if revision else ""
        raw = json_bytes(transcript.model_dump(mode="json"))
        version = sha256(raw).hexdigest()
        return (
            self._save(f"transcript{suffix}.json", raw, version),
            self._save(
                f"transcript{suffix}.md",
                render_transcript_markdown(transcript).encode(),
                version,
                "text/markdown",
            ),
        )

    def save_summary(self, bvid, summary, *, revision=None):
        from shiliu.artifacts import render_summary_markdown

        suffix = f".{revision}" if revision else ""
        raw = json_bytes(summary.model_dump(mode="json"))
        version = sha256(raw).hexdigest()
        return (
            self._save(f"summary{suffix}.json", raw, version),
            self._save(
                f"summary{suffix}.md",
                render_summary_markdown(summary).encode(),
                version,
                "text/markdown",
            ),
        )

    def save_generation_provenance(
        self, bvid, artifact_kind, metadata, *, revision=None
    ):
        if artifact_kind not in {"transcript", "summary"}:
            raise ValueError("Invalid generation kind")
        suffix = f".{revision}" if revision else ""
        return self._save(
            f"{artifact_kind}{suffix}.provenance.json", json_bytes(metadata)
        )

    def publish(self, conn):
        for (logical, version), (_, descriptor, ref) in self.entries.items():
            actual = self.store.objects.publish(
                conn, logical, version, descriptor, video_id=self.video_id
            )
            if actual != ref:
                raise ArtifactError("artifact_reference_binding_changed")

    def commit(self, writer, *, validate=None):
        for attempt in range(3):
            try:
                with self.store.db.connect(guard=True) as conn:
                    if validate:
                        validate(conn)
                    self.publish(conn)
                    result = writer(conn)
                return result
            except ArtifactPrepareStale:
                if attempt == 2:
                    raise
                # Retained bytes only. Never execute provider/ASR again.
                self.entries = {
                    key: (
                        raw,
                        self.store.objects.prepare(
                            raw, media_type=descriptor.media_type
                        ),
                        ref,
                    )
                    for key, (raw, descriptor, ref) in self.entries.items()
                }
        raise AssertionError("unreachable")


class ArtifactStore:
    def __init__(self, root: Path, db):
        self.db = db
        self.objects = Objects(root, db)
        self.root = self.objects.root
        self.videos_dir = self.root / "scratch" / self.objects.namespace
        self.objects._mkdir(self.videos_dir)

    def video_dir(self, bvid):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", bvid):
            raise ValueError("Invalid source ID")
        path = self.videos_dir / bvid
        self.objects._mkdir(path)
        return path

    def batch(self, video_id):
        if self.db.get_video(video_id) is None:
            raise KeyError(video_id)
        return VideoArtifactBatch(self, video_id)

    def managed_file(self, candidate):
        if not str(candidate).startswith("artifact:"):
            raise ArtifactError("artifact_manifest_reference_required")
        return self.objects.resolve(version_id=str(candidate))

    def read_bytes(self, candidate):
        if not str(candidate).startswith("artifact:"):
            raise ArtifactError("artifact_manifest_reference_required")
        return self.objects.read_bytes(version_id=str(candidate))

    def read_text(self, candidate):
        return self.read_bytes(candidate).decode("utf-8")

    def _video_id(self, bvid):
        video = self.db.get_video_by_source(bvid)
        if video is None:
            raise KeyError(bvid)
        return video["id"]

    def read_named(self, bvid, name, *, version=None):
        logical = f"video:{self._video_id(bvid)}:{name}"
        return self.objects.read_bytes(
            logical_key=logical, source_version=version, head=version is None
        )

    def load_transcript(self, bvid, *, revision=None):
        return TranscriptResult.model_validate_json(
            self.read_named(
                bvid, "transcript" + (f".{revision}" if revision else "") + ".json"
            )
        )

    def load_summary(self, bvid, *, revision=None):
        return SummaryResult.model_validate_json(
            self.read_named(
                bvid, "summary" + (f".{revision}" if revision else "") + ".json"
            )
        )

    def load_generation_provenance(self, bvid, artifact_kind, *, revision=None):
        try:
            return json.loads(
                self.read_named(
                    bvid,
                    artifact_kind
                    + (f".{revision}" if revision else "")
                    + ".provenance.json",
                )
            )
        except FileNotFoundError:
            return {
                "provenance_status": "legacy_unknown",
                "provider": "unknown",
                "model": "unknown",
                "prompt_version": "unknown",
                "schema": "unknown",
                "generated_at": None,
            }

    def raw_bytes(self, candidate, *, expected_source_version=None):
        row = self.objects.manifest(version_id=str(candidate))
        if row["logical_key"].endswith(":subtitle-raw.txt"):
            logical = row["logical_key"][:-4] + ".json"
            version = expected_source_version or row["source_version"]
            try:
                return self.objects.read_bytes(logical_key=logical, source_version=version)
            except FileNotFoundError:
                if expected_source_version is not None:
                    raise
                # Imported legacy files have independent byte-hash versions for
                # TXT and JSON. Resolve only the current pair and prove the TXT
                # is precisely the established projection of those JSON bytes.
                # Explicit historical JSON versions never fall back to a head.
                text_head = self.objects.manifest(logical_key=row["logical_key"], head=True)
                raw_head = self.objects.manifest(logical_key=logical, head=True)
                if (text_head["id"] != row["id"] or row["source_version"] != row["object_sha256"]
                        or raw_head["source_version"] != raw_head["object_sha256"]
                        or raw_head["video_id"] != row["video_id"]):
                    raise ArtifactError("legacy_raw_pair_identity_mismatch")
                raw = self.objects.read_bytes(version_id=raw_head["id"])
                segments = [SubtitleSegment.model_validate(s) for s in json.loads(raw)]
                from shiliu.artifacts import format_timestamp

                lines = [f"[{format_timestamp(s.start)} --> {format_timestamp(s.end)}] {s.content}" for s in segments]
                rendered = ("\n".join(lines) + ("\n" if lines else "")).encode()
                if rendered != self.objects.read_bytes(version_id=row["id"]):
                    raise ArtifactError("legacy_raw_pair_projection_mismatch")
                return raw
        if (
            expected_source_version is not None
            and row["source_version"] != expected_source_version
        ):
            # Explicitly address history of this logical source, never its head.
            return self.objects.read_bytes(
                logical_key=row["logical_key"], source_version=expected_source_version
            )
        return self.objects.read_bytes(version_id=str(candidate))

    def generated_json_bytes(self, candidate):
        """Resolve the JSON paired with an exact generated artifact version.

        A missing historical pair is an explicit unavailable artifact. Never
        substitute a newer logical head for a formal row's pinned reference.
        """
        row = self.objects.manifest(version_id=str(candidate))
        logical = row["logical_key"]
        if logical.endswith(".md"):
            return self.objects.read_bytes(
                logical_key=logical[:-3] + ".json", source_version=row["source_version"]
            )
        if not logical.endswith(".json"):
            raise ArtifactError("generated_json_manifest_required")
        return self.objects.read_bytes(version_id=str(candidate))

    def download_cover(self, bvid, cover_url, *, batch=None):
        if not cover_url:
            return None
        url = "https:" + cover_url if cover_url.startswith("//") else cover_url
        try:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                response = client.get(
                    url, headers={"User-Agent": "Mozilla/5.0 Shiliu/0.1"}
                )
                response.raise_for_status()
                if not response.content:
                    return None
                own_batch = batch is None
                batch = batch or self.batch(self._video_id(bvid))
                ref = batch._save(
                    "cover.jpg", response.content, media_type="image/jpeg"
                )
                if own_batch:
                    batch.commit(
                        lambda conn: self.db.update_video(
                            batch.video_id,
                            cover_url=cover_url,
                            cover_path=ref,
                            conn=conn,
                        )
                    )
                return ref
        except (httpx.HTTPError, OSError):
            return None

    def export(self, bvid, destination: Path):
        """An explicit read-only layout copy; product never reads this directory."""
        vid = self._video_id(bvid)
        with self.db.pg.read() as conn:
            rows = conn.execute(
                "SELECT logical_key,artifact_version_id FROM shiliu.artifact_heads WHERE workspace_id=%s "
                "AND logical_key LIKE %s",
                (self.db.workspace_id, f"video:{vid}:%"),
            ).fetchall()
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        result = []
        for row in rows:
            name = row["logical_key"].split(":", 2)[2]
            if "/" in name or name in {".", ".."}:
                raise ArtifactError("artifact_export_name_unsafe")
            path = destination / name
            if path.exists() or path.is_symlink():
                raise FileExistsError(path)
            with path.open("xb") as stream:
                stream.write(
                    self.objects.read_bytes(version_id=row["artifact_version_id"])
                )
            path.chmod(0o444)
            result.append(path)
        return result
