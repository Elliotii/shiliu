from __future__ import annotations

import asyncio
import json
import threading
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shiliu.assistant.api import router
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.memory_policy import anchored_validity
from shiliu.assistant.runtime import AssistantRuntime
from shiliu.assistant.store import AssistantRunStore
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.db import Database


def _client(memories):
    core = SimpleNamespace(config=SimpleNamespace(assistant_enabled=True),
                           assistant_runtime=SimpleNamespace(memories=memories, store=AssistantRunStore(memories.db)))
    app = FastAPI()
    app.state.core = core
    app.include_router(router)
    return TestClient(app)


def test_panel_create_and_patch_time_semantics(app_paths, monkeypatch):
    db = Database(app_paths.database)
    db.initialize()
    space = AssistantRunStore(db).create_space(name='时间', all_active=True)
    memories = MemoryService(db)
    client = _client(memories)
    clock = ['2026-10-17T02:00:00+00:00']
    monkeypatch.setattr('shiliu.assistant.api.utc_now', lambda: clock[0])
    monkeypatch.setattr('shiliu.assistant.memory.utc_now', lambda: clock[0])
    response = client.post('/api/assistant/memories', json=dict(text='下个月准备面试',
        kind='context', scope_kind='space', scope_id=space['id'], operation_key='panel-create'))
    assert response.status_code == 201
    item = response.json()['memory']
    assert item['expires_at'] is None and item['time_context']['events'][0]['value'] == '2026-11'
    clock[0] = '2026-12-17T02:00:00+00:00'
    response = client.patch(f"/api/assistant/memories/{item['id']}", json=dict(text='下个月准备后端面试',
        expected_version=1, operation_key='panel-polish', update_time_context=False))
    assert response.status_code == 200
    assert response.json()['memory']['time_context'] == item['time_context']
    response = client.patch(f"/api/assistant/memories/{item['id']}", json=dict(text='下个月准备后端面试',
        expected_version=2, operation_key='panel-reschedule', update_time_context=True))
    assert response.status_code == 200
    assert response.json()['memory']['time_context']['events'][0]['value'] == '2027-01'


def test_auto_policy_fences_queued_and_inflight_jobs(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="自动准入", all_active=True)
    memories = MemoryService(db)
    excerpt = "我决定未来30天准备系统设计面试"

    def completed_job(request_id):
        thread = store.create_thread(space["id"])
        run = store.create_run(thread["id"], text=excerpt, request_id=request_id)
        claimed = store.claim_next_run()
        assert claimed and store.complete_run(run["id"], epoch=claimed["run_epoch"], answer="收到", usage={})
        job = store.claim_job(owner=request_id)
        assert job and job["kind"] == "memory_extract"
        return job

    class Provider:
        def __init__(self, started=None, release=None):
            self.started, self.release = started, release
            self.calls = 0

        def extract_memories(self, *, prompt):
            self.calls += 1
            if self.started:
                self.started.set()
                assert self.release.wait(5)
            return [{"op": "add", "kind": "decision", "text": excerpt,
                     "subject_key": "system_design_preparation", "scope_kind": "space",
                     "scope_id": space["id"], "source_excerpt": excerpt}]

    provider = Provider()
    runtime = AssistantRuntime.__new__(AssistantRuntime)
    runtime.store, runtime.memories = store, memories
    runtime.extraction_provider_factory = lambda: provider

    memories.set_auto_enabled(False)
    off_job = completed_job("while-off")
    assert off_job["payload"]["auto_enabled_at_enqueue"] is False
    memories.set_auto_enabled(True)
    result = asyncio.run(runtime._extract_memories(off_job))
    assert result["reason"] == "automatic_memory_policy_changed" and provider.calls == 0

    started, release = threading.Event(), threading.Event()
    runtime.extraction_provider_factory = lambda: Provider(started, release)
    pending = completed_job("before-toggle")
    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(asyncio.run(runtime._extract_memories(pending))))
    thread.start()
    assert started.wait(5)
    memories.set_auto_enabled(False)
    memories.set_auto_enabled(True)
    release.set()
    thread.join(5)
    assert outcome and not outcome[0]["applied_memory_ids"]
    assert memories.list(space_id=space["id"]) == []
    assert memories.apply_extracted({"op": "add", "kind": "context", "text": excerpt,
           "subject_key": "stale", "scope_kind": "space", "scope_id": space["id"]},
           source_message_ids=["old"], expected_epoch=0, operation_key="stale-commit",
           expected_auto_generation=pending["payload"]["auto_memory_generation"]) is None

    runtime.extraction_provider_factory = lambda: provider
    fresh = completed_job("after-reopen")
    assert fresh["payload"]["auto_memory_generation"] == memories.auto_policy()["generation"]
    result = asyncio.run(runtime._extract_memories(fresh))
    assert len(result["applied_memory_ids"]) == 1
    assert len(memories.list(space_id=space["id"])) == 1
    explicit = memories.save_explicit(text="我长期练习数据库", subject_key="database_practice",
               kind="context", scope_kind="space", scope_id=space["id"], operation_key="explicit-after-toggle")
    assert explicit["status"] == "active"


def test_real_memory_tool_dispatch_respects_target_time_and_user_date(app_paths, monkeypatch):
    # v2: actual applicability is distinct from an interview/event deadline.
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="工具时间", all_active=True)
    memories = MemoryService(db)
    registry = AssistantToolRegistry(sources=None, memories=memories, store=store)
    clock = '2026-10-17T02:00:00+00:00'
    monkeypatch.setattr('shiliu.assistant.store.utc_now', lambda: clock)
    def dispatch(words, args, call):
        thread = store.create_thread(space['id'])
        run = store.create_run(thread['id'], text=words, request_id=call)
        return asyncio.run(registry.execute(name='memory_save', arguments=args, call_id=call,
            run_context=store.run_context(run['id'])))
    args = dict(text='我下个月面试', subject_key='interview', kind='context')
    event = dispatch('请记住我下个月面试', args, 'event')
    assert event['status'] == 'ok'
    assert event['items'][0]['expires_at'] is None
    assert event['items'][0]['time_context']['events'][0]['value'] == '2026-11'
    bad = dispatch('请记住我2026-11-01面试', {**args, 'text':'我2026-11-01面试', 'expires_at':'2026-11-02T00:00:00+08:00'}, 'bad')
    assert bad['error_code'] == 'memory_validity_without_user_basis'
    actual = dispatch('这个约束只在月底之前有效', {**args, 'text':'这个约束只在月底之前有效',
        'expires_at':'2026-11-01T00:00:00+08:00'}, 'actual')
    assert actual['status'] == 'ok'
    assert actual['items'][0]['expires_at'] == '2026-10-31T16:00:00+00:00'


def test_run_creation_admission_survives_toggle_before_completion(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="创建时准入", all_active=True)
    memories = MemoryService(db)
    excerpt = "我决定未来30天准备系统设计面试"

    class Provider:
        def extract_memories(self, *, prompt):
            return [{"op": "add", "kind": "decision", "text": excerpt,
                     "subject_key": "interview_plan", "scope_kind": "space",
                     "scope_id": space["id"], "source_excerpt": excerpt}]

    runtime = AssistantRuntime.__new__(AssistantRuntime)
    runtime.store, runtime.memories = store, memories
    runtime.extraction_provider_factory = Provider

    def create(request_id):
        thread = store.create_thread(space["id"])
        return store.create_run(thread["id"], text=excerpt, request_id=request_id)

    def finish(run, owner):
        claimed = store.claim_next_run()
        assert claimed and claimed["id"] == run["id"]
        assert store.complete_run(run["id"], epoch=claimed["run_epoch"], answer="收到", usage={})
        job = store.claim_job(owner=owner)
        assert job and job["kind"] == "memory_extract"
        return job

    memories.set_auto_enabled(False)
    off_run = create("created-off")
    assert off_run["working_state"]["auto_memory_admission"]["enabled"] is False
    memories.set_auto_enabled(True)
    off_job = finish(off_run, "off-then-on")
    assert off_job["payload"]["auto_enabled_at_enqueue"] is False
    assert asyncio.run(runtime._extract_memories(off_job))["applied_memory_ids"] == []

    on_run = create("created-on")
    original_generation = on_run["working_state"]["auto_memory_admission"]["generation"]
    memories.set_auto_enabled(False)
    memories.set_auto_enabled(True)
    on_job = finish(on_run, "on-off-on")
    assert on_job["payload"]["auto_memory_generation"] == original_generation
    assert original_generation != memories.auto_policy()["generation"]
    assert asyncio.run(runtime._extract_memories(on_job))["applied_memory_ids"] == []
    assert memories.list(space_id=space["id"]) == []

    legacy_run = create("legacy-without-admission")
    with db.connect() as connection:
        state = dict(legacy_run["working_state"])
        state.pop("auto_memory_admission")
        connection.execute("UPDATE assistant_runs SET working_state_json=? WHERE id=?",
                           (json.dumps(state), legacy_run["id"]))
    legacy_job = finish(legacy_run, "legacy")
    assert legacy_job["payload"]["auto_enabled_at_enqueue"] is False
    assert legacy_job["payload"]["auto_memory_generation"] == -1
    assert asyncio.run(runtime._extract_memories(legacy_job))["applied_memory_ids"] == []

    fresh_run = create("created-after-reopen")
    fresh_job = finish(fresh_run, "fresh")
    assert fresh_job["payload"]["auto_memory_generation"] == memories.auto_policy()["generation"]
    assert len(asyncio.run(runtime._extract_memories(fresh_job))["applied_memory_ids"]) == 1
