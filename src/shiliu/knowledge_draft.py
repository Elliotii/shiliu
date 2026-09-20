"""Durable non-authoritative Knowledge Draft and confirmed promotion path."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from shiliu.ask.persistence import AskRunStore
from shiliu.ask.evidence import TranscriptEvidenceMaterializer, _reference
from shiliu.ask.contracts import Citation, TranscriptEvidenceSpan
from shiliu.db import Database
from shiliu.evidence.authority import bind_live_current_version
from shiliu.research.knowledge_contracts import (
    IntakeKnowledgeCandidatesRequest,
    PublishKnowledgeSelection,
    PublishResearchKnowledgeRequest,
)
from shiliu.research.inner_evidence import PersistentEvidenceAuthority
from shiliu.research.knowledge_service import ResearchKnowledgeService
from shiliu.research.product_contracts import (
    CreateProductResearchRequest,
    RunProductResearchRequest,
)
from shiliu.research.product_service import ResearchProductService
from shiliu.research.schema import KNOWLEDGE_DRAFT_SCHEMA_VERSION


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SaveKnowledgeDraftRequest(_StrictModel):
    source_kind: Literal["ask_run", "research_task"]
    source_id: str = Field(min_length=1, max_length=160)
    expected_source_hash: str | None = Field(default=None, max_length=160)
    command_id: str = Field(min_length=1, max_length=160)


class DraftCommandRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    expected_version: int = Field(ge=1)


class ConfirmDraftPromotionRequest(DraftCommandRequest):
    candidate_ids: list[str] = Field(min_length=1, max_length=32)


class KnowledgeDraftError(RuntimeError):
    def __init__(self, message: str, *, code: str, http_status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


class KnowledgeDraftService:
    """Append-only Draft revisions; never a Fact or citation authority."""

    def __init__(
        self,
        *,
        db: Database,
        product: ResearchProductService,
        knowledge: ResearchKnowledgeService,
    ) -> None:
        self.db = db
        self.ask_runs = AskRunStore(db)
        self.materializer = TranscriptEvidenceMaterializer(db)
        self.research_authority = PersistentEvidenceAuthority(db)
        self.product = product
        self.knowledge = knowledge

    def save(self, request: SaveKnowledgeDraftRequest) -> dict[str, Any]:
        request = SaveKnowledgeDraftRequest.model_validate(request)
        if request.source_kind == "ask_run":
            source = self._ask_source(request.source_id)
            origin_kind = str(source["mode"])
            ask_run_id, research_task_id = request.source_id, None
        else:
            source = self._research_source(request.source_id)
            origin_kind = "research"
            ask_run_id, research_task_id = None, request.source_id
        if request.expected_source_hash and request.expected_source_hash != source["answer_hash"]:
            raise KnowledgeDraftError(
                "source answer hash changed", code="draft_source_hash_mismatch"
            )
        dedupe = _hash(
            [
                "local_user_workspace",
                origin_kind,
                request.source_id,
                source["answer_hash"],
                source["scope"],
            ]
        )
        draft_id = f"kdraft_{dedupe[7:39]}"
        payload_hash = _hash(request.model_dump(mode="json"))
        with self.db.connect() as connection:
            existing_command = connection.execute(
                "SELECT * FROM knowledge_draft_revisions WHERE draft_id=? AND command_id=?",
                (draft_id, request.command_id),
            ).fetchone()
            if existing_command is not None:
                if str(existing_command["command_payload_hash"]) != payload_hash:
                    raise KnowledgeDraftError(
                        "command payload mismatch", code="draft_command_payload_mismatch"
                    )
                return self._decode(existing_command)
            existing = connection.execute(
                "SELECT * FROM knowledge_draft_revisions "
                "WHERE owner_scope='local_user_workspace' AND dedupe_identity=? "
                "ORDER BY version DESC LIMIT 1",
                (dedupe,),
            ).fetchone()
            if existing is not None:
                return self._decode(existing)
            revision_id = f"kdrev_{hashlib.sha256((draft_id + ':1').encode()).hexdigest()[:32]}"
            connection.execute(
                """
                INSERT INTO knowledge_draft_revisions(
                    draft_revision_id,draft_id,draft_schema_version,version,
                    parent_revision_id,owner_scope,origin_kind,ask_run_id,
                    research_task_id,source_answer_snapshot_json,source_answer_hash,
                    evidence_refs_json,scope_json,limitations_json,revalidation_state,
                    status,dedupe_identity,materialization_task_id,candidate_ids_json,
                    promotion_output_json,event_kind,command_id,command_payload_hash,
                    reason_json,created_at
                ) VALUES(?,?,?,1,NULL,'local_user_workspace',?,?,?,?,?,?,?,?,?,
                         'saved',?,NULL,'[]','{}','saved',?,?,?,?)
                """,
                (
                    revision_id,
                    draft_id,
                    KNOWLEDGE_DRAFT_SCHEMA_VERSION,
                    origin_kind,
                    ask_run_id,
                    research_task_id,
                    _json(source["snapshot"]),
                    source["answer_hash"],
                    _json(source["evidence_refs"]),
                    _json(source["scope"]),
                    _json(source["limitations"]),
                    "current" if source["current"] else "needs_revalidation",
                    dedupe,
                    request.command_id,
                    payload_hash,
                    _json({"authority": "draft_only_not_fact_or_citation"}),
                    _now(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM knowledge_draft_revisions WHERE draft_revision_id=?",
                (revision_id,),
            ).fetchone()
        return self._decode(row)

    def get(self, draft_id: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM knowledge_draft_revisions WHERE draft_id=? ORDER BY version",
                (draft_id,),
            ).fetchall()
        if not rows:
            raise KnowledgeDraftError("Draft not found", code="draft_not_found", http_status=404)
        history = [self._decode(value) for value in rows]
        return {"draft": history[-1], "history": history, "non_authoritative": True}

    def prepare_promotion(
        self, draft_id: str, request: DraftCommandRequest
    ) -> dict[str, Any]:
        replay = self._command_replay(
            draft_id, request.command_id, request.model_dump(mode="json")
        )
        if replay is not None:
            return replay
        current = self._expected(draft_id, request.expected_version)
        if current["status"] not in {"saved", "needs_revalidation", "failed"}:
            return current
        try:
            self._assert_source_current(current)
            spans = self._reconstruct_materialization_evidence(current)
            draft_binding = self._draft_materialization_binding(current)
        except KnowledgeDraftError as exc:
            self._block_revalidation(current, request, exc)
            raise
        started = self._append(
            current,
            status="materializing",
            event_kind="materialization_started",
            command_id=f"{request.command_id}:started"[:160],
            payload=request.model_dump(mode="json"),
            revalidation_state="current",
        )
        objective = str(current["scope"].get("query") or "保存当前证据为长期知识")
        try:
            created = self.product.create_task(
                CreateProductResearchRequest(
                    command_id=f"{request.command_id}:create"[:160],
                    objective=objective,
                    success_constraints=[],
                    run_immediately=False,
                )
            )
            task_id = str(created["task_id"])
            evidence_intake = self.product.intake_draft_materialization_evidence(
                task_id,
                command_id=f"{request.command_id}:evidence"[:160],
                draft_binding=draft_binding,
                spans=spans,
            )
            outcome = self.product.run_to_boundary(
                task_id,
                RunProductResearchRequest(command_id=f"{request.command_id}:run"[:160]),
            )
            if str(outcome.get("task_status")) != "terminal":
                raise KnowledgeDraftError(
                    f"provider-free materialization did not reach terminal boundary: {outcome}",
                    code="draft_materialization_incomplete",
                )
            intake = self.knowledge.intake_candidates(
                task_id,
                IntakeKnowledgeCandidatesRequest(
                    command_id=f"{request.command_id}:intake"[:160]
                ),
            )
            workspace = self.knowledge.get_workspace(task_id)
            candidates = [
                value for value in workspace["candidates"] if value["status"] == "pending_review"
            ]
            if not candidates:
                raise KnowledgeDraftError(
                    "materialization produced no pending Candidate",
                    code="draft_candidate_missing",
                )
        except Exception as exc:
            self._append(
                started,
                status="failed",
                event_kind="materialization_failed",
                command_id=request.command_id,
                payload=request.model_dump(mode="json"),
                reason={"error_code": str(getattr(exc, "code", type(exc).__name__))},
            )
            raise
        ready = self._append(
            started,
            status="promotion_ready",
            event_kind="materialization_ready",
            command_id=request.command_id,
            payload=request.model_dump(mode="json"),
            materialization_task_id=task_id,
            candidate_ids=[str(value["candidate_id"]) for value in candidates],
            reason={
                "provider_calls": 0,
                "candidate_count": int(intake["candidate_count"]),
                "evidence_intake": evidence_intake,
                "preview": candidates,
            },
        )
        return ready

    def confirm_promotion(
        self, draft_id: str, request: ConfirmDraftPromotionRequest, *, principal_id: str
    ) -> dict[str, Any]:
        replay = self._command_replay(
            draft_id, request.command_id, request.model_dump(mode="json")
        )
        if replay is not None:
            return replay
        current = self._expected(draft_id, request.expected_version)
        if current["status"] == "confirmed":
            return current
        if current["status"] != "promotion_ready":
            raise KnowledgeDraftError("Draft is not promotion ready", code="draft_not_ready")
        try:
            self._assert_source_current(current)
        except KnowledgeDraftError as exc:
            self._block_revalidation(current, request, exc)
            raise
        expected = list(current["candidate_ids"])
        if list(request.candidate_ids) != expected:
            raise KnowledgeDraftError(
                "confirmation must bind the exact preview Candidate set",
                code="draft_candidate_set_mismatch",
            )
        task_id = str(current["materialization_task_id"])
        workspace = self.knowledge.get_workspace(task_id)
        versions = {
            str(value["candidate_id"]): int(value["state_version"])
            for value in workspace["candidates"]
            if value["status"] == "pending_review"
        }
        if set(versions) != set(expected):
            self._block_revalidation(
                current,
                request,
                KnowledgeDraftError(
                    "Candidate preview changed and requires re-preparation",
                    code="draft_preview_stale",
                ),
            )
            raise KnowledgeDraftError(
                "Candidate preview changed and requires re-preparation",
                code="draft_preview_stale",
            )
        published = self.knowledge.publish_selected_candidates(
            task_id,
            PublishResearchKnowledgeRequest(
                command_id=request.command_id[:96],
                selections=[
                    PublishKnowledgeSelection(
                        candidate_id=value, expected_state_version=versions[value]
                    )
                    for value in expected
                ],
            ),
            principal_id=principal_id,
        )
        return self._append(
            current,
            status="confirmed",
            event_kind="promotion_confirmed",
            command_id=request.command_id,
            payload=request.model_dump(mode="json"),
            promotion_output=published,
            reason={"explicit_user_confirmation": True, "principal_id": principal_id},
        )

    def cancel(self, draft_id: str, request: DraftCommandRequest) -> dict[str, Any]:
        replay = self._command_replay(
            draft_id, request.command_id, request.model_dump(mode="json")
        )
        if replay is not None:
            return replay
        current = self._expected(draft_id, request.expected_version)
        if current["status"] == "confirmed":
            raise KnowledgeDraftError("confirmed Knowledge cannot be cancelled", code="draft_confirmed")
        return self._append(
            current,
            status="cancelled",
            event_kind="cancelled",
            command_id=request.command_id,
            payload=request.model_dump(mode="json"),
        )

    def _ask_source(self, run_id: str) -> dict[str, Any]:
        run = self.ask_runs.get_run(run_id)
        if run is None:
            raise KnowledgeDraftError("AskRun not found", code="draft_source_not_found", http_status=404)
        events = self.ask_runs.get_events(run_id)
        trusted = [value for value in events if value["event_type"] == "minimum_trust_passed"]
        unsafe = {"interrupted", "external_side_effect_unknown"}
        if (
            run["lifecycle_status"] != "completed"
            or run["answer_status"] == "insufficient"
            or not run["answer_blocks"]
            or not trusted
            or run["termination_reason"] in unsafe
        ):
            raise KnowledgeDraftError(
                "only a completed trusted answer can become a Draft",
                code="draft_source_not_eligible",
            )
        latest_revision = [value for value in events if value["event_type"] == "answer_revision_created"]
        answer_version = int(latest_revision[-1]["payload"]["to_version"]) if latest_revision else 1
        snapshot = {
            "answer_blocks": run["answer_blocks"],
            "citations": run["citations"],
            "status": run["answer_status"],
            "limitations": run["limitations"],
            "answer_version": answer_version,
            "trust_summary": run["trace"].get("trust_summary"),
        }
        for evidence in run["final_evidence"]:
            row = self.materializer._video_row(int(evidence["video_id"]))
            if row is None:
                raise KnowledgeDraftError(
                    "source Evidence is unavailable",
                    code="draft_source_evidence_unavailable",
                )
            binding = bind_live_current_version(
                _reference(row), db=self.db, video_id=int(evidence["video_id"])
            )
            if (
                binding.source_artifact_id != evidence["source_artifact_id"]
                or binding.source_version != evidence["source_version"]
            ):
                raise KnowledgeDraftError(
                    "source Evidence changed and requires a new trusted answer",
                    code="draft_source_evidence_changed",
                )
        evidence_refs = [
            {
                **dict(value),
                "collection_bindings": self._collection_bindings(int(value["video_id"])),
            }
            for value in run["final_evidence"]
        ]
        return {
            "mode": run["mode"],
            "snapshot": snapshot,
            "answer_hash": _hash(snapshot),
            "evidence_refs": evidence_refs,
            "scope": {"query": run["query"], "filters": run["filters"]},
            "limitations": run["limitations"],
            "current": True,
        }

    def _research_source(self, task_id: str) -> dict[str, Any]:
        raw = self.product.kernel.get_task(task_id)
        task = raw["task"]
        terminal_result_id = str(task.get("terminal_result_id") or "")
        result = next(
            (
                value
                for value in raw["results"]
                if str(value["result_id"]) == terminal_result_id
            ),
            None,
        )
        if (
            str(task["status"]) != "terminal"
            or result is None
            or not bool(result["is_task_terminal"])
            or str(result["answer_status"]) not in {"valid_success", "valid_partial"}
            or str(result["failure_class"]) != "none"
            or str(result["termination_reason"])
            not in {
                "answer_ready",
                "budget_exhausted",
                "no_new_evidence",
                "repeated_action",
                "constraint_unsatisfied",
            }
            or any(
                str(value.get("status")) in {"reserved", "in_flight", "unknown"}
                for value in raw["side_effects"]
            )
            or not raw["provisional_artifacts"]
        ):
            raise KnowledgeDraftError(
                "Research task is not eligible", code="draft_source_not_eligible"
            )
        with self.db.connect() as connection:
            link = connection.execute(
                "SELECT * FROM research_outer_result_links "
                "WHERE result_id=? AND task_id=?",
                (terminal_result_id, task_id),
            ).fetchone()
        if link is None:
            raise KnowledgeDraftError(
                "Research result is not bound to an audited artifact",
                code="draft_source_not_eligible",
            )
        artifact_id = str(link["artifact_id"])
        artifact = next(
            (
                value
                for value in raw["provisional_artifacts"]
                if str(value["artifact_id"]) == artifact_id
            ),
            None,
        )
        if (
            artifact is None
            or str(raw["provisional_artifacts"][-1]["artifact_id"]) != artifact_id
            or str(artifact["task_id"]) != task_id
            or str(artifact["goal_id"]) != str(result["goal_id"])
            or str(artifact["attempt_id"]) != str(result["attempt_id"])
            or str(link["goal_id"]) != str(result["goal_id"])
            or str(link["attempt_id"]) != str(result["attempt_id"])
            or str(artifact["answer_status"]) not in {"valid_success", "valid_partial"}
        ):
            raise KnowledgeDraftError(
                "Research result artifact binding is not eligible",
                code="draft_source_not_eligible",
            )
        answer_blocks = list(artifact.get("answer_blocks") or [])
        use_ids = [str(value) for value in artifact.get("evidence_use_ids") or []]
        evidence_ids = [str(value) for value in artifact.get("evidence_ids") or []]
        if not self._grounded_research_blocks(answer_blocks, evidence_ids) or not use_ids:
            raise KnowledgeDraftError(
                "Research artifact has no grounded Evidence",
                code="draft_source_not_eligible",
            )
        validation_ids = [
            str(value)
            for value in json.loads(str(link["validation_observation_ids_json"]))
        ]
        if not validation_ids:
            raise KnowledgeDraftError(
                "Research artifact has no current validation binding",
                code="draft_source_not_eligible",
            )
        evidence_refs, evidence_snapshot = self._research_evidence_bindings(
            task_id=task_id,
            goal_id=str(result["goal_id"]),
            attempt_id=str(result["attempt_id"]),
            use_ids=use_ids,
            evidence_ids=evidence_ids,
            validation_ids=validation_ids,
        )
        goal = next(
            (
                value
                for value in raw["goals"]
                if str(value["goal_id"]) == str(result["goal_id"])
            ),
            None,
        )
        if goal is None:
            raise KnowledgeDraftError(
                "Research result Goal is unavailable", code="draft_source_not_eligible"
            )
        snapshot = {
            "task": {
                "task_id": task_id,
                "terminal_result_id": terminal_result_id,
            },
            "result": {
                key: result[key]
                for key in (
                    "result_id",
                    "goal_id",
                    "attempt_id",
                    "checkpoint_id",
                    "answer_status",
                    "termination_reason",
                    "failure_class",
                    "is_task_terminal",
                )
            },
            "artifact": {
                key: artifact[key]
                for key in (
                    "artifact_id",
                    "artifact_schema_version",
                    "goal_id",
                    "attempt_id",
                    "checkpoint_id",
                    "objective",
                    "answer_status",
                    "answer_blocks",
                    "limitations",
                    "evidence_set_fingerprint",
                    "evidence_use_ids",
                    "evidence_ids",
                    "validation_observation_ids",
                    "generation_policy_version",
                    "validator_policy_version",
                    "artifact_hash",
                )
            },
            "result_link": {
                "audit_id": str(link["audit_id"]),
                "constraint_fingerprint": str(link["constraint_fingerprint"]),
                "validation_observation_ids": validation_ids,
                "generation_policy_version": str(link["generation_policy_version"]),
                "audit_policy_version": str(link["audit_policy_version"]),
                "evaluator_policy_versions": json.loads(
                    str(link["evaluator_policy_versions_json"])
                ),
            },
            "evidence": evidence_snapshot,
        }
        return {
            "mode": "research",
            "snapshot": snapshot,
            "answer_hash": _hash(snapshot),
            "evidence_refs": evidence_refs,
            "scope": {
                "query": str(goal.get("objective") or artifact["objective"]),
                "task_id": task_id,
                "goal_id": str(result["goal_id"]),
                "result_id": terminal_result_id,
                "artifact_id": artifact_id,
            },
            "limitations": artifact.get("limitations") or [],
            "current": True,
        }

    @staticmethod
    def _grounded_research_blocks(
        answer_blocks: list[Any], evidence_ids: list[str]
    ) -> bool:
        allowed = set(evidence_ids)
        if not answer_blocks or not allowed:
            return False
        for block in answer_blocks:
            if not isinstance(block, dict) or not str(block.get("text") or "").strip():
                return False
            citations = [str(value) for value in block.get("citation_ids") or []]
            if not citations or any(value not in allowed for value in citations):
                return False
        return True

    def _research_evidence_bindings(
        self,
        *,
        task_id: str,
        goal_id: str,
        attempt_id: str,
        use_ids: list[str],
        evidence_ids: list[str],
        validation_ids: list[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if len(use_ids) != len(set(use_ids)) or len(evidence_ids) != len(use_ids):
            raise KnowledgeDraftError(
                "Research artifact Evidence binding is malformed",
                code="draft_source_not_eligible",
            )
        with self.db.connect() as connection:
            identities = []
            for use_id in use_ids:
                row = connection.execute(
                    "SELECT eu.*, ei.* FROM research_evidence_uses eu "
                    "JOIN research_evidence_identities ei "
                    "ON ei.evidence_id=eu.evidence_id "
                    "WHERE eu.evidence_use_id=? AND eu.task_id=? "
                    "AND eu.goal_id=? AND eu.attempt_id=?",
                    (use_id, task_id, goal_id, attempt_id),
                ).fetchone()
                if row is None:
                    raise KnowledgeDraftError(
                        "Research artifact EvidenceUse is unbound",
                        code="draft_source_not_eligible",
                    )
                identities.append(row)
            validations = []
            for validation_id in validation_ids:
                row = connection.execute(
                    "SELECT * FROM research_evidence_validations "
                    "WHERE observation_id=? AND task_id=? AND goal_id=? "
                    "AND attempt_id=?",
                    (validation_id, task_id, goal_id, attempt_id),
                ).fetchone()
                if row is None:
                    raise KnowledgeDraftError(
                        "Research Evidence validation is unbound",
                        code="draft_source_not_eligible",
                    )
                validations.append(row)
        if set(evidence_ids) != {str(value["evidence_id"]) for value in identities}:
            raise KnowledgeDraftError(
                "Research artifact Evidence identity set changed",
                code="draft_source_not_eligible",
            )
        validation_by_use: dict[str, Any] = {}
        for validation in validations:
            use_id = str(validation["evidence_use_id"])
            if use_id in validation_by_use:
                raise KnowledgeDraftError(
                    "Research Evidence validation binding is ambiguous",
                    code="draft_source_not_eligible",
                )
            validation_by_use[use_id] = validation
        if set(validation_by_use) != set(use_ids):
            raise KnowledgeDraftError(
                "Research Evidence validation set is incomplete",
                code="draft_source_not_eligible",
            )
        refs: list[dict[str, Any]] = []
        snapshots: list[dict[str, Any]] = []
        for identity in identities:
            use_id = str(identity["evidence_use_id"])
            validation = validation_by_use[use_id]
            if (
                str(validation["evidence_id"]) != str(identity["evidence_id"])
                or str(validation["outcome"]) != "current"
                or str(validation["authority_mode"]) != "live_current_exact_replay"
                or str(validation["expected_source_version"])
                != str(identity["source_version"])
                or str(validation["observed_source_version"] or "")
                != str(identity["source_version"])
            ):
                raise KnowledgeDraftError(
                    "Research Evidence has no current validation binding",
                    code="draft_source_not_eligible",
                )
            observed = self.research_authority.observe(identity)
            if observed.outcome != "current" or observed.span is None:
                raise KnowledgeDraftError(
                    "Research source Evidence changed or is unavailable",
                    code="draft_source_evidence_changed",
                )
            ref = {
                "evidence_use_id": use_id,
                "evidence_id": str(identity["evidence_id"]),
                "citation_identity_version": str(
                    identity["citation_identity_version"]
                ),
                "validation_observation_id": str(validation["observation_id"]),
                "video_id": int(identity["video_id"]),
                "source_artifact_id": str(identity["source_artifact_id"]),
                "source_version": str(identity["source_version"]),
                "timeline_run_id": str(identity["timeline_run_id"]),
                "segment_ids": json.loads(str(identity["segment_ids_json"])),
                "segment_ordinals": json.loads(str(identity["segment_ordinals_json"])),
                "collection_bindings": self._collection_bindings(
                    int(identity["video_id"])
                ),
            }
            refs.append(ref)
            snapshots.append(
                {
                    **ref,
                    "citation_identity_version": str(
                        identity["citation_identity_version"]
                    ),
                    "start_time": float(identity["start_time"]),
                    "end_time": float(identity["end_time"]),
                    "quote_hash": str(identity["quote_hash"]),
                    "identity_payload_hash": str(identity["identity_payload_hash"]),
                    "validation_policy_version": str(
                        validation["validation_policy_version"]
                    ),
                    "validation_reason_code": str(validation["reason_code"]),
                }
            )
        return refs, snapshots

    def _assert_source_current(self, current: dict[str, Any]) -> None:
        if current["ask_run_id"]:
            source = self._ask_source(str(current["ask_run_id"]))
        else:
            source = self._research_source(str(current["research_task_id"]))
        if source["answer_hash"] != current["source_answer_hash"]:
            raise KnowledgeDraftError(
                "source changed and requires a new Draft preview",
                code="draft_source_changed",
            )
        if _hash(source["evidence_refs"]) != _hash(current["evidence_refs"]):
            raise KnowledgeDraftError(
                "source Evidence binding changed and requires a new Draft preview",
                code="draft_source_binding_changed",
            )
        if _hash(source["scope"]) != _hash(current["scope"]):
            raise KnowledgeDraftError(
                "source scope changed and requires a new Draft preview",
                code="draft_scope_changed",
            )
        if _hash(source["limitations"]) != _hash(current["limitations"]):
            raise KnowledgeDraftError(
                "source limitations changed and require a new Draft preview",
                code="draft_limitations_changed",
            )

    def _reconstruct_materialization_evidence(
        self, current: dict[str, Any]
    ) -> tuple[TranscriptEvidenceSpan, ...]:
        refs = list(current["evidence_refs"])
        if not refs:
            raise KnowledgeDraftError(
                "Draft has no reconstructable Evidence binding",
                code="draft_source_evidence_unavailable",
            )
        try:
            if current["ask_run_id"]:
                spans = self._reconstruct_ask_evidence(current, refs)
            else:
                spans = self._reconstruct_research_evidence(current, refs)
        except KnowledgeDraftError:
            raise
        except Exception as exc:
            raise KnowledgeDraftError(
                "Draft Evidence cannot be reconstructed from current sources",
                code="draft_source_evidence_changed",
            ) from exc
        if not spans or len(spans) != len(refs):
            raise KnowledgeDraftError(
                "Draft Evidence reconstruction is incomplete",
                code="draft_source_evidence_unavailable",
            )
        return tuple(spans)

    def _reconstruct_ask_evidence(
        self, current: dict[str, Any], refs: list[dict[str, Any]]
    ) -> list[TranscriptEvidenceSpan]:
        citations = list(current["source_answer_snapshot"].get("citations") or [])
        by_id: dict[str, dict[str, Any]] = {}
        for value in citations:
            citation_id = str(value.get("citation_id") or "")
            if not citation_id or citation_id in by_id:
                raise KnowledgeDraftError(
                    "Draft Ask citation binding is missing or ambiguous",
                    code="draft_source_evidence_unavailable",
                )
            by_id[citation_id] = dict(value)
        spans: list[TranscriptEvidenceSpan] = []
        for ref in refs:
            citation_id = str(ref.get("citation_id") or "")
            citation_payload = by_id.get(citation_id)
            if citation_payload is None:
                raise KnowledgeDraftError(
                    "Draft Ask Evidence has no exact Citation",
                    code="draft_source_evidence_unavailable",
                )
            citation = Citation.model_validate(citation_payload)
            span = self.materializer.reconstruct_citation(
                citation,
                execution_id=f"draft:{current['draft_revision_id']}",
                search_trace_id=f"draft:{current['draft_revision_id']}",
                query=str(current["scope"].get("query") or ""),
            )
            self._assert_reconstructed_binding(span, ref)
            spans.append(self._with_draft_carry_provenance(span, current))
        return spans

    def _reconstruct_research_evidence(
        self, current: dict[str, Any], refs: list[dict[str, Any]]
    ) -> list[TranscriptEvidenceSpan]:
        source_task_id = str(current["research_task_id"])
        spans: list[TranscriptEvidenceSpan] = []
        with self.db.connect() as connection:
            for ref in refs:
                identity = connection.execute(
                    "SELECT eu.*, ei.* FROM research_evidence_uses eu "
                    "JOIN research_evidence_identities ei ON ei.evidence_id=eu.evidence_id "
                    "WHERE eu.evidence_use_id=? AND eu.evidence_id=? AND eu.task_id=?",
                    (
                        str(ref.get("evidence_use_id") or ""),
                        str(ref.get("evidence_id") or ""),
                        source_task_id,
                    ),
                ).fetchone()
                if identity is None:
                    raise KnowledgeDraftError(
                        "Draft Research Evidence identity is unavailable",
                        code="draft_source_evidence_unavailable",
                    )
                observed = self.research_authority.observe(identity)
                if observed.outcome != "current" or observed.span is None:
                    raise KnowledgeDraftError(
                        "Draft Research Evidence is no longer current",
                        code="draft_source_evidence_changed",
                    )
                self._assert_reconstructed_binding(observed.span, ref)
                spans.append(self._with_draft_carry_provenance(observed.span, current))
        return spans

    @staticmethod
    def _assert_reconstructed_binding(
        span: TranscriptEvidenceSpan, ref: dict[str, Any]
    ) -> None:
        observed = {
            "citation_id": span.citation_id,
            "citation_identity_version": span.citation_identity_version,
            "video_id": span.video_id,
            "source_artifact_id": span.source_artifact_id,
            "source_version": span.source_version,
            "timeline_run_id": span.timeline_run_id,
            "segment_ids": list(span.segment_ids),
        }
        expected = {
            key: ref.get(key)
            for key in (
                "citation_id",
                "citation_identity_version",
                "video_id",
                "source_artifact_id",
                "source_version",
                "timeline_run_id",
                "segment_ids",
            )
        }
        if ref.get("evidence_id") is not None:
            expected["citation_id"] = ref.get("evidence_id")
        if observed != expected:
            raise KnowledgeDraftError(
                "Draft Evidence identity does not reconstruct exactly",
                code="draft_source_evidence_changed",
            )
        if ref.get("segment_ordinals") is not None and list(span.segment_ordinals) != list(
            ref["segment_ordinals"]
        ):
            raise KnowledgeDraftError(
                "Draft Evidence segment binding changed",
                code="draft_source_evidence_changed",
            )

    @staticmethod
    def _with_draft_carry_provenance(
        span: TranscriptEvidenceSpan, current: dict[str, Any]
    ) -> TranscriptEvidenceSpan:
        return span.model_copy(
            update={
                "retrieval_provenance": (
                    {
                        "execution_id": f"draft-materialization:{current['draft_revision_id']}",
                        "search_trace_id": f"draft-materialization:{current['draft_id']}",
                        "query": str(current["scope"].get("query") or ""),
                        "retrieval_method": "draft_materialization_carry_in",
                        "index_identity": {
                            "draft_id": current["draft_id"],
                            "draft_revision_id": current["draft_revision_id"],
                            "origin_kind": current["origin_kind"],
                        },
                    },
                )
            }
        )

    @staticmethod
    def _draft_materialization_binding(current: dict[str, Any]) -> dict[str, Any]:
        return {
            "draft_id": str(current["draft_id"]),
            "draft_revision_id": str(current["draft_revision_id"]),
            "draft_version": int(current["version"]),
            "source_answer_hash": str(current["source_answer_hash"]),
            "evidence_refs_hash": _hash(current["evidence_refs"]),
            "scope_hash": _hash(current["scope"]),
            "limitations_hash": _hash(current["limitations"]),
            "origin_kind": str(current["origin_kind"]),
            "origin_source_id": str(
                current["ask_run_id"] or current["research_task_id"]
            ),
        }

    def _collection_bindings(self, video_id: int) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT s.id AS source_db_id, s.platform, s.folder_id,
                       s.folder_title, s.status AS source_status,
                       m.favorite_time, m.removed_at
                FROM video_source_memberships m
                JOIN favorite_sources s ON s.id=m.source_id
                WHERE m.video_id=?
                ORDER BY s.platform, s.folder_id, s.id
                """,
                (video_id,),
            ).fetchall()
        return [dict(value) for value in rows]

    def _expected(self, draft_id: str, expected_version: int) -> dict[str, Any]:
        current = self.get(draft_id)["draft"]
        if int(current["version"]) != expected_version:
            raise KnowledgeDraftError("Draft version conflict", code="draft_version_conflict")
        return current

    def _block_revalidation(
        self,
        current: dict[str, Any],
        request: DraftCommandRequest,
        error: KnowledgeDraftError,
    ) -> dict[str, Any]:
        return self._append(
            current,
            status="needs_revalidation",
            event_kind="revalidation_blocked",
            command_id=f"{request.command_id}:blocked"[:160],
            payload=request.model_dump(mode="json"),
            revalidation_state="needs_revalidation",
            reason={"error_code": error.code, "message": str(error)},
        )

    def _command_replay(
        self, draft_id: str, command_id: str, payload: Any
    ) -> dict[str, Any] | None:
        payload_hash = _hash(payload)
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_draft_revisions WHERE draft_id=? AND command_id=?",
                (draft_id, command_id),
            ).fetchone()
        if row is None:
            return None
        if str(row["command_payload_hash"]) != payload_hash:
            raise KnowledgeDraftError(
                "command payload mismatch", code="draft_command_payload_mismatch"
            )
        return self._decode(row)

    def _append(
        self,
        current: dict[str, Any],
        *,
        status: str,
        event_kind: str,
        command_id: str,
        payload: Any,
        revalidation_state: str | None = None,
        materialization_task_id: str | None = None,
        candidate_ids: list[str] | None = None,
        promotion_output: dict[str, Any] | None = None,
        reason: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        version = int(current["version"]) + 1
        payload_hash = _hash(payload)
        revision_id = f"kdrev_{hashlib.sha256((current['draft_id'] + ':' + str(version)).encode()).hexdigest()[:32]}"
        with self.db.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM knowledge_draft_revisions WHERE draft_id=? AND command_id=?",
                (current["draft_id"], command_id),
            ).fetchone()
            if existing is not None:
                if str(existing["command_payload_hash"]) != payload_hash:
                    raise KnowledgeDraftError("command payload mismatch", code="draft_command_payload_mismatch")
                return self._decode(existing)
            connection.execute(
                """
                INSERT INTO knowledge_draft_revisions(
                    draft_revision_id,draft_id,draft_schema_version,version,
                    parent_revision_id,owner_scope,origin_kind,ask_run_id,
                    research_task_id,source_answer_snapshot_json,source_answer_hash,
                    evidence_refs_json,scope_json,limitations_json,revalidation_state,
                    status,dedupe_identity,materialization_task_id,candidate_ids_json,
                    promotion_output_json,event_kind,command_id,command_payload_hash,
                    reason_json,created_at
                ) VALUES(?,?,?,?,?,'local_user_workspace',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    revision_id,current["draft_id"],KNOWLEDGE_DRAFT_SCHEMA_VERSION,version,
                    current["draft_revision_id"],current["origin_kind"],current["ask_run_id"],
                    current["research_task_id"],_json(current["source_answer_snapshot"]),
                    current["source_answer_hash"],_json(current["evidence_refs"]),
                    _json(current["scope"]),_json(current["limitations"]),
                    revalidation_state or current["revalidation_state"],status,
                    current["dedupe_identity"],materialization_task_id or current["materialization_task_id"],
                    _json(candidate_ids if candidate_ids is not None else current["candidate_ids"]),
                    _json(promotion_output if promotion_output is not None else current["promotion_output"]),
                    event_kind,command_id,payload_hash,_json(reason or {}),_now(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM knowledge_draft_revisions WHERE draft_revision_id=?", (revision_id,)
            ).fetchone()
        return self._decode(row)

    @staticmethod
    def _decode(row: Any) -> dict[str, Any]:
        value = dict(row)
        for target, source in (
            ("source_answer_snapshot", "source_answer_snapshot_json"),
            ("evidence_refs", "evidence_refs_json"),
            ("scope", "scope_json"),
            ("limitations", "limitations_json"),
            ("candidate_ids", "candidate_ids_json"),
            ("promotion_output", "promotion_output_json"),
            ("reason", "reason_json"),
        ):
            value[target] = json.loads(str(value.pop(source)))
        value["authority"] = "draft_only_not_fact_or_citation"
        return value


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
