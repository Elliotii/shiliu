"""W08 real PG formal state, native DTOs and same-database vectors."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Barrier
from dataclasses import replace

import pytest
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.store import AssistantConflict
from shiliu.storage.scheduler import claim_job
from shiliu.storage.fences import cancel_run
from seed_rows import SyntheticGraph
from test_collection_retrieval import FixedProvider


@pytest.fixture
def memory_parts(collection_db):
    db = collection_db
    with db.connect() as c:
        graph = SyntheticGraph(c)
        msg = graph.ensure("assistant_messages")
        run = graph.ensure("assistant_runs")
        space = graph.rows["assistant_spaces"]
        c.execute(
            "UPDATE assistant_spaces SET enabled=true WHERE id=%s", (space["id"],)
        )
        c.execute(
            "UPDATE assistant_runs SET status='running',run_epoch=1,working_state_json='{}',cancel_requested=false WHERE id=%s",
            (run["id"],),
        )
    return db, MemoryService(db), space["id"], msg["id"], run["id"]


def save(m, **kw):
    values = dict(
        text="白天学习数据库",
        subject_key="study",
        kind="context",
        scope_kind="user",
        scope_id=None,
        operation_key="save",
    )
    values.update(kw)
    return m.save_explicit(**values)


def claim(db, kind="memory_index", memory_id=None):
    with db.connect() as c:
        # Deterministic closed fixture chooses the intended queued job only.
        if memory_id:
            c.execute(
                "UPDATE assistant_jobs SET not_before=clock_timestamp()+interval '1 day' WHERE kind=%s AND payload_json->>'memory_id'<>%s",
                (kind, memory_id),
            )
        return claim_job(c, db.context, "test", allow_model_jobs=False)


def test_save_native_roundtrip_independent_facts_receipt_and_undo(memory_parts):
    db, m, space, msg, _ = memory_parts
    one = save(
        m,
        source_message_ids=[msg],
        stated_text="下个月学习数据库",
        stated_at="2026-10-17T13:45:38+00:00",
    )
    assert (
        one["version"] == 1 and one["expires_at"] is None and one["valid_from"] is None
    )
    assert one["time_context"]["events"][0]["value"] == "2026-11"
    replay = save(m, text="有效但不同的文字", operation_key="save")
    assert replay == one
    two = save(m, text="晚上阅读文档", operation_key="second")
    assert one["id"] != two["id"] and len(m.list()) == 2
    assert m.recall("11月", space_id=space)[0]["id"] == one["id"]
    retracted = m.undo_created(
        two["id"], save_operation_key="second", expected_version=1, operation_key="undo"
    )
    assert retracted["status"] == "forgotten" and not retracted["text"]
    assert retracted == m.undo_created(
        two["id"], save_operation_key="second", expected_version=1, operation_key="undo"
    )
    with db.connect() as c:
        row = c.execute(
            "SELECT * FROM assistant_memories WHERE id=%s", (one["id"],)
        ).fetchone()
        assert (
            isinstance(row["time_context_json"], dict)
            and type(row["user_edited"]) is bool
        )
        assert row["scope_id"] == "" and row["scope_space_id"] is None
        assert (
            c.execute("SELECT count(*) AS n FROM assistant_jobs").fetchone()["n"] == 3
        )


def test_correct_forget_suppression_and_actual_validity(memory_parts):
    db, m, space, msg, _ = memory_parts
    old = save(m, source_message_ids=[msg])
    current = m.correct(
        old["id"],
        text="改为晚上学习数据库",
        expected_version=1,
        operation_key="correct",
    )
    assert current["version"] == 2 and current["user_edited"]
    with pytest.raises(AssistantConflict, match="version_conflict"):
        m.correct(old["id"], text="旧版本", expected_version=1, operation_key="stale")
    forgotten = m.forget(old["id"], expected_version=2, operation_key="forget")
    assert (
        forgotten["text"] == ""
        and forgotten["source_excerpt"] == ""
        and forgotten["time_context"] == {}
    )
    assert msg in m.suppressed_source_message_ids(space_id=space)
    assert not m.recall("学习数据库", space_id=space)
    assert m.forget_receipt_valid(
        operation_key="forget", memory_id=old["id"], version=3, space_id=space
    )
    assert not m.validate_dependency_refs([f"memory:{old['id']}:2"], space_id=space)[
        "valid"
    ]
    assert m.changes_since(0)["current_epoch"] == 3
    with db.connect() as c:
        assert not c.execute(
            "SELECT before_json FROM assistant_memory_changes WHERE memory_id=%s AND before_json IS NOT NULL",
            (old["id"],),
        ).fetchone()
    timed = save(
        m,
        text="仅限这个测试时刻",
        operation_key="expired",
        expires_at="2020-01-01T00:00:00+00:00",
        pinned=True,
    )
    assert timed["expires_at"] == "2020-01-01T00:00:00+00:00" and not m.recall(
        "这个测试", space_id=space
    )


def test_scope_owner_needs_review_and_source_gates(memory_parts):
    db, m, space, msg, _ = memory_parts
    local = save(m, scope_kind="space", scope_id=space, source_message_ids=[msg])
    assert local["scope_space_id"] == space and local["scope_id"] == str(space)
    with pytest.raises(ValueError, match="scope"):
        save(m, scope_kind="space", scope_id=999)
    with pytest.raises(AssistantConflict, match="source_out_of_scope"):
        save(m, operation_key="bad-source", source_message_ids=["invented"])
    with pytest.raises(ValueError, match="principal_context_mismatch"):
        MemoryService(db, principal_id="other")
    hidden = save(
        m,
        operation_key="review",
        text="需要复核的知识",
        _initial_status="needs_review",
        pinned=True,
    )
    assert hidden["id"] in {x["id"] for x in m.list()}
    assert hidden["id"] not in {x["id"] for x in m.recall("需要复核", space_id=space)}
    with db.connect() as c:
        c.execute("UPDATE assistant_spaces SET enabled=false WHERE id=%s", (space,))
    with pytest.raises(ValueError, match="scope"):
        m.recall("学习", space_id=space)


def test_concurrent_receipt_different_payload_single_fact(memory_parts):
    db, m, _, _, _ = memory_parts
    barrier = Barrier(2)

    def write(text):
        barrier.wait(3)
        return save(m, text=text)

    with ThreadPoolExecutor(2) as ex:
        results = list(ex.map(write, ["白天学习", "晚上学习"]))
    assert results[0] == results[1] and len(m.list()) == 1


def test_run_fence_without_budget_and_management_entry(memory_parts):
    db, m, _, _, run = memory_parts
    row = save(
        m, operation_key="tool:" + run + ":save", expected_run_id=run, expected_epoch=1
    )
    with pytest.raises(AssistantConflict, match="expected_run_epoch"):
        save(m, operation_key="tool:" + run + ":without")
    with db.connect() as c:
        cancel_run(c, db.context, run)
    with pytest.raises(AssistantConflict, match="run_fenced"):
        m.correct(
            row["id"],
            text="迟到更正",
            expected_version=1,
            operation_key="late",
            expected_run_id=run,
            expected_epoch=1,
        )
    assert m.get(row["id"])["version"] == 1
    assert (
        save(m, operation_key="direct-management", text="直接管理入口")["version"] == 1
    )


def test_auto_generation_user_edit_and_suppression(memory_parts):
    _, m, space, msg, _ = memory_parts
    epoch = m.current_epoch()
    generation = m.auto_policy()["generation"]
    proposal = dict(
        op="add",
        text="提炼的学习安排",
        subject_key="study",
        kind="context",
        scope_kind="space",
        scope_id=space,
    )
    m.set_auto_enabled(False)
    m.set_auto_enabled(True)
    assert (
        m.apply_extracted(
            proposal,
            source_message_ids=[msg],
            expected_epoch=epoch,
            expected_auto_generation=generation,
            operation_key="late-policy",
        )
        is None
    )
    row = m.apply_extracted(
        proposal,
        source_message_ids=[msg],
        expected_epoch=m.current_epoch(),
        expected_auto_generation=m.auto_policy()["generation"],
        operation_key="extract",
    )
    assert row["origin"] == "extracted" and not row["user_edited"]
    m.correct(
        row["id"], text="用户修订的安排", expected_version=1, operation_key="edit"
    )
    assert (
        m.apply_extracted(
            proposal,
            source_message_ids=[msg],
            expected_epoch=epoch,
            operation_key="late-epoch",
        )
        is None
    )
    m.forget(row["id"], expected_version=2, operation_key="forget")
    assert (
        m.apply_extracted(
            proposal,
            source_message_ids=[msg],
            expected_epoch=m.current_epoch(),
            operation_key="resurrect",
        )
        is None
    )


def test_no_model_structured_short_chinese_and_kind_fallback(memory_parts):
    _, m, space, _, _ = memory_parts
    pinned = save(m, text="CUDA 和 pgvector 配置", kind="preference", pinned=True)
    info = m.recall_with_status("CUDA", space_id=space)
    assert (
        info["items"][0]["id"] == pinned["id"]
        and info["semantic_index"] == "unavailable"
    )
    assert info["authoritative_store"] == "postgresql" and info["degraded_reason"]
    assert m.recall("PG", space_id=space)
    assert not m.recall_with_status(
        "CUDA", space_id=space, excluded_kinds={"preference"}
    )["items"]
    assert (
        m.recall_with_status("", space_id=space, linked_ids=[pinned["id"]])["items"][0][
            "id"
        ]
        == pinned["id"]
    )


def test_vector_atomic_publication_exact_and_immediate_forget(memory_parts):
    db, _, space, _, _ = memory_parts
    m = MemoryService(db, provider=FixedProvider())
    row = save(m)
    job = claim(db)
    assert m.project(memory_id=row["id"], version=1, job=job)["status"] == "ready"
    info = m.recall_with_status("无词汇匹配", space_id=space)
    assert info["semantic_index"] == "ready" and info["items"][0]["id"] == row["id"]
    assert "semantic" in info["items"][0]["recall_reasons"]
    m.correct(
        row["id"], text="更正后的正文", expected_version=1, operation_key="correction"
    )
    info = m.recall_with_status("无词汇匹配", space_id=space)
    assert not any("semantic" in i["recall_reasons"] for i in info["items"])
    m.forget(row["id"], expected_version=2, operation_key="forget")
    with db.connect() as c:
        assert (
            c.execute("SELECT count(*) AS n FROM memory_embeddings").fetchone()["n"]
            == 0
        )
        assert (
            c.execute(
                "SELECT tokenized_text FROM assistant_memories WHERE id=%s",
                (row["id"],),
            ).fetchone()["tokenized_text"]
            == ""
        )


@pytest.mark.parametrize("mutation", ["correct", "forget"])
def test_c09_encode_then_mutate_cannot_publish_or_finish(memory_parts, mutation):
    db, _, _, _, _ = memory_parts
    started, release = Event(), Event()

    class Paused(FixedProvider):
        def embed_documents(self, texts):
            with db.connect(read_only=True) as c:
                assert (
                    c.execute(
                        "SELECT count(*) AS n FROM pg_stat_activity WHERE application_name='shiliu-pg' AND state='idle in transaction'"
                    ).fetchone()["n"]
                    == 0
                )
            started.set()
            assert release.wait(5)
            return super().embed_documents(texts)

    m = MemoryService(db, provider=Paused())
    row = save(m)
    job = claim(db)

    def work():
        with pytest.raises(AssistantConflict, match="projection_stale"):
            m.project(memory_id=row["id"], version=1, job=job)

    with ThreadPoolExecutor(1) as ex:
        result = ex.submit(work)
        assert started.wait(3)
        if mutation == "correct":
            m.correct(
                row["id"], text="新版本", expected_version=1, operation_key="mutate"
            )
        else:
            m.forget(row["id"], expected_version=1, operation_key="mutate")
        with db.connect(read_only=True) as c:
            before = c.execute(
                "SELECT to_jsonb(j) AS row FROM assistant_jobs j WHERE id=%s",
                (job["id"],),
            ).fetchone()["row"]
        release.set()
        result.result(5)
    with db.connect() as c:
        assert (
            c.execute(
                "SELECT to_jsonb(j) AS row FROM assistant_jobs j WHERE id=%s",
                (job["id"],),
            ).fetchone()["row"]
            == before
        )
        assert (
            c.execute("SELECT count(*) AS n FROM memory_embeddings").fetchone()["n"]
            == 0
        )


@pytest.mark.parametrize("bad", ["dimension", "nan", "zero", "norm"])
def test_invalid_vector_rolls_back_job_and_formal_projection(memory_parts, bad):
    import numpy as np

    db, _, _, _, _ = memory_parts

    class Bad(FixedProvider):
        def embed_documents(self, texts):
            v = np.array([1.0] + [0.0] * 511, dtype=np.float32)
            if bad == "dimension":
                v = v[:3]
            elif bad == "nan":
                v[3] = np.nan
            elif bad == "zero":
                v[:] = 0
            else:
                v[0] = 2
            return [v]

    m = MemoryService(db, provider=Bad())
    row = save(m)
    job = claim(db)
    with pytest.raises(ValueError):
        m.project(memory_id=row["id"], version=1, job=job)
    with db.connect() as c:
        assert (
            c.execute("SELECT count(*) AS n FROM memory_embeddings").fetchone()["n"]
            == 0
        )
        assert (
            c.execute(
                "SELECT status FROM assistant_jobs WHERE id=%s", (job["id"],)
            ).fetchone()["status"]
            == "running"
        )


def test_worker_recovers_stale_intents_purge_and_provider_failure(memory_parts):
    from shiliu.assistant.memory_jobs import MemoryJobWorker

    db, _, space, _, _ = memory_parts
    m = MemoryService(db, provider=FixedProvider())
    row = save(m)
    m.correct(row["id"], text="更新安排", expected_version=1, operation_key="c")
    worker = MemoryJobWorker(m, owner="worker")
    assert worker.run_once()["status"] == "stale"
    assert worker.run_once()["status"] == "ready"
    m.forget(row["id"], expected_version=2, operation_key="f")
    assert worker.run_once()["status"] == "purged"
    assert worker.run_once() is None
    m = MemoryService(db)
    save(m, text="没有模型也保留正式记忆", operation_key="no-model")
    worker = MemoryJobWorker(m, owner="worker")
    assert worker.run_once()["status"] == "retry_wait"
    assert m.recall("正式记忆", space_id=space)
    with db.connect() as c:
        row = c.execute(
            "SELECT * FROM assistant_jobs WHERE status='retry_wait'"
        ).fetchone()
        assert row["attempt"] == 1 and row["last_error_code"] == "RuntimeError"
        assert c.execute(
            "SELECT %s>clock_timestamp() AS delayed", (row["not_before"],)
        ).fetchone()["delayed"]


def test_dense_filters_before_limit_and_stable_ties(memory_parts):
    db, _, space, _, _ = memory_parts
    m = MemoryService(db, provider=FixedProvider())
    rows = [
        save(m, text=f"唯一知识条目{i}", operation_key=f"item{i}") for i in range(25)
    ]
    from shiliu.assistant.memory_jobs import MemoryJobWorker

    worker = MemoryJobWorker(m, owner="worker")
    for _ in rows:
        assert worker.run_once()["status"] == "ready"
    # All dense distances tie. Invalid vectors cannot occupy the Top20 budget.
    invalid = sorted(rows, key=lambda r: r["id"])[:21]
    with db.connect() as c:
        c.execute(
            "UPDATE memory_embeddings SET change_epoch=change_epoch+1 WHERE memory_id=ANY(%s)",
            ([r["id"] for r in invalid],),
        )
    info = m.recall_with_status("无词汇关联", space_id=space, limit=20)
    assert {i["id"] for i in info["items"]} == {
        r["id"] for r in rows if r not in invalid
    }
    assert all("semantic" in i["recall_reasons"] for i in info["items"])
    assert info["semantic_index"] == "partial"
    with db.connect() as c:
        c.execute("UPDATE memory_embeddings SET embedding_text_hash='wrong'")
    assert not m.recall_with_status("无词汇关联", space_id=space)["items"]


def test_query_only_profile_change_does_not_recompile_documents(memory_parts):
    from shiliu.storage.embedding_profiles import DocumentProfile

    a = FixedProvider()

    class QueryOnly(FixedProvider):
        def model_identity(self):
            return replace(
                super().model_identity(), query_instruction_version="new-query-only"
            )

    assert (
        DocumentProfile(a, "memory-text-v1").profile_id
        == DocumentProfile(QueryOnly(), "memory-text-v1").profile_id
    )
    assert (
        DocumentProfile(a, "memory-text-v1").profile_id
        != DocumentProfile(a, "wiki-effective-windows-v1").profile_id
    )


@pytest.mark.parametrize(
    "text,precision,value",
    [
        ("我喜欢单机游戏", None, None),
        ("过段时间学习日语", "vague", None),
        ("2077之前玩到一半，打算下个月继续玩", "month", "2026-11"),
        ("下周开始准备面试", "week", "2026-W43"),
        ("明年年初考虑换电脑", "year_part", "2027年初"),
        ("接下来两周重点学习数据库", "range", "2026-10-17"),
    ],
)
def test_migrated_memory_time_v2_fact_is_not_expiry(
    memory_parts, text, precision, value
):
    _, m, space, msg, _ = memory_parts
    at = "2026-10-17T13:45:38+00:00"
    item = save(m, text=text, source_message_ids=[msg], stated_text=text, stated_at=at)
    assert item["valid_from"] is None and item["expires_at"] is None
    events = item["time_context"]["events"]
    assert (
        (events[0]["precision"], events[0]["value"]) == (precision, value)
        if precision
        else not events
    )
    assert item["time_context"]["stated_at"] == at
    assert m.recall(text, space_id=space)[0]["time_context"] == item["time_context"]


@pytest.mark.parametrize("change", ["auto_generation", "correct", "forget"])
def test_c09_late_extraction_proposal_cannot_revive_protected_state(
    memory_parts, change
):
    db, m, space, msg, _ = memory_parts
    proposal = dict(
        op="add",
        text="提炼的原学习安排",
        subject_key="study",
        kind="context",
        scope_kind="space",
        scope_id=space,
    )
    row = m.apply_extracted(
        proposal,
        source_message_ids=[msg],
        expected_epoch=m.current_epoch(),
        operation_key="initial",
    )
    epoch = m.current_epoch()
    generation = m.auto_policy()["generation"]
    entered, release = Event(), Event()

    def model_result():
        entered.set()
        assert release.wait(5)
        return m.apply_extracted(
            proposal,
            source_message_ids=[msg],
            expected_epoch=epoch,
            expected_auto_generation=generation,
            operation_key="late-extraction",
        )

    with ThreadPoolExecutor(1) as ex:
        result = ex.submit(model_result)
        assert entered.wait(3)
        if change == "auto_generation":
            m.set_auto_enabled(False)
            m.set_auto_enabled(True)
        elif change == "correct":
            m.correct(
                row["id"],
                text="用户更正后的学习安排",
                expected_version=1,
                operation_key="correct",
            )
        else:
            m.forget(row["id"], expected_version=1, operation_key="forget")
        current = m.get(row["id"])
        release.set()
        assert result.result(5) is None
    assert m.get(row["id"]) == current and len(m.list(include_inactive=True)) == 1


def test_memory_row_lock_wait_expiry_rolls_back_vector_and_job(memory_parts):
    from test_p3_scheduler import expire_while_waiting
    from shiliu.storage.fences import CoordinationConflict

    db, _, _, _, _ = memory_parts
    m = MemoryService(db, provider=FixedProvider())
    row = save(m)
    with db.connect() as c:
        job = claim_job(
            c,
            db.context,
            "test",
            lease_seconds=1.5,
            allow_model_jobs=False,
            kinds=("memory_index",),
        )
    with db.connect() as c:
        before = c.execute(
            "SELECT to_jsonb(t) AS row FROM assistant_jobs t WHERE id=%s", (job["id"],)
        ).fetchone()["row"]
    result = expire_while_waiting(
        db.pg,
        "assistant_memories",
        row["id"],
        lambda c: m.project(memory_id=row["id"], version=1, job=job),
        lease_until=job["lease_until"],
    )
    assert isinstance(result, CoordinationConflict) and str(result) == "job_fenced"
    with db.connect() as c:
        assert (
            c.execute(
                "SELECT to_jsonb(t) AS row FROM assistant_jobs t WHERE id=%s",
                (job["id"],),
            ).fetchone()["row"]
            == before
        )
        assert (
            c.execute("SELECT count(*) AS n FROM memory_embeddings").fetchone()["n"]
            == 0
        )
        assert (
            c.execute(
                "SELECT last_projected_version FROM assistant_memories WHERE id=%s",
                (row["id"],),
            ).fetchone()["last_projected_version"]
            is None
        )
