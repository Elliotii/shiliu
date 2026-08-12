from __future__ import annotations

import json
import sqlite3

from scripts.run_post_v5_onboarding import (
    ONBOARDING_LAUNCHD_LABEL,
    OnboardingRunner,
    PHASES,
    ProductApiError,
    RunnerSettings,
    _remove_submitted_onboarding_job,
)


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


def test_runner_retries_temporary_local_api_unavailability(tmp_path, monkeypatch) -> None:
    database = tmp_path / "shiliu.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE favorite_sources(id INTEGER PRIMARY KEY, folder_id INTEGER)"
        )
    settings = RunnerSettings(
        base_url="http://127.0.0.1:1",
        database=database,
        state_file=tmp_path / "state.json",
        poll_seconds=1,
        retry_seconds=60,
        max_discovery_attempts=2,
    )
    runner = OnboardingRunner(
        settings, "https://space.bilibili.com/1/favlist?fid=12345&ftype=create"
    )
    calls = 0

    def post(path, payload, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ProductApiError("offline", code="local_api_unavailable")
        if path.endswith("preview"):
            return {
                "ok": True,
                "already_added": False,
                "preview": {"folder_id": 12345, "media_count": 2},
            }
        return {
            "ok": True,
            "source_id": 9,
            "baseline_count": 2,
            "history_queued": 2,
        }

    runner._post = post  # type: ignore[method-assign]
    wait_states = []

    def fake_sleep(_):
        wait_states.append(json.loads(settings.state_file.read_text(encoding="utf-8")))

    monkeypatch.setattr("scripts.run_post_v5_onboarding.time.sleep", fake_sleep)

    assert runner._ensure_source() == 9
    assert calls == 3
    assert wait_states[0]["status"] == "retry_wait"
    assert wait_states[0]["error_code"] == "local_api_unavailable"


def test_runner_only_unloads_its_exact_one_shot_launchd_job(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "scripts.run_post_v5_onboarding.subprocess.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    monkeypatch.delenv("XPC_SERVICE_NAME", raising=False)
    _remove_submitted_onboarding_job()
    monkeypatch.setenv("XPC_SERVICE_NAME", "app.shiliu.sync")
    _remove_submitted_onboarding_job()
    assert calls == []

    monkeypatch.setenv("XPC_SERVICE_NAME", ONBOARDING_LAUNCHD_LABEL)
    _remove_submitted_onboarding_job()

    assert calls[0][0][0] == [
        "/bin/launchctl",
        "remove",
        ONBOARDING_LAUNCHD_LABEL,
    ]
    assert calls[0][1]["check"] is False
