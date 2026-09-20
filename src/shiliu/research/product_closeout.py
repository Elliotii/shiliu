from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from shiliu.db import Database
from shiliu.research.errors import ResearchNotFound, ResearchValidationError
from shiliu.research.knowledge_contracts import SubmitKnowledgeFeedbackRequest
from shiliu.research.service import ResearchTaskService


FaultInjector = Callable[[str], None]
MAX_RELATIONS_PER_PAGE = 8
MAX_FEEDBACK_ITEMS = 20


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _json_object(value: object) -> dict[str, Any]:
    decoded = json.loads(str(value or "{}"))
    return decoded if isinstance(decoded, dict) else {}


class ResearchProductCloseoutService:
    """Stage 5 composition only; existing records remain the sole authorities."""

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

    def project(
        self,
        task_id: str,
        *,
        facts: list[dict[str, Any]],
        artifact_routes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        fact_by_revision = {
            str(fact["fact_revision_id"]): fact for fact in facts
        }
        with self.db.connect() as connection:
            self.kernel._task(connection, task_id)
            relations = self._relations(connection, task_id, fact_by_revision)
            observability = self._observability(connection, task_id)
        return {
            "policy_version": "v5b-stage5-product-closeout-v1",
            "relations": relations,
            "observability": observability,
            "product_paths": self._product_paths(artifact_routes),
            "authority": {
                "relations": "derived_navigation_only",
                "feedback": "research_event_plus_command_receipt",
                "observability": "derived_existing_records_only",
                "citation": "l1_evidence_only",
                "automatic_mutation": False,
                "workspace_product_interference": False,
            },
        }

    def submit_feedback(
        self,
        task_id: str,
        request: SubmitKnowledgeFeedbackRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        request = SubmitKnowledgeFeedbackRequest.model_validate(
            request.model_dump(mode="json")
        )
        request_value = request.model_dump(mode="json", exclude_none=True)
        payload_hash = _hash(
            {
                "operation": "submit_v5b_product_feedback",
                "task_id": task_id,
                "principal_id": principal_id,
                **request_value,
            }
        )
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

            target = self._feedback_target(
                connection,
                task_id=task_id,
                target_kind=request.target_kind,
                target_id=request.target_id,
            )
            if request.expected_hash != target["expected_hash"]:
                raise ResearchValidationError(
                    "feedback expected_hash does not match the exact immutable target"
                )

            now = _now()
            event_payload = {
                "target_kind": request.target_kind,
                "target_id": request.target_id,
                "target_hash": target["expected_hash"],
                "decision": request.decision,
                "reason_code": request.reason_code,
                "note": request.note,
                "principal_id": principal_id,
                "authority": "advisory_feedback_only",
                "automatic_action": False,
            }
            if request.candidate_preference is not None:
                event_payload["candidate_preference"] = (
                    request.candidate_preference.model_dump(mode="json")
                )
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=(
                    str(task["active_goal_id"])
                    if task["active_goal_id"] is not None
                    else None
                ),
                event_type="v5b_product_feedback_recorded",
                payload=event_payload,
                command_id=request.command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.fault_injector("after_stage5_feedback_event")
            response = {
                "event_id": event_id,
                "task_id": task_id,
                "target_kind": request.target_kind,
                "target_id": request.target_id,
                "target_hash": target["expected_hash"],
                "decision": request.decision,
                "reason_code": request.reason_code,
                "advisory_only": True,
                "automatic_action": False,
            }
            if request.candidate_preference is not None:
                response["candidate_preference"] = (
                    request.candidate_preference.model_dump(mode="json")
                )
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="v5b_product_feedback",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.fault_injector("after_stage5_feedback_receipt")
        return {**response, "deduplicated": False}

    @staticmethod
    def _feedback_target(
        connection: sqlite3.Connection,
        *,
        task_id: str,
        target_kind: str,
        target_id: str,
    ) -> dict[str, str]:
        if target_kind == "topic_page_revision":
            row = connection.execute(
                "SELECT page_revision_id, content_hash FROM research_topic_page_revisions "
                "WHERE task_id=? AND page_revision_id=?",
                (task_id, target_id),
            ).fetchone()
            expected_column = "content_hash"
        else:
            row = connection.execute(
                "SELECT record_id, expected_authority_hash FROM research_artifact_routes "
                "WHERE task_id=? AND record_id=?",
                (task_id, target_id),
            ).fetchone()
            expected_column = "expected_authority_hash"
        if row is None:
            raise ResearchNotFound(
                f"feedback target does not exist in Task: {target_kind}/{target_id}"
            )
        return {"expected_hash": str(row[expected_column])}

    def _relations(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        fact_by_revision: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        rows = connection.execute(
            """
            SELECT p.page_id, p.slug, p.published_version,
                   pr.page_revision_id, pr.title, pr.content_hash,
                   pfl.fact_revision_id, fr.fact_id, fr.claim_text,
                   fs.current_revision_id, fs.lifecycle_status, fs.currentness_status
            FROM research_topic_pages p
            JOIN research_topic_page_revisions pr
              ON pr.page_id=p.page_id AND pr.version=p.published_version
            JOIN research_topic_page_fact_links pfl
              ON pfl.page_revision_id=pr.page_revision_id
            JOIN research_fact_revisions fr
              ON fr.fact_revision_id=pfl.fact_revision_id
            LEFT JOIN research_knowledge_fact_states fs ON fs.fact_id=fr.fact_id
            WHERE p.task_id=? AND p.published_version IS NOT NULL
            ORDER BY p.page_id, pfl.ordinal, pfl.fact_revision_id
            """,
            (task_id,),
        ).fetchall()
        pages: dict[str, dict[str, Any]] = {}
        fact_pages: dict[str, list[str]] = defaultdict(list)
        eligible: dict[str, dict[str, Any]] = {}
        for row in rows:
            page_id = str(row["page_id"])
            pages.setdefault(
                page_id,
                {
                    "page_id": page_id,
                    "page_revision_id": str(row["page_revision_id"]),
                    "title": str(row["title"]),
                    "slug": str(row["slug"]),
                    "content_hash": str(row["content_hash"]),
                },
            )
            fact_revision_id = str(row["fact_revision_id"])
            projection = fact_by_revision.get(fact_revision_id)
            state_current_head = (
                row["current_revision_id"] is not None
                and str(row["current_revision_id"]) == fact_revision_id
                and str(row["lifecycle_status"]) == "current"
            )
            citations = list((projection or {}).get("citations") or [])
            citation_current = bool(citations) and all(
                citation.get("current_outcome") == "current" for citation in citations
            )
            if not (projection and state_current_head and citation_current):
                continue
            eligible[fact_revision_id] = {
                "fact_id": str(row["fact_id"]),
                "fact_revision_id": fact_revision_id,
                "claim": str(row["claim_text"]),
                "content_hash": str(projection["content_hash"]),
                "citations": citations,
                "currentness_status": str(row["currentness_status"]),
            }
            fact_pages[fact_revision_id].append(page_id)

        candidates: dict[tuple[str, str, str], dict[str, Any]] = {}
        for fact_revision_id, page_ids in sorted(fact_pages.items()):
            if eligible[fact_revision_id]["currentness_status"] != "current":
                continue
            unique_pages = sorted(set(page_ids))
            for index, left in enumerate(unique_pages):
                for right in unique_pages[index + 1 :]:
                    self._relation_candidate(
                        candidates,
                        pages=pages,
                        source_page_id=left,
                        target_page_id=right,
                        kind="shared_current_fact",
                        supporting_facts=[eligible[fact_revision_id]],
                        reason="Both published revisions cite the same current FactRevision.",
                    )

        conflict_rows = connection.execute(
            """
            SELECT left_fact_revision_id, right_fact_revision_id,
                   conflict_observation_id, reason
            FROM research_knowledge_conflict_observations
            WHERE task_id=? AND resolution='confirmed_conflict'
            ORDER BY created_at, conflict_observation_id
            """,
            (task_id,),
        ).fetchall()
        for conflict in conflict_rows:
            left_fact = str(conflict["left_fact_revision_id"])
            right_fact = str(conflict["right_fact_revision_id"])
            if left_fact not in eligible or right_fact not in eligible:
                continue
            if {
                eligible[left_fact]["currentness_status"],
                eligible[right_fact]["currentness_status"],
            } - {"current", "conflicted"}:
                continue
            for left_page in sorted(set(fact_pages.get(left_fact, []))):
                for right_page in sorted(set(fact_pages.get(right_fact, []))):
                    if left_page == right_page:
                        continue
                    self._relation_candidate(
                        candidates,
                        pages=pages,
                        source_page_id=min(left_page, right_page),
                        target_page_id=max(left_page, right_page),
                        kind="confirmed_conflict",
                        supporting_facts=[eligible[left_fact], eligible[right_fact]],
                        reason=(
                            str(conflict["reason"])
                            or "Current facts have a user-confirmed conflict."
                        ),
                    )

        by_page: dict[str, list[dict[str, Any]]] = {page_id: [] for page_id in pages}
        for relation in sorted(
            candidates.values(),
            key=lambda item: (
                item["kind"],
                item["source"]["page_id"],
                item["target"]["page_id"],
                item["relation_id"],
            ),
        ):
            by_page[relation["source"]["page_id"]].append(relation)
            reverse = {
                **relation,
                "source": relation["target"],
                "target": relation["source"],
                "backlink": True,
            }
            by_page[relation["target"]["page_id"]].append(reverse)

        total = len(candidates)
        return {
            "relation_types": ["shared_current_fact", "confirmed_conflict"],
            "total": total,
            "by_page": {
                page_id: {
                    "items": values[:MAX_RELATIONS_PER_PAGE],
                    "total": len(values),
                    "truncated": len(values) > MAX_RELATIONS_PER_PAGE,
                }
                for page_id, values in sorted(by_page.items())
            },
            "navigation_only": True,
            "max_per_page": MAX_RELATIONS_PER_PAGE,
        }

    @staticmethod
    def _relation_candidate(
        candidates: dict[tuple[str, str, str], dict[str, Any]],
        *,
        pages: dict[str, dict[str, Any]],
        source_page_id: str,
        target_page_id: str,
        kind: str,
        supporting_facts: list[dict[str, Any]],
        reason: str,
    ) -> None:
        key = (kind, source_page_id, target_page_id)
        if key in candidates:
            supporting_facts = [
                *candidates[key]["supporting_facts"], *supporting_facts
            ]
        facts_by_id = {
            item["fact_revision_id"]: item for item in supporting_facts
        }
        facts = [facts_by_id[value] for value in sorted(facts_by_id)]
        relation_hash = _hash(
            {
                "kind": kind,
                "source": pages[source_page_id]["page_revision_id"],
                "target": pages[target_page_id]["page_revision_id"],
                "facts": [item["fact_revision_id"] for item in facts],
            }
        )
        candidates[key] = {
            "relation_id": f"relation_{relation_hash[:32]}",
            "relation_hash": relation_hash,
            "kind": kind,
            "source": pages[source_page_id],
            "target": pages[target_page_id],
            "supporting_facts": facts,
            "reason": reason,
            "backlink": False,
            "navigation_only": True,
            "citation_authority": False,
            "verifier": False,
            "hard_filter": False,
            "route_authority": False,
            "promotion_authority": False,
        }

    @staticmethod
    def _observability(
        connection: sqlite3.Connection, task_id: str
    ) -> dict[str, Any]:
        table_queries = {
            "events": "SELECT COUNT(*) FROM research_events WHERE task_id=?",
            "traces": "SELECT COUNT(*) FROM research_traces WHERE task_id=?",
            "receipts": "SELECT COUNT(*) FROM research_command_receipts WHERE task_id=?",
            "build_runs": "SELECT COUNT(*) FROM research_knowledge_build_runs WHERE task_id=?",
            "operations": "SELECT COUNT(*) FROM research_knowledge_update_operations WHERE task_id=?",
            "artifact_routes": "SELECT COUNT(*) FROM research_artifact_routes WHERE task_id=?",
            "page_reviews": "SELECT COUNT(*) FROM research_topic_page_review_decisions WHERE task_id=?",
        }
        counts = {
            name: int(connection.execute(query, (task_id,)).fetchone()[0])
            for name, query in table_queries.items()
        }
        feedback_rows = connection.execute(
            """
            SELECT event_id, sequence, payload_json, command_id, created_at
            FROM research_events
            WHERE task_id=? AND event_type='v5b_product_feedback_recorded'
            ORDER BY sequence DESC LIMIT ?
            """,
            (task_id, MAX_FEEDBACK_ITEMS),
        ).fetchall()
        feedback = [
            {
                "event_id": str(row["event_id"]),
                "sequence": int(row["sequence"]),
                "command_id": str(row["command_id"]),
                "created_at": str(row["created_at"]),
                **_json_object(row["payload_json"]),
            }
            for row in feedback_rows
        ]
        feedback_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM research_events "
                "WHERE task_id=? AND event_type='v5b_product_feedback_recorded'",
                (task_id,),
            ).fetchone()[0]
        )
        status_counts = {
            "build_runs": ResearchProductCloseoutService._group_counts(
                connection,
                "SELECT status, COUNT(*) AS count FROM research_knowledge_build_runs "
                "WHERE task_id=? GROUP BY status ORDER BY status",
                task_id,
            ),
            "operations": ResearchProductCloseoutService._group_counts(
                connection,
                "SELECT status, COUNT(*) AS count FROM research_knowledge_update_operations "
                "WHERE task_id=? GROUP BY status ORDER BY status",
                task_id,
            ),
            "artifact_routes": ResearchProductCloseoutService._group_counts(
                connection,
                "SELECT status, COUNT(*) AS count FROM research_artifact_routes "
                "WHERE task_id=? GROUP BY status ORDER BY status",
                task_id,
            ),
        }
        latest = {
            "event": ResearchProductCloseoutService._latest_row(
                connection,
                "SELECT event_id, sequence, event_type, created_at FROM research_events "
                "WHERE task_id=? ORDER BY sequence DESC LIMIT 1",
                task_id,
            ),
            "trace": ResearchProductCloseoutService._latest_row(
                connection,
                "SELECT trace_id, ended_at, termination_reason, retention_class "
                "FROM research_traces WHERE task_id=? ORDER BY started_at DESC LIMIT 1",
                task_id,
            ),
            "receipt": ResearchProductCloseoutService._latest_row(
                connection,
                "SELECT receipt_id, command_type, status, outcome_reference, completed_at "
                "FROM research_command_receipts WHERE task_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                task_id,
            ),
            "build_run": ResearchProductCloseoutService._latest_row(
                connection,
                "SELECT build_run_id, build_kind, status, attempt_count, output_reference, "
                "error_code, completed_at FROM research_knowledge_build_runs "
                "WHERE task_id=? ORDER BY created_at DESC LIMIT 1",
                task_id,
            ),
            "operation": ResearchProductCloseoutService._latest_row(
                connection,
                "SELECT operation_id, operation_kind, status, attempt_count, error_class, "
                "error_code, updated_at FROM research_knowledge_update_operations "
                "WHERE task_id=? ORDER BY created_at DESC LIMIT 1",
                task_id,
            ),
            "artifact_route": ResearchProductCloseoutService._latest_row(
                connection,
                "SELECT record_id, route_id, version, final_route, status, "
                "expected_authority_hash, created_at FROM research_artifact_routes "
                "WHERE task_id=? ORDER BY created_at DESC, version DESC LIMIT 1",
                task_id,
            ),
            "page_review": ResearchProductCloseoutService._latest_row(
                connection,
                "SELECT decision_id, page_id, page_revision_id, decision_kind, created_at "
                "FROM research_topic_page_review_decisions WHERE task_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                task_id,
            ),
        }
        return {
            "counts": {**counts, "feedback": feedback_count},
            "status_counts": status_counts,
            "latest": latest,
            "feedback": feedback,
            "derived_only": True,
            "operation_authority": False,
            "bounded_feedback_limit": MAX_FEEDBACK_ITEMS,
            "trace_href": f"/research/{task_id}",
        }

    @staticmethod
    def _group_counts(
        connection: sqlite3.Connection, query: str, task_id: str
    ) -> dict[str, int]:
        return {
            str(row["status"]): int(row["count"])
            for row in connection.execute(query, (task_id,)).fetchall()
        }

    @staticmethod
    def _latest_row(
        connection: sqlite3.Connection, query: str, task_id: str
    ) -> dict[str, Any] | None:
        row = connection.execute(query, (task_id,)).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _product_paths(artifact_routes: list[dict[str, Any]]) -> dict[str, Any]:
        completed = [
            route
            for route in artifact_routes
            if route.get("status") == "completed" and route.get("final_route")
        ]
        completed.sort(key=lambda route: (str(route.get("created_at")), int(route.get("version", 0))))
        direct = next(
            (route for route in reversed(completed) if route["final_route"] == "direct_reuse"),
            None,
        )
        changed = next(
            (
                route
                for route in reversed(completed)
                if route["final_route"] in {"incremental_refresh", "research_seed"}
            ),
            None,
        )
        return {
            "reuse_first": ResearchProductCloseoutService._path_summary(direct),
            "research_change": ResearchProductCloseoutService._path_summary(changed),
            "explicit_publish_required": True,
            "candidate_review_required_for_new_content": True,
        }

    @staticmethod
    def _path_summary(route: dict[str, Any] | None) -> dict[str, Any] | None:
        if route is None:
            return None
        return {
            "record_id": route["record_id"],
            "route_id": route["route_id"],
            "route": route["final_route"],
            "status": route["status"],
            "continuation_task_id": route.get("continuation_task_id"),
            "outcome_artifact_revision_id": route.get("outcome_artifact_revision_id"),
            "contribution": route.get("contribution") or {},
            "expected_authority_hash": route["expected_authority_hash"],
        }
