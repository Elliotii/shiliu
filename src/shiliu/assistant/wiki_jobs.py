"""Bounded Wiki effective-projection tasks on retrieval_projection_tasks."""

from __future__ import annotations
from psycopg.types.json import Jsonb
from shiliu.assistant.lease_renewal import LeaseRenewal, check_renewal, renewal_period
from shiliu.assistant.sources import SourceScope
from shiliu.assistant.wiki_projection import digest
from shiliu.assistant.runtime_contract import AssistantConflict
from shiliu.retrieval.dense import _validate_vector


class WikiProjectionStale(AssistantConflict):
    pass


class WikiProjectionWorker:
    def __init__(self, index, *, owner, lease_seconds=120, heartbeat_interval=None):
        self.index = index
        self.db = index.db
        self.owner = owner
        self.lease_seconds = lease_seconds
        self.heartbeat_interval = renewal_period(lease_seconds, heartbeat_interval)

    def _lock(self, c, claim):
        row = c.execute(
            "SELECT * FROM retrieval_projection_tasks WHERE workspace_id=%s AND domain='wiki' AND id=%s FOR UPDATE",
            (self.db.workspace_id, claim["id"]),
        ).fetchone()
        if (
            row is None
            or row["status"] != "running"
            or row["lease_owner"] != self.owner
            or row["lease_epoch"] != claim["lease_epoch"]
            or row["requested_generation"] != claim["requested_generation"]
            or row["payload"] != claim["payload"]
            or not c.execute(
                "SELECT %s::timestamptz>clock_timestamp() AS live",
                (row["lease_until"],),
            ).fetchone()["live"]
        ):
            raise WikiProjectionStale("wiki_projection_fenced")
        return row

    def claim(self, *, seconds=120):
        if not self.owner or not 0 < seconds <= 120:
            raise ValueError("invalid_projection_lease")
        with self.db.connect() as c:
            row = c.execute(
                "SELECT * FROM retrieval_projection_tasks WHERE workspace_id=%s AND domain='wiki' "
                "AND status IN ('queued','retry_wait') AND not_before<=clock_timestamp() "
                "AND payload->>'principal_id'=%s AND EXISTS (SELECT 1 FROM jsonb_each(payload->'requests') r "
                "WHERE r.value->>'profile_id'=%s AND coalesce(payload->'request_states'->>r.key,'pending')='pending') "
                "ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1",
                (
                    self.db.workspace_id,
                    self.db.context.user_id,
                    self.index.profile.profile_id if self.index.profile else None,
                ),
            ).fetchone()
            if row is None:
                return None
            if row["payload"].get("principal_id") != self.db.context.user_id:
                raise AssistantConflict("wiki_projection_owner_mismatch")
            payload = dict(row["payload"])
            attempts = dict(payload.get("request_attempts", {}))
            selected = self._selected(payload)
            for key in selected:
                attempts[key] = int(attempts.get(key, 0)) + 1
            payload["request_attempts"] = attempts
            return c.execute(
                "UPDATE retrieval_projection_tasks SET status='running',attempt=%s,payload=%s,lease_epoch=lease_epoch+1,lease_owner=%s,"
                "lease_until=clock_timestamp()+%s*interval '1 second',updated_at=clock_timestamp() WHERE id=%s RETURNING *",
                (
                    max(attempts[k] for k in selected),
                    Jsonb(payload),
                    self.owner,
                    seconds,
                    row["id"],
                ),
            ).fetchone()

    def _selected(self, payload):
        profile = self.index.profile.profile_id if self.index.profile else None
        return {
            key: request
            for key, request in payload["requests"].items()
            if request["profile_id"] == profile
            and payload.get("request_states", {}).get(key, "pending") == "pending"
        }

    def heartbeat(self, claim):
        with self.db.connect() as c:
            self._lock(c, claim)
            c.execute(
                "UPDATE retrieval_projection_tasks SET lease_until=clock_timestamp()+%s*interval '1 second',updated_at=clock_timestamp() WHERE id=%s",
                (self.lease_seconds, claim["id"]),
            )

    def recover(self):
        count = 0
        with self.db.connect() as c:
            rows = c.execute(
                "SELECT * FROM retrieval_projection_tasks WHERE workspace_id=%s AND domain='wiki' AND payload->>'principal_id'=%s AND status='running' ORDER BY id FOR UPDATE SKIP LOCKED",
                (self.db.workspace_id, self.db.context.user_id),
            ).fetchall()
            for row in rows:
                if c.execute(
                    "SELECT %s::timestamptz<=clock_timestamp() AS expired",
                    (row["lease_until"],),
                ).fetchone()["expired"]:
                    payload = dict(row["payload"])
                    states = dict(payload.get("request_states", {}))
                    for key in payload["requests"]:
                        if (
                            states.get(key, "pending") == "pending"
                            and payload.get("request_attempts", {}).get(key, 0) >= 5
                        ):
                            states[key] = "failed"
                    payload["request_states"] = states
                    pending = any(
                        states.get(k, "pending") == "pending"
                        for k in payload["requests"]
                    )
                    c.execute(
                        "UPDATE retrieval_projection_tasks SET status=%s,payload=%s,lease_owner=NULL,lease_until=NULL,last_error='lease_expired',updated_at=clock_timestamp() WHERE id=%s",
                        (
                            "retry_wait" if pending else "failed",
                            Jsonb(payload),
                            row["id"],
                        ),
                    )
                    count += 1
        return count

    def requeue_failed(self, resource_key):
        with self.db.connect(guard=True) as c:
            row = c.execute(
                "SELECT * FROM retrieval_projection_tasks WHERE workspace_id=%s AND domain='wiki' AND resource_key=%s FOR UPDATE",
                (self.db.workspace_id, resource_key),
            ).fetchone()
            if (
                row is None
                or row["payload"].get("principal_id") != self.db.context.user_id
            ):
                raise AssistantConflict("wiki_projection_owner_mismatch")
            if row["status"] != "failed":
                return False
            payload = dict(row["payload"])
            payload["request_states"] = {
                k: v
                for k, v in payload.get("request_states", {}).items()
                if v != "failed"
            }
            payload["request_attempts"] = {}
            c.execute(
                "UPDATE retrieval_projection_tasks SET payload=%s,status='queued',attempt=0,requested_generation=requested_generation+1,not_before=clock_timestamp(),last_error=NULL,updated_at=clock_timestamp() WHERE id=%s",
                (Jsonb(payload), row["id"]),
            )
            return True

    def compute(self, claim):
        if self.index.provider is None:
            raise RuntimeError("wiki_embedding_provider_unavailable")
        computed = []
        for request in self._selected(claim["payload"]).values():
            if request["profile_id"] != self.index.profile.profile_id:
                continue
            desc = request["scope"]
            scope = (
                SourceScope(
                    frozenset(desc["source_ids"]),
                    frozenset(desc["video_ids"]),
                    desc["all_active"],
                )
                if desc
                else None
            )
            prepared = self.index.projections.prepare_sources(
                request["space_id"], page_id=request["page_id"]
            )
            snap = self.index.projections.capture(
                request["space_id"],
                scope=scope,
                thread_id=request["thread_id"],
                page_id=request["page_id"],
                prepared=prepared,
            )
            pages = snap["pages"]
            if not pages or pages[0]["effective_hash"] != request["effective_hash"]:
                # Carry the actual obsolete snapshot into publication; omission
                # alone is not proof that a pending request has become stale.
                computed.append((request, scope, snap, [], [], prepared))
                continue
            windows = self.index.windows(snap)
            if (
                len(windows) != request["window_count"]
                or digest(sorted(e["window_id"] for e in windows))
                != request["window_set_hash"]
            ):
                raise RuntimeError("wiki_window_policy_changed")
            if any(e["policy"] != "wiki-effective-windows-v1" for e in windows):
                raise RuntimeError("wiki_tokenizer_unavailable")
            vectors = []
            for start in range(0, len(windows), 8):
                batch = windows[start : start + 8]
                encoded = self.index.provider.embed_documents(
                    [e["text"] for e in batch]
                )
                if len(encoded) != len(batch):
                    raise ValueError("wiki_embedding_batch_mismatch")
                vectors.extend(_validate_vector(v, 512) for v in encoded)
            computed.append((request, scope, snap, windows, vectors, prepared))
        return computed

    def publish(self, claim, computed):
        # guard -> thread -> task -> page -> windows/vectors. All encoding and
        # historical Artifact preparation happened before entering this block.
        check_renewal()
        with self.db.connect(guard=True) as c:
            threads = sorted({r[0]["thread_id"] for r in computed if r[0]["thread_id"]})
            for thread in threads:
                if not c.execute(
                    "SELECT id FROM assistant_threads WHERE workspace_id=%s AND principal_id=%s AND id=%s FOR UPDATE",
                    (self.db.workspace_id, self.db.context.user_id, thread),
                ).fetchone():
                    raise WikiProjectionStale("wiki_thread_missing")
            self._lock(c, claim)
            c.execute(
                "SELECT id FROM assistant_wiki_pages WHERE workspace_id=%s AND principal_id=%s AND id=%s FOR UPDATE",
                (self.db.workspace_id, self.db.context.user_id, claim["resource_key"]),
            ).fetchall()
            # A page lock can itself wait across expiry after the task lock.
            self._lock(c, claim)
            self.index.profile.register(c)
            all_entries = []
            for request, scope, snapshot, entries, vectors, prepared in computed:
                try:
                    now = self.index.projections.capture(
                        request["space_id"],
                        scope=scope,
                        thread_id=request["thread_id"],
                        page_id=request["page_id"],
                        conn=c,
                        prepared=prepared,
                    )
                except AssistantConflict as exc:
                    raise WikiProjectionStale(
                        "wiki_projection_dependencies_changed"
                    ) from exc
                if now["snapshot_hash"] != snapshot["snapshot_hash"]:
                    raise WikiProjectionStale("wiki_projection_dependencies_changed")
                if (
                    not entries
                    and now["pages"]
                    and now["pages"][0]["effective_hash"] == request["effective_hash"]
                ):
                    raise WikiProjectionStale("wiki_projection_request_unprocessed")
                for e, v in zip(entries, vectors, strict=True):
                    c.execute(
                        "INSERT INTO wiki_windows(window_id,workspace_id,page_id,block_id,page_version,projection_hash,window_no,text,tokenized_text,search_vector,dependency_versions,created_at) "
                        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,to_tsvector('simple',%s),%s,clock_timestamp()) "
                        "ON CONFLICT(window_id) DO UPDATE SET page_version=excluded.page_version,dependency_versions=excluded.dependency_versions",
                        (
                            e["window_id"],
                            self.db.workspace_id,
                            e["page_id"],
                            e["block_id"],
                            e["page_version"],
                            e["projection_hash"],
                            e["window_no"],
                            e["text"],
                            e["tokenized_text"],
                            e["tokenized_text"],
                            Jsonb(e["dependency_versions"]),
                        ),
                    )
                    c.execute(
                        "INSERT INTO wiki_embeddings(window_id,profile_id,embedding_text_hash,embedding,updated_at) VALUES(%s,%s,%s,%s,clock_timestamp()) "
                        "ON CONFLICT(window_id,profile_id) DO UPDATE SET embedding_text_hash=excluded.embedding_text_hash,embedding=excluded.embedding,updated_at=excluded.updated_at",
                        (
                            e["window_id"],
                            self.index.profile.profile_id,
                            e["text_hash"],
                            v,
                        ),
                    )
                all_entries.extend(entries)
            if all_entries and len(
                self.index._current_rows(c, all_entries, self.index.profile.profile_id)
            ) == len({e["window_id"] for e in all_entries}):
                c.execute(
                    "INSERT INTO assistant_runtime_state(workspace_id,principal_id,key,value,embedding_domain,embedding_profile_id,updated_at) "
                    "VALUES(%s,%s,'active_profile:wiki',%s,'wiki',%s,clock_timestamp()) ON CONFLICT(workspace_id,principal_id,key) DO UPDATE SET "
                    "value=excluded.value,embedding_profile_id=excluded.embedding_profile_id,updated_at=excluded.updated_at",
                    (
                        self.db.workspace_id,
                        self.db.context.user_id,
                        self.index.profile.profile_id,
                        self.index.profile.profile_id,
                    ),
                )
            # Retain up to eight actual effective request projections for a page;
            # no enumeration of possible future task combinations or truncation.
            keep = [
                e["window_id"] for _, _, _, entries, _, _ in computed for e in entries
            ]
            if all_entries:
                c.execute(
                    "DELETE FROM wiki_windows WHERE workspace_id=%s AND page_id=%s AND window_id<>ALL(%s) "
                    "AND dependency_versions NOT IN (SELECT dependency_versions FROM wiki_windows WHERE workspace_id=%s AND page_id=%s GROUP BY dependency_versions ORDER BY max(created_at) DESC,dependency_versions LIMIT 8)",
                    (
                        self.db.workspace_id,
                        claim["resource_key"],
                        keep,
                        self.db.workspace_id,
                        claim["resource_key"],
                    ),
                )
            self._lock(c, claim)
            selected = self._selected(claim["payload"])
            if not selected:
                raise WikiProjectionStale("wiki_projection_profile_mismatch")
            payload = dict(claim["payload"])
            states = dict(payload.get("request_states", {}))
            built = [r[0] for r in computed if r[3]]
            obsolete = [r[0] for r in computed if not r[3]]
            for key, request in selected.items():
                if request not in built and request not in obsolete:
                    raise WikiProjectionStale("wiki_projection_request_unprocessed")
                states[key] = "completed" if request in built else "stale"
            payload["request_states"] = states
            pending = any(
                states.get(k, "pending") == "pending" for k in payload["requests"]
            )
            failed = any(states.get(k) == "failed" for k in payload["requests"])
            status = "queued" if pending else "failed" if failed else "completed"
            c.execute(
                "UPDATE retrieval_projection_tasks SET status=%s,payload=%s,lease_owner=NULL,lease_until=NULL,last_error=NULL,updated_at=clock_timestamp() WHERE id=%s",
                (status, Jsonb(payload), claim["id"]),
            )

        return {
            "status": "ready" if all_entries else "stale",
            "windows": len(all_entries),
            "generation": claim["requested_generation"],
        }

    def fail(self, claim, error):
        with self.db.connect() as c:
            self._lock(c, claim)
            payload = dict(claim["payload"])
            states = dict(payload.get("request_states", {}))
            selected = self._selected(payload)
            for key in selected:
                if payload.get("request_attempts", {}).get(key, claim["attempt"]) >= 5:
                    states[key] = "failed"
            payload["request_states"] = states
            pending = any(
                states.get(k, "pending") == "pending" for k in payload["requests"]
            )
            c.execute(
                "UPDATE retrieval_projection_tasks SET status=%s,payload=%s,lease_owner=NULL,lease_until=NULL,last_error=%s,not_before=clock_timestamp()+%s*interval '1 second',updated_at=clock_timestamp() WHERE id=%s",
                (
                    "retry_wait" if pending else "failed",
                    Jsonb(payload),
                    type(error).__name__,
                    min(300, 10 * 2 ** (claim["attempt"] - 1)),
                    claim["id"],
                ),
            )

    def run_once(self):
        claim = self.claim(seconds=self.lease_seconds)
        if claim is None:
            return None
        try:
            with LeaseRenewal(
                lambda: self.heartbeat(claim),
                interval=self.heartbeat_interval,
                fenced=WikiProjectionStale,
            ):
                return self.publish(claim, self.compute(claim))
        except WikiProjectionStale as exc:
            try:
                self.fail(claim, exc)
            except WikiProjectionStale:
                pass
            return {"status": "stale", "reason": str(exc)}
        except Exception as exc:
            try:
                self.fail(claim, exc)
            except WikiProjectionStale:
                return {"status": "stale", "reason": "wiki_projection_fenced"}
            return {"status": "retry_wait", "error_code": type(exc).__name__}
