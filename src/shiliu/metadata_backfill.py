"""Bounded, auditable backfill for Bilibili platform publication timestamps.

This module deliberately never initializes the application database. Its small
ledger schema is created only by explicit ``stage``/``apply`` operations, which
must be pointed at a disposable rehearsal copy before production rollout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ACCOUNT_ID = "32958899"
PRODUCTION_DATABASE = Path("/Users/elliot/Library/Application Support/Shiliu/shiliu.db")
BV_RE = re.compile(r"^BV[0-9A-Za-z]{10}$")
MIN_EPOCH = 946684800  # 2000-01-01 UTC
MAX_EPOCH = 4102444800  # 2100-01-01 UTC


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    else:
        connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=10000")
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    """Create only the task's compact run, operation, and durable hold tables."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata_backfill_runs (
            run_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            target_sha256 TEXT NOT NULL,
            state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS metadata_backfill_operations (
            run_id TEXT NOT NULL REFERENCES metadata_backfill_runs(run_id),
            video_id INTEGER NOT NULL,
            bvid TEXT NOT NULL,
            part INTEGER NOT NULL,
            candidate_json TEXT NOT NULL,
            candidate_sha256 TEXT NOT NULL,
            state TEXT NOT NULL,
            old_published_at INTEGER,
            new_published_at INTEGER,
            old_metadata_observed_at TEXT,
            new_metadata_observed_at TEXT,
            old_updated_at TEXT,
            new_updated_at TEXT,
            dirty_generation_before INTEGER,
            dirty_generation_after INTEGER,
            old_head_revision TEXT,
            new_head_revision TEXT,
            held_job_ids_json TEXT NOT NULL DEFAULT '[]',
            maintenance_json TEXT NOT NULL DEFAULT '{}',
            detail TEXT,
            written_at TEXT,
            PRIMARY KEY(run_id, video_id)
        );
        CREATE TABLE IF NOT EXISTS metadata_backfill_job_holds (
            job_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES metadata_backfill_runs(run_id),
            video_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS metadata_backfill_wiki_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES metadata_backfill_runs(run_id),
            video_id INTEGER NOT NULL,
            page_id TEXT NOT NULL,
            old_revision TEXT NOT NULL,
            new_revision TEXT NOT NULL,
            before_version INTEGER NOT NULL,
            after_version INTEGER,
            job_id TEXT NOT NULL UNIQUE,
            state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(run_id,video_id,page_id,old_revision,new_revision)
        );
        CREATE INDEX IF NOT EXISTS idx_metadata_backfill_ops_state
            ON metadata_backfill_operations(run_id, state, video_id);
        CREATE INDEX IF NOT EXISTS idx_metadata_backfill_wiki_page
            ON metadata_backfill_wiki_intents(run_id,page_id,id,state);
        """
    )


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _candidate_hash(candidate: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(candidate).encode("utf-8")).hexdigest()


def _require_production_backup(database: Path, manifest_path: Path | None) -> None:
    """Keep production writes locked until a checked pre-migration backup exists."""
    if database.resolve() != PRODUCTION_DATABASE.resolve():
        return
    if manifest_path is None:
        raise ValueError("production_backup_manifest_required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    backup = Path(str(manifest.get("snapshot_database") or "")).resolve()
    if (Path(str(manifest.get("source_database") or "")).resolve() != database.resolve()
            or backup == database.resolve() or not backup.is_file()
            or not manifest.get("service_stop")
            or list(manifest.get("checkpoint") or []) != [0, 0, 0]
            or manifest.get("migration_applied") is not False):
        raise ValueError("production_backup_manifest_invalid")
    actual_hash = hashlib.sha256(backup.read_bytes()).hexdigest()
    if actual_hash != manifest.get("db_sha256"):
        raise ValueError("production_backup_hash_mismatch")


def validate_candidate(candidate: dict[str, Any]) -> None:
    if not isinstance(candidate, dict):
        raise ValueError("candidate_not_object")
    if not BV_RE.fullmatch(str(candidate.get("bvid", ""))):
        raise ValueError("invalid_bvid")
    if candidate.get("platform", "bilibili") != "bilibili":
        raise ValueError("wrong_platform")
    if candidate.get("source_field") != "info.pubdate":
        raise ValueError("untrusted_source_field")
    raw = candidate.get("raw_pubdate")
    value = candidate.get("published_at")
    if isinstance(raw, bool) or not isinstance(raw, (int, str)) or str(raw).strip() != str(value):
        raise ValueError("raw_value_mismatch")
    if isinstance(value, bool) or not isinstance(value, int) or not MIN_EPOCH <= value < MAX_EPOCH:
        raise ValueError("invalid_epoch_seconds")
    observed = datetime.fromisoformat(str(candidate["metadata_observed_at"]).replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise ValueError("observation_time_missing_timezone")
    if value > int(observed.timestamp()):
        raise ValueError("publication_after_observation")
    if not str(candidate.get("source") or "").strip():
        raise ValueError("source_missing")


def _target_row(connection: sqlite3.Connection, candidate: dict[str, Any]) -> sqlite3.Row | None:
    return connection.execute(
        """SELECT v.id,v.platform,v.source_id,v.part,v.published_at,
                  v.metadata_observed_at,v.updated_at,v.is_ignored,v.archived_at,v.removed_at,
                  (SELECT h.current_revision FROM assistant_source_heads h
                   WHERE h.video_id=v.id) AS head_revision
           FROM videos v WHERE v.id=? AND v.platform='bilibili' AND v.source_id=? AND v.part=?
             AND v.removed_at IS NULL AND v.is_ignored=0 AND v.archived_at IS NULL
             AND EXISTS (
               SELECT 1 FROM video_source_memberships m
               JOIN favorite_sources s ON s.id=m.source_id
               WHERE m.video_id=v.id AND m.removed_at IS NULL AND s.status='active'
                 AND CAST(s.account_id AS TEXT)=?
             )""",
        (candidate["video_id"], candidate["bvid"], candidate["part"], ACCOUNT_ID),
    ).fetchone()


def dry_run(database: Path, candidates: Iterable[dict[str, Any]]) -> dict[str, Any]:
    connection = _connect(database, readonly=True)
    try:
        rows = []
        for candidate in candidates:
            try:
                validate_candidate(candidate)
                row = _target_row(connection, candidate)
                if row is None:
                    state = "identity_or_scope_mismatch"
                elif row["published_at"] is not None:
                    state = "already_known_same" if int(row["published_at"]) == candidate["published_at"] else "known_conflict"
                else:
                    state = "ready"
                rows.append({"video_id": candidate.get("video_id"), "bvid": candidate.get("bvid"), "state": state})
            except (KeyError, TypeError, ValueError) as exc:
                rows.append({"video_id": candidate.get("video_id"), "bvid": candidate.get("bvid"), "state": str(exc)})
        return {"count": len(rows), "states": rows}
    finally:
        connection.close()


def stage(database: Path, run_id: str, candidates: list[dict[str, Any]], *,
          production_backup_manifest: Path | None = None) -> dict[str, Any]:
    _require_production_backup(database, production_backup_manifest)
    validated: list[dict[str, Any]] = []
    for candidate in candidates:
        validate_candidate(candidate)
        for key in ("video_id", "part"):
            if isinstance(candidate.get(key), bool) or not isinstance(candidate.get(key), int):
                raise ValueError(f"invalid_{key}")
        validated.append(candidate)
    if len({int(c["video_id"]) for c in validated}) != len(validated):
        raise ValueError("duplicate_video_id")
    target_hash = hashlib.sha256("\n".join(sorted(_candidate_hash(c) for c in validated)).encode()).hexdigest()
    connection = _connect(database)
    try:
        ensure_schema(connection)
        connection.execute("BEGIN IMMEDIATE")
        now = _utc_now()
        existing = connection.execute("SELECT target_sha256 FROM metadata_backfill_runs WHERE run_id=?", (run_id,)).fetchone()
        if existing and existing["target_sha256"] != target_hash:
            raise ValueError("run_id_candidate_manifest_conflict")
        connection.execute(
            "INSERT OR IGNORE INTO metadata_backfill_runs(run_id,account_id,target_sha256,state,created_at,updated_at) VALUES(?,?,?,'staged',?,?)",
            (run_id, ACCOUNT_ID, target_hash, now, now),
        )
        for candidate in validated:
            digest = _candidate_hash(candidate)
            previous = connection.execute(
                "SELECT candidate_sha256 FROM metadata_backfill_operations WHERE run_id=? AND video_id=?",
                (run_id, candidate["video_id"]),
            ).fetchone()
            if previous and previous["candidate_sha256"] != digest:
                raise ValueError("candidate_changed_for_video")
            connection.execute(
                """INSERT OR IGNORE INTO metadata_backfill_operations(
                     run_id,video_id,bvid,part,candidate_json,candidate_sha256,state)
                   VALUES(?,?,?,?,?,?,'staged')""",
                (run_id, candidate["video_id"], candidate["bvid"], candidate["part"], _canonical(candidate), digest),
            )
        connection.commit()
        return {"run_id": run_id, "count": len(validated), "target_sha256": target_hash}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _hold_new_jobs(connection: sqlite3.Connection, run_id: str, video_id: int, generation: int | None) -> list[str]:
    if generation is None:
        return []
    jobs = connection.execute(
        """SELECT id FROM assistant_jobs WHERE kind='source_reconcile'
           AND status IN ('queued','retry_wait','budget_wait')
           AND json_extract(payload_json,'$.video_id')=?
           AND json_extract(payload_json,'$.dirty_generation')=?""",
        (video_id, generation),
    ).fetchall()
    now = _utc_now()
    ids = [str(row["id"]) for row in jobs]
    for job_id in ids:
        connection.execute(
            "INSERT OR IGNORE INTO metadata_backfill_job_holds(job_id,run_id,video_id,reason,created_at) VALUES(?,?,?,'publication_timestamp_maintenance_pending',?)",
            (job_id, run_id, video_id, now),
        )
    return ids


def _preflight_source_artifacts(
    connection: sqlite3.Connection, video_id: int, revision: str,
    *, assistant_objects_root: Path, videos_dir: Path,
) -> None:
    root = assistant_objects_root.resolve()
    videos_root = videos_dir.resolve()
    if not root.is_dir() or not videos_root.is_dir():
        raise ValueError("source_artifact_root_missing")
    row = connection.execute(
        """SELECT r.snapshot_ref FROM assistant_source_revisions r
           JOIN assistant_source_heads h ON h.id=r.head_id
           WHERE r.revision=? AND h.video_id=? AND h.principal_id='local_operator'""",
        (revision, video_id),
    ).fetchone()
    if row is None:
        raise ValueError("source_revision_missing")
    snapshot_path = (root / str(row["snapshot_ref"])).resolve()
    if not snapshot_path.is_relative_to(root) or not snapshot_path.is_file():
        raise ValueError("source_snapshot_artifact_missing")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if snapshot.get("revision") != revision or int(snapshot.get("metadata", {}).get("id", -1)) != video_id:
        raise ValueError("source_snapshot_identity_mismatch")
    video = connection.execute(
        "SELECT raw_subtitle_path,transcript_path,summary_path FROM videos WHERE id=?", (video_id,)
    ).fetchone()
    columns = {
        "raw_subtitle": "raw_subtitle_path",
        "transcript": "transcript_path",
        "summary": "summary_path",
    }
    for kind, expected_hash in snapshot.get("material_hashes", {}).items():
        column = columns[kind]
        source_path = Path(str(video[column] or "")).resolve()
        if not source_path.is_relative_to(videos_root) or not source_path.is_file():
            raise ValueError(f"source_material_missing:{kind}")
        actual_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(f"source_material_hash_mismatch:{kind}")


def _prepare_wiki_rebind(
    database: Path, run_id: str, video_id: int, page: dict[str, Any],
    space: dict[str, Any], *, old_revision: str, new_revision: str,
    job_tag: str | None = None,
) -> tuple[int, dict[str, Any] | None, str]:
    from shiliu.db import Database

    now = _utc_now()
    lease_until = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(timespec="seconds")
    suffix = job_tag or run_id
    job_id = f"metadata-backfill-wiki-{suffix}-{video_id}-{page['id']}"
    payload = {
        "space_id": int(space["id"]), "video_id": video_id,
        "revision": new_revision, "scope_version": int(space["scope_version"]),
    }
    db = Database(database)
    with db.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """INSERT OR IGNORE INTO metadata_backfill_wiki_intents(
                run_id,video_id,page_id,old_revision,new_revision,before_version,
                job_id,state,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,'pending',?,?)""",
            (run_id, video_id, str(page["id"]), old_revision, new_revision,
             int(page["version"]), job_id, now, now),
        )
        intent = connection.execute(
            """SELECT * FROM metadata_backfill_wiki_intents
               WHERE run_id=? AND video_id=? AND page_id=? AND old_revision=? AND new_revision=?""",
            (run_id, video_id, str(page["id"]), old_revision, new_revision),
        ).fetchone()
        intent_id = int(intent["id"])
        job_id = str(intent["job_id"])
        state = str(intent["state"])
        if state in {"rebound", "no_change"}:
            connection.commit()
            return intent_id, None, state
        job_payload = {**payload, "metadata_backfill_run_id": run_id,
                       "metadata_backfill_intent_id": intent_id}
        connection.execute(
            """INSERT OR IGNORE INTO assistant_jobs(
               id,kind,dedupe_key,status,payload_json,not_before,created_at,updated_at,
               lease_owner,lease_until,lease_epoch)
               VALUES(?,'wiki_integrate',?,'running',?,?,?,?,'metadata-backfill',?,1)""",
            (job_id, f"metadata_backfill_wiki:{suffix}:{video_id}:{page['id']}",
             _canonical(job_payload), now, now, now, lease_until),
        )
        connection.execute(
            """UPDATE assistant_jobs SET status='running',payload_json=?,lease_owner='metadata-backfill',
               lease_until=?,lease_epoch=lease_epoch+1,updated_at=?
               WHERE id=?""",
            (_canonical(job_payload), lease_until, now, job_id),
        )
        connection.execute(
            """INSERT INTO metadata_backfill_job_holds(job_id,run_id,video_id,reason,created_at)
               VALUES(?,?,?,'wiki_rebind_intent_pending',?)
               ON CONFLICT(job_id) DO UPDATE SET run_id=excluded.run_id,
                 video_id=excluded.video_id,reason=excluded.reason""",
            (job_id, run_id, video_id, now),
        )
        job_row = connection.execute("SELECT * FROM assistant_jobs WHERE id=?", (job_id,)).fetchone()
        connection.commit()
    job = dict(job_row)
    job["payload"] = json.loads(job.pop("payload_json"))
    return intent_id, job, state


def _rebind_with_backfill_intent(
    wiki: Any, page: dict[str, Any], *, space: dict[str, Any], video_id: int,
    revision: str, job: dict[str, Any], intent_id: int,
) -> dict[str, Any]:
    """Use the existing Wiki commit helpers and commit our intent with the page."""
    now = _utc_now()
    with wiki.db.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        wiki._validate_wiki_commit_fence(
            connection, space_id=int(space["id"]), video_id=video_id,
            revision=revision, scope_version=int(space["scope_version"]),
            job_id=str(job["id"]), lease_owner=str(job["lease_owner"]),
            lease_epoch=int(job["lease_epoch"]), now=now,
        )
        page_row = connection.execute(
            "SELECT * FROM assistant_wiki_pages WHERE id=? AND status='active'",
            (page["id"],),
        ).fetchone()
        if page_row is None or int(page_row["version"]) != int(page["version"]):
            raise RuntimeError("wiki_version_conflict")
        before = wiki._decode_page(dict(page_row))
        before_state = wiki._operation_state(connection, str(page["id"]))
        old_rows = connection.execute(
            """SELECT DISTINCT d.source_revision,old_card.input_hash AS old_hash,
                      new_card.input_hash AS new_hash
               FROM assistant_wiki_dependencies d
               JOIN assistant_source_cards old_card ON old_card.revision=d.source_revision
               JOIN assistant_source_cards new_card ON new_card.revision=?
               WHERE d.page_id=? AND d.video_id=? AND d.source_revision<>?""",
            (revision, page["id"], video_id, revision),
        ).fetchall()
        new_snapshot = wiki.sources._capture_or_load(video_id, revision).snapshot
        old_revisions = {
            str(item["source_revision"]) for item in old_rows
            if item["old_hash"] == item["new_hash"] or wiki._card_body_equivalent(
                wiki.sources._capture_or_load(video_id, str(item["source_revision"])).snapshot,
                new_snapshot,
                wiki.get_source_card(str(item["source_revision"])) or {},
            )
        }
        if not old_revisions:
            cursor = connection.execute(
                "UPDATE metadata_backfill_wiki_intents SET state='no_change',after_version=?,updated_at=? WHERE id=? AND state='pending'",
                (int(page["version"]), now, intent_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("metadata_backfill_intent_state_changed")
            connection.execute(
                "UPDATE assistant_jobs SET status='succeeded',lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                (now, str(job["id"])),
            )
            connection.execute("DELETE FROM metadata_backfill_job_holds WHERE job_id=?", (str(job["id"]),))
            return {"no_change": True, "page_id": page["id"], "version": int(page["version"])}

        blocks = []
        for block in before["blocks"]:
            item = dict(block)
            item["source_refs"] = list(dict.fromkeys(
                revision if ref in old_revisions else ref
                for ref in item.get("source_refs", [])
            ))
            blocks.append(item)
        for old_revision in old_revisions:
            connection.execute(
                """INSERT OR IGNORE INTO assistant_wiki_dependencies(
                     page_id,block_id,source_revision,video_id,dependency_kind,created_at)
                   SELECT page_id,block_id,?,video_id,dependency_kind,?
                   FROM assistant_wiki_dependencies
                   WHERE page_id=? AND video_id=? AND source_revision=?""",
                (revision, now, page["id"], video_id, old_revision),
            )
            connection.execute(
                "DELETE FROM assistant_wiki_dependencies WHERE page_id=? AND video_id=? AND source_revision=?",
                (page["id"], video_id, old_revision),
            )
        version = int(before["version"]) + 1
        connection.execute(
            "UPDATE assistant_wiki_pages SET blocks_json=?,version=?,scope_version=?,updated_at=? WHERE id=?",
            (json.dumps(blocks, ensure_ascii=False), version, int(space["scope_version"]), now, page["id"]),
        )
        connection.execute(
            "UPDATE assistant_wiki_materials SET source_revision=?,updated_at=? WHERE page_id=? AND video_id=?",
            (revision, now, page["id"], video_id),
        )
        after = wiki._decode_page(dict(connection.execute(
            "SELECT * FROM assistant_wiki_pages WHERE id=?", (page["id"],)
        ).fetchone()))
        connection.execute(
            """INSERT INTO assistant_wiki_changes(
                 page_id,version,operation,before_json,after_json,summary,actor,created_at)
               VALUES(?,?,'source_rebound',?,?,?,'assistant',?)""",
            (page["id"], version, json.dumps(before, ensure_ascii=False),
             json.dumps(after, ensure_ascii=False), "等价材料的来源版本已更新", now),
        )
        wiki._fts_replace(connection, after)
        wiki._save_operation_state(connection, str(page["id"]), version, before_state)
        cursor = connection.execute(
            "UPDATE metadata_backfill_wiki_intents SET state='rebound',after_version=?,updated_at=? WHERE id=? AND state='pending'",
            (version, now, intent_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("metadata_backfill_intent_state_changed")
        connection.execute(
            "UPDATE assistant_jobs SET status='succeeded',lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?",
            (now, str(job["id"])),
        )
        connection.execute("DELETE FROM metadata_backfill_job_holds WHERE job_id=?", (str(job["id"]),))
    return {"page_id": page["id"], "version": version, "no_model_call": True,
            "reason": "equivalent_source_rebound"}


def _wiki_intent_results(database: Path, run_id: str, video_id: int,
                         old_revision: str, new_revision: str) -> tuple[list[dict[str, Any]], list[str]]:
    connection = _connect(database)
    try:
        rows = connection.execute(
            """SELECT id,page_id,after_version,state FROM metadata_backfill_wiki_intents
               WHERE run_id=? AND video_id=? AND old_revision=? AND new_revision=? ORDER BY id""",
            (run_id, video_id, old_revision, new_revision),
        ).fetchall()
        rebound = [{"page_id": str(row["page_id"]), "version": int(row["after_version"]),
                    "intent_id": int(row["id"]), "old_revision": old_revision,
                    "new_revision": new_revision}
                   for row in rows if row["state"] == "rebound" and row["after_version"] is not None]
        deferred = [str(row["page_id"]) for row in rows if row["state"] == "pending"]
        return rebound, deferred
    finally:
        connection.close()


def _persist_operation_maintenance(
    connection: sqlite3.Connection, run_id: str, video_id: int,
    maintenance: dict[str, Any],
) -> None:
    connection.execute(
        "UPDATE metadata_backfill_operations SET new_head_revision=?,maintenance_json=? WHERE run_id=? AND video_id=?",
        (maintenance["new_head_revision"], _canonical(maintenance), run_id, video_id),
    )
    connection.commit()


def _wiki_versions_match_for_rollback(
    connection: sqlite3.Connection, run_id: str, video_id: int,
    maintenance: dict[str, Any],
) -> bool:
    for item in maintenance.get("wiki_rebound_pages", []):
        intent_id = int(item.get("intent_id") or 0)
        if not intent_id:
            return False
        row = connection.execute(
            "SELECT state FROM metadata_backfill_wiki_intents WHERE id=? AND run_id=? AND video_id=?",
            (intent_id, run_id, video_id),
        ).fetchone()
        if row is None or row["state"] != "rebound":
            return False
        later = int(connection.execute(
            """SELECT count(*) n FROM metadata_backfill_wiki_intents
               WHERE run_id=? AND page_id=? AND id>? AND state='rebound'""",
            (run_id, item["page_id"], intent_id),
        ).fetchone()["n"])
        expected_version = int(item["version"]) + later
        page = connection.execute("SELECT version FROM assistant_wiki_pages WHERE id=?", (item["page_id"],)).fetchone()
        if page is None or int(page["version"]) != expected_version:
            return False
    return True


def _apply_one(connection: sqlite3.Connection, run_id: str, operation: sqlite3.Row) -> str:
    candidate = json.loads(operation["candidate_json"])
    validate_candidate(candidate)
    row = _target_row(connection, candidate)
    if row is None:
        connection.execute("UPDATE metadata_backfill_operations SET state='skipped',detail='identity_or_scope_mismatch' WHERE run_id=? AND video_id=?", (run_id, operation["video_id"]))
        return "identity_or_scope_mismatch"
    if row["published_at"] is not None:
        state = "already_known_same" if int(row["published_at"]) == candidate["published_at"] else "known_conflict"
        connection.execute("UPDATE metadata_backfill_operations SET state='skipped',detail=? WHERE run_id=? AND video_id=?", (state, run_id, operation["video_id"]))
        return state
    now = _utc_now()
    before_generation_row = connection.execute("SELECT dirty_generation FROM assistant_source_dirty WHERE video_id=?", (operation["video_id"],)).fetchone()
    before_generation = int(before_generation_row["dirty_generation"]) if before_generation_row else None
    cursor = connection.execute(
        """UPDATE videos AS v SET published_at=?,metadata_observed_at=?,updated_at=?
           WHERE v.id=? AND v.platform='bilibili' AND v.source_id=? AND v.part=?
             AND v.published_at IS NULL AND v.removed_at IS NULL
             AND v.is_ignored=0 AND v.archived_at IS NULL
             AND EXISTS (SELECT 1 FROM video_source_memberships m
               JOIN favorite_sources s ON s.id=m.source_id
               WHERE m.video_id=v.id AND m.removed_at IS NULL AND s.status='active'
                 AND CAST(s.account_id AS TEXT)=?)""",
        (candidate["published_at"], candidate["metadata_observed_at"], now,
         operation["video_id"], candidate["bvid"], candidate["part"], ACCOUNT_ID),
    )
    if cursor.rowcount != 1:
        connection.execute("UPDATE metadata_backfill_operations SET state='skipped',detail='cas_or_scope_changed' WHERE run_id=? AND video_id=?", (run_id, operation["video_id"]))
        return "cas_or_scope_changed"
    from shiliu.db import Database
    Database._notify_assistant_source_change(Database, connection, int(operation["video_id"]), reason=f"metadata_backfill:{run_id}")
    after_generation_row = connection.execute("SELECT dirty_generation FROM assistant_source_dirty WHERE video_id=?", (operation["video_id"],)).fetchone()
    after_generation = int(after_generation_row["dirty_generation"]) if after_generation_row else None
    held = _hold_new_jobs(connection, run_id, int(operation["video_id"]), after_generation)
    updated = connection.execute("SELECT published_at,metadata_observed_at,updated_at FROM videos WHERE id=?", (operation["video_id"],)).fetchone()
    head_after = connection.execute("SELECT current_revision FROM assistant_source_heads WHERE video_id=?", (operation["video_id"],)).fetchone()
    connection.execute(
        """UPDATE metadata_backfill_operations SET state='applied',old_published_at=NULL,
             new_published_at=?,old_metadata_observed_at=?,new_metadata_observed_at=?,
             old_updated_at=?,new_updated_at=?,dirty_generation_before=?,dirty_generation_after=?,
             old_head_revision=?,new_head_revision=?,held_job_ids_json=?,detail='applied',written_at=?
           WHERE run_id=? AND video_id=?""",
        (updated["published_at"], row["metadata_observed_at"], updated["metadata_observed_at"],
         row["updated_at"], updated["updated_at"], before_generation, after_generation,
         row["head_revision"], str(head_after["current_revision"]) if head_after else None,
         _canonical(held), now, run_id, operation["video_id"]),
    )
    return "applied"


def _maintain_existing_source(
    database: Path, run_id: str, video_id: int, old_revision: str,
    *, assistant_objects_root: Path, videos_dir: Path, job_tag: str | None = None,
) -> dict[str, Any]:
    from shiliu.artifacts import ArtifactStore
    from shiliu.assistant.snapshots import SourceSnapshotStore
    from shiliu.assistant.sources import CollectionSourceService
    from shiliu.assistant.store import AssistantRunStore
    from shiliu.assistant.wiki import WikiService
    from shiliu.db import Database

    db = Database(database)
    artifacts = ArtifactStore(videos_dir)
    snapshots = SourceSnapshotStore(db, artifacts, assistant_objects_root)
    sources = CollectionSourceService(db=db, artifacts=artifacts, snapshots=snapshots)
    store = AssistantRunStore(db)
    wiki = WikiService(db=db, store=store, sources=sources)
    old_captured = sources._capture_or_load(video_id, old_revision)
    captured = snapshots.capture(video_id)
    result: dict[str, Any] = {
        "old_head_revision": old_revision,
        "new_head_revision": captured.revision,
        "snapshot_ref": captured.snapshot_ref,
        "card": "missing",
        "wiki_rebound_pages": [],
        "wiki_deferred_pages": [],
    }
    old_card = wiki.get_source_card(old_revision)
    if old_card is not None and wiki._card_body_equivalent(old_captured.snapshot, captured.snapshot, old_card):
        card = dict(old_card)
        card["published_at"] = captured.snapshot["metadata"].get("published_at")
        card["metadata_observed_at"] = captured.snapshot["metadata"].get("metadata_observed_at")
        card["memberships"] = captured.snapshot["memberships"]
        wiki._commit_source_card(captured, input_hash=wiki._card_input_hash(captured.snapshot), card=card)
        result["card"] = "reused_time_only"
    elif old_card is not None:
        result["card"] = "deferred_for_rejudgment"

    if result["card"] != "reused_time_only":
        with db.connect() as connection:
            result["wiki_deferred_pages"] = [
                str(row["id"]) for row in connection.execute(
                    """SELECT DISTINCT p.id FROM assistant_wiki_dependencies d
                       JOIN assistant_wiki_pages p ON p.id=d.page_id
                       WHERE d.video_id=? AND d.source_revision=? AND p.status='active'""",
                    (video_id, old_revision),
                ).fetchall()
            ]

    if result["card"] == "reused_time_only":
        with db.connect() as connection:
            pages = connection.execute(
                """SELECT DISTINCT p.* FROM assistant_wiki_dependencies d
                   JOIN assistant_wiki_pages p ON p.id=d.page_id
                   WHERE d.video_id=? AND d.source_revision=? AND p.status='active'""",
                (video_id, old_revision),
            ).fetchall()
        for raw_page in pages:
            page_row = dict(raw_page)
            page = wiki._decode_page(page_row)
            searchable = " ".join(
                [str(page.get("summary") or "")]
                + [str(block.get(k) or "") for block in page.get("blocks", [])
                   for k in ("heading", "markdown", "applicability", "speaker")]
            )
            if re.search(r"\b(?:19|20)\d{2}\b", searchable):
                result["wiki_deferred_pages"].append(str(page["id"]))
                continue
            space = store.get_space(int(page["space_id"]))
            intent_id, job, intent_state = _prepare_wiki_rebind(
                database, run_id, video_id, page, space,
                old_revision=old_revision, new_revision=captured.revision,
                job_tag=job_tag,
            )
            if intent_state == "rebound":
                continue
            if intent_state == "no_change":
                continue
            try:
                if job is None:
                    raise RuntimeError("wiki_rebind_intent_missing_job")
                outcome = _rebind_with_backfill_intent(
                    wiki,
                    page, space=space, video_id=video_id,
                    revision=captured.revision, job=job, intent_id=intent_id,
                )
            except Exception:
                with db.connect() as connection:
                    intent = connection.execute("SELECT state FROM metadata_backfill_wiki_intents WHERE id=?", (intent_id,)).fetchone()
                    if intent and intent["state"] not in {"rebound", "no_change"}:
                        connection.execute(
                            "UPDATE assistant_jobs SET status='queued',lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                            (_utc_now(), job["id"] if job else ""),
                        )
                        result["wiki_deferred_pages"].append(str(page["id"]))
            else:
                if outcome.get("no_model_call"):
                    # The intent result is committed by WikiService in the same
                    # transaction as the page/dependency change.
                    pass
    result["wiki_rebound_pages"], committed_deferred = _wiki_intent_results(
        database, run_id, video_id, old_revision, captured.revision,
    )
    result["wiki_deferred_pages"] = sorted(set(result["wiki_deferred_pages"]).union(committed_deferred))
    # Reconciliation is deterministic and the snapshot capture above has done
    # that work. Retire only this video's held reconcile jobs; held wiki/model
    # work remains durable for an explicit later review.
    with db.connect() as connection:
        held_reconciles = connection.execute(
            """SELECT h.job_id FROM metadata_backfill_job_holds h
               JOIN assistant_jobs j ON j.id=h.job_id
               WHERE h.run_id=? AND h.video_id=? AND j.kind='source_reconcile'""",
            (run_id, video_id),
        ).fetchall()
        for held in held_reconciles:
            connection.execute(
                "UPDATE assistant_jobs SET status='succeeded',lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=? AND status IN ('queued','retry_wait','budget_wait')",
                (_utc_now(), held["job_id"]),
            )
            connection.execute("DELETE FROM metadata_backfill_job_holds WHERE job_id=?", (held["job_id"],))
    return result


def apply(
    database: Path, run_id: str, *, assistant_objects_root: Path | None = None,
    videos_dir: Path | None = None, production_backup_manifest: Path | None = None,
) -> dict[str, Any]:
    _require_production_backup(database, production_backup_manifest)
    connection = _connect(database)
    try:
        ensure_schema(connection)
        operations = connection.execute("SELECT * FROM metadata_backfill_operations WHERE run_id=? ORDER BY video_id", (run_id,)).fetchall()
        if not operations:
            raise ValueError("run_not_staged")
        counts: dict[str, int] = {}
        for operation in operations:
            if operation["state"] == "applied":
                if operation["old_head_revision"]:
                    if assistant_objects_root is None or videos_dir is None:
                        raise ValueError("existing_source_head_requires_artifact_roots")
                    current = _target_row(connection, json.loads(operation["candidate_json"]))
                    if current is None or current["published_at"] != operation["new_published_at"] or current["updated_at"] != operation["new_updated_at"]:
                        counts["resume_conflict"] = counts.get("resume_conflict", 0) + 1
                        continue
                    maintenance = _maintain_existing_source(
                        database, run_id, int(operation["video_id"]), str(operation["old_head_revision"]),
                        assistant_objects_root=assistant_objects_root, videos_dir=videos_dir,
                    )
                    _persist_operation_maintenance(connection, run_id, int(operation["video_id"]), maintenance)
                counts["already_applied"] = counts.get("already_applied", 0) + 1
                continue
            if operation["state"] in {"rolled_back", "rollback_pending", "rollback_conflict", "skipped"}:
                counts["not_resumed"] = counts.get("not_resumed", 0) + 1
                continue
            if operation["old_head_revision"] and (assistant_objects_root is None or videos_dir is None):
                raise ValueError("existing_source_head_requires_artifact_roots")
            if operation["old_head_revision"]:
                _preflight_source_artifacts(
                    connection, int(operation["video_id"]), str(operation["old_head_revision"]),
                    assistant_objects_root=assistant_objects_root, videos_dir=videos_dir,
                )
            connection.execute("BEGIN IMMEDIATE")
            try:
                result = _apply_one(connection, run_id, operation)
                connection.execute("UPDATE metadata_backfill_runs SET state='applying',updated_at=? WHERE run_id=?", (_utc_now(), run_id))
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            counts[result] = counts.get(result, 0) + 1
            applied_operation = connection.execute(
                "SELECT * FROM metadata_backfill_operations WHERE run_id=? AND video_id=?",
                (run_id, operation["video_id"]),
            ).fetchone()
            if result == "applied" and applied_operation["old_head_revision"]:
                maintenance = _maintain_existing_source(
                    database, run_id, int(operation["video_id"]), str(applied_operation["old_head_revision"]),
                    assistant_objects_root=assistant_objects_root, videos_dir=videos_dir,
                )
                _persist_operation_maintenance(connection, run_id, int(operation["video_id"]), maintenance)
        connection.execute("UPDATE metadata_backfill_runs SET state='applied',updated_at=? WHERE run_id=?", (_utc_now(), run_id))
        connection.commit()
        return {"run_id": run_id, "counts": counts}
    finally:
        connection.close()


def rollback(
    database: Path, run_id: str, *, assistant_objects_root: Path | None = None,
    videos_dir: Path | None = None, production_backup_manifest: Path | None = None,
) -> dict[str, Any]:
    _require_production_backup(database, production_backup_manifest)
    connection = _connect(database)
    try:
        ensure_schema(connection)
        # Apply is ordered by video_id ascending; reverse that order when several
        # videos share a page so each page's dependency chain is unwound in LIFO order.
        operations = connection.execute("SELECT * FROM metadata_backfill_operations WHERE run_id=? AND state IN ('applied','rollback_pending') ORDER BY video_id DESC", (run_id,)).fetchall()
        counts: dict[str, int] = {}
        for operation in operations:
            connection.execute("BEGIN IMMEDIATE")
            try:
                candidate = json.loads(operation["candidate_json"])
                row = _target_row(connection, candidate)
                head = connection.execute("SELECT current_revision FROM assistant_source_heads WHERE video_id=?", (operation["video_id"],)).fetchone()
                current_head = str(head["current_revision"]) if head else None
                maintenance = json.loads(operation["maintenance_json"] or "{}")
                if operation["state"] == "rollback_pending":
                    if (row is None or row["published_at"] != operation["old_published_at"]
                            or row["updated_at"] != operation["old_updated_at"]
                            or current_head not in {operation["old_head_revision"], operation["new_head_revision"]}
                            or not _wiki_versions_match_for_rollback(
                                connection, run_id, int(operation["video_id"]), maintenance,
                            )):
                        connection.execute("UPDATE metadata_backfill_operations SET state='rollback_conflict',detail='rollback_resume_state_changed' WHERE run_id=? AND video_id=?", (run_id, operation["video_id"]))
                        connection.commit()
                        counts["rollback_conflict"] = counts.get("rollback_conflict", 0) + 1
                        continue
                    if operation["old_head_revision"]:
                        if assistant_objects_root is None or videos_dir is None:
                            raise ValueError("existing_source_head_requires_artifact_roots")
                        # Source snapshot and Wiki recovery use their own connections.
                        # Release this validation transaction before they write.
                        connection.commit()
                        restored = _maintain_existing_source(
                            database, run_id, int(operation["video_id"]), str(operation["new_head_revision"]),
                            assistant_objects_root=assistant_objects_root, videos_dir=videos_dir,
                            job_tag=run_id + "-rollback-resume",
                        )
                        connection.execute("BEGIN IMMEDIATE")
                        row_after = _target_row(connection, candidate)
                        head_after = connection.execute(
                            "SELECT current_revision FROM assistant_source_heads WHERE video_id=?",
                            (operation["video_id"],),
                        ).fetchone()
                        current_head_after = str(head_after["current_revision"]) if head_after else None
                        if (row_after is None or row_after["published_at"] != operation["old_published_at"]
                                or row_after["updated_at"] != operation["old_updated_at"]
                                or current_head_after != operation["old_head_revision"]
                                or not _wiki_versions_match_for_rollback(
                                    connection, run_id, int(operation["video_id"]), maintenance,
                                )):
                            connection.execute(
                                "UPDATE metadata_backfill_operations SET state='rollback_conflict',detail='rollback_resume_state_changed' WHERE run_id=? AND video_id=?",
                                (run_id, operation["video_id"]),
                            )
                            connection.commit()
                            counts["rollback_conflict"] = counts.get("rollback_conflict", 0) + 1
                            continue
                    else:
                        restored = {}
                    with connection:
                        connection.execute(
                            "UPDATE metadata_backfill_operations SET state='rolled_back',detail='rolled_back',maintenance_json=?,written_at=? WHERE run_id=? AND video_id=?",
                            (_canonical({"apply": maintenance, "rollback": restored}), _utc_now(), run_id, operation["video_id"]),
                        )
                    counts["rolled_back"] = counts.get("rolled_back", 0) + 1
                    continue
                if (row is None or row["published_at"] != operation["new_published_at"]
                        or row["updated_at"] != operation["new_updated_at"]
                        or current_head != operation["new_head_revision"]
                        or not _wiki_versions_match_for_rollback(
                            connection, run_id, int(operation["video_id"]), maintenance,
                        )):
                    connection.execute("UPDATE metadata_backfill_operations SET state='rollback_conflict',detail='current_state_changed' WHERE run_id=? AND video_id=?", (run_id, operation["video_id"]))
                    connection.commit()
                    counts["rollback_conflict"] = counts.get("rollback_conflict", 0) + 1
                    continue
                if operation["old_head_revision"] and (assistant_objects_root is None or videos_dir is None):
                    raise ValueError("existing_source_head_requires_artifact_roots")
                cursor = connection.execute(
                    """UPDATE videos SET published_at=NULL,metadata_observed_at=?,updated_at=?
                       WHERE id=? AND platform='bilibili' AND source_id=? AND part=?
                         AND published_at=? AND updated_at=? AND removed_at IS NULL
                         AND is_ignored=0 AND archived_at IS NULL
                         AND EXISTS (SELECT 1 FROM video_source_memberships m
                           JOIN favorite_sources s ON s.id=m.source_id
                           WHERE m.video_id=videos.id AND m.removed_at IS NULL
                             AND s.status='active' AND CAST(s.account_id AS TEXT)=?)""",
                    (operation["old_metadata_observed_at"], operation["old_updated_at"], operation["video_id"], candidate["bvid"], candidate["part"], operation["new_published_at"], operation["new_updated_at"], ACCOUNT_ID),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("rollback_cas_failed")
                from shiliu.db import Database
                Database._notify_assistant_source_change(Database, connection, int(operation["video_id"]), reason=f"metadata_backfill_rollback:{run_id}")
                gen_row = connection.execute("SELECT dirty_generation FROM assistant_source_dirty WHERE video_id=?", (operation["video_id"],)).fetchone()
                rollback_held = _hold_new_jobs(
                    connection, run_id, int(operation["video_id"]),
                    int(gen_row["dirty_generation"]) if gen_row else None,
                )
                held_ids = list(json.loads(operation["held_job_ids_json"] or "[]"))
                held_ids.extend(item for item in rollback_held if item not in held_ids)
                connection.execute(
                    "UPDATE metadata_backfill_operations SET held_job_ids_json=? WHERE run_id=? AND video_id=?",
                    (_canonical(held_ids), run_id, operation["video_id"]),
                )
                connection.execute("UPDATE metadata_backfill_operations SET state='rollback_pending',detail='rollback_pending' WHERE run_id=? AND video_id=?", (run_id, operation["video_id"]))
                connection.commit()
                if operation["old_head_revision"]:
                    restored = _maintain_existing_source(
                        database, run_id, int(operation["video_id"]), str(operation["new_head_revision"]),
                        assistant_objects_root=assistant_objects_root, videos_dir=videos_dir,
                        job_tag=run_id + "-rollback",
                    )
                    with connection:
                        full_maintenance = {"apply": maintenance, "rollback": restored}
                        connection.execute(
                            "UPDATE metadata_backfill_operations SET state='rolled_back',detail='rolled_back',maintenance_json=?,written_at=? WHERE run_id=? AND video_id=?",
                            (_canonical(full_maintenance), _utc_now(), run_id, operation["video_id"]),
                        )
                else:
                    with connection:
                        connection.execute("UPDATE metadata_backfill_operations SET state='rolled_back',detail='rolled_back',written_at=? WHERE run_id=? AND video_id=?", (_utc_now(), run_id, operation["video_id"]))
                counts["rolled_back"] = counts.get("rolled_back", 0) + 1
            except Exception:
                connection.rollback()
                raise
        connection.execute("UPDATE metadata_backfill_runs SET state='rolled_back',updated_at=? WHERE run_id=?", (_utc_now(), run_id))
        connection.commit()
        return {"run_id": run_id, "counts": counts}
    finally:
        connection.close()


def _load_candidates(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("candidate_file_must_be_array")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("dry-run", "stage", "apply", "resume", "rollback"):
        command = commands.add_parser(name)
        command.add_argument("--database", type=Path, required=True)
        if name in {"dry-run", "stage"}:
            command.add_argument("--candidates", type=Path, required=True)
        if name != "dry-run":
            command.add_argument("--run-id", required=True)
            command.add_argument("--production-backup-manifest", type=Path)
        if name in {"apply", "resume", "rollback"}:
            command.add_argument("--assistant-objects-root", type=Path)
            command.add_argument("--videos-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "dry-run":
            result = dry_run(args.database, _load_candidates(args.candidates))
        elif args.command == "stage":
            result = stage(args.database, args.run_id, _load_candidates(args.candidates),
                           production_backup_manifest=args.production_backup_manifest)
        elif args.command in {"apply", "resume"}:
            result = apply(args.database, args.run_id,
                           assistant_objects_root=args.assistant_objects_root,
                           videos_dir=args.videos_dir,
                           production_backup_manifest=args.production_backup_manifest)
        else:
            result = rollback(args.database, args.run_id,
                              assistant_objects_root=args.assistant_objects_root,
                              videos_dir=args.videos_dir,
                              production_backup_manifest=args.production_backup_manifest)
        print(_canonical(result))
        return 0
    except Exception as exc:
        print(_canonical({"error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
