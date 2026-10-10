from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/product_query_set_v1/gold_construction_v1"
P6 = ROOT / "research/v3_5/product_query_set_v1/gold_protocol_v1"
sys.path.insert(0, str(ROOT / "scripts"))
from validate_p7a_gold_packet import (  # noqa: E402
    EXPECTED_BATCHES,
    validate_packet_export,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def batch_paths() -> list[Path]:
    return sorted((OUT / "development/batches").iterdir()) + sorted(
        (OUT / "frozen_guarded/batches").iterdir()
    )


def test_p7a_decision_ledger_hash_matches() -> None:
    assert sha(OUT / "PQS_V1_P7A_PACKET_EXPORT_DECISION_LEDGER.json") == (
        "81b420d739641e7b6020cd6519022d4c24a83abf02a6620149d2533fefbb59f7"
    )


def test_p4_p5_p6_input_hashes_match() -> None:
    manifest = read_json(OUT / "p7a_packet_export.manifest.json")
    for relative, expected in manifest["source_hashes"].items():
        assert sha(ROOT / relative) == expected


def test_all_24_queries_packetized_exactly_once() -> None:
    ids = [
        query_id
        for split in EXPECTED_BATCHES.values()
        for query_ids in split.values()
        for query_id in query_ids
    ]
    assert len(ids) == 24
    assert set(Counter(ids).values()) == {1}


def test_development_has_14_queries_in_7_batches() -> None:
    manifest = read_json(OUT / "development/batch_manifest.json")
    assert manifest["query_count"] == 14
    assert manifest["batch_count"] == 7
    assert len(list((OUT / "development/batches").iterdir())) == 7


def test_frozen_has_10_queries_in_5_batches() -> None:
    manifest = read_json(OUT / "frozen_guarded/batch_manifest.json")
    assert manifest["query_count"] == 10
    assert manifest["batch_count"] == 5
    assert len(list((OUT / "frozen_guarded/batches").iterdir())) == 5


def test_batch_assignments_match_ledger() -> None:
    ledger = read_json(OUT / "PQS_V1_P7A_PACKET_EXPORT_DECISION_LEDGER.json")
    assert read_json(OUT / "development/batch_manifest.json")["batch_assignments"] == ledger[
        "development_batches"
    ]
    assert read_json(OUT / "frozen_guarded/batch_manifest.json")["batch_assignments"] == ledger[
        "frozen_batches"
    ]


def test_locked_query_records_unchanged() -> None:
    canonical = {
        row["query_id"]: row
        for row in read_jsonl(
            ROOT / "research/v3_5/product_query_set_v1/freeze/product_query_set_v1.locked.jsonl"
        )
    }
    packet_records = [
        row
        for batch in batch_paths()
        for row in read_jsonl(batch / "query_records.locked.jsonl")
    ]
    assert len(packet_records) == 24
    assert all(row == canonical[row["query_id"]] for row in packet_records)


def test_neutral_library_index_has_no_query_scores_or_labels() -> None:
    rows = read_jsonl(OUT / "shared/neutral_library_navigation_index.jsonl")
    forbidden = {
        "query_id",
        "query_score",
        "recommended_query",
        "candidate_video",
        "target_video",
        "relevant",
        "negative",
        "system_rank",
        "system_score",
    }
    assert len(rows) == 147
    assert all(not forbidden.intersection(row) for row in rows)


def test_transcript_catalog_has_identity_and_hashes() -> None:
    rows = read_jsonl(OUT / "shared/authoritative_transcript_identity_catalog.jsonl")
    required = {
        "video_id",
        "source_type",
        "source_language",
        "source_path",
        "source_file_sha256",
        "source_version",
        "timeline_run_id",
        "timeline_run_ids",
        "segment_identity_version",
        "segment_count",
        "timeline_replayable",
    }
    assert len(rows) == 131
    assert all(required <= row.keys() for row in rows)
    assert all(sha(Path(row["source_path"])) == row["source_file_sha256"] for row in rows)


def test_navigation_sources_marked_navigation_only() -> None:
    rows = read_jsonl(OUT / "shared/neutral_library_navigation_index.jsonl")
    assert all(row["evidence_authority"] == "navigation_only" for row in rows)


def test_templates_contain_no_prefilled_gold_semantics() -> None:
    for batch in batch_paths():
        for row in read_jsonl(batch / "retrieval_gold.template.jsonl"):
            record = row["record"]
            assert row["annotation_status"] == "not_started"
            assert not record["acceptable_video_ids"]
            assert not record["hard_negative_video_ids"]
        for row in read_jsonl(batch / "evidence_gold.template.jsonl"):
            record = row["record"]
            assert not record["required_aspects"]
            assert not record["span_registry"]
            assert not record["acceptable_evidence_groups"]
        for row in read_jsonl(batch / "sufficiency_gold.template.jsonl"):
            record = row["record"]
            assert record["status"] == "__PENDING__"
            assert not record["supported_aspects"]
            assert not record["missing_aspects"]


def test_templates_reference_correct_p6_schemas() -> None:
    refs = {
        "retrieval_gold.template.jsonl": "product_retrieval_gold.schema.json",
        "evidence_gold.template.jsonl": "product_evidence_gold.schema.json",
        "sufficiency_gold.template.jsonl": "product_sufficiency_gold.schema.json",
    }
    for batch in batch_paths():
        for name, schema in refs.items():
            rows = read_jsonl(batch / name)
            required = set(read_json(P6 / schema)["required"])
            assert all(set(row["record"]) == required for row in rows)
            assert all(row["schema_ref"].endswith(schema) for row in rows)


def test_prompts_enforce_independent_annotation_and_review() -> None:
    annotator = (OUT / "prompts/DEVELOPMENT_INITIAL_ANNOTATOR_PROMPT.md").read_text()
    reviewer = (OUT / "prompts/DEVELOPMENT_INDEPENDENT_REVIEWER_PROMPT.md").read_text()
    assert "new independent Session" in annotator
    assert "different independent Session" in reviewer
    assert "before viewing the Initial Annotation" in " ".join(reviewer.split())


def test_user_only_handles_disagreements_and_high_risk_cases() -> None:
    for name in (
        "DEVELOPMENT_USER_ADJUDICATION_PROMPT.md",
        "FROZEN_USER_ADJUDICATION_PROMPT.md",
    ):
        text = (OUT / "prompts" / name).read_text()
        assert "disagreement" in text
        assert "high-risk" in text
        assert "from scratch" in text


def test_frozen_guard_forbids_gold_content_return_to_v3_5_b() -> None:
    guard = read_json(OUT / "frozen_guarded/FROZEN_PACKET_ACCESS_GUARD.json")
    assert guard["v3_5_b_content_visibility"]["gold_content"] == "forbidden"
    assert guard["v3_5_b_content_visibility"]["annotation_decisions"] == "forbidden"


def test_frozen_completion_template_contains_only_allowed_metadata() -> None:
    guard = read_json(OUT / "frozen_guarded/FROZEN_PACKET_ACCESS_GUARD.json")
    template = read_json(OUT / "prompts/FROZEN_COMPLETION_ONLY_RESPONSE_TEMPLATE.md")
    assert set(template) == set(guard["completion_response_to_v3_5_b"]["allowed_fields"])
    assert not set(template).intersection(
        guard["completion_response_to_v3_5_b"]["forbidden_fields"]
    )


def test_packet_exporter_does_not_annotate() -> None:
    for batch in batch_paths():
        assignment = read_json(batch / "annotation_assignment.json")
        assert not assignment["packet_exporter_may_annotate"]
        assert not assignment["packet_exporter_may_review"]
        assert not assignment["same_session_annotation_and_review_allowed"]


def test_no_existing_gold_or_prediction_access() -> None:
    audit = read_json(OUT / "p7a_packet_export.audit.json")
    assert audit["neutrality"]["existing_gold_in_packets"] == 0
    assert audit["neutrality"]["system_results_in_packets"] == 0


def test_no_product_pipeline_calls() -> None:
    audit = read_json(OUT / "p7a_packet_export.audit.json")
    assert audit["scope"]["product_pipeline_calls"] == 0


def test_no_real_gold_files_created() -> None:
    assert read_json(OUT / "p7a_packet_export.audit.json")["scope"]["real_gold_created"] is False
    for path in OUT.rglob("*"):
        if "development_cycle" in path.relative_to(OUT).parts:
            continue
        name = path.name.lower()
        assert not (
            path.is_file()
            and ".template." not in name
            and (
                name.startswith("retrieval_gold.")
                or name.startswith("evidence_gold.")
                or name.startswith("sufficiency_gold.")
            )
        )


def test_p8_not_started() -> None:
    audit = read_json(OUT / "p7a_packet_export.audit.json")
    decision = read_json(OUT / "p7a_packet_export.execution_decision.json")
    assert audit["scope"]["p8_started"] is False
    assert decision["p8_authorized"] is False


def test_p3_p4_p5_p6_assets_unchanged() -> None:
    expected = {
        "research/v3_5/product_query_set_v1/user_validation/pqs_v1_user_validation.audit.json": "0acb8f6b88e5d60579dc03b0808862deff6fccd9611dcaaae79fa12b4622b58e",
        "research/v3_5/product_query_set_v1/freeze/product_query_set_v1.locked.jsonl": "35d33dcf4dd77f12cad4e0c118f2c2f2e371a3019320906a3d2134bb933dd59c",
        "research/v3_5/product_query_set_v1/split_v1/product_query_development_v1.locked.jsonl": "e68d6bb405bafadb56c5333834d72c8155a7a310ca2e20341df4f412488a8935",
        "research/v3_5/product_query_set_v1/gold_protocol_v1/PRODUCT_QUERY_GOLD_PROTOCOL_V1.md": "1da2fd575a091ac5adff7e823080b8d90564fbf912abdb3cc5ee409599886e06",
    }
    assert all(sha(ROOT / relative) == expected_hash for relative, expected_hash in expected.items())


def test_full_p7a_mechanical_validator_passes() -> None:
    validate_packet_export()
