from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.domain import PipelineError
from shiliu.llm import OpenAICompatibleProvider
from shiliu.taxonomy.candidates import TopLevelDomainDraft
from shiliu.taxonomy.controlled_facets import (
    ASSIGNMENT_SCHEMA_VERSION,
    DYNAMIC_FACETING_VERSION,
    ENTITY_MAPPING_VERSION,
    QUALITY_GATE_VERSION,
    ControlledDomainAssignment,
    ControlledFormAssignment,
    ControlledObjectAssignment,
    ControlledQualityResult,
    ControlledVocabularyRegistry,
    EntityObjectMapping,
    HybridAssignmentOutput,
    HybridControlledAssignment,
    NoveltyProposal,
    SuggestedContextAssignment,
    _active_terms,
    _available_options,
    _canonical_domain_path,
    _combined_audit,
    _compact_json,
    _facet_records,
    _git_state,
    _hash_file,
    _hash_text,
    _provider_manifest,
    _query,
    _stable_hash,
    _utc_now,
    _validate_domain_path,
    _write_json,
    _write_json_once,
    build_dynamic_faceting,
    build_quality_gate,
    load_controlled_vocabularies,
    map_entities_to_object_types,
    validate_assignments,
)
from shiliu.taxonomy.model_calls import AuditedJsonCaller
from shiliu.taxonomy.repository import TaxonomyRepository
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from shiliu.taxonomy.semantic_purity import build_budget_preflight, require_safe_budget


COMPLETION_ENGINE_VERSION = "hybrid-controlled-facets-completion-v1"
COMPLETION_PROTOCOL_VERSION = "checkpoint311b-controlled-facet-completion-v1"
MODEL_SCHEMA_VERSION = "controlled-facet-model-output-v1"
MODEL_PROMPT_VERSION = "controlled-facet-completion-v1"
HISTORICAL_ADAPTER_VERSION = "controlled-facet-history-adapter-v1"
OBJECT_NORMALIZATION_VERSION = "merge-duplicate-object-type-v1"
OBJECT_OVERFLOW_PROTOCOL_VERSION = "object-overflow-selection-v1"
DOMAIN_COMBINATION_VERSION = "frozen-domain-combination-v1"
DERIVED_FILTER_VERSION = "controlled-derived-filters-v2"
COMPLETION_GATE_VERSION = "checkpoint311b-quality-gate-v1"
COMPLETION_REVIEWER_BUNDLE_VERSION = "checkpoint311b-reviewer-bundle-v1"


CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


class ModelObjectAssignment(BaseModel):
    """Per-model-item limits stay frozen; only the local merged item may be larger."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(pattern=r"^OT[0-9]{2}$")
    source_entities: list[str] = Field(min_length=1, max_length=5)
    mapping_source: Literal["deterministic", "model_assisted"]
    confidence: Literal["high", "medium", "low"]
    evidence: list[str] = Field(min_length=1, max_length=3)


class ModelFacetAssignment(BaseModel):
    """Provider-owned fields only; Domain is deliberately absent."""

    model_config = ConfigDict(extra="forbid", strict=True)

    content_id: str = Field(pattern=r"^C[0-9]{3}$")
    presentation_form: ControlledFormAssignment
    object_types: list[ModelObjectAssignment] = Field(max_length=4)
    suggested_use_contexts: list[SuggestedContextAssignment] = Field(max_length=2)
    facet_novelty: list[NoveltyProposal] = Field(max_length=3)
    ambiguities: list[str] = Field(max_length=5)

    @model_validator(mode="after")
    def validate_nonmergeable_budgets(self):
        contexts = [value.id for value in self.suggested_use_contexts]
        if len(contexts) != len(set(contexts)):
            raise ValueError("duplicate Suggested Context")
        return self
class ModelFacetOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[MODEL_SCHEMA_VERSION] = MODEL_SCHEMA_VERSION
    assignments: list[ModelFacetAssignment] = Field(min_length=1, max_length=12)


class OverflowObjectTypeCandidate(BaseModel):
    """An auditable candidate preserved when the two-label OT budget is exceeded."""

    model_config = ConfigDict(extra="forbid", strict=True)

    object_type_id: str = Field(pattern=r"^OT[0-9]{2}$")
    source_entities: list[str]
    evidence: list[str]
    confidence: Literal["high", "medium", "low"]
    not_selected_reason: str


MODEL_SCHEMA_HINT = (
    '{"version":"controlled-facet-model-output-v1","assignments":[{'
    '"content_id":"C001","presentation_form":{"primary":"PF01|unknown",'
    '"secondary":null,"confidence":"high|medium|low","evidence":[""]},'
    '"object_types":[{"id":"OT01","source_entities":[""],'
    '"mapping_source":"deterministic|model_assisted",'
    '"confidence":"high|medium|low","evidence":[""]}],'
    '"suggested_use_contexts":[{"id":"UC01",'
    '"confidence":"high|medium|low","evidence":[""]}],'
    '"facet_novelty":[],"ambiguities":[]}]}'
)


def build_completion_prompt(
    *,
    rows: list[dict[str, Any]],
    domain_draft: TopLevelDomainDraft,
    registry: ControlledVocabularyRegistry,
    entity_mappings: dict[str, list[EntityObjectMapping]],
) -> str:
    domain_context: list[dict[str, Any]] = []
    for parent in domain_draft.domains:
        domain_context.append(
            {
                "id": parent.id,
                "name": parent.name,
                "definition": parent.definition,
                "parent_id": None,
            }
        )
        domain_context.extend(
            {
                "id": child.id,
                "name": child.name,
                "definition": child.definition,
                "parent_id": parent.id,
            }
            for child in parent.children
        )
    payload = {
        "readonly_domain_context": domain_context,
        "presentation_forms": _active_terms(registry.presentation_form),
        "focus_object_types": _active_terms(registry.focus_object_type),
        "suggested_use_contexts": _active_terms(registry.suggested_use_context),
        "entity_mappings": {
            content_id: [mapping.model_dump(mode="json") for mapping in mappings]
            for content_id, mappings in entity_mappings.items()
        },
        "contents": rows,
    }
    return f"""你只执行受控 Form/Object/Context 赋值。Domain 仅作为只读语义上下文，本地代码会组合冻结 Domain；输出中严禁出现 domain 或任何未知字段。

Presentation Form 只能选择 active PF ID 或 unknown；secondary 最多一个。Focus Object Type 只能选择 active OT ID，可空，最多两个唯一 ID。若多个 Entity 属于同一 OT，只输出一个 OT 项并合并 source_entities。source_entities 只能逐字复制本 content_id 的 Entity 白名单；没有 Entity 时 object_types 必须为空。Suggested Use Context 只能选择 active UC ID，可空且最多两个，不得机械复制 Domain。

每个 evidence 最多三条。Novelty 只能形成 Proposal，不能成为正式标签。不得创建新词条。只输出 JSON。

Schema（明确不含 Domain）：{MODEL_SCHEMA_HINT}
输入：{_compact_json(payload)}"""


def build_completion_repair_hint(
    *,
    expected_ids: list[str],
    entity_mappings: dict[str, list[EntityObjectMapping]],
    registry: ControlledVocabularyRegistry,
) -> str:
    allowed_entities = {
        content_id: [mapping.source_entity for mapping in mappings]
        for content_id, mappings in entity_mappings.items()
    }
    constraints = {
        "allowed_content_ids": expected_ids,
        "allowed_entities_by_content": allowed_entities,
        "allowed_pf_ids": sorted(registry.presentation_form.active_ids),
        "allowed_ot_ids": sorted(registry.focus_object_type.active_ids),
        "allowed_uc_ids": sorted(registry.suggested_use_context.active_ids),
        "forbidden_fields": ["domain"],
        "budgets": {
            "presentation_form_primary": 1,
            "presentation_form_secondary": 1,
            "unique_object_type_ids": 2,
            "suggested_use_contexts": 2,
            "evidence_per_item": 3,
        },
    }
    return (
        MODEL_SCHEMA_HINT
        + "\nRepair only JSON structure; do not redo semantic assignment. "
        + "Never output Domain. Duplicate OT IDs may remain because local audited "
        + "normalization merges them. Constraints:"
        + _compact_json(constraints)
    )


def normalize_model_assignment(
    assignment: ModelFacetAssignment,
    *,
    allowed_entities: set[str],
    timestamp: str,
    central_object_type_ids: set[str] | None = None,
) -> tuple[ModelFacetAssignment, list[dict[str, Any]]]:
    """Merge duplicate IDs, then select at most two OT labels without truncation."""

    groups: dict[str, list[ModelObjectAssignment]] = {}
    order: list[str] = []
    for item in assignment.object_types:
        if item.id not in groups:
            groups[item.id] = []
            order.append(item.id)
        groups[item.id].append(item)

    merged_objects: list[ControlledObjectAssignment] = []
    events: list[dict[str, Any]] = []
    for object_type_id in order:
        original_items = groups[object_type_id]
        merged_entities = _ordered_unique(
            entity
            for item in original_items
            for entity in item.source_entities
        )
        merged_evidence = _ordered_unique(
            evidence
            for item in original_items
            for evidence in item.evidence
        )
        if not set(merged_entities) <= allowed_entities:
            raise PipelineError(
                "Object Type 包含 Entity 白名单之外的名称",
                code="object_without_entity",
                retryable=False,
            )
        original_confidences = [item.confidence for item in original_items]
        final_confidence = max(original_confidences, key=CONFIDENCE_RANK.__getitem__)
        mapping_source: Literal["deterministic", "model_assisted"] = (
            "deterministic"
            if all(item.mapping_source == "deterministic" for item in original_items)
            else "model_assisted"
        )
        merged = ControlledObjectAssignment(
            id=object_type_id,
            source_entities=merged_entities,
            mapping_source=mapping_source,
            confidence=final_confidence,
            evidence=merged_evidence,
        )
        merged_objects.append(merged)
        if len(original_items) > 1:
            events.append(
                {
                    "operation": "merge_duplicate_object_type_v1",
                    "content_id": assignment.content_id,
                    "object_type_id": object_type_id,
                    "original_item_count": len(original_items),
                    "original_items": [
                        item.model_dump(mode="json") for item in original_items
                    ],
                    "merged_source_entities": merged_entities,
                    "merged_evidence": merged_evidence,
                    "original_confidences": original_confidences,
                    "final_confidence": final_confidence,
                    "normalization_rule_version": OBJECT_NORMALIZATION_VERSION,
                    "timestamp": timestamp,
                }
            )

    central = central_object_type_ids or set()
    ranked = (
        sorted(
            merged_objects,
            key=lambda item: (
                -(item.id in central),
                -CONFIDENCE_RANK[item.confidence],
                -len(item.evidence),
                -len(item.source_entities),
                item.id,
            ),
        )
        if len(merged_objects) > 2
        else merged_objects
    )
    selected = ranked[:2]
    overflow = ranked[2:]
    if overflow:
        overflow_candidates = [
            OverflowObjectTypeCandidate(
                object_type_id=item.id,
                source_entities=list(item.source_entities),
                evidence=list(item.evidence),
                confidence=item.confidence,
                not_selected_reason=(
                    "根据内容中心性、置信度和证据强度排序后未进入最多两个标签。"
                ),
            ).model_dump(mode="json")
            for item in overflow
        ]
        events.append(
            {
                "operation": OBJECT_OVERFLOW_PROTOCOL_VERSION,
                "content_id": assignment.content_id,
                "selected_object_types": [item.id for item in selected],
                "overflow_object_type_candidates": overflow_candidates,
                "ranking": [
                    {
                        "object_type_id": item.id,
                        "central": item.id in central,
                        "confidence": item.confidence,
                        "evidence_count": len(item.evidence),
                        "source_entity_count": len(item.source_entities),
                    }
                    for item in ranked
                ],
                "timestamp": timestamp,
            }
        )
    normalized = assignment.model_copy(update={"object_types": selected})
    return normalized, events


def combine_frozen_domain(
    assignment: ModelFacetAssignment,
    domain: ControlledDomainAssignment,
) -> HybridControlledAssignment:
    return HybridControlledAssignment(
        content_id=assignment.content_id,
        domain=domain.model_copy(deep=True),
        presentation_form=assignment.presentation_form.model_copy(deep=True),
        object_types=[
            ControlledObjectAssignment.model_validate(value.model_dump(mode="json"))
            for value in assignment.object_types
        ],
        suggested_use_contexts=[
            value.model_copy(deep=True)
            for value in assignment.suggested_use_contexts
        ],
        facet_novelty=[value.model_copy(deep=True) for value in assignment.facet_novelty],
        ambiguities=list(assignment.ambiguities),
    )


def adapt_historical_batch(
    output: HybridAssignmentOutput,
    *,
    expected_ids: list[str],
    entity_mappings: dict[str, list[EntityObjectMapping]],
    timestamp: str,
) -> tuple[list[HybridControlledAssignment], dict[str, Any]]:
    by_id = {item.content_id: item for item in output.assignments}
    if list(by_id) != expected_ids or len(by_id) != len(expected_ids):
        raise PipelineError(
            "历史 Batch 成员或顺序改变",
            code="historical_batch_membership_changed",
            retryable=False,
        )
    adapted: list[HybridControlledAssignment] = []
    operations: list[dict[str, Any]] = []
    for content_id in expected_ids:
        legacy = by_id[content_id]
        model_assignment = ModelFacetAssignment(
            content_id=legacy.content_id,
            presentation_form=legacy.presentation_form,
            object_types=[
                ModelObjectAssignment.model_validate(item.model_dump(mode="json"))
                for item in legacy.object_types
            ],
            suggested_use_contexts=legacy.suggested_use_contexts,
            facet_novelty=legacy.facet_novelty,
            ambiguities=legacy.ambiguities,
        )
        normalized, merge_events = normalize_model_assignment(
            model_assignment,
            allowed_entities={
                mapping.source_entity for mapping in entity_mappings[content_id]
            },
            timestamp=timestamp,
        )
        operations.append(
            {
                "operation": "remove_legacy_model_domain_v1",
                "content_id": content_id,
                "removed_domain": legacy.domain.model_dump(mode="json"),
                "replacement": "frozen_domain_assignment",
                "adapter_version": HISTORICAL_ADAPTER_VERSION,
                "timestamp": timestamp,
            }
        )
        operations.extend(merge_events)
        adapted.append(combine_frozen_domain(normalized, legacy.domain))
    return adapted, {
        "adapter_version": HISTORICAL_ADAPTER_VERSION,
        "source_count": len(output.assignments),
        "adapted_count": len(adapted),
        "semantic_fields_changed": False,
        "operations": operations,
    }


def _ordered_unique(values) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output


def extract_frozen_domains(
    *,
    source_run_dir: Path,
    selected_ids: list[str],
    domain_draft: TopLevelDomainDraft,
) -> tuple[dict[str, ControlledDomainAssignment], dict[str, Any]]:
    """Freeze per-card Domain decisions from Run #20 without asking the model again."""

    parent_by_id: dict[str, str | None] = {}
    for parent in domain_draft.domains:
        parent_by_id[parent.id] = None
        for child in parent.children:
            parent_by_id[child.id] = parent.id

    domains: dict[str, ControlledDomainAssignment] = {}
    sources: list[dict[str, Any]] = []
    for batch_index in range(1, 4):
        path = (
            source_run_dir
            / "hybrid_controlled_assignment"
            / f"batch-{batch_index:03d}"
            / "attempt-01"
            / "parsed-output.json"
        )
        output = HybridAssignmentOutput.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        for assignment in output.assignments:
            domains[assignment.content_id] = assignment.domain.model_copy(deep=True)
        sources.append(
            {
                "batch_id": f"batch-{batch_index:03d}",
                "source": "accepted_parsed_output",
                "path": str(path),
                "sha256": _hash_file(path),
            }
        )

    batch4_path = (
        source_run_dir
        / "hybrid_controlled_assignment"
        / "batch-004"
        / "attempt-01"
        / "repair-raw-response.txt"
    )
    batch4 = json.loads(batch4_path.read_text(encoding="utf-8"))
    assignments = batch4.get("assignments")
    if not isinstance(assignments, list):
        raise PipelineError(
            "Run #20 Batch 4 缺少可冻结 Domain",
            code="completion_domain_source_invalid",
            retryable=False,
        )
    for value in assignments:
        if not isinstance(value, dict) or not isinstance(value.get("content_id"), str):
            raise PipelineError(
                "Run #20 Batch 4 Domain 血缘无效",
                code="completion_domain_source_invalid",
                retryable=False,
            )
        domain = ControlledDomainAssignment.model_validate(value.get("domain"))
        domain.primary_path = _canonical_domain_path(
            domain.primary_path, parent_by_id
        )
        domain.secondary_paths = [
            _canonical_domain_path(path, parent_by_id)
            for path in domain.secondary_paths
        ]
        _validate_domain_path(domain.primary_path, parent_by_id)
        for path in domain.secondary_paths:
            _validate_domain_path(path, parent_by_id)
        domains[value["content_id"]] = domain
    sources.append(
        {
            "batch_id": "batch-004",
            "source": "failed_repair_domain_only",
            "path": str(batch4_path),
            "sha256": _hash_file(batch4_path),
        }
    )

    if set(domains) != set(selected_ids) or len(domains) != len(selected_ids):
        raise PipelineError(
            "冻结 Domain 未完整覆盖相同 48 条",
            code="completion_domain_coverage_mismatch",
            retryable=False,
        )
    return domains, {
        "version": DOMAIN_COMBINATION_VERSION,
        "assignment_count": len(domains),
        "sources": sources,
        "domains": {
            content_id: domains[content_id].model_dump(mode="json")
            for content_id in selected_ids
        },
    }


def build_completion_derived_filters(
    assignments: list[HybridControlledAssignment],
    registry: ControlledVocabularyRegistry,
) -> list[dict[str, Any]]:
    supports: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for assignment in assignments:
        form_ids = [assignment.presentation_form.primary]
        if assignment.presentation_form.secondary:
            form_ids.append(assignment.presentation_form.secondary)
        for form_id in form_ids:
            if form_id == "unknown":
                continue
            for object_value in assignment.object_types:
                supports[("focus_object_type", form_id, object_value.id)].add(
                    assignment.content_id
                )
            for context in assignment.suggested_use_contexts:
                supports[("suggested_use_context", form_id, context.id)].add(
                    assignment.content_id
                )
    proposals: list[dict[str, Any]] = []
    for (facet, form_id, value_id), content_ids in sorted(supports.items()):
        if len(content_ids) < 3:
            continue
        proposals.append(
            {
                "id": f"DF_{form_id}_{value_id}",
                "display_name": (
                    f"{registry.term(form_id).canonical_name} · "
                    f"{registry.term(value_id).canonical_name}"
                ),
                "expression": {
                    "presentation_form": [form_id],
                    facet: [value_id],
                },
                "support_count": len(content_ids),
                "supporting_content_ids": sorted(content_ids),
                "status": "report_only",
            }
        )
    return proposals


def build_completion_dynamic_faceting(
    assignments: list[HybridControlledAssignment],
    registry: ControlledVocabularyRegistry,
    domain_draft: TopLevelDomainDraft,
) -> dict[str, Any]:
    """Simulate real progressive clicks without enumerating a Cartesian product."""

    dynamic = build_dynamic_faceting(assignments, registry)
    records = _facet_records(assignments)
    top_level_domain_ids = {domain.id for domain in domain_draft.domains}
    global_options = _available_options(records, set(records))
    supported_domains = sorted(
        top_level_domain_ids & set(global_options["domain"])
    )
    first_steps: list[dict[str, Any]] = []
    second_steps: list[dict[str, Any]] = []
    third_steps: list[dict[str, Any]] = []

    def step(selections: dict[str, list[str]], result: set[str]) -> dict[str, Any]:
        return {
            "selections": selections,
            "result_count": len(result),
            "content_ids": sorted(result),
            "available_options": _available_options(records, result),
        }

    for domain_id in supported_domains:
        domain_result = _query(records, {"domain": {domain_id}})
        first = step({"domain": [domain_id]}, domain_result)
        first_steps.append(first)
        second_candidates: list[tuple[str, str]] = []
        second_candidates.extend(
            ("presentation_form", value)
            for value in sorted(first["available_options"]["presentation_form"])
        )
        second_candidates.extend(
            ("focus_object_type", value)
            for value in sorted(first["available_options"]["focus_object_type"])
        )
        for facet, value in second_candidates:
            selections = {"domain": [domain_id], facet: [value]}
            second_result = _query(
                records, {"domain": {domain_id}, facet: {value}}
            )
            second = step(selections, second_result)
            second_steps.append(second)
            if len(second_result) < 2:
                continue
            remaining_facets = (
                ("focus_object_type", "suggested_use_context")
                if facet == "presentation_form"
                else ("presentation_form", "suggested_use_context")
            )
            for third_facet in remaining_facets:
                for third_value in sorted(
                    second["available_options"][third_facet]
                ):
                    third_selections = {
                        **selections,
                        third_facet: [third_value],
                    }
                    query = {
                        key: set(values) for key, values in third_selections.items()
                    }
                    third_result = _query(records, query)
                    if third_result:
                        third_steps.append(step(third_selections, third_result))

    exposed_zero = sum(
        count == 0
        for steps in (first_steps, second_steps, third_steps)
        for item in steps
        for values in item["available_options"].values()
        for count in values.values()
    )
    second_counts = [item["result_count"] for item in second_steps]
    first_counts = [item["result_count"] for item in first_steps]
    dynamic["click_path_simulation"] = {
        "strategy": "supported_domain_then_form_or_object_then_remaining_facet",
        "first_steps": first_steps,
        "second_steps": second_steps,
        "third_steps": third_steps,
    }
    dynamic["metrics"].update(
        {
            "first_result_median": _median(first_counts),
            "first_available_form_median": _median(
                [
                    len(item["available_options"]["presentation_form"])
                    for item in first_steps
                ]
            ),
            "first_available_object_median": _median(
                [
                    len(item["available_options"]["focus_object_type"])
                    for item in first_steps
                ]
            ),
            "first_available_context_median": _median(
                [
                    len(item["available_options"]["suggested_use_context"])
                    for item in first_steps
                ]
            ),
            "second_result_median": _median(second_counts),
            "second_singleton_ratio": round(
                sum(value == 1 for value in second_counts) / len(second_counts), 4
            )
            if second_counts
            else 0,
            "second_refinable_ratio": round(
                sum(
                    any(
                        item["available_options"][facet]
                        for facet in (
                            "presentation_form",
                            "focus_object_type",
                            "suggested_use_context",
                        )
                    )
                    for item in second_steps
                )
                / len(second_steps),
                4,
            )
            if second_steps
            else 0,
            "exposed_zero_option_count": exposed_zero,
            "simulated_first_path_count": len(first_steps),
            "simulated_second_path_count": len(second_steps),
            "simulated_third_path_count": len(third_steps),
        }
    )
    return dynamic


def _median(values: list[int]) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return round((ordered[middle - 1] + ordered[middle]) / 2, 3)


def build_completion_metrics(
    *,
    assignments: list[HybridControlledAssignment],
    entity_mappings: dict[str, list[EntityObjectMapping]],
    dynamic: dict[str, Any],
    normalization_events: list[dict[str, Any]],
) -> dict[str, Any]:
    form_primary = Counter(
        assignment.presentation_form.primary for assignment in assignments
    )
    form_secondary = Counter(
        assignment.presentation_form.secondary
        for assignment in assignments
        if assignment.presentation_form.secondary
    )
    object_support = Counter(
        item.id for assignment in assignments for item in assignment.object_types
    )
    context_support = Counter(
        item.id
        for assignment in assignments
        for item in assignment.suggested_use_contexts
    )
    context_confidence = Counter(
        item.confidence
        for assignment in assignments
        for item in assignment.suggested_use_contexts
    )
    assigned_entities = {
        (assignment.content_id, entity)
        for assignment in assignments
        for item in assignment.object_types
        for entity in item.source_entities
    }
    untyped_entities = {
        (content_id, mapping.source_entity)
        for content_id, mappings in entity_mappings.items()
        for mapping in mappings
        if mapping.mapping_status == "untyped"
    }
    deterministic_count = sum(
        item.mapping_source == "deterministic"
        for assignment in assignments
        for item in assignment.object_types
    )
    model_assisted_count = sum(
        item.mapping_source == "model_assisted"
        for assignment in assignments
        for item in assignment.object_types
    )
    form_novelty = sum(
        proposal.facet == "presentation_form"
        for assignment in assignments
        for proposal in assignment.facet_novelty
    )
    object_novelty = sum(
        proposal.facet == "focus_object_type"
        for assignment in assignments
        for proposal in assignment.facet_novelty
    )
    context_novelty = sum(
        proposal.facet == "suggested_use_context"
        for assignment in assignments
        for proposal in assignment.facet_novelty
    )
    total = len(assignments)
    return {
        "assignment_count": total,
        "presentation_form": {
            "primary_distribution": dict(sorted(form_primary.items())),
            "secondary_distribution": dict(sorted(form_secondary.items())),
            "unknown_count": form_primary.get("unknown", 0),
            "secondary_count": sum(form_secondary.values()),
            "maximum_primary_coverage_ratio": round(
                max(form_primary.values(), default=0) / total, 4
            )
            if total
            else 0,
        },
        "focus_object_type": {
            "support": dict(sorted(object_support.items())),
            "empty_count": sum(not item.object_types for item in assignments),
            "empty_rate": round(
                sum(not item.object_types for item in assignments) / total, 4
            )
            if total
            else 1,
            "average_per_content": round(
                sum(len(item.object_types) for item in assignments) / total, 3
            )
            if total
            else 0,
            "deterministic_entity_mapping_count": deterministic_count,
            "model_assisted_object_assignment_count": model_assisted_count,
            "untyped_entity_count": len(untyped_entities),
            "untyped_entity_with_no_object_count": len(
                untyped_entities - assigned_entities
            ),
        },
        "suggested_use_context": {
            "support": dict(sorted(context_support.items())),
            "confidence": dict(sorted(context_confidence.items())),
            "empty_count": sum(
                not item.suggested_use_contexts for item in assignments
            ),
            "empty_rate": round(
                sum(not item.suggested_use_contexts for item in assignments) / total,
                4,
            )
            if total
            else 1,
            "average_per_content": round(
                sum(len(item.suggested_use_contexts) for item in assignments) / total,
                3,
            )
            if total
            else 0,
        },
        "novelty": {
            "presentation_form": form_novelty,
            "focus_object_type": object_novelty,
            "suggested_use_context": context_novelty,
        },
        "normalization": {
            "event_count": len(normalization_events),
            "duplicate_object_merge_count": sum(
                event.get("operation") == "merge_duplicate_object_type_v1"
                for event in normalization_events
            ),
            "overflow_candidate_count": sum(
                len(event.get("overflow_object_type_candidates") or [])
                for event in normalization_events
                if event.get("operation") == OBJECT_OVERFLOW_PROTOCOL_VERSION
            ),
        },
        "dynamic": dynamic["metrics"],
    }


def build_completion_quality_gate(
    *,
    assignments: list[HybridControlledAssignment],
    registry: ControlledVocabularyRegistry,
    dynamic: dict[str, Any],
    source_domain_hash: str,
    current_domain_hash: str,
    source_vocabulary_hashes: dict[str, str],
    current_vocabulary_hashes: dict[str, str],
    manifest_inputs: list[str],
    historical_tree_hashes: dict[str, str],
    current_historical_tree_hashes: dict[str, str],
    model_output_forbidden_field_count: int,
    audit_metrics: dict[str, int | float] | None = None,
) -> ControlledQualityResult:
    base = build_quality_gate(
        assignments=assignments,
        registry=registry,
        dynamic=dynamic,
        source_domain_hash=source_domain_hash,
        current_domain_hash=current_domain_hash,
        source_vocabulary_hashes=source_vocabulary_hashes,
        current_vocabulary_hashes=current_vocabulary_hashes,
        manifest_inputs=manifest_inputs,
        historical_manifest_hashes=historical_tree_hashes,
        current_historical_hashes=current_historical_tree_hashes,
    )
    blocking = list(base.blocking_issues)
    warnings = list(base.warnings)
    if len(assignments) != 48:
        blocking.append(
            {"code": "completion_assignment_incomplete", "details": [len(assignments)]}
        )
    if model_output_forbidden_field_count:
        blocking.append(
            {
                "code": "model_output_contains_forbidden_domain",
                "details": [model_output_forbidden_field_count],
            }
        )
    if assignments and all(item.suggested_use_contexts for item in assignments):
        blocking.append({"code": "suggested_context_forced_filled", "details": [48]})
    audit_metrics = dict(audit_metrics or {})
    warning_fields = {
        "repair_call_count": "模型阶段发生 JSON Repair",
        "repair_semantic_change_count": "Repair 含语义选择或增删",
        "untyped_entity_count": "仍有未类型化 Entity",
        "model_assisted_object_assignment_count": "Object Type 依赖模型辅助赋值",
        "overflow_candidate_count": "Object Type 存在预算外候选",
    }
    for field, message in warning_fields.items():
        value = audit_metrics.get(field, 0)
        if isinstance(value, (int, float)) and value > 0:
            warnings.append({"code": field, "details": [value, message]})
    return ControlledQualityResult(
        passed=not blocking,
        blocking_issues=blocking,
        warnings=warnings,
        metrics={
            **base.metrics,
            "completion_gate_version": COMPLETION_GATE_VERSION,
            "model_output_forbidden_field_count": model_output_forbidden_field_count,
            "repair_call_count": audit_metrics.get("repair_call_count", 0),
            "repair_rate": audit_metrics.get("repair_rate", 0),
            "repair_semantic_change_count": audit_metrics.get(
                "repair_semantic_change_count", 0
            ),
            "repair_syntax_only_count": audit_metrics.get(
                "repair_syntax_only_count", 0
            ),
            "untyped_entity_count": audit_metrics.get("untyped_entity_count", 0),
            "deterministic_entity_mapping_count": audit_metrics.get(
                "deterministic_entity_mapping_count", 0
            ),
            "model_assisted_object_assignment_count": audit_metrics.get(
                "model_assisted_object_assignment_count", 0
            ),
            "overflow_candidate_count": audit_metrics.get(
                "overflow_candidate_count", 0
            ),
        },
    )


def _tree_hash(path: Path) -> str:
    files = sorted(value for value in path.rglob("*") if value.is_file())
    return _stable_hash(
        [
            {"path": str(value.relative_to(path)), "sha256": _hash_file(value)}
            for value in files
        ]
    )


def _historical_db_state(
    run_repository: TaxonomyRunRepository, run_ids: tuple[int, ...]
) -> dict[str, Any]:
    return {
        str(run_id): {
            "run": run_repository.get_run(run_id),
            "stages": run_repository.list_stages(run_id),
        }
        for run_id in run_ids
    }


class ControlledFacetCompletionService:
    def __init__(
        self,
        *,
        repository: TaxonomyRepository,
        run_repository: TaxonomyRunRepository,
        provider_factory: Callable[[str], OpenAICompatibleProvider],
        output_dir: Path,
        profile_output_dir: Path,
        vocabulary_dir: Path | None = None,
    ) -> None:
        self.repository = repository
        self.run_repository = run_repository
        self.provider_factory = provider_factory
        self.output_dir = output_dir
        self.profile_output_dir = profile_output_dir
        self.vocabulary_dir = vocabulary_dir

    def create_completion(
        self,
        *,
        source_run_id: int = 20,
    ) -> int:
        source_run = self.run_repository.get_run(source_run_id)
        if (
            not source_run
            or source_run.get("run_kind") != "hybrid_controlled_facets_spike"
            or source_run.get("status") not in {"retry_wait", "failed"}
        ):
            raise PipelineError(
                "Completion 必须派生自冻结的失败 Hybrid Run",
                code="completion_source_invalid",
                retryable=False,
            )
        source_protocol = source_run["parameters"]["protocol_manifest"]
        snapshot_id = int(source_protocol["snapshot_id"])
        snapshot = self.repository.get_snapshot(snapshot_id)
        if not snapshot or snapshot["snapshot_hash"] != source_protocol["snapshot_hash"]:
            raise PipelineError(
                "Completion Snapshot 来源无效",
                code="completion_snapshot_invalid",
                retryable=False,
            )
        source_run_dir = self.output_dir / f"run-{source_run_id:06d}"
        source_stage_rows = {
            row["unit_key"]: row
            for row in self.run_repository.list_stages(source_run_id)
            if row["stage_name"] == "hybrid_controlled_assignment"
        }
        if any(
            source_stage_rows.get(f"batch-{index:03d}", {}).get("status")
            != "completed"
            for index in range(1, 4)
        ):
            raise PipelineError(
                "Run #20 前三批不满足复用条件",
                code="completion_reuse_source_incomplete",
                retryable=False,
            )
        if source_stage_rows.get("batch-004", {}).get("status") not in {
            "retry_wait",
            "failed",
        }:
            raise PipelineError(
                "Run #20 Batch 4 不是冻结失败状态",
                code="completion_batch4_source_invalid",
                retryable=False,
            )

        registry = load_controlled_vocabularies(self.vocabulary_dir)
        git_commit, clean = _git_state()
        if not clean:
            raise PipelineError(
                "创建 Completion Run 前 Git 必须干净",
                code="completion_git_dirty",
                retryable=False,
            )
        selected_ids = list(source_protocol["selected_ids"])
        if len(selected_ids) != 48 or len(set(selected_ids)) != 48:
            raise PipelineError(
                "Completion 必须使用相同 48 条",
                code="completion_sample_invalid",
                retryable=False,
            )
        historical_ids = (18, 19, 20)
        providers = {
            role: _provider_manifest(self.provider_factory(role))
            for role in ("taxonomy_assignment", "taxonomy_repair")
        }
        protocol = {
            "protocol_version": COMPLETION_PROTOCOL_VERSION,
            "created_at": _utc_now(),
            "source_run_id": source_run_id,
            "snapshot_id": snapshot_id,
            "snapshot_hash": snapshot["snapshot_hash"],
            "domain_run_id": int(source_protocol["domain_run_id"]),
            "sample_profile_run_id": source_protocol["sample_profile_run_id"],
            "selected_ids": selected_ids,
            "evidence_counts": source_protocol["evidence_counts"],
            "source_protocol_hash": _stable_hash(source_protocol),
            "source_tree_hashes": {
                f"run-{run_id:06d}": _tree_hash(
                    self.output_dir / f"run-{run_id:06d}"
                )
                for run_id in historical_ids
            },
            "source_db_state_hash": _stable_hash(
                _historical_db_state(self.run_repository, historical_ids)
            ),
            "source_artifact_hashes": source_protocol["source_artifact_hashes"],
            "vocabulary_hashes": registry.hashes,
            "entity_mapping_version": ENTITY_MAPPING_VERSION,
            "historical_adapter_version": HISTORICAL_ADAPTER_VERSION,
            "object_normalization_version": OBJECT_NORMALIZATION_VERSION,
            "domain_combination_version": DOMAIN_COMBINATION_VERSION,
            "model_schema_version": MODEL_SCHEMA_VERSION,
            "model_prompt_version": MODEL_PROMPT_VERSION,
            "dynamic_faceting_version": DYNAMIC_FACETING_VERSION,
            "quality_gate_version": COMPLETION_GATE_VERSION,
            "providers": providers,
            "git_commit": git_commit,
            "git_worktree_clean": True,
            "reuse_batches": ["batch-001", "batch-002", "batch-003"],
            "provider_batches": ["batch-004"],
            "assignment_inputs": [
                "Snapshot #2 compact_form_view_v1",
                "accepted 48-item classification_profile_v1",
                "Run #12 Domain Draft as readonly context",
                "Run #20 frozen per-card Domain decisions",
                "controlled vocabulary v1",
                "current Entity whitelist",
            ],
            "forbidden_inputs": [
                "Silver Reference",
                "Run #17 open vocabulary",
                "old Candidate Decision correctness claims",
            ],
        }
        run_id = self.run_repository.create_run(
            snapshot_id=snapshot_id,
            run_kind="hybrid_controlled_facets_completion",
            engine="hybrid_controlled_facets_completion",
            engine_version=COMPLETION_ENGINE_VERSION,
            parameters={
                "snapshot_hash": snapshot["snapshot_hash"],
                "protocol_manifest": protocol,
            },
        )
        _write_json_once(
            self.output_dir / f"run-{run_id:06d}" / "run-manifest.json",
            protocol,
        )
        return run_id

    def status(self, run_id: int) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if not run:
            raise LookupError("Taxonomy Run 不存在")
        return {"run": run, "stages": self.run_repository.list_stages(run_id)}

    def execute(self, run_id: int, *, resume: bool = False) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if (
            not run
            or run.get("run_kind") != "hybrid_controlled_facets_completion"
            or run.get("engine_version") != COMPLETION_ENGINE_VERSION
        ):
            raise PipelineError(
                "不是 Controlled Facet Completion Run",
                code="completion_run_invalid",
                retryable=False,
            )
        if run["status"] in {"completed", "quality_failed"}:
            return self.status(run_id)
        protocol = run["parameters"]["protocol_manifest"]
        run_dir = self.output_dir / f"run-{run_id:06d}"
        if json.loads(
            (run_dir / "run-manifest.json").read_text(encoding="utf-8")
        ) != protocol:
            raise PipelineError(
                "Completion Manifest 改变",
                code="completion_manifest_changed",
                retryable=False,
            )
        commit, clean = _git_state()
        if commit != protocol["git_commit"] or not clean:
            raise PipelineError(
                "Completion 执行代码状态改变",
                code="completion_code_state_changed",
                retryable=False,
            )
        self._verify_historical_sources(protocol)

        registry = load_controlled_vocabularies(self.vocabulary_dir)
        if registry.hashes != protocol["vocabulary_hashes"]:
            raise PipelineError(
                "Completion 受控词表改变",
                code="completion_vocabulary_changed",
                retryable=False,
            )
        source_run_dir = self.output_dir / f"run-{int(protocol['source_run_id']):06d}"
        domain_run_dir = self.output_dir / f"run-{int(protocol['domain_run_id']):06d}"
        profile_dir = self.profile_output_dir / str(protocol["sample_profile_run_id"])
        paths = {
            "domain_draft": domain_run_dir / "taxonomy-draft.json",
            "compact_corpus": domain_run_dir / "compact-corpus.json",
            "profile_manifest": profile_dir / "manifest.json",
            "profile_view": profile_dir / "profile-discovery-view.jsonl",
        }
        if {
            key: _hash_file(path) for key, path in paths.items()
        } != protocol["source_artifact_hashes"]:
            raise PipelineError(
                "Completion 冻结来源改变",
                code="completion_source_changed",
                retryable=False,
            )
        domain_draft = TopLevelDomainDraft.model_validate_json(
            paths["domain_draft"].read_text(encoding="utf-8")
        )
        compact = json.loads(paths["compact_corpus"].read_text(encoding="utf-8"))
        compact_by_id = {str(row[0]): row for row in compact["rows"]}
        profile_rows = [
            json.loads(line)
            for line in paths["profile_view"].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        profile_by_id = {str(row[0]): row for row in profile_rows}
        selected_ids = list(protocol["selected_ids"])
        if not set(selected_ids) <= set(compact_by_id) or not set(
            selected_ids
        ) <= set(profile_by_id):
            raise PipelineError(
                "Completion 48 条视图血缘改变",
                code="completion_sample_changed",
                retryable=False,
            )
        rows: dict[str, dict[str, Any]] = {}
        mapping_by_id: dict[str, list[EntityObjectMapping]] = {}
        for content_id in selected_ids:
            compact_row = compact_by_id[content_id]
            profile_row = profile_by_id[content_id]
            entities = list(profile_row[6])
            mapping_by_id[content_id] = map_entities_to_object_types(
                entities, registry
            )
            rows[content_id] = {
                "content_id": content_id,
                "evidence_level": compact_row[1],
                "compact_form_view": compact_row,
                "classification_profile_v1": profile_row,
                "entities": entities,
            }
        _write_json(
            run_dir / "entity-object-mappings.json",
            {
                "version": ENTITY_MAPPING_VERSION,
                "contents": {
                    content_id: [
                        mapping.model_dump(mode="json") for mapping in mappings
                    ]
                    for content_id, mappings in mapping_by_id.items()
                },
            },
        )

        frozen_domains, domain_lineage = extract_frozen_domains(
            source_run_dir=source_run_dir,
            selected_ids=selected_ids,
            domain_draft=domain_draft,
        )
        self._deterministic_stage(
            run_id,
            "freeze_domain_assignments",
            {
                "source_run_tree": protocol["source_tree_hashes"][
                    f"run-{int(protocol['source_run_id']):06d}"
                ]
            },
            run_dir / "frozen-domain-assignments.json",
            domain_lineage,
            DOMAIN_COMBINATION_VERSION,
        )

        assignments: list[HybridControlledAssignment] = []
        normalization_events: list[dict[str, Any]] = []
        reuse_lineage: list[dict[str, Any]] = []
        for batch_index in range(1, 4):
            batch_ids = selected_ids[(batch_index - 1) * 12 : batch_index * 12]
            source_path = (
                source_run_dir
                / "hybrid_controlled_assignment"
                / f"batch-{batch_index:03d}"
                / "attempt-01"
                / "parsed-output.json"
            )
            source_output = HybridAssignmentOutput.model_validate_json(
                source_path.read_text(encoding="utf-8")
            )
            adapted, adapter_audit = adapt_historical_batch(
                source_output,
                expected_ids=batch_ids,
                entity_mappings={key: mapping_by_id[key] for key in batch_ids},
                timestamp=protocol["created_at"],
            )
            self._validate_final_batch(
                adapted,
                expected_ids=batch_ids,
                domain_draft=domain_draft,
                registry=registry,
                entity_mappings={key: mapping_by_id[key] for key in batch_ids},
            )
            batch_dir = run_dir / "reused_batches" / f"batch-{batch_index:03d}"
            output_path = batch_dir / "adapted-output.json"
            audit_path = batch_dir / "adapter-audit.json"
            output_value = {
                "version": ASSIGNMENT_SCHEMA_VERSION,
                "assignments": [
                    assignment.model_dump(mode="json") for assignment in adapted
                ],
            }
            adapter_audit.update(
                {
                    "source_run_id": int(protocol["source_run_id"]),
                    "source_path": str(source_path),
                    "source_hash": _hash_file(source_path),
                    "output_semantic_hash": _stable_hash(output_value),
                    "provider_call_count": 0,
                }
            )
            _write_json(output_path, output_value)
            _write_json(audit_path, adapter_audit)
            input_hash = _stable_hash(
                {
                    "source_hash": _hash_file(source_path),
                    "adapter_version": HISTORICAL_ADAPTER_VERSION,
                    "batch_ids": batch_ids,
                }
            )
            self.run_repository.record_reused_stage(
                run_id,
                "controlled_facet_assignment",
                f"batch-{batch_index:03d}",
                input_hash=input_hash,
                output_path=str(output_path),
                output_hash=_hash_file(output_path),
                model=None,
                prompt_version=HISTORICAL_ADAPTER_VERSION,
                thinking_enabled=None,
                reasoning_effort=None,
            )
            assignments.extend(adapted)
            normalization_events.extend(adapter_audit["operations"])
            reuse_lineage.append(
                {
                    "batch_id": f"batch-{batch_index:03d}",
                    "source_hash": _hash_file(source_path),
                    "output_hash": _hash_file(output_path),
                    "adapter_audit_hash": _hash_file(audit_path),
                    "provider_call_count": 0,
                }
            )

        batch4_ids = selected_ids[36:48]
        batch4_mappings = {key: mapping_by_id[key] for key in batch4_ids}
        batch4_output, batch4_events, batch4_call_audit = self._execute_batch4(
            run_id=run_id,
            run_dir=run_dir,
            rows=[rows[key] for key in batch4_ids],
            expected_ids=batch4_ids,
            domain_draft=domain_draft,
            frozen_domains={key: frozen_domains[key] for key in batch4_ids},
            registry=registry,
            entity_mappings=batch4_mappings,
            timestamp=protocol["created_at"],
        )
        assignments.extend(batch4_output)
        normalization_events.extend(batch4_events)
        assignments.sort(key=lambda item: selected_ids.index(item.content_id))
        if [item.content_id for item in assignments] != selected_ids:
            raise PipelineError(
                "Completion 未完整保持相同 48 条顺序",
                code="completion_assignment_order_invalid",
                retryable=False,
            )
        for index in range(0, 48, 12):
            batch = assignments[index : index + 12]
            batch_ids = selected_ids[index : index + 12]
            self._validate_final_batch(
                batch,
                expected_ids=batch_ids,
                domain_draft=domain_draft,
                registry=registry,
                entity_mappings={key: mapping_by_id[key] for key in batch_ids},
            )

        assignment_payload = {
            "version": ASSIGNMENT_SCHEMA_VERSION,
            "assignments": [
                assignment.model_dump(mode="json") for assignment in assignments
            ],
        }
        _write_json(run_dir / "controlled-facet-assignments.json", assignment_payload)
        _write_json(
            run_dir / "normalization-audit.json",
            {
                "version": OBJECT_NORMALIZATION_VERSION,
                "events": normalization_events,
                "silent_normalization_count": 0,
            },
        )
        _write_json(
            run_dir / "reuse-lineage.json",
            {
                "adapter_version": HISTORICAL_ADAPTER_VERSION,
                "source_run_id": int(protocol["source_run_id"]),
                "reused_content_count": 36,
                "provider_call_count": 0,
                "batches": reuse_lineage,
            },
        )
        _write_json(
            run_dir / "domain-combination-lineage.json",
            {
                "version": DOMAIN_COMBINATION_VERSION,
                "domain_source_hash": _hash_file(
                    run_dir / "frozen-domain-assignments.json"
                ),
                "model_output_domain_field_count": 0,
                "combined_content_count": 48,
            },
        )
        novelty = [
            proposal.model_dump(mode="json")
            for assignment in assignments
            for proposal in assignment.facet_novelty
        ]
        _write_json(
            run_dir / "facet-novelty-proposals.json",
            {"proposals": novelty, "runtime_promotion_count": 0},
        )
        dynamic = build_completion_dynamic_faceting(
            assignments, registry, domain_draft
        )
        self._deterministic_stage(
            run_id,
            "dynamic_faceting",
            assignment_payload,
            run_dir / "dynamic-faceting.json",
            dynamic,
            DYNAMIC_FACETING_VERSION,
        )
        derived = build_completion_derived_filters(assignments, registry)
        self._deterministic_stage(
            run_id,
            "derived_filter_proposals",
            {"assignment_hash": _stable_hash(assignment_payload)},
            run_dir / "derived-filter-proposals.json",
            {"version": DERIVED_FILTER_VERSION, "proposals": derived},
            DERIVED_FILTER_VERSION,
        )
        metrics = build_completion_metrics(
            assignments=assignments,
            entity_mappings=mapping_by_id,
            dynamic=dynamic,
            normalization_events=normalization_events,
        )
        _write_json(run_dir / "completion-metrics.json", metrics)

        self._verify_historical_sources(protocol)
        current_tree_hashes = {
            key: _tree_hash(self.output_dir / key)
            for key in protocol["source_tree_hashes"]
        }
        quality = build_completion_quality_gate(
            assignments=assignments,
            registry=registry,
            dynamic=dynamic,
            source_domain_hash=protocol["source_artifact_hashes"]["domain_draft"],
            current_domain_hash=_hash_file(paths["domain_draft"]),
            source_vocabulary_hashes=protocol["vocabulary_hashes"],
            current_vocabulary_hashes=registry.hashes,
            manifest_inputs=protocol["assignment_inputs"],
            historical_tree_hashes=protocol["source_tree_hashes"],
            current_historical_tree_hashes=current_tree_hashes,
            model_output_forbidden_field_count=0,
        )
        self._deterministic_stage(
            run_id,
            "checkpoint311b_quality_gate",
            {
                "assignment_hash": _stable_hash(assignment_payload),
                "dynamic_hash": _stable_hash(dynamic),
                "metrics_hash": _stable_hash(metrics),
            },
            run_dir / "checkpoint311b-quality-gate" / "quality-result.json",
            quality.model_dump(mode="json"),
            COMPLETION_GATE_VERSION,
        )
        reviewer_bundle = {
            "version": COMPLETION_REVIEWER_BUNDLE_VERSION,
            "lineage": {
                "source_run_id": int(protocol["source_run_id"]),
                "source_tree_hashes": protocol["source_tree_hashes"],
                "snapshot_hash": protocol["snapshot_hash"],
                "domain_run_id": protocol["domain_run_id"],
                "vocabulary_hashes": protocol["vocabulary_hashes"],
                "reused_content_count": 36,
                "provider_content_count": 12,
            },
            "normalization_audit": {
                "path": "normalization-audit.json",
                "sha256": _hash_file(run_dir / "normalization-audit.json"),
            },
            "reuse_lineage": reuse_lineage,
            "batch4_call_audit": batch4_call_audit,
            "assignments": assignment_payload,
            "metrics": metrics,
            "dynamic_faceting": dynamic,
            "novelty_proposals": novelty,
            "derived_filter_proposals": derived,
            "automatic_gate": quality.model_dump(mode="json"),
            "excluded": [
                "Silver Reference",
                "Run #17 open vocabulary",
                "old Candidate Decision correctness claims",
                "raw Provider prompts and responses",
            ],
        }
        _write_json(run_dir / "independent-reviewer-bundle.json", reviewer_bundle)
        _write_json(
            run_dir / "checkpoint311b-lineage.json",
            {
                "protocol_hash": _stable_hash(protocol),
                "source_tree_hashes": protocol["source_tree_hashes"],
                "outputs": {
                    "assignments": _hash_file(
                        run_dir / "controlled-facet-assignments.json"
                    ),
                    "normalization": _hash_file(
                        run_dir / "normalization-audit.json"
                    ),
                    "dynamic": _hash_file(run_dir / "dynamic-faceting.json"),
                    "novelty": _hash_file(
                        run_dir / "facet-novelty-proposals.json"
                    ),
                    "derived": _hash_file(
                        run_dir / "derived-filter-proposals.json"
                    ),
                    "metrics": _hash_file(run_dir / "completion-metrics.json"),
                    "quality": _hash_file(
                        run_dir
                        / "checkpoint311b-quality-gate"
                        / "quality-result.json"
                    ),
                },
                "created_at": protocol["created_at"],
            },
        )
        self.run_repository.set_run_status(
            run_id,
            "completed" if quality.passed else "quality_failed",
            current_stage="checkpoint311b_quality_gate",
            error_code=None if quality.passed else "completion_quality_failed",
            error_message=None
            if quality.passed
            else "Checkpoint 3.11B automated gate failed",
        )
        return self.status(run_id)

    def _execute_batch4(
        self,
        *,
        run_id: int,
        run_dir: Path,
        rows: list[dict[str, Any]],
        expected_ids: list[str],
        domain_draft: TopLevelDomainDraft,
        frozen_domains: dict[str, ControlledDomainAssignment],
        registry: ControlledVocabularyRegistry,
        entity_mappings: dict[str, list[EntityObjectMapping]],
        timestamp: str,
    ) -> tuple[list[HybridControlledAssignment], list[dict[str, Any]], dict[str, Any]]:
        prompt = build_completion_prompt(
            rows=rows,
            domain_draft=domain_draft,
            registry=registry,
            entity_mappings=entity_mappings,
        )
        schema_hint = build_completion_repair_hint(
            expected_ids=expected_ids,
            entity_mappings=entity_mappings,
            registry=registry,
        )
        budget = build_budget_preflight(
            stage_name="controlled_facet_completion_batch_004",
            complexity_count=len(expected_ids),
            schema_hint_characters=len(schema_hint),
            historical_completion_tokens=None,
            technical_max_tokens=8192,
            safety_margin_ratio=0.25,
            base_tokens=2048,
            tokens_per_item=256,
        )
        require_safe_budget(budget)
        _write_json(
            run_dir / "budget-preflight" / "assignment-004.json",
            budget.model_dump(mode="json"),
        )
        input_hash = _hash_text(prompt)
        stage = self.run_repository.ensure_stage(
            run_id,
            "controlled_facet_assignment",
            "batch-004",
            input_hash=input_hash,
        )
        output_path = run_dir / "controlled_facet_assignment" / "batch-004" / "normalized-output.json"
        normalization_path = run_dir / "controlled_facet_assignment" / "batch-004" / "normalization-audit.json"
        if stage["status"] == "completed":
            output = HybridAssignmentOutput.model_validate_json(
                output_path.read_text(encoding="utf-8")
            )
            audit = json.loads(normalization_path.read_text(encoding="utf-8"))
            self._validate_final_batch(
                output.assignments,
                expected_ids=expected_ids,
                domain_draft=domain_draft,
                registry=registry,
                entity_mappings=entity_mappings,
            )
            return output.assignments, audit["events"], audit["call_audit"]
        if int(stage["attempt_count"]) >= 2:
            raise PipelineError(
                "Batch 4 已用完两次主调用额度",
                code="completion_batch4_attempts_exhausted",
                retryable=False,
            )
        previous = int(stage["attempt_count"])
        resume_existing = stage["status"] in {"processing", "retry_wait"} and previous > 0
        provider = self.provider_factory("taxonomy_assignment")
        repair_provider = self.provider_factory("taxonomy_repair")
        started = self.run_repository.start_stage(
            run_id,
            "controlled_facet_assignment",
            "batch-004",
            input_hash=input_hash,
            model=provider.model,
            prompt_version=MODEL_PROMPT_VERSION,
            thinking_enabled=provider.thinking_enabled,
            reasoning_effort=provider.reasoning_effort,
        )
        attempt = previous if resume_existing else int(started["attempt_count"])
        call_dir = (
            run_dir
            / "controlled_facet_assignment"
            / "batch-004"
            / f"attempt-{attempt:02d}"
        )

        def validator(value: ModelFacetOutput) -> None:
            normalized, _ = self._normalize_and_combine(
                value,
                expected_ids=expected_ids,
                frozen_domains=frozen_domains,
                entity_mappings=entity_mappings,
                domain_draft=domain_draft,
                registry=registry,
                timestamp=timestamp,
            )
            self._validate_final_batch(
                normalized,
                expected_ids=expected_ids,
                domain_draft=domain_draft,
                registry=registry,
                entity_mappings=entity_mappings,
            )

        caller = AuditedJsonCaller(
            provider=provider, repair_provider=repair_provider
        )
        try:
            model_output, call_audit = caller.call(
                call_dir=call_dir,
                prompt=prompt,
                prompt_version=MODEL_PROMPT_VERSION,
                schema=ModelFacetOutput,
                schema_hint=schema_hint,
                max_tokens=budget.allocated_max_tokens,
                input_ids=expected_ids,
                validator=validator,
                resume=call_dir.exists(),
            )
        except PipelineError as exc:
            self.run_repository.fail_stage(
                run_id,
                "controlled_facet_assignment",
                "batch-004",
                error_code=exc.code,
                error_message=str(exc),
                retryable=exc.retryable,
            )
            raise
        normalized, events = self._normalize_and_combine(
            model_output,
            expected_ids=expected_ids,
            frozen_domains=frozen_domains,
            entity_mappings=entity_mappings,
            domain_draft=domain_draft,
            registry=registry,
            timestamp=timestamp,
        )
        self._validate_final_batch(
            normalized,
            expected_ids=expected_ids,
            domain_draft=domain_draft,
            registry=registry,
            entity_mappings=entity_mappings,
        )
        output_value = HybridAssignmentOutput(assignments=normalized)
        _write_json(output_path, output_value.model_dump(mode="json"))
        normalization_audit = {
            "version": OBJECT_NORMALIZATION_VERSION,
            "events": events,
            "silent_normalization_count": 0,
            "model_output_schema": MODEL_SCHEMA_VERSION,
            "model_output_domain_field_count": 0,
            "call_audit": call_audit,
        }
        _write_json(normalization_path, normalization_audit)
        self.run_repository.complete_stage(
            run_id,
            "controlled_facet_assignment",
            "batch-004",
            output_path=str(output_path),
            output_hash=_hash_file(output_path),
            audit=_combined_audit(call_audit),
        )
        return normalized, events, call_audit

    def _normalize_and_combine(
        self,
        output: ModelFacetOutput,
        *,
        expected_ids: list[str],
        frozen_domains: dict[str, ControlledDomainAssignment],
        entity_mappings: dict[str, list[EntityObjectMapping]],
        domain_draft: TopLevelDomainDraft,
        registry: ControlledVocabularyRegistry,
        timestamp: str,
    ) -> tuple[list[HybridControlledAssignment], list[dict[str, Any]]]:
        by_id = {assignment.content_id: assignment for assignment in output.assignments}
        if list(by_id) != expected_ids or len(by_id) != len(expected_ids):
            raise PipelineError(
                "Batch 4 没有完整且唯一覆盖固定成员",
                code="completion_batch4_coverage_mismatch",
                retryable=False,
            )
        assignments: list[HybridControlledAssignment] = []
        events: list[dict[str, Any]] = []
        for content_id in expected_ids:
            normalized, item_events = normalize_model_assignment(
                by_id[content_id],
                allowed_entities={
                    mapping.source_entity for mapping in entity_mappings[content_id]
                },
                timestamp=timestamp,
            )
            assignments.append(
                combine_frozen_domain(normalized, frozen_domains[content_id])
            )
            events.extend(item_events)
        return assignments, events

    def _validate_final_batch(
        self,
        assignments: list[HybridControlledAssignment],
        *,
        expected_ids: list[str],
        domain_draft: TopLevelDomainDraft,
        registry: ControlledVocabularyRegistry,
        entity_mappings: dict[str, list[EntityObjectMapping]],
    ) -> None:
        output = HybridAssignmentOutput(assignments=assignments)
        validate_assignments(
            output,
            expected_ids=set(expected_ids),
            domain_draft=domain_draft,
            registry=registry,
            entity_mappings=entity_mappings,
        )
        if [item.content_id for item in output.assignments] != expected_ids:
            raise PipelineError(
                "严格校验后 Batch 顺序改变",
                code="completion_batch_order_changed",
                retryable=False,
            )

    def _verify_historical_sources(self, protocol: dict[str, Any]) -> None:
        current_tree_hashes = {
            key: _tree_hash(self.output_dir / key)
            for key in protocol["source_tree_hashes"]
        }
        if current_tree_hashes != protocol["source_tree_hashes"]:
            raise PipelineError(
                "Run #18–#20 运行产物改变",
                code="completion_historical_artifacts_changed",
                retryable=False,
            )
        current_db_hash = _stable_hash(
            _historical_db_state(self.run_repository, (18, 19, 20))
        )
        if current_db_hash != protocol["source_db_state_hash"]:
            raise PipelineError(
                "Run #18–#20 数据库状态改变",
                code="completion_historical_db_changed",
                retryable=False,
            )

    def _deterministic_stage(
        self,
        run_id: int,
        stage_name: str,
        input_value: Any,
        output_path: Path,
        output_value: Any,
        version: str,
    ) -> None:
        input_hash = _stable_hash(input_value)
        stage = self.run_repository.ensure_stage(
            run_id, stage_name, "main", input_hash=input_hash
        )
        if stage["status"] == "completed":
            if not output_path.is_file() or _hash_file(output_path) != stage["output_hash"]:
                raise PipelineError(
                    "Completion 确定性 Stage 产物改变",
                    code="completion_stage_changed",
                    retryable=False,
                )
            return
        self.run_repository.start_stage(
            run_id,
            stage_name,
            "main",
            input_hash=input_hash,
            model=None,
            prompt_version=version,
            thinking_enabled=None,
            reasoning_effort=None,
        )
        _write_json(output_path, output_value)
        self.run_repository.complete_stage(
            run_id,
            stage_name,
            "main",
            output_path=str(output_path),
            output_hash=_hash_file(output_path),
            audit={"elapsed_seconds": 0, "usage": {}},
        )
