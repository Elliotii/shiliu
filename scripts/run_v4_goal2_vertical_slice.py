from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory

from shiliu.app import Application
from shiliu.ask import AskRequest
from shiliu.ask.citations import stable_citation_id
from shiliu.config import AppPaths, load_config
from shiliu.evidence.authority import bind_live_current_version
from shiliu.evidence.contracts import SourceArtifactReference
from shiliu.evidence.source import load_source_artifact
from shiliu.retrieval.product_search import build_bilibili_jump_url


DEFAULT_QUERIES = (
    "MCP 是如何连接模型和外部工具的？请根据相关视频字幕解释。",
    "这些视频如何讨论 AI 编程工具的上下文管理？请比较不同视频。",
    "量子香蕉协议 ZQ-999 在字幕库中的定义是什么？",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a small real-data, real-provider V4 Goal 2 vertical slice."
    )
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Question to run; may be repeated.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    queries = tuple(args.queries or DEFAULT_QUERIES)

    default_paths = AppPaths.defaults()
    if not default_paths.database.is_file() or not default_paths.config.is_file():
        raise SystemExit("Shiliu database or config is unavailable")
    config = load_config(default_paths)
    with TemporaryDirectory(prefix="shiliu-v4-g2-") as temp:
        root = Path(temp)
        state = root / "state"
        state.mkdir()
        database = state / "shiliu.db"
        _snapshot_database(default_paths.database, database)
        config_path = state / "config.toml"
        shutil.copy2(default_paths.config, config_path)
        content = Path(config.content_dir).expanduser()
        paths = AppPaths(
            state_dir=state,
            content_dir=content,
            database=database,
            config=config_path,
            logs_dir=state / "logs",
            videos_dir=content / "videos",
            sync_lock=state / "sync.lock",
        )
        application = Application(paths)
        results = [_run(application, query) for query in queries]

    payload = {
        "goal": "V4 Goal 2 real vertical slice",
        "query_count": len(results),
        "results": results,
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    return 0


def _run(application: Application, query: str) -> dict[str, object]:
    response = application.ask_service.ask(
        AskRequest(query=query, mode="deep")
    )
    trace = application.ask_service.get_trace(response.run_id) or {}
    events = trace.get("events")
    events = events if isinstance(events, list) else []
    actions = [
        value.get("action")
        for value in events
        if isinstance(value, dict)
        and value.get("event_type") == "decision"
        and isinstance(value.get("action"), dict)
    ]
    finalization = trace.get("finalization")
    finalization = finalization if isinstance(finalization, dict) else {}
    citations_valid = True
    citation_errors: list[str] = []
    for citation in response.citations:
        try:
            _validate_citation(application, citation)
        except Exception as exc:
            citations_valid = False
            citation_errors.append(f"{type(exc).__name__}: {exc}"[:300])
    return {
        "query": query,
        "status": response.status,
        "termination_reason": response.termination_reason,
        "decision_rounds": response.trace_summary.decision_rounds,
        "tool_calls": response.trace_summary.tool_calls,
        "actions": actions,
        "visited_video_count": response.trace_summary.visited_video_count,
        "visited_segment_count": response.trace_summary.visited_segment_count,
        "navigation_result_count": response.trace_summary.navigation_result_count,
        "evidence_count": int(trace.get("evidence_count", 0)),
        "evidence_candidate_dropped_count": int(
            trace.get("evidence_candidate_dropped_count", 0)
        ),
        "stale_evidence_count": response.trace_summary.stale_evidence_count,
        "answer_calls": int(finalization.get("answer_calls", 0)),
        "repair_calls": int(finalization.get("repair_calls", 0)),
        "transport_retry_count": int(
            finalization.get("transport_retry_count", 0)
        )
        + sum(
            int(value.get("retry_count", 0))
            for value in events
            if isinstance(value, dict)
            and value.get("event_type") in {"decision", "decision_error"}
        ),
        "latency_ms": response.trace_summary.latency_ms,
        "agent_usage": trace.get("usage"),
        "answer_usage": finalization.get("answer_usage"),
        "context_truncated": response.trace_summary.context_truncated,
        "limitations": response.limitations,
        "citation_count": len(response.citations),
        "citation_validation": {
            "valid": citations_valid,
            "errors": citation_errors,
        },
        "errors": trace.get("errors"),
    }


def _validate_citation(application: Application, citation) -> None:
    video = application.db.get_video(citation.video_id)
    if video is None:
        raise ValueError("citation video is unavailable")
    reference = SourceArtifactReference(
        platform=str(video["platform"]),
        source_id=str(video["source_id"]),
        part=int(video["part"]),
        source_type=str(video.get("subtitle_source") or "unknown"),
        source_language=str(video.get("subtitle_language") or "unknown"),
        artifact_path=str(video.get("raw_subtitle_path") or ""),
    )
    binding = bind_live_current_version(
        reference, db=application.db, video_id=citation.video_id
    )
    if (
        binding.source_artifact_id != citation.source_artifact_id
        or binding.source_version != citation.source_version
    ):
        raise ValueError("citation source identity is stale")
    artifact = load_source_artifact(
        reference, expected_source_version=citation.source_version
    )
    by_id = {value.segment_id: value for value in artifact.segments}
    segments = tuple(by_id[value] for value in citation.segment_ids)
    if any(value.timeline_run_id != citation.timeline_run_id for value in segments):
        raise ValueError("citation crosses transcript timelines")
    expected_id = stable_citation_id(
        source_artifact_id=citation.source_artifact_id,
        source_version=citation.source_version,
        timeline_run_id=citation.timeline_run_id,
        segments=segments,
    )
    quote = "\n".join(
        value.source_text.strip()
        for value in segments
        if value.source_text.strip()
    )
    jump_url = build_bilibili_jump_url(
        str(video.get("video_url") or ""),
        citation.bvid,
        segments[0].start_time,
    )
    if (
        expected_id != citation.citation_id
        or quote != citation.quote_text
        or segments[0].start_time != citation.start_time
        or segments[-1].end_time != citation.end_time
        or jump_url != citation.jump_url
    ):
        raise ValueError("citation projection cannot be reconstructed")


def _snapshot_database(source: Path, target: Path) -> None:
    source_connection = sqlite3.connect(
        f"file:{source}?mode=ro", uri=True
    )
    target_connection = sqlite3.connect(target)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
