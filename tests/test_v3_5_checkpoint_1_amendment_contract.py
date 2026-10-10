from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AMENDMENT = ROOT / "research/v3_5/checkpoints/checkpoint_1/amendment_v1"


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def test_checkpoint_1_derived_findings_amended() -> None:
    manifest = load_json(AMENDMENT / "checkpoint_1_amendment.manifest.json")
    assert manifest["checkpoint_1_amendment_status"] == "execution_candidate_ready"
    findings = manifest["amended_findings"]
    assert findings["candidate_builder_complete_group_coverage"]["numerator"] == 6
    assert findings["candidate_builder_complete_group_coverage"]["denominator"] == 13
    assert findings["candidate_builder_primary_failures"] == 6
    assert findings["primary_failure_distribution"] == {
        "candidate_builder_failure": 6,
        "deterministic_selector_failure": 5,
        "end_to_end_bundle_hit": 1,
        "gold_defined_evidence_absent": 1,
        "source_unverifiable": 1,
    }


def test_original_checkpoint_preserved_as_derived_supersession() -> None:
    audit = load_json(AMENDMENT / "checkpoint_1_amendment.audit.json")
    manifest = load_json(AMENDMENT / "checkpoint_1_amendment.manifest.json")
    assert audit["original_checkpoint_preserved"] is True
    assert (
        audit["original_checkpoint_status"]
        == "superseded_by_checkpoint_1_amendment_for_derived_findings"
    )
    assert manifest["p7_status"] == "complete_and_accepted"
    assert manifest["p8_prediction_set_status"] == "valid_and_frozen"


def test_authority_files_record_amendment() -> None:
    state = (ROOT / "V3_5_CURRENT_STATE.md").read_text()
    index = (ROOT / "03_V3_5_DECISION_AND_ARTIFACT_INDEX.md").read_text()
    plan = (ROOT / "02_PRODUCT_QUERY_SET_AND_REMAINING_V3_5_PLAN.md").read_text()
    for text in (state, index, plan):
        assert "v3.5-p8-scoring-amendment-v1" in text
        assert "gold_defined_evidence_absent" in text
        assert "P9_restarted: false" in text or "restarted: false" in text


def test_checkpoint_scope_and_downstream_boundary() -> None:
    audit = load_json(AMENDMENT / "checkpoint_1_amendment.audit.json")
    for key in (
        "predictions_rerun",
        "traces_rerun",
        "retrieval_rerun",
        "builder_rerun",
        "selector_rerun",
        "gate_rerun",
        "query_split_gold_changed",
        "component_behavior_changed",
        "p9_restarted",
        "f1a_authorized",
        "f1b_authorized",
        "stage4_started",
    ):
        assert audit[key] is False
    assert audit["identity"]["frozen_gold_opened"] is False


def test_checkpoint_amendment_manifest_hashes_match() -> None:
    rows = [
        json.loads(line)
        for line in (
            AMENDMENT / "checkpoint_1_amendment.file_hash_manifest.jsonl"
        )
        .read_text()
        .splitlines()
        if line
    ]
    assert len(rows) == 4
    assert {
        row["path"].rsplit("/", 1)[-1] for row in rows
    } == {
        "CHECKPOINT_1_AMENDMENT_REPORT.md",
        "checkpoint_1_amendment.manifest.json",
        "checkpoint_1_amendment.audit.json",
        "checkpoint_1_amendment.execution_decision.json",
    }
    for row in rows:
        assert digest(ROOT / row["path"]) == row["sha256"]
