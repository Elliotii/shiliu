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
from shiliu.taxonomy.workflow import TaxonomyWorkflow


DOMAIN_COMPLETION_ENGINE_VERSION = "domain-completion-mission-v1"
DOMAIN_COMPLETION_PROTOCOL_VERSION = "domain-completion-protocol-v1"
SEMANTIC_CONTRACT_VERSION = "domain-semantic-contract-v2"
SEMANTIC_DIFF_VERSION = "semantic-contract-diff-a-b-c1-v1"
SEMANTIC_STAGE_PROMPT_VERSION = "domain-semantic-contract-adjudication-v1"
SEMANTIC_STAGE_SCHEMA_VERSION = "domain-semantic-contract-adjudication-schema-v1"
SEMANTIC_GATE_VERSION = "domain-semantic-contract-v2-gate-v1"
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
                item["raw_sha256"]
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
        protocol = run["parameters"]["protocol_manifest"]
        run_dir = self.output_dir / f"run-{run_id:06d}"
        bundle = json.loads((run_dir / "m1-semantic-audit-bundle.json").read_text(encoding="utf-8"))
        if {
            label: _stable_hash(payload) for label, payload in bundle["sources"].items()
        } != protocol["source_bundle_hashes"]:
            raise PipelineError("历史语义 Bundle 已改变", code="domain_completion_source_drift", retryable=False)
        prompt = build_semantic_adjudication_prompt(bundle)
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
