from __future__ import annotations

from pathlib import Path

from shiliu.artifacts import ArtifactStore
from shiliu.asr import ASRService, ParaformerProvider
from shiliu.bilibili import BilibiliAdapter
from shiliu.config import AppConfig, AppPaths, load_api_key, load_config
from shiliu.db import Database
from shiliu.llm import OpenAICompatibleProvider
from shiliu.library import LibraryService
from shiliu.domain import PipelineError
from shiliu.logging_config import configure_logging
from shiliu.pipeline import PipelineService
from shiliu.sync import SyncService
from shiliu.taxonomy import TaxonomyCorpusService
from shiliu.taxonomy.comparison import ProfileDiscoveryComparisonService
from shiliu.taxonomy.discovery import BatchedDiscoverySpikeService
from shiliu.taxonomy.facets import FacetExtractionService
from shiliu.taxonomy.profiles import ClassificationProfileService
from shiliu.taxonomy.run_repository import TaxonomyRunRepository
from shiliu.taxonomy.workflow import TaxonomyWorkflow


class Application:
    def __init__(self, paths: AppPaths | None = None) -> None:
        base_paths = paths or AppPaths.defaults()
        self.config: AppConfig = load_config(base_paths)
        self.paths = base_paths.with_content_dir(Path(self.config.content_dir))
        self.paths.ensure()
        configure_logging(self.paths.logs_dir)
        self.db = Database(self.paths.database)
        self.db.initialize()
        self.library = LibraryService(self.db)
        if self.config.favorite_id is not None:
            self.db.migrate_legacy_source(
                self.config.favorite_id,
                self.config.favorite_title or str(self.config.favorite_id),
            )
        self.adapter = BilibiliAdapter(Path(self.config.bili_cli_root))
        self.artifacts = ArtifactStore(self.paths.videos_dir)
        self.taxonomy_corpus = TaxonomyCorpusService(self.db, self.artifacts)
        self.taxonomy_facets = FacetExtractionService(
            repository=self.taxonomy_corpus.repository,
            provider_factory=self.provider,
            output_dir=self.paths.content_dir / "taxonomy" / "runtime" / "facet_spikes",
        )
        self.taxonomy_discovery_spikes = BatchedDiscoverySpikeService(
            repository=self.taxonomy_corpus.repository,
            provider_factory=self.provider,
            output_dir=self.paths.content_dir / "taxonomy" / "runtime" / "discovery_spikes",
        )
        self.taxonomy_profiles = ClassificationProfileService(
            repository=self.taxonomy_corpus.repository,
            provider_factory=self.provider,
            output_dir=self.paths.content_dir / "taxonomy" / "runtime" / "profile_spikes",
        )
        self.taxonomy_run_repository = TaxonomyRunRepository(self.db)
        self.taxonomy_workflow = TaxonomyWorkflow(
            snapshot_repository=self.taxonomy_corpus.repository,
            run_repository=self.taxonomy_run_repository,
            provider_factory=self.provider,
            output_dir=self.paths.content_dir / "taxonomy" / "runtime" / "runs",
            profile_output_dir=(
                self.paths.content_dir / "taxonomy" / "runtime" / "profile_spikes"
            ),
        )
        self.taxonomy_profile_comparison = ProfileDiscoveryComparisonService(
            workflow=self.taxonomy_workflow,
            run_repository=self.taxonomy_run_repository,
            provider_factory=self.provider,
            output_dir=(
                self.paths.content_dir
                / "taxonomy"
                / "runtime"
                / "profile_comparisons"
            ),
            profile_output_dir=(
                self.paths.content_dir / "taxonomy" / "runtime" / "profile_spikes"
            ),
        )
        self.pipeline = PipelineService(
            db=self.db,
            adapter=self.adapter,
            artifacts=self.artifacts,
            provider_factory=self.provider,
            asr_service_factory=self.asr_service,
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
        is_transcript = role in {"fast_transcript", "formal_transcript"}
        is_taxonomy_light = role in {
            "taxonomy_local", "taxonomy_content_type", "taxonomy_validator",
            "taxonomy_assignment", "taxonomy_profile", "taxonomy_repair",
        }
        model_role = "formal_summary" if role.startswith("taxonomy_") else role
        return OpenAICompatibleProvider(
            base_url=self.config.llm_base_url,
            api_key=api_key,
            model=self.config.model_for(model_role),
            timeout_seconds=180 if is_transcript else 600,
            thinking_enabled=(
                False
                if is_transcript or role in {
                    "taxonomy_local", "taxonomy_content_type", "taxonomy_validator",
                    "taxonomy_assignment", "taxonomy_profile", "taxonomy_repair",
                }
                else True
            ),
            reasoning_effort=None if is_transcript or is_taxonomy_light else "high",
        )

    def asr_service(self) -> ASRService:
        try:
            api_key = load_api_key(self.config.asr_api_key_ref)
        except RuntimeError as exc:
            raise PipelineError(
                "macOS Keychain 中没有找到 Paraformer API Key",
                code="asr_api_key_missing",
                retryable=False,
            ) from exc
        provider = ParaformerProvider(
            base_url=self.config.asr_base_url,
            api_key=api_key,
            model=self.config.asr_model,
        )
        return ASRService(
            db=self.db,
            adapter=self.adapter,
            artifacts=self.artifacts,
            provider=provider,
        )
