from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from shiliu.domain import FavoriteItem, StageName, StageStatus, VideoStatus


SCHEMA_VERSION = 6


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._backup_before_migration()
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS seen_items (
                    platform TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    part INTEGER NOT NULL DEFAULT 1,
                    is_baseline INTEGER NOT NULL DEFAULT 0,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    removed_at TEXT,
                    PRIMARY KEY (platform, source_id, part)
                );

                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    part INTEGER NOT NULL DEFAULT 1,
                    title TEXT NOT NULL,
                    uploader TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    description_links_json TEXT NOT NULL DEFAULT '[]',
                    video_url TEXT NOT NULL,
                    cover_url TEXT,
                    cover_path TEXT,
                    subtitle_language TEXT,
                    subtitle_source TEXT,
                    subtitle_upstream_type INTEGER,
                    raw_subtitle_path TEXT,
                    transcript_path TEXT,
                    summary_path TEXT,
                    artifact_dir TEXT,
                    status TEXT NOT NULL,
                    error_code TEXT,
                    error_message TEXT,
                    subtitle_check_count INTEGER NOT NULL DEFAULT 0,
                    subtitle_first_checked_at TEXT,
                    subtitle_next_check_at TEXT,
                    is_ignored INTEGER NOT NULL DEFAULT 0,
                    ignored_at TEXT,
                    discovered_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    removed_at TEXT,
                    UNIQUE (platform, source_id, part)
                );

                CREATE TABLE IF NOT EXISTS pipeline_stages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
                    stage_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT,
                    last_error_code TEXT,
                    last_error_message TEXT,
                    provider TEXT,
                    model TEXT,
                    prompt_version TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE (video_id, stage_name)
                );

                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    current_count INTEGER NOT NULL DEFAULT 0,
                    discovered_count INTEGER NOT NULL DEFAULT 0,
                    processed_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    error_summary TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    video_id INTEGER REFERENCES videos(id) ON DELETE SET NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    processed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS favorite_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL DEFAULT 'bilibili',
                    original_url TEXT NOT NULL DEFAULT '',
                    account_id INTEGER,
                    account_name TEXT NOT NULL DEFAULT '',
                    folder_id INTEGER NOT NULL,
                    folder_title TEXT NOT NULL DEFAULT '',
                    media_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    history_policy TEXT NOT NULL DEFAULT 'future_only',
                    history_limit INTEGER,
                    baseline_initialized INTEGER NOT NULL DEFAULT 0,
                    cooldown_until TEXT,
                    last_sync_at TEXT,
                    last_error_code TEXT,
                    last_error_message TEXT,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(platform, folder_id)
                );

                CREATE TABLE IF NOT EXISTS video_source_memberships (
                    source_id INTEGER NOT NULL REFERENCES favorite_sources(id) ON DELETE CASCADE,
                    bvid TEXT NOT NULL,
                    video_id INTEGER REFERENCES videos(id) ON DELETE SET NULL,
                    title TEXT NOT NULL DEFAULT '',
                    uploader TEXT NOT NULL DEFAULT '',
                    favorite_time INTEGER,
                    source_position INTEGER NOT NULL DEFAULT 0,
                    is_baseline INTEGER NOT NULL DEFAULT 0,
                    queued_history INTEGER NOT NULL DEFAULT 0,
                    first_observed_at TEXT NOT NULL,
                    last_observed_at TEXT NOT NULL,
                    removed_at TEXT,
                    PRIMARY KEY(source_id, bvid)
                );

                CREATE TABLE IF NOT EXISTS asr_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL UNIQUE REFERENCES videos(id) ON DELETE CASCADE,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    trigger_mode TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    task_id TEXT,
                    remote_file_url TEXT,
                    result_url TEXT,
                    audio_path TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT,
                    last_error_code TEXT,
                    last_error_message TEXT,
                    submitted_at TEXT,
                    completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS video_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS taxonomy_corpus_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    selected_source_ids_json TEXT NOT NULL,
                    membership_count INTEGER NOT NULL,
                    content_count INTEGER NOT NULL,
                    duplicate_memberships_merged INTEGER NOT NULL,
                    discovery_eligible_count INTEGER NOT NULL,
                    trial_assignment_only_count INTEGER NOT NULL,
                    evidence_counts_json TEXT NOT NULL,
                    snapshot_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    frozen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS taxonomy_classification_cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL REFERENCES taxonomy_corpus_snapshots(id) ON DELETE RESTRICT,
                    content_key TEXT NOT NULL,
                    video_id INTEGER REFERENCES videos(id) ON DELETE SET NULL,
                    platform TEXT NOT NULL,
                    source_content_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    evidence_level TEXT NOT NULL,
                    discovery_eligible INTEGER NOT NULL,
                    selected_revision TEXT,
                    stored_card_json TEXT NOT NULL,
                    discovery_view_json TEXT NOT NULL,
                    card_hash TEXT NOT NULL,
                    discovery_view_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(snapshot_id, content_key),
                    UNIQUE(snapshot_id, ordinal)
                );

                CREATE TABLE IF NOT EXISTS taxonomy_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_kind TEXT NOT NULL DEFAULT 'production',
                    status TEXT NOT NULL DEFAULT 'pending',
                    current_stage TEXT,
                    corpus_snapshot_id INTEGER REFERENCES taxonomy_corpus_snapshots(id) ON DELETE RESTRICT,
                    engine TEXT,
                    engine_version TEXT,
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    search_enabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    last_error_code TEXT,
                    last_error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS taxonomy_stage_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL REFERENCES taxonomy_runs(id) ON DELETE CASCADE,
                    stage_name TEXT NOT NULL,
                    unit_key TEXT NOT NULL DEFAULT 'main',
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT,
                    input_hash TEXT,
                    output_path TEXT,
                    output_hash TEXT,
                    provider TEXT,
                    model TEXT,
                    prompt_version TEXT,
                    prompt_hash TEXT,
                    thinking_enabled INTEGER,
                    reasoning_effort TEXT,
                    temperature REAL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    reasoning_tokens INTEGER,
                    cost_value REAL,
                    cost_currency TEXT,
                    elapsed_seconds REAL,
                    last_error_code TEXT,
                    last_error_message TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(run_id, stage_name, unit_key)
                );

                CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
                CREATE INDEX IF NOT EXISTS idx_stages_due ON pipeline_stages(status, next_retry_at);
                CREATE INDEX IF NOT EXISTS idx_events_status ON events(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_sources_status ON favorite_sources(status, cooldown_until);
                CREATE INDEX IF NOT EXISTS idx_memberships_video ON video_source_memberships(video_id);
                CREATE INDEX IF NOT EXISTS idx_memberships_history ON video_source_memberships(queued_history, source_id, source_position);
                CREATE INDEX IF NOT EXISTS idx_asr_jobs_due ON asr_jobs(status, next_retry_at);
                CREATE INDEX IF NOT EXISTS idx_video_notes_video ON video_notes(video_id, created_at, id);
                CREATE INDEX IF NOT EXISTS idx_taxonomy_cards_snapshot ON taxonomy_classification_cards(snapshot_id, ordinal);
                CREATE INDEX IF NOT EXISTS idx_taxonomy_runs_status ON taxonomy_runs(status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_taxonomy_stages_due ON taxonomy_stage_runs(status, next_retry_at);
                """
            )
            self._ensure_columns(connection)
            self._ensure_source_order(connection)
            connection.execute(
                "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    def _backup_before_migration(self) -> None:
        if not self.path.is_file():
            return
        try:
            source = sqlite3.connect(self.path)
            row = source.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
        except sqlite3.Error:
            if 'source' in locals():
                source.close()
            return
        version = int(row[0]) if row and str(row[0]).isdigit() else 0
        if version <= 0 or version >= SCHEMA_VERSION:
            source.close()
            return
        backup_version = 3 if version < 3 else SCHEMA_VERSION
        backup_path = self.path.with_name(f"{self.path.stem}.pre-v{backup_version}.backup.db")
        if backup_path.exists():
            source.close()
            return
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()

    @staticmethod
    def _ensure_columns(connection: sqlite3.Connection) -> None:
        additions = {
            "videos": {
                "processing_profile": "TEXT NOT NULL DEFAULT 'formal'",
                "active_revision": "TEXT NOT NULL DEFAULT 'refined'",
                "refinement_status": "TEXT NOT NULL DEFAULT 'not_required'",
                "display_favorite_time": "INTEGER",
                "duration_seconds": "INTEGER NOT NULL DEFAULT 0",
                "page_count": "INTEGER NOT NULL DEFAULT 1",
                "asr_provider": "TEXT",
                "asr_model": "TEXT",
                "reading_state": "TEXT NOT NULL DEFAULT 'unread'",
                "reading_state_updated_at": "TEXT",
                "is_marked": "INTEGER NOT NULL DEFAULT 0",
                "marked_at": "TEXT",
                "archived_at": "TEXT",
            },
            "pipeline_stages": {
                "profile": "TEXT NOT NULL DEFAULT 'formal'",
                "thinking_enabled": "INTEGER",
                "reasoning_effort": "TEXT",
                "decision": "TEXT",
                "change_reasons_json": "TEXT NOT NULL DEFAULT '[]'",
                "elapsed_seconds": "REAL",
            },
            "sync_runs": {
                "scope_source_id": "INTEGER",
                "current_phase": "TEXT",
                "current_video_id": "INTEGER",
                "history_pending_count": "INTEGER NOT NULL DEFAULT 0",
                "message": "TEXT",
                "heartbeat_at": "TEXT",
            },
            "favorite_sources": {
                "sort_order": "INTEGER NOT NULL DEFAULT 0",
            },
        }
        for table, columns in additions.items():
            existing = {
                str(row["name"])
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    @staticmethod
    def _ensure_source_order(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT id FROM favorite_sources ORDER BY sort_order, id"
        ).fetchall()
        for order, row in enumerate(rows):
            connection.execute(
                "UPDATE favorite_sources SET sort_order=? WHERE id=?",
                (order, int(row["id"])),
            )

    @staticmethod
    def _reset_library_state_for_reentry(
        connection: sqlite3.Connection,
        *,
        video_id: int,
        display_favorite_time: int,
        now: str,
    ) -> None:
        """Apply the approved re-entry rules in the membership transaction."""
        connection.execute(
            """
            UPDATE videos
            SET archived_at=NULL, reading_state='unread', reading_state_updated_at=?,
                is_ignored=0, ignored_at=NULL, removed_at=NULL,
                display_favorite_time=?, updated_at=?
            WHERE id=?
            """,
            (now, display_favorite_time, now, video_id),
        )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def has_baseline(self) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key='baseline_initialized'"
            ).fetchone()
        return bool(row and row["value"] == "1")

    def establish_baseline(self, source_ids: list[str], *, platform: str = "bilibili") -> None:
        now = utc_now()
        with self.connect() as connection:
            for source_id in source_ids:
                connection.execute(
                    """
                    INSERT INTO seen_items(platform, source_id, part, is_baseline, first_seen_at, last_seen_at)
                    VALUES(?, ?, 1, 1, ?, ?)
                    ON CONFLICT(platform, source_id, part) DO UPDATE SET
                        last_seen_at=excluded.last_seen_at,
                        removed_at=NULL
                    """,
                    (platform, source_id, now, now),
                )
            connection.execute(
                "INSERT INTO schema_meta(key, value) VALUES('baseline_initialized', '1') "
                "ON CONFLICT(key) DO UPDATE SET value='1'"
            )
            connection.execute(
                "INSERT INTO schema_meta(key, value) VALUES('baseline_created_at', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (now,),
            )

    def seen_source_ids(self, *, platform: str = "bilibili") -> set[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT source_id FROM seen_items WHERE platform=? AND part=1", (platform,)
            ).fetchall()
        return {str(row["source_id"]) for row in rows}

    def mark_seen(self, source_id: str, *, is_baseline: bool = False, platform: str = "bilibili") -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO seen_items(platform, source_id, part, is_baseline, first_seen_at, last_seen_at)
                VALUES(?, ?, 1, ?, ?, ?)
                ON CONFLICT(platform, source_id, part) DO UPDATE SET
                    last_seen_at=excluded.last_seen_at,
                    removed_at=NULL
                """,
                (platform, source_id, int(is_baseline), now, now),
            )

    def reconcile_current_items(self, current_ids: set[str], *, platform: str = "bilibili") -> None:
        now = utc_now()
        with self.connect() as connection:
            for source_id in current_ids:
                connection.execute(
                    "UPDATE seen_items SET last_seen_at=?, removed_at=NULL "
                    "WHERE platform=? AND source_id=? AND part=1",
                    (now, platform, source_id),
                )
                connection.execute(
                    "UPDATE videos SET removed_at=NULL, updated_at=? "
                    "WHERE platform=? AND source_id=? AND part=1",
                    (now, platform, source_id),
                )
            placeholders = ",".join("?" for _ in current_ids)
            if current_ids:
                params: list[Any] = [now, platform, *sorted(current_ids)]
                connection.execute(
                    f"UPDATE seen_items SET removed_at=COALESCE(removed_at, ?) "
                    f"WHERE platform=? AND part=1 AND source_id NOT IN ({placeholders})",
                    params,
                )
                connection.execute(
                    f"UPDATE videos SET removed_at=COALESCE(removed_at, ?), updated_at=? "
                    f"WHERE platform=? AND part=1 AND source_id NOT IN ({placeholders})",
                    [now, now, platform, *sorted(current_ids)],
                )
            else:
                connection.execute(
                    "UPDATE seen_items SET removed_at=COALESCE(removed_at, ?) WHERE platform=? AND part=1",
                    (now, platform),
                )
                connection.execute(
                    "UPDATE videos SET removed_at=COALESCE(removed_at, ?), updated_at=? "
                    "WHERE platform=? AND part=1",
                    (now, now, platform),
                )

    def create_favorite_source(
        self,
        *,
        folder_id: int,
        folder_title: str,
        account_id: int | None = None,
        account_name: str = "",
        original_url: str = "",
        media_count: int = 0,
        history_policy: str = "future_only",
        history_limit: int | None = None,
    ) -> int:
        now = utc_now()
        with self.connect() as connection:
            next_order = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM favorite_sources"
                ).fetchone()[0]
            )
            cursor = connection.execute(
                """
                INSERT INTO favorite_sources(
                    platform, original_url, account_id, account_name, folder_id,
                    folder_title, media_count, history_policy, history_limit,
                    sort_order, created_at, updated_at
                ) VALUES('bilibili', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, folder_id) DO UPDATE SET
                    original_url=CASE WHEN excluded.original_url='' THEN favorite_sources.original_url ELSE excluded.original_url END,
                    account_id=COALESCE(excluded.account_id, favorite_sources.account_id),
                    account_name=CASE WHEN excluded.account_name='' THEN favorite_sources.account_name ELSE excluded.account_name END,
                    folder_title=CASE WHEN excluded.folder_title='' THEN favorite_sources.folder_title ELSE excluded.folder_title END,
                    media_count=excluded.media_count,
                    updated_at=excluded.updated_at
                RETURNING id
                """,
                (
                    original_url,
                    account_id,
                    account_name,
                    folder_id,
                    folder_title,
                    media_count,
                    history_policy,
                    history_limit,
                    next_order,
                    now,
                    now,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("无法创建收藏夹来源")
        return int(row["id"])

    def get_source(self, source_db_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM favorite_sources WHERE id=?", (source_db_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_source_by_folder(self, folder_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM favorite_sources WHERE platform='bilibili' AND folder_id=?",
                (folder_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_sources(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        with self.connect() as connection:
            query = "SELECT * FROM favorite_sources"
            params: tuple[Any, ...] = ()
            if active_only:
                query += " WHERE status IN ('active', 'cooldown')"
            query += " ORDER BY sort_order, id"
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def set_source_status(self, source_db_id: int, status: str) -> None:
        if status not in {"active", "paused", "needs_auth", "unavailable", "cooldown"}:
            raise ValueError("Unsupported source status")
        with self.connect() as connection:
            connection.execute(
                "UPDATE favorite_sources SET status=?, updated_at=? WHERE id=?",
                (status, utc_now(), source_db_id),
            )

    def move_source(self, source_db_id: int, direction: str) -> bool:
        if direction not in {"up", "down"}:
            raise ValueError("Unsupported move direction")
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, sort_order FROM favorite_sources ORDER BY sort_order, id"
            ).fetchall()
            current_index = next(
                (index for index, row in enumerate(rows) if int(row["id"]) == source_db_id),
                None,
            )
            if current_index is None:
                raise KeyError(source_db_id)
            target_index = current_index + (-1 if direction == "up" else 1)
            if target_index < 0 or target_index >= len(rows):
                return False
            current = rows[current_index]
            target = rows[target_index]
            now = utc_now()
            connection.execute(
                "UPDATE favorite_sources SET sort_order=?, updated_at=? WHERE id=?",
                (int(target["sort_order"]), now, int(current["id"])),
            )
            connection.execute(
                "UPDATE favorite_sources SET sort_order=?, updated_at=? WHERE id=?",
                (int(current["sort_order"]), now, int(target["id"])),
            )
        return True

    def remove_source(self, source_db_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM favorite_sources WHERE id=?", (source_db_id,))

    def initialize_source_memberships(
        self, source_db_id: int, items: list[FavoriteItem]
    ) -> int:
        source = self.get_source(source_db_id)
        if source is None:
            raise KeyError(source_db_id)
        policy = str(source["history_policy"])
        limit = source.get("history_limit")
        requested = len(items) if policy == "all" else int(limit or 0) if policy == "latest_n" else 0
        selected = min(len(items), requested)
        now = utc_now()
        with self.connect() as connection:
            for position, item in enumerate(items):
                queued = position < selected
                existing_video = connection.execute(
                    "SELECT id, archived_at FROM videos WHERE platform='bilibili' AND source_id=? AND part=1",
                    (item.bvid,),
                ).fetchone()
                active_memberships = 0
                if existing_video:
                    active_memberships = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM video_source_memberships WHERE video_id=? AND removed_at IS NULL",
                            (int(existing_video["id"]),),
                        ).fetchone()[0]
                    )
                connection.execute(
                    """
                    INSERT INTO video_source_memberships(
                        source_id, bvid, video_id, title, uploader, favorite_time, source_position,
                        is_baseline, queued_history, first_observed_at, last_observed_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id, bvid) DO UPDATE SET
                        title=excluded.title,
                        uploader=excluded.uploader,
                        favorite_time=COALESCE(excluded.favorite_time, video_source_memberships.favorite_time),
                        source_position=excluded.source_position,
                        last_observed_at=excluded.last_observed_at,
                        removed_at=NULL
                    """,
                    (
                        source_db_id,
                        item.bvid,
                        existing_video["id"] if existing_video else None,
                        item.title,
                        item.uploader,
                        item.favorite_time,
                        position,
                        int(not queued),
                        int(queued),
                        now,
                        now,
                    ),
                )
                if existing_video and (existing_video["archived_at"] or active_memberships == 0):
                    self._reset_library_state_for_reentry(
                        connection,
                        video_id=int(existing_video["id"]),
                        display_favorite_time=item.favorite_time or _epoch_seconds(now),
                        now=now,
                    )
            connection.execute(
                """
                UPDATE favorite_sources
                SET baseline_initialized=1, media_count=?, last_sync_at=?, updated_at=?,
                    last_error_code=NULL, last_error_message=NULL
                WHERE id=?
                """,
                (len(items), now, now, source_db_id),
            )
        return selected

    def record_source_snapshot(
        self,
        source_db_id: int,
        items: list[FavoriteItem],
        *,
        processing_profile: str,
    ) -> list[int]:
        now = utc_now()
        current = {item.bvid for item in items}
        created: list[int] = []
        with self.connect() as connection:
            known = {
                str(row["bvid"]): dict(row)
                for row in connection.execute(
                    "SELECT * FROM video_source_memberships WHERE source_id=?",
                    (source_db_id,),
                ).fetchall()
            }
        for position, item in enumerate(items):
            prior = known.get(item.bvid)
            membership_is_new = prior is None
            membership_reactivated = bool(prior and prior.get("removed_at"))
            effective_time = item.favorite_time or _epoch_seconds(now)
            existing_video = self.get_video_by_source(item.bvid)
            video_id = int(prior["video_id"]) if prior and prior.get("video_id") else None
            if membership_is_new:
                video_id = self.create_video(
                    item.bvid,
                    item.title,
                    item.uploader,
                    processing_profile=processing_profile,
                    display_favorite_time=effective_time,
                )
                if existing_video is None:
                    created.append(video_id)
                existing_video = self.get_video(video_id)

            active_memberships_before = 0
            if video_id is not None:
                with self.connect() as connection:
                    row = connection.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM video_source_memberships
                        WHERE video_id=? AND removed_at IS NULL
                        """,
                        (video_id,),
                    ).fetchone()
                active_memberships_before = int(row["count"] if row else 0)

            observed_favorite_time = item.favorite_time
            if observed_favorite_time is None and (membership_is_new or membership_reactivated):
                observed_favorite_time = effective_time
            with self.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO video_source_memberships(
                        source_id, bvid, video_id, title, uploader, favorite_time,
                        source_position, is_baseline, queued_history,
                        first_observed_at, last_observed_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
                    ON CONFLICT(source_id, bvid) DO UPDATE SET
                        video_id=COALESCE(video_source_memberships.video_id, excluded.video_id),
                        title=excluded.title,
                        uploader=excluded.uploader,
                        favorite_time=COALESCE(excluded.favorite_time, video_source_memberships.favorite_time),
                        source_position=excluded.source_position,
                        last_observed_at=excluded.last_observed_at,
                        removed_at=NULL
                    """,
                    (
                        source_db_id,
                        item.bvid,
                        video_id,
                        item.title,
                        item.uploader,
                        observed_favorite_time,
                        position,
                        now,
                        now,
                    ),
                )
                if video_id is not None:
                    membership_activated = membership_is_new or membership_reactivated
                    should_reenter = membership_activated and bool(
                        (existing_video or {}).get("archived_at")
                        or active_memberships_before == 0
                    )
                    if should_reenter:
                        self._reset_library_state_for_reentry(
                            connection,
                            video_id=video_id,
                            display_favorite_time=effective_time,
                            now=now,
                        )
                    else:
                        connection.execute(
                            """
                            UPDATE videos
                            SET removed_at=NULL,
                                display_favorite_time=MAX(COALESCE(display_favorite_time, 0), ?),
                                updated_at=?
                            WHERE id=?
                            """,
                            (effective_time, now, video_id),
                        )
        with self.connect() as connection:
            if current:
                placeholders = ",".join("?" for _ in current)
                connection.execute(
                    f"UPDATE video_source_memberships SET removed_at=COALESCE(removed_at, ?) "
                    f"WHERE source_id=? AND bvid NOT IN ({placeholders})",
                    [now, source_db_id, *sorted(current)],
                )
            else:
                connection.execute(
                    "UPDATE video_source_memberships SET removed_at=COALESCE(removed_at, ?) WHERE source_id=?",
                    (now, source_db_id),
                )
            connection.execute(
                """
                UPDATE favorite_sources
                SET media_count=?, last_sync_at=?, status='active', cooldown_until=NULL,
                    last_error_code=NULL, last_error_message=NULL, updated_at=?
                WHERE id=?
                """,
                (len(items), now, now, source_db_id),
            )
            connection.execute(
                """
                UPDATE videos
                SET removed_at=CASE
                        WHEN EXISTS(
                            SELECT 1 FROM video_source_memberships active
                            WHERE active.video_id=videos.id AND active.removed_at IS NULL
                        ) THEN NULL
                        ELSE COALESCE(videos.removed_at, ?)
                    END,
                    updated_at=?
                WHERE id IN (
                    SELECT DISTINCT video_id
                    FROM video_source_memberships
                    WHERE source_id=? AND video_id IS NOT NULL
                )
                """,
                (now, now, source_db_id),
            )
        return created

    def list_history_backlog(self, *, limit: int = 8) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT m.*, s.folder_title, s.status AS source_status, s.cooldown_until
                FROM video_source_memberships m
                JOIN favorite_sources s ON s.id=m.source_id
                WHERE m.queued_history=1 AND m.removed_at IS NULL AND s.status='active'
                ORDER BY m.first_observed_at, m.source_id, m.source_position
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def materialize_history_membership(self, source_db_id: int, bvid: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM video_source_memberships WHERE source_id=? AND bvid=?",
                (source_db_id, bvid),
            ).fetchone()
        if row is None:
            raise KeyError((source_db_id, bvid))
        item = dict(row)
        effective_time = item.get("favorite_time") or _epoch_seconds(str(item["first_observed_at"]))
        video_id = self.create_video(
            bvid,
            str(item["title"]),
            str(item["uploader"]),
            processing_profile="formal",
            display_favorite_time=int(effective_time),
        )
        with self.connect() as connection:
            connection.execute(
                "UPDATE video_source_memberships SET video_id=?, queued_history=0, is_baseline=0 WHERE source_id=? AND bvid=?",
                (video_id, source_db_id, bvid),
            )
        return video_id

    def history_pending_count(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM video_source_memberships WHERE queued_history=1 AND removed_at IS NULL"
            ).fetchone()
        return int(row["count"] if row else 0)

    def video_sources(
        self, video_id: int, *, connection: sqlite3.Connection | None = None
    ) -> list[dict[str, Any]]:
        def query(active: sqlite3.Connection) -> list[dict[str, Any]]:
            rows = active.execute(
                """
                SELECT s.id, s.account_id, s.account_name, s.folder_id, s.folder_title,
                       m.favorite_time, m.removed_at
                FROM video_source_memberships m
                JOIN favorite_sources s ON s.id=m.source_id
                WHERE m.video_id=?
                ORDER BY COALESCE(m.favorite_time, 0) DESC, s.id
                """,
                (video_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        if connection is not None:
            return query(connection)
        with self.connect() as active:
            return query(active)

    def migrate_legacy_source(self, folder_id: int, folder_title: str) -> int:
        existing = self.get_source_by_folder(folder_id)
        if existing:
            return int(existing["id"])
        source_db_id = self.create_favorite_source(
            folder_id=folder_id,
            folder_title=folder_title or str(folder_id),
            history_policy="future_only",
        )
        now = utc_now()
        baseline_initialized = int(self.has_baseline())
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT source_id, is_baseline, first_seen_at, last_seen_at, removed_at FROM seen_items WHERE platform='bilibili' AND part=1"
            ).fetchall()
            for row in rows:
                video = connection.execute(
                    "SELECT id, title, uploader FROM videos WHERE platform='bilibili' AND source_id=? AND part=1",
                    (row["source_id"],),
                ).fetchone()
                connection.execute(
                    """
                    INSERT OR IGNORE INTO video_source_memberships(
                        source_id, bvid, video_id, title, uploader, is_baseline,
                        first_observed_at, last_observed_at, removed_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_db_id,
                        row["source_id"],
                        video["id"] if video else None,
                        video["title"] if video else "",
                        video["uploader"] if video else "",
                        row["is_baseline"],
                        row["first_seen_at"],
                        row["last_seen_at"],
                        row["removed_at"],
                    ),
                )
            connection.execute(
                "UPDATE favorite_sources SET baseline_initialized=?, updated_at=? WHERE id=?",
                (baseline_initialized, now, source_db_id),
            )
        return source_db_id

    def update_source_error(
        self,
        source_db_id: int,
        *,
        status: str,
        code: str,
        message: str,
        cooldown_until: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE favorite_sources
                SET status=?, last_error_code=?, last_error_message=?, cooldown_until=?, updated_at=?
                WHERE id=?
                """,
                (status, code, message, cooldown_until, utc_now(), source_db_id),
            )

    def create_video(
        self,
        source_id: str,
        title: str,
        uploader: str = "",
        *,
        processing_profile: str = "formal",
        display_favorite_time: int | None = None,
    ) -> int:
        now = utc_now()
        with self.connect() as connection:
            existed = connection.execute(
                "SELECT id FROM videos WHERE platform='bilibili' AND source_id=? AND part=1",
                (source_id,),
            ).fetchone()
            cursor = connection.execute(
                """
                INSERT INTO videos(
                    platform, source_id, part, title, uploader, video_url,
                    status, processing_profile, active_revision, refinement_status,
                    display_favorite_time, discovered_at, updated_at
                ) VALUES('bilibili', ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, source_id, part) DO UPDATE SET
                    title=excluded.title,
                    uploader=excluded.uploader,
                    removed_at=NULL,
                    display_favorite_time=COALESCE(excluded.display_favorite_time, videos.display_favorite_time),
                    updated_at=excluded.updated_at
                RETURNING id
                """,
                (
                    source_id,
                    title,
                    uploader,
                    f"https://www.bilibili.com/video/{source_id}",
                    VideoStatus.DISCOVERED.value,
                    processing_profile,
                    "fast" if processing_profile == "fast" else "refined",
                    "pending" if processing_profile == "fast" else "not_required",
                    display_favorite_time,
                    now,
                    now,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("无法创建视频记录")
            video_id = int(row["id"])
            if existed is None:
                connection.execute(
                    """
                    INSERT INTO events(event_type, video_id, payload_json, created_at)
                    VALUES('new_favorite', ?, ?, ?)
                    """,
                    (video_id, json.dumps({"source_id": source_id}, ensure_ascii=False), now),
                )
        return video_id

    def update_video(self, video_id: int, **fields: Any) -> None:
        if not fields:
            return
        allowed = {
            "title", "uploader", "description", "description_links_json", "video_url",
            "cover_url", "cover_path", "subtitle_language", "subtitle_source",
            "subtitle_upstream_type", "raw_subtitle_path", "transcript_path",
            "summary_path", "artifact_dir", "status", "error_code", "error_message",
            "subtitle_check_count", "subtitle_first_checked_at", "subtitle_next_check_at",
            "completed_at", "removed_at", "processing_profile", "active_revision",
            "refinement_status", "display_favorite_time",
            "duration_seconds", "page_count", "asr_provider", "asr_model",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unsupported video fields: {sorted(unknown)}")
        fields["updated_at"] = utc_now()
        assignments = ", ".join(f"{name}=?" for name in fields)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE videos SET {assignments} WHERE id=?",
                [*fields.values(), video_id],
            )

    def get_video(self, video_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        return dict(row) if row else None

    def get_video_by_source(self, source_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM videos WHERE platform='bilibili' AND source_id=? AND part=1",
                (source_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_videos(self, source_db_id: int | None = None) -> list[dict[str, Any]]:
        with self.connect() as connection:
            if source_db_id is None:
                rows = connection.execute(
                    "SELECT * FROM videos ORDER BY COALESCE(display_favorite_time, 0) DESC, discovered_at DESC, id DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT v.* FROM videos v
                    JOIN video_source_memberships m ON m.video_id=v.id
                    WHERE m.source_id=? AND m.removed_at IS NULL
                    ORDER BY COALESCE(m.favorite_time, v.display_favorite_time, 0) DESC,
                             m.source_position ASC, v.discovered_at DESC, v.id DESC
                    """,
                    (source_db_id,),
                ).fetchall()
            result = [dict(row) for row in rows]
            for item in result:
                item["sources"] = self.video_sources(int(item["id"]), connection=connection)
        return result

    def list_video_cards(
        self,
        *,
        view: str = "feed",
        source_db_id: int | None = None,
    ) -> list[dict[str, Any]]:
        conditions = {
            "feed": "v.archived_at IS NULL",
            "marked": "v.archived_at IS NULL AND v.is_marked=1",
            "noted": "v.archived_at IS NULL AND COALESCE(n.note_count, 0)>0",
            "archived": "v.archived_at IS NOT NULL",
        }
        if view not in conditions:
            raise ValueError("Unsupported library view")
        params: list[Any] = []
        source_clause = ""
        if source_db_id is not None:
            source_clause = " AND m.source_id=?"
            params.append(source_db_id)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                WITH note_counts AS (
                    SELECT video_id, COUNT(*) AS note_count
                    FROM video_notes
                    GROUP BY video_id
                )
                SELECT v.*,
                       m.source_id AS card_source_id,
                       m.favorite_time AS card_favorite_time,
                       m.source_position AS card_source_position,
                       m.first_observed_at AS card_first_observed_at,
                       s.account_id AS card_account_id,
                       s.account_name AS card_account_name,
                       s.folder_id AS card_folder_id,
                       s.folder_title AS card_folder_title,
                       COALESCE(n.note_count, 0) AS note_count
                FROM video_source_memberships m
                JOIN videos v ON v.id=m.video_id
                JOIN favorite_sources s ON s.id=m.source_id
                LEFT JOIN note_counts n ON n.video_id=v.id
                WHERE m.removed_at IS NULL
                  AND m.video_id IS NOT NULL
                  AND {conditions[view]}
                  {source_clause}
                ORDER BY COALESCE(
                           m.favorite_time,
                           v.display_favorite_time,
                           CAST(strftime('%s', m.first_observed_at) AS INTEGER),
                           0
                         ) DESC,
                         m.source_position ASC,
                         v.discovered_at DESC,
                         v.id DESC,
                         m.source_id ASC
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def set_reading_state(self, video_id: int, state: str) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE videos
                SET reading_state=?, reading_state_updated_at=?, updated_at=?
                WHERE id=?
                """,
                (state, now, now, video_id),
            )

    def set_marked(self, video_id: int, marked: bool) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "UPDATE videos SET is_marked=?, marked_at=?, updated_at=? WHERE id=?",
                (int(marked), now if marked else None, now, video_id),
            )

    def set_archived(self, video_id: int, archived: bool) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "UPDATE videos SET archived_at=?, updated_at=? WHERE id=?",
                (now if archived else None, now, video_id),
            )

    def create_note(self, video_id: int, content: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO video_notes(video_id, content, created_at, updated_at)
                VALUES(?, ?, ?, ?)
                """,
                (video_id, content, now, now),
            )
            note_id = int(cursor.lastrowid)
            row = connection.execute(
                "SELECT * FROM video_notes WHERE id=?", (note_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("无法创建笔记")
        return dict(row)

    def get_note(self, note_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM video_notes WHERE id=?", (note_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_note(self, note_id: int, content: str) -> dict[str, Any] | None:
        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE video_notes SET content=?, updated_at=? WHERE id=?",
                (content, now, note_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM video_notes WHERE id=?", (note_id,)
            ).fetchone()
        return dict(row) if row else None

    def delete_note(self, note_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM video_notes WHERE id=?", (note_id,))

    def list_notes(self, video_id: int) -> list[dict[str, Any]]:
        return self.list_notes_for_videos([video_id]).get(video_id, [])

    def list_notes_for_videos(self, video_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        unique_ids = sorted(set(video_ids))
        result = {video_id: [] for video_id in unique_ids}
        if not unique_ids:
            return result
        placeholders = ",".join("?" for _ in unique_ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM video_notes
                WHERE video_id IN ({placeholders})
                ORDER BY created_at ASC, id ASC
                """,
                unique_ids,
            ).fetchall()
        for row in rows:
            item = dict(row)
            result[int(item["video_id"])].append(item)
        return result

    def list_processable_videos(self, now: str | None = None) -> list[dict[str, Any]]:
        moment = now or utc_now()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM videos
                WHERE status IN ('discovered', 'subtitle_pending', 'transcript_processing',
                                 'summary_processing', 'retry_wait')
                  AND (subtitle_next_check_at IS NULL OR subtitle_next_check_at <= ?)
                ORDER BY discovered_at, id
                """,
                (moment,),
            ).fetchall()
        return [dict(row) for row in rows]

    def ensure_asr_job(
        self,
        video_id: int,
        *,
        provider: str,
        model: str,
        trigger_mode: str,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO asr_jobs(
                    video_id, provider, model, trigger_mode, status, created_at, updated_at
                ) VALUES(?, ?, ?, ?, 'pending', ?, ?)
                ON CONFLICT(video_id) DO NOTHING
                """,
                (video_id, provider, model, trigger_mode, now, now),
            )
            row = connection.execute(
                "SELECT * FROM asr_jobs WHERE video_id=?", (video_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("无法创建语音识别任务")
        return dict(row)

    def get_asr_job(self, video_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM asr_jobs WHERE video_id=?", (video_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_asr_job(self, video_id: int, **fields: Any) -> None:
        allowed = {
            "provider", "model", "trigger_mode", "status", "task_id",
            "remote_file_url", "result_url", "audio_path", "attempt_count",
            "next_retry_at", "last_error_code", "last_error_message",
            "submitted_at", "completed_at",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unsupported ASR job fields: {sorted(unknown)}")
        fields["updated_at"] = utc_now()
        assignments = ", ".join(f"{name}=?" for name in fields)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE asr_jobs SET {assignments} WHERE video_id=?",
                [*fields.values(), video_id],
            )

    def ensure_stage(self, video_id: int, stage: StageName) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO pipeline_stages(video_id, stage_name, status, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(video_id, stage_name) DO NOTHING
                """,
                (video_id, stage.value, StageStatus.PENDING.value, now),
            )
            row = connection.execute(
                "SELECT * FROM pipeline_stages WHERE video_id=? AND stage_name=?",
                (video_id, stage.value),
            ).fetchone()
        if row is None:
            raise RuntimeError("无法创建处理阶段")
        return dict(row)

    def update_stage(self, video_id: int, stage: StageName, **fields: Any) -> None:
        allowed = {
            "status", "attempt_count", "next_retry_at", "last_error_code",
            "last_error_message", "provider", "model", "prompt_version",
            "started_at", "completed_at", "profile", "thinking_enabled",
            "reasoning_effort", "decision", "change_reasons_json", "elapsed_seconds",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unsupported stage fields: {sorted(unknown)}")
        fields["updated_at"] = utc_now()
        assignments = ", ".join(f"{name}=?" for name in fields)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE pipeline_stages SET {assignments} WHERE video_id=? AND stage_name=?",
                [*fields.values(), video_id, stage.value],
            )

    def get_stage(self, video_id: int, stage: StageName) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM pipeline_stages WHERE video_id=? AND stage_name=?",
                (video_id, stage.value),
            ).fetchone()
        return dict(row) if row else None

    def reset_failed_stages(self, video_id: int) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE pipeline_stages
                SET status='pending', attempt_count=0, next_retry_at=NULL,
                    last_error_code=NULL, updated_at=?
                WHERE video_id=? AND status IN ('retry_wait', 'needs_review')
                """,
                (now, video_id),
            )
            connection.execute(
                """
                UPDATE videos
                SET status=CASE
                    WHEN transcript_path IS NOT NULL THEN 'summary_processing'
                    WHEN raw_subtitle_path IS NOT NULL THEN 'transcript_processing'
                    ELSE 'discovered'
                END,
                error_code=NULL, error_message=NULL, subtitle_next_check_at=NULL, updated_at=?
                WHERE id=?
                """,
                (now, video_id),
            )

    def set_ignored(self, video_id: int, ignored: bool) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "UPDATE videos SET is_ignored=?, ignored_at=?, updated_at=? WHERE id=?",
                (int(ignored), now if ignored else None, now, video_id),
            )

    def add_event(self, event_type: str, video_id: int | None, payload: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO events(event_type, video_id, payload_json, created_at) VALUES(?, ?, ?, ?)",
                (event_type, video_id, json.dumps(payload, ensure_ascii=False), utc_now()),
            )

    def start_sync_run(self, mode: str, *, scope_source_id: int | None = None) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO sync_runs(mode, status, scope_source_id, started_at, heartbeat_at, current_phase)
                VALUES(?, 'running', ?, ?, ?, 'starting')
                """,
                (mode, scope_source_id, utc_now(), utc_now()),
            )
            return int(cursor.lastrowid)

    def finish_sync_run(self, run_id: int, *, status: str, **counts: Any) -> None:
        allowed = {
            "current_count", "discovered_count", "processed_count", "failed_count",
            "history_pending_count", "error_summary", "message", "current_phase", "current_video_id",
        }
        fields = {name: value for name, value in counts.items() if name in allowed}
        fields.update({"status": status, "finished_at": utc_now()})
        assignments = ", ".join(f"{name}=?" for name in fields)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE sync_runs SET {assignments} WHERE id=?", [*fields.values(), run_id]
            )

    def latest_sync_run(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def get_sync_run(self, run_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM sync_runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def active_sync_run(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sync_runs WHERE status='running' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def update_sync_run(self, run_id: int, **fields: Any) -> None:
        allowed = {
            "current_count", "discovered_count", "processed_count", "failed_count",
            "history_pending_count", "current_phase", "current_video_id", "message",
            "error_summary",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unsupported sync run fields: {sorted(unknown)}")
        fields["heartbeat_at"] = utc_now()
        assignments = ", ".join(f"{name}=?" for name in fields)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE sync_runs SET {assignments} WHERE id=?", [*fields.values(), run_id]
            )

    def recover_stale_sync_runs(self) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE sync_runs
                SET status='interrupted', finished_at=?, error_summary='应用进程中断，等待下次同步恢复'
                WHERE status='running'
                """,
                (now,),
            )


def _epoch_seconds(value: str) -> int:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())
