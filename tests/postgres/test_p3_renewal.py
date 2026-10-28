# ruff: noqa: F811
"""Real PG renewal across the actual four P3 consumer lifetimes."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event, enumerate as threads
import time
import pytest
from test_wiki import wiki_parts, create, add_source  # noqa: F401
from test_collection_retrieval import FixedProvider
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.memory_jobs import MemoryJobWorker
from shiliu.assistant.memory_extraction import MemoryExtractionWorker
from shiliu.assistant.wiki_maintenance import WikiMaintenanceWorker
from shiliu.assistant.wiki_retrieval import WikiHybridIndex
from shiliu.assistant.wiki_jobs import WikiProjectionWorker
from test_memory_extraction import prepare

KINDS = [
    "memory_index",
    "memory_purge",
    "memory_extract",
    "wiki_maintenance",
    "wiki_projection",
]


def setup_worker(parts, kind, entered, release, monkeypatch):
    db, _, wiki, space, msg, run, _ = parts
    calls = []

    def pause():
        calls.append(kind)
        entered.set()
        assert release.wait(12)

    class Dense(FixedProvider):
        def embed_documents(self, texts):
            pause()
            return super().embed_documents(texts)

    memories = MemoryService(db, provider=Dense())
    kwargs = dict(owner="renewal-owner", lease_seconds=1.5, heartbeat_interval=0.2)
    if kind == "memory_extract":
        _, memories, job, proposal = prepare((db, memories, space, msg, run))

        class Model:
            def extract_memories(self, *, prompt):
                pause()
                return [proposal]

        worker = MemoryExtractionWorker(memories, provider_factory=Model, **kwargs)
    elif kind == "wiki_maintenance":
        _, _, ref, captured = add_source(parts)
        wiki.request_topic(
            space_id=space,
            topic="PG事务",
            source_refs=[ref],
            request_key="renewal-source",
            source_message_id=msg,
        )

        class Model:
            def generate_json(self, **kw):
                pause()
                return {"summary": "合成摘要", "key_points": [], "topics": ["PG事务"]}

        worker = WikiMaintenanceWorker(wiki, provider=Model(), **kwargs)
        # Reconcile itself has no model, run it before the source-extract target.
        assert worker.run_once()["kind"] == "source_reconcile"
    elif kind == "wiki_projection":
        create(wiki, space, msg)
        index = WikiHybridIndex(Dense(), wiki=wiki)
        index.search("事务", space_id=space)
        worker = WikiProjectionWorker(index, **kwargs)
    else:
        row = memories.save_explicit(
            text="正常长任务",
            subject_key="long",
            kind="context",
            scope_kind="user",
            scope_id=None,
            operation_key="memory",
        )
        if kind == "memory_purge":
            memories.forget(row["id"], expected_version=1, operation_key="forget")
            original = memories.purge

            def paused(**kw):
                pause()
                return original(**kw)

            monkeypatch.setattr(memories, "purge", paused)
        worker = MemoryJobWorker(memories, **kwargs)
    return worker, calls


def active(c, kind):
    if kind == "wiki_projection":
        return c.execute(
            "SELECT *,clock_timestamp() AS db_now FROM retrieval_projection_tasks WHERE status='running'"
        ).fetchone()
    # One statement snapshot: two read-committed SELECTs can legitimately see
    # the Job before a renewal and its lane after that atomic renewal commits.
    return c.execute(
        "SELECT j.*,l.lease_until AS lane_until,l.lease_epoch AS lane_epoch,clock_timestamp() AS db_now "
        "FROM assistant_jobs j LEFT JOIN scheduler_lanes l ON (l.workspace_id,l.principal_id,l.active_job_id)=(j.workspace_id,j.principal_id,j.id) "
        "WHERE j.status='running'"
    ).fetchone()


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("lose_owner", [False, True])
def test_actual_consumer_renews_and_stops_with_real_ownership_fence(
    wiki_parts, monkeypatch, kind, lose_owner
):
    db = wiki_parts[0]
    entered, release = Event(), Event()
    worker, calls = setup_worker(wiki_parts, kind, entered, release, monkeypatch)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(worker.run_once)
        assert entered.wait(5)
        with db.connect() as c:
            first = active(c, kind)
        assert first and first["lease_owner"] == "renewal-owner"
        samples = []
        start = time.monotonic()
        while time.monotonic() - start < 1.8:
            Event().wait(0.2)
            with db.connect() as c:
                row = active(c, kind)
                samples.append(row["lease_until"])
                if kind in ("memory_extract", "wiki_maintenance"):
                    assert (
                        row["lane_until"] == row["lease_until"]
                        and row["lane_epoch"] == row["lease_epoch"]
                    )
        assert max(samples) > first["lease_until"] and len(set(samples)) >= 3
        if lose_owner:
            table = (
                "retrieval_projection_tasks"
                if kind == "wiki_projection"
                else "assistant_jobs"
            )
            with db.connect() as c:
                c.execute(
                    f"UPDATE {table} SET lease_owner='replacement',lease_epoch=lease_epoch+1,lease_until=clock_timestamp()+interval '120 seconds' WHERE id=%s",
                    (first["id"],),
                )
                if kind in ("memory_extract", "wiki_maintenance"):
                    c.execute(
                        "UPDATE scheduler_lanes SET lease_epoch=lease_epoch+1,lease_until=(SELECT lease_until FROM assistant_jobs WHERE id=%s) WHERE active_job_id=%s",
                        (first["id"], first["id"]),
                    )
            Event().wait(0.4)
            with db.connect() as c:
                before = c.execute(
                    f"SELECT to_jsonb(t) AS value FROM {table} t WHERE id=%s",
                    (first["id"],),
                ).fetchone()["value"]
        release.set()
        result = future.result(8)
    assert not [t for t in threads() if t.name.startswith("shiliu-p3-renewal-")]
    table = (
        "retrieval_projection_tasks" if kind == "wiki_projection" else "assistant_jobs"
    )
    with db.connect() as c:
        after = c.execute(
            f"SELECT to_jsonb(t) AS value FROM {table} t WHERE id=%s", (first["id"],)
        ).fetchone()["value"]
        # Backend activity status can lag ReadyForQuery briefly. Observe fresh
        # statistics until drained, with a hard one-second bound; a persistent
        # transaction is still a failure, with PID/query details retained.
        deadline = time.monotonic() + 1
        while True:
            c.execute("SELECT pg_stat_clear_snapshot()")
            idle = c.execute(
                "SELECT pid,state,xact_start,state_change,query FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND state='idle in transaction'"
            ).fetchall()
            if not idle or time.monotonic() >= deadline:
                break
            Event().wait(0.01)
        assert not idle, idle
        if lose_owner:
            assert result["status"] == "stale" and after == before
            if kind == "memory_extract":
                assert after["proposal_json"] is None
                assert (
                    c.execute(
                        "SELECT count(*) AS n FROM model_dispatch_receipts WHERE job_id=%s",
                        (first["id"],),
                    ).fetchone()["n"]
                    == 1
                )
            # Explicitly expire the replacement for a separate recovery check.
            c.execute(
                f"UPDATE {table} SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",
                (first["id"],),
            )
            if kind in ("memory_extract", "wiki_maintenance"):
                c.execute(
                    "UPDATE scheduler_lanes SET lease_until=clock_timestamp()-interval '1 second' WHERE active_job_id=%s",
                    (first["id"],),
                )
        else:
            assert after["status"] == "completed", result
            assert (
                result["status"] in ("ready", "purged", "completed")
                if kind != "memory_extract"
                else result["reason"] == "applied"
            )
    if lose_owner:
        if kind == "wiki_maintenance":
            from shiliu.storage.scheduler import recover_job

            with db.connect() as c:
                assert recover_job(c, db.context, first["id"], disposition="unknown")
        else:
            assert worker.recover() >= 1
        if kind in ("memory_extract", "wiki_maintenance"):
            with db.connect() as c:
                assert (
                    c.execute(
                        "SELECT status FROM assistant_jobs WHERE id=%s", (first["id"],)
                    ).fetchone()["status"]
                    == "blocked"
                )
            assert len(calls) == 1  # recovery never resends unknown external work
        else:
            # Safe index/projection computation can retry; purge remains idempotent.
            with db.connect() as c:
                c.execute(
                    f"UPDATE {table} SET not_before=clock_timestamp() WHERE id=%s",
                    (first["id"],),
                )
            assert worker.run_once()["status"] in ("ready", "purged")
    assert not [t for t in threads() if t.name.startswith("shiliu-p3-renewal-")]
