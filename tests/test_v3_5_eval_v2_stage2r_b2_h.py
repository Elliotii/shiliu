from __future__ import annotations

import json

from shiliu.eval_v3_5.eval_v2.stage2r_b2_h_package import (
    AUDIT_ROOT,
    BUNDLE,
    CASE_IDS,
    TEMPLATE,
    WEBGPT_PROMPT,
    sha256_file,
)


def test_b2_h_package_is_exact_two_case_self_contained_bundle() -> None:
    bundle = BUNDLE.read_text(encoding="utf-8")
    assert [bundle.count(case_id) > 0 for case_id in CASE_IDS] == [True, True]
    assert bundle.count('"segment_id":') == 374
    assert "Appendix A — Complete Shared Raw Transcript" in bundle
    assert "BV1o87764Ebs_seg_000001" in bundle
    assert "BV1o87764Ebs_seg_000374" in bundle


def test_b2_h_template_is_exactly_two_blank_jsonl_records() -> None:
    rows = [json.loads(line) for line in TEMPLATE.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {"case_id": "V2C_B2P00001", "human_action": "", "adjudication_reason": ""},
        {"case_id": "V2C_B2P00002", "human_action": "", "adjudication_reason": ""},
    ]


def test_b2_h_prompt_requires_only_bundle_and_two_line_jsonl() -> None:
    prompt = WEBGPT_PROMPT.read_text(encoding="utf-8")
    assert "只可以依据" in prompt
    assert "最终响应只能输出两行简化 JSONL" in prompt
    assert "用户仍是最终人工决策者" in prompt
    assert "reject_both" in prompt


def test_b2_h_integrity_hashes_and_zero_model_calls() -> None:
    audit = json.loads((AUDIT_ROOT / "package_integrity.audit.json").read_text(encoding="utf-8"))
    assert audit["case_count"] == 2
    assert audit["case_ids"] == list(CASE_IDS)
    assert audit["source_assets_unchanged"] is True
    assert audit["model_calls"] == audit["reviewer_calls"] == 0
    assert audit["agreement_rerun"] is False
    assert audit["human_decision_prefilled"] is False
    assert audit["final_gold_created"] is False
    assert audit["stage2r_c_entered"] is False
    assert sha256_file(BUNDLE) == audit["bundle_sha256"]
    assert sha256_file(WEBGPT_PROMPT) == audit["webgpt_prompt_sha256"]
    assert sha256_file(TEMPLATE) == audit["template_sha256"]
