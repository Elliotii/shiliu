from __future__ import annotations

import pytest

from shiliu.domain import PipelineError
from shiliu.taxonomy.domain_draft_a import (
    DomainDraftA,
    build_domain_draft_a_budget_preflight,
    build_domain_draft_a_prompt,
    evaluate_domain_draft_a,
    freeze_domain_draft_a,
    record_domain_draft_a_hierarchy_review,
    validate_domain_draft_a,
)


def _cluster(cluster_id: str, *, disposition: str = "domain_candidate") -> dict:
    evidence = [f"C{cluster_id[-3:]}"]
    if cluster_id == "xc_001":
        evidence.append("C101")
    return {
        "cluster_id": cluster_id,
        "domain_disposition": disposition,
        "recommended_status": "probable" if disposition == "domain_candidate" else "not_applicable",
        "source_candidates": [f"A:nc_{cluster_id[-3:]}"],
        "protocol_provenance": ["A"],
        "evidence_pools": evidence,
        "representative_ids": [f"C{cluster_id[-3:]}"],
        "canonical_scope_proposal": {
            "name": f"领域 {cluster_id}",
            "definition": f"领域 {cluster_id} 的长期问题空间。",
            "includes": ["长期实践"],
            "excludes": ["短期话题"],
            "parent_scope_hint": None,
        },
    }


def _draft() -> DomainDraftA:
    return DomainDraftA.model_validate({
        "version": "domain-draft-a-v2",
        "synthesis_reason": "把两个冻结 Cluster 综合为一棵两级产品树。",
        "excluded_cluster_ids": [],
        "nodes": [
            {
                "draft_node_id": "draft_001",
                "name": "人工智能工程",
                "definition": "人工智能系统的长期工程问题空间。",
                "canonical_includes": ["系统设计"],
                "canonical_excludes": ["短期产品动态"],
                "parent_id": None,
                "status": "probable",
                "source_cluster_ids": ["xc_001"],
                "source_candidate_ids": ["A:nc_001"],
                "source_runs": ["A"],
                "evidence_pool_ids": ["C001", "C101"],
                "representative_ids": ["C001"],
                "decision_reason": "长期工程轴。",
                "known_risks": [],
            },
            {
                "draft_node_id": "draft_002",
                "name": "智能体工程",
                "definition": "人工智能工程中的智能体系统细分。",
                "canonical_includes": ["智能体架构"],
                "canonical_excludes": ["单一工具"],
                "parent_id": "draft_001",
                "status": "weak",
                "source_cluster_ids": ["xc_002"],
                "source_candidate_ids": ["A:nc_002"],
                "source_runs": ["A"],
                "evidence_pool_ids": ["C002"],
                "representative_ids": ["C002"],
                "decision_reason": "父级的语义子集。",
                "known_risks": ["single_evidence"],
            },
        ],
    })


def test_domain_draft_a_prompt_only_uses_frozen_cluster_views():
    clusters = {"clusters": [_cluster("xc_001"), _cluster("xc_002")]}
    prompt = build_domain_draft_a_prompt(
        semantic_contract={"version": "v2"}, m2_final={"decisions": []},
        final_clusters=clusters, final_decisions={"decisions": []},
    )

    assert "禁止 stable" in prompt
    assert "eligible_frozen_m3_clusters" in prompt
    assert "完整 131" not in prompt
    assert "Silver" not in prompt

    preflight = build_domain_draft_a_budget_preflight(
        prompt=prompt, eligible_cluster_count=2, max_tokens=4096,
    )
    assert preflight["recommended_strategy"] == "single_high_thinking_synthesis"


def test_domain_draft_a_provenance_and_complexity_gate_pass():
    clusters = {"clusters": [_cluster("xc_001"), _cluster("xc_002")]}
    draft = _draft()

    validate_domain_draft_a(draft, final_clusters=clusters)
    result = evaluate_domain_draft_a(draft)

    assert result["passed"] is True
    assert result["metrics"]["top_level_node_count"] == 1
    assert result["metrics"]["second_level_node_count"] == 1
    assert result["metrics"]["single_evidence_node_count"] == 1


def test_domain_draft_a_rejects_non_domain_cluster_and_single_evidence_probable():
    clusters = {
        "clusters": [
            _cluster("xc_001", disposition="non_domain_topic"),
            _cluster("xc_002"),
        ]
    }
    draft = _draft()
    with pytest.raises(PipelineError) as error:
        validate_domain_draft_a(draft, final_clusters=clusters)
    assert error.value.code == "domain_draft_a_dimension_leakage"

    clusters["clusters"][0]["domain_disposition"] = "domain_candidate"
    draft.nodes[0].evidence_pool_ids = ["C001"]
    with pytest.raises(PipelineError) as error:
        validate_domain_draft_a(draft, final_clusters=clusters)
    assert error.value.code == "domain_draft_a_single_evidence_probable"


def test_domain_draft_a_structure_gate_blocks_duplicate_names_and_boundary_conflict():
    draft = _draft()
    draft.nodes[1].name = "人工 智能工程"
    draft.nodes[0].canonical_excludes = ["智能体架构"]

    result = evaluate_domain_draft_a(draft)

    assert result["passed"] is False
    codes = {item["code"] for item in result["hierarchy_risks"]["blocking"]}
    assert "normalized_duplicate_name" in codes
    assert "parent_excludes_child" in codes


def test_domain_draft_a_allows_parent_child_provenance_aggregation_only():
    clusters = {"clusters": [_cluster("xc_001"), _cluster("xc_002")]}
    draft = _draft()
    draft.nodes[1].source_cluster_ids = ["xc_001", "xc_002"]
    draft.nodes[1].source_candidate_ids = ["A:nc_001", "A:nc_002"]
    draft.nodes[1].evidence_pool_ids = ["C001", "C002"]

    validate_domain_draft_a(draft, final_clusters=clusters)

    sibling = draft.nodes[1].model_copy(deep=True)
    sibling.draft_node_id = "draft_003"
    sibling.name = "另一个兄弟节点"
    sibling.parent_id = "draft_001"
    draft.nodes.append(sibling)
    with pytest.raises(PipelineError) as error:
        validate_domain_draft_a(draft, final_clusters=clusters)
    assert error.value.code == "domain_draft_a_cluster_cross_branch_reused"


def test_domain_draft_a_records_review_and_freezes_without_revision(tmp_path):
    import json

    draft = _draft()
    clusters = {"clusters": [_cluster("xc_001"), _cluster("xc_002")]}
    (tmp_path / "domain-draft-a.provider-draft.json").write_text(
        draft.model_dump_json(), encoding="utf-8",
    )
    (tmp_path / "m3-final-clusters.json").write_text(
        json.dumps(clusters), encoding="utf-8",
    )
    (tmp_path / "domain-draft-a-hierarchy-review-bundle.json").write_text(
        json.dumps({"draft": draft.model_dump(mode="json")}), encoding="utf-8",
    )
    (tmp_path / "domain-draft-a-concurrency-audit.json").write_text(
        json.dumps({
            "known_minimum_usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "reasoning_tokens": 20,
                "elapsed_seconds": 10.0,
            },
            "unknown_usage_response_count": 1,
        }),
        encoding="utf-8",
    )
    review = record_domain_draft_a_hierarchy_review(tmp_path, {
        "verdict": "PASS_WITH_CONCERNS",
        "blocking_findings": [],
        "non_blocking_concerns": ["树较扁平，留待 Trial Assignment 验证。"],
        "required_revisions": [],
        "dimension_leakage_count": 0,
    })

    manifest = freeze_domain_draft_a(tmp_path)

    assert review["freeze_eligible"] is True
    assert manifest["hierarchy_revision"] == "not_required"
    assert manifest["trial_assignment_started"] is False
    assert manifest["provider_usage_unknown_response_count"] == 1
    assert (tmp_path / "domain-draft-a.json").is_file()
    assert (tmp_path / "domain-draft-a-tree.md").is_file()
    assert json.loads(
        (tmp_path / "domain-draft-a-hierarchy-revision.json").read_text()
    )["status"] == "not_required"
