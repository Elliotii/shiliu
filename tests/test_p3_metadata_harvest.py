from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from shiliu import p3_metadata_harvest as harvest
from shiliu import bilibili
from shiliu.domain import PipelineError
from shiliu.config import load_config
from shiliu.metadata_backfill import validate_candidate
from shiliu.retry_after import parse_retry_after


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fixture_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    backup = tmp_path / "backup"
    frozen = [
        {"video_id": index, "bvid": f"BV{index:010d}", "part": 1}
        for index in range(1, 2297)
    ]
    p2_candidates = [{"video_id": index} for index in range(1, 15)]
    p2_exceptions = [
        {"video_id": index, "error_code": "upstream_error"}
        for index in (15, 16)
    ]
    _write_json(backup / "frozen-targets.json", frozen)
    _write_json(backup / "p2-candidates.json", p2_candidates)
    _write_json(backup / "p2-candidate-exceptions.json", p2_exceptions)
    candidate_sha = hashlib.sha256((backup / "p2-candidates.json").read_bytes()).hexdigest()
    _write_json(
        backup / "p2-apply-report.json",
        {
            "run_id": harvest.P2_RUN_ID,
            "candidate_sha256": candidate_sha,
            "apply": {"run_id": harvest.P2_RUN_ID, "counts": {"applied": 14}},
            "video_changes": [
                {"video_id": index, "changed_columns": ["published_at"]}
                for index in range(1, 15)
            ],
        },
    )
    frozen_sha = hashlib.sha256((backup / "frozen-targets.json").read_bytes()).hexdigest()
    monkeypatch.setattr(harvest, "FROZEN_TARGET_SHA256", frozen_sha)
    return backup


def _pubdate_response(bvid: str) -> dict[str, object]:
    return {
        "bvid": bvid,
        "source_field": "info.pubdate",
        "raw_pubdate": 1_700_000_000,
        "published_at": 1_700_000_000,
        "metadata_observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def test_retry_after_parses_delta_and_http_date() -> None:
    now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    assert parse_retry_after("4", now=now) == 4
    assert parse_retry_after("Fri, 25 Sep 2026 12:00:07 GMT", now=now) == 7
    assert parse_retry_after("n/a", now=now) is None
    assert parse_retry_after("-2", now=now) == 0


def test_bilibili_adapter_preserves_http_retry_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cli_root = tmp_path / "cli"
    for name in ("python", "bili"):
        executable = cli_root / ".venv" / "bin" / name
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.touch()
    adapter = bilibili.BilibiliAdapter(cli_root)
    stdout = json.dumps(
        {
            "ok": False,
            "error": {
                "code": "upstream_error",
                "message": "upstream request failed",
                "http_status": 429,
                "retry_after_seconds": 4,
            },
        }
    )
    monkeypatch.setattr(
        bilibili.subprocess,
        "run",
        lambda *_args, **_kwargs: bilibili.subprocess.CompletedProcess([], 1, stdout, ""),
    )

    with pytest.raises(PipelineError) as caught:
        adapter.fetch_video_pubdate("BV1234567890")

    assert caught.value.http_status == 429
    assert caught.value.retry_after_seconds == 4


def test_bridge_response_wrapper_accepts_upstream_keyword_arguments() -> None:
    cli_root = Path(load_config().bili_cli_root)
    interpreter = cli_root / ".venv" / "bin" / "python"
    if not interpreter.is_file():
        pytest.skip("configured upstream CLI runtime is unavailable")
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(repo_root / "src"), str(cli_root)))
    script = r'''import asyncio, json
from bilibili_api.utils.network import Api
import shiliu.bilibili_bridge as bridge

class Response:
    code = 429
    headers = {"Retry-After": "4"}
    def utf8_text(self): return "safe test response"

class FakeVideo:
    def __init__(self, **_kwargs): pass
    async def get_info(self):
        return Api._process_response(object(), resp=Response(), raw=False)

bridge.get_credential = lambda **_kwargs: None
bridge.video.Video = FakeVideo
try:
    asyncio.run(bridge.fetch_video_pubdate("BV1234567890"))
except Exception as exc:
    print(json.dumps({
        "http_status": getattr(exc, "http_status", None),
        "retry_after_seconds": getattr(exc, "retry_after_seconds", None),
    }))
'''
    result = subprocess.run(
        [str(interpreter), "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )

    assert result.returncode == 0, "configured bridge smoke test failed"
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {"http_status": 429, "retry_after_seconds": 4.0}


def test_target_plan_excludes_applied_and_pending_p2_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backup = _fixture_backup(tmp_path, monkeypatch)

    plan = harvest.load_target_plan(backup)

    assert len(plan["targets"]) == 2280
    target_ids = {row["video_id"] for row in plan["targets"]}
    assert not target_ids.intersection(range(1, 17))
    assert plan["p2_pending_retry_video_ids"] == [15, 16]


def test_resume_does_not_refetch_completed_target_and_candidates_validate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup = _fixture_backup(tmp_path, monkeypatch)
    requested: list[str] = []

    def fetch_one(bvid: str) -> dict[str, object]:
        requested.append(bvid)
        return _pubdate_response(bvid)

    options = {"min_interval": 0, "max_interval": 0, "sleep": lambda _: None}
    first = harvest.run_harvest(backup, fetch_one, max_targets=1, **options)
    second = harvest.run_harvest(backup, fetch_one, max_targets=1, **options)
    candidate_path = backup / "p3-harvest" / "p3-candidates.json"
    candidates = json.loads(candidate_path.read_text(encoding="utf-8"))

    assert first["targets_terminal"] == 1
    assert second["candidate_count"] == 2
    assert requested == ["BV0000000017", "BV0000000018"]
    assert [candidate["video_id"] for candidate in candidates] == [17, 18]
    for candidate in candidates:
        validate_candidate(candidate)


def test_interrupted_unknown_request_is_marked_without_refetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup = _fixture_backup(tmp_path, monkeypatch)
    harvest_dir = backup / "p3-harvest"
    harvest_dir.mkdir(parents=True)
    attempt = {
        "type": "attempt_started",
        "video_id": 17,
        "bvid": "BV0000000017",
        "attempt": 1,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (harvest_dir / "events.jsonl").write_text(json.dumps(attempt) + "\n", encoding="utf-8")
    requested: list[str] = []

    def fetch_one(bvid: str) -> dict[str, object]:
        requested.append(bvid)
        return _pubdate_response(bvid)

    result = harvest.run_harvest(
        backup,
        fetch_one,
        max_targets=0,
        min_interval=0,
        max_interval=0,
        sleep=lambda _: None,
    )

    exceptions = json.loads((harvest_dir / "p3-exceptions.json").read_text(encoding="utf-8"))
    assert requested == []
    assert result["exception_count"] == 1
    assert exceptions[0]["exception"] == "interrupted_request_outcome_unknown"


def test_retry_after_is_honored_before_bounded_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup = _fixture_backup(tmp_path, monkeypatch)
    waits: list[float] = []
    requested: list[str] = []

    class RateLimitError(RuntimeError):
        code = "upstream_error"
        retryable = True
        http_status = 429
        retry_after_seconds = 4.0

    def fetch_one(bvid: str) -> dict[str, object]:
        requested.append(bvid)
        if len(requested) == 1:
            raise RateLimitError("rate limited")
        return _pubdate_response(bvid)

    result = harvest.run_harvest(
        backup,
        fetch_one,
        max_targets=1,
        min_interval=0,
        max_interval=0,
        interval_picker=lambda _low, _high: 0,
        sleep=waits.append,
    )

    assert result["candidate_count"] == 1
    assert requested == ["BV0000000017", "BV0000000017"]
    assert waits == [4.0]


def test_repeated_rate_limit_stops_without_requesting_next_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup = _fixture_backup(tmp_path, monkeypatch)
    requested: list[str] = []

    class RateLimitError(RuntimeError):
        code = "upstream_error"
        retryable = True
        http_status = 412
        retry_after_seconds = 2.0

    def fetch_one(bvid: str) -> dict[str, object]:
        requested.append(bvid)
        raise RateLimitError("rate limited")

    result = harvest.run_harvest(
        backup,
        fetch_one,
        min_interval=0,
        max_interval=0,
        interval_picker=lambda _low, _high: 0,
        sleep=lambda _: None,
    )

    assert result["state"] == "stopped"
    assert result["stop_reason"] == "persistent_rate_limit"
    assert requested == ["BV0000000017", "BV0000000017"]
    manifest = json.loads((backup / "p3-harvest" / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["get_info_invocations"] == 2
