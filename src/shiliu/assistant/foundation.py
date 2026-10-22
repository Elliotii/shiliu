from __future__ import annotations

from shiliu.artifacts import ArtifactStore
from shiliu.assistant.schema import initialize_assistant_foundation_schema
from shiliu.assistant.snapshots import SourceSnapshotStore
from shiliu.assistant.sources import CollectionSourceService
from shiliu.assistant.store import AssistantRunStore
from shiliu.bilibili import BilibiliAdapter
from shiliu.config import AppPaths
from shiliu.db import Database
from shiliu.retrieval.product_search import ProductSearchService


class AssistantFoundation:
    """Feature-gated Stage-A assembly; no worker, chat loop, Memory UI, or Wiki."""

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
        with db.connect() as connection:
            initialize_assistant_foundation_schema(connection)
        snapshots = SourceSnapshotStore(db, artifacts, paths.assistant_content_dir)
        self.store = AssistantRunStore(db)
        self.sources = CollectionSourceService(
            db=db,
            artifacts=artifacts,
            snapshots=snapshots,
            product_search=product_search,
            metadata_adapter=adapter,
        )
