# ruff: noqa: F811
"""P3 reused Job/lane fences: real unchanged-row waits crossing DB expiry."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time
import json
import os
from pathlib import Path

import pytest
from psycopg import sql
from test_coordination import coordinated, CTX  # noqa: F401,F811
from shiliu.storage.fences import CoordinationConflict
from shiliu.storage.scheduler import claim_job, job_transition, recover_job


def snapshot(db):
    with db.read() as c:
        return {
            table: c.execute(
                sql.SQL(
                    "SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text) AS rows FROM shiliu.{} t"
                ).format(sql.Identifier(table))
            ).fetchone()["rows"]
            for table in (
                "assistant_jobs",
                "scheduler_lanes",
                "assistant_scheduler_events",
            )
        }


def expire_while_waiting(db, table, identity, operation, *, lease_until=None):
    """Test deadlines use monotonic; authorization time is only PG clock."""
    poll = Event()

    def run():
        try:
            with db.transaction() as c:
                return operation(c)
        except CoordinationConflict as exc:
            return exc

    with ThreadPoolExecutor(1) as executor:
        with db.transaction() as b:
            key = "active_job_id=%s" if table == "scheduler_lanes" else "id=%s"
            locked = b.execute(
                sql.SQL(
                    (
                        "SELECT lease_until FROM shiliu.{} WHERE "
                        if lease_until is None
                        else "SELECT id FROM shiliu.{} WHERE "
                    )
                    + key
                    + " FOR UPDATE"
                ).format(sql.Identifier(table)),
                (identity,),
            ).fetchone()
            until = locked["lease_until"] if lease_until is None else lease_until
            result = executor.submit(run)
            with db.read() as obs:
                deadline = time.monotonic() + 2.5
                while time.monotonic() < deadline:
                    obs.execute("SELECT pg_stat_clear_snapshot()")
                    if obs.execute(
                        "SELECT pid FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND %s=ANY(pg_blocking_pids(pid))",
                        (b.info.backend_pid,),
                    ).fetchone():
                        break
                    assert not result.done(), "No actual unchanged-row lock wait"
                    poll.wait(0.005)
                else:
                    pytest.fail("No actual PG Lock wait")
                assert obs.execute(
                    "SELECT clock_timestamp()<%s AS live", (until,)
                ).fetchone()["live"]
                while not obs.execute(
                    "SELECT clock_timestamp()>=%s AS expired", (until,)
                ).fetchone()["expired"]:
                    assert time.monotonic() < deadline
                    poll.wait(0.005)
                assert not result.done()
        return result.result(3)


def take(db, job, *, model=False):
    with db.transaction() as c:
        if model:
            c.execute(
                "UPDATE shiliu.assistant_jobs SET kind='wiki_integrate' WHERE id=%s",
                (job,),
            )
        return claim_job(c, CTX, "worker", lease_seconds=1.5)


@pytest.mark.parametrize("model", [False, True])
@pytest.mark.parametrize("action", ["heartbeat", "stage", "complete", "fail", "defer"])
def test_wait_expiry_rejects_all_job_transitions(coordinated, model, action):
    db, _, _, _, _, job = coordinated
    claimed = take(db, job, model=model)
    before = snapshot(db)
    result = expire_while_waiting(
        db,
        "assistant_jobs",
        job,
        lambda c: job_transition(
            c,
            CTX,
            job,
            "worker",
            claimed["lease_epoch"],
            action=action,
            proposal={"staged": True},
        ),
    )
    after = snapshot(db)
    evidence = Path("/tmp/shiliu-w01-20261023") / (
        "p3-scheduler-" + os.environ.get("P3_EVIDENCE_PHASE", "after") + "-states.jsonl"
    )
    with evidence.open("a") as f:
        f.write(
            json.dumps(
                {
                    "model": model,
                    "action": action,
                    "observed_lock_wait": True,
                    "live_during_wait": True,
                    "expired_before_unlock": True,
                    "result": type(result).__name__,
                    "error": str(result),
                    "before": before,
                    "after": after,
                    "unchanged": before == after,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    assert isinstance(result, CoordinationConflict) and str(result) == "job_fenced", (
        repr(result)
    )
    assert after == before


def test_recovery_rechecks_expiry_after_lock(coordinated):
    db, _, _, _, _, job = coordinated
    take(db, job)
    assert (
        expire_while_waiting(
            db,
            "assistant_jobs",
            job,
            lambda c: recover_job(c, CTX, job, disposition="replay_safe"),
        )
        is True
    )
    with db.read() as c:
        row = c.execute(
            "SELECT * FROM shiliu.assistant_jobs WHERE id=%s", (job,)
        ).fetchone()
        assert (
            row["status"] == "retry_wait"
            and row["attempt"] == 1
            and row["lease_epoch"] == 1
        )


def test_lane_claim_rechecks_expiry_after_lock(coordinated):
    db, _, _, _, _, job = coordinated
    take(db, job, model=True)
    with db.transaction() as c:
        c.execute(
            "INSERT INTO shiliu.assistant_jobs SELECT (jsonb_populate_record(NULL::shiliu.assistant_jobs,to_jsonb(j)||jsonb_build_object('id','next-job','dedupe_key','next-job','status','queued','lease_owner',NULL,'lease_until',NULL,'attempt',0,'lease_epoch',0))).* FROM shiliu.assistant_jobs j WHERE id=%s",
            (job,),
        )
    result = expire_while_waiting(
        db, "scheduler_lanes", job, lambda c: claim_job(c, CTX, "new")
    )
    assert result and result["id"] == "next-job"
    with db.transaction() as c:
        assert recover_job(c, CTX, job, disposition="unknown")
        lane = c.execute("SELECT * FROM shiliu.scheduler_lanes").fetchone()
        assert lane["active_job_id"] == "next-job"
    with pytest.raises(CoordinationConflict, match="job_fenced"):
        with db.transaction() as c:
            job_transition(c, CTX, job, "worker", 1, action="complete")


@pytest.mark.parametrize("action", ["heartbeat", "stage", "complete", "fail", "defer"])
def test_valid_job_transitions_and_recovery_preserve_state(coordinated, action):
    db, _, _, _, _, job = coordinated
    with db.transaction() as c:
        claim = claim_job(c, CTX, "worker")
        job_transition(
            c,
            CTX,
            job,
            "worker",
            claim["lease_epoch"],
            action=action,
            proposal={"keep": True},
        )
        row = c.execute(
            "SELECT * FROM shiliu.assistant_jobs WHERE id=%s", (job,)
        ).fetchone()
        assert row["attempt"] == (0 if action == "defer" else 1)
        if action == "stage":
            assert row["proposal_json"] == {"keep": True}
        assert (
            row["status"]
            == {
                "heartbeat": "running",
                "stage": "running",
                "complete": "completed",
                "fail": "retry_wait",
                "defer": "queued",
            }[action]
        )
