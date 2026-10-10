from __future__ import annotations

import hashlib
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
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
    operation_key: str = Field(min_length=1, max_length=200)
    subject_key: str | None = None
    kind: str | None = None
    valid_from: str | None = None
    expires_at: str | None = None
    validity_note: str | None = Field(default=None, max_length=400)
    validity_timezone: str | None = Field(default=None, max_length=80)


class AutoMemorySetting(StrictBody):
    enabled: bool


class WikiBlockUpdate(StrictBody):
    space_id: int = Field(ge=1)
    block_id: str = Field(min_length=1, max_length=100)
    markdown: str = Field(min_length=1, max_length=20000)
    expected_version: int = Field(ge=1)
    operation_key: str | None = Field(default=None, min_length=1, max_length=200)


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
    topics: list[dict[str, Any]] = Field(min_length=2, max_length=6)
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


@router.post("/spaces", status_code=201)
async def create_space(payload: SpaceCreate, request: Request) -> dict[str, Any]:
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


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, request: Request) -> dict[str, Any]:
    try:
        return {"thread": _runtime(request).store.get_thread(thread_id)}
    except KeyError as exc:
        raise HTTPException(404, "对话不存在") from exc


@router.post("/threads/{thread_id}/runs", status_code=202)
async def create_run(thread_id: str, payload: RunCreate, request: Request) -> dict[str, Any]:
    try:
        run = _runtime(request).store.create_run(
            thread_id, text=payload.input, request_id=payload.request_id
        )
    except KeyError as exc:
        raise HTTPException(404, "对话不存在") from exc
    except AssistantConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"run": run}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> dict[str, Any]:
    try:
        return {"run": _runtime(request).store.get_run(run_id)}
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
    return {"auto_enabled": _runtime(request).memories.set_auto_enabled(payload.enabled)}


@router.post("/memories", status_code=201)
async def create_memory(payload: MemoryCreate, request: Request) -> dict[str, Any]:
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
        value = _runtime(request).memories.save_explicit(
            text=payload.text,
            subject_key=subject_key,
            kind=payload.kind,
            scope_kind=payload.scope_kind,
            scope_id=payload.scope_id,
            operation_key=payload.operation_key or new_operation_key("ui-memory"),
            pinned=payload.pinned,
            stated_text=payload.text,
            stated_at=utc_now(),
            **validity,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"memory": value}


@router.patch("/memories/{memory_id}")
async def update_memory(
    memory_id: str, payload: MemoryUpdate, request: Request
) -> dict[str, Any]:
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
            source_message_ids=[],
            source_excerpt="",
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


@router.delete("/memories/{memory_id}")
async def forget_memory(
    memory_id: str,
    request: Request,
    expected_version: int = Query(ge=1),
    operation_key: str = Query(min_length=1, max_length=200),
) -> dict[str, Any]:
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
async def list_jobs(request: Request) -> dict[str, Any]:
    return {"jobs": _runtime(request).store.list_jobs()}


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
    model_budget: int = Query(default=30, ge=1, le=30),
) -> dict[str, Any]:
    try:
        return {"bootstrap": _runtime(request).wiki.bootstrap_space(space_id, limit=limit, model_budget=model_budget)}
    except KeyError as exc:
        raise HTTPException(404, "收藏范围不存在") from exc


@router.get("/wiki")
async def list_wiki(
    request: Request,
    space_id: int = Query(ge=1),
    query: str = Query(default="", max_length=1000),
) -> dict[str, Any]:
    try:
        return {"pages": _runtime(request).wiki.list_pages(space_id=space_id, query=query)}
    except KeyError as exc:
        raise HTTPException(404, "收藏范围不存在") from exc


@router.post("/wiki/organize", status_code=202)
async def organize_wiki(payload: WikiOrganize, request: Request) -> dict[str, Any]:
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
async def list_knowledge_plans(request: Request, space_id: int = Query(ge=1)) -> dict[str, Any]:
    return {"plans": _runtime(request).wiki.list_discussion_plans(space_id=space_id)}


@router.patch("/knowledge-plans/{plan_id}")
async def revise_knowledge_plan(
    plan_id: str, payload: KnowledgePlanRevision, request: Request
) -> dict[str, Any]:
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
    try:
        result = _runtime(request).wiki.decide_discussion_plan(
            plan_id, space_id=payload.space_id, expected_version=payload.expected_version,
            accept=payload.accept, operation_key=payload.operation_key,
        )
    except KeyError as exc:
        raise HTTPException(404, "主题提案不存在") from exc
    except AssistantConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"plan": result}


@router.get("/wiki/{page_id}")
async def get_wiki(
    page_id: str, request: Request, space_id: int = Query(ge=1)
) -> dict[str, Any]:
    try:
        return {"page": _runtime(request).wiki.get_page(page_id, space_id=space_id)}
    except KeyError as exc:
        raise HTTPException(404, "知识页不存在") from exc


@router.patch("/wiki/{page_id}")
async def update_wiki(
    page_id: str, payload: WikiBlockUpdate, request: Request
) -> dict[str, Any]:
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
    page_id: str, request: Request, space_id: int = Query(ge=1)
) -> dict[str, Any]:
    try:
        _runtime(request).wiki.get_page(page_id, space_id=space_id)
        return {"changes": _runtime(request).wiki.changes(page_id)}
    except KeyError as exc:
        raise HTTPException(404, "知识页不存在") from exc


@router.post("/wiki/{page_id}/revert")
async def revert_wiki(
    page_id: str, payload: WikiRevert, request: Request
) -> dict[str, Any]:
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
