from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from shiliu.db import Database
from shiliu.evidence.continuation import (
    ContinuationTarget,
    create_continuation_envelope,
)
from shiliu.evidence.decision import (
    AspectCoverage,
    AuthorizationStatus,
    ConflictObservation,
    ConflictStatus,
    ContributionKind,
    CorpusNewMaterialCheck,
    CorpusNewMaterialStatus,
    CoverageStatus,
    EvidenceContribution,
    EvidenceDecision,
    EvidenceDecisionAction,
    EvidenceDecisionInput,
    EvidenceRequirement,
    FactRevisionAuthorityReference,
    LibraryFreshness,
    LibraryFreshnessStatus,
    ReferenceScopeStatus,
    RequirementOrigin,
    ScopeAssessment,
    ScopeMatchStatus,
    SourceVersionStatus,
    create_evidence_decision,
    decision_from_persistence_projection,
    decision_to_persistence_projection,
    scope_hash,
    sha256_identity,
)
from shiliu.research.errors import (
    ResearchConflict,
    ResearchNotFound,
    ResearchUnsafeState,
    ResearchValidationError,
)
from shiliu.research.inner_evidence import PersistentEvidenceAuthority
from shiliu.research.knowledge_contracts import (
    AssessArtifactRouteRequest,
    ProceedArtifactRouteRequest,
)
from shiliu.research.product_policy import grounded_current_evidence_profile
from shiliu.research.schema import (
    ARTIFACT_ROUTE_POLICY_VERSION,
    KNOWLEDGE_WORKSPACE_SCHEMA_VERSION,
)
from shiliu.research.service import ResearchTaskService
from shiliu.retrieval.service import RetrievalService


FaultInjector = Callable[[str], None]
ROUTE_ORDER = {
    "direct_reuse": 0,
    "incremental_refresh": 1,
    "research_seed": 2,
}
MAX_INCREMENTAL_GAPS = 2


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _id(prefix: str, value: object) -> str:
    return f"{prefix}_{_hash(value)[:32]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _json(value: object, *, expected: type) -> Any:
    decoded = json.loads(str(value))
    if not isinstance(decoded, expected):
        raise ResearchUnsafeState("persisted ArtifactRoute JSON has invalid shape")
    return decoded


def _normalize(value: str) -> str:
    return "".join(value.casefold().split())


def _terms(value: str) -> set[str]:
    normalized = value.casefold()
    latin = set(re.findall(r"[a-z0-9_]+", normalized))
    cjk = "".join(re.findall(r"[\u3400-\u9fff]", normalized))
    grams = {cjk[index : index + 2] for index in range(max(0, len(cjk) - 1))}
    if len(cjk) == 1:
        grams.add(cjk)
    return latin | grams


class ResearchArtifactRouteService:
    """Lean Stage 3 route aggregate over accepted Stage 1/2 authority."""

    def __init__(
        self,
        db: Database,
        *,
        kernel: ResearchTaskService,
        retrieval: RetrievalService,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self.db = db
        self.kernel = kernel
        self.retrieval = retrieval
        self.authority = PersistentEvidenceAuthority(db)
        self.fault_injector = fault_injector or (lambda _point: None)
        self._command_lock = threading.RLock()

    def assess(
        self, task_id: str, request: AssessArtifactRouteRequest
    ) -> dict[str, Any]:
        request = AssessArtifactRouteRequest.model_validate(
            request.model_dump(mode="json")
        )
        query_value = {
            "query": request.query,
            "normalized_query": _normalize(request.query),
            "required_aspects": request.required_aspects,
            "temporal_scope": request.temporal_scope,
            "viewpoint_scope": request.viewpoint_scope,
            "policy_version": ARTIFACT_ROUTE_POLICY_VERSION,
        }
        payload = {
            "operation": "assess_artifact_route",
            "task_id": task_id,
            **query_value,
            "max_artifact_candidates": request.max_artifact_candidates,
            "max_open_results": request.max_open_results,
        }
        payload_hash = _hash(payload)
        with self._command_lock, self.kernel._transaction() as connection:
            task = self.kernel._task(connection, task_id)
            if str(task["status"]) != "terminal":
                raise ResearchValidationError("Artifact routing requires a terminal query Task")
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}

        open_summary = self._open_retrieval_summary(
            request.query, top_k=request.max_open_results
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
            ranked = self._artifact_candidates(
                connection,
                query=request.query,
                aspects=request.required_aspects,
                limit=request.max_artifact_candidates,
            )
            gates = [
                self._assess_candidate(connection, row, query_value)
                for row in ranked
            ]
            for rank, gate in enumerate(gates, start=1):
                gate["rank"] = rank
            direct = next(
                (value for value in gates if value["candidate_route"] == "direct_reuse"),
                None,
            )
            incremental = next(
                (
                    value
                    for value in gates
                    if value["candidate_route"] == "incremental_refresh"
                ),
                None,
            )
            selected = direct or incremental or (gates[0] if gates else None)
            compatibility_recommendation = (
                "direct_reuse" if direct else "incremental_refresh" if incremental else "research_seed"
            )
            expected_authority_hash = (
                str(selected["authority_hash"])
                if selected is not None
                else _hash(
                    {
                        "query": query_value,
                        "artifact_candidates": [],
                        "open_summary_hash": open_summary["summary_hash"],
                    }
                )
            )
            route_id = _id(
                "artifactroute",
                {"task_id": task_id, "command_id": request.command_id},
            )
            record_id = _id("artifactrouterecord", {"route_id": route_id, "version": 1})
            retrieval_value = {
                "artifact_candidates": [
                    {
                        "artifact_revision_id": value["artifact_revision_id"],
                        "artifact_id": value["artifact_id"],
                        "artifact_task_id": value["artifact_task_id"],
                        "content_hash": value["content_hash"],
                        "rank": value["rank"],
                        "score": value["score"],
                        "score_reason": value["score_reason"],
                    }
                    for value in gates
                ],
                "selected_artifact_revision_id": (
                    selected["artifact_revision_id"] if selected else None
                ),
                "open_corpus": open_summary,
                "authority": {
                    "artifact_ranking": "inspection_order_only",
                    "open_corpus_lane": "independent_not_suppressed",
                    "filesystem": "not_consulted",
                },
            }
            evidence_decision = self._canonical_decision(
                query_value=query_value,
                selected_gate=selected,
                compatibility_recommendation=compatibility_recommendation,
                recorded_at=datetime.now(timezone.utc),
            )
            recommended = self._canonical_route(evidence_decision.action)
            retrieval_value["evidence_decision"] = decision_to_persistence_projection(
                evidence_decision
            )
            retrieval_value["compatibility_recommendation"] = compatibility_recommendation
            connection.execute(
                """
                INSERT INTO research_artifact_routes(
                    record_id, route_id, version, parent_record_id, task_id,
                    record_kind, command_id, payload_hash, query_json,
                    retrieval_json, gates_json, recommended_route, final_route,
                    expected_authority_hash, continuation_task_id,
                    outcome_artifact_revision_id, contribution_json,
                    status, created_at
                ) VALUES(?, ?, 1, NULL, ?, 'assessment', ?, ?, ?, ?, ?, ?, NULL,
                         ?, NULL, NULL, '{}', 'assessed', ?)
                """,
                (
                    record_id,
                    route_id,
                    task_id,
                    request.command_id,
                    payload_hash,
                    _canonical_json(query_value),
                    _canonical_json(retrieval_value),
                    _canonical_json(gates),
                    recommended,
                    expected_authority_hash,
                    _now(),
                ),
            )
            self.fault_injector("after_stage3_route_assessment")
            response = {
                "route_id": route_id,
                "version": 1,
                "recommended_route": recommended,
                "selected_artifact_revision_id": (
                    selected["artifact_revision_id"] if selected else None
                ),
                "expected_authority_hash": expected_authority_hash,
                "artifact_candidates": retrieval_value["artifact_candidates"],
                "open_corpus": open_summary,
                "gates": gates,
                "status": "assessed",
                "evidence_decision": decision_to_persistence_projection(
                    evidence_decision
                ),
                "canonical_action": evidence_decision.action.value,
            }
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                event_type="artifact_route_assessed",
                payload={
                    "route_id": route_id,
                    "recommended_route": recommended,
                    "selected_artifact_revision_id": response[
                        "selected_artifact_revision_id"
                    ],
                    "artifact_candidate_count": len(gates),
                    "open_result_count": len(open_summary["results"]),
                    "expected_authority_hash": expected_authority_hash,
                    "evidence_decision_id": evidence_decision.decision_id,
                    "canonical_action": evidence_decision.action.value,
                },
                command_id=request.command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=_now(),
            )
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="assess_artifact_route",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=_now(),
            )
            self.fault_injector("after_stage3_route_assessment_receipt")
        return {**response, "deduplicated": False}

    def proceed(
        self,
        task_id: str,
        route_id: str,
        request: ProceedArtifactRouteRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        request = ProceedArtifactRouteRequest.model_validate(
            request.model_dump(mode="json")
        )
        payload = {
            "operation": "proceed_artifact_route",
            "task_id": task_id,
            "route_id": route_id,
            **request.model_dump(mode="json"),
            "principal_id": principal_id,
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
            latest = self._latest_record(connection, task_id, route_id)
            if int(latest["version"]) != request.expected_version:
                raise ResearchConflict("stale ArtifactRoute version")
            if request.action == "confirm":
                response = self._confirm(
                    connection,
                    task=task,
                    latest=latest,
                    request=request,
                    payload_hash=payload_hash,
                    principal_id=principal_id,
                )
                event_type = "artifact_route_confirmed"
            else:
                response = self._finalize(
                    connection,
                    task=task,
                    latest=latest,
                    request=request,
                    payload_hash=payload_hash,
                    principal_id=principal_id,
                )
                event_type = "artifact_route_outcome_committed"
            self.fault_injector("after_stage3_route_record")
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                event_type=event_type,
                payload={key: value for key, value in response.items() if key != "gates"},
                command_id=request.command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=_now(),
            )
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="proceed_artifact_route",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=_now(),
            )
            self.fault_injector("after_stage3_route_receipt")
        return {**response, "deduplicated": False}

    def get(self, task_id: str, route_id: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            self.kernel._task(connection, task_id)
            rows = connection.execute(
                "SELECT * FROM research_artifact_routes WHERE task_id=? AND route_id=? "
                "ORDER BY version",
                (task_id, route_id),
            ).fetchall()
        if not rows:
            raise ResearchNotFound(f"ArtifactRoute does not exist: {route_id}")
        records = [self._project(row) for row in rows]
        return {"route_id": route_id, "latest": records[-1], "records": records}

    def list(self, task_id: str) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            self.kernel._task(connection, task_id)
            rows = connection.execute(
                """
                SELECT r.* FROM research_artifact_routes r
                JOIN (
                    SELECT route_id, MAX(version) AS version
                    FROM research_artifact_routes WHERE task_id=? GROUP BY route_id
                ) latest ON latest.route_id=r.route_id AND latest.version=r.version
                WHERE r.task_id=? ORDER BY r.created_at, r.route_id
                """,
                (task_id, task_id),
            ).fetchall()
        return [self._project(row) for row in rows]

    def recommendation_assessment(self, task_id: str) -> dict[str, Any] | None:
        """Revalidate the sole active assessment without proceeding or writing."""
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT r.* FROM research_artifact_routes r
                JOIN (
                    SELECT route_id, MAX(version) AS version
                    FROM research_artifact_routes WHERE task_id=? GROUP BY route_id
                ) latest ON latest.route_id=r.route_id AND latest.version=r.version
                WHERE r.task_id=? AND r.record_kind='assessment' AND r.status='assessed'
                ORDER BY r.created_at, r.route_id
                """,
                (task_id, task_id),
            ).fetchall()
            if not rows:
                return None
            if len(rows) != 1:
                raise ResearchConflict(
                    "multiple active ArtifactRoute assessments require explicit selection"
                )
            row = rows[0]
            query_value = _json(row["query_json"], expected=dict)
            retrieval_value = _json(row["retrieval_json"], expected=dict)
            gates = _json(row["gates_json"], expected=list)
            open_corpus = retrieval_value.get("open_corpus")
            if (
                not isinstance(open_corpus, dict)
                or open_corpus.get("independent_lane") is not True
                or open_corpus.get("hard_filter") is not False
            ):
                raise ResearchConflict("ArtifactRoute open-corpus authority drifted")
            selected_id = retrieval_value.get("selected_artifact_revision_id")
            selected_gate = next(
                (
                    value
                    for value in gates
                    if value.get("artifact_revision_id") == selected_id
                ),
                None,
            )
            recommended_route = str(row["recommended_route"])
            if recommended_route not in ROUTE_ORDER:
                raise ResearchConflict("ArtifactRoute recommendation drifted")
            self._assert_authority_fence(
                connection,
                query_value=query_value,
                selected_gate=selected_gate,
                expected_hash=str(row["expected_authority_hash"]),
            )
            decision_payload = retrieval_value.get("evidence_decision")
            decision = (
                decision_from_persistence_projection(decision_payload)
                if isinstance(decision_payload, dict)
                else None
            )
            if decision is None or self._canonical_route(decision.action) != recommended_route:
                raise ResearchConflict("ArtifactRoute canonical decision drifted")
            return {
                "status": "available",
                "route_id": str(row["route_id"]),
                "version": int(row["version"]),
                "recommended_route": recommended_route,
                "expected_authority_hash": str(row["expected_authority_hash"]),
                "open_corpus": {
                    "independent_lane": True,
                    "hard_filter": False,
                    "summary_hash": open_corpus.get("summary_hash"),
                },
                "selected_gate": selected_gate,
                "evidence_decision": decision_payload,
                "canonical_action": decision.action.value,
            }

    @staticmethod
    def _canonical_route(action: EvidenceDecisionAction) -> str:
        if action == EvidenceDecisionAction.DIRECT_REUSE:
            return "direct_reuse"
        if action == EvidenceDecisionAction.TARGETED_REFRESH:
            return "incremental_refresh"
        return "research_seed"

    @staticmethod
    def _canonical_decision(
        *,
        query_value: dict[str, Any],
        selected_gate: dict[str, Any] | None,
        compatibility_recommendation: str,
        recorded_at: datetime,
    ) -> EvidenceDecision:
        raw_aspects = list(query_value.get("required_aspects") or [])
        requirements = tuple(
            EvidenceRequirement(
                aspect_id=f"aspect_{index}",
                description=str(aspect),
                origin=RequirementOrigin.EXPLICIT_USER,
            )
            for index, aspect in enumerate(raw_aspects, start=1)
        ) or (
            EvidenceRequirement(
                aspect_id="question",
                description=str(query_value["query"]),
                origin=RequirementOrigin.UNKNOWN,
            ),
        )
        selected_facts = {
            str(value["fact_revision_id"]): value
            for value in (selected_gate or {}).get("facts", [])
        }
        covered_by_text = dict((selected_gate or {}).get("covered_aspects", {}))
        coverage: list[AspectCoverage] = []
        contributions: list[EvidenceContribution] = []
        conflicts: list[ConflictObservation] = []
        scope_status = {
            "exact": ScopeMatchStatus.EXACT,
            "compatible": ScopeMatchStatus.COMPATIBLE,
            "mismatch": ScopeMatchStatus.MISMATCH,
            "ambiguous": ScopeMatchStatus.UNKNOWN,
        }.get(str((selected_gate or {}).get("scope_status")), ScopeMatchStatus.UNKNOWN)
        if compatibility_recommendation == "research_seed" and scope_status in {
            ScopeMatchStatus.EXACT,
            ScopeMatchStatus.COMPATIBLE,
        }:
            # The compatibility adapter has proved the gap exceeds the existing
            # bounded refresh route.  Canonical authority therefore selects the
            # Deep/Research boundary instead of allowing the old route to win.
            scope_status = ScopeMatchStatus.MISMATCH
        reference_scope = (
            ReferenceScopeStatus.IN_SCOPE
            if scope_status in {ScopeMatchStatus.EXACT, ScopeMatchStatus.COMPATIBLE}
            else ReferenceScopeStatus.OUT_OF_SCOPE
            if scope_status == ScopeMatchStatus.MISMATCH
            else ReferenceScopeStatus.UNKNOWN
        )
        for fact_id, fact in selected_facts.items():
            snapshot = dict(fact.get("authority_snapshot") or {})
            if str(snapshot.get("lifecycle_status")) != "conflicted":
                continue
            evidence_ids = [
                str(value["evidence_id"]) for value in fact.get("citations", [])
            ]
            conflicts.append(
                ConflictObservation(
                    conflict_id=f"knowledge-conflict-{fact_id}",
                    status=ConflictStatus.CONFIRMED,
                    left_reference_ids=(fact_id,),
                    right_reference_ids=tuple(evidence_ids[:16]) or (fact_id,),
                    observed_at=recorded_at,
                    explanation="accepted Knowledge lifecycle marks this Fact as conflicted",
                )
            )
        for requirement, aspect in zip(requirements, raw_aspects or [str(query_value["query"])]):
            fact_id = covered_by_text.get(aspect)
            fact = selected_facts.get(str(fact_id)) if fact_id else None
            references = ()
            if fact is not None:
                references = (
                    FactRevisionAuthorityReference(
                        reference_id=str(fact["fact_revision_id"]),
                        evidence_reference_ids=tuple(
                            str(value["evidence_id"])
                            for value in fact.get("citations", [])
                        ),
                        source_version_status=(
                            SourceVersionStatus.CURRENT
                            if fact.get("eligible_current")
                            else SourceVersionStatus.STALE
                        ),
                        scope_status=reference_scope,
                        authorization_status=AuthorizationStatus.AUTHORIZED,
                    ),
                )
                contributions.append(
                    EvidenceContribution(
                        kind=ContributionKind.REUSED,
                        reference_id=str(fact["fact_revision_id"]),
                        aspect_ids=(requirement.aspect_id,),
                    )
                )
            coverage.append(
                AspectCoverage(
                    aspect_id=requirement.aspect_id,
                    status=CoverageStatus.COVERED if references else CoverageStatus.OPEN,
                    authority_references=references,
                    explanation=(
                        "legacy route authority was projected to the canonical Fact revision reference"
                        if references
                        else "canonical requirement remains open"
                    ),
                )
            )
        scope_payload = {
            "temporal_scope": query_value.get("temporal_scope", {}),
            "viewpoint_scope": query_value.get("viewpoint_scope", {}),
        }
        freshness_status = (
            CorpusNewMaterialStatus.NO_RELEVANT_NEW_MATERIAL
            if compatibility_recommendation in {"direct_reuse", "incremental_refresh"}
            else CorpusNewMaterialStatus.NOT_CHECKED
        )
        return create_evidence_decision(
            EvidenceDecisionInput(
                normalized_question=str(query_value["query"]),
                requirements=requirements,
                scope=ScopeAssessment(
                    status=scope_status,
                    requested_scope_hash=scope_hash(scope_payload),
                    candidate_scope_hash=(
                        scope_hash(scope_payload)
                        if scope_status != ScopeMatchStatus.UNKNOWN
                        else None
                    ),
                    explanation="bounded Knowledge route scope compatibility projection",
                    compared_reference_ids=tuple(selected_facts),
                ),
                coverage=tuple(coverage),
                library_freshness=LibraryFreshness(
                    status=(
                        LibraryFreshnessStatus.FRESH
                        if freshness_status == CorpusNewMaterialStatus.NO_RELEVANT_NEW_MATERIAL
                        else LibraryFreshnessStatus.UNKNOWN
                    ),
                    corpus_new_material_check=CorpusNewMaterialCheck(
                        status=freshness_status,
                        recorded_check_time=recorded_at,
                        bounded_query_hash=sha256_identity(
                            {
                                "query": query_value["query"],
                                "scope": scope_payload,
                                "compatibility_route": compatibility_recommendation,
                            }
                        ),
                        candidate_reference_ids=tuple(selected_facts),
                    ),
                ),
                conflicts=tuple(conflicts),
                contributions=tuple(contributions),
            ),
            recorded_at=recorded_at,
        )

    def _open_retrieval_summary(self, query: str, *, top_k: int) -> dict[str, Any]:
        results = self.retrieval.search(query, level="all", top_k=top_k)
        bounded = []
        for result in results:
            value = result.as_dict()
            bounded.append(
                {
                    "unit_id": value["unit_id"],
                    "unit_type": value["unit_type"],
                    "video_id": value["video_id"],
                    "source_id": value["source_id"],
                    "title": value["title"],
                    "start_time": value["start_time"],
                    "end_time": value["end_time"],
                    "excerpt": str(value["matched_excerpt"])[:500],
                    "retrieval_method": value["retrieval_method"],
                    "index_version": value["index_version"],
                }
            )
        summary_hash = _hash(bounded)
        return {
            "results": bounded,
            "summary_hash": summary_hash,
            "candidate_only": True,
            "independent_lane": True,
            "hard_filter": False,
        }

    def _artifact_candidates(
        self,
        connection: sqlite3.Connection,
        *,
        query: str,
        aspects: list[str],
        limit: int,
    ) -> list[sqlite3.Row]:
        rows = connection.execute(
            """
            SELECT ar.* FROM research_knowledge_artifact_revisions ar
            WHERE ar.revision=(
                SELECT MAX(ar2.revision)
                FROM research_knowledge_artifact_revisions ar2
                WHERE ar2.artifact_id=ar.artifact_id
            )
            ORDER BY ar.created_at DESC, ar.artifact_revision_id
            """
        ).fetchall()
        query_terms = _terms(" ".join([query, *aspects]))
        ranked: list[tuple[float, str, sqlite3.Row]] = []
        for row in rows:
            text = " ".join(
                [
                    str(row["topic"]),
                    str(row["body_json"]),
                    str(row["limitations_json"]),
                    str(row["unresolved_json"]),
                ]
            )
            artifact_terms = _terms(text)
            overlap = query_terms & artifact_terms
            score = len(overlap) / max(1, len(query_terms))
            if score > 0:
                ranked.append((score, str(row["artifact_revision_id"]), row))
        ranked.sort(key=lambda value: (-value[0], value[1]))
        return [value[2] for value in ranked[:limit]]

    def _assess_candidate(
        self,
        connection: sqlite3.Connection,
        artifact: sqlite3.Row,
        query_value: dict[str, Any],
    ) -> dict[str, Any]:
        fact_rows = connection.execute(
            """
            SELECT afl.ordinal, fr.*, fs.current_revision_id,
                   fs.lifecycle_status, fs.currentness_status, fs.state_version
            FROM research_artifact_fact_links afl
            JOIN research_fact_revisions fr
              ON fr.fact_revision_id=afl.fact_revision_id
            LEFT JOIN research_knowledge_fact_states fs ON fs.fact_id=fr.fact_id
            WHERE afl.artifact_revision_id=? ORDER BY afl.ordinal
            """,
            (str(artifact["artifact_revision_id"]),),
        ).fetchall()
        facts = [self._fact_authority(connection, row) for row in fact_rows]
        aspects = list(query_value["required_aspects"])
        coverage: dict[str, str] = {}
        stale_aspects: list[str] = []
        for aspect in aspects:
            matches = [
                fact
                for fact in facts
                if _normalize(aspect) in _normalize(fact["claim"])
                or _normalize(fact["claim"]) in _normalize(aspect)
            ]
            current = next((fact for fact in matches if fact["eligible_current"]), None)
            if current is not None:
                coverage[aspect] = str(current["fact_revision_id"])
            elif matches:
                stale_aspects.append(aspect)
        missing = [aspect for aspect in aspects if aspect not in coverage]
        reused_ids = list(dict.fromkeys(coverage.values()))
        requested_temporal = dict(query_value["temporal_scope"])
        requested_viewpoint = dict(query_value["viewpoint_scope"])
        explicit_scope_mismatch = False
        unknown_scope = False
        for fact in facts:
            if fact["fact_revision_id"] not in reused_ids:
                continue
            temporal = fact["temporal_scope"]
            viewpoint = fact["viewpoint_scope"]
            if requested_temporal:
                if not temporal:
                    unknown_scope = True
                elif temporal != requested_temporal:
                    explicit_scope_mismatch = True
            elif temporal:
                unknown_scope = True
            if requested_viewpoint:
                if not viewpoint:
                    unknown_scope = True
                elif viewpoint != requested_viewpoint:
                    explicit_scope_mismatch = True
            elif viewpoint:
                unknown_scope = True
        if not aspects:
            scope_status = "ambiguous"
        elif explicit_scope_mismatch:
            scope_status = "mismatch"
        elif unknown_scope:
            scope_status = "ambiguous"
        elif len(coverage) == len(aspects):
            scope_status = "exact"
        elif coverage:
            scope_status = "compatible"
        else:
            scope_status = "mismatch"
        limitations = _json(artifact["limitations_json"], expected=list)
        unresolved = _json(artifact["unresolved_json"], expected=list)
        blocking = [
            str(value)
            for value in [*limitations, *unresolved]
            if any(_normalize(aspect) in _normalize(str(value)) for aspect in aspects)
        ]
        if not aspects:
            completeness = "ambiguous"
        elif not missing and not blocking:
            completeness = "complete"
        elif (
            coverage
            and len(missing) <= MAX_INCREMENTAL_GAPS
            and len(missing) < len(aspects)
            and not blocking
        ):
            completeness = "bounded_partial"
        elif coverage or missing:
            completeness = "substantial_gap"
        else:
            completeness = "ambiguous"
        all_current = bool(facts) and all(fact["eligible_current"] for fact in facts)
        reused_current = bool(reused_ids) and all(
            next(
                fact["eligible_current"]
                for fact in facts
                if fact["fact_revision_id"] == fact_id
            )
            for fact_id in reused_ids
        )
        citation_status = (
            "pass"
            if reused_ids
            and all(
                next(
                    fact["citations_current"]
                    for fact in facts
                    if fact["fact_revision_id"] == fact_id
                )
                for fact_id in reused_ids
            )
            else "fail"
        )
        currentness = "current" if all_current else "bounded_stale" if reused_current else "unsafe"
        if (
            scope_status == "exact"
            and completeness == "complete"
            and currentness == "current"
            and citation_status == "pass"
            and not blocking
        ):
            candidate_route = "direct_reuse"
        elif (
            scope_status in {"exact", "compatible"}
            and completeness == "bounded_partial"
            and reused_current
            and citation_status == "pass"
            and len(missing) <= MAX_INCREMENTAL_GAPS
        ):
            candidate_route = "incremental_refresh"
        else:
            candidate_route = "research_seed"
        authority_snapshot = {
            "artifact_revision_id": str(artifact["artifact_revision_id"]),
            "artifact_id": str(artifact["artifact_id"]),
            "content_hash": str(artifact["content_hash"]),
            "latest_revision": int(
                connection.execute(
                    "SELECT MAX(revision) FROM research_knowledge_artifact_revisions "
                    "WHERE artifact_id=?",
                    (str(artifact["artifact_id"]),),
                ).fetchone()[0]
            ),
            "facts": [fact["authority_snapshot"] for fact in facts],
        }
        score_terms = _terms(
            " ".join([str(query_value["query"]), *list(query_value["required_aspects"])])
        )
        artifact_terms = _terms(
            " ".join([str(artifact["topic"]), str(artifact["body_json"])])
        )
        overlap = sorted(score_terms & artifact_terms)
        return {
            "artifact_revision_id": str(artifact["artifact_revision_id"]),
            "artifact_id": str(artifact["artifact_id"]),
            "artifact_task_id": str(artifact["task_id"]),
            "content_hash": str(artifact["content_hash"]),
            "rank": 0,
            "score": round(len(overlap) / max(1, len(score_terms)), 6),
            "score_reason": {"matched_terms": overlap[:32], "authority": "ranking_only"},
            "scope_status": scope_status,
            "currentness_status": currentness,
            "citation_status": citation_status,
            "completeness_status": completeness,
            "blocking_limitations": blocking,
            "covered_aspects": coverage,
            "missing_aspects": missing,
            "stale_aspects": stale_aspects,
            "reused_fact_revision_ids": reused_ids,
            "candidate_route": candidate_route,
            "reason_codes": self._reason_codes(
                scope_status=scope_status,
                currentness=currentness,
                citation_status=citation_status,
                completeness=completeness,
                blocking=blocking,
            ),
            "facts": facts,
            "authority_snapshot": authority_snapshot,
            "authority_hash": _hash(authority_snapshot),
        }

    def _fact_authority(
        self, connection: sqlite3.Connection, fact: sqlite3.Row
    ) -> dict[str, Any]:
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
            (str(fact["fact_revision_id"]),),
        ).fetchall()
        citations = []
        for link in links:
            observed = self.authority.observe(link)
            citations.append(
                {
                    "evidence_id": str(link["evidence_id"]),
                    "evidence_use_id": str(link["evidence_use_id"]),
                    "expected_source_version": observed.expected_source_version,
                    "observed_source_version": observed.observed_source_version,
                    "outcome": observed.outcome,
                    "reason_code": observed.reason_code,
                    "video_id": int(link["video_id"]),
                    "start_time": float(link["start_time"]),
                    "end_time": float(link["end_time"]),
                    "quote": str(link["quote_preview"]),
                    "transcript_href": f"/media/{int(link['video_id'])}/raw-subtitle",
                }
            )
        citations_current = bool(citations) and all(
            value["outcome"] == "current"
            and value["expected_source_version"] == value["observed_source_version"]
            for value in citations
        )
        state_current = (
            fact["current_revision_id"] is not None
            and str(fact["current_revision_id"]) == str(fact["fact_revision_id"])
            and str(fact["lifecycle_status"]) == "current"
            and str(fact["currentness_status"]) == "current"
        )
        authority_snapshot = {
            "fact_id": str(fact["fact_id"]),
            "fact_revision_id": str(fact["fact_revision_id"]),
            "current_revision_id": (
                str(fact["current_revision_id"])
                if fact["current_revision_id"] is not None
                else None
            ),
            "lifecycle_status": str(fact["lifecycle_status"] or "missing"),
            "currentness_status": str(fact["currentness_status"] or "missing"),
            "state_version": int(fact["state_version"] or 0),
            "citations": citations,
        }
        return {
            "fact_id": str(fact["fact_id"]),
            "fact_revision_id": str(fact["fact_revision_id"]),
            "claim": str(fact["claim_text"]),
            "temporal_scope": _json(fact["temporal_scope_json"], expected=dict),
            "viewpoint_scope": _json(fact["viewpoint_scope_json"], expected=dict),
            "citations": citations,
            "citations_current": citations_current,
            "eligible_current": state_current and citations_current,
            "authority_snapshot": authority_snapshot,
        }

    @staticmethod
    def _reason_codes(
        *,
        scope_status: str,
        currentness: str,
        citation_status: str,
        completeness: str,
        blocking: list[str],
    ) -> list[str]:
        values = [
            f"scope_{scope_status}",
            f"currentness_{currentness}",
            f"citations_{citation_status}",
            f"completeness_{completeness}",
        ]
        if blocking:
            values.append("blocking_limitation_or_unresolved")
        return values

    def _confirm(
        self,
        connection: sqlite3.Connection,
        *,
        task: sqlite3.Row,
        latest: sqlite3.Row,
        request: ProceedArtifactRouteRequest,
        payload_hash: str,
        principal_id: str,
    ) -> dict[str, Any]:
        if str(latest["record_kind"]) != "assessment":
            raise ResearchConflict("ArtifactRoute is already confirmed")
        chosen = str(request.route)
        recommended = str(latest["recommended_route"])
        if ROUTE_ORDER[chosen] < ROUTE_ORDER[recommended]:
            raise ResearchValidationError("unsafe route override cannot bypass the Gate")
        query_value = _json(latest["query_json"], expected=dict)
        retrieval_value = _json(latest["retrieval_json"], expected=dict)
        gates = _json(latest["gates_json"], expected=list)
        canonical_payload = retrieval_value.get("evidence_decision")
        if not isinstance(canonical_payload, dict):
            raise ResearchConflict("ArtifactRoute canonical decision is missing")
        canonical_decision = decision_from_persistence_projection(canonical_payload)
        if self._canonical_route(canonical_decision.action) != recommended:
            raise ResearchConflict("ArtifactRoute canonical decision drifted")
        selected_id = retrieval_value.get("selected_artifact_revision_id")
        selected_gate = next(
            (
                value
                for value in gates
                if value["artifact_revision_id"] == selected_id
            ),
            None,
        )
        self._assert_authority_fence(
            connection,
            query_value=query_value,
            selected_gate=selected_gate,
            expected_hash=str(latest["expected_authority_hash"]),
        )
        if chosen == "direct_reuse":
            if selected_gate is None or selected_gate["candidate_route"] != "direct_reuse":
                raise ResearchValidationError("direct reuse Gate is not satisfied")
            continuation_task_id = None
            outcome_artifact_revision_id = str(selected_id)
            status = "completed"
            contribution = {
                "reused": selected_gate["reused_fact_revision_ids"],
                "newly_researched": [],
                "dropped": [],
                "authority": "exact_existing_artifact_revision",
            }
        else:
            if chosen == "incremental_refresh" and (
                selected_gate is None
                or selected_gate["candidate_route"] not in {
                    "direct_reuse",
                    "incremental_refresh",
                }
            ):
                raise ResearchValidationError("incremental refresh Gate is not satisfied")
            continuation_task_id = self._create_continuation_task(
                connection,
                parent_task=task,
                route_id=str(latest["route_id"]),
                final_route=chosen,
                query_value=query_value,
                selected_gate=selected_gate,
                command_id=request.command_id,
                evidence_decision=canonical_decision,
            )
            outcome_artifact_revision_id = None
            status = "running"
            contribution = {
                "parent_artifact_revision_id": selected_id,
                "reused": (
                    selected_gate["reused_fact_revision_ids"]
                    if chosen == "incremental_refresh" and selected_gate
                    else []
                ),
                "newly_researched": [],
                "dropped": [],
                "target_aspects": (
                    selected_gate["missing_aspects"]
                    if chosen == "incremental_refresh" and selected_gate
                    else query_value["required_aspects"]
                ),
                "artifact_context_authority": "candidate_only_not_verifier",
                "open_retrieval_required": True,
            }
        version = int(latest["version"]) + 1
        record_id = _id(
            "artifactrouterecord",
            {"route_id": latest["route_id"], "version": version},
        )
        connection.execute(
            """
            INSERT INTO research_artifact_routes(
                record_id, route_id, version, parent_record_id, task_id,
                record_kind, command_id, payload_hash, query_json,
                retrieval_json, gates_json, recommended_route, final_route,
                expected_authority_hash, continuation_task_id,
                outcome_artifact_revision_id, contribution_json,
                status, created_at
            ) VALUES(?, ?, ?, ?, ?, 'proceed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                str(latest["route_id"]),
                version,
                str(latest["record_id"]),
                str(task["task_id"]),
                request.command_id,
                payload_hash,
                str(latest["query_json"]),
                str(latest["retrieval_json"]),
                str(latest["gates_json"]),
                recommended,
                chosen,
                str(latest["expected_authority_hash"]),
                continuation_task_id,
                outcome_artifact_revision_id,
                _canonical_json(contribution),
                status,
                _now(),
            ),
        )
        return {
            "route_id": str(latest["route_id"]),
            "version": version,
            "recommended_route": recommended,
            "final_route": chosen,
            "continuation_task_id": continuation_task_id,
            "outcome_artifact_revision_id": outcome_artifact_revision_id,
            "contribution": contribution,
            "status": status,
            "reason": request.reason,
            "principal_id": principal_id,
            "evidence_decision": canonical_payload,
            "canonical_action": canonical_decision.action.value,
        }

    def _finalize(
        self,
        connection: sqlite3.Connection,
        *,
        task: sqlite3.Row,
        latest: sqlite3.Row,
        request: ProceedArtifactRouteRequest,
        payload_hash: str,
        principal_id: str,
    ) -> dict[str, Any]:
        if str(latest["record_kind"]) != "proceed" or str(latest["status"]) != "running":
            raise ResearchConflict("ArtifactRoute has no running continuation to finalize")
        final_route = str(latest["final_route"])
        child_task_id = str(latest["continuation_task_id"] or "")
        child = self.kernel._task(connection, child_task_id)
        if str(child["parent_task_id"] or "") != str(task["task_id"]):
            raise ResearchValidationError("continuation Task left the route parent boundary")
        if str(child["status"]) != "terminal":
            raise ResearchConflict("continuation Task is not terminal")
        query_value = _json(latest["query_json"], expected=dict)
        retrieval_value = _json(latest["retrieval_json"], expected=dict)
        gates = _json(latest["gates_json"], expected=list)
        parent_decision_payload = retrieval_value.get("evidence_decision")
        if not isinstance(parent_decision_payload, dict):
            raise ResearchConflict("ArtifactRoute canonical decision is missing")
        parent_decision = decision_from_persistence_projection(parent_decision_payload)
        selected_id = retrieval_value.get("selected_artifact_revision_id")
        selected_gate = next(
            (value for value in gates if value["artifact_revision_id"] == selected_id),
            None,
        )
        if final_route == "incremental_refresh":
            if selected_gate is None:
                raise ResearchUnsafeState("incremental route lost its selected Artifact")
            self._assert_authority_fence(
                connection,
                query_value=query_value,
                selected_gate=selected_gate,
                expected_hash=str(latest["expected_authority_hash"]),
            )
            gaps = list(selected_gate["missing_aspects"])
            if set(request.new_fact_aspect_map) != set(gaps):
                raise ResearchValidationError(
                    "incremental outcome must cover exactly the persisted bounded gaps"
                )
            new_fact_ids = list(request.new_fact_aspect_map.values())
            for aspect, fact_id in request.new_fact_aspect_map.items():
                self._assert_new_fact_current(
                    connection,
                    child_task_id=child_task_id,
                    fact_revision_id=fact_id,
                    aspect=aspect,
                )
            outcome_artifact_revision_id, contribution = self._create_incremental_artifact(
                connection,
                route_id=str(latest["route_id"]),
                parent_artifact_revision_id=str(selected_id),
                query_value=query_value,
                selected_gate=selected_gate,
                new_fact_aspect_map=request.new_fact_aspect_map,
                dropped_fact_revision_ids=request.dropped_fact_revision_ids,
            )
            outcome_decision = self._incremental_outcome_decision(
                connection,
                parent_decision=parent_decision,
                new_fact_aspect_map=request.new_fact_aspect_map,
                dropped_fact_revision_ids=request.dropped_fact_revision_ids,
            )
        elif final_route == "research_seed":
            outcome_id = request.outcome_artifact_revision_id
            if not outcome_id:
                raise ResearchValidationError(
                    "seed finalize requires the independently built Artifact revision"
                )
            artifact = connection.execute(
                "SELECT * FROM research_knowledge_artifact_revisions "
                "WHERE artifact_revision_id=? AND task_id=?",
                (outcome_id, child_task_id),
            ).fetchone()
            if artifact is None:
                raise ResearchValidationError("seed outcome Artifact left child Task boundary")
            outcome_artifact_revision_id = str(outcome_id)
            contribution = {
                "parent_artifact_revision_id": selected_id,
                "reused": [],
                "newly_researched": [],
                "dropped": [],
                "seed_context_only": True,
                "old_artifact_was_verifier": False,
            }
            outcome_decision = parent_decision
        else:
            raise ResearchConflict("direct reuse is already terminal")
        version = int(latest["version"]) + 1
        record_id = _id(
            "artifactrouterecord",
            {"route_id": latest["route_id"], "version": version},
        )
        outcome_retrieval = dict(retrieval_value)
        outcome_retrieval["parent_evidence_decision"] = parent_decision_payload
        outcome_retrieval["evidence_decision"] = decision_to_persistence_projection(
            outcome_decision
        )
        connection.execute(
            """
            INSERT INTO research_artifact_routes(
                record_id, route_id, version, parent_record_id, task_id,
                record_kind, command_id, payload_hash, query_json,
                retrieval_json, gates_json, recommended_route, final_route,
                expected_authority_hash, continuation_task_id,
                outcome_artifact_revision_id, contribution_json,
                status, created_at
            ) VALUES(?, ?, ?, ?, ?, 'outcome', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)
            """,
            (
                record_id,
                str(latest["route_id"]),
                version,
                str(latest["record_id"]),
                str(task["task_id"]),
                request.command_id,
                payload_hash,
                str(latest["query_json"]),
                _canonical_json(outcome_retrieval),
                str(latest["gates_json"]),
                str(latest["recommended_route"]),
                final_route,
                str(latest["expected_authority_hash"]),
                child_task_id,
                outcome_artifact_revision_id,
                _canonical_json(contribution),
                _now(),
            ),
        )
        return {
            "route_id": str(latest["route_id"]),
            "version": version,
            "recommended_route": str(latest["recommended_route"]),
            "final_route": final_route,
            "continuation_task_id": child_task_id,
            "outcome_artifact_revision_id": outcome_artifact_revision_id,
            "contribution": contribution,
            "status": "completed",
            "reason": request.reason,
            "principal_id": principal_id,
            "evidence_decision": decision_to_persistence_projection(outcome_decision),
            "canonical_action": outcome_decision.action.value,
        }

    def _incremental_outcome_decision(
        self,
        connection: sqlite3.Connection,
        *,
        parent_decision: EvidenceDecision,
        new_fact_aspect_map: dict[str, str],
        dropped_fact_revision_ids: list[str],
    ) -> EvidenceDecision:
        coverage: list[AspectCoverage] = []
        contributions = list(parent_decision.contributions)
        dropped = set(dropped_fact_revision_ids)
        for requirement in parent_decision.requirements:
            prior = next(
                value
                for value in parent_decision.coverage
                if value.aspect_id == requirement.aspect_id
            )
            fact_id = new_fact_aspect_map.get(requirement.description)
            if fact_id is None:
                retained = tuple(
                    value
                    for value in prior.authority_references
                    if value.reference_id not in dropped
                )
                coverage.append(
                    prior.model_copy(
                        update={
                            "authority_references": retained,
                            "status": (
                                CoverageStatus.COVERED
                                if retained
                                else CoverageStatus.OPEN
                            ),
                        }
                    )
                )
                continue
            row = connection.execute(
                """
                SELECT fr.*, fs.current_revision_id, fs.lifecycle_status,
                       fs.currentness_status, fs.state_version
                FROM research_fact_revisions fr
                JOIN research_knowledge_fact_states fs ON fs.fact_id=fr.fact_id
                WHERE fr.fact_revision_id=?
                """,
                (fact_id,),
            ).fetchone()
            if row is None:
                raise ResearchUnsafeState("incremental canonical Fact is missing")
            fact = self._fact_authority(connection, row)
            reference = FactRevisionAuthorityReference(
                reference_id=fact_id,
                evidence_reference_ids=tuple(
                    str(value["evidence_id"]) for value in fact["citations"]
                ),
                source_version_status=SourceVersionStatus.CURRENT,
                scope_status=ReferenceScopeStatus.IN_SCOPE,
                authorization_status=AuthorizationStatus.AUTHORIZED,
            )
            coverage.append(
                AspectCoverage(
                    aspect_id=requirement.aspect_id,
                    status=CoverageStatus.COVERED,
                    authority_references=(reference,),
                    explanation="incremental child Fact revalidated against current Evidence",
                )
            )
            contributions.append(
                EvidenceContribution(
                    kind=ContributionKind.NEW,
                    reference_id=fact_id,
                    aspect_ids=(requirement.aspect_id,),
                )
            )
        for fact_id in dropped:
            contributions.append(
                EvidenceContribution(
                    kind=ContributionKind.DROPPED,
                    reference_id=fact_id,
                )
            )
        recorded_at = datetime.now(timezone.utc)
        return create_evidence_decision(
            EvidenceDecisionInput(
                normalized_question=parent_decision.normalized_question,
                parent_decision_id=parent_decision.decision_id,
                requirements=parent_decision.requirements,
                scope=parent_decision.scope,
                coverage=tuple(coverage),
                library_freshness=LibraryFreshness(
                    status=LibraryFreshnessStatus.FRESH,
                    corpus_new_material_check=CorpusNewMaterialCheck(
                        status=CorpusNewMaterialStatus.NO_RELEVANT_NEW_MATERIAL,
                        recorded_check_time=recorded_at,
                        previous_check_time=parent_decision.library_freshness.corpus_new_material_check.recorded_check_time,
                        bounded_query_hash=sha256_identity(
                            {
                                "parent_decision_id": parent_decision.decision_id,
                                "new_fact_aspect_map": new_fact_aspect_map,
                            }
                        ),
                        candidate_reference_ids=tuple(new_fact_aspect_map.values()),
                    ),
                ),
                conflicts=parent_decision.conflicts,
                contributions=tuple(contributions),
                semantic_advice=parent_decision.semantic_advice,
            ),
            recorded_at=recorded_at,
        )

    def _assert_authority_fence(
        self,
        connection: sqlite3.Connection,
        *,
        query_value: dict[str, Any],
        selected_gate: dict[str, Any] | None,
        expected_hash: str,
    ) -> None:
        if selected_gate is None:
            candidates = self._artifact_candidates(
                connection,
                query=str(query_value["query"]),
                aspects=list(query_value["required_aspects"]),
                limit=1,
            )
            if candidates:
                raise ResearchConflict("no-hit route is stale; reroute required")
            return
        artifact = connection.execute(
            "SELECT * FROM research_knowledge_artifact_revisions "
            "WHERE artifact_revision_id=? AND content_hash=?",
            (
                str(selected_gate["artifact_revision_id"]),
                str(selected_gate["content_hash"]),
            ),
        ).fetchone()
        if artifact is None:
            raise ResearchConflict("Artifact content-hash fence changed")
        current = self._assess_candidate(connection, artifact, query_value)
        if str(current["authority_hash"]) != expected_hash:
            raise ResearchConflict("Artifact authority snapshot changed; reroute required")

    def _create_continuation_task(
        self,
        connection: sqlite3.Connection,
        *,
        parent_task: sqlite3.Row,
        route_id: str,
        final_route: str,
        query_value: dict[str, Any],
        selected_gate: dict[str, Any] | None,
        command_id: str,
        evidence_decision: EvidenceDecision,
    ) -> str:
        if str(parent_task["status"]) != "terminal":
            raise ResearchValidationError("route parent Task must be terminal")
        child_task_id = _id(
            "rtask", {"route_id": route_id, "final_route": final_route}
        )
        if connection.execute(
            "SELECT 1 FROM research_tasks WHERE task_id=?", (child_task_id,)
        ).fetchone():
            raise ResearchConflict("continuation Task already exists without route receipt")
        target_aspects = (
            list(selected_gate["missing_aspects"])
            if final_route == "incremental_refresh" and selected_gate
            else list(query_value["required_aspects"])
        )
        child_objective = (
            "；".join(target_aspects)
            if final_route == "incremental_refresh" and target_aspects
            else str(query_value["query"])
        )
        reused = (
            list(selected_gate["reused_fact_revision_ids"])
            if final_route == "incremental_refresh" and selected_gate
            else []
        )
        evidence_policy = {
            "authority": "live_current_exact_replay",
            "product_execution": "deterministic_no_provider",
            "constraint_profile": "grounded_current_evidence",
            "artifact_route_id": route_id,
            "route_kind": final_route,
            "parent_artifact_revision_id": (
                selected_gate["artifact_revision_id"] if selected_gate else None
            ),
            "reused_fact_revision_ids": reused,
            "artifact_context_authority": "candidate_only_not_verifier",
            "open_retrieval_required": True,
            "target_aspects": target_aspects,
            "original_query": str(query_value["query"]),
            "evidence_decision": decision_to_persistence_projection(evidence_decision),
            "continuation_envelope": create_continuation_envelope(
                parent_run_id=str(parent_task["task_id"]),
                parent_decision=evidence_decision,
                target=ContinuationTarget.KNOWLEDGE_REUSE,
                original_question=str(query_value["query"]),
                normalized_scope={
                    "temporal_scope": query_value.get("temporal_scope", {}),
                    "viewpoint_scope": query_value.get("viewpoint_scope", {}),
                },
            ).model_dump(mode="json"),
            "provider_authority_inherited": False,
        }
        now = _now()
        goal_id = _id("goal", {"task_id": child_task_id, "revision": 1})
        connection.execute(
            """
            INSERT INTO research_tasks(
                task_id, parent_task_id, status, active_goal_id, state_version,
                owner_id, owner_epoch, lease_until, terminal_result_id,
                created_at, updated_at
            ) VALUES(?, ?, 'ready', NULL, 0, NULL, 0, NULL, NULL, ?, ?)
            """,
            (child_task_id, str(parent_task["task_id"]), now, now),
        )
        self.fault_injector("after_stage3_continuation_task")
        connection.execute(
            """
            INSERT INTO research_goals(
                goal_id, task_id, revision, parent_goal_id, objective,
                success_constraints_json, evidence_policy_json,
                created_by_event_id, created_at
            ) VALUES(?, ?, 1, NULL, ?, ?, ?, NULL, ?)
            """,
            (
                goal_id,
                child_task_id,
                child_objective,
                _canonical_json([]),
                _canonical_json(evidence_policy),
                now,
            ),
        )
        connection.execute(
            "UPDATE research_tasks SET active_goal_id=? WHERE task_id=?",
            (goal_id, child_task_id),
        )
        event_id = self.kernel._event(
            connection,
            task_id=child_task_id,
            goal_id=goal_id,
            event_type="task_created",
            payload={
                "parent_task_id": str(parent_task["task_id"]),
                "goal_revision": 1,
                "artifact_route_id": route_id,
                "route_kind": final_route,
                "server_constraint_profile": grounded_current_evidence_profile(),
            },
            command_id=f"{command_id}:child",
            owner_epoch=0,
            now=now,
        )
        connection.execute(
            "UPDATE research_goals SET created_by_event_id=? WHERE goal_id=?",
            (event_id, goal_id),
        )
        child_payload_hash = _hash(
            {
                "route_id": route_id,
                "route_kind": final_route,
                "objective": child_objective,
                "target_aspects": target_aspects,
                "evidence_policy": evidence_policy,
            }
        )
        self.kernel._insert_receipt(
            connection,
            task_id=child_task_id,
            command_id=f"{command_id}:child",
            command_type="create_artifact_route_continuation",
            payload_hash=child_payload_hash,
            outcome_reference=event_id,
            response={"task_id": child_task_id, "goal_id": goal_id, "state_version": 0},
            owner_epoch=0,
            now=now,
        )
        return child_task_id

    def _assert_new_fact_current(
        self,
        connection: sqlite3.Connection,
        *,
        child_task_id: str,
        fact_revision_id: str,
        aspect: str,
    ) -> None:
        row = connection.execute(
            """
            SELECT fr.*, fs.current_revision_id, fs.lifecycle_status,
                   fs.currentness_status, fs.state_version
            FROM research_fact_revisions fr
            JOIN research_knowledge_fact_states fs ON fs.fact_id=fr.fact_id
            WHERE fr.fact_revision_id=? AND fr.task_id=?
            """,
            (fact_revision_id, child_task_id),
        ).fetchone()
        if row is None or not self._fact_authority(connection, row)["eligible_current"]:
            raise ResearchValidationError(
                "incremental new Fact must be current-grounded and belong to child Task"
            )
        if (
            _normalize(aspect) not in _normalize(str(row["claim_text"]))
            and _normalize(str(row["claim_text"])) not in _normalize(aspect)
        ):
            raise ResearchValidationError(
                "incremental new Fact does not cover its persisted gap aspect"
            )

    def _create_incremental_artifact(
        self,
        connection: sqlite3.Connection,
        *,
        route_id: str,
        parent_artifact_revision_id: str,
        query_value: dict[str, Any],
        selected_gate: dict[str, Any],
        new_fact_aspect_map: dict[str, str],
        dropped_fact_revision_ids: list[str],
    ) -> tuple[str, dict[str, Any]]:
        parent = connection.execute(
            "SELECT * FROM research_knowledge_artifact_revisions "
            "WHERE artifact_revision_id=?",
            (parent_artifact_revision_id,),
        ).fetchone()
        if parent is None:
            raise ResearchUnsafeState("parent Artifact revision missing")
        old_fact_ids = [
            str(row[0])
            for row in connection.execute(
                "SELECT fact_revision_id FROM research_artifact_fact_links "
                "WHERE artifact_revision_id=? ORDER BY ordinal",
                (parent_artifact_revision_id,),
            ).fetchall()
        ]
        reused = list(selected_gate["reused_fact_revision_ids"])
        dropped = list(
            dict.fromkeys(
                [
                    fact_id
                    for fact_id in old_fact_ids
                    if fact_id not in reused
                ]
                + dropped_fact_revision_ids
            )
        )
        if any(fact_id in reused for fact_id in dropped):
            raise ResearchValidationError("a Fact cannot be both reused and dropped")
        new_fact_ids = list(new_fact_aspect_map.values())
        result_fact_ids = list(dict.fromkeys([*reused, *new_fact_ids]))
        facts, corpus = self._artifact_body(connection, result_fact_ids)
        revision = int(
            connection.execute(
                "SELECT MAX(revision)+1 FROM research_knowledge_artifact_revisions "
                "WHERE artifact_id=?",
                (str(parent["artifact_id"]),),
            ).fetchone()[0]
        )
        input_value = {
            "route_id": route_id,
            "parent_artifact_revision_id": parent_artifact_revision_id,
            "reused": reused,
            "new_fact_aspect_map": new_fact_aspect_map,
            "dropped": dropped,
            "authority": ARTIFACT_ROUTE_POLICY_VERSION,
        }
        input_hash = _hash(input_value)
        revision_id = _id(
            "kartifactrev",
            {"artifact_id": parent["artifact_id"], "revision": revision, "route": route_id},
        )
        body = {
            "facts": facts,
            "source": {
                "route_id": route_id,
                "parent_artifact_revision_id": parent_artifact_revision_id,
                "corpus_snapshot": corpus,
            },
        }
        limitations = _json(parent["limitations_json"], expected=list)
        unresolved = [
            value
            for value in _json(parent["unresolved_json"], expected=list)
            if str(value) not in new_fact_aspect_map
        ]
        content_hash = _hash(
            {
                "topic": query_value["query"],
                "body": body,
                "limitations": limitations,
                "unresolved": unresolved,
                "policy": ARTIFACT_ROUTE_POLICY_VERSION,
            }
        )
        source_result_ids = set(_json(parent["source_result_ids_json"], expected=list))
        source_boundaries = set(
            _json(parent["source_boundary_hashes_json"], expected=list)
        )
        for fact_id in new_fact_ids:
            row = connection.execute(
                """
                SELECT kc.result_id, kc.source_boundary_hash
                FROM research_fact_revisions fr
                JOIN research_grounded_facts gf ON gf.fact_id=fr.fact_id
                JOIN research_knowledge_candidates kc
                  ON kc.candidate_id=gf.origin_candidate_id
                WHERE fr.fact_revision_id=?
                """,
                (fact_id,),
            ).fetchone()
            if row and row["result_id"]:
                source_result_ids.add(str(row["result_id"]))
            if row:
                source_boundaries.add(str(row["source_boundary_hash"]))
        connection.execute(
            """
            INSERT INTO research_knowledge_artifact_revisions(
                artifact_revision_id, artifact_id, task_id, revision,
                parent_revision_id, supersedes_revision_id, topic, body_json,
                limitations_json, unresolved_json, build_policy_version,
                source_result_ids_json, source_boundary_hashes_json,
                corpus_snapshot_json, input_hash, content_hash, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision_id,
                str(parent["artifact_id"]),
                str(parent["task_id"]),
                revision,
                parent_artifact_revision_id,
                parent_artifact_revision_id,
                str(query_value["query"]),
                _canonical_json(body),
                _canonical_json(limitations),
                _canonical_json(unresolved),
                ARTIFACT_ROUTE_POLICY_VERSION,
                _canonical_json(sorted(source_result_ids)),
                _canonical_json(sorted(source_boundaries)),
                _canonical_json(corpus),
                input_hash,
                content_hash,
                _now(),
            ),
        )
        for ordinal, fact_id in enumerate(result_fact_ids):
            connection.execute(
                "INSERT INTO research_artifact_fact_links("
                "link_id, task_id, artifact_revision_id, fact_revision_id, ordinal, created_at"
                ") VALUES(?, ?, ?, ?, ?, ?)",
                (
                    _id("artifactfact", {"artifact_revision_id": revision_id, "fact": fact_id}),
                    str(parent["task_id"]),
                    revision_id,
                    fact_id,
                    ordinal,
                    _now(),
                ),
            )
        self.fault_injector("after_stage3_incremental_artifact")
        contribution = {
            "parent_artifact_revision_id": parent_artifact_revision_id,
            "result_artifact_revision_id": revision_id,
            "reused": [
                {
                    "fact_revision_id": fact_id,
                    "disposition": "reused",
                    "citations": self._fact_authority_by_id(
                        connection, fact_id
                    )["citations"],
                }
                for fact_id in reused
            ],
            "newly_researched": [
                {
                    "aspect": aspect,
                    "fact_revision_id": fact_id,
                    "disposition": "new",
                    "citations": self._fact_authority_by_id(
                        connection, fact_id
                    )["citations"],
                }
                for aspect, fact_id in new_fact_aspect_map.items()
            ],
            "dropped": [
                {"fact_revision_id": fact_id, "disposition": "dropped_with_reason"}
                for fact_id in dropped
            ],
        }
        return revision_id, contribution

    def _fact_authority_by_id(
        self, connection: sqlite3.Connection, fact_revision_id: str
    ) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT fr.*, fs.current_revision_id, fs.lifecycle_status,
                   fs.currentness_status, fs.state_version
            FROM research_fact_revisions fr
            LEFT JOIN research_knowledge_fact_states fs ON fs.fact_id=fr.fact_id
            WHERE fr.fact_revision_id=?
            """,
            (fact_revision_id,),
        ).fetchone()
        if row is None:
            raise ResearchUnsafeState("Artifact contribution Fact missing")
        return self._fact_authority(connection, row)

    def _artifact_body(
        self, connection: sqlite3.Connection, fact_revision_ids: list[str]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        facts = []
        corpus: dict[str, dict[str, Any]] = {}
        for fact_id in fact_revision_ids:
            row = connection.execute(
                "SELECT * FROM research_fact_revisions WHERE fact_revision_id=?",
                (fact_id,),
            ).fetchone()
            if row is None:
                raise ResearchUnsafeState("Artifact contribution Fact missing")
            links = connection.execute(
                """
                SELECT fel.evidence_id, ei.video_id, ei.source_artifact_id,
                       ei.source_version, ei.timeline_run_id
                FROM research_fact_evidence_links fel
                JOIN research_evidence_identities ei ON ei.evidence_id=fel.evidence_id
                WHERE fel.fact_revision_id=? ORDER BY fel.ordinal
                """,
                (fact_id,),
            ).fetchall()
            citation_ids = [str(link["evidence_id"]) for link in links]
            facts.append(
                {
                    "fact_revision_id": fact_id,
                    "claim": str(row["claim_text"]),
                    "citation_ids": citation_ids,
                }
            )
            for link in links:
                corpus[str(link["evidence_id"])] = {
                    "evidence_id": str(link["evidence_id"]),
                    "video_id": int(link["video_id"]),
                    "source_artifact_id": str(link["source_artifact_id"]),
                    "source_version": str(link["source_version"]),
                    "timeline_run_id": str(link["timeline_run_id"]),
                }
        return facts, {
            "authority": "evidence_identity_source_versions",
            "evidence": [corpus[key] for key in sorted(corpus)],
        }

    @staticmethod
    def _latest_record(
        connection: sqlite3.Connection, task_id: str, route_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM research_artifact_routes WHERE task_id=? AND route_id=? "
            "ORDER BY version DESC LIMIT 1",
            (task_id, route_id),
        ).fetchone()
        if row is None:
            raise ResearchNotFound(f"ArtifactRoute does not exist: {route_id}")
        return row

    @staticmethod
    def _project(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "record_id": str(row["record_id"]),
            "route_id": str(row["route_id"]),
            "version": int(row["version"]),
            "record_kind": str(row["record_kind"]),
            "query": _json(row["query_json"], expected=dict),
            "retrieval": _json(row["retrieval_json"], expected=dict),
            "gates": _json(row["gates_json"], expected=list),
            "recommended_route": str(row["recommended_route"]),
            "final_route": str(row["final_route"]) if row["final_route"] else None,
            "expected_authority_hash": str(row["expected_authority_hash"]),
            "continuation_task_id": (
                str(row["continuation_task_id"])
                if row["continuation_task_id"]
                else None
            ),
            "outcome_artifact_revision_id": (
                str(row["outcome_artifact_revision_id"])
                if row["outcome_artifact_revision_id"]
                else None
            ),
            "contribution": _json(row["contribution_json"], expected=dict),
            "status": str(row["status"]),
            "created_at": str(row["created_at"]),
        }
