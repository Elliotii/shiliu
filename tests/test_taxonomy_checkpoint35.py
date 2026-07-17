from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from shiliu.app import Application
from shiliu.db import Database, utc_now
from shiliu.domain import PipelineError
from shiliu.taxonomy.candidates import (
    CompactCandidateTable,
    LocalTopLevelDiscoveryOutput,
    TopLevelDomainDraft,
    build_content_type_prompt,
    build_top_level_consolidation_prompt,
    build_top_level_local_prompt,
    normalize_candidates,
    stable_hash,
)
from shiliu.taxonomy.discovery import build_consolidation_prompt
from shiliu.taxonomy.quality import (
    build_local_validation_prompt,
    evaluate_top_level_rules,
)
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from shiliu.taxonomy.workflow import TaxonomyWorkflow


def _local(
    name: str,
    ids: list[str],
    *,
    provisional_id: str = "ld_software",
) -> LocalTopLevelDiscoveryOutput:
    return LocalTopLevelDiscoveryOutput.model_validate(
        {
            "domains": [
                {
                    "provisional_id": provisional_id,
                    "name": name,
                    "definition": "软件系统设计与实现的长期知识领域",
                    "supporting_ids": ids[:5],
                    "evidence_codes": ["durable", "supported"],
                }
            ],
            "topic_hints": [],
            "ambiguous_ids": [],
        }
    )


def _draft(*, overlap: bool = False, entity_name: str | None = None) -> TopLevelDomainDraft:
    right_ids = ["C002", "C003", "C004"] if overlap else ["C004", "C005"]
    return TopLevelDomainDraft.model_validate(
        {
            "domains": [
                {
                    "id": "d_01",
                    "name": entity_name or "软件工程",
                    "definition": "软件系统设计与实现",
                    "includes": ["系统设计"],
                    "excludes": ["单一工具新闻"],
                    "supporting_ids": ["C001", "C002", "C003"],
                    "representative_ids": ["C001", "C002"],
                },
                {
                    "id": "d_02",
                    "name": "工程质量",
                    "definition": "软件验证与质量保障",
                    "includes": ["测试"],
                    "excludes": ["泛娱乐"],
                    "supporting_ids": right_ids,
                    "representative_ids": right_ids[:2],
                },
            ],
            "consolidation_notes": [],
        }
    )


def _table() -> CompactCandidateTable:
    return normalize_candidates(
        [
            _local("软件 工程", ["C001", "C002", "C003", "C004", "C005"]),
            _local(
                "软件工程",
                ["C003", "C004", "C005", "C006", "C007"],
                provisional_id="ld_engineering",
            ),
            _local("工程质量", ["C004", "C005"], provisional_id="ld_quality"),
        ],
        allowed_ids={f"C{index:03d}" for index in range(1, 8)},
    )


def test_local_schema_enforces_quantity_and_forbids_entities() -> None:
    candidate = _local("软件工程", ["C001"]).domains[0].model_dump(mode="json")
    with pytest.raises(ValidationError):
        LocalTopLevelDiscoveryOutput.model_validate(
            {"domains": [{**candidate, "provisional_id": f"ld_{index}"} for index in range(9)]}
        )
    with pytest.raises(ValidationError):
        LocalTopLevelDiscoveryOutput.model_validate(
            {"domains": [candidate], "entities": [{"name": "ToolX"}]}
        )
    with pytest.raises(ValidationError):
        LocalTopLevelDiscoveryOutput.model_validate(
            {
                "domains": [candidate],
                "topic_hints": [
                    {"name": f"topic-{index}", "supporting_ids": ["C001"]}
                    for index in range(6)
                ],
            }
        )


def test_content_type_contract_is_independent_from_domain_discovery() -> None:
    rows = [["C001", "A", "教程", "完成部署", ["步骤"], ["ToolX"]]]
    content_prompt = build_content_type_prompt(rows)
    domain_prompt = build_top_level_local_prompt(rows)

    assert "不得输出 Domain、Topic 或 Entity" in content_prompt
    assert '"domains"' not in content_prompt
    assert '"content_types"' not in domain_prompt
    assert "不得输出 Content Type、二级领域、Entity" in domain_prompt


def test_normalizer_deduplicates_and_caps_transmitted_support() -> None:
    table = _table()
    software = next(item for item in table.domains if "软件" in item.name)

    assert len(table.domains) == 2
    assert software.support_count == 7
    assert software.batch_count == 2
    assert software.supporting_ids == ["C001", "C002", "C003", "C004", "C005"]
    assert software.representative_ids == ["C001", "C002", "C003"]
    assert stable_hash(table.model_dump(mode="json")) == stable_hash(
        _table().model_dump(mode="json")
    )


def test_consolidation_receives_only_compact_domain_table() -> None:
    prompt = build_top_level_consolidation_prompt(_table())

    assert "Compact Candidate Table" in prompt
    assert "topic_hints" not in prompt
    assert "local-candidates" not in prompt
    assert "完整局部响应秘密" not in prompt
    assert "support_count" in prompt
    assert "batch_count" in prompt


def test_top_level_draft_forbids_children_and_mixed_facets() -> None:
    payload = _draft().model_dump(mode="json")
    payload["domains"][0]["children"] = []
    with pytest.raises(ValidationError):
        TopLevelDomainDraft.model_validate(payload)

    payload = _draft().model_dump(mode="json")
    payload["content_types"] = []
    with pytest.raises(ValidationError):
        TopLevelDomainDraft.model_validate(payload)


def test_rules_detect_entity_leak_and_localize_sibling_review() -> None:
    table = _table()
    draft = _draft(overlap=True, entity_name="ToolX")
    rules = evaluate_top_level_rules(
        draft=draft,
        candidate_table=table,
        allowed_ids={f"C{index:03d}" for index in range(1, 8)},
        known_entity_names={"ToolX"},
    )

    assert "entity_leakage" in {item.code for item in rules.blocking_issues}
    assert len(rules.validation_units) == 1
    rows = {
        "C001": ["C001", "A", "相关卡片", "结论", [], []],
        "C002": ["C002", "A", "相关卡片二", "结论", [], []],
        "C004": ["C004", "A", "相关卡片四", "结论", [], []],
        "C999": ["C999", "A", "不应泄漏的完整历史", "秘密", [], []],
    }
    prompt = build_local_validation_prompt(
        unit=rules.validation_units[0], draft=draft, rows_by_id=rows
    )
    assert "d_01" in prompt and "d_02" in prompt
    assert "不应泄漏的完整历史" not in prompt
    assert "Local Discovery 历史" in prompt


def test_clean_structure_does_not_schedule_llm_validation() -> None:
    rules = evaluate_top_level_rules(
        draft=_draft(overlap=False),
        candidate_table=_table(),
        allowed_ids={f"C{index:03d}" for index in range(1, 8)},
        known_entity_names=set(),
    )
    assert rules.validation_units == []


def test_new_consolidation_prompt_is_materially_smaller_than_legacy_payload() -> None:
    long_text = "长定义和边界说明" * 30
    legacy_candidates = [
        {
            "content_types": [],
            "domains": [
                {
                    "provisional_id": f"ld_{batch}",
                    "name": "软件工程",
                    "definition": long_text,
                    "supporting_ids": [f"C{index:03d}" for index in range(1, 9)],
                    "includes": [long_text],
                    "excludes": [long_text],
                    "suggested_level": "primary",
                    "parent_hint": None,
                    "stability_reason": long_text,
                }
            ],
            "topics": [{"name": "阶段主题", "definition": long_text, "supporting_ids": ["C001"]}],
            "entities": [{"name": "ToolX", "definition": long_text, "supporting_ids": ["C001"], "entity_type": "tool"}],
            "ambiguous_ids": [],
        }
        for batch in range(3)
    ]
    legacy = build_consolidation_prompt(legacy_candidates)
    compact = build_top_level_consolidation_prompt(_table())

    assert len(compact) < len(legacy) * 0.45


def test_thinking_route_reserves_high_for_global_consolidation(monkeypatch) -> None:
    captured: list[dict] = []

    class Provider:
        def __init__(self, **kwargs) -> None:
            captured.append(kwargs)

    config = SimpleNamespace(
        api_key_ref="service:account",
        llm_base_url="https://example.invalid/v1",
        model_for=lambda role: "model-x",
    )
    app = Application.__new__(Application)
    app.config = config
    monkeypatch.setattr("shiliu.app.load_api_key", lambda reference: "secret")
    monkeypatch.setattr("shiliu.app.OpenAICompatibleProvider", Provider)

    app.provider("taxonomy_local")
    app.provider("taxonomy_validator")
    app.provider("taxonomy_global")
    app.provider("taxonomy_repair")

    assert [(item["thinking_enabled"], item["reasoning_effort"]) for item in captured] == [
        (False, None),
        (False, None),
        (True, "high"),
        (False, None),
    ]


def test_unfinished_old_engine_run_cannot_resume(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    now = utc_now()
    with db.connect() as connection:
        snapshot_cursor = connection.execute(
            """
            INSERT INTO taxonomy_corpus_snapshots(
                selected_source_ids_json, membership_count, content_count,
                duplicate_memberships_merged, discovery_eligible_count,
                trial_assignment_only_count, evidence_counts_json,
                snapshot_hash, created_at, frozen_at
            ) VALUES('[]', 1, 1, 0, 1, 0, '{"A":1,"B":0,"C":0,"D":0}', ?, ?, ?)
            """,
            ("b" * 64, now, now),
        )
        run_cursor = connection.execute(
            """
            INSERT INTO taxonomy_runs(
                corpus_snapshot_id, run_kind, engine, engine_version,
                parameters_json, status, created_at, updated_at
            ) VALUES(?, 'regression', 'batched_llm_native', 'old-engine', '{}',
                     'pending', ?, ?)
            """,
            (int(snapshot_cursor.lastrowid), now, now),
        )
    workflow = TaxonomyWorkflow(
        snapshot_repository=SimpleNamespace(get_snapshot=lambda snapshot_id: None),
        run_repository=TaxonomyRunRepository(db),
        provider_factory=lambda role: None,
        output_dir=app_paths.content_dir / "taxonomy" / "runtime" / "runs",
    )

    with pytest.raises(PipelineError) as error:
        workflow.execute(int(run_cursor.lastrowid), resume=True)
    assert error.value.code == "taxonomy_engine_version_mismatch"


def test_checkpoint35_run_creation_rejects_assignment() -> None:
    workflow = TaxonomyWorkflow.__new__(TaxonomyWorkflow)
    with pytest.raises(ValueError, match="尚未开放一级 Trial Assignment"):
        workflow.create_run(snapshot_id=1, include_assignment=True)
