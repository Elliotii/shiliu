from __future__ import annotations

import json
from hashlib import sha256
from dataclasses import replace
import pytest

from shiliu.artifacts import ArtifactStore
from shiliu.assistant.snapshots import SourceSnapshotStore
from shiliu.assistant.sources import CollectionSourceService, SourceScope
from shiliu.evidence.contracts import SourceArtifactReference
from shiliu.evidence.source import load_source_artifact, source_version_for_bytes
from shiliu.storage.artifacts import ArtifactPrepareStale


def publish_raw(db, artifacts, vid, raw):
    batch = artifacts.batch(vid)
    json_ref, text_ref = batch.save_raw_subtitle_bytes(raw)
    batch.commit(
        lambda conn: db.update_video(
            vid,
            raw_subtitle_path=text_ref,
            subtitle_language="zh",
            subtitle_source="human",
            conn=conn,
        )
    )
    return json_ref, text_ref


def test_raw_bytes_snapshot_and_historical_identity(collection_db, tmp_path):
    db = collection_db
    artifacts = ArtifactStore(tmp_path / "formal", db)
    sid = db.create_favorite_source(folder_id=1, folder_title="合成来源")
    from shiliu.domain import FavoriteItem

    vid = db.record_source_snapshot(
        sid,
        [FavoriteItem(bvid="BV1234567890", title="合成")],
        processing_profile="formal",
    )[0]
    old = b'[ {"from":0.0,"to":1.0,"content":"old"}, {"from":0.0,"to":2.0,"content":"run two"} ]\n'
    _, ref = publish_raw(db, artifacts, vid, old)
    reference = SourceArtifactReference(
        "bilibili", "BV1234567890", 1, "human", "zh", ref
    )
    evidence = load_source_artifact(reference, artifacts=artifacts)
    assert (
        evidence.source_version == sha256(old).hexdigest()
        and len(evidence.timeline_runs) == 1
    )
    # Different raw formatting creates another byte identity without changing IDs of old segments.
    snapshots = SourceSnapshotStore(db, artifacts)
    captured = snapshots.capture(vid)
    db.create_note(vid, "new private note")
    newer = snapshots.capture(vid)
    assert (
        captured.revision != newer.revision
        and captured.revision != evidence.source_version
    )
    assert snapshots.load(vid, captured.revision).snapshot["notes"] == []
    assert (
        snapshots.load(vid, newer.revision).snapshot["notes"][0]["content"]
        == "new private note"
    )
    new = json.dumps(
        json.loads(old), ensure_ascii=False, separators=(",", ":")
    ).encode()
    publish_raw(db, artifacts, vid, new)
    assert source_version_for_bytes(new) != evidence.source_version
    history = load_source_artifact(
        reference, expected_source_version=evidence.source_version, artifacts=artifacts
    )
    assert (
        history.segments == evidence.segments
        and history.source_artifact_id == evidence.source_artifact_id
    )
    assert artifacts.raw_bytes(ref) == old
    service = CollectionSourceService(db=db, artifacts=artifacts, snapshots=snapshots)
    assert (
        service._capture_or_load(vid, captured.revision).snapshot == captured.snapshot
    )
    assert service.visible_video_ids(SourceScope(all_active=True)) == [vid]
    assert (
        service._metadata_cards(
            [vid], allowed_source_ids={sid}, sort="collected_desc", limit=10
        )[0]["video_id"]
        == vid
    )


def test_batch_stale_retries_three_without_half_business(collection_db, tmp_path):
    import os, time

    db = collection_db
    artifacts = ArtifactStore(tmp_path / "formal", db)
    vid = db.create_video("BV1234567890", "unchanged")
    store = artifacts.objects
    original = store.prepare
    attempts = []

    def delete_prepared(raw, **kwargs):
        descriptor = original(raw, **kwargs)
        path = store.path_for_key(descriptor.relative_key)
        os.utime(path, (time.time() - 172800, time.time() - 172800))
        descriptor = original(raw, **kwargs)
        store.gc(dry_run=False)
        return descriptor

    store.prepare = delete_prepared
    batch = artifacts.batch(vid)
    _, ref = batch.save_raw_subtitle_bytes(b'[{"from":0,"to":1,"content":"synthetic"}]')

    def validate(conn):
        attempts.append(len(attempts) + 1)
        db._video(conn, vid, lock=True)

    with pytest.raises(ArtifactPrepareStale):
        batch.commit(
            lambda conn: db.update_video(
                vid, title="half", raw_subtitle_path=ref, conn=conn
            ),
            validate=validate,
        )
    assert (
        attempts == [1, 2, 3]
        and db.get_video(vid)["title"] == "unchanged"
        and db.get_video(vid)["raw_subtitle_path"] is None
    )
    with db.pg.read() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) AS n FROM shiliu.artifact_versions"
            ).fetchone()["n"]
            == 0
        )
