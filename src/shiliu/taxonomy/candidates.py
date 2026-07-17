from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.domain import PipelineError


CANDIDATE_TABLE_VERSION = "compact-domain-candidates-v2"
CONTENT_TYPE_TABLE_VERSION = "compact-content-type-candidates-v2"
LOCAL_TOP_LEVEL_SCHEMA_VERSION = "local-top-level-domain-schema-v2"
TOP_LEVEL_DOMAIN_SCHEMA_VERSION = "two-level-domain-draft-schema-v2"
CONTENT_TYPE_SCHEMA_VERSION = "content-type-local-schema-v2"
CONTENT_TYPE_DRAFT_SCHEMA_VERSION = "content-type-draft-schema-v2"
LOCAL_TOP_LEVEL_PROMPT_VERSION = "top-level-local-discovery-v2"
TOP_LEVEL_CONSOLIDATION_PROMPT_VERSION = "two-level-domain-consolidation-v2"
CONTENT_TYPE_PROMPT_VERSION = "content-type-discovery-v2"
CONTENT_TYPE_NORMALIZATION_VERSION = "content-type-candidate-normalization-v2"
CONTENT_TYPE_CONSOLIDATION_PROMPT_VERSION = "content-type-consolidation-v2"
CANDIDATE_NORMALIZATION_VERSION = "candidate-normalization-v2"


class TopicHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    supporting_ids: list[str] = Field(min_length=1, max_length=5)

    @model_validator(mode="before")
    @classmethod
    def cap_bounded_fields(cls, value):
        return _cap_fields(value, text={"name": 60}, lists={"supporting_ids": 5})


class LocalTopLevelDomainCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provisional_id: str = Field(pattern=r"^ld_[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=60)
    definition: str = Field(min_length=1, max_length=140)
    supporting_ids: list[str] = Field(min_length=1, max_length=5)
    representative_ids: list[str] = Field(default_factory=list, max_length=3)
    evidence_codes: list[str] = Field(default_factory=list, max_length=3)
    includes: list[str] = Field(default_factory=list, max_length=3)
    excludes: list[str] = Field(default_factory=list, max_length=3)
    possible_parent: str | None = Field(default=None, max_length=60)
    confidence: Literal["high", "medium", "low"] = "medium"
    node_type: Literal["domain"] = "domain"

    @model_validator(mode="before")
    @classmethod
    def cap_bounded_fields(cls, value):
        return _cap_fields(
            value,
            text={"name": 60, "definition": 140},
            lists={
                "supporting_ids": 5,
                "representative_ids": 3,
                "evidence_codes": 3,
                "includes": 3,
                "excludes": 3,
            },
        )


class LocalTopLevelDiscoveryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domains: list[LocalTopLevelDomainCandidate] = Field(default_factory=list, max_length=8)
    topic_hints: list[TopicHint] = Field(default_factory=list, max_length=5)
    ambiguous_ids: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="before")
    @classmethod
    def cap_bounded_fields(cls, value):
        return _cap_fields(
            value,
            lists={"domains": 8, "topic_hints": 5, "ambiguous_ids": 32},
        )


class ContentTypeCandidateV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provisional_id: str = Field(pattern=r"^lct_[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=60)
    definition: str = Field(min_length=1, max_length=140)
    includes: list[str] = Field(default_factory=list, max_length=3)
    excludes: list[str] = Field(default_factory=list, max_length=3)
    supporting_ids: list[str] = Field(min_length=1, max_length=5)
    representative_ids: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="before")
    @classmethod
    def cap_bounded_fields(cls, value):
        return _cap_fields(
            value,
            text={"name": 60, "definition": 140},
            lists={
                "includes": 3,
                "excludes": 3,
                "supporting_ids": 5,
                "representative_ids": 3,
            },
        )


class ContentTypeDiscoveryOutputV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_types: list[ContentTypeCandidateV1] = Field(min_length=1, max_length=8)
    ambiguous_ids: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="before")
    @classmethod
    def cap_bounded_fields(cls, value):
        return _cap_fields(value, lists={"content_types": 8, "ambiguous_ids": 32})


class CompactContentTypeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^nct_[0-9]{3}$")
    name: str = Field(min_length=1, max_length=60)
    definition: str = Field(min_length=1, max_length=140)
    includes: list[str] = Field(default_factory=list, max_length=3)
    excludes: list[str] = Field(default_factory=list, max_length=3)
    support_count: int = Field(ge=1)
    batch_count: int = Field(ge=1)
    supporting_ids: list[str] = Field(min_length=1, max_length=5)
    representative_ids: list[str] = Field(min_length=1, max_length=3)


class CompactContentTypeTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = CONTENT_TYPE_TABLE_VERSION
    content_types: list[CompactContentTypeCandidate] = Field(
        default_factory=list, max_length=24
    )
    source_batch_count: int = Field(ge=1)


class ContentTypeNodeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^ct_[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=60)
    definition: str = Field(min_length=1, max_length=180)
    includes: list[str] = Field(min_length=1, max_length=5)
    excludes: list[str] = Field(min_length=1, max_length=5)
    supporting_ids: list[str] = Field(min_length=1, max_length=32)
    representative_ids: list[str] = Field(min_length=1, max_length=3)
    node_type: Literal["content_type"] = "content_type"

    @model_validator(mode="before")
    @classmethod
    def cap_bounded_fields(cls, value):
        return _cap_fields(
            value,
            text={"name": 60, "definition": 180},
            lists={
                "includes": 5,
                "excludes": 5,
                "supporting_ids": 32,
                "representative_ids": 3,
            },
        )


class ContentTypeCandidateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^nct_[0-9]{3}$")
    action: Literal["merged_to_content_type", "rejected"]
    target_id: str | None = Field(default=None, pattern=r"^ct_[a-z0-9_]+$")
    reason: str = Field(min_length=1, max_length=180)


class ContentTypeDraftV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_types: list[ContentTypeNodeV1] = Field(min_length=1, max_length=8)
    candidate_decisions: list[ContentTypeCandidateDecision] = Field(default_factory=list)
    consolidation_notes: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="before")
    @classmethod
    def cap_notes(cls, value):
        return _cap_fields(value, lists={"consolidation_notes": 5})


class CompactDomainCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^nc_[0-9]{3}$")
    name: str = Field(min_length=1, max_length=60)
    definition: str = Field(min_length=1, max_length=140)
    support_count: int = Field(ge=1)
    batch_count: int = Field(ge=1)
    supporting_ids: list[str] = Field(min_length=1, max_length=5)
    representative_ids: list[str] = Field(min_length=1, max_length=3)
    evidence_codes: list[str] = Field(default_factory=list, max_length=3)
    includes: list[str] = Field(default_factory=list, max_length=3)
    excludes: list[str] = Field(default_factory=list, max_length=3)
    parent_hints: list[str] = Field(default_factory=list, max_length=3)
    confidence: Literal["high", "medium", "low"] = "medium"


class CompactTopicHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    support_count: int = Field(ge=1)
    supporting_ids: list[str] = Field(min_length=1, max_length=5)


class CompactCandidateTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = CANDIDATE_TABLE_VERSION
    domains: list[CompactDomainCandidate] = Field(default_factory=list, max_length=48)
    topic_hints: list[CompactTopicHint] = Field(default_factory=list, max_length=16)
    source_batch_count: int = Field(ge=1)


class SubdomainNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^d_[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1, max_length=240)
    includes: list[str] = Field(min_length=1, max_length=5)
    excludes: list[str] = Field(min_length=1, max_length=5)
    supporting_ids: list[str] = Field(min_length=1, max_length=32)
    representative_ids: list[str] = Field(min_length=1, max_length=3)
    parent_id: str = Field(pattern=r"^d_[a-z0-9_]+$")
    node_type: Literal["domain"] = "domain"


class TopLevelDomainNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^d_[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1, max_length=240)
    includes: list[str] = Field(min_length=1, max_length=5)
    excludes: list[str] = Field(min_length=1, max_length=5)
    supporting_ids: list[str] = Field(min_length=1, max_length=32)
    representative_ids: list[str] = Field(min_length=1, max_length=3)
    children: list[SubdomainNode] = Field(default_factory=list, max_length=6)

    @model_validator(mode="before")
    @classmethod
    def cap_bounded_fields(cls, value):
        return _cap_fields(
            value,
            text={"name": 80, "definition": 240},
            lists={
                "includes": 5,
                "excludes": 5,
                "supporting_ids": 32,
                "representative_ids": 3,
            },
        )


class DomainCandidateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^nc_[0-9]{3}$")
    action: Literal[
        "merged_to_domain",
        "downgraded_to_topic",
        "downgraded_to_entity",
        "rejected",
    ]
    target_id: str | None = Field(default=None, pattern=r"^d_[a-z0-9_]+$")
    reason: str = Field(min_length=1, max_length=180)


class TopLevelDomainDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domains: list[TopLevelDomainNode] = Field(min_length=1, max_length=12)
    candidate_decisions: list[DomainCandidateDecision] = Field(default_factory=list)
    consolidation_notes: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="before")
    @classmethod
    def cap_auxiliary_notes(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        notes = normalized.get("consolidation_notes")
        if isinstance(notes, list):
            normalized["consolidation_notes"] = notes[:5]
        return normalized


class DualViewDiscoveryOutputV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["dual-view-discovery-output-v1"] = "dual-view-discovery-output-v1"
    domain_input_view: Literal["classification_profile_v1", "compact"]
    content_type_input_view: Literal["compact_form_view_v1"] = "compact_form_view_v1"
    domain_draft: TopLevelDomainDraft
    content_type_draft: ContentTypeDraftV1


LOCAL_TOP_LEVEL_SCHEMA_HINT = (
    '{"domains":[{"provisional_id":"ld_x","name":"短名称",'
    '"definition":"一句话定义","supporting_ids":["C001"],'
    '"representative_ids":["C001"],'
    '"evidence_codes":["durable_domain"],"includes":[""],'
    '"excludes":[""],"possible_parent":null,"confidence":"high|medium|low",'
    '"node_type":"domain"}],'
    '"topic_hints":[{"name":"短名称","supporting_ids":["C002"]}],'
    '"ambiguous_ids":["C003"]}'
)
CONTENT_TYPE_SCHEMA_HINT = (
    '{"content_types":[{"provisional_id":"lct_x","name":"短名称",'
    '"definition":"一句话定义","includes":[""],"excludes":[""],'
    '"supporting_ids":["C001"],"representative_ids":["C001"]}],'
    '"ambiguous_ids":["C002"]}'
)
CONTENT_TYPE_CONSOLIDATION_SCHEMA_HINT = (
    '{"content_types":[{"id":"ct_01","name":"",'
    '"definition":"","includes":[""],"excludes":[""],'
    '"supporting_ids":["C001"],"representative_ids":["C001"],'
    '"node_type":"content_type"}],"candidate_decisions":['
    '{"candidate_id":"nct_001","action":"merged_to_content_type|rejected",'
    '"target_id":"ct_01|null","reason":""}],"consolidation_notes":[]}'
)
TOP_LEVEL_CONSOLIDATION_SCHEMA_HINT = (
    '{"domains":[{"id":"d_01","name":"","definition":"",'
    '"includes":[""],"excludes":[""],"supporting_ids":["C001"],'
    '"representative_ids":["C001"],"children":[{"id":"d_01_01",'
    '"name":"","definition":"","includes":[""],"excludes":[""],'
    '"supporting_ids":["C001"],"representative_ids":["C001"],'
    '"parent_id":"d_01","node_type":"domain"}]}],"candidate_decisions":['
    '{"candidate_id":"nc_001","action":"merged_to_domain|downgraded_to_topic|'
    'downgraded_to_entity|rejected","target_id":"d_01|null","reason":""}],'
    '"consolidation_notes":[""]}'
)


def build_top_level_local_prompt(
    rows: list[list[Any]], *, representation: str = "compact"
) -> str:
    if representation == "compact":
        row_protocol = (
            "A/B=[id,等级,标题,一句话结论,最多3条观点,最多5个已有实体]；"
            "C=[id,C,标题,最多300字简介]。"
        )
    elif representation == "classification_profile_v1":
        row_protocol = (
            "Profile=[id,等级,main_subject,content_goal,最多5个key_concepts,"
            "最多3个usage_contexts,最多5个entities,最多3个unknown_terms]。"
        )
    else:
        raise ValueError("Unsupported taxonomy discovery representation")
    return f"""你是局部知识领域候选发现器，不生成最终 Taxonomy，也不在单批中建立完整树。
只发现长期稳定、适合浏览的 Domain 候选，并用 possible_parent 保留可能的父级方向。不得输出 Content Type、Entity 或完整 Topic。
项目、工具、模型、论文、人物、公司和短期术语不得成为 Domain。
每批最多 8 个 Domain；每个候选写短名称、一句话定义、includes/excludes、最多 5 个 supporting IDs、最多 3 个 representative IDs、可能父级、置信度和最多 3 个短证据代码。
如必须保留阶段性信号，只能输出最多 5 个 topic_hints，且只有短名称和 supporting IDs。
证据不足内容放入 ambiguous_ids。所有 ID 必须来自本批。只输出 JSON。
名称和定义使用中文，专有名词保留英文；定义最多 140 个字符。

精简输出结构：{LOCAL_TOP_LEVEL_SCHEMA_HINT}
输入行协议：{row_protocol}
本批卡片：
{_rows_text(rows)}"""


def build_content_type_prompt(rows: list[list[Any]]) -> str:
    return f"""你是独立 Content Type 候选发现器。
Content Type 只回答内容采用什么表达形式或使用形式，不回答知识领域。
不得输出 Domain、Topic 或 Entity。最多输出 8 个候选，每个候选只保留短名称、一句话定义、includes/excludes、最多 5 个 supporting IDs 和最多 3 个 representative IDs。
证据不足内容放入 ambiguous_ids。所有 ID 必须来自本批。只输出 JSON。
名称和定义使用中文，专有名词保留英文；定义最多 140 个字符。

精简输出结构：{CONTENT_TYPE_SCHEMA_HINT}
输入行协议：A/B=[id,等级,标题,一句话结论,最多3条观点,最多5个已有实体]；C=[id,C,标题,最多300字简介]。
本批卡片：
{_rows_text(rows)}"""


def build_content_type_consolidation_prompt(
    table: CompactContentTypeTable,
) -> str:
    return f"""你是全局 Content Type 归并器，只处理内容表达形式，不处理知识领域。
输入只有分批 Content Type 候选表，不包含 Domain、Topic、Entity、Profile 或完整卡片。
合并语义相同但名称不同的候选，生成 2 至 8 个稳定 Content Type；不得输出或暗示 Domain Tree。
每个节点保留短名称、定义、includes/excludes、supporting IDs 和最多 3 个 representative IDs。
必须为输入表中的每个 candidate_id 输出一条 candidate_decisions，说明合并到哪个 Content Type 或拒绝及原因。
supporting_ids 只能来自输入；representative_ids 必须属于 supporting_ids。名称和定义使用中文，专有名词保留英文。只输出 JSON。

精简输出结构：{CONTENT_TYPE_CONSOLIDATION_SCHEMA_HINT}
Compact Content Type Table：{_compact_json(table.model_dump(mode="json"))}"""


def build_top_level_consolidation_prompt(table: CompactCandidateTable) -> str:
    payload = {
        "version": table.version,
        "domains": [item.model_dump(mode="json") for item in table.domains],
    }
    return f"""你是全局一级 Domain 归并器。
输入只有确定性归一化后的 Compact Candidate Table，不包含卡片、原始局部响应、Content Type、Entity 或 Topic。
合并语义相同但名称不同的候选，统一名称，生成短定义和必要的 includes/excludes。
输出通常 5 至 10 个一级 Domain，硬上限 12 个；每个一级 Domain 可有 0 至 6 个二级 Domain，最多两级。
只有存在语义明显不同、边界清晰、有足够语料支持且长期可复用的稳定子群时才生成 children；不得机械补齐二级分类。
名称、定义和边界说明使用中文，专有名词保留英文。每个节点 includes/excludes 各最多 5 条。
supporting_ids 只能来自输入；representative_ids 必须属于 supporting_ids 且最多 3 个。只输出 JSON。
必须为输入表中的每个 candidate_id 输出一条 candidate_decisions，说明合并到哪个 Domain、降级为 Topic/Entity，或拒绝及原因。
consolidation_notes 是可选辅助信息，最多 5 条；不要逐节点重复解释。

精简输出结构：{TOP_LEVEL_CONSOLIDATION_SCHEMA_HINT}
Compact Candidate Table：{_compact_json(payload)}"""


def validate_local_top_level(
    value: LocalTopLevelDiscoveryOutput, allowed_ids: set[str]
) -> None:
    used = set(value.ambiguous_ids)
    provisional_ids = [item.provisional_id for item in value.domains]
    if len(provisional_ids) != len(set(provisional_ids)):
        raise PipelineError(
            "局部一级 Domain provisional_id 不唯一",
            code="local_domain_id_collision",
            retryable=False,
        )
    for item in [*value.domains, *value.topic_hints]:
        used.update(item.supporting_ids)
        if isinstance(item, LocalTopLevelDomainCandidate):
            if not set(item.representative_ids) <= set(item.supporting_ids):
                raise PipelineError(
                    "局部 Domain representative_ids 不属于 supporting_ids",
                    code="local_domain_representative_mismatch",
                    retryable=False,
                )
    if not used <= allowed_ids:
        raise PipelineError(
            "局部一级候选引用了本批之外的短 ID",
            code="local_domain_support_mismatch",
            retryable=False,
        )


def validate_content_types(
    value: ContentTypeDiscoveryOutputV1, allowed_ids: set[str]
) -> None:
    used = set(value.ambiguous_ids)
    for item in value.content_types:
        used.update(item.supporting_ids)
        if not set(item.representative_ids) <= set(item.supporting_ids):
            raise PipelineError(
                "局部 Content Type representative_ids 不属于 supporting_ids",
                code="content_type_representative_mismatch",
                retryable=False,
            )
    if not used <= allowed_ids:
        raise PipelineError(
            "Content Type 候选引用了本批之外的短 ID",
            code="content_type_support_mismatch",
            retryable=False,
        )


def normalize_content_types(
    outputs: list[ContentTypeDiscoveryOutputV1], *, allowed_ids: set[str]
) -> CompactContentTypeTable:
    if not outputs:
        raise ValueError("Content Type normalization requires at least one batch")
    grouped: dict[str, list[tuple[int, ContentTypeCandidateV1]]] = defaultdict(list)
    for batch_index, output in enumerate(outputs, start=1):
        validate_content_types(output, allowed_ids)
        for candidate in output.content_types:
            grouped[normalized_name(candidate.name)].append((batch_index, candidate))
    content_types: list[CompactContentTypeCandidate] = []
    for ordinal, key in enumerate(sorted(grouped), start=1):
        values = grouped[key]
        names = sorted(
            {item.name.strip() for _, item in values}, key=lambda item: (len(item), item)
        )
        definitions = sorted(
            {item.definition.strip()[:140] for _, item in values},
            key=lambda item: (len(item), item),
        )
        support = sorted(
            {short_id for _, item in values for short_id in item.supporting_ids},
            key=_short_id_order,
        )
        content_types.append(
            CompactContentTypeCandidate(
                candidate_id=f"nct_{ordinal:03d}",
                name=names[0],
                definition=definitions[0],
                includes=sorted(
                    {value for _, item in values for value in item.includes if value}
                )[:3],
                excludes=sorted(
                    {value for _, item in values for value in item.excludes if value}
                )[:3],
                support_count=len(support),
                batch_count=len({batch_index for batch_index, _ in values}),
                supporting_ids=support[:5],
                representative_ids=support[:3],
            )
        )
    return CompactContentTypeTable(
        content_types=content_types,
        source_batch_count=len(outputs),
    )


def validate_content_type_draft(
    value: ContentTypeDraftV1,
    *,
    allowed_ids: set[str],
    candidate_ids: set[str] | None = None,
) -> None:
    ids = [item.id for item in value.content_types]
    names = [normalized_name(item.name) for item in value.content_types]
    if len(ids) != len(set(ids)) or len(names) != len(set(names)):
        raise PipelineError(
            "Content Type Draft ID 或名称重复",
            code="content_type_draft_collision",
            retryable=False,
        )
    used = {
        short_id for item in value.content_types for short_id in item.supporting_ids
    }
    if not used <= allowed_ids:
        raise PipelineError(
            "Content Type Draft 引用了未知短 ID",
            code="content_type_draft_support_mismatch",
            retryable=False,
        )
    if any(
        not set(item.representative_ids) <= set(item.supporting_ids)
        for item in value.content_types
    ):
        raise PipelineError(
            "Content Type representative_ids 不属于 supporting_ids",
            code="content_type_draft_representative_mismatch",
            retryable=False,
        )
    _validate_content_type_decisions(value, candidate_ids=candidate_ids)


def _validate_content_type_decisions(
    value: ContentTypeDraftV1, *, candidate_ids: set[str] | None
) -> None:
    decisions = value.candidate_decisions
    decision_ids = [item.candidate_id for item in decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise PipelineError(
            "Content Type candidate_decisions 重复",
            code="content_type_decision_collision",
            retryable=False,
        )
    if candidate_ids is not None and set(decision_ids) != candidate_ids:
        raise PipelineError(
            "Content Type candidate_decisions 未覆盖全部归一化候选",
            code="content_type_decision_coverage_mismatch",
            retryable=False,
        )
    target_ids = {item.id for item in value.content_types}
    invalid = [
        item.candidate_id
        for item in decisions
        if (
            item.action == "merged_to_content_type"
            and item.target_id not in target_ids
        )
        or (item.action == "rejected" and item.target_id is not None)
    ]
    if invalid:
        raise PipelineError(
            "Content Type candidate_decisions 的 target_id 无效",
            code="content_type_decision_target_mismatch",
            retryable=False,
        )


def normalize_candidates(
    outputs: list[LocalTopLevelDiscoveryOutput], *, allowed_ids: set[str]
) -> CompactCandidateTable:
    if not outputs:
        raise ValueError("Candidate normalization requires at least one batch")
    grouped: dict[str, list[tuple[int, LocalTopLevelDomainCandidate]]] = defaultdict(list)
    for batch_index, output in enumerate(outputs, start=1):
        validate_local_top_level(output, allowed_ids)
        for candidate in output.domains:
            grouped[normalized_name(candidate.name)].append((batch_index, candidate))

    domains: list[CompactDomainCandidate] = []
    for ordinal, key in enumerate(sorted(grouped), start=1):
        values = grouped[key]
        names = sorted({item.name.strip() for _, item in values}, key=lambda item: (len(item), item))
        definitions = sorted(
            {item.definition.strip()[:140] for _, item in values},
            key=lambda item: (len(item), item),
        )
        all_support = sorted(
            {content_id for _, item in values for content_id in item.supporting_ids},
            key=_short_id_order,
        )
        evidence_codes = sorted(
            {code.strip() for _, item in values for code in item.evidence_codes if code.strip()}
        )[:3]
        domains.append(
            CompactDomainCandidate(
                candidate_id=f"nc_{ordinal:03d}",
                name=names[0],
                definition=definitions[0],
                support_count=len(all_support),
                batch_count=len({batch_index for batch_index, _ in values}),
                supporting_ids=all_support[:5],
                representative_ids=all_support[:3],
                evidence_codes=evidence_codes,
                includes=sorted(
                    {value for _, item in values for value in item.includes if value}
                )[:3],
                excludes=sorted(
                    {value for _, item in values for value in item.excludes if value}
                )[:3],
                parent_hints=sorted(
                    {
                        item.possible_parent
                        for _, item in values
                        if item.possible_parent
                    }
                )[:3],
                confidence=(
                    "high"
                    if any(item.confidence == "high" for _, item in values)
                    else "medium"
                ),
            )
        )

    topic_groups: dict[str, set[str]] = defaultdict(set)
    topic_names: dict[str, set[str]] = defaultdict(set)
    for output in outputs:
        for topic in output.topic_hints:
            key = normalized_name(topic.name)
            topic_names[key].add(topic.name.strip())
            topic_groups[key].update(topic.supporting_ids)
    topic_hints = []
    for key in sorted(topic_groups)[:16]:
        support = sorted(topic_groups[key], key=_short_id_order)
        names = sorted(topic_names[key], key=lambda item: (len(item), item))
        topic_hints.append(
            CompactTopicHint(
                name=names[0],
                support_count=len(support),
                supporting_ids=support[:5],
            )
        )
    return CompactCandidateTable(
        domains=domains,
        topic_hints=topic_hints,
        source_batch_count=len(outputs),
    )


def validate_top_level_draft(
    value: TopLevelDomainDraft,
    *,
    allowed_ids: set[str],
    candidate_ids: set[str] | None = None,
) -> None:
    all_nodes = [*value.domains, *(child for item in value.domains for child in item.children)]
    ids = [item.id for item in all_nodes]
    names = [normalized_name(item.name) for item in all_nodes]
    if len(ids) != len(set(ids)):
        raise PipelineError(
            "一级 Domain ID 不唯一", code="top_level_domain_id_collision", retryable=False
        )
    if len(names) != len(set(names)):
        raise PipelineError(
            "一级 Domain 名称重复", code="top_level_domain_name_collision", retryable=False
        )
    used = {content_id for item in all_nodes for content_id in item.supporting_ids}
    if not used <= allowed_ids:
        raise PipelineError(
            "一级 Domain Draft 引用了未知短 ID",
            code="top_level_domain_support_mismatch",
            retryable=False,
        )
    bad_representatives = [
        item.id
        for item in all_nodes
        if not set(item.representative_ids) <= set(item.supporting_ids)
    ]
    if bad_representatives:
        raise PipelineError(
            "一级 Domain representative_ids 不属于 supporting_ids",
            code="top_level_representative_mismatch",
            retryable=False,
        )
    bad_children = [
        child.id
        for parent in value.domains
        for child in parent.children
        if child.parent_id != parent.id
        or not set(child.supporting_ids) <= set(parent.supporting_ids)
    ]
    if bad_children:
        raise PipelineError(
            "二级 Domain 的 parent_id 或支持范围无效",
            code="subdomain_parent_support_mismatch",
            retryable=False,
        )
    decision_ids = [item.candidate_id for item in value.candidate_decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise PipelineError(
            "Domain candidate_decisions 重复",
            code="domain_decision_collision",
            retryable=False,
        )
    if candidate_ids is not None and set(decision_ids) != candidate_ids:
        raise PipelineError(
            "Domain candidate_decisions 未覆盖全部归一化候选",
            code="domain_decision_coverage_mismatch",
            retryable=False,
        )
    target_ids = {item.id for item in all_nodes}
    invalid_decisions = [
        item.candidate_id
        for item in value.candidate_decisions
        if (
            item.action == "merged_to_domain" and item.target_id not in target_ids
        )
        or (item.action != "merged_to_domain" and item.target_id is not None)
    ]
    if invalid_decisions:
        raise PipelineError(
            "Domain candidate_decisions 的 target_id 无效",
            code="domain_decision_target_mismatch",
            retryable=False,
        )


def normalized_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cap_fields(
    value: Any,
    *,
    text: dict[str, int] | None = None,
    lists: dict[str, int] | None = None,
) -> Any:
    if not isinstance(value, dict):
        return value
    normalized = dict(value)
    for key, limit in (text or {}).items():
        item = normalized.get(key)
        if isinstance(item, str):
            normalized[key] = item[:limit]
    for key, limit in (lists or {}).items():
        item = normalized.get(key)
        if isinstance(item, list):
            normalized[key] = item[:limit]
    return normalized


def _short_id_order(value: str) -> tuple[int, str]:
    match = re.fullmatch(r"C([0-9]+)", value)
    return (int(match.group(1)), value) if match else (10**9, value)


def _rows_text(rows: list[list[Any]]) -> str:
    return "\n".join(_compact_json(row) for row in rows)


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
