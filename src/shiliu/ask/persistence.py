from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable, Mapping

from shiliu.db import Database


ASK_RUN_SCHEMA_VERSION = "post-v5-ask-run-v1"
LIFECYCLE_EVENT_SCHEMA_VERSION = "v5.6-lifecycle-event-v1"


def project_trace(record: dict[str, Any] | None) -> dict[str, Any] | None:
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
            "intro": record["intro"],
            "outro": record["outro"],
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


class PgAskRunStore:
    """PostgreSQL Ask lifecycle store; scope comes only from injected context."""

    def __init__(self, db: Database) -> None:
        from shiliu.storage.postgres import PgDatabase
        if not isinstance(getattr(db, "pg", None), PgDatabase) or db.context is None:
            raise TypeError("PgAskRunStore requires an injected PostgreSQL Database and ResourceContext")
        self.db = db
        self.context = db.context

    def start(self, *, run_id: str, query: str, mode: str, filters: Mapping[str, Any],
              parent_run_id: str | None = None) -> str:
        from psycopg.types.json import Jsonb
        created = datetime.now(timezone.utc)
        with self.db.connect() as conn:
            if parent_run_id:
                parent = conn.execute("SELECT 1 FROM shiliu.ask_runs WHERE workspace_id=%s AND run_id=%s AND owner_user_id=%s",
                                      (self.context.workspace_id, parent_run_id, self.context.user_id)).fetchone()
                if parent is None:
                    raise KeyError(parent_run_id)
            conn.execute("INSERT INTO shiliu.ask_runs(workspace_id,owner_user_id,run_id,run_schema_version,parent_run_id,created_at,query,mode,filters_json,lifecycle_status) "
                         "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'running')",
                         (self.context.workspace_id,self.context.user_id,run_id,ASK_RUN_SCHEMA_VERSION,parent_run_id,created,query,mode,Jsonb(dict(filters))))
        return created.isoformat(timespec="milliseconds")

    def _append_event_on(self, conn, run_id, event_type, payload=None, *, provenance=None):
        from psycopg.types.json import Jsonb
        owner=conn.execute("SELECT run_id FROM shiliu.ask_runs WHERE workspace_id=%s AND owner_user_id=%s AND run_id=%s FOR UPDATE",
                           (self.context.workspace_id,self.context.user_id,run_id)).fetchone()
        if owner is None:raise KeyError(run_id)
        seq=int(conn.execute("SELECT COALESCE(MAX(sequence),0)+1 AS seq FROM shiliu.ask_events WHERE workspace_id=%s AND run_id=%s",
                             (self.context.workspace_id,run_id)).fetchone()["seq"])
        envelope=_lifecycle_envelope(run_id=run_id,sequence=seq,event_type=event_type,payload=dict(payload or {}),provenance=provenance)
        conn.execute("INSERT INTO shiliu.ask_events(workspace_id,run_id,sequence,event_type,payload_json) VALUES(%s,%s,%s,%s,%s)",
                     (self.context.workspace_id,run_id,seq,event_type,Jsonb(envelope)))
        return envelope

    def append_event(self, run_id, event_type, payload=None, *, provenance=None):
        with self.db.connect() as conn:
            return self._append_event_on(conn,run_id,event_type,payload,provenance=provenance)

    def complete(self, *, run_id: str, trace: Mapping[str, Any], answer_status: str,
                 termination_reason: str, query_analysis: Mapping[str, Any], rewrites: Iterable[str],
                 search_executions: Iterable[Mapping[str, Any]], final_evidence: Iterable[Mapping[str, Any]],
                 citations: Iterable[Mapping[str, Any]], answer_blocks: Iterable[Mapping[str, Any]],
                 limitations: Iterable[str], usage_summary: Mapping[str, Any],
                 events: Iterable[Mapping[str, Any]] = ()) -> str:
        from psycopg.types.json import Jsonb
        completed=datetime.now(timezone.utc)
        trace_payload=dict(trace)
        for key in ("search_executions","events","final_evidence","citations","answer_blocks","limitations","provider_usage"):
            trace_payload.pop(key,None)
        with self.db.connect() as conn:
            conn.execute("SELECT run_id FROM shiliu.ask_runs WHERE workspace_id=%s AND owner_user_id=%s AND run_id=%s FOR UPDATE",
                         (self.context.workspace_id,self.context.user_id,run_id))
            updated=conn.execute("UPDATE shiliu.ask_runs SET completed_at=%s,lifecycle_status='completed',answer_status=%s,termination_reason=%s,"
                "query_analysis_json=%s,rewrites_json=%s,final_evidence_json=%s,citations_json=%s,answer_blocks_json=%s,limitations_json=%s,"
                "usage_summary_json=%s,trace_json=%s,error_json='{}'::jsonb WHERE workspace_id=%s AND owner_user_id=%s AND run_id=%s "
                "AND lifecycle_status='running' RETURNING run_id",
                (completed,answer_status,termination_reason,Jsonb(dict(query_analysis)),Jsonb(list(rewrites)),Jsonb(list(final_evidence)),
                 Jsonb(list(citations)),Jsonb(list(answer_blocks)),Jsonb(list(limitations)),Jsonb(dict(usage_summary)),Jsonb(trace_payload),
                 self.context.workspace_id,self.context.user_id,run_id)).fetchone()
            if updated is None:raise RuntimeError(f"Ask run is not active: {run_id}")
            for seq,value in enumerate(search_executions):
                conn.execute("INSERT INTO shiliu.ask_search_trace_links(workspace_id,run_id,sequence,relation_kind,decision_sequence,execution_id,search_trace_id,trace_persisted,trace_error,query,created_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (self.context.workspace_id,run_id,seq,str(value.get("relation_kind") or "retrieval"),value.get("decision_sequence"),value.get("execution_id"),
                    str(value["search_trace_id"]),bool(value.get("trace_persisted",True)),_json(value["trace_error"]) if value.get("trace_error") is not None else None,
                     str(value.get("query") or ""),completed))
            next_seq=int(conn.execute("SELECT COALESCE(MAX(sequence),0)+1 AS n FROM shiliu.ask_events WHERE workspace_id=%s AND run_id=%s",
                                      (self.context.workspace_id,run_id)).fetchone()["n"])
            for offset,value in enumerate(events):
                event_type=str(value.get("event_type") or "unknown")
                payload={k:v for k,v in value.items() if k!="event_type"}
                envelope=_lifecycle_envelope(run_id=run_id,sequence=next_seq+offset,event_type=event_type,payload=payload)
                conn.execute("INSERT INTO shiliu.ask_events(workspace_id,run_id,sequence,event_type,payload_json) VALUES(%s,%s,%s,%s,%s)",
                             (self.context.workspace_id,run_id,next_seq+offset,event_type,Jsonb(envelope)))
        return completed.isoformat(timespec="milliseconds")

    def get_events(self, run_id: str, *, after_sequence: int = 0) -> list[dict[str, Any]]:
        with self.db.connect(read_only=True) as conn:
            rows=conn.execute("SELECT payload_json FROM shiliu.ask_events e WHERE workspace_id=%s AND run_id=%s AND sequence>%s "
                              "AND EXISTS(SELECT 1 FROM shiliu.ask_runs r WHERE r.workspace_id=e.workspace_id AND r.run_id=e.run_id AND r.owner_user_id=%s) ORDER BY sequence",
                              (self.context.workspace_id,run_id,max(0,int(after_sequence)),self.context.user_id)).fetchall()
        return [dict(r["payload_json"]) for r in rows]

    def fail(self, run_id: str, error: Exception) -> None:
        from psycopg.types.json import Jsonb
        completed=datetime.now(timezone.utc)
        termination,failure_class=_failure_disposition(error)
        payload={"error_type":type(error).__name__,"error_code":str(getattr(error,"code",type(error).__name__)),
                 "failure_class":failure_class,"message":str(error)[:500]}
        with self.db.connect() as conn:
            row=conn.execute("UPDATE shiliu.ask_runs SET completed_at=%s,lifecycle_status='failed',termination_reason=%s,error_json=%s "
                             "WHERE workspace_id=%s AND owner_user_id=%s AND run_id=%s AND lifecycle_status='running' RETURNING run_id",
                             (completed,termination,Jsonb(payload),self.context.workspace_id,self.context.user_id,run_id)).fetchone()
            if row:
                event="run_interrupted" if failure_class=="interrupted" else "run_failed"
                self._append_event_on(conn,run_id,event,{**payload,"termination_reason":termination})

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.db.connect(read_only=True) as conn:
            row=conn.execute("SELECT * FROM shiliu.ask_runs WHERE workspace_id=%s AND owner_user_id=%s AND run_id=%s",
                             (self.context.workspace_id,self.context.user_id,run_id)).fetchone()
            if row is None:return None
            links=conn.execute("SELECT sequence,relation_kind,decision_sequence,execution_id,search_trace_id,trace_persisted,trace_error,query FROM shiliu.ask_search_trace_links WHERE workspace_id=%s AND run_id=%s ORDER BY sequence",
                               (self.context.workspace_id,run_id)).fetchall()
            events=conn.execute("SELECT payload_json FROM shiliu.ask_events WHERE workspace_id=%s AND run_id=%s ORDER BY sequence",
                                (self.context.workspace_id,run_id)).fetchall()
        from shiliu.storage.dto import row_dto
        value=row_dto(row,timestamps=("created_at","completed_at"),timespec="milliseconds")
        value.pop("workspace_id",None);value.pop("owner_user_id",None)
        for name in ("filters","query_analysis","rewrites","final_evidence","citations","answer_blocks","limitations","usage_summary","trace","error"):
            key=name+"_json"
            raw=value.pop(key)
            value[name]=dict(raw) if isinstance(raw,Mapping) else list(raw) if isinstance(raw,list) else raw
        value["intro"]=value["trace"].get("intro"); value["outro"]=value["trace"].get("outro")
        value["search_executions"]=[]
        for item in links:
            link=dict(item)
            link["trace_persisted"]=bool(link["trace_persisted"])
            link["trace_error"]=json.loads(link["trace_error"]) if link["trace_error"] is not None else None
            value["search_executions"].append(link)
        value["events"]=[dict(item["payload_json"]) for item in events]
        return value

    def _interrupt_on(self, conn, run_id, *, reason, error_type="AskOwnerLoss", command_id=None):
        from psycopg.types.json import Jsonb
        payload={"error_type":error_type,"error_code":"interrupted","failure_class":"interrupted","message":reason}
        row=conn.execute("UPDATE shiliu.ask_runs SET completed_at=clock_timestamp(),lifecycle_status='failed',"
            "termination_reason='interrupted',error_json=%s WHERE workspace_id=%s AND owner_user_id=%s AND run_id=%s "
            "AND lifecycle_status='running' RETURNING run_id",
            (Jsonb(payload),self.context.workspace_id,self.context.user_id,run_id)).fetchone()
        if row:
            return self._append_event_on(conn,run_id,"run_interrupted",{**payload,"reason":reason,"automatic_replay":False,
                **({"command_id":command_id} if command_id else {})})
        return None

    def interrupt_owner_loss(self, run_id, *, reason):
        with self.db.connect() as conn:
            return self._interrupt_on(conn,run_id,reason=reason) is not None

    def request_abort(self, run_id, *, command_id):
        with self.db.connect() as conn:
            requested=self._append_event_on(conn,run_id,"abort_requested",{"command_id":command_id,"automatic_replay":False})
            terminal=self._interrupt_on(conn,run_id,reason="user requested abort",error_type="AskAbort",command_id=command_id)
            return {"requested":requested,"terminal":terminal or requested}

    def interrupt_running_on_startup(self):
        with self.db.connect() as conn:
            rows=conn.execute("SELECT run_id FROM shiliu.ask_runs WHERE workspace_id=%s AND owner_user_id=%s "
                "AND lifecycle_status='running' ORDER BY run_id",(self.context.workspace_id,self.context.user_id)).fetchall()
            return sum(self._interrupt_on(conn,row["run_id"],reason="process owner lost at startup") is not None for row in rows)

    def get_trace(self, run_id: str):
        return project_trace(self.get_run(run_id))


# Formal runtime entry; SQLite remains available only by its explicit legacy name.
AskRunStore = PgAskRunStore






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


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
