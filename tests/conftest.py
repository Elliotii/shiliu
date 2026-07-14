from __future__ import annotations

from pathlib import Path

import pytest

from shiliu.config import AppPaths


@pytest.fixture
def app_paths(tmp_path: Path) -> AppPaths:
    state = tmp_path / "state"
    content = tmp_path / "content"
    return AppPaths(
        state_dir=state,
        content_dir=content,
        database=state / "shiliu.db",
        config=state / "config.toml",
        logs_dir=state / "logs",
        videos_dir=content / "videos",
        sync_lock=state / "sync.lock",
    )

