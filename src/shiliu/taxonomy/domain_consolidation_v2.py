from __future__ import annotations

import fnmatch
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.domain import PipelineError
from shiliu.taxonomy.candidates import (
    CANDIDATE_NORMALIZATION_VERSION,
    LOCAL_TOP_LEVEL_PROMPT_VERSION,
    LOCAL_TOP_LEVEL_SCHEMA_HINT,
    LOCAL_TOP_LEVEL_SCHEMA_VERSION,
    CompactCandidateTable,
    LocalTopLevelDiscoveryOutput,
    build_top_level_local_prompt,
    normalized_name,
    validate_local_top_level,
)
from shiliu.taxonomy.checkpoint312c import (
    DOMAIN_EVIDENCE_ADAPTER_VERSION,
    DOMAIN_EVIDENCE_CONTRACT_VERSION,
    adapt_domain_contract,
    validate_hierarchy_v2,
)
from shiliu.taxonomy.controlled_facets import (
    _git_state,
    _hash_file,
    _stable_hash,
    _utc_now,
    _write_json,
    _write_json_once,
)
from shiliu.taxonomy.domain_stability import _domain_provider_manifest
from shiliu.taxonomy.repository import TaxonomyRepository
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from shiliu.taxonomy.workflow import TaxonomyWorkflow


HASH_ALGORITHM_NAME = "sha256-tree"
HASH_ALGORITHM_VERSION = "v2"
HASH_EXCLUDED_PATTERNS = (".DS_Store", "*.tmp", "__pycache__/*", "final-artifact-manifest.json")
SEMANTIC_CONTRACT_VERSION = "domain-semantic-contract-v1"
EXECUTION_CONTRACT_VERSION = "domain-consolidation-execution-contract-v2"
RUN_C1_PROTOCOL_VERSION = "checkpoint312d-run-c1-v1"
RUN_C1_ENGINE_VERSION = "domain-consolidation-v2-engine-v1"
NODE_SYNTHESIS_PROMPT_VERSION = "domain-node-synthesis-v1"
NODE_SYNTHESIS_SCHEMA_VERSION = "domain-node-synthesis-schema-v1"
ROUTING_PROMPT_VERSION = "batched-candidate-routing-v1"
ROUTING_SCHEMA_VERSION = "candidate-routing-schema-v1"
RUN_C1_GATE_VERSION = "checkpoint312d-run-c1-gate-v1"
ROUTING_BATCH_SIZE = 12


DOMAIN_SEMANTIC_CONTRACT = {
    "version": SEMANTIC_CONTRACT_VERSION,
    "question": "内容属于什么相对稳定、可长期复用的知识领域？",
    "stable_domain_requirements": [
        "描述知识领域或相对稳定的问题空间",
        "能被多条内容共同支持",
        "具有长期分类和浏览价值",
        "最多形成两级层级",
        "边界可通过 definition/includes/excludes 解释",
    ],
    "forbidden_domain_kinds": [
        "presentation_form", "focus_object_type", "use_context", "tool", "model",
        "project", "product", "person", "company", "single_paper", "single_event",
        "temporary_hotspot", "single_title_topic", "narrow_implementation_detail",
        "unsupported_concept",
    ],
    "candidate_actions": [
        "merge_into_existing_domain", "downgrade_to_topic", "downgrade_to_entity",
        "remove_as_unsupported", "unresolved_requires_new_domain",
    ],
    "hierarchy_meaning": "子节点概念范围是父节点概念范围的更具体子集",
    "hierarchy_non_requirement": "子节点 Evidence 不必包含在父节点模型选择 Evidence 中",
}


def semantic_contract_hash() -> str:
    return _stable_hash(DOMAIN_SEMANTIC_CONTRACT)


def hash_contract() -> dict[str, Any]:
    return {
        "tree_hash_algorithm": HASH_ALGORITHM_NAME,
        "tree_hash_algorithm_version": HASH_ALGORITHM_VERSION,
        "included_path_policy": "relative POSIX paths; regular files only",
        "excluded_path_policy": list(HASH_EXCLUDED_PATTERNS),
        "canonicalization_policy": "relative_posix_lexicographic; raw file bytes",
        "file_content_hash": "sha256",
        "symlink_policy": "reject",
        "line_ending_policy": "raw_bytes",
    }


def versioned_tree_hash(path: Path) -> dict[str, Any]:
    entries: list[dict[str, str]] = []
    for value in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        relative = value.relative_to(path).as_posix()
        if value.is_symlink():
            raise ValueError(f"tree hash rejects symlink: {relative}")
        if not value.is_file() or any(fnmatch.fnmatch(relative, pattern) for pattern in HASH_EXCLUDED_PATTERNS):
            continue
        entries.append({"path": relative, "sha256": _hash_file(value)})
    return {**hash_contract(), "tree_hash": _stable_hash(entries), "file_count": len(entries), "files": entries}


class SynthesizedDomainNode(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    node_id: str = Field(pattern=r"^c1_d_[0-9]{2}(?:_[0-9]{2})?$")
    name: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1, max_length=300)
    canonical_includes: list[str] = Field(min_length=1, max_length=12)
    canonical_excludes: list[str] = Field(min_length=1, max_length=12)
    parent_id: str | None = Field(default=None, pattern=r"^c1_d_[0-9]{2}$")
    model_selected_evidence_ids: list[str] = Field(min_length=1, max_length=64)
    representative_ids: list[str] = Field(min_length=1, max_length=5)
    confidence: Literal["high", "medium", "low"]


class DomainNodeSynthesisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    domain_nodes: list[SynthesizedDomainNode] = Field(min_length=1, max_length=48)
    synthesis_notes: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_tree(self):
        ids = [item.node_id for item in self.domain_nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("node IDs must be unique")
        names = [normalized_name(item.name) for item in self.domain_nodes]
        if len(names) != len(set(names)):
            raise ValueError("node names must be unique")
        by_id = {item.node_id: item for item in self.domain_nodes}
        if not any(item.parent_id is None for item in self.domain_nodes):
            raise ValueError("at least one top-level Domain is required")
        for item in self.domain_nodes:
            if item.parent_id is not None:
                parent = by_id.get(item.parent_id)
                if parent is None or parent.parent_id is not None or parent.node_id == item.node_id:
                    raise ValueError("invalid parent or depth exceeds two")
            if not set(item.representative_ids) <= set(item.model_selected_evidence_ids):
                raise ValueError("representatives must belong to model evidence")
        return self


class RoutingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    candidate_id: str = Field(pattern=r"^nc_[0-9]{3}$")
    action: Literal[
        "merge_into_existing_domain", "downgrade_to_topic", "downgrade_to_entity",
        "remove_as_unsupported", "unresolved_requires_new_domain",
    ]
    target_id: str | None = Field(default=None, pattern=r"^c1_d_[0-9]{2}(?:_[0-9]{2})?$")
    reason: str = Field(min_length=1, max_length=500)
    definition_comparison: str = Field(min_length=1, max_length=500)
    granularity_assessment: str = Field(min_length=1, max_length=500)
    evidence_assessment: str = Field(min_length=1, max_length=500)
    confidence: Literal["high", "medium", "low"]

    @model_validator(mode="after")
    def validate_target(self):
        if self.action == "merge_into_existing_domain" and self.target_id is None:
            raise ValueError("merge requires target")
        if self.action in {"unresolved_requires_new_domain", "downgrade_to_entity", "remove_as_unsupported"} and self.target_id is not None:
            raise ValueError(f"{self.action} requires target=null")
        return self


class CandidateRoutingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    candidate_decisions: list[RoutingDecision] = Field(min_length=1, max_length=15)


NODE_SCHEMA_HINT = (
    '{"domain_nodes":[{"node_id":"c1_d_01","name":"","definition":"",'
    '"canonical_includes":[""],"canonical_excludes":[""],"parent_id":null,'
    '"model_selected_evidence_ids":["C001"],"representative_ids":["C001"],'
    '"confidence":"high|medium|low"}],"synthesis_notes":[]}'
)
ROUTING_SCHEMA_HINT = (
    '{"candidate_decisions":[{"candidate_id":"nc_001",'
    '"action":"merge_into_existing_domain|downgrade_to_topic|downgrade_to_entity|'
    'remove_as_unsupported|unresolved_requires_new_domain","target_id":"c1_d_01|null",'
    '"reason":"","definition_comparison":"","granularity_assessment":"",'
    '"evidence_assessment":"","confidence":"high|medium|low"}]}'
)


def build_node_synthesis_prompt(candidates: list[dict[str, Any]]) -> str:
    compact = [
        {key: item.get(key) for key in (
            "candidate_id", "name", "definition", "includes", "excludes",
            "supporting_ids", "representative_ids", "confidence",
        )}
        for item in candidates
    ]
    return (
        "你是 Domain Node Synthesis。严格遵守给定 Domain Semantic Contract，读取完整候选表，"
        "生成最多两级的稳定 Domain Tree。不得使用固定 Top-K，不得输出 Candidate Decisions，"
        "不得把 Form、Use Context、具体实体、单次事件、临时热点或单样本偶然 Topic 提升为 Domain。"
        "单样本候选只有在定义稳定且长期可复用时才能影响节点语义，但不能自动成为节点。"
        "node_id 使用 c1_d_01 或 c1_d_01_01；parent_id 只能指向一级节点。"
        "canonical includes/excludes 最多各12条；证据只保存有解释价值的合法 C ID；代表内容最多5条"
        "且必须属于模型证据。只输出 JSON。\n"
        f"Semantic Contract:{json.dumps(DOMAIN_SEMANTIC_CONTRACT, ensure_ascii=False, separators=(',', ':'))}\n"
        f"Schema:{NODE_SCHEMA_HINT}\n"
        f"Complete Candidate Table:{json.dumps(compact, ensure_ascii=False, separators=(',', ':'))}"
    )


def build_routing_prompt(
    candidates: list[dict[str, Any]], tree: DomainNodeSynthesisOutput,
    *, completed_ids: list[str],
) -> str:
    frozen_tree = [item.model_dump(mode="json") for item in tree.domain_nodes]
    return (
        "你是 Batched Candidate Routing。Domain Tree 已冻结，不得创建、修改、重命名、删除或移动节点。"
        "为当前批每个 Candidate 恰好输出一条 Decision，顺序与输入一致。不能强迫合并；若候选可能是"
        "稳定新领域但现有树无法容纳，使用 unresolved_requires_new_domain。Topic 的 target 只是归属参考。"
        "只输出 JSON。\n"
        f"Semantic Contract:{json.dumps(DOMAIN_SEMANTIC_CONTRACT, ensure_ascii=False, separators=(',', ':'))}\n"
        f"Schema:{ROUTING_SCHEMA_HINT}\n"
        f"Completed IDs only:{json.dumps(completed_ids, ensure_ascii=False)}\n"
        f"Frozen Tree:{json.dumps(frozen_tree, ensure_ascii=False, separators=(',', ':'))}\n"
        f"Current Batch:{json.dumps(candidates, ensure_ascii=False, separators=(',', ':'))}"
    )


def validate_node_synthesis(
    value: DomainNodeSynthesisOutput, *, allowed_evidence_ids: set[str],
) -> None:
    used = {item for node in value.domain_nodes for item in node.model_selected_evidence_ids}
    if not used <= allowed_evidence_ids:
        raise PipelineError("Node Synthesis 引用了未知证据", code="c1_node_evidence_invalid", retryable=False)


def validate_routing(
    value: CandidateRoutingOutput, *, expected_ids: list[str], node_ids: set[str],
) -> None:
    actual = [item.candidate_id for item in value.candidate_decisions]
    if actual != expected_ids:
        raise PipelineError("Routing Coverage 不匹配", code="c1_routing_coverage_mismatch", retryable=False)
    for item in value.candidate_decisions:
        if item.target_id is not None and item.target_id not in node_ids:
            raise PipelineError("Routing target 非法", code="c1_routing_target_invalid", retryable=False)


def enrich_candidate_lineage(
    table: CompactCandidateTable, outputs: list[LocalTopLevelDiscoveryOutput],
) -> list[dict[str, Any]]:
    batch_by_name: dict[str, list[str]] = {}
    for index, output in enumerate(outputs, start=1):
        for item in output.domains:
            batch_by_name.setdefault(normalized_name(item.name), []).append(f"batch-{index:03d}")
    enriched: list[dict[str, Any]] = []
    for item in table.domains:
        value = item.model_dump(mode="json")
        value["source_batch_ids"] = list(dict.fromkeys(batch_by_name.get(normalized_name(item.name), [])))
        enriched.append(value)
    return enriched


def deterministic_routing_batches(candidates: list[dict[str, Any]], size: int = ROUTING_BATCH_SIZE) -> list[list[dict[str, Any]]]:
    if size < 10 or size > 15:
        raise ValueError("routing batch size must be 10..15")
    return [candidates[index:index + size] for index in range(0, len(candidates), size)]


def assemble_decisions(
    candidates: list[dict[str, Any]], routed: list[tuple[str, CandidateRoutingOutput, str]],
) -> list[dict[str, Any]]:
    expected = [item["candidate_id"] for item in candidates]
    result: list[dict[str, Any]] = []
    for unit_key, output, response_hash in routed:
        result.extend({
            **item.model_dump(mode="json"),
            "decision_source": "batched_candidate_routing",
            "source_attempt": f"{unit_key}/attempt-01",
            "source_response_hash": response_hash,
        } for item in output.candidate_decisions)
    actual = [item["candidate_id"] for item in result]
    if actual != expected or len(actual) != len(set(actual)):
        raise PipelineError("C1 Candidate Coverage 未达到100%", code="c1_assembly_coverage_failed", retryable=False)
    return result


def nodes_to_nested_domains(tree: DomainNodeSynthesisOutput) -> list[dict[str, Any]]:
    parents: dict[str, dict[str, Any]] = {}
    children: dict[str, list[dict[str, Any]]] = {}
    for node in tree.domain_nodes:
        value = {
            "id": node.node_id, "name": node.name, "definition": node.definition,
            "includes": list(node.canonical_includes), "excludes": list(node.canonical_excludes),
            "supporting_ids": list(node.model_selected_evidence_ids),
            "representative_ids": list(node.representative_ids),
        }
        if node.parent_id is None:
            parents[node.node_id] = {**value, "children": []}
        else:
            children.setdefault(node.parent_id, []).append({**value, "parent_id": node.parent_id})
    for parent_id, values in children.items():
        parents[parent_id]["children"] = values
    return list(parents.values())


class DomainConsolidationV2Service:
    def __init__(
        self, *, repository: TaxonomyRepository, run_repository: TaxonomyRunRepository,
        workflow: TaxonomyWorkflow, output_dir: Path,
    ) -> None:
        self.repository = repository
        self.run_repository = run_repository
        self.workflow = workflow
        self.output_dir = output_dir

    def create_run_c1(self, *, source_run_id: int = 12, seed: int = 303) -> int:
        if seed != 303:
            raise ValueError("Run C1 seed is frozen to 303")
        git_commit, git_clean = _git_state()
        if not git_clean:
            raise PipelineError("创建 C1 前工作区必须干净", code="c1_git_dirty", retryable=False)
        source = self.run_repository.get_run(source_run_id)
        if source is None:
            raise LookupError(source_run_id)
        source_protocol = source["parameters"]["protocol_manifest"]
        snapshot = self.repository.get_snapshot(int(source["corpus_snapshot_id"]))
        if snapshot is None or snapshot["snapshot_hash"] != source_protocol["snapshot_hash"]:
            raise PipelineError("Snapshot #2 已改变", code="c1_snapshot_changed", retryable=False)
        selected_ids = list(source["parameters"]["selected_ids"])
        if len(selected_ids) != 128:
            raise PipelineError("C1 必须使用128条 Eligible Cards", code="c1_card_count_invalid", retryable=False)
        providers = {role: _domain_provider_manifest(self.workflow.provider_factory(role)) for role in ("taxonomy_local", "taxonomy_global", "taxonomy_repair")}
        expected = {role: source_protocol["providers"][role] for role in providers}
        order = list(selected_ids)
        random.Random(seed).shuffle(order)
        local_batches = [order[index:index + 24] for index in range(0, len(order), 24)]
        semantic_hash = semantic_contract_hash()
        execution_contract = {
            "version": EXECUTION_CONTRACT_VERSION,
            "stages": ["domain_node_synthesis", "batched_candidate_routing", "coverage_consistency_assembly"],
            "semantic_contract_hash": semantic_hash,
        }
        comparability = {
            "version": "run-c1-comparability-audit-v1",
            "same_snapshot": snapshot["snapshot_hash"] == source_protocol["snapshot_hash"],
            "same_eligible_ids": set(order) == set(selected_ids),
            "same_semantic_contract": True,
            "same_local_discovery_semantics": source_protocol["domain_prompt_version"] == LOCAL_TOP_LEVEL_PROMPT_VERSION and source_protocol["domain_schema_version"] == LOCAL_TOP_LEVEL_SCHEMA_VERSION,
            "same_normalize_semantics": source_protocol["domain_normalization_version"] == CANDIDATE_NORMALIZATION_VERSION,
            "same_provider_contract": providers == expected,
            "execution_contract_changed": True,
            "allowed_differences": ["seed", "card_order", "local_batch_members", "candidate_order", "routing_batch_members", "consolidation_serialization_and_recovery"],
            "unexpected_differences": [],
        }
        checks = [value for key, value in comparability.items() if key.startswith("same_")]
        comparability["verdict"] = "PASS" if all(checks) else "STOP_BEFORE_PROVIDER_CALL"
        if comparability["verdict"] != "PASS":
            raise PipelineError("C1 可比性审计失败", code="c1_comparability_failed", retryable=False)
        protocol = {
            "protocol_version": RUN_C1_PROTOCOL_VERSION,
            "protocol_family": "v2", "run_label": "C1", "seed": seed,
            "source_run_a_id": source_run_id,
            "snapshot_id": snapshot["id"], "snapshot_hash": snapshot["snapshot_hash"],
            "eligible_count": 128, "global_card_order": order,
            "local_batch_size": 24, "local_batch_members": local_batches,
            "local_discovery_prompt_version": LOCAL_TOP_LEVEL_PROMPT_VERSION,
            "local_discovery_schema_version": LOCAL_TOP_LEVEL_SCHEMA_VERSION,
            "normalize_version": CANDIDATE_NORMALIZATION_VERSION,
            "semantic_contract_version": SEMANTIC_CONTRACT_VERSION,
            "semantic_contract_hash": semantic_hash,
            "semantic_contract_canonical_json": DOMAIN_SEMANTIC_CONTRACT,
            "execution_contract": execution_contract,
            "node_synthesis_prompt_version": NODE_SYNTHESIS_PROMPT_VERSION,
            "node_synthesis_schema_version": NODE_SYNTHESIS_SCHEMA_VERSION,
            "node_schema_hash": _stable_hash(DomainNodeSynthesisOutput.model_json_schema()),
            "routing_prompt_version": ROUTING_PROMPT_VERSION,
            "routing_schema_version": ROUTING_SCHEMA_VERSION,
            "routing_schema_hash": _stable_hash(CandidateRoutingOutput.model_json_schema()),
            "routing_batch_size": ROUTING_BATCH_SIZE,
            "evidence_contract_version": DOMAIN_EVIDENCE_CONTRACT_VERSION,
            "evidence_adapter_version": DOMAIN_EVIDENCE_ADAPTER_VERSION,
            "gate_version": RUN_C1_GATE_VERSION,
            "hash_contract": hash_contract(),
            "providers": providers,
            "forbidden_inputs": ["Run B taxonomy", "Run B unresolved decisions", "Silver Reference", "controlled facets", "folder names"],
            "git_commit": git_commit, "git_worktree_clean": True,
            "created_at": _utc_now(),
        }
        run_id = self.run_repository.create_run(
            snapshot_id=int(snapshot["id"]), run_kind="domain_consolidation_v2",
            engine="domain_consolidation_v2", engine_version=RUN_C1_ENGINE_VERSION,
            parameters={"snapshot_hash": snapshot["snapshot_hash"], "selected_ids": selected_ids, "protocol_manifest": protocol},
        )
        run_dir = self.output_dir / f"run-{run_id:06d}"
        _write_json_once(run_dir / "run-manifest.json", protocol)
        _write_json_once(run_dir / "domain-semantic-contract-v1.json", DOMAIN_SEMANTIC_CONTRACT)
        _write_json_once(run_dir / "execution-contract-v2.json", execution_contract)
        _write_json_once(run_dir / "run-c1-comparability-audit.json", comparability)
        _write_json_once(run_dir / "local-batch-plan.json", {"seed": seed, "batch_size": 24, "batches": local_batches})
        return run_id

    def execute(self, run_id: int, *, resume: bool = False) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run is None or run.get("run_kind") != "domain_consolidation_v2":
            raise PipelineError("不是 C1 Run", code="c1_run_invalid", retryable=False)
        protocol = run["parameters"]["protocol_manifest"]
        run_dir = self.output_dir / f"run-{run_id:06d}"
        if json.loads((run_dir / "run-manifest.json").read_text()) != protocol:
            raise PipelineError("C1 Manifest 改变", code="c1_manifest_changed", retryable=False)
        if protocol["semantic_contract_hash"] != semantic_contract_hash():
            raise PipelineError("Semantic Contract 漂移", code="c1_semantic_contract_drift", retryable=False)
        source_run_id = int(protocol["source_run_a_id"])
        source_run = self.run_repository.get_run(source_run_id)
        if source_run is None:
            raise PipelineError("Run A 不可用", code="c1_source_missing", retryable=False)
        selected_ids = list(protocol["global_card_order"])
        profile_rows = self.workflow._load_profile_rows(
            profile_run_id=str(source_run["parameters"]["protocol_manifest"]["profile_run_id"]),
            snapshot_hash=str(protocol["snapshot_hash"]), expected_ids=set(selected_ids),
        )
        local_outputs: list[LocalTopLevelDiscoveryOutput] = []
        for index, ids in enumerate(protocol["local_batch_members"], start=1):
            rows = [profile_rows[item] for item in ids]
            prompt = build_top_level_local_prompt(rows, representation="classification_profile_v1")
            output = self.workflow._model_stage(
                run_id=run_id, run_dir=run_dir, stage_name="domain_local_discovery",
                unit_key=f"batch-{index:03d}", role="taxonomy_local", prompt=prompt,
                prompt_version=LOCAL_TOP_LEVEL_PROMPT_VERSION,
                schema=LocalTopLevelDiscoveryOutput, schema_hint=LOCAL_TOP_LEVEL_SCHEMA_HINT,
                max_tokens=4096, input_ids=ids,
                validator=lambda value, allowed=set(ids): validate_local_top_level(value, allowed),
            )
            local_outputs.append(output)
        _write_json(run_dir / "domain-local-candidates.json", [item.model_dump(mode="json") for item in local_outputs])
        table = self.workflow._candidate_normalization_stage(
            run_id=run_id, run_dir=run_dir, local_outputs=local_outputs,
            allowed_ids=set(selected_ids),
        )
        candidates = enrich_candidate_lineage(table, local_outputs)
        candidate_path = run_dir / "run-c1-normalized-candidate-table.json"
        _write_json(candidate_path, {"version": "run-c1-normalized-candidates-v1", "candidate_count": len(candidates), "candidates": candidates})
        candidate_hash = _hash_file(candidate_path)
        node_prompt = build_node_synthesis_prompt(candidates)
        budget = self._node_budget(candidates, node_prompt)
        _write_json(run_dir / "node-synthesis-budget.json", budget)
        tree = self.workflow._model_stage(
            run_id=run_id, run_dir=run_dir, stage_name="domain_node_synthesis",
            unit_key="main", role="taxonomy_global", prompt=node_prompt,
            prompt_version=NODE_SYNTHESIS_PROMPT_VERSION,
            schema=DomainNodeSynthesisOutput, schema_hint=NODE_SCHEMA_HINT,
            max_tokens=budget["max_tokens"], input_ids=[item["candidate_id"] for item in candidates],
            validator=lambda value: validate_node_synthesis(value, allowed_evidence_ids=set(selected_ids)),
        )
        node_call_dir = run_dir / "domain_node_synthesis/main/attempt-01"
        node_audit = json.loads((node_call_dir / "audit.json").read_text())
        if node_audit.get("finish_reason") == "length":
            raise PipelineError("Node Synthesis length 截断", code="c1_node_length", retryable=False)
        tree_hash = _stable_hash(tree.model_dump(mode="json"))
        frozen_tree = {
            "version": "run-c1-frozen-domain-tree-v1",
            "domain_nodes": [item.model_dump(mode="json") for item in tree.domain_nodes],
            "synthesis_notes": tree.synthesis_notes,
            "node_tree_hash": tree_hash,
            "semantic_contract_hash": protocol["semantic_contract_hash"],
            "execution_contract_version": EXECUTION_CONTRACT_VERSION,
            "node_synthesis_response_hash": _hash_file(node_call_dir / "raw-response.txt"),
            "candidate_table_hash": candidate_hash,
        }
        frozen_tree_path = run_dir / "run-c1-frozen-domain-tree.json"
        _write_json(frozen_tree_path, frozen_tree)
        node_ids = {item.node_id for item in tree.domain_nodes}
        routing_batches = deterministic_routing_batches(candidates)
        routing_plan = {
            "batch_size": ROUTING_BATCH_SIZE,
            "candidate_count": len(candidates),
            "batches": [[item["candidate_id"] for item in batch] for batch in routing_batches],
            "input_hashes": [],
        }
        routed: list[tuple[str, CandidateRoutingOutput, str]] = []
        completed_ids: list[str] = []
        for index, batch in enumerate(routing_batches, start=1):
            unit_key = f"batch-{index:03d}"
            expected_ids = [item["candidate_id"] for item in batch]
            prompt = build_routing_prompt(batch, tree, completed_ids=completed_ids)
            routing_plan["input_hashes"].append(_stable_hash({"prompt": prompt, "expected_ids": expected_ids}))
            output = self.workflow._model_stage(
                run_id=run_id, run_dir=run_dir, stage_name="candidate_routing",
                unit_key=unit_key, role="taxonomy_global", prompt=prompt,
                prompt_version=ROUTING_PROMPT_VERSION,
                schema=CandidateRoutingOutput, schema_hint=ROUTING_SCHEMA_HINT,
                max_tokens=8192, input_ids=expected_ids,
                validator=lambda value, expected=expected_ids: validate_routing(value, expected_ids=expected, node_ids=node_ids),
            )
            call_dir = run_dir / f"candidate_routing/{unit_key}/attempt-01"
            audit = json.loads((call_dir / "audit.json").read_text())
            if audit.get("finish_reason") == "length":
                raise PipelineError("Routing length 截断", code="c1_routing_length", retryable=False)
            response_path = call_dir / str(audit["raw_response_path"])
            routed.append((unit_key, output, _hash_file(response_path)))
            completed_ids.extend(expected_ids)
        _write_json(run_dir / "routing-batch-plan.json", routing_plan)
        decisions = assemble_decisions(candidates, routed)
        complete_path = run_dir / "run-c1-candidate-decisions-complete.json"
        _write_json(complete_path, {"candidate_count": len(candidates), "decision_count": len(decisions), "coverage": 1.0, "candidate_decisions": decisions})
        nested = nodes_to_nested_domains(tree)
        contract = adapt_domain_contract(
            source_run_id=run_id, domains=nested, decisions=decisions, candidates=candidates,
            lineage={
                "source_stage_id": f"run-{run_id:06d}:domain_node_synthesis+candidate_routing",
                "source_attempt": "node-attempt-01+routing-attempt-01",
                "raw_response_hash": _stable_hash([value for _, _, value in routed] + [frozen_tree["node_synthesis_response_hash"]]),
                "candidate_table_hash": candidate_hash,
            },
        )
        contract_path = run_dir / "run-c1-domain-contract-v2.json"
        _write_json(contract_path, contract)
        hierarchy = validate_hierarchy_v2(contract)
        _write_json(run_dir / "hierarchy-risk-findings.json", hierarchy)
        unresolved = [item for item in decisions if item["action"] == "unresolved_requires_new_domain"]
        unresolved_candidates = {item["candidate_id"]: item for item in candidates}
        unresolved_payload = {
            "count": len(unresolved),
            "rate": round(len(unresolved) / max(1, len(candidates)), 6),
            "supporting_id_count": len({value for item in unresolved for value in unresolved_candidates[item["candidate_id"]]["supporting_ids"]}),
            "high_confidence_count": sum(item["confidence"] == "high" for item in unresolved),
            "multi_evidence_count": sum(len(unresolved_candidates[item["candidate_id"]]["supporting_ids"]) > 1 for item in unresolved),
            "proposals": unresolved,
        }
        _write_json(run_dir / "run-c1-unresolved-domain-proposals.json", unresolved_payload)
        gate = self._gate(
            protocol=protocol, candidates=candidates, decisions=decisions, tree=tree,
            contract=contract, hierarchy=hierarchy, unresolved=unresolved_payload,
            run_dir=run_dir, node_audit=node_audit,
        )
        _write_json(run_dir / "run-c1-quality-gate.json", gate)
        replication = self._replication_plan(protocol, gate)
        _write_json(run_dir / "run-c2-replication-plan.json", replication)
        artifact_manifest = versioned_tree_hash(run_dir)
        artifact_manifest["important_asset_hashes"] = {
            path.name: _hash_file(path) for path in (
                candidate_path, frozen_tree_path, complete_path, contract_path,
                run_dir / "run-c1-quality-gate.json", run_dir / "run-c2-replication-plan.json",
            )
        }
        _write_json(run_dir / "final-artifact-manifest.json", artifact_manifest)
        status = "completed" if gate["status"] in {"PASS", "PASS_WITH_CHANGES"} else "quality_failed"
        self.run_repository.set_run_status(
            run_id, status, current_stage="run_c1_quality_gate",
            error_code=None if status == "completed" else "run_c1_quality_failed",
            error_message=None if status == "completed" else "Run C1 Gate 未通过",
        )
        return self.status(run_id)

    def status(self, run_id: int) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run is None:
            raise LookupError(run_id)
        return {"run": run, "stages": self.run_repository.list_stages(run_id)}

    def _node_budget(self, candidates: list[dict[str, Any]], prompt: str) -> dict[str, Any]:
        estimated_nodes = [max(5, len(candidates) // 8), min(24, max(10, len(candidates) // 3))]
        max_tokens = 16384
        return {
            "normalized_candidate_count": len(candidates),
            "candidate_input_chars": len(json.dumps(candidates, ensure_ascii=False)),
            "prompt_chars": len(prompt), "estimated_node_count_range": estimated_nodes,
            "schema_overhead_chars": len(NODE_SCHEMA_HINT),
            "historical_run_b_completion_tokens": 18432,
            "max_tokens": max_tokens,
            "safety_margin_rationale": "Node-only output removes 40 decisions; 16,384 retains reasoning and >2x estimated node JSON.",
        }

    def _gate(
        self, *, protocol: dict[str, Any], candidates: list[dict[str, Any]],
        decisions: list[dict[str, Any]], tree: DomainNodeSynthesisOutput,
        contract: dict[str, Any], hierarchy: dict[str, Any], unresolved: dict[str, Any],
        run_dir: Path, node_audit: dict[str, Any],
    ) -> dict[str, Any]:
        blocking: list[dict[str, Any]] = list(hierarchy["blocking"])
        warnings: list[dict[str, Any]] = list(hierarchy["warnings"])
        expected = [item["candidate_id"] for item in candidates]
        actual = [item["candidate_id"] for item in decisions]
        if expected != actual or len(actual) != len(set(actual)):
            blocking.append({"code": "candidate_coverage_failed", "details": []})
        if protocol["semantic_contract_hash"] != semantic_contract_hash():
            blocking.append({"code": "semantic_contract_mismatch", "details": []})
        if contract.get("version") != DOMAIN_EVIDENCE_CONTRACT_VERSION or contract.get("adapter_version") != DOMAIN_EVIDENCE_ADAPTER_VERSION:
            blocking.append({"code": "evidence_contract_mismatch", "details": []})
        if node_audit.get("finish_reason") == "length":
            blocking.append({"code": "node_synthesis_length", "details": []})
        if unresolved["count"] > 3 or unresolved["rate"] > 0.10:
            blocking.append({"code": "unresolved_boundary_exceeded", "details": [unresolved["count"], unresolved["rate"]]})
        if unresolved["multi_evidence_count"] > 1:
            blocking.append({"code": "systematic_unresolved_gap", "details": [unresolved["multi_evidence_count"]]})
        repair_count = 0
        semantic_changes = 0
        for audit_path in run_dir.glob("candidate_routing/*/attempt-01/audit.json"):
            audit = json.loads(audit_path.read_text())
            repair_count += int(audit.get("repair") is not None)
            diff_path = audit_path.parent / "repair-semantic-diff.json"
            if diff_path.is_file():
                semantic_changes += int(json.loads(diff_path.read_text()).get("semantic_change_count") or 0)
        if node_audit.get("repair") is not None:
            warnings.append({"code": "node_synthesis_repair_used", "details": [1]})
        if repair_count:
            warnings.append({"code": "routing_repair_used", "details": [repair_count]})
        if semantic_changes:
            warnings.append({"code": "repair_semantic_changes", "details": [semantic_changes]})
        if unresolved["count"]:
            warnings.append({"code": "unresolved_candidates", "details": [unresolved["count"]]})
        status = "FAIL" if blocking else ("PASS_WITH_CHANGES" if warnings else "PASS")
        return {
            "version": RUN_C1_GATE_VERSION, "status": status,
            "blocking": blocking, "warnings": warnings,
            "metrics": {
                "candidate_count": len(candidates), "decision_count": len(decisions),
                "coverage": len(decisions) / max(1, len(candidates)),
                "node_count": len(tree.domain_nodes),
                "top_level_count": sum(item.parent_id is None for item in tree.domain_nodes),
                "routing_batch_count": len(deterministic_routing_batches(candidates)),
                "routing_repair_count": repair_count,
                "repair_semantic_change_count": semantic_changes,
                **{f"unresolved_{key}": value for key, value in unresolved.items() if key != "proposals"},
            },
        }

    def _replication_plan(self, protocol: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
        locked = {
            key: protocol[key] for key in (
                "semantic_contract_hash", "node_synthesis_prompt_version", "node_schema_hash",
                "routing_prompt_version", "routing_schema_hash", "evidence_contract_version",
                "providers", "local_batch_size", "routing_batch_size", "gate_version",
            )
        }
        locked.update({
            "execution_contract_version": EXECUTION_CONTRACT_VERSION,
            "local_discovery_prompt_hash": _stable_hash({"version": LOCAL_TOP_LEVEL_PROMPT_VERSION, "schema": LOCAL_TOP_LEVEL_SCHEMA_VERSION}),
            "normalize_version": CANDIDATE_NORMALIZATION_VERSION,
            "model": protocol["providers"]["taxonomy_global"]["model"],
            "thinking": protocol["providers"]["taxonomy_global"],
            "hash_algorithm_version": HASH_ALGORITHM_VERSION,
        })
        eligible = gate["status"] in {"PASS", "PASS_WITH_CHANGES"} and not gate["blocking"] and gate["metrics"]["coverage"] == 1
        return {
            "version": "run-c2-replication-plan-v1", "future_run_label": "C2",
            "future_seed": 404, "locked_contract": locked,
            "allowed_differences": ["seed", "card_order", "local_batch_members", "candidate_order", "routing_batch_members", "run_id", "timestamps"],
            "replication_eligible": eligible,
            "invalidation_rule": "Any semantic prompt/schema/contract change requires protocol v2.1 and a new replication decision.",
        }
