"""Synthetic rehearsal of the explicit plan/copy boundary; no historical copy."""

import hashlib
import json
from pathlib import Path
import uuid
import pytest
from full_source import make_full_source
from shiliu.migration.package import (
    make_plan,
    prepare,
    reverse_support_policy,
    canonical,
)
from shiliu.migration.snapshot import inspect_snapshot, sha
from shiliu.migration.safety import TASK_ROOT
from shiliu.migration.values import MigrationRejected


def test_reviewed_policy_inverse_keeps_observed_bytes_and_rejects_wrong_event():
    old = {
        "presentation_forms": [
            {"temporary_id": "form1", "status": "stable", "supporting_content_ids": [1]}
        ]
    }
    expected = hashlib.sha256(canonical(old)).hexdigest()
    observed = json.loads(canonical(old))
    observed["presentation_forms"][0]["status"] = "draft"
    payload = canonical(observed)
    event = {
        "field_path": "presentation_forms[0].status",
        "node_id": "form1",
        "original_value": "stable",
        "normalized_value": "draft",
        "support_count": 1,
    }
    restored, count = reverse_support_policy(
        payload, canonical({"events": [event]}), expected
    )
    assert count == 1 and restored == canonical(old) and json.loads(payload) == observed
    event["node_id"] = "other"
    with pytest.raises(MigrationRejected, match="precondition"):
        reverse_support_policy(payload, canonical({"events": [event]}), expected)


def test_new_package_copies_only_synthetic_bound_files_and_detects_changed_plan_input(
    tmp_path,
):
    source = make_full_source(package_locators=True)
    # Explicit absolute locators for this independent packaging input. The
    # generic full-table fixture's export reference is a separate protocol path.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "candidate_audit", Path("scripts/postgres_p5_candidate_audit.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tmp_path.chmod(0o700)
    report = tmp_path / "audit.json"
    module.audit(source, [source.parent / "files"], report)
    plan = tmp_path / "plan.json"
    evidence = make_plan(report, plan)
    assert evidence["files"] >= 4
    before = sha(source)
    target = TASK_ROOT / "sources" / ("w14_package_" + uuid.uuid4().hex[:10])
    packaged = prepare(plan, target, "synthetic test only")
    identity, _ = inspect_snapshot(packaged)
    assert identity["provenance"]["synthetic_only"] and sha(source) == before
    assert not (target / "historical.json").exists()
    artifact = next((source.parent / "files").iterdir())
    artifact.write_bytes(b"changed synthetic input")
    with pytest.raises(MigrationRejected, match="approved_file_identity_changed"):
        prepare(
            plan,
            TASK_ROOT / "sources" / ("w14_package_" + uuid.uuid4().hex[:10]),
            "synthetic test only",
        )
