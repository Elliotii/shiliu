# ruff: noqa: F811
"""W09 effective windows, SQL ranking, asynchronous publication and C10."""

import pytest
from psycopg.types.json import Jsonb
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.store import AssistantConflict
from test_wiki import wiki_parts, create, source_page, add_source, wiki_index  # noqa: F401,F811


def test_wiki_window_queue_consumer_and_dense_current_set(wiki_parts):
    from shiliu.assistant.wiki_retrieval import WikiHybridIndex
    from shiliu.assistant.wiki_jobs import WikiProjectionWorker
    from test_collection_retrieval import FixedProvider

    _, _, wiki, space, msg, _, _ = wiki_parts

    class Provider(FixedProvider):
        def embed_query(self, text, **kw):
            return super().embed_query(text)

    page = create(wiki, space, msg)
    index = WikiHybridIndex(Provider(), wiki=wiki)
    wiki.retrieval = index
    lexical = index.search("事务", space_id=space)
    assert lexical["candidates"][0]["page_id"] == page["id"]
    assert (
        lexical["coverage"]["encoded_windows"] == 0
        and lexical["coverage"]["missing_windows"] > 0
    )
    worker = WikiProjectionWorker(index, owner="wiki-worker")
    result = worker.run_once()
    assert result["status"] == "ready", result
    dense = index.search("没有词汇交集的改述", space_id=space)
    assert (
        dense["coverage"]["dense_candidates"] == 1
        and dense["coverage"]["missing_windows"] == 0
    )
    assert dense["candidates"][0]["page_id"] == page["id"]
    assert worker.run_once() is None


@pytest.mark.parametrize(
    "change", ["source_removed", "task_narrow", "memory_forget", "page_edit"]
)
def test_c10_query_send_revalidates_and_does_not_reuse_old_hash(wiki_parts, change):
    db, _, wiki, space, msg, run, _ = wiki_parts
    if change in {"source_removed", "task_narrow"}:
        page, vid, sid, ref, _ = source_page(wiki_parts)
    else:
        page = create(wiki, space, msg)
        if change == "memory_forget":
            memory = MemoryService(db).save_explicit(
                text="个人私密偏好",
                subject_key="private",
                kind="context",
                scope_kind="user",
                scope_id=None,
                operation_key="private",
            )
            page = wiki.add_personal_note(
                page["id"],
                space_id=space,
                text=memory["text"],
                expected_version=1,
                operation_key="note",
                memory_id=memory["id"],
                memory_version=1,
            )
    index, worker = wiki_index(wiki_parts)
    index.search(
        "事务",
        space_id=space,
        thread_id=wiki_parts[1].get_thread("assistant_threads_id")["id"],
    )
    assert worker.run_once()["status"] == "ready"
    seen = []

    def mutate(attempt):
        if attempt:
            return
        if change == "source_removed":
            db.update_video(vid, is_ignored=True)
        elif change == "task_narrow":
            with db.connect(guard=True) as c:
                c.execute(
                    "UPDATE assistant_runs SET working_state_json=working_state_json||%s WHERE id=%s",
                    (Jsonb({"task_subset": {"video_ids": [-1]}}), run),
                )
                c.execute(
                    "UPDATE workspace_guards SET dependency_epoch=dependency_epoch+1 WHERE workspace_id=%s",
                    (db.workspace_id,),
                )
        elif change == "memory_forget":
            MemoryService(db).forget(
                memory["id"], expected_version=1, operation_key="f"
            )
        else:
            wiki.edit_block(
                page["id"],
                block_id=page["blocks"][0]["stable_id"],
                markdown="新版本已改变",
                expected_version=page["version"],
                operation_key="edit",
            )
        seen.append(attempt)

    result = index.search(
        "事务" if change != "memory_forget" else "个人私密偏好",
        space_id=space,
        thread_id="assistant_threads_id",
        before_validate=mutate,
    )
    assert seen == [0] and result["coverage"]["reprojections"] == 1
    if change in {"source_removed", "task_narrow"}:
        assert not result["candidates"]
    if change == "memory_forget":
        assert "个人私密" not in str(result["candidates"])
    assert not result["coverage"]["dense_candidates"]


def test_cross_domain_forget_uses_historical_build_snapshot_after_dependency_rewrite(
    wiki_parts,
):
    db, _, wiki, space, msg, _, _ = wiki_parts
    page = create(wiki, space, msg)
    memories = MemoryService(db)
    memory = memories.save_explicit(
        text="历史敏感正文",
        subject_key="secret",
        kind="context",
        scope_kind="user",
        scope_id=None,
        operation_key="secret",
    )
    page = wiki.add_personal_note(
        page["id"],
        space_id=space,
        text=memory["text"],
        expected_version=1,
        operation_key="note",
        memory_id=memory["id"],
        memory_version=1,
    )
    index, worker = wiki_index(wiki_parts)
    index.search("历史敏感正文", space_id=space)
    assert worker.run_once()["status"] == "ready"
    with db.connect(guard=True) as c:
        assert (
            c.execute("SELECT count(*) AS n FROM wiki_embeddings").fetchone()["n"] > 0
        )
        c.execute(
            "DELETE FROM assistant_wiki_personal_dependencies WHERE page_id=%s",
            (page["id"],),
        )
        # A legitimate page rewrite removes the sensitive block, while historical
        # projections retain the old sensitive text and its construction snapshot.
        raw = c.execute(
            "SELECT blocks_json FROM assistant_wiki_pages WHERE id=%s", (page["id"],)
        ).fetchone()["blocks_json"]
        c.execute(
            "UPDATE assistant_wiki_pages SET blocks_json=%s,version=version+1 WHERE id=%s",
            (Jsonb(raw[:1]), page["id"]),
        )
        c.execute(
            "UPDATE workspace_guards SET dependency_epoch=dependency_epoch+1 WHERE workspace_id=%s",
            (db.workspace_id,),
        )
    assert not index.search("历史敏感正文", space_id=space)["coverage"][
        "dense_candidates"
    ]
    memories.forget(memory["id"], expected_version=1, operation_key="forget")
    with db.connect() as c:
        assert c.execute("SELECT count(*) AS n FROM wiki_windows").fetchone()["n"] == 0
        assert (
            c.execute("SELECT count(*) AS n FROM wiki_embeddings").fetchone()["n"] == 0
        )
    from shiliu.assistant.memory_jobs import MemoryJobWorker

    worker = MemoryJobWorker(memories, owner="purge-worker")
    assert worker.run_once()["status"] == "purged"


def test_query_changes_twice_returns_explicit_retry(wiki_parts):
    db, _, wiki, space, msg, _, _ = wiki_parts
    page = create(wiki, space, msg)
    index, _ = wiki_index(wiki_parts)

    def change(attempt):
        with db.connect(guard=True) as c:
            c.execute(
                "UPDATE assistant_wiki_pages SET version=version+1 WHERE id=%s",
                (page["id"],),
            )
            c.execute(
                "UPDATE workspace_guards SET dependency_epoch=dependency_epoch+1 WHERE workspace_id=%s",
                (db.workspace_id,),
            )

    result = index.search("事务", space_id=space, before_validate=change)
    assert (
        result["status"] == "partial"
        and result["error_code"] == "wiki_dependencies_changing"
        and not result["candidates"]
    )


def test_no_model_lexical_fallback_windows_do_not_claim_token_safe(wiki_parts):
    from shiliu.assistant.wiki_retrieval import WikiHybridIndex

    _, _, wiki, space, msg, _, _ = wiki_parts
    create(wiki, space, msg)
    index = WikiHybridIndex(None, wiki=wiki)
    result = index.search("事务", space_id=space)
    assert result["candidates"] and result["coverage"]["window_policy"] == [
        "lexical-fallback-v1"
    ]
    assert result["coverage"]["degraded_reason"] == "embedding_provider_unavailable"
    assert (
        result["coverage"]["encoded_windows"] == 0
        and not result["coverage"]["dense_candidates"]
    )


@pytest.mark.parametrize("change", ["edit", "forget", "task", "new_request", "source"])
def test_c10_worker_compute_publish_revalidates_every_dependency(wiki_parts, change):
    from shiliu.assistant.wiki_jobs import WikiProjectionStale

    db, _, wiki, space, msg, run, _ = wiki_parts
    if change in {"task", "source"}:
        page, vid, _, _, _ = source_page(wiki_parts)
    else:
        page = create(wiki, space, msg)
    if change == "forget":
        memories = MemoryService(db)
        memory = memories.save_explicit(
            text="私密正文",
            subject_key="secret",
            kind="context",
            scope_kind="user",
            scope_id=None,
            operation_key="memory",
        )
        page = wiki.add_personal_note(
            page["id"],
            space_id=space,
            text=memory["text"],
            expected_version=1,
            operation_key="note",
            memory_id=memory["id"],
            memory_version=1,
        )
    index, worker = wiki_index(wiki_parts)
    index.search("事务", space_id=space, thread_id="assistant_threads_id")
    claim = worker.claim()
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    entered, release = Event(), Event()
    original = index.provider.embed_documents

    def paused(texts):
        entered.set()
        assert release.wait(5)
        return original(texts)

    index.provider.embed_documents = paused
    executor = ThreadPoolExecutor(1)
    future = executor.submit(worker.compute, claim)
    assert entered.wait(3)
    if change in {"edit", "new_request"}:
        wiki.edit_block(
            page["id"],
            block_id=page["blocks"][0]["stable_id"],
            markdown="新版材料",
            expected_version=page["version"],
            operation_key="edit",
        )
        if change == "new_request":
            index.search("新版", space_id=space, thread_id="assistant_threads_id")
    elif change == "source":
        db.update_video(vid, title="来源发生变化，head尚未刷新")
    elif change == "forget":
        memories.forget(memory["id"], expected_version=1, operation_key="forget")
    else:
        with db.connect(guard=True) as c:
            c.execute(
                "UPDATE assistant_runs SET working_state_json=working_state_json||%s WHERE id=%s",
                (Jsonb({"task_subset": {"video_ids": [-1]}}), run),
            )
            c.execute(
                "UPDATE workspace_guards SET dependency_epoch=dependency_epoch+1 WHERE workspace_id=%s",
                (db.workspace_id,),
            )
    release.set()
    computed = future.result(5)
    executor.shutdown()
    assert computed
    with db.connect() as c:
        before = c.execute(
            "SELECT to_jsonb(t) AS row FROM retrieval_projection_tasks t WHERE id=%s",
            (claim["id"],),
        ).fetchone()["row"]
    with pytest.raises(WikiProjectionStale):
        worker.publish(claim, computed)
    with db.connect() as c:
        assert (
            c.execute(
                "SELECT to_jsonb(t) AS row FROM retrieval_projection_tasks t WHERE id=%s",
                (claim["id"],),
            ).fetchone()["row"]
            == before
        )
        assert c.execute("SELECT count(*) AS n FROM wiki_windows").fetchone()["n"] == 0
        assert (
            c.execute("SELECT count(*) AS n FROM wiki_embeddings").fetchone()["n"] == 0
        )


def test_multiple_task_projections_coexist_and_scope_never_reuses_full_page(wiki_parts):
    from shiliu.assistant.sources import SourceScope

    db, _, wiki, space, msg, _, _ = wiki_parts
    page, vid1, _, ref1, _ = source_page(wiki_parts)
    vid2, _, ref2, _ = add_source(wiki_parts, 2, "另一个来源的条件只在特定场景有效。")
    page = wiki.save_discussion(
        space_id=space,
        title=page["title"],
        purpose="两条来源",
        expected_version=1,
        source_message_id=msg,
        operation_key="second-source",
        blocks=[
            {
                "role": "source",
                "heading": "独立条件",
                "markdown": "另一个来源的条件只在特定场景有效。",
                "source_refs": [ref2],
                "source_view": "transcript",
            }
        ],
    )
    index, worker = wiki_index(wiki_parts)
    full = index.search("条件", space_id=space)
    assert worker.run_once()["status"] == "ready"
    scope = SourceScope(video_ids=frozenset({vid1}), all_active=True)
    partial = index.search("事务", space_id=space, task_scope=scope)
    assert not partial["coverage"]["dense_candidates"]
    assert worker.run_once()["status"] == "ready"
    partial = index.search("事务", space_id=space, task_scope=scope)
    assert partial["coverage"]["dense_candidates"] == 1
    assert len(partial["candidates"][0]["hits"]) == 1
    full = index.search("条件", space_id=space)
    assert full["coverage"]["dense_candidates"] == 2
    with db.connect() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM wiki_windows WHERE page_id=%s", (page["id"],)
            ).fetchone()["n"]
            >= 3
        )


def test_wiki_window_normal_policy_bounds_and_directory_hit(wiki_parts):
    _, _, wiki, space, msg, _, _ = wiki_parts
    create(wiki, space, msg, title="CUDA配置")
    index, worker = wiki_index(wiki_parts)
    result = index.search("CUDA", space_id=space)
    assert result["candidates"][0]["hits"][0]["match_kind"] == "page_directory"
    assert result["candidates"][0]["hits"][0]["candidate_excerpt"] == ""
    assert result["candidates"][0]["hits"][0]["position"] == {}
    snap = index.projections.capture(space)
    assert all(
        len(e["text"]) <= 2000 and index.provider.count_tokens(e["text"]) <= 512
        for e in index.windows(snap)
    )


@pytest.mark.parametrize("action", ["publish", "heartbeat", "fail"])
def test_wiki_projection_unchanged_lock_wait_expiry_has_no_mutation(wiki_parts, action):
    from test_p3_scheduler import expire_while_waiting
    from shiliu.assistant.wiki_jobs import WikiProjectionStale

    db, _, wiki, space, msg, _, _ = wiki_parts
    create(wiki, space, msg)
    index, worker = wiki_index(wiki_parts)
    index.search("事务", space_id=space)
    claim = worker.claim(seconds=1.5)
    computed = worker.compute(claim)

    def state():
        with db.connect(read_only=True) as c:
            return {
                table: c.execute(
                    "SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]') AS rows FROM shiliu."
                    + table
                    + " t"
                ).fetchone()["rows"]
                for table in [
                    "retrieval_projection_tasks",
                    "wiki_windows",
                    "wiki_embeddings",
                    "embedding_profiles",
                    "assistant_runtime_state",
                ]
            }

    before = state()

    def operation(c):
        try:
            if action == "publish":
                return worker.publish(claim, computed)
            if action == "heartbeat":
                return worker.heartbeat(claim)
            return worker.fail(claim, RuntimeError("synthetic failure"))
        except WikiProjectionStale as exc:
            return exc

    result = expire_while_waiting(
        db.pg, "retrieval_projection_tasks", claim["id"], operation
    )
    assert (
        isinstance(result, WikiProjectionStale)
        and str(result) == "wiki_projection_fenced"
    )
    assert state() == before


def test_normalized_window_preserves_formal_character_offsets(wiki_parts):
    _, _, wiki, space, msg, _, _ = wiki_parts
    page = create(wiki, space, msg)
    body = "前缀ﬀ正文尾部" * 100
    page = wiki.edit_block(
        page["id"],
        block_id=page["blocks"][0]["stable_id"],
        markdown=body,
        expected_version=1,
        operation_key="ligature",
    )
    index, _ = wiki_index(wiki_parts)
    snapshot = index.projections.capture(space)
    entries = index.windows(snapshot)
    assert entries[-1]["end"] == len(body)
    assert all(0 <= e["start"] <= e["end"] <= len(body) for e in entries)
    assert all(
        len(e["text"]) <= 2000 and index.provider.count_tokens(e["text"]) <= 512
        for e in entries
    )


def test_source_changes_before_head_refresh_are_checked_by_actual_inputs(wiki_parts):
    from shiliu.assistant.wiki_projection import WikiProjection

    db, _, wiki, space, msg, _, sources = wiki_parts
    page, vid, _, ref, old = source_page(wiki_parts)
    projection = WikiProjection(wiki)
    prepared = projection.prepare_sources(space)
    # Keep updated_at at the same public second to prove the fence does not
    # depend on formatted timestamps or waiting for the source-head worker.
    with db.connect(guard=True) as c:
        c.execute(
            "UPDATE videos SET description='source changed without head refresh' WHERE workspace_id=%s AND id=%s",
            (db.workspace_id, vid),
        )
    with pytest.raises(AssistantConflict, match="prepare_stale"):
        with db.pg.transaction(read_only=True, isolation="repeatable read") as c:
            projection.capture(space, conn=c, prepared=prepared)
    assert wiki.get_page(page["id"])["blocks"]  # transcript view is equivalent
    # Point current formal material at a new immutable subtitle version, without
    # manually capturing a new comprehensive source revision.
    from shiliu.domain import SubtitleSegment

    batch = sources.artifacts.batch(vid)
    _, new_ref = batch.save_raw_subtitle(
        "BV0000000001",
        [
            SubtitleSegment.model_validate(
                {"from": 0, "to": 3, "content": "完全不同的新字幕正文"}
            )
        ],
    )
    batch.commit(lambda c: db.update_video(vid, raw_subtitle_path=new_ref, conn=c))
    assert not wiki.get_page(page["id"])["blocks"]


def test_wiki_page_lock_wait_expiry_rolls_back_entire_publication(wiki_parts):
    from test_p3_scheduler import expire_while_waiting
    from shiliu.assistant.wiki_jobs import WikiProjectionStale

    db, _, wiki, space, msg, _, _ = wiki_parts
    page = create(wiki, space, msg)
    index, worker = wiki_index(wiki_parts)
    index.search("事务", space_id=space)
    claim = worker.claim(seconds=1.5)
    computed = worker.compute(claim)
    with db.connect(read_only=True) as c:
        before = c.execute(
            "SELECT to_jsonb(t) AS row FROM retrieval_projection_tasks t WHERE id=%s",
            (claim["id"],),
        ).fetchone()["row"]

    def operation(c):
        try:
            return worker.publish(claim, computed)
        except WikiProjectionStale as exc:
            return exc

    result = expire_while_waiting(
        db.pg,
        "assistant_wiki_pages",
        page["id"],
        operation,
        lease_until=claim["lease_until"],
    )
    assert (
        isinstance(result, WikiProjectionStale)
        and str(result) == "wiki_projection_fenced"
    )
    with db.connect(read_only=True) as c:
        assert (
            c.execute(
                "SELECT to_jsonb(t) AS row FROM retrieval_projection_tasks t WHERE id=%s",
                (claim["id"],),
            ).fetchone()["row"]
            == before
        )
        assert (
            c.execute("SELECT count(*) AS n FROM wiki_embeddings").fetchone()["n"] == 0
        )
        assert c.execute("SELECT count(*) AS n FROM wiki_windows").fetchone()["n"] == 0


def test_projection_failed_is_not_hot_requeued_by_search_and_manual_rebuild_recovers(
    wiki_parts,
):
    db, _, wiki, space, msg, _, _ = wiki_parts
    page = create(wiki, space, msg)
    index, worker = wiki_index(wiki_parts)
    index.search("事务", space_id=space)
    with db.connect() as c:
        c.execute(
            "UPDATE retrieval_projection_tasks SET status='failed',attempt=5,last_error='synthetic_failure'"
        )
        before = c.execute(
            "SELECT to_jsonb(t) AS row FROM retrieval_projection_tasks t"
        ).fetchone()["row"]
    result = index.search("事务", space_id=space)
    assert (
        result["coverage"]["degraded_reason"]
        == "wiki_projection_failed_manual_retry_required"
    )
    with db.connect() as c:
        assert (
            c.execute(
                "SELECT to_jsonb(t) AS row FROM retrieval_projection_tasks t"
            ).fetchone()["row"]
            == before
        )
    assert worker.requeue_failed(page["id"]) and worker.run_once()["status"] == "ready"
    assert not worker.requeue_failed(page["id"])


def test_page_restricted_relevant_read_ranks_only_requested_authorized_page(wiki_parts):
    _, _, wiki, space, msg, _, _ = wiki_parts
    create(wiki, space, msg, title="事务", op="top-title")
    requested = create(wiki, space, msg, title="另一个页面", op="requested-page")
    index, _ = wiki_index(wiki_parts)
    result = index.search("事务", space_id=space, page_id=requested["id"], limit=1)
    assert [p["page_id"] for p in result["candidates"]] == [requested["id"]]
    assert not index.search("事务", space_id=space, page_id="unowned-or-missing")[
        "candidates"
    ]
