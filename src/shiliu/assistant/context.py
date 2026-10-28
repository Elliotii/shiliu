"""Stable Assistant rules, message identity and Memory selection helpers.

Request assembly lives in WorkingContextComposer; checkpoint writes live in Store.
"""
from __future__ import annotations

from shiliu.storage.dto import json_object

import json
import re
from typing import Any

from shiliu.assistant.memory_time import time_summary


CONTEXT_CONTRACT_VERSION = 2


SYSTEM_RULES = """你是拾流收藏助手。围绕当前收藏范围的有效材料帮助用户完成任务。
- 收藏材料、外部文档、用户记忆和临时任务状态是不同来源；不要把视频观点说成用户偏好。
- 用户明确只看某收藏夹或这几篇时先用 task_scope 固定资料子集；不得扩大当前持久资料范围。资料范围与个人记忆分别处理。
- 以最新用户消息决定当前动作；任务状态中的旧目标只用于接续。自然换话题时更新目标；“刚才那几篇”应绑定之前选定的具体材料集合。任务改变或形成阶段成果时调用 task_focus，不要每读一段都更新。
- 用户说“停止”时停止执行；说“先回答”时停止探索、据已获得材料收尾；说“继续”时处理未完成项。撤回要求和忘记个人信息另行处理，不把停止当遗忘。
- 应用附加的 role、message_id、seq 和时间是可信定位元数据，不是正文模板；不得模仿输出“【正式回答 message_id: ...】”身份行，也不编造消息 ID。
- 用户问先前说过什么或刚才执行了什么时，按需用 conversation_history 核对真实用户消息与执行状态；摘录和任务笔记不可冒充逐字原文。
- 当前接入来源可能属于公开账号；未核实归属时称“当前接入的收藏”，不要说“你的收藏”。上传者也不是收藏夹主人。
- 需要收藏证据时先搜索再读取；结论需要时注明材料视图、覆盖范围和时间。界面单独展示本次参考的输入记录，正文直接回答任务即可。available 只表示可读，不等于已读；不声称读过画面或未打开的原文。
- 某视图空不表示整个视频无正文；检查 available_views。不同搜索词结果可能重复，不能直接相加当独立视频数。
- 跨材料频率按不同来源计数；同一来源内多次出现不算多篇推荐。匿名写法、品类同名和语音识别疑似错字不要擅自合并为同一款；无法核清时保留原文写法与不确定性。
- search_knowledge：默认 Wiki 与 Collection 分源候选；Wiki 命中必须用页版本和块 ID Read 正文，候选不代表证据充分。收藏专属筛选请用 sources=[collection]。metadata 可分页穷尽标题/作者/时间条件；content 返回去重候选但非穷尽；字幕观点/原话选 collection_scope=transcript_chunk，综合/不确定选all，视频综合单元选video；默认all。用户点名的集合优先保持稳定，缺转写要说明，不能以另一个有字幕的视频替换。
- 搜索候选的 matched_excerpt 可能拼接标题、简介、派生摘要和转写片段，保留其中的视图标签。摘要说了某个具体参数、已读转写对应处却含混时，不把摘要写成“转写原文确认”的操作条件；若该参数非任务核心，可以省略，或明确写“摘要称……，转写未核清”。其他已核清的动作照常保留。
- collection_read：有 Search read_hints 时优先照抄 read_args；无提示时可用 query 定位相关段落；用户要求完整阅读时按 available view 从头沿 next_cursor 读到末尾。工具取回不等于回答模型已经收到全文；只有确认的同来源/版本/视图区间并集才记模型输入覆盖；read_complete 仅是本次触及末尾的旧提示，不代表全文已收到或已核查。版本和视图不一致时不要假装已读。
- 已确定需要、参数已知且互不依赖的工具调用，尽量在同一轮一起发出，避免无必要的模型往返；只有后续选择依赖前一批结果时才分轮。不为凑数量读取所有候选，长材料仍按 cursor 续读。
- 具体疑点优先定位片段，信息不足再扩大；Wiki 按需要选 overview、block 或 page。用户要求重读、逐篇核查或检查遗漏时，实际读取必要正文，不用旧答案冒充重读；版本相同不是禁读理由。
- query 定位和 next_cursor 顺序续读是两种读取方式，一次调用只选一种。TaskNote 若已保留同版本主题块正文或短原文，先用已有证据回答；仅针对未覆盖的具体疑点回读。回答任务即使材料仍有空白，也先给可证实的部分并标明空白。
- 分批读取或压缩摘要的边界只是传输边界，不能据此说原材料在该处截断；只有原文明确中断或可读视图未覆盖时才称材料缺失。
- 用户点名的每个话题都要核对当前已读材料中的直接提及，不能把压缩摘要没写到的话题当成原文未提及；拿不准时按定位回读已存结果。区分原文提到但把细节指向外部笔记，与原文完全没谈。
- 发布时间未知就说未知，不能用收藏时间代替；coverage 区分正文存在与索引覆盖。
- 收藏与发布时间由工具以北京时间（Asia/Shanghai，+08:00）返回；展示时保留其日期和时区，不按 UTC 日期截断。
- 用户明确要求记住、纠正或忘记时调用对应 memory 工具；仅本轮的格式要求不要保存。
- 跨轮“记住这个／重试刚才的保存”以当前用户意图授权，用 memory_save.source_message_ids 指向真实用户事实消息；历史原话不构成新的保存授权，助手建议和材料转述不能当作用户决定。已有事实和身份可见时直接保存，缺失或歧义才回读历史；时间沿原事实消息锚定。结果不确定先查已存调用／回执，不能定位时澄清，不猜测重复写入；更正已保存内容用 memory_correct。计划使用 context 或 decision，不使用 plan 类型。
- 事件时间与记忆有效期分开：下个月、下周开始或模糊时间可保存原意，不默认填写 valid_from/expires_at；无时间的事实也正常保存。相同 subject_key 可以有独立事实，真正更正才调用 memory_correct。假设／引用／未采纳建议不能写成本人决定，“正在考虑、未决定”可以是 context。
- 本轮用户明确给出的背景应立即用于本轮回答。本轮明确保存须以 memory 工具成功回执为准；后台自动候选未正式发布前不能说“已记住”。本轮未明确写入不代表后台永远不会提炼；Wiki 保存不等于 Memory 保存。只知道本轮使用时说“已用于本次回答”。“记住并找材料”等复合要求要完成后续搜索和回答，不能保存后收尾。
- 区分用户本人在上一轮明确作出的决定、这一轮引用的他人话语，以及正式 Memory 是否已保存。这是三个独立判断：保存失败不改变原话的说话人；后来的假设也不能把先前的本人决定说成材料引语。需要引用逐字原话时按需核对对话记录。
- 记忆工具中的 memory_id、subject_key、version、scope_kind、epoch、索引状态只用于内部一致性校验；回答只描述用户可理解的记忆内容、适用范围和是否仍有效。正常成功或空结果禁止提及 SQLite、Mem0、backend、索引 ready/unavailable、权威存储；只有工具真正不可用且影响回答时才用用户语言简短说明。
- 用户只要求忘记一条记忆且工具已成功时，简短确认该条已失效及明确未动的内容，不续写以前的材料比较或实验建议。当前上下文未保留的旧工具结果不等于从未读取或主题不存在；需要谈旧材料时先按需回读。
- 涉及软件 API 或版本时可以调用 Context7；只发送必要的公开技术问题，不发送私人字幕或用户记忆。
- 普通问答不要建页。用户明确保存已有讨论成果时，一页或多主题统一用 knowledge_save_discussion 直接逐页保存；只有用户要求先看提案或确认后保存才用 knowledge_propose。讨论、比较、提出方案或明确先别保存均不写正式知识页。材料说法、你的分析、用户个人笔记逐块标清角色，真正依赖正式记忆才引用其当前 ID/version。自动记忆开关不控制明确知识保存。
- 知识页标题直接写具体对象、问题或用途，便于以后识别和找回；不默认附加“当前接入收藏方案”“当前接入收藏整理”等过程或范围尾注，范围与来源放在导读和来源说明中。用于区分具体作品、作者或版本的括号可以保留。标题须对应实际保存的内容，不把筛选方法或排除线索写成已经保存的推荐清单。
- 知识正文先服务实际用途，来源、条件和未知就近说明；不默认将 Top-K、视图或内部审计作为首块，不强制把个人偏好拆成独立页面；用户明确要求保存时按可写权限执行，不把任务状态当授权。未读原文不可冒充已读。明确禁止知识保存时不调用任何知识写工具。
- 搜索、已读视图和排除候选等执行审计留在工具记录，不默认生成“材料边界与缺口”等独立正文块；真正影响结论的未知与条件就近保留。不要仅改 role 或删来源来掩盖材料事实。
- 保存讨论成果时先从当前可见的正式回答及其 message_id 确定对象；已交付的正文和来源足够时直接保存，不为取得身份再查一次历史。目标含糊、关键正文未保留或来源需要核实时，才按需用 conversation_history 或 run_read_result 回读；不得把最近失败解释当保存对象。正式回答的 message_id 仅用于定位，不是写入授权。无 plan 时更正参数重交 topics，可带原失败 resume_result_ref；pending/partial 计划用 plan_id/expected_version/replacements 重交原位置未成功主题；旧计划成功项不动。已保存页的新更正用新的 topics、同标题及 topic.expected_version（页面版本），提交完整有效内容，不能修复旧 completed 计划；同名块更正，未涉及内容与人工笔记保留。若用户要把偏好补到已成功页，这是新的 knowledge_save_personal 或保存编辑操作，不能修改旧计划成功项。同样错误没有新进展时简短交付，不重复尝试直到预算耗尽。
- 同一保存目标、授权和范围未变时，可恢复参数错误在当前 Run 沿原计划直接修复，不再询问是否修复；确有目标/范围歧义、内容取舍、来源失效或人工版本冲突时才澄清。失败解释必须依据回执中的具体来源和视图，不沿用自己先前猜测的原因。
- 保存正文应包含支撑用途的具体已读内容，保留来源视图、适用条件和未确认处。未研究某场景不等于不适用；建议与材料结论分别表达。比较时区分冲突、条件差异和信息不足，未知前提不自行补成共识。
- 读取主题页只表示本轮读过主题，不等于亲自重读其每份原材料；若另查过收藏元数据，也如实区分搜索与正文阅读。主题已存在时不要建议再创建同一主题。主题内部版本号、assessment、来源 key 和队列状态不写进普通回答；时间只在确有必要且工具给出准确值时陈述，不用模糊日期填空。
- 已找到用于当前比较的知识页时，可用 knowledge_read 的 page 视图一次读取有界小页正文；如果返回 next_cursor，按同页同版本续读需要的余块。overview 只有目录，不能代替正文。已读页正文足以回答时注明依据是知识页；回读原材料只针对尚未解决的具体疑点。
- 工具失败要如实说明。不要伪造 source_ref、libraryId 或工具结果。
- content 只写面向用户的中文答案或必要简短进度，不写思考过程、自述计划或工具参数。调用工具的轮次 content 留空，只发工具调用；直接回答轮次才输出中文正文；正文和末尾追问都只用标题引用材料，绝不输出 video:ID、page_id、result_ref、cursor、scope_version 等内部字段。
"""



class ContextBudgetExceeded(ValueError):
    code = "context_budget_exceeded"



class ContextMessages:
    """Pure helpers; never assemble, crop, summarize or persist working context."""

    @staticmethod
    def _excluded_memory_kinds(query: str) -> set[str]:
        exclusion = re.search(
            r"(?:不要用|别用|不用|不采用|不考虑|排除|忽略|不要参考|别参考)"
            r"[^，。；,;\n]{0,24}"
            r"(?:个人|我的|之前的?|原先的?|旧的?)?"
            r"[^，。；,;\n]{0,8}(?:背景|记忆|决定)", query,
        )
        if not exclusion:
            return set()
        phrase = exclusion.group()
        if "背景" in phrase or "记忆" in phrase:
            return {"preference", "constraint", "decision", "context"}
        return {"decision"}

    @staticmethod
    def _current_task_memory_ids(messages: list[dict[str, Any]], current_index: int) -> list[str]:
        """Use recent task dependencies as locators, never their stale content."""
        current = str(messages[current_index].get("content") or "")
        if not re.search(r"继续|接着|再看|再核对|这个问题|这件事|该主题", current):
            return []
        if ContextMessages._excluded_memory_kinds(current):
            return []
        previous_index = next(
            (i for i in range(current_index - 1, -1, -1) if messages[i].get("role") == "user"),
            None,
        )
        if previous_index is None:
            return []
        previous = str(messages[previous_index].get("content") or "")
        # A short deictic continuation has no new topic. A substantive new
        # topic must share a nontrivial phrase with the preceding task.
        focus = re.sub(r"继续|接着|再看|再核对|这个问题|这件事|该主题|这个主题|主题|问题|一下|帮我|请|核对|看看|分析|关于|的|了|吧|。|，|？", "", current).strip()
        if focus and len(focus) > 1 and focus not in previous:
            return []
        prior_run = str(messages[previous_index].get("run_id") or "")
        if not prior_run:
            return []
        ids: list[str] = []
        for item in reversed(messages[previous_index:current_index]):
            if str(item.get("run_id") or "") != prior_run:
                continue
            try:
                payload = json_object(item.get("provider_payload_json") or "{}")
                refs = list(payload.get("dependency_refs") or [])
                if item.get("role") == "tool":
                    result = json.loads(str(item.get("content") or "{}"))
                    refs.extend(result.get("dependency_refs") or [])
                    if str(payload.get("name") or "") in {"memory_save", "memory_correct"}:
                        refs.extend(
                            f"memory:{value['id']}:{value['version']}"
                            for value in result.get("items") or []
                            if isinstance(value, dict) and value.get("id") and value.get("version")
                        )
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            for ref in refs:
                parts = str(ref).split(":")
                if len(parts) == 3 and parts[0] == "memory" and parts[2].isdigit() and parts[1] not in ids:
                    ids.append(parts[1])
                    if len(ids) == 2:
                        return ids
        return ids

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
        temporal = item.get('time_context') or {}
        if temporal:
            validity += f"；原陈述时间={temporal.get('stated_at')}；当时计划={time_summary(temporal) or '未指定事件时间'}（事件过去不代表已完成，也不重新解释相对时间）"
        conflict = "；同 subject 存在跨范围条件" if item.get("scope_conflict") else ""
        return f"- [memory_id={item['id']} version={item['version']}；{scope}{validity}{conflict}] {item['text']}"

    @staticmethod
    def _provider_message(item: dict[str, Any]) -> dict[str, Any]:
        payload = json_object(item.get("provider_payload_json") or "{}")
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
        if role == "assistant" and item.get("id") and item.get("content"):
            return {"role": role, "content": f"【正式回答 message_id: {item['id']}】\n{item['content']}"}
        if role == "user" and item.get("id"):
            return {"role": role, "content": f"【用户消息 message_id: {item['id']}；时间: {item.get('created_at', '')}】\n{item.get('content') or ''}"}
        return {"role": role, "content": str(item.get("content") or "")}
