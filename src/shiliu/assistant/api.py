from __future__ import annotations

import asyncio
import json
import hashlib
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from shiliu.assistant.store import AssistantConflict
from shiliu.db import utc_now


router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SpaceCreate(StrictBody):
    name: str = Field(min_length=1, max_length=100)
    goal: str = Field(default="", max_length=1000)
    source_ids: list[int] = Field(default_factory=list)
    video_ids: list[int] = Field(default_factory=list)
    all_active: bool = False
    maintenance_mode: str = Field(default="on_demand", pattern="^(on_demand|automatic)$")


class SpaceUpdate(StrictBody):
    expected_scope_version: int = Field(ge=1)
    name: str | None = Field(default=None, max_length=100)
    goal: str | None = Field(default=None, max_length=1000)
    source_ids: list[int] | None = None
    video_ids: list[int] | None = None
    all_active: bool | None = None
    maintenance_mode: str | None = Field(default=None, pattern="^(on_demand|automatic)$")


class ThreadCreate(StrictBody):
    space_id: int = Field(ge=1)
    title: str = Field(default="", max_length=200)


class RunCreate(StrictBody):
    answer_message_id: str | None = None
    receipt_only: bool = False
    input: str = Field(min_length=1, max_length=100000)
    request_id: str = Field(min_length=1, max_length=200)


class MemoryCreate(StrictBody):
    text: str = Field(min_length=1, max_length=400)
    subject_key: str | None = Field(default=None, min_length=1, max_length=120)
    kind: str = "constraint"
    scope_kind: str = "space"
    scope_id: int | None = None
    operation_key: str | None = Field(default=None, min_length=1, max_length=200)
    pinned: bool = False
    valid_from: str | None = None
    expires_at: str | None = None
    validity_note: str = Field(default="", max_length=400)
    validity_timezone: str | None = Field(default=None, max_length=80)


class MemoryUpdate(StrictBody):
    text: str = Field(min_length=1, max_length=400)
    expected_version: int = Field(ge=1)
    update_time_context: bool | None = None
    operation_key: str = Field(min_length=1, max_length=200)
    subject_key: str | None = None
    kind: str | None = None
    valid_from: str | None = None
    expires_at: str | None = None
    validity_note: str | None = Field(default=None, max_length=400)
    validity_timezone: str | None = Field(default=None, max_length=80)


class MemoryCreationUndo(StrictBody):
    space_id: int = Field(ge=1)
    save_operation_key: str = Field(min_length=1, max_length=200)
    expected_version: int = Field(ge=1)
    operation_key: str = Field(min_length=1, max_length=200)


class AutoMemorySetting(StrictBody):
    enabled: bool


class WikiBlockUpdate(StrictBody):
    space_id: int = Field(ge=1)
    block_id: str = Field(min_length=1, max_length=100)
    markdown: str = Field(min_length=1, max_length=20000)
    expected_version: int = Field(ge=1)
    operation_key: str | None = Field(default=None, min_length=1, max_length=200)


class WikiLifecycle(StrictBody):
    space_id: int = Field(ge=1)
    action: str = Field(pattern="^(delete_block|restore_block|archive|restore)$")
    expected_version: int = Field(ge=1)
    operation_key: str = Field(min_length=1, max_length=200)
    block_id: str | None = None


class PlanItemAction(StrictBody):
    space_id: int = Field(ge=1)
    action: str = Field(pattern="^(ignore|restore)$")
    expected_version: int = Field(ge=1)
    operation_key: str = Field(min_length=1, max_length=200)


class PlanFieldRepair(StrictBody):
    space_id: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    operation_key: str = Field(min_length=1, max_length=200)
    corrections: list[dict[str, Any]] = Field(min_length=1, max_length=20)


class WikiRevert(StrictBody):
    space_id: int = Field(ge=1)
    target_version: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    operation_key: str | None = Field(default=None, min_length=1, max_length=200)


class WikiOrganize(StrictBody):
    space_id: int = Field(ge=1)
    topic: str = Field(min_length=1, max_length=120)
    source_refs: list[str] = Field(min_length=1, max_length=5)
    request_id: str = Field(min_length=1, max_length=200)


class WikiPersonalNote(StrictBody):
    space_id: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=4000)
    expected_version: int = Field(ge=1)
    operation_key: str | None = Field(default=None, min_length=1, max_length=200)
    memory_id: str | None = None
    memory_version: int | None = Field(default=None, ge=1)


class WikiMerge(StrictBody):
    space_id: int = Field(ge=1)
    source_page_id: str
    target_page_id: str
    source_version: int = Field(ge=1)
    target_version: int = Field(ge=1)
    operation_key: str | None = Field(default=None, min_length=1, max_length=200)


class WikiProposalDecision(StrictBody):
    space_id: int = Field(ge=1)
    accept: bool
    operation_key: str | None = Field(default=None, min_length=1, max_length=200)


class KnowledgePlanDecision(StrictBody):
    space_id: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    accept: bool
    operation_key: str = Field(min_length=1, max_length=200)


class KnowledgePlanRevision(StrictBody):
    space_id: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    topics: list[dict[str, Any]] = Field(min_length=1, max_length=6)
    omitted: list[str] = Field(default_factory=list, max_length=20)
    operation_key: str = Field(min_length=1, max_length=200)


def _runtime(request: Request):
    core = request.app.state.core
    if not core.config.assistant_enabled:
        raise HTTPException(404, "助手未启用")
    return core.assistant_runtime


@router.get("/spaces")
async def list_spaces(request: Request) -> dict[str, Any]:
    return {"spaces": _runtime(request).store.list_spaces()}


@router.get('/spaces/{space_id}')
async def space_detail(space_id: int, request: Request) -> dict:
    runtime = _runtime(request)
    try:
        space = runtime.store.get_space(space_id)
    except KeyError as exc:
        raise HTTPException(404, 'Space 不存在') from exc
    with runtime.store.db.connect() as c:
        space['sources'] = [dict(row) for row in c.execute('SELECT id,folder_title,status FROM favorite_sources ORDER BY sort_order,id')]
        space['selected_videos'] = [dict(row) for row in c.execute('SELECT id,title FROM videos WHERE id IN (SELECT value FROM json_each(?)) ORDER BY id',
            (json.dumps(space['video_ids']),))]
    return {'space':space}


@router.get('/maintenance-activity')
async def maintenance_activity(request: Request, space_id: int = Query(ge=1), limit: int = Query(default=20,ge=1,le=50)) -> dict:
    try:
        return await asyncio.to_thread(_runtime(request).store.maintenance_activity,space_id,limit=limit)
    except KeyError as exc:
        raise HTTPException(404,'Space 不存在') from exc


@router.post("/spaces", status_code=201)
async def create_space(payload: SpaceCreate, request: Request) -> dict[str, Any]:
    _runtime(request).store.mark_user_activity()
    try:
        space = _runtime(request).store.create_space(
            name=payload.name,
            goal=payload.goal,
            source_ids=payload.source_ids,
            video_ids=payload.video_ids,
            all_active=payload.all_active,
            maintenance_mode=payload.maintenance_mode,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"space": space}


@router.patch("/spaces/{space_id}")
async def update_space(space_id: int, payload: SpaceUpdate, request: Request) -> dict[str, Any]:
    _runtime(request).store.mark_user_activity()
    try:
        value = _runtime(request).store.update_space(
            space_id,
            expected_scope_version=payload.expected_scope_version,
            name=payload.name,
            goal=payload.goal,
            source_ids=payload.source_ids,
            video_ids=payload.video_ids,
            all_active=payload.all_active,
            maintenance_mode=payload.maintenance_mode,
        )
    except KeyError as exc:
        raise HTTPException(404, "Space 不存在") from exc
    except AssistantConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"space": value}


@router.post("/threads", status_code=201)
async def create_thread(payload: ThreadCreate, request: Request) -> dict[str, Any]:
    try:
        return {"thread": _runtime(request).store.create_thread(payload.space_id, title=payload.title)}
    except KeyError as exc:
        raise HTTPException(404, "Space 不存在") from exc


@router.get("/threads")
async def list_threads(request: Request, space_id: int = Query(ge=1),
                       limit: int = Query(default=30, ge=1, le=50),
                       before_updated_at: str | None = None,
                       before_id: str | None = None) -> dict[str, Any]:
    try:
        return _runtime(request).store.list_threads(
            space_id=space_id, limit=limit,
            before_updated_at=before_updated_at, before_id=before_id,
        )
    except KeyError as exc:
        raise HTTPException(404, "Space 不存在") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _safe_draft(runtime: Any, run: dict[str, Any]) -> dict[str, Any]:
    draft = run["working_state"].get("answer_draft")
    if not draft:
        return run
    if run["status"] != "running" or draft.get("epoch") != run["run_epoch"]:
        run["working_state"].pop("answer_draft", None)
        return run
    context = runtime.store.run_context(run["id"])
    from shiliu.assistant.tools import AssistantToolRegistry
    registry = AssistantToolRegistry(sources=runtime.sources, memories=runtime.memories,
                                     store=runtime.store, wiki=runtime.wiki)
    refs = run["working_state"].get("context_observation", {}).get("dependency_refs") or []
    if not registry.dependency_refs_valid(refs, int(context["space"]["id"]),
                                         str(context["thread"]["id"]), int(context["space"]["scope_version"])):
        run["working_state"]["answer_draft"] = {"text": "", "status": "invalidated", "epoch": run["run_epoch"]}
    return run


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request) -> StreamingResponse:
    runtime = _runtime(request)
    try:
        runtime.store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(404, "运行不存在") from exc
    async def snapshots():
        prior = None
        while not await request.is_disconnected():
            run = await asyncio.to_thread(lambda: _safe_draft(runtime, runtime.store.get_run(run_id)))
            compact = {key: run.get(key) for key in ("id", "status", "run_epoch", "actions", "step_count", "tool_count", "last_error_code")}
            compact["working_state"] = {key: run["working_state"].get(key) for key in
                                        ("answer_draft", "finish_requested", "task_subset", "task_focus", "model_delivered_read_spans")}
            value = json.dumps({"run": compact}, ensure_ascii=False)
            if value != prior:
                yield f"data: {value}\n\n"
                prior = value
            if run["status"] not in {"queued", "running"}:
                return
            await asyncio.sleep(0.2)
    return StreamingResponse(snapshots(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, request: Request) -> dict[str, Any]:
    try:
        runtime = _runtime(request)
        def snapshot():
            thread = runtime.store.get_thread(thread_id)
            note = thread.get('task_note')
            if note and note.get('usable'):
                from shiliu.assistant.tools import AssistantToolRegistry
                from shiliu.assistant.task_notes import TaskNoteService
                from shiliu.assistant.working_context import context_identity
                registry = getattr(runtime, 'tools', None) or AssistantToolRegistry(
                    sources=runtime.sources, memories=runtime.memories, store=runtime.store, wiki=runtime.wiki)
                space = runtime.store.task_space(thread_id)
                user = next((m for m in reversed(thread['messages']) if m['role'] == 'user'), None)
                identity = context_identity(registry, space, user['content'] if user else '')
                notes = TaskNoteService(runtime.store.db, runtime.memories,
                    source_ref_validator=lambda refs, sid: registry.dependency_refs_valid(
                        refs, sid, thread_id, int(space['scope_version'])),
                    dependency_ref_validator=registry.dependency_refs_valid)
                note['usable'] = notes.checkpoint_for_context(thread_id, space_id=int(space['id']),
                    scope_version=int(space['scope_version']), identity=identity) is not None
                if not note['usable']:
                    note['searched_scope_and_material_refs'] = []
            thread["runs"] = [_safe_draft(runtime, run) for run in thread["runs"]]
            return thread
        thread = await asyncio.to_thread(snapshot)
        return {"thread": thread}
    except KeyError as exc:
        raise HTTPException(404, "对话不存在") from exc


@router.post("/threads/{thread_id}/runs", status_code=202)
async def create_run(thread_id: str, payload: RunCreate, request: Request) -> dict[str, Any]:
    try:
        run = _runtime(request).store.create_run(
            thread_id, text=payload.input, request_id=payload.request_id, answer_message_id=payload.answer_message_id,
            receipt_only=payload.receipt_only
        )
    except KeyError as exc:
        raise HTTPException(404, "对话不存在") from exc
    except AssistantConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"run": run}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> dict[str, Any]:
    try:
        runtime = _runtime(request)
        return {"run": await asyncio.to_thread(_safe_draft, runtime, runtime.store.get_run(run_id))}
    except KeyError as exc:
        raise HTTPException(404, "运行不存在") from exc


@router.get("/runs/{run_id}/events")
async def get_run_events(
    run_id: str, request: Request, after_seq: int = Query(default=0, ge=0)
) -> dict[str, Any]:
    try:
        return {"events": _runtime(request).store.events(run_id, after_seq=after_seq)}
    except KeyError as exc:
        raise HTTPException(404, "运行不存在") from exc


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, request: Request) -> dict[str, Any]:
    try:
        return {"run": _runtime(request).store.cancel_run(run_id)}
    except KeyError as exc:
        raise HTTPException(404, "运行不存在") from exc


@router.post("/runs/{run_id}/resume", status_code=202)
async def resume_run(run_id: str, request: Request) -> dict[str, Any]:
    try:
        return {"run": _runtime(request).store.resume_run(run_id)}
    except KeyError as exc:
        raise HTTPException(404, "运行不存在") from exc
    except AssistantConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/runs/{run_id}/finish", status_code=202)
async def finish_run(run_id: str, request: Request) -> dict[str, Any]:
    try:
        return {"run": _runtime(request).store.request_finish(run_id)}
    except KeyError as exc:
        raise HTTPException(404, "运行不存在") from exc


@router.get("/memories")
async def list_memories(
    request: Request,
    space_id: int | None = Query(default=None, ge=1),
    include_inactive: bool = False,
) -> dict[str, Any]:
    return {
        "memories": _runtime(request).memories.list(
            space_id=space_id, include_inactive=include_inactive
        ),
        "memory_epoch": _runtime(request).memories.current_epoch(),
    }


@router.get("/memory-settings")
async def memory_settings(request: Request) -> dict[str, bool]:
    return {"auto_enabled": _runtime(request).memories.auto_enabled()}


@router.patch("/memory-settings")
async def update_memory_settings(payload: AutoMemorySetting, request: Request) -> dict[str, bool]:
    _runtime(request).store.mark_user_activity()
    return {"auto_enabled": _runtime(request).memories.set_auto_enabled(payload.enabled)}


@router.post("/memories", status_code=201)
async def create_memory(payload: MemoryCreate, request: Request) -> dict[str, Any]:
    _runtime(request).store.mark_user_activity()
    try:
        normalized = " ".join(payload.text.split())
        subject_key = payload.subject_key or (
            "manual_" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
        )
        validity = {
            "valid_from": payload.valid_from, "expires_at": payload.expires_at,
            "validity_note": payload.validity_note,
            "validity_timezone": payload.validity_timezone,
        }
        operation_key = payload.operation_key or new_operation_key("ui-memory")
        value = _runtime(request).memories.save_explicit(
            text=payload.text,
            subject_key=subject_key,
            kind=payload.kind,
            scope_kind=payload.scope_kind,
            scope_id=payload.scope_id,
            operation_key=operation_key,
            pinned=payload.pinned,
            stated_text=payload.text,
            stated_at=utc_now(),
            **validity,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"memory": value, "save_feedback": _runtime(request).memories.creation_feedback(
        value, save_operation_key=operation_key, space_id=payload.scope_id)}


@router.patch("/memories/{memory_id}")
async def update_memory(
    memory_id: str, payload: MemoryUpdate, request: Request
) -> dict[str, Any]:
    _runtime(request).store.mark_user_activity()
    try:
        validity_changes = {
            field: getattr(payload, field)
            for field in ("valid_from", "expires_at", "validity_note", "validity_timezone")
            if field in payload.model_fields_set
        }
        value = _runtime(request).memories.correct(
            memory_id,
            text=payload.text,
            expected_version=payload.expected_version,
            operation_key=payload.operation_key,
            subject_key=payload.subject_key,
            kind=payload.kind,
            stated_text=payload.text,
            stated_at=utc_now(),
            update_time_context=payload.update_time_context,
            **validity_changes,
        )
    except KeyError as exc:
        raise HTTPException(404, "记忆不存在") from exc
    except AssistantConflict as exc:
        current = _runtime(request).memories.get(memory_id)
        raise HTTPException(409, detail={"error": str(exc), "current": current}) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"memory": value}


@router.get("/memory-changes")
async def memory_changes(
    request: Request,
    after_epoch: int = Query(default=0, ge=0),
    space_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    return _runtime(request).memories.changes_since(
        after_epoch, space_id=space_id, limit=limit
    )


@router.post('/memories/{memory_id}/undo-created')
async def undo_created_memory(memory_id: str, payload: MemoryCreationUndo, request: Request) -> dict:
    runtime = _runtime(request)
    runtime.store.get_space(payload.space_id)
    try:
        memory = runtime.memories.get(memory_id)
    except KeyError as exc:
        raise HTTPException(404, '记忆不存在') from exc
    if memory['scope_kind'] != 'user' and str(memory['scope_id']) != str(payload.space_id):
        raise HTTPException(404, '记忆不在当前范围')
    runtime.store.mark_user_activity()
    try:
        return {'memory':runtime.memories.undo_created(memory_id, save_operation_key=payload.save_operation_key,
            expected_version=payload.expected_version, operation_key=payload.operation_key)}
    except (AssistantConflict, ValueError) as exc:
        raise HTTPException(409,str(exc)) from exc


@router.delete("/memories/{memory_id}")
async def forget_memory(
    memory_id: str,
    request: Request,
    expected_version: int = Query(ge=1),
    operation_key: str = Query(min_length=1, max_length=200),
) -> dict[str, Any]:
    _runtime(request).store.mark_user_activity()
    try:
        value = _runtime(request).memories.forget(
            memory_id,
            expected_version=expected_version,
            operation_key=operation_key,
        )
    except KeyError as exc:
        raise HTTPException(404, "记忆不存在") from exc
    except AssistantConflict as exc:
        current = _runtime(request).memories.get(memory_id)
        raise HTTPException(409, detail={"error": str(exc), "current": current}) from exc
    return {"memory": value}


@router.get("/jobs")
async def list_jobs(request: Request, space_id: int | None = Query(default=None,ge=1)) -> dict[str, Any]:
    try:
        return {"jobs": _runtime(request).store.list_jobs(space_id=space_id)}
    except KeyError as exc:
        raise HTTPException(404,'Space 不存在') from exc


@router.post("/jobs/{job_id}/retry", status_code=202)
async def retry_job(job_id: str, request: Request) -> dict[str, Any]:
    try:
        return {"job": _runtime(request).store.retry_job(job_id)}
    except KeyError as exc:
        raise HTTPException(404, "后台任务不存在") from exc
    except AssistantConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/capabilities")
async def capabilities(request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    return {
        "capabilities": runtime.capabilities(),
        "model": request.app.state.core.config.model_for("assistant"),
    }


@router.post("/spaces/{space_id}/bootstrap", status_code=202)
async def bootstrap_space(
    space_id: int, request: Request, limit: int = Query(default=5, ge=1, le=10),
    model_budget: int = Query(default=30, ge=1, le=30), thread_id: str | None = None,
) -> dict[str, Any]:
    _runtime(request).store.mark_user_activity()
    try:
        task_scope = _task_scope(request, space_id, thread_id)
        return {"bootstrap": _runtime(request).wiki.bootstrap_space(space_id, limit=limit, model_budget=model_budget,
                task_subset=sorted(task_scope.video_ids) if task_scope else None)}
    except KeyError as exc:
        raise HTTPException(404, "收藏范围不存在") from exc


def _task_scope(request: Request, space_id: int, thread_id: str | None):
    if not thread_id:
        return None
    runtime = _runtime(request)
    space = runtime.store.task_space(thread_id)
    if int(space["id"]) != space_id:
        raise KeyError(thread_id)
    if not space.get("task_subset"):
        return None
    from shiliu.assistant.sources import SourceScope
    return SourceScope(source_db_ids=frozenset(space["source_ids"]),
                       video_ids=frozenset(space["video_ids"]), all_active=space["all_active"])


@router.get("/wiki-management")
async def wiki_management(request: Request, space_id: int = Query(ge=1), status: str = Query(default="archived", pattern="^(active|archived)$"), thread_id: str | None = None):
    wiki = _runtime(request).wiki
    wiki.store.get_space(space_id)
    with wiki.db.connect() as connection:
        rows = connection.execute("SELECT id FROM assistant_wiki_pages WHERE principal_id=? AND space_id=? AND status=? ORDER BY updated_at DESC", (wiki.principal_id, space_id, status)).fetchall()
    scope = _task_scope(request, space_id, thread_id)
    pages = [wiki.management_page(row[0], space_id=space_id, task_scope=scope) for row in rows]
    return {"pages": [page for page in pages if scope is None or page["blocks"] or page["deleted_blocks"]]}


@router.get("/wiki/{page_id}/management")
async def wiki_management_page(page_id: str, request: Request, space_id: int = Query(ge=1), thread_id: str | None = None):
    try:
        return {"page": _runtime(request).wiki.management_page(page_id, space_id=space_id, task_scope=_task_scope(request, space_id, thread_id))}
    except KeyError as exc:
        raise HTTPException(404, "知识页不存在") from exc


@router.post("/wiki/{page_id}/lifecycle")
async def wiki_lifecycle(page_id: str, payload: WikiLifecycle, request: Request):
    runtime = _runtime(request)
    runtime.store.mark_user_activity()
    try:
        return {"result": runtime.wiki.manage_page(page_id, **payload.model_dump())}
    except KeyError as exc:
        raise HTTPException(404, "知识页或块不存在") from exc
    except (AssistantConflict, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/knowledge-plans/{plan_id}/items/{item_index}")
async def knowledge_item_action(plan_id: str, item_index: int, payload: PlanItemAction, request: Request):
    runtime = _runtime(request)
    runtime.store.mark_user_activity()
    try:
        return {"plan": runtime.wiki.manage_plan_item(plan_id, item_index=item_index, **payload.model_dump())}
    except KeyError as exc:
        raise HTTPException(404, "保存计划不存在") from exc
    except (AssistantConflict, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/knowledge-plans/{plan_id}/repair")
async def knowledge_field_repair(plan_id: str, payload: PlanFieldRepair, request: Request):
    runtime = _runtime(request)
    runtime.store.mark_user_activity()
    try:
        # UI is an explicit user operation, not an automatic model repair or a synthetic message.
        with runtime.store.db.connect() as connection:
            row = connection.execute("SELECT * FROM assistant_knowledge_plans WHERE id=? AND principal_id=? AND space_id=?", (plan_id, runtime.store.principal_id, payload.space_id)).fetchone()
        if row is None:
            raise KeyError(plan_id)
        plan = runtime.wiki._decode_knowledge_plan(dict(row))
        return {"plan": runtime.wiki.repair_discussion_plan(plan_id, space_id=payload.space_id,
            expected_version=payload.expected_version, corrections=payload.corrections,
            request={"source_message_id": plan["source_message_id"]}, repair_count=int(plan["payload"].get("repair_count", 0)), operation_key=payload.operation_key)}
    except KeyError as exc:
        raise HTTPException(404, "保存计划不存在") from exc
    except (AssistantConflict, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/wiki")
async def list_wiki(
    request: Request,
    space_id: int = Query(ge=1),
    query: str = Query(default="", max_length=1000),
    thread_id: str | None = None,
) -> dict[str, Any]:
    try:
        return {"pages": await asyncio.to_thread(_runtime(request).wiki.list_pages, space_id=space_id, query=query, task_scope=_task_scope(request, space_id, thread_id))}
    except KeyError as exc:
        raise HTTPException(404, "收藏范围不存在") from exc


@router.post("/wiki/organize", status_code=202)
async def organize_wiki(payload: WikiOrganize, request: Request) -> dict[str, Any]:
    _runtime(request).store.mark_user_activity()
    try:
        result = _runtime(request).wiki.request_topic(
            space_id=payload.space_id, topic=payload.topic,
            source_refs=payload.source_refs, request_key=f"ui:{payload.request_id}",
        )
    except KeyError as exc:
        raise HTTPException(404, "收藏范围不存在") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"request": result}


@router.get("/knowledge-plans")
async def list_knowledge_plans(request: Request, space_id: int = Query(ge=1), view: str = Query(default="pending", pattern="^(pending|ignored|all)$")) -> dict[str, Any]:
    return {"plans": await asyncio.to_thread(_runtime(request).wiki.list_discussion_plans, space_id=space_id, view=view, lightweight=True)}


@router.get('/knowledge-plans/{plan_id}')
async def get_knowledge_plan(plan_id: str, request: Request, space_id: int = Query(ge=1)) -> dict:
    wiki = _runtime(request).wiki
    wiki.store.get_space(space_id)
    with wiki.db.connect() as c:
        row = c.execute('SELECT * FROM assistant_knowledge_plans WHERE id=? AND principal_id=? AND space_id=?', (plan_id, wiki.principal_id, space_id)).fetchone()
    if row is None:
        raise HTTPException(404, '保存计划不存在')
    # Explicit detail only; list never does these checks.
    return {'plan': await asyncio.to_thread(wiki._present_knowledge_plan, wiki._decode_knowledge_plan(dict(row)))}


@router.get('/knowledge-plans/{plan_id}/sources')
async def knowledge_plan_sources(plan_id: str, request: Request, space_id: int = Query(ge=1),
                                 query: str = Query(default='', max_length=120)) -> dict[str, Any]:
    try:
        wiki = _runtime(request).wiki
        return {'sources': wiki.plan_source_options(plan_id, space_id=space_id, query=query),
                'selected_sources': wiki.plan_selected_source_statuses(plan_id, space_id=space_id)}
    except KeyError as exc:
        raise HTTPException(404, '主题提案不存在') from exc


@router.patch("/knowledge-plans/{plan_id}")
async def revise_knowledge_plan(
    plan_id: str, payload: KnowledgePlanRevision, request: Request
) -> dict[str, Any]:
    _runtime(request).store.mark_user_activity()
    try:
        result = _runtime(request).wiki.revise_discussion_plan(
            plan_id, space_id=payload.space_id, expected_version=payload.expected_version,
            topics=payload.topics, omitted=payload.omitted, operation_key=payload.operation_key,
        )
    except KeyError as exc:
        raise HTTPException(404, "主题提案不存在") from exc
    except AssistantConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"plan": result}


@router.post("/knowledge-plans/{plan_id}/decide")
async def decide_knowledge_plan(
    plan_id: str, payload: KnowledgePlanDecision, request: Request
) -> dict[str, Any]:
    _runtime(request).store.mark_user_activity()
    try:
        result = _runtime(request).wiki.decide_discussion_plan(
            plan_id, space_id=payload.space_id, expected_version=payload.expected_version,
            accept=payload.accept, operation_key=payload.operation_key,
        )
    except KeyError as exc:
        raise HTTPException(404, "主题提案不存在") from exc
    except AssistantConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"plan": result, "save_feedback": _runtime(request).wiki.save_feedback(result)}


@router.get("/wiki/{page_id}")
async def get_wiki(
    page_id: str, request: Request, space_id: int = Query(ge=1), thread_id: str | None = None
) -> dict[str, Any]:
    try:
        return {"page": _runtime(request).wiki.get_page(page_id, space_id=space_id, task_scope=_task_scope(request, space_id, thread_id))}
    except KeyError as exc:
        raise HTTPException(404, "知识页不存在") from exc


@router.patch("/wiki/{page_id}")
async def update_wiki(
    page_id: str, payload: WikiBlockUpdate, request: Request
) -> dict[str, Any]:
    _runtime(request).store.mark_user_activity()
    try:
        current = _runtime(request).wiki.get_page(page_id, space_id=payload.space_id)
        if payload.block_id not in {block["stable_id"] for block in current["blocks"]}:
            raise KeyError(payload.block_id)
        page = _runtime(request).wiki.edit_block(
            page_id,
            block_id=payload.block_id,
            markdown=payload.markdown,
            expected_version=payload.expected_version,
            operation_key=payload.operation_key or new_operation_key("ui-wiki-edit"),
        )
    except KeyError as exc:
        raise HTTPException(404, "知识页或段落不存在") from exc
    except AssistantConflict as exc:
        current = _runtime(request).wiki.get_page(page_id)
        raise HTTPException(409, detail={"error": str(exc), "current": current}) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"page": page}


@router.post("/wiki/{page_id}/notes", status_code=201)
async def add_wiki_note(page_id: str, payload: WikiPersonalNote, request: Request) -> dict[str, Any]:
    _runtime(request).store.mark_user_activity()
    try:
        page = _runtime(request).wiki.add_personal_note(
            page_id, space_id=payload.space_id, text=payload.text,
            expected_version=payload.expected_version,
            operation_key=payload.operation_key or new_operation_key("ui-wiki-note"),
            memory_id=payload.memory_id, memory_version=payload.memory_version,
        )
    except KeyError as exc:
        raise HTTPException(404, "主题不存在") from exc
    except AssistantConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"page": page}


@router.get("/wiki/{page_id}/changes")
async def wiki_changes(
    page_id: str, request: Request, space_id: int = Query(ge=1), management: bool = False
) -> dict[str, Any]:
    try:
        _runtime(request).wiki.get_page(page_id, space_id=space_id, include_hidden=management)
        return {"changes": _runtime(request).wiki.changes(page_id)}
    except KeyError as exc:
        raise HTTPException(404, "知识页不存在") from exc


@router.post("/wiki/{page_id}/revert")
async def revert_wiki(
    page_id: str, payload: WikiRevert, request: Request
) -> dict[str, Any]:
    _runtime(request).store.mark_user_activity()
    try:
        _runtime(request).wiki.get_page(page_id, space_id=payload.space_id)
        page = _runtime(request).wiki.revert(
            page_id,
            target_version=payload.target_version,
            expected_version=payload.expected_version,
            operation_key=payload.operation_key or new_operation_key("ui-wiki-revert"),
        )
    except KeyError as exc:
        raise HTTPException(404, "知识页或版本不存在") from exc
    except AssistantConflict as exc:
        current = _runtime(request).wiki.get_page(page_id, space_id=payload.space_id)
        raise HTTPException(409, detail={"error": str(exc), "current": current}) from exc
    return {"page": page}


@router.post("/wiki-actions/merge")
async def merge_wiki(payload: WikiMerge, request: Request) -> dict[str, Any]:
    _runtime(request).store.mark_user_activity()
    try:
        result = _runtime(request).wiki.merge_pages(
            payload.source_page_id, payload.target_page_id, space_id=payload.space_id,
            source_version=payload.source_version, target_version=payload.target_version,
            operation_key=payload.operation_key or new_operation_key("ui-wiki-merge"),
        )
    except KeyError as exc:
        raise HTTPException(404, "主题不存在") from exc
    except AssistantConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"result": result}


@router.get("/wiki-actions/proposals")
async def wiki_proposals(request: Request, space_id: int = Query(ge=1)) -> dict[str, Any]:
    return {"proposals": _runtime(request).wiki.list_proposals(space_id=space_id)}


@router.post("/wiki-actions/proposals/{proposal_id}/decide")
async def decide_wiki_proposal(
    proposal_id: str, payload: WikiProposalDecision, request: Request
) -> dict[str, Any]:
    _runtime(request).store.mark_user_activity()
    try:
        result = _runtime(request).wiki.decide_proposal(
            proposal_id, accept=payload.accept,
            operation_key=payload.operation_key or new_operation_key("ui-wiki-proposal"),
            space_id=payload.space_id,
        )
    except KeyError as exc:
        raise HTTPException(404, "待确认提案不存在或已过期") from exc
    except AssistantConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"result": result}


def new_operation_key(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex}"
