from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.domain import PipelineError
from shiliu.taxonomy.candidates import (
    CANDIDATE_NORMALIZATION_VERSION,
    LOCAL_TOP_LEVEL_PROMPT_VERSION,
    LOCAL_TOP_LEVEL_SCHEMA_HINT,
    LOCAL_TOP_LEVEL_SCHEMA_VERSION,
    TOP_LEVEL_CONSOLIDATION_PROMPT_VERSION,
    TOP_LEVEL_CONSOLIDATION_SCHEMA_HINT,
    TOP_LEVEL_DOMAIN_SCHEMA_VERSION,
    CompactCandidateTable,
    LocalTopLevelDiscoveryOutput,
    TopLevelDomainDraft,
    build_top_level_consolidation_prompt,
    build_top_level_local_prompt,
    normalize_candidates,
    normalized_name,
    validate_local_top_level,
    validate_top_level_draft,
)
from shiliu.taxonomy.controlled_facets import (
    _git_state,
    _hash_file,
    _provider_manifest,
    _stable_hash,
    _utc_now,
    _write_json,
    _write_json_once,
)
from shiliu.taxonomy.repository import TaxonomyRepository
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from shiliu.taxonomy.workflow import (
    DOMAIN_CONSOLIDATION_TOKEN_POLICY,
    TOP_LEVEL_QUALITY_GATE_VERSION,
    TaxonomyWorkflow,
    _domain_consolidation_max_tokens,
)


DOMAIN_STABILITY_ENGINE_VERSION = "domain-stability-workflow-v1"
DOMAIN_STABILITY_PROTOCOL_VERSION = "checkpoint312-domain-run-v1"
DOMAIN_RUN_GATE_VERSION = "checkpoint312-domain-run-gate-v1"
COMPARABILITY_AUDIT_VERSION = "domain-run-comparability-v1"
CROSS_RUN_ALIGNMENT_VERSION = "cross-run-domain-alignment-v1"
CROSS_RUN_ALIGNMENT_PROMPT_VERSION = "cross-run-domain-alignment-v1"
HIERARCHY_VALIDATOR_VERSION = "risk-unit-hierarchy-validator-v1"
HIERARCHY_VALIDATOR_PROMPT_VERSION = "risk-unit-hierarchy-validator-v1"
DRAFT_A_VERSION = "domain-draft-a-v1"
DRAFT_A_GATE_VERSION = "domain-draft-a-gate-v1"


class DomainRunGate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    passed: bool
    blocking_issues: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    metrics: dict[str, Any]


class AlignmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    pair_id: str = Field(pattern=r"^pair_[0-9]{3}$")
    run_node_ids: list[str] = Field(min_length=2, max_length=2)
    relation: Literal[
        "equivalent",
        "parent_child_variant",
        "granularity_variant",
        "overlapping_but_distinct",
        "unrelated",
        "uncertain",
    ]
    reason: str = Field(min_length=1, max_length=300)
    support_overlap: float = Field(ge=0, le=1)
    definition_comparison: str = Field(min_length=1, max_length=240)
    parent_comparison: str = Field(min_length=1, max_length=180)
    confidence: Literal["high", "medium", "low"]


class AlignmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[CROSS_RUN_ALIGNMENT_VERSION] = CROSS_RUN_ALIGNMENT_VERSION
    decisions: list[AlignmentDecision]


class ValidatorFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    unit_id: str = Field(pattern=r"^risk_[0-9]{3}$")
    affected_node_ids: list[str] = Field(min_length=1)
    operation: Literal[
        "keep",
        "rename",
        "merge",
        "move",
        "promote_to_top_level",
        "demote_to_subdomain",
        "downgrade_to_topic",
        "downgrade_to_entity",
        "mark_uncertain",
        "exclude_from_draft",
    ]
    reason: str = Field(min_length=1, max_length=320)
    evidence: list[str] = Field(min_length=1, max_length=5)
    confidence: Literal["high", "medium", "low"]
    blocking: bool


class HierarchyValidationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[HIERARCHY_VALIDATOR_VERSION] = HIERARCHY_VALIDATOR_VERSION
    findings: list[ValidatorFinding]


class DraftNode(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    draft_node_id: str = Field(pattern=r"^draft_[0-9]{3}$")
    canonical_name: str
    definition: str
    includes: list[str]
    excludes: list[str]
    parent_id: str | None
    stability: Literal["stable", "probable", "weak", "uncertain"]
    source_run_nodes: list[str]
    source_runs: list[str]
    supporting_ids: list[str]
    representative_ids: list[str]
    validator_findings: list[dict[str, Any]]
    draft_decision: str
    decision_reason: str


class DomainDraftA(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[DRAFT_A_VERSION] = DRAFT_A_VERSION
    nodes: list[DraftNode]

    @model_validator(mode="after")
    def validate_tree(self):
        ids = {item.draft_node_id for item in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("Draft node IDs must be unique")
        if any(item.parent_id is not None and item.parent_id not in ids for item in self.nodes):
            raise ValueError("Draft parent is missing")
        parent_by_id = {item.draft_node_id: item.parent_id for item in self.nodes}
        for item in self.nodes:
            parent = item.parent_id
            if parent is not None and parent_by_id.get(parent) is not None:
                raise ValueError("Draft depth exceeds two levels")
        return self


ALIGNMENT_SCHEMA_HINT = (
    '{"version":"cross-run-domain-alignment-v1","decisions":['
    '{"pair_id":"pair_001","run_node_ids":["A:d_01","B:d_02"],'
    '"relation":"equivalent|parent_child_variant|granularity_variant|'
    'overlapping_but_distinct|unrelated|uncertain","reason":"",'
    '"support_overlap":0.0,"definition_comparison":"",'
    '"parent_comparison":"","confidence":"high|medium|low"}]}'
)

VALIDATOR_SCHEMA_HINT = (
    '{"version":"risk-unit-hierarchy-validator-v1","findings":['
    '{"unit_id":"risk_001","affected_node_ids":["group_001"],'
    '"operation":"keep|rename|merge|move|promote_to_top_level|'
    'demote_to_subdomain|downgrade_to_topic|downgrade_to_entity|'
    'mark_uncertain|exclude_from_draft","reason":"","evidence":[""],'
    '"confidence":"high|medium|low","blocking":false}]}'
)


class DomainStabilityService:
    def __init__(
        self,
        *,
        repository: TaxonomyRepository,
        run_repository: TaxonomyRunRepository,
        workflow: TaxonomyWorkflow,
        output_dir: Path,
        profile_output_dir: Path,
    ) -> None:
        self.repository = repository
        self.run_repository = run_repository
        self.workflow = workflow
        self.output_dir = output_dir
        self.profile_output_dir = profile_output_dir

    def create_domain_run(
        self,
        *,
        source_run_id: int = 12,
        run_label: Literal["B", "C"],
        seed: int,
    ) -> int:
        if run_label not in {"B", "C"}:
            raise ValueError("run_label must be B or C")
        audit = self.audit_comparability(source_run_id=source_run_id)
        if not audit["comparable"]:
            raise PipelineError(
                "Run A 与当前 Domain 协议不可比较",
                code="domain_protocol_not_comparable",
                retryable=False,
            )
        source = self.run_repository.get_run(source_run_id)
        assert source is not None
        source_protocol = source["parameters"]["protocol_manifest"]
        snapshot = self.repository.get_snapshot(int(source["corpus_snapshot_id"]))
        if snapshot is None or snapshot["snapshot_hash"] != source_protocol["snapshot_hash"]:
            raise PipelineError(
                "冻结 Snapshot 或 Run A 不可用",
                code="domain_source_snapshot_changed",
                retryable=False,
            )
        git_commit, git_clean = _git_state()
        if not git_clean:
            raise PipelineError(
                "创建 Domain Run 前工作区必须干净",
                code="domain_run_git_dirty",
                retryable=False,
            )
        provider_roles = ("taxonomy_local", "taxonomy_global", "taxonomy_repair")
        providers = {
            role: _provider_manifest(self.workflow.provider_factory(role))
            for role in provider_roles
        }
        expected_providers = {
            role: source_protocol["providers"][role] for role in provider_roles
        }
        if providers != expected_providers:
            raise PipelineError(
                "Domain Provider、模型或 Thinking 配置与 Run A 不同",
                code="domain_provider_contract_changed",
                retryable=False,
            )
        selected_ids = list(source["parameters"]["selected_ids"])
        order = list(selected_ids)
        random.Random(seed).shuffle(order)
        batches = [order[index : index + 24] for index in range(0, len(order), 24)]
        protocol = {
            "protocol_version": DOMAIN_STABILITY_PROTOCOL_VERSION,
            "run_label": run_label,
            "source_run_a_id": source_run_id,
            "source_run_a_manifest_hash": _hash_file(
                self.output_dir / f"run-{source_run_id:06d}" / "run-manifest.json"
            ),
            "snapshot_id": snapshot["id"],
            "snapshot_hash": snapshot["snapshot_hash"],
            "classification_profile_version": source_protocol["profile_version"],
            "classification_profile_hash": source_protocol["profile_hash"],
            "profile_run_id": source_protocol["profile_run_id"],
            "domain_local_prompt_version": source_protocol["domain_prompt_version"],
            "domain_local_schema_version": source_protocol["domain_schema_version"],
            "domain_normalizer_version": source_protocol["domain_normalization_version"],
            "domain_consolidation_prompt_version": source_protocol[
                "domain_consolidation_prompt_version"
            ],
            "domain_consolidation_schema_version": source_protocol[
                "domain_draft_schema_version"
            ],
            "quality_gate_version": DOMAIN_RUN_GATE_VERSION,
            "semantic_contract_hash": audit["current_semantic_contract_hash"],
            "comparability_audit_hash": _stable_hash(audit),
            "providers": providers,
            "seed": seed,
            "global_card_order": order,
            "batch_members": batches,
            "batch_size": 24,
            "per_batch_candidate_limit": 8,
            "domain_consolidation_token_policy": DOMAIN_CONSOLIDATION_TOKEN_POLICY,
            "git_commit": git_commit,
            "git_worktree_clean": True,
            "created_at": _utc_now(),
        }
        run_id = self.run_repository.create_run(
            snapshot_id=int(snapshot["id"]),
            run_kind="domain_stability_discovery",
            engine="domain_stability",
            engine_version=DOMAIN_STABILITY_ENGINE_VERSION,
            parameters={"snapshot_hash": snapshot["snapshot_hash"], "protocol_manifest": protocol},
        )
        run_dir = self.output_dir / f"run-{run_id:06d}"
        _write_json_once(run_dir / "run-manifest.json", protocol)
        _write_json_once(run_dir / "comparability-audit.json", audit)
        _write_json_once(
            run_dir / "batch-plan.json",
            {"seed": seed, "batch_size": 24, "batches": batches},
        )
        return run_id

    def execute(self, run_id: int, *, resume: bool = False) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run is None or run.get("run_kind") != "domain_stability_discovery":
            raise PipelineError(
                "不是 Domain Stability Run",
                code="domain_stability_run_invalid",
                retryable=False,
            )
        protocol = run["parameters"]["protocol_manifest"]
        run_dir = self.output_dir / f"run-{run_id:06d}"
        if json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8")) != protocol:
            raise PipelineError(
                "Domain Run Manifest 已改变",
                code="domain_run_manifest_changed",
                retryable=False,
            )
        audit = self.audit_comparability(source_run_id=int(protocol["source_run_a_id"]))
        if (
            not audit["comparable"]
            or audit["current_semantic_contract_hash"] != protocol["semantic_contract_hash"]
        ):
            raise PipelineError(
                "Domain 协议在创建 Run 后发生漂移",
                code="domain_protocol_drift",
                retryable=False,
            )
        snapshot = self.repository.get_snapshot(int(protocol["snapshot_id"]))
        if snapshot is None or snapshot["snapshot_hash"] != protocol["snapshot_hash"]:
            raise PipelineError(
                "Snapshot 在 Domain Run 执行前改变",
                code="domain_source_snapshot_changed",
                retryable=False,
            )
        selected_ids = list(protocol["global_card_order"])
        if len(selected_ids) != 128 or len(set(selected_ids)) != 128:
            raise PipelineError(
                "Domain Run 必须精确使用 128 条 Eligible Card",
                code="domain_run_card_set_invalid",
                retryable=False,
            )
        compact = self._compact_from_source(int(protocol["source_run_a_id"]))
        evidence = {str(row[0]): str(row[1]) for row in compact["rows"]}
        if any(evidence.get(item) == "D" for item in selected_ids):
            raise PipelineError(
                "D 级卡片不得进入 Domain Discovery",
                code="domain_run_contains_d_grade",
                retryable=False,
            )
        profile_rows = self.workflow._load_profile_rows(
            profile_run_id=str(protocol["profile_run_id"]),
            snapshot_hash=str(protocol["snapshot_hash"]),
            expected_ids=set(selected_ids),
        )
        batches = [
            [profile_rows[item] for item in batch]
            for batch in protocol["batch_members"]
        ]
        local_outputs: list[LocalTopLevelDiscoveryOutput] = []
        for index, batch in enumerate(batches, start=1):
            prompt = build_top_level_local_prompt(
                batch, representation="classification_profile_v1"
            )
            result = self.workflow._model_stage(
                run_id=run_id,
                run_dir=run_dir,
                stage_name="domain_local_discovery",
                unit_key=f"batch-{index:03d}",
                role="taxonomy_local",
                prompt=prompt,
                prompt_version=LOCAL_TOP_LEVEL_PROMPT_VERSION,
                schema=LocalTopLevelDiscoveryOutput,
                schema_hint=LOCAL_TOP_LEVEL_SCHEMA_HINT,
                max_tokens=4096,
                input_ids=[str(row[0]) for row in batch],
                validator=lambda value, allowed={str(row[0]) for row in batch}: (
                    validate_local_top_level(value, allowed)
                ),
            )
            local_outputs.append(result)
        _write_json(
            run_dir / "domain-local-candidates.json",
            [item.model_dump(mode="json") for item in local_outputs],
        )
        table = self.workflow._candidate_normalization_stage(
            run_id=run_id,
            run_dir=run_dir,
            local_outputs=local_outputs,
            allowed_ids=set(selected_ids),
        )
        prompt = build_top_level_consolidation_prompt(table)
        draft = self.workflow._model_stage(
            run_id=run_id,
            run_dir=run_dir,
            stage_name="domain_consolidation",
            unit_key="main",
            role="taxonomy_global",
            prompt=prompt,
            prompt_version=TOP_LEVEL_CONSOLIDATION_PROMPT_VERSION,
            schema=TopLevelDomainDraft,
            schema_hint=TOP_LEVEL_CONSOLIDATION_SCHEMA_HINT,
            max_tokens=_domain_consolidation_max_tokens(
                DOMAIN_CONSOLIDATION_TOKEN_POLICY,
                candidate_count=len(table.domains),
            ),
            input_ids=sorted(
                {item for candidate in table.domains for item in candidate.supporting_ids}
            ),
            validator=lambda value: validate_top_level_draft(
                value,
                allowed_ids=set(selected_ids),
                candidate_ids={item.candidate_id for item in table.domains},
            ),
        )
        _write_json(run_dir / "taxonomy-draft.json", draft.model_dump(mode="json"))
        gate = self._domain_run_gate(
            run_id=run_id,
            draft=draft,
            local_outputs=local_outputs,
            table=table,
            allowed_ids=set(selected_ids),
            profile_rows=profile_rows,
        )
        self._deterministic_stage(
            run_id=run_id,
            stage_name="domain_quality_gate",
            input_value={
                "draft": draft.model_dump(mode="json"),
                "local": [item.model_dump(mode="json") for item in local_outputs],
            },
            output_path=run_dir / "domain-quality-gate" / "quality-result.json",
            output_value=gate.model_dump(mode="json"),
            version=DOMAIN_RUN_GATE_VERSION,
        )
        status = "completed" if gate.passed else "quality_failed"
        self.run_repository.set_run_status(
            run_id,
            status,
            current_stage="domain_quality_gate",
            error_code=None if gate.passed else "domain_quality_gate_failed",
            error_message=None if gate.passed else "Domain Run Gate 未通过",
        )
        return self.status(run_id)

    def status(self, run_id: int) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run is None:
            raise LookupError(run_id)
        return {"run": run, "stages": self.run_repository.list_stages(run_id)}

    def audit_comparability(self, *, source_run_id: int = 12) -> dict[str, Any]:
        source = self.run_repository.get_run(source_run_id)
        if (
            source is None
            or source.get("run_kind") != "full_discovery_run_a"
            or source.get("status") != "completed"
        ):
            raise PipelineError(
                "Run A 不可用于可比性审计",
                code="domain_run_a_invalid",
                retryable=False,
            )
        protocol = source["parameters"].get("protocol_manifest") or {}
        run_dir = self.output_dir / f"run-{source_run_id:06d}"
        source_manifest = run_dir / "run-manifest.json"
        candidate_path = run_dir / "candidate-normalization" / "compact-candidates.json"
        profile_run_id = str(protocol.get("profile_run_id") or "")
        profile_manifest_path = self.profile_output_dir / profile_run_id / "manifest.json"
        required = [source_manifest, candidate_path, profile_manifest_path]
        if any(not path.is_file() for path in required):
            raise PipelineError(
                "Run A 可比性审计缺少冻结产物",
                code="domain_comparability_artifact_missing",
                retryable=False,
            )
        profile_manifest = json.loads(profile_manifest_path.read_text(encoding="utf-8"))
        source_table = CompactCandidateTable.model_validate_json(
            candidate_path.read_text(encoding="utf-8")
        )
        consolidation_prompt = build_top_level_consolidation_prompt(source_table)
        consolidation_prompt_path = run_dir / "consolidation" / "main" / "attempt-01" / "prompt.txt"
        local_lineage = json.loads(
            (run_dir / "reused-discovery-lineage.json").read_text(encoding="utf-8")
        )
        current_local_hashes: dict[str, str] = {}
        source_local_hashes: dict[str, str] = {}
        profile_rows = self.workflow._load_profile_rows(
            profile_run_id=profile_run_id,
            snapshot_hash=str(protocol["snapshot_hash"]),
            expected_ids=set(source["parameters"]["selected_ids"]),
        )
        for item in local_lineage["stages"]:
            if item["stage_name"] != "local_discovery":
                continue
            unit = str(item["unit_key"])
            rows = [profile_rows[value] for value in item["batch_members"]]
            prompt = build_top_level_local_prompt(
                rows, representation="classification_profile_v1"
            )
            current_local_hashes[unit] = _hash_text(prompt)
            source_local_hashes[unit] = str(item["source_prompt_file_hash"])
        schema_contract = {
            "local": LocalTopLevelDiscoveryOutput.model_json_schema(),
            "draft": TopLevelDomainDraft.model_json_schema(),
        }
        semantic_contract = {
            "snapshot_hash": protocol.get("snapshot_hash"),
            "profile_version": protocol.get("profile_version"),
            "profile_hash": protocol.get("profile_hash"),
            "domain_local_prompt_version": LOCAL_TOP_LEVEL_PROMPT_VERSION,
            "domain_local_schema_version": LOCAL_TOP_LEVEL_SCHEMA_VERSION,
            "domain_normalizer_version": CANDIDATE_NORMALIZATION_VERSION,
            "domain_consolidation_prompt_version": TOP_LEVEL_CONSOLIDATION_PROMPT_VERSION,
            "domain_consolidation_schema_version": TOP_LEVEL_DOMAIN_SCHEMA_VERSION,
            "quality_gate_version": protocol.get("quality_gate_version"),
            "batch_size": protocol.get("batch_size"),
            "candidate_limit": 8,
            "token_policy": DOMAIN_CONSOLIDATION_TOKEN_POLICY,
            "providers": {
                role: protocol["providers"][role]
                for role in ("taxonomy_local", "taxonomy_global", "taxonomy_repair")
            },
            "schema_hash": _stable_hash(schema_contract),
        }
        checks = {
            "snapshot_same": protocol.get("snapshot_hash")
            == "1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2",
            "profile_same": profile_manifest.get("profiles_hash") == protocol.get("profile_hash"),
            "versions_same": all(
                (
                    protocol.get("domain_prompt_version") == LOCAL_TOP_LEVEL_PROMPT_VERSION,
                    protocol.get("domain_schema_version") == LOCAL_TOP_LEVEL_SCHEMA_VERSION,
                    protocol.get("domain_normalization_version") == CANDIDATE_NORMALIZATION_VERSION,
                    protocol.get("domain_consolidation_prompt_version")
                    == TOP_LEVEL_CONSOLIDATION_PROMPT_VERSION,
                    protocol.get("domain_draft_schema_version")
                    == TOP_LEVEL_DOMAIN_SCHEMA_VERSION,
                )
            ),
            "all_local_prompts_exact": current_local_hashes == source_local_hashes,
            "consolidation_prompt_exact": consolidation_prompt_path.is_file()
            and _hash_text(consolidation_prompt)
            == _hash_file(consolidation_prompt_path),
            "batch_size_same": protocol.get("batch_size") == 24,
            "provider_contract_present": all(
                role in protocol.get("providers", {})
                for role in ("taxonomy_local", "taxonomy_global", "taxonomy_repair")
            ),
        }
        allowed_engineering_differences = [
            "严格 Schema 替代超限静默截断",
            "原始响应先落盘",
            "独立 JSON Repair 与 Repair Semantic Diff",
            "正确失败状态、Resume、预算预检和审计字段",
        ]
        return {
            "version": COMPARABILITY_AUDIT_VERSION,
            "source_run_id": source_run_id,
            "source_git_commit": protocol.get("git_commit"),
            "source_manifest_hash": _hash_file(source_manifest),
            "classification_profile_version": protocol.get("profile_version"),
            "classification_profile_hash": protocol.get("profile_hash"),
            "current_local_prompt_hashes": current_local_hashes,
            "source_local_prompt_hashes": source_local_hashes,
            "current_consolidation_prompt_hash": _hash_text(consolidation_prompt),
            "source_consolidation_prompt_hash": (
                _hash_file(consolidation_prompt_path)
                if consolidation_prompt_path.is_file()
                else None
            ),
            "current_schema_hash": _stable_hash(schema_contract),
            "checks": checks,
            "allowed_engineering_differences": allowed_engineering_differences,
            "semantic_differences": [],
            "current_semantic_contract": semantic_contract,
            "current_semantic_contract_hash": _stable_hash(semantic_contract),
            "comparable": all(checks.values()),
            "audited_at": _utc_now(),
        }

    def create_merge_run(self, *, run_a_id: int = 12, run_b_id: int, run_c_id: int) -> int:
        runs = {"A": run_a_id, "B": run_b_id, "C": run_c_id}
        for label, run_id in runs.items():
            run = self.run_repository.get_run(run_id)
            if run is None or run.get("status") != "completed":
                raise PipelineError(
                    f"Domain Run {label} 未完成",
                    code="domain_cross_run_source_incomplete",
                    retryable=False,
                )
        source_a = self.run_repository.get_run(run_a_id)
        assert source_a is not None
        snapshot_id = int(source_a["corpus_snapshot_id"])
        manifests = {
            label: _hash_file(self.output_dir / f"run-{run_id:06d}" / "run-manifest.json")
            for label, run_id in runs.items()
        }
        run_id = self.run_repository.create_run(
            snapshot_id=snapshot_id,
            run_kind="domain_cross_run_merge",
            engine="domain_stability",
            engine_version=DOMAIN_STABILITY_ENGINE_VERSION,
            parameters={
                "snapshot_hash": source_a["parameters"]["snapshot_hash"],
                "protocol_manifest": {
                    "protocol_version": "checkpoint312-cross-run-merge-v1",
                    "source_runs": runs,
                    "source_manifest_hashes": manifests,
                    "git_commit": _git_state()[0],
                    "created_at": _utc_now(),
                },
            },
        )
        run_dir = self.output_dir / f"run-{run_id:06d}"
        _write_json_once(
            run_dir / "run-manifest.json",
            self.run_repository.get_run(run_id)["parameters"]["protocol_manifest"],  # type: ignore[index]
        )
        return run_id

    def execute_merge(self, run_id: int, *, resume: bool = False) -> dict[str, Any]:
        run = self.run_repository.get_run(run_id)
        if run is None or run.get("run_kind") != "domain_cross_run_merge":
            raise PipelineError("不是 Cross-run Merge", code="cross_run_invalid", retryable=False)
        protocol = run["parameters"]["protocol_manifest"]
        run_dir = self.output_dir / f"run-{run_id:06d}"
        nodes = self._load_source_nodes(protocol)
        pairs = build_alignment_candidates(nodes)
        _write_json(run_dir / "alignment-candidates.json", {"pairs": pairs})
        prompt = build_alignment_prompt(pairs)
        output = self.workflow._model_stage(
            run_id=run_id,
            run_dir=run_dir,
            stage_name="cross_run_alignment",
            unit_key="main",
            role="taxonomy_global",
            prompt=prompt,
            prompt_version=CROSS_RUN_ALIGNMENT_PROMPT_VERSION,
            schema=AlignmentOutput,
            schema_hint=ALIGNMENT_SCHEMA_HINT,
            max_tokens=16384,
            input_ids=[item["pair_id"] for item in pairs],
            validator=lambda value: validate_alignment(value, pairs),
        )
        groups, metrics = merge_aligned_nodes(nodes, output)
        _write_json(run_dir / "cross-run-groups.json", {"groups": groups, "metrics": metrics})
        risk_units, deterministic_findings = build_risk_units(groups)
        _write_json(
            run_dir / "hierarchy-validator" / "risk-units.json",
            {"risk_units": risk_units, "deterministic_findings": deterministic_findings},
        )
        if risk_units:
            validation = self.workflow._model_stage(
                run_id=run_id,
                run_dir=run_dir,
                stage_name="hierarchy_validation",
                unit_key="risk-units",
                role="taxonomy_validator",
                prompt=build_validator_prompt(risk_units),
                prompt_version=HIERARCHY_VALIDATOR_PROMPT_VERSION,
                schema=HierarchyValidationOutput,
                schema_hint=VALIDATOR_SCHEMA_HINT,
                max_tokens=12288,
                input_ids=[item["unit_id"] for item in risk_units],
                validator=lambda value: validate_hierarchy_output(value, risk_units),
            )
        else:
            validation = HierarchyValidationOutput(findings=[])
        _write_json(
            run_dir / "hierarchy-validator" / "validation-result.json",
            validation.model_dump(mode="json"),
        )
        draft, uncertain = build_draft_a(groups, validation)
        _write_json(run_dir / "domain-draft-a.json", draft.model_dump(mode="json"))
        _write_json(run_dir / "draft_a_uncertain_nodes.json", {"nodes": uncertain})
        gate = build_draft_a_gate(
            draft=draft,
            groups=groups,
            alignment=output,
            validation=validation,
            deterministic_findings=deterministic_findings,
        )
        self._deterministic_stage(
            run_id=run_id,
            stage_name="draft_a_gate",
            input_value={
                "groups": groups,
                "validation": validation.model_dump(mode="json"),
                "draft": draft.model_dump(mode="json"),
            },
            output_path=run_dir / "draft-a-gate" / "quality-result.json",
            output_value=gate.model_dump(mode="json"),
            version=DRAFT_A_GATE_VERSION,
        )
        status = "completed" if gate.passed else "quality_failed"
        self.run_repository.set_run_status(
            run_id,
            status,
            current_stage="draft_a_gate",
            error_code=None if gate.passed else "draft_a_gate_failed",
            error_message=None if gate.passed else "Draft A Gate 未通过",
        )
        return self.status(run_id)

    def _load_source_nodes(self, protocol: dict[str, Any]) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        for label, run_id in protocol["source_runs"].items():
            run_dir = self.output_dir / f"run-{int(run_id):06d}"
            if _hash_file(run_dir / "run-manifest.json") != protocol["source_manifest_hashes"][label]:
                raise PipelineError(
                    "Cross-run 来源 Manifest 改变",
                    code="cross_run_source_changed",
                    retryable=False,
                )
            draft = TopLevelDomainDraft.model_validate_json(
                (run_dir / "taxonomy-draft.json").read_text(encoding="utf-8")
            )
            for parent in draft.domains:
                nodes.append(_source_node(label, parent, parent_id=None))
                nodes.extend(
                    _source_node(label, child, parent_id=f"{label}:{parent.id}")
                    for child in parent.children
                )
        return nodes

    def _domain_run_gate(
        self,
        *,
        run_id: int,
        draft: TopLevelDomainDraft,
        local_outputs: list[LocalTopLevelDiscoveryOutput],
        table: CompactCandidateTable,
        allowed_ids: set[str],
        profile_rows: dict[str, list[Any]],
    ) -> DomainRunGate:
        blocking: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        if not draft.domains:
            blocking.append({"code": "no_top_level_domain", "details": []})
        all_nodes = [*draft.domains, *(child for parent in draft.domains for child in parent.children)]
        invalid_support = sorted(
            {value for node in all_nodes for value in node.supporting_ids if value not in allowed_ids}
        )
        if invalid_support:
            blocking.append({"code": "invalid_supporting_id", "details": invalid_support})
        entity_names = {
            normalized_name(str(entity))
            for row in profile_rows.values()
            for entity in (row[6] if len(row) > 6 else [])
        }
        leaks = [node.id for node in all_nodes if normalized_name(node.name) in entity_names]
        if leaks:
            blocking.append({"code": "entity_leakage", "details": leaks})
        form_terms = {"教程", "访谈", "演示", "解说", "评论", "复盘", "新闻"}
        form_leaks = [node.id for node in all_nodes if node.name in form_terms]
        if form_leaks:
            blocking.append({"code": "form_leakage", "details": form_leaks})
        context_terms = {"求职", "学习", "收藏", "工作流使用场景"}
        context_leaks = [node.id for node in all_nodes if node.name in context_terms]
        if context_leaks:
            blocking.append({"code": "context_leakage", "details": context_leaks})
        parent_errors = [
            child.id
            for parent in draft.domains
            for child in parent.children
            if child.parent_id != parent.id or not set(child.supporting_ids) <= set(parent.supporting_ids)
        ]
        if parent_errors:
            blocking.append({"code": "parent_child_error", "details": parent_errors})
        decision_ids = [item.candidate_id for item in draft.candidate_decisions]
        candidate_ids = [item.candidate_id for item in table.domains]
        if len(decision_ids) != len(set(decision_ids)) or set(decision_ids) != set(candidate_ids):
            blocking.append({"code": "candidate_decision_incomplete", "details": []})
        local_at_limit = sum(len(item.domains) == 8 for item in local_outputs)
        if local_at_limit:
            warnings.append({"code": "local_candidate_limit_reached", "details": [local_at_limit]})
        low_support = [node.id for node in all_nodes if len(node.supporting_ids) <= 2]
        if low_support:
            warnings.append({"code": "low_support_nodes", "details": low_support})
        repair = _repair_metrics(self.run_repository.list_stages(run_id))
        if repair["repair_call_count"]:
            warnings.append({"code": "repair_used", "details": [repair["repair_call_count"]]})
        if repair["repair_semantic_change_count"]:
            warnings.append(
                {"code": "semantic_repair_used", "details": [repair["repair_semantic_change_count"]]}
            )
        return DomainRunGate(
            passed=not blocking,
            blocking_issues=blocking,
            warnings=warnings,
            metrics={
                "top_level_count": len(draft.domains),
                "subdomain_count": sum(len(item.children) for item in draft.domains),
                "normalized_candidate_count": len(table.domains),
                "local_candidate_count": sum(len(item.domains) for item in local_outputs),
                **repair,
            },
        )

    def _compact_from_source(self, source_run_id: int) -> dict[str, Any]:
        return json.loads(
            (self.output_dir / f"run-{source_run_id:06d}" / "compact-corpus.json").read_text(
                encoding="utf-8"
            )
        )

    def _deterministic_stage(
        self,
        *,
        run_id: int,
        stage_name: str,
        input_value: Any,
        output_path: Path,
        output_value: Any,
        version: str,
    ) -> None:
        input_hash = _stable_hash(input_value)
        stage = self.run_repository.ensure_stage(run_id, stage_name, "main", input_hash=input_hash)
        if stage["status"] == "completed":
            if not output_path.is_file() or _stable_hash(
                json.loads(output_path.read_text(encoding="utf-8"))
            ) != stage["output_hash"]:
                raise PipelineError(
                    "确定性 Stage 产物改变",
                    code="domain_deterministic_stage_changed",
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
            output_hash=_stable_hash(output_value),
        )


def _source_node(label: str, node: Any, *, parent_id: str | None) -> dict[str, Any]:
    return {
        "run_node_id": f"{label}:{node.id}",
        "run": label,
        "name": node.name,
        "definition": node.definition,
        "includes": list(node.includes),
        "excludes": list(node.excludes),
        "parent_id": parent_id,
        "supporting_ids": list(node.supporting_ids),
        "representative_ids": list(node.representative_ids),
    }


def build_alignment_candidates(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for index, left in enumerate(nodes):
        for right in nodes[index + 1 :]:
            if left["run"] == right["run"]:
                continue
            jaccard = _jaccard(left["supporting_ids"], right["supporting_ids"])
            name_similarity = _character_similarity(left["name"], right["name"])
            definition_similarity = _character_similarity(left["definition"], right["definition"])
            if not (
                normalized_name(left["name"]) == normalized_name(right["name"])
                or jaccard >= 0.1
                or name_similarity >= 0.35
                or definition_similarity >= 0.4
            ):
                continue
            pairs.append(
                {
                    "pair_id": f"pair_{len(pairs) + 1:03d}",
                    "left": left,
                    "right": right,
                    "signals": {
                        "support_jaccard": round(jaccard, 4),
                        "name_similarity": round(name_similarity, 4),
                        "definition_similarity": round(definition_similarity, 4),
                        "parent_equal": left["parent_id"] == right["parent_id"],
                        "representative_overlap": sorted(
                            set(left["representative_ids"]) & set(right["representative_ids"])
                        ),
                    },
                }
            )
    return pairs


def build_alignment_prompt(pairs: list[dict[str, Any]]) -> str:
    return f"""你是独立 Cross-run Domain Alignment 裁判。只判断预对齐候选对之间的语义关系，不创建、删除或修改 Taxonomy。
不能只按名字或出现次数判断；综合定义、includes/excludes、父级、support Jaccard 和代表内容重合。每个 pair_id 必须且只能输出一次，run_node_ids 必须原样复制。
relation 只能是 equivalent、parent_child_variant、granularity_variant、overlapping_but_distinct、unrelated、uncertain。只输出 JSON。
Schema：{ALIGNMENT_SCHEMA_HINT}
候选对：{_compact_json(pairs)}"""


def validate_alignment(value: AlignmentOutput, pairs: list[dict[str, Any]]) -> None:
    expected = {item["pair_id"]: [item["left"]["run_node_id"], item["right"]["run_node_id"]] for item in pairs}
    actual = {item.pair_id: item.run_node_ids for item in value.decisions}
    if len(actual) != len(value.decisions) or actual != expected:
        raise PipelineError(
            "Cross-run Alignment 未完整覆盖预对齐候选",
            code="alignment_decision_coverage_mismatch",
            retryable=False,
        )


def merge_aligned_nodes(
    nodes: list[dict[str, Any]], alignment: AlignmentOutput
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parent = {item["run_node_id"]: item["run_node_id"] for item in nodes}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    for decision in alignment.decisions:
        if decision.relation == "equivalent" and decision.confidence != "low":
            union(*decision.run_node_ids)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        grouped[find(node["run_node_id"])].append(node)
    decisions_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for decision in alignment.decisions:
        payload = decision.model_dump(mode="json")
        for node_id in decision.run_node_ids:
            decisions_by_node[node_id].append(payload)
    groups: list[dict[str, Any]] = []
    for index, members in enumerate(grouped.values(), start=1):
        runs = sorted({item["run"] for item in members})
        supporting = sorted({value for item in members for value in item["supporting_ids"]})
        representative = sorted({value for item in members for value in item["representative_ids"]})[:3]
        canonical = max(
            members,
            key=lambda item: (len(item["supporting_ids"]), len(item["definition"]), -len(item["name"])),
        )
        group_id = f"group_{index:03d}"
        groups.append(
            {
                "group_id": group_id,
                "members": [item["run_node_id"] for item in members],
                "source_runs": runs,
                "stability": "stable" if len(runs) == 3 else "probable" if len(runs) == 2 else "weak",
                "canonical_candidate": canonical,
                "supporting_ids": supporting,
                "representative_ids": representative,
                "parent_source_ids": sorted({item["parent_id"] for item in members if item["parent_id"]}),
                "alignment_decisions": [
                    decision
                    for item in members
                    for decision in decisions_by_node[item["run_node_id"]]
                ],
            }
        )
    relation_counts = Counter(item.relation for item in alignment.decisions)
    stable = sum(item["stability"] == "stable" for item in groups)
    probable = sum(item["stability"] == "probable" for item in groups)
    weak = sum(item["stability"] == "weak" for item in groups)
    metrics = {
        "source_node_count": len(nodes),
        "aligned_group_count": len(groups),
        "stable_count": stable,
        "probable_count": probable,
        "weak_count": weak,
        "node_alignment_rate": round((len(nodes) - weak) / len(nodes), 4) if nodes else 0,
        "relation_counts": dict(sorted(relation_counts.items())),
        "name_variation_rate": round(
            sum(len({next(node["name"] for node in nodes if node["run_node_id"] == member) for member in item["members"]}) > 1 for item in groups)
            / len(groups),
            4,
        ) if groups else 0,
        "granularity_disagreement_count": relation_counts.get("granularity_variant", 0)
        + relation_counts.get("parent_child_variant", 0),
        "run_only_node_count": weak,
        "support_overlap_distribution": [
            item.support_overlap for item in alignment.decisions
        ],
    }
    return groups, metrics


def build_risk_units(groups: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    deterministic: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    for group in groups:
        canonical = group["canonical_candidate"]
        issues: list[str] = []
        if group["stability"] == "weak":
            issues.append("weak_node")
        if len(group["parent_source_ids"]) > 1:
            issues.append("parent_disagreement")
        if not group["supporting_ids"]:
            deterministic.append({"code": "empty_support", "node_ids": [group["group_id"]], "blocking": True})
        if canonical["parent_id"] == canonical["run_node_id"]:
            deterministic.append({"code": "self_parent", "node_ids": [group["group_id"]], "blocking": True})
        if issues:
            risks.append(
                {
                    "unit_id": f"risk_{len(risks) + 1:03d}",
                    "group_ids": [group["group_id"]],
                    "risk_reasons": issues,
                    "local_subtree": group,
                }
            )
    for index, left in enumerate(groups):
        for right in groups[index + 1 :]:
            overlap = _jaccard(left["supporting_ids"], right["supporting_ids"])
            if overlap >= 0.55:
                risks.append(
                    {
                        "unit_id": f"risk_{len(risks) + 1:03d}",
                        "group_ids": [left["group_id"], right["group_id"]],
                        "risk_reasons": ["high_support_overlap"],
                        "support_jaccard": round(overlap, 4),
                        "local_subtree": [left, right],
                    }
                )
    return risks, deterministic


def build_validator_prompt(risk_units: list[dict[str, Any]]) -> str:
    return f"""你是独立 Domain Hierarchy Validator。只检查给出的风险节点和局部子树，不重建整棵分类树，也不得直接修改 Draft。
检查父子关系、兄弟重叠、粒度一致性及 Domain/Topic/Entity/Form/Context 混用。每个 unit_id 必须且只能输出一个建议；affected_node_ids 只能取该单元 group_ids。只输出 JSON。
Schema：{VALIDATOR_SCHEMA_HINT}
风险单元：{_compact_json(risk_units)}"""


def validate_hierarchy_output(
    value: HierarchyValidationOutput, risk_units: list[dict[str, Any]]
) -> None:
    expected = {item["unit_id"]: set(item["group_ids"]) for item in risk_units}
    actual = {item.unit_id: set(item.affected_node_ids) for item in value.findings}
    if len(actual) != len(value.findings) or set(actual) != set(expected):
        raise PipelineError(
            "Hierarchy Validator 未完整覆盖风险单元",
            code="hierarchy_validator_coverage_mismatch",
            retryable=False,
        )
    if any(not actual[key] <= expected[key] for key in expected):
        raise PipelineError(
            "Hierarchy Validator 修改了风险单元外节点",
            code="hierarchy_validator_scope_violation",
            retryable=False,
        )


def build_draft_a(
    groups: list[dict[str, Any]], validation: HierarchyValidationOutput
) -> tuple[DomainDraftA, list[dict[str, Any]]]:
    findings_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in validation.findings:
        payload = finding.model_dump(mode="json")
        for group_id in finding.affected_node_ids:
            findings_by_group[group_id].append(payload)
    group_to_draft = {item["group_id"]: f"draft_{index:03d}" for index, item in enumerate(groups, start=1)}
    source_to_group = {
        source: group["group_id"] for group in groups for source in group["members"]
    }
    nodes: list[DraftNode] = []
    uncertain: list[dict[str, Any]] = []
    for group in groups:
        canonical = group["canonical_candidate"]
        findings = findings_by_group[group["group_id"]]
        blocking_downgrade = next(
            (
                item for item in findings
                if item["blocking"]
                and item["confidence"] == "high"
                and item["operation"] in {
                    "downgrade_to_topic", "downgrade_to_entity", "exclude_from_draft"
                }
            ),
            None,
        )
        if blocking_downgrade:
            uncertain.append(
                {
                    "group_id": group["group_id"],
                    "reason": blocking_downgrade["reason"],
                    "source_runs": group["source_runs"],
                    "supporting_ids": group["supporting_ids"],
                    "relations": group["alignment_decisions"],
                    "trial_assignment_question": "验证该节点是否应保留为稳定 Domain。",
                }
            )
            continue
        parent_group = next(
            (source_to_group[value] for value in group["parent_source_ids"] if value in source_to_group),
            None,
        )
        stability = group["stability"]
        if any(item["operation"] == "mark_uncertain" for item in findings):
            stability = "uncertain"
        node = DraftNode(
            draft_node_id=group_to_draft[group["group_id"]],
            canonical_name=canonical["name"],
            definition=canonical["definition"],
            includes=canonical["includes"],
            excludes=canonical["excludes"],
            parent_id=group_to_draft.get(parent_group) if parent_group else None,
            stability=stability,
            source_run_nodes=group["members"],
            source_runs=group["source_runs"],
            supporting_ids=group["supporting_ids"],
            representative_ids=group["representative_ids"],
            validator_findings=findings,
            draft_decision="merged_equivalent_sources" if len(group["members"]) > 1 else "kept_with_evidence",
            decision_reason="仅合并高/中置信等价节点；保留完整来源和 Validator 建议。",
        )
        nodes.append(node)
        if stability in {"weak", "uncertain"}:
            uncertain.append(
                {
                    "draft_node_id": node.draft_node_id,
                    "reason": "跨运行稳定度不足或 Validator 标记不确定。",
                    "source_runs": node.source_runs,
                    "supporting_ids": node.supporting_ids,
                    "relations": group["alignment_decisions"],
                    "trial_assignment_question": "验证覆盖率、边界和主要/备选领域冲突。",
                }
            )
    valid_ids = {item.draft_node_id for item in nodes}
    nodes = [
        item.model_copy(update={"parent_id": item.parent_id if item.parent_id in valid_ids else None})
        for item in nodes
    ]
    return DomainDraftA(nodes=nodes), uncertain


def build_draft_a_gate(
    *,
    draft: DomainDraftA,
    groups: list[dict[str, Any]],
    alignment: AlignmentOutput,
    validation: HierarchyValidationOutput,
    deterministic_findings: list[dict[str, Any]],
) -> DomainRunGate:
    blocking = [item for item in deterministic_findings if item.get("blocking")]
    warnings = [item for item in deterministic_findings if not item.get("blocking")]
    if not any(item.parent_id is None for item in draft.nodes):
        blocking.append({"code": "no_top_level_domain", "details": []})
    source_groups = {item["group_id"] for item in groups}
    sourced_nodes = {source for node in draft.nodes for source in node.source_run_nodes}
    if any(not node.source_run_nodes or not node.source_runs for node in draft.nodes):
        blocking.append({"code": "draft_source_missing", "details": []})
    if any(not node.supporting_ids for node in draft.nodes):
        blocking.append({"code": "draft_support_missing", "details": []})
    blocking_validator = [
        item.model_dump(mode="json")
        for item in validation.findings
        if item.blocking and item.operation not in {
            "keep", "mark_uncertain", "downgrade_to_topic", "downgrade_to_entity", "exclude_from_draft"
        }
    ]
    if blocking_validator:
        blocking.append({"code": "validator_blocking_unhandled", "details": blocking_validator})
    weak_count = sum(item.stability == "weak" for item in draft.nodes)
    uncertain_count = sum(item.stability == "uncertain" for item in draft.nodes)
    if weak_count:
        warnings.append({"code": "weak_nodes", "details": [weak_count]})
    if uncertain_count:
        warnings.append({"code": "uncertain_nodes", "details": [uncertain_count]})
    contributions = Counter(run for node in draft.nodes for run in node.source_runs)
    if contributions and max(contributions.values()) > min(contributions.values()) * 1.8:
        warnings.append({"code": "run_contribution_imbalance", "details": [dict(contributions)]})
    return DomainRunGate(
        passed=not blocking,
        blocking_issues=blocking,
        warnings=warnings,
        metrics={
            "draft_node_count": len(draft.nodes),
            "top_level_count": sum(item.parent_id is None for item in draft.nodes),
            "subdomain_count": sum(item.parent_id is not None for item in draft.nodes),
            "stable_count": sum(item.stability == "stable" for item in draft.nodes),
            "probable_count": sum(item.stability == "probable" for item in draft.nodes),
            "weak_count": weak_count,
            "uncertain_count": uncertain_count,
            "alignment_decision_count": len(alignment.decisions),
            "source_group_count": len(source_groups),
            "sourced_run_node_count": len(sourced_nodes),
            "run_contributions": dict(sorted(contributions.items())),
        },
    )


def _repair_metrics(stages: list[dict[str, Any]]) -> dict[str, int | float]:
    repair_call_count = 0
    semantic = 0
    syntax = 0
    model_stage_count = 0
    for stage in stages:
        if stage.get("model"):
            model_stage_count += 1
        output_path = Path(str(stage.get("output_path") or ""))
        call_dir = output_path.parent if output_path.name == "parsed-output.json" else None
        if call_dir is None:
            continue
        diff = call_dir / "repair-semantic-diff.json"
        if diff.is_file():
            repair_call_count += 1
            payload = json.loads(diff.read_text(encoding="utf-8"))
            semantic += int(payload.get("semantic_change_count") or 0)
            syntax += int(payload.get("syntax_only_count") or 0)
    return {
        "repair_call_count": repair_call_count,
        "repair_rate": round(repair_call_count / model_stage_count, 4) if model_stage_count else 0,
        "repair_semantic_change_count": semantic,
        "repair_syntax_only_count": syntax,
    }


def _jaccard(left: list[str], right: list[str]) -> float:
    a, b = set(left), set(right)
    return len(a & b) / len(a | b) if a or b else 0.0


def _character_similarity(left: str, right: str) -> float:
    a = set(normalized_name(left))
    b = set(normalized_name(right))
    return len(a & b) / len(a | b) if a or b else 0.0


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
