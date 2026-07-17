#!/usr/bin/env python3
"""One-time V2.1 cleanup for videos left in needs_review by the old model policy."""

from __future__ import annotations

import argparse
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shiliu.app import Application
from shiliu.pipeline import SUMMARY_ONLY_MAX_SECONDS, processing_policy
from shiliu.sync import ProcessLock, SyncAlreadyRunning


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


class RunLog:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **values: Any) -> None:
        payload = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event,
            **values,
        }
        line = json.dumps(payload, ensure_ascii=False, default=str)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        print(line, flush=True)


def candidates(app: Application) -> list[dict[str, Any]]:
    with app.db.connect() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM videos
            WHERE status='needs_review'
              AND error_code IN ('bad_provider_config', 'provider_insufficient_balance')
              AND raw_subtitle_path IS NOT NULL
            ORDER BY id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def discard_obsolete_stages(app: Application, video_id: int, policy: str) -> None:
    """Remove old failed stages that the selected V2.1 policy no longer requires."""
    stage_filter = ""
    parameters: list[Any] = [video_id]
    if policy == "summary_only":
        stage_filter = "AND stage_name IN ('transcript_cleanup', 'refined_transcript_cleanup')"
    elif policy != "subtitle_only":
        return
    with app.db.connect() as connection:
        connection.execute(
            f"""
            DELETE FROM pipeline_stages
            WHERE video_id=?
              AND status IN ('pending', 'retry_wait', 'needs_review')
              {stage_filter}
            """,
            parameters,
        )


def acquire_lock(app: Application, log: RunLog) -> ProcessLock:
    deadline = time.monotonic() + 15 * 60
    while True:
        lock = ProcessLock(app.paths.sync_lock)
        try:
            lock.__enter__()
            return lock
        except SyncAlreadyRunning:
            if time.monotonic() >= deadline:
                raise
            log.write("waiting_for_sync_lock", retry_in_seconds=30)
            time.sleep(30)


def main() -> int:
    arguments = parse_args()
    log = RunLog(arguments.log)
    app = Application()
    selected = candidates(app)
    policy_counts: dict[str, int] = {}
    for video in selected:
        policy = processing_policy(int(video.get("duration_seconds") or 0))
        policy_counts[policy] = policy_counts.get(policy, 0) + 1
    log.write(
        "run_started",
        dry_run=arguments.dry_run,
        candidate_count=len(selected),
        policy_counts=policy_counts,
    )
    if arguments.dry_run:
        for video in selected:
            log.write(
                "candidate",
                video_id=video["id"],
                bvid=video["source_id"],
                title=video["title"],
                duration_seconds=video["duration_seconds"],
                policy=processing_policy(int(video.get("duration_seconds") or 0)),
            )
        log.write("run_finished", dry_run=True)
        return 0

    lock = acquire_lock(app, log)
    completed = 0
    failed = 0
    try:
        for index, original in enumerate(selected, start=1):
            video_id = int(original["id"])
            video = app.db.get_video(video_id)
            if video is None or video.get("status") != "needs_review":
                log.write("video_skipped", video_id=video_id, reason="state_changed")
                continue
            duration = int(video.get("duration_seconds") or 0)
            policy = processing_policy(duration)
            log.write(
                "video_started",
                index=index,
                total=len(selected),
                video_id=video_id,
                bvid=video["source_id"],
                title=video["title"],
                duration_seconds=duration,
                policy=policy,
            )
            try:
                app.db.reset_failed_stages(video_id)
                app.pipeline.process_video(video_id)
                result = app.db.get_video(video_id) or {}
                discard_obsolete_stages(app, video_id, policy)
                successful = result.get("status") == "completed"
                completed += int(successful)
                failed += int(not successful)
                log.write(
                    "video_finished",
                    video_id=video_id,
                    status=result.get("status"),
                    error_code=result.get("error_code"),
                    error_message=result.get("error_message"),
                    has_summary=bool(result.get("summary_path")),
                )
            except Exception as exc:  # keep the one-time batch moving
                failed += 1
                log.write(
                    "video_exception",
                    video_id=video_id,
                    exception_type=type(exc).__name__,
                    error=str(exc),
                )
            if index < len(selected):
                time.sleep(random.randint(2, 6))
    finally:
        lock.__exit__(None, None, None)

    remaining = len(candidates(app))
    log.write(
        "run_finished",
        completed=completed,
        failed=failed,
        remaining_legacy_candidates=remaining,
        snapshot_created=False,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
