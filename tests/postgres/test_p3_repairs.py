# ruff: noqa: F811
"""Supervisor probes migrated as expected P3 repair contracts (synthetic PG)."""

from test_wiki import wiki_parts, create  # noqa: F401
from test_wiki_retrieval import wiki_index
from test_collection_retrieval import FixedProvider
import pytest
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.memory_jobs import MemoryJobWorker
from shiliu.assistant.wiki_retrieval import WikiHybridIndex
from shiliu.assistant.wiki_jobs import WikiProjectionWorker


def test_forget_cleans_windows_from_suppressed_message_without_direct_memory_dep(
    wiki_parts,
):
    db, _, wiki, space, msg, _, _ = wiki_parts
    text = "我喜欢白天学习数据库"
    page = wiki.save_discussion(
        space_id=space,
        title="个人学习偏好",
        purpose="记录个人偏好",
        source_message_id=msg,
        operation_key="supervisor-personal",
        blocks=[
            dict(
                role="personal",
                heading="个人偏好",
                markdown=text,
                user_quote=text,
                user_message_id=msg,
            )
        ],
    )
    index, worker = wiki_index(wiki_parts)
    assert index.search("学习", space_id=space)["candidates"]
    assert worker.run_once()["status"] == "ready"
    with db.connect(read_only=True) as c:
        before = c.execute(
            "SELECT window_id,text,dependency_versions FROM wiki_windows WHERE page_id=%s AND position(%s in text)>0",
            (page["id"], text),
        ).fetchall()
    assert before
    memories = MemoryService(db)
    m = memories.save_explicit(
        text=text,
        subject_key="preference",
        kind="preference",
        scope_kind="user",
        scope_id=None,
        operation_key="supervisor-save",
        source_message_ids=[msg],
    )
    memories.forget(m["id"], expected_version=1, operation_key="supervisor-forget")
    assert not wiki.get_page(page["id"], space_id=space)["blocks"]
    assert (
        MemoryJobWorker(memories, owner="supervisor-purge").run_once()["status"]
        == "purged"
    )
    with db.connect(read_only=True) as c:
        remaining = c.execute(
            "SELECT w.window_id,w.text,w.dependency_versions,(SELECT count(*) FROM wiki_embeddings e WHERE e.window_id=w.window_id) AS vectors FROM wiki_windows w WHERE w.page_id=%s AND position(%s in w.text)>0",
            (page["id"], text),
        ).fetchall()
    assert remaining == [], (
        "Forgotten source-message quote survives in online Wiki text/vector cache"
    )


def test_wrong_profile_worker_cannot_complete_unbuilt_wiki_request(wiki_parts):
    db, _, wiki, space, msg, _, _ = wiki_parts
    create(wiki, space, msg)
    requested_index = WikiHybridIndex(FixedProvider("requested-profile-A"), wiki=wiki)
    assert (
        requested_index.search("事务", space_id=space)["coverage"]["missing_windows"]
        > 0
    )
    with db.connect(read_only=True) as c:
        before = c.execute(
            "SELECT id,status,requested_generation,payload FROM retrieval_projection_tasks WHERE domain='wiki'"
        ).fetchone()
    wrong = WikiProjectionWorker(
        WikiHybridIndex(FixedProvider("wrong-profile-B"), wiki=wiki),
        owner="supervisor-wrong-profile",
    )
    result = wrong.run_once()
    with db.connect(read_only=True) as c:
        after = c.execute(
            "SELECT id,status,requested_generation,payload FROM retrieval_projection_tasks WHERE id=%s",
            (before["id"],),
        ).fetchone()
        count = c.execute("SELECT count(*) AS n FROM wiki_windows").fetchone()["n"]
    requested_worker_result = WikiProjectionWorker(
        requested_index, owner="supervisor-correct-profile"
    ).run_once()
    assert after["status"] != "completed", (
        "Wrong-profile worker consumed request without publishing any requested windows"
    )
    assert result is None and count == 0 and after == before
    assert requested_worker_result["status"] == "ready"


@pytest.fixture
def other_parts(wiki_parts, tmp_path):
    from shiliu.db import Database
    from shiliu.storage.scope import ResourceContext
    from shiliu.assistant.pg_access import PgAssistantAccess
    from shiliu.assistant.wiki import WikiService
    from shiliu.artifacts import ArtifactStore
    from shiliu.assistant.sources import CollectionSourceService
    from shiliu.assistant.snapshots import SourceSnapshotStore
    from seed_rows import SyntheticGraph

    db = wiki_parts[0]
    with db.connect() as c:
        c.execute(
            "INSERT INTO users(id,display_name,created_at) VALUES('supervisor_owner','Synthetic',clock_timestamp())"
        )
        c.execute(
            "INSERT INTO workspaces(id,kind,owner_user_id,created_at) VALUES('personal:supervisor_owner','personal','supervisor_owner',clock_timestamp())"
        )
        c.execute(
            "INSERT INTO workspace_guards(workspace_id) VALUES('personal:supervisor_owner')"
        )
        graph = SyntheticGraph(
            c,
            workspace="personal:supervisor_owner",
            user="supervisor_owner",
            suffix="_supervisor",
            numeric_id=300,
        )
        msg = graph.ensure("assistant_messages")
        run = graph.ensure("assistant_runs")
        space = graph.rows["assistant_spaces"]
        c.execute(
            "UPDATE assistant_spaces SET enabled=true,all_active=true WHERE id=%s",
            (space["id"],),
        )
        c.execute(
            "UPDATE assistant_messages SET role='user',run_id=%s,content='请保存这次讨论' WHERE id=%s",
            (run["id"], msg["id"]),
        )
    otherdb = Database(
        db.pg, ResourceContext("personal:supervisor_owner", "supervisor_owner")
    )
    artifacts = ArtifactStore(tmp_path / "supervisor-other-owner", otherdb)
    sources = CollectionSourceService(
        db=otherdb,
        artifacts=artifacts,
        snapshots=SourceSnapshotStore(otherdb, artifacts),
    )
    wiki = WikiService(
        db=otherdb,
        store=PgAssistantAccess(otherdb),
        sources=sources,
        principal_id="supervisor_owner",
    )
    return otherdb, wiki.store, wiki, space["id"], msg["id"], run["id"], sources


def test_other_owner_can_create_and_read_own_wiki_page(other_parts, wiki_parts):
    db, _, wiki, space, msg, _, _ = other_parts
    page = create(wiki, space, msg)
    assert wiki.get_page(page["id"], space_id=space)["blocks"]
    local = create(wiki_parts[2], wiki_parts[3], wiki_parts[4])
    assert (
        local["id"] != page["id"]
    )  # identical receipt key stays in its principal scope
    with pytest.raises((KeyError, ValueError)):
        wiki_parts[2].get_page(page["id"], space_id=wiki_parts[3])
    with pytest.raises((KeyError, ValueError)):
        wiki.get_page(local["id"], space_id=space)
    with pytest.raises(ValueError, match="principal_context_mismatch"):
        MemoryService(db)
    memories = MemoryService(db, principal_id=db.context.user_id)
    memory = memories.save_explicit(
        text="自己的个人偏好",
        subject_key="own",
        kind="preference",
        scope_kind="user",
        scope_id=None,
        source_message_ids=[msg],
        operation_key="own-memory",
    )
    page = wiki.add_personal_note(
        page["id"],
        space_id=space,
        text=memory["text"],
        memory_id=memory["id"],
        memory_version=1,
        expected_version=1,
        operation_key="own-note",
    )
    index = WikiHybridIndex(FixedProvider(), wiki=wiki)
    assert index.search("个人偏好", space_id=space)["candidates"]
    assert (
        WikiProjectionWorker(index, owner="own-worker").run_once()["status"] == "ready"
    )
    memories.forget(memory["id"], expected_version=1, operation_key="own-forget")
    assert msg in memories.suppressed_source_message_ids(space_id=space)
    assert msg not in MemoryService(wiki_parts[0]).suppressed_source_message_ids(
        space_id=wiki_parts[3]
    )
    assert (
        MemoryJobWorker(memories, owner="own-purger").run_once()["status"] == "purged"
    )
    assert not wiki.get_page(page["id"], space_id=space)[
        "blocks"
    ] or "自己的个人偏好" not in str(
        wiki.get_page(page["id"], space_id=space)["blocks"]
    )
    assert wiki_parts[2].get_page(local["id"], space_id=wiki_parts[3])["blocks"]


@pytest.mark.parametrize("scope_kind", ["user", "space"])
@pytest.mark.parametrize("history", [False, True])
def test_message_snapshot_forget_scope_history_idempotence(
    wiki_parts, other_parts, scope_kind, history
):
    from psycopg.types.json import Jsonb

    db, _, wiki, space, msg, _, _ = wiki_parts
    text = "我喜欢白天学习数据库"
    quote = wiki.save_discussion(
        space_id=space,
        title="敏感原话",
        purpose="引用",
        source_message_id=msg,
        operation_key="quote",
        blocks=[
            dict(
                role="personal",
                heading="原话",
                markdown=text,
                user_quote=text,
                user_message_id=msg,
            )
        ],
    )
    independent = create(wiki, space, msg, op="independent")
    foreign = create(other_parts[2], other_parts[3], other_parts[4])
    index, worker = wiki_index(wiki_parts)
    index.search("学习", space_id=space)
    while worker.run_once() is not None:
        pass
    foreign_index = WikiHybridIndex(FixedProvider(), wiki=other_parts[2])
    foreign_index.search("事务", space_id=other_parts[3])
    assert (
        WikiProjectionWorker(foreign_index, owner="foreign").run_once()["status"]
        == "ready"
    )
    with db.connect() as c:
        rows = c.execute(
            "SELECT window_id,dependency_versions FROM wiki_windows WHERE page_id=%s",
            (quote["id"],),
        ).fetchall()
        assert rows and all(msg in r["dependency_versions"]["messages"] for r in rows)
        keep = c.execute(
            "SELECT window_id FROM wiki_windows WHERE page_id=%s", (foreign["id"],)
        ).fetchall()
        if history:
            c.execute(
                "UPDATE assistant_wiki_pages SET blocks_json=%s,version=version+1 WHERE id=%s",
                (Jsonb([]), quote["id"]),
            )
            c.execute(
                "DELETE FROM assistant_wiki_personal_dependencies WHERE page_id=%s",
                (quote["id"],),
            )
    memories = MemoryService(db)
    memory = memories.save_explicit(
        text=text,
        subject_key="quote",
        kind="preference",
        scope_kind=scope_kind,
        scope_id=space if scope_kind == "space" else None,
        operation_key="memory",
        source_message_ids=[msg],
    )
    memories.forget(memory["id"], expected_version=1, operation_key="forget")
    purger = MemoryJobWorker(memories, owner="purger")
    assert purger.run_once()["status"] == "purged"
    with db.connect() as c:
        memories.store.enqueue_job(
            c,
            kind="memory_purge",
            dedupe_key="purge-again",
            payload={"memory_id": memory["id"], "version": 2},
        )
    assert purger.run_once()["status"] == "purged"
    memories.forget(memory["id"], expected_version=2, operation_key="repeat-forget")
    with db.connect() as c:
        assert not c.execute(
            "SELECT 1 FROM wiki_windows WHERE page_id=%s", (quote["id"],)
        ).fetchall()
        assert not c.execute(
            "SELECT 1 FROM wiki_embeddings WHERE window_id=ANY(%s)",
            ([r["window_id"] for r in rows],),
        ).fetchall()
        assert (
            c.execute(
                "SELECT window_id FROM wiki_windows WHERE page_id=%s", (foreign["id"],)
            ).fetchall()
            == keep
        )
        assert wiki.get_page(independent["id"], space_id=space)["blocks"]


def test_narrow_undo_does_not_erase_message_quote_cache(wiki_parts):
    db, _, wiki, space, msg, _, _ = wiki_parts
    text = "我喜欢白天学习数据库"
    quote = wiki.save_discussion(
        space_id=space,
        title="独立原话",
        purpose="引用",
        source_message_id=msg,
        operation_key="quote",
        blocks=[
            dict(
                role="personal",
                heading="原话",
                markdown=text,
                user_quote=text,
                user_message_id=msg,
            )
        ],
    )
    index, worker = wiki_index(wiki_parts)
    index.search("学习", space_id=space)
    worker.run_once()
    memories = MemoryService(db)
    memory = memories.save_explicit(
        text=text,
        subject_key="quote",
        kind="preference",
        scope_kind="user",
        scope_id=None,
        operation_key="memory",
        source_message_ids=[msg],
    )
    memories.undo_created(
        memory["id"],
        save_operation_key="memory",
        expected_version=1,
        operation_key="undo",
    )
    assert MemoryJobWorker(memories, owner="purger").run_once()["status"] == "purged"
    assert wiki.get_page(quote["id"], space_id=space)["blocks"]
    with db.connect() as c:
        assert c.execute(
            "SELECT 1 FROM wiki_windows WHERE page_id=%s", (quote["id"],)
        ).fetchone()


def test_message_forget_during_encoding_cannot_republish_quote(wiki_parts):
    from shiliu.assistant.wiki_jobs import WikiProjectionStale

    db, _, wiki, space, msg, _, _ = wiki_parts
    text = "我喜欢白天学习数据库"
    wiki.save_discussion(
        space_id=space,
        title="个人原话",
        purpose="引用",
        source_message_id=msg,
        operation_key="quote",
        blocks=[
            dict(
                role="personal",
                heading="原话",
                markdown=text,
                user_quote=text,
                user_message_id=msg,
            )
        ],
    )
    index, worker = wiki_index(wiki_parts)
    index.search("学习", space_id=space)
    claim = worker.claim()
    computed = worker.compute(claim)
    memories = MemoryService(db)
    memory = memories.save_explicit(
        text=text,
        subject_key="quote",
        kind="preference",
        scope_kind="user",
        scope_id=None,
        operation_key="memory",
        source_message_ids=[msg],
    )
    memories.forget(memory["id"], expected_version=1, operation_key="forget")
    with pytest.raises(WikiProjectionStale):
        worker.publish(claim, computed)
    with db.connect() as c:
        assert not c.execute("SELECT 1 FROM wiki_windows").fetchone()
        assert not c.execute("SELECT 1 FROM wiki_embeddings").fetchone()


def test_mixed_profile_scope_requests_remain_pending_until_each_worker_builds(
    wiki_parts,
):
    db, _, wiki, space, msg, _, _ = wiki_parts
    page = create(wiki, space, msg)
    a = WikiHybridIndex(FixedProvider("A"), wiki=wiki)
    b = WikiHybridIndex(FixedProvider("B"), wiki=wiki)
    a.search("事务", space_id=space)
    a.search("事务", space_id=space, thread_id="assistant_threads_id")
    b.search("事务", space_id=space)
    wa = WikiProjectionWorker(a, owner="A")
    wb = WikiProjectionWorker(b, owner="B")
    assert wa.run_once()["status"] == "ready"
    with db.connect() as c:
        row = c.execute(
            "SELECT * FROM retrieval_projection_tasks WHERE resource_key=%s",
            (page["id"],),
        ).fetchone()
        assert row["status"] == "queued"
        assert sorted(row["payload"]["request_states"].values()) == [
            "completed",
            "completed",
        ]
        assert (
            c.execute(
                "SELECT count(*) AS n FROM wiki_embeddings WHERE profile_id=%s",
                (b.profile.profile_id,),
            ).fetchone()["n"]
            == 0
        )
    assert wa.run_once() is None
    assert wb.run_once()["status"] == "ready"  # no new query
    with db.connect() as c:
        row = c.execute(
            "SELECT * FROM retrieval_projection_tasks WHERE id=%s", (row["id"],)
        ).fetchone()
        assert row["status"] == "completed" and set(
            row["payload"]["request_states"].values()
        ) == {"completed"}
        assert c.execute(
            "SELECT 1 FROM wiki_embeddings WHERE profile_id=%s", (b.profile.profile_id,)
        ).fetchone()


def test_unrelated_profile_query_does_not_requeue_failed_request(wiki_parts):
    db, _, wiki, space, msg, _, _ = wiki_parts
    page = create(wiki, space, msg)
    a = WikiHybridIndex(FixedProvider("A"), wiki=wiki)
    b = WikiHybridIndex(FixedProvider("B"), wiki=wiki)
    a.search("事务", space_id=space)
    wa = WikiProjectionWorker(a, owner="A")
    for i in range(5):
        claim = wa.claim()
        assert claim and claim["attempt"] == i + 1
        wa.fail(claim, RuntimeError("synthetic failure"))
        with db.connect() as c:
            c.execute(
                "UPDATE retrieval_projection_tasks SET not_before=clock_timestamp() WHERE id=%s",
                (claim["id"],),
            )
    b.search("事务", space_id=space)
    assert wa.run_once() is None
    assert WikiProjectionWorker(b, owner="B").run_once()["status"] == "ready"
    assert (
        a.search("事务", space_id=space)["coverage"]["degraded_reason"]
        == "wiki_projection_failed_manual_retry_required"
    )
    with db.connect() as c:
        row = c.execute(
            "SELECT * FROM retrieval_projection_tasks WHERE id=%s", (claim["id"],)
        ).fetchone()
        assert row["status"] == "failed"
        assert sorted(row["payload"]["request_states"].values()) == [
            "completed",
            "failed",
        ]
    assert wa.requeue_failed(page["id"])
    assert wa.run_once()["status"] == "ready"


def test_new_profile_request_during_compute_fences_old_payload_without_loss(wiki_parts):
    from shiliu.assistant.wiki_jobs import WikiProjectionStale

    db, _, wiki, space, msg, _, _ = wiki_parts
    create(wiki, space, msg)
    a = WikiHybridIndex(FixedProvider("A"), wiki=wiki)
    b = WikiHybridIndex(FixedProvider("B"), wiki=wiki)
    a.search("事务", space_id=space)
    wa = WikiProjectionWorker(a, owner="A")
    claim = wa.claim()
    computed = wa.compute(claim)
    b.search("事务", space_id=space)
    with pytest.raises(WikiProjectionStale):
        wa.publish(claim, computed)
    assert wa.run_once()["status"] == "ready"
    assert WikiProjectionWorker(b, owner="B").run_once()["status"] == "ready"
    with db.connect() as c:
        row = c.execute(
            "SELECT * FROM retrieval_projection_tasks WHERE id=%s", (claim["id"],)
        ).fetchone()
        assert (
            row["status"] == "completed"
            and row["requested_generation"] > claim["requested_generation"]
        )


def test_empty_computation_cannot_acknowledge_current_request(wiki_parts):
    from shiliu.assistant.wiki_jobs import WikiProjectionStale

    db, _, wiki, space, msg, _, _ = wiki_parts
    create(wiki, space, msg)
    index, worker = wiki_index(wiki_parts)
    index.search("事务", space_id=space)
    claim = worker.claim()
    with db.connect() as c:
        before = c.execute(
            "SELECT to_jsonb(t) AS value FROM retrieval_projection_tasks t WHERE id=%s",
            (claim["id"],),
        ).fetchone()["value"]
    with pytest.raises(WikiProjectionStale, match="request_unprocessed"):
        worker.publish(claim, [])
    with db.connect() as c:
        assert (
            c.execute(
                "SELECT to_jsonb(t) AS value FROM retrieval_projection_tasks t WHERE id=%s",
                (claim["id"],),
            ).fetchone()["value"]
            == before
        )
        assert not c.execute("SELECT 1 FROM wiki_windows").fetchone()


def test_tokenizer_failure_keeps_valid_request_retryable(wiki_parts, monkeypatch):
    db, _, wiki, space, msg, _, _ = wiki_parts
    create(wiki, space, msg)
    index, worker = wiki_index(wiki_parts)
    index.search("事务", space_id=space)

    def unavailable(*args):
        raise RuntimeError("synthetic tokenizer unavailable")

    monkeypatch.setattr(index.provider, "count_tokens", unavailable)
    assert worker.run_once()["status"] == "retry_wait"
    with db.connect() as c:
        row = c.execute(
            "SELECT * FROM retrieval_projection_tasks WHERE domain='wiki'"
        ).fetchone()
        assert row["status"] == "retry_wait" and not row["payload"]["request_states"]
        c.execute(
            "UPDATE retrieval_projection_tasks SET not_before=clock_timestamp() WHERE id=%s",
            (row["id"],),
        )
    monkeypatch.undo()
    assert worker.run_once()["status"] == "ready"  # same persisted request, no query


def test_only_proven_obsolete_request_is_recorded_stale(wiki_parts):
    db, _, wiki, space, msg, _, _ = wiki_parts
    page = create(wiki, space, msg)
    index, worker = wiki_index(wiki_parts)
    index.search("事务", space_id=space)
    wiki.edit_block(
        page["id"],
        block_id=page["blocks"][0]["stable_id"],
        markdown="已经变化",
        expected_version=1,
        operation_key="edit",
    )
    assert worker.run_once()["status"] == "stale"
    with db.connect() as c:
        row = c.execute(
            "SELECT * FROM retrieval_projection_tasks WHERE domain='wiki'"
        ).fetchone()
        assert row["status"] == "completed" and set(
            row["payload"]["request_states"].values()
        ) == {"stale"}
        assert not c.execute("SELECT 1 FROM wiki_embeddings").fetchone()


def test_new_same_profile_scope_has_its_own_five_attempt_budget(wiki_parts):
    db, _, wiki, space, msg, _, _ = wiki_parts
    create(wiki, space, msg)
    index, worker = wiki_index(wiki_parts)
    index.search("事务", space_id=space)
    for _ in range(4):
        claim = worker.claim()
        worker.fail(claim, RuntimeError("old scope fails"))
        with db.connect() as c:
            c.execute(
                "UPDATE retrieval_projection_tasks SET not_before=clock_timestamp() WHERE id=%s",
                (claim["id"],),
            )
    index.search("事务", space_id=space, thread_id="assistant_threads_id")
    claim = worker.claim()
    assert sorted(claim["payload"]["request_attempts"].values()) == [1, 5]
    worker.fail(claim, RuntimeError("shared provider fails"))
    with db.connect() as c:
        row = c.execute(
            "SELECT * FROM retrieval_projection_tasks WHERE id=%s", (claim["id"],)
        ).fetchone()
        assert row["status"] == "retry_wait" and list(
            row["payload"]["request_states"].values()
        ) == ["failed"]
        c.execute(
            "UPDATE retrieval_projection_tasks SET not_before=clock_timestamp() WHERE id=%s",
            (claim["id"],),
        )
    assert worker.run_once()["status"] == "ready"
    with db.connect() as c:
        row = c.execute(
            "SELECT * FROM retrieval_projection_tasks WHERE id=%s", (claim["id"],)
        ).fetchone()
        assert row["status"] == "failed" and sorted(
            row["payload"]["request_states"].values()
        ) == ["completed", "failed"]
