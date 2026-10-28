"""PG retrieval over the current effective Wiki windows; no raw-page index."""

from __future__ import annotations
from hashlib import sha256
import time
import unicodedata
from psycopg.types.json import Jsonb
from shiliu.retrieval.lexical import F1Tokenizer
from shiliu.retrieval.dense import _validate_vector
from shiliu.storage.embedding_profiles import DocumentProfile
from shiliu.assistant.wiki_projection import WikiProjection, canonical, digest
from shiliu.assistant.runtime_contract import AssistantConflict

WIKI_QUERY_INSTRUCTION = (
    "Given a Chinese or English knowledge or personal experience query, "
    "retrieve relevant knowledge passages, including applicable conditions and personal notes."
)
PROJECTION_VERSION = "wiki-effective-windows-v1"
QUERY_VERSION = "wiki-query-v1"
FALLBACK_VERSION = "lexical-fallback-v1"
MAX_REQUESTS = 8
MAX_SCOPE_BYTES = 32768


class WikiHybridIndex:
    def __init__(self, provider, *, wiki):
        self.provider = provider
        self.wiki = wiki
        self.db = wiki.db
        self.projections = WikiProjection(wiki)
        self.tokenizer = F1Tokenizer()
        self.profile = (
            DocumentProfile(provider, PROJECTION_VERSION)
            if provider is not None
            else None
        )

    def _block_windows(self, page, block, *, force_fallback=False):
        text = str(block.get("markdown") or "")  # offsets address formal text
        title = "\n".join(
            [
                page["title"],
                " ".join(page.get("aliases", [])),
                block.get("heading") or "",
            ]
        )
        applicability = str(block.get("applicability") or "")
        prefix = title + "\n" + applicability
        policy = PROJECTION_VERSION
        try:
            if force_fallback or self.provider is None:
                raise RuntimeError("tokenizer_unavailable")
            prefix = self.provider.truncate_text(prefix, 120)
            result = []
            start = 0
            while start < len(text):
                low, high = (
                    start + 1,
                    min(len(text), start + max(1, 2000 - len(prefix) - 1)),
                )
                while low < high:
                    end = (low + high + 1) // 2
                    if (
                        self.provider.count_tokens(
                            unicodedata.normalize(
                                "NFKC", prefix + "\n" + text[start:end]
                            )
                        )
                        <= 512
                    ):
                        low = end
                    else:
                        high = end - 1
                end = low
                represented = unicodedata.normalize(
                    "NFKC", prefix + "\n" + text[start:end]
                )
                if (
                    self.provider.count_tokens(represented) > 512
                    or len(represented) > 2000
                ):
                    raise ValueError("wiki_window_input_too_large")
                result.append(dict(text=represented, start=start, end=end))
                if end == len(text):
                    break
                start = max(start + 1, end - min(80, (end - start) // 5))
            if not result:
                result = [dict(text=prefix, start=0, end=0)]
        except Exception:
            policy = FALLBACK_VERSION
            # Preserve title terms for lexical scoring; the displayed fallback
            # window is explicitly character bounded, never claimed token safe.
            result = [
                dict(
                    text=text[start : start + 512],
                    start=start,
                    end=min(len(text), start + 512),
                )
                for start in range(0, max(1, len(text)), 450)
            ]
        projection_hash = digest(
            {
                "prefix": prefix,
                "text": text,
                "policy": policy,
                "effective": page["effective_hash"],
            }
        )
        entries = []
        for number, window in enumerate(result):
            window_id = "wwin_" + digest(
                [page["id"], block["stable_id"], projection_hash, number]
            )
            entries.append(
                {
                    **window,
                    "window_id": window_id,
                    "page_id": page["id"],
                    "page_version": page["version"],
                    "block_id": block["stable_id"],
                    "projection_hash": projection_hash,
                    "window_no": number,
                    "text_hash": sha256(window["text"].encode()).hexdigest(),
                    "policy": policy,
                    "title_tokens": self.tokenizer.document(title),
                    "applicability_tokens": self.tokenizer.document(applicability),
                    "tokenized_text": self.tokenizer.document(window["text"]),
                    "title": unicodedata.normalize("NFKC", title).casefold(),
                    "dependency_versions": page["dependency_versions"],
                }
            )
        return entries

    def windows(self, snapshot):
        return [
            entry
            for page in snapshot["pages"]
            for block in page["blocks"]
            for entry in self._block_windows(page, block)
        ]

    def _current_rows(self, c, entries, profile_id):
        if not entries or profile_id is None:
            return set()
        result = set()
        for start in range(0, len(entries), 200):
            values = [
                {
                    k: e[k]
                    for k in (
                        "window_id",
                        "projection_hash",
                        "page_version",
                        "text_hash",
                    )
                }
                for e in entries[start : start + 200]
            ]
            rows = c.execute(
                "WITH current AS (SELECT * FROM jsonb_to_recordset(%s) AS v(window_id text,projection_hash text,page_version bigint,text_hash text)) "
                "SELECT w.window_id FROM current v JOIN wiki_windows w ON w.window_id=v.window_id AND w.workspace_id=%s "
                "AND w.projection_hash=v.projection_hash AND w.page_version=v.page_version JOIN wiki_embeddings e ON e.window_id=w.window_id "
                "AND e.profile_id=%s AND e.embedding_text_hash=v.text_hash",
                (Jsonb(values), self.db.workspace_id, profile_id),
            ).fetchall()
            result.update(r["window_id"] for r in rows)
        return result

    def enqueue(self, snapshot, entries, *, space_id, scope=None, thread_id=None):
        if not entries:
            return
        scope_payload = (
            {
                "source_ids": sorted(scope.source_db_ids),
                "video_ids": sorted(scope.video_ids),
                "all_active": scope.all_active,
            }
            if scope
            else None
        )
        if len(canonical(scope_payload).encode()) > MAX_SCOPE_BYTES:
            return "scope_projection_payload_too_large"
        failure = None
        request_identity = digest(
            [
                space_id,
                scope_payload,
                thread_id,
                self.profile.profile_id if self.profile else None,
            ]
        )
        for page in snapshot["pages"]:
            page_entries = [e for e in entries if e["page_id"] == page["id"]]
            if not page_entries:
                continue
            request = {
                "space_id": space_id,
                "scope": scope_payload,
                "thread_id": thread_id,
                "page_id": page["id"],
                "effective_hash": page["effective_hash"],
                "window_set_hash": digest(sorted(e["window_id"] for e in page_entries)),
                "window_count": len(page_entries),
                "profile_id": self.profile.profile_id if self.profile else None,
            }
            with self.db.connect(guard=True) as c:
                old = c.execute(
                    "SELECT * FROM retrieval_projection_tasks WHERE workspace_id=%s AND domain='wiki' AND resource_key=%s FOR UPDATE",
                    (self.db.workspace_id, page["id"]),
                ).fetchone()
                requests = dict(old["payload"].get("requests", {})) if old else {}
                states = dict(old["payload"].get("request_states", {})) if old else {}
                attempts = (
                    dict(old["payload"].get("request_attempts", {})) if old else {}
                )
                if old and old["status"] == "failed" and not states:
                    states = {key: "failed" for key in requests}
                if (
                    requests.get(request_identity) == request
                    and states.get(request_identity) == "failed"
                ):
                    failure = "wiki_projection_failed_manual_retry_required"
                    continue
                if requests.get(request_identity) == request and old["status"] in {
                    "queued",
                    "running",
                    "retry_wait",
                }:
                    continue
                states.pop(request_identity, None)
                attempts.pop(request_identity, None)
                requests.pop(request_identity, None)
                requests[request_identity] = request
                requests = dict(list(requests.items())[-MAX_REQUESTS:])
                payload = {
                    "principal_id": self.db.context.user_id,
                    "requests": requests,
                    "request_states": {
                        k: v for k, v in states.items() if k in requests
                    },
                    "request_attempts": {
                        k: v for k, v in attempts.items() if k in requests
                    },
                }
                c.execute(
                    "INSERT INTO retrieval_projection_tasks(workspace_id,domain,resource_key,requested_generation,payload,status,not_before,created_at,updated_at) "
                    "VALUES(%s,'wiki',%s,1,%s,'queued',clock_timestamp(),clock_timestamp(),clock_timestamp()) "
                    "ON CONFLICT(workspace_id,domain,resource_key) DO UPDATE SET requested_generation=retrieval_projection_tasks.requested_generation+1,"
                    "payload=excluded.payload,status='queued',attempt=0,not_before=clock_timestamp(),lease_owner=NULL,lease_until=NULL,updated_at=clock_timestamp()",
                    (self.db.workspace_id, page["id"], Jsonb(payload)),
                )
        return failure

    def search(
        self,
        pages_or_query=None,
        query=None,
        *,
        space_id=None,
        page_id=None,
        task_scope=None,
        thread_id=None,
        limit=3,
        before_validate=None,
    ):
        # Accept only query+trusted scope, never caller-supplied page text as authorization.
        if query is None:
            query = str(pages_or_query or "")
        if space_id is None:
            raise ValueError("wiki_space_required")
        started = time.monotonic()
        for attempt in range(2):
            try:
                snapshot = self.projections.capture(
                    space_id, scope=task_scope, thread_id=thread_id
                )
            except AssistantConflict as exc:
                if str(exc) == "wiki_snapshot_prepare_stale":
                    continue
                raise
            entries = self.windows(snapshot)
            if page_id is not None:
                entries = [entry for entry in entries if entry["page_id"] == page_id]
            result = self._rank(snapshot, entries, query, limit)
            if before_validate:
                before_validate(attempt)
            try:
                current = self.projections.capture(
                    space_id, scope=task_scope, thread_id=thread_id
                )
            except AssistantConflict as exc:
                if str(exc) == "wiki_snapshot_prepare_stale":
                    continue
                raise
            if current["snapshot_hash"] == snapshot["snapshot_hash"]:
                if result["coverage"]["missing_windows"]:
                    enqueue_failure = self.enqueue(
                        snapshot,
                        entries,
                        space_id=space_id,
                        scope=task_scope,
                        thread_id=thread_id,
                    )
                    if enqueue_failure:
                        result["coverage"]["degraded_reason"] = enqueue_failure
                result["coverage"].update(
                    reprojections=attempt,
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                    snapshot_hash=snapshot["snapshot_hash"],
                )
                return result
        return {
            "source": "wiki",
            "status": "partial",
            "candidates": [],
            "error_code": "wiki_dependencies_changing",
            "retryable": True,
            "coverage": {
                "query": query,
                "reprojections": 1,
                "retrieval_method": "fts",
                "degraded_reason": "dependency_retry_required",
            },
        }

    def _rank(self, snapshot, entries, query, limit):
        terms = self.tokenizer.query(query)
        exact = unicodedata.normalize("NFKC", query).casefold().strip()
        by_id = {e["window_id"]: e for e in entries}
        lexical = []
        dense = []
        missing = len(entries)
        reason = None
        vector = None
        if self.provider is not None and query.strip():
            try:
                vector = _validate_vector(
                    self.provider.embed_query(
                        query, instruction=WIKI_QUERY_INSTRUCTION
                    ),
                    512,
                )
            except Exception as exc:
                reason = type(exc).__name__
        elif self.provider is None:
            reason = "embedding_provider_unavailable"
        with self.db.connect(read_only=True) as c:
            current = self._current_rows(
                c, entries, self.profile.profile_id if self.profile else None
            )
            missing = len(entries) - len(current)
            active = c.execute(
                "SELECT embedding_profile_id FROM assistant_runtime_state WHERE workspace_id=%s AND principal_id=%s AND embedding_domain='wiki'",
                (self.db.workspace_id, self.db.context.user_id),
            ).fetchone()
            if (
                not active
                or self.profile is None
                or active["embedding_profile_id"] != self.profile.profile_id
            ):
                vector = None
                reason = reason or "wiki_profile_not_active"
            # Each batch includes only this request's effective windows. Rank
            # before application-level RRF; never read all stored vectors.
            lexical_rows = []
            dense_rows = []
            for start in range(0, len(entries), 200):
                values = entries[start : start + 200]
                cte = (
                    "WITH current AS (SELECT * FROM jsonb_to_recordset(%s) AS v(window_id text,page_id text,block_id text,page_version bigint,projection_hash text,text_hash text,title text,title_tokens text,applicability_tokens text,tokenized_text text)), "
                    "ranked AS (SELECT v.*,setweight(to_tsvector('simple',title_tokens),'A') || setweight(to_tsvector('simple',applicability_tokens),'B') || setweight(to_tsvector('simple',tokenized_text),'D') AS search_vector FROM current v) "
                )
                lexical_rows.extend(
                    c.execute(
                        cte
                        + " , scores AS (SELECT window_id,page_id,block_id,ts_rank(search_vector,to_tsquery('simple',%s)) AS score, "
                        "(%s<>'' AND position(%s in title)>0) AS exact FROM ranked WHERE (%s<>'' AND search_vector @@ to_tsquery('simple',%s)) OR (%s<>'' AND position(%s in title)>0) "
                        "), best AS (SELECT DISTINCT ON(page_id,block_id) * FROM scores ORDER BY page_id,block_id,exact DESC,score DESC,window_id) SELECT * FROM best ORDER BY exact DESC,score DESC,page_id,block_id,window_id LIMIT 20",
                        (
                            Jsonb(values),
                            terms,
                            exact,
                            exact,
                            terms,
                            terms,
                            exact,
                            exact,
                        ),
                    ).fetchall()
                )
                if vector is not None:
                    dense_rows.extend(
                        c.execute(
                            cte
                            + " , scores AS (SELECT v.window_id,v.page_id,v.block_id,1-(e.embedding <=> %s) AS score FROM ranked v "
                            "JOIN wiki_windows w ON w.workspace_id=%s AND w.window_id=v.window_id AND w.projection_hash=v.projection_hash AND w.page_version=v.page_version "
                            "JOIN wiki_embeddings e ON e.window_id=w.window_id AND e.profile_id=%s AND e.embedding_text_hash=v.text_hash "
                            "ORDER BY e.embedding <=> %s,v.page_id,v.block_id,v.window_id), best AS (SELECT DISTINCT ON(page_id,block_id) * FROM scores ORDER BY page_id,block_id,score DESC,window_id) SELECT * FROM best ORDER BY score DESC,page_id,block_id,window_id LIMIT 20",
                            (
                                Jsonb(values),
                                vector,
                                self.db.workspace_id,
                                self.profile.profile_id,
                                vector,
                            ),
                        ).fetchall()
                    )

            def block_best(rows, lexical=False):
                rows.sort(
                    key=lambda r: (
                        -int(r.get("exact", False)),
                        -float(r["score"]),
                        r["page_id"],
                        r["block_id"],
                        r["window_id"],
                    )
                )
                result = []
                seen = set()
                for row in rows:
                    key = (row["page_id"], row["block_id"])
                    if key not in seen:
                        seen.add(key)
                        result.append(row)
                return result[:20]

            lexical = block_best(lexical_rows, True)
            dense = block_best(dense_rows)
        ranks = {}
        positions = {}
        for channel, rows in [("lexical", lexical), ("dense", dense)]:
            for rank, row in enumerate(rows, 1):
                key = (row["page_id"], row["block_id"])
                ranks.setdefault(key, {})[channel] = rank
                positions.setdefault(key, by_id[row["window_id"]])
        ordered = sorted(
            ranks,
            key=lambda key: (-sum(1 / (60 + n) for n in ranks[key].values()), key),
        )
        pages = {p["id"]: p for p in snapshot["pages"]}
        candidates = {}
        for page_id, block_id in ordered:
            page = pages[page_id]
            block = next(b for b in page["blocks"] if b["stable_id"] == block_id)
            if page_id not in candidates:
                if len(candidates) >= min(3, max(0, limit)):
                    continue
                candidates[page_id] = {
                    "page_id": page_id,
                    "page_version": page["version"],
                    "version": page["version"],
                    "title": page["title"],
                    "availability": page["availability"],
                    "hits": [],
                }
            if len(candidates[page_id]["hits"]) >= 3:
                continue
            window = positions[(page_id, block_id)]
            text = block.get("markdown") or ""
            body_terms = self.tokenizer.tokens(
                text
                + " "
                + str(block.get("heading") or "")
                + " "
                + str(block.get("applicability") or "")
            )
            directory = "lexical" in ranks[(page_id, block_id)] and not set(
                self.tokenizer.tokens(query)
            ).intersection(body_terms)
            candidates[page_id]["hits"].append(
                {
                    "block_id": block_id,
                    "heading": block.get("heading", ""),
                    "role": block.get("role")
                    or (
                        "personal"
                        if block.get("assessment") == "user_explicit"
                        else "analysis"
                        if block.get("assessment") == "system_synthesis"
                        else "source"
                    ),
                    "assessment": block.get("assessment"),
                    "match_kind": "page_directory" if directory else "block_candidate",
                    "candidate_excerpt": ""
                    if directory
                    else text[window["start"] : window["end"]][:240],
                    "position": {}
                    if directory
                    else {"start": window["start"], "end": window["end"]},
                    "ranks": ranks[(page_id, block_id)],
                    "window_id": window["window_id"],
                    "projection_hash": window["projection_hash"],
                }
            )
        reason = reason or ("missing_effective_windows" if missing else None)
        return {
            "source": "wiki",
            "status": "partial" if reason else "ok" if candidates else "empty",
            "candidates": list(candidates.values()),
            "coverage": {
                "query": query,
                "exhaustive": False,
                "candidate_count": len(candidates),
                "valid_blocks": sum(len(p["blocks"]) for p in snapshot["pages"]),
                "lexical_candidates": len(lexical),
                "dense_candidates": len(dense),
                "encoded_windows": 0,
                "missing_windows": missing,
                "retrieval_method": "hybrid" if dense else "fts",
                "rrf_k": 60,
                "storage_backend": "postgresql",
                "lexical_profile": self.tokenizer.profile,
                "embedding_profile": self.profile.profile_id if self.profile else None,
                "query_profile": QUERY_VERSION,
                "degraded_reason": reason,
                "window_policy": sorted({e["policy"] for e in entries}),
            },
        }
