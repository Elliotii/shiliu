from __future__ import annotations

from pathlib import Path
import importlib.util

from shiliu.evidence.contracts import EvidenceContractError
from shiliu.evidence.stage3a import CandidateBuilderConfig


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / (
    "research/v3_5/product_query_set_v1/"
    "f1a_candidate_builder_major_cycle_1/run_f1a_scored_regressions.py"
)
SPEC = importlib.util.spec_from_file_location("f1a_recovery_runner", RUNNER_PATH)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def test_terminal_contract_audit_has_exact_authoritative_source_variant() -> None:
    assert RUNNER.AUTHORITATIVE_SOURCE_TERMINAL_CODES == {
        "no_supported_subtitle"
    }


def test_no_supported_subtitle_becomes_complete_source_unverifiable() -> None:
    terminal = RUNNER.normalize_source_terminal(
        query_id="PUBLIC_QUERY",
        query="public query text",
        error=EvidenceContractError(
            "no authoritative raw subtitle is available",
            code="no_supported_subtitle",
        ),
    )
    value = RUNNER.runtime_terminal(terminal)
    assert value == {
        "complete": True,
        "status": "source_unverifiable",
        "reason_code": "no_supported_subtitle",
        "recognized_source_terminal": True,
        "builder_called": False,
        "selector_called": False,
        "mechanical_gate_outcome": "terminal_unverifiable",
    }
    assert terminal.candidates == ()
    assert terminal.validation_errors == ()
    assert terminal.failure_category == "no_supported_subtitle"


def test_terminal_normalization_is_query_and_video_identity_independent() -> None:
    values = []
    for query_id, query in (("A", "one"), ("B", "two")):
        terminal = RUNNER.normalize_source_terminal(
            query_id=query_id,
            query=query,
            error=EvidenceContractError("missing", code="no_supported_subtitle"),
        )
        values.append(RUNNER.runtime_terminal(terminal))
    assert values[0] == values[1]


def test_non_source_contract_error_is_not_normalized() -> None:
    try:
        RUNNER.normalize_source_terminal(
            query_id="PUBLIC_QUERY",
            query="public query",
            error=EvidenceContractError(
                "identity mismatch", code="source_version_mismatch",
            ),
        )
    except EvidenceContractError as error:
        assert error.code == "source_version_mismatch"
    else:
        raise AssertionError("non-terminal contract defect was hidden")


def test_empty_search_candidate_set_retains_existing_upstream_terminal() -> None:
    candidate_set = RUNNER.resolve_from_search_candidates(
        "public query", {"raw_unit_candidates": [], "video_candidates": []},
        lambda _: (_ for _ in ()).throw(AssertionError("resolver called")),
        CandidateBuilderConfig(), query_id="PUBLIC_QUERY",
    )
    value = RUNNER.runtime_terminal(candidate_set)
    assert value["complete"] is True
    assert value["status"] == "upstream_retrieval_failure"
    assert value["recognized_source_terminal"] is False
