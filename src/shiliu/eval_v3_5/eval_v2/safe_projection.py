from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PROJECTION_VERSION = "v3.5-safe-non-heldout-candidate-projection-v1"
OUTPUT_SCHEMA_VERSION = "v3.5-safe-candidate-projection-record-v1"
LINEAGE_SOURCE = "v3_eval_query_pool_safe_projection"
SOURCE_RELATIVE_PATH = Path("research/v3_eval/eval_queries.candidate.jsonl")
OUTPUT_DIRECTORY = Path("research/v3_5/eval_v2/stage2r_b_inputs")
OUTPUT_RELATIVE_PATH = OUTPUT_DIRECTORY / "pilot_candidate_projection.safe.v1.jsonl"
MANIFEST_RELATIVE_PATH = OUTPUT_DIRECTORY / "pilot_candidate_projection.safe.v1.manifest.json"
AUDIT_RELATIVE_PATH = OUTPUT_DIRECTORY / "pilot_candidate_projection.safe.v1.audit.json"

OUTPUT_FIELDS = frozenset(
    {
        "candidate_id",
        "query",
        "query_language",
        "lineage_source",
        "source_record_digest",
        "pilot_candidate_allowed",
        "projection_version",
    }
)
FORBIDDEN_KEYS = frozenset(
    {
        "held_out", "heldout", "is_heldout", "split", "partition", "development",
        "dev", "test", "eval_split", "evaluation_split", "gold", "gold_label",
        "label", "status", "sufficiency", "sufficient", "partial", "insufficient",
        "unverifiable", "relevant", "relevance", "target_video", "target_video_id",
        "target_video_ids", "acceptable_video", "gold_video", "gold_span",
        "required_span", "required_aspect", "supported_aspect", "missing_aspect",
        "evidence_group", "reason_code", "review", "reviewer", "human_decision",
        "adjudication", "candidate_builder", "selector", "judge",
    }
)
BOOLEAN_SPLIT_KEYS = ("heldout", "is_heldout")
NAMED_SPLIT_KEYS = ("split", "partition", "evaluation_split", "eval_split")
HELDOUT_VALUES = frozenset({"heldout", "test", "eval", "evaluation"})
NON_HELDOUT_VALUES = frozenset({"development", "dev", "train", "training", "nonheldout"})
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
CANDIDATE_ID_RE = re.compile(r"^SAFEQ_[0-9a-f]{20}$")
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)


class ProjectionError(RuntimeError):
    """A safe, content-free projection failure."""


@dataclass(frozen=True)
class ProjectionResult:
    source_path: str
    source_sha256: str
    input_record_count: int
    included_record_count: int
    excluded_record_count: int
    ambiguous_record_count: int
    output_path: str
    output_sha256: str
    validation_passed: bool

    def stdout_items(self) -> tuple[tuple[str, object], ...]:
        return (
            ("source_path", self.source_path),
            ("source_sha256", self.source_sha256),
            ("input_record_count", self.input_record_count),
            ("included_record_count", self.included_record_count),
            ("excluded_record_count", self.excluded_record_count),
            ("ambiguous_record_count", self.ambiguous_record_count),
            ("output_path", self.output_path),
            ("output_sha256", self.output_sha256),
            ("validation_passed", self.validation_passed),
        )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _normalized_query_digest(query: str) -> str:
    normalized = unicodedata.normalize("NFC", query).strip()
    return _sha256(normalized.encode("utf-8"))


def _display_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _require_exact_path(candidate: str | Path, expected: Path, kind: str) -> Path:
    lexical = Path(os.path.abspath(candidate))
    expected_lexical = Path(os.path.abspath(expected))
    resolved = lexical.resolve()
    if lexical != expected_lexical or resolved != expected_lexical.resolve():
        raise ProjectionError(f"{kind}_path_not_authorized")
    return resolved


def _named_split_signal(value: object) -> bool | None:
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"[-_\s]", "", value.casefold())
    if normalized in HELDOUT_VALUES:
        return True
    if normalized in NON_HELDOUT_VALUES:
        return False
    return None


def _classify(record: dict[str, Any]) -> tuple[bool, bool]:
    """Return (include, ambiguous) without exposing record identity."""
    ambiguous = False
    signals: list[bool] = []

    primary = record.get("held_out")
    if "held_out" not in record or type(primary) is not bool:
        ambiguous = True
    else:
        signals.append(primary)

    for key in BOOLEAN_SPLIT_KEYS:
        if key not in record:
            continue
        value = record[key]
        if type(value) is bool:
            signals.append(value)
        else:
            ambiguous = True

    for key in NAMED_SPLIT_KEYS:
        if key not in record:
            continue
        signal = _named_split_signal(record[key])
        if signal is None:
            ambiguous = True
        else:
            signals.append(signal)

    if signals and any(signals) and not all(signals):
        ambiguous = True

    query = record.get("query")
    query_valid = isinstance(query, str) and bool(query.strip())
    if not query_valid:
        ambiguous = True

    include = (
        type(primary) is bool
        and primary is False
        and query_valid
        and not ambiguous
        and not any(signals)
    )
    return include, ambiguous


def _language(record: dict[str, Any]) -> str:
    value = record.get("query_language")
    return value if isinstance(value, str) and LANGUAGE_RE.fullmatch(value) else "unknown"


def _record_for_output(
    record: dict[str, Any], *, source_sha256: str, line_ordinal: int
) -> dict[str, object]:
    query = record["query"]
    query_digest = _normalized_query_digest(query)
    identity_material = "\0".join(
        (source_sha256, str(line_ordinal), query_digest, PROJECTION_VERSION)
    ).encode("utf-8")
    return {
        "candidate_id": f"SAFEQ_{_sha256(identity_material)[:20]}",
        "lineage_source": LINEAGE_SOURCE,
        "pilot_candidate_allowed": True,
        "projection_version": PROJECTION_VERSION,
        "query": query,
        "query_language": _language(record),
        "source_record_digest": _sha256(_canonical_json_bytes(record)),
    }


def _parse_and_project(source_bytes: bytes) -> tuple[bytes, dict[str, int]]:
    included: list[dict[str, object]] = []
    included_query_digests: set[str] = set()
    excluded_query_digests: set[str] = set()
    source_record_digests: set[str] = set()
    ambiguous_count = 0
    input_count = 0
    source_sha256 = _sha256(source_bytes)

    for line_ordinal, raw_line in enumerate(source_bytes.splitlines(), 1):
        input_count += 1
        try:
            record = json.loads(
                raw_line,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non_finite_json")),
            )
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            ambiguous_count += 1
            print(
                f"projection_error: line={line_ordinal} category=malformed_json",
                file=sys.stderr,
            )
            continue
        if not isinstance(record, dict):
            ambiguous_count += 1
            print(
                f"projection_error: line={line_ordinal} category=non_object_record",
                file=sys.stderr,
            )
            continue

        include, ambiguous = _classify(record)
        query = record.get("query")
        query_digest = (
            _normalized_query_digest(query)
            if isinstance(query, str) and bool(query.strip())
            else None
        )
        if ambiguous:
            ambiguous_count += 1
        if not include:
            if query_digest is not None:
                excluded_query_digests.add(query_digest)
            continue

        assert query_digest is not None
        if query_digest in included_query_digests:
            raise ProjectionError("duplicate_query_digest")
        projected = _record_for_output(
            record, source_sha256=source_sha256, line_ordinal=line_ordinal
        )
        source_record_digest = str(projected["source_record_digest"])
        if source_record_digest in source_record_digests:
            raise ProjectionError("duplicate_source_record_digest")
        included_query_digests.add(query_digest)
        source_record_digests.add(source_record_digest)
        included.append(projected)

    overlap_count = len(included_query_digests & excluded_query_digests)
    if overlap_count:
        raise ProjectionError("excluded_digest_overlap")

    output_bytes = b"".join(_canonical_json_bytes(item) + b"\n" for item in included)
    counts = {
        "input_record_count": input_count,
        "included_record_count": len(included),
        "excluded_record_count": input_count - len(included),
        "ambiguous_record_count": ambiguous_count,
        "excluded_digest_overlap_count": overlap_count,
        "duplicate_candidate_id_count": 0,
        "duplicate_query_digest_count": 0,
    }
    return output_bytes, counts


def _iter_output_records(output_bytes: bytes) -> Iterable[dict[str, object]]:
    for line_ordinal, raw_line in enumerate(output_bytes.splitlines(), 1):
        try:
            value = json.loads(raw_line)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProjectionError(f"output_malformed_json_line_{line_ordinal}") from exc
        if not isinstance(value, dict):
            raise ProjectionError(f"output_non_object_line_{line_ordinal}")
        yield value


def validate_projection_bytes(output_bytes: bytes, expected_count: int) -> dict[str, object]:
    candidate_ids: set[str] = set()
    record_digests: set[str] = set()
    query_digests: set[str] = set()
    count = 0
    for record in _iter_output_records(output_bytes):
        count += 1
        if set(record) != OUTPUT_FIELDS:
            raise ProjectionError("output_field_allowlist_violation")
        if set(record) & FORBIDDEN_KEYS:
            raise ProjectionError("output_forbidden_key")
        candidate_id = record.get("candidate_id")
        if not isinstance(candidate_id, str) or not CANDIDATE_ID_RE.fullmatch(candidate_id):
            raise ProjectionError("invalid_candidate_id")
        if candidate_id in candidate_ids:
            raise ProjectionError("duplicate_candidate_id")
        candidate_ids.add(candidate_id)
        source_digest = record.get("source_record_digest")
        if not isinstance(source_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", source_digest):
            raise ProjectionError("invalid_source_record_digest")
        if source_digest in record_digests:
            raise ProjectionError("duplicate_source_record_digest")
        record_digests.add(source_digest)
        query = record.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ProjectionError("invalid_output_query")
        query_digest = _normalized_query_digest(query)
        if query_digest in query_digests:
            raise ProjectionError("duplicate_query_digest")
        query_digests.add(query_digest)
        if record.get("pilot_candidate_allowed") is not True:
            raise ProjectionError("pilot_candidate_allowed_not_true")
        if record.get("projection_version") != PROJECTION_VERSION:
            raise ProjectionError("projection_version_mismatch")
        if record.get("lineage_source") != LINEAGE_SOURCE:
            raise ProjectionError("lineage_source_mismatch")
    if count != expected_count:
        raise ProjectionError("output_record_count_mismatch")
    secret_scan_passed = not any(pattern.search(output_bytes.decode("utf-8")) for pattern in SECRET_PATTERNS)
    if not secret_scan_passed:
        raise ProjectionError("secret_scan_failed")
    return {
        "forbidden_field_scan_passed": True,
        "secret_scan_passed": True,
        "duplicate_candidate_id_count": 0,
        "duplicate_query_digest_count": 0,
        "duplicate_source_record_digest_count": 0,
    }


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _safe_unlink(paths: Iterable[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def build_safe_nonheldout_projection(
    repository_root: str | Path,
    *,
    source_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> ProjectionResult:
    """Build the one authorized projection and return aggregate metadata only."""
    root = Path(repository_root).resolve()
    expected_source = root / SOURCE_RELATIVE_PATH
    expected_output = root / OUTPUT_RELATIVE_PATH
    source = _require_exact_path(source_path or expected_source, expected_source, "source")
    output = _require_exact_path(output_path or expected_output, expected_output, "output")
    manifest_path = root / MANIFEST_RELATIVE_PATH
    audit_path = root / AUDIT_RELATIVE_PATH
    generated_paths = (output, manifest_path, audit_path)

    if not source.is_file():
        raise ProjectionError("source_file_missing")

    try:
        source_bytes = source.read_bytes()
        first_bytes, counts = _parse_and_project(source_bytes)
        second_bytes, second_counts = _parse_and_project(source_bytes)
        if first_bytes != second_bytes or counts != second_counts:
            raise ProjectionError("byte_reproducibility_failed")
        validation = validate_projection_bytes(first_bytes, counts["included_record_count"])
        output_sha256 = _sha256(first_bytes)
        source_sha256 = _sha256(source_bytes)

        eligibility = {
            "pilot_case_mining": False,
            "annotation_review": False,
            "gold_adjudication": False,
            "judge_development": False,
            "heldout_evaluation": False,
        }
        manifest = {
            "ambiguous_record_count": counts["ambiguous_record_count"],
            "byte_reproducible": True,
            "duplicate_candidate_id_count": validation["duplicate_candidate_id_count"],
            "duplicate_query_digest_count": validation["duplicate_query_digest_count"],
            "excluded_digest_overlap_count": counts["excluded_digest_overlap_count"],
            "excluded_record_count": counts["excluded_record_count"],
            "forbidden_field_scan_passed": validation["forbidden_field_scan_passed"],
            "generated_by": "shiliu.eval_v3_5.eval_v2.safe_projection",
            "generation_mode": "deterministic_local_projection",
            "included_record_count": counts["included_record_count"],
            "llm_calls": 0,
            "output_path": _display_path(output, root),
            "output_schema_version": OUTPUT_SCHEMA_VERSION,
            "output_sha256": output_sha256,
            "projection_version": PROJECTION_VERSION,
            "provider_calls": 0,
            "secret_scan_passed": validation["secret_scan_passed"],
            "session_future_eligibility": eligibility,
            "source_path": _display_path(source, root),
            "source_record_count": counts["input_record_count"],
            "source_sha256": source_sha256,
        }
        audit = {
            "authorized_source_path": _display_path(source, root),
            "authorized_output_path": _display_path(output, root),
            "byte_reproducible": True,
            "excluded_digest_material_persisted": False,
            "forbidden_field_scan_passed": True,
            "generation_mode": "deterministic_local_projection",
            "llm_calls": 0,
            "ordinary_stage2r_guard_modified": False,
            "output_record_content_logged": False,
            "provider_calls": 0,
            "raw_records_returned": False,
            "secret_scan_passed": True,
            "session_future_eligibility": eligibility,
            "split_aware_source_files_read": [_display_path(source, root)],
            "usage_identifier": "stage2r_b_recovery_a_safe_projection_builder",
            "validation_passed": True,
        }
        _atomic_write(output, first_bytes)
        _atomic_write(manifest_path, _canonical_json_bytes(manifest) + b"\n")
        _atomic_write(audit_path, _canonical_json_bytes(audit) + b"\n")
        return ProjectionResult(
            source_path=_display_path(source, root),
            source_sha256=source_sha256,
            input_record_count=counts["input_record_count"],
            included_record_count=counts["included_record_count"],
            excluded_record_count=counts["excluded_record_count"],
            ambiguous_record_count=counts["ambiguous_record_count"],
            output_path=_display_path(output, root),
            output_sha256=output_sha256,
            validation_passed=True,
        )
    except Exception:
        _safe_unlink(generated_paths)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the isolated safe non-held-out projection.")
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--source")
    parser.add_argument("--output")
    arguments = parser.parse_args(argv)
    try:
        result = build_safe_nonheldout_projection(
            arguments.repository_root,
            source_path=arguments.source,
            output_path=arguments.output,
        )
    except ProjectionError as exc:
        print(f"projection_failed: category={exc}", file=sys.stderr)
        return 2
    for key, value in result.stdout_items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        print(f"{key}: {rendered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
