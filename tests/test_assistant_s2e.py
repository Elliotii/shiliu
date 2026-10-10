from __future__ import annotations

import json
import asyncio
import pytest

from shiliu.assistant.memory import MemoryService
from shiliu.assistant.context import ContextComposer
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.store import AssistantConflict
from shiliu.assistant.wiki import WikiService
from test_assistant_s2d import TopicProvider, CapturingSplitProvider, _wiki_api_request
from shiliu.assistant.api import get_wiki, WikiProposalDecision, decide_wiki_proposal
from test_assistant_stage_c import _add_material, _drain_wiki_jobs, _services
from shiliu.domain import FavoriteItem


class LocalProvider(TopicProvider):
    def __init__(self) -> None:
        self.catalog_sizes: list[int] = []
        self.wiki_calls = 0

    def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400):
        if "SourceCard 提炼器" in system:
            return super().generate_json(system=system, prompt=prompt, max_tokens=max_tokens)
        payload = json.loads(prompt[prompt.index("\n") + 1:])
        self.catalog_sizes.append(len(payload["source_catalog"]))
        self.wiki_calls += 1
        card = payload["source_card"]
        return {
            "title": payload["topic"], "page_type": "comparison",
            "summary": "比较每份材料的适用条件。",
            "operation": "add_block" if payload.get("existing_page") else None,
            "blocks": [{
                "heading": f"条件 {self.wiki_calls}",
                "markdown": card["summary"],
                "applicability": "只在材料所述条件下",
                "assessment": "source_reported", "source_keys": ["s1"],
            }],
        }


def test_seventh_material_adds_local_content_without_dropping_six(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=991, folder_title="E", history_policy="all")
    ids = [_add_material(
        db, artifacts, source_id, bvid=f"BV1E2345678{index}",
        title=f"材料 {index}", text=f"适用条件 {index}；独特结论 {index}。",
    ) for index in range(1, 8)]
    space = store.create_space(name="E 七来源", source_ids=[source_id])
    provider = LocalProvider()
    for index, video_id in enumerate(ids, 1):
        wiki.request_topic(
            space_id=space["id"], topic="共同主题", source_refs=[f"video:{video_id}"],
            request_key=f"e:add:{index}",
        )
        results = _drain_wiki_jobs(store, wiki, provider)
        assert any(kind == "wiki_integrate" and result.get("page_id")
                   for kind, result in results)
    page = wiki.list_pages(space_id=space["id"])[0]
    assert len(page["blocks"]) == 7
    assert all(f"独特结论 {index}" in json.dumps(page, ensure_ascii=False)
               for index in range(1, 8))
    assert len(page["materials"]) == 7
    assert "比较每份材料的适用条件" in page["summary"]
    assert "新增对照" in page["summary"]
    assert {item["relation"] for item in page["materials"]} == {"supports_block"}
    assert max(provider.catalog_sizes) <= 6
    before_version = page["version"]
    before_calls = provider.wiki_calls
    wiki.request_topic(space_id=space["id"], topic="共同主题",
                       source_refs=[f"video:{ids[-1]}"], request_key="e:repeat")
    _drain_wiki_jobs(store, wiki, provider)
    assert wiki.get_page(page["id"])["version"] == before_version
    assert provider.wiki_calls == before_calls


def test_memory_derived_personal_content_hides_after_correction_without_hiding_independent_note(app_paths) -> None:
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=992, folder_title="E memory", history_policy="all")
    video_id = _add_material(db, artifacts, source_id, bvid="BV1E23456788",
                             title="原材料", text="原材料只陈述方案的适用条件。")
    space = store.create_space(name="E 个人依赖", source_ids=[source_id])
    wiki.request_topic(space_id=space["id"], topic="共同主题",
                       source_refs=[f"video:{video_id}"], request_key="e:memory:topic")
    _drain_wiki_jobs(store, wiki, LocalProvider())
    page = wiki.list_pages(space_id=space["id"])[0]
    page = wiki.add_personal_note(page["id"], space_id=space["id"],
        text="独立笔记：先看适用条件。", expected_version=page["version"],
        operation_key="e:independent")
    memories = MemoryService(db)
    memory = memories.save_explicit(text="我的旧判断：优先采用甲。", subject_key="方案选择",
        kind="decision", scope_kind="space", scope_id=space["id"], operation_key="e:save")
    page = wiki.add_personal_note(page["id"], space_id=space["id"],
        text="派生判断：优先采用甲。", expected_version=page["version"],
        operation_key="e:derived", memory_id=memory["id"], memory_version=memory["version"])
    registry = AssistantToolRegistry(sources=sources, memories=memories, store=store, wiki=wiki)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="读主题", request_id="e:read")
    read = asyncio.run(registry.execute(name="knowledge_read",
        arguments={"page_id": page["id"]}, call_id="before", run_context=store.run_context(run["id"])))
    assert read["status"] == "ok"
    assert f"memory:{memory['id']}:{memory['version']}" in read["dependency_refs"]
    store.begin_tool_call(run["id"], ordinal=1, call_id="before", name="knowledge_read",
                          arguments={"page_id": page["id"]})
    store.finish_tool_call(run["id"], call_id="before", result=read)
    store.save_assistant_tool_message(run["id"], content="", provider_payload={"tool_calls": [{
        "id": "before", "type": "function",
        "function": {"name": "knowledge_read", "arguments": json.dumps({"page_id": page["id"]})},
    }]})
    store.save_tool_result_message(run["id"], content=json.dumps(read, ensure_ascii=False),
                                   provider_payload={"tool_call_id": "before", "name": "knowledge_read"})
    search = asyncio.run(registry.execute(name="knowledge_search",
        arguments={"query": "派生判断"}, call_id="search-before",
        run_context=store.run_context(run["id"])))
    assert search["status"] == "ok"
    store.begin_tool_call(run["id"], ordinal=2, call_id="search-before",
                          name="knowledge_search", arguments={"query": "派生判断"})
    store.finish_tool_call(run["id"], call_id="search-before", result=search)
    memories.correct(memory["id"], text="我的新判断：先核对乙。",
                     expected_version=memory["version"], operation_key="e:correct")
    current = wiki.get_page(page["id"])
    text = json.dumps(current, ensure_ascii=False)
    assert "独立笔记：先看适用条件" in text
    assert "原材料只陈述方案" in text
    assert "派生判断：优先采用甲" not in text
    assert not registry.dependency_refs_valid(
        [f"run-result:{run['id']}:before"], space["id"], thread["id"], space["scope_version"]
    )
    assert not registry.dependency_refs_valid(
        [f"run-result:{run['id']}:search-before"], space["id"], thread["id"], space["scope_version"]
    )
    old = asyncio.run(registry.execute(name="run_read_result",
        arguments={"result_ref": f"run-result:{run['id']}:before"},
        call_id="after", run_context=store.run_context(run["id"])))
    assert old["status"] == "unavailable"
    fresh = asyncio.run(registry.execute(name="knowledge_read",
        arguments={"page_id": page["id"], "mode": "relevant", "query": "独立笔记 适用条件"},
        call_id="fresh", run_context=store.run_context(run["id"])))
    assert "派生判断：优先采用甲" not in json.dumps(fresh, ensure_ascii=False)
    store.cancel_run(run["id"])
    continuation = store.create_run(thread["id"], text="继续核对主题", request_id="e:continue")
    messages, _tokens = ContextComposer(
        memories, dependency_ref_validator=registry.dependency_refs_valid,
    ).compose(store.run_context(continuation["id"]))
    provider_input = json.dumps(messages, ensure_ascii=False)
    assert "派生判断：优先采用甲" not in provider_input
    assert "我的新判断：先核对乙" in provider_input
    assert "独立笔记：先看适用条件" in json.dumps(fresh, ensure_ascii=False)
    later = wiki.add_personal_note(page["id"], space_id=space["id"],
        text="纠正之后的独立补充", expected_version=current["version"],
        operation_key="e:after-correction")
    restored = wiki.revert(page["id"], target_version=page["version"],
                           expected_version=later["version"], operation_key="e:old-undo")
    restored_text = json.dumps(restored, ensure_ascii=False)
    assert "派生判断：优先采用甲" not in restored_text
    assert "独立笔记：先看适用条件" in restored_text


def test_merge_conflict_rejection_dedup_and_compensating_undo_preserves_later_note(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=993, folder_title="E merge", history_policy="all")
    first = _add_material(db, artifacts, source_id, bvid="BV1E23456789",
                          title="材料甲", text="条件甲说明先核对。")
    second = _add_material(db, artifacts, source_id, bvid="BV1E2345678A",
                           title="材料乙", text="条件乙说明再比较。")
    space = store.create_space(name="E 合并", source_ids=[source_id])
    for topic, video_id in (("主题甲", first), ("主题乙", second)):
        wiki.request_topic(space_id=space["id"], topic=topic,
                           source_refs=[f"video:{video_id}"], request_key=f"e:merge:{topic}")
        _drain_wiki_jobs(store, wiki, LocalProvider())
    pages = {page["title"]: page for page in wiki.list_pages(space_id=space["id"])}
    target = wiki.add_personal_note(pages["主题甲"]["id"], space_id=space["id"],
        text="人工判断甲", expected_version=pages["主题甲"]["version"], operation_key="e:manual:a")
    source = wiki.add_personal_note(pages["主题乙"]["id"], space_id=space["id"],
        text="人工判断乙", expected_version=pages["主题乙"]["version"], operation_key="e:manual:b")
    held = wiki.merge_pages(source["id"], target["id"], space_id=space["id"],
        source_version=source["version"], target_version=target["version"], operation_key="e:merge:held")
    assert held["status"] == "pending"
    assert wiki.decide_proposal(held["proposal_id"], accept=False,
                                operation_key="e:merge:reject")["status"] == "rejected"
    again = wiki.merge_pages(source["id"], target["id"], space_id=space["id"],
        source_version=source["version"], target_version=target["version"], operation_key="e:merge:retry")
    assert again["status"] == "rejected" and again["proposal_id"] == held["proposal_id"]
    # A fresh explicit decision can merge the same pair while preserving both judgments.
    merged = wiki.merge_pages(source["id"], target["id"], space_id=space["id"],
        source_version=source["version"], target_version=target["version"],
        operation_key="e:merge:accept", accept_conflict=True)
    assert merged["status"] == "merged"
    current = wiki.get_page(target["id"])
    assert "人工判断甲" in json.dumps(current, ensure_ascii=False)
    assert "人工判断乙" in json.dumps(current, ensure_ascii=False)
    assert wiki.get_page(source["id"])["redirected_from"] == source["id"]
    assert len(wiki.history_source_refs(target["id"], space_id=space["id"])) == 2
    later = wiki.add_personal_note(target["id"], space_id=space["id"],
        text="合并之后新增的独立笔记", expected_version=current["version"],
        operation_key="e:merge:later")
    restored = wiki.revert(target["id"], target_version=target["version"],
                           expected_version=later["version"], operation_key="e:merge:undo")
    restored_text = json.dumps(restored, ensure_ascii=False)
    assert "合并之后新增的独立笔记" in restored_text
    assert "人工判断甲" in restored_text
    assert "人工判断乙" not in restored_text
    assert "人工判断乙" in json.dumps(wiki.get_page(source["id"]), ensure_ascii=False)
    assert len(wiki.history_source_refs(target["id"], space_id=space["id"])) == 1


def test_membership_only_change_rebinds_existing_page_without_model_call(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_one = db.create_favorite_source(folder_id=994, folder_title="来源一", history_policy="all")
    video_id = _add_material(db, artifacts, source_one, bvid="BV1E2345678B",
                             title="等价材料", text="同一正文，收藏位置可以改变。")
    space = store.create_space(name="E 等价重绑", source_ids=[source_one])
    provider = LocalProvider()
    wiki.request_topic(space_id=space["id"], topic="共同主题",
                       source_refs=[f"video:{video_id}"], request_key="e:rebind:first")
    _drain_wiki_jobs(store, wiki, provider)
    page = wiki.list_pages(space_id=space["id"])[0]
    old_ref = wiki.history_source_refs(page["id"], space_id=space["id"])[0]
    calls = provider.wiki_calls
    source_two = db.create_favorite_source(folder_id=995, folder_title="来源二", history_policy="all")
    db.record_source_snapshot(source_two, [FavoriteItem(
        bvid="BV1E2345678B", title="等价材料", uploader="公开作者",
        favorite_time=1_700_000_001,
    )], processing_profile="fast", authoritative=False)
    wiki.request_topic(space_id=space["id"], topic="共同主题",
                       source_refs=[f"video:{video_id}"], request_key="e:rebind:second")
    outcomes = _drain_wiki_jobs(store, wiki, provider)
    assert any(kind == "wiki_integrate" and result.get("no_model_call")
               for kind, result in outcomes)
    assert provider.wiki_calls == calls
    after = wiki.get_page(page["id"])
    assert after["version"] == page["version"] + 1
    assert after["availability"] == "full"
    assert wiki.history_source_refs(page["id"], space_id=space["id"])[0] != old_ref


def test_automatic_scope_loss_rebuilds_mixed_block_from_remaining_source(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=996, folder_title="E repair", history_policy="all")
    first = _add_material(db, artifacts, source_id, bvid="BV1E2345678C",
                          title="来源甲", text="甲条件：只在离线环境使用。")
    second = _add_material(db, artifacts, source_id, bvid="BV1E2345678D",
                           title="来源乙", text="乙条件：在线环境先做实时核对。")
    space = store.create_space(name="E 自动修复", source_ids=[source_id],
                               maintenance_mode="automatic")
    wiki.bootstrap_space(space["id"], limit=2)
    _drain_wiki_jobs(store, wiki, TopicProvider())
    page = wiki.list_pages(space_id=space["id"])[0]
    assert any(len(block["source_refs"]) == 2 for block in page["blocks"])
    db.set_archived(first, True)
    hidden = wiki.get_page(page["id"])
    assert "甲条件" not in json.dumps(hidden, ensure_ascii=False)

    class RepairProvider(LocalProvider):
        def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400):
            if "SourceCard 提炼器" in system:
                return super().generate_json(system=system, prompt=prompt, max_tokens=max_tokens)
            payload = json.loads(prompt[prompt.index("\n") + 1:])
            if payload.get("repair_requested"):
                invalid = payload["invalid_block_directory"]
                assert invalid and "乙条件" in payload["source_card"]["summary"]
                return {"title": payload["topic"], "page_type": "comparison",
                        "operation": "revise_block", "target_block_id": invalid[0]["id"],
                        "blocks": [{"heading": "在线条件", "markdown": "乙条件：在线环境先做实时核对。",
                                    "assessment": "source_reported", "source_keys": ["s1"]}]}
            return super().generate_json(system=system, prompt=prompt, max_tokens=max_tokens)

    outcomes = _drain_wiki_jobs(store, wiki, RepairProvider())
    assert any(kind == "wiki_integrate" and result.get("page_id") == page["id"]
               for kind, result in outcomes)
    repaired = wiki.get_page(page["id"])
    assert repaired["availability"] == "full"
    assert "乙条件" in json.dumps(repaired, ensure_ascii=False)
    assert "甲条件" not in json.dumps(repaired, ensure_ascii=False)
    assert {int(ref.split(":", 2)[1]) for ref in
            wiki.history_source_refs(page["id"], space_id=space["id"])} == {second}


def test_publication_time_only_refresh_reuses_body_and_rebinds_provenance(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=997, folder_title="E time", history_policy="all")
    video_id = _add_material(db, artifacts, source_id, bvid="BV1E2345678E",
                             title="时间材料", text="原材料只讨论处理条件，没有日期主张。")
    space = store.create_space(name="E 时间重绑", source_ids=[source_id])
    provider = LocalProvider()
    wiki.request_topic(space_id=space["id"], topic="共同主题",
                       source_refs=[f"video:{video_id}"], request_key="e:time:first")
    _drain_wiki_jobs(store, wiki, provider)
    page = wiki.list_pages(space_id=space["id"])[0]
    calls = provider.wiki_calls
    db.update_video(video_id, published_at=1_800_000_000)
    wiki.request_topic(space_id=space["id"], topic="共同主题",
                       source_refs=[f"video:{video_id}"], request_key="e:time:second")
    results = _drain_wiki_jobs(store, wiki, provider)
    assert any(kind == "source_extract" and result.get("reused_time_only")
               for kind, result in results)
    assert any(kind == "wiki_integrate" and result.get("no_model_call")
               for kind, result in results)
    assert provider.wiki_calls == calls
    assert wiki.get_page(page["id"])["availability"] == "full"


def test_related_material_can_be_associated_without_fake_block_support(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=998, folder_title="E association", history_policy="all")
    first = _add_material(db, artifacts, source_id, bvid="BV1E2345678F",
                          title="核心材料", text="直接解释主题问题。")
    related = _add_material(db, artifacts, source_id, bvid="BV1E2345678G",
                            title="相关背景", text="只讲相邻话题，没有证据支持主题结论。")
    space = store.create_space(name="E 关联", source_ids=[source_id])
    provider = LocalProvider()
    wiki.request_topic(space_id=space["id"], topic="共同主题",
                       source_refs=[f"video:{first}"], request_key="e:assoc:first")
    _drain_wiki_jobs(store, wiki, provider)
    initial = wiki.list_pages(space_id=space["id"])[0]

    class AssociateProvider(LocalProvider):
        def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400):
            if "SourceCard 提炼器" in system:
                return super().generate_json(system=system, prompt=prompt, max_tokens=max_tokens)
            self.wiki_calls += 1
            payload = json.loads(prompt[prompt.index("\n") + 1:])
            return {"operation": "associate", "title": payload["topic"],
                    "summary": "错误的无依据导读", "blocks": []}

    associate = AssociateProvider()
    wiki.request_topic(space_id=space["id"], topic="共同主题",
                       source_refs=[f"video:{related}"], request_key="e:assoc:related")
    _drain_wiki_jobs(store, wiki, associate)
    page = wiki.get_page(initial["id"])
    assert page["version"] == initial["version"] + 1
    assert len(page["blocks"]) == len(initial["blocks"])
    assert page["summary"] == initial["summary"]
    assert {item["video_id"]: item["relation"] for item in page["materials"]}[related] == "associated"
    assert {int(ref.split(":", 2)[1]) for ref in wiki.history_source_refs(
        page["id"], space_id=space["id"])} == {first}
    wiki.request_topic(space_id=space["id"], topic="共同主题",
                       source_refs=[f"video:{related}"], request_key="e:assoc:repeat")
    _drain_wiki_jobs(store, wiki, associate)
    assert wiki.get_page(page["id"])["version"] == page["version"]
    assert associate.wiki_calls == 1


def test_pending_merge_cannot_reveal_or_accept_forgotten_personal_stance(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=999, folder_title="E pending", history_policy="all")
    a = _add_material(db, artifacts, source_id, bvid="BV1E2345678H", title="甲", text="材料甲。")
    b = _add_material(db, artifacts, source_id, bvid="BV1E2345678I", title="乙", text="材料乙。")
    space = store.create_space(name="E 待提案", source_ids=[source_id])
    for topic, video in (("主题甲", a), ("主题乙", b)):
        wiki.request_topic(space_id=space["id"], topic=topic,
                           source_refs=[f"video:{video}"], request_key=f"e:pending:{topic}")
        _drain_wiki_jobs(store, wiki, LocalProvider())
    pages = {page["title"]: page for page in wiki.list_pages(space_id=space["id"])}
    memories = MemoryService(db)
    memory = memories.save_explicit(text="旧个人判断：应永久保留甲。", subject_key="待提案判断",
        kind="decision", scope_kind="space", scope_id=space["id"], operation_key="e:pending:save")
    source = wiki.add_personal_note(pages["主题乙"]["id"], space_id=space["id"],
        text="旧个人判断：应永久保留甲。", expected_version=pages["主题乙"]["version"],
        operation_key="e:pending:derived", memory_id=memory["id"], memory_version=memory["version"])
    target = wiki.add_personal_note(pages["主题甲"]["id"], space_id=space["id"],
        text="独立判断：先核对。", expected_version=pages["主题甲"]["version"],
        operation_key="e:pending:independent")
    proposal = wiki.merge_pages(source["id"], target["id"], space_id=space["id"],
        source_version=source["version"], target_version=target["version"],
        operation_key="e:pending:merge")
    assert proposal["status"] == "pending"
    assert "旧个人判断" in json.dumps(wiki.list_proposals(space_id=space["id"]), ensure_ascii=False)
    memories.forget(memory["id"], expected_version=memory["version"],
                    operation_key="e:pending:forget")
    assert wiki.list_proposals(space_id=space["id"]) == []
    with pytest.raises(AssistantConflict, match="wiki_proposal_stale"):
        wiki.decide_proposal(proposal["proposal_id"], accept=True,
                             operation_key="e:pending:accept-stale")
    current_source = wiki.get_page(source["id"])
    assert "旧个人判断" not in json.dumps(current_source, ensure_ascii=False)
    assert "部分依赖个人内容已失效" in current_source["summary"]
    assert len([block for block in current_source["blocks"] if block.get("source_refs")]) == 1
    assert "独立判断：先核对" in json.dumps(wiki.get_page(target["id"]), ensure_ascii=False)


def test_automatic_space_narrowing_enqueues_bounded_page_repair(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=1000, folder_title="E scope", history_policy="all")
    first = _add_material(db, artifacts, source_id, bvid="BV1E2345678J", title="甲", text="甲条件。")
    second = _add_material(db, artifacts, source_id, bvid="BV1E2345678K", title="乙", text="乙条件。")
    space = store.create_space(name="E 收窄", source_ids=[source_id], maintenance_mode="automatic")
    wiki.bootstrap_space(space["id"], limit=2)
    _drain_wiki_jobs(store, wiki, TopicProvider())
    page = wiki.list_pages(space_id=space["id"])[0]
    updated = store.update_space(space["id"], expected_scope_version=space["scope_version"],
                                 video_ids=[second])
    assert updated["scope_version"] == space["scope_version"] + 1
    assert wiki.get_page(page["id"])["availability"] == "partial"

    class ScopeRepairProvider(LocalProvider):
        def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400):
            if "SourceCard 提炼器" in system:
                return super().generate_json(system=system, prompt=prompt, max_tokens=max_tokens)
            payload = json.loads(prompt[prompt.index("\n") + 1:])
            assert payload["repair_requested"]
            return {"operation": "revise_block", "title": payload["topic"],
                    "target_block_id": payload["invalid_block_directory"][0]["id"],
                    "blocks": [{"heading": "当前范围的乙条件", "markdown": "乙条件。",
                                "source_keys": ["s1"]}]}

    results = _drain_wiki_jobs(store, wiki, ScopeRepairProvider())
    assert any(kind == "wiki_integrate" and result.get("page_id") == page["id"]
               for kind, result in results)
    visible = wiki.get_page(page["id"])
    assert "乙条件" in json.dumps(visible, ensure_ascii=False)
    assert "甲条件" not in json.dumps(visible, ensure_ascii=False)
    assert {int(ref.split(":", 2)[1]) for ref in wiki.history_source_refs(
        page["id"], space_id=space["id"])} == {second}


def test_revise_full_page_invalidates_old_guide(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=1001, folder_title="E-R1", history_policy="all")
    first = _add_material(db, artifacts, source_id, bvid="BV1E2345678L",
                          title="甲", text="甲材料只讨论准备条件。")
    space = store.create_space(name="E-R1 局部修改", source_ids=[source_id])

    class ReviseProvider(TopicProvider):
        def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400):
            if "SourceCard 提炼器" in system:
                return super().generate_json(system=system, prompt=prompt, max_tokens=max_tokens)
            payload = json.loads(prompt[prompt.index("\n") + 1:])
            prior = payload.get("existing_page")
            if prior:
                return {"title": payload["topic"], "page_type": "comparison",
                        "operation": "revise_block", "target_block_id": payload["page_directory"][0]["id"],
                        "summary": "不应使用的模型导读", "blocks": [{
                            "heading": "修订后的条件", "markdown": "甲乙材料只支持当前有限条件。",
                            "source_keys": ["s1", "s2"], "assessment": "source_reported",
                        }]}
            return {"title": payload["topic"], "page_type": "comparison",
                    "summary": "旧导读断言：甲必须执行。", "blocks": [{
                        "heading": "准备条件", "markdown": payload["source_card"]["summary"],
                        "source_keys": ["s1"], "assessment": "source_reported",
                    }]}

    provider = ReviseProvider()
    wiki.request_topic(space_id=space["id"], topic="共同主题",
                       source_refs=[f"video:{first}"], request_key="e-r1:revise:first")
    _drain_wiki_jobs(store, wiki, provider)
    page = wiki.list_pages(space_id=space["id"])[0]
    assert "旧导读断言" in page["summary"]
    second = _add_material(db, artifacts, source_id, bvid="BV1E2345678M",
                           title="乙", text="乙材料只讨论限定条件。")
    wiki.request_topic(space_id=space["id"], topic="共同主题",
                       source_refs=[f"video:{second}"], request_key="e-r1:revise:second")
    _drain_wiki_jobs(store, wiki, provider)
    current = wiki.get_page(page["id"])
    assert "旧导读断言" not in json.dumps(current, ensure_ascii=False)
    assert "不应使用的模型导读" not in json.dumps(current, ensure_ascii=False)
    assert "导读未随本次修改重写" in current["summary"]
    assert "甲乙材料" in json.dumps(current, ensure_ascii=False)


def test_revert_filtered_source_and_manual_edit_never_restore_old_guide(app_paths) -> None:
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=1002, folder_title="E-R1 过滤", history_policy="all")
    first = _add_material(db, artifacts, source_id, bvid="BV1E2345678N",
                          title="甲", text="甲正文仅供旧对照。")
    second = _add_material(db, artifacts, source_id, bvid="BV1E2345678P",
                           title="乙", text="乙正文仍然有效。")
    space = store.create_space(name="E-R1 导读", source_ids=[source_id])
    provider = CapturingSplitProvider()
    wiki.request_topic(space_id=space["id"], topic="共同主题",
                       source_refs=[f"video:{first}", f"video:{second}"],
                       request_key="e-r1:filtered:initial")
    _drain_wiki_jobs(store, wiki, provider)
    page = wiki.list_pages(space_id=space["id"])[0]
    assert "甲正文仅供旧对照" in page["summary"]
    with_note = wiki.add_personal_note(page["id"], space_id=space["id"],
        text="我的独立笔记：保留乙。", expected_version=page["version"],
        operation_key="e-r1:note:keep")
    later = wiki.add_personal_note(page["id"], space_id=space["id"],
        text="临时笔记", expected_version=with_note["version"],
        operation_key="e-r1:note:later")
    db.set_archived(first, True)
    reverted = wiki.revert(page["id"], target_version=with_note["version"],
                           expected_version=later["version"], operation_key="e-r1:revert")
    assert "甲正文仅供旧对照" not in json.dumps(reverted, ensure_ascii=False)
    assert "乙正文仍然有效" in json.dumps(reverted, ensure_ascii=False)
    assert "我的独立笔记" in json.dumps(reverted, ensure_ascii=False)
    api_page = asyncio.run(get_wiki(page["id"], request=_wiki_api_request(wiki),
                                   space_id=space["id"]))
    assert "甲正文仅供旧对照" not in json.dumps(api_page, ensure_ascii=False)
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="继续读取主题", request_id="e-r1:read")
    for name, arguments in (("knowledge_search", {"query": "甲正文仅供旧对照"}),
                            ("knowledge_read", {"page_id": page["id"]})):
        result = asyncio.run(registry.execute(name=name, arguments=arguments,
            call_id=f"e-r1:{name}", run_context=store.run_context(run["id"])))
        assert "甲正文仅供旧对照" not in json.dumps(result, ensure_ascii=False)
    with db.connect() as connection:
        connection.execute("UPDATE assistant_wiki_pages SET summary=? WHERE id=?",
                           ("旧乙导读断言：乙永远正确。", page["id"]))
    current = wiki.get_page(page["id"])
    valid = next(block for block in current["blocks"] if block.get("source_refs"))
    edited = wiki.edit_block(page["id"], block_id=valid["stable_id"],
        markdown="人工纠正：乙仅在当前条件有效。", expected_version=current["version"],
        operation_key="e-r1:edit")
    assert "旧乙导读断言" not in json.dumps(edited, ensure_ascii=False)
    assert "我的独立笔记" in json.dumps(edited, ensure_ascii=False)
    edited_api = asyncio.run(get_wiki(page["id"], request=_wiki_api_request(wiki),
                                       space_id=space["id"]))
    assert "旧乙导读断言" not in json.dumps(edited_api, ensure_ascii=False)
    for name, arguments in (("knowledge_search", {"query": "旧乙导读断言"}),
                            ("knowledge_read", {"page_id": page["id"]})):
        result = asyncio.run(registry.execute(name=name, arguments=arguments,
            call_id=f"e-r1:edited:{name}", run_context=store.run_context(run["id"])))
        assert "旧乙导读断言" not in json.dumps(result, ensure_ascii=False)
    third = _add_material(db, artifacts, source_id, bvid="BV1E2345678Q",
                          title="丙", text="丙材料提供新条件。")
    wiki.request_topic(space_id=space["id"], topic="共同主题",
                       source_refs=[f"video:{third}"], request_key="e-r1:after-edit")
    _drain_wiki_jobs(store, wiki, provider)
    complete_input = json.dumps(provider.wiki_inputs[-1], ensure_ascii=False)
    assert "甲正文仅供旧对照" not in complete_input
    assert "旧乙导读断言" not in complete_input
    assert "人工纠正：乙仅在当前条件有效" in complete_input
    assert "我的独立笔记" in complete_input


@pytest.mark.parametrize("loss_kind", ["archive", "leave_selected_folder"])
def test_source_loss_repairs_own_automatic_space_even_when_other_space_can_see_video(
    app_paths, loss_kind: str,
) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    selected = db.create_favorite_source(folder_id=1003, folder_title="自动范围", history_policy="all")
    other = db.create_favorite_source(folder_id=1004, folder_title="其他范围", history_policy="all")
    first = _add_material(db, artifacts, selected, bvid="BV1E2345678R",
                          title="甲", text="甲旧条件：仅在离线使用。")
    second = _add_material(db, artifacts, selected, bvid="BV1E2345678S",
                           title="乙", text="乙有效条件：在线先核实。")
    db.record_source_snapshot(other, [FavoriteItem(
        bvid="BV1E2345678R", title="甲", uploader="公开作者",
        favorite_time=1_700_000_001,
    )], processing_profile="fast", authoritative=False)
    all_space = store.create_space(name="全库按需", all_active=True)
    automatic = store.create_space(name="指定自动", source_ids=[selected],
                                   maintenance_mode="automatic")
    provider = TopicProvider()
    for space in (all_space, automatic):
        wiki.request_topic(space_id=space["id"], topic="共同主题",
                           source_refs=[f"video:{first}", f"video:{second}"],
                           request_key=f"e-r2:initial:{space['id']}")
    _drain_wiki_jobs(store, wiki, provider)
    all_page = wiki.list_pages(space_id=all_space["id"])[0]
    auto_page = wiki.list_pages(space_id=automatic["id"])[0]
    assert any(len(block["source_refs"]) == 2 for block in auto_page["blocks"])
    if loss_kind == "archive":
        db.set_archived(first, True)
        assert wiki.get_page(all_page["id"])["availability"] == "partial"
    else:
        db.record_source_snapshot(selected, [FavoriteItem(
            bvid="BV1E2345678S", title="乙", uploader="公开作者",
            favorite_time=1_700_000_000,
        )], processing_profile="fast", authoritative=True)
        assert wiki.get_page(all_page["id"])["availability"] == "full"
    assert wiki.get_page(auto_page["id"])["availability"] == "partial"
    with db.connect() as connection:
        repairs = [json.loads(row["payload_json"]) for row in connection.execute(
            "SELECT payload_json FROM assistant_jobs WHERE kind='wiki_integrate' AND status='queued'"
        ) if json.loads(row["payload_json"]).get("repair_page_id")]
    assert len(repairs) == 1
    assert repairs[0]["repair_page_id"] == auto_page["id"]
    assert repairs[0]["space_id"] == automatic["id"]

    class RepairProvider(LocalProvider):
        def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400):
            if "SourceCard 提炼器" in system:
                return super().generate_json(system=system, prompt=prompt, max_tokens=max_tokens)
            payload = json.loads(prompt[prompt.index("\n") + 1:])
            assert payload["repair_requested"]
            return {"operation": "revise_block", "title": payload["topic"],
                    "target_block_id": payload["invalid_block_directory"][0]["id"],
                    "blocks": [{"heading": "乙的当前条件", "markdown": "乙有效条件：在线先核实。",
                                "source_keys": ["s1"]}]}

    _drain_wiki_jobs(store, wiki, RepairProvider())
    repaired = wiki.get_page(auto_page["id"])
    assert repaired["availability"] == "full"
    assert "乙有效条件" in json.dumps(repaired, ensure_ascii=False)
    assert "甲旧条件" not in json.dumps(repaired, ensure_ascii=False)
    assert {int(ref.split(":", 2)[1]) for ref in wiki.history_source_refs(
        auto_page["id"], space_id=automatic["id"])} == {second}
    assert wiki.get_page(all_page["id"])["version"] == all_page["version"]


def test_decide_proposal_atomic_accept_retry_and_rejected_late_accept(app_paths, monkeypatch) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=1005, folder_title="E-R3", history_policy="all")
    ids = [_add_material(db, artifacts, source_id, bvid=f"BV1E2345678{suffix}",
                         title=f"材料{suffix}", text=f"材料{suffix}的独立条件。")
           for suffix in ("T", "U", "V", "W")]
    space = store.create_space(name="E-R3 决定", source_ids=[source_id])
    provider = LocalProvider()
    for index, video_id in enumerate(ids):
        topic = f"主题{index}"
        wiki.request_topic(space_id=space["id"], topic=topic,
                           source_refs=[f"video:{video_id}"], request_key=f"e-r3:create:{index}")
        _drain_wiki_jobs(store, wiki, provider)
    pages = {page["title"]: page for page in wiki.list_pages(space_id=space["id"])}

    def conflict_pair(first_index: int, second_index: int, key: str):
        source = pages[f"主题{first_index}"]
        target = pages[f"主题{second_index}"]
        source = wiki.add_personal_note(source["id"], space_id=space["id"],
            text=f"来源判断{key}", expected_version=source["version"],
            operation_key=f"e-r3:{key}:source")
        target = wiki.add_personal_note(target["id"], space_id=space["id"],
            text=f"目标判断{key}", expected_version=target["version"],
            operation_key=f"e-r3:{key}:target")
        proposal = wiki.merge_pages(source["id"], target["id"], space_id=space["id"],
            source_version=source["version"], target_version=target["version"],
            operation_key=f"e-r3:{key}:propose")
        assert proposal["status"] == "pending"
        return source, target, proposal["proposal_id"]

    source, target, proposal_id = conflict_pair(0, 1, "accept")
    original_fts = wiki._fts_replace
    def interrupted(_connection, _page):
        raise RuntimeError("injected_after_merge_writes")
    monkeypatch.setattr(wiki, "_fts_replace", interrupted)
    with pytest.raises(RuntimeError, match="injected_after_merge_writes"):
        wiki.decide_proposal(proposal_id, accept=True, operation_key="e-r3:accept:decision",
                             space_id=space["id"])
    monkeypatch.setattr(wiki, "_fts_replace", original_fts)
    assert wiki.get_page(source["id"])["id"] == source["id"]
    assert wiki.get_page(target["id"])["version"] == target["version"]
    assert proposal_id in {item["id"] for item in wiki.list_proposals(space_id=space["id"])}
    with db.connect() as connection:
        assert connection.execute("SELECT status FROM assistant_wiki_proposals WHERE id=?",
                                  (proposal_id,)).fetchone()["status"] == "pending"
        assert connection.execute("SELECT 1 FROM assistant_wiki_redirects WHERE old_page_id=?",
                                  (source["id"],)).fetchone() is None
        assert connection.execute("SELECT 1 FROM assistant_mutation_receipts WHERE operation_key=?",
                                  (f"wiki_proposal_merge:{proposal_id}",)).fetchone() is None

    payload = WikiProposalDecision(space_id=space["id"], accept=True,
                                   operation_key="e-r3:accept:decision")
    accepted = asyncio.run(decide_wiki_proposal(proposal_id, payload=payload,
                                                request=_wiki_api_request(wiki)))["result"]
    assert accepted["status"] == "accepted" and accepted["page_id"] == target["id"]
    assert wiki.get_page(source["id"])["redirected_from"] == source["id"]
    repeated = asyncio.run(decide_wiki_proposal(proposal_id, payload=payload,
                                                request=_wiki_api_request(wiki)))["result"]
    assert repeated == accepted
    new_key_repeat = wiki.decide_proposal(proposal_id, accept=True,
        operation_key="e-r3:accept:new-key", space_id=space["id"])
    assert new_key_repeat == accepted
    with db.connect() as connection:
        assert connection.execute("SELECT status FROM assistant_wiki_proposals WHERE id=?",
                                  (proposal_id,)).fetchone()["status"] == "accepted"
        assert connection.execute("SELECT COUNT(*) FROM assistant_wiki_redirects WHERE old_page_id=?",
                                  (source["id"],)).fetchone()[0] == 1

    rejected_source, rejected_target, rejected_id = conflict_pair(2, 3, "reject")
    rejected = wiki.decide_proposal(rejected_id, accept=False,
                                    operation_key="e-r3:reject:decision", space_id=space["id"])
    assert rejected["status"] == "rejected"
    assert wiki.decide_proposal(rejected_id, accept=False,
        operation_key="e-r3:reject:decision", space_id=space["id"]) == rejected
    late = wiki.decide_proposal(rejected_id, accept=True,
                                operation_key="e-r3:reject:late", space_id=space["id"])
    assert late == rejected
    assert wiki.get_page(rejected_source["id"])["id"] == rejected_source["id"]
    assert wiki.get_page(rejected_target["id"])["version"] == rejected_target["version"]
