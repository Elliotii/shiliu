"""P2 leases must be checked against DB time after, not before, a row-lock wait."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time

import pytest
from psycopg import sql

from shiliu.domain import FavoriteItem, StageName
from shiliu.retrieval.coordinator import ProjectionWorker, ProjectionStale
from shiliu.storage.fences import CoordinationConflict
from test_collection_retrieval import add_video, task_row, due


LEASE_SECONDS = 1.5  # Less than the unchanged production 3-second lock timeout.
DOMAINS = ("favorite_sources", "asr_jobs", "pipeline_stages")
STATE_TABLES = (
    "favorite_sources",
    "videos",
    "video_source_memberships",
    "seen_items",
    "events",
    "sync_runs",
    "asr_jobs",
    "pipeline_stages",
    "workspace_guards",
    "retrieval_projection_tasks",
    "retrieval_units",
    "retrieval_unit_folders",
    "collection_embeddings",
    "retrieval_sync_state",
)


def state(db):
    with db.connect(read_only=True) as c:
        return {
            name: c.execute(
                sql.SQL(
                    "SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text) AS rows "
                    "FROM shiliu.{} t WHERE workspace_id=%s"
                ).format(sql.Identifier(name)),
                (db.workspace_id,),
            ).fetchone()["rows"]
            for name in STATE_TABLES
        }


def locked_expiry(db, table, identity, operation, *, source_commit=None):
    """B locks but never updates; A starts live, waits, and resumes only expired.

    Wall time is used only for test deadlines. Every lease assertion is SQL DB
    clock, and a timeout/connection error is never accepted as a lease fence.
    """
    started = Event()
    poll = Event()

    def run():
        started.set()
        try:
            return operation()
        except CoordinationConflict as exc:
            return exc

    with ThreadPoolExecutor(1) as executor:
        with db.connect(guard=source_commit is not None) as blocker:
            row = blocker.execute(
                sql.SQL(
                    "SELECT lease_until FROM shiliu.{} WHERE workspace_id=%s AND id=%s FOR UPDATE"
                ).format(sql.Identifier(table)),
                (db.workspace_id, identity),
            ).fetchone()
            until = row["lease_until"]
            if source_commit is not None:
                source_commit(blocker)
            blocker_pid = blocker.info.backend_pid
            result = executor.submit(run)
            assert started.wait(1)
            with db.connect(read_only=True) as observer:
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    waiting = observer.execute(
                        "SELECT pid FROM pg_stat_activity WHERE datname=current_database() "
                        "AND wait_event_type='Lock' AND %s=ANY(pg_blocking_pids(pid))",
                        (blocker_pid,),
                    ).fetchone()
                    if waiting:
                        break
                    assert not result.done(), "A did not wait on B's unchanged row"
                    poll.wait(0.005)
                else:
                    pytest.fail("No actual PG Lock wait observed")
                assert observer.execute(
                    "SELECT clock_timestamp()<%s::timestamptz AS live", (until,)
                ).fetchone()["live"], "A must enter the wait before expiry"
                while time.monotonic() < deadline:
                    if observer.execute(
                        "SELECT clock_timestamp()>=%s::timestamptz AS expired", (until,)
                    ).fetchone()["expired"]:
                        break
                    poll.wait(0.005)
                else:
                    pytest.fail("DB lease did not expire within the bounded wait")
                assert not result.done()
            # Only COMMIT releases B; no UPDATE/tuple replacement can trigger EPQ.
        return result.result(3)


def collection_claim(db, table, *, seconds=LEASE_SECONDS, owner="old"):
    vid = db.create_video("BV9000000001", "lease before lock wait")
    if table == "favorite_sources":
        identity = db.create_favorite_source(folder_id=9001, folder_title="lease")
        take = lambda worker, duration: db.claim_source(
            identity, worker, seconds=duration
        )
    elif table == "asr_jobs":
        db.ensure_asr_job(
            vid, provider="synthetic", model="synthetic", trigger_mode="manual"
        )
        take = lambda worker, duration: db.claim_asr(vid, worker, seconds=duration)
    else:
        db.ensure_stage(vid, StageName.SOURCE_FETCH)
        take = lambda worker, duration: db.claim_stage(
            vid, StageName.SOURCE_FETCH, worker, seconds=duration
        )
    return vid, take(owner, seconds), take


def complete_collection(db, table, claim, vid, *, conn=None):
    if table == "favorite_sources":
        return db.record_source_snapshot(
            claim["id"],
            [FavoriteItem(bvid="BV9000000002", title="late source result")],
            processing_profile="formal",
            claim=claim,
            conn=conn,
        )
    with db.connect(conn, guard=True) as c:
        db._video(c, vid, lock=True)
        if table == "asr_jobs":
            db.update_asr_job(vid, status="completed", claim=claim, conn=c)
        else:
            db.update_stage(
                vid, StageName.SOURCE_FETCH, status="completed", claim=claim, conn=c
            )
        db.update_video(vid, title="late business result", conn=c)


@pytest.mark.parametrize("table", DOMAINS)
@pytest.mark.parametrize("action", ("check", "heartbeat", "release", "complete"))
def test_collection_wait_expiry_is_fenced_without_any_mutation(
    collection_db, table, action
):
    db = collection_db
    vid, claim, _ = collection_claim(db, table)
    before = state(db)

    def operation():
        if action == "check":
            with db.connect(guard=True) as c:
                db.check_lease(c, table, claim)
                db.update_video(vid, title="unchecked late write", conn=c)
        elif action == "heartbeat":
            db.heartbeat(table, claim)
        elif action == "release":
            db.release(table, claim)
        else:
            complete_collection(db, table, claim, vid)

    result = locked_expiry(db, table, claim["id"], operation)
    assert isinstance(result, CoordinationConflict) and str(result) == "lease_fenced", (
        repr(result)
    )
    assert state(db) == before


@pytest.mark.parametrize("table", DOMAINS)
def test_collection_claim_rechecks_live_after_unchanged_row_wait(collection_db, table):
    db = collection_db
    vid, old, take = collection_claim(db, table)
    new = locked_expiry(db, table, old["id"], lambda: take("new", 120))
    assert new is not None and not isinstance(new, Exception)
    assert new["lease_owner"] == "new" and new["lease_epoch"] == old["lease_epoch"] + 1
    # A valid new owner may renew/finish; the old epoch may not touch it.
    db.heartbeat(table, new)
    complete_collection(db, table, new, vid)
    before = state(db)
    for action in (
        lambda: db.heartbeat(table, old),
        lambda: db.release(table, old),
        lambda: complete_collection(db, table, old, vid),
    ):
        with pytest.raises(CoordinationConflict, match="^lease_fenced$"):
            action()
        assert state(db) == before
    db.release(table, new)


@pytest.mark.parametrize("action", ("publish", "heartbeat", "fail"))
def test_projection_wait_expiry_cannot_publish_renew_or_release(retrieval, action):
    db, artifacts, lexical, dense = retrieval
    _, vid = add_video(retrieval)
    dense.rebuild()
    db.update_video(vid, description="new intent; old units must stay unchanged")
    worker = ProjectionWorker(lexical, dense, owner="old", lease_seconds=LEASE_SECONDS)
    claim = worker.claim(video_id=vid)
    snapshot = worker.snapshot(claim)
    units, tokens = worker.build(snapshot, claim)
    vectors = dense.encode(units)
    before = state(db)
    operations = {
        "publish": lambda: worker.publish(
            claim, snapshot, units, tokens, vectors=vectors
        ),
        "heartbeat": lambda: worker.heartbeat(claim),
        "fail": lambda: worker.fail(claim, "late failure"),
    }
    result = locked_expiry(
        db, "retrieval_projection_tasks", claim["id"], operations[action]
    )
    assert (
        isinstance(result, ProjectionStale) and str(result) == "projection_lease_fenced"
    ), repr(result)
    assert state(db) == before  # Includes exact lease/status/payload/ready_generation.
    assert task_row(db, vid)["status"] == "running"
    fresh = ProjectionWorker(lexical, dense, owner="fresh")
    fresh.recover()
    recovered = task_row(db, vid)
    assert (
        recovered["status"] == "retry_wait" and recovered["attempt"] == claim["attempt"]
    )
    assert recovered["payload"] == claim["payload"] and recovered["lease_owner"] is None
    due(db, vid)
    assert fresh.run_one(video_id=vid)["status"] == "completed"
    dense.activate()
    assert dense.statistics()["index"]["ready"]
    committed = state(db)
    for operation in operations.values():
        with pytest.raises(ProjectionStale):
            operation()
        assert state(db) == committed


def test_projection_live_heartbeat_publish_and_failure_still_work(retrieval):
    db, artifacts, lexical, dense = retrieval
    _, vid = add_video(retrieval)
    worker = ProjectionWorker(lexical, dense, owner="live")
    claim = worker.claim(video_id=vid)
    worker.heartbeat(claim)
    snapshot = worker.snapshot(claim)
    units, tokens = worker.build(snapshot, claim)
    assert (
        worker.publish(claim, snapshot, units, tokens, vectors=dense.encode(units))[
            "status"
        ]
        == "completed"
    )
    db.update_video(vid, description="new request")
    next_claim = worker.claim(video_id=vid)
    worker.fail(next_claim, "local failure")
    failed = task_row(db, vid)
    assert failed["status"] == "retry_wait" and failed["last_error"] == "local failure"
    assert failed["attempt"] == next_claim["attempt"] and failed["lease_owner"] is None


def test_valid_locked_source_commit_precedes_waiting_takeover(collection_db):
    db = collection_db
    vid, old, take = collection_claim(db, "favorite_sources")
    new = locked_expiry(
        db,
        "favorite_sources",
        old["id"],
        lambda: take("new", 120),
        source_commit=lambda c: complete_collection(
            db, "favorite_sources", old, vid, conn=c
        ),
    )
    assert new["lease_epoch"] == old["lease_epoch"] + 1
    assert db.get_video_by_source("BV9000000002")["title"] == "late source result"
    # A's publication was validated and written while live under the source lock;
    # B's later takeover cannot retroactively undo that committed publication.
    before = state(db)
    with pytest.raises(CoordinationConflict, match="^lease_fenced$"):
        db.release("favorite_sources", old)
    assert state(db) == before


@pytest.mark.parametrize(
    ("status", "task_id"),
    (
        ("submitted", None),
        ("processing", None),
        ("processing", "synthetic-existing-task"),
    ),
)
def test_asr_takeover_after_wait_preserves_attempt_and_poll_identity(
    collection_db, status, task_id
):
    db = collection_db
    vid, old, take = collection_claim(db, "asr_jobs")
    db.update_asr_job(vid, claim=old, status=status, task_id=task_id, attempt_count=7)
    new = locked_expiry(db, "asr_jobs", old["id"], lambda: take("new", 120))
    row = db.get_asr_job(vid)
    assert row["attempt_count"] == 7 and row["task_id"] == task_id
    assert row["lease_epoch"] == old["lease_epoch"] + 1
    if task_id is None:
        assert new is None and row["status"] == "needs_review"
        assert (
            row["last_error_code"] == "external_result_unknown"
            and row["lease_owner"] is None
        )
    else:
        assert new["lease_owner"] == "new" and row["status"] == "processing"
        db.heartbeat("asr_jobs", new)
        db.update_asr_job(vid, claim=new, status="completed")
    before = state(db)
    with pytest.raises(CoordinationConflict, match="^lease_fenced$"):
        db.update_asr_job(vid, claim=old, status="completed")
    assert state(db) == before


def test_unknown_model_stage_after_wait_is_reviewed_not_replayed(collection_db):
    db = collection_db
    vid = db.create_video("BV9000000001", "synthetic model stage")
    db.ensure_stage(vid, StageName.SUMMARY)
    old = db.claim_stage(vid, StageName.SUMMARY, "old", seconds=LEASE_SECONDS)
    db.update_stage(
        vid, StageName.SUMMARY, claim=old, status="processing", attempt_count=4
    )
    assert (
        locked_expiry(
            db,
            "pipeline_stages",
            old["id"],
            lambda: db.claim_stage(vid, StageName.SUMMARY, "new"),
        )
        is None
    )
    row = db.get_stage(vid, StageName.SUMMARY)
    assert row["status"] == "needs_review" and row["attempt_count"] == 4
    assert (
        row["last_error_code"] == "external_result_unknown"
        and row["lease_epoch"] == old["lease_epoch"] + 1
    )
    before = state(db)
    with pytest.raises(CoordinationConflict, match="^lease_fenced$"):
        db.update_stage(vid, StageName.SUMMARY, claim=old, status="completed")
    assert state(db) == before


def test_projection_recovery_skips_locked_expired_task_and_preserves_live_task(
    retrieval,
):
    db, artifacts, lexical, dense = retrieval
    _, vid = add_video(retrieval)
    _, live_vid = add_video(retrieval, index=2)
    old = ProjectionWorker(lexical, dense, owner="old")
    claim = old.claim(video_id=vid)
    live = old.claim(video_id=live_vid)
    with db.connect() as c:
        c.execute(
            "UPDATE shiliu.retrieval_projection_tasks SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",
            (claim["id"],),
        )
    before = state(db)
    fresh = ProjectionWorker(lexical, dense, owner="fresh")
    with ThreadPoolExecutor(1) as executor:
        with db.connect() as blocker:
            blocker.execute(
                "SELECT id FROM shiliu.retrieval_projection_tasks WHERE id=%s FOR UPDATE",
                (claim["id"],),
            ).fetchone()
            # SKIP LOCKED deliberately avoids a wait (timeouts stay unchanged).
            assert executor.submit(fresh.recover).result(1) is None
            assert state(db) == before
    fresh.recover()
    assert task_row(db, vid)["status"] == "retry_wait"
    live_after = task_row(db, live_vid)
    assert live_after == live and live_after["lease_owner"] == "old"
    recovered = task_row(db, vid)
    assert (
        recovered["attempt"] == claim["attempt"]
        and recovered["payload"] == claim["payload"]
    )


def test_projection_lost_lease_during_build_does_not_fail_or_release_request(
    retrieval, monkeypatch
):
    db, artifacts, lexical, dense = retrieval
    _, vid = add_video(retrieval)
    worker = ProjectionWorker(lexical, dense, owner="lost")
    saved = []

    def interrupted(snapshot, claim):
        with db.connect() as c:
            c.execute(
                "UPDATE shiliu.retrieval_projection_tasks SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",
                (claim["id"],),
            )
        saved.append(state(db))
        raise ValueError("synthetic local build interruption")

    monkeypatch.setattr(worker, "build", interrupted)
    assert worker.run_one(video_id=vid)["status"] == "stale"
    assert state(db) == saved[0]


def test_projection_future_intent_is_not_claimed_early(retrieval):
    db, artifacts, lexical, dense = retrieval
    _, vid = add_video(retrieval)
    with db.connect() as c:
        c.execute(
            "UPDATE shiliu.retrieval_projection_tasks SET not_before=clock_timestamp()+interval '1 minute' WHERE workspace_id=%s AND resource_key=%s",
            (db.workspace_id, str(vid)),
        )
    before = state(db)
    assert ProjectionWorker(lexical, dense).claim(video_id=vid) is None
    assert state(db) == before
    due(db, vid)
    assert (
        ProjectionWorker(lexical, dense).run_one(video_id=vid)["status"] == "completed"
    )


def test_sync_audit_recovery_does_not_interrupt_run_using_pre_wait_source_state(
    collection_db,
):
    db = collection_db
    source = db.create_favorite_source(folder_id=9001, folder_title="audit lease")
    run = db.start_sync_run("manual")
    with db.connect() as c:
        c.execute(
            "UPDATE shiliu.sync_runs SET heartbeat_at=clock_timestamp()-interval '11 minutes' WHERE id=%s",
            (run,),
        )
    with ThreadPoolExecutor(1) as executor:
        with db.connect() as blocker:
            blocker.execute(
                "SELECT id FROM shiliu.sync_runs WHERE id=%s FOR UPDATE", (run,)
            ).fetchone()
            result = executor.submit(db.recover_stale_sync_runs)
            # Old UPDATE waits using the old no-active-source snapshot. The
            # repaired SKIP LOCKED path may finish immediately without waiting.
            deadline = time.monotonic() + 1
            poll = Event()
            with db.connect(read_only=True) as observer:
                while not result.done():
                    if observer.execute(
                        "SELECT pid FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND %s=ANY(pg_blocking_pids(pid))",
                        (blocker.info.backend_pid,),
                    ).fetchone():
                        break
                    assert time.monotonic() < deadline
                    poll.wait(0.005)
            claim = db.claim_source(source, "active")
        result.result(2)
    assert db.get_sync_run(run)["status"] == "running"
    db.recover_stale_sync_runs()
    assert db.get_sync_run(run)["status"] == "running"
    db.release("favorite_sources", claim)
    db.recover_stale_sync_runs()
    assert db.get_sync_run(run)["status"] == "interrupted"
