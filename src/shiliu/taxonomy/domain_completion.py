from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.domain import PipelineError
from shiliu.taxonomy.controlled_facets import (
    _git_state,
    _hash_file,
    _stable_hash,
    _utc_now,
    _write_json,
    _write_json_once,
)
from shiliu.taxonomy.repository import TaxonomyRepository
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from shiliu.taxonomy.workflow import TaxonomyWorkflow, _combined_audit


DOMAIN_COMPLETION_ENGINE_VERSION = "domain-completion-mission-v1"
DOMAIN_COMPLETION_PROTOCOL_VERSION = "domain-completion-protocol-v1"
SEMANTIC_CONTRACT_VERSION = "domain-semantic-contract-v2"
SEMANTIC_DIFF_VERSION = "semantic-contract-diff-a-b-c1-v1"
SEMANTIC_STAGE_PROMPT_VERSION = "domain-semantic-contract-adjudication-v1"
SEMANTIC_STAGE_SCHEMA_VERSION = "domain-semantic-contract-adjudication-schema-v1"
SEMANTIC_GATE_VERSION = "domain-semantic-contract-v2-gate-v1"
UNRESOLVED_BUNDLE_VERSION = "unresolved-adjudication-bundle-v1"
UNRESOLVED_PROMPT_VERSION = "unresolved-adjudication-v1"
UNRESOLVED_SCHEMA_VERSION = "unresolved-adjudication-schema-v1"
SNAPSHOT_2_HASH = "1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2"


REQUIRED_EXCLUDED_DIMENSIONS = {
    "presentation_form",
    "focus_object_type",
    "suggested_use_context",
    "learning_path",
    "interview_use",
    "tutorial_form",
    "single_hotspot",
    "single_project",
    "single_paper",
    "single_algorithm_trick",
    "single_content_title",
    "concrete_entity",
}


class SupportPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    discovery_support_is_provisional: Literal[True] = True
    assignment_support_is_product_evidence: Literal[True] = True
    single_evidence_default_status: Literal["weak_or_uncertain"] = "weak_or_uncertain"
    single_evidence_exception: Literal["foundational_and_cross_run_or_assignment_supported"]
    multi_evidence_is_stability_signal: Literal[True] = True
    multi_evidence_is_sufficient: Literal[False] = False


class HierarchyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    max_depth: Literal[2] = 2
    child_is_semantic_subset: Literal[True] = True
    evidence_set_containment_required: Literal[False] = False
    parent_may_be_mechanical_name_summary: Literal[False] = False


class UnresolvedPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    meaning: Literal["current_frozen_tree_cannot_safely_route_candidate"]
    automatically_creates_domain: Literal[False] = False
    requires_adjudication: Literal[True] = True


class DomainAxisPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    stable_knowledge_domains_allowed: Literal[True] = True
    stable_practice_problem_spaces_allowed: Literal[True] = True
    learning_path_is_domain: Literal[False] = False
    interview_use_is_domain: Literal[False] = False
    focus_object_without_problem_space_is_domain: Literal[False] = False


class NonDomainRoutingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    routes: list[
        Literal[
            "presentation_form",
            "focus_object_type",
            "suggested_use_context",
            "topic",
            "entity",
            "unsupported",
            "uncertain",
        ]
    ] = Field(min_length=7, max_length=7)
    topic_domain_reference_is_membership: Literal[False] = False
    closest_domain_may_be_recorded_as_provenance: Literal[True] = True

    @model_validator(mode="after")
    def validate_routes(self):
        expected = [
            "presentation_form", "focus_object_type", "suggested_use_context",
            "topic", "entity", "unsupported", "uncertain",
        ]
        if self.routes != expected:
            raise ValueError("non-Domain routes must preserve approved order")
        return self


class DomainSemanticContractV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[SEMANTIC_CONTRACT_VERSION] = SEMANTIC_CONTRACT_VERSION
    primary_question: Literal[
        "内容主要属于什么相对稳定、可长期复用的知识领域或问题空间？"
    ]
    domain_definition: str = Field(min_length=20, max_length=320)
    topic_definition: str = Field(min_length=10, max_length=240)
    entity_definition: str = Field(min_length=10, max_length=240)
    excluded_dimensions: list[str] = Field(min_length=12, max_length=20)
    stable_domain_criteria: list[str] = Field(min_length=4, max_length=10)
    classification_tests: list[
        Literal[
            "instance_test",
            "temporal_test",
            "future_collection_test",
            "axis_purity_test",
            "parent_entailment_test",
            "evidence_test",
        ]
    ] = Field(min_length=6, max_length=6)
    domain_axis_policy: DomainAxisPolicy
    non_domain_routing_policy: NonDomainRoutingPolicy
    support_policy: SupportPolicy
    hierarchy_policy: HierarchyPolicy
    unresolved_policy: UnresolvedPolicy
    node_statuses: list[Literal["stable", "probable", "weak", "uncertain"]] = Field(
        min_length=4, max_length=4
    )
    assignment_rules: list[str] = Field(min_length=4, max_length=10)
    anti_overfitting_rules: list[str] = Field(min_length=3, max_length=8)

    @model_validator(mode="after")
    def validate_contract(self):
        if set(self.excluded_dimensions) != REQUIRED_EXCLUDED_DIMENSIONS:
            raise ValueError("excluded dimensions must match the approved product boundary")
        if self.node_statuses != ["stable", "probable", "weak", "uncertain"]:
            raise ValueError("node statuses must preserve approved order")
        if self.classification_tests != [
            "instance_test", "temporal_test", "future_collection_test",
            "axis_purity_test", "parent_entailment_test", "evidence_test",
        ]:
            raise ValueError("classification tests must preserve executable order")
        return self


class FinalSupportPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    discovery_support_is_provisional: Literal[True] = True
    assignment_support_is_product_evidence: Literal[True] = True
    single_evidence_default_status: Literal["weak_or_uncertain"] = "weak_or_uncertain"
    single_evidence_exception: Literal["none_without_explicit_adjudication"]
    multi_evidence_is_stability_signal: Literal[True] = True
    multi_evidence_is_sufficient: Literal[False] = False
    multi_evidence_distinct_content_ids_min: Literal[2] = 2
    cross_run_duplicate_counts_as_new_evidence: Literal[False] = False
    evidence_affects_status_not_semantic_type: Literal[True] = True


class NodeStatusDefinitions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    stable: Literal[
        "产品赋值证据要求已满足，语义边界清楚，且没有阻断性未决问题。"
    ]
    probable: Literal[
        "语义边界成立并有至少两个不同内容支持，但产品赋值确认仍不完整。"
    ]
    weak: Literal[
        "语义上可能属于 Domain，但当前只有单一内容证据或长期复用价值尚未验证。"
    ]
    uncertain: Literal[
        "语义类型、边界、粒度或父级仍存在无法安全裁决的问题。"
    ]


class FinalDomainSemanticContractV2(DomainSemanticContractV2):
    support_policy: FinalSupportPolicy
    status_definitions: NodeStatusDefinitions


class SourceSemanticDiff(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source: Literal["A", "B", "C1"]
    protocol_label: str
    prompt_hashes: list[str] = Field(min_length=1, max_length=3)
    schema_hashes: list[str] = Field(min_length=1, max_length=3)
    explicit_rules: list[str] = Field(min_length=1, max_length=16)
    implicit_constraints: list[str] = Field(max_length=12)
    missing_or_ambiguous_rules: list[str] = Field(min_length=1, max_length=12)
    protocol_risks: list[str] = Field(min_length=1, max_length=12)


class SemanticRuleResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    rule_id: str = Field(pattern=r"^sr_[0-9]{2}$")
    a_rule: str
    b_rule: str
    c1_rule: str
    canonical_v2_rule: str = Field(min_length=5, max_length=400)
    resolution_reason: str = Field(min_length=10, max_length=500)
    adopted_from: Literal["approved_product_definition", "A", "B", "C1", "synthesis"]
    known_risk: str


class SemanticContractDiff(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[SEMANTIC_DIFF_VERSION] = SEMANTIC_DIFF_VERSION
    sources: list[SourceSemanticDiff] = Field(min_length=3, max_length=3)
    rule_resolutions: list[SemanticRuleResolution] = Field(min_length=8, max_length=20)
    comparability_conclusion: Literal[
        "independent_evidence_sources_with_protocol_provenance"
    ]
    blocking_contradictions: list[str] = Field(max_length=4)

    @model_validator(mode="after")
    def validate_sources(self):
        if [item.source for item in self.sources] != ["A", "B", "C1"]:
            raise ValueError("semantic source order must be A, B, C1")
        ids = [item.rule_id for item in self.rule_resolutions]
        if len(ids) != len(set(ids)):
            raise ValueError("semantic rule IDs must be unique")
        return self


class SemanticAdjudicationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    contract: DomainSemanticContractV2
    diff: SemanticContractDiff
    adjudication_notes: list[str] = Field(max_length=6)


class UnresolvedDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    adjudication_id: str = Field(pattern=r"^ua_[0-9]{3}$")
    adjudication: Literal[
        "true_tree_gap",
        "candidate_mixed",
        "candidate_too_narrow",
        "candidate_is_topic",
        "candidate_is_entity",
        "granularity_mismatch",
        "routing_error",
        "insufficient_evidence",
        "uncertain",
    ]
    recommended_operation: Literal[
        "create_domain_proposal",
        "merge_into_existing",
        "split_candidate",
        "downgrade_to_topic",
        "downgrade_to_entity",
        "exclude_as_unsupported",
        "keep_uncertain",
    ]
    closest_existing_nodes: list[str] = Field(max_length=4)
    evidence: list[str] = Field(min_length=1, max_length=5)
    reason: str = Field(min_length=20, max_length=1200)
    counterarguments: list[str] = Field(min_length=1, max_length=3)
    confidence: Literal["high", "medium", "low"]

    @model_validator(mode="after")
    def validate_operation(self):
        if (self.adjudication == "true_tree_gap") != (
            self.recommended_operation == "create_domain_proposal"
        ):
            raise ValueError("only true_tree_gap may create a Domain proposal")
        if self.recommended_operation == "merge_into_existing" and not self.closest_existing_nodes:
            raise ValueError("merge_into_existing requires a target node")
        return self


class UnresolvedBatchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    decisions: list[UnresolvedDecision] = Field(min_length=1, max_length=5)


UNRESOLVED_SCHEMA_HINT = (
    '{"decisions":[{"adjudication_id":"ua_001","adjudication":"true_tree_gap|candidate_mixed|'
    'candidate_too_narrow|candidate_is_topic|candidate_is_entity|granularity_mismatch|routing_error|'
    'insufficient_evidence|uncertain","recommended_operation":"create_domain_proposal|merge_into_existing|'
    'split_candidate|downgrade_to_topic|downgrade_to_entity|exclude_as_unsupported|keep_uncertain",'
    '"closest_existing_nodes":["A:d_01"],"evidence":["C001"],"reason":"",'
    '"counterarguments":[""],"confidence":"high|medium|low"}]}'
)


SEMANTIC_SCHEMA_HINT = (
    '{"contract":{"version":"domain-semantic-contract-v2",'
    '"primary_question":"内容主要属于什么相对稳定、可长期复用的知识领域或问题空间？",'
    '"domain_definition":"","topic_definition":"","entity_definition":"",'
    '"excluded_dimensions":["presentation_form","focus_object_type","suggested_use_context",'
    '"learning_path","interview_use","tutorial_form","single_hotspot","single_project",'
    '"single_paper","single_algorithm_trick","single_content_title","concrete_entity"],'
    '"stable_domain_criteria":[""],"classification_tests":["instance_test",'
    '"temporal_test","future_collection_test","axis_purity_test",'
    '"parent_entailment_test","evidence_test"],"domain_axis_policy":{'
    '"stable_knowledge_domains_allowed":true,"stable_practice_problem_spaces_allowed":true,'
    '"learning_path_is_domain":false,"interview_use_is_domain":false,'
    '"focus_object_without_problem_space_is_domain":false},'
    '"non_domain_routing_policy":{"routes":["presentation_form","focus_object_type",'
    '"suggested_use_context","topic","entity","unsupported","uncertain"],'
    '"topic_domain_reference_is_membership":false,'
    '"closest_domain_may_be_recorded_as_provenance":true},"support_policy":{'
    '"discovery_support_is_provisional":true,"assignment_support_is_product_evidence":true,'
    '"single_evidence_default_status":"weak_or_uncertain",'
    '"single_evidence_exception":"foundational_and_cross_run_or_assignment_supported",'
    '"multi_evidence_is_stability_signal":true,"multi_evidence_is_sufficient":false},'
    '"hierarchy_policy":{"max_depth":2,"child_is_semantic_subset":true,'
    '"evidence_set_containment_required":false,"parent_may_be_mechanical_name_summary":false},'
    '"unresolved_policy":{"meaning":"current_frozen_tree_cannot_safely_route_candidate",'
    '"automatically_creates_domain":false,"requires_adjudication":true},'
    '"node_statuses":["stable","probable","weak","uncertain"],'
    '"assignment_rules":[""],"anti_overfitting_rules":[""]},'
    '"diff":{"version":"semantic-contract-diff-a-b-c1-v1","sources":['
    '{"source":"A","protocol_label":"","prompt_hashes":[""],"schema_hashes":[""],'
    '"explicit_rules":[""],"implicit_constraints":[],"missing_or_ambiguous_rules":[""],'
    '"protocol_risks":[""]}],"rule_resolutions":[{"rule_id":"sr_01","a_rule":"",'
    '"b_rule":"","c1_rule":"","canonical_v2_rule":"","resolution_reason":"",'
    '"adopted_from":"approved_product_definition|A|B|C1|synthesis","known_risk":""}],'
    '"comparability_conclusion":"independent_evidence_sources_with_protocol_provenance",'
    '"blocking_contradictions":[]},"adjudication_notes":[]}'
)


def _prompt_contract(path: Path, marker: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    preamble = raw.split(marker, 1)[0].rstrip()
    return {
        "path_label": path.name,
        "raw_sha256": _hash_file(path),
        "preamble_sha256": _stable_hash(preamble),
        "preamble": preamble,
    }


def _contract_node_summary(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for node in payload["nodes"]:
        stats = node.get("evidence_stats") or {}
        result.append(
            {
                "node_id": node["node_id"],
                "name": node["name"],
                "parent_id": node.get("parent_id"),
                "definition": node["definition"],
                "evidence_pool_count": stats.get("evidence_pool_count", 0),
                "source_candidate_count": stats.get("source_candidate_count", 0),
            }
        )
    return result


def _decision_summary(path: Path, key: str = "candidate_decisions") -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    decisions = payload[key] if isinstance(payload, dict) else payload
    return {
        "count": len(decisions),
        "action_counts": dict(sorted(Counter(item["action"] for item in decisions).items())),
        "unresolved": [
            {"candidate_id": item["candidate_id"], "action": item["action"]}
            for item in decisions
            if item["action"] == "unresolved_requires_new_domain"
        ],
    }


def build_semantic_audit_bundle(
    *, run_a_dir: Path, run_b_dir: Path, run_c1_dir: Path, checkpoint_312c_dir: Path,
) -> dict[str, Any]:
    a_prompt = run_a_dir / "consolidation/main/attempt-01/prompt.txt"
    b_prompt = run_b_dir / "domain_consolidation/main/attempt-01/prompt.txt"
    c1_node = run_c1_dir / "domain_node_synthesis/main/attempt-01/prompt.txt"
    c1_route = run_c1_dir / "candidate_routing/batch-001/attempt-01/prompt.txt"
    required = [
        a_prompt,
        b_prompt,
        c1_node,
        c1_route,
        checkpoint_312c_dir / "run-a-domain-contract-v2.json",
        checkpoint_312c_dir / "run-b-domain-contract-v2.json",
        checkpoint_312c_dir / "candidate-decisions-complete-v1.json",
        run_c1_dir / "run-c1-domain-contract-v2.json",
        run_c1_dir / "run-c1-candidate-decisions-complete.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"semantic bundle sources missing: {missing}")
    return {
        "version": "semantic-audit-bundle-v1",
        "approved_product_requirements": {
            "question": "内容主要属于什么相对稳定、可长期复用的知识领域或问题空间？",
            "topic": "比 Domain 更具体、更短期或更窄的讨论主题",
            "entity": "工具、模型、项目、产品、公司、人物、论文或其他具体对象",
            "excluded_dimensions": sorted(REQUIRED_EXCLUDED_DIMENSIONS),
            "support": {
                "single": "weak/uncertain by default; foundational exception needs cross-run or Assignment support",
                "multi": "stability signal, not sufficient condition",
                "discovery_vs_assignment": "must remain distinct",
            },
            "hierarchy": "max two levels; child semantic subset; no evidence-set containment rule",
            "unresolved": "frozen tree cannot safely route; never automatic Domain creation",
        },
        "sources": {
            "A": {
                "protocol": "old_single_response_consolidation",
                "prompt": _prompt_contract(a_prompt, "Compact Candidate Table："),
                "schema_hash": _stable_hash(
                    _prompt_contract(a_prompt, "Compact Candidate Table：")["preamble"].split("精简输出结构：", 1)[-1]
                ),
                "nodes": _contract_node_summary(checkpoint_312c_dir / "run-a-domain-contract-v2.json"),
                "protocol_risks": ["single response mixes tree and all candidate decisions"],
            },
            "B": {
                "protocol": "old_single_response_plus_tail_completion",
                "prompt": _prompt_contract(b_prompt, "Compact Candidate Table："),
                "schema_hash": _stable_hash(
                    _prompt_contract(b_prompt, "Compact Candidate Table：")["preamble"].split("精简输出结构：", 1)[-1]
                ),
                "nodes": _contract_node_summary(checkpoint_312c_dir / "run-b-domain-contract-v2.json"),
                "decisions": _decision_summary(checkpoint_312c_dir / "candidate-decisions-complete-v1.json"),
                "protocol_risks": ["main response length truncation", "four decisions completed by isolated tail call"],
            },
            "C1": {
                "protocol": "node_synthesis_plus_batched_routing",
                "node_prompt": _prompt_contract(c1_node, "Complete Candidate Table:"),
                "routing_prompt": _prompt_contract(c1_route, "Frozen Tree:"),
                "node_schema_hash": _stable_hash(
                    _prompt_contract(c1_node, "Complete Candidate Table:")["preamble"].split("Schema:", 1)[-1]
                ),
                "routing_schema_hash": _stable_hash(
                    _prompt_contract(c1_route, "Frozen Tree:")["preamble"].split("Schema:", 1)[-1]
                ),
                "nodes": _contract_node_summary(run_c1_dir / "run-c1-domain-contract-v2.json"),
                "decisions": _decision_summary(run_c1_dir / "run-c1-candidate-decisions-complete.json"),
                "protocol_risks": [
                    "semantic equivalence with A/B not proven",
                    "multi-card support requirement explicit only in C1 contract",
                    "frozen tree caused systematic unresolved boundary",
                ],
            },
        },
        "forbidden_inputs": [
            "Silver Reference", "Presentation Form results", "Focus Object Type results",
            "Suggested Use Context results", "folder names", "user notes",
        ],
    }


def build_semantic_adjudication_prompt(bundle: dict[str, Any]) -> str:
    return (
        "你负责审定拾流产品的 Canonical Domain Semantic Contract v2。A、B、C1 是三份带协议来源的"
        "独立发现证据，不是等价随机运行；不得投票，也不得把任一棵 Tree 当正确答案。"
        "approved_product_requirements 是已批准的产品边界，必须完整保留；你的任务是将它写成可执行契约，"
        "并逐项解释 A/B/C1 的明确规则、隐含约束、缺口和协议风险。不得读取或推测 Silver，"
        "不得根据节点名称反向创建人工分类。Domain/Topic/Entity 必须分离；Discovery support 与"
        "Assignment support 必须分离；single Evidence 默认 weak/uncertain；multi Evidence 不是充分条件；"
        "unresolved 不得自动创建 Domain。稳定知识领域和稳定实践问题空间均可成为 Domain，但学习路径、"
        "面试用途、纯 Focus Object 不可成为 Domain。按 instance→temporal→future collection→axis purity→"
        "parent entailment→evidence 的顺序写成可执行测试。非 Domain 要区分 Form/Object/Context/Topic/Entity，"
        "Topic 对最近 Domain 的引用只允许作为 provenance，不代表成员关系。只输出 JSON，"
        "blocking_contradictions 仅在批准要求内部真的冲突时填写。\n"
        f"Schema:{SEMANTIC_SCHEMA_HINT}\n"
        f"Audit Bundle:{json.dumps(bundle, ensure_ascii=False, separators=(',', ':'))}"
    )


def validate_semantic_output(value: SemanticAdjudicationOutput, bundle: dict[str, Any]) -> None:
    expected = {
        source: {
            "prompts": [
                item["preamble_sha256"]
                for key, item in payload.items()
                if key in {"prompt", "node_prompt", "routing_prompt"}
            ],
            "schemas": [
                item for key, item in payload.items() if key.endswith("schema_hash")
            ],
        }
        for source, payload in bundle["sources"].items()
    }
    for item in value.diff.sources:
        if item.prompt_hashes != expected[item.source]["prompts"]:
            raise PipelineError("Semantic Diff Prompt Hash 不匹配", code="semantic_prompt_hash_mismatch", retryable=False)
        if item.schema_hashes != expected[item.source]["schemas"]:
            raise PipelineError("Semantic Diff Schema Hash 不匹配", code="semantic_schema_hash_mismatch", retryable=False)
    if value.diff.blocking_contradictions:
        raise PipelineError("Semantic Contract 存在未解决矛盾", code="semantic_contract_blocked", retryable=False)


def recover_semantic_output(call_dir: Path, bundle: dict[str, Any]) -> tuple[SemanticAdjudicationOutput, dict[str, Any]]:
    """Recover a complete seven-rule response without another Provider call.

    The original response contains all approved product fields but uses composite
    provenance enum strings and groups axis policy into the other resolutions.
    This local recovery normalizes those enums and factors the already-approved
    axis rule into an eighth auditable resolution. It never reads corpus data.
    """

    source_path = call_dir / "repair-raw-response.txt"
    if not source_path.is_file():
        source_path = call_dir / "raw-response.txt"
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    resolutions = payload.get("diff", {}).get("rule_resolutions") or []
    if len(resolutions) != 7:
        raise PipelineError(
            "Semantic 本地恢复只接受完整七规则响应",
            code="semantic_local_recovery_not_applicable",
            retryable=False,
        )
    transformations: list[dict[str, Any]] = []
    allowed = {"approved_product_definition", "A", "B", "C1", "synthesis"}
    for item in resolutions:
        before = str(item.get("adopted_from") or "")
        if before in allowed:
            continue
        after = (
            "synthesis"
            if "+" in before
            else "approved_product_definition"
            if before.startswith("approved_product")
            else "synthesis"
        )
        item["adopted_from"] = after
        transformations.append({
            "path": f"diff.rule_resolutions.{item.get('rule_id')}.adopted_from",
            "before": before,
            "after": after,
            "kind": "enum_normalization",
        })
    resolutions.append({
        "rule_id": "sr_08",
        "a_rule": "A/B 混合接纳知识、实践、对象与使用情境，缺少统一 Axis Test。",
        "b_rule": "B 与 A 同协议，职业、学习路径和工具对象可能进入 Domain。",
        "c1_rule": "C1 禁止 Use Context 和具体工具，但实际节点仍存在轴边界不一致。",
        "canonical_v2_rule": (
            "稳定知识领域与稳定实践问题空间可以成为 Domain；学习路径、面试用途和"
            "不含稳定问题空间的 Focus Object 必须路由到独立非 Domain 分面。"
        ),
        "resolution_reason": "该规则逐字段来自已批准的 domain_axis_policy，用于补全独立 Axis Resolution。",
        "adopted_from": "approved_product_definition",
        "known_risk": "稳定实践问题空间与使用情境的边界仍需在 unresolved adjudication 中逐项验证。",
    })
    transformations.append({
        "path": "diff.rule_resolutions.sr_08",
        "before": None,
        "after": "factored_from_approved_domain_axis_policy",
        "kind": "approved_rule_factorization",
    })
    value = SemanticAdjudicationOutput.model_validate(payload)
    validate_semantic_output(value, bundle)
    recovery = {
        "version": "semantic-local-recovery-v1",
        "provider_call_count": 0,
        "source_path": source_path.name,
        "source_hash": _hash_file(source_path),
        "transformations": transformations,
        "result_hash": _stable_hash(value.model_dump(mode="json")),
        "created_at": _utc_now(),
    }
    _write_json(call_dir / "semantic-local-recovery-audit.json", recovery)
    _write_json(call_dir / "parsed-output.json", value.model_dump(mode="json"))
    audit_path = call_dir / "audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    repair_path = call_dir / "repair-audit.json"
    audit["repair"] = json.loads(repair_path.read_text(encoding="utf-8")) if repair_path.is_file() else None
    audit.update(status="completed", local_recovery=recovery, finished_at=_utc_now())
    _write_json(audit_path, audit)
    return value, audit


def revise_semantic_contract_once(
    provider_contract: DomainSemanticContractV2,
    provider_diff: SemanticContractDiff,
) -> tuple[FinalDomainSemanticContractV2, SemanticContractDiff, dict[str, Any]]:
    before_contract = provider_contract.model_dump(mode="json")
    after_contract = json.loads(json.dumps(before_contract, ensure_ascii=False))
    after_contract["domain_definition"] = (
        "相对稳定、可长期复用的知识领域或实践问题空间，具有明确边界和长期浏览价值；"
        "其语义边界原则上可容纳多条独立内容，当前证据数量不决定其是否属于 Domain。"
    )
    after_contract["stable_domain_criteria"] = [
        "描述稳定知识领域或稳定实践问题空间，而非表达形式、对象或使用情境",
        "通过 instance、temporal、future collection 与 axis purity 测试",
        "其语义边界原则上可容纳未来多条独立内容",
        "具有长期分类和浏览价值",
        "边界可通过 definition/includes/excludes 解释",
        "成熟 stable 节点应获得多条独立内容支持；证据不足只影响 status，不改变语义类型",
    ]
    after_contract["support_policy"] = {
        "discovery_support_is_provisional": True,
        "assignment_support_is_product_evidence": True,
        "single_evidence_default_status": "weak_or_uncertain",
        "single_evidence_exception": "none_without_explicit_adjudication",
        "multi_evidence_is_stability_signal": True,
        "multi_evidence_is_sufficient": False,
        "multi_evidence_distinct_content_ids_min": 2,
        "cross_run_duplicate_counts_as_new_evidence": False,
        "evidence_affects_status_not_semantic_type": True,
    }
    after_contract["status_definitions"] = {
        "stable": "产品赋值证据要求已满足，语义边界清楚，且没有阻断性未决问题。",
        "probable": "语义边界成立并有至少两个不同内容支持，但产品赋值确认仍不完整。",
        "weak": "语义上可能属于 Domain，但当前只有单一内容证据或长期复用价值尚未验证。",
        "uncertain": "语义类型、边界、粒度或父级仍存在无法安全裁决的问题。",
    }
    after_contract["assignment_rules"] = [
        "顶层节点成为 stable/probable 时必须通过语义边界测试并满足对应 evidence/status 条件",
        "子节点除满足 evidence/status 条件外，还必须通过 parent_entailment 并是父节点语义子集",
        "单一内容证据的 Domain 候选只能保持 weak/uncertain，除非经过显式 adjudication",
        "Topic、Entity、Form、Object、Context 不分配为 Domain 节点，而路由至对应非 Domain 类型",
        "每条内容最多一个 primary Domain、最多两个 secondary Domains，允许诚实拒绝",
        "Trial Assignment 不得创建、重命名、移动或修改 Domain",
    ]
    final_contract = FinalDomainSemanticContractV2.model_validate(after_contract)

    before_diff = provider_diff.model_dump(mode="json")
    after_diff = json.loads(json.dumps(before_diff, ensure_ascii=False))
    replacements = {
        "sr_01": (
            "证据数量不决定候选是否属于 Domain；single Evidence 通过语义测试后可保留为 weak/uncertain；"
            "至少两个不同 content_id 是成熟度信号，但仍不足以单独决定 status。"
        ),
        "sr_03": (
            "Discovery support 是候选发现血缘；Assignment support 是产品赋值证据。两者分开记录，"
            "且同一 content_id 跨 Run 重复出现不增加独立内容证据计数。"
        ),
        "sr_06": (
            "单一内容证据的 Domain 候选默认 weak/uncertain，不得由模型以 foundational 为由自动晋升；"
            "任何例外必须经过显式 adjudication。"
        ),
    }
    for item in after_diff["rule_resolutions"]:
        if item["rule_id"] in replacements:
            item["canonical_v2_rule"] = replacements[item["rule_id"]]
            item["adopted_from"] = "approved_product_definition"
            item["known_risk"] = "状态成熟度仍需由 Trial Assignment 和后续 Eval 验证。"
    final_diff = SemanticContractDiff.model_validate(after_diff)

    changes = []
    for field in (
        "domain_definition", "stable_domain_criteria", "support_policy",
        "status_definitions", "assignment_rules",
    ):
        changes.append({
            "field": field,
            "before": before_contract.get(field),
            "after": final_contract.model_dump(mode="json").get(field),
            "reason": "M1 Reviewer blocking fix: separate semantic type from evidence maturity.",
        })
    revision = {
        "version": "domain-semantic-contract-revision-01",
        "provider_call_count": 0,
        "reviewer_verdict_before": "FAIL",
        "changes": changes,
        "diff_rule_changes": sorted(replacements),
        "provider_contract_hash": _stable_hash(before_contract),
        "final_contract_hash": _stable_hash(final_contract.model_dump(mode="json")),
        "provider_diff_hash": _stable_hash(before_diff),
        "final_diff_hash": _stable_hash(final_diff.model_dump(mode="json")),
        "created_at": _utc_now(),
    }
    return final_contract, final_diff, revision


def build_semantic_review_record(
    *,
    contract: FinalDomainSemanticContractV2,
    diff: SemanticContractDiff,
    revision: dict[str, Any],
    verdict: Literal["PASS", "PASS_WITH_CONCERNS", "FAIL"],
    blocking_findings: list[str],
    non_blocking_concerns: list[str],
) -> dict[str, Any]:
    if verdict in {"PASS", "PASS_WITH_CONCERNS"} and blocking_findings:
        raise ValueError("accepted semantic review cannot contain blocking findings")
    if verdict == "FAIL" and not blocking_findings:
        raise ValueError("failed semantic review must explain at least one blocking finding")
    contract_payload = contract.model_dump(mode="json")
    diff_payload = diff.model_dump(mode="json")
    return {
        "version": "domain-semantic-contract-independent-review-v2",
        "reviewer_role": "independent_read_only_technical_reviewer",
        "verdict": verdict,
        "blocking_findings": blocking_findings,
        "non_blocking_concerns": non_blocking_concerns,
        "freeze_eligible": verdict in {"PASS", "PASS_WITH_CONCERNS"},
        "contract_hash": _stable_hash(contract_payload),
        "diff_hash": _stable_hash(diff_payload),
        "revision_hash": _stable_hash(revision),
        "provider_call_count": 0,
        "reviewed_at": _utc_now(),
    }


def _normalized_text(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _character_similarity(left: str, right: str) -> float:
    left_chars = set(_normalized_text(left))
    right_chars = set(_normalized_text(right))
    if not left_chars or not right_chars:
        return 0.0
    return len(left_chars & right_chars) / len(left_chars | right_chars)


def _candidate_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("candidates") or payload.get("domains") or []
    return [dict(row) for row in rows]


def _profile_rows(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        content_id = str(row.get("content_id") or "")
        if content_id:
            result[content_id] = row
    return result


def _unresolved_groups(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """De-duplicate only strong cross-run semantic matches while retaining provenance."""

    groups: list[list[dict[str, Any]]] = []
    for row in sorted(rows, key=lambda item: (item["source_run"], item["candidate_id"])):
        row_evidence = set(row["candidate"].get("supporting_ids") or [])
        row_text = " ".join(
            [row["candidate"].get("name", ""), row["candidate"].get("definition", "")]
        )
        destination = None
        for group in groups:
            if any(existing["source_run"] == row["source_run"] for existing in group):
                continue
            for existing in group:
                existing_evidence = set(existing["candidate"].get("supporting_ids") or [])
                existing_text = " ".join(
                    [
                        existing["candidate"].get("name", ""),
                        existing["candidate"].get("definition", ""),
                    ]
                )
                if row_evidence & existing_evidence and _character_similarity(row_text, existing_text) >= 0.12:
                    destination = group
                    break
            if destination is not None:
                break
        if destination is None:
            groups.append([row])
        else:
            destination.append(row)
    return groups


def _semantic_score(
    *, candidate: dict[str, Any], evidence_ids: set[str], text: str,
) -> float:
    target_evidence = set(candidate.get("evidence_pool_ids") or candidate.get("supporting_ids") or [])
    overlap = len(evidence_ids & target_evidence) / max(1, len(evidence_ids | target_evidence))
    candidate_text = " ".join(
        str(value)
        for value in [
            candidate.get("name", ""),
            candidate.get("definition", ""),
            " ".join(candidate.get("canonical_includes") or candidate.get("includes") or []),
        ]
    )
    return 5.0 * overlap + 2.0 * _character_similarity(text, candidate_text)


def build_unresolved_adjudication_bundle(
    *,
    run_a_dir: Path,
    run_b_dir: Path,
    run_c1_dir: Path,
    checkpoint_312c_dir: Path,
    profile_path: Path,
    semantic_contract_path: Path,
) -> dict[str, Any]:
    paths = {
        "A_candidates": run_a_dir / "candidate-normalization/compact-candidates.json",
        "B_candidates": run_b_dir / "candidate-normalization/compact-candidates.json",
        "C1_candidates": run_c1_dir / "candidate-normalization/compact-candidates.json",
        "A_contract": checkpoint_312c_dir / "run-a-domain-contract-v2.json",
        "B_contract": checkpoint_312c_dir / "run-b-domain-contract-v2.json",
        "C1_contract": run_c1_dir / "run-c1-domain-contract-v2.json",
        "B_decisions": checkpoint_312c_dir / "candidate-decisions-complete-v1.json",
        "C1_decisions": run_c1_dir / "run-c1-candidate-decisions-complete.json",
        "profiles": profile_path,
        "semantic_contract": semantic_contract_path,
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"unresolved bundle sources missing: {missing}")

    candidate_tables = {
        source: _candidate_rows(paths[f"{source}_candidates"])
        for source in ("A", "B", "C1")
    }
    candidate_maps = {
        source: {str(row["candidate_id"]): row for row in rows}
        for source, rows in candidate_tables.items()
    }
    decision_rows: list[dict[str, Any]] = []
    for source in ("B", "C1"):
        payload = json.loads(paths[f"{source}_decisions"].read_text(encoding="utf-8"))
        for decision in payload["candidate_decisions"]:
            if decision["action"] != "unresolved_requires_new_domain":
                continue
            candidate_id = str(decision["candidate_id"])
            decision_rows.append({
                "source_run": source,
                "candidate_id": candidate_id,
                "candidate": candidate_maps[source][candidate_id],
                "historical_decision": {
                    key: decision.get(key)
                    for key in (
                        "action", "confidence", "definition_comparison", "evidence_assessment",
                        "granularity_assessment", "reason", "decision_source",
                    )
                },
            })
    source_counts = Counter(row["source_run"] for row in decision_rows)
    if source_counts != Counter({"B": 3, "C1": 10}):
        raise PipelineError(
            f"unresolved source count changed: {dict(source_counts)}",
            code="unresolved_source_drift",
            retryable=False,
        )

    profiles = _profile_rows(profile_path)
    contracts = {
        source: json.loads(paths[f"{source}_contract"].read_text(encoding="utf-8"))["nodes"]
        for source in ("A", "B", "C1")
    }
    groups = []
    for index, source_group in enumerate(_unresolved_groups(decision_rows), start=1):
        evidence_ids = sorted({
            content_id
            for row in source_group
            for content_id in row["candidate"].get("supporting_ids") or []
        })
        text = " ".join(
            f"{row['candidate'].get('name', '')} {row['candidate'].get('definition', '')}"
            for row in source_group
        )
        nearest_nodes = []
        for source, nodes in contracts.items():
            for node in nodes:
                score = _semantic_score(candidate=node, evidence_ids=set(evidence_ids), text=text)
                nearest_nodes.append((score, source, node))
        nearest_nodes.sort(key=lambda item: (-item[0], item[1], str(item[2]["node_id"])))

        related_candidates = []
        source_keys = {(row["source_run"], row["candidate_id"]) for row in source_group}
        for source, candidates in candidate_tables.items():
            for candidate in candidates:
                if (source, str(candidate["candidate_id"])) in source_keys:
                    continue
                score = _semantic_score(candidate=candidate, evidence_ids=set(evidence_ids), text=text)
                related_candidates.append((score, source, candidate))
        related_candidates.sort(
            key=lambda item: (-item[0], item[1], str(item[2]["candidate_id"]))
        )

        profile_views = []
        for content_id in evidence_ids[:5]:
            profile = profiles.get(content_id)
            if profile is None:
                raise PipelineError(
                    f"missing profile for {content_id}",
                    code="unresolved_profile_missing",
                    retryable=False,
                )
            profile_views.append({
                "content_id": content_id,
                "main_subject": profile.get("main_subject"),
                "content_goal": profile.get("content_goal"),
                "key_concepts": list(profile.get("key_concepts") or [])[:5],
                "usage_contexts": list(profile.get("usage_contexts") or [])[:3],
                "entities": list(profile.get("entities") or [])[:5],
                "evidence_level": profile.get("source_evidence_level"),
            })
        groups.append({
            "adjudication_id": f"ua_{index:03d}",
            "sources": [
                {
                    "source_run": row["source_run"],
                    "candidate_id": row["candidate_id"],
                    "candidate_name": row["candidate"]["name"],
                    "definition": row["candidate"]["definition"],
                    "includes": row["candidate"].get("includes") or [],
                    "excludes": row["candidate"].get("excludes") or [],
                    "supporting_ids": row["candidate"].get("supporting_ids") or [],
                    "historical_decision": row["historical_decision"],
                }
                for row in source_group
            ],
            "representative_profiles": profile_views,
            "nearest_existing_nodes": [
                {
                    "ref": f"{source}:{node['node_id']}",
                    "source_run": source,
                    "node_id": node["node_id"],
                    "name": node["name"],
                    "parent_id": node.get("parent_id"),
                    "definition": node["definition"],
                    "includes": node.get("canonical_includes") or [],
                    "excludes": node.get("canonical_excludes") or [],
                    "evidence_pool_ids": node.get("evidence_pool_ids") or [],
                    "local_similarity": round(score, 6),
                }
                for score, source, node in nearest_nodes[:4]
            ],
            "possible_cross_run_candidates": [
                {
                    "ref": f"{source}:{candidate['candidate_id']}",
                    "source_run": source,
                    "candidate_id": candidate["candidate_id"],
                    "name": candidate["name"],
                    "definition": candidate["definition"],
                    "supporting_ids": candidate.get("supporting_ids") or [],
                    "local_similarity": round(score, 6),
                }
                for score, source, candidate in related_candidates[:4]
            ],
        })

    contract = FinalDomainSemanticContractV2.model_validate_json(
        semantic_contract_path.read_text(encoding="utf-8")
    )
    return {
        "version": UNRESOLVED_BUNDLE_VERSION,
        "snapshot_id": 2,
        "snapshot_hash": SNAPSHOT_2_HASH,
        "semantic_contract": contract.model_dump(mode="json"),
        "semantic_contract_hash": _stable_hash(contract.model_dump(mode="json")),
        "source_item_count": len(decision_rows),
        "source_counts": dict(sorted(source_counts.items())),
        "deduplicated_group_count": len(groups),
        "groups": groups,
        "input_hashes": {name: _hash_file(path) for name, path in sorted(paths.items())},
        "protocol_provenance": {
            "A": "Run 12 legacy consolidation evidence source",
            "B": "Run 22 candidate decision plus Evidence Contract v2",
            "C1": "Run 23 two-stage node synthesis and frozen-tree routing",
        },
        "forbidden_inputs": [
            "Silver Reference",
            "Presentation Form results",
            "Focus Object Type results",
            "Suggested Use Context results",
            "folder names",
            "user notes",
            "full 128-card corpus",
        ],
    }


def build_unresolved_adjudication_prompt(
    *, contract: dict[str, Any], groups: list[dict[str, Any]],
) -> str:
    return "\n".join([
        "你是拾流 V3 Domain unresolved adjudicator。只裁决输入中的未决候选，不生成完整 Taxonomy。",
        "必须以冻结的 Domain Semantic Contract v2 为唯一产品语义规则。A/B/C1 是带 provenance 的独立证据源，不得投票，也不得给某个 Run 固定权重。",
        "先判断 Candidate 是否真的是稳定知识领域或稳定实践问题空间，再判断当前 Tree 是否真的缺少承载边界。",
        "学习路径、面试用途、表达形式、对象类型、Topic、Entity 不得成为 Domain。单一算法技巧、单一项目、单一内容标题不能成为稳定 Domain。",
        "证据数只影响成熟状态，不决定语义类型；同一 content_id 跨 Run 重复不算新证据。",
        "只有 adjudication=true_tree_gap 时 recommended_operation 才能是 create_domain_proposal；其他情况绝对不能创建 Domain。",
        "closest_existing_nodes 只能引用输入提供的 ref；若 merge_into_existing，至少给出一个目标。evidence 只能使用本组内容 ID。",
        "reason 必须解释 Axis、粒度、现有节点边界和证据；counterarguments 必须写出最强反方理由。允许 uncertain，不得为减少 Gap 强行晋升。",
        "冻结 Contract：",
        json.dumps(contract, ensure_ascii=False, separators=(",", ":")),
        "本批未决组：",
        json.dumps(groups, ensure_ascii=False, separators=(",", ":")),
        "只输出符合 Schema 的 JSON。",
    ])


def validate_unresolved_batch(
    value: UnresolvedBatchOutput, groups: list[dict[str, Any]],
) -> None:
    expected = {group["adjudication_id"] for group in groups}
    actual = {decision.adjudication_id for decision in value.decisions}
    if actual != expected or len(actual) != len(value.decisions):
        raise PipelineError(
            f"unresolved batch IDs mismatch expected={sorted(expected)} actual={sorted(actual)}",
            code="unresolved_batch_ids_invalid",
            retryable=True,
        )
    groups_by_id = {group["adjudication_id"]: group for group in groups}
    for decision in value.decisions:
        group = groups_by_id[decision.adjudication_id]
        allowed_nodes = {item["ref"] for item in group["nearest_existing_nodes"]}
        if not set(decision.closest_existing_nodes).issubset(allowed_nodes):
            raise PipelineError(
                f"{decision.adjudication_id} contains unknown target node",
                code="unresolved_target_invalid",
                retryable=True,
            )
        allowed_evidence = {
            profile["content_id"] for profile in group["representative_profiles"]
        }
        if not set(decision.evidence).issubset(allowed_evidence):
            raise PipelineError(
                f"{decision.adjudication_id} contains unknown evidence",
                code="unresolved_evidence_invalid",
                retryable=True,
            )


def recover_unresolved_batch(
    call_dir: Path, groups: list[dict[str, Any]],
) -> tuple[UnresolvedBatchOutput, dict[str, Any]]:
    """Remove only out-of-group node refs from an otherwise valid Repair output."""

    source_path = call_dir / "repair-raw-response.txt"
    if not source_path.is_file():
        raise PipelineError(
            "M2 本地恢复缺少 Repair 原文",
            code="unresolved_local_recovery_not_applicable",
            retryable=False,
        )
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    groups_by_id = {group["adjudication_id"]: group for group in groups}
    transformations = []
    for decision in payload.get("decisions") or []:
        adjudication_id = str(decision.get("adjudication_id") or "")
        group = groups_by_id.get(adjudication_id)
        if group is None:
            continue
        allowed = {item["ref"] for item in group["nearest_existing_nodes"]}
        before = list(decision.get("closest_existing_nodes") or [])
        after = [node_ref for node_ref in before if node_ref in allowed]
        if before != after:
            if decision.get("recommended_operation") == "merge_into_existing" and not after:
                raise PipelineError(
                    f"{adjudication_id} 的唯一 merge target 非法，不能本地恢复",
                    code="unresolved_local_recovery_unsafe",
                    retryable=False,
                )
            decision["closest_existing_nodes"] = after
            transformations.append({
                "path": f"decisions.{adjudication_id}.closest_existing_nodes",
                "before": before,
                "after": after,
                "kind": "remove_out_of_group_reference",
            })
    if not transformations:
        raise PipelineError(
            "M2 Repair 没有可识别的局部引用尾差",
            code="unresolved_local_recovery_not_applicable",
            retryable=False,
        )
    value = UnresolvedBatchOutput.model_validate(payload)
    validate_unresolved_batch(value, groups)
    recovery = {
        "version": "unresolved-local-recovery-v1",
        "provider_call_count": 0,
        "source_path": source_path.name,
        "source_hash": _hash_file(source_path),
        "transformations": transformations,
        "result_hash": _stable_hash(value.model_dump(mode="json")),
        "created_at": _utc_now(),
    }
    _write_json(call_dir / "local-recovery-audit.json", recovery)
    _write_json(call_dir / "parsed-output.json", value.model_dump(mode="json"))
    audit_path = call_dir / "audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    repair_path = call_dir / "repair-audit.json"
    audit["repair"] = json.loads(repair_path.read_text(encoding="utf-8"))
    audit.update(status="completed", local_recovery=recovery, finished_at=_utc_now())
    _write_json(audit_path, audit)
    return value, audit


def apply_unresolved_review(
    *,
    draft: dict[str, Any],
    bundle: dict[str, Any],
    review_results: list[dict[str, Any]],
    overrides: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    groups_by_id = {group["adjudication_id"]: group for group in bundle["groups"]}
    review_by_id = {str(item["adjudication_id"]): item for item in review_results}
    expected = set(groups_by_id)
    if set(review_by_id) != expected or len(review_by_id) != len(review_results):
        raise ValueError("unresolved review must cover every adjudication ID exactly once")
    rejected = {
        adjudication_id
        for adjudication_id, item in review_by_id.items()
        if item["reviewer_verdict"] == "reject"
    }
    if not rejected.issubset(overrides):
        raise ValueError("every rejected adjudication requires an explicit override")

    final_decisions = []
    changes = []
    for item in draft["decisions"]:
        adjudication_id = str(item["adjudication_id"])
        before_core = {
            key: item[key]
            for key in (
                "adjudication_id", "adjudication", "recommended_operation",
                "closest_existing_nodes", "evidence", "reason", "counterarguments", "confidence",
            )
        }
        after_core = json.loads(json.dumps(before_core, ensure_ascii=False))
        for key, value in overrides.get(adjudication_id, {}).items():
            if key not in after_core or key == "adjudication_id":
                raise ValueError(f"unsupported unresolved override field: {key}")
            after_core[key] = value
        validated = UnresolvedDecision.model_validate(after_core)
        validate_unresolved_batch(
            UnresolvedBatchOutput(decisions=[validated]),
            [groups_by_id[adjudication_id]],
        )
        review = review_by_id[adjudication_id]
        final_decisions.append({
            "sources": item["sources"],
            **validated.model_dump(mode="json"),
            "reviewer_verdict": review["reviewer_verdict"],
            "review_notes": list(review.get("review_notes") or []),
        })
        if before_core != validated.model_dump(mode="json"):
            changes.append({
                "adjudication_id": adjudication_id,
                "before": before_core,
                "after": validated.model_dump(mode="json"),
                "reason": review.get("review_notes") or [],
            })

    final = {
        "version": "unresolved-adjudication-final-v1",
        "snapshot_id": draft["snapshot_id"],
        "snapshot_hash": draft["snapshot_hash"],
        "semantic_contract_hash": draft["semantic_contract_hash"],
        "source_item_count": draft["source_item_count"],
        "source_counts": draft["source_counts"],
        "deduplicated_group_count": draft["deduplicated_group_count"],
        "decisions": final_decisions,
        "review_status": "READY_FOR_REVIEW_2",
        "created_at": _utc_now(),
    }
    revision = {
        "version": "unresolved-adjudication-revision-01",
        "provider_call_count": 0,
        "reviewer_verdict_before": "FAIL",
        "reviewed_count": len(review_results),
        "rejected_ids": sorted(rejected),
        "changed_ids": [item["adjudication_id"] for item in changes],
        "changes": changes,
        "draft_hash": _stable_hash(draft),
        "final_hash": _stable_hash(final),
        "created_at": _utc_now(),
    }
    return final, revision


class DomainCompletionService:
    def __init__(
        self, *, repository: TaxonomyRepository, run_repository: TaxonomyRunRepository,
        workflow: TaxonomyWorkflow, output_dir: Path,
    ) -> None:
        self.repository = repository
        self.run_repository = run_repository
        self.workflow = workflow
        self.output_dir = output_dir

    def create(self, *, run_a_id: int = 12, run_b_id: int = 22, run_c1_id: int = 23) -> int:
        git_commit, git_clean = _git_state()
        if not git_clean:
            raise PipelineError("创建 Domain Completion 前工作区必须 clean", code="domain_completion_git_dirty", retryable=False)
        snapshot = self.repository.get_snapshot(2)
        if snapshot is None or snapshot["snapshot_hash"] != SNAPSHOT_2_HASH:
            raise PipelineError("Snapshot #2 已改变", code="domain_completion_snapshot_changed", retryable=False)
        runs = {label: self.run_repository.get_run(run_id) for label, run_id in {"A": run_a_id, "B": run_b_id, "C1": run_c1_id}.items()}
        if any(value is None for value in runs.values()):
            raise PipelineError("历史 Domain Run 不完整", code="domain_completion_source_missing", retryable=False)
        base = self.output_dir
        checkpoint = base.parent / "checkpoints" / "checkpoint-312c"
        bundle = build_semantic_audit_bundle(
            run_a_dir=base / f"run-{run_a_id:06d}", run_b_dir=base / f"run-{run_b_id:06d}",
            run_c1_dir=base / f"run-{run_c1_id:06d}", checkpoint_312c_dir=checkpoint,
        )
        source_hashes = {
            label: _stable_hash(payload) for label, payload in bundle["sources"].items()
        }
        protocol = {
            "version": DOMAIN_COMPLETION_PROTOCOL_VERSION,
            "snapshot_id": 2,
            "snapshot_hash": SNAPSHOT_2_HASH,
            "source_run_ids": {"A": run_a_id, "B": run_b_id, "C1": run_c1_id},
            "source_bundle_hashes": source_hashes,
            "semantic_prompt_version": SEMANTIC_STAGE_PROMPT_VERSION,
            "semantic_schema_version": SEMANTIC_STAGE_SCHEMA_VERSION,
            "semantic_schema_hash": _stable_hash(SemanticAdjudicationOutput.model_json_schema()),
            "forbidden_inputs": bundle["forbidden_inputs"],
            "git_commit": git_commit,
            "git_worktree_clean": True,
            "created_at": _utc_now(),
        }
        run_id = self.run_repository.create_run(
            snapshot_id=2, run_kind="domain_completion", engine="domain_completion",
            engine_version=DOMAIN_COMPLETION_ENGINE_VERSION,
            parameters={"protocol_manifest": protocol, "current_milestone": "M1_semantic_contract_v2"},
        )
        run_dir = base / f"run-{run_id:06d}"
        _write_json_once(run_dir / "run-manifest.json", protocol)
        _write_json_once(run_dir / "m1-semantic-audit-bundle.json", bundle)
        return run_id

    def execute(self, run_id: int, *, resume: bool = False) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run is None or run.get("run_kind") != "domain_completion":
            raise PipelineError("不是 Domain Completion Run", code="domain_completion_run_invalid", retryable=False)
        if run.get("current_stage") == "unresolved_adjudication":
            return self.execute_unresolved_adjudication(run_id)
        if run.get("current_stage") in {
            "semantic_contract_v2_review",
            "semantic_contract_v2_review_2",
            "semantic_contract_v2_blocked",
            "unresolved_adjudication_review",
            "unresolved_adjudication_review_2",
            "unresolved_adjudication_blocked",
        }:
            return self.status(run_id)
        protocol = run["parameters"]["protocol_manifest"]
        run_dir = self.output_dir / f"run-{run_id:06d}"
        bundle = json.loads((run_dir / "m1-semantic-audit-bundle.json").read_text(encoding="utf-8"))
        if {
            label: _stable_hash(payload) for label, payload in bundle["sources"].items()
        } != protocol["source_bundle_hashes"]:
            raise PipelineError("历史语义 Bundle 已改变", code="domain_completion_source_drift", retryable=False)
        prompt = build_semantic_adjudication_prompt(bundle)
        stage = self.run_repository.ensure_stage(run_id, "semantic_contract_v2", "main")
        call_dir = run_dir / "semantic_contract_v2" / "main" / "attempt-01"
        if (
            resume
            and stage["status"] == "retry_wait"
            and not (call_dir / "parsed-output.json").is_file()
            and (call_dir / "repair-raw-response.txt").is_file()
        ):
            recovered, audit = recover_semantic_output(call_dir, bundle)
            recovered_payload = recovered.model_dump(mode="json")
            self.run_repository.complete_stage(
                run_id, "semantic_contract_v2", "main",
                output_path=str(call_dir / "parsed-output.json"),
                output_hash=_stable_hash(recovered_payload),
                audit=_combined_audit(audit),
            )
        output = self.workflow._model_stage(
            run_id=run_id, run_dir=run_dir, stage_name="semantic_contract_v2", unit_key="main",
            role="taxonomy_global", prompt=prompt, prompt_version=SEMANTIC_STAGE_PROMPT_VERSION,
            schema=SemanticAdjudicationOutput, schema_hint=SEMANTIC_SCHEMA_HINT, max_tokens=12288,
            input_ids=["RunA", "RunB", "RunC1"],
            validator=lambda value: validate_semantic_output(value, bundle),
        )
        contract = output.contract.model_dump(mode="json")
        diff = output.diff.model_dump(mode="json")
        _write_json(run_dir / "domain-semantic-contract-v2.json", contract)
        _write_json(run_dir / "semantic-contract-diff-a-b-c1.json", diff)
        gate = {
            "version": SEMANTIC_GATE_VERSION,
            "status": "READY_FOR_INDEPENDENT_REVIEW",
            "contract_hash": _stable_hash(contract),
            "diff_hash": _stable_hash(diff),
            "blocking": [],
            "metrics": {
                "rule_resolution_count": len(diff["rule_resolutions"]),
                "source_count": len(diff["sources"]),
                "excluded_dimension_count": len(contract["excluded_dimensions"]),
            },
        }
        _write_json(run_dir / "m1-semantic-contract-gate.json", gate)
        self.run_repository.set_run_status(
            run_id, "waiting_for_review", current_stage="semantic_contract_v2_review",
            error_code=None, error_message=None,
        )
        return self.status(run_id)

    def status(self, run_id: int) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run is None:
            raise LookupError(run_id)
        return {"run": run, "stages": self.run_repository.list_stages(run_id)}

    def revise_semantic_contract(self, run_id: int) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run is None or run.get("run_kind") != "domain_completion":
            raise PipelineError("不是 Domain Completion Run", code="domain_completion_run_invalid", retryable=False)
        run_dir = self.output_dir / f"run-{run_id:06d}"
        revision_path = run_dir / "m1-semantic-contract-revision-01.json"
        if revision_path.exists():
            return json.loads(revision_path.read_text(encoding="utf-8"))
        contract_path = run_dir / "domain-semantic-contract-v2.json"
        diff_path = run_dir / "semantic-contract-diff-a-b-c1.json"
        provider_contract = DomainSemanticContractV2.model_validate_json(contract_path.read_text(encoding="utf-8"))
        provider_diff = SemanticContractDiff.model_validate_json(diff_path.read_text(encoding="utf-8"))
        final_contract, final_diff, revision = revise_semantic_contract_once(provider_contract, provider_diff)
        _write_json_once(run_dir / "domain-semantic-contract-v2.provider-draft.json", provider_contract.model_dump(mode="json"))
        _write_json_once(run_dir / "semantic-contract-diff-a-b-c1.provider-draft.json", provider_diff.model_dump(mode="json"))
        _write_json(contract_path, final_contract.model_dump(mode="json"))
        _write_json(diff_path, final_diff.model_dump(mode="json"))
        _write_json_once(revision_path, revision)
        gate = {
            "version": SEMANTIC_GATE_VERSION,
            "status": "READY_FOR_REVIEW_2",
            "contract_hash": revision["final_contract_hash"],
            "diff_hash": revision["final_diff_hash"],
            "blocking": [],
            "metrics": {
                "rule_resolution_count": len(final_diff.rule_resolutions),
                "source_count": len(final_diff.sources),
                "excluded_dimension_count": len(final_contract.excluded_dimensions),
                "revision_count": 1,
            },
        }
        _write_json(run_dir / "m1-semantic-contract-gate.json", gate)
        self.run_repository.set_run_status(
            run_id, "waiting_for_review", current_stage="semantic_contract_v2_review_2",
            error_code=None, error_message=None,
        )
        return revision

    def record_semantic_review(
        self,
        run_id: int,
        *,
        verdict: Literal["PASS", "PASS_WITH_CONCERNS", "FAIL"],
        blocking_findings: list[str],
        non_blocking_concerns: list[str],
    ) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run is None or run.get("run_kind") != "domain_completion":
            raise PipelineError("不是 Domain Completion Run", code="domain_completion_run_invalid", retryable=False)
        run_dir = self.output_dir / f"run-{run_id:06d}"
        review_path = run_dir / "m1-semantic-contract-review.json"
        if review_path.exists():
            return json.loads(review_path.read_text(encoding="utf-8"))
        contract = FinalDomainSemanticContractV2.model_validate_json(
            (run_dir / "domain-semantic-contract-v2.json").read_text(encoding="utf-8")
        )
        diff = SemanticContractDiff.model_validate_json(
            (run_dir / "semantic-contract-diff-a-b-c1.json").read_text(encoding="utf-8")
        )
        revision = json.loads(
            (run_dir / "m1-semantic-contract-revision-01.json").read_text(encoding="utf-8")
        )
        review = build_semantic_review_record(
            contract=contract,
            diff=diff,
            revision=revision,
            verdict=verdict,
            blocking_findings=blocking_findings,
            non_blocking_concerns=non_blocking_concerns,
        )
        _write_json_once(review_path, review)
        gate = {
            "version": SEMANTIC_GATE_VERSION,
            "status": verdict,
            "contract_hash": review["contract_hash"],
            "diff_hash": review["diff_hash"],
            "blocking": blocking_findings,
            "non_blocking_concerns": non_blocking_concerns,
            "metrics": {
                "rule_resolution_count": len(diff.rule_resolutions),
                "source_count": len(diff.sources),
                "excluded_dimension_count": len(contract.excluded_dimensions),
                "revision_count": 1,
            },
        }
        _write_json(run_dir / "m1-semantic-contract-gate.json", gate)
        if review["freeze_eligible"]:
            self.run_repository.set_run_status(
                run_id, "running", current_stage="unresolved_adjudication",
                error_code=None, error_message=None,
            )
        else:
            self.run_repository.set_run_status(
                run_id, "waiting_for_review", current_stage="semantic_contract_v2_blocked",
                error_code="semantic_contract_review_failed",
                error_message="; ".join(blocking_findings),
            )
        return review

    def execute_unresolved_adjudication(self, run_id: int) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run is None or run.get("run_kind") != "domain_completion":
            raise PipelineError("不是 Domain Completion Run", code="domain_completion_run_invalid", retryable=False)
        run_dir = self.output_dir / f"run-{run_id:06d}"
        semantic_review = json.loads(
            (run_dir / "m1-semantic-contract-review.json").read_text(encoding="utf-8")
        )
        if not semantic_review.get("freeze_eligible"):
            raise PipelineError(
                "Semantic Contract 尚未冻结",
                code="semantic_contract_not_frozen",
                retryable=False,
            )

        checkpoint = self.output_dir.parent / "checkpoints" / "checkpoint-312c"
        run_a_dir = self.output_dir / "run-000012"
        run_b_dir = self.output_dir / "run-000022"
        run_c1_dir = self.output_dir / "run-000023"
        run_a_manifest = json.loads((run_a_dir / "run-manifest.json").read_text(encoding="utf-8"))
        profile_run_id = str(run_a_manifest["profile_run_id"])
        profile_path = (
            self.output_dir.parent / "profile_spikes" / profile_run_id / "profiles.jsonl"
        )
        current_bundle = build_unresolved_adjudication_bundle(
            run_a_dir=run_a_dir,
            run_b_dir=run_b_dir,
            run_c1_dir=run_c1_dir,
            checkpoint_312c_dir=checkpoint,
            profile_path=profile_path,
            semantic_contract_path=run_dir / "domain-semantic-contract-v2.json",
        )
        bundle_path = run_dir / "m2-unresolved-adjudication-bundle.json"
        if bundle_path.exists():
            frozen_bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            if _stable_hash(frozen_bundle) != _stable_hash(current_bundle):
                raise PipelineError(
                    "M2 unresolved 输入已漂移",
                    code="unresolved_bundle_drift",
                    retryable=False,
                )
            bundle = frozen_bundle
        else:
            _write_json_once(bundle_path, current_bundle)
            bundle = current_bundle

        outputs: list[UnresolvedDecision] = []
        groups = list(bundle["groups"])
        batches = [groups[index:index + 4] for index in range(0, len(groups), 4)]
        for batch_index, batch in enumerate(batches, start=1):
            unit_key = f"batch-{batch_index:03d}"
            prompt = build_unresolved_adjudication_prompt(
                contract=bundle["semantic_contract"], groups=batch,
            )
            stage = self.run_repository.ensure_stage(
                run_id, "unresolved_adjudication", unit_key,
            )
            attempt_number = max(1, int(stage["attempt_count"]))
            call_dir = (
                run_dir / "unresolved_adjudication" / unit_key
                / f"attempt-{attempt_number:02d}"
            )
            saved_prompt_path = call_dir / "prompt.txt"
            if saved_prompt_path.is_file():
                prompt = saved_prompt_path.read_text(encoding="utf-8")
            if (
                stage["status"] == "retry_wait"
                and not (call_dir / "parsed-output.json").is_file()
                and (call_dir / "repair-raw-response.txt").is_file()
            ):
                recovered, audit = recover_unresolved_batch(call_dir, batch)
                recovered_payload = recovered.model_dump(mode="json")
                self.run_repository.complete_stage(
                    run_id, "unresolved_adjudication", unit_key,
                    output_path=str(call_dir / "parsed-output.json"),
                    output_hash=_stable_hash(recovered_payload),
                    audit=_combined_audit(audit),
                )
            output = self.workflow._model_stage(
                run_id=run_id,
                run_dir=run_dir,
                stage_name="unresolved_adjudication",
                unit_key=unit_key,
                role="taxonomy_global",
                prompt=prompt,
                prompt_version=UNRESOLVED_PROMPT_VERSION,
                schema=UnresolvedBatchOutput,
                schema_hint=UNRESOLVED_SCHEMA_HINT,
                max_tokens=6144,
                input_ids=[group["adjudication_id"] for group in batch],
                validator=lambda value, expected=batch: validate_unresolved_batch(value, expected),
            )
            outputs.extend(output.decisions)

        decisions_by_id = {decision.adjudication_id: decision for decision in outputs}
        draft = {
            "version": "unresolved-adjudication-draft-v1",
            "snapshot_id": 2,
            "snapshot_hash": SNAPSHOT_2_HASH,
            "semantic_contract_hash": bundle["semantic_contract_hash"],
            "source_item_count": bundle["source_item_count"],
            "source_counts": bundle["source_counts"],
            "deduplicated_group_count": bundle["deduplicated_group_count"],
            "decisions": [
                {
                    "adjudication_id": group["adjudication_id"],
                    "sources": [
                        {
                            key: source[key]
                            for key in ("source_run", "candidate_id", "candidate_name")
                        }
                        for source in group["sources"]
                    ],
                    **decisions_by_id[group["adjudication_id"]].model_dump(mode="json"),
                    "reviewer_verdict": "pending",
                    "review_notes": [],
                }
                for group in groups
            ],
            "batch_count": len(batches),
            "provider_call_policy": "one high-thinking call per incomplete batch; at most one JSON repair",
            "created_at": _utc_now(),
        }
        _write_json(run_dir / "unresolved-adjudication-draft.json", draft)
        gate = {
            "version": "unresolved-adjudication-gate-v1",
            "status": "READY_FOR_INDEPENDENT_REVIEW",
            "draft_hash": _stable_hash(draft),
            "decision_count": len(draft["decisions"]),
            "source_item_count": draft["source_item_count"],
            "blocking": [],
        }
        _write_json(run_dir / "m2-unresolved-adjudication-gate.json", gate)
        self.run_repository.set_run_status(
            run_id, "waiting_for_review", current_stage="unresolved_adjudication_review",
            error_code=None, error_message=None,
        )
        return self.status(run_id)

    def revise_unresolved_adjudication(
        self,
        run_id: int,
        *,
        review_results: list[dict[str, Any]],
        overrides: dict[str, dict[str, Any]],
        blocking_findings: list[str],
        non_blocking_concerns: list[str],
    ) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run is None or run.get("run_kind") != "domain_completion":
            raise PipelineError("不是 Domain Completion Run", code="domain_completion_run_invalid", retryable=False)
        run_dir = self.output_dir / f"run-{run_id:06d}"
        revision_path = run_dir / "m2-unresolved-adjudication-revision-01.json"
        if revision_path.exists():
            return json.loads(revision_path.read_text(encoding="utf-8"))
        bundle = json.loads(
            (run_dir / "m2-unresolved-adjudication-bundle.json").read_text(encoding="utf-8")
        )
        draft = json.loads(
            (run_dir / "unresolved-adjudication-draft.json").read_text(encoding="utf-8")
        )
        review = {
            "version": "unresolved-adjudication-independent-review-v1",
            "verdict": "FAIL",
            "blocking_findings": blocking_findings,
            "non_blocking_concerns": non_blocking_concerns,
            "results": review_results,
            "provider_call_count": 0,
            "draft_hash": _stable_hash(draft),
            "reviewed_at": _utc_now(),
        }
        final, revision = apply_unresolved_review(
            draft=draft,
            bundle=bundle,
            review_results=review_results,
            overrides=overrides,
        )
        _write_json_once(run_dir / "m2-unresolved-independent-review.json", review)
        _write_json_once(run_dir / "unresolved-adjudication-final.json", final)
        _write_json_once(revision_path, revision)
        gate = {
            "version": "unresolved-adjudication-gate-v1",
            "status": "READY_FOR_REVIEW_2",
            "final_hash": revision["final_hash"],
            "decision_count": len(final["decisions"]),
            "source_item_count": final["source_item_count"],
            "revision_count": 1,
            "blocking": [],
        }
        _write_json(run_dir / "m2-unresolved-adjudication-gate.json", gate)
        self.run_repository.set_run_status(
            run_id, "waiting_for_review", current_stage="unresolved_adjudication_review_2",
            error_code=None, error_message=None,
        )
        return revision

    def record_unresolved_final_review(
        self,
        run_id: int,
        *,
        verdict: Literal["PASS", "PASS_WITH_CONCERNS", "FAIL"],
        blocking_findings: list[str],
        non_blocking_concerns: list[str],
    ) -> dict[str, Any]:
        if verdict in {"PASS", "PASS_WITH_CONCERNS"} and blocking_findings:
            raise ValueError("accepted M2 review cannot contain blocking findings")
        if verdict == "FAIL" and not blocking_findings:
            raise ValueError("failed M2 review must contain blocking findings")
        run = self.run_repository.get_run(run_id)
        if run is None or run.get("run_kind") != "domain_completion":
            raise PipelineError("不是 Domain Completion Run", code="domain_completion_run_invalid", retryable=False)
        run_dir = self.output_dir / f"run-{run_id:06d}"
        review_path = run_dir / "m2-unresolved-final-review.json"
        if review_path.exists():
            return json.loads(review_path.read_text(encoding="utf-8"))
        final = json.loads(
            (run_dir / "unresolved-adjudication-final.json").read_text(encoding="utf-8")
        )
        review = {
            "version": "unresolved-adjudication-final-review-v1",
            "reviewer_role": "independent_read_only_counterexample_reviewer",
            "verdict": verdict,
            "blocking_findings": blocking_findings,
            "non_blocking_concerns": non_blocking_concerns,
            "final_hash": _stable_hash(final),
            "provider_call_count": 0,
            "reviewed_at": _utc_now(),
        }
        _write_json_once(review_path, review)
        gate = {
            "version": "unresolved-adjudication-gate-v1",
            "status": verdict,
            "final_hash": review["final_hash"],
            "decision_count": len(final["decisions"]),
            "source_item_count": final["source_item_count"],
            "revision_count": 1,
            "blocking": blocking_findings,
            "non_blocking_concerns": non_blocking_concerns,
        }
        _write_json(run_dir / "m2-unresolved-adjudication-gate.json", gate)
        if verdict in {"PASS", "PASS_WITH_CONCERNS"}:
            self.run_repository.set_run_status(
                run_id, "running", current_stage="cross_run_alignment",
                error_code=None, error_message=None,
            )
        else:
            self.run_repository.set_run_status(
                run_id, "waiting_for_review", current_stage="unresolved_adjudication_blocked",
                error_code="unresolved_final_review_failed",
                error_message="; ".join(blocking_findings),
            )
        return review
