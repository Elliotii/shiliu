"""P8 Attempt 3 scoring amendment over immutable persisted artifacts.

This module never invokes Retrieval, Candidate Builder, Selector, Gate, or a
prediction runner.  It verifies the existing Prediction Seal, reads the
already-persisted Predictions and Traces, opens only sealed Development Gold,
and writes a versioned scoring amendment beside the preserved original score.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


AMENDMENT_VERSION = "v3.5-p8-scoring-amendment-v1"
SCORING_SCHEMA_VERSION = "v3.5-p8-scoring-eligibility-v2"
ATTEMPT_ID = "P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_3"
PREDICTION_SEAL_SHA256 = "069fcf9e3ec70cf28d23674a2752033e608bf46937c990176dd6fb52f9e04617"
PREDICTIONS_SHA256 = "b34f173ac99208f4adb72966880ab7e9cf97d3e27157084792502f103e709038"
TRACE_ROOT_SHA256 = "f8636d55680e4e3ef72b196f31afe8743c692d48c66ed0a647443679e7353071"
DEVELOPMENT_GOLD_SEAL_SHA256 = "1010fb635680bacc72c9aac8cbd096494370cd0709ed1d746754a0eade90cb5a"
GOLD_HASHES = {
    "retrieval": "b34188c269bf3a2410f8602fdb7d72908a96c822ac3b8f675d4f4c2b72b45679",
    "evidence": "b259a1b225a48558f5d1a6c4cb4909ea413e86116a1564b3fa724632ae88efc1",
    "sufficiency": "11196158746bb2c12e457fcb36b87a1621e79dca0b2f628a4870ca5ec6c5de92",
    "case_status": "9ba38a1f8cf636ebb9e80219cd85a41003743cb11f370a24d3946534378c6352",
}
SOURCE_TERMINAL_CODES = frozenset(
    {
        "no_supported_subtitle",
        "raw_source_unavailable",
        "source_unavailable",
        "source_unreadable",
        "title_only",
        "language_unresolved",
    }
)
PRIMARY_ENUM = frozenset(
    {
        "retrieval_failure",
        "retrieval_gold_unjudged",
        "candidate_builder_failure",
        "deterministic_selector_failure",
        "mechanical_gate_failure",
        "source_unverifiable",
        "gold_defined_evidence_absent",
        "identity_or_scoring_defect",
        "end_to_end_bundle_hit",
    }
)


class AmendmentBlocked(RuntimeError):
    """Raised when immutable identity or one-primary-outcome checks fail."""


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def value_sha256(value: object) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    values = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for row in values
        )
        + ("\n" if values else ""),
        encoding="utf-8",
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical_video_id(value: object) -> str:
    text = str(value)
    if text.startswith("bilibili:"):
        return text
    if text.startswith("BV"):
        return f"bilibili:{text}"
    return text


def mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def latency(rows: Sequence[Mapping[str, Any]], stage: str) -> dict[str, float | None]:
    values = sorted(float(row[stage]["latency_ms"]) for row in rows)
    return {
        "mean_ms": mean(values),
        "min_ms": values[0] if values else None,
        "max_ms": values[-1] if values else None,
    }


def trace_root_hash(trace_rows: Sequence[Mapping[str, Any]]) -> str:
    return value_sha256(
        [{"path": row["path"], "sha256": row["sha256"]} for row in trace_rows]
    )


def verify_prediction_identity(baseline_root: Path) -> dict[str, Any]:
    blind = baseline_root / "blind_run"
    seal_path = blind / "product_initial_baseline.prediction_freeze.seal.json"
    predictions_path = blind / "product_initial_baseline.predictions.jsonl"
    hash_manifest_path = blind / "product_initial_baseline.prediction_hash_manifest.jsonl"
    seal = load_json(seal_path)
    hash_rows = load_jsonl(hash_manifest_path)
    mismatches = [
        row["path"]
        for row in hash_rows
        if file_sha256(baseline_root / row["path"]) != row["sha256"]
    ]
    traces = [row for row in hash_rows if row["path"].endswith(".trace.json")]
    checks = {
        "prediction_seal_sha256": file_sha256(seal_path),
        "predictions_sha256": file_sha256(predictions_path),
        "trace_root_sha256": trace_root_hash(traces),
        "prediction_count": len(load_jsonl(predictions_path)),
        "trace_count": len(traces),
        "prediction_hash_manifest_mismatches": mismatches,
        "seal_status": seal.get("status"),
        "seal_development_gold_opened": seal.get("development_gold_opened"),
        "seal_frozen_gold_opened": seal.get("frozen_gold_opened"),
    }
    if checks != {
        "prediction_seal_sha256": PREDICTION_SEAL_SHA256,
        "predictions_sha256": PREDICTIONS_SHA256,
        "trace_root_sha256": TRACE_ROOT_SHA256,
        "prediction_count": 14,
        "trace_count": 14,
        "prediction_hash_manifest_mismatches": [],
        "seal_status": "sealed_before_gold_scoring",
        "seal_development_gold_opened": False,
        "seal_frozen_gold_opened": False,
    }:
        raise AmendmentBlocked(f"Frozen Prediction identity mismatch: {checks}")
    return checks


def gold_paths(repository_root: Path) -> dict[str, Path]:
    sealed = (
        repository_root
        / "research/v3_5/product_query_set_v1/gold_construction_v1/"
        "development_seal_v1/sealed"
    )
    return {
        "retrieval": sealed / "product_retrieval_gold.development.v1.sealed.jsonl",
        "evidence": sealed / "product_evidence_gold.development.v1.sealed.jsonl",
        "sufficiency": sealed / "product_sufficiency_gold.development.v1.sealed.jsonl",
        "case_status": sealed / "reviewed_case_status.development.v1.sealed.jsonl",
    }


def verify_development_gold_identity(repository_root: Path) -> dict[str, Any]:
    paths = gold_paths(repository_root)
    hashes = {name: file_sha256(path) for name, path in paths.items()}
    seal_path = (
        repository_root
        / "research/v3_5/product_query_set_v1/gold_construction_v1/"
        "development_seal_v1/development_gold_v1.seal.json"
    )
    seal_hash = file_sha256(seal_path)
    counts = {name: len(load_jsonl(path)) for name, path in paths.items()}
    if hashes != GOLD_HASHES or seal_hash != DEVELOPMENT_GOLD_SEAL_SHA256:
        raise AmendmentBlocked(
            f"Development Gold identity mismatch: hashes={hashes}, seal={seal_hash}"
        )
    if set(counts.values()) != {14}:
        raise AmendmentBlocked(f"Development Gold layer counts mismatch: {counts}")
    return {
        "development_gold_version": "DEVELOPMENT_GOLD_V1",
        "development_gold_seal_sha256": seal_hash,
        "development_gold_hashes": hashes,
        "development_gold_layer_counts": counts,
    }


def covered_span_ids(
    evidence: Mapping[str, Any],
    candidate_spans: Sequence[Mapping[str, Any]],
) -> set[str]:
    covered: set[str] = set()
    for gold_span in evidence.get("span_registry", []):
        required = set(gold_span["segment_ids"])
        available = set().union(
            *(
                set(candidate.get("segment_ids", []))
                for candidate in candidate_spans
                if (
                    str(candidate.get("source_version"))
                    == str(gold_span["source_version"])
                    and str(candidate.get("timeline_run_id"))
                    == str(gold_span["timeline_run_id"])
                )
            ),
            set(),
        )
        if required.issubset(available):
            covered.add(str(gold_span["span_id"]))
    return covered


def complete_groups(evidence: Mapping[str, Any], covered_spans: set[str]) -> list[str]:
    return [
        str(group["group_id"])
        for group in evidence.get("acceptable_evidence_groups", [])
        if all(
            set(required_set["required_span_ids"]).issubset(covered_spans)
            for required_set in group["required_span_sets"]
        )
    ]


def covered_aspects(evidence: Mapping[str, Any], covered_spans: set[str]) -> list[str]:
    return [
        str(aspect["aspect_id"])
        for aspect in evidence.get("aspect_evidence_options", [])
        if any(
            set(alternative["required_span_ids"]).issubset(covered_spans)
            for alternative in aspect["alternative_sets"]
        )
    ]


def required_material_evidence_constructible(evidence: Mapping[str, Any]) -> bool:
    groups = evidence.get("acceptable_evidence_groups", [])
    if not groups:
        return False
    registered = {
        str(span["span_id"]) for span in evidence.get("span_registry", [])
    }
    material = {
        str(aspect["aspect_id"])
        for aspect in evidence.get("required_aspects", [])
        if aspect.get("materiality") == "material"
    }
    options = {
        str(aspect["aspect_id"]): aspect.get("alternative_sets", [])
        for aspect in evidence.get("aspect_evidence_options", [])
    }
    material_options_valid = all(
        options.get(aspect_id)
        and any(
            alternative.get("required_span_ids")
            and set(map(str, alternative["required_span_ids"])).issubset(registered)
            for alternative in options[aspect_id]
        )
        for aspect_id in material
    )
    groups_valid = all(
        group.get("required_span_sets")
        and all(
            required_set.get("required_span_ids")
            and set(map(str, required_set["required_span_ids"])).issubset(registered)
            for required_set in group["required_span_sets"]
        )
        for group in groups
    )
    return bool(material and material_options_valid and groups_valid)


def gold_defined_evidence_absent(evidence: Mapping[str, Any]) -> bool:
    """Generic terminal for reviewable sources with explicitly absent material evidence."""
    material = {
        str(aspect["aspect_id"])
        for aspect in evidence.get("required_aspects", [])
        if aspect.get("materiality") == "material"
    }
    option_ids = {
        str(aspect["aspect_id"])
        for aspect in evidence.get("aspect_evidence_options", [])
        if aspect.get("alternative_sets")
    }
    return (
        len(evidence.get("acceptable_evidence_groups", [])) == 0
        and bool(material - option_ids)
        and (
            "EG_MATERIAL_ASPECT_MISSING" in evidence.get("reason_codes", [])
            or evidence.get("review_state") == "independent_review_complete"
        )
    )


def metric_contract(
    *,
    numerator: float | int,
    eligible_ids: Sequence[str],
    all_ids: Sequence[str],
    exclusion_reasons: Mapping[str, str],
    definition: str,
) -> dict[str, Any]:
    denominator = len(eligible_ids)
    excluded_ids = [query_id for query_id in all_ids if query_id not in eligible_ids]
    return {
        "value": numerator / denominator if denominator else None,
        "numerator": numerator,
        "denominator": denominator,
        "eligible_query_count": denominator,
        "excluded_query_count": len(excluded_ids),
        "excluded_query_ids": excluded_ids,
        "exclusion_reason": {
            query_id: exclusion_reasons[query_id] for query_id in excluded_ids
        },
        "definition": definition,
    }


def build_per_query(
    *,
    baseline_root: Path,
    predictions: Sequence[Mapping[str, Any]],
    retrieval_gold: Mapping[str, Mapping[str, Any]],
    evidence_gold: Mapping[str, Mapping[str, Any]],
    sufficiency_gold: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for prediction in predictions:
        query_id = str(prediction["query_id"])
        retrieval = retrieval_gold[query_id]
        evidence = evidence_gold[query_id]
        sufficiency = sufficiency_gold[query_id]
        returned = [
            canonical_video_id(value)
            for value in prediction["retrieval"]["returned_video_ids_ranked"]
        ]
        reviewed = {
            canonical_video_id(value)
            for value in retrieval["relevance_review_scope"]["reviewed_video_ids"]
        }
        acceptable = {
            canonical_video_id(value) for value in retrieval["acceptable_video_ids"]
        }
        known = {
            canonical_video_id(value)
            for value in retrieval["known_relevant_video_ids"]
        }
        unresolved_ranks = [
            rank
            for rank, video_id in enumerate(returned, 1)
            if video_id not in reviewed
        ]
        acceptable_ranks = [
            rank
            for rank, video_id in enumerate(returned, 1)
            if video_id in acceptable
        ]
        retrieval_success = bool(acceptable_ranks)
        retrieval_state = (
            "determinate_success"
            if retrieval_success
            else (
                "indeterminate_due_to_unjudged"
                if unresolved_ranks
                else "determinate_failure"
            )
        )

        candidate_spans = prediction["candidate_builder"]["evidence_spans"]
        builder_covered = covered_span_ids(evidence, candidate_spans)
        builder_groups = complete_groups(evidence, builder_covered)
        builder_aspects = covered_aspects(evidence, builder_covered)
        selected_ids = set(
            prediction["deterministic_selector"]["selected_candidate_ids"]
        )
        selected_spans = [
            candidate
            for candidate in candidate_spans
            if candidate["candidate_id"] in selected_ids
        ]
        selected_covered = covered_span_ids(evidence, selected_spans)
        selected_groups = complete_groups(evidence, selected_covered)
        selected_aspects = covered_aspects(evidence, selected_covered)

        required_span_ids = {
            str(span_id)
            for group in evidence.get("acceptable_evidence_groups", [])
            for required_set in group["required_span_sets"]
            for span_id in required_set["required_span_ids"]
        }
        material_aspects = {
            str(aspect["aspect_id"])
            for aspect in evidence.get("required_aspects", [])
            if aspect["materiality"] == "material"
        }
        group_count = len(evidence.get("acceptable_evidence_groups", []))
        constructible = required_material_evidence_constructible(evidence)
        source_reviewable = bool(
            evidence["source_review_state"]["authoritative_sources_reviewable"]
        )
        gate_outcome = prediction["mechanical_gate"]["outcome"]
        gate_reasons = prediction["mechanical_gate"]["reason_codes"]
        source_terminal = bool(
            set(gate_reasons) & SOURCE_TERMINAL_CODES
            or prediction["terminal_prediction"]["recognized_source_terminal"]
        )
        identity_valid = source_terminal or not prediction["candidate_builder"][
            "validation_errors"
        ]

        if not identity_valid:
            primary = "identity_or_scoring_defect"
        elif source_terminal or not source_reviewable:
            primary = "source_unverifiable"
        elif retrieval_state == "indeterminate_due_to_unjudged":
            primary = "retrieval_gold_unjudged"
        elif retrieval_state == "determinate_failure":
            primary = "retrieval_failure"
        elif not constructible:
            if gold_defined_evidence_absent(evidence):
                primary = "gold_defined_evidence_absent"
            else:
                raise AmendmentBlocked(
                    f"Independent scoring defect: nonconstructible Gold is not "
                    f"covered by the generic terminal for {query_id}"
                )
        elif not builder_groups:
            primary = "candidate_builder_failure"
        elif not selected_groups:
            primary = "deterministic_selector_failure"
        elif gate_outcome != "judge_eligible":
            primary = "mechanical_gate_failure"
        else:
            primary = "end_to_end_bundle_hit"

        if primary not in PRIMARY_ENUM:
            raise AmendmentBlocked(f"Unknown primary attribution: {primary}")
        if primary == "candidate_builder_failure" and not (
            retrieval_success
            and source_reviewable
            and not source_terminal
            and group_count > 0
            and constructible
            and not builder_groups
        ):
            raise AmendmentBlocked(
                f"Invalid candidate_builder_failure eligibility for {query_id}"
            )
        if primary == "deterministic_selector_failure" and not (
            builder_groups and not selected_groups
        ):
            raise AmendmentBlocked(
                f"Invalid deterministic_selector_failure eligibility for {query_id}"
            )
        if primary == "end_to_end_bundle_hit" and not selected_groups:
            raise AmendmentBlocked(f"Invalid end_to_end_bundle_hit for {query_id}")

        trace = load_json(
            baseline_root
            / prediction["trace_path"].removeprefix(
                "research/v3_5/product_query_set_v1/"
                "product_initial_baseline_attempt_3/"
            )
        )
        bundle = trace.get("evidence_bundle")
        selected_duration = sum(
            max(
                0.0,
                float(candidate["end_time"]) - float(candidate["start_time"]),
            )
            for candidate in selected_spans
        )
        union_duration = float(bundle.get("union_duration", 0.0)) if bundle else 0.0
        span_recall_builder = (
            len(builder_covered & required_span_ids) / len(required_span_ids)
            if required_span_ids
            else None
        )
        span_recall_selector = (
            len(selected_covered & required_span_ids) / len(required_span_ids)
            if required_span_ids
            else None
        )
        aspect_coverage_builder = (
            len(set(builder_aspects) & material_aspects) / len(material_aspects)
            if constructible and material_aspects
            else None
        )
        aspect_coverage_selector = (
            len(set(selected_aspects) & material_aspects) / len(material_aspects)
            if constructible and material_aspects
            else None
        )
        rows.append(
            {
                "query_id": query_id,
                "prediction_run_id": prediction["run_id"],
                "persisted_assets": {
                    "prediction_sha256": PREDICTIONS_SHA256,
                    "trace_path": prediction["trace_path"],
                    "gate_decision_id": prediction["mechanical_gate"][
                        "gate_decision_id"
                    ],
                },
                "gold_eligibility": {
                    "acceptable_evidence_group_count": group_count,
                    "material_aspect_ids": sorted(material_aspects),
                    "required_material_evidence_constructible": constructible,
                    "sufficiency_gold_status": sufficiency["status"],
                    "authoritative_source_reviewable": source_reviewable,
                    "eligible_for_builder_complete_group_coverage_denominator": constructible,
                    "eligible_for_required_span_recall_denominator": bool(
                        required_span_ids
                    ),
                    "eligible_for_required_aspect_coverage_denominator": constructible,
                    "eligible_for_candidate_builder_failure": (
                        retrieval_success
                        and source_reviewable
                        and not source_terminal
                        and constructible
                    ),
                },
                "retrieval": {
                    "state": retrieval_state,
                    "acceptable_hit": retrieval_success,
                    "first_acceptable_rank": min(acceptable_ranks)
                    if acceptable_ranks
                    else None,
                    **{
                        f"hit_at_{k}": any(rank <= k for rank in acceptable_ranks)
                        for k in (1, 3, 5, 10)
                    },
                    **{
                        f"known_relevant_recall_at_{k}": (
                            len(set(returned[:k]) & known) / len(known)
                            if known
                            else None
                        )
                        for k in (1, 3, 5, 10)
                    },
                    "unjudged_count": len(unresolved_ranks),
                    "unjudged_ranks": unresolved_ranks,
                    "returned_count": len(returned),
                },
                "candidate_builder": {
                    "complete_group_hit": bool(builder_groups),
                    "covered_group_ids": builder_groups,
                    "covered_span_ids": sorted(builder_covered),
                    "required_span_recall": span_recall_builder,
                    "covered_aspect_ids": builder_aspects,
                    "required_aspect_coverage": aspect_coverage_builder,
                    "candidate_count": len(
                        prediction["candidate_builder"]["candidate_ids"]
                    ),
                    "invalid_candidate_count": prediction["candidate_builder"][
                        "invalid_candidate_count"
                    ],
                },
                "deterministic_selector": {
                    "bundle_hit": bool(selected_groups),
                    "covered_group_ids": selected_groups,
                    "complete_group_available_but_not_selected": bool(
                        builder_groups and not selected_groups
                    ),
                    "required_span_recall": span_recall_selector,
                    "required_aspect_coverage": aspect_coverage_selector,
                    "selected_candidate_count": len(selected_ids),
                    "compactness": (
                        union_duration / selected_duration
                        if selected_duration
                        else None
                    ),
                    "redundancy": (
                        1.0 - union_duration / selected_duration
                        if selected_duration
                        else None
                    ),
                },
                "mechanical_gate": {
                    "outcome": gate_outcome,
                    "reason_codes": gate_reasons,
                    "valid_decision": gate_outcome
                    in {"judge_eligible", "terminal_unverifiable"},
                },
                "primary_attribution": primary,
                "decision_sensitive_unjudged": primary
                == "retrieval_gold_unjudged",
            }
        )
    if len(rows) != 14 or len({row["query_id"] for row in rows}) != 14:
        raise AmendmentBlocked("Expected exactly 14 unique amended per-query rows")
    return rows


def build_scores(
    predictions: Sequence[Mapping[str, Any]],
    per_query: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    all_ids = [str(row["query_id"]) for row in per_query]
    complete_ids = [
        row["query_id"]
        for row in per_query
        if row["gold_eligibility"][
            "eligible_for_builder_complete_group_coverage_denominator"
        ]
    ]
    span_ids = [
        row["query_id"]
        for row in per_query
        if row["gold_eligibility"]["eligible_for_required_span_recall_denominator"]
    ]
    aspect_ids = [
        row["query_id"]
        for row in per_query
        if row["gold_eligibility"][
            "eligible_for_required_aspect_coverage_denominator"
        ]
    ]
    builder_failure_ids = [
        row["query_id"]
        for row in per_query
        if row["gold_eligibility"]["eligible_for_candidate_builder_failure"]
    ]
    zero_group_reason = {
        query_id: "zero_acceptable_evidence_groups_and_material_evidence_nonconstructible"
        for query_id in all_ids
        if query_id not in complete_ids
    }
    builder_failure_exclusions = {
        row["query_id"]: (
            "authoritative_source_terminal"
            if row["primary_attribution"] == "source_unverifiable"
            else "required_material_evidence_nonconstructible"
        )
        for row in per_query
        if row["query_id"] not in builder_failure_ids
    }
    complete_numerator = sum(
        row["candidate_builder"]["complete_group_hit"]
        for row in per_query
        if row["query_id"] in complete_ids
    )
    builder_span_sum = sum(
        row["candidate_builder"]["required_span_recall"]
        for row in per_query
        if row["query_id"] in span_ids
    )
    builder_aspect_sum = sum(
        row["candidate_builder"]["required_aspect_coverage"]
        for row in per_query
        if row["query_id"] in aspect_ids
    )
    selector_bundle_sum = sum(
        row["deterministic_selector"]["bundle_hit"]
        for row in per_query
        if row["query_id"] in complete_ids
    )
    selector_span_sum = sum(
        row["deterministic_selector"]["required_span_recall"]
        for row in per_query
        if row["query_id"] in span_ids
    )
    selector_aspect_sum = sum(
        row["deterministic_selector"]["required_aspect_coverage"]
        for row in per_query
        if row["query_id"] in aspect_ids
    )

    determinate = [
        row
        for row in per_query
        if row["retrieval"]["state"] != "indeterminate_due_to_unjudged"
    ]
    hit_metrics: dict[str, Any] = {}
    for k in (1, 3, 5, 10):
        determinate_hits = sum(
            row["retrieval"][f"hit_at_{k}"] for row in determinate
        )
        lower = sum(row["retrieval"][f"hit_at_{k}"] for row in per_query)
        indeterminate_count = len(per_query) - len(determinate)
        hit_metrics[f"hit_at_{k}"] = {
            "metrics_on_determinate_queries": determinate_hits / len(determinate)
            if determinate
            else None,
            "all_query_lower_bound": lower / 14,
            "all_query_upper_bound": (lower + indeterminate_count) / 14,
        }

    source_types = Counter(
        source_type
        for prediction in predictions
        for source_type in prediction["candidate_builder"]["source_types"]
    )
    languages = Counter(
        language
        for prediction in predictions
        for language in prediction["candidate_builder"]["source_languages"]
    )
    widths = [
        max(0.0, float(span["end_time"]) - float(span["start_time"]))
        for prediction in predictions
        for span in prediction["candidate_builder"]["evidence_spans"]
    ]
    selected_counts = [
        row["deterministic_selector"]["selected_candidate_count"]
        for row in per_query
    ]
    gate_counts = Counter(row["mechanical_gate"]["outcome"] for row in per_query)
    distribution = dict(Counter(row["primary_attribution"] for row in per_query))
    return {
        "attempt_id": ATTEMPT_ID,
        "amendment_version": AMENDMENT_VERSION,
        "scoring_schema_version": SCORING_SCHEMA_VERSION,
        "measurement_note": (
            "Amended metrics are recomputed from the unchanged P8 Attempt 3 "
            "Predictions, Traces, fixed Retrieval addendum, and DEVELOPMENT_GOLD_V1."
        ),
        "retrieval": {
            "determinate_query_count": len(determinate),
            "indeterminate_query_count": 14 - len(determinate),
            "any_acceptable_video": hit_metrics,
            "known_relevant_recall": {
                f"at_{k}": mean(
                    [
                        row["retrieval"][f"known_relevant_recall_at_{k}"]
                        for row in per_query
                        if row["retrieval"][
                            f"known_relevant_recall_at_{k}"
                        ]
                        is not None
                    ]
                )
                for k in (1, 3, 5, 10)
            },
            "first_acceptable_rank": [
                row["retrieval"]["first_acceptable_rank"] for row in per_query
            ],
            "empty_result_count": sum(
                row["retrieval"]["returned_count"] == 0 for row in per_query
            ),
            "router_distribution": dict(
                Counter(row["retrieval"]["effective_mode"] for row in predictions)
            ),
            "unjudged_return_count": sum(
                row["retrieval"]["unjudged_count"] for row in per_query
            ),
            "metadata_only_candidate_availability": sum(
                row["retrieval"]["metadata_only_candidates"] > 0
                for row in predictions
            ),
            "transcript_candidate_availability": sum(
                row["retrieval"]["transcript_candidates"] > 0
                for row in predictions
            ),
            "latency": latency(predictions, "retrieval"),
        },
        "candidate_builder": {
            "complete_acceptable_evidence_group_coverage": metric_contract(
                numerator=complete_numerator,
                eligible_ids=complete_ids,
                all_ids=all_ids,
                exclusion_reasons=zero_group_reason,
                definition=(
                    "Queries with at least one Gold-defined acceptable group "
                    "and constructible material evidence."
                ),
            ),
            "required_span_recall_macro": metric_contract(
                numerator=builder_span_sum,
                eligible_ids=span_ids,
                all_ids=all_ids,
                exclusion_reasons=zero_group_reason,
                definition=(
                    "Macro mean over queries with Gold-required span IDs in "
                    "an acceptable evidence group."
                ),
            ),
            "required_aspect_coverage_macro": metric_contract(
                numerator=builder_aspect_sum,
                eligible_ids=aspect_ids,
                all_ids=all_ids,
                exclusion_reasons=zero_group_reason,
                definition=(
                    "Macro mean over queries whose material aspects have "
                    "constructible Gold evidence options."
                ),
            ),
            "primary_failure_count": metric_contract(
                numerator=distribution.get("candidate_builder_failure", 0),
                eligible_ids=builder_failure_ids,
                all_ids=all_ids,
                exclusion_reasons=builder_failure_exclusions,
                definition=(
                    "Count among retrieval-success, source-reviewable queries "
                    "with constructible Gold groups."
                ),
            ),
            "candidate_count": sum(
                row["candidate_builder"]["candidate_count"] for row in per_query
            ),
            "evidence_compression": {
                "definition": "mean constructed evidence-candidate window width in seconds",
                "mean_window_seconds": mean(widths),
            },
            "window_width_mean_seconds": mean(widths),
            "cross_run_candidate_count": 0,
            "invalid_candidate_count": sum(
                row["candidate_builder"]["invalid_candidate_count"]
                for row in per_query
            ),
            "source_type_breakdown": dict(source_types),
            "language_breakdown": dict(languages),
            "asr_breakdown": {
                "asr": source_types.get("asr", 0),
                "human": source_types.get("human", 0),
                "ai": source_types.get("ai", 0),
            },
            "latency": latency(predictions, "candidate_builder"),
        },
        "deterministic_selector": {
            "bundle_hit": metric_contract(
                numerator=selector_bundle_sum,
                eligible_ids=complete_ids,
                all_ids=all_ids,
                exclusion_reasons=zero_group_reason,
                definition=(
                    "Selected bundle complete-group hit over queries with a "
                    "Gold-defined constructible acceptable group."
                ),
            ),
            "complete_group_available_but_not_selected": sum(
                row["deterministic_selector"][
                    "complete_group_available_but_not_selected"
                ]
                for row in per_query
            ),
            "primary_failure_count": distribution.get(
                "deterministic_selector_failure", 0
            ),
            "selected_candidate_count": {
                "total": sum(selected_counts),
                "mean": mean(selected_counts),
            },
            "required_span_recall_macro": metric_contract(
                numerator=selector_span_sum,
                eligible_ids=span_ids,
                all_ids=all_ids,
                exclusion_reasons=zero_group_reason,
                definition=(
                    "Macro mean over queries with Gold-required span IDs in "
                    "an acceptable evidence group."
                ),
            ),
            "required_aspect_coverage_macro": metric_contract(
                numerator=selector_aspect_sum,
                eligible_ids=aspect_ids,
                all_ids=all_ids,
                exclusion_reasons=zero_group_reason,
                definition=(
                    "Macro mean over queries whose material aspects have "
                    "constructible Gold evidence options."
                ),
            ),
            "compactness_macro": mean(
                [
                    row["deterministic_selector"]["compactness"]
                    for row in per_query
                    if row["deterministic_selector"]["compactness"] is not None
                ]
            ),
            "redundancy_macro": mean(
                [
                    row["deterministic_selector"]["redundancy"]
                    for row in per_query
                    if row["deterministic_selector"]["redundancy"] is not None
                ]
            ),
            "formula": {
                "compactness": "selected interval union duration / summed selected interval duration",
                "redundancy": "1 - compactness",
            },
            "latency": latency(predictions, "deterministic_selector"),
        },
        "mechanical_gate": {
            "judge_eligible_count": gate_counts["judge_eligible"],
            "terminal_unverifiable_count": gate_counts["terminal_unverifiable"],
            "invalid_identity_count": sum(
                "identity" in " ".join(row["mechanical_gate"]["reason_codes"])
                for row in per_query
            ),
            "invalid_source_count": sum(
                bool(
                    set(row["mechanical_gate"]["reason_codes"])
                    & SOURCE_TERMINAL_CODES
                )
                for row in per_query
            ),
            "invalid_timeline_count": sum(
                "timeline" in " ".join(row["mechanical_gate"]["reason_codes"])
                for row in per_query
            ),
            "mechanically_complete_count": gate_counts["judge_eligible"],
            "mechanically_incomplete_count": gate_counts["terminal_unverifiable"],
            "invalid_decision_count": sum(
                not row["mechanical_gate"]["valid_decision"] for row in per_query
            ),
            "latency": latency(predictions, "mechanical_gate"),
        },
        "primary_failure_distribution": distribution,
    }


def write_file_hash_manifest(
    repository_root: Path,
    manifest_path: Path,
    paths: Sequence[Path],
) -> None:
    write_jsonl(
        manifest_path,
        [
            {
                "path": str(path.relative_to(repository_root)),
                "sha256": file_sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in paths
        ],
    )


def generate(repository_root: Path) -> dict[str, Any]:
    baseline_root = (
        repository_root
        / "research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3"
    )
    output_root = baseline_root / "scoring_amendment_v1"
    checkpoint_root = (
        repository_root / "research/v3_5/checkpoints/checkpoint_1/amendment_v1"
    )
    identity = verify_prediction_identity(baseline_root)
    gold_identity = verify_development_gold_identity(repository_root)
    prediction_path = (
        baseline_root / "blind_run/product_initial_baseline.predictions.jsonl"
    )
    predictions = load_jsonl(prediction_path)
    paths = gold_paths(repository_root)
    retrieval_gold = {
        row["query_id"]: row for row in load_jsonl(paths["retrieval"])
    }
    evidence_gold = {
        row["query_id"]: row for row in load_jsonl(paths["evidence"])
    }
    sufficiency_gold = {
        row["query_id"]: row for row in load_jsonl(paths["sufficiency"])
    }
    per_query = build_per_query(
        baseline_root=baseline_root,
        predictions=predictions,
        retrieval_gold=retrieval_gold,
        evidence_gold=evidence_gold,
        sufficiency_gold=sufficiency_gold,
    )
    scores = build_scores(predictions, per_query)
    generated_at = utc_now()

    scores_path = output_root / "p8_scoring_amendment.scores.json"
    per_query_path = output_root / "p8_scoring_amendment.per_query.jsonl"
    attribution_path = (
        output_root / "p8_scoring_amendment.failure_attribution.jsonl"
    )
    audit_path = output_root / "p8_scoring_amendment.audit.json"
    decision_path = output_root / "p8_scoring_amendment.execution_decision.json"
    report_path = output_root / "P8_SCORING_AMENDMENT_REPORT.md"
    manifest_path = output_root / "p8_scoring_amendment.manifest.json"
    hash_manifest_path = (
        output_root / "p8_scoring_amendment.file_hash_manifest.jsonl"
    )
    ledger_path = (
        output_root
        / "V3_5_P8_SCORING_CHECKPOINT_1_AMENDMENT_DECISION_LEDGER.json"
    )
    scorer_path = repository_root / "src/shiliu/eval_v3_5/p8_scoring_amendment.py"
    write_json(scores_path, scores)
    write_jsonl(per_query_path, per_query)
    write_jsonl(
        attribution_path,
        [
            {
                "query_id": row["query_id"],
                "primary_attribution": row["primary_attribution"],
                "decision_sensitive_unjudged": row[
                    "decision_sensitive_unjudged"
                ],
                "eligibility": row["gold_eligibility"],
                "persisted_assets": row["persisted_assets"],
            }
            for row in per_query
        ],
    )

    original_scores = load_json(
        baseline_root / "scoring/product_initial_baseline.scores.json"
    )
    q017 = next(row for row in per_query if row["query_id"] == "PQS_V1_Q017")
    audit = {
        "schema_version": SCORING_SCHEMA_VERSION,
        "amendment_version": AMENDMENT_VERSION,
        "generated_at": generated_at,
        "identity": {
            **identity,
            **gold_identity,
            "predictions_unchanged": True,
            "traces_unchanged": True,
            "development_gold_unchanged": True,
            "frozen_gold_opened": False,
        },
        "repair": {
            "generic_eligibility_rule_added": True,
            "generic_non_builder_terminal": "gold_defined_evidence_absent",
            "q017_case_specific_rule_added": False,
            "all_14_attributions_revalidated": True,
            "one_primary_outcome_per_query": True,
            "q017_primary_attribution": q017["primary_attribution"],
        },
        "execution": {
            "retrieval_rerun": False,
            "builder_rerun": False,
            "selector_rerun": False,
            "gate_rerun": False,
            "prediction_rerun": False,
            "trace_rerun": False,
            "scoring_recomputed_from_frozen_artifacts": True,
        },
        "governance": {
            "original_scoring_preserved_as_superseded": True,
            "original_scoring_status": "superseded_by_scoring_amendment",
            "supersession_reason": "builder_failure_eligibility_defect",
            "checkpoint_1_derived_findings_amended": True,
            "p9_restarted": False,
            "f1a_authorized": False,
            "f1b_authorized": False,
            "stage4_started": False,
        },
    }
    write_json(audit_path, audit)
    decision = {
        "execution_status": "complete",
        "acceptance_status": "pending_v3_5_b_review",
        "P8_prediction_set": {"status": "valid_and_frozen"},
        "P8_scoring_amendment": {"status": "execution_candidate_ready"},
        "Checkpoint_1_amendment": {"status": "execution_candidate_ready"},
        "P9": {
            "status": "blocked_pending_v3_5_b_acceptance",
            "restarted": False,
            "restart_readiness": True,
        },
        "F1A_entry_signal": scores["candidate_builder"][
            "primary_failure_count"
        ]["numerator"]
        > 0,
        "F1A_authorized": False,
        "F1B_authorized": False,
        "Stage4_started": False,
    }
    write_json(decision_path, decision)
    report = f"""# P8 Scoring Amendment Report

## Identity

P8 Attempt 3's fourteen Predictions and fourteen Traces remain immutable.
Prediction SHA-256 is `{PREDICTIONS_SHA256}` and Prediction Seal SHA-256 is
`{PREDICTION_SEAL_SHA256}`. DEVELOPMENT_GOLD_V1 Seal SHA-256 is
`{DEVELOPMENT_GOLD_SEAL_SHA256}`. Frozen Gold was not opened.

## Generic scoring repair

`candidate_builder_failure` now requires Retrieval success, a reviewable
authoritative source, at least one Gold-defined acceptable evidence group,
constructible material evidence, and no complete group in the CandidateSet.
The generic terminal `gold_defined_evidence_absent` applies when reviewable
Development Gold explicitly has no constructible material evidence. No Query,
Case, or Video ID participates in this rule.

`PQS_V1_Q017` is therefore amended from `candidate_builder_failure` to
`gold_defined_evidence_absent`.

## Metric amendment

| Metric | Original | Amended |
|---|---:|---:|
| Builder complete-group coverage | 6/14 ({original_scores["candidate_builder"]["complete_acceptable_evidence_group_coverage"]:.6f}) | 6/13 ({scores["candidate_builder"]["complete_acceptable_evidence_group_coverage"]["value"]:.6f}) |
| Builder required-span recall macro | {original_scores["candidate_builder"]["required_span_recall_macro"]:.6f} | {scores["candidate_builder"]["required_span_recall_macro"]["value"]:.6f} |
| Builder required-aspect coverage macro | {original_scores["candidate_builder"]["required_aspect_coverage_macro"]:.6f} | {scores["candidate_builder"]["required_aspect_coverage_macro"]["value"]:.6f} |
| Builder primary failures | 7 | 6 |
| Selector bundle hit | 1/14 ({original_scores["deterministic_selector"]["bundle_hit"]:.6f}) | 1/13 ({scores["deterministic_selector"]["bundle_hit"]["value"]:.6f}) |
| Selector required-span recall macro | {original_scores["deterministic_selector"]["required_span_recall_macro"]:.6f} | {scores["deterministic_selector"]["required_span_recall_macro"]["value"]:.6f} |
| Selector required-aspect coverage macro | {original_scores["deterministic_selector"]["required_aspect_coverage_macro"]:.6f} | {scores["deterministic_selector"]["required_aspect_coverage_macro"]["value"]:.6f} |

Complete Group, Span Recall, Aspect Coverage, and Builder Primary Failure each
carry their own explicit numerator, denominator, eligibility count, excluded
IDs, and exclusion reason in `p8_scoring_amendment.scores.json`.

Retrieval and Gate metrics are byte-for-value unchanged. Candidate count,
window width, latency, source/language breakdowns, selected count,
compactness, and redundancy are also unchanged because no Product Component
was rerun.

## Primary attribution

Amended distribution:
`{json.dumps(scores["primary_failure_distribution"], ensure_ascii=False, sort_keys=True)}`.

Every one of the fourteen queries has exactly one eligibility-valid primary
outcome.

## Supersession and boundary

The original scoring assets remain present and are marked
`superseded_by_scoring_amendment` for reason
`builder_failure_eligibility_defect`. The amended baseline is:

`P8 Attempt 3 Frozen Prediction Set + P8 Scoring Amendment v1`.

F1A entry signal remains true because six real Builder-primary failures remain.
P9 restart readiness is true only after V3.5-B accepts this Amendment. P9 was
not restarted; F1A/F1B remain unauthorized; Stage 4 was not started.
"""
    report_path.write_text(report, encoding="utf-8")

    core_hashes = {
        "scores_sha256": file_sha256(scores_path),
        "per_query_sha256": file_sha256(per_query_path),
        "failure_attribution_sha256": file_sha256(attribution_path),
        "scorer_sha256": file_sha256(scorer_path),
        "prediction_seal_sha256": PREDICTION_SEAL_SHA256,
        "development_gold_seal_sha256": DEVELOPMENT_GOLD_SEAL_SHA256,
    }
    scoring_hash_root = value_sha256(core_hashes)
    manifest = {
        "schema_version": SCORING_SCHEMA_VERSION,
        "amendment_version": AMENDMENT_VERSION,
        "attempt_id": ATTEMPT_ID,
        "generated_at": generated_at,
        "version_relation": (
            "P8 Attempt 3 Frozen Prediction Set + P8 Scoring Amendment v1 "
            "= Amended Product Initial Baseline"
        ),
        "scoring_hash_root": scoring_hash_root,
        "hash_root_members": core_hashes,
        "original_scoring": {
            "status": "superseded_by_scoring_amendment",
            "reason": "builder_failure_eligibility_defect",
            "preserved": True,
            "scores_sha256": file_sha256(
                baseline_root / "scoring/product_initial_baseline.scores.json"
            ),
            "per_query_sha256": file_sha256(
                baseline_root / "scoring/product_initial_baseline.per_query.jsonl"
            ),
            "failure_attribution_sha256": file_sha256(
                baseline_root
                / "scoring/product_initial_baseline.failure_attribution.jsonl"
            ),
        },
        "outputs": [
            str(path.relative_to(repository_root))
            for path in (
                report_path,
                scores_path,
                per_query_path,
                attribution_path,
                audit_path,
                decision_path,
                ledger_path,
            )
        ],
        "success_state": decision,
    }
    write_json(manifest_path, manifest)

    checkpoint_report_path = checkpoint_root / "CHECKPOINT_1_AMENDMENT_REPORT.md"
    checkpoint_manifest_path = (
        checkpoint_root / "checkpoint_1_amendment.manifest.json"
    )
    checkpoint_audit_path = checkpoint_root / "checkpoint_1_amendment.audit.json"
    checkpoint_decision_path = (
        checkpoint_root / "checkpoint_1_amendment.execution_decision.json"
    )
    checkpoint_hash_manifest_path = (
        checkpoint_root / "checkpoint_1_amendment.file_hash_manifest.jsonl"
    )
    checkpoint_report_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_report_path.write_text(
        f"""# Checkpoint 1 Amendment Report

Checkpoint 1 is amended only for findings derived from P8 scoring. P7 remains
`complete_and_accepted`; the P8 Attempt 3 Prediction Set remains
`valid_and_frozen`.

The original Checkpoint 1 derived Builder denominator `14` and Builder primary
failure count `7` are superseded by Scoring Amendment v1. The amended Builder
complete-group coverage is `6/13`; required-span recall is
`{scores["candidate_builder"]["required_span_recall_macro"]["value"]}`;
required-aspect coverage is
`{scores["candidate_builder"]["required_aspect_coverage_macro"]["value"]}`;
Builder primary failures are `6`.

The amended Primary Failure Distribution is
`{json.dumps(scores["primary_failure_distribution"], ensure_ascii=False, sort_keys=True)}`.
Q017's general terminal is `gold_defined_evidence_absent`.

Retrieval remains Hit@10 `14/14` with zero primary Retrieval failures. Selector
primary failures remain `5`; Gate predictions and derived counts remain
unchanged.

F1A entry signal remains true because real Builder failures remain. P9 is
`blocked_pending_v3_5_b_acceptance`; restart readiness is true, but P9 was not
restarted. F1A/F1B remain unauthorized and Stage 4 was not started.
""",
        encoding="utf-8",
    )
    checkpoint_manifest = {
        "schema_version": "v3.5-b-checkpoint-1-amendment-v1",
        "execution_status": "complete",
        "acceptance_status": "pending_v3_5_b_review",
        "checkpoint_1_amendment_status": "execution_candidate_ready",
        "p7_status": "complete_and_accepted",
        "p8_prediction_set_status": "valid_and_frozen",
        "p8_formal_attempt": ATTEMPT_ID,
        "p8_prediction_seal_sha256": PREDICTION_SEAL_SHA256,
        "p8_scoring_amendment_path": str(manifest_path.relative_to(repository_root)),
        "p8_scoring_hash_root": scoring_hash_root,
        "amended_findings": {
            "candidate_builder_complete_group_coverage": scores[
                "candidate_builder"
            ]["complete_acceptable_evidence_group_coverage"],
            "candidate_builder_required_span_recall": scores[
                "candidate_builder"
            ]["required_span_recall_macro"],
            "candidate_builder_required_aspect_coverage": scores[
                "candidate_builder"
            ]["required_aspect_coverage_macro"],
            "candidate_builder_primary_failures": 6,
            "selector_primary_failures": 5,
            "primary_failure_distribution": scores[
                "primary_failure_distribution"
            ],
        },
        "governance_files_updated": [
            "V3_5_CURRENT_STATE.md",
            "03_V3_5_DECISION_AND_ARTIFACT_INDEX.md",
            "02_PRODUCT_QUERY_SET_AND_REMAINING_V3_5_PLAN.md",
            str(ledger_path.relative_to(repository_root)),
        ],
    }
    write_json(checkpoint_manifest_path, checkpoint_manifest)
    write_json(
        checkpoint_audit_path,
        {
            "schema_version": "v3.5-b-checkpoint-1-amendment-v1",
            "identity": {
                **identity,
                **gold_identity,
                "frozen_gold_opened": False,
            },
            "derived_findings_amended": True,
            "original_checkpoint_preserved": True,
            "original_checkpoint_status": (
                "superseded_by_checkpoint_1_amendment_for_derived_findings"
            ),
            "predictions_rerun": False,
            "traces_rerun": False,
            "retrieval_rerun": False,
            "builder_rerun": False,
            "selector_rerun": False,
            "gate_rerun": False,
            "query_split_gold_changed": False,
            "component_behavior_changed": False,
            "p9_restarted": False,
            "f1a_authorized": False,
            "f1b_authorized": False,
            "stage4_started": False,
        },
    )
    write_json(checkpoint_decision_path, decision)
    checkpoint_paths = [
        checkpoint_report_path,
        checkpoint_manifest_path,
        checkpoint_audit_path,
        checkpoint_decision_path,
    ]
    write_file_hash_manifest(
        repository_root, checkpoint_hash_manifest_path, checkpoint_paths
    )

    scoring_paths = [
        report_path,
        scores_path,
        per_query_path,
        attribution_path,
        manifest_path,
        audit_path,
        decision_path,
        ledger_path,
    ]
    write_file_hash_manifest(repository_root, hash_manifest_path, scoring_paths)
    return {
        "scoring_hash_root": scoring_hash_root,
        "scores": scores,
        "scoring_output_root": str(output_root),
        "checkpoint_output_root": str(checkpoint_root),
    }
