from __future__ import annotations

from typing import Any

from shiliu.db import Database
from shiliu.domain import ReadingState


class LibraryNotFound(LookupError):
    pass


class LibraryValidationError(ValueError):
    pass


class LibraryService:
    """User-owned reading state, independent from the processing pipeline."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def set_reading_state(self, video_id: int, state: str) -> dict[str, Any]:
        try:
            reading_state = ReadingState(state)
        except ValueError as exc:
            raise LibraryValidationError("阅读状态无效") from exc
        self._require_video(video_id)
        self.db.set_reading_state(video_id, reading_state.value)
        return self._require_video(video_id)

    def set_marked(self, video_id: int, marked: bool) -> dict[str, Any]:
        self._require_video(video_id)
        self.db.set_marked(video_id, marked)
        return self._require_video(video_id)

    def set_archived(self, video_id: int, archived: bool) -> dict[str, Any]:
        self._require_video(video_id)
        self.db.set_archived(video_id, archived)
        return self._require_video(video_id)

    def add_note(self, video_id: int, content: str) -> dict[str, Any]:
        self._require_video(video_id)
        value = content.strip()
        if not value:
            raise LibraryValidationError("笔记不能为空")
        return self.db.create_note(video_id, value)

    def update_note(self, note_id: int, content: str) -> dict[str, Any]:
        value = content.strip()
        if not value:
            raise LibraryValidationError("笔记不能为空")
        note = self.db.update_note(note_id, value)
        if note is None:
            raise LibraryNotFound("笔记不存在")
        return note

    def delete_note(self, note_id: int) -> dict[str, Any]:
        note = self.db.get_note(note_id)
        if note is None:
            raise LibraryNotFound("笔记不存在")
        self.db.delete_note(note_id)
        return note

    def _require_video(self, video_id: int) -> dict[str, Any]:
        video = self.db.get_video(video_id)
        if video is None:
            raise LibraryNotFound("视频不存在")
        return video
