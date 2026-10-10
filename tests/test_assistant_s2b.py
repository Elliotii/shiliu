from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event

import pytest

from shiliu.assistant.memory import MemoryService
from shiliu.assistant.runtime import AssistantRuntime
from shiliu.assistant.store import AssistantRunStore
from shiliu.db import Database, SCHEMA_VERSION


class SemanticBackend:
    def __init__(self) -> None:
        self.hits: dict[str, list[dict]] = {}

    def search(self, _query: str, *, top_k: int, scope_key: str):
        return self.hits.get(scope_key, [])[:top_k]


def _memory_service(app_paths, *, backend=None):
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="S2-B", all_active=True)
    return db, space, MemoryService(db, backend=backend)


def _save(memories: MemoryService, space_id: int, *, text: str, subject: str, key: str):
    return memories.save_explicit(
        text=text,
        subject_key=subject,
        kind="constraint",
        scope_kind="space",
        scope_id=space_id,
        operation_key=key,
    )


def test_semantic_candidate_older_than_eighty_is_authoritatively_reloaded(app_paths) -> None:
    backend = SemanticBackend()
    _db, space, memories = _memory_service(app_paths, backend=backend)
    old = _save(
        memories,
        space["id"],
        text="发布前必须完成可逆迁移演练",
        subject="release_restore",
        key="old-relevant",
    )
    for index in range(90):
        _save(
            memories,
            space["id"],
            text=f"无关的近期记录 {index}",
            subject=f"noise_{index}",
            key=f"noise-{index}",
        )
    with memories.db.connect() as connection:
        connection.execute(
            "UPDATE assistant_memories SET updated_at='2020-01-01T00:00:00+00:00' WHERE id=?",
            (old["id"],),
        )
        legacy_latest = {
            row["id"] for row in connection.execute(
                "SELECT id FROM assistant_memories WHERE status='active' "
                "ORDER BY pinned DESC, updated_at DESC LIMIT 80"
            )
        }
    assert old["id"] not in legacy_latest
    backend.hits[f"space:{space['id']}"] = [{
        "id": "semantic-old",
        "score": 0.91,
        "metadata": {"record_id": old["id"], "record_version": 1},
    }]

    result = memories.recall_with_status("上线前怎样保证可恢复", space_id=space["id"])

    assert result["semantic_index"] == "ready"
    assert result["items"][0]["id"] == old["id"]
    assert result["items"][0]["text"] == "发布前必须完成可逆迁移演练"
    assert "semantic" in result["items"][0]["recall_reasons"]


def test_stale_semantic_version_can_only_return_current_formal_text(app_paths) -> None:
    backend = SemanticBackend()
    _db, space, memories = _memory_service(app_paths, backend=backend)
    original = _save(
        memories, space["id"], text="项目使用 SQLite",
        subject="storage", key="stale-v1",
    )
    backend.hits[f"space:{space['id']}"] = [{
        "id": "stale-vector", "score": 0.99,
        "metadata": {"record_id": original["id"], "record_version": 1},
    }]
    corrected = memories.correct(
        original["id"], text="项目改用 DuckDB", expected_version=1,
        operation_key="stale-v2",
    )

    result = memories.recall_with_status("DuckDB", space_id=space["id"])

    assert result["items"][0]["id"] == corrected["id"]
    assert result["items"][0]["text"] == "项目改用 DuckDB"
    assert "stale_semantic_rechecked" in result["items"][0]["recall_reasons"]
    assert all(item["text"] != "项目使用 SQLite" for item in result["items"])


def test_scope_time_precedence_and_unknown_time_are_explicit(app_paths) -> None:
    _db, space, memories = _memory_service(app_paths)
    global_memory = memories.save_explicit(
        text="默认使用 PostgreSQL",
        subject_key="storage",
        kind="preference",
        scope_kind="user",
        scope_id=None,
        operation_key="global-storage",
    )
    space_memory = _save(
        memories,
        space["id"],
        text="本项目使用 SQLite",
        subject="storage",
        key="space-storage",
    )
    memories.save_explicit(
        text="已经过期的临时约束",
        subject_key="expired",
        kind="constraint",
        scope_kind="space",
        scope_id=space["id"],
        operation_key="expired",
        valid_from="2020-01-01T00:00:00+08:00",
        expires_at="2020-01-15T00:00:00+08:00",
        validity_note="2020 年前两周",
        validity_timezone="Asia/Shanghai",
    )
    unknown = memories.save_explicit(
        text="项目封板前不升级依赖",
        subject_key="dependency_freeze",
        kind="constraint",
        scope_kind="space",
        scope_id=space["id"],
        operation_key="unknown-expiry",
        validity_note="到项目封板为止，具体日期未确定",
        validity_timezone="Asia/Shanghai",
    )

    storage = memories.recall("storage", space_id=space["id"])
    freeze = memories.recall("封板", space_id=space["id"])
    all_text = [item["text"] for item in memories.recall("约束", space_id=space["id"])]

    assert [item["id"] for item in storage[:2]] == [space_memory["id"], global_memory["id"]]
    assert all(item["scope_conflict"] for item in storage[:2])
    assert freeze[0]["id"] == unknown["id"]
    assert freeze[0]["expires_at"] is None
    assert freeze[0]["validity_note"] == "到项目封板为止，具体日期未确定"
    assert "已经过期的临时约束" not in all_text
    with pytest.raises(ValueError, match="memory_time_requires_timezone"):
        memories.save_explicit(
            text="无时区时间不应接受", subject_key="bad_time", kind="constraint",
            scope_kind="space", scope_id=space["id"], operation_key="bad-time",
            expires_at="2030-01-01T00:00:00",
        )


def test_semantic_hit_cannot_cross_space_or_revive_expired_record(app_paths) -> None:
    backend = SemanticBackend()
    db, space_a, memories = _memory_service(app_paths, backend=backend)
    space_b = AssistantRunStore(db).create_space(name="另一个 Space", all_active=True)
    only_a = _save(
        memories, space_a["id"], text="方案代号是青石",
        subject="codename", key="only-a",
    )
    expired_b = memories.save_explicit(
        text="过期方案代号是白塔", subject_key="expired_codename", kind="context",
        scope_kind="space", scope_id=space_b["id"], operation_key="expired-b",
        expires_at="2020-01-01T00:00:00+08:00", validity_timezone="Asia/Shanghai",
    )
    backend.hits[f"space:{space_b['id']}"] = [
        {"score": 0.99, "metadata": {"record_id": only_a["id"], "record_version": 1}},
        {"score": 0.98, "metadata": {"record_id": expired_b["id"], "record_version": 1}},
    ]

    assert memories.recall("方案代号", space_id=space_b["id"]) == []


def test_change_cursor_dependency_validation_and_late_extraction_fencing(app_paths) -> None:
    _db, space, memories = _memory_service(app_paths)
    extracted = memories.apply_extracted(
        {
            "op": "add", "kind": "constraint", "text": "项目使用 SQLite",
            "subject_key": "storage", "scope_kind": "space", "scope_id": space["id"],
            "source_excerpt": "项目使用 SQLite",
        },
        source_message_ids=["message-1"],
        expected_epoch=0,
        operation_key="extract-v1",
    )
    assert extracted is not None
    old_ref = memories.dependency_ref(extracted)
    epoch_before = memories.current_epoch()
    corrected = memories.correct(
        extracted["id"],
        text="项目使用 DuckDB",
        expected_version=1,
        operation_key="correct-v2",
    )
    late = memories.apply_extracted(
        {
            "op": "add", "kind": "constraint", "text": "项目使用 SQLite",
            "subject_key": "storage", "scope_kind": "space", "scope_id": space["id"],
            "source_excerpt": "项目使用 SQLite",
        },
        source_message_ids=["message-1"],
        expected_epoch=epoch_before,
        operation_key="late-old-extract",
    )

    changes = memories.changes_since(epoch_before, space_id=space["id"])
    validation = memories.validate_dependency_refs([old_ref], space_id=space["id"])
    assert corrected["change_epoch"] > epoch_before
    assert [(item["operation"], item["version"]) for item in changes["items"]] == [
        ("corrected", 2)
    ]
    assert validation["valid"] is False and validation["stale"] == [old_ref]
    assert late is None


def test_unresolved_automatic_conflict_needs_review_and_is_not_recalled(app_paths) -> None:
    _db, space, memories = _memory_service(app_paths)
    first = memories.apply_extracted(
        {
            "op": "add", "kind": "decision", "text": "项目采用方案甲",
            "subject_key": "chosen_plan", "scope_kind": "space", "scope_id": space["id"],
            "source_excerpt": "我决定项目采用方案甲",
        },
        source_message_ids=["message-a"], expected_epoch=0, operation_key="proposal-a",
    )
    assert first is not None and first["status"] == "active"
    second = memories.apply_extracted(
        {
            "op": "add", "kind": "decision", "text": "项目采用方案乙",
            "subject_key": "chosen_plan", "scope_kind": "space", "scope_id": space["id"],
            "source_excerpt": "也许项目采用方案乙",
        },
        source_message_ids=["message-b"],
        expected_epoch=memories.current_epoch(),
        operation_key="proposal-b",
    )

    assert second is not None and second["status"] == "needs_review"
    assert second["id"] not in {item["id"] for item in memories.recall("方案", space_id=space["id"])}
    assert second["id"] in {
        item["id"] for item in memories.list(space_id=space["id"], include_inactive=True)
    }


def test_concurrent_memory_changes_get_distinct_epochs_and_paginate_without_loss(
    app_paths, monkeypatch,
) -> None:
    db, space, first_writer = _memory_service(app_paths)
    second_writer = MemoryService(db)
    first_holds_lock = Event()
    release_first = Event()
    second_attempted_write = Event()
    original_increment = first_writer._increment_epoch
    original_second_transaction = second_writer._memory_write_transaction

    def gated_increment(connection):
        value = original_increment(connection)
        first_holds_lock.set()
        assert release_first.wait(5), "first writer was not released"
        return value

    @contextmanager
    def observed_second_transaction():
        second_attempted_write.set()
        with original_second_transaction() as connection:
            yield connection

    monkeypatch.setattr(first_writer, "_increment_epoch", gated_increment)
    monkeypatch.setattr(
        second_writer, "_memory_write_transaction", observed_second_transaction
    )
    start_epoch = first_writer.current_epoch()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(
            first_writer.save_explicit,
            text="并发写入甲",
            subject_key="concurrent_a",
            kind="constraint",
            scope_kind="space",
            scope_id=space["id"],
            operation_key="concurrent-a",
        )
        assert first_holds_lock.wait(5)
        second_future = pool.submit(
            second_writer.save_explicit,
            text="并发写入乙",
            subject_key="concurrent_b",
            kind="constraint",
            scope_kind="space",
            scope_id=space["id"],
            operation_key="concurrent-b",
        )
        assert second_attempted_write.wait(5)
        assert not second_future.done()
        release_first.set()
        first = first_future.result(timeout=5)
        second = second_future.result(timeout=5)

    assert first["change_epoch"] < second["change_epoch"]
    first_page = first_writer.changes_since(start_epoch, space_id=space["id"], limit=1)
    second_page = first_writer.changes_since(
        first_page["next_epoch"], space_id=space["id"], limit=10
    )
    assert [item["memory_id"] for item in first_page["items"]] == [first["id"]]
    assert [item["memory_id"] for item in second_page["items"]] == [second["id"]]


def test_forget_and_old_extraction_cannot_cross_the_guarded_commit(
    app_paths, monkeypatch,
) -> None:
    db, space, seed_writer = _memory_service(app_paths)
    original = seed_writer.apply_extracted(
        {
            "op": "add",
            "kind": "constraint",
            "text": "发布前必须完成回滚演练",
            "subject_key": "release_restore",
            "scope_kind": "space",
            "scope_id": space["id"],
            "source_excerpt": "发布前必须完成回滚演练",
        },
        source_message_ids=["old-message"],
        expected_epoch=0,
        operation_key="old-proposal-seed",
    )
    assert original is not None
    proposal_epoch = seed_writer.current_epoch()
    extraction_writer = MemoryService(db)
    forget_writer = MemoryService(db)
    proposal_reached_final_guard = Event()
    release_proposal = Event()
    forget_attempted_write = Event()
    original_save_extracted = extraction_writer._save_extracted
    original_forget_transaction = forget_writer._memory_write_transaction

    def gated_save_extracted(connection, **values):
        proposal_reached_final_guard.set()
        assert release_proposal.wait(5), "old proposal was not released"
        return original_save_extracted(connection, **values)

    @contextmanager
    def observed_forget_transaction():
        forget_attempted_write.set()
        with original_forget_transaction() as connection:
            yield connection

    monkeypatch.setattr(extraction_writer, "_save_extracted", gated_save_extracted)
    monkeypatch.setattr(
        forget_writer, "_memory_write_transaction", observed_forget_transaction
    )
    stale_proposal = {
        "op": "add",
        "kind": "constraint",
        "text": "发布前必须完成回滚演练",
        "subject_key": "release_restore",
        "scope_kind": "space",
        "scope_id": space["id"],
        "source_excerpt": "发布前必须完成回滚演练",
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        proposal_future = pool.submit(
            extraction_writer.apply_extracted,
            stale_proposal,
            source_message_ids=["old-message"],
            expected_epoch=proposal_epoch,
            operation_key="old-proposal-in-flight",
        )
        assert proposal_reached_final_guard.wait(5)
        forget_future = pool.submit(
            forget_writer.forget,
            original["id"],
            expected_version=1,
            operation_key="forget-during-old-proposal",
        )
        assert forget_attempted_write.wait(5)
        assert not forget_future.done()
        release_proposal.set()
        proposal_result = proposal_future.result(timeout=5)
        forgotten = forget_future.result(timeout=5)

    assert proposal_result is not None and proposal_result["id"] == original["id"]
    assert forgotten["status"] == "forgotten"
    with db.connect() as connection:
        active_count = connection.execute(
            """
            SELECT COUNT(*) AS value FROM assistant_memories
            WHERE principal_id=? AND scope_kind='space' AND scope_id=?
              AND subject_key='release_restore' AND status='active'
            """,
            (seed_writer.principal_id, str(space["id"])),
        ).fetchone()["value"]
    assert active_count == 0
    assert extraction_writer.apply_extracted(
        stale_proposal,
        source_message_ids=["old-message"],
        expected_epoch=proposal_epoch,
        operation_key="old-proposal-after-forget",
    ) is None


def test_admission_gate_distinguishes_quote_rejection_adoption_and_temporary_request() -> None:
    gate = AssistantRuntime._proposal_is_user_memory
    assert not gate("视频说应该使用图数据库", {"kind": "decision"})
    assert not gate("我不同意使用图数据库", {"kind": "decision"})
    assert gate("我决定本项目采用 SQLite", {"kind": "decision"})
    assert not gate("这次回答短一点", {"kind": "preference"})
    assert gate("以后默认先给结论", {"kind": "preference"})
    assert gate("我正在准备开发岗面试", {"kind": "context"})


def test_current_schema_and_semantic_unavailable_are_reported_truthfully(app_paths) -> None:
    db, space, memories = _memory_service(app_paths)
    _save(
        memories, space["id"], text="项目只使用本地数据库",
        subject="local_database", key="local-only",
    )
    result = memories.recall_with_status("本地数据库", space_id=space["id"])
    with db.connect() as connection:
        version = connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()["value"]
        memory_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(assistant_memories)")
        }
        change_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(assistant_memory_changes)")
        }

    assert SCHEMA_VERSION == 25 and int(version) == 25
    assert {"validity_note", "validity_timezone", "change_epoch"} <= memory_columns
    assert "memory_epoch" in change_columns
    assert result["semantic_index"] == "unavailable"
    assert result["authoritative_store"] == "sqlite"
    assert result["items"][0]["semantic_index_ready"] is False
