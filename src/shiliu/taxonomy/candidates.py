from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shiliu.domain import PipelineError


CANDIDATE_TABLE_VERSION = "compact-domain-candidates-v1"
LOCAL_TOP_LEVEL_PROMPT_VERSION = "top-level-local-discovery-v1"
TOP_LEVEL_CONSOLIDATION_PROMPT_VERSION = "top-level-consolidation-v1"
CONTENT_TYPE_PROMPT_VERSION = "content-type-discovery-v1"
CANDIDATE_NORMALIZATION_VERSION = "candidate-normalization-v1"


class TopicHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    supporting_ids: list[str] = Field(min_length=1, max_length=5)


class LocalTopLevelDomainCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provisional_id: str = Field(pattern=r"^ld_[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=60)
    definition: str = Field(min_length=1, max_length=140)
    supporting_ids: list[str] = Field(min_length=1, max_length=5)
    evidence_codes: list[str] = Field(default_factory=list, max_length=3)


class LocalTopLevelDiscoveryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domains: list[LocalTopLevelDomainCandidate] = Field(default_factory=list, max_length=8)
    topic_hints: list[TopicHint] = Field(default_factory=list, max_length=5)
    ambiguous_ids: list[str] = Field(default_factory=list, max_length=32)


class ContentTypeCandidateV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provisional_id: str = Field(pattern=r"^lct_[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=60)
    definition: str = Field(min_length=1, max_length=140)
    supporting_ids: list[str] = Field(min_length=1, max_length=5)


class ContentTypeDiscoveryOutputV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_types: list[ContentTypeCandidateV1] = Field(default_factory=list, max_length=8)
    ambiguous_ids: list[str] = Field(default_factory=list, max_length=32)


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


class TopLevelDomainNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^d_[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1, max_length=240)
    includes: list[str] = Field(min_length=1, max_length=5)
    excludes: list[str] = Field(min_length=1, max_length=5)
    supporting_ids: list[str] = Field(min_length=1, max_length=32)
    representative_ids: list[str] = Field(min_length=1, max_length=3)


class TopLevelDomainDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domains: list[TopLevelDomainNode] = Field(min_length=1, max_length=12)
    consolidation_notes: list[str] = Field(default_factory=list, max_length=5)


LOCAL_TOP_LEVEL_SCHEMA_HINT = (
    '{"domains":[{"provisional_id":"ld_x","name":"短名称",'
    '"definition":"一句话定义","supporting_ids":["C001"],'
    '"evidence_codes":["durable_domain"]}],'
    '"topic_hints":[{"name":"短名称","supporting_ids":["C002"]}],'
    '"ambiguous_ids":["C003"]}'
)
CONTENT_TYPE_SCHEMA_HINT = (
    '{"content_types":[{"provisional_id":"lct_x","name":"短名称",'
    '"definition":"一句话定义","supporting_ids":["C001"]}],'
    '"ambiguous_ids":["C002"]}'
)
TOP_LEVEL_CONSOLIDATION_SCHEMA_HINT = (
    '{"domains":[{"id":"d_01","name":"","definition":"",'
    '"includes":[""],"excludes":[""],"supporting_ids":["C001"],'
    '"representative_ids":["C001"]}],"consolidation_notes":[""]}'
)


def build_top_level_local_prompt(rows: list[list[Any]]) -> str:
    return f"""你是局部一级知识领域候选发现器，不生成最终 Taxonomy。
只发现长期稳定、适合浏览的一级 Domain。不得输出 Content Type、二级领域、Entity 或完整 Topic。
项目、工具、模型、论文、人物、公司和短期术语不得成为 Domain。
每批最多 8 个 Domain；每个候选只写短名称、一句话定义、最多 5 个 supporting IDs 和最多 3 个短证据代码。
如必须保留阶段性信号，只能输出最多 5 个 topic_hints，且只有短名称和 supporting IDs。
证据不足内容放入 ambiguous_ids。所有 ID 必须来自本批。只输出 JSON。

精简输出结构：{LOCAL_TOP_LEVEL_SCHEMA_HINT}
输入行协议：A/B=[id,等级,标题,一句话结论,最多3条观点,最多5个已有实体]；C=[id,C,标题,最多300字简介]。
本批卡片：
{_rows_text(rows)}"""


def build_content_type_prompt(rows: list[list[Any]]) -> str:
    return f"""你是独立 Content Type 候选发现器。
Content Type 只回答内容采用什么表达形式或使用形式，不回答知识领域。
不得输出 Domain、Topic 或 Entity。最多输出 8 个候选，每个候选只保留短名称、一句话定义和最多 5 个 supporting IDs。
证据不足内容放入 ambiguous_ids。所有 ID 必须来自本批。只输出 JSON。

精简输出结构：{CONTENT_TYPE_SCHEMA_HINT}
本批卡片：
{_rows_text(rows)}"""


def build_top_level_consolidation_prompt(table: CompactCandidateTable) -> str:
    payload = {
        "version": table.version,
        "domains": [item.model_dump(mode="json") for item in table.domains],
    }
    return f"""你是全局一级 Domain 归并器。
输入只有确定性归一化后的 Compact Candidate Table，不包含卡片、原始局部响应、Content Type、Entity、Topic 或二级领域。
合并语义相同但名称不同的候选，统一名称，生成短定义和必要的 includes/excludes。
输出通常 5 至 10 个一级 Domain，硬上限 12 个；不得生成 children、二级结构或其他对象。
supporting_ids 只能来自输入；representative_ids 必须属于 supporting_ids 且最多 3 个。只输出 JSON。

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
    if not used <= allowed_ids:
        raise PipelineError(
            "Content Type 候选引用了本批之外的短 ID",
            code="content_type_support_mismatch",
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
    value: TopLevelDomainDraft, *, allowed_ids: set[str]
) -> None:
    ids = [item.id for item in value.domains]
    names = [normalized_name(item.name) for item in value.domains]
    if len(ids) != len(set(ids)):
        raise PipelineError(
            "一级 Domain ID 不唯一", code="top_level_domain_id_collision", retryable=False
        )
    if len(names) != len(set(names)):
        raise PipelineError(
            "一级 Domain 名称重复", code="top_level_domain_name_collision", retryable=False
        )
    used = {content_id for item in value.domains for content_id in item.supporting_ids}
    if not used <= allowed_ids:
        raise PipelineError(
            "一级 Domain Draft 引用了未知短 ID",
            code="top_level_domain_support_mismatch",
            retryable=False,
        )
    bad_representatives = [
        item.id
        for item in value.domains
        if not set(item.representative_ids) <= set(item.supporting_ids)
    ]
    if bad_representatives:
        raise PipelineError(
            "一级 Domain representative_ids 不属于 supporting_ids",
            code="top_level_representative_mismatch",
            retryable=False,
        )


def normalized_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _short_id_order(value: str) -> tuple[int, str]:
    match = re.fullmatch(r"C([0-9]+)", value)
    return (int(match.group(1)), value) if match else (10**9, value)


def _rows_text(rows: list[list[Any]]) -> str:
    return "\n".join(_compact_json(row) for row in rows)


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
