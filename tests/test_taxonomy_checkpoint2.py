from __future__ import annotations

import json
import re

import pytest
from pydantic import BaseModel

from shiliu.db import Database, utc_now
from shiliu.domain import PipelineError
from shiliu.llm import CompletionResponse
from shiliu.taxonomy.candidates import (
    ContentTypeDraftV1,
    ContentTypeDiscoveryOutputV1,
    LocalTopLevelDiscoveryOutput,
    TopLevelDomainDraft,
)
from shiliu.taxonomy.discovery import (
    ConsolidatedDraft,
    LocalDiscoveryOutput,
)
from shiliu.taxonomy.model_calls import AuditedJsonCaller
from shiliu.taxonomy.quality import (
    HierarchyValidationReport,
    TaxonomyQualityGate,
    build_hierarchy_validation_prompt,
)
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from shiliu.taxonomy.workflow import TaxonomyWorkflow, _combined_audit


def _candidate(name: str, ids: list[str]) -> dict:
    return {"name": name, "definition": f"{name}定义", "supporting_ids": ids}


def _content_type(name: str, ids: list[str]) -> dict:
    return {
        **_candidate(name, ids),
        "provisional_id": "lct_tutorial",
        "includes": ["教学和操作说明"],
        "excludes": ["纯新闻"],
    }


def _domain_candidate(name: str, ids: list[str], *, level: str) -> dict:
    return {
        **_candidate(name, ids),
        "provisional_id": "ld_primary" if level == "primary" else "ld_child",
        "includes": ["工程知识"],
        "excludes": ["具体工具新闻"],
        "suggested_level": level,
        "parent_hint": None if level == "primary" else "软件工程",
        "stability_reason": "具有长期复用价值且有多条语料支持",
    }


def _draft_node(
    node_id: str,
    name: str,
    ids: list[str],
    *,
    node_type: str,
    parent_id: str | None,
) -> dict:
    return {
        "id": node_id,
        "name": name,
        "definition": f"{name}定义",
        "includes": ["包含内容"],
        "excludes": ["排除内容"],
        "supporting_ids": ids,
        "representative_ids": ids[:1],
        "parent_id": parent_id,
        "node_type": node_type,
    }


def local_output(ids: list[str], *, content_types: bool = True, child: bool = True):
    domains = [_domain_candidate("软件工程", ids[:4], level="primary")]
    if child:
        domains.append(_domain_candidate("测试工程", ids[:2], level="subdomain"))
    return LocalDiscoveryOutput.model_validate(
        {
            "content_types": [_content_type("教程形式", ids[:3])] if content_types else [],
            "domains": domains,
            "topics": [],
            "entities": [
                {**_candidate("ToolX", ids[:1]), "entity_type": "tool"}
            ],
            "ambiguous_ids": [],
        }
    )


def valid_draft(ids: list[str]) -> ConsolidatedDraft:
    parent = {
        **_draft_node("d_01", "软件工程", ids[:4], node_type="domain", parent_id=None),
        "children": [
            _draft_node(
                "d_01_01", "测试工程", ids[:2], node_type="domain", parent_id="d_01"
            )
        ],
    }
    return ConsolidatedDraft.model_validate(
        {
            "content_types": [
                _draft_node("ct_01", "教程形式", ids[:3], node_type="content_type", parent_id=None)
            ],
            "domains": [parent],
            "topics": [],
            "entities": [],
            "consolidation_notes": ["保留有证据的两级结构"],
        }
    )


def clean_hierarchy_report() -> HierarchyValidationReport:
    return HierarchyValidationReport.model_validate(
        {"findings": [], "inspected_node_ids": ["d_01", "d_01_01"], "summary": "通过"}
    )


def test_hierarchy_prompt_requires_every_primary_and_child_id() -> None:
    ids = [f"C{i:03d}" for i in range(1, 6)]
    prompt = build_hierarchy_validation_prompt(valid_draft(ids), [local_output(ids)])

    assert '\"required_inspected_node_ids\":[\"d_01\",\"d_01_01\"]' in prompt
    assert "inspected_node_ids 都必须原样完整回传该数组" in prompt


def test_draft_normalizes_empty_leaf_children_and_unsupported_entities() -> None:
    ids = [f"C{i:03d}" for i in range(1, 6)]
    payload = valid_draft(ids).model_dump(mode="json")
    payload["domains"][0]["children"][0]["children"] = []
    payload["entities"] = [
        {
            "name": "无证据实体",
            "definition": "没有任何支持内容",
            "supporting_ids": [],
            "entity_type": "unknown",
        }
    ]

    value = ConsolidatedDraft.model_validate(payload)

    assert value.entities == []
    assert "children" not in value.model_dump(mode="json")["domains"][0]["children"][0]


def test_quality_feedback_is_reloaded_for_cross_process_retry(tmp_path) -> None:
    workflow = TaxonomyWorkflow.__new__(TaxonomyWorkflow)
    workflow.output_dir = tmp_path
    path = tmp_path / "run-000007" / "quality-gate" / "quality-result.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "passed": False,
                "blocking_issues": [{"code": "node_support"}],
                "retry_stage": "consolidation",
            }
        ),
        encoding="utf-8",
    )

    feedback = workflow._persisted_quality_feedback(7)

    assert feedback is not None
    assert feedback["retry_stage"] == "consolidation"


def test_quality_gate_passes_complete_two_level_taxonomy() -> None:
    ids = {f"C{i:03d}" for i in range(1, 6)}
    result = TaxonomyQualityGate().evaluate(
        draft=valid_draft(sorted(ids)),
        local_outputs=[local_output(sorted(ids))],
        allowed_ids=ids,
        hierarchy_report=clean_hierarchy_report(),
    )
    assert result.passed is True
    assert result.retry_stage is None
    assert result.metrics["content_type_count"] == 1
    assert result.metrics["subdomain_count"] == 1


def test_quality_gate_routes_missing_content_type_to_targeted_recovery() -> None:
    ids = [f"C{i:03d}" for i in range(1, 6)]
    draft = valid_draft(ids).model_copy(update={"content_types": []})
    result = TaxonomyQualityGate().evaluate(
        draft=draft,
        local_outputs=[local_output(ids, content_types=False)],
        allowed_ids=set(ids),
        hierarchy_report=clean_hierarchy_report(),
    )
    assert result.passed is False
    assert result.retry_stage == "content_type_recovery"
    assert "content_types_missing" in {item.code for item in result.blocking_issues}


def test_quality_gate_detects_invalid_support_entity_leak_and_missing_child() -> None:
    ids = [f"C{i:03d}" for i in range(1, 6)]
    local = local_output(ids)
    payload = valid_draft(ids).model_dump(mode="json")
    payload["domains"][0]["name"] = "ToolX"
    payload["domains"][0]["supporting_ids"].append("C999")
    payload["domains"][0]["children"] = []
    draft = ConsolidatedDraft.model_validate(payload)
    result = TaxonomyQualityGate().evaluate(
        draft=draft,
        local_outputs=[local],
        allowed_ids=set(ids),
        hierarchy_report=clean_hierarchy_report(),
    )
    codes = {item.code for item in result.blocking_issues}
    assert {"invalid_supporting_ids", "entity_leakage", "supported_subdomains_missing"} <= codes
    assert result.retry_stage == "consolidation"


class SnapshotRepository:
    def __init__(self, cards: list[dict]) -> None:
        self.cards = cards

    def get_snapshot(self, snapshot_id: int):
        return {
            "id": snapshot_id,
            "snapshot_hash": "a" * 64,
            "cards": self.cards,
        }


def card(index: int, evidence: str = "A") -> dict:
    key = f"bilibili:BV{index:010d}:p1"
    return {
        "content_key": key,
        "evidence_level": evidence,
        "discovery_eligible": evidence != "D",
        "discovery_view": {
            "content_id": key,
            "title": f"标题 {index}",
            "description": f"简介 {index}",
            "one_line_summary": f"结论 {index}",
            "key_points": ["观点一", "观点二"],
            "projects_tools_models": ["ToolX"],
            "evidence_level": evidence,
        },
    }


class WorkflowProvider:
    model = "fake-taxonomy"
    thinking_enabled = False
    reasoning_effort = None

    def __init__(
        self,
        *,
        fail_second_local_once: bool = False,
        fail_second_content_type_once: bool = False,
        bad_first_consolidation: bool = False,
    ) -> None:
        self.fail_second_local_once = fail_second_local_once
        self.fail_second_content_type_once = fail_second_content_type_once
        self.bad_first_consolidation = bad_first_consolidation
        self.local_calls = 0
        self.content_type_calls = 0
        self.content_type_consolidation_calls = 0
        self.consolidation_calls = 0
        self.calls: list[str] = []

    def complete_raw(self, prompt: str, *, max_tokens: int | None = None):
        if "局部知识领域候选发现器" in prompt:
            self.local_calls += 1
            self.calls.append("local")
            if self.fail_second_local_once and self.local_calls == 2:
                raise PipelineError("模拟中断", code="simulated_interrupt", retryable=True)
            ids = _ids_after(prompt, "本批卡片：")
            output = LocalTopLevelDiscoveryOutput.model_validate(
                {
                    "domains": [
                        {
                            "provisional_id": "ld_software",
                            "name": "软件工程",
                            "definition": "软件系统设计、实现与验证的长期知识领域",
                            "supporting_ids": ids[:5],
                            "evidence_codes": ["durable_domain", "multi_item_support"],
                        }
                    ],
                    "topic_hints": [],
                    "ambiguous_ids": [],
                }
            ).model_dump(mode="json")
        elif "独立 Content Type 候选发现器" in prompt:
            self.content_type_calls += 1
            self.calls.append("content_type")
            if self.fail_second_content_type_once and self.content_type_calls == 2:
                raise PipelineError(
                    "模拟 Content Type 中断",
                    code="simulated_content_type_interrupt",
                    retryable=True,
                )
            ids = _ids_after(prompt, "本批卡片：")
            output = ContentTypeDiscoveryOutputV1.model_validate(
                {
                    "content_types": [
                        {
                            "provisional_id": "lct_tutorial",
                            "name": "教程与实操",
                            "definition": "以讲解和操作步骤帮助完成任务",
                            "supporting_ids": ids[:5],
                        }
                    ],
                    "ambiguous_ids": [],
                }
            ).model_dump(mode="json")
        elif "全局 Content Type 归并器" in prompt:
            self.content_type_consolidation_calls += 1
            self.calls.append("content_type_consolidation")
            ids = list(dict.fromkeys(re.findall(r'"(C\d{3})"', prompt)))
            candidate_ids = list(dict.fromkeys(re.findall(r'"(nct_\d{3})"', prompt)))
            output = ContentTypeDraftV1.model_validate(
                {
                    "content_types": [
                        {
                            "id": "ct_01",
                            "name": "教程与实操",
                            "definition": "通过讲解和操作帮助完成任务",
                            "includes": ["步骤讲解"],
                            "excludes": ["纯观点评论"],
                            "supporting_ids": ids[:5],
                            "representative_ids": ids[:3],
                            "node_type": "content_type",
                        }
                    ],
                    "candidate_decisions": [
                        {
                            "candidate_id": candidate_id,
                            "action": "merged_into",
                            "target_id": "ct_01",
                            "reason": "合并同义内容形式候选",
                        }
                        for candidate_id in candidate_ids
                    ],
                    "consolidation_notes": [],
                }
            ).model_dump(mode="json")
        elif "全局一级 Domain 归并器" in prompt:
            self.calls.append("consolidation")
            self.consolidation_calls += 1
            ids = list(dict.fromkeys(re.findall(r'"(C\d{3})"', prompt)))
            candidate_ids = list(dict.fromkeys(re.findall(r'"(nc_\d{3})"', prompt)))
            name = (
                "ToolX"
                if self.bad_first_consolidation and self.consolidation_calls == 1
                else "软件工程"
            )
            draft = TopLevelDomainDraft.model_validate(
                {
                    "domains": [
                        {
                            "id": "d_01",
                            "name": name,
                            "definition": "软件系统设计、实现与验证的长期知识领域",
                            "includes": ["软件设计", "工程验证"],
                            "excludes": ["单一工具新闻"],
                            "supporting_ids": ids[:5],
                            "representative_ids": ids[:3],
                        }
                    ],
                    "candidate_decisions": [
                        {
                            "candidate_id": candidate_id,
                            "action": "merged_into",
                            "target_id": "d_01",
                            "reason": "合并同义领域候选",
                        }
                        for candidate_id in candidate_ids
                    ],
                    "consolidation_notes": ["合并同名候选"],
                }
            )
            output = draft.model_dump(mode="json")
        elif "局部一级 Taxonomy Validator" in prompt:
            raise AssertionError("本测试的单节点 Draft 不应触发局部模型校验")
        elif "JSON Repair" in prompt:
            raise AssertionError("本测试不应触发 Repair")
        else:
            raise AssertionError(prompt[:120])
        return CompletionResponse(
            json.dumps(output, ensure_ascii=False),
            "stop",
            {"prompt_tokens": 100, "completion_tokens": 50},
            f"response-{len(self.calls)}",
        )


def _ids_after(prompt: str, marker: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r'"(C\d{3})"', prompt.split(marker, 1)[1])))


def _insert_snapshot_row(db: Database) -> int:
    now = utc_now()
    with db.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO taxonomy_corpus_snapshots(
                selected_source_ids_json, membership_count, content_count,
                duplicate_memberships_merged, discovery_eligible_count,
                trial_assignment_only_count, evidence_counts_json,
                snapshot_hash, created_at, frozen_at
            ) VALUES('[]', 41, 41, 0, 40, 1, '{"A":40,"B":0,"C":0,"D":1}', ?, ?, ?)
            """,
            ("a" * 64, now, now),
        )
    return int(cursor.lastrowid)


def test_workflow_resume_skips_completed_batch_after_interruption(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    snapshot_id = _insert_snapshot_row(db)
    cards = [card(index) for index in range(1, 41)] + [card(41, "D")]
    provider = WorkflowProvider(fail_second_local_once=True)
    run_repository = TaxonomyRunRepository(db)
    workflow = TaxonomyWorkflow(
        snapshot_repository=SnapshotRepository(cards),  # type: ignore[arg-type]
        run_repository=run_repository,
        provider_factory=lambda role: provider,  # type: ignore[arg-type]
        output_dir=app_paths.content_dir / "taxonomy" / "runtime" / "runs",
    )
    run_id = workflow.create_run(
        snapshot_id=snapshot_id,
        batch_size=20,
        limit=40,
        include_assignment=False,
    )
    with pytest.raises(PipelineError, match="模拟中断"):
        workflow.execute(run_id)
    assert provider.local_calls == 2
    first_status = workflow.status(run_id)
    stages = {
        (item["stage_name"], item["unit_key"]): item
        for item in first_status["stages"]
    }
    assert stages[("local_discovery", "batch-001")]["status"] == "completed"
    assert stages[("local_discovery", "batch-002")]["status"] == "retry_wait"

    result = workflow.execute(run_id, resume=True)
    assert result["run"]["status"] == "completed"
    assert provider.local_calls == 3
    assert provider.content_type_calls == 2
    assert provider.content_type_consolidation_calls == 1
    stages = {
        (item["stage_name"], item["unit_key"]): item for item in result["stages"]
    }
    assert stages[("local_discovery", "batch-001")]["attempt_count"] == 1
    assert stages[("local_discovery", "batch-002")]["attempt_count"] == 2
    assert stages[("consolidation", "main")]["status"] == "completed"
    assert stages[("quality_gate", "main")]["status"] == "completed"


def test_quality_retry_reruns_consolidation_but_not_local_batches(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    snapshot_id = _insert_snapshot_row(db)
    cards = [card(index) for index in range(1, 41)] + [card(41, "D")]
    provider = WorkflowProvider(bad_first_consolidation=True)
    workflow = TaxonomyWorkflow(
        snapshot_repository=SnapshotRepository(cards),  # type: ignore[arg-type]
        run_repository=TaxonomyRunRepository(db),
        provider_factory=lambda role: provider,  # type: ignore[arg-type]
        output_dir=app_paths.content_dir / "taxonomy" / "runtime" / "runs",
    )
    run_id = workflow.create_run(
        snapshot_id=snapshot_id, batch_size=20, limit=40, include_assignment=False
    )
    first = workflow.execute(run_id)
    assert first["run"]["status"] == "quality_failed"
    assert provider.local_calls == 2
    assert provider.content_type_calls == 2
    assert provider.content_type_consolidation_calls == 1
    assert provider.consolidation_calls == 1

    second = workflow.execute(run_id, resume=True)
    assert second["run"]["status"] == "completed"
    assert provider.local_calls == 2
    assert provider.content_type_calls == 2
    assert provider.content_type_consolidation_calls == 1
    assert provider.consolidation_calls == 2
    consolidation = [
        item for item in second["stages"] if item["stage_name"] == "consolidation"
    ][0]
    assert consolidation["attempt_count"] == 2


def test_clean_top_level_workflow_uses_no_content_type_recovery_or_validator(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    snapshot_id = _insert_snapshot_row(db)
    cards = [card(index) for index in range(1, 41)] + [card(41, "D")]
    provider = WorkflowProvider()
    workflow = TaxonomyWorkflow(
        snapshot_repository=SnapshotRepository(cards),  # type: ignore[arg-type]
        run_repository=TaxonomyRunRepository(db),
        provider_factory=lambda role: provider,  # type: ignore[arg-type]
        output_dir=app_paths.content_dir / "taxonomy" / "runtime" / "runs",
    )
    run_id = workflow.create_run(
        snapshot_id=snapshot_id, batch_size=20, limit=40, include_assignment=False
    )
    result = workflow.execute(run_id)
    assert result["run"]["status"] == "completed"
    assert provider.local_calls == 2
    assert provider.content_type_calls == 2
    assert provider.content_type_consolidation_calls == 1
    assert provider.consolidation_calls == 1
    assert provider.calls == [
        "local", "local", "content_type", "content_type",
        "content_type_consolidation", "consolidation",
    ]
    stages = {(item["stage_name"], item["unit_key"]) for item in result["stages"]}
    assert ("candidate_normalization", "main") in stages
    assert ("structural_validation", "main") in stages
    assert not any(name == "local_validation" for name, _ in stages)


class InvalidOnceProvider:
    model = "original"
    thinking_enabled = False
    reasoning_effort = None

    def __init__(self) -> None:
        self.calls = 0

    def complete_raw(self, prompt: str, *, max_tokens: int | None = None):
        self.calls += 1
        return CompletionResponse('{"wrong":1}', "stop", None, "original-1")


class RepairFailsOnceProvider(InvalidOnceProvider):
    model = "repair"

    def complete_raw(self, prompt: str, *, max_tokens: int | None = None):
        self.calls += 1
        if self.calls == 1:
            raise PipelineError("Repair 暂时失败", code="repair_network", retryable=True)
        return CompletionResponse('{"value":"fixed"}', "stop", None, "repair-2")


class TinyOutput(BaseModel):
    value: str


class EmptyThenValidProvider:
    model = "empty-then-valid"
    thinking_enabled = False
    reasoning_effort = None

    def __init__(self) -> None:
        self.calls = 0

    def complete_raw(self, prompt: str, *, max_tokens: int | None = None):
        self.calls += 1
        if self.calls == 1:
            return CompletionResponse(
                "", "stop", {"prompt_tokens": 10, "completion_tokens": 0}, "empty-1"
            )
        return CompletionResponse(
            '{"value":"ok"}',
            "stop",
            {"prompt_tokens": 11, "completion_tokens": 2},
            "valid-2",
        )


def test_failed_primary_requires_new_immutable_attempt(tmp_path) -> None:
    provider = EmptyThenValidProvider()
    caller = AuditedJsonCaller(
        provider=provider,  # type: ignore[arg-type]
        repair_provider=provider,  # type: ignore[arg-type]
    )
    kwargs = {
        "call_dir": tmp_path / "call",
        "prompt": "PROMPT",
        "prompt_version": "v1",
        "schema": TinyOutput,
        "schema_hint": '{"value":"string"}',
        "max_tokens": 100,
        "input_ids": ["C001"],
    }
    with pytest.raises(PipelineError, match="模型返回为空"):
        caller.call(**kwargs)

    with pytest.raises(PipelineError) as resume_error:
        caller.call(**kwargs, resume=True)
    assert resume_error.value.code == "provider_attempt_failed_new_attempt_required"

    second_kwargs = {**kwargs, "call_dir": tmp_path / "attempt-02"}
    result, audit = caller.call(**second_kwargs)

    assert result.value == "ok"
    assert provider.calls == 2
    first_events = [
        json.loads(line)
        for line in (tmp_path / "call" / "provider-response-ledger.jsonl")
        .read_text().splitlines()
    ]
    assert first_events[0]["response_id"] == "empty-1"
    assert first_events[0]["usage"] == {
        "prompt_tokens": 10, "completion_tokens": 0,
    }
    assert audit["usage"] == {"prompt_tokens": 11, "completion_tokens": 2}


def test_combined_audit_preserves_reasoning_and_cached_token_details() -> None:
    combined = _combined_audit(
        {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 80,
                "prompt_tokens_details": {"cached_tokens": 20},
                "completion_tokens_details": {"reasoning_tokens": 60},
            },
            "elapsed_seconds": 3,
            "repair": {
                "usage": {
                    "prompt_tokens": 30,
                    "completion_tokens": 10,
                    "prompt_tokens_details": {"cached_tokens": 5},
                },
                "elapsed_seconds": 2,
            },
        }
    )

    assert combined["usage"]["prompt_tokens"] == 130
    assert combined["usage"]["completion_tokens"] == 90
    assert combined["usage"]["prompt_tokens_details"] == {"cached_tokens": 25}
    assert combined["usage"]["completion_tokens_details"] == {"reasoning_tokens": 60}
    assert combined["elapsed_seconds"] == 5


def test_failed_repair_requires_new_attempt_without_reusing_failed_lease(tmp_path) -> None:
    original = InvalidOnceProvider()
    repair = RepairFailsOnceProvider()
    caller = AuditedJsonCaller(
        provider=original,  # type: ignore[arg-type]
        repair_provider=repair,  # type: ignore[arg-type]
    )
    kwargs = {
        "call_dir": tmp_path / "call",
        "prompt": "ORIGINAL_CORPUS",
        "prompt_version": "v1",
        "schema": TinyOutput,
        "schema_hint": '{"value":"string"}',
        "max_tokens": 100,
        "input_ids": ["C001"],
    }
    with pytest.raises(PipelineError, match="Repair 暂时失败"):
        caller.call(**kwargs)
    with pytest.raises(PipelineError) as resume_error:
        caller.call(**kwargs, resume=True)
    assert resume_error.value.code == "provider_attempt_failed_new_attempt_required"

    result, audit = caller.call(**{**kwargs, "call_dir": tmp_path / "attempt-02"})
    assert result.value == "fixed"
    assert original.calls == 2
    assert repair.calls == 2
    assert audit["status"] == "completed"
    assert audit["repair"]["attempt_count"] == 1


class MustNotCallProvider(InvalidOnceProvider):
    def complete_raw(self, prompt: str, *, max_tokens: int | None = None):
        raise AssertionError("磁盘已有原始响应时不得重新调用模型")


def test_resume_parses_persisted_raw_response_before_new_request(tmp_path) -> None:
    call_dir = tmp_path / "call"
    call_dir.mkdir()
    (call_dir / "prompt.txt").write_text("PROMPT", encoding="utf-8")
    (call_dir / "raw-response.txt").write_text('{"value":"persisted"}', encoding="utf-8")
    (call_dir / "audit.json").write_text(
        json.dumps(
            {
                "status": "raw_received",
                "prompt_version": "v1",
                "prompt_path": "prompt.txt",
                "input_ids": ["C001"],
                "raw_response_path": None,
                "request_attempt_count": 1,
                "repair": None,
            }
        ),
        encoding="utf-8",
    )
    provider = MustNotCallProvider()
    caller = AuditedJsonCaller(
        provider=provider,  # type: ignore[arg-type]
        repair_provider=provider,  # type: ignore[arg-type]
    )
    result, audit = caller.call(
        call_dir=call_dir,
        prompt="PROMPT",
        prompt_version="v1",
        schema=TinyOutput,
        schema_hint='{"value":"string"}',
        max_tokens=100,
        input_ids=["C001"],
        resume=True,
    )
    assert result.value == "persisted"
    assert audit["status"] == "completed"
