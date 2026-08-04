from __future__ import annotations

import os
from pathlib import Path

from shiliu.artifacts import ArtifactStore
from shiliu.ask import AskService
from shiliu.asr import ASRService, ParaformerProvider
from shiliu.bilibili import BilibiliAdapter
from shiliu.config import AppConfig, AppPaths, load_api_key, load_config
from shiliu.db import Database
from shiliu.llm import OpenAICompatibleProvider
from shiliu.library import LibraryService
from shiliu.domain import PipelineError
from shiliu.logging_config import configure_logging
from shiliu.pipeline import PipelineService
from shiliu.retrieval import (
    HybridRetrievalService,
    QwenEmbeddingProvider,
    RetrievalIndexCoordinator,
    RetrievalService,
    SearchOrchestrator,
    SearchResultConsolidator,
    EvidenceEnricher,
    ProductSearchService,
    SQLiteExactDenseIndex,
)
from shiliu.sync import SyncService
from shiliu.evidence import EvidenceSearchService
from shiliu.runtime_modes import PRODUCT_RUNTIME_CONFIG
from shiliu.ask.deep.navigation import NavigationService
from shiliu.ask.deep.transcript import TranscriptSearchService, TranscriptWindowReader
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.research.inner_service import InnerResearchService
from shiliu.research.outer_service import OuterResearchService
from shiliu.research.inner_tools import LocalInnerToolAdapter
from shiliu.research.service import ResearchTaskService
from shiliu.research.control_service import ResearchControlService
from shiliu.research.product_service import ResearchProductService
from shiliu.research.knowledge_service import ResearchKnowledgeService
from shiliu.stage5 import Stage5PipelineService
from shiliu.taxonomy import TaxonomyCorpusService
from shiliu.taxonomy.comparison import ProfileDiscoveryComparisonService
from shiliu.taxonomy.controlled_facets import HybridControlledFacetsService
from shiliu.taxonomy.controlled_facets_completion import (
    ControlledFacetCompletionService,
)
from shiliu.taxonomy.discovery import BatchedDiscoverySpikeService
from shiliu.taxonomy.domain_stability import DomainStabilityService
from shiliu.taxonomy.domain_consolidation_v2 import DomainConsolidationV2Service
from shiliu.taxonomy.domain_completion import DomainCompletionService
from shiliu.taxonomy.facets import FacetExtractionService
from shiliu.taxonomy.faceted_metadata import FacetedMetadataService
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
        self.research = ResearchTaskService(self.db)
        self._research_control: ResearchControlService | None = None
        self._research_inner: InnerResearchService | None = None
        self._research_outer: OuterResearchService | None = None
        self._research_product: ResearchProductService | None = None
        self._research_knowledge: ResearchKnowledgeService | None = None
        if self.config.favorite_id is not None:
            self.db.migrate_legacy_source(
                self.config.favorite_id,
                self.config.favorite_title or str(self.config.favorite_id),
            )
        self.adapter = BilibiliAdapter(Path(self.config.bili_cli_root))
        self.artifacts = ArtifactStore(self.paths.videos_dir)
        self.retrieval = RetrievalService(db=self.db, artifacts=self.artifacts)
        self._dense_retrieval: SQLiteExactDenseIndex | None = None
        self._hybrid_retrieval: HybridRetrievalService | None = None
        self._search_orchestrator: SearchOrchestrator | None = None
        self._product_search: ProductSearchService | None = None
        self._ask_service: AskService | None = None
        self._stage5_pipeline: Stage5PipelineService | None = None
        self.runtime_config = PRODUCT_RUNTIME_CONFIG
        default_cache = (
            self.paths.state_dir / "fastembed-cache"
            if paths is not None
            else Path.home() / "Library" / "Caches" / "Shiliu" / "fastembed"
        )
        self.fastembed_cache_dir = Path(
            os.environ.get("SHILIU_FASTEMBED_CACHE_DIR", default_cache)
        ).expanduser()
        self.qwen_model_path = Path(
            os.environ.get(
                "SHILIU_QWEN_MODEL_PATH",
                "/Users/elliot/Library/Caches/Shiliu/model-selection/Qwen3-Embedding-0.6B",
            )
        ).expanduser()
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        self.retrieval_coordinator = RetrievalIndexCoordinator(
            db=self.db,
            lexical=self.retrieval,
            dense_factory=lambda: self.dense_retrieval,
        )
        self.retrieval_coordinator.initialize_schema()
        self.library = LibraryService(self.db, self.retrieval_coordinator)
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
        self.taxonomy_domain_stability = DomainStabilityService(
            repository=self.taxonomy_corpus.repository,
            run_repository=self.taxonomy_run_repository,
            workflow=self.taxonomy_workflow,
            output_dir=self.paths.content_dir / "taxonomy" / "runtime" / "runs",
            profile_output_dir=(
                self.paths.content_dir / "taxonomy" / "runtime" / "profile_spikes"
            ),
        )
        self.taxonomy_domain_consolidation_v2 = DomainConsolidationV2Service(
            repository=self.taxonomy_corpus.repository,
            run_repository=self.taxonomy_run_repository,
            workflow=self.taxonomy_workflow,
            output_dir=self.paths.content_dir / "taxonomy" / "runtime" / "runs",
        )
        self.taxonomy_domain_completion = DomainCompletionService(
            repository=self.taxonomy_corpus.repository,
            run_repository=self.taxonomy_run_repository,
            workflow=self.taxonomy_workflow,
            output_dir=self.paths.content_dir / "taxonomy" / "runtime" / "runs",
        )
        self.taxonomy_faceted_metadata = FacetedMetadataService(
            repository=self.taxonomy_corpus.repository,
            run_repository=self.taxonomy_run_repository,
            provider_factory=self.provider,
            output_dir=self.paths.content_dir / "taxonomy" / "runtime" / "runs",
            profile_output_dir=(
                self.paths.content_dir / "taxonomy" / "runtime" / "profile_spikes"
            ),
        )
        self.taxonomy_controlled_facets = HybridControlledFacetsService(
            repository=self.taxonomy_corpus.repository,
            run_repository=self.taxonomy_run_repository,
            provider_factory=self.provider,
            output_dir=self.paths.content_dir / "taxonomy" / "runtime" / "runs",
            profile_output_dir=(
                self.paths.content_dir / "taxonomy" / "runtime" / "profile_spikes"
            ),
        )
        self.taxonomy_controlled_facet_completion = ControlledFacetCompletionService(
            repository=self.taxonomy_corpus.repository,
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
            index_coordinator=self.retrieval_coordinator,
        )
        self.sync_service = SyncService(
            db=self.db,
            adapter=self.adapter,
            pipeline=self.pipeline,
            favorite_id=self.config.favorite_id,
            lock_path=self.paths.sync_lock,
            index_coordinator=self.retrieval_coordinator,
        )

    @property
    def dense_retrieval(self) -> SQLiteExactDenseIndex:
        if self._dense_retrieval is None:
            self._dense_retrieval = SQLiteExactDenseIndex(
                db=self.db,
                provider=QwenEmbeddingProvider(model_path=self.qwen_model_path),
            )
        return self._dense_retrieval

    @property
    def hybrid_retrieval(self) -> HybridRetrievalService:
        if self._hybrid_retrieval is None:
            self._hybrid_retrieval = HybridRetrievalService(
                lexical=self.retrieval, dense=self.dense_retrieval
            )
        return self._hybrid_retrieval

    @property
    def search_orchestrator(self) -> SearchOrchestrator:
        if self._search_orchestrator is None:
            self._search_orchestrator = SearchOrchestrator(
                db=self.db,
                lexical=self.retrieval,
                dense_factory=lambda: self.dense_retrieval,
                hybrid_factory=lambda: self.hybrid_retrieval,
            )
        return self._search_orchestrator

    @property
    def product_search(self) -> ProductSearchService:
        if self._product_search is None:
            self._product_search = ProductSearchService(
                db=self.db,
                raw_search=self.search_orchestrator,
                consolidator=SearchResultConsolidator(),
                enricher=EvidenceEnricher(db=self.db, artifacts=self.artifacts),
            )
        return self._product_search

    @property
    def ask_service(self) -> AskService:
        if self._ask_service is None:
            self._ask_service = AskService(
                db=self.db,
                product_search=self.product_search,
                provider_factory=self.provider,
                runtime_corpus_identity=self.runtime_config.corpus_identity,
                artifacts=self.artifacts,
            )
        return self._ask_service

    @property
    def stage5_pipeline(self) -> Stage5PipelineService:
        if self._stage5_pipeline is None:
            evidence_search = EvidenceSearchService(
                db=self.db,
                product_search=self.product_search,
                authority_mode="live_current_exact_replay",
                runtime_corpus_identity=self.runtime_config.corpus_identity,
            )
            self._stage5_pipeline = Stage5PipelineService(
                db=self.db,
                artifacts=self.artifacts,
                evidence_search=evidence_search,
                trace_dir=self.paths.logs_dir / "stage5_traces",
            )
        return self._stage5_pipeline

    @property
    def research_control(self) -> ResearchControlService:
        if self._research_control is None:
            self._research_control = ResearchControlService(
                db=self.db,
                kernel=self.research,
            )
        return self._research_control

    @property
    def research_inner(self) -> InnerResearchService:
        if self._research_inner is None:
            materializer = TranscriptEvidenceMaterializer(self.db)
            evidence_search = EvidenceSearchService(
                db=self.db,
                product_search=self.product_search,
                authority_mode="live_current_exact_replay",
                runtime_corpus_identity=self.runtime_config.corpus_identity,
            )
            tools = LocalInnerToolAdapter(
                navigation=NavigationService(
                    db=self.db,
                    artifacts=self.artifacts,
                    product_search=self.product_search,
                ),
                transcripts=TranscriptSearchService(
                    evidence_search=evidence_search,
                    materializer=materializer,
                    max_spans_per_search=6,
                    max_characters_per_search=6000,
                ),
                windows=TranscriptWindowReader(self.db, materializer),
            )
            self._research_inner = InnerResearchService(
                db=self.db,
                kernel=self.research,
                tools=tools,
                materializer=materializer,
                provider_runs_authorized=False,
            )
        return self._research_inner

    @property
    def research_outer(self) -> OuterResearchService:
        if self._research_outer is None:
            self._research_outer = OuterResearchService(
                db=self.db,
                kernel=self.research,
                provider_runs_authorized=False,
            )
        return self._research_outer

    @property
    def research_product(self) -> ResearchProductService:
        if self._research_product is None:
            self._research_product = ResearchProductService(
                db=self.db,
                kernel=self.research,
                inner=self.research_inner,
                outer=self.research_outer,
                control=self.research_control,
            )
        return self._research_product

    @property
    def research_knowledge(self) -> ResearchKnowledgeService:
        if self._research_knowledge is None:
            self._research_knowledge = ResearchKnowledgeService(
                db=self.db,
                kernel=self.research,
                product=self.research_product,
            )
        return self._research_knowledge

    def provider(self, role: str = "formal_summary") -> OpenAICompatibleProvider:
        try:
            api_key = load_api_key(self.config.api_key_ref)
        except RuntimeError as exc:
            raise PipelineError(str(exc), code="api_key_missing", retryable=False) from exc
        is_transcript = role in {"fast_transcript", "formal_transcript"}
        is_taxonomy_light = role in {
            "taxonomy_local", "taxonomy_content_type", "taxonomy_content_type_global",
            "taxonomy_validator",
            "taxonomy_content_type_purity",
            "taxonomy_assignment", "taxonomy_profile", "taxonomy_repair",
        }
        is_ask_light = role in {"query_analysis", "agent_action"}
        model_role = "formal_summary" if role.startswith("taxonomy_") else role
        return OpenAICompatibleProvider(
            base_url=self.config.llm_base_url,
            api_key=api_key,
            model=self.config.model_for(model_role),
            timeout_seconds=180 if is_transcript or role in {
                "query_analysis", "agent_action", "grounded_answer"
            } else 600,
            thinking_enabled=(
                False
                if is_transcript or is_ask_light or role in {
                    "taxonomy_local", "taxonomy_content_type",
                    "taxonomy_content_type_global", "taxonomy_validator",
                    "taxonomy_content_type_purity",
                    "taxonomy_assignment", "taxonomy_profile", "taxonomy_repair",
                }
                else True
            ),
            reasoning_effort=(
                None
                if is_transcript or is_taxonomy_light or is_ask_light
                else "high"
            ),
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
            index_coordinator=self.retrieval_coordinator,
        )
