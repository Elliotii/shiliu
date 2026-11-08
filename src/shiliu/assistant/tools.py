from __future__ import annotations

from shiliu.assistant.pg_store import PgAssistantRunStore

from shiliu.storage.dto import json_object

import json
import asyncio
import time
import hashlib
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from shiliu.assistant.contracts import CollectionReadArgs, CollectionSearchArgs, KnowledgeSearchArgs as UnifiedSearchArgs, ToolResult
from shiliu.assistant.dependencies import Context7MCPClient
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.memory_policy import anchored_validity, cancels_time, explicit_expiry_has_user_basis, time_phrase, plausible_personal_excerpt
from shiliu.assistant.memory_time import checked_validity, time_context as make_time_context, event_signature, validate_event_basis
from shiliu.assistant.sources import CollectionSourceService, SourceScope
from shiliu.assistant.delivery import field_value, read_evidence
from shiliu.assistant.runtime_contract import AssistantConflict
from shiliu.assistant.wiki import WikiService


def _forbids_knowledge_save(text: str) -> bool:
    # A request may forbid personal Memory while explicitly asking for a Wiki
    # proposal. Keep those two destinations independent.
    text = re.sub(
        r"(?:不要|别|禁止|不许|无需)(?:再|直接)?(?:保存|存入|写入|记到)(?:这条|我的|个人的|到)?(?:个人记忆|长期记忆|私人记忆|个人背景|(?:个人|长期|私人)?\s*(?:Memory|memory))",
        "", text,
    )
    text = re.sub(
        r"(?:个人记忆|长期记忆|私人记忆|个人背景|(?:个人|长期|私人)?\s*(?:Memory|memory))\s*(?:仍|也|同样)?\s*(?:不要|别|禁止|不许|无需)(?:再|直接)?(?:保存|存入|写入|记到)",
        "", text,
    )
    wiki_target = r"(?:Wiki|知识库|知识页)"
    if re.search(r"(?:不要|别|禁止|不许)(?:写入|更新|修改|更正|写)[\s]*(?:或(?:更新|修改|更正)[\s]*)?" + wiki_target, text, re.I):
        return True
    if not re.search(wiki_target, text, re.I) and re.search(
        r"(?:只|仅)(?:需要)?(?:保存|更正|更新|修改|写入)\s*(?:Memory|记忆|个人记忆)", text, re.I
    ):
        return True
    return bool(re.search(
        r"(?:不要|别|禁止|不许|无需).{0,12}(?:保存|入页|写入知识|记到知识|写进主题)|(?:别|不要)存",
        text,
    ))


def _unreported_knowledge_intent(text: str) -> str:
    intent_text = re.sub(r"“[^”]*”|‘[^’]*’|\"[^\"]*\"|'[^']*'", "", text)
    # A source's unquoted imperative is still source content. Remove that
    # clause before looking for the current user's own save request. A later
    # clause or sentence can independently authorize the save.
    report_intro = re.compile(
        r"(?:视频|字幕|文章|网页|材料|资料|原文|作者|讲者|主播|老师|有人|朋友|他们|他|她)"
        r"(?:里|中|上|的)?(?:说|写道|写着|写|要求|提到|建议)"
    )
    remaining: list[str] = []
    cursor = 0
    for match in report_intro.finditer(intent_text):
        if match.start() < cursor:
            continue
        remaining.append(intent_text[cursor:match.start()])
        content_start = match.end()
        while content_start < len(intent_text) and intent_text[content_start] in " ：:,，":
            content_start += 1
        while True:
            boundary = re.search(r"[，,。；;！？!?\n]", intent_text[content_start:])
            if boundary is None:
                cursor = len(intent_text)
                break
            cursor = content_start + boundary.start()
            marker = intent_text[cursor]
            if marker in "。！？!?\n" or re.match(
                r"\s*(?:(?:但|不过|另外|而)\s*(?:我|我们|请你|现在请)|(?:我|我们)(?:现在|另外|自己|要|想|请|决定))",
                intent_text[cursor + 1:],
            ):
                break
            # A bare imperative after a comma may still be part of the same
            # reported speech; keep it masked until the speaker clearly shifts.
            content_start = cursor + 1
    remaining.append(intent_text[cursor:])
    return " ".join(remaining)


def _direct_knowledge_save_requested(text: str) -> bool:
    intent_text = _unreported_knowledge_intent(text)
    if _forbids_knowledge_save(intent_text) or re.search(
        r"(?<!不用)(?<!不要)(?<!无需)先(?:给|看|出).{0,10}(?:提案|草案|方案)|(?:确认|审批)后.{0,6}(?:再)?保存",
        intent_text,
    ):
        return False
    if re.search(r"(?:能否|能不能|是否|可不可以|要不要|如果|假如|假设|考虑).{0,28}(?:保存|存入|写入|记到)", intent_text):
        return False
    return bool(re.search(
        r"^(?:请|现在|直接|马上|帮我|整理并)?(?:保存|存入|写入|记到|建成知识页|加入知识库|更新知识页)"
        r"|(?:请|现在|直接|马上|帮我|我想|我们想|把|将|整理并).{0,60}(?:保存|存入|写入|记到|建成知识页|加入知识库|更新知识页)",
        intent_text.strip(),
    ))


class MemorySearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=8, ge=1, le=8)


class MemorySaveArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=400)
    subject_key: str = Field(min_length=1, max_length=120)
    kind: Literal['preference', 'constraint', 'decision', 'context']
    source_message_ids: list[str] = Field(default_factory=list, max_length=20)
    source_excerpt: str | None = Field(default=None, max_length=1000)
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
    update_time_context: bool | None = None
    subject_key: str | None = None
    kind: Literal['preference', 'constraint', 'decision', 'context'] | None = None
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
    candidate_index: int | None = Field(default=None, ge=0)
    field: str | None = Field(default=None, max_length=80)
    start: int = Field(default=0, ge=0)
    max_characters: int = Field(default=6000, ge=1000, le=12000)


class TaskScopeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    basis_quote: str = Field(min_length=1, max_length=2000)
    message_id: str | None = None
    video_ids: list[int] = Field(default_factory=list, max_length=200)
    folder_ids: list[int] = Field(default_factory=list, max_length=50)


class TaskFocusArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(min_length=1, max_length=600)
    selected_source_refs: list[str] = Field(default_factory=list, max_length=20)
    requirements: list[str] = Field(default_factory=list, max_length=12)
    working_notes: str = Field(default="", max_length=4000)
    next_actions: list[str] = Field(default_factory=list, max_length=8)


class ConversationHistoryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=200)
    limit: int = Field(default=8, ge=1, le=20)
    message_id: str | None = None
    role: Literal["user", "assistant", "all"] = "user"
    after_seq: int | None = Field(default=None, ge=0)
    before_seq: int | None = Field(default=None, ge=0)
    start: int = Field(default=0, ge=0)
    max_characters: int = Field(default=2000, ge=1, le=12000)
    total_max_characters: int = Field(default=12000, ge=1, le=24000)


class KnowledgeSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=1000)
    limit: int = Field(default=5, ge=1, le=8)


class LegacyKnowledgeReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_id: str = Field(min_length=1, max_length=100)
    mode: Literal["overview", "page", "relevant", "block"] = "overview"
    query: str | None = Field(default=None, max_length=200)
    block_id: str | None = Field(default=None, max_length=120)
    cursor: str | None = Field(default=None, pattern=r"^[1-9][0-9]*:[1-9][0-9]*$")


class KnowledgeReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_id: str = Field(min_length=1, max_length=100)
    page_version: int | None = Field(default=None, ge=1)
    mode: Literal["overview", "page", "block"] = "overview"
    block_ids: list[str] = Field(default_factory=list, max_length=20)
    block_id: str | None = Field(default=None, max_length=120)
    cursor: str | None = Field(default=None, pattern=r"^[1-9][0-9]*:[1-9][0-9]*$")










class KnowledgeExternalSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=9, max_length=2000)
    result_ref: str = Field(min_length=1, max_length=200)


class KnowledgeOutcomeBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["source", "analysis", "personal"] = Field(description=(
        "source：仅已读来源直接支持的事实或来源观点，保留原条件、范围、确定性与评价强度，"
        "不把相对优势或非强项增强成作者的购买、排除指令；"
        "analysis：模型推断、比较、推荐决策及未知信息，注明依据与不确定性；"
        "personal：用户本人表达的偏好、决定或笔记，绑定真实用户原话。"
        "来源的好评不证明商品不辣、低油或清淡。混合事实与推断须拆块并纠正标题和正文归属，"
        "不能只换标签保留误导正文，也不能把有据事实全部改为analysis。"
    ))
    replace_block_id: str | None = Field(default=None, description="明确更正已读块时指定稳定ID；仅更新使用，未涉及块保留。")
    heading: str = Field(min_length=1, max_length=160)
    markdown: str = Field(min_length=1, max_length=12000, description=(
        "正文须符合本块角色：来源事实与模型推断分块，推荐和未知就近说明依据与条件；"
        "筛选结论属于analysis，不归给作者；缺证属性保留未知，不能凭品类猜测给出确定风险排序。"
        "可保留标明依据与条件的推断和推荐，标题与结论也须保持同等不确定性，文末免责声明不能修正前面的确定断言。"
    ))
    applicability: str = Field(default="", max_length=600)
    source_refs: list[str] = Field(default_factory=list, description="沿用可信读取回执的完整来源身份；视频必须是video:ID:revision，不用裸ID或猜测最新版本。Wiki依据另填真实evidence_ref，外部来源保留真实external_sources。")
    source_view: Literal["transcript", "summary", "description", "notes", "metadata", "time"] | None = None
    memory_id: str | None = Field(default=None, description="仅有意保留对现有 Memory 的动态引用时使用；独立 Wiki 内容留空。")
    memory_version: int | None = Field(default=None, ge=1, description="仅随明确的动态 Memory 引用提供。")
    user_quote: str | None = Field(default=None, max_length=600)
    user_message_id: str | None = None
    evidence_ref: str | None = None
    external_sources: list[KnowledgeExternalSource] = Field(default_factory=list, max_length=3)


class KnowledgeSaveOutcomeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_id: str | None = Field(default=None, description="更新已存在页时绑定真实ID，并提供该页准确标题及expected_version；不得另建同主题页。")
    title: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=600)
    blocks: list[KnowledgeOutcomeBlock] = Field(min_length=1, max_length=8)
    expected_version: int | None = Field(default=None, ge=1)


class KnowledgePlanTopic(KnowledgeSaveOutcomeArgs):
    cross_references: list[str] = Field(default_factory=list, max_length=6)
    omitted: list[str] = Field(default_factory=list, max_length=10)


class KnowledgeProposeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topics: list[KnowledgePlanTopic] = Field(min_length=1, max_length=6)
    omitted: list[str] = Field(default_factory=list, max_length=20)


class KnowledgeUserQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: str
    quote: str = Field(min_length=1, max_length=600)


class KnowledgeSaveRequestArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wiki_message_quotes: list[KnowledgeUserQuote] = Field(default_factory=list, max_length=4, description="用户明确要求保存刚才自己提出的内容时，绑定最近一条历史用户消息ID和具体原话；不授权整段历史。")
    input_kind: Literal["research", "user_facts"] = Field(default="research", description="research绑定已完成回答；user_facts只保存当前明确授权的用户事实/计划，不需先生成回答。")
    answer_message_id: str | None = Field(default=None, min_length=1, max_length=100)
    wiki_authorized_quotes: list[str] = Field(default_factory=list, max_length=12, description="当前用户的Wiki授权分句，不是旧内容本身。历史原话放wiki_message_quotes；只重授权上一条内容时本字段可留空。混合Memory/Wiki仅选Wiki分句。")

    @model_validator(mode="after")
    def target(self):
        if (self.input_kind == 'research') != bool(self.answer_message_id):
            raise ValueError('research需要真实answer_message_id；user_facts不接受回答锚点')
        return self


class KnowledgeUpdatePageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_id: str
    wiki_authorized_quotes: list[str] = Field(default_factory=list, max_length=12, description="混合Memory/Wiki请求，仅选择明确授权Wiki的原话分句，与新建相同。")
    expected_version: int = Field(ge=1)
    purpose: str = Field(default="更新已有知识", min_length=1, max_length=600)
    blocks: list[KnowledgeOutcomeBlock] = Field(min_length=1, max_length=8)


class KnowledgeSaveStatusArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")








class AssistantToolRegistry:
    def __init__(
        self,
        *,
        sources: CollectionSourceService,
        memories: MemoryService,
        store: PgAssistantRunStore,
        context7: Context7MCPClient | None = None,
        wiki: WikiService | None = None,
    ) -> None:
        self.sources = sources
        self.memories = memories
        self.store = store
        self.context7 = context7
        self.wiki = wiki

    @staticmethod
    def normalize_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Equivalent read requests share one durable result within a run."""
        contract = {"search_knowledge": UnifiedSearchArgs, "knowledge_read": KnowledgeReadArgs,
                    "collection_search": CollectionSearchArgs,
                    "collection_read": CollectionReadArgs,
                    "run_read_result": RunReadResultArgs}.get(name)
        if contract is None:
            return arguments
        try:
            return contract.model_validate(arguments).model_dump(exclude_defaults=True, exclude_none=True)
        except ValidationError:
            return arguments

    def schemas(self) -> list[dict[str, Any]]:
        values = [
            self._schema("search_knowledge", "发现当前真实资料范围内的 Wiki 与 Collection 候选，默认双源且分源返回，不是已读证据。Wiki 命中后用 page_id/page_version/block_ids 直接 knowledge_read。收藏专属作者/时间/目录筛选、metadata 分页请指定 sources=[collection]；content 的 collection_scope：字幕观点/原话选 transcript_chunk（正常长度用BM25，短词仍导航），综合/不确定选all，视频综合单元选video；默认all。", UnifiedSearchArgs),
            self._schema("collection_read", "按来源版本读材料视图。相关疑点可用query或Search read_hints定位；完整阅读首次不传query/cursor，从字符0开始，再用next_cursor续读。范围为字符[start,end)，has_unread_before/after表示本次窗口前后尚有内容；read_complete只表示本次覆盖整个当前视图。truncated=false或next_cursor=null仅说明后面无内容，不代表前面已读；body_coverage描述来源可用性，summary完整不等于字幕完整。累计只合并同来源/版本/视图已交付区间，不重复相同query当续读。", CollectionReadArgs),
            self._schema("memory_search", "搜索当前有效的用户和 Space 记忆", MemorySearchArgs),
            self._schema("memory_save", "当前用户明确要求时保存个人事实；source_message_ids 可选本线程较早用户原话，授权与事实分开、时间锚定原消息。已知事实直接保存，歧义才回读。kind 仅 preference/constraint/decision/context，计划用 context 或 decision。无时间和模糊计划均可保存；事件不是有效期，不要为下个月/下周计划填写 valid_from/expires_at。未知旧结果先核回执，修改已有记忆用 memory_correct。复合请求继续完成其余动作", MemorySaveArgs),
            self._schema("memory_correct", "使用 memory_search 回执或当前有效记忆行中的真实 memory_id 和 version 纠正；不能把展示文字当 ID。若还有其他要求，继续完成", MemoryCorrectArgs),
            self._schema("memory_forget", "使用 memory_search 回执或当前有效记忆行中的真实 memory_id 和 version 遗忘；不能把展示文字当 ID。若还有其他要求，继续完成", MemoryForgetArgs),
            self._schema("run_read_result", "按条目和字段回读当前对话的已保存工具结果；正文用 start 分段；field 支持 response.content.0.text 等列表下标，不返回任意 JSON 切片", RunReadResultArgs),
            self._schema("task_scope", "理解用户当前排除或限定资料的要求后缩小任务子集。basis_quote 必须是当前用户指令原话，提供 video_ids 或 folder_ids；后续搜索、读取、知识页和接续均受限，不修改空间或个人记忆。", TaskScopeArgs),
            self._schema("task_focus", "在换任务、选定‘刚才那几篇’的集合或形成阶段成果时更新当前目标、选定来源、有效要求及工作稿。由服务端绑定真实用户消息；这不是写入授权。无需每读一段调用。", TaskFocusArgs),
            self._schema("conversation_history", "按 message_id 或 seq 范围回读当前对话用户/正式助手消息；role=all 查近期对象身份，start 分段展开。总正文默认12000字符；按 coverage.next_read_args 续读，失效及被遗忘内容不返回。", ConversationHistoryArgs),
        ]
        if self.wiki is not None:
            values.extend([

                self._schema("knowledge_read", "按 Search 的 page_id/page_version/block_ids 直接读当前有效正文，不重新匹配 query。overview 为目录，page 有界全文及版本化续读；block 指定稳定块。候选不等于正文，Wiki 血缘不等于重读原视频。", KnowledgeReadArgs),
                self._schema("knowledge_save_request", "仅用户明确授权保存Wiki时新建：research绑定真实已完成answer_message_id；user_facts直接保存当前用户明确给出的事实/决定/计划，由程序绑定用户身份，无需先写回答。混合研究仍选research保留回答及用户引用。普通个人陈述或仅要求Memory不写Wiki。返回受理不是完成；已有页用knowledge_update_page，状态查knowledge_save_status，不重复创建。", KnowledgeSaveRequestArgs),
                self._schema("knowledge_save_status", "用户询问保存进度时查询本对话真实 Wiki 保存任务；完成项含真实 page_id/version，可再用 knowledge_read 阅读，未完成草稿不是正式 Wiki。", KnowledgeSaveStatusArgs),
                self._schema("knowledge_update_page", "用户明确授权更新已读页面时，提交同一后台Writer。原页正文已失效/为空不要求重复读出旧正文。必须提供真实page_id、观测expected_version和新增/更正块；personal绑定真实用户原话，不为独立知识附加Memory版本依赖；定点替换仍须已读replace_block_id。未涉及内容、CAS和人工保护保留；找不到页不新建。只表示受理，完成查knowledge_save_status。", KnowledgeUpdatePageArgs),
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
        *, space_override: dict | None = None,
    ) -> bool:
        """Validate direct and historical dependencies at their current versions."""
        try:
            space = space_override if space_override is not None else self.store.task_space(thread_id)
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
                    space_override=space,
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

    async def execute(self, *, name: str, arguments: dict[str, Any], call_id: str,
                      run_context: dict[str, Any], replay: bool = False) -> dict[str, Any]:
        kwargs = dict(name=name, arguments=arguments, call_id=call_id, run_context=run_context, replay=replay)
        if name in {"collection_read", "knowledge_read", "run_read_result", "memory_search", "conversation_history"} and not arguments.get("refresh_metadata"):
            return await asyncio.to_thread(lambda: asyncio.run(self._execute(**kwargs)))
        with self.store.tool_execution_scope(str(run_context["run"]["id"]), int(run_context["run"]["run_epoch"])):
            return await self._execute(**kwargs)

    async def _execute(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        call_id: str,
        run_context: dict[str, Any],
        replay: bool = False,
    ) -> dict[str, Any]:
        space = run_context["space"]
        scope = SourceScope(
            source_db_ids=frozenset(int(value) for value in space["source_ids"]),
            video_ids=frozenset(int(value) for value in space.get("video_ids", [])),
            all_active=bool(space["all_active"]),
        )
        try:
            # A limited veto for an explicit current prohibition; positive intent
            # and the confirm direction are supplied by the model's tool choice.
            # A preview/rejection does not commit a page, so it is not a save.
            if name in {'knowledge_save_request', 'knowledge_update_page', 'knowledge_save_discussion', 'knowledge_save_personal',
                        'knowledge_organize', 'knowledge_save_outcome'} or (
                            name == 'knowledge_confirm' and arguments.get('accept') is True):
                intent = _unreported_knowledge_intent(self._current_user_message(run_context)['content'])
                if _forbids_knowledge_save(intent):
                    return self._error(call_id, 'knowledge_save_forbidden', '当前用户明确禁止知识保存，未写入', status='invalid_arguments')
            if name in {'knowledge_save_discussion','knowledge_save_personal','knowledge_propose','knowledge_confirm',
                        'knowledge_organize','knowledge_manage','knowledge_plan_item','knowledge_save_outcome'}:
                return self._error(call_id, 'retired_tool', '旧工具已退役；历史计划请用人工管理入口。新建用knowledge_save_request，更新用knowledge_update_page，状态用knowledge_save_status', status='invalid_arguments')
            registered = replay and self.store.legacy_call_registered(str(run_context["run"]["id"]), call_id, name, arguments)
            if registered and name == "task_scope" and "basis_quote" not in arguments:
                arguments = {**arguments, "basis_quote": _unreported_knowledge_intent(self._current_user_message(run_context)["content"])}
            if registered and name == "knowledge_read" and arguments.get("mode") != "relevant" and "query" in arguments:
                arguments = {key: value for key, value in arguments.items() if key != "query"}
            if registered and name == "knowledge_read" and arguments.get("mode") == "block" and "page_version" not in arguments:
                page = self.wiki.get_page(arguments["page_id"], space_id=int(space["id"]), task_scope=scope if space.get("task_subset") else None)
                arguments = {**arguments, "page_version": page["version"]}
            legacy_read = name == "knowledge_read" and (arguments.get("mode") == "relevant" or "query" in arguments)
            if name in {"collection_search", "knowledge_search"} or legacy_read:
                # Only recovery may execute a call actually persisted before dispatch.
                if not registered:
                    return self._error(call_id, "retired_tool", "旧检索合同已退出，请使用 search_knowledge 和稳定块 Read")
                if name == "collection_search":
                    arguments = {**arguments, "sources": ["collection"]}
                    name = "search_knowledge"
                elif name == "knowledge_search":
                    old = KnowledgeSearchArgs.model_validate(arguments)
                    arguments = {"query": old.query, "sources": ["wiki"], "wiki_limit": old.limit}
                    name = "search_knowledge"
                else:
                    old = LegacyKnowledgeReadArgs.model_validate(arguments)
                    page = self.wiki.get_page(old.page_id, space_id=int(space["id"]), task_scope=scope if space.get("task_subset") else None)
                    found = await asyncio.to_thread(self.wiki.retrieval.search, old.query, page_id=old.page_id, space_id=int(space["id"]), task_scope=scope if space.get("task_subset") else None, thread_id=str(run_context["thread"]["id"]), limit=1)
                    hit_page = next((item for item in found["candidates"] if item["page_id"] == page["id"]), None)
                    if not hit_page:
                        return self._error(call_id, "knowledge_location_changed", "旧定位无法恢复，请重新 Search")
                    arguments = {"page_id": page["id"], "page_version": page["version"], "mode": "block",
                                 "block_ids": [hit["block_id"] for hit in hit_page["hits"]]}
            if name == "knowledge_save_request":
                from shiliu.assistant.knowledge_write import accept_save
                args = KnowledgeSaveRequestArgs.model_validate(arguments)
                user = self._current_user_message(run_context)
                job = accept_save(self.store, thread_id=run_context['thread']['id'],
                                  answer_message_id=args.answer_message_id,
                                  request_id='user:' + user['id'], user_message_id=user['id'],
                                  requirement=user['content'], wiki=self.wiki, registry=self,
                                  user_facts=args.input_kind == 'user_facts', wiki_authorized_quotes=args.wiki_authorized_quotes, wiki_message_quotes=[q.model_dump() for q in args.wiki_message_quotes])
                return ToolResult(call_id=call_id, status="ok", summary="Wiki 保存已受理；尚未完成，可继续聊天",
                                  items=[job]).model_dump(mode="json")
            if name == "knowledge_update_page":
                from shiliu.assistant.knowledge_write import accept_save
                args = KnowledgeUpdatePageArgs.model_validate(arguments)
                user = self._current_user_message(run_context)
                page = self.wiki.get_page(args.page_id, space_id=int(space['id']))
                topic = dict(page_id=args.page_id, title=page['title'], expected_version=args.expected_version,
                             purpose=args.purpose, blocks=[b.model_dump(mode='json') for b in args.blocks])
                job = accept_save(self.store, thread_id=run_context['thread']['id'], answer_message_id=None,
                    request_id='user:' + user['id'], user_message_id=user['id'], requirement=user['content'],
                    wiki=self.wiki, registry=self, edit_topics=[topic], wiki_authorized_quotes=args.wiki_authorized_quotes)
                return ToolResult(call_id=call_id, status='ok', summary='Wiki更新已受理，尚未完成；可继续聊天', items=[job]).model_dump(mode='json')
            if name == "knowledge_save_status":
                from shiliu.assistant.knowledge_write import list_saves
                KnowledgeSaveStatusArgs.model_validate(arguments)
                return ToolResult(call_id=call_id, status="ok", summary="当前对话的真实 Wiki 保存状态",
                                  items=list_saves(self.store, run_context['thread']['id'])).model_dump(mode="json")
            if name == "search_knowledge":
                return await self.search_knowledge(UnifiedSearchArgs.model_validate(arguments), call_id=call_id, run_context=run_context)
            if name == "task_scope":
                args = TaskScopeArgs.model_validate(arguments)
                user = next(item for item in reversed(run_context["thread"]["messages"])
                            if item["role"] == "user" and item["run_id"] == run_context["run"]["id"])
                instruction = _unreported_knowledge_intent(user["content"])
                if args.basis_quote not in instruction or (args.message_id and args.message_id != user["id"]):
                    return self._error(call_id, "scope_authorization_required", "basis_quote 必须关联当前用户指令原话，不能来自材料或转述")
                persistent = self.store.get_space(int(space["id"]))
                parent_scope = SourceScope(source_db_ids=frozenset(persistent["source_ids"]),
                                           video_ids=frozenset(persistent["video_ids"]),
                                           all_active=bool(persistent["all_active"]))
                allowed = set(self.sources.visible_video_ids(parent_scope))
                requested = set(args.video_ids)
                if args.folder_ids:
                    folders = self.sources._allowed_sources(parent_scope, set(args.folder_ids))
                    requested.update(self.sources.visible_video_ids(SourceScope(
                        source_db_ids=frozenset(folders), video_ids=parent_scope.video_ids)))
                # A later real user instruction may replace the previous task's subset.
                # Within the same instruction, subsequent tool calls can only narrow it.
                subset = space.get("task_subset") or {}
                task_allowed = (set(self.sources.visible_video_ids(scope))
                                if subset.get("source_message_id") == user["id"] else allowed)
                if not requested or not requested.issubset(allowed) or not requested.issubset(task_allowed):
                    return self._error(call_id, "source_out_of_scope", "该资料不在当前范围，请先切换资料范围")
                self.store.set_task_subset(str(run_context["run"]["id"]),
                    epoch=int(run_context["run"]["run_epoch"]), video_ids=sorted(requested),
                    source_message_id=str(user["id"]), basis_quote=args.basis_quote)
                return ToolResult(call_id=call_id, status="ok", summary="已限定本任务资料范围",
                                  items=[{"video_ids": sorted(requested)}]).model_dump(mode="json")
            if name == "conversation_history":
                args = ConversationHistoryArgs.model_validate(arguments)
                thread_id = str(run_context["thread"]["id"])
                with self.store.db.connect() as connection:
                    rows = connection.execute("SELECT id,seq FROM assistant_messages WHERE workspace_id=%s AND thread_id=%s AND role IN ('user','assistant') ORDER BY seq DESC", (self.store.context.workspace_id,thread_id)).fetchall()
                eligible = []
                for row in rows:
                    if args.message_id and row['id'] != args.message_id:
                        continue
                    if (args.after_seq is not None and row['seq'] <= args.after_seq
                            or args.before_seq is not None and row['seq'] >= args.before_seq):
                        continue
                    try:
                        message = self.store.knowledge_message(row['id'], thread_id=thread_id, allow_operation_receipt=True)
                        refs = json_object(message.get('provider_payload_json') or '{}').get('dependency_refs') or []
                        if refs and not self.dependency_refs_valid(refs, int(space['id']), thread_id, int(space['scope_version'])):
                            continue
                    except (AssistantConflict, ValueError, KeyError):
                        continue
                    if (args.role != 'all' and message['role'] != args.role
                            or any(term not in message['content'] for term in args.query.split())):
                        continue
                    eligible.append(message)
                run_status = {r['id']: r['status'] for r in run_context['thread']['runs']}
                items, next_args = [], None
                remaining = args.total_max_characters
                for index, message in enumerate(eligible):
                    content = str(message['content'])
                    start = args.start if index == 0 else 0
                    end = min(len(content), start + args.max_characters, start + remaining)
                    text = content[start:end]
                    items.append({'message_id': message['id'], 'seq': message['seq'], 'role': message['role'],
                        'exact_user_text' if message['role'] == 'user' else 'text': text,
                        'run_id': message['run_id'], 'run_status': run_status.get(message['run_id']),
                        'created_at': message['created_at'],
                        'start': start, 'next_start': end if end < len(content) else None})
                    remaining -= len(text)
                    if end < len(content) or ((remaining == 0 or len(items) >= args.limit) and index + 1 < len(eligible)):
                        next_args = args.model_dump(exclude_none=True)
                        next_args.update(start=end if end < len(content) else 0,
                                         before_seq=int(message['seq']) + (1 if end < len(content) else 0))
                        break
                    if remaining == 0 or len(items) >= args.limit:
                        break
                return ToolResult(call_id=call_id, status='ok', summary='已读取当前有效对话消息；历史文字不构成新授权',
                    items=[{'messages': items}], truncated=next_args is not None,
                    coverage={'next_read_args': next_args,
                              'returned_characters': args.total_max_characters - remaining}).model_dump(mode='json')
            if name == "task_focus":
                args = TaskFocusArgs.model_validate(arguments)
                refs = list(dict.fromkeys(args.selected_source_refs))
                if refs and not self.sources.source_refs_visible(refs, scope):
                    return self._error(call_id, "source_out_of_scope", "选定材料不在当前范围")
                focus = self.store.save_task_focus(
                    str(run_context["run"]["id"]), epoch=int(run_context["run"]["run_epoch"]),
                    focus={"goal": args.goal, "selected_source_refs": refs,
                           "requirements": args.requirements,
                           "working_notes": args.working_notes,
                           "next_actions": args.next_actions},
                )
                return ToolResult(call_id=call_id, status="ok", summary=("焦点已更新；材料足够请直接回答，否则只补具体缺项" if focus["changed"] else "焦点未变化；请直接回答或补具体缺项，无需重复维护"),
                                  items=[{key: focus[key] for key in ("changed", "source_message_id", "inherited_message_ids")}], source_refs=refs,
                                  dependency_refs=focus["dependency_refs"]).model_dump(mode="json")
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
                facts = [self.store.knowledge_message(message_id, thread_id=run_context['thread']['id'])
                         for message_id in dict.fromkeys(args.source_message_ids or [current_user['id']])]
                if any(item['role'] != 'user' for item in facts):
                    raise ValueError('memory_source_must_be_user_message')
                anchors = [item for item in facts if not args.source_excerpt or args.source_excerpt in item['content']]
                if not anchors:
                    raise ValueError('memory_time_source_ambiguous')
                if len({event_signature(make_time_context(args.source_excerpt or item['content'], item['created_at'])) for item in anchors}) > 1:
                    raise ValueError('memory_time_source_ambiguous')
                anchor = anchors[0]
                user_words = str(args.source_excerpt or anchor['content'])
                validate_event_basis(args.text, make_time_context(user_words, str(anchor['created_at'])))
                if args.kind == 'decision' and not plausible_personal_excerpt(user_words, 'decision'):
                    raise ValueError('memory_fact_not_user_decision')
                scope_id = None if args.scope_kind == "user" else int(space["id"])
                operation_key = f"tool:{run_context['run']['id']}:{call_id}"
                # Do not guess which uncertain operation a new call is replacing.
                with self.store.db.connect() as connection:
                    uncertain = connection.execute("SELECT c.* FROM assistant_tool_calls c JOIN assistant_runs r ON (r.workspace_id,r.id)=(c.workspace_id,c.run_id) "
                        "WHERE r.workspace_id=%s AND r.thread_id=%s AND c.name='memory_save' AND c.result_json IS NULL "
                        "AND NOT (c.run_id=%s AND c.call_id=%s)", (self.store.context.workspace_id,run_context['thread']['id'], run_context['run']['id'], call_id)).fetchall()
                    for previous in uncertain:
                        prior_args = json_object(previous['args_json'])
                        if (prior_args.get('subject_key'), prior_args.get('scope_kind', 'space')) != (args.subject_key, args.scope_kind):
                            continue
                        prior_ids = prior_args.get('source_message_ids') or [row["id"] for row in connection.execute(
                            "SELECT id FROM assistant_messages WHERE workspace_id=%s AND run_id=%s AND role='user'", (self.store.context.workspace_id,previous['run_id']))]
                        if set(prior_ids) != {item['id'] for item in facts}:
                            continue
                        receipt = connection.execute("SELECT result_json FROM assistant_mutation_receipts WHERE workspace_id=%s AND principal_id=%s AND operation_key=%s",
                            (self.store.context.workspace_id,self.store.principal_id, previous['operation_key'] or f"tool:{previous['run_id']}:{previous['call_id']}")).fetchone()
                        if not receipt or prior_args != arguments:
                            return self._error(call_id, 'memory_previous_outcome_unknown', '先按原结果引用核对这次保存的结果；无法确认目标时请澄清，不重复写入')
                        operation_key = previous['operation_key'] or f"tool:{previous['run_id']}:{previous['call_id']}"
                validity = checked_validity(user_words, str(anchor['created_at']),
                    {field: getattr(args, field) for field in ('valid_from', 'expires_at') if field in args.model_fields_set})
                result = self.memories.save_explicit(
                    text=args.text,
                    subject_key=args.subject_key,
                    kind=args.kind,
                    scope_kind=args.scope_kind,
                    scope_id=scope_id,
                    operation_key=operation_key,
                    source_message_ids=[item['id'] for item in facts],
                    source_excerpt='\n'.join(item['content'] for item in facts)[:1000],
                    stated_text=user_words,
                    stated_at=str(anchor["created_at"]),
                    time_context=make_time_context(user_words, str(anchor['created_at']), anchor['id']),
                    pinned=args.pinned,
                    _notification_causes={'run_id':run_context['run']['id'],'thread_id':run_context['thread']['id'],'request_message_id':current_user['id']},
                    **validity,
                )
                return ToolResult(
                    call_id=call_id, status="ok", summary="已保存正式记忆", items=[result],
                    coverage={"save_feedback": self.memories.creation_feedback(result,
                        save_operation_key=operation_key, space_id=int(space['id']))}
                ).model_dump(mode="json")
            if name == "memory_correct":
                args = MemoryCorrectArgs.model_validate(arguments)
                self._require_memory_in_scope(args.memory_id, int(space["id"]))
                current_user = self._current_user_message(run_context)
                user_words = str(current_user["content"])
                prior_memory = self.memories.get(args.memory_id)
                validate_event_basis(args.text, make_time_context(user_words, str(current_user['created_at'])), prior_memory.get('time_context'), prior_memory['text'])
                if args.kind == 'decision' and not plausible_personal_excerpt(user_words, 'decision'):
                    raise ValueError('memory_fact_not_user_decision')
                validity_changes = checked_validity(user_words, str(current_user['created_at']),
                    {field: getattr(args, field) for field in ('valid_from', 'expires_at') if field in args.model_fields_set})
                result = self.memories.correct(
                    args.memory_id,
                    text=args.text,
                    expected_version=args.expected_version,
                    update_time_context=args.update_time_context,
                    operation_key=f"tool:{run_context['run']['id']}:{call_id}",
                    subject_key=args.subject_key,
                    kind=args.kind,
                    source_message_ids=self._memory_mutation_source_message_ids(
                        run_context, args.memory_id, str(current_user["id"])
                    ),
                    source_excerpt=str(current_user["content"])[:1000],
                    stated_text=user_words,
                    stated_at=str(current_user["created_at"]),
                    _notification_causes={'run_id':run_context['run']['id'],'thread_id':run_context['thread']['id'],'request_message_id':current_user['id']},
                    **validity_changes,
                )
                return ToolResult(
                    call_id=call_id, status="ok", summary="已纠正正式记忆", items=[result],
                ).model_dump(mode="json")
            if name == "memory_forget":
                args = MemoryForgetArgs.model_validate(arguments)
                self._require_memory_in_scope(args.memory_id, int(space["id"]))
                current_user = self._current_user_message(run_context)
                result = self.memories.forget(
                    args.memory_id,
                    expected_version=args.expected_version,
                    _notification_causes={'run_id':run_context['run']['id'],'thread_id':run_context['thread']['id'],'request_message_id':current_user['id']},
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
                selected_index = 0 if args.item_index is None and len(selected_items) == 1 and (args.field or args.start) else args.item_index
                if selected_index is None:
                    if args.field or args.start:
                        return self._error(call_id, "item_required", f"共有 {len(selected_items)} 条；先指定 item_index（0 至 {max(0,len(selected_items)-1)}）再读取字段")
                    if len(json.dumps(result, ensure_ascii=False)) <= args.max_characters:
                        spans, materials = read_evidence(resolved['name'], result, result_ref=resolved['result_ref'])
                        return ToolResult(call_id=call_id, status="ok",
                                          summary="已读取历史工具结果",
                                          items=[result], result_ref=resolved["result_ref"],
                                          dependency_refs=[resolved["result_ref"]],
                                          coverage={'read_spans': spans, 'materials': materials}).model_dump(mode="json")
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
                if selected_index >= len(selected_items):
                    return self._error(call_id, "item_out_of_range", f"历史结果只有 {len(selected_items)} 条；有效 item_index 为 0 至 {max(0,len(selected_items)-1)}")
                item = selected_items[selected_index]
                if args.candidate_index is not None:
                    candidates = item.get("candidates") or []
                    if args.candidate_index >= len(candidates):
                        return self._error(call_id, "candidate_out_of_range", "候选索引越界，请先回读该来源组")
                    item = candidates[args.candidate_index]
                if args.field:
                    value: Any = item
                    try:
                        value = field_value(value, args.field)
                    except KeyError:
                        return self._error(call_id, "field_not_found", "字段不存在；请按概览的字段路径回读")
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
                spans, materials = [], []
                if (resolved['name'] == 'collection_read' and args.field == 'content'
                        and args.candidate_index is None and isinstance(value, str)):
                    position = item.get('provenance', {}).get('content_position') or {}
                    if position and value:
                        base = int(position.get('start') or 0)
                        copied = json.loads(json.dumps(result))
                        copied['items'] = [{**item, 'content': selected,
                            'provenance': {**item.get('provenance', {}), 'content_position': {
                                'start': base + args.start, 'end': base + end,
                                'total': int(position.get('total') or 0)}}}]
                        spans, materials = read_evidence('collection_read', copied, result_ref=resolved['result_ref'])
                        materials = [m for m in materials if m['view'] == result.get('coverage', {}).get('requested_view')]
                if (resolved['name'].startswith('context7_') and isinstance(value, str)
                        and args.field and args.field.startswith('response.content.') and args.field.endswith('.text')):
                    materials = [{'source_ref': resolved['result_ref'], 'kind': resolved['name'],
                                  'view': '公开文档', 'projection': '原文片段', 'complete': False,
                                  'result_ref': resolved['result_ref'], 'position': {
                                      'item_index': selected_index, 'field': args.field,
                                      'start': args.start, 'end': end, 'total': total}}]
                next_args = ({**args.model_dump(exclude_none=True), 'start': end}
                             if end < total else None)
                return ToolResult(
                    call_id=call_id,
                    status="partial" if end < total else "ok",
                    summary="已按需读取历史工具结果",
                    items=[{
                        "item_index": selected_index, "candidate_index": args.candidate_index, "field": args.field,
                        "value": selected,
                        "position": {"start": args.start, "end": end, "total": total},
                    }],
                    result_ref=resolved["result_ref"],
                    dependency_refs=[resolved["result_ref"]],
                    truncated=end < total,
                    next_cursor=str(end) if end < total else None,
                    coverage={'read_spans': spans, 'materials': materials, 'next_read_args': next_args},
                ).model_dump(mode="json")
            if name == "knowledge_read":
                if self.wiki is None:
                    return self._error(call_id, "knowledge_unavailable", "知识整理当前不可用")
                args = KnowledgeReadArgs.model_validate(arguments)
                try:
                    page = self.wiki.get_page(args.page_id, space_id=int(space["id"]), task_scope=scope if space.get("task_subset") else None)
                except KeyError:
                    return ToolResult(call_id=call_id, status='unavailable', error_code='knowledge_page_unavailable',
                        summary='页面不存在或不在当前授权范围；不同于原页存在但正文不可见，不得猜测页面或新建替代页。',
                        coverage={'body_state':'unavailable_page','page_exists':None}, retryable=False).model_dump(mode='json')
                if args.page_version is not None and (int(page["version"]) != args.page_version or page["id"] != args.page_id):
                    return self._error(call_id, "knowledge_page_version_changed", "知识页版本或定位已变化，请重新 Search")
                read_mode = "block" if args.block_ids or args.block_id else args.mode
                all_blocks = list(page.get("blocks") or [])
                from shiliu.assistant.wiki_recovery import read_state
                state_token = read_state(page)
                blocks = list(all_blocks)
                if args.cursor and read_mode != "page":
                    return self._error(call_id, "cursor_mode_mismatch", "知识页游标仅用于 page 续读")
                start = 0
                if read_mode == "block" or args.block_ids or args.block_id:
                    requested = set(args.block_ids or ([args.block_id] if args.block_id else []))
                    if not requested:
                        return self._error(call_id, "block_required", "需要指定 block_ids")
                    if args.page_version is None:
                        return self._error(call_id, "page_version_required", "稳定块读取需要 Search 返回的 page_version")
                    blocks = [block for block in blocks if str(block.get("stable_id")) in requested]
                    if len(blocks) != len(requested):
                        return self._error(call_id, "knowledge_block_unavailable", "原页存在，但指定块已删除或当前不可见。若已确认原页身份且用户明确授权，可沿原页版本提交knowledge_update_page；不要反复读取失效块。其他情况可重新Search核实。")
                elif read_mode == "page":
                    if args.cursor:
                        version_text, index_text = args.cursor.split(":", 1)
                        if int(version_text) != int(page["version"]):
                            return self._error(call_id, "knowledge_cursor_version_changed",
                                               "知识页版本已变化，请从头读取")
                        start = int(index_text) - 1
                        if start >= len(all_blocks):
                            return self._error(call_id, "knowledge_cursor_invalid", "知识页游标越界")
                    blocks = []
                    # Leave space for the directory and tool envelope. Never
                    # split a block or silently mark the page fully covered.
                    for block in all_blocks[start:]:
                        candidate = [*blocks, block]
                        if len(json.dumps(candidate, ensure_ascii=False)) > 10000:
                            break
                        blocks = candidate
                    if not blocks and start < len(all_blocks):
                        return self._error(call_id, "knowledge_block_too_large",
                                           "单块超过 page 读取上限，请按块定位读取")
                else:
                    blocks = []
                page = {
                    "id": page["id"], "title": page["title"], "summary": page.get("summary"),
                    "version": page.get("version"), "availability": page.get("availability"),
                    "evidence_ref": f"wiki:{page['id']}:{page['version']}",
                    "blocks": [{**{key: value for key, value in block.items()
                                if key in {"stable_id", "heading", "markdown", "role", "applicability", "assessment", "manual_lock", "source_refs", "external_sources", "historical_statement", "validity_note", "expires_at", "source_view"}},
                                "source_refs": self.wiki.block_source_refs([block])}
                               for block in blocks],
                    "available_blocks": [
                        {"id": block.get("stable_id"), "heading": str(block.get("heading") or "")[:100]}
                        for block in all_blocks[:50]
                    ],
                }
                if len(json.dumps(page, ensure_ascii=False)) > 14000:
                    return self._error(call_id, "knowledge_view_too_large", "请指定更窄的知识块")
                next_cursor = (f"{page['version']}:{start + len(blocks) + 1}"
                               if read_mode == "page" and start + len(blocks) < len(all_blocks) else None)
                source_refs = (self.wiki.block_source_refs(all_blocks) if space.get("task_subset") else
                               self.wiki.history_source_refs(str(page["id"]), space_id=int(space["id"])))
                return ToolResult(
                    call_id=call_id, status="ok" if (page["blocks"] or
                        (read_mode == "overview" and all_blocks)) else "empty",
                    summary=(f"已读取主题页：{page['title']}" if all_blocks else f"原页存在，但当前没有可见正文：{page['title']}"), items=[page],
                    next_cursor=next_cursor, truncated=next_cursor is not None,
                    source_refs=source_refs,
                    dependency_refs=self.wiki.personal_dependency_refs(
                        str(page["id"]), space_id=int(space["id"])
                    ),
                    coverage={"mode": read_mode, "total_blocks": len(all_blocks),
                              "page_exists": True, "state_token": state_token,
                              "body_state": "no_visible_body" if not all_blocks else "partially_available" if page.get('availability') == 'partial' else "readable",
                              "recovery_instruction": ("原页身份和版本仍有效。若用户明确授权更新本页，沿原page_id/expected_version用knowledge_update_page写新事实，无需重复空读；不代表已获得新的授权。" if not all_blocks else ""),
                              "save_instruction": "保存本页已读正文时沿用块内完整 source_refs，并用本页 evidence_ref 标明 Wiki 依据；这不代表亲读原材料，不照抄 source_view 为原文阅读。缺正文或要核对原文时再按需读取，不删除来源或改角色绕过校验。",
                              "returned_blocks": len(blocks), "start_block": start,
                              "returned_block_ids": [str(block.get("stable_id")) for block in blocks],
                              "complete": read_mode == "page" and next_cursor is None,
                              "version": page.get("version")},
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
            result = self._error(call_id, "invalid_arguments", "参数字段错误；只更正以下位置", status="invalid_arguments")
            result["items"] = [{"issues": [{"path": ".".join(str(v) if not isinstance(v, int) else f"[{v}]" for v in error["loc"]).replace('.[', '['),
                "code": error["type"], "message": error["msg"], "action": "仅更正工具Schema允许的字段；新建用knowledge_save_request，已有页用knowledge_update_page并绑定page_id/expected_version"} for error in exc.errors()]}]
            return result
        except ValueError as exc:
            if str(exc).startswith(('memory_validity_', 'memory_time_source_', 'memory_invalid_time_', 'memory_fact_', 'memory_event_')):
                explanations = {
                    'memory_event_without_user_basis': '拟保存的事件日期在原事实或原记忆中没有依据；保留原话的时间精度，不添加日期或期限。',
                    'memory_validity_without_user_basis': '这是事件时间，不是记忆有效期；删除无依据的 valid_from/expires_at，按原事实保存即可。',
                    'memory_validity_needs_clarification': '记忆的适用期限尚不明确，请确认有效性范围；普通模糊计划无需填写有效期。',
                    'memory_time_source_ambiguous': '请选择同线程中的一段事实，用 source_excerpt 指向其原话，不能混用其他事实的时间。',
                    'memory_fact_not_user_decision': '来源没有表达本人已作决定；考虑状态可按 context 保存，不把假设或作者建议写成决定。',
                }
                result = self._error(call_id, str(exc), explanations.get(str(exc), str(exc)), status='invalid_arguments')
                result['items'] = [{'issues': [{'code': str(exc), 'action': explanations.get(str(exc), '核对时间字段与真实原话')}]}]
                return result
            if str(exc) in {
                "result_outside_current_scope", "historical_result_stale",
                "historical_result_dependencies_missing",
            }:
                return self._error(
                    call_id,
                    "result_outside_current_scope",
                    "历史结果的记忆、知识或收藏范围依赖已变化，请重新查询",
                )
            result = self._error(call_id, "invalid_arguments", str(exc)[:500], status="invalid_arguments")
            if str(exc).startswith("topics["):
                path, _, code = str(exc).partition(":")
                result["items"] = [{"issues": [{"path": path, "code": code, "message": str(exc), "action": "只更正指定字段"}]}]
            return result
        except Exception as exc:
            if name.startswith("knowledge_") and isinstance(exc, (AssistantConflict, KeyError)):
                code = 'save_reference_not_found' if isinstance(exc, KeyError) else str(exc)
                explanations = {
                    'knowledge_plan_not_repairable': '旧计划状态不可修复，completed 计划不能用于新编辑。用户已授权的同一更正请用新 topics、同标题和 topic.expected_version 页面版本，提交完整有效内容；不要猜计划版本或重复索取同意。',
                    'knowledge_plan_version_conflict': '可修复计划的版本已变化；核对当前计划版本后只修复未成功主题，不猜版本。',
                }
                return self._error(call_id, code, explanations.get(code, str(exc)[:500]), status="invalid_arguments")
            code = str(getattr(exc, "code", None) or type(exc).__name__)
            retryable = bool(getattr(exc, "retryable", False))
            return ToolResult(
                call_id=call_id,
                status="unavailable",
                summary=f"工具调用失败：{str(exc)[:500]}",
                error_code=code,
                retryable=retryable,
            ).model_dump(mode="json")

    def scope_identity(self, space: dict) -> dict:
        scope = SourceScope(source_db_ids=frozenset(space["source_ids"]),
                            video_ids=frozenset(space.get("video_ids") or []), all_active=bool(space["all_active"]))
        actual_ids = sorted(self.sources.visible_video_ids(scope))
        return {"visible_set_hash": hashlib.sha256(json.dumps(actual_ids).encode()).hexdigest(),"scope_version": int(space["scope_version"]), "source_ids": sorted(space["source_ids"]),
                "video_ids": sorted(space.get("video_ids") or []), "all_active": bool(space["all_active"])}

    async def search_knowledge(self, args: UnifiedSearchArgs, *, call_id: str, run_context: dict) -> dict:
        space = run_context["space"]
        scope = SourceScope(source_db_ids=frozenset(space["source_ids"]),
                            video_ids=frozenset(space.get("video_ids") or []), all_active=bool(space["all_active"]))

        def search(source):
            started = time.monotonic()
            try:
                if source == "collection":
                    parameters = args.model_dump(exclude={"sources", "wiki_limit"})
                    if parameters["folder_ids"] is not None:
                        parameters["folder_ids"] = set(parameters["folder_ids"])
                    result = self.sources.search(call_id=call_id, scope=scope, scope_version=int(space["scope_version"]), **parameters).model_dump(mode="json")
                    for candidate in result["items"]:
                        captured = self.sources.snapshots.capture(int(candidate["video_id"]))
                        candidate["revision"] = captured.revision
                        candidate["source_ref"] = f"video:{candidate['video_id']}:{captured.revision}"
                        candidate["read_hints"], candidate["read_hint_unavailable_reasons"] = self.sources.search_read_hints(candidate, captured)
                    result["source_refs"] = [candidate["source_ref"] for candidate in result["items"]]
                    return {"source": source, "status": result["status"], "candidates": result["items"],
                            "source_refs": result["source_refs"], "coverage": {**result["coverage"],
                                "query": args.query, "candidate_count": len(result["items"]),
                                "elapsed_ms": round((time.monotonic() - started) * 1000)},
                            "next_cursor": result["next_cursor"], "truncated": result["truncated"],
                            "error_code": result["error_code"], "retryable": result["retryable"]}
                if self.wiki is None or self.wiki.retrieval is None:
                    raise RuntimeError("wiki_retrieval_unavailable")
                pages = self.wiki.list_pages(space_id=int(space["id"]), task_scope=scope if space.get("task_subset") else None)
                result = self.wiki.retrieval.search(str(args.query), space_id=int(space["id"]), task_scope=scope if space.get("task_subset") else None, thread_id=str(run_context["thread"]["id"]), limit=args.wiki_limit)
                refs, dependencies = set(), set()
                admitted = []
                for candidate in result["candidates"]:
                    page = self.wiki.get_page(candidate["page_id"], space_id=int(space["id"]), task_scope=scope if space.get("task_subset") else None)
                    if page["id"] != candidate["page_id"] or page["version"] != candidate["page_version"]:
                        continue
                    visible = {block["stable_id"]: block for block in page["blocks"]}
                    original = next(value for value in pages if value["id"] == page["id"])
                    prior = {block["stable_id"]: block for block in original["blocks"]}
                    candidate["hits"] = [hit for hit in candidate["hits"] if hit["block_id"] in visible
                                         and visible[hit["block_id"]] == prior[hit["block_id"]]]
                    for hit in candidate["hits"]:
                        hit["projection_hash"] = self.block_projection_hash(visible[hit["block_id"]])
                    if candidate["hits"]:
                        admitted.append(candidate)
                        refs.update(self.wiki.block_source_refs(page["blocks"]))
                        dependencies.update(self.wiki.personal_dependency_refs(page["id"], space_id=int(space["id"])))
                result["candidates"] = admitted
                result["source_refs"] = sorted(refs)
                result["dependency_refs"] = sorted(dependencies)
                result["coverage"]["candidate_count"] = len(admitted)
                return result
            except Exception as exc:
                return {"source": source, "status": "unavailable", "candidates": [],
                        "coverage": {"query": args.query, "exhaustive": False, "candidate_count": 0,
                                     "elapsed_ms": round((time.monotonic() - started) * 1000)},
                        "error_code": type(exc).__name__, "retryable": True, "summary": str(exc)[:250]}

        groups = await asyncio.gather(*(asyncio.to_thread(search, source) for source in args.sources))
        statuses = [group["status"] for group in groups]
        failed = any(status not in {"ok", "empty"} for status in statuses)
        status = ("partial" if any(group["candidates"] or group["status"] in {"ok", "empty"} for group in groups) else "unavailable") if failed else ("ok" if any(group["candidates"] for group in groups) else "empty")
        return ToolResult(call_id=call_id, status=status, summary="知识候选发现；需 Read 正文后判断依据",
                          items=groups, source_refs=sorted({ref for group in groups for ref in group.get("source_refs", [])}),
                          dependency_refs=sorted({ref for group in groups for ref in group.get("dependency_refs", [])}),
                          next_cursor=next((group.get("next_cursor") for group in groups if group["source"] == "collection"), None),
                          coverage={"canonical_name": "search_knowledge", "scope": self.scope_identity(space), "sources": args.sources, "candidate_only": True,
                                    "query": args.query, "exhaustive": False}).model_dump(mode="json")

    @staticmethod
    def block_projection_hash(block: dict) -> str:
        return hashlib.sha256(json.dumps(block, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def _validate_historical_result(
        self,
        resolved: dict[str, Any],
        *,
        scope: SourceScope,
        space_id: int,
        thread_id: str,
        scope_version: int,
        visited: set[tuple[str, str]] | None = None,
        space_override: dict | None = None,
    ) -> None:
        seen = visited if visited is not None else set()
        identity = (str(resolved["run_id"]), str(resolved["call_id"]))
        if identity in seen or len(seen) >= 8:
            raise ValueError("historical_result_stale")
        seen.add(identity)
        result = resolved["result"]
        if result.get("coverage", {}).get("discarded"):
            raise ValueError("historical_result_stale")
        name = str(result.get("coverage", {}).get("canonical_name") or resolved["name"])
        if name == 'conversation_history':
            for group in result.get('items') or []:
                for prior in group.get('messages') or []:
                    message = self.store.knowledge_message(prior['message_id'], thread_id=thread_id,
                                                           allow_operation_receipt=True)
                    refs = json_object(message.get('provider_payload_json') or '{}').get('dependency_refs') or []
                    if refs and not self.dependency_refs_valid(refs, space_id, thread_id, scope_version, space_override=space_override):
                        raise ValueError('historical_result_stale')
            return
        if name == "task_focus":
            suppressed = self.memories.suppressed_source_message_ids(space_id=space_id)
            for focus in result.get("items") or []:
                if (str(focus.get("source_message_id") or "") in suppressed or
                        set(focus.get("inherited_message_ids") or []).intersection(suppressed)):
                    raise ValueError("historical_result_stale")
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
                    "SELECT id,kind,payload_json FROM assistant_jobs WHERE workspace_id=%s AND principal_id=%s AND id=ANY(%s)",
                    (self.store.context.workspace_id,self.store.principal_id,job_ids),
                ).fetchall()
            if len(rows) != len(job_ids) or any(
                row["kind"] != "source_reconcile" or
                int(json_object(row["payload_json"] or "{}").get("space_id") or 0) != space_id or
                str(json_object(row["payload_json"] or "{}").get("task_topic") or "") != str(item.get("topic") or "")
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
                space_override=space_override,
            )
        if name == "run_read_result":
            if not declared_refs:
                raise ValueError("historical_result_dependencies_missing")
            return
        source_refs = result.get("source_refs") or []
        if name == "collection_read" and result.get("items") and not source_refs:
            raise ValueError("historical_result_dependencies_missing")
        if name == "collection_read":
            if not self._collection_read_current(result, scope):
                raise ValueError("historical_result_stale")
        elif name != "search_knowledge" and not self._source_refs_current(source_refs, scope):
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
        if name == "search_knowledge":
            coverage = result.get("coverage") or {}
            if coverage.get("origin") == "bootstrap" and str(coverage.get("source_message_id") or "") in self.memories.suppressed_source_message_ids(space_id=space_id):
                raise ValueError("historical_result_stale")
            if result.get("coverage", {}).get("scope") != self.scope_identity(space_override if space_override is not None else self.store.task_space(thread_id)):
                raise ValueError("result_outside_current_scope")
            for group in result.get("items") or []:
                if group.get("source") == "wiki":
                    for candidate in group.get("candidates") or []:
                        page = self.wiki.get_page(candidate["page_id"], space_id=space_id, task_scope=scope if (space_override if space_override is not None else self.store.task_space(thread_id)).get("task_subset") else None)
                        visible = {block["stable_id"]: block for block in page["blocks"]}
                        if page["id"] != candidate["page_id"] or page["version"] != candidate["page_version"]:
                            raise ValueError("historical_result_stale")
                        for hit in candidate["hits"]:
                            if hit["block_id"] not in visible or hit["projection_hash"] != self.block_projection_hash(visible[hit["block_id"]]):
                                raise ValueError("historical_result_stale")
                elif group.get("source") == "collection":
                    if not self._source_refs_current(group.get("source_refs") or [], scope):
                        raise ValueError("historical_result_stale")
                else:
                    raise ValueError("historical_result_stale")
            return
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
                page = self.wiki.get_page(page_id, space_id=space_id, task_scope=scope if (space_override if space_override is not None else self.store.task_space(thread_id)).get("task_subset") else None) if self.wiki else None
                if (page is None or str(page["id"]) != page_id or not page["blocks"] or
                        int(page["version"]) != version):
                    raise ValueError("historical_result_stale")
                prior_item = next(item for item in result.get("items") or []
                                  if isinstance(item, dict) and
                                  str(item.get("page_id") or item.get("id")) == page_id)
                if name == "knowledge_read":
                    visible_keys = {"stable_id", "heading", "markdown", "applicability",
                                    "assessment", "source_refs"}
                    def block_content(block):
                        # Old frozen reads contain storage revision hashes. Compare
                        # both forms through the existing lineage resolver, without
                        # changing the original receipt or accepting hashes on writes.
                        return json.dumps({**{key: value for key, value in block.items() if key in visible_keys},
                                           'source_refs': self.wiki.block_source_refs([block])},
                                          sort_keys=True, ensure_ascii=False)
                    current_blocks = {block_content(block) for block in page["blocks"]}
                    prior_blocks = prior_item.get("blocks") or []
                    if (any(block_content(block)
                            not in current_blocks for block in prior_blocks)
                            or str(prior_item.get("summary") or "") != str(page["summary"] or "")):
                        raise ValueError("historical_result_stale")
                if name == "knowledge_search" and str(prior_item.get("summary") or "") != str(page["summary"] or ""):
                    raise ValueError("historical_result_stale")
                current_refs.update(self.wiki.block_source_refs(page["blocks"])
                    if (space_override if space_override is not None else self.store.task_space(thread_id)).get("task_subset") else
                    self.wiki.history_source_refs(page_id, space_id=space_id))
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
        with self.store.db.connect() as connection:
            rows = connection.execute(
                "SELECT video_id,current_revision FROM assistant_source_heads WHERE workspace_id=%s AND principal_id=%s AND video_id=ANY(%s)",
                (self.store.context.workspace_id,self.store.principal_id,list(versioned)),
            ).fetchall()
        current = {int(row["video_id"]): str(row["current_revision"]) for row in rows}
        return all(current.get(video_id) == revision for video_id, revision in versioned.items())

    def _collection_read_current(self, result: dict[str, Any], scope: SourceScope) -> bool:
        refs = [str(value) for value in result.get("source_refs") or []]
        if len(refs) != 1 or not self.sources.source_refs_visible(refs, scope):
            return False
        parts = refs[0].split(":")
        if len(parts) == 2 and parts[0] == "video" and parts[1].isdigit():
            # Legacy receipts did not carry a revision or view. Preserve their
            # prior scope-only behavior; never infer a new fine-grained type.
            return self._source_refs_current(refs, scope)
        if len(parts) != 3 or parts[0] != "video" or not parts[1].isdigit():
            return False
        video_id, revision = int(parts[1]), parts[2]
        with self.store.db.connect() as connection:
            row = connection.execute(
                "SELECT current_revision FROM assistant_source_heads WHERE workspace_id=%s AND principal_id=%s AND video_id=%s",
                (self.store.context.workspace_id,self.store.principal_id, video_id),
            ).fetchone()
        if row is None:
            return False
        current_revision = str(row["current_revision"] or "")
        if current_revision == revision:
            return True
        view = str((result.get("coverage") or {}).get("requested_view") or "")
        if view not in {"transcript", "summary", "description", "notes"}:
            return False
        try:
            old = self.sources._capture_or_load(video_id, revision).snapshot
            new = self.sources._capture_or_load(video_id, current_revision).snapshot
        except (OSError, ValueError, KeyError):
            return False
        if view == "transcript":
            material = "raw_subtitle" if old.get("materials", {}).get("raw_subtitle") else "transcript"
            return bool(old.get("material_hashes", {}).get(material)) and (
                old.get("material_hashes", {}).get(material) == new.get("material_hashes", {}).get(material)
            )
        if view == "summary":
            return bool(old.get("material_hashes", {}).get("summary")) and (
                old.get("material_hashes", {}).get("summary") == new.get("material_hashes", {}).get("summary")
            )
        if view == "description":
            return (old.get("metadata", {}).get("description")
                    == new.get("metadata", {}).get("description"))
        return [item.get("content") for item in old.get("notes", [])] == [
            item.get("content") for item in new.get("notes", [])
        ]

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
                payload = json_object(message.get("provider_payload_json") or "{}")
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
