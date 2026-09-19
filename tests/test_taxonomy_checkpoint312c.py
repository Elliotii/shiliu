from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from shiliu.taxonomy.checkpoint312c import (
    TAIL_IDS,
    TailCompletionOutput,
    adapt_domain_contract,
    extract_complete_array,
    extract_complete_objects_from_partial_array,
    merge_candidate_decisions,
    precheck_finish_reason,
    validate_hierarchy_v2,
    validate_tail_output,
    build_quality_gate,
)


def _tail(**overrides):
    items = []
    for value in TAIL_IDS:
        item = {
            "candidate_id": value,
            "action": "remove_as_unsupported",
            "target_id": None,
            "reason": "单条证据不足以成立稳定领域",
            "definition_comparison": "与冻结节点边界不同",
            "evidence_assessment": "只有一条内容",
            "granularity_assessment": "更适合作为窄主题",
            "confidence": "medium",
        }
        item.update(overrides.get(value, {}))
        items.append(item)
    return {"candidate_decisions": items}


def _domains():
    return [
        {
            "id": "d_01", "name": "软件工程", "definition": "软件系统工程方法",
            "includes": ["一", "二", "三", "四", "五", "六"], "excludes": ["硬件"],
            "supporting_ids": [f"C{i:03d}" for i in range(1, 36)],
            "representative_ids": ["C001"],
            "children": [{
                "id": "d_01_01", "name": "工程实践", "definition": "工程实践方法",
                "includes": ["开发"], "excludes": ["硬件"], "supporting_ids": ["C036"],
                "representative_ids": ["C036"], "parent_id": "d_01",
            }],
        }
    ]


def _candidates():
    return [
        {"candidate_id": "nc_001", "supporting_ids": ["C001"], "representative_ids": ["C001"]},
        {"candidate_id": "nc_002", "supporting_ids": ["C002"], "representative_ids": ["C002"]},
    ]


def test_tail_requires_exact_order_and_coverage():
    valid = TailCompletionOutput.model_validate(_tail())
    assert [x.candidate_id for x in valid.candidate_decisions] == list(TAIL_IDS)
    for bad in (_tail(), _tail(), _tail()):
        pass
    missing = _tail(); missing["candidate_decisions"].pop()
    duplicate = _tail(); duplicate["candidate_decisions"][-1]["candidate_id"] = "nc_039"
    extra = _tail(); extra["candidate_decisions"].append(extra["candidate_decisions"][-1])
    for value in (missing, duplicate, extra):
        with pytest.raises(ValidationError):
            TailCompletionOutput.model_validate(value)
    frozen_domain_injection = _tail()
    frozen_domain_injection["domains"] = []
    with pytest.raises(ValidationError):
        TailCompletionOutput.model_validate(frozen_domain_injection)


def test_finish_reason_length_is_hard_failure():
    with pytest.raises(Exception):
        precheck_finish_reason("length", stage="Tail Completion")
    precheck_finish_reason("stop", stage="Tail Completion")


def test_tail_action_target_rules_and_legal_target():
    with pytest.raises(ValidationError):
        TailCompletionOutput.model_validate(_tail(nc_037={"action": "merge_into_existing_domain"}))
    with pytest.raises(ValidationError):
        TailCompletionOutput.model_validate(_tail(nc_037={"action": "unresolved_requires_new_domain", "target_id": "d_01"}))
    value = TailCompletionOutput.model_validate(_tail(nc_037={"action": "downgrade_to_topic", "target_id": "d_missing"}))
    with pytest.raises(Exception):
        validate_tail_output(value, {"d_01"})


def test_extract_complete_domains_from_truncated_response():
    raw = '{"domains":[{"id":"d_01","name":"x"}],"candidate_decisions":[{"candidate_id":"nc_001"},{"candidate_id":"nc_037","action'
    assert extract_complete_array(raw, "domains") == [{"id": "d_01", "name": "x"}]
    with pytest.raises(ValueError):
        extract_complete_array(raw, "candidate_decisions")
    assert extract_complete_objects_from_partial_array(raw, "candidate_decisions") == [
        {"candidate_id": "nc_001"}
    ]


def test_merge_36_plus_4_preserves_original_fields_and_lineage():
    original = [{"candidate_id": f"nc_{i:03d}", "action": "kept", "target_id": "d_01", "reason": str(i)} for i in range(1, 37)]
    result = merge_candidate_decisions(original, TailCompletionOutput.model_validate(_tail()), original_response_hash="old", tail_response_hash="new", repaired=False)
    assert len(result) == 40
    assert [{k: v for k, v in item.items() if not k.startswith("decision_") and not k.startswith("source_")} for item in result[:36]] == original
    assert {x["decision_source"] for x in result[:36]} == {"original_consolidation"}
    assert {x["decision_source"] for x in result[36:]} == {"tail_completion"}


def test_contract_keeps_canonical_and_all_35_evidence_without_assignment_fields():
    decisions = [
        {"candidate_id": "nc_001", "action": "kept", "target_id": "d_01"},
        {"candidate_id": "nc_002", "action": "kept", "target_id": "d_01_01"},
    ]
    contract = adapt_domain_contract(source_run_id=22, domains=_domains(), decisions=decisions, candidates=_candidates())
    parent = contract["nodes"][0]
    assert len(parent["canonical_includes"]) == 6
    assert len(parent["display_includes"]) == 5
    assert len(parent["model_selected_evidence_ids"]) == 35
    assert parent["representative_ids"][0] == "C001"
    assert parent["source_candidate_ids"] == ["nc_001", "nc_002"]
    assert parent["contract_version"] == "domain-evidence-contract-v2"
    assert parent["evidence_stats"]["model_selected_evidence_count"] == 35
    assert not ({"direct_assigned_ids", "descendant_assigned_ids", "scope_assigned_ids"} & parent.keys())


def test_hierarchy_zero_overlap_is_warning_not_blocking():
    contract = adapt_domain_contract(
        source_run_id=22,
        domains=_domains(),
        decisions=[{"candidate_id": "nc_001", "action": "kept", "target_id": "d_01"}, {"candidate_id": "nc_002", "action": "kept", "target_id": "d_01_01"}],
        candidates=_candidates(),
    )
    contract["nodes"][1]["evidence_pool_ids"] = ["C999"]
    contract["nodes"][1]["model_selected_evidence_ids"] = ["C999"]
    result = validate_hierarchy_v2(contract)
    assert not result["blocking"]
    assert "parent_child_evidence_zero_overlap" in {x["code"] for x in result["warnings"]}


def test_hierarchy_parent_exclusion_and_cycles_block():
    contract = adapt_domain_contract(
        source_run_id=22,
        domains=_domains(),
        decisions=[{"candidate_id": "nc_001", "action": "kept", "target_id": "d_01"}, {"candidate_id": "nc_002", "action": "kept", "target_id": "d_01_01"}],
        candidates=_candidates(),
    )
    contract["nodes"][0]["canonical_excludes"] = ["工程实践"]
    result = validate_hierarchy_v2(contract)
    assert "parent_excludes_child" in {x["code"] for x in result["blocking"]}
    contract["nodes"][0]["parent_id"] = "d_01_01"
    result = validate_hierarchy_v2(contract)
    assert "cycle" in {x["code"] for x in result["blocking"]}


def test_contract_is_deterministic_and_same_adapter_for_runs():
    args = dict(domains=_domains(), decisions=[{"candidate_id": "nc_001", "action": "kept", "target_id": "d_01"}, {"candidate_id": "nc_002", "action": "kept", "target_id": "d_01_01"}], candidates=_candidates())
    a = adapt_domain_contract(source_run_id=12, **args)
    b = adapt_domain_contract(source_run_id=22, **args)
    assert a["version"] == b["version"] == "domain-evidence-contract-v2"
    assert a["adapter_version"] == b["adapter_version"]
    assert a["derived_output_hash"] != b["derived_output_hash"]
    a.pop("derived_output_hash")
    b.pop("derived_output_hash")
    a["source_run_id"] = b["source_run_id"]
    for left, right in zip(a["nodes"], b["nodes"], strict=True):
        left["source_run_id"] = right["source_run_id"]
    assert json.dumps(a, ensure_ascii=False, sort_keys=True) == json.dumps(b, ensure_ascii=False, sort_keys=True)


def test_gate_blocks_adapter_version_and_evidence_stats_regression():
    args = dict(
        domains=_domains(),
        decisions=[
            {"candidate_id": "nc_001", "action": "kept", "target_id": "d_01"},
            {"candidate_id": "nc_002", "action": "kept", "target_id": "d_01_01"},
        ],
        candidates=_candidates(),
        lineage={
            "source_stage_id": "stage", "source_attempt": "attempt-01",
            "raw_response_hash": "raw", "candidate_table_hash": "table",
        },
    )
    a = adapt_domain_contract(source_run_id=12, **args)
    b = adapt_domain_contract(source_run_id=22, **args)
    a["adapter_version"] = "wrong"
    b["nodes"][0]["evidence_stats"]["evidence_pool_count"] = 999
    # Preserve valid derived hashes so the two specific contract checks are exercised.
    from shiliu.taxonomy.controlled_facets import _stable_hash
    for value in (a, b):
        value["derived_output_hash"] = _stable_hash(
            {key: item for key, item in value.items() if key != "derived_output_hash"}
        )
    result = build_quality_gate(
        tail_audit={}, complete_decisions=[{"candidate_id": f"nc_{i:03d}"} for i in range(1, 41)],
        run_a=a, run_b=b,
        hierarchy_a={"blocking": [], "warnings": []},
        hierarchy_b={"blocking": [], "warnings": []}, historical_tree_unchanged=True,
    )
    assert result["status"] == "FAIL"
    assert {item["code"] for item in result["blocking"]} >= {
        "adapter_version_mismatch", "node_contract_fields_missing"
    }
