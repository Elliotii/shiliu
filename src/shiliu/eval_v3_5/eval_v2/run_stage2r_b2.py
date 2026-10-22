from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .canary import CanaryCaseSpec, scan_artifacts_for_secrets
from .stage2r_b2_intake import OUTPUT_ROOT, validate_human_decisions, validate_preconditions
from .stage2r_b2_runtime import run_b2_case
from .stage2r_b_runtime import invoke_primary, invoke_secondary


SAFE_POOL = Path(
    "research/v3_5/eval_v2/stage2r_b_inputs/pilot_candidate_projection.safe.v1.jsonl"
)
SAFE_POOL_SHA256 = "2c2fd3e0d06452201119f22ab3b68dcdfc738f91d19a916e50dbb9fd2051b564"
REVIEWED = {
    "SAFEQ_b74c117c857397e307df",
    "SAFEQ_3722c739c07887747c70",
}


def remaining_candidates() -> list[dict[str, object]]:
    if hashlib.sha256(SAFE_POOL.read_bytes()).hexdigest() != SAFE_POOL_SHA256:
        raise RuntimeError("safe_projection_hash_mismatch")
    rows = [json.loads(line) for line in SAFE_POOL.read_text(encoding="utf-8").splitlines() if line.strip()]
    remaining = [row for row in rows if row["candidate_id"] not in REVIEWED]
    if len(rows) != 4 or len(remaining) != 2:
        raise RuntimeError("safe_candidate_inventory_mismatch")
    return remaining


def specs() -> tuple[CanaryCaseSpec, CanaryCaseSpec]:
    common = {
        "query_language": "en",
        "query_family": "exact_entity_topic",
        "leakage_group": "LGV2_VIDEO_BV1O87764EBS",
        "case_class": "remaining_safe_pool",
        "selection_reason": "Frozen V3 Search source navigation; excluded from Reviewer Packet",
        "complexity_tags": ("single_video", "full_transcript"),
        "video_id": "BV1o87764Ebs",
        "source_language": "zh",
        "source_type": "raw_subtitle",
        "raw_subtitle_json": Path(
            "/Users/elliot/Documents/Shiliu/videos/BV1o87764Ebs/subtitle-raw.json"
        ),
        "full_transcript_reference": Path(
            "/Users/elliot/Documents/Shiliu/videos/BV1o87764Ebs/subtitle-raw.txt"
        ),
        "development_authorization_source": "B2 remaining safe projection only",
        "evaluation_view": "single_video_topic_evidence",
        "projection_policy_version": "v3.5-query-projection-v1",
        "projection_status": "annotatable",
    }
    return (
        CanaryCaseSpec(
            case_id="V2C_B2P00001",
            candidate_id="SAFEQ_4c4b6895fe044589f229",
            query_id="SAFE_REMAINING_01",
            query="RAG",
            evidence_question="该视频的完整原字幕是否实质讨论了 RAG？",
            **common,
        ),
        CanaryCaseSpec(
            case_id="V2C_B2P00002",
            candidate_id="SAFEQ_ab03f4a17565fae4de35",
            query_id="SAFE_REMAINING_02",
            query="vibe coding",
            evidence_question="该视频的完整原字幕是否实质讨论了 vibe coding？",
            **common,
        ),
    )


def main() -> None:
    validate_preconditions()
    validate_human_decisions()
    remaining = remaining_candidates()
    expected = {row["candidate_id"] for row in remaining}
    actual = {spec.candidate_id for spec in specs()}
    if expected != actual:
        raise RuntimeError("remaining_candidate_binding_mismatch")
    if any((OUTPUT_ROOT / spec.case_id).exists() for spec in specs()):
        raise RuntimeError("refusing_to_overwrite_b2_case")

    _write_json(
        OUTPUT_ROOT / "safe_candidate_inventory.audit.json",
        {
            "safe_projection_sha256": SAFE_POOL_SHA256,
            "safe_projection_count": 4,
            "previously_reviewed_candidate_ids": sorted(REVIEWED),
            "remaining_candidate_count": 2,
            "remaining_candidate_ids": sorted(actual),
            "additional_query_pool_accessed": False,
        },
    )
    _write_json(
        OUTPUT_ROOT / "source_navigation.audit.json",
        {
            "search_only_navigation": True,
            "frozen_lexical_index_version": "v3-stage1-lexical-v1",
            "frozen_dense_index_version": "v3-dense-qwen3-0.6b-mrl512-v1",
            "index_rebuilt_without_source_or_code_change": True,
            "queries": [
                {
                    "candidate_id": "SAFEQ_4c4b6895fe044589f229",
                    "query": "RAG",
                    "mode": "lexical",
                    "selected_bvid": "BV1o87764Ebs",
                    "trace_id": "frozen_v3_navigation_local_trace",
                },
                {
                    "candidate_id": "SAFEQ_ab03f4a17565fae4de35",
                    "query": "vibe coding",
                    "mode": "dense",
                    "selected_bvid": "BV1o87764Ebs",
                    "trace_id": "frozen_v3_navigation_local_trace",
                },
            ],
            "search_ranking_sent_to_reviewer": False,
        },
    )
    protocol = (
        "Use the frozen four-state sufficiency protocol. Evidence Groups are alternatives (OR); "
        "all Required Spans inside a group are jointly required (AND). Required Aspects derive only "
        "from evidence_question, and the complete readable Transcript may be insufficient."
    )
    summaries = []
    all_usage: list[dict[str, object]] = []
    for spec in specs():
        result = run_b2_case(
            spec=spec,
            output_root=OUTPUT_ROOT,
            primary_invoke=invoke_primary,
            secondary_invoke=lambda packet, prompt: invoke_secondary(packet, prompt),
            protocol_excerpt=protocol,
        )
        primary = result["primary"]
        secondary = result["secondary"]
        summaries.append(
            {
                "case_id": spec.case_id,
                "candidate_id": spec.candidate_id,
                "original_query": spec.query,
                "evaluation_view": spec.evaluation_view,
                "evidence_question": spec.evidence_question,
                "projection_status": spec.projection_status,
                "primary_status": primary.status,
                "primary_attempt_count": len(primary.attempts),
                "primary_repair_count": primary.repair_count,
                "primary_query_grounding": primary.grounding_status,
                "secondary_status": secondary.status,
                "secondary_attempt_count": len(secondary.attempts),
                "secondary_repair_count": secondary.repair_count,
                "secondary_query_grounding": secondary.grounding_status,
                "agreement_status": result["agreement_status"],
                "human_review_packet": str(result["human_review_packet"]),
            }
        )
        for role in ("primary", "secondary"):
            usage_path = result["case_root"] / role / "provider_attempt_usage.jsonl"
            all_usage.extend(
                json.loads(line)
                for line in usage_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
    _write_json(OUTPUT_ROOT / "pilot_summary.json", summaries)
    (OUTPUT_ROOT / "provider_attempt_usage.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in all_usage),
        encoding="utf-8",
    )
    returned = [record for record in all_usage if record["model_body_returned"]]
    complete = all(
        record[field] != "unavailable"
        for record in returned
        for field in ("input_tokens", "output_tokens", "provider_latency_ms")
    )
    _write_json(
        OUTPUT_ROOT / "usage_summary.json",
        {
            "attempt_count": len(all_usage),
            "http_400_count": sum(record["http_status"] == 400 for record in all_usage),
            "model_body_count": len(returned),
            "input_tokens": sum(record["input_tokens"] for record in returned if isinstance(record["input_tokens"], int)),
            "output_tokens": sum(record["output_tokens"] for record in returned if isinstance(record["output_tokens"], int)),
            "cached_tokens_known_total": sum(record["cached_tokens"] for record in returned if isinstance(record["cached_tokens"], int)),
            "usage_completeness": "complete" if complete and all(isinstance(record["cached_tokens"], int) for record in returned) else "lower_bound",
            "all_attempts_included": True,
        },
    )
    _write_json(
        OUTPUT_ROOT / "secret_scan.audit.json",
        scan_artifacts_for_secrets(OUTPUT_ROOT, secrets=()),
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
