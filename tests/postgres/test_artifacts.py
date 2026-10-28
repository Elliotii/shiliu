from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from threading import Event
from pathlib import Path
import os
import time
import pytest

from shiliu.storage.artifacts import ArtifactStore, ArtifactError, ArtifactPrepareStale


@pytest.fixture
def store(collection_db, tmp_path):
    return ArtifactStore(tmp_path / "immutable", collection_db)


def aged(store, raw=b"old orphan"):
    descriptor = store.prepare(raw)
    path = store.path_for_key(descriptor.relative_key)
    os.utime(path, (time.time() - 172800, time.time() - 172800))
    return store.prepare(raw)


def test_legacy_subtitle_pair_uses_verified_json_without_historical_fallback(store, collection_db):
    from shiliu.storage.video_artifacts import ArtifactStore as VideoArtifacts

    video = collection_db.create_video("BVlegacyraw", "合成旧字幕")
    raw = b'[{"from":0,"to":1,"content":"legacy"}]'
    text = b'[00:00:00.000 --> 00:00:01.000] legacy\n'
    raw_object, text_object = store.prepare(raw), store.prepare(text)
    logical = f"video:{video}:subtitle-raw"
    with collection_db.connect(guard=True) as c:
        store.publish(c, logical + ".json", sha256(raw).hexdigest(), raw_object, video_id=video)
        text_ref = store.publish(c, logical + ".txt", sha256(text).hexdigest(), text_object, video_id=video)
    reader = VideoArtifacts(store.root, collection_db)
    assert reader.raw_bytes(text_ref) == raw
    assert reader.raw_bytes(text_ref, expected_source_version=sha256(raw).hexdigest()) == raw
    with pytest.raises(FileNotFoundError):
        reader.raw_bytes(text_ref, expected_source_version="missing-explicit-version")
    changed = raw.replace(b"legacy", b"different")
    descriptor = store.prepare(changed)
    with collection_db.connect(guard=True) as c:
        store.publish(c, logical + ".json", sha256(changed).hexdigest(), descriptor, video_id=video)
    with pytest.raises(ArtifactError, match="projection_mismatch"):
        reader.raw_bytes(text_ref)
    assert reader.raw_bytes(text_ref, expected_source_version=sha256(raw).hexdigest()) == raw


def rows(db):
    with db.pg.read() as c:
        return {
            t: c.execute("SELECT COUNT(*) AS n FROM shiliu." + t).fetchone()["n"]
            for t in [
                "artifact_objects",
                "artifact_versions",
                "artifact_heads",
                "video_notes",
            ]
        }


def test_prepare_history_and_integrity(store, collection_db, tmp_path):
    db = collection_db
    vid = db.create_video("BVartifact", "合成")
    raw = b'[ {"from":0,"to":1,"content":"old"} ]\n'
    old = store.prepare(raw)
    assert old == store.prepare(raw)
    assert old.relative_key.startswith(store.namespace + "/")
    with db.connect(guard=True) as c:
        ref = store.publish(c, "video:1:raw", "old", old, video_id=vid)
    assert store.read_bytes(version_id=ref) == raw
    new = store.prepare(b"new")
    with db.connect(guard=True) as c:
        store.publish(c, "video:1:raw", "new", new, video_id=vid)
    assert store.read_bytes(logical_key="video:1:raw", source_version="old") == raw
    assert store.read_bytes(logical_key="video:1:raw", head=True) == b"new"
    assert all(s == "referenced" for _, s in store.gc(dry_run=False, grace_seconds=0))
    assert store.read_bytes(version_id=ref) == raw
    with pytest.raises(ValueError):
        store.resolve(logical_key="video:1:raw")
    with pytest.raises(ArtifactError):
        store.path_for_key("../escape")
    with pytest.raises(ArtifactError):
        store.path_for_key("workspaces/wrong/objects/sha256/a/b")
    path = store.path_for_key(old.relative_key)
    path.unlink()
    path.symlink_to(tmp_path / "outside")
    with pytest.raises(ArtifactError):
        store.prepare(raw)
    with pytest.raises(ArtifactError):
        store.resolve(version_id=ref)


def test_c07_gc_first_rolls_back_entire_business_then_reprepare(store, collection_db):
    db = collection_db
    vid = db.create_video("BVc07", "合成")
    descriptor = aged(store)
    candidates = store.gc_candidates(grace_seconds=86400)
    before = rows(db)
    ready = Event()
    deleted = Event()

    def a():
        # prepare happened before B deletes an already-old reused orphan.
        ready.set()
        assert deleted.wait(5)
        with pytest.raises(ArtifactPrepareStale, match="artifact_prepare_stale"):
            with db.connect(guard=True) as c:
                db.create_note(vid, "must rollback", conn=c)
                db.update_video(vid, title="must rollback", conn=c)
                store.publish(c, "video:c07:raw", "v1", descriptor, video_id=vid)

    def b():
        assert ready.wait(5)
        result = store.gc(dry_run=False, grace_seconds=86400, candidates=candidates)
        assert result == [(descriptor.relative_key, "deleted")]
        deleted.set()

    with ThreadPoolExecutor(2) as executor:
        af = executor.submit(a)
        bf = executor.submit(b)
        af.result(8)
        bf.result(8)
    assert rows(db) == before and db.get_video(vid)["title"] == "合成"
    fresh = store.prepare(b"old orphan")
    with db.connect(guard=True) as c:
        db.create_note(vid, "committed", conn=c)
        ref = store.publish(c, "video:c07:raw", "v1", fresh, video_id=vid)
    assert store.read_bytes(version_id=ref) == b"old orphan"


def test_c07_publish_first_gc_waits_and_rechecks_all_history(store, collection_db):
    db = collection_db
    descriptor = aged(store)
    candidates = store.gc_candidates()
    locked = Event()
    commit = Event()
    started = Event()

    def a():
        with db.connect(guard=True) as c:
            ref = store.publish(c, "history", "v1", descriptor)
            locked.set()
            assert commit.wait(5)
        return ref

    def b():
        started.set()
        return store.gc(dry_run=False, candidates=candidates)

    with ThreadPoolExecutor(2) as executor:
        af = executor.submit(a)
        assert locked.wait(5)
        bf = executor.submit(b)
        assert started.wait(5)
        deadline = time.monotonic() + 3
        blocked = False
        while time.monotonic() < deadline:
            with db.pg.read() as c:
                blocked = c.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE 'SELECT %%workspace_guards%%') AS n"
                ).fetchone()["n"]
            if blocked:
                break
            time.sleep(0.01)
        assert blocked and not bf.done()
        commit.set()
        ref = af.result(5)
        assert bf.result(5) == [(descriptor.relative_key, "referenced")]
    assert store.read_bytes(version_id=ref) == b"old orphan"
    # The same lock-outside enumeration remains harmless after publication.
    assert store.gc(dry_run=False, candidates=candidates) == [
        (descriptor.relative_key, "referenced")
    ]


def test_c07_identity_change_rejected_and_corruption_not_overwritten(
    store, collection_db
):
    descriptor = store.prepare(b"original")
    path = store.path_for_key(descriptor.relative_key)
    original = path.read_bytes()
    path.unlink()
    path.write_bytes(original)
    with pytest.raises(ArtifactPrepareStale):
        with collection_db.pg.transaction() as c:
            store.publish(c, "changed", "v1", descriptor)
    assert rows(collection_db)["artifact_versions"] == 0
    path.write_bytes(b"corruption")
    with pytest.raises(ArtifactError, match="hash_or_size"):
        store.prepare(b"original")
    assert path.read_bytes() == b"corruption"


def test_c07_three_attempt_limit_revalidates_and_has_no_half_rows(store, collection_db):
    db = collection_db
    vid = db.create_video("BVc07retry", "合成")
    attempts = []

    def writer(c, descriptor):
        attempts.append(len(attempts) + 1)
        db.create_note(vid, "rolled back", conn=c)
        # Simulate an already-enumerated GC winning between prepare and guard.
        # GC is on an independent connection before this transaction locks guard.
        return store.publish(c, "retry", "v1", descriptor, video_id=vid)

    original = store.prepare

    def delete_after_prepare(content, **kwargs):
        descriptor = original(content, **kwargs)
        path = store.path_for_key(descriptor.relative_key)
        os.utime(path, (time.time() - 172800, time.time() - 172800))
        descriptor = original(content, **kwargs)
        assert store.gc(dry_run=False) == [(descriptor.relative_key, "deleted")]
        return descriptor

    store.prepare = delete_after_prepare
    before = rows(db)
    with pytest.raises(ArtifactPrepareStale):
        store.publish_bytes(b"retry", "retry", "v1", writer, video_id=vid)
    assert attempts == [1, 2, 3] and rows(db) == before


def test_c07_rename_before_rollback_only_leaves_orphan(store, collection_db):
    descriptor = store.prepare(b"renamed")
    with pytest.raises(RuntimeError):
        with collection_db.pg.transaction() as c:
            store.publish(c, "rollback", "v1", descriptor)
            raise RuntimeError("injected after rename")
    assert rows(collection_db)["artifact_versions"] == 0
    assert store.path_for_key(descriptor.relative_key).read_bytes() == b"renamed"
    # Default is dry run; no implicit unlink.
    assert store.gc(grace_seconds=0) == [(descriptor.relative_key, "candidate")]
    assert store.path_for_key(descriptor.relative_key).exists()


def _commit_then_crash(config, root, context, done):
    from shiliu.storage.postgres import PgDatabase
    from shiliu.db import Database

    with PgDatabase(config) as pg:
        db = Database(pg, context)
        store = ArtifactStore(Path(root), db)
        descriptor = store.prepare(b"committed before crash")
        with pg.transaction() as c:
            store.publish(c, "process", "v1", descriptor)
        done.set()
        os._exit(23)


def test_c07_commit_survives_process_exit(store, collection_db):
    import multiprocessing

    ctx = multiprocessing.get_context("spawn")
    done = ctx.Event()
    process = ctx.Process(
        target=_commit_then_crash,
        args=(collection_db.pg.config, str(store.root), collection_db.context, done),
    )
    process.start()
    try:
        assert done.wait(10)
        process.join(10)
        assert process.exitcode == 23
        assert (
            store.read_bytes(logical_key="process", source_version="v1")
            == b"committed before crash"
        )
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
