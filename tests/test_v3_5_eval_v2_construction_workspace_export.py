import json
from pathlib import Path

import pytest

from shiliu.eval_v3_5.eval_v2.construction_workspace_export import audit_workspace


pytestmark = pytest.mark.external_artifact


def test_production_workspace_is_external_and_allowlisted():
    workspace = Path("/tmp/shiliu-v3-5-c0-construction-input-v2").resolve()
    repository = Path("/Users/elliot/new-systems/agent-job-prep/Shiliu").resolve()
    assert repository not in workspace.parents and workspace not in repository.parents
    audit = audit_workspace(workspace)
    assert audit == {
        "forbidden_filename_violation_count": 0,
        "forbidden_key_violation_count": 0,
        "secret_violation_count": 0,
        "workspace_path_valid": True,
    }


def test_available_sources_have_raw_and_unavailable_do_not():
    workspace = Path("/tmp/shiliu-v3-5-c0-construction-input-v2")
    for metadata_path in workspace.glob("sources/SAFESRC_*/source_metadata.json"):
        metadata = json.loads(metadata_path.read_text())
        raw = metadata_path.with_name("subtitle-raw.json")
        assert raw.exists() is (metadata["source_availability"] == "available")


def test_workspace_manifest_hashes_every_asset():
    workspace = Path("/tmp/shiliu-v3-5-c0-construction-input-v2")
    manifest = json.loads((workspace / "workspace_manifest.json").read_text())
    assert manifest["raw_source_hash_mismatches"] == 0
    assert manifest["protected_source_overlap"] == 0
    assert manifest["unknown_protection_state_included"] == 0
    assert len(manifest["asset_sha256"]) == 4 + manifest["source_count"] + manifest["raw_source_export_count"]
