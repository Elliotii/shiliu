from __future__ import annotations

import asyncio
import json

import pytest

from shiliu.artifacts import ArtifactStore
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.snapshots import SourceSnapshotStore
from shiliu.assistant.sources import CollectionSourceService
from shiliu.assistant.store import AssistantConflict, AssistantRunStore
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.wiki import WikiService
from shiliu.db import Database
from shiliu.domain import FavoriteItem


class DeterministicWikiProvider:
    def __init__(self) -> None:
        self.card_calls = 0
        self.wiki_calls = 0

    def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400):
        if "SourceCard 提炼器" in system:
            self.card_calls += 1
            payload = json.loads(prompt[prompt.index("\n") + 1 :])
            title = payload["title"]
            return {
                "summary": f"{title} 的可核验摘要",
                "key_points": [{
                    "heading": title,
                    "markdown": f"{title}：显式约束应进入正式记忆。",
                    "applicability": "对话助手",
                    "assessment": "source_reported",
                }],
                "topics": ["助手记忆工程"],
                "limitations": ["只代表该来源"],
            }
        self.wiki_calls += 1
        payload = json.loads(prompt[prompt.index("\n") + 1 :])
        card = payload["source_card"]
        return {
            "title": "助手记忆工程",
            "page_type": "method",
            "summary": "把明确约束与来源知识分开管理。",
            "blocks": [{
                "heading": card["title"],
                "markdown": card["key_points"][0]["markdown"],
                "applicability": "对话助手",
                "assessment": "source_reported",
            }],
        }


class CallbackWikiProvider(DeterministicWikiProvider):
    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback
        self.fired = False

    def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400):
        if "Wiki 局部编译器" in system and not self.fired:
            self.fired = True
            self.callback()
        return super().generate_json(system=system, prompt=prompt, max_tokens=max_tokens)


def _services(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    artifacts = ArtifactStore(app_paths.videos_dir)
    sources = CollectionSourceService(
        db=db,
        artifacts=artifacts,
        snapshots=SourceSnapshotStore(db, artifacts, app_paths.assistant_content_dir),
    )
    store = AssistantRunStore(db)
    wiki = WikiService(db=db, store=store, sources=sources)
    return db, artifacts, sources, store, wiki


def _add_material(db, artifacts, source_id: int, *, bvid: str, title: str, text: str) -> int:
    db.record_source_snapshot(
        source_id,
        [FavoriteItem(
            bvid=bvid,
            title=title,
            uploader="公开作者",
            favorite_time=1_700_000_000,
        )],
        processing_profile="fast",
        authoritative=False,
    )
    video = db.get_video_by_source(bvid)
    assert video is not None
    path = artifacts.video_dir(bvid) / "stage-c-summary.md"
    artifacts.write_text(path, text)
    db.update_video(int(video["id"]), summary_path=str(path), status="completed")
    return int(video["id"])


def _drain_wiki_jobs(store, wiki, provider, *, limit: int = 30):
    outcomes = []
    for index in range(limit):
        job = store.claim_job(owner=f"test-worker-{index}")
        if job is None:
            break
        if job["kind"] == "source_reconcile":
            result = wiki.reconcile(job)
        elif job["kind"] == "source_extract":
            result = wiki.extract_source_card(job, provider=provider)
        elif job["kind"] == "wiki_integrate":
            result = wiki.integrate_source_card(job, provider=provider)
        else:
            result = {"ignored_in_test": job["kind"]}
        assert store.finish_job(
            job["id"], proposal=result,
            owner=job["lease_owner"], lease_epoch=int(job["lease_epoch"]),
        )
        outcomes.append((job["kind"], result))
    else:
        raise AssertionError("wiki job queue did not settle")
    return outcomes


def test_historical_tool_result_is_paged_and_invalidated_by_scope_change(app_paths) -> None:
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(
        folder_id=701, folder_title="阶段 C", history_policy="all"
    )
    video_id = _add_material(
        db, artifacts, source_id, bvid="BV1C23456789", title="长材料", text="内容" * 2000
    )
    space = store.create_space(name="C 历史读取", source_ids=[source_id])
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="继续读取之前的结果", request_id="req-c-history")
    stored = {
        "call_id": "large-result",
        "status": "ok",
        "summary": "长结果",
        "items": [{"content": "甲" * 3500}],
        "source_refs": [f"video:{video_id}"],
    }
    store.begin_tool_call(
        run["id"], ordinal=1, call_id="large-result", name="collection_read", arguments={}
    )
    store.finish_tool_call(run["id"], call_id="large-result", result=stored)
    registry = AssistantToolRegistry(
        sources=sources, memories=MemoryService(db), store=store, wiki=wiki
    )

    first = asyncio.run(registry.execute(
        name="run_read_result",
        arguments={
            "result_ref": f"run-result:{run['id']}:large-result",
            "max_characters": 1000,
        },
        call_id="history-page-1",
        run_context=store.run_context(run["id"]),
    ))
    assert first["status"] == "ok"
    assert first["items"][0]["total_items"] == 1
    second = asyncio.run(registry.execute(
        name="run_read_result",
        arguments={
            "result_ref": first["result_ref"],
            "item_index": 0,
            "field": "content",
            "start": 1000,
            "max_characters": 1000,
        },
        call_id="history-page-2",
        run_context=store.run_context(run["id"]),
    ))
    assert second["items"][0]["position"]["start"] == 1000

    changed = store.update_space(
        space["id"], expected_scope_version=space["scope_version"], source_ids=[]
    )
    denied = asyncio.run(registry.execute(
        name="run_read_result",
        arguments={"result_ref": first["result_ref"]},
        call_id="history-after-scope-change",
        run_context=store.run_context(run["id"]),
    ))
    assert changed["scope_version"] == 2
    assert denied["status"] == "unavailable"
    assert "范围" in denied["summary"]


def test_historical_memory_result_rejects_corrected_version(app_paths) -> None:
    db, _artifacts, sources, store, wiki = _services(app_paths)
    space = store.create_space(name="C 记忆版本")
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="回读记忆", request_id="req-c-memory-history")
    memories = MemoryService(db)
    memory = memories.save_explicit(
        text="项目使用 SQLite", subject_key="storage", kind="constraint",
        scope_kind="space", scope_id=space["id"], operation_key="memory-c-v1",
    )
    registry = AssistantToolRegistry(
        sources=sources, memories=memories, store=store, wiki=wiki
    )
    stored = asyncio.run(registry.execute(
        name="memory_search", arguments={"query": "SQLite"}, call_id="memory-result",
        run_context=store.run_context(run["id"]),
    ))
    assert stored["items"][0]["version"] == 1
    store.begin_tool_call(
        run["id"], ordinal=1, call_id="memory-result", name="memory_search", arguments={}
    )
    store.finish_tool_call(run["id"], call_id="memory-result", result=stored)

    memories.correct(
        memory["id"], text="项目使用 SQLite 3.46", expected_version=1,
        operation_key="memory-c-v2",
    )
    denied = asyncio.run(registry.execute(
        name="run_read_result",
        arguments={"result_ref": f"run-result:{run['id']}:memory-result"},
        call_id="read-memory-v1", run_context=store.run_context(run["id"]),
    ))
    assert denied["status"] == "unavailable"
    assert "重新查询" in denied["summary"]


def test_historical_wiki_and_indirect_page_revalidate_source_dependencies(app_paths) -> None:
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(
        folder_id=707, folder_title="C 历史 Wiki", history_policy="all"
    )
    video_id = _add_material(
        db, artifacts, source_id,
        bvid="BV1C2345678F", title="历史 Wiki 材料", text="来源移出后旧结果必须失效。",
    )
    space = store.create_space(name="C Wiki 回读", source_ids=[source_id])
    wiki.bootstrap_space(space["id"])
    _drain_wiki_jobs(store, wiki, DeterministicWikiProvider())
    page = wiki.list_pages(space_id=space["id"])[0]
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="回读 Wiki", request_id="req-c-wiki-history")
    registry = AssistantToolRegistry(
        sources=sources, memories=MemoryService(db), store=store, wiki=wiki
    )
    searched = asyncio.run(registry.execute(
        name="knowledge_search", arguments={"query": "记忆工程"},
        call_id="wiki-search", run_context=store.run_context(run["id"]),
    ))
    assert searched["source_refs"]
    assert searched["items"][0]["version"] == page["version"]
    store.begin_tool_call(
        run["id"], ordinal=1, call_id="wiki-search", name="knowledge_search", arguments={}
    )
    store.finish_tool_call(run["id"], call_id="wiki-search", result=searched)
    stored = asyncio.run(registry.execute(
        name="knowledge_read", arguments={"page_id": page["id"]},
        call_id="wiki-result", run_context=store.run_context(run["id"]),
    ))
    assert stored["source_refs"]
    store.begin_tool_call(
        run["id"], ordinal=2, call_id="wiki-result", name="knowledge_read", arguments={}
    )
    store.finish_tool_call(run["id"], call_id="wiki-result", result=stored)
    paged = asyncio.run(registry.execute(
        name="run_read_result",
        arguments={
            "result_ref": f"run-result:{run['id']}:wiki-result", "max_characters": 1000,
        },
        call_id="wiki-page", run_context=store.run_context(run["id"]),
    ))
    assert paged["dependency_refs"] == [f"run-result:{run['id']}:wiki-result"]
    # Match runtime persistence: it replaces the displayed result_ref, while the
    # dependency_refs field must retain the original result dependency.
    paged["result_ref"] = f"run-result:{run['id']}:wiki-page"
    store.begin_tool_call(
        run["id"], ordinal=3, call_id="wiki-page", name="run_read_result", arguments={}
    )
    store.finish_tool_call(run["id"], call_id="wiki-page", result=paged)

    with db.connect() as connection:
        connection.execute(
            "UPDATE video_source_memberships SET removed_at=? "
            "WHERE source_id=? AND video_id=?",
            ("2026-09-21T12:00:00+00:00", source_id, video_id),
        )
    assert store.get_space(space["id"])["scope_version"] == 1
    for result_ref in (
        f"run-result:{run['id']}:wiki-search",
        f"run-result:{run['id']}:wiki-result",
        f"run-result:{run['id']}:wiki-page",
    ):
        denied = asyncio.run(registry.execute(
            name="run_read_result", arguments={"result_ref": result_ref},
            call_id=f"denied-{result_ref.rsplit(':', 1)[-1]}",
            run_context=store.run_context(run["id"]),
        ))
        assert denied["status"] == "unavailable"
        assert "重新查询" in denied["summary"]


@pytest.mark.parametrize("stale_kind", ["scope", "source_revision", "lease"])
def test_wiki_commit_rejects_stale_scope_revision_or_lease(app_paths, stale_kind) -> None:
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(
        folder_id=708, folder_title=f"C 提交围栏 {stale_kind}", history_policy="all"
    )
    video_id = _add_material(
        db, artifacts, source_id,
        bvid="BV1C2345678G", title="提交围栏", text="迟到任务不得提交。",
    )
    space = store.create_space(name=f"C 围栏 {stale_kind}", source_ids=[source_id])
    wiki.bootstrap_space(space["id"])

    reconcile = store.claim_job(owner="fence-reconcile")
    assert reconcile and reconcile["kind"] == "source_reconcile"
    assert store.finish_job(
        reconcile["id"], proposal=wiki.reconcile(reconcile),
        owner=reconcile["lease_owner"], lease_epoch=int(reconcile["lease_epoch"]),
    )
    extraction = store.claim_job(owner="fence-extract")
    assert extraction and extraction["kind"] == "source_extract"
    extraction_result = wiki.extract_source_card(
        extraction, provider=DeterministicWikiProvider()
    )
    assert store.finish_job(
        extraction["id"], proposal=extraction_result,
        owner=extraction["lease_owner"], lease_epoch=int(extraction["lease_epoch"]),
    )
    integration = store.claim_job(owner="fence-integrate")
    assert integration and integration["kind"] == "wiki_integrate"

    def make_stale() -> None:
        if stale_kind == "scope":
            store.update_space(
                space["id"], expected_scope_version=space["scope_version"], source_ids=[]
            )
        elif stale_kind == "source_revision":
            path = artifacts.video_dir("BV1C2345678G") / "stage-c-summary.md"
            artifacts.write_text(path, "新版材料已替换旧版。")
            db.update_video(video_id, summary_path=str(path), status="completed")
            sources.snapshots.capture(video_id)
        else:
            with db.connect() as connection:
                connection.execute(
                    "UPDATE assistant_jobs SET lease_owner='replacement-worker', "
                    "lease_epoch=lease_epoch+1 WHERE id=?",
                    (integration["id"],),
                )

    result = wiki.integrate_source_card(
        integration, provider=CallbackWikiProvider(make_stale)
    )
    assert result == {
        "superseded": True,
        "reason": {
            "scope": "wiki_scope_changed",
            "source_revision": "source_revision_changed",
            "lease": "wiki_job_lease_lost",
        }[stale_kind],
    }
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM assistant_wiki_pages").fetchone()[0] == 0


def test_bootstrap_selects_latest_real_favorite_time_not_video_id(app_paths) -> None:
    db, _artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(
        folder_id=701, folder_title="真实收藏顺序", history_policy="all"
    )
    db.record_source_snapshot(
        source_id,
        [
            FavoriteItem(
                bvid="BV1C2345678Z", title="先入库但较新收藏", uploader="公开作者",
                favorite_time=300,
            ),
            FavoriteItem(
                bvid="BV1C2345678Y", title="后入库但较早收藏", uploader="公开作者",
                favorite_time=100,
            ),
        ],
        processing_profile="fast",
        authoritative=True,
        remote_total=2,
    )
    newest = db.get_video_by_source("BV1C2345678Z")
    assert newest is not None
    space = store.create_space(name="近期真实收藏", source_ids=[source_id])

    queued = wiki.bootstrap_space(space["id"], limit=1)

    assert queued["video_ids"] == [newest["id"]]


def test_related_page_matching_rejects_generic_ai_overlap_but_keeps_agent_memory() -> None:
    unrelated, _score = WikiService._topic_relation(
        ["Transformer", "mini transformer 实现", "PyTorch"],
        page_title="AI辅助编程",
        page_aliases=["程序员工作流", "代码审查"],
    )
    related, score = WikiService._topic_relation(
        ["Agent 记忆架构", "长期记忆"],
        page_title="Agent记忆系统",
        page_aliases=["Agent 记忆系统", "记忆提取"],
    )

    assert unrelated is False
    assert related is True and score > 0


def test_two_sources_increment_one_page_preserve_manual_edit_and_hide_on_scope_change(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(
        folder_id=702, folder_title="阶段 C Wiki", history_policy="all"
    )
    first_video = _add_material(
        db, artifacts, source_id,
        bvid="BV1C2345678A", title="记忆系统实践一", text="明确约束进入 SQLite，向量索引只是派生层。",
    )
    space = store.create_space(name="C Wiki", source_ids=[source_id])
    provider = DeterministicWikiProvider()

    assert wiki.bootstrap_space(space["id"], limit=10)["queued"] == 1
    first_outcomes = _drain_wiki_jobs(store, wiki, provider)
    pages = wiki.list_pages(space_id=space["id"])
    assert {kind for kind, _ in first_outcomes} >= {
        "source_reconcile", "source_extract", "wiki_integrate"
    }
    assert len(pages) == 1 and len(pages[0]["blocks"]) == 1
    page = pages[0]
    locked = wiki.edit_block(
        page["id"], block_id=page["blocks"][0]["stable_id"],
        markdown="人工确认：正式记忆以 SQLite 为准。",
        expected_version=page["version"], operation_key="edit-c-1",
    )
    with pytest.raises(AssistantConflict, match="wiki_version_conflict"):
        wiki.edit_block(
            page["id"], block_id=page["blocks"][0]["stable_id"], markdown="迟到编辑",
            expected_version=page["version"], operation_key="edit-c-stale",
        )

    second_video = _add_material(
        db, artifacts, source_id,
        bvid="BV1C2345678B", title="记忆系统实践二", text="纠正和遗忘必须让旧向量立即失效。",
    )
    wiki.bootstrap_space(space["id"], limit=10)
    outcomes = _drain_wiki_jobs(store, wiki, provider)
    updated = wiki.get_page(page["id"], space_id=space["id"])
    assert any(kind == "wiki_integrate" for kind, _ in outcomes)
    assert updated["version"] > locked["version"]
    assert len(updated["blocks"]) == 2
    assert updated["blocks"][0]["markdown"] == "人工确认：正式记忆以 SQLite 为准。"
    assert updated["blocks"][0]["manual_lock"] is True
    assert {dep["video_id"] for dep in _dependencies(db, page["id"])} == {
        first_video, second_video
    }
    restored = wiki.revert(
        page["id"], target_version=locked["version"],
        expected_version=updated["version"], operation_key="revert-c-1",
    )
    assert restored["version"] == updated["version"] + 1
    assert restored["blocks"][0]["markdown"] == "人工确认：正式记忆以 SQLite 为准。"
    assert restored["blocks"][0]["manual_lock"] is True

    changed = store.update_space(
        space["id"], expected_scope_version=space["scope_version"], source_ids=[]
    )
    assert changed["scope_version"] == 2
    assert wiki.list_pages(space_id=space["id"]) == []
    assert wiki.get_page(page["id"], space_id=space["id"])["blocks"] == []


def test_membership_only_revision_reuses_card_and_job_survives_lease_expiry(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_one = db.create_favorite_source(folder_id=703, folder_title="来源一", history_policy="all")
    video_id = _add_material(
        db, artifacts, source_one,
        bvid="BV1C2345678C", title="可恢复材料", text="持久队列通过租约恢复。",
    )
    space = store.create_space(name="C 恢复", source_ids=[source_one])
    provider = DeterministicWikiProvider()
    wiki.bootstrap_space(space["id"])

    first_job = store.claim_job(owner="crashed-worker", lease_seconds=1)
    assert first_job and first_job["kind"] == "source_reconcile"
    with db.connect() as connection:
        connection.execute(
            "UPDATE assistant_jobs SET lease_until='2000-01-01T00:00:00+00:00' WHERE id=?",
            (first_job["id"],),
        )
    recovered = store.claim_job(owner="restart-worker")
    assert recovered and recovered["id"] == first_job["id"]
    result = wiki.reconcile(recovered)
    assert store.finish_job(
        recovered["id"], proposal=result,
        owner=recovered["lease_owner"], lease_epoch=int(recovered["lease_epoch"]),
    )
    _drain_wiki_jobs(store, wiki, provider)
    assert provider.card_calls == 1
    page = wiki.list_pages(space_id=space["id"])[0]

    source_two = db.create_favorite_source(folder_id=704, folder_title="来源二", history_policy="all")
    db.record_source_snapshot(
        source_two,
        [FavoriteItem(
            bvid="BV1C2345678C", title="可恢复材料", uploader="公开作者",
            favorite_time=1_700_000_001,
        )],
        processing_profile="fast",
        authoritative=False,
    )
    _drain_wiki_jobs(store, wiki, provider)
    same_page = wiki.get_page(page["id"], space_id=space["id"])
    assert provider.card_calls == 1
    assert same_page["version"] == page["version"]
    assert db.get_video(video_id) is not None


def test_long_material_continues_in_persistent_batches(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(
        folder_id=705, folder_title="长材料", history_policy="all"
    )
    _add_material(
        db, artifacts, source_id,
        bvid="BV1C2345678D", title="长视频整理", text="持久批次材料。" * 9000,
    )
    space = store.create_space(name="C 长材料", source_ids=[source_id])
    provider = DeterministicWikiProvider()
    wiki.bootstrap_space(space["id"])
    outcomes = _drain_wiki_jobs(store, wiki, provider)

    extraction_jobs = [result for kind, result in outcomes if kind == "source_extract"]
    assert len(extraction_jobs) >= 2
    assert extraction_jobs[0]["partial"] is True
    assert provider.card_calls > 4
    with db.connect() as connection:
        batch_count = connection.execute(
            "SELECT COUNT(*) FROM assistant_source_card_batches"
        ).fetchone()[0]
    assert batch_count == provider.card_calls
    assert len(wiki.list_pages(space_id=space["id"])) == 1


def test_new_revision_amends_auto_block_instead_of_stacking_duplicates(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(
        folder_id=706, folder_title="修订材料", history_policy="all"
    )
    video_id = _add_material(
        db, artifacts, source_id,
        bvid="BV1C2345678E", title="会更新的材料", text="第一版：使用持久队列。",
    )
    space = store.create_space(name="C 自动修订", source_ids=[source_id])
    provider = DeterministicWikiProvider()
    wiki.bootstrap_space(space["id"])
    _drain_wiki_jobs(store, wiki, provider)
    before = wiki.list_pages(space_id=space["id"])[0]
    old_block_id = before["blocks"][0]["stable_id"]

    path = artifacts.video_dir("BV1C2345678E") / "stage-c-summary.md"
    artifacts.write_text(path, "第二版：持久队列还需要租约围栏。")
    db.update_video(video_id, summary_path=str(path), status="completed")
    wiki.bootstrap_space(space["id"], limit=10)
    _drain_wiki_jobs(store, wiki, provider)
    after = wiki.get_page(before["id"], space_id=space["id"])

    assert after["version"] == before["version"] + 1
    assert len(after["blocks"]) == 1
    assert after["blocks"][0]["stable_id"] != old_block_id


def _dependencies(db: Database, page_id: str):
    with db.connect() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT video_id, block_id FROM assistant_wiki_dependencies WHERE page_id=?",
            (page_id,),
        ).fetchall()]
