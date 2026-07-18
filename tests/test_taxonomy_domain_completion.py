from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from shiliu.cli import build_parser
from shiliu.taxonomy.domain_completion import (
    REQUIRED_EXCLUDED_DIMENSIONS,
    DomainSemanticContractV2,
    SemanticAdjudicationOutput,
    UnresolvedBatchOutput,
    AlignmentBatchOutput,
    _candidate_pair_features,
    _connected_candidate_components,
    _unresolved_groups,
    apply_unresolved_review,
    build_semantic_review_record,
    pack_alignment_components,
    build_semantic_adjudication_prompt,
    build_semantic_audit_bundle,
    recover_alignment_batch,
    recover_unresolved_batch,
    recover_semantic_output,
    revise_semantic_contract_once,
    validate_unresolved_batch,
    validate_alignment_batch,
    validate_semantic_output,
)


def _contract(node_id: str) -> dict:
    return {
        "version": "domain-evidence-contract-v2",
        "nodes": [{
            "node_id": node_id,
            "name": "软件工程",
            "parent_id": None,
            "definition": "稳定的软件开发知识与实践问题空间",
            "evidence_stats": {"evidence_pool_count": 2, "source_candidate_count": 1},
        }],
    }


def _write_sources(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    run_c1 = tmp_path / "run-c1"
    checkpoint = tmp_path / "checkpoint"
    paths = [
        run_a / "consolidation/main/attempt-01",
        run_b / "domain_consolidation/main/attempt-01",
        run_c1 / "domain_node_synthesis/main/attempt-01",
        run_c1 / "candidate_routing/batch-001/attempt-01",
        checkpoint,
    ]
    for path in paths:
        path.mkdir(parents=True)
    (paths[0] / "prompt.txt").write_text("A rules\n精简输出结构：{A}\nCompact Candidate Table：private")
    (paths[1] / "prompt.txt").write_text("B rules\n精简输出结构：{B}\nCompact Candidate Table：private")
    (paths[2] / "prompt.txt").write_text("C1 node\nSchema:{N}\nComplete Candidate Table:private")
    (paths[3] / "prompt.txt").write_text("C1 route\nSchema:{R}\nFrozen Tree:private")
    (checkpoint / "run-a-domain-contract-v2.json").write_text(json.dumps(_contract("d_a")))
    (checkpoint / "run-b-domain-contract-v2.json").write_text(json.dumps(_contract("d_b")))
    (checkpoint / "candidate-decisions-complete-v1.json").write_text(json.dumps({
        "candidate_decisions": [{
            "candidate_id": "nc_001", "action": "unresolved_requires_new_domain",
        }]
    }))
    (run_c1 / "run-c1-domain-contract-v2.json").write_text(json.dumps(_contract("c1_d_01")))
    (run_c1 / "run-c1-candidate-decisions-complete.json").write_text(json.dumps({
        "candidate_decisions": [{
            "candidate_id": "nc_001", "action": "downgrade_to_topic",
        }]
    }))
    return run_a, run_b, run_c1, checkpoint


def _valid_payload(bundle: dict) -> dict:
    source_rows = []
    for label, payload in bundle["sources"].items():
        prompts = [
            value["preamble_sha256"]
            for key, value in payload.items()
            if key in {"prompt", "node_prompt", "routing_prompt"}
        ]
        schemas = [value for key, value in payload.items() if key.endswith("schema_hash")]
        source_rows.append({
            "source": label,
            "protocol_label": payload["protocol"],
            "prompt_hashes": prompts,
            "schema_hashes": schemas,
            "explicit_rules": ["稳定语义"],
            "implicit_constraints": [],
            "missing_or_ambiguous_rules": ["支持度"],
            "protocol_risks": payload["protocol_risks"],
        })
    return {
        "contract": {
            "version": "domain-semantic-contract-v2",
            "primary_question": "内容主要属于什么相对稳定、可长期复用的知识领域或问题空间？",
            "domain_definition": "能够长期容纳未来多条内容且边界可解释的稳定知识领域或实践问题空间。",
            "topic_definition": "比 Domain 更具体、更短期或更窄的讨论主题。",
            "entity_definition": "工具、模型、项目、产品、公司、人物、论文或其他具体对象。",
            "excluded_dimensions": sorted(REQUIRED_EXCLUDED_DIMENSIONS),
            "stable_domain_criteria": ["长期复用", "未来可收集", "边界清楚", "轴纯净"],
            "classification_tests": [
                "instance_test", "temporal_test", "future_collection_test",
                "axis_purity_test", "parent_entailment_test", "evidence_test",
            ],
            "domain_axis_policy": {
                "stable_knowledge_domains_allowed": True,
                "stable_practice_problem_spaces_allowed": True,
                "learning_path_is_domain": False,
                "interview_use_is_domain": False,
                "focus_object_without_problem_space_is_domain": False,
            },
            "non_domain_routing_policy": {
                "routes": [
                    "presentation_form", "focus_object_type", "suggested_use_context",
                    "topic", "entity", "unsupported", "uncertain",
                ],
                "topic_domain_reference_is_membership": False,
                "closest_domain_may_be_recorded_as_provenance": True,
            },
            "support_policy": {
                "discovery_support_is_provisional": True,
                "assignment_support_is_product_evidence": True,
                "single_evidence_default_status": "weak_or_uncertain",
                "single_evidence_exception": "foundational_and_cross_run_or_assignment_supported",
                "multi_evidence_is_stability_signal": True,
                "multi_evidence_is_sufficient": False,
            },
            "hierarchy_policy": {
                "max_depth": 2,
                "child_is_semantic_subset": True,
                "evidence_set_containment_required": False,
                "parent_may_be_mechanical_name_summary": False,
            },
            "unresolved_policy": {
                "meaning": "current_frozen_tree_cannot_safely_route_candidate",
                "automatically_creates_domain": False,
                "requires_adjudication": True,
            },
            "node_statuses": ["stable", "probable", "weak", "uncertain"],
            "assignment_rules": ["一个 primary", "最多两个 secondary", "允许拒绝", "禁止建域"],
            "anti_overfitting_rules": ["不投票", "不强归", "不以节点膨胀换零 Gap"],
        },
        "diff": {
            "version": "semantic-contract-diff-a-b-c1-v1",
            "sources": source_rows,
            "rule_resolutions": [{
                "rule_id": f"sr_{index:02d}", "a_rule": "A", "b_rule": "B", "c1_rule": "C1",
                "canonical_v2_rule": f"统一产品规则 {index}", "resolution_reason": "依据已批准产品边界统一规则。",
                "adopted_from": "approved_product_definition", "known_risk": "none",
            } for index in range(1, 9)],
            "comparability_conclusion": "independent_evidence_sources_with_protocol_provenance",
            "blocking_contradictions": [],
        },
        "adjudication_notes": [],
    }


def test_semantic_bundle_uses_only_preambles_and_protocol_provenance(tmp_path: Path):
    bundle = build_semantic_audit_bundle(
        **dict(zip(
            ("run_a_dir", "run_b_dir", "run_c1_dir", "checkpoint_312c_dir"),
            _write_sources(tmp_path),
        ))
    )
    assert "private" not in json.dumps(bundle, ensure_ascii=False)
    assert set(bundle["sources"]) == {"A", "B", "C1"}
    assert bundle["sources"]["B"]["decisions"]["unresolved"]


def test_semantic_contract_enforces_product_axis_and_order(tmp_path: Path):
    run_a, run_b, run_c1, checkpoint = _write_sources(tmp_path)
    bundle = build_semantic_audit_bundle(
        run_a_dir=run_a, run_b_dir=run_b, run_c1_dir=run_c1, checkpoint_312c_dir=checkpoint,
    )
    payload = _valid_payload(bundle)
    value = SemanticAdjudicationOutput.model_validate(payload)
    assert value.contract.domain_axis_policy.stable_practice_problem_spaces_allowed is True
    payload["contract"]["excluded_dimensions"].remove("interview_use")
    with pytest.raises(ValidationError):
        DomainSemanticContractV2.model_validate(payload["contract"])


def test_semantic_validation_pins_historical_prompt_and_schema_hashes(tmp_path: Path):
    run_a, run_b, run_c1, checkpoint = _write_sources(tmp_path)
    bundle = build_semantic_audit_bundle(
        run_a_dir=run_a, run_b_dir=run_b, run_c1_dir=run_c1, checkpoint_312c_dir=checkpoint,
    )
    value = SemanticAdjudicationOutput.model_validate(_valid_payload(bundle))
    validate_semantic_output(value, bundle)
    value.diff.sources[0].prompt_hashes[0] = "changed"
    with pytest.raises(Exception):
        validate_semantic_output(value, bundle)


def test_semantic_prompt_rejects_voting_and_preserves_non_domain_routes(tmp_path: Path):
    run_a, run_b, run_c1, checkpoint = _write_sources(tmp_path)
    bundle = build_semantic_audit_bundle(
        run_a_dir=run_a, run_b_dir=run_b, run_c1_dir=run_c1, checkpoint_312c_dir=checkpoint,
    )
    prompt = build_semantic_adjudication_prompt(bundle)
    assert "不得投票" in prompt
    assert "Form/Object/Context/Topic/Entity" in prompt
    assert "Silver" in prompt and "不得读取" in prompt


def test_local_recovery_normalizes_enum_and_factors_approved_axis_rule(tmp_path: Path):
    run_a, run_b, run_c1, checkpoint = _write_sources(tmp_path / "sources")
    bundle = build_semantic_audit_bundle(
        run_a_dir=run_a, run_b_dir=run_b, run_c1_dir=run_c1, checkpoint_312c_dir=checkpoint,
    )
    payload = _valid_payload(bundle)
    payload["diff"]["rule_resolutions"].pop()
    payload["diff"]["rule_resolutions"][0]["adopted_from"] = "approved_product_requirements + C1"
    call_dir = tmp_path / "call"
    call_dir.mkdir()
    (call_dir / "repair-raw-response.txt").write_text(json.dumps(payload, ensure_ascii=False))
    (call_dir / "audit.json").write_text(json.dumps({"usage": {}, "status": "raw_received"}))
    (call_dir / "repair-audit.json").write_text(json.dumps({"status": "completed", "usage": {}}))
    value, audit = recover_semantic_output(call_dir, bundle)
    assert len(value.diff.rule_resolutions) == 8
    assert value.diff.rule_resolutions[-1].rule_id == "sr_08"
    assert value.diff.rule_resolutions[0].adopted_from == "synthesis"
    assert audit["local_recovery"]["provider_call_count"] == 0


def test_semantic_revision_separates_domain_type_from_evidence_maturity(tmp_path: Path):
    run_a, run_b, run_c1, checkpoint = _write_sources(tmp_path)
    bundle = build_semantic_audit_bundle(
        run_a_dir=run_a, run_b_dir=run_b, run_c1_dir=run_c1, checkpoint_312c_dir=checkpoint,
    )
    payload = _valid_payload(bundle)
    provider_contract = DomainSemanticContractV2.model_validate(payload["contract"])
    provider_diff = SemanticAdjudicationOutput.model_validate(payload).diff

    final_contract, final_diff, revision = revise_semantic_contract_once(
        provider_contract, provider_diff,
    )

    assert "当前证据数量不决定其是否属于 Domain" in final_contract.domain_definition
    assert final_contract.support_policy.multi_evidence_is_sufficient is False
    assert final_contract.support_policy.cross_run_duplicate_counts_as_new_evidence is False
    assert final_contract.support_policy.single_evidence_exception == "none_without_explicit_adjudication"
    assert "产品赋值证据要求已满足" in final_contract.status_definitions.stable
    assert "至少两个不同内容支持" in final_contract.status_definitions.probable
    assert "父节点语义子集" in final_contract.assignment_rules[1]
    assert "证据数量不决定候选是否属于 Domain" in next(
        item.canonical_v2_rule for item in final_diff.rule_resolutions if item.rule_id == "sr_01"
    )
    assert revision["provider_call_count"] == 0
    assert revision["diff_rule_changes"] == ["sr_01", "sr_03", "sr_06"]

    review = build_semantic_review_record(
        contract=final_contract,
        diff=final_diff,
        revision=revision,
        verdict="PASS_WITH_CONCERNS",
        blocking_findings=[],
        non_blocking_concerns=["stable 的数值门槛在 Assignment Protocol 中冻结"],
    )
    assert review["freeze_eligible"] is True
    assert review["provider_call_count"] == 0
    assert review["contract_hash"] == revision["final_contract_hash"]

    with pytest.raises(ValueError):
        build_semantic_review_record(
            contract=final_contract,
            diff=final_diff,
            revision=revision,
            verdict="PASS",
            blocking_findings=["contradiction"],
            non_blocking_concerns=[],
        )


def test_domain_completion_cli_defaults_to_frozen_sources():
    args = build_parser().parse_args(["taxonomy", "create-domain-completion"])
    assert (args.run_a_id, args.run_b_id, args.run_c1_id) == (12, 22, 23)


def test_unresolved_grouping_deduplicates_only_cross_run_semantic_evidence():
    rows = [
        {
            "source_run": "B",
            "candidate_id": "nc_037",
            "candidate": {
                "name": "算法与数据结构",
                "definition": "经典算法与数据结构",
                "supporting_ids": ["C131"],
            },
        },
        {
            "source_run": "C1",
            "candidate_id": "nc_039",
            "candidate": {
                "name": "算法优化与双指针技巧",
                "definition": "使用双指针优化经典数组算法",
                "supporting_ids": ["C131"],
            },
        },
        {
            "source_run": "C1",
            "candidate_id": "nc_040",
            "candidate": {
                "name": "终端与命令行",
                "definition": "文本计算机交互界面",
                "supporting_ids": ["C080", "C106"],
            },
        },
    ]
    groups = _unresolved_groups(rows)
    assert len(groups) == 2
    assert {(item["source_run"], item["candidate_id"]) for item in groups[0]} == {
        ("B", "nc_037"), ("C1", "nc_039"),
    }


def test_unresolved_batch_requires_exact_ids_targets_and_evidence():
    groups = [{
        "adjudication_id": "ua_001",
        "representative_profiles": [{"content_id": "C131"}],
        "nearest_existing_nodes": [{"ref": "A:d_07"}],
    }]
    output = UnresolvedBatchOutput.model_validate({
        "decisions": [{
            "adjudication_id": "ua_001",
            "adjudication": "candidate_too_narrow",
            "recommended_operation": "downgrade_to_topic",
            "closest_existing_nodes": ["A:d_07"],
            "evidence": ["C131"],
            "reason": "候选只描述单一算法技巧，不能形成可长期浏览的稳定领域边界。",
            "counterarguments": ["它可以作为更宽算法领域的局部证据。"],
            "confidence": "high",
        }],
    })
    validate_unresolved_batch(output, groups)
    output.decisions[0].evidence = ["C999"]
    with pytest.raises(Exception):
        validate_unresolved_batch(output, groups)

    with pytest.raises(ValidationError):
        UnresolvedBatchOutput.model_validate({
            "decisions": [{
                "adjudication_id": "ua_001",
                "adjudication": "candidate_is_topic",
                "recommended_operation": "create_domain_proposal",
                "closest_existing_nodes": [],
                "evidence": ["C131"],
                "reason": "候选属于 Topic，却错误请求创建正式 Domain Proposal。",
                "counterarguments": ["无。"],
                "confidence": "high",
            }],
        })


def test_unresolved_local_recovery_only_removes_out_of_group_node_ref(tmp_path: Path):
    groups = [{
        "adjudication_id": "ua_001",
        "representative_profiles": [{"content_id": "C126"}],
        "nearest_existing_nodes": [{"ref": "C1:c1_d_03_04"}],
    }]
    payload = {
        "decisions": [{
            "adjudication_id": "ua_001",
            "adjudication": "true_tree_gap",
            "recommended_operation": "create_domain_proposal",
            "closest_existing_nodes": ["C1:c1_d_03_04", "A:d_07"],
            "evidence": ["C126"],
            "reason": "间隔重复属于稳定实践问题空间，当前冻结树中的相邻节点都无法安全承载。",
            "counterarguments": ["当前只有一个内容证据，应保持 weak。"],
            "confidence": "low",
        }],
    }
    (tmp_path / "repair-raw-response.txt").write_text(json.dumps(payload, ensure_ascii=False))
    (tmp_path / "audit.json").write_text(json.dumps({"usage": {}, "status": "raw_received"}))
    (tmp_path / "repair-audit.json").write_text(json.dumps({"usage": {}, "status": "validation_failed"}))
    value, audit = recover_unresolved_batch(tmp_path, groups)
    assert value.decisions[0].closest_existing_nodes == ["C1:c1_d_03_04"]
    assert audit["local_recovery"]["provider_call_count"] == 0
    assert audit["local_recovery"]["transformations"][0]["before"] == [
        "C1:c1_d_03_04", "A:d_07",
    ]


def test_unresolved_review_requires_override_for_reject_and_revalidates():
    bundle = {"groups": [{
        "adjudication_id": "ua_001",
        "representative_profiles": [{"content_id": "C126"}],
        "nearest_existing_nodes": [{"ref": "C1:c1_d_03_04"}],
    }]}
    draft = {
        "snapshot_id": 2,
        "snapshot_hash": "snapshot",
        "semantic_contract_hash": "contract",
        "source_item_count": 1,
        "source_counts": {"B": 1},
        "deduplicated_group_count": 1,
        "decisions": [{
            "sources": [{"source_run": "B", "candidate_id": "nc_040", "candidate_name": "间隔重复系统"}],
            "adjudication_id": "ua_001",
            "adjudication": "true_tree_gap",
            "recommended_operation": "create_domain_proposal",
            "closest_existing_nodes": ["C1:c1_d_03_04"],
            "evidence": ["C126"],
            "reason": "间隔重复属于稳定实践问题空间，当前冻结树中的相邻节点都无法安全承载。",
            "counterarguments": ["当前只有一个项目证据。"],
            "confidence": "low",
            "reviewer_verdict": "pending",
            "review_notes": [],
        }],
    }
    reviews = [{
        "adjudication_id": "ua_001",
        "reviewer_verdict": "reject",
        "review_notes": ["单一 SRS 方法被过度扩张为 Domain。"],
    }]
    with pytest.raises(ValueError):
        apply_unresolved_review(
            draft=draft, bundle=bundle, review_results=reviews, overrides={},
        )
    final, revision = apply_unresolved_review(
        draft=draft,
        bundle=bundle,
        review_results=reviews,
        overrides={"ua_001": {
            "adjudication": "candidate_is_topic",
            "recommended_operation": "downgrade_to_topic",
            "reason": "当前证据只支持单一 SRS 方法与具体系统，应保留为 Topic，不能扩张为稳定 Domain。",
        }},
    )
    assert final["decisions"][0]["adjudication"] == "candidate_is_topic"
    assert final["decisions"][0]["recommended_operation"] == "downgrade_to_topic"
    assert revision["provider_call_count"] == 0
    assert revision["changed_ids"] == ["ua_001"]


def test_candidate_pair_graph_is_deterministic_and_scores_evidence_overlap():
    left = {
        "name": "算法与数据结构",
        "definition": "经典算法与复杂度分析",
        "includes": ["双指针"],
        "excludes": ["短期刷题"],
        "parent_hints": [],
        "supporting_ids": ["C131"],
    }
    right = {
        "name": "算法优化与双指针技巧",
        "definition": "使用双指针优化数组算法",
        "includes": ["复杂度优化"],
        "excludes": ["图算法"],
        "parent_hints": [],
        "supporting_ids": ["C131"],
    }
    features = _candidate_pair_features(left, right)
    assert features["evidence_overlap"] == 1.0
    assert features["score"] >= 5.0
    records = {"A:nc_001": {}, "B:nc_001": {}, "C1:nc_001": {}}
    components = _connected_candidate_components(records, [{
        "left_ref": "A:nc_001", "right_ref": "B:nc_001",
    }])
    assert components == [["A:nc_001", "B:nc_001"], ["C1:nc_001"]]


def test_alignment_batches_and_validator_allow_split_but_require_exact_coverage():
    components = [
        {
            "source_component_id": "sc_001",
            "candidate_count": 2,
            "candidates": [
                {"ref": "A:nc_001", "supporting_ids": ["C001"]},
                {"ref": "B:nc_001", "supporting_ids": ["C001", "C002"]},
            ],
        },
        {
            "source_component_id": "sc_002",
            "candidate_count": 1,
            "candidates": [{"ref": "C1:nc_002", "supporting_ids": ["C003"]}],
        },
    ]
    assert len(pack_alignment_components(components, max_candidates=2, max_components=8)) == 2
    output = AlignmentBatchOutput.model_validate({
        "clusters": [
            {
                "source_component_id": "sc_001",
                "source_members": ["A:nc_001", "B:nc_001"],
                "alignment_relation": "equivalent",
                "domain_disposition": "domain_candidate",
                "recommended_status": "probable",
                "canonical_name": "算法基础",
                "canonical_definition": "长期稳定的算法与数据结构基础知识领域。",
                "canonical_includes": ["经典算法"],
                "canonical_excludes": ["单一题目技巧"],
                "evidence_pool_ids": ["C001", "C002"],
                "representative_ids": ["C001"],
                "parent_scope_hint": None,
                "confidence": "high",
                "decision_reason": "两个候选的定义、边界和代表 Evidence 均指向同一稳定知识范围。",
                "protocol_risk_notes": [],
            },
            {
                "source_component_id": "sc_002",
                "source_members": ["C1:nc_002"],
                "alignment_relation": "protocol_specific",
                "domain_disposition": "non_domain_topic",
                "recommended_status": "not_applicable",
                "canonical_name": "单一技巧",
                "canonical_definition": "仅由单一内容支持的窄主题，不构成稳定领域。",
                "canonical_includes": ["局部技巧"],
                "canonical_excludes": ["稳定知识领域"],
                "evidence_pool_ids": ["C003"],
                "representative_ids": ["C003"],
                "parent_scope_hint": None,
                "confidence": "medium",
                "decision_reason": "候选只在一种协议下出现，且语义范围属于单一窄主题。",
                "protocol_risk_notes": ["单来源"],
            },
        ],
    })
    validate_alignment_batch(output, components)
    output.clusters[1].source_members = ["A:nc_001"]
    with pytest.raises(Exception):
        validate_alignment_batch(output, components)


def test_alignment_validator_rejects_pre_assignment_stable_and_m2_repromotion():
    components = [{
        "source_component_id": "sc_001",
        "candidate_count": 1,
        "candidates": [{
            "ref": "B:nc_001",
            "name": "间隔重复系统",
            "supporting_ids": ["C001"],
            "unresolved_adjudication": {
                "recommended_operation": "downgrade_to_topic",
            },
        }],
    }]
    payload = {
        "clusters": [{
            "source_component_id": "sc_001",
            "source_members": ["B:nc_001"],
            "alignment_relation": "protocol_specific",
            "domain_disposition": "domain_candidate",
            "recommended_status": "stable",
            "canonical_name": "间隔重复系统",
            "canonical_definition": "围绕间隔重复机制形成的长期学习知识领域。",
            "canonical_includes": ["重复调度"],
            "canonical_excludes": ["普通学习技巧"],
            "evidence_pool_ids": ["C001"],
            "representative_ids": ["C001"],
            "parent_scope_hint": None,
            "confidence": "medium",
            "decision_reason": "该候选来自单一来源，需要保守判断其产品分类地位。",
            "protocol_risk_notes": [],
        }],
    }
    output = AlignmentBatchOutput.model_validate(payload)
    with pytest.raises(Exception, match="不能晋升 stable"):
        validate_alignment_batch(output, components)
    output.clusters[0].recommended_status = "weak"
    with pytest.raises(Exception, match="静默晋升"):
        validate_alignment_batch(output, components)


def test_alignment_schema_preserves_uncertain_disposition_status():
    output = AlignmentBatchOutput.model_validate({"clusters": [{
        "source_component_id": "sc_001",
        "source_members": ["B:nc_039"],
        "alignment_relation": "uncertain",
        "domain_disposition": "uncertain",
        "recommended_status": "uncertain",
        "canonical_name": "语音交互系统",
        "canonical_definition": "候选混合具体项目与可能的长期问题空间，当前无法安全确定 Domain 地位。",
        "canonical_includes": [],
        "canonical_excludes": [],
        "evidence_pool_ids": ["C001"],
        "representative_ids": ["C001"],
        "parent_scope_hint": None,
        "confidence": "low",
        "decision_reason": "M2 判为 candidate_mixed，保留 uncertain 比错误降级或晋升更诚实。",
        "protocol_risk_notes": [],
    }]})
    assert output.clusters[0].recommended_status == "uncertain"


def test_recover_alignment_batch_applies_only_audited_structural_tails(tmp_path: Path):
    components = [{
        "source_component_id": "sc_001",
        "candidate_count": 2,
        "candidates": [
            {
                "ref": "A:nc_001", "name": "Agent 长期记忆系统",
                "supporting_ids": ["C001", "C002"],
            },
            {
                "ref": "B:nc_006", "name": "Agent 记忆与上下文工程",
                "supporting_ids": ["C002", "C003"],
            },
        ],
    }]
    repair = {
        "clusters": [{
            "source_component_id": "sc_001",
            "source_members": ["A:nc_001", "B:nc_006"],
            "alignment_relation": "equivalent",
            "domain_disposition": "domain_candidate",
            "recommended_status": "stable",
            "canonical_name": "",
            "canonical_definition": "研究 Agent 长期记忆的存储、检索、更新与上下文衔接机制。",
            "canonical_includes": [f"include-{index}" for index in range(10)],
            "canonical_excludes": [f"exclude-{index}" for index in range(10)],
            "evidence_pool_ids": ["C001", "C002", "C003"],
            "representative_ids": ["C002"],
            "parent_scope_hint": None,
            "confidence": "high",
            "decision_reason": "",
            "protocol_risk_notes": [],
        }],
    }
    (tmp_path / "repair-raw-response.txt").write_text(
        json.dumps(repair, ensure_ascii=False), encoding="utf-8",
    )
    (tmp_path / "repair-audit.json").write_text(
        json.dumps({"usage": {"total_tokens": 100}}), encoding="utf-8",
    )
    (tmp_path / "audit.json").write_text(
        json.dumps({"status": "failed", "usage": {"total_tokens": 500}}),
        encoding="utf-8",
    )

    output, audit = recover_alignment_batch(tmp_path, components)

    cluster = output.clusters[0]
    assert cluster.canonical_name in {
        "Agent 长期记忆系统", "Agent 记忆与上下文工程",
    }
    assert cluster.recommended_status == "probable"
    assert len(cluster.canonical_includes) == 8
    assert len(cluster.canonical_excludes) == 8
    assert "高推理主响应" in cluster.decision_reason
    assert audit["local_recovery"]["provider_call_count"] == 0
    assert (tmp_path / "parsed-output.json").is_file()
    assert {
        item["kind"] for item in audit["local_recovery"]["transformations"]
    } == {
        "select_existing_candidate_name", "provider_grouping_provenance",
        "ordered_schema_cap", "pre_assignment_support_policy",
    }


def test_recover_alignment_batch_accepts_empty_boundaries_only_for_non_domain(tmp_path: Path):
    components = [{
        "source_component_id": "sc_001",
        "candidate_count": 1,
        "candidates": [{
            "ref": "C1:nc_008", "name": "Agent 面试内容",
            "supporting_ids": ["C009"],
        }],
    }]
    cluster = {
        "source_component_id": "sc_001",
        "source_members": ["C1:nc_008"],
        "alignment_relation": "protocol_specific",
        "domain_disposition": "non_domain_topic",
        "recommended_status": "not_applicable",
        "canonical_name": "Agent 面试内容",
        "canonical_definition": "围绕 Agent 求职面试展开的阶段性内容主题。",
        "canonical_includes": [],
        "canonical_excludes": [],
        "evidence_pool_ids": ["C009"],
        "representative_ids": ["C009"],
        "parent_scope_hint": None,
        "confidence": "medium",
        "decision_reason": "该候选表达求职使用情境，不构成长期稳定的知识领域。",
        "protocol_risk_notes": [],
    }
    raw_path = tmp_path / "raw-response-02.txt"
    raw_path.write_text(
        json.dumps({"clusters": [cluster]}, ensure_ascii=False), encoding="utf-8",
    )
    (tmp_path / "audit.json").write_text(json.dumps({
        "status": "raw_received",
        "raw_response_path": raw_path.name,
        "usage": {"total_tokens": 100},
    }), encoding="utf-8")

    output, audit = recover_alignment_batch(tmp_path, components)

    assert output.clusters[0].canonical_includes == []
    assert output.clusters[0].canonical_excludes == []
    assert audit["local_recovery"]["recovery_mode"] == (
        "disposition_aware_schema_revalidation"
    )
    domain_payload = json.loads(json.dumps(cluster))
    domain_payload["domain_disposition"] = "domain_candidate"
    domain_payload["recommended_status"] = "probable"
    with pytest.raises(ValidationError, match="executable includes/excludes"):
        AlignmentBatchOutput.model_validate({"clusters": [domain_payload]})


def test_recover_alignment_batch_replaces_non_domain_placeholders_from_candidate(tmp_path: Path):
    components = [{
        "source_component_id": "sc_001",
        "candidate_count": 1,
        "candidates": [{
            "ref": "B:nc_004",
            "name": "模型评测动态",
            "definition": "围绕具体模型版本与评测结果展开的阶段性讨论主题。",
            "supporting_ids": ["C004"],
        }],
    }]
    payload = {"clusters": [{
        "source_component_id": "sc_001",
        "source_members": ["B:nc_004"],
        "alignment_relation": "protocol_specific",
        "domain_disposition": "non_domain_topic",
        "recommended_status": "not_applicable",
        "canonical_name": "未命名",
        "canonical_definition": "无足够信息定义",
        "canonical_includes": [],
        "canonical_excludes": [],
        "evidence_pool_ids": ["C004"],
        "representative_ids": ["C004"],
        "parent_scope_hint": None,
        "confidence": "low",
        "decision_reason": "该候选只构成阶段性 Topic，不应进入正式 Domain Tree。",
        "protocol_risk_notes": [],
    }]}
    (tmp_path / "repair-raw-response.txt").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8",
    )
    (tmp_path / "audit.json").write_text(
        json.dumps({"status": "failed", "usage": {}}), encoding="utf-8",
    )

    output, audit = recover_alignment_batch(tmp_path, components)

    cluster = output.clusters[0]
    assert cluster.canonical_name == "模型评测动态"
    assert cluster.canonical_definition == components[0]["candidates"][0]["definition"]
    assert {
        item["kind"] for item in audit["local_recovery"]["transformations"]
    } == {
        "select_existing_candidate_name", "select_existing_candidate_definition",
    }
