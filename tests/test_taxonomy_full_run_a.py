from __future__ import annotations

import json
from pathlib import Path

import pytest

from shiliu.domain import PipelineError
from shiliu.db import Database
from shiliu.cli import build_parser
from shiliu.taxonomy.candidates import (
    CompactContentTypeTable,
    ContentTypeDraftV1,
    ContentTypeDiscoveryOutputV1,
    LocalTopLevelDiscoveryOutput,
    TopLevelDomainDraft,
    normalize_candidates,
    normalize_content_types,
)
from shiliu.taxonomy.quality import evaluate_top_level_rules
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from shiliu.taxonomy.workflow import (
    DOMAIN_CONSOLIDATION_TOKEN_POLICY,
    TaxonomyWorkflow,
    _domain_consolidation_max_tokens,
    _write_json_once,
)
from tests.test_taxonomy_checkpoint2 import (
    SnapshotRepository as WorkflowSnapshotRepository,
    WorkflowProvider,
    _insert_snapshot_row,
    card,
)


SNAPSHOT_HASH = "1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2"


class SnapshotRepository:
    def get_snapshot(self, snapshot_id: int):
        return {
            "id": snapshot_id,
            "snapshot_hash": SNAPSHOT_HASH,
            "content_count": 131,
            "discovery_eligible_count": 128,
            "trial_assignment_only_count": 3,
            "evidence_counts": {"A": 76, "B": 17, "C": 35, "D": 3},
            "cards": [],
        }


class RunRepository:
    def __init__(self) -> None:
        self.created: dict | None = None

    def create_run(self, **kwargs) -> int:
        self.created = kwargs
        return 42


class Provider:
    name = "synthetic-openai-compatible"
    model = "synthetic-model"
    thinking_enabled = False
    reasoning_effort = None


def _profile_manifest(root: Path) -> str:
    run_id = "profile-corpus-accepted"
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "snapshot_hash": SNAPSHOT_HASH,
                "profile_version": "classification_profile_v1",
                "prompt_version": "classification-profile-generation-v2",
                "profiles_hash": "profiles-hash",
                "selected_ids": [f"C{index:03d}" for index in range(1, 129)],
                "gates": {
                    "schema_success_100_percent": True,
                    "domain_pollution_zero": True,
                    "repair_zero": True,
                    "estimated_token_reduction_at_least_25_percent": True,
                },
            }
        ),
        encoding="utf-8",
    )
    return run_id


def _workflow(tmp_path: Path) -> tuple[TaxonomyWorkflow, RunRepository, str]:
    profile_root = tmp_path / "profiles"
    run_repository = RunRepository()
    workflow = TaxonomyWorkflow(
        snapshot_repository=SnapshotRepository(),  # type: ignore[arg-type]
        run_repository=run_repository,  # type: ignore[arg-type]
        provider_factory=lambda role: Provider(),  # type: ignore[arg-type]
        output_dir=tmp_path / "runs",
        profile_output_dir=profile_root,
    )
    return workflow, run_repository, _profile_manifest(profile_root)


def test_full_run_a_freezes_exact_manifest(monkeypatch, tmp_path) -> None:
    workflow, repository, profile_run_id = _workflow(tmp_path)
    monkeypatch.setattr(
        "shiliu.taxonomy.workflow._git_state", lambda: ("commit-hash", True)
    )

    run_id = workflow.create_full_discovery_run_a(
        snapshot_id=2,
        profile_run_id=profile_run_id,
        seed=101,
        batch_size=24,
    )

    assert run_id == 42
    assert repository.created is not None
    parameters = repository.created["parameters"]
    assert repository.created["run_kind"] == "full_discovery_run_a"
    assert len(parameters["selected_ids"]) == 128
    protocol = parameters["protocol_manifest"]
    assert protocol["snapshot_hash"] == SNAPSHOT_HASH
    assert protocol["evidence_counts"] == {"A": 76, "B": 17, "C": 35, "D": 3}
    assert protocol["domain_schema_version"] == "local-top-level-domain-schema-v2"
    assert protocol["content_type_schema_version"] == "content-type-local-schema-v2"
    assert protocol["protocol_version"] == "full-discovery-run-a-v3"
    assert protocol["content_type_consolidation_max_tokens"] == 8192
    assert protocol["domain_consolidation_token_policy"] == (
        DOMAIN_CONSOLIDATION_TOKEN_POLICY
    )
    assert protocol["git_commit"] == "commit-hash"
    assert json.loads(
        (tmp_path / "runs" / "run-000042" / "run-manifest.json").read_text()
    ) == protocol


def test_full_run_a_rejects_dirty_git(monkeypatch, tmp_path) -> None:
    workflow, _, profile_run_id = _workflow(tmp_path)
    monkeypatch.setattr(
        "shiliu.taxonomy.workflow._git_state", lambda: ("commit-hash", False)
    )

    with pytest.raises(PipelineError) as error:
        workflow.create_full_discovery_run_a(
            snapshot_id=2, profile_run_id=profile_run_id
        )

    assert error.value.code == "run_a_git_dirty"


def test_frozen_manifest_cannot_be_silently_replaced(tmp_path) -> None:
    path = tmp_path / "run-manifest.json"
    _write_json_once(path, {"seed": 101})
    _write_json_once(path, {"seed": 101})

    with pytest.raises(PipelineError) as error:
        _write_json_once(path, {"seed": 102})

    assert error.value.code == "taxonomy_resume_input_mismatch"


def test_full_run_a_cli_accepts_explicit_reuse_source() -> None:
    arguments = build_parser().parse_args(
        [
            "taxonomy",
            "create-full-run-a",
            "--profile-run-id",
            "profile-corpus",
            "--reuse-from-run-id",
            "10",
            "--reuse-content-type-consolidation-from-run-id",
            "11",
        ]
    )

    assert arguments.reuse_from_run_id == 10
    assert arguments.reuse_content_type_consolidation_from_run_id == 11


def test_domain_consolidation_budget_is_candidate_scaled_and_bounded() -> None:
    assert _domain_consolidation_max_tokens(
        DOMAIN_CONSOLIDATION_TOKEN_POLICY, candidate_count=0
    ) == 16384
    assert _domain_consolidation_max_tokens(
        DOMAIN_CONSOLIDATION_TOKEN_POLICY, candidate_count=42
    ) == 19456
    assert _domain_consolidation_max_tokens(
        DOMAIN_CONSOLIDATION_TOKEN_POLICY, candidate_count=1000
    ) == 24576


def _local(name: str, parent: str, ids: list[str], ordinal: int):
    return LocalTopLevelDiscoveryOutput.model_validate(
        {
            "domains": [
                {
                    "provisional_id": f"ld_{ordinal}",
                    "name": name,
                    "definition": f"{name}的稳定知识边界",
                    "includes": [name],
                    "excludes": ["具体工具"],
                    "supporting_ids": ids,
                    "representative_ids": ids[:2],
                    "possible_parent": parent,
                    "confidence": "high",
                    "evidence_codes": ["durable_domain"],
                    "node_type": "domain",
                }
            ],
            "topic_hints": [],
            "ambiguous_ids": [],
        }
    )


def _content_type_draft() -> ContentTypeDraftV1:
    return ContentTypeDraftV1.model_validate(
        {
            "content_types": [
                {
                    "id": "ct_01",
                    "name": "教程与实操",
                    "definition": "以步骤和操作演示帮助完成任务",
                    "includes": ["步骤"],
                    "excludes": ["纯评论"],
                    "supporting_ids": ["C001", "C002"],
                    "representative_ids": ["C001"],
                    "node_type": "content_type",
                }
            ],
            "candidate_decisions": [],
            "consolidation_notes": [],
        }
    )


def test_quality_warns_when_supported_subdomains_are_missing() -> None:
    allowed = {f"C{index:03d}" for index in range(1, 7)}
    table = normalize_candidates(
        [
            _local("Agent 评测", "Agent 工程", ["C001", "C002"], 1),
            _local("Agent 编排", "Agent 工程", ["C003", "C004"], 2),
        ],
        allowed_ids=allowed,
    )
    draft = TopLevelDomainDraft.model_validate(
        {
            "domains": [
                {
                    "id": "d_01",
                    "name": "Agent 工程",
                    "definition": "Agent 系统的设计、实现和验证",
                    "includes": ["Agent 系统"],
                    "excludes": ["单一产品新闻"],
                    "supporting_ids": ["C001", "C002", "C003", "C004"],
                    "representative_ids": ["C001", "C003"],
                    "children": [],
                }
            ],
            "candidate_decisions": [],
            "consolidation_notes": [],
        }
    )

    result = evaluate_top_level_rules(
        draft=draft,
        candidate_table=table,
        allowed_ids=allowed,
        known_entity_names=set(),
        content_type_names={"教程与实操"},
        content_type_draft=_content_type_draft(),
        content_type_table=CompactContentTypeTable(
            content_types=[], source_batch_count=1
        ),
        local_content_types=[],
        evidence_by_id={short_id: "A" for short_id in allowed},
    )

    assert "missing_reasonable_subdomains" in {
        item.code for item in result.warnings
    }


def test_quality_blocks_domain_leakage_into_content_type() -> None:
    allowed = {"C001", "C002"}
    table = normalize_candidates(
        [_local("Agent 工程", "软件工程", ["C001", "C002"], 1)],
        allowed_ids=allowed,
    )
    draft = TopLevelDomainDraft.model_validate(
        {
            "domains": [
                {
                    "id": "d_01",
                    "name": "Agent 工程",
                    "definition": "Agent 系统设计与实现",
                    "includes": ["Agent 系统"],
                    "excludes": ["泛娱乐"],
                    "supporting_ids": ["C001", "C002"],
                    "representative_ids": ["C001"],
                }
            ],
            "consolidation_notes": [],
        }
    )
    content_types = _content_type_draft().model_copy(deep=True)
    content_types.content_types[0].name = "Agent 工程"

    result = evaluate_top_level_rules(
        draft=draft,
        candidate_table=table,
        allowed_ids=allowed,
        known_entity_names=set(),
        content_type_names={"Agent 工程"},
        content_type_draft=content_types,
    )

    assert "domain_leakage_into_content_type" in {
        item.code for item in result.blocking_issues
    }


def _content_batch(batch_index: int) -> ContentTypeDiscoveryOutputV1:
    first_id = (batch_index - 1) * 8 + 1
    return ContentTypeDiscoveryOutputV1.model_validate(
        {
            "content_types": [
                {
                    "provisional_id": f"lct_{batch_index}_{offset}",
                    "name": f"形式 {batch_index}-{offset}",
                    "definition": "独立的合成内容形式",
                    "includes": ["合成示例"],
                    "excludes": ["其他形式"],
                    "supporting_ids": [f"C{first_id + offset:03d}"],
                    "representative_ids": [f"C{first_id + offset:03d}"],
                }
                for offset in range(8)
            ],
            "ambiguous_ids": [],
        }
    )


def test_normalized_candidate_capacity_is_derived_from_batch_protocol() -> None:
    outputs = [_content_batch(index) for index in range(1, 7)]
    allowed = {f"C{index:03d}" for index in range(1, 49)}

    table = normalize_content_types(outputs, allowed_ids=allowed)

    assert len(table.content_types) == 48
    assert table.source_batch_count == 6


def test_domain_and_topic_intermediate_capacity_is_not_silently_truncated() -> None:
    outputs = []
    allowed = {f"C{index:03d}" for index in range(1, 49)}
    for batch_index in range(1, 7):
        first_id = (batch_index - 1) * 8 + 1
        outputs.append(
            LocalTopLevelDiscoveryOutput.model_validate(
                {
                    "domains": [
                        {
                            "provisional_id": f"ld_{batch_index}_{offset}",
                            "name": f"领域 {batch_index}-{offset}",
                            "definition": "合成稳定领域",
                            "supporting_ids": [f"C{first_id + offset:03d}"],
                        }
                        for offset in range(8)
                    ],
                    "topic_hints": [
                        {
                            "name": f"主题 {batch_index}-{offset}",
                            "supporting_ids": [f"C{first_id:03d}"],
                        }
                        for offset in range(5)
                    ],
                    "ambiguous_ids": [],
                }
            )
        )

    table = normalize_candidates(outputs, allowed_ids=allowed)

    assert len(table.domains) == 48
    assert len(table.topic_hints) == 30


def test_unhandled_normalization_error_marks_run_and_stage_failed(
    monkeypatch, app_paths
) -> None:
    db = Database(app_paths.database)
    db.initialize()
    snapshot_id = _insert_snapshot_row(db)
    cards = [card(index) for index in range(1, 41)]
    provider = WorkflowProvider()
    workflow = TaxonomyWorkflow(
        snapshot_repository=WorkflowSnapshotRepository(cards),  # type: ignore[arg-type]
        run_repository=TaxonomyRunRepository(db),
        provider_factory=lambda role: provider,  # type: ignore[arg-type]
        output_dir=app_paths.content_dir / "taxonomy" / "runtime" / "runs",
    )
    run_id = workflow.create_run(
        snapshot_id=snapshot_id, batch_size=20, limit=40
    )
    monkeypatch.setattr(
        "shiliu.taxonomy.workflow.normalize_content_types",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("capacity")),
    )

    with pytest.raises(ValueError, match="capacity"):
        workflow.execute(run_id)

    status = workflow.status(run_id)
    assert status["run"]["status"] == "failed"
    assert status["run"]["current_stage"] == "content_type_normalization"
    stages = {
        (item["stage_name"], item["unit_key"]): item
        for item in status["stages"]
    }
    assert stages[("content_type_normalization", "main")]["status"] == "failed"
    assert all(
        stages[(name, f"batch-{index:03d}")]["status"] == "completed"
        for name in ("local_discovery", "content_type_discovery")
        for index in (1, 2)
    )
    failure = json.loads(
        (
            workflow.output_dir
            / f"run-{run_id:06d}"
            / "run-failure.json"
        ).read_text()
    )
    assert failure["failed_stage"] == "content_type_normalization"
    assert failure["retryable"] is False
    assert failure["allows_model_artifact_reuse"] is True


class ConsolidationCrashesProvider(WorkflowProvider):
    def complete_raw(self, prompt: str, *, max_tokens: int | None = None):
        if "全局 Content Type 归并器" in prompt:
            raise RuntimeError("consolidation crashed")
        return super().complete_raw(prompt, max_tokens=max_tokens)


def test_consolidation_exception_marks_only_current_stage_failed(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    snapshot_id = _insert_snapshot_row(db)
    cards = [card(index) for index in range(1, 41)]
    provider = ConsolidationCrashesProvider()
    workflow = TaxonomyWorkflow(
        snapshot_repository=WorkflowSnapshotRepository(cards),  # type: ignore[arg-type]
        run_repository=TaxonomyRunRepository(db),
        provider_factory=lambda role: provider,  # type: ignore[arg-type]
        output_dir=app_paths.content_dir / "taxonomy" / "runtime" / "runs",
    )
    run_id = workflow.create_run(
        snapshot_id=snapshot_id, batch_size=20, limit=40
    )

    with pytest.raises(RuntimeError, match="consolidation crashed"):
        workflow.execute(run_id)

    status = workflow.status(run_id)
    stages = {
        (item["stage_name"], item["unit_key"]): item
        for item in status["stages"]
    }
    assert status["run"]["status"] == "failed"
    assert stages[("content_type_consolidation", "main")]["status"] == "failed"
    assert stages[("content_type_normalization", "main")]["status"] == "completed"
    assert all(
        stages[(name, f"batch-{index:03d}")]["status"] == "completed"
        for name in ("local_discovery", "content_type_discovery")
        for index in (1, 2)
    )


def test_new_run_reuses_verified_batches_with_lineage_and_zero_attempts(
    app_paths,
) -> None:
    db = Database(app_paths.database)
    db.initialize()
    snapshot_id = _insert_snapshot_row(db)
    cards = [card(index) for index in range(1, 41)]
    provider = WorkflowProvider()
    repository = TaxonomyRunRepository(db)
    workflow = TaxonomyWorkflow(
        snapshot_repository=WorkflowSnapshotRepository(cards),  # type: ignore[arg-type]
        run_repository=repository,
        provider_factory=lambda role: provider,  # type: ignore[arg-type]
        output_dir=app_paths.content_dir / "taxonomy" / "runtime" / "runs",
    )
    provider_contract = {
        "provider": "synthetic",
        "model": provider.model,
        "thinking_enabled": provider.thinking_enabled,
        "reasoning_effort": provider.reasoning_effort,
        "temperature": None,
    }
    protocol = {
        "snapshot_id": snapshot_id,
        "snapshot_hash": "a" * 64,
        "discovery_eligible_count": 40,
        "evidence_counts": {"A": 40, "B": 0, "C": 0, "D": 0},
        "profile_run_id": None,
        "profile_hash": None,
        "profile_version": None,
        "compact_form_view_version": "compact_form_view_v1",
        "domain_prompt_version": "top-level-local-discovery-v2",
        "content_type_prompt_version": "content-type-discovery-v2",
        "domain_schema_version": "local-top-level-domain-schema-v2",
        "content_type_schema_version": "content-type-local-schema-v2",
        "temperature": None,
        "batch_size": 20,
        "run_seed": 73,
        "ordering_strategy": "stable_short_id_map_then_seeded_shuffle",
        "providers": {
            "taxonomy_local": provider_contract,
            "taxonomy_content_type": provider_contract,
            "taxonomy_content_type_global": provider_contract,
        },
    }
    selected = [f"C{index:03d}" for index in range(1, 41)]
    source_run_id = workflow.create_run(
        snapshot_id=snapshot_id,
        seed=73,
        batch_size=20,
        limit=None,
        selected_ids=selected,
        protocol_manifest=protocol,
    )
    assert workflow.execute(source_run_id)["run"]["status"] == "completed"
    source_stages_before = repository.list_stages(source_run_id)
    calls_before = (
        provider.local_calls,
        provider.content_type_calls,
        provider.content_type_consolidation_calls,
    )

    target_protocol = {
        **protocol,
        "content_type_consolidation_max_tokens": 8192,
        "reuse_from_run_id": source_run_id,
        "reuse_content_type_consolidation_from_run_id": source_run_id,
    }
    target_run_id = workflow.create_run(
        snapshot_id=snapshot_id,
        seed=73,
        batch_size=20,
        limit=None,
        selected_ids=selected,
        protocol_manifest=target_protocol,
    )
    result = workflow.execute(target_run_id)

    assert result["run"]["status"] == "completed"
    assert (
        provider.local_calls,
        provider.content_type_calls,
        provider.content_type_consolidation_calls,
    ) == calls_before
    reused = [
        item
        for item in result["stages"]
        if item["stage_name"] in {"local_discovery", "content_type_discovery"}
    ]
    assert len(reused) == 4
    assert all(item["status"] == "completed" for item in reused)
    assert all(item["attempt_count"] == 0 for item in reused)
    lineage = json.loads(
        (
            workflow.output_dir
            / f"run-{target_run_id:06d}"
            / "reused-discovery-lineage.json"
        ).read_text()
    )
    assert lineage["source_run_id"] == source_run_id
    assert lineage["reused_stage_count"] == 4
    assert all(item["source_input_hash"] for item in lineage["stages"])
    assert all(item["source_output_hash"] for item in lineage["stages"])
    assert repository.list_stages(source_run_id) == source_stages_before
    consolidation = next(
        item
        for item in result["stages"]
        if item["stage_name"] == "content_type_consolidation"
    )
    assert consolidation["attempt_count"] == 0
    consolidation_lineage = json.loads(
        (
            workflow.output_dir
            / f"run-{target_run_id:06d}"
            / "reused-consolidation-lineage.json"
        ).read_text()
    )
    assert consolidation_lineage["reused_from_run_id"] == source_run_id
