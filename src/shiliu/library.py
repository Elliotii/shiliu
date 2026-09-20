from __future__ import annotations

from typing import Any, Protocol

from shiliu.db import Database
from shiliu.domain import ReadingState


class LibraryNotFound(LookupError):
    pass


class LibraryValidationError(ValueError):
    pass


class _IndexCoordinator(Protocol):
    def safe_sync_video(self, video_id: int, *, trigger: str) -> object: ...


class LibraryService:
    """User-owned reading state, independent from the processing pipeline."""

    def __init__(self, db: Database, index_coordinator: _IndexCoordinator | None = None) -> None:
        self.db = db
        self.index_coordinator = index_coordinator

    def set_reading_state(self, video_id: int, state: str) -> dict[str, Any]:
        try:
            reading_state = ReadingState(state)
        except ValueError as exc:
            raise LibraryValidationError("阅读状态无效") from exc
        self._require_video(video_id)
        self.db.set_reading_state(video_id, reading_state.value)
        self._sync(video_id, "reading_state_changed")
        return self._require_video(video_id)

    def set_marked(self, video_id: int, marked: bool) -> dict[str, Any]:
        self._require_video(video_id)
        self.db.set_marked(video_id, marked)
        self._sync(video_id, "marked_changed")
        return self._require_video(video_id)

    def set_archived(self, video_id: int, archived: bool) -> dict[str, Any]:
        self._require_video(video_id)
        self.db.set_archived(video_id, archived)
        self._sync(video_id, "archived_changed")
        return self._require_video(video_id)

    def add_note(self, video_id: int, content: str) -> dict[str, Any]:
        self._require_video(video_id)
        value = content.strip()
        if not value:
            raise LibraryValidationError("笔记不能为空")
        note = self.db.create_note(video_id, value)
        self._sync(video_id, "note_created")
        return note

    def update_note(self, note_id: int, content: str) -> dict[str, Any]:
        value = content.strip()
        if not value:
            raise LibraryValidationError("笔记不能为空")
        note = self.db.update_note(note_id, value)
        if note is None:
            raise LibraryNotFound("笔记不存在")
        self._sync(int(note["video_id"]), "note_updated")
        return note

    def delete_note(self, note_id: int) -> dict[str, Any]:
        note = self.db.get_note(note_id)
        if note is None:
            raise LibraryNotFound("笔记不存在")
        self.db.delete_note(note_id)
        self._sync(int(note["video_id"]), "note_deleted")
        return note

    def set_ignored(self, video_id: int, ignored: bool) -> dict[str, Any]:
        self._require_video(video_id)
        self.db.set_ignored(video_id, ignored)
        self._sync(video_id, "ignored_changed")
        return self._require_video(video_id)

    def _sync(self, video_id: int, trigger: str) -> None:
        if self.index_coordinator is not None:
            self.index_coordinator.safe_sync_video(video_id, trigger=trigger)

    def _require_video(self, video_id: int) -> dict[str, Any]:
        video = self.db.get_video(video_id)
        if video is None:
            raise LibraryNotFound("视频不存在")
        return video
