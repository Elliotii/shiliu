"""W09 business lifecycle on the formal PG schema and real ownership closure."""

import pytest
from psycopg.types.json import Jsonb
from shiliu.assistant.pg_access import PgAssistantAccess
from shiliu.assistant.wiki import WikiService
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.sources import CollectionSourceService
from shiliu.assistant.snapshots import SourceSnapshotStore
from shiliu.assistant.store import AssistantConflict
from shiliu.artifacts import ArtifactStore
from seed_rows import SyntheticGraph


@pytest.fixture
def wiki_parts(collection_db, tmp_path):
    db = collection_db
    with db.connect() as c:
        graph = SyntheticGraph(c)
        msg = graph.ensure("assistant_messages")
        run = graph.ensure("assistant_runs")
        space = graph.rows["assistant_spaces"]
        c.execute(
            "UPDATE assistant_spaces SET enabled=true,all_active=true WHERE id=%s",
            (space["id"],),
        )
        c.execute(
            "UPDATE assistant_runs SET status='running',run_epoch=1,working_state_json='{}',cancel_requested=false WHERE id=%s",
            (run["id"],),
        )
        c.execute(
            "UPDATE assistant_messages SET role='user',run_id=%s,content='请保存这次讨论，我喜欢白天学习数据库' WHERE id=%s",
            (run["id"], msg["id"]),
        )
    store = PgAssistantAccess(db)
    artifacts = ArtifactStore(tmp_path / "wiki-artifacts", db)
    sources = CollectionSourceService(
        db=db, artifacts=artifacts, snapshots=SourceSnapshotStore(db, artifacts)
    )
    wiki = WikiService(db=db, store=store, sources=sources)
    return db, store, wiki, space["id"], msg["id"], run["id"], sources


def topics():
    return [
        {
            "title": "数据库事务",
            "purpose": "保存讨论结论",
            "blocks": [
                {
                    "role": "analysis",
                    "heading": "事务边界",
                    "markdown": "模型编码应在事务之外，发布前重新校验版本。",
                }
            ],
        },
        {
            "title": "版本校验",
            "purpose": "保存校验方法",
            "blocks": [
                {
                    "role": "analysis",
                    "heading": "CAS",
                    "markdown": "用 version 和 epoch 拒绝迟到的结果。",
                }
            ],
        },
    ]


def create(wiki, space, msg, *, title="数据库事务", op="create"):
    return wiki.save_discussion(
        space_id=space,
        title=title,
        purpose="保存讨论结论",
        blocks=topics()[0]["blocks"],
        source_message_id=msg,
        operation_key=op,
    )


def test_discussion_receipt_lifecycle_cas_history_and_revert(wiki_parts):
    _, _, wiki, space, msg, _, _ = wiki_parts
    page = create(wiki, space, msg)
    assert page["version"] == 1 and page["blocks"]
    assert create(wiki, space, msg)["id"] == page["id"]
    edited = wiki.edit_block(
        page["id"],
        block_id=page["blocks"][0]["stable_id"],
        markdown="修改后的内容",
        expected_version=1,
        operation_key="edit",
    )
    assert edited["version"] == 2
    with pytest.raises(AssistantConflict, match="version_conflict"):
        wiki.edit_block(
            page["id"],
            block_id=page["blocks"][0]["stable_id"],
            markdown="旧版本编辑",
            expected_version=1,
            operation_key="stale",
        )
    deleted = wiki.manage_page(
        page["id"],
        space_id=space,
        action="delete_block",
        block_id=page["blocks"][0]["stable_id"],
        expected_version=2,
        operation_key="delete",
    )
    assert deleted["version"] == 3 and wiki.list_pages(space_id=space) == []
    restored = wiki.manage_page(
        page["id"],
        space_id=space,
        action="restore_block",
        block_id=page["blocks"][0]["stable_id"],
        expected_version=3,
        operation_key="restore-block",
    )
    assert restored["version"] == 4 and wiki.list_pages(space_id=space)
    wiki.manage_page(
        page["id"],
        space_id=space,
        action="archive",
        expected_version=4,
        operation_key="archive",
    )
    assert not wiki.list_pages(space_id=space)
    wiki.manage_page(
        page["id"],
        space_id=space,
        action="restore",
        expected_version=5,
        operation_key="restore-page",
    )
    assert wiki.get_page(page["id"], space_id=space)["version"] == 6
    assert len(wiki.changes(page["id"])) == 6


def test_w1_partial_repair_preserves_successful_page_and_receipts(wiki_parts):
    _, _, wiki, space, msg, _, _ = wiki_parts
    values = topics()
    values[1]["blocks"] = [
        {
            "role": "personal",
            "heading": "偏好",
            "markdown": "我喜欢白天学习数据库",
            "user_quote": "我喜欢白天学习数据库",
            "user_message_id": "missing",
        }
    ]
    plan = wiki.save_discussion_topics(
        space_id=space,
        topics=values,
        omitted=[],
        source_message_id=msg,
        request_key="request",
    )
    assert plan["status"] == "partial" and plan["results"]["0"]["status"] == "completed"
    one = wiki.list_pages(space_id=space)[0]
    fixed = wiki.replace_discussion_topics(
        plan["id"],
        space_id=space,
        expected_version=plan["version"],
        replacements=[
            {
                "index": 1,
                "topic": {
                    **values[1],
                    "blocks": [{**values[1]["blocks"][0], "user_message_id": msg}],
                },
            }
        ],
        operation_key="repair",
        request={"source_message_id": msg},
    )
    resumed = wiki.decide_discussion_plan(
        plan["id"],
        space_id=space,
        expected_version=fixed["version"],
        accept=True,
        operation_key="resume",
    )
    assert resumed["status"] == "completed"
    assert len(wiki.list_pages(space_id=space)) == 2
    assert wiki.get_page(one["id"])["version"] == one["version"]


def test_memory_personal_dependency_forget_and_scope(wiki_parts):
    db, _, wiki, space, msg, _, _ = wiki_parts
    page = create(wiki, space, msg)
    memories = MemoryService(db)
    memory = memories.save_explicit(
        text="我喜欢白天学习数据库",
        subject_key="study",
        kind="preference",
        scope_kind="space",
        scope_id=space,
        operation_key="memory",
        source_message_ids=[msg],
    )
    page = wiki.add_personal_note(
        page["id"],
        space_id=space,
        text=memory["text"],
        expected_version=1,
        operation_key="note",
        memory_id=memory["id"],
        memory_version=1,
        source_message_id=msg,
    )
    assert len(page["blocks"]) == 2
    memories.forget(memory["id"], expected_version=1, operation_key="forget")
    assert len(wiki.get_page(page["id"])["blocks"]) == 1
    with pytest.raises(KeyError):
        wiki.get_page(page["id"], space_id=999)


def add_source(parts, index=1, text="事务提交前必须核验来源版本。"):
    from test_collection_retrieval import add_video, FixedProvider
    from shiliu.retrieval.service import RetrievalService
    from shiliu.retrieval.dense import PgExactDenseIndex

    db, _, _, _, _, run, sources = parts
    lexical = RetrievalService(db=db, artifacts=sources.artifacts)
    dense = PgExactDenseIndex(db=db, provider=FixedProvider(), lexical=lexical)
    vid, sid = add_video(
        (db, sources.artifacts, lexical, dense), index=index, text=text
    )
    captured = sources.snapshots.capture(vid)
    ref = f"video:{vid}:{captured.revision}"
    with db.connect() as c:
        state = c.execute(
            "SELECT working_state_json FROM assistant_runs WHERE id=%s", (run,)
        ).fetchone()["working_state_json"]
        state.setdefault("model_delivered_materials", []).append(
            {
                "kind": "collection_read",
                "source_ref": ref,
                "view": "transcript",
                "projection": "正文",
            }
        )
        c.execute(
            "UPDATE assistant_runs SET working_state_json=%s WHERE id=%s",
            (Jsonb(state), run),
        )
    return vid, sid, ref, captured


def source_page(parts, title="PG来源", index=1):
    _, _, wiki, space, msg, _, _ = parts
    vid, sid, ref, captured = add_source(parts, index)
    page = wiki.save_discussion(
        space_id=space,
        title=title,
        purpose="保存来源证据",
        source_message_id=msg,
        operation_key="source:" + str(index),
        blocks=[
            {
                "role": "source",
                "heading": "来源事务",
                "markdown": "事务提交前必须核验来源版本。",
                "source_refs": [ref],
                "source_view": "transcript",
            }
        ],
    )
    return page, vid, sid, ref, captured


def wiki_index(parts, provider=None):
    from shiliu.assistant.wiki_retrieval import WikiHybridIndex
    from shiliu.assistant.wiki_jobs import WikiProjectionWorker
    from test_collection_retrieval import FixedProvider

    class Provider(FixedProvider):
        def embed_query(self, text, **kw):
            return super().embed_query(text)

    index = WikiHybridIndex(
        provider if provider is not None else Provider(), wiki=parts[2]
    )
    return index, WikiProjectionWorker(index, owner="wiki-worker")


def test_source_view_equivalence_change_and_actual_space_visibility(wiki_parts):
    db, _, wiki, space, msg, _, sources = wiki_parts
    page, vid, sid, ref, old = source_page(wiki_parts)
    assert wiki.get_page(page["id"])["blocks"]
    db.update_video(vid, title="仅标题变化")
    current = sources.snapshots.capture(vid)
    assert old.revision != current.revision and wiki.get_page(page["id"])["blocks"]
    # Transcript-equivalent source survives metadata-only comprehensive revision.
    assert wiki._source_dependency_current(
        video_id=vid,
        old_revision=old.revision,
        current_revision=current.revision,
        dependency_kind="view:transcript",
        cache={},
    )
    db.update_video(vid, is_ignored=True)
    assert not wiki.get_page(page["id"])["blocks"]
    db.update_video(vid, is_ignored=False)
    assert wiki.get_page(page["id"])["blocks"]


def test_w1_commit_before_plan_result_recovers_from_page_receipt(
    wiki_parts, monkeypatch
):
    _, _, wiki, space, msg, _, _ = wiki_parts
    original = wiki.save_discussion

    def crash(**kw):
        original(**kw)
        raise RuntimeError("synthetic connection lost after commit")

    monkeypatch.setattr(wiki, "save_discussion", crash)
    with pytest.raises(RuntimeError, match="after commit"):
        wiki.save_discussion_topics(
            space_id=space,
            topics=topics(),
            omitted=[],
            source_message_id=msg,
            request_key="crash",
        )
    page = wiki.list_pages(space_id=space)[0]
    monkeypatch.setattr(wiki, "save_discussion", original)
    resumed = wiki.save_discussion_topics(
        space_id=space,
        topics=topics(),
        omitted=[],
        source_message_id=msg,
        request_key="crash",
    )
    assert (
        resumed["status"] == "completed" and len(wiki.list_pages(space_id=space)) == 2
    )
    assert wiki.get_page(page["id"])["version"] == 1


def test_w2_merge_revert_keeps_later_deletion_and_archive(wiki_parts):
    _, _, wiki, space, msg, _, _ = wiki_parts
    source = create(wiki, space, msg, title="来源页", op="source")
    target = create(wiki, space, msg, title="目标页", op="target")
    wiki.edit_block(
        source["id"],
        block_id=source["blocks"][0]["stable_id"],
        markdown="应尊重后续删除的内容",
        expected_version=1,
        operation_key="edit",
    )
    merged = wiki.merge_pages(
        source["id"],
        target["id"],
        space_id=space,
        source_version=2,
        target_version=1,
        operation_key="merge",
    )
    assert merged["status"] == "merged"
    assert wiki.get_page(source["id"])["redirected_from"] == source["id"]
    page = wiki.get_page(target["id"])
    moved = next(b for b in page["blocks"] if b["markdown"] == "应尊重后续删除的内容")
    wiki.manage_page(
        target["id"],
        space_id=space,
        action="delete_block",
        block_id=moved["stable_id"],
        expected_version=2,
        operation_key="delete",
    )
    wiki.revert(
        target["id"], target_version=1, expected_version=3, operation_key="undo-merge"
    )
    assert not wiki.get_page(source["id"])["blocks"]
    assert all(
        b["markdown"] != "应尊重后续删除的内容"
        for p in wiki.list_pages(space_id=space)
        for b in p["blocks"]
    )
    wiki.manage_page(
        target["id"],
        space_id=space,
        action="archive",
        expected_version=4,
        operation_key="archive",
    )
    with pytest.raises(AssistantConflict, match="inactive"):
        wiki.revert(
            target["id"],
            target_version=1,
            expected_version=5,
            operation_key="bad-revert",
        )


def test_proposal_original_object_match_stale_and_success_replay(wiki_parts):
    _, _, wiki, space, msg, _, _ = wiki_parts
    left = create(wiki, space, msg, title="人工一", op="left")
    right = create(wiki, space, msg, title="人工二", op="right")
    for p, text in [(left, "观点一"), (right, "观点二")]:
        wiki.edit_block(
            p["id"],
            block_id=p["blocks"][0]["stable_id"],
            markdown=text,
            expected_version=1,
            operation_key="edit:" + p["id"],
        )
    proposal = wiki.merge_pages(
        left["id"],
        right["id"],
        space_id=space,
        source_version=2,
        target_version=2,
        operation_key="propose",
    )
    assert proposal["status"] == "pending"
    accepted = wiki.decide_proposal(
        proposal["proposal_id"], space_id=space, accept=True, operation_key="accept"
    )
    assert accepted["status"] == "accepted"
    assert (
        wiki.decide_proposal(
            proposal["proposal_id"], space_id=space, accept=True, operation_key="accept"
        )
        == accepted
    )


def test_model_budget_receipt_unknown_does_not_replay_and_no_transaction_call(
    wiki_parts,
):
    from shiliu.assistant.wiki import BudgetedStructuredProvider, ModelOutcomeUnknown

    db, store, _, _, _, _, _ = wiki_parts

    class Fake:
        calls = 0

        def generate_json(self, **kw):
            self.calls += 1
            with db.connect(read_only=True) as c:
                assert (
                    c.execute(
                        "SELECT count(*) AS n FROM pg_stat_activity WHERE application_name='shiliu-pg' AND state='idle in transaction'"
                    ).fetchone()["n"]
                    == 0
                )
            return {"response": "synthetic"}

    fake = Fake()
    provider = BudgetedStructuredProvider(store, None, fake)
    assert provider.generate_json(system="s", prompt="p") == {"response": "synthetic"}
    with pytest.raises(ModelOutcomeUnknown):
        provider.generate_json(system="s", prompt="p")
    assert fake.calls == 1
    with db.connect() as c:
        row = c.execute("SELECT * FROM model_dispatch_receipts").fetchone()
        assert row["status"] == "unknown" and row["settled_at"] is not None
        assert (
            c.execute(
                "SELECT requests_used FROM assistant_model_budget_days"
            ).fetchone()["requests_used"]
            == 1
        )


def test_source_reconcile_extract_integrate_real_pg_job_closure(wiki_parts):
    from shiliu.assistant.wiki_maintenance import WikiMaintenanceWorker

    db, store, wiki, space, msg, _, _ = wiki_parts
    vid, sid, ref, captured = add_source(wiki_parts)

    class Provider:
        calls = 0

        def generate_json(self, *, system, prompt, max_tokens=2400):
            self.calls += 1
            with db.connect(read_only=True) as c:
                assert not c.execute(
                    "SELECT pid FROM pg_stat_activity WHERE application_name='shiliu-pg' AND state='idle in transaction'"
                ).fetchone()
            if "source" in system.lower() and "wiki" not in system.lower():
                return {
                    "title": "PG合成来源",
                    "topics": ["PG事务"],
                    "claims": [
                        {"text": "事务提交前核验版本", "conditions": "当前版本"}
                    ],
                    "summary": "合成摘要",
                }
            return {
                "title": "PG事务",
                "page_type": "topic",
                "summary": "事务版本检查",
                "blocks": [
                    {
                        "heading": "提交前核验",
                        "markdown": "事务提交前核验版本",
                        "source_keys": ["s1"],
                        "source_refs": [captured.revision],
                    }
                ],
            }

    wiki.request_topic(
        space_id=space,
        topic="PG事务",
        source_refs=[ref],
        request_key=f"{space}:test",
        source_message_id=msg,
    )
    provider = Provider()
    worker = WikiMaintenanceWorker(wiki, owner="maintenance-worker", provider=provider)
    outcomes = []
    for _ in range(8):
        result = worker.run_once()
        if result is None:
            break
        outcomes.append(result)
        assert result["status"] == "completed", result
    assert {r["kind"] for r in outcomes} == {
        "source_reconcile",
        "source_extract",
        "wiki_integrate",
    }
    assert wiki.get_source_card(captured.revision)
    assert wiki.list_pages(space_id=space)
    with db.connect() as c:
        assert not c.execute(
            "SELECT id FROM assistant_jobs WHERE status='running'"
        ).fetchone()
        assert not c.execute(
            "SELECT active_job_id FROM scheduler_lanes WHERE active_job_id IS NOT NULL"
        ).fetchone()


def test_source_receipt_replay_and_equivalent_old_view_inside_merge(wiki_parts):
    db, _, wiki, space, msg, _, sources = wiki_parts
    source, vid, _, ref, old = source_page(wiki_parts)
    db.update_video(vid, title="等价正文的新标题")
    sources.snapshots.capture(vid)
    repeated = wiki.save_discussion(
        space_id=space,
        title=source["title"],
        purpose="保存来源证据",
        source_message_id=msg,
        operation_key="source:1",
        blocks=[
            {
                "role": "source",
                "heading": "来源事务",
                "markdown": "事务提交前必须核验来源版本。",
                "source_refs": [ref],
                "source_view": "transcript",
            }
        ],
    )
    assert repeated["id"] == source["id"] and repeated["blocks"]
    target = create(wiki, space, msg, title="合并目标", op="target")
    merged = wiki.merge_pages(
        source["id"],
        target["id"],
        space_id=space,
        source_version=1,
        target_version=1,
        operation_key="merge",
    )
    assert (
        merged["status"] == "merged" and len(wiki.get_page(target["id"])["blocks"]) == 2
    )


def test_zero_page_plan_ignore_restore_and_reject_preserve_real_results(wiki_parts):
    _, _, wiki, space, msg, _, _ = wiki_parts
    bad = [
        {
            "title": "无有效个人来源",
            "purpose": "尝试保存",
            "blocks": [
                {
                    "role": "personal",
                    "heading": "偏好",
                    "markdown": "非用户原话",
                    "user_quote": "伪造原话",
                    "user_message_id": "missing",
                }
            ],
        }
    ]
    plan = wiki.save_discussion_topics(
        space_id=space,
        topics=bad,
        omitted=[],
        source_message_id=msg,
        request_key="zero",
    )
    assert plan["status"] == "partial" and not wiki.list_pages(space_id=space)
    assert plan["results"]["0"]["status"] == "failed"
    ignored = wiki.manage_plan_item(
        plan["id"],
        space_id=space,
        item_index=0,
        action="ignore",
        expected_version=plan["version"],
        operation_key="ignore",
    )
    assert ignored["results"]["0"]["status"] == "ignored" and not wiki.list_pages(
        space_id=space
    )
    restored = wiki.manage_plan_item(
        plan["id"],
        space_id=space,
        item_index=0,
        action="restore",
        expected_version=ignored["version"],
        operation_key="restore",
    )
    assert restored["results"]["0"]["status"] != "completed"
    pending = wiki.propose_discussion(
        space_id=space,
        topics=topics(),
        omitted=[],
        source_message_id=msg,
        request_key="pending",
    )
    rejected = wiki.decide_discussion_plan(
        pending["id"],
        space_id=space,
        expected_version=1,
        accept=False,
        operation_key="reject",
    )
    assert rejected["status"] == "rejected" and not wiki.list_pages(space_id=space)


def test_p3_real_other_owner_workspace_cannot_read_or_replay_private_roots(
    wiki_parts, tmp_path
):
    from shiliu.storage.scope import ResourceContext
    from shiliu.db import Database

    db, _, wiki, space, msg, _, _ = wiki_parts
    page = create(wiki, space, msg)
    original = MemoryService(db).save_explicit(
        text="私人正文",
        subject_key="private",
        kind="context",
        scope_kind="user",
        scope_id=None,
        operation_key="same-key",
    )
    with db.connect() as c:
        c.execute(
            "INSERT INTO users(id,display_name,created_at) VALUES('synthetic_other','other',clock_timestamp())"
        )
        c.execute(
            "INSERT INTO workspaces(id,kind,owner_user_id,created_at) VALUES('personal:synthetic_other','personal','synthetic_other',clock_timestamp())"
        )
        c.execute(
            "INSERT INTO workspace_guards(workspace_id) VALUES('personal:synthetic_other')"
        )
        graph = SyntheticGraph(
            c,
            workspace="personal:synthetic_other",
            user="synthetic_other",
            suffix="_other",
            numeric_id=200,
        )
        other_space = graph.ensure("assistant_spaces")
        c.execute(
            "UPDATE assistant_spaces SET enabled=true WHERE id=%s", (other_space["id"],)
        )
    otherdb = Database(
        db.pg, ResourceContext("personal:synthetic_other", "synthetic_other")
    )
    memories = MemoryService(otherdb, principal_id="synthetic_other")
    with pytest.raises(KeyError):
        memories.get(original["id"])
    assert not memories.recall("私人正文", space_id=other_space["id"])
    independent = memories.save_explicit(
        text="另一个人的事实",
        subject_key="private",
        kind="context",
        scope_kind="user",
        scope_id=None,
        operation_key="same-key",
    )
    assert independent["id"] != original["id"]
    other_artifacts = ArtifactStore(tmp_path / "other-artifacts", otherdb)
    other_sources = CollectionSourceService(
        db=otherdb,
        artifacts=other_artifacts,
        snapshots=SourceSnapshotStore(otherdb, other_artifacts),
    )
    other = WikiService(
        db=otherdb,
        store=PgAssistantAccess(otherdb),
        sources=other_sources,
        principal_id="synthetic_other",
    )
    with pytest.raises(KeyError):
        other.get_page(page["id"])
    with pytest.raises(ValueError, match="scope"):
        memories.save_explicit(
            text="越权",
            subject_key="bad",
            kind="context",
            scope_kind="space",
            scope_id=space,
            operation_key="bad",
        )
    with pytest.raises(AssistantConflict, match="source_out_of_scope"):
        memories.save_explicit(
            text="越权消息",
            subject_key="bad",
            kind="context",
            scope_kind="user",
            scope_id=None,
            operation_key="bad-message",
            source_message_ids=[msg],
        )


def test_integration_unknown_response_cannot_be_resent_with_changed_basis(wiki_parts):
    from shiliu.assistant.wiki import BudgetedStructuredProvider, ModelOutcomeUnknown

    db, store, _, _, _, _, _ = wiki_parts
    with db.connect() as c:
        store.enqueue_job(
            c, kind="wiki_integrate", dedupe_key="unknown-basis", payload={}
        )
    job = store.claim_job(owner="integration-owner", kinds=("wiki_integrate",))

    class Fake:
        calls = 0

        def generate_json(self, **kw):
            self.calls += 1
            return {"synthetic": True}

    fake = Fake()
    provider = BudgetedStructuredProvider(store, None, fake, job=job)
    provider.generate_json(system="s", prompt="original page basis")
    with pytest.raises(ModelOutcomeUnknown):
        provider.generate_json(
            system="s", prompt="page changed before result was staged"
        )
    assert fake.calls == 1
