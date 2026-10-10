from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from shiliu.eval_v3_5.eval_v2.isolation import ProtectedPathError, Stage2RAAccessGuard
from shiliu.eval_v3_5.eval_v2.safe_projection import (
    AUDIT_RELATIVE_PATH,
    MANIFEST_RELATIVE_PATH,
    OUTPUT_FIELDS,
    OUTPUT_RELATIVE_PATH,
    PROJECTION_VERSION,
    SOURCE_RELATIVE_PATH,
    ProjectionError,
    build_safe_nonheldout_projection,
    validate_projection_bytes,
)


def write_fixture(root: Path, records: list[object], *, raw_lines: list[bytes] | None = None) -> Path:
    source = root / SOURCE_RELATIVE_PATH
    source.parent.mkdir(parents=True)
    lines = raw_lines or [
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode() for value in records
    ]
    source.write_bytes(b"\n".join(lines) + b"\n")
    return source


def output_records(root: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (root / OUTPUT_RELATIVE_PATH).read_bytes().splitlines()]


def test_fail_closed_filtering_conflicts_allowlist_and_unknown_language(tmp_path):
    records = [
        {"query": "included", "held_out": False, "query_language": "en"},
        {"query": "held out", "held_out": True},
        {"query": "missing assignment"},
        {"query": "null assignment", "held_out": None},
        {"query": "string assignment", "held_out": "false"},
        {"held_out": False},
        {"query": "", "held_out": False},
        {"query": "conflict", "held_out": False, "split": "heldout"},
        {"query": "multi conflict", "held_out": False, "split": "dev", "partition": "test"},
        {"query": "unknown language", "held_out": False, "query_language": "not a language!"},
    ]
    write_fixture(tmp_path, records)
    result = build_safe_nonheldout_projection(tmp_path)
    projected = output_records(tmp_path)
    assert result.input_record_count == 10
    assert result.included_record_count == 2
    assert result.excluded_record_count == 8
    assert result.ambiguous_record_count == 7
    assert [item["query"] for item in projected] == ["included", "unknown language"]
    assert projected[1]["query_language"] == "unknown"
    assert all(set(item) == OUTPUT_FIELDS for item in projected)
    assert all(item["pilot_candidate_allowed"] is True for item in projected)
    assert all(item["projection_version"] == PROJECTION_VERSION for item in projected)
    assert all(not (set(item) & {"held_out", "split", "gold", "label", "review"}) for item in projected)


def test_stable_opaque_ids_hashes_bytes_manifest_and_zero_calls(tmp_path):
    write_fixture(tmp_path, [{"query": "synthetic alpha", "held_out": False}])
    first = build_safe_nonheldout_projection(tmp_path)
    first_output = (tmp_path / OUTPUT_RELATIVE_PATH).read_bytes()
    first_manifest = (tmp_path / MANIFEST_RELATIVE_PATH).read_bytes()
    second = build_safe_nonheldout_projection(tmp_path)
    assert first == second
    assert first_output == (tmp_path / OUTPUT_RELATIVE_PATH).read_bytes()
    assert first_manifest == (tmp_path / MANIFEST_RELATIVE_PATH).read_bytes()
    assert first.output_sha256 == hashlib.sha256(first_output).hexdigest()
    candidate_id = output_records(tmp_path)[0]["candidate_id"]
    assert candidate_id.startswith("SAFEQ_") and len(candidate_id) == 26
    assert candidate_id != "SAFEQ_00000000000000000001"
    manifest = json.loads(first_manifest)
    audit = json.loads((tmp_path / AUDIT_RELATIVE_PATH).read_bytes())
    assert manifest["provider_calls"] == manifest["llm_calls"] == 0
    assert manifest["excluded_digest_overlap_count"] == 0
    assert manifest["duplicate_candidate_id_count"] == 0
    assert manifest["duplicate_query_digest_count"] == 0
    assert manifest["byte_reproducible"] is True
    assert audit["raw_records_returned"] is False


def test_duplicate_query_digest_and_source_record_are_rejected(tmp_path):
    write_fixture(tmp_path, [
        {"query": " duplicate ", "held_out": False},
        {"query": "duplicate", "held_out": False},
    ])
    with pytest.raises(ProjectionError, match="duplicate_query_digest"):
        build_safe_nonheldout_projection(tmp_path)
    assert not (tmp_path / OUTPUT_RELATIVE_PATH).exists()


def test_excluded_digest_overlap_fails_and_digests_are_not_persisted(tmp_path):
    write_fixture(tmp_path, [
        {"query": "same synthetic query", "held_out": False},
        {"query": "same synthetic query", "held_out": True},
    ])
    with pytest.raises(ProjectionError, match="excluded_digest_overlap"):
        build_safe_nonheldout_projection(tmp_path)
    assert not (tmp_path / OUTPUT_RELATIVE_PATH).exists()
    assert not (tmp_path / MANIFEST_RELATIVE_PATH).exists()
    assert not (tmp_path / AUDIT_RELATIVE_PATH).exists()


def test_validator_rejects_duplicate_candidate_id_and_forbidden_keys():
    base = {
        "candidate_id": "SAFEQ_0123456789abcdef0123",
        "lineage_source": "v3_eval_query_pool_safe_projection",
        "pilot_candidate_allowed": True,
        "projection_version": PROJECTION_VERSION,
        "query": "synthetic",
        "query_language": "en",
        "source_record_digest": "a" * 64,
    }
    line = json.dumps(base, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(ProjectionError, match="duplicate_candidate_id"):
        validate_projection_bytes(line + line, 2)
    forbidden = dict(base, held_out=False)
    bad = json.dumps(forbidden, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(ProjectionError, match="allowlist"):
        validate_projection_bytes(bad, 1)

    secret = dict(base, query="sk-abcdefghijklmnopqrstuvwxyz012345")
    secret_line = json.dumps(secret, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(ProjectionError, match="secret_scan_failed"):
        validate_projection_bytes(secret_line, 1)


def test_malformed_json_logs_only_ordinal_and_category(tmp_path, capsys):
    write_fixture(tmp_path, [], raw_lines=[b'{"query":"never emitted",', b'[]'])
    result = build_safe_nonheldout_projection(tmp_path)
    captured = capsys.readouterr()
    assert result.included_record_count == 0 and result.ambiguous_record_count == 2
    assert "line=1 category=malformed_json" in captured.err
    assert "line=2 category=non_object_record" in captured.err
    assert "never emitted" not in captured.err


def test_exact_paths_only_builder_returns_aggregates_not_records(tmp_path):
    source = write_fixture(tmp_path, [{"query": "synthetic", "held_out": False}])
    unauthorized = tmp_path / "other.jsonl"
    unauthorized.write_text("{}\n")
    with pytest.raises(ProjectionError, match="source_path_not_authorized"):
        build_safe_nonheldout_projection(tmp_path, source_path=unauthorized)
    with pytest.raises(ProjectionError, match="output_path_not_authorized"):
        build_safe_nonheldout_projection(tmp_path, source_path=source, output_path=tmp_path / "other-output.jsonl")
    source_alias = tmp_path / "source-alias.jsonl"
    source_alias.symlink_to(source)
    with pytest.raises(ProjectionError, match="source_path_not_authorized"):
        build_safe_nonheldout_projection(tmp_path, source_path=source_alias)
    result = build_safe_nonheldout_projection(tmp_path)
    assert not hasattr(result, "records") and not hasattr(result, "queries")


def test_ordinary_stage2r_guard_remains_strict(tmp_path):
    guard = Stage2RAAccessGuard(tmp_path)
    with pytest.raises(ProtectedPathError):
        guard.read_text(tmp_path / SOURCE_RELATIVE_PATH)
    with pytest.raises(ProtectedPathError):
        guard.read_text(tmp_path / "research/v3_eval/eval_queries.locked.jsonl")


def test_cli_stdout_allowlist_and_no_record_content(tmp_path):
    write_fixture(tmp_path, [{"query": "synthetic secret marker", "held_out": False}])
    completed = subprocess.run(
        [sys.executable, "-m", "shiliu.eval_v3_5.eval_v2.safe_projection",
         "--repository-root", str(tmp_path)],
        check=True, capture_output=True, text=True,
    )
    keys = {line.split(":", 1)[0] for line in completed.stdout.splitlines()}
    assert keys == {
        "source_path", "source_sha256", "input_record_count", "included_record_count",
        "excluded_record_count", "ambiguous_record_count", "output_path", "output_sha256",
        "validation_passed",
    }
    assert "synthetic secret marker" not in completed.stdout
    assert completed.stderr == ""
