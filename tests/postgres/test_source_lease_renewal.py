"""Real FK/transaction contention; only marker-guarded random PG test databases."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from shiliu.domain import FavoriteItem
from shiliu.retrieval.coordinator import ProjectionWorker
from shiliu.storage.fences import CoordinationConflict
from test_collection_retrieval import add_video


def test_projection_fk_does_not_block_source_heartbeat(retrieval, monkeypatch):
    db, _, lexical, _ = retrieval
    sid, vid = add_video(retrieval)
    source = db.claim_source(sid, "source")
    worker = ProjectionWorker(lexical)
    claim = worker.claim(video_id=vid)
    snapshot = worker.snapshot(claim)
    units, tokens = worker.build(snapshot, claim)
    held, release = Event(), Event()
    original = worker._publish_units

    def hold(*args, **kwargs):
        original(*args, **kwargs)  # real INSERT into retrieval_unit_folders + FK
        held.set()
        assert release.wait(6)

    monkeypatch.setattr(worker, "_publish_units", hold)
    with ThreadPoolExecutor(2) as pool:
        published = pool.submit(worker.publish, claim, snapshot, units, tokens)
        assert held.wait(2)
        try:
            renewed = pool.submit(db.heartbeat, "favorite_sources", source)
            renewed.result(4)  # old FOR UPDATE fails at production's 3s timeout
            assert not published.done()
            # Parent FK key-share stays held longer than the unchanged timeout.
            assert not release.wait(3.1)
        finally:
            release.set()
        published.result(3)
    db.release("favorite_sources", source)


@pytest.mark.parametrize("operation", ["snapshot", "baseline"])
def test_source_transaction_serializes_own_heartbeat(collection_db, monkeypatch, operation):
    db = collection_db
    sid = db.create_favorite_source(folder_id=9011, folder_title="lease transaction")
    claim = db.claim_source(sid, "source")
    other_id = db.create_favorite_source(folder_id=9013, folder_title="independent source")
    other = db.claim_source(other_id, "other")
    held, release, renewal_started = Event(), Event(), Event()
    original = db._membership

    def hold(*args, **kwargs):
        original(*args, **kwargs)
        held.set()
        assert release.wait(6)

    monkeypatch.setattr(db, "_membership", hold)
    items = [FavoriteItem(bvid="BV9000000011", title="atomic member")]
    write = (
        lambda: db.record_source_snapshot(sid, items, processing_profile="formal", claim=claim)
    ) if operation == "snapshot" else (
        lambda: db.initialize_source_memberships(sid, items, authoritative=True, claim=claim)
    )

    def heartbeat():
        renewal_started.set()
        db.heartbeat("favorite_sources", claim)

    with ThreadPoolExecutor(2) as pool:
        published = pool.submit(write)
        assert held.wait(2)
        renewed = pool.submit(heartbeat)
        assert renewal_started.wait(1)
        try:
            db.heartbeat("favorite_sources", other)  # no cross-source local mutex
            assert not release.wait(3.3)
            assert not renewed.done(), "heartbeat must wait locally, not fail on own SQL lock"
        finally:
            release.set()
        published.result(3)
        renewed.result(3)
    db.release("favorite_sources", claim)
    db.release("favorite_sources", other)


def test_expired_source_transaction_rolls_back_instead_of_reviving(collection_db, monkeypatch):
    db = collection_db
    sid = db.create_favorite_source(folder_id=9012, folder_title="expired transaction")
    claim = db.claim_source(sid, "old", seconds=.5)
    original = db._membership

    def expire(*args, **kwargs):
        original(*args, **kwargs)
        Event().wait(.65)

    monkeypatch.setattr(db, "_membership", expire)
    with pytest.raises(CoordinationConflict, match="lease_fenced"):
        db.record_source_snapshot(sid, [FavoriteItem(bvid="BV9000000012", title="late")],
                                  processing_profile="formal", claim=claim)
    assert db.get_video_by_source("BV9000000012") is None
    newer = db.claim_source(sid, "new")
    assert newer["lease_epoch"] > claim["lease_epoch"]
    for action in (db.heartbeat, db.release):
        with pytest.raises(CoordinationConflict, match="lease_fenced"):
            action("favorite_sources", claim)
    db.release("favorite_sources", newer)
