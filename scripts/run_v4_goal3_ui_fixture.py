from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import time

import uvicorn

from shiliu.app import Application
from shiliu.ask.contracts import (
    AnswerBlock,
    AskRequest,
    AskResponse,
    Citation,
    TraceSummary,
)
from shiliu.config import AppPaths
from shiliu.web import create_web_app


_TEMP = TemporaryDirectory(prefix="shiliu-v4-g3-ui-")


def create_fixture_app():
    root = Path(_TEMP.name)
    state = root / "state"
    content = root / "content"
    state.mkdir(exist_ok=True)
    content.mkdir(exist_ok=True)
    paths = AppPaths(
        state_dir=state,
        content_dir=content,
        database=state / "shiliu.db",
        config=state / "config.toml",
        logs_dir=state / "logs",
        videos_dir=content / "videos",
        sync_lock=state / "sync.lock",
    )
    core = Application(paths)
    core._ask_service = _FixtureAskService()
    core._product_search = _FixtureProductSearch()
    return create_web_app(core)


class _FixtureAskService:
    def __init__(self) -> None:
        self._counter = 0
        self._traces: dict[str, dict[str, object]] = {}

    def ask(self, request: AskRequest) -> AskResponse:
        self._counter += 1
        run_id = f"ask_run_ui_fixture_{self._counter}"
        query = request.query.casefold()
        if "loading" in query:
            time.sleep(1.5)
        citations = _citations()
        status = "complete"
        termination_reason = "answer_ready"
        answer_blocks = [
            AnswerBlock(
                text="MCP 客户端把模型与外部工具或数据源连接起来。",
                citation_ids=[citations[0].citation_id],
            ),
            AnswerBlock(
                text=(
                    "工具执行结果会作为新的上下文返回给模型继续处理；如果结果"
                    "不足以支持下一步，模型仍需明确保留限制，并根据已经观察到的"
                    "信息调整查询或读取相邻字幕，而不是把导航摘要当成事实答案。"
                ),
                citation_ids=[
                    citations[0].citation_id,
                    citations[1].citation_id,
                ],
            ),
        ]
        limitations: list[str] = []
        if "partial" in query:
            status = "partial"
            answer_blocks = answer_blocks[:1]
            citations = citations[:1]
            limitations = ["现有字幕只覆盖了问题的一部分"]
        elif "insufficient" in query:
            status = "insufficient"
            termination_reason = "evidence_unavailable"
            answer_blocks = []
            citations = []
            limitations = ["没有找到当前版本的可靠字幕证据"]
        elif "provider" in query:
            status = "insufficient"
            termination_reason = "provider_error"
            answer_blocks = []
            citations = []
            limitations = ["回答服务暂时不可用"]
        deep = request.mode == "deep"
        summary = TraceSummary(
            query_count=2 if deep else 1,
            retrieval_count=1,
            valid_evidence_count=len(citations),
            stale_evidence_count=0,
            context_span_count=len(citations),
            context_truncated=False,
            repair_used=False,
            latency_ms=1480 if deep else 420,
            termination_reason=termination_reason,
            decision_rounds=4 if deep else 0,
            tool_calls=3 if deep else 0,
            visited_video_count=4 if deep else 0,
            visited_segment_count=18 if deep else 0,
            navigation_result_count=6 if deep else 0,
            evidence_candidate_dropped_count=2 if deep else 0,
        )
        response = AskResponse(
            run_id=run_id,
            mode=request.mode,
            status=status,
            answer_blocks=answer_blocks,
            citations=citations,
            limitations=limitations,
            termination_reason=termination_reason,
            trace_summary=summary,
        )
        if "trace404" not in query:
            self._traces[run_id] = {
                "run_id": run_id,
                "mode": request.mode,
                "policy_version": "v4-deep-policy-v1" if deep else None,
                "status": status,
                "termination_reason": termination_reason,
                "decision_rounds": summary.decision_rounds,
                "tool_calls": summary.tool_calls,
                "visited_video_count": summary.visited_video_count,
                "visited_segment_count": summary.visited_segment_count,
                "evidence_candidate_dropped_count": (
                    summary.evidence_candidate_dropped_count
                ),
                "events": (
                    [
                        {
                            "event_type": "decision",
                            "action": {
                                "kind": "search_navigation",
                                "query": request.query,
                            },
                            "latency_ms": 120,
                        },
                        {
                            "event_type": "observation",
                            "observation_kind": "navigation",
                            "bounded_observation_summary": (
                                "navigation returned 6 videos"
                            ),
                            "latency_ms": 35,
                        },
                        {
                            "event_type": "decision",
                            "action": {
                                "kind": "search_transcripts",
                                "query": request.query,
                                "video_ids": [1, 2, 3, 4],
                            },
                            "latency_ms": 180,
                        },
                        {
                            "event_type": "observation",
                            "observation_kind": "transcript_search",
                            "bounded_observation_summary": (
                                "transcript search returned 2 spans"
                            ),
                            "latency_ms": 80,
                        },
                        {
                            "event_type": "decision",
                            "action": {
                                "kind": "read_transcript_window",
                                "anchor_segment_id": "segment_fixture_1",
                                "before": 2,
                                "after": 2,
                            },
                            "latency_ms": 100,
                        },
                        {
                            "event_type": "decision",
                            "action": {
                                "kind": "finish",
                                "summary": "evidence ready",
                            },
                            "latency_ms": 90,
                        },
                    ]
                    if deep
                    else []
                ),
                "usage": (
                    [{"role": "agent_action", "total_tokens": 1200}]
                    if deep
                    else None
                ),
                "answer_usage": [
                    {"role": "grounded_answer", "total_tokens": 640}
                ],
            }
        return response

    def get_trace(self, run_id: str):
        value = self._traces.get(run_id)
        return dict(value) if value is not None else None


@dataclass(frozen=True)
class _FixtureSearchResponse:
    def as_dict(self) -> dict[str, object]:
        return {
            "trace_id": "search_trace_ui_fixture",
            "trace_persisted": False,
            "presentation_trace_persisted": False,
            "plan": {},
            "executed_mode": "lexical",
            "fallback": False,
            "fallback_reason": None,
            "returned_group_count": 1,
            "warnings": [],
            "results": [
                {
                    "video_id": 1,
                    "bvid": "BV1fixture",
                    "title": "MCP 与工具连接",
                    "uploader": "Fixture UP",
                    "cover_url": None,
                    "detail_url": "/videos/1/transcript",
                    "duration": 300,
                    "reading_state": "unread",
                    "marked": False,
                    "folder_names": ["产品验证"],
                    "matched_unit_count": 2,
                    "total_window_count": 2,
                    "additional_window_count": 0,
                    "windows": [
                        {
                            "window_start": 12,
                            "window_end": 20,
                            "duration": 8,
                            "excerpt": (
                                "MCP 客户端把模型与外部工具或数据源连接起来。"
                            ),
                            "subtitle_sources": ["human"],
                            "jump_url": (
                                "https://www.bilibili.com/video/"
                                "BV1fixture?t=12"
                            ),
                            "jump_time": 12,
                            "jump_source": "exact_entity_term",
                            "chapter": None,
                        },
                        {
                            "window_start": 42,
                            "window_end": 50,
                            "duration": 8,
                            "excerpt": (
                                "工具执行结果会返回给模型，作为下一步上下文。"
                                "如果结果不足，模型会根据已经观察到的信息调整查询，"
                                "或读取相邻字幕确认语境；导航摘要只帮助选择视频，"
                                "不能替代最终引用的原字幕证据。"
                            ),
                            "subtitle_sources": ["human"],
                            "jump_url": (
                                "https://www.bilibili.com/video/"
                                "BV1fixture?t=42"
                            ),
                            "jump_time": 42,
                            "jump_source": "exact_query_phrase",
                            "chapter": None,
                        },
                    ],
                    "match_excerpt": "",
                }
            ],
        }


class _FixtureProductSearch:
    def search(self, _request):
        return _FixtureSearchResponse()


def _citations() -> list[Citation]:
    common = {
        "citation_identity_version": "v4-citation-identity-v1",
        "video_id": 1,
        "bvid": "BV1fixture",
        "title": "MCP 与工具连接",
        "source_type": "human",
        "source_language": "zh",
        "source_artifact_id": "source_artifact_fixture",
        "source_version": "source_version_fixture",
        "timeline_run_id": "timeline_run_fixture",
    }
    return [
        Citation(
            citation_id="citation_fixture_1",
            segment_ids=["segment_fixture_1"],
            start_time=12,
            end_time=20,
            quote_text="MCP 客户端把模型与外部工具或数据源连接起来。",
            jump_url="https://www.bilibili.com/video/BV1fixture?t=12",
            **common,
        ),
        Citation(
            citation_id="citation_fixture_2",
            segment_ids=["segment_fixture_2"],
            start_time=42,
            end_time=50,
            quote_text=(
                "工具执行结果会返回给模型，作为下一步上下文。如果结果不足，"
                "模型会根据已经观察到的信息调整查询，或读取相邻字幕确认语境；"
                "导航摘要只帮助选择视频，不能替代最终引用的原字幕证据。"
            ),
            jump_url="https://www.bilibili.com/video/BV1fixture?t=42",
            **common,
        ),
    ]


if __name__ == "__main__":
    uvicorn.run(create_fixture_app(), host="127.0.0.1", port=18522)
