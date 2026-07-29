from __future__ import annotations

import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from shiliu.app import Application
from shiliu.config import AppPaths, load_config
from shiliu.retrieval.product_search import ProductSearchRequest

from run_v4_goal3_eval import _snapshot_database


def main() -> int:
    source_paths = AppPaths.defaults()
    if not source_paths.database.is_file() or not source_paths.config.is_file():
        raise SystemExit("Shiliu database or config is unavailable")
    config = load_config(source_paths)

    with TemporaryDirectory(prefix="shiliu-v4-g3-search-") as temp:
        state = Path(temp) / "state"
        state.mkdir()
        database = state / "shiliu.db"
        _snapshot_database(source_paths.database, database)
        config_path = state / "config.toml"
        shutil.copy2(source_paths.config, config_path)
        content = Path(config.content_dir).expanduser()
        application = Application(
            AppPaths(
                state_dir=state,
                content_dir=content,
                database=database,
                config=config_path,
                logs_dir=state / "logs",
                videos_dir=content / "videos",
                sync_lock=state / "sync.lock",
            )
        )
        response = application.product_search.search(
            ProductSearchRequest(
                query="MCP",
                mode="lexical",
                scope="transcript_chunk",
                result_limit=10,
                max_windows_per_video=2,
            )
        )

    result = {
        "query": "MCP",
        "database_mode": "temporary_snapshot",
        "executed_mode": response.executed_mode,
        "returned_group_count": response.returned_group_count,
        "returned_window_count": sum(
            len(group.windows) for group in response.results
        ),
        "jump_urls_valid": all(
            str(window.get("jump_url", "")).startswith(
                "https://www.bilibili.com/video/"
            )
            and "?t=" in str(window.get("jump_url", ""))
            for group in response.results
            for window in group.windows
        ),
        "latency_ms": response.timing.total_ms,
        "trace_persisted": response.trace_persisted,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
