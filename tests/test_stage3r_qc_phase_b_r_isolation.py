from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/stage3r_qc/phase_b_r"


def audit():
    return json.loads(
        (OUT / "isolation/heldout_access.audit.json").read_text(encoding="utf-8")
    )


def test_stage3r_qc_phase_b_r_does_not_modify_v3():
    value = json.loads(
        (OUT / "runtime_freeze/runtime_integrity.audit.json").read_text(encoding="utf-8")
    )
    assert value["runtime_hashes_stable"] is True
    assert value["snapshot_hash_stable"] is True
    assert value["retrieval_parameters_modified"] is False


def test_stage3r_qc_phase_b_r_does_not_call_candidate_builder():
    assert audit()["candidate_builder_calls"] == 0


def test_stage3r_qc_phase_b_r_does_not_call_selector():
    assert audit()["selector_calls"] == 0


def test_stage3r_qc_phase_b_r_does_not_access_heldout():
    assert audit()["heldout_accessed"] is False
    assert audit()["known_positive_held_out"] is False


def test_stage3r_qc_phase_b_r_does_not_call_external_llm():
    assert audit()["external_llm_calls"] == 0


def test_stage3r_qc_phase_b_r_does_not_call_external_embedding():
    assert audit()["external_embedding_calls"] == 0
    assert audit()["external_network_calls"] == 0
