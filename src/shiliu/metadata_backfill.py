"""Bounded PostgreSQL publication-time backfill with held maintenance intents.

No Application defaults, credentials, schema creation or SQLite connection is
used by the service. The CLI owns one explicitly configured Application pool.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable
from psycopg.types.json import Jsonb
from shiliu.db import Database
from shiliu.storage.dto import json_value
from shiliu.storage.errors import StorageError
from shiliu.storage.fences import CoordinationConflict
from shiliu.storage.scheduler import claim_backfill_job, job_transition

ACCOUNT_ID = "32958899"
BV_RE = re.compile(r"^BV[0-9A-Za-z]{10}$")
MIN_EPOCH = 946684800
MAX_EPOCH = 4102444800
from datetime import datetime


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _candidate_hash(candidate):
    return hashlib.sha256(_canonical(candidate).encode()).hexdigest()


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
    if (
        isinstance(raw, bool)
        or not isinstance(raw, (int, str))
        or str(raw).strip() != str(value)
    ):
        raise ValueError("raw_value_mismatch")
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not MIN_EPOCH <= value < MAX_EPOCH
    ):
        raise ValueError("invalid_epoch_seconds")
    observed = datetime.fromisoformat(
        str(candidate["metadata_observed_at"]).replace("Z", "+00:00")
    )
    if observed.tzinfo is None:
        raise ValueError("observation_time_missing_timezone")
    if value > int(observed.timestamp()):
        raise ValueError("publication_after_observation")
    if not str(candidate.get("source") or "").strip():
        raise ValueError("source_missing")


class MetadataBackfillService:
    def __init__(self, db: Database, artifacts=None, *, fault_injector=None):
        if not isinstance(db, Database):
            raise TypeError(
                "metadata backfill requires an injected PostgreSQL Database"
            )
        self.db = db
        self.context = db.context
        self.artifacts = artifacts
        self.fault_injector = fault_injector or (lambda point: None)
        self.sources = self.store = self.wiki = None
        if artifacts is not None:
            from shiliu.assistant.snapshots import SourceSnapshotStore
            from shiliu.assistant.sources import CollectionSourceService
            from shiliu.assistant.pg_store import PgAssistantRunStore
            from shiliu.assistant.wiki import WikiService

            self.sources = CollectionSourceService(
                db=db, artifacts=artifacts, snapshots=SourceSnapshotStore(db, artifacts)
            )
            self.store = PgAssistantRunStore(db)
            self.wiki = WikiService(
                db=db,
                store=self.store,
                sources=self.sources,
                principal_id=self.context.user_id,
            )

    def _backup(self, path):
        if self.db.pg.config.environment != "production":
            return
        if path is None:
            raise ValueError("production_backup_manifest_required")
        manifest = json.loads(Path(path).read_text())
        from psycopg.conninfo import conninfo_to_dict

        target = conninfo_to_dict(self.db.pg.config.database_url)
        identity = {key: target.get(key) for key in ("host", "port", "dbname", "user")}
        identity["workspace_id"] = self.context.workspace_id
        if not manifest.get("service_stop") or manifest.get(
            "target_fingerprint"
        ) != _candidate_hash(identity):
            raise ValueError("production_backup_manifest_invalid")
        for name in ("postgres_backup", "artifact_manifest"):
            item = manifest.get(name) or {}
            candidate = Path(str(item.get("path") or ""))
            if (
                not candidate.is_absolute()
                or not candidate.is_file()
                or hashlib.sha256(candidate.read_bytes()).hexdigest()
                != item.get("sha256")
            ):
                raise ValueError("production_backup_hash_mismatch")

    def _run(self, c, run_id, *, lock=False):
        row = c.execute(
            "SELECT * FROM metadata_backfill_runs WHERE workspace_id=%s AND run_id=%s"
            + (" FOR UPDATE" if lock else ""),
            (self.context.workspace_id, run_id),
        ).fetchone()
        if row is None:
            raise KeyError("backfill run not found in this workspace")
        return row

    def _target(self, c, candidate, *, lock=False):
        return c.execute(
            """SELECT v.*,h.current_revision AS head_revision FROM videos v
            LEFT JOIN assistant_source_heads h ON (h.workspace_id,h.video_id)=(v.workspace_id,v.id) AND h.principal_id=%s
            WHERE v.workspace_id=%s AND v.id=%s AND v.platform='bilibili' AND v.source_id=%s AND v.part=%s
            AND v.removed_at IS NULL AND NOT v.is_ignored AND v.archived_at IS NULL
            AND EXISTS(SELECT 1 FROM video_source_memberships m JOIN favorite_sources s ON (s.workspace_id,s.id)=(m.workspace_id,m.source_id)
              WHERE (m.workspace_id,m.video_id)=(v.workspace_id,v.id) AND m.removed_at IS NULL AND s.status='active' AND s.account_id::text=%s)"""
            + (" FOR UPDATE OF v" if lock else ""),
            (
                self.context.user_id,
                self.context.workspace_id,
                candidate["video_id"],
                candidate["bvid"],
                candidate["part"],
                ACCOUNT_ID,
            ),
        ).fetchone()

    def dry_run(self, candidates: Iterable[dict]):
        result = []
        with self.db.connect(read_only=True) as c:
            for candidate in candidates:
                try:
                    validate_candidate(candidate)
                    row = self._target(c, candidate)
                    state = (
                        "identity_or_scope_mismatch"
                        if row is None
                        else "ready"
                        if row["published_at"] is None
                        else "already_known_same"
                        if row["published_at"] == candidate["published_at"]
                        else "known_conflict"
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    state = str(exc)
                result.append(
                    {
                        "video_id": candidate.get("video_id"),
                        "bvid": candidate.get("bvid"),
                        "state": state,
                    }
                )
        return {"count": len(result), "states": result}

    def stage(self, run_id, candidates, *, production_backup_manifest=None):
        self._backup(production_backup_manifest)
        candidates = list(candidates)
        for candidate in candidates:
            validate_candidate(candidate)
            if any(type(candidate.get(key)) is not int for key in ("video_id", "part")):
                raise ValueError("invalid_video_identity")
        if len({c["video_id"] for c in candidates}) != len(candidates):
            raise ValueError("duplicate_video_id")
        digest = hashlib.sha256(
            "\n".join(sorted(_candidate_hash(c) for c in candidates)).encode()
        ).hexdigest()
        with self.db.connect(guard=True) as c:
            c.execute(
                "INSERT INTO metadata_backfill_runs(workspace_id,run_id,account_id,target_sha256,state,created_at,updated_at) VALUES(%s,%s,%s,%s,'staged',clock_timestamp(),clock_timestamp()) ON CONFLICT DO NOTHING",
                (self.context.workspace_id, run_id, ACCOUNT_ID, digest),
            )
            run = self._run(c, run_id, lock=True)
            if run["target_sha256"] != digest:
                raise ValueError("run_id_candidate_manifest_conflict")
            for candidate in candidates:
                c.execute(
                    "INSERT INTO metadata_backfill_operations(workspace_id,run_id,video_id,bvid,part,candidate_json,candidate_sha256,state) VALUES(%s,%s,%s,%s,%s,%s,%s,'staged') ON CONFLICT DO NOTHING",
                    (
                        self.context.workspace_id,
                        run_id,
                        candidate["video_id"],
                        candidate["bvid"],
                        candidate["part"],
                        Jsonb(candidate),
                        _candidate_hash(candidate),
                    ),
                )
                old = c.execute(
                    "SELECT candidate_sha256 FROM metadata_backfill_operations WHERE workspace_id=%s AND run_id=%s AND video_id=%s",
                    (self.context.workspace_id, run_id, candidate["video_id"]),
                ).fetchone()
                if old["candidate_sha256"] != _candidate_hash(candidate):
                    raise ValueError("candidate_changed_for_video")
        return {"run_id": run_id, "count": len(candidates), "target_sha256": digest}

    def _operations(self, run_id, *, reverse=False):
        with self.db.connect(read_only=True) as c:
            self._run(c, run_id)
            return c.execute(
                "SELECT * FROM metadata_backfill_operations WHERE workspace_id=%s AND run_id=%s ORDER BY video_id"
                + (" DESC" if reverse else ""),
                (self.context.workspace_id, run_id),
            ).fetchall()

    def _hold(self, c, run_id, video_id, generation):
        if generation is None:
            return []
        rows = c.execute(
            "SELECT id FROM assistant_jobs WHERE workspace_id=%s AND principal_id=%s AND kind='source_reconcile' AND status IN ('queued','retry_wait','budget_wait') AND (payload_json->>'video_id')::bigint=%s AND (payload_json->>'dirty_generation')::bigint=%s",
            (self.context.workspace_id, self.context.user_id, video_id, generation),
        ).fetchall()
        for row in rows:
            c.execute(
                "INSERT INTO metadata_backfill_job_holds(workspace_id,job_id,run_id,video_id,reason,created_at) VALUES(%s,%s,%s,%s,'publication_timestamp_maintenance_pending',clock_timestamp()) ON CONFLICT DO NOTHING",
                (self.context.workspace_id, row["id"], run_id, video_id),
            )
        return [row["id"] for row in rows]

    def _preflight(self, video_id, revision):
        if not revision:
            return
        if self.sources is None:
            raise ValueError("existing_source_head_requires_artifact_resolver")
        captured = self.sources._capture_or_load(video_id, revision)
        video = self.db.get_video(video_id)
        for kind, digest in captured.snapshot.get("material_hashes", {}).items():
            column = {
                "raw_subtitle": "raw_subtitle_path",
                "transcript": "transcript_path",
                "summary": "summary_path",
            }[kind]
            ref = video.get(column)
            if not ref or not ref.startswith("artifact:"):
                raise ValueError("source_material_manifest_missing")
            raw = (
                self.artifacts.raw_bytes(ref)
                if kind == "raw_subtitle"
                else self.artifacts.read_bytes(ref)
            )
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("source_material_hash_mismatch")

    def _operation_guard(self, c, run_id, video_id):
        self._run(c, run_id, lock=True)
        op = c.execute(
            "SELECT * FROM metadata_backfill_operations WHERE workspace_id=%s AND run_id=%s AND video_id=%s FOR UPDATE",
            (self.context.workspace_id, run_id, video_id),
        ).fetchone()
        if op is None:
            raise KeyError("backfill operation missing")
        return op

    def apply(self, run_id, *, production_backup_manifest=None):
        self._backup(production_backup_manifest)
        counts = {}
        for operation in self._operations(run_id):
            video_id = operation["video_id"]
            if operation["state"] == "applied":
                if operation["old_head_revision"]:
                    self._maintain_and_persist(
                        run_id, video_id, operation["old_head_revision"]
                    )
                counts["already_applied"] = counts.get("already_applied", 0) + 1
                continue
            if operation["state"] in {
                "skipped",
                "rolled_back",
                "rollback_pending",
                "rollback_conflict",
            }:
                counts["not_resumed"] = counts.get("not_resumed", 0) + 1
                continue
            candidate = json_value(operation["candidate_json"])
            with self.db.connect(read_only=True) as c:
                before = self._target(c, candidate)
            self._preflight(video_id, before["head_revision"] if before else None)
            with self.db.connect(guard=True) as c:
                op = self._operation_guard(c, run_id, video_id)
                if op["state"] != "staged":
                    raise ValueError("backfill_operation_changed")
                row = self._target(c, candidate, lock=True)
                if (
                    row is not None
                    and before is not None
                    and row["head_revision"] != before["head_revision"]
                ):
                    raise ValueError("backfill_source_changed")
                state = (
                    "identity_or_scope_mismatch"
                    if row is None
                    else "already_known_same"
                    if row["published_at"] == candidate["published_at"]
                    else "known_conflict"
                    if row["published_at"] is not None
                    else "applied"
                )
                if state != "applied":
                    c.execute(
                        "UPDATE metadata_backfill_operations SET state='skipped',detail=%s WHERE workspace_id=%s AND run_id=%s AND video_id=%s",
                        (state, self.context.workspace_id, run_id, video_id),
                    )
                else:
                    generation = c.execute(
                        "SELECT dirty_generation FROM assistant_source_dirty WHERE workspace_id=%s AND video_id=%s",
                        (self.context.workspace_id, video_id),
                    ).fetchone()
                    self.db.update_video(
                        video_id,
                        conn=c,
                        published_at=candidate["published_at"],
                        metadata_observed_at=candidate["metadata_observed_at"],
                    )
                    updated = self.db._video(c, video_id)
                    after = c.execute(
                        "SELECT dirty_generation FROM assistant_source_dirty WHERE workspace_id=%s AND video_id=%s",
                        (self.context.workspace_id, video_id),
                    ).fetchone()
                    held = self._hold(
                        c,
                        run_id,
                        video_id,
                        after["dirty_generation"] if after else None,
                    )
                    c.execute(
                        """UPDATE metadata_backfill_operations SET state='applied',new_published_at=%s,old_metadata_observed_at=%s,new_metadata_observed_at=%s,old_updated_at=%s,new_updated_at=%s,dirty_generation_before=%s,dirty_generation_after=%s,old_head_revision=%s,new_head_revision=%s,held_job_ids_json=%s,detail='applied',written_at=clock_timestamp() WHERE workspace_id=%s AND run_id=%s AND video_id=%s""",
                        (
                            updated["published_at"],
                            row["metadata_observed_at"],
                            updated["metadata_observed_at"],
                            row["updated_at"],
                            updated["updated_at"],
                            generation["dirty_generation"] if generation else None,
                            after["dirty_generation"] if after else None,
                            row["head_revision"],
                            row["head_revision"],
                            Jsonb(held),
                            self.context.workspace_id,
                            run_id,
                            video_id,
                        ),
                    )
                c.execute(
                    "UPDATE metadata_backfill_runs SET state='applying',updated_at=clock_timestamp() WHERE workspace_id=%s AND run_id=%s",
                    (self.context.workspace_id, run_id),
                )
                self.fault_injector("after_metadata_update")
            counts[state] = counts.get(state, 0) + 1
            if state == "applied" and row["head_revision"]:
                self._maintain_and_persist(run_id, video_id, row["head_revision"])
        with self.db.connect(guard=True) as c:
            self._run(c, run_id, lock=True)
            c.execute(
                "UPDATE metadata_backfill_runs SET state='applied',updated_at=clock_timestamp() WHERE workspace_id=%s AND run_id=%s",
                (self.context.workspace_id, run_id),
            )
        return {"run_id": run_id, "counts": counts}

    def _maintenance_guard(self, c, run_id, video_id):
        op = self._operation_guard(c, run_id, video_id)
        if op["state"] not in {"applied", "rollback_pending"}:
            raise ValueError("backfill_operation_changed")
        row = self._target(c, json_value(op["candidate_json"]), lock=True)
        suffix = "old" if op["state"] == "rollback_pending" else "new"
        if row is None or any(
            row[key] != op[f"{suffix}_{key}"]
            for key in ("published_at", "metadata_observed_at", "updated_at")
        ):
            raise ValueError("backfill_source_changed")
        return op

    def _intent(self, c, run_id, video_id, page, space, old_revision, new_revision):
        values = (
            self.context.workspace_id,
            run_id,
            video_id,
            page["id"],
            old_revision,
            new_revision,
        )
        row = c.execute(
            "SELECT * FROM metadata_backfill_wiki_intents WHERE workspace_id=%s AND run_id=%s AND video_id=%s AND page_id=%s AND old_revision=%s AND new_revision=%s",
            values,
        ).fetchone()
        if row:
            return row
        payload = {
            "space_id": space["id"],
            "video_id": video_id,
            "revision": new_revision,
            "scope_version": space["scope_version"],
            "metadata_backfill_run_id": run_id,
        }
        key = "metadata-backfill:" + _candidate_hash(list(values))
        job_id = self.store.enqueue_job(
            c, kind="wiki_integrate", dedupe_key=key, payload=payload
        )
        row = c.execute(
            "INSERT INTO metadata_backfill_wiki_intents(workspace_id,run_id,video_id,page_id,old_revision,new_revision,before_version,job_id,state,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'pending',clock_timestamp(),clock_timestamp()) RETURNING *",
            (*values, page["version"], job_id),
        ).fetchone()
        payload["metadata_backfill_intent_id"] = row["id"]
        c.execute(
            "UPDATE assistant_jobs SET payload_json=%s WHERE workspace_id=%s AND principal_id=%s AND id=%s",
            (Jsonb(payload), self.context.workspace_id, self.context.user_id, job_id),
        )
        c.execute(
            "INSERT INTO metadata_backfill_job_holds(workspace_id,job_id,run_id,video_id,reason,created_at) VALUES(%s,%s,%s,%s,'wiki_rebind_intent_pending',clock_timestamp())",
            (self.context.workspace_id, job_id, run_id, video_id),
        )
        return row

    def _claim(self, c, run_id, job_id):
        from shiliu.storage.scheduler import recover_job

        # Only this service's durable held intents can enter this path. Their
        # work is deterministic; there is no model dispatch to replay.
        recover_job(c, self.context, job_id, disposition="replay_safe")
        job = claim_backfill_job(
            c, self.context, "metadata-backfill", job_id=job_id, run_id=run_id
        )
        if job:
            job["payload"] = json_value(job["payload_json"])
        return job

    def _maintain_existing_source(self, run_id, video_id, old_revision):
        if self.sources is None:
            raise ValueError("existing_source_head_requires_artifact_resolver")
        old = self.sources._capture_or_load(video_id, old_revision)
        captured = self.sources.snapshots.capture(
            video_id,
            publish_guard=lambda c: self._maintenance_guard(c, run_id, video_id),
        )
        result = {
            "old_head_revision": old_revision,
            "new_head_revision": captured.revision,
            "snapshot_ref": captured.snapshot_ref,
            "card": "missing",
            "wiki_rebound_pages": [],
            "wiki_deferred_pages": [],
        }
        card = self.wiki.get_source_card(old_revision)
        if card is not None and self.wiki._card_body_equivalent(
            old.snapshot, captured.snapshot, card
        ):
            card = dict(
                card,
                published_at=captured.snapshot["metadata"].get("published_at"),
                metadata_observed_at=captured.snapshot["metadata"].get(
                    "metadata_observed_at"
                ),
                memberships=captured.snapshot["memberships"],
            )
            with self.db.connect(guard=True) as c:
                self._maintenance_guard(c, run_id, video_id)
                self.wiki._commit_source_card(
                    captured,
                    input_hash=self.wiki._card_input_hash(captured.snapshot),
                    card=card,
                    conn=c,
                )
            result["card"] = "reused_time_only"
        elif card is not None:
            result["card"] = "deferred_for_rejudgment"
        with self.db.connect(read_only=True) as c:
            pages = c.execute(
                "SELECT DISTINCT p.* FROM assistant_wiki_dependencies d JOIN assistant_wiki_pages p ON (p.workspace_id,p.id)=(d.workspace_id,d.page_id) WHERE d.workspace_id=%s AND d.video_id=%s AND d.source_revision=%s AND p.principal_id=%s AND p.status='active'",
                (
                    self.context.workspace_id,
                    video_id,
                    old_revision,
                    self.context.user_id,
                ),
            ).fetchall()
        for raw in pages:
            page = self.wiki._decode_page(dict(raw))
            space = self.store.get_space(int(page["space_id"]))
            with self.db.connect(guard=True) as c:
                self._maintenance_guard(c, run_id, video_id)
                intent = self._intent(
                    c, run_id, video_id, page, space, old_revision, captured.revision
                )
            if intent["state"] != "pending":
                continue
            searchable = " ".join(
                [page.get("summary") or ""]
                + [
                    str(b.get(k) or "")
                    for b in page["blocks"]
                    for k in ("heading", "markdown", "applicability", "speaker")
                ]
            )
            if result["card"] != "reused_time_only" or re.search(
                r"\b(?:19|20)\d{2}\b", searchable
            ):
                continue
            prepared = self.wiki._prepare_sources_for_write(space_id=int(space["id"]))
            prepared[captured.revision] = captured.snapshot
            try:
                with self.db.connect(guard=True) as c:
                    self._maintenance_guard(c, run_id, video_id)
                    job = self._claim(c, run_id, intent["job_id"])
                    if job is None:
                        continue
                    self.fault_injector("before_wiki_rebind")
                    outcome = self.wiki._rebind_equivalent_source(
                        page,
                        space=space,
                        video_id=video_id,
                        revision=captured.revision,
                        job=job,
                        conn=c,
                        prepared_sources=prepared,
                    )
                    state = "no_change" if outcome.get("no_change") else "rebound"
                    c.execute(
                        "UPDATE metadata_backfill_wiki_intents SET state=%s,after_version=%s,updated_at=clock_timestamp() WHERE workspace_id=%s AND id=%s AND state='pending'",
                        (
                            state,
                            outcome["version"],
                            self.context.workspace_id,
                            intent["id"],
                        ),
                    )
                    c.execute(
                        "DELETE FROM metadata_backfill_job_holds WHERE workspace_id=%s AND job_id=%s",
                        (self.context.workspace_id, job["id"]),
                    )
            except StorageError:
                raise
            except (CoordinationConflict, RuntimeError):
                # Claim, page and intent are one transaction: failed writes keep
                # the original held queued Job, with no fabricated epoch.
                pass
        with self.db.connect(guard=True) as c:
            self._maintenance_guard(c, run_id, video_id)
            rows = c.execute(
                "SELECT * FROM metadata_backfill_wiki_intents WHERE workspace_id=%s AND run_id=%s AND video_id=%s AND old_revision=%s AND new_revision=%s ORDER BY id",
                (
                    self.context.workspace_id,
                    run_id,
                    video_id,
                    old_revision,
                    captured.revision,
                ),
            ).fetchall()
            result["wiki_rebound_pages"] = [
                {
                    "page_id": r["page_id"],
                    "version": r["after_version"],
                    "intent_id": r["id"],
                    "old_revision": old_revision,
                    "new_revision": captured.revision,
                }
                for r in rows
                if r["state"] == "rebound"
            ]
            result["wiki_deferred_pages"] = [
                r["page_id"] for r in rows if r["state"] == "pending"
            ]
            jobs = c.execute(
                "SELECT h.job_id FROM metadata_backfill_job_holds h JOIN assistant_jobs j ON (j.workspace_id,j.id)=(h.workspace_id,h.job_id) WHERE h.workspace_id=%s AND h.run_id=%s AND h.video_id=%s AND j.principal_id=%s AND j.kind='source_reconcile' ORDER BY h.job_id",
                (self.context.workspace_id, run_id, video_id, self.context.user_id),
            ).fetchall()
            for row in jobs:
                job = self._claim(c, run_id, row["job_id"])
                if job:
                    job_transition(
                        c,
                        self.context,
                        job["id"],
                        job["lease_owner"],
                        job["lease_epoch"],
                        action="complete",
                    )
                    c.execute(
                        "DELETE FROM metadata_backfill_job_holds WHERE workspace_id=%s AND job_id=%s",
                        (self.context.workspace_id, job["id"]),
                    )
        return result

    def _maintain_and_persist(self, run_id, video_id, old_revision):
        result = self._maintain_existing_source(run_id, video_id, old_revision)
        self.fault_injector("after_wiki_commit_before_operation_summary")
        with self.db.connect(guard=True) as c:
            op = self._maintenance_guard(c, run_id, video_id)
            maintenance = (
                result
                if op["state"] == "applied"
                else {"apply": json_value(op["maintenance_json"]), "rollback": result}
            )
            c.execute(
                "UPDATE metadata_backfill_operations SET new_head_revision=%s,maintenance_json=%s,written_at=clock_timestamp() WHERE workspace_id=%s AND run_id=%s AND video_id=%s",
                (
                    result["new_head_revision"],
                    Jsonb(maintenance),
                    self.context.workspace_id,
                    run_id,
                    video_id,
                ),
            )
        return result

    def _wiki_versions_match(self, c, run_id, video_id, maintenance):
        for item in maintenance.get("wiki_rebound_pages", []):
            intent = c.execute(
                "SELECT state FROM metadata_backfill_wiki_intents WHERE workspace_id=%s AND run_id=%s AND video_id=%s AND id=%s",
                (self.context.workspace_id, run_id, video_id, item["intent_id"]),
            ).fetchone()
            later = c.execute(
                "SELECT count(*) AS n FROM metadata_backfill_wiki_intents WHERE workspace_id=%s AND run_id=%s AND page_id=%s AND id>%s AND state='rebound'",
                (self.context.workspace_id, run_id, item["page_id"], item["intent_id"]),
            ).fetchone()["n"]
            page = c.execute(
                "SELECT version FROM assistant_wiki_pages WHERE workspace_id=%s AND principal_id=%s AND id=%s FOR UPDATE",
                (self.context.workspace_id, self.context.user_id, item["page_id"]),
            ).fetchone()
            if (
                not intent
                or intent["state"] != "rebound"
                or not page
                or page["version"] != item["version"] + later
            ):
                return False
        return True

    def _retire_rollback_intents(self, c, run_id, video_id):
        # Rollback supersedes queued forward-only maintenance. Complete it via
        # the real lease/lane, never by overwriting a live owner's Job state.
        rows = c.execute(
            "SELECT i.id,i.job_id,p.version FROM metadata_backfill_wiki_intents i JOIN assistant_wiki_pages p ON (p.workspace_id,p.id)=(i.workspace_id,i.page_id) WHERE i.workspace_id=%s AND i.run_id=%s AND i.video_id=%s AND i.state='pending' AND p.principal_id=%s ORDER BY i.id",
            (self.context.workspace_id, run_id, video_id, self.context.user_id),
        ).fetchall()
        pending = False
        for row in rows:
            job = self._claim(c, run_id, row["job_id"])
            if job is None:
                pending = True
                continue
            job_transition(
                c,
                self.context,
                job["id"],
                job["lease_owner"],
                job["lease_epoch"],
                action="complete",
            )
            c.execute(
                "UPDATE metadata_backfill_wiki_intents SET state='no_change',after_version=%s,updated_at=clock_timestamp() WHERE workspace_id=%s AND id=%s",
                (row["version"], self.context.workspace_id, row["id"]),
            )
            c.execute(
                "DELETE FROM metadata_backfill_job_holds WHERE workspace_id=%s AND job_id=%s",
                (self.context.workspace_id, job["id"]),
            )
        # A no-head operation cannot capture a source snapshot. Its obsolete
        # reconcile intents are retired through the same local Job lease.
        jobs = c.execute(
            "SELECT h.job_id FROM metadata_backfill_job_holds h JOIN assistant_jobs j ON (j.workspace_id,j.id)=(h.workspace_id,h.job_id) WHERE h.workspace_id=%s AND h.run_id=%s AND h.video_id=%s AND j.principal_id=%s AND j.kind='source_reconcile' ORDER BY h.job_id",
            (self.context.workspace_id, run_id, video_id, self.context.user_id),
        ).fetchall()
        for row in jobs:
            job = self._claim(c, run_id, row["job_id"])
            if job is None:
                pending = True
                continue
            job_transition(
                c,
                self.context,
                job["id"],
                job["lease_owner"],
                job["lease_epoch"],
                action="complete",
            )
            c.execute(
                "DELETE FROM metadata_backfill_job_holds WHERE workspace_id=%s AND job_id=%s",
                (self.context.workspace_id, job["id"]),
            )
        return not pending

    def rollback(self, run_id, *, production_backup_manifest=None):
        self._backup(production_backup_manifest)
        counts = {}
        for original in self._operations(run_id, reverse=True):
            video_id = original["video_id"]
            if original["state"] not in {"applied", "rollback_pending"}:
                continue
            if original["state"] == "applied" and original["old_head_revision"]:
                # Recover a committed page/intent whose operation summary was
                # lost before evaluating the rollback fence.
                if not json_value(original["maintenance_json"]):
                    self._maintain_and_persist(
                        run_id, video_id, original["old_head_revision"]
                    )
            with self.db.connect(guard=True) as c:
                op = self._operation_guard(c, run_id, video_id)
                row = self._target(c, json_value(op["candidate_json"]), lock=True)
                maintenance = json_value(op["maintenance_json"])
                suffix = "old" if op["state"] == "rollback_pending" else "new"
                valid = row is not None and all(
                    row[k] == op[f"{suffix}_{k}"]
                    for k in ("published_at", "metadata_observed_at", "updated_at")
                )
                valid = valid and row["head_revision"] in (
                    {op["old_head_revision"], op["new_head_revision"]}
                    if suffix == "old"
                    else {op["new_head_revision"]}
                )
                valid = valid and self._wiki_versions_match(
                    c, run_id, video_id, maintenance
                )
                if not valid:
                    c.execute(
                        "UPDATE metadata_backfill_operations SET state='rollback_conflict',detail='current_state_changed' WHERE workspace_id=%s AND run_id=%s AND video_id=%s",
                        (self.context.workspace_id, run_id, video_id),
                    )
                    counts["rollback_conflict"] = counts.get("rollback_conflict", 0) + 1
                    continue
                if op["state"] == "applied":
                    c.execute(
                        "UPDATE videos SET published_at=%s,metadata_observed_at=%s,updated_at=%s WHERE workspace_id=%s AND id=%s",
                        (
                            op["old_published_at"],
                            op["old_metadata_observed_at"],
                            op["old_updated_at"],
                            self.context.workspace_id,
                            video_id,
                        ),
                    )
                    self.db._touch(
                        c, video_id, reason="metadata_backfill_rollback:" + run_id
                    )
                    gen = c.execute(
                        "SELECT dirty_generation FROM assistant_source_dirty WHERE workspace_id=%s AND video_id=%s",
                        (self.context.workspace_id, video_id),
                    ).fetchone()
                    self._hold(
                        c, run_id, video_id, gen["dirty_generation"] if gen else None
                    )
                    c.execute(
                        "UPDATE metadata_backfill_operations SET state='rollback_pending',detail='rollback_pending' WHERE workspace_id=%s AND run_id=%s AND video_id=%s",
                        (self.context.workspace_id, run_id, video_id),
                    )
            if op["old_head_revision"]:
                self._maintain_and_persist(run_id, video_id, op["new_head_revision"])
            with self.db.connect(guard=True) as c:
                self._maintenance_guard(c, run_id, video_id)
                if not self._retire_rollback_intents(c, run_id, video_id):
                    counts["rollback_pending"] = counts.get("rollback_pending", 0) + 1
                    continue
                c.execute(
                    "UPDATE metadata_backfill_operations SET state='rolled_back',detail='rolled_back',written_at=clock_timestamp() WHERE workspace_id=%s AND run_id=%s AND video_id=%s",
                    (self.context.workspace_id, run_id, video_id),
                )
            counts["rolled_back"] = counts.get("rolled_back", 0) + 1
        with self.db.connect(guard=True) as c:
            self._run(c, run_id, lock=True)
            c.execute(
                "UPDATE metadata_backfill_runs SET state='rolled_back',updated_at=clock_timestamp() WHERE workspace_id=%s AND run_id=%s",
                (self.context.workspace_id, run_id),
            )
        return {"run_id": run_id, "counts": counts}


def dry_run(db, candidates):
    return MetadataBackfillService(db).dry_run(candidates)


def stage(db, run_id, candidates, **kwargs):
    return MetadataBackfillService(db).stage(run_id, candidates, **kwargs)


def apply(db, run_id, *, artifacts=None, **kwargs):
    return MetadataBackfillService(db, artifacts).apply(run_id, **kwargs)


def rollback(db, run_id, *, artifacts=None, **kwargs):
    return MetadataBackfillService(db, artifacts).rollback(run_id, **kwargs)


def _load_candidates(path):
    value = json.loads(Path(path).read_text())
    if isinstance(value, dict):
        value = value["candidates"]
    if not isinstance(value, list):
        raise ValueError("candidate_manifest_not_list")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Explicit PostgreSQL publication timestamp backfill"
    )
    parser.add_argument("action", choices=["dry-run", "stage", "apply", "rollback"])
    parser.add_argument("--run-id")
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--production-backup-manifest", type=Path)
    args = parser.parse_args(argv)
    if args.action in {"stage", "apply", "rollback"} and not args.run_id:
        parser.error("--run-id required")
    if args.action in {"dry-run", "stage"} and not args.candidates:
        parser.error("--candidates required")
    from shiliu.app import Application

    with Application() as app:
        service = MetadataBackfillService(app.db, app.artifacts)
        options = {"production_backup_manifest": args.production_backup_manifest}
        result = (
            service.dry_run(_load_candidates(args.candidates))
            if args.action == "dry-run"
            else service.stage(
                args.run_id, _load_candidates(args.candidates), **options
            )
            if args.action == "stage"
            else getattr(service, args.action)(args.run_id, **options)
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
