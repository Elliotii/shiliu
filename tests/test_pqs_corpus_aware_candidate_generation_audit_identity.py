from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/product_query_set_v1/corpus_aware_generation"
METADATA = "/Users/elliot/Documents/Shiliu/videos/BV1o87764Ebs/metadata.json"
REAL_TRANSCRIPT = "/Users/elliot/Documents/Shiliu/videos/BV1atjU6KEJF/subtitle-raw.txt"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_pqc_004_metadata_identity_and_derived_transcript_count() -> None:
    basis = {
        row["candidate_id"]: row
        for row in load_jsonl(OUT / "product_query_candidates.internal_basis.jsonl")
    }
    audit = json.loads(
        (OUT / "corpus_aware_candidate_generation.audit.json").read_text(encoding="utf-8")
    )
    report = (OUT / "corpus_aware_candidate_generation_report.md").read_text(encoding="utf-8")

    pqc_004 = basis["PQC_004"]
    metadata_basis = next(
        item for item in pqc_004["internal_source_basis"] if item["file_or_table"] == METADATA
    )
    assert metadata_basis["asset_type"] == "metadata"
    assert metadata_basis["transcript_checked"] is False

    # PQC_004 still has a genuine transcript basis from a different video.
    assert REAL_TRANSCRIPT in {
        item["file_or_table"]
        for item in pqc_004["internal_source_basis"]
        if item["asset_type"] == "transcript" and item["transcript_checked"]
    }
    assert "transcript" in pqc_004["source_types_consulted"]
    assert pqc_004["transcript_inspection_used"] is True

    transcript_paths = audit["transcript_files_or_items_inspected"]
    assert METADATA not in transcript_paths
    assert len(transcript_paths) == 16
    metadata_audit = next(
        item for item in audit["read_audit"] if item["file_or_table"] == METADATA
    )
    assert metadata_audit["source_type"] == "canonical_video_metadata_container"
    assert metadata_audit["transcript_body_read"] is False
    assert "Transcript files inspected: 16" in report
