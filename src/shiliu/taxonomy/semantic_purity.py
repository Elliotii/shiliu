from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from shiliu.domain import PipelineError
from shiliu.taxonomy.candidates import (
    CompactContentTypeTable,
    ContentTypeDraftV2,
    TopLevelDomainDraft,
)
from shiliu.taxonomy.quality import QualityIssue, TopLevelQualityResult


CONTENT_TYPE_PURITY_JUDGE_PROMPT_VERSION = "content-type-semantic-purity-judge-v1"
CONTENT_TYPE_PURITY_JUDGE_SCHEMA_VERSION = "content-type-purity-judge-schema-v1"
CHECKPOINT39_QUALITY_GATE_VERSION = "content-type-semantic-quality-gate-v1"
OUTPUT_BUDGET_PREFLIGHT_VERSION = "taxonomy-output-budget-preflight-v1"


class ContentTypePurityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(pattern=r"^ct_[a-z0-9_]+$")
    purity_result: Literal[
        "pure_content_type",
        "domain_leakage",
        "entity_leakage",
        "topic_leakage",
        "mixed",
        "unsupported",
    ]
    topic_substitution_test: Literal["passes", "fails", "partial"]
    cross_domain_reusability: Literal["high", "medium", "low"]
    evidence: list[str] = Field(min_length=1, max_length=3)
    recommended_action: Literal[
        "keep",
        "rename",
        "split",
        "remove_as_domain",
        "remove_as_entity",
        "remove_as_topic",
        "remove_as_unsupported",
        "needs_review",
    ]
    confidence: Literal["high", "medium", "low"]


class ContentTypePurityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[ContentTypePurityFinding] = Field(min_length=1, max_length=16)
    summary: str = Field(min_length=1, max_length=300)


class OutputBudgetPreflight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = OUTPUT_BUDGET_PREFLIGHT_VERSION
    stage_name: str
    complexity_count: int = Field(ge=0)
    schema_hint_characters: int = Field(ge=0)
    historical_completion_tokens: int | None = Field(default=None, ge=0)
    estimated_completion_tokens: int = Field(gt=0)
    safety_margin_ratio: float = Field(gt=0)
    required_with_margin_tokens: int = Field(gt=0)
    allocated_max_tokens: int = Field(gt=0)
    technical_max_tokens: int = Field(gt=0)
    safety_margin_tokens: int
    safe_to_call: bool
    rationale: str


class Checkpoint39QualityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    semantic_purity_passed: bool
    blocking_issues: list[QualityIssue]
    warnings: list[QualityIssue]
    metrics: dict[str, Any]
    recommended_next_stage: Literal["run_b", "targeted_content_type_retry"]


PURITY_JUDGE_SCHEMA_HINT = (
    '{"findings":[{"node_id":"ct_01",'
    '"purity_result":"pure_content_type|domain_leakage|entity_leakage|topic_leakage|mixed|unsupported",'
    '"topic_substitution_test":"passes|fails|partial",'
    '"cross_domain_reusability":"high|medium|low","evidence":[""],'
    '"recommended_action":"keep|rename|split|remove_as_domain|remove_as_entity|'
    'remove_as_topic|remove_as_unsupported|needs_review",'
    '"confidence":"high|medium|low"}],"summary":""}'
)


def build_purity_judge_prompt(
    *,
    draft: ContentTypeDraftV2,
    table: CompactContentTypeTable,
    domain_draft: TopLevelDomainDraft,
    compact_rows_by_id: dict[str, list[Any]],
) -> str:
    candidates_by_id = {item.candidate_id: item for item in table.content_types}
    payload_nodes: list[dict[str, Any]] = []
    for node in draft.content_types:
        decisions = [
            decision
            for decision in draft.candidate_decisions
            if decision.target_node_id == node.id
        ]
        source_candidates = [
            candidates_by_id[decision.candidate_id].model_dump(mode="json")
            for decision in decisions
            if decision.candidate_id in candidates_by_id
        ]
        payload_nodes.append(
            {
                "node": node.model_dump(mode="json"),
                "source_candidates": source_candidates,
                "candidate_decisions": [
                    decision.model_dump(mode="json") for decision in decisions
                ],
                "representative_compact_form_views": [
                    compact_rows_by_id[short_id]
                    for short_id in node.representative_ids
                    if short_id in compact_rows_by_id
                ][:3],
            }
        )
    domains = [
        {"name": node.name, "definition": node.definition}
        for node in domain_draft.domains
    ] + [
        {"name": child.name, "definition": child.definition}
        for node in domain_draft.domains
        for child in node.children
    ]
    payload = {"content_type_nodes": payload_nodes, "domain_boundaries": domains}
    return f"""你是独立 Content Type Semantic Purity Judge，只评估最终节点，不修改 Draft。
逐节点执行 Topic Substitution Test：把主题替换成数据库、烹饪、摄影或游戏开发后，节点是否仍描述表达、组织或使用形式。结合 name、definition、includes/excludes、来源候选、Candidate Decision、最多 3 个代表 Compact Form View 以及 Domain 名称/定义判断。

你必须区分：Domain=内容讲什么知识领域；Content Type=内容以什么表达、组织或使用形式呈现；Topic=具体或短期主题；Entity=具体项目、模型、工具、人物、公司或论文。
Domain 输入只用于识别维度重叠，不得据此创建或修改分类。不得读取或要求完整字幕、完整总结、Silver Reference 或人工分类。
每个输入 node_id 必须且只能输出一个 finding。pure_content_type 才能 keep/rename；domain/entity/topic 泄漏必须给对应 remove；mixed 必须 split 或 needs_review；unsupported 必须 remove_as_unsupported。只输出 JSON。

精简输出结构：{PURITY_JUDGE_SCHEMA_HINT}
输入：{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"""


def validate_purity_report(
    report: ContentTypePurityReport,
    *,
    expected_node_ids: set[str],
) -> None:
    node_ids = [item.node_id for item in report.findings]
    if len(node_ids) != len(set(node_ids)) or set(node_ids) != expected_node_ids:
        raise PipelineError(
            "Purity Judge 未完整且唯一覆盖最终 Content Type",
            code="content_type_purity_coverage_mismatch",
            retryable=False,
        )
    invalid: list[str] = []
    expected_actions = {
        "domain_leakage": {"remove_as_domain"},
        "entity_leakage": {"remove_as_entity"},
        "topic_leakage": {"remove_as_topic"},
        "mixed": {"split", "needs_review"},
        "unsupported": {"remove_as_unsupported"},
        "pure_content_type": {"keep", "rename"},
    }
    for finding in report.findings:
        if finding.recommended_action not in expected_actions[finding.purity_result]:
            invalid.append(finding.node_id)
        if (
            finding.purity_result == "pure_content_type"
            and finding.topic_substitution_test != "passes"
        ):
            invalid.append(finding.node_id)
    if invalid:
        raise PipelineError(
            "Purity Judge 结论与建议动作或 Topic Substitution Test 不一致",
            code="content_type_purity_action_mismatch",
            retryable=False,
        )


def build_budget_preflight(
    *,
    stage_name: str,
    complexity_count: int,
    schema_hint_characters: int,
    historical_completion_tokens: int | None,
    technical_max_tokens: int,
    safety_margin_ratio: float,
    base_tokens: int,
    tokens_per_item: int,
    historical_growth_factor: float = 1.0,
) -> OutputBudgetPreflight:
    structural_estimate = base_tokens + complexity_count * tokens_per_item
    historical_estimate = math.ceil(
        (historical_completion_tokens or 0) * historical_growth_factor
    )
    estimated = max(structural_estimate, historical_estimate)
    required = math.ceil(estimated * (1 + safety_margin_ratio))
    allocated = min(technical_max_tokens, math.ceil(required / 1024) * 1024)
    margin = allocated - estimated
    safe = allocated >= required
    return OutputBudgetPreflight(
        stage_name=stage_name,
        complexity_count=complexity_count,
        schema_hint_characters=schema_hint_characters,
        historical_completion_tokens=historical_completion_tokens,
        estimated_completion_tokens=estimated,
        safety_margin_ratio=safety_margin_ratio,
        required_with_margin_tokens=required,
        allocated_max_tokens=allocated,
        technical_max_tokens=technical_max_tokens,
        safety_margin_tokens=margin,
        safe_to_call=safe,
        rationale=(
            "候选/节点复杂度估计与历史完成量取较大值，再加安全余量并按 1024 向上取整"
        ),
    )


def require_safe_budget(preflight: OutputBudgetPreflight) -> None:
    if not preflight.safe_to_call:
        raise PipelineError(
            f"{preflight.stage_name} 技术上限不能提供冻结的安全余量",
            code="taxonomy_output_budget_preflight_failed",
            retryable=False,
        )


def combine_checkpoint39_quality(
    *,
    structural: TopLevelQualityResult,
    draft: ContentTypeDraftV2,
    table: CompactContentTypeTable,
    purity: ContentTypePurityReport,
    silent_normalization_event_count: int,
) -> Checkpoint39QualityResult:
    blocking = list(structural.blocking_issues)
    warnings = list(structural.warnings)
    candidate_ids = {item.candidate_id for item in table.content_types}
    decision_ids = {item.candidate_id for item in draft.candidate_decisions}
    coverage = len(decision_ids & candidate_ids) / len(candidate_ids) if candidate_ids else 0
    if coverage != 1.0:
        blocking.append(
            QualityIssue(
                code="candidate_typing_incomplete",
                message="Candidate Typing 没有 100% 覆盖 Normalize 候选。",
            )
        )
    unresolved_candidates = [
        item.candidate_id
        for item in draft.candidate_decisions
        if item.recommended_action == "needs_review"
    ]
    if unresolved_candidates:
        blocking.append(
            QualityIssue(
                code="candidate_typing_needs_review",
                message="存在未解决的 mixed 或低确定度候选。",
                node_ids=unresolved_candidates,
            )
        )
    non_pure = [
        item for item in purity.findings if item.purity_result != "pure_content_type"
    ]
    for result, code in (
        ("domain_leakage", "semantic_domain_leakage"),
        ("entity_leakage", "semantic_entity_leakage"),
        ("topic_leakage", "semantic_topic_leakage"),
        ("mixed", "semantic_mixed_node"),
        ("unsupported", "semantic_unsupported_node"),
    ):
        node_ids = [item.node_id for item in non_pure if item.purity_result == result]
        if node_ids:
            blocking.append(
                QualityIssue(
                    code=code,
                    message="Purity Judge 发现非纯 Content Type 节点。",
                    node_ids=node_ids,
                )
            )
    if silent_normalization_event_count:
        blocking.append(
            QualityIssue(
                code="silent_normalization_detected",
                message="模型输出发生了未允许的静默字段修改。",
            )
        )
    judge_by_id = {item.node_id: item for item in purity.findings}
    disagreements = [
        node.id
        for node in draft.content_types
        if judge_by_id.get(node.id) is None
        or judge_by_id[node.id].purity_result != "pure_content_type"
    ]
    kind_counts = Counter(item.candidate_kind for item in draft.candidate_decisions)
    action_counts = Counter(item.recommended_action for item in draft.candidate_decisions)
    purity_counts = Counter(item.purity_result for item in purity.findings)
    semantic_pass = not non_pure and not unresolved_candidates and coverage == 1.0
    passed = not blocking and semantic_pass and silent_normalization_event_count == 0
    return Checkpoint39QualityResult(
        passed=passed,
        semantic_purity_passed=semantic_pass,
        blocking_issues=blocking,
        warnings=warnings,
        recommended_next_stage="run_b" if passed else "targeted_content_type_retry",
        metrics={
            **structural.metrics,
            "semantic_purity_passed": semantic_pass,
            "domain_leakage_count": purity_counts["domain_leakage"],
            "entity_leakage_count": purity_counts["entity_leakage"],
            "topic_leakage_count": purity_counts["topic_leakage"],
            "mixed_node_count": purity_counts["mixed"],
            "unsupported_node_count": purity_counts["unsupported"],
            "candidate_typing_coverage": coverage,
            "candidate_kind_distribution": dict(kind_counts),
            "candidate_rejection_distribution": {
                key: value for key, value in action_counts.items() if key.startswith("remove_")
            },
            "purity_judge_disagreements": disagreements,
            "silent_normalization_event_count": silent_normalization_event_count,
        },
    )
