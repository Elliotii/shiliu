"""Aggregate-only validator for the Shiliu Frozen Gold Cycle v1.

The validator reads protected case records internally but never emits case-level
values, paths, identifiers, labels, evidence, or validation details. CLI output
is a single aggregate JSON object.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


EXPECTED_LEDGER_SHA256 = "9d37f019ed0ef302c56070e939a024c96546195ebde1236fdb5b30c5d5d78ee8"
EXPECTED_SPLIT_ASSIGNMENT_SHA256 = (
    "3014e941a385022abf0bef99c6d9f1d0b82b6d5e7a0b2a22d6977189c8f85239"
)
EXPECTED_FROZEN_LOCKED_SHA256 = (
    "faf962049281cba4c8a035e64068ef91b7cfa9159ea438cfe33052a225add44f"
)
EXPECTED_P7A_GUARD_SHA256 = (
    "aad5e437cb49ccae62b9a72ccd706da827a6235089c045ef2688fe4bbe8c7f10"
)
EXPECTED_INDEPENDENT_SEAL_SHA256 = (
    "97eff00429cfaa62ca414793d45503149ddeda887c1301ede176081dca77073d"
)
EXPECTED_QUERY_COUNT = 10
EXPECTED_BATCH_COUNT = 5
ALLOWED_OUTCOMES = {"agree", "revise_gold", "escalate", "blocked_by_source"}
AUTHORITATIVE_SOURCE_TYPES = {"official_subtitle", "asr_transcript"}
DOWNSTREAM_PREFIXES = ("RET_", "BLD_", "SEL_", "GATE_", "JDG_", "SRC_")
COMPLETION_FIELDS = {
    "input_identity_verified",
    "frozen_query_count",
    "guarded_batch_count",
    "annotator_unit_count",
    "reviewer_unit_count",
    "reviewer_independent_draft_seal_valid",
    "reviewed_case_count",
    "aggregate_outcomes",
    "pending_user_adjudication",
    "three_layer_validation",
    "evidence_spans_replayed",
    "replay_failures",
    "sealed_artifact_hashes",
    "byte_identical_copy",
    "semantic_fields_changed_by_orchestrator",
    "frozen_gold_leakage_detected",
    "development_gold_read_by_semantic_units",
    "product_prediction_read",
    "product_pipeline_calls",
    "p8_started",
    "acceptance_status",
    "current_codex_session_can_close",
}
FORBIDDEN_COMPLETION_TOKENS = (
    "PQS_V1_Q",
    "bilibili:",
    "quote_text",
    "required_aspects",
    "supported_aspects",
    "missing_aspects",
    "reason_codes",
    "span_registry",
    "known_relevant_video_ids",
    "acceptable_video_ids",
    "hard_negative_video_ids",
)


class FrozenCycleValidationError(ValueError):
    """An aggregate-safe Frozen Cycle validation failure."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


def _fail(category: str) -> None:
    raise FrozenCycleValidationError(category)


def sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        _fail("artifact_identity_failure")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _fail("artifact_structure_failure")
    if not isinstance(value, dict):
        _fail("artifact_structure_failure")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        values = [json.loads(line) for line in lines if line.strip()]
    except (OSError, json.JSONDecodeError):
        _fail("artifact_structure_failure")
    if not all(isinstance(value, dict) for value in values):
        _fail("artifact_structure_failure")
    return values


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _segment_id(artifact_id: str, version: str, ordinal: int) -> str:
    payload = {
        "original_ordinal": ordinal,
        "source_artifact_id": artifact_id,
        "source_version": version,
    }
    return "segment_" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _validate_schema(value: Any, schema: dict[str, Any]) -> None:
    expected_type = schema.get("type")
    if expected_type is not None:
        allowed = [expected_type] if isinstance(expected_type, str) else expected_type
        if not any(_type_matches(value, item) for item in allowed):
            _fail("p6_schema_validation_failure")
    if "const" in schema and value != schema["const"]:
        _fail("p6_schema_validation_failure")
    if "enum" in schema and value not in schema["enum"]:
        _fail("p6_schema_validation_failure")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            _fail("p6_schema_validation_failure")
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                _fail("p6_schema_validation_failure")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            _fail("p6_schema_validation_failure")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            _fail("p6_schema_validation_failure")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            _fail("p6_schema_validation_failure")
        if schema.get("uniqueItems") and len({_canonical(item) for item in value}) != len(value):
            _fail("p6_schema_validation_failure")
        if isinstance(schema.get("items"), dict):
            for item in value:
                _validate_schema(item, schema["items"])
    if isinstance(value, dict):
        required = set(schema.get("required", []))
        if not required <= value.keys():
            _fail("p6_schema_validation_failure")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and not set(value) <= set(properties):
            _fail("p6_schema_validation_failure")
        for key, child_schema in properties.items():
            if key in value:
                _validate_schema(value[key], child_schema)
    for constraint in schema.get("allOf", []):
        condition = constraint.get("if")
        if condition is None or _schema_matches(value, condition):
            if "then" in constraint:
                _validate_schema(value, constraint["then"])


def _schema_matches(value: Any, schema: dict[str, Any]) -> bool:
    try:
        _validate_schema(value, schema)
        return True
    except FrozenCycleValidationError:
        return False


def validate_reviewer_seal(seal: dict[str, Any]) -> None:
    required = {
        "initial_annotation_opened": False,
        "independent_draft_complete": True,
        "independent_draft_mutable_after_seal": False,
        "case_count": EXPECTED_QUERY_COUNT,
        "guarded_batch_count": EXPECTED_BATCH_COUNT,
        "gold_layers_complete": True,
    }
    if any(seal.get(key) != expected for key, expected in required.items()):
        _fail("reviewer_isolation_failure")
    counts = seal.get("three_layer_counts", {})
    if counts != {
        "retrieval_gold": EXPECTED_QUERY_COUNT,
        "evidence_gold": EXPECTED_QUERY_COUNT,
        "sufficiency_gold": EXPECTED_QUERY_COUNT,
    }:
        _fail("reviewer_isolation_failure")


def validate_p5_identity(root: Path, query_ids: Iterable[str]) -> None:
    split_root = root / "research/v3_5/product_query_set_v1/split_v1"
    locked = read_json(split_root / "product_query_split_v1.locked.json")
    manifest = read_json(split_root / "product_query_split_v1.manifest.json")
    frozen_path = split_root / "frozen_locked/product_query_frozen_evaluation_v1.locked.jsonl"
    if locked.get("canonical_assignment_sha256") != EXPECTED_SPLIT_ASSIGNMENT_SHA256:
        _fail("p5_identity_failure")
    if manifest.get("output_hashes", {}).get("frozen_evaluation_jsonl") != (
        EXPECTED_FROZEN_LOCKED_SHA256
    ):
        _fail("p5_identity_failure")
    if sha256(frozen_path) != EXPECTED_FROZEN_LOCKED_SHA256:
        _fail("p5_identity_failure")
    expected = set(locked.get("frozen_evaluation", {}).get("query_ids", []))
    actual = list(query_ids)
    if len(actual) != EXPECTED_QUERY_COUNT or len(set(actual)) != EXPECTED_QUERY_COUNT:
        _fail("p5_identity_failure")
    if set(actual) != expected:
        _fail("p5_identity_failure")


def validate_three_layer_records(
    root: Path,
    retrieval_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    sufficiency_rows: list[dict[str, Any]],
) -> None:
    if not (
        len(retrieval_rows)
        == len(evidence_rows)
        == len(sufficiency_rows)
        == EXPECTED_QUERY_COUNT
    ):
        _fail("three_layer_count_failure")
    p6 = root / "research/v3_5/product_query_set_v1/gold_protocol_v1"
    schemas = {
        "retrieval": read_json(p6 / "product_retrieval_gold.schema.json"),
        "evidence": read_json(p6 / "product_evidence_gold.schema.json"),
        "sufficiency": read_json(p6 / "product_sufficiency_gold.schema.json"),
    }
    scripts_path = str(root / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    try:
        from validate_product_gold_protocol_v1 import (  # type: ignore
            GoldProtocolValidationError,
            validate_three_layer,
        )
    except ImportError:
        _fail("p6_validator_unavailable")
    evidence_by_id = {row.get("query_id"): row for row in evidence_rows}
    sufficiency_by_id = {row.get("query_id"): row for row in sufficiency_rows}
    if len(evidence_by_id) != EXPECTED_QUERY_COUNT or len(sufficiency_by_id) != EXPECTED_QUERY_COUNT:
        _fail("three_layer_identity_failure")
    for retrieval in retrieval_rows:
        query_id = retrieval.get("query_id")
        if query_id not in evidence_by_id or query_id not in sufficiency_by_id:
            _fail("three_layer_identity_failure")
        evidence = evidence_by_id[query_id]
        sufficiency = sufficiency_by_id[query_id]
        _validate_schema(retrieval, schemas["retrieval"])
        _validate_schema(evidence, schemas["evidence"])
        _validate_schema(sufficiency, schemas["sufficiency"])
        try:
            validate_three_layer(retrieval, evidence, sufficiency)
        except GoldProtocolValidationError:
            _fail("p6_cross_object_validation_failure")
        for record in (retrieval, evidence, sufficiency):
            if any(
                isinstance(code, str) and code.startswith(DOWNSTREAM_PREFIXES)
                for code in record.get("reason_codes", [])
            ):
                _fail("downstream_code_failure")
        if evidence.get("builder_or_retrieval_output_limits_gold") is not False:
            _fail("product_output_contamination")
        source_state = evidence.get("source_review_state", {})
        if source_state.get("navigation_sources_used_as_gold_evidence") is not False:
            _fail("navigation_evidence_failure")
        if source_state.get("full_authoritative_transcript_reviewed") is not True:
            _fail("source_review_failure")


def replay_evidence(
    root: Path,
    evidence_rows: list[dict[str, Any]],
) -> int:
    catalog_path = (
        root
        / "research/v3_5/product_query_set_v1/gold_construction_v1/shared"
        / "authoritative_transcript_identity_catalog.jsonl"
    )
    catalog = {row["video_id"]: row for row in read_jsonl(catalog_path)}
    transcript_cache: dict[str, list[dict[str, Any]]] = {}
    replayed = 0
    for evidence in evidence_rows:
        for span in evidence.get("span_registry", []):
            source = catalog.get(span.get("video_id"))
            if source is None:
                _fail("evidence_replay_failure")
            if span.get("source_type") not in AUTHORITATIVE_SOURCE_TYPES:
                _fail("navigation_evidence_failure")
            if (
                span.get("source_type") != source.get("source_type")
                or span.get("source_version") != source.get("source_version")
                or span.get("segment_identity_version") != source.get("segment_identity_version")
                or span.get("timeline_run_id") not in source.get("timeline_run_ids", [])
            ):
                _fail("evidence_replay_failure")
            source_path = Path(source["source_path"])
            if sha256(source_path) != source.get("source_version"):
                _fail("evidence_replay_failure")
            cache_key = source["source_version"]
            if cache_key not in transcript_cache:
                try:
                    payload = json.loads(source_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    _fail("evidence_replay_failure")
                if not isinstance(payload, list) or len(payload) != source.get("segment_count"):
                    _fail("evidence_replay_failure")
                transcript_cache[cache_key] = payload
            transcript = transcript_cache[cache_key]
            matching_ranges: list[tuple[int, list[dict[str, Any]]]] = []
            for start_index, segment in enumerate(transcript):
                if segment.get("from") != span.get("start_time"):
                    continue
                combined = ""
                selected: list[dict[str, Any]] = []
                for candidate in transcript[start_index:]:
                    selected.append(candidate)
                    combined += str(candidate.get("content", ""))
                    if candidate.get("to") == span.get("end_time"):
                        if combined == span.get("quote_text"):
                            matching_ranges.append((start_index, selected.copy()))
                        break
                    if len(combined) > len(str(span.get("quote_text", ""))):
                        break
            if len(matching_ranges) != 1:
                _fail("evidence_replay_failure")
            start_index, selected = matching_ranges[0]
            segment_ids = span.get("segment_ids", [])
            expected_segment_ids = [
                _segment_id(
                    source["source_artifact_id"],
                    source["source_version"],
                    start_index + offset,
                )
                for offset in range(len(selected))
            ]
            if (
                not isinstance(segment_ids, list)
                or segment_ids != expected_segment_ids
            ):
                _fail("evidence_replay_failure")
            replayed += 1
    return replayed


def _paths(root: Path) -> dict[str, Path]:
    cycle = (
        root
        / "research/v3_5/product_query_set_v1/gold_construction_v1"
        / "frozen_guarded/frozen_cycle_v1"
    )
    return {
        "cycle": cycle,
        "candidate": cycle / "reviewed_gold_candidate",
        "sealed": cycle / "sealed",
        "internal": cycle / "internal_protected",
        "completion": cycle / "completion_only",
        "comparison": cycle / "review/comparison",
        "independent": cycle / "review/independent_draft",
        "initial": cycle / "annotation/initial",
        "guard": cycle.parent / "FROZEN_PACKET_ACCESS_GUARD.json",
    }


def validate_frozen_cycle(root: Path) -> dict[str, Any]:
    paths = _paths(root)
    cycle_ledger = paths["cycle"] / "PQS_V1_FROZEN_GOLD_CYCLE_DECISION_LEDGER.json"
    if sha256(cycle_ledger) != EXPECTED_LEDGER_SHA256:
        _fail("ledger_identity_failure")
    independent_seal_path = paths["independent"] / "independent_draft.seal.json"
    if sha256(independent_seal_path) != EXPECTED_INDEPENDENT_SEAL_SHA256:
        _fail("reviewer_seal_identity_failure")
    validate_reviewer_seal(read_json(independent_seal_path))
    comparison = read_json(paths["comparison"] / "comparison.manifest.json")
    outcomes = comparison.get("outcome_counts", {})
    if (
        comparison.get("case_count") != EXPECTED_QUERY_COUNT
        or outcomes.get("agree") != EXPECTED_QUERY_COUNT
        or any(outcomes.get(name, 0) for name in ALLOWED_OUTCOMES - {"agree"})
        or comparison.get("replacement_artifact_count") != 0
    ):
        _fail("unresolved_comparison_failure")
    candidate_names = {
        "retrieval": "product_retrieval_gold.frozen.v1.reviewed.jsonl",
        "evidence": "product_evidence_gold.frozen.v1.reviewed.jsonl",
        "sufficiency": "product_sufficiency_gold.frozen.v1.reviewed.jsonl",
        "status": "reviewed_case_status.frozen.v1.jsonl",
    }
    sealed_names = {
        "retrieval": "product_retrieval_gold.frozen.v1.sealed.jsonl",
        "evidence": "product_evidence_gold.frozen.v1.sealed.jsonl",
        "sufficiency": "product_sufficiency_gold.frozen.v1.sealed.jsonl",
        "status": "reviewed_case_status.frozen.v1.sealed.jsonl",
    }
    retrieval = read_jsonl(paths["candidate"] / candidate_names["retrieval"])
    evidence = read_jsonl(paths["candidate"] / candidate_names["evidence"])
    sufficiency = read_jsonl(paths["candidate"] / candidate_names["sufficiency"])
    statuses = read_jsonl(paths["candidate"] / candidate_names["status"])
    if len(statuses) != EXPECTED_QUERY_COUNT or any(
        row.get("resolution_status") != "resolved" for row in statuses
    ):
        _fail("review_status_failure")
    query_ids = [row.get("query_id") for row in retrieval]
    validate_p5_identity(root, query_ids)
    validate_three_layer_records(root, retrieval, evidence, sufficiency)
    replayed = replay_evidence(root, evidence)
    for layer in candidate_names:
        if (paths["candidate"] / candidate_names[layer]).read_bytes() != (
            paths["sealed"] / sealed_names[layer]
        ).read_bytes():
            _fail("byte_identity_failure")
    file_hash_rows = read_jsonl(
        paths["internal"] / "frozen_gold_v1.file_hash_manifest.jsonl"
    )
    for row in file_hash_rows:
        relative = row.get("path")
        expected = row.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            _fail("hash_manifest_failure")
        target = paths["cycle"] / relative
        if sha256(target) != expected:
            _fail("hash_manifest_failure")
    seal = read_json(paths["internal"] / "frozen_gold_v1.seal.json")
    if (
        seal.get("status") != "sealed_execution_candidate"
        or seal.get("acceptance_status") != "pending_v3_5_b_review"
        or seal.get("case_count") != EXPECTED_QUERY_COUNT
        or seal.get("pending_user_adjudication") != 0
    ):
        _fail("seal_state_failure")
    completion_json = paths["completion"] / "FROZEN_GOLD_V1_COMPLETION_STATUS.json"
    completion_md = paths["completion"] / "FROZEN_GOLD_V1_COMPLETION_RESPONSE.md"
    completion = read_json(completion_json)
    response = read_json(completion_md)
    if set(completion) != COMPLETION_FIELDS or response != completion:
        _fail("completion_contract_failure")
    completion_text = completion_md.read_text(encoding="utf-8")
    if any(token in completion_text for token in FORBIDDEN_COMPLETION_TOKENS):
        _fail("completion_leakage_failure")
    if (
        completion.get("p8_started") is not False
        or completion.get("product_pipeline_calls") != 0
        or completion.get("semantic_fields_changed_by_orchestrator") is not False
        or completion.get("frozen_gold_leakage_detected") is not False
    ):
        _fail("scope_failure")
    guard = read_json(paths["guard"])
    if guard.get("status") != "sealed_execution_candidate":
        _fail("guard_state_failure")
    transition_path = paths["cycle"] / "guard_transition.sealed_execution_candidate.json"
    transition = read_json(transition_path)
    if (
        transition.get("previous_guard_sha256") != EXPECTED_P7A_GUARD_SHA256
        and transition.get("entry_guard_sha256") != EXPECTED_P7A_GUARD_SHA256
    ):
        # The entry Guard may legitimately include the accepted Phase 1A transition;
        # its P7A predecessor must still be preserved in the transition chain.
        history = transition.get("preserved_transition_history", [])
        if not any(
            item.get("previous_guard_sha256") == EXPECTED_P7A_GUARD_SHA256
            for item in history
            if isinstance(item, dict)
        ):
            _fail("guard_identity_failure")
    if transition.get("new_guard_sha256") != sha256(paths["guard"]):
        _fail("guard_identity_failure")
    return {
        "status": "passed",
        "case_count": EXPECTED_QUERY_COUNT,
        "guarded_batch_count": EXPECTED_BATCH_COUNT,
        "three_layer_record_count": EXPECTED_QUERY_COUNT * 3,
        "evidence_spans_replayed": replayed,
        "replay_failures": 0,
        "pending_user_adjudication": 0,
        "byte_identical_copy": True,
        "scope_violation_count": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = validate_frozen_cycle(args.root.resolve())
    except FrozenCycleValidationError as exc:
        print(
            json.dumps(
                {"status": "blocked", "category": exc.category},
                sort_keys=True,
            )
        )
        return 1
    except Exception:
        print(json.dumps({"status": "blocked", "category": "aggregate_validation_failure"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
