from __future__ import annotations

import json
import re
from hashlib import sha256
from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.domain import PipelineError
from shiliu.taxonomy.controlled_facets import (
    _stable_hash,
    _utc_now,
    _write_json,
    _write_json_once,
)
from shiliu.taxonomy.domain_completion_review import _character_similarity, _set_overlap


DOMAIN_DRAFT_A_VERSION = "domain-draft-a-v2"
FROZEN_DOMAIN_DRAFT_A_VERSION = "domain-draft-a-v3-direct-scope-sources"
DOMAIN_DRAFT_A_PROMPT_VERSION = "domain-draft-a-synthesis-v1"
DOMAIN_DRAFT_A_COMPLEXITY_VERSION = "domain-draft-a-complexity-v1"
DOMAIN_DRAFT_A_HIERARCHY_RISKS_VERSION = "domain-draft-a-hierarchy-risks-v1"
DOMAIN_DRAFT_A_REVIEW_BUNDLE_VERSION = "domain-draft-a-hierarchy-review-bundle-v1"
DOMAIN_DRAFT_A_HIERARCHY_REVIEW_VERSION = "domain-draft-a-hierarchy-review-v1"
DOMAIN_DRAFT_A_MANIFEST_VERSION = "domain-draft-a-manifest-v2"
DOMAIN_DRAFT_A_SEMANTIC_DIFF_VERSION = "domain-draft-a-semantic-diff-v1"
DOMAIN_DRAFT_A_RESPONSE_LEDGER_VERSION = "domain-draft-a-response-ledger-v1"


class DomainDraftANode(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    draft_node_id: str = Field(pattern=r"^draft_[0-9]{3}$")
    name: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1, max_length=360)
    canonical_includes: list[str] = Field(min_length=1, max_length=8)
    canonical_excludes: list[str] = Field(min_length=1, max_length=8)
    parent_id: str | None
    status: Literal["probable", "weak", "uncertain"]
    source_cluster_ids: list[str] = Field(min_length=1)
    source_candidate_ids: list[str] = Field(min_length=1)
    source_runs: list[Literal["A", "B", "C1"]] = Field(min_length=1)
    evidence_pool_ids: list[str] = Field(min_length=1)
    representative_ids: list[str] = Field(min_length=1, max_length=8)
    decision_reason: str = Field(min_length=1, max_length=500)
    known_risks: list[str] = Field(max_length=12)


class DomainDraftA(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[DOMAIN_DRAFT_A_VERSION] = DOMAIN_DRAFT_A_VERSION
    synthesis_reason: str = Field(min_length=1, max_length=800)
    excluded_cluster_ids: list[str]
    nodes: list[DomainDraftANode] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tree(self):
        node_ids = [node.draft_node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Draft node IDs must be unique")
        node_by_id = {node.draft_node_id: node for node in self.nodes}
        for node in self.nodes:
            if node.parent_id is not None and node.parent_id not in node_by_id:
                raise ValueError("Draft parent is missing")
            if node.parent_id == node.draft_node_id:
                raise ValueError("Draft node cannot parent itself")
            if (
                node.parent_id is not None
                and node_by_id[node.parent_id].parent_id is not None
            ):
                raise ValueError("Draft depth exceeds two levels")
        return self


class FrozenDomainDraftANode(BaseModel):
    """Canonical frozen node with direct consumption separated from scope aggregation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    draft_node_id: str = Field(pattern=r"^draft_[0-9]{3}$")
    name: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1, max_length=360)
    canonical_includes: list[str] = Field(min_length=1, max_length=8)
    canonical_excludes: list[str] = Field(min_length=1, max_length=8)
    parent_id: str | None
    status: Literal["probable", "weak", "uncertain"]
    direct_source_cluster_ids: list[str]
    scope_source_cluster_ids: list[str] = Field(min_length=1)
    source_candidate_ids: list[str] = Field(min_length=1)
    source_runs: list[Literal["A", "B", "C1"]] = Field(min_length=1)
    evidence_pool_ids: list[str] = Field(min_length=1)
    representative_ids: list[str] = Field(min_length=1, max_length=8)
    decision_reason: str = Field(min_length=1, max_length=500)
    known_risks: list[str] = Field(max_length=12)


class FrozenDomainDraftA(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[FROZEN_DOMAIN_DRAFT_A_VERSION] = FROZEN_DOMAIN_DRAFT_A_VERSION
    synthesis_reason: str = Field(min_length=1, max_length=800)
    excluded_cluster_ids: list[str]
    nodes: list[FrozenDomainDraftANode] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tree(self):
        node_ids = [node.draft_node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Draft node IDs must be unique")
        node_by_id = {node.draft_node_id: node for node in self.nodes}
        for node in self.nodes:
            if node.parent_id is not None and node.parent_id not in node_by_id:
                raise ValueError("Draft parent is missing")
            if node.parent_id == node.draft_node_id:
                raise ValueError("Draft node cannot parent itself")
            if (
                node.parent_id is not None
                and node_by_id[node.parent_id].parent_id is not None
            ):
                raise ValueError("Draft depth exceeds two levels")
        return self


DOMAIN_DRAFT_A_SCHEMA_HINT = (
    '{"version":"domain-draft-a-v2","synthesis_reason":"",'
    '"excluded_cluster_ids":["xc_001"],"nodes":[{'
    '"draft_node_id":"draft_001","name":"", "definition":"",'
    '"canonical_includes":[""],"canonical_excludes":[""],'
    '"parent_id":null,"status":"probable|weak|uncertain",'
    '"source_cluster_ids":["xc_001"],'
    '"source_candidate_ids":["A:nc_001"],"source_runs":["A"],'
    '"evidence_pool_ids":["C001"],"representative_ids":["C001"],'
    '"decision_reason":"","known_risks":[]}]}'
)


def _compact_frozen_cluster(cluster: dict[str, Any]) -> dict[str, Any]:
    scope = dict(cluster.get("canonical_scope_proposal") or {})
    return {
        "cluster_id": cluster["cluster_id"],
        "name": scope.get("name"),
        "definition": scope.get("definition"),
        "includes": list(scope.get("includes") or []),
        "excludes": list(scope.get("excludes") or []),
        "parent_scope_hint": scope.get("parent_scope_hint"),
        "domain_disposition": cluster.get("domain_disposition"),
        "status": cluster.get("recommended_status"),
        "source_candidate_ids": list(cluster.get("source_candidates") or []),
        "source_runs": list(cluster.get("protocol_provenance") or []),
        "evidence_pool_ids": list(cluster.get("evidence_pools") or []),
        "representative_ids": list(cluster.get("representative_ids") or []),
        "known_risks": list(cluster.get("known_risk_flags") or []),
        "alignment_relation": cluster.get("alignment_relation"),
        "decision_reason": cluster.get("decision_reason"),
    }


def build_domain_draft_a_prompt(
    *, semantic_contract: dict[str, Any], m2_final: dict[str, Any],
    final_clusters: dict[str, Any], final_decisions: dict[str, Any],
    representative_profiles_by_id: dict[str, dict[str, Any]] | None = None,
    decision_log: dict[str, Any] | None = None,
) -> str:
    profiles = representative_profiles_by_id or {}
    eligible = [
        {
            **_compact_frozen_cluster(cluster),
            "representative_profiles": [
                profiles[content_id]
                for content_id in list(cluster.get("representative_ids") or [])[:5]
                if content_id in profiles
            ][:3],
        }
        for cluster in final_clusters.get("clusters") or []
        if cluster.get("domain_disposition") in {"domain_candidate", "uncertain"}
    ]
    excluded = [
        {
            "cluster_id": cluster["cluster_id"],
            "domain_disposition": cluster.get("domain_disposition"),
            "source_candidate_ids": list(cluster.get("source_candidates") or []),
        }
        for cluster in final_clusters.get("clusters") or []
        if cluster.get("domain_disposition") not in {"domain_candidate", "uncertain"}
    ]
    payload = {
        "semantic_contract": semantic_contract,
        "m2_frozen_constraints": [
            {
                "adjudication_id": row.get("adjudication_id"),
                "adjudication": row.get("adjudication"),
                "recommended_operation": row.get("recommended_operation"),
                "sources": row.get("sources") or [],
            }
            for row in m2_final.get("decisions") or []
        ],
        "eligible_frozen_m3_clusters": eligible,
        "non_domain_frozen_m3_clusters": excluded,
        "frozen_m3_decision_summary": {
            "decision_count": len(final_decisions.get("decisions") or []),
            "input_hash": _stable_hash(final_decisions),
        },
        "m3_decision_log": decision_log or {},
    }
    return (
        "你是 Taxonomy Synthesis 模型。只把冻结 M3 的语义 Domain Cluster 综合成可浏览的"
        " Domain Draft A。不得重做跨 Run Alignment，不得读取或猜测原始语料，不得把每个 Cluster"
        " 一一变成节点，不得创建无来源节点。Topic、Entity、Object、Use Context 和内容形式不得进入"
        " Domain Tree。树最多两级；子节点必须是父节点问题空间的语义子集。Draft A 尚未经过 Trial"
        " Assignment，因此禁止 stable，只能 probable、weak、uncertain。单 Evidence 节点只能 weak 或"
        " uncertain。每个节点必须完整保留来源 Cluster、Candidate、Run、Evidence 和代表内容。可以合并"
        "语义等价或浏览价值上应共享边界的冻结 Cluster；可以把不适合产品树的 uncertain Cluster 写入"
        " excluded_cluster_ids，但必须在 synthesis_reason 解释。不要使用固定 Top-K，不要为了未来可能"
        "出现的内容预建节点。只输出严格 JSON。\nINPUT="
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + "\nSCHEMA=" + DOMAIN_DRAFT_A_SCHEMA_HINT
    )


def validate_domain_draft_a(
    draft: DomainDraftA, *, final_clusters: dict[str, Any],
) -> None:
    clusters = {
        cluster["cluster_id"]: cluster
        for cluster in final_clusters.get("clusters") or []
    }
    eligible_ids = {
        cluster_id for cluster_id, cluster in clusters.items()
        if cluster.get("domain_disposition") in {"domain_candidate", "uncertain"}
    }
    used_cluster_ids: list[str] = []
    cluster_uses: dict[str, list[str]] = defaultdict(list)
    for node in draft.nodes:
        used_cluster_ids.extend(node.source_cluster_ids)
        for cluster_id in node.source_cluster_ids:
            cluster_uses[cluster_id].append(node.draft_node_id)
        if not set(node.source_cluster_ids).issubset(eligible_ids):
            raise PipelineError(
                f"Draft A 节点 {node.draft_node_id} 使用非 Domain M3 Cluster",
                code="domain_draft_a_dimension_leakage",
                retryable=False,
            )
        expected_candidates = {
            candidate
            for cluster_id in node.source_cluster_ids
            for candidate in clusters[cluster_id].get("source_candidates") or []
        }
        if not set(node.source_candidate_ids).issubset(expected_candidates):
            raise PipelineError(
                f"Draft A 节点 {node.draft_node_id} Candidate provenance 非法",
                code="domain_draft_a_candidate_provenance_invalid",
                retryable=False,
            )
        expected_evidence = {
            evidence
            for cluster_id in node.source_cluster_ids
            for evidence in clusters[cluster_id].get("evidence_pools") or []
        }
        if not set(node.evidence_pool_ids).issubset(expected_evidence):
            raise PipelineError(
                f"Draft A 节点 {node.draft_node_id} Evidence provenance 非法",
                code="domain_draft_a_evidence_provenance_invalid",
                retryable=False,
            )
        if len(node.evidence_pool_ids) == 1 and node.status == "probable":
            raise PipelineError(
                f"Draft A 单 Evidence 节点 {node.draft_node_id} 不得 probable",
                code="domain_draft_a_single_evidence_probable",
                retryable=False,
            )
    node_by_id = {node.draft_node_id: node for node in draft.nodes}
    invalid_reuse: dict[str, list[str]] = {}
    for cluster_id, node_ids in cluster_uses.items():
        if len(node_ids) <= 1:
            continue
        directly_related = all(
            left_id == right_id
            or node_by_id[left_id].parent_id == right_id
            or node_by_id[right_id].parent_id == left_id
            for left_id in node_ids
            for right_id in node_ids
        )
        if not directly_related:
            invalid_reuse[cluster_id] = node_ids
    if invalid_reuse:
        raise PipelineError(
            f"Draft A Cluster 跨无关分支重复消费: {invalid_reuse}",
            code="domain_draft_a_cluster_cross_branch_reused",
            retryable=False,
        )
    excluded_ids = set(draft.excluded_cluster_ids)
    if excluded_ids - eligible_ids or set(used_cluster_ids) & excluded_ids:
        raise PipelineError(
            "Draft A excluded_cluster_ids 非法",
            code="domain_draft_a_exclusion_invalid",
            retryable=False,
        )
    if set(used_cluster_ids) | excluded_ids != eligible_ids:
        raise PipelineError(
            "Draft A 未处理全部可用 M3 Cluster",
            code="domain_draft_a_cluster_coverage_invalid",
            retryable=False,
        )


def derive_frozen_domain_draft_a(draft: DomainDraftA) -> FrozenDomainDraftA:
    """Split Provider scope provenance into unique direct and derived scope sources."""

    children: dict[str, list[DomainDraftANode]] = defaultdict(list)
    for node in draft.nodes:
        if node.parent_id is not None:
            children[node.parent_id].append(node)
    frozen_nodes: list[dict[str, Any]] = []
    for node in draft.nodes:
        child_scope = {
            cluster_id
            for child in children[node.draft_node_id]
            for cluster_id in child.source_cluster_ids
        }
        direct = [
            cluster_id for cluster_id in node.source_cluster_ids
            if cluster_id not in child_scope
        ]
        scope = list(node.source_cluster_ids)
        for cluster_id in child_scope:
            if cluster_id not in scope:
                scope.append(cluster_id)
        payload = node.model_dump(mode="json")
        payload.pop("source_cluster_ids")
        payload["direct_source_cluster_ids"] = direct
        payload["scope_source_cluster_ids"] = scope
        frozen_nodes.append(payload)
    return FrozenDomainDraftA.model_validate({
        "version": FROZEN_DOMAIN_DRAFT_A_VERSION,
        "synthesis_reason": draft.synthesis_reason,
        "excluded_cluster_ids": list(draft.excluded_cluster_ids),
        "nodes": frozen_nodes,
    })


def validate_frozen_domain_draft_a(
    draft: FrozenDomainDraftA, *, final_clusters: dict[str, Any],
) -> None:
    clusters = {
        cluster["cluster_id"]: cluster
        for cluster in final_clusters.get("clusters") or []
    }
    eligible_ids = {
        cluster_id for cluster_id, cluster in clusters.items()
        if cluster.get("domain_disposition") in {"domain_candidate", "uncertain"}
    }
    direct_uses: dict[str, list[str]] = defaultdict(list)
    node_by_id = {node.draft_node_id: node for node in draft.nodes}
    children: dict[str, list[FrozenDomainDraftANode]] = defaultdict(list)
    for node in draft.nodes:
        if node.parent_id is not None:
            children[node.parent_id].append(node)
        for cluster_id in node.direct_source_cluster_ids:
            direct_uses[cluster_id].append(node.draft_node_id)
        if not set(node.scope_source_cluster_ids).issubset(eligible_ids):
            raise PipelineError(
                f"Draft A 节点 {node.draft_node_id} 使用非 Domain M3 Cluster",
                code="domain_draft_a_dimension_leakage",
                retryable=False,
            )
        expected_candidates = {
            candidate
            for cluster_id in node.scope_source_cluster_ids
            for candidate in clusters[cluster_id].get("source_candidates") or []
        }
        if not set(node.source_candidate_ids).issubset(expected_candidates):
            raise PipelineError(
                f"Draft A 节点 {node.draft_node_id} Candidate provenance 非法",
                code="domain_draft_a_candidate_provenance_invalid",
                retryable=False,
            )
        expected_evidence = {
            evidence
            for cluster_id in node.scope_source_cluster_ids
            for evidence in clusters[cluster_id].get("evidence_pools") or []
        }
        if not set(node.evidence_pool_ids).issubset(expected_evidence):
            raise PipelineError(
                f"Draft A 节点 {node.draft_node_id} Evidence provenance 非法",
                code="domain_draft_a_evidence_provenance_invalid",
                retryable=False,
            )
        if len(node.evidence_pool_ids) == 1 and node.status == "probable":
            raise PipelineError(
                f"Draft A 单 Evidence 节点 {node.draft_node_id} 不得 probable",
                code="domain_draft_a_single_evidence_probable",
                retryable=False,
            )
    duplicates = {
        cluster_id: node_ids
        for cluster_id, node_ids in direct_uses.items() if len(node_ids) > 1
    }
    if duplicates:
        raise PipelineError(
            f"Draft A direct Cluster 被重复消费: {duplicates}",
            code="domain_draft_a_direct_cluster_reused",
            retryable=False,
        )
    for node in draft.nodes:
        expected_scope = list(node.direct_source_cluster_ids)
        for child in children[node.draft_node_id]:
            for cluster_id in child.scope_source_cluster_ids:
                if cluster_id not in expected_scope:
                    expected_scope.append(cluster_id)
        if set(expected_scope) != set(node.scope_source_cluster_ids):
            raise PipelineError(
                f"Draft A 节点 {node.draft_node_id} scope sources 不是 direct + descendants",
                code="domain_draft_a_scope_sources_not_derived",
                retryable=False,
            )
        if node.parent_id is not None:
            parent = node_by_id[node.parent_id]
            if not set(node.scope_source_cluster_ids).issubset(
                parent.scope_source_cluster_ids
            ):
                raise PipelineError(
                    f"Draft A 节点 {node.draft_node_id} scope 未被父级聚合",
                    code="domain_draft_a_parent_scope_missing_child",
                    retryable=False,
                )
    direct_ids = set(direct_uses)
    excluded_ids = set(draft.excluded_cluster_ids)
    if excluded_ids - eligible_ids or direct_ids & excluded_ids:
        raise PipelineError(
            "Draft A excluded_cluster_ids 非法",
            code="domain_draft_a_exclusion_invalid",
            retryable=False,
        )
    if direct_ids | excluded_ids != eligible_ids:
        raise PipelineError(
            "Draft A direct sources 未处理全部可用 M3 Cluster",
            code="domain_draft_a_cluster_coverage_invalid",
            retryable=False,
        )


def build_domain_draft_a_budget_preflight(
    *, prompt: str, eligible_cluster_count: int, max_tokens: int,
) -> dict[str, Any]:
    estimated_prompt_tokens = max(1, round(len(prompt) / 3.0))
    # Deliberately pessimistic: the synthesis should produce fewer nodes than
    # clusters, but the budget remains safe even if every eligible cluster is
    # represented in a verbose source-preserving node.
    estimated_output_characters_upper = eligible_cluster_count * 1200 + 1600
    estimated_output_tokens_upper = max(
        1, round(estimated_output_characters_upper / 2.7)
    )
    obvious_truncation_risk = estimated_output_tokens_upper > int(max_tokens * 0.8)
    return {
        "version": "domain-draft-a-budget-preflight-v1",
        "prompt_characters": len(prompt),
        "estimated_prompt_tokens": estimated_prompt_tokens,
        "eligible_cluster_count": eligible_cluster_count,
        "estimated_output_characters_upper": estimated_output_characters_upper,
        "estimated_output_tokens_upper": estimated_output_tokens_upper,
        "max_tokens": max_tokens,
        "obvious_truncation_risk": obvious_truncation_risk,
        "recommended_strategy": (
            "split_top_level_then_children"
            if obvious_truncation_risk else "single_high_thinking_synthesis"
        ),
    }


def _normalized(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.lower())


def _scope_cluster_ids(
    node: DomainDraftANode | FrozenDomainDraftANode,
) -> list[str]:
    if isinstance(node, FrozenDomainDraftANode):
        return node.scope_source_cluster_ids
    return node.source_cluster_ids


def _direct_cluster_ids(
    node: DomainDraftANode | FrozenDomainDraftANode,
) -> list[str]:
    if isinstance(node, FrozenDomainDraftANode):
        return node.direct_source_cluster_ids
    return node.source_cluster_ids


def evaluate_domain_draft_a(
    draft: DomainDraftA | FrozenDomainDraftA,
) -> dict[str, Any]:
    nodes = list(draft.nodes)
    by_id = {node.draft_node_id: node for node in nodes}
    children: dict[
        str | None, list[DomainDraftANode | FrozenDomainDraftANode]
    ] = defaultdict(list)
    for node in nodes:
        children[node.parent_id].append(node)
    blocking: list[dict[str, Any]] = []
    concerns: list[dict[str, Any]] = []

    names: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        names[_normalized(node.name)].append(node.draft_node_id)
        overlap = {_normalized(value) for value in node.canonical_includes} & {
            _normalized(value) for value in node.canonical_excludes
        }
        if overlap:
            blocking.append({
                "code": "includes_excludes_conflict",
                "affected_node_ids": [node.draft_node_id],
                "values": sorted(overlap),
            })
    for normalized_name, ids in names.items():
        if normalized_name and len(ids) > 1:
            blocking.append({
                "code": "normalized_duplicate_name", "affected_node_ids": ids,
            })

    sibling_scope_overlap: list[dict[str, Any]] = []
    for parent_id, siblings in children.items():
        for index, left in enumerate(siblings):
            for right in siblings[index + 1:]:
                definition_similarity = _character_similarity(
                    left.definition, right.definition,
                )
                evidence_overlap = _set_overlap(
                    left.evidence_pool_ids, right.evidence_pool_ids,
                )
                if definition_similarity >= 0.55 or evidence_overlap >= 0.5:
                    row = {
                        "parent_id": parent_id,
                        "node_ids": [left.draft_node_id, right.draft_node_id],
                        "definition_similarity": round(definition_similarity, 6),
                        "evidence_overlap": round(evidence_overlap, 6),
                    }
                    sibling_scope_overlap.append(row)
                    concerns.append({"code": "sibling_scope_overlap", **row})

    parent_child_scope_conflict: list[dict[str, Any]] = []
    for node in nodes:
        if node.parent_id is None:
            continue
        parent = by_id[node.parent_id]
        excluded = {_normalized(value) for value in parent.canonical_excludes}
        child_scope = {
            _normalized(node.name),
            *(_normalized(value) for value in node.canonical_includes),
        }
        exact_conflicts = sorted(excluded & child_scope)
        if exact_conflicts:
            row = {
                "parent_id": parent.draft_node_id,
                "child_id": node.draft_node_id,
                "exact_conflicts": exact_conflicts,
            }
            parent_child_scope_conflict.append(row)
            blocking.append({"code": "parent_excludes_child", **row})

    evidence_counts = {
        node.draft_node_id: len(set(node.evidence_pool_ids)) for node in nodes
    }
    source_cluster_counts = {
        node.draft_node_id: len(set(_scope_cluster_ids(node))) for node in nodes
    }
    direct_source_cluster_counts = {
        node.draft_node_id: len(set(_direct_cluster_ids(node))) for node in nodes
    }
    unique_source_clusters = {
        cluster_id for node in nodes for cluster_id in _direct_cluster_ids(node)
    }
    eligible_cluster_count = len(unique_source_clusters | set(draft.excluded_cluster_ids))
    node_to_eligible_cluster_ratio = round(
        len(nodes) / max(1, eligible_cluster_count), 6,
    )
    root_share = round(len(children[None]) / max(1, len(nodes)), 6)
    if len(children[None]) >= 15 and root_share >= 0.75:
        concerns.append({
            "code": "flat_tree_complexity_review_required",
            "top_level_node_count": len(children[None]),
            "total_node_count": len(nodes),
            "root_share": root_share,
        })
    if len(nodes) >= 20 and node_to_eligible_cluster_ratio >= 0.8:
        concerns.append({
            "code": "near_one_cluster_per_node_review_required",
            "total_node_count": len(nodes),
            "eligible_cluster_count": eligible_cluster_count,
            "node_to_eligible_cluster_ratio": node_to_eligible_cluster_ratio,
        })
    metrics = {
        "version": DOMAIN_DRAFT_A_COMPLEXITY_VERSION,
        "top_level_node_count": len(children[None]),
        "second_level_node_count": len(nodes) - len(children[None]),
        "total_node_count": len(nodes),
        "probable_node_count": sum(node.status == "probable" for node in nodes),
        "weak_node_count": sum(node.status == "weak" for node in nodes),
        "uncertain_node_count": sum(node.status == "uncertain" for node in nodes),
        "single_evidence_node_count": sum(value == 1 for value in evidence_counts.values()),
        "low_support_node_count": sum(value <= 2 for value in evidence_counts.values()),
        "source_cluster_count_per_node": source_cluster_counts,
        "direct_source_cluster_count_per_node": direct_source_cluster_counts,
        "evidence_count_per_node": evidence_counts,
        "sibling_scope_overlap": sibling_scope_overlap,
        "parent_child_scope_conflict": parent_child_scope_conflict,
        "source_cluster_to_node_ratio": round(
            sum(source_cluster_counts.values()) / max(1, len(nodes)), 6,
        ),
        "unique_source_cluster_count": len(unique_source_clusters),
        "excluded_cluster_count": len(draft.excluded_cluster_ids),
        "eligible_cluster_count": eligible_cluster_count,
        "node_to_eligible_cluster_ratio": node_to_eligible_cluster_ratio,
        "root_share": root_share,
    }
    risks = {
        "version": DOMAIN_DRAFT_A_HIERARCHY_RISKS_VERSION,
        "blocking": blocking,
        "concerns": concerns,
        "metrics_hash": _stable_hash(metrics),
    }
    return {
        "passed": not blocking,
        "metrics": metrics,
        "hierarchy_risks": risks,
    }


def build_domain_draft_a_hierarchy_review_bundle(
    *, draft: DomainDraftA, evaluation: dict[str, Any],
    final_clusters: dict[str, Any],
    representative_profiles_by_id: dict[str, dict[str, Any]],
    m3_final_review: dict[str, Any],
) -> dict[str, Any]:
    clusters = {
        cluster["cluster_id"]: cluster
        for cluster in final_clusters.get("clusters") or []
    }
    return _build_domain_draft_a_hierarchy_review_bundle_body(
        draft=draft,
        evaluation=evaluation,
        final_clusters=final_clusters,
        representative_profiles_by_id=representative_profiles_by_id,
        m3_final_review=m3_final_review,
        clusters=clusters,
    )


def _file_sha256(path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def build_domain_draft_a_response_ledger(run_dir) -> dict[str, Any]:
    call_dir = run_dir / "domain_draft_a_synthesis" / "main" / "attempt-01"
    concurrency = json.loads(
        (run_dir / "domain-draft-a-concurrency-audit.json").read_text(
            encoding="utf-8"
        )
    )
    path_by_response = {
        "565fc77e-8e36-4135-a2f7-f11f3b51c167": "raw-response.txt",
        "16cfca4b-8de1-4fc7-9e59-0b5645dad2aa": "raw-response-02.txt",
        "77dca950-2877-4dcc-a54b-726e869bad4a": "repair-raw-response-02.txt",
        "b928a44f-fef2-4143-9e3d-c67f7f362834": "repair-raw-response.txt",
    }
    responses = []
    for response in concurrency.get("responses") or []:
        row = dict(response)
        raw_path = path_by_response[row["response_id"]]
        path = call_dir / raw_path
        if not path.is_file():
            raise PipelineError(
                f"Draft A response raw 缺失: {raw_path}",
                code="domain_draft_a_response_raw_missing",
                retryable=False,
            )
        row["raw_path"] = raw_path
        row["raw_sha256"] = _file_sha256(path)
        row["selected"] = row["response_id"] == (
            "b928a44f-fef2-4143-9e3d-c67f7f362834"
        )
        responses.append(row)
    ledger = {
        "version": DOMAIN_DRAFT_A_RESPONSE_LEDGER_VERSION,
        "severity": "BLOCKING_ENGINEERING_FINDING",
        "normal_single_call": False,
        "primary_response_count": sum(
            row["kind"] == "primary" for row in responses
        ),
        "repair_response_count": sum(
            row["kind"] == "json_repair" for row in responses
        ),
        "unknown_usage_response_count": sum(
            row.get("usage") is None for row in responses
        ),
        "responses": responses,
        "selected_response_id": "b928a44f-fef2-4143-9e3d-c67f7f362834",
        "selection_reason": (
            "This repair belongs to the 25-node primary chain, preserves the "
            "primary semantics, passes Schema after audited ID normalization "
            "and ordered overflow truncation, and passes the corrected direct/"
            "scope provenance gate. The 33-node chain remained validation-failed."
        ),
        "known_minimum_usage": concurrency["known_minimum_usage"],
        "root_cause": concurrency["cause"],
        "trial_assignment_blocked_until": "single_flight_attempt_lease_implemented",
    }
    if ledger["primary_response_count"] != 2 or ledger["repair_response_count"] != 2:
        raise PipelineError(
            "Draft A 并发事故响应数量不符合审计事实",
            code="domain_draft_a_response_count_mismatch",
            retryable=False,
        )
    if ledger["unknown_usage_response_count"] != 1:
        raise PipelineError(
            "Draft A unknown usage 数量不符合审计事实",
            code="domain_draft_a_unknown_usage_mismatch",
            retryable=False,
        )
    return ledger


def build_domain_draft_a_semantic_diff(
    *, primary: dict[str, Any], final_repair: dict[str, Any],
    primary_sha256: str, final_repair_sha256: str,
) -> dict[str, Any]:
    primary_nodes = primary.get("nodes") or []
    final_nodes = final_repair.get("nodes") or []
    if len(primary_nodes) != len(final_nodes):
        raise PipelineError(
            "Primary 与 Final Repair 节点数量不同",
            code="domain_draft_a_repair_node_count_changed",
            retryable=False,
        )
    id_map = {
        before["draft_node_id"]: after["draft_node_id"]
        for before, after in zip(primary_nodes, final_nodes, strict=True)
    }
    changes: list[dict[str, Any]] = []
    semantic_changes: list[dict[str, Any]] = []
    allowed_counts: dict[str, int] = defaultdict(int)
    for index, (before, after) in enumerate(
        zip(primary_nodes, final_nodes, strict=True)
    ):
        if before.get("name") != after.get("name"):
            semantic_changes.append({
                "node_index": index, "field": "name",
                "before": before.get("name"), "after": after.get("name"),
            })
        for field in sorted(set(before) | set(after)):
            old = before.get(field)
            new = after.get(field)
            if old == new:
                continue
            change_type = "semantic_change"
            if field == "draft_node_id":
                change_type = "id_normalization"
            elif field == "parent_id" and (
                (old is None and new is None) or id_map.get(old) == new
            ):
                change_type = "reference_sync"
            elif (
                isinstance(old, list) and isinstance(new, list)
                and len(new) < len(old) and old[:len(new)] == new
            ):
                change_type = "ordered_overflow_truncation"
            row = {
                "node_index": index,
                "node_name": before.get("name"),
                "field": field,
                "change_type": change_type,
                "before": old,
                "after": new,
            }
            changes.append(row)
            if change_type == "semantic_change":
                semantic_changes.append(row)
            else:
                allowed_counts[change_type] += 1
    if primary.get("excluded_cluster_ids") != final_repair.get(
        "excluded_cluster_ids"
    ):
        semantic_changes.append({
            "field": "excluded_cluster_ids",
            "before": primary.get("excluded_cluster_ids"),
            "after": final_repair.get("excluded_cluster_ids"),
        })
    return {
        "version": DOMAIN_DRAFT_A_SEMANTIC_DIFF_VERSION,
        "primary_sha256": primary_sha256,
        "final_repair_sha256": final_repair_sha256,
        "node_count_before": len(primary_nodes),
        "node_count_after": len(final_nodes),
        "excluded_clusters_unchanged": primary.get("excluded_cluster_ids") == (
            final_repair.get("excluded_cluster_ids")
        ),
        "changes": changes,
        "allowed_change_counts": dict(allowed_counts),
        "semantic_changes_requiring_reviewer": semantic_changes,
        "semantic_change_count": len(semantic_changes),
        "requires_hierarchy_reviewer_confirmation": True,
    }


def validate_hierarchy_review_evidence(run_dir) -> dict[str, Any]:
    input_path = run_dir / "domain-draft-a-hierarchy-review-bundle.json"
    output_path = run_dir / "domain-draft-a-hierarchy-review-raw-output.json"
    provenance_path = run_dir / "domain-draft-a-hierarchy-review-provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    input_sha = _file_sha256(input_path)
    output_sha = _file_sha256(output_path)
    if provenance.get("input_sha256") != input_sha:
        raise PipelineError(
            "Hierarchy Reviewer input hash 不匹配",
            code="domain_draft_a_reviewer_input_hash_mismatch",
            retryable=False,
        )
    if provenance.get("output_sha256") != output_sha:
        raise PipelineError(
            "Hierarchy Reviewer output hash 不匹配",
            code="domain_draft_a_reviewer_output_hash_mismatch",
            retryable=False,
        )
    raw_review = json.loads(output_path.read_text(encoding="utf-8"))
    blocking = raw_review.get("blocking_findings")
    if (
        raw_review.get("verdict") not in {"PASS", "PASS_WITH_CONCERNS"}
        or not isinstance(blocking, list)
        or blocking
        or int(raw_review.get("dimension_leakage_count") or 0) != 0
    ):
        raise PipelineError(
            "Hierarchy Reviewer 原始输出未通过独立 Freeze Gate",
            code="domain_draft_a_reviewer_gate_failed",
            retryable=False,
        )
    return {
        "input_sha256": input_sha,
        "output_sha256": output_sha,
        "verdict": raw_review["verdict"],
        "blocking_count": len(blocking),
        "dimension_leakage_count": int(
            raw_review.get("dimension_leakage_count") or 0
        ),
        "usage": provenance.get("usage"),
        "provider_call_count": int(provenance.get("provider_call_count") or 0),
    }
def _build_domain_draft_a_hierarchy_review_bundle_body(
    *, draft: DomainDraftA, evaluation: dict[str, Any],
    final_clusters: dict[str, Any],
    representative_profiles_by_id: dict[str, dict[str, Any]],
    m3_final_review: dict[str, Any], clusters: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    by_id = {node.draft_node_id: node for node in draft.nodes}
    risk_node_ids: set[str] = set()
    for finding in [
        *evaluation["hierarchy_risks"]["blocking"],
        *evaluation["hierarchy_risks"]["concerns"],
    ]:
        risk_node_ids.update(finding.get("affected_node_ids") or [])
        risk_node_ids.update(finding.get("node_ids") or [])
        for key in ("parent_id", "child_id"):
            if finding.get(key):
                risk_node_ids.add(finding[key])
    low_support_ids = {
        node_id for node_id, count in
        evaluation["metrics"]["evidence_count_per_node"].items() if count <= 2
    }
    risk_node_ids.update(low_support_ids)
    m3_concern_clusters = {
        cluster_id
        for concern in m3_final_review.get("remaining_concerns") or []
        for cluster_id in concern.get("scope", concern.get("cluster_ids", []))
        if isinstance(cluster_id, str) and cluster_id.startswith("xc_")
    }
    risk_node_ids.update(
        node.draft_node_id for node in draft.nodes
        if set(node.source_cluster_ids) & m3_concern_clusters
    )
    parents = {
        by_id[node_id].parent_id
        for node_id in list(risk_node_ids) if node_id in by_id
    }
    risk_node_ids.update(parent_id for parent_id in parents if parent_id)
    for node_id in list(risk_node_ids):
        if node_id not in by_id:
            continue
        parent_id = by_id[node_id].parent_id
        risk_node_ids.update(
            node.draft_node_id for node in draft.nodes
            if node.parent_id == parent_id
        )

    def node_record(node: DomainDraftANode) -> dict[str, Any]:
        evidence = list(node.evidence_pool_ids)
        return {
            **node.model_dump(mode="json"),
            "source_clusters": [{
                "cluster_id": cluster_id,
                "name": (clusters[cluster_id].get("canonical_scope_proposal") or {}).get("name"),
                "definition": (clusters[cluster_id].get("canonical_scope_proposal") or {}).get("definition"),
                "domain_disposition": clusters[cluster_id].get("domain_disposition"),
                "status": clusters[cluster_id].get("recommended_status"),
            } for cluster_id in node.source_cluster_ids],
            "representative_profiles": [
                representative_profiles_by_id[content_id]
                for content_id in evidence
                if content_id in representative_profiles_by_id
            ][:5],
        }

    return {
        "version": DOMAIN_DRAFT_A_REVIEW_BUNDLE_VERSION,
        "review_scope": "risk nodes, their parents, adjacent siblings, and flatness summary only",
        "allowed_operations": [
            "keep", "rename", "merge", "move", "promote_to_parent",
            "demote_to_child", "downgrade_to_topic", "downgrade_to_entity",
            "downgrade_to_object", "downgrade_to_use_context", "mark_weak",
            "mark_uncertain", "exclude",
        ],
        "forbidden": [
            "regenerate the full tree", "read Silver", "read complete corpus",
            "create source-free node", "use stable before Assignment",
        ],
        "complexity_metrics": evaluation["metrics"],
        "deterministic_hierarchy_risks": evaluation["hierarchy_risks"],
        "top_level_summary": [{
            "draft_node_id": node.draft_node_id,
            "name": node.name,
            "status": node.status,
            "source_cluster_count": len(node.source_cluster_ids),
            "evidence_count": len(node.evidence_pool_ids),
            "child_count": sum(
                child.parent_id == node.draft_node_id for child in draft.nodes
            ),
        } for node in draft.nodes if node.parent_id is None],
        "risk_nodes": [
            node_record(by_id[node_id])
            for node_id in sorted(risk_node_ids) if node_id in by_id
        ],
        "excluded_cluster_ids": list(draft.excluded_cluster_ids),
        "m3_remaining_concerns": m3_final_review.get("remaining_concerns") or [],
        "draft_hash": _stable_hash(draft.model_dump(mode="json")),
        "final_clusters_hash": _stable_hash(final_clusters),
    }


def record_domain_draft_a_hierarchy_review(
    run_dir, review: dict[str, Any],
) -> dict[str, Any]:
    bundle = json.loads(
        (run_dir / "domain-draft-a-hierarchy-review-bundle.json")
        .read_text(encoding="utf-8")
    )
    verdict = review.get("verdict")
    if verdict not in {"PASS", "PASS_WITH_CONCERNS", "FAIL"}:
        raise PipelineError(
            "Draft A Hierarchy Reviewer verdict 非法",
            code="domain_draft_a_review_verdict_invalid",
            retryable=False,
        )
    blocking = review.get("blocking_findings")
    if not isinstance(blocking, list):
        raise PipelineError(
            "Draft A Hierarchy Reviewer blocking_findings 缺失",
            code="domain_draft_a_review_shape_invalid",
            retryable=False,
        )
    if (verdict == "FAIL") != bool(blocking):
        raise PipelineError(
            "Draft A Hierarchy Reviewer verdict 与 Blocking 不一致",
            code="domain_draft_a_review_blocking_mismatch",
            retryable=False,
        )
    if int(review.get("dimension_leakage_count") or 0) != 0 and verdict != "FAIL":
        raise PipelineError(
            "Draft A 维度泄漏不能以非 FAIL 通过",
            code="domain_draft_a_review_dimension_leakage",
            retryable=False,
        )
    normalized = dict(review)
    normalized.update({
        "version": DOMAIN_DRAFT_A_HIERARCHY_REVIEW_VERSION,
        "review_bundle_hash": _stable_hash(bundle),
        "blocking_count": len(blocking),
        "freeze_eligible": not blocking,
        "provider_call_count": 0,
    })
    _write_json_once(run_dir / "domain-draft-a-hierarchy-review.json", normalized)
    return normalized


def _draft_tree_markdown(draft: FrozenDomainDraftA) -> str:
    children: dict[str | None, list[FrozenDomainDraftANode]] = defaultdict(list)
    for node in draft.nodes:
        children[node.parent_id].append(node)
    lines = ["# Domain Draft A", "", "> 尚未经过 Trial Assignment；没有 stable 节点。", ""]
    for root in children[None]:
        lines.append(
            f"- **{root.name}** (`{root.status}`) — {root.definition} "
            f"[direct: {', '.join(root.direct_source_cluster_ids) or 'none'}; "
            f"scope: {', '.join(root.scope_source_cluster_ids)}; "
            f"evidence: {len(root.evidence_pool_ids)}]"
        )
        for child in children[root.draft_node_id]:
            lines.append(
                f"  - **{child.name}** (`{child.status}`) — {child.definition} "
                f"[direct: {', '.join(child.direct_source_cluster_ids) or 'none'}; "
                f"scope: {', '.join(child.scope_source_cluster_ids)}; "
                f"evidence: {len(child.evidence_pool_ids)}]"
            )
    if draft.excluded_cluster_ids:
        lines.extend([
            "", "## Excluded pending evidence", "",
            ", ".join(f"`{cluster_id}`" for cluster_id in draft.excluded_cluster_ids),
        ])
    return "\n".join(lines) + "\n"


def freeze_domain_draft_a(run_dir) -> dict[str, Any]:
    provider_draft = DomainDraftA.model_validate_json(
        (run_dir / "domain-draft-a.provider-draft.json").read_text(encoding="utf-8")
    )
    clusters = json.loads(
        (run_dir / "m3-final-clusters.json").read_text(encoding="utf-8")
    )
    validate_domain_draft_a(provider_draft, final_clusters=clusters)
    draft = derive_frozen_domain_draft_a(provider_draft)
    validate_frozen_domain_draft_a(draft, final_clusters=clusters)
    evaluation = evaluate_domain_draft_a(draft)
    reviewer_gate = validate_hierarchy_review_evidence(run_dir)
    repair_diff_review = json.loads(
        (run_dir / "domain-draft-a-repair-diff-review.json").read_text(
            encoding="utf-8"
        )
    )
    semantic_diff = json.loads(
        (run_dir / "domain-draft-a-primary-to-final-repair-diff.json").read_text(
            encoding="utf-8"
        )
    )
    if (
        repair_diff_review.get("verdict") != "CONFIRMED_NO_SEMANTIC_CHANGE"
        or repair_diff_review.get("diff_sha256") != _file_sha256(
            run_dir / "domain-draft-a-primary-to-final-repair-diff.json"
        )
        or semantic_diff.get("semantic_change_count") != 0
    ):
        raise PipelineError(
            "Primary → Final Repair Diff 未经 Reviewer 确认",
            code="domain_draft_a_repair_diff_review_failed",
            retryable=False,
        )
    if not evaluation["passed"]:
        raise PipelineError(
            "Draft A 尚未通过独立重算的结构 Freeze Gate",
            code="domain_draft_a_freeze_gate_failed",
            retryable=False,
        )
    if any(node.status == "stable" for node in draft.nodes):
        raise PipelineError(
            "Draft A Freeze 禁止 stable",
            code="domain_draft_a_stable_forbidden",
            retryable=False,
        )
    response_ledger = build_domain_draft_a_response_ledger(run_dir)
    _write_json(
        run_dir / "domain-draft-a-response-ledger.json", response_ledger,
    )
    engineering_findings = {
        "version": "domain-draft-a-engineering-findings-v1",
        "overall_status": "BLOCKED_BEFORE_TRIAL_ASSIGNMENT",
        "findings": [
            {
                "id": "ENG-DRAFT-A-001",
                "severity": "BLOCKING_ENGINEERING_FINDING",
                "status": "confirmed_and_audited",
                "problem": "Concurrent recovery produced two Primary and two Repair responses; one Repair usage is unknown.",
                "response_ledger_sha256": _stable_hash(response_ledger),
            },
            {
                "id": "ENG-DRAFT-A-002",
                "severity": "BLOCKING_ENGINEERING_DEBT",
                "status": "open",
                "problem": "No single-flight / attempt lease prevents a second process from resending a requesting run/stage/unit.",
                "acceptance": [
                    "Acquire an atomic lease before Provider request.",
                    "A second process observing requesting with an unexpired lease must not resend.",
                    "Expired lease takeover must preserve attempt history and use a new attempt directory.",
                    "Concurrency tests must prove exactly one Provider call per leased attempt.",
                ],
                "must_complete_before": "trial_assignment",
            },
        ],
        "resolved_in_this_freeze": [
            {
                "id": "ENG-DRAFT-A-003",
                "status": "resolved",
                "problem": "Legacy source_cluster_ids mixed direct consumption with parent scope aggregation.",
                "resolution": "Frozen v3 separates unique direct_source_cluster_ids from deterministically derived scope_source_cluster_ids.",
            }
        ],
    }
    _write_json(
        run_dir / "domain-draft-a-engineering-findings.json",
        engineering_findings,
    )
    payload = draft.model_dump(mode="json")
    provisional_pairs = [
        ("domain-draft-a.json", "domain-draft-a.provisional-before-engineering-audit.json"),
        ("domain-draft-a-tree.md", "domain-draft-a-tree.provisional-before-engineering-audit.md"),
        ("domain-draft-a-manifest.json", "domain-draft-a-manifest.provisional-before-engineering-audit.json"),
        ("domain-draft-a-complexity-metrics.json", "domain-draft-a-complexity-metrics.provisional-before-direct-scope-v3.json"),
        ("domain-draft-a-hierarchy-risks.json", "domain-draft-a-hierarchy-risks.provisional-before-direct-scope-v3.json"),
    ]
    for source_name, archive_name in provisional_pairs:
        source = run_dir / source_name
        archive = run_dir / archive_name
        if source.exists() and not archive.exists():
            archive.write_bytes(source.read_bytes())
    _write_json(run_dir / "domain-draft-a.json", payload)
    _write_json(
        run_dir / "domain-draft-a-complexity-metrics.json", evaluation["metrics"]
    )
    _write_json(
        run_dir / "domain-draft-a-hierarchy-risks.json",
        evaluation["hierarchy_risks"],
    )
    tree_path = run_dir / "domain-draft-a-tree.md"
    tree_text = _draft_tree_markdown(draft)
    tree_path.write_text(tree_text, encoding="utf-8")
    revision_record = {
        "version": "domain-draft-a-hierarchy-revision-v1",
        "status": "not_required",
        "reason": "Independent Hierarchy Reviewer reported zero Blocking findings.",
        "provider_call_count": 0,
    }
    _write_json(run_dir / "domain-draft-a-hierarchy-revision.json", revision_record)
    manifest = {
        "version": DOMAIN_DRAFT_A_MANIFEST_VERSION,
        "frozen_at": _utc_now(),
        "semantic_freeze_status": "FROZEN",
        "engineering_gate": "BLOCKED_BEFORE_TRIAL_ASSIGNMENT",
        "reviewer_verdict": reviewer_gate["verdict"],
        "blocking_count": reviewer_gate["blocking_count"],
        "dimension_leakage_count": reviewer_gate["dimension_leakage_count"],
        "hierarchy_revision": "not_required",
        "node_count": len(draft.nodes),
        "top_level_node_count": evaluation["metrics"]["top_level_node_count"],
        "second_level_node_count": evaluation["metrics"]["second_level_node_count"],
        "probable_node_count": evaluation["metrics"]["probable_node_count"],
        "weak_node_count": evaluation["metrics"]["weak_node_count"],
        "uncertain_node_count": evaluation["metrics"]["uncertain_node_count"],
        "stable_node_count": 0,
        "excluded_cluster_count": len(draft.excluded_cluster_ids),
        "remaining_concerns": json.loads(
            (run_dir / "domain-draft-a-hierarchy-review-raw-output.json")
            .read_text(encoding="utf-8")
        ).get("non_blocking_concerns") or [],
        "provider_usage_known_minimum": response_ledger["known_minimum_usage"],
        "provider_usage_unknown_response_count": response_ledger["unknown_usage_response_count"],
        "provider_response_count": len(response_ledger["responses"]),
        "normal_single_call": False,
        "source_provenance_schema": "direct_source_cluster_ids + derived scope_source_cluster_ids",
        "direct_source_uniqueness_recomputed": True,
        "scope_sources_recomputed": True,
        "repair_semantic_diff": {
            "semantic_change_count": semantic_diff["semantic_change_count"],
            "reviewer_verdict": repair_diff_review["verdict"],
            "diff_sha256": repair_diff_review["diff_sha256"],
        },
        "hierarchy_reviewer_evidence": reviewer_gate,
        "blocking_engineering_debt": ["ENG-DRAFT-A-002"],
        "artifact_hashes": {
            "domain_draft_a": _stable_hash(payload),
            "complexity_metrics": _stable_hash(evaluation["metrics"]),
            "hierarchy_risks": _stable_hash(evaluation["hierarchy_risks"]),
            "hierarchy_review_raw_output_sha256": reviewer_gate["output_sha256"],
            "response_ledger": _stable_hash(response_ledger),
            "engineering_findings": _stable_hash(engineering_findings),
            "tree": _stable_hash(tree_text),
        },
        "source_hashes": {
            "m3_final_clusters": _stable_hash(clusters),
            "provider_draft": _stable_hash(
                provider_draft.model_dump(mode="json")
            ),
            "concurrency_audit_sha256": _file_sha256(
                run_dir / "domain-draft-a-concurrency-audit.json"
            ),
        },
        "next_stage": "single_flight_attempt_lease_remediation",
        "trial_assignment_eligible": False,
        "trial_assignment_started": False,
    }
    _write_json(run_dir / "domain-draft-a-manifest.json", manifest)
    return manifest
