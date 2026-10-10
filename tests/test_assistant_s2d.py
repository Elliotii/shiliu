from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from shiliu.assistant.api import get_wiki
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.wiki import WikiService
from shiliu.db import utc_now
from shiliu.domain import FavoriteItem
from test_assistant_stage_c import _add_material, _drain_wiki_jobs, _services


class TopicProvider:
    def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400):
        payload = json.loads(prompt[prompt.index("\n") + 1:])
        if "SourceCard 提炼器" in system:
            material = payload["material"]
            return {
                "summary": material[:100],
                "key_points": [{
                    "heading": "条件", "markdown": material[:90],
                    "applicability": "按材料所述条件", "assessment": "source_reported",
                    "evidence_quote": material[-10:],
                }],
                "topics": ["共同主题", "另一主题"], "limitations": [],
            }
        card = payload["source_card"]
        prior = payload.get("existing_page")
        keys = [item["key"] for item in payload["source_catalog"]]
        return {
            "title": payload["topic"], "page_type": "comparison",
            "summary": "两份材料条件不同，需按适用范围分别理解。" if prior else "先记录该材料的适用条件。",
            "blocks": [{
                "heading": "适用条件", "markdown": card["summary"],
                "applicability": "按材料所述条件", "assessment": "source_reported",
                "relation": "condition_difference" if prior else "related",
                "source_keys": keys,
            }],
        }


class CapturingSplitProvider(TopicProvider):
    def __init__(self) -> None:
        self.wiki_inputs: list[dict] = []

    def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400):
        if "SourceCard 提炼器" in system:
            return super().generate_json(system=system, prompt=prompt, max_tokens=max_tokens)
        payload = json.loads(prompt[prompt.index("\n") + 1:])
        self.wiki_inputs.append(payload)
        cards = payload["source_catalog"]
        return {
            "title": payload["topic"], "page_type": "comparison",
            "summary": "导读：" + "；".join(item["card"]["summary"] for item in cards),
            "blocks": [{
                "heading": f"材料 {item['key']}", "markdown": item["card"]["summary"],
                "assessment": "source_reported", "source_keys": [item["key"]],
            } for item in cards],
        }


def _wiki_api_request(wiki: WikiService) -> SimpleNamespace:
    core = SimpleNamespace(
        config=SimpleNamespace(assistant_enabled=True),
        assistant_runtime=SimpleNamespace(wiki=wiki),
    )
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(core=core)))


def test_summary_keeps_annotation_separate_and_located() -> None:
    snapshot = {
        "materials": {"summary": "作者认为条件甲才适用", "raw_subtitle": "字幕原文"},
        "metadata": {"description": "视频简介", "title": "材料", "uploader": "上传者", "published_at": None},
        "notes": [{"id": 4, "content": "我记录的疑问乙，另提到官方文档", "updated_at": "2026-01-01"}],
        "memberships": [], "coverage": "summary",
    }
    material, view = WikiService._card_material(snapshot)
    assert view == "summary_and_notes"
    assert "作者认为条件甲" in material and "我记录的疑问乙" in material
    assert "作者身份未核实" in material
    card = WikiService._normalize_card({
        "summary": "待核对", "topics": ["主题"], "key_points": [{
            "heading": "注释", "markdown": "注释提出疑问", "assessment": "user_annotation",
            "evidence_quote": "我记录的疑问乙，另提到官方文档", "speaker": "上传者", "cited_source": "官方文档",
        }],
    }, snapshot, view)
    point = card["key_points"][0]
    assert point["assessment"] == "user_annotation"
    assert point["position"] is not None
    assert point["material_view"] == view
    assert point["cited_source_checked"] is False
    assert point["cited_source"] == "官方文档"
    assert point["speaker"] == ""  # Uploader is not automatically the speaker.
    assert card["annotation_count"] == 1
    assert not WikiService._reference_like("Osmo Action 5 Pro")
    assert WikiService._reference_like("官方文档")


def test_explicit_topic_request_organizes_two_sources_and_personal_note(app_paths) -> None:
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=971, folder_title="D", history_policy="all")
    first = _add_material(db, artifacts, source_id, bvid="BV1D23456781", title="材料甲", text="仅当输入明确时使用方案甲。")
    second = _add_material(db, artifacts, source_id, bvid="BV1D23456782", title="材料乙", text="输入不确定时先保留方案乙。")
    space = store.create_space(name="D 主题", source_ids=[source_id])
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="把材料甲和乙整理成共同主题", request_id="d-topic")
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    args = {"topic": "共同主题", "source_refs": [f"video:{first}", f"video:{second}"]}
    accepted = asyncio.run(registry.execute(name="knowledge_organize", arguments=args,
        call_id="organize", run_context=store.run_context(run["id"])))
    assert accepted["status"] == "ok"
    assert accepted["items"][0]["status"] == "accepted"
    store.begin_tool_call(run["id"], ordinal=1, call_id="organize", name="knowledge_organize", arguments=args)
    store.finish_tool_call(run["id"], call_id="organize", result=accepted)
    repeated = asyncio.run(registry.execute(name="knowledge_organize", arguments=args,
        call_id="organize", run_context=store.run_context(run["id"])))
    assert repeated["items"][0]["job_ids"] == accepted["items"][0]["job_ids"]
    outcomes = _drain_wiki_jobs(store, wiki, TopicProvider())
    assert any(kind == "wiki_integrate" for kind, _ in outcomes)
    pages = wiki.list_pages(space_id=space["id"], query="共同主题")
    assert len(pages) == 1
    page = pages[0]
    assert len(page["blocks"]) == 1
    assert "条件不同" in page["summary"]
    assert len(wiki.history_source_refs(page["id"], space_id=space["id"])) == 2
    updated = wiki.add_personal_note(page["id"], space_id=space["id"],
        text="我当前先试方案甲，再核对输入条件。", expected_version=page["version"],
        operation_key="ui:d-note")
    assert updated["blocks"][-1]["assessment"] == "user_explicit"
    assert updated["blocks"][-1]["source_refs"] == []
    assert len(wiki.history_source_refs(page["id"], space_id=space["id"])) == 2
    receipt_ref = f"run-result:{run['id']}:organize"
    assert registry.dependency_refs_valid([receipt_ref], space["id"], thread["id"], space["scope_version"])
    receipt = asyncio.run(registry.execute(name="run_read_result", arguments={"result_ref": receipt_ref},
        call_id="receipt-read", run_context=store.run_context(run["id"])))
    assert receipt["status"] == "ok" and receipt["items"][0]["items"][0]["status"] == "accepted"
    read = asyncio.run(registry.execute(name="knowledge_read", arguments={
        "page_id": page["id"], "mode": "relevant", "query": "方案甲 方案乙"},
        call_id="read", run_context=store.run_context(run["id"])))
    assert read["status"] == "ok"
    assert any(block["assessment"] == "user_explicit" for block in read["items"][0]["blocks"])
    store.begin_tool_call(run["id"], ordinal=2, call_id="read", name="knowledge_read", arguments={"page_id": page["id"]})
    store.finish_tool_call(run["id"], call_id="read", result=read)
    result_ref = f"run-result:{run['id']}:read"
    assert registry.dependency_refs_valid([result_ref], space["id"], thread["id"], space["scope_version"])
    path = artifacts.video_dir("BV1D23456781") / "stage-c-summary.md"
    artifacts.write_text(path, "材料甲已经修订，旧条件不再成立。")
    db.update_video(first, summary_path=str(path), status="completed")
    sources.snapshots.capture(first)
    visible = wiki.get_page(page["id"], space_id=space["id"])
    assert len(visible["blocks"]) == 1
    assert any(block["assessment"] == "user_explicit" for block in visible["blocks"])
    assert all("仅当输入明确" not in block["markdown"] for block in visible["blocks"])
    assert not registry.dependency_refs_valid([result_ref], space["id"], thread["id"], space["scope_version"])
    old = asyncio.run(registry.execute(name="run_read_result", arguments={"result_ref": result_ref},
        call_id="old-read", run_context=store.run_context(run["id"])))
    assert old["status"] == "unavailable"


def test_one_video_can_join_another_topic_without_reextracting(app_paths) -> None:
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=972, folder_title="D2", history_policy="all")
    video_id = _add_material(db, artifacts, source_id, bvid="BV1D23456783", title="交叉材料", text="同一材料讨论两个问题。")
    space = store.create_space(name="D 双主题", source_ids=[source_id])
    for topic in ("共同主题", "另一主题"):
        wiki.request_topic(space_id=space["id"], topic=topic,
            source_refs=[f"video:{video_id}"], request_key=f"ui:{topic}")
        _drain_wiki_jobs(store, wiki, TopicProvider())
    pages = wiki.list_pages(space_id=space["id"])
    assert {page["title"] for page in pages} == {"共同主题", "另一主题"}
    assert all(len(wiki.history_source_refs(page["id"], space_id=space["id"])) == 1 for page in pages)


def test_reorganization_cannot_drop_existing_source(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=977, folder_title="D7", history_policy="all")
    first = _add_material(db, artifacts, source_id, bvid="BV1D2345678B", title="材料甲", text="条件甲。")
    second = _add_material(db, artifacts, source_id, bvid="BV1D2345678C", title="材料乙", text="条件乙。")
    space = store.create_space(name="D 来源覆盖", source_ids=[source_id])
    wiki.request_topic(space_id=space["id"], topic="共同主题",
        source_refs=[f"video:{first}"], request_key="ui:cover-first")
    _drain_wiki_jobs(store, wiki, TopicProvider())
    before = wiki.list_pages(space_id=space["id"])[0]

    class OmittingProvider(TopicProvider):
        def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400):
            result = super().generate_json(system=system, prompt=prompt, max_tokens=max_tokens)
            if "Wiki 局部编译器" in system:
                result["blocks"][0]["source_keys"] = ["s1"]
            return result

    wiki.request_topic(space_id=space["id"], topic="共同主题",
        source_refs=[f"video:{second}"], request_key="ui:cover-second")
    outcomes = _drain_wiki_jobs(store, wiki, OmittingProvider())
    assert any(kind == "wiki_integrate" and result.get("reason") == "proposal_missing_source_coverage"
               for kind, result in outcomes)
    after = wiki.list_pages(space_id=space["id"])[0]
    assert after["version"] == before["version"]
    assert {int(ref.split(":", 2)[1]) for ref in wiki.history_source_refs(
        after["id"], space_id=space["id"]
    )} == {first}


def test_partial_invalid_projection_is_used_for_page_tool_and_compiler(app_paths) -> None:
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=978, folder_title="D-R1", history_policy="all")
    old = _add_material(db, artifacts, source_id, bvid="BV1D2345678D",
                        title="材料甲", text="失效独特观点甲：必须先关掉检索。")
    valid = _add_material(db, artifacts, source_id, bvid="BV1D2345678E",
                          title="材料乙", text="有效独特观点乙：保留检索。")
    space = store.create_space(name="D-R1 部分失效", source_ids=[source_id])
    provider = CapturingSplitProvider()
    wiki.request_topic(space_id=space["id"], topic="共同主题",
        source_refs=[f"video:{old}", f"video:{valid}"], request_key="ui:r1-initial")
    _drain_wiki_jobs(store, wiki, provider)
    page = wiki.list_pages(space_id=space["id"])[0]
    assert "失效独特观点甲" in page["summary"]
    page = wiki.add_personal_note(page["id"], space_id=space["id"],
        text="我的独立判断：继续对照两份材料。", expected_version=page["version"],
        operation_key="ui:r1-personal-note")

    path = artifacts.video_dir("BV1D2345678D") / "stage-c-summary.md"
    artifacts.write_text(path, "材料甲已经修订，旧观点失效。")
    db.update_video(old, summary_path=str(path), status="completed")
    sources.snapshots.capture(old)
    assert "失效独特观点甲" in json.dumps(
        wiki.get_page(page["id"], space_id=space["id"], include_hidden=True), ensure_ascii=False
    )
    current = wiki.get_page(page["id"], space_id=space["id"])
    encoded = json.dumps(current, ensure_ascii=False)
    assert current["availability"] == "partial"
    assert "失效独特观点甲" not in encoded
    assert "有效独特观点乙" in encoded
    assert "我的独立判断" in encoded
    assert any(block.get("assessment") == "user_explicit" for block in current["blocks"])
    api_page = asyncio.run(get_wiki(page["id"], request=_wiki_api_request(wiki),
                                   space_id=space["id"]))
    assert "失效独特观点甲" not in json.dumps(api_page, ensure_ascii=False)

    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="读取共同主题", request_id="r1-partial-read")
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    read = asyncio.run(registry.execute(name="knowledge_read", arguments={
        "page_id": page["id"], "mode": "relevant", "query": "有效独特观点乙"},
                                        call_id="r1-read", run_context=store.run_context(run["id"])))
    assert read["status"] == "ok"
    assert "失效独特观点甲" not in json.dumps(read, ensure_ascii=False)
    assert "有效独特观点乙" in json.dumps(read, ensure_ascii=False)

    new = _add_material(db, artifacts, source_id, bvid="BV1D2345678F",
                        title="材料丙", text="新增独特观点丙：限定条件再整合。")
    before_inputs = len(provider.wiki_inputs)
    wiki.request_topic(space_id=space["id"], topic="共同主题",
        source_refs=[f"video:{new}"], request_key="ui:r1-refresh")
    _drain_wiki_jobs(store, wiki, provider)
    assert len(provider.wiki_inputs) > before_inputs
    complete_input = json.dumps(provider.wiki_inputs[-1], ensure_ascii=False)
    assert "失效独特观点甲" not in complete_input
    assert "有效独特观点乙" in complete_input
    assert "新增独特观点丙" in complete_input
    assert "我的独立判断" in complete_input
    old_page = provider.wiki_inputs[-1]["existing_page"]
    assert any(block["content_origin"] == "personal_note" and
               block["assessment"] == "user_explicit" for block in old_page["blocks"])
    refreshed = wiki.get_page(page["id"], space_id=space["id"])
    assert "失效独特观点甲" not in json.dumps(refreshed, ensure_ascii=False)
    assert {int(ref.split(":", 2)[1]) for ref in wiki.history_source_refs(
        page["id"], space_id=space["id"]
    )} == {valid, new}
    assert any(block.get("assessment") == "user_explicit" for block in refreshed["blocks"])


def test_all_invalid_page_never_returns_old_summary(app_paths) -> None:
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=979, folder_title="D-R1 全失效", history_policy="all")
    video_id = _add_material(db, artifacts, source_id, bvid="BV1D2345678G",
                             title="唯一材料", text="全失效独特导读：不要再引用。")
    space = store.create_space(name="D-R1 全失效", source_ids=[source_id])
    wiki.request_topic(space_id=space["id"], topic="共同主题",
        source_refs=[f"video:{video_id}"], request_key="ui:r1-only")
    _drain_wiki_jobs(store, wiki, CapturingSplitProvider())
    page = wiki.list_pages(space_id=space["id"])[0]
    assert "全失效独特导读" in page["summary"]
    store.update_space(space["id"], expected_scope_version=space["scope_version"], source_ids=[])
    assert "全失效独特导读" in json.dumps(
        wiki.get_page(page["id"], space_id=space["id"], include_hidden=True), ensure_ascii=False
    )

    current = wiki.get_page(page["id"], space_id=space["id"])
    assert current["blocks"] == []
    assert "全失效独特导读" not in json.dumps(current, ensure_ascii=False)
    api_page = asyncio.run(get_wiki(page["id"], request=_wiki_api_request(wiki),
                                   space_id=space["id"]))
    assert "全失效独特导读" not in json.dumps(api_page, ensure_ascii=False)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="读取共同主题", request_id="r1-empty-read")
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    read = asyncio.run(registry.execute(name="knowledge_read", arguments={"page_id": page["id"]},
                                        call_id="r1-empty", run_context=store.run_context(run["id"])))
    assert read["status"] == "empty"
    assert "全失效独特导读" not in json.dumps(read, ensure_ascii=False)
    assert page["id"] not in {item["id"] for item in wiki.list_pages(space_id=space["id"])}

    with_note = wiki.add_personal_note(page["id"], space_id=space["id"],
        text="我的独立判断仍保留。", expected_version=current["version"],
        operation_key="ui:r1-empty-note")
    assert "全失效独特导读" not in json.dumps(with_note, ensure_ascii=False)
    assert with_note["blocks"][0]["assessment"] == "user_explicit"
    assert "仅保留独立个人笔记" in with_note["summary"]


def test_mixed_block_keeps_valid_card_for_rebuild_after_scope_withdrawal(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    removed_source = db.create_favorite_source(folder_id=980, folder_title="撤出来源", history_policy="all")
    kept_source = db.create_favorite_source(folder_id=981, folder_title="保留来源", history_policy="all")
    old = _add_material(db, artifacts, removed_source, bvid="BV1D2345678H",
                        title="撤出材料", text="撤出独特观点：不可再输入。")
    valid = _add_material(db, artifacts, kept_source, bvid="BV1D2345678I",
                          title="保留材料", text="保留独特观点：可用于新整理。")
    space = store.create_space(name="D-R1 混合块", source_ids=[removed_source, kept_source])

    class MixedThenSplitProvider(CapturingSplitProvider):
        merge = True

        def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400):
            result = super().generate_json(system=system, prompt=prompt, max_tokens=max_tokens)
            if "Wiki 局部编译器" in system and self.merge:
                keys = [block["source_keys"][0] for block in result["blocks"]]
                result["blocks"] = [{
                    "heading": "混合说法", "markdown": result["summary"],
                    "assessment": "system_synthesis", "source_keys": keys,
                }]
            return result

    provider = MixedThenSplitProvider()
    wiki.request_topic(space_id=space["id"], topic="共同主题",
        source_refs=[f"video:{old}", f"video:{valid}"], request_key="ui:r1-mixed")
    _drain_wiki_jobs(store, wiki, provider)
    page = wiki.list_pages(space_id=space["id"])[0]
    assert len(page["blocks"]) == 1 and len(page["blocks"][0]["source_refs"]) == 2
    wiki.add_personal_note(page["id"], space_id=space["id"],
        text="我的独立判断：暂时保留乙。", expected_version=page["version"],
        operation_key="ui:r1-mixed-note")
    store.update_space(space["id"], expected_scope_version=space["scope_version"],
                       source_ids=[kept_source])
    projected = wiki.get_page(page["id"], space_id=space["id"])
    assert len(projected["blocks"]) == 1
    assert projected["blocks"][0]["assessment"] == "user_explicit"
    assert "撤出独特观点" not in json.dumps(projected, ensure_ascii=False)

    new = _add_material(db, artifacts, kept_source, bvid="BV1D2345678J",
                        title="新增材料", text="新增独特观点：只在条件明确时整合。")
    provider.merge = False
    wiki.request_topic(space_id=space["id"], topic="共同主题",
        source_refs=[f"video:{new}"], request_key="ui:r1-mixed-refresh")
    _drain_wiki_jobs(store, wiki, provider)
    complete_input = json.dumps(provider.wiki_inputs[-1], ensure_ascii=False)
    assert "撤出独特观点" not in complete_input
    assert "保留独特观点" in complete_input
    assert "新增独特观点" in complete_input
    assert "我的独立判断" in complete_input
    refreshed = wiki.get_page(page["id"], space_id=space["id"])
    assert {int(ref.split(":", 2)[1]) for ref in wiki.history_source_refs(
        page["id"], space_id=space["id"]
    )} == {valid, new}
    assert any(block["assessment"] == "user_explicit" for block in refreshed["blocks"])


def test_related_candidate_sees_page_older_than_fifty_newer_pages(app_paths) -> None:
    db, _artifacts, _sources, store, wiki = _services(app_paths)
    space = store.create_space(name="D 老主题", all_active=True)
    with db.connect() as connection:
        for index in range(61):
            title = "Agent 记忆工程" if index == 0 else f"无关专题 {index}"
            connection.execute(
                """INSERT INTO assistant_wiki_pages(
                    id,principal_id,space_id,normalized_title,title,aliases_json,
                    page_type,summary,blocks_json,version,status,scope_version,created_at,updated_at
                ) VALUES(?,?,?,?,?,'[]','topic','','[]',1,'active',?,?,?)""",
                (f"test-page-{index}", "local_operator", space["id"],
                 wiki._normalize_title(title), title, space["scope_version"],
                 f"2026-01-{index + 1:02d}" if index < 28 else f"2026-02-{index - 27:02d}",
                 f"2026-01-{index + 1:02d}" if index < 28 else f"2026-02-{index - 27:02d}"),
            )
    found = wiki._find_related_page(space["id"], {"topics": ["Agent 记忆工程"]})
    assert found and found["id"] == "test-page-0"


def test_task_input_suppression_blocks_late_wiki_commit(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=973, folder_title="D3", history_policy="all")
    video_id = _add_material(db, artifacts, source_id, bvid="BV1D23456784", title="过期任务", text="不要发布过期理解。")
    space = store.create_space(name="D 过期任务", source_ids=[source_id])
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="把这份材料整理成主题", request_id="d-stale")
    user = next(message for message in store.run_context(run["id"])["thread"]["messages"] if message["role"] == "user")
    wiki.request_topic(space_id=space["id"], topic="过期主题", source_refs=[f"video:{video_id}"],
        request_key="tool:d-stale", source_message_id=user["id"])
    with db.connect() as connection:
        connection.execute(
            """INSERT INTO assistant_memory_suppressions(
                principal_id,scope_kind,scope_id,subject_key,content_hash,
                source_message_ids_json,memory_epoch,created_at
            ) VALUES('local_operator','space',?,'task','deadbeef',?,1,?)""",
            (str(space["id"]), json.dumps([user["id"]]), utc_now()),
        )
    outcomes = _drain_wiki_jobs(store, wiki, TopicProvider())
    assert any(kind == "wiki_integrate" and result == {
        "superseded": True, "reason": "wiki_task_input_stale"
    } for kind, result in outcomes)
    assert wiki.list_pages(space_id=space["id"]) == []


def test_ordinary_question_cannot_create_topic(app_paths) -> None:
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=974, folder_title="D4", history_policy="all")
    video_id = _add_material(db, artifacts, source_id, bvid="BV1D23456785", title="普通材料", text="普通问答只需要读取。")
    space = store.create_space(name="D 普通问答", source_ids=[source_id])
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="这份材料说了什么？", request_id="d-normal")
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    refused = asyncio.run(registry.execute(name="knowledge_organize",
        arguments={"topic": "普通主题", "source_refs": [f"video:{video_id}"]},
        call_id="wrong-tool", run_context=store.run_context(run["id"])))
    assert refused["status"] == "unavailable"
    assert refused["error_code"] == "explicit_request_required"
    assert wiki.list_pages(space_id=space["id"]) == []


def test_source_trigger_updates_existing_topic_and_skips_unrelated_new_page(app_paths) -> None:
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=975, folder_title="D5", history_policy="all")
    first = _add_material(db, artifacts, source_id, bvid="BV1D23456786", title="共同材料甲", text="共同主题的甲条件。")
    second = _add_material(db, artifacts, source_id, bvid="BV1D23456787", title="共同材料乙", text="共同主题的乙条件。")
    third = _add_material(db, artifacts, source_id, bvid="BV1D23456788", title="孤立材料", text="只谈孤立问题。")
    space = store.create_space(name="D 来源触发", source_ids=[source_id], maintenance_mode="automatic")
    provider = TopicProvider()
    wiki.request_topic(space_id=space["id"], topic="共同主题", source_refs=[f"video:{first}"], request_key="ui:first")
    _drain_wiki_jobs(store, wiki, provider)

    class DistinctProvider(TopicProvider):
        def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400):
            result = super().generate_json(system=system, prompt=prompt, max_tokens=max_tokens)
            if "SourceCard 提炼器" in system and "孤立材料" in prompt:
                result["topics"] = ["孤立主题"]
            return result

    for video_id in (second, third):
        with db.connect() as connection:
            generation = wiki._ensure_dirty(connection, video_id)
            wiki._enqueue_reconcile(connection, video_id, generation)
    outcomes = _drain_wiki_jobs(store, wiki, DistinctProvider())
    page = wiki.list_pages(space_id=space["id"])
    assert len(page) == 1 and page[0]["title"] == "共同主题"
    assert {int(ref.split(":", 2)[1]) for ref in wiki.history_source_refs(
        page[0]["id"], space_id=space["id"]
    )} == {first, second}
    assert any(kind == "source_extract" and result.get("integration_job_ids") == []
               for kind, result in outcomes)


def test_same_word_different_topic_is_not_merged_by_lexical_candidate(app_paths) -> None:
    db, artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=976, folder_title="D6", history_policy="all")
    first = _add_material(db, artifacts, source_id, bvid="BV1D23456789", title="Agent 记忆工程", text="工程实现的条件。")
    second = _add_material(db, artifacts, source_id, bvid="BV1D2345678A", title="Agent 记忆历史", text="历史研究的条件。")
    space = store.create_space(name="D 同词不同题", source_ids=[source_id], maintenance_mode="automatic")
    wiki.request_topic(space_id=space["id"], topic="Agent 记忆工程",
        source_refs=[f"video:{first}"], request_key="ui:engineering")
    _drain_wiki_jobs(store, wiki, TopicProvider())

    class SeparateProvider(TopicProvider):
        def generate_json(self, *, system: str, prompt: str, max_tokens: int = 2400):
            result = super().generate_json(system=system, prompt=prompt, max_tokens=max_tokens)
            if "SourceCard 提炼器" in system:
                result["topics"] = ["Agent 记忆历史"]
            else:
                result["same_topic"] = False
            return result

    with db.connect() as connection:
        generation = wiki._ensure_dirty(connection, second)
        wiki._enqueue_reconcile(connection, second, generation)
    outcomes = _drain_wiki_jobs(store, wiki, SeparateProvider())
    assert any(kind == "wiki_integrate" and result.get("reason") == "no_existing_topic_match"
               for kind, result in outcomes)
    pages = wiki.list_pages(space_id=space["id"])
    assert len(pages) == 1 and pages[0]["title"] == "Agent 记忆工程"
    assert {int(ref.split(":", 2)[1]) for ref in wiki.history_source_refs(
        pages[0]["id"], space_id=space["id"]
    )} == {first}


def test_title_only_source_returns_no_op_instead_of_inventing_a_theme(app_paths) -> None:
    db, _artifacts, _sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=977, folder_title="D7", history_policy="all")
    db.record_source_snapshot(source_id, [FavoriteItem(
        bvid="BV1D2345678B", title="仅标题材料", uploader="未知上传者",
        favorite_time=1_700_000_000,
    )], processing_profile="fast", authoritative=False)
    video = db.get_video_by_source("BV1D2345678B")
    assert video is not None
    space = store.create_space(name="D 空正文", source_ids=[source_id])
    wiki.request_topic(space_id=space["id"], topic="不能凭标题编造的主题",
        source_refs=[f"video:{video['id']}"], request_key="ui:title-only")
    outcomes = _drain_wiki_jobs(store, wiki, TopicProvider())
    assert any(kind == "wiki_integrate" and result.get("no_change") is True
               and result.get("reason") == "insufficient_material" for kind, result in outcomes)
    assert wiki.list_pages(space_id=space["id"]) == []
