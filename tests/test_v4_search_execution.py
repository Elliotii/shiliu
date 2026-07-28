from __future__ import annotations

from shiliu.evidence import EvidenceSearchService
from shiliu.retrieval.product_search import ProductSearchRequest
from tests.test_evidence_stage1b import _snapshot_search_service


def test_materializing_search_execution_never_retrieves_again(tmp_path) -> None:
    evidence, lexical, _, _ = _snapshot_search_service(tmp_path)
    execution = evidence.execute_search(
        ProductSearchRequest(
            query="MCP", scope="transcript_chunk", result_limit=4
        )
    )
    assert lexical.calls == 1
    first = evidence.materialize_execution(execution)
    second = evidence.materialize_execution(execution)
    assert lexical.calls == 1
    assert first.search_trace_id == second.search_trace_id
    assert [value.unit_id for value in first.raw_unit_candidates] == [
        value.unit_id for value in second.raw_unit_candidates
    ]


def test_compatibility_search_wrapper_still_uses_one_retrieval(tmp_path) -> None:
    evidence, lexical, _, _ = _snapshot_search_service(tmp_path)
    result = evidence.search_library(
        ProductSearchRequest(query="MCP", scope="transcript_chunk")
    )
    assert lexical.calls == 1
    assert result.raw_unit_candidates
    assert isinstance(evidence, EvidenceSearchService)
