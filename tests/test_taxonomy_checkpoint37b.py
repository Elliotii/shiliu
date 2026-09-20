from __future__ import annotations

import json

import pytest

from shiliu.cli import build_parser
from shiliu.db import Database
from shiliu.domain import PipelineError
from shiliu.taxonomy.candidates import (
    TopLevelDomainDraft,
    build_top_level_local_prompt,
)
from shiliu.taxonomy.comparison import (
    DomainAlignmentReport,
    ProfileDiscoveryComparisonService,
    build_alignment_prompt,
    validate_alignment,
)
from shiliu.taxonomy.workflow import TaxonomyWorkflow
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from tests.test_taxonomy_checkpoint2 import (
    SnapshotRepository,
    WorkflowProvider,
    _insert_snapshot_row,
    card,
)


def draft(prefix: str = "d") -> TopLevelDomainDraft:
    return TopLevelDomainDraft.model_validate(
        {
            "domains": [
                {
                    "id": f"{prefix}_01",
                    "name": "软件工程",
                    "definition": "软件系统设计与实现",
                    "includes": ["系统设计"],
                    "excludes": ["单一产品新闻"],
                    "supporting_ids": ["C001", "C002"],
                    "representative_ids": ["C001"],
                },
                {
                    "id": f"{prefix}_02",
                    "name": "模型工程",
                    "definition": "模型训练与部署",
                    "includes": ["模型部署"],
                    "excludes": ["泛娱乐"],
                    "supporting_ids": ["C003"],
                    "representative_ids": ["C003"],
                },
            ],
            "consolidation_notes": [],
        }
    )


def test_local_discovery_prompt_changes_only_the_row_protocol() -> None:
    compact_rows = [["C001", "A", "标题", "结论", ["观点"], ["ToolX"]]]
    profile_rows = [
        ["C001", "A", "主题", "目标", ["概念"], ["开发"], ["ToolX"], []]
    ]

    compact = build_top_level_local_prompt(compact_rows, representation="compact")
    profile = build_top_level_local_prompt(
        profile_rows, representation="classification_profile_v1"
    )

    compact_prefix = compact.split("输入行协议：", 1)[0]
    profile_prefix = profile.split("输入行协议：", 1)[0]
    assert compact_prefix == profile_prefix
    assert "一句话结论" in compact
    assert "main_subject" in profile
    with pytest.raises(ValueError):
        build_top_level_local_prompt([], representation="unknown")


def test_alignment_contract_covers_every_source_and_rejects_unknown_targets() -> None:
    value = DomainAlignmentReport.model_validate(
        {
            "matches": [
                {
                    "source_id": "d_01",
                    "target_ids": ["p_01"],
                    "relation": "equivalent",
                    "reason": "名称、定义和支持内容一致",
                },
                {
                    "source_id": "d_02",
                    "target_ids": [],
                    "relation": "missing",
                    "reason": "目标结构没有对应领域",
                },
            ],
            "summary": "一个领域保留，一个缺失",
        }
    )
    validate_alignment(
        value, source_ids={"d_01", "d_02"}, target_ids={"p_01", "p_02"}
    )

    wrong = value.model_copy(
        update={
            "matches": [
                value.matches[0].model_copy(update={"target_ids": ["p_99"]}),
                value.matches[1],
            ]
        }
    )
    with pytest.raises(PipelineError) as error:
        validate_alignment(
            wrong, source_ids={"d_01", "d_02"}, target_ids={"p_01", "p_02"}
        )
    assert error.value.code == "comparison_alignment_target_mismatch"


def test_alignment_prompt_contains_only_draft_evidence() -> None:
    prompt = build_alignment_prompt(
        draft("d"), draft("d"), source_label="A1", target_label="B1"
    )

    assert "supporting_ids" in prompt
    assert "representative_ids" in prompt
    assert "equivalent" in prompt
    assert "不得读取或猜测卡片内容" in prompt
    assert "字幕" not in prompt


def test_workflow_profile_loader_requires_accepted_v2_and_exact_ids(tmp_path) -> None:
    profile_dir = tmp_path / "profiles"
    run_dir = profile_dir / "accepted"
    run_dir.mkdir(parents=True)
    manifest = {
        "status": "completed",
        "snapshot_hash": "a" * 64,
        "profile_version": "classification_profile_v1",
        "prompt_version": "classification-profile-generation-v2",
        "gates": {"schema": True, "repair": True},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_dir / "profile-discovery-view.jsonl").write_text(
        json.dumps(["C001", "A", "主题", "目标", [], [], [], []]) + "\n",
        encoding="utf-8",
    )
    workflow = TaxonomyWorkflow.__new__(TaxonomyWorkflow)
    workflow.profile_output_dir = profile_dir

    rows = workflow._load_profile_rows(
        profile_run_id="accepted",
        snapshot_hash="a" * 64,
        expected_ids={"C001"},
    )
    assert rows["C001"][2] == "主题"

    with pytest.raises(PipelineError) as mismatch:
        workflow._load_profile_rows(
            profile_run_id="accepted",
            snapshot_hash="a" * 64,
            expected_ids={"C002"},
        )
    assert mismatch.value.code == "taxonomy_profile_ids_mismatch"


def test_pair_metrics_apply_directional_coverage_and_ambiguity_deltas() -> None:
    service = ProfileDiscoveryComparisonService.__new__(
        ProfileDiscoveryComparisonService
    )
    compact = {
        "domain_count": 8,
        "c_representative_support_rate": 0.3,
        "c_domain_signal_rate": 0.8,
        "c_content_type_support_rate": 0.7,
        "c_content_type_ambiguity_rate": 0.2,
        "ambiguity_rate": 0.10,
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "elapsed_seconds": 10,
    }
    profile = {
        "domain_count": 7,
        "c_representative_support_rate": 0.2,
        "c_domain_signal_rate": 0.76,
        "c_content_type_support_rate": 0.4,
        "c_content_type_ambiguity_rate": 0.5,
        "ambiguity_rate": 0.14,
        "prompt_tokens": 70,
        "completion_tokens": 50,
        "elapsed_seconds": 9,
    }
    metrics = service._pair_metrics(
        compact, profile, {"weighted_recovery": 0.9}
    )

    assert metrics["weighted_domain_recovery"] == 0.9
    assert metrics["c_domain_signal_delta"] == -0.04
    assert metrics["c_content_type_ambiguity_delta"] == 0.3
    assert metrics["ambiguity_rate_delta"] == 0.04
    assert metrics["compact_domain_count"] != metrics["profile_domain_count"]


def test_new_unified_profile_comparison_is_retired_but_audit_resume_remains() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "taxonomy",
                "profile-compare",
                "--snapshot-id",
                "2",
                "--profile-run-id",
                "profile-run",
            ]
        )
    arguments = build_parser().parse_args(
        ["taxonomy", "profile-compare-resume", "existing-comparison"]
    )
    assert arguments.comparison_id == "existing-comparison"

    service = ProfileDiscoveryComparisonService.__new__(
        ProfileDiscoveryComparisonService
    )
    with pytest.raises(PipelineError) as error:
        service.run(snapshot_id=2, profile_run_id="profile-run")
    assert error.value.code == "unified_profile_experiment_retired"


def test_workflow_executes_profile_representation_without_compact_card_payload(
    app_paths,
) -> None:
    db = Database(app_paths.database)
    db.initialize()
    snapshot_id = _insert_snapshot_row(db)
    cards = [card(index) for index in range(1, 41)] + [card(41, "D")]
    profile_root = app_paths.content_dir / "taxonomy" / "runtime" / "profile_spikes"
    profile_dir = profile_root / "accepted-v2"
    profile_dir.mkdir(parents=True)
    gates = {
        "schema_success_100_percent": True,
        "domain_pollution_zero": True,
        "repair_zero": True,
        "estimated_token_reduction_at_least_25_percent": True,
    }
    (profile_dir / "manifest.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "snapshot_hash": "a" * 64,
                "profile_version": "classification_profile_v1",
                "prompt_version": "classification-profile-generation-v2",
                "gates": gates,
            }
        ),
        encoding="utf-8",
    )
    profile_rows = [
        [
            f"C{index:03d}",
            "A",
            f"Profile主题{index}",
            "完成合成目标",
            ["合成概念"],
            ["学习"],
            ["SyntheticTool"],
            [],
        ]
        for index in range(1, 41)
    ]
    (profile_dir / "profile-discovery-view.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in profile_rows),
        encoding="utf-8",
    )
    provider = WorkflowProvider()
    workflow = TaxonomyWorkflow(
        snapshot_repository=SnapshotRepository(cards),  # type: ignore[arg-type]
        run_repository=TaxonomyRunRepository(db),
        provider_factory=lambda role: provider,  # type: ignore[arg-type]
        output_dir=app_paths.content_dir / "taxonomy" / "runtime" / "runs",
        profile_output_dir=profile_root,
    )
    run_id = workflow.create_run(
        snapshot_id=snapshot_id,
        batch_size=20,
        limit=None,
        representation="classification_profile_v1",
        profile_run_id="accepted-v2",
        selected_ids=[f"C{index:03d}" for index in range(1, 41)],
    )

    result = workflow.execute(run_id)

    assert result["run"]["status"] == "completed"
    prompt = (
        workflow.output_dir
        / f"run-{run_id:06d}"
        / "local_discovery"
        / "batch-001"
        / "attempt-01"
        / "prompt.txt"
    ).read_text(encoding="utf-8")
    assert "main_subject" in prompt
    assert "Profile主题" in prompt
    assert '"标题 ' not in prompt
    content_type_prompt = (
        workflow.output_dir
        / f"run-{run_id:06d}"
        / "content_type_discovery"
        / "batch-001"
        / "attempt-01"
        / "prompt.txt"
    ).read_text(encoding="utf-8")
    assert '"标题 ' in content_type_prompt
    assert "Profile主题" not in content_type_prompt
    integrated = json.loads(
        (
            workflow.output_dir
            / f"run-{run_id:06d}"
            / "dual-view-discovery-output.json"
        ).read_text(encoding="utf-8")
    )
    assert integrated["domain_input_view"] == "classification_profile_v1"
    assert integrated["content_type_input_view"] == "compact_form_view_v1"
    assert "content_types" not in integrated["domain_draft"]
    assert "domains" not in integrated["content_type_draft"]
