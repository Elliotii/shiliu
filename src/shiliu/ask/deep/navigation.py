from __future__ import annotations

import json
from typing import Any

from shiliu.artifacts import ArtifactStore
from shiliu.ask.deep.contracts import NavigationDocument, NavigationSourceLabel
from shiliu.db import Database
from shiliu.retrieval.product_search import (
    ProductSearchFilterRequest,
    ProductSearchRequest,
    ProductSearchService,
)


_FIELD_LIMIT = 2000
_EXCERPT_LIMIT = 800
_LIST_ITEM_LIMIT = 600


class NavigationService:
    def __init__(
        self,
        *,
        db: Database,
        artifacts: ArtifactStore,
        product_search: ProductSearchService,
    ) -> None:
        self.db = db
        self.artifacts = artifacts
        self.product_search = product_search

    def search(
        self,
        query: str,
        *,
        filters: ProductSearchFilterRequest,
        limit: int = 8,
    ) -> list[NavigationDocument]:
        response = self.product_search.search(
            ProductSearchRequest(
                query=query,
                mode="auto",
                scope="video",
                result_limit=min(8, max(1, limit)),
                max_windows_per_video=1,
                filters=filters,
            )
        )
        return [
            self._project(result.video_id, result.match_excerpt)
            for result in response.results
        ]

    def _project(self, video_id: int, matched_excerpt: str) -> NavigationDocument:
        video = self.db.get_video(video_id)
        if video is None:
            raise LookupError(f"navigation video does not exist: {video_id}")
        bvid = str(video["source_id"])
        summary = self._summary(video)
        transcript = self._cleaned_transcript(video)
        notes = [
            _bounded(str(value.get("content") or ""), _LIST_ITEM_LIMIT)
            for value in self.db.list_notes(video_id)
            if str(value.get("content") or "").strip()
        ][:6]
        source_values = {
            "title": _bounded(str(video.get("title") or ""), _FIELD_LIMIT),
            "uploader": _bounded(str(video.get("uploader") or ""), _FIELD_LIMIT),
            "description": _bounded(
                str(video.get("description") or ""), _FIELD_LIMIT
            ),
            "ai_summary": "\n".join(summary),
            "user_notes": "\n".join(notes),
            "cleaned_transcript": "\n".join(transcript),
            "metadata": " ".join(
                (
                    str(video.get("duration_seconds") or ""),
                    str(video.get("reading_state") or ""),
                    str(bool(video.get("is_marked"))),
                )
            ),
        }
        excerpt = _bounded(matched_excerpt, _EXCERPT_LIMIT)
        excerpt_terms = set(" ".join(excerpt.casefold().split()).split())
        scored_sources = sorted(
            (
                (
                    len(
                        excerpt_terms
                        & set(" ".join(value.casefold().split()).split())
                    ),
                    source,
                )
                for source, value in source_values.items()
                if value.strip()
            ),
            reverse=True,
        )
        matched_sources = [
            source for score, source in scored_sources if score > 0
        ][:4]
        if not matched_sources:
            matched_sources = ["video_composite_retrieval"]
        return NavigationDocument(
            video_id=video_id,
            bvid=bvid,
            title=source_values["title"],
            uploader=source_values["uploader"],
            description=source_values["description"],
            summary_sections=summary,
            user_notes=notes,
            cleaned_transcript=transcript,
            metadata={
                "duration_seconds": int(video.get("duration_seconds") or 0),
                "reading_state": str(video.get("reading_state") or "unread"),
                "marked": bool(video.get("is_marked")),
                "active_revision": str(video.get("active_revision") or "refined"),
                "folders": [
                    str(value.get("folder_title") or "")
                    for value in self.db.video_sources(video_id)
                    if str(value.get("folder_title") or "").strip()
                ],
            },
            matched_excerpt=excerpt,
            matched_sources=matched_sources,
            source_labels={
                "title": NavigationSourceLabel(
                    source="title", priority="high"
                ),
                "uploader": NavigationSourceLabel(
                    source="uploader", priority="low"
                ),
                "description": NavigationSourceLabel(
                    source="description", priority="medium"
                ),
                "ai_summary": NavigationSourceLabel(
                    source="ai_summary", priority="high"
                ),
                "user_notes": NavigationSourceLabel(
                    source="user_notes", priority="low"
                ),
                "cleaned_transcript": NavigationSourceLabel(
                    source="cleaned_transcript", priority="low"
                ),
                "metadata": NavigationSourceLabel(
                    source="metadata", priority="low"
                ),
                "summary_sections": NavigationSourceLabel(
                    source="ai_summary", priority="high"
                ),
                "matched_excerpt": NavigationSourceLabel(
                    source="video_composite_retrieval", priority="enrichment"
                ),
            },
        )

    def _summary(self, video: dict[str, Any]) -> list[str]:
        payload = self._artifact_payload(video, "summary")
        if not isinstance(payload, dict):
            return []
        values: list[str] = []
        for key in ("conclusion", "key_points", "detailed_notes", "entities"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                values.append(f"{key}: {_bounded(value, _LIST_ITEM_LIMIT)}")
            elif isinstance(value, list):
                text = _bounded(
                    " | ".join(_object_text(item) for item in value),
                    _FIELD_LIMIT,
                )
                if text:
                    values.append(f"{key}: {text}")
        return values[:8]

    def _cleaned_transcript(self, video: dict[str, Any]) -> list[str]:
        payload = self._artifact_payload(video, "transcript")
        if not isinstance(payload, dict):
            return []
        values = []
        for section in payload.get("sections") or []:
            if not isinstance(section, dict):
                continue
            text = " ".join(
                [
                    str(section.get("title") or ""),
                    *[
                        str(value)
                        for value in section.get("paragraphs") or []
                        if isinstance(value, str)
                    ],
                ]
            )
            if text.strip():
                values.append(_bounded(text, _LIST_ITEM_LIMIT))
        return values[:6]

    def _artifact_payload(
        self, video: dict[str, Any], kind: str
    ) -> object | None:
        directory = self.artifacts.videos_dir / str(video["source_id"])
        revision = str(video.get("active_revision") or "refined")
        candidates = (
            directory / f"{kind}.{revision}.json",
            directory / f"{kind}.json",
        )
        path = next((value for value in candidates if value.is_file()), None)
        if path is None:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None


def _bounded(value: str, limit: int) -> str:
    normalized = " ".join(str(value).split())
    return normalized if len(normalized) <= limit else normalized[: limit - 1] + "…"


def _object_text(value: object) -> str:
    if isinstance(value, dict):
        return " ".join(
            str(item) for item in value.values() if isinstance(item, (str, int, float))
        )
    return str(value)
