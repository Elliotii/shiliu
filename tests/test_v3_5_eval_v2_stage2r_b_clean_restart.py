from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from shiliu.eval_v3_5.eval_v2.contracts import AnnotationPacketV2
from shiliu.eval_v3_5.eval_v2.isolation import ProtectedPathError, Stage2RAAccessGuard
from shiliu.eval_v3_5.eval_v2.providers import build_deepseek_secondary_request
from shiliu.eval_v3_5.eval_v2.stage2r_b_runtime import (
    PRIMARY_WORKSPACE_FILES,
    _sandbox_profile,
    export_primary_workspace,
)


ROOT = Path(__file__).resolve().parents[1]
SAFE = ROOT / "research/v3_5/eval_v2/stage2r_b_inputs/pilot_candidate_projection.safe.v1.jsonl"
MANIFEST = SAFE.with_suffix(".manifest.json")
FIXTURE = ROOT / "research/v3_5/eval_v2/stage2r_a/fixtures/annotation_packet.synthetic.v2.json"


def packet() -> AnnotationPacketV2:
    return AnnotationPacketV2.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def test_safe_projection_hash_schema_and_unique_ids() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = {
        "candidate_id", "query", "query_language", "lineage_source",
        "source_record_digest", "pilot_candidate_allowed", "projection_version",
    }
    rows = [json.loads(line) for line in SAFE.read_text(encoding="utf-8").splitlines()]
    digest = hashlib.sha256(SAFE.read_bytes()).hexdigest()
    assert digest == manifest["output_sha256"]
    assert digest == "2c2fd3e0d06452201119f22ab3b68dcdfc738f91d19a916e50dbb9fd2051b564"
    assert all(set(row) == expected and row["pilot_candidate_allowed"] is True for row in rows)
    assert len({row["candidate_id"] for row in rows}) == len(rows)


def test_raw_assignment_guard_fails_closed_without_opening(tmp_path: Path) -> None:
    guard = Stage2RAAccessGuard(ROOT)
    synthetic = tmp_path / "eval_queries.candidate.jsonl"
    with pytest.raises(ProtectedPathError):
        guard.validate(synthetic)
    assert not synthetic.exists()


def test_deepseek_annotation_request_is_exact_and_secret_free() -> None:
    request = build_deepseek_secondary_request(packet(), "blind prompt")
    assert request.provider_usage == "annotation_secondary_review"
    assert request.body["model"] == "deepseek-v4-pro"
    assert request.body["thinking"] == {"type": "enabled"}
    assert request.body["reasoning_effort"] == "max"
    serialized = json.dumps(request.body).casefold()
    assert "authorization" not in serialized and "api_key" not in serialized
    with pytest.raises(ValueError):
        build_deepseek_secondary_request(packet(), "blind prompt", reasoning_strength="high")


def test_primary_workspace_is_external_allowlisted_and_secret_free(tmp_path: Path) -> None:
    workspace = tmp_path / "review" / "case"
    manifest = export_primary_workspace(
        packet=packet(), workspace=workspace, protocol="locked protocol", prompt="blind prompt"
    )
    assert set(manifest["inventory"]) == PRIMARY_WORKSPACE_FILES
    assert manifest["allowlist_passed"] is True
    assert manifest["repository_copy_present"] is False
    assert manifest["secret_files_present"] is False
    profile = tmp_path / "profile.sb"
    _sandbox_profile(workspace, profile)
    text = profile.read_text(encoding="utf-8")
    assert "(deny default)" in text
    assert str(workspace.resolve()) in text


def test_no_gold_lock_or_third_case_assets_created() -> None:
    output = ROOT / "research/v3_5/eval_v2/stage2r_b_clean_restart"
    names = [path.name.casefold() for path in output.rglob("*")] if output.exists() else []
    assert not any("gold_lock" in name or "locked_gold" in name for name in names)
    assert not any("case_3" in name or "case_c" in name for name in names)
