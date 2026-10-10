from __future__ import annotations

import asyncio
import json
import threading

import pytest

from shiliu.assistant.context import ContextComposer
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.runtime import AssistantExecutionGraph
from shiliu.assistant.sources import SourceScope
from shiliu.assistant.store import AssistantConflict, AssistantRunStore
from shiliu.assistant.task_notes import TaskNoteService
from shiliu.assistant.tools import AssistantToolRegistry

from test_assistant_stage_b import _add_video, _source_service


def _record_read(store, sources, run_id, source_id, video_id, call_id, cursor=None):
    response = sources.read(
        call_id=call_id, scope=SourceScope(frozenset({source_id})),
        source_ref=f"video:{video_id}", view="description", cursor=cursor,
        max_characters=3000,
    ).model_dump(mode="json")
    store.save_assistant_tool_message(run_id, content="", provider_payload={"tool_calls": [{
        "id": call_id, "type": "function", "function": {
            "name": "collection_read", "arguments": "{}",
        },
    }]})
    store.begin_tool_call(run_id, ordinal=int(call_id[-1]) if call_id[-1].isdigit() else 1,
                          call_id=call_id, name="collection_read",
                          arguments={"source_ref": f"video:{video_id}", "view": "description"})
    response["result_ref"] = f"run-result:{run_id}:{call_id}"
    store.finish_tool_call(run_id, call_id=call_id, result=response)
    store.save_tool_result_message(
        run_id, content=json.dumps(response, ensure_ascii=False),
        provider_payload={"tool_call_id": call_id, "name": "collection_read"},
    )
    return response


def test_r1_inherit_only_current_summary_with_source_and_run_dependencies(app_paths):
    db, sources = _source_service(app_paths)
    source_id, video_id = _add_video(db)
    db.update_video(video_id, description="甲" * 6500)
    store = AssistantRunStore(db)
    space = store.create_space(name="R1", source_ids=[source_id])
    thread = store.create_thread(space["id"])
    first = store.create_run(thread["id"], text="读取独立事实", request_id="first")
    claimed = store.claim_next_run()
    assert claimed and claimed["id"] == first["id"]
    first_result = _record_read(store, sources, first["id"], source_id, video_id, "first")
    store.try_complete_run(first["id"], epoch=claimed["run_epoch"], answer="第一段已读", usage={},
                           expected_scope_version=space["scope_version"],
                           expected_observed_memory_epoch=0, dependency_refs=[],
                           expected_task_note_version=None)
    second = store.create_run(thread["id"], text="再读取", request_id="second")
    claimed = store.claim_next_run()
    assert claimed and claimed["id"] == second["id"]
    second_result = _record_read(store, sources, second["id"], source_id, video_id, "second",
                                 cursor=first_result["next_cursor"])
    notes = TaskNoteService(db, MemoryService(db),
                            source_ref_validator=lambda refs, _space: all(
                                ref == first_result["source_refs"][0] for ref in refs))
    context = store.run_context(second["id"])
    seq_first = next(int(m["seq"]) for m in context["thread"]["messages"]
                     if m.get("role") == "tool" and m.get("run_id") == first["id"])
    seq_second = next(int(m["seq"]) for m in context["thread"]["messages"]
                      if m.get("role") == "tool" and m.get("run_id") == second["id"])
    candidate = notes.build_candidate(context, messages=context["thread"]["messages"],
                                      recalled_memories=[], covered_until_message_seq=seq_second)
    candidate["findings"].extend([
        {"kind": "semantic_summary", "text": "独立有效事实", "message_seq": seq_first,
         "covered_until_message_seq": seq_first, "dependencies": first_result["source_refs"]},
        {"kind": "semantic_summary", "text": "应丢弃的旧事实", "message_seq": seq_second,
         "covered_until_message_seq": seq_second, "dependencies": second_result["source_refs"]},
    ])
    notes.commit(thread["id"], candidate)
    store.cancel_run(second["id"])
    next_run = store.create_run(thread["id"], text="继续", request_id="third")
    rebuilt = notes.build_candidate(store.run_context(next_run["id"]),
                                    messages=[m for m in store.run_context(next_run["id"])["thread"]["messages"]
                                              if m.get("run_id") != second["id"]],
                                    recalled_memories=[], covered_until_message_seq=seq_second)
    summaries = [f["text"] for f in rebuilt["findings"] if f["kind"] == "semantic_summary"]
    assert summaries == ["独立有效事实"]
    assert first_result["result_ref"] in rebuilt["dependencies"]
    assert second_result["result_ref"] not in rebuilt["dependencies"]
    assert second["id"] not in rebuilt["source_run_ids"]
    notes.source_ref_validator = lambda _refs, _space: False  # source revision no longer current
    changed = notes.build_candidate(store.run_context(next_run["id"]),
                                    messages=[m for m in store.run_context(next_run["id"])["thread"]["messages"]
                                              if m.get("run_id") != second["id"]],
                                    recalled_memories=[], covered_until_message_seq=seq_second)
    assert not any(f["kind"] == "semantic_summary" for f in changed["findings"])


def test_r2_cancel_during_compaction_prevents_late_note_and_next_call(app_paths):
    db, sources = _source_service(app_paths)
    source_id, video_id = _add_video(db)
    db.update_video(video_id, description="长文材料" * 1500)
    store = AssistantRunStore(db)
    space = store.create_space(name="R2", source_ids=[source_id])
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="完整阅读", request_id="r2")
    claimed = store.claim_next_run()
    assert claimed
    first = _record_read(store, sources, run["id"], source_id, video_id, "r1")
    _record_read(store, sources, run["id"], source_id, video_id, "r2", first["next_cursor"])
    memories = MemoryService(db)
    started, release = threading.Event(), threading.Event()

    class Provider:
        calls = 0

        def generate_json_with_usage(self, **_kwargs):
            self.calls += 1
            started.set()
            assert release.wait(5)
            return {"findings": ["迟到摘要"]}, {"prompt_tokens": 20, "completion_tokens": 10}

    provider = Provider()
    graph = AssistantExecutionGraph(
        store=store, memories=memories,
        tools=AssistantToolRegistry(sources=sources, memories=memories, store=store,
                                    wiki=None, context7=None),
        provider_factory=lambda: provider,
    )
    context = store.run_context(run["id"])
    _, _, metadata = graph.composer.compose_with_metadata(
        context, tool_schemas=graph.tools.schemas(), force_compact=True)
    assert metadata["covered_until_message_seq"] > 0
    assert graph.task_notes.get(thread["id"])

    async def exercise():
        task = asyncio.create_task(graph._compress_note_if_needed(
            context, metadata, state={"run_id": run["id"], "epoch": claimed["run_epoch"]}))
        assert await asyncio.to_thread(started.wait, 5)
        store.cancel_run(run["id"])
        release.set()
        with pytest.raises(AssistantConflict, match="semantic_run_terminated"):
            await task

    asyncio.run(exercise())
    assert provider.calls == 1
    note = graph.task_notes.get(thread["id"])
    assert note and not any(f["kind"] == "semantic_summary" for f in note["findings"])
    assert store.get_run(run["id"])["status"] == "cancelled"
    with pytest.raises(AssistantConflict, match="semantic_run_terminated"):
        graph.task_notes.commit_semantic_findings(
            thread["id"], note, [{"kind": "semantic_summary", "text": "迟到摘要",
                                  "dependencies": []}],
            run_id=run["id"], run_epoch=claimed["run_epoch"])
    following = store.create_run(thread["id"], text="新问题", request_id="after-r2")
    assert following["status"] == "queued"


def test_r3_tail_condition_is_structured_and_visible_in_compact_context():
    tail = "尾部关键条件：只在候选证据相互独立且用户确认后执行"
    semantic = TaskNoteService.bound_semantic({
        "findings": [f"普通事实 {index}" for index in range(30)],
        "conditions": [f"一般条件 {index}" for index in range(12)] + [tail],
        "disagreements": ["不同讲者有分歧"],
        "open_questions": ["本段未见后续内容", "原材料明确没有回答成本是多少"],
    })
    note = {"goal": "总结长文", "explicit_constraints": [],
            "searched_scope_and_material_refs": [], "open_questions": [], "next_actions": [],
            "findings": [{"kind": "semantic_summary", "semantic": semantic,
                          "text": json.dumps(semantic, ensure_ascii=False),
                          "dependencies": ["video:1:rev"],
                          "position": {"start": 6000, "end": 9000, "total": 9000}}]}
    rendered = TaskNoteService.render(note, compact=True)
    parsed = json.loads(rendered)
    assert tail in rendered
    assert parsed["阶段结果"][0]["semantic"]["disagreements"]
    assert parsed["阶段结果"][0]["semantic"]["open_questions"]
    assert "本段未见后续内容" not in rendered
    nested = TaskNoteService.bound_semantic({"findings": [{
        "topic": "跨段项目选型", "evidence": [{"position": "12000–24000",
                                     "text": "必须按场景解释精排选择"}],
        "conditions": ["选择依赖数据规模"],
        "open_questions": ["本段未涉及多 Agent", "本分段未交代手撕代码",
                           "资料确实未给出成本"],
    }]})
    assert "必须按场景解释精排选择" in nested["findings"][0]
    assert "选择依赖数据规模" in nested["conditions"]
    assert nested["open_questions"] == ["资料确实未给出成本"]
