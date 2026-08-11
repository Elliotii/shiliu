#!/usr/bin/env python3
"""One-shot, local-only real-corpus onboarding driver.

All product mutations go through the loopback Web API. SQLite access is read-only
and is used only for source lookup, phase gates, and redacted progress metrics.
The source URL is never written to the progress file or emitted to stdout.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shiliu.config import AppPaths


PHASES = (
    ("latest_100", "latest_n", 100),
    ("latest_300", "latest_n", 300),
    ("all_history", "all", None),
)


class ProductApiError(RuntimeError):
    def __init__(self, message: str, *, code: str = "", status: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class RunnerSettings:
    base_url: str
    database: Path
    state_file: Path
    poll_seconds: int
    retry_seconds: int
    max_discovery_attempts: int


class OnboardingRunner:
    def __init__(self, settings: RunnerSettings, source_url: str) -> None:
        self.settings = settings
        self.source_url = source_url.strip()
        if not self.source_url:
            raise ValueError("source URL is empty")
        values = urllib.parse.parse_qs(urllib.parse.urlparse(self.source_url).query)
        try:
            self.folder_id = int((values.get("fid") or [""])[0])
        except ValueError as exc:
            raise ValueError("source URL has no valid fid") from exc
        if self.folder_id <= 0:
            raise ValueError("source URL has no valid fid")

    def run(self, *, initial_delay_seconds: int = 0) -> None:
        if initial_delay_seconds > 0:
            self._event("cooldown_wait", seconds=initial_delay_seconds)
            time.sleep(initial_delay_seconds)
        source_db_id = self._ensure_source()
        for phase_name, policy, limit in PHASES:
            self._ensure_history_coverage(source_db_id, policy=policy, limit=limit)
            self._write_state(
                status="running", phase=phase_name, source_db_id=source_db_id
            )
            self._drain_phase(source_db_id, phase_name)
            gate = self._phase_gate(source_db_id)
            self._event("phase_complete", phase=phase_name, **gate)
            self._write_state(
                status="phase_complete",
                phase=phase_name,
                source_db_id=source_db_id,
                gate=gate,
            )
        final = self._phase_gate(source_db_id)
        self._write_state(
            status="completed",
            phase="all_history",
            source_db_id=source_db_id,
            gate=final,
        )
        self._event("onboarding_complete", **final)

    def _ensure_source(self) -> int:
        existing = self._source_by_folder_from_url()
        if existing is not None:
            self._event("source_reused", source_db_id=int(existing["id"]))
            return int(existing["id"])

        retryable_codes = {
            "incomplete_snapshot",
            "local_api_unavailable",
            "upstream_error",
            "upstream_retryable",
            "upstream_timeout",
        }
        last_error: ProductApiError | None = None
        for attempt in range(1, self.settings.max_discovery_attempts + 1):
            self._write_state(
                status="discovering", phase="latest_100", discovery_attempt=attempt
            )
            try:
                preview = self._post("/api/sources/preview", {"url": self.source_url})
                remote_total = int(preview["preview"].get("media_count") or 0)
                if preview.get("already_added"):
                    existing = self._source_by_folder(
                        int(preview["preview"]["folder_id"])
                    )
                    if existing is None:
                        raise RuntimeError("source preview and database disagree")
                    return int(existing["id"])
                result = self._post(
                    "/api/sources",
                    {
                        "url": self.source_url,
                        "history_policy": "latest_n",
                        "history_limit": 100,
                    },
                    timeout_seconds=1200,
                )
                source_db_id = int(result["source_id"])
                self._event(
                    "source_created",
                    source_db_id=source_db_id,
                    remote_total=remote_total,
                    baseline_count=int(result.get("baseline_count") or 0),
                    history_queued=int(result.get("history_queued") or 0),
                )
                return source_db_id
            except ProductApiError as exc:
                last_error = exc
                if exc.code not in retryable_codes or attempt >= self.settings.max_discovery_attempts:
                    raise
                self._event(
                    "discovery_retry_wait",
                    attempt=attempt,
                    code=exc.code or "http_error",
                    seconds=self.settings.retry_seconds,
                )
                time.sleep(self.settings.retry_seconds)
        assert last_error is not None
        raise last_error

    def _source_by_folder_from_url(self) -> sqlite3.Row | None:
        return self._source_by_folder(self.folder_id)

    def _source_by_folder(self, folder_id: int) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM favorite_sources WHERE folder_id=?", (folder_id,)
            ).fetchone()

    def _ensure_history_coverage(
        self, source_db_id: int, *, policy: str, limit: int | None
    ) -> None:
        source = self._source(source_db_id)
        if (
            str(source["history_policy"]) == policy
            and (source["history_limit"] if policy == "latest_n" else None) == limit
        ):
            return
        result = self._post(
            f"/api/sources/{source_db_id}/history-coverage",
            {"history_policy": policy, "history_limit": limit},
        )
        self._event(
            "history_coverage_updated",
            policy=policy,
            limit=limit,
            history_pending=int(result.get("history_pending") or 0),
        )

    def _drain_phase(self, source_db_id: int, phase_name: str) -> None:
        while True:
            metrics = self._metrics(source_db_id)
            if int(metrics["pending_history"]) == 0:
                return
            source = self._source(source_db_id)
            status = str(source["status"])
            if status in {"needs_auth", "unavailable", "paused"}:
                raise RuntimeError(f"source requires operator action: {status}")
            if status == "cooldown":
                self._event(
                    "source_cooldown_wait",
                    phase=phase_name,
                    seconds=self.settings.retry_seconds,
                )
                time.sleep(self.settings.retry_seconds)
                sync = self._post(f"/api/sources/{source_db_id}/sync", {})
                self._wait_run(int(sync["run_id"]))
                continue
            started = self._post(f"/api/sources/{source_db_id}/history-drain", {})
            run = self._wait_run(int(started["run_id"]))
            metrics = self._metrics(source_db_id)
            self._event(
                "history_batch_complete",
                phase=phase_name,
                run_status=str(run["status"]),
                processed=int(run.get("processed_count") or 0),
                failed=int(run.get("failed_count") or 0),
                pending_history=int(metrics["pending_history"]),
            )
            self._write_state(
                status="running",
                phase=phase_name,
                source_db_id=source_db_id,
                metrics=metrics,
            )

    def _wait_run(self, run_id: int) -> dict[str, Any]:
        while True:
            payload = self._get(f"/api/sync-runs/{run_id}")
            run = dict(payload["run"])
            if str(run["status"]) != "running":
                if str(run["status"]) not in {"completed", "completed_with_errors"}:
                    raise RuntimeError(
                        f"sync run {run_id} failed: {run.get('error_summary') or run.get('message')}"
                    )
                return run
            time.sleep(self.settings.poll_seconds)

    def _phase_gate(self, source_db_id: int) -> dict[str, Any]:
        with self._connect() as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            units = int(connection.execute("SELECT COUNT(*) FROM retrieval_units").fetchone()[0])
            fts = int(connection.execute("SELECT COUNT(*) FROM retrieval_units_fts").fetchone()[0])
            removed = int(
                connection.execute(
                    "SELECT COUNT(*) FROM video_source_memberships "
                    "WHERE source_id=? AND removed_at IS NOT NULL",
                    (source_db_id,),
                ).fetchone()[0]
            )
        if integrity != "ok":
            raise RuntimeError(f"database integrity gate failed: {integrity}")
        if units != fts:
            raise RuntimeError(f"lexical index gate failed: units={units}, fts={fts}")
        metrics = self._metrics(source_db_id)
        return {
            "integrity": integrity,
            "retrieval_units": units,
            "fts_units": fts,
            "removed_memberships": removed,
            "remote_detected": int(metrics["remote_detected"]),
            "imported": int(metrics["imported"]),
            "completed": int(metrics["completed"]),
            "pending": int(metrics["pending"]),
            "failed": int(metrics["failed"]),
            "not_backfilled": int(metrics["not_backfilled"]),
            "pending_history": int(metrics["pending_history"]),
        }

    def _source(self, source_db_id: int) -> sqlite3.Row:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM favorite_sources WHERE id=?", (source_db_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("source disappeared during onboarding")
        return row

    def _metrics(self, source_db_id: int) -> dict[str, int | str | None]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                  COALESCE(s.media_count, COUNT(m.id)) AS remote_detected,
                  SUM(m.video_id IS NOT NULL) AS imported,
                  SUM(v.status='completed') AS completed,
                  SUM(m.queued_history=1) AS pending_history,
                  SUM(m.video_id IS NOT NULL AND v.status IN ('discovered','processing','retry_wait')) AS pending_pipeline,
                  SUM(m.video_id IS NOT NULL AND v.status IN ('needs_review','failed','unsupported')) AS failed,
                  SUM(m.video_id IS NULL AND m.queued_history=0) AS not_backfilled
                FROM favorite_sources s
                LEFT JOIN video_source_memberships m
                  ON m.source_id=s.id AND m.removed_at IS NULL
                LEFT JOIN videos v ON v.id=m.video_id
                WHERE s.id=?
                GROUP BY s.id
                """,
                (source_db_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("source metrics unavailable")
        value = dict(row)
        for key in (
            "remote_detected",
            "imported",
            "completed",
            "pending_history",
            "pending_pipeline",
            "failed",
            "not_backfilled",
        ):
            value[key] = int(value.get(key) or 0)
        value["pending"] = int(value["pending_history"]) + int(value["pending_pipeline"])
        return value

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"file:{self.settings.database}?mode=ro", uri=True, timeout=30
        )
        connection.row_factory = sqlite3.Row
        return connection

    def _post(
        self, path: str, payload: dict[str, Any], *, timeout_seconds: int = 60
    ) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.settings.base_url.rstrip("/") + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return self._request(request, timeout_seconds=timeout_seconds)

    def _get(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(self.settings.base_url.rstrip("/") + path)
        return self._request(request, timeout_seconds=60)

    @staticmethod
    def _request(
        request: urllib.request.Request, *, timeout_seconds: int
    ) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = {}
            raise ProductApiError(
                str(payload.get("error") or f"HTTP {exc.code}"),
                code=str(payload.get("code") or ""),
                status=exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            raise ProductApiError(
                f"local product API unavailable: {exc.reason}", code="local_api_unavailable"
            ) from exc
        if not isinstance(payload, dict):
            raise ProductApiError("local product API returned invalid JSON")
        if payload.get("ok") is False:
            raise ProductApiError(
                str(payload.get("error") or "product API rejected request"),
                code=str(payload.get("code") or ""),
            )
        return payload

    def _write_state(self, **payload: Any) -> None:
        value = {
            **payload,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.settings.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.settings.state_file.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(self.settings.state_file)

    @staticmethod
    def _event(name: str, **payload: Any) -> None:
        value = {
            "event": name,
            **payload,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        print(json.dumps(value, ensure_ascii=False), flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the one-shot local 100 → 300 → all favorite onboarding"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-url")
    source.add_argument("--source-url-file", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:18520")
    parser.add_argument("--initial-delay-seconds", type=int, default=0)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--retry-seconds", type=int, default=1200)
    parser.add_argument("--max-discovery-attempts", type=int, default=3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    paths = AppPaths.defaults()
    source_url = (
        args.source_url
        if args.source_url is not None
        else args.source_url_file.read_text(encoding="utf-8").strip()
    )
    if args.source_url_file is not None:
        args.source_url_file.unlink(missing_ok=True)
    settings = RunnerSettings(
        base_url=args.base_url,
        database=paths.database,
        state_file=paths.state_dir / "post-v5-onboarding-state.json",
        poll_seconds=max(1, args.poll_seconds),
        retry_seconds=max(60, args.retry_seconds),
        max_discovery_attempts=max(1, args.max_discovery_attempts),
    )
    OnboardingRunner(settings, source_url).run(
        initial_delay_seconds=max(0, args.initial_delay_seconds)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
