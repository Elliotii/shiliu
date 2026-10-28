from __future__ import annotations

import os
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

from shiliu.artifacts import ArtifactStore
from shiliu.ask import AskService
from shiliu.asr import ASRService, ParaformerProvider
from shiliu.bilibili import BilibiliAdapter
from shiliu.config import AppConfig, AppPaths, PostgresConfig, load_postgres_config, load_api_key, load_config
from shiliu.storage.postgres import PgDatabase
from shiliu.storage.errors import StorageError
from shiliu.storage.scope import ResourceContext, personal_context
from shiliu.migration.schema import HEAD_REVISION
from shiliu.db import Database
from shiliu.llm import OpenAICompatibleProvider
from shiliu.library import LibraryService
from shiliu.domain import PipelineError
from shiliu.logging_config import configure_logging
from shiliu.pipeline import PipelineService
from shiliu.retrieval.coordinator import ProjectionWorker
from shiliu.assistant.wiki_jobs import WikiProjectionWorker
from shiliu.retrieval import (
    HybridRetrievalService,
    QwenEmbeddingProvider,
    RetrievalIndexCoordinator,
    RetrievalService,
    SearchOrchestrator,
    SearchResultConsolidator,
    EvidenceEnricher,
    ProductSearchService,
    PgExactDenseIndex,
)
from shiliu.sync import SyncService, ProcessLock, SyncAlreadyRunning
from shiliu.evidence import EvidenceSearchService
from shiliu.runtime_modes import PRODUCT_RUNTIME_CONFIG
from shiliu.assistant.foundation import AssistantFoundation
from shiliu.assistant.dependencies import Context7MCPClient
from shiliu.assistant.provider import OpenAICompatibleAssistantProvider
from shiliu.assistant.runtime import AssistantRuntime
from shiliu.ask.deep.navigation import NavigationService
from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.deep.transcript import TranscriptSearchService, TranscriptWindowReader
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.research.inner_service import InnerResearchService
from shiliu.research.outer_service import OuterResearchService
from shiliu.research.inner_tools import LocalInnerToolAdapter
from shiliu.research.service import ResearchTaskService
from shiliu.research.control_service import ResearchControlService
from shiliu.research.product_service import ResearchProductService
from shiliu.research.provider_product import (
    ReceiptBoundDeepResearchExecutor,
    ReceiptBoundResearchProductOrchestrator,
)
from shiliu.research.provider_wiring import (
    ProviderPricePolicy,
    ReceiptBoundProviderService,
)
from shiliu.research.knowledge_service import ResearchKnowledgeService
from shiliu.research.recovery import ResearchRecoveryCoordinator
from shiliu.knowledge_draft import KnowledgeDraftService
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


logger = logging.getLogger(__name__)


class Application:
    PROJECTION_POLL_SECONDS = 1.0
    PROJECTION_ERROR_BACKOFF_SECONDS = 5.0

    def __init__(
        self, paths: AppPaths | None = None, *, config: AppConfig | None = None,
        postgres_config: PostgresConfig | None = None,
        context: ResourceContext | None = None,
        provider_factory: Callable[[str], Any] | None = None,
        assistant_provider_factory: Callable[[], Any] | None = None,
        extraction_provider_factory: Callable[[], Any] | None = None,
        embedding_provider: Any = None, adapter: Any = None,
        provider_availability: Callable[[], dict[str, Any]] | None = None,
        context7: Any = None,
    ) -> None:
        # Validate explicit database/artifact configuration before consulting
        # default paths, application config, credentials or any legacy files.
        self.postgres_config = postgres_config or load_postgres_config()
        self.context = context if context is not None else personal_context()
        self._closed = False
        self._closing = False
        self._started = False
        self._serve_lock = None
        self._workers: list[threading.Thread] = []
        self._worker_lock=threading.Lock()
        self._close_lock=threading.Lock()
        self._projection_stop = threading.Event()
        self._projection_thread: threading.Thread | None = None
        self._collection_projection: ProjectionWorker | None = None
        self._wiki_projection: WikiProjectionWorker | None = None
        self._projection_status: dict[str, dict[str, Any]] = {}

        self._provider_factory_override=provider_factory
        self._assistant_provider_factory_override=assistant_provider_factory
        self._extraction_provider_factory_override=extraction_provider_factory
        self._embedding_provider_override=embedding_provider
        self._provider_availability_override=provider_availability
        self._context7_override=context7
        self.pg = PgDatabase(self.postgres_config)
        try:
            self.pg.open()
            self.pg.validate_startup(revision=HEAD_REVISION,context=self.context)
            self._compose(paths,config,adapter)
        except BaseException:
            self.pg.close()
            self._closed=True
            raise

    def _compose(self, paths: AppPaths | None, config: AppConfig | None, adapter: Any) -> None:
        base_paths = paths or AppPaths.defaults()
        self.config = config if config is not None else load_config(base_paths)
        self.paths = base_paths.with_content_dir(Path(self.config.content_dir))
        self.paths.ensure()
        configure_logging(self.paths.logs_dir)
        self._projection_status = {
            "collection": {"state": "paused"},
            "wiki": {"state": "paused" if self.config.assistant_enabled else "disabled"},
        }
        self.db = Database(self.pg,self.context)
        self.research = ResearchTaskService(self.db)
        self._research_control: ResearchControlService | None = None
        self._research_inner: InnerResearchService | None = None
        self._research_outer: OuterResearchService | None = None
        self._research_product: ResearchProductService | None = None
        self._research_provider_inner: InnerResearchService | None = None
        self._research_provider_product: ResearchProductService | None = None
        self._research_provider_receipts: ReceiptBoundProviderService | None = None
        self._research_provider_orchestrator: (
            ReceiptBoundResearchProductOrchestrator | None
        ) = None
        self._research_recovery: ResearchRecoveryCoordinator | None = None
        self._provider_research_readiness: dict[str, str | bool] | None = None
        self._research_knowledge: ResearchKnowledgeService | None = None
        self._knowledge_drafts: KnowledgeDraftService | None = None
        self._assistant_foundation: AssistantFoundation | None = None
        self._assistant_runtime: AssistantRuntime | None = None
        self.adapter = adapter if adapter is not None else BilibiliAdapter(Path(self.config.bili_cli_root))
        self.artifacts = ArtifactStore(self.postgres_config.artifact_root,self.db)
        self.retrieval = RetrievalService(db=self.db, artifacts=self.artifacts)
        self._dense_retrieval: PgExactDenseIndex | None = None
        self._hybrid_retrieval: HybridRetrievalService | None = None
        self._search_orchestrator: SearchOrchestrator | None = None
        self._product_search: ProductSearchService | None = None
        self._ask_service: AskService | None = None
        self._stage5_pipeline: Stage5PipelineService | None = None
        self.runtime_config = PRODUCT_RUNTIME_CONFIG
        self.qwen_model_path = Path(
            os.environ.get(
                "SHILIU_QWEN_MODEL_PATH",
                str(Path.home() / "Library/Caches/Shiliu/model-selection/Qwen3-Embedding-0.6B"),
            )
        ).expanduser()
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        self.retrieval_coordinator = RetrievalIndexCoordinator(
            db=self.db,
            lexical=self.retrieval,
            dense_factory=lambda: self.dense_retrieval,
        )
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
        self.taxonomy_run_repository = TaxonomyRunRepository(
            self.db,self.artifacts,self.paths.content_dir / "taxonomy" / "runtime" / "runs",
        )
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

    def health(self) -> dict[str, Any]:
        """Read database and projection coverage without loading a model/key."""
        with self.db.connect(read_only=True) as connection:
            revision=connection.execute("SELECT version_num FROM alembic_version").fetchone()["version_num"]
            videos=connection.execute("SELECT count(*) AS n FROM videos WHERE workspace_id=%s",(self.context.workspace_id,)).fetchone()["n"]
        return {"ok":True,"storage":"postgresql","schema_revision":revision,
                "environment":self.postgres_config.environment,
                "started":self._started,"collection_videos":videos,
                "retrieval":self.retrieval.statistics(),
                "projection_maintenance":{
                    "running":self._projection_thread is not None and self._projection_thread.is_alive(),
                    **{domain:dict(value) for domain,value in self._projection_status.items()},
                },
                "assistant_enabled":self.config.assistant_enabled,
                "assistant_runtime":self._assistant_runtime.capabilities() if self._assistant_runtime else {"runtime":"stopped"}}

    def start(self, *, background_tasks: bool = True, local_projections_only: bool = False,
              manual_model_since: str | None = None) -> None:
        if self._closed or self._closing:
            raise RuntimeError("application_closed")
        if self._started:
            return
        lock=ProcessLock(self.paths.state_dir / "serve.lock")
        try:
            lock.__enter__()
            self._serve_lock=lock
            if not local_projections_only:
                try:
                    with ProcessLock(self.paths.sync_lock):
                        self.db.recover_stale_sync_runs()
                except SyncAlreadyRunning:
                    pass
                from shiliu.ask.persistence import AskRunStore
                AskRunStore(self.db).interrupt_running_on_startup()
            if self.config.assistant_enabled:
                self.assistant_runtime.local_projections_only=local_projections_only
                self.assistant_runtime.manual_model_since=manual_model_since
                self.assistant_runtime.maintenance_paused=local_projections_only or not background_tasks
                self.assistant_runtime.start()
            if background_tasks or local_projections_only:
                self._start_projection_maintenance()
            if background_tasks and not local_projections_only:
                self.research_recovery.start()
            self._started=True
        except BaseException:
            self.close()
            raise

    def _start_projection_maintenance(self) -> None:
        # One process-owned loop for the two existing local projection queues.
        # These workers retain their own PG claims, fences and renewal scopes.
        self._collection_projection = ProjectionWorker(self.retrieval, self.dense_retrieval)
        if self.config.assistant_enabled:
            self._wiki_projection = WikiProjectionWorker(
                self.assistant_runtime.wiki.retrieval,
                owner=f"wiki-projection-{os.getpid()}",
            )
        # Recovery is deterministic/local and completes before either claims.
        # Startup errors unwind through Application.close before pool disposal.
        self._collection_projection.recover()
        if self._wiki_projection is not None:
            self._wiki_projection.recover()
        self._projection_stop.clear()
        self._projection_thread = threading.Thread(
            target=self._projection_loop, name="shiliu-projections", daemon=False
        )
        self.start_worker(self._projection_thread)

    def _projection_loop(self) -> None:
        while not self._projection_stop.is_set():
            delay = self.PROJECTION_POLL_SECONDS
            try:
                result = self._collection_projection.run_one()
                self._record_projection_result("collection", result)
            except Exception as error:
                self._record_projection_error("collection", error)
                delay = self.PROJECTION_ERROR_BACKOFF_SECONDS
            if self._projection_stop.is_set():
                break
            if self._wiki_projection is not None:
                try:
                    # Wiki run_once deliberately does not recover; repeat safe
                    # recovery so another process's later expiry is not stranded.
                    self._wiki_projection.recover()
                    result = self._wiki_projection.run_once()
                    self._record_projection_result("wiki", result)
                except Exception as error:
                    self._record_projection_error("wiki", error)
                    delay = self.PROJECTION_ERROR_BACKOFF_SECONDS
            # Even persistent work/failure is bounded to one attempt per domain
            # per poll. not_before/attempt/profile remain the PG workers' policy.
            self._projection_stop.wait(delay)

    def _record_projection_result(self, domain: str, result: dict | None) -> None:
        if result is not None:
            self._projection_status[domain] = {
                "state": result["status"],
                "error": result.get("error_code") or result.get("reason"),
            }
        elif self._projection_status[domain]["state"] == "paused":
            self._projection_status[domain] = {"state": "polling"}

    def _record_projection_error(self, domain: str, error: Exception) -> None:
        category = error.category if isinstance(error, StorageError) else type(error).__name__
        self._projection_status[domain] = {"state": "unavailable", "error": category}
        logger.warning("%s projection poll unavailable: %s", domain, category)

    def start_worker(self, worker: threading.Thread) -> None:
        with self._worker_lock:
            if self._closed or self._closing:
                raise RuntimeError("application_stopping")
            self._workers=[value for value in self._workers if value.is_alive()]
            self._workers.append(worker)
            worker.start()

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._close_owned_resources()

    def _close_owned_resources(self) -> None:
        with self._worker_lock:
            self._closing=True
        # Signal every claimer before draining any transport.
        self._projection_stop.set()
        if self._research_recovery is not None:
            self._research_recovery.request_stop()
        if self._assistant_runtime is not None:
            self._assistant_runtime.request_stop()
        if self._ask_service is not None:
            self._ask_service.request_shutdown()
        if self._research_recovery is not None:
            self._research_recovery.stop()
            if self._research_recovery._thread is not None and self._research_recovery._thread.is_alive():
                raise RuntimeError("research_shutdown_timeout")
        if self._assistant_runtime is not None:
            self._assistant_runtime.stop()
            if self._assistant_runtime._thread is not None and self._assistant_runtime._thread.is_alive():
                raise RuntimeError("assistant_shutdown_timeout")
        if self._ask_service is not None:
            self._ask_service.shutdown(timeout=30)
        deadline=time.monotonic()+30
        for worker in self._workers:
            worker.join(timeout=max(0,deadline-time.monotonic()))
        if any(worker.is_alive() for worker in self._workers):
            raise RuntimeError("background_shutdown_timeout")
        self.pg.close()
        self._closed=True
        self._started=False
        if self._serve_lock is not None:
            self._serve_lock.__exit__(None,None,None)
            self._serve_lock=None

    def __enter__(self):
        if self._closed or self._closing:
            raise RuntimeError("application_closed")
        return self

    def __exit__(self,*args):
        self.close()

    @property
    def dense_retrieval(self) -> PgExactDenseIndex:
        if self._dense_retrieval is None:
            self._dense_retrieval = PgExactDenseIndex(
                db=self.db,
                provider=self._embedding_provider_override or QwenEmbeddingProvider(model_path=self.qwen_model_path),
                lexical=self.retrieval,
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
                answer_provider_factory=self.fast_answer_provider,
                deep_answer_provider_factory=self.deep_v2_answer_provider,
                deep_provider_factory=self.deep_v2_provider,
                deep_embedding_provider=self.dense_retrieval.provider,
                fast_f1=True,
                deep_reduce_strategy=self.config.deep_reduce_strategy,
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
                artifacts=self.artifacts,
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
    def assistant_foundation(self) -> AssistantFoundation:
        if not self.config.assistant_enabled:
            raise RuntimeError("assistant_disabled")
        if self._assistant_foundation is None:
            self._assistant_foundation = AssistantFoundation(
                db=self.db,
                paths=self.paths,
                artifacts=self.artifacts,
                adapter=self.adapter,
                product_search=self.product_search,
            )
        return self._assistant_foundation

    @property
    def assistant_runtime(self) -> AssistantRuntime:
        if not self.config.assistant_enabled:
            raise RuntimeError("assistant_disabled")
        if self._assistant_runtime is None:
            foundation = self.assistant_foundation
            self._assistant_runtime = AssistantRuntime(
                store=foundation.store,
                sources=foundation.sources,
                embedding_provider=self.dense_retrieval.provider,
                context7=self._context7_override or Context7MCPClient(),
                provider_factory=self.assistant_provider,
                extraction_provider_factory=self.assistant_extraction_provider,
            )
        return self._assistant_runtime

    def assistant_provider(self) -> OpenAICompatibleAssistantProvider:
        if self._assistant_provider_factory_override is not None:
            return self._assistant_provider_factory_override()
        try:
            api_key = load_api_key(self.config.api_key_ref)
        except RuntimeError as exc:
            raise PipelineError(str(exc), code="api_key_missing", retryable=False) from exc
        return OpenAICompatibleAssistantProvider(
            base_url=self.config.llm_base_url,
            api_key=api_key,
            model=self.config.model_for("assistant"),
            timeout_seconds=120,
        )

    def assistant_extraction_provider(self) -> OpenAICompatibleAssistantProvider:
        if self._extraction_provider_factory_override is not None:
            return self._extraction_provider_factory_override()
        if self._assistant_provider_factory_override is not None:
            return self._assistant_provider_factory_override()
        try:
            api_key = load_api_key(self.config.api_key_ref)
        except RuntimeError as exc:
            raise PipelineError(str(exc), code="api_key_missing", retryable=False) from exc
        return OpenAICompatibleAssistantProvider(
            base_url=self.config.llm_base_url,
            api_key=api_key,
            model=self.config.model_for("formal_summary"),
            timeout_seconds=120,
        )

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
            materializer = TranscriptEvidenceMaterializer(self.db, self.artifacts)
            evidence_search = EvidenceSearchService(
                db=self.db,
                product_search=self.product_search,
                artifacts=self.artifacts,
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
                authority=self.research_inner.authority,
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

    def provider_research_availability(self) -> dict[str, str | bool]:
        if self._provider_availability_override is not None:
            return dict(self._provider_availability_override())
        if self._provider_factory_override is not None:
            return {"available":True,"reason":"injected_provider"}
        roles = ("query_analysis", "agent_action", "grounded_answer")
        models = {self.config.model_for(role) for role in roles}
        if self.config.llm_base_url.rstrip("/") != "https://api.deepseek.com/v1":
            return {
                "available": False,
                "reason": "当前 Provider 地址没有已注册的 Research 费用策略。",
            }
        if models not in ({"deepseek-v4-pro"}, {"deepseek-v4-flash"}):
            return {
                "available": False,
                "reason": "当前 Research 模型没有已注册的 receipt / 费用策略。",
            }
        try:
            load_api_key(self.config.api_key_ref)
        except RuntimeError:
            return {
                "available": False,
                "reason": "尚未配置可用的模型凭据，请先在设置中完成连接。",
            }
        if self._provider_research_readiness is None:
            try:
                # Exercise the actual offline query path, including the pinned
                # Qwen runtime and dense-index identity, before any paid call.
                self.dense_retrieval.search(
                    "Research 本地语义检索就绪检查",
                    level="video",
                    top_k=1,
                )
            except StorageError:
                raise
            except Exception:
                self._provider_research_readiness = {
                    "available": False,
                    "reason": (
                        "本地语义检索模型或索引尚未就绪；"
                        "Research 已在 Provider 调用前停止。"
                    ),
                }
            else:
                self._provider_research_readiness = {
                    "available": True,
                    "reason": "Provider Research 与本地语义检索均已就绪。",
                }
        return dict(self._provider_research_readiness)

    @property
    def research_provider_inner(self) -> InnerResearchService:
        if self._research_provider_inner is None:
            base = self.research_inner
            self._research_provider_inner = InnerResearchService(
                db=self.db,
                kernel=self.research,
                tools=base.tools,
                materializer=base.materializer,
                provider_runs_authorized=True,
            )
        return self._research_provider_inner

    @property
    def research_provider_product(self) -> ResearchProductService:
        if self._research_provider_product is None:
            self._research_provider_product = ResearchProductService(
                db=self.db,
                kernel=self.research,
                inner=self.research_provider_inner,
                outer=self.research_outer,
                control=self.research_control,
                lease_seconds=60,
                lease_renew_every=None,
            )
        return self._research_provider_product

    @property
    def research_provider_receipts(self) -> ReceiptBoundProviderService:
        if self._research_provider_receipts is None:
            self._research_provider_receipts = ReceiptBoundProviderService(
                db=self.db,
                kernel=self.research,
                price_policy=ProviderPricePolicy.deployed(
                    base_url=self.config.llm_base_url.rstrip("/"),
                    model=self.config.model_for("grounded_answer"),
                    grounded_thinking_enabled=False,
                    grounded_reasoning_effort=None,
                ),
                role_token_caps={"grounded_answer": 8192},
                provider_dispatch_authorized=True,
            )
        return self._research_provider_receipts

    @property
    def research_provider_orchestrator(
        self,
    ) -> ReceiptBoundResearchProductOrchestrator:
        if self._research_provider_orchestrator is None:
            self._research_provider_orchestrator = (
                ReceiptBoundResearchProductOrchestrator(
                    db=self.db,
                    kernel=self.research,
                    inner=self.research_provider_inner,
                    product=self.research_provider_product,
                    receipt_service=self.research_provider_receipts,
                    provider_factory=self.research_provider,
                    deep_executor=ReceiptBoundDeepResearchExecutor(
                        db=self.db,
                        artifacts=self.artifacts,
                        product_search=self.product_search,
                        runtime_corpus_identity=self.runtime_config.corpus_identity,
                        budget=DeepSearchBudget(),
                    ),
                    provider_product_authorized=True,
                )
            )
        return self._research_provider_orchestrator

    @property
    def research_recovery(self) -> ResearchRecoveryCoordinator:
        if self._research_recovery is None:
            self._research_recovery = ResearchRecoveryCoordinator(self)
        return self._research_recovery

    def research_provider(self, role: str) -> OpenAICompatibleProvider:
        if self._provider_factory_override is not None:
            return self._provider_factory_override(role)
        if role not in {"query_analysis", "agent_action", "grounded_answer"}:
            raise PipelineError(
                "Research Provider role 未获授权",
                code="bad_provider_config",
                retryable=False,
            )
        try:
            api_key = load_api_key(self.config.api_key_ref)
        except RuntimeError as exc:
            raise PipelineError(
                str(exc), code="api_key_missing", retryable=False
            ) from exc
        return OpenAICompatibleProvider(
            base_url=self.config.llm_base_url,
            api_key=api_key,
            model=self.config.model_for(role),
            timeout_seconds=180,
            thinking_enabled=False,
            reasoning_effort=None,
            structured_transport_retries=0,
        )

    @property
    def research_knowledge(self) -> ResearchKnowledgeService:
        if self._research_knowledge is None:
            self._research_knowledge = ResearchKnowledgeService(
                db=self.db,
                kernel=self.research,
                product=self.research_product,
                retrieval=self.retrieval,
                taxonomy=self.taxonomy_corpus,
                export_root=self.paths.content_dir / "knowledge-exports",
            )
        return self._research_knowledge

    @property
    def knowledge_drafts(self) -> KnowledgeDraftService:
        if self._knowledge_drafts is None:
            self._knowledge_drafts = KnowledgeDraftService(
                db=self.db,
                product=self.research_product,
                knowledge=self.research_knowledge,
            )
        return self._knowledge_drafts

    def provider(self, role: str = "formal_summary") -> OpenAICompatibleProvider:
        if self._provider_factory_override is not None:
            return self._provider_factory_override(role)
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
        is_ask_light = role in {
            "query_analysis",
            "agent_action",
            "grounded_answer_recovery",
            "grounded_answer_fast",
            "grounded_answer_fast_recovery",
            "grounded_answer_deep",
            "grounded_answer_deep_recovery",
        }
        return OpenAICompatibleProvider(
            base_url=self.config.llm_base_url,
            api_key=api_key,
            model=self.config.model_for(role),
            timeout_seconds=180 if is_transcript or role in {
                "query_analysis", "agent_action", "grounded_answer",
                "grounded_answer_fast", "grounded_answer_fast_recovery",
                "grounded_answer_deep", "grounded_answer_deep_recovery",
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
                else "low" if role in {
                    "grounded_answer", "grounded_answer_deep"
                } else "high"
            ),
        )

    def fast_answer_provider(self, role: str) -> OpenAICompatibleProvider:
        mapped = {
            "grounded_answer": "grounded_answer_fast",
            "grounded_answer_recovery": "grounded_answer_fast_recovery",
        }
        return self.provider(mapped[role])

    def deep_v2_provider(self, role: str) -> OpenAICompatibleProvider:
        if self._provider_factory_override is not None:
            return self._provider_factory_override(role)
        provider = self.provider(role)
        provider.model = "deepseek-v4-flash"
        provider.thinking_enabled = False
        provider.reasoning_effort = None
        provider.timeout_seconds = 180
        return provider

    def deep_v2_answer_provider(self, role: str) -> OpenAICompatibleProvider:
        return self.deep_v2_provider({"grounded_answer": "grounded_answer_deep",
            "grounded_answer_recovery": "grounded_answer_deep_recovery"}[role])

    def deep_answer_provider(self, role: str) -> OpenAICompatibleProvider:
        mapped = {
            "grounded_answer": "grounded_answer_deep",
            "grounded_answer_recovery": "grounded_answer_deep_recovery",
        }
        return self.provider(mapped[role])

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
