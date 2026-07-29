from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from shiliu.ask import (
    CITATION_IDENTITY_VERSION,
    AnswerBlock,
    AskRequest,
    AskResponse,
    stable_citation_id,
)
from shiliu.ask.contracts import Citation, TraceSummary
from shiliu.evidence import (
    EvidenceContractError,
    SourceArtifactReference,
    load_source_artifact,
)
from shiliu.llm import OpenAICompatibleProvider
from shiliu.ask.contracts import QueryAnalysis
from shiliu.domain import PipelineError


def _artifact(tmp_path, *, suffix: str = ""):
    directory = tmp_path / ("artifact" + suffix)
    directory.mkdir()
    path = directory / "subtitle-raw.json"
    path.write_text(
        json.dumps(
            [
                {"from": 0, "to": 1, "content": "第一段"},
                {"from": 1, "to": 2, "content": "第二段"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    reference = SourceArtifactReference(
        platform="bilibili",
        source_id="BV-citation",
        part=1,
        source_type="human",
        source_language="zh",
        artifact_path=str(path),
    )
    return path, load_source_artifact(reference)


def test_ask_contract_forbids_parallel_answer_and_claims() -> None:
    assert AskRequest.model_validate(
        {"query": "  ＭＣＰ  ", "mode": "fast"}
    ).query == "MCP"
    with pytest.raises(ValidationError):
        AskRequest.model_validate({"query": "MCP", "unexpected": True})
    with pytest.raises(ValidationError):
        AnswerBlock.model_validate({"text": "事实", "citation_ids": []})
    with pytest.raises(ValidationError):
        AskResponse.model_validate(
            {
                "run_id": "r",
                "mode": "fast",
                "status": "insufficient",
                "answer_blocks": [],
                "citations": [],
                "limitations": ["证据不足"],
                "termination_reason": "evidence_unavailable",
                "trace_summary": {
                    "query_count": 1,
                    "retrieval_count": 1,
                    "valid_evidence_count": 0,
                    "stale_evidence_count": 0,
                    "context_span_count": 0,
                    "context_truncated": False,
                    "repair_used": False,
                    "latency_ms": 1,
                    "termination_reason": "evidence_unavailable",
                },
                "answer": "parallel source",
                "claims": [],
            }
        )


def test_stable_citation_ignores_retrieval_rank_and_method(tmp_path) -> None:
    _, artifact = _artifact(tmp_path)
    values = artifact.segments
    first = stable_citation_id(
        source_artifact_id=artifact.source_artifact_id,
        source_version=artifact.source_version,
        timeline_run_id=values[0].timeline_run_id,
        segments=values,
    )
    second = stable_citation_id(
        source_artifact_id=artifact.source_artifact_id,
        source_version=artifact.source_version,
        timeline_run_id=values[0].timeline_run_id,
        segments=values,
    )
    assert first == second
    assert first.startswith("citation_v1_")
    assert CITATION_IDENTITY_VERSION == "v4-citation-identity-v1"


def test_stable_citation_changes_with_source_version_and_rejects_bad_order(
    tmp_path,
) -> None:
    path, original = _artifact(tmp_path)
    original_id = stable_citation_id(
        source_artifact_id=original.source_artifact_id,
        source_version=original.source_version,
        timeline_run_id=original.segments[0].timeline_run_id,
        segments=original.segments,
    )
    with pytest.raises(EvidenceContractError) as error:
        stable_citation_id(
            source_artifact_id=original.source_artifact_id,
            source_version=original.source_version,
            timeline_run_id=original.segments[0].timeline_run_id,
            segments=tuple(reversed(original.segments)),
        )
    assert error.value.code == "citation_segment_order_invalid"

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[1]["content"] = "第二段变化"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    reference = original.reference
    changed = load_source_artifact(reference)
    changed_id = stable_citation_id(
        source_artifact_id=changed.source_artifact_id,
        source_version=changed.source_version,
        timeline_run_id=changed.segments[0].timeline_run_id,
        segments=changed.segments,
    )
    assert changed.source_artifact_id == original.source_artifact_id
    assert changed_id != original_id


def test_structured_provider_uses_json_mode_and_one_retry() -> None:
    calls = 0
    bodies = []

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, headers, json):
            nonlocal calls
            calls += 1
            bodies.append(json)
            request = httpx.Request("POST", url)
            if calls == 1:
                return httpx.Response(503, request=request, text="busy")
            return httpx.Response(
                200,
                request=request,
                json={
                    "id": "response-1",
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"normalized_intent":"MCP",'
                                    '"search_queries":[],"entities":["MCP"],'
                                    '"language":"zh"}'
                                )
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 3},
                },
            )

    provider = OpenAICompatibleProvider(
        base_url="https://example.com/v1",
        api_key="secret",
        model="demo",
        thinking_enabled=False,
    )
    with patch("shiliu.llm.httpx.Client", FakeClient):
        response = provider.generate_structured(
            role="query_analysis",
            messages=[{"role": "user", "content": "MCP"}],
            response_schema=QueryAnalysis,
        )
    assert response.output.entities == ["MCP"]
    assert response.retry_count == 1 and calls == 2
    assert response.finish_reason == "stop"
    assert response.latency_ms >= 0
    assert bodies[-1]["response_format"] == {"type": "json_object"}
    assert bodies[-1]["temperature"] == 0


@pytest.mark.parametrize("method_name", ["complete_json", "complete_raw"])
def test_historical_provider_methods_keep_single_http_attempt(
    method_name,
) -> None:
    calls = 0

    class AlwaysUnavailableClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, headers, json):
            nonlocal calls
            calls += 1
            return httpx.Response(
                503,
                request=httpx.Request("POST", url),
                text="busy",
            )

    provider = OpenAICompatibleProvider(
        base_url="https://example.com/v1",
        api_key="secret",
        model="demo",
        thinking_enabled=False,
    )
    with patch("shiliu.llm.httpx.Client", AlwaysUnavailableClient):
        with pytest.raises(PipelineError) as error:
            if method_name == "complete_json":
                provider.complete_json("MCP", QueryAnalysis)
            else:
                provider.complete_raw("MCP")
    assert error.value.code == "provider_retryable"
    assert calls == 1
    assert error.value.completion_metadata["retry_count"] == 0


class _ProviderClock:
    def __init__(self, value: float = 1000) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _structured_provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url="https://example.com/v1",
        api_key="secret",
        model="demo",
        timeout_seconds=120,
        thinking_enabled=False,
    )


def _query_analysis_response(url: str) -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("POST", url),
        json={
            "id": "deadline-test",
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"normalized_intent":"MCP",'
                            '"search_queries":[],"entities":["MCP"],'
                            '"language":"zh"}'
                        )
                    },
                    "finish_reason": "stop",
                }
            ],
        },
    )


def test_structured_provider_httpx_timeout_at_deadline_is_not_retryable() -> None:
    clock = _ProviderClock()
    calls = 0

    class DeadlineClient:
        def __init__(self, *, timeout):
            self.timeout = float(timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, headers, json):
            nonlocal calls
            calls += 1
            clock.advance(self.timeout)
            raise httpx.ReadTimeout(
                "invocation deadline elapsed",
                request=httpx.Request("POST", url),
            )

    with (
        patch("shiliu.llm.time.monotonic", clock),
        patch("shiliu.llm.httpx.Client", DeadlineClient),
        pytest.raises(PipelineError) as error,
    ):
        _structured_provider().generate_structured(
            role="query_analysis",
            messages=[{"role": "user", "content": "MCP"}],
            response_schema=QueryAnalysis,
            timeout_seconds=3,
        )
    assert error.value.code == "deadline_exhausted"
    assert error.value.retryable is False
    assert error.value.completion_metadata["retry_count"] == 0
    assert calls == 1


def test_structured_provider_retries_network_error_while_deadline_remains() -> None:
    clock = _ProviderClock()
    calls = 0
    timeouts: list[float] = []

    class RecoveringClient:
        def __init__(self, *, timeout):
            self.timeout = float(timeout)
            timeouts.append(self.timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, headers, json):
            nonlocal calls
            calls += 1
            if calls == 1:
                clock.advance(1)
                raise httpx.ConnectError(
                    "temporary network failure",
                    request=httpx.Request("POST", url),
                )
            return _query_analysis_response(url)

    with (
        patch("shiliu.llm.time.monotonic", clock),
        patch("shiliu.llm.httpx.Client", RecoveringClient),
    ):
        response = _structured_provider().generate_structured(
            role="query_analysis",
            messages=[{"role": "user", "content": "MCP"}],
            response_schema=QueryAnalysis,
            timeout_seconds=10,
        )
    assert response.output.normalized_intent == "MCP"
    assert response.retry_count == 1
    assert calls == 2
    assert timeouts == [pytest.approx(10), pytest.approx(9)]


def test_structured_provider_does_not_retry_after_network_error_uses_deadline() -> None:
    clock = _ProviderClock()
    calls = 0

    class ExpiredNetworkClient:
        def __init__(self, *, timeout):
            self.timeout = float(timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, headers, json):
            nonlocal calls
            calls += 1
            clock.advance(self.timeout)
            raise httpx.ConnectError(
                "network failure consumed deadline",
                request=httpx.Request("POST", url),
            )

    with (
        patch("shiliu.llm.time.monotonic", clock),
        patch("shiliu.llm.httpx.Client", ExpiredNetworkClient),
        pytest.raises(PipelineError) as error,
    ):
        _structured_provider().generate_structured(
            role="query_analysis",
            messages=[{"role": "user", "content": "MCP"}],
            response_schema=QueryAnalysis,
            timeout_seconds=4,
        )
    assert error.value.code == "deadline_exhausted"
    assert error.value.retryable is False
    assert error.value.completion_metadata["retry_count"] == 0
    assert calls == 1
