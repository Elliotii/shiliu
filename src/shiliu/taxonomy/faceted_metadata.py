from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.domain import PipelineError
from shiliu.llm import OpenAICompatibleProvider, parse_json_content
from shiliu.taxonomy.candidates import CompactContentTypeTable, TopLevelDomainDraft
from shiliu.taxonomy.discovery import build_compact_corpus
from shiliu.taxonomy.model_calls import AuditedJsonCaller
from shiliu.taxonomy.repository import TaxonomyRepository
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from shiliu.taxonomy.semantic_purity import (
    OutputBudgetPreflight,
    build_budget_preflight,
    require_safe_budget,
)


FACETED_ENGINE_VERSION = "faceted-metadata-spike-v1"
FACETED_PROTOCOL_VERSION = "checkpoint310-faceted-metadata-v1"
DECOMPOSITION_SCHEMA_VERSION = "faceted-candidate-decomposition-v1"
DECOMPOSITION_PROMPT_VERSION = "faceted-candidate-decomposition-v1"
VOCABULARY_SCHEMA_VERSION = "faceted-controlled-vocabulary-v1"
VOCABULARY_PROMPT_VERSION = "faceted-controlled-vocabulary-v1"
ASSIGNMENT_SCHEMA_VERSION = "faceted-assignment-v1"
ASSIGNMENT_PROMPT_VERSION = "faceted-assignment-v1"
FILTER_PROTOCOL_VERSION = "faceted-filter-or-and-v1"
QUALITY_GATE_VERSION = "checkpoint310-faceted-quality-gate-v1"
MAX_SOURCE_CANDIDATES = 31
MAX_COMPONENTS_PER_MULTI_FACET = MAX_SOURCE_CANDIDATES * 2

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class FacetComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    canonical_name: str = Field(min_length=1, max_length=60)
    definition: str = Field(min_length=1, max_length=180)
    evidence: list[str] = Field(min_length=1, max_length=3)


class CandidateDecomposition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_candidate_id: str = Field(pattern=r"^nct_[0-9]{3}$")
    source_name: str = Field(min_length=1, max_length=60)
    presentation_form_component: FacetComponent | None
    focus_object_type_components: list[FacetComponent] = Field(max_length=2)
    use_context_components: list[FacetComponent] = Field(max_length=2)
    domain_component: FacetComponent | None
    entity_components: list[str] = Field(max_length=5)
    is_compound: bool
    decomposition_reason: str = Field(min_length=1, max_length=360)
    supporting_evidence: list[str] = Field(min_length=1, max_length=5)
    confidence: Literal["high", "medium", "low"]
    unresolved_parts: list[str] = Field(max_length=5)

    @model_validator(mode="after")
    def validate_distinct_components(self):
        values = [
            item.canonical_name
            for item in self.focus_object_type_components
            + self.use_context_components
        ]
        if len(values) != len(set(values)):
            raise ValueError("decomposed component names must be unique")
        if len(self.entity_components) != len(set(self.entity_components)):
            raise ValueError("entity components must be unique")
        return self


class CandidateDecompositionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[DECOMPOSITION_SCHEMA_VERSION] = DECOMPOSITION_SCHEMA_VERSION
    decisions: list[CandidateDecomposition] = Field(min_length=1, max_length=48)
    discarded_parts: list[str] = Field(max_length=20)


class FacetVocabularyNode(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    temporary_id: str = Field(pattern=r"^(pf|fo|uc)_[0-9]{2}$")
    facet: Literal["presentation_form", "focus_object_type", "use_context"]
    canonical_name: str = Field(min_length=1, max_length=60)
    definition: str = Field(min_length=1, max_length=180)
    includes: list[str] = Field(min_length=1, max_length=5)
    excludes: list[str] = Field(min_length=1, max_length=5)
    aliases: list[str] = Field(max_length=5)
    supporting_candidate_ids: list[str] = Field(min_length=1, max_length=31)
    supporting_content_ids: list[str] = Field(min_length=1, max_length=48)
    status: Literal["stable", "draft", "rejected"]
    rejection_reason: str | None = Field(default=None, min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_prefix_and_rejection(self):
        expected = {
            "presentation_form": "pf_",
            "focus_object_type": "fo_",
            "use_context": "uc_",
        }[self.facet]
        if not self.temporary_id.startswith(expected):
            raise ValueError("vocabulary ID prefix does not match facet")
        if (self.status == "rejected") != (self.rejection_reason is not None):
            raise ValueError("only rejected nodes require rejection_reason")
        return self


class FacetedVocabularyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[VOCABULARY_SCHEMA_VERSION] = VOCABULARY_SCHEMA_VERSION
    # These are structural capacities derived from the frozen 31 source
    # candidates, not product Top-K targets. Every candidate can contribute at
    # most one Form and at most two Object/Context components.
    presentation_forms: list[FacetVocabularyNode] = Field(
        min_length=1, max_length=MAX_SOURCE_CANDIDATES
    )
    focus_object_types: list[FacetVocabularyNode] = Field(
        min_length=1, max_length=MAX_COMPONENTS_PER_MULTI_FACET
    )
    use_contexts: list[FacetVocabularyNode] = Field(
        min_length=1, max_length=MAX_COMPONENTS_PER_MULTI_FACET
    )

    @model_validator(mode="after")
    def validate_unique_vocabularies(self):
        nodes = self.presentation_forms + self.focus_object_types + self.use_contexts
        ids = [item.temporary_id for item in nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("vocabulary node IDs must be globally unique")
        for values in (
            self.presentation_forms,
            self.focus_object_types,
            self.use_contexts,
        ):
            names = [item.canonical_name for item in values]
            if len(names) != len(set(names)):
                raise ValueError("canonical names must be unique within one facet")
        return self


class DomainFacetAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    primary_path: list[str] = Field(min_length=1, max_length=2)
    secondary_paths: list[list[str]] = Field(max_length=2)
    confidence: Literal["high", "medium", "low"]


class PresentationFormAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["assigned", "unknown", "ambiguous"]
    primary: str | None = Field(default=None, pattern=r"^pf_[0-9]{2}$")
    secondary: str | None = Field(default=None, pattern=r"^pf_[0-9]{2}$")
    alternatives: list[str] = Field(max_length=2)
    confidence: Literal["high", "medium", "low"]

    @model_validator(mode="after")
    def validate_status(self):
        if self.status == "assigned" and self.primary is None:
            raise ValueError("assigned Presentation Form requires primary")
        if self.status != "assigned" and (self.primary or self.secondary):
            raise ValueError("unknown/ambiguous Presentation Form cannot be assigned")
        if self.secondary is not None and self.secondary == self.primary:
            raise ValueError("secondary Presentation Form must differ from primary")
        if self.status == "ambiguous" and not self.alternatives:
            raise ValueError("ambiguous Presentation Form requires alternatives")
        if self.status != "ambiguous" and self.alternatives:
            raise ValueError("alternatives are only valid for ambiguous form")
        return self


class FacetLabelAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    node_id: str = Field(pattern=r"^(fo|uc)_[0-9]{2}$")
    confidence: Literal["high", "medium", "low"]
    evidence: str = Field(min_length=1, max_length=500)


class AssignmentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    domain: list[str] = Field(min_length=1, max_length=3)
    presentation_form: list[str] = Field(max_length=3)
    focus_object_types: list[str] = Field(max_length=3)
    use_contexts: list[str] = Field(max_length=3)


class FacetedAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    content_id: str = Field(pattern=r"^C[0-9]{3}$")
    domain: DomainFacetAssignment
    presentation_form: PresentationFormAssignment
    focus_object_types: list[FacetLabelAssignment] = Field(max_length=2)
    use_contexts: list[FacetLabelAssignment] = Field(max_length=2)
    entities: list[str] = Field(max_length=5)
    ambiguities: list[str] = Field(max_length=5)
    evidence: AssignmentEvidence

    @model_validator(mode="after")
    def validate_label_budgets(self):
        object_ids = [item.node_id for item in self.focus_object_types]
        context_ids = [item.node_id for item in self.use_contexts]
        if len(object_ids) != len(set(object_ids)):
            raise ValueError("duplicate Focus Object Type")
        if len(context_ids) != len(set(context_ids)):
            raise ValueError("duplicate Use Context")
        if any(not item.node_id.startswith("fo_") for item in self.focus_object_types):
            raise ValueError("Focus Object Type uses wrong vocabulary")
        if any(not item.node_id.startswith("uc_") for item in self.use_contexts):
            raise ValueError("Use Context uses wrong vocabulary")
        if self.presentation_form.status == "assigned" and not self.evidence.presentation_form:
            raise ValueError("assigned Presentation Form requires evidence")
        if self.focus_object_types and not self.evidence.focus_object_types:
            raise ValueError("assigned Focus Object Type requires evidence")
        if self.use_contexts and not self.evidence.use_contexts:
            raise ValueError("assigned Use Context requires evidence")
        return self


class FacetNovelty(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    content_id: str = Field(pattern=r"^C[0-9]{3}$")
    facet: Literal["presentation_form", "focus_object_type", "use_context"]
    description: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=180)


class FacetedAssignmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[ASSIGNMENT_SCHEMA_VERSION] = ASSIGNMENT_SCHEMA_VERSION
    assignments: list[FacetedAssignment] = Field(min_length=1, max_length=16)
    facet_novelty_pool: list[FacetNovelty] = Field(max_length=16)


class FacetedQualityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[QUALITY_GATE_VERSION] = QUALITY_GATE_VERSION
    passed: bool
    blocking_issues: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    metrics: dict[str, Any]


DECOMPOSITION_SCHEMA_HINT = (
    '{"version":"faceted-candidate-decomposition-v1","decisions":['
    '{"source_candidate_id":"nct_001","source_name":"",'
    '"presentation_form_component":null|{"canonical_name":"","definition":"",'
    '"evidence":[""]},"focus_object_type_components":[],"use_context_components":[],'
    '"domain_component":null,"entity_components":[],"is_compound":true,'
    '"decomposition_reason":"","supporting_evidence":[""],'
    '"confidence":"high|medium|low","unresolved_parts":[]}],"discarded_parts":[]}'
)

VOCABULARY_SCHEMA_HINT = (
    '{"version":"faceted-controlled-vocabulary-v1",'
    '"presentation_forms":[NODE],"focus_object_types":[NODE],"use_contexts":[NODE]};'
    ' NODE={"temporary_id":"pf_01|fo_01|uc_01",'
    '"facet":"presentation_form|focus_object_type|use_context",'
    '"canonical_name":"","definition":"","includes":[""],"excludes":[""],'
    '"aliases":[],"supporting_candidate_ids":["nct_001"],'
    '"supporting_content_ids":["C001"],"status":"stable|draft|rejected",'
    '"rejection_reason":null|""}'
)

ASSIGNMENT_SCHEMA_HINT = (
    '{"version":"faceted-assignment-v1","assignments":[{"content_id":"C001",'
    '"domain":{"primary_path":["d_01"],"secondary_paths":[],'
    '"confidence":"high|medium|low"},"presentation_form":{'
    '"status":"assigned|unknown|ambiguous","primary":"pf_01|null",'
    '"secondary":null,"alternatives":[],"confidence":"high|medium|low"},'
    '"focus_object_types":[{"node_id":"fo_01","confidence":"high|medium|low",'
    '"evidence":""}],"use_contexts":[],"entities":[],"ambiguities":[],'
    '"evidence":{"domain":[""],"presentation_form":[""],'
    '"focus_object_types":[],"use_contexts":[]}}],"facet_novelty_pool":[]}'
)


def build_decomposition_prompt(
    *, candidates: list[dict[str, Any]], candidate_decisions: list[dict[str, Any]],
    compact_rows_by_id: dict[str, list[Any]],
) -> str:
    decision_by_id = {item["candidate_id"]: item for item in candidate_decisions}
    payload = []
    for item in candidates:
        representative_ids = list(item.get("representative_ids") or [])[:3]
        payload.append(
            {
                "candidate": item,
                "historical_decision_for_provenance_only": decision_by_id.get(
                    item["candidate_id"]
                ),
                "representative_compact_form_views": [
                    compact_rows_by_id[value]
                    for value in representative_ids
                    if value in compact_rows_by_id
                ],
            }
        )
    return f"""你执行 Faceted Candidate Decomposition。旧候选可能同时包含表达形式、对象类别、使用情境、知识领域或具体实体；不要再把整个候选强制判成一个 Content Type。

四个分面边界：Domain=主要讲什么知识领域；Presentation Form=作者如何组织、表达或呈现；Focus Object Type=围绕哪类对象，不是具体名称；Use Context=用户在什么任务或目标下使用。具体项目、模型、工具、论文、人物名称只能进入 entity_components。

逐一覆盖全部输入 candidate_id。能拆出多个成分就分别保留；无效部分可舍弃但要在 unresolved_parts 或 discarded_parts 记录。不得按关键词机械切分，不得把旧名字直接复制为 Presentation Form，不得通过删去领域词把主题伪装成形式，不得为了覆盖制造成分。历史 Candidate Decision 只提供血缘，不是正确性证据。只输出 JSON。

Schema：{DECOMPOSITION_SCHEMA_HINT}
输入：{_compact_json(payload)}"""


def build_vocabulary_prompt(decomposition: CandidateDecompositionOutput) -> str:
    payload = decomposition.model_dump(mode="json")
    return f"""你把候选拆解结果归并成三个彼此独立的全局扁平受控词表：Presentation Form、Focus Object Type、Use Context。不建立树，不修改 Domain。

Presentation Form 必须描述表达、组织或呈现方式，并能跨 Domain 或对象类别复用。Focus Object Type 必须是对象类别而非具体名称，也不能与 Domain 同义。Use Context 必须是用户任务或目标，证据不足可不建节点。不得设固定 Top-K，不得为了数量制造标签。

每个节点必须保留来源 candidate/content ID；支持不足但语义合理用 draft；不合格成分也应形成 rejected 节点并写 rejection_reason，不能静默消失。单条内容来源不得无审计提升为 stable。只输出 JSON。

Schema：{VOCABULARY_SCHEMA_HINT}
拆解结果：{_compact_json(payload)}"""


def build_assignment_prompt(
    *, rows: list[list[Any]], domain_draft: TopLevelDomainDraft,
    vocabulary: FacetedVocabularyOutput,
) -> str:
    domains = []
    for parent in domain_draft.domains:
        domains.append(
            {"id": parent.id, "name": parent.name, "definition": parent.definition,
             "parent_id": None}
        )
        domains.extend(
            {"id": child.id, "name": child.name, "definition": child.definition,
             "parent_id": parent.id}
            for child in parent.children
        )
    vocabulary_payload = {
        "presentation_forms": [
            item.model_dump(mode="json") for item in vocabulary.presentation_forms
            if item.status != "rejected"
        ],
        "focus_object_types": [
            item.model_dump(mode="json") for item in vocabulary.focus_object_types
            if item.status != "rejected"
        ],
        "use_contexts": [
            item.model_dump(mode="json") for item in vocabulary.use_contexts
            if item.status != "rejected"
        ],
    }
    payload = {"domains": domains, "vocabularies": vocabulary_payload, "rows": rows}
    return f"""你执行小样本 Faceted Assignment。只能使用输入中已有 Domain ID 和三个受控词表 ID，不得创建稳定标签。

Domain 必须给 1 个 primary path（父级到可选子级，最多两级），可给最多 2 条 secondary path。Presentation Form 正常应给 1 个 primary、最多 1 个 secondary；证据不足可用 unknown，两个候选无法判断可用 ambiguous。Focus Object Type 和 Use Context 各 0～2 个；没有证据必须为空。具体名称只进入 entities。新概念写入 facet_novelty_pool，不得伪装成已有词表。

每项必须引用输入文本中的短证据。不要从 Domain 自动推导 Use Context。只输出 JSON，不静默截断。

Schema：{ASSIGNMENT_SCHEMA_HINT}
输入：{_compact_json(payload)}"""


def validate_decomposition(
    output: CandidateDecompositionOutput, *, candidates: CompactContentTypeTable,
) -> None:
    expected = {item.candidate_id: item.name for item in candidates.content_types}
    ids = [item.source_candidate_id for item in output.decisions]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise PipelineError(
            "分面拆解没有完整且唯一覆盖 31 个来源候选",
            code="facet_decomposition_coverage_mismatch", retryable=False,
        )
    mismatched = [
        item.source_candidate_id for item in output.decisions
        if item.source_name != expected[item.source_candidate_id]
    ]
    if mismatched:
        raise PipelineError(
            "分面拆解的来源名称与冻结候选不一致",
            code="facet_decomposition_source_changed", retryable=False,
        )


def validate_vocabulary(
    output: FacetedVocabularyOutput, *, decomposition: CandidateDecompositionOutput,
    valid_content_ids: set[str],
) -> None:
    valid_candidates = {item.source_candidate_id for item in decomposition.decisions}
    for node in output.presentation_forms + output.focus_object_types + output.use_contexts:
        if not set(node.supporting_candidate_ids) <= valid_candidates:
            raise PipelineError(
                "词表引用未知来源候选", code="facet_vocabulary_unknown_candidate",
                retryable=False,
            )
        if not set(node.supporting_content_ids) <= valid_content_ids:
            raise PipelineError(
                "词表引用未知内容", code="facet_vocabulary_unknown_content",
                retryable=False,
            )


def apply_vocabulary_support_policy(
    output: FacetedVocabularyOutput,
) -> tuple[FacetedVocabularyOutput, list[dict[str, Any]]]:
    """Downgrade unsupported stability with an explicit, reproducible audit."""
    payload = output.model_dump(mode="json")
    events: list[dict[str, Any]] = []
    for field in ("presentation_forms", "focus_object_types", "use_contexts"):
        for index, node in enumerate(payload[field]):
            support_count = len(set(node["supporting_content_ids"]))
            if node["status"] == "stable" and support_count < 2:
                events.append(
                    {
                        "field_path": f"{field}[{index}].status",
                        "node_id": node["temporary_id"],
                        "original_value": "stable",
                        "normalized_value": "draft",
                        "reason": "stable requires at least two supporting content IDs",
                        "support_count": support_count,
                    }
                )
                node["status"] = "draft"
    return FacetedVocabularyOutput.model_validate(payload), events


def validate_assignments(
    output: FacetedAssignmentOutput, *, expected_ids: set[str],
    domain_draft: TopLevelDomainDraft, vocabulary: FacetedVocabularyOutput,
) -> None:
    ids = [item.content_id for item in output.assignments]
    if len(ids) != len(set(ids)) or set(ids) != expected_ids:
        raise PipelineError(
            "分面赋值没有完整且唯一覆盖批次内容",
            code="faceted_assignment_coverage_mismatch", retryable=False,
        )
    parent_by_id: dict[str, str | None] = {}
    for parent in domain_draft.domains:
        parent_by_id[parent.id] = None
        for child in parent.children:
            parent_by_id[child.id] = parent.id
    allowed = {
        "pf": {item.temporary_id for item in vocabulary.presentation_forms if item.status != "rejected"},
        "fo": {item.temporary_id for item in vocabulary.focus_object_types if item.status != "rejected"},
        "uc": {item.temporary_id for item in vocabulary.use_contexts if item.status != "rejected"},
    }
    for item in output.assignments:
        _validate_domain_path(item.domain.primary_path, parent_by_id)
        for path in item.domain.secondary_paths:
            _validate_domain_path(path, parent_by_id)
        form_ids = {
            value for value in [item.presentation_form.primary,
                                item.presentation_form.secondary,
                                *item.presentation_form.alternatives] if value
        }
        if not form_ids <= allowed["pf"]:
            raise PipelineError("赋值引用未知 Form", code="unknown_form_assignment", retryable=False)
        if not {value.node_id for value in item.focus_object_types} <= allowed["fo"]:
            raise PipelineError("赋值引用未知 Object Type", code="unknown_object_assignment", retryable=False)
        if not {value.node_id for value in item.use_contexts} <= allowed["uc"]:
            raise PipelineError("赋值引用未知 Use Context", code="unknown_context_assignment", retryable=False)


def _validate_domain_path(path: list[str], parent_by_id: dict[str, str | None]) -> None:
    if any(item not in parent_by_id for item in path):
        raise PipelineError("赋值引用未知 Domain", code="unknown_domain_assignment", retryable=False)
    if len(path) == 2 and parent_by_id[path[1]] != path[0]:
        raise PipelineError("Domain path 父子关系无效", code="invalid_domain_path", retryable=False)
    if len(path) == 1 and parent_by_id[path[0]] is not None:
        raise PipelineError("子 Domain 不能缺少父路径", code="invalid_domain_path", retryable=False)


def simulate_filters(assignments: list[FacetedAssignment]) -> dict[str, Any]:
    records: dict[str, dict[str, set[str]]] = {}
    for item in assignments:
        records[item.content_id] = {
            "domain": set(item.domain.primary_path + [x for path in item.domain.secondary_paths for x in path]),
            "presentation_form": {x for x in [item.presentation_form.primary, item.presentation_form.secondary] if x},
            "focus_object_type": {x.node_id for x in item.focus_object_types},
            "use_context": {x.node_id for x in item.use_contexts},
        }
    support: dict[str, dict[str, int]] = {}
    for facet in ("domain", "presentation_form", "focus_object_type", "use_context"):
        counts = Counter(value for item in records.values() for value in item[facet])
        support[facet] = dict(sorted(counts.items()))

    def query(filters: dict[str, set[str]]) -> list[str]:
        return sorted(
            content_id for content_id, facets in records.items()
            if all(not selected or facets[facet] & selected for facet, selected in filters.items())
        )

    pairs = [("domain", "presentation_form"), ("domain", "focus_object_type"),
             ("presentation_form", "use_context")]
    pair_results: list[dict[str, Any]] = []
    for left, right in pairs:
        for left_id in support[left]:
            for right_id in support[right]:
                result = query({left: {left_id}, right: {right_id}})
                pair_results.append({"facets": [left, right], "labels": [left_id, right_id], "count": len(result), "content_ids": result})
    three_results = _sample_combinations(query, support, ["domain", "presentation_form", "focus_object_type"], 20)
    four_results = _sample_combinations(query, support, ["domain", "presentation_form", "focus_object_type", "use_context"], 20)
    counts = [item["count"] for item in pair_results]
    cooccurrence = _cross_facet_cooccurrence(records, support)
    return {
        "version": FILTER_PROTOCOL_VERSION,
        "semantics": {"within_facet": "OR", "across_facets": "AND", "unselected_facet": "ignored"},
        "assignment_count": len(assignments),
        "label_support": support,
        "single_label_result_distribution": _distribution([v for values in support.values() for v in values.values()]),
        "two_facet_combination_distribution": _distribution(counts),
        "two_facet_combinations": pair_results,
        "three_facet_examples": three_results,
        "four_facet_examples": four_results,
        "empty_pair_ratio": round(sum(value == 0 for value in counts) / len(counts), 4) if counts else 0,
        "singleton_pair_ratio": round(sum(value == 1 for value in counts) / len(counts), 4) if counts else 0,
        "broad_labels": [f"{facet}:{label}" for facet, values in support.items() for label, count in values.items() if count >= max(2, len(assignments) // 2)],
        "narrow_labels": [f"{facet}:{label}" for facet, values in support.items() for label, count in values.items() if count <= 1],
        "cross_facet_cooccurrence": cooccurrence,
    }


def _sample_combinations(query, support: dict[str, dict[str, int]], facets: list[str], limit: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    choices: list[list[str]] = [list(support[facet]) for facet in facets]
    if any(not values for values in choices):
        return results
    def visit(index: int, selected: list[str]) -> None:
        if len(results) >= limit:
            return
        if index == len(facets):
            found = query({facet: {label} for facet, label in zip(facets, selected)})
            results.append({"facets": facets, "labels": list(selected), "count": len(found), "content_ids": found})
            return
        for value in choices[index]:
            visit(index + 1, selected + [value])
            if len(results) >= limit:
                break
    visit(0, [])
    return results


def _cross_facet_cooccurrence(records: dict[str, dict[str, set[str]]], support: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    facets = list(support)
    output = []
    for index, left in enumerate(facets):
        for right in facets[index + 1:]:
            for left_id, left_count in support[left].items():
                for right_id, right_count in support[right].items():
                    both = sum(left_id in value[left] and right_id in value[right] for value in records.values())
                    if both and both == min(left_count, right_count):
                        output.append({"left": f"{left}:{left_id}", "right": f"{right}:{right_id}", "joint_count": both, "smaller_support_covered": True})
    return output


def _distribution(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "min": 0, "median": 0, "max": 0, "zero": 0, "one": 0}
    ordered = sorted(values)
    return {"count": len(values), "min": ordered[0], "median": ordered[len(ordered)//2], "max": ordered[-1], "zero": sum(v == 0 for v in values), "one": sum(v == 1 for v in values)}


def build_quality_gate(
    *, table: CompactContentTypeTable, decomposition: CandidateDecompositionOutput,
    vocabulary: FacetedVocabularyOutput, assignments: list[FacetedAssignment],
    filter_result: dict[str, Any], source_domain_hash: str, current_domain_hash: str,
    runtime_inputs: list[str], domain_draft: TopLevelDomainDraft,
) -> FacetedQualityResult:
    blocking: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    expected_ids = {item.candidate_id for item in table.content_types}
    decided_ids = {item.source_candidate_id for item in decomposition.decisions}
    if expected_ids != decided_ids:
        blocking.append({"code": "candidate_decomposition_incomplete", "details": sorted(expected_ids ^ decided_ids)})
    copied_compound = [
        item.source_candidate_id for item in decomposition.decisions
        if item.is_compound and item.presentation_form_component is not None
        and item.presentation_form_component.canonical_name == item.source_name
    ]
    if copied_compound:
        blocking.append({"code": "compound_candidate_copied_to_form", "details": copied_compound})
    components = decomposition.decisions
    entity_names = {_norm(name) for item in components for name in item.entity_components}
    domain_names = {_norm(item.domain_component.canonical_name) for item in components if item.domain_component}
    object_names = {_norm(value.canonical_name) for item in components for value in item.focus_object_type_components}
    context_names = {_norm(value.canonical_name) for item in components for value in item.use_context_components}
    frozen_domain_names = {
        _norm(node.name) for node in domain_draft.domains
    } | {
        _norm(child.name) for node in domain_draft.domains for child in node.children
    }
    form_leaks = [node.temporary_id for node in vocabulary.presentation_forms if node.status != "rejected" and _norm(node.canonical_name) in domain_names | object_names | context_names | frozen_domain_names]
    if form_leaks:
        blocking.append({"code": "presentation_form_semantic_leakage", "details": form_leaks})
    entity_leaks = [node.temporary_id for node in vocabulary.focus_object_types if node.status != "rejected" and ({_norm(node.canonical_name), *(_norm(alias) for alias in node.aliases)} & entity_names)]
    if entity_leaks:
        blocking.append({"code": "entity_in_focus_object_type", "details": entity_leaks})
    object_domain_duplicates = [
        node.temporary_id for node in vocabulary.focus_object_types
        if node.status != "rejected" and _norm(node.canonical_name) in frozen_domain_names
    ]
    if object_domain_duplicates:
        blocking.append({"code": "focus_object_duplicates_domain", "details": object_domain_duplicates})
    stable_singletons = [node.temporary_id for node in vocabulary.presentation_forms + vocabulary.focus_object_types + vocabulary.use_contexts if node.status == "stable" and len(set(node.supporting_content_ids)) < 2]
    if stable_singletons:
        blocking.append({"code": "unsupported_stable_vocabulary", "details": stable_singletons})
    if assignments and all(item.use_contexts for item in assignments):
        blocking.append({"code": "use_context_forced_full_coverage", "details": []})
    if source_domain_hash != current_domain_hash:
        blocking.append({"code": "frozen_domain_draft_modified", "details": []})
    if any("silver" in value.lower() for value in runtime_inputs):
        blocking.append({"code": "silver_reference_runtime_leak", "details": runtime_inputs})
    status_counts = {
        facet: dict(Counter(item.status for item in values))
        for facet, values in {
            "presentation_form": vocabulary.presentation_forms,
            "focus_object_type": vocabulary.focus_object_types,
            "use_context": vocabulary.use_contexts,
        }.items()
    }
    low_support_forms = [item.temporary_id for item in vocabulary.presentation_forms if item.status != "rejected" and len(set(item.supporting_content_ids)) < 3]
    if low_support_forms:
        warnings.append({"code": "low_support_presentation_form", "details": low_support_forms})
    context_empty_rate = round(sum(not item.use_contexts for item in assignments) / len(assignments), 4) if assignments else 0
    if context_empty_rate >= 0.75:
        warnings.append({"code": "high_use_context_empty_rate", "details": [context_empty_rate]})
    if filter_result.get("empty_pair_ratio", 0) >= 0.5:
        warnings.append({"code": "many_empty_filter_combinations", "details": [filter_result["empty_pair_ratio"]]})
    if len(vocabulary.presentation_forms) > 16 or len(vocabulary.focus_object_types) > 16 or len(vocabulary.use_contexts) > 16:
        warnings.append({"code": "facet_vocabulary_inflation", "details": status_counts})
    form_support: dict[str, set[str]] = defaultdict(set)
    form_domain_support: dict[str, set[str]] = defaultdict(set)
    form_object_support: dict[str, set[str]] = defaultdict(set)
    for assignment in assignments:
        form_ids = {
            value for value in (
                assignment.presentation_form.primary,
                assignment.presentation_form.secondary,
            ) if value
        }
        for form_id in form_ids:
            form_support[form_id].add(assignment.content_id)
            form_domain_support[form_id].add(assignment.domain.primary_path[0])
            form_object_support[form_id].update(
                item.node_id for item in assignment.focus_object_types
            )
    stable_forms_without_cross_support = [
        node.temporary_id for node in vocabulary.presentation_forms
        if node.status == "stable"
        and len(form_domain_support[node.temporary_id]) < 2
        and len(form_object_support[node.temporary_id]) < 2
    ]
    if stable_forms_without_cross_support:
        warnings.append({"code": "stable_form_lacks_cross_facet_support", "details": stable_forms_without_cross_support})
    form_overlap: list[dict[str, Any]] = []
    form_ids = sorted(form_support)
    for index, left in enumerate(form_ids):
        for right in form_ids[index + 1:]:
            union = form_support[left] | form_support[right]
            score = len(form_support[left] & form_support[right]) / len(union) if union else 0
            if score >= 0.6:
                form_overlap.append({"left": left, "right": right, "jaccard": round(score, 3)})
    if form_overlap:
        warnings.append({"code": "overlapping_presentation_forms", "details": form_overlap})
    total_labels = [1 + (1 if a.presentation_form.primary else 0) + (1 if a.presentation_form.secondary else 0) + len(a.focus_object_types) + len(a.use_contexts) for a in assignments]
    return FacetedQualityResult(
        passed=not blocking,
        blocking_issues=blocking,
        warnings=warnings,
        metrics={
            "candidate_decomposition_coverage": len(decided_ids & expected_ids) / len(expected_ids) if expected_ids else 0,
            "compound_candidate_count": sum(item.is_compound for item in decomposition.decisions),
            "unresolved_candidate_count": sum(bool(item.unresolved_parts) for item in decomposition.decisions),
            "vocabulary_status_counts": status_counts,
            "assignment_count": len(assignments),
            "presentation_unknown_or_ambiguous_rate": round(sum(a.presentation_form.status != "assigned" for a in assignments) / len(assignments), 4) if assignments else 0,
            "focus_object_empty_rate": round(sum(not a.focus_object_types for a in assignments) / len(assignments), 4) if assignments else 0,
            "focus_object_average_labels": round(sum(len(a.focus_object_types) for a in assignments) / len(assignments), 3) if assignments else 0,
            "use_context_empty_rate": context_empty_rate,
            "use_context_low_confidence_rate": round(sum(any(x.confidence == "low" for x in a.use_contexts) for a in assignments) / len(assignments), 4) if assignments else 0,
            "use_context_average_labels": round(sum(len(a.use_contexts) for a in assignments) / len(assignments), 3) if assignments else 0,
            "average_total_labels": round(sum(total_labels) / len(total_labels), 3) if total_labels else 0,
            "filter_empty_pair_ratio": filter_result.get("empty_pair_ratio", 0),
            "filter_singleton_pair_ratio": filter_result.get("singleton_pair_ratio", 0),
            "entity_leakage_count": len(entity_leaks),
            "form_leakage_count": len(form_leaks),
            "focus_object_domain_duplicate_count": len(object_domain_duplicates),
            "presentation_form_cross_support": {
                node_id: {
                    "content_count": len(form_support[node_id]),
                    "domain_count": len(form_domain_support[node_id]),
                    "object_type_count": len(form_object_support[node_id]),
                }
                for node_id in sorted(form_support)
            },
            "presentation_form_sibling_overlap": form_overlap,
        },
    )


def build_reviewer_bundle(
    *, protocol: dict[str, Any], decomposition: CandidateDecompositionOutput,
    vocabulary: FacetedVocabularyOutput, assignments: list[FacetedAssignment],
    filter_result: dict[str, Any], quality: FacetedQualityResult,
) -> dict[str, Any]:
    """Expose review evidence without Silver data or historical correctness claims."""
    return {
        "protocol_version": protocol["protocol_version"],
        "source_lineage": {
            "snapshot_hash": protocol["snapshot_hash"],
            "domain_run_id": protocol["domain_run_id"],
            "candidate_run_id": protocol["candidate_run_id"],
            "sample_profile_run_id": protocol["sample_profile_run_id"],
            "source_artifact_hashes": protocol["source_artifact_hashes"],
        },
        "decomposition": decomposition.model_dump(mode="json"),
        "vocabularies": vocabulary.model_dump(mode="json"),
        "assignments": [item.model_dump(mode="json") for item in assignments],
        "filter_simulation": filter_result,
        "automatic_gate": quality.model_dump(mode="json"),
        "excluded": [
            "Silver Reference",
            "historical Candidate Decision as correctness evidence",
            "raw Provider prompt and response",
        ],
    }


class FacetedMetadataService:
    def __init__(self, *, repository: TaxonomyRepository,
                 run_repository: TaxonomyRunRepository,
                 provider_factory: Callable[[str], OpenAICompatibleProvider],
                 output_dir: Path, profile_output_dir: Path) -> None:
        self.repository = repository
        self.run_repository = run_repository
        self.provider_factory = provider_factory
        self.output_dir = output_dir
        self.profile_output_dir = profile_output_dir

    def create_spike(self, *, snapshot_id: int = 2, domain_run_id: int = 12,
                     candidate_run_id: int = 14, sample_profile_run_id: str,
                     recovery_source_run_id: int | None = None) -> int:
        snapshot = self.repository.get_snapshot(snapshot_id)
        if snapshot is None:
            raise LookupError("快照不存在")
        domain_run = self.run_repository.get_run(domain_run_id)
        candidate_run = self.run_repository.get_run(candidate_run_id)
        if not domain_run or domain_run.get("status") != "completed":
            raise PipelineError("Domain 来源 Run 未完成", code="faceted_domain_source_invalid", retryable=False)
        if not candidate_run or candidate_run.get("status") != "completed":
            raise PipelineError("候选来源 Run 未完成", code="faceted_candidate_source_invalid", retryable=False)
        domain_dir = self.output_dir / f"run-{domain_run_id:06d}"
        candidate_dir = self.output_dir / f"run-{candidate_run_id:06d}"
        profile_dir = self.profile_output_dir / sample_profile_run_id
        paths = {
            "domain_draft": domain_dir / "taxonomy-draft.json",
            "candidate_table": candidate_dir / "content-type-normalization" / "compact-content-types.json",
            "candidate_decisions": candidate_dir / "content-types-purified.json",
            "compact_corpus": candidate_dir / "reused-source-artifacts" / "compact-corpus.json",
            "sample_manifest": profile_dir / "manifest.json",
        }
        missing = [name for name, path in paths.items() if not path.is_file()]
        if missing:
            raise PipelineError("Faceted Spike 来源缺少产物：" + ", ".join(missing), code="faceted_source_missing", retryable=False)
        manifest = json.loads(paths["sample_manifest"].read_text(encoding="utf-8"))
        selected_ids = list(manifest.get("selected_ids") or [])
        if manifest.get("status") != "completed" or manifest.get("snapshot_hash") != snapshot["snapshot_hash"] or len(selected_ids) != 48 or len(set(selected_ids)) != 48:
            raise PipelineError("48 条冻结样本 Manifest 不满足要求", code="faceted_sample_manifest_invalid", retryable=False)
        git_commit, clean = _git_state()
        if not clean:
            raise PipelineError("创建 Faceted Spike 前 Git 工作区必须干净", code="faceted_git_dirty", retryable=False)
        providers = {role: _provider_manifest(self.provider_factory(role)) for role in ("taxonomy_content_type_global", "taxonomy_assignment", "taxonomy_repair")}
        recovery: dict[str, Any] | None = None
        if recovery_source_run_id is not None:
            recovery_run = self.run_repository.get_run(recovery_source_run_id)
            recovery_dir = self.output_dir / f"run-{recovery_source_run_id:06d}"
            recovery_paths = {
                "decomposition": recovery_dir / "faceted-candidate-decomposition.json",
                "vocabulary": recovery_dir / "faceted-vocabularies.json",
            }
            if (
                not recovery_run
                or recovery_run.get("run_kind") != "faceted_metadata_spike"
                or not all(path.is_file() for path in recovery_paths.values())
            ):
                raise PipelineError(
                    "窄修复来源 Run 或原始产物无效",
                    code="faceted_recovery_source_invalid",
                    retryable=False,
                )
            recovery_protocol = recovery_run["parameters"].get("protocol_manifest") or {}
            if (
                recovery_protocol.get("snapshot_hash") != snapshot["snapshot_hash"]
                or recovery_protocol.get("domain_run_id") != domain_run_id
                or recovery_protocol.get("candidate_run_id") != candidate_run_id
                or recovery_protocol.get("selected_ids") != selected_ids
            ):
                raise PipelineError(
                    "窄修复来源与当前冻结输入不一致",
                    code="faceted_recovery_lineage_mismatch",
                    retryable=False,
                )
            assignment_raw: dict[str, dict[str, str]] = {}
            for batch_index in range(1, 5):
                call_dir = (
                    recovery_dir
                    / "faceted_assignment"
                    / f"batch-{batch_index:03d}"
                    / "attempt-01"
                )
                candidates = [
                    call_dir / "repair-raw-response.txt",
                    call_dir / "raw-response.txt",
                ]
                raw = next((path for path in candidates if path.is_file()), None)
                if raw is not None:
                    assignment_raw[f"batch-{batch_index:03d}"] = {
                        "relative_path": str(raw.relative_to(recovery_dir)),
                        "hash": _hash_file(raw),
                    }
            recovery = {
                "source_run_id": recovery_source_run_id,
                "reason": "narrow_recovery_without_semantic_replay",
                "artifact_hashes": {
                    name: _hash_file(path) for name, path in recovery_paths.items()
                },
                "assignment_raw": assignment_raw,
                "reused_stages": [
                    "faceted_candidate_decomposition",
                    "faceted_vocabulary_consolidation",
                ],
            }
        protocol = {
            "protocol_version": FACETED_PROTOCOL_VERSION,
            "snapshot_id": snapshot_id,
            "snapshot_hash": snapshot["snapshot_hash"],
            "domain_run_id": domain_run_id,
            "candidate_run_id": candidate_run_id,
            "sample_profile_run_id": sample_profile_run_id,
            "selected_ids": selected_ids,
            "source_artifact_hashes": {name: _hash_file(path) for name, path in paths.items()},
            "versions": {
                "deprecated_content_type": "content_type_v1",
                "presentation_form": "presentation_form_v1",
                "focus_object_type": "focus_object_type_v1",
                "use_context": "use_context_v1",
                "decomposition_schema": DECOMPOSITION_SCHEMA_VERSION,
                "vocabulary_schema": VOCABULARY_SCHEMA_VERSION,
                "assignment_schema": ASSIGNMENT_SCHEMA_VERSION,
                "filter_protocol": FILTER_PROTOCOL_VERSION,
                "quality_gate": QUALITY_GATE_VERSION,
            },
            "providers": providers,
            "git_commit": git_commit,
            "git_worktree_clean": True,
            "runtime_inputs": ["Snapshot #2", "Run #12 Domain Draft", "Run #14 normalized candidates", "compact_form_view_v1", "48-item accepted profile manifest"],
            "forbidden_inputs": ["Silver Reference", "full transcript", "full summary"],
            "recovery": recovery,
        }
        run_id = self.run_repository.create_run(snapshot_id=snapshot_id, run_kind="faceted_metadata_spike", engine="faceted_llm_native", engine_version=FACETED_ENGINE_VERSION, parameters={"snapshot_hash": snapshot["snapshot_hash"], "protocol_manifest": protocol})
        _write_json_once(self.output_dir / f"run-{run_id:06d}" / "run-manifest.json", protocol)
        return run_id

    def status(self, run_id: int) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run is None:
            raise LookupError("Taxonomy Run 不存在")
        return {"run": run, "stages": self.run_repository.list_stages(run_id)}

    def execute(self, run_id: int, *, resume: bool = False) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if not run or run.get("run_kind") != "faceted_metadata_spike" or run.get("engine_version") != FACETED_ENGINE_VERSION:
            raise PipelineError("不是可执行的 Faceted Metadata Spike", code="faceted_run_invalid", retryable=False)
        if run["status"] == "completed":
            return self.status(run_id)
        protocol = run["parameters"]["protocol_manifest"]
        run_dir = self.output_dir / f"run-{run_id:06d}"
        frozen = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
        if frozen != protocol:
            raise PipelineError("Faceted Run Manifest 已改变", code="faceted_manifest_changed", retryable=False)
        commit, clean = _git_state()
        if commit != protocol["git_commit"] or not clean:
            raise PipelineError("Faceted Run 执行代码或工作区与 Manifest 不一致", code="faceted_code_state_changed", retryable=False)
        snapshot = self.repository.get_snapshot(int(run["corpus_snapshot_id"]))
        if not snapshot or snapshot["snapshot_hash"] != protocol["snapshot_hash"]:
            raise PipelineError("Snapshot 已改变", code="faceted_snapshot_changed", retryable=False)
        domain_dir = self.output_dir / f"run-{int(protocol['domain_run_id']):06d}"
        candidate_dir = self.output_dir / f"run-{int(protocol['candidate_run_id']):06d}"
        paths = {
            "domain_draft": domain_dir / "taxonomy-draft.json",
            "candidate_table": candidate_dir / "content-type-normalization" / "compact-content-types.json",
            "candidate_decisions": candidate_dir / "content-types-purified.json",
            "compact_corpus": candidate_dir / "reused-source-artifacts" / "compact-corpus.json",
            "sample_manifest": self.profile_output_dir / str(protocol["sample_profile_run_id"]) / "manifest.json",
        }
        for name, path in paths.items():
            if _hash_file(path) != protocol["source_artifact_hashes"][name]:
                raise PipelineError("冻结来源产物发生变化", code="faceted_source_changed", retryable=False)
        table = CompactContentTypeTable.model_validate_json(paths["candidate_table"].read_text(encoding="utf-8"))
        domain = TopLevelDomainDraft.model_validate_json(paths["domain_draft"].read_text(encoding="utf-8"))
        candidate_decisions = json.loads(paths["candidate_decisions"].read_text(encoding="utf-8"))["candidate_decisions"]
        compact = json.loads(paths["compact_corpus"].read_text(encoding="utf-8"))
        rows_by_id = {str(row[0]): row for row in compact["rows"]}
        selected_ids = list(protocol["selected_ids"])
        if not set(selected_ids) <= set(rows_by_id):
            raise PipelineError("冻结样本不在 Compact Corpus", code="faceted_sample_changed", retryable=False)

        decomposition_prompt = build_decomposition_prompt(candidates=[item.model_dump(mode="json") for item in table.content_types], candidate_decisions=candidate_decisions, compact_rows_by_id=rows_by_id)
        decomposition_budget = _faceted_budget(
            stage_name="faceted_candidate_decomposition",
            complexity_count=len(table.content_types),
            schema_hint_characters=len(DECOMPOSITION_SCHEMA_HINT),
            base_tokens=4096,
            tokens_per_item=192,
            technical_max_tokens=16384,
        )
        _write_json(run_dir / "budget-preflight" / "candidate-decomposition.json", decomposition_budget.model_dump(mode="json"))
        recovery = protocol.get("recovery")
        if recovery:
            recovery_dir = self.output_dir / f"run-{int(recovery['source_run_id']):06d}"
            source_path = recovery_dir / "faceted-candidate-decomposition.json"
            if _hash_file(source_path) != recovery["artifact_hashes"]["decomposition"]:
                raise PipelineError("窄修复拆解产物 Hash 改变", code="faceted_recovery_artifact_changed", retryable=False)
            decomposition = CandidateDecompositionOutput.model_validate_json(
                source_path.read_text(encoding="utf-8")
            )
            validate_decomposition(decomposition, candidates=table)
            target_path = run_dir / "faceted-candidate-decomposition.json"
            _write_json(target_path, decomposition.model_dump(mode="json"))
            self.run_repository.record_reused_stage(
                run_id,
                "faceted_candidate_decomposition",
                "all-31",
                input_hash=_hash_text(decomposition_prompt),
                output_path=str(target_path),
                output_hash=_stable_hash(decomposition.model_dump(mode="json")),
                model=None,
                prompt_version=DECOMPOSITION_PROMPT_VERSION,
                thinking_enabled=False,
                reasoning_effort=None,
            )
        else:
            decomposition = self._model_stage(run_id=run_id, run_dir=run_dir, stage_name="faceted_candidate_decomposition", unit_key="all-31", role="taxonomy_content_type_global", prompt=decomposition_prompt, prompt_version=DECOMPOSITION_PROMPT_VERSION, schema=CandidateDecompositionOutput, schema_hint=DECOMPOSITION_SCHEMA_HINT, max_tokens=decomposition_budget.allocated_max_tokens, input_ids=[item.candidate_id for item in table.content_types], validator=lambda value: validate_decomposition(value, candidates=table))
        _write_json(run_dir / "faceted-candidate-decomposition.json", decomposition.model_dump(mode="json"))

        vocabulary_prompt = build_vocabulary_prompt(decomposition)
        vocabulary_budget = _faceted_budget(
            stage_name="faceted_vocabulary_consolidation",
            complexity_count=len(decomposition.decisions),
            schema_hint_characters=len(VOCABULARY_SCHEMA_HINT),
            base_tokens=4096,
            tokens_per_item=256,
            technical_max_tokens=16384,
        )
        _write_json(run_dir / "budget-preflight" / "vocabulary-consolidation.json", vocabulary_budget.model_dump(mode="json"))
        if recovery:
            recovery_dir = self.output_dir / f"run-{int(recovery['source_run_id']):06d}"
            vocabulary_path = recovery_dir / "faceted-vocabularies.json"
            if _hash_file(vocabulary_path) != recovery["artifact_hashes"]["vocabulary"]:
                raise PipelineError("窄修复词表产物 Hash 改变", code="faceted_recovery_artifact_changed", retryable=False)
            vocabulary = FacetedVocabularyOutput.model_validate_json(
                vocabulary_path.read_text(encoding="utf-8")
            )
            validate_vocabulary(
                vocabulary,
                decomposition=decomposition,
                valid_content_ids=set(rows_by_id),
            )
            target_path = run_dir / "faceted-vocabularies.json"
            _write_json(target_path, vocabulary.model_dump(mode="json"))
            self.run_repository.record_reused_stage(
                run_id,
                "faceted_vocabulary_consolidation",
                "all",
                input_hash=_hash_text(vocabulary_prompt),
                output_path=str(target_path),
                output_hash=_stable_hash(vocabulary.model_dump(mode="json")),
                model=None,
                prompt_version=VOCABULARY_PROMPT_VERSION,
                thinking_enabled=False,
                reasoning_effort=None,
            )
        else:
            vocabulary = self._model_stage(run_id=run_id, run_dir=run_dir, stage_name="faceted_vocabulary_consolidation", unit_key="all", role="taxonomy_content_type_global", prompt=vocabulary_prompt, prompt_version=VOCABULARY_PROMPT_VERSION, schema=FacetedVocabularyOutput, schema_hint=VOCABULARY_SCHEMA_HINT, max_tokens=vocabulary_budget.allocated_max_tokens, input_ids=[item.source_candidate_id for item in decomposition.decisions], validator=lambda value: validate_vocabulary(value, decomposition=decomposition, valid_content_ids=set(rows_by_id)))
        vocabulary, vocabulary_policy_events = apply_vocabulary_support_policy(vocabulary)
        _write_json(
            run_dir / "vocabulary-support-policy-audit.json",
            {
                "policy": "single-support stable nodes become draft",
                "semantic_fields_changed": [],
                "status_event_count": len(vocabulary_policy_events),
                "events": vocabulary_policy_events,
            },
        )
        _write_json(run_dir / "faceted-vocabularies.json", vocabulary.model_dump(mode="json"))

        assignments: list[FacetedAssignment] = []
        novelties: list[FacetNovelty] = []
        for index in range(0, len(selected_ids), 12):
            batch_ids = selected_ids[index:index + 12]
            rows = [rows_by_id[value] for value in batch_ids]
            prompt = build_assignment_prompt(rows=rows, domain_draft=domain, vocabulary=vocabulary)
            assignment_budget = _faceted_budget(
                stage_name=f"faceted_assignment_batch_{index // 12 + 1:03d}",
                complexity_count=len(batch_ids),
                schema_hint_characters=len(ASSIGNMENT_SCHEMA_HINT),
                base_tokens=2048,
                tokens_per_item=256,
                technical_max_tokens=8192,
            )
            _write_json(run_dir / "budget-preflight" / f"assignment-{index // 12 + 1:03d}.json", assignment_budget.model_dump(mode="json"))
            unit_key = f"batch-{index // 12 + 1:03d}"
            recovered_raw = (recovery or {}).get("assignment_raw", {}).get(unit_key)
            if recovered_raw:
                recovery_dir = self.output_dir / f"run-{int(recovery['source_run_id']):06d}"
                raw_path = recovery_dir / recovered_raw["relative_path"]
                if _hash_file(raw_path) != recovered_raw["hash"]:
                    raise PipelineError("窄修复赋值原响应 Hash 改变", code="faceted_recovery_artifact_changed", retryable=False)
                output = parse_json_content(
                    raw_path.read_text(encoding="utf-8"), FacetedAssignmentOutput
                )
                validate_assignments(
                    output,
                    expected_ids=set(batch_ids),
                    domain_draft=domain,
                    vocabulary=vocabulary,
                )
                target_path = run_dir / "reused-source-artifacts" / f"{unit_key}.json"
                _write_json(target_path, output.model_dump(mode="json"))
                self.run_repository.record_reused_stage(
                    run_id,
                    "faceted_assignment",
                    unit_key,
                    input_hash=_hash_text(prompt),
                    output_path=str(target_path),
                    output_hash=_stable_hash(output.model_dump(mode="json")),
                    model=None,
                    prompt_version=ASSIGNMENT_PROMPT_VERSION,
                    thinking_enabled=False,
                    reasoning_effort=None,
                )
            else:
                output = self._model_stage(run_id=run_id, run_dir=run_dir, stage_name="faceted_assignment", unit_key=unit_key, role="taxonomy_assignment", prompt=prompt, prompt_version=ASSIGNMENT_PROMPT_VERSION, schema=FacetedAssignmentOutput, schema_hint=ASSIGNMENT_SCHEMA_HINT, max_tokens=assignment_budget.allocated_max_tokens, input_ids=batch_ids, validator=lambda value, expected=set(batch_ids): validate_assignments(value, expected_ids=expected, domain_draft=domain, vocabulary=vocabulary))
            assignments.extend(output.assignments)
            novelties.extend(output.facet_novelty_pool)
        assignments.sort(key=lambda item: selected_ids.index(item.content_id))
        assignment_payload = {"version": ASSIGNMENT_SCHEMA_VERSION, "assignments": [item.model_dump(mode="json") for item in assignments]}
        _write_json(run_dir / "faceted-assignments.json", assignment_payload)
        _write_json(run_dir / "facet-novelty-pool.json", {"items": [item.model_dump(mode="json") for item in novelties]})

        filters = simulate_filters(assignments)
        self._deterministic_stage(run_id=run_id, stage_name="faceted_filter_simulation", input_value=assignment_payload, output_path=run_dir / "filter-simulation.json", output_value=filters)
        quality = build_quality_gate(table=table, decomposition=decomposition, vocabulary=vocabulary, assignments=assignments, filter_result=filters, source_domain_hash=protocol["source_artifact_hashes"]["domain_draft"], current_domain_hash=_hash_file(paths["domain_draft"]), runtime_inputs=protocol["runtime_inputs"], domain_draft=domain)
        self._deterministic_stage(run_id=run_id, stage_name="checkpoint310_quality_gate", input_value={"decomposition": decomposition.model_dump(mode="json"), "vocabulary": vocabulary.model_dump(mode="json"), "assignment_hash": _stable_hash(assignment_payload), "filter_hash": _stable_hash(filters)}, output_path=run_dir / "checkpoint310-quality-gate" / "quality-result.json", output_value=quality.model_dump(mode="json"))
        _write_json(
            run_dir / "independent-reviewer-bundle.json",
            build_reviewer_bundle(
                protocol=protocol,
                decomposition=decomposition,
                vocabulary=vocabulary,
                assignments=assignments,
                filter_result=filters,
                quality=quality,
            ),
        )
        _write_json(run_dir / "checkpoint310-lineage.json", {"source_run_ids": [int(protocol["domain_run_id"]), int(protocol["candidate_run_id"])], "snapshot_hash": protocol["snapshot_hash"], "sample_profile_run_id": protocol["sample_profile_run_id"], "selected_ids": selected_ids, "source_artifact_hashes": protocol["source_artifact_hashes"], "outputs": {"decomposition": _hash_file(run_dir / "faceted-candidate-decomposition.json"), "vocabularies": _hash_file(run_dir / "faceted-vocabularies.json"), "assignments": _hash_file(run_dir / "faceted-assignments.json"), "filters": _hash_file(run_dir / "filter-simulation.json"), "quality": _hash_file(run_dir / "checkpoint310-quality-gate" / "quality-result.json")}, "created_at": _utc_now()})
        self.run_repository.set_run_status(run_id, "completed", current_stage="checkpoint310_quality_gate", error_code=None if quality.passed else "faceted_quality_failed", error_message=None if quality.passed else "Checkpoint 3.10 automated gate failed")
        return self.status(run_id)

    def _model_stage(self, *, run_id: int, run_dir: Path, stage_name: str, unit_key: str, role: str, prompt: str, prompt_version: str, schema: type[SchemaT], schema_hint: str, max_tokens: int, input_ids: list[str], validator) -> SchemaT:
        input_hash = _hash_text(prompt)
        stage = self.run_repository.ensure_stage(run_id, stage_name, unit_key, input_hash=input_hash)
        if stage["status"] == "completed":
            result = schema.model_validate_json(Path(stage["output_path"]).read_text(encoding="utf-8"))
            validator(result)
            return result
        previous_attempt = int(stage["attempt_count"])
        resume_existing = stage["status"] in {"processing", "retry_wait"} and previous_attempt > 0
        provider = self.provider_factory(role)
        repair_provider = self.provider_factory("taxonomy_repair")
        started = self.run_repository.start_stage(run_id, stage_name, unit_key, input_hash=input_hash, model=provider.model, prompt_version=prompt_version, thinking_enabled=provider.thinking_enabled, reasoning_effort=provider.reasoning_effort)
        attempt = previous_attempt if resume_existing else int(started["attempt_count"])
        call_dir = run_dir / stage_name / unit_key / f"attempt-{attempt:02d}"
        caller = AuditedJsonCaller(provider=provider, repair_provider=repair_provider)
        try:
            result, audit = caller.call(call_dir=call_dir, prompt=prompt, prompt_version=prompt_version, schema=schema, schema_hint=schema_hint, max_tokens=max_tokens, input_ids=input_ids, validator=validator, resume=call_dir.exists())
        except PipelineError as exc:
            self.run_repository.fail_stage(run_id, stage_name, unit_key, error_code=exc.code, error_message=str(exc), retryable=exc.retryable)
            raise
        self.run_repository.complete_stage(run_id, stage_name, unit_key, output_path=str(call_dir / "parsed-output.json"), output_hash=_stable_hash(result.model_dump(mode="json")), audit=_combined_audit(audit))
        return result

    def _deterministic_stage(self, *, run_id: int, stage_name: str, input_value: Any, output_path: Path, output_value: Any) -> None:
        input_hash = _stable_hash(input_value)
        stage = self.run_repository.ensure_stage(run_id, stage_name, "main", input_hash=input_hash)
        if stage["status"] == "completed":
            if not output_path.is_file() or _hash_file(output_path) != stage["output_hash"]:
                raise PipelineError("已完成确定性 Stage 产物改变", code="faceted_stage_artifact_changed", retryable=False)
            return
        self.run_repository.start_stage(run_id, stage_name, "main", input_hash=input_hash, model=None, prompt_version=FILTER_PROTOCOL_VERSION if stage_name == "faceted_filter_simulation" else QUALITY_GATE_VERSION, thinking_enabled=None, reasoning_effort=None)
        _write_json(output_path, output_value)
        self.run_repository.complete_stage(run_id, stage_name, "main", output_path=str(output_path), output_hash=_hash_file(output_path), audit={"elapsed_seconds": 0, "usage": {}})


def _provider_manifest(provider: OpenAICompatibleProvider) -> dict[str, Any]:
    return {"model": provider.model, "thinking_enabled": provider.thinking_enabled, "reasoning_effort": provider.reasoning_effort}


def _faceted_budget(
    *, stage_name: str, complexity_count: int, schema_hint_characters: int,
    base_tokens: int, tokens_per_item: int, technical_max_tokens: int,
) -> OutputBudgetPreflight:
    result = build_budget_preflight(
        stage_name=stage_name,
        complexity_count=complexity_count,
        schema_hint_characters=schema_hint_characters,
        historical_completion_tokens=None,
        technical_max_tokens=technical_max_tokens,
        safety_margin_ratio=0.25,
        base_tokens=base_tokens,
        tokens_per_item=tokens_per_item,
    )
    require_safe_budget(result)
    return result


def _git_state() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[3]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    return commit, not status


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_hash(value: Any) -> str:
    return _hash_text(_compact_json(value))


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_json_once(path: Path, value: Any) -> None:
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != value:
            raise FileExistsError(path)
        return
    _write_json(path, value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _combined_audit(audit: dict[str, Any]) -> dict[str, Any]:
    usage = dict(audit.get("usage") or {})
    repair = audit.get("repair") or {}
    repair_usage = repair.get("usage") or {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if repair_usage.get(key) is not None:
            usage[key] = int(usage.get(key) or 0) + int(repair_usage[key])
    return {"usage": usage, "elapsed_seconds": round(float(audit.get("elapsed_seconds") or 0) + float(repair.get("elapsed_seconds") or 0), 3)}


def _norm(value: str) -> str:
    return "".join(value.lower().split())
