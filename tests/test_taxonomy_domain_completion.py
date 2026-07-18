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
    build_semantic_review_record,
    build_semantic_adjudication_prompt,
    build_semantic_audit_bundle,
    recover_semantic_output,
    revise_semantic_contract_once,
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
