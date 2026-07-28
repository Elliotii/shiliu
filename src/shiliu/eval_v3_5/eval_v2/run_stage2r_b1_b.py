from __future__ import annotations

import json
from pathlib import Path

from .canary import CanaryCaseSpec, run_canary_case, scan_artifacts_for_secrets
from .providers import ReviewerPayload
from .stage2r_b_runtime import (
    RawInvocation,
    canonical_json,
    invoke_primary,
    invoke_secondary,
)
from .transport_diagnosis import diagnose_openai_transport


OUTPUT_ROOT = Path("research/v3_5/eval_v2/stage2r_b1_b_canary")


def _specs() -> tuple[CanaryCaseSpec, CanaryCaseSpec]:
    return (
        CanaryCaseSpec(
            case_id="V2C_B1A00001",
            candidate_id="SAFEQ_b74c117c857397e307df",
            query_id="Q01",
            query="MCP",
            evaluation_view="single_video_topic_evidence",
            evidence_question="该视频的完整原字幕是否实质讨论了 MCP？",
            projection_policy_version="v3.5-query-projection-v1",
            projection_status="annotatable",
            query_language="en",
            query_family="exact_entity_mcp",
            leakage_group="LGV2_VIDEO_BV1ZDTX6EEGU",
            case_class="ordinary",
            selection_reason="same B1-A fixed canary; no reselection",
            complexity_tags=("single_video", "short_transcript", "negative_control_candidate"),
            video_id="BV1zDTX6eEGu",
            source_language="zh",
            source_type="raw_subtitle",
            raw_subtitle_json=Path("/Users/elliot/Documents/Shiliu/videos/BV1zDTX6eEGu/subtitle-raw.json"),
            full_transcript_reference=Path("/Users/elliot/Documents/Shiliu/videos/BV1zDTX6eEGu/subtitle-raw.txt"),
            development_authorization_source="B1-B instruction; exact B1-A canary reuse",
        ),
        CanaryCaseSpec(
            case_id="V2C_B1A00002",
            candidate_id="SAFEQ_3722c739c07887747c70",
            query_id="Q15",
            query="哪个视频解释了 CLI 相比 MCP 的优势？",
            evaluation_view="single_video_claim_evidence",
            evidence_question="该视频的完整原字幕是否实质解释了 CLI 相比 MCP 的优势？",
            projection_policy_version="v3.5-query-projection-v1",
            projection_status="annotatable",
            query_language="zh",
            query_family="evidence_lookup_cli_vs_mcp",
            leakage_group="LGV2_VIDEO_BV1O87764EBS",
            case_class="complex",
            selection_reason="same B1-A fixed canary; no reselection",
            complexity_tags=("single_video", "long_transcript", "multi_aspect", "evidence_lookup"),
            video_id="BV1o87764Ebs",
            source_language="zh",
            source_type="raw_subtitle",
            raw_subtitle_json=Path("/Users/elliot/Documents/Shiliu/videos/BV1o87764Ebs/subtitle-raw.json"),
            full_transcript_reference=Path("/Users/elliot/Documents/Shiliu/videos/BV1o87764Ebs/subtitle-raw.txt"),
            development_authorization_source="B1-B instruction; exact B1-A canary reuse",
        ),
    )


def _repair_payload(
    *, role: str, payload: ReviewerPayload, raw: RawInvocation, errors: tuple[str, ...]
) -> ReviewerPayload:
    prompt = "\n\n".join(
        [
            f"Repair only the supplied {role} ReviewerDraft. Return one JSON object matching the supplied schema. Preserve the evidence_question and bind every Required Aspect to exact query_anchor_texts. Do not change the Query, use another review, or create A/S/G IDs.",
            "VALIDATION ERRORS:\n" + canonical_json(list(errors)),
            "ORIGINAL REVIEWER OUTPUT:\n" + canonical_json(raw.body),
        ]
    )
    return ReviewerPayload(
        packet_bytes=payload.packet_bytes,
        prompt=prompt,
        draft_schema=payload.draft_schema,
    )


def main() -> None:
    if OUTPUT_ROOT.exists():
        raise SystemExit(f"refusing to overwrite existing output: {OUTPUT_ROOT}")
    OUTPUT_ROOT.mkdir(parents=True)
    diagnosis = diagnose_openai_transport()
    _write_json(OUTPUT_ROOT / "openai_transport_diagnosis.safe.json", diagnosis)

    protocol = (
        "Use the frozen four states: sufficient, partial, insufficient, and unverifiable. "
        "Evidence Groups are alternatives (OR); all Required Spans inside one group are jointly required (AND). "
        "The complete readable transcript can be insufficient when none of the query-derived aspects is supported."
    )
    summaries: list[dict[str, object]] = []
    for spec in _specs():
        holder: dict[str, object] = {}

        def primary_repair(
            payload: ReviewerPayload, raw: RawInvocation, errors: tuple[str, ...]
        ) -> tuple[RawInvocation, ReviewerPayload]:
            repair_payload = _repair_payload(
                role="Primary", payload=payload, raw=raw, errors=errors
            )
            return invoke_primary(repair_payload), repair_payload

        def secondary_initial(payload: ReviewerPayload) -> RawInvocation:
            packet = holder["packet"]
            return invoke_secondary(packet, payload.prompt)  # type: ignore[arg-type]

        def secondary_repair(
            payload: ReviewerPayload, raw: RawInvocation, errors: tuple[str, ...]
        ) -> tuple[RawInvocation, ReviewerPayload]:
            packet = holder["packet"]
            repair_payload = _repair_payload(
                role="Secondary", payload=payload, raw=raw, errors=errors
            )
            return invoke_secondary(packet, repair_payload.prompt), repair_payload  # type: ignore[arg-type]

        # Build once so the secondary adapter receives the exact packet object whose
        # bytes the canary runner will independently compare across providers.
        from .canary import build_canary_packet

        holder["packet"] = build_canary_packet(spec)
        result = run_canary_case(
            spec=spec,
            output_root=OUTPUT_ROOT,
            primary_invoke_factory=invoke_primary,
            primary_repair_factory=primary_repair,
            secondary_invoke_factory=secondary_initial,
            secondary_repair_factory=secondary_repair,
            protocol_excerpt=protocol,
        )
        summaries.append(
            {
                "case_id": spec.case_id,
                "review_run_id": result.review_run_id,
                "packet_sha256": result.packet_sha256,
                "primary_status": result.primary.status,
                "primary_query_grounding": result.primary.query_grounding_status,
                "secondary_status": result.secondary.status,
                "secondary_query_grounding": result.secondary.query_grounding_status,
                "agreement_status": getattr(result.agreement, "status", "not_available"),
                "human_review_packet": str(result.human_packet_path),
            }
        )
    _write_json(OUTPUT_ROOT / "canary_summary.json", summaries)
    _write_json(
        OUTPUT_ROOT / "secret_scan.audit.json",
        scan_artifacts_for_secrets(OUTPUT_ROOT, secrets=()),
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
