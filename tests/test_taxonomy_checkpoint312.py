from __future__ import annotations

import json

import pytest

from shiliu.domain import PipelineError
from shiliu.taxonomy.controlled_facets_completion import (
    ModelFacetAssignment,
    normalize_model_assignment,
)
from shiliu.taxonomy.domain_stability import (
    AlignmentOutput,
    HierarchyValidationOutput,
    build_alignment_candidates,
    build_draft_a,
    build_draft_a_gate,
    build_risk_units,
    merge_aligned_nodes,
    validate_alignment,
    validate_hierarchy_output,
)
from shiliu.taxonomy.model_calls import _write_repair_semantic_diff


def source_node(
    run: str,
    node_id: str,
    name: str,
    support: list[str],
    *,
    parent_id: str | None = None,
):
    return {
        "run_node_id": f"{run}:{node_id}",
        "run": run,
        "name": name,
        "definition": f"{name}的长期稳定知识领域",
        "includes": [name],
        "excludes": ["具体工具"],
        "parent_id": f"{run}:{parent_id}" if parent_id else None,
        "supporting_ids": support,
        "representative_ids": support[:2],
    }


def model_assignment(objects: list[dict]) -> ModelFacetAssignment:
    return ModelFacetAssignment.model_validate(
        {
            "content_id": "C001",
            "presentation_form": {
                "primary": "PF01",
                "secondary": None,
                "confidence": "high",
                "evidence": ["呈现形式"],
            },
            "object_types": objects,
            "suggested_use_contexts": [],
            "facet_novelty": [],
            "ambiguities": [],
        }
    )


def object_item(object_id: str, confidence: str, entity: str) -> dict:
    return {
        "id": object_id,
        "source_entities": [entity],
        "mapping_source": "model_assisted",
        "confidence": confidence,
        "evidence": [f"{entity}证据"],
    }


def test_repair_semantic_diff_marks_budget_selection(tmp_path) -> None:
    _write_repair_semantic_diff(
        call_dir=tmp_path,
        original_raw='{"content_id":"C001","object_types":[1,2,3]}',
        repaired_value={"content_id": "C001", "object_types": [1, 2]},
        validation_error="List should have at most 2 items max_length",
        stage_id="assignment-v1",
        attempt_id="1",
    )
    payload = json.loads((tmp_path / "repair-semantic-diff.json").read_text())
    assert payload["semantic_change_count"] == 1
    assert payload["events"][0]["change_type"] == "semantic_selection"
    assert payload["events"][0]["content_id"] == "C001"


def test_repair_semantic_diff_marks_invalid_json_as_syntax_only(tmp_path) -> None:
    _write_repair_semantic_diff(
        call_dir=tmp_path,
        original_raw="not-json",
        repaired_value={"value": 1},
        validation_error="invalid json",
        stage_id="local-v1",
        attempt_id="1",
    )
    payload = json.loads((tmp_path / "repair-semantic-diff.json").read_text())
    assert payload["syntax_only_count"] == 1
    assert payload["events"][0]["field_path"] == "$"


def test_object_overflow_preserves_unselected_candidates() -> None:
    normalized, events = normalize_model_assignment(
        model_assignment(
            [
                object_item("OT01", "low", "A"),
                object_item("OT02", "high", "B"),
                object_item("OT03", "medium", "C"),
            ]
        ),
        allowed_entities={"A", "B", "C"},
        central_object_type_ids={"OT03"},
        timestamp="fixed",
    )
    assert [item.id for item in normalized.object_types] == ["OT03", "OT02"]
    overflow = next(item for item in events if item["operation"] == "object-overflow-selection-v1")
    assert overflow["overflow_object_type_candidates"][0]["object_type_id"] == "OT01"
    assert overflow["overflow_object_type_candidates"][0]["not_selected_reason"]


def test_object_budget_does_not_silently_truncate_in_output_order() -> None:
    normalized, _ = normalize_model_assignment(
        model_assignment(
            [
                object_item("OT01", "low", "A"),
                object_item("OT02", "low", "B"),
                object_item("OT03", "high", "C"),
            ]
        ),
        allowed_entities={"A", "B", "C"},
        timestamp="fixed",
    )
    assert "OT03" in {item.id for item in normalized.object_types}


def test_alignment_candidates_use_support_not_only_names() -> None:
    nodes = [
        source_node("A", "d_1", "智能体工程", ["C001", "C002"]),
        source_node("B", "d_9", "自主系统开发", ["C001", "C002"]),
    ]
    pairs = build_alignment_candidates(nodes)
    assert len(pairs) == 1
    assert pairs[0]["signals"]["support_jaccard"] == 1.0


def test_alignment_validation_requires_every_pair() -> None:
    pairs = build_alignment_candidates(
        [
            source_node("A", "d_1", "Agent 工程", ["C001"]),
            source_node("B", "d_2", "Agent 系统", ["C001"]),
        ]
    )
    with pytest.raises(PipelineError) as error:
        validate_alignment(AlignmentOutput(decisions=[]), pairs)
    assert error.value.code == "alignment_decision_coverage_mismatch"


def alignment_output(pairs: list[dict], relation: str = "equivalent") -> AlignmentOutput:
    return AlignmentOutput.model_validate(
        {
            "version": "cross-run-domain-alignment-v1",
            "decisions": [
                {
                    "pair_id": item["pair_id"],
                    "run_node_ids": [item["left"]["run_node_id"], item["right"]["run_node_id"]],
                    "relation": relation,
                    "reason": "定义与证据对应",
                    "support_overlap": item["signals"]["support_jaccard"],
                    "definition_comparison": "定义相近",
                    "parent_comparison": "父级一致",
                    "confidence": "high",
                }
                for item in pairs
            ],
        }
    )


def test_three_run_equivalence_becomes_stable() -> None:
    nodes = [
        source_node("A", "d_1", "Agent 工程", ["C001", "C002"]),
        source_node("B", "d_2", "智能体工程", ["C001", "C002"]),
        source_node("C", "d_3", "Agent 系统", ["C001", "C002"]),
    ]
    pairs = build_alignment_candidates(nodes)
    groups, metrics = merge_aligned_nodes(nodes, alignment_output(pairs))
    assert len(groups) == 1
    assert groups[0]["stability"] == "stable"
    assert metrics["stable_count"] == 1


def test_weak_node_is_not_silently_deleted() -> None:
    nodes = [source_node("A", "d_1", "独立领域", ["C001"])]
    groups, _ = merge_aligned_nodes(nodes, AlignmentOutput(decisions=[]))
    risks, _ = build_risk_units(groups)
    validation = HierarchyValidationOutput.model_validate(
        {
            "version": "risk-unit-hierarchy-validator-v1",
            "findings": [
                {
                    "unit_id": risks[0]["unit_id"],
                    "affected_node_ids": risks[0]["group_ids"],
                    "operation": "mark_uncertain",
                    "reason": "仅一轮发现",
                    "evidence": ["单轮支持"],
                    "confidence": "high",
                    "blocking": False,
                }
            ],
        }
    )
    draft, uncertain = build_draft_a(groups, validation)
    assert len(draft.nodes) == 1
    assert draft.nodes[0].stability == "uncertain"
    assert uncertain


def test_validator_cannot_touch_nodes_outside_risk_unit() -> None:
    risks = [{"unit_id": "risk_001", "group_ids": ["group_001"]}]
    output = HierarchyValidationOutput.model_validate(
        {
            "version": "risk-unit-hierarchy-validator-v1",
            "findings": [
                {
                    "unit_id": "risk_001",
                    "affected_node_ids": ["group_999"],
                    "operation": "keep",
                    "reason": "越界",
                    "evidence": ["无"],
                    "confidence": "low",
                    "blocking": False,
                }
            ],
        }
    )
    with pytest.raises(PipelineError) as error:
        validate_hierarchy_output(output, risks)
    assert error.value.code == "hierarchy_validator_scope_violation"


def test_draft_gate_rejects_unsourced_node() -> None:
    draft = {
        "version": "domain-draft-a-v1",
        "nodes": [
            {
                "draft_node_id": "draft_001",
                "canonical_name": "领域",
                "definition": "定义",
                "includes": ["内容"],
                "excludes": ["工具"],
                "parent_id": None,
                "stability": "stable",
                "source_run_nodes": [],
                "source_runs": [],
                "supporting_ids": ["C001"],
                "representative_ids": ["C001"],
                "validator_findings": [],
                "draft_decision": "invalid",
                "decision_reason": "测试",
            }
        ],
    }
    from shiliu.taxonomy.domain_stability import DomainDraftA

    gate = build_draft_a_gate(
        draft=DomainDraftA.model_validate(draft),
        groups=[],
        alignment=AlignmentOutput(decisions=[]),
        validation=HierarchyValidationOutput(findings=[]),
        deterministic_findings=[],
    )
    assert not gate.passed
    assert any(item["code"] == "draft_source_missing" for item in gate.blocking_issues)
