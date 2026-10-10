from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "V5_D_CANDIDATE_REVISION_R1_EXPERIMENT_FREEZE.json"
R1_FREEZE_COMMIT = "789cf176adcc8c7a66dccbf0c507e875537bcc1a"
E1_MECHANICALLY_SUPERSEDED_FILES = {
    "scripts/v5_d_r1_source_runner.py",
    "tests/test_v5_d_r1_runner.py",
    "tests/test_v5_d_r1_freeze.py",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_freeze_binds_all_repo_artifacts_and_non_product_boundary() -> None:
    payload = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert payload["experiment_id"] == "V5D-R1-SOURCE-GATE-001"
    assert payload["candidate"]["version"] == "1.1.0"
    assert payload["candidate"]["runtime_registration"] is None
    assert payload["candidate"]["active"] is False
    assert payload["candidate"]["shadow"] is False
    assert payload["non_product_boundary"]["product_src_modification"] is False
    assert payload["non_product_boundary"]["default_product_import_or_discovery"] is False
    for relative, expected in payload["repo_file_sha256"].items():
        if relative in E1_MECHANICALLY_SUPERSEDED_FILES:
            historical = subprocess.run(
                [
                    "git",
                    "show",
                    f"{R1_FREEZE_COMMIT}:{relative}",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
            ).stdout
            assert hashlib.sha256(historical).hexdigest() == expected
        else:
            assert _sha256(ROOT / relative) == expected


def test_freeze_has_exact_source_order_budget_and_hard_gates() -> None:
    payload = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert payload["source_arm_order"] == [
        {"case_id": "V5D-S0-D-02", "arms": ["baseline", "treatment"]},
        {"case_id": "V5D-S0-D-04", "arms": ["treatment", "baseline"]},
    ]
    assert len(payload["task_attempt_identities"]) == 8
    assert payload["budget"]["valid_arms"] == 4
    assert payload["budget"]["outer_attempts"] == 8
    assert payload["budget"]["logical_provider_calls"] == 104
    assert payload["budget"]["paid_cost_reserve_stop_usd"] == "0.16"
    assert payload["budget"]["paid_cost_hard_stop_usd"] == "0.20"
    assert payload["source_gate"]["required_aspect_delta_min"] == 1
    assert payload["source_gate"]["current_grounded_citation_delta_min"] == 1
    assert payload["source_gate"]["both_pairs_must_pass"] is True


def test_freeze_keeps_reserve_and_heldout_closed() -> None:
    payload = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert payload["reserve_custody"]["open_authorized"] is False
    assert payload["reserve_custody"]["semantic_split_present"] is False
    assert payload["reserve_custody"]["reserve_runs"] == 0
    assert payload["reserve_custody"]["post_freeze_access_entries"] == 0
    assert payload["non_authorizations"]["heldout_execution"] is False
    assert payload["non_authorizations"]["v1_2_candidate"] is False
    assert payload["non_authorizations"]["stage_3_execution"] is False
