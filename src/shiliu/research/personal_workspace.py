from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from shiliu.db import Database
from shiliu.research.errors import (
    ResearchConflict,
    ResearchNotFound,
    ResearchValidationError,
)
from shiliu.research.knowledge_contracts import (
    CreateWorkspaceRecordRequest,
    DecideWorkspaceRecordRequest,
    WorkspaceSourceRef,
)
from shiliu.research.personalization import (
    LIMITATIONS_POSITION_KEY,
    LIMITATIONS_POSITIONS,
    PersonalizationContextProjection,
)
from shiliu.research.schema import PERSONAL_WORKSPACE_POLICY_VERSION
from shiliu.research.service import ResearchTaskService


FaultInjector = Callable[[str], None]
TERMINAL_STATUSES = {"rejected", "expired", "tombstoned", "invalidated"}
ACTIVE_EXPIRABLE_STATUSES = {
    "current",
    "candidate",
    "confirmed",
    "observed",
    "diagnosed",
    "candidate_source",
}
SECRET_KEYS = {
    "api_key",
    "password",
    "secret",
    "credential",
    "access_token",
    "refresh_token",
    "private_key",
}
PROGRESS_STATES = {
    "discovered",
    "reviewed",
    "researched",
    "supported",
    "unresolved",
    "conflicted",
    "stale",
    "learned",
    "understood",
    "familiar",
}
SELF_ASSESSMENT_STATES = {"learned", "understood", "familiar"}
CORPUS_OBSERVATION_TYPES = {
    "folder",
    "topic",
    "uploader",
    "series",
    "source_availability",
    "search_term",
    "limitation",
}


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _id(prefix: str, value: object) -> str:
    return f"{prefix}_{_hash(value)[:32]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ResearchValidationError("expires_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def _decode(value: object, expected: type) -> Any:
    decoded = json.loads(str(value))
    if not isinstance(decoded, expected):
        raise ResearchConflict("persisted WorkspaceRecord JSON has invalid shape")
    return decoded


def _normalized_key(value: str) -> str:
    return " ".join(value.casefold().split())


class ResearchPersonalWorkspaceService:
    """Single typed Stage 4 aggregate; it is never a product-behavior input."""

    def __init__(
        self,
        db: Database,
        *,
        kernel: ResearchTaskService,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self.db = db
        self.kernel = kernel
        self.fault_injector = fault_injector or (lambda _point: None)
        self._command_lock = threading.RLock()
        self.personalization = PersonalizationContextProjection()

    def create(
        self,
        command_task_id: str,
        request: CreateWorkspaceRecordRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        request = CreateWorkspaceRecordRequest.model_validate(
            request.model_dump(mode="json")
        )
        request_value = request.model_dump(mode="json")
        payload_hash = _hash(
            {
                "operation": "create_workspace_record",
                "command_task_id": command_task_id,
                "principal_id": principal_id,
                **request_value,
            }
        )
        with self._command_lock, self.kernel._transaction() as connection:
            task = self.kernel._task(connection, command_task_id)
            existing = self.kernel._existing_receipt(
                connection,
                task_id=command_task_id,
                command_id=request.command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}

            payload = dict(request.payload)
            self._assert_safe_payload(payload)
            semantic_key = _normalized_key(request.semantic_key)
            source_refs = self._validate_source_refs(connection, request.source_refs)
            if (
                request.record_kind == "inferred_candidate"
                and semantic_key == LIMITATIONS_POSITION_KEY
            ):
                self._validate_feedback_preference_sources(
                    connection,
                    command_task_id=command_task_id,
                    source_refs=source_refs,
                    semantic_key=semantic_key,
                    payload=payload,
                    principal_id=principal_id,
                )
            authority_class, status = self._create_semantics(
                request.record_kind,
                payload,
                source_refs,
            )
            expires_at = self._expires_value(request.expires_at)
            record_id = _id(
                "workspacerecord",
                {
                    "owner_scope": "local_user_workspace",
                    "record_kind": request.record_kind,
                    "semantic_key": semantic_key,
                },
            )
            source_boundary_hash = _hash(source_refs)
            latest = self._latest(connection, record_id, required=False)
            version = 1
            parent_revision_id = None
            if latest is not None:
                projected_latest = self._project(latest)
                same_boundary = (
                    str(latest["source_boundary_hash"]) == source_boundary_hash
                )
                same_content = (
                    _decode(latest["payload_json"], dict) == payload
                    and latest["confidence"] == request.confidence
                    and (str(latest["expires_at"]) if latest["expires_at"] else None)
                    == expires_at
                )
                if same_boundary and same_content:
                    response = {
                        **projected_latest,
                        "semantically_deduplicated": True,
                        "suppressed_no_resurrection": projected_latest[
                            "effective_status"
                        ]
                        in TERMINAL_STATUSES,
                    }
                    return self._audit_without_revision(
                        connection,
                        task=task,
                        command_id=request.command_id,
                        payload_hash=payload_hash,
                        response=response,
                        event_type="workspace_record_replay_suppressed",
                    )
                if same_boundary:
                    raise ResearchValidationError(
                        "same source boundary cannot rewrite a WorkspaceRecord; use a decision"
                    )
                if (
                    projected_latest["effective_status"] in TERMINAL_STATUSES
                    and not request.reopen_reason
                ):
                    raise ResearchValidationError(
                        "new evidence after a terminal decision requires reopen_reason"
                    )
                version = int(latest["version"]) + 1
                parent_revision_id = str(latest["record_revision_id"])

            revision_id = _id(
                "workspacerevision", {"record_id": record_id, "version": version}
            )
            content_hash = self._content_hash(
                record_kind=request.record_kind,
                authority_class=authority_class,
                status=status,
                semantic_key=semantic_key,
                payload=payload,
                source_refs=source_refs,
                confidence=request.confidence,
                expires_at=expires_at,
            )
            connection.execute(
                """
                INSERT INTO research_workspace_records(
                    record_revision_id, record_id, version, parent_revision_id,
                    command_task_id, record_kind, authority_class, status,
                    semantic_key, payload_json, source_refs_json,
                    source_boundary_hash, confidence, expires_at,
                    decision_action, reason, principal_id, policy_version,
                    content_hash, command_id, command_payload_hash, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'create',
                         ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    record_id,
                    version,
                    parent_revision_id,
                    command_task_id,
                    request.record_kind,
                    authority_class,
                    status,
                    semantic_key,
                    _canonical_json(payload),
                    _canonical_json(source_refs),
                    source_boundary_hash,
                    request.confidence,
                    expires_at,
                    request.reopen_reason or request.reason,
                    principal_id,
                    PERSONAL_WORKSPACE_POLICY_VERSION,
                    content_hash,
                    request.command_id,
                    payload_hash,
                    _now(),
                ),
            )
            self.fault_injector("after_stage4_workspace_record")
            response = {
                **self._project(self._latest(connection, record_id)),
                "semantically_deduplicated": False,
                "suppressed_no_resurrection": False,
            }
            self._commit_audit(
                connection,
                task=task,
                command_id=request.command_id,
                payload_hash=payload_hash,
                response=response,
                event_type="workspace_record_created",
            )
            self.fault_injector("after_stage4_workspace_receipt")
        return {**response, "deduplicated": False}

    def decide(
        self,
        command_task_id: str,
        record_id: str,
        request: DecideWorkspaceRecordRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        request = DecideWorkspaceRecordRequest.model_validate(
            request.model_dump(mode="json")
        )
        payload_hash = _hash(
            {
                "operation": "decide_workspace_record",
                "command_task_id": command_task_id,
                "record_id": record_id,
                "principal_id": principal_id,
                **request.model_dump(mode="json"),
            }
        )
        with self._command_lock, self.kernel._transaction() as connection:
            task = self.kernel._task(connection, command_task_id)
            existing = self.kernel._existing_receipt(
                connection,
                task_id=command_task_id,
                command_id=request.command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}
            latest = self._latest(connection, record_id)
            if int(latest["version"]) != request.expected_version:
                raise ResearchConflict("stale WorkspaceRecord expected_version")
            projected_latest = self._project(latest)
            if request.action not in projected_latest["allowed_actions"]:
                raise ResearchValidationError(
                    "WorkspaceRecord action is not allowed from its effective status"
                )
            payload = _decode(latest["payload_json"], dict)
            source_refs = _decode(latest["source_refs_json"], list)
            authority_class, status, next_payload = self._decision_semantics(
                latest,
                request,
                payload,
                source_refs,
            )
            self._assert_safe_payload(next_payload)
            if (
                str(latest["record_kind"]) == "inferred_candidate"
                and str(latest["semantic_key"]) == LIMITATIONS_POSITION_KEY
                and request.action == "confirm"
            ):
                self._validate_feedback_preference_sources(
                    connection,
                    command_task_id=command_task_id,
                    source_refs=source_refs,
                    semantic_key=str(latest["semantic_key"]),
                    payload=next_payload,
                    principal_id=principal_id,
                )
            self._create_semantics(str(latest["record_kind"]), next_payload, source_refs)
            version = int(latest["version"]) + 1
            revision_id = _id(
                "workspacerevision", {"record_id": record_id, "version": version}
            )
            content_hash = self._content_hash(
                record_kind=str(latest["record_kind"]),
                authority_class=authority_class,
                status=status,
                semantic_key=str(latest["semantic_key"]),
                payload=next_payload,
                source_refs=source_refs,
                confidence=(
                    float(latest["confidence"])
                    if latest["confidence"] is not None
                    else None
                ),
                expires_at=(str(latest["expires_at"]) if latest["expires_at"] else None),
            )
            connection.execute(
                """
                INSERT INTO research_workspace_records(
                    record_revision_id, record_id, version, parent_revision_id,
                    command_task_id, record_kind, authority_class, status,
                    semantic_key, payload_json, source_refs_json,
                    source_boundary_hash, confidence, expires_at,
                    decision_action, reason, principal_id, policy_version,
                    content_hash, command_id, command_payload_hash, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    record_id,
                    version,
                    str(latest["record_revision_id"]),
                    command_task_id,
                    str(latest["record_kind"]),
                    authority_class,
                    status,
                    str(latest["semantic_key"]),
                    _canonical_json(next_payload),
                    str(latest["source_refs_json"]),
                    str(latest["source_boundary_hash"]),
                    latest["confidence"],
                    latest["expires_at"],
                    request.action,
                    request.reason,
                    principal_id,
                    PERSONAL_WORKSPACE_POLICY_VERSION,
                    content_hash,
                    request.command_id,
                    payload_hash,
                    _now(),
                ),
            )
            self.fault_injector("after_stage4_workspace_decision")
            response = self._project(self._latest(connection, record_id))
            self._commit_audit(
                connection,
                task=task,
                command_id=request.command_id,
                payload_hash=payload_hash,
                response=response,
                event_type="workspace_record_decided",
            )
            self.fault_injector("after_stage4_workspace_decision_receipt")
        return {**response, "deduplicated": False}

    def get_workspace(
        self,
        command_task_id: str,
        *,
        record_kind: str | None = None,
        status: str | None = None,
        personalization_enabled: bool = True,
    ) -> dict[str, Any]:
        with self.db.connect() as connection:
            self.kernel._task(connection, command_task_id)
            rows = connection.execute(
                """
                SELECT * FROM research_workspace_records
                ORDER BY record_kind, semantic_key, record_id, version
                """
            ).fetchall()
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(str(row["record_id"]), []).append(row)
        all_records = []
        for history_rows in grouped.values():
            latest = self._project(history_rows[-1])
            latest["history"] = [
                {
                    "record_revision_id": str(row["record_revision_id"]),
                    "version": int(row["version"]),
                    "authority_class": str(row["authority_class"]),
                    "status": str(row["status"]),
                    "decision_action": str(row["decision_action"]),
                    "reason": str(row["reason"]),
                    "payload": _decode(row["payload_json"], dict),
                    "content_hash": str(row["content_hash"]),
                    "created_at": str(row["created_at"]),
                }
                for row in history_rows
            ]
            all_records.append(latest)
        personalization_context = self.personalization.project(
            all_records, enabled=personalization_enabled
        )
        applied_revision_id = (
            personalization_context["preference"]["record_revision_id"]
            if personalization_context["applied"]
            and personalization_context["preference"] is not None
            else None
        )
        for value in all_records:
            value["product_behavior_effect"] = (
                value["record_revision_id"] == applied_revision_id
            )
        records = [
            value
            for value in all_records
            if (record_kind is None or value["record_kind"] == record_kind)
            and (status is None or value["effective_status"] == status)
        ]
        records.sort(
            key=lambda value: (
                value["record_kind"],
                value["semantic_key"],
                value["record_id"],
            )
        )
        return {
            "workspace_schema_version": PERSONAL_WORKSPACE_POLICY_VERSION,
            "command_task_id": command_task_id,
            "authority": {
                "sqlite": "sole_workspace_record_authority",
                "explicit_memory": "user_authored_or_confirmed_only",
                "inferred": "candidate_until_explicit_decision",
                "corpus": "soft_prior_storage_only_not_consumed",
                "experience": "candidate_record_only_no_skill_or_policy",
                "product_behavior": "v5_c_stage1_confirmed_research_presentation_only",
            },
            "records": records,
            "personalization_context": personalization_context,
            "counts": {
                "records": len(records),
                "candidate": sum(
                    value["effective_status"] == "candidate" for value in records
                ),
                "terminal": sum(
                    value["effective_status"] in TERMINAL_STATUSES for value in records
                ),
            },
        }

    def _audit_without_revision(
        self,
        connection: sqlite3.Connection,
        *,
        task: sqlite3.Row,
        command_id: str,
        payload_hash: str,
        response: dict[str, Any],
        event_type: str,
    ) -> dict[str, Any]:
        self._commit_audit(
            connection,
            task=task,
            command_id=command_id,
            payload_hash=payload_hash,
            response=response,
            event_type=event_type,
        )
        self.fault_injector("after_stage4_workspace_receipt")
        return {**response, "deduplicated": False}

    def _commit_audit(
        self,
        connection: sqlite3.Connection,
        *,
        task: sqlite3.Row,
        command_id: str,
        payload_hash: str,
        response: dict[str, Any],
        event_type: str,
    ) -> None:
        now = _now()
        self.kernel._event(
            connection,
            task_id=str(task["task_id"]),
            goal_id=(str(task["active_goal_id"]) if task["active_goal_id"] else None),
            event_type=event_type,
            payload={
                "record_id": response["record_id"],
                "version": response["version"],
                "record_kind": response["record_kind"],
                "authority_class": response["authority_class"],
                "effective_status": response["effective_status"],
                "content_hash": response["content_hash"],
            },
            command_id=command_id,
            owner_epoch=int(task["owner_epoch"]),
            now=now,
        )
        self.kernel._insert_receipt(
            connection,
            task_id=str(task["task_id"]),
            command_id=command_id,
            command_type="workspace_record_command",
            payload_hash=payload_hash,
            outcome_reference=response["record_revision_id"],
            response=response,
            owner_epoch=int(task["owner_epoch"]),
            now=now,
        )

    def _validate_source_refs(
        self,
        connection: sqlite3.Connection,
        refs: list[WorkspaceSourceRef],
    ) -> list[dict[str, Any]]:
        canonical = []
        for ref in refs:
            row = self._source_row(connection, ref)
            boundary_hash = _hash(row)
            if ref.boundary_hash is not None and ref.boundary_hash != boundary_hash:
                raise ResearchConflict("Workspace source boundary hash mismatch")
            canonical.append(
                {
                    "ref_type": ref.ref_type,
                    "ref_id": ref.ref_id,
                    "task_id": ref.task_id,
                    "boundary_hash": boundary_hash,
                    "href": self._source_href(ref),
                }
            )
        canonical.sort(
            key=lambda value: (
                value["ref_type"],
                value["task_id"] or "",
                value["ref_id"],
            )
        )
        return canonical

    @staticmethod
    def _source_row(
        connection: sqlite3.Connection, ref: WorkspaceSourceRef
    ) -> dict[str, Any]:
        mapping = {
            "research_task": ("research_tasks", "task_id"),
            "research_event": ("research_events", "event_id"),
            "research_attempt": ("research_attempts", "attempt_id"),
            "research_trace": ("research_traces", "trace_id"),
            "research_result": ("research_results", "result_id"),
            "fact_revision": ("research_fact_revisions", "fact_revision_id"),
            "artifact_revision": (
                "research_knowledge_artifact_revisions",
                "artifact_revision_id",
            ),
            "taxonomy_snapshot": ("taxonomy_corpus_snapshots", "id"),
        }
        table, key = mapping[ref.ref_type]
        if ref.ref_type == "taxonomy_snapshot":
            try:
                lookup: object = int(ref.ref_id)
            except ValueError as exc:
                raise ResearchValidationError(
                    "taxonomy_snapshot ref_id must be an integer"
                ) from exc
        else:
            lookup = ref.ref_id
        row = connection.execute(
            f"SELECT * FROM {table} WHERE {key}=?", (lookup,)
        ).fetchone()
        if row is None:
            raise ResearchValidationError(
                f"Workspace source ref does not exist: {ref.ref_type}:{ref.ref_id}"
            )
        value = dict(row)
        if ref.ref_type != "taxonomy_snapshot" and str(value["task_id"]) != ref.task_id:
            raise ResearchValidationError("Workspace source ref crossed its Task boundary")
        return value

    @staticmethod
    def _source_href(ref: WorkspaceSourceRef) -> str:
        if ref.ref_type == "taxonomy_snapshot":
            return f"/taxonomy?snapshot_id={ref.ref_id}"
        return f"/research/{ref.task_id}"

    @staticmethod
    def _validate_feedback_preference_sources(
        connection: sqlite3.Connection,
        *,
        command_task_id: str,
        source_refs: list[dict[str, Any]],
        semantic_key: str,
        payload: dict[str, Any],
        principal_id: str,
    ) -> None:
        if set(payload) != {"statement"}:
            raise ResearchValidationError(
                "Stage 1 preference candidate requires exact statement payload"
            )
        proposed_value = _normalized_key(str(payload["statement"]))
        if (
            semantic_key != LIMITATIONS_POSITION_KEY
            or proposed_value not in LIMITATIONS_POSITIONS
        ):
            raise ResearchValidationError("unsupported Stage 1 preference candidate")
        if len(source_refs) < 2 or any(
            value["ref_type"] != "research_event" for value in source_refs
        ):
            raise ResearchValidationError(
                "Stage 1 preference candidate requires at least two Feedback Events"
            )

        for ref in source_refs:
            row = connection.execute(
                "SELECT task_id, event_id, event_type, payload_json, command_id "
                "FROM research_events WHERE event_id=?",
                (ref["ref_id"],),
            ).fetchone()
            if (
                row is None
                or str(row["task_id"]) != command_task_id
                or str(row["event_type"]) != "v5b_product_feedback_recorded"
            ):
                raise ResearchValidationError(
                    "preference candidate sources must be same-Task Feedback Events"
                )
            try:
                event_payload = json.loads(str(row["payload_json"]))
            except (TypeError, ValueError) as exc:
                raise ResearchConflict("Feedback Event payload is invalid") from exc
            if not isinstance(event_payload, dict):
                raise ResearchConflict("Feedback Event payload is invalid")
            preference = event_payload.get("candidate_preference")
            if not isinstance(preference, dict) or set(preference) != {
                "semantic_key",
                "proposed_value",
            }:
                raise ResearchValidationError(
                    "Feedback Event lacks an exact structured candidate preference"
                )
            if (
                _normalized_key(str(preference["semantic_key"])) != semantic_key
                or _normalized_key(str(preference["proposed_value"]))
                != proposed_value
            ):
                raise ResearchValidationError(
                    "Feedback Events must have the exact candidate key and value"
                )
            if str(event_payload.get("principal_id") or "") != principal_id:
                raise ResearchValidationError(
                    "Feedback Event principal_id does not match the current principal"
                )
            if event_payload.get("authority") != "advisory_feedback_only" or (
                event_payload.get("automatic_action") is not False
            ):
                raise ResearchValidationError("Feedback Event authority is invalid")

            target_kind = str(event_payload.get("target_kind") or "")
            target_id = str(event_payload.get("target_id") or "")
            target_hash = str(event_payload.get("target_hash") or "")
            if target_kind == "topic_page_revision":
                target = connection.execute(
                    "SELECT content_hash FROM research_topic_page_revisions "
                    "WHERE task_id=? AND page_revision_id=?",
                    (command_task_id, target_id),
                ).fetchone()
                hash_column = "content_hash"
            elif target_kind == "artifact_route":
                target = connection.execute(
                    "SELECT expected_authority_hash FROM research_artifact_routes "
                    "WHERE task_id=? AND record_id=?",
                    (command_task_id, target_id),
                ).fetchone()
                hash_column = "expected_authority_hash"
            else:
                target = None
                hash_column = ""
            if target is None or str(target[hash_column]) != target_hash:
                raise ResearchValidationError(
                    "Feedback Event target/hash is not the exact immutable target"
                )
            receipt = connection.execute(
                "SELECT 1 FROM research_command_receipts "
                "WHERE task_id=? AND command_id=? AND outcome_reference=? "
                "AND command_type='v5b_product_feedback' AND status='committed'",
                (
                    command_task_id,
                    str(row["command_id"]),
                    str(row["event_id"]),
                ),
            ).fetchone()
            if receipt is None:
                raise ResearchValidationError(
                    "Feedback Event lacks its committed CommandReceipt"
                )

    def _create_semantics(
        self,
        record_kind: str,
        payload: dict[str, Any],
        source_refs: list[dict[str, Any]],
    ) -> tuple[str, str]:
        if record_kind == "explicit_memory":
            self._require_keys(payload, {"key", "value"})
            if source_refs:
                raise ResearchValidationError(
                    "explicit memory is user-authored; inferred sources require candidate kind"
                )
            return "user_authored", "current"
        if record_kind == "inferred_candidate":
            self._require_keys(payload, {"statement"})
            self._require_multiple_event_refs(source_refs)
            return "behavioral_candidate", "candidate"
        if record_kind == "focus_state":
            self._require_keys(payload, {"topic", "state"})
            if source_refs:
                self._require_multiple_event_refs(source_refs)
                return "behavioral_candidate", "candidate"
            return "user_authored", "confirmed"
        if record_kind == "progress_observation":
            self._require_keys(payload, {"topic", "state"})
            state = str(payload["state"])
            if state not in PROGRESS_STATES:
                raise ResearchValidationError("unsupported progress state")
            user_asserted = payload.get("user_asserted") is True
            if state in SELF_ASSESSMENT_STATES and not user_asserted:
                raise ResearchValidationError(
                    "learned/understood/familiar requires explicit user assertion"
                )
            if user_asserted:
                return "user_authored", "current"
            if not source_refs:
                raise ResearchValidationError(
                    "evidence-backed progress requires source refs"
                )
            return "evidence_backed_observation", "current"
        if record_kind == "corpus_observation":
            self._require_keys(payload, {"observation_type", "value"})
            if payload["observation_type"] not in CORPUS_OBSERVATION_TYPES:
                raise ResearchValidationError("unsupported corpus observation type")
            if len(source_refs) != 1 or source_refs[0]["ref_type"] != "taxonomy_snapshot":
                raise ResearchValidationError(
                    "corpus observation requires exactly one frozen taxonomy snapshot"
                )
            return "corpus_soft_prior", "current"
        if record_kind == "system_experience":
            self._require_keys(
                payload, {"observed_pattern", "outcome", "environment_fingerprint"}
            )
            kinds = {value["ref_type"] for value in source_refs}
            if not {"research_trace", "research_result"}.issubset(kinds):
                raise ResearchValidationError(
                    "system experience requires Trace and Result lineage"
                )
            task_ids = {value["task_id"] for value in source_refs if value["task_id"]}
            if len(task_ids) != 1:
                raise ResearchValidationError(
                    "system experience source refs must share one Task boundary"
                )
            return "experience_candidate", "observed"
        raise ResearchValidationError("unsupported WorkspaceRecord kind")

    @staticmethod
    def _decision_semantics(
        latest: sqlite3.Row,
        request: DecideWorkspaceRecordRequest,
        payload: dict[str, Any],
        source_refs: list[dict[str, Any]],
    ) -> tuple[str, str, dict[str, Any]]:
        kind = str(latest["record_kind"])
        status = str(latest["status"])
        action = request.action
        authority = str(latest["authority_class"])
        next_payload = dict(payload)
        if action == "correct":
            if kind == "system_experience":
                raise ResearchValidationError("system experience uses diagnose, not correct")
            next_payload = dict(request.replacement_payload or {})
            if kind in {"inferred_candidate", "focus_state", "progress_observation"}:
                next_status = "confirmed" if kind != "progress_observation" else "current"
                return "user_confirmed", next_status, next_payload
            if kind == "corpus_observation":
                return "corpus_soft_prior", "current", next_payload
            return authority, "current", next_payload
        if action == "confirm":
            if kind not in {"inferred_candidate", "focus_state"}:
                raise ResearchValidationError("only inferred/focus candidates can be confirmed")
            return "user_confirmed", "confirmed", next_payload
        if action == "reject":
            if kind not in {"inferred_candidate", "focus_state"}:
                raise ResearchValidationError("only inferred/focus records can be rejected")
            return "behavioral_candidate", "rejected", next_payload
        if action == "expire":
            if kind not in {
                "explicit_memory",
                "inferred_candidate",
                "focus_state",
                "progress_observation",
            }:
                raise ResearchValidationError("this record kind does not support expire")
            return authority, "expired", next_payload
        if action == "tombstone":
            return authority, "tombstoned", next_payload
        if action == "invalidate":
            if kind not in {"corpus_observation", "system_experience"}:
                raise ResearchValidationError("only corpus/experience can be invalidated")
            return authority, "invalidated", next_payload
        if action == "diagnose":
            if kind != "system_experience" or status not in {"observed", "diagnosed"}:
                raise ResearchValidationError("diagnose requires observed/diagnosed experience")
            next_payload["diagnosis"] = dict(request.replacement_payload or {})
            return "experience_candidate", "diagnosed", next_payload
        if action == "candidate_source":
            if kind != "system_experience" or status != "diagnosed":
                raise ResearchValidationError(
                    "candidate_source requires latest diagnosed experience"
                )
            return "experience_candidate", "candidate_source", next_payload
        raise ResearchValidationError("unsupported WorkspaceRecord decision")

    @staticmethod
    def _require_keys(payload: dict[str, Any], keys: set[str]) -> None:
        if not keys.issubset(payload):
            raise ResearchValidationError(
                f"Workspace payload requires keys: {', '.join(sorted(keys))}"
            )
        for key in keys:
            if not str(payload[key]).strip():
                raise ResearchValidationError(f"Workspace payload {key} must not be blank")

    @staticmethod
    def _require_multiple_event_refs(source_refs: list[dict[str, Any]]) -> None:
        events = [value for value in source_refs if value["ref_type"] == "research_event"]
        if len(events) < 2:
            raise ResearchValidationError(
                "behavioral inference requires at least two distinct Research Events"
            )

    @classmethod
    def _assert_safe_payload(cls, payload: dict[str, Any]) -> None:
        encoded = _canonical_json(payload)
        if len(encoded.encode("utf-8")) > 32768:
            raise ResearchValidationError("Workspace payload exceeds 32 KiB")

        def inspect(value: object) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if str(key).casefold() in SECRET_KEYS:
                        raise ResearchValidationError(
                            "Workspace payload must not contain credential fields"
                        )
                    inspect(item)
            elif isinstance(value, list):
                for item in value:
                    inspect(item)

        inspect(payload)

    @staticmethod
    def _expires_value(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ResearchValidationError("expires_at must include a timezone")
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds")

    @staticmethod
    def _content_hash(
        *,
        record_kind: str,
        authority_class: str,
        status: str,
        semantic_key: str,
        payload: dict[str, Any],
        source_refs: list[dict[str, Any]],
        confidence: float | None,
        expires_at: str | None,
    ) -> str:
        return _hash(
            {
                "record_kind": record_kind,
                "authority_class": authority_class,
                "status": status,
                "semantic_key": semantic_key,
                "payload": payload,
                "source_refs": source_refs,
                "confidence": confidence,
                "expires_at": expires_at,
                "policy_version": PERSONAL_WORKSPACE_POLICY_VERSION,
            }
        )

    @staticmethod
    def _latest(
        connection: sqlite3.Connection,
        record_id: str,
        *,
        required: bool = True,
    ) -> sqlite3.Row | None:
        row = connection.execute(
            "SELECT * FROM research_workspace_records WHERE record_id=? "
            "ORDER BY version DESC LIMIT 1",
            (record_id,),
        ).fetchone()
        if row is None and required:
            raise ResearchNotFound(f"WorkspaceRecord does not exist: {record_id}")
        return row

    @classmethod
    def _project(cls, row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            raise ResearchNotFound("WorkspaceRecord does not exist")
        stored_status = str(row["status"])
        effective_status = stored_status
        if row["expires_at"] and stored_status in ACTIVE_EXPIRABLE_STATUSES:
            if _parse_iso(str(row["expires_at"])) <= datetime.now(timezone.utc):
                effective_status = "expired"
        projected = {
            "record_revision_id": str(row["record_revision_id"]),
            "record_id": str(row["record_id"]),
            "version": int(row["version"]),
            "parent_revision_id": (
                str(row["parent_revision_id"]) if row["parent_revision_id"] else None
            ),
            "command_task_id": str(row["command_task_id"]),
            "record_kind": str(row["record_kind"]),
            "authority_class": str(row["authority_class"]),
            "status": stored_status,
            "effective_status": effective_status,
            "semantic_key": str(row["semantic_key"]),
            "payload": _decode(row["payload_json"], dict),
            "source_refs": _decode(row["source_refs_json"], list),
            "source_boundary_hash": str(row["source_boundary_hash"]),
            "confidence": (
                float(row["confidence"]) if row["confidence"] is not None else None
            ),
            "expires_at": str(row["expires_at"]) if row["expires_at"] else None,
            "decision_action": str(row["decision_action"]),
            "reason": str(row["reason"]),
            "principal_id": str(row["principal_id"]),
            "policy_version": str(row["policy_version"]),
            "content_hash": str(row["content_hash"]),
            "created_at": str(row["created_at"]),
        }
        projected["user_state_authority"] = (
            projected["authority_class"] in {"user_authored", "user_confirmed"}
            and effective_status in {"current", "confirmed"}
        )
        projected["candidate_only"] = projected["authority_class"] in {
            "behavioral_candidate",
            "experience_candidate",
        }
        projected["soft_prior_only"] = (
            projected["authority_class"] == "corpus_soft_prior"
        )
        projected["product_behavior_effect"] = False
        projected["allowed_actions"] = cls._allowed_actions(projected)
        return projected

    @staticmethod
    def _allowed_actions(value: dict[str, Any]) -> list[str]:
        kind = value["record_kind"]
        status = value["effective_status"]
        if kind == "explicit_memory":
            if status in {"expired", "tombstoned"}:
                return ["correct"]
            return ["correct", "expire", "tombstone"]
        if kind in {"inferred_candidate", "focus_state"}:
            if status == "candidate":
                return ["confirm", "correct", "reject", "expire", "tombstone"]
            if status in {"rejected", "expired", "tombstoned"}:
                return ["confirm", "correct", "tombstone"]
            return ["correct", "reject", "expire", "tombstone"]
        if kind == "progress_observation":
            if status in {"expired", "tombstoned"}:
                return ["correct"]
            return ["correct", "expire", "tombstone"]
        if kind == "corpus_observation":
            if status in {"invalidated", "tombstoned"}:
                return ["correct"]
            return ["correct", "invalidate", "tombstone"]
        if status == "observed":
            return ["diagnose", "invalidate", "tombstone"]
        if status == "diagnosed":
            return ["diagnose", "candidate_source", "invalidate", "tombstone"]
        if status == "candidate_source":
            return ["invalidate", "tombstone"]
        return []
