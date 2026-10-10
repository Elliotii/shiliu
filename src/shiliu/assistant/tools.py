from __future__ import annotations

import json
import hashlib
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from shiliu.assistant.contracts import CollectionReadArgs, CollectionSearchArgs, ToolResult
from shiliu.assistant.dependencies import Context7MCPClient
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.memory_policy import cancels_time, explicit_expiry_has_user_basis, time_phrase
from shiliu.assistant.sources import CollectionSourceService, SourceScope
from shiliu.assistant.store import AssistantRunStore
from shiliu.assistant.wiki import WikiService


def _forbids_knowledge_save(text: str) -> bool:
    return bool(re.search(
        r"(?:不要|别|禁止|不许|无需).{0,12}(?:保存|入页|写入知识|记到知识|写进主题)|(?:别|不要)存",
        text,
    ))


def _confirmation_direction(text: str) -> bool | None:
    if re.search(r"(?:不要|别|不许|禁止).{0,6}(?:确认|同意|提交)", text):
        return None
    if re.search(r"拒绝|取消提案|不要这些主题", text):
        return False
    if re.search(r"确认|同意|就按|照这个|提交提案", text):
        return True
    return None


class MemorySearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=8, ge=1, le=8)


class MemorySaveArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=400)
    subject_key: str = Field(min_length=1, max_length=120)
    kind: str
    scope_kind: str = "space"
    pinned: bool = False
    valid_from: str | None = None
    expires_at: str | None = None
    validity_note: str = Field(default="", max_length=400)
    validity_timezone: str | None = Field(default=None, max_length=80)


class MemoryCorrectArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_id: str
    text: str = Field(min_length=1, max_length=400)
    expected_version: int = Field(ge=1)
    subject_key: str | None = None
    kind: str | None = None
    valid_from: str | None = None
    expires_at: str | None = None
    validity_note: str | None = Field(default=None, max_length=400)
    validity_timezone: str | None = Field(default=None, max_length=80)


class MemoryForgetArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_id: str
    expected_version: int = Field(ge=1)


class RunReadResultArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_ref: str = Field(pattern=r"^(run-result:[^:]+:[^:]+|tool_call_id:[^:]+)$")
    cursor: int | None = Field(default=None, ge=0)
    item_index: int | None = Field(default=None, ge=0)
    field: str | None = Field(default=None, max_length=80)
    start: int = Field(default=0, ge=0)
    max_characters: int = Field(default=6000, ge=1000, le=12000)


class KnowledgeSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=1000)
    limit: int = Field(default=5, ge=1, le=8)


class KnowledgeReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_id: str = Field(min_length=1, max_length=100)
    mode: Literal["overview", "relevant", "block"] = "overview"
    query: str | None = Field(default=None, max_length=200)
    block_id: str | None = Field(default=None, max_length=120)


class KnowledgeOrganizeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: str = Field(min_length=1, max_length=120)
    source_refs: list[str] = Field(min_length=1, max_length=5)


class KnowledgeSavePersonalArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_id: str
    memory_id: str | None = None
    memory_version: int | None = Field(default=None, ge=1)
    text: str = Field(min_length=1, max_length=4000)
    expected_page_version: int = Field(ge=1)


class KnowledgeExternalSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=9, max_length=2000)
    result_ref: str = Field(min_length=1, max_length=200)


class KnowledgeOutcomeBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["source", "analysis", "personal"]
    heading: str = Field(min_length=1, max_length=160)
    markdown: str = Field(min_length=1, max_length=12000)
    applicability: str = Field(default="", max_length=600)
    source_refs: list[str] = Field(default_factory=list, max_length=5)
    memory_id: str | None = None
    memory_version: int | None = Field(default=None, ge=1)
    user_quote: str | None = Field(default=None, max_length=600)
    external_sources: list[KnowledgeExternalSource] = Field(default_factory=list, max_length=3)


class KnowledgeSaveOutcomeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=600)
    blocks: list[KnowledgeOutcomeBlock] = Field(min_length=1, max_length=8)
    expected_version: int | None = Field(default=None, ge=1)


class KnowledgePlanTopic(KnowledgeSaveOutcomeArgs):
    cross_references: list[str] = Field(default_factory=list, max_length=6)
    omitted: list[str] = Field(default_factory=list, max_length=10)


class KnowledgeProposeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topics: list[KnowledgePlanTopic] = Field(min_length=2, max_length=6)
    omitted: list[str] = Field(default_factory=list, max_length=20)


class KnowledgeConfirmArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str
    expected_version: int = Field(ge=1)
    accept: bool = True


class AssistantToolRegistry:
    def __init__(
        self,
        *,
        sources: CollectionSourceService,
        memories: MemoryService,
        store: AssistantRunStore,
        context7: Context7MCPClient | None = None,
        wiki: WikiService | None = None,
    ) -> None:
        self.sources = sources
        self.memories = memories
        self.store = store
        self.context7 = context7
        self.wiki = wiki

    def schemas(self) -> list[dict[str, Any]]:
        values = [
            self._schema("collection_search", "在当前 Space 搜索收藏。metadata 可分页穷尽标题/作者/时间；content 仅为 Top-K 候选，可传最多两个 query_variants，内部每条都实际检索并计入 retrieval_requests，按排名融合去重，不是穷尽搜索。候选卡有 available_views；完整阅读任务可设 require_transcript=true 先筛有可读转写的收藏。", CollectionSearchArgs),
            self._schema("collection_read", "按来源版本读取一个材料视图。query 选相关段落；完整阅读从头沿 next_cursor 顺序分批读到末尾。coverage.read_position 是取回范围，模型是否读到由上下文投影决定。", CollectionReadArgs),
            self._schema("memory_search", "搜索当前有效的用户和 Space 记忆", MemorySearchArgs),
            self._schema("memory_save", "用户明确要求时正式保存个人背景、目标、约束或决定；返回正式回执。若还要求找材料或回答，继续完成其余动作", MemorySaveArgs),
            self._schema("memory_correct", "使用 memory_search 回执或当前有效记忆行中的真实 memory_id 和 version 纠正；不能把展示文字当 ID。若还有其他要求，继续完成", MemoryCorrectArgs),
            self._schema("memory_forget", "使用 memory_search 回执或当前有效记忆行中的真实 memory_id 和 version 遗忘；不能把展示文字当 ID。若还有其他要求，继续完成", MemoryForgetArgs),
            self._schema("run_read_result", "按条目和字段回读当前对话的已保存工具结果；正文用 start 分段，不返回任意 JSON 切片", RunReadResultArgs),
        ]
        if self.wiki is not None:
            values.extend([
                self._schema("knowledge_search", "搜索当前收藏范围内已经整理的主题知识", KnowledgeSearchArgs),
                self._schema("knowledge_read", "读取当前范围内主题页概览、相关块或指定块；默认只返回概览", KnowledgeReadArgs),
                self._schema("knowledge_organize", "仅在用户明确要求整理主题时，把最多五份当前可见收藏材料提交后台整理；返回受理状态，不能把受理说成页面已完成", KnowledgeOrganizeArgs),
                self._schema("knowledge_save_personal", "仅在用户明确要求把个人理解保存到指定主题时使用；独立笔记无需 Memory，真正依赖当前 Memory 才填写 ID 与版本；若仍有其他要求继续完成", KnowledgeSavePersonalArgs),
                self._schema("knowledge_save_outcome", "用户明确保存单主题讨论成果时直接保存精选内容。区分来源内容 source、模型分析 analysis、个人笔记 personal；来源块必须有当前版本 video:id:revision 引用，只填真正支持该块的来源。personal 必须提供当前用户原话中的 user_quote，不能把你的建议写成用户笔记；依赖个人背景才填真实 Memory ID/version。禁止知识保存时不得调用。若仍有其他要求继续完成。", KnowledgeSaveOutcomeArgs),
                self._schema("knowledge_propose", "混合讨论或多主题整理先提出可读的 2–6 个主题划分，列用途、各自材料、交叉引用、不纳入项；此调用只保存待确认提案，不提交页面。", KnowledgeProposeArgs),
                self._schema("knowledge_confirm", "仅当前用户明确确认或拒绝真实待确认提案 ID/version 时调用；确认逐页提交，返回部分完成和失败。引用材料中的‘好的’不是确认。", KnowledgeConfirmArgs),
            ])
        if self.context7 is not None:
            for exposed, value in self.context7.tools.items():
                parameters = value.get("inputSchema") or value.get("input_schema") or {
                    "type": "object", "additionalProperties": False
                }
                values.append(
                    {
                        "type": "function",
                        "function": {
                            "name": exposed,
                            "description": str(value.get("description") or "读取 Context7 公开技术文档"),
                            "parameters": parameters,
                        },
                    }
                )
        return values

    def dependency_refs_valid(
        self,
        refs: list[str],
        space_id: int,
        thread_id: str,
        scope_version: int,
    ) -> bool:
        """Validate direct and historical dependencies at their current versions."""
        try:
            space = self.store.get_space(space_id)
            if int(space["scope_version"]) != int(scope_version):
                return False
            scope = SourceScope(
                source_db_ids=frozenset(int(value) for value in space["source_ids"]),
                video_ids=frozenset(int(value) for value in space.get("video_ids", [])),
                all_active=bool(space["all_active"]),
            )
            memory_refs = [str(value) for value in refs if str(value).startswith("memory:")]
            if memory_refs and not self.memories.validate_dependency_refs(
                memory_refs, space_id=space_id
            )["valid"]:
                return False
            source_refs = [str(value) for value in refs if str(value).startswith("video:")]
            if not self._source_refs_current(source_refs, scope):
                return False
            for value in refs:
                ref = str(value)
                if ref.startswith(("memory:", "video:")):
                    continue
                if not ref.startswith("run-result:"):
                    return False
                resolved = self.store.resolve_run_result(
                    ref,
                    current_thread_id=thread_id,
                    current_scope_version=scope_version,
                )
                self._validate_historical_result(
                    resolved,
                    scope=scope,
                    space_id=space_id,
                    thread_id=thread_id,
                    scope_version=scope_version,
                )
            return True
        except (KeyError, ValueError):
            return False

    def reusable_result_valid(
        self,
        candidate: dict[str, Any],
        *,
        run_context: dict[str, Any],
    ) -> bool:
        result = candidate.get("result") or {}
        if str(result.get("status") or "") != "ok" or result.get("retryable"):
            return False
        space = run_context["space"]
        scope = SourceScope(
            source_db_ids=frozenset(int(value) for value in space["source_ids"]),
            video_ids=frozenset(int(value) for value in space.get("video_ids", [])),
            all_active=bool(space["all_active"]),
        )
        try:
            self._validate_historical_result(
                {
                    "run_id": str(candidate["run_id"]),
                    "call_id": str(candidate["call_id"]),
                    "name": str(candidate["name"]),
                    "result": result,
                    "result_ref": f"run-result:{candidate['run_id']}:{candidate['call_id']}",
                },
                scope=scope,
                space_id=int(space["id"]),
                thread_id=str(run_context["thread"]["id"]),
                scope_version=int(space["scope_version"]),
            )
            return True
        except (KeyError, ValueError):
            return False

    async def execute(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        call_id: str,
        run_context: dict[str, Any],
    ) -> dict[str, Any]:
        space = run_context["space"]
        scope = SourceScope(
            source_db_ids=frozenset(int(value) for value in space["source_ids"]),
            video_ids=frozenset(int(value) for value in space.get("video_ids", [])),
            all_active=bool(space["all_active"]),
        )
        try:
            if name == "collection_search":
                args = CollectionSearchArgs.model_validate(arguments)
                return self.sources.search(
                    call_id=call_id,
                    scope=scope,
                    query=args.query,
                    query_variants=args.query_variants,
                    require_transcript=args.require_transcript,
                    mode=args.mode,
                    cursor=args.cursor,
                    scope_version=int(space["scope_version"]),
                    folder_ids=set(args.folder_ids) if args.folder_ids is not None else None,
                    published_from=args.published_from,
                    published_to=args.published_to,
                    collected_from=args.collected_from,
                    collected_to=args.collected_to,
                    uploader=args.uploader,
                    sort=args.sort,
                    limit=args.limit,
                ).model_dump(mode="json")
            if name == "collection_read":
                args = CollectionReadArgs.model_validate(arguments)
                if args.refresh_metadata:
                    with self.store.db.connect() as connection:
                        job_id = self.store.enqueue_job(
                            connection,
                            kind="metadata_refresh",
                            dedupe_key=f"metadata_refresh:{args.source_ref}:{space['scope_version']}",
                            payload={
                                "source_ref": args.source_ref,
                                "source_ids": sorted(scope.source_db_ids),
                                "video_ids": sorted(scope.video_ids),
                                "all_active": scope.all_active,
                                "space_id": space["id"],
                                "scope_version": space["scope_version"],
                            },
                        )
                    return ToolResult(
                        call_id=call_id,
                        status="partial",
                        summary="元数据刷新已进入持久队列；当前返回已有稳定内容",
                        items=[{"job_id": job_id, "refresh_pending": True}],
                        retryable=True,
                    ).model_dump(mode="json")
                return self.sources.read(
                    call_id=call_id,
                    scope=scope,
                    source_ref=args.source_ref,
                    view=args.view,
                    revision=args.revision,
                    cursor=args.cursor,
                    query=args.query,
                    max_characters=args.max_characters,
                ).model_dump(mode="json")
            if name == "memory_search":
                args = MemorySearchArgs.model_validate(arguments)
                recalled = self.memories.recall_with_status(
                    args.query, space_id=int(space["id"]), limit=args.limit
                )
                items = recalled["items"]
                return ToolResult(
                    call_id=call_id,
                    status="ok" if items else "empty",
                    summary=f"找到 {len(items)} 条当前有效记忆",
                    items=items,
                    dependency_refs=[str(item["dependency_ref"]) for item in items],
                    coverage={
                        "authoritative_store": recalled["authoritative_store"],
                        "semantic_index": recalled["semantic_index"],
                        "memory_epoch": recalled["memory_epoch"],
                    },
                ).model_dump(mode="json")
            if name == "memory_save":
                current_user = self._current_user_message(run_context)
                args = MemorySaveArgs.model_validate(arguments)
                user_words = str(current_user["content"])
                if not any(word in user_words for word in ("记住", "保存我的", "存为记忆", "记下来")):
                    raise ValueError("memory_save_requires_explicit_user_request")
                proposed_time = time_phrase(args.text)
                if proposed_time and proposed_time not in user_words:
                    raise ValueError("memory_time_needs_review")
                scope_id = None if args.scope_kind == "user" else int(space["id"])
                validity: dict[str, Any] = {}
                if args.expires_at is not None:
                    if not explicit_expiry_has_user_basis(user_words, args.expires_at):
                        raise ValueError("memory_time_needs_review")
                    validity = {
                        "expires_at": args.expires_at,
                        "validity_note": f"原话：{user_words[:180]}；明确日期",
                        "validity_timezone": "explicit_offset",
                    }
                result = self.memories.save_explicit(
                    text=args.text,
                    subject_key=args.subject_key,
                    kind=args.kind,
                    scope_kind=args.scope_kind,
                    scope_id=scope_id,
                    operation_key=f"tool:{run_context['run']['id']}:{call_id}",
                    source_message_ids=[current_user["id"]],
                    source_excerpt=current_user["content"][:1000],
                    stated_text=user_words,
                    stated_at=str(current_user["created_at"]),
                    pinned=args.pinned,
                    **validity,
                )
                return ToolResult(
                    call_id=call_id, status="ok", summary="已保存正式记忆", items=[result]
                ).model_dump(mode="json")
            if name == "memory_correct":
                args = MemoryCorrectArgs.model_validate(arguments)
                self._require_memory_in_scope(args.memory_id, int(space["id"]))
                current_user = self._current_user_message(run_context)
                user_words = str(current_user["content"])
                proposed_time = time_phrase(args.text)
                prior_time = time_phrase(str(self.memories.get(args.memory_id)["text"]))
                if proposed_time and proposed_time not in user_words and proposed_time != prior_time:
                    raise ValueError("memory_time_needs_review")
                validity_changes: dict[str, Any] = {}
                if cancels_time(user_words, args.text):
                    if time_phrase(args.text):
                        raise ValueError("memory_time_needs_review")
                    if args.expires_at and explicit_expiry_has_user_basis(user_words, args.expires_at):
                        raise ValueError("memory_time_needs_review")
                    validity_changes = {"valid_from": None, "expires_at": None,
                                        "validity_note": "", "validity_timezone": None}
                elif args.expires_at is not None:
                    if not explicit_expiry_has_user_basis(user_words, args.expires_at):
                        raise ValueError("memory_time_needs_review")
                    validity_changes = {
                        "valid_from": None, "expires_at": args.expires_at,
                        "validity_note": f"原话：{user_words[:180]}；明确日期",
                        "validity_timezone": "explicit_offset",
                    }
                result = self.memories.correct(
                    args.memory_id,
                    text=args.text,
                    expected_version=args.expected_version,
                    operation_key=f"tool:{run_context['run']['id']}:{call_id}",
                    subject_key=args.subject_key,
                    kind=args.kind,
                    source_message_ids=self._memory_mutation_source_message_ids(
                        run_context, args.memory_id, str(current_user["id"])
                    ),
                    source_excerpt=str(current_user["content"])[:1000],
                    stated_text=user_words,
                    stated_at=str(current_user["created_at"]),
                    **validity_changes,
                )
                return ToolResult(
                    call_id=call_id, status="ok", summary="已纠正正式记忆", items=[result]
                ).model_dump(mode="json")
            if name == "memory_forget":
                args = MemoryForgetArgs.model_validate(arguments)
                self._require_memory_in_scope(args.memory_id, int(space["id"]))
                current_user = self._current_user_message(run_context)
                result = self.memories.forget(
                    args.memory_id,
                    expected_version=args.expected_version,
                    operation_key=f"tool:{run_context['run']['id']}:{call_id}",
                    source_message_ids=self._memory_mutation_source_message_ids(
                        run_context, args.memory_id, str(current_user["id"])
                    ),
                )
                return ToolResult(
                    call_id=call_id, status="ok", summary="已忘记该记忆；索引清理已入队", items=[result]
                ).model_dump(mode="json")
            if name == "run_read_result":
                args = RunReadResultArgs.model_validate(arguments)
                resolved = self.store.resolve_run_result(
                    args.result_ref,
                    current_thread_id=str(run_context["thread"]["id"]),
                    current_scope_version=int(space["scope_version"]),
                )
                self._validate_historical_result(
                    resolved,
                    scope=scope,
                    space_id=int(space["id"]),
                    thread_id=str(run_context["thread"]["id"]),
                    scope_version=int(space["scope_version"]),
                )
                result = resolved["result"]
                if args.cursor not in (None, 0):
                    return self._error(call_id, "legacy_cursor_requires_field",
                                       "请用 item_index、field 和 start 回读正文")
                selected_items = result.get("items") or []
                if args.item_index is None:
                    if args.field or args.start:
                        return self._error(call_id, "item_required", "先指定 item_index 再读取字段")
                    if len(json.dumps(result, ensure_ascii=False)) <= args.max_characters:
                        return ToolResult(call_id=call_id, status="ok",
                                          summary="已读取历史工具结果",
                                          items=[result], result_ref=resolved["result_ref"],
                                          dependency_refs=[resolved["result_ref"]]).model_dump(mode="json")
                    selected = [{
                        "item_index": index,
                        "fields": list(item) if isinstance(item, dict) else [],
                        "summary": str(item.get("title") or item.get("summary") or "")[:180]
                        if isinstance(item, dict) else "",
                    } for index, item in enumerate(selected_items[:30])]
                    payload = {"summary": result.get("summary"), "status": result.get("status"),
                               "coverage": result.get("coverage"), "items": selected,
                               "total_items": len(selected_items),
                               "next_cursor": result.get("next_cursor"),
                               "truncated": result.get("truncated"),
                               "source_refs": result.get("source_refs")}
                    if len(json.dumps(payload, ensure_ascii=False)) > args.max_characters:
                        payload["coverage"] = {"detail": "按字段回读"}
                    return ToolResult(call_id=call_id, status="ok", summary="已读取历史结果概览",
                                      items=[payload], result_ref=resolved["result_ref"],
                                      dependency_refs=[resolved["result_ref"]]).model_dump(mode="json")
                if args.item_index >= len(selected_items):
                    return self._error(call_id, "item_out_of_range", "历史结果条目不存在")
                item = selected_items[args.item_index]
                if args.field:
                    value: Any = item
                    for component in args.field.split("."):
                        if not isinstance(value, dict) or component not in value:
                            return self._error(call_id, "field_not_found", "历史结果字段不存在")
                        value = value[component]
                else:
                    if not isinstance(item, dict):
                        value = item
                    else:
                        value = {key: val for key, val in item.items()
                                 if len(json.dumps(val, ensure_ascii=False)) <= 1000}
                if isinstance(value, str):
                    end = min(len(value), args.start + args.max_characters)
                    selected = value[args.start:end]
                    total = len(value)
                else:
                    if args.start:
                        return self._error(call_id, "non_text_offset", "结构化字段不能按字符偏移读取")
                    if len(json.dumps(value, ensure_ascii=False)) > args.max_characters:
                        return self._error(call_id, "field_too_large", "请选择更窄的字段")
                    selected, end, total = value, 0, 0
                return ToolResult(
                    call_id=call_id,
                    status="partial" if end < total else "ok",
                    summary="已按需读取历史工具结果",
                    items=[{
                        "item_index": args.item_index, "field": args.field,
                        "value": selected,
                        "position": {"start": args.start, "end": end, "total": total},
                    }],
                    result_ref=resolved["result_ref"],
                    dependency_refs=[resolved["result_ref"]],
                    truncated=end < total,
                    next_cursor=str(end) if end < total else None,
                ).model_dump(mode="json")
            if name == "knowledge_search":
                if self.wiki is None:
                    return self._error(call_id, "knowledge_unavailable", "知识整理当前不可用")
                args = KnowledgeSearchArgs.model_validate(arguments)
                pages = self.wiki.list_pages(space_id=int(space["id"]), query=args.query)[:args.limit]
                items = [{
                    "page_id": page["id"], "title": page["title"],
                    "summary": page["summary"], "updated_at": page["updated_at"],
                    "availability": page["availability"], "version": page["version"],
                } for page in pages]
                source_refs = sorted({
                    ref for page in pages
                    for ref in self.wiki.history_source_refs(
                        str(page["id"]), space_id=int(space["id"])
                    )
                })
                return ToolResult(
                    call_id=call_id, status="ok" if items else "empty",
                    summary=f"找到 {len(items)} 个当前可见主题页", items=items,
                    source_refs=source_refs,
                ).model_dump(mode="json")
            if name == "knowledge_read":
                if self.wiki is None:
                    return self._error(call_id, "knowledge_unavailable", "知识整理当前不可用")
                args = KnowledgeReadArgs.model_validate(arguments)
                page = self.wiki.get_page(args.page_id, space_id=int(space["id"]))
                all_blocks = list(page.get("blocks") or [])
                blocks = list(all_blocks)
                if args.mode == "block":
                    if not args.block_id:
                        return self._error(call_id, "block_required", "需要指定 block_id")
                    blocks = [block for block in blocks if str(block.get("stable_id")) == args.block_id]
                elif args.mode == "relevant":
                    if not args.query:
                        return self._error(call_id, "query_required", "相关块读取需要 query")
                    terms = [term.casefold() for term in args.query.split() if term]
                    ranked = [(sum(term in json.dumps(block, ensure_ascii=False).casefold()
                                   for term in terms), block) for block in blocks]
                    blocks = [block for score, block in sorted(ranked, key=lambda item: -item[0])
                              if score > 0][:3]
                else:
                    blocks = []
                page = {
                    "id": page["id"], "title": page["title"], "summary": page.get("summary"),
                    "version": page.get("version"), "availability": page.get("availability"),
                    "blocks": [{key: value for key, value in block.items()
                                if key in {"stable_id", "heading", "markdown", "applicability", "assessment", "source_refs", "external_sources", "historical_statement", "validity_note", "expires_at"}}
                               for block in blocks],
                    "available_blocks": [
                        {"id": block.get("stable_id"), "heading": str(block.get("heading") or "")[:100]}
                        for block in all_blocks[:50]
                    ],
                }
                if len(json.dumps(page, ensure_ascii=False)) > 14000:
                    return self._error(call_id, "knowledge_view_too_large", "请指定更窄的知识块")
                source_refs = self.wiki.history_source_refs(
                    str(page["id"]), space_id=int(space["id"])
                )
                return ToolResult(
                    call_id=call_id, status="ok" if (page["blocks"] or
                        (args.mode == "overview" and all_blocks)) else "empty",
                    summary=f"已读取主题页：{page['title']}", items=[page],
                    source_refs=source_refs,
                    dependency_refs=self.wiki.personal_dependency_refs(
                        str(page["id"]), space_id=int(space["id"])
                    ),
                    coverage={"mode": args.mode, "total_blocks": len(all_blocks),
                              "returned_blocks": len(blocks), "version": page.get("version")},
                ).model_dump(mode="json")
            if name == "knowledge_save_personal":
                if self.wiki is None:
                    return self._error(call_id, "knowledge_unavailable", "主题整理当前不可用")
                args = KnowledgeSavePersonalArgs.model_validate(arguments)
                current_user = self._current_user_message(run_context)
                if _forbids_knowledge_save(str(current_user["content"])):
                    return self._error(call_id, "knowledge_save_forbidden", "用户已禁止本次知识保存")
                if not any(token in str(current_user["content"]) for token in
                           ("保存", "记到", "写入", "加入", "更新", "补充")):
                    return self._error(call_id, "explicit_request_required", "需要用户明确要求保存个人理解")
                if args.memory_id is None and args.text not in str(current_user["content"]):
                    return self._error(call_id, "personal_quote_required", "独立个人笔记须来自当前用户原话")
                page = self.wiki.add_personal_note(
                    args.page_id, space_id=int(space["id"]), text=args.text,
                    expected_version=args.expected_page_version,
                    operation_key=f"tool:{run_context['run']['id']}:{call_id}",
                    memory_id=args.memory_id, memory_version=args.memory_version,
                    source_message_id=str(current_user["id"]),
                )
                return ToolResult(
                    call_id=call_id, status="ok", summary="个人理解已保存到主题",
                    items=[{"page_id": page["id"], "version": page["version"]}],
                ).model_dump(mode="json")
            if name in {"knowledge_save_outcome", "knowledge_propose", "knowledge_confirm"}:
                if self.wiki is None:
                    return self._error(call_id, "knowledge_unavailable", "主题整理当前不可用")
                current_user = self._current_user_message(run_context)
                utterance = str(current_user["content"])
                if name != "knowledge_confirm" and _forbids_knowledge_save(utterance):
                    return self._error(call_id, "knowledge_save_forbidden", "用户已禁止本次知识保存")
                if name == "knowledge_save_outcome":
                    args = KnowledgeSaveOutcomeArgs.model_validate(arguments)
                    if not any(token in utterance for token in ("保存", "整理", "写入", "记到", "加入", "更新", "补充")):
                        return self._error(call_id, "explicit_request_required", "需要用户明确要求保存成果")
                    page = self.wiki.save_discussion(
                        space_id=int(space["id"]), title=args.title, purpose=args.purpose,
                        blocks=[item.model_dump(mode="json") for item in args.blocks],
                        expected_version=args.expected_version,
                        source_message_id=str(current_user["id"]),
                        operation_key=f"tool:{run_context['run']['id']}:{call_id}",
                    )
                    return ToolResult(call_id=call_id, status="ok", summary="讨论成果已保存，可打开、编辑或撤销",
                                      items=[{"page_id": page["id"], "title": page["title"],
                                              "version": page["version"]}]).model_dump(mode="json")
                if name == "knowledge_propose":
                    args = KnowledgeProposeArgs.model_validate(arguments)
                    if not any(token in utterance for token in ("整理", "主题", "保存", "拆成", "分成")):
                        return self._error(call_id, "explicit_request_required", "需要用户明确要求整理多个主题")
                    plan = self.wiki.propose_discussion(
                        space_id=int(space["id"]),
                        topics=[item.model_dump(mode="json") for item in args.topics],
                        omitted=args.omitted, source_message_id=str(current_user["id"]),
                        request_key=f"tool:{run_context['run']['id']}:{call_id}",
                    )
                    return ToolResult(call_id=call_id, status="ok", summary="主题划分提案待确认，尚未修改页面",
                                      items=[plan]).model_dump(mode="json")
                args = KnowledgeConfirmArgs.model_validate(arguments)
                direction = _confirmation_direction(utterance)
                if direction is None:
                    return self._error(call_id, "explicit_confirmation_required", "需要当前用户明确选择提案")
                if args.accept != direction or (args.accept and _forbids_knowledge_save(utterance)):
                    return self._error(call_id, "confirmation_direction_mismatch", "提案操作与当前用户选择不一致")
                plan = self.wiki.decide_discussion_plan(
                    args.plan_id, space_id=int(space["id"]), expected_version=args.expected_version,
                    accept=args.accept, operation_key=f"tool:{run_context['run']['id']}:{call_id}",
                )
                return ToolResult(call_id=call_id, status="ok", summary=f"提案处理：{plan['status']}",
                                  items=[plan]).model_dump(mode="json")
            if name == "knowledge_organize":
                if self.wiki is None:
                    return self._error(call_id, "knowledge_unavailable", "主题整理当前不可用")
                args = KnowledgeOrganizeArgs.model_validate(arguments)
                current_user = self._current_user_message(run_context)
                request_text = str(current_user["content"])
                if _forbids_knowledge_save(request_text):
                    return self._error(call_id, "knowledge_save_forbidden", "用户已禁止本次知识保存")
                if not any(token in request_text for token in ("整理", "主题", "专题", "归纳", "补充到")):
                    return self._error(call_id, "explicit_request_required", "只有明确整理请求才能创建主题")
                accepted = self.wiki.request_topic(
                    space_id=int(space["id"]), topic=args.topic,
                    source_refs=args.source_refs,
                    request_key=(
                        f"tool:{current_user['id']}:" + hashlib.sha256(
                            json.dumps([args.topic, sorted(args.source_refs)], ensure_ascii=False).encode("utf-8")
                        ).hexdigest()[:20]
                    ),
                    source_message_id=str(current_user["id"]),
                )
                summaries = {
                    "accepted": "主题整理已受理，完成后可在主题页查看",
                    "waiting_budget": "主题整理已记录，等待后台额度后继续",
                    "already_available": "该请求对应的主题内容已可查看",
                    "no_change": "材料未形成新的主题内容，可继续查看原材料",
                }
                return ToolResult(
                    call_id=call_id, status="ok", summary=summaries[accepted["status"]],
                    items=[accepted],
                ).model_dump(mode="json")
            if name.startswith("context7_"):
                if self.context7 is None:
                    return self._error(call_id, "context7_unavailable", "Context7 当前未连接")
                self._validate_context7_arguments(arguments)
                payload = await self.context7.call(name, arguments)
                return ToolResult(
                    call_id=call_id,
                    status="ok",
                    summary="Context7 公开技术文档读取成功",
                    items=[{"response": payload}],
                ).model_dump(mode="json")
            return self._error(call_id, "tool_not_allowed", "工具未获授权")
        except ValidationError as exc:
            return self._error(call_id, "invalid_arguments", str(exc)[:800], status="invalid_arguments")
        except ValueError as exc:
            if str(exc) in {
                "result_outside_current_scope", "historical_result_stale",
                "historical_result_dependencies_missing",
            }:
                return self._error(
                    call_id,
                    "result_outside_current_scope",
                    "历史结果的记忆、知识或收藏范围依赖已变化，请重新查询",
                )
            return self._error(call_id, "invalid_arguments", str(exc)[:500])
        except Exception as exc:
            code = str(getattr(exc, "code", None) or type(exc).__name__)
            retryable = bool(getattr(exc, "retryable", False))
            return ToolResult(
                call_id=call_id,
                status="unavailable",
                summary=f"工具调用失败：{str(exc)[:500]}",
                error_code=code,
                retryable=retryable,
            ).model_dump(mode="json")

    def _validate_historical_result(
        self,
        resolved: dict[str, Any],
        *,
        scope: SourceScope,
        space_id: int,
        thread_id: str,
        scope_version: int,
        visited: set[tuple[str, str]] | None = None,
    ) -> None:
        seen = visited if visited is not None else set()
        identity = (str(resolved["run_id"]), str(resolved["call_id"]))
        if identity in seen or len(seen) >= 8:
            raise ValueError("historical_result_stale")
        seen.add(identity)
        result = resolved["result"]
        name = str(resolved["name"])
        if name == "knowledge_organize":
            items = result.get("items") or []
            if str(result.get("status")) != "ok" or len(items) != 1:
                raise ValueError("historical_result_stale")
            item = items[0]
            job_ids = item.get("job_ids") if isinstance(item, dict) else None
            if (item.get("status") not in {"accepted", "waiting_budget", "already_available", "no_change"}
                    or not isinstance(job_ids, list)
                    or not 1 <= len(job_ids) <= 5):
                raise ValueError("historical_result_stale")
            with self.store.db.connect() as connection:
                rows = connection.execute(
                    f"SELECT id,kind,payload_json FROM assistant_jobs WHERE id IN ({','.join('?' for _ in job_ids)})",
                    job_ids,
                ).fetchall()
            if len(rows) != len(job_ids) or any(
                row["kind"] != "source_reconcile" or
                int(json.loads(row["payload_json"] or "{}").get("space_id") or 0) != space_id or
                str(json.loads(row["payload_json"] or "{}").get("task_topic") or "") != str(item.get("topic") or "")
                for row in rows
            ):
                raise ValueError("historical_result_stale")
            return
        if name == "memory_forget":
            items = result.get("items") or []
            if str(result.get("status")) != "ok" or len(items) != 1:
                raise ValueError("historical_result_stale")
            item = items[0]
            if not isinstance(item, dict) or item.get("status") != "forgotten":
                raise ValueError("historical_result_stale")
            if item.get("text") or item.get("source_excerpt"):
                raise ValueError("historical_result_stale")
            memory_id = str(item.get("id") or "")
            version = item.get("version")
            if not memory_id or not isinstance(version, int):
                raise ValueError("historical_result_dependencies_missing")
            if not self.memories.forget_receipt_valid(
                operation_key=f"tool:{resolved['run_id']}:{resolved['call_id']}",
                memory_id=memory_id,
                version=version,
                space_id=space_id,
            ):
                raise ValueError("historical_result_stale")
            return
        declared_refs = [str(value) for value in result.get("dependency_refs") or []]
        declared_memory_refs = [
            value for value in declared_refs if value.startswith("memory:")
        ]
        if declared_memory_refs and not self.memories.validate_dependency_refs(
            declared_memory_refs, space_id=space_id
        )["valid"]:
            raise ValueError("historical_result_stale")
        declared_source_refs = [
            value for value in declared_refs if value.startswith("video:")
        ]
        if declared_source_refs and not self._source_refs_current(
            declared_source_refs, scope
        ):
            raise ValueError("historical_result_stale")
        nested_refs = [
            value for value in declared_refs if value.startswith("run-result:")
        ]
        known_refs = set(declared_memory_refs + declared_source_refs + nested_refs)
        if any(value not in known_refs for value in declared_refs):
            raise ValueError("historical_result_dependencies_missing")
        for dependency_ref in nested_refs:
            dependency = self.store.resolve_run_result(
                dependency_ref,
                current_thread_id=thread_id,
                current_scope_version=scope_version,
            )
            self._validate_historical_result(
                dependency,
                scope=scope,
                space_id=space_id,
                thread_id=thread_id,
                scope_version=scope_version,
                visited=seen,
            )
        if name == "run_read_result":
            if not declared_refs:
                raise ValueError("historical_result_dependencies_missing")
            return
        source_refs = result.get("source_refs") or []
        if name == "collection_read" and result.get("items") and not source_refs:
            raise ValueError("historical_result_dependencies_missing")
        if not self._source_refs_current(source_refs, scope):
            raise ValueError("result_outside_current_scope")
        if name.startswith("memory_"):
            memory_refs: list[str] = []
            for item in result.get("items") or []:
                memory_id = item.get("id") if isinstance(item, dict) else None
                if not memory_id:
                    continue
                if item.get("version") is None:
                    raise ValueError("historical_result_dependencies_missing")
                memory_refs.append(f"memory:{memory_id}:{int(item['version'])}")
            if memory_refs and not self.memories.validate_dependency_refs(
                memory_refs, space_id=space_id
            )["valid"]:
                raise ValueError("historical_result_stale")
        if name in {"knowledge_search", "knowledge_read"}:
            if name == "knowledge_search":
                search_args = KnowledgeSearchArgs.model_validate(resolved.get("arguments") or {})
                fresh_pages = self.wiki.list_pages(space_id=space_id, query=search_args.query)[:search_args.limit]
                prior_ids = [str(item.get("page_id") or "") for item in result.get("items") or []]
                if prior_ids != [str(page["id"]) for page in fresh_pages]:
                    raise ValueError("historical_result_stale")
            pages: list[tuple[str, int]] = []
            for item in result.get("items") or []:
                if not isinstance(item, dict):
                    raise ValueError("historical_result_stale")
                page_id = item.get("page_id") or item.get("id")
                version = item.get("version")
                if not page_id or version is None:
                    raise ValueError("historical_result_dependencies_missing")
                pages.append((str(page_id), int(version)))
            current_refs: set[str] = set()
            current_memory_refs: set[str] = set()
            for page_id, version in pages:
                page = self.wiki.get_page(page_id, space_id=space_id) if self.wiki else None
                if (page is None or str(page["id"]) != page_id or not page["blocks"] or
                        int(page["version"]) != version):
                    raise ValueError("historical_result_stale")
                prior_item = next(item for item in result.get("items") or []
                                  if isinstance(item, dict) and
                                  str(item.get("page_id") or item.get("id")) == page_id)
                if name == "knowledge_read":
                    visible_keys = {"stable_id", "heading", "markdown", "applicability",
                                    "assessment", "source_refs"}
                    current_blocks = {json.dumps({key: value for key, value in block.items()
                                                  if key in visible_keys},
                                                 sort_keys=True, ensure_ascii=False)
                                      for block in page["blocks"]}
                    prior_blocks = prior_item.get("blocks") or []
                    if (any(json.dumps(block, sort_keys=True, ensure_ascii=False)
                            not in current_blocks for block in prior_blocks)
                            or str(prior_item.get("summary") or "") != str(page["summary"] or "")):
                        raise ValueError("historical_result_stale")
                if name == "knowledge_search" and str(prior_item.get("summary") or "") != str(page["summary"] or ""):
                    raise ValueError("historical_result_stale")
                current_refs.update(
                    self.wiki.history_source_refs(page_id, space_id=space_id)
                )
                if name == "knowledge_read":
                    current_memory_refs.update(self.wiki.personal_dependency_refs(
                        page_id, space_id=space_id
                    ))
            if set(str(value) for value in source_refs) != current_refs:
                raise ValueError("historical_result_stale")
            if name == "knowledge_read" and set(declared_memory_refs) != current_memory_refs:
                raise ValueError("historical_result_stale")

    def _source_refs_current(self, source_refs: list[str], scope: SourceScope) -> bool:
        refs = [str(value) for value in source_refs]
        if not self.sources.source_refs_visible(refs, scope):
            return False
        versioned: dict[int, str] = {}
        for ref in refs:
            parts = ref.split(":", 2)
            if len(parts) == 3 and parts[0] == "video" and parts[1].isdigit():
                versioned[int(parts[1])] = parts[2]
        if not versioned:
            return True
        placeholders = ",".join("?" for _ in versioned)
        with self.store.db.connect() as connection:
            rows = connection.execute(
                f"SELECT video_id,current_revision FROM assistant_source_heads "
                f"WHERE video_id IN ({placeholders})",
                list(versioned),
            ).fetchall()
        current = {int(row["video_id"]): str(row["current_revision"]) for row in rows}
        return all(current.get(video_id) == revision for video_id, revision in versioned.items())

    @staticmethod
    def _schema(name: str, description: str, model: type[BaseModel]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": model.model_json_schema(),
            },
        }

    def _require_memory_in_scope(self, memory_id: str, space_id: int) -> None:
        memory = self.memories.get(memory_id)
        if memory["scope_kind"] == "user":
            return
        if memory["scope_kind"] != "space" or str(memory["scope_id"]) != str(space_id):
            raise ValueError("memory_outside_current_scope")

    @staticmethod
    def _memory_mutation_source_message_ids(
        run_context: dict[str, Any], memory_id: str, current_message_id: str
    ) -> list[str]:
        """Recover user messages for prior explicit mutations of one memory."""
        mutation_runs: set[str] = set()
        for message in run_context["thread"]["messages"]:
            if message.get("role") != "tool" or not message.get("run_id"):
                continue
            try:
                payload = json.loads(message.get("provider_payload_json") or "{}")
                result = json.loads(message.get("content") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if payload.get("name") not in {"memory_save", "memory_correct", "memory_forget"}:
                continue
            if any(
                isinstance(item, dict) and str(item.get("id") or "") == memory_id
                for item in result.get("items") or []
            ):
                mutation_runs.add(str(message["run_id"]))
        values = [current_message_id]
        values.extend(
            str(message["id"])
            for message in run_context["thread"]["messages"]
            if message.get("role") == "user"
            and str(message.get("run_id") or "") in mutation_runs
        )
        return list(dict.fromkeys(values))

    @staticmethod
    def _current_user_message(run_context: dict[str, Any]) -> dict[str, Any]:
        run_id = run_context["run"]["id"]
        values = [
            item
            for item in run_context["thread"]["messages"]
            if item["role"] == "user" and item["run_id"] == run_id
        ]
        if not values:
            raise RuntimeError("current_user_message_missing")
        return values[-1]

    @staticmethod
    def _validate_context7_arguments(arguments: dict[str, Any]) -> None:
        encoded = json.dumps(arguments, ensure_ascii=False)
        if len(encoded) > 4000 or "video:" in encoded or "字幕" in encoded:
            raise ValueError("context7_query_contains_private_or_oversized_material")

    @staticmethod
    def _error(call_id: str, code: str, summary: str, *, status: str = "unavailable") -> dict[str, Any]:
        return ToolResult(
            call_id=call_id,
            status=status,  # type: ignore[arg-type]
            summary=summary,
            error_code=code,
        ).model_dump(mode="json")
