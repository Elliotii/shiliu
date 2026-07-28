"""Minimal structural and cross-object validator for Product Query Gold Protocol v1.

This module validates synthetic fixtures and future annotation records. It does
not build Gold, read transcripts, run retrieval, or evaluate system output.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = {"sufficient", "partial", "insufficient", "unverifiable"}
AUTHORITATIVE_SOURCE_TYPES = {"official_subtitle", "asr_transcript"}
DOWNSTREAM_FAILURE_PREFIXES = ("RET_", "BLD_", "SEL_", "GATE_", "JDG_", "SRC_")


class GoldProtocolValidationError(ValueError):
    """Raised when a Gold Protocol object violates a frozen invariant."""


def _require_keys(record: dict[str, Any], keys: set[str], label: str) -> None:
    missing = sorted(keys - record.keys())
    if missing:
        raise GoldProtocolValidationError(f"{label} missing required fields: {missing}")


def _require_unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise GoldProtocolValidationError(f"{label} must contain unique values")


def _reject_downstream_codes(reason_codes: list[str]) -> None:
    forbidden = [code for code in reason_codes if code.startswith(DOWNSTREAM_FAILURE_PREFIXES)]
    if forbidden:
        raise GoldProtocolValidationError(
            f"Gold objects may not use downstream failure codes: {forbidden}"
        )


def validate_retrieval(record: dict[str, Any]) -> None:
    _require_keys(
        record,
        {
            "query_id",
            "gold_version",
            "known_relevant_video_ids",
            "acceptable_video_ids",
            "hard_negative_video_ids",
            "relevance_review_scope",
            "exhaustive",
            "review_state",
            "reason_codes",
            "unjudged_outside_pool_is_negative",
        },
        "retrieval Gold",
    )
    if record["exhaustive"] is not False:
        raise GoldProtocolValidationError("retrieval exhaustive must be false")
    if record["unjudged_outside_pool_is_negative"] is not False:
        raise GoldProtocolValidationError("unjudged outside-pool videos are not negatives")
    known = set(record["known_relevant_video_ids"])
    acceptable = set(record["acceptable_video_ids"])
    hard_negative = set(record["hard_negative_video_ids"])
    if not known <= acceptable:
        raise GoldProtocolValidationError("known relevant videos must be acceptable")
    if hard_negative & acceptable:
        raise GoldProtocolValidationError("hard negatives must be disjoint from positives")
    scope = record["relevance_review_scope"]
    _require_keys(
        scope,
        {
            "pool_version",
            "reviewed_video_ids",
            "pool_construction_method",
            "review_authority",
            "review_timestamp",
        },
        "relevance review scope",
    )
    if not hard_negative <= set(scope["reviewed_video_ids"]):
        raise GoldProtocolValidationError("hard negatives require explicit human review")
    _reject_downstream_codes(record["reason_codes"])


def validate_evidence(record: dict[str, Any]) -> None:
    _require_keys(
        record,
        {
            "query_id",
            "gold_version",
            "required_aspects",
            "aspect_evidence_options",
            "acceptable_evidence_groups_logic",
            "acceptable_evidence_groups",
            "span_registry",
            "optional_context_spans",
            "source_review_state",
            "review_state",
            "reason_codes",
            "builder_or_retrieval_output_limits_gold",
        },
        "evidence Gold",
    )
    if record["acceptable_evidence_groups_logic"] != "OR":
        raise GoldProtocolValidationError("acceptable evidence groups must use OR")
    if record["builder_or_retrieval_output_limits_gold"] is not False:
        raise GoldProtocolValidationError("Builder/Retrieval output may not limit evidence Gold")

    aspect_ids = [aspect["aspect_id"] for aspect in record["required_aspects"]]
    _require_unique(aspect_ids, "aspect IDs")
    material_ids = {
        aspect["aspect_id"]
        for aspect in record["required_aspects"]
        if aspect["materiality"] == "material"
    }
    if not material_ids:
        raise GoldProtocolValidationError("at least one material aspect is required")

    spans = {span["span_id"]: span for span in record["span_registry"]}
    _require_unique(list(spans), "span IDs")
    required_span_fields = {
        "span_id",
        "video_id",
        "segment_ids",
        "start_time",
        "end_time",
        "quote_text",
        "source_language",
        "source_type",
        "source_version",
        "timeline_run_id",
        "segment_identity_version",
        "source_quality_flag",
        "translated_gloss",
    }
    for span in spans.values():
        _require_keys(span, required_span_fields, "evidence span")
        if span["source_type"] not in AUTHORITATIVE_SOURCE_TYPES:
            raise GoldProtocolValidationError("Gold evidence must use transcript authority")
        if span["end_time"] < span["start_time"]:
            raise GoldProtocolValidationError("span end_time must not precede start_time")
        if not span["segment_ids"]:
            raise GoldProtocolValidationError("span segment_ids must be replayable")

    option_aspects: set[str] = set()
    for option in record["aspect_evidence_options"]:
        aspect_id = option["aspect_id"]
        if aspect_id not in aspect_ids:
            raise GoldProtocolValidationError("aspect evidence references an unknown aspect")
        option_aspects.add(aspect_id)
        if option["alternative_sets_between"] != "OR":
            raise GoldProtocolValidationError("alternative aspect evidence sets must use OR")
        if option["required_spans_within_set"] != "AND":
            raise GoldProtocolValidationError("required spans inside a set must use AND")
        for evidence_set in option["alternative_sets"]:
            required = evidence_set["required_span_ids"]
            if not required:
                raise GoldProtocolValidationError("aspect evidence set needs a required span")
            if not set(required) <= spans.keys():
                raise GoldProtocolValidationError("aspect evidence references an unknown span")

    group_ids: list[str] = []
    for group in record["acceptable_evidence_groups"]:
        group_ids.append(group["group_id"])
        if group["required_span_sets_within_group"] != "AND":
            raise GoldProtocolValidationError("required span sets inside a group must use AND")
        required_sets = group["required_span_sets"]
        if not required_sets:
            raise GoldProtocolValidationError("complete evidence group needs required span sets")
        for required_set in required_sets:
            required = required_set["required_span_ids"]
            if not required or not set(required) <= spans.keys():
                raise GoldProtocolValidationError("evidence group has invalid required spans")
    _require_unique(group_ids, "evidence group IDs")

    optional = set(record["optional_context_spans"])
    if not optional <= spans.keys():
        raise GoldProtocolValidationError("optional context references an unknown span")
    required_ids = {
        span_id
        for option in record["aspect_evidence_options"]
        for evidence_set in option["alternative_sets"]
        for span_id in evidence_set["required_span_ids"]
    }
    if optional & required_ids:
        raise GoldProtocolValidationError("optional context cannot replace required spans")
    _reject_downstream_codes(record["reason_codes"])


def validate_sufficiency(record: dict[str, Any]) -> None:
    _require_keys(
        record,
        {
            "query_id",
            "gold_version",
            "status",
            "material_aspect_ids",
            "supported_aspects",
            "missing_aspects",
            "reason_codes",
            "evidence_group_ids_used",
            "gold_policy_version",
            "review_state",
            "authoritative_sources_reviewable",
        },
        "sufficiency Gold",
    )
    status = record["status"]
    if status not in ALLOWED_STATUSES:
        raise GoldProtocolValidationError(f"invalid sufficiency status: {status}")
    material = set(record["material_aspect_ids"])
    supported = set(record["supported_aspects"])
    missing = set(record["missing_aspects"])
    if not material:
        raise GoldProtocolValidationError("material_aspect_ids must not be empty")
    if supported & missing:
        raise GoldProtocolValidationError("supported and missing aspects must be disjoint")
    if not (supported | missing) <= material:
        raise GoldProtocolValidationError("sufficiency aspects must reference material aspects")
    reviewable = record["authoritative_sources_reviewable"]

    if status == "sufficient":
        valid = reviewable is True and supported == material and not missing
    elif status == "partial":
        valid = bool(supported) and bool(missing) and supported | missing == material
    elif status == "insufficient":
        valid = reviewable is True and not supported and missing == material
    else:
        valid = reviewable is False and not supported and missing == material
    if not valid:
        raise GoldProtocolValidationError(f"{status} boundary conditions are not satisfied")
    _reject_downstream_codes(record["reason_codes"])


def validate_three_layer(
    retrieval: dict[str, Any],
    evidence: dict[str, Any],
    sufficiency: dict[str, Any],
) -> None:
    validate_retrieval(retrieval)
    validate_evidence(evidence)
    validate_sufficiency(sufficiency)
    query_ids = {retrieval["query_id"], evidence["query_id"], sufficiency["query_id"]}
    if len(query_ids) != 1:
        raise GoldProtocolValidationError("three Gold layers must share one query_id")
    aspect_ids = {aspect["aspect_id"] for aspect in evidence["required_aspects"]}
    if not set(sufficiency["material_aspect_ids"]) <= aspect_ids:
        raise GoldProtocolValidationError("sufficiency references unknown material aspects")
    group_ids = {group["group_id"] for group in evidence["acceptable_evidence_groups"]}
    if not set(sufficiency["evidence_group_ids_used"]) <= group_ids:
        raise GoldProtocolValidationError("sufficiency references unknown evidence groups")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--sufficiency", type=Path)
    args = parser.parse_args()
    supplied = [args.retrieval, args.evidence, args.sufficiency]
    if all(supplied):
        validate_three_layer(*(_load(path) for path in supplied))
    elif sum(path is not None for path in supplied) == 1:
        path = next(path for path in supplied if path is not None)
        record = _load(path)
        if args.retrieval:
            validate_retrieval(record)
        elif args.evidence:
            validate_evidence(record)
        else:
            validate_sufficiency(record)
    else:
        parser.error("provide exactly one layer, or all three layers")
    print("Product Query Gold Protocol v1 validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
