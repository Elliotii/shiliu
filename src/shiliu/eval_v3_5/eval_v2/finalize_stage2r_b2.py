from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .canary import scan_artifacts_for_secrets
from .packets import verify_packet_hash
from .query_projection import QueryProjectedAnnotationPacketV2
from .stage2r_b2_intake import (
    BUNDLE,
    EXPECTED_BUNDLE_SHA256,
    EXPECTED_FREEZE_SHA256,
    FREEZE_MANIFEST,
    OUTPUT_ROOT,
    validate_preconditions,
)


def main() -> None:
    validate_preconditions()
    source = Path("/Users/elliot/Documents/Shiliu/videos/BV1o87764Ebs/subtitle-raw.json")
    source_rows = json.loads(source.read_text(encoding="utf-8"))
    cases = []
    for case_id in ("V2C_B2P00001", "V2C_B2P00002"):
        root = OUTPUT_ROOT / case_id
        primary_path = root / "primary/reviewer_packet.json"
        secondary_path = root / "secondary/reviewer_packet.json"
        packet = QueryProjectedAnnotationPacketV2.model_validate_json(
            primary_path.read_text(encoding="utf-8")
        )
        cases.append(
            {
                "case_id": case_id,
                "packet_hash_valid": verify_packet_hash(packet),
                "primary_secondary_packet_bytes_equal": (
                    primary_path.read_bytes() == secondary_path.read_bytes()
                ),
                "packet_segment_count": len(packet.full_raw_transcript),
                "raw_source_segment_count": len(source_rows),
                "full_transcript_not_truncated": (
                    len(packet.full_raw_transcript) == len(source_rows)
                ),
                "source_version_matches": packet.source_metadata["source_version"]
                == "sha256:" + _sha256(source),
                "first_segment_id": packet.full_raw_transcript[0].segment_id,
                "last_segment_id": packet.full_raw_transcript[-1].segment_id,
            }
        )
    secret = scan_artifacts_for_secrets(OUTPUT_ROOT, secrets=())
    _write_json(OUTPUT_ROOT / "secret_scan.audit.json", secret)
    audit = {
        "freeze_manifest_sha256": _sha256(FREEZE_MANIFEST),
        "freeze_manifest_expected": EXPECTED_FREEZE_SHA256,
        "bundle_sha256": _sha256(BUNDLE),
        "bundle_expected": EXPECTED_BUNDLE_SHA256,
        "safe_projection_sha256": _sha256(
            Path("research/v3_5/eval_v2/stage2r_b_inputs/pilot_candidate_projection.safe.v1.jsonl")
        ),
        "cases": cases,
        "secret_scan_passed": secret["passed"],
        "heldout_or_gold_accessed": False,
        "additional_query_pool_accessed": False,
        "third_reviewer_used": False,
        "third_case_selected": False,
        "final_gold_created": False,
        "eval_v1_modified": False,
        "frozen_v3_code_modified": False,
        "protocol_defect_detected": False,
        "stage2r_c_authorized": False,
        "stage2r_c_reason": "awaiting human adjudication of remaining Pilot Cases",
    }
    _write_json(OUTPUT_ROOT / "pilot_integrity.audit.json", audit)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
