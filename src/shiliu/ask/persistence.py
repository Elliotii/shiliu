from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Iterable, Mapping

from shiliu.db import Database


ASK_RUN_SCHEMA_VERSION = "post-v5-ask-run-v1"
LIFECYCLE_EVENT_SCHEMA_VERSION = "v5.6-lifecycle-event-v1"


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
            trace_persisted INTEGER NOT NULL CHECK(trace_persisted IN (0, 1)),
            trace_error TEXT,
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
        trace_payload = dict(trace)
        for duplicated in (
            "search_executions",
            "events",
            "final_evidence",
            "citations",
            "answer_blocks",
            "limitations",
            "provider_usage",
        ):
            trace_payload.pop(duplicated, None)
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
                    _json(trace_payload),
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"Ask run is not active: {run_id}")
            connection.executemany(
                """
                INSERT INTO ask_search_trace_links(
                    run_id, sequence, relation_kind, decision_sequence,
                    execution_id, search_trace_id, trace_persisted,
                    trace_error, query, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        sequence,
                        str(value.get("relation_kind") or "retrieval"),
                        value.get("decision_sequence"),
                        value.get("execution_id"),
                        str(value["search_trace_id"]),
                        int(bool(value.get("trace_persisted", True))),
                        (
                            _json(value["trace_error"])
                            if value.get("trace_error") is not None
                            else None
                        ),
                        str(value.get("query") or ""),
                        completed_at,
                    )
                    for sequence, value in enumerate(search_rows)
                ],
            )
            next_sequence = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM ask_events WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0]
            )
            for offset, value in enumerate(event_rows):
                event_type = str(value.get("event_type") or "unknown")
                payload = {key: item for key, item in value.items() if key != "event_type"}
                envelope = _lifecycle_envelope(
                    run_id=run_id,
                    sequence=next_sequence + offset,
                    event_type=event_type,
                    payload=payload,
                )
                connection.execute(
                    "INSERT INTO ask_events(run_id, sequence, event_type, payload_json) "
                    "VALUES(?, ?, ?, ?)",
                    (run_id, next_sequence + offset, event_type, _json(envelope)),
                )
        return completed_at

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
        *,
        provenance: Mapping[str, Iterable[str]] | None = None,
    ) -> dict[str, Any]:
        """Append one immutable event at the real execution boundary."""

        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            active = connection.execute(
                "SELECT 1 FROM ask_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if active is None:
                raise RuntimeError(f"Ask run does not exist: {run_id}")
            sequence = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM ask_events WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0]
            )
            envelope = _lifecycle_envelope(
                run_id=run_id,
                sequence=sequence,
                event_type=event_type,
                payload=dict(payload or {}),
                provenance=provenance,
            )
            connection.execute(
                "INSERT INTO ask_events(run_id, sequence, event_type, payload_json) "
                "VALUES(?, ?, ?, ?)",
                (run_id, sequence, event_type, _json(envelope)),
            )
        return envelope

    def get_events(self, run_id: str, *, after_sequence: int = 0) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM ask_events "
                "WHERE run_id=? AND sequence>? ORDER BY sequence",
                (run_id, max(0, int(after_sequence))),
            ).fetchall()
        return [json.loads(str(value["payload_json"])) for value in rows]

    def request_abort(self, run_id: str, *, command_id: str) -> dict[str, Any]:
        """Persist a bounded abort and truthfully interrupt an active owner."""

        requested = self.append_event(
            run_id,
            "abort_requested",
            {"command_id": command_id, "automatic_replay": False},
        )
        completed_at = _utc_now()
        with self.db.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE ask_runs SET completed_at=?, lifecycle_status='failed',
                    termination_reason='interrupted', error_json=?
                WHERE run_id=? AND lifecycle_status='running'
                """,
                (
                    completed_at,
                    _json(
                        {
                            "error_type": "AskAbort",
                            "error_code": "interrupted",
                            "failure_class": "interrupted",
                            "message": "user requested abort",
                        }
                    ),
                    run_id,
                ),
            )
        if cursor.rowcount:
            terminal = self.append_event(
                run_id,
                "run_interrupted",
                {"command_id": command_id, "reason": "explicit_abort"},
            )
        else:
            terminal = requested
        return {"requested": requested, "terminal": terminal}

    def interrupt_owner_loss(self, run_id: str, *, reason: str) -> bool:
        """Fail closed when an in-process owner is no longer available."""

        completed_at = _utc_now()
        payload = {
            "error_type": "AskOwnerLoss",
            "error_code": "interrupted",
            "failure_class": "interrupted",
            "message": reason,
        }
        with self.db.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE ask_runs SET completed_at=?, lifecycle_status='failed',
                    termination_reason='interrupted', error_json=?
                WHERE run_id=? AND lifecycle_status='running'
                """,
                (completed_at, _json(payload), run_id),
            )
        if cursor.rowcount:
            self.append_event(
                run_id,
                "run_interrupted",
                {**payload, "reason": reason, "automatic_replay": False},
            )
            return True
        return False

    def fail(self, run_id: str, error: Exception) -> None:
        completed_at = _utc_now()
        termination_reason, failure_class = _failure_disposition(error)
        payload = {
            "error_type": type(error).__name__,
            "error_code": str(getattr(error, "code", type(error).__name__)),
            "failure_class": failure_class,
            "message": str(error)[:500],
        }
        with self.db.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE ask_runs SET completed_at=?, lifecycle_status='failed',
                    termination_reason=?, error_json=?
                WHERE run_id=? AND lifecycle_status='running'
                """,
                (completed_at, termination_reason, _json(payload), run_id),
            )
        if cursor.rowcount:
            event_type = (
                "run_interrupted" if failure_class == "interrupted" else "run_failed"
            )
            self.append_event(
                run_id,
                event_type,
                {**payload, "termination_reason": termination_reason},
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
                "final_evidence": record["final_evidence"],
                "citations": record["citations"],
                "answer_blocks": record["answer_blocks"],
                "limitations": record["limitations"],
                "provider_usage": record["usage_summary"],
            }
        )
        if record["answer_status"] is not None:
            trace["status"] = record["answer_status"]
        if record["mode"] == "deep":
            trace["events"] = [_developer_event(value) for value in record["events"]]
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
                       search_trace_id, trace_persisted, trace_error, query
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
        value["search_executions"] = []
        for item in links:
            link = dict(item)
            link["trace_persisted"] = bool(link["trace_persisted"])
            link["trace_error"] = (
                json.loads(str(link["trace_error"]))
                if link["trace_error"] is not None
                else None
            )
            value["search_executions"].append(link)
        value["events"] = [json.loads(str(item["payload_json"])) for item in events]
        return value


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _failure_disposition(error: Exception) -> tuple[str, str]:
    code = str(getattr(error, "code", type(error).__name__)).casefold()
    if code in {
        "provider_dispatch_unknown",
        "external_side_effect_unknown",
        "unknown_side_effect",
    }:
        return "external_side_effect_unknown", "unknown_side_effect"
    if code in {"interrupted", "execution_interrupted", "cancelled"}:
        return "interrupted", "interrupted"
    if code.startswith("transport_") or code in {
        "connection_error",
        "connection_reset",
    }:
        return "transport_failure", "transport"
    if code == "deadline_exhausted" or "timeout" in code:
        return "budget_exhausted", "deadline"
    if code.startswith("provider_") or code in {
        "invalid_model_output",
        "bad_provider_config",
    }:
        return "provider_error", "provider"
    if code in {"generation_failed", "answer_generation_failed"}:
        return "provider_error", "generation"
    return "implementation_error", "implementation"


def _lifecycle_envelope(
    *,
    run_id: str,
    sequence: int,
    event_type: str,
    payload: Mapping[str, Any],
    provenance: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    occurred_at = _utc_now()
    normalized_provenance = {
        key: list(dict.fromkeys(str(item) for item in (provenance or {}).get(key, ())))
        for key in (
            "search_execution_ids",
            "evidence_reference_ids",
            "decision_ids",
            "research_event_ids",
            "usage_record_ids",
        )
    }
    identity = _json(
        {
            "schema_version": LIFECYCLE_EVENT_SCHEMA_VERSION,
            "source_id": run_id,
            "sequence": sequence,
            "event_type": event_type,
            "payload": dict(payload),
        }
    )
    return {
        "schema_version": LIFECYCLE_EVENT_SCHEMA_VERSION,
        "event_id": f"askevt_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]}",
        "source_kind": "ask_run",
        "source_id": run_id,
        "sequence": sequence,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "payload": dict(payload),
        "provenance": normalized_provenance,
    }


def _developer_event(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Keep the accepted developer trace shape while exposing its envelope."""

    payload = dict(envelope.get("payload") or {})
    payload["event_type"] = str(envelope.get("event_type") or "unknown")
    payload["lifecycle_event"] = dict(envelope)
    return payload


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
