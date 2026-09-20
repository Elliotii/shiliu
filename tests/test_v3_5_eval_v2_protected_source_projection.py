import json

import pytest

from shiliu.eval_v3_5.eval_v2.protected_source_projection import (
    PROTECTED_INPUT_NAMES, ProtectedProjectionError, build_protected_source_projection,
)


def _write_inputs(root, *, judgment=True):
    root.mkdir()
    (root / PROTECTED_INPUT_NAMES[0]).write_text(
        json.dumps({"query_id": "synthetic-q", "split": "heldout"}) + "\n"
    )
    payload = {"query_id": "synthetic-q", "video_id": "synthetic-video", "judgment": "not_relevant"} if judgment else {"query_id": "other"}
    (root / PROTECTED_INPUT_NAMES[1]).write_text(json.dumps(payload) + "\n")
    (root / PROTECTED_INPUT_NAMES[2]).write_text("", encoding="utf-8")
    (root / PROTECTED_INPUT_NAMES[3]).write_text("{}\n", encoding="utf-8")
    (root / PROTECTED_INPUT_NAMES[4]).write_text("{}\n", encoding="utf-8")


def test_exact_allowlist_and_not_relevant_protects(tmp_path):
    root = tmp_path / "protected"
    _write_inputs(root)
    projection = build_protected_source_projection(root)
    assert projection.video_identities == {"synthetic-video"}
    assert projection.protected_input_file_count == 5
    assert set(PROTECTED_INPUT_NAMES) == {path.name for path in root.iterdir()}


def test_missing_input_fails_closed(tmp_path):
    root = tmp_path / "protected"
    _write_inputs(root)
    (root / PROTECTED_INPUT_NAMES[-1]).unlink()
    with pytest.raises(ProtectedProjectionError):
        build_protected_source_projection(root)


def test_unmapped_judgments_fail_closed(tmp_path):
    root = tmp_path / "protected"
    _write_inputs(root, judgment=False)
    with pytest.raises(ProtectedProjectionError):
        build_protected_source_projection(root)


def test_aggregate_does_not_expose_identities(tmp_path):
    root = tmp_path / "protected"
    _write_inputs(root)
    aggregate = build_protected_source_projection(root).aggregate(excluded_source_count=1, unknown_count=2)
    serialized = json.dumps(aggregate)
    assert "synthetic-q" not in serialized
    assert "synthetic-video" not in serialized
    assert aggregate["unknown_protection_excluded_count"] == 2
