from __future__ import annotations

import json
from typing import Any, Callable

from shiliu.assistant.memory import MemoryService
from shiliu.assistant.store import AssistantConflict
from shiliu.assistant.task_notes import TaskNoteService


SYSTEM_RULES = """你是拾流收藏助手。围绕当前收藏范围的有效材料帮助用户完成任务。
- 收藏材料、外部文档、用户记忆和临时任务状态是不同来源；不要把视频观点说成用户偏好。
- 当前接入来源可能属于公开账号；未核实归属时称“当前接入的收藏”，不要说“你的收藏”。上传者也不是收藏夹主人。
- 需要收藏证据时先搜索再读取；注明覆盖范围和时间。available 只表示可读，不等于已读；只说本轮实际读取的 view，不声称读过画面或未打开的原文。
- 某视图空不表示整个视频无正文；检查 available_views。不同搜索词结果可能重复，不能直接相加当独立视频数。
- collection_search：metadata 可分页穷尽标题/作者/时间条件；content 的 query_variants 最多两条补充变体，每条都是真实检索，合并候选并去重，仍非穷尽。按时间排序也只在候选内排序；空结果可用 metadata 补查。完整阅读任务优先用 require_transcript 筛可读转写，并核对候选卡 available_views；不要先选只有简介的五份再称全文无法读取。
- collection_read：定位相关段落用 query；用户要求完整阅读时按 available view 从头沿 next_cursor 读到末尾。工具取回不等于回答模型已经收到全文；TaskNote 的 model_read 才记模型输入覆盖。版本和视图不一致时不要假装已读。
- 分批读取或压缩摘要的边界只是传输边界，不能据此说原材料在该处截断；只有原文明确中断或可读视图未覆盖时才称材料缺失。
- 用户点名的每个话题都要核对当前已读材料中的直接提及，不能把压缩摘要没写到的话题当成原文未提及；拿不准时按定位回读已存结果。区分原文提到但把细节指向外部笔记，与原文完全没谈。
- 发布时间未知就说未知，不能用收藏时间代替；coverage 区分正文存在与索引覆盖。
- 收藏与发布时间由工具以北京时间（Asia/Shanghai，+08:00）返回；展示时保留其日期和时区，不按 UTC 日期截断。
- 用户明确要求记住、纠正或忘记时调用对应 memory 工具；仅本轮的格式要求不要保存。
- 本轮用户明确给出的背景应立即用于本轮回答。只有 memory 工具返回成功回执后才能说“已记住”；自动后台提炼未完成时只能说“已用于本次回答”。“记住并找材料”等复合要求要完成后续搜索和回答，不能保存后收尾。
- 记忆工具中的 memory_id、subject_key、version、scope_kind、epoch、索引状态只用于内部一致性校验；回答只描述用户可理解的记忆内容、适用范围和是否仍有效。正常成功或空结果禁止提及 SQLite、Mem0、backend、索引 ready/unavailable、权威存储；只有工具真正不可用且影响回答时才用用户语言简短说明。
- 用户只要求忘记一条记忆且工具已成功时，简短确认该条已失效及明确未动的内容，不续写以前的材料比较或实验建议。当前上下文未保留的旧工具结果不等于从未读取或主题不存在；需要谈旧材料时先按需回读。
- 涉及软件 API 或版本时可以调用 Context7；只发送必要的公开技术问题，不发送私人字幕或用户记忆。
- 普通问答不要建页。用户明确保存一项已有讨论成果时，用 knowledge_save_outcome 保存精选结论；材料说法、你的分析、用户个人笔记逐块标清角色，真正依赖正式记忆才引用其当前 ID/version。自动记忆开关不控制明确知识保存。
- 多领域或复数主题整理先用 knowledge_propose 给出每页用途、材料、交叉参考和不纳入项，等待真实用户确认；确认时用 knowledge_confirm，逐页结果分别报告。提案先用少量 summary 视图定位各材料的核心条件；对用户点名的精确条件，若摘要未说清，再按需定位字幕，不能因一个转写片段未覆盖就断言整份材料没说。已有足够区分主题的材料时就提出有边界的草案，不要为了补齐所有细节反复搜索直到工具预算耗尽；确实未见的内容列入不纳入项。简单单主题材料整理可用 knowledge_organize，受理不等于页面完成。明确禁止知识保存时不调用任何知识写工具。
- 比较不同材料时区分直接冲突、条件不同和信息不足。同一动作的默认开关、频率或门槛不同，而一方未交代关键前提时，应说明存在尚未解决的策略张力；“定期”不能自行补成默认开启或固定周期。加条件使两者兼容只能作为你的设计建议，不能断言材料已经兼容或达成共识。开头判断与后文未决条件保持一致。
- 读取主题页只表示本轮读过主题，不等于亲自重读其每份原材料；若另查过收藏元数据，也如实区分搜索与正文阅读。主题已存在时不要建议再创建同一主题。主题内部版本号、assessment、来源 key 和队列状态不写进普通回答；时间只在确有必要且工具给出准确值时陈述，不用模糊日期填空。
- 工具失败要如实说明。不要伪造 source_ref、libraryId 或工具结果。
- 只给用户中文最终答案，不输出英文过程旁白；正文和末尾追问都只用标题引用材料，绝不输出 video:ID、page_id、result_ref、cursor、scope_version 等内部字段。
"""


class ContextBudgetExceeded(ValueError):
    code = "context_budget_exceeded"


class ContextComposer:
    def __init__(
        self,
        memories: MemoryService,
        *,
        task_notes: TaskNoteService | None = None,
        input_budget_tokens: int = 24000,
        compression_threshold: float = 0.8,
        recent_groups: int = 4,
        source_ref_validator: Callable[[list[str], int], bool] | None = None,
        dependency_ref_validator: Callable[[list[str], int, str, int], bool] | None = None,
    ) -> None:
        self.memories = memories
        self.task_notes = task_notes
        self.input_budget_tokens = input_budget_tokens
        self.compression_threshold = compression_threshold
        self.recent_groups = recent_groups
        self.source_ref_validator = source_ref_validator
        self.dependency_ref_validator = dependency_ref_validator

    def compose(
        self, run_context: dict[str, Any], *, tool_schemas: list[dict[str, Any]] | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        messages, estimated, _metadata = self.compose_with_metadata(
            run_context, tool_schemas=tool_schemas
        )
        return messages, estimated

    def compose_with_metadata(
        self, run_context: dict[str, Any], *, tool_schemas: list[dict[str, Any]] | None = None,
        force_compact: bool = False,
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        thread = run_context["thread"]
        space = run_context["space"]
        run_id = str(run_context.get("run", {}).get("id") or "")
        all_messages = thread["messages"]
        abandoned_run_ids = {
            str(item["id"]) for item in thread.get("runs", [])
            if item.get("status") == "cancelled"
        }
        current_user_index = next(
            (index for index in range(len(all_messages) - 1, -1, -1)
             if all_messages[index]["role"] == "user"
             and (not run_id or all_messages[index].get("run_id") == run_id)),
            None,
        )
        if current_user_index is None:
            raise ContextBudgetExceeded("当前用户消息不可用，请重新提问")
        current_user = all_messages[current_user_index]
        query = str(current_user["content"])
        note = None
        if self.task_notes is not None:
            note = self.task_notes.valid_for_context(
                str(thread["id"]), space_id=int(space["id"]),
                scope_version=int(space["scope_version"]),
            )
        recall_query = query + ("\n" + str(note.get("goal") or "")[:180] if note else "")
        recall = self.memories.recall_with_status(recall_query, space_id=int(space["id"]), limit=8)
        recalled = recall["items"]
        observed_epoch = int(recall["memory_epoch"])
        memory_block = "\n".join(
            self._memory_line(item)
            for item in recalled
        ) or "（没有匹配的长期记忆）"
        memory_status = (
            "ready（已回查 SQLite）"
            if recall["semantic_index"] == "ready"
            else "unavailable（SQLite/有限词法降级）"
        )
        conflict_rule = (
            "\n同一事项跨范围冲突：当前 Space 的明确决定优先；仍冲突时向用户说明。"
            if any(item.get("scope_conflict") for item in recalled) else ""
        )
        suppressed_ids = self.memories.suppressed_source_message_ids(space_id=int(space["id"]))
        # A legacy answer or tool result may predate dependency_refs. If the
        # user message that started its run was later corrected or forgotten,
        # exclude the whole historical run so its derived answer cannot restore
        # the superseded constraint through ordinary conversation history.
        suppressed_run_ids = {
            str(item.get("run_id"))
            for item in all_messages
            if str(item.get("id") or "") in suppressed_ids and item.get("run_id")
        }
        current_forget_receipts = self._current_forget_receipts(
            all_messages,
            run_id=run_id,
            space_id=int(space["id"]),
            thread_id=str(thread.get("id") or ""),
            scope_version=int(space["scope_version"]),
        ) if run_id in suppressed_run_ids else {}
        visible_messages: list[dict[str, Any]] = []
        for item in all_messages:
            if item is current_user:
                visible_messages.append(item)
                continue
            if str(item.get("run_id") or "") in abandoned_run_ids:
                continue
            if str(item.get("run_id") or "") in suppressed_run_ids:
                if str(item.get("run_id") or "") != run_id:
                    continue
                payload = json.loads(item.get("provider_payload_json") or "{}")
                if item.get("role") == "tool":
                    call_id = str(payload.get("tool_call_id") or "")
                    if call_id in current_forget_receipts:
                        visible_messages.append({
                            **item,
                            "content": json.dumps(
                                current_forget_receipts[call_id], ensure_ascii=False
                            ),
                        })
                elif item.get("role") == "assistant" and payload.get("tool_calls"):
                    calls = [
                        call for call in payload["tool_calls"]
                        if str(call.get("id") or "") in current_forget_receipts
                    ]
                    if calls:
                        visible_messages.append({
                            **item,
                            "content": "",
                            "provider_payload_json": json.dumps(
                                {**payload, "tool_calls": calls}, ensure_ascii=False
                            ),
                        })
                continue
            if (
                str(item.get("id") or "") not in suppressed_ids
                and self._message_dependencies_valid(
                    item,
                    space_id=int(space["id"]),
                    thread_id=str(thread.get("id") or ""),
                    scope_version=int(space["scope_version"]),
                )
            ):
                visible_messages.append(item)
        visible_current_index = visible_messages.index(current_user)
        tool_schema_cost = self._estimate(json.dumps(tool_schemas or [], ensure_ascii=False))
        history_groups = self._message_groups(visible_messages[:visible_current_index])
        current_tail = self._message_groups(visible_messages[visible_current_index + 1:])
        compressible_groups = [*history_groups, *current_tail]
        full_history_cost = sum(
            self._group_cost([self._provider_message(item) for item in group])
            for group in compressible_groups
        )
        compressed = force_compact or note is not None or (
            full_history_cost + tool_schema_cost >= int(self.input_budget_tokens * self.compression_threshold)
        )
        if compressed and self.task_notes is not None and compressible_groups:
            keep_groups = (
                0 if force_compact else
                1 if full_history_cost + tool_schema_cost >= int(self.input_budget_tokens * self.compression_threshold)
                else self.recent_groups
            )
            covered_groups = (
                compressible_groups if force_compact
                else compressible_groups[:-keep_groups]
            )
            covered_until = max(
                (int(item.get("seq") or 0) for group in covered_groups for item in group),
                default=int(note["covered_until_message_seq"]) if note else 0,
            )
            if covered_until > (int(note["covered_until_message_seq"]) if note else 0):
                note_context = {
                    **run_context,
                    "run": {**run_context["run"], "observed_memory_epoch": observed_epoch},
                }
                candidate = self.task_notes.build_candidate(
                    note_context,
                    messages=visible_messages,
                    recalled_memories=recalled,
                    covered_until_message_seq=covered_until,
                )
                try:
                    note = self.task_notes.commit(str(thread["id"]), candidate)
                except AssistantConflict:
                    note = self.task_notes.valid_for_context(
                        str(thread["id"]), space_id=int(space["id"]),
                        scope_version=int(space["scope_version"]),
                    )
        source_titles, search_evidence = self._material_identity(visible_messages)
        delivered_spans = [
            span for run in thread.get("runs", [])
            for span in run.get("working_state", {}).get("model_delivered_read_spans", [])
        ]
        note_block = (
            "\n当前任务笔记（用于继续任务，不是长期记忆）：\n"
            + self.task_notes.render(note, delivered_spans=delivered_spans,
                                     source_titles=source_titles, search_evidence=search_evidence)
            if note is not None and self.task_notes is not None else ""
        )
        system = (
            SYSTEM_RULES
            + f"\n当前收藏范围：{space['name']}；目标：{space['goal'] or '未设置'}；"
            + f"\n记忆索引：{memory_status}{conflict_rule}"
            + f"\n当前有效记忆：\n{memory_block}"
            + note_block
        )
        system_message = {"role": "system", "content": system}
        current_message = self._provider_message(current_user)
        required_cost = self._cost(system_message) + self._cost(current_message) + tool_schema_cost
        if required_cost > self.input_budget_tokens and note is not None and self.task_notes is not None:
            compact_note = self.task_notes.render(note, compact=True)
            system_message = {"role": "system", "content": system.replace(note_block,
                "\n当前任务笔记（精简；完整笔记及结果可回读）：\n" + compact_note)}
            required_cost = self._cost(system_message) + self._cost(current_message) + tool_schema_cost
        if required_cost > self.input_budget_tokens:
            raise ContextBudgetExceeded("当前要求超出上下文容量，请分段提供；原文已保存，未被截断")

        remaining = self.input_budget_tokens - required_cost
        if note is not None:
            covered_until = int(note["covered_until_message_seq"])
            history_groups = [
                group for group in history_groups
                if max(int(item.get("seq") or 0) for item in group) > covered_until
            ]
            current_tail = [
                group for group in current_tail
                if max(int(item.get("seq") or 0) for item in group) > covered_until
            ]
        chosen_tail: list[list[dict[str, Any]]] = []
        chosen_dependency_refs: list[str] = []
        for group in reversed(current_tail):
            projected = [self._provider_message(item) for item in group]
            fitted = self._fit_group(projected, remaining)
            if fitted is None:
                if note is not None and max(int(item.get("seq") or 0) for item in group) <= int(note["covered_until_message_seq"]):
                    continue
                raise ContextBudgetExceeded("本轮工具结果超出上下文容量，请缩小读取范围后继续")
            chosen_tail.append(fitted)
            chosen_dependency_refs.extend(self._group_dependency_refs(group))
            remaining -= self._group_cost(fitted)

        chosen_history: list[list[dict[str, Any]]] = []
        for group in reversed(history_groups):
            projected = [self._provider_message(item) for item in group]
            fitted = self._fit_group(projected, remaining)
            if fitted is None:
                continue
            chosen_history.append(fitted)
            chosen_dependency_refs.extend(self._group_dependency_refs(group))
            remaining -= self._group_cost(fitted)

        messages = [system_message]
        for group in reversed(chosen_history):
            messages.extend(group)
        messages.append(current_message)
        for group in reversed(chosen_tail):
            messages.extend(group)
        estimated = self.input_budget_tokens - remaining
        dependencies = [
            str(item["dependency_ref"]) for item in recalled if item.get("dependency_ref")
        ]
        if note is not None:
            dependencies.extend(str(value) for value in note["dependencies"])
        dependencies.extend(chosen_dependency_refs)
        dependencies = list(dict.fromkeys(dependencies))
        metadata = {
            "observed_memory_epoch": observed_epoch,
            "dependency_refs": dependencies,
            "memory_dependency_refs": [
                value for value in dependencies if value.startswith("memory:")
            ],
            "task_note_version": int(note["note_version"]) if note else None,
            "task_note_id": str(note["id"]) if note else None,
            "scope_version": int(space["scope_version"]),
            "estimated_input_tokens": estimated,
            "uncompressed_history_tokens": full_history_cost,
            "retained_history_tokens": sum(
                self._group_cost(group) for group in chosen_history
            ) + sum(self._group_cost(group) for group in chosen_tail),
            "tool_schema_tokens": tool_schema_cost,
            "compressed": bool(note),
            "force_compact": force_compact,
            "covered_until_message_seq": int(note["covered_until_message_seq"]) if note else 0,
            "delivered_read_spans": self._delivered_read_spans([*chosen_history[::-1], *chosen_tail[::-1]]),
        }
        return messages, estimated, metadata

    @staticmethod
    def _delivered_read_spans(groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
        spans: list[dict[str, Any]] = []
        for group in groups:
            for item in group:
                if item.get("role") != "tool":
                    continue
                try:
                    payload = json.loads(str(item.get("content") or "{}"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                for value in payload.get("items") or []:
                    if not isinstance(value, dict):
                        continue
                    position = value.get("provenance", {}).get("content_position") or {}
                    if not position or not value.get("content"):
                        continue
                    spans.append({
                        "source_ref": payload.get("source_refs", [None])[0],
                        "view": payload.get("coverage", {}).get("requested_view"),
                        "start": int(position.get("start") or 0),
                        "end": int(position.get("end") or 0),
                        "total": int(position.get("total") or 0),
                        "message_seq": item.get("seq"),
                    })
        return spans

    def _current_forget_receipts(
        self,
        messages: list[dict[str, Any]],
        *,
        run_id: str,
        space_id: int,
        thread_id: str,
        scope_version: int,
    ) -> dict[str, dict[str, Any]]:
        """Project only verified success, with the forgotten record body removed."""
        if not run_id or self.dependency_ref_validator is None:
            return {}
        receipts: dict[str, dict[str, Any]] = {}
        for item in messages:
            if item.get("run_id") != run_id or item.get("role") != "tool":
                continue
            payload = json.loads(item.get("provider_payload_json") or "{}")
            if payload.get("name") != "memory_forget":
                continue
            call_id = str(payload.get("tool_call_id") or "")
            if not call_id:
                continue
            try:
                result = json.loads(str(item.get("content") or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if result.get("status") != "ok":
                continue
            result_ref = f"run-result:{run_id}:{call_id}"
            if not self.dependency_ref_validator(
                [result_ref], space_id, thread_id, scope_version
            ):
                continue
            receipts[call_id] = {
                "status": "ok",
                "summary": "已忘记该记忆",
                "items": [{"status": "forgotten"}],
                "result_ref": result_ref,
                "operation_receipt_verified": True,
            }
        return receipts

    def _message_dependencies_valid(
        self,
        item: dict[str, Any],
        *,
        space_id: int,
        thread_id: str,
        scope_version: int,
    ) -> bool:
        refs: list[str] = []
        payload = json.loads(item.get("provider_payload_json") or "{}")
        refs.extend(str(value) for value in payload.get("dependency_refs") or [])
        if item.get("role") == "tool":
            try:
                result = json.loads(str(item.get("content") or "{}"))
                refs.extend(str(value) for value in result.get("dependency_refs") or [])
                refs.extend(str(value) for value in result.get("source_refs") or [])
                if result.get("result_ref"):
                    refs.append(str(result["result_ref"]))
                for value in result.get("items") or []:
                    if isinstance(value, dict) and value.get("id") and value.get("version"):
                        if str(payload.get("name") or "").startswith("memory_"):
                            refs.append(f"memory:{value['id']}:{int(value['version'])}")
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        memory_refs = [value for value in refs if value.startswith("memory:")]
        if memory_refs and not self.memories.validate_dependency_refs(
            memory_refs, space_id=space_id
        )["valid"]:
            return False
        source_refs = [value for value in refs if value.startswith("video:")]
        if source_refs and self.source_ref_validator is not None and not self.source_ref_validator(
            source_refs, space_id
        ):
            return False
        result_refs = [value for value in refs if value.startswith("run-result:")]
        return (
            not result_refs
            or self.dependency_ref_validator is None
            or self.dependency_ref_validator(
                result_refs,
                space_id,
                thread_id,
                scope_version,
            )
        )

    @staticmethod
    def _memory_line(item: dict[str, Any]) -> str:
        scope = "当前 Space" if item["scope_kind"] == "space" else "全局用户"
        validity = ""
        if item.get("valid_from") or item.get("expires_at") or item.get("validity_note"):
            validity = (
                f"；有效期={item.get('valid_from') or '未指定起点'}"
                f" 至 {item.get('expires_at') or '未指定终点'}"
            )
            if item.get("validity_note"):
                validity += f"（用户原话：{item['validity_note']}）"
        conflict = "；同 subject 存在跨范围条件" if item.get("scope_conflict") else ""
        return f"- [memory_id={item['id']} version={item['version']}；{scope}{validity}{conflict}] {item['text']}"

    def _fit_group(
        self, group: list[dict[str, Any]], remaining: int
    ) -> list[dict[str, Any]] | None:
        if self._group_cost(group) <= remaining:
            return group
        if not group or not group[0].get("tool_calls"):
            return None
        # Keep the native call and every corresponding result. The full durable
        # result stays in SQLite; the model receives a compact, explicit index.
        compacted = [group[0]]
        for result in group[1:]:
            if result["role"] != "tool":
                return None
            raw = str(result.get("content") or "")
            try:
                payload = json.loads(raw)
                refs = payload.get("source_refs") or []
                dependency_refs = payload.get("dependency_refs") or []
                summary = str(payload.get("summary") or "")[:180]
                result_ref = str(payload.get("result_ref") or "") or f"tool_call_id:{result['tool_call_id']}"
            except (TypeError, ValueError):
                refs, dependency_refs, summary = [], [], raw[:180]
                result_ref = f"tool_call_id:{result['tool_call_id']}"
            compacted.append({
                **result,
                "content": json.dumps({
                    "status": "partial", "summary": summary,
                    "source_refs": refs,
                    "dependency_refs": dependency_refs,
                    "result_ref": result_ref,
                    "detail_omitted_for_context_budget": True,
                }, ensure_ascii=False),
            })
        return compacted if self._group_cost(compacted) <= remaining else None

    @classmethod
    def _group_dependency_refs(cls, group: list[dict[str, Any]]) -> list[str]:
        refs: list[str] = []
        for item in group:
            payload = json.loads(item.get("provider_payload_json") or "{}")
            refs.extend(str(value) for value in payload.get("dependency_refs") or [])
            if item.get("role") != "tool":
                continue
            try:
                result = json.loads(str(item.get("content") or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            refs.extend(str(value) for value in result.get("dependency_refs") or [])
            refs.extend(str(value) for value in result.get("source_refs") or [])
            if result.get("result_ref"):
                refs.append(str(result["result_ref"]))
            tool_name = str(payload.get("name") or "")
            if tool_name.startswith("memory_"):
                for value in result.get("items") or []:
                    if isinstance(value, dict) and value.get("id") and value.get("version"):
                        refs.append(f"memory:{value['id']}:{int(value['version'])}")
        return list(dict.fromkeys(refs))

    @staticmethod
    def _material_identity(messages: list[dict[str, Any]]) -> tuple[dict[str, str], list[dict[str, Any]]]:
        titles: dict[str, str] = {}
        calls: dict[str, dict[str, Any]] = {}
        searches: list[dict[str, Any]] = []
        for item in messages:
            payload = json.loads(item.get("provider_payload_json") or "{}")
            if item.get("role") == "assistant":
                for call in payload.get("tool_calls") or []:
                    try:
                        args = json.loads(call["function"].get("arguments") or "{}")
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        args = {}
                    calls[str(call.get("id") or "")] = args
            if item.get("role") != "tool":
                continue
            try:
                result = json.loads(item.get("content") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if result.get("status") != "ok":
                continue
            values = [value for value in result.get("items") or [] if isinstance(value, dict)]
            for value in values:
                ref = str(value.get("source_ref") or "")
                video = value.get("video") or {}
                title = str(value.get("title") or video.get("title") or "")[:160]
                if ref.startswith("video:") and title:
                    titles[ref.split(":", 2)[1]] = title
            if payload.get("name") == "collection_search":
                args = calls.get(str(payload.get("tool_call_id") or ""), {})
                searches.append({
                    "query": str(args.get("query") or "")[:160],
                    "require_transcript": bool(args.get("require_transcript")),
                    "returned_count": len(values),
                    "candidates": [{"title": str(value.get("title") or "")[:120],
                                    "source_ref": value.get("source_ref"),
                                    "available_views": value.get("available_views") or []}
                                   for value in values[:5]],
                })
        return titles, searches[-3:]

    def _group_cost(self, group: list[dict[str, Any]]) -> int:
        return sum(self._cost(item) for item in group)

    def _cost(self, value: dict[str, Any]) -> int:
        return self._estimate(json.dumps(value, ensure_ascii=False))

    @staticmethod
    def _message_groups(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Keep each native tool-call message and all of its results together."""
        groups: list[list[dict[str, Any]]] = []
        index = 0
        while index < len(messages):
            item = messages[index]
            payload = json.loads(item.get("provider_payload_json") or "{}")
            if item["role"] == "assistant" and payload.get("tool_calls"):
                call_ids = {
                    str(call.get("id")) for call in payload["tool_calls"] if call.get("id")
                }
                group = [item]
                index += 1
                while index < len(messages) and messages[index]["role"] == "tool":
                    result_payload = json.loads(
                        messages[index].get("provider_payload_json") or "{}"
                    )
                    if str(result_payload.get("tool_call_id") or "") not in call_ids:
                        break
                    group.append(messages[index])
                    index += 1
                # A partial group is not safe to send to the provider. Recovery
                # completes it from assistant_tool_calls before another model turn.
                if len(group) == len(call_ids) + 1:
                    groups.append(group)
                continue
            if item["role"] != "tool":
                groups.append([item])
            index += 1
        return groups

    @staticmethod
    def _provider_message(item: dict[str, Any]) -> dict[str, Any]:
        payload = json.loads(item.get("provider_payload_json") or "{}")
        role = str(item["role"])
        if role == "assistant" and payload.get("tool_calls"):
            return {
                "role": "assistant", "content": item.get("content") or None,
                "tool_calls": payload["tool_calls"],
            }
        if role == "tool":
            return {
                "role": "tool", "tool_call_id": payload["tool_call_id"],
                "name": payload.get("name"), "content": item.get("content") or "{}",
            }
        return {"role": role, "content": str(item.get("content") or "")}

    @staticmethod
    def _estimate(value: str) -> int:
        ascii_count = sum(1 for character in value if ord(character) < 128)
        non_ascii = len(value) - ascii_count
        return max(1, ascii_count // 4 + non_ascii + 8)
