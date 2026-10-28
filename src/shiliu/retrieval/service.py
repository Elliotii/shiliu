from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import time
from typing import Any

from pydantic import ValidationError

from shiliu.domain import SubtitleSegment
from shiliu.storage.artifacts import ArtifactError
from shiliu.retrieval.chunking import build_raw_subtitle_chunks
from shiliu.retrieval.lexical import F1Tokenizer
from shiliu.retrieval import bm25
from shiliu.retrieval.models import (
    FolderContext,
    RetrievalFilters,
    SearchResult,
    SearchUnit,
)


INDEX_NAME = "shiliu_lexical"
INDEX_VERSION = "pg-collection-lexical-v1"
FTS_TOKENIZER = "jieba-simple-ts-rank"
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
    """Collection units, shared PG FTS and formal scope/version filtering."""

    def __init__(self, *, db, artifacts):
        self.db, self.artifacts = db, artifacts
        self.tokenizer = F1Tokenizer(artifacts.videos_dir / "tokenizer-cache")

    def _eligible_video(self, video_id, *, conn=None):
        video = self.db.get_video(video_id, conn=conn)
        if video is None or video["removed_at"]:
            return None
        return video if self.db.video_has_active_source(video_id, conn=conn) else None

    def _eligible_videos(self):
        return [
            v
            for v in self.db.list_videos()
            if self._eligible_video(v["id"]) is not None
        ]

    def request(self, video_id, *, reason="rebuild", conn=None):
        with self.db.connect(conn, guard=True) as c:
            self.db._touch(c, video_id, reason=reason)

    def replace_video(self, video_id):
        # Explicit administrative action requeues a durable intent. Mutations
        # have already registered theirs before commit.
        self.request(video_id)
        from shiliu.retrieval.coordinator import ProjectionWorker

        return ProjectionWorker(self, None).run_one(video_id=video_id)

    def delete_video(self, video_id):
        with self.db.connect(guard=True) as c:
            self.db._touch(c, video_id, reason="index_remove")
            # Explicit removal is an index intent, never a formal video deletion.
            c.execute(
                "UPDATE shiliu.retrieval_projection_tasks SET payload=payload||'{\"absent\":true}'::jsonb WHERE workspace_id=%s AND domain='collection' AND resource_key=%s",
                (self.db.workspace_id, str(video_id)),
            )
            count = c.execute(
                "DELETE FROM shiliu.retrieval_units WHERE workspace_id=%s AND video_id=%s RETURNING unit_id",
                (self.db.workspace_id, video_id),
            ).fetchall()
        return len(count)

    def rebuild(self):
        from shiliu.retrieval.coordinator import ProjectionWorker

        stats = RebuildStats()
        started = time.monotonic()
        # Requeue each resource without truncating still-valid active data.
        for video in self.db.list_videos():
            self.request(video["id"], reason="lexical_rebuild")
            ProjectionWorker(self, None).run_one(video_id=video["id"])
        current = self.statistics()["current"]
        stats.eligible_video_count = current["video_unit_count"]
        stats.video_unit_count = current["video_unit_count"]
        stats.chunk_unit_count = current["chunk_unit_count"]
        stats.duration_seconds = time.monotonic() - started
        return stats

    def _search_filters(self, *, level, filters, include_ignored=False):
        clauses = [
            "u.workspace_id=%s",
            "u.generation=t.requested_generation",
            "v.removed_at IS NULL",
            "u.removed_at IS NULL",
            "NOT COALESCE((t.payload->>'absent')::boolean,false)",
            "EXISTS(SELECT 1 FROM shiliu.video_source_memberships m JOIN shiliu.favorite_sources s ON "
            "(m.workspace_id,m.source_id)=(s.workspace_id,s.id) WHERE m.workspace_id=v.workspace_id "
            "AND m.video_id=v.id AND m.removed_at IS NULL AND s.status='active')",
        ]
        params = [self.db.workspace_id]
        if level != "all":
            clauses.append("u.unit_type=%s")
            params.append(level)
        if not include_ignored:
            clauses.append("NOT v.is_ignored")
        for column, value in [
            ("reading_state", filters.reading_state),
            ("is_marked", filters.is_marked),
        ]:
            if value is not None:
                clauses.append("v." + column + "=%s")
                params.append(value)
        if filters.uploader is not None:
            clauses.append("lower(v.uploader)=lower(%s)")
            params.append(filters.uploader)
        if filters.uploader_contains is not None:
            clauses.append("v.uploader ILIKE %s ESCAPE E'\\\\'")
            params.append("%" + escape_like(filters.uploader_contains) + "%")
        if filters.archived is not None:
            clauses.append(
                "v.archived_at IS NOT NULL"
                if filters.archived
                else "v.archived_at IS NULL"
            )
        # None means unrestricted. An explicit empty tuple means no candidates.
        if filters.video_ids is not None:
            clauses.append("v.id=ANY(%s)")
            params.append(list(filters.video_ids))
        folder = []
        for column, prefix, operator, value in [
            ("source_id", "m", "=", filters.source_db_id),
            ("folder_id", "s", "=", filters.folder_id),
            ("favorite_time", "m", ">=", filters.favorite_time_from),
            ("favorite_time", "m", "<=", filters.favorite_time_to),
        ]:
            if value is None:
                continue
            folder.append(f"{prefix}.{column}{operator}%s")
            params.append(value)
        if folder:
            clauses.append(
                "EXISTS(SELECT 1 FROM shiliu.video_source_memberships m JOIN shiliu.favorite_sources s ON "
                "(m.workspace_id,m.source_id)=(s.workspace_id,s.id) WHERE m.workspace_id=v.workspace_id AND m.video_id=v.id "
                "AND m.removed_at IS NULL AND s.status='active' AND "
                + " AND ".join(folder)
                + ")"
            )
        return " AND ".join(clauses), params

    @staticmethod
    def current_join():
        return "FROM shiliu.retrieval_units u JOIN shiliu.videos v ON (v.workspace_id,v.id)=(u.workspace_id,u.video_id) JOIN shiliu.retrieval_projection_tasks t ON t.workspace_id=u.workspace_id AND t.domain='collection' AND t.resource_key=u.video_id::text "

    def search(
        self,
        query,
        *,
        level="all",
        top_k=10,
        filters=None,
        include_ignored=False,
        navigation=True,
    ):
        normalized = " ".join(query.split())
        if not normalized:
            return []
        if level not in {"all", "video", "transcript_chunk"} or not 1 <= top_k <= 500:
            raise ValueError("Invalid search bounds")
        where, params = self._search_filters(
            level=level,
            filters=filters or RetrievalFilters(),
            include_ignored=include_ignored,
        )
        match = self.tokenizer.query(normalized)
        if navigation and len(normalized) < 3:
            statement = (
                "SELECT u.*,0.0::real AS lexical_score "
                + self.current_join()
                + "WHERE u.search_text ILIKE %s ESCAPE E'\\\\' AND "
                + where
                + " ORDER BY u.unit_id LIMIT %s"
            )
            values = ["%" + escape_like(normalized) + "%", *params, top_k]
            method = "lexical_substring_fallback"
        elif match and level == "transcript_chunk":
            distance = "u.tokenized_text OPERATOR(shiliu_search.<@>) shiliu_search.to_bm25query(%s,'shiliu.retrieval_units_chunk_bm25')::shiliu_search.bm25query"
            statement = (
                "SELECT u.*,-(" + distance + ") AS lexical_score "
                + self.current_join()
                + "WHERE u.unit_type='transcript_chunk' AND u.search_vector@@to_tsquery('pg_catalog.simple',%s) AND "
                + where
                + " ORDER BY " + distance + " ASC,u.unit_id LIMIT %s"
            )
            terms = " ".join(dict.fromkeys(self.tokenizer.tokens(normalized)))
            values = [terms, match, *params, terms, top_k]
            method = "lexical"
        elif match:
            statement = (
                "SELECT u.*,ts_rank(u.search_vector,to_tsquery('simple',%s)) AS lexical_score "
                + self.current_join()
                + "WHERE u.search_vector@@to_tsquery('simple',%s) AND "
                + where
                + " ORDER BY lexical_score DESC,u.unit_id LIMIT %s"
            )
            values = [match, match, *params, top_k]
            method = "lexical"
        else:
            return []
        with self.db.connect(read_only=True) as c:
            if level == "transcript_chunk" and method == "lexical":
                bm25.check_index(c)
            rows = c.execute(statement, values).fetchall()
            folders = _folder_contexts(
                c, self.db.workspace_id, [r["unit_id"] for r in rows]
            )
            return [
                self._result_from_row(
                    r,
                    folders=folders.get(r["unit_id"], ()),
                    query=normalized,
                    retrieval_method=method,
                )
                for r in rows
            ]

    def chunk_index_identity(self):
        with self.db.connect(read_only=True) as c:
            bm25.check_index(c)
        return bm25.identity(self.tokenizer.profile)

    def statistics(self):
        where, params = self._search_filters(
            level="all", filters=RetrievalFilters(), include_ignored=False
        )
        with self.db.connect(read_only=True) as c:
            counts = c.execute(
                "SELECT COUNT(*) AS metadata_count,COUNT(DISTINCT u.unit_id) AS distinct_unit_count,COUNT(*) FILTER(WHERE u.unit_type='video') AS video_unit_count,COUNT(*) FILTER(WHERE u.unit_type='transcript_chunk') AS chunk_unit_count "
                + self.current_join()
                + "WHERE "
                + where,
                params,
            ).fetchone()
            tasks = c.execute(
                "SELECT COUNT(*) FILTER(WHERE status='failed') AS failed,COUNT(*) FILTER(WHERE status!='completed') AS missing FROM shiliu.retrieval_projection_tasks WHERE workspace_id=%s AND domain='collection'",
                (self.db.workspace_id,),
            ).fetchone()
        counts.update(
            fts_count=counts["metadata_count"],
            duplicate_count=0,
            consistent=True,
            subtitle_source_distribution={},
        )
        return {
            "index": {
                "index_name": INDEX_NAME,
                "index_version": INDEX_VERSION,
                "tokenizer": FTS_TOKENIZER,
                "lexical_profile": self.tokenizer.profile,
            },
            "transcript_chunk_index": self.chunk_index_identity(),
            "current": dict(counts),
            "last_full_rebuild": None,
            "missing": tasks["missing"],
            "failed": tasks["failed"],
        }

    def _build_video_units(
        self, video: dict[str, Any], stats: RebuildStats
    ) -> list[SearchUnit]:
        folders = (
            video.get("_snapshot_folders")
            if "_snapshot_folders" in video
            else self._active_folders(int(video["id"]))
        )
        sections = [
            ("Title", str(video.get("title") or "")),
            ("Uploader", str(video.get("uploader") or "")),
            ("Description", str(video.get("description") or "")),
        ]
        sections.extend(self._summary_sections(video, stats))
        sections.extend(self._transcript_sections(video, stats))
        notes = (
            video.get("_snapshot_notes")
            if "_snapshot_notes" in video
            else self.db.list_notes(int(video["id"]))
        )
        if notes:
            sections.append(
                ("User Notes", "\n".join(str(note["content"]) for note in notes))
            )
        if folders:
            sections.append(
                (
                    "Favorite Folders",
                    "\n".join(folder.folder_title for folder in folders),
                )
            )
        source_text = "\n\n".join(
            f"[{label}]\n{value.strip()}" for label, value in sections if value.strip()
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
        try:
            payload = json.loads(self.artifacts.raw_bytes(str(raw_path)))
            if not isinstance(payload, list):
                raise ValueError("raw subtitle JSON is not an array")
            segments = [SubtitleSegment.model_validate(item) for item in payload]
        except (
            ArtifactError,
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            ValidationError,
            ValueError,
        ):
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
                archived_at=str(video["archived_at"])
                if video.get("archived_at")
                else None,
                removed_at=str(video["removed_at"])
                if video.get("removed_at")
                else None,
                folders=folders,
            )
            for chunk in chunks
        ]

    def _summary_sections(
        self, video: dict[str, Any], stats: RebuildStats
    ) -> list[tuple[str, str]]:
        if not video.get("summary_path"):
            return []
        try:
            payload = json.loads(
                self.artifacts.generated_json_bytes(video["summary_path"])
            )
            if not isinstance(payload, dict):
                raise ValueError("summary is not an object")
            values: list[tuple[str, str]] = []
            values.append(("Summary Conclusion", str(payload.get("conclusion") or "")))
            values.append(("Summary Key Points", _strings(payload.get("key_points"))))
            values.append(
                ("Summary Detailed Notes", _strings(payload.get("detailed_notes")))
            )
            values.append(
                ("Summary Entities", _object_strings(payload.get("entities")))
            )
            values.append(
                (
                    "Summary Chapters (video-level only)",
                    _object_strings(payload.get("important_chapters")),
                )
            )
            return [(label, value) for label, value in values if value]
        except (ArtifactError, OSError, UnicodeError, json.JSONDecodeError, ValueError):
            stats.malformed_summary_json += 1
            return []

    def _transcript_sections(
        self, video: dict[str, Any], stats: RebuildStats
    ) -> list[tuple[str, str]]:
        if not video.get("transcript_path"):
            return []
        try:
            payload = json.loads(
                self.artifacts.generated_json_bytes(video["transcript_path"])
            )
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
            return (
                [("Cleaned Transcript (video-level only)", "\n\n".join(values))]
                if values
                else []
            )
        except (ArtifactError, OSError, UnicodeError, json.JSONDecodeError, ValueError):
            stats.malformed_transcript_json += 1
            return []

    def _active_folders(self, video_id: int, *, conn=None) -> tuple[FolderContext, ...]:
        with self.db.connect(conn, read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT s.id AS source_db_id, s.folder_id, s.folder_title, m.favorite_time
                FROM video_source_memberships m
                JOIN favorite_sources s ON s.id=m.source_id
                WHERE m.workspace_id=%s AND m.video_id=%s AND m.removed_at IS NULL AND s.status='active'
                ORDER BY s.sort_order, s.id
                """,
                (self.db.workspace_id, video_id),
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

    def _result_from_row(
        self,
        row: dict[str, Any],
        *,
        folders: tuple[FolderContext, ...],
        query: str,
        retrieval_method: str,
    ) -> SearchResult:
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
            start_time=float(row["start_time"])
            if row["start_time"] is not None
            else None,
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
                str(field).strip() for field in item.values() if str(field).strip()
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


def escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _folder_contexts(connection, workspace_id, unit_ids):
    """Hydrate one returned result page, never a query per hit."""
    result = {}
    if not unit_ids:
        return result
    for item in connection.execute(
        "SELECT unit_id,source_db_id,folder_id,folder_title,favorite_time FROM retrieval_unit_folders WHERE workspace_id=%s AND unit_id=ANY(%s) ORDER BY unit_id,source_db_id",
        (workspace_id, unit_ids),
    ):
        result.setdefault(item["unit_id"], []).append(
            FolderContext(
                source_db_id=int(item["source_db_id"]),
                folder_id=int(item["folder_id"]),
                folder_title=str(item["folder_title"]),
                favorite_time=int(item["favorite_time"])
                if item["favorite_time"] is not None
                else None,
            )
        )
    return {key: tuple(values) for key, values in result.items()}
