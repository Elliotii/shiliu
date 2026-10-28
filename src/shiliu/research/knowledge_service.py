from __future__ import annotations

import hashlib
import json
from psycopg import Connection
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shiliu.research.errors import ResearchForbidden
from shiliu.db import Database, json_field
from shiliu.storage.dto import iso_time, json_value
from shiliu.research.service import _parse_iso
from shiliu.research.errors import (
    ResearchConflict,
    ResearchNotFound,
    ResearchUnsafeState,
    ResearchValidationError,
)
from shiliu.research.inner_evidence import PersistentEvidenceAuthority
from shiliu.research.integrated_journey import IntegratedJourneyProjection
from shiliu.research.knowledge_contracts import (
    AssessArtifactRouteRequest,
    BuildKnowledgeArtifactRequest,
    BuildTopicPageRequest,
    CreateWorkspaceRecordRequest,
    DecideWorkspaceRecordRequest,
    EditTopicPageRequest,
    ExportTopicPageRequest,
    IntakeKnowledgeCandidatesRequest,
    PublishResearchKnowledgeRequest,
    ProceedArtifactRouteRequest,
    ProposeFactUpdateRequest,
    RecoverKnowledgeOperationsRequest,
    ResolveKnowledgeOperationRequest,
    RevalidateKnowledgeRequest,
    ReviewFactUpdateRequest,
    ReviewKnowledgeCandidateRequest,
    ReviewTopicPageRequest,
    RevertTopicPageRequest,
    RunKnowledgeOperationRequest,
    SubmitKnowledgeFeedbackRequest,
)
from shiliu.research.knowledge_assistance import KnowledgeAssistanceProjection
from shiliu.research.knowledge_lifecycle import ResearchKnowledgeLifecycleService
from shiliu.research.knowledge_reuse import ResearchArtifactRouteService
from shiliu.research.personal_workspace import ResearchPersonalWorkspaceService
from shiliu.research.product_closeout import ResearchProductCloseoutService
from shiliu.research.product_service import (
    CANDIDATE_DELTA_SCHEMA_VERSION,
    ResearchProductService,
)
from shiliu.research.routing_recommendation import RouteRecommendationProjection
from shiliu.research.schema import (
    KNOWLEDGE_ARTIFACT_POLICY_VERSION,
    KNOWLEDGE_VALIDATION_POLICY_VERSION,
    KNOWLEDGE_WORKSPACE_SCHEMA_VERSION,
    TOPIC_PAGE_POLICY_VERSION,
)
from shiliu.research.service import ResearchTaskService
from shiliu.retrieval.service import RetrievalService
from shiliu.taxonomy.corpus import TaxonomyCorpusService


FaultInjector = Callable[[str], None]


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _id(prefix: str, value: object) -> str:
    return f"{prefix}_{_hash(value)[:32]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _json_list(value: object) -> list[Any]:
    decoded = json_value(value or '[]')
    if not isinstance(decoded, list):
        raise ResearchUnsafeState("persisted JSON list is invalid")
    return decoded


class ResearchKnowledgeService:
    """V5-B no-Provider knowledge path through the lean Stage 3 route."""

    def __init__(
        self,
        db: Database,
        *,
        kernel: ResearchTaskService,
        product: ResearchProductService,
        retrieval: RetrievalService,
        taxonomy: TaxonomyCorpusService | None = None,
        export_root: Path,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self.db = db
        self.context = db.context
        self.kernel = kernel
        self.product = product
        self.authority = PersistentEvidenceAuthority(db, retrieval.artifacts)
        self.fault_injector = fault_injector or (lambda _point: None)
        self._command_lock = threading.RLock()
        self.lifecycle = ResearchKnowledgeLifecycleService(
            db,
            kernel=kernel,
            artifacts=retrieval.artifacts,
            export_root=export_root,
            fault_injector=self.fault_injector,
        )
        self.reuse = ResearchArtifactRouteService(
            db,
            kernel=kernel,
            retrieval=retrieval,
            fault_injector=self.fault_injector,
        )
        self.personal_workspace = ResearchPersonalWorkspaceService(
            db,
            kernel=kernel,
            fault_injector=self.fault_injector,
        )
        self.route_recommendation = RouteRecommendationProjection(
            db,
            artifact_routes=self.reuse,
        )
        self.knowledge_assistance = KnowledgeAssistanceProjection(
            db,
            taxonomy=taxonomy or TaxonomyCorpusService(db, retrieval.artifacts),
        )
        self.integrated_journey = IntegratedJourneyProjection()
        self.closeout = ResearchProductCloseoutService(
            db,
            kernel=kernel,
            fault_injector=self.fault_injector,
        )

    def _sync_lifecycle_fault_injector(self) -> None:
        self.lifecycle.fault_injector = self.fault_injector
        self.reuse.fault_injector = self.fault_injector
        self.personal_workspace.fault_injector = self.fault_injector
        self.closeout.fault_injector = self.fault_injector

    def intake_candidates(
        self, task_id: str, request: IntakeKnowledgeCandidatesRequest
    ) -> dict[str, Any]:
        request = IntakeKnowledgeCandidatesRequest.model_validate(
            request.model_dump(mode="json")
        )
        self.product.ensure_candidate_deltas(task_id)
        payload = {"operation": "intake_knowledge_candidates", "task_id": task_id}
        payload_hash = _hash(payload)
        with self._command_lock, self.kernel._transaction() as connection:
            task = self.kernel._task(connection, task_id)
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}
            event = connection.execute(
                "SELECT * FROM research_events WHERE research_events.workspace_id=%s AND  task_id=%s AND event_type='candidate_deltas_materialized' ORDER BY sequence DESC LIMIT 1",
                (self.context.workspace_id, task_id),
            ).fetchone()
            if event is None:
                raise ResearchUnsafeState(
                    "Task 尚未到达可生成 KnowledgeDelta 的持久边界"
                )
            snapshot = json_value(event['payload_json'])
            self._validate_candidate_snapshot(connection, task_id, event, snapshot)
            delta = next(
                (
                    value
                    for value in snapshot["deltas"]
                    if value.get("delta_kind") == "KnowledgeDelta"
                ),
                None,
            )
            if delta is None:
                raise ResearchUnsafeState("candidate snapshot 缺少 KnowledgeDelta")
            artifact = connection.execute(
                'SELECT * FROM research_provisional_artifacts WHERE research_provisional_artifacts.workspace_id=%s AND  task_id=%s AND attempt_id=%s ORDER BY created_at DESC, artifact_id DESC LIMIT 1',
                (self.context.workspace_id, task_id, str(event['attempt_id'] or '')),
            ).fetchone()
            if delta.get("items") and artifact is None:
                raise ResearchUnsafeState("KnowledgeDelta 缺少来源 provisional artifact")
            source_use_ids = {str(value) for value in snapshot["evidence_use_ids"]}
            candidate_ids: list[str] = []
            now = _now()
            for index, item in enumerate(delta.get("items") or []):
                claim = " ".join(str(item.get("summary") or "").split())
                if not claim:
                    continue
                citations = [str(value) for value in item.get("citation_ids") or []]
                evidence_use_ids = self._map_candidate_evidence_uses(
                    connection,
                    task_id=task_id,
                    attempt_id=str(event["attempt_id"]),
                    citation_ids=citations,
                    allowed_use_ids=source_use_ids,
                )
                source_item_hash = _hash(
                    {
                        "source_delta_hash": delta["candidate_hash"],
                        "source_item_index": index,
                        "item": item,
                    }
                )
                candidate_id = _id(
                    "kcandidate",
                    {"source_event_id": event["event_id"], "item": source_item_hash},
                )
                connection.execute(
                    """
                    INSERT INTO research_knowledge_candidates(workspace_id, candidate_id, workspace_schema_version, task_id, goal_id, attempt_id, checkpoint_id, result_id, provisional_artifact_id, source_event_id, source_delta_snapshot_id, candidate_kind, source_boundary_hash, source_delta_hash, source_item_hash, source_item_index, parent_candidate_id, claim_text, citation_ids_json, evidence_use_ids_json, source_payload_json, status, state_version, created_at, updated_at) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'KnowledgeDelta', %s, %s, %s, %s, NULL, %s, %s, %s, %s, 'pending_review', 0, %s, %s)
                     ON CONFLICT DO NOTHING""",
                    (self.context.workspace_id, candidate_id, KNOWLEDGE_WORKSPACE_SCHEMA_VERSION, task_id, str(event['goal_id']), str(event['attempt_id']), str(event['checkpoint_id']) if event['checkpoint_id'] else None, str(snapshot['result_id']) if snapshot.get('result_id') else None, str(artifact['artifact_id']), str(event['event_id']), str(snapshot['delta_snapshot_id']), str(snapshot['boundary_hash']), str(delta['candidate_hash']), source_item_hash, index, claim, json_field(_canonical_json(citations)), json_field(_canonical_json(evidence_use_ids)), json_field(_canonical_json(item)), _parse_iso(now), _parse_iso(now)),
                )
                candidate_ids.append(candidate_id)
            self.fault_injector("after_knowledge_candidate_rows")
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                attempt_id=str(event["attempt_id"]) if event["attempt_id"] else None,
                checkpoint_id=(
                    str(event["checkpoint_id"]) if event["checkpoint_id"] else None
                ),
                event_type="knowledge_candidates_intaked",
                payload={
                    "source_event_id": str(event["event_id"]),
                    "delta_snapshot_id": snapshot["delta_snapshot_id"],
                    "candidate_ids": candidate_ids,
                },
                command_id=request.command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            response = {
                "task_id": task_id,
                "source_event_id": str(event["event_id"]),
                "candidate_ids": candidate_ids,
                "candidate_count": len(candidate_ids),
            }
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="intake_knowledge_candidates",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.fault_injector("after_knowledge_candidate_receipt")
        return {**response, "deduplicated": False}

    def _validate_candidate_snapshot(self,
        connection: Connection,
        task_id: str,
        event: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> None:
        if (
            snapshot.get("candidate_delta_schema_version")
            != CANDIDATE_DELTA_SCHEMA_VERSION
            or snapshot.get("task_id") != task_id
            or snapshot.get("authority") != "candidate_only_not_promoted"
            or snapshot.get("attempt_id") != event["attempt_id"]
            or not isinstance(snapshot.get("deltas"), list)
            or not isinstance(snapshot.get("evidence_use_ids"), list)
        ):
            raise ResearchUnsafeState("candidate snapshot identity/authority invalid")
        unsigned_snapshot = dict(snapshot)
        stored_snapshot_id = str(unsigned_snapshot.pop("delta_snapshot_id", ""))
        if stored_snapshot_id != f"delta_{_hash(unsigned_snapshot)[:32]}":
            raise ResearchUnsafeState("candidate snapshot hash invalid")
        for delta in snapshot["deltas"]:
            if not isinstance(delta, dict):
                raise ResearchUnsafeState("candidate delta payload invalid")
            unsigned_delta = dict(delta)
            stored_delta_hash = str(unsigned_delta.pop("candidate_hash", ""))
            if stored_delta_hash != _hash(
                {"boundary_hash": snapshot.get("boundary_hash"), **unsigned_delta}
            ):
                raise ResearchUnsafeState("candidate delta hash invalid")
        receipt = connection.execute(
            "SELECT 1 FROM research_command_receipts WHERE research_command_receipts.workspace_id=%s AND  task_id=%s AND command_id=%s AND outcome_reference=%s AND status='committed'",
            (self.context.workspace_id, task_id, str(event['command_id']), str(event['event_id'])),
        ).fetchone()
        if receipt is None:
            raise ResearchUnsafeState("candidate snapshot lacks committed source receipt")

    def _map_candidate_evidence_uses(self,
        connection: Connection,
        *,
        task_id: str,
        attempt_id: str,
        citation_ids: list[str],
        allowed_use_ids: set[str],
    ) -> list[str]:
        if not citation_ids:
            return []
        rows = connection.execute(
            """
            SELECT eu.evidence_use_id, ei.evidence_id
            FROM research_evidence_uses eu
            JOIN research_evidence_identities ei ON (ei.workspace_id,ei.evidence_id)=(eu.workspace_id,eu.evidence_id)
            WHERE eu.workspace_id=%s AND eu.task_id=%s AND eu.attempt_id=%s
              AND ei.evidence_id=ANY(%s)
            """,
            (self.context.workspace_id, task_id, attempt_id, citation_ids),
        ).fetchall()
        by_evidence = {
            str(row["evidence_id"]): str(row["evidence_use_id"])
            for row in rows
            if str(row["evidence_use_id"]) in allowed_use_ids
        }
        return [by_evidence[value] for value in citation_ids if value in by_evidence]

    def review_candidate(
        self,
        task_id: str,
        candidate_id: str,
        request: ReviewKnowledgeCandidateRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        request = ReviewKnowledgeCandidateRequest.model_validate(
            request.model_dump(mode="json")
        )
        payload = {
            "operation": "review_knowledge_candidate",
            "task_id": task_id,
            "candidate_id": candidate_id,
            **request.model_dump(mode="json", exclude={"command_id"}),
        }
        payload_hash = _hash(payload)
        with self._command_lock, self.kernel._transaction() as connection:
            task = self.kernel._task(connection, task_id)
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}
            candidate = connection.execute(
                'SELECT * FROM research_knowledge_candidates WHERE research_knowledge_candidates.workspace_id=%s AND  candidate_id=%s',
                (self.context.workspace_id, candidate_id),
            ).fetchone()
            if candidate is None or str(candidate["task_id"]) != task_id:
                raise ResearchNotFound(f"Knowledge Candidate 不存在: {candidate_id}")
            if int(candidate["state_version"]) != request.expected_state_version:
                raise ResearchConflict(
                    "stale candidate state: "
                    f"expected {request.expected_state_version}, "
                    f"current {candidate['state_version']}"
                )
            status = str(candidate["status"])
            allowed = {"pending_review", "needs_revalidation"}
            if status not in allowed:
                raise ResearchConflict(f"Candidate 已完成审查: {status}")
            if request.decision == "accept" and status != "pending_review":
                raise ResearchUnsafeState(
                    "needs_revalidation Candidate 没有服务器 validator，不得接受"
                )
            now = _now()
            decision_id = _id(
                "kdecision",
                {"task_id": task_id, "command_id": request.command_id},
            )
            response: dict[str, Any]
            edited_candidate_id: str | None = None
            fact_revision_id: str | None = None
            decision_reason = request.reason
            if request.decision == "accept":
                validation = self._validate_candidate_evidence(
                    connection, candidate=candidate, command_id=request.command_id, now=now
                )
                if not validation["all_current"]:
                    decision_reason = decision_reason or "server_currentness_validation_failed"
                    connection.execute(
                        "UPDATE research_knowledge_candidates SET status='needs_revalidation', state_version=state_version+1, updated_at=%s WHERE research_knowledge_candidates.workspace_id=%s AND  candidate_id=%s",
                        (_parse_iso(now), self.context.workspace_id, candidate_id),
                    )
                    response = {
                        "task_id": task_id,
                        "candidate_id": candidate_id,
                        "status": "needs_revalidation",
                        "state_version": request.expected_state_version + 1,
                        "fact_revision_id": None,
                        "validation_outcomes": validation["outcomes"],
                    }
                else:
                    fact_revision_id = self._create_initial_fact(
                        connection,
                        candidate=candidate,
                        validation_rows=validation["rows"],
                        now=now,
                    )
                    self.fault_injector("after_initial_fact_revision")
                    connection.execute(
                        "UPDATE research_knowledge_candidates SET status='accepted', state_version=state_version+1, updated_at=%s WHERE research_knowledge_candidates.workspace_id=%s AND  candidate_id=%s",
                        (_parse_iso(now), self.context.workspace_id, candidate_id),
                    )
                    response = {
                        "task_id": task_id,
                        "candidate_id": candidate_id,
                        "status": "accepted",
                        "state_version": request.expected_state_version + 1,
                        "fact_revision_id": fact_revision_id,
                        "validation_outcomes": validation["outcomes"],
                    }
            elif request.decision == "reject":
                connection.execute(
                    "UPDATE research_knowledge_candidates SET status='rejected', state_version=state_version+1, updated_at=%s WHERE research_knowledge_candidates.workspace_id=%s AND  candidate_id=%s",
                    (_parse_iso(now), self.context.workspace_id, candidate_id),
                )
                response = {
                    "task_id": task_id,
                    "candidate_id": candidate_id,
                    "status": "rejected",
                    "state_version": request.expected_state_version + 1,
                    "fact_revision_id": None,
                }
            else:
                edited_candidate_id = self._create_edited_candidate(
                    connection,
                    candidate=candidate,
                    command_id=request.command_id,
                    claim=str(request.edited_claim),
                    now=now,
                )
                connection.execute(
                    "UPDATE research_knowledge_candidates SET status='superseded', state_version=state_version+1, updated_at=%s WHERE research_knowledge_candidates.workspace_id=%s AND  candidate_id=%s",
                    (_parse_iso(now), self.context.workspace_id, candidate_id),
                )
                response = {
                    "task_id": task_id,
                    "candidate_id": candidate_id,
                    "status": "superseded",
                    "state_version": request.expected_state_version + 1,
                    "edited_candidate_id": edited_candidate_id,
                    "edited_candidate_status": "needs_revalidation",
                    "fact_revision_id": None,
                }
            connection.execute(
                """
                INSERT INTO research_knowledge_review_decisions(workspace_id, decision_id, task_id, candidate_id, decision_kind, reason, edited_candidate_id, fact_revision_id, expected_candidate_version, command_id, principal_id, created_at) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (self.context.workspace_id, decision_id, task_id, candidate_id, request.decision, decision_reason, edited_candidate_id, fact_revision_id, request.expected_state_version, request.command_id, principal_id, _parse_iso(now)),
            )
            self.fault_injector("after_knowledge_review_decision")
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(candidate["goal_id"]),
                attempt_id=str(candidate["attempt_id"]),
                checkpoint_id=(
                    str(candidate["checkpoint_id"])
                    if candidate["checkpoint_id"]
                    else None
                ),
                event_type="knowledge_candidate_reviewed",
                payload={
                    "candidate_id": candidate_id,
                    "decision_id": decision_id,
                    "decision": request.decision,
                    "result_status": response["status"],
                    "edited_candidate_id": edited_candidate_id,
                    "fact_revision_id": fact_revision_id,
                },
                command_id=request.command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="review_knowledge_candidate",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.fault_injector("after_knowledge_review_receipt")
        return {**response, "deduplicated": False}

    def publish_selected_candidates(
        self,
        task_id: str,
        request: PublishResearchKnowledgeRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        """Reuse the accepted V5-B steps behind one explicit product confirmation.

        Each sub-command has a stable command id, so retrying the same product
        confirmation resumes through the existing receipts instead of creating a
        second Fact, Artifact, or Topic Page.
        """
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        request = PublishResearchKnowledgeRequest.model_validate(
            request.model_dump(mode="json")
        )
        fact_revision_ids: list[str] = []
        candidate_ids: list[str] = []
        for index, selection in enumerate(request.selections):
            reviewed = self.review_candidate(
                task_id,
                selection.candidate_id,
                ReviewKnowledgeCandidateRequest(
                    command_id=f"{request.command_id}:candidate:{index}",
                    decision="accept",
                    expected_state_version=selection.expected_state_version,
                    reason="user confirmed long-term knowledge publication",
                ),
                principal_id=principal_id,
            )
            fact_revision_id = reviewed.get("fact_revision_id")
            if reviewed.get("status") != "accepted" or not fact_revision_id:
                raise ResearchValidationError(
                    "selected conclusion could not pass current evidence validation"
                )
            candidate_ids.append(selection.candidate_id)
            fact_revision_ids.append(str(fact_revision_id))

        artifact = self.build_artifact(
            task_id,
            BuildKnowledgeArtifactRequest(
                command_id=f"{request.command_id}:artifact",
                fact_revision_ids=fact_revision_ids,
            ),
        )
        page = self.build_topic_page(
            task_id,
            BuildTopicPageRequest(
                command_id=f"{request.command_id}:page",
                artifact_revision_id=str(artifact["artifact_revision_id"]),
            ),
        )
        published = self.review_page(
            task_id,
            str(page["page_id"]),
            ReviewTopicPageRequest(
                command_id=f"{request.command_id}:publish",
                decision="publish",
                expected_version=int(page["version"]),
                reason="user confirmed reviewed conclusions and sources",
            ),
            principal_id=principal_id,
        )
        return {
            "task_id": task_id,
            "candidate_ids": candidate_ids,
            "fact_revision_ids": fact_revision_ids,
            "artifact_id": artifact["artifact_id"],
            "artifact_revision_id": artifact["artifact_revision_id"],
            "page_id": page["page_id"],
            "page_revision_id": page["page_revision_id"],
            "review_status": published["review_status"],
            "published_version": published["version"],
        }

    def _validate_candidate_evidence(
        self,
        connection: Connection,
        *,
        candidate: dict[str, Any],
        command_id: str,
        now: str,
    ) -> dict[str, Any]:
        use_ids = [str(value) for value in _json_list(candidate["evidence_use_ids_json"])]
        citation_ids = [str(value) for value in _json_list(candidate["citation_ids_json"])]
        if not use_ids or len(use_ids) != len(citation_ids):
            return {
                "all_current": False,
                "rows": [],
                "outcomes": [
                    {
                        "outcome": "invalid",
                        "reason_code": "candidate_evidence_mapping_incomplete",
                    }
                ],
            }
        rows: list[dict[str, str]] = []
        outcomes: list[dict[str, str | None]] = []
        for ordinal, use_id in enumerate(use_ids):
            row = connection.execute(
                """
                SELECT eu.*, ei.* FROM research_evidence_uses eu
                JOIN research_evidence_identities ei ON ei.workspace_id=eu.workspace_id AND ei.evidence_id=eu.evidence_id
                WHERE eu.workspace_id=%s AND  eu.evidence_use_id=%s
                """,
                (self.context.workspace_id, use_id),
            ).fetchone()
            if (
                row is None
                or str(row["task_id"]) != str(candidate["task_id"])
                or str(row["attempt_id"]) != str(candidate["attempt_id"])
                or str(row["evidence_id"]) != citation_ids[ordinal]
            ):
                return {
                    "all_current": False,
                    "rows": rows,
                    "outcomes": outcomes
                    + [
                        {
                            "evidence_use_id": use_id,
                            "outcome": "invalid",
                            "reason_code": "candidate_evidence_lineage_invalid",
                        }
                    ],
                }
            observation = self.authority.observe(row)
            observation_id = _id(
                "kvalidation",
                {
                    "command_id": command_id,
                    "evidence_use_id": use_id,
                    "policy": KNOWLEDGE_VALIDATION_POLICY_VERSION,
                },
            )
            connection.execute(
                """
                INSERT INTO research_evidence_validations(workspace_id, observation_id, evidence_use_id, evidence_id, task_id, goal_id, attempt_id, checkpoint_id, validation_policy_version, authority_mode, expected_source_version, observed_source_version, outcome, reason_code, owner_epoch, observed_at) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, 'live_current_exact_replay', %s, %s, %s, %s, %s, %s)
                """,
                (self.context.workspace_id, observation_id, use_id, str(row['evidence_id']), str(candidate['task_id']), str(candidate['goal_id']), str(candidate['attempt_id']), str(candidate['checkpoint_id']) if candidate['checkpoint_id'] else None, KNOWLEDGE_VALIDATION_POLICY_VERSION, observation.expected_source_version, observation.observed_source_version, observation.outcome, observation.reason_code, int(row['owner_epoch']), _parse_iso(now)),
            )
            rows.append(
                {
                    "evidence_use_id": use_id,
                    "evidence_id": str(row["evidence_id"]),
                    "observation_id": observation_id,
                }
            )
            outcomes.append(
                {
                    "evidence_use_id": use_id,
                    "evidence_id": str(row["evidence_id"]),
                    "outcome": observation.outcome,
                    "reason_code": observation.reason_code,
                    "observed_source_version": observation.observed_source_version,
                }
            )
        return {
            "all_current": bool(rows)
            and all(value["outcome"] == "current" for value in outcomes),
            "rows": rows,
            "outcomes": outcomes,
        }

    def _create_initial_fact(self,
        connection: Connection,
        *,
        candidate: dict[str, Any],
        validation_rows: list[dict[str, str]],
        now: str,
    ) -> str:
        fact_id = _id("fact", {"origin_candidate_id": candidate["candidate_id"]})
        fact_revision_id = _id(
            "factrev", {"fact_id": fact_id, "revision": 1}
        )
        temporal_scope: dict[str, Any] = {}
        viewpoint_scope: dict[str, Any] = {}
        content_hash = _hash(
            {
                "fact_id": fact_id,
                "revision": 1,
                "claim_text": candidate["claim_text"],
                "temporal_scope": temporal_scope,
                "viewpoint_scope": viewpoint_scope,
                "evidence": validation_rows,
            }
        )
        connection.execute(
            'INSERT INTO research_grounded_facts(workspace_id, fact_id, workspace_schema_version, task_id, origin_candidate_id, created_at) VALUES(%s, %s, %s, %s, %s, %s)',
            (self.context.workspace_id, fact_id, KNOWLEDGE_WORKSPACE_SCHEMA_VERSION, str(candidate['task_id']), str(candidate['candidate_id']), _parse_iso(now)),
        )
        connection.execute(
            """
            INSERT INTO research_fact_revisions(workspace_id, fact_revision_id, fact_id, task_id, revision, parent_revision_id, supersedes_revision_id, origin_candidate_id, claim_text, temporal_scope_json, viewpoint_scope_json, verification_status, content_hash, created_at) VALUES(%s, %s, %s, %s, 1, NULL, NULL, %s, %s, %s, %s, 'accepted_current', %s, %s)
            """,
            (self.context.workspace_id, fact_revision_id, fact_id, str(candidate['task_id']), str(candidate['candidate_id']), str(candidate['claim_text']), json_field(_canonical_json(temporal_scope)), json_field(_canonical_json(viewpoint_scope)), content_hash, _parse_iso(now)),
        )
        for ordinal, value in enumerate(validation_rows):
            connection.execute(
                """
                INSERT INTO research_fact_evidence_links(workspace_id, link_id, task_id, fact_revision_id, evidence_id, evidence_use_id, validation_observation_id, ordinal, created_at) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (self.context.workspace_id, _id('factevidence', {'fact_revision_id': fact_revision_id, 'evidence_use_id': value['evidence_use_id']}), str(candidate['task_id']), fact_revision_id, value['evidence_id'], value['evidence_use_id'], value['observation_id'], ordinal, _parse_iso(now)),
            )
        connection.execute(
            """
            INSERT INTO research_knowledge_fact_states(workspace_id, fact_id, task_id, current_revision_id, lifecycle_status, currentness_status, superseded_by_revision_id, latest_observation_set_id, state_version, updated_at) VALUES(%s, %s, %s, %s, 'current', 'current', NULL, NULL, 0, %s)
            """,
            (self.context.workspace_id, fact_id, str(candidate['task_id']), fact_revision_id, _parse_iso(now)),
        )
        return fact_revision_id

    def _create_edited_candidate(self,
        connection: Connection,
        *,
        candidate: dict[str, Any],
        command_id: str,
        claim: str,
        now: str,
    ) -> str:
        source_item_hash = _hash(
            {
                "edited_from": candidate["candidate_id"],
                "command_id": command_id,
                "claim_text": claim,
            }
        )
        candidate_id = _id(
            "kcandidate",
            {"parent_candidate_id": candidate["candidate_id"], "item": source_item_hash},
        )
        connection.execute(
            """
            INSERT INTO research_knowledge_candidates(workspace_id, candidate_id, workspace_schema_version, task_id, goal_id, attempt_id, checkpoint_id, result_id, provisional_artifact_id, source_event_id, source_delta_snapshot_id, candidate_kind, source_boundary_hash, source_delta_hash, source_item_hash, source_item_index, parent_candidate_id, claim_text, citation_ids_json, evidence_use_ids_json, source_payload_json, status, state_version, created_at, updated_at) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'KnowledgeDelta', %s, %s, %s, %s, %s, %s, %s, %s, %s, 'needs_revalidation', 0, %s, %s)
            """,
            (self.context.workspace_id, candidate_id, KNOWLEDGE_WORKSPACE_SCHEMA_VERSION, str(candidate['task_id']), str(candidate['goal_id']), str(candidate['attempt_id']), str(candidate['checkpoint_id']) if candidate['checkpoint_id'] else None, str(candidate['result_id']) if candidate['result_id'] else None, str(candidate['provisional_artifact_id']), str(candidate['source_event_id']), str(candidate['source_delta_snapshot_id']), str(candidate['source_boundary_hash']), str(candidate['source_delta_hash']), source_item_hash, int(candidate['source_item_index']), str(candidate['candidate_id']), claim, json_field(candidate['citation_ids_json']), json_field(candidate['evidence_use_ids_json']), json_field(_canonical_json({'edited_from': str(candidate['candidate_id']), 'claim_text': claim, 'authority': 'user_edit_needs_revalidation'})), _parse_iso(now), _parse_iso(now)),
        )
        return candidate_id

    def build_artifact(
        self, task_id: str, request: BuildKnowledgeArtifactRequest
    ) -> dict[str, Any]:
        request = BuildKnowledgeArtifactRequest.model_validate(
            request.model_dump(mode="json")
        )
        fact_ids = sorted(request.fact_revision_ids)
        build_input = {
            "fact_revision_ids": fact_ids,
            "build_policy_version": KNOWLEDGE_ARTIFACT_POLICY_VERSION,
        }
        return self._run_build(
            task_id=task_id,
            command_id=request.command_id,
            kind="artifact",
            build_input=build_input,
            finalize=lambda connection, task, run_id, input_hash, now: (
                self._finalize_artifact(
                    connection,
                    task=task,
                    fact_revision_ids=fact_ids,
                    build_run_id=run_id,
                    input_hash=input_hash,
                    now=now,
                )
            ),
        )

    def build_topic_page(
        self, task_id: str, request: BuildTopicPageRequest
    ) -> dict[str, Any]:
        request = BuildTopicPageRequest.model_validate(
            request.model_dump(mode="json")
        )
        build_input = {
            "artifact_revision_id": request.artifact_revision_id,
            "build_policy_version": TOPIC_PAGE_POLICY_VERSION,
        }
        return self._run_build(
            task_id=task_id,
            command_id=request.command_id,
            kind="topic_page",
            build_input=build_input,
            finalize=lambda connection, task, run_id, input_hash, now: (
                self._finalize_topic_page(
                    connection,
                    task=task,
                    artifact_revision_id=request.artifact_revision_id,
                    build_run_id=run_id,
                    input_hash=input_hash,
                    now=now,
                )
            ),
        )

    def _run_build(
        self,
        *,
        task_id: str,
        command_id: str,
        kind: str,
        build_input: dict[str, Any],
        finalize: Callable[
            [Connection, dict[str, Any], str, str, str], dict[str, Any]
        ],
    ) -> dict[str, Any]:
        input_hash = _hash(build_input)
        payload_hash = _hash(
            {
                "operation": f"build_{kind}",
                "task_id": task_id,
                "input": build_input,
            }
        )
        with self._command_lock:
            with self.kernel._transaction() as connection:
                task = self.kernel._task(connection, task_id)
                existing = self.kernel._existing_receipt(
                    connection,
                    task_id=task_id,
                    command_id=command_id,
                    payload_hash=payload_hash,
                )
                if existing is not None:
                    return {**existing, "deduplicated": True}
                self.lifecycle.ensure_stage1_heads(connection, task_id)
                self._validate_build_input(connection, task_id, kind, build_input)
                run = connection.execute(
                    'SELECT * FROM research_knowledge_build_runs WHERE research_knowledge_build_runs.workspace_id=%s AND  task_id=%s AND build_kind=%s AND input_hash=%s',
                    (self.context.workspace_id, task_id, kind, input_hash),
                ).fetchone()
                now = _now()
                if run is None:
                    run_id = _id(
                        "kbuild",
                        {"task_id": task_id, "kind": kind, "input_hash": input_hash},
                    )
                    connection.execute(
                        """
                        INSERT INTO research_knowledge_build_runs(workspace_id, build_run_id, workspace_schema_version, task_id, build_kind, command_id, input_hash, input_json, status, attempt_count, output_reference, error_code, error_detail, created_at, updated_at, completed_at) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, 'running', 1, NULL, NULL, NULL, %s, %s, NULL)
                        """,
                        (self.context.workspace_id, run_id, KNOWLEDGE_WORKSPACE_SCHEMA_VERSION, task_id, kind, command_id, input_hash, json_field(_canonical_json(build_input)), _parse_iso(now), _parse_iso(now)),
                    )
                else:
                    run_id = str(run["build_run_id"])
                    if str(run["status"]) == "succeeded":
                        response = self._build_response(
                            task_id=task_id,
                            kind=kind,
                            run_id=run_id,
                            output_reference=str(run["output_reference"]),
                            reused_build=True,
                        )
                        self._commit_build_receipt(
                            connection,
                            task=task,
                            command_id=command_id,
                            payload_hash=payload_hash,
                            kind=kind,
                            response=response,
                            now=now,
                        )
                        return {**response, "deduplicated": False}
                    if str(run["status"]) == "failed":
                        raise ResearchUnsafeState("failed BuildRun requires Stage 2 recovery")
                    connection.execute(
                        'UPDATE research_knowledge_build_runs SET attempt_count=attempt_count+1, updated_at=%s WHERE research_knowledge_build_runs.workspace_id=%s AND  build_run_id=%s',
                        (_parse_iso(now), self.context.workspace_id, run_id),
                    )
            self.fault_injector(f"after_{kind}_build_reserved")
            with self.kernel._transaction() as connection:
                task = self.kernel._task(connection, task_id)
                existing = self.kernel._existing_receipt(
                    connection,
                    task_id=task_id,
                    command_id=command_id,
                    payload_hash=payload_hash,
                )
                if existing is not None:
                    return {**existing, "deduplicated": True}
                run = connection.execute(
                    'SELECT * FROM research_knowledge_build_runs WHERE research_knowledge_build_runs.workspace_id=%s AND  build_run_id=%s',
                    (self.context.workspace_id, run_id),
                ).fetchone()
                if run is None or str(run["status"]) != "running":
                    raise ResearchConflict("BuildRun state changed during synchronous build")
                now = _now()
                output = finalize(connection, task, run_id, input_hash, now)
                output_reference = str(output["output_reference"])
                connection.execute(
                    "UPDATE research_knowledge_build_runs SET status='succeeded', output_reference=%s, error_code=NULL, error_detail=NULL, updated_at=%s, completed_at=%s WHERE research_knowledge_build_runs.workspace_id=%s AND  build_run_id=%s",
                    (output_reference, _parse_iso(now), _parse_iso(now), self.context.workspace_id, run_id),
                )
                self.fault_injector(f"after_{kind}_build_state")
                response = {
                    **self._build_response(
                        task_id=task_id,
                        kind=kind,
                        run_id=run_id,
                        output_reference=output_reference,
                        reused_build=False,
                    ),
                    **output,
                }
                self._commit_build_receipt(
                    connection,
                    task=task,
                    command_id=command_id,
                    payload_hash=payload_hash,
                    kind=kind,
                    response=response,
                    now=now,
                )
            return {**response, "deduplicated": False}

    def _validate_build_input(self,
        connection: Connection,
        task_id: str,
        kind: str,
        build_input: dict[str, Any],
    ) -> None:
        if kind == "artifact":
            ids = list(build_input["fact_revision_ids"])
            for fact_revision_id in ids:
                row = connection.execute(
                    """
                    SELECT fr.fact_revision_id, fr.verification_status,
                           kc.status AS candidate_status,
                           fs.current_revision_id, fs.lifecycle_status,
                           fs.currentness_status,
                           COUNT(fel.link_id) AS evidence_count,
                           SUM(CASE WHEN ev.outcome='current' THEN 0 ELSE 1 END)
                             AS noncurrent_count
                    FROM research_fact_revisions fr
                    JOIN research_grounded_facts gf ON gf.workspace_id=fr.workspace_id AND gf.fact_id=fr.fact_id
                    JOIN research_knowledge_candidates kc
                      ON kc.workspace_id=fr.workspace_id AND kc.candidate_id=gf.origin_candidate_id
                    JOIN research_knowledge_fact_states fs ON fs.workspace_id=fr.workspace_id AND fs.fact_id=fr.fact_id
                    LEFT JOIN research_fact_evidence_links fel
                      ON fel.workspace_id=fr.workspace_id AND fel.fact_revision_id=fr.fact_revision_id
                    LEFT JOIN research_evidence_validations ev
                      ON ev.workspace_id=fr.workspace_id AND ev.observation_id=fel.validation_observation_id
                    WHERE fr.workspace_id=%s AND  fr.task_id=%s AND fr.fact_revision_id=%s
                    GROUP BY fr.fact_revision_id, fr.verification_status, kc.status,
                             fs.current_revision_id, fs.lifecycle_status,
                             fs.currentness_status
                    """,
                    (self.context.workspace_id, task_id, fact_revision_id),
                ).fetchone()
                if (
                    row is None
                    or str(row["verification_status"]) != "accepted_current"
                    or str(row["candidate_status"]) != "accepted"
                    or int(row["evidence_count"]) < 1
                    or int(row["noncurrent_count"] or 0) != 0
                    or str(row["current_revision_id"]) != fact_revision_id
                    or str(row["lifecycle_status"]) != "current"
                    or str(row["currentness_status"]) != "current"
                ):
                    raise ResearchValidationError(
                        "artifact inputs must be accepted, current-grounded Fact "
                        "revisions from this Task"
                    )
            return
        artifact_id = str(build_input["artifact_revision_id"])
        row = connection.execute(
            """
            SELECT ar.artifact_id, ar.revision,
                   (SELECT MAX(ar2.revision)
                    FROM research_knowledge_artifact_revisions ar2
                    WHERE ar2.workspace_id=ar.workspace_id AND ar2.artifact_id=ar.artifact_id) AS max_revision,
                   SUM(CASE
                     WHEN fs.current_revision_id!=afl.fact_revision_id
                       OR fs.lifecycle_status!='current'
                       OR fs.currentness_status!='current'
                     THEN 1 ELSE 0 END) AS stale_fact_count
            FROM research_knowledge_artifact_revisions ar
            LEFT JOIN research_artifact_fact_links afl
              ON afl.workspace_id=ar.workspace_id AND afl.artifact_revision_id=ar.artifact_revision_id
            LEFT JOIN research_fact_revisions fr
              ON fr.workspace_id=ar.workspace_id AND fr.fact_revision_id=afl.fact_revision_id
            LEFT JOIN research_knowledge_fact_states fs ON fs.workspace_id=ar.workspace_id AND fs.fact_id=fr.fact_id
            WHERE ar.workspace_id=%s AND  ar.task_id=%s AND ar.artifact_revision_id=%s
            GROUP BY ar.workspace_id, ar.artifact_id, ar.revision
            """,
            (self.context.workspace_id, task_id, artifact_id),
        ).fetchone()
        if (
            row is None
            or int(row["revision"]) != int(row["max_revision"])
            or int(row["stale_fact_count"] or 0) != 0
        ):
            raise ResearchValidationError(
                "page input must be the latest current-grounded Artifact revision "
                "from this Task"
            )

    @staticmethod
    def _build_response(
        *,
        task_id: str,
        kind: str,
        run_id: str,
        output_reference: str,
        reused_build: bool,
    ) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "build_kind": kind,
            "build_run_id": run_id,
            "build_status": "succeeded",
            "output_reference": output_reference,
            "reused_build": reused_build,
        }

    def _commit_build_receipt(
        self,
        connection: Connection,
        *,
        task: dict[str, Any],
        command_id: str,
        payload_hash: str,
        kind: str,
        response: dict[str, Any],
        now: str,
    ) -> None:
        event_id = self.kernel._event(
            connection,
            task_id=str(task["task_id"]),
            goal_id=str(task["active_goal_id"]),
            event_type=f"knowledge_{kind}_built",
            payload={
                "build_run_id": response["build_run_id"],
                "output_reference": response["output_reference"],
                "reused_build": response["reused_build"],
            },
            command_id=command_id,
            owner_epoch=int(task["owner_epoch"]),
            now=now,
        )
        self.kernel._insert_receipt(
            connection,
            task_id=str(task["task_id"]),
            command_id=command_id,
            command_type=f"build_knowledge_{kind}",
            payload_hash=payload_hash,
            outcome_reference=event_id,
            response=response,
            owner_epoch=int(task["owner_epoch"]),
            now=now,
        )

    def _finalize_artifact(
        self,
        connection: Connection,
        *,
        task: dict[str, Any],
        fact_revision_ids: list[str],
        build_run_id: str,
        input_hash: str,
        now: str,
    ) -> dict[str, Any]:
        facts = []
        result_ids: set[str] = set()
        boundary_hashes: set[str] = set()
        corpus_by_evidence: dict[str, dict[str, Any]] = {}
        for fact_revision_id in fact_revision_ids:
            row = connection.execute(
                """
                SELECT fr.*, kc.result_id AS source_result_id,
                       kc.source_boundary_hash
                FROM research_fact_revisions fr
                JOIN research_grounded_facts gf ON gf.workspace_id=fr.workspace_id AND gf.fact_id=fr.fact_id
                JOIN research_knowledge_candidates kc
                  ON kc.workspace_id=fr.workspace_id AND kc.candidate_id=gf.origin_candidate_id
                WHERE fr.workspace_id=%s AND  fr.task_id=%s AND fr.fact_revision_id=%s
                """,
                (self.context.workspace_id, str(task['task_id']), fact_revision_id),
            ).fetchone()
            if row is None:
                raise ResearchValidationError("Fact revision left Task boundary")
            evidence_rows = connection.execute(
                """
                SELECT fel.evidence_id, ei.video_id, ei.source_artifact_id,
                       ei.source_version, ei.timeline_run_id
                FROM research_fact_evidence_links fel
                JOIN research_evidence_identities ei
                  ON ei.workspace_id=fel.workspace_id AND ei.evidence_id=fel.evidence_id
                WHERE fel.workspace_id=%s AND  fel.fact_revision_id=%s ORDER BY fel.ordinal
                """,
                (self.context.workspace_id, fact_revision_id),
            ).fetchall()
            citations = [str(value["evidence_id"]) for value in evidence_rows]
            for value in evidence_rows:
                evidence_id = str(value["evidence_id"])
                corpus_by_evidence[evidence_id] = {
                    "evidence_id": evidence_id,
                    "video_id": int(value["video_id"]),
                    "source_artifact_id": str(value["source_artifact_id"]),
                    "source_version": str(value["source_version"]),
                    "timeline_run_id": str(value["timeline_run_id"]),
                }
            if row["source_result_id"]:
                result_ids.add(str(row["source_result_id"]))
            boundary_hashes.add(str(row["source_boundary_hash"]))
            facts.append(
                {
                    "fact_revision_id": fact_revision_id,
                    "claim": str(row["claim_text"]),
                    "citation_ids": citations,
                }
            )
        goal = connection.execute(
            'SELECT objective FROM research_goals WHERE research_goals.workspace_id=%s AND  goal_id=%s',
            (self.context.workspace_id, str(task['active_goal_id'])),
        ).fetchone()
        topic = str(goal["objective"] if goal else "Research Topic")
        corpus_snapshot = {
            "authority": "evidence_identity_source_versions",
            "evidence": [corpus_by_evidence[key] for key in sorted(corpus_by_evidence)],
        }
        body = {
            "facts": facts,
            "source": {
                "task_id": str(task["task_id"]),
                "result_ids": sorted(result_ids),
                "boundary_hashes": sorted(boundary_hashes),
                "corpus_snapshot": corpus_snapshot,
            },
        }
        limitations = ["仅包含本次显式接受且接受时通过当前性验证的 Fact"]
        unresolved: list[str] = []
        artifact_id = _id(
            "kartifact", {"task_id": task["task_id"], "input_hash": input_hash}
        )
        revision_id = _id("kartifactrev", {"artifact_id": artifact_id, "revision": 1})
        content_hash = _hash(
            {
                "topic": topic,
                "body": body,
                "limitations": limitations,
                "unresolved": unresolved,
                "policy": KNOWLEDGE_ARTIFACT_POLICY_VERSION,
            }
        )
        connection.execute(
            'INSERT INTO research_knowledge_artifacts(workspace_id, artifact_id, workspace_schema_version, task_id, created_at) VALUES(%s, %s, %s, %s, %s)',
            (self.context.workspace_id, artifact_id, KNOWLEDGE_WORKSPACE_SCHEMA_VERSION, str(task['task_id']), _parse_iso(now)),
        )
        connection.execute(
            """
            INSERT INTO research_knowledge_artifact_revisions(workspace_id, artifact_revision_id, artifact_id, task_id, revision, parent_revision_id, supersedes_revision_id, topic, body_json, limitations_json, unresolved_json, build_policy_version, source_result_ids_json, source_boundary_hashes_json, corpus_snapshot_json, input_hash, content_hash, created_at) VALUES(%s, %s, %s, %s, 1, NULL, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (self.context.workspace_id, revision_id, artifact_id, str(task['task_id']), topic, json_field(_canonical_json(body)), json_field(_canonical_json(limitations)), json_field(_canonical_json(unresolved)), KNOWLEDGE_ARTIFACT_POLICY_VERSION, json_field(_canonical_json(sorted(result_ids))), json_field(_canonical_json(sorted(boundary_hashes))), json_field(_canonical_json(corpus_snapshot)), input_hash, content_hash, _parse_iso(now)),
        )
        for ordinal, fact_revision_id in enumerate(fact_revision_ids):
            connection.execute(
                'INSERT INTO research_artifact_fact_links(workspace_id, link_id, task_id, artifact_revision_id, fact_revision_id, ordinal, created_at) VALUES(%s, %s, %s, %s, %s, %s, %s)',
                (self.context.workspace_id, _id('artifactfact', {'artifact_revision_id': revision_id, 'fact_revision_id': fact_revision_id}), str(task['task_id']), revision_id, fact_revision_id, ordinal, _parse_iso(now)),
            )
        self.fault_injector("after_initial_artifact_revision")
        return {
            "output_reference": revision_id,
            "artifact_id": artifact_id,
            "artifact_revision_id": revision_id,
            "revision": 1,
        }

    def _finalize_topic_page(
        self,
        connection: Connection,
        *,
        task: dict[str, Any],
        artifact_revision_id: str,
        build_run_id: str,
        input_hash: str,
        now: str,
    ) -> dict[str, Any]:
        artifact = connection.execute(
            'SELECT * FROM research_knowledge_artifact_revisions WHERE research_knowledge_artifact_revisions.workspace_id=%s AND  task_id=%s AND artifact_revision_id=%s',
            (self.context.workspace_id, str(task['task_id']), artifact_revision_id),
        ).fetchone()
        if artifact is None:
            raise ResearchValidationError("Artifact revision left Task boundary")
        page_id = _id(
            "topicpage", {"task_id": task["task_id"], "input_hash": input_hash}
        )
        revision_id = _id("topicpagerev", {"page_id": page_id, "version": 1})
        slug = f"topic-{page_id.rsplit('_', 1)[-1][:16]}"
        body = {
            "facts": json_value(artifact['body_json'])["facts"],
            "limitations": json_value(artifact['limitations_json']),
            "unresolved": json_value(artifact['unresolved_json']),
        }
        content_hash = _hash(
            {
                "title": str(artifact["topic"]),
                "body": body,
                "artifact_revision_id": artifact_revision_id,
                "policy": TOPIC_PAGE_POLICY_VERSION,
            }
        )
        connection.execute(
            """
            INSERT INTO research_topic_pages(workspace_id, page_id, workspace_schema_version, task_id, slug, current_version, published_version, review_status, state_version, created_at, updated_at) VALUES(%s, %s, %s, %s, %s, 1, NULL, 'draft', 0, %s, %s)
            """,
            (self.context.workspace_id, page_id, KNOWLEDGE_WORKSPACE_SCHEMA_VERSION, str(task['task_id']), slug, _parse_iso(now), _parse_iso(now)),
        )
        connection.execute(
            """
            INSERT INTO research_topic_page_revisions(workspace_id, page_revision_id, page_id, task_id, version, parent_revision_id, supersedes_revision_id, revert_of_revision_id, revision_kind, artifact_revision_id, title, body_json, build_policy_version, input_hash, content_hash, created_at) VALUES(%s, %s, %s, %s, 1, NULL, NULL, NULL, 'initial', %s, %s, %s, %s, %s, %s, %s)
            """,
            (self.context.workspace_id, revision_id, page_id, str(task['task_id']), artifact_revision_id, str(artifact['topic']), json_field(_canonical_json(body)), TOPIC_PAGE_POLICY_VERSION, input_hash, content_hash, _parse_iso(now)),
        )
        fact_ids = [
            str(row["fact_revision_id"])
            for row in connection.execute(
                'SELECT fact_revision_id FROM research_artifact_fact_links WHERE research_artifact_fact_links.workspace_id=%s AND  artifact_revision_id=%s ORDER BY ordinal',
                (self.context.workspace_id, artifact_revision_id),
            ).fetchall()
        ]
        for ordinal, fact_revision_id in enumerate(fact_ids):
            connection.execute(
                'INSERT INTO research_topic_page_fact_links(workspace_id, link_id, task_id, page_revision_id, fact_revision_id, ordinal, created_at) VALUES(%s, %s, %s, %s, %s, %s, %s)',
                (self.context.workspace_id, _id('pagefact', {'page_revision_id': revision_id, 'fact_revision_id': fact_revision_id}), str(task['task_id']), revision_id, fact_revision_id, ordinal, _parse_iso(now)),
            )
        self.fault_injector("after_initial_topic_page_revision")
        return {
            "output_reference": revision_id,
            "page_id": page_id,
            "page_revision_id": revision_id,
            "version": 1,
            "review_status": "draft",
        }

    def review_page(
        self,
        task_id: str,
        page_id: str,
        request: ReviewTopicPageRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        request = ReviewTopicPageRequest.model_validate(request.model_dump(mode="json"))
        payload = {
            "operation": "review_topic_page",
            "task_id": task_id,
            "page_id": page_id,
            **request.model_dump(mode="json", exclude={"command_id"}),
        }
        payload_hash = _hash(payload)
        with self._command_lock, self.kernel._transaction() as connection:
            task = self.kernel._task(connection, task_id)
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}
            page = connection.execute(
                'SELECT * FROM research_topic_pages WHERE research_topic_pages.workspace_id=%s AND  page_id=%s AND task_id=%s',
                (self.context.workspace_id, page_id, task_id),
            ).fetchone()
            if page is None:
                raise ResearchNotFound(f"Topic Page 不存在: {page_id}")
            if int(page["current_version"]) != request.expected_version:
                raise ResearchConflict(
                    "stale page version: "
                    f"expected {request.expected_version}, current {page['current_version']}"
                )
            if str(page["review_status"]) != "draft":
                raise ResearchConflict(
                    f"Topic Page 已完成审查: {page['review_status']}"
                )
            revision = connection.execute(
                'SELECT * FROM research_topic_page_revisions WHERE research_topic_page_revisions.workspace_id=%s AND  page_id=%s AND version=%s',
                (self.context.workspace_id, page_id, request.expected_version),
            ).fetchone()
            if revision is None:
                raise ResearchUnsafeState("Topic Page current revision missing")
            now = _now()
            status = "published" if request.decision == "publish" else "returned"
            decision_id = _id(
                "pagereview", {"task_id": task_id, "command_id": request.command_id}
            )
            connection.execute(
                """
                INSERT INTO research_topic_page_review_decisions(workspace_id, decision_id, task_id, page_id, page_revision_id, decision_kind, reason, expected_version, command_id, principal_id, created_at) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (self.context.workspace_id, decision_id, task_id, page_id, str(revision['page_revision_id']), request.decision, request.reason, request.expected_version, request.command_id, principal_id, _parse_iso(now)),
            )
            self.fault_injector("after_topic_page_review_decision")
            connection.execute(
                "UPDATE research_topic_pages SET review_status=%s, published_version=CASE WHEN %s='published' THEN %s ELSE published_version END, state_version=state_version+1, updated_at=%s WHERE research_topic_pages.workspace_id=%s AND  page_id=%s",
                (status, status, request.expected_version, _parse_iso(now), self.context.workspace_id, page_id),
            )
            self.fault_injector("after_topic_page_review_state")
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                event_type="topic_page_reviewed",
                payload={
                    "page_id": page_id,
                    "page_revision_id": str(revision["page_revision_id"]),
                    "decision_id": decision_id,
                    "decision": request.decision,
                    "review_status": status,
                    "expected_version": request.expected_version,
                },
                command_id=request.command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            response = {
                "task_id": task_id,
                "page_id": page_id,
                "page_revision_id": str(revision["page_revision_id"]),
                "version": request.expected_version,
                "review_status": status,
            }
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="review_topic_page",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.fault_injector("after_topic_page_review_receipt")
        return {**response, "deduplicated": False}

    def get_workspace(self, task_id: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            self.kernel._task(connection, task_id)
            candidate_rows = connection.execute(
                'SELECT * FROM research_knowledge_candidates WHERE research_knowledge_candidates.workspace_id=%s AND  task_id=%s ORDER BY created_at, candidate_id',
                (self.context.workspace_id, task_id),
            ).fetchall()
            fact_rows = connection.execute(
                'SELECT * FROM research_fact_revisions WHERE research_fact_revisions.workspace_id=%s AND  task_id=%s ORDER BY created_at, fact_revision_id',
                (self.context.workspace_id, task_id),
            ).fetchall()
            artifact_rows = connection.execute(
                'SELECT * FROM research_knowledge_artifact_revisions WHERE research_knowledge_artifact_revisions.workspace_id=%s AND  task_id=%s ORDER BY created_at, artifact_revision_id',
                (self.context.workspace_id, task_id),
            ).fetchall()
            page_rows = connection.execute(
                """
                SELECT p.*, pr.page_revision_id, pr.artifact_revision_id,
                       pr.title, pr.body_json, pr.content_hash, pr.revision_kind
                FROM research_topic_pages p
                JOIN research_topic_page_revisions pr
                  ON pr.workspace_id=p.workspace_id AND pr.page_id=p.page_id AND pr.version=p.current_version
                WHERE p.workspace_id=%s AND  p.task_id=%s ORDER BY p.created_at, p.page_id
                """,
                (self.context.workspace_id, task_id),
            ).fetchall()
            build_rows = connection.execute(
                'SELECT * FROM research_knowledge_build_runs WHERE research_knowledge_build_runs.workspace_id=%s AND  task_id=%s ORDER BY created_at, build_run_id',
                (self.context.workspace_id, task_id),
            ).fetchall()
            candidates = [
                self._candidate_projection(connection, row) for row in candidate_rows
            ]
            facts = [self._fact_projection(connection, row) for row in fact_rows]
            artifacts = [self._artifact_projection(row) for row in artifact_rows]
            pages = [self._page_projection(row) for row in page_rows]
            builds = [self._build_projection(row) for row in build_rows]
        stage2 = self.lifecycle.projection(task_id)
        fact_state_by_id = {
            value["fact_id"]: value for value in stage2["fact_states"]
        }
        fact_state_by_revision = {
            fact["fact_revision_id"]: fact_state_by_id[fact["fact_id"]]
            for fact in facts
            if fact["fact_id"] in fact_state_by_id
        }
        for fact in facts:
            state = fact_state_by_id.get(fact["fact_id"])
            fact["is_current_revision"] = bool(
                state and state["current_revision_id"] == fact["fact_revision_id"]
            )
            fact["lifecycle_status"] = (
                state["lifecycle_status"] if state else "current"
            )
            fact["currentness_status"] = (
                state["currentness_status"] if state else "current"
            )
            fact["fact_state_version"] = state["state_version"] if state else 0
        for value in [*artifacts, *pages]:
            fact_ids = [
                str(fact.get("fact_revision_id") or "")
                for fact in value.get("body", {}).get("facts", [])
            ]
            affected = [
                fact_state_by_revision[fact_id]
                for fact_id in fact_ids
                if fact_id in fact_state_by_revision
                and (
                    fact_state_by_revision[fact_id]["current_revision_id"] != fact_id
                    or
                    fact_state_by_revision[fact_id]["currentness_status"] != "current"
                    or fact_state_by_revision[fact_id]["lifecycle_status"] != "current"
                )
            ]
            value["currentness_status"] = (
                "conflicted"
                if any(item["currentness_status"] == "conflicted" for item in affected)
                else "potential_conflict"
                if any(
                    item["currentness_status"] == "potential_conflict"
                    for item in affected
                )
                else "stale"
                if affected
                else "current"
            )
            value["update_available"] = bool(affected)
            value["affected_fact_ids"] = [item["fact_id"] for item in affected]
        artifact_routes = self.reuse.list(task_id)
        closeout = self.closeout.project(
            task_id,
            facts=facts,
            artifact_routes=artifact_routes,
        )
        relations_by_page = closeout["relations"]["by_page"]
        for page in pages:
            page["relations"] = relations_by_page.get(
                page["page_id"], {"items": [], "total": 0, "truncated": False}
            )
        return {
            "workspace_schema_version": KNOWLEDGE_WORKSPACE_SCHEMA_VERSION,
            "task_id": task_id,
            "authority": {
                "candidate_source": "v5-a-candidate-event_immutable",
                "fact_acceptance": "server_current_evidence_required",
                "sqlite": "metadata_lineage_review_authority",
                "filesystem": "derived_revision_hash_export_only",
                "provider": "not_exercised",
            },
            "candidates": candidates,
            "facts": facts,
            "artifacts": artifacts,
            "pages": pages,
            "build_runs": builds,
            "artifact_routes": artifact_routes,
            "closeout": closeout,
            **stage2,
            "counts": {
                "candidates": len(candidates),
                "facts": len(facts),
                "artifacts": len(artifacts),
                "pages": len(pages),
            },
        }

    def list_published_knowledge(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Thin read projection over existing published Topic Pages and lineage."""
        bounded = max(1, min(limit, 100))
        with self.db.connect() as connection:
            task_rows = connection.execute(
                """
                SELECT task_id, MAX(updated_at) AS latest_update
                FROM research_topic_pages
                WHERE research_topic_pages.workspace_id=%s AND  published_version IS NOT NULL
                GROUP BY task_id
                ORDER BY latest_update DESC, task_id
                LIMIT %s
                """,
                (self.context.workspace_id, bounded),
            ).fetchall()

        assets: list[dict[str, Any]] = []
        for task_row in task_rows:
            task_id = str(task_row["task_id"])
            workspace = self.get_workspace(task_id)
            facts_by_revision = {
                str(fact["fact_revision_id"]): fact for fact in workspace["facts"]
            }
            for page in workspace["pages"]:
                if page["published_version"] is None:
                    continue
                page_facts: list[dict[str, Any]] = []
                citations: dict[str, dict[str, Any]] = {}
                for fact_ref in page.get("body", {}).get("facts", []):
                    revision_id = str(fact_ref.get("fact_revision_id") or "")
                    fact = facts_by_revision.get(revision_id)
                    claim = str(fact_ref.get("claim") or (fact or {}).get("claim") or "")
                    if claim:
                        page_facts.append({"claim": claim, "fact_revision_id": revision_id})
                    for citation in (fact or {}).get("citations", []):
                        citations[str(citation["evidence_id"])] = citation
                assets.append(
                    {
                        "task_id": task_id,
                        "page_id": page["page_id"],
                        "title": page["title"],
                        "facts": page_facts,
                        "citations": list(citations.values()),
                        "currentness_status": page["currentness_status"],
                        "update_available": page["update_available"],
                        "updated_at": page["updated_at"],
                        "version": page["version"],
                        "published_version": page["published_version"],
                    }
                )
        assets.sort(key=lambda value: (value["updated_at"], value["page_id"]), reverse=True)
        return assets[:bounded]

    def submit_feedback(
        self,
        task_id: str,
        request: SubmitKnowledgeFeedbackRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        self._sync_lifecycle_fault_injector()
        return self.closeout.submit_feedback(
            task_id, request, principal_id=principal_id
        )

    def assess_artifact_route(
        self, task_id: str, request: AssessArtifactRouteRequest
    ) -> dict[str, Any]:
        self._sync_lifecycle_fault_injector()
        return self.reuse.assess(task_id, request)

    def proceed_artifact_route(
        self,
        task_id: str,
        route_id: str,
        request: ProceedArtifactRouteRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        self._sync_lifecycle_fault_injector()
        return self.reuse.proceed(
            task_id,
            route_id,
            request,
            principal_id=principal_id,
        )

    def get_artifact_route(self, task_id: str, route_id: str) -> dict[str, Any]:
        return self.reuse.get(task_id, route_id)

    def create_personal_workspace_record(
        self,
        task_id: str,
        request: CreateWorkspaceRecordRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        self._sync_lifecycle_fault_injector()
        return self.personal_workspace.create(
            task_id,
            request,
            principal_id=principal_id,
        )

    def decide_personal_workspace_record(
        self,
        task_id: str,
        record_id: str,
        request: DecideWorkspaceRecordRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        self._sync_lifecycle_fault_injector()
        return self.personal_workspace.decide(
            task_id,
            record_id,
            request,
            principal_id=principal_id,
        )

    def get_personal_workspace(
        self,
        task_id: str,
        *,
        record_kind: str | None = None,
        status: str | None = None,
        personalization_enabled: bool = True,
        principal_id: str | None = None,
        routing_enabled: bool = False,
        current_explicit_path: str | None = None,
        allow_provider_answer: bool = False,
        allow_high_cost_or_durable: bool = False,
        allow_manual_asr: bool = False,
        asr_video_id: int | None = None,
        assistance_enabled: bool = False,
        baseline_snapshot_id: int | None = None,
        current_snapshot_id: int | None = None,
        journey_enabled: bool = False,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        complete_workspace = self.personal_workspace.get_workspace(
            task_id,
            personalization_enabled=personalization_enabled,
            principal_id=principal_id,
        )
        workspace = complete_workspace
        if record_kind is not None or status is not None:
            workspace = self.personal_workspace.get_workspace(
                task_id,
                record_kind=record_kind,
                status=status,
                personalization_enabled=personalization_enabled,
                principal_id=principal_id,
            )
        if (
            principal_id is None
            and not routing_enabled
            and not assistance_enabled
            and not journey_enabled
        ):
            return workspace
        recommendation = self.route_recommendation.project(
            task_id,
            principal_id=principal_id,
            enabled=routing_enabled,
            current_explicit_path=current_explicit_path,
            allow_provider_answer=allow_provider_answer,
            allow_high_cost_or_durable=allow_high_cost_or_durable,
            allow_manual_asr=allow_manual_asr,
            asr_video_id=asr_video_id,
        )
        applied_revision_id = (
            recommendation["preference"]["record_revision_id"]
            if recommendation["status"] == "recommended"
            and recommendation["preference"] is not None
            and (
                "confirmed_default_path_recommended"
                in recommendation["reason_codes"]
                or "exact_video_manual_asr_prerequisite"
                in recommendation["reason_codes"]
            )
            else None
        )
        for record in workspace["records"]:
            record["route_recommendation_effect"] = (
                record["record_revision_id"] == applied_revision_id
            )
        workspace["route_recommendation"] = recommendation
        assistance = self.knowledge_assistance.project(
            task_id,
            principal_id=principal_id,
            records=complete_workspace["records"],
            enabled=assistance_enabled,
            baseline_snapshot_id=baseline_snapshot_id,
            current_snapshot_id=current_snapshot_id,
        )
        workspace["knowledge_assistance"] = assistance
        workspace["integrated_journey"] = self.integrated_journey.project(
            task_id,
            principal_id=principal_id,
            enabled=journey_enabled,
            personalization=workspace["personalization_context"],
            routing=recommendation,
            assistance=assistance,
        )
        workspace["authority"]["product_behavior"] = (
            "v5_c_stage1_to_stage4_behavior_plus_stage5_read_only_composition"
        )
        return workspace

    def revalidate_knowledge(
        self, task_id: str, request: RevalidateKnowledgeRequest
    ) -> dict[str, Any]:
        self._sync_lifecycle_fault_injector()
        return self.lifecycle.revalidate(task_id, request)

    def propose_fact_update(
        self,
        task_id: str,
        fact_id: str,
        request: ProposeFactUpdateRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        self._sync_lifecycle_fault_injector()
        return self.lifecycle.propose_update(
            task_id, fact_id, request, principal_id=principal_id
        )

    def review_fact_update(
        self,
        task_id: str,
        update_candidate_id: str,
        request: ReviewFactUpdateRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        self._sync_lifecycle_fault_injector()
        return self.lifecycle.review_update(
            task_id, update_candidate_id, request, principal_id=principal_id
        )

    def run_update_operation(
        self,
        task_id: str,
        operation_id: str,
        request: RunKnowledgeOperationRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        self._sync_lifecycle_fault_injector()
        return self.lifecycle.run_operation(
            task_id, operation_id, request, principal_id=principal_id
        )

    def recover_update_operations(
        self,
        task_id: str,
        request: RecoverKnowledgeOperationsRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        self._sync_lifecycle_fault_injector()
        return self.lifecycle.recover_operations(
            task_id, request, principal_id=principal_id
        )

    def resolve_update_operation(
        self,
        task_id: str,
        operation_id: str,
        request: ResolveKnowledgeOperationRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        self._sync_lifecycle_fault_injector()
        return self.lifecycle.resolve_operation(
            task_id, operation_id, request, principal_id=principal_id
        )

    def edit_topic_page(
        self,
        task_id: str,
        page_id: str,
        request: EditTopicPageRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        self._sync_lifecycle_fault_injector()
        return self.lifecycle.edit_page(
            task_id, page_id, request, principal_id=principal_id
        )

    def revert_topic_page(
        self,
        task_id: str,
        page_id: str,
        request: RevertTopicPageRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        self._sync_lifecycle_fault_injector()
        return self.lifecycle.revert_page(
            task_id, page_id, request, principal_id=principal_id
        )

    def get_topic_page_history(self, task_id: str, page_id: str) -> dict[str, Any]:
        return self.lifecycle.page_history(task_id, page_id)

    def get_topic_page_diff(
        self, task_id: str, page_id: str, from_version: int, to_version: int
    ) -> dict[str, Any]:
        return self.lifecycle.page_diff(task_id, page_id, from_version, to_version)

    def export_topic_page(
        self,
        task_id: str,
        request: ExportTopicPageRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        if principal_id is not None and principal_id != self.context.user_id:
            raise ResearchForbidden("principal does not match trusted resource context")
        self._sync_lifecycle_fault_injector()
        return self.lifecycle.export_page(task_id, request, principal_id=principal_id)

    def _candidate_projection(
        self, connection: Connection, row: dict[str, Any]
    ) -> dict[str, Any]:
        evidence = []
        for evidence_use_id in _json_list(row["evidence_use_ids_json"]):
            identity = connection.execute(
                """
                SELECT eu.evidence_use_id, ei.*
                FROM research_evidence_uses eu
                JOIN research_evidence_identities ei
                  ON ei.workspace_id=eu.workspace_id AND ei.evidence_id=eu.evidence_id
                WHERE eu.workspace_id=%s AND  eu.task_id=%s AND eu.attempt_id=%s AND eu.evidence_use_id=%s
                """,
                (self.context.workspace_id, str(row['task_id']), str(row['attempt_id']), str(evidence_use_id)),
            ).fetchone()
            if identity is None:
                evidence.append(
                    {
                        "evidence_use_id": str(evidence_use_id),
                        "current_outcome": "invalid",
                        "reason_code": "candidate_evidence_lineage_invalid",
                    }
                )
                continue
            current = self.authority.observe(identity)
            video = self.db.get_video(int(identity["video_id"])) or {}
            evidence.append(
                {
                    "evidence_id": str(identity["evidence_id"]),
                    "evidence_use_id": str(evidence_use_id),
                    "current_outcome": current.outcome,
                    "reason_code": current.reason_code,
                    "title": str(
                        current.span.title
                        if current.span
                        else video.get("title") or ""
                    ),
                    "quote": str(
                        current.span.quote_text
                        if current.span
                        else identity["quote_preview"]
                    ),
                    "jump_url": current.span.jump_url if current.span else None,
                    "transcript_href": (
                        f"/videos/{int(identity['video_id'])}/transcript"
                        if video.get("transcript_path")
                        else f"/media/{int(identity['video_id'])}/raw-subtitle"
                    ),
                }
            )
        return {
            "candidate_id": str(row["candidate_id"]),
            "parent_candidate_id": (
                str(row["parent_candidate_id"]) if row["parent_candidate_id"] else None
            ),
            "claim": str(row["claim_text"]),
            "citation_ids": _json_list(row["citation_ids_json"]),
            "evidence_use_ids": _json_list(row["evidence_use_ids_json"]),
            "status": str(row["status"]),
            "state_version": int(row["state_version"]),
            "evidence": evidence,
            "source": {
                "event_id": str(row["source_event_id"]),
                "delta_snapshot_id": str(row["source_delta_snapshot_id"]),
                "candidate_kind": str(row["candidate_kind"]),
                "boundary_hash": str(row["source_boundary_hash"]),
                "delta_hash": str(row["source_delta_hash"]),
                "item_hash": str(row["source_item_hash"]),
                "provisional_artifact_id": str(row["provisional_artifact_id"]),
            },
            "created_at": iso_time(row['created_at'], timespec="microseconds"),
        }

    def _fact_projection(
        self, connection: Connection, row: dict[str, Any]
    ) -> dict[str, Any]:
        links = connection.execute(
            """
            SELECT fel.*, ei.*, ev.outcome AS accepted_outcome,
                   ev.reason_code AS accepted_reason_code,
                   ev.observed_source_version AS accepted_observed_source_version
            FROM research_fact_evidence_links fel
            JOIN research_evidence_identities ei ON ei.workspace_id=fel.workspace_id AND ei.evidence_id=fel.evidence_id
            JOIN research_evidence_validations ev
              ON ev.workspace_id=fel.workspace_id AND ev.observation_id=fel.validation_observation_id
            WHERE fel.workspace_id=%s AND  fel.fact_revision_id=%s ORDER BY fel.ordinal
            """,
            (self.context.workspace_id, str(row['fact_revision_id'])),
        ).fetchall()
        citations = []
        for link in links:
            current = self.authority.observe(link)
            video = self.db.get_video(int(link["video_id"])) or {}
            span = current.span
            citations.append(
                {
                    "evidence_id": str(link["evidence_id"]),
                    "evidence_use_id": str(link["evidence_use_id"]),
                    "validation_observation_id": str(
                        link["validation_observation_id"]
                    ),
                    "accepted_outcome": str(link["accepted_outcome"]),
                    "current_outcome": current.outcome,
                    "current_reason_code": current.reason_code,
                    "video_id": int(link["video_id"]),
                    "title": str(span.title if span else video.get("title") or ""),
                    "start_time": float(link["start_time"]),
                    "end_time": float(link["end_time"]),
                    "quote": str(span.quote_text if span else link["quote_preview"]),
                    "jump_url": span.jump_url if span else None,
                    "transcript_href": (
                        f"/videos/{int(link['video_id'])}/transcript"
                        if video.get("transcript_path")
                        else f"/media/{int(link['video_id'])}/raw-subtitle"
                    ),
                    "source_version": str(link["source_version"]),
                }
            )
        return {
            "fact_id": str(row["fact_id"]),
            "fact_revision_id": str(row["fact_revision_id"]),
            "revision": int(row["revision"]),
            "origin_candidate_id": str(row["origin_candidate_id"]),
            "claim": str(row["claim_text"]),
            "verification_status": str(row["verification_status"]),
            "content_hash": str(row["content_hash"]),
            "citations": citations,
            "created_at": iso_time(row['created_at'], timespec="microseconds"),
        }

    @staticmethod
    def _artifact_projection(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "artifact_id": str(row["artifact_id"]),
            "artifact_revision_id": str(row["artifact_revision_id"]),
            "revision": int(row["revision"]),
            "topic": str(row["topic"]),
            "body": json_value(row['body_json']),
            "limitations": json_value(row['limitations_json']),
            "unresolved": json_value(row['unresolved_json']),
            "source": {
                "result_ids": json_value(row['source_result_ids_json']),
                "boundary_hashes": json_value(row['source_boundary_hashes_json']),
                "corpus_snapshot": json_value(row['corpus_snapshot_json']),
            },
            "content_hash": str(row["content_hash"]),
            "created_at": iso_time(row['created_at'], timespec="microseconds"),
        }

    @staticmethod
    def _page_projection(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "page_id": str(row["page_id"]),
            "page_revision_id": str(row["page_revision_id"]),
            "version": int(row["current_version"]),
            "slug": str(row["slug"]),
            "title": str(row["title"]),
            "body": json_value(row['body_json']),
            "artifact_revision_id": str(row["artifact_revision_id"]),
            "review_status": str(row["review_status"]),
            "published_version": (
                int(row["published_version"]) if row["published_version"] else None
            ),
            "revision_kind": str(row["revision_kind"]),
            "state_version": int(row["state_version"]),
            "content_hash": str(row["content_hash"]),
            "created_at": iso_time(row['created_at'], timespec="microseconds"),
            "updated_at": iso_time(row['updated_at'], timespec="microseconds"),
        }

    @staticmethod
    def _build_projection(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "build_run_id": str(row["build_run_id"]),
            "build_kind": str(row["build_kind"]),
            "status": str(row["status"]),
            "attempt_count": int(row["attempt_count"]),
            "input_hash": str(row["input_hash"]),
            "output_reference": (
                str(row["output_reference"]) if row["output_reference"] else None
            ),
            "created_at": iso_time(row['created_at'], timespec="microseconds"),
            "updated_at": iso_time(row['updated_at'], timespec="microseconds"),
            "completed_at": iso_time(row['completed_at'], timespec="microseconds") if row["completed_at"] else None,
        }
