from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from shiliu.taxonomy.discovery import ConsolidatedDraft, LocalDiscoveryOutput


class QualityIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    node_ids: list[str] = Field(default_factory=list)


class HierarchyFinding(QualityIssue):
    severity: Literal["blocking", "warning"]
    check: Literal[
        "parent_child_adequacy",
        "sibling_overlap",
        "granularity_consistency",
        "entity_leakage",
        "content_type_leakage",
        "node_support",
        "overbroad_domain",
        "overfine_subdomain",
        "missing_subdomain",
    ]


class HierarchyValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[HierarchyFinding]
    inspected_node_ids: list[str]
    summary: str


class TaxonomyQualityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    blocking_issues: list[QualityIssue]
    warnings: list[QualityIssue]
    retry_stage: Literal[
        "content_type_recovery", "consolidation", "hierarchy_validation"
    ] | None
    metrics: dict[str, int | float]


class TaxonomyQualityGate:
    """Deterministic structural gate plus an independent hierarchy report."""

    def evaluate(
        self,
        *,
        draft: ConsolidatedDraft,
        local_outputs: list[LocalDiscoveryOutput],
        allowed_ids: set[str],
        hierarchy_report: HierarchyValidationReport | None,
    ) -> TaxonomyQualityResult:
        blocking: list[QualityIssue] = []
        warnings: list[QualityIssue] = []
        local_content_types = [
            item for output in local_outputs for item in output.content_types
        ]
        local_subdomains = [
            item
            for output in local_outputs
            for item in output.domains
            if item.suggested_level == "subdomain"
        ]
        if not draft.content_types:
            blocking.append(
                QualityIssue(
                    code="content_types_missing",
                    message="Taxonomy Draft 没有独立 Content Type。",
                )
            )
        if not draft.domains:
            blocking.append(
                QualityIssue(code="domains_missing", message="Taxonomy Draft 没有稳定领域。")
            )

        all_nodes = list(draft.content_types)
        top_domains = list(draft.domains)
        child_domains = [child for parent in draft.domains for child in parent.children]
        all_nodes.extend(top_domains)
        all_nodes.extend(child_domains)
        ids = [node.id for node in all_nodes]
        if len(ids) != len(set(ids)):
            blocking.append(
                QualityIssue(code="duplicate_node_ids", message="稳定节点 ID 不唯一。")
            )

        invalid_support_ids: set[str] = set()
        invalid_representatives: list[str] = []
        for node in all_nodes:
            invalid_support_ids.update(set(node.supporting_ids) - allowed_ids)
            if not set(node.representative_ids) <= set(node.supporting_ids):
                invalid_representatives.append(node.id)
        for candidate in list(draft.topics) + list(draft.entities):
            invalid_support_ids.update(set(candidate.supporting_ids) - allowed_ids)
        if invalid_support_ids:
            blocking.append(
                QualityIssue(
                    code="invalid_supporting_ids",
                    message="节点引用了 Snapshot 短 ID 映射之外的内容。",
                    node_ids=sorted(invalid_support_ids),
                )
            )
        if invalid_representatives:
            blocking.append(
                QualityIssue(
                    code="representative_not_supported",
                    message="代表内容必须属于节点 supporting IDs。",
                    node_ids=invalid_representatives,
                )
            )

        bad_types: list[str] = []
        bad_parents: list[str] = []
        bad_id_formats = [
            node.id for node in draft.content_types if not node.id.startswith("ct_")
        ] + [
            node.id for node in top_domains + child_domains if not node.id.startswith("d_")
        ]
        for node in draft.content_types:
            if node.node_type != "content_type" or node.parent_id is not None:
                bad_types.append(node.id)
        for parent in draft.domains:
            if parent.node_type != "domain" or parent.parent_id is not None:
                bad_types.append(parent.id)
            for child in parent.children:
                if child.node_type != "domain":
                    bad_types.append(child.id)
                if child.parent_id != parent.id:
                    bad_parents.append(child.id)
                if not set(child.supporting_ids) <= set(parent.supporting_ids):
                    bad_parents.append(child.id)
        if bad_types:
            blocking.append(
                QualityIssue(
                    code="node_type_or_root_parent_invalid",
                    message="Content Type/Domain 类型或根节点 parent_id 无效。",
                    node_ids=sorted(set(bad_types)),
                )
            )
        if bad_id_formats:
            blocking.append(
                QualityIssue(
                    code="node_id_format_invalid",
                    message="Content Type 和 Domain 临时 ID 前缀无效。",
                    node_ids=bad_id_formats,
                )
            )
        if bad_parents:
            blocking.append(
                QualityIssue(
                    code="parent_child_inadequate",
                    message="子节点 parent_id 或语料支持与父节点不一致。",
                    node_ids=sorted(set(bad_parents)),
                )
            )

        entity_names = {
            _normalized(item.name)
            for output in local_outputs
            for item in output.entities
        }
        content_type_names = {_normalized(item.name) for item in draft.content_types}
        entity_leaks = [
            node.id for node in top_domains + child_domains
            if _normalized(node.name) in entity_names
        ]
        type_leaks = [
            node.id for node in top_domains + child_domains
            if _normalized(node.name) in content_type_names
        ]
        if entity_leaks:
            blocking.append(
                QualityIssue(
                    code="entity_leakage",
                    message="具体 Entity 被放入稳定领域树。",
                    node_ids=entity_leaks,
                )
            )
        if type_leaks:
            blocking.append(
                QualityIssue(
                    code="content_type_leakage",
                    message="Content Type 被放入稳定领域树。",
                    node_ids=type_leaks,
                )
            )

        overlap_pairs = _high_overlap_siblings(draft)
        if overlap_pairs:
            warnings.append(
                QualityIssue(
                    code="sibling_support_overlap",
                    message="部分兄弟节点 supporting IDs 高度重叠，需要 Validator 复核边界。",
                    node_ids=sorted({value for pair in overlap_pairs for value in pair}),
                )
            )

        if hierarchy_report is None:
            blocking.append(
                QualityIssue(
                    code="hierarchy_validation_missing",
                    message="Quality Gate 前必须完成独立 Hierarchy Validation。",
                )
            )
        else:
            expected_inspected = {node.id for node in top_domains + child_domains}
            missing_inspection = expected_inspected - set(hierarchy_report.inspected_node_ids)
            if missing_inspection:
                blocking.append(
                    QualityIssue(
                        code="hierarchy_validation_incomplete",
                        message="Hierarchy Validator 没有覆盖所有 Domain 节点。",
                        node_ids=sorted(missing_inspection),
                    )
                )
            for finding in hierarchy_report.findings:
                target = blocking if finding.severity == "blocking" else warnings
                target.append(
                    QualityIssue(
                        code=finding.code,
                        message=finding.message,
                        node_ids=finding.node_ids,
                    )
                )

        child_count = len(child_domains)
        supported_local_subdomains = sum(
            len(set(item.supporting_ids)) >= 2 for item in local_subdomains
        )
        if child_count == 0 and supported_local_subdomains:
            blocking.append(
                QualityIssue(
                    code="supported_subdomains_missing",
                    message="局部候选存在多条语料支持的稳定细分，但 Draft 没有二级领域。",
                )
            )
        elif child_count == 0:
            warnings.append(
                QualityIssue(
                    code="no_subdomains_observed",
                    message="当前 Draft 没有二级领域；不得机械补齐，需以 Validator 结果判断。",
                )
            )

        retry_stage = _retry_stage(blocking, bool(local_content_types))
        return TaxonomyQualityResult(
            passed=not blocking,
            blocking_issues=blocking,
            warnings=warnings,
            retry_stage=retry_stage,
            metrics={
                "content_type_count": len(draft.content_types),
                "primary_domain_count": len(top_domains),
                "subdomain_count": child_count,
                "local_content_type_candidate_count": len(local_content_types),
                "local_subdomain_candidate_count": len(local_subdomains),
                "entity_leakage_count": len(entity_leaks),
                "content_type_leakage_count": len(type_leaks),
                "invalid_supporting_id_count": len(invalid_support_ids),
                "sibling_overlap_pair_count": len(overlap_pairs),
            },
        )


def _retry_stage(blocking: list[QualityIssue], has_local_content_types: bool) -> str | None:
    codes = {issue.code for issue in blocking}
    if "content_types_missing" in codes and not has_local_content_types:
        return "content_type_recovery"
    if codes & {"hierarchy_validation_missing", "hierarchy_validation_incomplete"}:
        return "hierarchy_validation"
    if codes:
        return "consolidation"
    return None


def _high_overlap_siblings(draft: ConsolidatedDraft) -> list[tuple[str, str]]:
    groups = [list(draft.domains)] + [list(parent.children) for parent in draft.domains]
    pairs: list[tuple[str, str]] = []
    for siblings in groups:
        for left_index, left in enumerate(siblings):
            for right in siblings[left_index + 1:]:
                left_ids = set(left.supporting_ids)
                right_ids = set(right.supporting_ids)
                union = left_ids | right_ids
                overlap = len(left_ids & right_ids) / len(union) if union else 0
                if len(left_ids & right_ids) >= 2 and overlap >= 0.7:
                    pairs.append((left.id, right.id))
    return pairs


def _normalized(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


HIERARCHY_VALIDATION_PROMPT_VERSION = "hierarchy-validation-v2"
HIERARCHY_VALIDATION_SCHEMA_HINT = (
    '{"findings":[{"code":"","message":"","node_ids":[],'
    '"severity":"blocking|warning","check":"parent_child_adequacy|sibling_overlap|'
    'granularity_consistency|entity_leakage|content_type_leakage|node_support|'
    'overbroad_domain|overfine_subdomain|missing_subdomain"}],'
    '"inspected_node_ids":["d_01"],"summary":""}'
)


def build_hierarchy_validation_prompt(
    draft: ConsolidatedDraft, local_outputs: list[LocalDiscoveryOutput]
) -> str:
    required_node_ids = [node.id for node in draft.domains] + [
        child.id for node in draft.domains for child in node.children
    ]
    payload = {
        "draft": draft.model_dump(mode="json"),
        "local_candidates": [value.model_dump(mode="json") for value in local_outputs],
        "required_inspected_node_ids": required_node_ids,
    }
    return f"""你是独立 Taxonomy Hierarchy Validator，只生成问题报告，不修改 Draft。
检查父子合理性、兄弟重叠、粒度一致性、Content Type/Entity/Topic 泄漏、节点证据、过宽一级领域、过细二级领域和缺失的稳定细分。
没有子领域本身不是错误；只有局部候选显示多个语义不同、有真实支持、边界清晰且长期可复用的稳定子群时，才报告 missing_subdomain。
项目、工具、模型、人物、单篇论文和短期概念不得成为稳定 Domain。只依据输入候选和 supporting IDs，不读取原始卡片，不修改任何节点。只输出 JSON。
必须逐一检查 required_inspected_node_ids 中的一级和二级 Domain；无论是否发现问题，inspected_node_ids 都必须原样完整回传该数组，不得只写一级节点。

精简输出结构：{HIERARCHY_VALIDATION_SCHEMA_HINT}
输入：{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"""
