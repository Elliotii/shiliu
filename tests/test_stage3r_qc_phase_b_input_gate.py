from __future__ import annotations

import json
from pathlib import Path

import pytest

from shiliu.eval_v3_5.stage3r_qc_phase_b import (
    PhaseBBlocked,
    freeze_approved_file,
    require_approved_source,
    validate_query_records,
)


ROOT = Path(__file__).resolve().parents[1]
CASE_IDS = json.loads(
    (ROOT / "research/v3_5/stage3r_qc/sample/selected_case_manifest.json").read_text()
)["selected_case_ids"]


def _rows() -> list[dict]:
    return [
        {
            "case_id": case_id,
            "q1_discovery_query": f"query {index}",
            "q2_retrieval_intents": [f"intent {index}"],
            "human_notes": "",
        }
        for index, case_id in enumerate(CASE_IDS)
    ]


def test_stage3r_qc_phase_b_requires_approved_query_file(tmp_path: Path) -> None:
    with pytest.raises(PhaseBBlocked, match="missing"):
        require_approved_source(tmp_path / "stage3r_qc_query_decisions.approved.jsonl")


def test_stage3r_qc_phase_b_rejects_template_file(tmp_path: Path) -> None:
    path = tmp_path / "stage3r_qc_query_decisions.template.jsonl"
    path.write_text("{}\n")
    with pytest.raises(PhaseBBlocked, match="cannot be used"):
        require_approved_source(path)


def test_stage3r_qc_phase_b_rejects_proposed_file(tmp_path: Path) -> None:
    path = tmp_path / "stage3r_qc_query_decisions.proposed.jsonl"
    path.write_text("{}\n")
    with pytest.raises(PhaseBBlocked, match="cannot be used"):
        require_approved_source(path)


def test_stage3r_qc_phase_b_validates_exact_case_set() -> None:
    rows = _rows()
    rows[-1]["case_id"] = "unexpected"
    with pytest.raises(PhaseBBlocked) as exc:
        validate_query_records(rows, CASE_IDS)
    assert any(error["code"] == "case_alignment" for error in exc.value.details["errors"])


def test_stage3r_qc_phase_b_freezes_approved_file_byte_for_byte(tmp_path: Path) -> None:
    source = tmp_path / "stage3r_qc_query_decisions.approved.jsonl"
    destination = tmp_path / "freeze/approved_query_decisions.jsonl"
    source.write_bytes(b' {\"human_notes\":\"\\xe5\\xa5\\xbd\"} \\n')
    result = freeze_approved_file(source, destination)
    assert source.read_bytes() == destination.read_bytes()
    assert result["byte_preserved"] and result["hash_match"]


def test_stage3r_qc_phase_b_rejects_duplicate_case_ids() -> None:
    rows = _rows()
    rows[-1]["case_id"] = rows[0]["case_id"]
    with pytest.raises(PhaseBBlocked) as exc:
        validate_query_records(rows, CASE_IDS)
    assert any(error["code"] == "duplicate_case_ids" for error in exc.value.details["errors"])


def test_stage3r_qc_phase_b_rejects_empty_q1() -> None:
    rows = _rows()
    rows[0]["q1_discovery_query"] = " "
    with pytest.raises(PhaseBBlocked):
        validate_query_records(rows, CASE_IDS)


def test_stage3r_qc_phase_b_rejects_empty_q2() -> None:
    rows = _rows()
    rows[0]["q2_retrieval_intents"] = []
    with pytest.raises(PhaseBBlocked):
        validate_query_records(rows, CASE_IDS)


def test_stage3r_qc_phase_b_rejects_more_than_three_q2_intents() -> None:
    rows = _rows()
    rows[0]["q2_retrieval_intents"] = ["a", "b", "c", "d"]
    with pytest.raises(PhaseBBlocked):
        validate_query_records(rows, CASE_IDS)
