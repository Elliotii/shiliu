from __future__ import annotations

import json
import re
from copy import deepcopy
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from shiliu.domain import PipelineError
from shiliu.taxonomy.controlled_facets import _stable_hash, _utc_now, _write_json_once


M3_REVIEW_BUNDLE_VERSION = "m3-independent-semantic-review-bundle-v1"
M3_RISK_COMPONENTS_VERSION = "m3-semantic-risk-components-v1"
M3_SEMANTIC_REVIEW_VERSION = "m3-independent-semantic-review-v1"
M3_ALIGNMENT_REVISION_VERSION = "m3-alignment-revision-01-v1"
M3_REVISION_GATE_VERSION = "m3-revision-gate-v1"
M3_SECOND_REVIEW_BUNDLE_VERSION = "m3-second-semantic-review-bundle-v1"
M3_SECOND_REVIEW_VERSION = "m3-second-semantic-review-v1"
M3_FINAL_MANIFEST_VERSION = "m3-final-manifest-v1"


_M3_CLUSTER_VERDICTS = {
    "keep_as_domain_candidate",
    "downgrade_to_topic",
    "downgrade_to_entity",
    "downgrade_to_object",
    "downgrade_to_use_context",
    "mark_uncertain",
}
_M3_COMPONENT_VERDICTS = {
    "keep_separate",
    "merge_equivalent",
    "merge_scope_overlap",
    "parent_child",
    "granularity_variant",
    "overlapping_but_distinct",
    "split_mixed_cluster",
    "uncertain",
}
_M3_REVISION_FIELDS = {
    "affected_cluster_ids",
    "affected_candidate_ids",
    "current_scope",
    "problem",
    "recommended_operation",
    "reason",
    "evidence",
}


def _normalized(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())


def _character_similarity(left: Any, right: Any) -> float:
    left_chars = set(_normalized(left))
    right_chars = set(_normalized(right))
    if not left_chars and not right_chars:
        return 1.0
    return len(left_chars & right_chars) / max(1, len(left_chars | right_chars))


def _set_overlap(left: list[Any], right: list[Any]) -> float:
    left_set = {_normalized(value) for value in left if _normalized(value)}
    right_set = {_normalized(value) for value in right if _normalized(value)}
    return len(left_set & right_set) / max(1, len(left_set | right_set))


def _scope(cluster: dict[str, Any]) -> dict[str, Any]:
    return dict(cluster.get("canonical_scope_proposal") or {})


def cluster_pair_features(
    left: dict[str, Any], right: dict[str, Any],
) -> dict[str, Any]:
    left_scope, right_scope = _scope(left), _scope(right)
    left_candidates = set(left.get("source_candidates") or [])
    right_candidates = set(right.get("source_candidates") or [])
    left_components = {str(left.get("local_source_component_id") or "")}
    right_components = {str(right.get("local_source_component_id") or "")}
    left_parent = left_scope.get("parent_scope_hint")
    right_parent = right_scope.get("parent_scope_hint")
    parent_similarity = (
        _character_similarity(left_parent, right_parent)
        if _normalized(left_parent) and _normalized(right_parent)
        else 0.0
    )
    features = {
        "normalized_name_similarity": round(
            _character_similarity(left_scope.get("name"), right_scope.get("name")), 6,
        ),
        "definition_similarity": round(
            _character_similarity(
                left_scope.get("definition"), right_scope.get("definition"),
            ), 6,
        ),
        "includes_overlap": round(
            _set_overlap(
                list(left_scope.get("includes") or []),
                list(right_scope.get("includes") or []),
            ), 6,
        ),
        "excludes_overlap": round(
            _set_overlap(
                list(left_scope.get("excludes") or []),
                list(right_scope.get("excludes") or []),
            ), 6,
        ),
        "evidence_pool_overlap": round(
            _set_overlap(
                list(left.get("evidence_pools") or []),
                list(right.get("evidence_pools") or []),
            ), 6,
        ),
        "representative_overlap": round(
            _set_overlap(
                list(left.get("representative_ids") or []),
                list(right.get("representative_ids") or []),
            ), 6,
        ),
        "parent_scope_similarity": round(
            parent_similarity, 6,
        ),
        "shared_source_candidates": sorted(left_candidates & right_candidates),
        "shared_source_components": sorted(
            value for value in left_components & right_components if value
        ),
    }
    score = (
        2.5 * features["normalized_name_similarity"]
        + 1.5 * features["definition_similarity"]
        + features["includes_overlap"]
        + 0.5 * features["excludes_overlap"]
        + 1.5 * features["evidence_pool_overlap"]
        + features["representative_overlap"]
        + 0.5 * features["parent_scope_similarity"]
        + 3.0 * bool(features["shared_source_candidates"])
    )
    features["risk_score"] = round(score, 6)
    return features


def _cluster_risk_flags(cluster: dict[str, Any]) -> list[str]:
    if cluster.get("domain_disposition") not in {"domain_candidate", "uncertain"}:
        return []
    scope = _scope(cluster)
    text = " ".join([
        str(scope.get("name") or ""),
        str(scope.get("definition") or ""),
        " ".join(scope.get("includes") or []),
    ])
    flags: list[str] = []
    if re.search(r"求职|面试|简历|岗位|招聘|职业发展|就业|学习路径", text):
        flags.append("domain_use_context_leakage")
    if re.search(r"工具|配置|终端|插件|IDE|产品|平台", text, re.IGNORECASE):
        flags.append("domain_object_leakage")
    if re.search(r"教程|盘点|解析|动态|短期|版本更新", text):
        flags.append("domain_topic_leakage")
    if re.search(r"项目|模型|论文|公司|人物", text):
        flags.append("domain_entity_leakage")
    if re.search(r"学习方法|学习与复现|方法论|设计哲学|架构对比", text):
        flags.append("granularity_overlap")
    if cluster.get("domain_disposition") == "uncertain" or cluster.get("confidence") == "low":
        flags.append("unclear_scope")
    if cluster.get("alignment_relation") == "protocol_specific":
        flags.append("protocol_specific_scope")
    return sorted(set(flags))


def _pair_risk_flags(
    left: dict[str, Any], right: dict[str, Any], features: dict[str, Any],
) -> list[str]:
    left_name = _normalized(_scope(left).get("name"))
    right_name = _normalized(_scope(right).get("name"))
    flags: list[str] = []
    if (
        left_name == right_name
        or features["normalized_name_similarity"] >= 0.55
        and features["definition_similarity"] >= 0.25
        or features["definition_similarity"] >= 0.55
        and (
            features["includes_overlap"] >= 0.2
            or features["evidence_pool_overlap"] >= 0.5
            or features["representative_overlap"] >= 0.5
        )
    ):
        flags.append("near_duplicate_scope")
    if (
        left_name != right_name
        and (left_name in right_name or right_name in left_name)
        or features["parent_scope_similarity"] >= 0.6
        and features["definition_similarity"] >= 0.25
    ):
        flags.append("possible_parent_child")
    if (
        features["normalized_name_similarity"] >= 0.3
        and (
            features["definition_similarity"] >= 0.3
            or features["includes_overlap"] >= 0.2
            or features["evidence_pool_overlap"] > 0
        )
    ):
        flags.append("granularity_overlap")
    if (
        features["evidence_pool_overlap"] >= 0.5
        and features["definition_similarity"] < 0.25
    ):
        flags.append("mixed_scope")
    if (
        left.get("alignment_relation") == "protocol_specific"
        or right.get("alignment_relation") == "protocol_specific"
    ) and (
        features["normalized_name_similarity"] >= 0.3
        or features["definition_similarity"] >= 0.3
        or features["evidence_pool_overlap"] > 0
        or features["representative_overlap"] > 0
    ):
        flags.append("protocol_specific_scope")
    return sorted(set(flags))


def _required_review_groups(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    patterns = {
        "agent_architecture_engineering_methodology": r"Agent|智能体",
        "rag": r"RAG|检索增强生成",
        "ai_assisted_development": r"AI辅助.*开发|AI编程|开发工作流",
        "job_search_and_interview": r"求职|面试|职业发展",
        "tools_configuration_and_learning_methodology": r"工具|配置|学习方法|学习与复现",
    }
    groups = []
    for family, pattern in patterns.items():
        cluster_ids = [
            cluster["cluster_id"]
            for cluster in clusters
            if re.search(pattern, str(_scope(cluster).get("name") or ""), re.IGNORECASE)
        ]
        groups.append({
            "risk_family": family,
            "cluster_ids": sorted(cluster_ids),
            "covered": bool(cluster_ids),
        })
    return groups


def build_m3_semantic_risk_components(
    clusters_artifact: dict[str, Any],
) -> dict[str, Any]:
    clusters = list(clusters_artifact.get("clusters") or [])
    cluster_ids = [str(cluster.get("cluster_id") or "") for cluster in clusters]
    if len(cluster_ids) != len(set(cluster_ids)) or any(not value for value in cluster_ids):
        raise PipelineError(
            "M3 Cluster ID 缺失或重复",
            code="m3_review_cluster_ids_invalid",
            retryable=False,
        )
    cluster_flags = {
        cluster["cluster_id"]: _cluster_risk_flags(cluster) for cluster in clusters
    }
    pair_rows: list[dict[str, Any]] = []
    for left_index, left in enumerate(clusters):
        for right in clusters[left_index + 1:]:
            features = cluster_pair_features(left, right)
            flags = _pair_risk_flags(left, right, features)
            if not flags and features["risk_score"] < 2.0:
                continue
            pair_rows.append({
                "left_cluster_id": left["cluster_id"],
                "right_cluster_id": right["cluster_id"],
                "risk_flags": flags or ["unclear_scope"],
                "features": features,
            })
    pair_rows.sort(
        key=lambda item: (
            -float(item["features"]["risk_score"]),
            item["left_cluster_id"],
            item["right_cluster_id"],
        )
    )

    adjacency: dict[str, set[str]] = defaultdict(set)
    for pair in pair_rows:
        left_id, right_id = pair["left_cluster_id"], pair["right_cluster_id"]
        adjacency[left_id].add(right_id)
        adjacency[right_id].add(left_id)
    risky_ids = set(adjacency)
    risky_ids.update(cluster_id for cluster_id, flags in cluster_flags.items() if flags)
    components: list[list[str]] = []
    remaining = set(risky_ids)
    while remaining:
        seed = min(remaining)
        stack = [seed]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(adjacency.get(current, set()) - component)
        remaining -= component
        components.append(sorted(component))
    components.sort(key=lambda values: (values[0], len(values)))

    required_groups = _required_review_groups(clusters)
    if not all(group["covered"] for group in required_groups):
        missing = [group["risk_family"] for group in required_groups if not group["covered"]]
        raise PipelineError(
            f"M3 必查风险族未覆盖: {missing}",
            code="m3_required_risk_family_missing",
            retryable=False,
        )
    return {
        "version": M3_RISK_COMPONENTS_VERSION,
        "source_clusters_hash": _stable_hash(clusters_artifact),
        "cluster_count": len(clusters),
        "global_pair_scan_count": len(clusters) * (len(clusters) - 1) // 2,
        "risk_pair_count": len(pair_rows),
        "risk_component_count": len(components),
        "cluster_risk_flags": cluster_flags,
        "risk_pairs": pair_rows,
        "risk_components": [
            {
                "risk_component_id": f"m3rc_{index:03d}",
                "cluster_ids": cluster_ids,
                "risk_flags": sorted({
                    flag
                    for cluster_id in cluster_ids
                    for flag in cluster_flags.get(cluster_id, [])
                } | {
                    flag
                    for pair in pair_rows
                    if pair["left_cluster_id"] in cluster_ids
                    and pair["right_cluster_id"] in cluster_ids
                    for flag in pair["risk_flags"]
                }),
            }
            for index, cluster_ids in enumerate(components, start=1)
        ],
        "required_review_groups": required_groups,
        "risk_detection_is_semantic_decision": False,
    }


def build_m3_coverage_audit(
    alignment_bundle: dict[str, Any], clusters_artifact: dict[str, Any],
) -> dict[str, Any]:
    expected = [
        candidate["ref"]
        for component in alignment_bundle.get("components") or []
        for candidate in component.get("candidates") or []
    ]
    actual = [
        candidate_ref
        for cluster in clusters_artifact.get("clusters") or []
        for candidate_ref in cluster.get("source_candidates") or []
    ]
    duplicate_ids = sorted(
        candidate_ref for candidate_ref, count in Counter(actual).items() if count > 1
    )
    return {
        "expected_candidates": len(expected),
        "actual_candidates": len(actual),
        "missing": sorted(set(expected) - set(actual)),
        "extra": sorted(set(actual) - set(expected)),
        "duplicate": duplicate_ids,
        "source_provenance": dict(sorted(Counter(
            candidate_ref.split(":", 1)[0] for candidate_ref in actual
        ).items())),
        "passed": (
            len(expected) == len(actual)
            and not duplicate_ids
            and set(expected) == set(actual)
        ),
    }


def build_m3_independent_review_bundle(
    *,
    semantic_contract: dict[str, Any],
    unresolved_final: dict[str, Any],
    alignment_bundle: dict[str, Any],
    clusters_artifact: dict[str, Any],
    decisions_artifact: dict[str, Any],
    engineering_gate: dict[str, Any],
    risk_artifact: dict[str, Any],
    recovery_records_by_component: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    coverage = build_m3_coverage_audit(alignment_bundle, clusters_artifact)
    if not coverage["passed"]:
        raise PipelineError(
            "M3 Reviewer Bundle Coverage Gate 未通过",
            code="m3_review_coverage_invalid",
            retryable=False,
        )
    components = {
        component["source_component_id"]: component
        for component in alignment_bundle.get("components") or []
    }
    profiles_by_id = {
        profile["content_id"]: profile
        for component in components.values()
        for profile in component.get("representative_profiles") or []
    }
    m2_by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for decision in unresolved_final.get("decisions") or []:
        for source in decision.get("sources") or []:
            ref = f"{source['source_run']}:{source['candidate_id']}"
            m2_by_candidate[ref].append({
                "adjudication_id": decision["adjudication_id"],
                "adjudication": decision["adjudication"],
                "recommended_operation": decision["recommended_operation"],
                "closest_existing_nodes": decision.get("closest_existing_nodes") or [],
                "confidence": decision["confidence"],
                "reviewer_verdict": decision.get("reviewer_verdict"),
            })
    neighbor_ids: dict[str, set[str]] = defaultdict(set)
    for pair in risk_artifact.get("risk_pairs") or []:
        left_id, right_id = pair["left_cluster_id"], pair["right_cluster_id"]
        neighbor_ids[left_id].add(right_id)
        neighbor_ids[right_id].add(left_id)
    risk_flags = risk_artifact.get("cluster_risk_flags") or {}

    review_clusters = []
    for cluster in clusters_artifact.get("clusters") or []:
        scope = _scope(cluster)
        component_id = cluster["local_source_component_id"]
        component = components[component_id]
        representative_ids = list(cluster.get("representative_ids") or [])
        evidence_ids = list(cluster.get("evidence_pools") or [])
        selected_profile_ids = []
        for content_id in [*representative_ids, *evidence_ids]:
            if content_id in profiles_by_id and content_id not in selected_profile_ids:
                selected_profile_ids.append(content_id)
            if len(selected_profile_ids) >= 5:
                break
        source_candidates = list(cluster.get("source_candidates") or [])
        review_clusters.append({
            "cluster_id": cluster["cluster_id"],
            "canonical_name": scope.get("name"),
            "canonical_definition": scope.get("definition"),
            "canonical_includes": list(scope.get("includes") or []),
            "canonical_excludes": list(scope.get("excludes") or []),
            "domain_disposition": cluster.get("domain_disposition"),
            "status": cluster.get("recommended_status"),
            "alignment_relation": cluster.get("alignment_relation"),
            "source_run_nodes": list(cluster.get("source_run_nodes") or []),
            "source_candidate_ids": source_candidates,
            "source_runs": list(cluster.get("protocol_provenance") or []),
            "protocol_provenance": {
                source: component.get("protocol_risks", {}).get(source, [])
                for source in cluster.get("protocol_provenance") or []
            },
            "evidence_pool_ids": evidence_ids,
            "representative_ids": representative_ids,
            "representative_profiles": [
                profiles_by_id[content_id] for content_id in selected_profile_ids
            ],
            "parent_scope_proposal": scope.get("parent_scope_hint"),
            "neighbor_cluster_ids": sorted(neighbor_ids.get(cluster["cluster_id"], set())),
            "local_component_id": component_id,
            "m2_adjudication_constraints": [
                constraint
                for candidate_ref in source_candidates
                for constraint in m2_by_candidate.get(candidate_ref, [])
            ],
            "local_recovery_record": recovery_records_by_component.get(component_id),
            "known_risk_flags": list(risk_flags.get(cluster["cluster_id"]) or []),
            "decision_reason": cluster.get("decision_reason"),
        })
    return {
        "version": M3_REVIEW_BUNDLE_VERSION,
        "reviewer_role": "independent_read_only_semantic_counterexample_reviewer",
        "review_contract": {
            "may_modify_artifacts": False,
            "may_call_provider_for_alignment": False,
            "may_read_silver": False,
            "may_treat_any_run_as_gold": False,
            "may_use_simple_voting": False,
            "engineering_gate_is_semantic_gate": False,
        },
        "domain_semantic_contract_v2": semantic_contract,
        "m2_final_unresolved_adjudication": unresolved_final,
        "m3_engineering_gate": engineering_gate,
        "m3_coverage_audit": coverage,
        "m3_semantic_risk_components": risk_artifact,
        "clusters": review_clusters,
        "input_hashes": {
            "semantic_contract": _stable_hash(semantic_contract),
            "unresolved_final": _stable_hash(unresolved_final),
            "alignment_bundle": _stable_hash(alignment_bundle),
            "clusters": _stable_hash(clusters_artifact),
            "decisions": _stable_hash(decisions_artifact),
            "engineering_gate": _stable_hash(engineering_gate),
            "risks": _stable_hash(risk_artifact),
        },
        "forbidden_inputs": [
            "Silver Reference",
            "other controlled facet results",
            "user-authored target taxonomy",
            "preselected Domain Draft A",
            "complete 131-card corpus",
        ],
    }


def prepare_m3_independent_review_materials(run_dir: Path) -> dict[str, Any]:
    """Build deterministic, immutable M3 review inputs from frozen Run #24 artifacts."""

    source_paths = {
        "semantic_contract": run_dir / "domain-semantic-contract-v2.json",
        "unresolved_final": run_dir / "unresolved-adjudication-final.json",
        "alignment_bundle": run_dir / "m3-cross-run-alignment-bundle.json",
        "clusters": run_dir / "cross-run-domain-clusters.json",
        "decisions": run_dir / "cross-run-alignment-decisions.json",
        "engineering_gate": run_dir / "m3-cross-run-alignment-gate.json",
    }
    missing = [str(path) for path in source_paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"M3 Reviewer source artifacts missing: {missing}")
    payloads = {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in source_paths.items()
    }
    if payloads["engineering_gate"].get("status") != "READY_FOR_INDEPENDENT_REVIEW":
        raise PipelineError(
            "M3 Engineering Gate 未停在独立复核入口",
            code="m3_review_gate_state_invalid",
            retryable=False,
        )

    recovery_records_by_component: dict[str, dict[str, Any]] = {}
    alignment_root = run_dir / "cross_run_alignment"
    for batch_dir in sorted(alignment_root.glob("batch-*")):
        call_dirs = sorted(batch_dir.glob("attempt-*"))
        if not call_dirs:
            continue
        call_dir = call_dirs[-1]
        audit_path = call_dir / "audit.json"
        if not audit_path.is_file():
            continue
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        local_recovery = audit.get("local_recovery")
        if not local_recovery:
            continue
        summary = {
            "batch_id": batch_dir.name,
            "provider_call_count": local_recovery.get("provider_call_count"),
            "source_path": local_recovery.get("source_path"),
            "source_hash": local_recovery.get("source_hash"),
            "result_hash": local_recovery.get("result_hash"),
            "recovery_mode": local_recovery.get("recovery_mode"),
            "transformation_count": len(local_recovery.get("transformations") or []),
            "transformation_kinds": sorted({
                item.get("kind")
                for item in local_recovery.get("transformations") or []
                if item.get("kind")
            }),
        }
        for component_id in audit.get("input_ids") or []:
            recovery_records_by_component[str(component_id)] = summary

    risks = build_m3_semantic_risk_components(payloads["clusters"])
    review_bundle = build_m3_independent_review_bundle(
        semantic_contract=payloads["semantic_contract"],
        unresolved_final=payloads["unresolved_final"],
        alignment_bundle=payloads["alignment_bundle"],
        clusters_artifact=payloads["clusters"],
        decisions_artifact=payloads["decisions"],
        engineering_gate=payloads["engineering_gate"],
        risk_artifact=risks,
        recovery_records_by_component=recovery_records_by_component,
    )
    risk_path = run_dir / "m3-semantic-risk-components.json"
    review_path = run_dir / "m3-independent-review-bundle.json"
    _write_json_once(risk_path, risks)
    _write_json_once(review_path, review_bundle)
    return {
        "risk_path": str(risk_path),
        "risk_hash": _stable_hash(risks),
        "review_bundle_path": str(review_path),
        "review_bundle_hash": _stable_hash(review_bundle),
        "cluster_count": len(review_bundle["clusters"]),
        "risk_pair_count": risks["risk_pair_count"],
        "risk_component_count": risks["risk_component_count"],
        "coverage": review_bundle["m3_coverage_audit"],
    }


def validate_m3_independent_semantic_review(
    review: dict[str, Any], review_bundle: dict[str, Any],
) -> dict[str, Any]:
    """Validate a read-only reviewer result without interpreting its semantics."""

    verdict = review.get("verdict")
    if verdict not in {"PASS", "PASS_WITH_CONCERNS", "FAIL"}:
        raise PipelineError(
            "M3 Independent Reviewer verdict 非法",
            code="m3_semantic_review_verdict_invalid",
            retryable=False,
        )
    required_lists = (
        "blocking_findings", "non_blocking_concerns", "component_reviews",
        "cluster_reviews", "required_revisions",
    )
    if any(not isinstance(review.get(field), list) for field in required_lists):
        raise PipelineError(
            "M3 Independent Reviewer 输出字段不完整",
            code="m3_semantic_review_shape_invalid",
            retryable=False,
        )

    expected_clusters = {
        cluster["cluster_id"]
        for cluster in review_bundle.get("clusters") or []
        if cluster.get("domain_disposition") in {"domain_candidate", "uncertain"}
    }
    all_clusters = {
        cluster["cluster_id"] for cluster in review_bundle.get("clusters") or []
    }
    reviewed_clusters: set[str] = set()
    for row in review["cluster_reviews"]:
        cluster_id = str(row.get("cluster_id") or "")
        if cluster_id in reviewed_clusters or cluster_id not in expected_clusters:
            raise PipelineError(
                f"M3 Cluster review ID 非法或重复: {cluster_id}",
                code="m3_semantic_review_cluster_invalid",
                retryable=False,
            )
        if row.get("verdict") not in _M3_CLUSTER_VERDICTS:
            raise PipelineError(
                f"M3 Cluster verdict 非法: {cluster_id}",
                code="m3_semantic_review_cluster_verdict_invalid",
                retryable=False,
            )
        reviewed_clusters.add(cluster_id)
    if reviewed_clusters != expected_clusters:
        raise PipelineError(
            "M3 Independent Reviewer 未覆盖全部 domain-candidate / uncertain Cluster",
            code="m3_semantic_review_cluster_coverage_invalid",
            retryable=False,
        )

    known_components = {
        component["risk_component_id"]
        for component in (
            review_bundle.get("m3_semantic_risk_components", {})
            .get("risk_components") or []
        )
    }
    reviewed_components: set[str] = set()
    for row in review["component_reviews"]:
        component_id = str(
            row.get("risk_component_id") or row.get("component_id") or ""
        )
        if component_id in reviewed_components or component_id not in known_components:
            raise PipelineError(
                f"M3 Component review ID 非法或重复: {component_id}",
                code="m3_semantic_review_component_invalid",
                retryable=False,
            )
        verdicts = row.get("verdicts", row.get("verdict"))
        if isinstance(verdicts, str):
            verdicts = [verdicts]
        if not isinstance(verdicts, list) or not verdicts or any(
            value not in _M3_COMPONENT_VERDICTS for value in verdicts
        ):
            raise PipelineError(
                f"M3 Component verdict 非法: {component_id}",
                code="m3_semantic_review_component_verdict_invalid",
                retryable=False,
            )
        reviewed_components.add(component_id)
    if reviewed_components != known_components:
        raise PipelineError(
            "M3 Independent Reviewer 未覆盖全部风险 Component",
            code="m3_semantic_review_component_coverage_invalid",
            retryable=False,
        )

    for revision in review["required_revisions"]:
        if not _M3_REVISION_FIELDS.issubset(revision):
            raise PipelineError(
                "M3 Required Revision 缺少审计字段",
                code="m3_semantic_review_revision_shape_invalid",
                retryable=False,
            )
        affected = set(revision.get("affected_cluster_ids") or [])
        if (
            not affected
            or not affected.issubset(all_clusters)
            or not affected.intersection(expected_clusters)
        ):
            raise PipelineError(
                "M3 Required Revision 的 Cluster 范围非法",
                code="m3_semantic_review_revision_scope_invalid",
                retryable=False,
            )

    blocking_count = len(review["blocking_findings"])
    if (verdict == "FAIL") != (blocking_count > 0):
        raise PipelineError(
            "M3 Reviewer verdict 与 Blocking Findings 不一致",
            code="m3_semantic_review_blocking_mismatch",
            retryable=False,
        )
    normalized = dict(review)
    normalized.update({
        "version": M3_SEMANTIC_REVIEW_VERSION,
        "review_bundle_hash": _stable_hash(review_bundle),
        "reviewed_cluster_count": len(reviewed_clusters),
        "reviewed_component_count": len(reviewed_components),
        "blocking_count": blocking_count,
        "freeze_eligible": blocking_count == 0,
        "reviewer_may_modify_artifacts": False,
        "provider_call_count": 0,
    })
    return normalized


def record_m3_independent_semantic_review(
    run_dir: Path, review: dict[str, Any],
) -> dict[str, Any]:
    bundle_path = run_dir / "m3-independent-review-bundle.json"
    if not bundle_path.is_file():
        raise FileNotFoundError(bundle_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    normalized = validate_m3_independent_semantic_review(review, bundle)
    _write_json_once(run_dir / "m3-independent-semantic-review.json", normalized)
    return normalized


def _ordered_union(rows: list[list[Any]], *, limit: int | None = None) -> list[Any]:
    result: list[Any] = []
    for row in rows:
        for value in row:
            if value not in result:
                result.append(value)
            if limit is not None and len(result) >= limit:
                return result
    return result


def _merge_m3_clusters(
    clusters_by_id: dict[str, dict[str, Any]], *, target_id: str,
    member_ids: list[str], canonical_id: str,
    disposition: str | None = None, status: str | None = None,
) -> dict[str, Any]:
    members = [clusters_by_id[cluster_id] for cluster_id in member_ids]
    canonical = clusters_by_id[canonical_id]
    merged = deepcopy(clusters_by_id[target_id])
    merged["source_run_nodes"] = _ordered_union([
        list(item.get("source_run_nodes") or []) for item in members
    ])
    merged["source_candidates"] = _ordered_union([
        list(item.get("source_candidates") or []) for item in members
    ])
    merged["definitions"] = _ordered_union([
        list(item.get("definitions") or []) for item in members
    ])
    merged["parent_positions"] = _ordered_union([
        list(item.get("parent_positions") or []) for item in members
    ])
    merged["evidence_pools"] = _ordered_union([
        list(item.get("evidence_pools") or []) for item in members
    ])
    merged["representative_ids"] = _ordered_union([
        list(item.get("representative_ids") or []) for item in members
    ], limit=8)
    merged["protocol_provenance"] = _ordered_union([
        list(item.get("protocol_provenance") or []) for item in members
    ])
    merged["known_protocol_risks"] = _ordered_union([
        list(item.get("known_protocol_risks") or []) for item in members
    ])
    canonical_scope = deepcopy(canonical.get("canonical_scope_proposal") or {})
    canonical_scope["includes"] = _ordered_union([
        list((item.get("canonical_scope_proposal") or {}).get("includes") or [])
        for item in [canonical, *members]
    ], limit=8)
    canonical_scope["excludes"] = _ordered_union([
        list((item.get("canonical_scope_proposal") or {}).get("excludes") or [])
        for item in [canonical, *members]
    ], limit=8)
    merged["canonical_scope_proposal"] = canonical_scope
    merged["alignment_relation"] = "merge_equivalent"
    if disposition is not None:
        merged["domain_disposition"] = disposition
    if status is not None:
        merged["recommended_status"] = status
    merged["decision_reason"] = (
        "M3 Independent Reviewer Revision 01：合并 "
        + ", ".join(member_ids)
        + f"；canonical scope 继承 {canonical_id}，边界只合并冻结成员已有字段。"
    )
    for cluster_id in member_ids:
        if cluster_id != target_id:
            del clusters_by_id[cluster_id]
    clusters_by_id[target_id] = merged
    return merged


def apply_m3_alignment_revision_01(
    *, clusters_artifact: dict[str, Any], decisions_artifact: dict[str, Any],
    review: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Apply the single reviewer-bounded M3 revision; no Provider is called."""

    if review.get("verdict") != "FAIL" or not review.get("blocking_findings"):
        raise PipelineError(
            "M3 Revision 01 只允许用于首轮 Reviewer Blocking",
            code="m3_revision_not_required",
            retryable=False,
        )
    before_clusters = list(clusters_artifact.get("clusters") or [])
    before_by_id = {item["cluster_id"]: deepcopy(item) for item in before_clusters}
    clusters_by_id = deepcopy(before_by_id)
    reviewer_scope = {
        cluster_id
        for revision in review.get("required_revisions") or []
        for cluster_id in revision.get("affected_cluster_ids") or []
    }
    operations: list[dict[str, Any]] = []

    merge_specs = [
        ("xc_002", ["xc_002", "xc_003", "xc_048", "xc_053", "xc_054"], "xc_053", None, None),
        ("xc_001", ["xc_001", "xc_006"], "xc_006", None, None),
        ("xc_005", ["xc_005", "xc_052"], "xc_005", None, None),
        ("xc_021", ["xc_021", "xc_030"], "xc_030", None, None),
        ("xc_044", ["xc_044", "xc_045"], "xc_044", None, None),
        ("xc_019", ["xc_019", "xc_056"], "xc_056", "non_domain_topic", "not_applicable"),
        ("xc_023", ["xc_023", "xc_046"], "xc_023", "domain_candidate", "weak"),
    ]
    for target_id, member_ids, canonical_id, disposition, status in merge_specs:
        if not set(member_ids).issubset(reviewer_scope):
            raise PipelineError(
                f"M3 Revision 越过 Reviewer 范围: {member_ids}",
                code="m3_revision_scope_violation",
                retryable=False,
            )
        _merge_m3_clusters(
            clusters_by_id, target_id=target_id, member_ids=member_ids,
            canonical_id=canonical_id, disposition=disposition, status=status,
        )
        operations.append({
            "operation": "merge_cluster",
            "target_cluster_id": target_id,
            "member_cluster_ids": member_ids,
            "canonical_source_cluster_id": canonical_id,
        })

    disposition_specs = {
        "xc_007": "non_domain_use_context",
        "xc_018": "non_domain_use_context",
        "xc_049": "non_domain_use_context",
        "xc_027": "non_domain_use_context",
        "xc_013": "non_domain_object",
        "xc_015": "non_domain_object",
        "xc_041": "non_domain_topic",
        "xc_043": "non_domain_topic",
    }
    for cluster_id, disposition in disposition_specs.items():
        if cluster_id not in reviewer_scope:
            raise PipelineError(
                f"M3 Revision 越过 Reviewer 范围: {cluster_id}",
                code="m3_revision_scope_violation",
                retryable=False,
            )
        cluster = clusters_by_id[cluster_id]
        before_disposition = cluster.get("domain_disposition")
        cluster["domain_disposition"] = disposition
        cluster["recommended_status"] = "not_applicable"
        cluster["alignment_relation"] = "granularity_variant"
        cluster["decision_reason"] = (
            f"M3 Independent Reviewer Revision 01：{before_disposition} → {disposition}；"
            "只改变语义 disposition，不改写来源和 Evidence。"
        )
        operations.append({
            "operation": "downgrade_disposition",
            "cluster_id": cluster_id,
            "before": before_disposition,
            "after": disposition,
        })

    for cluster_id in ["xc_012", "xc_024", "xc_029", "xc_040"]:
        if cluster_id not in reviewer_scope:
            raise PipelineError(
                f"M3 Revision 越过 Reviewer 范围: {cluster_id}",
                code="m3_revision_scope_violation",
                retryable=False,
            )
        cluster = clusters_by_id[cluster_id]
        cluster["domain_disposition"] = "uncertain"
        cluster["recommended_status"] = "uncertain"
        cluster["confidence"] = "low"
        cluster["decision_reason"] = (
            "M3 Independent Reviewer Revision 01：canonical scope 与 Evidence 尚未形成"
            "单一稳定轴；不重写边界，标记 uncertain 等待 Assignment 证据。"
        )
        operations.append({"operation": "mark_uncertain", "cluster_id": cluster_id})

    ai_workflow = clusters_by_id["xc_017"]
    ai_workflow["alignment_relation"] = "granularity_variant"
    ai_workflow["canonical_scope_proposal"]["parent_scope_hint"] = "AI辅助软件开发"
    ai_workflow["decision_reason"] = (
        "M3 Independent Reviewer Revision 01：保留为 AI 辅助软件开发的工作流与方法论"
        "细分；不与广义 Cluster 平级解释。"
    )
    operations.append({
        "operation": "change_alignment_relation",
        "cluster_id": "xc_017",
        "relation": "granularity_variant",
        "parent_scope_hint": "AI辅助软件开发",
    })

    revised_clusters = [clusters_by_id[key] for key in sorted(clusters_by_id)]
    actual_candidates = [
        candidate
        for cluster in revised_clusters
        for candidate in cluster.get("source_candidates") or []
    ]
    expected_candidates = [
        candidate
        for cluster in before_clusters
        for candidate in cluster.get("source_candidates") or []
    ]
    if Counter(actual_candidates) != Counter(expected_candidates):
        raise PipelineError(
            "M3 Revision 01 破坏 Candidate Coverage",
            code="m3_revision_candidate_coverage_invalid",
            retryable=False,
        )

    changed_before_ids = {
        cluster_id for cluster_id in before_by_id
        if cluster_id not in clusters_by_id
        or _stable_hash(before_by_id[cluster_id]) != _stable_hash(clusters_by_id[cluster_id])
    }
    if not changed_before_ids.issubset(reviewer_scope):
        raise PipelineError(
            "M3 Revision 01 修改了 Reviewer 未点名的 Cluster",
            code="m3_revision_scope_violation",
            retryable=False,
        )

    revised_cluster_artifact = dict(clusters_artifact)
    revised_cluster_artifact.update({
        "version": "cross-run-domain-clusters-revision-01-v1",
        "cluster_count": len(revised_clusters),
        "clusters": revised_clusters,
        "revision_source_review_hash": _stable_hash(review),
    })
    revised_decisions = dict(decisions_artifact)
    revised_decisions.update({
        "version": "cross-run-alignment-decisions-revision-01-v1",
        "decisions": [{
            "cluster_id": cluster["cluster_id"],
            "source_candidates": list(cluster.get("source_candidates") or []),
            "alignment_relation": cluster.get("alignment_relation"),
            "domain_disposition": cluster.get("domain_disposition"),
            "confidence": cluster.get("confidence"),
            "decision_reason": cluster.get("decision_reason"),
        } for cluster in revised_clusters],
        "revision_source_review_hash": _stable_hash(review),
    })
    before_counts = dict(Counter(
        cluster.get("domain_disposition") for cluster in before_clusters
    ))
    after_counts = dict(Counter(
        cluster.get("domain_disposition") for cluster in revised_clusters
    ))
    revision = {
        "version": M3_ALIGNMENT_REVISION_VERSION,
        "review_hash": _stable_hash(review),
        "before_clusters_hash": _stable_hash(clusters_artifact),
        "before_decisions_hash": _stable_hash(decisions_artifact),
        "after_clusters_hash": _stable_hash(revised_cluster_artifact),
        "after_decisions_hash": _stable_hash(revised_decisions),
        "reviewer_allowed_cluster_ids": sorted(reviewer_scope),
        "changed_original_cluster_ids": sorted(changed_before_ids),
        "operations": operations,
        "before_distribution": before_counts,
        "after_distribution": after_counts,
        "candidate_coverage": {
            "expected": len(expected_candidates),
            "actual": len(actual_candidates),
            "missing": [], "extra": [], "duplicate": [], "passed": True,
        },
        "m2_exact_repromotion": 0,
        "m2_semantic_parallel_repromotion_resolved": (
            clusters_by_id["xc_019"]["domain_disposition"] == "non_domain_topic"
        ),
        "provider_call_count": 0,
    }
    return revised_cluster_artifact, revised_decisions, revision


def execute_m3_alignment_revision_01(run_dir: Path) -> dict[str, Any]:
    paths = {
        "clusters": run_dir / "cross-run-domain-clusters.json",
        "decisions": run_dir / "cross-run-alignment-decisions.json",
        "review": run_dir / "m3-independent-semantic-review.json",
    }
    payloads = {
        key: json.loads(path.read_text(encoding="utf-8"))
        for key, path in paths.items()
    }
    revised_clusters, revised_decisions, revision = apply_m3_alignment_revision_01(
        clusters_artifact=payloads["clusters"],
        decisions_artifact=payloads["decisions"],
        review=payloads["review"],
    )
    _write_json_once(run_dir / "m3-revised-clusters.json", revised_clusters)
    _write_json_once(run_dir / "m3-revised-alignment-decisions.json", revised_decisions)
    _write_json_once(run_dir / "m3-alignment-revision-01.json", revision)
    return revision


def build_m3_revision_gate(
    *, original_clusters: dict[str, Any], revised_clusters: dict[str, Any],
    revision: dict[str, Any],
) -> dict[str, Any]:
    expected = [
        candidate
        for cluster in original_clusters.get("clusters") or []
        for candidate in cluster.get("source_candidates") or []
    ]
    actual = [
        candidate
        for cluster in revised_clusters.get("clusters") or []
        for candidate in cluster.get("source_candidates") or []
    ]
    counts = Counter(actual)
    blocking: list[dict[str, Any]] = []
    if Counter(expected) != counts:
        blocking.append({"code": "candidate_coverage_mismatch"})
    duplicate = sorted(candidate for candidate, count in counts.items() if count > 1)
    if duplicate:
        blocking.append({"code": "candidate_duplicate", "candidate_ids": duplicate})
    stable = [
        cluster["cluster_id"]
        for cluster in revised_clusters.get("clusters") or []
        if cluster.get("recommended_status") == "stable"
    ]
    if stable:
        blocking.append({"code": "stable_before_assignment", "cluster_ids": stable})
    if int(revision.get("m2_exact_repromotion") or 0) != 0:
        blocking.append({"code": "m2_exact_repromotion"})
    if not revision.get("m2_semantic_parallel_repromotion_resolved"):
        blocking.append({"code": "m2_semantic_parallel_repromotion"})
    return {
        "version": M3_REVISION_GATE_VERSION,
        "status": "PASS" if not blocking else "FAIL",
        "blocking": blocking,
        "metrics": {
            "candidate_expected": len(expected),
            "candidate_actual": len(actual),
            "candidate_missing": sorted(set(expected) - set(actual)),
            "candidate_extra": sorted(set(actual) - set(expected)),
            "candidate_duplicate": duplicate,
            "cluster_count": len(revised_clusters.get("clusters") or []),
            "stable_before_assignment": len(stable),
            "m2_exact_repromotion": int(revision.get("m2_exact_repromotion") or 0),
            "m2_semantic_parallel_repromotion_resolved": bool(
                revision.get("m2_semantic_parallel_repromotion_resolved")
            ),
            "provider_call_count": int(revision.get("provider_call_count") or 0),
        },
        "revised_clusters_hash": _stable_hash(revised_clusters),
        "revision_hash": _stable_hash(revision),
    }


def build_m3_second_review_bundle(run_dir: Path) -> dict[str, Any]:
    names = {
        "semantic_contract": "domain-semantic-contract-v2.json",
        "m2_final": "unresolved-adjudication-final.json",
        "original_clusters": "cross-run-domain-clusters.json",
        "revised_clusters": "m3-revised-clusters.json",
        "review": "m3-independent-semantic-review.json",
        "revision": "m3-alignment-revision-01.json",
    }
    payloads = {
        name: json.loads((run_dir / filename).read_text(encoding="utf-8"))
        for name, filename in names.items()
    }
    gate = build_m3_revision_gate(
        original_clusters=payloads["original_clusters"],
        revised_clusters=payloads["revised_clusters"],
        revision=payloads["revision"],
    )
    _write_json_once(run_dir / "m3-revision-gate.json", gate)
    affected_ids = set(payloads["revision"]["changed_original_cluster_ids"])
    affected_ids.update(
        operation.get("target_cluster_id")
        for operation in payloads["revision"]["operations"]
        if operation.get("target_cluster_id")
    )
    before = {
        cluster["cluster_id"]: cluster
        for cluster in payloads["original_clusters"].get("clusters") or []
        if cluster["cluster_id"] in affected_ids
    }
    after = {
        cluster["cluster_id"]: cluster
        for cluster in payloads["revised_clusters"].get("clusters") or []
        if cluster["cluster_id"] in affected_ids
    }
    affected_candidates = {
        candidate
        for revision in payloads["review"].get("required_revisions") or []
        for candidate in revision.get("affected_candidate_ids") or []
    }
    m2_constraints = [
        decision
        for decision in payloads["m2_final"].get("decisions") or []
        if any(
            f"{source.get('source_run')}:{source.get('candidate_id')}"
            in affected_candidates
            for source in decision.get("sources") or []
        )
    ]
    bundle = {
        "version": M3_SECOND_REVIEW_BUNDLE_VERSION,
        "review_scope": "only first-review blocking findings and Revision 01 effects",
        "first_blocking_findings": payloads["review"]["blocking_findings"],
        "first_required_revisions": payloads["review"]["required_revisions"],
        "revision_operations": payloads["revision"]["operations"],
        "affected_clusters_before": before,
        "affected_clusters_after": after,
        "m2_constraints_for_affected_candidates": m2_constraints,
        "domain_semantic_contract_v2": payloads["semantic_contract"],
        "revision_gate": gate,
        "forbidden": [
            "new broad alignment revision", "unaffected cluster changes",
            "Provider alignment call", "Silver", "complete 131-card corpus",
        ],
        "input_hashes": {
            name: _stable_hash(payload) for name, payload in payloads.items()
        },
    }
    _write_json_once(run_dir / "m3-second-review-bundle.json", bundle)
    return bundle


def record_m3_second_semantic_review(
    run_dir: Path, review: dict[str, Any],
) -> dict[str, Any]:
    bundle = json.loads(
        (run_dir / "m3-second-review-bundle.json").read_text(encoding="utf-8")
    )
    if review.get("verdict") not in {"PASS", "PASS_WITH_CONCERNS", "FAIL"}:
        raise PipelineError(
            "M3 Second Reviewer verdict 非法",
            code="m3_second_review_verdict_invalid",
            retryable=False,
        )
    if not isinstance(review.get("blocking_findings"), list):
        raise PipelineError(
            "M3 Second Reviewer blocking_findings 缺失",
            code="m3_second_review_shape_invalid",
            retryable=False,
        )
    expected_findings = {
        item["finding_id"] for item in bundle["first_blocking_findings"]
    }
    resolutions = list(review.get("finding_resolutions") or [])
    actual_findings = {item.get("finding_id") for item in resolutions}
    if actual_findings != expected_findings or any(
        item.get("resolved") is not True for item in resolutions
    ):
        raise PipelineError(
            "M3 Second Reviewer 未逐项解决首轮 Blocking",
            code="m3_second_review_resolution_incomplete",
            retryable=False,
        )
    blocking_count = len(review["blocking_findings"])
    if (review["verdict"] == "FAIL") != (blocking_count > 0):
        raise PipelineError(
            "M3 Second Reviewer verdict 与 Blocking 不一致",
            code="m3_second_review_blocking_mismatch",
            retryable=False,
        )
    if not all(
        review.get(field) is True
        for field in ("revision_scope_valid", "m2_constraints_preserved", "coverage_valid")
    ):
        raise PipelineError(
            "M3 Second Reviewer 硬约束未通过",
            code="m3_second_review_hard_constraint_failed",
            retryable=False,
        )
    normalized = dict(review)
    normalized.update({
        "version": M3_SECOND_REVIEW_VERSION,
        "review_bundle_hash": _stable_hash(bundle),
        "blocking_count": blocking_count,
        "freeze_eligible": blocking_count == 0,
        "provider_call_count": 0,
    })
    _write_json_once(run_dir / "m3-second-semantic-review.json", normalized)
    return normalized


def freeze_m3(run_dir: Path) -> dict[str, Any]:
    inputs = {
        "clusters": json.loads(
            (run_dir / "m3-revised-clusters.json").read_text(encoding="utf-8")
        ),
        "decisions": json.loads(
            (run_dir / "m3-revised-alignment-decisions.json").read_text(encoding="utf-8")
        ),
        "first_review": json.loads(
            (run_dir / "m3-independent-semantic-review.json").read_text(encoding="utf-8")
        ),
        "second_review": json.loads(
            (run_dir / "m3-second-semantic-review.json").read_text(encoding="utf-8")
        ),
        "revision": json.loads(
            (run_dir / "m3-alignment-revision-01.json").read_text(encoding="utf-8")
        ),
        "revision_gate": json.loads(
            (run_dir / "m3-revision-gate.json").read_text(encoding="utf-8")
        ),
    }
    second_review = inputs["second_review"]
    gate = inputs["revision_gate"]
    if not second_review.get("freeze_eligible") or gate.get("status") != "PASS":
        raise PipelineError(
            "M3 尚未满足 Freeze 条件",
            code="m3_freeze_gate_failed",
            retryable=False,
        )
    clusters = list(inputs["clusters"].get("clusters") or [])
    candidates = [
        candidate
        for cluster in clusters
        for candidate in cluster.get("source_candidates") or []
    ]
    if len(candidates) != 126 or len(set(candidates)) != 126:
        raise PipelineError(
            "M3 Freeze Candidate Coverage 非 126/126",
            code="m3_freeze_coverage_invalid",
            retryable=False,
        )
    if any(cluster.get("recommended_status") == "stable" for cluster in clusters):
        raise PipelineError(
            "M3 Freeze 前出现 stable",
            code="m3_freeze_stable_forbidden",
            retryable=False,
        )
    disposition_counts = Counter(
        cluster.get("domain_disposition") for cluster in clusters
    )
    final_review = {
        "version": "m3-final-semantic-review-v1",
        "verdict": second_review["verdict"],
        "first_review_verdict": inputs["first_review"]["verdict"],
        "first_blocking_count": inputs["first_review"]["blocking_count"],
        "revision_count": 1,
        "second_blocking_count": second_review["blocking_count"],
        "finding_resolutions": second_review["finding_resolutions"],
        "remaining_concerns": [
            *(inputs["first_review"].get("non_blocking_concerns") or []),
            *(second_review.get("non_blocking_concerns") or []),
        ],
        "provider_call_count": 0,
    }
    final_gate = {
        "version": "m3-final-gate-v1",
        "status": "PASS",
        "blocking": [],
        "metrics": {
            "cluster_count": len(clusters),
            "candidate_count": len(candidates),
            "candidate_unique_count": len(set(candidates)),
            "stable_before_assignment": 0,
            "m2_exact_repromotion": 0,
            "m2_semantic_parallel_repromotion_resolved": True,
            "independent_reviewer_completed": True,
            "reviewer_verdict": second_review["verdict"],
            "remaining_concern_count": len(final_review["remaining_concerns"]),
        },
    }
    _write_json_once(run_dir / "m3-final-clusters.json", inputs["clusters"])
    _write_json_once(
        run_dir / "m3-final-alignment-decisions.json", inputs["decisions"]
    )
    _write_json_once(run_dir / "m3-final-semantic-review.json", final_review)
    _write_json_once(run_dir / "m3-final-gate.json", final_gate)
    manifest = {
        "version": M3_FINAL_MANIFEST_VERSION,
        "frozen_at": _utc_now(),
        "cluster_count": len(clusters),
        "domain_candidate_count": disposition_counts.get("domain_candidate", 0),
        "topic_count": disposition_counts.get("non_domain_topic", 0),
        "entity_count": disposition_counts.get("non_domain_entity", 0),
        "object_count": disposition_counts.get("non_domain_object", 0),
        "use_context_count": disposition_counts.get("non_domain_use_context", 0),
        "uncertain_count": disposition_counts.get("uncertain", 0),
        "merge_count": sum(
            operation.get("operation") == "merge_cluster"
            for operation in inputs["revision"]["operations"]
        ),
        "downgrade_count": sum(
            cluster.get("domain_disposition")
            in {"non_domain_topic", "non_domain_entity", "non_domain_object", "non_domain_use_context"}
            for cluster in clusters
        ),
        "reviewer_verdict": second_review["verdict"],
        "remaining_concerns": final_review["remaining_concerns"],
        "candidate_coverage": "126/126",
        "m2_repromotion": 0,
        "stable_before_assignment": 0,
        "artifact_hashes": {
            "m3_final_clusters": _stable_hash(inputs["clusters"]),
            "m3_final_alignment_decisions": _stable_hash(inputs["decisions"]),
            "m3_final_semantic_review": _stable_hash(final_review),
            "m3_final_gate": _stable_hash(final_gate),
        },
        "source_hashes": {
            name: _stable_hash(payload) for name, payload in inputs.items()
        },
    }
    _write_json_once(run_dir / "m3-final-manifest.json", manifest)
    return manifest
