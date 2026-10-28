"""Offline local projections only: no Application, paid job claims or providers.

Collection units/PKs and frozen historical JSON remain intact. Memory never uses
legacy BGE payloads; Wiki uses the existing effective-window projection worker.
"""

from __future__ import annotations
from dataclasses import asdict
from hashlib import sha256
from types import SimpleNamespace
import unicodedata

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from shiliu.migration.safety import guard, guard_input_target
from shiliu.migration.snapshot import plan_snapshot, mapping
from shiliu.migration.values import MigrationRejected
from shiliu.migration.projection_state import POLICY, receipt, capture
from shiliu.migration.etl import _connect, validate_snapshot, _root_contract


def batches(db, table, key):
    last = None
    while True:
        with db.connect(read_only=True) as c:
            query = sql.SQL("SELECT * FROM shiliu.{} WHERE workspace_id=%s").format(
                sql.Identifier(table)
            )
            values = [db.workspace_id]
            if last is not None:
                query += sql.SQL(" AND {}>%s").format(sql.Identifier(key))
                values.append(last)
            query += sql.SQL(" ORDER BY {} LIMIT 128").format(sql.Identifier(key))
            rows = c.execute(query, values).fetchall()
        if not rows:
            return
        yield rows
        last = rows[-1][key]


def rebuild_snapshot(
    source, config, run_id, *, provider=None, _fault_after_batches=None
):
    guard(config, etl=True)
    guard_input_target(source, config)
    identity, _ = plan_snapshot(source)
    from shiliu.storage.embedding_profiles import DocumentProfile
    from shiliu.retrieval.dense import PgExactDenseIndex, _validate_vector
    from shiliu.retrieval.lexical import F1Tokenizer
    from shiliu.retrieval.service import RetrievalService
    from shiliu.storage.postgres import PgDatabase, PoolSettings
    from shiliu.storage.scope import ResourceContext
    from shiliu.db import Database
    from shiliu.artifacts import ArtifactStore
    from shiliu.assistant.memory import MemoryService
    from shiliu.assistant.pg_access import PgAssistantAccess
    from shiliu.assistant.snapshots import SourceSnapshotStore
    from shiliu.assistant.sources import CollectionSourceService
    from shiliu.assistant.wiki import WikiService
    from shiliu.assistant.wiki_retrieval import WikiHybridIndex, PROJECTION_VERSION
    from shiliu.assistant.wiki_jobs import WikiProjectionWorker
    from shiliu.retrieval.dense import provider_identity

    signature = asdict(provider_identity(provider)) if provider else None
    if provider and not identity["provenance"]["synthetic_only"]:
        from shiliu.retrieval.qwen import QWEN_MODEL_ID, QWEN_MODEL_REVISION

        if (
            signature["model_id"] != QWEN_MODEL_ID
            or signature["model_revision"] != QWEN_MODEL_REVISION
        ):
            raise MigrationRejected("historical_rebuild_requires_pinned_qwen")
    profiles = (
        {}
        if provider is None
        else {
            "memory": DocumentProfile(provider, "memory-text-v1").profile_id,
            "wiki": DocumentProfile(provider, PROJECTION_VERSION).profile_id,
        }
    )
    with _connect(config) as control:
        control.autocommit = True
        if not control.execute(
            "SELECT pg_try_advisory_lock(198023,4) AS ok"
        ).fetchone()["ok"]:
            raise MigrationRejected("migration_already_active")
        try:
            validate_snapshot(source, config, run_id, _allow_rebuild_incomplete=True)
            with _connect(config) as c:
                _root_contract(c)
                old = receipt(c, run_id)
                if (
                    old
                    and old["status"] == "ready"
                    and old["details"]["provider"] == signature
                ):
                    return validate_snapshot(source, config, run_id)
                c.execute(
                    "CREATE TABLE IF NOT EXISTS shiliu_migration.rebuild_receipts "
                    "(run_id text PRIMARY KEY,source_manifest_hash text NOT NULL,policy_version text NOT NULL,status text NOT NULL,details jsonb NOT NULL)"
                )
                c.execute(
                    "INSERT INTO shiliu_migration.rebuild_receipts VALUES(%s,%s,%s,'building',%s) ON CONFLICT(run_id) DO UPDATE SET status='building',details=excluded.details,policy_version=excluded.policy_version",
                    (
                        run_id,
                        identity["manifest_hash"],
                        POLICY,
                        Jsonb({"provider": signature, "profiles": profiles}),
                    ),
                )
                c.execute(
                    "UPDATE shiliu.migration_runs SET status='validating' WHERE run_id=%s",
                    (run_id,),
                )
            summary = {
                "model_available": provider is not None,
                "collection_units": 0,
                "memory_rows": 0,
                "wiki_effective_windows": 0,
                "wiki_current_windows": 0,
                "wiki_failed_tasks": 0,
                "collection_dense_missing": 0,
                "memory_active": 0,
                "memory_current": 0,
                "memory_missing": 0,
                "scope": "default effective Space projections; task variants remain on-demand",
            }
            tokenizer = F1Tokenizer(config.artifact_root / "tokenizer-cache")
            completed = 0

            def checkpoint():
                nonlocal completed
                completed += 1
                if _fault_after_batches == completed:
                    raise MigrationRejected("injected_rebuild_interruption")

            with PgDatabase(
                config, settings=PoolSettings(min_size=1, max_size=4)
            ) as pg:
                for owner, workspace in identity["ownership"]["principals"].items():
                    db = Database(pg, ResourceContext(workspace, owner))
                    artifacts = ArtifactStore(config.artifact_root, db)
                    lexical = RetrievalService(db=db, artifacts=artifacts)
                    dense = (
                        PgExactDenseIndex(db=db, provider=provider, lexical=lexical)
                        if provider
                        else None
                    )
                    if dense:
                        profiles["collection"] = dense.profile_id
                        dense.register()
                    for rows in batches(db, "retrieval_units", "unit_id"):
                        represented = [SimpleNamespace(**r) for r in rows]
                        vectors = dense.encode(represented) if dense else None
                        tokens = {
                            r["unit_id"]: tokenizer.document(r["search_text"])
                            for r in rows
                        }
                        with db.connect(guard=True) as c:
                            for r in rows:
                                result = c.execute(
                                    "UPDATE retrieval_units SET tokenized_text=%s,search_vector=to_tsvector('simple',%s) WHERE workspace_id=%s AND unit_id=%s AND content_hash=%s AND generation=%s AND search_text=%s",
                                    (
                                        tokens[r["unit_id"]],
                                        tokens[r["unit_id"]],
                                        workspace,
                                        r["unit_id"],
                                        r["content_hash"],
                                        r["generation"],
                                        r["search_text"],
                                    ),
                                )
                                if result.rowcount != 1:
                                    raise MigrationRejected("collection_rebuild_stale")
                                c.execute(
                                    "INSERT INTO retrieval_projection_tasks(workspace_id,domain,resource_key,requested_generation,payload,status,not_before,created_at,updated_at) "
                                    "VALUES(%s,'collection',%s,%s,%s,'completed',clock_timestamp(),clock_timestamp(),clock_timestamp()) "
                                    "ON CONFLICT(workspace_id,domain,resource_key) DO UPDATE SET requested_generation=excluded.requested_generation,payload=excluded.payload,status='completed',lease_owner=NULL,lease_until=NULL,updated_at=clock_timestamp()",
                                    (
                                        workspace,
                                        str(r["video_id"]),
                                        r["generation"],
                                        Jsonb(
                                            {
                                                "reason": "migration_preserved_units",
                                                "migration_run_id": run_id,
                                                "ready_generation": r["generation"],
                                                **({"ready_profile": dense.profile_id} if dense else {}),
                                                "lexical_profile": tokenizer.profile,
                                                "dense_state": "current"
                                                if dense
                                                else "missing",
                                            }
                                        ),
                                    ),
                                )
                            if dense:
                                dense.publish(
                                    c, represented, vectors, rows[0]["generation"]
                                )
                        summary["collection_units"] += len(rows)
                        checkpoint()
                    if dense:
                        with db.connect(read_only=True) as c:
                            missing = dense._coverage(c)
                        summary["collection_dense_missing"] += missing
                        if not missing:
                            dense.activate()
                    memories = MemoryService(db, provider=provider, principal_id=owner)
                    if provider:
                        with db.connect() as c:
                            memories.profile.register(c)
                    for rows in batches(db, "assistant_memories", "id"):
                        if any(r["principal_id"] != owner for r in rows):
                            raise MigrationRejected("memory_rebuild_owner_mismatch")
                        active = [r for r in rows if r["status"] == "active"]
                        texts = [
                            unicodedata.normalize("NFKC", r["text"]) for r in active
                        ]
                        vectors = (
                            [
                                _validate_vector(v, 512)
                                for v in provider.embed_documents(texts)
                            ]
                            if provider and active
                            else []
                        )
                        if provider and len(vectors) != len(active):
                            raise MigrationRejected("memory_embedding_count_mismatch")
                        with db.connect(guard=True) as c:
                            if provider:
                                memories.profile.register(c)
                            for r in rows:
                                words = (
                                    tokenizer.document(r["text"])
                                    if r["status"] == "active"
                                    else ""
                                )
                                changed = c.execute(
                                    "UPDATE assistant_memories SET tokenized_text=%s,search_vector=to_tsvector('simple',%s) WHERE workspace_id=%s AND principal_id=%s AND id=%s AND version=%s AND change_epoch=%s AND text=%s AND status=%s",
                                    (
                                        words,
                                        words,
                                        workspace,
                                        owner,
                                        r["id"],
                                        r["version"],
                                        r["change_epoch"],
                                        r["text"],
                                        r["status"],
                                    ),
                                )
                                if changed.rowcount != 1:
                                    raise MigrationRejected("memory_rebuild_stale")
                            for r, text, vector in zip(active, texts, vectors):
                                c.execute(
                                    "INSERT INTO memory_embeddings(workspace_id,memory_id,profile_id,memory_version,change_epoch,embedding_text_hash,embedding,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,clock_timestamp()) "
                                    "ON CONFLICT(memory_id,profile_id) DO UPDATE SET memory_version=excluded.memory_version,change_epoch=excluded.change_epoch,embedding_text_hash=excluded.embedding_text_hash,embedding=excluded.embedding,updated_at=excluded.updated_at",
                                    (
                                        workspace,
                                        r["id"],
                                        memories.profile.profile_id,
                                        r["version"],
                                        r["change_epoch"],
                                        sha256(text.encode()).hexdigest(),
                                        vector,
                                    ),
                                )
                                c.execute(
                                    "UPDATE assistant_memories SET last_projected_version=%s WHERE workspace_id=%s AND id=%s",
                                    (r["version"], workspace, r["id"]),
                                )
                        summary["memory_rows"] += len(rows)
                        checkpoint()
                    with db.connect(read_only=True) as c:
                        active_count = c.execute(
                            "SELECT count(*) AS n FROM assistant_memories WHERE workspace_id=%s AND principal_id=%s AND status='active'",
                            (workspace, owner),
                        ).fetchone()["n"]
                        current_count = c.execute(
                            "SELECT count(*) AS n FROM assistant_memories m JOIN memory_embeddings e ON e.workspace_id=m.workspace_id AND e.memory_id=m.id AND e.memory_version=m.version AND e.change_epoch=m.change_epoch WHERE m.workspace_id=%s AND m.principal_id=%s AND m.status='active' AND e.profile_id=%s AND e.embedding_text_hash=encode(sha256(convert_to(normalize(m.text,NFKC),'UTF8')),'hex')",
                            (
                                workspace,
                                owner,
                                memories.profile.profile_id if provider else None,
                            ),
                        ).fetchone()["n"]
                    summary["memory_active"] += active_count
                    summary["memory_current"] += current_count
                    summary["memory_missing"] += active_count - current_count
                    if provider:
                        with db.connect(guard=True) as c:
                            memories._activate_profile_if_covered(c)
                    access = PgAssistantAccess(db)
                    sources = CollectionSourceService(
                        db=db,
                        artifacts=artifacts,
                        snapshots=SourceSnapshotStore(db, artifacts),
                    )
                    wiki = WikiService(
                        db=db, store=access, sources=sources, principal_id=owner
                    )
                    index = WikiHybridIndex(provider, wiki=wiki)
                    worker = (
                        WikiProjectionWorker(index, owner="migration:" + run_id)
                        if provider
                        else None
                    )
                    for space in access.list_spaces():
                        snapshot = index.projections.capture(space["id"])
                        entries = index.windows(snapshot)
                        summary["wiki_effective_windows"] += len(entries)
                        if worker and entries:
                            index.enqueue(snapshot, entries, space_id=space["id"])
                            # Only local embedding intents in this isolated target;
                            # never Assistant/Research/ASR/model-maintenance Jobs.
                            for _ in range(len(snapshot["pages"]) + 1):
                                if worker.run_once() is None:
                                    break
                            with db.connect(read_only=True) as c:
                                summary["wiki_current_windows"] += len(
                                    index._current_rows(
                                        c, entries, index.profile.profile_id
                                    )
                                )
                        checkpoint()
                    with db.connect(read_only=True) as c:
                        summary["wiki_failed_tasks"] += c.execute(
                            "SELECT count(*) AS n FROM retrieval_projection_tasks WHERE workspace_id=%s AND domain='wiki' AND status='failed'",
                            (workspace,),
                        ).fetchone()["n"]
            if provider is None:
                summary["collection_dense_missing"] = summary["collection_units"]
            summary["dense_state"] = (
                "unavailable"
                if provider is None
                else "partial"
                if summary["collection_dense_missing"]
                or summary["memory_missing"]
                or summary["wiki_failed_tasks"]
                or summary["wiki_current_windows"] != summary["wiki_effective_windows"]
                else "current"
            )
            with _connect(config) as c:
                details = {
                    "provider": signature,
                    "profiles": profiles,
                    "summary": summary,
                }
                c.execute(
                    "UPDATE shiliu_migration.rebuild_receipts SET details=%s WHERE run_id=%s",
                    (Jsonb(details), run_id),
                )
            # Verify formal history before taking immutable post-rebuild digests.
            validate_snapshot(source, config, run_id, _allow_rebuild_incomplete=True)
            with _connect(config) as c:
                details["table_snapshots"] = capture(c, mapping()["tables"])
                c.execute(
                    "UPDATE shiliu_migration.rebuild_receipts SET status='ready',details=%s WHERE run_id=%s",
                    (Jsonb(details), run_id),
                )
            result = validate_snapshot(source, config, run_id)
            with _connect(config) as c:
                c.execute(
                    "UPDATE shiliu.migration_runs SET status='ready' WHERE run_id=%s",
                    (run_id,),
                )
            return result
        except Exception as error:
            from shiliu.retrieval.qwen import LocalModelNotReadyError

            category = (
                str(error)
                if isinstance(error, MigrationRejected)
                else "offline_embedding_unavailable"
                if isinstance(error, LocalModelNotReadyError)
                else "rebuild_database_" + str(error.sqlstate)
                if isinstance(error, psycopg.Error)
                else "rebuild_" + type(error).__name__
            )
            try:
                with _connect(config) as audit:
                    if audit.execute(
                        "SELECT 1 FROM migration_runs WHERE run_id=%s", (run_id,)
                    ).fetchone():
                        audit.execute(
                            "INSERT INTO migration_exceptions(run_id,table_name,record_key,category,disposition,created_at) VALUES(%s,'__rebuild__',%s,%s,'rejected',clock_timestamp()) ON CONFLICT DO NOTHING",
                            (run_id, Jsonb({"run_id": run_id}), category),
                        )
            except psycopg.Error:
                pass
            raise MigrationRejected(category) from None
        finally:
            control.execute("SELECT pg_advisory_unlock(198023,4)")
