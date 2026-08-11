from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from typing import Any, Iterable, Mapping

from shiliu.db import Database


ASK_RUN_SCHEMA_VERSION = "post-v5-ask-run-v1"


def initialize_ask_schema(connection: sqlite3.Connection) -> None:
    """Create the bounded Ask persistence contract.

    Search trace payloads remain in the retrieval tables.  These tables only own
    Ask identity/result data, ordered references, and bounded Deep diagnostics.
    """

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS ask_runs (
            run_id TEXT PRIMARY KEY,
            run_schema_version TEXT NOT NULL,
            parent_run_id TEXT REFERENCES ask_runs(run_id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            query TEXT NOT NULL,
            mode TEXT NOT NULL CHECK(mode IN ('fast', 'deep')),
            filters_json TEXT NOT NULL DEFAULT '{}',
            lifecycle_status TEXT NOT NULL
                CHECK(lifecycle_status IN ('running', 'completed', 'failed')),
            answer_status TEXT
                CHECK(answer_status IS NULL OR answer_status IN
                      ('complete', 'partial', 'insufficient')),
            termination_reason TEXT,
            query_analysis_json TEXT NOT NULL DEFAULT '{}',
            rewrites_json TEXT NOT NULL DEFAULT '[]',
            final_evidence_json TEXT NOT NULL DEFAULT '[]',
            citations_json TEXT NOT NULL DEFAULT '[]',
            answer_blocks_json TEXT NOT NULL DEFAULT '[]',
            limitations_json TEXT NOT NULL DEFAULT '[]',
            usage_summary_json TEXT NOT NULL DEFAULT '{}',
            trace_json TEXT NOT NULL DEFAULT '{}',
            error_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS ask_search_trace_links (
            run_id TEXT NOT NULL REFERENCES ask_runs(run_id) ON DELETE CASCADE,
            sequence INTEGER NOT NULL CHECK(sequence >= 0),
            relation_kind TEXT NOT NULL,
            decision_sequence INTEGER,
            execution_id TEXT,
            search_trace_id TEXT NOT NULL,
            query TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(run_id, sequence)
        );

        CREATE TABLE IF NOT EXISTS ask_events (
            run_id TEXT NOT NULL REFERENCES ask_runs(run_id) ON DELETE CASCADE,
            sequence INTEGER NOT NULL CHECK(sequence >= 0),
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY(run_id, sequence)
        );

        CREATE INDEX IF NOT EXISTS idx_ask_runs_created
            ON ask_runs(created_at DESC, run_id);
        CREATE INDEX IF NOT EXISTS idx_ask_runs_parent
            ON ask_runs(parent_run_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_ask_search_trace
            ON ask_search_trace_links(search_trace_id, run_id);
        """
    )


class AskRunStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def start(
        self,
        *,
        run_id: str,
        query: str,
        mode: str,
        filters: Mapping[str, Any],
        parent_run_id: str | None = None,
    ) -> str:
        created_at = _utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO ask_runs(
                    run_id, run_schema_version, parent_run_id, created_at,
                    query, mode, filters_json, lifecycle_status
                ) VALUES(?, ?, ?, ?, ?, ?, ?, 'running')
                """,
                (
                    run_id,
                    ASK_RUN_SCHEMA_VERSION,
                    parent_run_id,
                    created_at,
                    query,
                    mode,
                    _json(dict(filters)),
                ),
            )
        return created_at

    def complete(
        self,
        *,
        run_id: str,
        trace: Mapping[str, Any],
        answer_status: str,
        termination_reason: str,
        query_analysis: Mapping[str, Any],
        rewrites: Iterable[str],
        search_executions: Iterable[Mapping[str, Any]],
        final_evidence: Iterable[Mapping[str, Any]],
        citations: Iterable[Mapping[str, Any]],
        answer_blocks: Iterable[Mapping[str, Any]],
        limitations: Iterable[str],
        usage_summary: Mapping[str, Any],
        events: Iterable[Mapping[str, Any]] = (),
    ) -> str:
        completed_at = _utc_now()
        search_rows = [dict(value) for value in search_executions]
        event_rows = [dict(value) for value in events]
        with self.db.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE ask_runs SET
                    completed_at=?, lifecycle_status='completed',
                    answer_status=?, termination_reason=?,
                    query_analysis_json=?, rewrites_json=?,
                    final_evidence_json=?, citations_json=?,
                    answer_blocks_json=?, limitations_json=?,
                    usage_summary_json=?, trace_json=?, error_json='{}'
                WHERE run_id=? AND lifecycle_status='running'
                """,
                (
                    completed_at,
                    answer_status,
                    termination_reason,
                    _json(dict(query_analysis)),
                    _json(list(rewrites)),
                    _json(list(final_evidence)),
                    _json(list(citations)),
                    _json(list(answer_blocks)),
                    _json(list(limitations)),
                    _json(dict(usage_summary)),
                    _json(dict(trace)),
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"Ask run is not active: {run_id}")
            connection.executemany(
                """
                INSERT INTO ask_search_trace_links(
                    run_id, sequence, relation_kind, decision_sequence,
                    execution_id, search_trace_id, query, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        sequence,
                        str(value.get("relation_kind") or "retrieval"),
                        value.get("decision_sequence"),
                        value.get("execution_id"),
                        str(value["search_trace_id"]),
                        str(value.get("query") or ""),
                        completed_at,
                    )
                    for sequence, value in enumerate(search_rows)
                ],
            )
            connection.executemany(
                """
                INSERT INTO ask_events(run_id, sequence, event_type, payload_json)
                VALUES(?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        sequence,
                        str(value.get("event_type") or "unknown"),
                        _json(value),
                    )
                    for sequence, value in enumerate(event_rows)
                ],
            )
        return completed_at

    def fail(self, run_id: str, error: Exception) -> None:
        completed_at = _utc_now()
        payload = {
            "error_type": type(error).__name__,
            "error_code": str(getattr(error, "code", type(error).__name__)),
            "message": str(error)[:500],
        }
        with self.db.connect() as connection:
            connection.execute(
                """
                UPDATE ask_runs SET completed_at=?, lifecycle_status='failed',
                    termination_reason='provider_error', error_json=?
                WHERE run_id=? AND lifecycle_status='running'
                """,
                (completed_at, _json(payload), run_id),
            )

    def get_trace(self, run_id: str) -> dict[str, Any] | None:
        record = self.get_run(run_id)
        if record is None:
            return None
        trace = dict(record.pop("trace"))
        trace.update(
            {
                "run_id": record["run_id"],
                "query": record["query"],
                "mode": record["mode"],
                "created_at": record["created_at"],
                "completed_at": record["completed_at"],
                "lifecycle_status": record["lifecycle_status"],
                "parent_run_id": record["parent_run_id"],
                "filters": record["filters"],
                "termination_reason": record["termination_reason"],
                "search_executions": record["search_executions"],
            }
        )
        if record["answer_status"] is not None:
            trace["status"] = record["answer_status"]
        if record["mode"] == "deep":
            trace["events"] = record["events"]
        if record["error"]:
            trace["error"] = record["error"]
        return trace

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM ask_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                return None
            links = connection.execute(
                """
                SELECT sequence, relation_kind, decision_sequence, execution_id,
                       search_trace_id, query
                FROM ask_search_trace_links
                WHERE run_id=? ORDER BY sequence
                """,
                (run_id,),
            ).fetchall()
            events = connection.execute(
                "SELECT payload_json FROM ask_events WHERE run_id=? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        value = dict(row)
        for name in (
            "filters",
            "query_analysis",
            "rewrites",
            "final_evidence",
            "citations",
            "answer_blocks",
            "limitations",
            "usage_summary",
            "trace",
            "error",
        ):
            value[name] = json.loads(str(value.pop(f"{name}_json")))
        value["search_executions"] = [dict(item) for item in links]
        value["events"] = [json.loads(str(item["payload_json"])) for item in events]
        return value


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def final_evidence_identities(
    spans: Iterable[Any], citation_ids: set[str]
) -> list[dict[str, Any]]:
    """Project bounded source/provenance identity for adopted evidence only."""

    return [
        {
            "citation_id": span.citation_id,
            "citation_identity_version": span.citation_identity_version,
            "video_id": span.video_id,
            "source_artifact_id": span.source_artifact_id,
            "source_version": span.source_version,
            "timeline_run_id": span.timeline_run_id,
            "segment_ids": list(span.segment_ids),
            "retrieval_provenance": list(span.retrieval_provenance),
        }
        for span in spans
        if span.citation_id in citation_ids
    ]
