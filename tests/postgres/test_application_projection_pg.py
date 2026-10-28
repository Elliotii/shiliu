"""P4-R1: Application consumes durable local projections without execution hints."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from psycopg.types.json import Jsonb

from shiliu.app import Application
from shiliu.config import AppConfig
from shiliu.retrieval.coordinator import ProjectionWorker
from shiliu.assistant.wiki_jobs import WikiProjectionWorker
from shiliu.storage.errors import StorageError
from test_application_pg import application_target  # noqa: F401
from test_collection_retrieval import FixedProvider, add_video


class ProjectionProvider(FixedProvider):
    # Wiki's established query protocol supplies its own instruction.
    def embed_query(self, text, *, instruction=None):
        return super().embed_query(text)


@pytest.fixture
def projection_apps(application_target, app_paths):  # noqa: F811
    cores = []

    class Offline:
        async def connect(self):
            raise RuntimeError("synthetic offline Context7")

    def create(*, assistant=True, provider=None):
        core = Application(
            app_paths,
            config=AppConfig(
                content_dir=str(app_paths.content_dir), assistant_enabled=assistant
            ),
            postgres_config=application_target[0],
            embedding_provider=provider or ProjectionProvider(),
            adapter=object(),
            context7=Offline(),
            assistant_provider_factory=lambda: None,
            provider_availability=lambda: {
                "available": False,
                "reason": "synthetic offline",
            },
        )
        cores.append(core)
        return core

    try:
        yield create
    finally:
        for core in reversed(cores):
            core.close()


def tasks(core):
    with core.db.connect(read_only=True) as c:
        return c.execute(
            "SELECT * FROM retrieval_projection_tasks WHERE workspace_id=%s ORDER BY domain,id",
            (core.context.workspace_id,),
        ).fetchall()


def wait_for(core, predicate, *, timeout=None):
    deadline = time.monotonic() + (timeout or 3 * core.PROJECTION_POLL_SECONDS + 3)
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    assert predicate(), (tasks(core), core._projection_status)


def collection(core, index=1):
    # Model/profile activation is an explicit existing contract. Activate the
    # configured profile on the empty test corpus before registering any work;
    # the lifecycle consumer must not choose/activate a profile itself.
    if core.dense_retrieval.active_profile() is None:
        assert core.db.list_videos() == []
        core.dense_retrieval.register()
        core.dense_retrieval.activate()
    return add_video(
        (core.db, core.artifacts, core.retrieval, core.dense_retrieval),
        index=index,
        text="PostgreSQL事务与数据库连接池",
    )[1]


def wiki_page(core, suffix="main"):
    store, wiki = core.assistant_runtime.store, core.assistant_runtime.wiki
    space = store.create_space(name=f"projection-{suffix}")
    thread = store.create_thread(space["id"])
    run = store.create_run(
        thread["id"], text="请保存数据库事务讨论", request_id=f"projection-{suffix}"
    )
    message = store.get_thread(thread["id"])["messages"][0]["id"]
    store.cancel_run(run["id"])
    page = wiki.save_discussion(
        space_id=space["id"],
        title="数据库事务",
        purpose="synthetic projection",
        source_message_id=message,
        operation_key=f"projection-{suffix}",
        blocks=[
            dict(
                role="analysis",
                heading="事务",
                markdown="数据库事务通过版本与锁保护写入。",
            )
        ],
    )
    missing = wiki.retrieval.search("数据库事务", space_id=space["id"])
    assert missing["coverage"]["missing_windows"] > 0
    return page["id"], space["id"]


def test_actual_application_publishes_collection_and_wiki_without_manual_drain(
    projection_apps,
):
    core = projection_apps()
    video_id = collection(core)
    page_id, space_id = wiki_page(core)
    assert {r["domain"] for r in tasks(core)} == {"collection", "wiki"}
    core.start(background_tasks=True)
    thread = core._projection_thread
    core.start(background_tasks=True)
    assert core._projection_thread is thread and not thread.daemon
    wait_for(core, lambda: all(r["status"] == "completed" for r in tasks(core)))
    assert (
        core.retrieval.search("数据库", level="transcript_chunk")[0].video_id
        == video_id
    )
    assert core.dense_retrieval.search("数据库")[0].video_id == video_id
    result = core.assistant_runtime.wiki.retrieval.search(
        "数据库事务", space_id=space_id
    )
    assert (
        result["coverage"]["missing_windows"] == 0
        and result["coverage"]["dense_candidates"] > 0
    )
    assert any(p["page_id"] == page_id for p in result["candidates"])
    assert core.health()["projection_maintenance"]["running"]
    core.close()
    core.close()
    assert not thread.is_alive() and core.pg._pool.closed


def test_collection_paused_without_background_then_restart_without_assistant(
    projection_apps,
):
    first = projection_apps(assistant=False)
    video_id = collection(first)
    first.start(background_tasks=False)
    time.sleep(first.PROJECTION_POLL_SECONDS + 0.1)
    assert first._projection_thread is None
    assert all(r["status"] == "queued" and r["attempt"] == 0 for r in tasks(first))
    first.close()
    restarted = projection_apps(assistant=False)
    restarted.start(background_tasks=True)
    assert restarted._assistant_runtime is None and restarted._wiki_projection is None
    wait_for(
        restarted, lambda: all(r["status"] == "completed" for r in tasks(restarted))
    )
    assert restarted.dense_retrieval.search("数据库")[0].video_id == video_id
    assert restarted.health()["projection_maintenance"]["wiki"]["state"] == "disabled"


@pytest.mark.parametrize("leftover", ["expired", "due_retry"])
def test_actual_startup_recovers_both_domains_and_preserves_failed_future(
    projection_apps, leftover
):
    core = projection_apps()
    main_video = collection(core)
    main_page, main_space = wiki_page(core)
    failed_video, future_video = collection(core, 2), collection(core, 3)
    failed_page, _ = wiki_page(core, "failed")
    future_page, _ = wiki_page(core, "future")
    # Later formal writes may supersede an older scope/dependency snapshot.
    # Request the current main projection after arranging those writes.
    core.assistant_runtime.wiki.retrieval.search("数据库事务", space_id=main_space)
    old_collection = ProjectionWorker(
        core.retrieval, core.dense_retrieval, owner="gone-collection"
    )
    collection_claim = old_collection.claim(video_id=main_video)
    old_wiki = WikiProjectionWorker(
        core.assistant_runtime.wiki.retrieval, owner="gone-wiki"
    )
    wiki_claim = old_wiki.claim()
    assert wiki_claim["resource_key"] == main_page
    if leftover == "due_retry":
        old_collection.fail(collection_claim, "synthetic_retry")
        old_wiki.fail(wiki_claim, RuntimeError("synthetic retry"))
    with core.db.connect() as c:
        for claim in (collection_claim, wiki_claim):
            if leftover == "expired":
                c.execute(
                    "UPDATE retrieval_projection_tasks SET lease_until=clock_timestamp()-interval '1 second' WHERE workspace_id=%s AND id=%s",
                    (core.context.workspace_id, claim["id"]),
                )
            else:
                c.execute(
                    "UPDATE retrieval_projection_tasks SET not_before=clock_timestamp()-interval '1 second' WHERE workspace_id=%s AND id=%s",
                    (core.context.workspace_id, claim["id"]),
                )
        for row in tasks(core):
            if row["resource_key"] in {str(failed_video), failed_page}:
                payload = dict(row["payload"])
                if row["domain"] == "wiki":
                    payload["request_states"] = {
                        k: "failed" for k in payload["requests"]
                    }
                    payload["request_attempts"] = {k: 5 for k in payload["requests"]}
                c.execute(
                    "UPDATE retrieval_projection_tasks SET status='failed',attempt=5,payload=%s WHERE workspace_id=%s AND id=%s",
                    (Jsonb(payload), core.context.workspace_id, row["id"]),
                )
            if row["resource_key"] in {str(future_video), future_page}:
                c.execute(
                    "UPDATE retrieval_projection_tasks SET not_before=clock_timestamp()+interval '1 hour' WHERE workspace_id=%s AND id=%s",
                    (core.context.workspace_id, row["id"]),
                )
    untouched = {
        r["id"]: r
        for r in tasks(core)
        if r["resource_key"]
        in {str(failed_video), failed_page, str(future_video), future_page}
    }
    core.close()
    core = projection_apps()  # a new Application/pool recovers durable old owners
    core.start(background_tasks=True)
    wait_for(
        core,
        lambda: all(
            r["status"] == "completed"
            for r in tasks(core)
            if r["resource_key"] in {str(main_video), main_page}
        ),
    )
    for row in tasks(core):
        if row["id"] in untouched:
            assert row == untouched[row["id"]]
        else:
            assert row["attempt"] == 2 and row["lease_epoch"] == 2
    result = core.assistant_runtime.wiki.retrieval.search(
        "数据库事务", space_id=main_space
    )
    assert result["coverage"]["dense_candidates"] > 0


@pytest.mark.parametrize("domain", ["collection", "wiki"])
def test_close_drains_local_encoder_and_renewal_before_pool(projection_apps, domain):
    entered, release = threading.Event(), threading.Event()

    class Blocking(ProjectionProvider):
        def embed_documents(self, texts):
            entered.set()
            assert release.wait(10)
            return super().embed_documents(texts)

    core = projection_apps(assistant=domain == "wiki", provider=Blocking())
    if domain == "collection":
        collection(core)
        collection(core, 2)  # no second claim after stop
    else:
        _, main_space = wiki_page(core)
        wiki_page(core, "next")
        core.assistant_runtime.wiki.retrieval.search("数据库事务", space_id=main_space)
    core.start(background_tasks=True)
    try:
        assert entered.wait(3)
        renewal = [
            t
            for t in threading.enumerate()
            if t.name == "projection-lease" or t.name.startswith("shiliu-p3-renewal-")
        ]
        assert len(renewal) == 1
        with core.db.connect(read_only=True) as c:
            assert (
                c.execute(
                    "SELECT count(*) AS n FROM pg_stat_activity WHERE datname=current_database() AND state='idle in transaction'"
                ).fetchone()["n"]
                == 0
            )
        with ThreadPoolExecutor(max_workers=1) as executor:
            closing = executor.submit(core.close)
            try:
                deadline = time.monotonic() + 2
                while (
                    not core._projection_stop.is_set() and time.monotonic() < deadline
                ):
                    time.sleep(0.01)
                assert core._projection_stop.is_set() and not core.pg._pool.closed
                assert core._projection_thread.is_alive()
                assert sorted(r["attempt"] for r in tasks(core)) == [0, 1]
            finally:
                release.set()
            closing.result(timeout=20)
        assert core.pg._pool.closed and not core._projection_thread.is_alive()
        assert all(not t.is_alive() for t in renewal)
    finally:
        release.set()
        core.close()


def test_projection_recovery_failure_unwinds_startup_without_pool_or_worker(
    projection_apps, monkeypatch
):
    core = projection_apps(assistant=False)

    def unavailable(self):
        raise StorageError("pool_timeout")

    monkeypatch.setattr(ProjectionWorker, "recover", unavailable)
    with pytest.raises(StorageError, match="pool_timeout"):
        core.start(background_tasks=True)
    assert core.pg._pool.closed and core._projection_thread is None


def test_continuous_mixed_rounds_accept_new_work_and_leave_no_claims(projection_apps):
    core = projection_apps()
    core.start(background_tasks=True)
    thread = core._projection_thread
    snapshots = {}
    for round_number in range(1, 4):
        video_id = collection(core, round_number)
        page_id, space_id = wiki_page(core, f"continuous-{round_number}")
        # Actual Assistant lifecycle is exercised by wiki_page's run/cancel;
        # Research creates independent durable work while projections poll.
        created = core.research.create_task(
            command_id=f"continuous-{round_number}",
            objective="synthetic offline continuous lifecycle",
        )
        task_id = created["task_id"]
        assert core.research.get_task(task_id)["task"]["task_id"] == task_id
        wait_for(core, lambda: all(r["status"] == "completed" for r in tasks(core)))
        assert core.dense_retrieval.search("数据库")[0].video_id in range(
            1, round_number + 1
        )
        result = core.assistant_runtime.wiki.retrieval.search(
            "数据库", space_id=space_id
        )
        assert any(p["page_id"] == page_id for p in result["candidates"])
        assert core.db.get_video(video_id)["status"] == "completed"
        current = {r["id"]: (r["lease_epoch"], r["attempt"]) for r in tasks(core)}
        assert all(current[k] == value for k, value in snapshots.items())
        snapshots = current
        # Observe another poll with no work: no completed task is claimed again.
        time.sleep(core.PROJECTION_POLL_SECONDS + 0.05)
        assert {
            r["id"]: (r["lease_epoch"], r["attempt"]) for r in tasks(core)
        } == snapshots
    assert len(tasks(core)) >= 6
    core.close()
    assert not thread.is_alive() and core.pg._pool.closed
    assert core.research_recovery.run_once() is None
