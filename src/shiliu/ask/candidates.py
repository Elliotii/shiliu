from __future__ import annotations

import json
from typing import Any

from shiliu.ask.contracts import (
    RetrievedCandidate,
    RetrievedCandidateDisclosure,
)
from shiliu.ask.persistence import AskRunStore
from shiliu.db import Database
from shiliu.retrieval.product_search import build_bilibili_jump_url


DEFAULT_CANDIDATE_LIMIT = 5
HARD_CANDIDATE_LIMIT = 8
MAX_SEARCH_TRACES = 12
MAX_GROUPS_PER_TRACE = 8
MAX_EXCERPT_CHARACTERS = 360


class AskCandidateProjector:
    """Reconstruct a bounded, non-authoritative projection from durable Search lineage."""

    def __init__(self, db: Database, run_store: AskRunStore) -> None:
        self.db = db
        self.run_store = run_store

    def project(
        self,
        run_id: str,
        *,
        limit: int = DEFAULT_CANDIDATE_LIMIT,
    ) -> RetrievedCandidateDisclosure:
        if not 1 <= limit <= HARD_CANDIDATE_LIMIT:
            raise ValueError("candidate disclosure limit must be between 1 and 8")
        run = self.run_store.get_run(run_id)
        if run is None:
            return self._empty("ask_run_unavailable")
        links, total_links = self._lineage(run_id)
        raw_candidates: list[dict[str, Any]] = []
        available_presentations = 0
        unavailable_traces = 0
        source_groups_truncated = False
        for link in links:
            groups = self._presentation_groups(str(link["search_trace_id"]))
            if groups is None:
                unavailable_traces += 1
                continue
            available_presentations += 1
            source_groups_truncated = (
                source_groups_truncated or len(groups) > MAX_GROUPS_PER_TRACE
            )
            for group in groups[:MAX_GROUPS_PER_TRACE]:
                candidate = self._candidate_identity(link, group)
                if candidate is not None:
                    raw_candidates.append(candidate)

        metadata = self._video_metadata(raw_candidates)
        units = self._transcript_units(raw_candidates)
        citations = [
            value for value in run.get("citations", []) if isinstance(value, dict)
        ]
        projected = [
            (
                int(value["sequence"]),
                self._project_candidate(value, metadata=metadata, units=units),
            )
            for value in raw_candidates
        ]
        projected = [
            value
            for value in projected
            if not self._adopted_by_answer(value[1], citations)
        ]
        unique = self._unique_videos(projected)
        visible = unique[:limit]
        empty_reason = None
        if not links:
            empty_reason = "no_durable_search_lineage"
        elif available_presentations == 0:
            empty_reason = "search_presentations_unavailable"
        elif not unique:
            empty_reason = "no_unadopted_candidates"
        return RetrievedCandidateDisclosure(
            candidates=visible,
            inspected_search_trace_count=len(links),
            available_presentation_count=available_presentations,
            failed_or_unavailable_trace_count=unavailable_traces,
            reconstructed_candidate_count=len(unique),
            truncated=(
                len(unique) > limit
                or total_links > len(links)
                or source_groups_truncated
            ),
            empty_reason=empty_reason,
        )

    def _lineage(self, run_id: str) -> tuple[list[dict[str, Any]], int]:
        with self.db.connect() as connection:
            total = int(
                connection.execute(
                    "SELECT COUNT(*) FROM ask_search_trace_links WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0]
            )
            rows = connection.execute(
                """
                SELECT sequence, search_trace_id, query, trace_persisted
                FROM ask_search_trace_links
                WHERE run_id=?
                ORDER BY sequence
                LIMIT ?
                """,
                (run_id, MAX_SEARCH_TRACES),
            ).fetchall()
        return [dict(row) for row in rows], total

    def _presentation_groups(
        self, search_trace_id: str
    ) -> list[dict[str, Any]] | None:
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT status, group_summary_json
                FROM retrieval_search_presentations
                WHERE trace_id=?
                """,
                (search_trace_id,),
            ).fetchone()
        if row is None or str(row["status"]) != "success":
            return None
        try:
            value = json.loads(str(row["group_summary_json"]))
        except json.JSONDecodeError:
            return None
        if not isinstance(value, list):
            return None
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _candidate_identity(
        link: dict[str, Any], group: dict[str, Any]
    ) -> dict[str, Any] | None:
        video_id = group.get("video_id")
        rank = group.get("best_rank")
        if not isinstance(video_id, int) or video_id <= 0:
            return None
        if not isinstance(rank, int) or rank <= 0:
            return None
        windows = group.get("windows")
        window = (
            windows[0]
            if isinstance(windows, list) and windows and isinstance(windows[0], dict)
            else None
        )
        unit_id = str(window.get("best_chunk_id") or "") if window else ""
        return {
            "sequence": int(link["sequence"]),
            "search_trace_id": str(link["search_trace_id"]),
            "search_query": str(link.get("query") or ""),
            "search_rank": rank,
            "video_id": video_id,
            "candidate_kind": "transcript_candidate" if window else "metadata_lead",
            "unit_id": unit_id or None,
            "start_time": window.get("window_start") if window else None,
            "end_time": window.get("window_end") if window else None,
            "jump_time": window.get("jump_time") if window else None,
        }

    def _video_metadata(
        self, candidates: list[dict[str, Any]]
    ) -> dict[int, dict[str, Any]]:
        video_ids = sorted({int(value["video_id"]) for value in candidates})
        if not video_ids:
            return {}
        placeholders = ",".join("?" for _ in video_ids)
        with self.db.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, source_id AS bvid, title, video_url, status, removed_at
                FROM videos
                WHERE id IN ({placeholders})
                """,
                video_ids,
            ).fetchall()
        return {int(row["id"]): dict(row) for row in rows}

    def _transcript_units(
        self, candidates: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        unit_ids = sorted(
            {
                str(value["unit_id"])
                for value in candidates
                if value.get("unit_id")
            }
        )
        if not unit_ids:
            return {}
        placeholders = ",".join("?" for _ in unit_ids)
        with self.db.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT unit_id, video_id, unit_type, source_text
                FROM retrieval_units
                WHERE unit_id IN ({placeholders})
                """,
                unit_ids,
            ).fetchall()
        return {str(row["unit_id"]): dict(row) for row in rows}

    @staticmethod
    def _project_candidate(
        value: dict[str, Any],
        *,
        metadata: dict[int, dict[str, Any]],
        units: dict[str, dict[str, Any]],
    ) -> RetrievedCandidate:
        video_id = int(value["video_id"])
        video = metadata.get(video_id)
        unit_id = str(value.get("unit_id") or "") or None
        unit = units.get(unit_id) if unit_id else None
        if video is None:
            identity_status = "unavailable"
        elif value["candidate_kind"] == "transcript_candidate" and (
            unit_id is None
            or value.get("start_time") is None
            or value.get("end_time") is None
            or unit is None
            or int(unit["video_id"]) != video_id
            or str(unit["unit_type"]) != "transcript_chunk"
        ):
            identity_status = "stale"
        else:
            identity_status = "current"
        title = (
            str(video["title"])
            if video is not None
            else f"历史视频 #{video_id}（当前不可用）"
        )
        video_status = (
            str(video["status"])
            if video is not None and video["removed_at"] is None
            else "removed"
            if video is not None
            else "unavailable"
        )
        excerpt = None
        if unit is not None and identity_status == "current":
            excerpt = str(unit["source_text"]).strip()[:MAX_EXCERPT_CHARACTERS] or None
        jump_url = None
        detail_url = None
        if video is not None:
            detail_url = f"/videos/{video_id}/transcript"
            if value["candidate_kind"] == "metadata_lead" or identity_status == "current":
                jump_url = build_bilibili_jump_url(
                    str(video["video_url"] or ""),
                    str(video["bvid"] or ""),
                    value.get("jump_time"),
                )
        return RetrievedCandidate(
            candidate_kind=value["candidate_kind"],
            identity_status=identity_status,
            search_trace_id=str(value["search_trace_id"]),
            search_query=str(value["search_query"]),
            search_rank=int(value["search_rank"]),
            video_id=video_id,
            title=title,
            video_status=video_status,
            unit_id=(
                unit_id if value["candidate_kind"] == "transcript_candidate" else None
            ),
            start_time=(
                value.get("start_time")
                if value["candidate_kind"] == "transcript_candidate"
                else None
            ),
            end_time=(
                value.get("end_time")
                if value["candidate_kind"] == "transcript_candidate"
                else None
            ),
            excerpt=excerpt,
            jump_url=jump_url,
            detail_url=detail_url,
        )

    @staticmethod
    def _adopted_by_answer(
        candidate: RetrievedCandidate, citations: list[dict[str, Any]]
    ) -> bool:
        for citation in citations:
            if citation.get("video_id") != candidate.video_id:
                continue
            if candidate.candidate_kind == "metadata_lead":
                return True
            try:
                citation_start = float(citation["start_time"])
                citation_end = float(citation["end_time"])
            except (KeyError, TypeError, ValueError):
                continue
            if candidate.start_time is None or candidate.end_time is None:
                continue
            if max(candidate.start_time, citation_start) <= min(
                candidate.end_time, citation_end
            ):
                return True
        return False

    @staticmethod
    def _unique_videos(
        candidates: list[tuple[int, RetrievedCandidate]],
    ) -> list[RetrievedCandidate]:
        priority = {"transcript_candidate": 0, "metadata_lead": 1}
        identity_priority = {"current": 0, "stale": 1, "unavailable": 2}
        preferred = sorted(
            candidates,
            key=lambda value: (
                priority[value[1].candidate_kind],
                identity_priority[value[1].identity_status],
                value[0],
                value[1].search_rank,
            ),
        )
        by_video: dict[int, tuple[int, RetrievedCandidate]] = {}
        for sequence, candidate in preferred:
            by_video.setdefault(candidate.video_id, (sequence, candidate))
        return [
            value[1]
            for value in sorted(
                by_video.values(),
                key=lambda value: (
                    value[0],
                    value[1].search_rank,
                    value[1].video_id,
                ),
            )
        ]

    @staticmethod
    def _empty(reason: str) -> RetrievedCandidateDisclosure:
        return RetrievedCandidateDisclosure(
            inspected_search_trace_count=0,
            available_presentation_count=0,
            failed_or_unavailable_trace_count=0,
            reconstructed_candidate_count=0,
            empty_reason=reason,
        )
