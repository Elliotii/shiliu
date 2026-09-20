from __future__ import annotations

import pytest

from shiliu.domain import PipelineError
from shiliu.taxonomy.domain_completion_review import (
    apply_m3_alignment_revision_01,
    build_m3_coverage_audit,
    build_m3_independent_review_bundle,
    build_m3_semantic_risk_components,
    cluster_pair_features,
    validate_m3_independent_semantic_review,
)


def _cluster(
    cluster_id: str,
    name: str,
    candidate_ref: str,
    component_id: str,
    *,
    definition: str | None = None,
    evidence: list[str] | None = None,
) -> dict:
    evidence = evidence or [f"C{int(cluster_id[-3:]):03d}"]
    return {
        "cluster_id": cluster_id,
        "local_source_component_id": component_id,
        "source_run_nodes": [],
        "source_candidates": [candidate_ref],
        "definitions": [{
            "candidate_ref": candidate_ref,
            "definition": definition or f"{name}的长期知识与实践问题空间。",
        }],
        "parent_positions": [],
        "evidence_pools": evidence,
        "representative_ids": evidence[:1],
        "protocol_provenance": [candidate_ref.split(":", 1)[0]],
        "known_protocol_risks": [],
        "alignment_relation": "unrelated",
        "domain_disposition": "domain_candidate",
        "recommended_status": "probable",
        "canonical_scope_proposal": {
            "name": name,
            "definition": definition or f"{name}的长期知识与实践问题空间。",
            "includes": [f"{name}实践"],
            "excludes": [f"单一{name}产品"],
            "parent_scope_hint": None,
        },
        "confidence": "medium",
        "decision_reason": "来自冻结 Candidate 的 provisional 对齐结果，等待独立语义复核。",
    }


def _fixtures():
    clusters = [
        _cluster("xc_001", "AI Agent架构", "A:nc_001", "sc_001", evidence=["C001"]),
        _cluster("xc_002", "检索增强生成 RAG", "B:nc_002", "sc_002", evidence=["C002"]),
        _cluster("xc_003", "RAG系统", "C1:nc_003", "sc_003", evidence=["C002"]),
        _cluster("xc_004", "AI辅助软件开发", "A:nc_004", "sc_004"),
        _cluster("xc_005", "求职面试准备", "B:nc_005", "sc_005"),
        _cluster("xc_006", "AI编程工具配置", "C1:nc_006", "sc_006"),
        _cluster("xc_007", "开源项目学习方法", "A:nc_007", "sc_007"),
    ]
    clusters_artifact = {
        "version": "cross-run-domain-clusters-v1",
        "clusters": clusters,
    }
    components = []
    for cluster in clusters:
        candidate_ref = cluster["source_candidates"][0]
        source, candidate_id = candidate_ref.split(":", 1)
        content_id = cluster["representative_ids"][0]
        components.append({
            "source_component_id": cluster["local_source_component_id"],
            "candidates": [{
                "ref": candidate_ref,
                "source_run": source,
                "candidate_id": candidate_id,
                "name": cluster["canonical_scope_proposal"]["name"],
                "definition": cluster["canonical_scope_proposal"]["definition"],
                "supporting_ids": cluster["evidence_pools"],
            }],
            "representative_profiles": [{
                "content_id": content_id,
                "main_subject": cluster["canonical_scope_proposal"]["name"],
                "content_goal": "解释相关长期问题空间",
                "key_concepts": ["概念"],
                "entities": [],
                "evidence_level": "A",
            }],
            "protocol_risks": {source: ["synthetic protocol risk"]},
        })
    return clusters_artifact, {"components": components}


def test_cluster_pair_features_find_cross_component_rag_duplicate():
    clusters_artifact, _ = _fixtures()
    left, right = clusters_artifact["clusters"][1:3]

    features = cluster_pair_features(left, right)

    assert features["normalized_name_similarity"] > 0
    assert features["evidence_pool_overlap"] == 1.0
    assert features["shared_source_components"] == []
    assert features["parent_scope_similarity"] == 0.0
    assert features["risk_score"] >= 2.0


def test_m3_risk_scan_is_global_and_covers_required_families():
    clusters_artifact, _ = _fixtures()

    risks = build_m3_semantic_risk_components(clusters_artifact)

    assert risks["global_pair_scan_count"] == 21
    assert risks["risk_detection_is_semantic_decision"] is False
    assert all(item["covered"] for item in risks["required_review_groups"])
    rag_pair = next(
        item for item in risks["risk_pairs"]
        if {item["left_cluster_id"], item["right_cluster_id"]} == {"xc_002", "xc_003"}
    )
    assert "near_duplicate_scope" in rag_pair["risk_flags"]
    assert "domain_use_context_leakage" in risks["cluster_risk_flags"]["xc_005"]
    assert "domain_object_leakage" in risks["cluster_risk_flags"]["xc_006"]


def test_m3_coverage_and_review_bundle_are_bounded_and_traceable():
    clusters_artifact, alignment_bundle = _fixtures()
    risks = build_m3_semantic_risk_components(clusters_artifact)
    coverage = build_m3_coverage_audit(alignment_bundle, clusters_artifact)
    assert coverage == {
        "expected_candidates": 7,
        "actual_candidates": 7,
        "missing": [],
        "extra": [],
        "duplicate": [],
        "source_provenance": {"A": 3, "B": 2, "C1": 2},
        "passed": True,
    }
    unresolved = {
        "decisions": [{
            "adjudication_id": "ua_001",
            "adjudication": "candidate_is_topic",
            "recommended_operation": "downgrade_to_topic",
            "closest_existing_nodes": [],
            "confidence": "high",
            "reviewer_verdict": "accept",
            "sources": [{
                "source_run": "B", "candidate_id": "nc_005",
                "candidate_name": "求职面试准备",
            }],
        }],
    }

    bundle = build_m3_independent_review_bundle(
        semantic_contract={"version": "domain-semantic-contract-v2"},
        unresolved_final=unresolved,
        alignment_bundle=alignment_bundle,
        clusters_artifact=clusters_artifact,
        decisions_artifact={"decisions": []},
        engineering_gate={"status": "READY_FOR_INDEPENDENT_REVIEW"},
        risk_artifact=risks,
        recovery_records_by_component={
            "sc_001": {"result_hash": "abc", "provider_call_count": 0},
        },
    )

    assert bundle["m3_coverage_audit"]["passed"] is True
    assert len(bundle["clusters"]) == 7
    assert bundle["clusters"][0]["local_recovery_record"]["provider_call_count"] == 0
    assert len(bundle["clusters"][0]["representative_profiles"]) <= 5
    assert bundle["reviewer_role"] == "independent_read_only_semantic_counterexample_reviewer"
    assert bundle["review_contract"]["may_read_silver"] is False
    assert "complete 131-card corpus" in bundle["forbidden_inputs"]


def _valid_review(bundle: dict) -> dict:
    return {
        "verdict": "PASS_WITH_CONCERNS",
        "blocking_findings": [],
        "non_blocking_concerns": ["边界留待 Assignment 验证"],
        "component_reviews": [{
            "risk_component_id": component["risk_component_id"],
            "verdicts": ["keep_separate"],
            "cluster_ids": component["cluster_ids"],
            "reason": "合成复核记录",
            "evidence": [],
        } for component in bundle["m3_semantic_risk_components"]["risk_components"]],
        "cluster_reviews": [{
            "cluster_id": cluster["cluster_id"],
            "verdict": "keep_as_domain_candidate",
            "reason": "合成复核记录",
            "evidence": [],
        } for cluster in bundle["clusters"]],
        "required_revisions": [],
        "evidence": ["synthetic fixture"],
    }


def test_m3_semantic_review_requires_full_cluster_and_component_coverage():
    clusters_artifact, alignment_bundle = _fixtures()
    risks = build_m3_semantic_risk_components(clusters_artifact)
    bundle = build_m3_independent_review_bundle(
        semantic_contract={"version": "domain-semantic-contract-v2"},
        unresolved_final={"decisions": []},
        alignment_bundle=alignment_bundle,
        clusters_artifact=clusters_artifact,
        decisions_artifact={"decisions": []},
        engineering_gate={"status": "READY_FOR_INDEPENDENT_REVIEW"},
        risk_artifact=risks,
        recovery_records_by_component={},
    )
    review = _valid_review(bundle)

    normalized = validate_m3_independent_semantic_review(review, bundle)

    assert normalized["reviewed_cluster_count"] == 7
    assert normalized["reviewed_component_count"] == risks["risk_component_count"]
    assert normalized["freeze_eligible"] is True
    assert normalized["provider_call_count"] == 0

    review["cluster_reviews"].pop()
    with pytest.raises(PipelineError) as error:
        validate_m3_independent_semantic_review(review, bundle)
    assert error.value.code == "m3_semantic_review_cluster_coverage_invalid"


def test_m3_semantic_review_rejects_fail_without_blocking_findings():
    clusters_artifact, alignment_bundle = _fixtures()
    risks = build_m3_semantic_risk_components(clusters_artifact)
    bundle = build_m3_independent_review_bundle(
        semantic_contract={"version": "domain-semantic-contract-v2"},
        unresolved_final={"decisions": []},
        alignment_bundle=alignment_bundle,
        clusters_artifact=clusters_artifact,
        decisions_artifact={"decisions": []},
        engineering_gate={"status": "READY_FOR_INDEPENDENT_REVIEW"},
        risk_artifact=risks,
        recovery_records_by_component={},
    )
    review = _valid_review(bundle)
    review["verdict"] = "FAIL"

    with pytest.raises(PipelineError) as error:
        validate_m3_independent_semantic_review(review, bundle)
    assert error.value.code == "m3_semantic_review_blocking_mismatch"


def test_m3_revision_is_reviewer_bounded_and_preserves_candidate_coverage():
    affected_ids = [
        "xc_001", "xc_002", "xc_003", "xc_005", "xc_006", "xc_007",
        "xc_012", "xc_013", "xc_015", "xc_017", "xc_018", "xc_019",
        "xc_021", "xc_023", "xc_024", "xc_027", "xc_029", "xc_030",
        "xc_040", "xc_041", "xc_043", "xc_044", "xc_045", "xc_046",
        "xc_048", "xc_049", "xc_052", "xc_053", "xc_054", "xc_056",
    ]
    clusters = [
        _cluster(cluster_id, f"范围 {cluster_id}", f"A:nc_{index:03d}", f"sc_{index:03d}")
        for index, cluster_id in enumerate(affected_ids, start=1)
    ]
    clusters.append(_cluster("xc_060", "未受影响范围", "B:nc_060", "sc_060"))
    for cluster in clusters:
        if cluster["cluster_id"] in {"xc_046", "xc_056"}:
            cluster["domain_disposition"] = "non_domain_topic"
            cluster["recommended_status"] = "not_applicable"
    artifact = {"version": "test", "clusters": clusters}
    decisions = {"version": "test", "decisions": []}
    review = {
        "verdict": "FAIL",
        "blocking_findings": [{"finding_id": "BF-01"}],
        "required_revisions": [{
            "affected_cluster_ids": affected_ids,
            "affected_candidate_ids": [],
            "current_scope": "synthetic",
            "problem": "synthetic",
            "recommended_operation": "bounded_revision",
            "reason": "synthetic",
            "evidence": [],
        }],
    }

    revised, revised_decisions, revision = apply_m3_alignment_revision_01(
        clusters_artifact=artifact, decisions_artifact=decisions, review=review,
    )

    revised_by_id = {item["cluster_id"]: item for item in revised["clusters"]}
    assert revision["candidate_coverage"]["passed"] is True
    assert revision["provider_call_count"] == 0
    assert revision["m2_semantic_parallel_repromotion_resolved"] is True
    assert revised_by_id["xc_019"]["domain_disposition"] == "non_domain_topic"
    assert revised_by_id["xc_007"]["domain_disposition"] == "non_domain_use_context"
    assert revised_by_id["xc_013"]["domain_disposition"] == "non_domain_object"
    assert revised_by_id["xc_012"]["domain_disposition"] == "uncertain"
    assert revised_by_id["xc_060"] == clusters[-1]
    assert len(revised_decisions["decisions"]) == len(revised["clusters"])
