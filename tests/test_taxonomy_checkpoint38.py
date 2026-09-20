from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from shiliu.app import Application
from shiliu.cli import build_parser
from shiliu.db import Database
from shiliu.domain import PipelineError
from shiliu.taxonomy.candidates import (
    ContentTypeDraftV1,
    ContentTypeDiscoveryOutputV1,
    DualViewDiscoveryOutputV1,
    build_content_type_consolidation_prompt,
    build_top_level_consolidation_prompt,
    normalize_content_types,
)
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from shiliu.taxonomy.workflow import TaxonomyWorkflow
from tests.test_taxonomy_checkpoint2 import (
    SnapshotRepository,
    WorkflowProvider,
    _insert_snapshot_row,
    card,
)
from tests.test_taxonomy_checkpoint35 import _draft, _table


def local_content_type(name: str, ids: list[str]) -> ContentTypeDiscoveryOutputV1:
    return ContentTypeDiscoveryOutputV1.model_validate(
        {
            "content_types": [
                {
                    "provisional_id": "lct_tutorial",
                    "name": name,
                    "definition": "通过讲解和操作步骤帮助完成任务",
                    "supporting_ids": ids,
                }
            ],
            "ambiguous_ids": [],
        }
    )


def content_type_draft() -> ContentTypeDraftV1:
    return ContentTypeDraftV1.model_validate(
        {
            "content_types": [
                {
                    "id": "ct_01",
                    "name": "教程与实操",
                    "definition": "通过讲解和操作帮助完成任务",
                    "includes": ["操作步骤"],
                    "excludes": ["纯观点评论"],
                    "supporting_ids": ["C001", "C002"],
                    "representative_ids": ["C001"],
                    "node_type": "content_type",
                }
            ],
            "consolidation_notes": [],
        }
    )


def test_dual_view_schemas_and_consolidation_inputs_remain_separate() -> None:
    table = normalize_content_types(
        [
            local_content_type("教程与实操", ["C001", "C002"]),
            local_content_type("教程 与 实操", ["C002", "C003"]),
        ],
        allowed_ids={"C001", "C002", "C003"},
    )
    assert len(table.content_types) == 1
    assert table.content_types[0].batch_count == 2
    assert table.content_types[0].support_count == 3

    content_prompt = build_content_type_consolidation_prompt(table)
    domain_prompt = build_top_level_consolidation_prompt(_table())
    assert "Compact Content Type Table" in content_prompt
    assert '"domains"' not in content_prompt
    assert '"content_types"' not in domain_prompt

    integrated = DualViewDiscoveryOutputV1(
        domain_input_view="classification_profile_v1",
        domain_draft=_draft(),
        content_type_draft=content_type_draft(),
    )
    assert integrated.domain_draft.domains
    assert integrated.content_type_draft.content_types

    payload = content_type_draft().model_dump(mode="json")
    payload["domains"] = []
    with pytest.raises(ValidationError):
        ContentTypeDraftV1.model_validate(payload)


def test_content_type_batches_resume_without_repeating_completed_domain_or_batch(
    app_paths,
) -> None:
    db = Database(app_paths.database)
    db.initialize()
    snapshot_id = _insert_snapshot_row(db)
    cards = [card(index) for index in range(1, 41)] + [card(41, "D")]
    provider = WorkflowProvider(fail_second_content_type_once=True)
    workflow = TaxonomyWorkflow(
        snapshot_repository=SnapshotRepository(cards),  # type: ignore[arg-type]
        run_repository=TaxonomyRunRepository(db),
        provider_factory=lambda role: provider,  # type: ignore[arg-type]
        output_dir=app_paths.content_dir / "taxonomy" / "runtime" / "runs",
    )
    run_id = workflow.create_run(snapshot_id=snapshot_id, batch_size=20, limit=40)

    with pytest.raises(PipelineError, match="模拟 Content Type 中断"):
        workflow.execute(run_id)
    stages = {
        (item["stage_name"], item["unit_key"]): item
        for item in workflow.status(run_id)["stages"]
    }
    assert stages[("content_type_discovery", "batch-001")]["status"] == "completed"
    assert stages[("content_type_discovery", "batch-002")]["status"] == "retry_wait"

    result = workflow.execute(run_id, resume=True)

    assert result["run"]["status"] == "completed"
    assert provider.local_calls == 2
    assert provider.content_type_calls == 3
    assert provider.content_type_consolidation_calls == 1
    stages = {
        (item["stage_name"], item["unit_key"]): item for item in result["stages"]
    }
    assert stages[("content_type_discovery", "batch-001")]["attempt_count"] == 1
    assert stages[("content_type_discovery", "batch-002")]["attempt_count"] == 2
    assert stages[("content_type_normalization", "main")]["status"] == "completed"
    assert stages[("content_type_consolidation", "main")]["status"] == "completed"


def test_both_content_type_provider_roles_use_thinking_off(monkeypatch) -> None:
    captured: list[dict] = []

    class Provider:
        def __init__(self, **kwargs) -> None:
            captured.append(kwargs)

    app = Application.__new__(Application)
    app.config = SimpleNamespace(
        api_key_ref="service:account",
        llm_base_url="https://example.invalid/v1",
        model_for=lambda role: "model-x",
    )
    monkeypatch.setattr("shiliu.app.load_api_key", lambda reference: "secret")
    monkeypatch.setattr("shiliu.app.OpenAICompatibleProvider", Provider)

    app.provider("taxonomy_content_type")
    app.provider("taxonomy_content_type_global")

    assert [
        (item["thinking_enabled"], item["reasoning_effort"]) for item in captured
    ] == [(False, None), (False, None)]


def test_dual_view_regression_cli_freezes_profile_run_and_batch_plan() -> None:
    arguments = build_parser().parse_args(
        [
            "taxonomy",
            "create-dual-view-regression",
            "--snapshot-id",
            "2",
            "--profile-run-id",
            "accepted-profile",
        ]
    )

    assert arguments.snapshot_id == 2
    assert arguments.profile_run_id == "accepted-profile"
    assert arguments.seed == 73
    assert arguments.batch_size == 24
