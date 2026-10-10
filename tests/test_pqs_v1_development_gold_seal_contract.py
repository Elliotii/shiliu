from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CYCLE = ROOT / "research/v3_5/product_query_set_v1/gold_construction_v1/development_cycle"
SOURCE = CYCLE / "reviewed_gold_candidate"
OUT = ROOT / "research/v3_5/product_query_set_v1/gold_construction_v1/development_seal_v1"
SEALED = OUT / "sealed"
sys.path.insert(0, str(ROOT / "scripts"))
from validate_development_gold_cycle import validate_replay  # noqa: E402
from validate_development_gold_seal_v1 import validate_seal  # noqa: E402
from validate_product_gold_protocol_v1 import validate_three_layer  # noqa: E402


SOURCE_TO_SEALED = {
    "product_retrieval_gold.development.reviewed.jsonl":
        "product_retrieval_gold.development.v1.sealed.jsonl",
    "product_evidence_gold.development.reviewed.jsonl":
        "product_evidence_gold.development.v1.sealed.jsonl",
    "product_sufficiency_gold.development.reviewed.jsonl":
        "product_sufficiency_gold.development.v1.sealed.jsonl",
    "reviewed_case_status.jsonl":
        "reviewed_case_status.development.v1.sealed.jsonl",
}
EXPECTED_SOURCE_HASHES = {
    "product_retrieval_gold.development.reviewed.jsonl":
        "b34188c269bf3a2410f8602fdb7d72908a96c822ac3b8f675d4f4c2b72b45679",
    "product_evidence_gold.development.reviewed.jsonl":
        "b259a1b225a48558f5d1a6c4cb4909ea413e86116a1564b3fa724632ae88efc1",
    "product_sufficiency_gold.development.reviewed.jsonl":
        "11196158746bb2c12e457fcb36b87a1621e79dca0b2f628a4870ca5ec6c5de92",
    "reviewed_case_status.jsonl":
        "9ba38a1f8cf636ebb9e80219cd85a41003743cb11f370a24d3946534378c6352",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def j(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def jl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def source_layers() -> tuple[list[dict], list[dict], list[dict]]:
    return (
        jl(SOURCE / "product_retrieval_gold.development.reviewed.jsonl"),
        jl(SOURCE / "product_evidence_gold.development.reviewed.jsonl"),
        jl(SOURCE / "product_sufficiency_gold.development.reviewed.jsonl"),
    )


def test_development_gold_seal_ledger_hash_matches() -> None:
    assert sha(OUT / "PQS_V1_DEVELOPMENT_GOLD_SEAL_DECISION_LEDGER.json") == (
        "6caeeb1898e9aef7ed401fba4d5b0285b4c84834b6e5a2416527b74aa9352651"
    )


def test_source_candidate_hashes_match() -> None:
    assert {name: sha(SOURCE / name) for name in EXPECTED_SOURCE_HASHES} == (
        EXPECTED_SOURCE_HASHES
    )


def test_exactly_14_query_ids_in_all_layers() -> None:
    status = jl(SOURCE / "reviewed_case_status.jsonl")
    assert all(len(rows) == 14 for rows in (*source_layers(), status))
    assert all(len({row["query_id"] for row in rows}) == 14 for rows in (*source_layers(), status))


def test_query_id_sets_identical() -> None:
    status = jl(SOURCE / "reviewed_case_status.jsonl")
    sets = [{row["query_id"] for row in rows} for rows in (*source_layers(), status)]
    assert all(value == sets[0] for value in sets[1:])


def test_query_ids_match_development_split() -> None:
    development = jl(
        ROOT
        / "research/v3_5/product_query_set_v1/split_v1/"
        "product_query_development_v1.locked.jsonl"
    )
    actual = {row["query_id"] for row in source_layers()[0]}
    assert actual == {row["query_id"] for row in development}


def test_no_frozen_query_present() -> None:
    development = jl(
        ROOT
        / "research/v3_5/product_query_set_v1/split_v1/"
        "product_query_development_v1.locked.jsonl"
    )
    allowed = {row["query_id"] for row in development}
    assert all(
        {row["query_id"] for row in rows} <= allowed
        for rows in (*source_layers(), jl(SOURCE / "reviewed_case_status.jsonl"))
    )


def test_review_status_is_13_agree_1_reconciled() -> None:
    statuses = jl(SOURCE / "reviewed_case_status.jsonl")
    assert sum(row["resolution"] == "agree" for row in statuses) == 13
    assert sum(row["resolution"] == "agree_reconciled" for row in statuses) == 1


def test_q017_is_only_reconciled_case() -> None:
    reconciled = [
        row for row in jl(SOURCE / "reviewed_case_status.jsonl")
        if row["resolution"] == "agree_reconciled"
    ]
    assert [(row["query_id"], row["reconciliation_rounds_used"]) for row in reconciled] == [
        ("PQS_V1_Q017", 1)
    ]


def test_no_pending_or_blocked_case() -> None:
    statuses = jl(SOURCE / "reviewed_case_status.jsonl")
    assert not any(row["user_adjudication_required"] for row in statuses)
    assert {row["resolution"] for row in statuses} == {"agree", "agree_reconciled"}


def test_all_three_gold_layers_validate() -> None:
    layers = [{row["query_id"]: row for row in values} for values in source_layers()]
    for query_id in sorted(layers[0]):
        validate_three_layer(*(layer[query_id] for layer in layers))


def test_cross_object_validation_passes() -> None:
    assert validate_seal()["query_count"] == 14


def test_exactly_41_evidence_spans_replay() -> None:
    assert sum(validate_replay(row) for row in source_layers()[1]) == 41


def test_navigation_sources_not_used_as_evidence() -> None:
    assert all(
        span["source_type"] in {"official_subtitle", "asr_transcript"}
        for row in source_layers()[1]
        for span in row["span_registry"]
    )


def test_no_downstream_failure_codes_in_gold() -> None:
    prefixes = ("RET_", "BLD_", "SEL_", "GATE_", "JDG_", "SRC_")
    assert not any(
        code.startswith(prefixes)
        for rows in source_layers()
        for row in rows
        for code in row["reason_codes"]
    )


def test_sealed_files_byte_identical_to_source() -> None:
    assert all(
        (SOURCE / source).read_bytes() == (SEALED / sealed).read_bytes()
        for source, sealed in SOURCE_TO_SEALED.items()
    )


def test_sealed_hashes_match_source_hashes() -> None:
    assert all(
        sha(SOURCE / source) == sha(SEALED / sealed)
        for source, sealed in SOURCE_TO_SEALED.items()
    )


def test_source_candidate_files_unchanged() -> None:
    assert all(sha(SOURCE / name) == expected for name, expected in EXPECTED_SOURCE_HASHES.items())


def test_seal_manifest_audit_hashes_match() -> None:
    manifest = j(OUT / "development_gold_v1.manifest.json")
    assert all(sha(OUT / path) == expected for path, expected in manifest["artifact_hashes"].items())
    assert all(
        sha(OUT / row["path"]) == row["sha256"]
        for row in jl(OUT / "development_gold_v1.file_hash_manifest.jsonl")
    )


def test_no_semantic_modification() -> None:
    audit = j(OUT / "development_gold_v1.audit.json")
    assert audit["immutability"]["semantic_fields_changed"] == 0
    assert audit["immutability"]["sealed_files_byte_identical"]


def test_no_frozen_access_or_product_pipeline_calls() -> None:
    scope = j(OUT / "development_gold_v1.audit.json")["scope"]
    assert not scope["frozen_packet_or_gold_opened"]
    assert scope["product_pipeline_calls"] == 0
    assert not scope["product_prediction_read"]
    assert not scope["existing_external_gold_read"]


def test_no_frozen_cycle_or_p8_started() -> None:
    decision = j(OUT / "development_gold_v1.execution_decision.json")
    assert not decision["frozen_gold_cycle_authorized"]
    assert not decision["p8_authorized"]
    scope = j(OUT / "development_gold_v1.audit.json")["scope"]
    assert not scope["frozen_cycle_started"]
    assert not scope["p8_started"]


def test_upstream_assets_unchanged() -> None:
    assert sha(CYCLE / "DEVELOPMENT_GOLD_CYCLE_REPORT.md") == (
        "5965d7d728b5f3d98b1b357e0bd79d3ae9394ab9bb94636ce569a5ad8a0e1a62"
    )
    assert sha(
        ROOT
        / "research/v3_5/product_query_set_v1/split_v1/"
        "product_query_development_v1.locked.jsonl"
    ) == "e68d6bb405bafadb56c5333834d72c8155a7a310ca2e20341df4f412488a8935"
