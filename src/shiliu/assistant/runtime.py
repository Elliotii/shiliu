from __future__ import annotations

from shiliu.assistant.pg_store import PgAssistantRunStore

from shiliu.storage.dto import json_object

import asyncio
import json
import hashlib
import logging
import os
from pathlib import Path
import re
import threading
import time
import uuid
from typing import Any, Callable, Literal, TypedDict
from types import SimpleNamespace

from langgraph.graph import END, START, StateGraph

from shiliu.assistant.context import ContextBudgetExceeded
from shiliu.assistant.working_context import WorkingContextComposer, WorkingContextCandidate
from shiliu.assistant.compaction import plan_compaction, checkpoint_proposal
from shiliu.assistant.dependencies import Context7MCPClient
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.provider import AssistantModelProvider, ModelTurn, NativeToolCall
from shiliu.assistant.sources import CollectionSourceService, SourceScope
from shiliu.assistant.runtime_contract import AssistantConflict, ModelBudgetWait, ExecutionBudgetExceeded
from shiliu.assistant.task_notes import TaskNoteService
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.wiki import MaintenanceBudgetExceeded, MaintenanceYield, WikiService
from shiliu.storage.fences import CoordinationConflict
from shiliu.storage.scheduler import guard_job
from shiliu.domain import PipelineError
from shiliu.db import utc_now
from shiliu.config import (ASSISTANT_MODEL_DISPATCH_LIMIT, ASSISTANT_TOOL_EXECUTION_LIMIT, ASSISTANT_TOKEN_LIMIT, ASSISTANT_FINAL_SECONDS)


logger = logging.getLogger(__name__)


FINAL_INSTRUCTION = ("现在结束探索。只据本次已完成且有效的读取给出可证实的结论、实际覆盖范围、缺口和下一步。"
                     "不得调用工具或新写入；未完成的任务明确写为部分结果。")

class ExecutionState(TypedDict):
    run_id: str
    epoch: int
    step_count: int
    tool_count: int
    usage: dict[str, Any]
    route: Literal["model", "tools", "final", "stopped"]
    turn: ModelTurn | None
    memory_restart_count: int
    step_base: int
    tool_base: int
    context_metadata: dict[str, Any]
    replay_call_ids: list[str]
    completion_origin: str
    receipt_pages: list[dict[str, Any]]


class AssistantExecutionGraph:
    def __init__(
        self,
        *,
        store: PgAssistantRunStore,
        memories: MemoryService,
        tools: AssistantToolRegistry,
        provider_factory: Callable[[], AssistantModelProvider],
        max_steps: int = ASSISTANT_MODEL_DISPATCH_LIMIT,
        max_tool_calls: int = ASSISTANT_TOOL_EXECUTION_LIMIT,
        recover_legacy: bool = True,
    ) -> None:
        self.store = store
        if recover_legacy:
            self.store.freeze_legacy_recovery_calls()
            self.store.freeze_legacy_recovery_calls(stage="w1")
        self.memories = memories
        self.tools = tools
        self.provider_factory = provider_factory
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.dependency_ref_validator = getattr(
            self.tools, "dependency_refs_valid", None
        )
        self.task_notes = TaskNoteService(
            store.db,
            memories,
            source_ref_validator=self._source_refs_valid,
            dependency_ref_validator=self.dependency_ref_validator,
        )
        self.composer = WorkingContextComposer(store=store, tools=tools, task_notes=self.task_notes)
        self.compaction_soft_target = 32000
        self.compiled = self._build().compile()

    def _source_refs_valid(self, refs: list[str], space_id: int) -> bool:
        source_service = getattr(self.tools, "sources", None)
        if source_service is None:
            return True
        space = self.store.get_space(space_id)
        scope = SourceScope(
            source_db_ids=frozenset(int(value) for value in space["source_ids"]),
            video_ids=frozenset(int(value) for value in space["video_ids"]),
            all_active=bool(space["all_active"]),
        )
        if not source_service.source_refs_visible(refs, scope):
            return False
        versioned: dict[int, str] = {}
        for ref in refs:
            parts = str(ref).split(":", 2)
            if len(parts) == 3 and parts[0] == "video" and parts[1].isdigit():
                versioned[int(parts[1])] = parts[2]
        if not versioned:
            return True
        with self.store.db.connect() as connection:
            rows = connection.execute(
                "SELECT video_id,current_revision FROM assistant_source_heads WHERE workspace_id=%s AND principal_id=%s AND video_id=ANY(%s)",
                (self.store.context.workspace_id,self.store.principal_id,list(versioned)),
            ).fetchall()
        current = {int(row["video_id"]): str(row["current_revision"]) for row in rows}
        return all(current.get(video_id) == revision for video_id, revision in versioned.items())

    async def run(self, run: dict[str, Any]) -> None:
        self.store.initialize_execution_budget(str(run["id"]), epoch=int(run["run_epoch"]),
                                               model_limit=self.max_steps, tool_limit=self.max_tool_calls)
        run = self.store.get_run(str(run["id"]))
        working = run["working_state"]
        state: ExecutionState = {
            "run_id": str(run["id"]),
            "epoch": int(run["run_epoch"]),
            "step_count": int(run["step_count"]),
            "tool_count": max(
                int(run["tool_count"]),
                self.store.completed_tool_message_count(str(run["id"])),
            ),
            "usage": dict(run["usage"]),
            "route": "model",
            "turn": None,
            "memory_restart_count": 0,
            "step_base": int(working.get("segment_step_base", 0)),
            "tool_base": int(working.get("segment_tool_base", 0)),
            "context_metadata": dict(working.get("context_observation") or {}),
            "replay_call_ids": [],
        }
        # Every store mutation reached while this run executes inherits the
        # immutable epoch fence, including calls crossing asyncio.to_thread.
        with self.store.tool_execution_scope(state["run_id"], state["epoch"]):
            await self.compiled.ainvoke(state, config={"recursion_limit": 130})

    def _build(self) -> StateGraph:
        graph = StateGraph(ExecutionState)
        graph.add_node("recover", self._recover)
        graph.add_node("model", self._model)
        graph.add_node("tools", self._tools)
        graph.add_node("final", self._final)
        graph.add_edge(START, "recover")
        graph.add_conditional_edges(
            "recover", self._route_after_tools,
            {"model": "model", "tools": "tools", "final": "final", "stopped": END},
        )
        graph.add_conditional_edges(
            "model", self._route_after_model,
            {"tools": "tools", "final": "final", "stopped": END},
        )
        graph.add_conditional_edges(
            "tools", self._route_after_tools,
            {"model": "model", "final": "final", "stopped": END},
        )
        graph.add_conditional_edges(
            "final", self._route_after_final,
            {"model": "model", "stopped": END},
        )
        return graph

    @staticmethod
    def _dispatch_request_hash(request: Any) -> str:
        body=getattr(request,"body",request)
        encoded=json.dumps(body,sort_keys=True,ensure_ascii=False,separators=(",",":"),default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    async def _recover(self, state: ExecutionState) -> ExecutionState:
        current = self.store.get_run(state["run_id"])
        if current["status"] != "running" or current["run_epoch"] != state["epoch"]:
            return {**state, "route": "stopped"}
        if current["working_state"].get("finish_requested"):
            return await self._finish_with_available(state, reason="user_requested")
        pending = self.store.pending_tool_batch(state["run_id"])
        if not pending:
            return {**state, "route": "model"}
        try:
            calls = [
                NativeToolCall(
                    call_id=str(call["id"]),
                    name=str(call["function"]["name"]),
                    arguments=json.loads(call["function"].get("arguments") or "{}"),
                )
                for call in pending
            ]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.store.fail_run(
                state["run_id"], code="persisted_tool_call_invalid",
                message="中断前的工具参数损坏，无法安全恢复",
            )
            return {**state, "route": "stopped"}
        return {
            **state, "route": "tools", "replay_call_ids": [call.call_id for call in calls],
            "turn": ModelTurn(text="", tool_calls=calls),
        }

    async def _finish_with_available(self, state: ExecutionState, *, reason: str) -> ExecutionState:
        """Use the reserved final call once; never launch another business action."""
        if not self._run_epoch_active(state):
            return {**state, "route": "stopped"}
        context = self.store.run_context(state["run_id"])
        try:
            provider = self.provider_factory()
            candidate = await self._prepare_dispatch(state, provider=provider, final=True,
                suffix=FINAL_INSTRUCTION)
            metadata = candidate.metadata
            self.store.save_context_observation(state['run_id'], epoch=state['epoch'], metadata=metadata)
            reservation = self.store.reserve_model_request(lane="foreground", request_limit=10000,
                run_id=state["run_id"],request_hash=self._dispatch_request_hash(candidate.request))
            try:
                control, turn = await self._wait_for_model(state, lambda call_id: self._provider_turn(provider, state, call_id=call_id,
                    candidate=candidate, allow_finish=True),
                    timeout=min(ASSISTANT_FINAL_SECONDS, self.store.execution_remaining(state["run_id"], final=True)), ignore_finish=True,
                    budget_date=str(reservation["budget_date"]),
                    dispatch_id=str(reservation["dispatch_id"]),
                    input_tokens=candidate.request.input_tokens, output_tokens=candidate.budget.output_tokens)
                if control == "cancelled":
                    return {**state, "route": "stopped"}
                if control == "timeout":
                    raise TimeoutError("final_answer_timeout")
                assert turn is not None
                if turn.tool_calls or turn.finish_reason != 'stop':
                    raise ValueError("finalizer_returned_tool_calls")
                self.store.confirm_model_delivery(
                    state["run_id"], epoch=state["epoch"],
                    spans=metadata.get("delivered_read_spans") or [],
                    materials=metadata.get("material_projection") or [],
                    message_ids=candidate.message_ids, context_revision=candidate.state["revision"])
            except ExecutionBudgetExceeded:
                self.store.fail_run(state["run_id"], code="execution_budget_exhausted", message="本段执行额度已用完，已保留进度；可主动 Continue")
                return {**state, "route": "stopped"}
            except Exception:
                turn = ModelTurn(text=self._fallback_progress(context, reason=reason))
        except Exception:
            metadata = {"scope_version": context["space"]["scope_version"],
                        "observed_memory_epoch": self.store.current_memory_epoch(),
                        "dependency_refs": [], "task_note_version": None}
            turn = ModelTurn(text=self._fallback_progress(context, reason=reason))
        if not self._run_epoch_active(state):
            return {**state, "route": "stopped"}
        return {**state, "route": "final", "turn": turn, "usage": self.store.get_run(state["run_id"])["usage"],
                "context_metadata": metadata, "step_count": state["step_count"] + 1}

    @staticmethod
    def _fallback_progress(context: dict[str, Any], *, reason: str) -> str:
        messages = context["thread"].get("messages") or []
        reads = [item for item in messages if item.get("role") == "tool" and
                 json_object(item.get("provider_payload_json") or "{}").get("name") == "collection_read"]
        latest = next((str(item.get("content") or "") for item in reversed(messages)
                       if item.get("role") == "user"), "当前任务")
        return (f"这次已停止探索，当前请求是：{latest[:180]}。已完成 {len(reads)} 次材料读取；"
                "这只是读取次数，不能据此断定已逐篇核对。模型收尾暂不可用，"
                "因此我不能可靠地给出内容结论。已完成记录仍保留，可以继续未完成项。")

    @staticmethod
    def _discovery_request(text: str) -> tuple[bool, list[str], bool]:
        from shiliu.assistant.tools import _direct_knowledge_save_requested
        stripped = text.strip()
        operation_only = not re.search(r"查找|搜索|检索|研究|比较|回答|有哪些|如何", stripped)
        if (re.fullmatch(r"(?:(?:你好|您好|嗨|哈喽|谢谢|感谢|辛苦了|再见|早上好|晚上好|中午好|hello|hi|thanks)[呀啊哦啦!！。，,.~～\s]*)+", stripped, re.I)
                or (operation_only and (_direct_knowledge_save_requested(stripped)
                    or re.match(r"^(?:请)?(?:确认|拒绝|忽略|停止|继续|记住|忘记|纠正记忆|保存记忆)", stripped)))
                or (re.match(r"^[^。！？\n]{0,20}(?:翻译|改写|校对|润色)", stripped)
                    and re.search(r"以下|下面|这段|这句|：|:", stripped)
                    and not re.search(r"收藏|知识库|知识页|检索", stripped))):
            return False, [], False
        sources = ["wiki", "collection"]
        if re.search(r"(?:只|仅)(?:查|看|搜|用|参考).{0,12}(?:已整理|知识页|知识库|Wiki|wiki)", stripped):
            sources = ["wiki"]
        elif re.search(r"(?:只|仅)(?:查|看|搜|用|参考).{0,12}(?:原收藏|原视频|原始材料)", stripped):
            sources = ["collection"]
        unresolved = bool(re.search(r"限定|限制范围|限于|仅限|排除|不用管|不考虑", stripped)) or (
            len(sources) == 2 and bool(re.search(r"(?:只|仅)(?:看|读|用|参考|查|搜索)", stripped)))
        return True, sources, unresolved

    async def _bootstrap_knowledge(self, state: ExecutionState) -> ExecutionState | None:
        if not hasattr(self.tools, "search_knowledge") or self.tools.sources is None:
            return None
        context = self.store.run_context(state["run_id"])
        current = context["run"]
        if not current["working_state"].get("execution_budget"):
            self.store.initialize_execution_budget(state["run_id"], epoch=state["epoch"], model_limit=self.max_steps, tool_limit=self.max_tool_calls)
        user = next(item for item in reversed(context["thread"]["messages"])
                    if item["role"] == "user" and item["run_id"] == state["run_id"])
        eligible, sources, unresolved = self._discovery_request(str(user["content"]))
        markers = [run["working_state"].get("knowledge_bootstrap") or {} for run in self.store.get_thread(str(context["thread"]["id"]))["runs"]]
        if not eligible or any(marker.get("status") in {"completed", "abandoned"} for marker in markers):
            return None
        subset = context["space"].get("task_subset") or {}
        if unresolved and subset.get("source_message_id") != user["id"]:
            return None
        from shiliu.assistant.contracts import KnowledgeSearchArgs
        args = KnowledgeSearchArgs(query=user["content"][:2000], sources=sources)
        scope = self.tools.scope_identity(context["space"])
        scope_key = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()[:12]
        call_id = f"bootstrap_{user['id']}_{scope_key}"
        marker = {"message_id": user["id"], "call_id": call_id, "result_ref": f"run-result:{state['run_id']}:{call_id}",
                  "origin": "bootstrap", "scope": scope, "status": "running"}
        self.store.set_knowledge_bootstrap(state["run_id"], epoch=state["epoch"], value=marker)
        ordinal = max(state["tool_count"], int(current["tool_count"])) + 1
        existing = self.store.begin_tool_call(state["run_id"], ordinal=ordinal, call_id=call_id,
                                              name="search_knowledge", arguments=args.model_dump())
        if existing and existing.get("result_json"):
            ordinal = max(int(current["tool_count"]), int(existing["ordinal"]))
            result = json_object(existing["result_json"])
        else:
            try:
                self.store.dispatch_tool(state["run_id"], epoch=state["epoch"])
            except ExecutionBudgetExceeded:
                return await self._finish_with_available(state, reason="budget")
            pending = asyncio.create_task(self.tools.search_knowledge(args, call_id=call_id, run_context=context))
            while not pending.done():
                fresh = self.store.get_run(state["run_id"])
                changed = self.tools.scope_identity(self.store.task_space(str(context["thread"]["id"]))) != scope
                timed_out = self.store.execution_remaining(state["run_id"]) <= 0
                if (fresh["status"] != "running" or fresh["run_epoch"] != state["epoch"]
                        or fresh["working_state"].get("finish_requested") or changed or timed_out):
                    def settle_late(task):
                        try:
                            late = task.result()
                            late["result_ref"] = marker["result_ref"]
                            late["coverage"].update(origin="bootstrap", source_message_id=user["id"], discarded=True)
                            self.store.finish_tool_call(state["run_id"], call_id=call_id, result=late)
                        except (Exception, asyncio.CancelledError):
                            pass
                    pending.add_done_callback(settle_late)
                    if fresh["status"] == "running" and fresh["run_epoch"] == state["epoch"]:
                        self.store.set_knowledge_bootstrap(state["run_id"], epoch=state["epoch"], value={**marker, "status": "abandoned"})
                        if changed:
                            self.store.pause_run(state["run_id"], code="source_scope_changed", message="检索期间实际资料范围发生变化，候选已撤下；可继续按当前范围查询")
                        if fresh["working_state"].get("finish_requested") or timed_out:
                            return await self._finish_with_available(state, reason="user_requested" if fresh["working_state"].get("finish_requested") else "budget")
                    return {**state, "route": "stopped"}
                await asyncio.wait({pending}, timeout=.05)
            result = pending.result()
            result["result_ref"] = marker["result_ref"]
            result["coverage"].update(origin="bootstrap", source_message_id=user["id"])
            self.store.finish_tool_call(state["run_id"], call_id=call_id, result=result)
        fresh = self.store.get_run(state["run_id"])
        changed = self.tools.scope_identity(self.store.task_space(str(context["thread"]["id"]))) != scope
        if not self._run_epoch_active(state) or fresh["working_state"].get("finish_requested") or changed:
            result["coverage"]["discarded"] = True
            self.store.finish_tool_call(state["run_id"], call_id=call_id, result=result)
            if changed and self._run_epoch_active(state):
                self.store.set_knowledge_bootstrap(state["run_id"], epoch=state["epoch"], value={**marker, "status": "abandoned"})
                self.store.pause_run(state["run_id"], code="source_scope_changed", message="检索期间实际资料范围发生变化，候选已撤下；可继续按当前范围查询")
                return {**state, "route": "stopped"}
            return {**state, "route": "stopped"} if not self._run_epoch_active(state) else await self._finish_with_available(state, reason="user_requested")
        self.store.set_knowledge_bootstrap(state["run_id"], epoch=state["epoch"], value={**marker, "status": "completed"})
        self.store.save_step(state["run_id"], step_count=state["step_count"], tool_count=ordinal, usage=state["usage"], epoch=state["epoch"])
        return None

    async def _model(self, state: ExecutionState) -> ExecutionState:
        current = self.store.get_run(state["run_id"])
        if current["status"] != "running" or current["run_epoch"] != state["epoch"]:
            return {**state, "route": "stopped"}
        budget = self.store.initialize_execution_budget(
            state["run_id"], epoch=state["epoch"],
            model_limit=self.max_steps, tool_limit=self.max_tool_calls)
        if (current["working_state"].get("finish_requested")
                or budget["model_calls"] >= budget["model_limit"] - 1
                or budget["tool_executions"] >= budget["tool_limit"]
                or self.store.execution_remaining(state["run_id"]) <= 0
                or budget["known_tokens"] >= ASSISTANT_TOKEN_LIMIT):
            return await self._finish_with_available(state, reason="user_requested" if current["working_state"].get("finish_requested") else "budget")
        discovery = await self._bootstrap_knowledge(state)
        if discovery is not None:
            return discovery
        state = {**state, "tool_count": int(self.store.get_run(state["run_id"])["tool_count"])}
        provider = self.provider_factory()
        try:
            candidate = await self._prepare_dispatch(state, provider=provider)
            context_metadata = candidate.metadata
            control, turn = await self._dispatch_main(state, provider=provider, candidate=candidate)
        except ExecutionBudgetExceeded:
            return await self._finish_with_available(state, reason="budget")
        except ContextBudgetExceeded as exc:
            self.store.fail_run(state['run_id'], code='context_recovery_failed', message=f'{exc}；原始历史已保留，可新建对话继续。')
            return {**state, 'route': 'stopped'}
        except AssistantConflict as exc:
            if self._run_epoch_active(state):
                self.store.pause_run(state['run_id'], code='context_changed_retry_exhausted', message=str(exc))
            return {**state, 'route': 'stopped'}
        except PipelineError as exc:
            if not self._run_epoch_active(state):
                return {**state, 'route': 'stopped'}
            if exc.code == 'provider_context_window_exceeded':
                if not self.store.mark_context_recovery_attempt(state['run_id'], epoch=state['epoch']):
                    self.store.fail_run(state['run_id'], code='context_recovery_failed', message='容量恢复次数已用完，原始进度已保留')
                    return {**state, 'route': 'stopped'}
                try:
                    before = candidate.request.input_tokens
                    candidate = await self._prepare_dispatch(state, provider=provider, explicit_overflow=True)
                    if candidate.request.input_tokens >= before:
                        raise ContextBudgetExceeded('未取得实际缩减，不能重发溢出请求；原始历史保留')
                    context_metadata = candidate.metadata
                    control, turn = await self._dispatch_main(state, provider=provider, candidate=candidate)
                except ExecutionBudgetExceeded:
                    return await self._finish_with_available(state, reason='budget')
                except (ContextBudgetExceeded, AssistantConflict, PipelineError) as recovery_error:
                    if self._run_epoch_active(state):
                        self.store.fail_run(state['run_id'], code='context_recovery_failed', message=str(recovery_error))
                    return {**state, 'route': 'stopped'}
            elif exc.code == 'tool_arguments_invalid':
                # One fully recounted transient suffix; no tool has been persisted.
                try:
                    candidate = await self._prepare_dispatch(state, provider=provider,
                        suffix='上次工具参数格式无效。本轮工具调用必须是完整 JSON 对象；提案只写必要的精炼块。')
                    context_metadata = candidate.metadata
                    control, turn = await self._dispatch_main(state, provider=provider, candidate=candidate)
                except ExecutionBudgetExceeded:
                    return await self._finish_with_available(state, reason='budget')
            else:
                raise
        if control == 'cancelled':
            return {**state, 'route': 'stopped', 'turn': None}
        if control in {'finish', 'timeout'}:
            return await self._finish_with_available(state, reason='user_requested' if control == 'finish' else 'budget')
        assert turn is not None
        if turn.finish_reason not in {'stop', 'tool_calls'}:
            raise PipelineError('主模型回答未完整结束', code='provider_incomplete', retryable=False)
        usage = self.store.get_run(state["run_id"])["usage"]
        self.store.confirm_model_delivery(
            state["run_id"], epoch=state["epoch"],
            spans=context_metadata.get("delivered_read_spans") or [],
            materials=context_metadata.get("material_projection") or [],
            message_ids=candidate.message_ids, context_revision=candidate.state["revision"],
        )
        current = self.store.get_run(state["run_id"])
        if current["status"] != "running" or current["run_epoch"] != state["epoch"]:
            return {**state, "route": "stopped", "turn": None}
        if current["working_state"].get("finish_requested"):
            return await self._finish_with_available({**state, "usage": usage}, reason="user_requested")
        step_count = state["step_count"] + 1
        route: Literal["tools", "final"] = "tools" if turn.tool_calls else "final"
        if turn.tool_calls:
            provider_calls = [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in turn.tool_calls
            ]
            self.store.save_assistant_tool_message(
                state["run_id"],
                content="",
                provider_payload={"tool_calls": provider_calls, **turn.opaque_provider_state,
                                  "tool_round_content_characters": len(turn.text)},
            )
        self.store.save_step(
            state["run_id"], step_count=step_count, tool_count=state["tool_count"], usage=usage, epoch=state["epoch"]
        )
        return {
            **state, "step_count": step_count, "usage": usage, "turn": turn,
            "route": route, "context_metadata": context_metadata,
            "completion_origin": "model", "receipt_pages": [],
        }

    async def _prepare_dispatch(self, state: ExecutionState, *, provider: Any, final: bool = False,
                                explicit_overflow: bool = False, suffix: str | None = None) -> WorkingContextCandidate:
        """One decision and at most one summary, with one fresh CAS retry."""
        def prepare():
            prepared = self.composer.prepare(state['run_id'], provider=provider,
                tool_schemas=[] if final else self.tools.schemas(), output_tokens=8192 if final else 4096)
            return self.composer.reframe(prepared, provider=provider, suffix=suffix) if suffix else prepared
        attempted = False
        compaction_failure = None
        for retry in range(2):
            try:
                candidate = prepare()
                original = candidate.request.input_tokens
                high = original >= .85 * candidate.budget.available_input_tokens
                hard = explicit_overflow or not candidate.budget.fits
                if not final and not attempted:
                    if not high and not hard and candidate.state.get('pressure_event_attempted'):
                        self.store.record_context_attempt(candidate, attempted=False)
                        candidate = prepare()
                    elif hard or (high and not candidate.state.get('pressure_event_attempted')):
                        attempted = True
                        plan = plan_compaction(candidate, composer=self.composer, provider=provider,
                                               hard=hard, soft_target=self.compaction_soft_target, suffix=suffix)
                        old = candidate
                        self.store.record_context_attempt(candidate, attempted=True,
                            reason='hard' if hard else 'preventative')
                        candidate = prepare()
                        # A summary cannot be transplanted onto a concurrently rebuilt base.
                        unchanged = (candidate.state['entries'] == old.state['entries']
                            and candidate.state['identity'] == old.state['identity']
                            and candidate.source_guard == old.source_guard
                            and candidate.memory_epoch == old.memory_epoch
                            and candidate.navigation_guard == old.navigation_guard
                            and candidate.context['thread'].get('task_note') == old.context['thread'].get('task_note'))
                        if plan is not None and unchanged:
                            replacement, compaction_failure = await self._compact_once(state, candidate=candidate, plan=plan, provider=provider, suffix=suffix)
                            if replacement is not None:
                                return replacement
                            candidate = prepare()
                if not candidate.budget.fits and not final:
                    candidate = self.composer.fit_unfrozen_tools(candidate, provider=provider, suffix=suffix)
                if explicit_overflow and candidate.request.input_tokens >= original:
                    raise ContextBudgetExceeded('已确认溢出的工作基准无法有效缩减；原始历史保留，可新建对话')
                self.composer.persist(candidate)
                return candidate
            except ContextBudgetExceeded as exc:
                if compaction_failure:
                    failure = compaction_failure
                    raise ContextBudgetExceeded(
                        f"摘要失败（阶段={failure['stage']}，派发={failure['dispatched']}，"
                        f"原因={failure['code']}：{failure['reason']}）；容量恢复未完成：{exc}"
                    ) from exc
                raise
            except ExecutionBudgetExceeded:
                raise
            except AssistantConflict:
                if retry or not self._run_epoch_active(state):
                    raise
        raise AssistantConflict('working_context_changed')

    async def _compact_once(self, state: ExecutionState, *, candidate: WorkingContextCandidate, plan: Any,
                            provider: Any, suffix: str | None = None) -> tuple[WorkingContextCandidate | None, dict | None]:
        started = time.monotonic()
        dispatched, summary_usage = False, {}
        stage = 'prepare'
        try:
            budget = self.store.get_run(state['run_id'])['working_state']['execution_budget']
            reserve_input = self._final_reserve_input(candidate, provider=provider)
            request = provider.prepare_compaction(messages=plan.messages,
                remaining_tokens=ASSISTANT_TOKEN_LIMIT - int(budget['known_tokens']) - reserve_input - 8192)
            stage = 'dispatch'
            reservation = self.store.reserve_model_request(lane='foreground', request_limit=10000,
                run_id=state['run_id'],request_hash=self._dispatch_request_hash(request))
            def summarize(call_id):
                nonlocal dispatched, summary_usage
                dispatched = True
                try:
                    turn = provider.send_prepared(request,
                        timeout_seconds=self.store.execution_remaining(state['run_id']))
                    summary_usage = turn.usage
                    return turn
                except Exception as exc:
                    summary_usage = getattr(exc, 'usage', {}) or {}
                    raise
            control, turn = await self._wait_for_model(state, summarize,
                timeout=self.store.execution_remaining(state['run_id']),
                input_tokens=request.input_tokens, output_tokens=request.body['max_tokens'],
                reserve_input_tokens=reserve_input, publish_draft=False,
                budget_date=str(reservation['budget_date']),dispatch_id=str(reservation['dispatch_id']))
            if control != 'ready':
                raise ExecutionBudgetExceeded('摘要已停止，转入停止或收尾')
            stage = 'response'
            if (turn.finish_reason != 'stop' or turn.tool_calls
                    or not isinstance(turn.text, str) or not turn.text.strip()):
                raise ValueError('摘要正文不完整')
            stage = 'candidate'
            proposed = checkpoint_proposal(candidate, plan, turn.text, composer=self.composer, provider=provider)
            if suffix:
                proposed = self.composer.reframe(proposed, provider=provider, suffix=suffix)
            if not proposed.budget.fits:
                proposed = self.composer.fit_unfrozen_tools(proposed, provider=provider, suffix=suffix)
            if proposed.request.input_tokens >= candidate.request.input_tokens or not proposed.budget.fits:
                raise ValueError('摘要候选未实际缩小或仍不适配')
            # All source/Memory/navigation/frontier checks and both writes share one transaction.
            stage = 'commit'
            self.composer.persist(proposed, new_checkpoint=True)
            return proposed, None
        except Exception as exc:
            # Optional failure does not turn a still legal original request into a Run error.
            if not self._run_epoch_active(state):
                if isinstance(exc, ExecutionBudgetExceeded):
                    raise
                raise AssistantConflict('run_fenced') from exc
            failure = {'stage': stage, 'dispatched': dispatched,
                       'code': str(getattr(exc, 'code', type(exc).__name__)), 'reason': str(exc)[:200]}
            with self.store.db.connect() as connection:
                self.store._append_event(connection, state['run_id'], 'context_compaction_discarded', failure)
            if isinstance(exc, ExecutionBudgetExceeded):
                raise
            return None, failure
        finally:
            if dispatched:
                self.store.record_compaction(state['run_id'], epoch=state['epoch'], usage=summary_usage,
                    input_characters=sum(len(m['content']) for m in plan.messages),
                    latency_ms=(time.monotonic()-started)*1000)

    def _final_reserve_input(self, candidate: WorkingContextCandidate, *, provider: Any) -> int:
        base, _ = self.composer._request(candidate.state, candidate.projections,
            checkpoint=candidate.checkpoint, provider=provider, tool_schemas=[], output_tokens=8192,
            input_limit_tokens=candidate.budget.input_limit_tokens)
        request = provider.prepare_request(messages=[*base.body['messages'],
            {'role': 'system', 'content': FINAL_INSTRUCTION}], tools=[], max_tokens=8192,
            stream=bool(base.body.get('stream')))
        return request.input_tokens

    async def _dispatch_main(self, state: ExecutionState, *, provider: Any,
                             candidate: WorkingContextCandidate) -> tuple[str, Any]:
        if not self.store.save_context_observation(state['run_id'], epoch=state['epoch'], metadata=candidate.metadata):
            return 'cancelled', None
        reservation = self.store.reserve_model_request(lane='foreground', request_limit=10000,
            run_id=state['run_id'],request_hash=self._dispatch_request_hash(candidate.request))
        return await self._wait_for_model(state,
            lambda call_id: self._provider_turn(provider, state, candidate=candidate, call_id=call_id),
            timeout=self.store.execution_remaining(state['run_id']),
            input_tokens=candidate.request.input_tokens, output_tokens=candidate.budget.output_tokens,
            reserve_input_tokens=self._final_reserve_input(candidate, provider=provider),
            budget_date=str(reservation['budget_date']),dispatch_id=str(reservation['dispatch_id']))

    def _run_epoch_active(self, state: ExecutionState) -> bool:
        run = self.store.get_run(state["run_id"])
        return (run["status"] == "running" and run["run_epoch"] == state["epoch"]
                and not run.get("cancel_requested"))

    def _provider_turn(self, provider: Any, state: ExecutionState, *, candidate: WorkingContextCandidate,
                       call_id: str, allow_finish: bool = False) -> ModelTurn:
        last_saved = 0.0
        memory_succeeded = self._memory_write_succeeded(state['run_id'])
        def on_text(text: str) -> None:
            nonlocal last_saved
            now = time.monotonic()
            if now - last_saved < 0.25:
                return
            last_saved = now
            # Publication revalidates all source/knowledge dependencies in the
            # API, and final commit validates again. The writer checks epoch,
            # control and Memory in a short transaction; do not replay whole
            # historical-result projections on every provider token.
            self.store.save_answer_draft(state["run_id"], epoch=state["epoch"],
                                         text=self._memory_claim(text, memory_succeeded), allow_finish=allow_finish, call_id=call_id)
        turn = provider.send_prepared(candidate.request, on_text=on_text)
        if turn.finish_reason not in {'stop', 'tool_calls'}:
            raise PipelineError('主模型回答未完整结束', code='provider_incomplete', retryable=False)
        # Tool-round content is provisional; do not retain it as an answer.
        self.store.save_answer_draft(state["run_id"], epoch=state["epoch"],
                                     text="" if turn.tool_calls else self._memory_claim(turn.text, memory_succeeded), allow_finish=allow_finish, call_id=call_id)
        return turn

    async def _wait_for_model(self, state: ExecutionState, invoke: Callable[[str], Any],
                              *, timeout: float | None = None,
                              ignore_finish: bool = False,
                              budget_date: str | None = None,
                              dispatch_id: str,
                              input_tokens: int | None = None, output_tokens: int | None = None,
                              reserve_input_tokens: int | None = None, publish_draft: bool = True) -> tuple[str, Any | None]:
        """Release the foreground lane on local control, while settling a late call once."""
        started = time.monotonic()
        # Register before dispatch: even a delayed executor thread cannot claim
        # the draft after a replacement call has started.
        call_id = uuid.uuid4().hex
        if publish_draft:
            try:
                self.store.save_answer_draft(state["run_id"], epoch=state["epoch"], text="",
                                             call_id=call_id, start_call=True, allow_finish=ignore_finish)
            except Exception:
                self.store.release_model_request(dispatch_id)
                raise
        observation = self.store.get_run(state["run_id"])["working_state"].get("context_observation") or {}
        estimated = int(input_tokens if input_tokens is not None else observation.get("estimated_input_tokens") or 0)
        dispatched = {"value": False}
        remaining = self.store.execution_remaining(state["run_id"], final=ignore_finish)
        timeout = min(timeout if timeout is not None else remaining, remaining)
        if timeout <= 0:
            self.store.release_model_request(dispatch_id)
            raise ExecutionBudgetExceeded("本段期限已用完")
        def dispatch():
            self.store.dispatch_model(state["run_id"], epoch=state["epoch"], final=ignore_finish,
                                      input_tokens=estimated, output_tokens=output_tokens or (8192 if ignore_finish else 4096),
                                      reserve_input_tokens=reserve_input_tokens)
            dispatched["value"] = True
            return invoke(call_id)
        pending = asyncio.create_task(asyncio.to_thread(dispatch))
        deadline = started + timeout
        while True:
            done, _ = await asyncio.wait({pending}, timeout=0.1)
            if done:
                try:
                    value = pending.result()
                except BaseException as exc:
                    if not dispatched["value"]:
                        self.store.release_model_request(dispatch_id)
                        if isinstance(exc, AssistantConflict) and not isinstance(exc, ExecutionBudgetExceeded):
                            return "cancelled", None
                        raise
                    self.store.record_provider_response(state["run_id"], SimpleNamespace(usage=getattr(exc, "usage", {}) or {}), late=False, call_id=call_id)
                    self.store.record_model_usage(lane="foreground", usage=getattr(exc, "usage", None),
                        outcome="error_or_lost", latency_ms=(time.monotonic() - started) * 1000,
                        budget_date=budget_date,dispatch_id=dispatch_id)
                    raise
                self.store.record_provider_response(state["run_id"], value, late=False, call_id=call_id)
                self.store.record_model_usage(lane="foreground", usage=getattr(value, "usage", None),
                    outcome="response", latency_ms=(time.monotonic() - started) * 1000,
                    budget_date=budget_date,dispatch_id=dispatch_id)
                return "ready", value
            current = self.store.get_run(state["run_id"])
            reason = ("cancelled" if current["status"] != "running" or
                      current["run_epoch"] != state["epoch"] else
                      "finish" if not ignore_finish and current["working_state"].get("finish_requested") else
                      "timeout" if deadline is not None and time.monotonic() >= deadline else None)
            if reason is None:
                continue

            def settle_late(task: asyncio.Task[Any]) -> None:
                try:
                    value = task.result()
                    usage = getattr(value, "usage", None)
                    self.store.record_provider_response(state["run_id"], value, late=True, call_id=call_id)
                    self.store.record_model_usage(lane="foreground", usage=usage,
                        outcome="late_response", latency_ms=(time.monotonic() - started) * 1000,
                        budget_date=budget_date,dispatch_id=dispatch_id)
                except BaseException as exc:
                    if not dispatched["value"]:
                        self.store.release_model_request(dispatch_id)
                        return
                    known = getattr(exc, "usage", None)
                    self.store.record_provider_response(state["run_id"], SimpleNamespace(usage=known or {}), late=True, call_id=call_id)
                    self.store.record_model_usage(lane="foreground", usage=known,
                        outcome="error_or_lost", latency_ms=(time.monotonic() - started) * 1000,
                        budget_date=budget_date,dispatch_id=dispatch_id)

            # Revoke publication before returning to the replacement path.
            # Late completion still settles usage through the callback below.
            if publish_draft:
                self.store.save_answer_draft(state["run_id"], epoch=state["epoch"], text="",
                                             call_id=uuid.uuid4().hex, start_call=True,
                                             allow_finish=ignore_finish)
            if dispatched["value"]:
                self.store.mark_dispatch_unknown(dispatch_id)
            pending.add_done_callback(settle_late)
            return reason, None

    async def _controlled_search(self, state: ExecutionState, invoke: Callable[[], Any], *, call_id: str) -> tuple[str, dict | None]:
        pending = asyncio.create_task(invoke())
        scope = self.tools.scope_identity(self.store.task_space(str(self.store.get_run(state["run_id"])["thread_id"])))
        while not pending.done():
            current = self.store.get_run(state["run_id"])
            control = ("cancelled" if not self._run_epoch_active(state) else
                       "finish" if current["working_state"].get("finish_requested") else
                       "timeout" if self.store.execution_remaining(state["run_id"]) <= 0 else
                       "scope" if self.tools.scope_identity(self.store.task_space(str(current["thread_id"]))) != scope else None)
            if control:
                def settle_late(task):
                    try:
                        result = task.result()
                        result["coverage"]["discarded"] = True
                        result["result_ref"] = f"run-result:{state['run_id']}:{call_id}"
                        self.store.finish_tool_call(state["run_id"], call_id=call_id, result=result)
                    except (Exception, asyncio.CancelledError):
                        pass
                pending.add_done_callback(settle_late)
                return control, None
            await asyncio.wait({pending}, timeout=.05)
        result = pending.result()
        current = self.store.get_run(state["run_id"])
        control = ("cancelled" if not self._run_epoch_active(state) else
                   "finish" if current["working_state"].get("finish_requested") else
                   "scope" if self.tools.scope_identity(self.store.task_space(str(current["thread_id"]))) != scope else "completed")
        if control != "completed":
            result["coverage"]["discarded"] = True
            result["result_ref"] = f"run-result:{state['run_id']}:{call_id}"
            self.store.finish_tool_call(state["run_id"], call_id=call_id, result=result)
            return control, None
        return "completed", result

    def _focus_rounds(self, state: ExecutionState) -> int:
        context = self.store.run_context(state["run_id"])
        with self.store.db.connect() as connection:
            rows = connection.execute("SELECT call_id,result_json FROM assistant_tool_calls WHERE workspace_id=%s AND run_id=%s", (self.store.context.workspace_id,state["run_id"])).fetchall()
        results = {str(row["call_id"]): json_object(row["result_json"] or "{}") for row in rows}
        rounds = 0
        for message in reversed(context["thread"]["messages"]):
            if message.get("run_id") != state["run_id"] or message["role"] != "assistant":
                continue
            calls = json_object(message.get("provider_payload_json") or "{}").get("tool_calls") or []
            if not calls:
                break
            focus = False
            for call in calls:
                name = call["function"]["name"]
                result = results.get(str(call["id"]), {})
                if name == "task_focus":
                    refs = result.get("dependency_refs") or []
                    if refs and self.dependency_ref_validator and not self.dependency_ref_validator(
                        refs, int(context["space"]["id"]), str(context["thread"]["id"]), int(context["space"]["scope_version"])):
                        return rounds
                    focus = True
                elif not result.get("coverage", {}).get("cache_hit"):
                    return rounds
            if focus:
                rounds += 1
        return rounds

    async def _tools(self, state: ExecutionState) -> ExecutionState:
        turn = state["turn"]
        if turn is None:
            return {**state, "route": "stopped"}
        tool_count = state["tool_count"]
        result = {}
        # Only identical failed save submissions count as no progress. Changed drafts,
        # reads and real edits are never stopped by this check.
        with self.store.db.connect() as c:
            rows = c.execute("SELECT name,args_json,result_json FROM assistant_tool_calls WHERE workspace_id=%s AND run_id=%s ORDER BY ordinal DESC LIMIT 2", (self.store.context.workspace_id,state['run_id'])).fetchall()
        if len(rows) == 2 and all(r['name'] in {'knowledge_save_discussion', 'memory_save'} and (
                json_object(r['result_json'] or '{}').get('status') in {'invalid_arguments','partial'} or
                (r['name']=='memory_save' and json_object(r['result_json'] or '{}').get('status')=='unavailable'
                 and not json_object(r['result_json'] or '{}').get('retryable'))) for r in rows):
            failed = [json_object(r['result_json']) for r in rows]
            prior_args = json_object(rows[0]['args_json'])
            repeating = all(call.name == rows[0]['name'] and rows[0]['name'] == rows[1]['name'] and
                self.tools.normalize_arguments(call.name, call.arguments) == prior_args for call in turn.tool_calls)
            if repeating and prior_args == json_object(rows[1]['args_json']) and failed[0].get('error_code') == failed[1].get('error_code') and failed[0].get('items') == failed[1].get('items'):
                return await self._finish_with_available(state, reason='unchanged_save_error')
        focus_rounds = self._focus_rounds(state)
        if focus_rounds >= 3:
            return await self._finish_with_available(state, reason="repeated_focus")
        for call in turn.tool_calls:
            current = self.store.get_run(state["run_id"])
            if current["status"] != "running" or current["run_epoch"] != state["epoch"]:
                return {**state, "route": "stopped", "tool_count": tool_count}
            if current["working_state"].get("finish_requested"):
                return await self._finish_with_available(
                    {**state, "tool_count": tool_count}, reason="user_requested")
            if self.store.tool_result_message_exists(state["run_id"], call.call_id):
                continue
            if self.store.execution_remaining(state["run_id"]) <= 0:
                return await self._finish_with_available(
                    {**state, "tool_count": tool_count}, reason="budget")
            ordinal = tool_count + 1
            arguments = (call.arguments if call.call_id in state.get("replay_call_ids", [])
                         else self.tools.normalize_arguments(call.name, call.arguments))
            existing = self.store.begin_tool_call(
                state["run_id"],
                ordinal=ordinal,
                call_id=call.call_id,
                name=call.name,
                arguments=arguments,
                operation_key=f"tool:{state['run_id']}:{call.call_id}",
                reuse_validator=(
                    lambda candidate: self.tools.reusable_result_valid(
                        candidate,
                        run_context=self.store.run_context(state["run_id"]),
                    )
                ) if hasattr(self.tools, "reusable_result_valid") else None,
            )
            if existing is not None and existing.get("result_json"):
                result = json_object(existing["result_json"])
            else:
                try:
                    self.store.dispatch_tool(state["run_id"], epoch=state["epoch"])
                except ExecutionBudgetExceeded:
                    return await self._finish_with_available(state, reason="budget")
                async def invoke():
                    return await self.tools.execute(
                        name=call.name, arguments=arguments, call_id=call.call_id,
                        run_context=self.store.run_context(state["run_id"]),
                        **({"replay": True} if call.call_id in state.get("replay_call_ids", []) and isinstance(self.tools, AssistantToolRegistry) else {}),
                    )
                if isinstance(self.tools, AssistantToolRegistry) and (call.name.startswith("context7_") or call.name in {"search_knowledge", "collection_search", "knowledge_search", "collection_read", "knowledge_read", "run_read_result", "memory_search", "conversation_history"}):
                    control, result = await self._controlled_search(state, invoke, call_id=call.call_id)
                    if control in {"finish", "timeout"}:
                        return await self._finish_with_available(state, reason="user_requested" if control == "finish" else "budget")
                    if control != "completed":
                        if control == "scope" and self._run_epoch_active(state):
                            self.store.pause_run(state["run_id"], code="source_scope_changed", message="检索期间实际资料范围发生变化，候选已撤下；可继续按当前范围查询")
                        return {**state, "route": "stopped"}
                else:
                    result = await invoke()
                if call.name == "task_focus" and focus_rounds >= 2:
                    result["summary"] += "；连续两轮仅维护焦点，下一轮请直接交付有效结果或实际补查具体缺项"
                    result.setdefault("coverage", {})["focus_feedback"] = True
                result["result_ref"] = f"run-result:{state['run_id']}:{call.call_id}"
                self.store.finish_tool_call(state["run_id"], call_id=call.call_id, result=result)
            self.store.save_tool_result_message(
                state["run_id"],
                content=json.dumps(result, ensure_ascii=False),
                provider_payload={"tool_call_id": call.call_id, "name": call.name},
            )
            tool_count += 1
            self.store.save_step(
                state["run_id"], step_count=state["step_count"],
                tool_count=tool_count, usage=state["usage"], epoch=state["epoch"],
            )
            current = self.store.get_run(state["run_id"])
            if current["status"] != "running" or current["run_epoch"] != state["epoch"]:
                self.store.record_late_tool_completion(state["run_id"], tool_count)
                return {**state, "route": "stopped", "tool_count": tool_count}
            if current["working_state"].get("finish_requested"):
                return await self._finish_with_available(
                    {**state, "tool_count": tool_count}, reason="user_requested")
        self.store.save_step(
            state["run_id"], step_count=state["step_count"], tool_count=tool_count, usage=state["usage"], epoch=state["epoch"]
        )
        # Only the dedicated save button is a proven operation-only request.
        # Natural-language compound requests still return to the Agent.
        binding = self.store.get_run(state["run_id"])["working_state"].get("knowledge_save") or {}
        if (binding.get("answer_message_id") and binding.get("receipt_only") is True and len(turn.tool_calls) == 1
                and turn.tool_calls[0].name == "knowledge_save_discussion"
                and result.get("status") == "ok" and result.get("items")
                and result["items"][0].get("status") == "completed"):
            feedback = result.get("coverage", {}).get("save_feedback") or {}
            if feedback.get("count"):
                return {**state, "tool_count": tool_count, "route": "final",
                        "turn": ModelTurn(text=f"已保存 {feedback['count']} 个知识页，可在知识面板查看。"),
                        "completion_origin": "operation_receipt", "receipt_pages": feedback["items"]}
        return {**state, "tool_count": tool_count, "route": "model", "turn": None}

    async def _final(self, state: ExecutionState) -> ExecutionState:
        turn = state["turn"]
        if turn is None:
            return {**state, "route": "stopped"}
        current = self.store.get_run(state["run_id"])
        if current["status"] != "running" or current["run_epoch"] != state["epoch"]:
            return {**state, "route": "stopped"}
        if self._bare_tool_protocol(turn.text):
            self.store.fail_run(state['run_id'], code='model_protocol_in_answer',
                message='模型返回了未执行的工具协议，未发布正式成果；可继续原问题。')
            return {**state, 'route':'stopped'}
        metadata = state.get("context_metadata") or {}
        def validate_dependencies(refs, space_id, thread_id, scope_version):
            if self.dependency_ref_validator and not self.dependency_ref_validator(refs, space_id, thread_id, scope_version):
                return False
            for item in state.get("receipt_pages") or []:
                try:
                    page = self.tools.wiki.get_page(item["page_id"], space_id=space_id)
                    if int(page["version"]) != int(item["version"]) or not page["blocks"]:
                        return False
                except (KeyError, ValueError, AssistantConflict):
                    return False
            return True
        outcome = self.store.try_complete_run(
            state["run_id"], epoch=state["epoch"],
            answer=self._presentable_answer(self._memory_claim(turn.text, self._memory_write_succeeded(state['run_id']))),
            usage=self.store.get_run(state["run_id"])["usage"],
            expected_scope_version=int(metadata.get("scope_version") or 0),
            expected_observed_memory_epoch=int(metadata.get("observed_memory_epoch") or 0),
            dependency_refs=[str(value) for value in metadata.get("dependency_refs") or []],
            expected_task_note_version=(
                int(metadata["task_note_version"])
                if metadata.get("task_note_version") is not None else None
            ),
            dependency_validator=validate_dependencies,
            completion_origin=state.get("completion_origin", "model"),
        )
        if outcome == "completed":
            return {**state, "route": "stopped"}
        self.store.save_answer_draft(state["run_id"], epoch=state["epoch"], text="")
        if outcome == "execution_budget_exhausted":
            self.store.fail_run(state["run_id"], code=outcome, message="本段期限已结束，已保留进度；可主动 Continue")
            return {**state, "route": "stopped"}
        if outcome in {
            "memory_changed", "memory_dependency_changed", "dependency_changed",
            "task_note_changed", "scope_changed"
        } and state["memory_restart_count"] < 1:
            return {
                **state,
                "route": "model",
                "turn": None,
                "memory_restart_count": state["memory_restart_count"] + 1,
            }
        if outcome != "run_fenced":
            self.store.pause_run(
                state["run_id"], code="context_changed_retry_exhausted",
                message="回答生成期间上下文持续变化，已保留进度；请继续后重新生成",
            )
        return {**state, "route": "stopped"}

    def _memory_write_succeeded(self, run_id: str) -> bool:
        with self.store.db.connect() as c:
            calls = c.execute("SELECT result_json FROM assistant_tool_calls WHERE workspace_id=%s AND run_id=%s AND name IN ('memory_save','memory_correct') AND status='completed'", (self.store.context.workspace_id,run_id)).fetchall()
        for row in calls:
            result = json_object(row['result_json'] or '{}')
            if result.get('status') != 'ok':
                continue
            for item in result.get('items') or []:
                try:
                    memory = self.tools.memories.get(item['id'])
                    if memory['status'] == 'active' and memory['version'] == item['version']:
                        return True
                except (KeyError, TypeError):
                    pass
        return False

    @staticmethod
    def _memory_claim(text: str, succeeded: bool) -> str:
        if succeeded:
            return text
        # Only a leading operation assertion is rewritten; quoted examples and
        # ordinary memory discussions are not a success assertion.
        assertion = r'^(?:【正式回答[^】]*】\s*)?(?:(?:好的|好|没问题|可以)[，,。！!\s]*)?(?:(?:我)?(?:已经|已)(?:为你|帮你)?(?:记下|记住)|(?:这条|这次|该条)?记忆(?:已经|已)?(?:保存|记录)(?:成功|好了)?|(?:我)?(?:已经|已)(?:保存|存入)(?:到)?(?:了)?(?:正式|长期|个人)?记忆)'
        if re.match(assertion, text.strip()) or re.match(r'^(?:以后|今后)(?:我)?(?:会|将)(?:一直)?记住', text.strip()):
            parts = text.strip().split('\n\n', 1)
            return '这条信息已用于本次对话，尚未确认保存为正式记忆。' + ('\n\n' + parts[1] if len(parts) > 1 else '')
        return text

    @staticmethod
    def _bare_tool_protocol(raw: str) -> bool:
        from shiliu.assistant.provider import contains_unexecuted_tool_protocol
        return contains_unexecuted_tool_protocol(raw)

    @staticmethod
    def _presentable_answer(raw: str) -> str:
        answer = raw.strip()
        # Only an unquoted leading application-identity line is impersonation.
        # Keep examples, quotations and IDs elsewhere in the answer verbatim.
        answer = re.sub(r"\A(?:【正式回答 message_id:[^\n】]*】[ \t]*(?:\r?\n|$)\s*)+", "", answer)
        # Bare model protocol is never an answer or executable instruction. Quoted
        # examples remain intact; no recovery tool is synthesized from this text.
        if AssistantExecutionGraph._bare_tool_protocol(answer):
            return "模型返回了未执行的工具协议，未生成可保存的正式成果。请继续原问题。"
        # Internal source handles belong to the UI provenance panel. Keep
        # titles and uncertainty in the prose without exposing storage IDs.
        answer = re.sub(r"\bvideo:[1-9][0-9]*(?::[0-9a-f]{64})?\b", "该材料", answer)
        return answer or "这次调用没有生成可展示的回答。"

    @staticmethod
    def _route_after_model(state: ExecutionState) -> str:
        return state["route"]

    @staticmethod
    def _route_after_tools(state: ExecutionState) -> str:
        return state["route"]

    @staticmethod
    def _route_after_final(state: ExecutionState) -> str:
        return state["route"]


class AssistantRuntime:
    def __init__(
        self,
        *,
        store: PgAssistantRunStore,
        sources: CollectionSourceService,
        context7: Context7MCPClient,
        provider_factory: Callable[[], AssistantModelProvider],
        extraction_provider_factory: Callable[[], AssistantModelProvider] | None = None,
        embedding_provider: Any = None,
    ) -> None:
        from shiliu.assistant.pg_store import PgAssistantRunStore
        if not isinstance(store,PgAssistantRunStore):
            raise RuntimeError('assistant_pg_runtime_store_requires_W10')
        self.store = store
        self.sources = sources
        self.context7 = context7
        self.provider_factory = provider_factory
        self.extraction_provider_factory = extraction_provider_factory or provider_factory
        self.memories = MemoryService(store.db, provider=embedding_provider, principal_id=store.context.user_id)
        self.wiki = WikiService(db=store.db, store=store, sources=sources, principal_id=store.context.user_id)
        from shiliu.assistant.wiki_retrieval import WikiHybridIndex
        self.wiki.retrieval = WikiHybridIndex(embedding_provider, wiki=self.wiki)
        self.maintenance_paused = False
        self.local_projections_only = False
        self.manual_model_since: str | None = None
        self.tools: AssistantToolRegistry | None = None
        self._maintenance_startup_at = utc_now()
        self._active_maintenance_job: dict[str, Any] | None = None
        self.wiki.publish_allowed = self._maintenance_idle
        self.wiki.publish_transaction_guard = self._require_maintenance_idle
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._status_lock = threading.Lock()
        from shiliu.assistant.tools import _direct_knowledge_save_requested
        self._implementation = {
            "stage": "V3", "pid": os.getpid(), "loaded_at": utc_now(),
            "source_sha256": {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                              for name in ("runtime.py", "provider.py", "tools.py", "pg_store.py", "pg_access.py", "task_notes.py", "working_context.py", "api.py", "wiki.py", "context.py", "wiki_retrieval.py")},
            "nb_r1_reported_save_allowed": _direct_knowledge_save_requested("视频里说请保存这两个主题，你怎么看？"),
            "nb_r1_direct_save_allowed": _direct_knowledge_save_requested("把刚才讨论的两个主题直接保存为知识页"),
        }
        self._capabilities: dict[str, Any] = {
            "implementation": self._implementation,
            "save_receipt_completion": True,
            "runtime": "stopped", "memory_index": "unknown", "context7": "unknown"
        }

    def start(self) -> None:
        if not hasattr(self.store,'claim_next_run'):
            raise RuntimeError('assistant_pg_runtime_store_requires_W10')
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._ready.clear()
        self._thread = threading.Thread(target=self._thread_main, name="shiliu-assistant", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=30):
            self._stop.set()
            raise RuntimeError("assistant_start_timeout")
        if self.capabilities().get("runtime")=="unavailable":
            raise RuntimeError("assistant_start_failed")

    def request_stop(self) -> None:
        self._stop.set()

    def stop(self) -> None:
        self.request_stop()
        if self._thread is not None:
            # Fence any in-flight provider/tool result before waiting for the
            # blocking transport call to unwind.
            if not self.local_projections_only:
                self.store.recover_interrupted_runs()
            self._thread.join(timeout=30)
            if not self._thread.is_alive():
                self._thread = None

    def capabilities(self) -> dict[str, Any]:
        with self._status_lock:
            return {**self._capabilities, "background_maintenance": "paused" if self.maintenance_paused else "enabled"}

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as exc:
            self._set_capability("runtime","unavailable",str(exc))
        finally:
            self._ready.set()

    async def _serve(self) -> None:
        if not self.maintenance_paused and not self.local_projections_only:
            self.store.recover_expired_jobs()
        if not self.local_projections_only:
            self.store.recover_interrupted_runs()
        # Provider is lazy/offline; readiness belongs to scoped PG coverage,
        # never to opening an external vector directory at startup.
        self._set_capability('memory_index','lazy' if self.memories.provider is not None else 'unavailable')
        context7_ready = False
        if self.local_projections_only:
            self._set_capability("context7", "disabled")
        else:
            try:
                await self.context7.connect()
                context7_ready = True
                self._set_capability("context7", "ready")
            except Exception as exc:
                self._set_capability("context7", "unavailable", str(exc))
        registry = AssistantToolRegistry(
            sources=self.sources,
            memories=self.memories,
            store=self.store,
            context7=self.context7 if context7_ready else None,
            wiki=self.wiki,
        )
        self.tools = registry
        graph = AssistantExecutionGraph(
            store=self.store,
            memories=self.memories,
            tools=registry,
            provider_factory=self.provider_factory,
            recover_legacy=not self.local_projections_only,
        )
        if self.local_projections_only and self.manual_model_since is None:
            self._set_capability("provider_transport", "disabled")
        else:
            try:
                configured_provider = self.provider_factory()
                self._set_capability("provider_transport", "sse" if hasattr(configured_provider, "stream_turn") else "nonstream_compatible")
            except Exception as exc:
                self._set_capability("provider_transport", "unavailable", str(exc))
        self._set_capability("runtime", "ready")
        self._ready.set()
        try:
            loops = ([self._foreground_loop(graph)]
                     if not self.local_projections_only or self.manual_model_since else [])
            if not self.maintenance_paused or self.local_projections_only:
                loops.append(self._background_loop())
            await asyncio.gather(*loops)
        finally:
            if context7_ready:
                await self.context7.close()
            self._set_capability("runtime", "stopped")

    async def _foreground_loop(self, graph: AssistantExecutionGraph) -> None:
        while not self._stop.is_set():
            run = (self.store.claim_next_run(created_after=self.manual_model_since)
                   if self.local_projections_only else self.store.claim_next_run())
            if run is None:
                await asyncio.sleep(0.2)
                continue
            try:
                await graph.run(run)
            except Exception as exc:
                code = str(getattr(exc, "code", None) or type(exc).__name__)
                self.store.fail_run(str(run["id"]), code=code, message=str(exc), epoch=int(run["run_epoch"]))

    async def _background_loop(self) -> None:
        # Only immediate personal index/purge cleanup may bypass the idle gate.
        while not self._stop.is_set():
            try:
                idle = not self.local_projections_only and self._maintenance_idle()
                job = self.store.claim_job(
                    owner=f"runtime-{uuid.uuid4().hex[:8]}",
                    allow_model_jobs=idle,
                    allow_maintenance=idle,
                    scheduler_reason="idle_180s" if idle else "immediate_index_cleanup",
                    kinds={"memory_index", "memory_purge"} if self.local_projections_only else None,
                )
                if job is not None:
                    await self._process_job(job)
                    continue
            except Exception:
                # A claim/settlement outage belongs to this background round.
                # CancelledError still escapes, and the normal poll prevents a spin.
                logger.exception("Assistant background round failed")
            await asyncio.sleep(15)

    def _maintenance_idle(self) -> bool:
        return not self.maintenance_paused and self.store.maintenance_idle(seconds=180, startup_at=self._maintenance_startup_at)

    def _require_maintenance_idle(self, connection: Any) -> None:
        if self.maintenance_paused:
            raise MaintenanceYield("maintenance_paused")
        job = self._active_maintenance_job
        if job is not None:
            from shiliu.storage.scheduler import guard_job
            from shiliu.storage.fences import CoordinationConflict
            try:
                guard_job(connection,self.store.context,job["id"],job["lease_owner"],job["lease_epoch"])
            except CoordinationConflict as exc:
                raise MaintenanceYield("maintenance_lease_lost") from exc
        if not self.store.maintenance_idle(seconds=180,
                startup_at=self._maintenance_startup_at, connection=connection):
            raise MaintenanceYield("maintenance_user_returned")

    async def _process_job(self, job: dict[str, Any]) -> None:
        self._active_maintenance_job = job
        heartbeat = asyncio.create_task(self._heartbeat_job(job))
        try:
            kind = str(job["kind"])
            payload = job["payload"]
            if kind == "memory_index":
                result = await asyncio.to_thread(
                    self.memories.project,
                    memory_id=str(payload["memory_id"]),
                    version=int(payload["version"]),
                    job=job,
                )
            elif kind == "memory_purge":
                result = await asyncio.to_thread(
                    self.memories.purge,
                    memory_id=str(payload["memory_id"]),
                    version=int(payload["version"]),
                    job=job,
                )
            elif kind == "metadata_refresh":
                result = (
                    await asyncio.to_thread(
                        self.sources.refresh_metadata,
                        call_id=f"job:{job['id']}",
                        scope=SourceScope(
                            source_db_ids=frozenset(int(value) for value in payload["source_ids"]),
                            video_ids=frozenset(
                                int(value) for value in payload.get("video_ids", [])
                            ),
                            all_active=bool(payload["all_active"]),
                        ),
                        source_ref=str(payload["source_ref"]),
                        publish_guard=self._require_maintenance_idle,
                    )
                ).model_dump(mode="json")
            elif kind == "memory_extract":
                result = await self._extract_memories(job)
            elif kind == "source_reconcile":
                result = await asyncio.to_thread(self.wiki.reconcile, job)
            elif kind == "source_extract":
                provider = self.extraction_provider_factory()
                result = await asyncio.to_thread(
                    self.wiki.extract_source_card, job, provider=provider
                )
            elif kind == "wiki_integrate":
                provider = self.extraction_provider_factory()
                result = await asyncio.to_thread(
                    self.wiki.integrate_source_card, job, provider=provider
                )
            else:
                result = {"superseded": True, "reason": "stage_b_handler_not_enabled"}
            if kind in {"memory_index", "memory_purge", "memory_extract"}:
                return
            # Only the trusted Wiki handler sets this after its atomic commit.
            # Never persist the internal handoff in a proposal or public result.
            if result.pop("_job_completed", False) is True:
                return
            self.store.finish_job(
                str(job["id"]), proposal=result,
                owner=str(job["lease_owner"]), lease_epoch=int(job["lease_epoch"]),
            )
        except Exception as exc:
            if isinstance(exc, CoordinationConflict) and str(exc) in {
                "job_fenced", "lane_fenced", "job_missing",
            }:
                logger.info("Assistant job %s lost ownership: %s", job["id"], exc)
                return
            try:
                # A handler may have committed before a later read/cleanup failed.
                # Check ownership before attempting failure/defer; each transition
                # still performs its own CAS against races after this check.
                with self.store.db.connect() as connection:
                    guard_job(connection, self.store.context, job["id"],
                              job["lease_owner"], job["lease_epoch"])
                if isinstance(exc, ModelBudgetWait):
                    self.store.defer_job_for_budget(job, message=str(exc))
                elif isinstance(exc, MaintenanceBudgetExceeded):
                    self.store.defer_job_for_batch_budget(job, message=str(exc))
                elif isinstance(exc, MaintenanceYield):
                    self.store.defer_job_for_activity(job)
                elif isinstance(exc, AssistantConflict) and str(exc) == 'wiki_maintenance_not_authorized':
                    self.store.finish_job(str(job['id']), proposal={'superseded': True, 'reason': str(exc)},
                        owner=str(job['lease_owner']), lease_epoch=int(job['lease_epoch']))
                else:
                    code = str(getattr(exc, "code", None) or type(exc).__name__)
                    blocked = code in {"api_key_missing", "provider_auth", "memory_embedding_unavailable"}
                    self.store.fail_job(job, code=code, message=str(exc), blocked=blocked)
            except CoordinationConflict as conflict:
                if str(conflict) not in {"job_fenced", "lane_fenced", "job_missing"}:
                    raise
                logger.info("Assistant job %s settlement fenced: %s (handler: %s)",
                            job["id"], conflict, exc)
        finally:
            self._active_maintenance_job = None
            heartbeat.cancel()
            # Collect the heartbeat's own cancellation/error as a result while
            # cancellation of this consumer still propagates through gather.
            error, = await asyncio.gather(heartbeat, return_exceptions=True)
            if isinstance(error, Exception):
                logger.error("Assistant job %s heartbeat cleanup failed", job["id"],
                             exc_info=(type(error), error, error.__traceback__))

    async def _heartbeat_job(self, job: dict[str, Any]) -> None:
        while True:
            await asyncio.sleep(20)
            renewed = await asyncio.to_thread(
                self.store.heartbeat_job,
                str(job["id"]),
                owner=str(job["lease_owner"]),
                lease_epoch=int(job["lease_epoch"]),
            )
            if not renewed:
                return

    async def _extract_memories(self, job: dict[str, Any]) -> dict[str, Any]:
        from shiliu.assistant.memory_extraction import MemoryExtractionService

        return await MemoryExtractionService(
            self.memories,
            provider_factory=self.extraction_provider_factory,
            continue_allowed=self._maintenance_idle,
        ).process(job)

    def _set_capability(self, name: str, status: str, detail: str | None = None) -> None:
        with self._status_lock:
            self._capabilities[name] = status
            if detail:
                self._capabilities[f"{name}_detail"] = detail[:500]


def _merge_usage(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    value = dict(current)
    for key, amount in incoming.items():
        if isinstance(amount, (int, float)):
            value[key] = value.get(key, 0) + amount
    return value
