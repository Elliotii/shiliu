"""Mechanical validator for P7A packet export.

The validator checks identities, packet assignments, blank template shape,
neutrality, paths, hashes, and the Frozen guard. It never constructs Gold and
never performs semantic transcript review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research/v3_5/product_query_set_v1/gold_construction_v1"
P6 = ROOT / "research/v3_5/product_query_set_v1/gold_protocol_v1"

EXPECTED_LEDGER_SHA = "81b420d739641e7b6020cd6519022d4c24a83abf02a6620149d2533fefbb59f7"
EXPECTED_BATCHES = {
    "development": {
        "DEV_BATCH_01": ["PQS_V1_Q003", "PQS_V1_Q005"],
        "DEV_BATCH_02": ["PQS_V1_Q004", "PQS_V1_Q006"],
        "DEV_BATCH_03": ["PQS_V1_Q007", "PQS_V1_Q008"],
        "DEV_BATCH_04": ["PQS_V1_Q011", "PQS_V1_Q012"],
        "DEV_BATCH_05": ["PQS_V1_Q014", "PQS_V1_Q015"],
        "DEV_BATCH_06": ["PQS_V1_Q017", "PQS_V1_Q018"],
        "DEV_BATCH_07": ["PQS_V1_Q013", "PQS_V1_Q019"],
    },
    "frozen_guarded": {
        "FROZEN_BATCH_01": ["PQS_V1_Q001", "PQS_V1_Q024"],
        "FROZEN_BATCH_02": ["PQS_V1_Q009", "PQS_V1_Q010"],
        "FROZEN_BATCH_03": ["PQS_V1_Q002", "PQS_V1_Q016"],
        "FROZEN_BATCH_04": ["PQS_V1_Q020", "PQS_V1_Q021"],
        "FROZEN_BATCH_05": ["PQS_V1_Q022", "PQS_V1_Q023"],
    },
}
TEMPLATE_FILES = {
    "retrieval_gold.template.jsonl": "product_retrieval_gold.schema.json",
    "evidence_gold.template.jsonl": "product_evidence_gold.schema.json",
    "sufficiency_gold.template.jsonl": "product_sufficiency_gold.schema.json",
}
DECISION_TEMPLATES = {
    "initial_annotation_decision.template.jsonl",
    "independent_review_decision.template.jsonl",
    "user_adjudication_decision.template.jsonl",
}
PACKET_FILES = {
    "batch_manifest.json",
    "query_records.locked.jsonl",
    "annotation_assignment.json",
    *TEMPLATE_FILES,
    *DECISION_TEMPLATES,
    "README.md",
}
NAVIGATION_FORBIDDEN_KEYS = {
    "query_id",
    "query_score",
    "recommended_query",
    "candidate_video",
    "target_video",
    "relevant",
    "negative",
    "expected_evidence",
    "system_rank",
    "system_score",
}
DOWNSTREAM_FORBIDDEN_TEXT = (
    "builder_output",
    "selector_output",
    "judge_output",
    "expected_failure",
    "system_score",
    "system_rank",
    "existing_gold",
)


class PacketValidationError(ValueError):
    """Raised for a P7A mechanical contract violation."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _required_schema_fields(schema_name: str) -> set[str]:
    return set(read_json(P6 / schema_name)["required"])


def validate_input_identity() -> None:
    ledger = OUTPUT / "PQS_V1_P7A_PACKET_EXPORT_DECISION_LEDGER.json"
    if sha256(ledger) != EXPECTED_LEDGER_SHA:
        raise PacketValidationError("P7A repository Ledger hash mismatch")
    manifest = read_json(OUTPUT / "p7a_packet_export.manifest.json")
    for relative, expected in manifest["source_hashes"].items():
        path = ROOT / relative
        if not path.is_file() or sha256(path) != expected:
            raise PacketValidationError(f"upstream identity mismatch: {relative}")


def validate_navigation_bundle() -> None:
    rows = read_jsonl(OUTPUT / "shared/neutral_library_navigation_index.jsonl")
    if not rows:
        raise PacketValidationError("neutral navigation index is empty")
    required = {
        "video_id",
        "bvid",
        "title",
        "uploader",
        "folder_identity",
        "metadata_path",
        "summary_path",
        "chapter_path",
        "authoritative_transcript_available",
        "authoritative_transcript_path",
        "source_type",
        "source_language",
        "source_version",
        "timeline_run_id",
        "segment_identity_version",
        "evidence_authority",
    }
    for row in rows:
        if not required <= row.keys():
            raise PacketValidationError("neutral navigation row misses required fields")
        if NAVIGATION_FORBIDDEN_KEYS & row.keys():
            raise PacketValidationError("neutral navigation row contains query labels or scores")
        if row["evidence_authority"] != "navigation_only":
            raise PacketValidationError("navigation evidence authority must be navigation_only")
        if row["authoritative_transcript_available"]:
            source = Path(row["authoritative_transcript_path"])
            if not source.is_file() or sha256(source) != row["source_version"]:
                raise PacketValidationError("navigation source path/hash mismatch")
            if row["source_type"] not in {"official_subtitle", "asr_transcript"}:
                raise PacketValidationError("invalid authoritative source type")


def validate_transcript_catalog() -> None:
    rows = read_jsonl(OUTPUT / "shared/authoritative_transcript_identity_catalog.jsonl")
    required = {
        "video_id",
        "source_type",
        "source_language",
        "source_path",
        "source_file_sha256",
        "source_version",
        "timeline_run_id",
        "segment_identity_version",
        "segment_count",
        "timeline_replayable",
    }
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not required <= row.keys():
            raise PacketValidationError("transcript catalog row misses identity fields")
        source = Path(row["source_path"])
        if not source.is_file():
            raise PacketValidationError("catalog source path does not exist")
        actual = sha256(source)
        if actual != row["source_file_sha256"] or actual != row["source_version"]:
            raise PacketValidationError("catalog source hash mismatch")
        payload = json.loads(source.read_bytes())
        if not isinstance(payload, list) or len(payload) != row["segment_count"]:
            raise PacketValidationError("catalog segment count mismatch")
        if not row["timeline_replayable"] or not row["timeline_run_id"]:
            raise PacketValidationError("catalog timeline is not replayable")
        if not row.get("timeline_run_ids"):
            raise PacketValidationError("complete timeline run identities are required")
        key = (row["video_id"], row["source_version"])
        if key in seen:
            raise PacketValidationError("catalog repeats an authoritative source")
        seen.add(key)


def _validate_template(path: Path, schema_name: str, query_ids: list[str]) -> None:
    rows = read_jsonl(path)
    if len(rows) != 2 or [row["query_id"] for row in rows] != query_ids:
        raise PacketValidationError(f"template identity mismatch: {path}")
    schema_required = _required_schema_fields(schema_name)
    for row in rows:
        if row.get("annotation_status") != "not_started":
            raise PacketValidationError("template must remain not_started")
        if row.get("schema_ref") != f"../../../../gold_protocol_v1/{schema_name}":
            raise PacketValidationError("template references the wrong P6 schema")
        record = row.get("record")
        if not isinstance(record, dict) or set(record) != schema_required:
            raise PacketValidationError("template record fields do not match P6 schema")
        if schema_name == "product_retrieval_gold.schema.json":
            if any(record[key] for key in ("known_relevant_video_ids", "acceptable_video_ids", "hard_negative_video_ids", "reason_codes")):
                raise PacketValidationError("retrieval template contains prefilled judgment")
            if record["relevance_review_scope"]["reviewed_video_ids"]:
                raise PacketValidationError("retrieval template contains a prefilled pool")
        elif schema_name == "product_evidence_gold.schema.json":
            semantic_arrays = (
                "required_aspects",
                "aspect_evidence_options",
                "acceptable_evidence_groups",
                "span_registry",
                "optional_context_spans",
                "reason_codes",
            )
            if any(record[key] for key in semantic_arrays):
                raise PacketValidationError("evidence template contains prefilled Gold")
        else:
            if record["status"] != "__PENDING__" or any(
                record[key]
                for key in (
                    "material_aspect_ids",
                    "supported_aspects",
                    "missing_aspects",
                    "reason_codes",
                    "evidence_group_ids_used",
                )
            ):
                raise PacketValidationError("sufficiency template contains prefilled Gold")


def validate_batches() -> None:
    all_query_ids: list[str] = []
    canonical = {
        row["query_id"]: row
        for row in read_jsonl(
            ROOT / "research/v3_5/product_query_set_v1/freeze/product_query_set_v1.locked.jsonl"
        )
    }
    for split_dir, batches in EXPECTED_BATCHES.items():
        split_manifest = read_json(OUTPUT / split_dir / "batch_manifest.json")
        if split_manifest["batch_assignments"] != batches:
            raise PacketValidationError(f"{split_dir} batch manifest differs from Ledger")
        for batch_id, query_ids in batches.items():
            batch = OUTPUT / split_dir / "batches" / batch_id
            if {path.name for path in batch.iterdir() if path.is_file()} != PACKET_FILES:
                raise PacketValidationError(f"packet file set mismatch: {batch_id}")
            records = read_jsonl(batch / "query_records.locked.jsonl")
            if [row["query_id"] for row in records] != query_ids:
                raise PacketValidationError(f"query order mismatch: {batch_id}")
            if any(row != canonical[row["query_id"]] for row in records):
                raise PacketValidationError(f"locked query changed: {batch_id}")
            for file_name, schema_name in TEMPLATE_FILES.items():
                _validate_template(batch / file_name, schema_name, query_ids)
            for decision_name in DECISION_TEMPLATES:
                decisions = read_jsonl(batch / decision_name)
                if len(decisions) != 2 or [row["query_id"] for row in decisions] != query_ids:
                    raise PacketValidationError("decision template identity mismatch")
                if any(row["status"] != "not_started" for row in decisions):
                    raise PacketValidationError("decision workflow was started")
            assignment = read_json(batch / "annotation_assignment.json")
            if assignment["packet_exporter_may_annotate"] or assignment["same_session_annotation_and_review_allowed"]:
                raise PacketValidationError("role separation failed")
            packet_manifest = read_json(batch / "batch_manifest.json")
            for relative, expected in packet_manifest["file_hashes"].items():
                if sha256(batch / relative) != expected:
                    raise PacketValidationError(f"packet hash mismatch: {batch_id}/{relative}")
            all_query_ids.extend(query_ids)
    if len(all_query_ids) != 24 or len(set(all_query_ids)) != 24:
        raise PacketValidationError("24 queries were not packetized exactly once")
    if set(all_query_ids) != set(canonical):
        raise PacketValidationError("packet query set differs from locked P4 set")


def validate_prompts_and_guard() -> None:
    dev_annotator = (OUTPUT / "prompts/DEVELOPMENT_INITIAL_ANNOTATOR_PROMPT.md").read_text()
    dev_reviewer = (OUTPUT / "prompts/DEVELOPMENT_INDEPENDENT_REVIEWER_PROMPT.md").read_text()
    frozen_annotator = (OUTPUT / "prompts/FROZEN_INITIAL_ANNOTATOR_PROMPT.md").read_text()
    frozen_reviewer = (OUTPUT / "prompts/FROZEN_INDEPENDENT_REVIEWER_PROMPT.md").read_text()
    dev_annotator_normalized = " ".join(dev_annotator.split())
    dev_reviewer_normalized = " ".join(dev_reviewer.split())
    frozen_annotator_normalized = " ".join(frozen_annotator.split())
    frozen_reviewer_normalized = " ".join(frozen_reviewer.split())
    if "new independent Session" not in dev_annotator_normalized or "Do not run the Product Pipeline" not in dev_annotator_normalized:
        raise PacketValidationError("Development annotator independence prompt incomplete")
    if "different independent Session" not in dev_reviewer_normalized or "before viewing the Initial Annotation" not in dev_reviewer_normalized:
        raise PacketValidationError("Development reviewer independence prompt incomplete")
    if "frozen_guarded" not in frozen_annotator_normalized or "must not return Gold content" not in frozen_annotator_normalized:
        raise PacketValidationError("Frozen annotator isolation prompt incomplete")
    if "different Session" not in frozen_reviewer_normalized or "must not return Gold content" not in frozen_reviewer_normalized:
        raise PacketValidationError("Frozen reviewer isolation prompt incomplete")

    guard = read_json(OUTPUT / "frozen_guarded/FROZEN_PACKET_ACCESS_GUARD.json")
    if guard["status"] not in {
        "packetized_not_annotated",
        "annotation_in_progress",
        "sealed_execution_candidate",
    }:
        raise PacketValidationError("Frozen guard status invalid")
    if guard["v3_5_b_content_visibility"]["gold_content"] != "forbidden":
        raise PacketValidationError("Frozen Gold visibility is not forbidden")
    completion = guard["completion_response_to_v3_5_b"]
    completion_template = read_json(OUTPUT / "prompts/FROZEN_COMPLETION_ONLY_RESPONSE_TEMPLATE.md")
    if set(completion_template) != set(completion["allowed_fields"]):
        raise PacketValidationError("Frozen completion template has non-allowed fields")
    if set(completion_template) & set(completion["forbidden_fields"]):
        raise PacketValidationError("Frozen completion template leaks protected fields")


def validate_governance_hashes() -> None:
    manifest = read_json(OUTPUT / "p7a_packet_export.manifest.json")
    for relative, expected in manifest["artifact_hashes"].items():
        path = OUTPUT / relative
        if not path.is_file():
            raise PacketValidationError(f"artifact hash mismatch: {relative}")
        if sha256(path) == expected:
            continue
        if relative == "frozen_guarded/FROZEN_PACKET_ACCESS_GUARD.json":
            guard = read_json(path)
            transitions = list(guard.get("status_transition_history", []))
            if isinstance(guard.get("status_transition"), dict):
                transitions.append(guard["status_transition"])
            if any(
                transition.get("previous_guard_sha256") == expected
                for transition in transitions
                if isinstance(transition, dict)
            ):
                continue
        raise PacketValidationError(f"artifact hash mismatch: {relative}")
    if manifest["real_gold_annotation_started"]:
        raise PacketValidationError("manifest says real annotation started")
    audit = read_json(OUTPUT / "p7a_packet_export.audit.json")
    if audit["scope"]["real_gold_created"] or audit["scope"]["product_pipeline_calls"]:
        raise PacketValidationError("audit records forbidden P7A work")
    # P7A owns the packet-export tree, while later accepted lifecycle steps may
    # add sibling directories under the same historical output root.
    for path in OUTPUT.rglob("*"):
        relative_parts = path.relative_to(OUTPUT).parts
        if "development_cycle" in relative_parts or "frozen_cycle_v1" in relative_parts:
            continue
        name = path.name.lower()
        if path.is_file() and ".template." not in name and (
            name.startswith("retrieval_gold.")
            or name.startswith("evidence_gold.")
            or name.startswith("sufficiency_gold.")
        ):
            raise PacketValidationError("real Gold file found in P7A output")


def validate_packet_export() -> None:
    validate_input_identity()
    validate_navigation_bundle()
    validate_transcript_catalog()
    validate_batches()
    validate_prompts_and_guard()
    validate_governance_hashes()


def main() -> int:
    global OUTPUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=OUTPUT)
    args = parser.parse_args()
    OUTPUT = args.root.resolve()
    validate_packet_export()
    print("P7A packet export validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
