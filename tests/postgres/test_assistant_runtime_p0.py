"""P0 integration: real PG fences, Wiki commits and the shared Assistant loop.

Fault hooks call the real stores/handlers; no replacement finish implementation.
All Provider transports are local scripted functions.
"""
import asyncio
from collections import Counter
import json
import time

import pytest
from psycopg.conninfo import conninfo_to_dict

from test_wiki import wiki_parts, add_source  # noqa: F401
from shiliu.assistant.pg_store import PgAssistantRunStore
from shiliu.assistant.provider import OpenAICompatibleAssistantProvider, ModelTurn
from shiliu.assistant.provider_request import EndpointCapabilities
from shiliu.assistant.runtime import AssistantRuntime
from shiliu.assistant.wiki import MaintenanceYield
from shiliu.storage.fences import CoordinationConflict
from shiliu.storage.scheduler import recover_job


class OfflineContext:
    async def connect(self):
        raise RuntimeError("P0 fixture: external Context7 disabled")


class ScriptedProvider(OpenAICompatibleAssistantProvider):
    def __init__(self):
        super().__init__(base_url="https://synthetic.invalid/v1", api_key="synthetic", model="synthetic",
            capabilities=EndpointCapabilities("https://synthetic.invalid/v1", "synthetic",
                1048576, 65536, 4096, True, "offline P0 fixture"))
        self.calls = 0
        self.structured_calls = 0

    def send_prepared(self, request, **kwargs):
        self.calls += 1
        return ModelTurn(text="P0 隔离验证正式回答。", finish_reason="stop",
                         usage={"input_tokens": 3, "output_tokens": 2})

    def generate_json(self, *, system, prompt, max_tokens=2400):
        self.structured_calls += 1
        # An untrusted model key must never control the Runtime handoff.
        if "source" in system.lower() and "wiki" not in system.lower():
            return {"_job_completed": True, "title": "PG合成来源", "topics": ["PG事务"],
                    "summary": "合成摘要", "claims": [{"text": "事务提交前核验版本"}]}
        return {"_job_completed": True, "title": "PG事务", "page_type": "topic", "summary": "事务版本检查",
                "blocks": [{"heading": "提交前核验", "markdown": "事务提交前核验版本", "source_keys": ["s1"]}]}


@pytest.fixture
def runtime_parts(wiki_parts, record_property):
    db, _, _, space, msg, run, sources = wiki_parts
    # The inherited source fixture uses an already-running synthetic conversation.
    # Age only this isolated fixture's activity to exercise the real idle gate.
    with db.connect() as c:
        c.execute("UPDATE assistant_runs SET status='completed',completed_at=clock_timestamp()-interval '1 hour'")
        c.execute("UPDATE assistant_messages SET created_at=clock_timestamp()-interval '1 hour'")
        # SyntheticGraph seeds insertion_seq=1 explicitly; advance only this
        # fresh fixture's sequence before creating Runs through the real API.
        c.execute("SELECT nextval(pg_get_serial_sequence('shiliu.assistant_runs','insertion_seq'))")
    store = PgAssistantRunStore(db)
    provider = ScriptedProvider()
    runtime = AssistantRuntime(store=store, sources=sources, context7=OfflineContext(),
        provider_factory=lambda: provider, extraction_provider_factory=lambda: provider)
    runtime._maintenance_startup_at = "2020-01-01T00:00:00+00:00"
    record_property("isolated_database", conninfo_to_dict(db.pg.config.database_url)["dbname"])
    record_property("artifact_root", str(sources.artifacts.root))
    yield db, store, runtime, provider, space, msg, sources
    runtime.stop()
    assert runtime._thread is None
    record_property("stub_calls", json.dumps({"foreground": provider.calls, "structured": provider.structured_calls}))
    record_property("actual_cost", 0)


def enqueue(store, *, kind="source_reconcile", key="one", payload=None):
    with store.db.connect() as c:
        identity = store.enqueue_job(c, kind=kind, dedupe_key=key, payload=payload or {"video_id": -1})
        c.execute("UPDATE assistant_jobs SET created_at=clock_timestamp() WHERE id=%s", (identity,))
        return identity


def row(store, job_id):
    with store.db.connect(read_only=True) as c:
        return c.execute("SELECT * FROM assistant_jobs WHERE id=%s", (job_id,)).fetchone()


def trace_completions(monkeypatch):
    import shiliu.storage.scheduler as scheduler
    import shiliu.assistant.wiki as wiki_module
    original = scheduler.job_transition
    attempts = Counter()

    def traced(c, context, job_id, *args, **kwargs):
        if kwargs.get("action") == "complete":
            attempts[job_id] += 1
        return original(c, context, job_id, *args, **kwargs)

    monkeypatch.setattr(scheduler, "job_transition", traced)
    monkeypatch.setattr(wiki_module, "job_transition", traced)
    return attempts


def drain(runtime, *, limit=12):
    processed = []
    for _ in range(limit):
        job = runtime.store.claim_job(owner="P0-real-runtime")
        if job is None:
            return processed
        asyncio.run(runtime._process_job(job))
        processed.append(job)
    pytest.fail("unexpected unbounded fixture queue")


def test_runtime_wiki_chain_staged_resume_early_returns_and_equivalent_rebind(
    runtime_parts, wiki_parts, monkeypatch, record_property
):
    db, store, runtime, provider, space, msg, sources = runtime_parts
    vid, _, ref, captured = add_source(wiki_parts)
    attempts = trace_completions(monkeypatch)
    # Force each model-bearing stage to yield once after staging. The transaction
    # fails before publication; the original staged response/identity is retained.
    faults = Counter()
    for name in ("_commit_source_card", "apply_patch"):
        original = getattr(runtime.wiki, name)

        def once(*args, _name=name, _original=original, **kwargs):
            faults[_name] += 1
            if faults[_name] == 1:
                raise MaintenanceYield("P0 staged publication yield")
            return _original(*args, **kwargs)

        monkeypatch.setattr(runtime.wiki, name, once)
    runtime.wiki.request_topic(space_id=space, topic="PG事务", source_refs=[ref],
        request_key=f"{space}:P0", source_message_id=msg)
    jobs = drain(runtime)
    assert {j["kind"] for j in jobs} == {"source_reconcile", "source_extract", "wiki_integrate"}
    assert len(jobs) == 5 and provider.structured_calls == 2
    ids = set(j["id"] for j in jobs)
    for identity in ids:
        current = row(store, identity)
        assert current["status"] == "completed" and current["attempt"] == 1
        assert attempts[identity] == 1
        assert "_job_completed" not in (current["proposal_json"] or {})
    page = runtime.wiki.list_pages(space_id=space)[0]
    assert page["version"] == 1 and runtime.wiki.get_source_card(captured.revision)
    assert "_job_completed" not in json.dumps(page)
    assert "_job_completed" not in json.dumps(runtime.wiki.get_source_card(captured.revision))
    assert drain(runtime) == []  # completed jobs are not replayed
    assert provider.structured_calls == 2

    # Repeat a legal integration under a new Job identity: normal early no_change
    # has NOT committed a finish itself and must be completed by the Runtime.
    integration = next(j for j in jobs if j["kind"] == "wiki_integrate")
    no_change = enqueue(store, kind="wiki_integrate", key="repeat-integration", payload=integration["payload"])
    # Reusing an existing SourceCard is also an outer-finish branch.
    extraction = next(j for j in jobs if j["kind"] == "source_extract")
    reused = enqueue(store, kind="source_extract", key="repeat-extraction", payload=extraction["payload"])
    unauthorized = enqueue(store, key="unauthorized")
    drained = drain(runtime)
    assert {j["id"] for j in drained} == {no_change, reused, unauthorized}
    assert row(store, no_change)["proposal_json"]["no_change"] is True
    assert row(store, reused)["proposal_json"]["reused"] is True
    assert row(store, unauthorized)["proposal_json"]["superseded"] is True
    for identity in (no_change, reused, unauthorized):
        assert attempts[identity] == 1 and row(store, identity)["status"] == "completed"
        assert "_job_completed" not in row(store, identity)["proposal_json"]

    # Publication-time-only revision reuses the body and atomically rebinds
    # provenance. Use the real request entry to carry the NEW dirty generation.
    db.update_video(vid, published_at=1_800_000_000)
    newer = sources.snapshots.capture(vid)
    assert newer.revision != captured.revision
    runtime.wiki.request_topic(space_id=space, topic="PG事务",
        source_refs=[f"video:{vid}:{newer.revision}"],
        request_key=f"{space}:P0-time-rebind", source_message_id=msg)
    rebound_jobs = drain(runtime)
    assert {j["kind"] for j in rebound_jobs} == {"source_reconcile", "source_extract", "wiki_integrate"}
    for job in rebound_jobs:
        assert row(store, job["id"])["status"] == "completed", row(store, job["id"])["last_error_message"]
    assert runtime.wiki.get_page(page["id"])["version"] == 2
    assert provider.structured_calls == 2
    assert all(value == 1 for value in attempts.values())
    with db.connect(read_only=True) as c:
        assert not c.execute("SELECT id FROM assistant_jobs WHERE status='running'").fetchone()
        assert not c.execute("SELECT active_job_id FROM scheduler_lanes WHERE active_job_id IS NOT NULL").fetchone()
    record_property("completion_attempts", json.dumps(dict(attempts)))
    record_property("staged_yields", json.dumps(dict(faults)))


@pytest.mark.parametrize("failure", ["job_fenced", "lane_fenced", "late_business_error", "yield_after_takeover", "error_after_commit"])
def test_stale_or_completed_job_never_settles_with_old_identity(runtime_parts, monkeypatch, failure):
    db, store, runtime, _, _, _, _ = runtime_parts
    identity = enqueue(store, kind="wiki_integrate", key="stale")
    old = store.claim_job(owner="old")
    assert old["id"] == identity
    if failure == "error_after_commit":
        store.finish_job(identity, owner="old", lease_epoch=old["lease_epoch"])
    elif failure == "lane_fenced":
        # Another model job owns the lane while the old Job row still looks live.
        with db.connect() as c:
            c.execute("UPDATE scheduler_lanes SET lease_until=clock_timestamp()-interval '1 second'")
        newer_id = enqueue(store, kind="wiki_integrate", key="other-model-job")
        assert store.claim_job(owner="new")["id"] == newer_id
    else:
        with db.connect() as c:
            c.execute("UPDATE assistant_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s", (identity,))
            c.execute("UPDATE scheduler_lanes SET lease_until=clock_timestamp()-interval '1 second'")
            assert recover_job(c, db.context, identity, disposition="replay_safe")
        assert store.claim_job(owner="new")["lease_epoch"] == old["lease_epoch"] + 1
    with db.connect(read_only=True) as c:
        before_job = c.execute("SELECT * FROM assistant_jobs ORDER BY id").fetchall()
        before_lane = c.execute("SELECT * FROM scheduler_lanes").fetchall()

    def fault(*args, **kwargs):
        if failure in {"job_fenced", "lane_fenced"}:
            raise CoordinationConflict(failure)
        if failure == "yield_after_takeover":
            raise MaintenanceYield("maintenance_lease_lost")
        raise ValueError("P0 late handler/read error")

    monkeypatch.setattr(runtime.wiki, "integrate_source_card", fault)
    asyncio.run(runtime._process_job(old))
    with db.connect(read_only=True) as c:
        assert c.execute("SELECT * FROM assistant_jobs ORDER BY id").fetchall() == before_job
        assert c.execute("SELECT * FROM scheduler_lanes").fetchall() == before_lane


def wait_until(predicate, *, seconds=8):
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, "P0 bounded runtime wait expired"
        time.sleep(.02)


def test_shared_runtime_survives_claim_business_fence_and_heartbeat_faults_then_answers_and_restarts(
    runtime_parts, monkeypatch, record_property
):
    db, store, runtime, provider, space, _, _ = runtime_parts
    broken = enqueue(store, key="business-error", payload={"fault": "business"})
    stale = enqueue(store, key="stale-error", payload={"fault": "stale"})
    good = enqueue(store, key="legal-superseded")
    original_claim = store.claim_job
    original_reconcile = runtime.wiki.reconcile
    rounds = Counter()

    def claim(**kwargs):
        rounds["claim"] += 1
        if rounds["claim"] == 1:
            raise RuntimeError("P0 transient claim error")
        return original_claim(**kwargs)

    def reconcile(job):
        if job["id"] == broken:
            # Let the independently scheduled heartbeat finish with an error.
            time.sleep(.05)
            raise ValueError("P0 genuine background business error")
        if job["id"] == stale:
            with db.connect() as c:
                c.execute("UPDATE assistant_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s", (stale,))
                assert recover_job(c, db.context, stale, disposition="replay_safe")
            new = original_claim(owner="P0-new-owner", kinds={"source_reconcile"})
            assert new["id"] == stale
            rounds["takeover_epoch"] = new["lease_epoch"]
            raise CoordinationConflict("job_fenced")
        return original_reconcile(job)

    async def heartbeat(job):
        if job["id"] == broken:
            raise RuntimeError("P0 transient heartbeat failure")
        await original_heartbeat(job)

    original_heartbeat = runtime._heartbeat_job
    monkeypatch.setattr(store, "claim_job", claim)
    monkeypatch.setattr(runtime.wiki, "reconcile", reconcile)
    monkeypatch.setattr(runtime, "_heartbeat_job", heartbeat)
    # Accelerate only the existing no-job/error poll, retaining an awaited delay.
    import shiliu.assistant.runtime as runtime_module
    real_sleep = asyncio.sleep

    async def quick_poll(delay):
        await real_sleep(.02 if delay == 15 else delay)

    monkeypatch.setattr(runtime_module.asyncio, "sleep", quick_poll)
    try:
        runtime.start()
        thread = runtime._thread
        runtime.start()
        assert runtime._thread is thread
        wait_until(lambda: row(store, good)["status"] == "completed")
        bad = row(store, broken)
        assert bad["status"] == "retry_wait" and bad["attempt"] == 1
        assert bad["last_error_code"] == "ValueError" and bad["not_before"] > bad["updated_at"]
        taken = row(store, stale)
        assert taken["status"] == "running" and taken["lease_owner"] == "P0-new-owner"
        assert taken["lease_epoch"] == rounds["takeover_epoch"] and taken["last_error_code"] is None
        chat = store.create_thread(space)
        queued = store.create_run(chat["id"], text="你好", request_id="P0-original-message")
        original_message = store.get_thread(chat["id"])["messages"][0]["id"]
        wait_until(lambda: store.get_run(queued["id"])["status"] == "completed")
        history = store.get_thread(chat["id"])
        assert history["messages"][0]["id"] == original_message
        assert history["messages"][-1]["role"] == "assistant"
        assert history["messages"][-1]["content"] == "P0 隔离验证正式回答。"
        assert provider.calls == 1 and thread.is_alive()
        assert runtime.capabilities()["runtime"] == "ready"
        runtime.stop()
        assert runtime._thread is None and runtime.capabilities()["runtime"] == "stopped"
        runtime.start()
        assert runtime._thread is not thread and runtime._thread.is_alive()
        again = store.create_run(chat["id"], text="谢谢", request_id="P0-after-restart")
        wait_until(lambda: store.get_run(again["id"])["status"] == "completed")
        assert provider.calls == 2
        assert store.create_run(chat["id"], text="你好", request_id="P0-original-message")["id"] == queued["id"]
        record_property("run_ids", json.dumps([queued["id"], again["id"]]))
        record_property("original_user_message", original_message)
        record_property("fault_rounds", json.dumps(dict(rounds)))
    finally:
        runtime.stop()
    assert runtime._active_maintenance_job is None


def test_process_job_cancellation_propagates_and_joins_heartbeat(runtime_parts, monkeypatch):
    _, store, runtime, _, _, _, _ = runtime_parts
    identity = enqueue(store)
    claimed = store.claim_job(owner="cancel")
    joined = []

    async def heartbeat(job):
        try:
            await asyncio.Event().wait()
        finally:
            joined.append(job["id"])

    async def blocked(job):
        await asyncio.Event().wait()

    monkeypatch.setattr(runtime, "_heartbeat_job", heartbeat)
    monkeypatch.setattr(runtime, "_extract_memories", blocked)
    # The extraction entry lets cancellation be deterministic without a to_thread
    # transport that cannot itself be cancelled. Ownership stays real PG.
    claimed = {**claimed, "kind": "memory_extract"}

    async def cancel():
        task = asyncio.create_task(runtime._process_job(claimed))
        await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]

    asyncio.run(cancel())
    assert joined == [identity] and runtime._active_maintenance_job is None
    assert row(store, identity)["status"] == "running"
