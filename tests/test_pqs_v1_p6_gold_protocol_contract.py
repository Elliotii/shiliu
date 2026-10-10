from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/product_query_set_v1/gold_protocol_v1"
FIXTURES = OUT / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))
from validate_product_gold_protocol_v1 import (  # noqa: E402
    GoldProtocolValidationError,
    validate_evidence,
    validate_retrieval,
    validate_sufficiency,
    validate_three_layer,
)


def load(relative: str) -> dict:
    return json.loads((OUT / relative).read_text(encoding="utf-8"))


def fixture(name: str) -> dict:
    return load(f"fixtures/{name}")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_p6_decision_ledger_hash_matches() -> None:
    assert sha(OUT / "PQS_V1_P6_GOLD_PROTOCOL_DECISION_LEDGER.json") == (
        "4449faea22163dfd6b8d347a72bb3e7d7b48e665a62c87143179e5d60a81a720"
    )


def test_p4_p5_input_hashes_match() -> None:
    manifest = load("product_gold_protocol_v1.manifest.json")
    assert manifest["source_query_set_hashes"] == {
        "canonical_content_sha256": "fadf21c1992d848f2904192af479f6720a059c9aeb772ccfc4cee3b220942825",
        "locked_jsonl_sha256": "35d33dcf4dd77f12cad4e0c118f2c2f2e371a3019320906a3d2134bb933dd59c",
    }
    assert manifest["source_split_hashes"] == {
        "canonical_split_assignment_sha256": "3014e941a385022abf0bef99c6d9f1d0b82b6d5e7a0b2a22d6977189c8f85239",
        "development_jsonl_sha256": "e68d6bb405bafadb56c5333834d72c8155a7a310ca2e20341df4f412488a8935",
        "frozen_jsonl_sha256": "faf962049281cba4c8a035e64068ef91b7cfa9159ea438cfe33052a225add44f",
    }


def test_three_gold_schemas_exist_and_are_distinct() -> None:
    names = [
        "product_retrieval_gold.schema.json",
        "product_evidence_gold.schema.json",
        "product_sufficiency_gold.schema.json",
    ]
    schemas = [load(name) for name in names]
    assert all((OUT / name).is_file() for name in names)
    assert len({schema["$id"] for schema in schemas}) == 3
    assert len({sha(OUT / name) for name in names}) == 3


def test_retrieval_exhaustive_is_const_false() -> None:
    schema = load("product_retrieval_gold.schema.json")
    assert schema["properties"]["exhaustive"] == {"const": False}
    validate_retrieval(fixture("synthetic_retrieval_gold.valid.json"))


def test_retrieval_known_relevant_subset_of_acceptable() -> None:
    record = fixture("synthetic_retrieval_gold.valid.json")
    record["known_relevant_video_ids"].append("SYNTH_UNKNOWN")
    with pytest.raises(GoldProtocolValidationError):
        validate_retrieval(record)


def test_retrieval_hard_negatives_disjoint_from_positives() -> None:
    record = fixture("synthetic_retrieval_gold.valid.json")
    record["hard_negative_video_ids"].append("SYNTH_VIDEO_A")
    with pytest.raises(GoldProtocolValidationError):
        validate_retrieval(record)


def test_unjudged_is_not_automatic_negative() -> None:
    schema = load("product_retrieval_gold.schema.json")
    assert schema["properties"]["unjudged_outside_pool_is_negative"] == {"const": False}


def test_retrieval_schema_contains_no_evidence_or_sufficiency_fields() -> None:
    properties = set(load("product_retrieval_gold.schema.json")["properties"])
    assert properties.isdisjoint({"required_aspects", "evidence_spans", "acceptable_evidence_groups", "status", "sufficiency_status"})


def test_evidence_authority_sources_are_transcript_only() -> None:
    schema = load("product_evidence_gold.schema.json")
    span = schema["properties"]["span_registry"]["items"]
    assert span["properties"]["source_type"]["enum"] == ["official_subtitle", "asr_transcript"]


def test_navigation_sources_cannot_be_gold_evidence() -> None:
    record = fixture("synthetic_evidence_gold.valid.json")
    record["span_registry"][0]["source_type"] = "ai_summary"
    with pytest.raises(GoldProtocolValidationError):
        validate_evidence(record)


def test_evidence_groups_support_or_between_groups() -> None:
    schema = load("product_evidence_gold.schema.json")
    assert schema["properties"]["acceptable_evidence_groups_logic"] == {"const": "OR"}


def test_required_spans_support_and_within_group() -> None:
    schema = load("product_evidence_gold.schema.json")
    group = schema["properties"]["acceptable_evidence_groups"]["items"]
    assert group["properties"]["required_span_sets_within_group"] == {"const": "AND"}


def test_multi_video_evidence_group_is_supported() -> None:
    record = fixture("synthetic_evidence_gold.valid.json")
    group = record["acceptable_evidence_groups"][0]
    used = {
        span["video_id"]
        for span in record["span_registry"]
        if any(span["span_id"] in item["required_span_ids"] for item in group["required_span_sets"])
    }
    assert len(used) == 2
    validate_evidence(record)


def test_partial_aspect_evidence_is_supported() -> None:
    record = fixture("synthetic_evidence_gold.valid.json")
    record["acceptable_evidence_groups"] = []
    validate_evidence(record)
    assert record["aspect_evidence_options"]


def test_span_identity_fields_are_required() -> None:
    schema = load("product_evidence_gold.schema.json")
    required = set(schema["properties"]["span_registry"]["items"]["required"])
    assert {
        "span_id", "video_id", "segment_ids", "start_time", "end_time",
        "quote_text", "source_language", "source_type", "source_version",
        "timeline_run_id", "segment_identity_version", "source_quality_flag",
        "translated_gloss",
    } <= required


def test_optional_context_cannot_replace_required_span() -> None:
    record = fixture("synthetic_evidence_gold.valid.json")
    record["optional_context_spans"].append("SYNTH_SPAN_A1")
    with pytest.raises(GoldProtocolValidationError):
        validate_evidence(record)


def test_evidence_schema_contains_no_sufficiency_or_failure_fields() -> None:
    properties = set(load("product_evidence_gold.schema.json")["properties"])
    assert properties.isdisjoint({"status", "sufficiency_status", "system_prediction", "builder_miss", "selector_miss", "expected_failure"})


def test_sufficiency_status_enum_is_exact() -> None:
    schema = load("product_sufficiency_gold.schema.json")
    assert schema["properties"]["status"]["enum"] == ["sufficient", "partial", "insufficient", "unverifiable"]


def test_sufficient_requires_all_material_aspects() -> None:
    record = fixture("synthetic_sufficiency_gold.sufficient.valid.json")
    validate_sufficiency(record)
    record["supported_aspects"].pop()
    with pytest.raises(GoldProtocolValidationError):
        validate_sufficiency(record)


def test_partial_requires_supported_and_missing_material_aspects() -> None:
    record = fixture("synthetic_sufficiency_gold.partial.valid.json")
    validate_sufficiency(record)
    record["missing_aspects"] = []
    with pytest.raises(GoldProtocolValidationError):
        validate_sufficiency(record)


def test_insufficient_requires_reviewable_authority_and_no_material_support() -> None:
    record = fixture("synthetic_sufficiency_gold.insufficient.valid.json")
    validate_sufficiency(record)
    record["authoritative_sources_reviewable"] = False
    with pytest.raises(GoldProtocolValidationError):
        validate_sufficiency(record)


def test_unverifiable_requires_authority_review_failure() -> None:
    record = fixture("synthetic_sufficiency_gold.unverifiable.valid.json")
    validate_sufficiency(record)
    record["authoritative_sources_reviewable"] = True
    with pytest.raises(GoldProtocolValidationError):
        validate_sufficiency(record)


def test_mixed_source_rules() -> None:
    partial = fixture("synthetic_sufficiency_gold.partial.valid.json")
    unverifiable = fixture("synthetic_sufficiency_gold.unverifiable.valid.json")
    insufficient = fixture("synthetic_sufficiency_gold.insufficient.valid.json")
    validate_sufficiency(partial)
    validate_sufficiency(unverifiable)
    validate_sufficiency(insufficient)
    assert partial["supported_aspects"] and partial["missing_aspects"]
    assert not unverifiable["authoritative_sources_reviewable"]
    assert insufficient["authoritative_sources_reviewable"]


def test_sufficiency_schema_contains_no_prediction_fields() -> None:
    properties = set(load("product_sufficiency_gold.schema.json")["properties"])
    assert properties.isdisjoint({"system_prediction", "system_rank", "builder_miss", "selector_miss", "judge_prediction", "expected_failure"})


def test_reason_code_namespaces_are_separate() -> None:
    registry = load("product_gold_reason_code_registry.json")
    gold = set().union(*map(set, registry["gold_state"].values()))
    downstream = set().union(*map(set, registry["downstream_failure_attribution"].values()))
    assert gold.isdisjoint(downstream)


def test_downstream_failure_codes_forbidden_in_gold() -> None:
    record = fixture("synthetic_retrieval_gold.valid.json")
    record["reason_codes"].append("BLD_GOLD_SOURCE_NOT_IN_CANDIDATE_SET")
    with pytest.raises(GoldProtocolValidationError):
        validate_retrieval(record)


def test_review_policy_normal_and_high_risk_routes() -> None:
    policy = load("product_gold_review_policy.json")
    assert policy["normal_case_route"] == ["initial_annotation", "independent_review"]
    assert policy["high_risk_case_route"][-1] == "second_independent_review_or_user_adjudication"
    assert {"partial_status", "unverifiable_status", "multi_video_evidence", "cross_language_evidence"} <= set(policy["high_risk_triggers"])


def test_user_adjudication_is_final_for_unresolved_disagreement() -> None:
    policy = load("product_gold_review_policy.json")
    assert policy["unresolved_disagreement_final_authority"] == "user"


def test_frozen_isolation_forbids_content_visibility_to_v3_5_b() -> None:
    text = (OUT / "product_frozen_evaluation_isolation_contract.md").read_text(encoding="utf-8")
    assert "must not know" in text
    assert "required aspects" in text
    assert "sufficiency status" in text
    assert "creates no Frozen Gold" in text


def test_protocol_versioning_and_amendment_rules() -> None:
    text = (OUT / "PRODUCT_QUERY_GOLD_PROTOCOL_V1.md").read_text(encoding="utf-8")
    assert "versioned amendments" in text
    assert "new protocol version" in text
    assert "never because of system results" in text


def test_only_synthetic_fixtures_created() -> None:
    expected = {
        "synthetic_retrieval_gold.valid.json",
        "synthetic_evidence_gold.valid.json",
        "synthetic_sufficiency_gold.sufficient.valid.json",
        "synthetic_sufficiency_gold.partial.valid.json",
        "synthetic_sufficiency_gold.insufficient.valid.json",
        "synthetic_sufficiency_gold.unverifiable.valid.json",
    }
    assert {path.name for path in FIXTURES.iterdir()} == expected


def test_no_real_query_video_segment_or_transcript_in_fixtures() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in FIXTURES.iterdir())
    assert "PQS_V1_Q" not in text
    assert "SYNTH_QUERY_" in text
    assert "SYNTH_VIDEO_" in text
    assert "SYNTH_SEG_" in text


def test_no_raw_transcript_gold_prediction_or_pipeline_access() -> None:
    audit = load("product_gold_protocol_v1.audit.json")
    assert audit["scope"] == {
        "raw_transcripts_read": False,
        "real_gold_read_or_created": False,
        "target_videos_read": False,
        "system_results_read": False,
        "pipeline_calls": 0,
        "fixtures_are_synthetic_only": True,
    }


def test_no_p7_baseline_f1_or_stage4_assets_created() -> None:
    audit = load("product_gold_protocol_v1.audit.json")
    assert audit["downstream"] == {
        "p7_started": False,
        "product_baseline_started": False,
        "f1a_or_f1b_started": False,
        "stage4_started": False,
    }
    assert not any("p7" in path.name.lower() or "baseline" in path.name.lower() for path in OUT.rglob("*"))


def test_all_synthetic_fixtures_pass_validator() -> None:
    retrieval = fixture("synthetic_retrieval_gold.valid.json")
    evidence = fixture("synthetic_evidence_gold.valid.json")
    validate_three_layer(
        retrieval,
        evidence,
        fixture("synthetic_sufficiency_gold.sufficient.valid.json"),
    )
    for status in ("partial", "insufficient", "unverifiable"):
        validate_sufficiency(fixture(f"synthetic_sufficiency_gold.{status}.valid.json"))


def test_cross_object_validator_rejects_identity_mismatch() -> None:
    retrieval = fixture("synthetic_retrieval_gold.valid.json")
    evidence = fixture("synthetic_evidence_gold.valid.json")
    sufficiency = fixture("synthetic_sufficiency_gold.sufficient.valid.json")
    sufficiency["query_id"] = "SYNTH_QUERY_DIFFERENT"
    with pytest.raises(GoldProtocolValidationError):
        validate_three_layer(retrieval, evidence, sufficiency)
