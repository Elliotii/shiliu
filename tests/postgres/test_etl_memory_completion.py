"""W14 forgotten cleanup completion is atomic, auditable and replay-stable."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import uuid

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest

from poc_source import make_source
from schema_support import formal_target
from test_collection_retrieval import FixedProvider
from test_etl import target_etl
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.memory_jobs import MemoryJobWorker
from shiliu.config import LIBPQ_DISABLED_PASSFILE, load_postgres_config
from shiliu.db import Database
from shiliu.migration.backup import create_pair, restore_pair
from shiliu.migration.etl import import_snapshot, validate_snapshot
from shiliu.migration.rebuild import rebuild_snapshot
from shiliu.migration.safety import TASK_ROOT
from shiliu.migration.snapshot import inspect_snapshot, sha
from shiliu.migration.states import FORGOTTEN_PURGE_COMPLETION
from shiliu.migration.values import MigrationRejected
from shiliu.storage.postgres import PgDatabase
from shiliu.storage.scope import personal_context


def test_forgotten_purge_completion_preserves_audit_reentry_and_paired_restore():
    source = make_source()
    with closing(sqlite3.connect(source)) as c, c:
        c.row_factory = sqlite3.Row
        c.execute(
            "UPDATE assistant_jobs SET status='running',lease_owner='old-owner',"
            "lease_until='2026-10-23T01:00:00+00:00',last_error_code='old-error',"
            "last_error_message='old-audit',completed_at=NULL "
            "WHERE kind='memory_purge'"
        )
        original = dict(
            c.execute(
                "SELECT * FROM assistant_jobs WHERE kind='memory_purge'"
            ).fetchone()
        )
    source_hash = sha(source)
    identity, _ = inspect_snapshot(source)
    assert (
        identity["state_dispositions"]["assistant_jobs"][FORGOTTEN_PURGE_COMPLETION]
        == 1
    )
    assert (
        identity["state_dispositions"]["assistant_jobs"][
            "block_legacy_payload_pg_projection_only"
        ]
        == 1
    )
    run = "w14_memory_completion"
    with formal_target(load_postgres_config()) as (runtime, admin):
        target = target_etl(runtime)
        imported = import_snapshot(source, target, run)
        assert import_snapshot(source, target, run) == imported
        lexical = rebuild_snapshot(source, target, run)
        assert lexical["rebuild"]["memory_missing"] > 0
        assert lexical["rebuild"]["dense_state"] == "unavailable"

        def audit():
            with psycopg.connect(
                target.database_url,
                passfile=LIBPQ_DISABLED_PASSFILE,
                row_factory=dict_row,
            ) as c:
                jobs = c.execute(
                    "SELECT * FROM shiliu.assistant_jobs ORDER BY id"
                ).fetchall()
                staged = c.execute(
                    "SELECT data FROM shiliu_migration.rows WHERE run_id=%s AND table_name='assistant_jobs' AND data->>'id'=%s",
                    (run, original["id"]),
                ).fetchone()["data"]
                assert {
                    k: v for k, v in staged.items() if k != "__source_rowid"
                } == original
                totals = {
                    name: c.execute(
                        "SELECT count(*) AS n FROM shiliu." + name
                    ).fetchone()["n"]
                    for name in (
                        "assistant_jobs",
                        "assistant_memory_changes",
                        "assistant_run_events",
                        "model_dispatch_receipts",
                        "migration_batches",
                    )
                }
                return jobs, totals

        before = audit()
        purge = next(j for j in before[0] if j["kind"] == "memory_purge")
        active = next(j for j in before[0] if j["kind"] == "memory_index")
        assert purge["status"] == "completed" and purge["completed_at"] is not None
        assert purge["lease_owner"] is purge["lease_until"] is None
        assert purge["last_error_code"] is purge["last_error_message"] is None
        for key in (
            "principal_id",
            "attempt",
            "lease_epoch",
            "not_before",
            "proposal_json",
            "created_at",
        ):
            expected = (
                identity["ownership"]["default_principal"]
                if key == "principal_id"
                else original[key]
            )
            if key in {"not_before", "created_at"}:
                expected = datetime.fromisoformat(expected)
            elif key == "proposal_json" and expected is not None:
                expected = json.loads(expected)
            assert purge[key] == expected
        completion = purge["payload_json"]["migration_completion"]
        assert completion == {
            "policy": FORGOTTEN_PURGE_COMPLETION,
            "time_basis": "max_source_job_and_memory_updated_at",
            "audit_anchor": purge["completed_at"].astimezone(timezone.utc).isoformat(),
        }
        assert active["status"] == "blocked"
        assert active["last_error_code"] == "migration_projection_pending"
        assert "migration_completion" not in active["payload_json"]
        assert before[1]["model_dispatch_receipts"] == 0
        with PgDatabase(runtime) as pg:
            worker = MemoryJobWorker(
                MemoryService(Database(pg, personal_context()), provider=None),
                owner="repair-check",
            )
            assert worker.run_once() is None
        assert import_snapshot(source, target, run) == lexical
        assert rebuild_snapshot(source, target, run) == lexical
        assert audit() == before  # No second completion/event/attempt or claim.
        dense = rebuild_snapshot(source, target, run, provider=FixedProvider())
        assert dense["rebuild"]["memory_missing"] == 0
        assert audit() == before
        assert validate_snapshot(source, target, run) == dense
        directory = (
            TASK_ROOT / "backups" / ("w14_memory_completion_" + uuid.uuid4().hex[:10])
        )
        pair = create_pair(source, target, run, directory)
        with formal_target(load_postgres_config(), revisions=()) as (runtime2, admin2):
            target2 = target_etl(runtime2)
            restore_pair(directory, admin2, target2)
            assert (
                validate_snapshot(source, target2, run) == dense == pair["validation"]
            )
        # Canonical validation still rejects an invented completion audit.
        with psycopg.connect(admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as c:
            c.execute(
                "UPDATE shiliu.assistant_jobs SET payload_json=%s WHERE id=%s",
                (
                    Jsonb(
                        {
                            **purge["payload_json"],
                            "migration_completion": {"policy": "tampered"},
                        }
                    ),
                    purge["id"],
                ),
            )
        with pytest.raises(
            MigrationRejected, match="same_primary_key_different_payload"
        ):
            validate_snapshot(source, target, run)
        # The new policy is bound only for this affected input; an old-policy
        # receipt cannot silently be reused for the newly completed payload.
        previous_identity = {
            k: v
            for k, v in identity.items()
            if k not in {"manifest_hash", "_descriptor_index"}
        }
        previous_identity["state_dispositions"] = {
            **identity["state_dispositions"],
            "assistant_jobs": {"block_legacy_payload_pg_projection_only": 2},
        }
        previous_hash = hashlib.sha256(
            json.dumps(
                previous_identity, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        assert previous_hash != identity["manifest_hash"]
        with psycopg.connect(admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as c:
            c.execute(
                "UPDATE shiliu.migration_runs SET source_manifest_hash=%s WHERE run_id=%s",
                (previous_hash, run),
            )
        with pytest.raises(
            MigrationRejected, match="migration_input_identity_conflict"
        ):
            import_snapshot(source, target, run)
        assert audit()[1] == before[1]
    assert sha(source) == source_hash
