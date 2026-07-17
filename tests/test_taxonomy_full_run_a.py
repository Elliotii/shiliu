from __future__ import annotations

import json
from pathlib import Path

import pytest

from shiliu.domain import PipelineError
from shiliu.taxonomy.candidates import (
    CompactContentTypeTable,
    ContentTypeDraftV1,
    LocalTopLevelDiscoveryOutput,
    TopLevelDomainDraft,
    normalize_candidates,
)
from shiliu.taxonomy.quality import evaluate_top_level_rules
from shiliu.taxonomy.workflow import TaxonomyWorkflow, _write_json_once


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
