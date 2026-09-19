from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


UnitType = Literal["video", "transcript_chunk"]
SearchLevel = Literal["video", "transcript_chunk", "all"]


@dataclass(frozen=True)
class FolderContext:
    source_db_id: int
    folder_id: int
    folder_title: str
    favorite_time: int | None


@dataclass(frozen=True)
class SearchUnit:
    unit_id: str
    unit_type: UnitType
    video_id: int
    platform: str
    source_id: str
    part: int
    title: str
    uploader: str
    chunk_id: str | None
    source_type: str
    start_time: float | None
    end_time: float | None
    source_text: str
    search_text: str
    content_hash: str
    index_version: str
    reading_state: str
    is_marked: bool
    is_ignored: bool
    archived_at: str | None
    removed_at: str | None
    folders: tuple[FolderContext, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RetrievalFilters:
    source_db_id: int | None = None
    folder_id: int | None = None
    favorite_time_from: int | None = None
    favorite_time_to: int | None = None
    reading_state: str | None = None
    is_marked: bool | None = None
    uploader: str | None = None
    uploader_contains: str | None = None
    archived: bool | None = None
    video_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class SearchResult:
    unit_id: str
    unit_type: UnitType
    video_id: int
    platform: str
    source_id: str
    part: int
    title: str
    uploader: str
    chunk_id: str | None
    source_type: str
    start_time: float | None
    end_time: float | None
    matched_excerpt: str
    lexical_score: float
    retrieval_method: str
    index_version: str
    reading_state: str
    is_marked: bool
    is_ignored: bool
    archived: bool
    folders: tuple[FolderContext, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "unit_id": self.unit_id,
            "unit_type": self.unit_type,
            "video_id": self.video_id,
            "platform": self.platform,
            "source_id": self.source_id,
            "part": self.part,
            "title": self.title,
            "uploader": self.uploader,
            "chunk_id": self.chunk_id,
            "source_type": self.source_type,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "matched_excerpt": self.matched_excerpt,
            "lexical_score": self.lexical_score,
            "retrieval_method": self.retrieval_method,
            "index_version": self.index_version,
            "reading_state": self.reading_state,
            "is_marked": self.is_marked,
            "is_ignored": self.is_ignored,
            "archived": self.archived,
            "folders": [
                {
                    "source_db_id": item.source_db_id,
                    "folder_id": item.folder_id,
                    "folder_title": item.folder_title,
                    "favorite_time": item.favorite_time,
                }
                for item in self.folders
            ],
        }


@dataclass(frozen=True)
class DenseSearchResult:
    unit_id: str
    unit_type: UnitType
    video_id: int
    platform: str
    source_id: str
    part: int
    title: str
    uploader: str
    chunk_id: str | None
    source_type: str
    start_time: float | None
    end_time: float | None
    matched_excerpt: str
    dense_score: float
    retrieval_method: str
    index_version: str
    dense_index_version: str
    model_id: str
    projection_version: str
    reading_state: str
    is_marked: bool
    is_ignored: bool
    archived: bool
    folders: tuple[FolderContext, ...]

    def as_dict(self) -> dict[str, object]:
        return _result_dict(self, dense_score=self.dense_score)


@dataclass(frozen=True)
class HybridSearchResult:
    unit_id: str
    unit_type: UnitType
    video_id: int
    platform: str
    source_id: str
    part: int
    title: str
    uploader: str
    chunk_id: str | None
    source_type: str
    start_time: float | None
    end_time: float | None
    matched_excerpt: str
    lexical_score: float | None
    dense_score: float | None
    lexical_rank: int | None
    dense_rank: int | None
    rrf_score: float
    retrieval_method: str
    lexical_retrieval_method: str | None
    fusion_version: str
    index_version: str
    lexical_index_version: str
    dense_index_version: str
    model_id: str
    projection_version: str
    reading_state: str
    is_marked: bool
    is_ignored: bool
    archived: bool
    folders: tuple[FolderContext, ...]

    def as_dict(self) -> dict[str, object]:
        return _result_dict(
            self,
            lexical_score=self.lexical_score,
            dense_score=self.dense_score,
            lexical_rank=self.lexical_rank,
            dense_rank=self.dense_rank,
            rrf_score=self.rrf_score,
        )


def _result_dict(result: object, **scores: object) -> dict[str, object]:
    values = {
        name: getattr(result, name)
        for name in (
            "unit_id", "unit_type", "video_id", "platform", "source_id", "part",
            "title", "uploader", "chunk_id", "source_type", "start_time", "end_time",
            "matched_excerpt", "retrieval_method", "index_version", "reading_state",
            "is_marked", "is_ignored", "archived",
        )
    }
    for name in ("dense_index_version", "model_id", "projection_version", "fusion_version", "lexical_index_version", "lexical_retrieval_method"):
        if hasattr(result, name):
            values[name] = getattr(result, name)
    values.update(scores)
    values["folders"] = [
        {
            "source_db_id": item.source_db_id,
            "folder_id": item.folder_id,
            "folder_title": item.folder_title,
            "favorite_time": item.favorite_time,
        }
        for item in getattr(result, "folders")
    ]
    return values
