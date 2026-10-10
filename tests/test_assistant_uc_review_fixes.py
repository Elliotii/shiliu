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
                           assistant_runtime=SimpleNamespace(memories=memories))
    app = FastAPI()
    app.state.core = core
    app.include_router(router)
    return TestClient(app)


def test_panel_create_and_patch_time_semantics(app_paths, monkeypatch):
    db = Database(app_paths.database)
    db.initialize()
    space = AssistantRunStore(db).create_space(name="时间", all_active=True)
    memories = MemoryService(db)
    client = _client(memories)
    clock = ["2026-09-24T02:00:00+00:00"]
    monkeypatch.setattr("shiliu.assistant.api.utc_now", lambda: clock[0])
    monkeypatch.setattr("shiliu.assistant.memory.utc_now", lambda: clock[0])

    def create(text, key):
        response = client.post("/api/assistant/memories", json={
            "text": text, "subject_key": key, "kind": "context", "scope_kind": "space",
            "scope_id": space["id"], "operation_key": f"create-{key}"})
        assert response.status_code == 201
        return response.json()["memory"]

    def edit_response(item, text, key, **fields):
        return client.patch(f"/api/assistant/memories/{item['id']}", json={
            "text": text, "expected_version": item["version"], "operation_key": key,
            **fields})

    def edit(item, text, key, **fields):
        response = edit_response(item, text, key, **fields)
        assert response.status_code == 200
        return response.json()["memory"]

    item = create("下周面试，准备系统设计", "interview")
    first_end = item["expires_at"]
    first_note = item["validity_note"]
    assert first_end == "2026-10-04T16:00:00+00:00"
    clock[0] = "2026-09-25T02:00:00+00:00"
    item = edit(item, "下周面试，准备数据库设计", "edit-words")
    assert (item["expires_at"], item["validity_note"]) == (first_end, first_note)
    item = edit(item, "未来30天准备系统设计面试", "edit-time")
    assert item["expires_at"] == "2026-10-25T16:00:00+00:00"
    assert "未来30天" in item["validity_note"] and "2026-09-25" in item["validity_note"]
    assert memories.recall("系统设计面试", space_id=space["id"])
    clock[0] = "2026-10-05T16:00:00+00:00"
    assert memories.recall("系统设计面试", space_id=space["id"])
    clock[0] = "2026-10-25T16:00:00+00:00"
    assert memories.recall("系统设计面试", space_id=space["id"]) == []
    clock[0] = "2026-09-26T02:00:00+00:00"
    item = edit(item, "长期准备系统设计面试", "edit-durable")
    assert item["expires_at"] is None and item["validity_note"] == ""
    item = edit(item, "长期准备系统设计面试", "edit-clear", expires_at=None)
    assert item["expires_at"] is None

    assert anchored_validity("未来30天准备面试", clock[0])["expires_at"] == "2026-10-26T16:00:00+00:00"
    assert anchored_validity("未来十二周准备面试", clock[0]) is None
    assert anchored_validity("改到下个月面试", clock[0]) is None
    assert client.post("/api/assistant/memories", json={"text": "下个月面试",
           "subject_key": "unsupported", "kind": "context", "scope_kind": "space",
           "scope_id": space["id"], "operation_key": "unsupported-create"}).status_code == 400
    assert edit_response(item, "改到下个月面试", "unsupported-edit").status_code == 400
    assert memories.get(item["id"])["text"] == item["text"]
    item = edit(item, "改到下个月面试", "explicit-date",
                expires_at="2026-11-01T00:00:00+08:00")
    assert item["expires_at"] == "2026-10-31T16:00:00+00:00"
    assert item["validity_note"] == ""
    assert item["validity_timezone"] == "explicit_offset"


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
    db = Database(app_paths.database)
    db.initialize()
    store = AssistantRunStore(db)
    space = store.create_space(name="工具更正", all_active=True)
    memories = MemoryService(db)
    registry = AssistantToolRegistry(sources=None, memories=memories, store=store)  # type: ignore[arg-type]
    clock = ["2026-09-24T02:00:00+00:00"]
    monkeypatch.setattr("shiliu.assistant.store.utc_now", lambda: clock[0])
    monkeypatch.setattr("shiliu.assistant.memory.utc_now", lambda: clock[0])

    def dispatch(message, name, arguments, call_id):
        thread = store.create_thread(space["id"])
        run = store.create_run(thread["id"], text=message, request_id=call_id)
        return asyncio.run(registry.execute(name=name, arguments=arguments, call_id=call_id,
                                            run_context=store.run_context(run["id"])))

    saved = dispatch("请记住我原定下周面试，但明确截止到2026-11-01。", "memory_save", {
        "text": "我准备后端面试", "subject_key": "backend_interview", "kind": "context",
        "expires_at": "2026-11-02T00:00:00+08:00"}, "save-explicit-date")
    assert saved["status"] == "ok"
    first = saved["items"][0]
    assert first["expires_at"] == "2026-11-01T16:00:00+00:00"
    assert "明确日期" in first["validity_note"]

    rejected = dispatch("请记住我下个月面试。", "memory_save", {
        "text": "我下个月面试", "subject_key": "invented_deadline", "kind": "context",
        "expires_at": "2026-11-02T00:00:00+08:00"}, "save-invented-date")
    assert rejected["error_code"] == "invalid_arguments"
    assert all(m["subject_key"] != "invented_deadline" for m in memories.list(space_id=space["id"]))

    wrong_date = dispatch("请记住我的面试截止到2026-11-01。", "memory_save", {
        "text": "我的面试截止到2026-11-01", "subject_key": "wrong_deadline", "kind": "context",
        "expires_at": "2026-11-10T00:00:00+08:00"}, "save-wrong-date")
    assert wrong_date["error_code"] == "invalid_arguments"

    invented_relative = dispatch("请记住我正在准备面试。", "memory_save", {
        "text": "我未来30天准备面试", "subject_key": "invented_relative", "kind": "context"},
        "save-invented-relative")
    assert invented_relative["error_code"] == "invalid_arguments"

    missing_date = dispatch("请记住我下周面试，但明确截止到2026-11-01。", "memory_save", {
        "text": "我下周面试", "subject_key": "missing_explicit_date", "kind": "context"},
        "save-missing-date")
    assert missing_date["error_code"] == "invalid_arguments"

    scoped = dispatch("请记住我下周要面试，也请记住我未来30天补数据库。", "memory_save", {
        "text": "我下周要面试", "subject_key": "scoped_interview", "kind": "context"},
        "save-scoped-time")
    assert scoped["status"] == "ok"
    assert scoped["items"][0]["expires_at"] == "2026-10-04T16:00:00+00:00"

    changed = dispatch("请把之前下周面试改到2026-11-03，明确以这一天为准。", "memory_correct", {
        "memory_id": first["id"], "expected_version": first["version"],
        "text": "2026-11-03准备数据库面试", "expires_at": "2026-11-04T00:00:00+08:00"},
        "correct-explicit-date")
    assert changed["status"] == "ok"
    assert changed["items"][0]["expires_at"] == "2026-11-03T16:00:00+00:00"

    next_month = dispatch("请把面试改到下个月，具体截止2026-11-20。", "memory_correct", {
        "memory_id": first["id"], "expected_version": changed["items"][0]["version"],
        "text": "下个月准备数据库面试", "expires_at": "2026-11-21T00:00:00+08:00"},
        "correct-next-month-explicit-date")
    assert next_month["status"] == "ok"
    assert next_month["items"][0]["expires_at"] == "2026-11-20T16:00:00+00:00"

    old = memories.save_explicit(text="下周后端面试", subject_key="week_interview", kind="context",
           scope_kind="space", scope_id=space["id"], operation_key="week-old",
           **anchored_validity("下周后端面试", clock[0]))
    old_end, old_note = old["expires_at"], old["validity_note"]
    clock[0] = "2026-10-05T02:00:00+00:00"
    edited = dispatch("之前下周面试那条只把后端改成数据库，日期不变。", "memory_correct", {
        "memory_id": old["id"], "expected_version": old["version"],
        "text": "下周数据库面试"}, "correct-words-only")
    assert edited["status"] == "ok"
    assert (edited["items"][0]["expires_at"], edited["items"][0]["validity_note"]) == (old_end, old_note)

    ambiguous = dispatch("把旧面试改到明天，但正文只写数据库面试。", "memory_correct", {
        "memory_id": old["id"], "expected_version": edited["items"][0]["version"],
        "text": "数据库面试"}, "correct-ambiguous-target")
    assert ambiguous["error_code"] == "invalid_arguments"
    assert memories.get(old["id"])["expires_at"] == old_end

    cleared = dispatch("把原来下周面试的记忆改成长期学习数据库，取消期限。", "memory_correct", {
        "memory_id": old["id"], "expected_version": edited["items"][0]["version"],
        "text": "长期学习数据库", "expires_at": old_end}, "correct-clear-time")
    assert cleared["status"] == "ok"
    assert cleared["items"][0]["expires_at"] is None
    assert cleared["items"][0]["validity_note"] == ""


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
