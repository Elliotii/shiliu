from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory

from shiliu.app import Application
from shiliu.ask import AskRequest
from shiliu.config import AppPaths, load_config


DEFAULT_QUERIES = (
    "MCP 是如何连接模型和外部工具的？",
    "这些视频如何讨论 AI 编程工具的上下文管理？",
    "量子香蕉协议 ZQ-999 在字幕库中的定义是什么？",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a small real-data, real-provider V4 Goal 1 vertical slice."
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
    with TemporaryDirectory(prefix="shiliu-v4-g1-") as temp:
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
        "goal": "V4 Goal 1 real vertical slice",
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
    response = application.ask_service.ask(AskRequest(query=query))
    trace = application.ask_service.get_trace(response.run_id) or {}
    answer_usage = trace.get("answer_usage")
    return {
        "query": query,
        "status": response.status,
        "termination_reason": response.termination_reason,
        "answer_block_count": len(response.answer_blocks),
        "citation_count": len(response.citations),
        "citations_reconstructable": all(
            bool(value.quote_text)
            and value.end_time >= value.start_time
            and value.jump_url.startswith("http")
            for value in response.citations
        ),
        "query_analysis_calls": 1,
        "retrieval_executions": response.trace_summary.retrieval_count,
        "answer_calls": int(trace.get("answer_calls", 0)),
        "repair_calls": int(trace.get("repair_calls", 0)),
        "answer_provider_call_count": int(
            trace.get("answer_provider_call_count", 0)
        ),
        "latency_ms": response.trace_summary.latency_ms,
        "query_analysis_usage": trace.get("query_analysis_usage"),
        "answer_usage": answer_usage,
        "limitations": response.limitations,
        "observed_failure": (
            trace.get("answer_provider_error")
            or trace.get("initial_answer_provider_error")
            or trace.get("initial_answer_validation_errors")
            or trace.get("retrieval_errors")
            or trace.get("query_analysis_error")
        ),
    }


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
