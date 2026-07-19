from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import time
from typing import Any

from pydantic import ValidationError

from shiliu.artifacts import ArtifactStore
from shiliu.db import Database
from shiliu.domain import SubtitleSegment
from shiliu.retrieval.chunking import build_raw_subtitle_chunks
from shiliu.retrieval.models import (
    FolderContext,
    RetrievalFilters,
    SearchLevel,
    SearchResult,
    SearchUnit,
)


INDEX_NAME = "shiliu_lexical"
INDEX_VERSION = "v3-stage1-lexical-v1"
FTS_TOKENIZER = "trigram"
SHORT_QUERY_MIN_CHARACTERS = 3


@dataclass
class RebuildStats:
    eligible_video_count: int = 0
    video_unit_count: int = 0
    chunk_unit_count: int = 0
    subtitle_source_distribution: dict[str, int] = field(default_factory=dict)
    missing_raw_subtitle_json: int = 0
    malformed_raw_subtitle_json: int = 0
    malformed_summary_json: int = 0
    malformed_transcript_json: int = 0
    index_version: str = INDEX_VERSION
    fts_tokenizer: str = FTS_TOKENIZER
    duration_seconds: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "eligible_video_count": self.eligible_video_count,
            "video_unit_count": self.video_unit_count,
            "chunk_unit_count": self.chunk_unit_count,
            "total_unit_count": self.video_unit_count + self.chunk_unit_count,
            "subtitle_source_distribution": dict(
                sorted(self.subtitle_source_distribution.items())
            ),
            "missing_raw_subtitle_json": self.missing_raw_subtitle_json,
            "malformed_raw_subtitle_json": self.malformed_raw_subtitle_json,
            "malformed_summary_json": self.malformed_summary_json,
            "malformed_transcript_json": self.malformed_transcript_json,
            "index_version": self.index_version,
            "fts_tokenizer": self.fts_tokenizer,
            "duration_seconds": round(self.duration_seconds, 6),
        }


class RetrievalService:
    """Build and query the local FTS5 lexical index.

    FTS5 trigram supports Chinese and mixed-language substring matching without
    an external service.  Queries with fewer than three characters cannot be
    represented by trigram tokens; those queries use a documented, unranked
    SQLite substring fallback (`lexical_substring_fallback`).  Normal queries
    use FTS5 BM25 and expose its negated value, so a higher lexical_score ranks
    ahead of a lower value.
    """

    def __init__(self, *, db: Database, artifacts: ArtifactStore) -> None:
        self.db = db
        self.artifacts = artifacts

    def initialize_schema(self) -> None:
        with self.db.connect() as connection:
            connection.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS retrieval_units (
                    unit_id TEXT PRIMARY KEY,
                    unit_type TEXT NOT NULL CHECK(unit_type IN ('video', 'transcript_chunk')),
                    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
                    platform TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    part INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    uploader TEXT NOT NULL,
                    chunk_id TEXT,
                    source_type TEXT NOT NULL,
                    start_time REAL,
                    end_time REAL,
                    source_text TEXT NOT NULL,
                    search_text TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    index_version TEXT NOT NULL,
                    reading_state TEXT NOT NULL,
                    is_marked INTEGER NOT NULL,
                    is_ignored INTEGER NOT NULL,
                    archived_at TEXT,
                    removed_at TEXT,
                    CHECK(
                        (unit_type='video' AND chunk_id IS NULL AND start_time IS NULL AND end_time IS NULL)
                        OR
                        (unit_type='transcript_chunk' AND chunk_id IS NOT NULL AND start_time IS NOT NULL AND end_time IS NOT NULL)
                    ),
                    UNIQUE(video_id, chunk_id)
                );

                CREATE INDEX IF NOT EXISTS idx_retrieval_units_video
                    ON retrieval_units(video_id, unit_type);
                CREATE INDEX IF NOT EXISTS idx_retrieval_units_visibility
                    ON retrieval_units(unit_type, is_ignored, archived_at);

                CREATE TABLE IF NOT EXISTS retrieval_unit_folders (
                    unit_id TEXT NOT NULL REFERENCES retrieval_units(unit_id) ON DELETE CASCADE,
                    source_db_id INTEGER NOT NULL REFERENCES favorite_sources(id) ON DELETE CASCADE,
                    folder_id INTEGER NOT NULL,
                    folder_title TEXT NOT NULL,
                    favorite_time INTEGER,
                    PRIMARY KEY(unit_id, source_db_id)
                );

                CREATE INDEX IF NOT EXISTS idx_retrieval_folders_filter
                    ON retrieval_unit_folders(source_db_id, folder_id, favorite_time, unit_id);

                CREATE TABLE IF NOT EXISTS retrieval_index_meta (
                    index_name TEXT PRIMARY KEY,
                    index_version TEXT NOT NULL,
                    tokenizer TEXT NOT NULL,
                    rebuilt_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    eligible_video_count INTEGER NOT NULL,
                    video_unit_count INTEGER NOT NULL,
                    chunk_unit_count INTEGER NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS retrieval_units_fts USING fts5(
                    unit_id UNINDEXED,
                    search_text,
                    tokenize='{FTS_TOKENIZER}'
                );
                """
            )
            meta_columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(retrieval_index_meta)"
                ).fetchall()
            }
            if "updated_at" not in meta_columns:
                connection.execute(
                    "ALTER TABLE retrieval_index_meta ADD COLUMN updated_at TEXT"
                )
                connection.execute(
                    "UPDATE retrieval_index_meta SET updated_at=rebuilt_at WHERE updated_at IS NULL"
                )

    def rebuild(self) -> RebuildStats:
        self.initialize_schema()
        started = time.monotonic()
        stats = RebuildStats()
        videos = self._eligible_videos()
        stats.eligible_video_count = len(videos)
        units: list[SearchUnit] = []
        for video in videos:
            built = self._build_video_units(video, stats)
            units.extend(built)
            stats.video_unit_count += sum(unit.unit_type == "video" for unit in built)
            stats.chunk_unit_count += sum(
                unit.unit_type == "transcript_chunk" for unit in built
            )

        with self.db.connect() as connection:
            connection.execute("DELETE FROM retrieval_units_fts")
            connection.execute("DELETE FROM retrieval_unit_folders")
            connection.execute("DELETE FROM retrieval_units")
            self._insert_units(connection, units)
            completed_at = _utc_now()
            connection.execute(
                """
                INSERT INTO retrieval_index_meta(
                    index_name, index_version, tokenizer, rebuilt_at, updated_at,
                    eligible_video_count, video_unit_count, chunk_unit_count
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(index_name) DO UPDATE SET
                    index_version=excluded.index_version,
                    tokenizer=excluded.tokenizer,
                    rebuilt_at=excluded.rebuilt_at,
                    updated_at=excluded.updated_at,
                    eligible_video_count=excluded.eligible_video_count,
                    video_unit_count=excluded.video_unit_count,
                    chunk_unit_count=excluded.chunk_unit_count
                """,
                (
                    INDEX_NAME,
                    INDEX_VERSION,
                    FTS_TOKENIZER,
                    completed_at,
                    completed_at,
                    stats.eligible_video_count,
                    stats.video_unit_count,
                    stats.chunk_unit_count,
                ),
            )
        stats.duration_seconds = time.monotonic() - started
        return stats

    def replace_video(self, video_id: int) -> dict[str, int]:
        self.initialize_schema()
        video = self._eligible_video(video_id)
        stats = RebuildStats(eligible_video_count=int(video is not None))
        units = self._build_video_units(video, stats) if video is not None else []
        with self.db.connect() as connection:
            desired_ids = {unit.unit_id for unit in units}
            connection.execute(
                "DELETE FROM retrieval_units_fts WHERE unit_id IN "
                "(SELECT unit_id FROM retrieval_units WHERE video_id=?)",
                (video_id,),
            )
            connection.execute(
                "DELETE FROM retrieval_unit_folders WHERE unit_id IN "
                "(SELECT unit_id FROM retrieval_units WHERE video_id=?)",
                (video_id,),
            )
            existing_ids = {
                str(row[0])
                for row in connection.execute(
                    "SELECT unit_id FROM retrieval_units WHERE video_id=?", (video_id,)
                )
            }
            stale_ids = existing_ids - desired_ids
            if stale_ids:
                connection.executemany(
                    "DELETE FROM retrieval_units WHERE unit_id=?",
                    [(unit_id,) for unit_id in sorted(stale_ids)],
                )
            self._upsert_units(connection, units)
            self._refresh_index_meta_counts(connection)
        return {
            "video_id": video_id,
            "video_units": sum(unit.unit_type == "video" for unit in units),
            "chunk_units": sum(unit.unit_type == "transcript_chunk" for unit in units),
        }

    def delete_video(self, video_id: int) -> int:
        self.initialize_schema()
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM retrieval_units WHERE video_id=?", (video_id,)
            ).fetchone()
            count = int(row[0] if row else 0)
            self._delete_video_units(connection, video_id)
            self._refresh_index_meta_counts(connection)
        return count

    def statistics(self) -> dict[str, object]:
        self.initialize_schema()
        with self.db.connect() as connection:
            meta = connection.execute(
                "SELECT * FROM retrieval_index_meta WHERE index_name=?", (INDEX_NAME,)
            ).fetchone()
            counts = connection.execute(
                """
                SELECT COUNT(*) AS metadata_count,
                       COUNT(DISTINCT unit_id) AS distinct_unit_count,
                       SUM(unit_type='video') AS video_unit_count,
                       SUM(unit_type='transcript_chunk') AS chunk_unit_count
                FROM retrieval_units
                """
            ).fetchone()
            fts_count = int(connection.execute(
                "SELECT COUNT(*) FROM retrieval_units_fts"
            ).fetchone()[0])
            duplicate_count = int(connection.execute(
                "SELECT COUNT(*) - COUNT(DISTINCT unit_id) FROM retrieval_units"
            ).fetchone()[0])
            distribution = {
                str(row["source_type"]): int(row["count"])
                for row in connection.execute(
                    """
                    SELECT source_type, COUNT(*) AS count
                    FROM retrieval_units
                    WHERE unit_type='transcript_chunk'
                    GROUP BY source_type ORDER BY source_type
                    """
                )
            }
        current = {
            "metadata_count": int(counts["metadata_count"] or 0),
            "distinct_unit_count": int(counts["distinct_unit_count"] or 0),
            "video_unit_count": int(counts["video_unit_count"] or 0),
            "chunk_unit_count": int(counts["chunk_unit_count"] or 0),
            "fts_count": fts_count,
            "duplicate_count": duplicate_count,
            "subtitle_source_distribution": distribution,
            "consistent": int(counts["metadata_count"] or 0) == fts_count,
        }
        index = None
        last_full_rebuild = None
        if meta is not None:
            index = {
                "index_name": str(meta["index_name"]),
                "index_version": str(meta["index_version"]),
                "tokenizer": str(meta["tokenizer"]),
                "metadata_semantics": "current_index_state",
                "updated_at": str(meta["updated_at"]),
                "eligible_video_count": int(meta["eligible_video_count"]),
                "video_unit_count": int(meta["video_unit_count"]),
                "chunk_unit_count": int(meta["chunk_unit_count"]),
                "total_unit_count": (
                    int(meta["video_unit_count"]) + int(meta["chunk_unit_count"])
                ),
            }
            last_full_rebuild = {"completed_at": str(meta["rebuilt_at"])}
        return {
            "index": index,
            "current": current,
            "last_full_rebuild": last_full_rebuild,
        }

    def search(
        self,
        query: str,
        *,
        level: SearchLevel = "all",
        top_k: int = 10,
        filters: RetrievalFilters | None = None,
        include_ignored: bool = False,
    ) -> list[SearchResult]:
        self.initialize_schema()
        normalized = " ".join(query.split())
        if not normalized:
            raise ValueError("query must not be empty")
        if level not in {"video", "transcript_chunk", "all"}:
            raise ValueError("unsupported search level")
        if not 1 <= top_k <= 500:
            raise ValueError("top_k must be between 1 and 500")
        resolved_filters = filters or RetrievalFilters()
        where, parameters = self._search_filters(
            level=level,
            filters=resolved_filters,
            include_ignored=include_ignored,
        )

        use_fallback = len(normalized) < SHORT_QUERY_MIN_CHARACTERS
        if use_fallback:
            sql = f"""
                SELECT u.*, 0.0 AS lexical_score
                FROM retrieval_units u
                WHERE instr(lower(u.search_text), lower(?)) > 0
                  AND {where}
                ORDER BY u.unit_type, u.video_id, u.start_time
                LIMIT ?
            """
            query_parameters: list[Any] = [normalized, *parameters, top_k]
            method = "lexical_substring_fallback"
        else:
            sql = f"""
                SELECT u.*, -bm25(retrieval_units_fts) AS lexical_score
                FROM retrieval_units_fts
                JOIN retrieval_units u ON u.unit_id=retrieval_units_fts.unit_id
                WHERE retrieval_units_fts MATCH ?
                  AND {where}
                ORDER BY lexical_score DESC, u.unit_id
                LIMIT ?
            """
            query_parameters = [_fts_phrase(normalized), *parameters, top_k]
            method = "lexical"

        with self.db.connect() as connection:
            rows = connection.execute(sql, query_parameters).fetchall()
            return [
                self._result_from_row(
                    connection,
                    row,
                    query=normalized,
                    retrieval_method=method,
                )
                for row in rows
            ]

    def _eligible_videos(self) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT v.* FROM videos v
                WHERE v.removed_at IS NULL
                  AND EXISTS(
                      SELECT 1 FROM video_source_memberships m
                      WHERE m.video_id=v.id AND m.removed_at IS NULL
                  )
                ORDER BY v.id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def _eligible_video(self, video_id: int) -> dict[str, Any] | None:
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT v.* FROM videos v
                WHERE v.id=? AND v.removed_at IS NULL
                  AND EXISTS(
                      SELECT 1 FROM video_source_memberships m
                      WHERE m.video_id=v.id AND m.removed_at IS NULL
                  )
                """,
                (video_id,),
            ).fetchone()
        return dict(row) if row else None

    def _build_video_units(
        self, video: dict[str, Any], stats: RebuildStats
    ) -> list[SearchUnit]:
        folders = self._active_folders(int(video["id"]))
        sections = [
            ("Title", str(video.get("title") or "")),
            ("Uploader", str(video.get("uploader") or "")),
            ("Description", str(video.get("description") or "")),
        ]
        sections.extend(self._summary_sections(video, stats))
        sections.extend(self._transcript_sections(video, stats))
        notes = self.db.list_notes(int(video["id"]))
        if notes:
            sections.append(
                ("User Notes", "\n".join(str(note["content"]) for note in notes))
            )
        if folders:
            sections.append(
                ("Favorite Folders", "\n".join(folder.folder_title for folder in folders))
            )
        source_text = "\n\n".join(
            f"[{label}]\n{value.strip()}"
            for label, value in sections
            if value.strip()
        )
        platform = str(video["platform"])
        source_id = str(video["source_id"])
        part = int(video["part"])
        video_unit = SearchUnit(
            unit_id=f"video:{platform}:{source_id}:p{part}",
            unit_type="video",
            video_id=int(video["id"]),
            platform=platform,
            source_id=source_id,
            part=part,
            title=str(video["title"]),
            uploader=str(video.get("uploader") or ""),
            chunk_id=None,
            source_type="video_composite",
            start_time=None,
            end_time=None,
            source_text=source_text,
            search_text=source_text,
            content_hash=_hash_text(source_text),
            index_version=INDEX_VERSION,
            reading_state=str(video.get("reading_state") or "unread"),
            is_marked=bool(video.get("is_marked")),
            is_ignored=bool(video.get("is_ignored")),
            archived_at=str(video["archived_at"]) if video.get("archived_at") else None,
            removed_at=str(video["removed_at"]) if video.get("removed_at") else None,
            folders=folders,
        )
        units = [video_unit]
        units.extend(self._chunk_units(video, folders, stats))
        return units

    def _chunk_units(
        self,
        video: dict[str, Any],
        folders: tuple[FolderContext, ...],
        stats: RebuildStats,
    ) -> list[SearchUnit]:
        raw_path = video.get("raw_subtitle_path")
        if not raw_path:
            return []
        json_path = Path(str(raw_path)).with_name("subtitle-raw.json")
        if not json_path.is_file():
            stats.missing_raw_subtitle_json += 1
            return []
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError("raw subtitle JSON is not an array")
            segments = [SubtitleSegment.model_validate(item) for item in payload]
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError):
            stats.malformed_raw_subtitle_json += 1
            return []
        source_type = str(video.get("subtitle_source") or "unknown")
        chunks = build_raw_subtitle_chunks(
            platform=str(video["platform"]),
            source_id=str(video["source_id"]),
            part=int(video["part"]),
            source_type=source_type,
            segments=segments,
        )
        if chunks:
            stats.subtitle_source_distribution[source_type] = (
                stats.subtitle_source_distribution.get(source_type, 0) + len(chunks)
            )
        return [
            SearchUnit(
                unit_id=(
                    f"transcript_chunk:{video['platform']}:{video['source_id']}:"
                    f"p{video['part']}:{chunk.chunk_id}"
                ),
                unit_type="transcript_chunk",
                video_id=int(video["id"]),
                platform=str(video["platform"]),
                source_id=str(video["source_id"]),
                part=int(video["part"]),
                title=str(video["title"]),
                uploader=str(video.get("uploader") or ""),
                chunk_id=chunk.chunk_id,
                source_type=source_type,
                start_time=chunk.start_time,
                end_time=chunk.end_time,
                source_text=chunk.text,
                search_text=chunk.text,
                content_hash=chunk.content_hash,
                index_version=INDEX_VERSION,
                reading_state=str(video.get("reading_state") or "unread"),
                is_marked=bool(video.get("is_marked")),
                is_ignored=bool(video.get("is_ignored")),
                archived_at=str(video["archived_at"]) if video.get("archived_at") else None,
                removed_at=str(video["removed_at"]) if video.get("removed_at") else None,
                folders=folders,
            )
            for chunk in chunks
        ]

    def _summary_sections(
        self, video: dict[str, Any], stats: RebuildStats
    ) -> list[tuple[str, str]]:
        if not video.get("summary_path"):
            return []
        path = self._revision_json_path(video, "summary")
        if path is None:
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("summary is not an object")
            values: list[tuple[str, str]] = []
            values.append(("Summary Conclusion", str(payload.get("conclusion") or "")))
            values.append(("Summary Key Points", _strings(payload.get("key_points"))))
            values.append(("Summary Detailed Notes", _strings(payload.get("detailed_notes"))))
            values.append(("Summary Entities", _object_strings(payload.get("entities"))))
            values.append(("Summary Chapters (video-level only)", _object_strings(payload.get("important_chapters"))))
            return [(label, value) for label, value in values if value]
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            stats.malformed_summary_json += 1
            return []

    def _transcript_sections(
        self, video: dict[str, Any], stats: RebuildStats
    ) -> list[tuple[str, str]]:
        if not video.get("transcript_path"):
            return []
        path = self._revision_json_path(video, "transcript")
        if path is None:
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("transcript is not an object")
            values: list[str] = []
            for section in payload.get("sections") or []:
                if not isinstance(section, dict):
                    continue
                title = str(section.get("title") or "").strip()
                paragraphs = _strings(section.get("paragraphs"))
                text = "\n".join(value for value in (title, paragraphs) if value)
                if text:
                    values.append(text)
            return [("Cleaned Transcript (video-level only)", "\n\n".join(values))] if values else []
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            stats.malformed_transcript_json += 1
            return []

    def _revision_json_path(
        self, video: dict[str, Any], kind: str
    ) -> Path | None:
        directory = self.artifacts.videos_dir / str(video["source_id"])
        revision = str(video.get("active_revision") or "refined")
        candidates = [directory / f"{kind}.{revision}.json", directory / f"{kind}.json"]
        return next((candidate for candidate in candidates if candidate.is_file()), None)

    def _active_folders(self, video_id: int) -> tuple[FolderContext, ...]:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT s.id AS source_db_id, s.folder_id, s.folder_title, m.favorite_time
                FROM video_source_memberships m
                JOIN favorite_sources s ON s.id=m.source_id
                WHERE m.video_id=? AND m.removed_at IS NULL
                ORDER BY s.sort_order, s.id
                """,
                (video_id,),
            ).fetchall()
        return tuple(
            FolderContext(
                source_db_id=int(row["source_db_id"]),
                folder_id=int(row["folder_id"]),
                folder_title=str(row["folder_title"]),
                favorite_time=(
                    int(row["favorite_time"])
                    if row["favorite_time"] is not None
                    else None
                ),
            )
            for row in rows
        )

    @staticmethod
    def _insert_units(connection: sqlite3.Connection, units: list[SearchUnit]) -> None:
        connection.executemany(
            """
            INSERT INTO retrieval_units(
                unit_id, unit_type, video_id, platform, source_id, part,
                title, uploader, chunk_id, source_type, start_time, end_time,
                source_text, search_text, content_hash, index_version,
                reading_state, is_marked, is_ignored, archived_at, removed_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    unit.unit_id,
                    unit.unit_type,
                    unit.video_id,
                    unit.platform,
                    unit.source_id,
                    unit.part,
                    unit.title,
                    unit.uploader,
                    unit.chunk_id,
                    unit.source_type,
                    unit.start_time,
                    unit.end_time,
                    unit.source_text,
                    unit.search_text,
                    unit.content_hash,
                    unit.index_version,
                    unit.reading_state,
                    int(unit.is_marked),
                    int(unit.is_ignored),
                    unit.archived_at,
                    unit.removed_at,
                )
                for unit in units
            ],
        )
        connection.executemany(
            "INSERT INTO retrieval_units_fts(unit_id, search_text) VALUES(?, ?)",
            [(unit.unit_id, unit.search_text) for unit in units],
        )
        connection.executemany(
            """
            INSERT INTO retrieval_unit_folders(
                unit_id, source_db_id, folder_id, folder_title, favorite_time
            ) VALUES(?, ?, ?, ?, ?)
            """,
            [
                (unit.unit_id, folder.source_db_id, folder.folder_id,
                 folder.folder_title, folder.favorite_time)
                for unit in units for folder in unit.folders
            ],
        )

    @staticmethod
    def _upsert_units(connection: sqlite3.Connection, units: list[SearchUnit]) -> None:
        values = [
            (
                unit.unit_id, unit.unit_type, unit.video_id, unit.platform,
                unit.source_id, unit.part, unit.title, unit.uploader, unit.chunk_id,
                unit.source_type, unit.start_time, unit.end_time, unit.source_text,
                unit.search_text, unit.content_hash, unit.index_version,
                unit.reading_state, int(unit.is_marked), int(unit.is_ignored),
                unit.archived_at, unit.removed_at,
            )
            for unit in units
        ]
        connection.executemany(
            """
            INSERT INTO retrieval_units(
                unit_id, unit_type, video_id, platform, source_id, part,
                title, uploader, chunk_id, source_type, start_time, end_time,
                source_text, search_text, content_hash, index_version,
                reading_state, is_marked, is_ignored, archived_at, removed_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(unit_id) DO UPDATE SET
                unit_type=excluded.unit_type, video_id=excluded.video_id,
                platform=excluded.platform, source_id=excluded.source_id,
                part=excluded.part, title=excluded.title, uploader=excluded.uploader,
                chunk_id=excluded.chunk_id, source_type=excluded.source_type,
                start_time=excluded.start_time, end_time=excluded.end_time,
                source_text=excluded.source_text, search_text=excluded.search_text,
                content_hash=excluded.content_hash, index_version=excluded.index_version,
                reading_state=excluded.reading_state, is_marked=excluded.is_marked,
                is_ignored=excluded.is_ignored, archived_at=excluded.archived_at,
                removed_at=excluded.removed_at
            """,
            values,
        )
        connection.executemany(
            "INSERT INTO retrieval_units_fts(unit_id, search_text) VALUES(?, ?)",
            [(unit.unit_id, unit.search_text) for unit in units],
        )
        connection.executemany(
            """
            INSERT INTO retrieval_unit_folders(
                unit_id, source_db_id, folder_id, folder_title, favorite_time
            ) VALUES(?, ?, ?, ?, ?)
            """,
            [
                (unit.unit_id, folder.source_db_id, folder.folder_id,
                 folder.folder_title, folder.favorite_time)
                for unit in units for folder in unit.folders
            ],
        )

    @staticmethod
    def _delete_video_units(connection: sqlite3.Connection, video_id: int) -> None:
        connection.execute(
            """
            DELETE FROM retrieval_units_fts
            WHERE unit_id IN (SELECT unit_id FROM retrieval_units WHERE video_id=?)
            """,
            (video_id,),
        )
        connection.execute("DELETE FROM retrieval_units WHERE video_id=?", (video_id,))

    @staticmethod
    def _refresh_index_meta_counts(connection: sqlite3.Connection) -> None:
        counts = connection.execute(
            """
            SELECT COUNT(DISTINCT CASE WHEN unit_type='video' THEN video_id END)
                       AS eligible_video_count,
                   SUM(unit_type='video') AS video_unit_count,
                   SUM(unit_type='transcript_chunk') AS chunk_unit_count
            FROM retrieval_units
            """
        ).fetchone()
        connection.execute(
            """
            UPDATE retrieval_index_meta
            SET updated_at=?,
                eligible_video_count=?,
                video_unit_count=?,
                chunk_unit_count=?
            WHERE index_name=?
            """,
            (
                _utc_now(),
                int(counts["eligible_video_count"] or 0),
                int(counts["video_unit_count"] or 0),
                int(counts["chunk_unit_count"] or 0),
                INDEX_NAME,
            ),
        )

    @staticmethod
    def _search_filters(
        *,
        level: SearchLevel,
        filters: RetrievalFilters,
        include_ignored: bool,
    ) -> tuple[str, list[Any]]:
        clauses = ["u.removed_at IS NULL"]
        parameters: list[Any] = []
        if level != "all":
            clauses.append("u.unit_type=?")
            parameters.append(level)
        if not include_ignored:
            clauses.append("u.is_ignored=0")
        if filters.reading_state is not None:
            clauses.append("u.reading_state=?")
            parameters.append(filters.reading_state)
        if filters.is_marked is not None:
            clauses.append("u.is_marked=?")
            parameters.append(int(filters.is_marked))
        if filters.uploader is not None:
            clauses.append("lower(u.uploader)=lower(?)")
            parameters.append(filters.uploader)
        if filters.archived is not None:
            clauses.append("u.archived_at IS NOT NULL" if filters.archived else "u.archived_at IS NULL")

        folder_clauses: list[str] = []
        if filters.source_db_id is not None:
            folder_clauses.append("f.source_db_id=?")
            parameters.append(filters.source_db_id)
        if filters.folder_id is not None:
            folder_clauses.append("f.folder_id=?")
            parameters.append(filters.folder_id)
        if filters.favorite_time_from is not None:
            folder_clauses.append("f.favorite_time>=?")
            parameters.append(filters.favorite_time_from)
        if filters.favorite_time_to is not None:
            folder_clauses.append("f.favorite_time<=?")
            parameters.append(filters.favorite_time_to)
        if folder_clauses:
            clauses.append(
                "EXISTS(SELECT 1 FROM retrieval_unit_folders f WHERE f.unit_id=u.unit_id AND "
                + " AND ".join(folder_clauses)
                + ")"
            )
        return " AND ".join(clauses), parameters

    def _result_from_row(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        query: str,
        retrieval_method: str,
    ) -> SearchResult:
        folder_rows = connection.execute(
            """
            SELECT source_db_id, folder_id, folder_title, favorite_time
            FROM retrieval_unit_folders WHERE unit_id=?
            ORDER BY source_db_id
            """,
            (row["unit_id"],),
        ).fetchall()
        folders = tuple(
            FolderContext(
                source_db_id=int(item["source_db_id"]),
                folder_id=int(item["folder_id"]),
                folder_title=str(item["folder_title"]),
                favorite_time=(
                    int(item["favorite_time"])
                    if item["favorite_time"] is not None
                    else None
                ),
            )
            for item in folder_rows
        )
        return SearchResult(
            unit_id=str(row["unit_id"]),
            unit_type=str(row["unit_type"]),  # type: ignore[arg-type]
            video_id=int(row["video_id"]),
            platform=str(row["platform"]),
            source_id=str(row["source_id"]),
            part=int(row["part"]),
            title=str(row["title"]),
            uploader=str(row["uploader"]),
            chunk_id=str(row["chunk_id"]) if row["chunk_id"] else None,
            source_type=str(row["source_type"]),
            start_time=float(row["start_time"]) if row["start_time"] is not None else None,
            end_time=float(row["end_time"]) if row["end_time"] is not None else None,
            matched_excerpt=_excerpt(str(row["source_text"]), query),
            lexical_score=float(row["lexical_score"]),
            retrieval_method=retrieval_method,
            index_version=str(row["index_version"]),
            reading_state=str(row["reading_state"]),
            is_marked=bool(row["is_marked"]),
            is_ignored=bool(row["is_ignored"]),
            archived=bool(row["archived_at"]),
            folders=folders,
        )


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _strings(value: object) -> str:
    if not isinstance(value, list):
        return ""
    return "\n".join(str(item).strip() for item in value if str(item).strip())


def _object_strings(value: object) -> str:
    if not isinstance(value, list):
        return ""
    rows: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = " · ".join(
                str(field).strip()
                for field in item.values()
                if str(field).strip()
            )
        else:
            text = str(item).strip()
        if text:
            rows.append(text)
    return "\n".join(rows)


def _fts_phrase(query: str) -> str:
    return '"' + query.replace('"', '""') + '"'


def _excerpt(text: str, query: str, *, radius: int = 140) -> str:
    compact = " ".join(text.split())
    position = compact.casefold().find(query.casefold())
    if position < 0:
        return compact[: radius * 2]
    start = max(0, position - radius)
    end = min(len(compact), position + len(query) + radius)
    prefix = "…" if start else ""
    suffix = "…" if end < len(compact) else ""
    return prefix + compact[start:end] + suffix
