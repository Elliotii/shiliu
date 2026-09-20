from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from shiliu.evidence import SourceArtifactReference, bind_snapshot_manifest_version, load_source_artifact
from shiliu.eval_v3_5.models import CompletedReviewDecision, MasterCaseCandidate


VALIDATOR_VERSION = "v3.5-human-intake-validator-v1"
INTAKE_FILES = (
    "calibration_batch_01_cases_015_017_013_001_003_012.completed.jsonl",
    "calibration_batch_02_cases_007_008_009_010.completed.jsonl",
)
EXPECTED_INPUT_HASHES = {
    INTAKE_FILES[0]: "b6b004c45514182676f67ceda664bd8c45d34d8efeb49ef63f56a4fe44fc2566",
    INTAKE_FILES[1]: "970a502d5041444489addb226a8a4e687408a998747dec6ea30897998dfbce09",
}
AUTHORIZED_ORDER = (
    "CASE_015", "CASE_017", "CASE_013", "CASE_001", "CASE_003",
    "CASE_012", "CASE_007", "CASE_008", "CASE_009", "CASE_010",
)
ROUND2_ORDER = (
    "CASE_002", "CASE_004", "CASE_005", "CASE_006",
    "CASE_011", "CASE_014", "CASE_016", "CASE_018",
)
DEFAULT_SNAPSHOT_DB = Path("local-data/eval/shiliu_eval.db")


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _case_records(root: Path) -> dict[str, MasterCaseCandidate]:
    values = _jsonl(root / "master_case_candidates.jsonl") + _jsonl(root / "master_case_reserves.jsonl")
    return {item.case_id: item for item in (MasterCaseCandidate.model_validate(value) for value in values)}


def _reference(row: sqlite3.Row) -> SourceArtifactReference:
    return SourceArtifactReference(
        platform=str(row["platform"]), source_id=str(row["source_id"]), part=int(row["part"]),
        source_type=str(row["subtitle_source"] or "unknown"),
        source_language=str(row["subtitle_language"] or "unknown"),
        artifact_path=str(row["raw_subtitle_path"] or ""),
    )


def _union_duration(intervals: list[tuple[float, float]]) -> float:
    if not intervals:
        return 0.0
    total = 0.0
    current_start, current_end = sorted(intervals)[0]
    for start, end in sorted(intervals)[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    return total + current_end - current_start


def validate_human_intake(
    *,
    root: str | Path = "research/v3_5",
    snapshot_db: str | Path = DEFAULT_SNAPSHOT_DB,
    artifact_manifest: str | Path = "research/v3_eval/artifact_manifest.jsonl",
    intake_files: tuple[str, ...] = INTAKE_FILES,
    expected_input_hashes: dict[str, str] = EXPECTED_INPUT_HASHES,
    authorized_order: tuple[str, ...] = AUTHORIZED_ORDER,
    expected_label_distribution: dict[str, int] | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    root = Path(root)
    intake_root = root / "human_reviews" / "intake"
    input_meta = []
    records: list[dict[str, object]] = []
    for filename in intake_files:
        path = intake_root / filename
        digest = sha256(path.read_bytes()).hexdigest()
        if digest != expected_input_hashes[filename]:
            raise ValueError(f"Human Intake identity mismatch: {filename}: {digest}")
        values = _jsonl(path)
        input_meta.append({
            "filename": filename, "sha256": digest, "record_count": len(values),
            "case_ids": [str(item.get("case_id")) for item in values],
        })
        records.extend(values)

    case_ids = [str(item.get("case_id")) for item in records]
    if tuple(case_ids) != authorized_order or len(set(case_ids)) != len(authorized_order):
        raise ValueError(f"unknown, duplicate, or incorrectly ordered case IDs: {case_ids}")
    decisions = [CompletedReviewDecision.model_validate(item) for item in records]
    if any(item.reviewer != "human_user" or item.decision_status != "completed" for item in decisions):
        raise ValueError("every decision must be completed by human_user")

    cases = _case_records(root)
    packet_manifest = json.loads((root / "review_packet_manifest.json").read_text(encoding="utf-8"))
    packet_entries = {item["case_id"]: item for item in packet_manifest["packets"]}
    connection = sqlite3.connect(f"file:{Path(snapshot_db).resolve()}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    warnings: list[dict[str, object]] = []
    case_audits: list[dict[str, object]] = []
    source_distribution: Counter[str] = Counter()
    language_distribution: Counter[str] = Counter()
    group_durations: list[dict[str, object]] = []
    multi_span_cases: set[str] = set()
    alternative_group_cases: set[str] = set()
    transcript_error_cases: set[str] = set()
    try:
        for raw, decision in zip(records, decisions, strict=True):
            case_id = decision.case_id
            if case_id not in cases or case_id not in packet_entries:
                raise ValueError(f"unknown case or missing packet manifest entry: {case_id}")
            case = cases[case_id]
            entry = packet_entries[case_id]
            packet_path = Path(entry["packet_path"])
            packet_bytes = packet_path.read_bytes()
            if sha256(packet_bytes).hexdigest() != entry["sha256"]:
                raise ValueError(f"Packet drift: {case_id}")
            packet_text = packet_bytes.decode("utf-8")

            aspect_ids = [item.aspect_id for item in decision.required_aspects]
            if len(aspect_ids) != len(set(aspect_ids)):
                raise ValueError(f"duplicate Aspect ID: {case_id}")
            known_aspects = set(aspect_ids)
            if not set(decision.supported_aspects) <= known_aspects or not set(decision.missing_aspects) <= known_aspects:
                raise ValueError(f"top-level decision references unknown Aspect: {case_id}")
            for group in decision.gold_evidence_groups:
                if not group.required_spans or not set(group.supported_aspects) <= known_aspects:
                    raise ValueError(f"empty group or unknown group Aspect: {case_id}/{group.group_id}")

            required = {item.aspect_id for item in decision.required_aspects if item.is_required}
            if decision.sufficiency_label == "sufficient":
                if not decision.gold_evidence_groups or decision.missing_aspects or not required <= set(decision.supported_aspects):
                    raise ValueError(f"sufficient invariant failed: {case_id}")
                if not any(required <= set(group.supported_aspects) for group in decision.gold_evidence_groups):
                    raise ValueError(f"no complete OR Evidence Group: {case_id}")
            elif decision.sufficiency_label == "partial":
                if not decision.gold_evidence_groups or not decision.supported_aspects or not decision.missing_aspects:
                    raise ValueError(f"partial invariant failed: {case_id}")
            elif decision.gold_evidence_groups:
                raise ValueError(f"non-evidence label fabricates Gold Evidence: {case_id}")

            source_distribution[case.source_type or case.source_state] += 1
            language_distribution[case.source_language or "none"] += 1
            if (
                any(
                    flag.startswith("ai_transcript_")
                    or (flag.startswith("asr_") and flag != "asr_authority_judged_as_rendered")
                    for flag in decision.reviewer_flags
                )
                or "asr_transcription_uncertainty" in decision.primary_reason_codes
            ):
                transcript_error_cases.add(case_id)

            segment_count = 0
            if case.source_state == "readable_raw":
                row = connection.execute("SELECT * FROM videos WHERE id=?", (case.target_video_id,)).fetchone()
                if row is None:
                    raise ValueError(f"Snapshot video missing: {case_id}")
                binding = bind_snapshot_manifest_version(
                    _reference(row), video_id=int(case.target_video_id), manifest_path=artifact_manifest
                )
                artifact = load_source_artifact(_reference(row), expected_source_version=binding.source_version)
                if case.source_version != artifact.source_version or entry["source_version"] != artifact.source_version:
                    raise ValueError(f"source-version mismatch: {case_id}")
                segments = {item.segment_id: item for item in artifact.segments}
                segment_count = len(segments)
                for group in decision.gold_evidence_groups:
                    intervals = []
                    if len(group.required_spans) > 1:
                        multi_span_cases.add(case_id)
                    for span in group.required_spans:
                        unknown = [value for value in span.segment_ids if value not in segments]
                        if unknown:
                            raise ValueError(f"unknown Segment ID: {case_id}/{span.span_id}: {unknown}")
                        selected = [segments[value] for value in span.segment_ids]
                        if any(value not in packet_text for value in span.segment_ids):
                            raise ValueError(f"Segment ID absent from Packet: {case_id}/{span.span_id}")
                        ordinals = [item.original_ordinal for item in selected]
                        if ordinals != sorted(ordinals) or len(ordinals) != len(set(ordinals)):
                            raise ValueError(f"Segment order invalid: {case_id}/{span.span_id}")
                        runs = {item.timeline_run_id for item in selected}
                        if runs != {span.timeline_run_id}:
                            raise ValueError(f"Timeline Run mismatch: {case_id}/{span.span_id}")
                        if span.start_time != selected[0].start_time or span.end_time != selected[-1].end_time:
                            raise ValueError(
                                f"span time reconstruction mismatch: {case_id}/{span.span_id}; "
                                f"stored={span.start_time}-{span.end_time}; "
                                f"actual={selected[0].start_time}-{selected[-1].end_time}"
                            )
                        if any(right != left + 1 for left, right in zip(ordinals, ordinals[1:])):
                            warnings.append({
                                "case_id": case_id, "span_id": span.span_id,
                                "warning": "deliberate_non_contiguous_segment_selection",
                                "ordinals": ordinals,
                            })
                        intervals.append((span.start_time, span.end_time))
                    duration = _union_duration(intervals)
                    group_durations.append({
                        "case_id": case_id, "group_id": group.group_id,
                        "duration_seconds": round(duration, 6),
                        "span_count": len(group.required_spans),
                    })
                if decision.sufficiency_label == "unverifiable":
                    raise ValueError(f"unverifiable has readable Raw Source: {case_id}")
            else:
                if decision.gold_evidence_groups:
                    raise ValueError(f"unavailable/corpus case fabricates Evidence: {case_id}")
                if decision.sufficiency_label == "unverifiable" and case.source_state not in {"title_only", "subtitle_missing"}:
                    raise ValueError(f"unverifiable source authority is available: {case_id}")
                if decision.sufficiency_label == "insufficient" and case.case_scope != "query_corpus":
                    raise ValueError(f"insufficient unavailable-source case is incompatible: {case_id}")

            if len(decision.gold_evidence_groups) > 1:
                alternative_group_cases.add(case_id)
            case_audits.append({
                "case_id": case_id,
                "schema": "passed", "packet": "passed", "source_version": "passed",
                "segments": "passed", "timeline": "passed", "four_state": "passed",
                "source_state": case.source_state,
                "source_type": case.source_type or case.source_state,
                "source_language": case.source_language,
                "segment_authority_count": segment_count,
                "gold_group_count": len(decision.gold_evidence_groups),
            })
    finally:
        connection.close()

    labels = Counter(item.sufficiency_label for item in decisions)
    expected_labels = Counter(
        expected_label_distribution
        or {"sufficient": 6, "insufficient": 3, "unverifiable": 1}
    )
    if labels != expected_labels:
        raise ValueError(f"unexpected human label distribution: {dict(labels)}")
    needs_second_review = [item.case_id for item in decisions if item.needs_second_review]
    longest = max(group_durations, key=lambda item: float(item["duration_seconds"]), default=None)
    audit = {
        "validator_version": VALIDATOR_VERSION,
        "input_files": input_meta,
        "case_ids": list(authorized_order),
        "schema_validation_result": "passed",
        "packet_validation_result": "passed",
        "source_version_validation_result": "passed",
        "segment_validation_result": "passed",
        "timeline_validation_result": "passed",
        "four_state_invariant_result": "passed",
        "warnings": warnings,
        "errors": [],
        "label_distribution": dict(sorted(labels.items())),
        "source_type_distribution": dict(sorted(source_distribution.items())),
        "language_distribution": dict(sorted(language_distribution.items())),
        "needs_second_review_cases": needs_second_review,
        "cases_with_gold_evidence_groups": sum(bool(item.gold_evidence_groups) for item in decisions),
        "multi_span_group_cases": sorted(multi_span_cases),
        "alternative_or_group_cases": sorted(alternative_group_cases),
        "group_durations": group_durations,
        "longest_gold_group": longest,
        "transcript_error_flag_cases": sorted(transcript_error_cases),
        "case_validation": case_audits,
    }
    return records, audit


def write_validated_intake(
    *, root: str | Path = "research/v3_5", validated_at: str | None = None
) -> dict[str, object]:
    root = Path(root)
    records, audit = validate_human_intake(root=root)
    output_root = root / "human_reviews"
    output_root.mkdir(parents=True, exist_ok=True)
    ledger_path = output_root / "review_decisions.calibration.10_cases.validated.jsonl"
    ledger_text = "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for item in records
    )
    ledger_path.write_text(ledger_text, encoding="utf-8")
    ledger_hash = sha256(ledger_text.encode("utf-8")).hexdigest()
    timestamp = validated_at or datetime.now(timezone.utc).isoformat()
    audit.update({
        "validated_at": timestamp,
        "canonical_ledger_path": str(ledger_path),
        "canonical_output_sha256": ledger_hash,
    })
    (output_root / "calibration_10_case_validation_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "validator_version": VALIDATOR_VERSION,
        "validated_at": timestamp,
        "received_status": "received_exact_hash",
        "validated_status": "passed",
        "canonical_ledger": {
            "path": str(ledger_path), "sha256": ledger_hash,
            "record_count": len(records), "case_ids": list(AUTHORIZED_ORDER),
        },
        "files": [
            {**item, "received_status": "received_exact_hash", "validated_status": "passed",
             "validated_at": timestamp, "validator_version": VALIDATOR_VERSION}
            for item in audit["input_files"]
        ],
    }
    (output_root / "calibration_intake_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(write_validated_intake(), ensure_ascii=False, sort_keys=True))
