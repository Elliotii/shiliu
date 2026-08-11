from __future__ import annotations

import json
import sqlite3

from scripts.run_post_v5_onboarding import OnboardingRunner, PHASES, RunnerSettings


def test_runner_resolves_existing_source_without_remote_preview(tmp_path) -> None:
    database = tmp_path / "shiliu.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE favorite_sources(id INTEGER PRIMARY KEY, folder_id INTEGER)"
        )
        connection.execute("INSERT INTO favorite_sources VALUES(7, 12345)")
    settings = RunnerSettings(
        base_url="http://127.0.0.1:1",
        database=database,
        state_file=tmp_path / "state.json",
        poll_seconds=1,
        retry_seconds=60,
        max_discovery_attempts=1,
    )
    runner = OnboardingRunner(
        settings, "https://space.bilibili.com/1/favlist?fid=12345&ftype=create"
    )
    runner._post = lambda *args, **kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        AssertionError("existing-source lookup must not call the remote preview")
    )

    source = runner._source_by_folder_from_url()

    assert source is not None
    assert int(source["id"]) == 7


def test_runner_state_is_redacted_and_phase_order_is_fixed(tmp_path) -> None:
    settings = RunnerSettings(
        base_url="http://127.0.0.1:1",
        database=tmp_path / "shiliu.db",
        state_file=tmp_path / "state.json",
        poll_seconds=1,
        retry_seconds=60,
        max_discovery_attempts=1,
    )
    private_url = "https://space.bilibili.com/1/favlist?fid=12345&ftype=create"
    runner = OnboardingRunner(settings, private_url)

    runner._write_state(status="running", phase="latest_100")
    state_text = settings.state_file.read_text(encoding="utf-8")

    assert private_url not in state_text
    assert json.loads(state_text)["phase"] == "latest_100"
    assert PHASES == (
        ("latest_100", "latest_n", 100),
        ("latest_300", "latest_n", 300),
        ("all_history", "all", None),
    )
