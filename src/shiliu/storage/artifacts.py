"""Immutable bytes with transaction-bound manifests and guarded garbage collection.

prepare is deliberately outside DB transactions. Its descriptor is not a pin.
publish rechecks the physical identity under the same workspace guard as GC and
keeps that guard until the caller commits. No external operation is replayed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from hashlib import sha256
from contextlib import contextmanager
import fcntl
import os
import re
import stat
import tempfile
from typing import Callable

from shiliu.storage.fences import lock_workspace


class ArtifactError(RuntimeError):
    code = "artifact_integrity_error"


class ArtifactPrepareStale(ArtifactError):
    code = "artifact_prepare_stale"

    def __init__(self):
        super().__init__(self.code)


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int

    @classmethod
    def of(cls, value):
        return cls(
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )


@dataclass(frozen=True)
class ObjectDescriptor:
    relative_key: str
    sha256: str
    byte_size: int
    identity: FileIdentity
    media_type: str = "application/octet-stream"


@dataclass(frozen=True)
class GCCandidate:
    descriptor: ObjectDescriptor
    mtime_ns: int


def artifact_version_id(workspace_id, logical_key, version):
    import json

    raw = json.dumps(
        [workspace_id, logical_key, version], ensure_ascii=False, separators=(",", ":")
    ).encode()
    return "artifact_" + sha256(raw).hexdigest()


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class ArtifactStore:
    def __init__(self, root: Path, db, context=None):
        self.root = Path(root).absolute()
        self.db = db.pg if hasattr(db, "pg") else db
        self.context = context if context is not None else db.context
        if not self.root.is_absolute():
            raise ArtifactError("artifact_root_absolute_required")
        self.root.mkdir(parents=True, exist_ok=True)
        self._safe_components(self.root)
        self.namespace = self.context.workspace_id
        if not re.fullmatch(r"[A-Za-z0-9:_-]+", self.namespace):
            raise ArtifactError("artifact_workspace_namespace_unsafe")
        self.workspace_root = self.root / self.namespace
        self._mkdir(self.workspace_root / "objects")

    def _safe_components(self, path):
        if not path.is_relative_to(self.root) and path != self.root:
            raise ArtifactError("artifact_path_outside_root")
        # Check every existing ancestor, including the explicit root's parents.
        for component in [*reversed(path.parents), path]:
            try:
                info = component.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode):
                raise ArtifactError("artifact_symlink_rejected")
            if component != path and not stat.S_ISDIR(info.st_mode):
                raise ArtifactError("artifact_parent_not_directory")

    def _mkdir(self, path):
        self._safe_components(path)
        path.mkdir(parents=True, exist_ok=True)
        self._safe_components(path)
        # Persist directories themselves and each new parent entry.
        for directory in [path, *path.parents]:
            if not directory.is_relative_to(self.root):
                break
            _fsync_dir(directory)

    def path_for_key(self, key):
        relative = PurePosixPath(key)
        if relative.is_absolute() or ".." in relative.parts or str(relative) != key:
            raise ArtifactError("artifact_unsafe_key")
        if not key.startswith(self.namespace + "/objects/"):
            raise ArtifactError("artifact_workspace_key_mismatch")
        path = self.root / key
        self._safe_components(path)
        return path

    def _stat(self, path):
        self._safe_components(path)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ArtifactError("artifact_regular_unlinked_file_required")
        return info

    @contextmanager
    def _prepare_lock(self):
        path = self.workspace_root / ".prepare.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _verified_descriptor(self, path, digest, size, media_type):
        before = self._stat(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            opened = os.fstat(fd)
            hasher = sha256()
            length = 0
            while block := os.read(fd, 1024 * 1024):
                hasher.update(block)
                length += len(block)
            after = os.fstat(fd)
        finally:
            os.close(fd)
        try:
            current = self._stat(path)
        except FileNotFoundError:
            raise ArtifactPrepareStale() from None
        if (
            FileIdentity.of(before) != FileIdentity.of(opened)
            or FileIdentity.of(opened) != FileIdentity.of(after)
            or FileIdentity.of(after) != FileIdentity.of(current)
        ):
            raise ArtifactPrepareStale()
        if hasher.hexdigest() != digest or length != size:
            raise ArtifactError("artifact_hash_or_size_mismatch")
        return ObjectDescriptor(
            path.relative_to(self.root).as_posix(),
            digest,
            size,
            FileIdentity.of(current),
            media_type,
        )

    def prepare(self, content: bytes, *, media_type="application/octet-stream"):
        if not isinstance(content, bytes):
            raise TypeError("Artifact content must be bytes")
        digest = sha256(content).hexdigest()
        directory = self.workspace_root / "objects"
        self._mkdir(directory)
        path = directory / digest
        with self._prepare_lock():
            if not path.exists():
                # lstat detects a dangling symlink even though exists() is false.
                if path.is_symlink():
                    raise ArtifactError("artifact_symlink_rejected")
                fd, name = tempfile.mkstemp(prefix=".prepare-", dir=directory)
                temporary = Path(name)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.rename(temporary, path)
                    _fsync_dir(directory)
                finally:
                    temporary.unlink(missing_ok=True)
            return self._verified_descriptor(path, digest, len(content), media_type)

    def _recheck(self, descriptor):
        if not re.fullmatch("[0-9a-f]{64}", descriptor.sha256):
            raise ArtifactError("artifact_invalid_hash")
        expected = f"{self.namespace}/objects/{descriptor.sha256}"
        if descriptor.relative_key != expected:
            raise ArtifactError("artifact_key_hash_mismatch")
        path = self.path_for_key(descriptor.relative_key)
        try:
            info = self._stat(path)
        except FileNotFoundError:
            raise ArtifactPrepareStale() from None
        if (
            descriptor.byte_size != info.st_size
            or descriptor.identity != FileIdentity.of(info)
        ):
            raise ArtifactPrepareStale()
        return path

    def publish(self, conn, logical_key, version, descriptor, *, video_id=None):
        lock_workspace(conn, self.context)
        self._recheck(descriptor)
        workspace = self.context.workspace_id
        old = conn.execute(
            "SELECT relative_key,byte_size FROM shiliu.artifact_objects WHERE workspace_id=%s AND sha256=%s",
            (workspace, descriptor.sha256),
        ).fetchone()
        if old and (
            old["relative_key"] != descriptor.relative_key
            or old["byte_size"] != descriptor.byte_size
        ):
            raise ArtifactError("artifact_object_conflict")
        conn.execute(
            "INSERT INTO shiliu.artifact_objects(workspace_id,sha256,relative_key,byte_size,media_type,created_at) "
            "VALUES(%s,%s,%s,%s,%s,clock_timestamp()) ON CONFLICT(workspace_id,sha256) DO NOTHING",
            (
                workspace,
                descriptor.sha256,
                descriptor.relative_key,
                descriptor.byte_size,
                descriptor.media_type,
            ),
        )
        identity = artifact_version_id(workspace, logical_key, version)
        previous = conn.execute(
            "SELECT * FROM shiliu.artifact_versions WHERE workspace_id=%s AND logical_key=%s AND source_version=%s",
            (workspace, logical_key, version),
        ).fetchone()
        if previous and (
            previous["id"] != identity
            or previous["object_sha256"] != descriptor.sha256
            or previous["video_id"] != video_id
        ):
            # Imported historical IDs are valid and preserved, as long as binding matches.
            if (
                previous["object_sha256"] != descriptor.sha256
                or previous["video_id"] != video_id
            ):
                raise ArtifactError("artifact_version_conflict")
            identity = previous["id"]
        conn.execute(
            "INSERT INTO shiliu.artifact_versions(id,workspace_id,video_id,logical_key,source_version,object_sha256,created_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,clock_timestamp()) ON CONFLICT(workspace_id,logical_key,source_version) DO NOTHING",
            (identity, workspace, video_id, logical_key, version, descriptor.sha256),
        )
        conn.execute(
            "INSERT INTO shiliu.artifact_heads(workspace_id,logical_key,artifact_version_id) VALUES(%s,%s,%s) "
            "ON CONFLICT(workspace_id,logical_key) DO UPDATE SET artifact_version_id=excluded.artifact_version_id",
            (workspace, logical_key, identity),
        )
        return "artifact:" + identity

    def manifest(
        self,
        *,
        version_id=None,
        logical_key=None,
        source_version=None,
        head=False,
        conn=None,
    ):
        if version_id is not None:
            where = "v.id=%s"
            params = [version_id.removeprefix("artifact:")]
        elif logical_key is not None and source_version is not None and not head:
            where = "v.logical_key=%s AND v.source_version=%s"
            params = [logical_key, source_version]
        elif logical_key is not None and head and source_version is None:
            where = (
                "v.logical_key=%s AND EXISTS(SELECT 1 FROM shiliu.artifact_heads h WHERE "
                "(h.workspace_id,h.logical_key,h.artifact_version_id)=(v.workspace_id,v.logical_key,v.id))"
            )
            params = [logical_key]
        else:
            raise ValueError(
                "Resolve requires an explicit historical version or explicit head"
            )

        def query(c):
            row = c.execute(
                "SELECT v.*,o.relative_key,o.byte_size,o.media_type FROM shiliu.artifact_versions v "
                "JOIN shiliu.artifact_objects o ON (o.workspace_id,o.sha256)=(v.workspace_id,v.object_sha256) "
                "WHERE v.workspace_id=%s AND " + where,
                [self.context.workspace_id, *params],
            ).fetchone()
            if row is None:
                raise FileNotFoundError("artifact_version_missing")
            return row

        if conn is not None:
            return query(conn)
        with self.db.read() as c:
            return query(c)

    def resolve(self, **kwargs):
        row = self.manifest(**kwargs)
        path = self.path_for_key(row["relative_key"])
        self._verified_descriptor(
            path, row["object_sha256"], row["byte_size"], row["media_type"]
        )
        return path

    def read_bytes(self, **kwargs):
        # Resolve verifies bytes; verify the same opened identity on the final read.
        row = self.manifest(**kwargs)
        path = self.path_for_key(row["relative_key"])
        before = self._stat(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            with os.fdopen(fd, "rb") as stream:
                raw = stream.read()
                after = os.fstat(stream.fileno())
        except OSError:
            raise ArtifactError("artifact_unreadable") from None
        if (
            FileIdentity.of(before) != FileIdentity.of(after)
            or len(raw) != row["byte_size"]
            or sha256(raw).hexdigest() != row["object_sha256"]
        ):
            raise ArtifactError("artifact_hash_or_size_mismatch")
        return raw

    def publish_bytes(
        self,
        content,
        logical_key,
        version,
        writer: Callable,
        *,
        video_id=None,
        media_type="application/octet-stream",
    ):
        """Retry only preparation/publication, exactly three total attempts."""
        for attempt in range(3):
            descriptor = self.prepare(content, media_type=media_type)
            try:
                with self.db.transaction() as conn:
                    lock_workspace(conn, self.context)
                    # writer revalidates business/run/epoch each attempt before
                    # publishing and writes its references in this transaction.
                    result = writer(conn, descriptor)
                return result
            except ArtifactPrepareStale:
                if attempt == 2:
                    raise
        raise AssertionError("unreachable")

    def gc_candidates(self, *, grace_seconds=86400):
        if grace_seconds < 0:
            raise ValueError("Invalid artifact grace")
        result = []
        for path in (self.workspace_root / "objects").glob("*"):
            if path.name.startswith("."):
                continue
            info = self._stat(path)
            if not re.fullmatch("[0-9a-f]{64}", path.name):
                raise ArtifactError("artifact_invalid_object_name")
            descriptor = self._verified_descriptor(
                path, path.name, info.st_size, "application/octet-stream"
            )
            result.append(GCCandidate(descriptor, info.st_mtime_ns))
        return result

    def gc(self, *, dry_run=True, grace_seconds=86400, candidates=None):
        if grace_seconds < 0:
            raise ValueError("Invalid artifact grace")
        result = []
        for candidate in (
            self.gc_candidates(grace_seconds=grace_seconds)
            if candidates is None
            else candidates
        ):
            descriptor = candidate.descriptor
            with self.db.transaction() as c:
                lock_workspace(c, self.context)
                try:
                    path = self._recheck(descriptor)
                except ArtifactPrepareStale:
                    result.append((descriptor.relative_key, "changed_or_missing"))
                    continue
                old = c.execute(
                    "SELECT to_timestamp(%s)<clock_timestamp()-%s*interval '1 second' AS old",
                    (candidate.mtime_ns / 1e9, grace_seconds),
                ).fetchone()["old"]
                if not old:
                    result.append((descriptor.relative_key, "young"))
                    continue
                # Every historical manifest retains its object, even with no head.
                refs = c.execute(
                    "SELECT 1 FROM shiliu.artifact_versions WHERE workspace_id=%s AND object_sha256=%s LIMIT 1",
                    (self.context.workspace_id, descriptor.sha256),
                ).fetchone()
                if refs:
                    result.append((descriptor.relative_key, "referenced"))
                    continue
                if not dry_run:
                    path.unlink()
                    _fsync_dir(path.parent)
                    c.execute(
                        "DELETE FROM shiliu.artifact_objects WHERE workspace_id=%s AND sha256=%s",
                        (self.context.workspace_id, descriptor.sha256),
                    )
                result.append(
                    (descriptor.relative_key, "candidate" if dry_run else "deleted")
                )
        return result
