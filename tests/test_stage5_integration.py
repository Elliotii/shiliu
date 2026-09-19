from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.evidence.contracts import (
    SEARCH_CANDIDATE_CONTRACT_VERSION,
    SearchCandidateSet,
    SearchCandidateVideo,
    SearchRawUnitCandidate,
)
from shiliu.evidence.stage4 import (
    FINAL_CANDIDATE_BUILDER_VERSION,
    MECHANICAL_GATE_POLICY_VERSION,
    MechanicalGateDecision,
)
from shiliu.eval_v3_5.stage4b import SemanticJudgeOutput, to_decision
from shiliu.stage5 import (
    SEMANTIC_JUDGE_MAX_OBSERVED_LATENCY_MS,
    SEMANTIC_JUDGE_TIMEOUT_SECONDS,
    FrozenSemanticJudgeAdapter,
    Stage5IntegrationError,
    Stage5PipelineRequest,
    Stage5PipelineService,
    _resolve_codex_executable,
)
from shiliu.web import create_web_app


class StaticSearch:
    def __init__(self, value: SearchCandidateSet):
        self.value = value

    def search_library(self, request):
        return replace(
            self.value,
            original_query=request.query,
            request_parameters=request.model_dump(mode="json"),
        )


class FakeJudge:
    provider = "openai-codex-cli"
    model = "gpt-5.6-terra"

    def __init__(self, status: str = "sufficient"):
        self.status = status
        self.calls = 0

    def judge(self, request, bundle):
        self.calls += 1
        supported = ("现有证据支持主要问题",) if self.status in {"sufficient", "partial"} else ()
        missing = ("仍缺少一个方面",) if self.status == "partial" else ()
        conflicts = ("证据存在冲突",) if self.status == "partial" else ()
        blocker = "权威证据无法解释" if self.status == "unverifiable" else None
        reasons = {
            "sufficient": ("SJ_ALL_MATERIAL_NEEDS_SUPPORTED",),
            "partial": ("SJ_MEANINGFUL_SUBSET_WITH_MATERIAL_GAP", "SJ_BLOCKING_CONFLICT"),
            "insufficient": ("SJ_REVIEWABLE_WITHOUT_USABLE_MAIN_ANSWER",),
            "unverifiable": ("SJ_AUTHORITATIVE_VERIFICATION_BLOCKED",),
        }[self.status]
        output = SemanticJudgeOutput(
            query_id=request.query_id,
            status=self.status,
            supported_aspects=supported,
            missing_aspects=missing,
            conflicts=conflicts,
            reason_codes=reasons,
            confidence=0.8,
            evidence_ids_used=(
                bundle.candidate_ids if self.status in {"sufficient", "partial"} else ()
            ),
            verification_blocker=blocker,
            trace_id=request.trace_id,
        )
        return to_decision(output, request, bundle, judge_model=self.model), {
            "provider": self.provider,
            "model": self.model,
            "temperature": 0,
            "prompt_version": "v3.5-semantic-judge-prompt-v1",
            "policy_version": "v3.5-semantic-sufficiency-policy-v1",
            "parse_status": "valid",
            "raw_response_hash": "0" * 64,
            "latency_ms": 12,
            "retry_count": 0,
        }


def _metadata_candidate(video_id: int = 1) -> SearchRawUnitCandidate:
    return SearchRawUnitCandidate(
        unit_id=f"video:{video_id}",
        video_id=video_id,
        unit_type="video",
        raw_rank=1,
        raw_score=1.0,
        retrieval_method="lexical",
        subtitle_source="ai",
        source_language="zh",
        start_time=None,
        end_time=None,
        source_artifact_id=None,
        source_identity_version=None,
        source_version=None,
        source_version_authority=None,
        source_version_verified=False,
        source_version_expected=None,
        source_version_actual=None,
        segment_ids=(),
        segment_ordinals=(),
        timeline_run_id=None,
        mapping_status="not_applicable",
        candidate_eligibility=False,
        reason_codes=(),
        source_chunk_policy_version=None,
        mapping_version=None,
        replay_implementation_version=None,
    )


def _search_set(*, empty: bool = False) -> SearchCandidateSet:
    raw = () if empty else (_metadata_candidate(),)
    videos = () if empty else (
        SearchCandidateVideo(
            video_id=1,
            source_id="BV0000000001",
            product_rank=1,
            title="MCP 证据视频",
            uploader="UP",
            best_unit_id="video:1",
            best_unit_type="video",
            best_score=1.0,
            component_unit_ids=("video:1",),
            retrieval_methods=("lexical",),
            product_windows=(),
            source_types=("ai",),
            video_level_hit_present=True,
        ),
    )
    return SearchCandidateSet(
        contract_version=SEARCH_CANDIDATE_CONTRACT_VERSION,
        original_query="MCP 如何工作",
        request_parameters={},
        search_trace_id="search-trace",
        presentation_trace_id="search-trace",
        trace_persisted=True,
        presentation_trace_persisted=True,
        executed_mode="lexical",
        query_type="exact_term",
        fallback_state={"fallback": False, "fallback_reason": None},
        index_identity={"lexical_index_version": "v3-stage1-lexical-v1"},
        raw_unit_candidates=raw,
        video_candidates=videos,
        snapshot_id=None,
        runtime_corpus_identity="fixture",
        created_at="2026-07-27T00:00:00+00:00",
        reason_codes=("no_search_candidate",) if empty else (),
    )


def _service(app_paths, *, status: str = "sufficient", empty: bool = False):
    core = Application(app_paths)
    core.db.create_video(
        "BV0000000001", "MCP 证据视频", "UP", duration_seconds=300
    )
    video_dir = core.artifacts.videos_dir / "BV0000000001"
    video_dir.mkdir(parents=True, exist_ok=True)
    raw_path = video_dir / "subtitle-raw.json"
    raw_path.write_text(
        json.dumps(
            [
                {
                    "from": index * 5.0,
                    "to": index * 5.0 + 4.0,
                    "content": text,
                }
                for index, text in enumerate(
                    [
                        "MCP 是一种连接模型与工具的协议。",
                        "它通过标准接口暴露资源和工具。",
                        "客户端发现能力后发起结构化调用。",
                        "服务端执行工具并返回结构化结果。",
                    ]
                )
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    core.db.update_video(
        1,
        raw_subtitle_path=str(raw_path),
        subtitle_language="zh",
        subtitle_source="ai",
    )
    judge = FakeJudge(status)
    service = Stage5PipelineService(
        db=core.db,
        artifacts=core.artifacts,
        evidence_search=StaticSearch(_search_set(empty=empty)),
        trace_dir=app_paths.logs_dir / "stage5-test-traces",
        judge=judge,
    )
    return service, judge


@pytest.mark.parametrize(
    "status", ["sufficient", "partial", "insufficient", "unverifiable"]
)
def test_judge_eligible_pipeline_preserves_four_states_and_trace(
    app_paths, status: str
) -> None:
    service, judge = _service(app_paths, status=status)
    result = service.run(
        Stage5PipelineRequest(query="MCP 如何工作", mode="lexical", query_language="zh")
    )

    assert result["pipeline_status"] == "completed"
    assert result["mechanical_gate_result"]["status"] == "judge_eligible"
    assert result["sufficiency_decision"]["status"] == status
    assert judge.calls == 1
    evidence = result["evidence_bundle"]["evidence"]
    assert evidence and evidence[0]["quote_text"]
    assert evidence[0]["segment_ids"] and evidence[0]["evidence_id"]
    assert set(result["sufficiency_decision"]["evidence_ids_used"]).issubset(
        {item["evidence_id"] for item in evidence}
    )
    stages = result["trace"]["stages"]
    assert [value["stage_name"] for value in stages] == [
        "retrieval",
        "candidate_builder",
        "fine_selector",
        "mechanical_gate",
        "semantic_judge_or_bypass",
    ]
    assert all(value["component_version"] and value["latency_ms"] >= 0 for value in stages)
    assert all(value["parent_trace_id"] == result["trace_id"] for value in stages)
    assert service.get_trace(result["trace_id"])["trace_id"] == result["trace_id"]
    assert result["final_answer_generated"] is False


def test_source_unverifiable_bypasses_judge_and_preserves_terminal_status(
    app_paths,
) -> None:
    service, judge = _service(app_paths, empty=True)
    result = service.run(Stage5PipelineRequest(query="不存在的证据", mode="lexical"))

    assert result["pipeline_status"] == "completed"
    assert result["mechanical_gate_result"]["status"] == "source_unverifiable"
    assert result["semantic_sufficiency"] == {
        "status": None,
        "bypassed": True,
        "bypass_reason": "upstream_retrieval_failure",
    }
    assert result["sufficiency_decision"] is None
    assert judge.calls == 0


def test_invalid_synthetic_gate_bypasses_judge(app_paths) -> None:
    service, judge = _service(app_paths)
    trace = {"trace_id": "stage5_trace_" + "1" * 64, "stages": []}
    gate = MechanicalGateDecision(
        gate_decision_id="gate-invalid",
        gate_outcome="invalid",
        terminal_status="invalid",
        operational_reason_code="invalid_evidence_bundle",
        action_family="data_integrity_action",
        semantic_judge_required=False,
        query_id="query",
        evaluation_track="frozen_v3_end_to_end",
        end_to_end_claim_eligible=True,
        search_candidate_set_id="search",
        evidence_candidate_set_id="candidates",
        evidence_bundle_id=None,
        evidence_ids_used=(),
        mechanical_gate_policy_version=MECHANICAL_GATE_POLICY_VERSION,
        candidate_builder_version=FINAL_CANDIDATE_BUILDER_VERSION,
        selector_version="v3.5-deterministic-fine-selector-v1",
        trace_id=trace["trace_id"],
        validation_errors=("synthetic_invalid_contract",),
    )
    request = Stage5PipelineRequest(query="synthetic")
    formal, _ = service._sufficiency_request(
        request,
        request_id="query",
        trace_id=trace["trace_id"],
        search_candidate_set_id="search",
        candidate_set_id="candidates",
        candidate_set=_empty_candidate_set(),
        bundle=None,
        reason="invalid_evidence_bundle",
    )
    decision = service._route_semantic(
        trace,
        request=request,
        sufficiency_request=formal,
        gate=gate,
        bundle=None,
    )
    assert decision is None and judge.calls == 0
    assert trace["stages"][0]["status"] == "completed"


def _empty_candidate_set():
    from shiliu.evidence.stage3a import EvidenceCandidateSet

    return EvidenceCandidateSet(
        query_id="query",
        original_query="synthetic",
        candidates=(),
        evaluation_track="frozen_v3_end_to_end",
        end_to_end_claim_eligible=True,
        trace={},
        normalization_status="invalid",
        validation_errors=("synthetic_invalid_contract",),
        failure_category="invalid_evidence_bundle",
    )


def test_provider_and_parse_failures_remain_typed() -> None:
    def timeout_runner(prompt, schema, timeout):
        raise __import__("subprocess").TimeoutExpired("codex", timeout)

    timeout_adapter = FrozenSemanticJudgeAdapter(runner=timeout_runner)
    request, bundle = _judge_fixture()
    with pytest.raises(Stage5IntegrationError) as timeout:
        timeout_adapter.judge(request, bundle)
    assert timeout.value.error_type == "judge_timeout_or_provider_error"

    parse_adapter = FrozenSemanticJudgeAdapter(
        runner=lambda prompt, schema, timeout: "not json"
    )
    with pytest.raises(Stage5IntegrationError) as parse:
        parse_adapter.judge(request, bundle)
    assert parse.value.error_type == "structured_output_error"


def _judge_fixture():
    from shiliu.evidence.stage3a import EvidenceBundle
    from shiliu.evidence.stage4 import SufficiencyRequest

    bundle = EvidenceBundle(
        bundle_id="bundle",
        query_id="query",
        video_id=1,
        source_artifact_ids=("source",),
        source_versions=("a" * 64,),
        timeline_run_ids=("timeline",),
        candidate_ids=("evidence",),
        normalized_spans=(
            {
                "candidate_id": "evidence",
                "segment_ids": ["segment"],
                "start_time": 0.0,
                "end_time": 1.0,
                "timeline_run_id": "timeline",
            },
        ),
        union_duration=1.0,
        source_texts=("text",),
        selection_method="v3.5-deterministic-fine-selector-v1",
        score=1.0,
        score_breakdown={},
        evaluation_track="frozen_v3_end_to_end",
        end_to_end_claim_eligible=True,
        trace_id="trace",
        normalization_status="valid",
        validation_errors=(),
    )
    request = SufficiencyRequest(
        request_id="request",
        query_id="query",
        original_query="question",
        evaluation_track="frozen_v3_end_to_end",
        end_to_end_claim_eligible=True,
        search_candidate_set_id="search",
        evidence_candidate_set_id="candidates",
        evidence_bundle_id="bundle",
        evidence_resolution_status="resolved",
        failure_attribution=None,
        candidate_builder_version=FINAL_CANDIDATE_BUILDER_VERSION,
        selector_version="v3.5-deterministic-fine-selector-v1",
        source_states=("valid",),
        source_languages=("zh",),
        trace_id="trace",
        evidence_bundle=bundle.as_dict(),
        mechanical_gate_status="judge_eligible",
        policy_version="v3.5-semantic-sufficiency-policy-v1",
    )
    return request, bundle


def test_timeout_is_above_observed_maximum() -> None:
    assert SEMANTIC_JUDGE_TIMEOUT_SECONDS * 1000 > SEMANTIC_JUDGE_MAX_OBSERVED_LATENCY_MS


def test_codex_transport_accepts_explicit_launchagent_path(
    tmp_path, monkeypatch
) -> None:
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o700)
    monkeypatch.setenv("SHILIU_CODEX_EXECUTABLE", str(executable))
    monkeypatch.setattr("shiliu.stage5.shutil.which", lambda _name: None)

    assert _resolve_codex_executable() == str(executable)


def test_api_contract_and_trace_route(app_paths) -> None:
    service, _ = _service(app_paths)
    core = Application(app_paths)
    core._stage5_pipeline = service
    client = TestClient(create_web_app(core))
    response = client.post(
        "/api/evidence-sufficiency",
        json={"query": "MCP 如何工作", "mode": "lexical", "query_language": "zh"},
    )
    assert response.status_code == 200
    body = response.json()
    for key in (
        "request_id",
        "trace_id",
        "query",
        "search_candidate_set_summary",
        "evidence_bundle",
        "mechanical_gate_result",
        "sufficiency_decision",
        "component_versions",
        "stage_latencies",
        "warnings",
        "errors",
    ):
        assert key in body
    trace = client.get(
        f"/api/evidence-sufficiency/traces/{body['trace_id']}"
    )
    assert trace.status_code == 200
    assert trace.json()["trace"]["request_id"] == body["request_id"]


@pytest.mark.parametrize(
    "filters",
    [
        {"uploader": "Exact Creator"},
        {"uploader_contains": "creator"},
    ],
)
def test_stage5_route_supports_exact_and_contains_uploader_fields(
    app_paths, filters
) -> None:
    captured = []

    class CapturingPipeline:
        def run(self, payload):
            captured.append(payload)
            return {"pipeline_status": "completed", "errors": []}

    core = Application(app_paths)
    core._stage5_pipeline = CapturingPipeline()
    response = TestClient(create_web_app(core)).post(
        "/api/evidence-sufficiency",
        json={"query": "MCP", "filters": filters},
    )

    assert response.status_code == 200
    assert captured[0].filters.model_dump(exclude_none=True) == {
        **filters,
        "ignored": False,
    }


def test_stage5_ui_surface_and_safe_dom(app_paths) -> None:
    client = TestClient(create_web_app(Application(app_paths)))
    page = client.get("/search").text
    script = client.get("/static/search.js?v=5").text
    for marker in (
        'name="sufficiency"',
        "data-loading-stage",
        "data-pipeline-summary",
        "data-integration-limitations",
    ):
        assert marker in page
    for text in (
        "MECHANICAL GATE",
        "SEMANTIC SUFFICIENCY",
        "Evidence IDs Used",
        "/api/evidence-sufficiency",
    ):
        assert text in script
    assert ".innerHTML" not in script
    assert "不生成最终答案" in page
