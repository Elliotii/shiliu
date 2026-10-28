"""Offline rebuild preserves imported history and never claims paid Jobs."""

import psycopg
import pytest
from full_source import make_full_source
from schema_support import formal_target
from test_etl import target_etl
from test_collection_retrieval import FixedProvider
from shiliu.config import LIBPQ_DISABLED_PASSFILE, load_postgres_config
from shiliu.migration.etl import import_snapshot, validate_snapshot
from shiliu.migration.rebuild import rebuild_snapshot
from shiliu.migration.values import MigrationRejected


def test_rebuild_none_resume_then_model_recovery_preserves_history():
    source = make_full_source()
    with formal_target(load_postgres_config()) as (runtime, admin):
        target = target_etl(runtime)
        initial = import_snapshot(source, target, "w14_rebuild")
        with pytest.raises(MigrationRejected, match="injected_rebuild_interruption"):
            rebuild_snapshot(source, target, "w14_rebuild", _fault_after_batches=1)
        with pytest.raises(MigrationRejected, match="rebuild_incomplete"):
            validate_snapshot(source, target, "w14_rebuild")
        lexical = rebuild_snapshot(source, target, "w14_rebuild")
        assert lexical["rebuild"]["dense_state"] == "unavailable"
        assert lexical["rebuild"]["model_available"] is False
        assert (
            lexical["rebuild"]["memory_missing"] == lexical["rebuild"]["memory_active"]
        )
        assert rebuild_snapshot(source, target, "w14_rebuild") == lexical
        dense = rebuild_snapshot(
            source, target, "w14_rebuild", provider=FixedProvider()
        )
        assert (
            dense["rebuild"]["model_available"]
            and dense["rebuild"]["dense_state"] == "current"
        )
        assert (
            dense["rebuild"]["memory_missing"]
            == dense["rebuild"]["collection_dense_missing"]
            == 0
        )
        for name in (
            "research_tasks",
            "research_checkpoints",
            "research_side_effects",
            "assistant_messages",
            "assistant_task_notes",
            "assistant_jobs",
            "assistant_model_budget_days",
            "ask_runs",
        ):
            assert dense["counts"][name] == initial["counts"][name]
            assert dense["logical_hashes"][name] == initial["logical_hashes"][name]
        assert validate_snapshot(source, target, "w14_rebuild") == dense
        with psycopg.connect(admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as c:
            assert c.execute(
                "SELECT count(*) FROM shiliu.model_dispatch_receipts"
            ).fetchone() == (0,)
            assert (
                c.execute(
                    "SELECT count(*) FROM shiliu.migration_exceptions"
                ).fetchone()[0]
                >= 1
            )
            c.execute("UPDATE shiliu.retrieval_units SET tokenized_text='tampered'")
        with pytest.raises(
            MigrationRejected, match="different_payload|snapshot_changed"
        ):
            validate_snapshot(source, target, "w14_rebuild")


def test_full_table_rebuilt_pair_restores_to_independent_database_and_root():
    import uuid
    from shiliu.migration.safety import TASK_ROOT
    from shiliu.migration.backup import create_pair, restore_pair, verify_pair

    source = make_full_source()
    with formal_target(load_postgres_config()) as (runtime, admin):
        target = target_etl(runtime)
        import_snapshot(source, target, "w14_pair")
        report = rebuild_snapshot(source, target, "w14_pair", provider=FixedProvider())
        directory = TASK_ROOT / "backups" / ("w14_pair_" + uuid.uuid4().hex[:10])
        pair = create_pair(source, target, "w14_pair", directory)
        with formal_target(load_postgres_config(), revisions=()) as (runtime2, admin2):
            target2 = target_etl(runtime2)
            restore_pair(directory, admin2, target2)
            restored = validate_snapshot(source, target2, "w14_pair")
            assert restored == report == pair["validation"]
            assert (
                target2.database_url != target.database_url
                and target2.artifact_root != target.artifact_root
            )
            with psycopg.connect(
                admin2.database_url, passfile=LIBPQ_DISABLED_PASSFILE
            ) as c:
                with pytest.raises(psycopg.errors.CheckViolation):
                    with c.transaction():
                        c.execute("DELETE FROM shiliu.research_workspace_records")
                with pytest.raises(psycopg.errors.ForeignKeyViolation):
                    with c.transaction():
                        c.execute(
                            "UPDATE shiliu.assistant_memories SET workspace_id='missing-owner'"
                        )
            from shiliu.storage.postgres import PgDatabase

            with PgDatabase(runtime2) as db:
                with pytest.raises(Exception) as denied:
                    with db.read() as c:
                        c.execute("SELECT * FROM shiliu_migration.rebuild_receipts")
                assert getattr(denied.value, "sqlstate", None) == "42501"
        artifact = next((directory / "artifacts").rglob("*.json"), None)
        if artifact is None:
            item = pair["artifacts"][0]
            artifact = directory / "artifacts" / item["relative_key"]
        artifact.write_bytes(b"corrupted synthetic backup")
        with pytest.raises(MigrationRejected, match="backup_artifact_hash_mismatch"):
            verify_pair(directory)


def test_offline_rebuild_publishes_generation_fence_for_exact_citations():
    import sqlite3
    from shiliu.storage.postgres import PgDatabase
    from shiliu.storage.scope import personal_context
    from shiliu.db import Database
    from shiliu.artifacts import ArtifactStore
    from shiliu.evidence.authority import bind_live_current_version
    from shiliu.ask.evidence import _reference

    source = make_full_source()
    with sqlite3.connect(source) as c:
        c.execute("UPDATE retrieval_sync_state SET desired_state='indexed',lexical_state='current',dense_state='current'")
        c.execute("UPDATE favorite_sources SET status='active'")
        c.execute("UPDATE video_source_memberships SET video_id=1,bvid=(SELECT source_id FROM videos WHERE id=1)")
    with formal_target(load_postgres_config()) as (runtime, admin):
        target = target_etl(runtime)
        import_snapshot(source, target, "w14_citation_ready")
        rebuilt = rebuild_snapshot(source, target, "w14_citation_ready", provider=FixedProvider())
        assert rebuilt["rebuild"]["status"] == "ready"
        with PgDatabase(runtime) as pg:
            db = Database(pg, personal_context())
            artifacts = ArtifactStore(target.artifact_root, db)
            video = db.get_video(1)
            binding = bind_live_current_version(_reference(video), db=db, video_id=1, artifacts=artifacts)
            assert len(binding.source_version) == 64
            with db.connect(read_only=True) as c:
                task = c.execute("SELECT requested_generation,payload FROM retrieval_projection_tasks WHERE domain='collection' AND resource_key='1'").fetchone()
            assert task["payload"]["ready_generation"] == task["requested_generation"]
            assert task["payload"]["ready_profile"] == rebuilt["rebuild"]["profiles"]["collection"]
