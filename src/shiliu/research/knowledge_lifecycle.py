from __future__ import annotations

import difflib
import hashlib
import json
import os
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from shiliu.db import Database
from shiliu.research.errors import (
    ResearchConflict,
    ResearchNotFound,
    ResearchUnsafeState,
    ResearchValidationError,
)
from shiliu.research.inner_evidence import PersistentEvidenceAuthority
from shiliu.research.knowledge_contracts import (
    EditTopicPageRequest,
    ExportTopicPageRequest,
    ProposeFactUpdateRequest,
    RecoverKnowledgeOperationsRequest,
    ResolveKnowledgeOperationRequest,
    RevalidateKnowledgeRequest,
    ReviewFactUpdateRequest,
    RevertTopicPageRequest,
    RunKnowledgeOperationRequest,
)
from shiliu.research.schema import (
    KNOWLEDGE_ARTIFACT_POLICY_VERSION,
    KNOWLEDGE_EXPORT_POLICY_VERSION,
    KNOWLEDGE_REVALIDATION_POLICY_VERSION,
    KNOWLEDGE_UPDATE_POLICY_VERSION,
    KNOWLEDGE_WORKSPACE_SCHEMA_VERSION,
    TOPIC_PAGE_POLICY_VERSION,
)
from shiliu.research.service import ResearchTaskService


FaultInjector = Callable[[str], None]


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _id(prefix: str, value: object) -> str:
    return f"{prefix}_{_hash(value)[:32]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _future(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(
        timespec="microseconds"
    )


def _json_list(value: object) -> list[Any]:
    decoded = json.loads(str(value or "[]"))
    if not isinstance(decoded, list):
        raise ResearchUnsafeState("persisted JSON list is invalid")
    return decoded


def _json_dict(value: object) -> dict[str, Any]:
    decoded = json.loads(str(value or "{}"))
    if not isinstance(decoded, dict):
        raise ResearchUnsafeState("persisted JSON object is invalid")
    return decoded


def _scope_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Unknown overlaps conservatively; explicit disjoint scalar scopes do not."""
    if not left or not right:
        return True
    shared = set(left).intersection(right)
    if not shared:
        return True
    return all(left[key] == right[key] for key in shared)


class ResearchKnowledgeLifecycleService:
    """V5-B Stage 2 SQLite-owned lifecycle, refresh, and derived export path."""

    def __init__(
        self,
        db: Database,
        *,
        kernel: ResearchTaskService,
        export_root: Path,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self.db = db
        self.kernel = kernel
        self.authority = PersistentEvidenceAuthority(db)
        self.export_root = export_root
        self.fault_injector = fault_injector or (lambda _point: None)
        self._command_lock = threading.RLock()

    def ensure_stage1_heads(self, connection: sqlite3.Connection, task_id: str) -> None:
        now = _now()
        rows = connection.execute(
            """
            SELECT gf.fact_id, fr.fact_revision_id
            FROM research_grounded_facts gf
            JOIN research_fact_revisions fr ON fr.fact_id=gf.fact_id
            WHERE gf.task_id=?
              AND fr.revision=(
                  SELECT MAX(fr2.revision) FROM research_fact_revisions fr2
                  WHERE fr2.fact_id=gf.fact_id
              )
            """,
            (task_id,),
        ).fetchall()
        for row in rows:
            connection.execute(
                """
                INSERT OR IGNORE INTO research_knowledge_fact_states(
                    fact_id, task_id, current_revision_id, lifecycle_status,
                    currentness_status, superseded_by_revision_id,
                    latest_observation_set_id, state_version, updated_at
                ) VALUES(?, ?, ?, 'current', 'current', NULL, NULL, 0, ?)
                """,
                (str(row["fact_id"]), task_id, str(row["fact_revision_id"]), now),
            )

    def revalidate(
        self, task_id: str, request: RevalidateKnowledgeRequest
    ) -> dict[str, Any]:
        request = RevalidateKnowledgeRequest.model_validate(
            request.model_dump(mode="json")
        )
        payload = {
            "operation": "revalidate_knowledge",
            "task_id": task_id,
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
            self.ensure_stage1_heads(connection, task_id)
            if request.fact_revision_ids:
                placeholders = ",".join("?" for _ in request.fact_revision_ids)
                revisions = connection.execute(
                    f"""
                    SELECT fr.*, fs.state_version AS fact_state_version
                    FROM research_fact_revisions fr
                    JOIN research_knowledge_fact_states fs
                      ON fs.fact_id=fr.fact_id AND fs.current_revision_id=fr.fact_revision_id
                    WHERE fr.task_id=? AND fr.fact_revision_id IN ({placeholders})
                    ORDER BY fr.fact_revision_id
                    """,
                    (task_id, *request.fact_revision_ids),
                ).fetchall()
                if len(revisions) != len(request.fact_revision_ids):
                    raise ResearchValidationError(
                        "revalidation target must be current Fact revisions in one Task"
                    )
            else:
                revisions = connection.execute(
                    """
                    SELECT fr.*, fs.state_version AS fact_state_version
                    FROM research_knowledge_fact_states fs
                    JOIN research_fact_revisions fr
                      ON fr.fact_revision_id=fs.current_revision_id
                    WHERE fs.task_id=? AND fs.lifecycle_status='current'
                    ORDER BY fr.fact_revision_id
                    """,
                    (task_id,),
                ).fetchall()
            now = _now()
            observation_set_id = _id(
                "revalset", {"task_id": task_id, "command_id": request.command_id}
            )
            facts: list[dict[str, Any]] = []
            for revision in revisions:
                outcomes = self._observe_fact_revision(
                    connection,
                    task=task,
                    revision=revision,
                    observation_set_id=observation_set_id,
                    trigger=request.trigger,
                    input_hash=payload_hash,
                    now=now,
                )
                currentness = (
                    "current"
                    if outcomes and all(value["outcome"] == "current" for value in outcomes)
                    else "stale"
                )
                connection.execute(
                    """
                    UPDATE research_knowledge_fact_states
                    SET currentness_status=?, latest_observation_set_id=?,
                        state_version=state_version+1, updated_at=?
                    WHERE fact_id=? AND current_revision_id=?
                    """,
                    (
                        currentness,
                        observation_set_id,
                        now,
                        str(revision["fact_id"]),
                        str(revision["fact_revision_id"]),
                    ),
                )
                affected = self._affected_lineage(
                    connection, str(revision["fact_revision_id"])
                )
                update_candidate_id = None
                if currentness == "stale":
                    update_candidate_id = self._create_revalidation_candidate(
                        connection,
                        revision=revision,
                        observation_set_id=observation_set_id,
                        affected=affected,
                        now=now,
                    )
                else:
                    connection.execute(
                        """
                        UPDATE research_knowledge_update_candidates
                        SET status='superseded', state_version=state_version+1,
                            updated_at=?
                        WHERE task_id=? AND source_fact_revision_id=?
                          AND candidate_kind='source_rebind'
                          AND status='needs_revalidation'
                        """,
                        (now, task_id, str(revision["fact_revision_id"])),
                    )
                facts.append(
                    {
                        "fact_id": str(revision["fact_id"]),
                        "fact_revision_id": str(revision["fact_revision_id"]),
                        "currentness": currentness,
                        "outcomes": outcomes,
                        "affected": affected,
                        "update_candidate_id": update_candidate_id,
                    }
                )
            self.fault_injector("after_stage2_revalidation_observations")
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                event_type="knowledge_revalidated",
                payload={
                    "observation_set_id": observation_set_id,
                    "fact_count": len(facts),
                    "facts": facts,
                },
                command_id=request.command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            response = {
                "task_id": task_id,
                "observation_set_id": observation_set_id,
                "facts": facts,
            }
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="revalidate_knowledge",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.fault_injector("after_stage2_revalidation_receipt")
        return {**response, "deduplicated": False}

    def _observe_fact_revision(
        self,
        connection: sqlite3.Connection,
        *,
        task: sqlite3.Row,
        revision: sqlite3.Row,
        observation_set_id: str,
        trigger: str,
        input_hash: str,
        now: str,
    ) -> list[dict[str, Any]]:
        links = connection.execute(
            """
            SELECT fel.*, eu.goal_id, eu.attempt_id,
                   eu.originating_checkpoint_id AS checkpoint_id,
                   eu.owner_epoch, ei.*
            FROM research_fact_evidence_links fel
            JOIN research_evidence_uses eu ON eu.evidence_use_id=fel.evidence_use_id
            JOIN research_evidence_identities ei ON ei.evidence_id=fel.evidence_id
            WHERE fel.fact_revision_id=? ORDER BY fel.ordinal
            """,
            (str(revision["fact_revision_id"]),),
        ).fetchall()
        outcomes: list[dict[str, Any]] = []
        for link in links:
            observed = self.authority.observe(link)
            validation_id = _id(
                "revalidation",
                {
                    "observation_set_id": observation_set_id,
                    "evidence_use_id": link["evidence_use_id"],
                },
            )
            connection.execute(
                """
                INSERT INTO research_evidence_validations(
                    observation_id, evidence_use_id, evidence_id, task_id,
                    goal_id, attempt_id, checkpoint_id,
                    validation_policy_version, authority_mode,
                    expected_source_version, observed_source_version,
                    outcome, reason_code, owner_epoch, observed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'live_current_exact_replay',
                         ?, ?, ?, ?, ?, ?)
                """,
                (
                    validation_id,
                    str(link["evidence_use_id"]),
                    str(link["evidence_id"]),
                    str(task["task_id"]),
                    str(link["goal_id"]),
                    str(link["attempt_id"]),
                    str(link["checkpoint_id"]) if link["checkpoint_id"] else None,
                    KNOWLEDGE_REVALIDATION_POLICY_VERSION,
                    observed.expected_source_version,
                    observed.observed_source_version,
                    observed.outcome,
                    observed.reason_code,
                    int(link["owner_epoch"]),
                    now,
                ),
            )
            observation_id = _id(
                "knowledgeobservation",
                {
                    "observation_set_id": observation_set_id,
                    "evidence_use_id": link["evidence_use_id"],
                },
            )
            connection.execute(
                """
                INSERT INTO research_knowledge_revalidation_observations(
                    observation_id, observation_set_id, task_id,
                    fact_revision_id, evidence_id, evidence_use_id,
                    validation_observation_id, trigger_kind,
                    expected_source_version, observed_source_version,
                    outcome, reason_code, policy_version, input_hash, observed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    observation_set_id,
                    str(task["task_id"]),
                    str(revision["fact_revision_id"]),
                    str(link["evidence_id"]),
                    str(link["evidence_use_id"]),
                    validation_id,
                    trigger,
                    observed.expected_source_version,
                    observed.observed_source_version,
                    observed.outcome,
                    observed.reason_code,
                    KNOWLEDGE_REVALIDATION_POLICY_VERSION,
                    input_hash,
                    now,
                ),
            )
            outcomes.append(
                {
                    "evidence_id": str(link["evidence_id"]),
                    "evidence_use_id": str(link["evidence_use_id"]),
                    "outcome": observed.outcome,
                    "reason_code": observed.reason_code,
                    "expected_source_version": observed.expected_source_version,
                    "observed_source_version": observed.observed_source_version,
                }
            )
        if not outcomes:
            outcomes.append(
                {
                    "outcome": "invalid",
                    "reason_code": "fact_has_no_evidence_links",
                    "expected_source_version": "",
                    "observed_source_version": None,
                }
            )
        return outcomes

    def _affected_lineage(
        self, connection: sqlite3.Connection, fact_revision_id: str
    ) -> dict[str, list[str]]:
        artifact_ids = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT DISTINCT ar.artifact_id
                FROM research_artifact_fact_links afl
                JOIN research_knowledge_artifact_revisions ar
                  ON ar.artifact_revision_id=afl.artifact_revision_id
                WHERE afl.fact_revision_id=? ORDER BY ar.artifact_id
                """,
                (fact_revision_id,),
            ).fetchall()
        ]
        page_ids = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT DISTINCT pr.page_id
                FROM research_topic_page_fact_links pfl
                JOIN research_topic_page_revisions pr
                  ON pr.page_revision_id=pfl.page_revision_id
                WHERE pfl.fact_revision_id=? ORDER BY pr.page_id
                """,
                (fact_revision_id,),
            ).fetchall()
        ]
        return {"artifact_ids": artifact_ids, "page_ids": page_ids}

    def _create_revalidation_candidate(
        self,
        connection: sqlite3.Connection,
        *,
        revision: sqlite3.Row,
        observation_set_id: str,
        affected: dict[str, list[str]],
        now: str,
    ) -> str:
        existing = connection.execute(
            """
            SELECT update_candidate_id
            FROM research_knowledge_update_candidates
            WHERE task_id=? AND source_fact_revision_id=?
              AND candidate_kind='source_rebind'
              AND status IN ('pending_review', 'needs_revalidation')
            ORDER BY created_at LIMIT 1
            """,
            (str(revision["task_id"]), str(revision["fact_revision_id"])),
        ).fetchone()
        if existing is not None:
            return str(existing["update_candidate_id"])
        candidate_id = _id(
            "kupdate",
            {
                "kind": "source_rebind",
                "fact_revision_id": revision["fact_revision_id"],
                "observation_set_id": observation_set_id,
            },
        )
        use_ids = [
            str(row[0])
            for row in connection.execute(
                "SELECT evidence_use_id FROM research_fact_evidence_links "
                "WHERE fact_revision_id=? ORDER BY ordinal",
                (str(revision["fact_revision_id"]),),
            ).fetchall()
        ]
        connection.execute(
            """
            INSERT OR IGNORE INTO research_knowledge_update_candidates(
                update_candidate_id, task_id, fact_id,
                source_fact_revision_id, related_fact_revision_id,
                source_observation_set_id, candidate_kind, proposed_claim,
                temporal_scope_json, viewpoint_scope_json,
                evidence_use_ids_json, affected_artifact_ids_json,
                affected_page_ids_json, validator_status, status,
                parent_candidate_id, state_version, created_at, updated_at
            ) VALUES(?, ?, ?, ?, NULL, ?, 'source_rebind', ?, ?, ?, ?, ?, ?,
                     'needs_revalidation', 'needs_revalidation', NULL, 0, ?, ?)
            """,
            (
                candidate_id,
                str(revision["task_id"]),
                str(revision["fact_id"]),
                str(revision["fact_revision_id"]),
                observation_set_id,
                str(revision["claim_text"]),
                str(revision["temporal_scope_json"]),
                str(revision["viewpoint_scope_json"]),
                _canonical_json(use_ids),
                _canonical_json(affected["artifact_ids"]),
                _canonical_json(affected["page_ids"]),
                now,
                now,
            ),
        )
        return candidate_id

    def propose_update(
        self,
        task_id: str,
        fact_id: str,
        request: ProposeFactUpdateRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        request = ProposeFactUpdateRequest.model_validate(
            request.model_dump(mode="json")
        )
        payload = {
            "operation": "propose_fact_update",
            "task_id": task_id,
            "fact_id": fact_id,
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
            self.ensure_stage1_heads(connection, task_id)
            state, revision = self._fact_head(connection, task_id, fact_id)
            if int(state["state_version"]) != request.expected_fact_state_version:
                raise ResearchConflict(
                    "stale Fact state: "
                    f"expected {request.expected_fact_state_version}, "
                    f"current {state['state_version']}"
                )
            if str(state["lifecycle_status"]) != "current":
                raise ResearchConflict(
                    f"Fact lifecycle is already {state['lifecycle_status']}"
                )
            related = None
            if request.related_fact_revision_id:
                related = connection.execute(
                    "SELECT * FROM research_fact_revisions "
                    "WHERE task_id=? AND fact_revision_id=?",
                    (task_id, request.related_fact_revision_id),
                ).fetchone()
                if related is None:
                    raise ResearchValidationError(
                        "related Fact revision left Task boundary"
                    )
                if (
                    str(related["fact_revision_id"])
                    == str(revision["fact_revision_id"])
                    or str(related["fact_id"]) == fact_id
                ):
                    raise ResearchValidationError(
                        "conflict requires a distinct current Fact family"
                    )
            use_ids = request.evidence_use_ids or [
                str(row[0])
                for row in connection.execute(
                    "SELECT evidence_use_id FROM research_fact_evidence_links "
                    "WHERE fact_revision_id=? ORDER BY ordinal",
                    (str(revision["fact_revision_id"]),),
                ).fetchall()
            ]
            temporal = request.temporal_scope or _json_dict(
                revision["temporal_scope_json"]
            )
            viewpoint = request.viewpoint_scope or _json_dict(
                revision["viewpoint_scope_json"]
            )
            eligible = request.kind == "retire"
            if request.kind in {"user_correction", "supersede"}:
                eligible = self._claim_is_current_grounded(
                    connection,
                    task_id=task_id,
                    claim=str(request.proposed_claim),
                    evidence_use_ids=use_ids,
                )
            elif request.kind == "potential_conflict":
                assert related is not None
                related_state = connection.execute(
                    "SELECT * FROM research_knowledge_fact_states "
                    "WHERE fact_id=? AND current_revision_id=?",
                    (str(related["fact_id"]), str(related["fact_revision_id"])),
                ).fetchone()
                eligible = bool(
                    related_state
                    and str(state["currentness_status"]) == "current"
                    and str(related_state["currentness_status"]) == "current"
                    and _scope_overlap(
                        temporal, _json_dict(related["temporal_scope_json"])
                    )
                    and _scope_overlap(
                        viewpoint, _json_dict(related["viewpoint_scope_json"])
                    )
                )
            validator_status = "eligible" if eligible else "needs_revalidation"
            status = "pending_review" if eligible else "needs_revalidation"
            affected = self._affected_lineage(
                connection, str(revision["fact_revision_id"])
            )
            candidate_id = _id(
                "kupdate", {"task_id": task_id, "command_id": request.command_id}
            )
            now = _now()
            connection.execute(
                """
                INSERT INTO research_knowledge_update_candidates(
                    update_candidate_id, task_id, fact_id,
                    source_fact_revision_id, related_fact_revision_id,
                    source_observation_set_id, candidate_kind, proposed_claim,
                    temporal_scope_json, viewpoint_scope_json,
                    evidence_use_ids_json, affected_artifact_ids_json,
                    affected_page_ids_json, validator_status, status,
                    parent_candidate_id, state_version, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                         NULL, 0, ?, ?)
                """,
                (
                    candidate_id,
                    task_id,
                    fact_id,
                    str(revision["fact_revision_id"]),
                    str(related["fact_revision_id"]) if related else None,
                    request.kind,
                    request.proposed_claim,
                    _canonical_json(temporal),
                    _canonical_json(viewpoint),
                    _canonical_json(use_ids),
                    _canonical_json(affected["artifact_ids"]),
                    _canonical_json(affected["page_ids"]),
                    validator_status,
                    status,
                    now,
                    now,
                ),
            )
            if request.kind == "potential_conflict":
                connection.execute(
                    "UPDATE research_knowledge_fact_states SET "
                    "currentness_status='potential_conflict', "
                    "state_version=state_version+1, updated_at=? WHERE fact_id=?",
                    (now, fact_id),
                )
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                event_type="knowledge_update_proposed",
                payload={
                    "update_candidate_id": candidate_id,
                    "fact_id": fact_id,
                    "kind": request.kind,
                    "validator_status": validator_status,
                    "status": status,
                    "affected": affected,
                },
                command_id=request.command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            response = {
                "task_id": task_id,
                "fact_id": fact_id,
                "update_candidate_id": candidate_id,
                "kind": request.kind,
                "validator_status": validator_status,
                "status": status,
                "affected": affected,
            }
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="propose_fact_update",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
        return {**response, "deduplicated": False}

    def _fact_head(
        self, connection: sqlite3.Connection, task_id: str, fact_id: str
    ) -> tuple[sqlite3.Row, sqlite3.Row]:
        state = connection.execute(
            "SELECT * FROM research_knowledge_fact_states "
            "WHERE task_id=? AND fact_id=?",
            (task_id, fact_id),
        ).fetchone()
        if state is None:
            raise ResearchNotFound(f"Grounded Fact 不存在: {fact_id}")
        revision = connection.execute(
            "SELECT * FROM research_fact_revisions WHERE fact_revision_id=?",
            (str(state["current_revision_id"]),),
        ).fetchone()
        if revision is None:
            raise ResearchUnsafeState("Fact current revision missing")
        return state, revision

    def _claim_is_current_grounded(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        claim: str,
        evidence_use_ids: list[str],
    ) -> bool:
        if not evidence_use_ids:
            return False
        normalized_claim = " ".join(claim.casefold().split())
        grounded = False
        for use_id in evidence_use_ids:
            row = connection.execute(
                """
                SELECT eu.*, ei.* FROM research_evidence_uses eu
                JOIN research_evidence_identities ei ON ei.evidence_id=eu.evidence_id
                WHERE eu.task_id=? AND eu.evidence_use_id=?
                """,
                (task_id, use_id),
            ).fetchone()
            if row is None:
                return False
            observed = self.authority.observe(row)
            if observed.outcome != "current" or observed.span is None:
                return False
            quote = " ".join(observed.span.quote_text.casefold().split())
            grounded = grounded or normalized_claim in quote or quote in normalized_claim
        return grounded

    def review_update(
        self,
        task_id: str,
        update_candidate_id: str,
        request: ReviewFactUpdateRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        request = ReviewFactUpdateRequest.model_validate(
            request.model_dump(mode="json")
        )
        payload = {
            "operation": "review_fact_update",
            "task_id": task_id,
            "update_candidate_id": update_candidate_id,
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
                "SELECT * FROM research_knowledge_update_candidates "
                "WHERE task_id=? AND update_candidate_id=?",
                (task_id, update_candidate_id),
            ).fetchone()
            if candidate is None:
                raise ResearchNotFound(
                    f"Knowledge Update Candidate 不存在: {update_candidate_id}"
                )
            if int(candidate["state_version"]) != request.expected_candidate_version:
                raise ResearchConflict(
                    "stale update candidate: "
                    f"expected {request.expected_candidate_version}, "
                    f"current {candidate['state_version']}"
                )
            state, source_revision = self._fact_head(
                connection, task_id, str(candidate["fact_id"])
            )
            if int(state["state_version"]) != request.expected_fact_state_version:
                raise ResearchConflict(
                    "stale Fact state: "
                    f"expected {request.expected_fact_state_version}, "
                    f"current {state['state_version']}"
                )
            if str(source_revision["fact_revision_id"]) != str(
                candidate["source_fact_revision_id"]
            ):
                raise ResearchConflict("update Candidate source Fact head is stale")
            status = str(candidate["status"])
            if status not in {"pending_review", "needs_revalidation"}:
                raise ResearchConflict(f"Update Candidate 已完成审查: {status}")
            if request.decision == "accept" and (
                status != "pending_review"
                or str(candidate["validator_status"]) != "eligible"
            ):
                raise ResearchUnsafeState(
                    "needs_revalidation update cannot be accepted without server validator"
                )
            now = _now()
            result_revision_id: str | None = None
            operation_id: str | None = None
            related_revision_id = (
                str(candidate["related_fact_revision_id"])
                if candidate["related_fact_revision_id"]
                else None
            )
            result_kind = "reject"
            resulting_status = "rejected"
            edited_candidate_id: str | None = None
            if request.decision == "edit":
                edited_candidate_id = self._edit_update_candidate(
                    connection,
                    candidate=candidate,
                    command_id=request.command_id,
                    edited_claim=str(request.edited_claim),
                    now=now,
                )
                connection.execute(
                    "UPDATE research_knowledge_update_candidates SET "
                    "status='superseded', state_version=state_version+1, updated_at=? "
                    "WHERE update_candidate_id=?",
                    (now, update_candidate_id),
                )
                result_kind = "edit"
                resulting_status = "superseded"
            elif request.decision == "reject":
                connection.execute(
                    "UPDATE research_knowledge_update_candidates SET "
                    "status='rejected', state_version=state_version+1, updated_at=? "
                    "WHERE update_candidate_id=?",
                    (now, update_candidate_id),
                )
                if str(candidate["candidate_kind"]) == "potential_conflict":
                    connection.execute(
                        "UPDATE research_knowledge_fact_states SET "
                        "currentness_status='current', state_version=state_version+1, "
                        "updated_at=? WHERE fact_id=? AND currentness_status='potential_conflict'",
                        (now, str(candidate["fact_id"])),
                    )
            else:
                kind = str(candidate["candidate_kind"])
                if kind in {"user_correction", "supersede"}:
                    result_revision_id = self._create_followup_fact_revision(
                        connection,
                        task=task,
                        candidate=candidate,
                        source_revision=source_revision,
                        command_id=request.command_id,
                        now=now,
                    )
                    result_kind = "supersede" if kind == "supersede" else "correct"
                    connection.execute(
                        """
                        UPDATE research_knowledge_fact_states
                        SET current_revision_id=?, lifecycle_status='current',
                            currentness_status='current',
                            superseded_by_revision_id=NULL,
                            state_version=state_version+1, updated_at=?
                        WHERE fact_id=? AND current_revision_id=?
                          AND state_version=?
                        """,
                        (
                            result_revision_id,
                            now,
                            str(candidate["fact_id"]),
                            str(source_revision["fact_revision_id"]),
                            request.expected_fact_state_version,
                        ),
                    )
                elif kind == "retire":
                    result_kind = "retire"
                    connection.execute(
                        """
                        UPDATE research_knowledge_fact_states
                        SET lifecycle_status='retired',
                            state_version=state_version+1, updated_at=?
                        WHERE fact_id=? AND current_revision_id=?
                          AND state_version=?
                        """,
                        (
                            now,
                            str(candidate["fact_id"]),
                            str(source_revision["fact_revision_id"]),
                            request.expected_fact_state_version,
                        ),
                    )
                elif kind == "potential_conflict":
                    result_kind = "confirm_conflict"
                    if not related_revision_id:
                        raise ResearchUnsafeState("conflict Candidate lost related revision")
                    conflict_id = _id(
                        "kconflict",
                        {
                            "task_id": task_id,
                            "command_id": request.command_id,
                        },
                    )
                    related = connection.execute(
                        "SELECT * FROM research_fact_revisions "
                        "WHERE fact_revision_id=? AND task_id=?",
                        (related_revision_id, task_id),
                    ).fetchone()
                    if related is None:
                        raise ResearchUnsafeState("related conflict revision missing")
                    related_state = connection.execute(
                        "SELECT * FROM research_knowledge_fact_states "
                        "WHERE fact_id=?",
                        (str(related["fact_id"]),),
                    ).fetchone()
                    if (
                        related_state is None
                        or str(related_state["current_revision_id"])
                        != related_revision_id
                        or str(related_state["lifecycle_status"]) != "current"
                        or str(related_state["currentness_status"]) != "current"
                    ):
                        raise ResearchConflict(
                            "related conflict Fact head/currentness changed"
                        )
                    overlap = _scope_overlap(
                        _json_dict(candidate["temporal_scope_json"]),
                        _json_dict(related["temporal_scope_json"]),
                    ) and _scope_overlap(
                        _json_dict(candidate["viewpoint_scope_json"]),
                        _json_dict(related["viewpoint_scope_json"]),
                    )
                    if not overlap:
                        raise ResearchUnsafeState(
                            "non-overlapping scope cannot be confirmed as conflict"
                        )
                    connection.execute(
                        """
                        INSERT INTO research_knowledge_conflict_observations(
                            conflict_observation_id, task_id,
                            left_fact_revision_id, right_fact_revision_id,
                            scope_overlap, resolution, update_candidate_id,
                            reason, created_at
                        ) VALUES(?, ?, ?, ?, 1, 'confirmed_conflict', ?, ?, ?)
                        """,
                        (
                            conflict_id,
                            task_id,
                            str(source_revision["fact_revision_id"]),
                            related_revision_id,
                            update_candidate_id,
                            request.reason,
                            now,
                        ),
                    )
                    connection.execute(
                        "UPDATE research_knowledge_fact_states SET "
                        "currentness_status='conflicted', "
                        "state_version=state_version+1, updated_at=? "
                        "WHERE fact_id IN (?, ?)",
                        (now, str(candidate["fact_id"]), str(related["fact_id"])),
                    )
                else:
                    raise ResearchUnsafeState(
                        f"unsupported accepted update kind: {kind}"
                    )
                connection.execute(
                    "UPDATE research_knowledge_update_candidates SET "
                    "status='accepted', state_version=state_version+1, updated_at=? "
                    "WHERE update_candidate_id=?",
                    (now, update_candidate_id),
                )
                resulting_status = "accepted"
                if kind in {"user_correction", "supersede", "retire"}:
                    operation_id = self._enqueue_refresh_operation(
                        connection,
                        task_id=task_id,
                        candidate=candidate,
                        command_id=request.command_id,
                        now=now,
                    )
            decision_id = _id(
                "klifecycledecision",
                {"task_id": task_id, "command_id": request.command_id},
            )
            connection.execute(
                """
                INSERT INTO research_knowledge_lifecycle_decisions(
                    decision_id, task_id, fact_id, update_candidate_id,
                    decision_kind, result_kind, source_revision_id,
                    result_revision_id, related_fact_revision_id, reason,
                    expected_candidate_version, expected_fact_state_version,
                    command_id, principal_id, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    task_id,
                    str(candidate["fact_id"]),
                    update_candidate_id,
                    request.decision,
                    result_kind,
                    str(source_revision["fact_revision_id"]),
                    result_revision_id,
                    related_revision_id,
                    request.reason,
                    request.expected_candidate_version,
                    request.expected_fact_state_version,
                    request.command_id,
                    principal_id,
                    now,
                ),
            )
            self.fault_injector("after_stage2_lifecycle_decision")
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                event_type="knowledge_update_reviewed",
                payload={
                    "update_candidate_id": update_candidate_id,
                    "decision_id": decision_id,
                    "decision": request.decision,
                    "result_kind": result_kind,
                    "result_revision_id": result_revision_id,
                    "operation_id": operation_id,
                    "edited_candidate_id": edited_candidate_id,
                },
                command_id=request.command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            response = {
                "task_id": task_id,
                "update_candidate_id": update_candidate_id,
                "status": resulting_status,
                "result_kind": result_kind,
                "result_revision_id": result_revision_id,
                "operation_id": operation_id,
                "edited_candidate_id": edited_candidate_id,
            }
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="review_fact_update",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.fault_injector("after_stage2_lifecycle_receipt")
        return {**response, "deduplicated": False}

    def _edit_update_candidate(
        self,
        connection: sqlite3.Connection,
        *,
        candidate: sqlite3.Row,
        command_id: str,
        edited_claim: str,
        now: str,
    ) -> str:
        child_id = _id(
            "kupdateedit",
            {
                "parent_candidate_id": candidate["update_candidate_id"],
                "command_id": command_id,
            },
        )
        connection.execute(
            """
            INSERT INTO research_knowledge_update_candidates(
                update_candidate_id, task_id, fact_id,
                source_fact_revision_id, related_fact_revision_id,
                source_observation_set_id, candidate_kind, proposed_claim,
                temporal_scope_json, viewpoint_scope_json,
                evidence_use_ids_json, affected_artifact_ids_json,
                affected_page_ids_json, validator_status, status,
                parent_candidate_id, state_version, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                     'needs_revalidation', 'needs_revalidation', ?, 0, ?, ?)
            """,
            (
                child_id,
                str(candidate["task_id"]),
                str(candidate["fact_id"]),
                str(candidate["source_fact_revision_id"]),
                str(candidate["related_fact_revision_id"])
                if candidate["related_fact_revision_id"]
                else None,
                str(candidate["source_observation_set_id"])
                if candidate["source_observation_set_id"]
                else None,
                str(candidate["candidate_kind"]),
                edited_claim,
                str(candidate["temporal_scope_json"]),
                str(candidate["viewpoint_scope_json"]),
                str(candidate["evidence_use_ids_json"]),
                str(candidate["affected_artifact_ids_json"]),
                str(candidate["affected_page_ids_json"]),
                str(candidate["update_candidate_id"]),
                now,
                now,
            ),
        )
        return child_id

    def _create_followup_fact_revision(
        self,
        connection: sqlite3.Connection,
        *,
        task: sqlite3.Row,
        candidate: sqlite3.Row,
        source_revision: sqlite3.Row,
        command_id: str,
        now: str,
    ) -> str:
        claim = str(candidate["proposed_claim"] or "").strip()
        use_ids = [str(value) for value in _json_list(candidate["evidence_use_ids_json"])]
        if not self._claim_is_current_grounded(
            connection,
            task_id=str(task["task_id"]),
            claim=claim,
            evidence_use_ids=use_ids,
        ):
            raise ResearchUnsafeState("accepted correction is no longer current-grounded")
        next_revision = int(source_revision["revision"]) + 1
        revision_id = _id(
            "factrev",
            {
                "fact_id": source_revision["fact_id"],
                "revision": next_revision,
                "command_id": command_id,
            },
        )
        content_hash = _hash(
            {
                "claim": claim,
                "temporal_scope": _json_dict(candidate["temporal_scope_json"]),
                "viewpoint_scope": _json_dict(candidate["viewpoint_scope_json"]),
                "evidence_use_ids": use_ids,
                "policy": KNOWLEDGE_UPDATE_POLICY_VERSION,
            }
        )
        connection.execute(
            """
            INSERT INTO research_fact_revisions(
                fact_revision_id, fact_id, task_id, revision,
                parent_revision_id, supersedes_revision_id,
                origin_candidate_id, claim_text, temporal_scope_json,
                viewpoint_scope_json, verification_status, content_hash, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted_current', ?, ?)
            """,
            (
                revision_id,
                str(source_revision["fact_id"]),
                str(source_revision["task_id"]),
                next_revision,
                str(source_revision["fact_revision_id"]),
                (
                    str(source_revision["fact_revision_id"])
                    if str(candidate["candidate_kind"]) == "supersede"
                    else None
                ),
                str(source_revision["origin_candidate_id"]),
                claim,
                str(candidate["temporal_scope_json"]),
                str(candidate["viewpoint_scope_json"]),
                content_hash,
                now,
            ),
        )
        for ordinal, use_id in enumerate(use_ids):
            identity = connection.execute(
                """
                SELECT eu.*, ei.* FROM research_evidence_uses eu
                JOIN research_evidence_identities ei ON ei.evidence_id=eu.evidence_id
                WHERE eu.task_id=? AND eu.evidence_use_id=?
                """,
                (str(task["task_id"]), use_id),
            ).fetchone()
            if identity is None:
                raise ResearchUnsafeState("Fact correction evidence lineage missing")
            observed = self.authority.observe(identity)
            if observed.outcome != "current":
                raise ResearchUnsafeState("Fact correction evidence became noncurrent")
            observation_id = _id(
                "kupdatevalidation",
                {"command_id": command_id, "evidence_use_id": use_id},
            )
            connection.execute(
                """
                INSERT INTO research_evidence_validations(
                    observation_id, evidence_use_id, evidence_id, task_id,
                    goal_id, attempt_id, checkpoint_id,
                    validation_policy_version, authority_mode,
                    expected_source_version, observed_source_version,
                    outcome, reason_code, owner_epoch, observed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'live_current_exact_replay',
                         ?, ?, 'current', ?, ?, ?)
                """,
                (
                    observation_id,
                    use_id,
                    str(identity["evidence_id"]),
                    str(task["task_id"]),
                    str(identity["goal_id"]),
                    str(identity["attempt_id"]),
                    str(identity["originating_checkpoint_id"])
                    if identity["originating_checkpoint_id"]
                    else None,
                    KNOWLEDGE_UPDATE_POLICY_VERSION,
                    observed.expected_source_version,
                    observed.observed_source_version,
                    observed.reason_code,
                    int(identity["owner_epoch"]),
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO research_fact_evidence_links(
                    link_id, task_id, fact_revision_id, evidence_id,
                    evidence_use_id, validation_observation_id,
                    ordinal, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _id(
                        "factevidence",
                        {"fact_revision_id": revision_id, "evidence_use_id": use_id},
                    ),
                    str(task["task_id"]),
                    revision_id,
                    str(identity["evidence_id"]),
                    use_id,
                    observation_id,
                    ordinal,
                    now,
                ),
            )
        self.fault_injector("after_stage2_fact_revision")
        return revision_id

    def _enqueue_refresh_operation(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        candidate: sqlite3.Row,
        command_id: str,
        now: str,
    ) -> str:
        fact_state = connection.execute(
            "SELECT * FROM research_knowledge_fact_states WHERE fact_id=?",
            (str(candidate["fact_id"]),),
        ).fetchone()
        if fact_state is None:
            raise ResearchUnsafeState("Fact state missing while enqueueing refresh")
        artifact_ids = [
            str(value) for value in _json_list(candidate["affected_artifact_ids_json"])
        ]
        page_ids = [
            str(value) for value in _json_list(candidate["affected_page_ids_json"])
        ]
        expected_artifacts = {
            artifact_id: int(
                connection.execute(
                    "SELECT COALESCE(MAX(revision), 0) FROM "
                    "research_knowledge_artifact_revisions WHERE artifact_id=?",
                    (artifact_id,),
                ).fetchone()[0]
            )
            for artifact_id in artifact_ids
        }
        expected_pages = {
            page_id: int(
                connection.execute(
                    "SELECT current_version FROM research_topic_pages WHERE page_id=?",
                    (page_id,),
                ).fetchone()[0]
            )
            for page_id in page_ids
        }
        expected_heads = {
            "facts": {
                str(candidate["fact_id"]): {
                    "revision_id": str(fact_state["current_revision_id"]),
                    "state_version": int(fact_state["state_version"]),
                    "lifecycle_status": str(fact_state["lifecycle_status"]),
                }
            },
            "artifacts": expected_artifacts,
            "pages": expected_pages,
        }
        input_value = {
            "policy": KNOWLEDGE_UPDATE_POLICY_VERSION,
            "update_candidate_id": str(candidate["update_candidate_id"]),
            "fact_id": str(candidate["fact_id"]),
            "artifact_ids": artifact_ids,
            "page_ids": page_ids,
        }
        input_hash = _hash(input_value)
        operation_id = _id(
            "koperation",
            {"task_id": task_id, "kind": "refresh_knowledge", "input": input_hash},
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO research_knowledge_update_operations(
                operation_id, task_id, operation_kind, target_reference,
                dedup_key, command_id, input_hash, input_json,
                expected_heads_json, status, attempt_count, max_attempts,
                error_class, error_code, error_detail, next_attempt_at,
                claimant_id, lease_until, claim_generation, output_reference,
                created_at, updated_at, finished_at
            ) VALUES(?, ?, 'refresh_knowledge', ?, ?, ?, ?, ?, ?, 'pending',
                     0, 3, NULL, NULL, NULL, NULL, NULL, NULL, 0, NULL, ?, ?, NULL)
            """,
            (
                operation_id,
                task_id,
                str(candidate["fact_id"]),
                input_hash,
                command_id,
                input_hash,
                _canonical_json(input_value),
                _canonical_json(expected_heads),
                now,
                now,
            ),
        )
        return operation_id

    def run_operation(
        self,
        task_id: str,
        operation_id: str,
        request: RunKnowledgeOperationRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        request = RunKnowledgeOperationRequest.model_validate(
            request.model_dump(mode="json")
        )
        payload = {
            "operation": "run_knowledge_operation",
            "task_id": task_id,
            "operation_id": operation_id,
            "claimant_id": request.claimant_id,
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
            operation = connection.execute(
                "SELECT * FROM research_knowledge_update_operations "
                "WHERE task_id=? AND operation_id=?",
                (task_id, operation_id),
            ).fetchone()
            if operation is None:
                raise ResearchNotFound(f"Knowledge operation 不存在: {operation_id}")
            status = str(operation["status"])
            if status == "succeeded":
                response = self._operation_projection(operation)
                self.kernel._insert_receipt(
                    connection,
                    task_id=task_id,
                    command_id=request.command_id,
                    command_type="run_knowledge_operation",
                    payload_hash=payload_hash,
                    outcome_reference=operation_id,
                    response=response,
                    owner_epoch=int(task["owner_epoch"]),
                    now=_now(),
                )
                return {**response, "deduplicated": True}
            if status not in {"pending", "retry_wait", "running"}:
                raise ResearchConflict(f"operation cannot run from {status}")
            now = _now()
            if status == "running" and operation["lease_until"]:
                if str(operation["lease_until"]) > now:
                    raise ResearchConflict("operation has an active claim")
            if int(operation["attempt_count"]) >= int(operation["max_attempts"]):
                raise ResearchConflict("operation retry budget exhausted")
            generation = int(operation["claim_generation"]) + 1
            connection.execute(
                """
                UPDATE research_knowledge_update_operations
                SET status='running', attempt_count=attempt_count+1,
                    claimant_id=?, lease_until=?, claim_generation=?,
                    error_class=NULL, error_code=NULL, error_detail=NULL,
                    next_attempt_at=NULL, updated_at=?
                WHERE operation_id=?
                """,
                (
                    request.claimant_id,
                    _future(30),
                    generation,
                    now,
                    operation_id,
                ),
            )
        self.fault_injector("after_stage2_operation_claim")
        try:
            with self._command_lock, self.kernel._transaction() as connection:
                task = self.kernel._task(connection, task_id)
                operation = connection.execute(
                    "SELECT * FROM research_knowledge_update_operations "
                    "WHERE task_id=? AND operation_id=?",
                    (task_id, operation_id),
                ).fetchone()
                if operation is None:
                    raise ResearchUnsafeState("claimed operation disappeared")
                if (
                    str(operation["status"]) != "running"
                    or str(operation["claimant_id"]) != request.claimant_id
                    or int(operation["claim_generation"]) != generation
                ):
                    raise ResearchConflict("stale operation claim")
                fence_error = self._head_fence_error(connection, operation)
                now = _now()
                if fence_error:
                    connection.execute(
                        """
                        UPDATE research_knowledge_update_operations
                        SET status='superseded', error_class='bounded_limitation',
                            error_code='stale_input_fence', error_detail=?,
                            claimant_id=NULL, lease_until=NULL,
                            updated_at=?, finished_at=?
                        WHERE operation_id=? AND claim_generation=?
                        """,
                        (fence_error, now, now, operation_id, generation),
                    )
                    response = {
                        **self._operation_projection(
                            connection.execute(
                                "SELECT * FROM research_knowledge_update_operations "
                                "WHERE operation_id=?",
                                (operation_id,),
                            ).fetchone()
                        ),
                        "fence_reason": fence_error,
                    }
                else:
                    self.fault_injector("during_stage2_operation_build")
                    if str(operation["operation_kind"]) != "refresh_knowledge":
                        raise ResearchUnsafeState(
                            "export operations use the export command"
                        )
                    outputs = self._build_refresh_outputs(
                        connection, task=task, operation=operation, now=now
                    )
                    self.fault_injector("after_stage2_operation_outputs")
                    connection.execute(
                        """
                        UPDATE research_knowledge_update_operations
                        SET status='succeeded', output_reference=?,
                            claimant_id=NULL, lease_until=NULL,
                            updated_at=?, finished_at=?
                        WHERE operation_id=? AND status='running'
                          AND claimant_id=? AND claim_generation=?
                        """,
                        (
                            _canonical_json(outputs),
                            now,
                            now,
                            operation_id,
                            request.claimant_id,
                            generation,
                        ),
                    )
                    if connection.execute("SELECT changes()").fetchone()[0] != 1:
                        raise ResearchConflict("late operation finalize rejected")
                    response = {
                        "operation_id": operation_id,
                        "status": "succeeded",
                        "attempt_count": int(operation["attempt_count"]),
                        "claim_generation": generation,
                        "outputs": outputs,
                    }
                event_id = self.kernel._event(
                    connection,
                    task_id=task_id,
                    goal_id=str(task["active_goal_id"]),
                    event_type="knowledge_operation_finished",
                    payload=response,
                    command_id=request.command_id,
                    owner_epoch=int(task["owner_epoch"]),
                    now=now,
                )
                self.kernel._insert_receipt(
                    connection,
                    task_id=task_id,
                    command_id=request.command_id,
                    command_type="run_knowledge_operation",
                    payload_hash=payload_hash,
                    outcome_reference=event_id,
                    response=response,
                    owner_epoch=int(task["owner_epoch"]),
                    now=now,
                )
                self.fault_injector("after_stage2_operation_receipt")
            return {**response, "deduplicated": False}
        except (ResearchConflict, ResearchUnsafeState, ResearchValidationError):
            raise
        except Exception as exc:
            return self._record_operation_failure(
                task_id=task_id,
                operation_id=operation_id,
                generation=generation,
                request=request,
                payload_hash=payload_hash,
                exc=exc,
                principal_id=principal_id,
            )

    def _record_operation_failure(
        self,
        *,
        task_id: str,
        operation_id: str,
        generation: int,
        request: RunKnowledgeOperationRequest,
        payload_hash: str,
        exc: Exception,
        principal_id: str,
    ) -> dict[str, Any]:
        del principal_id
        with self._command_lock, self.kernel._transaction() as connection:
            task = self.kernel._task(connection, task_id)
            operation = connection.execute(
                "SELECT * FROM research_knowledge_update_operations "
                "WHERE task_id=? AND operation_id=?",
                (task_id, operation_id),
            ).fetchone()
            if operation is None:
                raise ResearchUnsafeState("failed operation disappeared")
            if (
                str(operation["status"]) != "running"
                or int(operation["claim_generation"]) != generation
            ):
                raise ResearchConflict("failure belongs to stale operation claim")
            transient = isinstance(exc, OSError)
            attempts = int(operation["attempt_count"])
            max_attempts = int(operation["max_attempts"])
            status = (
                "retry_wait"
                if transient and attempts < max_attempts
                else "dead_letter"
                if transient
                else "needs_user"
            )
            error_class = "infrastructure_invalid" if transient else "implementation_failure"
            now = _now()
            connection.execute(
                """
                UPDATE research_knowledge_update_operations
                SET status=?, error_class=?, error_code=?, error_detail=?,
                    next_attempt_at=?, claimant_id=NULL, lease_until=NULL,
                    updated_at=?, finished_at=?
                WHERE operation_id=? AND claim_generation=?
                """,
                (
                    status,
                    error_class,
                    type(exc).__name__,
                    str(exc)[:1000],
                    _future(min(60, 2**attempts)) if status == "retry_wait" else None,
                    now,
                    now if status in {"dead_letter", "needs_user"} else None,
                    operation_id,
                    generation,
                ),
            )
            response = self._operation_projection(
                connection.execute(
                    "SELECT * FROM research_knowledge_update_operations "
                    "WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
            )
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                event_type="knowledge_operation_failed",
                payload=response,
                command_id=request.command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="run_knowledge_operation",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
        return {**response, "deduplicated": False}

    def _head_fence_error(
        self, connection: sqlite3.Connection, operation: sqlite3.Row
    ) -> str | None:
        expected = _json_dict(operation["expected_heads_json"])
        for fact_id, value in dict(expected.get("facts") or {}).items():
            row = connection.execute(
                "SELECT * FROM research_knowledge_fact_states WHERE fact_id=?",
                (fact_id,),
            ).fetchone()
            if row is None:
                return f"fact head missing: {fact_id}"
            if (
                str(row["current_revision_id"]) != str(value["revision_id"])
                or int(row["state_version"]) != int(value["state_version"])
                or str(row["lifecycle_status"]) != str(value["lifecycle_status"])
            ):
                return f"fact head changed: {fact_id}"
        for artifact_id, revision in dict(expected.get("artifacts") or {}).items():
            current = int(
                connection.execute(
                    "SELECT COALESCE(MAX(revision), 0) FROM "
                    "research_knowledge_artifact_revisions WHERE artifact_id=?",
                    (artifact_id,),
                ).fetchone()[0]
            )
            if current != int(revision):
                return f"artifact head changed: {artifact_id}"
        for page_id, version in dict(expected.get("pages") or {}).items():
            row = connection.execute(
                "SELECT current_version FROM research_topic_pages WHERE page_id=?",
                (page_id,),
            ).fetchone()
            if row is None or int(row[0]) != int(version):
                return f"page head changed: {page_id}"
        return None

    def _build_refresh_outputs(
        self,
        connection: sqlite3.Connection,
        *,
        task: sqlite3.Row,
        operation: sqlite3.Row,
        now: str,
    ) -> dict[str, Any]:
        input_value = _json_dict(operation["input_json"])
        artifact_map: dict[str, str] = {}
        artifact_outputs: list[dict[str, Any]] = []
        for artifact_id in input_value.get("artifact_ids") or []:
            old = connection.execute(
                "SELECT * FROM research_knowledge_artifact_revisions "
                "WHERE artifact_id=? ORDER BY revision DESC LIMIT 1",
                (str(artifact_id),),
            ).fetchone()
            if old is None or str(old["task_id"]) != str(task["task_id"]):
                raise ResearchUnsafeState("refresh artifact left Task boundary")
            current_fact_ids = self._current_fact_ids_for_artifact(
                connection, str(old["artifact_revision_id"])
            )
            next_revision = int(old["revision"]) + 1
            revision_id = _id(
                "kartifactrev",
                {
                    "artifact_id": artifact_id,
                    "revision": next_revision,
                    "operation_id": operation["operation_id"],
                },
            )
            facts, corpus = self._artifact_fact_body(connection, current_fact_ids)
            body = {
                "facts": facts,
                "source": {
                    "task_id": str(task["task_id"]),
                    "result_ids": _json_list(old["source_result_ids_json"]),
                    "boundary_hashes": _json_list(old["source_boundary_hashes_json"]),
                    "corpus_snapshot": corpus,
                },
            }
            limitations = _json_list(old["limitations_json"])
            unresolved = _json_list(old["unresolved_json"])
            input_hash = _hash(
                {
                    "operation_id": operation["operation_id"],
                    "artifact_id": artifact_id,
                    "revision": next_revision,
                    "facts": current_fact_ids,
                }
            )
            content_hash = _hash(
                {
                    "topic": str(old["topic"]),
                    "body": body,
                    "limitations": limitations,
                    "unresolved": unresolved,
                    "policy": KNOWLEDGE_UPDATE_POLICY_VERSION,
                }
            )
            connection.execute(
                """
                INSERT INTO research_knowledge_artifact_revisions(
                    artifact_revision_id, artifact_id, task_id, revision,
                    parent_revision_id, supersedes_revision_id, topic,
                    body_json, limitations_json, unresolved_json,
                    build_policy_version, source_result_ids_json,
                    source_boundary_hashes_json, corpus_snapshot_json,
                    input_hash, content_hash, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    str(artifact_id),
                    str(task["task_id"]),
                    next_revision,
                    str(old["artifact_revision_id"]),
                    str(old["artifact_revision_id"]),
                    str(old["topic"]),
                    _canonical_json(body),
                    _canonical_json(limitations),
                    _canonical_json(unresolved),
                    KNOWLEDGE_UPDATE_POLICY_VERSION,
                    str(old["source_result_ids_json"]),
                    str(old["source_boundary_hashes_json"]),
                    _canonical_json(corpus),
                    input_hash,
                    content_hash,
                    now,
                ),
            )
            for ordinal, fact_revision_id in enumerate(current_fact_ids):
                connection.execute(
                    "INSERT INTO research_artifact_fact_links("
                    "link_id, task_id, artifact_revision_id, fact_revision_id, ordinal, created_at"
                    ") VALUES(?, ?, ?, ?, ?, ?)",
                    (
                        _id(
                            "artifactfact",
                            {
                                "artifact_revision_id": revision_id,
                                "fact_revision_id": fact_revision_id,
                            },
                        ),
                        str(task["task_id"]),
                        revision_id,
                        fact_revision_id,
                        ordinal,
                        now,
                    ),
                )
            artifact_map[str(artifact_id)] = revision_id
            artifact_outputs.append(
                {
                    "artifact_id": str(artifact_id),
                    "artifact_revision_id": revision_id,
                    "revision": next_revision,
                }
            )
        page_outputs: list[dict[str, Any]] = []
        for page_id in input_value.get("page_ids") or []:
            page = connection.execute(
                "SELECT * FROM research_topic_pages WHERE page_id=? AND task_id=?",
                (str(page_id), str(task["task_id"])),
            ).fetchone()
            if page is None:
                raise ResearchUnsafeState("refresh Page left Task boundary")
            old = connection.execute(
                "SELECT * FROM research_topic_page_revisions "
                "WHERE page_id=? AND version=?",
                (str(page_id), int(page["current_version"])),
            ).fetchone()
            if old is None:
                raise ResearchUnsafeState("refresh Page head missing")
            old_artifact = connection.execute(
                "SELECT artifact_id FROM research_knowledge_artifact_revisions "
                "WHERE artifact_revision_id=?",
                (str(old["artifact_revision_id"]),),
            ).fetchone()
            artifact_revision_id = (
                artifact_map.get(str(old_artifact[0]))
                if old_artifact is not None
                else None
            ) or str(old["artifact_revision_id"])
            page_outputs.append(
                self._create_page_revision(
                    connection,
                    task=task,
                    page=page,
                    source=old,
                    revision_kind="refresh",
                    artifact_revision_id=artifact_revision_id,
                    title=str(old["title"]),
                    body_override=None,
                    revert_of_revision_id=None,
                    command_id=(
                        f"{operation['operation_id']}:refresh:{page['page_id']}"
                    ),
                    principal_id="stage2_refresh_worker",
                    reason="accepted Fact lifecycle refresh",
                    now=now,
                )
            )
        return {"artifacts": artifact_outputs, "pages": page_outputs}

    def _current_fact_ids_for_artifact(
        self, connection: sqlite3.Connection, artifact_revision_id: str
    ) -> list[str]:
        rows = connection.execute(
            """
            SELECT fs.current_revision_id, fs.lifecycle_status
            FROM research_artifact_fact_links afl
            JOIN research_fact_revisions old_fr
              ON old_fr.fact_revision_id=afl.fact_revision_id
            JOIN research_knowledge_fact_states fs ON fs.fact_id=old_fr.fact_id
            WHERE afl.artifact_revision_id=? ORDER BY afl.ordinal
            """,
            (artifact_revision_id,),
        ).fetchall()
        return [
            str(row["current_revision_id"])
            for row in rows
            if str(row["lifecycle_status"]) == "current"
        ]

    @staticmethod
    def _artifact_fact_body(
        connection: sqlite3.Connection, fact_revision_ids: list[str]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        corpus: dict[str, dict[str, Any]] = {}
        for fact_revision_id in fact_revision_ids:
            revision = connection.execute(
                "SELECT * FROM research_fact_revisions WHERE fact_revision_id=?",
                (fact_revision_id,),
            ).fetchone()
            if revision is None:
                raise ResearchUnsafeState("refresh Fact revision missing")
            evidence = connection.execute(
                """
                SELECT fel.evidence_id, ei.video_id, ei.source_artifact_id,
                       ei.source_version, ei.timeline_run_id
                FROM research_fact_evidence_links fel
                JOIN research_evidence_identities ei ON ei.evidence_id=fel.evidence_id
                WHERE fel.fact_revision_id=? ORDER BY fel.ordinal
                """,
                (fact_revision_id,),
            ).fetchall()
            citation_ids = [str(row["evidence_id"]) for row in evidence]
            facts.append(
                {
                    "fact_revision_id": fact_revision_id,
                    "claim": str(revision["claim_text"]),
                    "citation_ids": citation_ids,
                }
            )
            for row in evidence:
                corpus[str(row["evidence_id"])] = {
                    "evidence_id": str(row["evidence_id"]),
                    "video_id": int(row["video_id"]),
                    "source_artifact_id": str(row["source_artifact_id"]),
                    "source_version": str(row["source_version"]),
                    "timeline_run_id": str(row["timeline_run_id"]),
                }
        return facts, {
            "authority": "evidence_identity_source_versions",
            "evidence": [corpus[key] for key in sorted(corpus)],
        }

    def recover_operations(
        self,
        task_id: str,
        request: RecoverKnowledgeOperationsRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        request = RecoverKnowledgeOperationsRequest.model_validate(
            request.model_dump(mode="json")
        )
        with self.db.connect() as connection:
            self.kernel._task(connection, task_id)
            now = _now()
            rows = connection.execute(
                """
                SELECT operation_id FROM research_knowledge_update_operations
                WHERE task_id=? AND operation_kind='refresh_knowledge'
                  AND (
                    status='pending'
                    OR (status='retry_wait' AND (next_attempt_at IS NULL OR next_attempt_at<=?))
                    OR (status='running' AND lease_until IS NOT NULL AND lease_until<=?)
                  )
                ORDER BY created_at, operation_id LIMIT ?
                """,
                (task_id, now, now, request.limit),
            ).fetchall()
        outcomes = []
        for index, row in enumerate(rows):
            outcomes.append(
                self.run_operation(
                    task_id,
                    str(row["operation_id"]),
                    RunKnowledgeOperationRequest(
                        command_id=f"{request.command_id}:{index}",
                        claimant_id="stage2_recovery",
                    ),
                    principal_id=principal_id,
                )
            )
        return {"task_id": task_id, "recovered": outcomes, "count": len(outcomes)}

    def resolve_operation(
        self,
        task_id: str,
        operation_id: str,
        request: ResolveKnowledgeOperationRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        request = ResolveKnowledgeOperationRequest.model_validate(
            request.model_dump(mode="json")
        )
        payload = {
            "operation": "resolve_knowledge_operation",
            "task_id": task_id,
            "operation_id": operation_id,
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
            operation = connection.execute(
                "SELECT * FROM research_knowledge_update_operations "
                "WHERE task_id=? AND operation_id=?",
                (task_id, operation_id),
            ).fetchone()
            if operation is None:
                raise ResearchNotFound(f"Knowledge operation 不存在: {operation_id}")
            if int(operation["claim_generation"]) != request.expected_claim_generation:
                raise ResearchConflict("stale operation resolution generation")
            status = str(operation["status"])
            now = _now()
            if request.action == "retry":
                if status != "needs_user":
                    raise ResearchConflict("only needs_user operation can be resolved to retry")
                if int(operation["attempt_count"]) >= int(operation["max_attempts"]):
                    raise ResearchConflict("operation retry budget exhausted")
                resulting_status = "pending"
                finished_at = None
            else:
                if status not in {
                    "pending",
                    "retry_wait",
                    "needs_user",
                    "dead_letter",
                }:
                    raise ResearchConflict(f"operation cannot cancel from {status}")
                resulting_status = "cancelled"
                finished_at = now
            connection.execute(
                """
                UPDATE research_knowledge_update_operations
                SET status=?, error_class=NULL, error_code=NULL,
                    error_detail=NULL, next_attempt_at=NULL,
                    claimant_id=NULL, lease_until=NULL,
                    updated_at=?, finished_at=?
                WHERE operation_id=? AND claim_generation=?
                """,
                (
                    resulting_status,
                    now,
                    finished_at,
                    operation_id,
                    request.expected_claim_generation,
                ),
            )
            response = {
                "task_id": task_id,
                "operation_id": operation_id,
                "action": request.action,
                "status": resulting_status,
                "claim_generation": request.expected_claim_generation,
                "reason": request.reason,
            }
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                event_type="knowledge_operation_resolved",
                payload={**response, "principal_id": principal_id},
                command_id=request.command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="resolve_knowledge_operation",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
        return {**response, "deduplicated": False}

    def edit_page(
        self,
        task_id: str,
        page_id: str,
        request: EditTopicPageRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        request = EditTopicPageRequest.model_validate(request.model_dump(mode="json"))
        payload = {
            "operation": "edit_topic_page",
            "task_id": task_id,
            "page_id": page_id,
            **request.model_dump(mode="json", exclude={"command_id"}),
        }
        return self._page_revision_command(
            task_id=task_id,
            page_id=page_id,
            command_id=request.command_id,
            payload_hash=_hash(payload),
            expected_version=request.expected_version,
            revision_kind="edit",
            target_version=None,
            title=request.title,
            limitations=request.limitations,
            unresolved=request.unresolved,
            annotation=request.annotation,
            reason=request.reason,
            principal_id=principal_id,
        )

    def revert_page(
        self,
        task_id: str,
        page_id: str,
        request: RevertTopicPageRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        request = RevertTopicPageRequest.model_validate(
            request.model_dump(mode="json")
        )
        payload = {
            "operation": "revert_topic_page",
            "task_id": task_id,
            "page_id": page_id,
            **request.model_dump(mode="json", exclude={"command_id"}),
        }
        return self._page_revision_command(
            task_id=task_id,
            page_id=page_id,
            command_id=request.command_id,
            payload_hash=_hash(payload),
            expected_version=request.expected_version,
            revision_kind="revert",
            target_version=request.target_version,
            title=None,
            limitations=None,
            unresolved=None,
            annotation=None,
            reason=request.reason,
            principal_id=principal_id,
        )

    def _page_revision_command(
        self,
        *,
        task_id: str,
        page_id: str,
        command_id: str,
        payload_hash: str,
        expected_version: int,
        revision_kind: str,
        target_version: int | None,
        title: str | None,
        limitations: list[str] | None,
        unresolved: list[str] | None,
        annotation: str | None,
        reason: str,
        principal_id: str,
    ) -> dict[str, Any]:
        with self._command_lock, self.kernel._transaction() as connection:
            task = self.kernel._task(connection, task_id)
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}
            page = connection.execute(
                "SELECT * FROM research_topic_pages WHERE task_id=? AND page_id=?",
                (task_id, page_id),
            ).fetchone()
            if page is None:
                raise ResearchNotFound(f"Topic Page 不存在: {page_id}")
            if int(page["current_version"]) != expected_version:
                raise ResearchConflict(
                    "stale page version: "
                    f"expected {expected_version}, current {page['current_version']}"
                )
            current = connection.execute(
                "SELECT * FROM research_topic_page_revisions "
                "WHERE page_id=? AND version=?",
                (page_id, expected_version),
            ).fetchone()
            if current is None:
                raise ResearchUnsafeState("Topic Page current revision missing")
            source = current
            revert_of = None
            if revision_kind == "revert":
                source = connection.execute(
                    "SELECT * FROM research_topic_page_revisions "
                    "WHERE page_id=? AND version=?",
                    (page_id, target_version),
                ).fetchone()
                if source is None:
                    raise ResearchValidationError(
                        f"revert target version does not exist: {target_version}"
                    )
                revert_of = str(source["page_revision_id"])
            body = _json_dict(source["body_json"])
            if revision_kind == "edit":
                if limitations is not None:
                    body["limitations"] = [str(value) for value in limitations]
                if unresolved is not None:
                    body["unresolved"] = [str(value) for value in unresolved]
                if annotation is not None:
                    body["user_annotation"] = annotation
            now = _now()
            response = self._create_page_revision(
                connection,
                task=task,
                page=page,
                source=current,
                revision_kind=revision_kind,
                artifact_revision_id=str(source["artifact_revision_id"]),
                title=title or str(source["title"]),
                body_override=body,
                revert_of_revision_id=revert_of,
                command_id=command_id,
                principal_id=principal_id,
                reason=reason,
                now=now,
            )
            self.fault_injector("after_stage2_page_revision")
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                event_type="topic_page_revision_created",
                payload=response,
                command_id=command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type=f"{revision_kind}_topic_page",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.fault_injector("after_stage2_page_revision_receipt")
        return {**response, "deduplicated": False}

    def _create_page_revision(
        self,
        connection: sqlite3.Connection,
        *,
        task: sqlite3.Row,
        page: sqlite3.Row,
        source: sqlite3.Row,
        revision_kind: str,
        artifact_revision_id: str,
        title: str,
        body_override: dict[str, Any] | None,
        revert_of_revision_id: str | None,
        command_id: str,
        principal_id: str,
        reason: str,
        now: str,
    ) -> dict[str, Any]:
        next_version = int(page["current_version"]) + 1
        if body_override is None:
            artifact = connection.execute(
                "SELECT * FROM research_knowledge_artifact_revisions "
                "WHERE task_id=? AND artifact_revision_id=?",
                (str(task["task_id"]), artifact_revision_id),
            ).fetchone()
            if artifact is None:
                raise ResearchUnsafeState("Page refresh Artifact revision missing")
            old_body = _json_dict(source["body_json"])
            body = {
                "facts": _json_dict(artifact["body_json"]).get("facts", []),
                "limitations": old_body.get(
                    "limitations", _json_list(artifact["limitations_json"])
                ),
                "unresolved": old_body.get(
                    "unresolved", _json_list(artifact["unresolved_json"])
                ),
            }
            if old_body.get("user_annotation"):
                body["user_annotation"] = old_body["user_annotation"]
        else:
            body = body_override
        input_hash = _hash(
            {
                "page_id": page["page_id"],
                "version": next_version,
                "command_id": command_id,
                "kind": revision_kind,
            }
        )
        content_hash = _hash(
            {
                "title": title,
                "body": body,
                "artifact_revision_id": artifact_revision_id,
                "policy": KNOWLEDGE_UPDATE_POLICY_VERSION,
            }
        )
        revision_id = _id(
            "topicpagerev",
            {"page_id": page["page_id"], "version": next_version},
        )
        connection.execute(
            """
            INSERT INTO research_topic_page_revisions(
                page_revision_id, page_id, task_id, version,
                parent_revision_id, supersedes_revision_id,
                revert_of_revision_id, revision_kind,
                artifact_revision_id, title, body_json,
                build_policy_version, input_hash, content_hash, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision_id,
                str(page["page_id"]),
                str(task["task_id"]),
                next_version,
                str(source["page_revision_id"]),
                str(source["page_revision_id"]),
                revert_of_revision_id,
                revision_kind,
                artifact_revision_id,
                title,
                _canonical_json(body),
                (
                    KNOWLEDGE_UPDATE_POLICY_VERSION
                    if revision_kind != "initial"
                    else TOPIC_PAGE_POLICY_VERSION
                ),
                input_hash,
                content_hash,
                now,
            ),
        )
        fact_ids = [
            str(row[0])
            for row in connection.execute(
                "SELECT fact_revision_id FROM research_artifact_fact_links "
                "WHERE artifact_revision_id=? ORDER BY ordinal",
                (artifact_revision_id,),
            ).fetchall()
        ]
        if not fact_ids and revision_kind in {"edit", "revert"}:
            fact_ids = [
                str(row[0])
                for row in connection.execute(
                    "SELECT fact_revision_id FROM research_topic_page_fact_links "
                    "WHERE page_revision_id=? ORDER BY ordinal",
                    (str(source["page_revision_id"]),),
                ).fetchall()
            ]
        for ordinal, fact_revision_id in enumerate(fact_ids):
            connection.execute(
                "INSERT INTO research_topic_page_fact_links("
                "link_id, task_id, page_revision_id, fact_revision_id, ordinal, created_at"
                ") VALUES(?, ?, ?, ?, ?, ?)",
                (
                    _id(
                        "pagefact",
                        {
                            "page_revision_id": revision_id,
                            "fact_revision_id": fact_revision_id,
                        },
                    ),
                    str(task["task_id"]),
                    revision_id,
                    fact_revision_id,
                    ordinal,
                    now,
                ),
            )
        decision_id = _id(
            "pagerevisiondecision",
            {"task_id": task["task_id"], "command_id": command_id},
        )
        connection.execute(
            """
            INSERT INTO research_topic_page_revision_decisions(
                decision_id, task_id, page_id, source_revision_id,
                result_revision_id, decision_kind, reason,
                command_id, principal_id, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                str(task["task_id"]),
                str(page["page_id"]),
                str(source["page_revision_id"]),
                revision_id,
                revision_kind,
                reason,
                command_id,
                principal_id,
                now,
            ),
        )
        connection.execute(
            """
            UPDATE research_topic_pages
            SET current_version=?, review_status='draft',
                state_version=state_version+1, updated_at=?
            WHERE page_id=? AND current_version=?
            """,
            (
                next_version,
                now,
                str(page["page_id"]),
                int(page["current_version"]),
            ),
        )
        if connection.execute("SELECT changes()").fetchone()[0] != 1:
            raise ResearchConflict("stale Page head while creating revision")
        return {
            "task_id": str(task["task_id"]),
            "page_id": str(page["page_id"]),
            "page_revision_id": revision_id,
            "version": next_version,
            "revision_kind": revision_kind,
            "review_status": "draft",
            "published_version": (
                int(page["published_version"]) if page["published_version"] else None
            ),
            "content_hash": content_hash,
        }

    def page_history(self, task_id: str, page_id: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            self.kernel._task(connection, task_id)
            page = connection.execute(
                "SELECT * FROM research_topic_pages WHERE task_id=? AND page_id=?",
                (task_id, page_id),
            ).fetchone()
            if page is None:
                raise ResearchNotFound(f"Topic Page 不存在: {page_id}")
            revisions = connection.execute(
                "SELECT * FROM research_topic_page_revisions "
                "WHERE page_id=? ORDER BY version",
                (page_id,),
            ).fetchall()
            review_rows = connection.execute(
                "SELECT * FROM research_topic_page_review_decisions "
                "WHERE page_id=? ORDER BY created_at, decision_id",
                (page_id,),
            ).fetchall()
        return {
            "page_id": page_id,
            "current_version": int(page["current_version"]),
            "published_version": (
                int(page["published_version"]) if page["published_version"] else None
            ),
            "review_status": str(page["review_status"]),
            "revisions": [self._page_revision_projection(row) for row in revisions],
            "reviews": [
                {
                    "decision_id": str(row["decision_id"]),
                    "page_revision_id": str(row["page_revision_id"]),
                    "decision": str(row["decision_kind"]),
                    "reason": str(row["reason"]),
                    "created_at": str(row["created_at"]),
                }
                for row in review_rows
            ],
        }

    def page_diff(
        self, task_id: str, page_id: str, from_version: int, to_version: int
    ) -> dict[str, Any]:
        history = self.page_history(task_id, page_id)
        by_version = {value["version"]: value for value in history["revisions"]}
        if from_version not in by_version or to_version not in by_version:
            raise ResearchValidationError("Page diff version does not exist")
        left = json.dumps(
            {
                "title": by_version[from_version]["title"],
                "body": by_version[from_version]["body"],
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).splitlines()
        right = json.dumps(
            {
                "title": by_version[to_version]["title"],
                "body": by_version[to_version]["body"],
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).splitlines()
        lines = list(
            difflib.unified_diff(
                left,
                right,
                fromfile=f"page-v{from_version}",
                tofile=f"page-v{to_version}",
                lineterm="",
            )
        )
        return {
            "page_id": page_id,
            "from_version": from_version,
            "to_version": to_version,
            "format": "unified_json",
            "lines": lines,
        }

    def export_page(
        self,
        task_id: str,
        request: ExportTopicPageRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        del principal_id
        request = ExportTopicPageRequest.model_validate(
            request.model_dump(mode="json")
        )
        payload = {
            "operation": "export_topic_page",
            "task_id": task_id,
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
            revision = connection.execute(
                """
                SELECT pr.*, p.slug FROM research_topic_page_revisions pr
                JOIN research_topic_pages p ON p.page_id=pr.page_id
                WHERE pr.task_id=? AND pr.page_revision_id=?
                """,
                (task_id, request.page_revision_id),
            ).fetchone()
            if revision is None:
                raise ResearchNotFound(
                    f"Topic Page revision 不存在: {request.page_revision_id}"
                )
            dedup_key = _hash(
                {
                    "page_revision_id": request.page_revision_id,
                    "content_hash": str(revision["content_hash"]),
                    "format": request.export_format,
                }
            )
            operation_id = _id(
                "koperation",
                {"task_id": task_id, "kind": "export_page", "dedup": dedup_key},
            )
            now = _now()
            connection.execute(
                """
                INSERT OR IGNORE INTO research_knowledge_update_operations(
                    operation_id, task_id, operation_kind, target_reference,
                    dedup_key, command_id, input_hash, input_json,
                    expected_heads_json, status, attempt_count, max_attempts,
                    error_class, error_code, error_detail, next_attempt_at,
                    claimant_id, lease_until, claim_generation, output_reference,
                    created_at, updated_at, finished_at
                ) VALUES(?, ?, 'export_page', ?, ?, ?, ?, ?, '{}', 'pending',
                         0, 3, NULL, NULL, NULL, NULL, NULL, NULL, 0, NULL, ?, ?, NULL)
                """,
                (
                    operation_id,
                    task_id,
                    request.page_revision_id,
                    dedup_key,
                    request.command_id,
                    payload_hash,
                    _canonical_json(payload),
                    now,
                    now,
                ),
            )
            operation = connection.execute(
                "SELECT * FROM research_knowledge_update_operations "
                "WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if operation is None:
                raise ResearchUnsafeState("export operation reservation missing")
            if str(operation["input_hash"]) != payload_hash:
                raise ResearchConflict("export dedup payload mismatch")
            if str(operation["status"]) == "succeeded":
                export = connection.execute(
                    "SELECT * FROM research_knowledge_exports WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                if export is None:
                    raise ResearchUnsafeState("successful export record missing")
                response = self._export_projection(export, operation)
                self.kernel._insert_receipt(
                    connection,
                    task_id=task_id,
                    command_id=request.command_id,
                    command_type="export_topic_page",
                    payload_hash=payload_hash,
                    outcome_reference=operation_id,
                    response=response,
                    owner_epoch=int(task["owner_epoch"]),
                    now=now,
                )
                return {**response, "deduplicated": True}
            if str(operation["status"]) not in {"pending", "retry_wait"}:
                raise ResearchConflict(
                    f"export cannot run from {operation['status']}"
                )
            if int(operation["attempt_count"]) >= int(operation["max_attempts"]):
                raise ResearchConflict("export retry budget exhausted")
            generation = int(operation["claim_generation"]) + 1
            connection.execute(
                """
                UPDATE research_knowledge_update_operations
                SET status='running', attempt_count=attempt_count+1,
                    claimant_id='stage2_export', lease_until=?,
                    claim_generation=?, error_class=NULL, error_code=NULL,
                    error_detail=NULL, next_attempt_at=NULL, updated_at=?
                WHERE operation_id=?
                """,
                (_future(30), generation, now, operation_id),
            )
            page_payload = {
                "page_id": str(revision["page_id"]),
                "page_revision_id": str(revision["page_revision_id"]),
                "version": int(revision["version"]),
                "slug": str(revision["slug"]),
                "title": str(revision["title"]),
                "body": _json_dict(revision["body_json"]),
                "artifact_revision_id": str(revision["artifact_revision_id"]),
                "content_hash": str(revision["content_hash"]),
            }
        suffix = "md" if request.export_format == "markdown" else "json"
        relative = (
            Path(task_id)
            / request.page_revision_id
            / f"{revision['content_hash']}.{suffix}"
        )
        output_path = self.export_root / relative
        try:
            self.fault_injector("during_stage2_export")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            content = (
                self._page_markdown(page_payload)
                if request.export_format == "markdown"
                else json.dumps(page_payload, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n"
            )
            temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
            with temp_path.open("w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, output_path)
        except OSError as exc:
            with self._command_lock, self.kernel._transaction() as connection:
                operation = connection.execute(
                    "SELECT * FROM research_knowledge_update_operations "
                    "WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                if operation is None:
                    raise ResearchUnsafeState("failed export operation missing")
                attempts = int(operation["attempt_count"])
                status = (
                    "retry_wait"
                    if attempts < int(operation["max_attempts"])
                    else "dead_letter"
                )
                now = _now()
                connection.execute(
                    """
                    UPDATE research_knowledge_update_operations
                    SET status=?, error_class='infrastructure_invalid',
                        error_code=?, error_detail=?, next_attempt_at=?,
                        claimant_id=NULL, lease_until=NULL, updated_at=?, finished_at=?
                    WHERE operation_id=? AND claim_generation=?
                    """,
                    (
                        status,
                        type(exc).__name__,
                        str(exc)[:1000],
                        _future(min(60, 2**attempts))
                        if status == "retry_wait"
                        else None,
                        now,
                        now if status == "dead_letter" else None,
                        operation_id,
                        generation,
                    ),
                )
                failed = self._operation_projection(
                    connection.execute(
                        "SELECT * FROM research_knowledge_update_operations "
                        "WHERE operation_id=?",
                        (operation_id,),
                    ).fetchone()
                )
            return {**failed, "deduplicated": False}
        with self._command_lock, self.kernel._transaction() as connection:
            task = self.kernel._task(connection, task_id)
            current_revision = connection.execute(
                "SELECT * FROM research_topic_page_revisions "
                "WHERE task_id=? AND page_revision_id=?",
                (task_id, request.page_revision_id),
            ).fetchone()
            operation = connection.execute(
                "SELECT * FROM research_knowledge_update_operations "
                "WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if (
                current_revision is None
                or str(current_revision["content_hash"])
                != str(page_payload["content_hash"])
                or operation is None
                or str(operation["status"]) != "running"
                or int(operation["claim_generation"]) != generation
            ):
                raise ResearchConflict("export finalize fence rejected")
            now = _now()
            export_id = _id(
                "kexport",
                {
                    "page_revision_id": request.page_revision_id,
                    "format": request.export_format,
                    "content_hash": page_payload["content_hash"],
                },
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO research_knowledge_exports(
                    export_id, task_id, page_revision_id, export_format,
                    content_hash, relative_path, operation_id, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    export_id,
                    task_id,
                    request.page_revision_id,
                    request.export_format,
                    str(page_payload["content_hash"]),
                    str(relative),
                    operation_id,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE research_knowledge_update_operations
                SET status='succeeded', output_reference=?, claimant_id=NULL,
                    lease_until=NULL, updated_at=?, finished_at=?
                WHERE operation_id=? AND status='running'
                  AND claim_generation=?
                """,
                (str(relative), now, now, operation_id, generation),
            )
            export = connection.execute(
                "SELECT * FROM research_knowledge_exports WHERE export_id=?",
                (export_id,),
            ).fetchone()
            operation = connection.execute(
                "SELECT * FROM research_knowledge_update_operations "
                "WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if export is None or operation is None:
                raise ResearchUnsafeState("export finalize projection missing")
            response = self._export_projection(export, operation)
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                event_type="topic_page_exported",
                payload=response,
                command_id=request.command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="export_topic_page",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
        return {**response, "deduplicated": False}

    @staticmethod
    def _page_markdown(page: dict[str, Any]) -> str:
        lines = [
            f"# {page['title']}",
            "",
            f"Revision: `{page['page_revision_id']}`",
            f"Content SHA-256: `{page['content_hash']}`",
            "",
        ]
        for fact in page["body"].get("facts") or []:
            lines.extend(
                [
                    f"- {fact.get('claim', '')}",
                    f"  - Fact revision: `{fact.get('fact_revision_id', '')}`",
                    f"  - Evidence: {', '.join(fact.get('citation_ids') or [])}",
                ]
            )
        limitations = page["body"].get("limitations") or []
        if limitations:
            lines.extend(["", "## Limitations", ""])
            lines.extend(f"- {value}" for value in limitations)
        unresolved = page["body"].get("unresolved") or []
        if unresolved:
            lines.extend(["", "## Unresolved", ""])
            lines.extend(f"- {value}" for value in unresolved)
        if page["body"].get("user_annotation"):
            lines.extend(
                ["", "## User annotation", "", str(page["body"]["user_annotation"])]
            )
        return "\n".join(lines).rstrip() + "\n"

    def projection(self, task_id: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            self.kernel._task(connection, task_id)
            self.ensure_stage1_heads(connection, task_id)
            connection.commit()
            states = connection.execute(
                "SELECT * FROM research_knowledge_fact_states "
                "WHERE task_id=? ORDER BY fact_id",
                (task_id,),
            ).fetchall()
            candidates = connection.execute(
                "SELECT * FROM research_knowledge_update_candidates "
                "WHERE task_id=? ORDER BY created_at, update_candidate_id",
                (task_id,),
            ).fetchall()
            operations = connection.execute(
                "SELECT * FROM research_knowledge_update_operations "
                "WHERE task_id=? ORDER BY created_at, operation_id",
                (task_id,),
            ).fetchall()
            exports = connection.execute(
                "SELECT * FROM research_knowledge_exports "
                "WHERE task_id=? ORDER BY created_at, export_id",
                (task_id,),
            ).fetchall()
        return {
            "fact_states": [self._fact_state_projection(row) for row in states],
            "update_candidates": [
                self._update_candidate_projection(row) for row in candidates
            ],
            "operations": [self._operation_projection(row) for row in operations],
            "exports": [
                {
                    "export_id": str(row["export_id"]),
                    "page_revision_id": str(row["page_revision_id"]),
                    "format": str(row["export_format"]),
                    "content_hash": str(row["content_hash"]),
                    "relative_path": str(row["relative_path"]),
                    "operation_id": str(row["operation_id"]),
                    "created_at": str(row["created_at"]),
                }
                for row in exports
            ],
        }

    @staticmethod
    def _fact_state_projection(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "fact_id": str(row["fact_id"]),
            "current_revision_id": str(row["current_revision_id"]),
            "lifecycle_status": str(row["lifecycle_status"]),
            "currentness_status": str(row["currentness_status"]),
            "superseded_by_revision_id": (
                str(row["superseded_by_revision_id"])
                if row["superseded_by_revision_id"]
                else None
            ),
            "latest_observation_set_id": (
                str(row["latest_observation_set_id"])
                if row["latest_observation_set_id"]
                else None
            ),
            "state_version": int(row["state_version"]),
            "updated_at": str(row["updated_at"]),
        }

    @staticmethod
    def _update_candidate_projection(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "update_candidate_id": str(row["update_candidate_id"]),
            "fact_id": str(row["fact_id"]),
            "source_fact_revision_id": str(row["source_fact_revision_id"]),
            "related_fact_revision_id": (
                str(row["related_fact_revision_id"])
                if row["related_fact_revision_id"]
                else None
            ),
            "kind": str(row["candidate_kind"]),
            "proposed_claim": (
                str(row["proposed_claim"]) if row["proposed_claim"] else None
            ),
            "temporal_scope": _json_dict(row["temporal_scope_json"]),
            "viewpoint_scope": _json_dict(row["viewpoint_scope_json"]),
            "evidence_use_ids": _json_list(row["evidence_use_ids_json"]),
            "affected": {
                "artifact_ids": _json_list(row["affected_artifact_ids_json"]),
                "page_ids": _json_list(row["affected_page_ids_json"]),
            },
            "validator_status": str(row["validator_status"]),
            "status": str(row["status"]),
            "parent_candidate_id": (
                str(row["parent_candidate_id"]) if row["parent_candidate_id"] else None
            ),
            "state_version": int(row["state_version"]),
            "created_at": str(row["created_at"]),
        }

    @staticmethod
    def _operation_projection(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "operation_id": str(row["operation_id"]),
            "kind": str(row["operation_kind"]),
            "target_reference": str(row["target_reference"]),
            "status": str(row["status"]),
            "attempt_count": int(row["attempt_count"]),
            "max_attempts": int(row["max_attempts"]),
            "claim_generation": int(row["claim_generation"]),
            "error_class": str(row["error_class"]) if row["error_class"] else None,
            "error_code": str(row["error_code"]) if row["error_code"] else None,
            "error_detail": str(row["error_detail"]) if row["error_detail"] else None,
            "next_attempt_at": (
                str(row["next_attempt_at"]) if row["next_attempt_at"] else None
            ),
            "output_reference": (
                str(row["output_reference"]) if row["output_reference"] else None
            ),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    @staticmethod
    def _page_revision_projection(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "page_revision_id": str(row["page_revision_id"]),
            "version": int(row["version"]),
            "parent_revision_id": (
                str(row["parent_revision_id"]) if row["parent_revision_id"] else None
            ),
            "revert_of_revision_id": (
                str(row["revert_of_revision_id"])
                if row["revert_of_revision_id"]
                else None
            ),
            "revision_kind": str(row["revision_kind"]),
            "artifact_revision_id": str(row["artifact_revision_id"]),
            "title": str(row["title"]),
            "body": _json_dict(row["body_json"]),
            "content_hash": str(row["content_hash"]),
            "created_at": str(row["created_at"]),
        }

    @staticmethod
    def _export_projection(
        export: sqlite3.Row, operation: sqlite3.Row
    ) -> dict[str, Any]:
        return {
            "export_id": str(export["export_id"]),
            "operation_id": str(operation["operation_id"]),
            "status": str(operation["status"]),
            "page_revision_id": str(export["page_revision_id"]),
            "format": str(export["export_format"]),
            "content_hash": str(export["content_hash"]),
            "relative_path": str(export["relative_path"]),
            "attempt_count": int(operation["attempt_count"]),
        }
