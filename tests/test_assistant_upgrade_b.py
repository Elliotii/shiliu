from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from shiliu.assistant.context import ContextComposer
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.provider import ModelTurn
from shiliu.assistant.runtime import AssistantExecutionGraph
from shiliu.assistant.sources import SourceScope
from shiliu.assistant.store import AssistantRunStore
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.domain import FavoriteItem

from test_assistant_stage_b import _add_video, _source_service


def test_rank_fusion_counts_real_queries_and_read_positions_are_bound(app_paths):
    db, sources = _source_service(app_paths)
    source_id, first_id = _add_video(db)
    second_id = first_id + 1
    db.record_source_snapshot(source_id, [
        FavoriteItem(
            bvid="BV1B23456789", title="Memory Agent 工程", uploader="公开作者", favorite_time=1_700_000_000,
        ),
        FavoriteItem(
            bvid="BV1B2345678A", title="Agent 实战", uploader="公开作者", favorite_time=1_700_000_001,
        ),
    ], processing_profile="fast", authoritative=True, remote_total=2)
    actual_second = db.get_video_by_source("BV1B2345678A")
    assert actual_second and int(actual_second["id"]) == second_id
    calls = []

    class Search:
        def search_with_raw(self, request, **_kwargs):
            calls.append(request.query)
            ids = [first_id, second_id] if request.query == "Agent" else [second_id, first_id]
            return SimpleNamespace(executed_mode="hybrid", fallback=False,
                                   fallback_reason=None, timing=SimpleNamespace(total_ms=12.0)), SimpleNamespace(
                results=[SimpleNamespace(video_id=value, match_excerpt="匹配片段") for value in ids]
            )

    sources.product_search = Search()
    scope = SourceScope(source_db_ids=frozenset({source_id}))
    result = sources.search(call_id="search", scope=scope, query="Agent",
                            query_variants=["智能体", "Agent"], mode="content", limit=2)
    assert calls == ["Agent", "智能体"]
    assert result.coverage["retrieval_requests"] == 2
    assert result.coverage["retrieval_candidate_count"] == 2
    assert len(result.items) == 2
    assert len(result.items[0]["match_basis"]) == 2

    db.update_video(first_id, description="引言" * 900 + "关键条件：只在输入可靠时执行" + "结尾" * 600)
    focused = sources.read(call_id="read", scope=scope, source_ref=f"video:{first_id}",
                           view="description", query="关键条件", max_characters=1000)
    position = focused.coverage["read_position"]
    assert position["start"] > 0
    assert "关键条件" in focused.items[0]["content"]
    assert focused.coverage["selection"] == "relevant_span"
    assert focused.coverage["read_complete"] is False
    invalid = sources.read(call_id="bad", scope=scope, source_ref=focused.source_refs[0],
                           view="description", query="关键条件", cursor=focused.next_cursor)
    assert invalid.error_code == "query_cursor_conflict"


def test_forced_recovery_compacts_material_before_answer_and_keeps_pairing(app_paths):
    db, sources = _source_service(app_paths)
    source_id, video_id = _add_video(db)
    db.update_video(video_id, description=("有条件 A，缺少条件 B。" * 650).ljust(11990, "甲")
                    + "尾端条件不能忽略")
    store = AssistantRunStore(db)
    space = store.create_space(name="长阅读", source_ids=[source_id])
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="完整读完材料，说明条件 A 和未解决的 B", request_id="long")
    claimed = store.claim_next_run()
    assert claimed and claimed["id"] == run["id"]
    result = sources.read(call_id="read-1", scope=SourceScope(frozenset({source_id})),
                          source_ref=f"video:{video_id}", view="description", max_characters=12000).model_dump(mode="json")
    store.save_assistant_tool_message(run["id"], content="", provider_payload={"tool_calls": [{
        "id": "read-1", "type": "function", "function": {
            "name": "collection_read", "arguments": json.dumps({"source_ref": f"video:{video_id}", "view": "description"}),
        },
    }]})
    store.begin_tool_call(run["id"], ordinal=1, call_id="read-1", name="collection_read",
                          arguments={"source_ref": f"video:{video_id}", "view": "description"})
    result["result_ref"] = f"run-result:{run['id']}:read-1"
    store.finish_tool_call(run["id"], call_id="read-1", result=result)
    store.save_tool_result_message(run["id"], content=json.dumps(result, ensure_ascii=False),
                                   provider_payload={"tool_call_id": "read-1", "name": "collection_read"})

    class Provider:
        def __init__(self):
            self.compaction_prompts = []
            self.answer_messages = []

        def generate_json_with_usage(self, *, system, prompt, max_tokens):
            self.compaction_prompts.append(prompt)
            return {"findings": ["条件 A 有前提"], "conditions": ["输入可靠"],
                    "disagreements": [], "open_questions": ["条件 B 仍缺失"]}, {"prompt_tokens": 900, "completion_tokens": 100}

        def turn(self, *, messages, tools, max_tokens):
            self.answer_messages = messages
            return ModelTurn(text="条件 A 需输入可靠；条件 B 尚未解决。", usage={"prompt_tokens": 600, "completion_tokens": 40})

    provider = Provider()
    memories = MemoryService(db)
    registry = AssistantToolRegistry(sources=sources, memories=memories, store=store,
                                     wiki=None, context7=None)
    graph = AssistantExecutionGraph(store=store, memories=memories, tools=registry,
                                    provider_factory=lambda: provider)
    assert store.mark_context_recovery_attempt(run["id"], epoch=claimed["run_epoch"])
    asyncio.run(graph.run(store.get_run(run["id"])))
    finished = store.get_run(run["id"])
    assert finished["status"] == "completed", (finished["last_error_code"], finished["last_error_message"])
    assert len(provider.compaction_prompts) == 1
    assert "有条件 A" in provider.compaction_prompts[0]
    assert "尾端条件不能忽略" in provider.compaction_prompts[0]
    assert "条件 B 仍缺失" in json.dumps(provider.answer_messages, ensure_ascii=False)
    assert finished["usage"]["prompt_tokens"] == 1500
    note = graph.task_notes.get(thread["id"])
    assert note and any(item["kind"] == "semantic_summary" for item in note["findings"])
    assert '"compressed_for_answer": true' in graph.task_notes.render(note)


def test_delivered_coverage_requires_confirmed_model_input(app_paths):
    db, sources = _source_service(app_paths)
    source_id, video_id = _add_video(db)
    db.update_video(video_id, description="甲" * 2500)
    store = AssistantRunStore(db)
    space = store.create_space(name="覆盖", source_ids=[source_id])
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="读全文", request_id="read")
    store.claim_next_run()
    first = sources.read(call_id="r1", scope=SourceScope(frozenset({source_id})),
                         source_ref=f"video:{video_id}", view="description", max_characters=1500)
    second = sources.read(call_id="r2", scope=SourceScope(frozenset({source_id})),
                          source_ref=first.source_refs[0], view="description",
                          cursor=first.next_cursor, max_characters=1500)
    for index, value in enumerate((first, second), 1):
        call_id = f"r{index}"
        store.save_assistant_tool_message(run["id"], content="", provider_payload={"tool_calls": [{
            "id": call_id, "type": "function", "function": {"name": "collection_read", "arguments": "{}"},
        }]})
        payload = value.model_dump(mode="json")
        payload["result_ref"] = f"run-result:{run['id']}:{call_id}"
        store.save_tool_result_message(run["id"], content=json.dumps(payload, ensure_ascii=False),
                                       provider_payload={"tool_call_id": call_id, "name": "collection_read"})
    composer = ContextComposer(MemoryService(db), input_budget_tokens=10000)
    _, _, metadata = composer.compose_with_metadata(store.run_context(run["id"]))
    assert len(metadata["delivered_read_spans"]) == 1
    assert metadata["delivered_read_spans"][0]["start"] == 1500
    assert metadata["delivered_read_spans"][0]["end"] == 2500
    assert store.get_run(run["id"])["working_state"].get("model_delivered_read_spans") is None
    store.confirm_model_delivery(run["id"], epoch=1, spans=metadata["delivered_read_spans"])
    assert len(store.get_run(run["id"])["working_state"]["model_delivered_read_spans"]) == 1


def test_note_identity_retains_actual_titles_and_transcript_search_evidence():
    messages = [
        {"role": "assistant", "provider_payload_json": json.dumps({"tool_calls": [{
            "id": "s1", "function": {"arguments": json.dumps({
                "query": "Agent 面试", "require_transcript": True,
            })},
        }]})},
        {"role": "tool", "content": json.dumps({
            "status": "ok", "items": [{"source_ref": "video:73:rev1",
                                      "title": "真实标题", "available_views": ["transcript"]}],
        }), "provider_payload_json": json.dumps({"name": "collection_search",
                                                "tool_call_id": "s1"})},
        {"role": "tool", "content": json.dumps({
            "status": "ok", "items": [{"video": {"title": "另一真实标题"},
                                      "source_ref": "video:58:rev2"}],
        }), "provider_payload_json": json.dumps({"name": "collection_read",
                                                "tool_call_id": "r1"})},
    ]
    titles, searches = ContextComposer._material_identity(messages)
    assert titles == {"73": "真实标题", "58": "另一真实标题"}
    assert searches == [{"query": "Agent 面试", "require_transcript": True,
                         "returned_count": 1, "candidates": [{
                             "title": "真实标题", "source_ref": "video:73:rev1",
                             "available_views": ["transcript"],
                         }]}]
