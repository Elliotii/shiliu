from __future__ import annotations

import asyncio
import json
import re
import threading
import time
import uuid
from typing import Any, Callable, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from shiliu.assistant.context import ContextBudgetExceeded, ContextComposer
from shiliu.assistant.dependencies import Context7MCPClient, Mem0SemanticIndex
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.memory_policy import anchored_validity, forbids_auto_save, plausible_personal_excerpt
from shiliu.assistant.provider import AssistantModelProvider, ModelTurn, NativeToolCall
from shiliu.assistant.sources import CollectionSourceService, SourceScope
from shiliu.assistant.store import AssistantConflict, AssistantRunStore, ModelBudgetWait
from shiliu.assistant.task_notes import TaskNoteService
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.wiki import MaintenanceBudgetExceeded, WikiService
from shiliu.domain import PipelineError


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


class AssistantExecutionGraph:
    def __init__(
        self,
        *,
        store: AssistantRunStore,
        memories: MemoryService,
        tools: AssistantToolRegistry,
        provider_factory: Callable[[], AssistantModelProvider],
        max_steps: int = 8,
        max_tool_calls: int = 12,
    ) -> None:
        self.store = store
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
        self.composer = ContextComposer(
            memories,
            task_notes=self.task_notes,
            source_ref_validator=self._source_refs_valid,
            dependency_ref_validator=self.dependency_ref_validator,
        )
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
        placeholders = ",".join("?" for _ in versioned)
        with self.store.db.connect() as connection:
            rows = connection.execute(
                f"SELECT video_id,current_revision FROM assistant_source_heads "
                f"WHERE video_id IN ({placeholders})",
                list(versioned),
            ).fetchall()
        current = {int(row["video_id"]): str(row["current_revision"]) for row in rows}
        return all(current.get(video_id) == revision for video_id, revision in versioned.items())

    async def run(self, run: dict[str, Any]) -> None:
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
        }
        await self.compiled.ainvoke(state, config={"recursion_limit": 40})

    def _build(self) -> StateGraph:
        graph = StateGraph(ExecutionState)
        graph.add_node("recover", self._recover)
        graph.add_node("model", self._model)
        graph.add_node("tools", self._tools)
        graph.add_node("final", self._final)
        graph.add_edge(START, "recover")
        graph.add_conditional_edges(
            "recover", self._route_after_tools,
            {"model": "model", "tools": "tools", "stopped": END},
        )
        graph.add_conditional_edges(
            "model", self._route_after_model,
            {"tools": "tools", "final": "final", "stopped": END},
        )
        graph.add_conditional_edges(
            "tools", self._route_after_tools,
            {"model": "model", "stopped": END},
        )
        graph.add_conditional_edges(
            "final", self._route_after_final,
            {"model": "model", "stopped": END},
        )
        return graph

    async def _recover(self, state: ExecutionState) -> ExecutionState:
        current = self.store.get_run(state["run_id"])
        if current["status"] != "running" or current["run_epoch"] != state["epoch"]:
            return {**state, "route": "stopped"}
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
            **state, "route": "tools",
            "turn": ModelTurn(text="", tool_calls=calls),
        }

    def _proposal_budget_hint(
        self, state: ExecutionState, context: dict[str, Any]
    ) -> bool:
        """Prompt for a proposal near this segment's limit without removing read tools."""
        remaining = self.max_tool_calls - (state["tool_count"] - state["tool_base"])
        if remaining > 5 or remaining <= 0:
            return False
        user = next((item for item in reversed(context["thread"]["messages"])
                     if item.get("role") == "user" and item.get("run_id") == state["run_id"]), None)
        utterance = str((user or {}).get("content") or "")
        if not (re.search(r"整理|保存|主题|拆成|分成", utterance) and
                re.search(r"两个|两[个类项]|多个|多主题|分别|拆成|分成", utterance)):
            return False
        refs: set[str] = set()
        with self.store.db.connect() as connection:
            calls = connection.execute(
                "SELECT name,result_json FROM assistant_tool_calls WHERE run_id=? AND status='completed'",
                (state["run_id"],),
            ).fetchall()
        if any(row["name"] == "knowledge_propose" for row in calls):
            return False
        for row in calls:
            if row["name"] not in {"collection_read", "knowledge_read"}:
                continue
            try:
                result = json.loads(row["result_json"] or "{}")
            except ValueError:
                continue
            refs.update(str(ref) for ref in result.get("source_refs") or []
                        if str(ref).startswith("video:"))
        return len(refs) >= 2

    async def _model(self, state: ExecutionState) -> ExecutionState:
        current = self.store.get_run(state["run_id"])
        if current["status"] != "running" or current["run_epoch"] != state["epoch"]:
            return {**state, "route": "stopped"}
        if state["step_count"] - state["step_base"] >= self.max_steps:
            self.store.fail_run(
                state["run_id"], code="step_budget_exhausted", message="助手达到最大模型步骤"
            )
            return {**state, "route": "stopped"}
        context = self.store.run_context(state["run_id"])
        tool_schemas = self.tools.schemas()
        proposal_hint = self._proposal_budget_hint(state, context)
        force_compact = bool(current["working_state"].get("context_recovery_attempts"))
        try:
            messages, _estimated_tokens, context_metadata = self.composer.compose_with_metadata(
                context, tool_schemas=tool_schemas, force_compact=force_compact,
            )
        except ContextBudgetExceeded as exc:
            if force_compact or not self.store.mark_context_recovery_attempt(
                state["run_id"], epoch=state["epoch"]
            ):
                self.store.fail_run(state["run_id"], code="context_recovery_failed", message=str(exc))
                return {**state, "route": "stopped"}
            force_compact = True
            context = self.store.run_context(state["run_id"])
            try:
                messages, _estimated_tokens, context_metadata = self.composer.compose_with_metadata(
                    context, tool_schemas=tool_schemas, force_compact=True,
                )
            except ContextBudgetExceeded as retry_exc:
                self.store.fail_run(state["run_id"], code="context_recovery_failed", message=str(retry_exc))
                return {**state, "route": "stopped"}
        try:
            compressed_usage = await self._compress_note_if_needed(
                context, context_metadata, state=state,
            )
        except Exception as exc:
            if not self._run_epoch_active(state):
                return {**state, "route": "stopped"}
            self.store.fail_run(state["run_id"], code="context_compaction_failed",
                                message=f"材料压缩失败：{str(exc)[:180]}")
            return {**state, "route": "stopped"}
        if compressed_usage is not None:
            state = {**state, "usage": _merge_usage(state["usage"], compressed_usage)}
            context = self.store.run_context(state["run_id"])
            try:
                messages, _estimated_tokens, context_metadata = self.composer.compose_with_metadata(
                    context, tool_schemas=tool_schemas, force_compact=force_compact,
                )
            except ContextBudgetExceeded as exc:
                self.store.fail_run(state["run_id"], code="context_recovery_failed", message=str(exc))
                return {**state, "route": "stopped"}
        if not self.store.save_context_observation(
            state["run_id"], epoch=state["epoch"], metadata=context_metadata
        ):
            return {**state, "route": "stopped"}
        if proposal_hint:
            remaining = self.max_tool_calls - (state["tool_count"] - state["tool_base"])
            messages[0] = {**messages[0], "content": str(messages[0]["content"]) +
                           f"\n当前多主题任务本段约剩 {remaining} 次工具调用。优先避免重复搜索；"
                           "如果用户要求完整阅读，或仍有未读游标、精确疑点需要回读，先使用现有读取工具完成必要阅读。"
                           "预算不足以完成前置阅读时，沿现有暂停/未完成反馈处理，不以草案替代阅读。"
                           "已读材料足以满足本次任务时，及时调用 knowledge_propose 给出有来源、"
                           "有边界的待确认提案；未掌握的细节列为待补，不编造来源或把未说明解释为否定。"}
        self.store.reserve_model_request(lane="foreground", request_limit=10000)
        provider = self.provider_factory()
        started = time.monotonic()
        try:
            turn = await asyncio.to_thread(
                provider.turn,
                messages=messages,
                tools=tool_schemas,
                max_tokens=4096,
            )
        except BaseException:
            self.store.record_model_usage(
                lane="foreground", usage=None, outcome="error_or_lost",
                latency_ms=(time.monotonic() - started) * 1000,
            )
            raise
        self.store.record_model_usage(
            lane="foreground", usage=turn.usage or None, outcome="response",
            latency_ms=(time.monotonic() - started) * 1000,
        )
        self.store.confirm_model_delivery(
            state["run_id"], epoch=state["epoch"],
            spans=context_metadata.get("delivered_read_spans") or [],
        )
        current = self.store.get_run(state["run_id"])
        if current["status"] != "running" or current["run_epoch"] != state["epoch"]:
            return {**state, "route": "stopped", "turn": None}
        usage = _merge_usage(state["usage"], turn.usage)
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
                content=turn.text,
                provider_payload={"tool_calls": provider_calls, **turn.opaque_provider_state},
            )
        self.store.save_step(
            state["run_id"], step_count=step_count, tool_count=state["tool_count"], usage=usage
        )
        return {
            **state, "step_count": step_count, "usage": usage, "turn": turn,
            "route": route, "context_metadata": context_metadata,
        }

    async def _compress_note_if_needed(
        self, context: dict[str, Any], metadata: dict[str, Any], *, state: ExecutionState
    ) -> dict[str, Any] | None:
        covered_until = int(metadata.get("covered_until_message_seq") or 0)
        if not covered_until:
            return None
        note = self.task_notes.valid_for_context(
            str(context["thread"]["id"]), space_id=int(context["space"]["id"]),
            scope_version=int(context["space"]["scope_version"]),
        )
        if note is None:
            return None
        prior = max((int(value.get("covered_until_message_seq") or 0)
                     for value in note["findings"] if value.get("kind") == "semantic_summary"), default=0)
        messages = []
        for item in context["thread"]["messages"]:
            seq = int(item.get("seq") or 0)
            if seq <= prior or seq > covered_until or item.get("role") != "tool":
                continue
            if str(item.get("run_id") or "") != state["run_id"]:
                continue
            payload = json.loads(item.get("provider_payload_json") or "{}")
            if payload.get("name") != "collection_read":
                continue
            result = json.loads(item.get("content") or "{}")
            if result.get("status") != "ok":
                continue
            source_ref = next(iter(result.get("source_refs") or []), "")
            if source_ref not in note["dependencies"]:
                continue
            for material in result.get("items") or []:
                content = str(material.get("content") or "") if isinstance(material, dict) else ""
                if len(content) >= 2000:
                    messages.append((seq, source_ref, str(result.get("result_ref") or ""),
                                     result.get("coverage", {}).get("requested_view"),
                                     material.get("provenance", {}).get("content_position"), content))
        if not messages:
            return None
        provider = self.provider_factory()
        total_usage: dict[str, Any] = {}
        for seq, source_ref, result_ref, view, position, content in messages:
            if not self._run_epoch_active(state):
                raise AssistantConflict("semantic_run_terminated")
            prompt = json.dumps({
                "task_goal": note["goal"],
                "explicit_constraints": note["explicit_constraints"],
                "source_ref": source_ref, "view": view, "position": position,
                "material_text": content,
            }, ensure_ascii=False)
            for attempt in range(3):
                if not self._run_epoch_active(state):
                    raise AssistantConflict("semantic_run_terminated")
                self.store.reserve_model_request(lane="foreground", request_limit=10000)
                started = time.monotonic()
                try:
                    if attempt == 2:
                        compact_turn = await asyncio.to_thread(
                            provider.turn,
                            messages=[
                                {"role": "system", "content": "用中文简明压缩当前分段，保留关键条件、分歧和确实未解决的要求。分段结束不代表来源截断；不得把本段未见写成全篇缺失。只依据输入，不补事实。"},
                                {"role": "user", "content": prompt},
                            ],
                            tools=[], max_tokens=1600,
                        )
                        summary, usage = {"summary": compact_turn.text[:4000]}, compact_turn.usage
                    elif hasattr(provider, "generate_json_with_usage"):
                        summary, usage = await asyncio.to_thread(
                            provider.generate_json_with_usage,
                            system=("只压缩已给出的当前分段。按 task_goal 中用户点名的每个主题保留已有直接证据、"
                                    "适用条件、分歧、明确未完成要求和精确回读定位；短暂提及的主题也不能丢失。"
                                    "分段边界不表示原文中断；本段未见的内容不算整篇缺失，不能列为 open_questions。不得把归纳当新证据。"
                                    "只输出 JSON：findings、conditions、disagreements、open_questions，四项均为简短字符串数组。"),
                            prompt=prompt, max_tokens=1800,
                        )
                    else:
                        summary = await asyncio.to_thread(
                            provider.generate_json,
                            system="压缩已给出的材料，保留条件、分歧、未完成要求；只输出 JSON。",
                            prompt=prompt, max_tokens=1800,
                        )
                        usage = {}
                    break
                except BaseException as exc:
                    self.store.record_model_usage(lane="foreground", usage=None,
                                                  outcome="error_or_lost",
                                                  latency_ms=(time.monotonic() - started) * 1000)
                    if (not self._run_epoch_active(state) or attempt == 2
                            or getattr(exc, "code", None) != "wiki_proposal_invalid"):
                        raise
            latency_ms = (time.monotonic() - started) * 1000
            self.store.record_model_usage(lane="foreground", usage=usage or None,
                                          outcome="response", latency_ms=latency_ms)
            if not self._run_epoch_active(state):
                raise AssistantConflict("semantic_run_terminated")
            self.store.record_compaction(
                state["run_id"], epoch=state["epoch"], usage=usage,
                input_characters=len(prompt), latency_ms=latency_ms,
            )
            total_usage = _merge_usage(total_usage, usage)
            semantic = self.task_notes.bound_semantic(summary)
            finding = {
                "kind": "semantic_summary",
                "text": json.dumps(semantic, ensure_ascii=False),
                "semantic": semantic,
                "dependencies": [ref for ref in (source_ref, result_ref) if ref],
                "source_ref": source_ref,
                "source_run_id": state["run_id"],
                "message_seq": seq,
                "covered_until_message_seq": seq,
                "view": view, "position": position,
                "model_derived": True,
            }
            note = self.task_notes.commit_semantic_findings(
                str(context["thread"]["id"]), note, [finding],
                run_id=state["run_id"], run_epoch=state["epoch"],
            )
        return total_usage

    def _run_epoch_active(self, state: ExecutionState) -> bool:
        run = self.store.get_run(state["run_id"])
        return (run["status"] == "running" and run["run_epoch"] == state["epoch"]
                and not run.get("cancel_requested"))

    async def _tools(self, state: ExecutionState) -> ExecutionState:
        turn = state["turn"]
        if turn is None:
            return {**state, "route": "stopped"}
        tool_count = state["tool_count"]
        for call in turn.tool_calls:
            current = self.store.get_run(state["run_id"])
            if current["status"] != "running" or current["run_epoch"] != state["epoch"]:
                return {**state, "route": "stopped", "tool_count": tool_count}
            if self.store.tool_result_message_exists(state["run_id"], call.call_id):
                continue
            if tool_count - state["tool_base"] >= self.max_tool_calls:
                self.store.fail_run(
                    state["run_id"], code="tool_budget_exhausted", message="助手达到最大工具调用次数"
                )
                return {**state, "route": "stopped", "tool_count": tool_count}
            ordinal = tool_count + 1
            existing = self.store.begin_tool_call(
                state["run_id"],
                ordinal=ordinal,
                call_id=call.call_id,
                name=call.name,
                arguments=call.arguments,
                operation_key=f"tool:{state['run_id']}:{call.call_id}",
                reuse_validator=(
                    lambda candidate: self.tools.reusable_result_valid(
                        candidate,
                        run_context=self.store.run_context(state["run_id"]),
                    )
                ) if hasattr(self.tools, "reusable_result_valid") else None,
            )
            if existing is not None and existing.get("result_json"):
                result = json.loads(existing["result_json"])
            else:
                result = await self.tools.execute(
                    name=call.name,
                    arguments=call.arguments,
                    call_id=call.call_id,
                    run_context=self.store.run_context(state["run_id"]),
                )
                current = self.store.get_run(state["run_id"])
                if current["status"] != "running" or current["run_epoch"] != state["epoch"]:
                    return {**state, "route": "stopped", "tool_count": tool_count}
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
                tool_count=tool_count, usage=state["usage"],
            )
        self.store.save_step(
            state["run_id"], step_count=state["step_count"], tool_count=tool_count, usage=state["usage"]
        )
        return {**state, "tool_count": tool_count, "route": "model", "turn": None}

    async def _final(self, state: ExecutionState) -> ExecutionState:
        turn = state["turn"]
        if turn is None:
            return {**state, "route": "stopped"}
        current = self.store.get_run(state["run_id"])
        if current["status"] != "running" or current["run_epoch"] != state["epoch"]:
            return {**state, "route": "stopped"}
        metadata = state.get("context_metadata") or {}
        outcome = self.store.try_complete_run(
            state["run_id"], epoch=state["epoch"],
            answer=self._presentable_answer(turn.text),
            usage=state["usage"],
            expected_scope_version=int(metadata.get("scope_version") or 0),
            expected_observed_memory_epoch=int(metadata.get("observed_memory_epoch") or 0),
            dependency_refs=[str(value) for value in metadata.get("dependency_refs") or []],
            expected_task_note_version=(
                int(metadata["task_note_version"])
                if metadata.get("task_note_version") is not None else None
            ),
            dependency_validator=self.dependency_ref_validator,
        )
        if outcome == "completed":
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

    @staticmethod
    def _presentable_answer(raw: str) -> str:
        answer = raw.strip()
        while True:
            first, newline, rest = answer.partition("\n")
            if not (
                newline and rest.strip() and len(first) <= 180
                and re.search(r"[\u4e00-\u9fff]", rest)
                and not re.search(r"[\u4e00-\u9fff]", first)
                and re.match(r"(?i)^(?:I\s|Here's\s|Here is\s|Let me\s|Now I\s|The cursor\s)", first)
            ):
                break
            answer = rest.strip()
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
        store: AssistantRunStore,
        sources: CollectionSourceService,
        memory_backend: Mem0SemanticIndex,
        context7: Context7MCPClient,
        provider_factory: Callable[[], AssistantModelProvider],
        extraction_provider_factory: Callable[[], AssistantModelProvider] | None = None,
    ) -> None:
        self.store = store
        self.sources = sources
        self.memory_backend = memory_backend
        self.context7 = context7
        self.provider_factory = provider_factory
        self.extraction_provider_factory = extraction_provider_factory or provider_factory
        self.memories = MemoryService(store.db, backend=memory_backend)
        self.wiki = WikiService(db=store.db, store=store, sources=sources)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._status_lock = threading.Lock()
        self._capabilities: dict[str, Any] = {
            "runtime": "stopped", "memory_index": "unknown", "context7": "unknown"
        }

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._ready.clear()
        self._thread = threading.Thread(target=self._thread_main, name="shiliu-assistant", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=30)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            # Fence any in-flight provider/tool result before waiting for the
            # blocking transport call to unwind.
            self.store.recover_interrupted_runs()
            self._thread.join(timeout=30)
            if not self._thread.is_alive():
                self._thread = None

    def capabilities(self) -> dict[str, Any]:
        with self._status_lock:
            return dict(self._capabilities)

    def _thread_main(self) -> None:
        asyncio.run(self._serve())

    async def _serve(self) -> None:
        self.store.recover_interrupted_runs()
        memory_ready = False
        try:
            await asyncio.to_thread(self.memory_backend.start)
            memory_ready = True
            self.store.requeue_blocked_memory_jobs()
            self._set_capability("memory_index", "ready")
        except Exception as exc:
            self.memories.backend = None
            self._set_capability("memory_index", "unavailable", str(exc))
        context7_ready = False
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
        graph = AssistantExecutionGraph(
            store=self.store,
            memories=self.memories,
            tools=registry,
            provider_factory=self.provider_factory,
        )
        self._set_capability("runtime", "ready")
        self._ready.set()
        try:
            await asyncio.gather(
                self._foreground_loop(graph), self._background_loop()
            )
        finally:
            if context7_ready:
                await self.context7.close()
            if memory_ready:
                await asyncio.to_thread(self.memory_backend.stop)
            self._set_capability("runtime", "stopped")

    async def _foreground_loop(self, graph: AssistantExecutionGraph) -> None:
        while not self._stop.is_set():
            run = self.store.claim_next_run()
            if run is None:
                await asyncio.sleep(0.2)
                continue
            try:
                await graph.run(run)
            except Exception as exc:
                code = str(getattr(exc, "code", None) or type(exc).__name__)
                self.store.fail_run(str(run["id"]), code=code, message=str(exc))

    async def _background_loop(self) -> None:
        # One background job at a time, independent of the foreground model
        # loop. A running extraction may finish, but a new one waits for idle.
        while not self._stop.is_set():
            foreground_active = self.store.has_active_runs()
            starved = foreground_active and self.store.model_job_wait_exceeded(30)
            job = self.store.claim_job(
                owner=f"runtime-{uuid.uuid4().hex[:8]}",
                allow_model_jobs=not foreground_active or starved,
                scheduler_reason=(
                    "wait_age_promotion" if starved
                    else "foreground_idle" if not foreground_active
                    else "non_model_while_foreground"
                ),
            )
            if job is None:
                await asyncio.sleep(0.2)
                continue
            await self._process_job(job)

    async def _process_job(self, job: dict[str, Any]) -> None:
        heartbeat = asyncio.create_task(self._heartbeat_job(job))
        try:
            kind = str(job["kind"])
            payload = job["payload"]
            if kind == "memory_index":
                result = await asyncio.to_thread(
                    self.memories.project,
                    memory_id=str(payload["memory_id"]),
                    version=int(payload["version"]),
                    old_backend_id=payload.get("old_backend_id"),
                )
            elif kind == "memory_purge":
                result = await asyncio.to_thread(
                    self.memories.purge,
                    memory_id=str(payload["memory_id"]),
                    version=int(payload["version"]),
                    backend_id=payload.get("backend_id"),
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
            self.store.finish_job(
                str(job["id"]), proposal=result,
                owner=str(job["lease_owner"]), lease_epoch=int(job["lease_epoch"]),
            )
        except ModelBudgetWait as exc:
            self.store.defer_job_for_budget(job, message=str(exc))
        except MaintenanceBudgetExceeded as exc:
            self.store.defer_job_for_batch_budget(job, message=str(exc))
        except Exception as exc:
            code = str(getattr(exc, "code", None) or type(exc).__name__)
            blocked = code in {"api_key_missing", "provider_auth", "memory_backend_unavailable"}
            self.store.fail_job(job, code=code, message=str(exc), blocked=blocked)
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

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
        payload = job["payload"]
        def policy_matches() -> bool:
            policy = self.memories.auto_policy()
            return (payload.get("auto_enabled_at_enqueue") is True
                    and policy["enabled"]
                    and int(payload.get("auto_memory_generation", -1)) == policy["generation"])
        if not policy_matches():
            return {"proposals": [], "applied_memory_ids": [], "reason": "automatic_memory_policy_changed"}
        context = self.store.get_thread(str(payload["thread_id"]))
        message_ids = set(str(value) for value in payload["message_ids"])
        user_messages = [
            item for item in context["messages"]
            if item["id"] in message_ids and item["role"] == "user"
        ]
        if not user_messages:
            return {"proposals": [], "applied_memory_ids": [], "reason": "no_unprocessed_user_messages"}
        if any(forbids_auto_save(str(item["content"])) for item in user_messages):
            return {"proposals": [], "applied_memory_ids": [], "reason": "user_forbids_auto_save"}
        if all(re.fullmatch(r"(?:这次|本次|这个回答)?(?:回答)?(?:请)?(?:短一点|简短些|用中文|列三条|不要表格)[。！! ]*",
                            str(item["content"]).strip()) for item in user_messages):
            return {"proposals": [], "applied_memory_ids": [], "reason": "format_only"}
        raw_user = "\n".join(
            f"{item['id']} [{item['created_at']}]: {item['content']}" for item in user_messages
        )
        user_text = "\n".join(str(item["content"]) for item in user_messages)
        thread_space = self.store.get_space(int(context["space_id"]))
        message_positions = [
            index for index, item in enumerate(context["messages"])
            if item["id"] in message_ids
        ]
        nearby: list[str] = []
        if message_positions:
            start = max(0, min(message_positions) - 2)
            for item in context["messages"][start:min(message_positions)]:
                nearby.append(
                    f"{item['role']} [{item['created_at']}]: {str(item['content'])[:2000]}"
                )
        nearby_text = "\n".join(nearby) if nearby else "（无）"
        related = self.memories.recall(user_text[:300], space_id=int(context["space_id"]), limit=5)
        related_text = "\n".join(
            f"{item['id']} v{item['version']} [{item['kind']}] {item['text']}"
            for item in related
        ) or "（无）"
        prompt = (
            "从以下用户消息中提取最多 5 条可跨会话使用的个人背景。"
            "用户无需说‘记住’：例如‘今天确定接下来三周主要补数据库基础’是可保存的阶段目标，"
            "应输出 op=add、kind=context、scope_kind=space 的提案；本轮格式要求才输出空列表。"
            "有日期或持续时长的目标需要保留时间依据；正在比较只能记为探索状态，不得写成决定。"
            "视频/文档观点、引用内容、工具结果和助手回答不得成为用户立场。"
            "‘我不同意 X’不等于采用 X；‘我决定采用 X’才是明确决定。"
            "邻近上下文只用于解释指代，source_excerpt 必须逐字来自本次用户消息。"
            "用户给出期限时，可返回带时区的 valid_from/expires_at、validity_note 和"
            "validity_timezone；无法可靠确定精确时间时只保留 validity_note，不猜时间。"
            "返回 {\"proposals\":[{op,kind,text,subject_key,scope_kind,scope_id,"
            "source_excerpt,target_memory_id?,expected_version?,valid_from?,expires_at?,"
            "validity_note?,validity_timezone?}]}。scope 默认 space，时区默认 Asia/Shanghai。\n"
            f"当前 Space id={thread_space['id']} name={thread_space['name']}。"
            f"\n相关现有正式记忆（修订须给出这里的 ID 和版本）：\n{related_text}"
            f"\n邻近解释上下文：\n{nearby_text}"
            f"\n本次用户消息：\n{raw_user}"
        )
        provider = self.extraction_provider_factory()
        self.store.reserve_model_request(lane="background", request_limit=60)
        started = time.monotonic()
        try:
            proposals = await asyncio.to_thread(provider.extract_memories, prompt=prompt)
        except BaseException:
            self.store.record_model_usage(
                lane="background", usage=None, outcome="error_or_lost",
                latency_ms=(time.monotonic() - started) * 1000,
            )
            raise
        self.store.record_model_usage(
            lane="background", usage=None, outcome="response_usage_unavailable",
            latency_ms=(time.monotonic() - started) * 1000,
        )
        saved_proposal = {"proposals": proposals}
        if not self.store.save_job_proposal(
            str(job["id"]), saved_proposal,
            owner=str(job["lease_owner"]), lease_epoch=int(job["lease_epoch"]),
        ):
            raise RuntimeError("job_lease_lost")
        if not policy_matches():
            return {"proposals": proposals, "applied_memory_ids": [],
                    "reason": "automatic_memory_policy_changed"}
        applied: list[str] = []
        for index, proposal in enumerate(proposals[:5]):
            if not policy_matches():
                break
            excerpt = str(proposal.get("source_excerpt") or "")
            if (
                not excerpt
                or excerpt not in user_text
                or not plausible_personal_excerpt(excerpt, str(proposal.get("kind") or "context"))
            ):
                continue
            source = next((item for item in user_messages if excerpt in str(item["content"])), None)
            if source is None:
                continue
            time_bounds = anchored_validity(excerpt, str(source["created_at"]))
            if time_bounds is None:
                continue
            if time_bounds:
                proposal.update(time_bounds)
                proposal["valid_from"] = None
            elif re.search(r"下个月|月底|过几天|近期", excerpt) and not proposal.get("expires_at"):
                continue
            if str(proposal.get("op")) == "revise":
                if not any(str(item["id"]) == str(proposal.get("target_memory_id"))
                           and int(item["version"]) == int(proposal.get("expected_version") or 0)
                           for item in related):
                    continue
            requested_scope = str(proposal.get("scope_kind") or "space")
            global_markers = ("以后默认", "长期", "所有项目", "跨项目")
            if requested_scope != "user" or not any(marker in excerpt for marker in global_markers):
                proposal["scope_kind"] = "space"
                proposal["scope_id"] = int(thread_space["id"])
            value = self.memories.apply_extracted(
                proposal,
                source_message_ids=[str(source["id"])],
                expected_epoch=int(payload["memory_epoch"]),
                operation_key=f"extract:{job['id']}:{index}",
                expected_auto_generation=int(payload.get("auto_memory_generation", -1)),
            )
            if value is not None:
                applied.append(str(value["id"]))
        return {"proposals": proposals, "applied_memory_ids": applied,
                "reason": ("applied" if applied else
                           "automatic_memory_policy_changed" if not policy_matches()
                           else "no_admissible_proposal")}

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
