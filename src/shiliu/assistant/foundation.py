from __future__ import annotations

from shiliu.artifacts import ArtifactStore
from shiliu.assistant.snapshots import SourceSnapshotStore
from shiliu.assistant.sources import CollectionSourceService
from shiliu.assistant.pg_store import PgAssistantRunStore
from shiliu.bilibili import BilibiliAdapter
from shiliu.config import AppPaths
from shiliu.db import Database
from shiliu.retrieval.product_search import ProductSearchService


class AssistantFoundation:
    """Scoped PG composition; migrations and pool ownership belong to the caller."""

    def __init__(
        self,
        *,
        db: Database,
        paths: AppPaths,
        artifacts: ArtifactStore,
        adapter: BilibiliAdapter,
        product_search: ProductSearchService,
    ) -> None:
        self.db = db
        self.paths = paths
        snapshots = SourceSnapshotStore(db, artifacts, paths.assistant_content_dir)
        self.store = PgAssistantRunStore(db)
        self.sources = CollectionSourceService(
            db=db,
            artifacts=artifacts,
            snapshots=snapshots,
            product_search=product_search,
            metadata_adapter=adapter,
        )
