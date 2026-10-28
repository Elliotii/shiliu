"""Reuse the guarded random BM25 child, with Application's actual pool defaults.

The lexical-only fixture's max_size=1 is a diagnostic control, not an Agent pool.
This helper never touches shared fixture settings or the original smoke evidence.
"""
from contextlib import contextmanager
import shutil

from test_collection_bm25_product import resources as lexical_resources
from research.postgres_eval.bm25_product import ROOT, admin
from psycopg.conninfo import conninfo_to_dict
from shiliu.artifacts import ArtifactStore
from shiliu.db import Database
from shiliu.retrieval.service import RetrievalService
from shiliu.storage.postgres import PgDatabase, PoolSettings
from shiliu.storage.scope import personal_context


@contextmanager
def assistant_agent_resources(*, single_connection_control=False, cleanup_receipt=None):
    """Only max_size differs for the control; all timeouts remain unchanged."""
    fixture = lexical_resources.__wrapped__()
    root = name = None
    try:
        old_db, old_artifacts, _, _ = next(fixture)
        config, root = old_db.pg.config, old_artifacts.root
        name = conninfo_to_dict(config.database_url)["dbname"]
        assert name.startswith("shiliu_bm25_fixture_")
        old_db.pg.close()
        settings = PoolSettings(max_size=1) if single_connection_control else PoolSettings()
        with PgDatabase(config, settings=settings) as pg:
            db = Database(pg, personal_context())
            artifacts = ArtifactStore(root, db)
            yield db, artifacts, RetrievalService(db=db, artifacts=artifacts)
    finally:
        try:
            fixture.close()  # closes the original pool and drops only its random DB
        finally:
            if root is not None:
                assert root.parent == ROOT / "fixture-artifacts" and root.name == name
                if root.exists():
                    shutil.rmtree(root)
            if name is not None:
                with admin("shiliu_bm25_fixture") as conn:
                    assert not conn.execute("SELECT datname FROM pg_database WHERE datname=%s", (name,)).fetchall()
                if cleanup_receipt:
                    cleanup_receipt({"database": name, "dropped": True, "artifacts_removed": True})
