from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from shiliu.cli import build_parser
from shiliu.db import Database, utc_now
from shiliu.llm import CompletionResponse
from shiliu.taxonomy.candidates import (
    CONTENT_TYPE_PURITY_CONSOLIDATION_SCHEMA_HINT,
    CompactContentTypeCandidate,
    CompactContentTypeTable,
    ContentTypeCandidateDecisionV2,
    ContentTypeDraftV2,
    ContentTypeNodeV1,
    TopLevelDomainNode,
    build_content_type_purity_consolidation_prompt,
    build_content_type_purity_local_prompt,
    validate_content_type_draft_v2,
)
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from shiliu.taxonomy.semantic_purity import (
    ContentTypePurityReport,
    build_budget_preflight,
    build_purity_judge_prompt,
    combine_checkpoint39_quality,
    require_safe_budget,
    validate_purity_report,
)
from shiliu.taxonomy.workflow import TaxonomyWorkflow
from tests.test_taxonomy_checkpoint2 import SnapshotRepository, WorkflowProvider, card


def _table() -> CompactContentTypeTable:
    return CompactContentTypeTable(
        source_batch_count=1,
        content_types=[
            CompactContentTypeCandidate(
                candidate_id="nct_001",
                name="操作教程",
                definition="用步骤演示完成任务",
                includes=["步骤"],
                excludes=["纯评论"],
                support_count=2,
                batch_count=1,
                supporting_ids=["C001", "C002"],
                representative_ids=["C001"],
            ),
            CompactContentTypeCandidate(
                candidate_id="nct_002",
                name="数据库索引原理",
                definition="解释数据库索引的知识机制",
                includes=["索引原理"],
                excludes=["操作教程"],
                support_count=1,
                batch_count=1,
                supporting_ids=["C003"],
                representative_ids=["C003"],
            ),
        ],
    )


def _draft() -> ContentTypeDraftV2:
    return ContentTypeDraftV2(
        content_types=[
            ContentTypeNodeV1(
                id="ct_tutorial",
                name="操作教程",
                definition="以可跟随步骤演示如何完成任务",
                includes=["步骤演示"],
                excludes=["纯观点"],
                supporting_ids=["C001", "C002"],
                representative_ids=["C001"],
                node_type="content_type",
            )
        ],
        candidate_decisions=[
            ContentTypeCandidateDecisionV2(
                candidate_id="nct_001",
                candidate_kind="content_type",
                reason="更换主题后仍是一种表达形式",
                supporting_evidence=["步骤演示"],
                topic_substitution_result="passes",
                recommended_action="keep",
                target_node_id="ct_tutorial",
                salvaged_content_type=None,
                confidence="high",
            ),
            ContentTypeCandidateDecisionV2(
                candidate_id="nct_002",
                candidate_kind="domain",
                reason="描述知识主题而不是表达形式",
                supporting_evidence=["索引原理"],
                topic_substitution_result="fails",
                recommended_action="remove_as_domain",
                target_node_id=None,
                salvaged_content_type=None,
                confidence="high",
            ),
        ],
        consolidation_notes=[],
    )


def _purity() -> ContentTypePurityReport:
    return ContentTypePurityReport.model_validate(
        {
            "findings": [
                {
                    "node_id": "ct_tutorial",
                    "purity_result": "pure_content_type",
                    "topic_substitution_test": "passes",
                    "cross_domain_reusability": "high",
                    "evidence": ["数据库、烹饪和摄影均可采用操作教程"],
                    "recommended_action": "keep",
                    "confidence": "high",
                }
            ],
            "summary": "节点描述形式且可跨领域复用",
        }
    )


def test_candidate_typing_routes_real_rejection_paths_and_covers_all() -> None:
    draft = _draft()
    validate_content_type_draft_v2(
        draft,
        allowed_ids={"C001", "C002", "C003"},
        candidate_ids={"nct_001", "nct_002"},
    )
    assert {item.candidate_kind for item in draft.candidate_decisions} == {
        "content_type", "domain"
    }
    assert draft.candidate_decisions[1].recommended_action == "remove_as_domain"

    payload = draft.candidate_decisions[1].model_dump(mode="json")
    payload["recommended_action"] = "merge_into"
    payload["target_node_id"] = "ct_tutorial"
    with pytest.raises(ValidationError):
        ContentTypeCandidateDecisionV2.model_validate(payload)


@pytest.mark.parametrize(
    ("candidate_kind", "recommended_action"),
    [
        ("domain", "remove_as_domain"),
        ("topic", "remove_as_topic"),
        ("entity", "remove_as_entity"),
        ("unsupported", "remove_as_unsupported"),
    ],
)
def test_candidate_typing_supports_every_rejection_route(
    candidate_kind: str,
    recommended_action: str,
) -> None:
    decision = ContentTypeCandidateDecisionV2.model_validate(
        {
            "candidate_id": "nct_001",
            "candidate_kind": candidate_kind,
            "reason": "反事实替换后不构成跨主题内容形式",
            "supporting_evidence": ["候选定义与形式维度不一致"],
            "topic_substitution_result": "fails",
            "recommended_action": recommended_action,
            "target_node_id": None,
            "salvaged_content_type": None,
            "confidence": "high",
        }
    )
    assert decision.recommended_action == recommended_action


def test_mixed_candidate_must_be_salvaged_or_left_for_review() -> None:
    salvaged = ContentTypeCandidateDecisionV2.model_validate(
        {
            "candidate_id": "nct_001",
            "candidate_kind": "mixed",
            "reason": "候选同时包含主题和可复用形式",
            "supporting_evidence": ["形式成分可以独立表达"],
            "topic_substitution_result": "partial",
            "recommended_action": "salvage_content_type",
            "target_node_id": "ct_tutorial",
            "salvaged_content_type": "操作教程",
            "confidence": "medium",
        }
    )
    assert salvaged.salvaged_content_type == "操作教程"

    invalid = salvaged.model_dump(mode="json")
    invalid["recommended_action"] = "merge_into"
    invalid["salvaged_content_type"] = None
    with pytest.raises(ValidationError):
        ContentTypeCandidateDecisionV2.model_validate(invalid)


def test_purity_prompt_uses_generic_counterfactual_not_run_a_answer_names() -> None:
    prompt = build_content_type_purity_consolidation_prompt(_table())
    assert "Topic Substitution Test" in prompt
    assert "数据库索引原理" in prompt
    assert "PostgreSQL" in prompt
    assert "Agent 架构与原理" not in prompt
    assert "AI 学习路径与职业规划" not in prompt
    assert "不得因为有 supporting IDs 就强制并入" in prompt


def test_second_layer_local_prompt_treats_cross_topic_as_necessary_not_sufficient() -> None:
    prompt = build_content_type_purity_local_prompt(
        [["C001", "A", "标题", "结论", ["观点"], ["Entity"]]]
    )
    assert "跨主题成立只是必要条件，不是充分条件" in prompt
    assert "内容如何表达、组织或呈现" in prompt
    assert "数据库自动化" in prompt
    assert "通常输出 3～6 个候选" in prompt
    assert "8 个只是技术绝对上限，不是目标数量" in prompt


def test_purity_judge_is_separate_and_requires_every_final_node() -> None:
    domain = type("DomainDraft", (), {})
    from shiliu.taxonomy.candidates import TopLevelDomainDraft

    domain_draft = TopLevelDomainDraft(
        domains=[
            TopLevelDomainNode(
                id="d_db",
                name="数据库系统",
                definition="数据库设计与实现知识",
                includes=["索引"],
                excludes=["烹饪"],
                supporting_ids=["C003"],
                representative_ids=["C003"],
                children=[],
            )
        ],
        candidate_decisions=[],
        consolidation_notes=[],
    )
    prompt = build_purity_judge_prompt(
        draft=_draft(),
        table=_table(),
        domain_draft=domain_draft,
        compact_rows_by_id={"C001": ["C001", "A", "教程"]},
    )
    assert "只评估最终节点，不修改 Draft" in prompt
    assert "domain_boundaries" in prompt
    validate_purity_report(_purity(), expected_node_ids={"ct_tutorial"})
    with pytest.raises(Exception):
        validate_purity_report(_purity(), expected_node_ids={"ct_tutorial", "ct_other"})


def test_strict_schema_rejects_silent_truncation() -> None:
    payload = _draft().content_types[0].model_dump(mode="json")
    payload["includes"] = [str(index) for index in range(6)]
    with pytest.raises(ValidationError):
        ContentTypeNodeV1.model_validate(payload)

    domain = {
        "id": "d_01",
        "name": "软件工程",
        "definition": "定义",
        "includes": [str(index) for index in range(6)],
        "excludes": ["无"],
        "supporting_ids": ["C001"],
        "representative_ids": ["C001"],
        "children": [],
    }
    with pytest.raises(ValidationError):
        TopLevelDomainNode.model_validate(domain)


def test_budget_preflight_records_margin_and_fails_before_call() -> None:
    safe = build_budget_preflight(
        stage_name="domain",
        complexity_count=42,
        schema_hint_characters=500,
        historical_completion_tokens=19295,
        technical_max_tokens=24576,
        safety_margin_ratio=0.20,
        base_tokens=8192,
        tokens_per_item=256,
    )
    assert safe.allocated_max_tokens == 23552
    assert safe.safety_margin_tokens == 4257
    require_safe_budget(safe)

    unsafe = build_budget_preflight(
        stage_name="domain",
        complexity_count=42,
        schema_hint_characters=500,
        historical_completion_tokens=23000,
        technical_max_tokens=24576,
        safety_margin_ratio=0.20,
        base_tokens=8192,
        tokens_per_item=256,
    )
    assert unsafe.safe_to_call is False
    with pytest.raises(Exception):
        require_safe_budget(unsafe)


def test_cli_exposes_narrow_checkpoint39_run_creation() -> None:
    arguments = build_parser().parse_args(
        ["taxonomy", "create-content-type-purity-run", "--source-run-id", "12"]
    )
    assert arguments.source_run_id == 12
    second = build_parser().parse_args(
        [
            "taxonomy",
            "create-content-type-second-layer-run",
            "--source-run-id",
            "12",
            "--first-layer-run-id",
            "13",
        ]
    )
    assert second.source_run_id == 12
    assert second.first_layer_run_id == 13


class PurityProvider(WorkflowProvider):
    purity_calls = 0

    def complete_raw(self, prompt: str, *, max_tokens: int | None = None):
        if "Content Type Semantic Purification Reduce" in prompt:
            self.content_type_consolidation_calls += 1
            candidate_ids = list(dict.fromkeys(re.findall(r'"(nct_\d{3})"', prompt)))
            ids = list(dict.fromkeys(re.findall(r'"(C\d{3})"', prompt)))
            output = {
                "content_types": [
                    {
                        "id": "ct_tutorial",
                        "name": "操作教程",
                        "definition": "以可跟随步骤演示如何完成任务",
                        "includes": ["步骤演示"],
                        "excludes": ["纯观点"],
                        "supporting_ids": ids[:5],
                        "representative_ids": ids[:3],
                        "node_type": "content_type",
                    }
                ],
                "candidate_decisions": [
                    {
                        "candidate_id": candidate_id,
                        "candidate_kind": "content_type",
                        "reason": "主题替换后仍描述表达形式",
                        "supporting_evidence": ["步骤或讲解"],
                        "topic_substitution_result": "passes",
                        "recommended_action": "merge_into",
                        "target_node_id": "ct_tutorial",
                        "salvaged_content_type": None,
                        "confidence": "high",
                    }
                    for candidate_id in candidate_ids
                ],
                "consolidation_notes": [],
            }
            return CompletionResponse(
                json.dumps(output, ensure_ascii=False),
                "stop",
                {"prompt_tokens": 500, "completion_tokens": 1000},
                "purified-draft",
            )
        if "Content Type Semantic Purity Judge" in prompt:
            self.purity_calls += 1
            node_ids = [
                node_id
                for node_id in dict.fromkeys(
                    re.findall(r'"(ct_[a-z0-9_]+)"', prompt.split("输入：", 1)[1])
                )
            ]
            output = {
                "findings": [
                    {
                        "node_id": node_id,
                        "purity_result": "pure_content_type",
                        "topic_substitution_test": "passes",
                        "cross_domain_reusability": "high",
                        "evidence": ["可跨主题复用"],
                        "recommended_action": "keep",
                        "confidence": "high",
                    }
                    for node_id in node_ids
                ],
                "summary": "全部为纯内容形式",
            }
            return CompletionResponse(
                json.dumps(output, ensure_ascii=False),
                "stop",
                {"prompt_tokens": 300, "completion_tokens": 300},
                "purity-report",
            )
        return super().complete_raw(prompt, max_tokens=max_tokens)


def _insert_snapshot(db: Database) -> int:
    now = utc_now()
    with db.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO taxonomy_corpus_snapshots(
                selected_source_ids_json, membership_count, content_count,
                duplicate_memberships_merged, discovery_eligible_count,
                trial_assignment_only_count, evidence_counts_json,
                snapshot_hash, created_at, frozen_at
            ) VALUES('[]', 128, 128, 0, 128, 0, '{"A":128,"B":0,"C":0,"D":0}', ?, ?, ?)
            """,
            ("a" * 64, now, now),
        )
    return int(cursor.lastrowid)


def test_checkpoint39_derived_run_reuses_source_and_calls_only_two_models(
    app_paths, monkeypatch
) -> None:
    db = Database(app_paths.database)
    db.initialize()
    snapshot_id = _insert_snapshot(db)
    cards = [card(index) for index in range(1, 129)]
    provider = PurityProvider()
    repository = TaxonomyRunRepository(db)
    workflow = TaxonomyWorkflow(
        snapshot_repository=SnapshotRepository(cards),  # type: ignore[arg-type]
        run_repository=repository,
        provider_factory=lambda role: provider,  # type: ignore[arg-type]
        output_dir=app_paths.content_dir / "taxonomy" / "runtime" / "runs",
    )
    selected = [f"C{index:03d}" for index in range(1, 129)]
    source_run_id = workflow.create_run(
        snapshot_id=snapshot_id,
        run_kind="regression",
        seed=101,
        batch_size=24,
        limit=None,
        selected_ids=selected,
    )
    assert workflow.execute(source_run_id)["run"]["status"] == "completed"
    source_dir = workflow.output_dir / f"run-{source_run_id:06d}"
    (source_dir / "run-manifest.json").write_text("{}\n", encoding="utf-8")
    with db.connect() as connection:
        connection.execute(
            "UPDATE taxonomy_runs SET run_kind='full_discovery_run_a' WHERE id=?",
            (source_run_id,),
        )
    monkeypatch.setattr(
        "shiliu.taxonomy.workflow._git_state", lambda: ("checkpoint39-commit", True)
    )
    calls_before = list(provider.calls)
    local_before = provider.local_calls
    content_local_before = provider.content_type_calls
    run_id = workflow.create_content_type_purity_run(source_run_id=source_run_id)
    result = workflow.execute(run_id)

    assert result["run"]["status"] == "completed"
    assert provider.local_calls == local_before
    assert provider.content_type_calls == content_local_before
    assert provider.content_type_consolidation_calls == 2  # source + purified Reduce
    assert provider.purity_calls == 1
    assert provider.calls == calls_before
    stages = result["stages"]
    reused = [item for item in stages if item["attempt_count"] == 0]
    assert len(reused) == 15
    quality = json.loads(
        (
            workflow.output_dir
            / f"run-{run_id:06d}"
            / "checkpoint39-quality-gate"
            / "quality-result.json"
        ).read_text()
    )
    assert quality["passed"] is True
    assert quality["metrics"]["candidate_typing_coverage"] == 1.0
    normalization = json.loads(
        (
            workflow.output_dir
            / f"run-{run_id:06d}"
            / "normalization-audit.json"
        ).read_text()
    )
    assert normalization["silent_normalization_event_count"] == 0
    assert all(
        event["event_type"] == "strict_validation_no_change"
        for event in normalization["events"]
    )
    for stage_name, unit_key in (
        ("content_type_consolidation", "semantic-purity-v1"),
        ("content_type_semantic_purity_judge", "main"),
    ):
        stage = next(
            item
            for item in stages
            if item["stage_name"] == stage_name and item["unit_key"] == unit_key
        )
        persisted = json.loads(Path(stage["output_path"]).read_text(encoding="utf-8"))
        persisted_hash = hashlib.sha256(
            json.dumps(
                persisted,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        assert stage["output_hash"] == persisted_hash

    domain_calls_before = provider.local_calls
    content_calls_before = provider.content_type_calls
    second_run_id = workflow.create_content_type_second_layer_run(
        source_run_id=source_run_id,
        first_layer_run_id=run_id,
    )
    second_result = workflow.execute(second_run_id)

    assert second_result["run"]["status"] == "completed"
    assert provider.local_calls == domain_calls_before
    assert provider.content_type_calls == content_calls_before + 6
    assert provider.content_type_consolidation_calls == 3
    assert provider.purity_calls == 2
    second_protocol = second_result["run"]["parameters"]["protocol_manifest"]
    assert second_protocol["local_content_type_prompt_changed"] is True
    assert second_protocol["second_layer_repair"] is True
    second_reused = [
        item for item in second_result["stages"] if item["attempt_count"] == 0
    ]
    assert len(second_reused) == 8
    assert {item["stage_name"] for item in second_reused} == {
        "local_discovery",
        "candidate_normalization",
        "consolidation",
    }
