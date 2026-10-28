"""P1 result index against guarded real PG; no provider/network execution."""

from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from shiliu.assistant.notifications import (
    NotificationService,
    message_id,
    plan_fingerprint,
)
from shiliu.assistant.pg_store import PgAssistantRunStore
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.runtime_contract import AssistantConflict
from shiliu.assistant.api import router
from test_wiki import wiki_parts, topics, create


def service(parts):
    db, _, wiki, *_ = parts
    runtime = SimpleNamespace(
        store=PgAssistantRunStore(db), wiki=wiki, memories=MemoryService(db)
    )
    return NotificationService(runtime)


def counts(db):
    with db.connect(read_only=True) as c:
        return tuple(
            c.execute(f"SELECT count(*) n FROM {table}").fetchone()["n"]
            for table in (
                "assistant_wiki_changes",
                "assistant_memory_changes",
                "assistant_notifications",
            )
        )


def save_memory(s, **extra):
    return s.runtime.memories.save_explicit(
        text="P1独立记忆",
        subject_key="p1",
        kind="context",
        scope_kind="user",
        scope_id=None,
        operation_key="p1-save",
        **extra,
    )


def test_atomic_rollback_replay_and_read_only_get(wiki_parts, monkeypatch):
    s = service(wiki_parts)
    db, _, wiki, space, msg, *_ = wiki_parts
    initial = counts(db)
    with pytest.raises(RuntimeError):
        with db.connect(guard=True) as c:
            create_args = dict(
                space_id=space,
                title="原子写入",
                purpose="测试事务",
                blocks=topics()[0]["blocks"],
                source_message_id=msg,
                operation_key="atomic",
                conn=c,
                prepared_sources={},
            )
            wiki.save_discussion(**create_args)
            s.runtime.memories.save_explicit(
                text="回滚的记忆",
                subject_key="rollback",
                kind="context",
                scope_kind="user",
                scope_id=None,
                operation_key="rollback",
                _connection=c,
            )
            raise RuntimeError("rollback")
    assert counts(db) == initial
    page = create(wiki, space, msg)
    memory = save_memory(s, source_message_ids=[msg])
    assert create(wiki, space, msg)["id"] == page["id"]
    assert save_memory(s, source_message_ids=[msg])["id"] == memory["id"]
    assert counts(db) == (initial[0] + 1, initial[1] + 1, initial[2] + 2)

    def forbidden(*a, **kw):
        raise AssertionError("GET attempted write/provider")

    monkeypatch.setattr(wiki, "_prepare_sources_for_write", forbidden)
    monkeypatch.setattr(wiki.sources.snapshots, "capture", forbidden)
    before = counts(db)
    rows = s.list(show_history=True)["items"]
    assert len(rows) == 2
    for row in rows:
        detail = s.get(row["id"])
        assert detail["source_times"]
        assert any(l["kind"] == "thread" for l in detail["links"])
    assert counts(db) == before


def test_old_pending_identity_read_decide_effects_and_no_duplicate(wiki_parts):
    s = service(wiki_parts)
    db, _, wiki, space, msg, *_ = wiki_parts
    plan = wiki.propose_discussion(
        space_id=space,
        topics=topics(),
        omitted=[],
        source_message_id=msg,
        request_key="old",
    )
    identity = message_id(db.context, f"plan:{plan['id']}:{plan_fingerprint(plan)}")
    old = datetime.now(timezone.utc) - timedelta(days=40)
    with db.connect() as c:
        c.execute("DELETE FROM assistant_notifications")
        c.execute(
            "UPDATE assistant_knowledge_plans SET created_at=%s WHERE id=%s",
            (old, plan["id"]),
        )
    assert counts(db)[2] == 0
    assert s.list()["items"][0]["id"] == identity
    assert counts(db)[2] == 0
    original = s.get(identity)["created_at"]
    s.read([identity])
    read = s.get(identity)["read_at"]
    assert s.list()["items"][0]["id"] == identity
    result = wiki.decide_discussion_plan(
        plan["id"],
        space_id=space,
        expected_version=plan["version"],
        accept=True,
        operation_key="decide",
    )
    assert result["status"] == "completed"
    detail = s.get(identity)
    assert detail["read_at"] == read and detail["created_at"] == original
    assert len(detail["effect_refs"]) == 2 and detail["business_state"] == "applied"
    activity = detail["activity_at"]
    wiki.decide_discussion_plan(
        plan["id"],
        space_id=space,
        expected_version=plan["version"],
        accept=True,
        operation_key="again",
    )
    assert counts(db)[2] == 1 and s.get(identity)["activity_at"] == activity


def test_content_revision_preserves_review_and_new_identity(wiki_parts):
    s = service(wiki_parts)
    _, _, wiki, space, msg, *_ = wiki_parts
    plan = wiki.propose_discussion(
        space_id=space,
        topics=topics(),
        omitted=[],
        source_message_id=msg,
        request_key="revise",
    )
    a = s.list()["items"][0]
    s.read([a["id"]])
    new = topics()
    new[0]["blocks"][0]["markdown"] = "新的审核内容"
    updated = wiki.revise_discussion_plan(
        plan["id"],
        space_id=space,
        expected_version=1,
        topics=new,
        omitted=[],
        operation_key="revise",
    )
    values = s.list(show_history=True)["items"]
    assert len(values) == 2 and len({v["id"] for v in values}) == 2
    assert s.get(a["id"])["business_state"] == "expired"
    assert (
        s.get(a["id"])["detail"]["payload"]["topics"][0]["blocks"][0]["markdown"]
        == topics()[0]["blocks"][0]["markdown"]
    )
    b = next(v for v in values if v["id"] != a["id"])
    assert b["read_at"] is None
    assert plan_fingerprint(updated) != plan_fingerprint(plan)


def test_safe_undo_click_rechecks_version_and_unversioned_save(wiki_parts):
    s = service(wiki_parts)
    db, _, wiki, space, msg, *_ = wiki_parts
    memory = save_memory(s)
    row = s.list()["items"][0]
    assert s.get(row["id"])["actions"][0]["kind"] == "undo"
    # Duplicate save leaves version=1 yet adoption makes the old effect unsafe.
    s.runtime.memories.save_explicit(
        text="P1独立记忆",
        subject_key="p1",
        kind="context",
        scope_kind="user",
        scope_id=None,
        operation_key="later-save",
    )
    with pytest.raises(AssistantConflict):
        s.undo(row["id"], expected_version=1, operation_key="undo-refused")
    assert s.runtime.memories.get(memory["id"])["status"] == "active"
    page = create(wiki, space, msg)
    row = next(v for v in s.list()["items"] if v["origin_type"] == "wiki_change")
    assert s.get(row["id"])["actions"][0]["kind"] == "undo"
    changed = wiki.edit_block(
        page["id"],
        block_id=page["blocks"][0]["stable_id"],
        markdown="后续人工编辑不能丢失",
        expected_version=1,
        operation_key="later-edit",
    )
    with pytest.raises(AssistantConflict):
        s.undo(row["id"], expected_version=1, operation_key="bad-undo")
    assert wiki.get_page(page["id"])["version"] == changed["version"]
    assert wiki.get_page(page["id"])["blocks"][0]["markdown"] == "后续人工编辑不能丢失"


def test_memory_undo_forget_redaction_and_wiki_creation_archive(wiki_parts):
    s = service(wiki_parts)
    _, _, wiki, space, msg, *_ = wiki_parts
    memory = save_memory(s)
    row = s.list()["items"][0]
    s.undo(row["id"], expected_version=1, operation_key="undo")
    assert s.runtime.memories.get(memory["id"])["status"] == "forgotten"
    assert (
        s.get(row["id"])["detail"] is None
        and s.get(row["id"])["business_state"] == "undone"
    )
    assert counts(s.db)[2] == 1
    page = create(wiki, space, msg)
    row = next(v for v in s.list()["items"] if v["origin_type"] == "wiki_change")
    s.undo(row["id"], expected_version=1, operation_key="wiki-undo")
    assert wiki.get_page(page["id"], include_hidden=True)["status"] == "archived"
    assert counts(s.db)[2] == 2


def test_cursor_unread_history_filters_and_api(wiki_parts):
    s = service(wiki_parts)
    db, _, wiki, space, msg, *_ = wiki_parts
    for i in range(3):
        s.runtime.memories.save_explicit(
            text=f"自动记忆 {i}",
            subject_key=f"auto{i}",
            kind="context",
            scope_kind="user",
            scope_id=None,
            operation_key=f"auto{i}",
            origin="extracted",
            source_message_ids=[msg],
        )
    with db.connect() as c:
        c.execute(
            "UPDATE assistant_notifications SET created_at=clock_timestamp()-interval '40 days',activity_at=clock_timestamp()-interval '40 days'"
        )
    first = s.list(limit=1)
    assert first["unread_count"] == 3 and first["next_cursor"]
    second = s.list(limit=1, cursor=first["next_cursor"])
    assert (
        second["items"][0]["id"] != first["items"][0]["id"]
        and second["unread_count"] == 3
    )
    with pytest.raises(ValueError):
        s.list(view="pending", cursor=first["next_cursor"])
    identity = first["items"][0]["id"]
    s.read([identity])
    assert s.list()["unread_count"] == 2
    assert len(s.list()["items"]) == 2 and len(s.list(show_history=True)["items"]) == 3
    app = FastAPI()
    app.include_router(router)
    app.state.core = SimpleNamespace(
        config=SimpleNamespace(assistant_enabled=True), assistant_runtime=s.runtime
    )
    with TestClient(app) as client:
        assert (
            client.get("/api/assistant/messages/unread-count").json()["unread_count"]
            == 2
        )
        assert (
            client.get("/api/assistant/messages", params={"limit": 1}).json()[
                "unread_count"
            ]
            == 2
        )
        assert client.get("/api/assistant/messages/missing").status_code == 404


def test_legacy_proposal_stable_id_read_accept_and_replay(wiki_parts):
    s = service(wiki_parts)
    db, _, wiki, space, msg, *_ = wiki_parts
    left = create(wiki, space, msg, title="合并左", op="left")
    right = create(wiki, space, msg, title="合并右", op="right")
    for p, text in [(left, "人工观点甲"), (right, "人工观点乙")]:
        wiki.edit_block(
            p["id"],
            block_id=p["blocks"][0]["stable_id"],
            markdown=text,
            expected_version=1,
            operation_key="edit" + p["id"],
        )
    proposal = wiki.merge_pages(
        left["id"],
        right["id"],
        space_id=space,
        source_version=2,
        target_version=2,
        operation_key="proposal",
    )
    identity = message_id(db.context, f"wiki-proposal:{proposal['proposal_id']}")
    with db.connect() as c:
        c.execute("DELETE FROM assistant_notifications")
    assert s.list()["items"][0]["id"] == identity and counts(db)[2] == 0
    s.read([identity])
    read = s.get(identity)["read_at"]
    created = s.get(identity)["created_at"]
    assert s.get(identity)["actions"][0]["kind"] == "proposal"
    wiki.decide_proposal(
        proposal["proposal_id"], space_id=space, accept=True, operation_key="accept"
    )
    wiki.decide_proposal(
        proposal["proposal_id"], space_id=space, accept=True, operation_key="again"
    )
    detail = s.get(identity)
    assert detail["read_at"] == read and detail["created_at"] == created
    assert (
        detail["business_state"] == "applied"
        and len(detail["effect_refs"]) == 2
        and counts(db)[2] == 1
    )

    assert detail["applied_at"] is not None
    assert (
        next(r for r in detail["object_refs"] if r["id"] == right["id"])["version"] == 3
    )
    assert detail["reason"]


def test_reused_full_receipt_preserves_intermediate_candidate(wiki_parts):
    s = service(wiki_parts)
    _, _, wiki, space, msg, *_ = wiki_parts
    plan = wiki.propose_discussion(
        space_id=space,
        topics=topics(),
        omitted=[],
        source_message_id=msg,
        request_key="abc",
    )
    second = topics()
    second[0]["blocks"][0]["markdown"] = "候选B的真实内容"
    b = wiki.revise_discussion_plan(
        plan["id"],
        space_id=space,
        expected_version=1,
        topics=second,
        omitted=[],
        operation_key="B",
    )
    identity = message_id(s.context, f"plan:{b['id']}:{plan_fingerprint(b)}")
    third = topics()
    third[0]["blocks"][0]["markdown"] = "候选C的真实内容"
    wiki.revise_discussion_plan(
        plan["id"],
        space_id=space,
        expected_version=2,
        topics=third,
        omitted=[],
        operation_key="C",
    )
    detail = s.get(identity)
    assert (
        detail["detail"]["payload"]["topics"][0]["blocks"][0]["markdown"]
        == "候选B的真实内容"
    )
    newest = s.list()["items"][0]
    assert newest["cause_refs"]["supersedes_message_id"] == identity
    assert newest["read_at"] is None


def test_completed_plan_and_memory_history_redacted_after_forget(wiki_parts):
    s = service(wiki_parts)
    db, _, wiki, space, msg, *_ = wiki_parts
    memory = save_memory(s, source_message_ids=[msg])
    values = topics()[:1]
    values[0]["blocks"][0].update(memory_id=memory["id"], memory_version=1)
    plan = wiki.propose_discussion(
        space_id=space,
        topics=values,
        omitted=[],
        source_message_id=msg,
        request_key="private",
    )
    identity = message_id(s.context, f"plan:{plan['id']}:{plan_fingerprint(plan)}")
    wiki.decide_discussion_plan(
        plan["id"],
        space_id=space,
        expected_version=1,
        accept=True,
        operation_key="accept",
    )
    assert s.get(identity)["detail"]["payload"]["topics"]
    s.runtime.memories.forget(memory["id"], expected_version=1, operation_key="forget")
    detail = s.get(identity)
    assert "payload" not in detail["detail"]
    assert "P1独立记忆" not in str(detail)
    for row in s.list(show_history=True)["items"]:
        if row["origin_type"] == "memory_change":
            assert s.get(row["id"])["detail"] is None


def test_legacy_issue_recovery_replay_and_cross_owner(wiki_parts):
    from shiliu.assistant.notifications import record
    from shiliu.db import Database
    from shiliu.storage.scope import ResourceContext

    s = service(wiki_parts)
    db, _, wiki, space, msg, *_ = wiki_parts
    with db.connect() as c:
        job = s.store.enqueue_job(
            c,
            kind="memory_index",
            dedupe_key="legacy-failure",
            payload={"memory_id": "missing", "version": 1},
        )
        c.execute(
            "UPDATE assistant_jobs SET status='blocked',created_at=clock_timestamp()-interval '1 day' WHERE id=%s",
            (job,),
        )
    row = next(r for r in s.list()["items"] if r["origin_type"] == "job_issue")
    assert row["business_state"] == "important_failure"
    s.read([row["id"]])
    assert s.list(view="issues")["items"]
    with db.connect() as c:
        c.execute("UPDATE assistant_jobs SET status='completed' WHERE id=%s", (job,))
    assert s.get(row["id"])["business_state"] == "applied"
    # Trusted other resource context cannot resolve either origin or message.
    with db.connect() as c:
        c.execute("INSERT INTO users(id,display_name) VALUES('other','other')")
        c.execute(
            "INSERT INTO workspaces(id,kind,owner_user_id) VALUES('personal:other','personal','other')"
        )
        c.execute("INSERT INTO workspace_guards(workspace_id) VALUES('personal:other')")
    other = Database(db.pg, ResourceContext("personal:other", "other"))
    other_s = NotificationService(
        SimpleNamespace(
            store=PgAssistantRunStore(other),
            wiki=wiki,
            memories=MemoryService(other, principal_id="other"),
        )
    )
    assert other_s.list()["items"] == []
    with pytest.raises(KeyError):
        other_s.get(row["id"])
    with pytest.raises(KeyError):
        other_s.read([row["id"]])
    with pytest.raises(KeyError):
        s.list(space_id=987654)


def test_notification_failure_rolls_back_business_and_direct_plan_aggregates(
    wiki_parts, monkeypatch
):
    import shiliu.assistant.notifications as module

    s = service(wiki_parts)
    db, _, wiki, space, msg, *_ = wiki_parts
    initial = counts(db)
    original = module.record

    def fail(*args, **kwargs):
        raise RuntimeError("notification insert failed")

    monkeypatch.setattr(module, "record", fail)
    with pytest.raises(RuntimeError, match="notification insert failed"):
        save_memory(s)
    with pytest.raises(RuntimeError, match="notification insert failed"):
        create(wiki, space, msg)
    assert counts(db) == initial
    monkeypatch.setattr(module, "record", original)
    plan = wiki.save_discussion_topics(
        space_id=space,
        topics=topics(),
        omitted=[],
        source_message_id=msg,
        request_key="direct",
    )
    assert plan["status"] == "completed"
    rows = s.list()["items"]
    assert len(rows) == 1 and rows[0]["business_state"] == "applied"
    assert len(rows[0]["effect_refs"]) == 2 and s.list(view="pending")["items"] == []


def test_pending_priority_single_plan_undo_and_modified_wiki_restore(wiki_parts):
    s = service(wiki_parts)
    _, _, wiki, space, msg, *_ = wiki_parts
    plan = wiki.propose_discussion(
        space_id=space,
        topics=topics()[:1],
        omitted=[],
        source_message_id=msg,
        request_key="single",
    )
    identity = s.list()["items"][0]["id"]
    s.runtime.memories.save_explicit(
        text="较新后台记忆",
        subject_key="new-auto",
        kind="context",
        scope_kind="user",
        scope_id=None,
        operation_key="new-auto",
        origin="extracted",
    )
    assert s.list(limit=1)["items"][0]["id"] == identity
    result = wiki.decide_discussion_plan(
        plan["id"],
        space_id=space,
        expected_version=1,
        accept=True,
        operation_key="single-accept",
    )
    assert s.get(identity)["actions"][0]["kind"] == "undo"
    s.undo(identity, expected_version=1, operation_key="single-undo")
    assert s.get(identity)["business_state"] == "undone"
    # Undo an actual discussion update, constrained to its direct before.
    page = create(wiki, space, msg, title="只撤本次更新", op="initial")
    wiki.save_discussion(
        space_id=space,
        title="只撤本次更新",
        purpose="第二次保存",
        blocks=topics()[1]["blocks"],
        source_message_id=msg,
        operation_key="update",
        expected_version=1,
    )
    row = next(
        r
        for r in s.list()["items"]
        if r["origin_type"] == "wiki_change"
        and r["object_refs"][0]["id"] == page["id"]
        and r["object_refs"][0]["version"] == 2
    )
    assert s.get(row["id"])["actions"][0]["kind"] == "undo"
    s.undo(row["id"], expected_version=2, operation_key="restore-before")
    current = wiki.get_page(page["id"])
    assert current["version"] == 3
    assert current["blocks"] == page["blocks"]


def test_source_history_readonly_links_and_invalid_source_hides_text(
    wiki_parts, monkeypatch
):
    from test_wiki import source_page

    s = service(wiki_parts)
    db, _, wiki, space, msg, *_ = wiki_parts
    page, vid, sid, ref, old = source_page(wiki_parts)
    db.update_video(
        vid,
        video_url="https://www.bilibili.com/video/BV1xx411c7mD?p=1",
        published_at=1700000000,
    )
    identity = s.list()["items"][0]["id"]

    def no_capture(*a, **kw):
        raise AssertionError("message GET captured sources")

    monkeypatch.setattr(wiki.sources.snapshots, "capture", no_capture)
    detail = s.get(identity)
    assert detail["detail"]["after"]["blocks"]
    video = next(l for l in detail["links"] if l["kind"] == "video")
    assert video["url"].endswith("?p=1") and "&t=" not in video["url"]
    assert any(t["kind"] == "video_published" for t in detail["source_times"])
    db.update_video(vid, is_ignored=True)
    hidden = s.get(identity)
    assert hidden["detail"]["after"]["blocks"] == []
    assert not any(l["kind"] == "video" for l in hidden["links"])
    from shiliu.assistant.snapshots import SourceChangedDuringCapture

    def missing_file(*a, **kw):
        raise SourceChangedDuringCapture("source_material_unavailable")

    monkeypatch.setattr(wiki.sources.snapshots, "_build_snapshot", missing_file)
    unavailable = s.get(identity)
    assert unavailable["detail"]["after"]["blocks"] == []


def test_partial_success_survives_reused_candidate_receipt_and_replacement(
    wiki_parts, monkeypatch
):
    s = service(wiki_parts)
    db, _, wiki, space, msg, *_ = wiki_parts
    plan = wiki.propose_discussion(
        space_id=space,
        topics=topics(),
        omitted=[],
        source_message_id=msg,
        request_key="partial-history",
    )
    btopics = topics()
    btopics[0]["blocks"][0]["markdown"] = "B版待审内容"
    b = wiki.revise_discussion_plan(
        plan["id"],
        space_id=space,
        expected_version=1,
        topics=btopics,
        omitted=[],
        operation_key="B",
    )
    identity = message_id(s.context, f"plan:{b['id']}:{plan_fingerprint(b)}")
    original = wiki.save_discussion

    def fail_second(**kw):
        if kw["title"] == btopics[1]["title"]:
            raise AssistantConflict("synthetic second topic failure")
        return original(**kw)

    monkeypatch.setattr(wiki, "save_discussion", fail_second)
    partial = wiki.decide_discussion_plan(
        plan["id"],
        space_id=space,
        expected_version=2,
        accept=True,
        operation_key="partial",
    )
    assert (
        partial["status"] == "partial"
        and partial["results"]["0"]["status"] == "completed"
    )
    first = partial["results"]["0"]
    monkeypatch.setattr(wiki, "save_discussion", original)
    replacement = {
        **btopics[1],
        "blocks": [{**btopics[1]["blocks"][0], "markdown": "C版修正内容"}],
    }
    c = wiki.replace_discussion_topics(
        plan["id"],
        space_id=space,
        expected_version=2,
        replacements=[{"index": 1, "topic": replacement}],
        request={"source_message_id": msg},
        operation_key="C",
    )
    old = s.get(identity)
    assert (
        old["business_state"] == "partial"
        and old["object_refs"][0]["id"] == first["page_id"]
    )
    assert old["detail"]["results"]["0"]["status"] == "completed"
    complete = wiki.decide_discussion_plan(
        plan["id"],
        space_id=space,
        expected_version=c["version"],
        accept=True,
        operation_key="C-accept",
    )
    assert (
        complete["status"] == "completed"
        and wiki.get_page(first["page_id"])["version"] == 1
    )
