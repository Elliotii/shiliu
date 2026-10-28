# ruff: noqa: F811
"""Actual P3 extraction Job/dispatch/staged recovery, with a local model stub."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from psycopg.types.json import Jsonb
from test_memory import memory_parts, save  # noqa: F401
from shiliu.assistant.memory_extraction import MemoryExtractionWorker

TEXT = "我决定接下来两周重点学习数据库基础"


def prepare(parts, *, staged=None):
    db, m, space, msg, run = parts
    with db.connect(guard=True) as c:
        c.execute(
            "UPDATE assistant_messages SET role='user',content=%s,run_id=%s WHERE id=%s",
            (TEXT, run, msg),
        )
        thread = c.execute(
            "SELECT thread_id FROM assistant_messages WHERE id=%s", (msg,)
        ).fetchone()["thread_id"]
        job = m.store.enqueue_job(
            c,
            kind="memory_extract",
            dedupe_key="extract:actual",
            payload={
                "thread_id": thread,
                "message_ids": [msg],
                "memory_epoch": m.current_epoch(conn=c),
                "auto_enabled_at_enqueue": True,
                "auto_memory_generation": m.auto_policy(conn=c)["generation"],
            },
        )
        if staged is not None:
            c.execute(
                "UPDATE assistant_jobs SET proposal_json=%s WHERE id=%s",
                (Jsonb({"proposals": staged}), job),
            )
    proposal = dict(
        op="add",
        kind="context",
        text=TEXT,
        subject_key="study",
        scope_kind="space",
        scope_id=space,
        source_excerpt=TEXT,
    )
    return db, m, job, proposal


def test_actual_extraction_dispatch_staging_and_atomic_publication(memory_parts):
    db, m, job, proposal = prepare(memory_parts)

    class Provider:
        calls = 0

        def extract_memories(self, *, prompt):
            self.calls += 1
            assert TEXT in prompt
            with db.connect(read_only=True) as c:
                assert not c.execute(
                    "SELECT pid FROM pg_stat_activity WHERE datname=current_database() AND state='idle in transaction' AND pid<>pg_backend_pid()"
                ).fetchall()
            return [proposal]

    provider = Provider()
    worker = MemoryExtractionWorker(
        m, owner="extractor", provider_factory=lambda: provider
    )
    result = worker.run_once()
    assert result["reason"] == "applied", result
    assert len(result["applied_memory_ids"]) == 1 and provider.calls == 1
    assert worker.run_once() is None
    with db.connect() as c:
        row = c.execute("SELECT * FROM assistant_jobs WHERE id=%s", (job,)).fetchone()
        assert row["status"] == "completed" and row["proposal_json"]["proposals"]
        assert (
            c.execute(
                "SELECT count(*) AS n FROM model_dispatch_receipts WHERE job_id=%s",
                (job,),
            ).fetchone()["n"]
            == 1
        )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM assistant_mutation_receipts"
            ).fetchone()["n"]
            == 1
        )

    with db.connect(read_only=True) as c:
        messages=c.execute("SELECT * FROM assistant_notifications WHERE origin_type='memory_change'").fetchall()
        assert len(messages)==1 and messages[0]['source_type']=='auto_memory'
        assert messages[0]['cause_refs']['job_id']==job
        assert messages[0]['cause_refs']['source_message_ids']


def test_unknown_dispatch_never_calls_model_again(memory_parts):
    db, m, job, _ = prepare(memory_parts)

    class Provider:
        calls = 0

        def extract_memories(self, *, prompt):
            self.calls += 1
            raise OSError("synthetic lost response")

    provider = Provider()
    worker = MemoryExtractionWorker(
        m, owner="extractor", provider_factory=lambda: provider
    )
    assert worker.run_once()["status"] == "retry_wait"
    with db.connect() as c:
        c.execute(
            "UPDATE assistant_jobs SET not_before=clock_timestamp() WHERE id=%s", (job,)
        )
    assert worker.run_once()["status"] == "blocked"
    assert provider.calls == 1 and not m.list()
    with db.connect() as c:
        assert (
            c.execute(
                "SELECT last_error_code FROM assistant_jobs WHERE id=%s", (job,)
            ).fetchone()["last_error_code"]
            == "external_result_unknown"
        )


def test_staged_proposal_recovers_without_model(memory_parts):
    _, m, _, _ = prepare(memory_parts, staged=[])

    def denied():
        raise AssertionError("staged result must not invoke model")

    assert (
        MemoryExtractionWorker(
            m, owner="extractor", provider_factory=denied
        ).run_once()["reason"]
        == "no_admissible_proposal"
    )


@pytest.mark.parametrize("change", ["generation", "correct", "forget"])
def test_c09_actual_extraction_model_inflight_cannot_undo_user_change(
    memory_parts, change
):
    db, m, job, proposal = prepare(memory_parts)
    old = (
        save(m, source_message_ids=[memory_parts[3]], text=TEXT)
        if change != "generation"
        else None
    )
    entered, release = Event(), Event()

    class Provider:
        def extract_memories(self, *, prompt):
            entered.set()
            assert release.wait(10)
            return [proposal]

    worker = MemoryExtractionWorker(m, owner="extractor", provider_factory=Provider)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(worker.run_once)
        assert entered.wait(10)
        try:
            if change == "generation":
                m.set_auto_enabled(False)
                m.set_auto_enabled(True)
            elif change == "correct":
                m.correct(
                    old["id"],
                    text="用户改为学习网络",
                    expected_version=1,
                    operation_key="user-correct",
                )
            else:
                m.forget(old["id"], expected_version=1, operation_key="user-forget")
        finally:
            release.set()
        result = future.result(15)
    assert not result["applied_memory_ids"], result
    visible = m.list()
    assert (
        not visible
        if change != "correct"
        else [v["text"] for v in visible] == ["用户改为学习网络"]
    )


@pytest.mark.parametrize("state", ["staged", "unknown", "replay_safe"])
def test_actual_extraction_expired_owner_recovery_preserves_staged_and_blocks_unknown(
    memory_parts, state
):
    from shiliu.storage.scheduler import claim_job, job_transition
    from shiliu.storage.budget import reserve_dispatch

    db, m, job, _ = prepare(memory_parts)
    worker = MemoryExtractionWorker(m, owner="new-owner", provider_factory=lambda: None)
    with db.connect() as c:
        claimed = claim_job(c, db.context, "old-owner", kinds=("memory_extract",))
        assert claimed["id"] == job
        if state == "staged":
            job_transition(
                c,
                db.context,
                job,
                "old-owner",
                claimed["lease_epoch"],
                action="stage",
                proposal={"proposals": []},
            )
        if state == "unknown":
            reserve_dispatch(
                c,
                db.context,
                "synthetic-memory-dispatch",
                lane="background",
                request_limit=24,
                request_hash="a" * 64,
                job_id=job,
            )
        c.execute(
            "UPDATE assistant_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",
            (job,),
        )
        c.execute(
            "UPDATE scheduler_lanes SET lease_until=clock_timestamp()-interval '1 second' WHERE active_job_id=%s",
            (job,),
        )
    assert worker.recover() == 1
    with db.connect() as c:
        row = c.execute("SELECT * FROM assistant_jobs WHERE id=%s", (job,)).fetchone()
        assert row["status"] == ("blocked" if state == "unknown" else "retry_wait")
        assert row["attempt"] == 1 and row["lease_epoch"] == claimed["lease_epoch"]
        assert row["proposal_json"] == (
            {"proposals": []} if state == "staged" else None
        )


@pytest.mark.parametrize("reason", ["activity", "daily_budget", "batch_budget"])
def test_maintenance_wait_preserves_attempt_and_staged_proposal(memory_parts, reason):
    from shiliu.storage.scheduler import claim_job, job_transition

    db, m, job, _ = prepare(memory_parts)
    with db.connect() as c:
        raw = claim_job(c, db.context, "owner", kinds=("memory_extract",))
        job_transition(
            c,
            db.context,
            job,
            "owner",
            raw["lease_epoch"],
            action="stage",
            proposal={"proposals": []},
        )
    m.store.defer_maintenance_job(m.store.job_dto(raw), reason=reason)
    with db.connect() as c:
        row = c.execute(
            "SELECT *,not_before>clock_timestamp() AS delayed FROM assistant_jobs WHERE id=%s",
            (job,),
        ).fetchone()
        assert row["attempt"] == 0 and row["proposal_json"] == {"proposals": []}
        assert row["status"] == ("queued" if reason == "activity" else "budget_wait")
        assert row["lease_owner"] is None and row["lease_until"] is None
        assert row["delayed"] if reason != "activity" else not row["delayed"]
        assert (
            c.execute("SELECT active_job_id FROM scheduler_lanes").fetchone()[
                "active_job_id"
            ]
            is None
        )


def test_actual_extractor_budget_wait_and_activity_gate_do_not_spend_retry(
    memory_parts,
):
    from shiliu.storage.budget import reserve_dispatch

    db, m, job, _ = prepare(memory_parts)

    def denied():
        raise AssertionError("no model call allowed")

    busy = MemoryExtractionWorker(
        m, owner="busy", provider_factory=denied, continue_allowed=lambda: False
    )
    assert busy.run_once() is None
    with db.connect() as c:
        for i in range(60):
            reserve_dispatch(
                c,
                db.context,
                f"fill-budget-{i}",
                lane="background",
                request_limit=60,
                request_hash="a" * 64,
            )
    worker = MemoryExtractionWorker(
        m,
        owner="budget",
        provider_factory=lambda: type("P", (), {"extract_memories": denied})(),
    )
    assert worker.run_once()["status"] == "budget_wait"
    with db.connect() as c:
        row = c.execute(
            "SELECT status,attempt,proposal_json FROM assistant_jobs WHERE id=%s",
            (job,),
        ).fetchone()
        assert row == {"status": "budget_wait", "attempt": 0, "proposal_json": None}


def test_actual_extractor_yields_after_model_and_reuses_staged_result(memory_parts):
    db, m, job, proposal = prepare(memory_parts)
    idle = {"value": True}

    class Provider:
        calls = 0

        def extract_memories(self, *, prompt):
            self.calls += 1
            idle["value"] = False
            return [proposal]

    provider = Provider()
    worker = MemoryExtractionWorker(
        m,
        owner="worker",
        provider_factory=lambda: provider,
        continue_allowed=lambda: idle["value"],
    )
    assert worker.run_once()["status"] == "queued"
    assert not m.list()
    with db.connect() as c:
        row = c.execute("SELECT * FROM assistant_jobs WHERE id=%s", (job,)).fetchone()
        assert row["attempt"] == 0 and row["proposal_json"] == {"proposals": [proposal]}
    idle["value"] = True
    assert worker.run_once()["reason"] == "applied"
    assert provider.calls == 1
