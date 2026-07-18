from __future__ import annotations

import hashlib
import json
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.domain import PipelineError
from shiliu.llm import OpenAICompatibleProvider
from shiliu.taxonomy.candidates import TopLevelDomainDraft
from shiliu.taxonomy.model_calls import AuditedJsonCaller
from shiliu.taxonomy.repository import TaxonomyRepository
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from shiliu.taxonomy.semantic_purity import build_budget_preflight, require_safe_budget


HYBRID_ENGINE_VERSION = "hybrid-controlled-facets-v1"
HYBRID_PROTOCOL_VERSION = "checkpoint311-hybrid-controlled-facets-v1"
ASSIGNMENT_SCHEMA_VERSION = "controlled-facet-assignment-v1"
ASSIGNMENT_PROMPT_VERSION = "controlled-facet-assignment-v3"
ENTITY_MAPPING_VERSION = "entity-object-type-mapping-v1"
DYNAMIC_FACETING_VERSION = "dynamic-faceting-v1"
QUALITY_GATE_VERSION = "checkpoint311-controlled-facet-gate-v1"
REVIEWER_BUNDLE_VERSION = "checkpoint311-reviewer-bundle-v1"

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class ControlledTerm(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    canonical_name: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1, max_length=240)
    includes: tuple[str, ...] = Field(min_length=1, max_length=8)
    excludes: tuple[str, ...] = Field(min_length=1, max_length=8)
    aliases: tuple[str, ...] = Field(max_length=8)
    status: Literal["active", "deprecated"]
    version: str


class ControlledVocabulary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    vocabulary: Literal[
        "presentation_form", "focus_object_type", "suggested_use_context"
    ]
    version: str
    terms: tuple[ControlledTerm, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_asset(self):
        expected = {
            "presentation_form": ("presentation_form_v1", "PF"),
            "focus_object_type": ("focus_object_type_v1", "OT"),
            "suggested_use_context": ("suggested_use_context_v1", "UC"),
        }[self.vocabulary]
        if self.version != expected[0]:
            raise ValueError("controlled vocabulary version mismatch")
        ids = [term.id for term in self.terms]
        if len(ids) != len(set(ids)) or any(
            not value.startswith(expected[1]) for value in ids
        ):
            raise ValueError("controlled vocabulary IDs are invalid or duplicated")
        if any(term.version != self.version for term in self.terms):
            raise ValueError("term version must equal asset version")
        return self

    @property
    def active_ids(self) -> frozenset[str]:
        return frozenset(term.id for term in self.terms if term.status == "active")


class ControlledVocabularyRegistry(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    presentation_form: ControlledVocabulary
    focus_object_type: ControlledVocabulary
    suggested_use_context: ControlledVocabulary
    hashes: dict[str, str]

    def term(self, value: str) -> ControlledTerm:
        for vocabulary in (
            self.presentation_form,
            self.focus_object_type,
            self.suggested_use_context,
        ):
            for term in vocabulary.terms:
                if term.id == value:
                    return term
        raise KeyError(value)


def load_controlled_vocabularies(
    root: Path | None = None,
) -> ControlledVocabularyRegistry:
    directory = root or Path(__file__).with_name("vocabularies")
    filenames = {
        "presentation_form": "presentation_form_v1.yaml",
        "focus_object_type": "focus_object_type_v1.yaml",
        "suggested_use_context": "suggested_use_context_v1.yaml",
    }
    values: dict[str, ControlledVocabulary] = {}
    hashes: dict[str, str] = {}
    for key, filename in filenames.items():
        path = directory / filename
        raw = path.read_bytes()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PipelineError(
                f"受控词表不是 JSON-compatible YAML：{filename}",
                code="controlled_vocabulary_invalid",
                retryable=False,
            ) from exc
        values[key] = ControlledVocabulary.model_validate(payload)
        hashes[filename] = hashlib.sha256(raw).hexdigest()
    return ControlledVocabularyRegistry(
        presentation_form=values["presentation_form"],
        focus_object_type=values["focus_object_type"],
        suggested_use_context=values["suggested_use_context"],
        hashes=hashes,
    )


ENTITY_TYPE_TO_OBJECT_TYPE = {
    "tool": "OT01",
    "framework": "OT01",
    "library": "OT01",
    "plugin": "OT01",
    "platform": "OT01",
    "model": "OT02",
    "llm": "OT02",
    "project": "OT03",
    "product": "OT03",
    "repository": "OT03",
    "application": "OT03",
    "system": "OT03",
    "paper": "OT04",
    "research_report": "OT04",
    "research_artifact": "OT04",
    "course": "OT05",
    "textbook": "OT05",
    "learning_resource": "OT05",
    "question_bank": "OT05",
    "job": "OT06",
    "role": "OT06",
    "position": "OT06",
    "company": "OT07",
    "organization": "OT07",
    "team": "OT07",
    "community": "OT07",
    "dataset": "OT08",
    "eval_set": "OT08",
    "benchmark": "OT08",
    "release": "OT09",
    "conference": "OT09",
    "event": "OT09",
}


class EntityObjectMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    source_entity: str = Field(min_length=1, max_length=120)
    source_type: str | None = Field(default=None, max_length=60)
    object_type_id: str | None = Field(default=None, pattern=r"^OT[0-9]{2}$")
    mapping_status: Literal["mapped", "untyped", "unsupported"]
    rule_version: Literal[ENTITY_MAPPING_VERSION] = ENTITY_MAPPING_VERSION
    reason: str = Field(min_length=1, max_length=180)


def map_entities_to_object_types(
    entities: list[str | dict[str, Any]], registry: ControlledVocabularyRegistry,
) -> list[EntityObjectMapping]:
    results: list[EntityObjectMapping] = []
    for entity in entities:
        if isinstance(entity, str):
            results.append(
                EntityObjectMapping(
                    source_entity=entity,
                    source_type=None,
                    object_type_id=None,
                    mapping_status="untyped",
                    reason="source entity has no reliable type; controlled model choice or empty is required",
                )
            )
            continue
        name = str(entity.get("name") or "").strip()
        source_type = str(entity.get("type") or "").strip().lower().replace(" ", "_")
        if not name:
            raise ValueError("entity name cannot be empty")
        object_type_id = ENTITY_TYPE_TO_OBJECT_TYPE.get(source_type)
        if object_type_id and object_type_id in registry.focus_object_type.active_ids:
            status: Literal["mapped", "untyped", "unsupported"] = "mapped"
            reason = f"deterministic {source_type} mapping"
        else:
            status = "unsupported" if source_type else "untyped"
            reason = "source entity type has no active deterministic mapping"
            object_type_id = None
        results.append(
            EntityObjectMapping(
                source_entity=name,
                source_type=source_type or None,
                object_type_id=object_type_id,
                mapping_status=status,
                reason=reason,
            )
        )
    return results


class ControlledDomainAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    primary_path: list[str] = Field(min_length=1, max_length=2)
    secondary_paths: list[list[str]] = Field(max_length=2)
    confidence: Literal["high", "medium", "low"]

    @model_validator(mode="before")
    @classmethod
    def normalize_secondary_path_shorthand(cls, value: Any) -> Any:
        """Accept the model's unambiguous `[child_id]` shorthand, then canonicalize later."""
        if not isinstance(value, dict):
            return value
        secondary = value.get("secondary_paths")
        if isinstance(secondary, list):
            value = dict(value)
            value["secondary_paths"] = [
                [path] if isinstance(path, str) else path for path in secondary
            ]
        return value


class ControlledFormAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    primary: str
    secondary: str | None = None
    confidence: Literal["high", "medium", "low"]
    evidence: list[str] = Field(max_length=3)

    @model_validator(mode="after")
    def validate_form(self):
        if self.primary != "unknown" and not self.primary.startswith("PF"):
            raise ValueError("primary Form must be controlled ID or unknown")
        if self.secondary is not None and not self.secondary.startswith("PF"):
            raise ValueError("secondary Form must be controlled ID")
        if self.secondary == self.primary:
            raise ValueError("secondary Form must differ from primary")
        if self.primary != "unknown" and not self.evidence:
            raise ValueError("assigned Form requires evidence")
        return self


class ControlledObjectAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(pattern=r"^OT[0-9]{2}$")
    source_entities: list[str] = Field(min_length=1, max_length=5)
    mapping_source: Literal["deterministic", "model_assisted"]
    confidence: Literal["high", "medium", "low"]
    evidence: list[str] = Field(min_length=1, max_length=3)


class SuggestedContextAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(pattern=r"^UC[0-9]{2}$")
    confidence: Literal["high", "medium", "low"]
    evidence: list[str] = Field(min_length=1, max_length=3)


class NoveltyProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    facet: Literal["presentation_form", "focus_object_type", "suggested_use_context"]
    proposed_name: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1, max_length=180)
    closest_existing_ids: list[str] = Field(max_length=3)
    difference: str = Field(min_length=1, max_length=180)
    supporting_content_ids: list[str] = Field(min_length=1, max_length=12)
    evidence: list[str] = Field(min_length=1, max_length=3)
    confidence: Literal["high", "medium", "low"]


class HybridControlledAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    content_id: str = Field(pattern=r"^C[0-9]{3}$")
    domain: ControlledDomainAssignment
    presentation_form: ControlledFormAssignment
    object_types: list[ControlledObjectAssignment] = Field(max_length=2)
    suggested_use_contexts: list[SuggestedContextAssignment] = Field(max_length=2)
    facet_novelty: list[NoveltyProposal] = Field(max_length=3)
    ambiguities: list[str] = Field(max_length=5)

    @model_validator(mode="after")
    def validate_budgets(self):
        if len({value.id for value in self.object_types}) != len(self.object_types):
            raise ValueError("duplicate Object Type")
        if len({value.id for value in self.suggested_use_contexts}) != len(
            self.suggested_use_contexts
        ):
            raise ValueError("duplicate Suggested Context")
        return self


class HybridAssignmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[ASSIGNMENT_SCHEMA_VERSION] = ASSIGNMENT_SCHEMA_VERSION
    assignments: list[HybridControlledAssignment] = Field(min_length=1, max_length=12)


class ControlledQualityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[QUALITY_GATE_VERSION] = QUALITY_GATE_VERSION
    passed: bool
    blocking_issues: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    metrics: dict[str, Any]


ASSIGNMENT_SCHEMA_HINT = (
    '{"version":"controlled-facet-assignment-v1","assignments":[{'
    '"content_id":"C001","domain":{"primary_path":["d_01"],'
    '"secondary_paths":[["d_02","d_02_01"]],'
    '"confidence":"high|medium|low"},'
    '"presentation_form":{"primary":"PF01|unknown","secondary":null,'
    '"confidence":"high|medium|low","evidence":[""]},'
    '"object_types":[{"id":"OT01","source_entities":[""],'
    '"mapping_source":"deterministic|model_assisted",'
    '"confidence":"high|medium|low","evidence":[""]}],'
    '"suggested_use_contexts":[{"id":"UC01",'
    '"confidence":"high|medium|low","evidence":[""]}],'
    '"facet_novelty":[],"ambiguities":[]}]}')


def build_assignment_prompt(
    *, rows: list[dict[str, Any]], domain_draft: TopLevelDomainDraft,
    registry: ControlledVocabularyRegistry,
    entity_mappings: dict[str, list[EntityObjectMapping]],
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
    payload = {
        "domains": domains,
        "presentation_forms": _active_terms(registry.presentation_form),
        "focus_object_types": _active_terms(registry.focus_object_type),
        "suggested_use_contexts": _active_terms(registry.suggested_use_context),
        "entity_mapping_version": ENTITY_MAPPING_VERSION,
        "entity_mappings": {
            key: [item.model_dump(mode="json") for item in values]
            for key, values in entity_mappings.items()
        },
        "contents": rows,
    }
    return f"""你执行 Hybrid Controlled Facet Assignment。只能选择输入中的 active PF/OT/UC ID；不得创建或激活词条，也不得读取或借用历史开放词表。

Presentation Form 回答作者如何组织、表达或呈现。primary 必须是一个 PF ID或 unknown；secondary 最多一个且只有明显检索价值时填写。对象词、领域词、面试等场景词不能改变 Form 名称。

Focus Object Type 只在内容围绕明确具体对象类别时填写，0～2 个。具体名称必须写在 source_entities，ID 只表示类别。先保留 deterministic 映射；untyped/unsupported Entity 可在文本证据充分时 model_assisted 选择一个已有 OT，也可留空。知识体系、任务流程、个人经验、主题观点、学习路径、技术方法、目标和抽象领域都不是 Object Type。
source_entities 只能逐字复制该 content_id 的 entity_mappings.source_entity；该列表为空时 object_types 必须为空。每个 evidence 数组最多 3 条。

Suggested Use Context 是可空 AI 建议，0～2 个；不得从 Domain 或收藏夹名称机械推断。Novelty 只能写 Proposal，不能用于本条正式赋值。

Domain 只使用冻结 ID，primary path 1～2 级，secondary paths 最多 2。secondary_paths 的每个元素都必须是完整路径数组，例如 [["d_02","d_02_01"]]，不能写成 ["d_02_01"]。所有 evidence 必须来自本条输入。只输出 JSON。

Schema：{ASSIGNMENT_SCHEMA_HINT}
输入：{_compact_json(payload)}"""


def _build_repair_schema_hint(
    entity_mappings: dict[str, list[EntityObjectMapping]],
) -> str:
    allowed = {
        content_id: [mapping.source_entity for mapping in mappings]
        for content_id, mappings in entity_mappings.items()
    }
    return (
        ASSIGNMENT_SCHEMA_HINT
        + "\nRepair constraints: source_entities may only copy exact strings from "
        + _compact_json(allowed)
        + ". If a content_id has no allowed source entity, object_types must be []. "
        + "Each evidence array has at most 3 items."
    )


def _active_terms(vocabulary: ControlledVocabulary) -> list[dict[str, Any]]:
    return [term.model_dump(mode="json") for term in vocabulary.terms if term.status == "active"]


def validate_assignments(
    output: HybridAssignmentOutput, *, expected_ids: set[str],
    domain_draft: TopLevelDomainDraft, registry: ControlledVocabularyRegistry,
    entity_mappings: dict[str, list[EntityObjectMapping]],
) -> None:
    ids = [item.content_id for item in output.assignments]
    if len(ids) != len(set(ids)) or set(ids) != expected_ids:
        raise PipelineError(
            "受控分面赋值没有完整且唯一覆盖批次",
            code="controlled_assignment_coverage_mismatch", retryable=False,
        )
    parent_by_id: dict[str, str | None] = {}
    for parent in domain_draft.domains:
        parent_by_id[parent.id] = None
        for child in parent.children:
            parent_by_id[child.id] = parent.id
    for item in output.assignments:
        item.domain.primary_path = _canonical_domain_path(
            item.domain.primary_path, parent_by_id
        )
        item.domain.secondary_paths = [
            _canonical_domain_path(path, parent_by_id)
            for path in item.domain.secondary_paths
        ]
        _validate_domain_path(item.domain.primary_path, parent_by_id)
        for path in item.domain.secondary_paths:
            _validate_domain_path(path, parent_by_id)
        form_ids = {item.presentation_form.primary, item.presentation_form.secondary} - {
            None, "unknown"
        }
        if not form_ids <= registry.presentation_form.active_ids:
            raise PipelineError("赋值使用非 active Form", code="uncontrolled_form", retryable=False)
        if not {value.id for value in item.object_types} <= registry.focus_object_type.active_ids:
            raise PipelineError("赋值使用非 active Object Type", code="uncontrolled_object_type", retryable=False)
        if not {value.id for value in item.suggested_use_contexts} <= registry.suggested_use_context.active_ids:
            raise PipelineError("赋值使用非 active Context", code="uncontrolled_context", retryable=False)
        known_entities = {
            mapping.source_entity for mapping in entity_mappings[item.content_id]
        }
        for value in item.object_types:
            if not set(value.source_entities) <= known_entities:
                raise PipelineError("Object Type 缺少来源 Entity", code="object_without_entity", retryable=False)
        deterministic = {
            (mapping.source_entity, mapping.object_type_id)
            for mapping in entity_mappings[item.content_id]
            if mapping.mapping_status == "mapped"
        }
        assigned = {
            (entity, value.id)
            for value in item.object_types
            for entity in value.source_entities
        }
        if not deterministic <= assigned:
            raise PipelineError("确定性 Entity 映射未保留", code="deterministic_mapping_lost", retryable=False)
        for proposal in item.facet_novelty:
            if proposal.supporting_content_ids != [item.content_id]:
                raise PipelineError("单条 Proposal 血缘无效", code="novelty_lineage_invalid", retryable=False)
            allowed = {
                "presentation_form": registry.presentation_form.active_ids,
                "focus_object_type": registry.focus_object_type.active_ids,
                "suggested_use_context": registry.suggested_use_context.active_ids,
            }[proposal.facet]
            if not set(proposal.closest_existing_ids) <= allowed:
                raise PipelineError("Novelty 引用未知词条", code="novelty_unknown_closest", retryable=False)


def _validate_domain_path(path: list[str], parent_by_id: dict[str, str | None]) -> None:
    if any(value not in parent_by_id for value in path):
        raise PipelineError("未知 Domain ID", code="unknown_domain", retryable=False)
    if len(path) == 2 and parent_by_id[path[1]] != path[0]:
        raise PipelineError("Domain path 父子关系错误", code="invalid_domain_path", retryable=False)
    if len(path) == 1 and parent_by_id[path[0]] is not None:
        raise PipelineError("子 Domain 缺少父级", code="invalid_domain_path", retryable=False)


def _canonical_domain_path(
    path: list[str], parent_by_id: dict[str, str | None]
) -> list[str]:
    if len(path) != 1 or path[0] not in parent_by_id:
        return path
    parent_id = parent_by_id[path[0]]
    return [parent_id, path[0]] if parent_id is not None else path


def build_dynamic_faceting(
    assignments: list[HybridControlledAssignment],
    registry: ControlledVocabularyRegistry,
) -> dict[str, Any]:
    records = _facet_records(assignments)
    all_ids = set(records)
    global_options = _available_options(records, all_ids)
    first_steps: list[dict[str, Any]] = []
    second_steps: list[dict[str, Any]] = []
    third_steps: list[dict[str, Any]] = []
    domain_labels = sorted(global_options["domain"])
    for domain_id in domain_labels:
        result = _query(records, {"domain": {domain_id}})
        options = _available_options(records, result)
        first_steps.append(
            _step({"domain": [domain_id]}, result, options, registry)
        )
        for form_id in sorted(options["presentation_form"]):
            result2 = _query(
                records,
                {"domain": {domain_id}, "presentation_form": {form_id}},
            )
            options2 = _available_options(records, result2)
            second_steps.append(
                _step(
                    {"domain": [domain_id], "presentation_form": [form_id]},
                    result2, options2, registry,
                )
            )
            for object_id in sorted(options2["focus_object_type"]):
                result3 = _query(
                    records,
                    {
                        "domain": {domain_id},
                        "presentation_form": {form_id},
                        "focus_object_type": {object_id},
                    },
                )
                if result3:
                    third_steps.append(
                        _step(
                            {
                                "domain": [domain_id],
                                "presentation_form": [form_id],
                                "focus_object_type": [object_id],
                            },
                            result3,
                            _available_options(records, result3),
                            registry,
                        )
                    )
    all_controlled = {
        "presentation_form": len(registry.presentation_form.active_ids),
        "focus_object_type": len(registry.focus_object_type.active_ids),
        "suggested_use_context": len(registry.suggested_use_context.active_ids),
    }
    second_counts = [item["result_count"] for item in second_steps]
    reductions = _facet_reductions(records)
    redundancy = _cross_facet_redundancy(records)
    exposed_zero = sum(
        count == 0
        for steps in (first_steps, second_steps, third_steps)
        for item in steps
        for values in item["available_options"].values()
        for count in values.values()
    )
    return {
        "version": DYNAMIC_FACETING_VERSION,
        "semantics": {"within_facet": "OR", "across_facets": "AND"},
        "assignment_count": len(assignments),
        "global_nonzero_options": global_options,
        "first_steps": first_steps,
        "second_steps": second_steps,
        "third_steps": third_steps,
        "metrics": {
            "first_result_median": _median([item["result_count"] for item in first_steps]),
            "first_available_form_median": _median([len(item["available_options"]["presentation_form"]) for item in first_steps]),
            "first_available_object_median": _median([len(item["available_options"]["focus_object_type"]) for item in first_steps]),
            "first_available_context_median": _median([len(item["available_options"]["suggested_use_context"]) for item in first_steps]),
            "second_result_median": _median(second_counts),
            "second_singleton_ratio": round(sum(value == 1 for value in second_counts) / len(second_counts), 4) if second_counts else 0,
            "second_refinable_ratio": round(sum(any(item["available_options"][facet] for facet in ("focus_object_type", "suggested_use_context")) for item in second_steps) / len(second_steps), 4) if second_steps else 0,
            "hidden_zero_support_values": {
                facet: sum(max(0, total - len(item["available_options"][facet])) for item in second_steps)
                for facet, total in all_controlled.items()
            },
            "exposed_zero_option_count": exposed_zero,
            "average_reduction_ratio": reductions,
            "near_duplicate_cross_facet_count": len(redundancy),
        },
        "near_duplicate_cross_facet": redundancy,
    }


def _facet_records(assignments: list[HybridControlledAssignment]) -> dict[str, dict[str, set[str]]]:
    return {
        item.content_id: {
            "domain": set(item.domain.primary_path + [value for path in item.domain.secondary_paths for value in path]),
            "presentation_form": {value for value in (item.presentation_form.primary, item.presentation_form.secondary) if value and value != "unknown"},
            "focus_object_type": {value.id for value in item.object_types},
            "suggested_use_context": {value.id for value in item.suggested_use_contexts},
        }
        for item in assignments
    }


def _query(records: dict[str, dict[str, set[str]]], selections: dict[str, set[str]]) -> set[str]:
    return {
        content_id for content_id, facets in records.items()
        if all(not values or facets[facet] & values for facet, values in selections.items())
    }


def _available_options(records: dict[str, dict[str, set[str]]], current_ids: set[str]) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for facet in ("domain", "presentation_form", "focus_object_type", "suggested_use_context"):
        counts = Counter(value for content_id in current_ids for value in records[content_id][facet])
        output[facet] = dict(sorted((key, value) for key, value in counts.items() if value > 0))
    return output


def _step(selections: dict[str, list[str]], result: set[str], options: dict[str, dict[str, int]], registry: ControlledVocabularyRegistry) -> dict[str, Any]:
    return {"selections": selections, "result_count": len(result), "content_ids": sorted(result), "available_options": options}


def _median(values: list[int]) -> float:
    return round(float(statistics.median(values)), 3) if values else 0


def _facet_reductions(records: dict[str, dict[str, set[str]]]) -> dict[str, Any]:
    total = len(records)
    output: dict[str, Any] = {}
    for facet in ("domain", "presentation_form", "focus_object_type", "suggested_use_context"):
        supports = Counter(value for item in records.values() for value in item[facet])
        ratios = [1 - count / total for count in supports.values()]
        output[facet] = {
            "mean": round(sum(ratios) / len(ratios), 4) if ratios else 0,
            "nonreducing_labels": sorted(label for label, count in supports.items() if count == total),
        }
    return output


def _cross_facet_redundancy(records: dict[str, dict[str, set[str]]]) -> list[dict[str, Any]]:
    supports: dict[tuple[str, str], set[str]] = defaultdict(set)
    facets = ("domain", "presentation_form", "focus_object_type", "suggested_use_context")
    for content_id, values in records.items():
        for facet in facets:
            for label in values[facet]:
                supports[(facet, label)].add(content_id)
    output = []
    facet_order = {facet: index for index, facet in enumerate(facets)}
    items = sorted(
        supports.items(),
        key=lambda item: (facet_order[item[0][0]], item[0][1]),
    )
    for index, ((facet_a, label_a), ids_a) in enumerate(items):
        if len(ids_a) < 3:
            continue
        for (facet_b, label_b), ids_b in items[index + 1:]:
            if facet_a == facet_b or len(ids_b) < 3:
                continue
            intersection = ids_a & ids_b
            p_b_a = len(intersection) / len(ids_a)
            p_a_b = len(intersection) / len(ids_b)
            if p_b_a > 0.9 and p_a_b > 0.9:
                output.append({"left": f"{facet_a}:{label_a}", "right": f"{facet_b}:{label_b}", "support": len(intersection), "p_right_given_left": round(p_b_a, 4), "p_left_given_right": round(p_a_b, 4), "warning": "near_duplicate_cross_facet"})
    return output


def build_derived_filter_proposals(
    assignments: list[HybridControlledAssignment], registry: ControlledVocabularyRegistry,
) -> list[dict[str, Any]]:
    records = _facet_records(assignments)
    pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for content_id, values in records.items():
        for form_id in values["presentation_form"]:
            for object_id in values["focus_object_type"]:
                pairs[(form_id, object_id)].add(content_id)
    output = []
    for (form_id, object_id), content_ids in sorted(pairs.items()):
        if len(content_ids) < 3:
            continue
        output.append({"id": f"DF_{form_id}_{object_id}", "display_name": f"{registry.term(form_id).canonical_name} · {registry.term(object_id).canonical_name}", "expression": {"presentation_form": [form_id], "focus_object_type": [object_id]}, "support_count": len(content_ids), "supporting_content_ids": sorted(content_ids), "status": "report_only"})
    return output


def build_quality_gate(
    *, assignments: list[HybridControlledAssignment], registry: ControlledVocabularyRegistry,
    dynamic: dict[str, Any], source_domain_hash: str, current_domain_hash: str,
    source_vocabulary_hashes: dict[str, str], current_vocabulary_hashes: dict[str, str],
    manifest_inputs: list[str], historical_manifest_hashes: dict[str, str],
    current_historical_hashes: dict[str, str],
) -> ControlledQualityResult:
    blocking: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if source_domain_hash != current_domain_hash:
        blocking.append({"code": "frozen_domain_modified", "details": []})
    if source_vocabulary_hashes != current_vocabulary_hashes:
        blocking.append({"code": "controlled_vocabulary_modified", "details": []})
    if historical_manifest_hashes != current_historical_hashes:
        blocking.append({"code": "historical_run_modified", "details": []})
    if any("run #17 open vocabulary" in value.lower() or "silver" in value.lower() for value in manifest_inputs):
        blocking.append({"code": "forbidden_runtime_input", "details": manifest_inputs})
    unknown = sum(item.presentation_form.primary == "unknown" for item in assignments)
    form_novelty = sum(any(value.facet == "presentation_form" for value in item.facet_novelty) for item in assignments)
    coverage_gap = (unknown + form_novelty) / len(assignments) if assignments else 1
    if coverage_gap > 0.25:
        blocking.append({"code": "controlled_form_coverage_insufficient", "details": [round(coverage_gap, 4)]})
    if dynamic["metrics"]["exposed_zero_option_count"]:
        blocking.append({"code": "dynamic_faceting_exposes_zero", "details": [dynamic["metrics"]["exposed_zero_option_count"]]})
    form_counts = Counter(item.presentation_form.primary for item in assignments if item.presentation_form.primary != "unknown")
    overrepresented = {key: value for key, value in form_counts.items() if value / len(assignments) > 0.4}
    if overrepresented:
        warnings.append({"code": "form_over_40_percent", "details": overrepresented})
    object_empty_rate = sum(not item.object_types for item in assignments) / len(assignments) if assignments else 1
    context_empty_rate = sum(not item.suggested_use_contexts for item in assignments) / len(assignments) if assignments else 1
    if object_empty_rate > 0.6:
        warnings.append({"code": "high_object_empty_rate", "details": [round(object_empty_rate, 4)]})
    if context_empty_rate > 0.6:
        warnings.append({"code": "high_suggested_context_empty_rate", "details": [round(context_empty_rate, 4)]})
    if dynamic["near_duplicate_cross_facet"]:
        warnings.append({"code": "near_duplicate_cross_facet", "details": dynamic["near_duplicate_cross_facet"]})
    if dynamic["metrics"]["second_singleton_ratio"] > 0.5:
        warnings.append({"code": "high_dynamic_second_step_singleton", "details": [dynamic["metrics"]["second_singleton_ratio"]]})
    novelty = [value for item in assignments for value in item.facet_novelty]
    if novelty:
        warnings.append({"code": "single_item_novelty_proposals", "details": len(novelty)})
    used = {
        "presentation_form": set(form_counts),
        "focus_object_type": {value.id for item in assignments for value in item.object_types},
        "suggested_use_context": {value.id for item in assignments for value in item.suggested_use_contexts},
    }
    unused = {
        "presentation_form": sorted(registry.presentation_form.active_ids - used["presentation_form"]),
        "focus_object_type": sorted(registry.focus_object_type.active_ids - used["focus_object_type"]),
        "suggested_use_context": sorted(registry.suggested_use_context.active_ids - used["suggested_use_context"]),
    }
    if any(unused.values()):
        warnings.append({"code": "controlled_terms_unused_in_sample", "details": unused})
    return ControlledQualityResult(
        passed=not blocking,
        blocking_issues=blocking,
        warnings=warnings,
        metrics={"assignment_count": len(assignments), "form_unknown_count": unknown, "form_novelty_count": form_novelty, "form_coverage_gap_rate": round(coverage_gap, 4), "object_empty_rate": round(object_empty_rate, 4), "suggested_context_empty_rate": round(context_empty_rate, 4), "average_object_labels": round(sum(len(item.object_types) for item in assignments) / len(assignments), 3) if assignments else 0, "average_context_labels": round(sum(len(item.suggested_use_contexts) for item in assignments) / len(assignments), 3) if assignments else 0, "average_total_labels": round(sum(1 + (item.presentation_form.primary != "unknown") + (item.presentation_form.secondary is not None) + len(item.object_types) + len(item.suggested_use_contexts) for item in assignments) / len(assignments), 3) if assignments else 0, "novelty_count": len(novelty), "used_term_counts": {key: len(value) for key, value in used.items()}, "unused_terms": unused, "dynamic_metrics": dynamic["metrics"]},
    )


def build_reviewer_bundle(
    *, protocol: dict[str, Any], registry: ControlledVocabularyRegistry,
    entity_mappings: dict[str, list[EntityObjectMapping]],
    assignments: list[HybridControlledAssignment], dynamic: dict[str, Any],
    proposals: list[dict[str, Any]], derived: list[dict[str, Any]],
    quality: ControlledQualityResult,
) -> dict[str, Any]:
    return {
        "version": REVIEWER_BUNDLE_VERSION,
        "lineage": {
            "snapshot_hash": protocol["snapshot_hash"],
            "domain_run_id": protocol["domain_run_id"],
            "sample_profile_run_id": protocol["sample_profile_run_id"],
            "vocabulary_hashes": protocol["vocabulary_hashes"],
            "historical_manifest_hashes": protocol["historical_manifest_hashes"],
        },
        "vocabularies": {
            "presentation_form": _active_terms(registry.presentation_form),
            "focus_object_type": _active_terms(registry.focus_object_type),
            "suggested_use_context": _active_terms(
                registry.suggested_use_context
            ),
        },
        "entity_mappings": {
            key: [value.model_dump(mode="json") for value in values]
            for key, values in entity_mappings.items()
        },
        "assignments": {
            "version": ASSIGNMENT_SCHEMA_VERSION,
            "assignments": [value.model_dump(mode="json") for value in assignments],
        },
        "dynamic_faceting": dynamic,
        "novelty_proposals": proposals,
        "derived_filter_proposals": derived,
        "automatic_gate": quality.model_dump(mode="json"),
        "excluded": [
            "Silver Reference",
            "Run #17 open vocabulary",
            "old Candidate Decision correctness claims",
            "raw Provider prompts and responses",
        ],
    }


class HybridControlledFacetsService:
    def __init__(self, *, repository: TaxonomyRepository,
                 run_repository: TaxonomyRunRepository,
                 provider_factory: Callable[[str], OpenAICompatibleProvider],
                 output_dir: Path, profile_output_dir: Path,
                 vocabulary_dir: Path | None = None) -> None:
        self.repository = repository
        self.run_repository = run_repository
        self.provider_factory = provider_factory
        self.output_dir = output_dir
        self.profile_output_dir = profile_output_dir
        self.vocabulary_dir = vocabulary_dir

    def create_spike(self, *, snapshot_id: int = 2, domain_run_id: int = 12,
                     sample_profile_run_id: str) -> int:
        snapshot = self.repository.get_snapshot(snapshot_id)
        domain_run = self.run_repository.get_run(domain_run_id)
        if not snapshot or not domain_run or domain_run.get("status") != "completed":
            raise PipelineError("Hybrid Spike 来源无效", code="hybrid_source_invalid", retryable=False)
        domain_dir = self.output_dir / f"run-{domain_run_id:06d}"
        profile_dir = self.profile_output_dir / sample_profile_run_id
        paths = {"domain_draft": domain_dir / "taxonomy-draft.json", "compact_corpus": domain_dir / "compact-corpus.json", "profile_manifest": profile_dir / "manifest.json", "profile_view": profile_dir / "profile-discovery-view.jsonl"}
        if not all(path.is_file() for path in paths.values()):
            raise PipelineError("Hybrid Spike 缺少冻结来源", code="hybrid_source_missing", retryable=False)
        profile_manifest = json.loads(paths["profile_manifest"].read_text(encoding="utf-8"))
        selected_ids = list(profile_manifest.get("selected_ids") or [])
        if profile_manifest.get("status") != "completed" or profile_manifest.get("snapshot_hash") != snapshot["snapshot_hash"] or len(selected_ids) != 48 or len(set(selected_ids)) != 48:
            raise PipelineError("Hybrid Spike 必须复用验收的 48 条 Manifest", code="hybrid_sample_invalid", retryable=False)
        registry = load_controlled_vocabularies(self.vocabulary_dir)
        git_commit, clean = _git_state()
        if not clean:
            raise PipelineError("创建 Hybrid Spike 前 Git 必须干净", code="hybrid_git_dirty", retryable=False)
        historical_hashes = {
            f"run-{run_id:06d}": _hash_file(self.output_dir / f"run-{run_id:06d}" / "run-manifest.json")
            for run_id in (15, 16, 17)
        }
        providers = {role: _provider_manifest(self.provider_factory(role)) for role in ("taxonomy_assignment", "taxonomy_repair")}
        protocol = {"protocol_version": HYBRID_PROTOCOL_VERSION, "snapshot_id": snapshot_id, "snapshot_hash": snapshot["snapshot_hash"], "domain_run_id": domain_run_id, "sample_profile_run_id": sample_profile_run_id, "selected_ids": selected_ids, "evidence_counts": profile_manifest.get("evidence_counts"), "source_artifact_hashes": {key: _hash_file(path) for key, path in paths.items()}, "vocabulary_hashes": registry.hashes, "historical_manifest_hashes": historical_hashes, "entity_mapping_version": ENTITY_MAPPING_VERSION, "assignment_prompt_version": ASSIGNMENT_PROMPT_VERSION, "assignment_schema_version": ASSIGNMENT_SCHEMA_VERSION, "dynamic_faceting_version": DYNAMIC_FACETING_VERSION, "quality_gate_version": QUALITY_GATE_VERSION, "providers": providers, "git_commit": git_commit, "git_worktree_clean": True, "assignment_inputs": ["Snapshot #2 compact_form_view_v1", "accepted 48-item classification_profile_v1", "Run #12 Domain Draft", "controlled vocabulary v1", "current entity names and deterministic mappings"], "forbidden_inputs": ["Silver Reference", "Run #17 open vocabulary", "old Candidate Decision as correctness evidence"]}
        run_id = self.run_repository.create_run(snapshot_id=snapshot_id, run_kind="hybrid_controlled_facets_spike", engine="hybrid_controlled_facets", engine_version=HYBRID_ENGINE_VERSION, parameters={"snapshot_hash": snapshot["snapshot_hash"], "protocol_manifest": protocol})
        _write_json_once(self.output_dir / f"run-{run_id:06d}" / "run-manifest.json", protocol)
        return run_id

    def status(self, run_id: int) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if not run:
            raise LookupError("Taxonomy Run 不存在")
        return {"run": run, "stages": self.run_repository.list_stages(run_id)}

    def execute(self, run_id: int, *, resume: bool = False) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if not run or run.get("run_kind") != "hybrid_controlled_facets_spike" or run.get("engine_version") != HYBRID_ENGINE_VERSION:
            raise PipelineError("不是 Hybrid Controlled Facets Run", code="hybrid_run_invalid", retryable=False)
        if run["status"] == "completed":
            return self.status(run_id)
        protocol = run["parameters"]["protocol_manifest"]
        run_dir = self.output_dir / f"run-{run_id:06d}"
        if json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8")) != protocol:
            raise PipelineError("Hybrid Manifest 改变", code="hybrid_manifest_changed", retryable=False)
        commit, clean = _git_state()
        if commit != protocol["git_commit"] or not clean:
            raise PipelineError("Hybrid 执行代码状态改变", code="hybrid_code_state_changed", retryable=False)
        registry = load_controlled_vocabularies(self.vocabulary_dir)
        if registry.hashes != protocol["vocabulary_hashes"]:
            raise PipelineError("受控词表改变", code="controlled_vocabulary_changed", retryable=False)
        domain_dir = self.output_dir / f"run-{int(protocol['domain_run_id']):06d}"
        profile_dir = self.profile_output_dir / str(protocol["sample_profile_run_id"])
        paths = {"domain_draft": domain_dir / "taxonomy-draft.json", "compact_corpus": domain_dir / "compact-corpus.json", "profile_manifest": profile_dir / "manifest.json", "profile_view": profile_dir / "profile-discovery-view.jsonl"}
        if {key: _hash_file(path) for key, path in paths.items()} != protocol["source_artifact_hashes"]:
            raise PipelineError("冻结来源改变", code="hybrid_source_changed", retryable=False)
        domain = TopLevelDomainDraft.model_validate_json(paths["domain_draft"].read_text(encoding="utf-8"))
        compact = json.loads(paths["compact_corpus"].read_text(encoding="utf-8"))
        compact_by_id = {str(row[0]): row for row in compact["rows"]}
        profiles = [json.loads(line) for line in paths["profile_view"].read_text(encoding="utf-8").splitlines() if line.strip()]
        profile_by_id = {str(row[0]): row for row in profiles}
        selected_ids = list(protocol["selected_ids"])
        if not set(selected_ids) <= set(compact_by_id) or not set(selected_ids) <= set(profile_by_id):
            raise PipelineError("48 条视图血缘改变", code="hybrid_sample_changed", retryable=False)
        rows: dict[str, dict[str, Any]] = {}
        mapping_by_id: dict[str, list[EntityObjectMapping]] = {}
        for short_id in selected_ids:
            compact_row = compact_by_id[short_id]
            profile_row = profile_by_id[short_id]
            entities = list(profile_row[6])
            mapping_by_id[short_id] = map_entities_to_object_types(entities, registry)
            rows[short_id] = {"content_id": short_id, "evidence_level": compact_row[1], "compact_form_view": compact_row, "classification_profile_v1": profile_row, "entities": entities}
        _write_json(run_dir / "entity-object-mappings.json", {"version": ENTITY_MAPPING_VERSION, "contents": {key: [value.model_dump(mode="json") for value in values] for key, values in mapping_by_id.items()}})
        assignments: list[HybridControlledAssignment] = []
        for index in range(0, 48, 12):
            batch_ids = selected_ids[index:index + 12]
            batch_mappings = {value: mapping_by_id[value] for value in batch_ids}
            prompt = build_assignment_prompt(rows=[rows[value] for value in batch_ids], domain_draft=domain, registry=registry, entity_mappings=batch_mappings)
            repair_schema_hint = _build_repair_schema_hint(batch_mappings)
            budget = build_budget_preflight(stage_name=f"hybrid_assignment_batch_{index // 12 + 1:03d}", complexity_count=len(batch_ids), schema_hint_characters=len(repair_schema_hint), historical_completion_tokens=None, technical_max_tokens=8192, safety_margin_ratio=0.25, base_tokens=2048, tokens_per_item=256)
            require_safe_budget(budget)
            _write_json(run_dir / "budget-preflight" / f"assignment-{index // 12 + 1:03d}.json", budget.model_dump(mode="json"))
            output = self._model_stage(run_id=run_id, run_dir=run_dir, stage_name="hybrid_controlled_assignment", unit_key=f"batch-{index // 12 + 1:03d}", prompt=prompt, schema_hint=repair_schema_hint, max_tokens=budget.allocated_max_tokens, input_ids=batch_ids, validator=lambda value, expected=set(batch_ids), maps=batch_mappings: validate_assignments(value, expected_ids=expected, domain_draft=domain, registry=registry, entity_mappings=maps))
            assignments.extend(output.assignments)
        assignments.sort(key=lambda value: selected_ids.index(value.content_id))
        assignment_payload = {"version": ASSIGNMENT_SCHEMA_VERSION, "assignments": [value.model_dump(mode="json") for value in assignments]}
        _write_json(run_dir / "controlled-facet-assignments.json", assignment_payload)
        proposals = [value.model_dump(mode="json") for item in assignments for value in item.facet_novelty]
        _write_json(run_dir / "facet-novelty-proposals.json", {"proposals": proposals, "runtime_promotion_count": 0})
        dynamic = build_dynamic_faceting(assignments, registry)
        self._deterministic_stage(run_id, "dynamic_faceting", assignment_payload, run_dir / "dynamic-faceting.json", dynamic, DYNAMIC_FACETING_VERSION)
        derived = build_derived_filter_proposals(assignments, registry)
        self._deterministic_stage(run_id, "derived_filter_proposals", {"assignment_hash": _stable_hash(assignment_payload)}, run_dir / "derived-filter-proposals.json", {"proposals": derived}, "derived-filter-proposals-v1")
        current_history = {f"run-{value:06d}": _hash_file(self.output_dir / f"run-{value:06d}" / "run-manifest.json") for value in (15, 16, 17)}
        quality = build_quality_gate(assignments=assignments, registry=registry, dynamic=dynamic, source_domain_hash=protocol["source_artifact_hashes"]["domain_draft"], current_domain_hash=_hash_file(paths["domain_draft"]), source_vocabulary_hashes=protocol["vocabulary_hashes"], current_vocabulary_hashes=registry.hashes, manifest_inputs=protocol["assignment_inputs"], historical_manifest_hashes=protocol["historical_manifest_hashes"], current_historical_hashes=current_history)
        self._deterministic_stage(run_id, "checkpoint311_quality_gate", {"assignment_hash": _stable_hash(assignment_payload), "dynamic_hash": _stable_hash(dynamic)}, run_dir / "checkpoint311-quality-gate" / "quality-result.json", quality.model_dump(mode="json"), QUALITY_GATE_VERSION)
        _write_json(run_dir / "checkpoint311-lineage.json", {"snapshot_hash": protocol["snapshot_hash"], "source_artifact_hashes": protocol["source_artifact_hashes"], "vocabulary_hashes": protocol["vocabulary_hashes"], "historical_manifest_hashes": protocol["historical_manifest_hashes"], "outputs": {"assignments": _hash_file(run_dir / "controlled-facet-assignments.json"), "dynamic": _hash_file(run_dir / "dynamic-faceting.json"), "novelty": _hash_file(run_dir / "facet-novelty-proposals.json"), "derived": _hash_file(run_dir / "derived-filter-proposals.json"), "quality": _hash_file(run_dir / "checkpoint311-quality-gate" / "quality-result.json")}, "created_at": _utc_now()})
        _write_json(
            run_dir / "independent-reviewer-bundle.json",
            build_reviewer_bundle(
                protocol=protocol,
                registry=registry,
                entity_mappings=mapping_by_id,
                assignments=assignments,
                dynamic=dynamic,
                proposals=proposals,
                derived=derived,
                quality=quality,
            ),
        )
        self.run_repository.set_run_status(run_id, "completed", current_stage="checkpoint311_quality_gate", error_code=None if quality.passed else "hybrid_quality_failed", error_message=None if quality.passed else "Checkpoint 3.11 automated gate failed")
        return self.status(run_id)

    def _model_stage(self, *, run_id: int, run_dir: Path, stage_name: str, unit_key: str, prompt: str, schema_hint: str, max_tokens: int, input_ids: list[str], validator) -> HybridAssignmentOutput:
        input_hash = _hash_text(prompt)
        stage = self.run_repository.ensure_stage(run_id, stage_name, unit_key, input_hash=input_hash)
        if stage["status"] == "completed":
            value = HybridAssignmentOutput.model_validate_json(Path(stage["output_path"]).read_text(encoding="utf-8")); validator(value); return value
        previous = int(stage["attempt_count"]); resume_existing = stage["status"] in {"processing", "retry_wait"} and previous > 0
        provider = self.provider_factory("taxonomy_assignment"); repair = self.provider_factory("taxonomy_repair")
        started = self.run_repository.start_stage(run_id, stage_name, unit_key, input_hash=input_hash, model=provider.model, prompt_version=ASSIGNMENT_PROMPT_VERSION, thinking_enabled=provider.thinking_enabled, reasoning_effort=provider.reasoning_effort)
        attempt = previous if resume_existing else int(started["attempt_count"])
        call_dir = run_dir / stage_name / unit_key / f"attempt-{attempt:02d}"
        caller = AuditedJsonCaller(provider=provider, repair_provider=repair)
        try:
            value, audit = caller.call(call_dir=call_dir, prompt=prompt, prompt_version=ASSIGNMENT_PROMPT_VERSION, schema=HybridAssignmentOutput, schema_hint=schema_hint, max_tokens=max_tokens, input_ids=input_ids, validator=validator, resume=call_dir.exists())
        except PipelineError as exc:
            self.run_repository.fail_stage(run_id, stage_name, unit_key, error_code=exc.code, error_message=str(exc), retryable=exc.retryable); raise
        self.run_repository.complete_stage(run_id, stage_name, unit_key, output_path=str(call_dir / "parsed-output.json"), output_hash=_stable_hash(value.model_dump(mode="json")), audit=_combined_audit(audit)); return value

    def _deterministic_stage(self, run_id: int, stage_name: str, input_value: Any, output_path: Path, output_value: Any, version: str) -> None:
        input_hash = _stable_hash(input_value); stage = self.run_repository.ensure_stage(run_id, stage_name, "main", input_hash=input_hash)
        if stage["status"] == "completed":
            if not output_path.is_file() or _hash_file(output_path) != stage["output_hash"]: raise PipelineError("确定性 Stage 产物改变", code="hybrid_stage_changed", retryable=False)
            return
        self.run_repository.start_stage(run_id, stage_name, "main", input_hash=input_hash, model=None, prompt_version=version, thinking_enabled=None, reasoning_effort=None); _write_json(output_path, output_value); self.run_repository.complete_stage(run_id, stage_name, "main", output_path=str(output_path), output_hash=_hash_file(output_path), audit={"elapsed_seconds": 0, "usage": {}})


def _provider_manifest(provider: OpenAICompatibleProvider) -> dict[str, Any]:
    return {"model": provider.model, "thinking_enabled": provider.thinking_enabled, "reasoning_effort": provider.reasoning_effort}


def _git_state() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[3]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    return commit, not status


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _stable_hash(value: Any) -> str:
    return _hash_text(_compact_json(value))


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_json_once(path: Path, value: Any) -> None:
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != value: raise FileExistsError(path)
        return
    _write_json(path, value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _combined_audit(audit: dict[str, Any]) -> dict[str, Any]:
    usage = dict(audit.get("usage") or {}); repair = audit.get("repair") or {}; repair_usage = repair.get("usage") or {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if repair_usage.get(key) is not None: usage[key] = int(usage.get(key) or 0) + int(repair_usage[key])
    return {"usage": usage, "elapsed_seconds": round(float(audit.get("elapsed_seconds") or 0) + float(repair.get("elapsed_seconds") or 0), 3)}
