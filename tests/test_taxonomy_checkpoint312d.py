from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from shiliu.taxonomy.domain_consolidation_v2 import (
    DOMAIN_SEMANTIC_CONTRACT,
    EXECUTION_CONTRACT_VERSION,
    HASH_ALGORITHM_VERSION,
    ROUTING_BATCH_SIZE,
    CandidateRoutingOutput,
    DomainConsolidationV2Service,
    DomainNodeSynthesisOutput,
    assemble_decisions,
    build_node_synthesis_prompt,
    build_routing_prompt,
    deterministic_routing_batches,
    enrich_candidate_lineage,
    hash_contract,
    nodes_to_nested_domains,
    semantic_contract_hash,
    validate_node_synthesis,
    validate_routing,
    versioned_tree_hash,
)
from shiliu.taxonomy.candidates import CompactCandidateTable, LocalTopLevelDiscoveryOutput


def _candidates(count: int = 25):
    return [
        {
            "candidate_id": f"nc_{index:03d}", "name": f"领域{index}",
            "definition": f"稳定领域{index}", "includes": ["方法"], "excludes": ["工具"],
            "supporting_ids": [f"C{index:03d}"], "representative_ids": [f"C{index:03d}"],
            "confidence": "high", "source_batch_ids": ["batch-001"],
        }
        for index in range(1, count + 1)
    ]


def _tree():
    return DomainNodeSynthesisOutput.model_validate({
        "domain_nodes": [
            {
                "node_id": "c1_d_01", "name": "软件工程", "definition": "软件工程稳定领域",
                "canonical_includes": ["开发"], "canonical_excludes": ["硬件"],
                "parent_id": None, "model_selected_evidence_ids": ["C001", "C002"],
                "representative_ids": ["C001"], "confidence": "high",
            },
            {
                "node_id": "c1_d_01_01", "name": "开发流程", "definition": "软件开发流程",
                "canonical_includes": ["流程"], "canonical_excludes": ["硬件"],
                "parent_id": "c1_d_01", "model_selected_evidence_ids": ["C002"],
                "representative_ids": ["C002"], "confidence": "medium",
            },
        ],
        "synthesis_notes": [],
    })


def _routing(ids: list[str]):
    return CandidateRoutingOutput.model_validate({
        "candidate_decisions": [
            {
                "candidate_id": value, "action": "merge_into_existing_domain",
                "target_id": "c1_d_01", "reason": "定义相符",
                "definition_comparison": "属于软件工程", "granularity_assessment": "领域级",
                "evidence_assessment": "证据充分", "confidence": "high",
            }
            for value in ids
        ]
    })


def test_hash_contract_is_versioned_sorted_and_reproducible(tmp_path: Path):
    (tmp_path / "b.txt").write_bytes(b"b\r\n")
    (tmp_path / "a.txt").write_bytes(b"a\n")
    (tmp_path / ".DS_Store").write_bytes(b"ignored")
    first = versioned_tree_hash(tmp_path)
    second = versioned_tree_hash(tmp_path)
    assert first["tree_hash_algorithm_version"] == HASH_ALGORITHM_VERSION
    assert [item["path"] for item in first["files"]] == ["a.txt", "b.txt"]
    assert first["tree_hash"] == second["tree_hash"]
    assert hash_contract()["line_ending_policy"] == "raw_bytes"


def test_hash_contract_rejects_symlink(tmp_path: Path):
    target = tmp_path / "target"; target.write_text("x")
    (tmp_path / "link").symlink_to(target)
    with pytest.raises(ValueError):
        versioned_tree_hash(tmp_path)


def test_semantic_contract_canonical_hash_and_execution_separation():
    assert semantic_contract_hash() == semantic_contract_hash()
    assert DOMAIN_SEMANTIC_CONTRACT["hierarchy_non_requirement"].startswith("子节点 Evidence")
    assert EXECUTION_CONTRACT_VERSION.endswith("v2")


def test_node_prompt_uses_complete_candidate_table_without_top_k():
    prompt = build_node_synthesis_prompt(_candidates(25))
    assert all(f"nc_{index:03d}" in prompt for index in range(1, 26))
    assert "不得使用固定 Top-K" in prompt
    assert "candidate_decisions" not in prompt.lower()


def test_node_schema_forbids_candidate_decisions_and_depth_three():
    payload = _tree().model_dump(mode="json")
    payload["candidate_decisions"] = []
    with pytest.raises(ValidationError):
        DomainNodeSynthesisOutput.model_validate(payload)
    payload = _tree().model_dump(mode="json")
    payload["domain_nodes"].append({
        **payload["domain_nodes"][1], "node_id": "c1_d_01_02",
        "parent_id": "c1_d_01_01", "name": "三级",
    })
    with pytest.raises(ValidationError):
        DomainNodeSynthesisOutput.model_validate(payload)


def test_node_evidence_must_be_traceable():
    with pytest.raises(Exception):
        validate_node_synthesis(_tree(), allowed_evidence_ids={"C001"})


def test_routing_batches_are_deterministic_and_bounded():
    candidates = _candidates(25)
    first = deterministic_routing_batches(candidates)
    second = deterministic_routing_batches(candidates)
    assert [[x["candidate_id"] for x in batch] for batch in first] == [[x["candidate_id"] for x in batch] for batch in second]
    assert [len(batch) for batch in first] == [ROUTING_BATCH_SIZE, ROUTING_BATCH_SIZE, 1]
    with pytest.raises(ValueError):
        deterministic_routing_batches(candidates, 9)


def test_routing_exact_coverage_and_legal_target():
    output = _routing(["nc_001", "nc_002"])
    validate_routing(output, expected_ids=["nc_001", "nc_002"], node_ids={"c1_d_01"})
    with pytest.raises(Exception):
        validate_routing(output, expected_ids=["nc_002", "nc_001"], node_ids={"c1_d_01"})
    with pytest.raises(Exception):
        validate_routing(output, expected_ids=["nc_001", "nc_002"], node_ids={"c1_d_02"})


def test_routing_action_target_contract():
    payload = _routing(["nc_001"]).model_dump(mode="json")
    payload["candidate_decisions"][0].update(action="unresolved_requires_new_domain", target_id="c1_d_01")
    with pytest.raises(ValidationError):
        CandidateRoutingOutput.model_validate(payload)


def test_routing_prompt_freezes_tree_and_only_current_batch():
    prompt = build_routing_prompt(_candidates(2), _tree(), completed_ids=["nc_099"])
    assert "Domain Tree 已冻结" in prompt
    assert "nc_001" in prompt and "nc_002" in prompt and "nc_099" in prompt
    assert "nc_003" not in prompt


def test_assembly_requires_100_percent_ordered_coverage_and_lineage():
    candidates = _candidates(2)
    output = _routing(["nc_001", "nc_002"])
    result = assemble_decisions(candidates, [("batch-001", output, "hash")])
    assert [item["candidate_id"] for item in result] == ["nc_001", "nc_002"]
    assert {item["decision_source"] for item in result} == {"batched_candidate_routing"}
    with pytest.raises(Exception):
        assemble_decisions(candidates, [("batch-001", _routing(["nc_001"]), "hash")])


def test_normalized_candidate_lineage_is_derived_from_source_batches():
    outputs = [LocalTopLevelDiscoveryOutput.model_validate({
        "domains": [{
            "provisional_id": "ld_a", "name": "软件工程", "definition": "软件工程方法",
            "supporting_ids": ["C001"], "representative_ids": ["C001"],
            "evidence_codes": ["durable_domain"], "includes": ["开发"], "excludes": ["硬件"],
            "possible_parent": None, "confidence": "high", "node_type": "domain",
        }], "topic_hints": [], "ambiguous_ids": [],
    })]
    table = CompactCandidateTable.model_validate({
        "version": "compact-domain-candidates-v3", "source_batch_count": 1,
        "domains": [{
            "candidate_id": "nc_001", "name": "软件工程", "definition": "软件工程方法",
            "support_count": 1, "batch_count": 1, "supporting_ids": ["C001"],
            "representative_ids": ["C001"], "evidence_codes": ["durable_domain"],
            "includes": ["开发"], "excludes": ["硬件"], "parent_hints": [], "confidence": "high",
        }], "topic_hints": [],
    })
    assert enrich_candidate_lineage(table, outputs)[0]["source_batch_ids"] == ["batch-001"]


def test_nested_tree_conversion_preserves_frozen_semantics():
    nested = nodes_to_nested_domains(_tree())
    assert nested[0]["id"] == "c1_d_01"
    assert nested[0]["children"][0]["id"] == "c1_d_01_01"
    assert nested[0]["includes"] == ["开发"]


def test_replication_plan_locks_contract_and_only_allows_frozen_differences():
    service = object.__new__(DomainConsolidationV2Service)
    protocol = {
        "semantic_contract_hash": "semantic", "node_synthesis_prompt_version": "node",
        "node_schema_hash": "node-schema", "routing_prompt_version": "routing",
        "routing_schema_hash": "routing-schema", "evidence_contract_version": "evidence",
        "providers": {"taxonomy_global": {"model": "deepseek-v4-pro", "thinking_enabled": True}},
        "local_batch_size": 24, "routing_batch_size": 12, "gate_version": "gate",
    }
    gate = {"status": "PASS_WITH_CHANGES", "blocking": [], "metrics": {"coverage": 1}}
    plan = service._replication_plan(protocol, gate)
    assert plan["future_seed"] == 404 and plan["replication_eligible"] is True
    assert set(plan["allowed_differences"]) == {"seed", "card_order", "local_batch_members", "candidate_order", "routing_batch_members", "run_id", "timestamps"}
    gate["status"] = "FAIL"
    assert service._replication_plan(protocol, gate)["replication_eligible"] is False
