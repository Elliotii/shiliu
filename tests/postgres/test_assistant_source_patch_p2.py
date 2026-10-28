# ruff: noqa: F811, RUF059
"""P2 real isolated PG/Artifacts and Runtime, with local scripted transports only."""

from types import SimpleNamespace

import pytest
from test_assistant_runtime_p0 import (
    drain,
    enqueue,
    row,
    runtime_parts,  # noqa: F401
    trace_completions,
)  # noqa: F401
from test_wiki import add_source, create, wiki_parts  # noqa: F401

from shiliu.assistant.notifications import NotificationService, message_id
from shiliu.assistant.runtime_contract import AssistantConflict
from shiliu.assistant.wiki import MaintenanceYield


def setup(runtime_parts, wiki_parts, *, op="add_block"):
    db, store, runtime, provider, space, msg, sources = runtime_parts
    page = create(runtime.wiki, space, msg, title="PG事务")
    vid, sid, ref, captured = add_source(wiki_parts)
    # Automatic maintenance requires a bounded current Space, through the real API.
    store.update_space(
        space,
        expected_scope_version=1,
        source_ids=[sid],
        all_active=False,
        maintenance_mode="automatic",
    )
    original = provider.generate_json

    def generated(**kw):
        response = original(**kw)
        if "Wiki" in kw["system"]:
            response.update(
                operation=op, target_block_id=page["blocks"][0]["stable_id"]
            )
        return response

    provider.generate_json = generated
    with db.connect() as c:
        generation = runtime.wiki._ensure_dirty(c, vid)
        runtime.wiki._enqueue_reconcile(c, vid, generation)
    return page, vid, captured


def proposal(runtime_parts):
    db = runtime_parts[0]
    with db.connect(read_only=True) as c:
        return dict(
            c.execute(
                "SELECT * FROM assistant_wiki_proposals WHERE kind='source_patch' ORDER BY content_version DESC,created_at DESC LIMIT 1"
            ).fetchone()
        )


def decision(wiki, p, *, accept=True, key="decide"):
    return wiki.decide_proposal(
        p["id"],
        space_id=p["space_id"],
        accept=accept,
        operation_key=key,
        expected_content_version=p["content_version"],
        expected_target_version=p["target_version"],
    )


def test_runtime_queued_staged_review_atomic_confirm_replay(
    runtime_parts, wiki_parts, monkeypatch, record_property
):
    db, store, runtime, provider, space, msg, sources = runtime_parts
    page, vid, captured = setup(runtime_parts, wiki_parts)
    attempts = trace_completions(monkeypatch)
    real = runtime.wiki.apply_patch
    yielded = []

    def once(**kw):
        if not yielded:
            yielded.append(True)
            raise MaintenanceYield("P2 staged upgrade recovery fixture")
        return real(**kw)

    monkeypatch.setattr(runtime.wiki, "apply_patch", once)
    jobs = drain(runtime)
    assert {j["kind"] for j in jobs} == {
        "source_reconcile",
        "source_extract",
        "wiki_integrate",
    }
    assert provider.structured_calls == 2
    p = proposal(runtime_parts)
    assert (
        p["status"] == "pending"
        and p["source_page_id"] is None
        and p["source_version"] is None
    )
    assert runtime.wiki.get_page(page["id"])["version"] == 1
    with db.connect(read_only=True) as c:
        assert not c.execute(
            "SELECT 1 FROM assistant_wiki_dependencies WHERE page_id=%s", (page["id"],)
        ).fetchone()
        assert not c.execute(
            "SELECT 1 FROM scheduler_lanes WHERE active_job_id IS NOT NULL"
        ).fetchone()
    assert all(
        attempts[j["id"]] == 1 and row(store, j["id"])["status"] == "completed"
        for j in jobs
    )
    s = NotificationService(runtime)
    identity = message_id(db.context, f"wiki-proposal:{p['id']}")
    detail = s.get(identity)
    assert detail["business_state"] == "pending" and detail["source_type"] == "video"
    assert detail["detail"]["after"]["blocks"] and detail["processing_times"]
    assert any(a.get("expected_target_version") == 1 for a in detail["actions"])

    # A read cannot capture or enqueue work. Neither can a confirmation.
    def forbidden(*a, **kw):
        raise AssertionError("provider/capture invoked during review")

    monkeypatch.setattr(sources.snapshots, "capture", forbidden)
    monkeypatch.setattr(provider, "generate_json", forbidden)
    assert s.get(identity)["business_state"] == "pending"
    # Inject message failure after the shared writer: all formal state rolls back.
    notify = runtime.wiki._notify_proposal
    monkeypatch.setattr(
        runtime.wiki,
        "_notify_proposal",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("message failure")),
    )
    with pytest.raises(RuntimeError, match="message failure"):
        decision(runtime.wiki, p, key="rollback")
    assert proposal(runtime_parts)["status"] == "pending"
    assert runtime.wiki.get_page(page["id"])["version"] == 1
    monkeypatch.setattr(runtime.wiki, "_notify_proposal", notify)
    store.mark_user_activity()  # confirmation ignores background idle/lease/lane gates
    assert decision(runtime.wiki, p)["status"] == "accepted"
    assert decision(runtime.wiki, p)["version"] == 2
    assert decision(runtime.wiki, p, key="different")["status"] == "accepted"
    assert (
        decision(runtime.wiki, p, accept=False, key="opposite")["status"] == "accepted"
    )
    assert runtime.wiki.get_page(page["id"])["version"] == 2
    detail = s.get(identity)
    assert detail["business_state"] == "applied" and len(detail["effect_refs"]) == 1
    assert not any(a["kind"] == "undo" for a in detail["actions"])
    with db.connect(read_only=True) as c:
        assert (
            c.execute(
                "SELECT count(*) n FROM assistant_notifications WHERE origin_type='wiki_proposal'"
            ).fetchone()["n"]
            == 1
        )
        assert (
            c.execute(
                "SELECT count(*) n FROM assistant_wiki_changes WHERE page_id=%s",
                (page["id"],),
            ).fetchone()["n"]
            == 2
        )
    record_property("actual_provider_calls", 0)


@pytest.mark.parametrize("change", ["page", "source", "scope"])
def test_stale_read_validate_and_explicit_refresh(runtime_parts, wiki_parts, change):
    db, store, runtime, provider, space, msg, sources = runtime_parts
    page, vid, captured = setup(runtime_parts, wiki_parts)
    drain(runtime)
    p = proposal(runtime_parts)
    if change == "page":
        runtime.wiki.edit_block(
            page["id"],
            block_id=page["blocks"][0]["stable_id"],
            markdown="用户后续修改",
            expected_version=1,
            operation_key="edit",
        )
    elif change == "source":
        db.update_video(vid, title="改变来源身份")
    else:
        vid2, sid2, _, _ = add_source(wiki_parts, index=2)
        store.update_space(
            space, expected_scope_version=2, source_ids=[sid2], video_ids=[vid2]
        )
    before = provider.structured_calls
    s = NotificationService(runtime)
    identity = message_id(db.context, f"wiki-proposal:{p['id']}")
    assert s.get(identity)["business_state"] == "expired"
    assert provider.structured_calls == before
    result = runtime.wiki.validate_source_proposal(p["id"], space_id=space)
    assert result["status"] == "stale"
    assert decision(runtime.wiki, p)["status"] == "stale"
    assert runtime.wiki.get_page(page["id"], include_hidden=True)["version"] == (
        2 if change == "page" else 1
    )
    if change == "scope":
        with pytest.raises(AssistantConflict):
            runtime.wiki.refresh_source_proposal(
                p["id"], space_id=space, request_key="refresh"
            )
    else:
        refresh = runtime.wiki.refresh_source_proposal(
            p["id"], space_id=space, request_key="refresh"
        )
        assert refresh["status"] == "accepted"
        # Explicit refresh is a real three-stage recomputation, with Stub only.
        drain(runtime)
        b = proposal(runtime_parts)
        assert (
            b["id"] != p["id"]
            and b["content_version"] == 2
            and b["supersedes_id"] == p["id"]
        )
        assert b["status"] == "pending"
        assert provider.structured_calls > before


def test_reject_identical_input_and_real_request_and_batch_authorization(
    runtime_parts, wiki_parts
):
    db, store, runtime, provider, space, msg, sources = runtime_parts
    page, vid, captured = setup(runtime_parts, wiki_parts)
    jobs = drain(runtime)
    p = proposal(runtime_parts)
    assert decision(runtime.wiki, p, accept=False)["status"] == "rejected"
    integration = next(j for j in jobs if j["kind"] == "wiki_integrate")
    enqueue(
        store, kind="wiki_integrate", key="duplicate", payload=integration["payload"]
    )
    drain(runtime)
    assert (
        proposal(runtime_parts)["id"] == p["id"]
        and proposal(runtime_parts)["status"] == "rejected"
    )
    assert runtime.wiki.get_page(page["id"])["version"] == 1
    # A forged integration carrying a real request key but another topic is refused.
    runtime.wiki.request_topic(
        space_id=space,
        topic="PG事务",
        source_refs=[f"video:{vid}:{captured.revision}"],
        request_key="authorized",
        source_message_id=msg,
    )
    drain(runtime)
    assert runtime.wiki.get_page(page["id"])["version"] == 2
    assert proposal(runtime_parts)["status"] == "rejected"
    with db.connect(read_only=True) as c:
        payload = dict(
            c.execute(
                "SELECT payload_json FROM assistant_jobs WHERE kind='wiki_integrate' AND payload_json->>'request_key' IS NOT NULL ORDER BY created_at DESC LIMIT 1"
            ).fetchone()["payload_json"]
        )
        payload["task_topic"] = "越权目标"
        with pytest.raises(AssistantConflict, match="basis_mismatch"):
            runtime.wiki._source_direct_authorized(c, payload)
        payload["request_key"] = "forged"
        with pytest.raises(AssistantConflict):
            runtime.wiki._source_direct_authorized(c, payload)
    # Original approved maintenance batch remains direct for a different fresh source.
    vid2, sid2, ref2, captured2 = add_source(wiki_parts, index=2)
    store.update_space(space, expected_scope_version=2, source_ids=[sid2])
    batch = runtime.wiki.bootstrap_space(space, task_subset=[vid2])
    assert batch["queued"] == 1
    drain(runtime)
    assert runtime.wiki.get_page(page["id"])["version"] == 3


def test_revise_accept_then_new_supplement_preserves_accepted_A(
    runtime_parts, wiki_parts
):
    db, store, runtime, provider, space, msg, sources = runtime_parts
    page, vid, captured = setup(runtime_parts, wiki_parts, op="revise_block")
    drain(runtime)
    a = proposal(runtime_parts)
    assert runtime.wiki.get_page(page["id"])["version"] == 1
    assert decision(runtime.wiki, a)["status"] == "accepted"
    # New material leads to B on the real current version, never reopens A.
    vid2, sid2, ref2, _ = add_source(wiki_parts, index=2)
    store.update_space(
        space,
        expected_scope_version=2,
        source_ids=[*store.get_space(space)["source_ids"], sid2],
    )
    original = provider.generate_json

    def supplement(**kw):
        value = original(**kw)
        if "Wiki" in kw["system"]:
            value["operation"] = "add_block"
        return value

    provider.generate_json = supplement
    with db.connect() as c:
        generation = runtime.wiki._ensure_dirty(c, vid2)
        runtime.wiki._enqueue_reconcile(c, vid2, generation)
    drain(runtime)
    b = proposal(runtime_parts)
    assert (
        b["id"] != a["id"]
        and b["supersedes_id"] == a["id"]
        and b["target_version"] == 2
    )
    with db.connect(read_only=True) as c:
        assert runtime.wiki._source_proposal(c, a["id"])["status"] == "accepted"
    assert decision(runtime.wiki, b, key="second")["status"] == "accepted"
    assert runtime.wiki.get_page(page["id"])["version"] == 3
    assert decision(runtime.wiki, a, key="old")["status"] == "accepted"


@pytest.mark.parametrize("op", ["associate", "no_change"])
def test_automatic_non_body_operations_stay_legal(runtime_parts, wiki_parts, op):
    db, store, runtime, provider, space, *_ = runtime_parts
    page, vid, captured = setup(runtime_parts, wiki_parts, op=op)
    jobs = drain(runtime)
    assert all(row(store, j["id"])["status"] == "completed" for j in jobs)
    with db.connect(read_only=True) as c:
        assert not c.execute(
            "SELECT 1 FROM assistant_wiki_proposals WHERE kind='source_patch'"
        ).fetchone()
    assert runtime.wiki.get_page(page["id"])["version"] == (
        2 if op == "associate" else 1
    )


def test_candidate_preview_does_not_reveal_deleted_baseline(runtime_parts, wiki_parts):
    db, store, runtime, provider, space, *_ = runtime_parts
    page, _, _ = setup(runtime_parts, wiki_parts)
    runtime.wiki.manage_page(
        page["id"],
        space_id=space,
        action="delete_block",
        block_id=page["blocks"][0]["stable_id"],
        expected_version=1,
        operation_key="delete-before-review",
    )
    drain(runtime)
    p = proposal(runtime_parts)
    detail = NotificationService(runtime).get(
        message_id(db.context, f"wiki-proposal:{p['id']}")
    )
    assert detail["business_state"] == "pending"
    assert not detail["detail"]["before"]["blocks"]
    assert "模型编码应在事务之外" not in str(detail["detail"])


def test_auto_memory_identity_branches_remain_unavailable_for_creation_undo(wiki_parts):
    from shiliu.assistant.memory import MemoryService

    db, _, wiki, space, msg, *_ = wiki_parts
    memories = MemoryService(db)
    fact = dict(
        op="add",
        text="我决定接下来两周重点学习数据库基础",
        subject_key="p2-study",
        kind="context",
        scope_kind="space",
        scope_id=space,
        source_excerpt="我决定接下来两周重点学习数据库基础",
    )

    def apply(value, key):
        return memories.apply_extracted(
            value,
            source_message_ids=[msg],
            expected_epoch=memories.current_epoch(),
            operation_key=key,
        )

    one = apply(fact, "extract:p2:0")
    duplicate = apply(fact, "extract:p2:1")
    assert one and duplicate and one["id"] == duplicate["id"]
    with db.connect(read_only=True) as c:
        receipts = c.execute(
            "SELECT operation FROM assistant_mutation_receipts WHERE operation_key IN ('extract:p2:0','extract:p2:1')"
        ).fetchall()
        assert len(receipts) == 2 and all(
            r["operation"] == "memory_save" for r in receipts
        )
        assert (
            c.execute(
                "SELECT count(*) n FROM assistant_memory_changes WHERE memory_id=%s AND operation='created'",
                (one["id"],),
            ).fetchone()["n"]
            == 1
        )
    with pytest.raises(AssistantConflict):
        memories.undo_created(
            one["id"],
            save_operation_key="extract:p2:0",
            expected_version=1,
            operation_key="no-auto-undo",
        )
    revised = apply(
        {
            **fact,
            "op": "revise",
            "text": "我决定接下来两周重点练习数据库事务",
            "target_memory_id": one["id"],
            "expected_version": 1,
        },
        "extract:p2:2",
    )
    assert revised and revised["version"] == 2
    with db.connect(read_only=True) as c:
        assert (
            c.execute(
                "SELECT operation FROM assistant_mutation_receipts WHERE operation_key='extract:p2:2'"
            ).fetchone()["operation"]
            == "memory_correct"
        )
    detail = NotificationService(
        SimpleNamespace(store=runtime_store(db), wiki=wiki, memories=memories)
    ).list(show_history=True)
    assert all(
        not any(a["kind"] == "undo" for a in item["actions"])
        for item in detail["items"]
        if item["object_type"] == "memory"
    )


def runtime_store(db):
    from shiliu.assistant.pg_store import PgAssistantRunStore

    return PgAssistantRunStore(db)
