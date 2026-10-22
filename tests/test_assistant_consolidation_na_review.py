from __future__ import annotations

from assistant_offline_provider import offline_provider

from test_assistant_context_c2 import c2
from test_assistant_context_c3 import c3, history, state_for, notes
from assistant_context_support import mixed_checkpoint

import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from assistant_offline_provider import OfflineRequestProvider
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.provider import ModelTurn, NativeToolCall
from shiliu.assistant.runtime import AssistantExecutionGraph
from shiliu.assistant.sources import SourceScope
from shiliu.assistant.store import AssistantRunStore
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.wiki import MaintenanceYield, WikiService
from shiliu.db import Database
from test_assistant_stage_b import _add_video, _source_service


def services(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="R", all_active=True)
    thread = store.create_thread(space["id"])
    memories = MemoryService(db)
    tools = AssistantToolRegistry(sources=None, memories=memories, store=store)
    return db, store, space, thread, memories, tools


def graph(store, memories, tools, provider):
    if tools.sources is None:
        # This fixture deliberately exercises Memory/control only, with an empty source universe.
        tools.scope_identity = lambda space: {'visible_set_hash': 'synthetic-empty',
            'scope_version': space['scope_version'], 'source_ids': space['source_ids'],
            'video_ids': space['video_ids'], 'all_active': space['all_active']}
    value = AssistantExecutionGraph(store=store, memories=memories, tools=tools,
                                    provider_factory=lambda: OfflineRequestProvider(provider))
    value.dependency_ref_validator = None
    return value


def old_idle(store, db, *, run_id=None):
    old = (datetime.now(timezone.utc) - timedelta(seconds=240)).isoformat(timespec="seconds")
    with db.connect() as connection:
        connection.execute("UPDATE assistant_runtime_state SET value=? WHERE key='last_user_activity_at'", (old,))
        if run_id:
            connection.execute("UPDATE assistant_messages SET created_at=? WHERE run_id=?", (old, run_id))
            connection.execute("UPDATE assistant_runs SET completed_at=? WHERE id=?", (old, run_id))
    assert store.maintenance_idle(startup_at=old)
    return old


def test_finish_during_blocked_model_settles_late_usage_without_late_answer(app_paths):
    _db, store, _space, thread, memories, tools = services(app_paths)
    run = store.create_run(thread["id"], text="读材料", request_id="r1-finish")
    claimed = store.claim_next_run()
    started, release = threading.Event(), threading.Event()

    class Provider:
        calls = 0

        def turn(self, *, messages, tools, max_tokens):
            self.calls += 1
            if self.calls == 1:
                started.set()
                assert release.wait(5)
                return ModelTurn(text="迟到旧答案", tool_calls=[NativeToolCall(
                    call_id="late", name="collection_search", arguments={})],
                    usage={"prompt_tokens": 11, "completion_tokens": 3})
            assert tools == []
            return ModelTurn(text="先按当前成果回答", usage={"prompt_tokens": 7, "completion_tokens": 2})

    provider = Provider()

    async def scenario():
        active = asyncio.create_task(graph(store, memories, tools, provider).run(claimed))
        assert await asyncio.to_thread(started.wait, 2)
        store.request_finish(run["id"])
        await asyncio.wait_for(active, 2)
        assert store.get_run(run["id"])["status"] == "completed"
        assert provider.calls == 2
        release.set()
        await asyncio.sleep(.2)

    asyncio.run(scenario())
    assert store.get_run(run["id"])["usage"]["prompt_tokens"] == 18
    messages = store.get_thread(thread["id"])["messages"]
    assert sum("先按当前成果回答" in item["content"] for item in messages) == 1
    assert all("迟到旧答案" not in item["content"] for item in messages)


def test_cancel_during_blocked_model_allows_next_run(app_paths):
    _db, store, _space, thread, memories, tools = services(app_paths)
    old_run = store.create_run(thread["id"], text="先核对", request_id="r1-old")
    claimed = store.claim_next_run()
    started, release = threading.Event(), threading.Event()

    class Provider:
        def turn(self, *, messages, tools, max_tokens):
            if "先核对" in str(messages[-1]) and not release.is_set():
                started.set()
                assert release.wait(5)
                return ModelTurn(text="旧答案", usage={"prompt_tokens": 13})
            return ModelTurn(text="新请求已完成", usage={"prompt_tokens": 5})

    provider = Provider()

    async def scenario():
        active = asyncio.create_task(graph(store, memories, tools, provider).run(claimed))
        assert await asyncio.to_thread(started.wait, 2)
        store.cancel_run(old_run["id"])
        await asyncio.wait_for(active, 2)
        new_run = store.create_run(thread["id"], text="新任务", request_id="r1-new")
        await asyncio.wait_for(graph(store, memories, tools, provider).run(store.claim_next_run()), 2)
        assert store.get_run(new_run["id"])["status"] == "completed"
        release.set()
        await asyncio.sleep(.2)

    asyncio.run(scenario())
    assert store.get_run(old_run["id"])["usage"]["prompt_tokens"] == 13
    assert all(item["content"] != "旧答案" for item in store.get_thread(thread["id"])["messages"])


@pytest.mark.parametrize("cancel", [False, True])
def test_finish_after_tool_commits_keeps_result_receipt(app_paths, cancel):
    _db, store, _space, thread, memories, tools = services(app_paths)
    run = store.create_run(thread["id"], text="核对", request_id="r1-tool")
    claimed = store.claim_next_run()
    started = asyncio.Event()
    release = asyncio.Event()

    class Provider:
        calls = 0

        def turn(self, *, messages, tools, max_tokens):
            self.calls += 1
            if self.calls == 1:
                return ModelTurn(text="", tool_calls=[NativeToolCall(
                    call_id="read-1", name="collection_read", arguments={})],
                    usage={"prompt_tokens": 4})
            return ModelTurn(text="根据已完成读取先回答", usage={"prompt_tokens": 3})

    async def execute(**kwargs):
        from shiliu.assistant.contracts import ToolResult
        started.set()
        await release.wait()
        return ToolResult(call_id=kwargs['call_id'],status='ok',summary='合成读取结果',items=[{'content':'材料甲'}]).model_dump(mode='json')

    tools.execute = execute

    async def scenario():
        active = asyncio.create_task(graph(store, memories, tools, Provider()).run(claimed))
        await asyncio.wait_for(started.wait(), 2)
        if cancel:
            store.cancel_run(run["id"])
        else:
            store.request_finish(run["id"])
        release.set()
        await asyncio.wait_for(active, 2)

    asyncio.run(scenario())
    with store.db.connect() as connection:
        receipt = connection.execute("SELECT status,result_json FROM assistant_tool_calls "
                                     "WHERE run_id=? AND call_id='read-1'", (run["id"],)).fetchone()
    assert receipt["status"] == "completed"
    assert "材料甲" in receipt["result_json"]
    assert json.loads(receipt['result_json'])['coverage']['discarded'] is True
    assert store.get_run(run['id'])['tool_count'] == 0
    assert not store.get_run(run['id'])['working_state'].get('model_delivered_read_spans')
    assert store.get_run(run["id"])["status"] == ("cancelled" if cancel else "completed")
    assert not any(item['role'] == 'tool' for item in store.get_thread(thread['id'])['messages'])


def test_memory_publish_guard_orders_with_foreground_and_explicit_save(app_paths):
    db, store, space, thread, memories, _tools = services(app_paths)
    old = old_idle(store, db)
    proposal = {"op": "add", "kind": "context", "text": "自动提炼甲", "subject_key": "甲",
                "scope_kind": "space", "scope_id": space["id"], "source_excerpt": "自动提炼甲"}

    class Yield(Exception):
        pass

    def guard(connection):
        if not store.maintenance_idle(startup_at=old, connection=connection):
            raise Yield()

    assert store.maintenance_idle(startup_at=old)
    run = store.create_run(thread["id"], text="用户回来了", request_id="r2-return")
    with pytest.raises(Yield):
        memories.apply_extracted(proposal, source_message_ids=["source"], expected_epoch=0,
                                 operation_key="r2:auto", publish_guard=guard)
    assert memories.current_epoch() == 0
    assert memories.save_explicit(text="明确保存乙", subject_key="乙", kind="decision",
                                  scope_kind="space", scope_id=space["id"],
                                  operation_key="r2:explicit")
    store.cancel_run(run["id"])
    old_idle(store, db, run_id=run["id"])
    result = memories.apply_extracted(proposal, source_message_ids=["source"],
                                      expected_epoch=memories.current_epoch(),
                                      operation_key="r2:auto", publish_guard=guard)
    assert result and result["text"] == "自动提炼甲"


def test_source_head_publish_guard_orders_with_foreground(app_paths):
    db, sources = _source_service(app_paths)
    _source_id, video_id = _add_video(db)
    store = AssistantRunStore(db)
    space = store.create_space(name="R-source", all_active=True)
    thread = store.create_thread(space["id"])
    baseline = sources.snapshots.capture(video_id).revision
    db.update_video(video_id, description="新版材料")
    old = old_idle(store, db)

    class Yield(Exception):
        pass

    def guard(connection):
        if not store.maintenance_idle(startup_at=old, connection=connection):
            raise Yield()

    assert store.maintenance_idle(startup_at=old)
    run = store.create_run(thread["id"], text="用户先受理", request_id="r2-source")
    with pytest.raises(Yield):
        sources.snapshots.capture(video_id, publish_guard=guard)
    with db.connect() as connection:
        head = connection.execute("SELECT current_revision FROM assistant_source_heads "
                                  "WHERE video_id=?", (video_id,)).fetchone()
    assert head["current_revision"] == baseline
    store.cancel_run(run["id"])
    old_idle(store, db, run_id=run["id"])
    updated = sources.snapshots.capture(video_id, publish_guard=guard)
    assert updated.revision != baseline
    new_run = store.create_run(thread["id"], text="前台后受理", request_id="r2-source-after")
    with db.connect() as connection:
        head = connection.execute("SELECT current_revision FROM assistant_source_heads "
                                  "WHERE video_id=?", (video_id,)).fetchone()
    assert head["current_revision"] == updated.revision
    assert store.get_run(new_run["id"])["status"] == "queued"


def test_requested_topic_queue_obeys_idle_publish_gate_and_reuses_proposal(app_paths):
    db, sources = _source_service(app_paths)
    _source_id, video_id = _add_video(db)
    store = AssistantRunStore(db)
    space = store.create_space(name="R-topic", all_active=True)
    thread = store.create_thread(space["id"])
    wiki = WikiService(db=db, store=store, sources=sources)
    baseline = sources.snapshots.capture(video_id).revision
    db.update_video(video_id, description="新材料：方法甲适用于条件乙")
    old = old_idle(store, db)

    def guard(connection):
        if not store.maintenance_idle(startup_at=old, connection=connection):
            raise MaintenanceYield("maintenance_user_returned")

    wiki.publish_allowed = lambda: store.maintenance_idle(startup_at=old)
    wiki.publish_transaction_guard = guard
    queued = wiki.request_topic(space_id=space["id"], topic="方法甲",
                                source_refs=[f"video:{video_id}"], request_key="requested-topic")
    assert queued["status"] == "accepted"
    reconcile = store.claim_job(owner="r2-test")
    assert reconcile["kind"] == "source_reconcile" and reconcile["payload"]["request_key"]
    returned = store.create_run(thread["id"], text="前台先受理", request_id="r2-topic-return")
    with pytest.raises(MaintenanceYield):
        wiki.reconcile(reconcile)
    with db.connect() as connection:
        assert connection.execute("SELECT current_revision FROM assistant_source_heads WHERE video_id=?",
                                  (video_id,)).fetchone()["current_revision"] == baseline
    store.defer_job_for_activity(reconcile)
    store.cancel_run(returned["id"])
    old_idle(store, db, run_id=returned["id"])
    reconcile = store.claim_job(owner="r2-test")
    next_job = wiki.reconcile(reconcile)
    store.finish_job(reconcile["id"], owner="r2-test", lease_epoch=reconcile["lease_epoch"])
    with db.connect() as connection:
        head = connection.execute("SELECT current_revision FROM assistant_source_heads WHERE video_id=?",
                                  (video_id,)).fetchone()["current_revision"]
    assert head != baseline and next_job["revision"] == head

    class CardProvider:
        calls = 0
        def generate_json(self, **kwargs):
            self.calls += 1
            return {"summary": "方法甲适用于条件乙", "key_points": ["方法甲有条件乙"],
                    "topics": ["方法甲"], "limitations": []}

    card_provider = CardProvider()
    extraction = store.claim_job(owner="r2-test")
    assert extraction["kind"] == "source_extract" and extraction["payload"]["request_key"]
    wiki.extract_source_card(extraction, provider=card_provider)
    store.finish_job(extraction["id"], owner="r2-test", lease_epoch=extraction["lease_epoch"])

    class PageProvider:
        calls = 0
        def generate_json(self, **kwargs):
            self.calls += 1
            self.returned = store.create_run(thread["id"], text="用户又回来", request_id="r2-page-return")
            return {"same_topic": True, "title": "方法甲", "page_type": "method",
                    "summary": "方法甲的条件", "blocks": [{
                        "heading": "适用条件", "markdown": "方法甲适用于条件乙",
                        "applicability": "条件乙", "assessment": "有条件支持", "relation": "supports",
                        "source_keys": ["s1"], "speaker": "公开作者",
                        "cited_source": "", "evidence_quote": "方法甲适用于条件乙"}]}

    page_provider = PageProvider()
    integration = store.claim_job(owner="r2-test")
    assert integration["kind"] == "wiki_integrate" and integration["payload"]["request_key"]
    with pytest.raises(MaintenanceYield):
        wiki.integrate_source_card(integration, provider=page_provider)
    assert wiki.list_pages(space_id=space["id"]) == []
    with db.connect() as connection:
        staged = connection.execute("SELECT proposal_json FROM assistant_jobs WHERE id=?",
                                    (integration["id"],)).fetchone()["proposal_json"]
    assert json.loads(staged)["kind"] == "wiki_integrate"
    store.defer_job_for_activity(integration)
    store.cancel_run(page_provider.returned["id"])
    old_idle(store, db, run_id=page_provider.returned["id"])
    integration = store.claim_job(owner="r2-test")
    applied = wiki.integrate_source_card(integration, provider=page_provider)
    store.finish_job(integration["id"], owner="r2-test", lease_epoch=integration["lease_epoch"])
    assert applied["version"] == 1 and len(wiki.list_pages(space_id=space["id"])) == 1
    assert page_provider.calls == 1 and card_provider.calls == 1
    assert wiki.request_topic(space_id=space["id"], topic="方法甲",
                              source_refs=[f"video:{video_id}"],
                              request_key="requested-topic")["status"] == "already_available"


@pytest.mark.parametrize('forget', [False, True])
def test_focus_and_history_receipt_drop_corrected_memory_keep_materials(c3, forget):
    from test_assistant_context_c2 import running, batch, execute
    memory = c3.memories.save_explicit(text='个人决定 A：采用旧方案', subject_key='方案', kind='decision',
        pinned=True, scope_kind='space', scope_id=c3.space['id'], operation_key='old-focus')
    run, state, candidate = history(c3)
    candidate = c3.composer.prepare(run['id'], provider=c3.provider)
    c3.store.save_context_observation(run['id'], epoch=run['run_epoch'], metadata=candidate.metadata)
    result = execute(c3, run, 'task_focus', {'goal':'按个人决定 A 继续', 'working_notes':'旧方案 A 已确认',
        'selected_source_refs':[f'video:{c3.video_id}']}, call_id='focus')
    batch(c3, run, [('focus','task_focus',{'goal':'按个人决定 A 继续'},result)])
    c3.store.cancel_run(run['id'])
    changed = c3.memories.correct(memory['id'],expected_version=1,text='个人决定 B：采用新方案',operation_key='new-focus')
    if forget: c3.memories.forget(memory['id'],expected_version=changed['version'],operation_key='forget-focus')
    latest = running(c3, text='继续核对材料', key='next-focus')
    fresh = c3.composer.prepare(latest['id'],provider=c3.provider)
    rendered = str(fresh.request.body)
    assert '旧方案 A 已确认' not in rendered and '按个人决定 A 继续' not in rendered
    assert '甲乙丙丁条件' in rendered
    assert not c3.tools.dependency_refs_valid([f"run-result:{run['id']}:focus"],c3.space['id'],c3.thread['id'],1)
    c3.store.save_context_observation(latest['id'],epoch=latest['run_epoch'],metadata=fresh.metadata)
    focus = c3.store.save_task_focus(latest['id'],epoch=latest['run_epoch'],focus={
        'goal':'按新目标核对材料','working_notes':'新的有效工作稿','selected_source_refs':[f'video:{c3.video_id}']})
    assert c3.memories.dependency_ref(memory) not in focus['dependency_refs']
    assert '新的有效工作稿' in str(c3.composer.prepare(latest['id'],provider=c3.provider).request.body)


@pytest.mark.parametrize('cancel', [False, True])
def test_committed_memory_write_keeps_receipt_after_control(app_paths, cancel):
    _, store, space, thread, memories, tools = services(app_paths)
    run = store.create_run(thread['id'],text='请记住：我的项目优先可靠性',request_id='committed-write')
    claimed = store.claim_next_run()
    committed, release = asyncio.Event(), asyncio.Event()
    original_execute = tools.execute
    saved = []
    class Provider:
        calls = 0
        def turn(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return ModelTurn('', [NativeToolCall('save-committed','memory_save',
                    {'text':'我的项目优先可靠性','subject_key':'project-rule','kind':'constraint'})])
            return ModelTurn('已保留实际提交的记忆回执。')
    async def execute(**kwargs):
        result = await original_execute(**kwargs)
        assert result['status']=='ok', result
        saved.append(result['items'][0]['id'])
        committed.set()
        await release.wait()
        return result
    tools.execute = execute
    async def scenario():
        task = asyncio.create_task(graph(store,memories,tools,Provider()).run(claimed))
        await asyncio.wait_for(committed.wait(),2)
        assert memories.get(saved[0])['status']=='active'
        if cancel: store.cancel_run(run['id'])
        else: store.request_finish(run['id'])
        release.set()
        await asyncio.wait_for(task,2)
    asyncio.run(scenario())
    assert memories.get(saved[0])['status']=='active'
    with store.db.connect() as connection:
        receipt = connection.execute('SELECT status,result_json FROM assistant_tool_calls WHERE run_id=? AND call_id=?',
                                     (run['id'],'save-committed')).fetchone()
    assert receipt['status']=='completed' and saved[0] in receipt['result_json']
    assert any(m['role']=='tool' and saved[0] in m['content'] for m in store.get_thread(thread['id'])['messages'])
    assert store.get_run(run['id'])['status']==('cancelled' if cancel else 'completed')
