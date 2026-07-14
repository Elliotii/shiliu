from __future__ import annotations

from pathlib import Path

from shiliu.artifacts import ArtifactStore
from shiliu.bilibili import BilibiliAdapter
from shiliu.config import AppConfig, AppPaths, load_api_key, load_config
from shiliu.db import Database
from shiliu.llm import OpenAICompatibleProvider
from shiliu.domain import PipelineError
from shiliu.logging_config import configure_logging
from shiliu.pipeline import PipelineService
from shiliu.sync import SyncService


class Application:
    def __init__(self, paths: AppPaths | None = None) -> None:
        base_paths = paths or AppPaths.defaults()
        self.config: AppConfig = load_config(base_paths)
        self.paths = base_paths.with_content_dir(Path(self.config.content_dir))
        self.paths.ensure()
        configure_logging(self.paths.logs_dir)
        self.db = Database(self.paths.database)
        self.db.initialize()
        if self.config.favorite_id is not None:
            self.db.migrate_legacy_source(
                self.config.favorite_id,
                self.config.favorite_title or str(self.config.favorite_id),
            )
        self.adapter = BilibiliAdapter(Path(self.config.bili_cli_root))
        self.artifacts = ArtifactStore(self.paths.videos_dir)
        self.pipeline = PipelineService(
            db=self.db,
            adapter=self.adapter,
            artifacts=self.artifacts,
            provider_factory=self.provider,
        )
        self.sync_service = SyncService(
            db=self.db,
            adapter=self.adapter,
            pipeline=self.pipeline,
            favorite_id=self.config.favorite_id,
            lock_path=self.paths.sync_lock,
        )

    def provider(self, role: str = "formal_summary") -> OpenAICompatibleProvider:
        try:
            api_key = load_api_key(self.config.api_key_ref)
        except RuntimeError as exc:
            raise PipelineError(str(exc), code="api_key_missing", retryable=False) from exc
        is_fast = role == "fast_transcript"
        return OpenAICompatibleProvider(
            base_url=self.config.llm_base_url,
            api_key=api_key,
            model=self.config.model_for(role),
            timeout_seconds=180 if is_fast else 600,
            thinking_enabled=not is_fast,
            reasoning_effort=None if is_fast else self.config.formal_reasoning_effort,
        )
