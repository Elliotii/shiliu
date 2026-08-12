from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.ask.contracts import AnswerBlock, AskResponse, Citation, TraceSummary
from shiliu.web import create_web_app
from scripts.run_v4_goal3_ui_fixture import create_fixture_app
from scripts.run_v4_goal3_eval import (
    _deterministic_checks,
    _selected_runs,
    _validate_citation,
)


def test_ask_page_is_primary_shared_fast_deep_entry(app_paths) -> None:
    client = TestClient(create_web_app(Application(app_paths)))

    page = client.get("/ask")

    assert page.status_code == 200
    assert 'data-ask-page' in page.text
    assert 'name="mode" value="fast" checked' in page.text
    assert 'name="mode" value="deep"' in page.text
    assert "快速回答" in page.text
    assert "深入搜索" in page.text
    assert "/static/evidence-ui.js" in page.text
    assert "/static/ask.js" in page.text
    assert "使用深入搜索继续" in page.text
    assert "开发者 Trace" in page.text

    search = client.get("/search")
    assert search.status_code == 200
    assert "/static/evidence-ui.js" in search.text
    assert "/static/search.js" in search.text
    assert '<a href="/search">搜索证据</a>' in page.text
    assert '<a href="/search">搜索证据</a>' in search.text

    home = client.get("/")
    assert '<a href="/ask">问答</a>' in home.text
    assert '<a href="/search">搜索证据</a>' in home.text


def test_ask_static_resources_expose_safe_state_and_shared_evidence_contract(
    app_paths,
) -> None:
    client = TestClient(create_web_app(Application(app_paths)))

    ask_js = client.get("/static/ask.js")
    evidence_js = client.get("/static/evidence-ui.js")
    ask_css = client.get("/static/ask.css")
    evidence_css = client.get("/static/evidence-ui.css")

    assert (
        ask_js.status_code
        == evidence_js.status_code
        == ask_css.status_code
        == evidence_css.status_code
        == 200
    )
    source = ask_js.text
    assert "fetch('/api/ask'" in source
    assert "sequence !== requestSequence" in source
    assert "activeController?.abort()" in source
    assert "textContent" in source
    assert "innerHTML" not in source
    assert "mode: state.mode" in source
    assert "filters: filterPayload(state)" in source
    assert "data.execution_outcome !== 'generation_failed'" in source
    assert "['partial', 'insufficient'].includes(data.status)" in source
    assert "回答生成失败" in source
    assert "字幕检索可能已经完成" in source
    assert "response.status === 404" in source
    assert "fetch(`/api/ask/traces/" in source
    assert "window.__shiliuAsk" in source
    assert "renderEvidenceCard" in source
    assert "card.closest('.citation-extra[hidden]')" in source
    assert "toggle.setAttribute('aria-expanded', 'true')" in source
    assert "window.ShiliuEvidenceUI" in evidence_js.text
    assert ".is-citation-target" in evidence_css.text


def test_ui_fixture_covers_shared_renderer_states_trace_404_and_search() -> None:
    client = TestClient(create_fixture_app())

    fast = client.post(
        "/api/ask", json={"query": "MCP", "mode": "fast"}
    ).json()
    assert fast["status"] == "complete"
    assert len(fast["answer_blocks"]) == len(fast["citations"]) == 2
    assert fast["answer_blocks"][1]["citation_ids"] == [
        fast["citations"][0]["citation_id"],
        fast["citations"][1]["citation_id"],
    ]
    assert fast["citations"][0]["jump_url"].endswith("t=12")

    partial = client.post(
        "/api/ask", json={"query": "partial", "mode": "fast"}
    ).json()
    assert partial["status"] == "partial"
    assert partial["limitations"]

    insufficient = client.post(
        "/api/ask", json={"query": "insufficient", "mode": "fast"}
    ).json()
    assert insufficient["status"] == "insufficient"
    assert insufficient["answer_blocks"] == insufficient["citations"] == []

    deep = client.post(
        "/api/ask", json={"query": "MCP", "mode": "deep"}
    ).json()
    trace = client.get(f"/api/ask/traces/{deep['run_id']}").json()["trace"]
    assert trace["policy_version"] == "v4-deep-policy-v1"
    assert [event["action"]["kind"] for event in trace["events"] if "action" in event] == [
        "search_navigation",
        "search_transcripts",
        "read_transcript_window",
        "finish",
    ]

    missing = client.post(
        "/api/ask", json={"query": "trace404", "mode": "fast"}
    ).json()
    assert client.get(f"/api/ask/traces/{missing['run_id']}").status_code == 404

    search = client.post("/api/search", json={"query": "MCP"}).json()
    assert search["ok"] is True
    assert len(search["results"][0]["windows"]) == 2


def test_goal3_manifest_has_six_fast_and_required_four_deep_cases() -> None:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (root / "eval" / "v4_goal3_cases.json").read_text(encoding="utf-8")
    )
    cases = manifest["cases"]
    fast = _selected_runs(cases, mode="fast", case_ids=set())
    deep = _selected_runs(cases, mode="deep", case_ids=set())

    assert len(cases) == len(fast) == 6
    assert len(deep) == 4
    assert {case["category"] for case, _ in deep} == {
        "direct_fact_or_single_topic",
        "contextual_transcript_question",
        "cross_video_comparison",
        "no_reliable_evidence",
    }
    assert all("target_answer" not in case and "gold" not in case for case in cases)


def _trace(reason: str = "answer_ready") -> TraceSummary:
    return TraceSummary(
        query_count=1,
        retrieval_count=1,
        valid_evidence_count=1,
        stale_evidence_count=0,
        context_span_count=1,
        context_truncated=False,
        repair_used=False,
        latency_ms=1,
        termination_reason=reason,
    )


def _citation() -> Citation:
    return Citation(
        citation_id="citation_v1_" + "a" * 64,
        citation_identity_version="v4-citation-identity-v1",
        video_id=999,
        bvid="BV1234567890",
        title="仅用于 Checker 测试",
        source_type="human",
        source_language="zh",
        source_artifact_id="artifact",
        source_version="version",
        timeline_run_id="timeline",
        segment_ids=["segment"],
        start_time=0,
        end_time=1,
        quote_text="原字幕",
        jump_url="https://www.bilibili.com/video/BV1234567890?t=0",
    )


def _answering_response() -> AskResponse:
    citation = _citation()
    return AskResponse(
        run_id="run",
        mode="fast",
        status="complete",
        answer_blocks=[
            AnswerBlock(
                text="有字幕支持的回答",
                citation_ids=[citation.citation_id],
            )
        ],
        citations=[citation],
        limitations=[],
        termination_reason="answer_ready",
        trace_summary=_trace(),
    )


def _checks(response: AskResponse, *, reconstructable: bool = True):
    return _deterministic_checks(
        response,
        citation_checks=[
            {
                "citation_id": _citation().citation_id,
                "reconstructable": reconstructable,
                "error": None if reconstructable else "cannot reconstruct",
            }
        ]
        if response.citations
        else [],
        budget_respected=True,
    )


def test_eval_checker_rejects_response_trace_termination_mismatch() -> None:
    response = _answering_response().model_copy(
        update={"trace_summary": _trace("provider_error")}
    )
    assert _checks(response)["status_termination_valid"] is False


def test_eval_checker_rejects_insufficient_with_answer_or_citation() -> None:
    citation = _citation()
    response = AskResponse.model_construct(
        run_id="run",
        mode="fast",
        status="insufficient",
        answer_blocks=[
            AnswerBlock(text="不应存在", citation_ids=[citation.citation_id])
        ],
        citations=[citation],
        limitations=["证据不足"],
        termination_reason="answer_ready",
        trace_summary=_trace(),
    )
    checks = _checks(response)
    assert checks["contract_valid"] is False
    assert checks["status_termination_valid"] is False

    citation_only = AskResponse.model_construct(
        run_id="run",
        mode="fast",
        status="insufficient",
        answer_blocks=[],
        citations=[citation],
        limitations=["证据不足"],
        termination_reason="answer_ready",
        trace_summary=_trace(),
    )
    assert _checks(citation_only)["status_termination_valid"] is False


def test_eval_checker_rejects_answering_status_without_blocks() -> None:
    response = AskResponse.model_construct(
        run_id="run",
        mode="fast",
        status="partial",
        answer_blocks=[],
        citations=[],
        limitations=["只覆盖部分"],
        termination_reason="answer_ready",
        trace_summary=_trace(),
    )
    checks = _checks(response)
    assert checks["contract_valid"] is False
    assert checks["status_termination_valid"] is False


def test_eval_checker_rejects_missing_response_citation() -> None:
    response = AskResponse.model_construct(
        run_id="run",
        mode="fast",
        status="complete",
        answer_blocks=[
            AnswerBlock(
                text="引用不存在",
                citation_ids=["citation_v1_" + "b" * 64],
            )
        ],
        citations=[_citation()],
        limitations=[],
        termination_reason="answer_ready",
        trace_summary=_trace(),
    )
    checks = _checks(response)
    assert checks["citation_ids_resolve"] is False
    assert checks["status_termination_valid"] is False


def test_eval_citation_validator_rejects_unreconstructable_source(
    app_paths,
) -> None:
    with pytest.raises(ValueError, match="citation video is unavailable"):
        _validate_citation(Application(app_paths), _citation())


def test_navigation_event_without_citation_ids_cannot_prove_provenance() -> None:
    navigation_event = {"observation_kind": "navigation"}
    assert "citation_ids" not in navigation_event

    checks = _checks(_answering_response(), reconstructable=False)
    assert checks["citations_reconstruct_from_current_transcript"] is False
    assert checks["source_identity_current"] is False
    assert "navigation_not_cited" not in checks
